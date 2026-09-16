"""Selected-instrument price charts (MD-SELECTED-PRICE): the pure contract.

Windows, provider bar normalization (Alpaca consolidated SIP, and the older
Yahoo shape), stored-fallback reduction, chatter slots and their retained
tone, and the version-1 response assembly. Nothing here imports the app, the
database, Flask or a network client -- the spawned fetch child imports this
module, so it must stay that light. Every input is a bounded list of plain
mappings or an already parsed provider payload, and every output is a
JSON-serialisable dict matching SPEC section 3.

Rules this module exists to keep true:

- Missing is not zero. A slot with no valid represented bucket has
  `count: null`; only recorded valid zero contributions can add up to 0. A
  minute Alpaca did not report is absent, never a null or zero price.
- A bar close is not a tick at its start. A provider timestamp names the START
  of a bar; its close is known at the bar's end, and a bar still open when the
  data was received is provisional and plotted at the receipt instant.
- Adjustment basis is stated, never assumed: `raw` for Alpaca, which says so,
  and `unknown` for Yahoo, which does not.
- Hard boundaries stay hard. A session, a market state and a source/regime
  change each start a NEW hard segment, and no line or fill crosses one. A
  missing expected bar inside one segment is disclosed (`break_before`) but is
  not a boundary: the renderer connects the reported prices around it as a
  visual guide, which adds no observation.
- One coherent price dataset. Provider bars, stored quotes and stored daily
  closes are never combined, and competing quote sources are never
  interleaved.

The modeled calendar is market_calendars.us, used as it is. Boundaries are
modeled, not independently validated exchange facts.

Binding: radar-design/MD-SELECTED-PRICE-SPEC.md sections 2-5, as amended by
radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md and
radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import math
import re

from .analysis_contract import _finite_positive, _price_reason
from .market_calendars import us
from .prices import alpaca, yahoo

VERSION = 1
SPANS = ('1D', '1W')
NY = us.NY
UTC = dt.timezone.utc

#: Calendar days searched backwards for the sessions a window needs.
LOOKUP_DAYS = 16
WEEK_SESSIONS = 5
PRICE_INTERVAL_SECONDS = {'1D': 60, '1W': 300}
YAHOO_INTERVAL = {60: '1m', 300: '5m'}
INCLUDE_PREPOST = {'1D': True, '1W': False}
CHATTER_STEP_MINUTES = {'1D': 15, '1W': 60}
BUCKET = dt.timedelta(minutes=15)

MAX_SOURCES = 64
#: 16 days x 96 buckets x 64 sources; readers select one more as a sentinel.
SOURCE_ROW_LIMIT = LOOKUP_DAYS * 96 * MAX_SOURCES
QUOTE_ROW_LIMIT = 20_000
DAILY_ROW_LIMIT = 32
MAX_PRICE_POINTS = 2_000
#: Raw provider timestamps accepted before normalization rejects the body.
MAX_RAW_BARS = 4_000

#: A cached provider series is fresh this long after RECEIPT, then served with
#: its visible age until the stale limit, then not served at all.
FRESH_SECONDS = 60
STALE_LIMIT_SECONDS = 900
#: Consecutive stored quotes further apart than this are not joined.
QUOTE_GAP_SECONDS = 15 * 60

YAHOO_SOURCE = 'yahoo_chart'
YAHOO_PRICE_BASIS = 'provider_bar_close'
UNKNOWN_ADJUSTMENT = 'unknown'
YAHOO_REGIME = f'{YAHOO_SOURCE}:{YAHOO_PRICE_BASIS}:{UNKNOWN_ADJUSTMENT}'

#: Delayed consolidated SIP bars. `raw` is Alpaca's own documented adjustment
#: parameter, so unlike Yahoo the basis is stated rather than unknown.
ALPACA_SOURCE = 'alpaca_sip'
ALPACA_PRICE_BASIS = 'provider_bar_close'
RAW_ADJUSTMENT = 'raw'
ALPACA_REGIME = f'{ALPACA_SOURCE}:{ALPACA_PRICE_BASIS}:{RAW_ADJUSTMENT}'

#: Per provider source: the price basis, adjustment basis and regime id its
#: normalized series carries. Nothing else in the code branches on a source.
PROVIDER_PROFILES = {
    YAHOO_SOURCE: (YAHOO_PRICE_BASIS, UNKNOWN_ADJUSTMENT, YAHOO_REGIME),
    ALPACA_SOURCE: (ALPACA_PRICE_BASIS, RAW_ADJUSTMENT, ALPACA_REGIME),
}

ACQUISITION_STATES = ('ready', 'pending', 'backoff', 'busy', 'disabled', 'unavailable')
TONE_CATEGORIES = ('bullish', 'bearish', 'neutral', 'unjudged', 'unavailable')
BUCKET_STATUSES = frozenset({'ok', 'truncated', 'missing'})

_PLAIN_SYMBOL = re.compile(r'^[A-Z0-9]{1,10}$')
_CLASS_SHARE = re.compile(r'^([A-Z0-9]{1,8})\.([A-Z0-9]{1,3})$')


class ChartError(Exception):
    """A request or bounded read that cannot be answered as asked.

    `code` is the stable public value, `status` the HTTP status. Messages
    never carry SQL, paths, provider bodies or credentials.
    """

    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


# --- time helpers ---------------------------------------------------------------

def aware_utc(when: dt.datetime) -> dt.datetime:
    if when.tzinfo is None:
        raise ValueError('a timezone-aware instant is required')
    return when.astimezone(UTC)


def naive_utc(when):
    if when is None:
        return None
    if isinstance(when, dt.datetime) and when.tzinfo is not None:
        return when.astimezone(UTC).replace(tzinfo=None)
    return when


def iso_z(when) -> str | None:
    if when is None:
        return None
    when = naive_utc(when)
    return when.replace(microsecond=0).isoformat() + 'Z'


def from_epoch(seconds: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(seconds, UTC)


# --- windows ----------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Session:
    """One modeled US trading day, as aware UTC instants."""
    date: dt.date
    opens_at: dt.datetime
    regular_opens_at: dt.datetime
    regular_closes_at: dt.datetime
    closes_at: dt.datetime


@dataclasses.dataclass(frozen=True)
class Window:
    """The one explicit period both price and chatter are read for."""
    span: str
    start: dt.datetime
    end: dt.datetime
    sessions: tuple
    partial: bool
    interval_seconds: int
    include_prepost: bool
    step_minutes: int

    @property
    def session_dates(self) -> tuple:
        return tuple(session.date for session in self.sessions)

    @property
    def waiting(self) -> bool:
        """A zero-length window: 04:00 ET exactly, or a regular open this
        instant. An explanatory state, never a division by zero."""
        return self.end <= self.start

    def price_intervals(self) -> list[tuple[dt.datetime, dt.datetime]]:
        """Where a price bar may START: the extended day on 1D, each regular
        session on 1W. Clipped to the window."""
        out = []
        for session in self.sessions:
            if self.include_prepost:
                left, right = session.opens_at, session.closes_at
            else:
                left, right = session.regular_opens_at, session.regular_closes_at
            left, right = max(left, self.start), min(right, self.end)
            if left < right:
                out.append((left, right))
        return out


def session_for(day: dt.date) -> Session:
    bounds = us.session_bounds(dt.datetime.combine(day, dt.time(12), tzinfo=NY))
    return Session(day, bounds.opens_at.astimezone(UTC),
                   bounds.regular_opens_at.astimezone(UTC),
                   bounds.regular_closes_at.astimezone(UTC),
                   bounds.closes_at.astimezone(UTC))


def window_for(span: str, now: dt.datetime) -> Window:
    """SPEC section 2. `now` must be aware; the result never reaches past it."""
    if span not in SPANS:
        raise ChartError('invalid_span', 400, 'span must be 1D or 1W')
    now = aware_utc(now)
    today = now.astimezone(NY).date()
    interval = PRICE_INTERVAL_SECONDS[span]
    common = dict(span=span, interval_seconds=interval,
                  include_prepost=INCLUDE_PREPOST[span],
                  step_minutes=CHATTER_STEP_MINUTES[span])
    if span == '1D':
        for offset in range(LOOKUP_DAYS):
            day = today - dt.timedelta(days=offset)
            if not us.is_trading_day(day):
                continue
            session = session_for(day)
            if offset == 0 and session.opens_at <= now < session.closes_at:
                return Window(start=session.opens_at, end=now, sessions=(session,),
                              partial=True, **common)
            if session.closes_at <= now:
                return Window(start=session.opens_at, end=session.closes_at,
                              sessions=(session,), partial=False, **common)
        raise ChartError('window_unavailable', 503,
                         'no modeled session was found in the bounded lookup')

    sessions = []
    for offset in range(LOOKUP_DAYS):
        day = today - dt.timedelta(days=offset)
        if not us.is_trading_day(day):
            continue
        session = session_for(day)
        # Today counts only from its regular open onward.
        if offset == 0 and now < session.regular_opens_at:
            continue
        sessions.append(session)
        if len(sessions) == WEEK_SESSIONS:
            break
    if len(sessions) < WEEK_SESSIONS:
        raise ChartError('window_unavailable', 503,
                         'five modeled sessions were not found in the bounded lookup')
    sessions.reverse()
    last = sessions[-1]
    live = last.regular_opens_at <= now < last.regular_closes_at
    return Window(start=sessions[0].regular_opens_at,
                  end=now if live else last.regular_closes_at,
                  sessions=tuple(sessions), partial=live, **common)


def window_label(window: Window) -> str:
    if window.span == '1W':
        return '5 sessions · today partial' if window.partial else '5 sessions'
    return 'current session so far' if window.partial else 'last completed session'


def bands(window: Window) -> list[dict]:
    """Contiguous market-state intervals covering [start, end]. They describe
    the PRICE market, not chatter availability."""
    if window.waiting:
        return []
    marks = []
    first = window.start.astimezone(NY).date() - dt.timedelta(days=1)
    last = window.end.astimezone(NY).date() + dt.timedelta(days=1)
    day = first
    while day <= last:
        if us.is_trading_day(day):
            s = session_for(day)
            marks += [(s.opens_at, s.regular_opens_at, 'premarket'),
                      (s.regular_opens_at, s.regular_closes_at, 'regular'),
                      (s.regular_closes_at, s.closes_at, 'afterhours')]
        day += dt.timedelta(days=1)
    out: list[list] = []

    def push(left, right, state):
        left, right = max(left, window.start), min(right, window.end)
        if left >= right:
            return
        if out and out[-1][2] == state and out[-1][1] == left:
            out[-1][1] = right
        else:
            out.append([left, right, state])

    cursor = window.start
    for left, right, state in sorted(marks):
        if right <= window.start or left >= window.end:
            continue
        if left > cursor:
            push(cursor, left, 'closed')
        push(left, right, state)
        cursor = max(cursor, right)
    if cursor < window.end:
        push(cursor, window.end, 'closed')
    return [{'from': iso_z(a), 'to': iso_z(b), 'state': s} for a, b, s in out]


def state_at(window: Window, when: dt.datetime) -> str:
    for session in window.sessions:
        if session.opens_at <= when < session.regular_opens_at:
            return f'premarket:{session.date}'
        if session.regular_opens_at <= when < session.regular_closes_at:
            return f'regular:{session.date}'
        if session.regular_closes_at <= when < session.closes_at:
            return f'afterhours:{session.date}'
    return 'closed'


def slot_bounds(window: Window) -> list[tuple[dt.datetime, dt.datetime]]:
    """Histogram slots anchored at window.start; the last may be short."""
    step = dt.timedelta(minutes=window.step_minutes)
    out = []
    cursor = window.start
    while cursor < window.end:
        out.append((cursor, min(cursor + step, window.end)))
        cursor += step
    return out


# --- identity ---------------------------------------------------------------------

def fingerprint(company_id, instrument_id, provider_symbol, currency, mic, mapped_at) -> str:
    text = '|'.join(str(part) for part in (company_id, instrument_id, provider_symbol,
                                           currency, mic, iso_z(mapped_at)))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]


def yahoo_symbol(provider_symbol) -> str | None:
    """The adapter-local Yahoo spelling, or None for an unknown form.

    Ordinary symbols pass unchanged; one class-share dot between alphanumeric
    parts becomes a hyphen (BRK.B -> BRK-B). Anything else -- slashes,
    hyphens, several dots, lower case -- is refused rather than guessed, and
    the chart falls back to stored data. The stored mapping is never changed.
    """
    if not isinstance(provider_symbol, str):
        return None
    if _PLAIN_SYMBOL.match(provider_symbol):
        return provider_symbol
    match = _CLASS_SHARE.match(provider_symbol)
    if match:
        return f'{match.group(1)}-{match.group(2)}'
    return None


def alpaca_symbol(provider_symbol) -> str | None:
    """Alpaca's spelling, which is Radar's own: `BRK.B` stays `BRK.B`.

    The validation resolved the dot form on the first attempt, so nothing is
    rewritten and no alternative spelling is ever tried. Unknown forms --
    slashes, hyphens, several dots, lower case -- are refused rather than
    guessed, and the chart falls back to stored data.
    """
    if not isinstance(provider_symbol, str):
        return None
    if _PLAIN_SYMBOL.match(provider_symbol) or _CLASS_SHARE.match(provider_symbol):
        return provider_symbol
    return None


def provider_symbol_supported(provider_symbol) -> bool:
    """Whether either adapter has a spelling for this mapped symbol. Both
    accept exactly the plain and single-class-share forms."""
    return alpaca_symbol(provider_symbol) is not None


def expected_intervals(window: Window) -> int:
    """How many whole bars the window could hold, for the chart's coverage
    wording. Provider coverage may be far below it without being wrong."""
    seconds = sum((right - left).total_seconds() for left, right in window.price_intervals())
    return int(seconds // window.interval_seconds)


def request_spec(identity: dict, window: Window) -> dict | None:
    """The validated public parameters a fetch child receives, or None when
    the symbol has no Yahoo form. Nothing browser-supplied reaches this."""
    symbol = yahoo_symbol(identity.get('provider_symbol'))
    if symbol is None or window.waiting:
        return None
    return {
        'version': VERSION,
        'source': YAHOO_SOURCE,
        'symbol': symbol,
        'currency': identity['currency'],
        'mic': identity['mic'],
        'interval': YAHOO_INTERVAL[window.interval_seconds],
        'interval_seconds': window.interval_seconds,
        'period1': int(window.start.timestamp()),
        # Clipped to now by the window itself; a closed session ends at its
        # modeled close.
        'period2': int(math.ceil(window.end.timestamp())),
        'include_prepost': window.include_prepost,
        'anchor': int(window.start.timestamp()),
        'intervals': [[int(a.timestamp()), int(b.timestamp())]
                      for a, b in window.price_intervals()],
    }


#: Why no Alpaca request was built. Each is an explanatory unavailable state,
#: never a retry loop and never a zero-valued series.
ALPACA_REFUSALS = {
    'session_not_started': 'the session has only just begun',
    'unsupported_symbol': 'the mapped symbol has no supported provider form',
    'waiting_for_delay': 'delayed consolidated SIP data does not reach this window yet',
}


def alpaca_request_spec(identity: dict, window: Window, *, now) -> tuple:
    """`(spec, None)` or `(None, refusal)` for ONE bounded Alpaca request.

    One symbol, one call, `feed=sip`, `adjustment=raw`, `sort=asc`,
    `limit=10000`, and an `end` clamped to `min(window end, now - 16 minutes)`
    -- a minute past the documented fifteen-minute Basic delay, on purpose. A
    window older than the clamp keeps its own contract end. When the clamp
    leaves nothing, no request is built at all: Alpaca is not asked for data
    that cannot exist yet.
    """
    if window.waiting:
        return None, 'session_not_started'
    symbol = alpaca_symbol(identity.get('provider_symbol'))
    if symbol is None:
        return None, 'unsupported_symbol'
    end = min(window.end, aware_utc(now) - dt.timedelta(seconds=alpaca.DELAY_MARGIN_SECONDS))
    if end <= window.start:
        return None, 'waiting_for_delay'
    return {
        'version': VERSION,
        'source': ALPACA_SOURCE,
        'symbol': symbol,
        'currency': identity['currency'],
        'mic': identity['mic'],
        'timeframe': alpaca.TIMEFRAMES[window.interval_seconds],
        'interval_seconds': window.interval_seconds,
        'start': iso_z(window.start),
        'end': iso_z(end),
        'feed': alpaca.FEED,
        'adjustment': alpaca.ADJUSTMENT,
        'sort': alpaca.SORT,
        'limit': alpaca.LIMIT,
        'anchor': int(window.start.timestamp()),
        'intervals': [[int(a.timestamp()), int(b.timestamp())]
                      for a, b in window.price_intervals()],
    }, None


def request_spec_for(source: str, identity: dict, window: Window, *, now) -> tuple:
    """`(spec, refusal)` for the admitted source."""
    if source == ALPACA_SOURCE:
        return alpaca_request_spec(identity, window, now=now)
    spec = request_spec(identity, window)
    if spec is not None:
        return spec, None
    return None, 'session_not_started' if window.waiting else 'unsupported_symbol'


def cache_key(identity: dict, window: Window, *, source: str = YAHOO_SOURCE) -> tuple:
    """Stable across a moving `now`: neither period2 nor the delay clamp is in
    it. The source is, so two adapters never share one cached series."""
    return (VERSION, source, identity['fingerprint'], window.span,
            window.interval_seconds, window.include_prepost,
            tuple(day.isoformat() for day in window.session_dates))


# --- Yahoo bars -------------------------------------------------------------------

_INVALID = object()


def _close_value(close):
    """A plotted value, None for an explicit null/nonpositive bar, or _INVALID
    for something that is not a number at all."""
    if close is None:
        return None
    if isinstance(close, bool) or not isinstance(close, (int, float)):
        return _INVALID
    value = float(close)
    if not math.isfinite(value):
        return _INVALID
    return value if value > 0 else None


def _intervals_ok(spec) -> bool:
    return (isinstance(spec.get('intervals'), list)
            and len(spec['intervals']) <= LOOKUP_DAYS
            and all(isinstance(pair, list) and len(pair) == 2
                    and all(isinstance(x, int) and not isinstance(x, bool) for x in pair)
                    for pair in spec['intervals']))


def _alpaca_spec_ok(spec) -> bool:
    """Structure only. `start >= end` is not a malformed request -- it is the
    delay clamp having nothing to ask for -- so the child answers `waiting`
    for it rather than calling it invalid."""
    try:
        return (isinstance(spec, dict) and spec.get('version') == VERSION
                and spec.get('source') == ALPACA_SOURCE
                and alpaca_symbol(spec.get('symbol')) is not None
                and spec.get('interval_seconds') in alpaca.TIMEFRAMES
                and spec.get('timeframe') == alpaca.TIMEFRAMES[spec['interval_seconds']]
                and spec.get('feed') == alpaca.FEED
                and spec.get('adjustment') == alpaca.ADJUSTMENT
                and spec.get('sort') == alpaca.SORT
                and spec.get('limit') == alpaca.LIMIT
                and _alpaca_instant(spec.get('start')) is not None
                and _alpaca_instant(spec.get('end')) is not None
                and isinstance(spec.get('anchor'), int) and not isinstance(spec['anchor'], bool)
                and _intervals_ok(spec))
    except (TypeError, AttributeError, KeyError):
        return False


def spec_ok(spec) -> bool:
    """Whichever adapter this request names."""
    if isinstance(spec, dict) and spec.get('source') == ALPACA_SOURCE:
        return _alpaca_spec_ok(spec)
    return _spec_ok(spec)


def _spec_ok(spec) -> bool:
    try:
        return (isinstance(spec, dict) and spec.get('version') == VERSION
                and spec.get('source', YAHOO_SOURCE) == YAHOO_SOURCE
                and isinstance(spec.get('symbol'), str)
                and yahoo_symbol(spec['symbol'].replace('-', '.')) is not None
                and spec.get('interval_seconds') in YAHOO_INTERVAL
                and spec.get('interval') == YAHOO_INTERVAL[spec['interval_seconds']]
                and all(isinstance(spec.get(k), int) and not isinstance(spec.get(k), bool)
                        for k in ('period1', 'period2', 'anchor'))
                and spec['period1'] < spec['period2']
                and isinstance(spec.get('include_prepost'), bool)
                and _intervals_ok(spec))
    except (TypeError, AttributeError, KeyError):
        return False


def normalize_yahoo(payload, spec: dict, *, received_at: float) -> dict:
    """Validated bars for one request, or a classified refusal.

    The result is what crosses the child's result channel: `kind` plus, for
    `ok`, `[start_epoch, value|None]` pairs on the requested grid inside the
    requested sessions. Points are made from it at response time.
    """
    if not _spec_ok(spec):
        return {'kind': 'invalid', 'reason': 'request_spec'}
    result = yahoo._result(payload)
    if result is None:
        return {'kind': 'invalid', 'reason': 'envelope'}
    if not yahoo._identity_ok(result.get('meta'), spec['symbol'], spec['currency'], spec['mic']):
        return {'kind': 'identity_mismatch', 'reason': 'returned symbol, currency or exchange'}
    raw = yahoo._bars(result)
    if raw is None:
        # An envelope with no timestamp array at all is an empty answer, not a
        # malformed one; anything else unparallel is invalid.
        if result.get('timestamp') is None and isinstance(result.get('indicators'), dict):
            return {'kind': 'empty', 'reason': 'no bars'}
        return {'kind': 'invalid', 'reason': 'arrays'}
    if len(raw) > MAX_RAW_BARS:
        return {'kind': 'invalid', 'reason': 'too many bars'}
    interval = spec['interval_seconds']
    anchor = spec['anchor']
    intervals = spec['intervals']
    previous = None
    bars = []
    off_grid = outside = nulls = 0
    for stamp, close, _volume in raw:
        if previous is not None and stamp <= previous:
            return {'kind': 'invalid', 'reason': 'timestamps not increasing'}
        previous = stamp
        value = _close_value(close)
        if value is _INVALID:
            return {'kind': 'invalid', 'reason': 'close is not a finite number'}
        if (stamp - anchor) % interval:
            # A quote-like point between grid instants is not a completed
            # interval. Omitted, counted, never turned into a headline.
            off_grid += 1
            continue
        if not any(left <= stamp < right for left, right in intervals):
            outside += 1
            continue
        if value is None:
            nulls += 1
        bars.append([stamp, value])
    if len(bars) > MAX_PRICE_POINTS:
        return {'kind': 'invalid', 'reason': 'too many points'}
    if not any(value is not None for _, value in bars):
        return {'kind': 'empty', 'reason': 'no valid bar in the window',
                'off_grid': off_grid, 'outside': outside}
    return {'kind': 'ok', 'source': YAHOO_SOURCE, 'bars': bars, 'off_grid': off_grid,
            'outside': outside, 'nulls': nulls, 'received_at': received_at}


# --- Alpaca bars ------------------------------------------------------------------

_FRACTION = re.compile(r'\.(\d+)')


def _alpaca_instant(text) -> dt.datetime | None:
    """One RFC-3339 instant, or None. Every observed bar carried whole
    seconds, but the documentation reserves nanosecond precision, so the
    fraction is accepted and truncated to what datetime can hold."""
    if not isinstance(text, str) or not text.strip():
        return None
    value = text.strip()
    if value[-1] in 'Zz':
        value = value[:-1] + '+00:00'
    value = _FRACTION.sub(lambda match: '.' + match.group(1)[:6].ljust(6, '0'), value, count=1)
    try:
        when = dt.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return when.astimezone(UTC) if when.tzinfo is not None else None


def normalize_alpaca(payload, spec: dict, *, received_at: float) -> dict:
    """Validated consolidated-SIP bars for one request, or a classified
    refusal, in the same shape the supervisor already acts on.

    What the 2026-09-16 validation established and this enforces: exactly one
    bars key, equal to the requested symbol; a non-null `next_page_token` is
    truncation, never a complete answer; a minute without a trade is ABSENT,
    so a null or nonpositive close is a malformed answer rather than a gap;
    `t` is the bar START. Timestamps outside the window's half-open intervals
    are dropped -- which is what keeps the exact regular-close bar out of 1W
    regular data while the 1D extended window keeps it as after-hours.
    """
    if not _alpaca_spec_ok(spec):
        return {'kind': 'invalid', 'reason': 'request_spec'}
    if not isinstance(payload, dict):
        return {'kind': 'invalid', 'reason': 'envelope'}
    if payload.get('next_page_token') is not None:
        return {'kind': 'truncated', 'reason': 'the provider answer was paginated'}
    groups = payload.get('bars')
    if not isinstance(groups, dict):
        return {'kind': 'invalid', 'reason': 'envelope'}
    if not groups:
        return {'kind': 'empty', 'reason': 'no bars'}
    if set(groups) != {spec['symbol']}:
        return {'kind': 'identity_mismatch', 'reason': 'the answer named another symbol'}
    raw = groups[spec['symbol']]
    if not isinstance(raw, list):
        return {'kind': 'invalid', 'reason': 'series'}
    if not raw:
        return {'kind': 'empty', 'reason': 'no bars'}
    if len(raw) > MAX_RAW_BARS:
        return {'kind': 'invalid', 'reason': 'too many bars'}
    interval = spec['interval_seconds']
    anchor = spec['anchor']
    intervals = spec['intervals']
    previous = None
    bars = []
    off_grid = outside = 0
    for row in raw:
        when = _alpaca_instant(row.get(alpaca.TIMESTAMP_KEY)) if isinstance(row, dict) else None
        if when is None:
            return {'kind': 'invalid', 'reason': 'timestamp'}
        epoch = when.timestamp()
        if previous is not None and epoch <= previous:
            return {'kind': 'invalid', 'reason': 'timestamps not increasing'}
        previous = epoch
        close = row.get(alpaca.CLOSE_KEY)
        if (close is None or isinstance(close, bool) or not isinstance(close, (int, float))
                or not math.isfinite(close) or close <= 0):
            # Alpaca omits a minute it has nothing for, so a null, zero or
            # negative close is a malformed answer, not a disclosed gap.
            return {'kind': 'invalid', 'reason': 'close is not a finite positive number'}
        stamp = int(epoch)
        if stamp != epoch or (stamp - anchor) % interval:
            off_grid += 1
            continue
        if not any(left <= stamp < right for left, right in intervals):
            outside += 1
            continue
        bars.append([stamp, float(close)])
    if len(bars) > MAX_PRICE_POINTS:
        return {'kind': 'invalid', 'reason': 'too many points'}
    if not bars:
        return {'kind': 'empty', 'reason': 'no bar inside the window',
                'off_grid': off_grid, 'outside': outside}
    return {'kind': 'ok', 'source': ALPACA_SOURCE, 'bars': bars, 'off_grid': off_grid,
            'outside': outside, 'nulls': 0, 'received_at': received_at}


def yahoo_points(bars, window: Window, received_at: dt.datetime) -> list[dict]:
    return provider_points(bars, window, received_at, regime=YAHOO_REGIME)


def provider_points(bars, window: Window, received_at: dt.datetime, *,
                    regime: str = YAHOO_REGIME) -> list[dict]:
    """Points for normalized bars, clipped to window.end.

    A bar still open when the data was RECEIVED is provisional and plotted at
    the receipt instant, however much later it is served from cache: its close
    was captured mid-bar.

    `segment` is the HARD boundary the renderer groups by: the market
    state and session date this bar starts in, plus the source/regime. Nothing
    is drawn across two of them. `break_before` is the softer fact that the
    previous reported bar was not the adjacent one (or had no valid close);
    it is disclosed but does NOT split the drawing, because connecting two
    reported prices across a quiet minute adds no observation.
    """
    interval = window.interval_seconds
    step = dt.timedelta(seconds=interval)
    points = []
    previous_start = previous_state = None
    previous_valid = False
    for stamp, value in bars:
        start = from_epoch(stamp)
        if start < window.start or start >= window.end:
            continue
        end = start + step
        provisional = end > received_at or end > window.end
        at = min(end, received_at, window.end) if provisional else end
        state = state_at(window, start)
        break_before = bool(points) and (
            value is None or not previous_valid
            or start - previous_start != step or state != previous_state)
        points.append({'at': iso_z(at), 'start': iso_z(start), 'end': iso_z(end),
                       'value': value, 'provisional': provisional,
                       'break_before': break_before if points else False,
                       'regime': regime, 'segment': f'{state}|{regime}'})
        previous_start, previous_state, previous_valid = start, state, value is not None
    return points


def provider_price(bars_result: dict, window: Window, identity: dict, *,
                   now: dt.datetime) -> dict | None:
    """The provider price block, or None when no valid point is inside the
    window (the caller then tries the stored fallback).

    `observations` and `expected_intervals` are what the chart discloses
    instead of implying complete coverage: an illiquid listing reporting 64 of
    390 minutes is 64 real observations, not a broken chart.
    """
    source = bars_result.get('source', YAHOO_SOURCE)
    price_basis, adjustment, regime = PROVIDER_PROFILES[source]
    received = from_epoch(bars_result['received_at'])
    points = provider_points(bars_result['bars'], window, received, regime=regime)
    valid = [p for p in points if p['value'] is not None]
    if not valid:
        return None
    age = max(0, int((aware_utc(now) - received).total_seconds()))
    return {
        'source': source, 'kind': 'bar_close', 'currency': 'USD',
        'mic': identity['mic'], 'price_basis': price_basis,
        'adjustment_basis': adjustment,
        'regimes': [{'id': regime, 'source': source, 'price_basis': price_basis,
                     'adjustment_basis': adjustment}],
        'received_at': iso_z(received), 'cache_age_seconds': age,
        'latest_observation_at': valid[-1]['at'],
        'stale': age >= FRESH_SECONDS, 'fallback': False,
        'interval_seconds': window.interval_seconds,
        'observations': len(valid), 'expected_intervals': expected_intervals(window),
        'points': points,
    }


def provider_warnings(bars_result: dict) -> list[str]:
    out = []
    if bars_result.get('off_grid'):
        out.append(f"price: {bars_result['off_grid']} provider point(s) off the "
                   f"bar grid were omitted; they are not completed intervals")
    if bars_result.get('nulls'):
        out.append(f"price: {bars_result['nulls']} provider bar(s) had no valid close "
                   'and are shown as gaps')
    return out


# --- stored fallback --------------------------------------------------------------

def _regime_id(source, price_basis, adjustment_basis) -> str:
    return f'{source}:{price_basis}:{adjustment_basis}'


def quote_fallback(rows, identity: dict, window: Window, *, read_start: dt.datetime) -> tuple[dict | None, list[str]]:
    """1D retained event-time quotes of this instrument inside the window.

    One provider source only: when several have valid events, the source with
    the latest event is used and the omission is disclosed. Legacy rows
    without market/MIC, shadow rows, rows fetched after this read began, rows
    before the mapping and nonpositive prices are never used.
    """
    rows = list(rows)
    if len(rows) > QUOTE_ROW_LIMIT:
        return None, ['price: stored quotes exceed the bounded read; the fallback was refused']
    start, end = naive_utc(window.start), naive_utc(window.end)
    mapped_at = naive_utc(identity['mapped_at_dt'])
    read_start = naive_utc(read_start)
    by_source: dict[str, dict] = {}
    rejected = 0
    for row in rows:
        when = naive_utc(row.get('quote_ts'))
        fetched = naive_utc(row.get('fetched_at'))
        price = _finite_positive(row.get('price'))
        source = (row.get('source') or '').strip()
        basis = (row.get('price_basis') or '').strip()
        if (row.get('is_shadow') or row.get('market') != 'us' or row.get('mic') != identity['mic']
                or row.get('currency') != 'USD' or when is None or fetched is None):
            rejected += 1
            continue
        if not (start <= when <= end) or when < mapped_at or fetched > read_start or when > fetched:
            rejected += 1
            continue
        if price is None or not source or basis not in ('trade', 'midpoint', 'close'):
            rejected += 1
            continue
        observations = by_source.setdefault(source, {})
        observations.setdefault(when, set()).add((price, basis))
    if not by_source:
        return None, []
    latest = {source: max(obs) for source, obs in by_source.items()}
    chosen = max(latest, key=lambda s: (latest[s], s))
    warnings = []
    if len(by_source) > 1:
        others = sorted(s for s in by_source if s != chosen)
        warnings.append('price: stored quotes from ' + ', '.join(others)
                        + f' were not combined with {chosen}; coverage of the fallback is incomplete')
    points = []
    previous = None
    conflicts = 0
    run = 0
    for when in sorted(by_source[chosen]):
        values = by_source[chosen][when]
        if len(values) > 1:
            conflicts += 1
            continue
        price, basis = next(iter(values))
        regime = _regime_id(chosen, basis, UNKNOWN_ADJUSTMENT)
        aware = when.replace(tzinfo=UTC)
        state = state_at(window, aware)
        break_before = previous is not None and (
            previous['regime'] != regime or previous['state'] != state
            or (when - previous['when']).total_seconds() > QUOTE_GAP_SECONDS)
        # A stored quote has no expected grid, so an hours-long hole between
        # two polls is itself a hard boundary: a line across it would be a
        # claim about a period nothing was recorded for.
        if break_before:
            run += 1
        points.append({'at': iso_z(when), 'start': iso_z(when), 'end': iso_z(when),
                       'value': price, 'provisional': False,
                       'break_before': break_before, 'regime': regime,
                       'segment': f'{state}|{regime}|{run}'})
        previous = {'regime': regime, 'state': state, 'when': when}
    if conflicts:
        warnings.append(f'price: {conflicts} stored quote instant(s) carried conflicting '
                        'prices and were left out')
    if not points:
        return None, warnings
    regimes = []
    for point in points:
        if not regimes or regimes[-1]['id'] != point['regime']:
            source, basis, adjustment = point['regime'].split(':')
            if all(r['id'] != point['regime'] for r in regimes):
                regimes.append({'id': point['regime'], 'source': source,
                                'price_basis': basis, 'adjustment_basis': adjustment})
    received = max(naive_utc(r['fetched_at']) for r in rows
                   if (r.get('source') or '').strip() == chosen and r.get('fetched_at') is not None
                   and naive_utc(r['fetched_at']) <= read_start)
    last_basis = points[-1]['regime'].split(':')[1]
    return {
        'source': chosen, 'kind': 'stored_quote', 'currency': 'USD', 'mic': identity['mic'],
        'price_basis': last_basis, 'adjustment_basis': UNKNOWN_ADJUSTMENT,
        'regimes': regimes, 'received_at': iso_z(received), 'cache_age_seconds': None,
        'latest_observation_at': points[-1]['at'],
        'stale': (read_start - received).total_seconds() >= FRESH_SECONDS,
        'fallback': True, 'interval_seconds': None,
        'observations': len(points), 'expected_intervals': None, 'points': points,
    }, warnings


def daily_fallback(rows, identity: dict, window: Window, *, read_start: dt.datetime) -> tuple[dict | None, list[str]]:
    """Eligible stored daily closes of this instrument whose modeled regular
    close falls inside the window. Each is its own dot: a line between two
    daily closes would draw prices nobody observed across a session."""
    rows = list(rows)
    if len(rows) > DAILY_ROW_LIMIT:
        return None, ['price: stored daily closes exceed the bounded read; the fallback was refused']
    read_start = naive_utc(read_start)
    mapped_at = naive_utc(identity['mapped_at_dt'])
    by_date: dict[dt.date, list] = {}
    for row in rows:
        day = row.get('close_date')
        if isinstance(day, dt.datetime):
            day = day.date()
        if not isinstance(day, dt.date):
            continue
        if row.get('is_shadow') or row.get('market') != 'us' or row.get('mic') != identity['mic']:
            continue
        by_date.setdefault(day, []).append(row)
    warnings = []
    points = []
    regimes = []
    invalid = 0
    fetched_max = None
    for session in window.sessions:
        close_at = session.regular_closes_at
        if not (window.start <= close_at <= window.end):
            continue
        candidates = by_date.get(session.date, [])
        if not candidates:
            continue
        if len(candidates) > 1:
            invalid += 1
            continue
        row = candidates[0]
        fetched = naive_utc(row.get('fetched_at'))
        if (_price_reason(row) is not None or fetched is None or fetched > read_start
                or fetched < naive_utc(close_at) or naive_utc(close_at) < mapped_at):
            invalid += 1
            continue
        regime = _regime_id(row['source'].strip(), 'close', row['adjustment_basis'].strip())
        if all(r['id'] != regime for r in regimes):
            regimes.append({'id': regime, 'source': row['source'].strip(),
                            'price_basis': 'close', 'adjustment_basis': row['adjustment_basis'].strip()})
        fetched_max = fetched if fetched_max is None or fetched > fetched_max else fetched_max
        # Each daily close is its own hard segment: a line between two of them
        # would draw prices nobody observed across a whole session.
        points.append({'at': iso_z(close_at), 'start': iso_z(session.regular_opens_at),
                       'end': iso_z(close_at), 'value': _finite_positive(row['close']),
                       'provisional': False, 'break_before': bool(points), 'regime': regime,
                       'segment': f'{session.date.isoformat()}|{regime}'})
    if invalid:
        warnings.append(f'price: {invalid} stored daily close(s) in this window were unusable')
    if not points:
        return None, warnings
    if len(regimes) > 1:
        warnings.append('price: stored close source/basis changed inside the window; '
                        'values are not comparable across it')
    return {
        'source': regimes[-1]['source'], 'kind': 'daily_close', 'currency': 'USD',
        'mic': identity['mic'], 'price_basis': 'close',
        'adjustment_basis': regimes[-1]['adjustment_basis'], 'regimes': regimes,
        'received_at': iso_z(fetched_max), 'cache_age_seconds': None,
        'latest_observation_at': points[-1]['at'],
        'stale': (read_start - fetched_max).total_seconds() >= FRESH_SECONDS,
        'fallback': True, 'interval_seconds': None,
        'observations': len(points), 'expected_intervals': None, 'points': points,
    }, warnings


# --- chatter ----------------------------------------------------------------------

def _valid_count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _reddit_family(source: str) -> bool:
    return source == 'reddit' or source.startswith('reddit:')


def chatter_slots(rows, window: Window, *, identity_floor) -> dict:
    """Aligned counts for the window's own slots, from retained source buckets.

    `rows` are mappings with bucket_start (naive UTC), source, mention_count,
    status and source_config_version, already limited to this ticker, the
    selected concrete sources and [window.start, window.end). Returns the
    public slot list plus, per slot, the exact counted (source, bucket, count)
    cells the tone partition must reconcile to.
    """
    rows = list(rows)
    if len(rows) > SOURCE_ROW_LIMIT:
        raise ChartError('read_limit', 503, 'more retained bucket rows than the bounded reader supports')
    if len({row.get('source') for row in rows}) > MAX_SOURCES:
        raise ChartError('read_limit', 503, 'more distinct sources than the bounded reader supports')
    start, end = naive_utc(window.start), naive_utc(window.end)
    floor = naive_utc(identity_floor)
    grouped: dict[tuple[str, dt.datetime], list] = {}
    represented: set[str] = set()
    pre_identity = 0
    off_grid: dict[dt.datetime, int] = {}
    for row in rows:
        when = naive_utc(row.get('bucket_start'))
        source = row.get('source')
        if not isinstance(when, dt.datetime) or not isinstance(source, str):
            continue
        if not (start <= when < end):
            continue
        if floor is not None and when < floor:
            pre_identity += 1
            continue
        if when.second or when.microsecond or when.minute % 15:
            off_grid[when] = off_grid.get(when, 0) + 1
            continue
        represented.add(source)
        grouped.setdefault((source, when), []).append(row)

    cells: dict[tuple[str, dt.datetime], tuple] = {}
    conflicts = 0
    for key, entries in grouped.items():
        variants = {(repr(e.get('mention_count')), e.get('status'), e.get('source_config_version'))
                    for e in entries}
        row = entries[0]
        count = _valid_count(row.get('mention_count'))
        status = row.get('status')
        if len(variants) > 1:
            conflicts += 1
            cells[key] = ('unknown', None, None)
        elif count is None or status not in BUCKET_STATUSES:
            cells[key] = ('unknown', None, None)
        else:
            cells[key] = (status, count, row.get('source_config_version'))

    sources = sorted(represented)
    previous_config: dict[str, object] = {}
    slots = []
    counted_cells = []
    step = dt.timedelta(minutes=window.step_minutes)
    for slot_start, slot_end in slot_bounds(window):
        s_start, s_end = naive_utc(slot_start), naive_utc(slot_end)
        buckets = []
        cursor = s_start
        while cursor < s_end:
            buckets.append(cursor)
            cursor += BUCKET
        partial = buckets[-1] + BUCKET > end
        identity_buckets = [b for b in buckets if floor is None or b >= floor]
        if len(identity_buckets) < len(buckets):
            partial = True
        if any(s_start <= when < s_end for when in off_grid):
            partial = True
        truncated = transition = overlap = False
        total = 0
        any_valid = False
        counted = []
        reddit_by_bucket: dict[dt.datetime, set] = {}
        for source in sources:
            source_total = 0
            source_valid = source_unknown = False
            source_cells = []
            for bucket in identity_buckets:
                cell = cells.get((source, bucket))
                if cell is None:
                    partial = True
                    continue
                status, count, config = cell
                if status == 'unknown':
                    source_unknown = True
                    continue
                if source in previous_config and previous_config[source] != config:
                    transition = True
                previous_config[source] = config
                if status == 'missing':
                    partial = True
                    continue
                if status == 'truncated':
                    truncated = partial = True
                source_total += count
                source_valid = True
                source_cells.append((source, bucket, count))
                if _reddit_family(source):
                    reddit_by_bucket.setdefault(bucket, set()).add(source)
            if source_unknown:
                # A conflicting or malformed bucket makes this source unknown
                # for the slot: excluded, never counted as zero.
                partial = True
                for bucket, members in reddit_by_bucket.items():
                    members.discard(source)
                continue
            if source_valid:
                total += source_total
                any_valid = True
                counted.extend(source_cells)
        for members in reddit_by_bucket.values():
            if 'reddit' in members and any(m != 'reddit' for m in members):
                overlap = True
        count = total if any_valid and not overlap else None
        coverage = 'unknown' if count is None else ('partial' if partial else 'observed')
        slots.append({'start': iso_z(s_start), 'end': iso_z(s_end), 'count': count,
                      'coverage': coverage, 'config_transition': transition,
                      'truncated': truncated, 'overlap_ambiguous': overlap})
        counted_cells.append(counted if count is not None else [])

    warnings = []
    if pre_identity:
        warnings.append(f'chatter: {pre_identity} retained source-bucket row(s) precede the '
                        'company record and are excluded')
    if off_grid:
        warnings.append(f'chatter: {sum(off_grid.values())} retained row(s) off the 15-minute '
                        'grid were excluded; their slots are partial')
    if conflicts:
        warnings.append(f'chatter: {conflicts} source bucket(s) had conflicting duplicate rows '
                        'and are unknown')
    if any(slot['overlap_ambiguous'] for slot in slots):
        warnings.append('chatter: bare reddit and a subreddit source overlap in a slot; '
                        'that slot total is withheld')
    if any(slot['config_transition'] for slot in slots):
        warnings.append('chatter: source configuration changed inside the window; counts '
                        'across the change are descriptive, not comparable')
    return {'step_minutes': window.step_minutes, 'from': iso_z(window.start),
            'to': iso_z(window.end), 'slots': slots, 'represented_sources': sources,
            'counted_cells': counted_cells, 'warnings': warnings,
            'configured_source_coverage': 'unknown'}


def tone_slots(chatter: dict, aggregates, *, retained_from, failure: str | None = None) -> list:
    """Retained recorded-judgment partitions reconciled to the NEW slot totals.

    `aggregates` maps (source, naive bucket_start) to a row with total,
    eligibility_conflicts and the five categories, as the existing chart tone
    aggregate returns them. Evidence older than `retained_from`, missing or
    conflicting is unavailable -- never neutral. `failure` (a timeout,
    overflow or store error) colours every counted slot unavailable while the
    counts stand.
    """
    from .chatter_tone import reconcile_slot

    retained_from = naive_utc(retained_from)
    out = []
    for slot, cells in zip(chatter['slots'], chatter['counted_cells']):
        count = slot['count']
        if count is None:
            out.append(None)
            continue
        if failure is not None:
            out.append(reconcile_slot(total=count, source_bins=[{
                'total': count, 'bullish': 0, 'bearish': 0, 'neutral': 0,
                'unjudged': 0, 'unavailable': count}]))
            continue
        bins = []
        for source, bucket, bucket_count in cells:
            source_bin = {'total': bucket_count, 'bullish': 0, 'bearish': 0,
                          'neutral': 0, 'unjudged': 0, 'unavailable': 0}
            row = aggregates.get((source, bucket)) if bucket >= retained_from else None
            if row is None or _valid_count(_int(row.get('eligibility_conflicts'))) != 0:
                source_bin['unavailable'] = bucket_count
            else:
                source_bin.update({key: _int(row.get(key)) for key in TONE_CATEGORIES})
            bins.append(source_bin)
        out.append(reconcile_slot(total=count, source_bins=bins))
    return out


def _int(value):
    """Driver aggregates arrive as int, Decimal or None."""
    if value is None:
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return -1
    return number if number == value else -1


# --- assembly ---------------------------------------------------------------------

def public_identity(identity: dict) -> dict:
    return {key: identity[key] for key in ('ticker', 'company_id', 'instrument_id', 'mic',
                                           'venue', 'currency', 'provider_symbol',
                                           'mapped_at', 'fingerprint')}


def assemble(*, identity: dict, window: Window, now: dt.datetime, acquisition: dict,
             price: dict | None, chatter: dict, tone: list, warnings: list[str]) -> dict:
    """The version-1 response. Keys are all present, always."""
    if len(chatter['slots']) != len(tone):
        raise ValueError('tone must align with chatter slots')
    if price is not None and len(price['points']) > MAX_PRICE_POINTS:
        raise ChartError('read_limit', 503, 'more price points than the bounded contract supports')
    return {
        'version': VERSION,
        'identity': public_identity(identity),
        'span': window.span,
        'generated_at': iso_z(now),
        'window': {'from': iso_z(window.start), 'to': iso_z(window.end),
                   'timezone': 'America/New_York',
                   'session_dates': [day.isoformat() for day in window.session_dates],
                   'partial': window.partial, 'calendar_basis': 'modeled',
                   'bands': bands(window)},
        'acquisition': {'state': acquisition['state'],
                        'retry_after_seconds': acquisition.get('retry_after_seconds'),
                        'reason': acquisition.get('reason')},
        'price': price,
        'chatter': {'step_minutes': chatter['step_minutes'], 'from': chatter['from'],
                    'to': chatter['to'], 'slots': chatter['slots'],
                    'tone': {'basis': 'recorded-judgments', 'slots': tone},
                    'normal_per_slot': None},
        'warnings': list(warnings),
    }

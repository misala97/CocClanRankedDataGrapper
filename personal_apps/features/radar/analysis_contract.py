"""HA1 US Daily Explore: the pure contract.

Validated ranges and the two independent daily reducers (closes, retained
chatter counts) that the Analysis reader serialises. Nothing here imports the
app, the database, a provider or the board: every input is a bounded list of
plain mappings the reader already fetched, and every output is a dict that
serialises exactly to the SPEC section 4 payload objects.

Three rules this module exists to keep true:

- Missing is not zero. A date with no retained close is `missing`; a source
  with no usable slot in a day has `mentions: null`; an explicit ok zero is an
  observed zero.
- Identity is the current mapping, retrospectively. Rows before the company's
  `first_seen` are marked `identity_unverified`; bucket rows before it are
  excluded row by row. Neither says anything about legal lineage.
- Nothing is inferred. No return, no split, no exchange calendar beyond a
  modeled hint, no pooling across the bare-Reddit/child overlap, no summing
  of mention_z.

Binding: radar-design/HA1-US-DAILY-EXPLORE-SPEC.md sections 4-7.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from decimal import Decimal, InvalidOperation

MAX_DAYS = 7
SLOTS_PER_DAY = 96
SLOT = dt.timedelta(minutes=15)
MAX_SOURCES = 64
#: 7 days x 96 slots x 64 sources; the reader selects one more as a sentinel.
BUCKET_ROW_LIMIT = MAX_DAYS * SLOTS_PER_DAY * MAX_SOURCES
BUCKET_ROW_SENTINEL = BUCKET_ROW_LIMIT + 1
DAILY_ROW_LIMIT = MAX_DAYS
DAILY_ROW_SENTINEL = DAILY_ROW_LIMIT + 1

#: US MICs the rule-based NYSE calendar is allowed to model: exactly the eight
#: listing MICs the Nasdaq directory contract can produce, each confirmed
#: ACTIVE and US in the ISO 10383 register. Anything else -- including
#: Nasdaq's operating MIC `XNAS`, which no listing resolves to -- is
#: `unknown`, never guessed.
KNOWN_US_MICS = frozenset({'ARCX', 'XNMS', 'XNYS', 'XNCM', 'BATS', 'XNGS',
                           'XASE', 'IEXG'})

SOURCE_STATUSES = frozenset({'ok', 'missing', 'truncated'})
USABLE_STATUSES = frozenset({'ok', 'truncated'})
ALLOWED_QUERY_KEYS = frozenset({'instrument_id', 'from', 'to'})
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TICKER = re.compile(r'^[A-Z][A-Z0-9.\-]{0,11}$')


class ContractError(Exception):
    """A request or a bounded read that cannot be answered as asked.

    `code` is the stable public value the transport echoes; `status` is the
    HTTP status the route uses. Messages never carry SQL or credentials.
    """

    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


# --- request ------------------------------------------------------------------

def _pairs(args):
    """Every (key, value) pair, repeated keys included.

    Accepts a werkzeug MultiDict (items(multi=True)), an iterable of pairs,
    or a plain mapping. Repeats are the caller's to reject, so nothing here
    collapses them.
    """
    if hasattr(args, 'items'):
        try:
            return list(args.items(multi=True))
        except TypeError:
            return list(args.items())
    return list(args)


def _fields(args):
    pairs = _pairs(args)
    seen: dict[str, str] = {}
    for key, value in pairs:
        if key not in ALLOWED_QUERY_KEYS:
            raise ContractError('unknown_query', 400,
                                f'unsupported query parameter {key!r}')
        if key in seen:
            raise ContractError('duplicate_query', 400,
                                f'query parameter {key!r} was given more than once')
        seen[key] = value if value is not None else ''
    return seen


def parse_instrument_id(args) -> int:
    fields = _fields(args)
    if 'instrument_id' not in fields:
        raise ContractError('missing_query', 400, 'instrument_id is required')
    return positive_int(fields['instrument_id'], 'instrument_id')


def positive_int(raw, name: str) -> int:
    text = (raw or '').strip() if isinstance(raw, str) else raw
    if isinstance(text, bool) or not re.fullmatch(r'\d{1,18}', str(text) if text is not None else ''):
        raise ContractError('invalid_id', 400, f'{name} must be a positive integer')
    value = int(text)
    if value <= 0:
        raise ContractError('invalid_id', 400, f'{name} must be a positive integer')
    return value


def parse_date(raw, name: str) -> dt.date:
    if not isinstance(raw, str) or not ISO_DATE.match(raw.strip()):
        raise ContractError('invalid_date', 400, f'{name} must be YYYY-MM-DD')
    try:
        return dt.date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ContractError('invalid_date', 400, f'{name} is not a calendar date') from exc


def today_utc(now_utc: dt.datetime) -> dt.date:
    """The UTC calendar date of an aware `now`. Naive datetimes are refused:
    a local-machine date must never decide what "completed" means."""
    if now_utc.tzinfo is None:
        raise ValueError('now_utc must be timezone-aware')
    return now_utc.astimezone(dt.timezone.utc).date()


def default_range(now_utc: dt.datetime) -> tuple[dt.date, dt.date]:
    """The last seven COMPLETED UTC calendar days -- yesterday and the six
    before it -- not the last seven with data."""
    last = today_utc(now_utc) - dt.timedelta(days=1)
    return last - dt.timedelta(days=MAX_DAYS - 1), last


def parse_range(args, now_utc: dt.datetime) -> tuple[dt.date, dt.date]:
    """Validate the company request's query. All three keys are required;
    nothing is defaulted, clamped or shifted towards data."""
    fields = _fields(args)
    for key in ('instrument_id', 'from', 'to'):
        if key not in fields:
            raise ContractError('missing_query', 400, f'{key} is required')
    positive_int(fields['instrument_id'], 'instrument_id')
    start = parse_date(fields['from'], 'from')
    end = parse_date(fields['to'], 'to')
    if end < start:
        raise ContractError('reversed_range', 400, 'from must not be after to')
    if (end - start).days + 1 > MAX_DAYS:
        raise ContractError('range_too_long', 400,
                            f'at most {MAX_DAYS} days may be requested')
    if end > today_utc(now_utc) - dt.timedelta(days=1):
        raise ContractError('range_not_completed', 400,
                            'to must be a completed UTC day (yesterday or earlier)')
    return start, end


def valid_ticker(raw) -> str:
    text = (raw or '').strip().upper() if isinstance(raw, str) else ''
    if not TICKER.match(text):
        raise ContractError('invalid_ticker', 400, 'ticker is not a symbol')
    return text


# --- helpers ------------------------------------------------------------------

def _dates(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def _iso_z(when) -> str | None:
    if when is None:
        return None
    if when.tzinfo is not None:
        when = when.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return when.replace(microsecond=0).isoformat() + 'Z'


def _naive_utc(when):
    if when is None:
        return None
    if when.tzinfo is not None:
        return when.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return when


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_seen_date(first_seen) -> dt.date | None:
    when = _naive_utc(first_seen)
    return when.date() if when is not None else None


def interior_missing(usable_dates, expected_dates):
    """Dates strictly between the first and last usable close where the
    model says the market was open and no usable close exists.

    Set membership, never outer-join row counting: two adjacent closes with
    no interior expected date are an empty list, not one synthetic gap.
    """
    usable = {d for d in usable_dates if d is not None}
    if len(usable) < 2 or expected_dates is None:
        return None
    first, last = min(usable), max(usable)
    return sorted(d for d in expected_dates
                  if d is not None and first < d < last and d not in usable)


def calendar_for(mic: str | None):
    """A modeled hint function for a known US MIC, or the unknown function.

    The existing rule-based NYSE calendar knows weekends and full-day
    holidays. It does not know unscheduled closures or listing-specific
    halts, which is why every answer is `modeled_*` and never `open`.
    """
    if mic in KNOWN_US_MICS:
        from .market_calendars import us

        def modeled(day: dt.date) -> str:
            return 'modeled_open' if us.is_trading_day(day) else 'modeled_closed'
        return modeled

    def unknown(day: dt.date) -> str:
        return 'unknown'
    return unknown


# --- price --------------------------------------------------------------------

def _finite_positive(close) -> float | None:
    if close is None or isinstance(close, bool):
        return None
    try:
        value = float(Decimal(str(close))) if not isinstance(close, float) else close
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _selected(row, instrument, start, end, read_started_at) -> bool:
    """Whether a row is even about the selected instrument's live lane in
    the window. Rows that fail this are EXCLUDED (they say nothing about the
    date); rows that pass but are unusable are `invalid` (they do)."""
    if row.get('is_shadow'):
        return False
    if row.get('market') != instrument['market'] or row.get('mic') != instrument['mic']:
        return False
    day = row.get('close_date')
    if not isinstance(day, dt.date) or isinstance(day, dt.datetime):
        if isinstance(day, dt.datetime):
            day = day.date()
        else:
            return False
    if day < start or day > end:
        return False
    fetched = _naive_utc(row.get('fetched_at'))
    if read_started_at is not None:
        if fetched is None or fetched > _naive_utc(read_started_at):
            return False
    return True


def _price_reason(row) -> str | None:
    problems = []
    if _finite_positive(row.get('close')) is None:
        problems.append('close is not a finite positive number')
    if (row.get('currency') or '') != 'USD':
        problems.append('currency is not USD')
    if _text(row.get('source')) is None:
        problems.append('source is empty')
    if _text(row.get('price_basis')) != 'close':
        problems.append('price_basis is not close')
    if _text(row.get('adjustment_basis')) != 'split':
        problems.append('adjustment_basis is not split')
    return '; '.join(problems) or None


def _regime(instrument, row) -> str:
    return '/'.join(str(part) for part in (
        instrument['market'], instrument['mic'], row.get('currency'),
        _text(row.get('source')), _text(row.get('price_basis')),
        _text(row.get('adjustment_basis'))))


def price_days(rows, instrument, company_first_seen, start, end, calendar,
               read_started_at=None) -> dict:
    """One entry per requested date, independently.

    `rows` are mappings with close_date, close, currency, source,
    price_basis, adjustment_basis, fetched_at, market, mic, is_shadow.
    `calendar(date)` returns modeled_open / modeled_closed / unknown.
    """
    identity_floor = _first_seen_date(company_first_seen)
    by_date: dict[dt.date, list] = {}
    for row in rows:
        if not _selected(row, instrument, start, end, read_started_at):
            continue
        day = row['close_date']
        day = day.date() if isinstance(day, dt.datetime) else day
        by_date.setdefault(day, []).append(row)

    days = []
    warnings: list[str] = []
    usable_dates: set[dt.date] = set()
    expected: set[dt.date] | None = set()
    regimes: set[str] = set()
    unverified = 0
    for day in _dates(start, end):
        hint = calendar(day)
        if hint not in ('modeled_open', 'modeled_closed', 'unknown'):
            hint = 'unknown'
        if hint == 'unknown':
            expected = None
        elif hint == 'modeled_open' and expected is not None:
            expected.add(day)
        entry = {
            'date': day.isoformat(), 'close': None, 'state': 'missing',
            'reason': None, 'source': None, 'price_basis': None,
            'adjustment_basis': None, 'fetched_at': None, 'regime': None,
            'calendar_hint': hint,
        }
        candidates = by_date.get(day, [])
        if candidates:
            row = candidates[0]
            entry.update({
                'source': _text(row.get('source')),
                'price_basis': _text(row.get('price_basis')),
                'adjustment_basis': _text(row.get('adjustment_basis')),
                'fetched_at': _iso_z(_naive_utc(row.get('fetched_at'))),
            })
            if len(candidates) > 1:
                entry['state'] = 'invalid'
                entry['reason'] = 'more than one retained live row for this date'
            elif identity_floor is not None and day < identity_floor:
                entry['state'] = 'identity_unverified'
                entry['reason'] = ('close_date precedes the company record; '
                                   'identity on that date is not verified')
                unverified += 1
            else:
                reason = _price_reason(row)
                if reason:
                    entry['state'] = 'invalid'
                    entry['reason'] = reason
                else:
                    entry['state'] = 'observed'
                    entry['close'] = _finite_positive(row.get('close'))
                    entry['regime'] = _regime(instrument, row)
                    regimes.add(entry['regime'])
                    usable_dates.add(day)
                    if hint == 'modeled_closed':
                        warnings.append(
                            f'price:{day.isoformat()}: a close is stored on a '
                            'modeled_closed day; the modeled calendar or the '
                            'stored trading date may be wrong')
        elif identity_floor is not None and day < identity_floor:
            entry['state'] = 'identity_unverified'
            entry['reason'] = 'date precedes the company record'
        days.append(entry)

    if unverified:
        warnings.append(
            f'price: {unverified} retained close(s) precede the company record '
            'and are shown as identity_unverified; first_seen is a conservative '
            'boundary, not a verified lineage')
    invalid = sum(1 for p in days if p['state'] == 'invalid')
    if invalid:
        warnings.append(f'price: {invalid} retained row(s) are unusable and shown as invalid')
    if len(regimes) > 1:
        warnings.append('price: source/basis regime changed inside the window; '
                        'segments are not connected across the boundary and '
                        'values are not comparable across it')
    if usable_dates:
        warnings.append('price: the split stamp is a declared basis, not a verified '
                        'adjustment vintage; same-source closes may have been restated')
    interior = interior_missing(usable_dates, expected)
    return {
        'resolution': 'daily_close',
        'days': days,
        'usable_count': len(usable_dates),
        'first_usable': min(usable_dates).isoformat() if usable_dates else None,
        'last_usable': max(usable_dates).isoformat() if usable_dates else None,
        'official_completeness': 'unknown',
        'interior_modeled_missing': (
            [d.isoformat() for d in interior] if interior is not None else None),
        'regime_changed': len(regimes) > 1,
        'warnings': warnings,
    }


def regime_runs(days) -> list[list[str]]:
    """Consecutive observed dates sharing one regime, as date lists. A run
    breaks at any non-observed date and at any regime change; A->B->A is
    three runs. The renderer connects only within a run."""
    runs: list[list[str]] = []
    current: list[str] = []
    regime = None
    for day in days:
        if day['state'] != 'observed':
            if current:
                runs.append(current)
            current, regime = [], None
            continue
        if current and day['regime'] != regime:
            runs.append(current)
            current = []
        current.append(day['date'])
        regime = day['regime']
    if current:
        runs.append(current)
    return runs


# --- chatter ------------------------------------------------------------------

def _slot_index(when: dt.datetime, day: dt.date) -> int | None:
    """Which of the 96 aligned quarter-hours of `day` `when` is, or None
    when it is not aligned."""
    if when.date() != day:
        return None
    if when.second or when.microsecond or when.minute % 15:
        return None
    return when.hour * 4 + when.minute // 15


def _valid_count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def chatter_days(rows, start, end, company_first_seen) -> dict:
    """One entry per requested UTC day, from the selected ticker's retained
    per-source buckets in [start 00:00Z, end+1 00:00Z).

    `rows` are mappings with bucket_start (naive UTC), source, mention_count,
    status, source_config_version. Every stored concrete source with retained
    evidence at or after the company record anywhere in the window is
    represented on every day; nothing is expanded from today's configuration
    and nothing is borrowed from other tickers.

    Units, because two different things are counted here:

    - The per-source `*_slots` fields partition the day's 96 aligned
      quarter-hours: ok + truncated + missing + invalid + absent == 96.
    - `excluded_rows` (per source and per day) and `identity_excluded_slots`
      (per day; the name is kept for compatibility) count SOURCE-BUCKET ROWS,
      not time slots. An excluded row sits outside the partition: it is off
      the 15-minute grid or repeats a slot's key. An identity-excluded row
      precedes the company record. Three sources before first_seen for 12
      hours are 144 such rows, not 48 slots.
    """
    rows = list(rows)
    if len(rows) > BUCKET_ROW_LIMIT:
        raise ContractError('analysis_limit', 503,
                            'the retained bucket read exceeded the bounded row limit')
    # The resource bound is on what was fetched, before any exclusion.
    fetched_sources = {str(row.get('source')) for row in rows if row.get('source') is not None}
    if len(fetched_sources) > MAX_SOURCES:
        raise ContractError('analysis_limit', 503,
                            'more distinct sources than the bounded reader supports')

    window_start = dt.datetime.combine(start, dt.time())
    window_end = dt.datetime.combine(end + dt.timedelta(days=1), dt.time())
    identity_floor = _naive_utc(company_first_seen)
    warnings: list[str] = []
    identity_excluded_total = 0
    first_seen_at = None
    last_seen_at = None

    # (day, source) -> aligned slot index -> list of rows. Rows off the grid
    # never enter a slot; they are counted per (day, source) instead.
    grid: dict[tuple[dt.date, str], dict] = {}
    unaligned: dict[tuple[dt.date, str], int] = {}
    identity_excluded: dict[dt.date, int] = {}
    represented: set[str] = set()
    identity_sources: set[str] = set()
    for row in rows:
        when = _naive_utc(row.get('bucket_start'))
        source = row.get('source')
        if when is None or source is None:
            continue
        if when < window_start or when >= window_end:
            continue
        day = when.date()
        if identity_floor is not None and when < identity_floor:
            identity_excluded[day] = identity_excluded.get(day, 0) + 1
            identity_excluded_total += 1
            identity_sources.add(str(source))
            continue
        represented.add(str(source))
        slot = _slot_index(when, day)
        if slot is None:
            unaligned[(day, str(source))] = unaligned.get((day, str(source)), 0) + 1
            continue
        grid.setdefault((day, str(source)), {}).setdefault(slot, []).append(row)
        first_seen_at = when if first_seen_at is None or when < first_seen_at else first_seen_at
        last_seen_at = when if last_seen_at is None or when > last_seen_at else last_seen_at

    # A source whose only rows in the window precede the company record says
    # nothing about the identity this page shows: it is not in the
    # represented denominator, but its exclusion is still disclosed.
    sources = sorted(represented)
    pre_identity_only = sorted(identity_sources - represented)

    days = []
    previous_configs: dict[str, list] = {}
    any_config_boundary = False
    excluded_total = 0
    for day in _dates(start, end):
        per_source = []
        overlap = False
        reddit_slots: dict[str, set[int]] = {}
        day_transition = False
        day_excluded = 0
        for source in sources:
            cell = grid.get((day, source), {})
            ok = truncated = missing = invalid = 0
            excluded = unaligned.get((day, source), 0)
            total = 0
            usable_slots: set[int] = set()
            configs: set = set()
            for slot, entries in cell.items():
                # A repeated key is one slot; the extra rows sit outside it.
                excluded += len(entries) - 1
                row = entries[0]
                count = _valid_count(row.get('mention_count'))
                status = row.get('status')
                if count is None or status not in SOURCE_STATUSES:
                    invalid += 1
                    continue
                configs.add(row.get('source_config_version'))
                if status == 'ok':
                    ok += 1
                    total += count
                    usable_slots.add(slot)
                elif status == 'truncated':
                    truncated += 1
                    total += count
                    usable_slots.add(slot)
                else:
                    missing += 1
            # Absent = aligned slots with no retained row at all.
            absent = SLOTS_PER_DAY - len(cell)
            day_excluded += excluded
            config_list = sorted(configs, key=lambda c: (c is not None, str(c)))
            transition = len(configs) > 1
            if usable_slots:
                mentions = total
                full = (ok == SLOTS_PER_DAY and truncated == 0 and missing == 0
                        and invalid == 0 and absent == 0 and excluded == 0
                        and len(configs) == 1 and None not in configs)
                coverage = 'observed_full_day' if full else 'partial'
            else:
                mentions = None
                coverage = 'unavailable'
            if source == 'reddit' or source.startswith('reddit:'):
                reddit_slots[source] = usable_slots
            if configs:
                before = previous_configs.get(source)
                if before is not None and before != config_list:
                    day_transition = True
                    any_config_boundary = True
                previous_configs[source] = config_list
            if transition:
                day_transition = True
                any_config_boundary = True
            per_source.append({
                'source': source, 'mentions': mentions,
                'ok_slots': ok, 'truncated_slots': truncated,
                'missing_slots': missing, 'absent_slots': absent,
                'invalid_slots': invalid, 'expected_slots': SLOTS_PER_DAY,
                'excluded_rows': excluded,
                'config_versions': config_list, 'transition': transition,
                'coverage': coverage,
            })
        # The bare root and any child family observed in one slot cannot be
        # pooled: nobody knows whether they are the same or different posts.
        bare = reddit_slots.get('reddit', set())
        if bare:
            for source, slots in reddit_slots.items():
                if source != 'reddit' and slots & bare:
                    overlap = True
                    break
        usable_sources = [s for s in per_source if s['mentions'] is not None]
        if not usable_sources:
            mentions, coverage = None, 'unavailable'
        elif overlap:
            mentions, coverage = None, 'partial'
        else:
            mentions = sum(s['mentions'] for s in usable_sources)
            coverage = ('observed'
                        if all(s['coverage'] == 'observed_full_day' for s in per_source)
                        else 'partial')
        identity_rows = identity_excluded.get(day, 0)
        if (identity_rows or day_excluded) and coverage == 'observed':
            coverage = 'partial'
        excluded_total += day_excluded
        days.append({
            'date': day.isoformat(), 'mentions': mentions, 'coverage': coverage,
            'configured_source_coverage': 'unknown', 'sources': per_source,
            'config_transition': day_transition, 'overlap_ambiguous': overlap,
            # Source-bucket rows, not time slots (see the docstring).
            'identity_excluded_slots': identity_rows,
            'excluded_rows': day_excluded,
        })

    if identity_excluded_total:
        warnings.append(
            f'chatter: {identity_excluded_total} retained source-bucket row(s) '
            'precede the company record and are excluded; identity on those '
            'rows is not verified')
    if pre_identity_only:
        warnings.append(
            f'chatter: {len(pre_identity_only)} source(s) have retained rows in '
            'this window only before the company record and are not counted '
            'among the represented sources: ' + ', '.join(pre_identity_only))
    if excluded_total:
        warnings.append(
            f'chatter: {excluded_total} retained source-bucket row(s) are off '
            'the 15-minute grid or repeat a slot and are excluded from counts; '
            'the days they fall on are not complete')
    if any_config_boundary:
        warnings.append('chatter: source config changed inside or between the '
                        'requested days; counts across the boundary are '
                        'descriptive, not comparable activity')
    if any(day['overlap_ambiguous'] for day in days):
        warnings.append('chatter: bare reddit and a subreddit source overlap in '
                        'one slot; the pooled day count is withheld and the '
                        'per-source breakdown stands on its own')
    return {
        'resolution': 'daily_counts',
        'input_minutes': 15,
        'source_scope': 'all_retained_for_ticker',
        'days': days,
        'first_observed': _iso_z(first_seen_at),
        'last_observed': _iso_z(last_seen_at),
        'warnings': warnings,
    }

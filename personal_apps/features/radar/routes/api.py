"""JSON for the leaderboard surface."""
import dataclasses
import datetime as dt
import threading

from flask import jsonify, request

from auth import current_user, login_required

from .. import board as board_mod
from .. import detail as detail_mod
from .. import detail_panel, llm_sentiment, market_data, phrasing, spend
from .. import search as search_mod
from .. import watch
from ..config import DEFAULT_SEGMENT, REDDIT_SUBS, SOURCES, source_root
from ..market_calendars import session_bounds, session_state
from ._blueprint import radar_bp

# `small` is the discover group's pre-2026-08-31 name, accepted for
# bookmarked URLs; config.SEGMENT_GROUPS resolves both to the same segments.
SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo', 'fund',
            'discover', 'small')
WINDOWS = (1, 4, 12, 24)
VENUE_FLOORS = (1, 2)
MAX_LIMIT = 100
# Every root plus every configured subreddit. See parse_query.
MAX_SOURCES = len(SOURCES) + len(REDDIT_SUBS)


@dataclasses.dataclass
class Query:
    """A validated query string.

    A dataclass rather than a tuple: five fields unpacked positionally in two
    call sites, three of them ints, is one transposition away from silently
    swapping limit and min_venues with nothing to complain about.
    """
    sources: list
    # Several, and a UNION -- picking a second chip asks to see more. Empty
    # is 'no filter', which is how the surface asks for All.
    segments: list
    window: int
    limit: int
    min_venues: int
    # Omission means the live session -- see default_market. The API remains
    # strict for any value that is supplied, so a typo cannot silently return
    # a different market.
    market: str = 'de'
    # None is the default two-tier ranking; otherwise one of board.SORT_KEYS.
    sort: str = None
    direction: str = 'desc'


def _decimal_or_none(value):
    return float(value) if value is not None else None


def _iso_z(value):
    """Serialize a UTC instant explicitly, preserving UTC as the wire format."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value.isoformat() + 'Z'


def _chart_sessions(chart, market, span, mic=None):
    """What kind of time each stretch of the chart is, in UTC intervals.

    A chart may represent a real German quote or an explicit US fallback.  Its
    bands must follow the quote's actual market calendar, not the selected
    surface's market label.

    Three kinds since the single-lane chart (2026-08-30): premarket and
    afterhours as before, plus `closed` -- nights, weekends and holidays --
    so a missing stretch of price line inside an UNSHADED band reads as what
    it is, an outage, and inside a gray band as what THAT is, a shut market.
    The daily 1M span gets its closed days too (weekends are the reader's
    orientation marks at that zoom); the longer daily spans stay bare, where
    a hundred weekend stripes would be noise rather than context.
    """
    slots = max(len(chart.closes), len(chart.chatter))
    if not slots:
        return []

    if chart.step_minutes >= 1440:
        return _daily_closed_days(chart, market, slots, span, mic=mic)

    if not isinstance(chart.start, dt.datetime):
        return []

    # The hourly week works like the month: whole non-trading DAYS wash
    # gray and nothing else. Night-by-night slats plus a merged weekend
    # monolith were most of what made the week view unreadable; the daily
    # rhythm carries the orientation on its own.
    if chart.step_minutes >= 60:
        return _closed_day_intervals(chart.start, slots * chart.step_minutes,
                                     market, mic=mic)

    start = chart.start
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    else:
        start = start.astimezone(dt.timezone.utc)
    end = start + dt.timedelta(minutes=slots * chart.step_minutes)

    intervals = []
    # Every stretch outside [opens_at, closes_at) of a trading day is closed.
    # Collected as trading windows first, then complemented, so a holiday
    # falls out as closed without being special-cased.
    windows = []
    day = start.date() - dt.timedelta(days=1)
    last_day = end.date() + dt.timedelta(days=1)
    while day <= last_day:
        # Noon UTC unambiguously selects this local US or German calendar day;
        # the extra day at either side covers a session crossing a UTC date.
        probe = dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc)
        bounds = session_bounds(market, probe, mic=mic)
        if session_state(market, bounds.regular_opens_at,
                          mic=mic) == 'regular':
            windows.append((bounds.opens_at, bounds.closes_at))
            for kind, left, right in (
                ('premarket', bounds.opens_at, bounds.premarket_closes_at),
                ('afterhours', bounds.regular_closes_at, bounds.closes_at),
            ):
                clipped_start = max(start, left)
                clipped_end = min(end, right)
                if clipped_start < clipped_end:
                    intervals.append({
                        'start': _iso_z(clipped_start),
                        'end': _iso_z(clipped_end),
                        'kind': kind,
                    })
        day += dt.timedelta(days=1)

    cursor = start
    for opens_at, closes_at in sorted(windows):
        if opens_at > cursor:
            left, right = cursor, min(opens_at, end)
            if left < right:
                intervals.append({'start': _iso_z(left), 'end': _iso_z(right),
                                  'kind': 'closed'})
        cursor = max(cursor, min(closes_at, end))
    if cursor < end:
        intervals.append({'start': _iso_z(cursor), 'end': _iso_z(end),
                          'kind': 'closed'})
    return intervals


def _closed_day_intervals(start, minutes, market, mic=None):
    """Runs of non-trading local calendar days inside an intraday window,
    as UTC intervals clipped to it.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(minutes=minutes)

    intervals = []
    run_start = None
    day = start.date() - dt.timedelta(days=1)
    last_day = end.date() + dt.timedelta(days=1)
    while day <= last_day + dt.timedelta(days=1):
        probe = dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc)
        bounds = session_bounds(market, probe, mic=mic)
        trading = (day <= last_day
                   and session_state(market, bounds.regular_opens_at,
                          mic=mic) == 'regular')
        if not trading and day <= last_day:
            if run_start is None:
                run_start = day
        elif run_start is not None:
            left = max(start, dt.datetime.combine(
                run_start, dt.time.min, tzinfo=dt.timezone.utc))
            right = min(end, dt.datetime.combine(
                day, dt.time.min, tzinfo=dt.timezone.utc))
            if left < right:
                intervals.append({'start': _iso_z(left), 'end': _iso_z(right),
                                  'kind': 'closed'})
            run_start = None
        day += dt.timedelta(days=1)
    return intervals


def _daily_closed_days(chart, market, slots, span, mic=None):
    """Runs of non-trading calendar days on the 1M chart, nothing elsewhere."""
    if span != '1M' or not isinstance(chart.start, dt.date):
        return []

    intervals = []
    run_start = None
    for offset in range(slots + 1):
        day = chart.start + dt.timedelta(days=offset)
        probe = dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc)
        bounds = session_bounds(market, probe, mic=mic)
        trading = (offset < slots
                   and session_state(market, bounds.regular_opens_at,
                          mic=mic) == 'regular')
        if not trading and offset < slots:
            if run_start is None:
                run_start = day
        elif run_start is not None:
            intervals.append({
                'start': dt.datetime.combine(run_start, dt.time.min)
                    .isoformat() + 'Z',
                'end': dt.datetime.combine(day, dt.time.min).isoformat() + 'Z',
                'kind': 'closed',
            })
            run_start = None
    return intervals


def _quote(view):
    """The selected market quote shared by board rows and detail identity."""
    return {
        'market': view.market,
        'venue': view.venue,
        'mic': view.mic,
        'currency': view.currency,
        'price': _decimal_or_none(view.price),
        'regular_move': _decimal_or_none(view.regular_move),
        'extended_move': _decimal_or_none(view.extended_move),
        'session': view.session,
        'quality': view.quality,
        'age_seconds': view.age_seconds,
        'quoted_at': _iso_z(view.quote_ts),
        # These are decided from quote quality and tape history server-side.
        # A client only receives the selected row, so it must not reinvent the
        # eligibility decision from a session label.
        'tape_status': view.tape_status,
        'score_eligible': view.score_eligible,
        'score_term': view.score_term,
        'is_fallback': view.is_fallback,
        # Market-data v2 provenance: decided in QuoteView, never re-derived
        # here (spec 10).
        'source': view.source,
        'price_basis': view.price_basis,
        'bid': _decimal_or_none(view.bid),
        'ask': _decimal_or_none(view.ask),
    }


class BadQuery(ValueError):
    """A query parameter the caller sent that cannot be honoured."""


def default_market(now=None):
    """The market an unqualified request opens on: whichever session is live.

    Michi, 2026-09-01, reversing the DE-always default of 2026-08-30. US only
    when the US session is regular AND the German one is not; DE otherwise.
    The home market wins the 15:30-17:30 overlap, and with nothing live there
    is no price move to diverge from on either venue, so the board opens on
    the one the reader trades.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    # Callers pass the codebase's naive-UTC `now`; the calendars want it aware.
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    us_live = session_state('us', now) == 'regular'
    de_live = session_state('de', now) == 'regular'
    return 'us' if us_live and not de_live else 'de'


def parse_query(args, now=None):
    """(sources, segment, window, limit) or raise BadQuery.

    Every parameter is validated rather than coerced. Silently ignoring an
    unknown source would return the default board under a selection the viewer
    never made, which is worse than an error.
    """
    market = args.get('market') or default_market(now)
    if market not in {'us', 'de'}:
        raise BadQuery('unknown market')

    raw_sources = args.get('sources')
    if raw_sources:
        selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
        # A prefixed name is valid when its ROOT is a known source: the UI
        # offers `reddit` as one chip, and a link may name one subreddit.
        if any(source_root(s) not in SOURCES for s in selected):
            raise BadQuery('unknown source')
        # Bounded, because rooting the membership check unbounded it. Before
        # the subreddit split every accepted name had to be one of three, so
        # the list could hold at most three; now `reddit:<anything>` passes,
        # and each accepted entry lands in six or more IN (...) clauses
        # against a ~300k-row partitioned table. MAX_SOURCES is the largest
        # selection that can name something real -- every root plus every
        # configured subreddit.
        if len(selected) > MAX_SOURCES:
            raise BadQuery('too many sources')
    else:
        selected = list(SOURCES)

    # Comma-separated since 2026-08-25, and `?segment=small` still parses --
    # widening the parameter must not invalidate every bookmarked link.
    # `?segment=` with an empty value stays how the surface asks for All.
    raw_segments = args.get('segment', DEFAULT_SEGMENT)
    segments = [name.strip() for name in raw_segments.split(',') if name.strip()]
    # One bad name rejects the whole selection rather than being dropped:
    # answering with a board under a selection the viewer never made is the
    # thing every parameter here is validated rather than coerced to avoid.
    if any(name not in SEGMENTS for name in segments):
        raise BadQuery('unknown segment')

    try:
        window = int(args.get('window', 4))
    except ValueError:
        raise BadQuery('bad window')
    if window not in WINDOWS:
        raise BadQuery('unsupported window')

    try:
        limit = min(int(args.get('limit', 50)), MAX_LIMIT)
    except ValueError:
        raise BadQuery('bad limit')

    try:
        min_venues = int(args.get('venues', 1))
    except ValueError:
        raise BadQuery('bad venues')
    if min_venues not in VENUE_FLOORS:
        raise BadQuery('unsupported venues')

    # Validated, never coerced -- the rule stated on the segment block above.
    # A sort the server silently ignored would draw the default ranking under
    # a header claiming it was sorted, which is the same lie in a new place.
    sort = args.get('sort') or None
    if sort is not None and sort not in board_mod.SORT_KEYS:
        raise BadQuery('unknown sort')
    direction = args.get('dir', 'desc')
    if direction not in ('asc', 'desc'):
        raise BadQuery('unknown sort direction')

    return Query(sources=selected, segments=segments, window=window,
                 limit=limit, min_venues=min_venues, market=market,
                 sort=sort, direction=direction)


def serialize(board):
    """The board as the shape the island consumes.

    Times go out as ISO 8601 with an explicit Z. Every datetime in this
    codebase is naive UTC by convention, and a naive timestamp on the wire is
    one the browser renders in local time without being asked to.
    """
    return {
        'generated_at': board.generated_at.isoformat() + 'Z',
        'market': board.market,
        'display_timezone': board.display_timezone,
        'market_venue': board.market_venue,
        'next_boundary_label': board.next_boundary_label,
        'next_boundary_at': _iso_z(board.next_boundary_at),
        'sources': board.sources,
        'all_sources': list(SOURCES),
        'segments': board.segments,
        'session': board.session,
        'min_venues': board.min_venues,
        # Echoed so the island can seed its Selection from the server's own
        # parsed answer rather than re-parsing the URL (BoardPage.tsx).
        'sort': board.sort,
        'dir': board.direction,
        'venue_counts': board.venue_counts,
        'window_hours': board.window_hours,
        'segment_counts': board.segment_counts,
        'excluded': board.excluded,
        # Spend, never a balance. There is no balance endpoint in the Claude
        # API at all -- the Cost API reports what was spent, needs a separate
        # Admin API key, and is documented as unavailable for individual
        # accounts. Counted here from the token usage the responses carry.
        'spend': spend.summary(),
        # Judgment-pipeline health (spec §10.4): backlog size and p95 age,
        # plus the review tier's unique-demand meters and the live
        # over-ceiling gauge. Visibility, not control -- nothing here
        # changes what the passes do.
        'sentiment_ops': llm_sentiment.ops_summary(),
        # Market-data v2 health: the cached database-only summary; the
        # detail endpoint deliberately does not repeat it (spec §11).
        'market_data_ops': market_data.ops_summary(board.generated_at),
        'triplet_hours': list(board_mod.TRIPLET_HOURS),
        'series_hours': board_mod.SERIES_HOURS,
        'lead_count': board_mod.LEAD_COUNT,
        'rows': [_row(entry) for entry in board.rows],
    }


def _row(entry):
    r = entry.rank
    return {
        'ticker': r.ticker,
        'name': r.name,
        'segment': r.segment,
        'divergence': r.divergence,
        'mention_z': r.mention_z,
        'mentions': r.mentions,
        'expected': r.expected,
        # The number behind the `ratio` clause. Sent so the row can draw a bar
        # of how far above its own normal it is without the client deciding
        # for itself when a baseline is too thin to divide by -- that guard
        # lives once, in phrasing.py, beside the wording it also governs.
        'ratio': phrasing.ratio_value(r.mentions, r.expected),
        'authors': r.authors,
        'text_ratio': r.text_ratio,
        'sources': r.sources,
        'price': _decimal_or_none(r.price),
        'price_move': _decimal_or_none(r.price_move),
        'direction': r.direction,
        'price_status': r.price_status,
        'quote': _quote(r.quote),
        'baseline_days': r.baseline_days,
        'marks': r.marks,
        # False only on a watched row the floor would have dropped; the
        # island renders it quiet and its warn clause says why.
        'eligible': r.eligible,
        # `count: null` is a measured gap, not a quiet hour -- see board.py.
        'series': [{'hour': p.hour.isoformat() + 'Z', 'count': p.count}
                   for p in entry.series],
        # Same hour grid as `series`; null is an hour nobody priced. The
        # chart-row draws both on one time axis.
        'price_series': [_decimal_or_none(p) for p in entry.price_series],
        'normal_per_hour': _decimal_or_none(entry.normal_per_hour),
        'triplet': {str(hours): value for hours, value in entry.triplet.items()},
        'tone': {'bullish': entry.tone.bullish,
                 'neutral': entry.tone.neutral,
                 'bearish': entry.tone.bearish},
        # Why this row is here, in words. The client styles by `kind` and
        # never parses `text` -- see phrasing.py.
        'clauses': [{'kind': c.kind, 'text': c.text} for c in entry.clauses],
    }


# The board build, memoised per selection for a minute.
#
# Viewer-invariant, which is coverage.py's rule and the coc_stats bulk-standing
# cache's: every account sees identical rows, so what does not depend on who
# is asking can be shared. Measured 2026-09-01, after the N+1s of 2026-08-24
# were gone and the query count was flat at 24: the build is ~0.6s and it is
# the whole of the page's server time. Ingest advances the buckets every 15
# minutes, so a 60-second memo is fresh in the sense that matters, and the
# cached board keeps its own generated_at -- the head's stamp says when the
# board was BUILT, which stays true.
BOARD_TTL = dt.timedelta(seconds=60)
board_cache: dict = {}
_board_lock = threading.Lock()


def _build_board(query, now):
    # The sort is part of the KEY, not just of the build: it changes which
    # rows the board holds, so a key without it would serve the unsorted
    # board to the next reader who asked for a sorted one -- inside the
    # same minute, silently, and only sometimes.
    key = (tuple(query.sources), tuple(query.segments), query.window,
           query.limit, query.min_venues, query.market,
           query.sort, query.direction)
    with _board_lock:
        hit = board_cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    board = board_mod.build(query.sources, now,
                            window_hours=query.window,
                            segments=query.segments, limit=query.limit,
                            min_venues=query.min_venues, market=query.market,
                            sort=query.sort, direction=query.direction)
    with _board_lock:
        board_cache[key] = (now + BOARD_TTL, board)
        # A handful of distinct selections per minute; past that it is old
        # keys aging out, and the dict must not grow with every filter ever
        # tried.
        if len(board_cache) > 64:
            for stale in [k for k, (expires, _) in board_cache.items()
                          if expires <= now]:
                del board_cache[stale]
    return board


def build_payload(args, now=None, user_id=None):
    """Validated query -> serialized board. Shared by the page and the API.

    `user_id` adds the caller's watching list and its rows on top of the
    memoised, viewer-invariant board -- a handful of tickers, uncached
    because it is per account.
    """
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    query = parse_query(args, now=now)
    # The SELECTION, unexpanded. board.build hands it to each query, and the
    # queries expand differently: a scored read may not see the pre-split root
    # `reddit` rows and a raw-count read must (config.expand_sources vs
    # expand_sources_for_history). Expanding once here would take that choice
    # away from them -- and expanding for history afterwards is impossible,
    # since the root is no longer in the list to recognise.
    board = _build_board(query, now)
    # ROOTED, because the payload's `sources` is what lights the chips and
    # there is one chip per root. `?sources=reddit:wallstreetbets` filtered
    # the board to that subreddit above and still lights the Reddit chip
    # here; without the rooting it matched no chip at all and the control
    # rendered every chip off -- a state it otherwise forbids, and one whose
    # first click silently discarded the concrete selection.
    board.sources = sorted({source_root(s) for s in query.sources})
    payload = serialize(board)
    watching = watch.tickers_for(user_id) if user_id is not None else []
    payload['watching'] = watching
    payload['watch_rows'] = [_row(entry) for entry in board_mod.build_pinned_rows(
        watching, query.sources, now, window_hours=query.window,
        market=query.market)] if watching else []
    return payload


@radar_bp.route('/api/board')
@login_required
def board():
    """Ranked rows for the selected sources, segment and window."""
    try:
        return jsonify(build_payload(request.args, user_id=current_user().id))
    except BadQuery as exc:
        return jsonify({'error': str(exc)}), 400


@radar_bp.route('/api/watch/<ticker>', methods=['PUT'])
@login_required
def watch_put(ticker):
    """Mark a ticker for the caller. Idempotent; answers the whole list so
    the client never merges."""
    try:
        return jsonify({'watching': watch.add(current_user().id, ticker)})
    except watch.BadTicker:
        return jsonify({'error': 'bad ticker'}), 400


@radar_bp.route('/api/watch/<ticker>', methods=['DELETE'])
@login_required
def watch_delete(ticker):
    """Unmark a ticker for the caller. Unmarking the unmarked is a 200."""
    try:
        return jsonify({'watching': watch.remove(current_user().id, ticker)})
    except watch.BadTicker:
        return jsonify({'error': 'bad ticker'}), 400


@radar_bp.route('/api/search')
@login_required
def search():
    """Symbol-or-name search over the universe, eight matches at most."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    matches = search_mod.search_universe(request.args.get('q', ''), now.date())
    if not matches:
        return jsonify({'matches': []})
    watching = set(watch.tickers_for(current_user().id))
    return jsonify({'matches': [
        {'ticker': m.ticker, 'name': m.name, 'exchange': m.exchange,
         'segment': m.segment, 'watching': m.ticker in watching}
        for m in matches
    ]})


def serialize_detail(d):
    """One ticker's panel.

    Five zones, in the order the reader meets them: who this is, what we
    found, what the stock has done, how the chatter breaks down, and what
    people actually said.
    """
    b = d.breakdown
    return {
        'market': d.market,
        'display_timezone': 'Europe/Berlin',
        'identity': {
            'ticker': d.ticker,
            'name': d.name,
            'exchange': d.exchange,
            'segment': d.segment,
            'market_cap': _decimal_or_none(d.market_cap),
            'ipo_date': d.ipo_date.isoformat() if d.ipo_date else None,
            'price': _decimal_or_none(d.price),
            'price_move': _decimal_or_none(d.price_move),
            'price_status': d.price_status,
            'session': d.session,
            'quote': _quote(d.quote),
        },
        'read': [{'kind': c.kind, 'text': c.text}
                 for c in phrasing.read_clauses(
                     d, d.mentions, d.expected, b.voices, d.session,
                     baseline_days=d.baseline_days,
                     venues=len(b.venues))],
        'chart': {
            # ISO with an explicit Z, and a DATETIME for the intraday spans:
            # a slot fifteen minutes wide cannot be placed by a date alone.
            'from': d.chart.start.isoformat() + (
                'Z' if isinstance(d.chart.start, dt.datetime) else 'T00:00:00Z'),
            # How wide one slot is. The renderer draws evenly spaced slots and
            # cannot tell minutes from days without being told.
            'step_minutes': d.chart.step_minutes,
            'span': d.span,
            'closes': [_decimal_or_none(c) for c in d.chart.closes],
            'normal_per_slot': _decimal_or_none(d.chart.normal_per_slot),
            # null where nobody was watching, never a zero.
            'chatter': d.chart.chatter,
            'watched_from': (
                _iso_z(d.chart.watched_from)
                if isinstance(d.chart.watched_from, dt.datetime)
                else (d.chart.watched_from.isoformat()
                      if d.chart.watched_from else None)),
            'sessions': _chart_sessions(d.chart, d.quote.market, d.span,
                                        mic=d.quote.mic),
            # Where this line came from. The axis reads `currency` from
            # here, never from the quote: they differ exactly when the
            # basis is a converted foreign listing, which is the case the
            # reader most needs told (spec §1/§3).
            'currency': d.chart.currency,
            'basis_venue': d.chart.basis_venue,
            'converted_from': d.chart.converted_from,
            'priced_from': d.chart.priced_from,
        },
        'breakdown': {
            'venues': [{'source': v.source, 'mentions': v.mentions,
                        'voices': v.voices} for v in b.venues],
            'bullish': b.bullish,
            'neutral': b.neutral,
            'bearish': b.bearish,
            # How often the word list and the model read the same post the
            # opposite way. Both scores exist so this is answerable, and a
            # disagreement is the sarcasm the lexicon cannot see.
            'disagreements': b.disagreements,
            'top_author_share': b.top_author_share,
            'top_two_share': b.top_two_share,
            'peak_hour': b.peak_hour.isoformat() + 'Z' if b.peak_hour else None,
            'peak_count': b.peak_count,
            'first_seen': b.first_seen.isoformat() if b.first_seen else None,
            'mentions': b.mentions,
            'voices': b.voices,
        },
        'posts': [{
            'source': p.source,
            'author': p.author,
            'channel': p.channel,
            'created': p.created_utc.isoformat() + 'Z',
            'title': p.title,
            'body': p.body,
            'url': p.url,
            # The same §7.1 read the tallies use, per post, so the list
            # and the counts above it can never disagree.
            'tone': tone,
            # Who decided that tone: the model, or the local wording score.
            'judged_by': judged_by,
            # ...and WHICH model, when it was one. Resolved server-side from
            # the recorded id, because the component cannot know and used to
            # print a literal 'Claude' for every model-decided tone.
            'judged_label': judged_label,
        } for p, tone, judged_by, judged_label in d.posts],
        'post_total': d.post_total,
    }


@radar_bp.route('/api/ticker/<ticker>')
@login_required
def ticker_detail(ticker):
    """One ticker, in depth.

    Its own endpoint rather than a field on the board payload: three years is
    ~780 closes, so carrying it per row would have a twenty-row board ship
    sixteen thousand numbers to draw twenty sparklines.
    """
    span = request.args.get('span', detail_mod.DEFAULT_SPAN)
    if not detail_mod.known_span(span):
        return jsonify({'error': 'unknown span'}), 400
    try:
        query = parse_query(request.args)
    except BadQuery as exc:
        return jsonify({'error': str(exc)}), 400

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    try:
        built = detail_panel.build(ticker.upper(), query.sources, now,
                                    window_hours=query.window, span=span,
                                    market=query.market)
    except detail_mod.UnknownTicker:
        return jsonify({'error': 'unknown ticker'}), 404
    return jsonify(serialize_detail(built))

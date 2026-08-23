"""JSON for the leaderboard surface."""
import dataclasses
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import board as board_mod
from ..config import DEFAULT_SEGMENT, SOURCES
from ._blueprint import radar_bp

SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo', 'small')
WINDOWS = (1, 4, 24)
VENUE_FLOORS = (1, 2)
MAX_LIMIT = 100


@dataclasses.dataclass
class Query:
    """A validated query string.

    A dataclass rather than a tuple: five fields unpacked positionally in two
    call sites, three of them ints, is one transposition away from silently
    swapping limit and min_venues with nothing to complain about.
    """
    sources: list
    segment: str | None
    window: int
    limit: int
    min_venues: int


def _decimal_or_none(value):
    return float(value) if value is not None else None


class BadQuery(ValueError):
    """A query parameter the caller sent that cannot be honoured."""


def parse_query(args):
    """(sources, segment, window, limit) or raise BadQuery.

    Every parameter is validated rather than coerced. Silently ignoring an
    unknown source would return the default board under a selection the viewer
    never made, which is worse than an error.
    """
    raw_sources = args.get('sources')
    if raw_sources:
        selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
        if any(s not in SOURCES for s in selected):
            raise BadQuery('unknown source')
    else:
        selected = list(SOURCES)

    # `?segment=` with an empty value is how the surface asks for All, and
    # it has to stay reachable now that the default is not None.
    segment = args.get('segment', DEFAULT_SEGMENT) or None
    if segment is not None and segment not in SEGMENTS:
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

    return Query(sources=selected, segment=segment, window=window,
                 limit=limit, min_venues=min_venues)


def serialize(board):
    """The board as the shape the island consumes.

    Times go out as ISO 8601 with an explicit Z. Every datetime in this
    codebase is naive UTC by convention, and a naive timestamp on the wire is
    one the browser renders in local time without being asked to.
    """
    return {
        'generated_at': board.generated_at.isoformat() + 'Z',
        'sources': board.sources,
        'all_sources': list(SOURCES),
        'segment': board.segment,
        'session': board.session,
        'min_venues': board.min_venues,
        'venue_counts': board.venue_counts,
        'window_hours': board.window_hours,
        'segment_counts': board.segment_counts,
        'excluded': board.excluded,
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
        'authors': r.authors,
        'text_ratio': r.text_ratio,
        'sources': r.sources,
        'price': _decimal_or_none(r.price),
        'price_move': _decimal_or_none(r.price_move),
        'direction': r.direction,
        'price_status': r.price_status,
        'baseline_days': r.baseline_days,
        'marks': r.marks,
        # `count: null` is a measured gap, not a quiet hour -- see board.py.
        'series': [{'hour': p.hour.isoformat() + 'Z', 'count': p.count}
                   for p in entry.series],
        'triplet': {str(hours): value for hours, value in entry.triplet.items()},
        'tone': {'bullish': entry.tone.bullish,
                 'neutral': entry.tone.neutral,
                 'bearish': entry.tone.bearish},
        # Why this row is here, in words. The client styles by `kind` and
        # never parses `text` -- see phrasing.py.
        'clauses': [{'kind': c.kind, 'text': c.text} for c in entry.clauses],
    }


def build_payload(args, now=None):
    """Validated query -> serialized board. Shared by the page and the API."""
    query = parse_query(args)
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    board = board_mod.build(query.sources, now, window_hours=query.window,
                            segment=query.segment, limit=query.limit,
                            min_venues=query.min_venues)
    return serialize(board)


@radar_bp.route('/api/board')
@login_required
def board():
    """Ranked rows for the selected sources, segment and window."""
    try:
        return jsonify(build_payload(request.args))
    except BadQuery as exc:
        return jsonify({'error': str(exc)}), 400

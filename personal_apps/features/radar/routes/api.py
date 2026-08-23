"""JSON for the leaderboard surface."""
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import board as board_mod
from ..config import SOURCES
from ._blueprint import radar_bp

SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo')
WINDOWS = (1, 4, 24)
MAX_LIMIT = 100


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

    segment = args.get('segment') or None
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

    return selected, segment, window, limit


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
        'window_hours': board.window_hours,
        'segment_counts': board.segment_counts,
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
        'price_series': [{'at': at.isoformat() + 'Z',
                          'price': _decimal_or_none(price)}
                         for at, price in entry.price_series],
        'chart': _chart(entry.chart),
    }


def build_payload(args, now=None):
    """Validated query -> serialized board. Shared by the page and the API."""
    selected, segment, window, limit = parse_query(args)
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    board = board_mod.build(selected, now, window_hours=window,
                            segment=segment, limit=limit)
    return serialize(board)


@radar_bp.route('/api/board')
@login_required
def board():
    """Ranked rows for the selected sources, segment and window."""
    try:
        return jsonify(build_payload(request.args))
    except BadQuery as exc:
        return jsonify({'error': str(exc)}), 400

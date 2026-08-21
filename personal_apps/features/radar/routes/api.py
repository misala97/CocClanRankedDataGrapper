"""JSON for the leaderboard surface."""
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import leaderboard
from ..config import SOURCES
from ._blueprint import radar_bp

SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo')
WINDOWS = (1, 4, 24)
MAX_LIMIT = 100


def _decimal_or_none(value):
    return float(value) if value is not None else None


@radar_bp.route('/api/board')
@login_required
def board():
    """Ranked rows for the selected sources, segment and window.

    Every parameter is validated rather than coerced. Silently ignoring an
    unknown source would return the default board under a selection the viewer
    never made, which is worse than an error.
    """
    raw_sources = request.args.get('sources')
    if raw_sources:
        selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
        if any(s not in SOURCES for s in selected):
            return jsonify({'error': 'unknown source'}), 400
    else:
        selected = list(SOURCES)

    segment = request.args.get('segment') or None
    if segment is not None and segment not in SEGMENTS:
        return jsonify({'error': 'unknown segment'}), 400

    try:
        window = int(request.args.get('window', 4))
    except ValueError:
        return jsonify({'error': 'bad window'}), 400
    if window not in WINDOWS:
        return jsonify({'error': 'unsupported window'}), 400

    try:
        limit = min(int(request.args.get('limit', 50)), MAX_LIMIT)
    except ValueError:
        return jsonify({'error': 'bad limit'}), 400

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows = leaderboard.build_rows(selected, now, window_hours=window,
                                  segment=segment, limit=limit)

    return jsonify({
        'generated_at': now.isoformat() + 'Z',
        'sources': selected,
        'segment': segment,
        'window_hours': window,
        'rows': [{
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
        } for r in rows],
    })

"""Two read-only operational endpoints: what was recorded, and how it is going.

Both are reads and nothing else. There is no retry, no restart, no retrain and
no provider request behind either of them -- everything they answer is either
already in the database or already computed by the summaries the board page
reads. That is deliberate: an operations surface that can act is a surface that
can be made to act by accident.

`/api/activity` is for everyone who can read the board, because recorded fetch
activity is not personal. `/api/ops` is admin-only, and it answers 403 to a
signed-in non-admin rather than pretending not to exist: the endpoint is no
secret, and "not allowed" is the honest answer to a real reader asking for
someone else's page. That distinction matters on the client, where a 403 must
not be mistaken for an expired session -- reloading fixes one and not the other.

The admin gate here is about who gets an operations PAGE, not about keeping
these figures secret: /api/board already serves `spend`, `sentiment_ops` and
`market_data_ops` to any signed-in reader. Removing them from that payload is
a compatibility decision the spec explicitly defers, so this endpoint is the
new front door and not a new wall.
"""
import datetime as dt
import re

from flask import jsonify, request

from auth import admin_required, login_required

from .. import activity, llm_sentiment, market_data, observations, spend
from ._blueprint import radar_bp


def _utcnow() -> dt.datetime:
    """Naive UTC, the convention every datetime in this codebase is stored in."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


@radar_bp.route('/api/activity')
@login_required
def activity_read():
    """Recorded fetch activity by Berlin calendar day.

    The window is validated rather than clamped. Answering `days=2` with a
    week would describe a period the reader never asked about, under a number
    they chose -- the same objection every other radar parameter is validated
    for.
    """
    raw = request.args.get('days', '7')
    # Digits only, so `7 ` is rejected rather than quietly read as 7. A module
    # whose argument is that it does not reinterpret the reader's number
    # should not begin by reinterpreting it.
    if not re.fullmatch(r'\d+', raw) or int(raw) not in activity.ALLOWED_DAYS:
        return jsonify({'error': 'unsupported days'}), 400
    days = int(raw)
    return jsonify(activity.summary(_utcnow(), days))


@radar_bp.route('/api/ops')
@admin_required
def ops():
    """The operational summaries the application already computes.

    Nothing new is fetched and nothing is exposed that the board payload does
    not already carry -- this endpoint exists so the hub can show them without
    building a board, not so it can show more.
    """
    now = _utcnow()
    return jsonify({
        'generated_at': activity.iso_z(now),
        'spend': spend.summary(),
        'sentiment': llm_sentiment.ops_summary(),
        'market_data': market_data.ops_summary(now),
        # A database read. How old the archive is, or null when nothing has
        # been captured -- which is the state until capture is switched on.
        'capture': {
            'latest_observed_at': activity.iso_z(
                observations.latest_observed_at()),
        },
    })

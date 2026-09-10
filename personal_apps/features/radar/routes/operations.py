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

import sqlalchemy as sa
from flask import jsonify, request

from auth import admin_required, login_required
from extensions import db

from .. import activity, board_namespace, board_store, llm_sentiment
from .. import market_data, observations, spend
from . import api
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
        'board_results': _board_results(now),
    })


def _board_results(now):
    """Whether the shared board cache is working, and who is filling it.

    Two reads and a derivation: the generation's control row says whether a
    producer has spoken and how its last job went, and one aggregate over the
    result rows says how much work is outstanding. Nothing here builds, claims
    or enqueues -- this endpoint answers questions and takes no actions, which
    is the rule the whole module is written to.

    Both failures below are answered rather than raised, because this page is
    what an operator opens WHEN something is wrong and a 500 would take away
    the other four summaries with it. The tables can be absent because the flag
    was turned on before the migration ran, which is operator error and exactly
    the error the page has to be able to report; and the revision can be
    unresolvable on a checkout that ships without one, which makes a namespace
    impossible to name at all.
    """
    enabled = api.shared_results_enabled()
    try:
        described = board_namespace.describe()
    except board_namespace.ConfigError:
        return {'namespace': None, 'enabled': enabled,
                'error': 'no build revision'}

    ns = described['namespace']
    try:
        control = board_store.health(db.engine, ns)
        queue = board_store.queue_summary(db.engine, ns, now)
    except sa.exc.ProgrammingError:
        return {'namespace': ns, 'enabled': enabled, 'error': 'table missing'}

    return {
        'namespace': ns,
        'enabled': enabled,
        # All four are null until a producer has run against this generation,
        # which is itself the answer to "is anything building these boards".
        'producer': {
            'owner': control.get('producer_owner'),
            'seen_at': activity.iso_z(control.get('producer_seen_at')),
            'success_at': activity.iso_z(control.get('producer_success_at')),
            'error': control.get('producer_error'),
        },
        # Against the number of standing boards this build DERIVES, not the
        # number of warm rows the table happens to hold -- a ninth standing
        # selection must read as one short, never as ready.
        'warm_ready': queue['warm_ready'],
        'warm_total': board_store.limits().warm_limit,
        'queue': {name: queue[name]
                  for name in ('pending', 'building', 'failed_due')},
        'on_demand_rows': queue['on_demand_rows'],
    }

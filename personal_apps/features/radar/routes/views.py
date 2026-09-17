"""The board page itself.

A thin Jinja shell that mounts one React island, the same arrangement every
gym page uses. The first board is embedded in the document rather than fetched
after mount: the payload is the page, and a spinner on arrival for data the
server already had in hand is a self-inflicted wait.

Control changes after that go through /radar/api/board, which returns the
identical shape -- so the island has exactly one payload type to render and no
separate "initial" code path to keep in sync.
"""
from flask import abort, render_template, request

from auth import current_user, is_admin, login_required

from ._blueprint import radar_bp
from .api import BadQuery, build_payload, require_us_market
from .. import config
from ..config import DEFAULT_SEGMENT


def _refuse_unsupported_market(args):
    """A visible 400 for an explicit market other than US.

    Checked before the friendly fallback below, which would otherwise turn a
    bookmarked link to a retired market into the US board without saying so.
    An absent or empty market is the US board, as it is for the API, and
    every value of a repeated market is checked the same way the API does.
    """
    try:
        require_us_market(args)
    except BadQuery:
        abort(400, description=(
            'unsupported market: Radar shows US listings only. Remove the '
            'market parameter from the address to open the board.'))


def _hub_args(args):
    """Map the hub's visible Discover choice to the existing warm key."""
    mapped = args.copy()
    # `t` is old-board selection state. The hub translates it in the browser,
    # where a fragment can take precedence; the board API must never receive
    # it or reject otherwise valid legacy filters.
    mapped.pop('t', None)
    if mapped.get('segment') == 'discover':
        mapped['segment'] = DEFAULT_SEGMENT
    return mapped


@radar_bp.route('/legacy/')
@login_required
def board_page():
    """A bad query string falls back to the default board rather than 400.

    The API is strict because a client sending nonsense has a bug worth
    surfacing. A person editing the address bar is not a bug, and answering a
    typo with a JSON error page would be an odd way to run a dashboard. An
    explicit unsupported market is the exception: it names a board Radar no
    longer has, so it is refused visibly rather than answered with another.
    """
    _refuse_unsupported_market(request.args)
    user_id = current_user().id
    try:
        payload = build_payload(request.args, user_id=user_id)
    except BadQuery:
        payload = build_payload({}, user_id=user_id)
    query = request.query_string.decode('utf-8')
    return render_template('radar/board.html', payload=payload,
                           hub_url=f'/radar/{"?" + query if query else ""}')


@radar_bp.route('/')
@radar_bp.route('/hub/')
@login_required
def hub_page():
    """The hub at the root, with /hub/ retained as a compatibility alias.

    `is_admin` travels with the board so the shell can decide whether to render
    an Administration link on first paint rather than after a probe request.
    It is a rendering hint: /radar/api/ops enforces authorization itself and
    does not trust it.

    Same BadQuery fallback as the legacy board page: a person editing the address bar
    is not a bug, and answering a typo with an error page is an odd way to run
    a dashboard. The same explicit-market exception applies.
    """
    _refuse_unsupported_market(request.args)
    user_id = current_user().id
    try:
        payload = build_payload(_hub_args(request.args), user_id=user_id)
    except BadQuery:
        payload = build_payload({}, user_id=user_id)
    # The selected-price chart flag is a rendering hint as well: the chart
    # endpoint refuses by itself when it is off, and the provider switch is
    # never sent to the browser at all.
    return render_template('radar/hub.html',
                           shell={'board': payload, 'is_admin': is_admin(),
                                  'selected_price_charts_enabled':
                                      config.selected_price_charts_enabled()})

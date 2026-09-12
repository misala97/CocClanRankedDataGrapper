"""The board page itself.

A thin Jinja shell that mounts one React island, the same arrangement every
gym page uses. The first board is embedded in the document rather than fetched
after mount: the payload is the page, and a spinner on arrival for data the
server already had in hand is a self-inflicted wait.

Control changes after that go through /radar/api/board, which returns the
identical shape -- so the island has exactly one payload type to render and no
separate "initial" code path to keep in sync.
"""
from flask import render_template, request

from auth import current_user, is_admin, login_required

from ._blueprint import radar_bp
from .api import BadQuery, build_payload
from ..config import DEFAULT_SEGMENT


def _hub_args(args):
    """Map the hub's visible Discover choice to the existing warm key."""
    mapped = args.copy()
    if mapped.get('segment') == 'discover':
        mapped['segment'] = DEFAULT_SEGMENT
    return mapped


@radar_bp.route('/')
@login_required
def board_page():
    """A bad query string falls back to the default board rather than 400.

    The API is strict because a client sending nonsense has a bug worth
    surfacing. A person editing the address bar is not a bug, and answering a
    typo with a JSON error page would be an odd way to run a dashboard.
    """
    user_id = current_user().id
    try:
        payload = build_payload(request.args, user_id=user_id)
    except BadQuery:
        payload = build_payload({}, user_id=user_id)
    return render_template('radar/board.html', payload=payload)


@radar_bp.route('/hub/')
@login_required
def hub_page():
    """The opt-in hub, offered alongside the board rather than in place of it.

    /radar/ above is unchanged and stays the way back. Promoting this route is
    a separate release decision, so nothing here may change what that one does.

    `is_admin` travels with the board so the shell can decide whether to render
    an Administration link on first paint rather than after a probe request.
    It is a rendering hint: /radar/api/ops enforces authorization itself and
    does not trust it.

    Same BadQuery fallback as the board page: a person editing the address bar
    is not a bug, and answering a typo with an error page is an odd way to run
    a dashboard.
    """
    user_id = current_user().id
    try:
        payload = build_payload(_hub_args(request.args), user_id=user_id)
    except BadQuery:
        payload = build_payload({}, user_id=user_id)
    return render_template('radar/hub.html',
                           shell={'board': payload, 'is_admin': is_admin()})

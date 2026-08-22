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

from auth import login_required

from ._blueprint import radar_bp
from .api import BadQuery, build_payload


@radar_bp.route('/')
@login_required
def board_page():
    """A bad query string falls back to the default board rather than 400.

    The API is strict because a client sending nonsense has a bug worth
    surfacing. A person editing the address bar is not a bug, and answering a
    typo with a JSON error page would be an odd way to run a dashboard.
    """
    try:
        payload = build_payload(request.args)
    except BadQuery:
        payload = build_payload({})
    return render_template('radar/board.html', payload=payload)

"""Mutations answer in JSON when asked, and redirect otherwise.

The redirect half is not a formality: session_detail.html still posts plain
forms and refreshBody still parses the HTML that comes back. Breaking that
while adding the JSON path would take the live workout screen down.
"""
import datetime as dt

import pytest

from conftest import _admin_id


JSON = {'Accept': 'application/json'}
# What a browser actually sends when a <form> is submitted. The */* at the end
# is why the negotiation cannot test accept_json alone -- it makes accept_json
# true for this header too.
FORM = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}


def test_a_form_post_still_redirects(client, live_session):
    """The path the current page uses. If this breaks, the live workout
    screen breaks."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=FORM)
    assert response.status_code in (302, 303)


def test_a_json_request_gets_the_session_payload(client, live_session):
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON)
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    body = response.get_json()
    assert body['session']['id'] == live_session['session']
    assert 'visible_exercises' in body


def test_the_payload_reflects_the_mutation(client, live_session):
    """The point of returning it: the client needs the post-mutation state,
    not the state it already had."""
    before = client.get(
        f"/gym/session/{live_session['session']}/detail.json").get_json()
    assert before['sets_done'] == 1

    after = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON).get_json()
    assert after['sets_done'] == 2


def test_a_bare_fetch_does_not_get_json(client, live_session):
    """fetch() with no Accept header sends */*, which accepts HTML too. The
    island has to opt in explicitly, and this pins that it must."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers={'Accept': '*/*'})
    assert response.status_code in (302, 303)

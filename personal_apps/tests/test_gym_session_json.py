"""The live-workout JSON endpoint.

It must agree with the page, which is why both go through _live_data. The
breadth test below is the one that matters: step 1 shipped a real crash past
a green suite because every test sampled the first record, and whichever row
sorts first is not representative of an unfinished session, a deload, a
shared one, or an empty one.
"""
import datetime as dt

import pytest

from conftest import _admin_id, acting_as


def test_returns_the_payload_shape(client, live_session):
    session_id = live_session['session']
    response = client.get(f'/gym/session/{session_id}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) >= {
        'session', 'visible_exercises', 'live_id', 'sets_done', 'sets_total',
        'resting', 'record_set_ids', 'exercises', 'session_is_shared',
    }
    assert body['session']['id'] == session_id


def test_agrees_with_the_page(client, live_session):
    """Both go through _live_data, so the live exercise cannot differ."""
    session_id = live_session['session']
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import owned_session

    with flask_app.app_context():
        with acting_as(_admin_id()):
            direct = _session_payload(owned_session(session_id))

    from_endpoint = client.get(f'/gym/session/{session_id}/detail.json').get_json()
    assert from_endpoint['live_id'] == direct.live_id
    assert from_endpoint['sets_total'] == direct.sets_total


def test_every_unfinished_session_builds_a_valid_payload():
    """Breadth, not a sample."""
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import my_sessions, owned_session
    from models import WorkoutSession

    failures = []
    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions()
                   .filter(WorkoutSession.finished_at.is_(None)).all()]
            for session_id in ids:
                try:
                    _session_payload(owned_session(session_id))
                except Exception as exc:
                    failures.append(f'{session_id}: {type(exc).__name__}: {exc}')
    assert not failures, 'payload failed for:\n' + '\n'.join(failures)


def test_every_session_page_still_renders(client):
    """Finished and unfinished both -- session_detail serves two pages and
    only one of them was restructured."""
    from app import app as flask_app
    from features.gym.scope import my_sessions

    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions().all()]
            assert ids, 'the dev database needs sessions'

    bad = [(i, client.get(f'/gym/session/{i}').status_code) for i in ids]
    assert all(status == 200 for _, status in bad), \
        f'non-200 responses: {[p for p in bad if p[1] != 200]}'


def test_int_keyed_dicts_reach_the_client_as_strings(client, live_session):
    """suggestions and stagnation_counts are keyed by SessionExercise.id.
    Pinned end-to-end, not just at the schema, because this is the detail the
    React port will trip over."""
    session_id = live_session['session']
    body = client.get(f'/gym/session/{session_id}/detail.json').get_json()
    assert all(isinstance(key, str) for key in body['suggestions'])
    assert all(isinstance(key, str) for key in body['stagnation_counts'])


def test_requires_a_login(anon_client, live_session):
    session_id = live_session['session']
    response = anon_client.get(f'/gym/session/{session_id}/detail.json')
    assert response.status_code in (302, 401, 403)

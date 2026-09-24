"""Crafted query strings and bodies get an answer, not a 500.

Walkthrough 2026-09-23, G-135: `/gym/export?ids=²` and a 5000-digit id
crashed int(); the export's id list had no cap; three redirects to the debrief
passed the whole query string to url_for, so `?session_id=` collided with its
own keyword and `?_scheme=` rewrote the redirect; and a JSON array posted to
reorder reached `.get` on a list.

Runs against the real local development database; the fixtures clean up.
"""
import pytest

from app import app as flask_app

JSON = {'Accept': 'application/json'}


# -- the export's id list ----------------------------------------------------

@pytest.mark.parametrize('ids', [
    '%C2%B2',            # '²': isdigit() is true, int() refuses it
    '9' * 5000,          # past Python's digit limit for int()
    '1,,2, ,x,-3,4.5',   # the ordinary junk, skipped as before
], ids=['superscript', 'huge', 'junk'])
def test_an_export_of_ids_that_are_not_ids_is_an_empty_export(client, ids):
    response = client.get(f'/gym/export?ids={ids}')
    assert response.status_code == 200
    assert response.headers['Content-Disposition'].startswith('attachment')


def test_an_arabic_indic_digit_is_not_an_id(client, temp_finished_session):
    """'٣' is a decimal digit to Python, and int() reads it as 3. An id in the
    URL is ASCII; anything else must not quietly select a workout."""
    from features.gym.routes.reports import _export_ids
    with flask_app.test_request_context():
        assert _export_ids('٣') == []
        assert _export_ids('12,12, 7') == [12, 7]


def test_an_export_of_more_workouts_than_the_cap_is_refused_with_a_reason(client):
    from features.gym.routes.reports import MAX_EXPORT_IDS
    ids = ','.join(str(n) for n in range(1, MAX_EXPORT_IDS + 2))
    response = client.get(f'/gym/export?ids={ids}', headers=JSON)
    assert response.status_code == 400
    assert str(MAX_EXPORT_IDS) in response.get_json()['error']


# -- redirects to the debrief carry ?just_finished and nothing else ----------

def _set_id(se_id):
    from models import SessionSet
    with flask_app.app_context():
        return SessionSet.query.filter_by(session_exercise_id=se_id).first().id


def test_the_summary_redirect_ignores_a_session_id_in_the_query(client, temp_finished_session):
    session_id, _, _ = temp_finished_session
    response = client.get(f'/gym/session/{session_id}/summary?session_id=1&just_finished=1')
    assert response.status_code == 302
    assert response.headers['Location'] == f'/gym/session/{session_id}?just_finished=1'


def test_the_summary_redirect_cannot_be_turned_absolute(client, temp_finished_session):
    session_id, _, _ = temp_finished_session
    response = client.get(f'/gym/session/{session_id}/summary?_scheme=https&_external=1')
    assert response.status_code == 302
    assert response.headers['Location'] == f'/gym/session/{session_id}'


def test_a_set_correction_keeps_just_finished_and_drops_the_rest(client, temp_finished_session):
    session_id, se_id, _ = temp_finished_session
    response = client.post(
        f'/gym/set/{_set_id(se_id)}/update?session_id=1&just_finished=1&_anchor=x',
        data={'weight': '50', 'reps': '8'})
    assert response.status_code == 302
    assert response.headers['Location'] == f'/gym/session/{session_id}?just_finished=1'


def test_marking_a_deload_ignores_a_session_id_in_the_query(client, temp_finished_session):
    session_id, _, _ = temp_finished_session
    response = client.post(f'/gym/session/{session_id}/deload?session_id=1',
                           data={'on': '1', 'pct': '70'})
    assert response.status_code == 302
    assert response.headers['Location'] == f'/gym/session/{session_id}'


# -- reorder bodies of the wrong shape ---------------------------------------

@pytest.mark.parametrize('body', [[1, 2], {'order': 5}, {'order': 'abc'}, 'order'],
                         ids=['array', 'number order', 'string order', 'string'])
def test_a_reorder_body_of_the_wrong_shape_reorders_nothing(client, live_session, body):
    from extensions import db
    from models import SessionExercise
    response = client.post(f"/gym/session/{live_session['session']}/exercises/reorder",
                           json=body, headers=JSON)
    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(SessionExercise, live_session['se']).position == 1

"""A finished workout's shape is closed; its values stay correctable.

Walkthrough 2026-09-23, G-090: the refusal hung on the live screen's
X-Gym-Surface header alone, so any caller that left it out could add, replace,
skip, remove and reorder exercises, set rests and skip rests on a finished
workout. A replace hid two logged sets from the debrief while the stats still
counted them. Structure edits are now refused whoever asks; the debrief's own
corrections (set values, ticks, notes, bodyweight, deload, add and delete a
set) go through as before. None of the requests here carry the header.
"""
import pytest

from app import app as flask_app
from conftest import list_exercise

JSON = {'Accept': 'application/json'}


def _finished_rows(ids):
    from extensions import db
    from models import SessionExercise, WorkoutSession
    session_id, se_id, _ = ids
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        se = db.session.get(SessionExercise, se_id)
        return {
            'exercises': SessionExercise.query.filter_by(session_id=session_id).count(),
            'rest': se.rest_seconds, 'skipped': se.skipped, 'position': se.position,
            'resting': session_.resting_set_id,
        }


def _other_exercise_id():
    with flask_app.app_context():
        return list_exercise().id


STRUCTURE_EDITS = [
    ('add exercise', lambda s, se: (f'/gym/session/{s}/exercises/add',
                                    {'exercise_id': _other_exercise_id()})),
    ('replace', lambda s, se: (f'/gym/session-exercise/{se}/replace',
                               {'exercise_id': _other_exercise_id()})),
    ('rest', lambda s, se: (f'/gym/session-exercise/{se}/rest', {'rest_seconds': '90'})),
    ('remove exercise', lambda s, se: (f'/gym/session-exercise/{se}/delete', {})),
    ('skip', lambda s, se: (f'/gym/session-exercise/{se}/skip', {})),
    ('reorder', lambda s, se: (f'/gym/session/{s}/exercises/reorder', {'order': str(se)})),
    ('rest skip', lambda s, se: (f'/gym/session/{s}/rest/skip', {})),
]


@pytest.mark.parametrize('name,request_for', STRUCTURE_EDITS, ids=[e[0] for e in STRUCTURE_EDITS])
def test_a_structure_edit_to_a_finished_workout_is_refused_whoever_asks(
        client, temp_finished_session, name, request_for):
    session_id, se_id, _ = temp_finished_session
    before = _finished_rows(temp_finished_session)
    url, data = request_for(session_id, se_id)
    response = client.post(url, data=data, headers=JSON)
    assert response.status_code == 409, name
    assert response.get_json()['finished'] is True
    assert _finished_rows(temp_finished_session) == before, name


def test_a_form_post_of_a_structure_edit_goes_back_to_the_debrief(client, temp_finished_session):
    session_id, se_id, _ = temp_finished_session
    response = client.post(f'/gym/session-exercise/{se_id}/skip')
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/session/{session_id}')
    assert _finished_rows(temp_finished_session)['skipped'] is False


def test_the_debriefs_own_corrections_still_go_through(client, temp_finished_session):
    from extensions import db
    from models import SessionSet, WorkoutSession
    session_id, se_id, _ = temp_finished_session
    with flask_app.app_context():
        set_id = SessionSet.query.filter_by(session_exercise_id=se_id).one().id

    for url, data in (
            (f'/gym/set/{set_id}/update', {'weight': '52.5', 'reps': '8'}),
            (f'/gym/sessions/{session_id}/meta', {'bodyweight_kg': '80', 'notes': 'ok'}),
            (f'/gym/session-exercises/{se_id}/meta', {'notes': 'Knie', 'pain': 'on'}),
            (f'/gym/session/{session_id}/deload', {'on': '1', 'pct': '70'}),
            (f'/gym/session-exercise/{se_id}/sets/add', {'weight': '50', 'reps': '6'}),
            (f'/gym/set/{set_id}/toggle_complete', {'completed': '0'}),
    ):
        assert client.post(url, data=data, headers=JSON).status_code == 200, url

    with flask_app.app_context():
        assert db.session.get(SessionSet, set_id).weight == 52.5
        assert db.session.get(WorkoutSession, session_id).notes == 'ok'
        assert SessionSet.query.filter_by(session_exercise_id=se_id).count() == 2


def test_a_tick_on_a_finished_workout_gets_no_stamp_of_the_correction_time(
        client, temp_finished_session):
    """It was lifted at some unknown point during the workout. A stamp of
    "now" read as a set hours after the others -- gym_add_set leaves the
    debrief's sets unstamped for the same reason."""
    from extensions import db
    from models import SessionSet
    _, se_id, _ = temp_finished_session
    with flask_app.app_context():
        set_id = SessionSet.query.filter_by(session_exercise_id=se_id).one().id
    toggle = f'/gym/set/{set_id}/toggle_complete'
    assert client.post(toggle, data={'completed': '0'}, headers=JSON).status_code == 200
    assert client.post(toggle, data={'completed': '1'}, headers=JSON).status_code == 200
    with flask_app.app_context():
        row = db.session.get(SessionSet, set_id)
        assert row.completed is True
        assert row.completed_at is None


def test_a_duplicate_done_does_not_restamp_a_logged_set(client, live_session):
    import datetime as dt
    from extensions import db
    from models import SessionSet
    stamp = dt.datetime(2026, 9, 20, 18, 0, 0)
    with flask_app.app_context():
        db.session.get(SessionSet, live_session['done_set']).completed_at = stamp
        db.session.commit()
    response = client.post(f"/gym/set/{live_session['done_set']}/toggle_complete",
                           data={'completed': '1'}, headers=JSON)
    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(SessionSet, live_session['done_set']).completed_at == stamp

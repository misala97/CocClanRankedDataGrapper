"""Bodyweight, notes and the pain flag: everything a workout learns to
record about itself beyond the sets."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import Exercise, WorkoutSession, SessionExercise, SessionSet
from conftest import _admin_id


@pytest.fixture()
def temp_session():
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Session Fields', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Test Session', user_id=_admin_id(),
                                 started_at=dt.datetime.utcnow())
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.commit()
        ids = (session.id, se.id, exercise.id)
    yield ids
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, ids[0])
        if session is not None:
            db.session.delete(session)
        exercise = db.session.get(Exercise, ids[2])
        if exercise is not None:
            db.session.delete(exercise)
        db.session.commit()


def test_new_session_has_no_bodyweight_or_notes(temp_session):
    session_id, se_id, _ = temp_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg is None
        assert session.notes is None
        se = db.session.get(SessionExercise, se_id)
        assert se.notes is None
        assert se.pain is False


def test_session_fields_round_trip(temp_session):
    session_id, se_id, _ = temp_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        session.bodyweight_kg = 96.8
        session.notes = 'nach 8h Schicht'
        se = db.session.get(SessionExercise, se_id)
        se.notes = 'linke Schulter zwickt'
        se.pain = True
        db.session.commit()
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg == 96.8
        assert session.notes == 'nach 8h Schicht'
        se = db.session.get(SessionExercise, se_id)
        assert se.notes == 'linke Schulter zwickt'
        assert se.pain is True


def test_session_meta_route_saves_bodyweight_and_notes(client, temp_session):
    session_id, _, _ = temp_session
    response = client.post(f'/gym/sessions/{session_id}/meta', data={
        'bodyweight_kg': '96,8',
        'notes': 'nach 8h Schicht',
    })
    assert response.status_code == 302
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg == 96.8, 'a German decimal comma is accepted'
        assert session.notes == 'nach 8h Schicht'


def test_blank_bodyweight_clears_it(client, temp_session):
    session_id, _, _ = temp_session
    client.post(f'/gym/sessions/{session_id}/meta', data={'bodyweight_kg': '96.8'})
    client.post(f'/gym/sessions/{session_id}/meta', data={'bodyweight_kg': ''})
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg is None


def test_exercise_meta_route_saves_note_and_pain(client, temp_session):
    _, se_id, _ = temp_session
    response = client.post(f'/gym/session-exercises/{se_id}/meta', data={
        'notes': 'linke Schulter zwickt',
        'pain': 'on',
    })
    assert response.status_code == 302
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.notes == 'linke Schulter zwickt'
        assert se.pain is True


def test_unchecked_pain_clears_the_flag(client, temp_session):
    _, se_id, _ = temp_session
    client.post(f'/gym/session-exercises/{se_id}/meta', data={'pain': 'on'})
    client.post(f'/gym/session-exercises/{se_id}/meta', data={'notes': ''})
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.pain is False


@pytest.fixture()
def temp_finished_session():
    """Same shape as temp_session, but FINISHED and with one completed set --
    session_detail() hands a finished session to session_finished.html, and
    that template only lists an exercise that has at least one completed set
    (see routes.py's reported_session_exercises filter)."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Finished Session Fields', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Test Finished Session', user_id=_admin_id(),
                                 started_at=dt.datetime.utcnow() - dt.timedelta(hours=1),
                                 finished_at=dt.datetime.utcnow())
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        se.sets = [SessionSet(position=1, weight=50.0, reps=8, completed=True)]
        db.session.add(se)
        db.session.commit()
        ids = (session.id, se.id, exercise.id)
    yield ids
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, ids[0])
        if session is not None:
            db.session.delete(session)
        exercise = db.session.get(Exercise, ids[2])
        if exercise is not None:
            db.session.delete(exercise)
        db.session.commit()


def test_meta_routes_persist_against_a_finished_session(client, temp_finished_session):
    """Finding 1: bodyweight, session note, exercise note and the pain flag
    must stay editable after "Workout beenden" -- forgetting to log one
    before finishing made it unrecordable forever. owned_session() and
    owned_session_exercise() carry no finished-check, so both routes already
    accepted this write; session_finished.html just never exposed a form to
    send it from."""
    session_id, se_id, _ = temp_finished_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.finished_at is not None, 'fixture must be a finished session'

    meta_response = client.post(f'/gym/sessions/{session_id}/meta', data={
        'bodyweight_kg': '91,4',
        'notes': 'nach Feierabend',
    })
    assert meta_response.status_code == 302
    ex_response = client.post(f'/gym/session-exercises/{se_id}/meta', data={
        'notes': 'rechtes Knie zwickt',
        'pain': 'on',
    })
    assert ex_response.status_code == 302

    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg == 91.4, 'a German decimal comma is accepted'
        assert session.notes == 'nach Feierabend'
        se = db.session.get(SessionExercise, se_id)
        assert se.notes == 'rechtes Knie zwickt'
        assert se.pain is True


def test_finished_session_page_renders_bodyweight_and_exercise_note_fields(client, temp_finished_session):
    """The render side of the same fix: session_finished.html is the only
    template a finished session ever hits, so the bodyweight/notes sheet and
    the per-exercise note/pain fields have to actually appear there -- not
    just work when POSTed to directly."""
    session_id, se_id, _ = temp_finished_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        session.bodyweight_kg = 91.4
        session.notes = 'nach Feierabend'
        se = db.session.get(SessionExercise, se_id)
        se.notes = 'rechtes Knie zwickt'
        se.pain = True
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'name="bodyweight_kg"' in html
    assert 'value="91.4"' in html
    assert 'nach Feierabend' in html
    assert f'name="pain"' in html and 'checked' in html
    assert 'rechtes Knie zwickt' in html
    assert f'/gym/sessions/{session_id}/meta' in html
    assert f'/gym/session-exercises/{se_id}/meta' in html


def test_meta_routes_require_login(anon_client, temp_session):
    """anon_client carries no session at all, so this only proves the
    @login_required gate -- it says nothing about one logged-in user reaching
    another's workout. That cross-user coverage lives in
    test_gym_ownership.py's owned_session/owned_session_exercise table."""
    session_id, se_id, _ = temp_session
    assert anon_client.post(f'/gym/sessions/{session_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)
    assert anon_client.post(f'/gym/session-exercises/{se_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)

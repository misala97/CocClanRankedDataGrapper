"""Bodyweight, notes and the pain flag: everything a workout learns to
record about itself beyond the sets."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import Exercise, WorkoutSession, SessionExercise
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


def test_meta_routes_refuse_another_users_workout(anon_client, temp_session):
    session_id, se_id, _ = temp_session
    assert anon_client.post(f'/gym/sessions/{session_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)
    assert anon_client.post(f'/gym/session-exercises/{se_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)

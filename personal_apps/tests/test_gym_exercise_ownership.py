"""One exercise list for everyone; settings and history stay each lifter's.

Exercises were per user from 2026-08-02 until the one list (2026-09-23).
What these tests guarded then -- one lifter never inheriting another's
increment or history through a shared row -- is still the rule, now on a
row both of them use: the row is everyone's, the settings row and the
sessions are not.

Runs against a real database. Every row created here is deleted again.
"""
import datetime as dt
import json
import re

import pytest

from app import app as flask_app
from conftest import _admin_id


def test_an_exercise_belongs_to_nobody():
    from models import Exercise, ExerciseSettings
    assert not hasattr(Exercise, 'user_id'), 'Exercise has an owner again'
    assert ExerciseSettings.__table__.c.user_id.nullable is False


def test_a_list_key_names_one_row():
    from sqlalchemy.exc import IntegrityError
    from extensions import db
    from models import Exercise

    with flask_app.app_context():
        db.session.add_all([Exercise(name='pytest dup a', library_key='pytest_dup_key'),
                            Exercise(name='pytest dup b', library_key='pytest_dup_key')])
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.fixture()
def two_lifters():
    """A key-less exercise the admin has logged once (60 kg) and set a step
    of 9 on, and a second account that has done nothing.

    Yields {'owner_id', 'stranger_id', 'exercise_id', 'owner_session_id'}.
    """
    from extensions import db
    from models import (AppUser, Exercise, ExerciseSettings, SessionExercise, SessionSet,
                        WorkoutSession)
    from werkzeug.security import generate_password_hash

    with flask_app.app_context():
        stranger = AppUser(username='pytest catalogue stranger',
                           password_hash=generate_password_hash('irrelevant'),
                           is_admin=False)
        db.session.add(stranger)
        exercise = Exercise(name='pytest owned lift', muscle_group='Brust',
                            list_increment=2.5, list_rest_seconds=120)
        db.session.add(exercise)
        db.session.flush()
        db.session.add(ExerciseSettings(user_id=_admin_id(), exercise_id=exercise.id,
                                        weight_increment=9.0, default_rest_seconds=200))
        now = dt.datetime.utcnow()
        logged = WorkoutSession(name='pytest owned lift session', user_id=_admin_id(),
                                started_at=now - dt.timedelta(days=2, hours=1),
                                finished_at=now - dt.timedelta(days=2))
        db.session.add(logged)
        db.session.flush()
        se = SessionExercise(session_id=logged.id, exercise_id=exercise.id, position=1)
        se.sets = [SessionSet(position=1, weight=60.0, reps=8, completed=True)]
        db.session.add(se)
        db.session.commit()
        ids = {'owner_id': _admin_id(), 'stranger_id': stranger.id,
               'exercise_id': exercise.id, 'owner_session_id': logged.id}
    yield ids
    with flask_app.app_context():
        for session_ in WorkoutSession.query.filter(WorkoutSession.user_id == ids['stranger_id']).all():
            session_.resting_set_id = None
            db.session.flush()
            db.session.delete(session_)
        doomed = db.session.get(WorkoutSession, ids['owner_session_id'])
        if doomed is not None:
            db.session.delete(doomed)
        db.session.commit()
        ExerciseSettings.query.filter_by(user_id=ids['stranger_id']).delete()
        doomed = db.session.get(Exercise, ids['exercise_id'])
        if doomed is not None:
            db.session.delete(doomed)
        db.session.commit()
        doomed_user = db.session.get(AppUser, ids['stranger_id'])
        if doomed_user is not None:
            db.session.delete(doomed_user)
            db.session.commit()


def _client_for(user_id):
    flask_app.config['TESTING'] = True
    test_client = flask_app.test_client()
    with test_client.session_transaction() as flask_session:
        flask_session['user_id'] = user_id
    return test_client


@pytest.fixture()
def stranger_client(two_lifters):
    return _client_for(two_lifters['stranger_id'])


def _stranger_session(two_lifters):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = WorkoutSession(name='pytest stranger session', started_at=dt.datetime.utcnow(),
                                  user_id=two_lifters['stranger_id'])
        db.session.add(session_)
        db.session.commit()
        return session_.id


def test_a_new_account_is_offered_the_whole_list(stranger_client, two_lifters):
    """First visit: every entry of the list, already set up -- the add sheet
    is where a new lifter starts, and nothing in it is anyone's."""
    from conftest import embedded_payload
    from features.gym.library import LIBRARY

    session_id = _stranger_session(two_lifters)
    payload = embedded_payload(stranger_client.get(f'/gym/session/{session_id}').get_data(as_text=True))
    offered = {entry['name'] for entry in payload['exercises']}
    assert offered == {entry.name for entry in LIBRARY}
    assert 'pytest owned lift' not in offered, 'a row outside the list was offered'
    # Nothing is theirs yet: the sheet opens on the whole list, not on "Deine".
    assert {(e['workouts'], e['days_ago'], e['rank'], e['common'])
            for e in payload['exercises']} == {(0, None, None, False)}


def test_a_new_accounts_catalogue_holds_only_their_own_exercises(stranger_client, two_lifters):
    body = stranger_client.get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' not in body


def test_the_owner_sees_the_exercise_they_logged(two_lifters):
    body = _client_for(two_lifters['owner_id']).get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' in body, 'a logged exercise is missing from its lifter\'s catalogue'


def test_one_lifters_settings_and_history_never_reach_another(stranger_client, two_lifters):
    """Same id, two lifters: each sees their own step, rest and sessions."""
    exercise_id = two_lifters['exercise_id']
    hers = stranger_client.get(f'/gym/exercises/{exercise_id}/detail.json').get_json()
    assert hers['exercise']['weight_increment'] == 2.5
    assert hers['exercise']['default_rest_seconds'] == 120
    assert hers['exercise']['list_defaults']['weight_increment'] == 2.5
    assert hers['table'] == [], 'the owner\'s session shows in her history'

    his = _client_for(two_lifters['owner_id']).get(
        f'/gym/exercises/{exercise_id}/detail.json').get_json()
    assert his['exercise']['weight_increment'] == 9.0
    assert his['exercise']['default_rest_seconds'] == 200
    assert his['exercise']['list_defaults']['weight_increment'] == 2.5
    assert len(his['table']) == 1


def test_adding_an_exercise_by_name_is_refused(stranger_client, two_lifters):
    """The list is read-only: a name-only post from a stale page creates
    nothing, and links to nothing."""
    from models import Exercise, SessionExercise

    session_id = _stranger_session(two_lifters)
    response = stranger_client.post(f'/gym/session/{session_id}/exercises/add',
                                    data={'new_exercise_name': 'pytest brand new lift'})
    assert response.status_code == 400
    with flask_app.app_context():
        assert SessionExercise.query.filter_by(session_id=session_id).count() == 0
        assert Exercise.query.filter_by(name='pytest brand new lift').count() == 0


def test_an_exercise_someone_else_logged_joins_her_session_with_her_values(
        stranger_client, two_lifters):
    """Any row can join any session, since none is owned -- but what it
    brings is the session owner's: her rest, and a plan seeded from her
    (empty) history, never his 60 kg."""
    from features.gym.exercises import setup as exercise_setup
    from models import SessionExercise

    session_id = _stranger_session(two_lifters)
    response = stranger_client.post(f'/gym/session/{session_id}/exercises/add',
                                    data={'exercise_id': str(two_lifters['exercise_id'])})
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        row = SessionExercise.query.filter_by(session_id=session_id).one()
        # The row holds no rest of its own (V3): it follows the session
        # owner's setting at each set -- hers is the list's 120, never his 200.
        assert row.rest_seconds is None
        assert exercise_setup(row.session.user_id, row.exercise).default_rest_seconds == 120, \
            'took the owner\'s rest setting'
        assert row.sets and all(s.is_default_seeded for s in row.sets), \
            'seeded from somebody else\'s history'
        assert all(s.weight != 60.0 for s in row.sets)


def test_a_non_admin_saves_settings_of_their_own(stranger_client, two_lifters):
    """The settings form needs no admin flag and no ownership: it writes the
    caller's settings row. The owner's stays as it was, and a posted name
    renames nothing."""
    from extensions import db
    from models import Exercise, ExerciseSettings

    exercise_id = two_lifters['exercise_id']
    response = stranger_client.post(f'/gym/exercises/{exercise_id}/update',
                                    data={'name': 'pytest renamed lift', 'weight_increment': '5'})
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        mine = ExerciseSettings.query.filter_by(user_id=two_lifters['stranger_id'],
                                                exercise_id=exercise_id).one()
        theirs = ExerciseSettings.query.filter_by(user_id=two_lifters['owner_id'],
                                                  exercise_id=exercise_id).one()
        assert (mine.weight_increment, theirs.weight_increment) == (5.0, 9.0)
        assert db.session.get(Exercise, exercise_id).name == 'pytest owned lift'


def test_the_delete_route_is_gone(stranger_client, two_lifters):
    from extensions import db
    from models import Exercise

    response = stranger_client.post(f"/gym/exercises/{two_lifters['exercise_id']}/delete")
    assert response.status_code == 404
    with flask_app.app_context():
        assert db.session.get(Exercise, two_lifters['exercise_id']) is not None


def test_a_non_admin_is_handed_the_exercise_page(stranger_client, two_lifters):
    """The page payload describes the exercise, never the viewer: no field
    a component could branch an admin gate on."""
    exercise_id = two_lifters['exercise_id']
    response = stranger_client.get(f'/gym/exercises/{exercise_id}')
    assert response.status_code == 200
    payload = json.loads(
        re.search(r'<script type="application/json" id="gym-data">(.*?)</script>',
                  response.get_data(as_text=True), re.S).group(1))
    assert payload['exercise']['id'] == exercise_id
    assert not any('admin' in key for key in payload), \
        'the payload gained a viewer-role field -- an admin gate can now be re-added'

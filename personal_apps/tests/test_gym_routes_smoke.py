"""Smoke checks that every gym GET route renders. Needs the real database, so
these are run manually rather than in the pure-stats suite."""
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['logged_in'] = True
        yield test_client


import datetime as dt


@pytest.fixture()
def scratch_session():
    """A throwaway session with one exercise and two uncompleted sets.

    Deleted afterwards whatever the test does -- this suite runs against the
    real local development database.
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise.query.first()
        assert exercise is not None, 'the dev database needs at least one exercise'
        session_ = WorkoutSession(name='pytest scratch', started_at=dt.datetime.utcnow())
        session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
        session_exercise.sets = [
            SessionSet(position=1, weight=80.0, reps=8, completed=False),
            SessionSet(position=2, weight=75.0, reps=8, completed=False),
        ]
        session_.exercises.append(session_exercise)
        db.session.add(session_)
        db.session.commit()
        session_id = session_.id
    yield session_id
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()


def test_dashboard_renders(client):
    assert client.get('/gym').status_code == 200


def test_uebungen_renders(client):
    assert client.get('/gym/uebungen').status_code == 200


def test_verlauf_renders(client):
    assert client.get('/gym/verlauf').status_code == 200


def test_exercise_detail_renders_for_every_exercise(client):
    with flask_app.app_context():
        from models import Exercise
        ids = [row.id for row in Exercise.query.all()]
    for exercise_id in ids:
        response = client.get('/gym/exercises/{}'.format(exercise_id))
        assert response.status_code == 200, exercise_id


def test_session_pages_render_for_every_finished_session(client):
    with flask_app.app_context():
        from models import WorkoutSession
        ids = [row.id for row in WorkoutSession.query.filter(
            WorkoutSession.finished_at.isnot(None)).all()]
    for session_id in ids:
        assert client.get('/gym/session/{}'.format(session_id)).status_code == 200
        # /summary is a redirect now (a finished workout is one page under
        # /gym/session/<id>) -- kept working for old bookmarks/history.
        # Follow it through to the real destination so this smoke test still
        # catches a broken render, not just a broken redirect.
        assert client.get('/gym/session/{}/summary'.format(session_id), follow_redirects=True).status_code == 200


def set_weights(session_id):
    from models import WorkoutSession
    from extensions import db
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        return [s.weight for se in session_.exercises for s in se.sets]


def deload_state(session_id):
    from models import WorkoutSession
    from extensions import db
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        return session_.is_deload, session_.deload_pct


def base_weights(session_id):
    from models import WorkoutSession
    from extensions import db
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        return [s.base_weight for se in session_.exercises for s in se.sets]


def test_deload_on_rewrites_every_weight_when_nothing_is_completed(client, scratch_session):
    response = client.post('/gym/session/{}/deload'.format(scratch_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    # 80 * 0.7 = 56 -> 55.0 ; 75 * 0.7 = 52.5 -> 52.5
    assert set_weights(scratch_session) == [55.0, 52.5]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_percentage_change_scales_from_the_baseline_not_the_deloaded_weight(client, scratch_session):
    """The compounding regression. Two picks in a row must not stack."""
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert set_weights(scratch_session) == [55.0, 52.5]
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '60'})
    # 60 % of the 80/75 baseline -> 47.5 / 45.0.
    # Compounding from 55/52.5 would give 32.5 / 30.0.
    assert set_weights(scratch_session) == [47.5, 45.0]


def test_deload_applied_twice_at_the_same_percentage_is_idempotent(client, scratch_session):
    """A double-tap or a POST retry must not reduce the weights twice."""
    for _ in range(2):
        client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert set_weights(scratch_session) == [55.0, 52.5]


def test_deload_off_restores_the_exact_pre_deload_weights(client, scratch_session):
    """Replaces the old test, which asserted `!= [77.5, 75.0]` and so passed
    even when the off-branch did nothing at all."""
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert base_weights(scratch_session) == [None, None]
    assert deload_state(scratch_session) == (False, None)


def test_deload_off_restores_a_manually_adjusted_weight_not_last_sessions(client, scratch_session):
    """The baseline is what was actually planned, which may not match history."""
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].weight = 92.5      # user bumped it before starting
        db.session.commit()
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session)[0] == 92.5


def test_deload_on_rewrites_nothing_once_a_set_is_completed(client, scratch_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = True
        db.session.commit()
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_on_a_finished_session_is_label_only(client, scratch_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = True
        session_.finished_at = dt.datetime.utcnow()
        db.session.commit()
    response = client.post('/gym/session/{}/deload'.format(scratch_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_pct_out_of_range_falls_back_to_the_default(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session),
                data={'on': '1', 'pct': '999'})
    assert deload_state(scratch_session) == (True, 70)


def test_deload_pct_that_is_not_a_number_falls_back_to_the_default(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session),
                data={'on': '1', 'pct': 'schwer'})
    assert deload_state(scratch_session) == (True, 70)

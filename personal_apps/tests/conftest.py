"""Shared fixtures. Every suite here runs against the real local development
database, so the account these clients log in as is the seeded admin."""
from contextlib import contextmanager

import pytest

from app import app as flask_app
from flask import session as flask_session


def _admin_id():
    """The seeded admin's id. Imported by the other suites as
    `from conftest import _admin_id` -- tests/ is on sys.path, not a package."""
    from models import AppUser
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None, 'the dev database needs the seeded admin account'
        return admin.id


@pytest.fixture()
def client():
    """Logged in as the author. The gym suites act as the admin throughout."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = _admin_id()
        yield test_client


@pytest.fixture()
def anon_client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def live_session():
    """An unfinished session with one exercise and two sets, one completed.

    Built rather than found. The dev database contains no live workout, so
    tests that went looking for one all skipped -- which is how a real bug
    (pain typed str against a BOOLEAN column) hid behind a green suite.

    Yields {'session', 'se', 'done_set', 'open_set', 'exercise'} of ids.

    The teardown clears resting_set_id first. A mutation that completes a set
    schedules a rest, which points the session at that set; deleting the sets
    with that pointer still set trips the foreign key.
    """
    import datetime as dt

    from extensions import db
    from models import Exercise, PendingPush, SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        user_id = _admin_id()
        exercise = (Exercise.query.filter_by(user_id=user_id)
                    .order_by(Exercise.id).first())
        assert exercise is not None, 'the dev database needs an exercise'
        session_ = WorkoutSession(user_id=user_id, started_at=dt.datetime.utcnow())
        db.session.add(session_)
        db.session.flush()
        se = SessionExercise(session_id=session_.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.flush()
        sets = [
            SessionSet(session_exercise_id=se.id, weight=60.0, reps=8, completed=True),
            SessionSet(session_exercise_id=se.id, weight=60.0, reps=8, completed=False),
        ]
        db.session.add_all(sets)
        db.session.commit()
        ids = {'session': session_.id, 'se': se.id,
               'done_set': sets[0].id, 'open_set': sets[1].id,
               'exercise': exercise.id}

    yield ids

    with flask_app.app_context():
        row = db.session.get(WorkoutSession, ids['session'])
        if row is not None:
            row.resting_set_id = None
            row.rest_ends_at = None
            PendingPush.query.filter_by(session_id=row.id).delete()
            db.session.flush()
            db.session.delete(row)
            db.session.commit()


@contextmanager
def acting_as(user_id):
    """Request context carrying a logged-in session.

    For tests that call route helpers (_last_full_performance and friends)
    directly rather than through the client: those helpers read flask.session
    to scope their queries, which a plain app_context cannot provide. A
    request context pushes an app context too, so db work inside still works.
    """
    with flask_app.test_request_context():
        flask_session['user_id'] = user_id
        yield

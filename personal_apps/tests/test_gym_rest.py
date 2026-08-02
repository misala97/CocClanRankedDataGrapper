"""Rest timing: the column, the pure maths, and the two readouts.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def scratch_live_set():
    """An unfinished session with one exercise and one uncompleted set.

    Yields (session_id, session_exercise_id, set_id, exercise_id).
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    ids = None
    with flask_app.app_context():
        exercise = Exercise(name='pytest rest lift', muscle_group='Brust',
                            user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session_ = WorkoutSession(name='pytest rest session',
                                  started_at=dt.datetime.utcnow(),
                                  user_id=_admin_id())
        se = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=False)]
        session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, session_.exercises[0].id,
               session_.exercises[0].sets[0].id, exercise.id)
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, ids[0])
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, ids[3])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_the_set_table_can_record_when_a_set_landed():
    from models import SessionSet
    assert hasattr(SessionSet, 'completed_at'), 'SessionSet has no completed_at'
    assert SessionSet.__table__.c.completed_at.nullable is True, \
        'completed_at must be nullable -- every set that predates it has none'


def test_completing_a_set_stamps_it(client, scratch_live_set):
    from extensions import db
    from models import SessionSet
    _, _, set_id, _ = scratch_live_set

    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '1', 'weight': '40.0', 'reps': '8'})

    with flask_app.app_context():
        stored = db.session.get(SessionSet, set_id)
        assert stored.completed is True
        assert stored.completed_at is not None, 'completed but never stamped'


def test_un_completing_a_set_clears_the_stamp(client, scratch_live_set):
    """Otherwise re-ticking measures a gap that includes however long you spent
    deciding, and the number silently becomes fiction."""
    from extensions import db
    from models import SessionSet
    _, _, set_id, _ = scratch_live_set

    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '1', 'weight': '40.0', 'reps': '8'})
    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '0', 'weight': '40.0', 'reps': '8'})

    with flask_app.app_context():
        stored = db.session.get(SessionSet, set_id)
        assert stored.completed is False
        assert stored.completed_at is None, 'a stale stamp survived un-completing'


def test_a_set_appended_mid_workout_is_stamped(client, scratch_live_set):
    """gym_add_set creates a set already completed, so it must stamp it too --
    it is the path used every time you append past the planned sets."""
    from extensions import db
    from models import SessionExercise
    _, se_id, _, _ = scratch_live_set

    client.post(f'/gym/session-exercise/{se_id}/sets/add',
                data={'weight': '42.5', 'reps': '6'})

    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        appended = [s for s in se.sets if s.completed]
        assert appended, 'no completed set was appended'
        assert all(s.completed_at is not None for s in appended), \
            'an appended set was left unstamped'


@pytest.fixture()
def finished_with_rest():
    """A finished session whose three sets landed 3 and 2 minutes apart.

    Yields (session_id, exercise_id).
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    ids = None
    with flask_app.app_context():
        exercise = Exercise(name='pytest rest readout lift', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        started = dt.datetime.utcnow() - dt.timedelta(hours=1)
        session_ = WorkoutSession(name='pytest rest readout', started_at=started,
                                  finished_at=started + dt.timedelta(minutes=52),
                                  user_id=_admin_id())
        se = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se.sets = [
            SessionSet(position=1, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=5)),
            SessionSet(position=2, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=8)),
            SessionSet(position=3, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=10)),
        ]
        session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, exercise.id)
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, ids[0])
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, ids[1])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_the_finished_page_reports_the_rest_it_measured(client, finished_with_rest):
    """3 minutes then 2 gives 5 minutes of counted rest."""
    session_id, _ = finished_with_rest
    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'davon 5 Minuten Pause' in html


def test_the_finished_page_says_nothing_about_rest_without_stamps(client, scratch_live_set):
    """Every set that predates the column has completed_at NULL. The page must
    not answer a question it has no data for."""
    from extensions import db
    from models import WorkoutSession
    session_id, _, set_id, _ = scratch_live_set
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        session_.finished_at = dt.datetime.utcnow()
        for se in session_.exercises:
            for s in se.sets:
                s.completed, s.completed_at = True, None
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'Pause' not in html, 'claimed a rest figure with no timestamps to build it from'


def test_statistik_reports_planned_against_actual_rest(client, finished_with_rest):
    """The fixture plans 150 s and takes 180 and 120, so the medians are
    2:30 planned against 2:30 actual -- the point is that both are stated."""
    html = client.get('/gym/statistik').get_data(as_text=True)
    assert 'Wie lange pausierst du' in html
    assert 'Du planst' in html


def test_statistik_says_nothing_about_rest_without_stamps(client):
    """With no timestamped session anywhere, the question must not be asked --
    an unanswerable question on the page reads as a broken feature."""
    from extensions import db
    from models import SessionSet
    with flask_app.app_context():
        stamped = SessionSet.query.filter(SessionSet.completed_at.isnot(None)).all()
        saved = [(s.id, s.completed_at) for s in stamped]
        for s in stamped:
            s.completed_at = None
        db.session.commit()
    try:
        html = client.get('/gym/statistik').get_data(as_text=True)
        assert 'Wie lange pausierst du' not in html
    finally:
        with flask_app.app_context():
            for set_id, when in saved:
                row = db.session.get(SessionSet, set_id)
                if row is not None:
                    row.completed_at = when
            db.session.commit()

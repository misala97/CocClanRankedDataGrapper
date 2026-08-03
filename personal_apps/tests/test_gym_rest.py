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


@pytest.fixture()
def two_close_sessions():
    """Two separately finished sessions whose sets straddle a 30-second gap:
    the last set of session 1 lands 30 seconds before the first set of
    session 2.

    That 30 s is well inside REST_GAP_CAP_SECONDS (600), so it would NOT be
    dropped by the cap if the two sessions' entries were ever pooled into one
    stats.rest_gaps() call -- it would show up as a spurious "rest" spanning
    two different workouts. Grouped correctly per session (rest_gaps() called
    once per session, per gym_statistik's actual habit_gaps loop), the two
    sessions only ever produce their own internal gaps: 180 s in session 1,
    240 s in session 2. Neither of those is 30.

    Yields (session_id_1, session_id_2, exercise_id).
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    ids = None
    with flask_app.app_context():
        exercise = Exercise(name='pytest cross-session lift', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()

        base = dt.datetime.utcnow() - dt.timedelta(hours=2)
        session_1 = WorkoutSession(name='pytest cross-session one', started_at=base,
                                   finished_at=base + dt.timedelta(minutes=10),
                                   user_id=_admin_id())
        se1 = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se1.sets = [
            SessionSet(position=1, weight=40.0, reps=8, completed=True,
                       completed_at=base),
            SessionSet(position=2, weight=40.0, reps=8, completed=True,
                       completed_at=base + dt.timedelta(seconds=180)),
        ]
        session_1.exercises.append(se1)
        db.session.add(session_1)
        db.session.commit()

        # Session 2 starts 30 s after session 1's last set -- a real gap
        # between two different workouts, not a rest inside either one.
        session_2_first = base + dt.timedelta(seconds=210)
        session_2 = WorkoutSession(name='pytest cross-session two',
                                   started_at=session_2_first,
                                   finished_at=session_2_first + dt.timedelta(minutes=10),
                                   user_id=_admin_id())
        se2 = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se2.sets = [
            SessionSet(position=1, weight=40.0, reps=8, completed=True,
                       completed_at=session_2_first),
            SessionSet(position=2, weight=40.0, reps=8, completed=True,
                       completed_at=session_2_first + dt.timedelta(seconds=240)),
        ]
        session_2.exercises.append(se2)
        db.session.add(session_2)
        db.session.commit()

        ids = (session_1.id, session_2.id, exercise.id)
    yield ids
    with flask_app.app_context():
        for session_id in ids[:2]:
            doomed = db.session.get(WorkoutSession, session_id)
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
                db.session.commit()
        doomed_exercise = db.session.get(Exercise, ids[2])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_rest_gaps_are_built_per_session_not_flattened_across_history(two_close_sessions):
    """Pins the load-bearing rule gym_statistik's habit_gaps loop depends on:
    rest_gaps() is called ONCE PER SESSION and the results concatenated,
    never once across the whole history. Neither the pure stats.rest_gaps()
    tests nor test_statistik_reports_planned_against_actual_rest can catch a
    regression here -- the former only ever sees one session's entries, and
    the latter only asserts that two German substrings are present, never an
    actual number.
    """
    from extensions import db
    from features.gym import stats
    from features.gym.routes import _session_rest_entries
    from models import WorkoutSession

    session_id_1, session_id_2, _ = two_close_sessions

    with flask_app.app_context():
        session_1 = db.session.get(WorkoutSession, session_id_1)
        session_2 = db.session.get(WorkoutSession, session_id_2)

        # Prove the fixture actually exercises the bug: flattening both
        # sessions' entries into one rest_gaps() call produces the spurious
        # 30 s cross-session gap.
        flattened = stats.rest_gaps(
            _session_rest_entries(session_1) + _session_rest_entries(session_2))
        flattened_actuals = [actual for actual, _ in flattened]
        assert 30 in flattened_actuals, \
            'fixture does not actually straddle a cross-session gap -- test is not load-bearing'

        # The real per-session grouping: one rest_gaps() call per session,
        # concatenated -- exactly what gym_statistik's habit_gaps loop does.
        grouped = (stats.rest_gaps(_session_rest_entries(session_1))
                   + stats.rest_gaps(_session_rest_entries(session_2)))
        grouped_actuals = [actual for actual, _ in grouped]

    assert 30 not in grouped_actuals, \
        'a gap spanning two different sessions leaked into the per-session grouping'
    assert sorted(grouped_actuals) == [180, 240], \
        'per-session grouping should yield exactly the two sessions own internal gaps'


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

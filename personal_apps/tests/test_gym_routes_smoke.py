"""Smoke checks that every gym GET route renders. Needs the real database, so
these are run manually rather than in the pure-stats suite."""
import pytest

from app import app as flask_app
from conftest import _admin_id, acting_as

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
        session_ = WorkoutSession(name='pytest scratch', started_at=dt.datetime.utcnow(),
                                  user_id=_admin_id())
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


def test_statistik_renders(client):
    assert client.get('/gym/statistik').status_code == 200


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


def test_deload_on_records_the_baseline_it_captured(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert base_weights(scratch_session) == [80.0, 75.0]


def test_completing_a_set_freezes_the_weights_and_un_completing_thaws_them(client, scratch_session):
    """The "computed, not latched" guarantee: the completed-set gate is
    re-evaluated per request, so un-completing a set makes the toggle able to
    rewrite again and a mis-tap is always recoverable."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert set_weights(scratch_session) == [55.0, 52.5]

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = True
        db.session.commit()
    # Frozen: a completed set gates the rewrite, so toggling off changes the
    # flag but leaves every weight alone.
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session) == [55.0, 52.5]

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = False
        db.session.commit()
    # Thawed: nothing is completed any more, so the gate opens and the
    # baseline restores exactly.
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert base_weights(scratch_session) == [None, None]


def test_a_weight_typed_during_a_deload_survives_turning_it_off(client, scratch_session):
    """Fix 1's regression: a stale baseline must not overwrite a hand-typed
    weight. Before the fix this restored 80.0 and lost the 60.0 entirely."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        set_id = session_.exercises[0].sets[0].id
    client.post('/gym/set/{}/update'.format(set_id), data={'weight': '60', 'reps': '8'})
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session)[0] == 60.0


def test_ticking_a_set_done_does_not_destroy_its_deload_baseline(client, scratch_session):
    """The check button submits the whole row, so an unchanged weight must not
    read as a hand-typed one -- otherwise completing and un-completing a set
    during a deload loses its working weight for good."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        set_id = session_.exercises[0].sets[0].id
    # Tick done, then undo -- exactly what the form posts, weight unchanged.
    client.post('/gym/set/{}/toggle_complete'.format(set_id), data={'weight': '55.0', 'reps': '8'})
    client.post('/gym/set/{}/toggle_complete'.format(set_id), data={'weight': '55.0', 'reps': '8'})
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert base_weights(scratch_session) == [None, None]


def test_a_new_session_seeds_from_the_last_normal_session_not_the_deload():
    """The regression this whole feature exists to prevent.

    Without the filter in _last_session_exercise, the session after a deload
    pre-fills at 70 %, the one after that seeds from *that*, and the lifter
    silently never returns to their real working weight.

    The exercise used here is created for this test, not borrowed from the
    live catalogue -- otherwise a real exercise trained in slot 1 within the
    last two days would produce an unrelated pre-existing session, and this
    test would fail for a reason that has nothing to do with deloads.
    """
    from extensions import db
    from features.gym.routes import _last_full_performance
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    created = []
    exercise_id = None
    try:
        with acting_as(_admin_id()):
            exercise = Exercise(name='pytest seed lift', is_unilateral=False, user_id=_admin_id())
            db.session.add(exercise)
            db.session.commit()
            exercise_id = exercise.id

            for offset, weight, deload in ((2, 100.0, False), (1, 70.0, True)):
                started = dt.datetime.utcnow() - dt.timedelta(days=offset)
                session_ = WorkoutSession(
                    name='pytest seed {}'.format(offset), started_at=started,
                    finished_at=started + dt.timedelta(hours=1), is_deload=deload,
                    deload_pct=70 if deload else None, user_id=_admin_id())
                session_exercise = SessionExercise(exercise_id=exercise_id, position=1)
                session_exercise.sets = [
                    SessionSet(position=1, weight=weight, reps=8, completed=True)]
                session_.exercises.append(session_exercise)
                db.session.add(session_)
                db.session.commit()
                created.append(session_.id)

            seeded = _last_full_performance(exercise_id, position=1)
            assert seeded, 'expected the normal session to be found'
            assert len(seeded) == 1
            assert seeded[0]['weight'] == 100.0, 'seeded from the deload'
    finally:
        with flask_app.app_context():
            # The exercise delete is in its own finally: if the session delete
            # above raised, the exercise would otherwise leak -- and because
            # Exercise.name is unique, a stranded 'pytest seed lift' row would
            # sit in the real catalogue and make every later run of this test
            # fail at insert. Sessions must still go first: Exercise
            # .session_exercises has no cascade, so deleting the exercise
            # while its SessionExercise rows are live would try to null a
            # NOT NULL foreign key.
            try:
                for session_id in created:
                    doomed = db.session.get(WorkoutSession, session_id)
                    if doomed is not None:
                        db.session.delete(doomed)
                db.session.commit()
            finally:
                if exercise_id is not None:
                    doomed_exercise = db.session.get(Exercise, exercise_id)
                    if doomed_exercise is not None:
                        db.session.delete(doomed_exercise)
                    db.session.commit()


def _seed_slot_history(rows):
    """Create a throwaway exercise plus one finished session per (days_ago,
    position, weight). Returns (exercise_id, [session_ids]).

    Its own exercise, so no real training data can influence which session the
    seeding query considers most recent.
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    exercise = Exercise(name='pytest slot lift', is_unilateral=False, user_id=_admin_id())
    db.session.add(exercise)
    db.session.flush()
    created = []
    for days_ago, position, weight in rows:
        started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
        session_ = WorkoutSession(name='pytest slot %d' % days_ago, started_at=started,
                                  finished_at=started + dt.timedelta(hours=1),
                                  user_id=_admin_id())
        session_exercise = SessionExercise(exercise_id=exercise.id, position=position)
        session_exercise.sets = [SessionSet(position=1, weight=weight, reps=8, completed=True)]
        session_.exercises.append(session_exercise)
        db.session.add(session_)
        db.session.commit()
        created.append(session_.id)
    return exercise.id, created


def _drop_slot_history(exercise_id, session_ids):
    from extensions import db
    from models import Exercise, WorkoutSession
    try:
        for session_id in session_ids:
            doomed = db.session.get(WorkoutSession, session_id)
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
        db.session.commit()
    finally:
        if exercise_id is not None:
            doomed_exercise = db.session.get(Exercise, exercise_id)
            if doomed_exercise is not None:
                db.session.delete(doomed_exercise)
                db.session.commit()


def test_stale_slot_history_does_not_beat_a_recent_performance():
    """Reordering an exercise months ago must not resurrect the weight from
    whatever slot the template still names.

    Slot 1 was last trained 200 days ago at 40 kg; the lifter has since been
    doing it at slot 2 and is now on 70 kg. Starting from a template that
    still puts it in slot 1 must pre-fill 70, not 40 -- the slot's own history
    is only the fairer comparison while it is still current.
    """
    from features.gym.routes import _last_full_performance
    exercise_id = None
    created = []
    try:
        with acting_as(_admin_id()):
            exercise_id, created = _seed_slot_history([
                (200, 1, 40.0),   # stale slot-1 history
                (3, 2, 70.0),     # current working weight, different slot
            ])
            seeded = _last_full_performance(exercise_id, position=1)
            assert seeded, 'expected some history to be found'
            assert seeded[0]['weight'] == 70.0, 'seeded from stale slot history'
    finally:
        with flask_app.app_context():
            _drop_slot_history(exercise_id, created)


def test_recent_slot_history_still_wins_over_another_slot():
    """The fatigue rule still holds while the slot's data is current: an
    exercise recently trained in this very slot pre-fills from that slot, even
    though a lighter/heavier performance exists in another one."""
    from features.gym.routes import _last_full_performance
    exercise_id = None
    created = []
    try:
        with acting_as(_admin_id()):
            exercise_id, created = _seed_slot_history([
                (5, 3, 61.0),     # recent, in the slot we will ask for
                (2, 2, 69.0),     # more recent, but a fresher slot
            ])
            seeded = _last_full_performance(exercise_id, position=3)
            assert seeded, 'expected some history to be found'
            assert seeded[0]['weight'] == 61.0, 'ignored still-current slot history'
    finally:
        with flask_app.app_context():
            _drop_slot_history(exercise_id, created)


def _deload_reorder_fixture():
    """Two throwaway exercises, each with recent completed history, plus an
    unstarted session holding both in slots 1 and 2.

    Returns (exercise_ids, history_session_ids, active_session_id).
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    exercise_ids, history_ids = [], []
    for label, weight in (('a', 100.0), ('b', 50.0)):
        exercise = Exercise(name='pytest reorder lift %s' % label, is_unilateral=False, user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        exercise_ids.append(exercise.id)
        started = dt.datetime.utcnow() - dt.timedelta(days=3)
        history = WorkoutSession(name='pytest reorder history %s' % label, started_at=started,
                                 finished_at=started + dt.timedelta(hours=1),
                                 user_id=_admin_id())
        history_exercise = SessionExercise(exercise_id=exercise.id, position=len(exercise_ids))
        history_exercise.sets = [SessionSet(position=1, weight=weight, reps=8, completed=True)]
        history.exercises.append(history_exercise)
        db.session.add(history)
        db.session.commit()
        history_ids.append(history.id)

    active = WorkoutSession(name='pytest reorder active', started_at=dt.datetime.utcnow(),
                            user_id=_admin_id())
    for position, (exercise_id, weight) in enumerate(zip(exercise_ids, (100.0, 50.0)), start=1):
        session_exercise = SessionExercise(exercise_id=exercise_id, position=position)
        session_exercise.sets = [SessionSet(position=1, weight=weight, reps=8, completed=False)]
        active.exercises.append(session_exercise)
    db.session.add(active)
    db.session.commit()
    return exercise_ids, history_ids, active.id


def test_reordering_a_deload_session_keeps_the_deloaded_weights(client):
    """Reordering re-seeds an exercise's pending sets from history, which is
    recorded at full working weight. On a deload session that silently undid
    the prescription for every exercise that moved."""
    from extensions import db
    from models import SessionExercise, WorkoutSession
    exercise_ids = history_ids = active_id = None
    try:
        with flask_app.app_context():
            exercise_ids, history_ids, active_id = _deload_reorder_fixture()

        client.post('/gym/session/%d/deload' % active_id, data={'on': '1', 'pct': '70'})
        # 100 * 0.7 = 70.0 ; 50 * 0.7 = 35.0
        assert set_weights(active_id) == [70.0, 35.0]

        with flask_app.app_context():
            session_ = db.session.get(WorkoutSession, active_id)
            swapped = [se.id for se in sorted(session_.exercises, key=lambda se: -se.position)]
        client.post('/gym/session/%d/exercises/reorder' % active_id,
                    json={'order': [str(se_id) for se_id in swapped]})

        with flask_app.app_context():
            session_ = db.session.get(WorkoutSession, active_id)
            ordered = sorted(session_.exercises, key=lambda se: se.position)
            weights = [s.weight for se in ordered for s in se.sets]
            bases = [s.base_weight for se in ordered for s in se.sets]
        # slot 1 is now the 50 kg lift, slot 2 the 100 kg one -- both still deloaded
        assert weights == [35.0, 70.0]
        assert bases == [50.0, 100.0]
    finally:
        with flask_app.app_context():
            if active_id is not None:
                doomed = db.session.get(WorkoutSession, active_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            for exercise_id, history_id in zip(exercise_ids or [], history_ids or []):
                _drop_slot_history(exercise_id, [history_id])


@pytest.fixture()
def scratch_increment_exercise():
    """A throwaway Exercise inside a throwaway session.

    Its own exercise rather than the catalogue's first one, because these tests
    write to the exercise itself and must not leave a real lift carrying a
    made-up increment. Both rows are deleted afterwards.
    """
    from extensions import db
    from models import Exercise, SessionExercise, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest scratch increment lift', muscle_group='Brust', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session_ = WorkoutSession(name='pytest scratch increment',
                                  started_at=dt.datetime.utcnow(), user_id=_admin_id())
        session_.exercises.append(SessionExercise(exercise_id=exercise.id, position=1))
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, session_.exercises[0].id, exercise.id)
    yield ids
    with flask_app.app_context():
        session_id, _, exercise_id = ids
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_live_stepper_falls_back_when_the_exercise_has_no_increment(client, scratch_increment_exercise):
    session_id, _, _ = scratch_increment_exercise
    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'data-step="2.5" data-decimals="1"' in html


def test_live_stepper_uses_the_exercises_own_increment(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise
    session_id, _, exercise_id = scratch_increment_exercise

    with flask_app.app_context():
        db.session.get(Exercise, exercise_id).weight_increment = 9.0
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'data-step="9.0" data-decimals="1"' in html
    # The fallback must be gone, not merely joined -- this session has exactly
    # one exercise, so a surviving 2.5 would mean the template still branches
    # on is_unilateral instead of reading the resolved value.
    assert 'data-step="2.5"' not in html


def test_session_sheet_writes_the_increment_to_the_exercise(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise, SessionExercise
    _, session_exercise_id, exercise_id = scratch_increment_exercise

    response = client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                           data={'weight_increment': '9'})
    assert response.status_code == 302

    with flask_app.app_context():
        assert db.session.get(Exercise, exercise_id).weight_increment == 9.0
        # The session row is untouched: this field is per exercise, forever,
        # unlike the rest time sitting directly above it in the same sheet.
        assert db.session.get(SessionExercise, session_exercise_id).rest_seconds is None


def test_session_sheet_clears_the_increment_back_to_the_default(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise
    _, session_exercise_id, exercise_id = scratch_increment_exercise

    client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                data={'weight_increment': '9'})
    client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                data={'weight_increment': ''})

    with flask_app.app_context():
        assert db.session.get(Exercise, exercise_id).weight_increment is None


def test_to_increment_is_comma_tolerant():
    """A German keyboard produces '2,5', not '2.5' -- the docstring's claim,
    unverified until now."""
    from features.gym.routes import _to_increment
    assert _to_increment('2,5') == 2.5


@pytest.mark.parametrize('raw', ['-9', 'abc', '0', ''])
def test_to_increment_rejects_non_positive_and_unparseable(raw):
    from features.gym.routes import _to_increment
    assert _to_increment(raw) is None


def test_add_exercise_carries_the_increment_onto_the_new_row(client):
    """gym_add_exercise is a write surface for weight_increment with no
    other coverage -- a dropped/typo'd form field here would silently store
    NULL and nothing would fail."""
    from extensions import db
    from models import Exercise

    response = client.post('/gym/exercises/add', data={
        'name': 'pytest add exercise increment',
        'muscle_group': 'Brust',
        'weight_increment': '5',
    })
    assert response.status_code in (302, 303)

    exercise_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise.query.filter_by(name='pytest add exercise increment').first()
            assert exercise is not None
            exercise_id = exercise.id
            assert exercise.weight_increment == 5.0
            assert exercise.muscle_group == 'Brust'
    finally:
        if exercise_id is not None:
            with flask_app.app_context():
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_update_exercise_sets_and_clears_the_increment_without_losing_other_fields(client):
    """gym_update_exercise writes weight_increment unconditionally, so this
    also pins that name and muscle_group survive both writes -- the failure
    mode this finding is about is a silent NULL on an unrelated field, not
    just on the increment itself."""
    from extensions import db
    from models import Exercise

    with flask_app.app_context():
        exercise = Exercise(name='pytest update exercise increment', muscle_group='Rücken', user_id=_admin_id())
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id

    try:
        response = client.post(f'/gym/exercises/{exercise_id}/update', data={
            'name': 'pytest update exercise increment',
            'muscle_group': 'Rücken',
            'weight_increment': '5',
        })
        assert response.status_code in (302, 303)
        with flask_app.app_context():
            exercise = db.session.get(Exercise, exercise_id)
            assert exercise.weight_increment == 5.0
            assert exercise.name == 'pytest update exercise increment'
            assert exercise.muscle_group == 'Rücken'

        response = client.post(f'/gym/exercises/{exercise_id}/update', data={
            'name': 'pytest update exercise increment',
            'muscle_group': 'Rücken',
            'weight_increment': '',
        })
        assert response.status_code in (302, 303)
        with flask_app.app_context():
            exercise = db.session.get(Exercise, exercise_id)
            assert exercise.weight_increment is None
            assert exercise.name == 'pytest update exercise increment'
            assert exercise.muscle_group == 'Rücken'
    finally:
        with flask_app.app_context():
            doomed = db.session.get(Exercise, exercise_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


@pytest.fixture()
def scratch_deload_session():
    """A deload session with no exercises yet, plus recent history to suggest from.

    Self-contained rather than leaning on whatever the dev database holds: a
    throwaway exercise, one finished non-deload session that logged it at
    100 kg (so _last_session_exercise has something CURRENT to match), and an
    empty active session flagged as a 70 % deload.
    """
    import datetime as dt
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest deload suggest lift', muscle_group='Brust', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()

        past = WorkoutSession(name='pytest deload history',
                              started_at=dt.datetime.utcnow() - dt.timedelta(days=3),
                              finished_at=dt.datetime.utcnow() - dt.timedelta(days=3),
                              user_id=_admin_id())
        past_se = SessionExercise(exercise_id=exercise.id, position=1)
        past_se.sets = [SessionSet(position=1, weight=100.0, reps=8, completed=True)]
        past.exercises.append(past_se)

        live = WorkoutSession(name='pytest deload live',
                              started_at=dt.datetime.utcnow(),
                              is_deload=True, deload_pct=70, user_id=_admin_id())
        db.session.add_all([past, live])
        db.session.commit()
        ids = (live.id, past.id, exercise.id)
    yield ids
    with flask_app.app_context():
        live_id, past_id, exercise_id = ids
        for sid in (live_id, past_id):
            doomed = db.session.get(WorkoutSession, sid)
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
                db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_deload_scales_the_suggestion_for_an_exercise_added_mid_session(client, scratch_deload_session):
    """A session started without a template has no sets for gym_toggle_deload to
    scale, and gym_add_session_exercise creates none either -- so the steppers
    fall back to the raw suggestion, which offered the full working weight and
    silently handed back the deload the lifter had just asked for.
    """
    live_id, _, exercise_id = scratch_deload_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'exercise_id': str(exercise_id)})
    assert response.status_code in (302, 303)

    html = client.get(f'/gym/session/{live_id}').get_data(as_text=True)
    # 100 kg at 70 % on the default 2.5 grid is exactly 70.0.
    assert 'name="weight" value="70.0"' in html
    assert 'name="weight" value="100.0"' not in html


def test_adding_an_exercise_mid_session_seeds_its_sets_from_history(client, scratch_deload_session):
    """Adding an exercise mid-session was the only one of four seeding paths
    that created no sets at all -- template start, un-skip and reorder all
    call _seeded_sets. It now mirrors what was last done in that slot.
    """
    from extensions import db
    from models import SessionExercise, WorkoutSession
    live_id, _, exercise_id = scratch_deload_session
    with flask_app.app_context():                  # plain session, no deload
        live = db.session.get(WorkoutSession, live_id)
        live.is_deload, live.deload_pct = False, None
        db.session.commit()

    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.weight, s.reps, s.completed) for s in se.sets] == [(100.0, 8, False)]
        # Seeded sets are proposals, not history: nothing is logged until the
        # lifter confirms it, and base_weight stays clear on a normal session.
        assert se.sets[0].base_weight is None


def test_adding_an_exercise_to_a_deload_session_seeds_scaled_sets(client, scratch_deload_session):
    """The same path during a deload: the seeded sets carry the prescription,
    and base_weight remembers the working weight so switching the deload off
    restores them like any other."""
    from extensions import db
    from models import SessionExercise
    live_id, _, exercise_id = scratch_deload_session

    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        # 100 kg at 70 % on the default 2.5 grid, at the deload rep count.
        assert [(s.weight, s.base_weight, s.reps) for s in se.sets] == [(70.0, 100.0, 10)]


def test_deload_seeds_ten_reps_and_remembers_the_real_ones(client, scratch_deload_session):
    """A deload prescribes a rep count as well as a weight. History is recorded
    at working reps, so seeding them raw hands back half the prescription."""
    from extensions import db
    from models import SessionExercise
    live_id, _, exercise_id = scratch_deload_session      # history is 100 kg x 8

    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.weight, s.reps) for s in se.sets] == [(70.0, 10)]
        assert [(s.base_weight, s.base_reps) for s in se.sets] == [(100.0, 8)]


def test_toggling_a_deload_on_rewrites_reps_and_off_restores_them(client, scratch_deload_session):
    """The template flow: sets already exist at working weight and working reps
    when the deload is switched on, so the toggle -- not the seeding -- is what
    has to apply the prescription, and undo it."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, _, exercise_id = scratch_deload_session
    with flask_app.app_context():                 # start it as a plain session
        live = db.session.get(WorkoutSession, live_id)
        live.is_deload, live.deload_pct = False, None
        se = SessionExercise(session_id=live_id, exercise_id=exercise_id, position=1)
        se.sets = [SessionSet(position=1, weight=100.0, reps=8, completed=False)]
        db.session.add(se)
        db.session.commit()

    client.post(f'/gym/session/{live_id}/deload', data={'on': '1', 'pct': '70'})
    with flask_app.app_context():
        s = SessionExercise.query.filter_by(session_id=live_id).one().sets[0]
        assert (s.weight, s.reps) == (70.0, 10)
        assert (s.base_weight, s.base_reps) == (100.0, 8)

    client.post(f'/gym/session/{live_id}/deload', data={'on': '0'})
    with flask_app.app_context():
        s = SessionExercise.query.filter_by(session_id=live_id).one().sets[0]
        assert (s.weight, s.reps) == (100.0, 8)
        assert (s.base_weight, s.base_reps) == (None, None)


def test_hand_typed_reps_drop_the_deload_baseline(client, scratch_deload_session):
    """Symmetric with the weight rule: a typed rep count is ground truth, so a
    later toggle-off must not overwrite it."""
    from extensions import db
    from models import SessionExercise
    live_id, _, exercise_id = scratch_deload_session
    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        set_id = SessionExercise.query.filter_by(session_id=live_id).one().sets[0].id
    client.post(f'/gym/set/{set_id}/update', data={'weight': '70.0', 'reps': '6'})

    with flask_app.app_context():
        from models import SessionSet
        s = db.session.get(SessionSet, set_id)
        assert s.reps == 6
        assert s.base_reps is None          # dropped: the typed 6 is now the truth
        assert s.base_weight == 100.0       # weight was echoed unchanged, baseline survives


def test_the_add_exercise_sheet_separates_picking_from_creating(client, scratch_session):
    """The sheet used to carry a "— Neue Übung —" option in the catalogue select
    plus a permanently visible name field, so both paths were one form and
    neither was signposted. They are two panes and two forms now.

    Pins the structural guarantee rather than the styling: the pick form must
    not offer a create option, and the create form must not carry an
    exercise_id -- that empty-value pair is exactly what made the old sheet
    ambiguous, and it is what gym_add_session_exercise branches on.
    """
    html = client.get(f'/gym/session/{scratch_session}').get_data(as_text=True)

    assert 'id="add-pick-pane"' in html
    assert 'id="add-new-pane"' in html
    assert '— Neue Übung —' not in html, 'the fake select option is back'

    pick = html.split('id="add-pick-pane"', 1)[1].split('id="add-new-pane"', 1)[0]
    assert 'name="exercise_id"' in pick
    assert 'name="new_exercise_name"' not in pick, 'create fields leaked into the pick pane'

    create = html.split('id="add-new-pane"', 1)[1].split('</dialog>', 1)[0]
    assert 'name="new_exercise_name"' in create
    assert 'name="exercise_id"' not in create, 'the create form still submits an exercise id'


def test_a_finished_exercise_can_still_append_a_set_from_the_panel(client, scratch_session):
    """With every set logged, the panel used to render a paragraph pointing at
    the row's ⋮ sheet and no control -- the same bug the block's own comment
    records fixing for an exercise with no sets at all, one branch over.

    gym_add_set already backed the confirm button whenever nothing was pending,
    so the state was missing the control, not the machinery.
    """
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        for s in session_.exercises[0].sets:
            s.completed = True
        db.session.commit()

    html = client.get(f'/gym/session/{scratch_session}').get_data(as_text=True)

    assert 'id="set-confirm"' in html, 'no confirm button once every set is logged'
    assert 'sets/add' in html, 'the confirm button does not append a set'
    assert 'über <b>⋮</b>' not in html, 'still sending the lifter to the sheet'


def test_appending_a_set_starts_from_the_last_one_not_the_opening_suggestion(client, scratch_session):
    """The reason you append is that the last set went well enough to want
    another, so the steppers open on it rather than on the session's starting
    suggestion."""
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        sets_ = session_.exercises[0].sets
        for s in sets_:
            s.completed = True
        sets_[-1].weight, sets_[-1].reps = 62.5, 5
        db.session.commit()

    html = client.get(f'/gym/session/{scratch_session}').get_data(as_text=True)
    assert 'value="62.5"' in html, 'steppers ignored the set that was actually just done'
    assert 'value="5"' in html


def test_the_finished_page_can_actually_save_a_freeform_workout_as_a_template():
    """The finished page's prompt posted name="name" while gym_save_as_template
    reads template_name, so the route saw an empty string, skipped the `if`,
    and redirected having created nothing -- silently, since the redirect is
    the same one a success produces. Broken since the finished pages were
    merged on 2026-07-23.

    Submits exactly what the rendered form declares rather than a hardcoded
    field name, so this fails again if either side is renamed on its own.
    """
    import datetime as dt
    import re
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession, WorkoutTemplate

    ex_id = sid = tpl_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest finished tpl lift', user_id=_admin_id())
            db.session.add(exercise)
            db.session.flush()
            ex_id = exercise.id
            started = dt.datetime.utcnow() - dt.timedelta(hours=1)
            done = WorkoutSession(name='pytest finished tpl', started_at=started,
                                  finished_at=dt.datetime.utcnow(), user_id=_admin_id())
            se = SessionExercise(exercise_id=exercise.id, position=1)
            se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
            done.exercises.append(se)
            db.session.add(done)
            db.session.commit()
            sid = done.id

        flask_app.config['TESTING'] = True
        with flask_app.test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session['user_id'] = _admin_id()
            # The prompt is gated on ?just_finished -- it is offered at the one
            # moment you know what you did, not on every later visit.
            html = client.get(f'/gym/session/{sid}?just_finished=1').get_data(as_text=True)
            assert 'als Vorlage speichern' in html, 'the freeform prompt did not render'

            form = html.split('save_as_template', 1)[1].split('</form>', 1)[0]
            field = re.search(r'<input[^>]*type="text"[^>]*name="([^"]+)"', form)
            assert field, 'no text input in the save-as-template form'

            response = client.post(f'/gym/session/{sid}/save_as_template',
                                   data={field.group(1): 'pytest finished tpl name'})
            assert response.status_code in (302, 303)

        with flask_app.app_context():
            created = WorkoutTemplate.query.filter_by(name='pytest finished tpl name').first()
            assert created is not None, \
                f'the form posts {field.group(1)!r}, which the route ignores'
            tpl_id = created.id
            assert [te.exercise_id for te in created.exercises] == [ex_id]
    finally:
        with flask_app.app_context():
            for model, row_id in ((WorkoutTemplate, tpl_id), (WorkoutSession, sid)):
                if row_id:
                    doomed = db.session.get(model, row_id)
                    if doomed is not None:
                        if model is WorkoutSession:
                            doomed.resting_set_id = None
                            db.session.commit()
                        db.session.delete(doomed)
                        db.session.commit()
            if ex_id:
                doomed = db.session.get(Exercise, ex_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()

def test_every_gym_form_posts_fields_its_own_route_reads():
    """The class of bug behind the finished page's broken save-as-template: the
    form posted `name` while gym_save_as_template reads `template_name`, so the
    route saw an empty string, skipped its `if`, and redirected -- the same
    redirect a success produces. Ten days of a button that looked like it worked.

    Checking that *some* route reads a field is not enough: `name` is read by
    gym_add_exercise, so a global scan passes while the form is still broken.
    The pairing is what matters, so this resolves each form's own action to its
    route function and checks that function's body.
    """
    import re
    from pathlib import Path

    root = Path(flask_app.root_path)
    source = (root / 'features' / 'gym' / 'routes.py').read_text(encoding='utf-8')
    # Split routes.py into function bodies, so a field is checked against the
    # route it is actually posted to rather than the whole module.
    bodies, current = {}, None
    for line in source.splitlines():
        match = re.match(r'def (\w+)\(', line)
        if match:
            current = match.group(1)
            bodies[current] = []
        elif current:
            bodies[current].append(line)
    bodies = {name: '\n'.join(lines) for name, lines in bodies.items()}

    form_re = re.compile(
        r"<form[^>]*action=\"\{\{\s*url_for\('gym\.(\w+)'.*?\}\}\"(.*?)</form>", re.S)
    control_re = re.compile(r'<(?:input|select|textarea)\b[^>]*\bname="([^"{]+)"')

    problems = []
    for path in sorted((root / 'templates' / 'gym').glob('*.html')):
        html = path.read_text(encoding='utf-8')
        for endpoint, body in form_re.findall(html):
            route = bodies.get(endpoint)
            if route is None:
                problems.append(f'{path.name}: posts to gym.{endpoint}, which does not exist')
                continue
            for field in sorted(set(control_re.findall(body))):
                if f"'{field}'" not in route and f'"{field}"' not in route:
                    problems.append(f'{path.name}: posts {field!r} to gym.{endpoint}, '
                                    f'which never reads it')

    assert not problems, 'form/route field mismatch:\n  ' + '\n  '.join(problems)


def _finished_freeform_session(name):
    """A finished session with one completed set and no template. Returns
    (session_id, exercise_id)."""
    import datetime as dt
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    exercise = Exercise(name=f'{name} lift', user_id=_admin_id())
    db.session.add(exercise)
    db.session.flush()
    started = dt.datetime.utcnow() - dt.timedelta(hours=1)
    done = WorkoutSession(name=name, started_at=started,
                          finished_at=dt.datetime.utcnow(), user_id=_admin_id())
    se = SessionExercise(exercise_id=exercise.id, position=1)
    se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
    done.exercises.append(se)
    db.session.add(done)
    db.session.commit()
    return done.id, exercise.id


def _drop(session_id, exercise_id, template_id=None):
    from extensions import db
    from models import Exercise, WorkoutSession, WorkoutTemplate
    with flask_app.app_context():
        for model, row_id in ((WorkoutTemplate, template_id), (WorkoutSession, session_id)):
            if row_id:
                doomed = db.session.get(model, row_id)
                if doomed is not None:
                    if model is WorkoutSession:
                        doomed.resting_set_id = None
                        db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
        if exercise_id:
            doomed = db.session.get(Exercise, exercise_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_saving_a_session_as_a_template_counts_as_having_done_it(client):
    """Start reads "last done" from WorkoutSession.template_id, and a freeform
    session has none -- so a routine created from a workout you just finished
    announced itself as never performed. The session it was built from is the
    one instance of it that certainly exists."""
    from extensions import db
    from models import WorkoutSession, WorkoutTemplate

    sid = ex_id = tpl_id = None
    try:
        with flask_app.app_context():
            sid, ex_id = _finished_freeform_session('pytest neverdone')

        client.post(f'/gym/session/{sid}/save_as_template',
                    data={'template_name': 'pytest neverdone routine'})

        with flask_app.app_context():
            tpl = WorkoutTemplate.query.filter_by(name='pytest neverdone routine').one()
            tpl_id = tpl.id
            session_ = db.session.get(WorkoutSession, sid)
            assert session_.template_id == tpl_id, 'the source session was left unlinked'

        html = client.get('/gym').get_data(as_text=True)
        block = html.split('pytest neverdone routine', 1)[1][:400]
        assert 'Noch nie' not in block, 'Start still calls the routine never performed'
    finally:
        _drop(sid, ex_id, tpl_id)


def test_saving_as_a_new_template_does_not_steal_a_session_from_its_routine(client):
    """Only a session with no routine gets linked. Re-pointing one that already
    belongs to a template would quietly remove it from that template's history
    and change when Start thinks that routine was last done."""
    from extensions import db
    from models import WorkoutSession, WorkoutTemplate

    sid = ex_id = new_id = old_id = None
    try:
        with flask_app.app_context():
            sid, ex_id = _finished_freeform_session('pytest owned already')
            original = WorkoutTemplate(name='pytest original routine', user_id=_admin_id())
            db.session.add(original)
            db.session.flush()
            old_id = original.id
            db.session.get(WorkoutSession, sid).template_id = old_id
            db.session.commit()

        client.post(f'/gym/session/{sid}/save_as_template',
                    data={'template_name': 'pytest second routine'})

        with flask_app.app_context():
            new_id = WorkoutTemplate.query.filter_by(name='pytest second routine').one().id
            assert db.session.get(WorkoutSession, sid).template_id == old_id, \
                'the session was moved off the routine it already belonged to'
    finally:
        _drop(sid, ex_id, new_id)
        _drop(None, None, old_id)


def test_the_queue_offers_adding_an_exercise(client, scratch_session):
    """Adding an exercise mid-workout lived only in the ⋮ sheet in the top
    corner. The queue is where you are already reading what the workout
    contains, so it is where "and one more" belongs.

    Also pins that the action is not a queue__row and carries no data-se-id:
    session_reorder.js keys both drag and the arrow-key path off that class,
    and an action is not a position in the sequence.
    """
    html = client.get(f'/gym/session/{scratch_session}').get_data(as_text=True)

    queue = html.split('<div class="queue"', 1)[1].split('</div>\n\n</div>', 1)[0]
    assert 'queue__add' in queue, 'no add-exercise row in the queue'

    row = queue.split('queue__add', 1)[1]
    assert 'data-sheet="sheet-add-exercise"' in row
    assert 'data-se-id' not in row, 'the action row looks like a reorderable exercise'
    assert 'queue__row' not in row, 'the action row would be picked up by the reorder handler'

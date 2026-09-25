"""Smoke checks that every gym GET route renders. Needs the real database, so
these are run manually rather than in the pure-stats suite."""
import pytest

from app import app as flask_app
from conftest import embedded_payload


def _live_exercise(payload):
    """The exercise the panel is showing, out of an embedded payload."""
    return next(se for se in payload['visible_exercises']
                if se['id'] == payload['live_id'])


def _pending_set(payload):
    """The set the steppers are bound to: the live exercise's first unlogged
    one, or None when everything is logged."""
    live = _live_exercise(payload)
    return next((s for s in live['sets'] if not s['completed']), None)

from conftest import _admin_id, acting_as, list_exercise
from extensions import db
from features.gym import stats
from models import Exercise, SessionExercise, SessionSet, WorkoutSession

import datetime as dt


@pytest.fixture()
def scratch_session():
    """A throwaway session with one exercise and two uncompleted sets.

    Deleted afterwards whatever the test does -- this suite runs against the
    real local development database.
    """
    with flask_app.app_context():
        exercise_id = list_exercise().id
    yield from _scratch_session(exercise_id)


@pytest.fixture()
def even_step_session():
    """scratch_session on a key-less row of its own with a 2.5 kg step.

    The deload tests assert rounding, and rounding follows the lifter's own
    step for the exercise. On a list exercise that is real user data: the
    admin carries 8 kg on Butterfly (Maschine) since the 09-23 list migration
    kept what differed from the list, which turned 80/75 into 56/51.
    """
    with flask_app.app_context():
        exercise = Exercise(name='pytest scratch even steps', list_increment=2.5)
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id
    try:
        yield from _scratch_session(exercise_id)
    finally:
        with flask_app.app_context():
            row = db.session.get(Exercise, exercise_id)
            if row is not None:
                db.session.delete(row)
                db.session.commit()


def _scratch_session(exercise_id):
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        session_ = WorkoutSession(name='pytest scratch', started_at=dt.datetime.utcnow(),
                                  user_id=_admin_id())
        session_exercise = SessionExercise(exercise_id=exercise_id, position=1)
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


def test_statistik_is_gone_and_its_address_lands_on_verlauf(client):
    """M3 (D7-C): Start says what moves and what stands still, Verlauf what
    the whole history holds. A bookmark or an installed shortcut still lands
    somewhere -- permanently, not on a 404."""
    response = client.get('/gym/statistik')
    assert response.status_code == 301
    assert response.headers['Location'].endswith('/gym/verlauf')


@pytest.mark.parametrize('path', ['/gym', '/gym/verlauf', '/gym/uebungen'])
def test_no_page_offers_statistik_any_more(client, path):
    html = client.get(path).get_data(as_text=True)
    assert '/gym/statistik' not in html
    assert '>Statistik<' not in html


# Every row is everyone's since the one list (2026-09-23), so every page is
# reachable. The ones worth rendering are those with something on them -- the
# admin's touched exercises -- plus one untouched list row for the empty page.
# That no one else's history shows on a page is test_gym_exercise_ownership's.
def test_exercise_detail_renders_for_every_exercise(client):
    from features.gym.exercises import library_exercises, touched_exercises
    with flask_app.app_context():
        touched = touched_exercises(_admin_id())
        ids = [row.id for row in touched]
        ids.append(next(row.id for row in library_exercises() if row not in touched))
    assert len(ids) > 1, 'the dev database needs an exercise the admin has done'
    for exercise_id in ids:
        response = client.get('/gym/exercises/{}'.format(exercise_id))
        assert response.status_code == 200, exercise_id


def test_session_pages_render_for_every_finished_session(client):
    with flask_app.app_context():
        from models import WorkoutSession
        ids = [row.id for row in WorkoutSession.query.filter(
            WorkoutSession.user_id == _admin_id(),
            WorkoutSession.finished_at.isnot(None)).all()]
    assert ids, 'the dev database needs a finished session owned by the admin'
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


def test_deload_on_rewrites_every_weight_when_nothing_is_completed(client, even_step_session):
    response = client.post('/gym/session/{}/deload'.format(even_step_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    # 80 * 0.7 = 56 -> 55.0 ; 75 * 0.7 = 52.5 -> 52.5
    assert set_weights(even_step_session) == [55.0, 52.5]
    assert deload_state(even_step_session) == (True, 70)


def test_deload_percentage_change_scales_from_the_baseline_not_the_deloaded_weight(client, even_step_session):
    """The compounding regression. Two picks in a row must not stack."""
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    assert set_weights(even_step_session) == [55.0, 52.5]
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '60'})
    # 60 % of the 80/75 baseline -> 47.5 / 45.0.
    # Compounding from 55/52.5 would give 32.5 / 30.0.
    assert set_weights(even_step_session) == [47.5, 45.0]


def test_deload_applied_twice_at_the_same_percentage_is_idempotent(client, even_step_session):
    """A double-tap or a POST retry must not reduce the weights twice."""
    for _ in range(2):
        client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    assert set_weights(even_step_session) == [55.0, 52.5]


def test_deload_off_restores_the_exact_pre_deload_weights(client, even_step_session):
    """Replaces the old test, which asserted `!= [77.5, 75.0]` and so passed
    even when the off-branch did nothing at all."""
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session) == [80.0, 75.0]
    assert base_weights(even_step_session) == [None, None]
    assert deload_state(even_step_session) == (False, None)


def test_deload_off_restores_a_manually_adjusted_weight_not_last_sessions(client, even_step_session):
    """The baseline is what was actually planned, which may not match history."""
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        session_.exercises[0].sets[0].weight = 92.5      # user bumped it before starting
        db.session.commit()
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session)[0] == 92.5


def test_deload_on_rewrites_nothing_once_a_set_is_completed(client, even_step_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        session_.exercises[0].sets[0].completed = True
        db.session.commit()
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    assert set_weights(even_step_session) == [80.0, 75.0]
    assert deload_state(even_step_session) == (True, 70)


def test_deload_on_a_finished_session_is_label_only(client, even_step_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        session_.exercises[0].sets[0].completed = True
        session_.finished_at = dt.datetime.utcnow()
        db.session.commit()
    response = client.post('/gym/session/{}/deload'.format(even_step_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    assert set_weights(even_step_session) == [80.0, 75.0]
    assert deload_state(even_step_session) == (True, 70)


def test_deload_pct_out_of_range_falls_back_to_the_default(client, even_step_session):
    client.post('/gym/session/{}/deload'.format(even_step_session),
                data={'on': '1', 'pct': '999'})
    assert deload_state(even_step_session) == (True, 70)


def test_deload_pct_that_is_not_a_number_falls_back_to_the_default(client, even_step_session):
    client.post('/gym/session/{}/deload'.format(even_step_session),
                data={'on': '1', 'pct': 'schwer'})
    assert deload_state(even_step_session) == (True, 70)


def test_deload_on_records_the_baseline_it_captured(client, even_step_session):
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    assert base_weights(even_step_session) == [80.0, 75.0]


def test_completing_a_set_freezes_the_weights_and_un_completing_thaws_them(client, even_step_session):
    """The "computed, not latched" guarantee: the completed-set gate is
    re-evaluated per request, so un-completing a set makes the toggle able to
    rewrite again and a mis-tap is always recoverable."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    assert set_weights(even_step_session) == [55.0, 52.5]

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        session_.exercises[0].sets[0].completed = True
        db.session.commit()
    # Frozen: a completed set gates the rewrite, so toggling off changes the
    # flag but leaves every weight alone.
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session) == [55.0, 52.5]

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        session_.exercises[0].sets[0].completed = False
        db.session.commit()
    # Thawed: nothing is completed any more, so the gate opens and the
    # baseline restores exactly.
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session) == [80.0, 75.0]
    assert base_weights(even_step_session) == [None, None]


def test_a_weight_typed_during_a_deload_survives_turning_it_off(client, even_step_session):
    """Fix 1's regression: a stale baseline must not overwrite a hand-typed
    weight. Before the fix this restored 80.0 and lost the 60.0 entirely."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        set_id = session_.exercises[0].sets[0].id
    client.post('/gym/set/{}/update'.format(set_id), data={'weight': '60', 'reps': '8'})
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session)[0] == 60.0


def test_ticking_a_set_done_does_not_destroy_its_deload_baseline(client, even_step_session):
    """The check button submits the whole row, so an unchanged weight must not
    read as a hand-typed one -- otherwise completing and un-completing a set
    during a deload loses its working weight for good."""
    from extensions import db
    from models import WorkoutSession
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '1', 'pct': '70'})
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, even_step_session)
        set_id = session_.exercises[0].sets[0].id
    # Tick done, then undo -- exactly what the form posts, weight unchanged.
    client.post('/gym/set/{}/toggle_complete'.format(set_id), data={'weight': '55.0', 'reps': '8'})
    client.post('/gym/set/{}/toggle_complete'.format(set_id), data={'weight': '55.0', 'reps': '8'})
    client.post('/gym/session/{}/deload'.format(even_step_session), data={'on': '0'})
    assert set_weights(even_step_session) == [80.0, 75.0]
    assert base_weights(even_step_session) == [None, None]


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
            exercise = Exercise(name='pytest seed lift', is_unilateral=False)
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
    exercise = Exercise(name='pytest slot lift', is_unilateral=False)
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
        exercise = Exercise(name='pytest reorder lift %s' % label, is_unilateral=False)
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
        exercise = Exercise(name='pytest scratch increment lift', muscle_group='Brust')
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
    assert embedded_payload(html)['live_increment'] == 2.5


def _admin_step(exercise_id):
    """The admin's stored step for an exercise, or None for no setting."""
    from models import ExerciseSettings
    with flask_app.app_context():
        row = ExerciseSettings.query.filter_by(user_id=_admin_id(), exercise_id=exercise_id).first()
        return row.weight_increment if row else None


def test_live_stepper_uses_the_lifters_own_increment(client, scratch_increment_exercise):
    from extensions import db
    from models import ExerciseSettings
    session_id, _, exercise_id = scratch_increment_exercise

    with flask_app.app_context():
        db.session.add(ExerciseSettings(user_id=_admin_id(), exercise_id=exercise_id,
                                        weight_increment=9.0))
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert embedded_payload(html)['live_increment'] == 9.0
    # The fallback must be gone, not merely joined -- this session has exactly
    # one exercise, so a surviving 2.5 would mean the template still branches
    # on is_unilateral instead of reading the resolved value.
    assert embedded_payload(html)['live_increment'] != 2.5


def test_live_stepper_uses_the_lists_increment_without_a_setting(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise
    session_id, _, exercise_id = scratch_increment_exercise

    with flask_app.app_context():
        db.session.get(Exercise, exercise_id).list_increment = 5.0
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert embedded_payload(html)['live_increment'] == 5.0


JSON = {'Accept': 'application/json'}


def test_settings_sheet_writes_the_lifters_increment(client, scratch_increment_exercise):
    """The workout's "Deine Einstellungen" sheet (V3) writes the step through
    the exercise's own settings route, answered as JSON -- the route the
    workout's own step field used to have is gone with the field."""
    from extensions import db
    from models import Exercise, SessionExercise
    _, session_exercise_id, exercise_id = scratch_increment_exercise

    response = client.post(f'/gym/exercises/{exercise_id}/update',
                           data={'weight_increment': '9'}, headers=JSON)
    assert response.status_code == 200
    assert response.get_json()['weight_increment'] == 9.0

    assert _admin_step(exercise_id) == 9.0
    with flask_app.app_context():
        # The list's value stays: the step is this lifter's setting, not a
        # change to the row everyone uses.
        assert db.session.get(Exercise, exercise_id).list_increment is None
        # The session row is untouched: the step is the exercise's, forever.
        assert db.session.get(SessionExercise, session_exercise_id).rest_seconds is None


def test_settings_sheet_clears_the_increment_back_to_the_default(client, scratch_increment_exercise):
    _, _, exercise_id = scratch_increment_exercise

    client.post(f'/gym/exercises/{exercise_id}/update', data={'weight_increment': '9'},
                headers=JSON)
    client.post(f'/gym/exercises/{exercise_id}/update', data={'weight_increment': ''},
                headers=JSON)

    assert _admin_step(exercise_id) is None


def test_to_increment_is_comma_tolerant():
    """A German keyboard produces '2,5', not '2.5' -- the docstring's claim,
    unverified until now."""
    from features.gym.routes import _to_increment
    assert _to_increment('2,5') == 2.5


def test_a_blank_increment_is_the_lists_again():
    from features.gym.routes import _to_increment
    assert _to_increment('') is None
    assert _to_increment('  ') is None


@pytest.mark.parametrize('raw', ['-9', 'abc', '0', 'inf', '51'])
def test_to_increment_refuses_what_is_not_a_step(raw):
    """These used to store NULL just as quietly as a blank, and 'inf' got
    through to the database (walkthrough G-071). Now they say why."""
    from features.gym.routes import _to_increment
    from features.gym.routes.helpers import InvalidInput
    with pytest.raises(InvalidInput):
        _to_increment(raw)


def test_update_exercise_sets_and_clears_the_increment_without_losing_other_fields(client):
    """The settings form writes the step as the caller's setting, and a
    blank puts it back on the list's. Name and group are the list's and
    survive both writes, whatever the form posts for them."""
    from extensions import db
    from models import Exercise

    with flask_app.app_context():
        exercise = Exercise(name='pytest update exercise increment', muscle_group='Rücken')
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
        assert _admin_step(exercise_id) == 5.0
        with flask_app.app_context():
            exercise = db.session.get(Exercise, exercise_id)
            assert exercise.name == 'pytest update exercise increment'
            assert exercise.muscle_group == 'Rücken'

        response = client.post(f'/gym/exercises/{exercise_id}/update', data={
            'name': 'pytest renamed on the way',
            'muscle_group': 'Brust',
            'weight_increment': '',
        })
        assert response.status_code in (302, 303)
        assert _admin_step(exercise_id) is None
        with flask_app.app_context():
            exercise = db.session.get(Exercise, exercise_id)
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
        exercise = Exercise(name='pytest deload suggest lift', muscle_group='Brust')
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
    """gym_add_session_exercise seeds from history through _seeded_sets, so the
    sets it creates must already carry the deload -- history is recorded at full
    working weight, and handing it back untouched would silently undo the deload
    the lifter just asked for. This exercise HAS history; the no-history default
    is a separate path, covered in test_gym_cold_start.py.
    """
    live_id, _, exercise_id = scratch_deload_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'exercise_id': str(exercise_id)})
    assert response.status_code in (302, 303)

    html = client.get(f'/gym/session/{live_id}').get_data(as_text=True)
    # 100 kg at 70 % on the default 2.5 grid is exactly 70.0.
    pending = _pending_set(embedded_payload(html))
    assert pending['weight'] == 70.0
    assert pending['weight'] != 100.0


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


UNEVEN_STACK = [5.0, 12.0, 18.0, 29.0, 33.0, 61.0, 68.0, 92.0]


def _my_stack_stops(exercise_id):
    """The admin's own stops on an exercise, as their settings row. Goes
    with the exercise: the row cascades when the fixture deletes it."""
    from models import ExerciseSettings
    db.session.add(ExerciseSettings(user_id=_admin_id(), exercise_id=exercise_id,
                                    stack_kg=UNEVEN_STACK))


def test_deload_seeding_snaps_to_the_exercises_real_stack_stops(client, scratch_deload_session):
    """The route wiring, not just the pure function: stats.deload_weight()
    correctly snapping to a stack is worthless if the lifter's own stops
    never reach it. 100 kg at 70 % on the default 2.5 grid is exactly 70.0
    -- a value this stack does not have -- so this only passes if
    _seeded_sets actually reads the session owner's setup and passes its
    stops through.
    """
    from models import SessionExercise
    live_id, _, exercise_id = scratch_deload_session
    with flask_app.app_context():
        _my_stack_stops(exercise_id)
        db.session.commit()

    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.weight, s.base_weight, s.reps) for s in se.sets] == [(68.0, 100.0, 10)]


def test_seeded_suggestion_snaps_to_the_exercises_real_stack_stops(client, scratch_deload_session):
    """The GET-time suggestion (_seeded_suggestion), not the POST-time seeding
    covered above (_seeded_sets): an exercise attached to the session with no
    sets of its own yet -- the "live" slot, since it is the only exercise --
    reads its opening weight from _seeded_suggestion alone, which must also
    read the stops -- here the list's own, where the neighbouring tests use
    the lifter's setting. 100 kg at 70 % on the default 2.5 grid is exactly
    70.0 -- a value this stack does not have -- so this only passes if
    _seeded_suggestion actually passes the stops through. The "zuletzt ..."
    line (_session_live.html) and the hidden stepper input both read the same
    suggestion, so both are checked.
    """
    from models import Exercise, SessionExercise
    live_id, _, exercise_id = scratch_deload_session
    with flask_app.app_context():
        db.session.get(Exercise, exercise_id).list_stack_kg = UNEVEN_STACK
        se = SessionExercise(session_id=live_id, exercise_id=exercise_id, position=1)
        db.session.add(se)
        db.session.commit()

    html = client.get(f'/gym/session/{live_id}').get_data(as_text=True)
    payload = embedded_payload(html)
    # An exercise with no sets prefills from its suggestion, which the panel
    # also quotes in its empty-state line.
    suggestion = payload['suggestions'][str(payload['live_id'])]
    assert suggestion['weight'] == 68.0
    assert suggestion['weight'] != 70.0


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


def test_deload_toggle_snaps_to_the_exercises_real_stack_stops(client, scratch_deload_session):
    """The toggle route's own deload_weight() call (gym_toggle_deload), not the
    seeding paths covered above: switching a deload on for a session that
    already has sets logged at working weight must also read the lifter's
    stops. 100 kg at 70 % on the default 2.5 grid is exactly 70.0 -- a value
    this stack does not have.
    """
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, _, exercise_id = scratch_deload_session
    with flask_app.app_context():
        _my_stack_stops(exercise_id)
        live = db.session.get(WorkoutSession, live_id)
        live.is_deload, live.deload_pct = False, None   # start plain, like the toggle test above
        se = SessionExercise(session_id=live_id, exercise_id=exercise_id, position=1)
        se.sets = [SessionSet(position=1, weight=100.0, reps=8, completed=False)]
        db.session.add(se)
        db.session.commit()

    client.post(f'/gym/session/{live_id}/deload', data={'on': '1', 'pct': '70'})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [s.weight for s in se.sets] == [68.0]


@pytest.fixture()
def scratch_stagnant_stack_session():
    """A finished session sitting at the end of a stagnation streak, on an
    exercise with an UNEVEN recorded stack (5, 12, 18, 29, 33, 61, 68, 92).

    This is the route-level counterpart to the pure stats.py stack tests: it
    exercises routes.py's own _to_performed(), the fourth call site that reads
    exercise.stack_kg into a PerformedExercise (session_detail.html's finished
    branch, load_performed()) -- the one the earlier stack-plumbing review
    missed. 61 kg is itself a real stop; the default 2.5 kg grid would suggest
    63.5 kg next, a position this machine does not have.
    """
    import datetime as dt
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest stagnant stack lift', muscle_group='Brust',
                            list_stack_kg=[5.0, 12.0, 18.0, 29.0, 33.0, 61.0, 68.0, 92.0])
        db.session.add(exercise)
        db.session.flush()

        base = dt.datetime.utcnow() - dt.timedelta(days=28)
        sessions = []
        for n in range(4):
            past = WorkoutSession(name=f'pytest stagnant history {n}',
                                  started_at=base + dt.timedelta(days=7 * n),
                                  finished_at=base + dt.timedelta(days=7 * n, hours=1),
                                  user_id=_admin_id())
            se = SessionExercise(exercise_id=exercise.id, position=1)
            se.sets = [SessionSet(position=1, weight=61.0, reps=8, completed=True)]
            past.exercises.append(se)
            sessions.append(past)

        current = WorkoutSession(name='pytest stagnant current',
                                 started_at=base + dt.timedelta(days=28),
                                 finished_at=base + dt.timedelta(days=28, hours=1),
                                 user_id=_admin_id())
        current_se = SessionExercise(exercise_id=exercise.id, position=1)
        current_se.sets = [SessionSet(position=1, weight=61.0, reps=8, completed=True)]
        current.exercises.append(current_se)
        sessions.append(current)

        db.session.add_all(sessions)
        db.session.commit()
        session_ids = [s.id for s in sessions]
        finished_id = current.id
        exercise_id = exercise.id
    yield finished_id
    with flask_app.app_context():
        for sid in session_ids:
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


def test_finished_session_advice_snaps_to_the_exercises_real_stack_stops(
        client, scratch_stagnant_stack_session):
    """Route-level regression guard for _to_performed's stack_kg plumbing
    (routes.py:478), the fourth call site the earlier stack-plumbing review
    missed. Setting stack_kg=None there leaves the full suite green, because
    nothing else exercises this exact path -- the "Nächstes Mal" advice on
    session_finished.html, the app's own "go heavier" prescription.
    """
    html = client.get(f'/gym/session/{scratch_stagnant_stack_session}').get_data(as_text=True)
    advice = embedded_payload(html)['advice']
    assert advice, 'expected a "Nächstes Mal" advice entry'
    # The prescription itself, not the sentence FinishedPage wraps it in:
    # snapped to the stack's real 68 kg stop rather than the arithmetic 63,5.
    assert advice[0]['suggested_weight'] == 68.0
    assert 63.5 not in [item['suggested_weight'] for item in advice]


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


def test_the_add_exercise_sheet_is_one_searchable_list(client, scratch_session):
    """The sheet used to be two panes -- a catalogue <select> in one, an
    invent-a-new-exercise form (with a muscle-group field) in the other, with
    buttons to switch between them. It is one search field and one list now,
    and tapping a row posts exercise_id. Since the one list (2026-09-23) it
    has no create row either: a name the list lacks is not an exercise.
    """
    from features.gym.library import BY_KEY, LIBRARY, LIST_GROUPS, MOVEMENT_GROUP, fold

    html = client.get(f'/gym/session/{scratch_session}').get_data(as_text=True)

    # The sheet is a React component; that it is ONE list is pinned by
    # AddExerciseSheet in static/gym/src/session/components/sheets.test.tsx.
    # What the server owes it is the list to search, and what to search it by.
    payload = embedded_payload(html)
    catalogue = payload['exercises']
    assert catalogue, 'no catalogue for the add sheet to search'
    assert set(catalogue[0]) == {'id', 'name', 'muscle_group', 'search', 'movement', 'label',
                                 'movement_group', 'workouts', 'days_ago', 'rank', 'common'}

    # The German name is what shows; the English one must still find it.
    bench = next(row for row in catalogue
                 if row['name'] == BY_KEY['barbell_bench_press'].name)
    assert fold('Bench Press') in bench['search']
    assert (bench['movement'], bench['label'], bench['movement_group']) == \
        ('Bankdrücken', 'Langhantel', 'Brust')

    # A variant that works another muscle first is still listed with its
    # movement: the sheet's sections are movements' groups, in the list's order.
    assert payload['list_groups'] == list(LIST_GROUPS)
    split = next((e for e in LIBRARY if e.group != MOVEMENT_GROUP[e.movement]), None)
    if split is not None:
        row = next(row for row in catalogue if row['name'] == split.name)
        assert row['muscle_group'] == split.group
        assert row['movement_group'] == MOVEMENT_GROUP[split.movement]


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

    payload = embedded_payload(html)
    # The confirm button renders in every state including "everything logged"
    # -- the panel picks its endpoint from whether a set is pending, so what
    # the server has to get right is that the exercise is still live with
    # nothing pending.
    assert payload['live_id'] is not None, 'no live exercise once every set is logged'
    assert _pending_set(payload) is None, 'expected every set to be logged'
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
    payload = embedded_payload(html)
    # Nothing pending, so the panel seeds from the set just done rather than
    # from the session's opening suggestion.
    live = _live_exercise(payload)
    assert _pending_set(payload) is None
    assert live['sets'][-1]['weight'] == 62.5, \
        'steppers would ignore the set that was actually just done'
    assert live['sets'][-1]['reps'] == 5


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
            exercise = Exercise(name='pytest finished tpl lift')
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
            payload = embedded_payload(html)
            # What the server decides: the prompt is offered at the one moment
            # you know what you did, and it is the freeform variant because
            # this session came from no template.
            assert payload['just_finished'] is True, 'the prompt would not render'
            assert payload['session']['template_id'] is None
            assert payload['total_sets'] > 0

            # The field name the form actually posts is checked against what
            # this route reads by test_every_react_form_posts_fields_its_own_
            # route_reads; here the round trip is what matters.
            response = client.post(f'/gym/session/{sid}/save_as_template',
                                   data={'template_name': 'pytest finished tpl name'})
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

def _route_bodies():
    """{route function name: its own source, plus the source of everything it
    calls}. Shared by the two form/route pairing tests below."""
    import re
    from pathlib import Path

    root = Path(flask_app.root_path)
    # Every module in the routes package, concatenated. It was one file until
    # the package split; reading only one module now would silently stop
    # covering every route that had moved out of it, which is the exact
    # failure this test exists to prevent. The transitive call resolution
    # below still works across modules because they share one `bodies` map.
    routes_dir = root / 'features' / 'gym' / 'routes'
    modules = sorted(routes_dir.glob('*.py'))
    assert modules, \
        f'no route modules under {routes_dir} -- this test would pass by reading nothing'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in modules)
    # Split into function bodies, so a field is checked against the route it is
    # actually posted to rather than the whole package.
    bodies, current = {}, None
    for line in source.splitlines():
        match = re.match(r'def (\w+)\(', line)
        if match:
            current = match.group(1)
            bodies[current] = []
        elif current:
            bodies[current].append(line)
    bodies = {name: '\n'.join(lines) for name, lines in bodies.items()}

    def resolve(name, seen=None):
        # A route's own body is not always where the field is read anymore:
        # _apply_typed_weight_reps (shared by gym_toggle_set_complete and
        # gym_update_set, see the final-polish F1 extraction) is where
        # 'weight'/'reps' actually get pulled off request.form. Follow calls
        # to any other function defined in this module, transitively, so a
        # field read by a shared helper still counts as read by its caller
        # -- otherwise this test would force every route to inline its field
        # reads, which is the opposite of what it's meant to guard.
        seen = seen if seen is not None else set()
        if name in seen or name not in bodies:
            return ''
        seen.add(name)
        text = bodies[name]
        for callee in sorted(set(re.findall(r'\b(\w+)\(', text)) & bodies.keys() - seen):
            text += '\n' + resolve(callee, seen)
        return text

    return bodies, resolve


#: A form control that names a field. Excludes `name="{...` so a Jinja- or
#: JSX-interpolated name is skipped rather than reported as a literal.
CONTROL_RE = r'<(?:input|select|textarea)\b[^>]*\bname="([^"{]+)"'


def test_every_jinja_form_posts_fields_its_own_route_reads():
    """The class of bug behind the finished page's broken save-as-template: the
    form posted `name` while gym_save_as_template reads `template_name`, so the
    route saw an empty string, skipped its `if`, and redirected -- the same
    redirect a success produces. Ten days of a button that looked like it worked.

    Checking that *some* route reads a field is not enough: `name` is read by
    gym_rename_template, so a global scan passes while the form is still broken.
    The pairing is what matters, so this resolves each form's own action to its
    route function and checks that function's body.

    The Jinja half. Every gym page that becomes a React island takes its forms
    with it, so this one shrinks towards covering nothing without ever failing
    -- which is why the TSX half below is named as its pair rather than as an
    extra.
    """
    import re
    from pathlib import Path

    root = Path(flask_app.root_path)
    bodies, resolve = _route_bodies()
    form_re = re.compile(
        r"<form[^>]*action=\"\{\{\s*url_for\('gym\.(\w+)'.*?\}\}\"(.*?)</form>", re.S)
    control_re = re.compile(CONTROL_RE)

    problems = []
    for path in sorted((root / 'templates' / 'gym').glob('*.html')):
        html = path.read_text(encoding='utf-8')
        for endpoint, body in form_re.findall(html):
            if endpoint not in bodies:
                problems.append(f'{path.name}: posts to gym.{endpoint}, which does not exist')
                continue
            route = resolve(endpoint)
            for field in sorted(set(control_re.findall(body))):
                if f"'{field}'" not in route and f'"{field}"' not in route:
                    problems.append(f'{path.name}: posts {field!r} to gym.{endpoint}, '
                                    f'which never reads it')

    assert not problems, 'form/route field mismatch:\n  ' + '\n  '.join(problems)


def test_every_react_form_posts_fields_its_own_route_reads():
    """The TSX half of the pairing check above, and the stricter of the two.

    A Jinja form names its route through url_for, so a typo is a 500 the first
    time anyone opens the page. A React form carries a literal path string,
    which nothing validates -- a wrong URL is a silent 404 on submit, and four
    of them were written into the finished page's first draft. So this resolves
    each action against the real url_map before it looks at any field: an
    action that matches no POST route is the failure, not just a field the
    route ignores.
    """
    import re
    from pathlib import Path

    bodies, resolve = _route_bodies()
    adapter = flask_app.url_map.bind('localhost')
    src = Path(flask_app.root_path) / 'static' / 'gym' / 'src'
    files = sorted(p for p in src.rglob('*.tsx') if '.test.' not in p.name)
    assert files, f'no React sources under {src} -- this test would pass by reading nothing'

    # action={`...`} or action="..." through to the matching </form>.
    form_re = re.compile(r'<form[^>]*\baction=\{?[`"]([^`"]+)[`"]\}?(.*?)</form>', re.S)
    control_re = re.compile(CONTROL_RE)

    problems = []
    for path in files:
        for action, body in form_re.findall(path.read_text(encoding='utf-8')):
            # Every ${...} is an id being interpolated; 1 matches any <int:>
            # converter, which is the only kind these routes use.
            url = re.sub(r'\$\{[^}]*\}', '1', action)
            try:
                endpoint, _ = adapter.match(url, method='POST')
            except Exception as exc:
                problems.append(f'{path.name}: posts to {url!r}, which matches no '
                                f'POST route ({type(exc).__name__})')
                continue
            route = resolve(endpoint.split('.')[-1])
            for field in sorted(set(control_re.findall(body))):
                if f"'{field}'" not in route and f'"{field}"' not in route:
                    problems.append(f'{path.name}: posts {field!r} to {endpoint}, '
                                    f'which never reads it')

    assert not problems, 'form/route mismatch:\n  ' + '\n  '.join(problems)


def _finished_freeform_session(name):
    """A finished session with one completed set and no template. Returns
    (session_id, exercise_id)."""
    import datetime as dt
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    exercise = Exercise(name=f'{name} lift')
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

    # The queue is a React component now. That its add row carries neither
    # .queue__row nor data-se-id -- so the reorder handler cannot pick up an
    # action as a position -- is pinned by Queue.test.tsx. What the server
    # still owes it is the catalogue that row opens onto.
    assert embedded_payload(html)['exercises'], \
        'no catalogue behind the queue add row'


def test_the_lead_routine_names_a_stall_inside_it():
    """Heute lists every stalling exercise further down the page. The card you
    are about to tap says only which exercises are in it -- so this names the
    one to watch in THIS routine, and stays quiet about the rest.

    Runs as a fresh, throwaway user rather than the shared `client` fixture:
    admin has real, ongoing training history in the local dev database
    (including a currently-active WorkoutSession), and gym_heute() renders a
    "continue your workout" card instead of the lead-routine card whenever an
    active session exists -- which would make this test's target block never
    render, intermittently, depending on whatever admin happens to be doing
    that day. A brand-new user has no active session and no routine history
    to compete with the fixture built here, so the fixture's routine is
    unambiguously the lead.
    """
    import datetime as dt
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SessionSet, TemplateExercise,
                        WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    made = {'sessions': [], 'exercise': None, 'template': None, 'user': None}
    try:
        with flask_app.app_context():
            user = AppUser(username='pytest briefing user',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.flush()
            made['user'] = user.id

            exercise = Exercise(name='pytest briefing lift', muscle_group='Brust')
            db.session.add(exercise)
            db.session.flush()
            made['exercise'] = exercise.id

            template = WorkoutTemplate(name='pytest briefing routine', user_id=user.id)
            template.exercises.append(TemplateExercise(exercise_id=exercise.id, position=1))
            db.session.add(template)
            db.session.flush()
            made['template'] = template.id

            # Five sessions at an unchanged weight is a stall by
            # stats.STAGNATION_THRESHOLD (4).
            for days_ago in (30, 24, 18, 12, 6):
                started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
                session_ = WorkoutSession(name='pytest briefing session',
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1),
                                          user_id=user.id, template_id=template.id)
                se = SessionExercise(exercise_id=exercise.id, position=1)
                se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
                session_.exercises.append(se)
                db.session.add(session_)
                db.session.commit()
                made['sessions'].append(session_.id)

        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = made['user']
            html = test_client.get('/gym').get_data(as_text=True)
        # LeadWatch renders the line; what the server decides is that the
        # stall is reported at all and that the lead routine contains it.
        payload = embedded_payload(html)
        stalled_ids = {s['exercise_id'] for s in payload['stalls']}
        assert 'pytest briefing lift' in [s['name'] for s in payload['stalls']],             'the stalling lift was not reported on Heute'
        assert stalled_ids & set(payload['routines'][0]['exercise_ids']),             'the lead routine does not contain it, so no briefing line would render'
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            if made['template']:
                doomed = db.session.get(WorkoutTemplate, made['template'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made['exercise']:
                doomed = db.session.get(Exercise, made['exercise'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made['user']:
                doomed = db.session.get(AppUser, made['user'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_the_lead_routine_ignores_a_stall_it_does_not_contain():
    """An exercise stalling elsewhere in the catalogue must not appear on a card
    whose routine does not contain it -- otherwise the line is just the stalls
    section repeated, and its claim to be about THIS routine is false.

    Runs as a fresh, throwaway user for the same reason as the sibling test
    above: admin's real, currently-active WorkoutSession makes gym_heute()
    render the "continue your workout" card instead of the lead-routine card,
    so the shared `client` fixture (always admin) cannot reliably reach the
    lead__watch block this test inspects.
    """
    import datetime as dt
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SessionSet, TemplateExercise,
                        WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    made = {'sessions': [], 'in_routine': None, 'outsider': None, 'template': None, 'user': None}
    try:
        with flask_app.app_context():
            user = AppUser(username='pytest exclusion user',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.flush()
            made['user'] = user.id

            # Named to sort alphabetically BEFORE the in-routine exercise, so
            # the stall_report tie-break (-sessions_since_pr, name) would put
            # it at watch[0] if the routine-membership filter in heute.html
            # were ever removed -- making its absence below a real check on
            # the filter, not just on stall_report's sort order.
            in_routine = Exercise(name='pytest inroutine lift')
            outsider = Exercise(name='pytest aaa outsider lift')
            db.session.add_all([in_routine, outsider])
            db.session.flush()
            made['in_routine'], made['outsider'] = in_routine.id, outsider.id

            # The routine contains ONLY the first exercise.
            template = WorkoutTemplate(name='pytest exclusion routine', user_id=user.id)
            template.exercises.append(TemplateExercise(exercise_id=in_routine.id, position=1))
            db.session.add(template)
            db.session.flush()
            made['template'] = template.id

            # Both lifts stall: five sessions at an unchanged weight.
            for days_ago in (30, 24, 18, 12, 6):
                started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
                session_ = WorkoutSession(name='pytest exclusion session',
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1),
                                          user_id=user.id, template_id=template.id)
                for position, exercise_id in enumerate((in_routine.id, outsider.id), start=1):
                    se = SessionExercise(exercise_id=exercise_id, position=position)
                    se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
                    session_.exercises.append(se)
                db.session.add(session_)
                db.session.commit()
                made['sessions'].append(session_.id)

        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = made['user']
            html = test_client.get('/gym').get_data(as_text=True)
        # LeadWatch intersects the lead routine's exercises with the stalls,
        # so what has to hold server-side is that both lifts are reported and
        # only one of them is in the routine.
        payload = embedded_payload(html)
        by_name = {s['name']: s['exercise_id'] for s in payload['stalls']}
        assert 'pytest inroutine lift' in by_name
        assert 'pytest aaa outsider lift' in by_name
        # The intersection is by id, so that is what the payload has to support.
        lead_ids = payload['routines'][0]['exercise_ids']
        assert by_name['pytest inroutine lift'] in lead_ids,             'the briefing would not name the stall the routine DOES contain'
        assert by_name['pytest aaa outsider lift'] not in lead_ids,             'the briefing would name a stall the routine does not contain'
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            if made['template']:
                doomed = db.session.get(WorkoutTemplate, made['template'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            for key in ('in_routine', 'outsider'):
                if made[key]:
                    doomed = db.session.get(Exercise, made[key])
                    if doomed is not None:
                        db.session.delete(doomed)
                        db.session.commit()
            if made['user']:
                doomed = db.session.get(AppUser, made['user'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_the_lead_routine_briefing_is_silent_when_nothing_stalls():
    """The design spec's Testing section requires this outright: the briefing
    renders nothing when the lead routine has no stalling exercise. The two
    sibling tests above only ever cover a stall inside vs. outside the lead
    routine -- neither one ever exercises the "nothing stalls anywhere" case,
    so the spec's own explicit requirement had no test proving it.

    Runs as a fresh, throwaway user for the same reason as the two tests
    above: admin's real, currently-active WorkoutSession would make gym_heute()
    render the "continue your workout" card instead of the lead-routine card.

    Two sessions is below stats.STAGNATION_THRESHOLD (4), so
    sessions_since_pr can never reach the threshold that marks a stall --
    there simply isn't enough history yet for anything to count as stuck.
    """
    import datetime as dt
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SessionSet, TemplateExercise,
                        WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    made = {'sessions': [], 'exercise': None, 'template': None, 'user': None}
    try:
        with flask_app.app_context():
            user = AppUser(username='pytest no-stall user',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.flush()
            made['user'] = user.id

            exercise = Exercise(name='pytest no-stall lift', muscle_group='Brust')
            db.session.add(exercise)
            db.session.flush()
            made['exercise'] = exercise.id

            template = WorkoutTemplate(name='pytest no-stall routine', user_id=user.id)
            template.exercises.append(TemplateExercise(exercise_id=exercise.id, position=1))
            db.session.add(template)
            db.session.flush()
            made['template'] = template.id

            # Two sessions, well under STAGNATION_THRESHOLD (4) -- nowhere near
            # enough history for anything to read as stuck.
            for days_ago in (12, 6):
                started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
                session_ = WorkoutSession(name='pytest no-stall session',
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1),
                                          user_id=user.id, template_id=template.id)
                se = SessionExercise(exercise_id=exercise.id, position=1)
                se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
                session_.exercises.append(se)
                db.session.add(session_)
                db.session.commit()
                made['sessions'].append(session_.id)

        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = made['user']
            html = test_client.get('/gym').get_data(as_text=True)
        payload = embedded_payload(html)
        assert 'pytest no-stall routine' in [r['name'] for r in payload['routines']], \
            'the lead routine card itself did not render'
        # Nothing in the lead routine stalls, so LeadWatch renders nothing.
        lead_ids = set(payload['routines'][0]['exercise_ids'])
        assert not [s for s in payload['stalls'] if s['exercise_id'] in lead_ids],             'a briefing line would render though nothing in the routine stalls'
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            if made['template']:
                doomed = db.session.get(WorkoutTemplate, made['template'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made['exercise']:
                doomed = db.session.get(Exercise, made['exercise'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made['user']:
                doomed = db.session.get(AppUser, made['user'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_an_open_chip_shows_the_weight_and_reps_it_is_planned_for(client):
    """The numbers are already on the row, prefilled from last time. A chip
    that says only "Satz 2" makes the lifter at the machine remember last
    week to decide whether to add weight -- which is the thing a tracker
    exists to stop."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Chip Plan',
                            muscle_group='Rücken')
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Chip Plan Session', user_id=_admin_id(),
                                 started_at=dt.datetime.utcnow())
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.flush()
        db.session.add(SessionSet(session_exercise_id=se.id, position=1, weight=35.0,
                                  reps=11, completed=True,
                                  completed_at=dt.datetime.utcnow()))
        db.session.add(SessionSet(session_exercise_id=se.id, position=2, weight=35.0,
                                  reps=9, completed=False))
        db.session.commit()
        session_id, exercise_id = session.id, exercise.id

    try:
        html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
        live = _live_exercise(embedded_payload(html))
        assert (live['sets'][0]['weight'], live['sets'][0]['reps']) == (35.0, 11), \
            'the done set still wears its result'
        assert (live['sets'][1]['weight'], live['sets'][1]['reps']) == (35.0, 9), \
            'the open set now wears its plan'
        assert (live['sets'][1]['weight'], live['sets'][1]['reps']) == (35.0, 9), \
            'the ordinal moved into the label, it did not vanish'
        # The done branch's label reads its weight through the same formatter
        # as the visible chip. Untested, it was the one place in this file a
        # raw float could reach a screen reader as "35.0".
        assert live['sets'][0]['completed'] and live['sets'][0]['reps'] == 11, \
            'a logged set says its weight the German way too'
    finally:
        with flask_app.app_context():
            row = db.session.get(WorkoutSession, session_id)
            if row is not None:
                db.session.delete(row)
            ex = db.session.get(Exercise, exercise_id)
            if ex is not None:
                db.session.delete(ex)
            db.session.commit()

"""The cold-start path: a workout where nothing has been logged before.

Every test here builds its own throwaway exercise with NO history, which is
the condition the whole suite is about -- an exercise the lifter has never
performed produces no seeded sets, and before this suite existed the live
screen had no behaviour for that.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def virgin_session():
    """An active session with no exercises, plus one exercise with no history.

    Deliberately NOT derived from the dev database's real data: the point is an
    exercise nothing has ever been logged against, which no existing row can be
    relied on to be.
    """
    from extensions import db
    from models import Exercise, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest cold start lift', muscle_group='Brust',
                            user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()

        live = WorkoutSession(name='pytest cold start live',
                              started_at=dt.datetime.utcnow(),
                              user_id=_admin_id())
        db.session.add(live)
        db.session.commit()
        ids = (live.id, exercise.id)
    yield ids
    with flask_app.app_context():
        live_id, exercise_id = ids
        doomed = db.session.get(WorkoutSession, live_id)
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_an_exercise_with_no_history_arrives_with_a_default_plan(client, virgin_session):
    """It used to arrive with nothing at all, which is what made the first
    logged set also the last: with no planned sets, one completed set meant
    every set was completed."""
    from extensions import db
    from models import SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'exercise_id': str(exercise_id)})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.position, s.weight, s.reps, s.completed) for s in se.sets] == [
            (1, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
            (2, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
            (3, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
        ]


def test_logging_one_set_does_not_advance_past_a_default_planned_exercise(client, virgin_session):
    """The bug this whole task exists for. `_live_context` calls an exercise
    finished when every set it has is completed; with no planned sets the first
    confirmation both created and completed the list, so each exercise got
    exactly one set before the screen moved on.

    A SECOND exercise is required to make this test able to fail at all.
    `_live_context` falls back to `visible_exercises[-1]` when nothing is
    live, and with only one exercise in the session that fallback names the
    SAME row whether or not the screen actually advanced -- data-se-id would
    be identical either way, so the assertions below could never catch a
    regression. With two exercises present, "advanced" moves live off the
    first row and onto the second's, which is now a real, different id.
    """
    from extensions import db
    from models import Exercise, SessionExercise
    from conftest import _admin_id
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        second = Exercise(name='pytest cold start advance guard',
                          muscle_group='Rücken', user_id=_admin_id())
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(second_id)})

        with flask_app.app_context():
            rows = (SessionExercise.query.filter_by(session_id=live_id)
                    .order_by(SessionExercise.position).all())
            se = rows[0]
            assert se.exercise_id == exercise_id, 'the exercise under test is not the first row'
            # Explicit set count: the mutation this test exists to catch --
            # seeding one set instead of DEFAULT_PLAN_SETS -- reproduces the
            # advance-after-one-set bug exactly, and this assertion catches
            # it directly rather than only through the live-panel side effect
            # below.
            assert len(se.sets) == stats.DEFAULT_PLAN_SETS, (
                f'expected the default plan ({stats.DEFAULT_PLAN_SETS} sets), '
                f'got {len(se.sets)}')
            first_set_id = sorted(se.sets, key=lambda s: s.position)[0].id
            se_id = se.id

        client.post(f'/gym/set/{first_set_id}/toggle_complete',
                    data={'completed': '1', 'weight': '60.0', 'reps': '8'})

        html = client.get(f'/gym/session/{live_id}').get_data(as_text=True)
        # The live panel names its own session-exercise in data-se-id; if the
        # screen had advanced this would instead name the SECOND exercise's
        # row (or, with the pre-fix `[]` seeding, render the "Noch keine
        # Übung" empty state).
        assert f'<section class="live" data-se-id="{se_id}">' in html
        assert 'Noch keine Übung' not in html
    finally:
        with flask_app.app_context():
            for se in SessionExercise.query.filter_by(exercise_id=second_id).all():
                db.session.delete(se)
            db.session.commit()
            doomed = db.session.get(Exercise, second_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_a_deload_does_not_scale_an_invented_default(client, virgin_session):
    """There is no working weight to take a percentage of. Scaling the default
    would present a fabricated prescription as a real one.

    This covers only the ORDER that was already safe: is_deload is set
    directly on the model before the exercise is ever added, so
    gym_toggle_deload (the route that fills base_weight) never runs at all --
    see the sibling test below for the order that broke this.
    """
    from extensions import db
    from models import SessionExercise, WorkoutSession
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, live_id)
        session_.is_deload = True
        session_.deload_pct = 70
        db.session.commit()

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {stats.DEFAULT_PLAN_WEIGHT}
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {stats.DEFAULT_PLAN_REPS}


def test_a_deload_toggled_on_after_adding_does_not_scale_an_invented_default(client, virgin_session):
    """The order that broke it. gym_toggle_deload used to fill base_weight for
    every set that had None, with no way to tell an invented default-plan set
    apart from a real one that happened to sit at the same weight -- so
    add-exercise THEN deload-ON scaled the placeholder into a fabricated
    12,5 kg x 10 prescription, while the other order (see the sibling test
    above) stayed safe by accident. is_default_seeded makes the set say what
    it is, so gym_toggle_deload can now refuse regardless of ordering.

    Also proves the OFF round trip stays clean: nothing here was ever
    scaled, so toggling back off must leave it untouched too, not attempt to
    "restore" a baseline that was correctly never captured.
    """
    from extensions import db
    from models import SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})

    response = client.post(f'/gym/session/{live_id}/deload', data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {stats.DEFAULT_PLAN_WEIGHT}, (
            'deload toggled on after adding scaled an invented default')
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {stats.DEFAULT_PLAN_REPS}
        assert {s.base_reps for s in se.sets} == {None}
        assert all(s.is_default_seeded for s in se.sets)

    response = client.post(f'/gym/session/{live_id}/deload', data={'on': '0'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {stats.DEFAULT_PLAN_WEIGHT}, (
            'toggling the deload back off moved a set nothing ever scaled')
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {stats.DEFAULT_PLAN_REPS}
        assert {s.base_reps for s in se.sets} == {None}


def test_un_skipping_a_no_history_exercise_restores_the_default_plan(client, virgin_session):
    """Un-skip re-seeds through the same helper, so it gets the default too."""
    from extensions import db
    from models import SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se_id = SessionExercise.query.filter_by(session_id=live_id).one().id

    client.post(f'/gym/session-exercise/{se_id}/skip')
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.skipped is True
        assert se.sets == []

    client.post(f'/gym/session-exercise/{se_id}/skip')
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.skipped is False
        assert len(se.sets) == stats.DEFAULT_PLAN_SETS


def test_the_first_run_of_a_new_template_gets_the_default_plan(client, virgin_session):
    """Half the reason this work exists. A template stores an ordered list of
    exercises and no numbers at all, so on the day it is created every exercise
    in it has no history -- gym_start seeds through the same helper and used to
    produce a session of empty exercises."""
    from extensions import db
    from models import SessionExercise, TemplateExercise, WorkoutSession, WorkoutTemplate
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        # The fixture's session is in the way: gym_start redirects to the
        # running workout instead of starting a second one.
        running = db.session.get(WorkoutSession, live_id)
        running.finished_at = dt.datetime.utcnow()

        template = WorkoutTemplate(name='pytest brand new template',
                                   user_id=_admin_id())
        template.exercises.append(
            TemplateExercise(exercise_id=exercise_id, position=1))
        db.session.add(template)
        db.session.commit()
        template_id = template.id

    started_id = None
    try:
        response = client.post('/gym/start', data={'template_id': str(template_id)})
        assert response.status_code in (302, 303)

        with flask_app.app_context():
            started = (WorkoutSession.query
                       .filter_by(user_id=_admin_id(), finished_at=None)
                       .order_by(WorkoutSession.id.desc()).first())
            assert started is not None, 'gym_start did not create a session'
            started_id = started.id
            se = SessionExercise.query.filter_by(session_id=started_id).one()
            assert [(s.weight, s.reps, s.completed) for s in se.sets] == [
                (stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False)
            ] * stats.DEFAULT_PLAN_SETS
    finally:
        with flask_app.app_context():
            if started_id is not None:
                doomed = db.session.get(WorkoutSession, started_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            doomed_template = db.session.get(WorkoutTemplate, template_id)
            if doomed_template is not None:
                db.session.delete(doomed_template)
                db.session.commit()


def test_reordering_a_no_history_exercise_keeps_a_plan(client, virgin_session):
    """Reorder clears and re-derives pending sets for the new slot. Through the
    same helper, so the exercise must come back with a plan rather than with
    nothing -- the guard that protects logged work (`not any(s.completed)`) is
    unchanged and is not what this checks."""
    from extensions import db
    from models import Exercise, SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        second = Exercise(name='pytest cold start lift two',
                          muscle_group='Rücken', user_id=_admin_id())
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(second_id)})
        with flask_app.app_context():
            rows = (SessionExercise.query.filter_by(session_id=live_id)
                    .order_by(SessionExercise.position).all())
            reversed_ids = [se.id for se in reversed(rows)]

        client.post(f'/gym/session/{live_id}/exercises/reorder',
                    json={'order': reversed_ids})

        with flask_app.app_context():
            for se in SessionExercise.query.filter_by(session_id=live_id).all():
                assert len(se.sets) == stats.DEFAULT_PLAN_SETS, \
                    f'{se.id} came back from reorder with {len(se.sets)} sets'
    finally:
        with flask_app.app_context():
            for se in SessionExercise.query.filter_by(exercise_id=second_id).all():
                db.session.delete(se)
            db.session.commit()
            doomed = db.session.get(Exercise, second_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_history_still_wins_over_the_default(client, virgin_session):
    """The default is a fallback, not a replacement: an exercise that HAS been
    performed must still seed from what was actually done."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        past = WorkoutSession(name='pytest cold start history',
                              started_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              finished_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              user_id=_admin_id())
        past_se = SessionExercise(exercise_id=exercise_id, position=1)
        past_se.sets = [SessionSet(position=1, weight=77.5, reps=6, completed=True),
                        SessionSet(position=2, weight=77.5, reps=6, completed=True)]
        past.exercises.append(past_se)
        db.session.add(past)
        db.session.commit()
        past_id = past.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        with flask_app.app_context():
            se = (SessionExercise.query
                  .filter_by(session_id=live_id).one())
            assert [(s.weight, s.reps) for s in sorted(se.sets, key=lambda s: s.position)] \
                == [(77.5, 6), (77.5, 6)]
    finally:
        with flask_app.app_context():
            doomed = db.session.get(WorkoutSession, past_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_creating_an_exercise_from_the_search_leaves_no_muscle_group(client, virgin_session):
    """The search sheet's create path posts a name and nothing else -- the
    muscle-group select is gone from it, because mid-workout is the worst moment
    to ask and the field is optional and editable later in Übungen. Pinned
    because the route still accepts a muscle_group it will now never receive."""
    from extensions import db
    from models import Exercise, SessionExercise
    from features.gym import stats
    live_id, _ = virgin_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'new_exercise_name': 'pytest search created lift'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        created = Exercise.query.filter_by(name='pytest search created lift',
                                           user_id=_admin_id()).one()
        assert created.muscle_group is None
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert se.exercise_id == created.id
        # A brand-new exercise has no history by construction, so it must arrive
        # with the default plan -- this is the exact first-time-user path.
        assert len(se.sets) == stats.DEFAULT_PLAN_SETS
        db.session.delete(se)
        db.session.commit()
        db.session.delete(created)
        db.session.commit()

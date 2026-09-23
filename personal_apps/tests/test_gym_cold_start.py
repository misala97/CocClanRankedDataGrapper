"""The cold-start path: a workout where nothing has been logged before.

Every test here builds its own throwaway exercise with NO history, which is
the condition the whole suite is about -- an exercise the lifter has never
performed produces no seeded sets, and before this suite existed the live
screen had no behaviour for that.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id, embedded_payload


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
        exercise = Exercise(name='pytest cold start lift', muscle_group='Brust')
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


def test_an_exercise_with_no_history_arrives_with_a_blank_plan(client, virgin_session):
    """It used to arrive with nothing at all, which is what made the first
    logged set also the last: with no planned sets, one completed set meant
    every set was completed. Then with 3 x 20 kg x 8, a placeholder wrong for
    almost every exercise. Now the three sets wait with no numbers (V2)."""
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'exercise_id': str(exercise_id)})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.position, s.weight, s.reps, s.completed, s.is_default_seeded)
                for s in se.sets] == [
            (1, None, None, False, True),
            (2, None, None, False, True),
            (3, None, None, False, True),
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
                          muscle_group='Rücken')
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
        # Which exercise is live is the server's decision -- three surfaces
        # have to agree on it -- so the payload names it directly. If the
        # screen had advanced this would be the SECOND exercise's row, and
        # with the pre-fix `[]` seeding it would be None, which is what
        # renders the "Noch keine Übung" empty state.
        payload = embedded_payload(html)
        assert payload['live_id'] == se_id
        assert payload['visible_exercises'], 'no exercises, so the panel is empty'
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
    """There is no working weight to take a percentage of. Scaling the plan
    would present a fabricated prescription as a real one -- it stays blank.

    This covers only the ORDER that was already safe: is_deload is set
    directly on the model before the exercise is ever added, so
    gym_toggle_deload (the route that fills base_weight) never runs at all --
    see the sibling test below for the order that broke this.
    """
    from extensions import db
    from models import SessionExercise, WorkoutSession
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
        assert {s.weight for s in se.sets} == {None}
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {None}


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
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})

    response = client.post(f'/gym/session/{live_id}/deload', data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {None}, (
            'deload toggled on after adding gave the blank plan a number')
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {None}
        assert {s.base_reps for s in se.sets} == {None}
        assert all(s.is_default_seeded for s in se.sets)

    response = client.post(f'/gym/session/{live_id}/deload', data={'on': '0'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {None}, (
            'toggling the deload back off moved a set nothing ever scaled')
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {None}
        assert {s.base_reps for s in se.sets} == {None}


def test_a_deload_leaves_a_blank_alone_even_without_its_flag(client, virgin_session):
    """An edit to a sibling can clear a blank set's is_default_seeded (the
    carry clears the flag of every set it reaches, and a reps-only carry
    leaves the weight blank). A blank is still nothing to scale -- the
    deload must skip it rather than take a percentage of None."""
    from extensions import db
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        first_id = sorted(se.sets, key=lambda s: s.position)[0].id

    # Reps only, through the sheet: carried to sets 2/3 with their flags
    # cleared, weights still blank.
    client.post(f'/gym/set/{first_id}/update', data={'reps': '10'})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        rest = [s for s in se.sets if s.position > 1]
        assert [(s.weight, s.reps, s.is_default_seeded) for s in rest] == [
            (None, 10, False), (None, 10, False)], 'fixture assumption broken'

    response = client.post(f'/gym/session/{live_id}/deload', data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.weight, s.base_weight) for s in se.sets] == [(None, None)] * 3


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


def test_the_first_run_of_a_new_template_gets_the_blank_plan(client, virgin_session):
    """Half the reason this work exists. A template stores an ordered list of
    exercises and no numbers at all, so on the day it is created every exercise
    in it has no history -- gym_start seeds through the same helper and used to
    produce a session of empty exercises."""
    from extensions import db
    from models import SessionExercise, TemplateExercise, WorkoutSession, WorkoutTemplate
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        # Any running workout is in the way -- the fixture's, or one left in
        # the dev database by local testing: gym_start redirects to the
        # running workout instead of starting a second one.
        for running in (WorkoutSession.query
                        .filter_by(user_id=_admin_id())
                        .filter(WorkoutSession.finished_at.is_(None))):
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
                (None, None, False)
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
                          muscle_group='Rücken')
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


def test_correcting_set_one_of_a_default_plan_carries_to_the_still_pending_defaults(client, virgin_session):
    """The payoff this whole task exists for: type the real working weight
    once, on set 1, and sets 2/3 -- still sitting untouched on the blank
    plan -- pick it up too, instead of making the lifter retype it on every
    set of a brand-new exercise."""
    from extensions import db
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        first_id = sorted(se.sets, key=lambda s: s.position)[0].id

    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        rest = sorted((s for s in se.sets if s.position > 1), key=lambda s: s.position)
        assert [(s.weight, s.reps, s.completed) for s in rest] == [
            (82.5, 8, False), (82.5, 8, False)]


def test_correcting_a_history_seeded_set_does_not_propagate(client, virgin_session):
    """The owner's explicit condition: propagation is ONLY for the plan an
    exercise with no history gets (the 20,0kg placeholder then, blank since
    V2). An exercise seeded from real prior performance is a
    normal templated workout, where a mid-exercise weight change (a drop set,
    a ramp-up) is usually deliberate and must not spread to later sets."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        past = WorkoutSession(name='pytest carry history',
                              started_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              finished_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              user_id=_admin_id())
        past_se = SessionExercise(exercise_id=exercise_id, position=1)
        past_se.sets = [SessionSet(position=1, weight=60.0, reps=6, completed=True),
                        SessionSet(position=2, weight=60.0, reps=6, completed=True)]
        past.exercises.append(past_se)
        db.session.add(past)
        db.session.commit()
        past_id = past.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        with flask_app.app_context():
            se = SessionExercise.query.filter_by(session_id=live_id).one()
            assert all(not s.is_default_seeded for s in se.sets), \
                'fixture assumption broken: history-seeded sets must not be is_default_seeded'
            first_id = sorted(se.sets, key=lambda s: s.position)[0].id

        client.post(f'/gym/set/{first_id}/toggle_complete',
                    data={'completed': '1', 'weight': '65.0', 'reps': '5'})

        with flask_app.app_context():
            se = SessionExercise.query.filter_by(session_id=live_id).one()
            second = [s for s in se.sets if s.position == 2][0]
            assert (second.weight, second.reps, second.completed) == (60.0, 6, False), \
                'a history-seeded set must not adopt a sibling correction'
    finally:
        with flask_app.app_context():
            doomed = db.session.get(WorkoutSession, past_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_a_hand_edited_default_set_is_not_overwritten_by_a_later_correction(client, virgin_session):
    """Once a default-seeded set has been hand-edited, is_default_seeded is
    cleared on it (existing behaviour) -- so it must be left alone by a LATER
    correction on an earlier set in the same exercise, same as any other real,
    lifter-chosen value."""
    from extensions import db
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        first_id, second_id = ordered[0].id, ordered[1].id

    # Set 2 gets its own deliberate drop-set weight first, hand-typed but not
    # yet confirmed done -- gym_toggle_set_complete is the only route that
    # writes weight/reps from the live screen, so "hand-typed" here means
    # posting a changed value, same as a real correction.
    client.post(f'/gym/set/{second_id}/toggle_complete',
                data={'completed': '0', 'weight': '40.0', 'reps': '12'})
    with flask_app.app_context():
        from models import SessionSet
        second = db.session.get(SessionSet, second_id)
        assert second.is_default_seeded is False, \
            'fixture assumption broken: a changed weight must clear is_default_seeded'

    # Now set 1 is corrected and confirmed -- propagation must skip set 2,
    # which is no longer sitting on the untouched default.
    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        from models import SessionSet
        second = db.session.get(SessionSet, second_id)
        assert (second.weight, second.reps) == (40.0, 12), \
            'a hand-edited default set must not be overwritten by a later correction'


def test_a_completed_set_is_never_rewritten_by_propagation(client, virgin_session):
    """A set that is already logged is never touched, even if it is STILL
    is_default_seeded (nothing about it was ever hand-edited) and sits after
    the set being corrected -- completed work is never rewritten regardless
    of position or flag state.

    Set 3 was confirmed done out of order first, at the old 20 kg x 8
    placeholder unchanged -- the "changed by hand" branch never fired, so it
    stayed is_default_seeded=True while completed=True. Blank plans cannot
    get there any more (a first number is always a change), but those sets
    are in the database: the blanking migration leaves completed sets alone.
    It is the one state combination that would slip past a propagation guard
    checking only is_default_seeded and not completed -- so this is the test
    that actually exercises the `completed` filter, not just the
    `is_default_seeded` one. Built directly, as the old code left it."""
    from extensions import db
    from models import SessionExercise, SessionSet
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        first_id, second_id, third_id = [s.id for s in ordered]
        third = db.session.get(SessionSet, third_id)
        third.weight, third.reps, third.completed = 20.0, 8, True
        db.session.commit()

    # Set 1 typed and confirmed -- the carry reaches set 2 (still pending,
    # still untouched) but must skip set 3: it is already completed.
    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        second = db.session.get(SessionSet, second_id)
        third = db.session.get(SessionSet, third_id)
        assert (second.weight, second.reps) == (82.5, 8)
        assert (third.weight, third.reps, third.completed, third.is_default_seeded) == (
            20.0, 8, True, True), 'a completed set was rewritten by a later propagation'


def test_a_propagated_correction_becomes_the_real_plan_not_a_new_placeholder(client, virgin_session):
    """Decision the owner left to this implementation: a set that ADOPTS a
    propagated correction has its own is_default_seeded cleared too, same as
    the set that was hand-typed. The correction is now the plan, not a
    guess -- if the flag stayed set, a second, independent correction later
    in the exercise would keep re-propagating past sets the lifter already
    silently accepted, which is exactly the always-carry-forward behaviour
    the owner rejected for a normal templated workout, just deferred by one
    set instead of skipped."""
    from extensions import db
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        first_id = sorted(se.sets, key=lambda s: s.position)[0].id

    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        rest = sorted((s for s in se.sets if s.position > 1), key=lambda s: s.position)
        assert all(s.is_default_seeded is False for s in rest), \
            'a set that adopted a propagated correction must stop counting as an untouched default'


def test_correcting_set_two_does_not_propagate_backwards_to_set_one(client, virgin_session):
    """Mutation-tested guard: _propagate_default_correction skips any sibling
    whose position is <= the corrected set's own. Every other test in this
    file corrects set 1, so a mutant that deletes that guard -- propagating
    BACKWARDS too -- sailed through the whole suite untouched. Correct set 2
    instead, and assert set 1, still pending and still on the untouched
    default, is left alone (while forward propagation to set 3 still works,
    so this isn't just a weaker version of the forward test). Holds for
    _fill_blanks_after too: set 1 is blank, and a later set's numbers must
    not fill it."""
    from extensions import db
    from models import SessionExercise, SessionSet
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        first_id, second_id, third_id = [s.id for s in ordered]

    client.post(f'/gym/set/{second_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        first = db.session.get(SessionSet, first_id)
        third = db.session.get(SessionSet, third_id)
        assert (first.weight, first.reps, first.completed, first.is_default_seeded) == (
            None, None, False, True), \
            'an earlier pending default set must not be propagated to backwards'
        assert (third.weight, third.reps, third.is_default_seeded) == (82.5, 8, False), \
            'forward propagation from set 2 to set 3 must still work'


def test_retyping_an_already_hand_edited_set_does_not_re_propagate(client, virgin_session):
    """Mutation-tested guard: gym_toggle_set_complete's trigger condition
    checks `was_default_seeded` -- read before this request's own edits touch
    the flag -- not just `completed and (weight_changed or reps_changed)`.

    Hand-edit set 2 once (a deliberate drop set, not yet confirmed): its own
    is_default_seeded clears, same as any hand-edit, and it is not completed
    so no propagation fires. Set 3 gets a rep count typed through the sheet
    -- a typed rep count leaves the flag standing, so set 3 is still an
    untouched plan with its weight blank. Retype set 2 a SECOND time, new
    weight AND reps, and complete it -- without the was_default_seeded guard
    this reads as merely `completed and changed` and fires propagation again,
    even though set 2 was no longer an untouched default at the moment this
    second edit arrived, and would stamp set 3's typed reps with set 2's.

    Set 3's blank weight does take set 2's: filling a blank overrides
    nothing (_fill_blanks_after). Only its typed reps must survive."""
    from extensions import db
    from models import SessionExercise, SessionSet
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        second_id, third_id = ordered[1].id, ordered[2].id

    # First correction: a deliberate drop set on set 2, not yet confirmed.
    client.post(f'/gym/set/{second_id}/toggle_complete',
                data={'completed': '0', 'weight': '40.0', 'reps': '12'})
    client.post(f'/gym/set/{third_id}/update', data={'reps': '10'})
    with flask_app.app_context():
        second = db.session.get(SessionSet, second_id)
        third = db.session.get(SessionSet, third_id)
        assert second.is_default_seeded is False, \
            'fixture assumption broken: a changed weight must clear is_default_seeded'
        assert (third.weight, third.reps, third.is_default_seeded) == (None, 10, True), \
            'fixture assumption broken: typed reps alone must leave the flag'

    # Second correction: retype set 2, weight and reps, and confirm it.
    client.post(f'/gym/set/{second_id}/toggle_complete',
                data={'completed': '1', 'weight': '45.0', 'reps': '15'})

    with flask_app.app_context():
        third = db.session.get(SessionSet, third_id)
        assert (third.weight, third.reps, third.completed) == (45.0, 10, False), \
            'a retype of an already hand-edited set must not re-propagate to a later default sibling'


def test_correcting_via_gym_update_set_also_propagates(client, virgin_session):
    """F1 regression: session_detail.html's per-exercise sheet renders a
    SECOND full weight/reps editor for each set, posting to gym_update_set --
    not gym_toggle_set_complete's confirm button. Before this fix, that route
    cleared is_default_seeded without ever propagating, and clearing the flag
    then made the LATER toggle_complete confirm refuse to propagate too
    (was_default_seeded read False by the time it ran). Reproduces the exact
    repro: POST update with a corrected weight, then confirm the set via
    toggle_complete, and assert sets 2/3 pick up the correction."""
    from extensions import db
    from models import SessionExercise, SessionSet
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        first_id, second_id, third_id = [s.id for s in ordered]

    client.post(f'/gym/set/{first_id}/update', data={'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        second = db.session.get(SessionSet, second_id)
        third = db.session.get(SessionSet, third_id)
        assert (second.weight, second.reps, second.is_default_seeded) == (82.5, 8, False), \
            'gym_update_set must propagate a default correction forward, same as gym_toggle_set_complete'
        assert (third.weight, third.reps, third.is_default_seeded) == (82.5, 8, False)

    # The other affordance on the same screen, confirming the same set --
    # must not error, and must not undo what the update above already did.
    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        second = db.session.get(SessionSet, second_id)
        third = db.session.get(SessionSet, third_id)
        assert (second.weight, second.reps) == (82.5, 8)
        assert (third.weight, third.reps) == (82.5, 8)


def test_gym_update_set_does_not_propagate_on_a_finished_session(client, virgin_session):
    """F2 (polish): gym_update_set had no liveness guard, and the finished
    session's quiet "Sätze & Notizen" disclosure (session_finished.html)
    posts to this same route. Set 1 was confirmed at the old 20 kg x 8
    placeholder unchanged, so is_default_seeded survived on it (built
    directly, as the old code left it -- see
    test_a_completed_set_is_never_rewritten_by_propagation above); the
    session is finished, then set 1's weight is corrected from the finished
    page. Sets 2 and 3 were NEVER PERFORMED -- rewriting them inside an
    already-closed historical record is wrong even though most consumers
    filter on `completed`, because the JSON export does not. Only set 1, the
    one actually edited, may change."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        ordered = sorted(se.sets, key=lambda s: s.position)
        first_id, second_id, third_id = [s.id for s in ordered]
        first = db.session.get(SessionSet, first_id)
        first.weight, first.reps, first.completed = 20.0, 8, True
        session_ = db.session.get(WorkoutSession, live_id)
        session_.finished_at = dt.datetime.utcnow()
        db.session.commit()

    # Correct the typo from the finished page's own editor -- gym_update_set,
    # same route the live sheet uses.
    client.post(f'/gym/set/{first_id}/update', data={'weight': '82.5', 'reps': '8'})

    with flask_app.app_context():
        first = db.session.get(SessionSet, first_id)
        second = db.session.get(SessionSet, second_id)
        third = db.session.get(SessionSet, third_id)
        assert (first.weight, first.reps) == (82.5, 8), \
            'correcting a finished set must still apply to the set actually edited'
        assert (second.weight, second.reps, second.is_default_seeded) == (None, None, True), \
            'a never-performed sibling must not be rewritten on a finished session'
        assert (third.weight, third.reps, third.is_default_seeded) == (None, None, True), \
            'a never-performed sibling must not be rewritten on a finished session'


# The search sheet's create path (a name-only post) is gone with the one list
# (2026-09-23); its refusal is pinned in test_gym_exercise_ownership.py.


def test_replacing_an_exercise_with_no_history_seeds_a_blank_plan(client, virgin_session):
    """F2 regression: gym_replace_session_exercise created the substitute
    SessionExercise without ever calling _seeded_sets, the only remaining
    route that produced the zero-sets shape _live_context treats as "live
    until one set lands, then finished" -- the headline cold-start bug this
    whole file is about. The ORIGINAL row's own sets (seeded when it was
    added, same no-history path) must be left completely untouched -- the
    replace route deliberately keeps them so they keep counting toward the
    original exercise's own history."""
    from extensions import db
    from models import Exercise, SessionExercise
    from features.gym import stats
    from conftest import _admin_id
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        original = SessionExercise.query.filter_by(session_id=live_id).one()
        original_id = original.id
        original_sets_before = [(s.position, s.weight, s.reps) for s in original.sets]

        substitute_exercise = Exercise(name='pytest replace no-history sub',
                                       muscle_group='Brust')
        db.session.add(substitute_exercise)
        db.session.commit()
        substitute_exercise_id = substitute_exercise.id

    try:
        response = client.post(f'/gym/session-exercise/{original_id}/replace',
                               data={'exercise_id': str(substitute_exercise_id)})
        assert response.status_code in (302, 303)

        with flask_app.app_context():
            substitute = SessionExercise.query.filter_by(
                session_id=live_id, exercise_id=substitute_exercise_id).one()
            assert [(s.position, s.weight, s.reps, s.completed, s.is_default_seeded)
                    for s in substitute.sets] == [
                (1, None, None, False, True),
                (2, None, None, False, True),
                (3, None, None, False, True),
            ]
            assert substitute.replaces_id == original_id

            original = db.session.get(SessionExercise, original_id)
            assert [(s.position, s.weight, s.reps) for s in original.sets] == original_sets_before, \
                'the original row and its own sets must be left untouched by the replace'
    finally:
        with flask_app.app_context():
            leftover = SessionExercise.query.filter_by(
                session_id=live_id, exercise_id=substitute_exercise_id).first()
            if leftover is not None:
                db.session.delete(leftover)
                db.session.commit()
            doomed = db.session.get(Exercise, substitute_exercise_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


# V2 (docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md): the plan
# for an exercise with no history waits blank, the lifter types the first set.


def _add_and_ids(client, live_id, exercise_id):
    """Add the exercise through the route: its SessionExercise id, and its set
    ids in position order."""
    from models import SessionExercise
    client.post(f'/gym/session/{live_id}/exercises/add', data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id, exercise_id=exercise_id).one()
        return se.id, [s.id for s in sorted(se.sets, key=lambda s: s.position)]


def test_a_blank_set_cannot_be_logged(client, virgin_session):
    """There is no lift for a set without its numbers to say. The live screen
    never asks -- its button asks for the missing number first -- so this is a
    stale page or a replay: the set stays open, keeps whatever number it did
    carry, starts no rest, and fills nothing after it."""
    from extensions import db
    from models import SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session
    _se_id, (first_id, second_id, _third_id) = _add_and_ids(client, live_id, exercise_id)

    client.post(f'/gym/set/{first_id}/toggle_complete', data={'completed': '1'})
    client.post(f'/gym/set/{first_id}/toggle_complete', data={'completed': '1', 'weight': '60'})

    with flask_app.app_context():
        first = db.session.get(SessionSet, first_id)
        assert (first.weight, first.reps, first.completed, first.completed_at) == (
            60.0, None, False, None)
        assert db.session.get(WorkoutSession, live_id).resting_set_id is None
        second = db.session.get(SessionSet, second_id)
        assert (second.weight, second.reps, second.completed) == (None, None, False)


def test_the_first_numbers_fill_the_plan_even_at_the_old_placeholder(client, virgin_session):
    """20 kg x 8 used to be the placeholder, so typing exactly that was no
    change and carried nowhere -- the lifter retyped it on every set. A blank
    has no such number: whatever is typed first carries."""
    from extensions import db
    from models import SessionSet
    live_id, exercise_id = virgin_session
    _se_id, set_ids = _add_and_ids(client, live_id, exercise_id)

    client.post(f'/gym/set/{set_ids[0]}/toggle_complete',
                data={'completed': '1', 'weight': '20.0', 'reps': '8'})

    with flask_app.app_context():
        sets = [db.session.get(SessionSet, set_id) for set_id in set_ids]
        assert [(s.weight, s.reps, s.completed) for s in sets] == [
            (20.0, 8, True), (20.0, 8, False), (20.0, 8, False)]


def test_reps_logged_after_a_sheet_typed_weight_still_reach_the_blanks(client, virgin_session):
    """A weight typed into the exercise sheet before the first set is logged
    carries the weight and clears every flag -- so the carry cannot move the
    reps logged afterwards. _fill_blanks_after does: sets 2/3 end up with the
    logged set's numbers, not a weight and a blank."""
    from extensions import db
    from models import SessionSet
    live_id, exercise_id = virgin_session
    _se_id, (first_id, second_id, third_id) = _add_and_ids(client, live_id, exercise_id)

    client.post(f'/gym/set/{first_id}/update', data={'weight': '60'})
    with flask_app.app_context():
        second = db.session.get(SessionSet, second_id)
        assert (second.weight, second.reps, second.is_default_seeded) == (60.0, None, False), \
            'fixture assumption broken'

    client.post(f'/gym/set/{first_id}/toggle_complete',
                data={'completed': '1', 'weight': '60', 'reps': '10'})

    with flask_app.app_context():
        for set_id in (second_id, third_id):
            s = db.session.get(SessionSet, set_id)
            assert (s.weight, s.reps, s.completed, s.is_default_seeded) == (60.0, 10, False, False)


def test_a_finished_workouts_open_blanks_stay_blank(client, virgin_session):
    """Filling blanks is for the plan ahead of a live lifter. A set logged
    into a finished workout from anywhere but the live screen (which is
    refused outright) leaves the never-lifted sets after it as they were --
    the rule gym_update_set's carry keeps too."""
    from extensions import db
    from models import SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session
    _se_id, (first_id, second_id, _third_id) = _add_and_ids(client, live_id, exercise_id)
    # Typed in the sheet while live: the weight carries to sets 2/3 and every
    # flag clears, so only _fill_blanks_after could still reach their reps.
    client.post(f'/gym/set/{first_id}/update', data={'weight': '60'})
    with flask_app.app_context():
        db.session.get(WorkoutSession, live_id).finished_at = dt.datetime.utcnow()
        db.session.commit()

    client.post(f'/gym/set/{first_id}/toggle_complete', data={'completed': '1', 'reps': '10'})

    with flask_app.app_context():
        first = db.session.get(SessionSet, first_id)
        assert (first.weight, first.reps, first.completed) == (60.0, 10, True)
        second = db.session.get(SessionSet, second_id)
        assert (second.weight, second.reps) == (60.0, None)


def test_the_payload_marks_a_first_time_until_a_set_lands(client, virgin_session):
    """first_time names the exercises the lifter meets for the first time --
    the live screen's "Erstes Mal" note. This one is a throwaway row off the
    list, so it has no variants to name; once a set of it is logged it is no
    longer a first time. live_floor is where a blank kg stepper's "+" lands:
    with no bar and no stack, one step."""
    from features.gym import stats
    live_id, exercise_id = virgin_session
    se_id, set_ids = _add_and_ids(client, live_id, exercise_id)

    payload = client.get(f'/gym/session/{live_id}/detail.json').get_json()
    assert payload['first_time'] == {str(se_id): []}
    assert payload['live_floor'] == stats.DEFAULT_INCREMENT
    assert [(s['weight'], s['reps']) for s in payload['visible_exercises'][0]['sets']] == [
        (None, None)] * 3

    client.post(f'/gym/set/{set_ids[0]}/toggle_complete',
                data={'completed': '1', 'weight': '60', 'reps': '10'})
    payload = client.get(f'/gym/session/{live_id}/detail.json').get_json()
    assert payload['first_time'] == {}


@pytest.fixture()
def fresh_lifter(client):
    """A lifter of their own, logged in on `client`: a history this suite
    controls completely, which the admin's dev-database record is not."""
    from werkzeug.security import generate_password_hash
    from extensions import db
    from models import AppUser, ExerciseSettings, PendingPush, WorkoutSession
    with flask_app.app_context():
        user = AppUser(username='pytest first time lifter',
                       password_hash=generate_password_hash('x'), is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as flask_session:
        flask_session['user_id'] = user_id
    yield user_id
    with flask_app.app_context():
        for session_ in WorkoutSession.query.filter_by(user_id=user_id).all():
            session_.resting_set_id = None
            PendingPush.query.filter_by(session_id=session_.id).delete()
            db.session.commit()
            db.session.delete(session_)
            db.session.commit()
        ExerciseSettings.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(AppUser, user_id))
        db.session.commit()


def test_a_first_time_names_the_lifters_other_variants(client, fresh_lifter):
    """The "Erstes Mal" note's references: up to two other variants of the
    movement the lifter has done, most-done first, each with the top set of
    the latest workout that had it. A deload's numbers are deliberately
    light, so a deload workout does not count -- and a variant done only in
    deloads gives way to the next one, though it ranks first. live_floor is
    the empty bar of a barbell lift."""
    from extensions import db
    from conftest import list_exercise
    from models import SessionExercise, SessionSet, WorkoutSession
    now = dt.datetime.utcnow()
    with flask_app.app_context():
        rows = {key: list_exercise(key) for key in (
            'barbell_bench_press', 'dumbbell_bench_press', 'plate_bench_press',
            'smith_bench_press')}
        ids = {key: row.id for key, row in rows.items()}
        per_side = {key: row.is_unilateral for key, row in rows.items()}

        def workout(days_ago, deload, lifts):
            session_ = WorkoutSession(
                name='pytest first time history', user_id=fresh_lifter,
                started_at=now - dt.timedelta(days=days_ago),
                finished_at=now - dt.timedelta(days=days_ago) + dt.timedelta(minutes=50),
                is_deload=deload, deload_pct=70 if deload else None)
            for position, (key, sets) in enumerate(lifts, start=1):
                row = SessionExercise(exercise_id=ids[key], position=position)
                row.sets = [SessionSet(position=j, weight=weight, reps=reps, completed=True)
                            for j, (weight, reps) in enumerate(sets, start=1)]
                session_.exercises.append(row)
            db.session.add(session_)

        # Usage ranks: Multipresse 1 (two recent deloads), Maschine 2, Kurzhantel 3.
        workout(1, True, [('smith_bench_press', [(30.0, 8)]), ('plate_bench_press', [(40.0, 8)])])
        workout(2, True, [('smith_bench_press', [(30.0, 8)])])
        workout(5, False, [('dumbbell_bench_press', [(26.0, 10), (26.0, 9)])])
        workout(10, False, [('plate_bench_press', [(27.5, 10), (25.0, 12)])])
        workout(20, False, [('dumbbell_bench_press', [(24.0, 10)])])
        live = WorkoutSession(name='pytest first time live', user_id=fresh_lifter, started_at=now)
        db.session.add(live)
        db.session.commit()
        live_id = live.id

    se_id, _set_ids = _add_and_ids(client, live_id, ids['barbell_bench_press'])
    payload = client.get(f'/gym/session/{live_id}/detail.json').get_json()

    assert payload['first_time'] == {str(se_id): [
        {'label': 'Maschine, Scheiben', 'weight': 27.5, 'reps': 10,
         'per_side': per_side['plate_bench_press']},
        {'label': 'Kurzhantel', 'weight': 26.0, 'reps': 10,
         'per_side': per_side['dumbbell_bench_press']},
    ]}
    assert payload['live_floor'] == 20.0

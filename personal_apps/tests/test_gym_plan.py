"""The plan model (walkthrough D2 P1: G-050, G-051).

A routine row keeps how many sets the exercise gets and the rep range it
aims at. They are filled from the lifter's history the first time the
routine is started, then changed only by an explicit edit -- so one short
workout no longer shrinks a routine for good (G-050). Seeding cuts the
picked workout's sets to the row's count, or repeats its last set up to it.

Runs against the local development database with a throwaway lifter.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import Exercise, SessionSet, SharedSession, TemplateExercise, WorkoutSession

DAY = dt.timedelta(days=1)


def _history(lifter, exercise, days_ago, sets, template=None, position=1,
             is_deload=False):
    """A finished workout `days_ago` with `sets` of `exercise` done."""
    workout = lifter.workout(days_ago * DAY, template=template, finished=True,
                             is_deload=is_deload)
    lifter.row(workout, exercise, position, done=sets)
    return workout


def _routine_rows(template_id):
    """The routine's rows as (exercise id, target_sets, rep_min, rep_max)."""
    with flask_app.app_context():
        return [(row.exercise_id, row.target_sets, row.rep_min, row.rep_max)
                for row in TemplateExercise.query.filter_by(template_id=template_id)
                .order_by(TemplateExercise.position)]


def _running(user_id):
    with flask_app.app_context():
        return WorkoutSession.query.filter_by(user_id=user_id, finished_at=None).one().id


def _plan(workout_id):
    """The workout's visible rows as (exercise id, [(weight, reps), ...])."""
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        return [(row.exercise_id, [(s.weight, s.reps) for s in row.sets])
                for row in workout.exercises if row.replaced_by is None]


def _row_id(workout_id, exercise_id):
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        return next(row.id for row in workout.exercises if row.exercise_id == exercise_id)


def _start(lifter, template_id, user_id=None):
    response = lifter.client(user_id).post('/gym/start', data={'template_id': template_id})
    assert response.status_code == 302
    return _running(user_id or lifter.user_id)


def test_the_first_start_fills_the_routine_from_its_history(lifter):
    """The count is the most sets any of the routine's last three workouts
    held; the range is centred on the median reps at the top weight."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 9, [(100, 10)] * 4, template=routine)
        _history(lifter, press, 6, [(100, 11), (100, 11), (100, 10), (100, 10), (100, 9)],
                 template=routine)
        _history(lifter, press, 3, [(100, 12)] * 3, template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _routine_rows(routine_id) == [(press_id, 5, 8, 12)]
    # The pick is the 12-rep workout (best e1RM), its three sets repeated to five.
    assert _plan(workout_id) == [(press_id, [(100, 12)] * 5)]


def test_the_set_count_reads_the_routines_own_workouts_first(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 6, [(100, 8)] * 3, template=routine)
        _history(lifter, press, 3, [(100, 8)] * 6)
        db.session.commit()
        routine_id = routine.id

    _start(lifter, routine_id)

    assert _routine_rows(routine_id)[0][1] == 3


def test_a_routine_never_done_takes_the_count_from_anywhere(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 3, [(100, 8)] * 4)
        db.session.commit()
        routine_id = routine.id

    _start(lifter, routine_id)

    assert _routine_rows(routine_id)[0][1] == 4


def test_the_set_count_reads_the_routines_last_three_workouts(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 12, [(100, 8)] * 6, template=routine)
        for days_ago in (9, 6, 3):
            _history(lifter, press, days_ago, [(100, 8)] * 3, template=routine)
        db.session.commit()
        routine_id = routine.id

    _start(lifter, routine_id)

    assert _routine_rows(routine_id)[0][1] == 3


def test_a_deload_does_not_shape_the_plan(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 6, [(100, 8)] * 3, template=routine)
        _history(lifter, press, 3, [(70, 15)] * 5, template=routine, is_deload=True)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    _start(lifter, routine_id)

    assert _routine_rows(routine_id) == [(press_id, 3, 6, 10)]


def test_a_short_workout_does_not_shrink_the_routine(lifter):
    """G-050: a two-set test workout was the pick, and every start after it
    planned two sets."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        _history(lifter, press, 6, [(100, 8)] * 4, template=routine)
        _history(lifter, press, 2, [(105, 8)] * 2, template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _plan(workout_id) == [(press_id, [(105, 8)] * 4)]


def test_a_filled_plan_is_not_derived_again(lifter):
    """Once filled, the row is the lifter's: history that says otherwise
    changes neither it nor the plan it makes."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (2, 5, 7)})
        _history(lifter, press, 3, [(100, 6), (100, 6), (95, 7), (95, 7), (90, 8)],
                 template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _routine_rows(routine_id) == [(press_id, 2, 5, 7)]
    assert _plan(workout_id) == [(press_id, [(100, 6), (100, 6)])]


def test_no_history_fills_the_defaults(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press])
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _routine_rows(routine_id) == [(press_id, 3, 6, 10)]
    assert _plan(workout_id) == [(press_id, [(None, None)] * 3)]


def test_no_history_plans_the_routines_count_of_blank_sets(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (5, 6, 10)})
        db.session.commit()
        routine_id = routine.id

    workout_id = _start(lifter, routine_id)

    with flask_app.app_context():
        sets = SessionSet.query.join(SessionSet.session_exercise).filter_by(
            session_id=workout_id).all()
        assert len(sets) == 5
        assert all(s.is_default_seeded and s.weight is None for s in sets)


def test_updating_the_routine_keeps_each_exercises_plan(lifter):
    """"Routine aktualisieren" rebuilds the rows from the workout: the plan
    travels with the exercise, wherever it now stands. A new exercise starts
    unfilled, and the next start fills it."""
    with flask_app.app_context():
        press, row_, curl = (lifter.exercise(name) for name in ('press', 'row', 'curl'))
        routine = lifter.routine('push', [press, row_],
                                 plan={press.id: (4, 6, 8), row_.id: (3, 8, 12)})
        workout = lifter.workout(DAY, template=routine, finished=True)
        lifter.row(workout, row_, 1, done=[(60, 10)])
        lifter.row(workout, press, 2, done=[(100, 7)])
        lifter.row(workout, curl, 3, done=[(20, 12)])
        db.session.commit()
        routine_id, workout_id = routine.id, workout.id
        ids = press.id, row_.id, curl.id

    response = lifter.client().post(f'/gym/session/{workout_id}/update_template')

    assert response.status_code == 302
    press_id, row_id, curl_id = ids
    assert _routine_rows(routine_id) == [
        (row_id, 3, 8, 12), (press_id, 4, 6, 8), (curl_id, None, None, None)]


def test_a_substitute_plans_its_slots_set_count(lifter):
    """The substitute stands in for the routine's exercise: its slot's four
    sets, not the two its own last workout held."""
    with flask_app.app_context():
        press, dips = lifter.exercise('press'), lifter.exercise('dips')
        routine = lifter.routine('push', [press], plan={press.id: (4, 6, 10)})
        _history(lifter, dips, 3, [(50, 8)] * 2)
        db.session.commit()
        routine_id, press_id, dips_id = routine.id, press.id, dips.id

    workout_id = _start(lifter, routine_id)
    lifter.client().post(f'/gym/session-exercise/{_row_id(workout_id, press_id)}/replace',
                         data={'exercise_id': dips_id})

    assert _plan(workout_id) == [(dips_id, [(50, 8)] * 4)]


def test_an_added_exercise_keeps_the_count_its_history_gives(lifter):
    """An exercise the routine does not hold has no row to read: its own
    last workout decides, as before."""
    with flask_app.app_context():
        press, curl = lifter.exercise('press'), lifter.exercise('curl')
        routine = lifter.routine('push', [press], plan={press.id: (4, 6, 10)})
        _history(lifter, curl, 3, [(20, 12)] * 2)
        db.session.commit()
        routine_id, curl_id = routine.id, curl.id

    workout_id = _start(lifter, routine_id)
    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id})

    assert _plan(workout_id)[1] == (curl_id, [(20, 12)] * 2)


def test_a_substitute_back_from_a_skip_owes_its_slots_count(lifter):
    with flask_app.app_context():
        press, dips = lifter.exercise('press'), lifter.exercise('dips')
        routine = lifter.routine('push', [press], plan={press.id: (4, 6, 10)})
        _history(lifter, dips, 3, [(50, 8)] * 2)
        db.session.commit()
        routine_id, press_id, dips_id = routine.id, press.id, dips.id

    workout_id = _start(lifter, routine_id)
    client = lifter.client()
    client.post(f'/gym/session-exercise/{_row_id(workout_id, press_id)}/replace',
                data={'exercise_id': dips_id})
    dips_row = _row_id(workout_id, dips_id)
    with flask_app.app_context():
        first = SessionSet.query.filter_by(session_exercise_id=dips_row, position=1).one()
        first.completed, first.completed_at = True, lifter.now
        db.session.commit()
    client.post(f'/gym/session-exercise/{dips_row}/skip')
    client.post(f'/gym/session-exercise/{dips_row}/skip')

    assert _plan(workout_id) == [(dips_id, [(50, 8)] * 4)]


def test_a_substitute_moved_to_another_slot_is_replanned_at_its_count(lifter):
    """Reordering re-derives an untouched plan for the new slot -- which it
    can only tell is untouched by asking seeding the same question, count
    included."""
    with flask_app.app_context():
        press, row_, dips = (lifter.exercise(name) for name in ('press', 'row', 'dips'))
        routine = lifter.routine('push', [press, row_],
                                 plan={press.id: (4, 6, 10), row_.id: (3, 6, 10)})
        _history(lifter, dips, 3, [(60, 8)] * 2, position=1)
        _history(lifter, dips, 2, [(50, 8)] * 2, position=2)
        db.session.commit()
        routine_id, press_id, row_id, dips_id = routine.id, press.id, row_.id, dips.id

    workout_id = _start(lifter, routine_id)
    client = lifter.client()
    client.post(f'/gym/session-exercise/{_row_id(workout_id, press_id)}/replace',
                data={'exercise_id': dips_id})
    assert _plan(workout_id)[0] == (dips_id, [(60, 8)] * 4)
    order = f'{_row_id(workout_id, row_id)},{_row_id(workout_id, dips_id)}'
    client.post(f'/gym/session/{workout_id}/exercises/reorder', data={'order': order})

    assert _plan(workout_id)[1] == (dips_id, [(50, 8)] * 4)


def _payload(lifter, workout_id):
    return lifter.client().get(f'/gym/session/{workout_id}/detail.json').get_json()


def test_the_live_card_aims_one_rep_higher_set_by_set(lifter):
    """"Nächstes Ziel" per set (Michi, M2 09-24): each set at its own
    weight, one rep more -- the back-off sets are not asked to climb to the
    first set's weight. From the workout the Vorgabe names."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (3, 6, 10)})
        _history(lifter, press, 3, [(40, 8), (35, 9), (35, 8)], template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)
    body = _payload(lifter, workout_id)

    assert body['next_targets'] == {str(_row_id(workout_id, press_id)): [
        {'weight': 40.0, 'reps': 9}, {'weight': 35.0, 'reps': 10}, {'weight': 35.0, 'reps': 9}]}
    assert body['deload_hints'] == {}


def test_every_set_at_the_top_of_the_range_steps_each_one_up(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (2, 7, 11)})
        _history(lifter, press, 3, [(85, 11), (80, 12)], template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _payload(lifter, workout_id)['next_targets'][str(_row_id(workout_id, press_id))] == [
        {'weight': 87.5, 'reps': 7}, {'weight': 82.5, 'reps': 7}]


def test_an_exercise_outside_any_routine_aims_by_the_range_its_history_gives(lifter):
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        _history(lifter, curl, 3, [(20, 12)] * 3)
        workout = lifter.workout(dt.timedelta(minutes=5))
        db.session.commit()
        workout_id, curl_id = workout.id, curl.id

    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id})

    # The range 10-14 around the median of 12: one rep more, set by set.
    assert _payload(lifter, workout_id)['next_targets'] == {
        str(_row_id(workout_id, curl_id)): [{'weight': 20.0, 'reps': 13}] * 3}


def test_a_deload_week_does_not_shape_the_range_the_card_aims_by(lifter):
    """Four reps in a deload would pull the range down to 5-9, and the 10s
    of the real workout would read as the top of it."""
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        _history(lifter, curl, 5, [(20, 10)] * 3)
        _history(lifter, curl, 2, [(15, 4)] * 3, is_deload=True)
        workout = lifter.workout(dt.timedelta(minutes=5))
        db.session.commit()
        workout_id, curl_id = workout.id, curl.id

    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id})

    assert _payload(lifter, workout_id)['next_targets'] == {
        str(_row_id(workout_id, curl_id)): [{'weight': 20.0, 'reps': 11}] * 3}


def test_the_card_aims_by_the_newest_workouts(lifter):
    """Six old workouts of fours would pull the range down to 2-6 and read
    the tens as far past it: only the newest five are read."""
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        for days_ago in (20, 19, 18, 17, 16, 15):
            _history(lifter, curl, days_ago, [(20, 4)] * 3)
        for days_ago in (10, 8, 6, 4, 2):
            _history(lifter, curl, days_ago, [(20, 10)] * 3)
        workout = lifter.workout(dt.timedelta(minutes=5))
        db.session.commit()
        workout_id, curl_id = workout.id, curl.id

    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id})

    assert _payload(lifter, workout_id)['next_targets'] == {
        str(_row_id(workout_id, curl_id)): [{'weight': 20.0, 'reps': 11}] * 3}


def test_a_substitute_aims_at_its_slots_count(lifter):
    """Four planned sets, two done last time, both at the top of the range
    (6-10, from the eights before): the two missing hold the step back, so
    no set steps up -- each stays at the top."""
    with flask_app.app_context():
        press, dips = lifter.exercise('press'), lifter.exercise('dips')
        routine = lifter.routine('push', [press], plan={press.id: (4, 6, 10)})
        for days_ago in (12, 9, 6):
            _history(lifter, dips, days_ago, [(50, 8)] * 4)
        _history(lifter, dips, 3, [(50, 10)] * 2)
        db.session.commit()
        routine_id, press_id, dips_id = routine.id, press.id, dips.id

    workout_id = _start(lifter, routine_id)
    lifter.client().post(f'/gym/session-exercise/{_row_id(workout_id, press_id)}/replace',
                         data={'exercise_id': dips_id})

    assert _payload(lifter, workout_id)['next_targets'] == {
        str(_row_id(workout_id, dips_id)): [{'weight': 50.0, 'reps': 10}] * 4}


def _two_lift_routine(lifter):
    """A routine of press and row, last done three days ago: 100 × 8 twice,
    then 50 × 8 twice."""
    with flask_app.app_context():
        press, row_ = lifter.exercise('press'), lifter.exercise('row')
        routine = lifter.routine('push', [press, row_])
        workout = lifter.workout(3 * DAY, template=routine, finished=True)
        lifter.row(workout, press, 1, done=[(100, 8)] * 2)
        lifter.row(workout, row_, 2, done=[(50, 8)] * 2)
        db.session.commit()
        return routine.id, press.id, row_.id


def test_a_deload_workout_aims_at_nothing(lifter):
    routine_id, _press_id, _row_id_ = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)

    lifter.client().post(f'/gym/session/{workout_id}/deload', data={'on': '1', 'pct': '70'})

    assert _payload(lifter, workout_id)['next_targets'] == {}


def test_a_deload_marked_after_a_set_hints_what_it_would_lift(lifter):
    """D4: marked after the first set, the deload only labels the workout and
    nothing rescales mid-workout -- so every exercise not started yet says
    what the deload would have planned."""
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)
    press_row = _row_id(workout_id, press_id)
    with flask_app.app_context():
        first = SessionSet.query.filter_by(session_exercise_id=press_row, position=1).one()
        first.completed, first.completed_at = True, lifter.now
        db.session.commit()

    lifter.client().post(f'/gym/session/{workout_id}/deload', data={'on': '1', 'pct': '70'})

    assert _plan(workout_id)[1] == (row_exercise_id, [(50, 8)] * 2)
    assert _payload(lifter, workout_id)['deload_hints'] == {
        str(_row_id(workout_id, row_exercise_id)): 35.0}


def test_a_deload_that_rescaled_the_plan_hints_nothing(lifter):
    routine_id, _press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)

    lifter.client().post(f'/gym/session/{workout_id}/deload', data={'on': '1', 'pct': '70'})

    assert _plan(workout_id)[1] == (row_exercise_id, [(35, 10)] * 2)
    assert _payload(lifter, workout_id)['deload_hints'] == {}


def test_the_card_gives_one_answer_to_what_to_lift(lifter):
    """The "Bereit" line and the stall line's own step-up are gone: the
    target is the one answer (the stall line keeps its fact). Their fields
    stayed, saying nothing, while a page loaded before B5's deploy could
    still read them unguarded; B5 has been live since 09-25, so they are
    gone too (B10b)."""
    routine_id, _press_id, _row_id_ = _two_lift_routine(lifter)
    body = _payload(lifter, _start(lifter, routine_id))

    assert 'stall_next_weight' not in body
    assert 'ready_for_more' not in body


def test_joining_under_your_own_routine_fills_it_and_plans_by_it(lifter):
    partner_id = lifter.partner()
    with flask_app.app_context():
        press = lifter.exercise('press')
        leader_workout = lifter.workout(dt.timedelta(minutes=10))
        lifter.row(leader_workout, press, 1, open_=3)
        theirs = lifter.routine('their push', [press], user_id=partner_id)
        workout = lifter.workout(6 * DAY, user_id=partner_id, template=theirs, finished=True)
        lifter.row(workout, press, 1, done=[(80, 9)] * 5)
        # The seed pick (the newest of equals) holds three: five planned is
        # the routine speaking.
        newer = lifter.workout(3 * DAY, user_id=partner_id, template=theirs, finished=True)
        lifter.row(newer, press, 1, done=[(80, 9)] * 3)
        invite = SharedSession(leader_session_id=leader_workout.id, leader_user_id=lifter.user_id,
                               follower_user_id=partner_id)
        db.session.add(invite)
        db.session.commit()
        invite_id, routine_id, press_id = invite.id, theirs.id, press.id

    response = lifter.client(partner_id).post(f'/gym/shared/{invite_id}/accept',
                                              data={'template_id': routine_id})

    assert response.status_code == 302
    assert _routine_rows(routine_id) == [(press_id, 5, 7, 11)]
    assert _plan(_running(partner_id)) == [(press_id, [(80, 9)] * 5)]


# -- Changing the plan from the live sheet (B5 step 7) ----------------------

JSON = {'Accept': 'application/json'}


def _edit(lifter, row_id, sets, rep_min, rep_max, user_id=None):
    return lifter.client(user_id).post(
        f'/gym/session-exercise/{row_id}/routine-plan',
        data={'sets': sets, 'rep_min': rep_min, 'rep_max': rep_max}, headers=JSON)


def test_the_payload_carries_the_routines_plan_for_each_exercise_it_holds(lifter):
    """Where the sheet's steppers start: the routine row's numbers, keyed by
    workout row. An exercise the routine does not hold has none to change."""
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        db.session.commit()
        curl_id = curl.id
    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id}, headers=JSON)

    assert _payload(lifter, workout_id)['routine_plans'] == {
        str(_row_id(workout_id, press_id)): {'sets': 2, 'rep_min': 6, 'rep_max': 10},
        str(_row_id(workout_id, row_exercise_id)): {'sets': 2, 'rep_min': 6, 'rep_max': 10}}


def test_a_row_not_filled_yet_starts_where_its_history_would_fill_it(lifter):
    """A workout started before routines kept a plan, or an exercise added to
    the routine since: the steppers show what the next start would fill in --
    the routine's own workouts first, so five sets of press outside it since
    do not count."""
    routine_id, press_id, _row_exercise_id = _two_lift_routine(lifter)
    with flask_app.app_context():
        _history(lifter, db.session.get(Exercise, press_id), 1, [(100, 8)] * 5)
        db.session.commit()
    workout_id = _start(lifter, routine_id)
    with flask_app.app_context():
        for row in TemplateExercise.query.filter_by(template_id=routine_id):
            row.target_sets = row.rep_min = row.rep_max = None
        db.session.commit()

    plans = _payload(lifter, workout_id)['routine_plans']

    assert plans[str(_row_id(workout_id, press_id))] == {'sets': 2, 'rep_min': 6, 'rep_max': 10}


def test_the_sheet_changes_the_routines_plan_and_not_the_workouts_sets(lifter):
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)
    press_row = _row_id(workout_id, press_id)

    response = _edit(lifter, press_row, 4, 5, 8)

    assert response.status_code == 200
    assert _routine_rows(routine_id) == [(press_id, 4, 5, 8), (row_exercise_id, 2, 6, 10)]
    # The count applies from the next workout: today's sets stay as seeded.
    assert _plan(workout_id)[0] == (press_id, [(100, 8)] * 2)
    assert response.get_json()['routine_plans'][str(press_row)] == {
        'sets': 4, 'rep_min': 5, 'rep_max': 8}


def test_the_target_reads_a_changed_range_at_once(lifter):
    """8 reps is the top of 5-8: both sets step up, back to the bottom."""
    routine_id, press_id, _row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)
    press_row = _row_id(workout_id, press_id)

    body = _edit(lifter, press_row, 2, 5, 8).get_json()

    assert body['next_targets'][str(press_row)] == [{'weight': 102.5, 'reps': 5}] * 2


@pytest.mark.parametrize('sets, rep_min, rep_max', [
    (0, 6, 10), (11, 6, 10), ('', 6, 10), ('drei', 6, 10), (2.5, 6, 10),
    (3, 0, 10), (3, 9, 8), (3, 6, 101), (3, 6, ''),
])
def test_a_plan_the_routine_cannot_keep_is_refused_with_why(lifter, sets, rep_min, rep_max):
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)

    response = _edit(lifter, _row_id(workout_id, press_id), sets, rep_min, rep_max)

    assert response.status_code == 400
    assert response.get_json()['error'] == (
        'Sätze 1 bis 10, Wiederholungen 1 bis 100 — „von“ nicht über „bis“.')
    assert _routine_rows(routine_id) == [(press_id, 2, 6, 10), (row_exercise_id, 2, 6, 10)]


def test_an_exercise_the_routine_does_not_hold_has_no_plan_to_change(lifter):
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        db.session.commit()
        curl_id = curl.id
    lifter.client().post(f'/gym/session/{workout_id}/exercises/add',
                         data={'exercise_id': curl_id}, headers=JSON)

    response = _edit(lifter, _row_id(workout_id, curl_id), 3, 6, 10)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Die Routine dieses Workouts hat die Übung nicht.'
    assert _routine_rows(routine_id) == [(press_id, 2, 6, 10), (row_exercise_id, 2, 6, 10)]


def test_a_workout_without_a_routine_has_no_plan_to_change(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        workout = lifter.workout(dt.timedelta(minutes=10))
        lifter.row(workout, press, 1, open_=3)
        db.session.commit()
        workout_id, press_id = workout.id, press.id

    response = _edit(lifter, _row_id(workout_id, press_id), 3, 6, 10)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Dieses Workout hat keine Routine.'
    assert _payload(lifter, workout_id)['routine_plans'] == {}


def test_someone_elses_row_is_not_theirs_to_plan(lifter):
    partner_id = lifter.partner()
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    workout_id = _start(lifter, routine_id)

    response = _edit(lifter, _row_id(workout_id, press_id), 4, 5, 8, user_id=partner_id)

    assert response.status_code == 404
    assert _routine_rows(routine_id) == [(press_id, 2, 6, 10), (row_exercise_id, 2, 6, 10)]


def test_a_finished_workouts_sheet_changes_no_plan(lifter):
    routine_id, press_id, row_exercise_id = _two_lift_routine(lifter)
    with flask_app.app_context():
        finished = WorkoutSession.query.filter_by(template_id=routine_id).one()
        finished_id = finished.id

    response = _edit(lifter, _row_id(finished_id, press_id), 4, 5, 8)

    assert response.status_code == 409
    assert _routine_rows(routine_id) == [(press_id, None, None, None),
                                         (row_exercise_id, None, None, None)]


def test_a_workout_under_someone_elses_routine_has_no_plan_to_change(lifter):
    """Only your own routine: a workout filed under another lifter's -- a
    partner's -- neither shows its plan nor changes it."""
    partner_id = lifter.partner()
    with flask_app.app_context():
        press = lifter.exercise('press')
        theirs = lifter.routine('their push', [press], plan={press.id: (3, 6, 10)},
                                user_id=partner_id)
        workout = lifter.workout(dt.timedelta(minutes=10), template=theirs)
        lifter.row(workout, press, 1, open_=3)
        db.session.commit()
        workout_id, press_id, routine_id = workout.id, press.id, theirs.id

    response = _edit(lifter, _row_id(workout_id, press_id), 4, 5, 8)

    assert response.status_code == 400
    assert _payload(lifter, workout_id)['routine_plans'] == {}
    assert _routine_rows(routine_id) == [(press_id, 3, 6, 10)]


def _substitute_id(workout_id):
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        return next(row.id for row in workout.exercises if row.replaces_id is not None)


def test_a_substitute_has_no_plan_of_its_own_to_change(lifter):
    """Swapped in for the press, the incline press stands in the press's
    slot: the routine's own incline row (slot 2) is not its plan to show or
    to change."""
    with flask_app.app_context():
        press, incline = lifter.exercise('press'), lifter.exercise('incline')
        routine = lifter.routine('push', [press, incline],
                                 plan={press.id: (4, 6, 10), incline.id: (3, 8, 12)})
        db.session.commit()
        routine_id, press_id, incline_id = routine.id, press.id, incline.id
    workout_id = _start(lifter, routine_id)
    lifter.client().post(f'/gym/session-exercise/{_row_id(workout_id, press_id)}/replace',
                         data={'exercise_id': incline_id})
    substitute_id = _substitute_id(workout_id)
    with flask_app.app_context():
        own_id = next(row.id for row in db.session.get(WorkoutSession, workout_id).exercises
                      if row.exercise_id == incline_id and row.id != substitute_id)

    response = _edit(lifter, substitute_id, 5, 6, 10)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Ein Ersatz hat in der Routine keinen eigenen Plan.'
    assert _routine_rows(routine_id) == [(press_id, 4, 6, 10), (incline_id, 3, 8, 12)]
    assert _payload(lifter, workout_id)['routine_plans'] == {
        str(own_id): {'sets': 3, 'rep_min': 8, 'rep_max': 12}}


# -- Found in the B5 review and the M5 mockup (09-24) -------------------------

def test_after_a_step_up_the_card_climbs_from_the_last_workout(lifter):
    """60 × 10 filled the range, so the last workout stepped up to 62,5 × 6.
    Now one rep more at 62,5 (D2: +1 rep each time) -- not the same step up
    again, which the stronger 60 × 10 (the seed pick: best e1RM of four
    weeks) would ask for until 62,5 × 9 beat it."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (3, 6, 10)})
        _history(lifter, press, 6, [(60, 10)] * 3, template=routine)
        _history(lifter, press, 3, [(62.5, 6)] * 3, template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id

    workout_id = _start(lifter, routine_id)

    assert _payload(lifter, workout_id)['next_targets'] == {
        str(_row_id(workout_id, press_id)): [{'weight': 62.5, 'reps': 7}] * 3}


def test_a_record_in_this_workout_ends_the_stall_on_the_card(lifter):
    """"Stagniert · 4 Workouts ohne neuen e1RM-PR" stood beside "Rekord ·
    Satz 1 ist ein neuer Bestwert": a record today ends the stall."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (3, 6, 10)})
        _history(lifter, press, 15, [(100, 8)] * 3, template=routine)
        for days_ago in (12, 9, 6, 3):
            _history(lifter, press, days_ago, [(100, 7)] * 3, template=routine)
        db.session.commit()
        routine_id, press_id = routine.id, press.id
    workout_id = _start(lifter, routine_id)
    row_id = _row_id(workout_id, press_id)
    assert _payload(lifter, workout_id)['stagnation_counts'] == {str(row_id): 4}
    with flask_app.app_context():
        first = (SessionSet.query.filter_by(session_exercise_id=row_id)
                 .order_by(SessionSet.position).first().id)

    lifter.client().post(f'/gym/set/{first}/toggle_complete',
                         data={'completed': '1', 'weight': '100', 'reps': '9'}, headers=JSON)

    body = _payload(lifter, workout_id)
    assert body['record_set_ids'] == [first]
    assert body['stagnation_counts'] == {}


def test_a_followers_copy_of_a_substitute_plans_their_slots_count(lifter):
    """The leader swaps the press for dips: the follower's dips stand in the
    slot of their own routine's press -- four sets, as target and plan both
    say, not the two their last dips held."""
    partner_id = lifter.partner()
    with flask_app.app_context():
        press, dips = lifter.exercise('press'), lifter.exercise('dips')
        theirs = lifter.routine('their push', [press], plan={press.id: (4, 6, 10)},
                                user_id=partner_id)
        earlier = lifter.workout(3 * DAY, user_id=partner_id, finished=True)
        lifter.row(earlier, dips, 1, done=[(50, 8)] * 2)
        leader_workout = lifter.workout(dt.timedelta(minutes=10))
        leader_press = lifter.row(leader_workout, press, 1, open_=3)
        invite = SharedSession(leader_session_id=leader_workout.id, leader_user_id=lifter.user_id,
                               follower_user_id=partner_id)
        db.session.add(invite)
        db.session.commit()
        invite_id, routine_id = invite.id, theirs.id
        leader_press_id, dips_id = leader_press.id, dips.id
    lifter.client(partner_id).post(f'/gym/shared/{invite_id}/accept',
                                   data={'template_id': routine_id})

    lifter.client().post(f'/gym/session-exercise/{leader_press_id}/replace',
                         data={'exercise_id': dips_id})

    assert _plan(_running(partner_id)) == [(dips_id, [(50, 8)] * 4)]


# -- the exercise page's "Nächstes Ziel" (D9 A) --------------------------------

def _goal(lifter, exercise_id):
    return lifter.client().get(f'/gym/exercises/{exercise_id}/detail.json').get_json()['goal']


def test_the_exercise_page_aims_where_the_live_card_will(lifter):
    """One answer to "what do I lift next" (D9): the page says, before the
    workout exists, what the card says once it does."""
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (3, 6, 10)})
        done = _history(lifter, press, 3, [(40, 8), (35, 9), (35, 8)], template=routine)
        db.session.commit()
        routine_id, press_id, done_at = routine.id, press.id, done.started_at

    goal = _goal(lifter, press_id)
    assert goal == {
        'sets': [{'weight': 40.0, 'reps': 9}, {'weight': 35.0, 'reps': 10},
                 {'weight': 35.0, 'reps': 9}],
        'last_sets': [{'weight': 40.0, 'reps': 8}, {'weight': 35.0, 'reps': 9},
                      {'weight': 35.0, 'reps': 8}],
        'last_at': done_at.isoformat(), 'rep_min': 6, 'rep_max': 10,
        'stepped': False, 'step_ups': [42.5, 37.5, 37.5],
    }
    workout_id = _start(lifter, routine_id)
    assert _payload(lifter, workout_id)['next_targets'][str(_row_id(workout_id, press_id))] \
        == goal['sets']


def test_the_page_plans_the_routines_count_not_last_times(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (2, 6, 10)})
        _history(lifter, press, 3, [(40, 8)] * 3, template=routine)
        db.session.commit()
        press_id = press.id

    assert _goal(lifter, press_id)['sets'] == [{'weight': 40.0, 'reps': 9}] * 2


def test_the_page_says_a_target_that_already_stepped_up(lifter):
    with flask_app.app_context():
        press = lifter.exercise('press')
        routine = lifter.routine('push', [press], plan={press.id: (2, 7, 11)})
        _history(lifter, press, 3, [(85, 11), (80, 12)], template=routine)
        db.session.commit()
        press_id = press.id

    goal = _goal(lifter, press_id)
    assert goal['sets'] == [{'weight': 87.5, 'reps': 7}, {'weight': 82.5, 'reps': 7}]
    assert (goal['stepped'], goal['step_ups']) == (True, None)


def test_a_bodyweight_set_at_the_top_goes_on_by_a_rep_and_is_no_step(lifter):
    """0 kg at the top of the range: one rep more, past it -- and the page
    must not say "eine Stufe höher" of a weight that did not move."""
    with flask_app.app_context():
        dips = lifter.exercise('dips')
        routine = lifter.routine('push', [dips], plan={dips.id: (3, 6, 10)})
        _history(lifter, dips, 3, [(0, 10)] * 3, template=routine)
        db.session.commit()
        dips_id = dips.id

    goal = _goal(lifter, dips_id)
    assert goal['sets'] == [{'weight': 0.0, 'reps': 11}] * 3
    assert (goal['stepped'], goal['step_ups']) == (False, [None, None, None])


def test_the_page_plans_an_exercise_outside_any_routine_freeform(lifter):
    # As many sets as last time, in the range its history gives: 10-14 round 12.
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        _history(lifter, curl, 3, [(20, 12)] * 3)
        db.session.commit()
        curl_id = curl.id

    goal = _goal(lifter, curl_id)
    assert goal['sets'] == [{'weight': 20.0, 'reps': 13}] * 3
    assert (goal['rep_min'], goal['rep_max'], goal['step_ups']) == (10, 14, [22.5] * 3)


def test_a_routine_that_dropped_the_exercise_plans_it_freeform(lifter):
    with flask_app.app_context():
        press, fly = lifter.exercise('press'), lifter.exercise('fly')
        routine = lifter.routine('push', [press, fly], plan={press.id: (2, 6, 10)})
        _history(lifter, press, 3, [(40, 8)] * 3, template=routine)
        TemplateExercise.query.filter_by(template_id=routine.id, exercise_id=press.id).delete()
        db.session.commit()
        press_id = press.id

    assert len(_goal(lifter, press_id)['sets']) == 3


def test_the_page_builds_on_the_newest_workout_that_was_no_deload(lifter):
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        real = _history(lifter, curl, 5, [(20, 10)] * 3)
        _history(lifter, curl, 2, [(15, 4)] * 3, is_deload=True)
        db.session.commit()
        curl_id, real_at = curl.id, real.started_at

    goal = _goal(lifter, curl_id)
    assert goal['last_sets'] == [{'weight': 20.0, 'reps': 10}] * 3
    assert goal['last_at'] == real_at.isoformat()


def test_the_page_has_no_goal_with_only_deloads_to_build_on(lifter):
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        _history(lifter, curl, 2, [(15, 4)] * 3, is_deload=True)
        db.session.commit()
        curl_id = curl.id

    assert _goal(lifter, curl_id) is None


def test_a_lift_twice_in_its_newest_workout_builds_on_the_later_slot(lifter):
    # As the live card's base: the later slot of that workout.
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        workout = lifter.workout(3 * DAY, finished=True)
        lifter.row(workout, curl, 1, done=[(20, 10)] * 3)
        lifter.row(workout, curl, 3, done=[(12, 12)] * 2)
        db.session.commit()
        curl_id = curl.id

    assert _goal(lifter, curl_id)['last_sets'] == [{'weight': 12.0, 'reps': 12}] * 2


def test_a_lift_twice_in_its_newest_workout_builds_on_the_row_logged_last(lifter):
    # The live card builds on seeding's newest row -- by start, then by row
    # id -- whatever slot it sat in; the page sorted by slot and built on
    # the other one (I2 review). Here the third slot was logged first.
    with flask_app.app_context():
        curl = lifter.exercise('curl')
        routine = lifter.routine('arms', [curl], plan={curl.id: (3, 8, 12)})
        workout = lifter.workout(3 * DAY, template=routine, finished=True)
        lifter.row(workout, curl, 3, done=[(12, 12)] * 2)
        lifter.row(workout, curl, 1, done=[(20, 10)] * 3)
        db.session.commit()
        routine_id, curl_id = routine.id, curl.id

    goal = _goal(lifter, curl_id)
    assert goal['last_sets'] == [{'weight': 20.0, 'reps': 10}] * 3
    workout_id = _start(lifter, routine_id)
    assert _payload(lifter, workout_id)['next_targets'][str(_row_id(workout_id, curl_id))] \
        == goal['sets']

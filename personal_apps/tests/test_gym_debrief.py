"""The debrief (D10, I4): what was done, the one comparison with the
routine's earlier workouts, and the plan for next time -- the payload the
finished page is mounted from."""
import datetime as dt

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from models import Exercise, WorkoutTemplate
from gym_lifter import lifter  # noqa: F401 -- the fixture

DAY = dt.timedelta(days=1)


def _workout(lifter, days_ago, lifts, template=None, is_deload=False, planned=None):
    """A finished workout `days_ago` days back. `lifts`: (exercise, [(weight,
    reps)]) in order -- a row with nothing done keeps one open set."""
    workout = lifter.workout(days_ago * DAY, template=template, finished=True,
                             is_deload=is_deload)
    workout.planned_sets = planned
    for position, (exercise, sets) in enumerate(lifts, start=1):
        lifter.row(workout, exercise, position, done=sets, open_=0 if sets else 1)
    return workout


def _page(lifter, workout_id):
    """The payload the workout's page is mounted from: the debrief's, or for
    a running workout the live screen's."""
    response = lifter.client().get(f'/gym/session/{workout_id}')
    assert response.status_code == 200
    return embedded_payload(response.get_data(as_text=True))


def test_the_comparison_is_to_the_two_newest_earlier_workouts_done_in_full(lifter):
    """D10: the mean of the last two FULL non-deload workouts of the routine
    before this one -- four in five planned sets done; one finished before
    that count was kept, by the sets it still holds. A deload, one cut
    short, an empty one, one that moved nothing, another routine's and a
    later one are passed over; a third full one is never read."""
    with flask_app.app_context():
        lift = lifter.exercise('cmp')
        push, pull = lifter.routine('cmp push', [lift]), lifter.routine('cmp pull', [lift])
        _workout(lifter, 14, [(lift, [(100.0, 8)] * 3)], push, planned=3)
        uncounted = _workout(lifter, 12, [(lift, [(100.0, 10)] * 3)], push)
        four_of_five = _workout(lifter, 10, [(lift, [(100.0, 10)] * 4)], push, planned=5)
        _workout(lifter, 9, [(lift, [(0.0, 10)] * 3)], push, planned=3)
        _workout(lifter, 8, [(lift, [(120.0, 10)] * 3)], push, planned=4)
        _workout(lifter, 7, [(lift, [(50.0, 10)] * 4)], push, is_deload=True)
        _workout(lifter, 6, [(lift, [])], push)
        _workout(lifter, 5, [(lift, [(125.0, 10)] * 4)], pull)
        today = _workout(lifter, 3, [(lift, [(100.0, 10)] * 4)], push, planned=4)
        _workout(lifter, 1, [(lift, [(150.0, 10)] * 4)], push)
        db.session.commit()
        ids = today.id, four_of_five.id, uncounted.id

    comparison = _page(lifter, ids[0])['comparison']
    assert [(workout['id'], workout['volume']) for workout in comparison['against']] == [
        (ids[1], 4000.0), (ids[2], 3000.0)]
    assert comparison['pct'] == 14          # 4000 kg against a mean of 3500


def test_the_comparison_reads_on_past_a_page_of_workouts_cut_short(lifter):
    """The earlier workouts are read a page at a time: two full ones behind
    nine cut short are still found."""
    with flask_app.app_context():
        lift = lifter.exercise('cmp paging')
        push = lifter.routine('cmp paging', [lift])
        full = [_workout(lifter, days, [(lift, [(100.0, 10)] * 2)], push, planned=2)
                for days in (13, 12)]
        for days in range(11, 2, -1):
            _workout(lifter, days, [(lift, [(100.0, 10)])], push, planned=2)
        today = _workout(lifter, 1, [(lift, [(110.0, 10)] * 2)], push, planned=2)
        db.session.commit()
        ids = today.id, full[1].id, full[0].id

    comparison = _page(lifter, ids[0])['comparison']
    assert [workout['id'] for workout in comparison['against']] == [ids[1], ids[2]]
    assert comparison['pct'] == 10


def test_no_comparison_without_two_full_workouts_to_measure_a_full_one_by(lifter):
    """None, and the page silent: for a workout cut short, a deload, a
    routine done in full only once before, and a workout without a routine
    -- however many full ones went before it."""
    with flask_app.app_context():
        lift = lifter.exercise('cmp none')
        push = lifter.routine('cmp none push', [lift])
        pull = lifter.routine('cmp none pull', [lift])
        full = [(lift, [(100.0, 10)] * 3)]
        for days in (20, 19):
            _workout(lifter, days, full, push, planned=3)
            _workout(lifter, days, full)
        cut_short = _workout(lifter, 5, [(lift, [(100.0, 10)] * 2)], push, planned=3)
        deload = _workout(lifter, 4, full, push, is_deload=True, planned=3)
        _workout(lifter, 18, full, pull, planned=3)
        once_before = _workout(lifter, 3, full, pull, planned=3)
        freeform = _workout(lifter, 2, full)
        db.session.commit()
        ids = {'cut short': cut_short.id, 'deload': deload.id,
               'only one before': once_before.id, 'no routine': freeform.id}

    assert {case: _page(lifter, workout_id)['comparison']
            for case, workout_id in ids.items()} == {case: None for case in ids}


def test_full_counts_the_sets_a_workout_held_and_the_ones_its_skips_dropped(lifter):
    """Full by the sets the workout held: one finished before the count was
    kept (planned_sets NULL) by its open sets, and a skipped exercise by the
    sets its routine slot keeps -- the skip deleted its open ones -- unless a
    substitute took the slot. Each workout is judged on its own page: a
    comparison, or none for one cut short; and passed over as an earlier
    workout when cut short."""
    with flask_app.app_context():
        lift, second, alt = (lifter.exercise(name) for name in ('held', 'held 2', 'held alt'))
        push = lifter.routine('held', [lift, second],
                              plan={lift.id: (4, 8, 12), second.id: (1, 8, 12)})
        full = [(lift, [(100.0, 10)] * 4), (second, [(50.0, 10)])]
        for days in (12, 11):
            _workout(lifter, days, full, push, planned=5)
        # The finish kept what the workouts below still held, then deleted
        # the open sets; each skip had deleted its row's open sets before.
        ended = _workout(lifter, 10, full[:1], push, planned=5)
        lifter.row(ended, second, 2)                                     # 4 of 5
        outright = _workout(lifter, 9, full[:1], push, planned=4)
        lifter.row(outright, second, 2, skipped=True)                   # 4 of 5
        three = _workout(lifter, 8, full[1:], push, planned=4)
        lifter.row(three, lift, 2, done=[(100.0, 10)] * 3, skipped=True)  # 4 of 5
        swapped = _workout(lifter, 7, full[1:], push, planned=5)
        original = lifter.row(swapped, lift, 2, skipped=True)
        lifter.row(swapped, alt, 2, done=[(90.0, 10)] * 4, replaces=original)  # 5 of 5
        two = _workout(lifter, 6, full[1:], push, planned=3)
        lifter.row(two, lift, 2, done=[(100.0, 10)] * 2, skipped=True)    # 3 of 5
        # Finished before B4, which kept the open sets: 1 of 5.
        open_left = lifter.workout(5 * DAY, template=push, finished=True)
        lifter.row(open_left, lift, 1, done=[(100.0, 10)], open_=3)
        lifter.row(open_left, second, 2, open_=1)
        today = _workout(lifter, 3, [(lift, [(110.0, 10)] * 4), full[1]], push, planned=5)
        db.session.commit()
        cases = {'ended early': ended.id, 'skipped outright': outright.id,
                 'skipped after three': three.id, 'skipped and swapped': swapped.id,
                 'skipped after two': two.id, 'open sets kept': open_left.id}
        ids = today.id, swapped.id, three.id

    assert {case: _page(lifter, workout_id)['comparison'] is not None
            for case, workout_id in cases.items()} == {
        'ended early': True, 'skipped outright': True, 'skipped after three': True,
        'skipped and swapped': True, 'skipped after two': False, 'open sets kept': False}
    comparison = _page(lifter, ids[0])['comparison']
    assert [workout['id'] for workout in comparison['against']] == [ids[1], ids[2]]
    assert comparison['pct'] == 29          # 4900 kg against a mean of 3800


def test_workouts_started_at_the_same_moment_run_in_the_order_they_were_logged(lifter):
    """Two workouts can share a start: the one logged first is the earlier
    one -- for the comparison and for where the plan went alike."""
    with flask_app.app_context():
        lift = lifter.exercise('same start')
        push = lifter.routine('same start', [lift])
        oldest = _workout(lifter, 9, [(lift, [(100.0, 10)] * 3)], push, planned=3)
        before, today, after = (_workout(lifter, 5, [(lift, [(weight, 10)] * 3)], push, planned=3)
                                for weight in (90.0, 110.0, 120.0))
        db.session.commit()
        ids = oldest.id, before.id, today.id, after.id

    debrief, latest = _page(lifter, ids[2]), _page(lifter, ids[3])
    assert [workout['id'] for workout in debrief['comparison']['against']] == [ids[1], ids[0]]
    assert [workout['id'] for workout in latest['comparison']['against']] == [ids[2], ids[1]]
    assert [_page(lifter, ids[1])['plan_moved_to']['id'], debrief['plan_moved_to']['id']] == [
        ids[3], ids[3]]
    assert latest['plan_moved_to'] is None


def test_a_later_visit_points_to_where_the_plan_went(lifter):
    """D10: once a newer workout of the routine has a set that counts, the
    plan for next time is built there -- the debrief names the newest such
    one, and its rows plan only what the next live card still builds on
    them: a lift the newer workouts left out. A newer one left empty, one
    still running, another routine's: no plan went there."""
    with flask_app.app_context():
        lift, other = lifter.exercise('moved'), lifter.exercise('moved other')
        dropped = lifter.exercise('moved dropped')
        push = lifter.routine('moved push', [lift, dropped], plan={lift.id: (3, 8, 12)})
        pull = lifter.routine('moved pull', [other])
        sets = [(60.0, 10), (60.0, 9), (60.0, 8)]
        first = _workout(lifter, 6, [(lift, sets), (dropped, [(20.0, 12)] * 3)], push)
        middle = _workout(lifter, 4, [(lift, sets)], push)
        newest = _workout(lifter, 3, [(lift, sets)], push)
        empty = lifter.workout(2 * DAY, template=push, finished=True)
        lifter.row(empty, lift, 1, ticked_empty=2, open_=1)
        _workout(lifter, 1, [(other, [(40.0, 10)])], pull)
        running = lifter.workout(dt.timedelta(minutes=5), template=push)
        lifter.row(running, lift, 1, done=[(60.0, 11)], open_=2,
                   done_ago=[dt.timedelta(minutes=1)])
        db.session.commit()
        ids = first.id, middle.id, newest.id

    pages = [_page(lifter, workout_id) for workout_id in ids]
    assert [(page['plan_moved_to'] or {}).get('id') for page in pages] == [ids[2], ids[2], None]
    assert [entry['next_sets'] is not None for entry in pages[0]['exercises']] == [False, True]
    assert [entry['next_sets'] for entry in pages[1]['exercises']] == [None]
    assert [entry['next_sets'] for entry in pages[2]['exercises']] == [
        [{'weight': 60.0, 'reps': 11}, {'weight': 60.0, 'reps': 10},
         {'weight': 60.0, 'reps': 9}]]


def test_next_time_is_what_the_next_live_card_aims_at(lifter):
    """"Nächstes Mal" is the live card's own target (plan.target_for): the
    routine's set count and rep range, built on this workout's sets -- and
    the next workout of the routine shows the same numbers."""
    with flask_app.app_context():
        lift = lifter.exercise('next time')
        push = lifter.routine('next time', [lift], plan={lift.id: (4, 6, 10)})
        done = _workout(lifter, 2, [(lift, [(60.0, 10), (60.0, 9), (60.0, 8)])], push)
        db.session.commit()
        done_id, push_id, lift_id = done.id, push.id, lift.id

    debrief = _page(lifter, done_id)
    assert debrief['plan_base'] is None     # named for a deload only
    next_sets = debrief['exercises'][0]['next_sets']
    # Four sets, the last one repeated; the set at the top of 6-10 waits there.
    assert next_sets == [{'weight': 60.0, 'reps': 10}, {'weight': 60.0, 'reps': 10},
                         {'weight': 60.0, 'reps': 9}, {'weight': 60.0, 'reps': 9}]
    with flask_app.app_context():
        push, lift = db.session.get(WorkoutTemplate, push_id), db.session.get(Exercise, lift_id)
        running = lifter.workout(dt.timedelta(minutes=5), template=push)
        row = lifter.row(running, lift, 1, open_=4)
        db.session.commit()
        running_id, row_id = running.id, row.id
    assert _page(lifter, running_id)['next_targets'][str(row_id)] == next_sets


def test_next_time_is_left_out_where_the_exercise_has_moved_on(lifter):
    """Said only where the next live card builds on this row: not once the
    exercise ran later in another routine, and of a lift done twice in the
    workout only on the row logged later -- the one seeding takes."""
    with flask_app.app_context():
        lift, moved, twice = (lifter.exercise(name) for name in ('stays', 'moves on', 'twice'))
        push = lifter.routine('moved on push', [lift, moved, twice])
        pull = lifter.routine('moved on pull', [moved])
        sets = [(50.0, 10)] * 3
        today = _workout(lifter, 3, [(lift, sets), (moved, sets), (twice, sets),
                                     (twice, sets)], push)
        _workout(lifter, 1, [(moved, sets)], pull)
        db.session.commit()
        today_id = today.id

    debrief = _page(lifter, today_id)
    assert debrief['plan_moved_to'] is None
    assert [entry['next_sets'] is not None for entry in debrief['exercises']] == [
        True, False, False, True]


def test_a_workout_without_a_routine_keeps_its_plan(lifter):
    """No routine, nothing for a later workout to take the plan to: a later
    one without a routine is no newer workout of this one's."""
    with flask_app.app_context():
        lift, other = lifter.exercise('freeform plan'), lifter.exercise('freeform other')
        today = _workout(lifter, 3, [(lift, [(50.0, 10)] * 3)])
        _workout(lifter, 1, [(other, [(30.0, 10)] * 3)])
        db.session.commit()
        today_id = today.id

    debrief = _page(lifter, today_id)
    assert debrief['plan_moved_to'] is None
    assert debrief['exercises'][0]['next_sets'] is not None


def _deload_after(lifter, days_between):
    """A workout of the push routine, then a deload of it `days_between`
    days later: two lifts, both planned 3 x 8-12. Also returns a second
    routine holding both lifts."""
    lift, second = lifter.exercise('deload plan'), lifter.exercise('deload plan 2')
    push = lifter.routine('deload push', [lift, second],
                          plan={lift.id: (3, 8, 12), second.id: (3, 8, 12)})
    pull = lifter.routine('deload pull', [lift, second])
    before = _workout(lifter, 3 + days_between, [(lift, [(60.0, 10), (60.0, 9), (60.0, 8)]),
                                                  (second, [(40.0, 10)] * 3)], push)
    deload = _workout(lifter, 3, [(lift, [(30.0, 10)] * 3), (second, [(20.0, 10)] * 3)],
                      push, is_deload=True)
    return lift, second, pull, before, deload


def test_a_deload_plans_from_the_workout_before_it(lifter):
    """A deload aims at nothing: its "Nächstes Mal" is the next live card's,
    built on the workout before it -- named, while every row builds on the
    same one. And it moves no plan: the workout before it still plans, and
    points nowhere."""
    with flask_app.app_context():
        *_, before, deload = _deload_after(lifter, 7)
        db.session.commit()
        ids = before.id, deload.id

    debrief, earlier = _page(lifter, ids[1]), _page(lifter, ids[0])
    assert debrief['plan_base']['id'] == ids[0]
    next_sets = [[{'weight': 60.0, 'reps': 11}, {'weight': 60.0, 'reps': 10},
                  {'weight': 60.0, 'reps': 9}],
                 [{'weight': 40.0, 'reps': 11}] * 3]
    assert [entry['next_sets'] for entry in debrief['exercises']] == next_sets
    assert earlier['plan_moved_to'] is None
    assert [entry['next_sets'] for entry in earlier['exercises']] == next_sets


def test_a_deload_names_no_one_workout_when_its_rows_build_on_two(lifter):
    """The second lift was done again in between, in another routine: that
    is what the next push workout builds it on -- and there is no one
    workout the plan builds on to name."""
    with flask_app.app_context():
        _lift, second, pull, _before, deload = _deload_after(lifter, 7)
        _workout(lifter, 5, [(second, [(42.0, 10)] * 3)], pull)
        db.session.commit()
        deload_id = deload.id

    debrief = _page(lifter, deload_id)
    assert debrief['plan_base'] is None
    assert debrief['exercises'][1]['next_sets'] == [{'weight': 42.0, 'reps': 11}] * 3


def test_a_deload_plans_nothing_for_a_lift_done_since(lifter):
    """Lifted again after the deload, in another routine: the next push
    workout builds on that, and the deload's row only says what was done."""
    with flask_app.app_context():
        lift, _second, pull, before, deload = _deload_after(lifter, 7)
        _workout(lifter, 1, [(lift, [(62.0, 10)] * 3)], pull)
        db.session.commit()
        ids = before.id, deload.id

    debrief = _page(lifter, ids[1])
    assert debrief['plan_moved_to'] is None
    assert debrief['exercises'][0]['next_sets'] is None
    assert debrief['exercises'][1]['next_sets'] == [{'weight': 40.0, 'reps': 11}] * 3
    assert debrief['plan_base']['id'] == ids[0]


def test_the_rows_and_the_flare_say_which_set_made_the_record(lifter):
    """The row washes its record sets gold (the live flare's judgement, set
    by set) and says what the record beat; the flare names the set."""
    with flask_app.app_context():
        lift = lifter.exercise('record set')
        _workout(lifter, 9, [(lift, [(80.0, 5)])])
        today = _workout(lifter, 1, [(lift, [(80.0, 8), (82.5, 3)])])
        db.session.commit()
        today_id = today.id

    debrief = _page(lifter, today_id)
    [entry] = debrief['exercises']
    assert [set_row['is_record'] for set_row in entry['set_rows']] == [True, False]
    assert entry['record'] == {'value': 101.3, 'previous': 93.3}
    [record] = debrief['records']
    assert (record['weight'], record['reps'], record['value']) == (80.0, 8, 101.3)


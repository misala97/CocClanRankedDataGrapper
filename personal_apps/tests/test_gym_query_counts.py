"""What a gym request costs in queries, as the history or the workout grows.

Each of these was linear once: a query (or four) per workout exported, per
exercise in the live payload, per row the resume strip looked at (walkthrough
G-095, G-140, G-143). The tests compare a small case with a big one rather
than pin a number, so an unrelated query added somewhere does not break them,
and a new per-row one does.
"""
import datetime as dt

from sqlalchemy import event

from app import app as flask_app
from extensions import db
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import Exercise, WorkoutSession

DAY = dt.timedelta(days=1)
JSON = {'Accept': 'application/json'}
LIVE = {**JSON, 'X-Gym-Surface': 'live', 'X-Gym-Catalogue': 'kept'}


def _queries(call):
    """(response, number of SQL statements) for `call()`."""
    seen = []

    def count(*_args):
        seen.append(1)

    with flask_app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', count)
    try:
        response = call()
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    assert response.status_code == 200, response.status_code
    return response, len(seen)


def _finished_workouts(lifter, count, lifts):
    """`count` finished workouts of `lifts`, each with one swap; their ids."""
    ids = []
    for n in range(count):
        workout = lifter.workout((20 - n) * DAY, finished=True)
        rows = [lifter.row(workout, lift, position, done=[(50, 8)] * 3)
                for position, lift in enumerate(lifts, start=1)]
        # The export names both ends of a swap.
        lifter.row(workout, lifts[0], len(lifts) + 1, done=[(40, 8)], replaces=rows[-1])
        ids.append(workout.id)
    return ids


def test_an_export_costs_the_same_for_six_workouts_as_for_two(lifter):
    """44 workouts were 677 queries: every row's exercise, sets, substitute and
    original loaded one by one (G-095)."""
    with flask_app.app_context():
        lifts = [lifter.exercise(f'export {n}') for n in range(3)]
        ids = _finished_workouts(lifter, 6, lifts)
        db.session.commit()
    client = lifter.client()

    def export(some):
        return lambda: client.get('/gym/export?ids=' + ','.join(map(str, some)))

    export(ids[:1])()  # a first request pays once for things no second one does
    few, few_cost = _queries(export(ids[:2]))
    many, many_cost = _queries(export(ids))
    assert len(many.get_json()['sessions']) == 6
    assert many_cost == few_cost


def test_the_live_payload_costs_the_same_for_eight_exercises_as_for_two(lifter):
    """Eight exercises were 81 queries, and a set tick 83: each row's sets,
    exercise, history pick and plan asked for one at a time (G-140). Under a
    routine not filled yet, so the plan comes from history as well."""
    with flask_app.app_context():
        lifts = [lifter.exercise(f'live {n}') for n in range(8)]
        _finished_workouts(lifter, 3, lifts)
        routine = lifter.routine('live', lifts)
        workout = lifter.workout(dt.timedelta(minutes=10), template=routine)
        for position, lift in enumerate(lifts[:2], start=1):
            lifter.row(workout, lift, position, open_=3)
        db.session.commit()
        workout_id, lift_ids = workout.id, [lift.id for lift in lifts]
    client = lifter.client()
    url = f'/gym/session/{workout_id}/detail.json'

    def tick(set_id):
        return lambda: client.post(f'/gym/set/{set_id}/toggle_complete',
                                   data={'completed': '1'}, headers=LIVE)

    first = client.get(url).get_json()  # a first request pays once, as above
    opened = [s['id'] for s in first['visible_exercises'][0]['sets']]
    assert first['routine_plans']
    _, few = _queries(lambda: client.get(url))
    _, few_tick = _queries(tick(opened[0]))

    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        for position, lift_id in enumerate(lift_ids[2:], start=3):
            lifter.row(workout, db.session.get(Exercise, lift_id), position, open_=3)
        db.session.commit()
    body, many = _queries(lambda: client.get(url))
    _, many_tick = _queries(tick(opened[1]))
    assert len(body.get_json()['routine_plans']) == 8
    assert (many, many_tick) == (few, few_tick)


def test_a_page_with_the_resume_strip_costs_the_same_for_eight_exercises_as_for_two(lifter):
    """The strip walked every row's sets one query at a time, and the
    running workout was looked up twice per page (G-143)."""
    with flask_app.app_context():
        lifts = [lifter.exercise(f'strip {n}') for n in range(8)]
        workout = lifter.workout(dt.timedelta(minutes=10))
        for position, lift in enumerate(lifts[:2], start=1):
            lifter.row(workout, lift, position, done=[(50, 8)] * 3)
        db.session.commit()
        workout_id, lift_ids = workout.id, [lift.id for lift in lifts]
    client = lifter.client()

    def page():
        return client.get('/gym/uebungen')

    page()  # a first request pays once, as above
    _, few = _queries(page)
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        # All done but the last: the strip reads every row to get there.
        for position, lift_id in enumerate(lift_ids[2:], start=3):
            last = position == len(lift_ids)
            lifter.row(workout, db.session.get(Exercise, lift_id), position,
                       done=() if last else [(50, 8)] * 3, open_=3 if last else 0)
        db.session.commit()
    body, many = _queries(page)
    assert ('<span class="resume__meta">pytest gym strip 7</span>'
            in body.get_data(as_text=True))
    assert many == few

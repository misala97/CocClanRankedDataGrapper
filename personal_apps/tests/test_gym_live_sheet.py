"""The live sheet, server side (walkthrough B7): "Anhängen" plans an open set
(Q2, G-060); the live payload and the debrief carry each exercise's bests for
the screen's "Sicher?" (Q5, G-070); a remove says how many done sets it saw.

Runs against the local development database with a throwaway lifter.
"""
import datetime as dt

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import PendingPush, SessionExercise, SessionSet, WorkoutSession

LIVE = {'Accept': 'application/json', 'X-Gym-Surface': 'live'}
MINUTE = dt.timedelta(minutes=1)


def _running(lifter, name, open_=2):
    """A running workout with one exercise: a set done twenty minutes ago,
    then `open_` open sets. Returns (workout id, row id)."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=40 * MINUTE)
        row = lifter.row(workout, lifter.exercise(name), 1, done=((60.0, 8),),
                         done_ago=[20 * MINUTE], open_=open_)
        row.rest_seconds = 120
        db.session.commit()
        return workout.id, row.id


def _add(client, row_id, key, open_):
    data = {'weight': '95', 'reps': '10', 'key': key}
    if open_:
        data['open'] = '1'
    return client.post(f'/gym/session-exercise/{row_id}/sets/add', data=data, headers=LIVE)


def test_a_set_planned_in_the_sheet_waits_open_behind_the_others(lifter):
    """Added done, it jumped the open sets, started a rest, and was judged a
    record before anyone had lifted it -- 95 x 10 beats the 80 x 8 before."""
    workout_id, row_id = _running(lifter, 'plan one')
    with flask_app.app_context():
        earlier = lifter.workout(started_ago=dt.timedelta(days=3), finished=True)
        lifter.row(earlier, db.session.get(SessionExercise, row_id).exercise, 1,
                   done=((80.0, 8),))
        db.session.commit()

    response = _add(lifter.client(), row_id, 'plan-1', open_=True)

    assert response.status_code == 200
    body = response.get_json()
    [row] = [se for se in body['visible_exercises'] if se['id'] == row_id]
    assert [(s['weight'], s['reps'], s['completed']) for s in row['sets']] == [
        (60.0, 8, True), (40.0, 8, False), (40.0, 8, False), (95.0, 10, False)]
    assert row['sets'][-1]['key'] == 'plan-1'
    assert body['record_set_ids'] == []
    with flask_app.app_context():
        assert SessionSet.query.filter_by(client_key='plan-1').one().completed_at is None
        assert db.session.get(WorkoutSession, workout_id).resting_set_id is None
        assert PendingPush.query.filter_by(session_id=workout_id, sent=False).count() == 0


def test_a_planned_set_sent_twice_is_one_set(lifter):
    _, row_id = _running(lifter, 'plan twice')
    client = lifter.client()

    for _ in range(2):
        _add(client, row_id, 'plan-2', open_=True)

    with flask_app.app_context():
        assert SessionSet.query.filter_by(client_key='plan-2').count() == 1


def test_a_set_added_with_nothing_open_is_still_done(lifter):
    """"Satz geschafft" after the last set: the set it adds was lifted."""
    workout_id, row_id = _running(lifter, 'append done', open_=0)

    _add(lifter.client(), row_id, 'done-1', open_=False)

    with flask_app.app_context():
        added = SessionSet.query.filter_by(client_key='done-1').one()
        assert added.completed is True
        assert added.completed_at is not None
        assert db.session.get(WorkoutSession, workout_id).resting_set_id == added.id


def test_the_debrief_adds_a_set_done_whatever_it_is_asked(lifter):
    """"Nachtragen" stays "add as done" (Q2): an open set in a finished
    workout would never be ticked."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=3 * 60 * MINUTE, finished=True)
        row = lifter.row(workout, lifter.exercise('debrief add'), 1, done=((60.0, 8),))
        db.session.commit()
        row_id = row.id

    lifter.client().post(f'/gym/session-exercise/{row_id}/sets/add',
                         data={'weight': '60', 'reps': '8', 'open': '1'},
                         headers={'Accept': 'application/json'})

    with flask_app.app_context():
        sets = (SessionSet.query.filter_by(session_exercise_id=row_id)
                .order_by(SessionSet.position).all())
        assert [s.completed for s in sets] == [True, True]


def _heavy_uncounted(row):
    """A set ticked with no reps and one still open, both past every best:
    neither counts, so neither may raise one."""
    db.session.add(SessionSet(session_exercise_id=row.id, position=90, weight=300.0,
                              reps=0, completed=True))
    db.session.add(SessionSet(session_exercise_id=row.id, position=91, weight=300.0,
                              reps=40, completed=False))


def test_the_live_screen_knows_each_exercise_s_bests(lifter):
    """What its "Sicher?" measures a typed number against: the heaviest
    weight and the most reps in the finished workouts before, raised by this
    one's counted sets -- a set ticked with no reps, or one still open, is no
    best."""
    with flask_app.app_context():
        bench = lifter.exercise('bests bench')
        earlier = lifter.workout(started_ago=dt.timedelta(days=3), finished=True)
        lifter.row(earlier, bench, 1, done=((100.0, 5), (80.0, 12)))
        workout = lifter.workout(started_ago=30 * MINUTE)
        row = lifter.row(workout, bench, 1, done=((90.0, 15), (95.0, 6)))
        _heavy_uncounted(row)
        db.session.commit()
        workout_id, row_id = workout.id, row.id

    body = lifter.client().get(f'/gym/session/{workout_id}/detail.json',
                               headers=LIVE).get_json()

    rows = {se['id']: se for se in body['visible_exercises']}
    assert rows[row_id]['best'] == {'weight': 100.0, 'reps': 15}


def test_a_first_time_has_no_bar_to_ask_against(lifter):
    """Today's sets raise a bar, never set one: a 20 kg warm-up on a new
    exercise made the 50 kg after it a "Sicher?" (B7 review)."""
    with flask_app.app_context():
        fresh = lifter.exercise('bests fresh')
        workout = lifter.workout(started_ago=30 * MINUTE)
        row = lifter.row(workout, fresh, 1, done=((20.0, 10),), open_=2)
        db.session.commit()
        workout_id, row_id = workout.id, row.id

    body = lifter.client().get(f'/gym/session/{workout_id}/detail.json',
                               headers=LIVE).get_json()

    assert {se['id']: se['best'] for se in body['visible_exercises']} == {row_id: None}


def test_another_lifter_s_sets_are_no_best_of_yours(lifter):
    with flask_app.app_context():
        press = lifter.exercise('bests press')
        theirs = lifter.workout(started_ago=dt.timedelta(days=2), user_id=lifter.partner(),
                                finished=True)
        lifter.row(theirs, press, 1, done=((140.0, 20),))
        mine = lifter.workout(started_ago=30 * MINUTE)
        lifter.row(mine, press, 1, done=((50.0, 8),), open_=1)
        db.session.commit()
        workout_id = mine.id

    body = lifter.client().get(f'/gym/session/{workout_id}/detail.json',
                               headers=LIVE).get_json()

    assert body['visible_exercises'][0]['best'] is None


def test_the_debrief_knows_the_bests_too(lifter):
    """"Nachtragen" and a correction are typed and counted at once (Q5): the
    debrief judges them against the workouts before and its own sets -- an
    exercise with nothing logged included."""
    with flask_app.app_context():
        bench = lifter.exercise('debrief bests bench')
        rows_ = lifter.exercise('debrief bests row')
        earlier = lifter.workout(started_ago=dt.timedelta(days=3), finished=True)
        lifter.row(earlier, bench, 1, done=((100.0, 5), (60.0, 12), (70.0, 10)))
        lifter.row(earlier, rows_, 2, done=((70.0, 12),))
        workout = lifter.workout(started_ago=3 * 60 * MINUTE, finished=True)
        done_row = lifter.row(workout, bench, 1, done=((90.0, 9),))
        _heavy_uncounted(done_row)
        lifter.row(workout, rows_, 2, open_=2)
        # Finished, this workout is history too -- but not its own bar.
        lifter.row(workout, lifter.exercise('debrief bests new'), 3, done=((40.0, 10),))
        db.session.commit()
        workout_id = workout.id

    body = embedded_payload(
        lifter.client().get(f'/gym/session/{workout_id}').get_data(as_text=True))

    assert [entry['best'] for entry in body['exercises']] == [{'weight': 100.0, 'reps': 12}, None]
    assert [entry['best'] for entry in body['unlogged']] == [{'weight': 70.0, 'reps': 12}]


def test_the_live_screen_knows_which_rows_are_substitutes(lifter):
    """A substitute's remove brings its original back, a row the screen does
    not hold: it draws no remove for one, and waits for the answer (B7
    re-review)."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=40 * MINUTE)
        original = lifter.row(workout, lifter.exercise('swap original'), 1, open_=1)
        substitute = lifter.row(workout, lifter.exercise('swap substitute'), 1, open_=1,
                                replaces=original)
        other = lifter.row(workout, lifter.exercise('swap other'), 2, open_=1)
        db.session.commit()
        workout_id, substitute_id, other_id = workout.id, substitute.id, other.id

    body = lifter.client().get(f'/gym/session/{workout_id}/detail.json',
                               headers=LIVE).get_json()

    assert {se['id']: se['is_substitute'] for se in body['visible_exercises']} == {
        substitute_id: True, other_id: False}


def _removable(lifter, name):
    """A running workout whose one row has a set done. Returns the row id."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=40 * MINUTE)
        row = lifter.row(workout, lifter.exercise(name), 1, done=((60.0, 8),), open_=1)
        db.session.commit()
        return row.id


def test_a_remove_that_saw_fewer_sets_leaves_the_row(lifter):
    """A swap's undo sent again once the connection came back took the sets
    logged on the row since with it (B7 review): the screen says how many
    done sets it showed, and a row holding more stays."""
    row_id = _removable(lifter, 'remove stale')

    response = lifter.client().post(f'/gym/session-exercise/{row_id}/delete',
                                    data={'done': '0'}, headers=LIVE)

    assert response.status_code == 409
    with flask_app.app_context():
        assert SessionSet.query.filter_by(session_exercise_id=row_id).count() == 2


def test_a_remove_that_saw_every_set_goes_through(lifter):
    row_id = _removable(lifter, 'remove seen')

    response = lifter.client().post(f'/gym/session-exercise/{row_id}/delete',
                                    data={'done': '1'}, headers=LIVE)

    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id) is None


def test_a_remove_with_a_garbled_count_is_refused(lifter):
    row_id = _removable(lifter, 'remove garbled')

    response = lifter.client().post(f'/gym/session-exercise/{row_id}/delete',
                                    data={'done': 'x'}, headers=LIVE)

    assert response.status_code == 400
    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id) is not None


def test_a_remove_that_says_nothing_is_not_judged(lifter):
    """A page from before this rule sends no count; it removes as it did."""
    row_id = _removable(lifter, 'remove silent')

    lifter.client().post(f'/gym/session-exercise/{row_id}/delete', headers=LIVE)

    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id) is None

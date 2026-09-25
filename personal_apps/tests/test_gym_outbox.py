"""The offline outbox, server side (walkthrough B6, D6-A: G-072, G-138).

A phone that lost its connection keeps what the lifter logged and sends it
later, in order -- maybe hours later, maybe twice. So every live write says
how long ago it was made (X-Gym-Write-Age), an added set carries a key that
makes its second copy a no-op, the skip states the state it wants, and while
the phone still holds writes for its workout the three-hour rule waits for
them (the gym_outbox cookie).

Runs against the local development database with a throwaway lifter.
"""
import datetime as dt

from app import app as flask_app
from extensions import db
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import (
    STALE_SESSION_TIMEOUT, PendingPush, SessionExercise, SessionSet, WorkoutSession,
)

LIVE = {'Accept': 'application/json', 'X-Gym-Surface': 'live'}
MINUTE = dt.timedelta(minutes=1)
REST = 120


def _ms(moment):
    """Epoch milliseconds for a naive-UTC moment, as the phone sends them."""
    return str(int(moment.replace(tzinfo=dt.timezone.utc).timestamp() * 1000))


def _at(moment):
    """The live headers for a write made at `moment`: the phone says how long
    ago that was, whatever its own clock reads."""
    age = (dt.datetime.utcnow() - moment).total_seconds() * 1000
    return {**LIVE, 'X-Gym-Write-Age': str(int(age))}


def _running(lifter, name, started_ago=50 * MINUTE, done_ago=None, open_=3):
    """A running workout with one exercise: one set done `done_ago` before
    now when that is given, then `open_` open sets, and a rest of REST
    seconds. Returns (workout id, row id, the open sets' ids)."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=started_ago)
        done = [(60.0, 8)] if done_ago is not None else ()
        row = lifter.row(workout, lifter.exercise(name), 1, done=done,
                         done_ago=[done_ago] if done_ago is not None else None, open_=open_)
        row.rest_seconds = REST
        db.session.commit()
        return workout.id, row.id, [s.id for s in row.sets if not s.completed]


def _tick(client, set_id, headers):
    return client.post(f'/gym/set/{set_id}/toggle_complete',
                       data={'completed': '1'}, headers=headers)


def _pushes(workout_id):
    return PendingPush.query.filter_by(session_id=workout_id, sent=False).all()


def test_a_set_sent_late_keeps_the_time_it_was_lifted(lifter):
    """It was stamped when it arrived: a set lifted offline twenty minutes
    ago read as lifted now, its rest ran from now, and a push buzzed for a
    rest that had ended long before."""
    workout_id, _, open_sets = _running(lifter, 'late tick')
    lifted = lifter.now - 20 * MINUTE

    response = _tick(lifter.client(), open_sets[0], _at(lifted))

    assert response.status_code == 200
    with flask_app.app_context():
        set_ = db.session.get(SessionSet, open_sets[0])
        assert set_.completed is True
        assert set_.completed_at == lifted
        workout = db.session.get(WorkoutSession, workout_id)
        assert workout.rest_ends_at == lifted + dt.timedelta(seconds=REST)
        assert workout.resting_set_id == open_sets[0]
        assert _pushes(workout_id) == []


def test_a_late_set_whose_rest_still_runs_buzzes_at_its_end(lifter):
    workout_id, _, open_sets = _running(lifter, 'recent tick')
    lifted = lifter.now - MINUTE

    _tick(lifter.client(), open_sets[0], _at(lifted))

    with flask_app.app_context():
        [push] = _pushes(workout_id)
        assert push.fire_at == lifted + dt.timedelta(seconds=REST)


def test_the_write_time_is_held_to_the_workout_and_to_now(lifter):
    """A phone is not to be trusted past what is possible: a write from the
    future is now, one from before the workout began is its start, and an
    age that is not a number is not there."""
    workout_id, _, open_sets = _running(lifter, 'clock')
    client = lifter.client()

    _tick(client, open_sets[0], _at(lifter.now + dt.timedelta(hours=2)))
    _tick(client, open_sets[1], _at(lifter.now - dt.timedelta(days=1)))
    _tick(client, open_sets[2], {**LIVE, 'X-Gym-Write-Age': 'soon'})

    with flask_app.app_context():
        started_at = db.session.get(WorkoutSession, workout_id).started_at
        stamps = [db.session.get(SessionSet, set_id).completed_at for set_id in open_sets]
    later = dt.datetime.utcnow() + dt.timedelta(seconds=1)
    assert lifter.now <= stamps[0] <= later
    assert stamps[1] == started_at
    assert lifter.now <= stamps[2] <= later


def test_an_added_set_sent_twice_is_one_set(lifter):
    """The answer to the first copy was lost on the way back; the phone sent
    it again. It used to be a second set, and a second rest."""
    _, row_id, _ = _running(lifter, 'add twice', open_=0)
    client = lifter.client()

    for _ in range(2):
        response = client.post(f'/gym/session-exercise/{row_id}/sets/add',
                               data={'weight': '60', 'reps': '8', 'key': 'a1b2-c3'},
                               headers=LIVE)
        assert response.status_code == 200

    with flask_app.app_context():
        assert SessionSet.query.filter_by(session_exercise_id=row_id).count() == 1
    [row] = [se for se in response.get_json()['visible_exercises'] if se['id'] == row_id]
    assert [s['key'] for s in row['sets']] == ['a1b2-c3']


def test_two_copies_of_an_add_arriving_together_are_one_set(lifter, monkeypatch):
    """The first copy is still being written when the second arrives: each
    looks, neither finds the other's set, both insert. The unique index
    refuses the second, and that is the answer, not a 500."""
    from features.gym.routes import workout as workout_routes
    _, row_id, _ = _running(lifter, 'add race', open_=0)
    parse = workout_routes._to_client_key

    def while_the_other_copy_lands(value):
        key = parse(value)
        with db.engine.connect() as other:
            other.execute(SessionSet.__table__.insert().values(
                session_exercise_id=row_id, position=1, weight=60.0, reps=8, completed=True,
                completed_at=lifter.now, client_key=key))
            other.commit()
        return key

    monkeypatch.setattr(workout_routes, '_to_client_key', while_the_other_copy_lands)
    response = lifter.client().post(f'/gym/session-exercise/{row_id}/sets/add',
                                    data={'weight': '60', 'reps': '8', 'key': 'race-1'},
                                    headers=LIVE)

    assert response.status_code == 200
    [row] = [se for se in response.get_json()['visible_exercises'] if se['id'] == row_id]
    assert [s['key'] for s in row['sets']] == ['race-1']
    with flask_app.app_context():
        assert SessionSet.query.filter_by(session_exercise_id=row_id).count() == 1


def test_two_added_sets_with_their_own_keys_are_two_sets(lifter):
    _, row_id, _ = _running(lifter, 'add two', open_=0)
    client = lifter.client()

    for key in ('first-set', 'second-set'):
        client.post(f'/gym/session-exercise/{row_id}/sets/add',
                    data={'weight': '60', 'reps': '8', 'key': key}, headers=LIVE)
    # And a page from before the outbox, which sends no key at all.
    client.post(f'/gym/session-exercise/{row_id}/sets/add',
                data={'weight': '60', 'reps': '8'}, headers=LIVE)

    with flask_app.app_context():
        keys = [s.client_key for s in
                SessionSet.query.filter_by(session_exercise_id=row_id).order_by(SessionSet.position)]
    assert keys == ['first-set', 'second-set', None]


def test_a_key_that_is_not_one_is_refused(lifter):
    _, row_id, _ = _running(lifter, 'bad key', open_=0)
    client = lifter.client()

    for key in ('x' * 37, 'no spaces', "k'1"):
        response = client.post(f'/gym/session-exercise/{row_id}/sets/add',
                               data={'weight': '60', 'reps': '8', 'key': key}, headers=LIVE)
        assert response.status_code == 400

    with flask_app.app_context():
        assert SessionSet.query.filter_by(session_exercise_id=row_id).count() == 0


def test_an_added_set_sent_late_keeps_its_time(lifter):
    workout_id, row_id, _ = _running(lifter, 'add late', open_=0)
    lifted = lifter.now - 15 * MINUTE

    lifter.client().post(f'/gym/session-exercise/{row_id}/sets/add',
                         data={'weight': '60', 'reps': '8', 'key': 'late-add'},
                         headers=_at(lifted))

    with flask_app.app_context():
        [set_] = SessionSet.query.filter_by(session_exercise_id=row_id).all()
        assert set_.completed_at == lifted
        assert _pushes(workout_id) == []


def test_the_skip_states_the_state_it_wants(lifter):
    """A flip sent twice was undone by its own copy -- and un-skipping twice
    planned the missing sets twice."""
    _, row_id, _ = _running(lifter, 'skip twice', done_ago=10 * MINUTE, open_=2)
    client = lifter.client()

    for _ in range(2):
        client.post(f'/gym/session-exercise/{row_id}/skip',
                    data={'skipped': '1'}, headers=LIVE)
    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id).skipped is True

    client.post(f'/gym/session-exercise/{row_id}/skip', data={'skipped': '0'}, headers=LIVE)
    with flask_app.app_context():
        planned = len(db.session.get(SessionExercise, row_id).sets)
    client.post(f'/gym/session-exercise/{row_id}/skip', data={'skipped': '0'}, headers=LIVE)

    with flask_app.app_context():
        row = db.session.get(SessionExercise, row_id)
        assert row.skipped is False
        assert len(row.sets) == planned


def test_the_skip_without_a_state_still_flips(lifter):
    """A page from before the outbox sends no state."""
    _, row_id, _ = _running(lifter, 'old skip', open_=2)

    lifter.client().post(f'/gym/session-exercise/{row_id}/skip', headers=LIVE)

    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id).skipped is True


LAST = STALE_SESSION_TIMEOUT + 30 * MINUTE


def test_a_set_made_while_the_workout_ran_lands_hours_later(lifter):
    """The basement: the last set that reached the server was LAST ago, the
    next ones were logged offline, and the phone gets them out only now.
    Judged by the time they arrive the workout was over, so the first one
    ended it -- the screen reloaded into a debrief without them."""
    workout_id, _, open_sets = _running(lifter, 'basement', started_ago=LAST + 40 * MINUTE,
                                        done_ago=LAST)
    lifted = lifter.now - LAST + 20 * MINUTE
    client = lifter.client()

    response = _tick(client, open_sets[0], _at(lifted))

    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at is None
        assert db.session.get(SessionSet, open_sets[0]).completed_at == lifted

    # Everything is in: the next page ends it at its real last set.
    client.get('/gym')
    with flask_app.app_context():
        ended = db.session.get(WorkoutSession, workout_id)
        assert ended.finished_at == lifted
        assert ended.auto_finished is True


def test_a_skip_made_while_the_workout_ran_lands_hours_later(lifter):
    """The same for a change to the workout's shape."""
    workout_id, row_id, _ = _running(lifter, 'basement skip', started_ago=LAST + 40 * MINUTE,
                                     done_ago=LAST)

    response = lifter.client().post(f'/gym/session-exercise/{row_id}/skip',
                                    data={'skipped': '1'},
                                    headers=_at(lifter.now - LAST + 20 * MINUTE))

    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(SessionExercise, row_id).skipped is True
        assert db.session.get(WorkoutSession, workout_id).finished_at is None


def test_a_set_made_after_the_three_hours_still_ends_the_workout(lifter):
    """The write time moves the question to when the set was made, not past
    the rule: a set made three hours after the last one is still a set on a
    workout nobody came back to (B4)."""
    workout_id, _, open_sets = _running(lifter, 'too late', started_ago=LAST + 40 * MINUTE,
                                        done_ago=LAST)

    response = _tick(lifter.client(), open_sets[0], _at(lifter.now - MINUTE))

    assert response.status_code == 409
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at == lifter.now - LAST


def _hold(client, workout_id, oldest):
    client.set_cookie('gym_outbox', f'{workout_id}:{_ms(oldest)}', path='/gym')


def test_a_phone_still_holding_sets_keeps_its_workout_running(lifter):
    """Offline to the end of the workout, the app closed, opened again the
    next day: the page ended the workout at its last set that had reached the
    server -- or threw it away when none had -- before the phone could send
    the rest, and every one of them was refused."""
    workout_id, _, _ = _running(lifter, 'held', started_ago=LAST + 40 * MINUTE, done_ago=LAST)
    client = lifter.client()
    _hold(client, workout_id, lifter.now - LAST + 10 * MINUTE)

    client.get('/gym')
    client.get(f'/gym/session/{workout_id}')
    client.get(f'/gym/session/{workout_id}/detail.json')

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at is None

    client.delete_cookie('gym_outbox', path='/gym')
    client.get('/gym')
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at == lifter.now - LAST


def test_a_phone_holding_sets_keeps_an_empty_workout_too(lifter):
    """Nothing reached the server at all: the workout was discarded."""
    workout_id, _, _ = _running(lifter, 'held empty', started_ago=LAST)
    client = lifter.client()
    _hold(client, workout_id, lifter.now - LAST + 30 * MINUTE)

    client.get('/gym')

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id) is not None


def test_the_service_worker_script_settles_nothing(lifter):
    """The browser fetches /sw.js on its own around a page load, and the
    hold cookie (Path=/gym) never goes with it: that request ended the
    workout the phone was still holding sets for, and the queue's writes
    were then refused one by one (B6 review, P1)."""
    workout_id, _, _ = _running(lifter, 'sw held', started_ago=LAST + 40 * MINUTE, done_ago=LAST)
    client = lifter.client()
    _hold(client, workout_id, lifter.now - LAST + 10 * MINUTE)

    assert client.get('/sw.js').status_code == 200

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at is None


def test_a_hold_is_for_the_workout_it_names(lifter):
    workout_id, _, _ = _running(lifter, 'other hold', started_ago=LAST + 40 * MINUTE,
                                done_ago=LAST)
    client = lifter.client()
    _hold(client, workout_id + 1, lifter.now - LAST + 10 * MINUTE)

    client.get('/gym')

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at == lifter.now - LAST


def test_a_hold_only_reaches_back_to_the_oldest_write_it_holds(lifter):
    """The phone's oldest write was made after the three hours had passed:
    the workout was over before it, hold or not."""
    workout_id, _, _ = _running(lifter, 'late hold', started_ago=LAST + 40 * MINUTE,
                                done_ago=LAST)
    client = lifter.client()
    _hold(client, workout_id, lifter.now - MINUTE)

    client.get('/gym')

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at == lifter.now - LAST


def test_a_hold_older_than_a_week_holds_nothing(lifter):
    """The cookie's own Max-Age, held on the server too: the cookie is the
    phone's to set."""
    workout_id, _, _ = _running(lifter, 'week hold', started_ago=dt.timedelta(days=8),
                                done_ago=dt.timedelta(days=8) - 10 * MINUTE)
    client = lifter.client()
    _hold(client, workout_id, lifter.now - dt.timedelta(days=8) + 20 * MINUTE)

    client.get('/gym')

    with flask_app.app_context():
        assert (db.session.get(WorkoutSession, workout_id).finished_at
                == lifter.now - dt.timedelta(days=8) + 10 * MINUTE)


def test_a_hold_that_is_not_one_holds_nothing(lifter):
    workout_id, _, _ = _running(lifter, 'junk hold', started_ago=LAST + 40 * MINUTE,
                                done_ago=LAST)
    client = lifter.client()
    client.set_cookie('gym_outbox', f'{workout_id}:yesterday', path='/gym')

    client.get('/gym')

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).finished_at == lifter.now - LAST


def test_a_rest_skipped_offline_ends_when_it_was_skipped(lifter):
    workout_id, _, open_sets = _running(lifter, 'late skip')
    client = lifter.client()
    _tick(client, open_sets[0], _at(lifter.now - 30 * MINUTE / 60))
    skipped = lifter.now - 10 * MINUTE / 60

    response = client.post(f'/gym/session/{workout_id}/rest/skip', headers=_at(skipped))

    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id).rest_ends_at == skipped
        assert _pushes(workout_id) == []

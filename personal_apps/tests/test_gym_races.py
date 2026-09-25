"""Two requests at once, and requests the server used to answer as if done.

Walkthrough 2026-09-23:
- G-091: two starts at once made two running workouts.
- G-136: "Mitmachen" twice made two partner workouts; a double invite hit
  the (session, partner) unique key; a double "Routine aktualisieren" wrote
  every exercise twice; a double "Als Routine speichern" saved it twice; the
  first save of an exercise's settings collided with itself; a lock timeout
  while carrying a change to the partner answered 500 for a saved change.
- G-149: deleting a running workout answered deleted: true, and a replace
  that did nothing answered 200.
- G-085: a follower could invite, and saw the picker.

The races are made certain rather than likely: a stub slows the request down
between its check and its insert, so without a lock every request passes the
check. With the lock the later ones wait and then see the first one's work.

Runs against the real local development database. Every lifter here is a
throwaway account, deleted with everything it made.
"""
import datetime as dt
import secrets
import threading
import time
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app import app as flask_app
from conftest import _admin_id, embedded_payload, list_exercise

JSON = {'Accept': 'application/json'}
PAUSE = 0.4


_SLOWED = []


def _slowed(function):
    """`function`, PAUSE seconds later. The race is certain only while the
    request really passes through it: a refactor that stops calling it would
    leave the test racing on luck, so each one is checked after the test."""
    def slow(*args, **kwargs):
        slow.calls += 1
        time.sleep(PAUSE)
        return function(*args, **kwargs)
    slow.calls = 0
    slow.stub_of = function.__name__
    _SLOWED.append(slow)
    return slow


@pytest.fixture(autouse=True)
def _every_slowed_function_was_on_the_path():
    _SLOWED.clear()
    yield
    idle = [slow.stub_of for slow in _SLOWED if slow.calls == 0]
    _SLOWED.clear()
    assert not idle, f'slowed but never called, so the race was left to luck: {idle}'


def _race(user_id, method, url, data=None, count=2):
    """Send the same request `count` times at once, each from its own client
    logged in as user_id. Returns each response, or the exception it raised."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def run(index):
        with flask_app.test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session['user_id'] = user_id
            barrier.wait()
            try:
                results[index] = getattr(client, method)(url, data=data or {})
            except Exception as error:  # the failure under test, reported below
                results[index] = error

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def _statuses(results):
    return [result if isinstance(result, Exception) else result.status_code
            for result in results]


def _client_for(user_id):
    client = flask_app.test_client()
    with client.session_transaction() as flask_session:
        flask_session['user_id'] = user_id
    return client


@pytest.fixture()
def lifter():
    """A throwaway account: nothing running, nothing saved."""
    from werkzeug.security import generate_password_hash
    from extensions import db
    from features.gym.routes.helpers import _delete_session_and_links
    from models import (AppUser, ExerciseSettings, LifterSettings, SharedSession,
                        WorkoutSession, WorkoutTemplate)
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        user = AppUser(username=f'pytest race {uuid.uuid4().hex[:8]}',
                       password_hash=generate_password_hash(secrets.token_hex(16)),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id
    with flask_app.app_context():
        for session_ in WorkoutSession.query.filter_by(user_id=user_id).all():
            _delete_session_and_links(session_)
        SharedSession.query.filter(db.or_(SharedSession.follower_user_id == user_id,
                                          SharedSession.leader_user_id == user_id)).delete(
            synchronize_session=False)
        for template in WorkoutTemplate.query.filter_by(user_id=user_id).all():
            db.session.delete(template)
        ExerciseSettings.query.filter_by(user_id=user_id).delete()
        LifterSettings.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(AppUser, user_id))
        db.session.commit()


def _finished_workout(user_id, exercise_ids, template_id=None):
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        started = dt.datetime.utcnow() - dt.timedelta(hours=1)
        session_ = WorkoutSession(name='pytest race workout', user_id=user_id,
                                  template_id=template_id, started_at=started,
                                  finished_at=started + dt.timedelta(minutes=45))
        for position, exercise_id in enumerate(exercise_ids, start=1):
            se = SessionExercise(exercise_id=exercise_id, position=position)
            se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
            session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        return session_.id


def _exercise_ids(*keys):
    with flask_app.app_context():
        return [list_exercise(key).id for key in keys]


def _invite(leader_session_id, follower_id):
    from extensions import db
    from models import SharedSession
    with flask_app.app_context():
        shared = SharedSession(leader_session_id=leader_session_id,
                               leader_user_id=_admin_id(), follower_user_id=follower_id)
        db.session.add(shared)
        db.session.commit()
        return shared.id


def _drop_links(leader_session_id):
    """Before live_session's teardown deletes the leader's workout."""
    from extensions import db
    from features.gym.routes.helpers import _delete_session_and_links
    from models import SharedSession, WorkoutSession
    with flask_app.app_context():
        links = SharedSession.query.filter_by(leader_session_id=leader_session_id).all()
        followers = [link.follower_session_id for link in links if link.follower_session_id]
        SharedSession.query.filter_by(leader_session_id=leader_session_id).delete(
            synchronize_session=False)
        db.session.commit()
        for session_id in followers:
            session_ = db.session.get(WorkoutSession, session_id)
            if session_ is not None:
                _delete_session_and_links(session_)


# -- G-091: one running workout ------------------------------------------------

def test_three_starts_at_once_make_one_workout(lifter, monkeypatch):
    from models import WorkoutSession
    from features.gym.routes import workout
    monkeypatch.setattr(workout, '_to_name', _slowed(workout._to_name))

    results = _race(lifter, 'post', '/gym/start', count=3)

    assert _statuses(results) == [302, 302, 302]
    with flask_app.app_context():
        running = WorkoutSession.query.filter_by(user_id=lifter, finished_at=None).all()
        assert len(running) == 1, 'two starts at once made two running workouts'
    assert {result.headers['Location'] for result in results} == {f'/gym/session/{running[0].id}'}


# -- G-136: joining, inviting, routines, settings --------------------------------

def test_mitmachen_twice_at_once_joins_once(lifter, live_session, monkeypatch):
    from models import WorkoutSession
    from features.gym.routes import partners
    monkeypatch.setattr(partners, '_to_int', _slowed(partners._to_int))
    shared_id = _invite(live_session['session'], lifter)
    try:
        results = _race(lifter, 'post', f'/gym/shared/{shared_id}/accept')

        assert _statuses(results) == [302, 302]
        with flask_app.app_context():
            joined = WorkoutSession.query.filter_by(user_id=lifter).all()
            assert len(joined) == 1, '"Mitmachen" twice made two workouts'
        assert {result.headers['Location'] for result in results} == \
            {f'/gym/session/{joined[0].id}'}
    finally:
        _drop_links(live_session['session'])


def test_mitmachen_again_later_lands_in_the_workout_already_joined(lifter, live_session):
    shared_id = _invite(live_session['session'], lifter)
    try:
        client = _client_for(lifter)
        first = client.post(f'/gym/shared/{shared_id}/accept')
        again = client.post(f'/gym/shared/{shared_id}/accept')
        assert first.status_code == again.status_code == 302
        assert again.headers['Location'] == first.headers['Location']
    finally:
        _drop_links(live_session['session'])


def test_inviting_twice_at_once_invites_once(lifter, live_session, monkeypatch):
    from models import SharedSession
    from features.gym.routes import partners
    monkeypatch.setattr(partners, 'current_user_id', _slowed(partners.current_user_id))
    try:
        results = _race(_admin_id(), 'post', f"/gym/session/{live_session['session']}/invite",
                        data={'partner_id': str(lifter)})

        assert _statuses(results) == [302, 302]
        with flask_app.app_context():
            assert SharedSession.query.filter_by(
                leader_session_id=live_session['session'], follower_user_id=lifter).count() == 1
    finally:
        _drop_links(live_session['session'])


def test_updating_a_routine_twice_at_once_writes_each_exercise_once(lifter, monkeypatch):
    from extensions import db
    from models import TemplateExercise, WorkoutTemplate
    from features.gym.routes import session_admin
    monkeypatch.setattr(session_admin, '_template_exercises_from_session',
                        _slowed(session_admin._template_exercises_from_session))
    fly, bench, row = _exercise_ids('machine_fly', 'barbell_bench_press', 'cable_row')
    with flask_app.app_context():
        template = WorkoutTemplate(name='pytest race routine', user_id=lifter)
        template.exercises.extend([TemplateExercise(exercise_id=fly, position=1),
                                   TemplateExercise(exercise_id=bench, position=2)])
        db.session.add(template)
        db.session.commit()
        template_id = template.id
    session_id = _finished_workout(lifter, [bench, fly, row], template_id=template_id)

    results = _race(lifter, 'post', f'/gym/session/{session_id}/update_template')

    assert _statuses(results) == [302, 302]
    with flask_app.app_context():
        written = [te.exercise_id for te in db.session.get(WorkoutTemplate, template_id).exercises]
        assert written == [bench, fly, row], 'every exercise written twice'


def test_saving_a_routine_twice_at_once_saves_it_once(lifter, monkeypatch):
    from models import WorkoutTemplate
    from features.gym.routes import session_admin
    monkeypatch.setattr(session_admin, '_template_exercises_from_session',
                        _slowed(session_admin._template_exercises_from_session))
    session_id = _finished_workout(lifter, _exercise_ids('machine_fly', 'cable_row'))

    results = _race(lifter, 'post', f'/gym/session/{session_id}/save_as_template',
                    data={'template_name': 'pytest race saved'})

    assert _statuses(results) == [302, 302]
    with flask_app.app_context():
        saved = WorkoutTemplate.query.filter_by(user_id=lifter, name='pytest race saved').all()
        assert len(saved) == 1, 'the routine was saved twice'


def test_saving_the_same_routine_again_makes_no_copy(lifter):
    from models import WorkoutTemplate
    session_id = _finished_workout(lifter, _exercise_ids('machine_fly', 'cable_row'))
    client = _client_for(lifter)
    for _ in range(2):
        client.post(f'/gym/session/{session_id}/save_as_template',
                    data={'template_name': 'pytest saved again'})
    with flask_app.app_context():
        assert WorkoutTemplate.query.filter_by(
            user_id=lifter, name='pytest saved again').count() == 1


def test_a_different_routine_under_the_same_name_is_still_saved(lifter):
    """Only the same name with the same exercises is the same routine."""
    from models import WorkoutTemplate
    client = _client_for(lifter)
    for keys in (('machine_fly',), ('machine_fly', 'cable_row')):
        session_id = _finished_workout(lifter, _exercise_ids(*keys))
        client.post(f'/gym/session/{session_id}/save_as_template',
                    data={'template_name': 'pytest same name'})
    with flask_app.app_context():
        assert WorkoutTemplate.query.filter_by(
            user_id=lifter, name='pytest same name').count() == 2


def test_the_first_settings_save_twice_at_once_does_not_collide(lifter, monkeypatch):
    from models import ExerciseSettings
    from features.gym import exercises
    monkeypatch.setattr(exercises, '_stored', _slowed(exercises._stored))
    (fly,) = _exercise_ids('machine_fly')

    results = _race(lifter, 'post', f'/gym/exercises/{fly}/update',
                    data={'weight_increment': '2.5'})

    assert _statuses(results) == [302, 302]
    with flask_app.app_context():
        rows = ExerciseSettings.query.filter_by(user_id=lifter, exercise_id=fly).all()
        assert len(rows) == 1 and rows[0].weight_increment == 2.5


def test_a_partners_lock_timeout_does_not_fail_the_leaders_saved_change(
        client, lifter, live_session, monkeypatch):
    from models import SessionExercise
    from features.gym import sharing
    shared_id = _invite(live_session['session'], lifter)
    try:
        assert _client_for(lifter).post(f'/gym/shared/{shared_id}/accept').status_code == 302

        def timed_out(shared):
            raise OperationalError('SELECT ... FOR UPDATE', {},
                                   Exception('Lock wait timeout exceeded'))

        monkeypatch.setattr(sharing, 'reconcile_follower', timed_out)
        (bench,) = _exercise_ids('barbell_bench_press')
        response = client.post(f"/gym/session/{live_session['session']}/exercises/add",
                               data={'exercise_id': str(bench)}, headers=JSON)
        assert response.status_code == 200
        with flask_app.app_context():
            assert SessionExercise.query.filter_by(
                session_id=live_session['session'], exercise_id=bench).count() == 1
    finally:
        _drop_links(live_session['session'])


# -- G-055: the rest band's "+15", tapped twice ------------------------------------

def test_two_quick_plus_fifteens_add_thirty_seconds(live_session, monkeypatch):
    """Two taps are two requests. Each read the end both of them saw, and the
    second wrote the same "+15" over the first: the lifter asked for 30
    seconds and got 15."""
    from extensions import db
    from models import PendingPush, SessionSet, WorkoutSession
    from features.gym.routes import workout
    monkeypatch.setattr(workout, '_cancel_pending_push', _slowed(workout._cancel_pending_push))

    started = dt.datetime.utcnow().replace(microsecond=0)
    with flask_app.app_context():
        db.session.get(SessionSet, live_session['done_set']).completed_at = started
        row = db.session.get(WorkoutSession, live_session['session'])
        row.rest_ends_at = started + dt.timedelta(seconds=90)
        row.resting_set_id = live_session['done_set']
        db.session.commit()

    results = _race(_admin_id(), 'post',
                    f"/gym/session/{live_session['session']}/rest/shift", {'seconds': '15'})

    assert _statuses(results) == [302, 302]
    with flask_app.app_context():
        row = db.session.get(WorkoutSession, live_session['session'])
        assert row.rest_ends_at == started + dt.timedelta(seconds=120)
        pushes = PendingPush.query.filter_by(session_id=row.id, sent=False).all()
        assert [p.fire_at for p in pushes] == [row.rest_ends_at]


# -- G-149: no answer as if done ------------------------------------------------

def test_deleting_a_running_workout_is_refused_with_a_reason(client, live_session):
    from extensions import db
    from models import WorkoutSession
    response = client.post(f"/gym/session/{live_session['session']}/delete", headers=JSON)
    assert response.status_code == 400
    assert 'läuft noch' in response.get_json()['error']
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, live_session['session']) is not None


def test_a_replace_without_an_exercise_is_refused(client, live_session):
    response = client.post(f"/gym/session-exercise/{live_session['se']}/replace",
                           data={}, headers=JSON)
    assert response.status_code == 400


def test_a_second_replace_is_done_when_it_names_the_same_exercise_and_refused_otherwise(
        client, live_session):
    from models import SessionExercise
    bench, row = _exercise_ids('barbell_bench_press', 'cable_row')
    url = f"/gym/session-exercise/{live_session['se']}/replace"
    assert client.post(url, data={'exercise_id': str(bench)}, headers=JSON).status_code == 200
    assert client.post(url, data={'exercise_id': str(bench)}, headers=JSON).status_code == 200

    refused = client.post(url, data={'exercise_id': str(row)}, headers=JSON)
    assert refused.status_code == 400
    assert 'schon durch' in refused.get_json()['error']
    with flask_app.app_context():
        assert [se.exercise_id for se in SessionExercise.query.filter_by(
            replaces_id=live_session['se'])] == [bench]


# -- G-085: the leader invites ------------------------------------------------

def test_a_follower_cannot_invite_and_sees_no_picker(lifter, live_session):
    from models import SharedSession
    shared_id = _invite(live_session['session'], lifter)
    try:
        follower = _client_for(lifter)
        joined = follower.post(f'/gym/shared/{shared_id}/accept')
        follower_session = int(joined.headers['Location'].rsplit('/', 1)[1])

        page = follower.get(f'/gym/session/{follower_session}')
        assert embedded_payload(page.get_data(as_text=True))['partners'] == []

        response = follower.post(f'/gym/session/{follower_session}/invite',
                                 data={'partner_id': str(_admin_id())})
        assert response.status_code == 302
        with follower.session_transaction() as flask_session:
            assert ('error', 'Einladen kann nur, wer das gemeinsame Workout leitet.') \
                in flask_session['_flashes']
        with flask_app.app_context():
            assert SharedSession.query.filter_by(
                leader_session_id=follower_session).count() == 0
    finally:
        _drop_links(live_session['session'])

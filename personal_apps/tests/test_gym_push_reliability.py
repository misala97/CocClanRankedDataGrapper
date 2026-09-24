"""Push delivery that cannot hang or break what triggered it, and cannot
reach a real phone from a development machine.

Walkthrough 2026-09-23:
- G-133: webpush had no timeout and only WebPushException was caught. An
  unreachable push service escaped as a raw network error -- a 500 for an
  invite that was already saved, a notifier pass that ended before marking
  anything (so the same row failed again every ten seconds and every push
  behind it waited), and a weekly digest that stopped at the first user.
- G-134: the service worker's renewal after pushsubscriptionchange carried
  no CSRF token and was refused every time, and logging out left the device
  subscribed, so a shared phone kept the previous user's pushes.
- G-096: the local database is a copy of production's, subscriptions
  included, so a local invite buzzed a real phone. PERSONAL_PUSH_SENDING=off
  now keeps a process away from push services; these tests switch sending on
  around a stubbed webpush.

Runs against the real local development database. Every row created here is
deleted in a finally or a fixture teardown.
"""
import datetime as dt
from types import SimpleNamespace

import pytest
import requests
from pywebpush import WebPushException

from app import app as flask_app
from conftest import _admin_id

APPLE = 'https://web.push.apple.com/pytest-reliability-'
JSON = {'Accept': 'application/json'}
TOKEN = 'pytest-csrf-token'
REST = {'title': 'Rest complete', 'body': 'Time for your next set.'}


@pytest.fixture()
def scratch_subs():
    """Deletes every subscription this module created, whatever the test did."""
    from extensions import db
    from models import PushSubscription
    yield
    with flask_app.app_context():
        PushSubscription.query.filter(
            PushSubscription.endpoint.like(f'{APPLE}%')).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture()
def sending_on(monkeypatch):
    """Sending switched on, webpush stubbed. Yields the list of calls; set
    `failures[endpoint]` to the exception that endpoint's send raises."""
    from features.gym import push
    calls = []
    failures = {}

    def fake_webpush(subscription_info, **kwargs):
        endpoint = subscription_info['endpoint']
        calls.append({'endpoint': endpoint, **kwargs})
        if endpoint in failures:
            raise failures[endpoint]

    monkeypatch.setitem(flask_app.config, 'PUSH_SENDING', True)
    monkeypatch.setattr(push, 'webpush', fake_webpush)
    yield SimpleNamespace(calls=calls, failures=failures)


def _add_sub(suffix, user_id):
    from extensions import db
    from models import PushSubscription
    with flask_app.app_context():
        db.session.add(PushSubscription(
            endpoint=f'{APPLE}{suffix}', p256dh_key='pytest-p256dh', auth_key='pytest-auth',
            user_id=user_id, last_seen_at=dt.datetime.utcnow()))
        db.session.commit()


def _row(suffix):
    from models import PushSubscription
    with flask_app.app_context():
        return PushSubscription.query.filter_by(endpoint=f'{APPLE}{suffix}').first()


def _other_user_id():
    from models import AppUser
    with flask_app.app_context():
        other = (AppUser.query.filter(AppUser.id != _admin_id())
                 .order_by(AppUser.id).first())
        if other is None:
            pytest.skip('needs a second account')
        return other.id


def _response(status):
    return SimpleNamespace(status_code=status, text='pytest')


# -- G-133: one device's failure is that device's alone -----------------------

@pytest.mark.parametrize('failure', [
    requests.ConnectionError('unreachable'),
    requests.Timeout('stalled'),
    ValueError('the stored keys do not decode'),
    WebPushException('push service error', response=_response(500)),
], ids=['connection', 'timeout', 'bad keys', 'service error'])
def test_a_device_that_fails_does_not_stop_the_others(sending_on, scratch_subs, failure):
    from features.gym import push
    admin = _admin_id()
    _add_sub('broken', admin)
    _add_sub('fine', admin)
    sending_on.failures[f'{APPLE}broken'] = failure

    with flask_app.app_context():
        push.send_push_to_user(admin, REST)

    sent = [call['endpoint'] for call in sending_on.calls]
    assert f'{APPLE}fine' in sent, 'the working device was skipped'
    assert _row('broken') is not None, 'a transient failure is not a dead subscription'


def test_every_send_is_bounded_by_a_timeout(sending_on, scratch_subs):
    from features.gym import push
    _add_sub('timed', _admin_id())
    with flask_app.app_context():
        push.send_push_to_user(_admin_id(), REST)
    mine = [call for call in sending_on.calls if call['endpoint'] == f'{APPLE}timed']
    assert mine and mine[0]['timeout'] == push.PUSH_TIMEOUT_SECONDS


@pytest.mark.parametrize('status', [404, 410])
def test_an_expired_device_is_still_pruned(sending_on, scratch_subs, status):
    from features.gym import push
    _add_sub('gone', _admin_id())
    sending_on.failures[f'{APPLE}gone'] = WebPushException('gone', response=_response(status))
    with flask_app.app_context():
        push.send_push_to_user(_admin_id(), REST)
    assert _row('gone') is None


def test_an_invite_is_answered_even_when_the_partners_push_service_is_down(
        client, live_session, sending_on, scratch_subs):
    from extensions import db
    from models import SharedSession
    partner = _other_user_id()
    _add_sub('partner', partner)
    sending_on.failures[f'{APPLE}partner'] = requests.ConnectionError('unreachable')
    try:
        response = client.post(f"/gym/session/{live_session['session']}/invite",
                                data={'partner_id': partner})
        assert response.status_code == 302
        with flask_app.app_context():
            assert SharedSession.query.filter_by(
                leader_session_id=live_session['session'],
                follower_user_id=partner).count() == 1
        assert f'{APPLE}partner' in [call['endpoint'] for call in sending_on.calls]
    finally:
        with flask_app.app_context():
            SharedSession.query.filter_by(
                leader_session_id=live_session['session']).delete()
            db.session.commit()


def test_a_push_sent_later_never_raises(monkeypatch):
    """Off the request's thread: the dispatch returns at once, and whatever
    the send raises stays inside the thread."""
    from features.gym import push
    started = []

    class FakeThread:
        def __init__(self, target, name, daemon):
            self.target, self.daemon = target, daemon

        def start(self):
            started.append(self)

    def exploding_send(user_id, payload):
        raise RuntimeError('push service exploded')

    monkeypatch.setitem(flask_app.config, 'TESTING', False)
    monkeypatch.setattr(push.threading, 'Thread', FakeThread)
    monkeypatch.setattr(push, 'send_push_to_user', exploding_send)
    with flask_app.app_context():
        push.send_push_later(1, REST)
    assert len(started) == 1 and started[0].daemon is True
    started[0].target()  # what the thread runs: must swallow and log


# -- G-133: the notifier ---------------------------------------------------

def test_one_failing_rest_push_does_not_hold_the_others(monkeypatch):
    from extensions import db
    from models import PendingPush, WorkoutSession
    import run_gym_notifier

    calls = []

    def flaky_send(user_id, payload):
        calls.append(user_id)
        if len(calls) == 1:
            raise RuntimeError('push service exploded')

    monkeypatch.setattr(run_gym_notifier, 'send_push_to_user', flaky_send)
    session_ids, push_ids = [], []
    # Two lifters, one running workout each -- the shape production has.
    owners = (_admin_id(), _other_user_id())
    try:
        with flask_app.app_context():
            for name, owner in zip(('ZZ rest push a', 'ZZ rest push b'), owners):
                session_ = WorkoutSession(name=name, user_id=owner,
                                          started_at=dt.datetime.utcnow())
                db.session.add(session_)
                db.session.flush()
                pending = PendingPush(session_id=session_.id,
                                      fire_at=dt.datetime.utcnow() - dt.timedelta(seconds=5))
                db.session.add(pending)
                db.session.flush()
                session_ids.append(session_.id)
                push_ids.append(pending.id)
            db.session.commit()

        run_gym_notifier.check_pending_pushes()

        with flask_app.app_context():
            assert all(db.session.get(PendingPush, push_id).sent for push_id in push_ids), \
                'a failed push kept its row due, to fail again every ten seconds'
        assert len(calls) >= 2, 'the push after the failing one was never sent'
    finally:
        with flask_app.app_context():
            PendingPush.query.filter(PendingPush.id.in_(push_ids)).delete(
                synchronize_session=False)
            WorkoutSession.query.filter(WorkoutSession.id.in_(session_ids)).delete(
                synchronize_session=False)
            db.session.commit()


def test_one_users_failing_digest_does_not_cost_the_others_theirs(monkeypatch):
    from extensions import db
    from models import AppUser
    import run_gym_notifier

    with flask_app.app_context():
        user_ids = [user_id for (user_id,) in db.session.query(AppUser.id)]
    if len(user_ids) < 2:
        pytest.skip('needs a second account')
    failing = user_ids[0]

    def digest(user_id, now):
        if user_id == failing:
            raise RuntimeError('digest exploded')
        return {'title': 'Deine Trainingswoche', 'body': 'pytest'}

    sent = []
    monkeypatch.setattr(run_gym_notifier, '_weekly_digest_for', digest)
    monkeypatch.setattr(run_gym_notifier, 'send_push_to_user',
                        lambda user_id, payload: sent.append(user_id))
    run_gym_notifier.send_weekly_digests()
    assert sorted(sent) == sorted(user_ids[1:])


# -- G-096: a development machine sends nothing -----------------------------

def test_sending_off_reaches_no_push_service(monkeypatch, scratch_subs):
    from features.gym import push
    calls = []
    monkeypatch.setitem(flask_app.config, 'PUSH_SENDING', False)
    monkeypatch.setattr(push, 'webpush', lambda **kwargs: calls.append(kwargs))
    _add_sub('dev', _admin_id())
    with flask_app.app_context():
        assert push.send_push_to_user(_admin_id(), REST) == 0
    assert calls == []


def test_the_switch_reads_the_environment():
    """PERSONAL_PUSH_SENDING=off is the only value that turns it off, so a
    production box that never heard of the variable keeps sending."""
    import ast
    import pathlib
    source = (pathlib.Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
    line = next(l for l in source.splitlines() if "app.config['PUSH_SENDING']" in l)
    expression = ast.parse(line.split('=', 1)[1].strip(), mode='eval')
    for value, expected in ((None, True), ('on', True), ('off', False), ('OFF', False)):
        environ = {} if value is None else {'PERSONAL_PUSH_SENDING': value}
        fake_os = SimpleNamespace(getenv=lambda key, default=None: environ.get(key, default))
        assert eval(compile(expression, 'app.py', 'eval'), {'os': fake_os}) is expected, value


# -- G-134: the service worker's renewal, and logging out -------------------

@pytest.fixture()
def strict_client(monkeypatch):
    """The CSRF gate closed, as in production."""
    monkeypatch.setitem(flask_app.config, 'TESTING', True)
    monkeypatch.setitem(flask_app.config, 'CSRF_STRICT', True)
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = _admin_id()
            flask_session['csrf_token'] = TOKEN
        yield test_client


def _subscribe(client, suffix, headers=None, **extra):
    return client.post('/gym/push/subscribe', headers=headers or {}, json={
        'endpoint': f'{APPLE}{suffix}',
        'keys': {'p256dh': 'pytest-p256dh', 'auth': 'pytest-auth'},
        **extra,
    })


def test_the_service_worker_can_renew_a_rotated_subscription(strict_client, scratch_subs):
    """What sw.js does on pushsubscriptionchange: ask for the token, then post
    the new subscription naming the one it replaces."""
    assert _subscribe(strict_client, 'old', headers={'X-CSRF-Token': TOKEN}).status_code == 200

    answer = strict_client.get('/gym/push/token', headers=JSON)
    assert answer.status_code == 200
    assert answer.headers['Cache-Control'] == 'no-store'
    token = answer.get_json()['token']

    renewal = _subscribe(strict_client, 'new', headers={'X-CSRF-Token': token},
                         replaces=f'{APPLE}old')
    assert renewal.status_code == 200
    assert _row('old') is None, 'the rotated-away endpoint kept receiving'
    assert _row('new') is not None


def test_a_renewal_without_the_token_is_still_refused(strict_client, scratch_subs):
    _add_sub('old', _admin_id())
    assert _subscribe(strict_client, 'new', replaces=f'{APPLE}old').status_code == 403
    assert _row('new') is None


def test_the_token_is_for_a_logged_in_session_only(anon_client):
    assert anon_client.get('/gym/push/token', headers=JSON).status_code == 401


def test_logging_out_takes_this_devices_subscription_along(client, scratch_subs):
    """A shared phone kept the previous user's rest timers, invites and
    digests. The user's other devices keep theirs."""
    _add_sub('other-device', _admin_id())
    assert _subscribe(client, 'this-device').status_code == 200
    assert client.get('/logout').status_code == 302
    assert _row('this-device') is None
    assert _row('other-device') is not None


def test_logging_out_leaves_a_device_someone_else_took_over(client, scratch_subs):
    """The row is deleted only while it is still the logged-out user's."""
    from extensions import db
    assert _subscribe(client, 'handed-on').status_code == 200
    with flask_app.app_context():
        from models import PushSubscription
        row = PushSubscription.query.filter_by(endpoint=f'{APPLE}handed-on').one()
        row.user_id = _other_user_id()
        db.session.commit()
    client.get('/logout')
    assert _row('handed-on') is not None


def test_logging_out_without_a_subscription_is_an_ordinary_logout(client):
    assert client.get('/logout').status_code == 302
    with client.session_transaction() as flask_session:
        assert 'user_id' not in flask_session


# -- G-134 (review): bodies of the wrong shape are a 400, not a 500 ----------

@pytest.mark.parametrize('body', [
    ['https://web.push.apple.com/x'],
    'https://web.push.apple.com/x',
    {'endpoint': 42, 'keys': {'p256dh': 'k', 'auth': 'a'}},
    {'endpoint': f'{APPLE}x', 'keys': ['k', 'a']},
    {'endpoint': f'{APPLE}x', 'keys': {'p256dh': 1, 'auth': 'a'}},
], ids=['list', 'string', 'number endpoint', 'list keys', 'number key'])
def test_a_subscription_of_the_wrong_shape_is_refused(client, scratch_subs, body):
    assert client.post('/gym/push/subscribe', json=body).status_code == 400


def test_a_replaces_of_the_wrong_shape_is_ignored(client, scratch_subs):
    assert _subscribe(client, 'shaped', replaces=[f'{APPLE}x', f'{APPLE}y']).status_code == 200
    assert _row('shaped') is not None


@pytest.mark.parametrize('body', [['x'], {'endpoint': ['x', 'y']}], ids=['list', 'list endpoint'])
def test_an_unsubscribe_of_the_wrong_shape_is_harmless(client, body):
    assert client.post('/gym/push/unsubscribe', json=body).status_code == 200

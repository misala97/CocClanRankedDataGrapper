"""Push subscriptions that stop being used must stop being pushed to.

Every notification this app sends fans out to every row a user owns
(push.send_push_to_user), so a row the browser has silently replaced is a
second buzz on the same phone forever. Found in production: four rows for one
lifter, two of them per device, dating back to a subscribe two browsers apart.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id

APPLE = 'https://web.push.apple.com/pytest-'


@pytest.fixture()
def scratch_subs():
    """Deletes anything this module created, whatever the test did."""
    from extensions import db
    from models import PushSubscription
    made = []
    yield made
    with flask_app.app_context():
        PushSubscription.query.filter(
            PushSubscription.endpoint.like(f'{APPLE}%')).delete(synchronize_session=False)
        db.session.commit()


def _subscribe(client, suffix, **extra):
    return client.post('/gym/push/subscribe', json={
        'endpoint': f'{APPLE}{suffix}',
        'keys': {'p256dh': 'pytest-p256dh', 'auth': 'pytest-auth'},
        **extra,
    })


def _row(endpoint_suffix):
    from models import PushSubscription
    return PushSubscription.query.filter_by(endpoint=f'{APPLE}{endpoint_suffix}').first()


def test_subscribing_stamps_when_the_device_was_last_seen(client, scratch_subs):
    assert _subscribe(client, 'fresh').status_code == 200
    with flask_app.app_context():
        row = _row('fresh')
        assert row is not None
        assert row.last_seen_at is not None
        assert (dt.datetime.utcnow() - row.last_seen_at).total_seconds() < 60


def test_resubscribing_the_same_endpoint_refreshes_the_stamp(client, scratch_subs):
    """The heartbeat: both pages post the subscription they already hold on
    load, which is how a device in use says it still exists."""
    from extensions import db
    assert _subscribe(client, 'beat').status_code == 200
    with flask_app.app_context():
        row = _row('beat')
        row.last_seen_at = dt.datetime.utcnow() - dt.timedelta(days=40)
        db.session.commit()
        stale = row.last_seen_at

    assert _subscribe(client, 'beat').status_code == 200
    with flask_app.app_context():
        assert _row('beat').last_seen_at > stale


def test_a_rotated_subscription_takes_the_place_of_the_one_it_replaces(client, scratch_subs):
    """What pushsubscriptionchange reports: the browser swapped the endpoint,
    so the old row is not a second device and must not survive as one."""
    assert _subscribe(client, 'old').status_code == 200
    assert _subscribe(client, 'new', replaces=f'{APPLE}old').status_code == 200
    with flask_app.app_context():
        assert _row('old') is None
        assert _row('new') is not None


def test_replacing_cannot_reach_another_users_subscription(client, scratch_subs):
    """`replaces` is an endpoint supplied by the client, so it is exactly the
    shape of thing that must not delete rows the caller does not own."""
    from extensions import db
    from models import AppUser, PushSubscription
    with flask_app.app_context():
        other = (AppUser.query.filter(AppUser.id != _admin_id())
                 .order_by(AppUser.id).first())
        if other is None:
            pytest.skip('needs a second account')
        db.session.add(PushSubscription(
            endpoint=f'{APPLE}theirs', p256dh_key='x', auth_key='y',
            user_id=other.id, last_seen_at=dt.datetime.utcnow()))
        db.session.commit()

    assert _subscribe(client, 'mine', replaces=f'{APPLE}theirs').status_code == 200
    with flask_app.app_context():
        assert _row('theirs') is not None, "deleted another account's subscription"


def test_pruning_drops_a_device_that_stopped_confirming_itself(client, scratch_subs):
    from extensions import db
    from features.gym import push
    assert _subscribe(client, 'ghost').status_code == 200
    with flask_app.app_context():
        row = _row('ghost')
        row.last_seen_at = (dt.datetime.utcnow()
                            - dt.timedelta(days=push.STALE_SUBSCRIPTION_DAYS + 1))
        db.session.commit()

        # Not an exact count: this database holds other people's rows, and
        # whether any of them are also stale is not this test's business.
        assert push.prune_stale_subscriptions(dt.datetime.utcnow()) >= 1
        assert _row('ghost') is None


def test_pruning_keeps_a_device_still_in_use(client, scratch_subs):
    from extensions import db
    from features.gym import push
    assert _subscribe(client, 'daily').status_code == 200
    with flask_app.app_context():
        row = _row('daily')
        row.last_seen_at = (dt.datetime.utcnow()
                            - dt.timedelta(days=push.STALE_SUBSCRIPTION_DAYS - 1))
        db.session.commit()

        push.prune_stale_subscriptions(dt.datetime.utcnow())
        assert _row('daily') is not None

import datetime as dt
import json
import logging
import re
import threading
from urllib.parse import urlparse

import requests
from flask import current_app
from pywebpush import webpush, WebPushException

from extensions import db
from models import PushSubscription

log = logging.getLogger(__name__)

# Real browser push services only. The endpoint a client submits at
# subscribe-time ends up handed verbatim to webpush(), which makes an
# outbound HTTP(S) request to it from the server -- so anything not on
# this allowlist must be rejected before it ever reaches the database
# (see gym_push_subscribe in routes.py), closing off the SSRF vector.
_ALLOWED_PUSH_HOSTS = {
    'fcm.googleapis.com',  # Chrome / Edge / most Chromium browsers
    'updates.push.services.mozilla.com',  # Firefox
    'web.push.apple.com',  # Safari on iOS/iPadOS/macOS (Apple Push Service)
}
_WNS_HOST_RE = re.compile(r'^wns2-[a-z0-9-]+\.notify\.windows\.com$')  # Windows Notification Service


def is_valid_push_endpoint(url):
    """True if url is a real browser push-service subscription endpoint.

    Requires https and a hostname matching a known push service, using
    urlparse so it can't be fooled by userinfo/lookalike-subdomain tricks
    like 'https://fcm.googleapis.com.evil.com/' or 'https://evil.com/@fcm.googleapis.com/'.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != 'https':
        return False
    host = parsed.hostname
    if not host:
        return False
    return host in _ALLOWED_PUSH_HOSTS or bool(_WNS_HOST_RE.match(host))


# How long a subscription survives without the device confirming it. Both gym
# pages post whatever subscription the browser already holds on every load, so
# a device in use refreshes this constantly and a device that has genuinely
# stopped being used simply re-registers itself the next time it is opened --
# the row is rebuilt by the same POST that would have refreshed it. What does
# NOT come back is an endpoint no browser holds any more, which is exactly the
# row that was buzzing a phone a second time.
#
# Thirty days rather than a week: the only things a dormant device misses are
# rest timers (which require using the app anyway) and the weekly digest.
STALE_SUBSCRIPTION_DAYS = 30


def prune_stale_subscriptions(now):
    """Drop subscriptions no device has confirmed inside the window.

    Returns the number deleted. Called daily from the notifier daemon rather
    than from the send path: a send is the wrong moment to be reasoning about
    which rows deserve to exist, and the daemon is already the one process
    that runs on a schedule regardless of traffic.
    """
    cutoff = now - dt.timedelta(days=STALE_SUBSCRIPTION_DAYS)
    deleted = (PushSubscription.query
               .filter(PushSubscription.last_seen_at < cutoff)
               .delete(synchronize_session=False))
    db.session.commit()
    return deleted


# Seconds a push service gets to answer. pywebpush's default is no timeout at
# all: a stalled endpoint held the invite request -- or the notifier's single
# worker, and with it every rest push -- for as long as the socket stayed
# open (G-133).
PUSH_TIMEOUT_SECONDS = 10


def sending_enabled():
    """Whether this process may reach a real push service.

    Off where PERSONAL_PUSH_SENDING=off. A development machine sets that: its
    database is a copy of production's, subscriptions included, so a local
    invite or a locally started notifier would buzz real phones with test
    traffic (G-096). Production leaves it unset. Tests inherit the machine's
    setting, and the ones that check sending switch it on around a stubbed
    webpush -- a test that forgets the stub then sends nothing.
    """
    return bool(current_app.config.get('PUSH_SENDING', True))


def send_push_to_user(user_id: int, payload: dict):
    """payload e.g. {'title': 'Rest complete', 'body': 'Time for your next set.'}

    Scoped to one user: this used to fan out to every subscription row, which
    with more than one lifter means one person's rest timer buzzing another
    person's phone.

    Never raises for a failed delivery. Each device gets its own try and a
    timeout: an unreachable endpoint used to escape as a raw network error --
    a 500 for an invite that had already been saved, and a notifier batch
    rolled back and sent again every ten seconds (G-133). Returns how many
    devices the push reached.
    """
    if not sending_enabled():
        log.info('push sending is off here; not sending %r to user %s',
                 payload.get('title'), user_id)
        return 0
    reached = 0
    for sub in PushSubscription.query.filter_by(user_id=user_id).all():
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh_key, 'auth': sub.auth_key},
                },
                data=json.dumps(payload),
                vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                vapid_claims={'sub': current_app.config['VAPID_CLAIMS_EMAIL']},
                timeout=PUSH_TIMEOUT_SECONDS,
            )
            reached += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                db.session.delete(sub)  # subscription expired/revoked, prune it
            else:
                log.warning('push to subscription %s failed: %s', sub.id, e)
        except (requests.RequestException, ValueError) as e:
            # ValueError: the device's stored keys do not decode. That is
            # one device's problem, not a reason to skip the others.
            log.warning('push to subscription %s failed: %s', sub.id, e)
    db.session.commit()
    return reached


def send_push_later(user_id: int, payload: dict):
    """send_push_to_user, off the request's own thread.

    For a request that must not wait on a push service: the invite answered
    only once every one of the partner's devices had been tried (G-133).
    Best effort, like the push itself -- a worker that restarts mid-send loses
    it. Under TESTING it runs inline, so a test sees what it sent.
    """
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                send_push_to_user(user_id, payload)
            except Exception:  # a push is never worth an unhandled thread error
                log.exception('push to user %s failed', user_id)

    if app.config.get('TESTING'):
        run()
        return
    threading.Thread(target=run, name='gym-push', daemon=True).start()

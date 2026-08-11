import json
import re
from urllib.parse import urlparse

from flask import current_app
from pywebpush import webpush, WebPushException

from extensions import db
from models import PushSubscription

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


def send_push_to_user(user_id: int, payload: dict):
    """payload e.g. {'title': 'Rest complete', 'body': 'Time for your next set.'}

    Scoped to one user: this used to fan out to every subscription row, which
    with more than one lifter means one person's rest timer buzzing another
    person's phone.
    """
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
            )
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                db.session.delete(sub)  # subscription expired/revoked, prune it
    db.session.commit()

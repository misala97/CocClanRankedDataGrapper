import json

from flask import current_app
from pywebpush import webpush, WebPushException

from extensions import db
from models import PushSubscription


def send_push_to_all(payload: dict):
    """payload e.g. {'title': 'Rest complete', 'body': 'Time for your next set.'}"""
    for sub in PushSubscription.query.all():
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

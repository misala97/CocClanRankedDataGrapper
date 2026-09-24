"""Web-push subscribe and unsubscribe for this device, and the service
worker itself -- served from the site root so its default scope covers /gym/."""

import datetime as dt
import os

from flask import (
    current_app, jsonify, request, send_from_directory, session,
)
from extensions import (
    db,
)
from models import (
    PushSubscription,
)
from auth import (
    PUSH_SUBSCRIPTION_KEY, _get_csrf_token, login_required,
)
from features.gym.scope import (
    current_user_id,
)
from features.gym.push import (
    is_valid_push_endpoint,
)
from ._blueprint import (
    gym_bp,
)


@gym_bp.route('/sw.js')
def gym_service_worker():
    # A service worker's default max scope is its own directory -- served
    # from /static/gym/sw.js, it could only ever control /static/gym/*, not
    # /gym/*. Serving it from the site root instead gives it the whole site
    # as its default scope, which covers /gym/. No @login_required: the
    # browser fetches this before any page context, and it's static JS with
    # no user data in it anyway.
    return send_from_directory(
        os.path.join(current_app.root_path, 'static', 'gym'),
        'sw.js',
        mimetype='application/javascript',
    )


def _json_object():
    """The request's JSON body when it is an object, else an empty one.

    A list or a bare string used to reach `.get` and answer 500."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _text(value):
    """A JSON string field, or None for anything else -- a number or a list
    in the endpoint's place used to reach the URL parser and the query as-is
    and answer 500."""
    return value if isinstance(value, str) and value else None


@gym_bp.route('/gym/push/token')
@login_required
def gym_push_token():
    """The session's CSRF token, for the service worker.

    The worker has no page and so no <meta name="csrf-token"> to read. Its
    renewal after a pushsubscriptionchange went out without a token, the
    blueprint's gate refused every one, and a rotated subscription stayed
    unknown until a gym page next opened (G-134). Handing the token out is
    safe: another site can make this request but cannot read the answer,
    and under SameSite=Lax its request carries no login in the first place.
    """
    response = jsonify({'token': _get_csrf_token()})
    response.headers['Cache-Control'] = 'no-store'
    return response


@gym_bp.route('/gym/push/subscribe', methods=['POST'])
@login_required
def gym_push_subscribe():
    data = _json_object()
    endpoint = _text(data.get('endpoint'))
    keys = data.get('keys') if isinstance(data.get('keys'), dict) else {}
    p256dh = _text(keys.get('p256dh'))
    auth_key = _text(keys.get('auth'))
    if not endpoint or not p256dh or not auth_key:
        return jsonify({'status': 'error', 'message': 'invalid subscription'}), 400
    if not is_valid_push_endpoint(endpoint):
        return jsonify({'status': 'error', 'message': 'unrecognized push service endpoint'}), 400

    # Looked up by endpoint alone, NOT by (endpoint, user): the column is
    # globally unique, one row per browser installation. Scoping the lookup to
    # the caller would return None for a device the other lifter last
    # subscribed from, and the insert below would then hit the unique
    # constraint and 500. Re-pointing the row is the correct answer anyway --
    # the subscription belongs to whoever is logged in on that device now.
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    now = dt.datetime.utcnow()
    if sub:
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
        sub.user_id = current_user_id()
        # Doubles as the heartbeat: both pages post the subscription the
        # browser already holds on load, so an unchanged POST is a device
        # saying it still exists. Nothing else can say that -- an endpoint
        # stays valid at the push service long after its browser forgot it.
        sub.last_seen_at = now
    else:
        sub = PushSubscription(endpoint=endpoint, p256dh_key=p256dh,
                               auth_key=auth_key, user_id=current_user_id(),
                               last_seen_at=now)
        db.session.add(sub)

    # The endpoint this one rotated away from, when the service worker's
    # pushsubscriptionchange told the client about it. Scoped to the caller:
    # it is a client-supplied endpoint, so unscoped it would be a way to
    # delete anyone's subscription by naming it.
    replaces = _text(data.get('replaces'))
    if replaces and replaces != endpoint:
        (PushSubscription.query
         .filter_by(endpoint=replaces, user_id=current_user_id())
         .delete(synchronize_session=False))

    db.session.flush()
    subscription_id = sub.id
    db.session.commit()
    # Which subscription this login registered, so logging out can take it
    # along (auth.logout) -- that device's, and only that device's.
    if session.get(PUSH_SUBSCRIPTION_KEY) != subscription_id:
        session[PUSH_SUBSCRIPTION_KEY] = subscription_id
    return jsonify({'status': 'ok'})


@gym_bp.route('/gym/push/unsubscribe', methods=['POST'])
@login_required
def gym_push_unsubscribe():
    endpoint = _text(_json_object().get('endpoint'))
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user_id()).delete()
        db.session.commit()
    return jsonify({'status': 'ok'})

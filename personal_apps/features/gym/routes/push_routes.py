"""Web-push subscribe and unsubscribe for this device, and the service
worker itself -- served from the site root so its default scope covers /gym/."""

import os

from flask import (
    current_app, jsonify, request, send_from_directory,
)
from extensions import (
    db,
)
from models import (
    PushSubscription,
)
from auth import (
    login_required,
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


@gym_bp.route('/gym/push/subscribe', methods=['POST'])
@login_required
def gym_push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth_key = keys.get('auth')
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
    if sub:
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
        sub.user_id = current_user_id()
    else:
        db.session.add(PushSubscription(endpoint=endpoint, p256dh_key=p256dh,
                                        auth_key=auth_key, user_id=current_user_id()))
    db.session.commit()
    return jsonify({'status': 'ok'})


@gym_bp.route('/gym/push/unsubscribe', methods=['POST'])
@login_required
def gym_push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user_id()).delete()
        db.session.commit()
    return jsonify({'status': 'ok'})

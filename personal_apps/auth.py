import os
import secrets
from functools import wraps

from flask import Blueprint, render_template, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import AppUser

auth_bp = Blueprint('auth', __name__)

# Precomputed once at import so login() can always run check_password_hash even
# when the username misses -- otherwise a missing user returns measurably
# faster than a wrong password and the form becomes a username oracle.
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))

# Hostname that has access to everything (incl. the overview page at "/").
# Other hostnames (e.g. the public pubquiz-only domain) don't proxy "/" at
# all, so logins from there should land on a route that domain actually serves.
FULL_ACCESS_HOST = os.getenv("PERSONAL_FULL_ACCESS_HOST", "mgemmel.viewdns.net")


def current_user():
    """The logged-in AppUser, or None.

    Resolves the id every request rather than trusting the cookie's contents:
    deleting a user must invalidate their live sessions.
    """
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(AppUser, user_id)


def _is_logged_in():
    return current_user() is not None


def _on_full_access_host():
    return request.host.split(':')[0] == FULL_ACCESS_HOST


@auth_bp.app_context_processor
def _inject_host_flags():
    # Templates brand themselves per hostname: the public pubquiz domain must
    # look like the pub quiz it serves, not like a generic credential form.
    return {'is_full_access_host': _on_full_access_host()}


@auth_bp.after_request
def _no_index(response):
    # Keep the login form out of search/crawler indexes entirely.
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


def _post_login_redirect():
    if request.host.split(':')[0] == FULL_ACCESS_HOST:
        return redirect(url_for('index'))
    return redirect(url_for('pubquiz.pubquiz_admin'))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_logged_in():
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if _is_logged_in():
        return _post_login_redirect()
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = AppUser.query.filter_by(username=username).first()
        # Always hash, even on a missing username -- see _DUMMY_PASSWORD_HASH.
        if check_password_hash(user.password_hash if user else _DUMMY_PASSWORD_HASH, password) and user:
            session.clear()
            session['user_id'] = user.id
            return _post_login_redirect()
        error = 'Invalid username or password.'
    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    if request.host.split(':')[0] == FULL_ACCESS_HOST:
        return redirect(url_for('index'))
    return redirect(url_for('pubquiz.pubquiz'))

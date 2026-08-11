import os
import secrets
from functools import wraps

from flask import Blueprint, abort, render_template, request, session, redirect, url_for
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


@auth_bp.app_context_processor
def _inject_admin_flag():
    # Templates gate admin-only controls (catalogue edit/delete, the users
    # link) on this rather than posting to an @admin_required route and
    # letting a non-admin hit a bare 403 with their input gone.
    return {'is_admin': is_admin()}


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


def is_admin():
    user = current_user()
    return bool(user and user.is_admin)


def admin_required(f):
    """403 for a logged-in non-admin, redirect to login for anonymous.

    403 rather than 404 here: unlike a gym object, the existence of /tips is
    not a secret worth protecting, and a flat "not allowed" is the honest
    answer to a real user asking for someone else's app.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_logged_in():
            return redirect(url_for('auth.login'))
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if _is_logged_in():
        return _post_login_redirect()
    error = None
    if request.method == 'POST':
        if not _valid_csrf(request.form.get('csrf_token')):
            abort(400)
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


MIN_PASSWORD_LENGTH = 8


def _get_csrf_token():
    """Per-session token, minted on first use.

    personal_apps has no app-wide CSRF protection: adding it means a hidden
    field in every existing form across four features, which is its own piece
    of work. These helpers cover the three forms where a forged request would
    be an account takeover -- login, create-user, change-password.
    """
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def _valid_csrf(submitted):
    expected = session.get('csrf_token')
    return bool(expected and submitted and secrets.compare_digest(str(submitted), str(expected)))


@auth_bp.app_context_processor
def _inject_csrf_token():
    return {'csrf_token': _get_csrf_token}


@auth_bp.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    error = None
    if request.method == 'POST':
        if not _valid_csrf(request.form.get('csrf_token')):
            abort(400)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username:
            error = 'Benutzername fehlt.'
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f'Passwort braucht mindestens {MIN_PASSWORD_LENGTH} Zeichen.'
        elif AppUser.query.filter_by(username=username).first():
            error = 'Benutzername ist schon vergeben.'
        else:
            db.session.add(AppUser(
                username=username,
                password_hash=generate_password_hash(password),
                is_admin=bool(request.form.get('is_admin')),
            ))
            db.session.commit()
            return redirect(url_for('auth.admin_users'))
    users = AppUser.query.order_by(AppUser.username).all()
    return render_template('auth/users.html', users=users, error=error, error_user_id=None)


@auth_bp.route('/admin/users/<int:user_id>/update', methods=['POST'])
@admin_required
def admin_update_user(user_id):
    if not _valid_csrf(request.form.get('csrf_token')):
        abort(400)
    user = db.session.get(AppUser, user_id)
    if user is None:
        abort(404)
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    error = None
    if not username:
        error = 'Benutzername fehlt.'
    # Excludes this user, or renaming someone to their own current name would
    # collide with themselves.
    elif AppUser.query.filter(AppUser.username == username, AppUser.id != user.id).first():
        error = 'Benutzername ist schon vergeben.'
    elif password and len(password) < MIN_PASSWORD_LENGTH:
        error = f'Passwort braucht mindestens {MIN_PASSWORD_LENGTH} Zeichen.'

    if error:
        # Re-render rather than redirect, so the typed values survive and the
        # message can be shown against the row it belongs to.
        users = AppUser.query.order_by(AppUser.username).all()
        return render_template('auth/users.html', users=users,
                               error=error, error_user_id=user.id)

    user.username = username
    # An empty password field means "leave it as it is". Renaming someone must
    # not force you to invent a new password for them at the same time.
    if password:
        user.password_hash = generate_password_hash(password)
    db.session.commit()
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    user = current_user()
    error = None
    done = False
    if request.method == 'POST':
        if not _valid_csrf(request.form.get('csrf_token')):
            abort(400)
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        if not check_password_hash(user.password_hash, current_password):
            error = 'Aktuelles Passwort stimmt nicht.'
        elif len(new_password) < MIN_PASSWORD_LENGTH:
            error = f'Neues Passwort braucht mindestens {MIN_PASSWORD_LENGTH} Zeichen.'
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            done = True
    return render_template('auth/account.html', user=user, error=error, done=done)

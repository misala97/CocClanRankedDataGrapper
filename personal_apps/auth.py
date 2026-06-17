import os
import secrets
from functools import wraps

from flask import Blueprint, render_template, request, session, redirect, url_for

auth_bp = Blueprint('auth', __name__)

ADMIN_USER = os.getenv("PERSONAL_ADMIN_USER", "")
ADMIN_PASS = os.getenv("PERSONAL_ADMIN_PASS", "")

# Hostname that has access to everything (incl. the overview page at "/").
# Other hostnames (e.g. the public pubquiz-only domain) don't proxy "/" at
# all, so logins from there should land on a route that domain actually serves.
FULL_ACCESS_HOST = os.getenv("PERSONAL_FULL_ACCESS_HOST", "mgemmel.viewdns.net")


def _is_logged_in():
    return bool(session.get('logged_in'))


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
        ok = (ADMIN_USER and ADMIN_PASS
              and secrets.compare_digest(username.encode(), ADMIN_USER.encode())
              and secrets.compare_digest(password.encode(), ADMIN_PASS.encode()))
        if ok:
            session.clear()
            session['logged_in'] = True
            return _post_login_redirect()
        error = 'Invalid username or password.'
    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    if request.host.split(':')[0] == FULL_ACCESS_HOST:
        return redirect(url_for('index'))
    return redirect(url_for('pubquiz.pubquiz'))

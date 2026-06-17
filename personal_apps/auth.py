import os
import secrets
from functools import wraps

from flask import Blueprint, render_template, request, session, redirect, url_for

auth_bp = Blueprint('auth', __name__)

ADMIN_USER = os.getenv("PERSONAL_ADMIN_USER", "")
ADMIN_PASS = os.getenv("PERSONAL_ADMIN_PASS", "")


def _is_logged_in():
    return bool(session.get('logged_in'))


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
        return redirect(url_for('index'))
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
            return redirect(url_for('index'))
        error = 'Invalid username or password.'
    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

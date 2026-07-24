import os
import secrets
import datetime as _dt
from functools import wraps

from flask import Blueprint, render_template, request, session, redirect, url_for, abort
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from models import AppUser, ClanWar, RaidWeekend, CWLSeason

auth_bp = Blueprint('auth', __name__)

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

# Precomputed at import time so login() can always run check_password_hash
# against *some* hash of the same cost, whether or not the username exists.
# This keeps response timing for "unknown username" and "known username,
# wrong password" indistinguishable, closing the enumeration side-channel.
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _recon_teaser():
    """Small, cheap, real-data teaser for the auth content panel: what's live
    right now plus how many members already have access. Three lightweight
    indexed lookups, same staleness guard app.py's index() uses for war/raid
    so a frozen 'inWar' row past its end_time doesn't read as falsely live."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

    latest_war = ClanWar.query.order_by(ClanWar.start_time.desc()).first()
    clan_name = (latest_war.clan_name if latest_war and latest_war.clan_name else None) or 'the clan'

    live_label = None

    active_war = ClanWar.query.filter(
        ClanWar.state.in_(['preparation', 'inWar'])
    ).order_by(ClanWar.start_time.desc()).first()
    if active_war and active_war.end_time and active_war.end_time <= now:
        active_war = None
    if active_war:
        live_label = 'War in progress' if active_war.state == 'inWar' else 'War prep day'

    if not live_label:
        active_raid = RaidWeekend.query.filter(RaidWeekend.state == 'ongoing') \
            .order_by(RaidWeekend.start_time.desc()).first()
        if active_raid and active_raid.end_time and active_raid.end_time <= now:
            active_raid = None
        if active_raid:
            live_label = 'Raid weekend live'

    if not live_label:
        active_cwl = CWLSeason.query.filter(
            CWLSeason.state.in_(['preparation', 'inWar'])
        ).order_by(CWLSeason.id.desc()).first()
        if active_cwl:
            live_label = 'CWL in progress'

    member_count = AppUser.query.filter_by(is_approved=True).count()

    return {
        'clan_name': clan_name,
        'live_label': live_label,
        'member_count': member_count,
    }

def _get_csrf_token():
    """Session-bound CSRF token for the unauthenticated login/register forms.
    Generated once per session and handed back to the template as a hidden
    field; POST handlers below reject requests whose submitted token doesn't
    match, closing the login-CSRF hole (no third-party CSRF library is a
    dependency of this project, so this is a minimal hand-rolled double
    submit rather than pulling one in)."""
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_hex(32)
        session['csrf_token'] = token
    return token

def _valid_csrf(submitted):
    expected = session.get('csrf_token')
    return bool(expected) and bool(submitted) and secrets.compare_digest(expected, submitted)

def _current_user():
    uid = session.get('user_id')
    return db.session.get(AppUser, uid) if uid else None

def _is_env_admin():
    return bool(session.get('env_admin_logged_in'))

def _is_super_admin():
    if _is_env_admin():
        return True
    u = _current_user()
    return bool(u and u.is_approved and u.is_super_admin)

def _any_access():
    if _is_env_admin():
        return True
    u = _current_user()
    return bool(u and u.is_approved)

def _can_create_reminder_ranked():
    if _is_super_admin():
        return True
    u = _current_user()
    return bool(u and u.is_approved and u.perm_create_reminder_ranked)

def _can_edit_clan_war():
    if _is_super_admin():
        return True
    u = _current_user()
    return bool(u and u.is_approved and u.perm_clan_war_edits)

def require_super_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_super_admin():
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if _any_access():
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        if not _valid_csrf(request.form.get('csrf_token', '')):
            abort(400, description='Invalid or missing CSRF token.')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        env_ok = (ADMIN_USER and ADMIN_PASS
                  and secrets.compare_digest(username.encode(), ADMIN_USER.encode())
                  and secrets.compare_digest(password.encode(), ADMIN_PASS.encode()))
        if env_ok:
            session.clear()
            session['env_admin_logged_in'] = True
            return redirect(url_for('index'))
        u = AppUser.query.filter_by(username=username).first()
        # Always run check_password_hash, even when the username doesn't
        # exist, so an attacker can't time the response to enumerate valid
        # usernames (CWE-208). The dummy hash never matches a real password.
        password_ok = check_password_hash(u.password_hash if u else _DUMMY_PASSWORD_HASH, password)
        if u and password_ok:
            if not u.is_approved:
                error = 'Your account is pending approval.'
            else:
                session.clear()
                session['user_id'] = u.id
                return redirect(url_for('index'))
        else:
            error = 'Invalid username or password.'
    return render_template('auth/login.html', error=error, recon=_recon_teaser(), csrf_token=_get_csrf_token())


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if _any_access():
        return redirect(url_for('index'))
    error = None
    success = None
    if request.method == 'POST':
        if not _valid_csrf(request.form.get('csrf_token', '')):
            abort(400, description='Invalid or missing CSRF token.')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            error = 'Username and password are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif AppUser.query.filter_by(username=username).first():
            error = 'Username already taken.'
        else:
            db.session.add(AppUser(username=username, password_hash=generate_password_hash(password)))
            db.session.commit()
            success = 'Account created — an admin will approve it shortly.'
    return render_template('auth/register.html', error=error, success=success, recon=_recon_teaser(), csrf_token=_get_csrf_token())


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@auth_bp.route('/admin/login')
def admin_login():
    return redirect(url_for('auth.login'))


@auth_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))

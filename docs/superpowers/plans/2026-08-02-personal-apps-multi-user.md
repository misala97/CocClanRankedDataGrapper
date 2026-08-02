# personal_apps Multi-User Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real user accounts to personal_apps and partition every Gym Tracker query per user, so a second person can use the app with their own training history.

**Architecture:** A new `app_user` table replaces the single environment-credential login; `session['user_id']` replaces `session['logged_in']`. Three gym tables gain a `user_id` owner column (sessions, templates, push subscriptions) and the other five inherit ownership through their parent foreign key. A new `features/gym/scope.py` holds ownership-checking loaders, and every route that reads an object id from the URL goes through them instead of `db.get_or_404`. The exercise catalog stays shared and unowned.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy + Flask-SQLAlchemy, Flask-Migrate/Alembic, MySQL (pymysql), pytest, werkzeug.security for password hashing.

**Spec:** `docs/superpowers/specs/2026-08-02-personal-apps-multi-user-design.md`

## Global Constraints

- Branch: `dev_personal`. Do not commit to `main`.
- All paths below are relative to `personal_apps/` unless stated otherwise. Run pytest from `personal_apps/`.
- Tests run against the **real local development database**. It is disposable dev data — normal care, not read-only paranoia. Every fixture that creates rows must delete them in a `finally`.
- The UI language is German. New user-facing copy is German; code, comments and commit messages are English.
- `Exercise.name` is globally unique. Test fixtures that create exercises must use distinct names and clean them up, or later runs fail at insert.
- Ownership failures return **404, never 403**. A 403 confirms the object exists. The one exception is admin-only routes, where the caller is already known to be a legitimate user and 403 is correct.
- The exercise catalog (`gym_exercises`) is shared and gets **no** owner column.
- Migration revision ids are given explicitly per task. Before the first migration, confirm the current head with `flask db heads` — it should be `e9b4c2a71d63`. If it is not, use the actual head as `down_revision` for Task 1.

---

## File Structure

**Created:**
- `features/gym/scope.py` — ownership loaders and pre-filtered queries. The single place that knows how a gym object is tied to a user. ~60 lines.
- `tests/conftest.py` — shared `_admin_id()` helper plus the `client` and `anon_client` fixtures. `tests/` is not a package, so cross-module helpers live here and are imported as `from conftest import ...`.
- `tests/test_gym_ownership.py` — the two-user fixture and the table-driven IDOR test. The durable guarantee that no route leaks.
- `tests/test_auth.py` — password hashing, login, permission gate.
- `templates/auth/users.html` — admin user list + create form.
- `templates/auth/account.html` — change-own-password form.
- `migrations/versions/a4c81f2e5b76_add_app_user_table.py`
- `migrations/versions/b7d93a5c1e40_add_user_id_to_gym_tables.py`

**Modified:**
- `models.py` — add `AppUser`; add `user_id` to `WorkoutSession`, `WorkoutTemplate`, `PushSubscription`.
- `auth.py` — replace env-credential login with password hashing; add `current_user()`, `admin_required`, `/admin/users`, `/account`, CSRF helpers.
- `app.py:64-71` — extend the before_request gate with the admin check; filter `APPS`.
- `features/gym/routes.py` — swap 24 `db.get_or_404` calls for scope loaders; scope ~15 list/history queries.
- `features/gym/push.py:45-61` — `send_push_to_all` becomes `send_push_to_user`.
- `run_gym_notifier.py:12-22` — resolve each pending push to its session's owner.
- `templates/auth/login.html:97` — CSRF token.
- `templates/overview.html` — no change needed; `app.py` filters the list it receives.
- `tests/test_gym_routes_smoke.py` — session fixture uses `user_id`; 8 `WorkoutSession(...)` constructions gain `user_id`.

---

### Task 1: `app_user` table and the admin seed

**Files:**
- Modify: `models.py` (append after `PendingPush`, currently ends line 305)
- Create: `migrations/versions/a4c81f2e5b76_add_app_user_table.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `models.AppUser` with fields `id: int`, `username: str`, `password_hash: str`, `created_at: datetime`, `is_admin: bool`. Every later task imports it from `models`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth.py`:

```python
"""Account model, login, and the admin permission gate.

Runs against the real local development database, like the other suites here.
"""
import pytest
from werkzeug.security import check_password_hash

from app import app as flask_app


def test_app_user_model_exists_and_hashes():
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash

    with flask_app.app_context():
        user = AppUser(username='pytest hash probe',
                       password_hash=generate_password_hash('correct horse'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    try:
        with flask_app.app_context():
            stored = db.session.get(AppUser, user_id)
            assert stored.username == 'pytest hash probe'
            assert stored.is_admin is False
            assert stored.created_at is not None
            assert check_password_hash(stored.password_hash, 'correct horse')
            assert not check_password_hash(stored.password_hash, 'wrong')
    finally:
        with flask_app.app_context():
            doomed = db.session.get(AppUser, user_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_migration_seeded_an_admin():
    """The migration seeds one admin from PERSONAL_ADMIN_USER so the author
    can still log in after deployment."""
    from models import AppUser
    with flask_app.app_context():
        admins = AppUser.query.filter_by(is_admin=True).all()
        assert len(admins) >= 1, 'migration did not seed an admin account'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'AppUser' from 'models'`

- [ ] **Step 3: Add the model**

Append to `models.py`, after the `PendingPush` class:

```python
class AppUser(db.Model):
    # personal_apps had exactly one user until 2026-08-02: authentication was a
    # single credential pair compared against the environment. This table is
    # what "belongs to someone" now means -- see gym_workout_sessions.user_id.
    __tablename__ = 'app_user'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    # The whole permission model: an admin sees every app, a non-admin sees
    # Gym only. A per-app permission table is the thing to add if a third
    # person ever needs a different slice -- not before.
    is_admin      = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/a4c81f2e5b76_add_app_user_table.py`:

```python
"""add app_user table and seed the admin from the environment

Revision ID: a4c81f2e5b76
Revises: e9b4c2a71d63
Create Date: 2026-08-02 00:00:00.000000

"""
import os

from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash


# revision identifiers, used by Alembic.
revision = 'a4c81f2e5b76'
down_revision = 'e9b4c2a71d63'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_user',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    # Seed the author's account from the credentials the app authenticated
    # against until now, so the first login after deployment uses exactly the
    # username and password already in use. Task 2 then deletes the
    # environment code path entirely.
    username = os.getenv('PERSONAL_ADMIN_USER', '')
    password = os.getenv('PERSONAL_ADMIN_PASS', '')
    if not (username and password):
        raise RuntimeError(
            'PERSONAL_ADMIN_USER / PERSONAL_ADMIN_PASS must be set when running '
            'this migration -- they are the only source for the seeded admin account.')
    op.get_bind().execute(
        sa.text('INSERT INTO app_user (username, password_hash, created_at, is_admin) '
                'VALUES (:username, :password_hash, UTC_TIMESTAMP(), 1)'),
        {'username': username, 'password_hash': generate_password_hash(password)},
    )


def downgrade():
    op.drop_table('app_user')
```

- [ ] **Step 5: Apply the migration**

Run: `flask db upgrade`
Expected: `Running upgrade e9b4c2a71d63 -> a4c81f2e5b76, add app_user table and seed the admin from the environment`

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS, 2 passed

- [ ] **Step 7: Verify the migration is reversible**

Run: `flask db downgrade` then `flask db upgrade`
Expected: both succeed with no error. Confirm the admin row exists again:

Run: `python -c "from app import app; from models import AppUser; app.app_context().push(); print(AppUser.query.filter_by(is_admin=True).count())"`
Expected: `1`

- [ ] **Step 8: Commit**

```bash
git add models.py migrations/versions/a4c81f2e5b76_add_app_user_table.py tests/test_auth.py
git commit -m "feat(auth): add app_user table, seeded from the environment credentials"
```

---

### Task 2: Password-based login

**Files:**
- Modify: `auth.py:9-10` (env constants), `auth.py:18-19` (`_is_logged_in`), `auth.py:55-79` (login/logout)
- Create: `tests/conftest.py`
- Modify: `tests/test_gym_routes_smoke.py:8-14` (delete the local client fixture)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `models.AppUser` from Task 1.
- Produces:
  - `auth.current_user() -> AppUser | None` — the logged-in user, or None.
  - `auth.login_required` — unchanged name and behaviour, now checks `session['user_id']`.
  - `session['user_id']: int` — set on successful login. `session['logged_in']` no longer exists anywhere.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
@pytest.fixture()
def temp_user():
    """A throwaway non-admin account. Yields (id, username, password)."""
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash
    username, password = 'pytest login probe', 'ein sicheres Passwort'
    with flask_app.app_context():
        user = AppUser(username=username,
                       password_hash=generate_password_hash(password),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id, username, password
    with flask_app.app_context():
        doomed = db.session.get(AppUser, user_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


@pytest.fixture()
def anon_client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        yield test_client


def test_login_with_the_right_password_sets_user_id(anon_client, temp_user):
    user_id, username, password = temp_user
    response = anon_client.post('/login', data={'username': username, 'password': password})
    assert response.status_code in (302, 303)
    with anon_client.session_transaction() as flask_session:
        assert flask_session['user_id'] == user_id


def test_login_with_the_wrong_password_sets_nothing(anon_client, temp_user):
    _, username, _ = temp_user
    anon_client.post('/login', data={'username': username, 'password': 'falsch'})
    with anon_client.session_transaction() as flask_session:
        assert 'user_id' not in flask_session


def test_a_missing_username_and_a_wrong_password_are_indistinguishable(anon_client, temp_user):
    """Both must render the same error. A different message (or a redirect on
    one and not the other) tells an attacker which usernames exist."""
    _, username, _ = temp_user
    wrong_password = anon_client.post('/login', data={'username': username, 'password': 'falsch'})
    no_such_user = anon_client.post('/login', data={'username': 'kein solcher Nutzer', 'password': 'falsch'})
    assert wrong_password.status_code == no_such_user.status_code
    assert wrong_password.get_data() == no_such_user.get_data()


def test_a_session_pointing_at_a_deleted_user_is_logged_out(anon_client):
    """Deleting a user must invalidate their live sessions, not 500."""
    with anon_client.session_transaction() as flask_session:
        flask_session['user_id'] = 999999      # no such row
    response = anon_client.get('/gym')
    assert response.status_code in (302, 303)
    assert '/login' in response.headers['Location']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v -k "login or deleted"`
Expected: FAIL — the login route still compares against the environment, so `user_id` is never set.

- [ ] **Step 3: Rewrite auth.py's authentication**

In `auth.py`, replace lines 9-10:

```python
ADMIN_USER = os.getenv("PERSONAL_ADMIN_USER", "")
ADMIN_PASS = os.getenv("PERSONAL_ADMIN_PASS", "")
```

with:

```python
# Precomputed once at import so login() can always run check_password_hash even
# when the username misses -- otherwise a missing user returns measurably
# faster than a wrong password and the form becomes a username oracle.
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))
```

Update the imports at the top of `auth.py` (currently lines 1-5):

```python
import os
import secrets
from functools import wraps

from flask import Blueprint, render_template, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import AppUser
```

Replace `_is_logged_in` (lines 18-19):

```python
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
```

Replace the body of `login()` (lines 60-70) — the `if request.method == 'POST':` block:

```python
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
```

- [ ] **Step 4: Move the shared test fixtures into a conftest**

`tests/` has no `__init__.py`, so it is not a package and `from tests.x import y` will not resolve. pytest puts `tests/` itself on `sys.path`, so shared helpers go in a conftest and are imported by plain module name.

Create `tests/conftest.py`:

```python
"""Shared fixtures. Every suite here runs against the real local development
database, so the account these clients log in as is the seeded admin."""
import pytest

from app import app as flask_app


def _admin_id():
    """The seeded admin's id. Imported by the other suites as
    `from conftest import _admin_id` -- tests/ is on sys.path, not a package."""
    from models import AppUser
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None, 'the dev database needs the seeded admin account'
        return admin.id


@pytest.fixture()
def client():
    """Logged in as the author. The gym suites act as the admin throughout."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = _admin_id()
        yield test_client


@pytest.fixture()
def anon_client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        yield test_client
```

In `tests/test_gym_routes_smoke.py`, **delete** the local `client` fixture at lines 8-14 — conftest fixtures are discovered automatically, and a local one would shadow it. Add the import at the top of the file instead:

```python
from conftest import _admin_id
```

In `tests/test_auth.py`, delete the local `anon_client` fixture written in Step 1 (conftest now provides it) and add the same import:

```python
from conftest import _admin_id
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS, 6 passed

Run: `python -m pytest tests/ -v`
Expected: PASS — the whole suite, no regressions. `user_id` is not a column yet, so the gym tests still work unchanged.

- [ ] **Step 6: Commit**

```bash
git add auth.py tests/
git commit -m "feat(auth): authenticate against app_user instead of the environment"
```

---

### Task 3: Admin gate and per-user app list

**Files:**
- Modify: `app.py:64-71` (before_request), `app.py:102-105` (index)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `auth.current_user` from Task 2.
- Produces:
  - `auth.admin_required` — decorator, 403 for a non-admin. Used by Task 7 and Task 10.
  - `app.GYM_APP` / filtered `APPS` — the overview list a non-admin receives has exactly one entry.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
@pytest.fixture()
def member_client(temp_user):
    """A client logged in as the throwaway non-admin."""
    user_id, _, _ = temp_user
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id
        yield test_client


@pytest.mark.parametrize('path', ['/tips', '/quizbank', '/pubquiz/admin'])
def test_a_non_admin_cannot_reach_the_other_apps(member_client, path):
    assert member_client.get(path).status_code == 403


def test_a_non_admin_can_reach_the_gym(member_client):
    assert member_client.get('/gym').status_code == 200


def test_the_overview_shows_one_app_to_a_non_admin_and_four_to_an_admin(member_client):
    from conftest import _admin_id
    member_html = member_client.get('/').get_data(as_text=True)
    assert 'Gym Tracker' in member_html
    assert 'Pub Quiz' not in member_html
    assert 'Trinkgeld Tracker' not in member_html

    with flask_app.test_client() as admin_client:
        with admin_client.session_transaction() as flask_session:
            flask_session['user_id'] = _admin_id()
        admin_html = admin_client.get('/').get_data(as_text=True)
    assert 'Gym Tracker' in admin_html
    assert 'Pub Quiz' in admin_html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v -k "non_admin or overview"`
Expected: FAIL — `/tips` returns 200 for the non-admin; the overview shows all four apps.

- [ ] **Step 3: Add `admin_required` to auth.py**

Append to `auth.py`, after `login_required`:

```python
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
```

Add `abort` to the flask import line in `auth.py`:

```python
from flask import Blueprint, abort, render_template, request, session, redirect, url_for
```

- [ ] **Step 4: Extend the before_request gate in app.py**

Replace `app.py:64-71`:

```python
@app.before_request
def _require_login_on_full_access_host():
    if request.host.split(':')[0] != FULL_ACCESS_HOST:
        return
    if request.endpoint in ('auth.login', 'auth.logout', 'static'):
        return
    if not _is_logged_in():
        return redirect(url_for('auth.login'))
```

with:

```python
# Blueprints a non-admin may reach. Everything else on the full-access host is
# the author's: the other three apps hold no per-user data and are not
# partitioned (see the multi-user design spec, decision 1).
_MEMBER_BLUEPRINTS = {'gym', 'auth'}


@app.before_request
def _require_login_on_full_access_host():
    if request.host.split(':')[0] != FULL_ACCESS_HOST:
        return
    if request.endpoint in ('auth.login', 'auth.logout', 'static', 'gym.gym_service_worker'):
        return
    if not _is_logged_in():
        return redirect(url_for('auth.login'))
    if not is_admin() and request.blueprint not in _MEMBER_BLUEPRINTS:
        abort(403)
```

Update the imports in `app.py:5` and `app.py:46`:

```python
from flask import Flask, abort, render_template, request, redirect, url_for
```

```python
from auth import auth_bp, _is_logged_in, login_required, is_admin
```

- [ ] **Step 5: Filter the overview list**

Replace `app.py:102-105`:

```python
@app.route('/')
@login_required
def index():
    return render_template('overview.html', apps=APPS)
```

with:

```python
@app.route('/')
@login_required
def index():
    # A non-admin's landing page lists the one app they can open, rather than
    # four tiles of which three would 403.
    visible = APPS if is_admin() else [a for a in APPS if a['url'] == '/gym']
    return render_template('overview.html', apps=visible)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS, 11 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add auth.py app.py tests/test_auth.py
git commit -m "feat(auth): gate the non-gym apps behind is_admin"
```

---

### Task 4: Owner columns on the three gym roots

**Files:**
- Modify: `models.py:165-176` (`WorkoutTemplate`), `models.py:191-216` (`WorkoutSession`), `models.py:287-293` (`PushSubscription`)
- Create: `migrations/versions/b7d93a5c1e40_add_user_id_to_gym_tables.py`
- Modify: `tests/test_gym_routes_smoke.py` — 8 `WorkoutSession(...)` constructions
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `models.AppUser` from Task 1.
- Produces: `WorkoutSession.user_id: int`, `WorkoutTemplate.user_id: int`, `PushSubscription.user_id: int`, all NOT NULL with a foreign key to `app_user.id`. Task 5 onwards filters on these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gym_ownership.py`:

```python
"""Ownership of gym data.

The IDOR table test at the bottom of this file is the durable guarantee that
no gym route leaks another user's data: it loops over every route that takes an
object id, so a new unscoped route fails the moment it is added.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import pytest

from app import app as flask_app


def test_the_three_roots_carry_an_owner():
    from models import PushSubscription, WorkoutSession, WorkoutTemplate
    for model in (WorkoutSession, WorkoutTemplate, PushSubscription):
        assert hasattr(model, 'user_id'), f'{model.__name__} has no user_id'
        # __table__.c, not the mapped attribute: an InstrumentedAttribute has
        # no .nullable of its own.
        assert model.__table__.c.user_id.nullable is False, \
            f'{model.__name__}.user_id must be NOT NULL'


def test_every_pre_existing_row_was_backfilled_to_the_admin():
    """Rows created by this suite's own fixtures are excluded by name -- they
    are deliberately owned by throwaway users, and this assertion is about what
    the migration did to the data that already existed."""
    import sqlalchemy as sa
    from models import AppUser, WorkoutSession, WorkoutTemplate
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None
        for model in (WorkoutSession, WorkoutTemplate):
            orphans = model.query.filter(
                model.user_id != admin.id,
                # WorkoutSession.name is nullable, and NOT LIKE is NULL (not
                # true) for a NULL -- without the is_(None) arm an unnamed row
                # owned by someone else would slip past this check.
                sa.or_(model.name.is_(None), model.name.notlike('pytest%')),
            ).count()
            assert orphans == 0, f'{model.__name__} has rows not owned by the admin'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: FAIL — `AssertionError: WorkoutSession has no user_id`

- [ ] **Step 3: Add the columns to models.py**

In `WorkoutTemplate` (after `name`, line 168) add:

```python
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
```

In `WorkoutSession` (after `name`, line 194) add:

```python
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
```

In `PushSubscription` (after `id`, line 289) add:

```python
    # A root with no parent to inherit from -- and the reason this column
    # exists at all: send_push_to_all used to fan out to every row, which
    # after this change would buzz the wrong person's phone.
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
```

The four child tables (`gym_template_exercises`, `gym_session_exercises`, `gym_session_sets`, `gym_pending_pushes`) get **no** column — they inherit through their parent foreign key. `gym_exercises` gets no column: the catalog is shared.

- [ ] **Step 4: Write the migration**

Create `migrations/versions/b7d93a5c1e40_add_user_id_to_gym_tables.py`:

```python
"""add user_id to the three gym root tables

Revision ID: b7d93a5c1e40
Revises: a4c81f2e5b76
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d93a5c1e40'
down_revision = 'a4c81f2e5b76'
branch_labels = None
depends_on = None

_TABLES = ('gym_workout_sessions', 'gym_workout_templates', 'gym_push_subscriptions')


def upgrade():
    connection = op.get_bind()
    admin_id = connection.execute(sa.text(
        'SELECT id FROM app_user WHERE is_admin = 1 ORDER BY id LIMIT 1')).scalar()
    if admin_id is None:
        raise RuntimeError(
            'no admin account to backfill ownership to -- run the a4c81f2e5b76 '
            'migration first, which seeds it.')

    # Added nullable, backfilled, then tightened. Doing it in one step would
    # fail against a non-empty table, and doing it without the backfill would
    # leave every existing row violating the constraint.
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    for table in _TABLES:
        connection.execute(
            sa.text(f'UPDATE {table} SET user_id = :admin_id WHERE user_id IS NULL'),
            {'admin_id': admin_id},
        )

    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(f'ix_{table}_user_id', ['user_id'])
            batch_op.create_foreign_key(f'fk_{table}_user_id', 'app_user', ['user_id'], ['id'])


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_user_id', type_='foreignkey')
            batch_op.drop_index(f'ix_{table}_user_id')
            batch_op.drop_column('user_id')
```

- [ ] **Step 5: Apply the migration**

Run: `flask db upgrade`
Expected: `Running upgrade a4c81f2e5b76 -> b7d93a5c1e40, add user_id to the three gym root tables`

- [ ] **Step 6: Give the smoke-test fixtures an owner**

Every `WorkoutSession(...)` construction in `tests/test_gym_routes_smoke.py` now needs `user_id`. There are 8, at approximately lines 32, 296, 351, 443, 452, 518, 697 and 704. Add `user_id=_admin_id()` to each. For example, line 32 becomes:

```python
        session_ = WorkoutSession(name='pytest scratch', started_at=dt.datetime.utcnow(),
                                  user_id=_admin_id())
```

and line 296 becomes:

```python
                session_ = WorkoutSession(
                    name='pytest seed {}'.format(offset), started_at=started,
                    finished_at=started + dt.timedelta(hours=1), is_deload=deload,
                    deload_pct=70 if deload else None, user_id=_admin_id())
```

Find them all with:

Run: `grep -n "WorkoutSession(" tests/test_gym_routes_smoke.py`
Expected: 8 lines. Every one must end up with a `user_id=` argument.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 2 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions. A `NOT NULL constraint failed` here means a fixture was missed in Step 6.

- [ ] **Step 8: Verify the migration is reversible**

Run: `flask db downgrade` then `flask db upgrade`
Expected: both succeed. Re-run `python -m pytest tests/test_gym_ownership.py -v` — still PASS.

- [ ] **Step 9: Commit**

```bash
git add models.py migrations/versions/b7d93a5c1e40_add_user_id_to_gym_tables.py tests/
git commit -m "feat(gym): add user_id to sessions, templates and push subscriptions"
```

---

### Task 5: `scope.py` and the session routes

**Files:**
- Create: `features/gym/scope.py`
- Modify: `features/gym/routes.py` — 9 `db.get_or_404(WorkoutSession, ...)` calls at lines 589, 860, 1168, 1213, 1224, 1262, 1325, 1340, 1354
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `user_id` columns from Task 4; `auth.current_user` from Task 2.
- Produces, all in `features.gym.scope`:
  - `current_user_id() -> int | None`
  - `my_sessions() -> Query` — `WorkoutSession` filtered to the caller
  - `my_templates() -> Query` — `WorkoutTemplate` filtered to the caller
  - `owned_session(session_id: int) -> WorkoutSession` — aborts 404
  - `owned_template(template_id: int) -> WorkoutTemplate` — aborts 404
  - `owned_session_exercise(session_exercise_id: int) -> SessionExercise` — aborts 404 (used in Task 6)
  - `owned_set(set_id: int) -> SessionSet` — aborts 404 (used in Task 6)

- [ ] **Step 1: Write the two-user fixture and the session-route table test**

Append to `tests/test_gym_ownership.py`:

```python
import datetime as dt


@pytest.fixture()
def two_users():
    """Owner A (admin) with a full object graph, and intruder B (non-admin).

    Yields a dict of A's object ids plus B's user id. Everything is deleted
    afterwards, in dependency order.
    """
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SessionSet,
                        TemplateExercise, WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    created = {}
    with flask_app.app_context():
        owner = AppUser(username='pytest owner A',
                        password_hash=generate_password_hash('a'), is_admin=True)
        intruder = AppUser(username='pytest intruder B',
                           password_hash=generate_password_hash('b'), is_admin=False)
        db.session.add_all([owner, intruder])
        db.session.flush()

        exercise = Exercise(name='pytest ownership lift', muscle_group='Brust')
        db.session.add(exercise)
        db.session.flush()

        template = WorkoutTemplate(name='pytest ownership template', user_id=owner.id)
        template.exercises.append(TemplateExercise(exercise_id=exercise.id, position=1))
        db.session.add(template)
        db.session.flush()

        workout = WorkoutSession(name='pytest ownership session',
                                 started_at=dt.datetime.utcnow(), user_id=owner.id)
        session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
        session_exercise.sets = [SessionSet(position=1, weight=123.5, reps=7, completed=True)]
        workout.exercises.append(session_exercise)
        db.session.add(workout)
        db.session.commit()

        created = {
            'owner_id': owner.id,
            'intruder_id': intruder.id,
            'exercise_id': exercise.id,
            'template_id': template.id,
            'session_id': workout.id,
            'session_exercise_id': workout.exercises[0].id,
            'set_id': workout.exercises[0].sets[0].id,
        }
    yield created

    with flask_app.app_context():
        doomed_session = db.session.get(WorkoutSession, created['session_id'])
        if doomed_session is not None:
            doomed_session.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed_session)
            db.session.commit()
        doomed_template = db.session.get(WorkoutTemplate, created['template_id'])
        if doomed_template is not None:
            db.session.delete(doomed_template)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, created['exercise_id'])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()
        for user_id in (created['owner_id'], created['intruder_id']):
            doomed_user = db.session.get(AppUser, user_id)
            if doomed_user is not None:
                db.session.delete(doomed_user)
        db.session.commit()


@pytest.fixture()
def intruder_client(two_users):
    """A client logged in as B, who owns nothing."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['intruder_id']
        yield test_client


# (method, url template, which id from the two_users fixture fills the {})
SESSION_ROUTES = [
    ('GET',  '/gym/session/{}',                    'session_id'),
    ('POST', '/gym/session/{}/exercises/add',      'session_id'),
    ('POST', '/gym/session/{}/exercises/reorder',  'session_id'),
    ('POST', '/gym/session/{}/rest/skip',          'session_id'),
    ('POST', '/gym/session/{}/finish',             'session_id'),
    ('POST', '/gym/session/{}/deload',             'session_id'),
    ('GET',  '/gym/session/{}/summary',            'session_id'),
    ('POST', '/gym/session/{}/delete',             'session_id'),
    ('POST', '/gym/session/{}/update_template',    'session_id'),
    ('POST', '/gym/session/{}/save_as_template',   'session_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', SESSION_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_session(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


def test_the_owners_session_still_works(two_users):
    """The scoping must not break the owner -- a 404 for everyone is not a fix."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        assert owner_client.get('/gym/session/{}'.format(two_users['session_id'])).status_code == 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_ownership.py -v -k stranger`
Expected: FAIL — 10 failures, each reporting 200/302 instead of 404. This is the leak the task closes.

- [ ] **Step 3: Create scope.py**

Create `features/gym/scope.py`:

```python
"""Ownership rules for gym data.

The single place that knows how a gym object is tied to a user. Routes call
these instead of db.get_or_404 -- doing the check inline at 25 call sites is
how a leak arrives on the twenty-sixth.

Ownership lives on three roots (WorkoutSession, WorkoutTemplate,
PushSubscription); everything else inherits through its parent foreign key.
The exercise catalogue is deliberately shared and has no owner, so there is
no loader for it here -- see the multi-user design spec, decision 2.

Every failure is 404, never 403: a 403 confirms the object exists.
"""
from flask import abort, session as flask_session

from extensions import db
from models import SessionExercise, SessionSet, WorkoutSession, WorkoutTemplate


def current_user_id():
    """The logged-in user's id, or None. The gate in app.py means routes
    reached through the app always have one."""
    return flask_session.get('user_id')


def my_sessions():
    """WorkoutSession query filtered to the caller. Use for every list,
    history and aggregate read."""
    return WorkoutSession.query.filter(WorkoutSession.user_id == current_user_id())


def my_templates():
    return WorkoutTemplate.query.filter(WorkoutTemplate.user_id == current_user_id())


def owned_session(session_id):
    row = db.session.get(WorkoutSession, session_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row


def owned_template(template_id):
    row = db.session.get(WorkoutTemplate, template_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row


def owned_session_exercise(session_exercise_id):
    row = db.session.get(SessionExercise, session_exercise_id)
    if row is None or row.session.user_id != current_user_id():
        abort(404)
    return row


def owned_set(set_id):
    row = db.session.get(SessionSet, set_id)
    if row is None or row.session_exercise.session.user_id != current_user_id():
        abort(404)
    return row
```

- [ ] **Step 4: Swap the session loaders in routes.py**

Add to the imports at the top of `features/gym/routes.py`, after line 16:

```python
from features.gym.scope import (
    current_user_id, my_sessions, my_templates,
    owned_session, owned_session_exercise, owned_set, owned_template,
)
```

Replace every `db.get_or_404(WorkoutSession, session_id)` with `owned_session(session_id)`. There are 9, at lines 589, 860, 1168, 1213, 1224, 1262, 1325, 1340, 1354. Verify none remain:

Run: `grep -n "get_or_404(WorkoutSession" features/gym/routes.py`
Expected: no output.

`gym_session_summary` (line 1315) does not load the session at all — it redirects. Add the ownership check as its first statement so a stranger gets 404 rather than a redirect:

```python
def gym_session_summary(session_id):
    owned_session(session_id)   # 404 for a stranger rather than a redirect that then 404s
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 13 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add features/gym/scope.py features/gym/routes.py tests/test_gym_ownership.py
git commit -m "feat(gym): scope every session route to its owner"
```

---

### Task 6: Session-exercise and set routes

**Files:**
- Modify: `features/gym/routes.py` — 6 `db.get_or_404(SessionExercise, ...)` at lines 907, 947, 965, 976, 1000, 1024; 3 `db.get_or_404(SessionSet, ...)` at lines 1049, 1080, 1135
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `owned_session_exercise`, `owned_set` from Task 5.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_ownership.py`:

```python
DESCENDANT_ROUTES = [
    ('POST', '/gym/session-exercise/{}/replace',   'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/rest',      'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/increment', 'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/sets/add',  'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/delete',    'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/skip',      'session_exercise_id'),
    ('POST', '/gym/set/{}/delete',                 'set_id'),
    ('POST', '/gym/set/{}/toggle_complete',        'set_id'),
    ('POST', '/gym/set/{}/update',                 'set_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', DESCENDANT_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_session_exercise_or_set(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


def test_a_rejected_write_changed_nothing(intruder_client, two_users):
    """A 404 is only half the guarantee -- the write must not have landed."""
    from extensions import db
    from models import SessionSet
    intruder_client.post('/gym/set/{}/update'.format(two_users['set_id']),
                         data={'weight': '999', 'reps': '1'})
    with flask_app.app_context():
        stored = db.session.get(SessionSet, two_users['set_id'])
        assert (stored.weight, stored.reps) == (123.5, 7)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_ownership.py -v -k "session_exercise_or_set or rejected_write"`
Expected: FAIL — 9 routes return 302 instead of 404, and the weight is 999.0.

- [ ] **Step 3: Swap the loaders**

In `features/gym/routes.py`, replace every `db.get_or_404(SessionExercise, session_exercise_id)` with `owned_session_exercise(session_exercise_id)` (6 sites) and every `db.get_or_404(SessionSet, set_id)` with `owned_set(set_id)` (3 sites).

Verify none remain:

Run: `grep -nE "get_or_404\((SessionExercise|SessionSet)" features/gym/routes.py`
Expected: no output.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 23 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add features/gym/routes.py tests/test_gym_ownership.py
git commit -m "feat(gym): scope session-exercise and set routes to their owner"
```

---

### Task 7: Template routes and admin-only catalogue writes

**Files:**
- Modify: `features/gym/routes.py:1370,1381` (template loaders), `routes.py:1384` (template detach query), `routes.py:2200-2233` (catalogue writes)
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `owned_template` from Task 5; `auth.admin_required` from Task 3.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_ownership.py`:

```python
TEMPLATE_ROUTES = [
    ('POST', '/gym/templates/{}/rename', 'template_id'),
    ('POST', '/gym/templates/{}/delete', 'template_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', TEMPLATE_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_template(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


CATALOGUE_ADMIN_ROUTES = [
    ('POST', '/gym/exercises/{}/update', 'exercise_id'),
    ('POST', '/gym/exercises/{}/delete', 'exercise_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', CATALOGUE_ADMIN_ROUTES)
def test_a_non_admin_cannot_edit_the_shared_catalogue(
        intruder_client, two_users, method, url_template, id_key):
    """The catalogue is shared, so there is no owner to check -- but curating
    it is the admin's job. 403 here, not 404: the exercise is legitimately
    visible to this user, only editing it is refused."""
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 403, f'{method} {url} returned {response.status_code}'


def test_the_shared_exercise_survived_the_rejected_writes(two_users):
    from extensions import db
    from models import Exercise
    with flask_app.app_context():
        assert db.session.get(Exercise, two_users['exercise_id']) is not None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_ownership.py -v -k "template or catalogue"`
Expected: FAIL — templates return 302, catalogue writes return 302 instead of 403.

- [ ] **Step 3: Swap the template loaders**

In `features/gym/routes.py`, replace `db.get_or_404(WorkoutTemplate, template_id)` at lines 1370 and 1381 with `owned_template(template_id)`.

Line 1384 detaches sessions from a deleted template and must not touch another user's rows:

```python
    WorkoutSession.query.filter_by(template_id=template.id).update({'template_id': None})
```

becomes:

```python
    my_sessions().filter_by(template_id=template.id).update({'template_id': None}, synchronize_session=False)
```

Line 1342, inside `gym_update_template`, loads the session's own template:

```python
        template = db.session.get(WorkoutTemplate, session_.template_id)
```

becomes:

```python
        template = my_templates().filter_by(id=session_.template_id).first()
```

Line 564, inside `gym_start`, loads the template a session starts from:

```python
        template = db.session.get(WorkoutTemplate, template_id)
```

becomes:

```python
        template = my_templates().filter_by(id=template_id).first()
```

This is the cross-user foreign-key guard from the spec: a session can only ever be started from a template the caller owns.

Verify no unscoped template loads remain:

Run: `grep -nE "get_or_404\(WorkoutTemplate|db\.session\.get\(WorkoutTemplate" features/gym/routes.py`
Expected: no output.

- [ ] **Step 4: Make the catalogue writes admin-only**

In `features/gym/routes.py`, add `admin_required` to the import from `auth` (line 13):

```python
from auth import login_required, admin_required
```

Add the decorator to `gym_update_exercise` (line 2200) and `gym_delete_exercise` (line 2225), below the existing `@login_required`:

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
@admin_required
def gym_update_exercise(exercise_id):
```

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>/delete', methods=['POST'])
@login_required
@admin_required
def gym_delete_exercise(exercise_id):
```

`gym_add_exercise` (line 2174) stays open to everyone: adding a missing lift to the shared catalogue is decision 2's explicit allowance.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 28 passed

Run: `python -m pytest tests/ -v`
Expected: PASS. Note `test_update_exercise_sets_and_clears_the_increment_without_losing_other_fields` in the smoke suite posts to `/gym/exercises/<id>/update` as the seeded admin, so it still passes.

- [ ] **Step 6: Commit**

```bash
git add features/gym/routes.py tests/test_gym_ownership.py
git commit -m "feat(gym): scope template routes, restrict catalogue edits to admins"
```

---

### Task 8: History and list queries

This is the task the spec calls the trap: the object is shared or the route takes no id at all, but the data rendered beside it is private.

**Files:**
- Modify: `features/gym/routes.py` at lines 108-113 (`_get_active_session`), 182-193 (`_last_session_exercise`), 374-382 (`_performed_query`), 453, 459, 464, 501 (`gym_heute`), 601, 619 (session detail), 1402 (`gym_verlauf`), 1668 (`gym_export`), 2080-2130 (exercise detail), 2139-2173 (`progress.json`)
- Modify: `tests/conftest.py` (add `acting_as`), `tests/test_gym_routes_smoke.py` (three direct-call tests)
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `my_sessions`, `my_templates`, `current_user_id` from Task 5.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_ownership.py`:

```python
LEAKY_PAGES = [
    '/gym',
    '/gym/verlauf',
    '/gym/statistik',
    '/gym/export',
    '/gym/uebungen',
]


@pytest.mark.parametrize('path', LEAKY_PAGES)
def test_the_list_pages_show_none_of_another_users_numbers(intruder_client, two_users, path):
    """B has no training data at all, so A's distinctive 123.5 kg must not
    appear anywhere on a page B can open."""
    body = intruder_client.get(path).get_data(as_text=True)
    assert '123.5' not in body, f'{path} leaked another user\'s weight'
    assert 'pytest ownership session' not in body, f'{path} leaked another user\'s session name'


def test_the_shared_exercise_page_shows_no_foreign_history(intruder_client, two_users):
    """The subtle one: the exercise itself is shared and B may open it, but
    the history rendered around it is A's and must not appear."""
    url = '/gym/exercises/{}'.format(two_users['exercise_id'])
    response = intruder_client.get(url)
    assert response.status_code == 200, 'the shared catalogue must stay readable'
    assert '123.5' not in response.get_data(as_text=True)


def test_the_progress_json_carries_no_foreign_history(intruder_client, two_users):
    url = '/gym/exercises/{}/progress.json'.format(two_users['exercise_id'])
    response = intruder_client.get(url)
    assert response.status_code == 200
    assert '123.5' not in response.get_data(as_text=True)


def test_a_stranger_does_not_inherit_the_active_session(intruder_client, two_users):
    """A's session is unfinished. _get_active_session must not hand it to B --
    B would land in someone else's workout on the dashboard."""
    body = intruder_client.get('/gym').get_data(as_text=True)
    assert 'pytest ownership session' not in body


def test_the_owner_still_sees_their_own_numbers(two_users):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        body = owner_client.get('/gym/exercises/{}'.format(two_users['exercise_id'])).get_data(as_text=True)
    assert '123.5' in body, 'scoping hid the owner from their own history'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_ownership.py -v -k "leaked or foreign or inherit"`
Expected: FAIL — several pages contain `123.5`, and `/gym` shows A's active session to B.

- [ ] **Step 3: Scope the three shared helpers**

`_get_active_session` at line 108 — replace:

```python
    session_ = (
        WorkoutSession.query
        .filter_by(finished_at=None)
```

with:

```python
    session_ = (
        my_sessions()
        .filter_by(finished_at=None)
```

`_last_session_exercise` at line 182 already joins `WorkoutSession`; add the owner to its filter list (after the `WorkoutSession.is_deload == False,` line):

```python
            WorkoutSession.is_deload == False,
            # Suggestions come from your own training, never your partner's.
            WorkoutSession.user_id == current_user_id(),
```

`_performed_query` at line 374 also already joins `WorkoutSession`; add after the join at line 381:

```python
        .filter(WorkoutSession.user_id == current_user_id())
```

These three carry most of the app: every suggestion, every statistic and every history list flows through one of them.

- [ ] **Step 4: Give the direct-call tests a request context**

`current_user_id()` reads `flask.session`, which only exists inside a **request** context. Three existing tests call `_last_full_performance` directly from inside a plain `app_context()`, and will now raise `RuntimeError: Working outside of request context`:

- `test_a_new_session_seeds_from_the_last_normal_session_not_the_deload` (call at approximately line 308)
- `test_stale_slot_history_does_not_beat_a_recent_performance` (approximately line 399)
- `test_recent_slot_history_still_wins_over_another_slot` (approximately line 420)

Add this helper to `tests/conftest.py`:

```python
from contextlib import contextmanager

from flask import session as flask_session


@contextmanager
def acting_as(user_id):
    """Request context carrying a logged-in session.

    For tests that call route helpers (_last_full_performance and friends)
    directly rather than through the client: those helpers read flask.session
    to scope their queries, which a plain app_context cannot provide. A
    request context pushes an app context too, so db work inside still works.
    """
    with flask_app.test_request_context():
        flask_session['user_id'] = user_id
        yield
```

In `tests/test_gym_routes_smoke.py`, extend the conftest import:

```python
from conftest import _admin_id, acting_as
```

In each of the three tests above, the `with flask_app.app_context():` block that contains the `_last_full_performance(...)` call becomes:

```python
        with acting_as(_admin_id()):
```

Only those three blocks change. Every other `with flask_app.app_context():` in the file — the setup and cleanup blocks — stays exactly as it is.

- [ ] **Step 5: Scope the remaining list queries**

Replace each of these `WorkoutSession.query` occurrences with `my_sessions()`: lines 459, 464, 501 (`gym_heute`), 601, 619 (session detail), 1402 (`gym_verlauf`), 1668 (`gym_export`).

Replace `WorkoutTemplate.query` at line 453 with `my_templates()`.

Verify nothing unscoped remains:

Run: `grep -nE "WorkoutSession\.query|WorkoutTemplate\.query" features/gym/routes.py`
Expected: no output.

Note `db.session.query(Exercise.muscle_group)` at line 481 and the `Exercise.query` calls at 255, 747, 865, 877, 913, 1720, 2185, 2207 are the **shared catalogue** and stay exactly as they are.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 38 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions. A `RuntimeError: Working outside of request context` here means Step 4 was missed or applied to the wrong block.

- [ ] **Step 7: Commit**

```bash
git add features/gym/routes.py tests/
git commit -m "feat(gym): scope history, suggestion and list queries to the caller"
```

---

### Task 9: Push subscription ownership

**Files:**
- Modify: `features/gym/push.py:45-61`
- Modify: `run_gym_notifier.py:9,12-22`
- Modify: `features/gym/routes.py:842` (`has_push_subscription`), `routes.py:2237-2270` (subscribe/unsubscribe)
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `PushSubscription.user_id` from Task 4.
- Produces: `features.gym.push.send_push_to_user(user_id: int, payload: dict) -> None`. Replaces `send_push_to_all`, which no longer exists.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_ownership.py`:

```python
def test_a_push_goes_only_to_the_sessions_owner(two_users, monkeypatch):
    """The failure that would otherwise show up at 22:00 on a Tuesday: one
    lifter's rest timer buzzing the other's phone."""
    from extensions import db
    from features.gym import push
    from models import PushSubscription

    sent_to = []

    def fake_webpush(subscription_info, **kwargs):
        sent_to.append(subscription_info['endpoint'])

    monkeypatch.setattr(push, 'webpush', fake_webpush)

    endpoints = {}
    with flask_app.app_context():
        for label, user_id in (('owner', two_users['owner_id']),
                               ('intruder', two_users['intruder_id'])):
            endpoint = f'https://fcm.googleapis.com/pytest/{label}'
            db.session.add(PushSubscription(endpoint=endpoint, p256dh_key='k',
                                            auth_key='a', user_id=user_id))
            endpoints[label] = endpoint
        db.session.commit()
    try:
        with flask_app.app_context():
            push.send_push_to_user(two_users['owner_id'],
                                   {'title': 'Rest complete', 'body': 'Time for your next set.'})
        assert sent_to == [endpoints['owner']], 'push reached the wrong subscriptions'
    finally:
        with flask_app.app_context():
            for endpoint in endpoints.values():
                PushSubscription.query.filter_by(endpoint=endpoint).delete()
            db.session.commit()


def test_resubscribing_a_shared_device_repoints_it_instead_of_colliding(intruder_client, two_users):
    """PushSubscription.endpoint is globally unique -- one row per browser
    installation. If B subscribes from a device A last used, the row must move
    to B rather than hitting the unique constraint on insert."""
    from extensions import db
    from models import PushSubscription
    endpoint = 'https://fcm.googleapis.com/pytest/shared-device'
    with flask_app.app_context():
        db.session.add(PushSubscription(endpoint=endpoint, p256dh_key='k', auth_key='a',
                                        user_id=two_users['owner_id']))
        db.session.commit()
    try:
        response = intruder_client.post('/gym/push/subscribe', json={
            'endpoint': endpoint, 'keys': {'p256dh': 'k2', 'auth': 'a2'}})
        assert response.status_code == 200
        with flask_app.app_context():
            stored = PushSubscription.query.filter_by(endpoint=endpoint).one()
            assert stored.user_id == two_users['intruder_id']
    finally:
        with flask_app.app_context():
            PushSubscription.query.filter_by(endpoint=endpoint).delete()
            db.session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_ownership.py -v -k "push or shared_device"`
Expected: FAIL — `AttributeError: module 'features.gym.push' has no attribute 'send_push_to_user'`

- [ ] **Step 3: Replace send_push_to_all**

In `features/gym/push.py`, replace lines 45-61:

```python
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
```

- [ ] **Step 4: Resolve the owner in the notifier**

In `run_gym_notifier.py`, replace line 9:

```python
from features.gym.push import send_push_to_all
```

with:

```python
from features.gym.push import send_push_to_user
```

and replace lines 14-22:

```python
        due = PendingPush.query.filter(
            PendingPush.sent == False,  # noqa: E712 (SQLAlchemy comparison, not a real bool check)
            PendingPush.fire_at <= dt.datetime.utcnow(),
        ).all()
        for pending in due:
            send_push_to_all({'title': 'Rest complete', 'body': 'Time for your next set.'})
            pending.sent = True
        if due:
            db.session.commit()
```

with:

```python
        due = (
            PendingPush.query
            .join(WorkoutSession, PendingPush.session_id == WorkoutSession.id)
            .filter(
                PendingPush.sent == False,  # noqa: E712 (SQLAlchemy comparison, not a real bool check)
                PendingPush.fire_at <= dt.datetime.utcnow(),
            )
            .add_columns(WorkoutSession.user_id)
            .all()
        )
        for pending, user_id in due:
            # A rest timer belongs to whoever started the session it came from.
            send_push_to_user(user_id, {'title': 'Rest complete', 'body': 'Time for your next set.'})
            pending.sent = True
        if due:
            db.session.commit()
```

and update the model import on line 8:

```python
from models import PendingPush, WorkoutSession
```

- [ ] **Step 5: Scope the subscribe/unsubscribe routes**

In `features/gym/routes.py`, replace lines 2248-2253 inside `gym_push_subscribe`:

```python
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
    else:
        db.session.add(PushSubscription(endpoint=endpoint, p256dh_key=p256dh, auth_key=auth_key))
```

with:

```python
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
```

Line 2264, inside `gym_push_unsubscribe`:

```python
        PushSubscription.query.filter_by(endpoint=endpoint).delete()
```

becomes:

```python
        PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user_id()).delete()
```

Line 842, the flag telling the session page whether push is available:

```python
        has_push_subscription=PushSubscription.query.first() is not None,
```

becomes:

```python
        has_push_subscription=PushSubscription.query.filter_by(user_id=current_user_id()).first() is not None,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS, 40 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

Confirm no caller of the old function survives:

Run: `grep -rn "send_push_to_all" . --include=*.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add features/gym/push.py run_gym_notifier.py features/gym/routes.py tests/test_gym_ownership.py
git commit -m "feat(gym): deliver rest-timer pushes only to the session's owner"
```

---

### Task 10: User management, account page and CSRF

**Files:**
- Modify: `auth.py` — CSRF helpers, `/admin/users`, `/account`
- Create: `templates/auth/users.html`, `templates/auth/account.html`
- Modify: `templates/auth/login.html:97`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `AppUser` (Task 1), `admin_required` (Task 3).
- Produces: `/admin/users` (GET, POST) and `/account` (GET, POST); `auth._get_csrf_token()` and `auth._valid_csrf(submitted)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
def test_only_an_admin_reaches_the_user_admin(member_client):
    assert member_client.get('/admin/users').status_code == 403


def test_an_admin_can_create_a_user(temp_user):
    from conftest import _admin_id
    from extensions import db
    from models import AppUser

    flask_app.config['TESTING'] = True
    created_id = None
    try:
        with flask_app.test_client() as admin_client:
            with admin_client.session_transaction() as flask_session:
                flask_session['user_id'] = _admin_id()
            token = admin_client.get('/admin/users')  # issues the CSRF token
            assert token.status_code == 200
            with admin_client.session_transaction() as flask_session:
                csrf = flask_session['csrf_token']
            response = admin_client.post('/admin/users', data={
                'username': 'pytest created user',
                'password': 'lang genug hier',
                'csrf_token': csrf,
            })
            assert response.status_code in (302, 303)
        with flask_app.app_context():
            created = AppUser.query.filter_by(username='pytest created user').first()
            assert created is not None
            assert created.is_admin is False
            created_id = created.id
    finally:
        if created_id is not None:
            with flask_app.app_context():
                doomed = db.session.get(AppUser, created_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_creating_a_user_without_a_csrf_token_is_refused():
    from conftest import _admin_id
    from models import AppUser
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as admin_client:
        with admin_client.session_transaction() as flask_session:
            flask_session['user_id'] = _admin_id()
        response = admin_client.post('/admin/users', data={
            'username': 'pytest csrf victim',
            'password': 'lang genug hier',
        })
    assert response.status_code == 400
    with flask_app.app_context():
        assert AppUser.query.filter_by(username='pytest csrf victim').first() is None


def test_a_user_can_change_their_own_password(member_client, temp_user):
    from extensions import db
    from models import AppUser
    user_id, _, old_password = temp_user

    member_client.get('/account')
    with member_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    response = member_client.post('/account', data={
        'current_password': old_password,
        'new_password': 'ein noch besseres',
        'csrf_token': csrf,
    })
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert check_password_hash(stored.password_hash, 'ein noch besseres')


def test_changing_a_password_requires_the_current_one(member_client, temp_user):
    from extensions import db
    from models import AppUser
    user_id, _, old_password = temp_user

    member_client.get('/account')
    with member_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    member_client.post('/account', data={
        'current_password': 'falsch',
        'new_password': 'sollte nicht greifen',
        'csrf_token': csrf,
    })
    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert check_password_hash(stored.password_hash, old_password)


def test_a_short_password_is_refused(member_client, temp_user):
    from extensions import db
    from models import AppUser
    user_id, _, old_password = temp_user

    member_client.get('/account')
    with member_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    member_client.post('/account', data={
        'current_password': old_password,
        'new_password': 'kurz',
        'csrf_token': csrf,
    })
    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert check_password_hash(stored.password_hash, old_password)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v -k "admin_can_create or csrf or password"`
Expected: FAIL — 404 on `/admin/users` and `/account`, which do not exist yet.

- [ ] **Step 3: Add the CSRF helpers to auth.py**

Append to `auth.py`, after `admin_required`:

```python
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
```

- [ ] **Step 4: Add the two routes**

Append to `auth.py`:

```python
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
    return render_template('auth/users.html', users=users, error=error)


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
```

- [ ] **Step 5: Guard the login form with the same token**

In `auth.py`'s `login()`, add the check as the first statement inside `if request.method == 'POST':`:

```python
        if not _valid_csrf(request.form.get('csrf_token')):
            abort(400)
```

In `templates/auth/login.html`, replace line 97:

```html
    <form method="POST">
```

with:

```html
    <form method="POST">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

- [ ] **Step 6: Create the two templates**

Create `templates/auth/users.html`:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Benutzer</title>
</head>
<body>
    <h1>Benutzer</h1>
    {% if error %}<p role="alert">{{ error }}</p>{% endif %}
    <ul>
        {% for user in users %}
            <li>{{ user.username }}{% if user.is_admin %} (Admin){% endif %}</li>
        {% endfor %}
    </ul>

    <h2>Neuen Benutzer anlegen</h2>
    <form method="POST">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <label for="username">Benutzername</label>
        <input type="text" id="username" name="username" autocomplete="off" required>
        <label for="password">Passwort</label>
        <input type="password" id="password" name="password" autocomplete="new-password" required>
        <label for="is_admin">
            <input type="checkbox" id="is_admin" name="is_admin" value="1"> Admin
        </label>
        <button type="submit">Anlegen</button>
    </form>
    <p><a href="{{ url_for('index') }}">Zurück</a></p>
</body>
</html>
```

Create `templates/auth/account.html`:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Konto</title>
</head>
<body>
    <h1>Konto</h1>
    <p>Angemeldet als {{ user.username }}.</p>
    {% if error %}<p role="alert">{{ error }}</p>{% endif %}
    {% if done %}<p role="status">Passwort geändert.</p>{% endif %}

    <h2>Passwort ändern</h2>
    <form method="POST">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <label for="current_password">Aktuelles Passwort</label>
        <input type="password" id="current_password" name="current_password"
               autocomplete="current-password" required>
        <label for="new_password">Neues Passwort</label>
        <input type="password" id="new_password" name="new_password"
               autocomplete="new-password" required>
        <button type="submit">Ändern</button>
    </form>
    <p><a href="{{ url_for('index') }}">Zurück</a></p>
</body>
</html>
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS, 17 passed

Run: `python -m pytest tests/ -v`
Expected: PASS. The login tests from Task 2 now need a CSRF token — if they fail with 400, add the token to those three POSTs the same way `test_an_admin_can_create_a_user` does: GET `/login` first, read `csrf_token` from the session, post it.

- [ ] **Step 8: Commit**

```bash
git add auth.py templates/auth/ tests/test_auth.py
git commit -m "feat(auth): add user administration, account page and CSRF on the credential forms"
```

---

## Deployment

Not a task — run by the author once the ten tasks are merged. Steps 2 and 5 have no test coverage by nature.

1. Confirm the full suite passes: `python -m pytest tests/ -v`
2. **Back up the production database.** First migration here that rewrites ownership of every row.
3. Merge `dev_personal` to `main`, deploy, then on the VPS: `flask db upgrade`
4. Restart the web service **and** the notifier daemon. `push.py` changed; a stale daemon keeps the old broadcast behaviour and buzzes the wrong phone.
5. Create the partner's account at `/admin/users`.
6. Copy the two templates, once, from a Flask shell. `SRC` is the author's user id, `DST` the partner's:

```python
for t in WorkoutTemplate.query.filter_by(user_id=SRC).all():
    copy = WorkoutTemplate(name=t.name, user_id=DST)
    db.session.add(copy)
    db.session.flush()          # need copy.id before the children
    for te in t.exercises:
        db.session.add(TemplateExercise(
            template_id=copy.id,
            exercise_id=te.exercise_id,
            position=te.position,
            rest_seconds=te.rest_seconds,
        ))
db.session.commit()
```

7. Verify as the partner: his login works, both templates are present, history is empty, and an exercise detail page shows none of the author's numbers.

Both users are logged out once on deploy — the session cookie changes from `logged_in` to `user_id`. Expected, not a bug.

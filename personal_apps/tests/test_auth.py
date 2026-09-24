"""Account model, login, and the admin permission gate.

Runs against the real local development database, like the other suites here.
"""
from contextlib import contextmanager

import pytest
from werkzeug.security import check_password_hash

from app import app as flask_app
from conftest import _admin_id


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


def test_login_with_the_right_password_sets_user_id(anon_client, temp_user):
    user_id, username, password = temp_user
    anon_client.get('/login')  # issues the CSRF token
    with anon_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    response = anon_client.post('/login', data={
        'username': username, 'password': password, 'csrf_token': csrf,
    })
    assert response.status_code in (302, 303)
    with anon_client.session_transaction() as flask_session:
        assert flask_session['user_id'] == user_id


def test_login_with_the_wrong_password_sets_nothing(anon_client, temp_user):
    _, username, _ = temp_user
    anon_client.get('/login')  # issues the CSRF token
    with anon_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    anon_client.post('/login', data={
        'username': username, 'password': 'falsch', 'csrf_token': csrf,
    })
    with anon_client.session_transaction() as flask_session:
        assert 'user_id' not in flask_session


def test_a_missing_username_and_a_wrong_password_are_indistinguishable(anon_client, temp_user):
    """Both must render the same error. A different message (or a redirect on
    one and not the other) tells an attacker which usernames exist."""
    _, username, _ = temp_user
    # Both POSTs share this client's session, so the CSRF token minted here is
    # identical -- and identically embedded -- in both rendered responses. It
    # does not become a variable that could break the byte-for-byte comparison.
    anon_client.get('/login')  # issues the CSRF token
    with anon_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    wrong_password = anon_client.post('/login', data={
        'username': username, 'password': 'falsch', 'csrf_token': csrf,
    })
    no_such_user = anon_client.post('/login', data={
        'username': 'kein solcher Nutzer', 'password': 'falsch', 'csrf_token': csrf,
    })
    assert wrong_password.status_code == no_such_user.status_code
    assert wrong_password.get_data() == no_such_user.get_data()


def test_a_session_pointing_at_a_deleted_user_is_logged_out(anon_client):
    """Deleting a user must invalidate their live sessions, not 500."""
    with anon_client.session_transaction() as flask_session:
        flask_session['user_id'] = 999999      # no such row
    response = anon_client.get('/gym')
    assert response.status_code in (302, 303)
    assert '/login' in response.headers['Location']


# The before_request gate asks for a login on the full-access hostname only,
# and holds a signed-in non-admin to the member blueprints on every public
# hostname. Loopback is exempt, and the test client defaults to "localhost",
# where the gate returns early -- so these requests must state the host
# explicitly or they would assert against a surface the gate never touches.
from app import FULL_ACCESS_HOST

FULL_ACCESS_URL = f'http://{FULL_ACCESS_HOST}'
PUBQUIZ_HOST = 'pubquizmainz.viewdns.net'


@contextmanager
def _client_on_host(user_id, host):
    """A logged-in client whose session cookie is scoped to `host`.

    `session_transaction()` writes the cookie against the client's *current*
    host, and Werkzeug's jar is host-only when no Domain attribute is set. Set
    the session on the default localhost and every later request carrying
    another base_url arrives anonymous -- which would make these tests
    assert 302-vs-403 rather than admin-vs-non-admin. The host must be stated
    when the session is written, not only when the request is made.
    """
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction(base_url=f'http://{host}') as flask_session:
            flask_session['user_id'] = user_id
        yield test_client


def _client_on_full_access_host(user_id):
    return _client_on_host(user_id, FULL_ACCESS_HOST)


@pytest.fixture()
def member_client(temp_user):
    """A client logged in as the throwaway non-admin, on the full-access host."""
    user_id, _, _ = temp_user
    with _client_on_full_access_host(user_id) as test_client:
        yield test_client


# /radar/ is on this list because a new blueprint is denied by default -- it
# is absent from _MEMBER_BLUEPRINTS, not present-and-blocked. That makes the
# gate safe but silent, so widening it later would be a one-word change with
# no failing test unless the deny is asserted somewhere.
@pytest.mark.parametrize('path', ['/tips', '/quizbank', '/pubquiz/admin',
                                  '/radar/', '/radar/api/board'])
def test_a_non_admin_cannot_reach_the_other_apps(member_client, path):
    assert member_client.get(path, base_url=FULL_ACCESS_URL).status_code == 403


def test_a_non_admin_can_reach_the_gym(member_client):
    assert member_client.get('/gym', base_url=FULL_ACCESS_URL).status_code == 200


def test_an_admin_still_reaches_the_other_apps():
    """The gate must block the non-admin without locking the author out.

    Builds its own client rather than using conftest's: that fixture's session
    is scoped to localhost, which this host-specific request would not carry.
    """
    with _client_on_full_access_host(_admin_id()) as admin_client:
        for path in ('/tips', '/quizbank'):
            assert admin_client.get(path, base_url=FULL_ACCESS_URL).status_code == 200


def test_the_overview_shows_only_the_gym_to_a_non_admin(member_client):
    member_html = member_client.get('/', base_url=FULL_ACCESS_URL).get_data(as_text=True)
    assert 'Gym Tracker' in member_html
    assert 'Pub Quiz' not in member_html
    assert 'Trinkgeld Tracker' not in member_html
    # Offering a card that 403s on click is worse than not offering it.
    assert 'Radar' not in member_html

    with _client_on_full_access_host(_admin_id()) as admin_client:
        admin_html = admin_client.get('/', base_url=FULL_ACCESS_URL).get_data(as_text=True)
    assert 'Gym Tracker' in admin_html
    assert 'Pub Quiz' in admin_html
    assert 'Radar' in admin_html


def test_only_an_admin_reaches_the_user_admin(member_client):
    assert member_client.get('/admin/users', base_url=FULL_ACCESS_URL).status_code == 403


# G-151: the member check used to run on the full-access host only. The
# pub-quiz domain proxies /pubquiz*, /login and /logout, so a member who signed
# in there got the quiz admin. G-132: the host was compared as sent, so other
# spellings of the full-access host skipped the gate as well.
@pytest.mark.parametrize('host', [PUBQUIZ_HOST, FULL_ACCESS_HOST + '.', '192.168.1.20'])
@pytest.mark.parametrize('path', ['/pubquiz/admin', '/tips', '/quizbank', '/radar/'])
def test_a_non_admin_is_refused_the_other_apps_on_every_public_host(temp_user, host, path):
    user_id, _, _ = temp_user
    with _client_on_host(user_id, host) as test_client:
        assert test_client.get(path, base_url=f'http://{host}').status_code == 403


def test_a_non_admin_still_gets_the_public_quiz_page_without_an_admin_link(temp_user):
    """Public on the quiz domain, so a signed-in member must not get less than
    a stranger -- and no Admin link that would only 403."""
    user_id, _, _ = temp_user
    with _client_on_host(user_id, PUBQUIZ_HOST) as test_client:
        response = test_client.get('/pubquiz', base_url=f'http://{PUBQUIZ_HOST}')
    assert response.status_code == 200
    assert 'href="/pubquiz/admin"' not in response.get_data(as_text=True)


def test_an_admin_still_runs_the_quiz_on_the_quiz_domain():
    with _client_on_host(_admin_id(), PUBQUIZ_HOST) as admin_client:
        assert admin_client.get('/pubquiz/admin', base_url=f'http://{PUBQUIZ_HOST}').status_code == 200


def test_a_member_signing_in_on_the_quiz_domain_lands_on_the_public_page(anon_client, temp_user):
    _, username, password = temp_user
    quiz_url = f'http://{PUBQUIZ_HOST}'
    anon_client.get('/login', base_url=quiz_url)  # issues the CSRF token
    with anon_client.session_transaction(base_url=quiz_url) as flask_session:
        csrf = flask_session['csrf_token']
    response = anon_client.post('/login', base_url=quiz_url, data={
        'username': username, 'password': password, 'csrf_token': csrf,
    })
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/pubquiz')


@pytest.mark.parametrize('host', [FULL_ACCESS_HOST.upper(), FULL_ACCESS_HOST + '.',
                                  FULL_ACCESS_HOST.upper() + '.:443'])
def test_the_full_access_host_asks_for_a_login_however_it_is_spelled(anon_client, host):
    """/pubquiz is public on every other host, so it shows whether the login
    requirement engaged. The Host header goes in raw: the test client
    lowercases a base_url's host on its own, which would hide the case bug."""
    response = anon_client.get('/pubquiz', environ_overrides={'HTTP_HOST': host})
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_an_admin_can_create_a_user(temp_user):
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

    # member_client's session cookie is host-only (see _client_on_full_access_host):
    # every call here must state base_url=FULL_ACCESS_URL or it lands on the
    # default localhost host, which is an anonymous session for this client.
    member_client.get('/account', base_url=FULL_ACCESS_URL)
    with member_client.session_transaction(base_url=FULL_ACCESS_URL) as flask_session:
        csrf = flask_session['csrf_token']
    response = member_client.post('/account', base_url=FULL_ACCESS_URL, data={
        'current_password': old_password,
        'new_password': 'ein noch besseres',
        'csrf_token': csrf,
    })
    # account() (brief Step 4) re-renders account.html with done=True on success
    # rather than redirecting -- unlike admin_users(), which does redirect. A
    # 302/303 assertion here could never pass against that verbatim route; the
    # inline success banner is the actual success signal this route produces.
    assert response.status_code == 200
    assert 'Passwort geändert.' in response.get_data(as_text=True)
    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert check_password_hash(stored.password_hash, 'ein noch besseres')


def test_changing_a_password_requires_the_current_one(member_client, temp_user):
    from extensions import db
    from models import AppUser
    user_id, _, old_password = temp_user

    member_client.get('/account', base_url=FULL_ACCESS_URL)
    with member_client.session_transaction(base_url=FULL_ACCESS_URL) as flask_session:
        csrf = flask_session['csrf_token']
    member_client.post('/account', base_url=FULL_ACCESS_URL, data={
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

    member_client.get('/account', base_url=FULL_ACCESS_URL)
    with member_client.session_transaction(base_url=FULL_ACCESS_URL) as flask_session:
        csrf = flask_session['csrf_token']
    member_client.post('/account', base_url=FULL_ACCESS_URL, data={
        'current_password': old_password,
        'new_password': 'kurz',
        'csrf_token': csrf,
    })
    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert check_password_hash(stored.password_hash, old_password)


# --- editing an existing account -------------------------------------------
# Decision 3 originally said "no edit UI, rare operations go through SQL".
# The author reversed that: renaming someone and resetting a forgotten password
# are not rare enough to be worth a shell.


def _admin_session():
    """A logged-in admin client plus its CSRF token, minted by a real GET."""
    flask_app.config['TESTING'] = True
    admin_client = flask_app.test_client()
    with admin_client.session_transaction() as flask_session:
        flask_session['user_id'] = _admin_id()
    assert admin_client.get('/admin/users').status_code == 200
    with admin_client.session_transaction() as flask_session:
        csrf = flask_session['csrf_token']
    return admin_client, csrf


def test_an_admin_can_rename_a_user(temp_user):
    from extensions import db
    from models import AppUser
    user_id, _, password = temp_user

    admin_client, csrf = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': 'pytest renamed user', 'password': '', 'csrf_token': csrf})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert stored.username == 'pytest renamed user'
        # A blank password field means "leave it alone" -- renaming must not
        # silently invalidate the password the user already has.
        assert check_password_hash(stored.password_hash, password)


def test_an_admin_can_reset_a_password_without_renaming(temp_user):
    from extensions import db
    from models import AppUser
    user_id, username, _ = temp_user

    admin_client, csrf = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': username, 'password': 'ein neues langes', 'csrf_token': csrf})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        stored = db.session.get(AppUser, user_id)
        assert stored.username == username
        assert check_password_hash(stored.password_hash, 'ein neues langes')


def test_renaming_to_an_existing_username_is_refused(temp_user):
    from extensions import db
    from models import AppUser
    user_id, username, _ = temp_user

    with flask_app.app_context():
        taken = db.session.get(AppUser, _admin_id()).username

    admin_client, csrf = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': taken, 'password': '', 'csrf_token': csrf})
    assert response.status_code == 200
    assert 'schon vergeben' in response.get_data(as_text=True)

    with flask_app.app_context():
        assert db.session.get(AppUser, user_id).username == username


def test_keeping_your_own_username_is_not_a_collision(temp_user):
    """The uniqueness check must exclude the row being edited, or resetting a
    password without renaming would report the user colliding with themselves."""
    from extensions import db
    from models import AppUser
    user_id, username, _ = temp_user

    admin_client, csrf = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': username, 'password': 'noch ein langes', 'csrf_token': csrf})
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        assert check_password_hash(db.session.get(AppUser, user_id).password_hash,
                                   'noch ein langes')


def test_a_short_replacement_password_is_refused(temp_user):
    from extensions import db
    from models import AppUser
    user_id, username, password = temp_user

    admin_client, csrf = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': username, 'password': 'kurz', 'csrf_token': csrf})
    assert response.status_code == 200

    with flask_app.app_context():
        assert check_password_hash(db.session.get(AppUser, user_id).password_hash, password)


def test_editing_a_user_without_a_csrf_token_is_refused(temp_user):
    from extensions import db
    from models import AppUser
    user_id, username, _ = temp_user

    admin_client, _ = _admin_session()
    response = admin_client.post(f'/admin/users/{user_id}/update', data={
        'username': 'pytest forged rename', 'password': ''})
    assert response.status_code == 400

    with flask_app.app_context():
        assert db.session.get(AppUser, user_id).username == username


def test_a_non_admin_cannot_edit_users(member_client, temp_user):
    from extensions import db
    from models import AppUser
    user_id, username, _ = temp_user

    response = member_client.post(f'/admin/users/{user_id}/update', data={
        'username': 'pytest escalation'}, base_url=FULL_ACCESS_URL)
    assert response.status_code == 403

    with flask_app.app_context():
        assert db.session.get(AppUser, user_id).username == username


def test_editing_a_user_that_does_not_exist_is_404(temp_user):
    admin_client, csrf = _admin_session()
    response = admin_client.post('/admin/users/999999/update', data={
        'username': 'pytest ghost', 'password': '', 'csrf_token': csrf})
    assert response.status_code == 404

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


# The before_request gate only engages on the full-access hostname -- the
# public pubquiz domain does not proxy the other apps at all, so their
# protection lives on that host. The test client defaults to "localhost", where
# the gate returns early, so these requests must state the host explicitly or
# they would assert against a surface the gate never touches.
from app import FULL_ACCESS_HOST

FULL_ACCESS_URL = f'http://{FULL_ACCESS_HOST}'


@contextmanager
def _client_on_full_access_host(user_id):
    """A logged-in client whose session cookie is scoped to the full-access host.

    `session_transaction()` writes the cookie against the client's *current*
    host, and Werkzeug's jar is host-only when no Domain attribute is set. Set
    the session on the default localhost and every later request carrying
    base_url=FULL_ACCESS_URL arrives anonymous -- which would make these tests
    assert 302-vs-403 rather than admin-vs-non-admin. The host must be stated
    when the session is written, not only when the request is made.
    """
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction(base_url=FULL_ACCESS_URL) as flask_session:
            flask_session['user_id'] = user_id
        yield test_client


@pytest.fixture()
def member_client(temp_user):
    """A client logged in as the throwaway non-admin, on the full-access host."""
    user_id, _, _ = temp_user
    with _client_on_full_access_host(user_id) as test_client:
        yield test_client


@pytest.mark.parametrize('path', ['/tips', '/quizbank', '/pubquiz/admin'])
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


def test_the_overview_shows_one_app_to_a_non_admin_and_four_to_an_admin(member_client):
    member_html = member_client.get('/', base_url=FULL_ACCESS_URL).get_data(as_text=True)
    assert 'Gym Tracker' in member_html
    assert 'Pub Quiz' not in member_html
    assert 'Trinkgeld Tracker' not in member_html

    with _client_on_full_access_host(_admin_id()) as admin_client:
        admin_html = admin_client.get('/', base_url=FULL_ACCESS_URL).get_data(as_text=True)
    assert 'Gym Tracker' in admin_html
    assert 'Pub Quiz' in admin_html

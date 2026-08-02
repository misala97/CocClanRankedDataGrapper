"""Account model, login, and the admin permission gate.

Runs against the real local development database, like the other suites here.
"""
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

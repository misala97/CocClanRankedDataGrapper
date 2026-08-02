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

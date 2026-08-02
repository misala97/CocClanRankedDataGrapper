"""Shared fixtures. Every suite here runs against the real local development
database, so the account these clients log in as is the seeded admin."""
from contextlib import contextmanager

import pytest

from app import app as flask_app
from flask import session as flask_session


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

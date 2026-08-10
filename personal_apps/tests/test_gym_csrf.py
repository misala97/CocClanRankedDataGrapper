"""The blueprint-level CSRF gate on gym writes.

Second layer behind SESSION_COOKIE_SAMESITE=Lax. The suite at large runs with
the gate open (TESTING skips it, Flask-WTF's own convention); these tests set
CSRF_STRICT and pin the closed gate explicitly.
"""
import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def template_id():
    from extensions import db
    from models import WorkoutTemplate
    with flask_app.app_context():
        template = WorkoutTemplate(name='ZZ csrf routine', user_id=_admin_id())
        db.session.add(template)
        db.session.commit()
        made = template.id
    yield made
    with flask_app.app_context():
        doomed = db.session.get(WorkoutTemplate, made)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


@pytest.fixture()
def strict_client():
    flask_app.config['TESTING'] = True
    flask_app.config['CSRF_STRICT'] = True
    try:
        with flask_app.test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session['user_id'] = _admin_id()
                flask_session['csrf_token'] = 'pytest-csrf-token'
            yield client
    finally:
        flask_app.config['CSRF_STRICT'] = False


def test_a_write_without_a_token_is_refused(strict_client, template_id):
    response = strict_client.post(f'/gym/templates/{template_id}/rename',
                                  data={'name': 'ZZ forged'})
    assert response.status_code == 403


def test_the_header_opens_the_gate(strict_client, template_id):
    """The islands' path: X-CSRF-Token on every fetch (src/api.ts)."""
    response = strict_client.post(f'/gym/templates/{template_id}/rename',
                                  data={'name': 'ZZ header renamed'},
                                  headers={'X-CSRF-Token': 'pytest-csrf-token'})
    assert response.status_code in (200, 302, 303)


def test_the_form_field_opens_the_gate(strict_client, template_id):
    """The native forms' path: the CsrfField hidden input."""
    response = strict_client.post(f'/gym/templates/{template_id}/rename',
                                  data={'name': 'ZZ field renamed',
                                        'csrf_token': 'pytest-csrf-token'})
    assert response.status_code in (200, 302, 303)


def test_a_wrong_token_is_a_forgery(strict_client, template_id):
    response = strict_client.post(f'/gym/templates/{template_id}/rename',
                                  data={'name': 'ZZ forged',
                                        'csrf_token': 'not-the-token'})
    assert response.status_code == 403


def test_reads_never_need_a_token(strict_client):
    assert strict_client.get('/gym').status_code == 200


def test_the_shell_delivers_the_token(strict_client):
    """What src/csrf.ts reads: the meta tag, carrying the session's token."""
    html = strict_client.get('/gym').get_data(as_text=True)
    assert '<meta name="csrf-token" content="pytest-csrf-token">' in html

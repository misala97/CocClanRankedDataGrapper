"""The watch endpoints: per account, idempotent, and behind the CSRF gate."""
import pytest

from app import app as flask_app
from extensions import db
from models import AppUser, RadarWatch
from conftest import _admin_id


@pytest.fixture()
def clean_marks():
    with flask_app.app_context():
        RadarWatch.query.filter_by(user_id=_admin_id()).delete()
        db.session.commit()
        yield
        RadarWatch.query.filter_by(user_id=_admin_id()).delete()
        db.session.commit()


def test_put_and_delete_return_the_callers_list(client, clean_marks):
    assert client.put('/radar/api/watch/nvda').get_json() == {'watching': ['NVDA']}
    assert client.put('/radar/api/watch/TSLA').get_json() == {'watching': ['NVDA', 'TSLA']}
    assert client.put('/radar/api/watch/NVDA').get_json() == {'watching': ['NVDA', 'TSLA']}
    assert client.delete('/radar/api/watch/NVDA').get_json() == {'watching': ['TSLA']}
    assert client.delete('/radar/api/watch/NVDA').status_code == 200


def test_a_malformed_ticker_is_400(client, clean_marks):
    response = client.put('/radar/api/watch/1abc')
    assert response.status_code == 400
    assert response.get_json() == {'error': 'bad ticker'}


def test_the_marks_need_a_session(anon_client):
    assert anon_client.put('/radar/api/watch/NVDA').status_code in (302, 401, 403)


def test_writes_need_the_csrf_token_when_the_gate_is_closed(client, clean_marks, monkeypatch):
    """Suites run with the gate open (Flask-WTF's convention); this test
    closes it, the way test_gym_csrf.py does for the gym blueprint."""
    monkeypatch.setitem(flask_app.config, 'CSRF_STRICT', True)

    assert client.put('/radar/api/watch/NVDA').status_code == 403

    with client.session_transaction() as flask_session:
        flask_session['csrf_token'] = 'pytest-token'
    ok = client.put('/radar/api/watch/NVDA', headers={'X-CSRF-Token': 'pytest-token'})
    assert ok.status_code == 200
    assert ok.get_json() == {'watching': ['NVDA']}
    # Reads stay open.
    assert client.get('/radar/api/board?market=us').status_code == 200

"""Showoff is shared by authenticated members; private apps stay private."""
from types import SimpleNamespace

import pytest

import auth
from app import app, FULL_ACCESS_HOST


@pytest.mark.parametrize('host', ['localhost', FULL_ACCESS_HOST])
@pytest.mark.parametrize('role', ['anonymous', 'member', 'admin'])
def test_showoff_access_and_hub_visibility(monkeypatch, host, role):
    user = None if role == 'anonymous' else SimpleNamespace(is_admin=role == 'admin')
    monkeypatch.setattr(auth, 'current_user', lambda: user)
    with app.test_client() as client:
        response = client.get('/showoff/', base_url=f'https://{host}')
        hub = client.get('/', base_url=f'https://{host}')
    if role == 'anonymous':
        assert response.status_code == 302
        assert response.location.endswith('/login')
        assert hub.status_code == 302
    else:
        assert response.status_code == 200
        assert b'Interactive three-dimensional particle sculpture' in response.data
        assert hub.status_code == 200
        assert b'href="/showoff/"' in hub.data
        assert b'href="/gym"' in hub.data
        if role == 'member':
            assert b'href="/radar/"' not in hub.data
            assert b'href="/tips"' not in hub.data


def test_showoff_access_does_not_open_private_apps(monkeypatch):
    monkeypatch.setattr(auth, 'current_user', lambda: SimpleNamespace(is_admin=False))
    with app.test_client() as client:
        assert client.get('/radar/', base_url=f'https://{FULL_ACCESS_HOST}').status_code == 403

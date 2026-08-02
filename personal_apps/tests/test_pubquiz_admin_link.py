"""Regression test for the pubquiz nav Admin link.

`auth.py` used to set session['logged_in'] = True on login; it now sets
session['user_id'] instead. The pubquiz template still tested
session.logged_in, so the link silently stopped appearing for logged-in
users. This pins the fix.

Runs against the real local development database, like the other suites
here. `/pubquiz` is public -- the login gate in app.py only applies on
PERSONAL_FULL_ACCESS_HOST, which the test client is not using -- so the
anonymous request renders the page normally, just without the link.
"""
from conftest import _admin_id

ADMIN_LINK = '<a href="/pubquiz/admin" class="admin-link">Admin</a>'


def test_logged_in_session_shows_admin_link(client):
    response = client.get('/pubquiz')
    assert response.status_code == 200
    assert ADMIN_LINK in response.get_data(as_text=True)


def test_anonymous_session_hides_admin_link(anon_client):
    response = anon_client.get('/pubquiz')
    assert response.status_code == 200
    assert ADMIN_LINK not in response.get_data(as_text=True)

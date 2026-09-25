"""Security headers on every response (walkthrough 2026-09-23, G-122).

Nothing set them before. Gym and login pages run only scripts this app
ships -- a file of its own, or an inline script carrying the response's nonce
-- so an injected script runs nowhere there. Every response refuses to be
framed, to be sniffed as another type, and to leak its URL to other sites.

The inline-script test is the one that guards the future: an inline script
added to a gym template without the nonce is blocked in the browser, and
fails here first.
"""
import re

import pytest

from app import app as flask_app

INLINE_SCRIPT_TAG = re.compile(r'<script\b([^>]*)>', re.I)
NONCE = re.compile(r"'nonce-([^']+)'")


def _inline_executable_scripts(html):
    """The attributes of each <script> the browser would run from the page
    itself: not a file (src=) and not a data block (application/json)."""
    return [attrs for attrs in INLINE_SCRIPT_TAG.findall(html)
            if 'src=' not in attrs and 'application/json' not in attrs]


def _assert_every_inline_script_carries_the_nonce(response):
    policy = response.headers['Content-Security-Policy']
    assert "script-src 'self' 'nonce-" in policy
    assert "object-src 'none'" in policy and "base-uri 'self'" in policy
    nonce = NONCE.search(policy).group(1)
    for attrs in _inline_executable_scripts(response.get_data(as_text=True)):
        assert f'nonce="{nonce}"' in attrs, f'an inline script without the nonce: <script{attrs}>'


@pytest.mark.parametrize('path', ['/gym', '/gym/verlauf', '/gym/uebungen'])
def test_every_inline_script_on_a_gym_page_carries_the_nonce(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert _inline_executable_scripts(response.get_data(as_text=True)), \
        'the gym shell has inline scripts -- the pattern found none'
    _assert_every_inline_script_carries_the_nonce(response)


def test_the_live_workout_page_too(client, live_session):
    response = client.get(f"/gym/session/{live_session['session']}")
    assert response.status_code == 200
    _assert_every_inline_script_carries_the_nonce(response)


def test_each_response_gets_a_nonce_of_its_own(client):
    first, second = (NONCE.search(client.get('/gym').headers['Content-Security-Policy']).group(1)
                     for _ in range(2))
    assert first != second


def test_the_login_page_runs_only_what_the_app_ships(anon_client):
    response = anon_client.get('/login')
    assert response.status_code == 200
    _assert_every_inline_script_carries_the_nonce(response)


@pytest.mark.parametrize('path,anonymous', [
    ('/gym/push/token', False),   # JSON
    ('/pubquiz', True),           # another feature's page, inline scripts and all
    ('/sw.js', True),             # a script
])
def test_every_response_refuses_frames_sniffing_and_referrers(client, anon_client, path, anonymous):
    response = (anon_client if anonymous else client).get(path, headers={'Accept': 'application/json'}
                                                          if not anonymous else {})
    assert response.status_code == 200
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']


def test_other_features_keep_their_inline_scripts(anon_client):
    """Only gym and login pages are under the strict script policy: the other
    features still run inline scripts without a nonce."""
    policy = anon_client.get('/pubquiz').headers['Content-Security-Policy']
    assert 'script-src' not in policy

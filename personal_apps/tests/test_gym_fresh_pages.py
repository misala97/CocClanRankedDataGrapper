"""No gym page is shown from a stored copy (walkthrough 2026-09-23, G-141).

Every gym page carries its data in its HTML -- the island payload -- so a
stored copy is the workout as it was: before the delete, the finish, the new
record. no-store keeps the pages out of the HTTP cache and, in Chrome, out of
the back-forward cache; the islands reload a page Safari restores anyway
(static/gym/src/fresh.ts). The prefetch waits for the finger on the link, so
it cannot fetch a page before the change the lifter is about to make on this
one.
"""
import json
import re

import pytest

SPECULATION_RULES = re.compile(r'<script type="speculationrules"[^>]*>(.*?)</script>', re.S)


@pytest.mark.parametrize('path', ['/gym', '/gym/verlauf', '/gym/uebungen', '/gym/statistik'])
def test_no_gym_page_is_stored(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'


def test_nor_the_live_workout(client, live_session):
    response = client.get(f"/gym/session/{live_session['session']}")
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'


def test_the_prefetch_waits_for_the_finger_on_the_link(client):
    html = client.get('/gym').get_data(as_text=True)
    rules = json.loads(SPECULATION_RULES.search(html).group(1))
    assert {rule['eagerness'] for rule in rules['prefetch']} == {'conservative'}

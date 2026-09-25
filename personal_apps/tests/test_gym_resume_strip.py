"""The resume strip and Heute's card name what the live screen has live.

Both say which exercise the running workout is on. The strip had its own
copy of the live rule in Jinja, without the follower's "keep started", so
for a partner it could name another exercise than the screen they had just
left (walkthrough G-143). Both now ask workout._live_exercise_name.
"""
import datetime as dt
import html
import json
import re

from app import app as flask_app
from extensions import db
from features.gym.routes import helpers
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import SharedSession

MINUTE = dt.timedelta(minutes=1)


def _strip(client):
    """The strip's exercise line on Übungen, or None without a strip."""
    page = client.get('/gym/uebungen').get_data(as_text=True)
    found = re.search(r'<span class="resume__meta">([^<]*)</span>', page)
    return html.unescape(found.group(1)) if found else None


def _card(client):
    """Heute's card line: the page's payload says it."""
    page = client.get('/gym').get_data(as_text=True)
    found = re.search(r'"active_session_exercise": ?("(?:[^"\\]|\\.)*"|null)', page)
    return json.loads(found.group(1))


def test_the_strip_names_the_first_exercise_not_done(lifter):
    """Skipped rows and the original a swap hid are passed over, as on the
    screen."""
    with flask_app.app_context():
        done, skipped, swapped, stand_in = (lifter.exercise(n) for n in
                                            ('done', 'skipped', 'swapped', 'stand-in'))
        workout = lifter.workout(20 * MINUTE)
        lifter.row(workout, done, 1, done=[(50, 8)] * 2)
        lifter.row(workout, skipped, 2, open_=3, skipped=True)
        original = lifter.row(workout, swapped, 3, open_=3)
        lifter.row(workout, stand_in, 3, open_=3, replaces=original)
        db.session.commit()
    client = lifter.client()

    assert _strip(client) == 'pytest gym stand-in'
    assert _card(client) == 'pytest gym stand-in'


def test_with_everything_skipped_the_strip_names_nothing(lifter):
    with flask_app.app_context():
        workout = lifter.workout(20 * MINUTE)
        lifter.row(workout, lifter.exercise('skipped'), 1, open_=3, skipped=True)
        db.session.commit()
    client = lifter.client()

    assert _strip(client) == 'Wird fortgesetzt'
    assert _card(client) is None


def test_for_a_partner_the_strip_names_what_they_started(lifter):
    """The leader dragged another exercise to the top: the follower's screen
    keeps the one they started live, and so do the strip and the card."""
    partner_id = lifter.partner()
    with flask_app.app_context():
        moved_up, started = lifter.exercise('moved up'), lifter.exercise('started')
        leading = lifter.workout(30 * MINUTE)
        lifter.row(leading, moved_up, 1, open_=3)
        lifter.row(leading, started, 2, open_=3)
        following = lifter.workout(30 * MINUTE, user_id=partner_id)
        lifter.row(following, moved_up, 1, open_=3)
        lifter.row(following, started, 2, done=[(50, 8)], done_ago=[5 * MINUTE], open_=2)
        db.session.add(SharedSession(
            leader_session_id=leading.id, leader_user_id=lifter.user_id,
            follower_user_id=partner_id, follower_session_id=following.id,
            accepted_at=lifter.now - 25 * MINUTE))
        db.session.commit()
    client = lifter.client(partner_id)

    assert _strip(client) == 'pytest gym started'
    assert _card(client) == 'pytest gym started'
    # The leader's own is the plain rule: the drag was theirs.
    assert _strip(lifter.client()) == 'pytest gym moved up'


def test_a_page_looks_the_running_workout_up_once(lifter, monkeypatch):
    """The before-request settle, Heute's card and the nav's strip each
    looked it up -- a query and a settle apiece. The settle's answer is kept
    for the rest of the GET."""
    with flask_app.app_context():
        workout = lifter.workout(20 * MINUTE)
        lifter.row(workout, lifter.exercise('once'), 1, open_=3)
        db.session.commit()
    client = lifter.client()
    lookups = []
    real = helpers._get_active_session
    monkeypatch.setattr(helpers, '_get_active_session',
                        lambda: lookups.append(1) or real())

    for page in ('/gym', '/gym/uebungen', '/gym/verlauf'):
        lookups.clear()
        assert client.get(page).status_code == 200
        assert len(lookups) == 1, page

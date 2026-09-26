"""B10a (walkthrough 2026-09-23): a discard says so on Start (G-116), a gym
address that leads nowhere gets a gym page (G-081), and an empty Verlauf
knows the running workout (G-003)."""
import datetime as dt

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym.routes import workout as workout_routes
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import WorkoutSession

MIN = dt.timedelta(minutes=1)
HOUR = dt.timedelta(hours=1)
JSON = {'Accept': 'application/json'}


def _flashes(client):
    """What the next page will say, as (category, message) pairs."""
    with client.session_transaction() as flask_session:
        return [tuple(flashed) for flashed in flask_session.get('_flashes', [])]


def _running(lifter, started_ago=MIN):
    with flask_app.app_context():
        workout = lifter.workout(started_ago)
        db.session.commit()
        return workout.id


def _gone(lifter):
    """The id of a workout of the lifter's that no longer exists."""
    with flask_app.app_context():
        workout = lifter.workout(HOUR, finished=True)
        db.session.commit()
        workout_id = workout.id
        db.session.delete(workout)
        db.session.commit()
    return workout_id


# ---- G-116: "Workout verwerfen" says so -----------------------------------

def test_discarding_a_workout_says_so_on_start(lifter):
    workout_id = _running(lifter)
    client = lifter.client()
    response = client.post(f'/gym/session/{workout_id}/discard')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/gym')
    assert _flashes(client) == [('success', 'Workout verworfen.')]
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id) is None


def test_a_discard_that_finds_it_gone_already_says_so_too(lifter):
    # The second of a double submit, or the tab behind: gone either way.
    workout_id = _running(lifter)
    client = lifter.client()
    client.post(f'/gym/session/{workout_id}/discard')
    client.get('/gym')                     # Start said it
    assert _flashes(client) == []
    response = client.post(f'/gym/session/{workout_id}/discard')
    assert response.headers['Location'].endswith('/gym')
    assert _flashes(client) == [('success', 'Workout verworfen.')]


ABANDONED = 'Das leere Workout wurde nach 3 Stunden ohne Satz verworfen.'


def test_a_discard_that_loses_the_race_says_so_too(lifter, monkeypatch):
    # The second of a double submit waits at the lock while the first throws
    # the workout away: it finds nothing there, and says what happened.
    workout_id = _running(lifter)
    lock = workout_routes.lock_sessions
    calls = []

    def the_first_one_won(ids):
        calls.append(list(ids))
        lock(ids)
        db.session.delete(db.session.get(WorkoutSession, workout_id))
        db.session.flush()

    monkeypatch.setattr(workout_routes, 'lock_sessions', the_first_one_won)
    client = lifter.client()
    response = client.post(f'/gym/session/{workout_id}/discard')
    # The race was run: a plain discard ends the same way.
    assert calls == [[workout_id]]
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/gym')
    assert _flashes(client) == [('success', 'Workout verworfen.')]


def test_discarding_a_workout_nobody_came_back_to_says_it_once(lifter):
    # Settled on the way in -- nothing in it counts, so it goes -- and the
    # settle already says so, and why: not a second message beside it.
    workout_id = _running(lifter, started_ago=4 * HOUR)
    client = lifter.client()
    response = client.post(f'/gym/session/{workout_id}/discard')
    assert response.headers['Location'].endswith('/gym')
    assert _flashes(client) == [('error', ABANDONED)]


def test_a_workout_settled_by_a_page_says_why_not_verworfen(lifter):
    # Nobody tapped anything: a page read found it abandoned and threw it
    # away through _discard_session, which says nothing of its own.
    workout_id = _running(lifter, started_ago=4 * HOUR)
    client = lifter.client()
    response = client.get('/gym/verlauf')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ABANDONED in html
    assert 'Workout verworfen.' not in html
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, workout_id) is None


# ---- G-081: a gym page for a gym address that leads nowhere ----------------

def _way_on(html, href, label):
    """The page's one way on -- not any link to it: the nav has those too."""
    return f'class="btn btn--live void__go" href="{href}">{label}</a>' in html


def test_a_deleted_workout_gets_a_gym_page_with_the_way_on(lifter):
    # The back button, an old tab: it was Werkzeug's English "Not Found".
    workout_id = _gone(lifter)
    response = lifter.client().get(f'/gym/session/{workout_id}')
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'Dieses Workout gibt es nicht mehr.' in html
    assert _way_on(html, '/gym/verlauf', 'Zum Verlauf')
    assert 'The requested URL was not found' not in html


def test_a_deleted_workout_keeps_the_running_one_in_the_nav(lifter):
    # Its address is the session page's own, where the nav leaves the strip
    # out -- and the workout running was then nowhere on the page.
    gone_id = _gone(lifter)
    running_id = _running(lifter)
    html = lifter.client().get(f'/gym/session/{gone_id}').get_data(as_text=True)
    assert f'<a href="/gym/session/{running_id}" class="resume">' in html
    assert 'has-resume' in html


def test_a_workout_thrown_away_on_the_other_phone_sends_its_last_tap_to_start(lifter):
    # Discarded on phone B; phone A still showed it, and this browser's own
    # record of discards knows nothing of B's. Verlauf would never show it.
    workout_id = _gone(lifter)
    for action in ('discard', 'finish'):
        response = lifter.client().post(f'/gym/session/{workout_id}/{action}')
        assert response.status_code == 404
        assert _way_on(response.get_data(as_text=True), '/gym', 'Zum Start')


def test_an_invite_that_no_longer_holds_says_so(lifter):
    # Accepted, then Back from the workout it joined: its confirm page is a
    # 404 like one never sent -- "vorbei oder abgesagt" was not the reason.
    response = lifter.client().get('/gym/shared/2147483000/confirm')
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'Diese Einladung gilt nicht mehr.' in html
    assert 'Angenommen, abgelehnt oder das Workout ist vorbei.' in html
    assert _way_on(html, '/gym', 'Zum Start')


def test_an_island_read_of_it_gets_json(lifter):
    workout_id = _gone(lifter)
    response = lifter.client().get(f'/gym/session/{workout_id}/sync.json', headers=JSON)
    assert response.status_code == 404
    assert response.get_json() == {'error': 'Gibt es nicht (mehr).'}


def test_an_unknown_exercise_says_so(lifter):
    response = lifter.client().get('/gym/exercises/2147483000')
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'Diese Übung gibt es nicht.' in html
    assert _way_on(html, '/gym/uebungen', 'Zu den Übungen')


def test_a_gym_address_no_route_matches_gets_the_gym_page(lifter):
    # Never reaches the blueprint's own handlers: the handler is app-wide.
    workout_id = _running(lifter)
    response = lifter.client().get('/gym/nirgendwo')
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'Diese Seite gibt es nicht.' in html
    assert _way_on(html, '/gym', 'Zum Start')
    # The nav still offers the running workout, as on every gym page.
    assert f'<a href="/gym/session/{workout_id}" class="resume">' in html
    # What a gym page has from its blueprint, which this request has none of:
    # kept out of every cache (it carries the running workout), and scripts
    # held to the app's own and the nonce.
    assert response.headers['Cache-Control'] == 'no-store'
    assert "script-src 'self' 'nonce-" in response.headers['Content-Security-Policy']


def test_an_address_outside_the_gym_keeps_flasks_answer(lifter):
    response = lifter.client().get('/nirgendwo-sonst')
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert 'class="void"' not in html
    assert 'Not Found' in html
    assert response.headers['Content-Security-Policy'] == "frame-ancestors 'none'"


# ---- M6 carry: "Zu „…“ hinzufügen" into a workout gone elsewhere ------------

def test_adding_from_an_exercise_page_into_a_workout_gone_goes_back_to_it(lifter):
    # Discarded or deleted on the other phone after the page was read: back
    # to the exercise's page, told why, where it was a bare 404.
    with flask_app.app_context():
        exercise_id = lifter.exercise('pytest gym B10a Übung').id
        db.session.commit()
    workout_id = _gone(lifter)
    url = f'/gym/session/{workout_id}/exercises/add'

    client = lifter.client()
    response = client.post(url, data={'exercise_id': exercise_id, 'back': 'exercise'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/exercises/{exercise_id}')
    assert _flashes(client) == [('error', 'Das Workout gibt es nicht mehr — nichts hinzugefügt.')]
    # Anyone else asking gets the 404, unflashed.
    plain = lifter.client()
    assert plain.post(url, data={'exercise_id': exercise_id}).status_code == 404
    assert _flashes(plain) == []
    response = lifter.client().post(url, data={'exercise_id': exercise_id, 'back': 'exercise'},
                                    headers=JSON)
    assert response.status_code == 404


# ---- G-003: an empty Verlauf knows the running workout ---------------------

def test_verlauf_names_the_running_workout_for_its_empty_state(lifter):
    def payload():
        response = lifter.client().get('/gym/verlauf')
        assert response.status_code == 200
        return embedded_payload(response.get_data(as_text=True))

    assert payload()['running_session_id'] is None
    workout_id = _running(lifter)
    assert payload()['running_session_id'] == workout_id

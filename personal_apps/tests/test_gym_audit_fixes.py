"""Server halves of the 2026-09-23 workflow audit.

Every case here was first seen by driving the real UI: a stale live screen
writing into a finished workout and queueing a push for it, a skipped last
exercise coming back as "Jetzt", a 0 kg x 0 set from an empty add row, a
Statistik sentence that ignored the break still running, a debrief that could
not correct what the live screen got wrong.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id, embedded_payload


JSON = {'Accept': 'application/json'}
LIVE = {'Accept': 'application/json', 'X-Gym-Surface': 'live'}


def _finish(session_id):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        row = db.session.get(WorkoutSession, session_id)
        row.finished_at = dt.datetime.utcnow()
        db.session.commit()


def _set(set_id):
    from extensions import db
    from models import SessionSet
    with flask_app.app_context():
        row = db.session.get(SessionSet, set_id)
        return None if row is None else (row.weight, row.reps, row.completed, row.completed_at)


def _pending_pushes(session_id):
    from models import PendingPush
    with flask_app.app_context():
        return PendingPush.query.filter_by(session_id=session_id, sent=False).count()


# --- B3: a live screen left open after finishing ----------------------------

def test_a_live_write_to_a_finished_workout_is_refused(client, live_session):
    """The back button or a second phone still shows the live screen. Its
    "Satz geschafft" used to land in the finished workout, queue a rest push
    for a workout that was over, and blank the page."""
    _finish(live_session['session'])
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1', 'weight': '60', 'reps': '8'}, headers=LIVE)
    assert response.status_code == 409
    assert response.get_json() == {'finished': True}
    assert _set(live_session['open_set'])[2] is False
    assert _pending_pushes(live_session['session']) == 0


def test_every_live_route_refuses_a_finished_workout(client, live_session):
    ids = live_session
    _finish(ids['session'])
    cases = [
        (f"/gym/session/{ids['session']}/exercises/add", {'exercise_id': str(ids['exercise'])}),
        (f"/gym/session-exercise/{ids['se']}/rest", {'rest_seconds': '90'}),
        (f"/gym/sessions/{ids['session']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercises/{ids['se']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercise/{ids['se']}/sets/add", {'weight': '60', 'reps': '8'}),
        (f"/gym/set/{ids['done_set']}/update", {'weight': '61', 'reps': '8'}),
        (f"/gym/set/{ids['done_set']}/delete", {}),
        (f"/gym/session-exercise/{ids['se']}/skip", {}),
        (f"/gym/session-exercise/{ids['se']}/replace", {'exercise_id': str(ids['exercise'])}),
        (f"/gym/session/{ids['session']}/exercises/reorder", {'order': str(ids['se'])}),
        (f"/gym/session/{ids['session']}/rest/skip", {}),
        (f"/gym/session/{ids['session']}/deload", {'on': '1', 'pct': '60'}),
        (f"/gym/session-exercise/{ids['se']}/delete", {}),
    ]
    for url, data in cases:
        response = client.post(url, data=data, headers=LIVE)
        assert response.status_code == 409, url


def test_the_debrief_can_still_correct_a_finished_workout(client, live_session):
    """The refusal is keyed on the live surface, not on finished_at alone:
    the debrief's correction sheet writes to finished workouts by design."""
    _finish(live_session['session'])
    response = client.post(f"/gym/set/{live_session['done_set']}/update",
                           data={'weight': '62.5', 'reps': '8'}, headers=JSON)
    assert response.status_code == 200
    assert _set(live_session['done_set'])[:2] == (62.5, 8)


def test_a_set_added_after_finishing_starts_no_rest(client, live_session):
    """A set typed into the debrief was lifted some time ago. It must not
    start a countdown, and its stamp would measure a rest nobody took."""
    _finish(live_session['session'])
    body = client.post(f"/gym/session-exercise/{live_session['se']}/sets/add",
                       data={'weight': '60', 'reps': '6'}, headers=JSON).get_json()
    assert body['total_sets'] == 2
    assert _pending_pushes(live_session['session']) == 0
    from extensions import db
    from models import SessionSet, WorkoutSession
    with flask_app.app_context():
        added = (SessionSet.query.filter_by(session_exercise_id=live_session['se'])
                 .order_by(SessionSet.id.desc()).first())
        assert added.completed is True
        assert added.completed_at is None
        assert db.session.get(WorkoutSession, live_session['session']).rest_ends_at is None


def test_finishing_twice_keeps_the_first_stamp(client, live_session):
    """A stale screen's second "Beenden" hours later used to re-stamp the
    workout and stretch it to however long the phone sat in a pocket."""
    from extensions import db
    from models import WorkoutSession
    first = dt.datetime.utcnow().replace(microsecond=0) - dt.timedelta(hours=3)
    with flask_app.app_context():
        db.session.get(WorkoutSession, live_session['session']).finished_at = first
        db.session.commit()
    response = client.post(f"/gym/session/{live_session['session']}/finish")
    assert response.status_code in (302, 303)
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, live_session['session']).finished_at == first


# --- B4: a skipped last exercise is not "Jetzt" ------------------------------

def test_a_skipped_last_exercise_is_never_live(client, live_session):
    from extensions import db
    from models import SessionExercise
    with flask_app.app_context():
        db.session.add(SessionExercise(session_id=live_session['session'],
                                       exercise_id=live_session['exercise'],
                                       position=2, skipped=True))
        db.session.commit()
    body = client.post(f"/gym/set/{live_session['open_set']}/toggle_complete",
                       data={'completed': '1'}, headers=LIVE).get_json()
    assert body['live_id'] == live_session['se']


def test_everything_skipped_leaves_nothing_live(client, live_session):
    client.post(f"/gym/session-exercise/{live_session['se']}/skip", headers=LIVE)
    body = client.get(f"/gym/session/{live_session['session']}/detail.json").get_json()
    assert body['live_id'] is None
    assert len(body['visible_exercises']) == 1


# --- B5: nothing invented from an empty or impossible field ------------------

def test_an_empty_or_impossible_add_creates_no_set(client, live_session):
    for data in ({'weight': '', 'reps': ''}, {'weight': '0', 'reps': '0'},
                 {'weight': '-5', 'reps': '8'}, {'weight': 'nan', 'reps': '8'},
                 {'weight': 'inf', 'reps': '8'}):
        body = client.post(f"/gym/session-exercise/{live_session['se']}/sets/add",
                           data=data, headers=LIVE).get_json()
        exercise = next(se for se in body['visible_exercises'] if se['id'] == live_session['se'])
        assert len(exercise['sets']) == 2, data


def test_a_bodyweight_set_at_zero_kg_is_still_allowed(client, live_session):
    body = client.post(f"/gym/session-exercise/{live_session['se']}/sets/add",
                       data={'weight': '0', 'reps': '10'}, headers=LIVE).get_json()
    exercise = next(se for se in body['visible_exercises'] if se['id'] == live_session['se'])
    assert [s['reps'] for s in exercise['sets']][-1] == 10


def test_an_impossible_edit_keeps_the_stored_numbers(client, live_session):
    client.post(f"/gym/set/{live_session['done_set']}/update",
                data={'weight': '', 'reps': '0'}, headers=LIVE)
    assert _set(live_session['done_set'])[:2] == (60.0, 8)


# --- B7: the longest break includes the one still running --------------------

def test_the_longest_break_counts_the_gap_to_today():
    from features.gym.routes.reports import _longest_break_days
    now = dt.datetime(2026, 9, 23, 12)
    dates = [dt.datetime(2026, 8, 20), dt.datetime(2026, 8, 24), dt.datetime(2026, 9, 1)]
    assert _longest_break_days(dates, now) == 22
    assert _longest_break_days(dates, dt.datetime(2026, 9, 2)) == 8
    assert _longest_break_days([], now) == 0


# --- B8: the debrief lists what was never logged -----------------------------

def test_the_debrief_offers_exercises_with_nothing_logged(client, live_session):
    from extensions import db
    from models import SessionExercise
    with flask_app.app_context():
        extra = SessionExercise(session_id=live_session['session'],
                                exercise_id=live_session['exercise'], position=2)
        db.session.add(extra)
        db.session.commit()
        extra_id = extra.id
    _finish(live_session['session'])
    html = client.get(f"/gym/session/{live_session['session']}").get_data(as_text=True)
    unlogged = embedded_payload(html)['unlogged']
    assert [row['session_exercise_id'] for row in unlogged] == [extra_id]


# --- U3: a workout started by mistake can be thrown away ---------------------

def test_a_workout_without_a_logged_set_can_be_discarded(client, live_session):
    from extensions import db
    from models import SessionSet, WorkoutSession
    with flask_app.app_context():
        db.session.get(SessionSet, live_session['done_set']).completed = False
        db.session.commit()
    response = client.post(f"/gym/session/{live_session['session']}/discard")
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/gym')
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, live_session['session']) is None


def test_a_workout_with_a_logged_set_is_not_discarded(client, live_session):
    from extensions import db
    from models import WorkoutSession
    client.post(f"/gym/session/{live_session['session']}/discard")
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, live_session['session']) is not None


# --- U6: pace per set rather than a "Pause" that includes the sets -----------

def test_the_debrief_reports_pace_per_set(client, live_session):
    from extensions import db
    from models import SessionSet
    start = dt.datetime.utcnow() - dt.timedelta(minutes=30)
    with flask_app.app_context():
        done = db.session.get(SessionSet, live_session['done_set'])
        done.completed_at = start
        other = db.session.get(SessionSet, live_session['open_set'])
        other.completed, other.completed_at = True, start + dt.timedelta(minutes=3)
        db.session.commit()
    _finish(live_session['session'])
    html = client.get(f"/gym/session/{live_session['session']}").get_data(as_text=True)
    payload = embedded_payload(html)
    assert payload['set_pace_seconds'] == 180
    assert 'rest_taken_seconds' not in payload


# --- V1: the first-run checklist on Start -------------------------------------

@pytest.fixture()
def newcomer():
    """A brand-new account and a client logged in as it. Yields
    (client, user_id); workouts are added with _train()."""
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash

    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        user = AppUser(username='pytest newcomer',
                       password_hash=generate_password_hash('x'), is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id
        yield test_client, user_id

    from models import Exercise, ExerciseSettings, WorkoutSession, WorkoutTemplate
    with flask_app.app_context():
        for model in (WorkoutSession, WorkoutTemplate, ExerciseSettings):
            for row in model.query.filter_by(user_id=user_id).all():
                db.session.delete(row)
            db.session.commit()
        Exercise.query.filter_by(name=NEWCOMER_LIFT).delete()
        db.session.delete(db.session.get(AppUser, user_id))
        db.session.commit()


NEWCOMER_LIFT = 'pytest newcomer squat'


def _train(user_id, logged=True, minutes=42):
    """One finished workout for `user_id`, with a completed set unless
    `logged` is False. Returns the session id."""
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    now = dt.datetime.utcnow()
    with flask_app.app_context():
        exercise = Exercise.query.filter_by(name=NEWCOMER_LIFT).first()
        if exercise is None:
            exercise = Exercise(name=NEWCOMER_LIFT)
            db.session.add(exercise)
            db.session.flush()
        session_ = WorkoutSession(user_id=user_id, name='Beine',
                                  started_at=now - dt.timedelta(minutes=minutes), finished_at=now)
        se = SessionExercise(exercise_id=exercise.id, position=1)
        se.sets = [SessionSet(position=1, weight=40.0, reps=10, completed=logged,
                              completed_at=now if logged else None)]
        session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        return session_.id


def _start_payload(test_client):
    return embedded_payload(test_client.get('/gym').get_data(as_text=True))


def test_an_empty_account_gets_the_checklist(newcomer):
    test_client, _ = newcomer
    assert _start_payload(test_client)['onboarding'] == {'workouts': 0, 'last': None}


def test_a_finished_workout_is_step_one_done(newcomer):
    test_client, user_id = newcomer
    session_id = _train(user_id)
    onboarding = _start_payload(test_client)['onboarding']
    assert onboarding['workouts'] == 1
    assert onboarding['last']['session_id'] == session_id
    assert onboarding['last']['name'] == 'Beine'
    assert onboarding['last']['exercises'] == 1


def test_a_workout_that_logged_nothing_does_not_count(newcomer):
    """Same rule as "Zuletzt vor N Tagen": a finished session where nothing
    was ticked off is not a workout the page can build on."""
    test_client, user_id = newcomer
    _train(user_id, logged=False)
    assert _start_payload(test_client)['onboarding'] == {'workouts': 0, 'last': None}


def test_saving_from_the_checklist_lands_back_on_start(newcomer):
    test_client, user_id = newcomer
    session_id = _train(user_id)
    response = test_client.post(f'/gym/session/{session_id}/save_as_template',
                                data={'template_name': 'Beine', 'next': 'start'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/gym')
    payload = _start_payload(test_client)
    assert payload['onboarding'] is None
    assert [r['name'] for r in payload['routines']] == ['Beine']


def test_the_next_token_is_not_a_url(newcomer):
    test_client, user_id = newcomer
    session_id = _train(user_id)
    response = test_client.post(f'/gym/session/{session_id}/save_as_template',
                                data={'template_name': 'Beine', 'next': 'https://example.com'})
    assert response.headers['Location'].endswith(f'/gym/session/{session_id}')


def test_freeform_becomes_the_habit_after_three_workouts(newcomer):
    test_client, user_id = newcomer
    for _ in range(3):
        _train(user_id)
    assert _start_payload(test_client)['onboarding'] is None


def test_an_account_with_routines_gets_no_checklist(client):
    assert _start_payload(client)['onboarding'] is None


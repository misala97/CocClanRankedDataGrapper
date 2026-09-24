"""What the server refuses, and how the refusal reaches the lifter.

Walkthrough 2026-09-23, batch B1:
- G-070: impossible set numbers were dropped with a 200 (the screen snapped
  back without a word) and absurd ones were stored -- 1e9 kg became a record.
- G-071: an invalid bodyweight erased the stored one; 'inf' in a setting
  reached the database.
- G-083: a name longer than its column, or a note longer than TEXT, was a 500
  the island called "Verbindung fehlgeschlagen".
- G-092: two of the three rest routes stored any number, negative included.
- G-093: a lapsed login answered an island's fetch with the login page.

A refusal is a 400 carrying {'error': <German sentence>} for an island, and a
flash plus a redirect back for a native form post.
"""
import pytest

from app import app as flask_app
from auth import FULL_ACCESS_HOST
from conftest import _admin_id

JSON = {'Accept': 'application/json'}


def _set_row(set_id):
    from extensions import db
    from models import SessionSet
    with flask_app.app_context():
        row = db.session.get(SessionSet, set_id)
        return row.weight, row.reps, row.completed


def _session_meta(session_id):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        row = db.session.get(WorkoutSession, session_id)
        return row.bodyweight_kg, row.notes


# ---- G-070: set numbers ---------------------------------------------------

IMPOSSIBLE_SET_FIELDS = [
    {'weight': '1e9'}, {'weight': '9999'}, {'weight': '-10'}, {'weight': 'nan'},
    {'weight': 'inf'}, {'weight': 'abc'},
    {'reps': '0'}, {'reps': '2.5'}, {'reps': '1000000'}, {'reps': str(2 ** 31)},
]


@pytest.mark.parametrize('fields', IMPOSSIBLE_SET_FIELDS)
def test_an_impossible_set_number_is_refused_with_the_reason(client, live_session, fields):
    set_id = live_session['open_set']
    response = client.post(f'/gym/set/{set_id}/update', data=fields, headers=JSON)
    assert response.status_code == 400
    message = response.get_json()['error']
    assert ('Gewicht' if 'weight' in fields else 'Wiederholungen') in message
    assert _set_row(set_id) == (60.0, 8, False)


def test_confirming_a_set_with_an_impossible_weight_leaves_it_open(client, live_session):
    set_id = live_session['open_set']
    response = client.post(f'/gym/set/{set_id}/toggle_complete',
                           data={'completed': '1', 'weight': '9999', 'reps': '8'}, headers=JSON)
    assert response.status_code == 400
    assert _set_row(set_id) == (60.0, 8, False)


def test_an_impossible_set_is_not_appended(client, live_session):
    from models import SessionSet
    se_id = live_session['se']
    response = client.post(f'/gym/session-exercise/{se_id}/sets/add',
                           data={'weight': '9999', 'reps': '999'}, headers=JSON)
    assert response.status_code == 400
    with flask_app.app_context():
        assert SessionSet.query.filter_by(session_exercise_id=se_id).count() == 2


def test_a_blank_field_is_still_not_an_edit(client, live_session):
    set_id = live_session['open_set']
    response = client.post(f'/gym/set/{set_id}/update', data={'weight': '', 'reps': '10'},
                           headers=JSON)
    assert response.status_code == 200
    assert _set_row(set_id) == (60.0, 10, False)


@pytest.mark.parametrize('weight,reps,stored', [
    ('1000', '1000', (1000.0, 1000)), ('0', '1', (0.0, 1)), ('62,5', '8', (62.5, 8)),
])
def test_the_bounds_themselves_are_numbers_a_set_can_carry(client, live_session, weight, reps, stored):
    set_id = live_session['open_set']
    response = client.post(f'/gym/set/{set_id}/update', data={'weight': weight, 'reps': reps},
                           headers=JSON)
    assert response.status_code == 200
    assert _set_row(set_id)[:2] == stored


# ---- G-071: bodyweight, and bodyweight and note apart ----------------------

@pytest.mark.parametrize('raw', ['-5', '99999', 'inf', 'abc', '19.9', '400.5'])
def test_an_impossible_bodyweight_is_refused_and_the_stored_one_kept(client, live_session, raw):
    session_id = live_session['session']
    meta = f'/gym/sessions/{session_id}/meta'
    assert client.post(meta, data={'bodyweight_kg': '80', 'notes': 'gut'},
                       headers=JSON).status_code == 200
    response = client.post(meta, data={'bodyweight_kg': raw, 'notes': 'neu'}, headers=JSON)
    assert response.status_code == 400
    assert 'Körpergewicht' in response.get_json()['error']
    assert _session_meta(session_id) == (80.0, 'gut'), 'nothing of a refused save is kept'


def test_bodyweight_and_note_each_save_on_their_own(client, live_session):
    session_id = live_session['session']
    meta = f'/gym/sessions/{session_id}/meta'
    assert client.post(meta, data={'bodyweight_kg': '81,5'}, headers=JSON).status_code == 200
    assert client.post(meta, data={'notes': 'Schulter ok'}, headers=JSON).status_code == 200
    assert _session_meta(session_id) == (81.5, 'Schulter ok')
    assert client.post(meta, data={'bodyweight_kg': ''}, headers=JSON).status_code == 200
    assert _session_meta(session_id) == (None, 'Schulter ok'), 'a blank clears only its own field'


# ---- G-083: names and notes past their columns -----------------------------

@pytest.fixture()
def scratch_routine():
    from extensions import db
    from models import WorkoutTemplate
    with flask_app.app_context():
        template = WorkoutTemplate(name='pytest scratch routine', user_id=_admin_id())
        db.session.add(template)
        db.session.commit()
        template_id = template.id
    yield template_id
    with flask_app.app_context():
        row = db.session.get(WorkoutTemplate, template_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def test_a_routine_name_past_the_column_is_refused_with_the_reason(client, scratch_routine):
    from extensions import db
    from models import WorkoutTemplate
    url = f'/gym/templates/{scratch_routine}/rename'
    response = client.post(url, data={'name': 'R' * 151}, headers=JSON)
    assert response.status_code == 400
    assert 'Name zu lang' in response.get_json()['error']
    assert client.post(url, data={'name': 'R' * 150}, headers=JSON).status_code == 200
    with flask_app.app_context():
        assert db.session.get(WorkoutTemplate, scratch_routine).name == 'R' * 150


def test_a_routine_saved_under_a_name_past_the_column_goes_back_with_the_reason(
        client, temp_finished_session):
    from models import WorkoutTemplate
    session_id = temp_finished_session[0]
    page = f'/gym/session/{session_id}'
    response = client.post(f'{page}/save_as_template', data={'template_name': 'R' * 151},
                           headers={'Referer': f'http://localhost{page}'})
    assert response.status_code == 302
    assert response.headers['Location'] == page
    with client.session_transaction() as flask_session:
        assert any('Name zu lang' in message for _, message in flask_session['_flashes'])
    with flask_app.app_context():
        assert WorkoutTemplate.query.filter_by(user_id=_admin_id(), name='R' * 150).count() == 0


def test_a_refused_form_post_never_follows_a_foreign_referer(client, temp_finished_session):
    session_id = temp_finished_session[0]
    response = client.post(f'/gym/session/{session_id}/save_as_template',
                           data={'template_name': 'R' * 151},
                           headers={'Referer': 'https://evil.example/gym/x'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/gym'


def test_a_workout_started_under_a_name_past_the_column_is_refused(client):
    from models import WorkoutSession
    with flask_app.app_context():
        if WorkoutSession.query.filter_by(user_id=_admin_id(), finished_at=None).count():
            pytest.skip('the admin has a running workout on this database')
        before = WorkoutSession.query.filter_by(user_id=_admin_id()).count()
    response = client.post('/gym/start', data={'name': 'W' * 151},
                           headers={'Referer': 'http://localhost/gym'})
    assert response.status_code == 302
    assert response.headers['Location'] == '/gym'
    with flask_app.app_context():
        assert WorkoutSession.query.filter_by(user_id=_admin_id()).count() == before


def test_a_note_past_the_limit_is_refused_and_one_at_it_is_kept(client, live_session):
    session_url = f"/gym/sessions/{live_session['session']}/meta"
    exercise_url = f"/gym/session-exercises/{live_session['se']}/meta"
    for url in (session_url, exercise_url):
        response = client.post(url, data={'notes': 'n' * 2001}, headers=JSON)
        assert response.status_code == 400, url
        assert 'Notiz zu lang' in response.get_json()['error']
        assert client.post(url, data={'notes': 'n' * 2000}, headers=JSON).status_code == 200


# ---- G-092: one rest range for every rest route ----------------------------

@pytest.fixture()
def scratch_exercise():
    from extensions import db
    from models import Exercise
    with flask_app.app_context():
        exercise = Exercise(name='pytest scratch input bounds', muscle_group='Brust')
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id
    yield exercise_id
    with flask_app.app_context():
        row = db.session.get(Exercise, exercise_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.parametrize('raw', ['-5', '0', '14', '601', '999999', 'abc', str(2 ** 31)])
def test_every_rest_route_refuses_a_rest_outside_the_stepper(
        client, live_session, scratch_exercise, raw):
    for url, field in ((f'/gym/exercises/{scratch_exercise}/update', 'default_rest_seconds'),
                       (f"/gym/session-exercise/{live_session['se']}/rest", 'rest_seconds'),
                       ('/gym/rest', 'rest_seconds')):
        response = client.post(url, data={field: raw}, headers=JSON)
        assert response.status_code == 400, url
        assert 'Pause' in response.get_json()['error'], url


def test_a_rest_inside_the_stepper_is_kept_for_this_workout(client, live_session):
    from extensions import db
    from models import SessionExercise
    response = client.post(f"/gym/session-exercise/{live_session['se']}/rest",
                           data={'rest_seconds': '95'}, headers=JSON)
    assert response.status_code == 200
    with flask_app.app_context():
        assert db.session.get(SessionExercise, live_session['se']).rest_seconds == 95


# ---- G-071 (code map): the settings parsers --------------------------------

@pytest.mark.parametrize('field,raw', [
    ('weight_increment', 'inf'), ('weight_increment', '0'), ('weight_increment', '-9'),
    ('weight_increment', 'abc'), ('weight_increment', '51'),
    ('bar_weight', 'inf'), ('bar_weight', '-1'), ('bar_weight', '101'),
])
def test_an_impossible_setting_is_refused_with_the_reason(client, scratch_exercise, field, raw):
    response = client.post(f'/gym/exercises/{scratch_exercise}/update', data={field: raw},
                           headers=JSON)
    assert response.status_code == 400
    assert response.get_json()['error']


def test_a_stack_drops_stops_that_are_not_weights_and_refuses_a_hundred_and_one():
    from features.gym.routes import _to_stack_steps
    from features.gym.routes.helpers import InvalidInput
    assert _to_stack_steps('5, inf, 13, 1e9') == [5.0, 13.0]
    assert len(_to_stack_steps(', '.join(str(n) for n in range(1, 101)))) == 100
    with pytest.raises(InvalidInput):
        _to_stack_steps(', '.join(str(n) for n in range(1, 102)))


# ---- G-093: a lapsed login, asked by an island -----------------------------

ISLAND_READS = ['/gym/session/1/detail.json', '/gym/session/1/sync.json',
                '/gym/exercises/1/settings.json']


@pytest.mark.parametrize('path', ISLAND_READS)
def test_a_lapsed_login_answers_an_island_with_a_401_it_can_read(anon_client, path):
    response = anon_client.get(path, headers=JSON)
    assert response.status_code == 401
    assert response.get_json() == {'error': 'login_required'}


def test_a_lapsed_login_answers_an_island_write_with_the_401_too(anon_client):
    response = anon_client.post('/gym/set/1/update', data={'weight': '60'}, headers=JSON)
    assert response.status_code == 401


def test_a_page_load_without_a_login_still_goes_to_the_login_page(anon_client):
    response = anon_client.get('/gym/session/1/detail.json', headers={'Accept': 'text/html'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')


def test_the_admin_pages_answer_an_island_with_the_401_too(anon_client):
    assert anon_client.get('/admin/users', headers=JSON).status_code == 401
    assert anon_client.get('/admin/users').status_code == 302


def test_the_full_access_host_gate_answers_an_island_with_a_401(anon_client):
    host = {'HTTP_HOST': FULL_ACCESS_HOST}
    response = anon_client.get('/gym/session/1/sync.json', headers=JSON, environ_overrides=host)
    assert response.status_code == 401
    page = anon_client.get('/gym', headers={'Accept': 'text/html'}, environ_overrides=host)
    assert page.status_code == 302
    assert page.headers['Location'].endswith('/login')

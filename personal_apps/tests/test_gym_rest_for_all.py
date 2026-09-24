"""V3 "Deine Pause": one rest for all of a lifter's exercises -- the rest's
three levels, the routes that set them, and where a workout reads them.

The pure half needs nothing; the rest runs against the real local
development database, as a fresh lifter on three key-less rows, all of it
deleted afterwards.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import embedded_payload
from features.gym import exercises
from features.gym.exercises import resolve, to_store

LIST = {'weight_increment': 5.0, 'default_rest_seconds': 90, 'stack_kg': None, 'bar_weight': None}
JSON = {'Accept': 'application/json'}


# -- pure ----------------------------------------------------------------------

def test_the_rest_for_all_sits_between_the_own_rest_and_the_lists():
    assert resolve(LIST, None).default_rest_seconds == 90
    assert resolve(LIST, None, 150).default_rest_seconds == 150
    assert resolve(LIST, {'default_rest_seconds': 180}, 150).default_rest_seconds == 180


def test_the_rest_for_all_is_not_an_own_value_and_leaves_the_rest_alone():
    setup = resolve(LIST, None, 150)
    assert setup.changed == frozenset()
    assert setup.rest_for_all == 150
    assert setup.weight_increment == 5.0


def test_an_own_rest_is_stored_only_as_an_exception_to_the_rest_for_all():
    assert to_store(LIST, {'default_rest_seconds': 150}, 'stack', 150) == {'default_rest_seconds': None}
    # The list's own rest is then an exception worth keeping...
    assert to_store(LIST, {'default_rest_seconds': 90}, 'stack', 150) == {'default_rest_seconds': 90}
    # ...and without a rest for all it is the one that stores nothing.
    assert to_store(LIST, {'default_rest_seconds': 90}, 'stack') == {'default_rest_seconds': None}


# -- against the database --------------------------------------------------------

@pytest.fixture()
def lifter():
    """A fresh lifter and three key-less rows: a curl (list rest 90), a row
    (150) and a stack machine (90). Yields {'user', 'curl', 'row', 'machine'}
    ids; everything goes afterwards."""
    from extensions import db
    from models import (AppUser, Exercise, ExerciseSettings, LifterSettings, WorkoutSession,
                        WorkoutTemplate)
    from werkzeug.security import generate_password_hash
    with flask_app.app_context():
        user = AppUser(username='pytest rest lifter', password_hash=generate_password_hash('x'),
                       is_admin=False)
        rows = {
            'curl': Exercise(name='pytest rest curl', list_increment=2.5, list_rest_seconds=90),
            'row': Exercise(name='pytest rest row', list_increment=2.5, list_rest_seconds=150),
            'machine': Exercise(name='pytest rest machine', equipment='stack', list_increment=5.0,
                                list_rest_seconds=90),
        }
        db.session.add_all([user, *rows.values()])
        db.session.commit()
        ids = {'user': user.id, **{key: row.id for key, row in rows.items()}}
    yield ids
    with flask_app.app_context():
        uid = ids['user']
        for session_ in WorkoutSession.query.filter_by(user_id=uid).all():
            session_.resting_set_id = None
            db.session.commit()
            db.session.delete(session_)
        for template in WorkoutTemplate.query.filter_by(user_id=uid).all():
            db.session.delete(template)
        ExerciseSettings.query.filter_by(user_id=uid).delete()
        LifterSettings.query.filter_by(user_id=uid).delete()
        db.session.commit()
        for key in ('curl', 'row', 'machine'):
            db.session.delete(db.session.get(Exercise, ids[key]))
        db.session.delete(db.session.get(AppUser, uid))
        db.session.commit()


@pytest.fixture()
def lifter_client(lifter):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = lifter['user']
        yield test_client


def _own(uid, rests):
    """Own settings rows for `uid`, {exercise_id: rest} or {exercise_id:
    (rest, step)}. Needs an app context."""
    from extensions import db
    from models import ExerciseSettings
    for exercise_id, value in rests.items():
        rest, step = value if isinstance(value, tuple) else (value, None)
        db.session.add(ExerciseSettings(user_id=uid, exercise_id=exercise_id,
                                        default_rest_seconds=rest, weight_increment=step))
    db.session.commit()


def _rests(lifter):
    """{key: (rest in force, own rest stored)} for the three rows."""
    from extensions import db
    from models import Exercise, ExerciseSettings
    rows = {key: db.session.get(Exercise, lifter[key]) for key in ('curl', 'row', 'machine')}
    resolved = exercises.setups(lifter['user'], rows.values())
    stored = {row.exercise_id: row.default_rest_seconds
              for row in ExerciseSettings.query.filter_by(user_id=lifter['user'])}
    return {key: (resolved[row.id].default_rest_seconds, stored.get(row.id))
            for key, row in rows.items()}


def test_switching_it_on_absorbs_the_own_rests_equal_to_it(lifter):
    """Twelve single rests, ten of them 2:30, become 2:30 for all and two
    exceptions -- here three become one and one."""
    from extensions import db
    from models import ExerciseSettings
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['curl']: 150, lifter['row']: 180,
                   lifter['machine']: (150, 8.0)})
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        assert _rests(lifter) == {'curl': (150, None), 'row': (180, 180), 'machine': (150, None)}
        # The curl's row held nothing else and is gone; the machine keeps its step.
        steps = {row.exercise_id: row.weight_increment
                 for row in ExerciseSettings.query.filter_by(user_id=uid)}
        assert steps == {lifter['row']: None, lifter['machine']: 8.0}


def test_changing_it_keeps_every_exception_it_passes(lifter):
    """The stepper walks through values: an exception it stops on for a
    moment must still be one when it moves on."""
    from extensions import db
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['row']: 180})
        for seconds in (150, 180, 165):
            exercises.set_rest_for_all(uid, seconds)
            db.session.commit()
        assert _rests(lifter) == {'curl': (165, None), 'row': (180, 180), 'machine': (165, None)}


def test_switching_it_off_goes_back_to_the_list_and_keeps_the_own_rests(lifter):
    from extensions import db
    from models import LifterSettings
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['row']: 180})
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        exercises.set_rest_for_all(uid, None)
        db.session.commit()
        assert db.session.get(LifterSettings, uid) is None
        assert _rests(lifter) == {'curl': (90, None), 'row': (180, 180), 'machine': (90, None)}


def test_the_overview_lists_the_exceptions_and_starts_where_most_rests_are(lifter):
    from extensions import db
    uid = lifter['user']
    with flask_app.app_context():
        assert exercises.rest_overview(uid)['start_seconds'] == exercises.REST_FOR_ALL_START
        _own(uid, {lifter['curl']: 150, lifter['row']: 180,
                   lifter['machine']: 150})
        overview = exercises.rest_overview(uid)
        assert overview['rest_for_all'] is None
        assert overview['start_seconds'] == 150
        assert [(e['name'], e['rest_seconds']) for e in overview['exceptions']] == [
            ('pytest rest curl', 150), ('pytest rest machine', 150), ('pytest rest row', 180)]
        assert (overview['list_min_seconds'], overview['list_max_seconds']) == (60, 180)
        exercises.set_rest_for_all(uid, 135)
        db.session.commit()
        assert exercises.rest_overview(uid)['start_seconds'] == 135


def test_a_tie_starts_on_the_longer_rest(lifter):
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['curl']: 120, lifter['row']: 180})
        assert exercises.rest_overview(uid)['start_seconds'] == 180


def _workout(uid, rows, finished=False):
    """A workout of `uid` with one row per (exercise_id, rest_seconds), each
    with one open set. Returns (session id, [session exercise ids], [set
    ids]). Needs an app context."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    now = dt.datetime.utcnow()
    session_ = WorkoutSession(name='pytest rest workout', user_id=uid, started_at=now,
                              finished_at=now if finished else None)
    for position, (exercise_id, rest) in enumerate(rows, start=1):
        row = SessionExercise(exercise_id=exercise_id, position=position, rest_seconds=rest)
        row.sets = [SessionSet(position=1, weight=20.0, reps=10, completed=False)]
        session_.exercises.append(row)
    db.session.add(session_)
    db.session.commit()
    return (session_.id, [se.id for se in session_.exercises],
            [se.sets[0].id for se in session_.exercises])


def test_the_timer_runs_the_rest_for_all(lifter, lifter_client):
    from extensions import db
    from models import WorkoutSession
    uid = lifter['user']
    with flask_app.app_context():
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        session_id, _, (set_id,) = _workout(uid, [(lifter['curl'], None)])
    before = dt.datetime.utcnow()
    response = lifter_client.post(f'/gym/set/{set_id}/toggle_complete',
                                  data={'completed': '1'}, headers=JSON)
    assert response.status_code == 200
    with flask_app.app_context():
        ends = db.session.get(WorkoutSession, session_id).rest_ends_at
        assert 148 <= (ends - before).total_seconds() <= 152


def test_pause_heute_at_the_setting_stores_nothing(lifter, lifter_client):
    from extensions import db
    from models import SessionExercise
    uid = lifter['user']
    with flask_app.app_context():
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        _, (se_id,), _ = _workout(uid, [(lifter['curl'], None)])
    stored = []
    for sent in ('120', '150', ''):
        lifter_client.post(f'/gym/session-exercise/{se_id}/rest', data={'rest_seconds': sent},
                           headers=JSON)
        with flask_app.app_context():
            stored.append(db.session.get(SessionExercise, se_id).rest_seconds)
    assert stored == [120, None, None]


def test_the_live_payload_names_the_rest_that_always_applies(lifter, lifter_client):
    from extensions import db
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['row']: 180})
        session_id, _, _ = _workout(uid, [(lifter['curl'], None), (lifter['row'], 200)])

    def rows():
        payload = embedded_payload(lifter_client.get(f'/gym/session/{session_id}').get_data(as_text=True))
        return [(e['rest_seconds'], e['rest_setting'], e['rest_setting_mine'])
                for e in payload['visible_exercises']]

    assert rows() == [(None, 90, False), (200, 180, True)]
    with flask_app.app_context():
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
    assert rows() == [(None, 150, True), (200, 180, True)]


def test_finishing_writes_the_rest_in_force_into_the_rows(lifter, lifter_client):
    """Tomorrow's setting must not rewrite what today's workout planned."""
    from extensions import db
    from models import SessionExercise, SessionSet
    uid = lifter['user']
    with flask_app.app_context():
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        session_id, se_ids, set_ids = _workout(uid, [(lifter['curl'], None), (lifter['row'], 200)])
        # Finishing needs something lifted: an empty workout is only
        # discarded (D5).
        db.session.get(SessionSet, set_ids[0]).completed = True
        db.session.commit()
    lifter_client.post(f'/gym/session/{session_id}/finish')
    with flask_app.app_context():
        assert [db.session.get(SessionExercise, i).rest_seconds for i in se_ids] == [150, 200]


def test_a_workout_started_from_a_routine_follows_the_setting(lifter, lifter_client):
    """A routine holds no rest (G-076), and the new rows hold none either:
    the setting decides, from the next set on."""
    from extensions import db
    from models import TemplateExercise, WorkoutSession, WorkoutTemplate
    uid = lifter['user']
    with flask_app.app_context():
        template = WorkoutTemplate(name='pytest rest routine', user_id=uid)
        template.exercises.append(TemplateExercise(exercise_id=lifter['curl'], position=1))
        db.session.add(template)
        db.session.commit()
        template_id = template.id
    lifter_client.post('/gym/start', data={'template_id': str(template_id)})
    with flask_app.app_context():
        session_ = WorkoutSession.query.filter_by(user_id=uid).one()
        assert [se.rest_seconds for se in session_.exercises] == [None]
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
        assert _rests(lifter)['curl'] == (150, None)


def test_saving_a_routine_copies_no_rest(lifter, lifter_client):
    """A routine has nowhere to keep one: the column went with G-076."""
    from models import TemplateExercise, WorkoutTemplate
    uid = lifter['user']
    with flask_app.app_context():
        session_id, _, _ = _workout(uid, [(lifter['curl'], 200)])
    lifter_client.post(f'/gym/session/{session_id}/save_as_template',
                       data={'template_name': 'pytest rest saved'})
    with flask_app.app_context():
        template = WorkoutTemplate.query.filter_by(user_id=uid).one()
        assert [te.exercise_id for te in template.exercises] == [lifter['curl']]
        assert 'rest_seconds' not in TemplateExercise.__table__.columns


def test_adding_an_exercise_mid_workout_stores_no_rest(lifter, lifter_client):
    from models import SessionExercise
    uid = lifter['user']
    with flask_app.app_context():
        session_id, _, _ = _workout(uid, [(lifter['curl'], None)])
    lifter_client.post(f'/gym/session/{session_id}/exercises/add',
                       data={'exercise_id': str(lifter['row'])}, headers=JSON)
    with flask_app.app_context():
        added = SessionExercise.query.filter_by(session_id=session_id,
                                                exercise_id=lifter['row']).one()
        assert added.rest_seconds is None


def test_the_rest_route_sets_changes_and_clears_and_refuses_garble(lifter, lifter_client):
    from extensions import db
    from models import LifterSettings

    def post(value):
        return lifter_client.post('/gym/rest', data={'rest_seconds': value}, headers=JSON)

    response = post('150')
    assert response.status_code == 200
    assert response.get_json()['rest_for_all'] == 150
    for garble in ('abc', '5', '601', '150.5'):
        assert post(garble).status_code == 400, garble
    with flask_app.app_context():
        assert db.session.get(LifterSettings, lifter['user']).rest_seconds == 150
    assert post('').get_json()['rest_for_all'] is None
    with flask_app.app_context():
        assert db.session.get(LifterSettings, lifter['user']) is None


def test_the_settings_routes_answer_with_the_sheets_values(lifter, lifter_client):
    from extensions import db
    curl = lifter['curl']
    got = lifter_client.get(f'/gym/exercises/{curl}/settings.json', headers=JSON).get_json()
    assert (got['default_rest_seconds'], got['own'], got['rest_for_all']) == (90, [], None)

    saved = lifter_client.post(f'/gym/exercises/{curl}/update',
                               data={'default_rest_seconds': '180'}, headers=JSON).get_json()
    assert (saved['default_rest_seconds'], saved['own']) == (180, ['default_rest_seconds'])

    with flask_app.app_context():
        exercises.set_rest_for_all(lifter['user'], 150)
        db.session.commit()
    saved = lifter_client.post(f'/gym/exercises/{curl}/update',
                               data={'default_rest_seconds': '150'}, headers=JSON).get_json()
    assert (saved['default_rest_seconds'], saved['own'], saved['rest_for_all']) == (150, [], 150)


def test_the_catalogue_carries_deine_pause(lifter, lifter_client):
    from extensions import db
    uid = lifter['user']
    with flask_app.app_context():
        _own(uid, {lifter['row']: 180})
        exercises.set_rest_for_all(uid, 150)
        db.session.commit()
    payload = embedded_payload(lifter_client.get('/gym/uebungen').get_data(as_text=True))
    assert payload['rest']['rest_for_all'] == 150
    assert [(e['name'], e['rest_seconds']) for e in payload['rest']['exceptions']] == [
        ('pytest rest row', 180)]

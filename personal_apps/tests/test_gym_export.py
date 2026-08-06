"""Export v2 is a contract with an external coaching tool: every key is
always present, a missing value is null or [], and nothing is ever
omitted. These tests are the contract."""
import datetime as dt
from types import SimpleNamespace

import pytest

from app import app as flask_app
from extensions import db
from features.gym import export, stats
from models import Exercise, WorkoutSession, SessionExercise, SessionSet
from conftest import _admin_id


def _exercise(**kwargs):
    base = dict(id=12, name='Military Press', muscle_group='Schultern',
                secondary_muscle_groups=['Trizeps'], equipment='plate_loaded',
                is_unilateral=False, bar_weight=20.0, weight_increment=2.5,
                stack_kg=None)
    base.update(kwargs)
    return SimpleNamespace(**base)


def _set(position=1, weight=35.0, reps=11, completed=True, completed_at=None):
    return SimpleNamespace(position=position, weight=weight, reps=reps,
                           completed=completed, completed_at=completed_at)


def _session_exercise(exercise=None, sets=None, **kwargs):
    base = dict(position=4, rest_seconds=150, notes=None, pain=False,
                skipped=False, replaces=None, replaced_by=None)
    base.update(kwargs)
    return SimpleNamespace(exercise=exercise or _exercise(),
                           sets=sets if sets is not None else [_set()], **base)


def _session(exercises=None, **kwargs):
    base = dict(id=33, name='HBF Push 06.08.2026', template=None,
                started_at=dt.datetime(2026, 8, 6, 9, 30),
                finished_at=dt.datetime(2026, 8, 6, 11, 2),
                is_deload=False, deload_pct=None, bodyweight_kg=96.8,
                notes='nach 8h Schicht')
    base.update(kwargs)
    return SimpleNamespace(
        exercises=exercises if exercises is not None else [_session_exercise()],
        **base)


@pytest.fixture()
def temp_finished_session():
    """A real, finished session belonging to the acting user (admin), with
    one exercise and one completed set. Exercises `build_payload` against
    actual ORM rows rather than SimpleNamespace fakes, so a rename of any
    model attribute the export module reads (stack_kg,
    secondary_muscle_groups, pain, bodyweight_kg, completed_at, ...) fails
    this test with an AttributeError instead of shipping unnoticed."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Export Exercise', user_id=_admin_id(),
                            muscle_group='Schultern', equipment='plate_loaded',
                            bar_weight=20.0)
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Test Export Session', user_id=_admin_id(),
                                 started_at=dt.datetime(2026, 8, 1, 9, 0),
                                 finished_at=dt.datetime(2026, 8, 1, 10, 0))
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.flush()
        session_set = SessionSet(session_exercise_id=se.id, position=1, weight=40.0,
                                 reps=8, completed=True,
                                 completed_at=dt.datetime(2026, 8, 1, 9, 15))
        db.session.add(session_set)
        db.session.commit()
        ids = (session.id, exercise.id)
    yield ids[0]
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, ids[0])
        if session is not None:
            db.session.delete(session)
        exercise = db.session.get(Exercise, ids[1])
        if exercise is not None:
            db.session.delete(exercise)
        db.session.commit()


@pytest.mark.parametrize('equipment,unilateral,expected', [
    ('dumbbell',     True,  'per_dumbbell'),
    ('dumbbell',     False, 'total'),
    ('plate_loaded', True,  'per_side'),
    ('plate_loaded', False, 'total'),
    ('stack',        True,  'per_side'),
    ('stack',        False, 'total'),
])
def test_weight_convention_matrix(equipment, unilateral, expected):
    assert export.weight_convention(equipment, unilateral) == expected


def test_session_carries_every_contract_key():
    """Full-dict assertion, not just a key set: a reviewer earlier wired
    seven fields to the wrong source (e.g. template_name/bodyweight_kg/pain
    hardcoded, exercise_name emitting muscle_group) and every test in this
    file still passed because they only checked `set(payload)`."""
    payload = export.session_payload(_session())
    assert payload == {
        'id': 33,
        'name': 'HBF Push 06.08.2026',
        'template_name': None,
        'started_at': '2026-08-06T09:30:00Z',
        'finished_at': '2026-08-06T11:02:00Z',
        'deload': False,
        'deload_pct': None,
        'bodyweight_kg': 96.8,
        'notes': 'nach 8h Schicht',
        'exercises': [{
            'exercise_id': 12,
            'exercise_name': 'Military Press',
            'muscle_group': 'Schultern',
            'secondary_muscle_groups': ['Trizeps'],
            'equipment': 'plate_loaded',
            'weight_convention': 'total',
            'bar_weight': 20.0,
            'increment_kg': 2.5,
            'stack_kg': None,
            'position': 4,
            'replaces': None,
            'replaced_by': None,
            'rest_seconds': 150,
            'notes': '',
            'pain': False,
            'skipped': False,
            'sets': [{'position': 1, 'weight': 35.0, 'reps': 11,
                      'completed': True, 'finished_at': None}],
        }],
    }


def test_session_with_template_carries_its_name():
    """The only other fixture leaves `template` None, which can't catch
    `template_name` reading the wrong attribute off a real template."""
    template = SimpleNamespace(name='Push Day A')
    payload = export.session_payload(_session(template=template))
    assert payload['template_name'] == 'Push Day A'


def test_exercise_carries_every_contract_key():
    payload = export.exercise_payload(_session_exercise())
    assert payload == {
        'exercise_id': 12,
        'exercise_name': 'Military Press',
        'muscle_group': 'Schultern',
        'secondary_muscle_groups': ['Trizeps'],
        'equipment': 'plate_loaded',
        'weight_convention': 'total',
        'bar_weight': 20.0,
        'increment_kg': 2.5,
        'stack_kg': None,
        'position': 4,
        'replaces': None,
        'replaced_by': None,
        'rest_seconds': 150,
        'notes': '',
        'pain': False,
        'skipped': False,
        'sets': [{'position': 1, 'weight': 35.0, 'reps': 11,
                  'completed': True, 'finished_at': None}],
    }


def test_unilateral_dumbbell_exercise_through_exercise_payload():
    """The only other fixture is non-unilateral plate_loaded, so the
    equipment/laterality wiring into weight_convention (and, since finding
    3, into the increment fallback) is barely exercised through this
    function otherwise."""
    exercise = _exercise(id=41, name='Kurzhantel Seitheben', equipment='dumbbell',
                         is_unilateral=True, bar_weight=None, weight_increment=None,
                         stack_kg=None)
    payload = export.exercise_payload(_session_exercise(exercise=exercise))
    assert payload == {
        'exercise_id': 41,
        'exercise_name': 'Kurzhantel Seitheben',
        'muscle_group': 'Schultern',
        'secondary_muscle_groups': ['Trizeps'],
        'equipment': 'dumbbell',
        'weight_convention': 'per_dumbbell',
        'bar_weight': None,
        'increment_kg': stats.DEFAULT_INCREMENT / 2,
        'stack_kg': None,
        'position': 4,
        'replaces': None,
        'replaced_by': None,
        'rest_seconds': 150,
        'notes': '',
        'pain': False,
        'skipped': False,
        'sets': [{'position': 1, 'weight': 35.0, 'reps': 11,
                  'completed': True, 'finished_at': None}],
    }


def test_missing_secondary_groups_export_as_empty_list():
    payload = export.exercise_payload(
        _session_exercise(exercise=_exercise(secondary_muscle_groups=None)))
    assert payload['secondary_muscle_groups'] == []


def test_stack_steps_suppress_the_increment():
    """The contract makes the two mutually exclusive: where an exercise has
    real stops, the stops are the whole answer."""
    payload = export.exercise_payload(
        _session_exercise(exercise=_exercise(stack_kg=[5, 13, 21], weight_increment=8)))
    assert payload['stack_kg'] == [5, 13, 21]
    assert payload['increment_kg'] is None


def test_increment_survives_without_stack_steps():
    """An explicit, non-zero increment is taken literally -- see
    stats.resolve_increment's docstring."""
    payload = export.exercise_payload(_session_exercise())
    assert payload['increment_kg'] == 2.5
    assert payload['stack_kg'] is None


def test_missing_increment_falls_back_to_the_apps_default():
    """weight_increment is NULL-means-default. Sending the raw null would
    make the coaching tool guess a step the app already knows; sending the
    resolved fallback keeps the two in agreement."""
    payload = export.exercise_payload(
        _session_exercise(exercise=_exercise(weight_increment=None, is_unilateral=False)))
    assert payload['increment_kg'] == stats.DEFAULT_INCREMENT


def test_missing_increment_falls_back_to_half_default_when_unilateral():
    payload = export.exercise_payload(
        _session_exercise(exercise=_exercise(weight_increment=None, is_unilateral=True)))
    assert payload['increment_kg'] == stats.DEFAULT_INCREMENT / 2


def test_completed_set_carries_its_timestamp():
    payload = export.set_payload(
        _set(completed=True, completed_at=dt.datetime(2026, 8, 6, 10, 14, 21)))
    assert payload == {'position': 1, 'weight': 35.0, 'reps': 11,
                       'completed': True, 'finished_at': '2026-08-06T10:14:21Z'}


def test_unfinished_set_exports_a_null_timestamp():
    payload = export.set_payload(_set(completed=False, completed_at=None))
    assert payload['completed'] is False
    assert payload['finished_at'] is None


def test_replacement_names_survive():
    original = SimpleNamespace(exercise=_exercise(name='T Bar Row (Standing)'))
    substitute = SimpleNamespace(exercise=_exercise(name='T Bar Row (Lying)'))
    payload = export.exercise_payload(
        _session_exercise(replaces=original, replaced_by=substitute))
    assert payload['replaces'] == 'T Bar Row (Standing)'
    assert payload['replaced_by'] == 'T Bar Row (Lying)'


def test_session_notes_is_null_when_absent():
    """Unlike the exercise note, an absent session note stays null -- the
    contract sample pins '' for the exercise note specifically, not for
    every absent scalar in the document."""
    payload = export.session_payload(_session(notes=None))
    assert payload['notes'] is None


def test_session_notes_survives_when_present():
    payload = export.session_payload(_session(notes='nach 8h Schicht'))
    assert payload['notes'] == 'nach 8h Schicht'


def test_exercise_notes_is_empty_string_when_absent():
    payload = export.exercise_payload(_session_exercise(notes=None))
    assert payload['notes'] == ''


def test_pain_and_skipped_are_both_coerced_to_bool():
    """Both columns are non-nullable booleans; the export must treat them
    the same way rather than coercing one and trusting the other."""
    payload = export.exercise_payload(_session_exercise(pain=0, skipped=1))
    assert payload['pain'] is False
    assert payload['skipped'] is True


def test_a_deload_session_with_a_skipped_noted_exercise():
    """Every other fixture in this file leaves skipped/deload/deload_pct/notes
    at their falsy default, so a hardcoded False/False/None/'' in the export
    module would pass every other test here. This is the one test that
    actually flips each of them and checks the flip survives."""
    se = _session_exercise(notes='linke Schulter zwickt', pain=True, skipped=True)
    payload = export.session_payload(
        _session(is_deload=True, deload_pct=85, exercises=[se]))
    assert payload['deload'] is True
    assert payload['deload_pct'] == 85
    assert payload['exercises'][0]['skipped'] is True
    assert payload['exercises'][0]['pain'] is True
    assert payload['exercises'][0]['notes'] == 'linke Schulter zwickt'


def test_range_derives_from_the_sessions_actually_exported():
    early = _session(id=31, started_at=dt.datetime(2026, 7, 24, 8, 0))
    late = _session(id=33, started_at=dt.datetime(2026, 8, 6, 9, 30))
    payload = export.build_payload([early, late], [31, 32, 33],
                                   dt.datetime(2026, 8, 6, 18, 0))
    assert payload['schema_version'] == 2
    assert payload['exported_at'] == '2026-08-06T18:00:00Z'
    assert payload['range'] == {'from': '2026-07-24', 'to': '2026-08-06'}
    assert payload['requested_session_ids'] == [31, 32, 33]
    assert len(payload['sessions']) == 2


def test_empty_selection_still_carries_every_key():
    payload = export.build_payload([], [], dt.datetime(2026, 8, 6, 18, 0))
    assert set(payload) == {'schema_version', 'exported_at', 'range',
                            'requested_session_ids', 'sessions'}
    assert payload['range'] == {'from': None, 'to': None}
    assert payload['sessions'] == []
    assert payload['schema_version'] == 2


def test_route_returns_v2(client):
    """The HTTP surface, end to end. An empty id list is the cheapest
    request that still has to satisfy the whole contract."""
    response = client.get('/gym/export?ids=')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {'schema_version', 'exported_at', 'range',
                         'requested_session_ids', 'sessions'}
    assert body['schema_version'] == 2
    assert body['range'] == {'from': None, 'to': None}


def test_route_exports_a_real_finished_session(client, temp_finished_session):
    """`?ids=` alone never runs any of the three payload builders against a
    real row -- every model attribute they read was validated only against
    hand-written SimpleNamespace fakes. This requests one real, finished
    session and lets the whole ORM -> payload chain execute for real."""
    session_id = temp_finished_session
    response = client.get(f'/gym/export?ids={session_id}')
    assert response.status_code == 200
    body = response.get_json()
    assert len(body['sessions']) == 1
    exercises = body['sessions'][0]['exercises']
    assert len(exercises) == 1
    assert set(exercises[0]) == {
        'exercise_id', 'exercise_name', 'muscle_group', 'secondary_muscle_groups',
        'equipment', 'weight_convention', 'bar_weight', 'increment_kg',
        'stack_kg', 'position', 'replaces', 'replaced_by', 'rest_seconds',
        'notes', 'pain', 'skipped', 'sets',
    }
    assert exercises[0]['increment_kg'] == stats.DEFAULT_INCREMENT
    sets = exercises[0]['sets']
    assert len(sets) == 1
    assert set(sets[0]) == {'position', 'weight', 'reps', 'completed', 'finished_at'}


def test_v1_field_name_is_gone():
    """`is_deload` became `deload`. Asserted against a payload that actually
    HAS a session -- against an empty export the same assertion passes no
    matter what the session shape is."""
    payload = export.build_payload([_session()], [33], dt.datetime(2026, 8, 6, 18, 0))
    assert 'deload' in payload['sessions'][0]
    assert 'is_deload' not in payload['sessions'][0]

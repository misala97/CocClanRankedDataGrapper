"""Export v2 is a contract with an external coaching tool: every key is
always present, a missing value is null or [], and nothing is ever
omitted. These tests are the contract."""
import datetime as dt
from types import SimpleNamespace

import pytest

from features.gym import export


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
    payload = export.session_payload(_session())
    assert set(payload) == {
        'id', 'name', 'template_name', 'started_at', 'finished_at',
        'deload', 'deload_pct', 'bodyweight_kg', 'notes', 'exercises',
    }
    assert payload['deload'] is False
    assert payload['template_name'] is None


def test_exercise_carries_every_contract_key():
    payload = export.exercise_payload(_session_exercise())
    assert set(payload) == {
        'exercise_id', 'exercise_name', 'muscle_group', 'secondary_muscle_groups',
        'equipment', 'weight_convention', 'bar_weight', 'increment_kg',
        'stack_kg', 'position', 'replaces', 'replaced_by', 'rest_seconds',
        'notes', 'pain', 'skipped', 'sets',
    }
    assert payload['exercise_id'] == 12
    assert payload['weight_convention'] == 'total'
    assert payload['notes'] == ''


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
    payload = export.exercise_payload(_session_exercise())
    assert payload['increment_kg'] == 2.5
    assert payload['stack_kg'] is None


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


def test_v1_field_name_is_gone():
    """`is_deload` became `deload`. Asserted against a payload that actually
    HAS a session -- against an empty export the same assertion passes no
    matter what the session shape is."""
    payload = export.build_payload([_session()], [33], dt.datetime(2026, 8, 6, 18, 0))
    assert 'deload' in payload['sessions'][0]
    assert 'is_deload' not in payload['sessions'][0]

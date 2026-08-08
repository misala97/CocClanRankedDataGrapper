"""The live-workout JSON contract.

Mirrors what session_detail already computes. Every model forbids extra fields
on purpose: a field added to the route and not to the schema should fail here
rather than silently vanish from the payload and leave the screen missing a
number.

Every type below was read off the producer in workout.py rather than inferred
from the template. Step 1's schema was written the other way round and was
wrong in five places, one of which shipped past a green suite.
"""
import pytest
from pydantic import ValidationError

from features.gym.schemas import SessionDetailPayload


def _minimal():
    """A freshly started workout: one exercise, one set, nothing completed."""
    return {
        'session': {
            'id': 1, 'name': None,
            'started_at': '2026-08-08T10:00:00', 'finished_at': None,
            'is_deload': False, 'deload_pct': None,
            'rest_ends_at': None, 'resting_set_id': None,
            'template_id': None, 'template_name': None,
            'bodyweight_kg': None, 'notes': None, 'structure_version': 0,
        },
        'visible_exercises': [{
            'id': 10, 'exercise_id': 5, 'name': 'Bankdrücken',
            'muscle_group': 'Brust', 'position': 1, 'skipped': False,
            'is_unilateral': False, 'rest_seconds': 90, 'increment': 2.5,
            'notes': None, 'pain': False,
            'sets': [{
                'id': 100, 'weight': 60.0, 'reps': 8, 'completed': False,
                'base_weight': None,
            }],
        }],
        'live_id': 10, 'live_index': 1, 'live_increment': 2.5,
        'tick_states': ['now'], 'sets_done': 0, 'sets_total': 1, 'sets_open': 1,
        'session_volume': 0.0, 'resting': False, 'rest_total_seconds': 0,
        'suggestions': {'10': {'weight': 60.0, 'reps': 8}},
        'stagnation_counts': {}, 'record_set_ids': [],
        'ready_for_more': None, 'min_full_reps': 5,
        'default_plan_weight': 20.0, 'default_plan_reps': 8,
        'exercises': [{'id': 5, 'name': 'Bankdrücken', 'muscle_group': 'Brust'}],
        'muscle_groups': ['Brust'], 'vapid_public_key': None,
        'has_completed_set': False, 'deload_applied': False,
        'deload_pcts': [10, 20], 'deload_default_pct': 20,
        'partners': [], 'partner_status': [], 'session_is_shared': False,
    }


def test_accepts_a_fresh_session():
    payload = SessionDetailPayload.model_validate(_minimal())
    assert payload.live_id == 10
    assert payload.visible_exercises[0].sets[0].reps == 8


def test_accepts_a_session_with_nothing_live():
    """Every exercise skipped or finished leaves live_id None -- the screen
    still renders, so the schema must allow it."""
    data = _minimal()
    data['live_id'] = None
    data['live_index'] = 0
    assert SessionDetailPayload.model_validate(data).live_id is None


def test_ready_for_more_is_none_or_a_verdict():
    """The route initialises it to None and only fills it for the live
    exercise, outside a deload. An empty dict is not one of its values."""
    data = _minimal()
    assert SessionDetailPayload.model_validate(data).ready_for_more is None

    data['ready_for_more'] = {'sets': 3, 'weight': 60.0, 'is_latest': True}
    verdict = SessionDetailPayload.model_validate(data).ready_for_more
    assert verdict is not None and verdict.sets == 3

    data['ready_for_more'] = {}
    with pytest.raises(ValidationError):
        SessionDetailPayload.model_validate(data)


def test_a_suggestion_may_be_absent_for_an_exercise():
    """_seeded_suggestion returns None when there is no history to seed
    from, and the dict carries that None rather than omitting the key."""
    data = _minimal()
    data['suggestions'] = {'10': None}
    assert SessionDetailPayload.model_validate(data).suggestions['10'] is None


def test_rejects_an_unknown_field():
    data = _minimal()
    data['surprise'] = 1
    with pytest.raises(ValidationError, match='surprise'):
        SessionDetailPayload.model_validate(data)


def test_record_set_ids_is_a_list_not_a_set():
    """It is a set in the route. json.dumps cannot serialize a set, so the
    builder converts it -- if that conversion is ever dropped the endpoint
    500s at jsonify() rather than here, which is much harder to read."""
    data = _minimal()
    data['record_set_ids'] = [100, 101]
    dumped = SessionDetailPayload.model_validate(data).model_dump(mode='json')
    assert dumped['record_set_ids'] == [100, 101]


def test_int_keyed_dicts_serialize_as_string_keys():
    """suggestions and stagnation_counts are keyed by SessionExercise.id, an
    int. JSON object keys are always strings, so the client reads '10', not
    10. Pinned here so the React side is not surprised by it."""
    data = _minimal()
    data['stagnation_counts'] = {'10': 4}
    dumped = SessionDetailPayload.model_validate(data).model_dump(mode='json')
    assert list(dumped['stagnation_counts']) == ['10']
    assert list(dumped['suggestions']) == ['10']


def test_round_trips_to_json_mode():
    dumped = SessionDetailPayload.model_validate(_minimal()).model_dump(mode='json')
    assert dumped['session']['started_at'].startswith('2026-08-08')
    assert dumped['visible_exercises'][0]['name'] == 'Bankdrücken'
    assert dumped['session']['finished_at'] is None

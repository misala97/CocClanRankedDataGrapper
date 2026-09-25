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
            'mirrored': False,
            'is_unilateral': False, 'rest_seconds': 90, 'rest_setting': 150,
            'rest_setting_mine': True, 'increment': 2.5, 'floor': 20.0,
            'notes': None, 'pain': False, 'best': {'weight': 62.5, 'reps': 10}, 'picture': None,
            'replaced_sets_done': 0, 'replaced_volume': 0.0, 'is_substitute': False,
            'sets': [{
                'id': 100, 'weight': 60.0, 'reps': 8, 'completed': False,
                'base_weight': None, 'key': None,
            }],
        }],
        'live_id': 10, 'live_index': 1, 'live_increment': 2.5, 'live_floor': 20.0,
        'tick_states': ['now'], 'sets_done': 0, 'sets_total': 1, 'sets_open': 1,
        'session_volume': 0.0, 'resting': False, 'rest_total_seconds': 0,
        'suggestions': {'10': {'weight': 60.0, 'reps': 8}},
        'seed_sources': {'10': {'date': '2026-08-01T09:00:00', 'position': 1,
                                'basis': 'slot', 'is_latest': True,
                                'sets': [{'weight': 60.0, 'reps': 8}]}},
        'stagnation_counts': {}, 'next_targets': {}, 'deload_hints': {},
        'routine_plans': {},
        'record_set_ids': [], 'record_details': {},
        'first_time': {},
        'exercises': [{'id': 5, 'name': 'Bankdrücken (Langhantel)', 'muscle_group': 'Brust',
                       'search': 'bankdrucken langhantel bench press',
                       'movement': 'Bankdrücken', 'label': 'Langhantel',
                       'movement_group': 'Brust', 'workouts': 3, 'days_ago': 2,
                       'rank': 1, 'common': True}],
        'list_groups': ['Brust'], 'vapid_public_key': None,
        'has_completed_set': False, 'deload_applied': False,
        'deload_pcts': [10, 20], 'deload_default_pct': 20,
        'partners': [], 'partner_status': [], 'partner_links': [], 'session_is_shared': False,
    }


def test_accepts_a_fresh_session():
    payload = SessionDetailPayload.model_validate(_minimal())
    assert payload.live_id == 10
    assert payload.visible_exercises[0].sets[0].reps == 8


def test_a_planned_set_may_wait_blank_for_its_numbers():
    """An exercise with no history is planned with no numbers (V2), and a
    first time lists the lifter's other variants of the movement."""
    data = _minimal()
    data['visible_exercises'][0]['sets'][0].update(weight=None, reps=None)
    data['first_time'] = {'10': [{'label': 'Kurzhantel', 'weight': 26.0, 'reps': 10,
                                  'per_side': True}]}
    data['live_floor'] = None
    payload = SessionDetailPayload.model_validate(data)
    assert payload.visible_exercises[0].sets[0].weight is None
    dumped = payload.model_dump(mode='json')
    assert dumped['first_time']['10'][0] == {'label': 'Kurzhantel', 'weight': 26.0,
                                             'reps': 10, 'per_side': True}


def test_accepts_a_session_with_nothing_live():
    """Every exercise skipped or finished leaves live_id None -- the screen
    still renders, so the schema must allow it."""
    data = _minimal()
    data['live_id'] = None
    data['live_index'] = 0
    assert SessionDetailPayload.model_validate(data).live_id is None


def test_a_target_is_a_weight_and_reps_per_set():
    """Set by set (D2 P1): a set without its reps is no target."""
    data = _minimal()
    data['next_targets'] = {'10': [{'weight': 60.0, 'reps': 9}, {'weight': 55.0, 'reps': 10}]}
    targets = SessionDetailPayload.model_validate(data).next_targets['10']
    assert [(t.weight, t.reps) for t in targets] == [(60.0, 9), (55.0, 10)]

    data['next_targets'] = {'10': [{'weight': 60.0}]}
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
    data['next_targets'] = {'10': [{'weight': 68.0, 'reps': 6}]}
    data['deload_hints'] = {'10': 42.5}
    data['routine_plans'] = {'10': {'sets': 3, 'rep_min': 6, 'rep_max': 10}}
    dumped = SessionDetailPayload.model_validate(data).model_dump(mode='json')
    assert list(dumped['stagnation_counts']) == ['10']
    assert list(dumped['suggestions']) == ['10']
    assert list(dumped['next_targets']) == ['10']
    assert list(dumped['deload_hints']) == ['10']
    assert list(dumped['routine_plans']) == ['10']


def test_record_details_are_keyed_by_set_id_as_strings():
    """Keyed by Set.id, not SessionExercise.id -- the takeover looks a detail
    up by the same id it found in record_set_ids."""
    data = _minimal()
    data['record_set_ids'] = [100]
    data['record_details'] = {'100': {
        'kind': 'e1rm', 'value': 82.5, 'previous': 80.0,
        'previous_at': '2026-09-09T18:30:00',
    }}
    dumped = SessionDetailPayload.model_validate(data).model_dump(mode='json')
    assert list(dumped['record_details']) == ['100']
    assert dumped['record_details']['100']['kind'] == 'e1rm'
    assert dumped['record_details']['100']['previous'] == 80.0


@pytest.mark.parametrize('kind', ['weight', 'volume'])
def test_rejects_a_record_kind_the_live_screen_cannot_render(kind):
    """A record is e1RM only (D3). The weight and volume kinds are gone --
    accepting one would put a word on the gold slab that the copy has no
    branch for."""
    data = _minimal()
    data['record_set_ids'] = [100]
    data['record_details'] = {'100': {
        'kind': kind, 'value': 1830.0, 'previous': 1656.0,
        'previous_at': '2026-09-09T18:30:00',
    }}
    with pytest.raises(ValidationError, match='kind'):
        SessionDetailPayload.model_validate(data)


def test_round_trips_to_json_mode():
    dumped = SessionDetailPayload.model_validate(_minimal()).model_dump(mode='json')
    assert dumped['session']['started_at'].startswith('2026-08-08')
    assert dumped['visible_exercises'][0]['name'] == 'Bankdrücken'
    assert dumped['session']['finished_at'] is None

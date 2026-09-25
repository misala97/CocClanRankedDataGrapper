"""The exercise-detail JSON contract.

These assert the shape the React page reads, so a rename on the Python side
fails here rather than rendering an empty page.

Every model sets extra='forbid'. That is the point: the schema is a mirror of
what stats, plan and routes._exercise_detail_payload already return, and a
field appearing on one side but not the other should be loud. What enforces it
against real output is test_every_exercise_builds_a_valid_payload in
test_gym_exercise_detail_json.py, which validates the payload of every
exercise in the dev database.
"""
import pytest
from pydantic import ValidationError

from features.gym.schemas import ExerciseDetailPayload


def _minimal():
    """The empty-history case: a brand new exercise with nothing logged."""
    return {
        'exercise': {
            'id': 1, 'name': 'Bankdrücken', 'muscle_group': 'Brust',
            'is_unilateral': False, 'default_rest_seconds': 90,
            'weight_increment': 2.5, 'equipment': 'barbell',
            'bar_weight': 20.0, 'stack_kg': None,
            'secondary_muscle_groups': ['Trizeps'],
            'list_defaults': {'default_rest_seconds': 180, 'weight_increment': 2.5,
                              'bar_weight': 20.0, 'stack_kg': None},
            'own': ['default_rest_seconds'], 'rest_for_all': None,
        },
        'table': [], 'goal': None, 'weights': [], 'pr_e1rm': None, 'trend': None,
        'stairs': [], 'position_pills': [], 'selected_position': None,
        'state': 'neu', 'sessions_since_pr': None,
        'chip_class': None, 'chip_label': None,
        'about': {'picture': None, 'movement': None, 'variants': []},
        'equipment_labels': {'barbell': 'Langhantel'},
        'on_list': True, 'running': None, 'routines': [],
    }


def _a_row():
    return {
        'session_id': 7, 'started_at': '2026-08-01T18:30:00',
        'position': 2, 'is_deload': False, 'is_record': False,
        'sets': [{'weight': 80.0, 'reps': 8}] * 3, 'volume': 1920.0, 'e1rm': 100.0,
    }


def _populated():
    """A lift with history: every part of the page filled."""
    data = _minimal()
    data.update({
        'table': [_a_row()],
        'goal': {
            'sets': [{'weight': 80.0, 'reps': 9}] * 3, 'last_sets': [{'weight': 80.0, 'reps': 8}] * 3,
            'last_at': '2026-08-01T18:30:00', 'rep_min': 6, 'rep_max': 10, 'stepped': False,
            'step_ups': [82.5, 82.5, None],
        },
        'weights': [{'weight': 80.0, 'reps': 8, 'workouts': 1, 'first_at': '2026-08-01T18:30:00'}],
        'pr_e1rm': {'e1rm': 101.3, 'weight': 80.0, 'reps': 8, 'session_id': 7,
                    'started_at': '2026-08-01T18:30:00', 'position': 2, 'is_record': True},
        'trend': {'per_month': -0.4, 'workouts': 5},
        'stairs': [{
            'position': None, 'lo': 97.5, 'hi': 102.5, 'ticks': [98, 100, 102],
            'since': 0, 'stalled': False,
            'cols': [
                {'session_id': 6, 'position': 1, 'started_at': '2026-07-25T18:30:00',
                 'e1rm': 99.0, 'best': 99.0, 'kind': 'workout'},
                {'session_id': 7, 'position': 2, 'started_at': '2026-08-01T18:30:00',
                 'e1rm': 101.3, 'best': 101.3, 'kind': 'record'},
            ],
        }],
        'about': {'picture': '/static/gym/art/bench.webp', 'movement': 'Bankdrücken',
                  'variants': [{'id': 3, 'label': 'Kurzhantel'}]},
    })
    return data


def test_accepts_empty_history():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    assert payload.exercise.name == 'Bankdrücken'
    assert payload.goal is None
    assert payload.table == []


def test_accepts_a_page_with_history():
    payload = ExerciseDetailPayload.model_validate(_populated())
    assert payload.table[0].sets[0].reps == 8
    assert payload.goal.step_ups == [82.5, 82.5, None]
    assert payload.stairs[0].cols[1].kind == 'record'


def test_rejects_a_row_missing_e1rm():
    data = _minimal()
    row = _a_row()
    del row['e1rm']
    data['table'] = [row]
    with pytest.raises(ValidationError, match='e1rm'):
        ExerciseDetailPayload.model_validate(data)


def test_rejects_an_unknown_field():
    """extra='forbid' is what makes this schema a mirror rather than a subset.
    Without it, a field renamed in stats.py would silently vanish from the
    payload and the page would render a blank where a number belongs."""
    data = _minimal()
    data['surprise'] = 1
    with pytest.raises(ValidationError, match='surprise'):
        ExerciseDetailPayload.model_validate(data)


def test_rejects_a_field_the_page_dropped():
    """The chart and the slot the page chose are gone (D9): a stale writer
    must fail here, not ship dead weight in every payload."""
    for field, value in (('chart', None), ('series', []), ('last_overall', None)):
        data = _minimal()
        data[field] = value
        with pytest.raises(ValidationError, match=field):
            ExerciseDetailPayload.model_validate(data)


def test_a_stair_workout_is_one_of_three_kinds():
    data = _populated()
    data['stairs'][0]['cols'][0]['kind'] = 'pr'
    with pytest.raises(ValidationError, match='kind'):
        ExerciseDetailPayload.model_validate(data)


def test_the_record_requires_session_id():
    """The log and the readout tie the record to its workout by session_id,
    never by the date -- two sessions on one day both matched a date test and
    both went gold."""
    data = _populated()
    del data['pr_e1rm']['session_id']
    with pytest.raises(ValidationError, match='session_id'):
        ExerciseDetailPayload.model_validate(data)


def test_the_best_set_says_whether_it_is_a_record():
    """"Rekord" or "Bestwert" is the server's to say (D3: the debut beats
    nothing); a payload that leaves it out would have the page guess."""
    data = _populated()
    del data['pr_e1rm']['is_record']
    with pytest.raises(ValidationError, match='is_record'):
        ExerciseDetailPayload.model_validate(data)


def test_round_trips_to_json_mode():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    dumped = payload.model_dump(mode='json')
    assert dumped['exercise']['name'] == 'Bankdrücken'
    assert dumped['stairs'] == []
    # Datetimes must serialize, not blow up, once rows are present.
    round_tripped = ExerciseDetailPayload.model_validate(_populated()).model_dump(mode='json')
    assert round_tripped['table'][0]['started_at'].startswith('2026-08-01')
    assert round_tripped['goal']['last_at'].startswith('2026-08-01')
    assert round_tripped['stairs'][0]['cols'][0]['started_at'].startswith('2026-07-25')
    assert round_tripped['weights'][0]['first_at'].startswith('2026-08-01')

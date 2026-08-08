"""The exercise-detail JSON contract.

These assert the shape the React page reads, so a rename on the Python side
fails here rather than rendering an empty page.

Every model sets extra='forbid'. That is the point: the schema is a mirror of
what stats.exercise_progress() and routes._chart_geometry() already return, and
a field appearing on one side but not the other should be loud. The last test
in this file validates against real output from the dev database, which is what
actually enforces that.
"""
import pytest
from pydantic import ValidationError

from features.gym.schemas import ChartGeometry, ExerciseDetailPayload


def _minimal():
    """The empty-history case: a brand new exercise with nothing logged."""
    return {
        'exercise': {
            'id': 1, 'name': 'Bankdrücken', 'muscle_group': 'Brust',
            'is_unilateral': False, 'default_rest_seconds': 90,
            'weight_increment': 2.5, 'equipment': 'barbell',
            'bar_weight': 20.0, 'stack_kg': None,
            'secondary_muscle_groups': ['Trizeps'],
        },
        'table': [], 'series': [], 'available_positions': [],
        'selected_position': None, 'selected_position_is_default': False,
        'selected_position_reason': None,
        'last_overall': None, 'pr_weight': None, 'pr_e1rm': None,
        'last_progression': None,
        'state': 'neu', 'sessions_since_pr': 0, 'chart': None,
        'chip_class': None, 'chip_label': None, 'can_delete': True,
        'muscle_groups': ['Brust', 'Trizeps'],
        'equipment_labels': {'barbell': 'Langhantel'},
    }


def _a_row():
    return {
        'session_id': 7, 'started_at': '2026-08-01T18:30:00',
        'position': 2, 'is_deload': False, 'sets_display': '3 × 8',
        'best_weight': 80.0, 'volume': 1920.0, 'e1rm': 100.0,
    }


def test_accepts_empty_history():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    assert payload.exercise.name == 'Bankdrücken'
    assert payload.chart is None
    assert payload.table == []


def test_accepts_a_populated_row():
    data = _minimal()
    data['table'] = [_a_row()]
    data['available_positions'] = [2]
    payload = ExerciseDetailPayload.model_validate(data)
    assert payload.table[0].session_id == 7
    assert payload.table[0].e1rm == 100.0


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


def test_both_pr_shapes_require_session_id():
    """exercise_detail.html matches the record row on session_id, never on the
    date -- two sessions on one day both matched a date test and both went
    gold. Losing the field would break that match silently."""
    data = _minimal()
    data['pr_weight'] = {'weight': 80.0, 'reps': 5, 'position': 2,
                         'started_at': '2026-08-01T18:30:00'}
    with pytest.raises(ValidationError, match='session_id'):
        ExerciseDetailPayload.model_validate(data)


def test_round_trips_to_json_mode():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    dumped = payload.model_dump(mode='json')
    assert dumped['exercise']['name'] == 'Bankdrücken'
    assert dumped['chart'] is None
    # Datetimes must serialize, not blow up, once rows are present.
    populated = _minimal()
    populated['table'] = [_a_row()]
    round_tripped = ExerciseDetailPayload.model_validate(populated).model_dump(mode='json')
    assert round_tripped['table'][0]['started_at'].startswith('2026-08-01')


def test_matches_real_chart_geometry():
    """The guard that actually earns extra='forbid'. Builds real geometry from
    the dev database and validates it, so a field added to _chart_geometry
    fails here instead of at render time."""
    from app import app as flask_app
    from features.gym.routes import _chart_geometry
    from features.gym import stats
    from features.gym.scope import my_exercises
    from features.gym.routes import load_performed
    from conftest import acting_as, _admin_id

    with acting_as(_admin_id()):
        geometry = None
        for exercise in my_exercises().all():
            rows = load_performed(exercise_ids=[exercise.id], include_active=True)
            progress = stats.exercise_progress(rows, position=None)
            candidate = _chart_geometry(progress['series'], progress.get('pr_e1rm'))
            if candidate:
                geometry = candidate
                break

    if geometry is None:
        pytest.skip('the dev database has no exercise with plottable history')

    validated = ChartGeometry.model_validate(geometry)
    assert validated.width > 0
    assert validated.series

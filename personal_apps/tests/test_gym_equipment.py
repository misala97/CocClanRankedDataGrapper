"""The equipment facts an exercise carries -- how it is loaded, what dead
weight is baked into the logged number, which muscles it hits besides the
primary one -- and the settings form that lets a lifter state their own gym's
step, rest, stack stops and bar on top of the list's.

Since the one exercise list (2026-09-23) the facts are the list's and
read-only; the form writes gym_exercise_settings, never the row."""
import pytest

from app import app as flask_app
from extensions import db
from features.gym.library import LIBRARY
from models import Exercise, ExerciseSettings, EQUIPMENT_TYPES, EQUIPMENT_LABELS
from conftest import _admin_id, list_exercise


@pytest.fixture()
def temp_exercise():
    """A throwaway key-less row (the list rows are everyone's), removed again
    afterwards together with any settings on it. The suite runs against a
    real database, so nothing may be left behind."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Equipment')
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id
    yield exercise_id
    with flask_app.app_context():
        row = db.session.get(Exercise, exercise_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


@pytest.fixture()
def barbell_exercise():
    """A key-less plate-loaded row whose list bar is 20 kg."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Barbell', equipment='plate_loaded',
                            list_bar_weight=20.0, list_increment=2.5,
                            list_rest_seconds=180)
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id
    yield exercise_id
    with flask_app.app_context():
        row = db.session.get(Exercise, exercise_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def _settings(exercise_id):
    with flask_app.app_context():
        row = ExerciseSettings.query.filter_by(user_id=_admin_id(),
                                               exercise_id=exercise_id).first()
        if row is None:
            return None
        return {field: getattr(row, field) for field in
                ('weight_increment', 'default_rest_seconds', 'stack_kg', 'bar_weight')}


def test_equipment_defaults_to_stack(temp_exercise):
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert row.equipment == 'stack'
        assert row.list_bar_weight is None
        assert row.list_stack_kg is None
        assert row.secondary_muscle_groups is None


def test_equipment_facts_round_trip(temp_exercise):
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        row.equipment = 'plate_loaded'
        row.list_bar_weight = 20.0
        row.list_stack_kg = [5, 13, 21, 29]
        row.secondary_muscle_groups = ['Trizeps', 'Schultern']
        db.session.commit()
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert row.equipment == 'plate_loaded'
        assert row.list_bar_weight == 20.0
        assert row.list_stack_kg == [5, 13, 21, 29]
        assert row.secondary_muscle_groups == ['Trizeps', 'Schultern']


def test_every_equipment_type_has_a_label():
    assert set(EQUIPMENT_LABELS) == set(EQUIPMENT_TYPES)
    assert all(EQUIPMENT_LABELS[value] for value in EQUIPMENT_TYPES)


def test_the_list_rows_carry_the_lists_facts():
    """One side or both decides every volume figure of a history, so a list
    row must state exactly what library.py states."""
    with flask_app.app_context():
        list_exercise()                                   # syncs the list
        rows = {e.library_key: e for e in Exercise.query.filter(
            Exercise.library_key.isnot(None)).all()}
        for entry in LIBRARY:
            row = rows[entry.key]
            assert (row.is_unilateral, row.equipment, row.name) == \
                (entry.unilateral, entry.equipment, entry.name), entry.key


def test_stack_steps_parser_accepts_a_typed_list():
    from features.gym.routes import _to_stack_steps
    assert _to_stack_steps('5, 13,21 , 29') == [5.0, 13.0, 21.0, 29.0]
    assert _to_stack_steps('5; 13') == [5.0, 13.0]
    assert _to_stack_steps('21, 5, 13') == [5.0, 13.0, 21.0], 'sorted ascending'
    assert _to_stack_steps('') is None
    assert _to_stack_steps('   ') is None
    assert _to_stack_steps('abc') is None
    assert _to_stack_steps('5, abc, 13') == [5.0, 13.0], 'junk entries dropped'


def test_the_settings_form_stores_stack_stops_as_the_lifters_setting(client, temp_exercise):
    """The row keeps the list's values; the lifter's stops land in their
    settings. Identity fields a stale form still posts are ignored."""
    response = client.post(f'/gym/exercises/{temp_exercise}/update', data={
        'name': 'ZZ Renamed Equipment',
        'muscle_group': 'Rücken',
        'equipment': 'dumbbell',
        'bar_weight': '',
        'stack_kg': '5, 13, 21, 29',
        'secondary_muscle_groups': ['Bizeps'],
    }, follow_redirects=False)
    assert response.status_code == 302
    assert _settings(temp_exercise)['stack_kg'] == [5.0, 13.0, 21.0, 29.0]
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert (row.name, row.equipment, row.muscle_group) == ('ZZ Test Equipment', 'stack', None)
        assert row.list_stack_kg is None
        assert row.secondary_muscle_groups is None


def test_stack_stops_on_a_machine_without_a_stack_are_not_stored(client, barbell_exercise):
    """Stops mean something on a stack only -- stale ones on a plate-loaded
    exercise would silently suppress its step in the export."""
    client.post(f'/gym/exercises/{barbell_exercise}/update',
                data={'stack_kg': '5, 13, 21, 29'})
    assert _settings(barbell_exercise) is None


def test_a_bar_of_zero_switches_the_lists_bar_off_and_blank_restores_it(client, barbell_exercise):
    client.post(f'/gym/exercises/{barbell_exercise}/update', data={'bar_weight': '0'})
    assert _settings(barbell_exercise)['bar_weight'] == 0.0
    client.post(f'/gym/exercises/{barbell_exercise}/update', data={'bar_weight': ''})
    assert _settings(barbell_exercise) is None, 'an all-list row is deleted'


def test_the_lists_own_value_is_not_stored(client, barbell_exercise):
    """Stored only while it differs, so a later change to the list still
    reaches every lifter who never changed it."""
    client.post(f'/gym/exercises/{barbell_exercise}/update',
                data={'weight_increment': '2,5', 'default_rest_seconds': '180',
                      'bar_weight': '20'})
    assert _settings(barbell_exercise) is None


def test_a_field_the_form_left_out_keeps_its_setting(client, barbell_exercise):
    client.post(f'/gym/exercises/{barbell_exercise}/update',
                data={'weight_increment': '1.25', 'default_rest_seconds': '150'})
    client.post(f'/gym/exercises/{barbell_exercise}/update', data={'default_rest_seconds': ''})
    assert _settings(barbell_exercise) == {'weight_increment': 1.25, 'default_rest_seconds': None,
                                           'stack_kg': None, 'bar_weight': None}

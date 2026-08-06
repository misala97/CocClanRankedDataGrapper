"""The equipment facts an exercise carries: how it is loaded, what dead
weight is baked into the logged number, and which muscles it hits besides
the primary one. is_unilateral is deliberately NOT part of this -- it
already exists, production holds the correct flags, and nothing here may
touch it."""
import pytest

from app import app as flask_app
from extensions import db
from models import Exercise, EQUIPMENT_TYPES, EQUIPMENT_LABELS
from conftest import _admin_id
from test_gym_sharing import linked_pair


@pytest.fixture()
def temp_exercise():
    """A throwaway catalogue entry, removed again afterwards. The suite runs
    against the real dev database, so nothing may be left behind."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Equipment', user_id=_admin_id())
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id
    yield exercise_id
    with flask_app.app_context():
        row = db.session.get(Exercise, exercise_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def test_equipment_defaults_to_stack(temp_exercise):
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert row.equipment == 'stack'
        assert row.bar_weight is None
        assert row.stack_kg is None
        assert row.secondary_muscle_groups is None


def test_equipment_facts_round_trip(temp_exercise):
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        row.equipment = 'plate_loaded'
        row.bar_weight = 20.0
        row.stack_kg = [5, 13, 21, 29]
        row.secondary_muscle_groups = ['Trizeps', 'Schultern']
        db.session.commit()
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert row.equipment == 'plate_loaded'
        assert row.bar_weight == 20.0
        assert row.stack_kg == [5, 13, 21, 29]
        assert row.secondary_muscle_groups == ['Trizeps', 'Schultern']


def test_every_equipment_type_has_a_label():
    assert set(EQUIPMENT_LABELS) == set(EQUIPMENT_TYPES)
    assert all(EQUIPMENT_LABELS[value] for value in EQUIPMENT_TYPES)


def test_seed_left_unilateral_flags_alone():
    """The migration seeds equipment, never laterality: overwriting one flag
    would silently halve or double that exercise's whole history."""
    with flask_app.app_context():
        rows = {e.name: e for e in Exercise.query.filter(
            Exercise.name.in_(['Chest Press (Machine, Lying)',
                               'Preacher Curl (Machine, Good)',
                               'Bench Press (Dumbbell)',
                               'Military Press'])).all()}
        if not rows:
            pytest.skip('dev catalogue does not carry the seeded exercise names')
        for name in ('Chest Press (Machine, Lying)', 'Preacher Curl (Machine, Good)',
                     'Bench Press (Dumbbell)'):
            if name in rows:
                assert rows[name].is_unilateral is True, name
        if 'Military Press' in rows:
            assert rows['Military Press'].is_unilateral is False
            assert rows['Military Press'].equipment == 'plate_loaded'
            assert rows['Military Press'].bar_weight == 20


def test_cloned_partner_exercise_inherits_equipment_facts(linked_pair):
    """A shared workout clones the leader's exercise into the follower's
    catalogue. Equipment is a property of the machine, so it travels --
    weight_increment stays behind because increments are per-person and are
    deliberately not copied here."""
    from features.gym import sharing
    from models import SharedSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        rigged = Exercise(name='pytest shared rigged lift',
                          user_id=linked_pair['leader_user'],
                          equipment='plate_loaded', bar_weight=20.0,
                          stack_kg=[5, 13, 21, 29],
                          secondary_muscle_groups=['Trizeps', 'Schultern'],
                          weight_increment=2.5)
        db.session.add(rigged)
        db.session.flush()

        resolved_id = sharing.follower_exercise_for(shared, rigged.id)
        db.session.commit()

        created = db.session.get(Exercise, resolved_id)
        assert created.equipment == 'plate_loaded'
        assert created.bar_weight == 20.0
        assert created.stack_kg == [5, 13, 21, 29]
        assert created.secondary_muscle_groups == ['Trizeps', 'Schultern']
        assert created.weight_increment is None, (
            'weight_increment is per-person and must not be copied, even '
            'though the leader had one set')

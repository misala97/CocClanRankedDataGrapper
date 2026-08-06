# Gym Export Schema v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the gym tracker the equipment facts a coaching tool needs, capture bodyweight/notes/pain per workout, and ship a `schema_version: 2` export carrying all of it.

**Architecture:** Two orthogonal exercise facts (`equipment` + the existing `is_unilateral`) replace the contract's single `weight_convention` enum, which is derived at export time instead of stored — so `stats.set_volume` and every figure computed from it stay untouched. The export payload moves out of `features/gym/routes.py` (2761 lines) into a new `features/gym/export.py` that takes ORM rows and returns plain dicts, so the schema is testable without HTTP.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate/Alembic, MySQL 8, Jinja templates, pytest.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-08-06-gym-export-v2-design.md`. It is authoritative where this plan is silent.
- Work on branch `dev_personal`. Do not merge to `main`.
- Never modify existing set or session data. Migrations add columns and seed the new ones only; `is_unilateral`, `weight`, `reps` and `weight_increment` are never written by a migration.
- The workout start path must not gain a step. Every new input lives inside an existing `<dialog class="sheet">`.
- All new UI is mobile-first and built from existing classes (`.field`, `.label`, `.input`, `.select`, `.check`, `.sheet__row`, `.sheet__group`, `.sheet__note`, `.btn`).
- German UI copy, matching the existing tone.
- Run tests from `personal_apps/`: `PYTHONPATH=. python -m pytest`. The suite runs against the real local dev MySQL database (`MySQL80` service must be running); the seeded admin account is the acting user.
- Alembic head before this work: `d98add219b32`. Migration revision ids are given per task — use them verbatim so the two revisions chain correctly.
- Equipment values are exactly `dumbbell`, `plate_loaded`, `stack`. There is no `barbell` — a loaded bar is `plate_loaded` with `bar_weight`.

---

### Task 1: Exercise equipment facts

**Files:**
- Modify: `personal_apps/models.py:145-170` (add `EQUIPMENT_TYPES`, `EQUIPMENT_LABELS`, four `Exercise` columns)
- Create: `personal_apps/migrations/versions/a1c4e8b20f31_add_exercise_equipment_facts.py`
- Modify: `personal_apps/features/gym/sharing.py:85-95` (carry the new facts to a partner's cloned exercise)
- Modify: `personal_apps/scripts/copy_templates.py:70-80` (same, for the copy script)
- Test: `personal_apps/tests/test_gym_equipment.py` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `models.EQUIPMENT_TYPES: tuple[str, ...]` = `('dumbbell', 'plate_loaded', 'stack')`
  - `models.EQUIPMENT_LABELS: dict[str, str]` — German label per value
  - `Exercise.equipment: str` (NOT NULL, default `'stack'`)
  - `Exercise.bar_weight: float | None`
  - `Exercise.stack_kg: list[float] | None` (JSON column)
  - `Exercise.secondary_muscle_groups: list[str] | None` (JSON column)

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_gym_equipment.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_equipment.py -v`
Expected: FAIL — `ImportError: cannot import name 'EQUIPMENT_TYPES' from 'models'`

- [ ] **Step 3: Add the constants and columns**

In `personal_apps/models.py`, directly below the `MUSCLE_GROUPS` tuple:

```python
# How an exercise is loaded. Two orthogonal facts describe a logged weight:
# this one, and is_unilateral below. Their combination is what the export's
# `weight_convention` is derived from -- storing that enum instead would put
# laterality in two places at once, and volume already depends on
# is_unilateral alone (stats.set_volume).
#
# A loaded barbell is `plate_loaded` with a bar_weight; it is not a value of
# its own, because "the bar is dead weight inside the number you logged" is
# exactly what bar_weight already says.
EQUIPMENT_TYPES = ('dumbbell', 'plate_loaded', 'stack')

EQUIPMENT_LABELS = {
    'dumbbell': 'Kurzhantel',
    'plate_loaded': 'Scheiben',
    'stack': 'Steckgewicht',
}
```

In the `Exercise` class, after `is_unilateral`:

```python
    equipment            = db.Column(db.String(20), nullable=False, default='stack',
                                     server_default='stack')  # one of EQUIPMENT_TYPES
    bar_weight           = db.Column(db.Float, nullable=True)   # dead weight (bar, carriage) already contained in the logged number
    # The real stops of an uneven stack, ascending. NULL on everything that
    # steps evenly -- weight_increment already answers those, and a list
    # spelling out 5,10,15,... would be the same fact typed twice. Mutually
    # exclusive with weight_increment in the export.
    stack_kg             = db.Column(db.JSON, nullable=True)
    # Values from MUSCLE_GROUPS. NULL and [] mean the same thing; readers
    # normalise to [].
    secondary_muscle_groups = db.Column(db.JSON, nullable=True)
```

- [ ] **Step 4: Write the migration**

Create `personal_apps/migrations/versions/a1c4e8b20f31_add_exercise_equipment_facts.py`:

```python
"""add equipment facts to gym exercises

Revision ID: a1c4e8b20f31
Revises: d98add219b32
Create Date: 2026-08-06

Adds how an exercise is loaded, the dead weight inside its logged number,
uneven stack stops, and secondary muscles -- then seeds the values for the
exercises actually in this gym, matched by name across every user's
catalogue (same machines, same hall, so a per-user answer is the same
answer three times).

is_unilateral is deliberately untouched: production already holds the
correct flags, and rewriting one would silently halve or double that
exercise's entire history in every statistic.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = 'a1c4e8b20f31'
down_revision = 'd98add219b32'
branch_labels = None
depends_on = None


# name -> (equipment, bar_weight, secondary muscle groups)
SEED = {
    'Bench Press (Dumbbell)':                   ('dumbbell',     None, ['Trizeps', 'Schultern']),
    'Biceps Curl (Rotating)':                   ('dumbbell',     None, []),
    'Hammer Curl (Dumbbell)':                   ('dumbbell',     None, []),
    'Chest Press (Machine, Lying)':             ('plate_loaded', None, ['Trizeps', 'Schultern']),
    'Preacher Curl (Machine, Good)':            ('plate_loaded', None, []),
    'Lat Pulldown (Single Arm, Hauptbahnhof)':  ('plate_loaded', None, ['Bizeps']),
    'Military Press':                           ('plate_loaded', 20,   ['Trizeps']),
    'T Bar Row (Standing)':                     ('plate_loaded', None, ['Bizeps']),
    'T Bar Row (Lying)':                        ('plate_loaded', None, ['Bizeps']),
    'Chest Fly (Machine)':                      ('stack',        None, []),
    'Lateral Raise (Machine, Good)':            ('stack',        None, []),
    'Triceps Pushdown (Cable, EZ Bar)':         ('stack',        None, []),
    'Triceps Extension (Cable, Overhead)':      ('stack',        None, []),
    'Seated Row (Machine, Good)':               ('stack',        None, ['Bizeps']),
    'Lat Pulldown Kabelzug':                    ('stack',        None, ['Bizeps']),
    'Reverse Fly (Machine)':                    ('stack',        None, []),
    'Preacher Curl Bilateral':                  ('stack',        None, []),
}


def upgrade():
    # server_default on equipment: the column is NOT NULL and the table has
    # rows, which would otherwise fail the ALTER.
    op.add_column('gym_exercises',
                  sa.Column('equipment', sa.String(length=20), nullable=False,
                            server_default='stack'))
    op.add_column('gym_exercises', sa.Column('bar_weight', sa.Float(), nullable=True))
    op.add_column('gym_exercises', sa.Column('stack_kg', sa.JSON(), nullable=True))
    op.add_column('gym_exercises',
                  sa.Column('secondary_muscle_groups', sa.JSON(), nullable=True))

    bind = op.get_bind()
    for name, (equipment, bar_weight, secondary) in SEED.items():
        bind.execute(
            sa.text('UPDATE gym_exercises '
                    'SET equipment = :equipment, bar_weight = :bar_weight, '
                    '    secondary_muscle_groups = CAST(:secondary AS JSON) '
                    'WHERE name = :name'),
            {'equipment': equipment, 'bar_weight': bar_weight,
             'secondary': json.dumps(secondary), 'name': name},
        )


def downgrade():
    op.drop_column('gym_exercises', 'secondary_muscle_groups')
    op.drop_column('gym_exercises', 'stack_kg')
    op.drop_column('gym_exercises', 'bar_weight')
    op.drop_column('gym_exercises', 'equipment')
```

- [ ] **Step 5: Apply the migration and verify both directions**

Run: `PYTHONPATH=. python -m flask --app app db upgrade`
Expected: `Running upgrade d98add219b32 -> a1c4e8b20f31`

Run: `PYTHONPATH=. python -m flask --app app db downgrade && PYTHONPATH=. python -m flask --app app db upgrade`
Expected: a clean downgrade followed by a clean upgrade, no traceback.

- [ ] **Step 6: Run the test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_equipment.py -v`
Expected: PASS (4 passed, or 3 passed + 1 skipped if the dev catalogue lacks the seeded names)

- [ ] **Step 7: Carry the facts to a partner's cloned exercise**

In `personal_apps/features/gym/sharing.py`, the `Exercise(...)` construction around line 88 currently copies `muscle_group` and `is_unilateral` with a comment explaining that `weight_increment` deliberately does not travel. Add the new facts to what travels — they describe the machine, not the person:

```python
            is_unilateral=leader_exercise.is_unilateral,
            equipment=leader_exercise.equipment,
            bar_weight=leader_exercise.bar_weight,
            stack_kg=leader_exercise.stack_kg,
            secondary_muscle_groups=leader_exercise.secondary_muscle_groups,
```

Make the identical addition in `personal_apps/scripts/copy_templates.py`, where the same clone happens beside `weight_increment=source_exercise.weight_increment`:

```python
                equipment=source_exercise.equipment,
                bar_weight=source_exercise.bar_weight,
                stack_kg=source_exercise.stack_kg,
                secondary_muscle_groups=source_exercise.secondary_muscle_groups,
```

- [ ] **Step 8: Test that the facts travel**

Append to `personal_apps/tests/test_gym_equipment.py`:

```python
def test_cloned_partner_exercise_inherits_equipment_facts():
    """A shared workout clones the leader's exercise into the follower's
    catalogue. Equipment is a property of the machine, so it travels --
    unlike weight_increment, which is per-person and deliberately does not."""
    import inspect
    from features.gym import sharing
    source = inspect.getsource(sharing)
    for field in ('equipment=leader_exercise.equipment',
                  'bar_weight=leader_exercise.bar_weight',
                  'stack_kg=leader_exercise.stack_kg',
                  'secondary_muscle_groups=leader_exercise.secondary_muscle_groups'):
        assert field in source, field
    assert 'weight_increment=leader_exercise' not in source, \
        'increments are per-person and must not be copied'
```

- [ ] **Step 9: Run the full gym suite**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass, no new failures.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/a1c4e8b20f31_add_exercise_equipment_facts.py personal_apps/features/gym/sharing.py personal_apps/scripts/copy_templates.py personal_apps/tests/test_gym_equipment.py
git commit -m "feat(gym): record how each exercise is actually loaded"
```

---

### Task 2: Session bodyweight, notes and the pain flag

**Files:**
- Modify: `personal_apps/models.py:199-260` (`WorkoutSession`, `SessionExercise`)
- Create: `personal_apps/migrations/versions/b2d5f9c31a42_add_session_notes_bodyweight_pain.py`
- Test: `personal_apps/tests/test_gym_session_fields.py` (new)

**Interfaces:**
- Consumes: Task 1's migration as the Alembic parent (`a1c4e8b20f31`).
- Produces:
  - `WorkoutSession.bodyweight_kg: float | None`
  - `WorkoutSession.notes: str | None`
  - `SessionExercise.notes: str | None`
  - `SessionExercise.pain: bool` (NOT NULL, default `False`)

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_gym_session_fields.py`:

```python
"""Bodyweight, notes and the pain flag: everything a workout learns to
record about itself beyond the sets."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import Exercise, WorkoutSession, SessionExercise
from conftest import _admin_id


@pytest.fixture()
def temp_session():
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Test Session Fields', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Test Session', user_id=_admin_id(),
                                 started_at=dt.datetime.utcnow())
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.commit()
        ids = (session.id, se.id, exercise.id)
    yield ids
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, ids[0])
        if session is not None:
            db.session.delete(session)
        exercise = db.session.get(Exercise, ids[2])
        if exercise is not None:
            db.session.delete(exercise)
        db.session.commit()


def test_new_session_has_no_bodyweight_or_notes(temp_session):
    session_id, se_id, _ = temp_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg is None
        assert session.notes is None
        se = db.session.get(SessionExercise, se_id)
        assert se.notes is None
        assert se.pain is False


def test_session_fields_round_trip(temp_session):
    session_id, se_id, _ = temp_session
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        session.bodyweight_kg = 96.8
        session.notes = 'nach 8h Schicht'
        se = db.session.get(SessionExercise, se_id)
        se.notes = 'linke Schulter zwickt'
        se.pain = True
        db.session.commit()
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg == 96.8
        assert session.notes == 'nach 8h Schicht'
        se = db.session.get(SessionExercise, se_id)
        assert se.notes == 'linke Schulter zwickt'
        assert se.pain is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_session_fields.py -v`
Expected: FAIL — `AttributeError: 'WorkoutSession' object has no attribute 'bodyweight_kg'`

- [ ] **Step 3: Add the columns**

In `personal_apps/models.py`, in `WorkoutSession` after `structure_version`:

```python
    # What the lifter weighed on the day of this workout. Deliberately per
    # session rather than a daily weigh-in log: every question worth asking
    # of it ("what did I weigh when I lifted this") is a question about a
    # session, and a second table would need its own screen, its own history
    # and its own gaps. NULL whenever it was skipped, which is most of them.
    bodyweight_kg = db.Column(db.Float, nullable=True)
    notes         = db.Column(db.Text, nullable=True)
```

In `SessionExercise` after `mirrors_id`:

```python
    notes = db.Column(db.Text, nullable=True)
    # A twinge, flagged with one tap. Deliberately a boolean and not a
    # description: mid-set is the worst possible moment to ask for prose, and
    # "something hurt here" is already the whole signal a later reader needs
    # to go looking.
    pain  = db.Column(db.Boolean, nullable=False, default=False,
                      server_default=sa.false())
```

- [ ] **Step 4: Write the migration**

Create `personal_apps/migrations/versions/b2d5f9c31a42_add_session_notes_bodyweight_pain.py`:

```python
"""add bodyweight, notes and the pain flag to workouts

Revision ID: b2d5f9c31a42
Revises: a1c4e8b20f31
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2d5f9c31a42'
down_revision = 'a1c4e8b20f31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_workout_sessions', sa.Column('bodyweight_kg', sa.Float(), nullable=True))
    op.add_column('gym_workout_sessions', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('gym_session_exercises', sa.Column('notes', sa.Text(), nullable=True))
    # server_default: NOT NULL against a table with rows.
    op.add_column('gym_session_exercises',
                  sa.Column('pain', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade():
    op.drop_column('gym_session_exercises', 'pain')
    op.drop_column('gym_session_exercises', 'notes')
    op.drop_column('gym_workout_sessions', 'notes')
    op.drop_column('gym_workout_sessions', 'bodyweight_kg')
```

- [ ] **Step 5: Apply the migration**

Run: `PYTHONPATH=. python -m flask --app app db upgrade`
Expected: `Running upgrade a1c4e8b20f31 -> b2d5f9c31a42`

- [ ] **Step 6: Run the test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_session_fields.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/b2d5f9c31a42_add_session_notes_bodyweight_pain.py personal_apps/tests/test_gym_session_fields.py
git commit -m "feat(gym): let a workout record bodyweight, notes and a twinge"
```

---

### Task 3: Export v2 payload

**Files:**
- Create: `personal_apps/features/gym/export.py`
- Modify: `personal_apps/features/gym/routes.py:2124-2189` (`gym_export` delegates to the new module)
- Test: `personal_apps/tests/test_gym_export.py` (new)

**Interfaces:**
- Consumes: Task 1's `Exercise.equipment` / `bar_weight` / `stack_kg` / `secondary_muscle_groups`; Task 2's `WorkoutSession.bodyweight_kg` / `notes`, `SessionExercise.notes` / `pain`.
- Produces:
  - `export.SCHEMA_VERSION: int` = `2`
  - `export.weight_convention(equipment: str, is_unilateral: bool) -> str` — one of `'total'`, `'per_dumbbell'`, `'per_side'`
  - `export.set_payload(session_set) -> dict`
  - `export.exercise_payload(session_exercise) -> dict`
  - `export.session_payload(session) -> dict`
  - `export.build_payload(sessions: list, requested_session_ids: list[int], exported_at: datetime) -> dict`

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_gym_export.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.gym.export'`

- [ ] **Step 3: Write the export module**

Create `personal_apps/features/gym/export.py`:

```python
"""The JSON an external coaching tool reads.

Schema v2. The break from v1 is small but real: `is_deload` became
`deload`, and every exercise now carries what the logged weight physically
means (`weight_convention`) plus what the machine can actually be loaded
to (`increment_kg` or `stack_kg`). A reader that guesses at either of
those recommends weights that cannot be selected.

This module takes ORM rows and returns plain dicts. It holds no queries
and no request handling, so the contract can be tested without a database
or an HTTP client -- which is the point, because the contract is the part
that must not drift.
"""

SCHEMA_VERSION = 2


def _stamp(value):
    """ISO 8601 UTC, matching v1's format exactly."""
    return value.isoformat() + 'Z' if value is not None else None


def weight_convention(equipment, is_unilateral):
    """What the logged number means, derived rather than stored.

    Two orthogonal facts already answer this: how the exercise is loaded,
    and whether the number is one side's share. Storing a third field that
    restates their combination would let it disagree with them -- and
    volume is computed from is_unilateral alone (stats.set_volume), so the
    stored value would be the one that is wrong.

    The contract's fourth value, `per_arm`, is never emitted: nothing in
    this app distinguishes "one side at a time" from "both at once", and
    both double the volume identically.
    """
    if not is_unilateral:
        return 'total'
    return 'per_dumbbell' if equipment == 'dumbbell' else 'per_side'


def set_payload(session_set):
    return {
        'position': session_set.position,
        'weight': session_set.weight,
        'reps': session_set.reps,
        'completed': session_set.completed,
        # completed_at is cleared whenever a set stops being completed, so
        # this is null exactly for sets that never happened.
        'finished_at': _stamp(session_set.completed_at),
    }


def exercise_payload(session_exercise):
    exercise = session_exercise.exercise
    stack_kg = exercise.stack_kg or None
    return {
        'exercise_id': exercise.id,
        'exercise_name': exercise.name,
        'muscle_group': exercise.muscle_group,
        'secondary_muscle_groups': exercise.secondary_muscle_groups or [],
        'equipment': exercise.equipment,
        'weight_convention': weight_convention(exercise.equipment, exercise.is_unilateral),
        'bar_weight': exercise.bar_weight,
        # Mutually exclusive by contract: real stops are a complete answer,
        # and a step size beside them would be a second, coarser one.
        'increment_kg': None if stack_kg else exercise.weight_increment,
        'stack_kg': stack_kg,
        'position': session_exercise.position,
        'replaces': (session_exercise.replaces.exercise.name
                     if session_exercise.replaces else None),
        'replaced_by': (session_exercise.replaced_by.exercise.name
                        if session_exercise.replaced_by else None),
        'rest_seconds': session_exercise.rest_seconds,
        'notes': session_exercise.notes or '',
        'pain': bool(session_exercise.pain),
        'skipped': session_exercise.skipped,
        'sets': [set_payload(s) for s in session_exercise.sets],
    }


def session_payload(session):
    return {
        'id': session.id,
        'name': session.name,
        'template_name': session.template.name if session.template else None,
        'started_at': _stamp(session.started_at),
        'finished_at': _stamp(session.finished_at),
        'deload': session.is_deload,
        # Kept beside the boolean: how deep a deload went is not recoverable
        # from "it was one".
        'deload_pct': session.deload_pct,
        'bodyweight_kg': session.bodyweight_kg,
        'notes': session.notes or '',
        'exercises': [exercise_payload(se) for se in session.exercises],
    }


def build_payload(sessions, requested_session_ids, exported_at):
    """`range` is derived from what actually came back, not from what was
    asked for. The route is id-picked -- Verlauf's 30/90-day presets are a
    client-side bulk-check and no date range ever reaches the server -- so
    a range echoing the request would be inventing one. requested_session_ids
    stays beside it as the only record of the gap between asked and
    delivered.
    """
    dates = sorted(s.started_at.date() for s in sessions)
    return {
        'schema_version': SCHEMA_VERSION,
        'exported_at': _stamp(exported_at),
        'range': {
            'from': dates[0].isoformat() if dates else None,
            'to': dates[-1].isoformat() if dates else None,
        },
        'requested_session_ids': requested_session_ids,
        'sessions': [session_payload(s) for s in sessions],
    }
```

- [ ] **Step 4: Point the route at it**

In `personal_apps/features/gym/routes.py`, replace the `payload = {...}` literal inside `gym_export` (lines 2153-2184) with:

```python
    payload = export.build_payload(sessions, session_ids, dt.datetime.utcnow())
```

Extend the route's docstring with a sentence naming the schema:

```python
    list, never a date range). Full detail (every set, not just aggregates)
    so nothing useful is thrown away up front. Both original and substitute
    SessionExercise rows are exported (mirroring what a finished session's
    own detail view already shows -- see session_detail's visible_exercises
    computation), each carrying replaces/replaced_by exercise names so a
    swap is fully traceable. The payload shape is schema v2 and lives in
    features/gym/export.py."""
```

Add the import beside the module's existing `from features.gym import ...` lines (near the top of the file):

```python
from features.gym import export
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_export.py -v`
Expected: PASS (17 passed)

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/export.py personal_apps/features/gym/routes.py personal_apps/tests/test_gym_export.py
git commit -m "feat(gym): export what the weight number actually means"
```

---

### Task 4: Equipment fields in the exercise forms

**Files:**
- Modify: `personal_apps/features/gym/routes.py:2650-2702` (`gym_add_exercise`, `gym_update_exercise`), plus the `_to_increment` helper's neighbourhood for two new parsers
- Modify: `personal_apps/features/gym/routes.py` — the `gym_uebungen` and `exercise_detail` render calls, to pass `equipment_labels` and `muscle_groups`
- Modify: `personal_apps/templates/gym/exercise_detail.html:305-320` (edit sheet)
- Modify: `personal_apps/templates/gym/uebungen.html:188-201` (add form)
- Test: `personal_apps/tests/test_gym_equipment.py` (extend)

**Interfaces:**
- Consumes: `models.EQUIPMENT_TYPES`, `models.EQUIPMENT_LABELS`, `models.MUSCLE_GROUPS`, the Task 1 columns.
- Produces:
  - `routes._to_stack_steps(raw: str) -> list[float] | None`
  - `routes._clean_equipment(raw: str, current: str = 'stack') -> str`
  - `routes._clean_secondary_groups(values: list[str], primary: str | None) -> list[str] | None`
  - Form field names: `equipment`, `bar_weight`, `stack_kg`, `secondary_muscle_groups` (multi)

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_equipment.py`:

```python
def test_stack_steps_parser_accepts_a_typed_list():
    from features.gym.routes import _to_stack_steps
    assert _to_stack_steps('5, 13,21 , 29') == [5.0, 13.0, 21.0, 29.0]
    assert _to_stack_steps('5; 13') == [5.0, 13.0]
    assert _to_stack_steps('21, 5, 13') == [5.0, 13.0, 21.0], 'sorted ascending'
    assert _to_stack_steps('') is None
    assert _to_stack_steps('   ') is None
    assert _to_stack_steps('abc') is None
    assert _to_stack_steps('5, abc, 13') == [5.0, 13.0], 'junk entries dropped'


def test_equipment_parser_rejects_unknown_values():
    from features.gym.routes import _clean_equipment
    assert _clean_equipment('dumbbell') == 'dumbbell'
    assert _clean_equipment('barbell') == 'stack', 'unknown falls back to current'
    assert _clean_equipment('barbell', current='plate_loaded') == 'plate_loaded'
    assert _clean_equipment('') == 'stack'


def test_secondary_groups_parser_filters_and_dedupes():
    from features.gym.routes import _clean_secondary_groups
    assert _clean_secondary_groups(['Trizeps', 'Schultern'], 'Brust') == ['Trizeps', 'Schultern']
    assert _clean_secondary_groups(['Trizeps', 'Trizeps'], None) == ['Trizeps']
    assert _clean_secondary_groups(['Brust', 'Trizeps'], 'Brust') == ['Trizeps'], \
        'the primary group is not also a secondary one'
    assert _clean_secondary_groups(['Erfundenes'], None) is None
    assert _clean_secondary_groups([], None) is None


def test_add_form_persists_equipment_facts(client):
    """The catalogue's add form is the only place a brand new exercise gets
    its equipment, so it must carry every field the edit sheet does."""
    response = client.post('/gym/exercises/add', data={
        'name': 'ZZ Form Equipment',
        'muscle_group': 'Brust',
        'equipment': 'plate_loaded',
        'bar_weight': '20',
        'stack_kg': '',
        'secondary_muscle_groups': ['Trizeps', 'Schultern'],
    }, follow_redirects=False)
    assert response.status_code == 302
    with flask_app.app_context():
        row = Exercise.query.filter_by(name='ZZ Form Equipment').first()
        assert row is not None
        assert row.equipment == 'plate_loaded'
        assert row.bar_weight == 20.0
        assert row.stack_kg is None
        assert row.secondary_muscle_groups == ['Trizeps', 'Schultern']
        db.session.delete(row)
        db.session.commit()


def test_update_form_persists_stack_steps(client, temp_exercise):
    response = client.post(f'/gym/exercises/{temp_exercise}/update', data={
        'name': 'ZZ Test Equipment',
        'muscle_group': 'Rücken',
        'equipment': 'stack',
        'bar_weight': '',
        'stack_kg': '5, 13, 21, 29',
        'secondary_muscle_groups': ['Bizeps'],
    }, follow_redirects=False)
    assert response.status_code == 302
    with flask_app.app_context():
        row = db.session.get(Exercise, temp_exercise)
        assert row.equipment == 'stack'
        assert row.bar_weight is None
        assert row.stack_kg == [5.0, 13.0, 21.0, 29.0]
        assert row.secondary_muscle_groups == ['Bizeps']
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_equipment.py -v`
Expected: FAIL — `ImportError: cannot import name '_to_stack_steps' from 'features.gym.routes'`

- [ ] **Step 3: Add the parsers**

In `personal_apps/features/gym/routes.py`, beside the existing `_to_increment` helper:

```python
def _clean_equipment(raw, current='stack'):
    """An unknown value keeps whatever the exercise already had. The form
    only ever submits the three real values; anything else is a hand-rolled
    request, and silently widening the column's vocabulary from one of those
    would break the export's derivation table."""
    value = (raw or '').strip()
    return value if value in EQUIPMENT_TYPES else current


def _to_stack_steps(raw):
    """The real stops of an uneven stack, typed as a list.

    Comma or semicolon separated, sorted ascending, junk dropped. Empty
    means None rather than [] -- an empty list would read as "this machine
    has no positions", and the column's whole meaning is "NULL: steps
    evenly, ask weight_increment instead".
    """
    steps = []
    for chunk in (raw or '').replace(';', ',').split(','):
        chunk = chunk.strip().replace(',', '.')
        if not chunk:
            continue
        try:
            value = float(chunk)
        except ValueError:
            continue
        if value > 0:
            steps.append(value)
    return sorted(set(steps)) or None


def _clean_secondary_groups(values, primary):
    """Known groups only, in the order given, primary removed. None when
    nothing is left -- the column treats NULL and [] the same and NULL is
    the cheaper of the two to store."""
    seen = []
    for value in values or []:
        value = (value or '').strip()
        if value in MUSCLE_GROUPS and value != primary and value not in seen:
            seen.append(value)
    return seen or None
```

Make sure `EQUIPMENT_TYPES` is imported in that file's `from models import ...` line, alongside `MUSCLE_GROUPS`.

- [ ] **Step 4: Wire the parsers into both routes**

In `gym_add_exercise`, extend the `Exercise(...)` construction:

```python
    muscle_group = _clean_muscle_group(request.form.get('muscle_group', ''))
    exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
        equipment=_clean_equipment(request.form.get('equipment', '')),
        bar_weight=_to_increment(request.form.get('bar_weight', '')),
        stack_kg=_to_stack_steps(request.form.get('stack_kg', '')),
        secondary_muscle_groups=_clean_secondary_groups(
            request.form.getlist('secondary_muscle_groups'), muscle_group),
        user_id=current_user_id(),
    )
```

In `gym_update_exercise`, after the existing `exercise.is_unilateral = ...` line:

```python
    exercise.equipment = _clean_equipment(request.form.get('equipment', ''),
                                          current=exercise.equipment)
    exercise.bar_weight = _to_increment(request.form.get('bar_weight', ''))
    exercise.stack_kg = _to_stack_steps(request.form.get('stack_kg', ''))
    exercise.secondary_muscle_groups = _clean_secondary_groups(
        request.form.getlist('secondary_muscle_groups'), exercise.muscle_group)
```

- [ ] **Step 5: Pass the labels to both templates**

Find the `render_template` call in `gym_uebungen` and in `exercise_detail` and add:

```python
        equipment_labels=EQUIPMENT_LABELS,
```

`muscle_groups` is already passed to both. Import `EQUIPMENT_LABELS` from `models` in the same line as `EQUIPMENT_TYPES`.

- [ ] **Step 6: Add the fields to the edit sheet**

In `personal_apps/templates/gym/exercise_detail.html`, between the Schrittweite field (ends line 314) and the unilateral checkbox (line 315):

```html
      <div class="field grow">
        <label class="label" for="meta-equipment">Art</label>
        <select id="meta-equipment" name="equipment" class="select" data-role="equipment">
          {% for value, label in equipment_labels.items() %}
          <option value="{{ value }}" {{ 'selected' if exercise.equipment == value else '' }}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="field">
        <label class="label" for="meta-bar">Stangengewicht (kg)</label>
        <input type="number" id="meta-bar" name="bar_weight" step="0.5" min="0" class="input input--num"
               value="{{ '%g'|format(exercise.bar_weight) if exercise.bar_weight is not none else '' }}" placeholder="0">
      </div>
      {# Only meaningful on an uneven stack. Even ones are already described by
         Schrittweite above, and typing 5,10,15,... would be the same fact twice. #}
      <div class="field grow" data-role="stack-field"{% if exercise.equipment != 'stack' %} hidden{% endif %}>
        <label class="label" for="meta-stack">Stack-Stufen (kg, kommagetrennt)</label>
        <input type="text" id="meta-stack" name="stack_kg" class="input" inputmode="numeric"
               value="{{ exercise.stack_kg|join(', ') if exercise.stack_kg else '' }}" placeholder="5, 13, 21, 29">
      </div>
      <div class="field grow">
        <label class="label" for="meta-secondary">Sekundäre Muskelgruppen</label>
        <select id="meta-secondary" name="secondary_muscle_groups" class="select" multiple size="5">
          {% for mg in muscle_groups %}
          <option value="{{ mg }}" {{ 'selected' if exercise.secondary_muscle_groups and mg in exercise.secondary_muscle_groups else '' }}>{{ mg }}</option>
          {% endfor %}
        </select>
      </div>
```

Below the form's closing tag, inside the existing `{% block scripts %}` at the bottom of the file, add the one behaviour the fields need:

```javascript
// The stack-steps field only applies to a stack. Shown and hidden rather
// than always visible: on a dumbbell it is not an empty answer, it is a
// meaningless question.
document.addEventListener('change', function (e) {
    if (!e.target.matches || !e.target.matches('[data-role="equipment"]')) return;
    var field = document.querySelector('[data-role="stack-field"]');
    if (field) field.hidden = e.target.value !== 'stack';
});
```

- [ ] **Step 7: Add the same fields to the add form**

In `personal_apps/templates/gym/uebungen.html`, between the Schrittweite field (ends line 196) and the unilateral checkbox (line 197):

```html
      <div class="field grow">
        <label class="label" for="uebungen-add-equipment">Art</label>
        <select id="uebungen-add-equipment" name="equipment" class="select" data-role="equipment">
          {% for value, label in equipment_labels.items() %}
          <option value="{{ value }}" {{ 'selected' if value == 'stack' else '' }}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="field">
        <label class="label" for="uebungen-add-bar">Stangengewicht (kg)</label>
        <input type="number" id="uebungen-add-bar" name="bar_weight" step="0.5" min="0" class="input input--num" placeholder="0">
      </div>
      <div class="field grow" data-role="stack-field">
        <label class="label" for="uebungen-add-stack">Stack-Stufen (kg, kommagetrennt)</label>
        <input type="text" id="uebungen-add-stack" name="stack_kg" class="input" inputmode="numeric" placeholder="5, 13, 21, 29">
      </div>
      <div class="field grow">
        <label class="label" for="uebungen-add-secondary">Sekundäre Muskelgruppen</label>
        <select id="uebungen-add-secondary" name="secondary_muscle_groups" class="select" multiple size="5">
          {% for mg in muscle_groups %}
          <option value="{{ mg }}">{{ mg }}</option>
          {% endfor %}
        </select>
      </div>
```

Add the same `change` listener to this page's `{% block scripts %}`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_equipment.py -v`
Expected: PASS (all, including the three parser tests and the two form tests)

- [ ] **Step 9: Verify both forms in a browser**

Start the app on port 5001 and mint a session cookie (see `reference_personal_apps_local_run`), then use python-playwright at 390×844 to screenshot: `/gym/uebungen` with the add sheet open, and one exercise's detail page with the edit sheet open. Confirm the stack field hides when Art is switched away from Steckgewicht, and that nothing overflows horizontally.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/exercise_detail.html personal_apps/templates/gym/uebungen.html personal_apps/tests/test_gym_equipment.py
git commit -m "feat(gym): edit an exercise's equipment facts"
```

---

### Task 5: Bodyweight, notes and pain in the session UI

**Files:**
- Modify: `personal_apps/features/gym/routes.py` (two new POST routes beside `gym_update_session_exercise_rest`)
- Modify: `personal_apps/templates/gym/session_detail.html:86-145` (workout sheet)
- Modify: `personal_apps/templates/gym/session_detail.html:285-307` (per-exercise sheet)
- Test: `personal_apps/tests/test_gym_session_fields.py` (extend)

**Interfaces:**
- Consumes: Task 2's columns.
- Produces:
  - `POST /gym/sessions/<int:session_id>/meta` — form fields `bodyweight_kg`, `notes`
  - `POST /gym/session-exercises/<int:session_exercise_id>/meta` — form fields `notes`, `pain` (checkbox)

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_session_fields.py`:

```python
def test_session_meta_route_saves_bodyweight_and_notes(client, temp_session):
    session_id, _, _ = temp_session
    response = client.post(f'/gym/sessions/{session_id}/meta', data={
        'bodyweight_kg': '96,8',
        'notes': 'nach 8h Schicht',
    })
    assert response.status_code == 302
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg == 96.8, 'a German decimal comma is accepted'
        assert session.notes == 'nach 8h Schicht'


def test_blank_bodyweight_clears_it(client, temp_session):
    session_id, _, _ = temp_session
    client.post(f'/gym/sessions/{session_id}/meta', data={'bodyweight_kg': '96.8'})
    client.post(f'/gym/sessions/{session_id}/meta', data={'bodyweight_kg': ''})
    with flask_app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert session.bodyweight_kg is None


def test_exercise_meta_route_saves_note_and_pain(client, temp_session):
    _, se_id, _ = temp_session
    response = client.post(f'/gym/session-exercises/{se_id}/meta', data={
        'notes': 'linke Schulter zwickt',
        'pain': 'on',
    })
    assert response.status_code == 302
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.notes == 'linke Schulter zwickt'
        assert se.pain is True


def test_unchecked_pain_clears_the_flag(client, temp_session):
    _, se_id, _ = temp_session
    client.post(f'/gym/session-exercises/{se_id}/meta', data={'pain': 'on'})
    client.post(f'/gym/session-exercises/{se_id}/meta', data={'notes': ''})
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.pain is False


def test_meta_routes_refuse_another_users_workout(anon_client, temp_session):
    session_id, se_id, _ = temp_session
    assert anon_client.post(f'/gym/sessions/{session_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)
    assert anon_client.post(f'/gym/session-exercises/{se_id}/meta',
                            data={'notes': 'x'}).status_code in (302, 401, 403)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_session_fields.py -v`
Expected: FAIL — the POSTs return 404, so the first assertion on `response.status_code == 302` fails.

- [ ] **Step 3: Add the routes**

In `personal_apps/features/gym/routes.py`, beside `gym_update_session_exercise_rest` (search for that function and add below it). Both ownership helpers already exist in `features/gym/scope.py` — `owned_session` (line 37) and `owned_session_exercise` (line 51) — and both are already imported in routes.py:

```python
@gym_bp.route('/gym/sessions/<int:session_id>/meta', methods=['POST'])
@login_required
def gym_update_session_meta(session_id):
    """Bodyweight and a note for this workout. Both optional, both editable
    at any point -- during the session, or weeks later from Verlauf. The
    start path deliberately does not ask for either: a field between "start"
    and the first set is a field you skip anyway."""
    session = owned_session(session_id)
    session.bodyweight_kg = _to_increment(request.form.get('bodyweight_kg', ''))
    session.notes = (request.form.get('notes', '') or '').strip() or None
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session.id))


@gym_bp.route('/gym/session-exercises/<int:session_exercise_id>/meta', methods=['POST'])
@login_required
def gym_update_session_exercise_meta(session_exercise_id):
    """A note and a twinge flag, for this exercise in this workout. Both
    belong to the session rather than the catalogue: "shoulder pinched
    today" is not a property of the machine."""
    session_exercise = owned_session_exercise(session_exercise_id)
    session_exercise.notes = (request.form.get('notes', '') or '').strip() or None
    session_exercise.pain = request.form.get('pain') == 'on'
    db.session.commit()
    return redirect(url_for('gym.session_detail',
                            session_id=session_exercise.session_id))
```

`_to_increment` (routes.py:77) is already comma-tolerant and already returns `None` for blank, unparseable and non-positive input, which is exactly the bodyweight parsing this needs. Reuse it; do not write a second parser.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_session_fields.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Add the workout-sheet fields**

In `personal_apps/templates/gym/session_detail.html`, inside `<dialog id="sheet-session">`'s `.sheet__body`, above the "Pause beenden" form:

```html
    {# Inside the sheet, never on the start path: the workout begins with one
       tap and that stays true. Both fields are editable for as long as the
       session exists. #}
    <div class="sheet__group">
      <form method="post" action="{{ url_for('gym.gym_update_session_meta', session_id=session.id) }}">
        <div class="sheet__row">
          <label class="label" for="session-bodyweight">Körpergewicht (kg)</label>
          <input type="number" id="session-bodyweight" name="bodyweight_kg" step="0.1" min="0"
                 class="input input--num rest-form__input"
                 value="{{ '%g'|format(session.bodyweight_kg) if session.bodyweight_kg is not none else '' }}"
                 placeholder="—">
        </div>
        <div class="field grow">
          <label class="label" for="session-notes">Notiz</label>
          <input type="text" id="session-notes" name="notes" class="input"
                 value="{{ session.notes or '' }}" placeholder="z. B. nach 8h Schicht">
        </div>
        <button type="submit" class="btn btn--ghost btn--sm">Speichern</button>
      </form>
      <p class="sheet__note">Gilt für dieses Workout.</p>
    </div>
```

- [ ] **Step 6: Add the per-exercise fields**

In the same file, inside `<dialog id="sheet-ex-{{ se.id }}">`'s `.sheet__body`, directly after the Schrittweite group (which ends with its `<p class="sheet__note">Gilt für die Übung, nicht nur heute.</p>`):

```html
    {# The opposite lifetime to the increment above: a twinge and a note
       belong to this workout, not to the machine. #}
    <div class="sheet__group">
      <form method="post" action="{{ url_for('gym.gym_update_session_exercise_meta', session_exercise_id=se.id) }}">
        <label class="sheet__row">
          <input type="checkbox" name="pain" class="check" {{ 'checked' if se.pain else '' }}>
          <span class="check__text">Schmerz / Zwicken</span>
        </label>
        <div class="field grow">
          <label class="label" for="ex-notes-{{ se.id }}">Notiz</label>
          <input type="text" id="ex-notes-{{ se.id }}" name="notes" class="input"
                 value="{{ se.notes or '' }}" placeholder="—">
        </div>
        <button type="submit" class="btn btn--ghost btn--sm">Speichern</button>
      </form>
      <p class="sheet__note">Gilt nur für heute.</p>
    </div>
```

- [ ] **Step 7: Verify in a browser**

Screenshot at 390×844 via python-playwright: an active session's workout sheet and one exercise sheet. Confirm the pain checkbox and both notes render inside the sheets, that the session page's normal flow (tap row → sheet) is unchanged, and that no field overflows.

- [ ] **Step 8: Run the full suite and commit**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass.

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/session_detail.html personal_apps/tests/test_gym_session_fields.py
git commit -m "feat(gym): log bodyweight, a note and a twinge without leaving the sheet"
```

---

### Task 6: Snap suggestions to real stack stops

**Files:**
- Modify: `personal_apps/features/gym/stats.py:475-530` (`snap_to_stack`, and `deload_weight` / `_next_weight` honouring it)
- Modify: `personal_apps/features/gym/stats.py:102-140` (`PerformedExercise` carries `stack_kg`)
- Modify: `personal_apps/features/gym/routes.py:265-320, 900-930, 1680-1695` (pass the steps wherever `weight_increment` is passed today)
- Test: `personal_apps/tests/test_gym_stats.py` (extend)

**Interfaces:**
- Consumes: `Exercise.stack_kg` from Task 1.
- Produces:
  - `stats.snap_to_stack(weight: float, steps: list[float] | None, direction: str) -> float` — `direction` is `'down'` or `'up'`; returns `weight` unchanged when `steps` is falsy
  - `PerformedExercise.stack_kg: list[float] | None` (new trailing field, defaulted to `None`)

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_stats.py`:

```python
def test_snap_to_stack_returns_the_weight_when_there_are_no_steps():
    """Everything in this gym steps evenly, so this is the path almost every
    exercise takes: no stops recorded, increment logic untouched."""
    assert stats.snap_to_stack(42.0, None, 'down') == 42.0
    assert stats.snap_to_stack(42.0, [], 'up') == 42.0


def test_snap_to_stack_lands_on_a_real_stop():
    steps = [5, 13, 21, 29, 37, 45]
    assert stats.snap_to_stack(42.0, steps, 'down') == 37
    assert stats.snap_to_stack(42.0, steps, 'up') == 45
    assert stats.snap_to_stack(37.0, steps, 'down') == 37, 'an exact stop stays put'
    assert stats.snap_to_stack(37.0, steps, 'up') == 37


def test_snap_to_stack_clamps_at_the_ends():
    steps = [5, 13, 21]
    assert stats.snap_to_stack(2.0, steps, 'down') == 5, 'below the lightest stop'
    assert stats.snap_to_stack(99.0, steps, 'up') == 21, 'above the heaviest'


def test_deload_lands_on_a_real_stop_when_steps_are_known():
    """The bug this guards: 70 % of 69 on an 8 kg stack sitting on a 5 kg
    carriage is 48.3, and 48 is not a position the machine has."""
    steps = [5, 13, 21, 29, 37, 45, 53, 61, 69, 77]
    weight = stats.deload_weight(69.0, 70, 8, stack_kg=steps)
    assert weight in steps
    assert weight <= 69 * 0.7 + 0.001
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_stats.py -k stack -v`
Expected: FAIL — `AttributeError: module 'features.gym.stats' has no attribute 'snap_to_stack'`

- [ ] **Step 3: Implement the snapping**

In `personal_apps/features/gym/stats.py`, directly below `resolve_increment`:

```python
def snap_to_stack(weight, steps, direction):
    """The nearest real position of a machine whose stops are known.

    Almost nothing needs this: an evenly stepping stack is already fully
    described by its increment, and deload_weight's anchor-to-working-weight
    rule keeps even an offset grid (5, 13, 21 ...) honest without knowing the
    stops. It exists for the machine whose gaps are uneven, where counting
    increments from anywhere invents a position -- the first such exercise
    entered into the form computes correctly the same day instead of
    prescribing a weight nobody can select.

    `steps` falsy means the exercise has no recorded stops, and the weight
    passes through untouched.
    """
    if not steps:
        return weight
    ordered = sorted(steps)
    if direction == 'down':
        below = [s for s in ordered if s <= weight]
        return below[-1] if below else ordered[0]
    above = [s for s in ordered if s >= weight]
    return above[0] if above else ordered[-1]
```

Extend `deload_weight`'s signature and its final return. The existing body computes `steps` and returns `weight - steps * increment`; keep every line of that and snap the result:

```python
def deload_weight(weight, pct, increment, stack_kg=None):
```

and immediately before the existing return of the computed weight:

```python
    # A recorded stack overrides the increment grid: its stops are the only
    # positions that exist, and the grid is at best a good guess at them.
    return snap_to_stack(prescribed, stack_kg, 'down')
```

where `prescribed` is the local the function already computes. Do not change the anchoring or the ceil.

Add the field to `PerformedExercise`, after `weight_increment`:

```python
    # The machine's real stops, when they are uneven enough to be worth
    # recording. None on everything that steps evenly -- see snap_to_stack.
    stack_kg: Optional[Tuple] = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_stats.py -k stack -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Pass the steps from the routes**

`stats.deload_weight` is called from exactly three places in `personal_apps/features/gym/routes.py`. Each already has the `Exercise` row in scope, under the name given:

- **routes.py:279** — inside the seeded-deload set builder. The exercise row reaches this function alongside the increment; pass `stack_kg=exercise.stack_kg` (read the enclosing function's parameters and use its own name for that row).
- **routes.py:310** — `return {'weight': stats.deload_weight(last['weight'], pct, increment), ...}`. Same enclosing function's exercise row.
- **routes.py:1698** — `s.weight = stats.deload_weight(s.base_weight, pct, increment)` inside `gym_toggle_deload`. The row is `session_exercise.exercise` in that loop.

The single `PerformedExercise(...)` construction is at **routes.py:423**, where the row is the local `exercise`. Add as the last argument:

```python
        stack_kg=tuple(exercise.stack_kg) if exercise.stack_kg else None,
```

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass. Deload behaviour for every existing exercise is unchanged, because none of them has `stack_kg` set.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/features/gym/routes.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): prescribe weights a machine can actually make"
```

---

### Task 7: Prove it end to end

**Files:**
- Create: `<scratchpad>/export_v2_sample.py` (throwaway, not committed)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Generate a real 14-day export**

Write a scratchpad script that opens an app context, selects every finished session of the acting user whose `started_at` falls in the last 14 days, calls `export.build_payload` on them, and writes the JSON to the scratchpad directory:

```python
import datetime as dt
import json
import sys

sys.path.insert(0, '.')
from app import app
from features.gym import export
from models import WorkoutSession

CUTOFF_DAYS = 14

with app.app_context():
    since = dt.datetime.utcnow() - dt.timedelta(days=CUTOFF_DAYS)
    sessions = (WorkoutSession.query
                .filter(WorkoutSession.finished_at.isnot(None),
                        WorkoutSession.started_at >= since)
                .order_by(WorkoutSession.started_at.asc())
                .all())
    payload = export.build_payload(sessions, [s.id for s in sessions],
                                   dt.datetime.utcnow())
print(json.dumps(payload, indent=2, ensure_ascii=False))
```

Run: `PYTHONPATH=. python <scratchpad>/export_v2_sample.py > <scratchpad>/gym-export-v2-sample.json`

- [ ] **Step 2: Check the sample against the contract**

Read the generated file. Confirm by eye:
- `schema_version` is 2 and `range` holds two dates
- every exercise carries all 17 keys, including the ones that are `null`
- `weight_convention` is `per_dumbbell` on the dumbbell lifts, `per_side` on Chest Press / Preacher Curl (Machine, Good) / Lat Pulldown (Single Arm), `total` everywhere else
- `bar_weight` is 20 on Military Press and `null` elsewhere
- completed sets carry a `finished_at`, unfinished ones carry `null`

If the local dev database holds no sessions in the window, say so plainly and generate over the widest range that does have data instead of reporting an empty success.

- [ ] **Step 3: Show the user**

Report the sample's session count, date range, and one full exercise block. Note explicitly whether the dev database's data is real or dev junk, since the local database is disposable and its numbers mean nothing on their own.

- [ ] **Step 4: Run the whole suite one last time**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass.

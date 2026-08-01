# Per-exercise Weight Increment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each exercise carry its own weight increment (dumbbells 2 kg, a selectorised stack 9 kg, a bar 2.5 kg) and have the live stepper, the progression suggestion and the deload rounding all read it.

**Architecture:** One nullable `Float` column on `Exercise`, plus one pure resolver in `stats.py` that turns `(stored_value, is_unilateral)` into the step to use. `_next_weight()` and `deload_weight()` stop taking `is_unilateral` and take a resolved increment instead; every caller resolves first. NULL means "use 2.5, halved when unilateral", so an untouched catalogue behaves exactly as it does today.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate/Alembic, Jinja2, vanilla JS, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-gym-per-exercise-increment-design.md`. Read it before Task 1.
- Branch: `dev_personal`. Do **not** commit to `main`.
- All work is inside `personal_apps/`. Run every command from that directory.
- User-facing copy is **German**. Code, comments and identifiers are **English**.
- Column name is exactly `weight_increment` — not `default_weight_increment`.
- Fallback constant is exactly `stats.DEFAULT_INCREMENT = 2.5`.
- An explicit increment is used **literally**. Never halve it for unilateral exercises; halving applies only to the fallback.
- No per-session or per-template increment column. No visible step indicator on the live screen. The reps stepper stays at 1.
- Alembic head before this work is `a1e4c9d27f63`. The new revision's `down_revision` must be `a1e4c9d27f63`.
- The pure suite (`tests/test_gym_stats.py`, `tests/test_gym_analytics.py`) needs no database. `tests/test_gym_routes_smoke.py` needs MySQL80 running — if it is down, start the service before Tasks 5–7 rather than skipping the tests.

---

### Task 1: The resolver

The one place that decides what step an exercise uses. Pure, so it is testable before any column exists.

**Files:**
- Modify: `personal_apps/features/gym/stats.py:89` (constants block) and `:459` (above `_next_weight`)
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `stats.DEFAULT_INCREMENT` (float, `2.5`) and `stats.resolve_increment(increment, is_unilateral) -> float`. Every later task calls this rather than repeating the fallback.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_gym_stats.py`:

```python
def test_resolve_increment_falls_back_to_the_plate_pair():
    assert stats.resolve_increment(None, False) == 2.5


def test_resolve_increment_halves_the_fallback_for_unilateral_work():
    # One side at a time, so half the smallest pair of plates.
    assert stats.resolve_increment(None, True) == 1.25


def test_resolve_increment_takes_an_explicit_value_literally():
    # A selectorised stack moves in 9 kg steps; nothing about 2.5 applies.
    assert stats.resolve_increment(9.0, False) == 9.0


def test_resolve_increment_does_not_halve_an_explicit_unilateral_value():
    # The discriminating case for the whole feature: the live screen labels
    # this field "kg je Seite", so 2.0 already IS the per-side step. Halving it
    # would dial 1.0 kg on a pair of dumbbells that only exist in 2 kg jumps.
    assert stats.resolve_increment(2.0, True) == 2.0


def test_resolve_increment_treats_zero_as_unset():
    # A step of zero would freeze the stepper, so it collapses to the fallback
    # rather than being honoured.
    assert stats.resolve_increment(0, False) == 2.5
    assert stats.resolve_increment(0, True) == 1.25
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_gym_stats.py -k resolve_increment -v
```

Expected: 5 errors, `AttributeError: module 'features.gym.stats' has no attribute 'resolve_increment'`.

- [ ] **Step 3: Add the constant**

In `personal_apps/features/gym/stats.py`, the constants block currently ends:

```python
NO_GROUP_LABEL = 'Ohne Muskelgruppe'
```

Add directly beneath it:

```python
# The smallest pair of plates on most bars, and the step for any exercise that
# has no increment of its own. Halved for a unilateral lift, which moves one
# side at a time.
DEFAULT_INCREMENT = 2.5
```

- [ ] **Step 4: Add the resolver**

In the same file, insert immediately **above** `def _next_weight(...)`:

```python
def resolve_increment(increment, is_unilateral):
    """The smallest loadable jump for one exercise.

    An explicit per-exercise value is taken literally: it is already the number
    that moves when you tap, per side when the lift is unilateral (the live
    screen labels that field `kg je Seite`). Halving survives only as the
    fallback, so an exercise with nothing set behaves exactly as the whole app
    did before increments existed.

    Zero collapses to the fallback along with None -- a step of zero would
    freeze the stepper, so it is never a value worth honouring.
    """
    if increment:
        return increment
    return DEFAULT_INCREMENT / 2 if is_unilateral else DEFAULT_INCREMENT
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_gym_stats.py -k resolve_increment -v
```

Expected: `5 passed`.

- [ ] **Step 6: Run the whole pure suite**

```bash
python -m pytest tests/test_gym_stats.py tests/test_gym_analytics.py -q
```

Expected: `162 passed` (157 before this task, plus the 5 new ones).

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): resolve a per-exercise weight increment"
```

---

### Task 2: The column

**Files:**
- Modify: `personal_apps/models.py:157`
- Create: `personal_apps/migrations/versions/c7d3e91a4f28_add_weight_increment_to_exercises.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Exercise.weight_increment` — `float | None`. Later tasks read and write this attribute.

- [ ] **Step 1: Add the column to the model**

In `personal_apps/models.py`, the `Exercise` class currently reads:

```python
    default_rest_seconds = db.Column(db.Integer, nullable=True)
    is_unilateral        = db.Column(db.Boolean, nullable=False, default=False)  # logged weight/reps are per side (e.g. one-arm curls); volume must be doubled
```

Change to:

```python
    default_rest_seconds = db.Column(db.Integer, nullable=True)
    weight_increment     = db.Column(db.Float, nullable=True)  # smallest loadable jump on this equipment (dumbbells 2, a stack often 9); NULL means use stats.DEFAULT_INCREMENT
    is_unilateral        = db.Column(db.Boolean, nullable=False, default=False)  # logged weight/reps are per side (e.g. one-arm curls); volume must be doubled
```

Note there is no `default_` prefix: unlike `default_rest_seconds`, this value is never copied onto a session or template row, so it is not a default *for* anything.

- [ ] **Step 2: Write the migration**

Create `personal_apps/migrations/versions/c7d3e91a4f28_add_weight_increment_to_exercises.py`:

```python
"""add weight_increment to exercises

Revision ID: c7d3e91a4f28
Revises: a1e4c9d27f63
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d3e91a4f28'
down_revision = 'a1e4c9d27f63'
branch_labels = None
depends_on = None


def upgrade():
    # Deliberately no server_default and no backfill: NULL is the correct
    # resting state and means "use stats.DEFAULT_INCREMENT", so every existing
    # exercise keeps the behaviour it had before this column existed.
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('weight_increment', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_column('weight_increment')
```

- [ ] **Step 3: Confirm the revision chain has a single head**

```bash
python -m flask --app app db heads
```

Expected: exactly one line, `c7d3e91a4f28 (head)`. If two heads print, the `down_revision` is wrong — it must be `a1e4c9d27f63`.

- [ ] **Step 4: Apply the migration**

```bash
python -m flask --app app db upgrade
```

Expected: `Running upgrade a1e4c9d27f63 -> c7d3e91a4f28, add weight_increment to exercises`.

Needs MySQL80 running. If it is not, start the service and re-run.

- [ ] **Step 5: Verify the column exists and every row is NULL**

```bash
python -c "from app import app; from models import Exercise; app.app_context().push(); print(Exercise.query.count(), 'exercises,', Exercise.query.filter(Exercise.weight_increment.isnot(None)).count(), 'with an increment')"
```

Expected: `N exercises, 0 with an increment`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/c7d3e91a4f28_add_weight_increment_to_exercises.py
git commit -m "feat(gym): add weight_increment to exercises"
```

---

### Task 3: The consumers

`_next_weight()` and `deload_weight()` take `is_unilateral` today for the sole purpose of picking a step. Both swap it for a resolved increment; all four call sites resolve first.

**Files:**
- Modify: `personal_apps/features/gym/stats.py:111` (dataclass), `:459` (`_next_weight`), `:465` (`deload_weight`), `:587` (`suggested_weight`)
- Modify: `personal_apps/features/gym/routes.py:242-247`, `:362-376`, `:1191-1202`
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `stats.resolve_increment(increment, is_unilateral)`, `Exercise.weight_increment`.
- Produces: `stats._next_weight(weight, increment)`, `stats.deload_weight(weight, pct, increment)`, and `stats.PerformedExercise(..., weight_increment=None)`.

- [ ] **Step 1: Update the existing tests to the new signature**

In `personal_apps/tests/test_gym_stats.py`, seven functions pass the `is_unilateral` boolean positionally. Replace all seven with:

```python
def test_deload_weight_takes_the_percentage_and_rounds_down_to_a_plate():
    # 80 * 0.70 = 56.0, which is not loadable in 2.5 kg steps -> 55.0
    assert stats.deload_weight(80.0, 70, 2.5) == 55.0


def test_deload_weight_rounds_down_not_to_nearest():
    # 100 * 0.70 = 70.0 exactly; 90 * 0.70 = 63.0 -> 62.5, not 65.0
    assert stats.deload_weight(100.0, 70, 2.5) == 70.0
    assert stats.deload_weight(90.0, 70, 2.5) == 62.5


def test_deload_weight_rounds_down_even_when_nearest_would_round_up():
    # The discriminating case: 81 * 0.70 = 56.7, which is 22.68 increments of
    # 2.5 kg. Rounding to nearest would give 23 increments (57.5 kg) -- heavier
    # than the 81 kg lift's own prescription implies. Flooring gives 55.0.
    # Every other case in this file has a remainder below 0.5, where floor and
    # round-to-nearest agree, so only this one proves the direction.
    assert stats.deload_weight(81.0, 70, 2.5) == 55.0


def test_deload_weight_uses_the_half_step_for_unilateral():
    # 20 * 0.70 = 14.0 -> 13.75 in 1.25 kg steps, not 12.5 in 2.5 kg steps
    assert stats.deload_weight(20.0, 70, stats.resolve_increment(None, True)) == 13.75


def test_deload_weight_leaves_a_bodyweight_set_alone():
    assert stats.deload_weight(0.0, 70, 2.5) == 0.0


def test_deload_weight_never_floors_a_light_weight_to_zero():
    # 2.5 * 0.70 = 1.75 -> would floor to 0.0; one increment is the minimum.
    assert stats.deload_weight(2.5, 70, 2.5) == 2.5
    assert stats.deload_weight(1.25, 70, 1.25) == 1.25


def test_deload_weight_preserves_the_shape_of_a_ramped_session():
    session = [80.0, 80.0, 75.0]
    assert [stats.deload_weight(w, 70, 2.5) for w in session] == [55.0, 55.0, 52.5]
```

- [ ] **Step 2: Add the new tests**

Append to `personal_apps/tests/test_gym_stats.py`:

```python
def test_deload_weight_floors_onto_a_stack_machines_grid():
    # A 90 kg stack at 70 % is 63.0, which is exactly seven 9 kg plates. The
    # old 2.5 grid would have prescribed 62.5 -- a weight the machine cannot
    # produce at all.
    assert stats.deload_weight(90.0, 70, 9.0) == 63.0
    # 100 * 0.70 = 70.0 is not on the 9 kg grid: floor to 63.0, never 72.0.
    assert stats.deload_weight(100.0, 70, 9.0) == 63.0


def test_deload_weight_never_floors_below_one_stack_plate():
    # 9 * 0.70 = 6.3 -> would floor to 0.0; the lightest real position is 9.
    assert stats.deload_weight(9.0, 70, 9.0) == 9.0


def test_next_weight_adds_the_exercises_own_increment():
    assert stats._next_weight(81.0, 9.0) == 90.0
    assert stats._next_weight(80.0, 2.5) == 82.5


def test_session_report_suggests_the_exercises_own_increment():
    # Same stagnation setup as the 82.5 case above, but on a 9 kg stack: the
    # advice has to name a weight the machine can actually make.
    history = [perf([(72.0, 8)], weight_increment=9.0, started_at=day(0), session_id=1)]
    history += [
        perf([(63.0, 8)], weight_increment=9.0, started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(63.0, 8)], weight_increment=9.0, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['advice'][0]['stuck_at'] == 63.0
    assert report['advice'][0]['suggested_weight'] == 72.0
```

Also extend the `perf()` helper at the top of the file so those tests can set the field. It currently reads:

```python
def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1,
         is_deload=False):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]."""
    return stats.PerformedExercise(
        exercise_id=exercise_id,
        name=name,
        muscle_group=muscle_group,
        is_unilateral=is_unilateral,
        position=position,
        session_id=session_id,
        started_at=started_at or dt.datetime(2026, 7, 1, 18, 0),
        sets=tuple(sets),
        is_deload=is_deload,
    )
```

Change to:

```python
def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1,
         is_deload=False, weight_increment=None):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]."""
    return stats.PerformedExercise(
        exercise_id=exercise_id,
        name=name,
        muscle_group=muscle_group,
        is_unilateral=is_unilateral,
        position=position,
        session_id=session_id,
        started_at=started_at or dt.datetime(2026, 7, 1, 18, 0),
        sets=tuple(sets),
        is_deload=is_deload,
        weight_increment=weight_increment,
    )
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_gym_stats.py -q
```

Expected: failures — `TypeError: PerformedExercise.__init__() got an unexpected keyword argument 'weight_increment'`, plus wrong values from the stack-machine deload cases (`deload_weight(90.0, 70, 9.0)` currently returns `62.5`, because the third argument is still read as a truthy `is_unilateral`).

- [ ] **Step 4: Add the dataclass field**

In `personal_apps/features/gym/stats.py`, `PerformedExercise` currently ends:

```python
    # True when this row was performed in a deliberately light session. Every
    # function below that makes a *judgement* (records, stagnation, averages)
    # drops these rows via _progression_rows(); every function that reports
    # what actually happened (tonnage, balance, consistency) keeps them.
    # Defaulted so callers predating the flag keep working.
    is_deload: bool = False
```

Add beneath it:

```python
    # The exercise's own loadable step, as stored -- None when it has none and
    # the default applies. Carried on the row rather than looked up because
    # this module never touches the ORM. Defaulted for the same reason
    # is_deload is.
    weight_increment: Optional[float] = None
```

`Optional` is already imported by this module.

- [ ] **Step 5: Rewrite the two functions**

They currently read:

```python
def _next_weight(weight, is_unilateral):
    """The smallest honest jump up. 2.5 kg is the smallest pair of plates on
    most bars; a unilateral lift moves one side at a time, so half that."""
    return weight + (1.25 if is_unilateral else 2.5)


def deload_weight(weight, pct, is_unilateral):
    """`pct` of a working weight, rounded DOWN to a loadable increment.

    Down, not to nearest: rounding a deload up makes it heavier than
    prescribed, which is the one direction that defeats the point. The
    increments mirror _next_weight() -- 2.5 kg is the smallest pair of plates
    on most bars, and a unilateral lift moves one side at a time.

    Applied per set by the caller, never to the top set alone, so any ramping
    or drop-off in the session's shape survives the deload.
    """
    if weight <= 0:
        return weight          # a bodyweight set stays bodyweight
    step = 1.25 if is_unilateral else 2.5
    return max(step, math.floor(weight * pct / 100.0 / step) * step)
```

Replace both with:

```python
def _next_weight(weight, increment):
    """The smallest honest jump up: one loadable step on this exercise's own
    equipment. Callers resolve `increment` through resolve_increment()."""
    return weight + increment


def deload_weight(weight, pct, increment):
    """`pct` of a working weight, rounded DOWN to a loadable increment.

    Down, not to nearest: rounding a deload up makes it heavier than
    prescribed, which is the one direction that defeats the point. The grid is
    anchored at 0, which is what a stack machine actually offers -- 90 kg at
    70 % on a 9 kg stack lands on 63, a real position.

    Applied per set by the caller, never to the top set alone, so any ramping
    or drop-off in the session's shape survives the deload.
    """
    if weight <= 0:
        return weight          # a bodyweight set stays bodyweight
    return max(increment, math.floor(weight * pct / 100.0 / increment) * increment)
```

- [ ] **Step 6: Update the suggestion call site**

In the same file, `suggested_weight` currently reads:

```python
                'suggested_weight': _next_weight(weight, row.is_unilateral),
```

Change to:

```python
                'suggested_weight': _next_weight(
                    weight, resolve_increment(row.weight_increment, row.is_unilateral)),
```

- [ ] **Step 7: Run the pure suite**

```bash
python -m pytest tests/test_gym_stats.py tests/test_gym_analytics.py -q
```

Expected: `166 passed`. The two pre-existing suggestion tests (`suggested_weight == 82.5` and `== 21.25`) must still pass untouched — they build rows with `weight_increment=None`, so the fallback answers exactly as before.

- [ ] **Step 8: Populate the field from the ORM**

In `personal_apps/features/gym/routes.py`, `_to_performed` currently reads:

```python
def _to_performed(session_exercise, completed_sets):
    exercise = session_exercise.exercise
    return stats.PerformedExercise(
        exercise_id=session_exercise.exercise_id,
        name=exercise.name,
        muscle_group=exercise.muscle_group,
        is_unilateral=exercise.is_unilateral,
        position=session_exercise.position,
        session_id=session_exercise.session_id,
        started_at=session_exercise.session.started_at,
        sets=completed_sets,
        # session is already joinedload()ed by load_performed(), so this costs
        # no extra query.
        is_deload=session_exercise.session.is_deload,
    )
```

Add one line after `is_unilateral=...`:

```python
        weight_increment=exercise.weight_increment,
```

- [ ] **Step 9: Update the deload prefill call site**

In the same file, `_seeded_sets` currently reads:

```python
    exercise = db.session.get(Exercise, exercise_id)
    is_unilateral = bool(exercise and exercise.is_unilateral)
    return [
        SessionSet(
            position=j,
            weight=stats.deload_weight(prev['weight'], pct, is_unilateral),
```

Change to:

```python
    exercise = db.session.get(Exercise, exercise_id)
    increment = stats.resolve_increment(
        exercise.weight_increment if exercise else None,
        bool(exercise and exercise.is_unilateral),
    )
    return [
        SessionSet(
            position=j,
            weight=stats.deload_weight(prev['weight'], pct, increment),
```

- [ ] **Step 10: Update the deload toggle call site**

In the same file, `gym_toggle_deload` currently reads:

```python
        for session_exercise in session_.exercises:
            is_unilateral = session_exercise.exercise.is_unilateral
            for s in session_exercise.sets:
```

Change to:

```python
        for session_exercise in session_.exercises:
            increment = stats.resolve_increment(
                session_exercise.exercise.weight_increment,
                session_exercise.exercise.is_unilateral,
            )
            for s in session_exercise.sets:
```

and, eleven lines below, change:

```python
                    s.weight = stats.deload_weight(s.base_weight, pct, is_unilateral)
```

to:

```python
                    s.weight = stats.deload_weight(s.base_weight, pct, increment)
```

- [ ] **Step 11: Confirm no caller still passes a boolean**

```bash
grep -rn "deload_weight(\|_next_weight(" personal_apps/features personal_apps/tests
```

Expected: no line ends in `, True)` or `, False)`. Every call passes a number or a `resolve_increment(...)` expression.

- [ ] **Step 12: Run everything that does not need a database**

```bash
python -m pytest tests/test_gym_stats.py tests/test_gym_analytics.py -q
```

Expected: `166 passed`.

- [ ] **Step 13: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/features/gym/routes.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): step progression and deloads by the exercise's increment"
```

---

### Task 4: The live stepper

**Files:**
- Modify: `personal_apps/features/gym/routes.py:758` (the `session_detail.html` render call)
- Modify: `personal_apps/templates/gym/_session_live.html:143-159`
- Test: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `stats.resolve_increment`, `stats.DEFAULT_INCREMENT`, `Exercise.weight_increment`.
- Produces: a `live_increment` float in the `session_detail.html` template context (the template does no fallback logic of its own), and the `scratch_increment_exercise` pytest fixture, which Task 6 reuses.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`:

```python
@pytest.fixture()
def scratch_increment_exercise():
    """A throwaway Exercise inside a throwaway session.

    Its own exercise rather than the catalogue's first one, because these tests
    write to the exercise itself and must not leave a real lift carrying a
    made-up increment. Both rows are deleted afterwards.
    """
    from extensions import db
    from models import Exercise, SessionExercise, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest scratch increment lift', muscle_group='Brust')
        db.session.add(exercise)
        db.session.flush()
        session_ = WorkoutSession(name='pytest scratch increment',
                                  started_at=dt.datetime.utcnow())
        session_.exercises.append(SessionExercise(exercise_id=exercise.id, position=1))
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, session_.exercises[0].id, exercise.id)
    yield ids
    with flask_app.app_context():
        session_id, _, exercise_id = ids
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_live_stepper_falls_back_when_the_exercise_has_no_increment(client, scratch_increment_exercise):
    session_id, _, _ = scratch_increment_exercise
    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'data-step="2.5" data-decimals="1"' in html


def test_live_stepper_uses_the_exercises_own_increment(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise
    session_id, _, exercise_id = scratch_increment_exercise

    with flask_app.app_context():
        db.session.get(Exercise, exercise_id).weight_increment = 9.0
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'data-step="9.0" data-decimals="1"' in html
    # The fallback must be gone, not merely joined -- this session has exactly
    # one exercise, so a surviving 2.5 would mean the template still branches
    # on is_unilateral instead of reading the resolved value.
    assert 'data-step="2.5"' not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_gym_routes_smoke.py -k live_stepper -v
```

Expected: the fallback test passes by accident (the template still hardcodes `2.5`), and `test_live_stepper_uses_the_exercises_own_increment` FAILS on `assert 'data-step="9.0" data-decimals="1"' in html`. Needs MySQL80.

- [ ] **Step 3: Pass the resolved value into the template**

In `personal_apps/features/gym/routes.py`, the `render_template('gym/session_detail.html', ...)` call contains:

```python
        live_se=live_se,
        live_id=live_se.id if live_se else None,
```

Insert between those two lines:

```python
        # Resolved here, not in Jinja: the template must never re-implement the
        # fallback, or the two copies drift the moment DEFAULT_INCREMENT moves.
        live_increment=stats.resolve_increment(
            live_se.exercise.weight_increment, live_se.exercise.is_unilateral,
        ) if live_se else stats.DEFAULT_INCREMENT,
```

- [ ] **Step 4: Read the resolved value in the stepper**

In `personal_apps/templates/gym/_session_live.html`, this comment and line currently read:

```jinja
    {# The two numbers. No keyboard ever opens during a workout: the steppers
       carry the value in a hidden input and the readout is text. The step is
       2.5 kg, or 1.25 for a unilateral lift, mirroring stats._next_weight's
       own increments -- the smallest pair of plates on most bars, and one side
       at a time when only one side moves. #}
```

...and, further down:

```jinja
        <div class="field-num" data-step="{{ 1.25 if live_se.exercise.is_unilateral else 2.5 }}" data-decimals="1">
```

Replace the comment with:

```jinja
    {# The two numbers. No keyboard ever opens during a workout: the steppers
       carry the value in a hidden input and the readout is text. The weight
       step is the exercise's own increment, already resolved by the route
       (see stats.resolve_increment) -- a bar moves in 2.5 kg, a dumbbell pair
       often in 2, a selectorised stack in 9. Reps always step by 1. #}
```

and the `div` with:

```jinja
        <div class="field-num" data-step="{{ live_increment }}" data-decimals="1">
```

Leave `data-decimals="1"` alone: an integer step still reads `24,0`, matching every other weight the app prints. The stepper JS at `session_detail.html:362` already does `parseFloat(field.dataset.step)` and needs no change.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_gym_routes_smoke.py -k live_stepper -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/_session_live.html personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): step the live weight by the exercise's own increment"
```

---

### Task 5: Setting it from the catalogue

The exercise meta sheet and the Übungen add-form. Both already post to routes that build/update an `Exercise`.

**Files:**
- Modify: `personal_apps/features/gym/routes.py:63` (new helper), `:2089` (`gym_add_exercise`), `:2116` (`gym_update_exercise`)
- Modify: `personal_apps/templates/gym/exercise_detail.html:305-309`
- Modify: `personal_apps/templates/gym/uebungen.html:172-175`

**Interfaces:**
- Consumes: `Exercise.weight_increment`.
- Produces: `_to_increment(value) -> float | None` in `routes.py`, and a form field named exactly `weight_increment` on both surfaces. Task 6 reuses both.

- [ ] **Step 1: Add the parser**

In `personal_apps/features/gym/routes.py`, `_to_float` currently reads:

```python
def _to_float(value, fallback=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
```

Insert directly beneath it:

```python
def _to_increment(value):
    """A weight increment as typed, or None.

    Comma-tolerant: `type=number` normalises to a dot, but the field degrades
    to text without JS and a German keyboard produces `2,5`. Blank,
    unparseable and non-positive all store NULL, which
    stats.resolve_increment() reads as "use the default" -- so clearing the
    field is the way to put an exercise back on 2.5 kg.
    """
    parsed = _to_float(str(value).replace(',', '.').strip())
    return parsed if parsed and parsed > 0 else None
```

- [ ] **Step 2: Accept it when creating an exercise**

In the same file, `gym_add_exercise` currently reads:

```python
    exercise = Exercise(
        name=name,
        muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        is_unilateral=request.form.get('is_unilateral') == 'on',
    )
```

Change to:

```python
    exercise = Exercise(
        name=name,
        muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
    )
```

Note the asymmetry with rest, which falls back to `DEFAULT_REST_SECONDS` on a blank field: an increment left blank stores NULL on purpose, so the fallback stays in one place (`resolve_increment`) instead of being frozen into the row.

The two mid-session creation paths (`gym_add_session_exercise`, `gym_replace_session_exercise`) are deliberately left alone — neither posts this field, so a lift invented mid-workout starts at NULL and can be set from the sheet in Task 6.

- [ ] **Step 3: Accept it when updating an exercise**

In the same file, `gym_update_exercise` currently reads:

```python
    exercise.default_rest_seconds = _to_int(request.form.get('default_rest_seconds', ''))
    exercise.is_unilateral = request.form.get('is_unilateral') == 'on'
```

Change to:

```python
    exercise.default_rest_seconds = _to_int(request.form.get('default_rest_seconds', ''))
    exercise.weight_increment = _to_increment(request.form.get('weight_increment', ''))
    exercise.is_unilateral = request.form.get('is_unilateral') == 'on'
```

- [ ] **Step 4: Add the field to the exercise meta sheet**

In `personal_apps/templates/gym/exercise_detail.html`, this block currently reads:

```jinja
      <div class="field">
        <label class="label" for="meta-rest">Standard-Pause (Sek.)</label>
        <input type="number" id="meta-rest" name="default_rest_seconds" min="0" class="input input--num"
               value="{{ exercise.default_rest_seconds if exercise.default_rest_seconds is not none else '' }}" placeholder="90">
      </div>
```

Add directly beneath it:

```jinja
      <div class="field">
        <label class="label" for="meta-increment">Schrittweite (kg)</label>
        <input type="number" id="meta-increment" name="weight_increment" step="0.25" min="0" class="input input--num"
               value="{{ '%g'|format(exercise.weight_increment) if exercise.weight_increment is not none else '' }}" placeholder="2,5">
      </div>
```

`'%g'` renders `9.0` as `9` and `2.5` as `2.5`, so the field never shows a trailing zero it did not ask for.

- [ ] **Step 5: Add the field to the Übungen add-form**

In `personal_apps/templates/gym/uebungen.html`, this block currently reads:

```jinja
      <div class="field">
        <label class="label" for="uebungen-add-rest">Standard-Pause (Sek.)</label>
        <input type="number" id="uebungen-add-rest" name="default_rest_seconds" min="0" class="input input--num" placeholder="{{ default_rest_seconds }}">
      </div>
```

Add directly beneath it:

```jinja
      <div class="field">
        <label class="label" for="uebungen-add-increment">Schrittweite (kg)</label>
        <input type="number" id="uebungen-add-increment" name="weight_increment" step="0.25" min="0" class="input input--num" placeholder="2,5">
      </div>
```

- [ ] **Step 6: Verify the round trip**

```bash
python -c "
from app import app
from extensions import db
from models import Exercise
app.config['TESTING'] = True
c = app.test_client()
with c.session_transaction() as s: s['logged_in'] = True
c.post('/gym/exercises/add', data={'name': 'pytest scratch lift', 'weight_increment': '9'})
with app.app_context():
    ex = Exercise.query.filter_by(name='pytest scratch lift').first()
    print('created with', ex.weight_increment)
    eid = ex.id
c.post(f'/gym/exercises/{eid}/update', data={'name': 'pytest scratch lift', 'weight_increment': '2,5'})
with app.app_context():
    print('comma parsed to', db.session.get(Exercise, eid).weight_increment)
c.post(f'/gym/exercises/{eid}/update', data={'name': 'pytest scratch lift', 'weight_increment': ''})
with app.app_context():
    print('cleared to', db.session.get(Exercise, eid).weight_increment)
c.post(f'/gym/exercises/{eid}/delete')
with app.app_context():
    print('deleted:', db.session.get(Exercise, eid) is None)
"
```

Expected, in order: `created with 9.0`, `comma parsed to 2.5`, `cleared to None`, `deleted: True`.

- [ ] **Step 7: Verify both pages still render**

```bash
python -m pytest tests/test_gym_routes_smoke.py -q
```

Expected: all pass. Needs MySQL80.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/exercise_detail.html personal_apps/templates/gym/uebungen.html
git commit -m "feat(gym): set an exercise's increment from the catalogue"
```

---

### Task 6: Setting it mid-workout

The per-exercise sheet on the session screen. It sits **outside** `#session-body`, so its forms are ordinary posts with a redirect — the AJAX body-swap never sees them.

**Files:**
- Modify: `personal_apps/features/gym/routes.py:894` (new route, after `gym_update_session_exercise_rest`)
- Modify: `personal_apps/templates/gym/session_detail.html:235-241` (new sheet group) and `:725-730` (the change handler)
- Test: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `_to_increment` (Task 5), `Exercise.weight_increment` (Task 2), and the `scratch_increment_exercise` fixture already in `tests/test_gym_routes_smoke.py` (Task 4). It yields `(session_id, session_exercise_id, exercise_id)` and deletes both rows afterwards — do **not** redefine it.
- Produces: route `gym.gym_update_exercise_increment(session_exercise_id)` at `POST /gym/session-exercise/<int:session_exercise_id>/increment`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`:

```python
def test_session_sheet_writes_the_increment_to_the_exercise(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise, SessionExercise
    _, session_exercise_id, exercise_id = scratch_increment_exercise

    response = client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                           data={'weight_increment': '9'})
    assert response.status_code == 302

    with flask_app.app_context():
        assert db.session.get(Exercise, exercise_id).weight_increment == 9.0
        # The session row is untouched: this field is per exercise, forever,
        # unlike the rest time sitting directly above it in the same sheet.
        assert db.session.get(SessionExercise, session_exercise_id).rest_seconds is None


def test_session_sheet_clears_the_increment_back_to_the_default(client, scratch_increment_exercise):
    from extensions import db
    from models import Exercise
    _, session_exercise_id, exercise_id = scratch_increment_exercise

    client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                data={'weight_increment': '9'})
    client.post(f'/gym/session-exercise/{session_exercise_id}/increment',
                data={'weight_increment': ''})

    with flask_app.app_context():
        assert db.session.get(Exercise, exercise_id).weight_increment is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_gym_routes_smoke.py -k increment -v
```

Expected: FAIL — `werkzeug.routing.exceptions.BuildError` or a 404, because the route does not exist.

- [ ] **Step 3: Add the route**

In `personal_apps/features/gym/routes.py`, `gym_update_session_exercise_rest` currently ends:

```python
@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/rest', methods=['POST'])
@login_required
def gym_update_session_exercise_rest(session_exercise_id):
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_exercise.rest_seconds = _to_int(request.form.get('rest_seconds', ''))
    session_id = session_exercise.session_id
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))
```

Add directly beneath it:

```python
@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/increment', methods=['POST'])
@login_required
def gym_update_exercise_increment(session_exercise_id):
    """Write the EXERCISE's increment from inside a running session.

    Reached from the per-exercise sheet, beside the rest field -- but unlike
    rest, which is genuinely per session, a loadable step is a property of the
    equipment and so lands on the Exercise itself and stays. Keyed on the
    SessionExercise regardless, because that is the id the sheet has and it
    keeps the redirect back to the workout trivial.
    """
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_exercise.exercise.weight_increment = _to_increment(
        request.form.get('weight_increment', ''))
    session_id = session_exercise.session_id
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_gym_routes_smoke.py -k increment -v
```

Expected: `2 passed`.

- [ ] **Step 5: Add the field to the sheet**

In `personal_apps/templates/gym/session_detail.html`, the sheet body currently opens:

```jinja
  <div class="sheet__body">

    <div class="sheet__group">
      <form method="post" action="{{ url_for('gym.gym_update_session_exercise_rest', session_exercise_id=se.id) }}" class="sheet__row rest-form">
        <label class="label" for="rest-{{ se.id }}">Pause (Sekunden)</label>
        <input type="number" id="rest-{{ se.id }}" name="rest_seconds" min="0" class="input input--num rest-form__input"
               value="{{ se.rest_seconds if se.rest_seconds is not none else '' }}">
      </form>
    </div>
```

Add directly beneath that closing `</div>`:

```jinja
    {# Its own group, with the note, because the two fields have opposite
       lifetimes: the rest above is this session's, this one is the exercise's
       and outlives the workout. Identical styling with no caption would make
       that invisible. #}
    <div class="sheet__group">
      <form method="post" action="{{ url_for('gym.gym_update_exercise_increment', session_exercise_id=se.id) }}" class="sheet__row rest-form">
        <label class="label" for="increment-{{ se.id }}">Schrittweite (kg)</label>
        <input type="number" id="increment-{{ se.id }}" name="weight_increment" step="0.25" min="0" class="input input--num rest-form__input"
               value="{{ '%g'|format(se.exercise.weight_increment) if se.exercise.weight_increment is not none else '' }}" placeholder="2,5">
      </form>
      <p class="sheet__note">Gilt für die Übung, nicht nur heute.</p>
    </div>
```

`.sheet__note` and `.sheet__group` already exist in `static/gym/gym.css` (lines 2224–2225). No new CSS.

- [ ] **Step 6: Extend the auto-save handler**

In the same file, the change handler currently reads:

```javascript
// rest seconds auto-save, unchanged in behaviour
document.addEventListener('change', function (e) {
    if (e.target.name !== 'rest_seconds') { return; }
    var form = e.target.closest('form');
    if (form && form.requestSubmit) { form.requestSubmit(); }
});
```

Change to:

```javascript
// Auto-save for the two bare number fields in the per-exercise sheet. Both
// sheets live outside #session-body, so these are ordinary posts followed by a
// redirect -- the submit interceptor above never sees them.
document.addEventListener('change', function (e) {
    if (e.target.name !== 'rest_seconds' && e.target.name !== 'weight_increment') { return; }
    var form = e.target.closest('form');
    if (form && form.requestSubmit) { form.requestSubmit(); }
});
```

- [ ] **Step 7: Verify the field renders with its value and note**

```bash
python -c "
from app import app
from extensions import db
from models import WorkoutSession
app.config['TESTING'] = True
c = app.test_client()
with c.session_transaction() as s: s['logged_in'] = True
with app.app_context():
    sid = db.session.query(WorkoutSession.id).order_by(WorkoutSession.id.desc()).first()[0]
html = c.get(f'/gym/session/{sid}').get_data(as_text=True)
print('field:', html.count('name=\"weight_increment\"'), 'occurrences')
print('note:', 'Gilt f' in html)
"
```

Expected: one occurrence per visible exercise in that session, and `note: True`.

- [ ] **Step 8: Run the whole suite**

```bash
python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/session_detail.html personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): set an exercise's increment from inside the workout"
```

---

### Task 7: End-to-end verification

Nothing new is built here. This is the gate before the branch is offered for merge.

**Files:**
- Create: `personal_apps/scratchpad/verify_increment.py` (throwaway; do not commit)

- [ ] **Step 1: Run the full suite**

```bash
python -m pytest tests -q
```

Expected: all pass, zero failures, zero errors. If MySQL80 is down, start it — do not report a pass while the route suite is skipped.

- [ ] **Step 2: Check the migration is reversible**

```bash
python -m flask --app app db downgrade && python -m flask --app app db upgrade
```

Expected: a clean `a1e4c9d27f63 -> c7d3e91a4f28` after the down-and-up. Any error here means the batch operation is wrong.

- [ ] **Step 3: Confirm the constant is gone from every consumer**

```bash
grep -rn "1\.25\|2\.5" personal_apps/features/gym/stats.py personal_apps/templates/gym/_session_live.html
```

Expected: the only hits are inside `DEFAULT_INCREMENT = 2.5` and prose in docstrings/comments. No live expression still branches on `is_unilateral` to pick a step.

- [ ] **Step 4: Look at the sheet**

Per the standing preference, use python-playwright via Bash rather than the browser pane, batching both viewports into one script. The dev server must be running on port 5000, and `PERSONAL_ADMIN_USER` / `PERSONAL_ADMIN_PASS` must be set in the environment (the login form at `/login` checks them directly).

Write `personal_apps/scratchpad/verify_increment.py`:

```python
"""Screenshot the per-exercise sheet at both viewports. Throwaway."""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:5000'
SESSION_ID = sys.argv[1]          # pass a live session id on the command line
OUT = os.path.dirname(os.path.abspath(__file__))
VIEWPORTS = [('phone', 390, 844), ('desktop', 1280, 800)]

with sync_playwright() as p:
    browser = p.chromium.launch()
    for label, width, height in VIEWPORTS:
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.goto(f'{BASE}/login')
        page.fill('input[name="username"]', os.environ['PERSONAL_ADMIN_USER'])
        page.fill('input[name="password"]', os.environ['PERSONAL_ADMIN_PASS'])
        page.click('button[type="submit"]')
        page.goto(f'{BASE}/gym/session/{SESSION_ID}')
        # Open the live exercise's sheet the way the user does, then wait for
        # the native <dialog> to actually be open rather than merely present.
        page.click('.live__more')
        page.wait_for_selector('dialog.sheet[open]')
        page.screenshot(path=os.path.join(OUT, f'increment_{label}.png'), full_page=False)
        page.close()
    browser.close()
print('wrote increment_phone.png and increment_desktop.png')
```

Run it against a live session:

```bash
python scratchpad/verify_increment.py 123
```

Then `Read` both PNGs. Confirm by eye: the `Schrittweite (kg)` field sits in its own group under `Pause (Sekunden)`, separated by the existing group border, with `Gilt für die Übung, nicht nur heute.` beneath it, and nothing overflows at 390 px.

- [ ] **Step 5: Set a real increment by hand**

Open a workout on a machine exercise, set its increment in the sheet, close the sheet, and confirm the `+` button now moves the weight by that amount. Then check the exercise page shows the same number in its meta sheet.

- [ ] **Step 6: Clean up**

```bash
rm personal_apps/scratchpad/verify_increment.py personal_apps/scratchpad/increment_phone.png personal_apps/scratchpad/increment_desktop.png
```

- [ ] **Step 7: Report**

Summarise: the suite result with its actual count, the migration state, and what the screenshots showed. Then hand off to `superpowers:finishing-a-development-branch` for the merge decision.

---

## Deferred

Recorded so a later reviewer knows these were decided, not missed:

- Backfilling the existing catalogue. NULL is a correct permanent state; each exercise gets its increment the next time it is trained.
- Non-uniform stacks (5/10/20/30). Not representable by one number.
- Historical weights are not re-gridded. The first tap after setting a 9 kg step moves from the last logged weight, which may be off-stack until one weight is dialled by hand.

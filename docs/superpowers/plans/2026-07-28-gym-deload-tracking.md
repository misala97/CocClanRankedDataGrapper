# Gym Deload Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any workout session be marked as a deload, so the statistics stop misreading a deliberately light week as a bad one, and so running a deload is one tap instead of manual arithmetic across every set.

**Architecture:** One boolean plus one percentage on `WorkoutSession`. The flag reaches every statistics function through a single new field on the `stats.PerformedExercise` dataclass, which is built in exactly one place (`routes._to_performed`), so no function needs its own query. A single private helper `stats._progression_rows()` performs the exclusion wherever a function makes a *judgement* (records, stagnation, averages); functions that merely report *what happened* (tonnage, balance, consistency, history tables) keep every row and mark it instead. Prescription is one pure function, `stats.deload_weight()`, applied per set by one new route.

**Tech Stack:** Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), MySQL, Jinja2, pytest. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-07-28-gym-deload-tracking-design.md`](../specs/2026-07-28-gym-deload-tracking-design.md)

## Global Constraints

- **UI copy is German.** Code, comments, identifiers, and commit messages are English. Do not translate `PerformedExercise`, `is_deload`, etc.
- **Exactly three semantic hues** (`--live`, `--record`, `--stall`). Deload gets **no colour** — it renders in `--dim` on `--raised`. Do not add a fourth hue or a new CSS custom property for a colour.
- **Every state carries a word or a shape, never colour alone.** The deload state always renders the literal word `Deload`.
- **Touch targets ≥ 44×44 CSS px** for anything tapped during a workout.
- **Every interactive control is a real `<button>` or `<a>`.** Never a styled `<div>`.
- **Panels are borderless at rest.** A visible border means something (live, stall). Do not add borders for deload.
- **Repeated identical cards are banned.** Do not add a new panel to Heute for the deload suggestion; it goes inside the existing "Steht still" panel.
- **Numerals are tabular** (`font-variant-numeric: tabular-nums`) and the largest thing in their container.
- **`prefers-reduced-motion` disables all transitions.** Any new transition must sit inside the existing media query block.
- **`_head.html` open `<style>` convention:** never open a second `<style>` tag in a page template — it silently swallows the next CSS rule. All new CSS goes in `static/gym/gym.css`.
- **No emoji.** Icons come from the shared inline-SVG set (`templates/gym/_icon.html`).
- **`load_performed()` is called at most once per request.** Never add a call inside a loop or a second call to a route that already has one.
- **`stats.py` has zero SQLAlchemy imports** and must keep it. It sees only `PerformedExercise` and plain data.
- **Default deload percentage is 70.** Allowed values: `{50, 60, 70, 80, 90}`.
- **Run tests from `personal_apps/`:** `cd personal_apps && python -m pytest tests/test_gym_stats.py -v`

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `personal_apps/models.py` | `WorkoutSession.is_deload`, `.deload_pct` | 1 |
| `personal_apps/migrations/versions/<rev>_add_deload_to_sessions.py` | New Alembic revision | 1 |
| `personal_apps/features/gym/stats.py` | `is_deload` field, `_progression_rows`, `deload_weight`, `deload_signal`, exclusions, `has_deload` on tonnage | 2, 3, 4, 5, 6 |
| `personal_apps/features/gym/routes.py` | Carry flag into `PerformedExercise`; deload-aware seeding; the toggle route; `deload_signal` wiring | 2, 7, 8, 9 |
| `personal_apps/templates/gym/session_detail.html` | Live toggle + percentage picks | 10 |
| `personal_apps/templates/gym/session_finished.html` | Chip, verdict branch, advice suppression, retroactive toggle | 11 |
| `personal_apps/templates/gym/verlauf.html` | Chip on history rows | 12 |
| `personal_apps/templates/gym/heute.html` | Suggestion in "Steht still", deload week bars | 13 |
| `personal_apps/templates/gym/exercise_detail.html` | Deload marker on history rows | 14 |
| `personal_apps/static/gym/gym.css` | `chip--deload`, `.deload-bar`, `.vbar--deload`, `.deload-note` | 10, 13 |
| `personal_apps/tests/test_gym_stats.py` | Pure-function tests | 3, 4, 5, 6 |
| `personal_apps/tests/test_gym_routes_smoke.py` | DB-backed route tests | 8, 9 |
| `personal_apps/PRODUCT.md` | Document the deload state | 15 |

**Ordering rationale:** Tasks 1–2 are plumbing that everything depends on. Tasks 3–6 are pure functions, testable with no database. Tasks 7–9 are routes. Tasks 10–14 are templates. Task 15 is documentation and final verification. Tasks 3–6 could in principle run in parallel, but they all edit `stats.py`, so run them in order.

---

## Task 1: Schema — `is_deload` and `deload_pct`

**Files:**
- Modify: `personal_apps/models.py:190-206` (the `WorkoutSession` class)
- Create: `personal_apps/migrations/versions/f2a7c31d9b48_add_deload_to_sessions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `WorkoutSession.is_deload` (`bool`, non-null, default `False`) and `WorkoutSession.deload_pct` (`int | None`).

**Background:** This project uses Flask-Migrate (Alembic). The current migration head is `9c3e5a71f2b6` (`add_skipped_to_session_exercises`). Verify before writing: the head is the revision id that never appears as another file's `down_revision`.

`sa` is already imported in `models.py` (it is used by `SessionExercise.skipped`'s `server_default=sa.false()`). A `server_default` is **required** here because the column is `NOT NULL` and the table already has rows — without it the `ALTER TABLE` fails on existing data.

- [ ] **Step 1: Confirm the migration head**

```bash
cd personal_apps/migrations/versions && grep -h "^revision\|^down_revision" *.py
```

Expected: `9c3e5a71f2b6` appears as a `revision` but never as a `down_revision`. If a different id has that property, use it as `down_revision` in Step 3 instead.

- [ ] **Step 2: Add the columns to the model**

In `personal_apps/models.py`, inside `class WorkoutSession`, immediately after the `resting_set_id` line:

```python
    # A deliberately light session. Excluded from every judgement that assumes
    # an attempt at progress (records, stagnation, volume averages, next
    # session's pre-fill) and kept in every figure where it is simply true
    # (tonnage, balance, consistency). See features/gym/stats.py.
    is_deload    = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    # The percentage of normal working weight actually used, stored per session
    # rather than read from a constant: changing the default later must not
    # retroactively rewrite what past sessions claim to have been, and it makes
    # deload depth a measurable variable. NULL on every non-deload session.
    deload_pct   = db.Column(db.SmallInteger, nullable=True)
```

- [ ] **Step 3: Write the migration**

Create `personal_apps/migrations/versions/f2a7c31d9b48_add_deload_to_sessions.py`:

```python
"""add deload flag and percentage to workout sessions

Revision ID: f2a7c31d9b48
Revises: 9c3e5a71f2b6
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a7c31d9b48'
down_revision = '9c3e5a71f2b6'
branch_labels = None
depends_on = None


def upgrade():
    # server_default is required: the column is NOT NULL and the table has
    # existing rows, which would otherwise fail the ALTER.
    op.add_column('gym_workout_sessions',
                  sa.Column('is_deload', sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column('gym_workout_sessions',
                  sa.Column('deload_pct', sa.SmallInteger(), nullable=True))


def downgrade():
    op.drop_column('gym_workout_sessions', 'deload_pct')
    op.drop_column('gym_workout_sessions', 'is_deload')
```

- [ ] **Step 4: Apply the migration**

```bash
cd personal_apps && flask db upgrade
```

Expected: `Running upgrade 9c3e5a71f2b6 -> f2a7c31d9b48, add deload flag and percentage to workout sessions`

If `flask db upgrade` cannot find the app, use `FLASK_APP=app.py flask db upgrade`.

- [ ] **Step 5: Verify the columns exist**

```bash
cd personal_apps && python -c "from app import app; from models import WorkoutSession; app.app_context().push(); s = WorkoutSession.query.first(); print(s.id, s.is_deload, s.deload_pct)"
```

Expected: a session id followed by `False None`. If there are no sessions, `AttributeError: 'NoneType'` is acceptable — the import succeeding is the real check.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/f2a7c31d9b48_add_deload_to_sessions.py
git commit -m "feat(gym): add is_deload and deload_pct to workout sessions"
```

---

## Task 2: Carry the flag into `PerformedExercise`

**Files:**
- Modify: `personal_apps/features/gym/stats.py:35-56` (the `PerformedExercise` dataclass)
- Modify: `personal_apps/features/gym/routes.py:258-271` (`_to_performed`)
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `WorkoutSession.is_deload` from Task 1.
- Produces: `stats.PerformedExercise.is_deload` (`bool`, defaults to `False`); the test helper `perf(..., is_deload=False)`.

**Background:** `PerformedExercise` is a frozen dataclass and the *only* shape `stats.py` consumes. `routes._to_performed()` is the single place it is constructed. Adding the field here is what makes every later task a one-line filter instead of a query. The default is required so the existing test helper and any other constructor keep working.

`load_performed()` already `joinedload`s `SessionExercise.session`, so reading `session.is_deload` costs no extra query.

- [ ] **Step 1: Write the failing test**

Add to `personal_apps/tests/test_gym_stats.py`, directly after the `perf` helper:

```python
def test_performed_exercise_defaults_to_not_deload():
    assert perf([(80.0, 8)]).is_deload is False


def test_performed_exercise_carries_the_deload_flag():
    assert perf([(80.0, 8)], is_deload=True).is_deload is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k deload -v
```

Expected: FAIL — `TypeError: perf() got an unexpected keyword argument 'is_deload'`

- [ ] **Step 3: Add the field to the dataclass**

In `personal_apps/features/gym/stats.py`, add to `PerformedExercise` after `sets`:

```python
    sets: Tuple
    # True when this row was performed in a deliberately light session. Every
    # function below that makes a *judgement* (records, stagnation, averages)
    # drops these rows via _progression_rows(); every function that reports
    # what actually happened (tonnage, balance, consistency) keeps them.
    # Defaulted so callers predating the flag keep working.
    is_deload: bool = False
```

Extend the docstring's final paragraph with:

```
    `is_deload` marks a row performed during a deliberate deload. It is a
    property of the session, not the exercise -- every row from one session
    carries the same value.
```

- [ ] **Step 4: Extend the test helper**

In `personal_apps/tests/test_gym_stats.py`, change the `perf` signature and body:

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

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS, including every pre-existing test.

- [ ] **Step 6: Populate the field in `_to_performed`**

In `personal_apps/features/gym/routes.py`, in `_to_performed`, add after `sets=completed_sets,`:

```python
        # session is already joinedload()ed by load_performed(), so this costs
        # no extra query.
        is_deload=session_exercise.session.is_deload,
```

- [ ] **Step 7: Verify the routes still render**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: PASS. (Needs the local MySQL database. If it is not running, start it before continuing — this suite is the only check that the ORM wiring is intact.)

- [ ] **Step 8: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/features/gym/routes.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): carry the deload flag into PerformedExercise"
```

---

## Task 3: `deload_weight` — the prescription math

**Files:**
- Modify: `personal_apps/features/gym/stats.py` (add near `_next_weight`, around line 281)
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `stats.DELOAD_DEFAULT_PCT = 70`; `stats.DELOAD_ALLOWED_PCTS = (50, 60, 70, 80, 90)`; `stats.deload_weight(weight, pct, is_unilateral) -> float`.

**Background:** `stats.py` does not currently import `math`. Add it to the imports at the top of the file if it is absent.

Rounding is **down**, not to nearest: a deload rounded up is heavier than prescribed, which is the one direction that defeats it. Increments mirror `_next_weight()` — 2.5 kg is the smallest pair of plates on most bars; a unilateral lift moves one side at a time, so 1.25 kg.

- [ ] **Step 1: Write the failing tests**

Add to `personal_apps/tests/test_gym_stats.py`:

```python
def test_deload_weight_takes_the_percentage_and_rounds_down_to_a_plate():
    # 80 * 0.70 = 56.0, which is not loadable in 2.5 kg steps -> 55.0
    assert stats.deload_weight(80.0, 70, False) == 55.0


def test_deload_weight_rounds_down_not_to_nearest():
    # 100 * 0.70 = 70.0 exactly; 90 * 0.70 = 63.0 -> 62.5, not 65.0
    assert stats.deload_weight(100.0, 70, False) == 70.0
    assert stats.deload_weight(90.0, 70, False) == 62.5


def test_deload_weight_uses_the_half_step_for_unilateral():
    # 20 * 0.70 = 14.0 -> 13.75 in 1.25 kg steps, not 12.5 in 2.5 kg steps
    assert stats.deload_weight(20.0, 70, True) == 13.75


def test_deload_weight_leaves_a_bodyweight_set_alone():
    assert stats.deload_weight(0.0, 70, False) == 0.0


def test_deload_weight_never_floors_a_light_weight_to_zero():
    # 2.5 * 0.70 = 1.75 -> would floor to 0.0; one increment is the minimum.
    assert stats.deload_weight(2.5, 70, False) == 2.5
    assert stats.deload_weight(1.25, 70, True) == 1.25


def test_deload_weight_preserves_the_shape_of_a_ramped_session():
    session = [80.0, 80.0, 75.0]
    assert [stats.deload_weight(w, 70, False) for w in session] == [55.0, 55.0, 52.5]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k deload_weight -v
```

Expected: FAIL — `AttributeError: module 'features.gym.stats' has no attribute 'deload_weight'`

- [ ] **Step 3: Implement**

Add `import math` to the imports at the top of `personal_apps/features/gym/stats.py` if absent.

Add the constants beside the other module constants (after `UNDER_TRAINED_RATIO`):

```python
# The default depth of a deload: 70 % of normal working weight. Stored per
# session rather than read from here at display time, so changing this never
# rewrites what a past session claims to have been.
DELOAD_DEFAULT_PCT = 70
# The depths offered in the UI. Anything outside this falls back to the
# default rather than erroring -- losing the toggle is worse than an odd value.
DELOAD_ALLOWED_PCTS = (50, 60, 70, 80, 90)
```

Add the function directly after `_next_weight`:

```python
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

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS (all tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): add deload_weight prescription math"
```

---

## Task 4: Exclude deload rows from stagnation and record judgements

**Files:**
- Modify: `personal_apps/features/gym/stats.py` — `_progression_rows` (new), `is_new_best`, `sessions_since_pr`, `exercise_state`, `stall_report`, `_pr_weight`, `_pr_e1rm`
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `PerformedExercise.is_deload` from Task 2.
- Produces: `stats._progression_rows(rows) -> list` — the shared exclusion helper every judging function calls.

**Background:** This is the largest correctness change. The risk is a *missed* call site, not wrong logic, so everything goes through one greppable helper.

Do **not** change `muscle_group_volume`, `weekly_tonnage`, `consistency`, or `routine_memory` — deload sessions belong in all four (the sets happened, the session happened). Task 6 marks tonnage weeks without excluding them.

`exercise_state` calls both `_scoped` and `sessions_since_pr`. `sessions_since_pr` filters internally, so `exercise_state` must filter its own local `scoped` too, or its `rekord` and `steigend` branches would still read deload rows.

- [ ] **Step 1: Write the failing tests**

Add to `personal_apps/tests/test_gym_stats.py`:

```python
def test_deload_row_does_not_count_as_a_session_without_a_pr():
    # Without the exclusion this is 2 sessions since the PR; the deload in the
    # middle is not a failed attempt at one.
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),                   # the PR
        perf([(60.0, 8)], started_at=day(14), is_deload=True),  # deliberately light
        perf([(85.0, 8)], started_at=day(21)),
    ]
    assert stats.sessions_since_pr(rows) == 1


def test_a_run_of_deloads_cannot_push_an_exercise_to_stagniert():
    rows = [perf([(80.0, 8)], started_at=day(0)), perf([(85.0, 8)], started_at=day(7))]
    rows += [perf([(60.0, 8)], started_at=day(14 + 7 * n), is_deload=True) for n in range(6)]
    assert stats.exercise_state(rows) != 'stagniert'


def test_a_deload_session_cannot_set_a_record():
    # 200 kg logged in a deload session must not become the exercise's PR.
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    assert stats._pr_weight(rows)['weight'] == 80.0
    assert stats._pr_e1rm(rows)['weight'] == 80.0


def test_a_deload_row_is_not_the_baseline_a_later_set_is_judged_against():
    # A 60 kg deload must not make a normal 70 kg set look like a new best
    # when the real history already holds 80 kg.
    prior = [perf([(80.0, 8)], started_at=day(0)),
             perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    assert stats.is_new_best(70.0, 8, prior) is False


def test_is_new_best_is_false_when_only_deload_history_exists():
    # No real history to beat -- the same "a first attempt isn't a record"
    # rule the empty case already has.
    prior = [perf([(60.0, 8)], started_at=day(0), is_deload=True)]
    assert stats.is_new_best(200.0, 8, prior) is False


def test_stall_report_ignores_deload_sessions():
    rows = [perf([(80.0, 8)], started_at=day(0)), perf([(85.0, 8)], started_at=day(7))]
    rows += [perf([(60.0, 8)], started_at=day(14 + 7 * n), is_deload=True) for n in range(6)]
    assert stats.stall_report({1: rows}) == []


def test_exercise_state_is_neu_when_every_row_is_a_deload():
    rows = [perf([(60.0, 8)], started_at=day(0), is_deload=True),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    assert stats.exercise_state(rows) == 'neu'
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k "deload_row or deloads or deload_session or deload_history or ignores_deload or every_row_is_a_deload" -v
```

Expected: FAIL — `assert 2 == 1`, `assert 200.0 == 80.0`, `assert True is False`, and similar.

- [ ] **Step 3: Add the shared exclusion helper**

In `personal_apps/features/gym/stats.py`, add directly after `_chronological`:

```python
def _progression_rows(rows):
    """Only the rows that count as an attempt at progress.

    A deload session is deliberately light: its numbers are not a failed
    attempt at a record, and treating them as one manufactures exactly the
    plateau the deload existed to break. Every function that makes a
    *judgement* -- records, stagnation, volume averages -- starts here.
    Functions that report what actually happened (tonnage, balance,
    consistency, the history table) deliberately do not.
    """
    return [row for row in rows if not row.is_deload]
```

- [ ] **Step 4: Apply it to `sessions_since_pr`**

Change the first line of the body:

```python
def sessions_since_pr(rows, position=None):
    """How many completed sessions in a row have passed without a new best
    estimated 1RM. None when there is too little history to say anything.
    Deload sessions are not counted -- see _progression_rows()."""
    scoped = _scoped(_progression_rows(rows), position)
```

- [ ] **Step 5: Apply it to `exercise_state`**

```python
def exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD):
    """One of 'neu', 'rekord', 'stagniert', 'steigend', or None for stable.
    Mutually exclusive; first match wins. Deload sessions are excluded
    throughout -- an exercise whose only history is deloads reads 'neu',
    because there is no honest basis for comparison."""
    rows = _progression_rows(rows)
    if not rows:
        return 'neu'
    scoped = _scoped(rows, position)
```

The rest of the body is unchanged. Note `sessions_since_pr` is called with the already-filtered `rows`; filtering twice is harmless and keeps each function correct on its own.

- [ ] **Step 6: Apply it to `stall_report`**

Change the loop body's opening:

```python
    for exercise_id, rows in rows_by_exercise.items():
        rows = _progression_rows(rows)
        if not rows:
            continue
```

The `position`, `scoped`, `peak`, and `stuck_at` lines below are unchanged and now read filtered data.

- [ ] **Step 7: Apply it to `_pr_weight` and `_pr_e1rm`**

```python
def _pr_weight(rows):
    """The heaviest single set ever logged. A deload cannot hold a record."""
    best = None
    for row in _progression_rows(rows):
```

```python
def _pr_e1rm(rows):
    """The single set with the highest estimated 1RM -- not always the
    heaviest one, since more reps at less weight can estimate higher. A
    deload cannot hold a record."""
    best = None
    for row in _progression_rows(rows):
```

- [ ] **Step 8: Apply it to `is_new_best`**

```python
def is_new_best(weight, reps, prior_rows):
    """True if one just-logged (weight, reps) pair beats every OTHER
    session's best for this exercise -- ...

    Deload sessions are excluded from `prior_rows`: a light week must not
    lower the bar a normal set is judged against. If deloads are the only
    history, this is False, the same as having no history at all.
    """
    prior_rows = _progression_rows(prior_rows)
    if not prior_rows:
        return False
```

Keep the existing docstring body; add only the new paragraph.

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS, all tests. If a pre-existing test now fails, the filter has been applied to a reporting function by mistake — check that `muscle_group_volume`, `weekly_tonnage`, `consistency`, and `routine_memory` are untouched.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): exclude deload sessions from stagnation and record judgements"
```

---

## Task 5: Exclude deload rows from session reports and volume averages

**Files:**
- Modify: `personal_apps/features/gym/stats.py` — `session_report`, `session_record_counts`, `exercise_progress`
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `stats._progression_rows` from Task 4.
- Produces: `session_report(...)` gains `'is_deload'` and `'deload_pct'` in its return dict; each `exercise_progress` table row and series point gains `'is_deload'`.

**Background:** `session_report` takes `current` (this session's rows) and `history` (every other row for those exercises). Two separate things must happen:

1. `history` is filtered, so past deloads never become a baseline or an average.
2. When `current` is *itself* a deload, no record may be awarded and no verdict may claim stagnation — the session was never an attempt.

`session_report` does not currently receive the flag directly; it reads it off `current`, whose rows all carry the same session's value. An empty `current` (no completed sets) is possible, so default to `False`.

`exercise_progress` is the split case: `table` and `series` keep every row and mark it; `pr_weight`, `pr_e1rm`, `state`, and `sessions_since_pr` exclude (already handled in Task 4, since they call the filtered functions).

- [ ] **Step 1: Write the failing tests**

Add to `personal_apps/tests/test_gym_stats.py`:

```python
def test_session_report_excludes_deloads_from_the_volume_average():
    current = [perf([(80.0, 10)], started_at=day(21))]                       # 800
    history = [
        perf([(80.0, 10)], started_at=day(0)),                               # 800
        perf([(40.0, 10)], started_at=day(7), is_deload=True),               # 400, ignored
    ]
    report = stats.session_report(current, history)
    assert report['exercises'][0]['avg_volume'] == 800.0
    assert report['exercises'][0]['volume_delta_pct'] == 0


def test_session_report_awards_no_record_when_the_session_is_a_deload():
    current = [perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    history = [perf([(80.0, 8)], started_at=day(0))]
    report = stats.session_report(current, history)
    assert report['records'] == []
    assert report['record_count'] == 0
    assert report['exercises'][0]['is_weight_pr'] is False


def test_session_report_gives_no_stagnation_advice_on_a_deload():
    current = [perf([(60.0, 8)], started_at=day(35), is_deload=True)]
    history = [perf([(85.0, 8)], started_at=day(0))]
    history += [perf([(80.0, 8)], started_at=day(7 * n)) for n in range(1, 5)]
    report = stats.session_report(current, history)
    assert report['advice'] == []
    assert report['exercises'][0]['verdict'] != 'stagniert'


def test_session_report_reports_its_own_deload_state():
    plain = stats.session_report([perf([(80.0, 8)])], [])
    assert plain['is_deload'] is False
    loaded = stats.session_report([perf([(80.0, 8)], is_deload=True)], [])
    assert loaded['is_deload'] is True


def test_session_report_on_an_empty_session_is_not_a_deload():
    assert stats.session_report([], [])['is_deload'] is False


def test_session_record_counts_ignores_deload_sessions():
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert stats.session_record_counts(rows) == {}


def test_exercise_progress_keeps_deload_rows_but_marks_them():
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert len(progress['table']) == 2
    # table is newest-first
    assert progress['table'][0]['is_deload'] is True
    assert progress['table'][1]['is_deload'] is False
    assert [point['is_deload'] for point in progress['series'][0]['points']] == [False, True]
    # ...but the deload still holds no record
    assert progress['pr_weight']['weight'] == 80.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k "session_report or session_record_counts_ignores or exercise_progress_keeps" -v
```

Expected: FAIL — `KeyError: 'is_deload'`, `assert 600.0 == 800.0`, and similar.

- [ ] **Step 3: Filter `session_record_counts`**

Change the first loop:

```python
    rows_by_exercise = {}
    for row in _progression_rows(rows):
        by_session = rows_by_exercise.setdefault(row.exercise_id, {})
        by_session.setdefault(row.session_id, []).append(row)
```

Add to the docstring, after the first paragraph:

```
    Deload sessions are excluded outright: they can neither hold a record nor
    be the bar another session has to clear.
```

- [ ] **Step 4: Filter `session_report`'s history and detect its own deload state**

Replace the opening of `session_report`'s body (the `by_exercise` build) with:

```python
    # This session's own deload state. Every row in `current` comes from the
    # same session, so any of them answers it; an empty session (no completed
    # sets) is not a deload.
    is_deload = bool(current) and current[0].is_deload

    by_exercise = {}
    for row in _progression_rows(history):
        by_exercise.setdefault(row.exercise_id, []).append(row)
```

Add to the docstring, before the closing quotes:

```
    A deload session awards no records and produces no stagnation advice: it
    was never an attempt at either. Past deloads are dropped from `history`
    so they cannot become a baseline or deflate an average.
```

- [ ] **Step 5: Suppress records and advice on a deload session**

In the per-row loop, change the three PR flags so a deload can never set one:

```python
            'is_weight_pr': (not is_deload) and has_history and weight > max(best_weight(p) for p in past),
            'is_volume_pr': (not is_deload) and has_history and volume > max(past_volumes),
            'is_e1rm_pr': (not is_deload) and has_history and e1rm > max(best_e1rm(p) for p in past),
```

Change the verdict call so stagnation is never claimed on a deload:

```python
        since = sessions_since_pr(past + ([] if is_deload else [row]), position=row.position)
        entry['sessions_since_pr'] = since
        entry['verdict'] = None if is_deload else _verdict(entry, since)
```

Guard the advice block:

```python
        if entry['verdict'] == 'stagniert':
```

remains as-is — with `verdict` forced to `None` above, it can no longer fire on a deload. No change needed here; verify by reading it.

- [ ] **Step 6: Return the deload state**

Add two keys to `session_report`'s return dict, after `'advice': advice,`:

```python
        'is_deload': is_deload,
        # The percentage is a property of the session row, not of the
        # performed rows, so the route supplies it to the template directly.
        # Reported here as None so the shape is stable for any caller reading
        # the dict alone.
        'deload_pct': None,
```

- [ ] **Step 7: Mark rows in `exercise_progress`**

Add `'is_deload': row.is_deload,` to the `table` dict comprehension (after `'position': row.position,`) and to each `points` dict (after `'started_at': row.started_at,`).

Add to the docstring:

```
    `table` and `series` keep deload rows and mark them `is_deload`: they are
    the record of what was performed, and dropping them would leave holes in
    the chart. The PR and state fields below exclude them.
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS, all tests.

- [ ] **Step 9: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): exclude deloads from session reports and volume averages"
```

---

## Task 6: `deload_signal` and tonnage week marking

**Files:**
- Modify: `personal_apps/features/gym/stats.py` — constants, `weekly_tonnage`, new `deload_signal`
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `stall_report()`'s output shape (a list of dicts with `exercise_id`, `name`, `position`, `stuck_at`, `since`, `sessions_since_pr`).
- Produces: `stats.DELOAD_STALL_THRESHOLD = 4`; `stats.DELOAD_SUPPRESSION_DAYS = 21`; `stats.deload_signal(report, rows_by_exercise, now, last_deload_at=None, days=ROLLING_WINDOW_DAYS, threshold=DELOAD_STALL_THRESHOLD, suppression_days=DELOAD_SUPPRESSION_DAYS) -> dict | None` returning `{'count': int, 'stalls': list}`; `weekly_tonnage()` buckets gain `'has_deload': bool`.

**Background:** `stall_report()` reports every stalled exercise in the catalogue, including lifts abandoned months ago that drifted into `stagniert` from disuse. Those say nothing about recovery, so the deload signal counts only exercises trained inside the rolling window. `stall_report()` itself is deliberately **not** changed — the "Steht still" roster should keep listing all of them.

The suppression window stops a stall that survives a deload from nagging every session. A lifter who has never deloaded (`last_deload_at is None`) must still be able to be told to.

Threshold 4, not 3: `STAGNATION_THRESHOLD` counts sessions, not weeks, and isolation lifts cross it routinely. With an active rotation around 12–15 exercises, 4 is roughly a third stalling at once.

- [ ] **Step 1: Write the failing tests**

Add to `personal_apps/tests/test_gym_stats.py`:

```python
def stalled(exercise_id, name, last_trained):
    """One stall_report entry plus the history row that dates it."""
    entry = {'exercise_id': exercise_id, 'name': name, 'position': 1,
             'stuck_at': 80.0, 'since': last_trained, 'sessions_since_pr': 5}
    row = perf([(80.0, 8)], started_at=last_trained, exercise_id=exercise_id, name=name)
    return entry, row


def signal_input(count, last_trained_offsets=None, now=None):
    """Build (report, rows_by_exercise) for `count` stalled exercises."""
    now = now or DELOAD_NOW
    offsets = last_trained_offsets or [1] * count
    report, rows_by_exercise = [], {}
    for index, offset in enumerate(offsets, start=1):
        entry, row = stalled(index, 'Uebung {}'.format(index),
                             now - dt.timedelta(days=offset))
        report.append(entry)
        rows_by_exercise[index] = [row]
    return report, rows_by_exercise


DELOAD_NOW = dt.datetime(2026, 7, 28, 18, 0)   # NOT `NOW` -- the test file already has one


def test_deload_signal_fires_at_the_threshold():
    report, rows = signal_input(4)
    signal = stats.deload_signal(report, rows, DELOAD_NOW)
    assert signal is not None
    assert signal['count'] == 4
    assert len(signal['stalls']) == 4


def test_deload_signal_stays_quiet_below_the_threshold():
    report, rows = signal_input(3)
    assert stats.deload_signal(report, rows, DELOAD_NOW) is None


def test_deload_signal_ignores_exercises_not_trained_in_the_window():
    # Four stalls, but two are lifts abandoned months ago -- stagnating from
    # disuse, which says nothing about how recovered the lifter is.
    report, rows = signal_input(4, last_trained_offsets=[1, 3, 200, 300])
    assert stats.deload_signal(report, rows, DELOAD_NOW) is None


def test_deload_signal_is_suppressed_soon_after_a_deload():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW,
                               last_deload_at=NOW - dt.timedelta(days=7)) is None


def test_deload_signal_fires_again_once_the_suppression_window_passes():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW,
                               last_deload_at=NOW - dt.timedelta(days=22)) is not None


def test_deload_signal_fires_for_someone_who_has_never_deloaded():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW, last_deload_at=None) is not None


def test_weekly_tonnage_marks_a_week_containing_a_deload():
    now = dt.datetime(2026, 7, 29, 18, 0)          # a Wednesday
    rows = [
        perf([(80.0, 10)], started_at=now - dt.timedelta(days=1)),
        perf([(60.0, 10)], started_at=now, is_deload=True),
        perf([(80.0, 10)], started_at=now - dt.timedelta(days=8)),
    ]
    weeks = stats.weekly_tonnage(rows, now)
    assert weeks[-1]['has_deload'] is True
    assert weeks[-2]['has_deload'] is False
    # the volume itself still totals everything
    assert weeks[-1]['volume'] == 800.0 + 600.0


def test_weekly_tonnage_marks_an_empty_week_as_no_deload():
    now = dt.datetime(2026, 7, 29, 18, 0)
    weeks = stats.weekly_tonnage([], now)
    assert all(week['has_deload'] is False for week in weeks)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k "deload_signal or weekly_tonnage_marks" -v
```

Expected: FAIL — `AttributeError: module 'features.gym.stats' has no attribute 'deload_signal'` and `KeyError: 'has_deload'`.

- [ ] **Step 3: Add the constants**

Beside the other module constants in `personal_apps/features/gym/stats.py`, after `DELOAD_ALLOWED_PCTS`:

```python
# How many exercises from the *active* rotation must be stalled at once before
# it reads as accumulated fatigue rather than a set of individual weak points.
# STAGNATION_THRESHOLD counts sessions, not weeks, and isolation lifts cross it
# routinely -- at 3 this would fire during ordinary training and be learned-
# ignored. With a rotation of roughly 12-15 exercises, 4 is about a third.
DELOAD_STALL_THRESHOLD = 4
# Don't re-suggest a deload this soon after one, so a stall that survives the
# deload doesn't nag every single session.
DELOAD_SUPPRESSION_DAYS = 21
```

- [ ] **Step 4: Implement `deload_signal`**

Add after `stall_report`:

```python
def deload_signal(report, rows_by_exercise, now, last_deload_at=None,
                  days=ROLLING_WINDOW_DAYS, threshold=DELOAD_STALL_THRESHOLD,
                  suppression_days=DELOAD_SUPPRESSION_DAYS):
    """Whether the data says a deload is due, and the lifts that say so.

    `report` is stall_report()'s output and `rows_by_exercise` the map the
    caller already holds, so this costs no extra query.

    Only exercises actually trained inside the rolling window count. A lift
    abandoned six months ago drifts into 'stagniert' from disuse and says
    nothing about how recovered the lifter is; counting it would leave the
    suggestion permanently lit for anyone with a long catalogue.

    Returns None when the signal does not fire, otherwise the qualifying
    stalls so the page can name the lifts rather than assert a vague verdict.
    """
    if last_deload_at is not None and (now - last_deload_at).days < suppression_days:
        return None

    cutoff = now - dt.timedelta(days=days)
    active = []
    for entry in report:
        rows = rows_by_exercise.get(entry['exercise_id']) or []
        if any(row.started_at >= cutoff for row in rows):
            active.append(entry)

    if len(active) < threshold:
        return None
    return {'count': len(active), 'stalls': active}
```

- [ ] **Step 5: Mark deload weeks in `weekly_tonnage`**

Replace the bucket accumulation and return:

```python
    current_start = _week_start(now)
    starts = [current_start - dt.timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]
    buckets = {start: 0.0 for start in starts}
    deload_weeks = set()
    for row in rows:
        start = _week_start(row.started_at)
        if start in buckets:
            buckets[start] += row_volume(row)
            if row.is_deload:
                deload_weeks.add(start)
    return [
        {'week_start': start, 'volume': round(buckets[start], 1),
         'is_current': start == current_start,
         'has_deload': start in deload_weeks}
        for start in starts
    ]
```

Add to the docstring:

```
    `has_deload` marks a week containing at least one deload session, so the
    page can label the dip instead of leaving it looking like a collapse. The
    volume itself still totals every session, deload or not -- the work was
    done and the chart reports what happened.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS, all tests.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): add deload_signal and mark deload weeks in tonnage"
```

---

## Task 7: Deload-aware seeding

**Files:**
- Modify: `personal_apps/features/gym/routes.py:104-149` (`_last_session_exercise`, `_last_performance`, `_last_full_performance`)

**Interfaces:**
- Consumes: `WorkoutSession.is_deload` from Task 1.
- Produces: `_last_session_exercise(exercise_id, position=None)` now ignores deload sessions. Signatures unchanged.

**Background:** **This is the most important behavioural fix in the feature.** `_last_session_exercise` finds the most recent `SessionExercise` with a completed set, and `gym_start` uses it to pre-fill a new session's weights. Without this change, the session after a deload pre-fills at 70 %, the one after that pre-fills from *that*, and the lifter silently never returns to their real working weight. The feature would sabotage the training it exists to support.

Both `_last_performance` (the add-set suggestion) and `_last_full_performance` (the template pre-fill) call it, so one filter fixes both.

There is no test for this task alone — it is verified end to end by Task 9's regression test, which is the honest place to check it.

- [ ] **Step 1: Add the filter**

In `personal_apps/features/gym/routes.py`, in `_last_session_exercise`, change `base_query`:

```python
    base_query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(
            SessionExercise.exercise_id == exercise_id,
            SessionExercise.sets.any(SessionSet.completed == True),
            # Never seed from a deload. Pre-filling the next session at 70 %
            # would make the following one seed from *that*, and the lifter
            # would silently never return to their real working weight.
            WorkoutSession.is_deload == False,
        )
    )
```

Note the `== False` (not `is False`) — this is a SQLAlchemy filter expression, matching the `SessionSet.completed == True` on the line above.

- [ ] **Step 2: Extend the docstring**

Add a final paragraph to `_last_session_exercise`'s docstring:

```
    Deload sessions are skipped entirely. They are a deliberately light week,
    not what you should come back to -- seeding from one would carry the
    reduction forward into every session after it.
```

- [ ] **Step 3: Verify the routes still render**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/features/gym/routes.py
git commit -m "feat(gym): never seed a new session from a deload"
```

---

## Task 8: The toggle route

**Files:**
- Modify: `personal_apps/features/gym/routes.py` (add after `gym_finish_session`, around line 754)
- Test: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `stats.deload_weight`, `stats.DELOAD_DEFAULT_PCT`, `stats.DELOAD_ALLOWED_PCTS` from Task 3; `_last_full_performance` from Task 7.
- Produces: endpoint `gym.gym_toggle_deload` at `POST /gym/session/<int:session_id>/deload`, form fields `on` and `pct`.

**Background:** The rule from the spec, §6.2:

| Session state when toggled | Flag | Weights |
|---|---|---|
| No completed sets, toggled **on** | set | every `SessionSet.weight` rewritten through `deload_weight()` |
| No completed sets, toggled **off** | cleared | **re-seeded** from `_last_full_performance()` |
| Any completed set, either direction | set / cleared | untouched |

The "any completed set" test is **computed, not latched** — it asks whether the session has a completed set *right now*, so un-completing a set re-enables prescription and a mis-tap is always recoverable.

Toggling off **re-seeds** rather than dividing by the percentage: reversing the arithmetic after a floor is lossy (`80 → 55 → 78.57 → 77.5`) and repeated toggling would walk the weights downward.

Finished sessions are accepted — retroactively flagging a workout you already did is a first-class flow, and it lands in the "any completed set" branch, so nothing is rewritten.

- [ ] **Step 1: Write the failing tests**

Add to `personal_apps/tests/test_gym_routes_smoke.py`. First add the imports and a fixture at the top of the file, after the existing `client` fixture:

```python
import datetime as dt


@pytest.fixture()
def scratch_session():
    """A throwaway session with one exercise and two uncompleted sets.

    Deleted afterwards whatever the test does -- this suite runs against the
    real local development database.
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise.query.first()
        assert exercise is not None, 'the dev database needs at least one exercise'
        session_ = WorkoutSession(name='pytest scratch', started_at=dt.datetime.utcnow())
        session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
        session_exercise.sets = [
            SessionSet(position=1, weight=80.0, reps=8, completed=False),
            SessionSet(position=2, weight=75.0, reps=8, completed=False),
        ]
        session_.exercises.append(session_exercise)
        db.session.add(session_)
        db.session.commit()
        session_id = session_.id
    yield session_id
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
```

Then the tests:

```python
def set_weights(session_id):
    from models import WorkoutSession
    from extensions import db
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        return [s.weight for se in session_.exercises for s in se.sets]


def deload_state(session_id):
    from models import WorkoutSession
    from extensions import db
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        return session_.is_deload, session_.deload_pct


def test_deload_on_rewrites_every_weight_when_nothing_is_completed(client, scratch_session):
    response = client.post('/gym/session/{}/deload'.format(scratch_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    # 80 * 0.7 = 56 -> 55.0 ; 75 * 0.7 = 52.5 -> 52.5
    assert set_weights(scratch_session) == [55.0, 52.5]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_off_restores_the_seeded_weights_exactly(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '0'})
    # Not 55 / 0.7 = 78.57 -> 77.5. Toggling must not walk the weights down.
    assert set_weights(scratch_session) != [77.5, 75.0]
    assert deload_state(scratch_session) == (False, None)


def test_deload_on_rewrites_nothing_once_a_set_is_completed(client, scratch_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = True
        db.session.commit()
    client.post('/gym/session/{}/deload'.format(scratch_session), data={'on': '1', 'pct': '70'})
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_on_a_finished_session_is_label_only(client, scratch_session):
    from extensions import db
    from models import WorkoutSession
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, scratch_session)
        session_.exercises[0].sets[0].completed = True
        session_.finished_at = dt.datetime.utcnow()
        db.session.commit()
    response = client.post('/gym/session/{}/deload'.format(scratch_session),
                           data={'on': '1', 'pct': '70'})
    assert response.status_code in (302, 303)
    assert set_weights(scratch_session) == [80.0, 75.0]
    assert deload_state(scratch_session) == (True, 70)


def test_deload_pct_out_of_range_falls_back_to_the_default(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session),
                data={'on': '1', 'pct': '999'})
    assert deload_state(scratch_session) == (True, 70)


def test_deload_pct_that_is_not_a_number_falls_back_to_the_default(client, scratch_session):
    client.post('/gym/session/{}/deload'.format(scratch_session),
                data={'on': '1', 'pct': 'schwer'})
    assert deload_state(scratch_session) == (True, 70)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -k deload -v
```

Expected: FAIL with `assert 404 in (302, 303)` — the route does not exist yet.

- [ ] **Step 3: Implement the route**

Add to `personal_apps/features/gym/routes.py`, after `gym_finish_session`:

```python
@gym_bp.route('/gym/session/<int:session_id>/deload', methods=['POST'])
@login_required
def gym_toggle_deload(session_id):
    """Mark (or unmark) a session as a deliberately light one.

    The flag is always editable -- including on a finished session, since
    labelling a workout you already did is a first-class flow and the reason
    this feature exists. What is gated is the *prescription*: weights are only
    rewritten when the session has no completed set, so nothing actually
    lifted is ever overwritten.

    That test is computed, not latched: un-completing a set re-enables the
    rewrite, so a mis-tap is always recoverable.

    Toggling off re-seeds from history rather than dividing the weights back
    up. Reversing the arithmetic after deload_weight()'s floor is lossy
    (80 -> 55 -> 78.57 -> 77.5), so repeated toggling would walk the weights
    downward.
    """
    session_ = db.get_or_404(WorkoutSession, session_id)

    on = request.form.get('on') == '1'
    pct = _to_int(request.form.get('pct', ''), fallback=stats.DELOAD_DEFAULT_PCT)
    if pct not in stats.DELOAD_ALLOWED_PCTS:
        pct = stats.DELOAD_DEFAULT_PCT

    session_.is_deload = on
    session_.deload_pct = pct if on else None

    has_completed_set = any(
        s.completed for se in session_.exercises for s in se.sets
    )
    if not has_completed_set:
        for session_exercise in session_.exercises:
            if on:
                is_unilateral = session_exercise.exercise.is_unilateral
                for s in session_exercise.sets:
                    s.weight = stats.deload_weight(s.weight, pct, is_unilateral)
            else:
                seeded = _last_full_performance(
                    session_exercise.exercise_id, position=session_exercise.position)
                for s, previous in zip(session_exercise.sets, seeded):
                    s.weight = previous['weight']

    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))
```

Note `zip()` stops at the shorter of the two, so a session with more sets than its history keeps the extra sets' weights rather than raising — the right failure mode for a control that must never lose data.

- [ ] **Step 4: Verify `_to_int` accepts a fallback**

Read `personal_apps/features/gym/routes.py:53-58`. It should be:

```python
def _to_int(value, fallback=None):
```

If the signature differs, adjust the call in Step 3 to match.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: PASS, all tests including the pre-existing smoke checks.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): add the deload toggle route"
```

---

## Task 9: Wire `deload_signal` into Heute, and the seeding regression test

**Files:**
- Modify: `personal_apps/features/gym/routes.py:294-345` (`gym_heute`)
- Modify: `personal_apps/features/gym/routes.py` (`session_detail`'s finished branch, around line 410, to pass `deload_pct`)
- Test: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `stats.deload_signal` from Task 6; `WorkoutSession.is_deload` from Task 1.
- Produces: `gym_heute` renders with `deload_suggestion` (a dict or `None`); the finished-session render receives `deload_pct`.

**Background:** `gym_heute` already builds `rows_by_exercise` and calls `stats.stall_report(rows_by_exercise)`. `deload_signal` reuses both, so the only new cost is one small query for the most recent deload.

`session_report` returns `'deload_pct': None` (Task 5) because it sees only `PerformedExercise` rows, which do not carry it. The route overrides it from the ORM object.

The **seeding regression test** here is the single most important test in the feature.

- [ ] **Step 1: Write the failing regression test**

Add to `personal_apps/tests/test_gym_routes_smoke.py`:

```python
def test_a_new_session_seeds_from_the_last_normal_session_not_the_deload(client):
    """The regression this whole feature exists to prevent.

    Without the filter in _last_session_exercise, the session after a deload
    pre-fills at 70 %, the one after that seeds from *that*, and the lifter
    silently never returns to their real working weight.
    """
    from extensions import db
    from features.gym.routes import _last_full_performance
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    created = []
    try:
        with flask_app.app_context():
            exercise = Exercise.query.first()
            assert exercise is not None
            for offset, weight, deload in ((2, 100.0, False), (1, 70.0, True)):
                started = dt.datetime.utcnow() - dt.timedelta(days=offset)
                session_ = WorkoutSession(
                    name='pytest seed {}'.format(offset), started_at=started,
                    finished_at=started + dt.timedelta(hours=1), is_deload=deload,
                    deload_pct=70 if deload else None)
                session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
                session_exercise.sets = [
                    SessionSet(position=1, weight=weight, reps=8, completed=True)]
                session_.exercises.append(session_exercise)
                db.session.add(session_)
                db.session.commit()
                created.append(session_.id)

            seeded = _last_full_performance(exercise.id, position=1)
            assert seeded, 'expected the normal session to be found'
            assert seeded[0]['weight'] == 100.0, 'seeded from the deload'
    finally:
        with flask_app.app_context():
            for session_id in created:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()
```

- [ ] **Step 2: Run it to verify it passes**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -k seeds_from_the_last_normal -v
```

Expected: PASS — Task 7 already implemented the filter. If it FAILS with `assert 70.0 == 100.0`, Task 7's filter is missing or wrong; fix it before continuing. This test exists to lock that behaviour in permanently.

- [ ] **Step 3: Wire `deload_signal` into `gym_heute`**

In `gym_heute`, after the `performed`/`rows_by_exercise` loop and before `return render_template(...)`:

```python
    # stall_report() lists every stalled lift in the catalogue, which is what
    # the "Steht still" roster should show. The deload signal is a narrower
    # read of the same data -- only the active rotation -- so it is computed
    # here from the report rather than by changing stall_report itself.
    stalls = stats.stall_report(rows_by_exercise)
    last_deload = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None), WorkoutSession.is_deload.is_(True))
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    deload_suggestion = stats.deload_signal(
        stalls, rows_by_exercise, now,
        last_deload_at=last_deload.started_at if last_deload else None,
    )
```

Then change the `render_template` call: replace `stalls=stats.stall_report(rows_by_exercise),` with

```python
        stalls=stalls,
        deload_suggestion=deload_suggestion,
```

so `stall_report` is called exactly once.

- [ ] **Step 4: Exclude deloads from the comparable-session cohort**

**Spec §5 requires this and the plan previously missed it.** `session_report` receives `comparable_session_volumes` as a list of bare floats with no flag attached, so it *cannot* filter them itself — the exclusion has to happen where the cohort is built. Without this, a past deload's total volume stays in `avg_total_volume`, deflating the baseline every future session of that template is measured against. That is the same defect the per-exercise `avg_volume` fix in Task 5 closed, one level up.

In `session_detail`'s finished branch, add one clause to the cohort query:

```python
        comparable = []
        if session_.template_id:
            cohort = (
                WorkoutSession.query
                .filter(
                    WorkoutSession.id != session_.id,
                    WorkoutSession.finished_at.isnot(None),
                    WorkoutSession.template_id == session_.template_id,
                    # A deliberately light session must not deflate the average
                    # every later session of this template is compared against.
                    # session_report cannot do this itself -- it receives bare
                    # floats with no flag to filter on.
                    WorkoutSession.is_deload.is_(False),
                )
                .all()
            )
```

Leave the rest of the block unchanged.

- [ ] **Step 5: Pass `deload_pct` to the finished-session template**

In the same branch, change its final render:

```python
        # session_report only sees PerformedExercise rows, which do not carry
        # the percentage -- it belongs to the session row itself.
        data['deload_pct'] = session_.deload_pct
        return render_template('gym/session_finished.html', session=session_, **data)
```

- [ ] **Step 6: Verify every route still renders**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: PASS, all tests.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): wire the deload suggestion into Heute"
```

---

## Task 10: Live session — the toggle control

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html:21-27` (`.session-head`)
- Modify: `personal_apps/features/gym/routes.py` (`session_detail`'s active branch render, around line 460)
- Modify: `personal_apps/static/gym/gym.css` (after `.chip--neu`, around line 480)

**Interfaces:**
- Consumes: `gym.gym_toggle_deload` from Task 8; `stats.DELOAD_ALLOWED_PCTS` and `DELOAD_DEFAULT_PCT` from Task 3.
- Produces: CSS classes `.chip--deload`, `.deload-bar`, `.deload-bar__pick`, used by Tasks 11–14.

**Background:** Deload gets **no colour** — `--dim` on `--raised`, plus the literal word. `.chip--neu` already has exactly the right treatment (`border-color: var(--edge); color: var(--dim); background: transparent`), so `.chip--deload` mirrors it.

The percentage picks are shown only while nothing is completed: once a set is done, changing the percentage cannot rewrite anything, so offering the control would be a button that silently does nothing.

Every pick is a real `<button>` at ≥44×44. All CSS goes in `gym.css` — never open a second `<style>` tag in a page template, it silently swallows the next rule.

- [ ] **Step 1: Suppress the live PR flare and stagnation nudge during a deload**

**This closes a hole the rest of the feature would otherwise leave open.** `session_detail`'s active branch computes `record_set_ids` by calling `stats.is_new_best()` per completed set — the live equivalent of the finished-session PR flare. Task 4 filtered `is_new_best`'s *prior* rows, and Task 5 stops a deload session awarding records at session end, but **nothing checks whether the session being logged right now is a deload.** Without this, a set logged during a deload flares gold mid-workout and then earns no record on the recap screen — the two disagree, which is exactly the invariant `is_new_best`'s own docstring promises.

The same applies to `stagnation_counts`: its chip is a nudge to go heavier, which is wrong advice during a deliberately light session.

In `personal_apps/features/gym/routes.py`, in `session_detail`'s active branch, change the `for se in visible_exercises:` loop:

```python
    # Both signals below are progress judgements, and a deload session is not
    # an attempt at progress -- so neither is computed during one. The PR flare
    # must agree with the recap screen (session_report awards no record on a
    # deload), and a "go heavier" nudge is wrong advice beside deliberately
    # reduced weights. Guarding the whole loop rather than `continue`-ing per
    # iteration: is_deload is loop-invariant, and a per-iteration skip would
    # let a later maintainer add work above it that silently never runs.
    if not session_.is_deload:
        for se in visible_exercises:
            prior = by_exercise.get(se.exercise_id, [])
            count = stats.sessions_since_pr(prior, position=se.position)
            if count is not None and count >= stats.STAGNATION_THRESHOLD:
                stagnation_counts[se.id] = count
            # Live equivalent of the finished-session PR flare (session_report's
            # is_weight_pr/is_e1rm_pr) -- checked per completed set, against the
            # same prior-sessions-only pool, so a set can light up cyan the
            # instant it's confirmed rather than only on the recap screen an
            # hour later.
            for s in se.sets:
                if s.completed and stats.is_new_best(s.weight, s.reps, prior):
                    record_set_ids.add(s.id)
```

Keep the existing comment above the inner loop; add only the new one. Note the whole loop body shifts one indent level to the right.

- [ ] **Step 2: Pass the needed values to the active-session template**

In the same `render_template('gym/session_detail.html', ...)` call, add:

```python
        has_completed_set=any(s.completed for se in session_.exercises for s in se.sets),
        deload_pcts=stats.DELOAD_ALLOWED_PCTS,
        deload_default_pct=stats.DELOAD_DEFAULT_PCT,
```

- [ ] **Step 3: Add the chip and the toggle to the header**

In `personal_apps/templates/gym/session_detail.html`, replace the `.session-head__main` block:

```jinja
        <div class="session-head__main">
            <h1>{{ session.name or 'Workout' }}</h1>
            <span class="chip chip--live">Aktiv</span>
            {% if session.is_deload %}<span class="chip chip--deload">Deload</span>{% endif %}
        </div>
```

- [ ] **Step 4: Add the deload bar below the header**

Immediately after the closing `</header>`, before the save-error banner:

```jinja
    {# Deload: no colour of its own -- the app has exactly three semantic hues
       and this is none of them. It is a settled fact about the session, so it
       reads as dim ink plus the word. The percentage picks only appear while
       nothing is completed, because past that point changing the percentage
       can no longer rewrite anything. #}
    <div class="deload-bar{{ ' is-on' if session.is_deload else '' }}">
        <form method="post" action="{{ url_for('gym.gym_toggle_deload', session_id=session.id) }}">
            <input type="hidden" name="on" value="{{ '0' if session.is_deload else '1' }}">
            <input type="hidden" name="pct" value="{{ session.deload_pct or deload_default_pct }}">
            <button type="submit" class="btn btn--ghost btn--sm deload-bar__toggle">
                {{ 'Deload beenden' if session.is_deload else 'Als Deload markieren' }}
            </button>
        </form>
        {% if session.is_deload %}
        <span class="label deload-bar__state">
            {{ session.deload_pct or deload_default_pct }} % vom Arbeitsgewicht
        </span>
        {% if not has_completed_set %}
        <div class="deload-bar__picks">
            {% for pct in deload_pcts %}
            <form method="post" action="{{ url_for('gym.gym_toggle_deload', session_id=session.id) }}">
                <input type="hidden" name="on" value="1">
                <input type="hidden" name="pct" value="{{ pct }}">
                <button type="submit"
                        class="deload-bar__pick{{ ' is-active' if pct == session.deload_pct else '' }}"
                        {% if pct == session.deload_pct %}aria-current="true"{% endif %}>{{ pct }} %</button>
            </form>
            {% endfor %}
        </div>
        {% endif %}
        {% endif %}
    </div>
```

- [ ] **Step 5: Add the CSS**

In `personal_apps/static/gym/gym.css`, after the `.chip--neu` rule:

```css
/* Deload carries no hue: the app has exactly three semantic colours and a
   deliberately light session is none of them. It is a settled fact, so it
   reads as dim ink plus the word -- same treatment as .chip--neu. */
.chip--deload { border-color: var(--edge); color: var(--dim); background: transparent; }

.deload-bar {
  display: flex; align-items: center; flex-wrap: wrap;
  gap: var(--sp-3); margin-block-end: var(--sp-4);
}
.deload-bar.is-on {
  padding: var(--sp-3); border-radius: var(--r-panel); background: var(--raised);
}
.deload-bar__toggle { min-block-size: 44px; }
.deload-bar__state { color: var(--dim); font-variant-numeric: tabular-nums; }
.deload-bar__picks { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.deload-bar__pick {
  min-inline-size: 44px; min-block-size: 44px;
  padding-inline: var(--sp-3);
  border: 1px solid var(--edge); border-radius: var(--r-control);
  background: transparent; color: var(--dim);
  font: inherit; font-variant-numeric: tabular-nums;
  cursor: pointer; transition: color 120ms ease-out, border-color 120ms ease-out;
}
.deload-bar__pick.is-active { border-color: var(--edge-hi); color: var(--ink); }
```

If any custom property used above (`--sp-2`, `--sp-3`, `--sp-4`, `--r-panel`, `--r-control`, `--raised`, `--edge`, `--edge-hi`, `--dim`, `--ink`) does not exist, grep `gym.css` for the correct name and use that — do **not** invent a new token.

- [ ] **Step 6: Confirm the reduced-motion block covers the new transition**

```bash
cd personal_apps && grep -n "prefers-reduced-motion" -A 12 static/gym/gym.css
```

Expected: a block containing a blanket `transition: none` (typically on `*` or a broad selector). If it only lists specific selectors, add `.deload-bar__pick` to it.

- [ ] **Step 7: Verify in the browser**

Start the app, open an active session, and confirm: the toggle marks the session, the chip appears, the weights drop, and the picks vanish once a set is completed.

```bash
cd personal_apps && python -c "from app import app; app.run(port=5001, debug=False)"
```

Then use python-playwright (not the Browser MCP) to screenshot at 390×844 and read the PNG:

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 390, 'height': 844})
    pg.goto('http://localhost:5001/gym')
    pg.screenshot(path='../scratch-deload-heute.png', full_page=True)
    b.close()
"
```

Adjust the URL to an active session's path. Read the PNG with the Read tool and confirm the bar renders with no colour of its own and the picks are ≥44 px.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/features/gym/routes.py personal_apps/static/gym/gym.css
git commit -m "feat(gym): add the deload toggle to the live session header"
```

---

## Task 11: Finished session — chip, verdict, advice, retroactive toggle

**Files:**
- Modify: `personal_apps/templates/gym/session_finished.html:21-50` and the advice block around line 140

**Interfaces:**
- Consumes: `is_deload` and `deload_pct` from Task 5/9; `.chip--deload` and `.deload-bar` from Task 10; `gym.gym_toggle_deload` from Task 8.
- Produces: nothing.

**Background:** Two real bugs to fix, not just decoration:

1. The verdict's existing `total_volume_delta_pct <= -5` branch renders *"Leichter als sonst — −35 % gegenüber deinem Schnitt"*, which frames a deload that worked exactly as intended as a shortfall.
2. The advice block would tell the lifter to add 2.5 kg to a lift they deliberately went light on. Task 5 already forces `verdict` to `None` on a deload so `advice` comes back empty, but the template must not assume it.

The deload branch goes **after** `total_sets == 0` (an empty session is empty regardless of its label) and **before** every volume branch.

- [ ] **Step 1: Add the chip**

```jinja
        <div class="session-head__main">
            <h1>{{ session.name or 'Workout' }}</h1>
            <span class="chip chip--done">Beendet</span>
            {% if session.is_deload %}<span class="chip chip--deload">Deload</span>{% endif %}
        </div>
```

- [ ] **Step 2: Add the verdict branch**

In the `<p class="session-verdict...">` block, insert directly after the `total_sets == 0` branch:

```jinja
        {%- elif session.is_deload -%}
        Deload — {{ deload_pct or 70 }} %. Bewusst leichter.
```

Extend the comment above the block:

```jinja
       red delete button, which is a receipt, not a debrief. Every branch says
       something: the zero-record case gets a real substitute rather than
       falling through to silence, which is what made the screen feel empty on
       an ordinary day.

       The deload branch sits after the empty-session case (an empty session is
       empty whatever it is labelled) and before every volume branch: without
       it, a deload that worked exactly as intended falls through to "Leichter
       als sonst -- -35 % gegenueber deinem Schnitt", which frames the point of
       the session as a shortfall. #}
```

- [ ] **Step 3: Suppress the volume comparison in the stat band**

The `.stat-grid` block renders a delta against your average. On a deload that number is arithmetically correct and meaningless — the session was *supposed* to be lighter. Change the `Volumen` stat:

```jinja
        <div class="stat">
            <span class="stat__label">Volumen</span>
            <span class="stat__value">{{ total_volume }} kg</span>
            {# No delta on a deload: comparing a deliberately light session
               against the normal average produces a number that is correct
               and meaningless. #}
            {% if total_volume_delta_pct is not none and not session.is_deload %}
            <span class="stat__delta{{ ' is-up' if total_volume_delta_pct >= 0 else '' }}">{{ '%+d'|format(total_volume_delta_pct) }} % ggü. Ø</span>
            {% elif session.is_deload %}
            <span class="stat__delta">{{ deload_pct or 70 }} % Deload</span>
            {% endif %}
        </div>
```

- [ ] **Step 4: Guard the advice block**

The `Nächstes Mal` section currently opens with `{% if advice %}` (around line 137). Change it to:

```jinja
    {% if advice and not session.is_deload %}
```

Task 5 already forces `verdict` to `None` on a deload, so `advice` comes back empty — this is belt-and-braces so the template does not depend on that invariant holding forever.

- [ ] **Step 5: Add the retroactive toggle**

At the end of the page, alongside the existing "Sätze korrigieren" / delete affordances, add:

```jinja
    {# Retroactively labelling a workout you already did is the flow this
       feature was built for. It is label-only: every set is already completed,
       so gym_toggle_deload rewrites nothing. #}
    <div class="deload-bar{{ ' is-on' if session.is_deload else '' }}">
        <form method="post" action="{{ url_for('gym.gym_toggle_deload', session_id=session.id) }}">
            <input type="hidden" name="on" value="{{ '0' if session.is_deload else '1' }}">
            <input type="hidden" name="pct" value="{{ session.deload_pct or 70 }}">
            <button type="submit" class="btn btn--ghost btn--sm deload-bar__toggle">
                {{ 'Deload-Markierung entfernen' if session.is_deload else 'War ein Deload' }}
            </button>
        </form>
        {% if session.is_deload %}
        <span class="label deload-bar__state">{{ session.deload_pct or 70 }} % vom Arbeitsgewicht</span>
        {% endif %}
    </div>
```

- [ ] **Step 6: Verify**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: PASS — `test_session_pages_render_for_every_finished_session` covers this template against real data.

Then mark a real finished session as a deload through the UI and screenshot it with python-playwright at 390×844. Confirm the verdict reads *"Deload — 70 %. Bewusst leichter."* and no stagnation advice appears.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/templates/gym/session_finished.html
git commit -m "feat(gym): render deload state on the finished session page"
```

---

## Task 12: History — chip on the row

**Files:**
- Modify: `personal_apps/templates/gym/verlauf.html:70-76` (`.verlauf-row__stats`)

**Interfaces:**
- Consumes: `.chip--deload` from Task 10.
- Produces: nothing.

- [ ] **Step 1: Add the chip**

```jinja
            <div class="verlauf-row__stats">
                <span class="load"><span class="load__val">{{ entry.volume }}</span><span class="load__unit">kg</span></span>
                {% if entry.session.is_deload %}
                <span class="chip chip--deload">Deload</span>
                {% endif %}
                {% if entry.record_count %}
                <span class="chip chip--record">{{ entry.record_count }} {{ 'Rekord' if entry.record_count == 1 else 'Rekorde' }}</span>
                {% endif %}
            </div>
```

The deload chip goes **before** the record chip: a deload session cannot hold a record (Task 5), so the two never appear together, and this ordering puts the label nearer the volume figure it explains.

- [ ] **Step 2: Verify**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -k verlauf -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/templates/gym/verlauf.html
git commit -m "feat(gym): mark deload sessions in the history list"
```

---

## Task 13: Heute — the suggestion and the marked tonnage weeks

**Files:**
- Modify: `personal_apps/templates/gym/heute.html:186-240`
- Modify: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: `deload_suggestion` from Task 9; `week.has_deload` from Task 6.
- Produces: CSS classes `.deload-note`, `.vbar--deload`.

**Background:** The suggestion is the **lead element of the existing "Steht still" panel**, not a new panel — repeated identical cards are banned. The tonnage chart is plain CSS `.vbar` divs, not Chart.js, so marking a week is just a modifier class.

- [ ] **Step 1: Add the suggestion**

In `heute.html`, inside the "Steht still" panel, directly after the `<div class="section-head">` line:

```jinja
            {# The lead element of this panel rather than a panel of its own:
               it is the same data read more narrowly (only the active
               rotation), and a page of near-identical panels is exactly what
               the brief bans. #}
            {% if deload_suggestion %}
            <p class="deload-note">
                {{ deload_suggestion.count }} aktive Übungen stehen still — ein Deload könnte fällig sein.
            </p>
            {% endif %}
```

- [ ] **Step 2: Mark deload weeks in the tonnage bars**

Change the `.vbar` loop:

```jinja
                {% for week in tonnage %}
                <div class="vbar{{ ' is-live' if week.is_current else '' }}{{ ' vbar--deload' if week.has_deload else '' }}"
                     style="height:{{ ((week.volume / peak) * 100)|round(1) }}%"></div>
                {% endfor %}
```

And extend the note below the chart, after the existing `tonnage__note` paragraph:

```jinja
            {% set deload_weeks = tonnage|selectattr('has_deload')|list %}
            {% if deload_weeks %}
            <p class="label tonnage__note">Gedimmte Balken: Deload-Wochen — der Einbruch ist beabsichtigt.</p>
            {% endif %}
```

Extend the existing comment above the chart:

```jinja
            {# is_current is always the last bucket (stats.weekly_tonnage's own
               contract) -- lit amber AND spelled out below, so a short bar
               from a week that's still running never reads as a decline.
               has_deload is marked the same way, for the same reason: an
               unexplained dip reads as a collapse. #}
```

- [ ] **Step 3: Add the CSS**

In `personal_apps/static/gym/gym.css`, beside the existing `.vbar` rules:

```css
/* A deload week's dip is deliberate, so the bar is dimmed and spelled out
   below the chart rather than left looking like a collapse. No hue: this is
   an explanation, not a fourth semantic state. */
.vbar--deload { opacity: 0.45; }

.deload-note {
  margin-block-end: var(--sp-3);
  color: var(--dim);
  font-variant-numeric: tabular-nums;
}
```

Verify `.vbar` does not already set `opacity` — if it does, place `.vbar--deload` after it so the cascade resolves correctly.

- [ ] **Step 4: Verify**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -k dashboard -v
```

Expected: PASS.

Then screenshot `/gym` with python-playwright at 390×844 and 1280×800, and read both PNGs. Confirm: the suggestion sits inside the "Steht still" panel (no new panel), and any deload week's bar is visibly dimmed with the note below.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/heute.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): surface the deload suggestion and mark deload weeks"
```

---

## Task 14: Exercise detail — mark deload rows and fix two invariants they break

**Files:**
- Modify: `personal_apps/features/gym/stats.py` (`exercise_progress`)
- Modify: `personal_apps/templates/gym/exercise_detail.html:58-93` and `:129-138`
- Test: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: `row.is_deload` on each `table` entry from Task 5; `.chip--deload` from Task 10.
- Produces: `exercise_progress()` gains `'last_progression'` — the newest non-deload table row, or `None`.

**Background:** Keeping deload rows in the table (Task 5, correct) breaks two invariants this template silently relied on. **Both are real bugs, not cosmetics.**

1. **The stagnation advice reads `table[0]`** — the newest row. That row can now *be* the deload, so the page would say *"Seit 5 Workouts auf 60 kg — auf 62,5 kg gehen"* about a weight you deliberately went light on. It must read the newest **non-deload** row instead.
2. **`pr_weight` / `pr_e1rm` can now be `None` while `table` is non-empty** — an exercise whose only history is a deload. The `.pr-grid` block is gated on `{% if table %}` and dereferences `pr_weight.weight` unguarded. Jinja's default `Undefined` renders that as an empty string rather than raising, so it is a silently blank card, not a 500 — but it is still broken output that was impossible before this change.

- [ ] **Step 1: Write the failing test**

Add to `personal_apps/tests/test_gym_stats.py`:

```python
def test_exercise_progress_reports_the_last_non_deload_row():
    # The newest row is the deload; stagnation advice must not quote its
    # weight back as the weight you are stuck at.
    rows = [perf([(85.0, 8)], started_at=day(0)),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert progress['table'][0]['is_deload'] is True          # newest overall
    assert progress['last_progression']['best_weight'] == 85.0


def test_exercise_progress_has_no_last_progression_when_only_deloads_exist():
    rows = [perf([(60.0, 8)], started_at=day(0), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert progress['last_progression'] is None
    assert progress['pr_weight'] is None
    assert progress['table'] != []      # the row is still reported
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -k "last_progression or only_deloads" -v
```

Expected: FAIL — `KeyError: 'last_progression'`.

- [ ] **Step 3: Add `last_progression` to `exercise_progress`**

In `personal_apps/features/gym/stats.py`, add to the returned dict, after `'sessions_since_pr': ...`:

```python
        # The newest row that counts as an attempt at progress. `table[0]` is
        # the newest row of ANY kind and can be a deload, so anything quoting
        # "the weight you are stuck at" must read this instead -- otherwise
        # the stagnation advice tells you to add 2.5 kg to a weight you went
        # deliberately light on. None when there is no non-deload history.
        'last_progression': next(
            (row for row in table if not row['is_deload']), None),
```

This must be placed after `table` is built (it reads the already-constructed list).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Mark deload rows in the history table**

In `personal_apps/templates/gym/exercise_detail.html`, change the table body loop (around line 129):

```jinja
                    <tbody>
                        {# Deload rows stay in this table: they are the record
                           of what was performed, and dropping them would leave
                           unexplained gaps in the history and holes in the
                           chart. They are labelled instead, because a 60 kg row
                           between two 85 kg rows otherwise reads as a bad
                           session. They hold no records -- exercise_progress
                           excludes them from pr_weight/pr_e1rm/state. #}
                        {% for row in table %}
                        {% set is_record = (pr_e1rm and row.started_at == pr_e1rm.started_at) or (pr_weight and row.started_at == pr_weight.started_at) %}
                        <tr class="{{ 'is-record' if is_record else '' }}{{ ' is-deload' if row.is_deload else '' }}">
                            <td>{{ row.started_at.strftime('%d.%m.%Y') }}{% if row.is_deload %} <span class="chip chip--deload">Deload</span>{% endif %}</td>
                            <td>{{ row.position }}</td>
                            <td>{{ row.sets_display }}</td>
                            <td class="num">{{ row.volume }} kg</td>
                            <td class="num">{{ row.e1rm }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
```

- [ ] **Step 6: Fix the stagnation advice to read `last_progression`**

Replace the `{% if state == 'stagniert' %}` block (around line 80):

```jinja
            {# Reads last_progression, NOT table[0]: the newest row can be a
               deload, and quoting its weight back would tell you to add 2.5 kg
               to a weight you deliberately went light on. #}
            {% if state == 'stagniert' and last_progression %}
            <div class="note-stall">
                <span class="note-stall__label">Stagniert</span>
                Seit {{ sessions_since_pr }} Workouts auf {{ last_progression.best_weight }} kg (Position {{ last_progression.position }}) — auf
                <strong>{{ (last_progression.best_weight + 1.25) if exercise.is_unilateral else (last_progression.best_weight + 2.5) }} kg</strong>
                gehen, notfalls 2 Wdh. weniger.
            </div>
            {% endif %}
```

- [ ] **Step 7: Guard the PR cards**

Replace the `.pr-grid` block (around line 64) so it cannot render blank cards for an exercise whose only history is a deload:

```jinja
            {# pr_weight/pr_e1rm are None when every session for this exercise
               was a deload -- table is non-empty but nothing in it holds a
               record. Before deloads existed, a non-empty table always implied
               a PR, so this block was unguarded. #}
            {% if pr_weight and pr_e1rm %}
            <div class="pr-grid">
                <div class="pr-card">
                    <div class="label">Bestes Gewicht</div>
                    <div class="val">{{ pr_weight.weight }} kg</div>
                    <div class="sub">{{ pr_weight.reps }} Wdh. · Pos. {{ pr_weight.position }} · {{ pr_weight.started_at.strftime('%d.%m.%Y') }}</div>
                </div>
                <div class="pr-card">
                    <div class="label">Bestes e1RM</div>
                    <div class="val">{{ pr_e1rm.e1rm }} kg</div>
                    <div class="sub">{{ pr_e1rm.weight }} kg × {{ pr_e1rm.reps }} · Pos. {{ pr_e1rm.position }} · {{ pr_e1rm.started_at.strftime('%d.%m.%Y') }}</div>
                </div>
            </div>
            {% else %}
            <p class="empty">Noch kein Rekord — bisher nur Deload-Sätze protokolliert.</p>
            {% endif %}
```

- [ ] **Step 8: Add the row dimming**

In `personal_apps/static/gym/gym.css`, beside the `.table` rules:

```css
/* A deload row in the history table is dimmed as well as labelled, so a
   lighter number in the middle of a progression doesn't read as a bad day. */
.table tr.is-deload td { color: var(--dim); }
```

- [ ] **Step 9: Verify**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS. `test_exercise_detail_renders_for_every_exercise` covers this template against every real exercise.

Then screenshot an exercise detail page for an exercise with a deload in its history at 390×844 with python-playwright, and read the PNG. Confirm the deload row is dimmed and labelled, and that any stagnation advice quotes the normal working weight, not the deload weight.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/templates/gym/exercise_detail.html personal_apps/static/gym/gym.css personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): mark deload rows on exercise detail and fix the advice they broke"
```

---

## Task 15: Document the deload state and verify the whole feature

**Files:**
- Modify: `personal_apps/PRODUCT.md` (§4.2, the state model table)

**Interfaces:**
- Consumes: everything.
- Produces: nothing.

**Background:** §4.2 of `PRODUCT.md` is the load-bearing state model — five states, each carrying a word or a shape as well as a colour. Deload is a sixth surface-level label but deliberately *not* a sixth semantic state: it has no hue, and it describes a session rather than a set's progress. Document it so a future designer does not "fix" it by giving it a colour.

- [ ] **Step 1: Add the note to `PRODUCT.md`**

Directly after the §4.2 state table and its bolded rule line, add:

```markdown
**Deload is a label, not a sixth state.** A session can be marked as a
deliberately light one. It carries **no hue** — the three-hue rule stands — and
renders as `--dim` ink plus the literal word `Deload`, the same treatment as
the `neu` chip. It describes a whole session rather than one set's progress,
and its job is to stop the statistics reading a planned light week as a
plateau. Do not promote it to a colour.
```

- [ ] **Step 2: Run the full test suite**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS, every test.

- [ ] **Step 3: Run the anti-pattern detector**

```bash
cd personal_apps && grep -rn "🏋\|💪\|📊\|🔥" templates/gym/ ; echo "exit: $?"
```

Expected: no matches (`exit: 1` from grep finding nothing). Emoji as icons are banned by §4.6.

- [ ] **Step 4: Full visual verification**

Screenshot all five changed pages at 390×844 and 1280×800 with python-playwright, and read every PNG:

```bash
python -c "
from playwright.sync_api import sync_playwright
paths = {'heute': '/gym', 'verlauf': '/gym/verlauf', 'uebungen': '/gym/uebungen'}
with sync_playwright() as p:
    b = p.chromium.launch()
    for label, path in paths.items():
        for name, w, h in (('mobile', 390, 844), ('desktop', 1280, 800)):
            pg = b.new_page(viewport={'width': w, 'height': h})
            pg.goto('http://localhost:5001' + path)
            pg.screenshot(path='../scratch-{}-{}.png'.format(label, name), full_page=True)
            pg.close()
    b.close()
"
```

Add the session detail and finished session URLs for a real session id. Confirm on every page:
- Deload renders with no colour of its own.
- The word `Deload` is always present, never colour alone.
- No horizontal overflow at 390 px.
- The picks and toggle are ≥44×44.

- [ ] **Step 5: Verify 200 % text scaling still passes**

The gym app was recently fixed for WCAG 1.4.4 at 200 % text. The new deload bar is a flex container and can reintroduce overflow.

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 390, 'height': 844})
    pg.goto('http://localhost:5001/gym')
    pg.add_style_tag(content='html { font-size: 32px !important; }')
    print('scrollWidth', pg.evaluate('document.documentElement.scrollWidth'))
    b.close()
"
```

Expected: `scrollWidth` ≤ 390. If larger, add `min-inline-size: 0` to `.deload-bar` and its flex children, and re-check. Repeat for the session detail page.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/PRODUCT.md
git commit -m "docs(gym): document deload as a label, not a sixth state"
```

---

## Verification Checklist

Run before considering the feature done:

- [ ] `cd personal_apps && python -m pytest tests/ -v` — all pass
- [ ] A new session started from a template after a deload seeds at the **normal** weight (Task 9's regression test)
- [ ] A deload session awards no records and produces no stagnation advice
- [ ] The deload toggle works on an active session, a finished session, and a session with one completed set
- [ ] Toggling off twice does not walk the weights downward
- [ ] Stagnation advice on exercise detail quotes the last **normal** working weight, never the deload weight
- [ ] An exercise whose only history is a deload renders without blank PR cards
- [ ] Every deload surface carries the word `Deload`, never colour alone
- [ ] No fourth semantic hue was introduced (`grep -n "^  --" personal_apps/static/gym/gym.css` — the token list is unchanged)
- [ ] No horizontal overflow at 390 px, at 100 % and 200 % text
- [ ] No emoji in any gym template

# Actual Rest and Pre-Start Briefing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record when each set was completed so the app can report real rest, and name the stalling lift inside the routine you are about to start.

**Architecture:** One nullable column, `gym_session_sets.completed_at`, written wherever a set is completed and cleared wherever one is un-completed. Two pure functions in `features/gym/stats.py` turn those timestamps into rest gaps and medians; two templates read them. The briefing is a filter over `stall_report`, which Heute already computes — no new data and no new query.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy + Flask-SQLAlchemy, Flask-Migrate/Alembic, MySQL (pymysql), pytest.

**Spec:** `docs/superpowers/specs/2026-08-03-gym-rest-and-briefing-design.md`

## Global Constraints

- Branch: `dev_personal`. Do not commit to `main`.
- All paths relative to `personal_apps/`. Run pytest and `flask db upgrade` from there.
- Tests run against the **real local development database** — disposable dev data. Every fixture that creates rows deletes them in a `finally`.
- User-facing copy is **German**; code, comments and commit messages English.
- **A gap over 600 seconds is an interruption, not rest, and is not counted.**
- **Planned rest belongs to the set that ENDS the gap** — you finish a set of Bankdrücken and rest Bankdrücken's time. That is the earlier set of each consecutive pair.
- **The habit figure is a median over every counted gap in history, pooled** — not a median of per-session medians.
- **Nothing is retroactive.** Every existing set has `completed_at` NULL. Both readouts render nothing rather than reporting zero.
- `features/gym/stats.py` takes **no ORM dependency** — it is pure functions over values, and its tests pass plain objects. Do not import models into it.
- Migration revision id `d1f6b83c25e9`, `down_revision = 'c8e5f14a9b32'`. Confirm the head with `flask db heads` first; if it differs, stop and report.
- `tests/conftest.py` provides `_admin_id()`, `client`, `anon_client`, `acting_as`. Leave it unchanged.

---

## File Structure

**Modified:**
- `models.py` — `SessionSet.completed_at`.
- `features/gym/routes.py` — stamp on completion, clear on un-completion; pass the new figures to two templates.
- `features/gym/stats.py` — `rest_gaps()` and `rest_medians()`, pure.
- `templates/gym/session_finished.html` — the per-session split.
- `templates/gym/statistik.html` — the habit figure, inside the existing "Wie du trainierst" block.
- `templates/gym/heute.html` — the briefing line on the lead routine card.
- `static/gym/gym.css` — one class for the briefing line.

**Created:**
- `migrations/versions/d1f6b83c25e9_add_completed_at_to_session_sets.py`
- `tests/test_gym_rest.py`

---

### Task 1: The column, and everywhere it is written

Folded into one task: a column nobody writes is dead weight, and a column that is written but never cleared silently produces fiction the first time someone un-ticks a set.

**Files:**
- Modify: `models.py` (`SessionSet`)
- Create: `migrations/versions/d1f6b83c25e9_add_completed_at_to_session_sets.py`
- Modify: `features/gym/routes.py` — `gym_add_set`, `gym_toggle_set_complete`
- Test: `tests/test_gym_rest.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `SessionSet.completed_at: datetime | None` — set to `dt.datetime.utcnow()` when a set becomes completed, `None` whenever it is not completed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gym_rest.py`:

```python
"""Rest timing: the column, the pure maths, and the two readouts.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def scratch_live_set():
    """An unfinished session with one exercise and one uncompleted set.

    Yields (session_id, session_exercise_id, set_id, exercise_id).
    """
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    ids = None
    with flask_app.app_context():
        exercise = Exercise(name='pytest rest lift', muscle_group='Brust',
                            user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        session_ = WorkoutSession(name='pytest rest session',
                                  started_at=dt.datetime.utcnow(),
                                  user_id=_admin_id())
        se = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=False)]
        session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, session_.exercises[0].id,
               session_.exercises[0].sets[0].id, exercise.id)
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, ids[0])
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, ids[3])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_the_set_table_can_record_when_a_set_landed():
    from models import SessionSet
    assert hasattr(SessionSet, 'completed_at'), 'SessionSet has no completed_at'
    assert SessionSet.__table__.c.completed_at.nullable is True, \
        'completed_at must be nullable -- every set that predates it has none'


def test_completing_a_set_stamps_it(client, scratch_live_set):
    from extensions import db
    from models import SessionSet
    _, _, set_id, _ = scratch_live_set

    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '1', 'weight': '40.0', 'reps': '8'})

    with flask_app.app_context():
        stored = db.session.get(SessionSet, set_id)
        assert stored.completed is True
        assert stored.completed_at is not None, 'completed but never stamped'


def test_un_completing_a_set_clears_the_stamp(client, scratch_live_set):
    """Otherwise re-ticking measures a gap that includes however long you spent
    deciding, and the number silently becomes fiction."""
    from extensions import db
    from models import SessionSet
    _, _, set_id, _ = scratch_live_set

    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '1', 'weight': '40.0', 'reps': '8'})
    client.post(f'/gym/set/{set_id}/toggle_complete',
                data={'completed': '0', 'weight': '40.0', 'reps': '8'})

    with flask_app.app_context():
        stored = db.session.get(SessionSet, set_id)
        assert stored.completed is False
        assert stored.completed_at is None, 'a stale stamp survived un-completing'


def test_a_set_appended_mid_workout_is_stamped(client, scratch_live_set):
    """gym_add_set creates a set already completed, so it must stamp it too --
    it is the path used every time you append past the planned sets."""
    from extensions import db
    from models import SessionExercise
    _, se_id, _, _ = scratch_live_set

    client.post(f'/gym/session-exercise/{se_id}/sets/add',
                data={'weight': '42.5', 'reps': '6'})

    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        appended = [s for s in se.sets if s.completed]
        assert appended, 'no completed set was appended'
        assert all(s.completed_at is not None for s in appended), \
            'an appended set was left unstamped'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_rest.py -v`
Expected: FAIL — `AssertionError: SessionSet has no completed_at`

- [ ] **Step 3: Add the column**

In `models.py`, inside `SessionSet`, after `completed`:

```python
    # When this set actually landed. The rest between two sets is the gap
    # between their stamps, which is the only way the app can compare the rest
    # you planned against the rest you took -- rest_ends_at is a display target
    # for the countdown, not a record that anything happened.
    #
    # Cleared whenever the set stops being completed: a stale stamp would make
    # a re-tick measure however long you spent deciding.
    completed_at        = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/d1f6b83c25e9_add_completed_at_to_session_sets.py`:

```python
"""add completed_at to session sets

Revision ID: d1f6b83c25e9
Revises: c8e5f14a9b32
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f6b83c25e9'
down_revision = 'c8e5f14a9b32'
branch_labels = None
depends_on = None


def upgrade():
    # No backfill. rest_ends_at is a countdown target, not a record of when a
    # set landed, so deriving history from it would invent data. Every existing
    # set keeps NULL and the readouts stay silent until real sessions arrive.
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.drop_column('completed_at')
```

- [ ] **Step 5: Apply the migration**

Run: `flask db upgrade`
Expected: `Running upgrade c8e5f14a9b32 -> d1f6b83c25e9, add completed_at to session sets`

- [ ] **Step 6: Stamp on completion, clear on un-completion**

In `features/gym/routes.py`, `gym_toggle_set_complete`. Find the line that assigns `set_.completed`:

```python
    set_.completed = (wanted == '1') if wanted in ('0', '1') else (not set_.completed)
```

and add immediately after it:

```python
    # The stamp follows the flag in both directions. Leaving it behind on an
    # un-complete would make the next tick measure the wrong interval.
    set_.completed_at = dt.datetime.utcnow() if set_.completed else None
```

In `gym_add_set`, the `SessionSet(...)` construction already passes
`completed=True`. Add the stamp beside it:

```python
            completed=True,  # logged live via this form, so it's inherently just-performed
            completed_at=dt.datetime.utcnow(),
```

Confirm both sites and that nothing else sets `completed`:

Run: `grep -n "\.completed = \|completed=True" features/gym/routes.py`
Expected: the two sites above, each with a `completed_at` beside it. Any other hit is a third write path and must be reported, not silently left.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_rest.py -v`
Expected: PASS, 4 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Verify the migration is reversible**

Run: `flask db downgrade` then `flask db upgrade`
Expected: both succeed. Re-run `python -m pytest tests/test_gym_rest.py -v` — still PASS.

- [ ] **Step 9: Commit**

```bash
git add models.py migrations/versions/d1f6b83c25e9_add_completed_at_to_session_sets.py features/gym/routes.py tests/test_gym_rest.py
git commit -m "feat(gym): record when a set actually landed"
```

---

### Task 2: The rest maths, as pure functions

**Files:**
- Modify: `features/gym/stats.py` (append)
- Test: `tests/test_gym_stats.py`

**Interfaces:**
- Consumes: nothing — deliberately no ORM dependency.
- Produces, in `features.gym.stats`:
  - `REST_GAP_CAP_SECONDS = 600`
  - `rest_gaps(entries) -> list[tuple[int, int | None]]` — `entries` is an iterable of `(completed_at, planned_seconds)` for **one session's** completed sets, in any order. Returns `(actual_seconds, planned_seconds)` per consecutive pair, gaps over the cap dropped.
  - `rest_medians(gaps) -> tuple[int, int] | None` — `(median_planned, median_actual)` over the pooled gaps, or `None` when there is nothing to report or no gap carries a planned time.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_stats.py`:

```python
# --- rest timing -----------------------------------------------------------


def _at(minute, second=0):
    import datetime as dt
    return dt.datetime(2026, 8, 3, 18, minute, second)


def test_rest_gaps_measures_the_interval_between_consecutive_sets():
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 150), (_at(5), 150)])
    assert [actual for actual, _ in gaps] == [180, 120]


def test_rest_gaps_sorts_by_when_the_set_landed():
    """Callers hand over whatever order the rows came back in."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(5), 150), (_at(0), 150), (_at(3), 150)])
    assert [actual for actual, _ in gaps] == [180, 120]


def test_rest_gaps_takes_the_planned_time_from_the_set_that_ended_the_gap():
    """You finish a set of Bankdrücken and rest Bankdrücken's time -- so the
    earlier set of each pair supplies the plan, not the one you are about to do."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 90)])
    assert gaps == [(180, 150)]


def test_rest_gaps_drops_an_interruption():
    """A phone call between sets is not rest. Over the cap it is not counted at
    all, rather than counted and averaged away."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 150), (_at(30), 150)])
    assert [actual for actual, _ in gaps] == [180]


def test_rest_gaps_of_a_single_set_is_empty():
    """The first completed set of a session has nothing before it."""
    from features.gym import stats
    assert stats.rest_gaps([(_at(0), 150)]) == []
    assert stats.rest_gaps([]) == []


def test_rest_medians_reports_planned_against_actual():
    from features.gym import stats
    gaps = [(180, 150), (200, 150), (240, 150)]
    assert stats.rest_medians(gaps) == (150, 200)


def test_rest_medians_is_none_without_data():
    """Nothing is retroactive, so this is the normal state on the day it ships
    -- the caller must be able to say "noch keine Daten" rather than "0"."""
    from features.gym import stats
    assert stats.rest_medians([]) is None
    assert stats.rest_medians([(180, None), (200, None)]) is None


def test_rest_medians_ignores_gaps_with_no_planned_time():
    """An exercise with no rest configured contributes an actual but cannot
    contribute a plan, and must not drag the planned median toward zero."""
    from features.gym import stats
    assert stats.rest_medians([(180, 150), (200, None), (220, 150)]) == (150, 200)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_stats.py -v -k rest_`
Expected: FAIL — `AttributeError: module 'features.gym.stats' has no attribute 'rest_gaps'`

- [ ] **Step 3: Write the functions**

Append to `features/gym/stats.py`:

```python
# A gap longer than this is an interruption, not rest -- a phone call between
# sets should not become part of what your rest looks like. Long enough for a
# genuinely slow superset, short enough to exclude walking away. Uncapped, one
# such gap distorts everything downstream.
REST_GAP_CAP_SECONDS = 600


def rest_gaps(entries):
    """Rest taken between consecutive sets of ONE session.

    `entries` is an iterable of (completed_at, planned_seconds) for that
    session's completed sets, in any order -- sorted here, because callers hand
    over whatever order the rows arrived in.

    Returns [(actual_seconds, planned_seconds), ...], one per consecutive pair.
    The plan comes from the set that ENDED the gap: you finish a set and rest
    that exercise's time. Gaps over REST_GAP_CAP_SECONDS are dropped entirely.

    Deliberately includes walking to the next machine and setting it up. That
    time is not lifting, and it is a real part of why a session takes as long
    as it does.
    """
    ordered = sorted((e for e in entries if e[0] is not None), key=lambda e: e[0])
    gaps = []
    for (earlier_at, earlier_planned), (later_at, _) in zip(ordered, ordered[1:]):
        actual = int((later_at - earlier_at).total_seconds())
        if 0 <= actual <= REST_GAP_CAP_SECONDS:
            gaps.append((actual, earlier_planned))
    return gaps


def rest_medians(gaps):
    """(median_planned, median_actual) over pooled gaps, or None.

    Pooled over every gap rather than averaged per session: the question is
    what a typical rest of yours looks like, and a twenty-set session carries
    more evidence about that than a six-set one.

    Median rather than mean so one slow day cannot move it -- which also makes
    the cap above less load-bearing, since an outlier that slips past it shifts
    a median far less than a mean.

    None when there is nothing to report, so the caller says "noch keine Daten"
    instead of a confident zero.
    """
    actuals = [actual for actual, _ in gaps]
    planned = [plan for _, plan in gaps if plan is not None]
    if not actuals or not planned:
        return None
    return int(_median(planned)), int(_median(actuals))


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_stats.py -v -k rest_`
Expected: PASS, 8 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add features/gym/stats.py tests/test_gym_stats.py
git commit -m "feat(gym): compute rest gaps and their medians"
```

---

### Task 3: The per-session split on the finished page

**Files:**
- Modify: `features/gym/routes.py` — the finished-session render
- Modify: `templates/gym/session_finished.html` (the duration line, around line 27)
- Test: `tests/test_gym_rest.py`

**Interfaces:**
- Consumes: `stats.rest_gaps` from Task 2; `SessionSet.completed_at` from Task 1.
- Produces: template variable `rest_taken_seconds: int | None` on the finished page — the sum of that session's counted gaps, or `None` when it has none.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_rest.py`:

```python
@pytest.fixture()
def finished_with_rest():
    """A finished session whose three sets landed 3 and 2 minutes apart.

    Yields (session_id, exercise_id).
    """
    import datetime as dt
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession
    ids = None
    with flask_app.app_context():
        exercise = Exercise(name='pytest rest readout lift', user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()
        started = dt.datetime.utcnow() - dt.timedelta(hours=1)
        session_ = WorkoutSession(name='pytest rest readout', started_at=started,
                                  finished_at=started + dt.timedelta(minutes=52),
                                  user_id=_admin_id())
        se = SessionExercise(exercise_id=exercise.id, position=1, rest_seconds=150)
        se.sets = [
            SessionSet(position=1, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=5)),
            SessionSet(position=2, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=8)),
            SessionSet(position=3, weight=40.0, reps=8, completed=True,
                       completed_at=started + dt.timedelta(minutes=10)),
        ]
        session_.exercises.append(se)
        db.session.add(session_)
        db.session.commit()
        ids = (session_.id, exercise.id)
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, ids[0])
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, ids[1])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_the_finished_page_reports_the_rest_it_measured(client, finished_with_rest):
    """3 minutes then 2 gives 5 minutes of counted rest."""
    session_id, _ = finished_with_rest
    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'davon 5 Minuten Pause' in html


def test_the_finished_page_says_nothing_about_rest_without_stamps(client, scratch_live_set):
    """Every set that predates the column has completed_at NULL. The page must
    not answer a question it has no data for."""
    import datetime as dt
    from extensions import db
    from models import WorkoutSession
    session_id, _, set_id, _ = scratch_live_set
    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        session_.finished_at = dt.datetime.utcnow()
        for se in session_.exercises:
            for s in se.sets:
                s.completed, s.completed_at = True, None
        db.session.commit()

    html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
    assert 'Pause' not in html, 'claimed a rest figure with no timestamps to build it from'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_rest.py -v -k finished_page`
Expected: FAIL — `assert 'davon 5 Minuten Pause' in html`

- [ ] **Step 3: Compute it in the route**

In `features/gym/routes.py`, find the `render_template('gym/session_finished.html', ...)` call. Immediately before it, add:

```python
    # Rest measured rather than planned: the gap between consecutive sets, which
    # exists only for sessions logged since completed_at was added. None means
    # "no timestamps", which the template must render as silence, not as zero.
    rest_entries = [
        (s.completed_at, se.rest_seconds if se.rest_seconds is not None
         else se.exercise.default_rest_seconds)
        for se in session_.exercises for s in se.sets
        if s.completed and s.completed_at is not None
    ]
    rest_gaps = stats.rest_gaps(rest_entries)
    rest_taken_seconds = sum(actual for actual, _ in rest_gaps) or None
```

and pass it into the render call:

```python
        rest_taken_seconds=rest_taken_seconds,
```

- [ ] **Step 4: Render it**

In `templates/gym/session_finished.html`, find the duration line (around line 27-30):

```jinja
      {% set minutes = ((session.finished_at - session.started_at).total_seconds() // 60)|int %}
```

Immediately after the element that prints `minutes`, add:

```jinja
      {#- Measured, not planned. Absent for every session logged before
          completed_at existed, and silent rather than zero in that case. -#}
      {% if rest_taken_seconds %}
      <span class="finished__rest">davon {{ (rest_taken_seconds // 60)|int }} Minuten Pause</span>
      {% endif %}
```

- [ ] **Step 5: Style it**

In `static/gym/gym.css`, next to the other `.finished__` rules:

```css
/* Sits with the duration it qualifies, quieter than it: the session length is
   the fact, the rest is the explanation. */
.finished__rest { color: var(--dim); font-size: var(--t-meta); }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_rest.py -v`
Expected: PASS, 6 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add features/gym/routes.py templates/gym/session_finished.html static/gym/gym.css tests/test_gym_rest.py
git commit -m "feat(gym): report how much of a workout was rest"
```

---

### Task 4: The habit figure on Statistik

**Files:**
- Modify: `features/gym/routes.py` — `gym_statistik`
- Modify: `templates/gym/statistik.html` — inside the existing "Wie du trainierst" block
- Test: `tests/test_gym_rest.py`

**Interfaces:**
- Consumes: `stats.rest_gaps`, `stats.rest_medians` from Task 2.
- Produces: template variable `rest_habit: tuple[int, int] | None` on Statistik — `(planned_seconds, actual_seconds)`, or `None` when no counted gap exists in the whole history.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_rest.py`:

```python
def test_statistik_reports_planned_against_actual_rest(client, finished_with_rest):
    """The fixture plans 150 s and takes 180 and 120, so the medians are
    2:30 planned against 2:30 actual -- the point is that both are stated."""
    html = client.get('/gym/statistik').get_data(as_text=True)
    assert 'Wie lange pausierst du' in html
    assert 'Du planst' in html


def test_statistik_says_nothing_about_rest_without_stamps(client):
    """With no timestamped session anywhere, the question must not be asked --
    an unanswerable question on the page reads as a broken feature."""
    from extensions import db
    from models import SessionSet
    with flask_app.app_context():
        stamped = SessionSet.query.filter(SessionSet.completed_at.isnot(None)).all()
        saved = [(s.id, s.completed_at) for s in stamped]
        for s in stamped:
            s.completed_at = None
        db.session.commit()
    try:
        html = client.get('/gym/statistik').get_data(as_text=True)
        assert 'Wie lange pausierst du' not in html
    finally:
        with flask_app.app_context():
            for set_id, when in saved:
                row = db.session.get(SessionSet, set_id)
                if row is not None:
                    row.completed_at = when
            db.session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_rest.py -v -k statistik`
Expected: FAIL — `assert 'Wie lange pausierst du' in html`

- [ ] **Step 3: Compute it in the route**

In `features/gym/routes.py`, inside `gym_statistik`, before its `render_template` call:

```python
    # Gaps are built PER SESSION and then concatenated, never across the whole
    # history at once: rest_gaps() measures consecutive pairs, and two different
    # workouts are not consecutive -- the interval from Monday's last set to
    # Wednesday's first is not a rest, it is a rest day. The cap would drop it
    # anyway, but only by accident, and an accident is not a rule.
    #
    # Pooled rather than averaged per session, because the question is what a
    # typical rest of yours looks like: a twenty-set session carries more
    # evidence about that than a six-set one.
    habit_gaps = []
    for session_ in my_sessions().filter(WorkoutSession.finished_at.isnot(None)):
        habit_gaps.extend(stats.rest_gaps([
            (s.completed_at, se.rest_seconds if se.rest_seconds is not None
             else se.exercise.default_rest_seconds)
            for se in session_.exercises for s in se.sets
            if s.completed and s.completed_at is not None
        ]))
    rest_habit = stats.rest_medians(habit_gaps)
```

Pass it into the render call:

```python
        rest_habit=rest_habit,
```

- [ ] **Step 4: Render it**

In `templates/gym/statistik.html`, inside the `<div class="read">` that follows
the "Wie du trainierst" heading, after the existing rep-range block, add:

```jinja
        {#- Measured against planned. Absent entirely before any session was
            logged with timestamps -- an unanswerable question on the page reads
            as a broken feature, not as an empty one. -#}
        {% if rest_habit %}
        <p class="read__q">Wie lange pausierst du?</p>
        <p class="read__a">
          Du planst <em>{{ '%d:%02d'|format(rest_habit[0] // 60, rest_habit[0] % 60) }}</em>,
          nimmst dir <em>{{ '%d:%02d'|format(rest_habit[1] // 60, rest_habit[1] % 60) }}</em>.
        </p>
        {% endif %}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_rest.py -v`
Expected: PASS, 8 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add features/gym/routes.py templates/gym/statistik.html tests/test_gym_rest.py
git commit -m "feat(gym): report the rest you plan against the rest you take"
```

---

### Task 5: The briefing line on the lead routine card

Independent of Tasks 1-4. No new data, no new query — `stalls` is already built for this page.

**Files:**
- Modify: `templates/gym/heute.html` — the lead routine card (around lines 155-168)
- Modify: `static/gym/gym.css`
- Test: `tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `stalls` (from `stats.stall_report`), already passed to `heute.html`. Entries carry `exercise_id`, `name`, `position`, `stuck_at`, `since`, `sessions_since_pr`, sorted worst-first.
- Produces: nothing other tasks rely on.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_routes_smoke.py`:

```python
def test_the_lead_routine_names_a_stall_inside_it(client):
    """Heute lists every stalling exercise further down the page. The card you
    are about to tap says only which exercises are in it -- so this names the
    one to watch in THIS routine, and stays quiet about the rest."""
    import datetime as dt
    from extensions import db
    from models import (Exercise, SessionExercise, SessionSet, TemplateExercise,
                        WorkoutSession, WorkoutTemplate)

    made = {'sessions': [], 'exercise': None, 'template': None}
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest briefing lift', muscle_group='Brust',
                                user_id=_admin_id())
            db.session.add(exercise)
            db.session.flush()
            made['exercise'] = exercise.id

            template = WorkoutTemplate(name='pytest briefing routine', user_id=_admin_id())
            template.exercises.append(TemplateExercise(exercise_id=exercise.id, position=1))
            db.session.add(template)
            db.session.flush()
            made['template'] = template.id

            # Five sessions at an unchanged weight is a stall by
            # stats.STAGNATION_THRESHOLD (4).
            for days_ago in (30, 24, 18, 12, 6):
                started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
                session_ = WorkoutSession(name='pytest briefing session',
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1),
                                          user_id=_admin_id(), template_id=template.id)
                se = SessionExercise(exercise_id=exercise.id, position=1)
                se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
                session_.exercises.append(se)
                db.session.add(session_)
                db.session.commit()
                made['sessions'].append(session_.id)

        html = client.get('/gym').get_data(as_text=True)
        assert 'pytest briefing lift' in html, 'the stalling lift was not named on Heute'
        assert 'lead__watch' in html, 'no briefing line on the lead card'
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            if made['template']:
                doomed = db.session.get(WorkoutTemplate, made['template'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made['exercise']:
                doomed = db.session.get(Exercise, made['exercise'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
```

- [ ] **Step 2: Write the exclusion test**

The line's whole justification is that it is narrower than the stalls section
below it. A version that names every stall you own would pass the test above and
be wrong, so this pins the difference.

Append to `tests/test_gym_routes_smoke.py`:

```python
def test_the_lead_routine_ignores_a_stall_it_does_not_contain(client):
    """An exercise stalling elsewhere in the catalogue must not appear on a card
    whose routine does not contain it -- otherwise the line is just the stalls
    section repeated, and its claim to be about THIS routine is false."""
    import datetime as dt
    from extensions import db
    from models import (Exercise, SessionExercise, SessionSet, TemplateExercise,
                        WorkoutSession, WorkoutTemplate)

    made = {'sessions': [], 'in_routine': None, 'outsider': None, 'template': None}
    try:
        with flask_app.app_context():
            in_routine = Exercise(name='pytest inroutine lift', user_id=_admin_id())
            outsider = Exercise(name='pytest outsider lift', user_id=_admin_id())
            db.session.add_all([in_routine, outsider])
            db.session.flush()
            made['in_routine'], made['outsider'] = in_routine.id, outsider.id

            # The routine contains ONLY the first exercise.
            template = WorkoutTemplate(name='pytest exclusion routine', user_id=_admin_id())
            template.exercises.append(TemplateExercise(exercise_id=in_routine.id, position=1))
            db.session.add(template)
            db.session.flush()
            made['template'] = template.id

            # Both lifts stall: five sessions at an unchanged weight.
            for days_ago in (30, 24, 18, 12, 6):
                started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
                session_ = WorkoutSession(name='pytest exclusion session',
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1),
                                          user_id=_admin_id(), template_id=template.id)
                for position, exercise_id in enumerate((in_routine.id, outsider.id), start=1):
                    se = SessionExercise(exercise_id=exercise_id, position=position)
                    se.sets = [SessionSet(position=1, weight=40.0, reps=8, completed=True)]
                    session_.exercises.append(se)
                db.session.add(session_)
                db.session.commit()
                made['sessions'].append(session_.id)

        html = client.get('/gym').get_data(as_text=True)
        watch = html.split('lead__watch', 1)[1].split('</p>', 1)[0] if 'lead__watch' in html else ''
        assert 'pytest outsider lift' not in watch,             'the briefing named a stall the routine does not contain'
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            if made['template']:
                doomed = db.session.get(WorkoutTemplate, made['template'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            for key in ('in_routine', 'outsider'):
                if made[key]:
                    doomed = db.session.get(Exercise, made[key])
                    if doomed is not None:
                        db.session.delete(doomed)
                        db.session.commit()
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `python -m pytest tests/test_gym_routes_smoke.py -v -k "lead_routine"`
Expected: FAIL — `AssertionError: no briefing line on the lead card`. The
exclusion test passes trivially at this point, because nothing renders at all;
it earns its keep once the line exists.

- [ ] **Step 4: Render the line**

In `templates/gym/heute.html`, between the lead card's `<p class="lead__list">…</p>`
and the `<form>` that starts the workout, add:

```jinja
      {#- The stalls section further down covers every exercise you own,
          including ones this routine does not contain. This is the one to watch
          in the routine you are about to tap, and it is silent when there is
          none -- which is what makes it worth reading when it appears.
          stall_report returns worst-first, so the first survivor is the one. -#}
      {% set routine_ids = lead.template.exercises|map(attribute='exercise_id')|list %}
      {% set watch = stalls|selectattr('exercise_id', 'in', routine_ids)|list %}
      {% if watch %}
      <p class="lead__watch">
        {{ watch[0].name }} steht seit {{ watch[0].sessions_since_pr }}
        {{ 'Session' if watch[0].sessions_since_pr == 1 else 'Sessions' }}
        bei {{ ('%.1f'|format(watch[0].stuck_at)).replace('.', ',') }} kg.{%
        if watch|length > 1 %} · {{ watch|length - 1 }} weitere{% endif %}
      </p>
      {% endif %}
```

- [ ] **Step 5: Style it**

In `static/gym/gym.css`, next to the other `.lead__` rules:

```css
/* --stall is the teal this app already uses for ATTENTION and that the "Steht
   still" section below uses for exactly this concept, so the two read as one
   vocabulary rather than two competing warnings. */
.lead__watch {
  margin: var(--sp-2) 0 0;
  color: var(--stall-ink); font-size: var(--t-meta); line-height: 1.45;
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_routes_smoke.py -v -k lead_routine`
Expected: PASS

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Verify it is silent when nothing stalls**

The suite's other Heute tests already render the page with routines that are not
stalling. Confirm none of them now contain the class:

Run: `python -m pytest tests/test_gym_routes_smoke.py -v -k "dashboard or heute"`
Expected: PASS. A failure here means the line renders unconditionally, which is
the one behaviour the design rules out.

- [ ] **Step 8: Commit**

```bash
git add templates/gym/heute.html static/gym/gym.css tests/test_gym_routes_smoke.py
git commit -m "feat(gym): name the stalling lift in the routine you are about to start"
```

---

## Deployment

Not a task. Merge to `main` and run the deploy script — it covers `flask db upgrade`, the gunicorn restart and the notifier restart.

One migration, `d1f6b83c25e9`, adding a nullable column with no backfill. It cannot fail on existing data and needs none of the ordering care the per-user-exercises rollout did.

Expect both rest readouts to be **absent** immediately after deploying. That is correct: every set logged before this has no timestamp. They appear once you have trained.

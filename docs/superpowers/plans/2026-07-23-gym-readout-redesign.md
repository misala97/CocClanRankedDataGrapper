# Gym Tracker "Readout" Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the gym tracker's navigation shell, dashboard, exercise detail, session detail and session summary around a single visual identity and a real information architecture, extracting the analytics maths into a pure, tested module.

**Architecture:** Analytics move out of `routes.py` into a pure `stats.py` that knows nothing about Flask or SQLAlchemy — it consumes one normalised input shape (`PerformedExercise`) that `routes.py` builds in a single query. Three real page routes replace two fake anchor links, a running workout becomes a persistent resume strip rather than a nav tab, and the two half-complete finished-workout pages merge into one. The visual system is produced by the `impeccable` skill against the design brief and consumed by every template through CSS custom properties.

**Tech Stack:** Python 3 / Flask / Flask-SQLAlchemy / MySQL, Jinja2 templates, vanilla JS, Chart.js 4 (CDN), pytest 9 for the pure module.

**Spec:** `docs/superpowers/specs/2026-07-23-gym-readout-redesign-design.md` — read it before starting. This plan implements it; where they disagree, the spec wins.

## Global Constraints

- **Working directory for all commands is `personal_apps/`** unless a command says otherwise. Its modules import as top-level (`extensions`, `models`, `auth`), so nothing resolves from the repo root.
- **Branch:** `dev_personal`. Do not merge to `main` — deployment is a separate, manual step the owner performs.
- **UI language is German.** All user-facing copy in German. Code, identifiers, comments and commit messages in English.
- **Dark theme only.** No light theme, no `prefers-color-scheme` alternate.
- **`stats.py` must never import Flask, SQLAlchemy, `extensions`, or `models`.** If a function needs a query, it belongs in `routes.py`.
- **Frozen contract:** every POST route keeps its exact URL and exact form field names. Only the five redirect targets listed in spec §5.2 may change.
- **All times are naive UTC.** `WorkoutSession.started_at` is `dt.datetime.utcnow()`. Every window and "days ago" calculation compares against `dt.datetime.utcnow()`. Client-side elapsed timers must append `'Z'` when parsing the ISO string.
- **No migrations.** The data model does not change. No new columns, no new tables.
- **Muscle group vocabulary** is `models.MUSCLE_GROUPS`, exactly: `Bizeps, Trizeps, Brust, Rücken, Schultern, Beine, Bauch, Gesäß, Waden, Unterarme, Cardio, Sonstiges`. Anything else buckets into `Ohne Muskelgruppe`.
- **Unilateral rule:** logged weight and reps are per side. Volume doubles; displayed weight and reps never do.
- **Accessibility:** every interactive control is a real `<button>` or `<a>`; visible keyboard focus everywhere; 44×44 CSS px minimum touch targets for anything tapped mid-workout; state is never carried by colour alone; `prefers-reduced-motion` disables all motion.
- **Commit after every task.** Never `--no-verify`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `features/gym/stats.py` | **Create.** Pure analysis. No I/O, no framework. |
| `tests/test_gym_stats.py` | **Create.** pytest for the above; needs no app or DB. |
| `requirements-dev.txt` | **Create.** pytest, kept out of the production requirements. |
| `features/gym/routes.py` | **Modify.** Thin: queries, mutations, redirects. Loses the maths. |
| `PRODUCT.md` | **Create.** Product framing + design brief, for the `impeccable` skill. |
| `static/gym/gym.css` | **Replace.** Token system + components, produced by `impeccable`. |
| `static/gym/gym.js` | **Modify.** Chart series by position; resume-strip clock. |
| `templates/gym/_base.html` | **Create.** One `<head>` for every gym page. |
| `templates/gym/_nav.html` | **Replace.** Tab bar, desktop top bar, resume strip. |
| `templates/gym/_progress_modal.html` | **Create.** Extracted, shared. |
| `templates/gym/heute.html` | **Create.** Replaces `dashboard.html`. |
| `templates/gym/uebungen.html` | **Create.** Exercise catalogue. |
| `templates/gym/verlauf.html` | **Create.** History + export. |
| `templates/gym/session_detail.html` | **Replace.** Live logging only. |
| `templates/gym/session_finished.html` | **Create.** Replaces `session_summary.html`. |
| `templates/gym/exercise_detail.html` | **Replace.** |
| `templates/gym/dashboard.html` | **Delete** (Task 13). |
| `templates/gym/session_summary.html` | **Delete** (Task 13). |

**Note on template tasks.** Tasks 6–12 specify the data contract, the required elements, and the acceptance checks — not literal markup. This is deliberate: spec §4.0 leaves visual execution to `impeccable`, and freezing 700 lines of Jinja here would override decisions the spec explicitly delegates. Every template task lists exactly what must be present and how to verify it.

---

## Task 1: `stats.py` primitives and the input shape

**Files:**
- Create: `personal_apps/features/gym/stats.py`
- Create: `personal_apps/tests/test_gym_stats.py`
- Create: `requirements-dev.txt` (repo root)

**Interfaces:**
- Consumes: nothing.
- Produces: `PerformedExercise`, `epley_1rm(weight, reps) -> float`, `set_volume(weight, reps, is_unilateral) -> float`, `best_weight(row) -> float`, `best_e1rm(row) -> float`, `row_volume(row) -> float`, and the constants `STAGNATION_THRESHOLD = 4`, `ROLLING_WINDOW_DAYS = 28`, `TONNAGE_WEEKS = 8`, `UNDER_TRAINED_RATIO = 0.25`, `NO_GROUP_LABEL = 'Ohne Muskelgruppe'`.

- [ ] **Step 1: Create the dev requirements file**

Create `requirements-dev.txt` at the repo root (not in `personal_apps/`):

```
-r requirements.txt
pytest
```

- [ ] **Step 2: Write the failing test**

Create `personal_apps/tests/test_gym_stats.py`:

```python
"""Tests for features.gym.stats -- pure functions, so no app context, no
database, and no fixtures beyond plain data."""
import datetime as dt

from features.gym import stats


def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1):
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
    )


def test_epley_1rm_at_one_rep_is_the_weight_itself():
    assert stats.epley_1rm(100.0, 1) == 100.0 * (1 + 1 / 30.0)


def test_epley_1rm_at_zero_reps_is_the_weight():
    assert stats.epley_1rm(100.0, 0) == 100.0


def test_epley_1rm_rewards_more_reps_at_the_same_weight():
    assert stats.epley_1rm(80.0, 10) > stats.epley_1rm(80.0, 8)


def test_set_volume_is_weight_times_reps():
    assert stats.set_volume(80.0, 8, False) == 640.0


def test_set_volume_doubles_for_unilateral_because_both_sides_did_it():
    assert stats.set_volume(20.0, 10, True) == 400.0


def test_row_volume_sums_every_set():
    row = perf([(80.0, 8), (80.0, 8), (82.5, 6)])
    assert stats.row_volume(row) == 80.0 * 8 + 80.0 * 8 + 82.5 * 6


def test_row_volume_respects_unilateral():
    row = perf([(20.0, 10), (20.0, 10)], is_unilateral=True)
    assert stats.row_volume(row) == 800.0


def test_best_weight_and_best_e1rm_pick_different_sets_when_they_should():
    # The heaviest set is not always the best estimated 1RM: 5 reps at 100
    # estimates lower than 12 reps at 90.
    row = perf([(100.0, 5), (90.0, 12)])
    assert stats.best_weight(row) == 100.0
    assert stats.best_e1rm(row) == stats.epley_1rm(90.0, 12)
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'features.gym.stats'`.

- [ ] **Step 4: Write the implementation**

Create `personal_apps/features/gym/stats.py`:

```python
"""Pure analysis for the gym tracker.

No Flask, no SQLAlchemy, no queries, no I/O. Every function takes
already-loaded data and returns plain Python, which is what makes the maths
checkable without an app context or a database (see tests/test_gym_stats.py).
If something here needs a query, it belongs in routes.py instead.

The single input shape is PerformedExercise: one exercise as it was actually
performed in one session, carrying only *completed* sets. routes.py builds
these from the ORM in one pass and everything here consumes them.
"""
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

# Sessions in a row without a new estimated-1RM PR before an exercise counts
# as stagnating. 4 is roughly a month of training a lift once or twice a week
# -- long enough that it is a real plateau, short enough to still act on.
STAGNATION_THRESHOLD = 4

# Rolling window for "how am I doing lately" figures: balance, consistency.
ROLLING_WINDOW_DAYS = 28

# How many ISO weeks of tonnage to plot, including the current partial one.
TONNAGE_WEEKS = 8

# A muscle group with fewer than this share of the best-served group's working
# sets counts as under-trained. Relative rather than absolute so the flag stays
# meaningful as overall training volume changes.
UNDER_TRAINED_RATIO = 0.25

NO_GROUP_LABEL = 'Ohne Muskelgruppe'


@dataclass(frozen=True)
class PerformedExercise:
    """One exercise, as actually performed in one session.

    `sets` holds only *completed* sets as (weight, reps) pairs in the order
    they were logged -- a set prefilled from a template but never confirmed
    did not happen and must never reach this shape. Rows are therefore
    guaranteed to have at least one set, and every function here relies on
    that rather than defending against empty rows.

    weight and reps are as logged. For a unilateral exercise that means *per
    side*; volume doubles them, display never does.
    """
    exercise_id: int
    name: str
    muscle_group: Optional[str]
    is_unilateral: bool
    position: int
    session_id: int
    started_at: dt.datetime
    sets: Tuple


def epley_1rm(weight, reps):
    """Estimated one-rep max. No real single-rep test happens mid-workout, so
    this is the standard estimate every mainstream lifting tracker uses for
    the same reason. It is the yardstick for progress throughout this module,
    rather than raw weight, so that more reps at the same weight still counts
    as getting stronger."""
    return weight * (1 + reps / 30.0)


def set_volume(weight, reps, is_unilateral):
    """Volume for one logged set. A unilateral exercise logs the per-side
    weight and reps, so both sides did this and the real volume is double."""
    return weight * reps * (2 if is_unilateral else 1)


def best_weight(row):
    return max(weight for weight, _ in row.sets)


def best_e1rm(row):
    return max(epley_1rm(weight, reps) for weight, reps in row.sets)


def row_volume(row):
    return sum(set_volume(weight, reps, row.is_unilateral) for weight, reps in row.sets)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): add pure stats module with volume and 1RM primitives"
```

---

## Task 2: Per-exercise analysis — stagnation, state, stalls

**Files:**
- Modify: `personal_apps/features/gym/stats.py`
- Modify: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces: `sessions_since_pr(rows, position=None) -> Optional[int]`, `exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD) -> Optional[str]` returning one of `'neu' | 'rekord' | 'stagniert' | 'steigend' | None`, `stall_report(rows_by_exercise, threshold=STAGNATION_THRESHOLD) -> list[dict]` where each dict has keys `exercise_id, name, position, stuck_at, since, sessions_since_pr`, and `dominant_position(rows) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_gym_stats.py`:

```python
def day(n):
    return dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=n)


def test_sessions_since_pr_is_none_without_enough_history():
    assert stats.sessions_since_pr([]) is None
    assert stats.sessions_since_pr([perf([(80.0, 8)], started_at=day(0))]) is None


def test_sessions_since_pr_counts_sessions_after_the_best_one():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),   # the PR
        perf([(82.5, 8)], started_at=day(14)),
        perf([(82.5, 8)], started_at=day(21)),
    ]
    assert stats.sessions_since_pr(rows) == 2


def test_sessions_since_pr_is_zero_when_the_latest_session_is_the_best():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),
    ]
    assert stats.sessions_since_pr(rows) == 0


def test_more_reps_at_the_same_weight_counts_as_a_pr():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(80.0, 10)], started_at=day(7)),
    ]
    assert stats.sessions_since_pr(rows) == 0


def test_sessions_since_pr_scopes_to_position_when_that_slot_has_history():
    rows = [
        perf([(85.0, 8)], position=1, started_at=day(0)),
        perf([(70.0, 8)], position=3, started_at=day(7)),
        perf([(72.5, 8)], position=3, started_at=day(14)),
    ]
    # Slot 3 has 2 sessions and is climbing, so it has a fresh PR of its own --
    # the heavier slot-1 session must not mask that.
    assert stats.sessions_since_pr(rows, position=3) == 0


def test_sessions_since_pr_falls_back_to_all_positions_when_the_slot_is_thin():
    rows = [
        perf([(85.0, 8)], position=1, started_at=day(0)),
        perf([(80.0, 8)], position=1, started_at=day(7)),
        perf([(70.0, 8)], position=3, started_at=day(14)),
    ]
    # Slot 3 has only one session, too little to judge from, so the answer
    # comes from every position instead of being None.
    assert stats.sessions_since_pr(rows, position=3) == 2


def test_exercise_state_neu_when_never_performed():
    assert stats.exercise_state([]) == 'neu'


def test_exercise_state_rekord_when_the_latest_session_beat_everything():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),
    ]
    assert stats.exercise_state(rows) == 'rekord'


def test_exercise_state_stagniert_at_the_threshold():
    rows = [perf([(85.0, 8)], started_at=day(0))]
    rows += [perf([(80.0, 8)], started_at=day(7 * n)) for n in range(1, 5)]
    assert stats.sessions_since_pr(rows) == 4
    assert stats.exercise_state(rows) == 'stagniert'


def test_exercise_state_steigend_when_improving_but_not_a_record():
    rows = [
        perf([(90.0, 8)], started_at=day(0)),   # all-time best
        perf([(80.0, 8)], started_at=day(7)),
        perf([(82.5, 8)], started_at=day(14)),  # better than last time only
    ]
    assert stats.exercise_state(rows) == 'steigend'


def test_exercise_state_is_none_when_flat_and_not_yet_stagnating():
    rows = [
        perf([(90.0, 8)], started_at=day(0)),
        perf([(80.0, 8)], started_at=day(7)),
        perf([(80.0, 8)], started_at=day(14)),
    ]
    assert stats.exercise_state(rows) is None


def test_dominant_position_breaks_ties_toward_the_lower_slot():
    rows = [
        perf([(80.0, 8)], position=3, started_at=day(0)),
        perf([(80.0, 8)], position=1, started_at=day(7)),
    ]
    assert stats.dominant_position(rows) == 1


def test_stall_report_lists_only_stagnating_exercises_worst_first():
    def stalled(exercise_id, name, gap):
        rows = [perf([(85.0, 8)], exercise_id=exercise_id, name=name, started_at=day(0))]
        rows += [
            perf([(80.0, 8)], exercise_id=exercise_id, name=name, started_at=day(7 * n))
            for n in range(1, gap + 1)
        ]
        return rows

    climbing = [
        perf([(80.0, 8)], exercise_id=9, name='Rudern', started_at=day(0)),
        perf([(85.0, 8)], exercise_id=9, name='Rudern', started_at=day(7)),
    ]
    report = stats.stall_report({
        1: stalled(1, 'Bankdruecken', 4),
        2: stalled(2, 'Beinpresse', 6),
        9: climbing,
    })

    assert [entry['name'] for entry in report] == ['Beinpresse', 'Bankdruecken']
    assert report[0]['sessions_since_pr'] == 6
    assert report[0]['stuck_at'] == 80.0
    assert report[0]['since'] == day(0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: FAIL with `AttributeError: module 'features.gym.stats' has no attribute 'sessions_since_pr'`.

- [ ] **Step 3: Write the implementation**

Append to `personal_apps/features/gym/stats.py`:

```python
def _chronological(rows):
    return sorted(rows, key=lambda row: (row.started_at, row.session_id))


def dominant_position(rows):
    """The slot this exercise is most often performed in -- the fair default
    lens when nobody has asked for a specific one. Ties go to the lower slot
    so the answer is stable across calls."""
    counts = {}
    for row in rows:
        counts[row.position] = counts.get(row.position, 0) + 1
    return max(sorted(counts), key=lambda position: counts[position])


def _scoped(rows, position):
    """Position-scoped history, with an all-positions fallback.

    Exercise order changes how fatigued you are, so the same slot is the fair
    comparison -- but a slot with fewer than two sessions cannot support a
    judgement, and answering "no idea" would be worse than answering from
    every position. So it falls back rather than going empty.
    """
    if position is None:
        return _chronological(rows)
    scoped = [row for row in rows if row.position == position]
    return _chronological(scoped if len(scoped) >= 2 else rows)


def sessions_since_pr(rows, position=None):
    """How many completed sessions in a row have passed without a new best
    estimated 1RM. None when there is too little history to say anything."""
    scoped = _scoped(rows, position)
    if len(scoped) < 2:
        return None
    best_ever = None
    since = 0
    for row in scoped:
        current = best_e1rm(row)
        if best_ever is None or current > best_ever:
            best_ever = current
            since = 0
        else:
            since += 1
    return since


def exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD):
    """One of 'neu', 'rekord', 'stagniert', 'steigend', or None for stable.
    Mutually exclusive; first match wins."""
    if not rows:
        return 'neu'
    scoped = _scoped(rows, position)
    if len(scoped) >= 2 and best_e1rm(scoped[-1]) > max(best_e1rm(row) for row in scoped[:-1]):
        return 'rekord'
    since = sessions_since_pr(rows, position=position)
    if since is not None and since >= threshold:
        return 'stagniert'
    if len(scoped) >= 2 and best_e1rm(scoped[-1]) > best_e1rm(scoped[-2]):
        return 'steigend'
    return None


def stall_report(rows_by_exercise, threshold=STAGNATION_THRESHOLD):
    """Every exercise currently stagnating, worst first.

    `rows_by_exercise` maps exercise_id -> list of PerformedExercise. Each
    entry reports the slot it was judged in, the weight it is stuck at, and
    when the plateau started, so the page can say something specific rather
    than just flagging a name.
    """
    report = []
    for exercise_id, rows in rows_by_exercise.items():
        if not rows:
            continue
        position = dominant_position(rows)
        if exercise_state(rows, position=position, threshold=threshold) != 'stagniert':
            continue
        scoped = _scoped(rows, position)
        peak = max(scoped, key=best_e1rm)
        report.append({
            'exercise_id': exercise_id,
            'name': rows[0].name,
            'position': position,
            'stuck_at': best_weight(scoped[-1]),
            'since': peak.started_at,
            'sessions_since_pr': sessions_since_pr(rows, position=position),
        })
    report.sort(key=lambda entry: (-entry['sessions_since_pr'], entry['name']))
    return report
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): add stagnation, exercise state and stall reporting to stats"
```

---

## Task 3: Aggregates — session report, balance, tonnage, consistency, routines

**Files:**
- Modify: `personal_apps/features/gym/stats.py`
- Modify: `personal_apps/tests/test_gym_stats.py`

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces:
  - `exercise_progress(rows, position=None) -> dict` with keys `table, series, available_positions, selected_position, pr_weight, pr_e1rm, state, sessions_since_pr`
  - `session_report(current, history, comparable_session_volumes=()) -> dict` with keys `exercises, total_volume, total_sets, avg_total_volume, total_volume_delta_pct, records, record_count, advice`
  - `muscle_group_volume(rows, catalogue_groups, now, days=ROLLING_WINDOW_DAYS) -> list[dict]` with keys `group, sets, volume, share, under_trained`
  - `weekly_tonnage(rows, now, weeks=TONNAGE_WEEKS) -> list[dict]` with keys `week_start, volume, is_current`
  - `consistency(finished_started_at, now, days=ROLLING_WINDOW_DAYS) -> dict` with keys `sessions, per_week, days_since_last, window_days`
  - `routine_memory(templates, sessions, now) -> list[dict]` with keys `template, last_done, days_ago`
  - `group_exercises_by_muscle(exercises, muscle_groups) -> list[tuple]`

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_gym_stats.py`:

```python
class FakeTemplate:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class FakeSession:
    def __init__(self, template_id, started_at):
        self.template_id = template_id
        self.started_at = started_at


class FakeExercise:
    def __init__(self, name, muscle_group):
        self.name = name
        self.muscle_group = muscle_group


NOW = dt.datetime(2026, 7, 23, 12, 0)


def test_exercise_progress_returns_newest_first_table_and_per_position_series():
    rows = [
        perf([(80.0, 8)], position=1, started_at=day(0), session_id=1),
        perf([(70.0, 8)], position=3, started_at=day(7), session_id=2),
        perf([(82.5, 6)], position=1, started_at=day(14), session_id=3),
    ]
    result = stats.exercise_progress(rows)

    assert [entry['session_id'] for entry in result['table']] == [3, 2, 1]
    assert result['available_positions'] == [1, 3]
    assert [series['position'] for series in result['series']] == [1, 3]
    assert len(result['series'][0]['points']) == 2
    assert result['pr_weight']['weight'] == 82.5
    assert result['selected_position'] is None


def test_exercise_progress_isolates_a_single_position_when_asked():
    rows = [
        perf([(80.0, 8)], position=1, started_at=day(0), session_id=1),
        perf([(70.0, 8)], position=3, started_at=day(7), session_id=2),
    ]
    result = stats.exercise_progress(rows, position=3)

    assert [entry['session_id'] for entry in result['table']] == [2]
    assert [series['position'] for series in result['series']] == [3]
    # available_positions always describes the unfiltered data, so the page
    # can still offer the other slots as options.
    assert result['available_positions'] == [1, 3]


def test_exercise_progress_on_an_exercise_with_no_history_is_empty_not_broken():
    result = stats.exercise_progress([])
    assert result['table'] == []
    assert result['series'] == []
    assert result['pr_weight'] is None
    assert result['pr_e1rm'] is None
    assert result['state'] == 'neu'


def test_session_report_totals_and_flags_a_weight_record():
    current = [perf([(85.0, 8)], started_at=day(21), session_id=9)]
    history = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(80.0, 8)], started_at=day(7), session_id=2),
    ]
    report = stats.session_report(current, history)

    assert report['total_sets'] == 1
    assert report['total_volume'] == 680.0
    assert report['record_count'] == 1
    assert report['records'][0]['kind'] == 'weight'
    assert report['records'][0]['previous'] == 80.0
    assert report['exercises'][0]['verdict'] == 'rekord'


def test_session_report_marks_a_first_ever_exercise_as_neu_not_as_a_record():
    current = [perf([(60.0, 10)], started_at=day(0), session_id=1)]
    report = stats.session_report(current, [])

    assert report['record_count'] == 0
    assert report['exercises'][0]['verdict'] == 'neu'
    assert report['exercises'][0]['has_history'] is False
    assert report['exercises'][0]['avg_volume'] is None
    assert report['exercises'][0]['volume_delta_pct'] is None


def test_session_report_advises_on_a_stagnating_exercise():
    history = [perf([(85.0, 8)], started_at=day(0), session_id=1)]
    history += [
        perf([(80.0, 8)], started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(80.0, 8)], started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['exercises'][0]['verdict'] == 'stagniert'
    assert len(report['advice']) == 1
    assert report['advice'][0]['stuck_at'] == 80.0
    assert report['advice'][0]['suggested_weight'] == 82.5


def test_session_report_suggests_a_smaller_jump_for_unilateral_work():
    history = [perf([(22.5, 8)], is_unilateral=True, started_at=day(0), session_id=1)]
    history += [
        perf([(20.0, 8)], is_unilateral=True, started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(20.0, 8)], is_unilateral=True, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['advice'][0]['suggested_weight'] == 21.25


def test_session_report_compares_against_the_template_cohort_when_given_one():
    current = [perf([(80.0, 10)], started_at=day(21), session_id=9)]
    report = stats.session_report(current, [], comparable_session_volumes=[400.0, 400.0])

    assert report['avg_total_volume'] == 400.0
    assert report['total_volume_delta_pct'] == 100


def test_session_report_omits_the_whole_workout_comparison_for_freeform_sessions():
    current = [perf([(80.0, 10)], started_at=day(21), session_id=9)]
    report = stats.session_report(current, [])

    assert report['avg_total_volume'] is None
    assert report['total_volume_delta_pct'] is None


def test_muscle_group_volume_lists_untrained_catalogue_groups_at_zero():
    rows = [
        perf([(80.0, 8)] * 5, muscle_group='Brust', started_at=NOW - dt.timedelta(days=3)),
        perf([(60.0, 8)], muscle_group='Waden', started_at=NOW - dt.timedelta(days=3)),
    ]
    result = stats.muscle_group_volume(rows, ['Brust', 'Waden', 'Bizeps'], NOW)
    by_group = {bucket['group']: bucket for bucket in result}

    assert by_group['Brust']['sets'] == 5
    assert by_group['Brust']['under_trained'] is False
    assert by_group['Waden']['sets'] == 1
    assert by_group['Waden']['under_trained'] is True   # 1 < 25% of 5
    assert by_group['Bizeps']['sets'] == 0
    assert by_group['Bizeps']['under_trained'] is True


def test_muscle_group_volume_ignores_work_outside_the_window():
    rows = [perf([(80.0, 8)], muscle_group='Brust', started_at=NOW - dt.timedelta(days=40))]
    result = stats.muscle_group_volume(rows, ['Brust'], NOW)

    assert result[0]['sets'] == 0


def test_weekly_tonnage_returns_one_bucket_per_week_oldest_first():
    rows = [perf([(100.0, 10)], started_at=NOW - dt.timedelta(days=1))]
    result = stats.weekly_tonnage(rows, NOW, weeks=4)

    assert len(result) == 4
    assert result[0]['week_start'] < result[-1]['week_start']
    assert result[-1]['is_current'] is True
    assert result[-1]['volume'] == 1000.0
    assert sum(bucket['is_current'] for bucket in result) == 1


def test_weekly_tonnage_buckets_by_iso_week_not_by_rolling_seven_days():
    monday = dt.datetime(2026, 7, 20, 9, 0)     # a Monday
    sunday_before = dt.datetime(2026, 7, 19, 9, 0)
    rows = [
        perf([(100.0, 10)], started_at=monday, session_id=1),
        perf([(100.0, 10)], started_at=sunday_before, session_id=2),
    ]
    result = stats.weekly_tonnage(rows, dt.datetime(2026, 7, 23, 12, 0), weeks=2)

    assert result[0]['volume'] == 1000.0
    assert result[1]['volume'] == 1000.0


def test_consistency_reports_rate_and_gap():
    finished = [NOW - dt.timedelta(days=n) for n in (2, 5, 9, 30)]
    result = stats.consistency(finished, NOW)

    assert result['sessions'] == 3          # the 30-day-old one is outside
    assert result['per_week'] == 0.75
    assert result['days_since_last'] == 2


def test_consistency_with_no_history_does_not_divide_by_zero():
    result = stats.consistency([], NOW)

    assert result['sessions'] == 0
    assert result['per_week'] == 0.0
    assert result['days_since_last'] is None


def test_routine_memory_sorts_longest_ago_first_and_unused_last():
    templates = [FakeTemplate(1, 'Push'), FakeTemplate(2, 'Pull'), FakeTemplate(3, 'Beine')]
    sessions = [
        FakeSession(1, NOW - dt.timedelta(days=5)),
        FakeSession(1, NOW - dt.timedelta(days=12)),
        FakeSession(2, NOW - dt.timedelta(days=2)),
    ]
    result = stats.routine_memory(templates, sessions, NOW)

    assert [entry['template'].name for entry in result] == ['Push', 'Pull', 'Beine']
    assert result[0]['days_ago'] == 5        # most recent Push, not the older one
    assert result[2]['days_ago'] is None


def test_group_exercises_by_muscle_keeps_vocabulary_order_and_collects_strays():
    exercises = [
        FakeExercise('Bizepscurls', 'Bizeps'),
        FakeExercise('Bankdruecken', 'Brust'),
        FakeExercise('Etwas Altes', 'Legacy-Kategorie'),
        FakeExercise('Ohne Gruppe', None),
    ]
    result = stats.group_exercises_by_muscle(exercises, ('Bizeps', 'Brust'))

    assert [group for group, _ in result] == ['Bizeps', 'Brust', 'Ohne Muskelgruppe']
    assert [ex.name for ex in result[2][1]] == ['Etwas Altes', 'Ohne Gruppe']
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: FAIL with `AttributeError: module 'features.gym.stats' has no attribute 'exercise_progress'`.

- [ ] **Step 3: Write the implementation**

Append to `personal_apps/features/gym/stats.py`:

```python
def _sets_display(row):
    return ', '.join('{:g} kg x {}'.format(weight, reps) for weight, reps in row.sets)


def _pr_weight(rows):
    """The heaviest single set ever logged."""
    best = None
    for row in rows:
        for weight, reps in row.sets:
            if best is None or weight > best['weight']:
                best = {'weight': weight, 'reps': reps,
                        'started_at': row.started_at, 'position': row.position}
    return best


def _pr_e1rm(rows):
    """The single set with the highest estimated 1RM -- not always the
    heaviest one, since more reps at less weight can estimate higher."""
    best = None
    for row in rows:
        for weight, reps in row.sets:
            value = epley_1rm(weight, reps)
            if best is None or value > best['e1rm']:
                best = {'e1rm': round(value, 1), 'weight': weight, 'reps': reps,
                        'started_at': row.started_at, 'position': row.position}
    return best


def exercise_progress(rows, position=None):
    """History table and chart series for one exercise.

    Position is a *series*, not a filter: every session is plotted, grouped by
    the slot it was performed in, so a slot sitting consistently higher than
    another is visible instead of having to be hunted for by hiding data.
    `position` still isolates one slot when the user explicitly asks.

    `available_positions` always describes the unfiltered data, so the page can
    keep offering the other slots even while one is isolated.
    """
    chronological = _chronological(rows)
    available_positions = sorted({row.position for row in chronological})
    shown = ([row for row in chronological if row.position == position]
             if position is not None else chronological)

    table = [
        {
            'session_id': row.session_id,
            'started_at': row.started_at,
            'position': row.position,
            'sets_display': _sets_display(row),
            'best_weight': best_weight(row),
            'volume': round(row_volume(row), 1),
            'e1rm': round(best_e1rm(row), 1),
        }
        for row in reversed(shown)
    ]

    series = []
    for slot in (available_positions if position is None else [position]):
        points = [row for row in shown if row.position == slot]
        if not points:
            continue
        series.append({
            'position': slot,
            'points': [
                {
                    'started_at': row.started_at,
                    'e1rm': round(best_e1rm(row), 1),
                    'best_weight': best_weight(row),
                    'volume': round(row_volume(row), 1),
                }
                for row in points
            ],
        })

    return {
        'table': table,
        'series': series,
        'available_positions': available_positions,
        'selected_position': position,
        'pr_weight': _pr_weight(chronological),
        'pr_e1rm': _pr_e1rm(chronological),
        'state': exercise_state(rows, position=position),
        'sessions_since_pr': sessions_since_pr(rows, position=position),
    }


def _next_weight(weight, is_unilateral):
    """The smallest honest jump up. 2.5 kg is the smallest pair of plates on
    most bars; a unilateral lift moves one side at a time, so half that."""
    return weight + (1.25 if is_unilateral else 2.5)


def _verdict(entry, since):
    if not entry['has_history']:
        return 'neu'
    if entry['is_weight_pr'] or entry['is_volume_pr'] or entry['is_e1rm_pr']:
        return 'rekord'
    if since is not None and since >= STAGNATION_THRESHOLD:
        return 'stagniert'
    if entry['volume_delta_pct'] is not None and entry['volume_delta_pct'] > 0:
        return 'steigend'
    return None


def session_report(current, history, comparable_session_volumes=()):
    """The finished-workout page.

    `current` is this session's performed exercises -- the caller must already
    have dropped any exercise that was replaced mid-workout, since its slot is
    represented by the substitute that took over and counting both would
    inflate the total. `history` is every other performed row for those same
    exercises. `comparable_session_volumes` holds the total volume of past
    sessions built from the same template, and is empty for freeform workouts:
    averaging a leg day into a push day produces a number that is arithmetically
    correct and completely meaningless.
    """
    by_exercise = {}
    for row in history:
        by_exercise.setdefault(row.exercise_id, []).append(row)

    exercises = []
    records = []
    advice = []
    total_volume = 0.0
    total_sets = 0

    for row in current:
        volume = row_volume(row)
        weight = best_weight(row)
        e1rm = best_e1rm(row)
        total_volume += volume
        total_sets += len(row.sets)

        past = by_exercise.get(row.exercise_id, [])
        past_volumes = [row_volume(p) for p in past]
        has_history = bool(past_volumes)
        avg_volume = (sum(past_volumes) / len(past_volumes)) if has_history else None

        entry = {
            'exercise_id': row.exercise_id,
            'name': row.name,
            'position': row.position,
            'sets': row.sets,
            'sets_display': _sets_display(row),
            'volume': round(volume, 1),
            'best_weight': weight,
            'e1rm': round(e1rm, 1),
            'has_history': has_history,
            'avg_volume': round(avg_volume, 1) if has_history else None,
            'volume_delta_pct': (round((volume - avg_volume) / avg_volume * 100)
                                 if avg_volume else None),
            'is_weight_pr': has_history and weight > max(best_weight(p) for p in past),
            'is_volume_pr': has_history and volume > max(past_volumes),
            'is_e1rm_pr': has_history and e1rm > max(best_e1rm(p) for p in past),
        }

        since = sessions_since_pr(past + [row], position=row.position)
        entry['sessions_since_pr'] = since
        entry['verdict'] = _verdict(entry, since)
        exercises.append(entry)

        # One record per exercise, strongest kind first -- three badges on one
        # lift is noise, and a weight PR already implies the others matter less.
        if entry['is_weight_pr']:
            previous_row = max(past, key=best_weight)
            records.append({'kind': 'weight', 'name': row.name, 'position': row.position,
                            'value': weight, 'previous': best_weight(previous_row),
                            'previous_at': previous_row.started_at})
        elif entry['is_e1rm_pr']:
            previous_row = max(past, key=best_e1rm)
            records.append({'kind': 'e1rm', 'name': row.name, 'position': row.position,
                            'value': round(e1rm, 1), 'previous': round(best_e1rm(previous_row), 1),
                            'previous_at': previous_row.started_at})
        elif entry['is_volume_pr']:
            previous_row = max(past, key=row_volume)
            records.append({'kind': 'volume', 'name': row.name, 'position': row.position,
                            'value': round(volume, 1), 'previous': round(row_volume(previous_row), 1),
                            'previous_at': previous_row.started_at})

        if entry['verdict'] == 'stagniert':
            advice.append({
                'exercise_id': row.exercise_id,
                'name': row.name,
                'stuck_at': weight,
                'sessions': since,
                'suggested_weight': _next_weight(weight, row.is_unilateral),
            })

    records.sort(key=lambda record: -record['value'])
    advice.sort(key=lambda item: -item['sessions'])

    avg_total = ((sum(comparable_session_volumes) / len(comparable_session_volumes))
                 if comparable_session_volumes else None)

    return {
        'exercises': exercises,
        'total_volume': round(total_volume, 1),
        'total_sets': total_sets,
        'avg_total_volume': round(avg_total, 1) if avg_total else None,
        'total_volume_delta_pct': (round((total_volume - avg_total) / avg_total * 100)
                                   if avg_total else None),
        'records': records,
        'record_count': len(records),
        'advice': advice,
    }


def muscle_group_volume(rows, catalogue_groups, now, days=ROLLING_WINDOW_DAYS):
    """Working sets and volume per muscle group over a rolling window.

    `catalogue_groups` is every group with at least one exercise in the
    catalogue, so a group you have quietly stopped training still appears --
    at zero, flagged -- instead of vanishing from the page precisely when it
    most needs pointing out.
    """
    cutoff = now - dt.timedelta(days=days)
    totals = {group: {'group': group, 'sets': 0, 'volume': 0.0} for group in catalogue_groups}
    for row in rows:
        if row.started_at < cutoff:
            continue
        group = row.muscle_group or NO_GROUP_LABEL
        bucket = totals.setdefault(group, {'group': group, 'sets': 0, 'volume': 0.0})
        bucket['sets'] += len(row.sets)
        bucket['volume'] += row_volume(row)

    buckets = sorted(totals.values(), key=lambda bucket: (-bucket['sets'], bucket['group']))
    peak = buckets[0]['sets'] if buckets else 0
    for bucket in buckets:
        bucket['volume'] = round(bucket['volume'], 1)
        bucket['share'] = (bucket['sets'] / peak) if peak else 0.0
        bucket['under_trained'] = bucket['sets'] == 0 or bucket['sets'] < peak * UNDER_TRAINED_RATIO
    return buckets


def _week_start(moment):
    """Monday 00:00 of the ISO week `moment` falls in."""
    monday = moment.date() - dt.timedelta(days=moment.weekday())
    return dt.datetime(monday.year, monday.month, monday.day)


def weekly_tonnage(rows, now, weeks=TONNAGE_WEEKS):
    """Total volume per ISO week, oldest first, ending with the current one.

    The last bucket is a partial week by definition. It is flagged
    `is_current` so the page can label it as still running -- unflagged, a
    Tuesday would always look like a collapse in training.
    """
    current_start = _week_start(now)
    starts = [current_start - dt.timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]
    buckets = {start: 0.0 for start in starts}
    for row in rows:
        start = _week_start(row.started_at)
        if start in buckets:
            buckets[start] += row_volume(row)
    return [
        {'week_start': start, 'volume': round(buckets[start], 1),
         'is_current': start == current_start}
        for start in starts
    ]


def consistency(finished_started_at, now, days=ROLLING_WINDOW_DAYS):
    """Training rate over the window, plus how long it has been since the last
    session. `finished_started_at` is a list of datetimes."""
    cutoff = now - dt.timedelta(days=days)
    recent = [moment for moment in finished_started_at if moment >= cutoff]
    latest = max(finished_started_at) if finished_started_at else None
    return {
        'sessions': len(recent),
        'per_week': len(recent) / (days / 7.0),
        'days_since_last': (now - latest).days if latest else None,
        'window_days': days,
    }


def routine_memory(templates, sessions, now):
    """Each routine with how long since it was last performed.

    Longest-ago first, because that is usually the one you are about to do.
    Routines never performed sort last: they are unproven rather than overdue,
    and putting them on top would bury the answer under noise.
    """
    latest = {}
    for session in sessions:
        if session.template_id is None:
            continue
        seen = latest.get(session.template_id)
        if seen is None or session.started_at > seen:
            latest[session.template_id] = session.started_at

    memory = []
    for template in templates:
        last = latest.get(template.id)
        memory.append({
            'template': template,
            'last_done': last,
            'days_ago': (now - last).days if last else None,
        })
    memory.sort(key=lambda entry: (entry['days_ago'] is None,
                                   -(entry['days_ago'] or 0),
                                   entry['template'].name))
    return memory


def group_exercises_by_muscle(exercises, muscle_groups):
    """Bucket exercises by muscle group in the vocabulary's own order.

    Anything that does not match a current group -- no group set, or a legacy
    free-text value from before the vocabulary existed -- lands in a trailing
    catch-all bucket rather than being silently dropped. `exercises` is
    expected pre-sorted by name so each bucket stays alphabetical.
    """
    grouped = {group: [] for group in muscle_groups}
    other = []
    for exercise in exercises:
        if exercise.muscle_group in grouped:
            grouped[exercise.muscle_group].append(exercise)
        else:
            other.append(exercise)
    result = [(group, grouped[group]) for group in muscle_groups if grouped[group]]
    if other:
        result.append((NO_GROUP_LABEL, other))
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_stats.py -v
```

Expected: 38 passed.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/tests/test_gym_stats.py
git commit -m "feat(gym): add session report, balance, tonnage and routine aggregates"
```

---

## Task 4: Rewire `routes.py` onto `stats.py` — behaviour unchanged

This task changes no user-visible behaviour. Its whole job is to make the existing four pages render identically while sourcing their numbers from `stats.py`, so that any later breakage is provably caused by a later task.

**Files:**
- Modify: `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: all of `stats.py`.
- Produces: `load_performed(exercise_ids=None, since=None) -> list[stats.PerformedExercise]` and `performed_from_session(session_) -> list[stats.PerformedExercise]`, both used by Tasks 8–12.

- [ ] **Step 1: Add the loader**

Add to `personal_apps/features/gym/routes.py`, after the existing helper functions:

```python
from features.gym import stats


def load_performed(exercise_ids=None, since=None):
    """Every exercise-as-performed with at least one completed set, as the
    single flat shape stats.py consumes.

    This exists to be called ONCE per request. The pages that need per-exercise
    verdicts need them for the whole catalogue at once, and asking per exercise
    would mean one query per row -- roughly forty on the catalogue page today,
    and worse every time an exercise is added.
    """
    query = (
        SessionExercise.query
        .options(
            joinedload(SessionExercise.exercise),
            joinedload(SessionExercise.session),
            joinedload(SessionExercise.sets),
        )
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(WorkoutSession.finished_at.isnot(None))
    )
    if exercise_ids is not None:
        query = query.filter(SessionExercise.exercise_id.in_(exercise_ids))
    if since is not None:
        query = query.filter(WorkoutSession.started_at >= since)

    performed = []
    for session_exercise in query.order_by(WorkoutSession.started_at).all():
        completed = tuple(
            (s.weight, s.reps) for s in session_exercise.sets if s.completed
        )
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed))
    return performed


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
    )


def performed_from_session(session_):
    """This session's exercises as performed.

    A replaced-away original is skipped: its slot is represented by the
    substitute that took over, and counting both would inflate the session's
    totals with an exercise the historical comparison was never scoped to.
    """
    performed = []
    for session_exercise in session_.exercises:
        if session_exercise.replaced_by:
            continue
        completed = tuple(
            (s.weight, s.reps) for s in session_exercise.sets if s.completed
        )
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed))
    return performed
```

- [ ] **Step 2: Delete the migrated helpers**

Delete these functions from `routes.py` entirely — they now live in `stats.py`:

- `_epley_1rm`
- `_set_volume`
- `_sessions_since_last_pr`
- `_session_summary_data`
- `_exercise_progress_data`
- `_group_exercises_by_muscle`

Also delete the module-level `STAGNATION_THRESHOLD = 4` — it lives in `stats.py` now.

- [ ] **Step 3: Rewire the four call sites**

In `gym_dashboard`, replace the `_group_exercises_by_muscle(exercises)` call with `stats.group_exercises_by_muscle(exercises, MUSCLE_GROUPS)`.

In `session_detail`, replace the stagnation block with:

```python
    stagnation_counts = {}
    if not session_.finished_at:
        history = load_performed(
            exercise_ids=[se.exercise_id for se in visible_exercises]
        )
        by_exercise = {}
        for row in history:
            if row.session_id != session_.id:
                by_exercise.setdefault(row.exercise_id, []).append(row)
        for se in visible_exercises:
            count = stats.sessions_since_pr(
                by_exercise.get(se.exercise_id, []), position=se.position
            )
            if count is not None and count >= stats.STAGNATION_THRESHOLD:
                stagnation_counts[se.id] = count
```

In `gym_session_summary`, replace `_session_summary_data(session_)` with:

```python
    current = performed_from_session(session_)
    history = [
        row for row in load_performed(exercise_ids=[row.exercise_id for row in current])
        if row.session_id != session_.id
    ]
    comparable = []
    if session_.template_id:
        cohort = (
            WorkoutSession.query
            .filter(
                WorkoutSession.id != session_.id,
                WorkoutSession.finished_at.isnot(None),
                WorkoutSession.template_id == session_.template_id,
            )
            .all()
        )
        cohort_ids = {other.id for other in cohort}
        volumes = {}
        for row in load_performed():
            if row.session_id in cohort_ids:
                volumes[row.session_id] = volumes.get(row.session_id, 0.0) + stats.row_volume(row)
        comparable = [volume for volume in volumes.values() if volume > 0]
    data = stats.session_report(current, history, comparable_session_volumes=comparable)
```

In `exercise_detail` and `gym_exercise_progress_json`, replace `_exercise_progress_data(exercise, position=position)` with:

```python
    rows = load_performed(exercise_ids=[exercise.id])
    data = stats.exercise_progress(rows, position=position)
```

For `gym_exercise_progress_json`, keep the existing "fall back to all positions when this slot has no rows" behaviour by checking `data['table']` instead of `data['rows']`.

**The existing templates read different key names than `stats.py` returns.** Do not rewrite the templates in this task — instead, in `exercise_detail` and `gym_session_summary`, adapt the keys where the old template expects them, so the pages keep rendering. Tasks 10 and 12 replace those templates and delete the adapters. Write the adapter inline and mark it:

```python
    # Temporary shim: the old templates predate stats.py's key names. Deleted
    # when exercise_detail.html and session_finished.html are rebuilt.
```

- [ ] **Step 4: Verify the four existing pages still render**

Start the app and check each page returns 200 with content that matches what it showed before. Create `personal_apps/tests/test_gym_routes_smoke.py`:

```python
"""Smoke checks that every gym GET route renders. Needs the real database, so
these are run manually rather than in the pure-stats suite."""
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['logged_in'] = True
        yield test_client


def test_dashboard_renders(client):
    assert client.get('/gym').status_code == 200


def test_exercise_detail_renders_for_every_exercise(client):
    with flask_app.app_context():
        from models import Exercise
        ids = [row.id for row in Exercise.query.all()]
    for exercise_id in ids:
        response = client.get('/gym/exercises/{}'.format(exercise_id))
        assert response.status_code == 200, exercise_id


def test_session_pages_render_for_every_finished_session(client):
    with flask_app.app_context():
        from models import WorkoutSession
        ids = [row.id for row in WorkoutSession.query.filter(
            WorkoutSession.finished_at.isnot(None)).all()]
    for session_id in ids:
        assert client.get('/gym/session/{}'.format(session_id)).status_code == 200
        assert client.get('/gym/session/{}/summary'.format(session_id)).status_code == 200
```

Run:

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -v
```

Expected: all pass. If MySQL is not running, start it first — this suite needs the real data, which is the point.

- [ ] **Step 5: Run the pure suite too, to confirm nothing regressed**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: 38 passed in the stats suite plus the smoke tests.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "refactor(gym): source page data from stats.py with a single bulk loader"
```

---

## Task 5: Product context and the visual system

**Files:**
- Create: `personal_apps/PRODUCT.md`
- Replace: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: nothing.
- Produces: the CSS custom properties every later template reads — `--ground, --chassis, --raised, --edge, --edge-hi, --ink, --dim, --unlit, --live, --live-deep, --record, --stall` — plus component classes for panels, set rows, chips, the rest bar, buttons, the tab bar, and the resume strip.

- [ ] **Step 1: Write `personal_apps/PRODUCT.md`**

It must contain: what the gym tracker is and who uses it (§2 of the spec), a `## Platform` heading whose value is exactly `web`, and the complete design brief — spec §4.0 through §4.6, copied in full including the locked-vs-open table.

Do **not** create a `PRODUCT.md` at the repo root or in the repo's `docs/`. Either would take precedence in `impeccable`'s resolution order and would also apply to `coc_stats`, which has an unrelated identity.

- [ ] **Step 2: Run impeccable to build the visual system**

Invoke the `impeccable` skill from the repo root with `IMPECCABLE_CONTEXT_DIR=personal_apps` set, targeting `personal_apps/static/gym/gym.css`. Because no `PRODUCT.md` exists at the repo root or in `docs/`, that environment variable is what makes it resolve `personal_apps/PRODUCT.md`.

Give it spec §4 as the brief and state plainly what is locked and what is open — §4.0 has the table.

Its detectors false-positive on em-dashes and numbered markers in this codebase's CSS comments. Do not chase those findings.

- [ ] **Step 3: Verify the token contract exists**

```bash
cd personal_apps && for token in ground chassis raised edge edge-hi ink dim unlit live live-deep record stall; do grep -q -- "--$token:" static/gym/gym.css && echo "OK   --$token" || echo "MISSING --$token"; done
```

Expected: twelve `OK` lines. Any `MISSING` means a later template will silently fall back to an unstyled value — fix before continuing.

- [ ] **Step 4: Verify contrast on the pairings that actually occur**

Check with a contrast tool that each of these meets WCAG AA at its rendered size: `--ink` on `--chassis`, `--dim` on `--chassis`, `--live` on `--chassis`, `--record` on `--chassis`, `--stall` on `--chassis`, `--unlit` on `--ground`. Record the measured ratios in the commit message.

Then confirm `--live`, `--record` and `--stall` stay distinguishable under deuteranopia and protanopia simulation. If any pair collapses, the hue is wrong regardless of how it looks — say so and re-derive rather than shipping it.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/PRODUCT.md personal_apps/static/gym/gym.css
git commit -m "feat(gym): build the Readout visual system"
```

---

## Task 6: The shell — base template, nav, resume strip

**Files:**
- Create: `personal_apps/templates/gym/_base.html`
- Replace: `personal_apps/templates/gym/_nav.html`
- Modify: `personal_apps/static/gym/gym.js`

**Interfaces:**
- Consumes: `gym.css` tokens and components from Task 5; `gym_active_session`, already injected into every gym template by the existing `inject_gym_nav_context()` context processor.
- Produces: `_base.html` with blocks `{% block title %}`, `{% block content %}`, `{% block scripts %}`; and `window.GymClock.start(element)` in `gym.js`, which reads `data-started` (an ISO string, UTC) and ticks `HH:MM:SS` into the element every second.

**`_base.html` must contain**, so no page repeats it: `<!DOCTYPE html>`, `lang="de"`, charset and viewport meta, `<link rel="manifest" href="/static/manifest.json">`, the mobile-web-app and apple-touch-icon meta tags currently in `dashboard.html` lines 7–11, `<meta name="theme-color">` set to the new `--ground` value, the webfont link chosen in Task 5, `gym.css`, the `_nav.html` include, and the three blocks.

**`_nav.html` must contain:**

1. A bottom tab bar, mobile only, with exactly three tabs: **Heute** → `gym.gym_heute`, **Übungen** → `gym.gym_uebungen`, **Verlauf** → `gym.gym_verlauf`. The active tab is derived from `request.endpoint` and is lit `--live`. Each tab is an `<a>`, minimum 44 px tall.
2. A desktop top bar, `≥900px` only, with the wordmark, the same three links, and a logout link to `/logout`.
3. A logout link in a quiet footer position on mobile, since it is not a tab.
4. The resume strip — rendered only when `gym_active_session` exists **and** `request.endpoint != 'gym.session_detail'`. It must be an `<a>` to `gym.session_detail` for that session, carry the workout name, a live-ticking elapsed time, and the current exercise name, and sit pinned above the tab bar on mobile and below the top bar on desktop.

Endpoint names used above do not exist until Tasks 9–11. For this task, point all three tabs at `gym.gym_dashboard` and leave a comment saying they are rewired in Task 11; the shell is verified against the pages that exist today.

- [ ] **Step 1: Write `_base.html` and `_nav.html`**

- [ ] **Step 2: Add the shared clock to `gym.js`**

```javascript
window.GymClock = {
    // Ticks HH:MM:SS into `element` from its data-started ISO timestamp.
    // The timestamps the server writes are naive UTC, so 'Z' has to be
    // appended or the browser reads them as local time and the elapsed
    // figure is wrong by the timezone offset.
    start(element) {
        if (!element) return;
        const startedAt = new Date(element.dataset.started + 'Z');
        const pad = (n) => String(n).padStart(2, '0');
        const tick = () => {
            const total = Math.floor(Math.max(0, Date.now() - startedAt.getTime()) / 1000);
            element.textContent = `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
        };
        tick();
        return setInterval(tick, 1000);
    },
};
```

- [ ] **Step 3: Convert `dashboard.html` to extend `_base.html`**

Strip its `<head>` and `<body>` wrapper, wrap its content in `{% block content %}`, move its inline script into `{% block scripts %}`, and switch the elapsed-time script to `GymClock.start(document.getElementById('active-elapsed'))`. This proves the shell works before four new pages depend on it.

- [ ] **Step 4: Verify in the browser**

Run the app, open `/gym` at 390×844 and at 1440 px wide. Confirm: the tab bar appears only on mobile and the top bar only on desktop; nothing is clipped behind either; starting a workout makes the resume strip appear on `/gym` and disappear on the session page itself; the elapsed time ticks on both.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/_base.html personal_apps/templates/gym/_nav.html personal_apps/templates/gym/dashboard.html personal_apps/static/gym/gym.js
git commit -m "feat(gym): add base template, three-tab nav and active-workout resume strip"
```

---

## Task 7: Live workout view

**Files:**
- Replace: `personal_apps/templates/gym/session_detail.html`
- Create: `personal_apps/templates/gym/_progress_modal.html`

**Interfaces:**
- Consumes: `_base.html`, `gym.css`, and the existing `session_detail` view context — `session`, `visible_exercises`, `suggestions`, `stagnation_counts`, `exercises`, `muscle_groups`, `vapid_public_key`.
- Produces: `_progress_modal.html`, also included by Task 12.

**Every one of these must survive**, with the same URL and the same form field names. Check each off individually:

- [ ] Set completion — POST `/gym/set/<id>/toggle_complete`, fields `weight`, `reps`
- [ ] Set edit — POST `/gym/set/<id>/update`, fields `weight`, `reps`
- [ ] Set delete — POST `/gym/set/<id>/delete`
- [ ] Add set — POST `/gym/session-exercise/<id>/sets/add`, fields `weight`, `reps`
- [ ] Rest seconds — POST `/gym/session-exercise/<id>/rest`, field `rest_seconds`, auto-saving
- [ ] Skip toggle — POST `/gym/session-exercise/<id>/skip`
- [ ] Replace exercise — POST `/gym/session-exercise/<id>/replace`, same-muscle-group options only
- [ ] Remove exercise — POST `/gym/session-exercise/<id>/delete`
- [ ] Add exercise — POST `/gym/session/<id>/exercises/add`, including creating a new exercise inline
- [ ] Reorder — POST `/gym/session/<id>/exercises/reorder`, behind the existing lock toggle
- [ ] Finish — POST `/gym/session/<id>/finish`
- [ ] Save as template — POST `/gym/session/<id>/save_as_template`, field `template_name`
- [ ] Push notification enable row, using `vapid_public_key`
- [ ] The progress modal, fed by `/gym/exercises/<id>/progress.json`
- [ ] The rest bar, driven by `session.rest_ends_at` and `session.resting_set_id`

**What changes:** exactly one exercise panel is live at a time. An exercise whose sets are all completed collapses to a settled summary row. An exercise not yet reached renders unlit. The live one is the first with incomplete sets. Set rows move unlit → live → done per spec §4.2. Skipped exercises keep their existing badge.

- [ ] **Step 1: Extract the progress modal into `_progress_modal.html`**

Move the modal markup from `session_detail.html` lines 21–30 and its JavaScript from the inline `<script>`, unchanged in behaviour. It fetches `/gym/exercises/<id>/progress.json` and renders PR cards and a chart.

- [ ] **Step 2: Write the new `session_detail.html`**

For a finished session it must still render — Task 8 splits that off. Until then, keep the existing read-only branch working.

- [ ] **Step 3: Verify every interaction against a real workout**

Start a workout from a template, then exercise the full checklist above by hand at 390×844: complete a set and confirm rest starts, edit a completed set, delete a set, add a set, change rest seconds, skip and unskip, replace an exercise, add an exercise, reorder with the lock off, open the progress modal, save as template, finish.

- [ ] **Step 4: Confirm no endpoint drifted**

```bash
cd personal_apps && grep -o "url_for('gym\.[a-z_]*'" templates/gym/session_detail.html | sort -u
```

Compare against the list above. Anything missing is a lost feature, not a simplification.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/templates/gym/_progress_modal.html
git commit -m "feat(gym): rebuild the live workout view around the lit-state model"
```

---

## Task 8: Finished workout page and the route merge

**Files:**
- Create: `personal_apps/templates/gym/session_finished.html`
- Modify: `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: `stats.session_report(...)` output from Task 3, `performed_from_session` from Task 4.
- Produces: the merged `session_detail` route.

- [ ] **Step 1: Merge the routes**

In `session_detail`, branch on `session_.finished_at`: unfinished renders `session_detail.html` with today's context; finished builds the report (the code from Task 4 Step 3) and renders `session_finished.html`.

Replace the body of `gym_session_summary` with a redirect, keeping the route registered so old links survive:

```python
@gym_bp.route('/gym/session/<int:session_id>/summary')
@login_required
def gym_session_summary(session_id):
    # Kept as a redirect: a finished workout is one page now, and this URL is
    # in browser history and bookmarks.
    return redirect(url_for('gym.session_detail', session_id=session_id,
                            **request.args.to_dict()))
```

Change `gym_finish_session`'s redirect to `url_for('gym.session_detail', session_id=session_.id, just_finished=1)`.

Delete the Task 4 shim comment and its key adaptation for the summary page.

- [ ] **Step 2: Write `session_finished.html`**

Required elements, in this order:

1. **Record flare** — only when `record_count > 0`. One block per entry in `records`, largest first. Each shows the exercise, the new value with its unit, the previous value with its date, and the position. Cyan (`--record`), with the single-pulse flare from spec §4.5.
2. **Readouts** — Volumen (with `total_volume_delta_pct` when it is not `None`), Sätze, Dauer, Rekorde.
3. **Nach Übung** — one row per entry in `exercises`: name, position, `sets_display`, and a verdict chip driven by `verdict`. Chips: `rekord` → `--record`; `stagniert` → `--stall` outline plus the count; `steigend` → `+N % Vol.`; `neu` → "Erste Aufzeichnung"; `None` → no chip.
4. **Nächstes Mal** — only when `advice` is non-empty. For each: *"{name} steht seit {sessions} Workouts auf {stuck_at} kg — auf {suggested_weight} kg gehen, notfalls 2 Wdh. weniger."*
5. **Template update prompt** — only when `request.args.get('just_finished')` and `session.template`. POST to `/gym/session/<id>/update_template`.
6. Actions: link to Verlauf, and delete (POST `/gym/session/<id>/delete`, with confirmation).

- [ ] **Step 3: Update the two redirects whose destination moved**

`gym_delete_session` → `url_for('gym.gym_verlauf')`. That endpoint does not exist until Task 11 — leave it pointing at `gym.gym_dashboard` with a comment naming Task 11, and change it there.

- [ ] **Step 4: Verify**

Finish a real workout and confirm you land on `/gym/session/<id>?just_finished=1`. Visit `/gym/session/<id>/summary` and confirm a 302 to `/gym/session/<id>`. Check a session with a PR shows the flare, one without shows no empty container, and a freeform session omits the whole-workout comparison rather than showing a broken one.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/session_finished.html personal_apps/features/gym/routes.py
git commit -m "feat(gym): merge the finished-workout pages into one"
```

---

## Task 9: Heute

**Files:**
- Create: `personal_apps/templates/gym/heute.html`
- Modify: `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: `stats.consistency`, `stats.routine_memory`, `stats.stall_report`, `stats.muscle_group_volume`, `stats.weekly_tonnage`, `load_performed`.
- Produces: endpoint `gym.gym_heute` at `/gym`.

- [ ] **Step 1: Rewrite the view, then sweep every reference to its old name**

Rename `gym_dashboard` to `gym_heute`. It must call `load_performed()` **once** and pass that one list into every stats function. Context: `active_session`, `consistency`, `routines`, `recent_sessions` (last 5 finished), `stalls`, `balance`, `tonnage`, `templates`, `vapid_public_key`.

`catalogue_groups` for `muscle_group_volume` is the set of `muscle_group` values present on `Exercise` rows, mapped through `stats.NO_GROUP_LABEL` for `None`.

**This rename breaks every existing reference to the old endpoint name**, and one of them — `_nav.html` — renders on every page, including this one. Immediately after renaming the view function, do a literal find-and-replace of `gym.gym_dashboard` → `gym.gym_heute` in `templates/gym/_nav.html` and in every remaining call site in `features/gym/routes.py` (the redirects inside `gym_delete_session`, `gym_delete_template`, `gym_add_exercise`, `gym_delete_exercise` — left pointing at the old name by Tasks 6 and 8). This is a pure rename, not a destination change: all three nav tabs still point at the same one page, and all four redirects still land on Heute. Tasks 10 and 11 change three of those seven links to their real final destination.

`templates/gym/session_summary.html` also contains one reference. Leave it — that template is dead code after Task 8 (its route redirects instead of rendering it) and is deleted outright in Task 13.

Confirm the sweep is complete:

```bash
cd personal_apps && grep -rn "gym\.gym_dashboard" features/gym templates/gym/_nav.html
```

Expected: no output.

- [ ] **Step 2: Write the template**

**Phone order:** consistency header · routines (each with name, `days_ago` as "vor N Tagen", its exercise list, and a Starten button POSTing to `/gym/start` with `template_id`) · a free-workout start form (fields `name`, `template_id`) · last 5 workouts · the board, condensed.

**Desktop order:** a bar with "Letzte 4 Wochen", the consistency line and the start action · a three-panel board (Steht still / Sätze pro Muskelgruppe / Tonnage pro Woche) · routines and recent workouts in two columns below.

One template. The reorder is CSS grid areas and `order`, not duplicated markup.

The tonnage panel must label the `is_current` bucket as still running.

Routine rename and delete sit behind a small edit affordance per routine; delete POSTs to `/gym/templates/<id>/delete`.

- [ ] **Step 3: Confirm `gym_delete_template`'s destination is already final**

Step 1's sweep pointed all four redirects at `gym.gym_heute`. Of those four, `gym_delete_template` stays there permanently — deleting a routine belongs back on Heute, where routines are listed. No further change needed here; `gym_delete_session`, `gym_add_exercise` and `gym_delete_exercise` get their real final destination in Tasks 10 and 11.

- [ ] **Step 4: Verify**

`/gym` returns 200 at both widths. Confirm with a stopwatch-free check: the page issues one bulk query rather than one per exercise — add a temporary `print(len(rows))` or inspect with SQLAlchemy echo, and confirm the count of `SELECT` statements does not scale with the number of exercises.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/heute.html personal_apps/features/gym/routes.py
git commit -m "feat(gym): add Heute as launcher on mobile and cockpit on desktop"
```

---

## Task 10: Übungen

**Files:**
- Create: `personal_apps/templates/gym/uebungen.html`
- Modify: `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: `load_performed`, `stats.exercise_state`, `stats.dominant_position`, `stats.group_exercises_by_muscle`.
- Produces: endpoint `gym.gym_uebungen` at `/gym/uebungen`.

- [ ] **Step 1: Add the route**

One `load_performed()` call, grouped by `exercise_id`. For each exercise compute `state`, `last_done`, `best_weight`, and `best_e1rm` from that one list.

- [ ] **Step 2: Write the template**

Search box filtering rows client-side, no round trip. Sort control with three options: **nach Muskelgruppe** (default, grouped, using `group_exercises_by_muscle`), **am längsten ohne PR**, **zuletzt gemacht** — the latter two flat.

Each row: name (link to `gym.exercise_detail`), last done, current best, and a state chip per spec §5.6. `None` state shows no chip. Add-exercise form at the bottom, POSTing to `/gym/exercises/add` with fields `name`, `muscle_group`, `default_rest_seconds`, `is_unilateral`. Delete button only when the exercise has no `session_exercises` and no `template_exercises`.

- [ ] **Step 3: Point the exercise redirects here**

`gym_add_exercise` and `gym_delete_exercise` → `url_for('gym.gym_uebungen')`.

- [ ] **Step 4: Verify**

Confirm every exercise appears exactly once across all groups, search narrows correctly, each sort reorders, an exercise with no history shows **neu**, and adding then deleting an exercise lands back on this page.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/uebungen.html personal_apps/features/gym/routes.py
git commit -m "feat(gym): add the Uebungen catalogue with per-exercise state"
```

---

## Task 11: Verlauf, and the nav rewire

**Files:**
- Create: `personal_apps/templates/gym/verlauf.html`
- Modify: `personal_apps/features/gym/routes.py`, `personal_apps/templates/gym/_nav.html`

**Interfaces:**
- Consumes: `load_performed`, `stats.row_volume`.
- Produces: endpoint `gym.gym_verlauf` at `/gym/verlauf`.

- [ ] **Step 1: Add the route**

Every finished session, newest first, with its total volume and record count computed from one `load_performed()` call.

- [ ] **Step 2: Write the template**

Chronological list: name, date, duration, exercise list, total volume, and a record-count chip where non-zero. Each links to `gym.session_detail`. Per-row delete, POST `/gym/session/<id>/delete`, with confirmation.

The export panel moves here verbatim from `dashboard.html` lines 64–81: the 30-day / 90-day / all preset buttons and the from/to form GETting `/gym/export`. Its JavaScript moves too.

- [ ] **Step 3: Rewire the nav and the delete redirect**

Point the three tabs and the three desktop links at `gym.gym_heute`, `gym.gym_uebungen`, `gym.gym_verlauf`, and delete the Task 6 comment. Point `gym_delete_session` at `gym.gym_verlauf`.

- [ ] **Step 4: Verify**

All three tabs navigate and highlight correctly at both widths. Export with each preset produces a JSON download. Deleting a workout returns here.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/verlauf.html personal_apps/features/gym/routes.py personal_apps/templates/gym/_nav.html
git commit -m "feat(gym): add Verlauf with export and wire up the three real routes"
```

---

## Task 12: Exercise detail

**Files:**
- Replace: `personal_apps/templates/gym/exercise_detail.html`
- Modify: `personal_apps/static/gym/gym.js`, `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: `stats.exercise_progress` output — `table, series, available_positions, selected_position, pr_weight, pr_e1rm, state, sessions_since_pr`.
- Produces: `window.GymChart.renderProgressChart(canvas, {series, tokens})`, also used by `_progress_modal.html`.

- [ ] **Step 1: Rewrite the chart renderer**

`renderProgressChart` currently takes flat `labels/weights/minWeights/volumes` arrays and hardcodes `#d4ff3f`, `#8a8a92`, `#e8e8ec`, `#272727`. Replace both.

It must now take `series` — one dataset per workout position, so the fatigue difference between slots is visible without hiding data — and read its colours from resolved token values.

**Canvas cannot resolve `var()`.** Colours must be read out first and passed in as concrete strings:

```javascript
const styles = getComputedStyle(document.documentElement);
const token = (name) => styles.getPropertyValue(name).trim();
```

Pass `{ ink: token('--ink'), dim: token('--dim'), edge: token('--edge'), live: token('--live'), record: token('--record') }`. If a token resolves empty, the chart silently loses that colour — assert non-empty and log loudly if not.

- [ ] **Step 2: Write the template**

1. **Verdict band** — the state chip from `state`, last performance from `table[0]`, `pr_weight` and `pr_e1rm`, `sessions_since_pr`, and the concrete next step when `state == 'stagniert'`.
2. **Chart** — every session, position as series. The position filter stays, rendered as isolate-one-slot controls linking to `?position=N` and back to unfiltered. Only render the filter when `available_positions|length > 1`.
3. **History table** — date, position, `sets_display`, volume, e1RM. Unilateral exercises keep the note that weight and reps are per side and volume counts both.
4. **Metadata** — behind a `Bearbeiten` disclosure: POST `/gym/exercises/<id>/update` with fields `name`, `muscle_group`, `default_rest_seconds`, `is_unilateral`. Preserve the `name_taken` query-parameter warning and the legacy-muscle-group `(alt)` option.
5. Empty state when `table` is empty — no chart, no table, no broken PR cards.

Desktop: chart large, verdict and PR rail to its right, history full-width below.

- [ ] **Step 3: Delete the Task 4 shim**

Remove the temporary key adaptation in `exercise_detail` and its comment.

- [ ] **Step 4: Verify**

Open an exercise done in more than one position and confirm the series are separable. Open one with a single session. Open one with none. Rename an exercise to a name already taken and confirm the warning still appears and other changes still save. Confirm the modal on the live workout page still renders after the `renderProgressChart` signature change.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/exercise_detail.html personal_apps/static/gym/gym.js personal_apps/features/gym/routes.py
git commit -m "feat(gym): rebuild exercise detail with position as a chart series"
```

---

## Task 13: Delete the old templates and sweep

**Files:**
- Delete: `personal_apps/templates/gym/dashboard.html`, `personal_apps/templates/gym/session_summary.html`

- [ ] **Step 1: Confirm nothing references them**

```bash
cd personal_apps && grep -rn "dashboard.html\|session_summary.html\|gym_dashboard" --include=*.py --include=*.html .
```

Expected: no hits. Any hit is a live reference — fix it before deleting.

- [ ] **Step 2: Delete**

```bash
cd personal_apps && git rm templates/gym/dashboard.html templates/gym/session_summary.html
```

- [ ] **Step 3: Confirm no dead helpers remain in `routes.py`**

```bash
cd personal_apps && grep -n "_epley_1rm\|_set_volume\|_sessions_since_last_pr\|_session_summary_data\|_exercise_progress_data\|_group_exercises_by_muscle\|STAGNATION_THRESHOLD" features/gym/routes.py
```

Expected: no hits.

- [ ] **Step 4: Full verification sweep**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Then by hand, at 390×844 and at 1440 px: every route returns 200 (`/gym`, `/gym/uebungen`, `/gym/verlauf`, `/gym/session/<id>` for a finished and an unfinished session, `/gym/exercises/<id>`); `/gym/session/<id>/summary` 302s; a full workout can be started, logged, and finished; the resume strip appears and disappears correctly; keyboard tabbing reaches every control with a visible focus ring; and the app still installs and launches as a PWA.

- [ ] **Step 5: Commit**

```bash
git add -A personal_apps
git commit -m "chore(gym): remove the superseded dashboard and summary templates"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: §4 → Task 5; §5.1 → the file table; §5.2 routes → Tasks 8–11; §5.3 `stats.py` → Tasks 1–3; §5.4 N+1 → Task 4 Step 1, verified Task 9 Step 4; §5.5 time → Global Constraints and Task 6 Step 2; §5.6 signals → Tasks 2–3; §5.7 shell → Task 6; §6.1 → Task 9; §6.2 → Task 10; §6.3 → Task 12; §6.4 → Task 7; §6.5 → Task 8; §6.6 → Task 11; §7 accessibility → Global Constraints, verified Task 13 Step 4; §9 verification → the test files in Tasks 1 and 4.

**Known gap, stated rather than hidden.** Tasks 6–12 specify template contracts and acceptance checks, not literal markup — see the note under File Structure. The reason is that spec §4.0 deliberately delegates visual execution, and pre-writing the Jinja here would silently overrule it. Each of those tasks compensates with an explicit element list and a verification step.

**Type consistency.** `PerformedExercise` field names are used identically in Tasks 1, 3 and 4. `exercise_progress` returns `table` (not `rows`) everywhere it is consumed — Task 4 Step 3 calls this out as the reason the old templates need a temporary shim, and Task 12 Step 3 deletes it. `stall_report` entries use `sessions_since_pr` in both its definition (Task 2) and its consumer (Task 9). `renderProgressChart`'s signature change in Task 12 is flagged against its second consumer, `_progress_modal.html`, in that task's verification step.

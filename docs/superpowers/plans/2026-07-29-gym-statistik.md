# Gym Statistik Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A desktop-only fourth tab presenting all-time analytics over the whole training history, stating findings in words and staying silent when the sample cannot carry them.

**Architecture:** A new pure module `features/gym/analytics.py` holds every all-time aggregate, split from `stats.py` along the same boundary the pages use — `stats.py` answers windowed per-session judgements (Heute), `analytics.py` answers all-time descriptions (Statistik). A thin route makes one `load_performed()` call and hands the rows over. Analytics returns **structured data plus a `statable` flag**, never German prose; the template owns all copy.

**Tech Stack:** Python 3.12, Flask, Jinja2, pytest. Existing CSS bar primitives (`.hbar`, `.vbars`) for distributions; sparklines are inline SVG, so the page loads no charting library. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-07-29-gym-statistik-design.md`](../specs/2026-07-29-gym-statistik-design.md)

## Global Constraints

- **UI copy is German.** Code, comments, identifiers, commit messages are English.
- **`analytics.py` has zero SQLAlchemy imports** and zero Jinja/Flask imports. It sees `stats.PerformedExercise` and plain data only. It may import from `stats.py`; `stats.py` must never import from it.
- **No German prose in `analytics.py`.** Functions return figures plus a `statable` boolean; the template writes the sentence. This keeps copy in one place and the module unit-testable.
- **One `load_performed()` call per request.** The route makes exactly one; never inside a loop.
- **Deload rule:** excluded from progression ranking and the record timeline (judgements); included in tonnage, set counts, muscle share, rep range, fatigue curve, daypart, weekday, rest-gap (descriptions).
- **Silence rule:** a finding's sentence is gated on its sample threshold. The chart always renders, annotated with its sample size. Gates the sentence only.
- **Deload carries no colour** and the app has exactly three semantic hues (`--live`, `--record`, `--stall`). Do not add a fourth, and do not invent CSS custom properties — reuse what exists in `gym.css`.
- **Repeated identical cards are banned.** Where a list has more than one entry use two tiers: one featured item, the rest as divided `.row`s in one shared panel.
- **Never open a second `<style>` tag in a page template** — it silently swallows the next CSS rule. All CSS goes in `static/gym/gym.css`.
- **Touch targets ≥44×44 CSS px**; every interactive control is a real `<button>` or `<a>`.
- **Wide content scrolls in its own `overflow-x: auto` container** — the page body never scrolls horizontally, at 100% or 200% text.
- No emoji.
- **Run tests from `personal_apps/`:** `cd personal_apps && python -m pytest tests/ -v` (102 currently pass).

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `personal_apps/features/gym/analytics.py` | All-time aggregates, pure | 1–6 |
| `personal_apps/tests/test_gym_analytics.py` | Pure unit tests, no DB | 1–6 |
| `personal_apps/features/gym/routes.py` | `gym_statistik()` — thin | 7 |
| `personal_apps/templates/gym/_nav.html` | Fourth nav item, desktop-only | 7 |
| `personal_apps/templates/gym/statistik.html` | The page, five zones | 7–10 |
| `personal_apps/static/gym/gym.css` | Page composition + zone styles | 8–10 |
| `personal_apps/tests/test_gym_routes_smoke.py` | Route renders | 7 |
| `personal_apps/PRODUCT.md` | Record the windowed-vs-all-time split | 12 |

**Ordering:** Tasks 1–6 build the pure module bottom-up, each independently testable with no database. Task 7 makes the page reachable and empty. Tasks 8–11 fill the zones. Task 12 documents and verifies the whole.

---

## Task 1: Analytics module + Das Werk totals

**Files:**
- Create: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Consumes: `stats.PerformedExercise`, `stats.row_volume`.
- Produces: `analytics.totals(rows, now) -> dict` with keys `tonnage`, `sets`, `reps`, `sessions`, `first_session`, `days_training`, `best_session`.

**Background:** `PerformedExercise` is a frozen dataclass with `exercise_id`, `name`, `muscle_group`, `is_unilateral`, `position`, `session_id`, `started_at`, `sets` (a tuple of `(weight, reps)` pairs, completed only), `is_deload`. One row is one exercise as performed in one session, so a session's rows share `session_id` and `started_at`.

`stats.row_volume(row)` already sums `weight × reps` across a row's sets, doubling for unilateral exercises. Reuse it — do not reimplement volume.

Deloads are **included** here: the work happened.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_gym_analytics.py`:

```python
"""Tests for features.gym.analytics -- all-time aggregates. Pure functions, so
no app context, no database, no fixtures beyond plain data."""
import datetime as dt

from features.gym import analytics, stats


def perf(sets, started_at=None, session_id=1, exercise_id=1, name='Bankdruecken',
         muscle_group='Brust', is_unilateral=False, position=1, is_deload=False):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]."""
    return stats.PerformedExercise(
        exercise_id=exercise_id, name=name, muscle_group=muscle_group,
        is_unilateral=is_unilateral, position=position, session_id=session_id,
        started_at=started_at or dt.datetime(2026, 6, 1, 18, 0),
        sets=tuple(sets), is_deload=is_deload,
    )


def day(n):
    return dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=n)


NOW = dt.datetime(2026, 7, 1, 18, 0)


def test_totals_sums_tonnage_sets_and_reps():
    rows = [
        perf([(100.0, 10), (100.0, 8)], started_at=day(0), session_id=1),
        perf([(50.0, 5)], started_at=day(2), session_id=2),
    ]
    result = analytics.totals(rows, NOW)
    assert result['tonnage'] == 100.0 * 10 + 100.0 * 8 + 50.0 * 5
    assert result['sets'] == 3
    assert result['reps'] == 23
    assert result['sessions'] == 2


def test_totals_counts_a_unilateral_row_at_double_volume():
    # matches stats.set_volume: both sides did the work
    rows = [perf([(20.0, 10)], is_unilateral=True)]
    assert analytics.totals(rows, NOW)['tonnage'] == 400.0


def test_totals_includes_deload_sessions_because_the_work_happened():
    rows = [
        perf([(100.0, 10)], started_at=day(0), session_id=1),
        perf([(60.0, 10)], started_at=day(2), session_id=2, is_deload=True),
    ]
    result = analytics.totals(rows, NOW)
    assert result['sessions'] == 2
    assert result['tonnage'] == 1000.0 + 600.0


def test_totals_reports_the_training_span_from_the_first_session():
    rows = [perf([(100.0, 10)], started_at=day(0)), perf([(100.0, 10)], started_at=day(10), session_id=2)]
    result = analytics.totals(rows, NOW)
    assert result['first_session'] == day(0)
    assert result['days_training'] == (NOW - day(0)).days


def test_totals_names_the_biggest_session_by_tonnage_with_its_date():
    rows = [
        perf([(100.0, 10)], started_at=day(0), session_id=1),   # 1000
        perf([(100.0, 20)], started_at=day(3), session_id=2),   # 2000
    ]
    best = analytics.totals(rows, NOW)['best_session']
    assert best['session_id'] == 2
    assert best['volume'] == 2000.0
    assert best['started_at'] == day(3)


def test_totals_on_no_history_is_zeroed_not_broken():
    result = analytics.totals([], NOW)
    assert result['tonnage'] == 0
    assert result['sessions'] == 0
    assert result['first_session'] is None
    assert result['days_training'] is None
    assert result['best_session'] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'features.gym.analytics'`

- [ ] **Step 3: Create the module**

Create `personal_apps/features/gym/analytics.py`:

```python
"""All-time analytics for the Statistik page.

The split from stats.py mirrors the split between the pages themselves:

    stats.py      windowed, per-session JUDGEMENTS -- is this a record, is
                  this stalling, what does the last 28 days look like.
                  Feeds Heute and the session pages.

    analytics.py  all-time AGGREGATES and DESCRIPTIONS -- totals, rankings,
                  distributions, behavioural patterns over the whole history.
                  Feeds Statistik.

The same question that decides which page a figure belongs on decides which
module it lives in: is this about now, or about everything?

This module may import from stats.py; stats.py must never import from here.
Like stats.py it is deliberately free of SQLAlchemy, Flask and Jinja -- it
sees stats.PerformedExercise and plain data, nothing else.

It also contains NO German prose. Every function returns figures plus a
`statable` flag where a finding is involved; the template writes the sentence.
Copy belongs in one place, and a module that returns numbers is one that can
be unit-tested.
"""
import datetime as dt
from collections import defaultdict

from . import stats


def _sessions(rows):
    """{session_id: started_at} across the given rows."""
    return {row.session_id: row.started_at for row in rows}


def totals(rows, now):
    """Das Werk: the cumulative body of work, all time.

    Deload sessions are included -- this describes what was actually lifted,
    and a deliberately light session was still lifted.

    `days_training` counts from the first session to `now` rather than to the
    last session: the span is how long you have been at it, not how long the
    log happens to cover.
    """
    if not rows:
        return {'tonnage': 0, 'sets': 0, 'reps': 0, 'sessions': 0,
                'first_session': None, 'days_training': None, 'best_session': None}

    volume_by_session = defaultdict(float)
    for row in rows:
        volume_by_session[row.session_id] += stats.row_volume(row)

    started = _sessions(rows)
    best_id = max(volume_by_session, key=lambda sid: volume_by_session[sid])
    first = min(started.values())

    return {
        'tonnage': round(sum(volume_by_session.values()), 1),
        'sets': sum(len(row.sets) for row in rows),
        'reps': sum(reps for row in rows for _, reps in row.sets),
        'sessions': len(volume_by_session),
        'first_session': first,
        'days_training': (now - first).days,
        'best_session': {
            'session_id': best_id,
            'started_at': started[best_id],
            'volume': round(volume_by_session[best_id], 1),
        },
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Confirm the module stayed pure**

```bash
cd personal_apps && grep -nE "sqlalchemy|flask|jinja|from models|import models" features/gym/analytics.py
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): add analytics module with all-time totals"
```

---

## Task 2: Fortschritt — progression ranking

**Files:**
- Modify: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Consumes: `stats.progression_rows`, `stats.best_e1rm`, `stats.best_weight`.
- Produces: `analytics.progression_ranking(rows) -> list[dict]` with keys `exercise_id`, `name`, `sessions`, `first_e1rm`, `current_e1rm`, `change_pct`, `best_weight`, `points`.

**Background:** `stats.progression_rows(rows)` returns only rows that count as an attempt at progress — it strips deload rows. Use it; do not filter by hand.

This is a **judgement**, so deloads are excluded. An exercise needs at least two qualifying sessions or there is no first-versus-current to compute.

`points` is the chronological list of per-session best e1RM values, for the sparkline in Task 10.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def test_progression_ranking_reports_first_to_current_change():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['sessions'] == 2
    assert entry['first_e1rm'] == round(stats.epley_1rm(100.0, 8), 1)
    assert entry['current_e1rm'] == round(stats.epley_1rm(110.0, 8), 1)
    assert entry['change_pct'] == 10.0
    assert entry['best_weight'] == 110.0
    assert len(entry['points']) == 2


def test_progression_ranking_sorts_biggest_gain_first():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, exercise_id=1, name='Klein'),
        perf([(105.0, 8)], started_at=day(7), session_id=2, exercise_id=1, name='Klein'),
        perf([(50.0, 8)], started_at=day(0), session_id=1, exercise_id=2, name='Gross'),
        perf([(75.0, 8)], started_at=day(7), session_id=2, exercise_id=2, name='Gross'),
    ]
    assert [e['name'] for e in analytics.progression_ranking(rows)] == ['Gross', 'Klein']


def test_progression_ranking_excludes_deload_sessions():
    # a 200 kg deload must not become the "current" figure
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
        perf([(200.0, 8)], started_at=day(14), session_id=3, is_deload=True),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['sessions'] == 2
    assert entry['current_e1rm'] == round(stats.epley_1rm(110.0, 8), 1)


def test_progression_ranking_skips_an_exercise_with_one_session():
    rows = [perf([(100.0, 8)], started_at=day(0), session_id=1)]
    assert analytics.progression_ranking(rows) == []


def test_progression_ranking_skips_an_exercise_whose_history_is_all_deloads():
    rows = [
        perf([(60.0, 8)], started_at=day(0), session_id=1, is_deload=True),
        perf([(60.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert analytics.progression_ranking(rows) == []


def test_progression_ranking_on_no_history_is_empty():
    assert analytics.progression_ranking([]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -k progression_ranking -v
```

Expected: FAIL — `AttributeError: module 'features.gym.analytics' has no attribute 'progression_ranking'`

- [ ] **Step 3: Implement**

Append to `personal_apps/features/gym/analytics.py`:

```python
def progression_ranking(rows):
    """Fortschritt: every exercise ranked by all-time change in estimated 1RM.

    A judgement, so deload rows are dropped via stats.progression_rows() --
    a deliberately light session is not an attempt at a heavier one, and a
    200 kg typo in a deload week must not become anyone's "current".

    An exercise needs two qualifying sessions: with one there is no
    first-versus-current to compute, and reporting 0 % would be a claim the
    data does not make.

    `points` is the per-session best e1RM in chronological order, for the
    sparkline. One point per session, not per set.
    """
    by_exercise = defaultdict(list)
    for row in stats.progression_rows(rows):
        by_exercise[row.exercise_id].append(row)

    ranking = []
    for exercise_id, exercise_rows in by_exercise.items():
        # one entry per session: an exercise performed twice in a session
        # (two slots) is still one data point on its curve
        best_per_session = {}
        for row in exercise_rows:
            current = stats.best_e1rm(row)
            seen = best_per_session.get(row.session_id)
            if seen is None or current > seen[1]:
                best_per_session[row.session_id] = (row.started_at, current)

        ordered = sorted(best_per_session.values())
        if len(ordered) < 2:
            continue

        first_e1rm = ordered[0][1]
        current_e1rm = ordered[-1][1]
        ranking.append({
            'exercise_id': exercise_id,
            'name': exercise_rows[0].name,
            'sessions': len(ordered),
            'first_e1rm': round(first_e1rm, 1),
            'current_e1rm': round(current_e1rm, 1),
            'change_pct': round((current_e1rm - first_e1rm) / first_e1rm * 100, 1),
            'best_weight': max(stats.best_weight(row) for row in exercise_rows),
            'points': [round(value, 1) for _, value in ordered],
        })

    ranking.sort(key=lambda entry: (-entry['change_pct'], entry['name']))
    return ranking
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): rank every exercise by all-time e1RM change"
```

---

## Task 3: Within-session behaviour — rep range and fatigue

**Files:**
- Modify: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Produces: `analytics.MIN_SETS_FOR_REP_RANGE = 50`, `analytics.MIN_ROWS_FOR_FATIGUE = 30`; `analytics.rep_range_distribution(rows) -> dict`, `analytics.fatigue_curve(rows) -> dict`.

**Background:** These describe what happened, so deloads are **included**.

Both return a `statable` flag implementing the spec's silence rule. `statable` gates the template's sentence; the chart renders regardless, which is why `sample` is always returned.

Rep buckets are `1-5`, `6-8`, `9-12`, `13+` — the boundaries the app already uses when talking about rep ranges.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def test_rep_range_distribution_buckets_every_set():
    rows = [perf([(100.0, 3), (100.0, 7), (100.0, 10), (100.0, 15)])]
    result = analytics.rep_range_distribution(rows)
    counts = {b['label']: b['sets'] for b in result['buckets']}
    assert counts == {'1-5': 1, '6-8': 1, '9-12': 1, '13+': 1}
    assert result['sample'] == 4


def test_rep_range_distribution_reports_the_dominant_bucket_share():
    rows = [perf([(100.0, 7)] * 3 + [(100.0, 10)])]
    result = analytics.rep_range_distribution(rows)
    assert result['dominant']['label'] == '6-8'
    assert result['dominant']['share'] == 75.0


def test_rep_range_distribution_is_not_statable_below_the_threshold():
    rows = [perf([(100.0, 8)] * (analytics.MIN_SETS_FOR_REP_RANGE - 1))]
    assert analytics.rep_range_distribution(rows)['statable'] is False


def test_rep_range_distribution_is_statable_at_the_threshold():
    rows = [perf([(100.0, 8)] * analytics.MIN_SETS_FOR_REP_RANGE)]
    assert analytics.rep_range_distribution(rows)['statable'] is True


def test_rep_range_distribution_includes_deloads_because_it_describes():
    rows = [perf([(60.0, 8)] * analytics.MIN_SETS_FOR_REP_RANGE, is_deload=True)]
    assert analytics.rep_range_distribution(rows)['sample'] == analytics.MIN_SETS_FOR_REP_RANGE


def test_rep_range_distribution_on_no_history_is_empty_not_broken():
    result = analytics.rep_range_distribution([])
    assert result['sample'] == 0
    assert result['statable'] is False
    assert result['dominant'] is None


def test_fatigue_curve_averages_first_versus_last_set():
    rows = [perf([(100.0, 10), (90.0, 8)])]        # -10 % weight, 10 -> 8 reps
    result = analytics.fatigue_curve(rows)
    assert result['weight_change_pct'] == -10.0
    assert result['first_reps'] == 10.0
    assert result['last_reps'] == 8.0
    assert result['sample'] == 1


def test_fatigue_curve_ignores_rows_with_a_single_set():
    rows = [perf([(100.0, 10)]), perf([(100.0, 10), (90.0, 8)], session_id=2)]
    assert analytics.fatigue_curve(rows)['sample'] == 1


def test_fatigue_curve_is_not_statable_below_the_threshold():
    rows = [perf([(100.0, 10), (90.0, 8)], session_id=i)
            for i in range(analytics.MIN_ROWS_FOR_FATIGUE - 1)]
    assert analytics.fatigue_curve(rows)['statable'] is False


def test_fatigue_curve_on_no_history_is_empty_not_broken():
    result = analytics.fatigue_curve([])
    assert result['sample'] == 0
    assert result['statable'] is False
    assert result['weight_change_pct'] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -k "rep_range or fatigue" -v
```

Expected: FAIL — `AttributeError: module 'features.gym.analytics' has no attribute 'MIN_SETS_FOR_REP_RANGE'`

- [ ] **Step 3: Implement**

Append to `personal_apps/features/gym/analytics.py`. Put the constants at the **top** of the module, directly under the imports:

```python
# --- silence thresholds -----------------------------------------------------
# A stated finding must never outrun its sample. Each figure below is the
# point at which a pattern stops being plausibly coincidental for one lifter's
# log, set deliberately low enough that the page says something in its first
# months. They gate the SENTENCE only -- the chart always renders, annotated
# with its own sample size, so nothing is ever hidden.
MIN_SETS_FOR_REP_RANGE = 50
MIN_ROWS_FOR_FATIGUE = 30
```

And the functions at the end:

```python
# Rep buckets, and the boundaries the app already uses when it talks about
# rep ranges: heavy / working / hypertrophy / endurance.
REP_BUCKETS = (('1-5', 1, 5), ('6-8', 6, 8), ('9-12', 9, 12), ('13+', 13, None))


def rep_range_distribution(rows):
    """How the lifter's sets distribute across rep ranges, all time.

    A description, so deload sets are included -- eight reps in a light week
    is still eight reps.
    """
    counts = {label: 0 for label, _, _ in REP_BUCKETS}
    for row in rows:
        for _, reps in row.sets:
            for label, low, high in REP_BUCKETS:
                if reps >= low and (high is None or reps <= high):
                    counts[label] += 1
                    break

    sample = sum(counts.values())
    buckets = [
        {'label': label, 'sets': counts[label],
         'share': round(counts[label] / sample * 100, 1) if sample else 0.0}
        for label, _, _ in REP_BUCKETS
    ]
    dominant = max(buckets, key=lambda b: b['sets']) if sample else None
    return {
        'buckets': buckets,
        'sample': sample,
        'dominant': dominant,
        'statable': sample >= MIN_SETS_FOR_REP_RANGE,
    }


def fatigue_curve(rows):
    """How much the lifter drops off within one exercise: first set vs last.

    Only rows with at least two sets can answer this; a single-set row has no
    drop-off to measure and is excluded from the sample rather than counted as
    zero, which would flatten the average toward nothing.

    A description, so deloads are included.
    """
    weight_deltas = []
    first_reps = []
    last_reps = []
    for row in rows:
        if len(row.sets) < 2:
            continue
        (first_weight, first_rep) = row.sets[0]
        (last_weight, last_rep) = row.sets[-1]
        if first_weight > 0:
            weight_deltas.append((last_weight - first_weight) / first_weight * 100)
        first_reps.append(first_rep)
        last_reps.append(last_rep)

    sample = len(first_reps)
    if not sample:
        return {'sample': 0, 'statable': False, 'weight_change_pct': None,
                'first_reps': None, 'last_reps': None}

    return {
        'sample': sample,
        'statable': sample >= MIN_ROWS_FOR_FATIGUE,
        'weight_change_pct': (round(sum(weight_deltas) / len(weight_deltas), 1)
                              if weight_deltas else None),
        'first_reps': round(sum(first_reps) / sample, 1),
        'last_reps': round(sum(last_reps) / sample, 1),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): add rep-range and within-session fatigue analytics"
```

---

## Task 4: Scheduling behaviour — daypart, weekday, rest gap

**Files:**
- Modify: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Produces: `analytics.MIN_SESSIONS_PER_DAYPART = 8`, `analytics.MIN_SESSIONS_PER_GAP_BUCKET = 5`, `analytics.MIN_SESSIONS_FOR_WEEKDAY = 14`; `analytics.daypart_volume(rows) -> dict`, `analytics.weekday_distribution(rows) -> dict`, `analytics.rest_gap_effect(rows) -> dict`.

**Background:** All three are descriptions — deloads included.

Dayparts are `morning` 08:00–13:59 and `evening` 19:00–22:59, matching the two clusters actually present in the data; sessions outside both are counted in an `other` bucket that never carries a finding.

**Keys are English; the template maps them to German.** This module holds no
user-visible copy — that is what lets the wording change without editing
Python, and it is why weekdays are returned as an index rather than a label.

`daypart_volume` is statable only when **both** compared buckets clear the threshold — comparing 11 sessions against 2 is not a comparison.

Weekdays are returned as `weekday` 0–6 (Monday-first, matching
`datetime.weekday()`), never as labels. The template owns the German short
forms.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def at(hour, days=0, session_id=1, weight=100.0, reps=10):
    return perf([(weight, reps)], session_id=session_id,
                started_at=dt.datetime(2026, 6, 1, hour, 0) + dt.timedelta(days=days))


def test_daypart_volume_separates_morning_from_evening():
    rows = [at(9, days=0, session_id=1), at(20, days=1, session_id=2)]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    assert parts['morning']['sessions'] == 1
    assert parts['evening']['sessions'] == 1


def test_daypart_volume_reports_volume_per_session_not_total():
    rows = [at(9, days=0, session_id=1, reps=10), at(9, days=1, session_id=2, reps=30)]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    # 1000 + 3000 across two sessions -> 2000 average
    assert parts['morning']['avg_volume'] == 2000.0


def test_daypart_volume_needs_both_buckets_to_clear_the_threshold():
    # plenty of mornings, one evening -- not a comparison
    rows = [at(9, days=i, session_id=i) for i in range(analytics.MIN_SESSIONS_PER_DAYPART)]
    rows.append(at(20, days=99, session_id=99))
    assert analytics.daypart_volume(rows)['statable'] is False


def test_daypart_volume_is_statable_when_both_buckets_clear_it():
    n = analytics.MIN_SESSIONS_PER_DAYPART
    rows = [at(9, days=i, session_id=i) for i in range(n)]
    rows += [at(20, days=100 + i, session_id=100 + i) for i in range(n)]
    assert analytics.daypart_volume(rows)['statable'] is True


def test_daypart_volume_on_no_history_is_empty_not_broken():
    result = analytics.daypart_volume([])
    assert result['statable'] is False
    assert all(p['sessions'] == 0 for p in result['parts'])


def test_weekday_distribution_counts_sessions_per_weekday():
    # 2026-06-01 is a Monday
    rows = [at(9, days=0, session_id=1), at(9, days=0, session_id=1),
            at(9, days=1, session_id=2)]
    days = {d['weekday']: d['sessions'] for d in analytics.weekday_distribution(rows)['days']}
    assert days[0] == 1      # Monday: one session, two rows
    assert days[1] == 1
    assert days[6] == 0      # Sunday: never trained, still present


def test_weekday_distribution_lists_monday_first_and_carries_no_copy():
    days = analytics.weekday_distribution([])['days']
    assert [d['weekday'] for d in days] == [0, 1, 2, 3, 4, 5, 6]
    assert all('label' not in d for d in days), 'weekday copy belongs in the template'


def test_rest_gap_effect_buckets_by_days_since_the_previous_session():
    rows = [at(9, days=0, session_id=1), at(9, days=1, session_id=2),
            at(9, days=5, session_id=3)]
    buckets = {b['label']: b for b in analytics.rest_gap_effect(rows)['buckets']}
    assert buckets['0-1']['sessions'] == 1     # session 2, one day after session 1
    assert buckets['4+']['sessions'] == 1      # session 3, four days after session 2


def test_rest_gap_effect_is_not_statable_on_tiny_buckets():
    rows = [at(9, days=i * 2, session_id=i) for i in range(4)]
    assert analytics.rest_gap_effect(rows)['statable'] is False


def test_rest_gap_effect_on_no_history_is_empty_not_broken():
    result = analytics.rest_gap_effect([])
    assert result['statable'] is False
    assert all(b['sessions'] == 0 for b in result['buckets'])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -k "daypart or weekday or rest_gap" -v
```

Expected: FAIL — `AttributeError: module 'features.gym.analytics' has no attribute 'daypart_volume'`

- [ ] **Step 3: Implement**

Add to the constants block at the top of `analytics.py`:

```python
MIN_SESSIONS_PER_DAYPART = 8
MIN_SESSIONS_PER_GAP_BUCKET = 5
MIN_SESSIONS_FOR_WEEKDAY = 14
```

Append the functions:

```python
# The two clusters the training log actually contains. Sessions outside both
# fall into `andere`, which is reported but never carries a finding -- a
# bucket defined as "everything else" cannot support a claim about behaviour.
DAYPARTS = (('morning', 8, 14), ('evening', 19, 23))
WEEKDAYS = tuple(range(7))   # 0 = Monday, matching datetime.weekday()
GAP_BUCKETS = (('0-1', 0, 1), ('2', 2, 2), ('3', 3, 3), ('4+', 4, None))


def _session_volumes(rows):
    """[(started_at, volume)] per session, chronological."""
    volume = defaultdict(float)
    started = {}
    for row in rows:
        volume[row.session_id] += stats.row_volume(row)
        started[row.session_id] = row.started_at
    return sorted((started[sid], volume[sid]) for sid in volume)


def daypart_volume(rows):
    """Volume per session by time of day.

    Per session, not total: a bucket with more sessions in it would otherwise
    always "win", which measures how often you train then, not how well.

    Statable only when BOTH named buckets clear the threshold -- eleven
    mornings against two evenings is not a comparison, it is one bucket.
    """
    sessions = _session_volumes(rows)
    buckets = {label: [] for label, _, _ in DAYPARTS}
    buckets['other'] = []
    for started_at, volume in sessions:
        for label, low, high in DAYPARTS:
            if low <= started_at.hour < high:
                buckets[label].append(volume)
                break
        else:
            buckets['other'].append(volume)

    parts = [
        {'label': label,
         'sessions': len(buckets[label]),
         'volume': round(sum(buckets[label]), 1),
         'avg_volume': round(sum(buckets[label]) / len(buckets[label]), 1) if buckets[label] else 0.0}
        for label in list(dict.fromkeys([label for label, _, _ in DAYPARTS] + ['other']))
    ]
    named = [p for p in parts if p['label'] != 'other']
    return {
        'parts': parts,
        'statable': all(p['sessions'] >= MIN_SESSIONS_PER_DAYPART for p in named),
    }


def weekday_distribution(rows):
    """Sessions per weekday, Monday first, as an INDEX (0-6) not a label --
    this module holds no user-visible copy.

    Every weekday is always present, including the ones never trained: a
    missing Sunday and a Sunday at zero are different facts, and only one of
    them is true."""
    sessions = _session_volumes(rows)
    counts = {index: 0 for index in WEEKDAYS}
    for started_at, _ in sessions:
        counts[started_at.weekday()] += 1

    total = len(sessions)
    return {
        'days': [
            {'weekday': index, 'sessions': counts[index],
             'share': round(counts[index] / total * 100, 1) if total else 0.0}
            for index in WEEKDAYS
        ],
        'sample': total,
        'statable': total >= MIN_SESSIONS_FOR_WEEKDAY,
    }


def rest_gap_effect(rows):
    """Volume as a function of days since the previous session.

    The first session has no previous one and is excluded -- it has no gap,
    which is not the same as a gap of zero.
    """
    sessions = _session_volumes(rows)
    buckets = {label: [] for label, _, _ in GAP_BUCKETS}
    for index in range(1, len(sessions)):
        gap = (sessions[index][0] - sessions[index - 1][0]).days
        for label, low, high in GAP_BUCKETS:
            if gap >= low and (high is None or gap <= high):
                buckets[label].append(sessions[index][1])
                break

    result = [
        {'label': label,
         'sessions': len(buckets[label]),
         'avg_volume': round(sum(buckets[label]) / len(buckets[label]), 1) if buckets[label] else 0.0}
        for label, _, _ in GAP_BUCKETS
    ]
    populated = [b for b in result if b['sessions']]
    return {
        'buckets': result,
        # every bucket that exists at all must be big enough, and there must be
        # at least two of them -- one bucket is a number, not a relationship
        'statable': (len(populated) >= 2
                     and all(b['sessions'] >= MIN_SESSIONS_PER_GAP_BUCKET for b in populated)),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): add daypart, weekday and rest-gap analytics"
```

---

## Task 5: Wohin die Arbeit geht — effort distribution

**Files:**
- Modify: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Consumes: `stats.NO_GROUP_LABEL`, `stats.row_volume`.
- Produces: `analytics.effort_distribution(rows) -> dict` with keys `groups` and `exercises`, each a list of `{'label', 'volume', 'sets', 'share'}` sorted by volume descending.

**Background:** A description — deloads included. `share` is percent of total tonnage.

An exercise or group with no completed sets never appears: it has no row in `rows` at all. Do not synthesise zero entries from the catalogue — that is `stats.muscle_group_volume`'s job on Heute, where a group at zero is the actionable finding. Here, absence is absence.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def test_effort_distribution_splits_tonnage_by_muscle_group():
    rows = [
        perf([(100.0, 10)], muscle_group='Brust', exercise_id=1, name='Bank'),
        perf([(50.0, 10)], muscle_group='Ruecken', exercise_id=2, name='Rudern', session_id=2),
    ]
    groups = {g['label']: g for g in analytics.effort_distribution(rows)['groups']}
    assert groups['Brust']['volume'] == 1000.0
    assert groups['Brust']['share'] == round(1000 / 1500 * 100, 1)
    assert groups['Ruecken']['volume'] == 500.0


def test_effort_distribution_sorts_biggest_share_first():
    rows = [
        perf([(10.0, 10)], muscle_group='Klein', exercise_id=1, name='A'),
        perf([(100.0, 10)], muscle_group='Gross', exercise_id=2, name='B', session_id=2),
    ]
    assert [g['label'] for g in analytics.effort_distribution(rows)['groups']] == ['Gross', 'Klein']


def test_effort_distribution_also_breaks_down_per_exercise():
    rows = [perf([(100.0, 10)], exercise_id=1, name='Bankdruecken')]
    exercises = analytics.effort_distribution(rows)['exercises']
    assert exercises[0]['label'] == 'Bankdruecken'
    assert exercises[0]['sets'] == 1


def test_effort_distribution_labels_an_exercise_without_a_group():
    rows = [perf([(100.0, 10)], muscle_group=None)]
    assert analytics.effort_distribution(rows)['groups'][0]['label'] == stats.NO_GROUP_LABEL


def test_effort_distribution_includes_deloads_because_it_describes():
    rows = [perf([(60.0, 10)], muscle_group='Brust', is_deload=True)]
    assert analytics.effort_distribution(rows)['groups'][0]['volume'] == 600.0


def test_effort_distribution_on_no_history_is_empty_not_broken():
    result = analytics.effort_distribution([])
    assert result['groups'] == []
    assert result['exercises'] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -k effort_distribution -v
```

Expected: FAIL — `AttributeError: module 'features.gym.analytics' has no attribute 'effort_distribution'`

- [ ] **Step 3: Implement**

Append to `personal_apps/features/gym/analytics.py`:

```python
def _share_table(pairs, total):
    """[{label, volume, sets, share}] sorted by volume, biggest first."""
    table = [
        {'label': label, 'volume': round(volume, 1), 'sets': sets,
         'share': round(volume / total * 100, 1) if total else 0.0}
        for label, (volume, sets) in pairs.items()
    ]
    table.sort(key=lambda entry: (-entry['volume'], entry['label']))
    return table


def effort_distribution(rows):
    """Wohin die Arbeit geht: where the tonnage actually went, all time.

    Split two ways -- by muscle group and by exercise -- because they answer
    different questions: whether the body is trained evenly, and which lifts
    the training is actually made of.

    A description, so deloads are included.

    Nothing is synthesised at zero. An exercise never performed has no row
    here at all, and a group with no trained exercises simply does not appear.
    Heute's muscle_group_volume() deliberately does the opposite, because
    there a group at zero IS the finding; here absence is just absence.
    """
    groups = defaultdict(lambda: [0.0, 0])
    exercises = defaultdict(lambda: [0.0, 0])
    total = 0.0
    for row in rows:
        volume = stats.row_volume(row)
        total += volume
        group = row.muscle_group or stats.NO_GROUP_LABEL
        groups[group][0] += volume
        groups[group][1] += len(row.sets)
        exercises[row.name][0] += volume
        exercises[row.name][1] += len(row.sets)

    return {
        'groups': _share_table({k: tuple(v) for k, v in groups.items()}, total),
        'exercises': _share_table({k: tuple(v) for k, v in exercises.items()}, total),
        'total_volume': round(total, 1),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): add all-time effort distribution by group and exercise"
```

---

## Task 6: Rekorde — the record timeline

**Files:**
- Modify: `personal_apps/features/gym/analytics.py`
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Consumes: `stats.progression_rows`, `stats.best_weight`, `stats.best_e1rm`.
- Produces: `analytics.record_timeline(rows) -> list[dict]` with keys `started_at`, `session_id`, `exercise_id`, `name`, `kind`, `value`, `previous`; newest first.

**Background:** A judgement — deloads excluded via `stats.progression_rows`.

A record is a session that beat every *earlier* session for that exercise. This is deliberately **chronological**, unlike `stats.session_record_counts`, which asks "beats every OTHER session" so a page can show a stable count. A timeline is a history: what was true on the day. The first session of an exercise is not a record — there was nothing to beat.

Two kinds, `weight` and `e1rm`, reported separately: beating your heaviest single and beating your best estimated max are different achievements and one session can do both.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def test_record_timeline_reports_a_beaten_previous_best():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    weight_records = [r for r in analytics.record_timeline(rows) if r['kind'] == 'weight']
    assert len(weight_records) == 1
    assert weight_records[0]['value'] == 110.0
    assert weight_records[0]['previous'] == 100.0
    assert weight_records[0]['started_at'] == day(7)


def test_record_timeline_does_not_count_the_first_session():
    rows = [perf([(100.0, 8)], started_at=day(0), session_id=1)]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_is_newest_first():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
        perf([(120.0, 8)], started_at=day(14), session_id=3),
    ]
    dates = [r['started_at'] for r in analytics.record_timeline(rows) if r['kind'] == 'weight']
    assert dates == [day(14), day(7)]


def test_record_timeline_excludes_deload_sessions():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_reports_weight_and_e1rm_separately():
    # more reps at the same weight: an e1RM record but not a weight record
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(100.0, 12)], started_at=day(7), session_id=2),
    ]
    kinds = {r['kind'] for r in analytics.record_timeline(rows)}
    assert kinds == {'e1rm'}


def test_record_timeline_on_no_history_is_empty():
    assert analytics.record_timeline([]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -k record_timeline -v
```

Expected: FAIL — `AttributeError: module 'features.gym.analytics' has no attribute 'record_timeline'`

- [ ] **Step 3: Implement**

Append to `personal_apps/features/gym/analytics.py`:

```python
def record_timeline(rows):
    """Rekorde: every personal best ever set, newest first.

    A judgement, so deload rows are dropped -- a light week cannot hold a
    record.

    Chronological by construction: a record is a session that beat every
    EARLIER session for that exercise. stats.session_record_counts() asks a
    deliberately different question ("beats every OTHER session") so a page can
    show a count that does not change as later sessions arrive. A timeline is a
    history, and history is what was true on the day.

    The first session of an exercise is never a record: there was nothing to
    beat, and calling it one would make every exercise's debut a milestone.
    """
    by_exercise = defaultdict(dict)
    for row in stats.progression_rows(rows):
        seen = by_exercise[row.exercise_id].get(row.session_id)
        candidate = (row.started_at, stats.best_weight(row), stats.best_e1rm(row), row.name)
        if seen is None:
            by_exercise[row.exercise_id][row.session_id] = candidate
        else:
            # same exercise twice in one session: judge it as its best showing
            by_exercise[row.exercise_id][row.session_id] = (
                seen[0], max(seen[1], candidate[1]), max(seen[2], candidate[2]), seen[3])

    timeline = []
    for exercise_id, sessions in by_exercise.items():
        ordered = sorted(sessions.items(), key=lambda item: item[1][0])
        best_weight = None
        best_e1rm = None
        for session_id, (started_at, weight, e1rm, name) in ordered:
            if best_weight is not None and weight > best_weight:
                timeline.append({'started_at': started_at, 'session_id': session_id,
                                 'exercise_id': exercise_id, 'name': name,
                                 'kind': 'weight', 'value': round(weight, 1),
                                 'previous': round(best_weight, 1)})
            if best_e1rm is not None and e1rm > best_e1rm:
                timeline.append({'started_at': started_at, 'session_id': session_id,
                                 'exercise_id': exercise_id, 'name': name,
                                 'kind': 'e1rm', 'value': round(e1rm, 1),
                                 'previous': round(best_e1rm, 1)})
            best_weight = weight if best_weight is None else max(best_weight, weight)
            best_e1rm = e1rm if best_e1rm is None else max(best_e1rm, e1rm)

    timeline.sort(key=lambda entry: (entry['started_at'], entry['name']), reverse=True)
    return timeline
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_analytics.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): add the all-time record timeline"
```

---

## Task 7: Route, navigation, and the page shell

**Files:**
- Modify: `personal_apps/features/gym/routes.py`
- Modify: `personal_apps/templates/gym/_nav.html`
- Create: `personal_apps/templates/gym/statistik.html`
- Modify: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: every function from Tasks 1–6.
- Produces: endpoint `gym.gym_statistik` at `GET /gym/statistik`; template context `totals`, `progression`, `rep_range`, `fatigue`, `daypart`, `weekday`, `rest_gap`, `effort`, `records`.

**Background:** `_nav.html` defines `gym_nav_items` as a Jinja list literal looped by **both** the `.topbar` (desktop, shown at `min-width: 900px`) and the `.tabbar` (mobile, `grid-template-columns: repeat(3, 1fr)`). A `desktop_only` flag filtered out of the tabbar loop keeps the phone bar at exactly three tabs — do not change the grid.

`load_performed()` must be called exactly once. It already excludes unfinished sessions and rows with no completed sets.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`:

```python
def test_statistik_renders(client):
    assert client.get('/gym/statistik').status_code == 200
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd personal_apps && python -m pytest tests/test_gym_routes_smoke.py -k statistik -v
```

Expected: FAIL — `assert 404 == 200`

- [ ] **Step 3: Add the route**

In `personal_apps/features/gym/routes.py`, add the analytics import beside the existing `stats` import at the top of the file:

```python
from . import analytics
```

Then add the route after `gym_verlauf`:

```python
@gym_bp.route('/gym/statistik')
@login_required
def gym_statistik():
    """All-time analytics (spec 2026-07-29). Desktop-only in the navigation,
    but the URL stays reachable: opening it on a phone renders the page
    single-column rather than redirecting, because hiding data the user asked
    for is worse than showing it in a cramped layout.

    Thin by construction. The one bulk load below feeds every figure on the
    page -- same discipline as Heute/Uebungen/Verlauf (spec 5.4): never one
    query per exercise, no matter how long the history gets. All analysis
    lives in analytics.py.
    """
    now = dt.datetime.utcnow()
    performed = load_performed()
    return render_template(
        'gym/statistik.html',
        now=now,
        totals=analytics.totals(performed, now),
        progression=analytics.progression_ranking(performed),
        rep_range=analytics.rep_range_distribution(performed),
        fatigue=analytics.fatigue_curve(performed),
        daypart=analytics.daypart_volume(performed),
        weekday=analytics.weekday_distribution(performed),
        rest_gap=analytics.rest_gap_effect(performed),
        effort=analytics.effort_distribution(performed),
        records=analytics.record_timeline(performed),
    )
```

- [ ] **Step 4: Add the navigation entry**

In `personal_apps/templates/gym/_nav.html`, extend the `gym_nav_items` literal:

```jinja
{% set gym_nav_items = [
    {'label': 'Heute', 'endpoint': 'gym.gym_heute'},
    {'label': 'Übungen', 'endpoint': 'gym.gym_uebungen'},
    {'label': 'Verlauf', 'endpoint': 'gym.gym_verlauf'},
    {'label': 'Statistik', 'endpoint': 'gym.gym_statistik', 'desktop_only': true},
] %}
```

Then filter it out of the **tabbar** loop only (leave the topbar loop untouched):

```jinja
<nav class="tabbar" aria-label="Hauptnavigation">
    {# desktop_only items are skipped here: the bar is a fixed 3-column grid
       and Statistik is composed for a width a phone does not have. The route
       stays reachable by URL. #}
    {% for item in gym_nav_items if not item.get('desktop_only') %}
    <a href="{{ url_for(item.endpoint) }}" class="tabbar__tab{{ ' is-active' if request.endpoint == item.endpoint else '' }}">{{ item.label }}</a>
    {% endfor %}
</nav>
```

- [ ] **Step 5: Create the page shell**

Create `personal_apps/templates/gym/statistik.html`:

```jinja
{% extends 'gym/_base.html' %}

{# Statistik: all-time analytics over the whole training history.

   The division against Heute is by TIME HORIZON, not by metric: Heute is
   windowed (28-day balance, 8 weeks of tonnage, last 5 workouts, what is
   stalling now), this page has no window at all. Any future figure belongs
   here if it answers "about everything" and on Heute if it answers "about
   now".

   Composed for the desktop width -- it is not linked from the mobile tab bar
   (see _nav.html). Opening the URL on a phone renders it single-column.

   Every zone states its finding in words with the figures beneath, and every
   finding is gated on `statable`: below its sample threshold the chart still
   renders and the sentence does not. See analytics.py's threshold block. #}

{% block title %}Statistik · Gym Tracker{% endblock %}

{% block content %}
<div class="gym-wrap statistik">

    <header class="statistik__head">
        <h1>Statistik</h1>
        {% if totals.first_session %}
        <p class="label">Seit {{ totals.first_session.strftime('%d.%m.%Y') }} · {{ totals.days_training }} Tage</p>
        {% endif %}
    </header>

    {% if totals.sessions == 0 %}
    <div class="empty">
        <span class="label">Noch keine Daten</span>
        Sobald du dein erstes Workout abgeschlossen hast, entsteht hier deine Auswertung.
    </div>
    {% else %}

    {# zones are filled in by the following tasks #}

    {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS — 102 existing plus the analytics suite plus `test_statistik_renders`.

- [ ] **Step 7: Confirm the mobile bar still has three tabs**

```bash
cd personal_apps && grep -n "repeat(3, 1fr)" static/gym/gym.css
```

Expected: the `.tabbar` rule is unchanged and still says `repeat(3, 1fr)`.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/templates/gym/_nav.html personal_apps/templates/gym/statistik.html personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): add the desktop-only Statistik route and page shell"
```

---

## Task 8: Zones 1 and 2 — Das Werk and Fortschritt

**Files:**
- Modify: `personal_apps/templates/gym/statistik.html`
- Modify: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: `totals` and `progression` from Task 7.
- Produces: CSS classes `.statistik`, `.statistik__head`, `.werk`, `.werk__item`, `.prog-table`.

**Background:** The readout band follows the existing `.stat-grid` family — a divided band, **not** four separate tiles. Numerals are tabular and the largest thing in their container.

The progression table reuses the existing `.table` class (dense history, tabular figures) and must sit inside an `overflow-x: auto` wrapper so it never scrolls the page body.

Sorting is client-side and progressive: the table is fully readable without JavaScript, and the `<script>` only adds sorting on top. Sortable headers get `tabindex="0"` and respond to Enter/Space — they are `<th>`, not buttons, so keyboard support has to be explicit.

- [ ] **Step 1: Add the two zones to the template**

In `personal_apps/templates/gym/statistik.html`, replace the `{# zones are filled in by the following tasks #}` comment with:

```jinja
    <section class="statistik__zone">
        <div class="section-head"><h2 class="label">Das Werk</h2></div>
        <div class="panel werk">
            <div class="werk__item">
                <span class="label">Tonnage</span>
                <span class="num num--lg">{{ (totals.tonnage / 1000)|round(1) }}<span class="werk__unit">t</span></span>
            </div>
            <div class="werk__item">
                <span class="label">Sätze</span>
                <span class="num num--lg">{{ totals.sets }}</span>
            </div>
            <div class="werk__item">
                <span class="label">Wiederholungen</span>
                <span class="num num--lg">{{ totals.reps }}</span>
            </div>
            <div class="werk__item">
                <span class="label">Workouts</span>
                <span class="num num--lg">{{ totals.sessions }}</span>
            </div>
            <div class="werk__item">
                <span class="label">Größtes Workout</span>
                <span class="num num--lg">{{ totals.best_session.volume|round|int }}<span class="werk__unit">kg</span></span>
                <span class="label werk__meta">{{ totals.best_session.started_at.strftime('%d.%m.%Y') }}</span>
            </div>
        </div>
    </section>

    <section class="statistik__zone">
        <div class="section-head"><h2 class="label">Fortschritt</h2></div>
        {% if progression %}
        <p class="statistik__finding">
            {% set gaining = progression|selectattr('change_pct', 'gt', 0)|list %}
            {{ gaining|length }} von {{ progression|length }} Übungen sind seit Beginn stärker geworden.
            {% if gaining %}Am stärksten: <strong>{{ progression[0].name }}</strong> mit {{ '%+.1f'|format(progression[0].change_pct) }} %.{% endif %}
        </p>
        <div class="panel">
            <div class="statistik__table-wrap">
                <table class="table prog-table" id="prog-table">
                    <thead>
                        <tr>
                            <th data-sort="text">Übung</th>
                            <th class="num" data-sort="num">Workouts</th>
                            <th class="num" data-sort="num">Start e1RM</th>
                            <th class="num" data-sort="num">Aktuell</th>
                            <th class="num" data-sort="num">Δ</th>
                            <th class="num" data-sort="num">Bestes Gewicht</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for entry in progression %}
                        <tr>
                            <td>{{ entry.name }}</td>
                            <td class="num">{{ entry.sessions }}</td>
                            <td class="num">{{ entry.first_e1rm }}</td>
                            <td class="num">{{ entry.current_e1rm }}</td>
                            <td class="num prog-table__delta{{ ' is-up' if entry.change_pct > 0 else '' }}">{{ '%+.1f'|format(entry.change_pct) }} %</td>
                            <td class="num">{{ entry.best_weight }} kg</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% else %}
        <div class="panel"><div class="empty">Noch keine Übung mit zwei Workouts — Fortschritt braucht einen Vergleich.</div></div>
        {% endif %}
    </section>
```

- [ ] **Step 2: Add the CSS**

In `personal_apps/static/gym/gym.css`, append a new section at the end of the file, before the `REDUCED MOTION` block:

```css
/* ============================================================================
   STATISTIK  ·  all-time analytics (statistik.html)
   ----------------------------------------------------------------------------
   Desktop-composed: this page is not in the mobile tab bar, so it is free to
   use the width instead of stacking. It still renders single-column on a
   phone (the URL stays reachable), which is why nothing here depends on a
   minimum width to be legible -- only to be well arranged.
   ============================================================================ */

.statistik__head { margin-bottom: var(--sp-5); }
.statistik__zone { margin-bottom: var(--sp-6); }

/* the stated finding: the sentence the zone exists to make, above its evidence */
.statistik__finding {
  margin: 0 0 var(--sp-3);
  font-size: var(--t-name);
  color: var(--ink);
  text-wrap: pretty;
}
.statistik__finding--quiet { color: var(--dim); }

/* wide tables scroll in their own box; the page body never does */
.statistik__table-wrap { overflow-x: auto; }

/* Das Werk: one divided readout band, not five tiles. Same family as
   .stat-grid -- repeated identical cards are banned, and five of them would
   be the worst case of it on the page. */
.werk {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(11rem, 100%), 1fr));
  gap: 0;
}
/* Dividers drawn as a background layer rather than per-item borders: with
   auto-fit the band wraps, and a :first-child reset only clears the very
   first item -- the first item of every LATER row would keep a stray leading
   rule. Insetting the item's own background over the gap gives clean
   dividers at any column count. */
.werk__item {
  display: flex; flex-direction: column; gap: var(--sp-1);
  padding: var(--sp-4);
  box-shadow: inset 1px 0 0 var(--edge);
}
.werk__item:first-child { box-shadow: none; }
.werk__unit { margin-inline-start: 0.2em; font-size: var(--t-meta); color: var(--dim); }
.werk__meta { color: var(--unlit); }

.prog-table__delta { color: var(--dim); }
.prog-table__delta.is-up { color: var(--ink); }
/* sortable headers are <th>, so the affordance and the keyboard target are
   both explicit -- a bare th has neither */
.prog-table th[data-sort] { cursor: pointer; user-select: none; }
.prog-table th[data-sort]:focus-visible { outline: 2px solid var(--live); outline-offset: -2px; }
.prog-table th[aria-sort] { color: var(--ink); }
```

Verify every custom property used above already exists:

```bash
cd personal_apps && for t in --sp-1 --sp-3 --sp-4 --sp-5 --sp-6 --edge --ink --dim --unlit --live --t-name --t-meta; do grep -qE "(^|[^a-z-])$t:" static/gym/gym.css && echo "$t ok" || echo "$t MISSING"; done
```

Expected: every line reports `ok`. Several tokens share a line in the `:root`
block, so the pattern must not assume one definition per line. If one really is
missing, grep `gym.css` for the correct name and use that — never invent a
token.

- [ ] **Step 3: Add progressive sorting**

Append to `personal_apps/templates/gym/statistik.html`, after `{% endblock %}` of the content block:

```jinja
{% block scripts %}
<script>
// Progressive enhancement: the table is fully readable without this. Sorting
// is added on top, never required to see the data.
(function setupProgTableSort() {
    var table = document.getElementById('prog-table');
    if (!table) return;
    var tbody = table.tBodies[0];
    var headers = Array.prototype.slice.call(table.querySelectorAll('th[data-sort]'));

    function sortBy(index, kind, ascending) {
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) {
            var x = a.cells[index].textContent.trim();
            var y = b.cells[index].textContent.trim();
            if (kind === 'num') {
                // strip units, %, + and the thin spaces the numerals carry
                var nx = parseFloat(x.replace(/[^0-9.\-]/g, ''));
                var ny = parseFloat(y.replace(/[^0-9.\-]/g, ''));
                return ascending ? nx - ny : ny - nx;
            }
            return ascending ? x.localeCompare(y, 'de') : y.localeCompare(x, 'de');
        });
        rows.forEach(function (row) { tbody.appendChild(row); });
    }

    headers.forEach(function (th, i) {
        th.tabIndex = 0;
        function activate() {
            var ascending = th.getAttribute('aria-sort') !== 'ascending';
            headers.forEach(function (other) { other.removeAttribute('aria-sort'); });
            th.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
            sortBy(i, th.dataset.sort, ascending);
        }
        th.addEventListener('click', activate);
        th.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
        });
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 4: Verify**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS.

```bash
cd personal_apps && grep -c "<style" templates/gym/statistik.html
```

Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/statistik.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): render the Das Werk and Fortschritt zones"
```

---

## Task 9: Zone 3 — Wie du trainierst

**Files:**
- Modify: `personal_apps/templates/gym/statistik.html`
- Modify: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: `rep_range`, `fatigue`, `daypart`, `weekday`, `rest_gap` from Task 7; the `.row` component and `.hbar` primitive.
- Produces: CSS class `.finding-bar`.

**Background:** `analytics.py` returns English keys and weekday indexes; this
template owns every German word. Define the two maps once at the top of the
zone and reuse them:

```jinja
{% set DAYPART_LABELS = {'morning': 'morgens', 'evening': 'abends', 'other': 'sonst'} %}
{% set WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'] %}
```

**This is the zone the page exists for.** It must not be a grid of identical cards — that is banned. Two tiers: the rep-range finding is featured (it is the most characterising and has by far the strongest sample), the rest are divided `.row`s in one shared panel.

The `.row` component from the recent refactor: `__main` for the sentence, `__wide` for a full-width chart below it, `__trail` for the headline figure. `.row + .row` supplies the divider.

Each finding renders its sentence **only** when its `statable` flag is true; otherwise the sample size and *"noch zu wenig Daten"*.

- [ ] **Step 1: Add the zone**

In `personal_apps/templates/gym/statistik.html`, after the Fortschritt section:

```jinja
    <section class="statistik__zone">
        <div class="section-head"><h2 class="label">Wie du trainierst</h2></div>

        {# Featured: the rep-range finding. It has the largest sample of
           anything on the page (every set ever) and says the most about the
           lifter, so it leads. The rest are divided rows in one panel -- a
           grid of five identical finding-cards is exactly the pattern the
           design brief bans. #}
        <div class="panel">
            {% if rep_range.statable %}
            <p class="statistik__finding">
                {{ rep_range.dominant.share }} % deiner {{ rep_range.sample }} Sätze liegen bei
                {{ rep_range.dominant.label }} Wiederholungen.
                {% set outside = rep_range.buckets|rejectattr('sets')|map(attribute='label')|list %}
                {% if outside %}Bereiche ohne einen einzigen Satz: {{ outside|join(', ') }}.{% endif %}
            </p>
            {% else %}
            <p class="statistik__finding statistik__finding--quiet">
                Noch zu wenig Daten für eine Aussage — {{ rep_range.sample }} von {{ min_sets_for_rep_range }} Sätzen.
            </p>
            {% endif %}
            {% for bucket in rep_range.buckets %}
            <div class="hbar">
                <span class="hbar__name">{{ bucket.label }} Wdh.</span>
                <span class="hbar__track"><span class="hbar__fill" style="width:{{ bucket.share }}%"></span></span>
                <span class="hbar__val">{{ bucket.sets }}</span>
            </div>
            {% endfor %}
            {# analytics excludes 0-rep sets from the distribution on purpose --
               a failed attempt is not a rep range -- but it reports how many it
               dropped so the exclusion stays visible. Silently discarding this
               count here would put the silent-drop bug straight back, one layer
               up from where it was fixed. #}
            {% if rep_range.skipped %}
            <p class="label finding-bar__note">
                {{ rep_range.skipped }} {{ 'Satz' if rep_range.skipped == 1 else 'Sätze' }} ohne Wiederholung — nicht gewertet
            </p>
            {% endif %}
        </div>

        <div class="panel">
            {# time of day #}
            <div class="row row--top">
                <div class="row__main">
                    {% if daypart.statable %}
                    {% set parts = daypart.parts|selectattr('sessions')|sort(attribute='avg_volume', reverse=true)|list %}
                    <p class="statistik__finding">
                        Du bewegst {{ DAYPART_LABELS[parts[0].label] }} mehr Gewicht pro Workout als {{ DAYPART_LABELS[parts[-1].label] }}.
                    </p>
                    {% else %}
                    <p class="statistik__finding statistik__finding--quiet">Tageszeit: noch zu wenig Daten für eine Aussage.</p>
                    {% endif %}
                </div>
                <div class="row__wide">
                    {% set peak = (daypart.parts|map(attribute='avg_volume')|max) or 1 %}
                    {% for part in daypart.parts if part.sessions %}
                    <div class="hbar">
                        <span class="hbar__name">{{ DAYPART_LABELS[part.label] }}</span>
                        <span class="hbar__track"><span class="hbar__fill" style="width:{{ (part.avg_volume / peak * 100)|round(1) }}%"></span></span>
                        <span class="hbar__val">{{ part.avg_volume|round|int }} kg</span>
                    </div>
                    {% endfor %}
                    <p class="label finding-bar__note">{{ daypart.parts|selectattr('sessions')|map(attribute='sessions')|sum }} Workouts</p>
                </div>
            </div>

            {# within-session fatigue #}
            <div class="row row--top">
                <div class="row__main">
                    {% if fatigue.statable %}
                    <p class="statistik__finding">
                        Im letzten Satz einer Übung bewegst du im Schnitt {{ '%+.1f'|format(fatigue.weight_change_pct) }} % Gewicht
                        und schaffst {{ fatigue.first_reps }} → {{ fatigue.last_reps }} Wiederholungen.
                    </p>
                    {% else %}
                    <p class="statistik__finding statistik__finding--quiet">Ermüdung: noch zu wenig Daten für eine Aussage.</p>
                    {% endif %}
                </div>
                <span class="row__trail num num--md">{{ fatigue.sample }}</span>
            </div>

            {# weekday spread #}
            <div class="row row--top">
                <div class="row__main">
                    {% if weekday.statable %}
                    {% set top = weekday.days|sort(attribute='sessions', reverse=true)|first %}
                    <p class="statistik__finding">Dein häufigster Trainingstag ist {{ WEEKDAY_LABELS[top.weekday] }} ({{ top.sessions }} Workouts).</p>
                    {% else %}
                    <p class="statistik__finding statistik__finding--quiet">Wochentage: noch zu wenig Daten für eine Aussage.</p>
                    {% endif %}
                </div>
                <div class="row__wide">
                    {% set peak = (weekday.days|map(attribute='sessions')|max) or 1 %}
                    <div class="vbars">
                        {% for d in weekday.days %}
                        <div class="vbar" style="height:{{ (d.sessions / peak * 100)|round(1) }}%"></div>
                        {% endfor %}
                    </div>
                    <div class="vbars__axis">
                        {% for d in weekday.days %}<span>{{ WEEKDAY_LABELS[d.weekday] }}</span>{% endfor %}
                    </div>
                </div>
            </div>

            {# rest days #}
            <div class="row row--top">
                <div class="row__main">
                    {% if rest_gap.statable %}
                    {% set best = rest_gap.buckets|selectattr('sessions')|sort(attribute='avg_volume', reverse=true)|first %}
                    <p class="statistik__finding">Nach {{ best.label }} Tagen Pause bewegst du am meisten Gewicht.</p>
                    {% else %}
                    <p class="statistik__finding statistik__finding--quiet">Pausenlänge: noch zu wenig Daten für eine Aussage.</p>
                    {% endif %}
                </div>
                <div class="row__wide">
                    {% set peak = (rest_gap.buckets|map(attribute='avg_volume')|max) or 1 %}
                    {% for bucket in rest_gap.buckets %}
                    <div class="hbar">
                        <span class="hbar__name">{{ bucket.label }} Tage</span>
                        <span class="hbar__track"><span class="hbar__fill" style="width:{{ (bucket.avg_volume / peak * 100)|round(1) }}%"></span></span>
                        <span class="hbar__val">{{ bucket.sessions }}</span>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </section>
```

- [ ] **Step 2: Pass the threshold to the template**

The rep-range fallback copy names its threshold. In `personal_apps/features/gym/routes.py`, add to `gym_statistik`'s `render_template(...)` call:

```python
        min_sets_for_rep_range=analytics.MIN_SETS_FOR_REP_RANGE,
```

- [ ] **Step 3: Add the CSS**

Append to the `STATISTIK` section in `personal_apps/static/gym/gym.css`:

```css
.finding-bar__note { margin-top: var(--sp-2); color: var(--unlit); }
/* the findings panel holds charts inside rows, so its rows need room to
   breathe that a plain list row does not */
.statistik__zone .row__wide { margin-top: var(--sp-3); }
```

- [ ] **Step 4: Verify**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/statistik.html personal_apps/static/gym/gym.css personal_apps/features/gym/routes.py
git commit -m "feat(gym): render the behavioural findings zone"
```

---

## Task 10: Zones 4 and 5 — distribution and records

**Files:**
- Modify: `personal_apps/templates/gym/statistik.html`
- Modify: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: `effort` and `records` from Task 7.
- Produces: CSS classes `.statistik__cols`, `.record-row`.

**Background:** Two columns side by side on desktop, stacking below 900px via `auto-fit`. The record list reuses the `.row` component.

Records are the one place `--record` gold is correct — it already means "record" everywhere else in the app.

- [ ] **Step 1: Add both zones**

Append inside the `{% else %}` branch of `statistik.html`, after the behavioural zone:

```jinja
    <section class="statistik__zone">
        <div class="section-head"><h2 class="label">Wohin die Arbeit geht</h2></div>
        {% if effort.groups %}
        <p class="statistik__finding">
            {{ effort.groups[0].label }} trägt mit {{ effort.groups[0].share }} % den größten Anteil deiner Tonnage.
        </p>
        {% endif %}
        <div class="statistik__cols">
            <div class="panel">
                <div class="section-head"><h3 class="label">Nach Muskelgruppe</h3></div>
                {% for group in effort.groups %}
                <div class="hbar">
                    <span class="hbar__name">{{ group.label }}</span>
                    <span class="hbar__track"><span class="hbar__fill" style="width:{{ group.share }}%"></span></span>
                    <span class="hbar__val">{{ group.share }} %</span>
                </div>
                {% else %}
                <div class="empty">Noch keine Sätze protokolliert.</div>
                {% endfor %}
            </div>
            <div class="panel">
                <div class="section-head"><h3 class="label">Nach Übung</h3></div>
                {# |max raises on an empty sequence, and this list is empty on a
                   fresh database -- materialise first, then guard #}
                {% set shares = effort.exercises|map(attribute='share')|list %}
                {% set peak = (shares|max) if shares else 1 %}
                {% for exercise in effort.exercises %}
                <div class="hbar">
                    <span class="hbar__name">{{ exercise.label }}</span>
                    <span class="hbar__track"><span class="hbar__fill" style="width:{{ (exercise.share / peak * 100)|round(1) }}%"></span></span>
                    <span class="hbar__val">{{ exercise.share }} %</span>
                </div>
                {% else %}
                <div class="empty">Noch keine Sätze protokolliert.</div>
                {% endfor %}
            </div>
        </div>
    </section>

    <section class="statistik__zone">
        <div class="section-head"><h2 class="label">Rekorde</h2></div>
        <div class="panel">
            {% if records %}
            <p class="statistik__finding">{{ records|length }} persönliche Rekorde seit Beginn.</p>
            {% for record in records %}
            <div class="row">
                <div class="row__main">
                    <div class="name">{{ record.name }}</div>
                    <div class="label row__meta">
                        {{ record.started_at.strftime('%d.%m.%Y') }} ·
                        {{ 'Gewicht' if record.kind == 'weight' else 'e1RM' }} ·
                        vorher {{ record.previous }} kg
                    </div>
                </div>
                <span class="row__trail num num--md record-row__value">{{ record.value }} kg</span>
            </div>
            {% endfor %}
            {% else %}
            <div class="empty">Noch keine Rekorde — dafür braucht eine Übung mindestens zwei Workouts.</div>
            {% endif %}
        </div>
    </section>
```

- [ ] **Step 2: Add the CSS**

Append to the `STATISTIK` section:

```css
/* two columns where there is room, stacked where there is not -- no
   breakpoint needed, auto-fit does it */
.statistik__cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(22rem, 100%), 1fr));
  gap: var(--sp-4);
}

/* the one place gold is right on this page: it already means "record"
   everywhere else in the app */
.record-row__value { color: var(--record); }
```

- [ ] **Step 3: Verify**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/templates/gym/statistik.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): render the effort distribution and record timeline zones"
```

---

## Task 11: Sparklines in the progression table

**Files:**
- Modify: `personal_apps/templates/gym/statistik.html`
- Modify: `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: `entry.points` from `analytics.progression_ranking` (Task 2) — the chronological list of per-session best e1RM values.
- Produces: CSS class `.spark`.

**Background — a deliberate deviation from the spec.** Spec §6.5 says these use **Chart.js, lazy-loaded**. Building them instead as **inline SVG polylines, with no library at all**, because fourteen chart instances in fourteen table cells is the case Chart.js is worst at:

- it would pull a 208 KB third-party payload onto the page for decoration,
- canvas cannot resolve `var()`, so every sparkline would need its tokens resolved to `rgb()` in JavaScript first,
- fourteen canvases each carry their own render loop and resize observer,
- and a sparkline has no axes, no legend, no tooltip and no interaction — none of what a chart library is for.

An SVG polyline is a handful of Jinja, scales with the row, inherits `currentColor` so it needs no token resolution, and prints. **The result: this page loads no JavaScript charting library at all.** If that trade is unwanted, the fallback is the spec as written.

The line is decorative-adjacent but not decorative: it shows the *shape* of the progression that the first/current columns only bookend — steady climb versus a spike and plateau read completely differently at the same `Δ`.

- [ ] **Step 1: Add the sparkline column**

In `personal_apps/templates/gym/statistik.html`, add a header cell to the progression table, after `Δ`:

```jinja
                            <th>Verlauf</th>
```

Do **not** give it `data-sort` — a shape is not sortable.

Then add the matching body cell after the `Δ` cell:

```jinja
                            <td class="spark-cell">
                                {# Inline SVG, no chart library: a normalised polyline
                                   across the session-by-session e1RM values. Uses a
                                   0-100 viewBox with preserveAspectRatio="none" so the
                                   drawing needs no knowledge of its rendered size, and
                                   stroke inherits currentColor so it needs no token
                                   resolution. #}
                                {% set lo = entry.points|min %}
                                {% set hi = entry.points|max %}
                                {% set span = (hi - lo) if hi > lo else 1 %}
                                <svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none"
                                     role="img" aria-label="Verlauf {{ entry.name }}: {{ entry.first_e1rm }} bis {{ entry.current_e1rm }}">
                                    <polyline points="{% for p in entry.points %}{{ (loop.index0 / ((entry.points|length - 1) or 1) * 100)|round(2) }},{{ (22 - (p - lo) / span * 20)|round(2) }} {% endfor %}" />
                                </svg>
                            </td>
```

- [ ] **Step 2: Add the CSS**

Append to the `STATISTIK` section in `personal_apps/static/gym/gym.css`:

```css
/* Sparkline: shape only. The first/current columns already carry the numbers,
   so this exists to show whether the climb was steady or a spike followed by a
   plateau -- two very different stories behind one identical delta. */
.spark-cell { inline-size: 7rem; }
.spark {
  display: block; inline-size: 100%; block-size: 1.5rem;
  overflow: visible; color: var(--dim);
}
.spark polyline {
  fill: none; stroke: currentColor; stroke-width: 1.5;
  vector-effect: non-scaling-stroke;   /* preserveAspectRatio="none" would otherwise smear the stroke */
  stroke-linejoin: round; stroke-linecap: round;
}
tr:hover .spark { color: var(--ink); }
```

- [ ] **Step 3: Verify the shape renders and the stroke is even**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: PASS.

Then in the browser at 1280px, confirm on `/gym/statistik`:
- every progression row shows a line, including exercises whose points are all equal (a flat line, not an empty cell or a divide-by-zero)
- the stroke is uniform width, not stretched horizontally — this is what `vector-effect: non-scaling-stroke` prevents, and its absence is immediately visible
- `document.documentElement.scrollWidth` is unchanged at 100% and 200% text

- [ ] **Step 4: Commit**

```bash
git add personal_apps/templates/gym/statistik.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): add SVG sparklines to the progression table"
```

---

## Task 12: Document the split and verify the whole page

**Files:**
- Modify: `personal_apps/PRODUCT.md`

**Interfaces:**
- Consumes: everything.

**Background:** The windowed-vs-all-time rule is the thing a future contributor most needs and cannot infer from the code. Record it where the design decisions live.

- [ ] **Step 1: Document the rule**

In `personal_apps/PRODUCT.md`, directly after the paragraph in "What it is" that ends *"...legible enough to plan from in your head"*, add:

```markdown
### Heute vs Statistik

Two surfaces answer the same kinds of question at different **time horizons**,
and that is the whole rule for deciding where a new figure belongs:

- **Heute is windowed.** 28-day muscle balance, eight weeks of tonnage, the
  last five workouts, what is stalling now. It answers *what should I do
  today*.
- **Statistik has no window.** Cumulative totals, all-time progression per
  exercise, behavioural patterns, every record ever. It answers *what does my
  training say about me*.

Ask of any new statistic: is this about now, or about everything? The answer
picks the page — and the module, since `stats.py` serves the first and
`features/gym/analytics.py` the second. Statistik is desktop-only: it is
composed for the width and is not in the mobile tab bar, though its URL stays
reachable.
```

- [ ] **Step 2: Run the whole suite**

```bash
cd personal_apps && python -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 3: Confirm module purity and the single-query rule**

```bash
cd personal_apps && grep -cE "sqlalchemy|from models|import flask" features/gym/analytics.py
cd personal_apps && grep -c "load_performed()" features/gym/routes.py
```

Expected: `0` for the first. For the second, confirm by reading `gym_statistik` that it contains exactly one call.

- [ ] **Step 4: Browser verification**

Start the app and drive it with python-playwright (not the Browser MCP), reading the resulting PNGs:

```bash
cd personal_apps && python app.py
```

At **1280×900** and **390×844**, for `/gym/statistik`:

1. Page returns 200 and renders every zone.
2. `document.documentElement.scrollWidth` equals the viewport width at 100% text **and** at 200% (`html { font-size: 32px }`). The progression table must scroll inside `.statistik__table-wrap`, never the body.
3. No console errors.
4. The mobile tab bar shows exactly **three** tabs; the desktop top bar shows **four** including Statistik.
5. Sorting: click a `Δ` header, confirm the row order changes and `aria-sort` appears; press Enter on a focused header and confirm the same.
6. Every stated finding either has its sentence or the *"noch zu wenig Daten"* fallback — never a sentence with a nonsense number in it.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/PRODUCT.md
git commit -m "docs(gym): record the Heute-vs-Statistik time-horizon split"
```

---

## Verification Checklist

- [ ] `cd personal_apps && python -m pytest tests/ -v` — all pass
- [ ] `analytics.py` imports no SQLAlchemy, Flask or Jinja, and contains no German prose
- [ ] `stats.py` does not import from `analytics.py`
- [ ] `gym_statistik` calls `load_performed()` exactly once
- [ ] Deloads excluded from progression ranking and record timeline; included in totals, rep range, fatigue, daypart, weekday, rest gap, effort distribution
- [ ] Every finding goes silent below its threshold, and the chart still renders
- [ ] Mobile tab bar still `repeat(3, 1fr)` with three tabs
- [ ] No horizontal page scroll at 390px, at 100% and 200% text
- [ ] No new CSS custom properties; no fourth semantic hue
- [ ] No second `<style>` tag in `statistik.html`
- [ ] No emoji

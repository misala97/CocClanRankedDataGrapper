# Task Schedule Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record which schedule each background task is actually on, so the Monitor and the sitewide nav strip stop reporting correctly-idle tasks as down.

**Architecture:** One shared `TASK_SCHEDULE` dict becomes the only place intervals are written. Each `UptimeTracker` row records the interval in force for the next run. `monitor_stats.infer_cadence()` is deleted; both reporting surfaces read the persisted value through one helper.

**Tech Stack:** Flask, SQLAlchemy, Alembic (Flask-Migrate), APScheduler, MySQL, pytest.

Spec: `docs/superpowers/specs/2026-08-05-task-schedule-awareness-design.md`

## Global Constraints

- All work happens on branch `dev_coc`. Only `main` deploys.
- Run everything from `coc_stats/` — that directory is the pytest rootdir (`coc_stats/conftest.py`).
- `features/admin/monitor_stats.py` is a **pure module**: no Flask, no DB session, no template concerns. It takes ORM-shaped rows and returns plain dicts.
- The four health states are `up` / `idle` / `warn` / `down`, plus `absent` for a task with no runs at all. German UI labels: `Läuft` / `Ruht` / `Verzögert` / `Still` / `Kein Lauf`.
- Existing thresholds keep their names and values: `WARN_FACTOR = 1.5`, `DOWN_FACTOR = 2.5`.
- Never invent an interval. Paths that do not reach a reschedule decision write `NULL`.
- The migration must not delete rows.
- Local verification needs the dev server: from `coc_stats/`, `python -c "from app import app; app.run(host='127.0.0.1', port=5000, use_reloader=False)"`. Admin routes need the session cookie minted in `scratchpad/mint_cookie.py`.

---

### Task 1: The schedule registry and the interval decisions

Every background-task interval, and the rules that choose between them, in one
pure module. This is also where the `raid_weekend` defect gets fixed — not by
patching in the missing branch, but by making the decision a total function and
testing that no state can fall through it.

**Files:**
- Create: `coc_stats/tasks/schedule.py`
- Create: `coc_stats/tests/test_task_schedule.py`

**Interfaces:**
- Produces: `TASK_SCHEDULE`, `active_minutes(key) -> int`, `idle_minutes(key) -> int | None`, `is_dynamic(key) -> bool`, `war_interval(state) -> int`, `cwl_interval(state, season) -> int`, `raid_interval(state) -> int`

- [ ] **Step 1: Write the failing tests**

Create `coc_stats/tests/test_task_schedule.py`:

```python
# -*- coding: utf-8 -*-
"""The interval registry and the rules that pick between intervals.

run_scheduler.py, the three dynamic tasks and features/admin/monitor_stats.py
all read from here. Duplicating the numbers is what this module exists to stop.

The *_interval functions are total on purpose. raid_weekend shipped a bug where
state == 'ended' matched neither reschedule branch and the job silently kept its
3-minute war interval for two days; the exhaustiveness tests below are what
catch that class of defect.
"""

import pytest

from tasks.schedule import (
    TASK_SCHEDULE,
    active_minutes,
    cwl_interval,
    idle_minutes,
    is_dynamic,
    raid_interval,
    war_interval,
)


def test_every_task_declares_an_active_interval():
    assert all(v['active'] for v in TASK_SCHEDULE.values())


def test_the_three_dynamic_tasks_declare_an_idle_interval():
    dynamic = {k for k, v in TASK_SCHEDULE.items() if v['idle'] is not None}
    assert dynamic == {
        'task_update_clan_war',
        'task_update_cwl',
        'task_update_raid_weekend',
    }


def test_fixed_tasks_have_no_idle_mode():
    """A task with idle=None can never resolve to the 'Ruht' state."""
    for key in ('task_update_battle_logs', 'task_update_ranked_weeks',
                'task_update_clan_members'):
        assert idle_minutes(key) is None
        assert is_dynamic(key) is False


def test_idle_is_always_slower_than_active():
    for key, v in TASK_SCHEDULE.items():
        if v['idle'] is not None:
            assert v['idle'] > v['active'], key


def test_lookups_reject_unknown_tasks():
    with pytest.raises(KeyError):
        active_minutes('task_update_nonexistent')


# ── the decisions must be total ──────────────────────────────────────────────

@pytest.mark.parametrize('state', [
    'ongoing', 'ended', 'notStarted', 'unknown', '', None,
])
def test_every_raid_state_maps_to_a_real_interval(state):
    """Regression test for the two-day 3-minute poll: 'ended' matched no branch,
    so the job kept whatever interval it happened to hold."""
    assert raid_interval(state) in (3, 60)


def test_only_an_ongoing_raid_weekend_polls_fast():
    assert raid_interval('ongoing') == 3
    assert raid_interval('ended') == 60
    assert raid_interval('notStarted') == 60


@pytest.mark.parametrize('state', [
    'inWar', 'preparation', 'warEnded', 'notInWar', 'unknown', '', None,
])
def test_every_war_state_maps_to_a_real_interval(state):
    assert war_interval(state) in (3, 60)


def test_only_a_live_war_polls_fast():
    assert war_interval('inWar') == 3
    assert war_interval('preparation') == 3
    assert war_interval('warEnded') == 60
    assert war_interval('notInWar') == 60


@pytest.mark.parametrize('state,season', [
    ('inWar', '2026-08'), ('preparation', '2026-08'), ('notInWar', '2026-08'),
    ('inWar', ''), ('inWar', None), (None, None), ('', ''),
])
def test_every_cwl_input_maps_to_a_real_interval(state, season):
    assert cwl_interval(state, season) in (3, 60)


def test_cwl_polls_fast_only_with_a_live_season():
    assert cwl_interval('inWar', '2026-08') == 3
    assert cwl_interval('notInWar', '2026-08') == 60
    assert cwl_interval('inWar', '') == 60
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd coc_stats && python -m pytest tests/test_task_schedule.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tasks.schedule'`

- [ ] **Step 3: Create the module**

Create `coc_stats/tasks/schedule.py`:

```python
"""The only place background-task intervals are written, and the rules that
choose between them.

Three of the six tasks retune themselves at runtime — clan_war, cwl and
raid_weekend drop from a 3-minute cadence to hourly when there is nothing to
poll for. That interval used to be written in run_scheduler.py and again inside
each task's reschedule call, with the Monitor reverse-engineering it from
timestamps a third time. Three copies of one number is how they drift.

The *_interval functions are total: every possible state maps to an interval.
raid_weekend previously decided this with an if/elif covering 'ongoing' and
"neither ongoing nor ended", leaving state == 'ended' to match neither branch
and the job to keep whatever interval it held. It polled every 3 minutes for
two days.
"""

TASK_SCHEDULE = {
    'task_update_battle_logs':  {'active': 5,  'idle': None},
    'task_update_ranked_weeks': {'active': 10, 'idle': None},
    'task_update_clan_members': {'active': 5,  'idle': None},
    'task_update_clan_war':     {'active': 3,  'idle': 60},
    'task_update_cwl':          {'active': 3,  'idle': 60},
    'task_update_raid_weekend': {'active': 3,  'idle': 60},
}


def active_minutes(key):
    """Interval while the task has work to poll for."""
    return TASK_SCHEDULE[key]['active']


def idle_minutes(key):
    """Interval while the task is dormant, or None if it has no dormant mode."""
    return TASK_SCHEDULE[key]['idle']


def is_dynamic(key):
    """True when the task switches interval at runtime."""
    return TASK_SCHEDULE.get(key, {}).get('idle') is not None


def _pick(key, active):
    return active_minutes(key) if active else idle_minutes(key)


def war_interval(state):
    """Clan war: only a live war is worth polling every few minutes.

    'warEnded' is still polled so the final result lands, but hourly is plenty.
    """
    return _pick('task_update_clan_war',
                 state not in ('notInWar', 'warEnded', None, ''))


def cwl_interval(state, season):
    """CWL: needs both a season and a state that is not 'notInWar'."""
    return _pick('task_update_cwl',
                 bool(season) and state not in ('notInWar', None, ''))


def raid_interval(state):
    """Raid weekend: only an ongoing weekend polls fast.

    'ended' is polled hourly so a late-arriving attack log still gets picked up.
    """
    return _pick('task_update_raid_weekend', state == 'ongoing')
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd coc_stats && python -m pytest tests/test_task_schedule.py -q`
Expected: `26 passed`

- [ ] **Step 5: Teeth-check the exhaustiveness test**

Temporarily reintroduce the original defect — replace `raid_interval` with:

```python
def raid_interval(state):
    if state not in ('ongoing', 'ended'):
        return idle_minutes('task_update_raid_weekend')
    elif state == 'ongoing':
        return active_minutes('task_update_raid_weekend')
```

Run: `cd coc_stats && python -m pytest tests/test_task_schedule.py -q`
Expected: FAIL on `test_every_raid_state_maps_to_a_real_interval[ended]` — the function returns `None`.

Restore the correct version and re-run. Expected: `26 passed`. This is the exact defect that ran in production for two days; the suite now catches it.

- [ ] **Step 6: Commit**

```bash
git add coc_stats/tasks/schedule.py coc_stats/tests/test_task_schedule.py
git commit -m "feat(tasks): one registry for task intervals, with total decision rules

The numbers lived in run_scheduler.py and again in each dynamic task's
reschedule call, and the Monitor inferred them from timestamps a third time.
Three copies of one number drift.

The *_interval functions are total by design. raid_weekend decided this with an
if/elif covering 'ongoing' and 'neither ongoing nor ended', so state == 'ended'
matched neither and the job kept its 3-minute war interval for two days - 480
runs in 24 hours against ~24 expected. A parametrised exhaustiveness test now
fails if any state maps to nothing."
```

---

### Task 2: Persist the interval on every run

**Files:**
- Modify: `coc_stats/models.py` (UptimeTracker)
- Modify: `coc_stats/services/db.py` (`db_finalize_uptime`)
- Create: `coc_stats/migrations/versions/b4e7d2a91f56_add_interval_minutes_to_uptime.py`

**Interfaces:**
- Consumes: `tasks.schedule.TASK_SCHEDULE` (Task 1)
- Produces: `UptimeTracker.interval_minutes: int | None`; `db_finalize_uptime(..., interval_minutes=None)`

- [ ] **Step 1: Add the column to the model**

In `coc_stats/models.py`, inside `class UptimeTracker`, after the `summary` column:

```python
    # The interval, in minutes, governing the NEXT run — recorded at write time
    # because three tasks retune themselves and nothing else preserves which
    # schedule was in force. NULL where the task returned before reaching a
    # reschedule decision (e.g. an API failure): readers carry the last known
    # value forward rather than guessing.
    interval_minutes = db.Column(db.Integer, nullable=True)
```

- [ ] **Step 2: Accept it in the writer**

In `coc_stats/services/db.py`, replace the `db_finalize_uptime` signature and body:

```python
def db_finalize_uptime(func_name: str, t0: float, status: str = 'success', error_message: str = None,
                       summary: str = None, logger=None, interval_minutes: int = None):
    duration = round(time.time() - t0, 2)
    if logger:
        logger.info(f"Done in {duration}s | {summary or status}")
    db.session.add(UptimeTracker(function=func_name, duration=duration, status=status,
                                 error_message=error_message, summary=summary,
                                 interval_minutes=interval_minutes))
    db.session.commit()
```

- [ ] **Step 3: Write the migration**

Create `coc_stats/migrations/versions/b4e7d2a91f56_add_interval_minutes_to_uptime.py`:

```python
"""add interval_minutes to uptime_tracker

Revision ID: b4e7d2a91f56
Revises: a8e2f4c6b9d1
Create Date: 2026-08-05 03:00:00.000000

Backfills historical rows so no NULL-fallback path survives in the reader.
Deliberately deletes nothing: this migration runs automatically on every
deploy, and the table holds the 2026-07-31 API outage the Monitor redesign
was built around.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b4e7d2a91f56'
down_revision = 'a8e2f4c6b9d1'
branch_labels = None
depends_on = None

FIXED = {
    'task_update_battle_logs': 5,
    'task_update_clan_members': 5,
    'task_update_ranked_weeks': 10,
}
DYNAMIC = ('task_update_clan_war', 'task_update_cwl', 'task_update_raid_weekend')


def upgrade():
    op.add_column('uptime_tracker', sa.Column('interval_minutes', sa.Integer(), nullable=True))

    conn = op.get_bind()

    # Fixed-interval tasks never varied, so their value is exact.
    for fn, minutes in FIXED.items():
        conn.execute(
            sa.text("UPDATE uptime_tracker SET interval_minutes = :m WHERE function = :fn"),
            {"m": minutes, "fn": fn},
        )

    # Dynamic tasks: a 'skipped' row is one the task wrote after downshifting to
    # hourly, a 'success' row is one it wrote on the active schedule. Verified
    # against live rows. 'error' rows are left NULL — those are written before
    # the task inspects game state, so it genuinely did not know its schedule.
    conn.execute(
        sa.text(
            "UPDATE uptime_tracker SET interval_minutes = 60 "
            "WHERE function IN :fns AND status = 'skipped'"
        ).bindparams(sa.bindparam("fns", expanding=True)),
        {"fns": list(DYNAMIC)},
    )
    conn.execute(
        sa.text(
            "UPDATE uptime_tracker SET interval_minutes = 3 "
            "WHERE function IN :fns AND status = 'success'"
        ).bindparams(sa.bindparam("fns", expanding=True)),
        {"fns": list(DYNAMIC)},
    )


def downgrade():
    op.drop_column('uptime_tracker', 'interval_minutes')
```

- [ ] **Step 4: Apply it locally and verify the backfill**

Run:
```bash
cd coc_stats && python -m flask db upgrade
```
Expected: alembic reports running `b4e7d2a91f56`.

Then:
```bash
cd coc_stats && python -c "
from app import app
from models import UptimeTracker
from extensions import db
from sqlalchemy import func
with app.app_context():
    q = db.session.query(UptimeTracker.function, UptimeTracker.interval_minutes,
                         func.count(UptimeTracker.id)).group_by(
                             UptimeTracker.function, UptimeTracker.interval_minutes)
    for fn, iv, n in q.all():
        print(f'{fn:26} interval={str(iv):>5}  rows={n}')
"
```
Expected: fixed tasks show a single interval each (5/5/10); the three dynamic tasks show rows at 3 and 60, plus a small number at `None` for error rows.

- [ ] **Step 5: Verify the downgrade is clean**

Run:
```bash
cd coc_stats && python -m flask db downgrade && python -m flask db upgrade
```
Expected: both succeed; the column is dropped and re-added with the backfill intact.

- [ ] **Step 6: Commit**

```bash
git add coc_stats/models.py coc_stats/services/db.py coc_stats/migrations/versions/b4e7d2a91f56_add_interval_minutes_to_uptime.py
git commit -m "feat(admin): record which schedule each task run was on

UptimeTracker stored when a run happened but not the interval governing it, so
both reporting surfaces reverse-engineered it from timestamps and both got it
wrong for the three tasks that retune themselves.

Backfilled rather than reset: the table holds 52 days including the 2026-07-31
outage. Error rows stay NULL because the task returns before it inspects game
state, so it genuinely does not know its schedule at that point."
```

---

### Task 3: Wire the tasks and the scheduler to the registry

One decision per run, used twice: it sets the schedule and it gets recorded.
This is also where the `raid_weekend` fix reaches running code — Task 1 made the
rule correct and tested, this makes the task obey it.

**Files:**
- Modify: `coc_stats/run_scheduler.py:39-44`
- Modify: `coc_stats/tasks/clan_war.py`, `cwl.py`, `raid_weekend.py`
- Modify: `coc_stats/tasks/battle_logs.py`, `clan_members.py`, `ranked_weeks.py`

**Interfaces:**
- Consumes: `tasks.schedule` (Task 1), `db_finalize_uptime(..., interval_minutes=)` (Task 2)

- [ ] **Step 1: Register jobs from the registry**

In `coc_stats/run_scheduler.py`, add near the other `from tasks...` imports:

```python
from tasks.schedule import active_minutes
```

Replace the six `add_job` lines (39-44) with:

```python
    # Intervals come from tasks/schedule.py — the dynamic three retune themselves
    # from the same registry, so the number is written in exactly one place.
    scheduler.add_job(func=task_update_clan_members, trigger="interval",
                      minutes=active_minutes('task_update_clan_members'), max_instances=1)
    scheduler.add_job(func=task_update_ranked_weeks, trigger="interval",
                      minutes=active_minutes('task_update_ranked_weeks'), max_instances=1)
    scheduler.add_job(func=task_update_battle_logs, trigger="interval",
                      minutes=active_minutes('task_update_battle_logs'), max_instances=1)
    scheduler.add_job(func=task_update_raid_weekend, trigger="interval",
                      minutes=active_minutes('task_update_raid_weekend'),
                      max_instances=1, id='raid_weekend_update')
    scheduler.add_job(func=task_update_clan_war, trigger="interval",
                      minutes=active_minutes('task_update_clan_war'),
                      max_instances=1, id='clan_war_update')
    scheduler.add_job(func=task_update_cwl, trigger="interval",
                      minutes=active_minutes('task_update_cwl'),
                      max_instances=1, id='cwl_update')
```

- [ ] **Step 2: Fixed-interval tasks report their constant**

In each of `tasks/battle_logs.py`, `tasks/clan_members.py`, `tasks/ranked_weeks.py`, add:

```python
from tasks.schedule import active_minutes
```

and add `interval_minutes=active_minutes(<task_func>.__name__)` to **every**
`db_finalize_uptime(...)` call in that file. Example from `battle_logs.py`:

```python
        db_finalize_uptime(task_update_battle_logs.__name__, t0, 'error', str(e),
                           logger=battle_logs_logger,
                           interval_minutes=active_minutes(task_update_battle_logs.__name__))
```

These tasks never change interval, so every row — error rows included — carries
the true value.

- [ ] **Step 3: `clan_war` decides once, then applies and records it**

In `tasks/clan_war.py`, add:

```python
from tasks.schedule import war_interval
```

Immediately after `state` is read (line 42), compute the interval once and apply it:

```python
        interval = war_interval(state)
        _reschedule(minutes=interval)
```

Then delete the three scattered `_reschedule(hours=1)` / `_reschedule(minutes=3)`
calls at lines 50, 55 and 65, and pass `interval_minutes=interval` on each
`db_finalize_uptime` that follows the decision:

```python
            db_finalize_uptime(task_update_clan_war.__name__, t0, 'skipped',
                               summary='notInWar', logger=clan_war_logger,
                               interval_minutes=interval)
```

Apply the same to the `already finalized` call and the final call at the end of a
processed war.

**Leave the early `except` at line 45 alone** — it returns before `state` exists,
so no decision was made and the row must stay NULL.

- [ ] **Step 4: Same shape for `cwl` and `raid_weekend`**

`tasks/cwl.py` — add `from tasks.schedule import cwl_interval`. The season string
is only known after the group fetch, so the 404 branch decides on its own:

```python
# the 404 "not in CWL" branch
                interval = cwl_interval(None, None)
                if extensions.scheduler:
                    extensions.scheduler.reschedule_job('cwl_update', trigger='interval',
                                                        minutes=interval)
                db_finalize_uptime(task_update_cwl.__name__, t0, 'skipped', 'notFound',
                                   logger=cwl_logger, interval_minutes=interval)
```

and after `state` and `season_str` are both known, replace the `if/else` pair of
reschedule calls with one decision:

```python
        interval = cwl_interval(state, season_str)
        if extensions.scheduler:
            extensions.scheduler.reschedule_job('cwl_update', trigger='interval',
                                                minutes=interval)
```

passing `interval_minutes=interval` on the `notInWar` skip and on the final
processed-season call. Leave the non-404 fetch failure NULL.

`tasks/raid_weekend.py` — add `from tasks.schedule import raid_interval`. Replace
the whole `if/elif` block at lines 58-66 with:

```python
        interval = raid_interval(raid_weekend.state)
        if extensions.scheduler:
            extensions.scheduler.reschedule_job('raid_weekend_update',
                                                trigger='interval', minutes=interval)
        if raid_weekend.state not in ('ongoing', 'ended'):
            raid_weekend_logger.info("No active raid weekend — skipping.")
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'skipped',
                               summary='not ongoing', logger=raid_weekend_logger,
                               interval_minutes=interval)
            return
```

`'ended'` now falls through to the processing below on an hourly interval, which
is the fix. Pass `interval_minutes=interval` on the final call too, and leave the
two early API-error calls at lines 40 and 53 NULL.

- [ ] **Step 5: Verify every task imports**

Run:
```bash
cd coc_stats && python -c "
import run_scheduler
import tasks.battle_logs, tasks.clan_members, tasks.ranked_weeks
import tasks.clan_war, tasks.cwl, tasks.raid_weekend
print('scheduler + all six tasks import ok')"
```
Expected: `scheduler + all six tasks import ok`

- [ ] **Step 6: Confirm no reschedule call bypasses the registry**

Run:
```bash
cd coc_stats && grep -n "hours=1\|minutes=3\|minutes=5\|minutes=10" tasks/*.py run_scheduler.py
```
Expected: **no matches.** Every interval now comes from `tasks/schedule.py`. A
literal here means a fourth copy of a number that already has one home.

- [ ] **Step 7: Confirm the NULL paths are deliberate**

Run:
```bash
cd coc_stats && grep -c "db_finalize_uptime(" tasks/*.py && echo "---" && grep -c "interval_minutes" tasks/*.py
```
Expected: for `battle_logs.py`, `clan_members.py` and `ranked_weeks.py` the two
counts match. For `clan_war.py`, `cwl.py` and `raid_weekend.py` the
`interval_minutes` count is lower — by exactly the number of early API-error
paths (1, 1 and 2 respectively), which are the rows that must stay NULL.

- [ ] **Step 8: Commit**

```bash
git add coc_stats/run_scheduler.py coc_stats/tasks/
git commit -m "fix(tasks): schedule and record from one decision per run

Each dynamic task now computes its interval once from tasks/schedule.py, applies
it, and records it on the uptime row. run_scheduler registers from the same
registry, so no interval literal survives anywhere in tasks/ or the scheduler.

This is where the raid_weekend fix reaches running code: state == 'ended' now
resolves through raid_interval() to the hourly schedule instead of falling
through an if/elif that handled every other case.

Paths that return before the task learns its game state - the early API failures
- record NULL rather than guess. Readers carry the last known schedule forward."
```

---

### Task 4: Derive health from the persisted interval

**Files:**
- Modify: `coc_stats/features/admin/monitor_stats.py`
- Modify: `coc_stats/tests/test_monitor_stats.py`

**Interfaces:**
- Consumes: `tasks.schedule` (Task 1), `UptimeTracker.interval_minutes` (Task 1)
- Produces: `resolve_interval(runs, key) -> (int, bool)` returning `(minutes, assumed)`; `task_stats()` gains `mode` (`'active'` | `'idle'`) and `idle_reason` (str | None); `health` gains `'idle'`; `infer_cadence` is removed

- [ ] **Step 1: Write the failing tests**

Append to `coc_stats/tests/test_monitor_stats.py`:

```python
# ── schedule awareness ───────────────────────────────────────────────────────

def sched_row(fn, minutes, interval, status='success', summary=''):
    r = row(fn, minutes, status=status, summary=summary)
    r.interval_minutes = interval
    return r


def test_resolve_interval_reads_the_persisted_value():
    rows = [sched_row('task_update_clan_war', i * 60, 60, 'skipped', 'notInWar')
            for i in range(4)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 60
    assert assumed is False


def test_null_intervals_carry_the_last_known_schedule_forward():
    """An API failure writes NULL. A burst of them must not lose the schedule."""
    rows = [sched_row('task_update_clan_war', 0, 60, 'skipped', 'notInWar')]
    rows += [sched_row('task_update_clan_war', 60 + i, None, 'error') for i in range(3)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 60
    assert assumed is False


def test_all_null_falls_back_to_the_declared_active_interval():
    rows = [sched_row('task_update_clan_war', i, None, 'error') for i in range(3)]
    minutes, assumed = resolve_interval(runs_of(rows, 'task_update_clan_war'),
                                        'task_update_clan_war')
    assert minutes == 3
    assert assumed is True


def test_an_idle_task_is_not_reported_as_down():
    """The bug this whole change exists to fix: clan_war polling correctly on its
    hourly idle schedule was reported Still, because cadence was inferred from
    war-time runs days earlier."""
    rows = [sched_row('task_update_clan_war', i * 60, 60, 'skipped', 'notInWar')
            for i in range(5)]
    now = T0 + dt.timedelta(minutes=4 * 60 + 30)
    s = task_stats('task_update_clan_war', runs_of(rows, 'task_update_clan_war'), now)
    assert s['health'] == 'idle'
    assert s['mode'] == 'idle'
    assert s['cadence'] == 60


def test_an_idle_task_that_stops_polling_still_goes_down():
    """Scaling the threshold to the schedule must not mean never alerting."""
    rows = [sched_row('task_update_clan_war', i * 60, 60, 'skipped', 'notInWar')
            for i in range(5)]
    runs = runs_of(rows, 'task_update_clan_war')
    base = T0 + dt.timedelta(minutes=4 * 60)
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=80))['health'] == 'idle'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=100))['health'] == 'warn'
    assert task_stats('task_update_clan_war', runs, base + dt.timedelta(minutes=200))['health'] == 'down'


def test_a_fixed_task_can_never_be_idle():
    rows = [sched_row('task_update_battle_logs', i * 5, 5) for i in range(6)]
    s = task_stats('task_update_battle_logs',
                   runs_of(rows, 'task_update_battle_logs'),
                   T0 + dt.timedelta(minutes=27))
    assert s['mode'] == 'active'
    assert s['health'] == 'up'


def test_idle_reason_comes_from_the_last_summary():
    rows = [sched_row('task_update_raid_weekend', i * 60, 60, 'skipped', 'not ongoing')
            for i in range(3)]
    s = task_stats('task_update_raid_weekend',
                   runs_of(rows, 'task_update_raid_weekend'),
                   T0 + dt.timedelta(minutes=130))
    assert s['idle_reason'] == 'not ongoing'


def test_idle_windows_group_contiguous_dormant_stretches():
    """Task 6 shades these behind the lane; a wrong grouping paints the wrong
    span of history as dormant."""
    rows  = [sched_row('task_update_clan_war', i * 3, 3) for i in range(5)]
    rows += [sched_row('task_update_clan_war', 60 + i * 60, 60, 'skipped', 'notInWar')
             for i in range(4)]
    rows += [sched_row('task_update_clan_war', 400 + i * 3, 3) for i in range(3)]
    windows = idle_windows(runs_of(rows, 'task_update_clan_war'), 'task_update_clan_war')
    assert len(windows) == 1
    assert windows[0]['start'] == T0 + dt.timedelta(minutes=60)


def test_a_fixed_task_has_no_idle_windows():
    rows = [sched_row('task_update_battle_logs', i * 5, 5) for i in range(6)]
    assert idle_windows(runs_of(rows, 'task_update_battle_logs'),
                        'task_update_battle_logs') == []


def test_hourly_polling_is_not_counted_as_a_gap():
    """find_gaps compared hourly idle polls against a 3-minute cadence."""
    rows = [sched_row('task_update_clan_war', i * 60, 60, 'skipped', 'notInWar')
            for i in range(6)]
    s = task_stats('task_update_clan_war', runs_of(rows, 'task_update_clan_war'),
                   T0 + dt.timedelta(minutes=5 * 60 + 10))
    assert s['gaps'] == []
```

Add `resolve_interval` and `idle_windows` to the import block at the top of the test file, and remove `infer_cadence` from it.

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd coc_stats && python -m pytest tests/test_monitor_stats.py -q -k "schedule or idle or interval or hourly or fixed_task"`
Expected: FAIL — `ImportError: cannot import name 'resolve_interval'`

- [ ] **Step 3: Implement the derivation**

In `features/admin/monitor_stats.py`, add the import:

```python
from tasks.schedule import TASK_SCHEDULE, active_minutes, idle_minutes
```

Delete `infer_cadence()` entirely and add:

```python
def resolve_interval(runs, key):
    """The interval governing this task, in minutes, and whether it is assumed.

    Reads the most recent NON-NULL interval_minutes rather than strictly the
    last row's: an API failure writes NULL because it returns before the task
    inspects game state, and a burst of those must not lose the schedule.
    """
    for r in reversed(runs):
        if r.get('interval_minutes') is not None:
            return r['interval_minutes'], False
    return active_minutes(key) if key in TASK_SCHEDULE else None, True
```

In `normalize_runs()`, carry the column through:

```python
            'interval_minutes': getattr(r, 'interval_minutes', None),
```

In `task_stats()`, replace the `cadence = infer_cadence(runs)` line and the health block:

```python
    cadence, cadence_assumed = resolve_interval(runs, key)
    mode = 'idle' if cadence is not None and cadence == idle_minutes(key) else 'active'

    last = runs[-1] if runs else None
    minutes_since, health = None, 'absent'
    if last:
        minutes_since = round((now - last['time']).total_seconds() / 60, 1)
        if cadence:
            if minutes_since > cadence * DOWN_FACTOR:
                health = 'down'
            elif minutes_since > cadence * WARN_FACTOR:
                health = 'warn'
            else:
                # Dormant by design is its own state — not health, not warning.
                health = 'idle' if mode == 'idle' else 'up'
        elif minutes_since < NO_CADENCE_WARN:
            health = 'up'
        elif minutes_since < NO_CADENCE_DOWN:
            health = 'warn'
        else:
            health = 'down'
```

Add the window grouper next to `find_gaps`, so the lane strip in Task 6 has something to shade:

```python
def idle_windows(runs, key):
    """Contiguous stretches where the task was on its dormant schedule.

    Drawn as a faint band behind the lane, which turns the strip into a history
    of when the clan was actually at war rather than just an uptime chart.
    """
    idle = idle_minutes(key)
    if idle is None:
        return []
    out, start, prev = [], None, None
    for r in runs:
        on_idle = r.get('interval_minutes') == idle
        if on_idle and start is None:
            start = r['time']
        elif not on_idle and start is not None:
            out.append({'start': start, 'end': prev})
            start = None
        prev = r['time']
    if start is not None:
        out.append({'start': start, 'end': prev})
    return out
```

Add to the returned dict:

```python
        mode=mode,
        cadence_assumed=cadence_assumed,
        idle_reason=(last['summary'] or None) if last and mode == 'idle' else None,
        idle_windows=idle_windows(runs, key),
```

`find_gaps(runs, cadence, now)` needs no change — it now receives the true interval, so hourly polls stop registering as gaps.

- [ ] **Step 4: Run the whole monitor suite**

Run: `cd coc_stats && python -m pytest tests/test_monitor_stats.py -q`
Expected: all pass. Some pre-existing tests reference `infer_cadence` and must be updated to set `interval_minutes` on their fixtures instead — update them, do not delete them.

- [ ] **Step 5: Teeth-check the idle guard**

Temporarily change `health = 'idle' if mode == 'idle' else 'up'` to `health = 'up'`, then run:

Run: `cd coc_stats && python -m pytest tests/test_monitor_stats.py -q`
Expected: FAIL — at minimum `test_an_idle_task_is_not_reported_as_down`.

Restore the line and re-run. Expected: all pass. A guard whose tests pass while it is disabled is not a guard.

- [ ] **Step 6: Commit**

```bash
git add coc_stats/features/admin/monitor_stats.py coc_stats/tests/test_monitor_stats.py
git commit -m "feat(admin): derive task health from the recorded interval

infer_cadence() took the median gap between non-skipped runs, so an idle task
was judged against the 3-minute cadence of a war that ended days ago and
reported Still. The interval is now a fact on the row.

Idle is its own state: dormant is neither health nor warning. An idle task that
genuinely stops polling still reaches Still - at 150 minutes rather than 7.5."
```

---

### Task 5: Nav strip reads the same helper

**Files:**
- Modify: `coc_stats/app.py:88-112` (`_nav_task_status`)

**Interfaces:**
- Consumes: `monitor_stats.resolve_interval`, `task_stats` health vocabulary (Task 4)

- [ ] **Step 1: Replace the hand-rolled thresholds**

In `coc_stats/app.py`, rewrite `_nav_task_status()`:

```python
def _nav_task_status():
    """Per-task freshness for the sitewide status strip.

    Reads the same recorded interval the Monitor does. It used to apply its own
    fixed thresholds (<15 min good, <60 warn), which meant a correctly-idle
    clan_war sat amber for most of every hour on every page of the site — and
    this strip is what tells you whether to open the admin pages at all.
    """
    try:
        from features.admin import monitor_stats
        known = [
            ('task_update_ranked_weeks', 'Ranked'),
            ('task_update_battle_logs',  'Battles'),
            ('task_update_raid_weekend', 'Raids'),
            ('task_update_clan_war',     'War'),
            ('task_update_cwl',          'CWL'),
            ('task_update_clan_members', 'Members'),
        ]
        now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        cutoff = now - _dt.timedelta(days=2)
        rows = UptimeTracker.query.filter(UptimeTracker.time >= cutoff).all()
        by_task = monitor_stats.normalize_runs(rows)

        # Dormant counts as healthy here: three of the six tasks are idle for most
        # of any week, and a strip that names them stops meaning "look at this".
        LEVEL = {'up': 'good', 'idle': 'good', 'warn': 'warn',
                 'down': 'bad', 'absent': 'none'}

        result = []
        for fn, label in known:
            s = monitor_stats.task_stats(fn, by_task.get(fn, []), now)
            mins = s['minutes_since']
            result.append({
                'label': label,
                'status': LEVEL.get(s['health'], 'none'),
                'time_str': _fmt_age(round(mins)) if mins is not None else 'No data',
                'mins': round(mins) if mins is not None else None,
            })
        return result
    except Exception:
        return []
```

- [ ] **Step 2: Verify the strip against live-shaped data**

Start the dev server, then run:

```bash
cd coc_stats && python -c "
import app as A
with A.app.app_context():
    for t in A._nav_task_status():
        named = ' <-- named in strip' if t['status'] in ('warn','bad') else ''
        print(f\"  {t['label']:9} {t['status']:5} {t['time_str']:>10}{named}\")
"
```
Expected: no task is named purely for being idle. On the local DB (14 days stale) every task is legitimately `bad`; that is correct, not a regression.

- [ ] **Step 3: Commit**

```bash
git add coc_stats/app.py
git commit -m "fix(nav): stop the status strip alarming on correctly-idle tasks

The strip applied its own <15/<60 minute thresholds against the last run of any
status, so clan_war polling correctly on its hourly idle schedule sat amber for
most of every hour, on every page. It now reads the same recorded interval the
Monitor does, and dormant resolves to healthy so the strip collapses to its
hairline."
```

---

### Task 6: Show the dynamic behaviour on the Monitor

**Files:**
- Modify: `coc_stats/templates/admin/admin_monitor.html`

**Interfaces:**
- Consumes: `task_stats()` fields `mode`, `idle_reason`, `health == 'idle'` (Task 4)

- [ ] **Step 1: Add the `Ruht` pill**

In the `<style>` block, beside the other `.mon-pill` variants:

```css
        /* Dormant by design: neither health nor warning, so neither green nor
           amber. Only ever appears on the three tasks that retune themselves. */
        .mon-pill.idle { color: var(--blue); background: color-mix(in oklch, var(--blue) 11%, transparent); border-color: color-mix(in oklch, var(--blue) 30%, transparent); }
```

Add `'idle': 'Ruht'` to the `health_label` dict.

- [ ] **Step 2: Name the reason in the cadence line**

Replace the register row's cadence cell:

```jinja
                <div class="reg-fig">{{ cadence(t.cadence) }}<small>
                    {%- if t.health == 'idle' and t.idle_reason -%}
                        {{ {'notInWar': 'kein Krieg aktiv',
                            'not ongoing': 'kein Raid-Wochenende',
                            'notFound': 'keine CWL-Saison'}.get(t.idle_reason, t.idle_reason) }}
                    {%- else -%}zuletzt {{ ago(t.minutes_since) }}{%- endif -%}
                </small></div>
```

- [ ] **Step 3: Shade idle stretches in the lane strip**

In the `laneData` JSON block, emit each task's idle windows by walking its series and grouping consecutive runs whose `interval_minutes` equals the idle value. Add to each lane object:

```jinja
  "idle": [{% for w in t.idle_windows %}["{{ w.start.strftime('%Y-%m-%dT%H:%M:%S') }}","{{ w.end.strftime('%Y-%m-%dT%H:%M:%S') }}"]{{ "," if not loop.last else "" }}{% endfor %}]
```

This requires `task_stats()` to produce `idle_windows` — add it in Task 4's module alongside `gaps`, grouping consecutive series points by mode.

In the lane-drawing JS, draw the band **first**, before the run marks, so it sits behind them:

```javascript
            const idle = (lane.idle || []).map(w =>
                '<rect x="' + px(w[0]).toFixed(1) + '" y="0" width="' + Math.max(1, px(w[1]) - px(w[0])).toFixed(1) +
                '" height="' + H + '" fill="var(--lane-idle)"/>').join('');
```

and add the token beside the others:

```css
            --lane-idle: color-mix(in oklch, var(--blue) 9%, transparent);
```

Add a legend entry `<i><span class="sw sw-idle"></span>ruhend</i>` with `.lane-legend .sw-idle { background: var(--lane-idle); }`.

- [ ] **Step 4: Verify in the browser**

Run the screenshot script against `?days=30` at 390/768/1200 and **read the PNGs**. Check specifically that the idle band does not compete with the red failure marks — those remain the strip's primary signal. If it does, drop the band's alpha.

- [ ] **Step 5: Run the full verification suite**

Run:
```bash
cd coc_stats && python -m pytest tests/ -q
```
Expected: all pass.

Then the browser suites in `scratchpad/`: `verify_monitor.py`, `verify_fixes.py`, `verify_audit.py`, `verify_overview.py`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add coc_stats/templates/admin/admin_monitor.html coc_stats/features/admin/monitor_stats.py
git commit -m "feat(admin): show when a task is dormant rather than broken

Ruht is neutral blue - dormant is neither health nor warning - and the cadence
line names why: kein Krieg aktiv, kein Raid-Wochenende, keine CWL-Saison. The
lane strip shades idle stretches, so it doubles as a history of when the clan
was actually at war."
```

---

## A note on testing the backfill

The spec asks for the backfill to be tested against synthetic rows. It has no
pytest coverage here on purpose: `monitor_stats` is a pure module and this repo
has no DB-backed test harness, so a migration test would mean standing one up —
more machinery than the one-shot `UPDATE` warrants. Task 2 Steps 4 and 5 verify
it directly instead: a per-task/per-interval row count after `upgrade`, and a
full `downgrade` → `upgrade` cycle. If that turns out to be insufficient, the
right fix is a DB fixture, not a weaker check.

## Verification before merge

- [ ] `cd coc_stats && python -m pytest tests/ -q` — all pass
- [ ] All four browser suites in `scratchpad/` pass
- [ ] Sweep every route (the 19-page script from the audit session): no JS errors, no overflow
- [ ] `clan_war` on the live-shaped data reads `Ruht`, not `Still`
- [ ] The nav strip collapses to a hairline when the only non-`up` tasks are idle
- [ ] `flask db upgrade` then `flask db downgrade` then `upgrade` — clean both ways

## Deploy notes

- One migration, `b4e7d2a91f56`. It adds a nullable column and updates rows in place; it deletes nothing.
- Backfill touches ~85,000 rows in three `UPDATE`s. On MySQL this is fast, but it runs inside the deploy's `flask db upgrade`, so expect a few seconds longer than usual.
- No new dependencies.
- The scheduler must restart for the new `add_job` intervals to take effect — the deploy script already stops and starts `coc_scheduler`.

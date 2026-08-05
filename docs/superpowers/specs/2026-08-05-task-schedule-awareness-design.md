# Task schedule awareness — design

Date: 2026-08-05 · Branch: `dev_coc`

Make the app know what schedule each background task is actually on, instead of
guessing it from timestamps. Fixes a live false alarm, removes an inference, and
surfaces the dynamic behaviour the scheduler already has.

## 1. The problem, measured

Three of the six background tasks change their own interval at runtime:

| task | interval | switches on |
|---|---|---|
| `clan_members` | 5 min | — fixed |
| `battle_logs` | 5 min | — fixed |
| `ranked_weeks` | 10 min | — fixed |
| `clan_war` | 3 min ↔ 60 min | war active vs `notInWar` / `warEnded` |
| `cwl` | 3 min ↔ 60 min | CWL season active vs not |
| `raid_weekend` | 3 min ↔ 60 min | raid weekend ongoing vs not |

They call `scheduler.reschedule_job()` on themselves (`tasks/clan_war.py:65`,
`tasks/cwl.py:67`, `tasks/raid_weekend.py:66`), so the interval is a consequence
of game state, not a constant.

**Nothing records what the interval currently is.** `UptimeTracker` stores when a
run happened, how long it took and whether it succeeded — not the schedule it was
on. So both reporting surfaces reverse-engineer it, and both get it wrong:

- `monitor_stats.infer_cadence()` takes the median gap between recent
  **non-skipped** runs. An idle task writes only `skipped` rows, so the median
  still reflects the last war's 3-minute cadence while the real gap is 60
  minutes. `60 > 3 × 2.5` ⇒ the Monitor reports **Still**.
- `_nav_task_status()` (app.py:88) uses its own fixed thresholds — under 15 min
  good, under 60 warn, else bad — against the last run of any status. An idle
  task therefore sits amber for most of every hour and tips red just before each
  poll.

Verified live on the VPS while writing this:

```
Ranked   good    9m ago
Battles  good    4m ago
Raids    good    3m ago
War      warn   30m ago   ← named in the strip, nothing wrong
CWL      good    3m ago
Members  good    5m ago
```

`clan_war` had polled correctly 30 minutes earlier and was waiting out its idle
interval. The strip is the surface the owner uses to decide whether to open the
admin pages at all, so a recurring false amber is the worst possible failure: it
trains him to ignore the one signal he relies on.

**Separate defect found while investigating** — `tasks/raid_weekend.py:58`:

```python
if raid_weekend.state not in ('ongoing', 'ended'):
    reschedule(hours=1); return          # idle
elif raid_weekend.state == 'ongoing':
    reschedule(minutes=3)                # active
# state == 'ended' matches neither branch — no reschedule at all
```

The last raid weekend ended 2026-08-03 07:00. State has been `'ended'` since, so
the job kept whatever interval it last held: 3 minutes. Measured **480 runs in
24 hours** against ~24 if it had downshifted — roughly 456 needless Clash API
calls a day, against an API this codebase documents as timing out frequently.
`clan_war` and `cwl` do not have this hole.

## 2. Decisions

1. **Idle is its own state**, shown on the three dynamic tasks only. The register
   gains a fourth pill: `Läuft` · `Ruht` · `Verzögert` · `Still`.
2. **Persist the interval** rather than deriving it from `status == 'skipped'`.
   Deriving would couple the Monitor to each task's internal control flow — and
   the raid_weekend bug is a live demonstration of that failure mode: once
   `'ended'` correctly downshifts it will still log `success`, so a
   status-based rule would read it as active-but-overdue.
3. **Backfill, do not reset.** A migration that deletes rows sits in an automated
   deploy path. The table holds 52 days and 85,646 rows, including the 31 errors
   of the 2026-07-31 API outage that the Monitor redesign was built around.
4. **Idle counts as healthy in the nav strip**, so an idle task is not named and
   the strip stays a hairline. Dormancy is the normal state of three of six tasks
   for most of any week; it is not news. Seeing *which* tasks are dormant is the
   Monitor's job, one click away.
5. **Name the idle reason** on the Monitor. The tasks already write it
   (`notInWar`, `not ongoing`, `notFound`), so it costs nothing to surface.
6. **Shade idle stretches in the lane strip**, turning it into a readable history
   of when the clan was actually at war.

## 3. Single source of truth

New `tasks/schedule.py`:

```python
TASK_SCHEDULE = {
    'task_update_battle_logs':  {'active': 5,  'idle': None},
    'task_update_ranked_weeks': {'active': 10, 'idle': None},
    'task_update_clan_members': {'active': 5,  'idle': None},
    'task_update_clan_war':     {'active': 3,  'idle': 60},
    'task_update_cwl':          {'active': 3,  'idle': 60},
    'task_update_raid_weekend': {'active': 3,  'idle': 60},
}
```

`idle: None` marks a task with no dormant mode. `run_scheduler.py`, the three
dynamic tasks and `features/admin/monitor_stats.py` all read from here.

This matters more than it looks. The interval is currently written in
`run_scheduler.py` *and* in each task's reschedule call; adding a third copy in
the Monitor is how the correlation-overlay bug happened earlier the same day —
CSS and JS each encoded the same 18px offset and drifted apart. One copy.

## 4. Schema

`UptimeTracker.interval_minutes` — nullable `Integer`.

Each task passes the interval **in force for the next run**. The dynamic tasks
already call `reschedule_job()` before `db_finalize_uptime()`, so the new value
is correct at write time. `db_finalize_uptime()` gains an
`interval_minutes=None` keyword.

**Paths that never reach a reschedule decision write `NULL`.** An API failure
returns early — `tasks/clan_war.py:45` writes its `error` row before the code
that would inspect war state — so the task genuinely does not know which
schedule it is on. Inventing a value there would be a guess, which is the thing
this change exists to remove.

Readers therefore resolve the expected interval as **the most recent non-NULL
`interval_minutes` for that task**, not strictly the last row's. A burst of
error rows carries the last known schedule forward, which is correct: a failed
poll does not change the interval. If no non-NULL row exists in the window, the
task's `TASK_SCHEDULE['active']` is the fallback, and the reader marks the value
as assumed rather than measured.

**Backfill, in the same migration**, so no NULL path survives in the code:

| task | rule | accuracy |
|---|---|---|
| `clan_members`, `battle_logs` | 5 | exact — never varied |
| `ranked_weeks` | 10 | exact |
| `clan_war`, `cwl`, `raid_weekend` | `skipped` → 60, else → 3 | accurate; verified against live rows |

The dynamic rule is the inference being removed, applied once at rest rather
than on every page load. For `raid_weekend` the `'ended'` rows genuinely ran at
3 minutes, so recording 3 is truthful, not a papering-over.

Downgrade drops the column. No data is destroyed in either direction.

## 5. Derivation

`infer_cadence()` is deleted. Both surfaces read facts:

```
expected = most recent non-NULL interval_minutes for this task
           (fallback: TASK_SCHEDULE[key]['active'])
mode     = 'idle' if expected == TASK_SCHEDULE[key]['idle'] else 'active'
```

A task with `idle: None` can never resolve to `idle`, so the fourth state
appears only on the three dynamic tasks.

| state | condition |
|---|---|
| `Läuft` | active, within `expected × WARN_FACTOR` |
| `Ruht` | idle, within `expected × WARN_FACTOR` |
| `Verzögert` | beyond `expected × WARN_FACTOR` (1.5) |
| `Still` | beyond `expected × DOWN_FACTOR` (2.5) |

`absent` (no runs at all in the window) is unchanged.

Gap detection uses the same persisted interval, so an hourly poll no longer
registers as a gap against a 3-minute cadence.

## 6. Surfaces

**Nav strip** — `_nav_task_status()` drops its own thresholds and calls the
shared helper. Idle resolves to `good`. The strip already names only `warn`/`bad`
tasks (`_nav.html:173`), so an idle task simply stops appearing and the strip
collapses to its hairline.

**Monitor register** — the `Ruht` pill is neutral, neither green nor amber, since
dormancy is neither health nor warning. The cadence line reads
`alle 60 min · kein Krieg aktiv`.

**Lane strip** — a faint band behind stretches where the task was on its idle
interval. Must not compete with the red failure marks, which remain the strip's
primary signal.

## 7. Order of work

1. `raid_weekend` `'ended'` fix — own commit, first. Two lines, independent of
   everything else, and it stops the wasted API calls immediately.
2. `tasks/schedule.py` + migration + backfill + `db_finalize_uptime` plumbing.
3. `monitor_stats` derivation, replacing `infer_cadence()`.
4. Nav strip onto the shared helper.
5. Monitor UI: pill, cadence copy, lane shading.

## 8. Testing

`monitor_stats` is a pure module with 48 existing tests; mode derivation and all
four health states are covered there. Additionally:

- The backfill, against synthetic rows of each shape.
- The negative case: an idle task that stops polling must still reach `Still` —
  at 150 minutes, not never.
- NULL handling: a run of `error` rows with NULL intervals must resolve to the
  last known schedule, not to the fallback and not to `absent`.
- A fixed-interval task must never resolve to `idle`, whatever its row values.
- A **teeth check** on the idle guard: disable it, confirm tests fail, restore.
  Same discipline applied to the correlation rule.

## 9. Known consequence, accepted

Scaling the threshold to the schedule means `Verzögert` and `Still` for an idle
task now sit at 90 and 150 minutes. If the scheduler process dies while all three
dynamic tasks are dormant, nothing reports it for two and a half hours.

That is the honest cost of not crying wolf. The real fix is a liveness check on
the scheduler process itself rather than on individual tasks — out of scope here,
flagged for its own pass.

## 10. Out of scope

- Scheduler process liveness (above).
- The `_nav_health()` footer aggregate, which will inherit the corrected
  per-task states without changes.
- Any change to what the tasks actually do when they run.

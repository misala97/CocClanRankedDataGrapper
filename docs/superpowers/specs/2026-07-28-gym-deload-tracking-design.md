# Gym Tracker — Deload tracking

**Date:** 2026-07-28
**Feature:** `personal_apps` / gym
**Status:** design approved, ready for planning

---

## 1. Problem

The tracker judges every session as an attempt at progress. A deliberately
light week is therefore indistinguishable from a bad one: the reduced weights
count as sessions without a PR, so they push exercises toward `stagniert`; the
reduced volume drags down the average that future sessions are measured
against; and the next session pre-fills from the deload's weights, so the
lifter silently restarts at 70 % and stays there.

The owner ran a deload week and hit exactly this, which is what prompted the
feature.

Two things are needed: a way to **mark** a session as a deload so the
statistics stop misreading it, and enough **prescription** that running one is
a single tap rather than manual arithmetic across every set.

## 2. Goals

1. Mark any session — planned, in progress, or long finished — as a deload.
2. Exclude deload sessions from every judgement that assumes an attempt at
   progress, while keeping them in every figure where they are simply true.
3. Prescribe deload weights automatically when the session has not been
   started yet.
4. Suggest a deload when the data indicates accumulated fatigue.

## 3. Non-goals

- **No scheduler and no deload calendar.** `PRODUCT.md` rules out planning
  features; the suggestion is derived from what happened, never from a date.
- **No per-exercise deload.** The flag is per session. Deloading only the
  stalled lift is a real practice, but it costs taps mid-workout and makes
  "was this a deload session" unanswerable. It can be layered on later without
  reworking this.
- **No deload blocks or date ranges.** A deload week is the two or three
  sessions in it, each flagged.
- **No fourth semantic hue.** §4.3 of the design brief permits exactly three.

---

## 4. Data model

Two columns on `WorkoutSession` (`gym_workout_sessions`), one Alembic revision
with `down_revision = '9c3e5a71f2b6'` (current head):

```python
is_deload  = db.Column(db.Boolean, nullable=False, default=False,
                       server_default=sa.false())
deload_pct = db.Column(db.SmallInteger, nullable=True)
```

`deload_pct` records the percentage actually used, rather than relying on a
module constant. Two reasons:

1. Changing the default later must not retroactively rewrite what past
   sessions claim to have been.
2. It makes the depth a measurable variable — the app can eventually answer
   *which deload depth preceded the best rebound*, which is the kind of
   question it exists to answer. A hardcoded constant discards that.

It is nullable rather than defaulted so historic and non-deload sessions stay
honestly blank instead of claiming a depth they never had.

`server_default` is required on `is_deload`: the column is `NOT NULL` and the
table has existing rows.

**Default percentage:** `DELOAD_DEFAULT_PCT = 70`.

## 5. What deload changes

Every statistics function consumes `stats.PerformedExercise`, which is built in
exactly one place (`routes._to_performed`). One new field carries the flag to
all of them:

```python
@dataclass(frozen=True)
class PerformedExercise:
    ...
    is_deload: bool = False   # performed in a deliberately light session
```

Defaulted, so existing test fixtures keep constructing rows without it.
`load_performed()` already joins `WorkoutSession`, so this adds no queries and
preserves its one-call-per-request contract.

| Consumer | Deload sessions | Rationale |
|---|---|---|
| `sessions_since_pr`, `exercise_state`, `stall_report` | **excluded** | A deliberate light day is not a failed PR attempt. Counting it manufactures the plateau the deload was meant to break. |
| PR detection — `_pr_weight`, `_pr_e1rm`, `is_weight_pr` / `is_volume_pr` / `is_e1rm_pr`, `is_new_best`, `session_record_counts` | **excluded**, as candidate *and* as baseline | A deload cannot set a record, and its lighter numbers must not lower the bar the next real session is judged against. |
| `session_report` volume averages (`avg_volume`, `volume_delta_pct`, `comparable_session_volumes`) | **excluded** | Averaging a 70 % week into "normal" quietly deflates the baseline for every future session. |
| `_last_full_performance` / `_last_performance` seeding | **excluded** | **The critical one.** The next normal session must pre-fill from the last *real* session. Seeding from a deload leaves the lifter at 70 % permanently — the feature would sabotage the training it exists to support. |
| `exercise_progress` — `table` and `series` | **included, marked** | These are the record of what was performed. Dropping the rows would leave unexplained gaps in the history table and holes in the chart line. Each row/point carries `is_deload` so the page can dim it. |
| `exercise_progress` — `pr_weight`, `pr_e1rm`, `state`, `sessions_since_pr` | **excluded** | Same function, but these four are judgements, and fall under the rows above. |
| `exercise_progress` — new `last_progression` | **excluded** | Keeping deload rows in `table` means `table[0]` (the newest row) can *be* the deload. Anything quoting "the weight you are stuck at" must read the newest **non-deload** row instead, or the stagnation advice tells you to add 2.5 kg to a weight you deliberately went light on. Also `None` when an exercise's only history is deloads — which newly breaks the old invariant that a non-empty `table` implies a `pr_weight`. |
| `weekly_tonnage` | **included, marked** | The dip is true and should be visible. An unexplained hole in the chart is worse than a labelled one. |
| `consistency` | **included** | The session happened. |
| `muscle_group_volume` (balance) | **included** | The sets were performed; the muscle was trained. Excluding them would fake an under-trained group. |
| `routine_memory` | **included** | It answers "when did I last run this routine", which a deload still satisfies. |

**Edge case — a deload session is the only history an exercise has.** With
deload rows excluded, `has_history` is false and the verdict is `neu`. Correct:
there is no honest basis for comparison.

**Edge case — every session of an exercise is a deload.** Same path. No
division by an empty set occurs, because the exclusions happen before the
aggregates are computed, and the existing code already guards `has_history`.

## 6. Prescription

### 6.1 The weight math

Pure function in `stats.py`, unit-tested in isolation:

```python
DELOAD_DEFAULT_PCT = 70

def deload_weight(weight, pct, is_unilateral):
    """`pct` of the working weight, rounded DOWN to a loadable increment.

    Rounding up would make the deload heavier than prescribed, which is the
    one direction that defeats the point. Increments match _next_weight():
    2.5 kg is the smallest pair of plates on most bars, and a unilateral lift
    moves one side at a time.
    """
    if weight <= 0:
        return weight          # a bodyweight set stays bodyweight
    step = 1.25 if is_unilateral else 2.5
    return max(step, math.floor(weight * pct / 100.0 / step) * step)
```

- The `weight <= 0` guard runs **first**, so a genuinely bodyweight set is not
  handed 2.5 kg by the floor below it.
- `max(step, ...)` stops a very light accessory rounding to zero.
- Applied **per set**, not to the top set only, so any ramping or drop-off in
  the session's shape is preserved. `80, 80, 75` at 70 % becomes `55, 55, 52.5`.

### 6.2 The toggle rule

**The flag is always editable. The prescription is what is gated.**

| Session state when toggled | Flag | Weights |
|---|---|---|
| No completed sets, toggled **on** | set | every `SessionSet.weight` rewritten through `deload_weight()` |
| No completed sets, toggled **off** | cleared | **re-seeded** from `_last_full_performance()` |
| Any completed set, either direction | set / cleared | untouched |

One rule covers all three real cases: the fresh session, the rare mid-workout
change of plan, and the retroactive relabel of a finished workout. Nothing the
lifter actually performed is ever overwritten, and the toggle is never dead.

The "any completed set" test is **computed, not latched** — it asks whether the
session has a completed set *right now*. Un-completing a set therefore
re-enables prescription, so a mis-tap is always recoverable.

**Toggling off re-seeds rather than dividing by the percentage.** Reversing the
arithmetic after a floor is lossy: `80 → 55 → 78.57 → 77.5`. Repeated toggling
would walk the weights downward. Re-seeding is exact and reuses existing code.

### 6.3 Route

`POST /gym/session/<int:session_id>/deload`

Form fields: `on` (`'1'` / `'0'`), `pct` (optional int, defaults to
`DELOAD_DEFAULT_PCT`).

1. Load the session (404 if absent). Accept finished sessions — the retroactive
   case is a first-class flow, not an exception.
2. Validate `pct` into a bounded whitelist (see §10). Reject silently to the
   default rather than erroring; this is a one-user app and a bad value should
   not lose the toggle.
3. Set `is_deload`; set `deload_pct` when on, `None` when off.
4. Apply the §6.2 table.
5. Redirect back to the referring surface (session detail or finished page).

## 7. Suggestion

```python
DELOAD_STALL_THRESHOLD = 4     # simultaneous stalls that read as systemic
DELOAD_SUPPRESSION_DAYS = 21   # don't re-suggest this soon after a deload

def deload_signal(report, rows_by_exercise, now, last_deload_at=None,
                  days=ROLLING_WINDOW_DAYS,
                  threshold=DELOAD_STALL_THRESHOLD,
                  suppression_days=DELOAD_SUPPRESSION_DAYS):
    """The stalls that indicate accumulated fatigue rather than a weak point.

    Only exercises actually trained inside the rolling window count: a lift
    abandoned six months ago drifts into 'stagniert' from disuse and says
    nothing about how recovered the lifter is. Returns None when the signal
    does not fire, otherwise the qualifying stalls so the page can name the
    lifts rather than assert a vague verdict.
    """
```

- **Input** is `stall_report()`'s existing output plus the `rows_by_exercise`
  map the caller already holds. No new query, no new bulk load.
- **Recency filter:** an entry qualifies only if its exercise has a row with
  `started_at >= now - days`. `ROLLING_WINDOW_DAYS` is 28, matching every other
  "how am I doing lately" figure in the module.
- **Suppression:** returns `None` if `last_deload_at` is within
  `suppression_days`, so a stall that survives a deload does not nag every
  session.
- **Threshold rationale — why 4, not 3.** The active rotation is roughly 12–15
  distinct exercises (about 4 exercises per session, 2–3 sessions per week,
  28-day window). `STAGNATION_THRESHOLD` counts *sessions*, not weeks, and
  isolation lifts cross it routinely — a lateral raise going a month without an
  e1RM PR is ordinary. At 3 the suggestion would fire during normal training
  and be learned-ignored. 4 is roughly a third of the rotation stalling at
  once, which is systemic.

`last_deload_at` is one cheap query: the newest finished session with
`is_deload` set.

`stall_report()`'s own **signature and behaviour are unchanged**: it keeps
reporting every currently stalled exercise, unfiltered by recency, because the
"Steht still" roster on Heute should keep listing all of them. (Its *inputs*
still change, like every other function's — deload rows are excluded upstream
per §5, so a light week can no longer push a lift onto that roster.) Recency
filtering belongs to the deload signal alone.

## 8. Surfaces

Deload is rendered with **no colour**, using `--dim` on `--raised`. This is not
a compromise around the three-hue rule — it is semantically right. A deload is
not live, not a record, not a stall. It is a settled fact about a session, and
it carries **the word** plus the percentage, satisfying §4.2's requirement that
every state carry a shape or a word and not only a colour.

New chip variant `chip--deload`, alongside the existing `chip--done` and
`chip--record`.

### 8.1 Live session — `session_detail.html`

- Pill toggle in `.session-head`, minimum 44×44, a real `<button>` in a form.
- Off by default.
- When on: a quiet band beneath the header reading `DELOAD · 70 %`, with
  60 / 70 / 80 quick-picks.
- Once any set in the session is completed, the quick-picks are **hidden** —
  changing the percentage can no longer rewrite anything, so offering it would
  be a control that silently does nothing. The flag toggle itself remains.

### 8.2 Finished session — `session_finished.html`

- `chip--deload` beside `chip--done` in `.session-head`.
- **Verdict copy needs a dedicated branch.** The existing
  `total_volume_delta_pct <= -5` branch renders *"Leichter als sonst — −35 %
  gegenüber deinem Schnitt"*, which frames a deload that worked exactly as
  intended as a shortfall. A deload session instead reads:
  **"Deload — 70 %. Bewusst leichter."**
  This branch is checked before all existing volume branches, and after the
  `total_sets == 0` branch (an empty session is an empty session regardless of
  its label).
- **Stagnation advice is suppressed.** The `advice` block must not tell the
  lifter to add 2.5 kg to a lift they deliberately went light on. Records are
  suppressed by the §5 exclusions already.
- **The retroactive toggle lives here**, next to the workout it relabels,
  rather than on the history list.

### 8.3 History — `verlauf.html`

`chip--deload` on the row, in the same slot as `chip--record`.

### 8.4 Tonnage chart — `heute.html`

Deload weeks marked so the dip reads as explained rather than as a gap. **Hatched**
bar, no new hue.

> Superseded during implementation: this section originally specified a *dimmed*
> bar. Dimming was built and rejected — the bar's **height is the datum**, so
> fading it to 45 % dropped it to roughly 1.37:1 against the panel and read as
> "no training that week", the opposite of the meaning. It also left the state
> carried by brightness alone, against §4.2. A diagonal hatch keeps full
> legibility and supplies the required shape. The rationale lives beside the
> rule in `gym.css`.

The tonnage chart is **not** Chart.js — it is plain CSS bars (`.vbars` /
`.vbar` divs in `heute.html`, heights set inline from a percentage of the
peak). Marking a week is therefore just a modifier class, `.vbar--deload`, with
no canvas colour-resolution concern. (Chart.js is used only on exercise detail
and the progress modal, neither of which changes here.)

`weekly_tonnage()` gains a per-week `has_deload` flag. A week containing both
normal and deload sessions counts as a deload week for marking purposes; the
tonnage value itself is unchanged and still totals everything.

### 8.5 Heute — the suggestion

Rendered as the **lead element of the existing "Steht still" section**, not as
a new panel — §4.5 bans card proliferation, and this is the same data
escalated.

Copy: **"{n} aktive Übungen stehen still — ein Deload könnte fällig sein."**
followed by the named lifts, which the section already lists.

**Heute is the only home for the suggestion.** It sits adjacent to the button
that acts on it: read it, start the workout, flip the toggle. On the finished
page it would be advice forgotten before the next session, and that page
already owns a per-exercise advice block.

## 9. Tests

Added to the existing gym suite.

**`tests/test_gym_stats.py`** — pure functions, no DB:

- `deload_weight`: standard case; unilateral increment; rounds **down** not to
  nearest; bodyweight (`0`) passes through unchanged; a very light weight
  floors to one increment rather than zero; per-set application preserves a
  ramped `80, 80, 75` shape.
- `sessions_since_pr` / `exercise_state`: a deload row between two normal
  sessions does not increment the count, and a run of deloads cannot by itself
  push an exercise to `stagniert`.
- PR detection: a deload row cannot *set* a record; a deload row cannot *become
  the baseline* that a later normal session is compared against.
- `session_report`: deload sessions are absent from `avg_volume` and
  `volume_delta_pct`.
- `deload_signal`: fires at the threshold and not below it; a stalled exercise
  untrained for longer than the window does not count; returns `None` inside
  the suppression window; **fires normally when `last_deload_at` is `None`** —
  a lifter who has never deloaded must still be able to be told to.
- `weekly_tonnage`: `has_deload` set on a mixed week.

**`tests/test_gym_routes_smoke.py`** — the route:

- Toggle on with no completed sets rewrites every set weight.
- Toggle on with one completed set rewrites nothing and still sets the flag.
- Toggle off with no completed sets restores the seeded weights exactly (not
  the lossy division).
- Toggle on a **finished** session sets the flag and touches no set.
- A subsequent normal session started from the same template seeds from the
  last non-deload session, not from the deload. *This is the regression test
  that matters most* — it is the failure the feature exists to prevent.
- An out-of-range `pct` falls back to the default instead of erroring.

## 10. Edge cases and decisions

| Case | Decision |
|---|---|
| `pct` out of range or non-numeric | Clamped to the `{50, 60, 70, 80, 90}` whitelist; anything else falls back to `DELOAD_DEFAULT_PCT`. Never errors — losing the toggle is worse than accepting an odd value. |
| Toggling deload on an active session mid-workout | Supported, flag-only once a set is completed. Rare by the owner's own account; correctness over convenience. |
| Bodyweight sets (`weight = 0`) | Unchanged by prescription. A deload of nothing is nothing. |
| Unilateral exercises | 1.25 kg increment, matching `_next_weight()`. Volume doubling is unaffected — it happens downstream in `set_volume()`. |
| Retroactively flagging a session that awarded records | The records disappear from the recount, which is correct: they were set under a light session and should never have counted. |
| Deload session with zero completed sets | Behaves as any empty session; the `total_sets == 0` verdict branch wins. |
| A skipped exercise in a deload session | Unaffected. `skipped` and `is_deload` are orthogonal; `load_performed` already drops rows with no completed sets. |
| A mid-session substitution in a deload session | Unaffected. `replaces_id` handling is upstream of the flag. |

## 11. Risks

- **The suggestion threshold is a guess.** 4 is reasoned from an estimated
  12–15 exercise rotation, but it is one constant against real training data
  nobody has yet. It is a single documented value and trivial to lower if the
  suggestion turns out too quiet — which is the failure mode to prefer, since a
  nagging suggestion gets ignored permanently.
- **The exclusions touch nearly every function in `stats.py`.** The risk is a
  missed call site rather than wrong logic. Mitigated by routing everything
  through the one `PerformedExercise` field and by the seeding regression test
  in §9.
- **`70 %` may prove too light or too heavy.** This is why it is stored per
  session rather than hardcoded; the data will answer it.

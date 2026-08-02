# Gym: actual rest, and a briefing on the routine you are about to start

**Date:** 2026-08-03
**Status:** Approved design, not yet implemented
**Scope:** `personal_apps` gym feature only.

## Why

Two gaps between what the app records and what it tells you. They ship together
but share no code, so the plan can build them as separate tasks.

**Rest is planned and never measured.** Every exercise carries a `rest_seconds`
and the session page counts it down, but `SessionSet` has no timestamp, so the
app has never known how long you actually rested. That single number explains
two things it currently cannot: why a session ran long, and why a lift went
flat while the log looks unchanged.

**Heute knows which lifts are stalling and never says so where it matters.**
`stall_report` is already computed for the page, and the routine card you are
about to tap says only which exercises are in it. The stall list sits further
down and covers every exercise you own, including ones this routine does not
contain.

Both stay inside the product's boundary: no plan is proposed, no target is set.
The app reports what happened and names what to watch.

## Decisions

### 1. Rest answers two different questions, on two surfaces

The author chose both readouts rather than one:

- **The finished page** reports the session: *"52 Minuten · davon 31 Pause."*
  Works from the first workout, and gives the duration already shown there a
  meaning.
- **Statistik, inside the existing "Wie du trainierst" section**, reports the
  habit: *"Du planst 2:30, nimmst dir 3:40."*

They are not redundant. The first is a fact about one session; the second is a
pattern across all of them, which is exactly the windowed/cumulative split the
gym's PRODUCT.md uses to decide which page a figure belongs on.

*Rejected:* either one alone. The per-session number says nothing about whether
that was normal for you; the habit says nothing until several sessions exist.

### 2. Rest is the gap between consecutive completed sets

Measured within one session, ordered by `completed_at`. This deliberately
includes walking to the next machine and setting it up — that time is not
lifting, and it is a real part of why a session takes as long as it does.

**Gaps over 10 minutes are not counted.** A phone call between sets is not rest.
Ten minutes is long enough for a genuinely slow superset and short enough to
exclude an interruption. Without a cap a single long gap distorts everything
downstream.

**Planned rest is the ending exercise's, not the next one's.** You finish a set
of Bankdrücken and rest Bankdrücken's time.

### 3. The habit figure is a median

One slow day must not move it. The median also makes the 10-minute cap less
load-bearing: an outlier that slips past the cap shifts a median far less than
it shifts a mean.

### 4. Nothing is retroactive, and the UI must say so

Every existing `SessionSet` has `completed_at` NULL. Both readouts stay silent
until real data exists rather than reporting a confident zero — "noch keine
Daten", never "0 Minuten Pause". This is the state most likely to look broken on
the day it ships, so it is a requirement rather than a nicety.

### 5. The briefing names the worst stall in that routine, and is otherwise silent

On the **lead routine card only** — the one carrying the Starten button. The
other routines render as compact rows; a line of context on each would become
wallpaper.

Silence when nothing in the routine is stalling is what makes the line mean
something when it appears.

*Rejected:* "how it went last time" (always present, so quickly stops being
read) and "what this routine is owed" (closest to restating the muscle-balance
chart already on the page, in words).

## Feature A: actual rest

### Schema

| column | change |
| --- | --- |
| `gym_session_sets.completed_at` | new, DateTime, nullable |

No other table changes. Nullable because every existing row predates it, and
because a set that is not completed has no completion time.

### Writing it

- Set to now when a set is marked completed — both in `gym_toggle_set_complete`
  and in `gym_add_set`, which creates a set already completed.
- **Cleared when a set is un-completed.** Otherwise re-ticking measures a gap
  that includes however long you spent deciding, and the number silently
  becomes fiction.

### Deriving rest

For one session: take its completed sets, order by `completed_at`, and take the
gap between each consecutive pair. Drop any gap over 600 seconds. The first
completed set of a session has no preceding set and contributes no gap.

Each gap's *planned* rest is the `rest_seconds` of the `SessionExercise` whose
set ended the gap, falling back to that exercise's `default_rest_seconds`.

This belongs in `features/gym/stats.py` as a pure function over rows, matching
how the rest of that module is built and tested — no ORM dependency.

### Reading it

**Finished page.** The sum of that session's counted gaps, against its duration
(`finished_at - started_at`, the figure the page already shows): *"52 Minuten ·
davon 31 Pause."* Rendered only when the session has at least one counted gap.

**Statistik, "Wie du trainierst".** *"Du planst 2:30, nimmst dir 3:40."*

Both numbers are medians **over every counted gap in your history, pooled** —
not medians of per-session medians. Pooling weights a long session more than a
short one, which is correct here: the question is what a typical rest of yours
looks like, and a session with twenty sets contains more evidence about that
than one with six. Rendered only when at least one counted gap exists.

## Feature B: the briefing line

No new data and no new computation. `stalls` is already built for Heute by
`stats.stall_report`, and its entries carry `exercise_id`, `name`, `position`,
`stuck_at`, `since` and `sessions_since_pr`.

**Filter** `stalls` to entries whose `exercise_id` appears in the lead
template's exercises. `stall_report` returns worst-first, so the first surviving
entry is the one to name.

**Copy.** One stall:

> Bankdrücken steht seit 4 Sessions bei 40 kg.

More than one — name the worst, count the rest. A line that wraps to three on a
phone stops being read:

> Bankdrücken steht seit 4 Sessions bei 40 kg · 1 weitere

None: render nothing at all.

**Placement.** Between the lead card's exercise list and its Starten button —
the last thing read before tapping.

**Colour.** `--stall`, the teal already used for ATTENTION and by the "Steht
still" section for this exact concept, so the two read as one vocabulary rather
than two competing warnings.

## Testing

- A set completed then un-completed leaves `completed_at` NULL, not stale.
- `gym_add_set` stamps it, since that path creates a set already completed.
- Gaps over 600 seconds are excluded; a session containing one long
  interruption reports the same median as the same session without it.
- The first completed set of a session contributes no gap.
- Planned rest comes from the exercise ending the gap, not the one starting the
  next.
- Both readouts render nothing on data that predates the column, and say so
  rather than showing zero.
- The briefing names only stalls belonging to the lead routine — an exercise
  stalling elsewhere in the catalogue must not appear on a card whose routine
  does not contain it.
- The briefing renders nothing when the lead routine has no stalling exercise.
- Migration reversibility.

## Out of scope

- **Suggesting a rest time.** The app reports what you did; it does not
  prescribe. Same boundary as everywhere else.
- **Rest as a per-exercise statistic.** The habit figure is one number across
  training. Per-exercise rest is a different feature and would need its own
  surface.
- **Backfilling from `rest_ends_at`.** That column records a display target for
  the countdown, not when a set actually landed, and treating it as history
  would invent data.
- **A briefing on non-lead routine cards.**

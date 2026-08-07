# Gym Tracker — the cold-start path

**Date:** 2026-08-07
**Status:** implemented on `dev_personal` (a9dfb49), plus a final-review fix
pass closing five findings (F1–F5, see `final-fixes-report.md`) — two of
which corrected claims made below, a follow-up (H1, below) that carries a
corrected placeholder weight forward within an exercise, and a second,
whole-branch blocker re-review (also F1–F5, see `blockers-report.md`) closing
five more findings — two of which further correct claims below (marked
"blocker-review" to distinguish them from the earlier final-review
corrections). Not merged to `main`.
**Branch:** `dev_personal`

## The problem

Two entry points into a workout are, in the owner's words, "literally unusable":

1. **A freestyle session** — started without a template.
2. **The first run of a new template** — a template whose exercises have no
   history yet, which is what every template is on the day it is created.

The templated path with history behind it is well liked and is not touched by
this work.

### One root cause

`TemplateExercise` stores `exercise_id`, `position` and `rest_seconds` and
nothing else (`models.py:216`). A template is an ordered list of exercises; it
carries no set count, no weight and no reps. **Every number on the live screen
comes from history.**

History is read by `_seeded_sets` (`features/gym/routes.py:292`), which returns
`[]` when the exercise has never been performed. So an exercise with no history
enters a session with **no sets at all**, and the live screen — which is built
throughout on the assumption that a plan already exists — degrades in five
separate places at once:

| # | Symptom | Mechanism |
|---|---------|-----------|
| 1 | The exercise advances after a single set | `_live_context` treats "every set completed" as finished (`routes.py:719`). With no planned sets, the first logged set both creates and completes the list. Each exercise therefore gets exactly one set before the app moves on. |
| 2 | Weight starts at 20,0 kg and can only be stepped | `.field-num` is deliberately keyboard-free; the fallback chain in `_session_live.html:162` lands on a hardcoded `20.0 × 8`. Reaching 100 kg on a 2,5 kg increment is 32 taps. |
| 3 | No chips, no denominator, no rail fill | All of them count planned sets. |
| 4 | Exercises enter one at a time through a modal | `sheet-add-exercise` closes and full-page-renders on every add. Six exercises is six round trips. |
| 5 | A first-time user has an empty catalogue | So each of those six round trips also passes through a separate "Neue Übung" pane, which asks for a muscle group mid-workout. |

Symptoms 1–3 are the shared root and hit **both** entry points. Symptoms 4–5 are
freestyle-only.

### Rejected framing

An earlier proposal was a plan-first build step: pick exercises, set counts and
starting weights, then start. The owner rejected it — *"If I want to plan before,
I would use a template."* Freestyle must stay improvisational, and a template
that happens to have no history is a different problem from freestyle, not a
weaker version of it.

## Design

Three changes, in dependency order.

---

### Change 1 — a plan always exists

**`_seeded_sets` returns three open sets at 20,0 kg × 8 reps when there is no
history, instead of `[]`.**

New constants in `features/gym/stats.py`, alongside `DEFAULT_INCREMENT` and
`DELOAD_REPS`:

```python
DEFAULT_PLAN_SETS = 3
DEFAULT_PLAN_REPS = 8
DEFAULT_PLAN_WEIGHT = 20.0
```

`_session_live.html:162` reads these instead of repeating the literals, so the
fallback chain and the seeding cannot drift apart.

#### Why this seam

All call sites that put an exercise into a session funnel through
`_seeded_sets`:

| Line | Path |
|------|------|
| `routes.py:683` | `gym_start` from a template |
| `routes.py:1077` | `gym_add_session_exercise` mid-workout |
| `routes.py:1279` | un-skip |
| `routes.py:1437` | reorder |
| `routes.py:1729` | shared-session follower reconciliation |
| `routes.py:980` | `gym_replace_session_exercise` (mid-workout substitute) |

One change reaches freestyle, first-run templates and mid-session additions
alike.

**Correction (blocker-review F2):** the table above claimed "all" call sites
at initial ship, but `gym_replace_session_exercise` was not actually one of
them — it created the substitute `SessionExercise` directly, with no call to
`_seeded_sets`, which is exactly the zero-sets shape symptom 1 was about: the
first set logged against a substitute both created and completed its plan.
Reachable any time a lifter swaps an exercise mid-workout for one they have no
history with (equipment taken, trying a variant). Fixed by seeding the
substitute the same way every other row in this table is seeded, at the
substitute's own position — the original row and its already-logged sets are
left untouched, as designed (they keep counting toward the original
exercise's own history). See `blockers-report.md` (F2) for the fix and its
test.

**Correction (final-review F4):** the follower-reconciliation row above was
aspirational, not actual, at initial ship. `sharing.reconcile_follower`
(then at `routes.py:1729`, now `sharing.py`) created the follower's mirrored
`SessionExercise` row but never called `_seeded_sets` on it — its own
docstring said so explicitly. An exercise a leader added mid-workout still
arrived on the follower's side as an empty slot, reproducing symptom 1 for
the follower alone. `_seeded_sets` and its history-lookup helpers moved to a
new `features/gym/seeding.py` (sharing.py cannot import routes.py) and now
take an explicit `user_id`, and `reconcile_follower` seeds every new row it
creates, passing the follower's own id explicitly rather than relying on
`current_user_id()` — which inside a leader's request would otherwise name
the leader. See `final-fixes-report.md` for the fix and its tests.

#### What it fixes for free

Symptom 1 requires no change to `_live_context`. With three planned sets, one
logged set leaves `done != len(sets)`, so the exercise stays live. No new rule,
no second mode, no "next exercise" control. Symptom 3 likewise: chips, rail
fill, tick strip and "Noch N Sätze" all have a denominator again.

#### Safety at the re-seeding call sites

Two call sites re-seed a slot that already exists, and both are already guarded:

- Un-skip (`routes.py:1277`) seeds only `elif not session_exercise.sets`.
- Reorder (`routes.py:1435`) clears and re-seeds only when
  `not any(s.completed for s in se.sets)`.

Neither can overwrite logged work. One accepted behaviour change: reordering a
no-history exercise whose set count the lifter had edited (say to 5) but not yet
logged against now resets it to 3. This is the same class of reset that already
happens today when history-seeded sets are re-derived for a new position.

#### Deload

A no-history exercise gets the plain default, **not** a deload-scaled one.
`_seeded_sets` applies `deload_pct` only on the history branch. There is no
working weight to take a percentage of, and scaling an invented number would
present a fabricated prescription as a real one.

**Correction (final-review F1):** that guarantee held only for `_seeded_sets`
itself, and only claimed to hold for `gym_toggle_deload` by inference — the
original comment ("base_weight stays None … there is no working weight for
gym_toggle_deload to restore this to") assumed the toggle would never fill
`base_weight` for one of these sets, but `gym_toggle_deload` actually filled
`base_weight` for **every** set where it was `None`, with no way to tell an
invented default-plan set apart from a real one that happened to sit at the
same weight. Add-exercise-then-deload-ON scaled the placeholder into a
fabricated prescription; the reverse order stayed safe by accident. Fixed by
giving `SessionSet` an `is_default_seeded` column, set only by `_seeded_sets`'
no-history branch and cleared the same moment a hand-typed edit clears
`base_weight`/`base_reps` (turning the invented number into a real, lifter-
chosen one). `gym_toggle_deload` skips any set carrying it, regardless of
ordering.

#### Considered and dropped

Seeding from `Exercise.bar_weight` for barbell lifts. An exercise created
through the new search sheet has no equipment set, so the signal is usually
absent, and Change 2 makes a wrong seed cheap to correct. Not worth the
branch.

---

### Change 2 — tap the number to type it

`.field-num`'s readout (`_session_live.html:194` and `:203`) becomes a button.
Tapping it swaps the display span for an `<input inputmode="decimal">`, focused
with its contents selected.

- **Commit** on Enter or blur: the parsed value goes into the hidden
  `data-role="value"` input and the readout is restored.
- **Cancel** on Escape: the previous value stands.
- `+` / `−` behaviour is unchanged.
- **Both fields**, weight and reps. One rule is cheaper to remember than two.
- **No snapping** to the exercise's `weight_increment`. Typing is exact by
  intent; the increment governs stepping, not entry.
- Accepts both `82,5` and `82.5`. Renders German (comma) as everywhere else.
- **Never submits.** The confirm button still commits the set.

#### Why this and not hold-to-repeat

The keyboard-free stepper is correct *when the prefilled number is already
close* — which is the 95 % case and stays untouched here. It silently assumes
closeness, and at 20,0 kg that assumption fails, turning the fastest input into
the slowest. Typing is the only option that also fixes a normal templated
session where the lifter moves to a different machine, and it adds no gesture to
the case that already works.

The owner approved this with reservation ("I hope"), so its feel must be checked
on a real phone-sized screen before it ships, not after.

---

### Change 3 — one search sheet

`sheet-add-exercise` (`templates/gym/session_detail.html:229`) loses its
two-pane `add-pick-pane` / `add-new-pane` split and its `<select>`. It becomes a
single pane: a text field that filters the user's catalogue live.

- **Tap a row** → the exercise is added; the POST goes through the existing
  in-place `refreshBody` path; **the sheet stays open**; the row marks as added
  and a running count updates. Tapping again adds a second instance, which
  `gym_add_session_exercise` already permits.
- **No match** → the top row becomes `Anlegen: „<query>"`. One tap creates the
  exercise and adds it. No muscle group is asked — it is already optional and
  editable later in Übungen, and asking for it mid-workout is part of what made
  this flow tiring.
- **An empty catalogue** means every search comes up empty, so a first-time user
  reaches the create path without ever choosing a mode. The `add-new-pane` hint
  ("Du hast noch keine Übungen…") and the mode-switch buttons are retired.

Sheet forms currently navigate rather than post in place
(`session_detail.html:845`). This sheet moves onto the in-place path that
`#session-body` forms already use.

**Non-goal:** picker ordering. Recency or frequency ranking would help the
well-worn case, not the cold-start one, and is a separate piece of work.

---

## Follow-up (H1) — a correction propagates to the remaining defaults

A whole-branch review found that Change 2 (tap the readout to type it) only
fixed the input *speed*, not the count: correcting the weight on set 1 of a
new exercise left chips 2 and 3, and the next set's prefill, sitting at the
invented 20,0 kg placeholder — three retypes per new exercise, on exactly the
path this whole feature exists for.

The owner was asked whether a corrected weight should carry to the remaining
unlogged sets and chose **narrow, not universal**: a hand-typed weight (and/or
reps) propagates forward **only** when the later, still-uncompleted sets of
that same exercise are themselves still sitting on the untouched default plan
(`SessionSet.is_default_seeded`). They explicitly rejected always-carrying a
correction forward, because on a normal templated workout a mid-exercise
weight change is usually a deliberate drop set or ramp-up, not a correction.

Implemented in `gym_toggle_set_complete` (`features/gym/routes.py`) via a new
`_propagate_default_correction` helper, run when a set is confirmed done and
its own weight and/or reps changed from what was stored, and it was itself
still `is_default_seeded` at that moment (read before the "changed by hand"
branches clear the flag on it). It writes the new value into every later
sibling (`position >` the set just confirmed) that is not yet completed and
is still `is_default_seeded`, then clears the flag on each of those siblings
too.

**Correction (blocker-review F1):** `gym_toggle_set_complete`'s confirm button
is not the only weight/reps editor on the live screen. `session_detail.html`'s
per-exercise sheet renders a second, fully functional editor per set, posting
to `gym_update_set` — a route that clears `is_default_seeded` on a hand-typed
change (same as the toggle route) but, at initial ship, never called
`_propagate_default_correction`. Because the flag was already cleared,
confirming that same set afterward through the toggle route's own button
found `was_default_seeded` already `False` and silently skipped propagation
too — the sheet's editor both bypassed propagation and disabled the later
one, leaving the lifter back to retyping the weight on every set. Fixed by
calling `_propagate_default_correction` from `gym_update_set` under the same
condition (`was_default_seeded and` the value actually changed, read before
the clearing branch), so either editor on the live screen carries a
correction the same way. `gym_update_set`'s docstring, which described it as
exclusive to the finished-session "Sätze & Notizen" disclosure, is corrected
to note the live sheet as well. See `blockers-report.md` (F1) for the fix and
its test.

Three decisions were left to the implementation:

- **Does adopting the value clear `is_default_seeded` on the sibling that
  received it?** Yes. The correction is now the plan, not a guess. Leaving
  it set would let a *second*, independent correction later in the exercise
  re-propagate past sets the lifter already silently accepted at the first
  corrected number — which is the always-carry-forward behaviour the owner
  rejected, just deferred by one set instead of skipped. Clearing it means
  the exercise behaves like an ordinary templated one from the first
  correction onward: any further divergence is deliberate and stays local.
- **Do reps propagate on the same rule as weight, or only weight?** Same
  rule as weight. The two are seeded together, cleared together
  (`is_default_seeded` is one flag covering both), and `gym_toggle_set_complete`
  already treats a hand-typed weight and a hand-typed rep count identically
  everywhere else. Propagating only weight while leaving reps stuck at the
  invented 8 would be a second, narrower version of the exact bug this fixes.
- **Are earlier sets, or anything already completed, ever touched?** No.
  Propagation only reaches later positions, and only sets that are not yet
  completed — logged work is never rewritten, regardless of position or
  flag state.

Tests in `personal_apps/tests/test_gym_cold_start.py`: correcting set 1
carries to pending default sets 2/3; a history-seeded exercise is
unaffected (the owner's explicit condition); a set the lifter already
hand-edited is not overwritten by a later correction; a completed set is
never rewritten even if it is still `is_default_seeded`; a set that adopted
a propagated correction has its own `is_default_seeded` cleared. Each was
verified with a teeth experiment — the guarded mutation was applied to
production code and the test confirmed to fail for the stated reason before
being reverted.

---

## Verification

### Automated (pytest, `personal_apps/tests/`)

Change 1:
- `_seeded_sets` returns three sets at the default weight and reps for an
  exercise with no history, and unchanged history-derived sets when history
  exists.
- The default applies at each call site: template start, mid-session add,
  un-skip, reorder.
- A no-history exercise in a deload session seeds the plain default, not a
  scaled one.
- **The advance rule:** log one set on a freshly added no-history exercise and
  assert it is still the live exercise.

Change 3:
- Tapping a catalogue row adds the exercise and returns the re-rendered body
  rather than a redirect.
- The create-from-query path creates the exercise, adds it, and leaves
  `muscle_group` null.

Two existing tests reference this area in `test_gym_routes_smoke.py`:
`test_deload_scales_the_suggestion_for_an_exercise_added_mid_session` and
`test_seeded_suggestion_snaps_to_the_exercises_real_stack_stops`. Both use
exercises **with** history, so neither pins the behaviour being changed. The
first carries a stale docstring claiming "gym_add_session_exercise creates none
either", which stopped being true when that route started seeding; correct it
while nearby.

### Manual (python-playwright at 390×844)

The full freestyle path end to end, on a fresh account with an empty catalogue:

1. Start a freestyle workout.
2. Create two exercises from the search sheet without leaving it.
3. Type a weight rather than stepping to it.
4. Log three sets on the first exercise and confirm the screen does not advance
   after the first.
5. Finish and save as a template; start it again and confirm the second run
   seeds from history, not from the defaults.

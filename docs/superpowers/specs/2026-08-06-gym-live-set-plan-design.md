# Gym Tracker — The Plan On The Chip, And When To Add Weight

**Date:** 2026-08-06
**Status:** approved design, not yet implemented

## Why

The live workout screen shows a row of set chips. A finished set wears its
result — `35,0 × 11`. An unfinished one says `Satz 2` and nothing else, even
though the weight and reps it is going to be performed at are already sitting
in the row, prefilled from the last time this exercise was trained.

So the lifter standing at the machine can see what they have done and not what
they are about to do. Deciding whether today is the day to add weight means
remembering last week, which is the one thing a tracker exists to stop.

Two changes, one small and one a judgement:

1. An open chip shows its planned numbers instead of its ordinal.
2. An exercise whose last session went easy says so, before the first set.

## The Chip

An open chip renders the prefilled `weight × reps` of its own set, formatted
like every other weight in this app (German decimal comma, `35,0 × 9`).

Done and planned stay apart the way they already do — a done chip is filled,
an open one is an outline — with the planned numbers additionally set in the
muted foreground the outline chip already uses for its label. The chip's
ordinal moves into the `aria-label` (`"Satz 2, geplant 35,0 kg mal 9"`), which
is where a done chip's ordinal already lives; on screen, position in the row
is the ordinal, unchanged from today.

The chip about to be performed (`is-now`) shows its numbers too. They also
appear in the big steppers directly below it, which is redundant — but a chip
row where one chip is the odd one out reads as a bug, and the whole point is
to see the shape of the session at a glance.

A set whose weight is 0 (a bodyweight set) renders `0,0 × 10`. That is what
the app already shows everywhere else for such a set; this is not the place to
invent an exception.

## The Signal

A badge on the live exercise card: **Bereit**, followed by the sentence of
evidence below. It renders as its own full-width line above the set chips, in
the same slot as the neighbouring `Stagniert` line and for the same reason —
it is advice about the numbers about to be set, so it belongs above the
workspace, not under the confirm button. It does not sit beside the exercise
name: the sentence is far too long for a chip next to an `<h2>`.

It appears when, in the last session that counts, at least **two** sets were
performed at that session's **heaviest weight** for at least **10 reps**.

Each part of that rule earns its place:

- **The last session that counts** is the most recent non-deload one. A deload
  is deliberately light, so two easy sets at its top weight are the expected
  outcome, not evidence of readiness — `progression_rows()` already draws this
  line for every other judgement in the module and this reuses it.
- **The same slot in the workout order**, through the existing `_scoped()`
  helper. Exercise order decides how fatigued you were, so a first-slot session
  is not evidence about a seventh-slot one. `_scoped()` falls back to all
  positions when the slot holds fewer than two sessions, because answering "no
  idea" is worse than answering from a different slot; the badge inherits that
  rule rather than adding a second one.
- **That session's heaviest weight**, not an all-time best: the question is
  whether the working weight has become easy, and a ramp-up set at a lighter
  weight says nothing about that.
- **Two sets**, not one: one good set is a good set. Two is a pattern.
- **Ten reps** is the app's own definition of a full set — `DELOAD_REPS` is 10,
  and the rep-range figures treat 10+ as the endurance end of a working set.

Today's session is never part of the evidence. The badge answers "what did last
time tell me", and the sets being logged right now are the thing it is advising
about.

The badge names no NEXT weight and changes no prefilled value. It is a reminder
of what happened, not a prescription — the lifter taps `+` if they agree. It
does name the evidence, the way the neighbouring `Stagniert` line names its
count: *„Bereit — letztes Mal 2 Sätze auf 35,0 kg mit 10+ Wdh."*, and `kg je
Seite` on a unilateral exercise, matching every other weight on this screen.
A bare badge would make the lifter go looking for the reason it appeared.

It renders only on the live exercise card, not on the queue rows beneath it.
The queue is an overview; seven badges at once is decoration, and the decision
is made at the machine.

**Naming the evidence honestly.** `_scoped()`'s slot lens (no staleness
cutoff, falls back across positions) and the chips' own prefill lens
(`routes._last_session_exercise`, which drops a stale slot after
`ROLLING_WINDOW_DAYS` in favour of the most recent session at any position)
can legitimately disagree once a slot's history goes stale — the badge is
answering "was the last time in THIS slot easy", the chips are answering
"what should I load RIGHT NOW". That divergence is left alone on purpose. What
is not left alone is the sentence claiming to be about *the* last time when it
is not: `ready_for_more` also reports whether its evidence session is the
newest session in the rows it was given, at any position. The badge says
*„Letztes Mal …"* only when it is; otherwise it says *„Zuletzt in diesem Slot
…"*, naming the same numbers without asserting they were the most recent
thing trained.

**Retiring itself once today has already answered.** "That weight went easy"
is only useful advice while that weight is still what the lifter is about to
lift. Right after `ready_for_more` is computed, the route compares its
evidence weight against the heaviest weight already planned across today's
own sets for this exercise; if today's planned top is heavier, the badge does
not render at all — reworded evidence would still be arguing with the chips
underneath it. The comparison is one-sided (`>`, not `!=`): a ramp-up whose
first chip is lighter than the evidence must still see the badge, since
nothing about today has answered the question yet.

## Where The Code Goes

`stats.ready_for_more(rows, position=None)`, a pure function beside the other
judgements, fed by the `PerformedExercise` rows the live route already loads.
Those rows carry only completed sets, which is exactly the input this rule
wants.

It returns `None` when the rule does not fire, and otherwise the evidence the
badge quotes: `{'sets': 2, 'weight': 35.0, 'is_latest': True}` — how many sets
qualified, the weight they were performed at, and whether that evidence
session is also the newest session in the rows it was given, at any position.
A bool would force the template to re-derive numbers the function already
computed; `is_latest` exists for the same reason `sets` and `weight` do — so
the template states a fact the function already checked instead of assuming
one.

The route passes the flag into the live template. No new query: the live screen
already loads this exercise's history for the suggestion and record logic.

## Testing

`ready_for_more` is pure, so its rule is testable directly:

- two sets at the top weight with 10 and 11 reps → `{'sets': 2, 'weight': ...}`
- two sets at the top weight with 9 reps → `None`
- one set at the top weight with 12 reps, one lighter set with 12 → `None`
- the qualifying session is a deload, the one before it is not → judged on the
  earlier one
- three qualifying sets at a different position, fewer than two sessions in
  this slot → fires, via the `_scoped()` fallback
- three qualifying sets at a different position, two or more sessions in this
  slot that do not qualify → `None`
- no history at all → `None`

Each test states the number it asserts on, not merely that a boolean came back.

The chip change gets a rendering test: an open set's planned numbers appear in
the markup, a done set's actual numbers still do, and the ordinal is still
reachable in the `aria-label` of both.

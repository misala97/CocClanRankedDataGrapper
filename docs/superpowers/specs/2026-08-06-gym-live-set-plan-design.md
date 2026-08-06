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

A badge on the live exercise card, beside the exercise name: **Bereit für
mehr**.

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

The badge names no weight and changes no prefilled value. It is a reminder of
what happened, not a prescription — the lifter taps `+` if they agree.

It renders only on the live exercise card, not on the queue rows beneath it.
The queue is an overview; seven badges at once is decoration, and the decision
is made at the machine.

## Where The Code Goes

`stats.ready_for_more(rows, position=None) -> bool`, a pure function beside the
other judgements, fed by the `PerformedExercise` rows the live route already
loads. Those rows carry only completed sets, which is exactly the input this
rule wants.

The route passes the flag into the live template. No new query: the live screen
already loads this exercise's history for the suggestion and record logic.

## Testing

`ready_for_more` is pure, so its rule is testable directly:

- two sets at the top weight with 10 and 11 reps → true
- two sets at the top weight with 9 reps → false
- one set at the top weight with 12 reps, one lighter set with 12 → false
- the qualifying session is a deload, the one before it is not → judged on the
  earlier one
- three qualifying sets at a different position, fewer than two sessions in
  this slot → true via the `_scoped()` fallback
- three qualifying sets at a different position, two or more sessions in this
  slot that do not qualify → false
- no history at all → false

Each test states the number it asserts on, not merely that a boolean came back.

The chip change gets a rendering test: an open set's planned numbers appear in
the markup, a done set's actual numbers still do, and the ordinal is still
reachable in the `aria-label` of both.

# Gym Tracker — Export Schema v2 and the Equipment Facts Behind It

**Date:** 2026-08-06
**Status:** approved design, not yet implemented

## Why

An external coaching tool reads the gym tracker's JSON export. Today that export
carries what the app happens to store, which leaves the reader guessing at the
two things it most needs: what the logged weight number physically means, and
what the machine can actually be loaded to. A recommendation of "next time 42 kg"
is worthless on a stack that only stops at 37 and 45, and a dumbbell press logged
as 30 is either 30 or 60 kg of work depending on a flag the export never sends.

Export v2 closes that gap. It is a schema break (`schema_version: 2`) rather than
an additive patch, because one field is renamed and the reader is expected to
switch over in one step.

## What The App Learns To Store

Two orthogonal facts per exercise, plus two numbers:

| Field | Values | Meaning |
|---|---|---|
| `equipment` | `dumbbell`, `plate_loaded`, `stack` | how the resistance is loaded |
| `is_unilateral` | bool (already exists) | the logged number is one side's load |
| `bar_weight` | kg, optional | dead weight already included in the logged number |
| `stack_kg` | list of kg, optional | the real stops of an uneven stack |

Volume doubles when and only when `is_unilateral` is true. That rule is already
implemented (`stats.set_volume`) and does not change — which is the point of
choosing this decomposition over a single `weight_convention` enum. Not one
existing number in Statistik or Verlauf moves.

`weight_convention`, which the export contract requires, is **derived at export
time** rather than stored:

| equipment | unilateral | exported `weight_convention` |
|---|---|---|
| `dumbbell` | yes | `per_dumbbell` |
| `plate_loaded` / `stack` | yes | `per_side` |
| any | no | `total` |

The contract's fourth value, `per_arm`, is never emitted. It would have meant
"one side at a time, so the rep count is per arm and the exercise takes twice as
long" — a real distinction, but one nothing in this app or the coaching tool acts
on today. Adding it later costs one checkbox.

`barbell` is likewise absent from `equipment`. Military Press is a loaded bar,
which is `plate_loaded` with `bar_weight = 20` — the bar is dead weight included
in the logged number, which is exactly what `bar_weight` says. A separate
equipment value would encode the same fact twice.

Two more fields per exercise, unrelated to loading:

- `secondary_muscle_groups` — a list drawn from the existing `MUSCLE_GROUPS`
  tuple, so a push session's triceps work is visible to anything counting volume
  per muscle.
- `weight_increment` — already exists and already holds correct production
  values, but is NULL-means-default on several rows. The export does not send
  the raw column: it sends `stats.resolve_increment(weight_increment,
  is_unilateral)` — the stored value when there is one, otherwise the app's
  own fallback (halved when the exercise is unilateral) — under the field
  name `increment_kg`. Sending the raw `null` would leave the coaching tool
  guessing a step the app already knows; sending the resolved value keeps its
  recommendation in agreement with the app's own stepper instead of
  contradicting it.

## Seed Values

Set by migration for every user's catalogue, matched by exercise name. The same
physical machines in the same gym, so a per-user answer would be the same answer
three times. Names absent from a user's catalogue are silently skipped.

| Exercise | equipment | bar_weight | secondary |
|---|---|---|---|
| Bench Press (Dumbbell) | dumbbell | — | Trizeps, Schultern |
| Biceps Curl (Rotating) | dumbbell | — | — |
| Hammer Curl (Dumbbell) | dumbbell | — | — |
| Chest Press (Machine, Lying) | plate_loaded | — | Trizeps, Schultern |
| Preacher Curl (Machine, Good) | plate_loaded | — | — |
| Lat Pulldown (Single Arm, Hauptbahnhof) | plate_loaded | — | Bizeps |
| Military Press | plate_loaded | 20 | Trizeps |
| T Bar Row (Standing) | plate_loaded | — | Bizeps |
| T Bar Row (Lying) | plate_loaded | — | Bizeps |
| Chest Fly (Machine) | stack | — | — |
| Lateral Raise (Machine, Good) | stack | — | — |
| Triceps Pushdown (Cable, EZ Bar) | stack | — | — |
| Triceps Extension (Cable, Overhead) | stack | — | — |
| Seated Row (Machine, Good) | stack | — | Bizeps |
| Lat Pulldown Kabelzug | stack | — | Bizeps |
| Reverse Fly (Machine) | stack | — | — |
| Preacher Curl Bilateral | stack | — | — |

`is_unilateral` is **not** part of the seed. Production already holds the correct
flags (six exercises true), and the migration must not second-guess them —
overwriting one would silently halve or double that exercise's entire history in
every statistic.

Exercises not listed keep the column default `stack` and no bar weight. That is a
guess, and the edit form is where it gets corrected.

## What Sessions Learn To Store

- `WorkoutSession.bodyweight_kg` — optional, one number per session. Deliberately
  not a separate daily weigh-in log: the useful question is what the lifter
  weighed *on the day of this session*, and anything more is a second feature.
- `WorkoutSession.notes` — free text.
- `SessionExercise.notes` — free text.
- `SessionExercise.pain` — a boolean, one tap. Flags a twinge without forcing the
  lifter to describe it mid-set.

The workout start path stays exactly as fast as it is today. Every one of these
inputs lives behind an existing disclosure on the session page, never as a step
between "start" and "first set".

Set timestamps need nothing new: `SessionSet.completed_at` already records when a
set actually landed. It becomes `finished_at` in the export, `null` for a set
that was never ticked -- or, for any set logged before `completed_at` existed,
one that predates set timestamps regardless of whether it was ticked.

## Export v2 Shape

The route stays id-picked. Verlauf hands it a list of session ids; the 30/90-day
presets are a client-side bulk-check, and no date range ever reaches the server.
So `range` is **derived** from the sessions actually exported — first and last
`started_at` as dates, both `null` when the selection is empty — and
`requested_session_ids` stays alongside it, because it is the only record of what
was asked for versus what came back.

```json
{
  "schema_version": 2,
  "exported_at": "2026-08-06T18:00:00Z",
  "range": { "from": "2026-07-24", "to": "2026-08-06" },
  "requested_session_ids": [31, 32, 33],
  "sessions": [
    {
      "id": 33,
      "name": "HBF Push 06.08.2026",
      "template_name": "HBF Push",
      "started_at": "2026-08-06T09:30:00Z",
      "finished_at": "2026-08-06T11:02:00Z",
      "deload": false,
      "deload_pct": null,
      "bodyweight_kg": 96.8,
      "notes": "nach 8h Schicht",
      "exercises": [
        {
          "exercise_id": 12,
          "exercise_name": "Military Press",
          "muscle_group": "Schultern",
          "secondary_muscle_groups": ["Trizeps"],
          "equipment": "plate_loaded",
          "weight_convention": "total",
          "bar_weight": 20,
          "increment_kg": 2.5,
          "stack_kg": null,
          "position": 4,
          "replaces": null,
          "replaced_by": null,
          "rest_seconds": 150,
          "notes": "",
          "pain": false,
          "skipped": false,
          "sets": [
            { "position": 1, "weight": 35.0, "reps": 11, "completed": true,  "finished_at": "2026-08-06T10:14:21Z" },
            { "position": 2, "weight": 35.0, "reps": 10, "completed": true,  "finished_at": "2026-08-06T10:17:40Z" },
            { "position": 3, "weight": 35.0, "reps": 8,  "completed": false, "finished_at": null }
          ]
        }
      ]
    }
  ]
}
```

Rules:

- Every key is always present. A missing value is `null` or `[]`, never omitted.
- `increment_kg` and `stack_kg` are mutually exclusive. When an exercise has stack
  steps, `increment_kg` exports as `null` and the steps carry the answer.
- `replaces` / `replaced_by` keep emitting exercise **names**, unchanged from v1.
- `deload` replaces v1's `is_deload` — same value, contract name. `deload_pct`
  survives beside it, because how deep a deload went is not recoverable from a
  boolean.
- Timestamps are ISO 8601 UTC with a trailing `Z`, matching v1.
- An absent note exports differently depending on where it lives: the session
  `notes` field stays `null` when absent, while the exercise `notes` field
  exports as `""` (pinned by `""` in the sample payload above). The two
  fields are not interchangeable — do not normalize one to match the other.

## Weight Suggestions On An Uneven Stack

`stack_kg` earns its place by changing what the app proposes, not just what it
exports. Where a suggested or deloaded weight is currently rounded to a multiple
of `weight_increment` anchored at the working weight, an exercise carrying stack
steps snaps to the nearest real step instead.

For this gym that changes nothing today — every stack here steps evenly (5 or 8
kg), and the existing anchor-to-working-weight fix already handles the offset 8 kg
family correctly. It exists so that the first genuinely uneven machine entered
into the form starts computing correctly the same day, instead of quietly
prescribing a weight that cannot be selected.

Exercises without stack steps keep today's increment path unchanged.

## User Interface

Mobile-first, built from the components already on these pages.

**Exercise edit form (`uebungen.html`)** — gains Art (three options), Stangengewicht
(number, optional), Stack-Stufen (comma-separated, shown only for Art = stack),
and Sekundärmuskeln (multi-select over `MUSCLE_GROUPS`). The existing unilateral
checkbox stays where it is.

**Session header (`session_detail.html`)** — Körpergewicht and a session note,
inside a collapsed disclosure. Editable at any point during or after the workout.

**Per exercise, inside a session** — a note field and a pain toggle, inside the
per-exercise disclosure that already exists. The pain toggle is one tap and needs
no text.

## Testing

`tests/test_gym_export.py`, new:

- the generated payload matches the v2 contract key-for-key, including keys whose
  value is `null`
- the `weight_convention` derivation matrix, all six combinations
- `increment_kg` / `stack_kg` mutual exclusion
- `finished_at` is `null` for a set that was never ticked, and for any set
  logged before `completed_at` existed -- `completed: true` with
  `finished_at: null` is real pre-migration data, not an impossible state
- `range` derives from the exported sessions, and is `{null, null}` for an empty
  selection

Route tests cover the new form fields persisting, and that a session with no
bodyweight, no notes and no pain flag still exports every key.

The migration is one-shot and was verified by hand against the live catalogue;
no automated seed test exists for it.

## Delivery

Migration is a single reversible revision. Downgrade drops the added columns and
leaves `is_unilateral` and every existing value untouched.

Closing step: generate a real export over the last 14 days and read it back.

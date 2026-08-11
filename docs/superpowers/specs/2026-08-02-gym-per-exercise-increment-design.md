# Gym Tracker — Per-exercise weight increment

**Date:** 2026-08-02
**Feature:** `personal_apps` / gym
**Status:** design approved, ready for planning

---

## 1. Problem

Every weight in the app moves in 2.5 kg steps — 1.25 kg when the exercise is
flagged unilateral. That constant is hardcoded in three places: the `+`/`−`
stepper on the live session screen, `stats._next_weight()` (the progression
suggestion shown after a stalled lift), and `stats.deload_weight()` (which
floors a deload target onto that grid).

Real equipment does not agree on one step. Dumbbells go up in 2 kg, a selectorised
machine's stack often moves in 9 kg, a plate-loaded machine matches the bar at
2.5 kg. On anything but the barbell the app therefore dials weights that cannot
be loaded, suggests a next weight that does not exist, and prescribes a deload
target the machine cannot produce.

The step is a property of the equipment, so it belongs on the exercise — exactly
where `Exercise.default_rest_seconds` already lives.

## 2. Goals

1. Store a weight increment per exercise, editable from the surfaces the owner is
   already on when the wrong step becomes obvious.
2. Have all three consumers — stepper, progression suggestion, deload rounding —
   read that one value.
3. Leave every untouched exercise behaving exactly as it does today.

## 3. Non-goals

- **No per-session override.** Rest time has three tiers (Exercise → Template →
  SessionExercise) because how long you rest genuinely varies by day. A machine's
  stack does not. One tier only: no `TemplateExercise`/`SessionExercise` column, no
  capture-on-template-save, no override control.
- **No visible step indicator on the live screen.** The buttons stay `−` and `+`.
  A machine's step is learned in one tap, and the number is visible in the sheet
  where it is set. `PRODUCT.md` treats the live screen as the one surface operated
  without thinking about the app; a changing number on its two most-hit controls
  works against that.
- **No reps increment.** The reps stepper stays at 1.
- **No bulk backfill editor.** NULL is a correct, permanent state; the catalogue
  gets filled in as each exercise is next trained.
- **No non-uniform stacks.** A machine going 5/10/20/30 is not representable by a
  single number and is out of scope.

---

## 4. Data model

One nullable column on `Exercise` (`gym_exercises`), one Alembic revision, **no
backfill**:

```python
# models.py, Exercise
weight_increment = db.Column(db.Float, nullable=True)  # smallest loadable jump on this equipment; NULL falls back
```

`Float`, matching `SessionSet.weight`. Named `weight_increment` rather than
`default_weight_increment` — the `default_` prefix on `default_rest_seconds`
marks it as the seed for a per-session value, and this feature deliberately has
no second tier for it to be the default *for*.

NULL is the intended resting state, not a migration gap: it means "use the
fallback", so every exercise that is never edited keeps today's exact numbers.

## 5. The resolution rule

One function, in `stats.py`, taking plain values rather than an ORM object so
`stats.py` stays pure:

```python
DEFAULT_INCREMENT = 2.5   # the smallest pair of plates on most bars


def resolve_increment(increment, is_unilateral):
    """The smallest loadable jump for one exercise.

    An explicit per-exercise value is taken literally: it is already the number
    that moves when you tap, per side when the lift is unilateral (the live
    screen labels that field `kg je Seite`). Halving survives only as the
    fallback, so nothing changes for an exercise that has no value set.
    """
    if increment:                                   # 0 is not a usable step
        return increment
    return DEFAULT_INCREMENT / 2 if is_unilateral else DEFAULT_INCREMENT
```

The truthiness guard collapses NULL and 0 to the same fallback deliberately: a
step of zero would freeze the stepper.

No other module re-implements this. Templates in particular receive a resolved
number and never branch on `is_unilateral` themselves.

## 6. Consumers

`_next_weight()` and `deload_weight()` currently take `is_unilateral` for the sole
purpose of picking a step. Both swap that parameter for a resolved `increment`
float; every caller resolves first.

```python
def _next_weight(weight, increment):
    return weight + increment


def deload_weight(weight, pct, increment):
    if weight <= 0:
        return weight
    return max(increment, math.floor(weight * pct / 100.0 / increment) * increment)
```

| Consumer | Change |
| --- | --- |
| `templates/gym/_session_live.html:159` | `data-step` receives the resolved value from the route context. The `{{ 1.25 if ... else 2.5 }}` expression and the comment above it both go. |
| `stats.py:587` (`suggested_weight`) | `PerformedExercise` gains `weight_increment: Optional[float] = None`, defaulted so existing constructions keep working. Populated at `routes.py:364`. |
| `routes.py:247` (deload prefill) | Already loads the `Exercise`; resolve there instead of passing `is_unilateral`. |
| `routes.py:1202` (deload toggle) | Already walks `session_exercise.exercise`; same change. |

`deload_weight`'s grid is anchored at 0, which stays correct for a stack machine:
90 kg at 70 % with a 9 kg step floors to 63, a real stack position. The `max()`
floor also keeps its meaning — a light weight can never round to zero.

The stepper JS at `session_detail.html:356` is already generic (`parseFloat(field.dataset.step)`)
and needs no change. `data-decimals` stays at `1`, so an integer step still reads
`24,0` — consistent with every other weight the app prints.

## 7. Where it is set

Three forms, all writing `Exercise.weight_increment`. The input is
`type="number" step="0.25" min="0"` with placeholder `2,5`; submitting it empty
stores NULL. Parsing goes through the existing `_to_float` helper
(`routes.py:63`) with a comma-to-dot normalisation, so a value typed as `2,5`
survives even if the field ever degrades to text.

1. **Exercise meta sheet** — `exercise_detail.html:306`, a new `Schrittweite (kg)`
   field directly after `Standard-Pause (Sek.)`. Handled by the existing
   `gym_update_exercise` route.
2. **Übungen add-form** — `uebungen.html:174`, the same field beside the rest
   input, so a new exercise can carry its step from creation.
3. **In-session exercise sheet** — `session_detail.html:236`. A single-input form
   in its own `sheet__group`, posting to a new `gym_update_exercise_increment`
   route, submitting implicitly on Enter exactly like the rest form above it.
   This is the moment of discovery: the step is wrong while you are standing at
   the machine, and fixing it should not mean leaving the workout.

**Scope must be visible in the session sheet.** The `Pause` field immediately
above is per-session; this one is per-exercise and permanent. Two adjacent
inputs with identical styling and opposite lifetimes is a trap, so the increment
sits in a separate `sheet__group` under the caption
`Gilt für die Übung, nicht nur heute.`

## 8. Testing

Seven test functions in `tests/test_gym_stats.py` (nine call sites) pass the
`is_unilateral` boolean positionally to `deload_weight`; all are updated to pass
an increment instead. The unilateral cases (`deload_weight(20.0, 70, True) ==
13.75`) become explicit-increment cases and keep their expected values.

New coverage:

- The fallback matrix on `resolve_increment`: NULL → 2.5; NULL + unilateral →
  1.25; explicit → returned literally; explicit + unilateral → returned literally,
  **not** halved; 0 → fallback.
- `_next_weight` with a 9 kg step, and `deload_weight` flooring onto a 9 kg grid.
- A route test posting the increment from the session sheet and asserting the
  `Exercise` row changed and the `SessionExercise` did not.
- A render assertion that `data-step` in the live block carries the exercise's
  configured value, and the fallback when it has none.

## 9. Risks

- **Silent behaviour change for exercises given a value.** Setting an increment
  changes what the deload prescribes and what the stagnation advice suggests, not
  just what the buttons do. That is the point of §1, but it means the number is
  worth getting right per exercise rather than approximating.
- **Historical weights are not re-gridded.** Sets logged before an exercise got
  its real increment stay where they are, so the first tap after setting a 9 kg
  step moves from whatever was last logged, not from a stack position. Correct —
  the grid is anchored to history, not to zero — but the first jump on a
  mis-logged exercise may land off-stack until one weight is dialled by hand.

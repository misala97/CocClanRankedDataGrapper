# Gym Cold-Start Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a workout usable when nothing has been logged yet — freestyle sessions and the first run of a new template.

**Architecture:** Three independent changes against one root cause (an exercise with no history produces no plan, and the live screen assumes a plan exists). Task 1 is server-side and makes a plan always exist, which retires the advance-after-one-set bug without touching the live rule. Task 2 makes the steppers typeable. Task 3 collapses the add-exercise sheet into one search field that doubles as the create path. Tasks are ordered by dependency but each ships on its own.

**Tech Stack:** Flask + SQLAlchemy + Jinja2, vanilla JS (no framework, no build step), pytest against the local dev database, python-playwright for the client-side checks.

**Spec:** `docs/superpowers/specs/2026-08-07-gym-cold-start-design.md`

## Global Constraints

- Branch: `dev_personal`. Do not merge to `main` as part of this plan.
- App is German throughout. All user-visible strings in German; decimals render with a comma (`82,5`), never a dot.
- `personal_apps` runs locally on **port 5001**, not 5000. Scratchpad scripts need `PYTHONPATH=.` from the `personal_apps` directory.
- Tests run against the real local dev database. It is disposable dev data, but every fixture must clean up the rows it creates.
- The gym app is multi-user and exercises are per-user. Never query `Exercise` unscoped — use the existing `my_exercises()` / `owned_exercise()` helpers.
- `.claude/skills/` is never committed.
- No new dependencies. No build step. Vanilla JS only.
- `sheet__pane`, `sheet__switch`, `sheet__back` and `sheet__hint` are **also used by the per-exercise replace sheet** (`templates/gym/session_detail.html:412-428`). Task 3 stops using them in the add sheet but must not delete their CSS or the `data-show-pane` handler.

---

## File Structure

| File | Responsibility | Tasks |
|------|----------------|-------|
| `personal_apps/features/gym/stats.py` | The three default-plan constants, next to `DEFAULT_INCREMENT` and `DELOAD_REPS` | 1 |
| `personal_apps/features/gym/routes.py` | `_seeded_sets` no-history branch; pass the constants into the session template context | 1 |
| `personal_apps/templates/gym/_session_live.html` | Read the constants instead of repeating `20.0` / `8` | 1 |
| `personal_apps/templates/gym/session_detail.html` | Typed-entry handler; the rewritten add sheet and its script | 2, 3 |
| `personal_apps/static/gym/gym.css` | Styles for the inline number input and the search rows | 2, 3 |
| `personal_apps/tests/test_gym_cold_start.py` | New suite: seeding defaults, the advance rule, the create-from-search path | 1, 3 |
| `personal_apps/tests/test_gym_routes_smoke.py` | Fix one stale docstring | 1 |

---

### Task 1: A plan always exists

**Files:**
- Modify: `personal_apps/features/gym/stats.py` (near line 99, after `DEFAULT_INCREMENT`)
- Modify: `personal_apps/features/gym/routes.py:292-335` (`_seeded_sets`) and the `render_template` call for `session_detail` (around line 982-1016)
- Modify: `personal_apps/templates/gym/_session_live.html:157-163`
- Modify: `personal_apps/tests/test_gym_routes_smoke.py:726-729` (stale docstring only)
- Test: `personal_apps/tests/test_gym_cold_start.py` (create)

**Interfaces:**
- Produces: `stats.DEFAULT_PLAN_SETS: int = 3`, `stats.DEFAULT_PLAN_REPS: int = 8`, `stats.DEFAULT_PLAN_WEIGHT: float = 20.0`
- Produces: `_seeded_sets(session_, exercise_id, position) -> list[SessionSet]` now returns `DEFAULT_PLAN_SETS` uncompleted `SessionSet` rows (positions 1..3, `weight=DEFAULT_PLAN_WEIGHT`, `reps=DEFAULT_PLAN_REPS`, `base_weight=None`, `base_reps=None`) when `_last_full_performance` yields nothing. Unchanged on the history branch.
- Produces: template context names `default_plan_weight`, `default_plan_reps` in `session_detail.html`'s render context.

- [ ] **Step 1: Write the failing tests**

Create `personal_apps/tests/test_gym_cold_start.py`:

```python
"""The cold-start path: a workout where nothing has been logged before.

Every test here builds its own throwaway exercise with NO history, which is
the condition the whole suite is about -- an exercise the lifter has never
performed produces no seeded sets, and before this suite existed the live
screen had no behaviour for that.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def virgin_session():
    """An active session with no exercises, plus one exercise with no history.

    Deliberately NOT derived from the dev database's real data: the point is an
    exercise nothing has ever been logged against, which no existing row can be
    relied on to be.
    """
    from extensions import db
    from models import Exercise, WorkoutSession
    with flask_app.app_context():
        exercise = Exercise(name='pytest cold start lift', muscle_group='Brust',
                            user_id=_admin_id())
        db.session.add(exercise)
        db.session.flush()

        live = WorkoutSession(name='pytest cold start live',
                              started_at=dt.datetime.utcnow(),
                              user_id=_admin_id())
        db.session.add(live)
        db.session.commit()
        ids = (live.id, exercise.id)
    yield ids
    with flask_app.app_context():
        live_id, exercise_id = ids
        doomed = db.session.get(WorkoutSession, live_id)
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()


def test_an_exercise_with_no_history_arrives_with_a_default_plan(client, virgin_session):
    """It used to arrive with nothing at all, which is what made the first
    logged set also the last: with no planned sets, one completed set meant
    every set was completed."""
    from extensions import db
    from models import SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'exercise_id': str(exercise_id)})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert [(s.position, s.weight, s.reps, s.completed) for s in se.sets] == [
            (1, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
            (2, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
            (3, stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False),
        ]


def test_logging_one_set_does_not_advance_past_a_default_planned_exercise(client, virgin_session):
    """The bug this whole task exists for. `_live_context` calls an exercise
    finished when every set it has is completed; with no planned sets the first
    confirmation both created and completed the list, so each exercise got
    exactly one set before the screen moved on."""
    from extensions import db
    from models import SessionExercise
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        first_set_id = sorted(se.sets, key=lambda s: s.position)[0].id
        se_id = se.id

    client.post(f'/gym/set/{first_set_id}/toggle_complete',
                data={'completed': '1', 'weight': '60.0', 'reps': '8'})

    html = client.get(f'/gym/session/{live_id}').get_data(as_text=True)
    # The live panel names its own session-exercise in data-se-id; if the screen
    # had advanced there would be nothing left to be live and the panel would
    # render the "Noch keine Übung" empty state instead.
    assert f'<section class="live" data-se-id="{se_id}">' in html
    assert 'Noch keine Übung' not in html


def test_a_deload_does_not_scale_an_invented_default(client, virgin_session):
    """There is no working weight to take a percentage of. Scaling the default
    would present a fabricated prescription as a real one."""
    from extensions import db
    from models import SessionExercise, WorkoutSession
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, live_id)
        session_.is_deload = True
        session_.deload_pct = 70
        db.session.commit()

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})

    with flask_app.app_context():
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert {s.weight for s in se.sets} == {stats.DEFAULT_PLAN_WEIGHT}
        assert {s.base_weight for s in se.sets} == {None}
        assert {s.reps for s in se.sets} == {stats.DEFAULT_PLAN_REPS}


def test_un_skipping_a_no_history_exercise_restores_the_default_plan(client, virgin_session):
    """Un-skip re-seeds through the same helper, so it gets the default too."""
    from extensions import db
    from models import SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    client.post(f'/gym/session/{live_id}/exercises/add',
                data={'exercise_id': str(exercise_id)})
    with flask_app.app_context():
        se_id = SessionExercise.query.filter_by(session_id=live_id).one().id

    client.post(f'/gym/session-exercise/{se_id}/skip')
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.skipped is True
        assert se.sets == []

    client.post(f'/gym/session-exercise/{se_id}/skip')
    with flask_app.app_context():
        se = db.session.get(SessionExercise, se_id)
        assert se.skipped is False
        assert len(se.sets) == stats.DEFAULT_PLAN_SETS


def test_the_first_run_of_a_new_template_gets_the_default_plan(client, virgin_session):
    """Half the reason this work exists. A template stores an ordered list of
    exercises and no numbers at all, so on the day it is created every exercise
    in it has no history -- gym_start seeds through the same helper and used to
    produce a session of empty exercises."""
    from extensions import db
    from models import SessionExercise, TemplateExercise, WorkoutSession, WorkoutTemplate
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        # The fixture's session is in the way: gym_start redirects to the
        # running workout instead of starting a second one.
        running = db.session.get(WorkoutSession, live_id)
        running.finished_at = dt.datetime.utcnow()

        template = WorkoutTemplate(name='pytest brand new template',
                                   user_id=_admin_id())
        template.exercises.append(
            TemplateExercise(exercise_id=exercise_id, position=1))
        db.session.add(template)
        db.session.commit()
        template_id = template.id

    started_id = None
    try:
        response = client.post('/gym/start', data={'template_id': str(template_id)})
        assert response.status_code in (302, 303)

        with flask_app.app_context():
            started = (WorkoutSession.query
                       .filter_by(user_id=_admin_id(), finished_at=None)
                       .order_by(WorkoutSession.id.desc()).first())
            assert started is not None, 'gym_start did not create a session'
            started_id = started.id
            se = SessionExercise.query.filter_by(session_id=started_id).one()
            assert [(s.weight, s.reps, s.completed) for s in se.sets] == [
                (stats.DEFAULT_PLAN_WEIGHT, stats.DEFAULT_PLAN_REPS, False)
            ] * stats.DEFAULT_PLAN_SETS
    finally:
        with flask_app.app_context():
            if started_id is not None:
                doomed = db.session.get(WorkoutSession, started_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            doomed_template = db.session.get(WorkoutTemplate, template_id)
            if doomed_template is not None:
                db.session.delete(doomed_template)
                db.session.commit()


def test_reordering_a_no_history_exercise_keeps_a_plan(client, virgin_session):
    """Reorder clears and re-derives pending sets for the new slot. Through the
    same helper, so the exercise must come back with a plan rather than with
    nothing -- the guard that protects logged work (`not any(s.completed)`) is
    unchanged and is not what this checks."""
    from extensions import db
    from models import Exercise, SessionExercise
    from features.gym import stats
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        second = Exercise(name='pytest cold start lift two',
                          muscle_group='Rücken', user_id=_admin_id())
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(second_id)})
        with flask_app.app_context():
            rows = (SessionExercise.query.filter_by(session_id=live_id)
                    .order_by(SessionExercise.position).all())
            reversed_ids = [se.id for se in reversed(rows)]

        client.post(f'/gym/session/{live_id}/exercises/reorder',
                    json={'order': reversed_ids})

        with flask_app.app_context():
            for se in SessionExercise.query.filter_by(session_id=live_id).all():
                assert len(se.sets) == stats.DEFAULT_PLAN_SETS, \
                    f'{se.id} came back from reorder with {len(se.sets)} sets'
    finally:
        with flask_app.app_context():
            for se in SessionExercise.query.filter_by(exercise_id=second_id).all():
                db.session.delete(se)
            db.session.commit()
            doomed = db.session.get(Exercise, second_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()


def test_history_still_wins_over_the_default(client, virgin_session):
    """The default is a fallback, not a replacement: an exercise that HAS been
    performed must still seed from what was actually done."""
    from extensions import db
    from models import SessionExercise, SessionSet, WorkoutSession
    live_id, exercise_id = virgin_session

    with flask_app.app_context():
        past = WorkoutSession(name='pytest cold start history',
                              started_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              finished_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                              user_id=_admin_id())
        past_se = SessionExercise(exercise_id=exercise_id, position=1)
        past_se.sets = [SessionSet(position=1, weight=77.5, reps=6, completed=True),
                        SessionSet(position=2, weight=77.5, reps=6, completed=True)]
        past.exercises.append(past_se)
        db.session.add(past)
        db.session.commit()
        past_id = past.id

    try:
        client.post(f'/gym/session/{live_id}/exercises/add',
                    data={'exercise_id': str(exercise_id)})
        with flask_app.app_context():
            se = (SessionExercise.query
                  .filter_by(session_id=live_id).one())
            assert [(s.weight, s.reps) for s in sorted(se.sets, key=lambda s: s.position)] \
                == [(77.5, 6), (77.5, 6)]
    finally:
        with flask_app.app_context():
            doomed = db.session.get(WorkoutSession, past_id)
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_cold_start.py -v
```

Expected: it errors first with `AttributeError: module 'features.gym.stats' has no attribute 'DEFAULT_PLAN_WEIGHT'` — the constants land in Step 3. Once they exist, `test_history_still_wins_over_the_default` PASSES (it already holds) and the other six FAIL: the seeding ones with `assert [] == [(1, 20.0, 8, False), ...]`, and `test_logging_one_set_does_not_advance_past_a_default_planned_exercise` because the panel renders `Noch keine Übung`.

If it is easier to see the real failures, do Step 3 first and re-run — the constants alone change no behaviour.

- [ ] **Step 3: Add the constants**

In `personal_apps/features/gym/stats.py`, directly after the `DEFAULT_INCREMENT = 2.5` block (line 99):

```python
# What an exercise with no history at all plans for. A template stores only an
# ordered list of exercises -- no set count, no weight, no reps -- so the first
# run of a NEW template hits this too, not just a freestyle workout. Before
# these existed such an exercise arrived with no sets, and the live screen (which
# assumes a plan throughout) called it finished the moment one set was logged.
#
# Three sets is the shape almost every plan starts at. The weight is a
# placeholder and is expected to be wrong -- it is cheap to correct because the
# steppers' readout can be typed into (see session_detail.html).
DEFAULT_PLAN_SETS = 3
DEFAULT_PLAN_REPS = 8
DEFAULT_PLAN_WEIGHT = 20.0
```

- [ ] **Step 4: Return the default from `_seeded_sets`**

In `personal_apps/features/gym/routes.py`, replace the early return in `_seeded_sets` (currently lines 308-310):

```python
    seeded = _last_full_performance(exercise_id, position=position)
    if not seeded:
        return []
```

with:

```python
    seeded = _last_full_performance(exercise_id, position=position)
    if not seeded:
        # No history: a plain default plan, NOT a deload-scaled one. A deload is
        # a percentage of a real working weight, and there isn't one here --
        # scaling an invented number would dress a placeholder up as a
        # prescription. base_weight stays None for the same reason: there is no
        # working weight for gym_toggle_deload to restore this to.
        return [
            SessionSet(position=j, weight=stats.DEFAULT_PLAN_WEIGHT,
                       reps=stats.DEFAULT_PLAN_REPS, completed=False)
            for j in range(1, stats.DEFAULT_PLAN_SETS + 1)
        ]
```

Also extend the docstring's first line so it stops promising history is the only source:

```python
    """Pending sets for `exercise_id` in `position` -- pre-filled from history
    when there is any (honouring the session's deload), and a plain default plan
    when there is none.
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_gym_cold_start.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Run the full suite for regressions**

```bash
cd personal_apps && python -m pytest tests/ -q
```

Expected: all pass. If `test_deload_scales_the_suggestion_for_an_exercise_added_mid_session` or `test_seeded_suggestion_snaps_to_the_exercises_real_stack_stops` fail, stop — they use exercises *with* history and must be unaffected; a failure there means the history branch was changed by mistake.

- [ ] **Step 7: Retire the duplicated literals in the template**

In `personal_apps/features/gym/routes.py`, in the `render_template('gym/session_detail.html', ...)` call (around line 982), add two context names alongside the existing ones:

```python
        default_plan_weight=stats.DEFAULT_PLAN_WEIGHT,
        default_plan_reps=stats.DEFAULT_PLAN_REPS,
```

In `personal_apps/templates/gym/_session_live.html`, replace lines 162-163:

```jinja
    {% set pair_weight = next_set.weight if next_set else (last_done.weight if last_done else (start.weight if start else 20.0)) %}
    {% set pair_reps = next_set.reps if next_set else (last_done.reps if last_done else (start.reps if start else 8)) %}
```

with:

```jinja
    {# The last link of each chain is the same default _seeded_sets falls back to,
       read from stats rather than re-typed, so the two cannot drift. It is close
       to unreachable now -- every path into a session seeds a plan -- but an
       exercise can still reach zero sets by having them deleted individually. #}
    {% set pair_weight = next_set.weight if next_set else (last_done.weight if last_done else (start.weight if start else default_plan_weight)) %}
    {% set pair_reps = next_set.reps if next_set else (last_done.reps if last_done else (start.reps if start else default_plan_reps)) %}
```

- [ ] **Step 8: Fix the stale docstring**

In `personal_apps/tests/test_gym_routes_smoke.py`, the docstring of `test_deload_scales_the_suggestion_for_an_exercise_added_mid_session` (lines 726-729) claims `gym_add_session_exercise` "creates none either". That stopped being true when the route started seeding, and is doubly wrong now. Replace the docstring with:

```python
    """gym_add_session_exercise seeds from history through _seeded_sets, so the
    sets it creates must already carry the deload -- history is recorded at full
    working weight, and handing it back untouched would silently undo the deload
    the lifter just asked for. This exercise HAS history; the no-history default
    is a separate path, covered in test_gym_cold_start.py.
    """
```

- [ ] **Step 9: Verify the page renders and re-run everything**

```bash
cd personal_apps && python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add personal_apps/features/gym/stats.py personal_apps/features/gym/routes.py personal_apps/templates/gym/_session_live.html personal_apps/tests/test_gym_cold_start.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "fix(gym): give an exercise with no history a default plan

A template stores only an ordered list of exercises, so the first run of a
new one lands in the same place a freestyle workout does: _seeded_sets finds
no history and returns nothing, and the live screen assumes a plan exists
throughout. With no planned sets, the first confirmed set both created and
completed the list, so every exercise got exactly one set before the screen
moved on.

Three open sets at a placeholder weight instead. That retires the
advance-after-one-set bug without touching _live_context, and gives the
chips, the rail fill and the tick strip a denominator again. A deload gets
the plain default rather than a scaled one -- there is no working weight to
take a percentage of.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Tap the number to type it

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html:497-515` (the steppers script) and `_session_live.html:192-211` (the two `.field-num` blocks)
- Modify: `personal_apps/static/gym/gym.css:1799-1819` (the `.field-num` block)
- Verify: `personal_apps/scratchpad/verify_typed_entry.py` (create, not committed)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `.field-num__val` becomes a `<button type="button" data-role="display">`. Its `data-role` is unchanged, so the existing stepper handler that writes `display.textContent` keeps working untouched.

- [ ] **Step 1: Make the readout a button**

In `personal_apps/templates/gym/_session_live.html`, replace the weight readout (line 194):

```jinja
          <span class="field-num__val" data-role="display">{{ ("%.1f"|format(pair_weight)).replace(".", ",") }}</span>
```

with:

```jinja
          <button type="button" class="field-num__val" data-role="display"
                  aria-label="Gewicht eingeben">{{ ("%.1f"|format(pair_weight)).replace(".", ",") }}</button>
```

and the reps readout (line 203):

```jinja
          <span class="field-num__val" data-role="display">{{ pair_reps }}</span>
```

with:

```jinja
          <button type="button" class="field-num__val" data-role="display"
                  aria-label="Wiederholungen eingeben">{{ pair_reps }}</button>
```

Update the comment above the pair (lines 178-182) — it currently states "No keyboard ever opens during a workout", which stops being true:

```jinja
    {# The two numbers. The steppers carry the value in a hidden input and the
       readout is text, so no keyboard opens for the ordinary case -- the weight
       step is the exercise's own increment, already resolved by the route (see
       stats.resolve_increment), so a prefilled number is one or two taps from
       right. That only holds while the prefill is CLOSE. On an exercise with no
       history it starts at the default placeholder, where stepping to a real
       working weight is dozens of taps, so the readout itself is tappable and
       opens a numeric field. Same escape when you move to a different machine
       mid-session. #}
```

- [ ] **Step 2: Add the typed-entry handler**

In `personal_apps/templates/gym/session_detail.html`, directly after the steppers handler (after line 515, before the `---- motion ----` comment), add:

```javascript
// ---- typing a number instead of stepping to it ----------------------------
// The steppers are right when the prefilled number is already close, which is
// the ordinary case and stays one tap. It is wrong when it is not: an exercise
// with no history starts at the default placeholder, and stepping from there to
// a real working weight is dozens of taps. So the readout opens a field.
//
// The hidden input remains the single source of truth -- this writes into the
// same [data-role="value"] the steppers write into, and never submits. The
// confirm button still commits the set.
function openNumberEntry(display) {
    var field = display.closest('.field-num');
    var input = field.querySelector('[data-role="value"]');
    var decimals = parseInt(field.dataset.decimals, 10) || 0;
    if (field.querySelector('.field-num__entry')) { return; }

    var entry = document.createElement('input');
    entry.type = 'text';
    entry.inputMode = decimals ? 'decimal' : 'numeric';
    entry.className = 'field-num__entry';
    entry.value = decimals
        ? parseFloat(input.value || 0).toFixed(decimals).replace('.', ',')
        : String(parseInt(input.value, 10) || 0);
    entry.setAttribute('aria-label', display.getAttribute('aria-label'));

    function commit(save) {
        if (!entry.isConnected) { return; }
        if (save) {
            // Accept both separators: the app renders commas, phone keypads
            // vary on which one they offer, and rejecting either would be a
            // silent no-op at the exact moment the lifter is trying to correct
            // a number.
            var parsed = parseFloat(entry.value.replace(',', '.'));
            if (isFinite(parsed) && parsed >= 0) {
                // Not snapped to the exercise's increment. The increment governs
                // stepping; typing is exact by intent -- that is what it is for.
                input.value = decimals ? parsed : Math.round(parsed);
                display.textContent = decimals
                    ? parsed.toFixed(decimals).replace('.', ',')
                    : String(Math.round(parsed));
            }
        }
        entry.replaceWith(display);
    }

    entry.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(true); }
        else if (e.key === 'Escape') { e.preventDefault(); commit(false); }
    });
    entry.addEventListener('blur', function () { commit(true); });

    display.replaceWith(entry);
    entry.focus();
    entry.select();
}

document.addEventListener('click', function (e) {
    var display = e.target.closest && e.target.closest('.field-num__val');
    if (display) { openNumberEntry(display); }
});
```

- [ ] **Step 3: Style the entry field to sit exactly where the readout sat**

In `personal_apps/static/gym/gym.css`, update the `.field-num__val` rule (line 1806) and add the entry rule after it:

```css
.field-num__val {
  font-family: var(--font-display); font-size: var(--num-md); font-weight: var(--w-max);
  letter-spacing: var(--track-num); line-height: 1; font-variant-numeric: tabular-nums;
  /* It is a button now, so it has to be told not to look like one. */
  background: none; border: 0; padding: 0; color: inherit; cursor: pointer;
}
/* Replaces the readout in place, so it inherits the same metrics -- swapping to
   a field must not move anything else in the panel. */
.field-num__entry {
  font-family: var(--font-display); font-size: var(--num-md); font-weight: var(--w-max);
  letter-spacing: var(--track-num); line-height: 1; font-variant-numeric: tabular-nums;
  inline-size: 100%; min-inline-size: 0; text-align: center;
  background: none; border: 0; padding: 0; color: var(--live);
  outline: none;
}
```

Also fix the section comment above `.pair` (line 1799), which says the same now-false thing as the template did:

```css
/* ---- the two numbers: stepped by default, typed when the prefill is wrong ---- */
```

- [ ] **Step 4: Start the app**

```bash
cd personal_apps && python -c "from app import app; app.run(port=5001)"
```

Leave it running in the background. If port 5001 is already serving, reuse it — but restart it, because a running server caches templates.

- [ ] **Step 5: Write the playwright check**

Create `personal_apps/scratchpad/verify_typed_entry.py`:

```python
"""Drives the real page at 390x844 (iPhone 16e) and proves the readout can be
typed into. Run from personal_apps with PYTHONPATH=. -- it mints a signed
session cookie rather than logging in with a password."""
import datetime as dt
import sys

from playwright.sync_api import sync_playwright

from app import app as flask_app
from extensions import db
from flask.sessions import SecureCookieSessionInterface
from models import AppUser, Exercise, WorkoutSession

with flask_app.app_context():
    admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
    exercise = Exercise(name='playwright typed entry lift', muscle_group='Brust',
                        user_id=admin.id)
    db.session.add(exercise)
    live = WorkoutSession(name='playwright typed entry',
                          started_at=dt.datetime.utcnow(), user_id=admin.id)
    db.session.add(live)
    db.session.commit()
    session_id, exercise_id, admin_id = live.id, exercise.id, admin.id

serializer = SecureCookieSessionInterface().get_signing_serializer(flask_app)
cookie = serializer.dumps({'user_id': admin_id})

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.context.add_cookies([{
            'name': 'session', 'value': cookie,
            'domain': 'localhost', 'path': '/',
        }])
        page.goto(f'http://localhost:5001/gym/session/{session_id}')

        # Add the exercise, then confirm the default plan rendered three chips.
        page.click('.sheet-open[data-sheet="sheet-add-exercise"]')
        page.select_option('#exercise-select', str(exercise_id))
        page.click('#add-exercise-form button[type="submit"]')
        page.wait_for_selector('.live__name')
        assert page.locator('.set').count() == 3, 'expected three planned chips'

        # Type a weight instead of stepping to it.
        page.click('.field-num:first-child .field-num__val')
        page.fill('.field-num__entry', '82,5')
        page.keyboard.press('Enter')
        page.wait_for_selector('.field-num:first-child .field-num__val')
        shown = page.inner_text('.field-num:first-child .field-num__val')
        stored = page.get_attribute('.field-num:first-child [data-role="value"]', 'value')
        assert shown == '82,5', f'readout shows {shown!r}'
        assert float(stored) == 82.5, f'hidden input holds {stored!r}'

        # Escape must leave the value alone.
        page.click('.field-num:first-child .field-num__val')
        page.fill('.field-num__entry', '5')
        page.keyboard.press('Escape')
        assert page.inner_text('.field-num:first-child .field-num__val') == '82,5'

        # Log one set and confirm the screen does NOT advance (Task 1's rule,
        # re-checked through the real UI rather than the route).
        page.click('#set-confirm')
        page.wait_for_timeout(600)
        assert page.locator('.live__name').inner_text() == 'playwright typed entry lift'

        page.screenshot(path='scratchpad/typed_entry.png', full_page=True)
        browser.close()
    print('OK')
finally:
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, exercise_id)
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()
```

- [ ] **Step 6: Run it**

```bash
cd personal_apps && PYTHONPATH=. python scratchpad/verify_typed_entry.py
```

Expected: prints `OK`. Then **open `personal_apps/scratchpad/typed_entry.png` with the Read tool and actually look at it** — confirm the panel did not shift when the field replaced the readout, and that the typed value is legible at phone size. A passing assertion does not prove it looks right.

- [ ] **Step 7: Confirm the dev database is clean**

```bash
cd personal_apps && PYTHONPATH=. python -c "
from app import app
from models import Exercise, WorkoutSession
with app.app_context():
    print('sessions:', WorkoutSession.query.filter(WorkoutSession.name.like('playwright%')).count())
    print('exercises:', Exercise.query.filter(Exercise.name.like('playwright%')).count())
"
```

Expected: both `0`.

- [ ] **Step 8: Run the test suite**

```bash
cd personal_apps && python -m pytest tests/ -q
```

Expected: all pass — this task is client-side, so nothing should move.

- [ ] **Step 9: Commit**

```bash
git add personal_apps/templates/gym/_session_live.html personal_apps/templates/gym/session_detail.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): let the set steppers' readout be typed into

The keyboard-free steppers are right when the prefilled number is already
close -- the increment is the exercise's own, so one or two taps land it, and
that case is untouched. They silently assume closeness. On an exercise with
no history the prefill is a placeholder, and stepping to a real working
weight is dozens of taps.

Tapping the readout swaps it for a numeric field; Enter or blur commits into
the same hidden input the steppers write, Escape cancels. Not snapped to the
increment -- the increment governs stepping, typing is exact by intent. Also
the escape hatch when you move to a different machine mid-session.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: One search sheet

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html:229-279` (the add sheet) and its script region (near `refreshBody`, line 773)
- Modify: `personal_apps/static/gym/gym.css` (append a `.exadd` block near the other sheet styles, around line 2446)
- Test: `personal_apps/tests/test_gym_cold_start.py` (extend)
- Verify: `personal_apps/scratchpad/verify_add_search.py` (create, not committed)

**Interfaces:**
- Consumes: `stats.DEFAULT_PLAN_SETS` from Task 1 (every added exercise now arrives with a plan, which is what makes adding several in a row worth doing).
- Produces: `#exadd-list` — the container the refresh swaps so the sheet stays in step with the session. `refreshBody(html)` gains a second responsibility: if the incoming document has an `#exadd-list`, replace the current one.
- No route changes. `gym_add_session_exercise` already branches on `exercise_id` vs `new_exercise_name` (`routes.py:1044-1057`), and its redirect is followed by `fetch`, so `performMutation` receives the re-rendered page either way.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_cold_start.py`:

```python
def test_creating_an_exercise_from_the_search_leaves_no_muscle_group(client, virgin_session):
    """The search sheet's create path posts a name and nothing else -- the
    muscle-group select is gone from it, because mid-workout is the worst moment
    to ask and the field is optional and editable later in Übungen. Pinned
    because the route still accepts a muscle_group it will now never receive."""
    from extensions import db
    from models import Exercise, SessionExercise
    from features.gym import stats
    live_id, _ = virgin_session

    response = client.post(f'/gym/session/{live_id}/exercises/add',
                           data={'new_exercise_name': 'pytest search created lift'})
    assert response.status_code in (302, 303)

    with flask_app.app_context():
        created = Exercise.query.filter_by(name='pytest search created lift',
                                           user_id=_admin_id()).one()
        assert created.muscle_group is None
        se = SessionExercise.query.filter_by(session_id=live_id).one()
        assert se.exercise_id == created.id
        # A brand-new exercise has no history by construction, so it must arrive
        # with the default plan -- this is the exact first-time-user path.
        assert len(se.sets) == stats.DEFAULT_PLAN_SETS
        db.session.delete(se)
        db.session.commit()
        db.session.delete(created)
        db.session.commit()
```

- [ ] **Step 2: Run it to verify it passes already**

```bash
cd personal_apps && python -m pytest tests/test_gym_cold_start.py::test_creating_an_exercise_from_the_search_leaves_no_muscle_group -v
```

Expected: PASS. This one pins existing route behaviour that the UI change depends on — it is a regression guard, not a driver. The rest of this task is client-side and is driven by the playwright check in Step 7.

- [ ] **Step 3: Replace the add sheet**

In `personal_apps/templates/gym/session_detail.html`, replace the whole `sheet-add-exercise` dialog (lines 229-279) with:

```jinja
<dialog class="sheet" id="sheet-add-exercise" aria-labelledby="sheet-add-exercise-title">
  <div class="sheet__head">
    <h2 class="sheet__title" id="sheet-add-exercise-title">Übung hinzufügen</h2>
    <button type="button" class="sheet__close" data-close>Fertig</button>
  </div>
  <div class="sheet__body">
    {# One field, two jobs. The sheet used to be two panes -- pick an existing
       lift, or switch modes and invent one -- which meant a first-time user with
       an empty catalogue had to understand the split before they could log
       anything. Here the create path is simply what the list offers when the
       search matches nothing, so an empty catalogue reaches it without choosing
       a mode at all.

       The sheet also stays open: it used to close and full-page-render on every
       add, so building a six-exercise workout was six round trips. Rows post in
       place through the same performMutation the live panel uses. #}
    <input type="search" id="exadd-search" class="input" autocomplete="off"
           placeholder="Übung suchen oder anlegen" aria-label="Übung suchen oder anlegen"
           aria-controls="exadd-list">
    <div class="exadd" id="exadd-list" data-add-url="{{ url_for('gym.gym_add_session_exercise', session_id=session.id) }}">
      {# Rendered server-side and re-rendered by every refresh, so the "schon
         drin" counts are the session's real contents rather than a tally the
         client keeps and could get wrong. #}
      {% for e in exercises %}
      {% set in_session = session.exercises|selectattr('exercise_id', 'equalto', e.id)|list|length %}
      <button type="button" class="exadd__row" data-exercise-id="{{ e.id }}"
              data-name="{{ e.name|lower }}">
        <span class="exadd__name">{{ e.name }}</span>
        {% if e.muscle_group %}<span class="exadd__group">{{ e.muscle_group }}</span>{% endif %}
        {% if in_session %}<span class="exadd__in">{{ in_session }}× drin</span>{% endif %}
      </button>
      {% endfor %}
      <button type="button" class="exadd__row exadd__row--new" id="exadd-create" hidden>
        <span class="exadd__name">Anlegen: <b id="exadd-create-name"></b></span>
        <span class="exadd__group">neue Übung</span>
      </button>
      <p class="exadd__empty" id="exadd-empty" {% if exercises %}hidden{% endif %}>
        Tippe einen Namen — die Übung wird angelegt und bleibt in deiner Liste.
      </p>
    </div>
  </div>
</dialog>
```

Note what this deliberately drops: the `<select>`, both `sheet__pane` wrappers, the `sheet__switch` / `sheet__back` mode buttons, the `sheet__hint`, and the muscle-group field. **Do not delete their CSS or the `data-show-pane` handler** — the per-exercise replace sheet still uses all of them.

- [ ] **Step 4: Keep the sheet list in step with the session**

In `personal_apps/templates/gym/session_detail.html`, inside `refreshBody` (line 773), after the `if (fresh && old) { ... }` block and before `startRestTick();`, add:

```javascript
    // The sheet lives outside #session-body, so the wholesale swap above never
    // touches it -- and its rows carry "schon drin" counts that go stale the
    // moment one is tapped. Swap the list too, then re-apply whatever the
    // search field is currently filtering by.
    var freshList = doc.getElementById('exadd-list');
    var oldList = document.getElementById('exadd-list');
    if (freshList && oldList) {
        oldList.replaceWith(freshList);
        filterAddList();
    }
```

- [ ] **Step 5: Add the sheet's script**

In `personal_apps/templates/gym/session_detail.html`, after the typed-entry handler added in Task 2, add:

```javascript
// ---- the add-exercise search ----------------------------------------------
// Filtering is client-side over a list the server already rendered: a lifter's
// catalogue is tens of rows, not thousands, and a round trip per keystroke on
// gym wifi would be worse than useless.
function filterAddList() {
    var search = document.getElementById('exadd-search');
    var list = document.getElementById('exadd-list');
    if (!search || !list) { return; }
    var q = search.value.trim().toLowerCase();
    var hits = 0;
    list.querySelectorAll('.exadd__row:not(.exadd__row--new)').forEach(function (row) {
        var match = !q || row.dataset.name.indexOf(q) !== -1;
        row.hidden = !match;
        if (match) { hits += 1; }
    });

    // The create row is what the list offers when nothing matches -- which is
    // every search on an empty catalogue, so a first-time user never has to
    // find a separate "new exercise" mode.
    var create = document.getElementById('exadd-create');
    var name = document.getElementById('exadd-create-name');
    if (create && name) {
        create.hidden = !q || hits > 0;
        name.textContent = search.value.trim();
    }
    var empty = document.getElementById('exadd-empty');
    if (empty) { empty.hidden = !!q || hits > 0; }
}

document.addEventListener('input', function (e) {
    if (e.target.id === 'exadd-search') { filterAddList(); }
});

// One row tap = one add, posted in place so the sheet stays open. The list is
// re-rendered by refreshBody, which is what updates the "schon drin" counts.
const addRowsInFlight = new WeakSet();

document.addEventListener('click', function (e) {
    var row = e.target.closest && e.target.closest('.exadd__row');
    if (!row) { return; }
    var list = document.getElementById('exadd-list');
    var search = document.getElementById('exadd-search');
    if (!list) { return; }
    if (addRowsInFlight.has(row)) { return; }

    var data = new FormData();
    if (row.id === 'exadd-create') {
        var typed = search ? search.value.trim() : '';
        if (!typed) { return; }
        data.append('new_exercise_name', typed);
    } else {
        data.append('exercise_id', row.dataset.exerciseId);
    }

    addRowsInFlight.add(row);
    row.classList.add('is-busy');
    performMutation(list.dataset.addUrl, {
        method: 'POST', body: data, credentials: 'same-origin',
    }).finally(function () {
        addRowsInFlight.delete(row);
        row.classList.remove('is-busy');
        // Clearing the search after a create is the difference between "added"
        // and "still looks like it did not take": the create row would otherwise
        // sit there offering to create the same name again.
        if (search && row.id === 'exadd-create') { search.value = ''; filterAddList(); }
    });
});
```

- [ ] **Step 6: Style the rows**

In `personal_apps/static/gym/gym.css`, after the `.sheet__pane .field--full` rule (line 2446), append:

```css
/* ---- the add-exercise search list ---- */
/* A list, not a <select>: the select could not be searched, could not show what
   is already in the session, and hid a catalogue behind a native picker. */
#exadd-search { inline-size: 100%; }
.exadd { display: flex; flex-direction: column; margin-top: var(--sp-3); }
.exadd__row {
  display: flex; align-items: center; gap: var(--sp-3);
  min-block-size: var(--tap); inline-size: 100%;
  padding: var(--sp-2) 0; text-align: start;
  background: none; border: 0; border-block-end: 1px solid var(--edge);
  color: var(--ink);
}
.exadd__row[hidden] { display: none; }   /* the [hidden] display trap: .exadd__row sets display:flex, which wins over the UA's [hidden] rule unless it is restated */
.exadd__row:active { background: var(--raised); }
.exadd__row.is-busy { opacity: 0.5; }
.exadd__name { flex: 1; min-inline-size: 0; font-weight: var(--w-med); }
.exadd__group { font-size: var(--t-meta); color: var(--unlit); }
.exadd__in { font-size: var(--t-meta); color: var(--live); font-weight: var(--w-semi); }
.exadd__row--new .exadd__name b { color: var(--live); }
.exadd__row--new[hidden] { display: none; }
.exadd__empty { font-size: var(--t-meta); color: var(--unlit); padding: var(--sp-3) 0; }
.exadd__empty[hidden] { display: none; }
```

- [ ] **Step 7: Write the playwright check**

Create `personal_apps/scratchpad/verify_add_search.py`:

```python
"""The full first-time-user path at 390x844: an empty catalogue, two exercises
created from the search without leaving the sheet, three sets logged on the
first without the screen advancing. Run from personal_apps with PYTHONPATH=."""
import datetime as dt

from playwright.sync_api import sync_playwright

from app import app as flask_app
from extensions import db
from flask.sessions import SecureCookieSessionInterface
from models import AppUser, Exercise, SessionExercise, WorkoutSession

MADE = ['playwright search lift A', 'playwright search lift B']

with flask_app.app_context():
    admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
    live = WorkoutSession(name='playwright search session',
                          started_at=dt.datetime.utcnow(), user_id=admin.id)
    db.session.add(live)
    db.session.commit()
    session_id, admin_id = live.id, admin.id

serializer = SecureCookieSessionInterface().get_signing_serializer(flask_app)
cookie = serializer.dumps({'user_id': admin_id})

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.context.add_cookies([{
            'name': 'session', 'value': cookie,
            'domain': 'localhost', 'path': '/',
        }])
        page.goto(f'http://localhost:5001/gym/session/{session_id}')

        # The empty state offers the add sheet directly.
        page.click('.live .sheet-open[data-sheet="sheet-add-exercise"]')
        page.wait_for_selector('#exadd-search')

        for name in MADE:
            page.fill('#exadd-search', name)
            page.wait_for_selector('#exadd-create:not([hidden])')
            page.click('#exadd-create')
            page.wait_for_function(
                "() => document.getElementById('exadd-search').value === ''")
            # The sheet must still be open -- that is the whole point.
            assert page.is_visible('#exadd-search'), f'sheet closed after {name}'

        page.screenshot(path='scratchpad/add_search_sheet.png')
        page.click('.sheet__close[data-close]')
        page.wait_for_selector('.live__name')

        assert page.inner_text('.live__name') == MADE[0]
        assert page.locator('.set').count() == 3, 'expected the default plan'

        for i in range(3):
            page.click('#set-confirm')
            page.wait_for_timeout(700)
            if i < 2:
                assert page.inner_text('.live__name') == MADE[0], \
                    f'advanced after set {i + 1}'

        # Only after the third does it move on.
        assert page.inner_text('.live__name') == MADE[1]

        page.screenshot(path='scratchpad/add_search_done.png', full_page=True)
        browser.close()
    print('OK')
finally:
    with flask_app.app_context():
        doomed = db.session.get(WorkoutSession, session_id)
        if doomed is not None:
            doomed.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed)
            db.session.commit()
        for name in MADE:
            ex = Exercise.query.filter_by(name=name, user_id=admin_id).first()
            if ex is not None:
                for se in SessionExercise.query.filter_by(exercise_id=ex.id).all():
                    db.session.delete(se)
                db.session.commit()
                db.session.delete(ex)
                db.session.commit()
```

- [ ] **Step 8: Restart the server and run it**

```bash
cd personal_apps && PYTHONPATH=. python scratchpad/verify_add_search.py
```

The server caches templates, so restart it first or the old sheet will still be served. Expected: prints `OK`.

Then **open both PNGs with the Read tool and look at them.** Check the row list is legible at 390px, the "×  drin" marker reads as a count rather than a button, and the create row is distinguishable from a real catalogue row.

- [ ] **Step 9: Confirm the replace sheet still works**

The pane machinery this task stopped using is shared. Verify by hand at `http://localhost:5001/gym/session/<id>`: open a per-exercise sheet, expand "Übung ersetzen", and confirm the "+ Neue Übung anlegen" / "← Vorhandene wählen" switch still toggles.

- [ ] **Step 10: Confirm the dev database is clean**

```bash
cd personal_apps && PYTHONPATH=. python -c "
from app import app
from models import Exercise, WorkoutSession
with app.app_context():
    print('sessions:', WorkoutSession.query.filter(WorkoutSession.name.like('playwright%')).count())
    print('exercises:', Exercise.query.filter(Exercise.name.like('playwright%')).count())
"
```

Expected: both `0`.

- [ ] **Step 11: Run the full suite**

```bash
cd personal_apps && python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 12: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/static/gym/gym.css personal_apps/tests/test_gym_cold_start.py
git commit -m "feat(gym): one search sheet for adding an exercise

The add sheet was a <select> of the whole catalogue in one pane and an
invent-a-new-exercise form in another, and it closed and full-page-rendered
on every add. Building a six-exercise freestyle workout was six round trips;
on an empty catalogue all six also went through the other pane, which asked
for a muscle group mid-workout.

One search field now. Tapping a row adds in place and the sheet stays open,
with the row showing how many times that lift is already in the session.
Typing something that matches nothing turns the top row into 'Anlegen: ...',
so an empty catalogue reaches the create path without anyone choosing a mode.

The pane machinery stays -- the per-exercise replace sheet still uses it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done criteria

- A freestyle session can be built and logged end to end on a phone-sized screen without opening the catalogue page, and without the screen advancing after one set.
- The first run of a brand-new template behaves the same as a later run, minus the history-derived numbers.
- `python -m pytest tests/ -q` passes from `personal_apps`.
- The dev database holds no `playwright%` or `pytest%` rows afterwards.
- Not merged to `main` — the owner validates on a real workout first.

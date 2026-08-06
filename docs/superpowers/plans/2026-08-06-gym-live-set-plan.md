# Live Set Plan And The Add-Weight Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an unfinished set's planned weight and reps on its chip, and badge the live exercise when its last comparable session went easy enough to add weight.

**Architecture:** Task 1 is template-only — the numbers are already on the row, the chip just never rendered them. Task 2 adds one pure function to `features/gym/stats.py` beside the other judgements, wires it into the live route's existing per-exercise loop (which already computes stagnation and record signals from the same rows), and renders it with the markup pattern the neighbouring `Stagniert` line established.

**Tech Stack:** Flask, Jinja templates, pytest, existing `gym.css`.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-08-06-gym-live-set-plan-design.md`. It is authoritative where this plan is silent.
- Work on branch `dev_personal`. Do not merge to `main`.
- Run tests from `personal_apps/`: `PYTHONPATH=. python -m pytest tests/ -q`, against the real local dev MySQL database (service `MySQL80` must be running). 480 tests pass before this plan.
- `features/gym/stats.py` is pure: no Flask, no SQLAlchemy, no queries, no I/O. It must stay that way.
- German UI copy, matching the surrounding tone. Weights render with a decimal comma (`35,0`), never a point.
- Comments explain *why* a decision was made, never *what* the line does.
- Mobile-first. Build from classes already in `static/gym/gym.css`; new CSS needs a justification.
- A unilateral exercise's weight is per side and every surface says so (`kg je Seite`).
- Today's session is never evidence for the badge. The live route already excludes it: `by_exercise` is built with `if row.session_id != session_.id`.

---

### Task 1: The plan on the chip

**Files:**
- Modify: `personal_apps/templates/gym/_session_live.html:93-110` (the set chip loop)
- Test: `personal_apps/tests/test_gym_routes_smoke.py` (extend)

**Interfaces:**
- Consumes: nothing from other tasks. `live_sets` already carries each `SessionSet` with its prefilled `weight` and `reps`.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Read the chip loop before changing it**

Open `personal_apps/templates/gym/_session_live.html` and read lines 80-121 — the comment above the loop explains why the record state says its own name and why the ordinal lives where it does. Your change has to keep both true.

- [ ] **Step 2: Write the failing test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`. Follow the file's existing fixture style — look at how the neighbouring tests build a session and clean it up, and reuse that rather than inventing a second approach.

```python
def test_an_open_chip_shows_the_weight_and_reps_it_is_planned_for(client):
    """The numbers are already on the row, prefilled from last time. A chip
    that says only "Satz 2" makes the lifter at the machine remember last
    week to decide whether to add weight -- which is the thing a tracker
    exists to stop."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Chip Plan', user_id=_admin_id(),
                            muscle_group='Rücken')
        db.session.add(exercise)
        db.session.flush()
        session = WorkoutSession(name='ZZ Chip Plan Session', user_id=_admin_id(),
                                 started_at=dt.datetime.utcnow())
        db.session.add(session)
        db.session.flush()
        se = SessionExercise(session_id=session.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.flush()
        db.session.add(SessionSet(session_exercise_id=se.id, position=1, weight=35.0,
                                  reps=11, completed=True,
                                  completed_at=dt.datetime.utcnow()))
        db.session.add(SessionSet(session_exercise_id=se.id, position=2, weight=35.0,
                                  reps=9, completed=False))
        db.session.commit()
        session_id, exercise_id = session.id, exercise.id

    try:
        html = client.get(f'/gym/session/{session_id}').get_data(as_text=True)
        assert '35,0 × 11' in html, 'the done set still wears its result'
        assert '35,0 × 9' in html, 'the open set now wears its plan'
        assert 'Satz 2, geplant 35,0 kg mal 9' in html, \
            'the ordinal moved into the label, it did not vanish'
    finally:
        with flask_app.app_context():
            row = db.session.get(WorkoutSession, session_id)
            if row is not None:
                db.session.delete(row)
            ex = db.session.get(Exercise, exercise_id)
            if ex is not None:
                db.session.delete(ex)
            db.session.commit()
```

Add whatever imports the file is missing for this (`Exercise`, `WorkoutSession`, `SessionExercise`, `SessionSet`, `db`, `flask_app`, `_admin_id`, `datetime as dt`) at the module top, not inside the function.

- [ ] **Step 3: Run the test to verify it fails**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_routes_smoke.py -k chip_shows -v`
Expected: FAIL on `assert '35,0 × 9' in html` — the open chip currently renders `Satz 2`.

- [ ] **Step 4: Render the plan on the chip**

In `personal_apps/templates/gym/_session_live.html`, replace the button's `aria-label` and its body (currently lines 105-106) with:

```html
                aria-label="{% if is_record %}Satz {{ loop.index }} — Rekord, {{ s.weight }} kg mal {{ s.reps }} — antippen zum Zurücksetzen{% elif s.completed %}Satz {{ loop.index }} erledigt, {{ s.weight }} kg mal {{ s.reps }} — antippen zum Zurücksetzen{% else %}Satz {{ loop.index }}, geplant {{ s.weight }} kg mal {{ s.reps }}{% endif %}">
          {{ ("%.1f"|format(s.weight)).replace(".", ",") }} × {{ s.reps }}
        </button>
```

Both branches now print the same numbers, so the conditional inside the body is gone. Update the block comment above the loop (lines 80-92) to say what the two states now mean — a filled chip is a result, an outlined one is a plan — rather than leaving a comment that describes the old rendering.

- [ ] **Step 5: Run the test to verify it passes**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_routes_smoke.py -k chip_shows -v`
Expected: PASS

- [ ] **Step 6: Prove the test can fail**

Temporarily change the chip body back to `{% if s.completed %}...{% else %}Satz {{ loop.index }}{% endif %}`, run the test, confirm it fails on the open-set assertion, then restore. Record both outputs in your report.

- [ ] **Step 7: Look at it**

Start the app on port 5001 and screenshot the live session at 390×844 with python-playwright (mint the session cookie directly — `tests/conftest.py` shows how `user_id` is set; do not use a browser MCP tool). Confirm: the chips still fit three to a row without wrapping mid-number, a done chip is still visibly different from a planned one, and the `is-now` chip still reads as the current one. Actually open the PNG and look at it before claiming any of that.

- [ ] **Step 8: Run the full suite and commit**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass.

```bash
git add personal_apps/templates/gym/_session_live.html personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): show an open set the numbers it is planned for"
```

---

### Task 2: The add-weight signal

**Files:**
- Modify: `personal_apps/features/gym/stats.py` (new `ready_for_more`, placed after `sessions_since_pr`)
- Modify: `personal_apps/features/gym/routes.py:877-899` (the per-exercise signal loop) and the `render_template` call for the session page
- Modify: `personal_apps/templates/gym/_session_live.html:73-78` (beside the existing `Stagniert` line)
- Modify: `personal_apps/static/gym/gym.css` (a `.live__ready` rule mirroring `.live__stall`)
- Test: `personal_apps/tests/test_gym_stats.py` and `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `stats.PerformedExercise` rows (they carry only completed sets), `stats.progression_rows`, `stats._scoped`, `stats.DELOAD_REPS`.
- Produces: `stats.ready_for_more(rows, position=None) -> dict | None` — `None` when the rule does not fire, otherwise `{'sets': int, 'weight': float}`: how many sets qualified, and the weight they were performed at. Template variable `ready_for_more` (dict or None) on the session page.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_gym_stats.py`. The file already has a `perf()` helper for building `PerformedExercise` rows — read it and use it rather than constructing the dataclass by hand.

```python
def test_two_top_weight_sets_at_ten_reps_say_go_heavier():
    """The rule, in its plainest form: the working weight has become easy."""
    row = perf([(35.0, 10), (35.0, 11), (35.0, 8)])
    assert stats.ready_for_more([row]) == {'sets': 2, 'weight': 35.0}


def test_nine_reps_is_not_enough():
    """DELOAD_REPS is this app's own definition of a full set. Nine is a set
    you finished, not one that had room left in it."""
    row = perf([(35.0, 9), (35.0, 9), (35.0, 9)])
    assert stats.ready_for_more([row]) is None


def test_one_good_top_set_is_not_a_pattern():
    row = perf([(35.0, 12), (30.0, 12), (30.0, 12)])
    assert stats.ready_for_more([row]) is None


def test_only_the_sessions_own_heaviest_weight_counts():
    """A ramp-up set at a lighter weight says nothing about whether the
    working weight is easy, however many reps it ran to."""
    row = perf([(20.0, 15), (20.0, 15), (35.0, 10)])
    assert stats.ready_for_more([row]) is None


def test_a_deload_session_is_not_evidence():
    """Two easy sets at a deload's top weight are the expected outcome, not
    readiness -- so the judgement falls through to the last real session."""
    deload = perf([(25.0, 10), (25.0, 10)], is_deload=True,
                  started_at=dt.datetime(2026, 8, 3), session_id=2)
    real = perf([(35.0, 8), (35.0, 7)],
                started_at=dt.datetime(2026, 7, 27), session_id=1)
    assert stats.ready_for_more([deload, real]) is None


def test_the_newest_qualifying_session_wins():
    older = perf([(30.0, 12), (30.0, 12)],
                 started_at=dt.datetime(2026, 7, 20), session_id=1)
    newer = perf([(35.0, 10), (35.0, 11)],
                 started_at=dt.datetime(2026, 7, 27), session_id=2)
    assert stats.ready_for_more([older, newer]) == {'sets': 2, 'weight': 35.0}


def test_a_thin_slot_falls_back_to_every_position():
    """_scoped()'s own rule: fewer than two sessions in this slot cannot
    support a judgement, and answering from another slot beats answering
    'no idea'."""
    row = perf([(35.0, 10), (35.0, 10)], position=1,
               started_at=dt.datetime(2026, 7, 27), session_id=1)
    assert stats.ready_for_more([row], position=7) == {'sets': 2, 'weight': 35.0}


def test_a_populated_slot_is_judged_on_its_own_sessions():
    """Two sessions in slot 7 is enough to answer from slot 7 alone, so slot
    1's easy session must not leak in."""
    easy_elsewhere = perf([(35.0, 12), (35.0, 12)], position=1,
                          started_at=dt.datetime(2026, 7, 20), session_id=1)
    hard_here_a = perf([(35.0, 6), (35.0, 5)], position=7,
                       started_at=dt.datetime(2026, 7, 24), session_id=2)
    hard_here_b = perf([(35.0, 7), (35.0, 6)], position=7,
                       started_at=dt.datetime(2026, 7, 27), session_id=3)
    rows = [easy_elsewhere, hard_here_a, hard_here_b]
    assert stats.ready_for_more(rows, position=7) is None


def test_no_history_says_nothing():
    assert stats.ready_for_more([]) is None
```

If `perf()` does not accept `started_at` or `session_id`, extend the helper with defaulted parameters rather than writing a second helper.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_stats.py -k ready_for_more -v`
Expected: FAIL — `AttributeError: module 'features.gym.stats' has no attribute 'ready_for_more'`

- [ ] **Step 3: Write the function**

In `personal_apps/features/gym/stats.py`, directly below `sessions_since_pr`:

```python
def ready_for_more(rows, position=None):
    """Whether the last comparable session says the working weight has become
    easy -- two or more sets at that session's own heaviest weight, each run
    to a full set's worth of reps.

    Returns the evidence rather than a bare yes: the badge quotes it, the way
    the stagnation line beside it quotes its count. A lifter who cannot see
    why a nudge appeared has to go looking for the reason.

    "That session's heaviest", not an all-time best: the question is whether
    the weight you are actually working at has room left in it, and a ramp-up
    set says nothing about that. Two sets, not one, because one good set is a
    good set and two is a pattern.

    Deload sessions are excluded (progression_rows): light weight for ten reps
    is what a deload IS, so counting it would leave this permanently lit. The
    position lens and its fallback come from _scoped() -- exercise order
    decides how fatigued you were, and a slot with too little history borrows
    from the others rather than going silent.
    """
    scoped = _scoped(progression_rows(rows), position)
    if not scoped:
        return None
    last = scoped[-1]
    top = max(weight for weight, _ in last.sets)
    qualifying = [reps for weight, reps in last.sets
                  if weight == top and reps >= DELOAD_REPS]
    if len(qualifying) < 2:
        return None
    return {'sets': len(qualifying), 'weight': top}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_stats.py -k ready_for_more -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Wire it into the live route**

In `personal_apps/features/gym/routes.py`, the session-page view already builds `by_exercise` (prior sessions only) and loops over `visible_exercises` inside `if not session_.is_deload:` computing `stagnation_counts` and `record_set_ids`. Read that block and its comment first — it explains why the guard wraps the whole loop.

Add a single value for the live exercise only, computed inside that same guard so a deload session shows no nudge:

```python
    ready_for_more = None
    if not session_.is_deload and live_se is not None:
        # Only the live exercise: the queue below is an overview, and seven
        # badges at once is decoration rather than a decision.
        ready_for_more = stats.ready_for_more(
            by_exercise.get(live_se.exercise_id, []), position=live_se.position)
```

Place it after the existing loop, and pass `ready_for_more=ready_for_more` in the `render_template` call for the session page.

- [ ] **Step 6: Render the badge**

In `personal_apps/templates/gym/_session_live.html`, directly after the existing `{% if live_se.id in stagnation_counts %}` block (which ends at line 78):

```html
    {# Same slot as Stagniert and for the same reason: this is advice about
       the numbers you are about to set, so it belongs above the workspace,
       not under the confirm button. The two never contradict each other --
       stagnation counts sessions without a PR, this one reads the last
       session's reps -- but if both fire, both are worth saying. #}
    {% if ready_for_more %}
    <p class="live__ready">
      <span class="live__ready-lbl">Bereit</span>
      Letztes Mal {{ ready_for_more.sets }} Sätze auf
      {{ ("%.1f"|format(ready_for_more.weight)).replace(".", ",") }} kg{% if live_se.exercise.is_unilateral %} je Seite{% endif %}
      mit {{ min_full_reps }}+ Wdh.
    </p>
    {% endif %}
```

`min_full_reps` is `stats.DELOAD_REPS`, passed into the template from the route in the same `render_template` call (`min_full_reps=stats.DELOAD_REPS`) rather than hardcoded in the markup, so the copy cannot drift from the rule.

- [ ] **Step 7: Style it**

In `personal_apps/static/gym/gym.css`, directly after the `.live__stall-lbl` rule (which ends at line 1737), add the same shape in the live accent:

```css
/* Same shape as .live__stall above, different ink on purpose: a stall is a
   warning and wears --stall-ink, readiness is the good news and wears the
   same accent the chip you are about to perform does. */
.live__ready {
  margin-top: var(--sp-4); padding: var(--sp-3);
  border-radius: var(--r-inset); box-shadow: inset 0 0 0 1px var(--live);
  font-size: var(--t-meta); color: var(--dim); line-height: 1.45;
}
.live__ready-lbl {
  display: block; font-size: var(--t-micro); font-weight: var(--w-bold);
  letter-spacing: var(--track-label); text-transform: uppercase; color: var(--live-ink);
}
```

Before committing to `--live-ink`, check its contrast against the panel background this line sits on. `.set.is-now` uses it on a transparent chip, which is not the same surface. If it does not clear 4.5:1, use `--live` for the label instead and say so in your report.

- [ ] **Step 8: Write the rendering test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`, in the same fixture style as Task 1's test:

```python
def test_the_live_card_badges_an_exercise_that_went_easy_last_time(client):
    """Two sets at last session's top weight with 10+ reps, so the live card
    says so before the first set of today."""
    with flask_app.app_context():
        exercise = Exercise(name='ZZ Ready Lift', user_id=_admin_id(),
                            muscle_group='Rücken')
        db.session.add(exercise)
        db.session.flush()
        past = WorkoutSession(name='ZZ Ready Past', user_id=_admin_id(),
                              started_at=dt.datetime.utcnow() - dt.timedelta(days=7),
                              finished_at=dt.datetime.utcnow() - dt.timedelta(days=7))
        db.session.add(past)
        db.session.flush()
        past_se = SessionExercise(session_id=past.id, exercise_id=exercise.id, position=1)
        db.session.add(past_se)
        db.session.flush()
        for i, reps in enumerate((10, 11), start=1):
            db.session.add(SessionSet(session_exercise_id=past_se.id, position=i,
                                      weight=35.0, reps=reps, completed=True,
                                      completed_at=dt.datetime.utcnow() - dt.timedelta(days=7)))
        today = WorkoutSession(name='ZZ Ready Today', user_id=_admin_id(),
                               started_at=dt.datetime.utcnow())
        db.session.add(today)
        db.session.flush()
        today_se = SessionExercise(session_id=today.id, exercise_id=exercise.id, position=1)
        db.session.add(today_se)
        db.session.flush()
        db.session.add(SessionSet(session_exercise_id=today_se.id, position=1,
                                  weight=35.0, reps=10, completed=False))
        db.session.commit()
        ids = (today.id, past.id, exercise.id)

    try:
        html = client.get(f'/gym/session/{ids[0]}').get_data(as_text=True)
        assert 'live__ready' in html
        assert 'Letztes Mal 2 Sätze auf 35,0 kg' in html
    finally:
        with flask_app.app_context():
            for model, row_id in ((WorkoutSession, ids[0]), (WorkoutSession, ids[1]),
                                  (Exercise, ids[2])):
                row = db.session.get(model, row_id)
                if row is not None:
                    db.session.delete(row)
            db.session.commit()
```

- [ ] **Step 9: Run it and prove it can fail**

Run: `PYTHONPATH=. python -m pytest tests/test_gym_routes_smoke.py -k badges_an_exercise -v`
Expected: PASS.

Then delete the `ready_for_more=ready_for_more` argument from the `render_template` call, run the test again, confirm it FAILS, and restore. Record both outputs — a badge test that passes without the route passing the value is not a test.

- [ ] **Step 10: Look at it**

Screenshot the live session at 390×844 with python-playwright, on a session where the badge fires. Confirm the badge and the `Stagniert` line do not collide when both are present, that the badge reads as a nudge rather than a warning, and that nothing pushes the confirm button off-screen. Open the PNG and look at it.

- [ ] **Step 11: Run the full suite and commit**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: all pass.

```bash
git add personal_apps/features/gym/stats.py personal_apps/features/gym/routes.py personal_apps/templates/gym/_session_live.html personal_apps/static/gym/gym.css personal_apps/tests/test_gym_stats.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): say so when last session left room for more weight"
```

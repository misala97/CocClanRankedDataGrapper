# Gym Tracker: Skip / Edit History / Sticky-Bar Fix / Export / Reorder Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship five independent Gym Tracker changes on `dev_personal`: skip-exercise (non-destructive), edit-history values, a sticky-bottom-bar bug fix, a JSON training export, and a reorder-accident lock.

**Architecture:** All five live inside the existing `personal_apps` Flask app's `gym` blueprint (`features/gym/routes.py`, `models.py`, `templates/gym/*.html`, `static/gym/gym.css`). No new blueprints, no new dependencies. One new DB column (`SessionExercise.skipped`) via one Alembic migration; everything else is additive routes/template/CSS/JS changes to files that already exist.

**Tech Stack:** Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), MySQL, vanilla JS (no framework), Jinja2 templates.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-18-gym-tracker-five-features-design.md` — every task below implements one numbered section of it.
- **No automated test suite exists anywhere in this repository** (confirmed: zero `test_*.py`/`*_test.py` files, `pytest` not in any `requirements.txt`). This plan does **not** introduce pytest — that would be a new testing framework choice affecting the whole project, out of scope for a 5-feature plan. Every task's verification step is a concrete, runnable manual check instead (a Python one-liner against the app context, or a browser click-path against the running dev server). Do not silently swap in a test framework.
- UI copy is German throughout (existing convention — "Übung ersetzen", "Übung entfernen", etc.). All new copy in this plan follows that convention.
- DB is MySQL (`personal_apps/app.py`), migrated via `flask db upgrade` (Flask-Migrate/Alembic), migration files in `personal_apps/migrations/versions/`.
- Current Alembic head revision: `b3f9a1d5e7c2` (`add_is_unilateral_to_exercises`). Every new migration in this plan chains off that.
- Branch: `dev_personal`. Commit after every task.
- Existing CSS/JS conventions to follow exactly: buttons use `btn btn-ghost|btn-primary|btn-danger` (+ optional `btn-sm`, `icon-btn`); badges use `.badge` + a modifier (`.badge-active`, `.badge-done`); forms inside `#exercise-cards` are auto-intercepted and AJAX-submitted by the existing global `document.addEventListener('submit', ...)` handler in `session_detail.html` (~line 560) — new forms placed inside that container need **no** new submit-handling JS, they get it for free.

## Local Dev Server Setup (one-time, before Task 1's verification)

`personal_apps/app.py` hardcodes `port=5000` in its `if __name__ == '__main__':` block, which collides with `coc_stats`'s dev server (already registered on port 5000 in `.claude/launch.json`). Use Flask's CLI runner instead, which ignores that block and takes its own `--port`:

- [ ] Add a `personal_apps` entry to `.claude/launch.json` (this repo's dev-server registry), alongside the existing `coc_stats` entry:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "coc_stats",
      "runtimeExecutable": "python",
      "runtimeArgs": ["app.py"],
      "cwd": "coc_stats",
      "port": 5000
    },
    {
      "name": "personal_apps",
      "runtimeExecutable": "flask",
      "runtimeArgs": ["run", "--port", "5001"],
      "cwd": "personal_apps",
      "port": 5001
    }
  ]
}
```

- [ ] Verify: start the `personal_apps` dev server (via the Browser pane's `preview_start {name: "personal_apps"}`, or manually with `cd personal_apps && flask run --port 5001`), then load `http://127.0.0.1:5001/` and confirm the Gym Tracker overview page renders. Log in if prompted (existing account).
- [ ] Commit the `.claude/launch.json` change alone:

```bash
git add .claude/launch.json
git commit -m "chore: register personal_apps dev server on port 5001"
```

---

## Task 1: Migration — `SessionExercise.skipped` column

**Files:**
- Modify: `personal_apps/models.py:207-225` (`SessionExercise` class)
- Create: `personal_apps/migrations/versions/9c3e5a71f2b6_add_skipped_to_session_exercises.py`

**Interfaces:**
- Produces: `SessionExercise.skipped` (bool, default `False`) — consumed by Task 2 (skip/undo route), Task 3 (template badge/UI), Task 6 (export).

- [ ] **Step 1: Add the column to the model**

In `personal_apps/models.py`, inside `class SessionExercise(db.Model):`, add a new line directly after the existing `replaces_id` column (currently line 214):

```python
    replaces_id  = db.Column(db.Integer, db.ForeignKey('gym_session_exercises.id', ondelete='SET NULL'), nullable=True, unique=True)  # set when this row is a mid-workout substitute for another exercise in the same slot; unique so at most one substitute can ever point at a given original
    skipped      = db.Column(db.Boolean, nullable=False, default=False)  # True when this exercise is intentionally not being done this session; the row (and any already-completed sets) is kept as-is so a later "save/update as template" still includes it
```

- [ ] **Step 2: Write the migration**

Create `personal_apps/migrations/versions/9c3e5a71f2b6_add_skipped_to_session_exercises.py`:

```python
"""add skipped to session exercises

Revision ID: 9c3e5a71f2b6
Revises: b3f9a1d5e7c2
Create Date: 2026-07-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c3e5a71f2b6'
down_revision = 'b3f9a1d5e7c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gym_session_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('gym_session_exercises', schema=None) as batch_op:
        batch_op.drop_column('skipped')
```

- [ ] **Step 3: Apply the migration**

Run: `cd personal_apps && flask db upgrade`
Expected: no errors; last line mentions upgrading to `9c3e5a71f2b6`.

- [ ] **Step 4: Verify the column exists**

Run:
```bash
cd personal_apps
python -c "
from app import app
from models import SessionExercise
with app.app_context():
    cols = SessionExercise.__table__.columns.keys()
    assert 'skipped' in cols, f'skipped column missing, got: {cols}'
    print('OK: skipped column present')
"
```
Expected output: `OK: skipped column present`

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/9c3e5a71f2b6_add_skipped_to_session_exercises.py
git commit -m "feat(gym): add skipped column to session exercises"
```

---

## Task 2: Backend — skip/undo route

**Files:**
- Modify: `personal_apps/features/gym/routes.py` — new route inserted directly after `gym_delete_session_exercise` (currently ends at line 599, before `gym_delete_set` at line 602)

**Interfaces:**
- Consumes: `SessionExercise.skipped` (Task 1), `_last_full_performance(exercise_id, position=None)` (already defined at routes.py:133, returns `[{'weight': float, 'reps': int}, ...]`), `SessionSet` model.
- Produces: route `gym.gym_toggle_skip_session_exercise`, URL `/gym/session-exercise/<int:session_exercise_id>/skip` (POST) — consumed by Task 3's template form.

- [ ] **Step 1: Add the route**

Insert into `personal_apps/features/gym/routes.py` directly after the `gym_delete_session_exercise` function (after line 599, before the blank lines preceding `gym_delete_set` at line 602):

```python
@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/skip', methods=['POST'])
@login_required
def gym_toggle_skip_session_exercise(session_exercise_id):
    """Skip: mark this exercise as intentionally not done this session,
    without deleting it -- unlike gym_delete_session_exercise, the row stays
    in session_.exercises, so _template_exercises_from_session still picks
    it up if this session is later saved/updated as a template (no change
    needed there: it already includes every non-substitute row). Toggling
    back off (undo) re-derives pending sets the same way a fresh template
    start does, but only if nothing is left over from before the skip."""
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_ = session_exercise.session
    if session_.finished_at:
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    session_exercise.skipped = not session_exercise.skipped
    if session_exercise.skipped:
        # Drop only the not-yet-confirmed sets -- anything already completed
        # (e.g. 2 of 4 sets done, then the lifter decides to skip the rest)
        # stays untouched, still counting toward that exercise's history.
        for s in list(session_exercise.sets):
            if not s.completed:
                db.session.delete(s)
    elif not session_exercise.sets:
        for j, prev_set in enumerate(_last_full_performance(session_exercise.exercise_id, position=session_exercise.position), start=1):
            session_exercise.sets.append(SessionSet(position=j, weight=prev_set['weight'], reps=prev_set['reps'], completed=False))

    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))
```

- [ ] **Step 2: Verify no import errors**

Run: `cd personal_apps && python -c "from app import app; print('OK: routes import cleanly')"`
Expected: `OK: routes import cleanly`

- [ ] **Step 3: Manual verification against the running dev server**

With the `personal_apps` dev server running (see Local Dev Server Setup) and logged in:
1. Start a workout from any template with at least one exercise (or add one to a nameless workout).
2. Note the exercise's pre-filled suggested weight/reps (if any).
3. `POST` the skip route by submitting a raw form from the browser console, or wait for Task 3 to add the UI button — for this task alone, verify via a Python shell round-trip instead:

```bash
cd personal_apps
python -c "
from app import app
from extensions import db
from models import SessionExercise
with app.app_context():
    se = SessionExercise.query.filter_by(skipped=False).first()
    assert se, 'no SessionExercise to test with -- start a workout first'
    sid = se.id
    print('before:', se.skipped, len(se.sets))
"
```
Then hit the route with a logged-in session's cookies (simplest: this will be re-verified end-to-end with the UI in Task 3 — this step just confirms the route doesn't 500). Skip a full manual curl round-trip here; Task 3's browser-based check is the real end-to-end verification for this route.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/features/gym/routes.py
git commit -m "feat(gym): add skip/undo route for session exercises"
```

---

## Task 3: Frontend — Skip button, badge, and undo state

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html:68-176` (exercise card title area + body)
- Modify: `personal_apps/static/gym/gym.css` — add `.exercise-actions` rule

**Interfaces:**
- Consumes: `se.skipped` (Task 1), route `gym.gym_toggle_skip_session_exercise` (Task 2).

- [ ] **Step 1: Replace the card title/body block**

In `personal_apps/templates/gym/session_detail.html`, replace lines 68–176 (from `<div class="card-title-area">` through the closing `</div>` of `card-body`) with:

```html
                <div class="card-title-area">
                    <h2>{{ se.exercise.name }}</h2>
                    {% if se.skipped %}
                    <span class="badge badge-done">Übersprungen</span>
                    {% elif total_count %}
                    <span class="progress-badge {{ 'all-done' if all_done else '' }}">{{ completed_count }}/{{ total_count }}</span>
                    {% endif %}
                </div>
                <button type="button" class="progress-open-btn" data-exercise-id="{{ se.exercise_id }}" data-position="{{ se.position }}" title="Fortschritt anzeigen">📊</button>
            </div>
            {% if session.finished_at and (se.replaces or se.replaced_by) %}
            <div class="replace-note">
                {% if se.replaces %}🔁 Ersetzt: {{ se.replaces.exercise.name }}{% endif %}
                {% if se.replaces and se.replaced_by %}<br>{% endif %}
                {% if se.replaced_by %}🔁 Ersetzt durch: {{ se.replaced_by.exercise.name }}{% endif %}
            </div>
            {% endif %}
            {% if not session.finished_at %}
            <form method="post" action="{{ url_for('gym.gym_update_session_exercise_rest', session_exercise_id=se.id) }}" class="rest-form" title="Pause in Sekunden -- speichert automatisch">
                <span class="unit">⏱</span>
                <input type="number" name="rest_seconds" min="0" class="num-input-sm" value="{{ se.rest_seconds if se.rest_seconds is not none else '' }}">
                <span class="unit">s</span>
            </form>
            {% endif %}
        </div>
        <div class="card-body">
            {% if se.sets %}
            {% if not session.finished_at and total_count > completed_count %}
            <div class="pending-hint">{{ total_count - completed_count }} Satz{{ 'e' if total_count - completed_count != 1 else '' }} aus letztem Mal -- Werte anpassen und antippen zum Bestätigen</div>
            {% endif %}
            <div class="sets-list">
                {% for s in se.sets %}
                <div class="set-row {{ 'set-done' if s.completed else 'set-pending' }}">
                    <span class="set-index">{{ loop.index }}</span>
                    {% if not session.finished_at %}
                    <form method="post" action="{{ url_for('gym.gym_toggle_set_complete', set_id=s.id) }}" class="set-edit-form">
                        <input type="number" name="weight" step="0.5" min="0" class="num-input-sm" value="{{ s.weight }}">
                        <span class="unit">kg ×</span>
                        <input type="number" name="reps" min="0" class="num-input-sm" value="{{ s.reps }}">
                        <button type="submit" class="set-check {{ 'checked' if s.completed else '' }}" title="{{ 'Erledigt -- antippen zum Zurücksetzen' if s.completed else 'Werte speichern & als erledigt markieren (startet die Pause)' }}">{{ '✓' if s.completed else '' }}</button>
                    </form>
                    <form method="post" action="{{ url_for('gym.gym_delete_set', set_id=s.id) }}">
                        <button type="submit" class="btn btn-ghost icon-btn">✕</button>
                    </form>
                    {% else %}
                    <span class="set-value" data-set-value>{{ s.weight }} kg × {{ s.reps }}</span>
                    <button type="button" class="btn btn-ghost icon-btn edit-set-btn" data-set-id="{{ s.id }}" title="Wert bearbeiten">✏️</button>
                    <form method="post" action="{{ url_for('gym.gym_update_set', set_id=s.id) }}" class="set-edit-form edit-set-form hidden">
                        <input type="number" name="weight" step="0.5" min="0" class="num-input-sm" value="{{ s.weight }}">
                        <span class="unit">kg ×</span>
                        <input type="number" name="reps" min="0" class="num-input-sm" value="{{ s.reps }}">
                        <button type="submit" class="btn btn-ghost icon-btn" title="Speichern">💾</button>
                    </form>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% elif not se.skipped %}
            <div class="empty">Noch keine Sätze protokolliert.</div>
            {% endif %}

            {% if resting_set and not session.finished_at %}
            <div class="rest-bar">
                <div class="rest-bar-top"><span>Pause</span><span class="rest-bar-label" id="rest-bar-label">--:--</span></div>
                <div class="rest-bar-track"><div class="rest-bar-fill" id="rest-fill" data-rest-ends="{{ session.rest_ends_at.isoformat() }}" data-rest-total="{{ se.rest_seconds or se.exercise.default_rest_seconds or 0 }}"></div></div>
            </div>
            {% endif %}

            {% if not session.finished_at %}
            {% if not se.skipped %}
            {% set suggestion = suggestions.get(se.id) %}
            {% if se.id in stagnation_counts %}
            <div class="stagnation-note">💡 {{ stagnation_counts[se.id] }} Workouts ohne neuen e1RM-PR — mehr Gewicht oder Wdh. versuchen (progressive overload)</div>
            {% endif %}
            <form method="post" action="{{ url_for('gym.gym_add_set', session_exercise_id=se.id) }}">
                <div class="form-row">
                    <div class="form-group">
                        <label>Gewicht (kg)</label>
                        <input type="number" name="weight" step="0.5" min="0" class="num-input" required
                               value="{{ suggestion.weight if suggestion else '' }}">
                    </div>
                    <div class="form-group">
                        <label>Wdh.</label>
                        <input type="number" name="reps" min="0" class="num-input" required
                               value="{{ suggestion.reps if suggestion else '' }}">
                    </div>
                    <button type="submit" class="btn btn-primary">Satz hinzufügen</button>
                </div>
            </form>
            {% if suggestion and not se.sets %}
            <div class="empty" style="padding-top:8px">Letzte Leistung: {{ suggestion.weight }} kg × {{ suggestion.reps }}</div>
            {% endif %}
            {% endif %}
            <div class="exercise-actions">
                <form method="post" action="{{ url_for('gym.gym_toggle_skip_session_exercise', session_exercise_id=se.id) }}">
                    <button type="submit" class="btn btn-ghost btn-sm">{{ '↩️ Rückgängig' if se.skipped else '⏭️ Überspringen' }}</button>
                </form>
                <details class="replace-details">
                    <summary class="btn btn-ghost btn-sm">🔁 Übung ersetzen</summary>
                    <form method="post" action="{{ url_for('gym.gym_replace_session_exercise', session_exercise_id=se.id) }}" style="margin-top:8px">
                        <div class="form-row">
                            <div class="form-group grow">
                                <label>Ersatzübung</label>
                                <select name="exercise_id">
                                    <option value="">— Neue Übung —</option>
                                    {% for e in exercises if e.muscle_group == se.exercise.muscle_group and e.id != se.exercise_id %}
                                    <option value="{{ e.id }}">{{ e.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="form-group grow">
                                <label>Name der neuen Übung</label>
                                <input type="text" name="new_exercise_name" placeholder="z.B. Kabelzug">
                            </div>
                            <button type="submit" class="btn btn-primary btn-sm">Ersetzen</button>
                        </div>
                    </form>
                </details>
                <form method="post" action="{{ url_for('gym.gym_delete_session_exercise', session_exercise_id=se.id) }}" data-confirm="Übung aus Workout entfernen?">
                    <button type="submit" class="btn btn-ghost btn-sm">Übung entfernen</button>
                </form>
            </div>
            {% endif %}
        </div>
```

Note what changed vs. the original: the `data-set-value`/`edit-set-btn`/`edit-set-form` additions on the finished-session branch belong to Task 5 — they're included here because they sit inside the same block being replaced; Task 5 only adds the JS/CSS that makes them interactive. Also note the three action buttons (skip/undo, swap, delete) are now grouped in one `.exercise-actions` wrapper instead of three separately-margined siblings.

- [ ] **Step 2: Add the `.exercise-actions` CSS rule**

In `personal_apps/static/gym/gym.css`, add after the `.progress-badge.all-done` rule (currently line 236):

```css
.exercise-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; margin-top: 12px; }
```

- [ ] **Step 3: Manual verification**

With the dev server running and logged in:
1. Start a workout from a template with 2+ exercises.
2. On one exercise card, click "⏭️ Überspringen". Confirm: the card shows an "Übersprungen" badge, the add-set form disappears, and the button now reads "↩️ Rückgängig". If that exercise had pre-filled suggested sets, confirm they're gone.
3. Click "↩️ Rückgängig". Confirm: badge disappears, add-set form reappears (with re-derived suggestion if one existed before).
4. Log a set on a different exercise (mark it completed), then skip that exercise. Confirm the completed set is still shown in the sets list (not deleted).
5. Finish the workout, then go to "Vorlage aktualisieren" / re-save as template (or inspect the template's exercises directly) and confirm the skipped exercise is still present in the resulting template.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): add skip/undo UI for session exercises"
```

---

## Task 4: Backend — edit-history route

**Files:**
- Modify: `personal_apps/features/gym/routes.py` — new route inserted directly after `gym_toggle_set_complete` (currently ends at line 645)

**Interfaces:**
- Consumes: `_to_float`, `_to_int` (routes.py:38-49), `SessionSet` model.
- Produces: route `gym.gym_update_set`, URL `/gym/set/<int:set_id>/update` (POST) — consumed by Task 5's template form (already added in Task 3, Step 1).

- [ ] **Step 1: Add the route**

Insert into `personal_apps/features/gym/routes.py` directly after `gym_toggle_set_complete` (after line 645, before the blank line preceding `gym_reorder_session_exercises`):

```python
@gym_bp.route('/gym/set/<int:set_id>/update', methods=['POST'])
@login_required
def gym_update_set(set_id):
    """Edit-history: correct a typo'd weight/reps on a set from a finished
    session. Deliberately narrow -- unlike gym_toggle_set_complete, this
    never touches `completed`, and works regardless of session.finished_at
    (that route's edit form is only shown for active sessions; this one's
    form is only shown for finished ones, in session_detail.html)."""
    set_ = db.get_or_404(SessionSet, set_id)
    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    if weight is not None:
        set_.weight = weight
    if reps is not None:
        set_.reps = reps
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=set_.session_exercise.session_id))
```

- [ ] **Step 2: Verify no import errors**

Run: `cd personal_apps && python -c "from app import app; print('OK: routes import cleanly')"`
Expected: `OK: routes import cleanly`

- [ ] **Step 3: Commit**

```bash
git add personal_apps/features/gym/routes.py
git commit -m "feat(gym): add edit-history route for logged sets"
```

---

## Task 5: Frontend — click-to-edit for finished-session set values

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html` — the finished-session set-value markup was already added in Task 3, Step 1 (`data-set-value`, `.edit-set-btn`, `.edit-set-form.hidden`); this task adds the JS that makes it interactive, plus the CSS that hides/shows it.
- Modify: `personal_apps/static/gym/gym.css` — add hide/show rules

**Interfaces:**
- Consumes: route `gym.gym_update_set` (Task 4), the global submit-interceptor already in `session_detail.html` (no new JS needed for the actual save — only for the click-to-reveal toggle).

- [ ] **Step 1: Add CSS to hide the edit form by default and style the button**

In `personal_apps/static/gym/gym.css`, add directly after the `.set-value` rule (currently line 210):

```css
.edit-set-btn { flex-shrink: 0; }
.set-value.hidden, .edit-set-btn.hidden, .edit-set-form.hidden { display: none; }
```

- [ ] **Step 2: Add the reveal-on-click JS**

In `personal_apps/templates/gym/session_detail.html`, inside the existing `<script>` block, add a new IIFE directly after `setupProgressModal` closes (after the closing `})();` that follows the progress-modal's `document.addEventListener('click', ...)` block — currently ends around line 644-645, right before the drag-reorder IIFE at line 351... **note the order in the file**: `setupProgressModal` (~583-645) is defined *after* `setupDragReorder` (~351-539) in the current file. Add this new block immediately after `setupProgressModal`'s closing `})();`:

```javascript
(function setupEditSetForms() {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest && e.target.closest('.edit-set-btn');
        if (!btn) return;
        const row = btn.closest('.set-row');
        if (!row) return;
        const valueEl = row.querySelector('[data-set-value]');
        const formEl = row.querySelector('.edit-set-form');
        if (valueEl) valueEl.classList.add('hidden');
        btn.classList.add('hidden');
        if (formEl) formEl.classList.remove('hidden');
    });
})();
```

- [ ] **Step 3: Manual verification**

With the dev server running and logged in:
1. Open a **finished** session (from dashboard history, or finish an active one first).
2. On a logged set, confirm it shows as plain text (`X kg × Y`) with a ✏️ button next to it, and no visible inputs.
3. Click ✏️. Confirm the text disappears and two number inputs + a 💾 button appear, pre-filled with the current weight/reps.
4. Change the weight value and click 💾. Confirm the page reflects the new value (via the existing AJAX refresh) and the row goes back to plain-text display with the corrected number.
5. Confirm `completed` status is unaffected (the set doesn't un-check or move) and no other sets on the page changed.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): add click-to-edit for finished-session set values"
```

---

## Task 6: Backend — export route

**Files:**
- Modify: `personal_apps/features/gym/routes.py` — new route, placed after `gym_delete_template` (currently ends at line 761, before `_exercise_progress_data` at line 762) since it's a dashboard-level export, not tied to one session/exercise.

**Interfaces:**
- Consumes: `WorkoutSession`, `SessionExercise`, `SessionSet` models; `se.replaces`/`se.replaced_by` relationships (models.py:220); `SessionExercise.skipped` (Task 1).
- Produces: route `gym.gym_export`, URL `/gym/export?from=YYYY-MM-DD&to=YYYY-MM-DD` (GET) — consumed by Task 7's template form.

- [ ] **Step 1: Add the route**

Insert into `personal_apps/features/gym/routes.py` directly after `gym_delete_template` (after line 761, before the blank lines preceding `_exercise_progress_data`):

```python
@gym_bp.route('/gym/export')
@login_required
def gym_export():
    """Downloadable JSON of finished workout history in a date range, for
    feeding into an external analysis tool later. Full detail (every set,
    not just aggregates) so nothing useful is thrown away up front. Both
    original and substitute SessionExercise rows are exported (mirroring
    what a finished session's own detail view already shows -- see
    session_detail's visible_exercises computation), each carrying
    replaces/replaced_by exercise names so a swap is fully traceable."""
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    try:
        from_date = dt.datetime.strptime(date_from, '%Y-%m-%d') if date_from else dt.datetime.min
    except ValueError:
        from_date = dt.datetime.min
    try:
        to_date = dt.datetime.strptime(date_to, '%Y-%m-%d') if date_to else dt.datetime.utcnow()
    except ValueError:
        to_date = dt.datetime.utcnow()
    to_date_exclusive = to_date + dt.timedelta(days=1)  # 'to' is inclusive of that whole calendar day

    sessions = (
        WorkoutSession.query
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.started_at >= from_date,
            WorkoutSession.started_at < to_date_exclusive,
        )
        .order_by(WorkoutSession.started_at.asc())
        .all()
    )

    payload = {
        'exported_at': dt.datetime.utcnow().isoformat() + 'Z',
        'range': {'from': date_from or None, 'to': date_to or None},
        'sessions': [
            {
                'id': s.id,
                'name': s.name,
                'template_name': s.template.name if s.template else None,
                'started_at': s.started_at.isoformat(),
                'finished_at': s.finished_at.isoformat(),
                'exercises': [
                    {
                        'exercise_name': se.exercise.name,
                        'muscle_group': se.exercise.muscle_group,
                        'position': se.position,
                        'rest_seconds': se.rest_seconds,
                        'skipped': se.skipped,
                        'replaces': se.replaces.exercise.name if se.replaces else None,
                        'replaced_by': se.replaced_by.exercise.name if se.replaced_by else None,
                        'sets': [
                            {'position': st.position, 'weight': st.weight, 'reps': st.reps, 'completed': st.completed}
                            for st in se.sets
                        ],
                    }
                    for se in s.exercises
                ],
            }
            for s in sessions
        ],
    }

    resp = jsonify(payload)
    filename = f"gym-export-{date_from or 'all'}_{date_to or 'now'}.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp
```

- [ ] **Step 2: Verify no import errors**

Run: `cd personal_apps && python -c "from app import app; print('OK: routes import cleanly')"`
Expected: `OK: routes import cleanly`

- [ ] **Step 3: Manual verification**

With the dev server running and logged in, visit (adjust dates to cover real history):
`http://127.0.0.1:5001/gym/export?from=2020-01-01&to=2030-01-01`
Expected: a `.json` file downloads (or renders inline, browser-dependent); open it and confirm it contains a `sessions` array with real past workout names, nested `exercises`, and nested `sets` matching what's shown in the dashboard history.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/features/gym/routes.py
git commit -m "feat(gym): add JSON training history export route"
```

---

## Task 7: Frontend — export UI on dashboard

**Files:**
- Modify: `personal_apps/templates/gym/dashboard.html:62-64` (history card header) and its `<script>` block (~line 184)

**Interfaces:**
- Consumes: route `gym.gym_export` (Task 6).

- [ ] **Step 1: Add the export panel**

In `personal_apps/templates/gym/dashboard.html`, replace:

```html
    <div class="card" id="history">
        <div class="card-header"><h2>Vergangene Workouts</h2></div>
        {% if past_sessions %}
```

with:

```html
    <div class="card" id="history">
        <div class="card-header"><h2>Vergangene Workouts</h2></div>
        <div class="export-panel">
            <div class="export-presets">
                <button type="button" class="btn btn-ghost btn-sm export-preset" data-days="30">Letzte 30 Tage</button>
                <button type="button" class="btn btn-ghost btn-sm export-preset" data-days="90">Letzte 90 Tage</button>
                <button type="button" class="btn btn-ghost btn-sm export-preset" data-days="">Alle</button>
            </div>
            <form method="get" action="{{ url_for('gym.gym_export') }}" class="form-row">
                <div class="form-group">
                    <label>Von</label>
                    <input type="date" name="from" id="export-from">
                </div>
                <div class="form-group">
                    <label>Bis</label>
                    <input type="date" name="to" id="export-to">
                </div>
                <button type="submit" class="btn btn-primary btn-sm">Exportieren (JSON)</button>
            </form>
        </div>
        {% if past_sessions %}
```

- [ ] **Step 2: Add the preset-fill JS**

In `personal_apps/templates/gym/dashboard.html`, inside the existing `<script>` block, add directly after the `{% endif %}` that closes the active-session ticker (currently line 184, right before the closing `</script>` on line 185):

```javascript
document.querySelectorAll('.export-preset').forEach((btn) => {
    btn.addEventListener('click', () => {
        const days = btn.dataset.days;
        const toInput = document.getElementById('export-to');
        const fromInput = document.getElementById('export-from');
        const today = new Date();
        toInput.value = today.toISOString().slice(0, 10);
        if (days) {
            const from = new Date(today);
            from.setDate(from.getDate() - parseInt(days, 10));
            fromInput.value = from.toISOString().slice(0, 10);
        } else {
            fromInput.value = '';
        }
    });
});
```

- [ ] **Step 3: Add the `.export-panel` CSS**

In `personal_apps/static/gym/gym.css`, add directly after the `.card-body` rule (currently line 98):

```css
.export-panel { padding: 14px 18px; border-bottom: 1px solid var(--gym-border); }
.export-presets { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
```

- [ ] **Step 4: Manual verification**

With the dev server running and logged in, load the dashboard, scroll to "Vergangene Workouts":
1. Click "Letzte 30 Tage". Confirm the "Von"/"Bis" date fields fill in (today, and 30 days prior).
2. Click "Alle". Confirm "Bis" fills with today and "Von" clears.
3. Click "Exportieren (JSON)". Confirm a JSON file downloads with a name like `gym-export-..._....json`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/dashboard.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): add export UI to dashboard history"
```

---

## Task 8: Frontend — reorder lock

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html` — new lock button (before line 61's `<div id="exercise-cards"...>`), new JS (near `SESSION_FINISHED` declaration and inside `setupDragReorder`'s `onMove`)
- Modify: `personal_apps/static/gym/gym.css` — small spacing rule

**Interfaces:**
- No backend change — this task is entirely client-side and doesn't touch the existing `gym_reorder_session_exercises` route.

- [ ] **Step 1: Add the lock toggle button**

In `personal_apps/templates/gym/session_detail.html`, directly before `<div id="exercise-cards" class="{{ 'read-only' if session.finished_at else '' }}">` (currently line 61), insert:

```html
    {% if not session.finished_at %}
    <div class="reorder-lock-row">
        <button type="button" class="btn btn-ghost btn-sm" id="reorder-lock-btn">🔒 Reihenfolge gesperrt</button>
    </div>
    {% endif %}
```

- [ ] **Step 2: Add the lock state and wire the button**

In the same file's `<script>` block, directly after `const SESSION_FINISHED = {{ 'true' if session.finished_at else 'false' }};` (currently line 242), insert:

```javascript
let reorderUnlocked = false;
const reorderLockBtn = document.getElementById('reorder-lock-btn');
function updateReorderLockButton() {
    if (!reorderLockBtn) return;
    reorderLockBtn.textContent = reorderUnlocked ? '🔓 Entsperrt — ziehen zum Sortieren' : '🔒 Reihenfolge gesperrt';
    reorderLockBtn.classList.toggle('btn-primary', reorderUnlocked);
    reorderLockBtn.classList.toggle('btn-ghost', !reorderUnlocked);
}
if (reorderLockBtn) {
    reorderLockBtn.addEventListener('click', () => {
        reorderUnlocked = !reorderUnlocked;
        updateReorderLockButton();
    });
    updateReorderLockButton();
}
```

- [ ] **Step 3: Gate the drag-start on the lock**

In the same file's `setupDragReorder` IIFE, inside `function onMove(e)` (currently lines 484-498), change:

```javascript
        if (!dragStarted) {
            if (SESSION_FINISHED) return;
```

to:

```javascript
        if (!dragStarted) {
            if (SESSION_FINISHED || !reorderUnlocked) return;
```

- [ ] **Step 4: Add the CSS spacing rule**

In `personal_apps/static/gym/gym.css`, add directly after the `.session-header` rules (currently line 178):

```css
.reorder-lock-row { margin-bottom: 12px; }
```

- [ ] **Step 5: Manual verification**

With the dev server running and logged in, start a workout with 3+ exercises:
1. Confirm the lock button shows "🔒 Reihenfolge gesperrt" on page load.
2. Try to drag an exercise card by its title (press, move down past a few pixels, release). Confirm it does **not** reorder — the card should NOT follow the drag.
3. Confirm a plain tap (no movement) on the title still collapses/expands the card as before.
4. Click the lock button — confirm it now reads "🔓 Entsperrt — ziehen zum Sortieren".
5. Drag a card to a new position. Confirm it reorders (existing behavior, now armed).
6. Reload the page. Confirm the button is back to "🔒 Reihenfolge gesperrt" (no persistence).

- [ ] **Step 6: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html personal_apps/static/gym/gym.css
git commit -m "feat(gym): add reorder lock to prevent accidental drags"
```

---

## Task 9: Fix — sticky bottom bar scrolling away

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html` — `refreshExerciseCards` function (currently lines 541-558)

**Interfaces:**
- No new interfaces — this is a targeted bug fix inside an existing function.

**Context:** Per the design spec, this bug ("past a certain scroll depth, the bottom tab bar stops staying pinned and scrolls away with the page") is not root-caused by static analysis alone — no ancestor `transform`/`filter`/`will-change`/`perspective` was found breaking `.gym-tabbar`'s `position: fixed`. The leading hypothesis is that `session_detail.html`'s frequent AJAX full-subtree swap (`oldCards.replaceWith(newCards)` inside `refreshExerciseCards`, triggered by nearly every form in `#exercise-cards`) desyncs the fixed bar from the visual viewport when it happens while scrolled deep — a known class of mobile-Safari/PWA bug. **Reproduce first, then apply candidates in order, verifying after each before moving to the next.**

- [ ] **Step 1: Reproduce**

On a mobile device (or Chrome DevTools device toolbar, e.g. iPhone 14 Pro preset) with the dev server running:
1. Start a workout from a template with 6+ exercises (enough to make the page tall).
2. Scroll to the bottom of the page, past the last exercise card.
3. Log a set on the last exercise (triggers the AJAX swap via `gym_add_set` → `refreshExerciseCards`).
4. Observe whether the bottom tab bar detaches/scrolls away instead of staying pinned.

If it does not reproduce in DevTools emulation, this is likely iOS-Safari-PWA-specific; reproduce on an actual iPhone in standalone (home-screen-installed) mode before proceeding — the fix candidates below specifically target that environment, and a fix can't be verified against a bug that isn't reproducing.

- [ ] **Step 2: Apply Candidate Fix 1 — preserve scroll position across the swap**

In `personal_apps/templates/gym/session_detail.html`, replace the `refreshExerciseCards` function (currently lines 541-558):

```javascript
function refreshExerciseCards(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const newCards = doc.getElementById('exercise-cards');
    const oldCards = document.getElementById('exercise-cards');
    if (newCards && oldCards) {
        const collapsedIds = new Set();
        const openIds = new Set();
        oldCards.querySelectorAll('.exercise-card').forEach((c) => {
            (c.classList.contains('collapsed') ? collapsedIds : openIds).add(c.dataset.seId);
        });
        oldCards.replaceWith(newCards);
        newCards.querySelectorAll('.exercise-card').forEach((c) => {
            if (collapsedIds.has(c.dataset.seId)) c.classList.add('collapsed');
            else if (openIds.has(c.dataset.seId)) c.classList.remove('collapsed');
        });
    }
    startRestFillTick();
}
```

with:

```javascript
function refreshExerciseCards(html) {
    const scrollY = window.scrollY;
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const newCards = doc.getElementById('exercise-cards');
    const oldCards = document.getElementById('exercise-cards');
    if (newCards && oldCards) {
        const collapsedIds = new Set();
        const openIds = new Set();
        oldCards.querySelectorAll('.exercise-card').forEach((c) => {
            (c.classList.contains('collapsed') ? collapsedIds : openIds).add(c.dataset.seId);
        });
        oldCards.replaceWith(newCards);
        newCards.querySelectorAll('.exercise-card').forEach((c) => {
            if (collapsedIds.has(c.dataset.seId)) c.classList.add('collapsed');
            else if (openIds.has(c.dataset.seId)) c.classList.remove('collapsed');
        });
        window.scrollTo(0, scrollY);
    }
    startRestFillTick();
}
```

- [ ] **Step 3: Re-test Candidate Fix 1**

Repeat Step 1's reproduction exactly. If the bar now stays pinned: skip to Step 6 (commit). If it still detaches: keep this change (it's a real improvement — explicit scroll-position restoration is correct regardless) and proceed to Step 4.

- [ ] **Step 4: Apply Candidate Fix 2 — force a repaint on the bar after swap (only if Step 3 didn't resolve it)**

In the same `refreshExerciseCards` function, add directly after the `window.scrollTo(0, scrollY);` line:

```javascript
        requestAnimationFrame(() => {
            const tabbar = document.querySelector('.gym-tabbar');
            if (tabbar) tabbar.style.transform = 'translateZ(0)';
        });
```

Re-test per Step 1. If resolved: proceed to Step 6. If not: proceed to Step 5.

- [ ] **Step 5: Apply Candidate Fix 3 — pin to the actual visual viewport (only if Steps 3-4 didn't resolve it)**

In the same `<script>` block, add a new top-level block (outside any existing function, anywhere after the `SESSION_FINISHED` declaration):

```javascript
if (window.visualViewport) {
    const tabbarEl = document.querySelector('.gym-tabbar');
    function pinTabbarToVisualViewport() {
        if (!tabbarEl) return;
        const offset = window.innerHeight - (window.visualViewport.height + window.visualViewport.offsetTop);
        tabbarEl.style.bottom = Math.max(0, offset) + 'px';
    }
    window.visualViewport.addEventListener('resize', pinTabbarToVisualViewport);
    window.visualViewport.addEventListener('scroll', pinTabbarToVisualViewport);
    pinTabbarToVisualViewport();
}
```

Re-test per Step 1.

- [ ] **Step 6: Commit whichever candidate(s) resolved it**

```bash
git add personal_apps/templates/gym/session_detail.html
git commit -m "fix(gym): keep bottom tab bar pinned after AJAX card refresh"
```

If none of the three candidates resolve it after real device testing, stop and report back with what was observed (does not reproduce in DevTools / reproduces but unaffected by all three / etc.) rather than committing a guess — this is the one task in this plan where "I tried the documented candidates and none worked" is a valid, honest outcome to report rather than force a commit.

---

## Self-Review

**Spec coverage:** Section 1 (Skip) → Tasks 1-3. Section 2 (Edit History) → Tasks 4-5. Section 3 (Sticky Bar) → Task 9. Section 4 (Export) → Tasks 6-7. Section 5 (Reorder Lock) → Task 8. All five spec sections have tasks; the spec's migration note maps to Task 1; the spec's "out of scope" list (CSV export, add/delete sets on history, cross-reload lock persistence, guaranteed bug root-cause) has no corresponding task, correctly.

**Placeholder scan:** No TBD/TODO. Task 9 is the one task without a single fixed diff — it has three fully-coded candidate fixes with an explicit escalation order and a legitimate "report back if none work" exit, which is not a placeholder (it's an honest bug-fix task where the exact diff depends on live reproduction, consistent with the spec's own framing).

**Type/name consistency check:** `gym_toggle_skip_session_exercise` (Task 2) matches the form action in Task 3. `gym_update_set` (Task 4) matches the form action added in Task 3/used in Task 5. `SessionExercise.skipped` (Task 1) is read in Tasks 2, 3, 6 with consistent naming. `.exercise-actions`, `.export-panel`, `.export-presets`, `.reorder-lock-row`, `.edit-set-btn`, `.edit-set-form` are each defined once (CSS) and referenced consistently across the task that defines them and any that consume them.

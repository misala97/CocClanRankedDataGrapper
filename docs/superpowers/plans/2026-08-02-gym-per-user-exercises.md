# Per-User Exercise Catalogues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `gym_exercises` an owned root so each user has their own exercise catalogue, and a new account starts empty.

**Architecture:** `gym_exercises` gains `user_id` NOT NULL, the global unique on `name` becomes unique on `(user_id, name)`, and `features/gym/scope.py` gains `my_exercises()` / `owned_exercise()` to join the four loaders already there. Fifteen call sites in `features/gym/routes.py` move from global reads to scoped ones. Two standalone scripts handle the rollout: a new `delete_user.py`, and `copy_templates.py` gains exercise forking.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy + Flask-SQLAlchemy, Flask-Migrate/Alembic, MySQL (pymysql), pytest, werkzeug.

**Spec:** `docs/superpowers/specs/2026-08-02-gym-per-user-exercises-design.md`

## Global Constraints

- Branch: `dev_personal`. Do not commit to `main`.
- All paths relative to `personal_apps/` unless stated. Run pytest and `flask db upgrade` from `personal_apps/`.
- Tests run against the **real local development database** — disposable dev data, normal care. Every fixture that creates rows deletes them in a `finally`.
- User-facing copy is **German**; code, comments and commit messages English.
- **Ownership failures return 404, never 403.** After this plan there is no admin-gated gym route left — every gym row belongs to exactly one user.
- Ownership lives on **four** roots: `gym_workout_sessions`, `gym_workout_templates`, `gym_push_subscriptions`, `gym_exercises`. The four child tables inherit through their parent foreign key.
- `tests/conftest.py` provides `_admin_id()`, `client`, `anon_client`, `acting_as`. Leave it unchanged unless a task says otherwise.
- Migration revision id `c8e5f14a9b32`, `down_revision = 'b7d93a5c1e40'`. Confirm the head with `flask db heads` first; if it differs, stop and report.
- The MySQL unique constraint on `gym_exercises.name` is named **`name`** (verified against the dev database).

---

## File Structure

**Modified:**
- `models.py` — `Exercise.user_id`, unique constraint swap.
- `features/gym/scope.py` — add `my_exercises()` and `owned_exercise()`. Currently 61 lines with four loaders; this brings it to six, still one idea per function.
- `features/gym/routes.py` — 15 call sites; no restructuring.
- `tests/test_gym_ownership.py` — the catalogue route tables change meaning.
- `scripts/copy_templates.py` — fork exercises into the destination's catalogue.

**Created:**
- `migrations/versions/c8e5f14a9b32_add_user_id_to_gym_exercises.py`
- `scripts/delete_user.py`

---

### Task 1: Owner column, migration, and the three construction sites

Folded into one task deliberately: the moment `user_id` is NOT NULL, any route that builds an `Exercise` without one fails on insert. Splitting them would leave the branch broken between tasks, which is exactly how the previous plan shipped a green suite over an app whose main flow was dead.

**Files:**
- Modify: `models.py:151-163` (`Exercise`)
- Create: `migrations/versions/c8e5f14a9b32_add_user_id_to_gym_exercises.py`
- Modify: `features/gym/routes.py:877`, `:925`, `:2208` (the three `Exercise(...)` constructions)
- Test: `tests/test_gym_exercise_ownership.py` (new)

**Interfaces:**
- Consumes: `models.AppUser`; `features.gym.scope.current_user_id` (already imported into `routes.py`).
- Produces: `Exercise.user_id: int` NOT NULL, FK `app_user.id`, indexed. Unique constraint `uq_gym_exercises_user_id_name` on `(user_id, name)`. The global unique named `name` no longer exists.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gym_exercise_ownership.py`:

```python
"""Per-user exercise catalogues.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import pytest

from app import app as flask_app
from conftest import _admin_id


def test_the_exercise_table_carries_an_owner():
    from models import Exercise
    assert hasattr(Exercise, 'user_id'), 'Exercise has no user_id'
    assert Exercise.__table__.c.user_id.nullable is False, 'Exercise.user_id must be NOT NULL'


def test_every_pre_existing_exercise_was_backfilled_to_the_admin():
    from models import AppUser, Exercise
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None
        orphans = Exercise.query.filter(
            Exercise.user_id != admin.id,
            Exercise.name.notlike('pytest%'),
        ).count()
        assert orphans == 0, 'Exercise has rows not owned by the admin'


def test_two_users_can_hold_an_exercise_with_the_same_name():
    """The constraint swap: unique(name) globally would reject this outright."""
    from extensions import db
    from models import AppUser, Exercise
    from werkzeug.security import generate_password_hash

    created = []
    try:
        with flask_app.app_context():
            other = AppUser(username='pytest samename user',
                            password_hash=generate_password_hash('irrelevant'),
                            is_admin=False)
            db.session.add(other)
            db.session.flush()
            mine = Exercise(name='pytest shared name lift', user_id=_admin_id())
            theirs = Exercise(name='pytest shared name lift', user_id=other.id)
            db.session.add_all([mine, theirs])
            db.session.commit()
            created = [mine.id, theirs.id, other.id]
            assert mine.id != theirs.id
    finally:
        with flask_app.app_context():
            for exercise_id in created[:2]:
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()
            if len(created) == 3:
                doomed_user = db.session.get(AppUser, created[2])
                if doomed_user is not None:
                    db.session.delete(doomed_user)
                    db.session.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v`
Expected: FAIL — `AssertionError: Exercise has no user_id`

- [ ] **Step 3: Add the column and swap the constraint in models.py**

In `models.py`, replace the `Exercise` class's `name` line and add `user_id` plus a table argument. The class becomes:

```python
class Exercise(db.Model):
    __tablename__ = 'gym_exercises'
    # Owned per user since 2026-08-02: a third lifter joined who trains at the
    # same gym but shares none of the same exercises, so one global list meant
    # everyone's picker held everyone else's lifts. The cost is that the same
    # machine can now carry a different weight_increment per user, and nothing
    # reports the disagreement -- see the per-user-exercises design spec.
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_gym_exercises_user_id_name'),)
    id                   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    name                 = db.Column(db.String(150), nullable=False)
    previous_name        = db.Column(db.String(150), nullable=True)  # set to the prior name on rename, so anything still referencing the old name (e.g. historical data, or a rename made by mistake) can still resolve to this exercise instead of creating a duplicate
    muscle_group         = db.Column(db.String(100), nullable=True)
    default_rest_seconds = db.Column(db.Integer, nullable=True)
    weight_increment     = db.Column(db.Float, nullable=True)  # smallest loadable jump on this equipment (dumbbells 2, a stack often 9); NULL means use stats.DEFAULT_INCREMENT
    is_unilateral        = db.Column(db.Boolean, nullable=False, default=False)  # logged weight/reps are per side (e.g. one-arm curls); volume must be doubled

    session_exercises  = db.relationship('SessionExercise', back_populates='exercise', lazy=True)
    template_exercises = db.relationship('TemplateExercise', back_populates='exercise', lazy=True)
```

Note `unique=True` is gone from `name` — the pair constraint replaces it.

- [ ] **Step 4: Write the migration**

Create `migrations/versions/c8e5f14a9b32_add_user_id_to_gym_exercises.py`:

```python
"""add user_id to gym_exercises, swap the unique constraint to (user_id, name)

Revision ID: c8e5f14a9b32
Revises: b7d93a5c1e40
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e5f14a9b32'
down_revision = 'b7d93a5c1e40'
branch_labels = None
depends_on = None

# Every row referencing an exercise must belong to the same user as the
# exercise. Run before any DDL: if it is already violated, the state this
# migration assumes does not hold and continuing would bake the violation in.
_CROSS_OWNER_CHECK = sa.text("""
    SELECT COUNT(*) FROM (
        SELECT te.id
          FROM gym_template_exercises te
          JOIN gym_workout_templates t ON t.id = te.template_id
          JOIN gym_exercises e ON e.id = te.exercise_id
         WHERE t.user_id <> :owner
        UNION ALL
        SELECT se.id
          FROM gym_session_exercises se
          JOIN gym_workout_sessions s ON s.id = se.session_id
          JOIN gym_exercises e ON e.id = se.exercise_id
         WHERE s.user_id <> :owner
    ) AS offenders
""")


def upgrade():
    connection = op.get_bind()
    owner = connection.execute(sa.text(
        'SELECT id FROM app_user WHERE is_admin = 1 ORDER BY id LIMIT 1')).scalar()
    if owner is None:
        raise RuntimeError('no admin account to own the existing exercises')

    # The intended state is a single-user database: the second account is
    # deleted before this runs, precisely so no exercise has to be duplicated
    # and no live foreign key repointed inside a migration. If that did not
    # happen, stop -- the alternative is silently leaving one user's templates
    # pointing at another user's lifts.
    offenders = connection.execute(_CROSS_OWNER_CHECK, {'owner': owner}).scalar()
    if offenders:
        raise RuntimeError(
            f'{offenders} template/session row(s) reference an exercise belonging to '
            f'another user. Delete those accounts first (scripts/delete_user.py), or '
            f'fork their exercises by hand before migrating.')

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    connection.execute(
        sa.text('UPDATE gym_exercises SET user_id = :owner WHERE user_id IS NULL'),
        {'owner': owner},
    )

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index('ix_gym_exercises_user_id', ['user_id'])
        batch_op.create_foreign_key('fk_gym_exercises_user_id', 'app_user', ['user_id'], ['id'])
        # MySQL named the original constraint after its column.
        batch_op.drop_constraint('name', type_='unique')
        batch_op.create_unique_constraint('uq_gym_exercises_user_id_name', ['user_id', 'name'])


def downgrade():
    connection = op.get_bind()
    # Lossy and it says so: restoring a global unique on `name` cannot succeed
    # while two users hold the same name, and choosing which row survives (and
    # whose weight_increment with it) has no correct answer. Restore from
    # backup instead.
    duplicates = connection.execute(sa.text(
        'SELECT COUNT(*) FROM (SELECT name FROM gym_exercises '
        'GROUP BY name HAVING COUNT(*) > 1) AS d')).scalar()
    if duplicates:
        raise RuntimeError(
            f'{duplicates} exercise name(s) are held by more than one user. Downgrading '
            f'would have to merge them and pick a surviving weight_increment, which this '
            f'migration will not guess. Restore from backup.')

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_constraint('uq_gym_exercises_user_id_name', type_='unique')
        batch_op.create_unique_constraint('name', ['name'])
        batch_op.drop_constraint('fk_gym_exercises_user_id', type_='foreignkey')
        batch_op.drop_index('ix_gym_exercises_user_id')
        batch_op.drop_column('user_id')
```

- [ ] **Step 5: Apply the migration**

Run: `flask db upgrade`
Expected: `Running upgrade b7d93a5c1e40 -> c8e5f14a9b32, add user_id to gym_exercises, swap the unique constraint to (user_id, name)`

- [ ] **Step 6: Give the three construction sites an owner**

`routes.py:877`, inside `gym_add_session_exercise`:

```python
            exercise = Exercise(
                name=new_name,
                muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
            )
```

becomes:

```python
            exercise = Exercise(
                name=new_name,
                muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
                user_id=current_user_id(),
            )
```

`routes.py:925`, inside `gym_replace_session_exercise`:

```python
            exercise = Exercise(
                name=new_name,
                muscle_group=original.exercise.muscle_group,
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
            )
```

becomes the same with `user_id=current_user_id(),` added as the last argument.

`routes.py:2208`, inside `gym_add_exercise`:

```python
    exercise = Exercise(
        name=name,
        muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
    )
```

becomes the same with `user_id=current_user_id(),` added as the last argument.

Confirm all three are done:

Run: `grep -n "Exercise(" features/gym/routes.py`
Expected: three hits, at approximately 877, 925 and 2208, each followed within a few lines by `user_id=current_user_id(),`.

- [ ] **Step 7: Give the test fixtures an owner too**

Application code is not the only thing that builds an `Exercise`. Seven fixture constructions do as well, and they hit the same NOT NULL wall:

- `tests/test_gym_ownership.py` — 1 site, in the `two_users` fixture
- `tests/test_gym_routes_smoke.py` — 6 sites

Find every one and add `user_id=_admin_id()`:

Run: `grep -n "Exercise(" tests/test_gym_ownership.py tests/test_gym_routes_smoke.py`
Expected: 7 hits. Account for every one — these are `Exercise(...)` constructions, not `SessionExercise(...)` or `TemplateExercise(...)`, so read each match rather than trusting the substring.

Both files already import `_admin_id` from `conftest` at module level. This is a mechanical argument addition: **do not change what any of these tests assert.**

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v`
Expected: PASS, 3 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions. A `NOT NULL constraint failed` or an `IntegrityError` on `user_id` here means a construction site was missed — in Step 6 if it is a route, in Step 7 if it is a fixture.

- [ ] **Step 9: Verify the migration is reversible**

Run: `flask db downgrade` then `flask db upgrade`
Expected: both succeed. (The downgrade guard only fires when two users share an exercise name; at this point in the plan none do.)

- [ ] **Step 10: Prove the precondition guard actually fires**

The guard is the only thing standing between a forgotten `delete_user` and one lifter's templates silently pointing at another's exercises. A guard nobody has seen refuse is not a guard.

Create a cross-owner reference, downgrade, and confirm the upgrade **refuses**:

```bash
python -c "
from app import app
from extensions import db
from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate
from werkzeug.security import generate_password_hash
with app.app_context():
    other = AppUser(username='pytest guard probe',
                    password_hash=generate_password_hash('irrelevant'), is_admin=False)
    db.session.add(other); db.session.flush()
    mine = Exercise.query.first()
    t = WorkoutTemplate(name='pytest guard template', user_id=other.id)
    t.exercises.append(TemplateExercise(exercise_id=mine.id, position=1))
    db.session.add(t); db.session.commit()
    print('planted: template owned by', other.id, 'using exercise owned by', mine.user_id)
"
```

Run: `flask db downgrade` then `flask db upgrade`
Expected: the downgrade succeeds; the **upgrade fails** with `RuntimeError: 1 template/session row(s) reference an exercise belonging to another user.`

Then remove the probe and confirm the upgrade succeeds again:

```bash
python -c "
from app import app
from extensions import db
from models import AppUser, WorkoutTemplate
with app.app_context():
    other = AppUser.query.filter_by(username='pytest guard probe').first()
    for t in WorkoutTemplate.query.filter_by(user_id=other.id):
        db.session.delete(t)
    db.session.commit()
    db.session.delete(other); db.session.commit()
    print('probe removed')
"
```

Run: `flask db upgrade`
Expected: succeeds.

Report all three outcomes. If the upgrade did **not** fail while the probe existed, the guard's query is wrong and the task is not done — report BLOCKED rather than continuing.

- [ ] **Step 11: Commit**

```bash
git add models.py migrations/versions/c8e5f14a9b32_add_user_id_to_gym_exercises.py features/gym/routes.py tests/
git commit -m "feat(gym): make the exercise catalogue per-user"
```

---

### Task 2: Scope loaders and the pickers

**Files:**
- Modify: `features/gym/scope.py` (append two loaders)
- Modify: `features/gym/routes.py:488`, `:758`, `:1740`
- Test: `tests/test_gym_exercise_ownership.py`

**Interfaces:**
- Consumes: `Exercise.user_id` from Task 1.
- Produces, in `features.gym.scope`:
  - `my_exercises() -> Query` — `Exercise` filtered to the caller
  - `owned_exercise(exercise_id: int) -> Exercise` — aborts 404 if not the caller's

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_exercise_ownership.py`:

```python
@pytest.fixture()
def two_lifters():
    """An admin-owned exercise and a second account that owns nothing.

    Yields {'owner_id', 'stranger_id', 'exercise_id'}.
    """
    from extensions import db
    from models import AppUser, Exercise
    from werkzeug.security import generate_password_hash

    ids = {}
    with flask_app.app_context():
        stranger = AppUser(username='pytest catalogue stranger',
                           password_hash=generate_password_hash('irrelevant'),
                           is_admin=False)
        db.session.add(stranger)
        db.session.flush()
        exercise = Exercise(name='pytest owned lift', muscle_group='Brust',
                            weight_increment=9.0, user_id=_admin_id())
        db.session.add(exercise)
        db.session.commit()
        ids = {'owner_id': _admin_id(), 'stranger_id': stranger.id,
               'exercise_id': exercise.id}
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(Exercise, ids['exercise_id'])
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
        doomed_user = db.session.get(AppUser, ids['stranger_id'])
        if doomed_user is not None:
            db.session.delete(doomed_user)
            db.session.commit()


@pytest.fixture()
def stranger_client(two_lifters):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_lifters['stranger_id']
        yield test_client


def test_a_new_accounts_exercise_list_is_empty(stranger_client, two_lifters):
    """The whole point of the change: she opens the picker and sees nothing of
    theirs, not thirty lifts she will never do."""
    body = stranger_client.get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' not in body


def test_the_owner_still_sees_their_own_exercise(two_lifters):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_lifters['owner_id']
        body = owner_client.get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' in body, 'scoping hid the owner from their own catalogue'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v -k "empty or owner_still"`
Expected: FAIL — `test_a_new_accounts_exercise_list_is_empty` finds the owner's exercise on the stranger's page.

- [ ] **Step 3: Add the loaders to scope.py**

In `features/gym/scope.py`, extend the model import:

```python
from models import Exercise, SessionExercise, SessionSet, WorkoutSession, WorkoutTemplate
```

Append after `owned_set`:

```python
def my_exercises():
    """Exercise query filtered to the caller.

    The catalogue was shared until 2026-08-02. It is owned now: a third lifter
    joined who trains at the same gym but uses none of the same exercises, so
    one global list put everyone's lifts in everyone's picker.
    """
    return Exercise.query.filter(Exercise.user_id == current_user_id())


def owned_exercise(exercise_id):
    row = db.session.get(Exercise, exercise_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row
```

- [ ] **Step 4: Scope the pickers**

In `features/gym/routes.py`, extend the scope import to include the two new names:

```python
from features.gym.scope import (
    current_user_id, my_exercises, my_sessions, my_templates,
    owned_exercise, owned_session, owned_session_exercise, owned_set, owned_template,
)
```

Line 758 (`gym_heute`'s exercise list) and line 1740 (`gym_uebungen`):

```python
    exercises = Exercise.query.order_by(Exercise.name).all()
```

both become:

```python
    exercises = my_exercises().order_by(Exercise.name).all()
```

Line 488, the muscle-group vocabulary:

```python
           for row in db.session.query(Exercise.muscle_group).distinct()}
```

becomes:

```python
           for row in my_exercises().with_entities(Exercise.muscle_group).distinct()}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v`
Expected: PASS, 5 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add features/gym/scope.py features/gym/routes.py tests/test_gym_exercise_ownership.py
git commit -m "feat(gym): scope the exercise pickers to their owner"
```

---

### Task 3: Own-exercise pages, and the admin gate comes off

**Files:**
- Modify: `features/gym/routes.py:2100`, `:2159`, `:2224`, `:2250`, and the decorators above `gym_update_exercise` and `gym_delete_exercise`
- Modify: `tests/test_gym_ownership.py:332-369` (the catalogue tables)
- Test: `tests/test_gym_ownership.py`

**Interfaces:**
- Consumes: `owned_exercise` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Rewrite the catalogue route tables**

In `tests/test_gym_ownership.py`, replace lines 332-369 — from `CATALOGUE_ADMIN_ROUTES = [` through the closing brace of `SHARED_CATALOGUE_GET_ROUTES` — with:

```python
# Was CATALOGUE_ADMIN_ROUTES, asserting 403 on a shared row an admin curated.
# The catalogue is owned per user now, so these are ordinary owned routes and
# a stranger gets 404 like everywhere else -- including the two GETs, which
# used to render a shared page with the owner's history filtered out of it.
CATALOGUE_ROUTES = [
    ('GET',  '/gym/exercises/{}',               'exercise_id'),
    ('GET',  '/gym/exercises/{}/progress.json', 'exercise_id'),
    ('POST', '/gym/exercises/{}/update',        'exercise_id'),
    ('POST', '/gym/exercises/{}/delete',        'exercise_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', CATALOGUE_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_exercise(
        intruder_client, two_users, method, url_template, id_key):
    """Also checks the exercise survived: a 404 on /delete is only half the
    guarantee if the row went away anyway."""
    from extensions import db
    from models import Exercise
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'
    with flask_app.app_context():
        assert db.session.get(Exercise, two_users['exercise_id']) is not None, \
            f'the exercise did not survive the rejected {method} {url}'


# The tables hold Flask's route strings with '<int:name>' replaced by '{}', so
# that a route can be filled in with .format(some_id). This is the inverse
# substitution, applied to url_map's rules to bring them into the same shape.
_INT_CONVERTER = re.compile(r'<int:[^>]+>')
```

- [ ] **Step 2: Update the completeness check's table list**

In the same file, `test_every_id_taking_gym_route_is_covered_by_a_table` currently reads:

```python
    covered = {
        (method, url_template)
        for table in (SESSION_ROUTES, DESCENDANT_ROUTES, TEMPLATE_ROUTES, CATALOGUE_ADMIN_ROUTES)
        for method, url_template, _id_key in table
    } | SHARED_CATALOGUE_GET_ROUTES
```

becomes:

```python
    covered = {
        (method, url_template)
        for table in (SESSION_ROUTES, DESCENDANT_ROUTES, TEMPLATE_ROUTES, CATALOGUE_ROUTES)
        for method, url_template, _id_key in table
    }
```

`SHARED_CATALOGUE_GET_ROUTES` no longer exists — the two GETs are inside `CATALOGUE_ROUTES` now.

- [ ] **Step 3: Delete the two now-wrong leak tests**

`test_the_shared_exercise_page_shows_no_foreign_history` and `test_the_progress_json_carries_no_foreign_history` (around lines 482 and 493) assert **200 with the owner's numbers filtered out**. Both pages now 404 for a stranger, which the new parametrized test covers, so these two assert a behaviour that no longer exists. Delete both.

Do not delete `test_the_list_pages_show_none_of_another_users_numbers` — the list pages still render for everyone and still must not leak.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_ownership.py -v -k "stranger_gets_404_on_someone_elses_exercise"`
Expected: FAIL — the GET routes return 200 and the POST routes return 403, not 404.

- [ ] **Step 5: Swap the loaders and drop the admin gate**

In `features/gym/routes.py`, replace `db.get_or_404(Exercise, exercise_id)` with `owned_exercise(exercise_id)` at lines 2100, 2159, 2224 and 2250.

Then remove `@admin_required` from `gym_update_exercise` and `gym_delete_exercise`. Each decorator stack becomes:

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
def gym_update_exercise(exercise_id):
```

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_exercise(exercise_id):
```

Confirm nothing unscoped remains and the gate is gone:

Run: `grep -n "get_or_404(Exercise\|admin_required" features/gym/routes.py`
Expected: no output. (`admin_required` was only ever used on these two routes, so its import becomes unused — remove it from the `from auth import ...` line, leaving `from auth import login_required`.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_ownership.py -v`
Expected: PASS.

Run: `python -m pytest tests/ -v`
Expected: PASS. `tests/test_auth.py` covers `admin_required` through `/admin/users`, which is unaffected.

- [ ] **Step 7: Commit**

```bash
git add features/gym/routes.py tests/test_gym_ownership.py
git commit -m "feat(gym): exercise pages check ownership instead of admin"
```

---

### Task 4: Scoped name lookups

**Files:**
- Modify: `features/gym/routes.py:875`, `:923`, `:2205`, `:2228`
- Test: `tests/test_gym_exercise_ownership.py`

**Interfaces:**
- Consumes: `my_exercises` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_exercise_ownership.py`:

```python
def test_adding_an_exercise_whose_name_another_user_has_creates_your_own(
        stranger_client, two_lifters):
    """Unscoped, the name lookup finds the other user's row and the route
    redirects with name_taken -- so she could never create her own 'Bankdruecken',
    and any path that linked instead of created would hand her their increment
    and put her sets in their history."""
    from extensions import db
    from models import Exercise

    response = stranger_client.post('/gym/exercises/add', data={
        'name': 'pytest owned lift', 'muscle_group': 'Brust'})
    assert response.status_code in (302, 303)

    created_id = None
    try:
        with flask_app.app_context():
            hers = Exercise.query.filter_by(name='pytest owned lift',
                                            user_id=two_lifters['stranger_id']).first()
            assert hers is not None, 'the name lookup matched another user and refused'
            created_id = hers.id
            assert hers.id != two_lifters['exercise_id'], 'linked to their row instead of creating'
            assert hers.weight_increment is None, 'inherited their increment'
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(Exercise, created_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v -k name_another_user`
Expected: FAIL — `the name lookup matched another user and refused`.

- [ ] **Step 3: Scope the four lookups**

All four are `Exercise.query.filter_by(name=...)`. Each becomes `my_exercises().filter_by(name=...)`.

Line 875, in `gym_add_session_exercise`:

```python
        exercise = Exercise.query.filter_by(name=new_name).first()
```
becomes
```python
        exercise = my_exercises().filter_by(name=new_name).first()
```

Line 923, in `gym_replace_session_exercise`: identical change.

Line 2205, in `gym_add_exercise`:

```python
    if Exercise.query.filter_by(name=name).first():
```
becomes
```python
    if my_exercises().filter_by(name=name).first():
```

Line 2228, in `gym_update_exercise`:

```python
        if Exercise.query.filter_by(name=new_name).first():
```
becomes
```python
        if my_exercises().filter_by(name=new_name).first():
```

Confirm none remain:

Run: `grep -n "Exercise.query" features/gym/routes.py`
Expected: no output.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v`
Expected: PASS, 6 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add features/gym/routes.py tests/test_gym_exercise_ownership.py
git commit -m "feat(gym): scope exercise name lookups to the caller"
```

---

### Task 5: The form-supplied exercise ids

**Files:**
- Modify: `features/gym/routes.py:887` and the equivalent in `gym_replace_session_exercise`
- Test: `tests/test_gym_exercise_ownership.py`

**Interfaces:**
- Consumes: `owned_exercise` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gym_exercise_ownership.py`:

```python
def test_a_stranger_cannot_add_another_users_exercise_to_their_session(
        stranger_client, two_lifters):
    """Both mid-session paths take exercise_id straight from a submitted form.
    Harmless while one catalogue was shared; an IDOR once exercises are owned."""
    from extensions import db
    from models import SessionExercise, WorkoutSession

    session_id = None
    try:
        with flask_app.app_context():
            theirs = WorkoutSession(name='pytest stranger session',
                                    user_id=two_lifters['stranger_id'])
            db.session.add(theirs)
            db.session.commit()
            session_id = theirs.id

        response = stranger_client.post(f'/gym/session/{session_id}/exercises/add',
                                        data={'exercise_id': str(two_lifters['exercise_id'])})
        assert response.status_code == 404, f'returned {response.status_code}'

        with flask_app.app_context():
            assert SessionExercise.query.filter_by(session_id=session_id).count() == 0, \
                'the rejected request added the exercise anyway'
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v -k cannot_add_another`
Expected: FAIL — returns 302 and the exercise is added.

- [ ] **Step 3: Check ownership on both form-supplied ids**

In `gym_add_session_exercise`, line 887:

```python
    if exercise_id:
        exercise = db.session.get(Exercise, exercise_id)
```

becomes:

```python
    if exercise_id:
        # exercise_id arrives from a submitted form, so it is attacker-chosen:
        # without this check a lifter could graft another user's exercise --
        # and its history, through _seeded_sets -- into their own session.
        exercise = owned_exercise(exercise_id)
```

`gym_replace_session_exercise` never loads the row — it uses `exercise_id` directly to build the replacement. So the check goes in as its own statement, just above line 934:

```python
    if exercise_id and exercise_id != original.exercise_id and not original.replaced_by:
        db.session.add(SessionExercise(
```

becomes:

```python
    if exercise_id:
        # Attacker-chosen whenever it came from the form rather than from the
        # branch above that just created it. Re-checking the freshly created
        # one costs a primary-key lookup and keeps this to a single rule.
        owned_exercise(exercise_id)

    if exercise_id and exercise_id != original.exercise_id and not original.replaced_by:
        db.session.add(SessionExercise(
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_exercise_ownership.py -v`
Expected: PASS, 7 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add features/gym/routes.py tests/test_gym_exercise_ownership.py
git commit -m "fix(gym): reject a form-supplied exercise id from another user"
```

---

### Task 6: `delete_user.py`

**Files:**
- Create: `scripts/delete_user.py`
- Test: `tests/test_scripts.py` (new)

**Interfaces:**
- Consumes: `models.AppUser`, `WorkoutTemplate`, `WorkoutSession`, `PushSubscription`.
- Produces: `scripts.delete_user.delete_user(username: str, commit: bool) -> list[str]` — returns the lines it reported, so a test can assert on them without parsing stdout.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scripts.py`:

```python
"""The two rollout scripts. They run once each against production, so their
guards matter more than their happy paths."""
import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def throwaway_user():
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash
    with flask_app.app_context():
        user = AppUser(username='pytest deletable',
                       password_hash=generate_password_hash('irrelevant'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id
    with flask_app.app_context():
        doomed = db.session.get(AppUser, user_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


def test_delete_user_dry_run_writes_nothing(throwaway_user):
    from extensions import db
    from models import AppUser
    from scripts.delete_user import delete_user

    with flask_app.app_context():
        delete_user('pytest deletable', commit=False)
        assert db.session.get(AppUser, throwaway_user) is not None


def test_delete_user_removes_the_account_and_its_templates(throwaway_user):
    from extensions import db
    from models import AppUser, WorkoutTemplate
    from scripts.delete_user import delete_user

    with flask_app.app_context():
        db.session.add(WorkoutTemplate(name='pytest deletable template',
                                       user_id=throwaway_user))
        db.session.commit()

    with flask_app.app_context():
        delete_user('pytest deletable', commit=True)

    with flask_app.app_context():
        assert db.session.get(AppUser, throwaway_user) is None
        assert WorkoutTemplate.query.filter_by(user_id=throwaway_user).count() == 0


def test_delete_user_refuses_a_user_with_a_logged_session(throwaway_user):
    """The guard that separates removing an empty placeholder from destroying
    someone's training history because a username was mistyped."""
    import datetime as dt
    from extensions import db
    from models import AppUser, WorkoutSession
    from scripts.delete_user import delete_user

    session_id = None
    try:
        with flask_app.app_context():
            logged = WorkoutSession(name='pytest deletable session',
                                    started_at=dt.datetime.utcnow(),
                                    user_id=throwaway_user)
            db.session.add(logged)
            db.session.commit()
            session_id = logged.id

        with flask_app.app_context():
            with pytest.raises(SystemExit):
                delete_user('pytest deletable', commit=True)
            assert db.session.get(AppUser, throwaway_user) is not None
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_scripts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.delete_user'`

- [ ] **Step 3: Write the script**

Create `scripts/delete_user.py`:

```python
"""One-time: remove an account that has no training history.

    python scripts/delete_user.py <username>
    python scripts/delete_user.py <username> --commit

Without --commit it only reports what it would remove. Nothing is written.

Written for the per-user-exercises rollout, where an account created with
nothing in it is deleted so the migration runs against a single-user database
and never has to duplicate an exercise or repoint a live foreign key.

It refuses a user with any logged session. That guard is the point: it
separates removing an empty placeholder from silently destroying a training
history because a username was mistyped. Deleting someone who has actually
trained is a deliberate act and can be a deliberate SQL statement.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (needs the path insert above)
from extensions import db  # noqa: E402
from models import AppUser, PushSubscription, WorkoutSession, WorkoutTemplate  # noqa: E402


def delete_user(username, commit):
    """Remove `username`. Returns the report lines. Exits on a refusal."""
    user = AppUser.query.filter_by(username=username).first()
    if user is None:
        existing = ', '.join(u.username for u in AppUser.query.order_by(AppUser.username))
        sys.exit(f'no user named {username!r}. Accounts that exist: {existing}')

    sessions = WorkoutSession.query.filter_by(user_id=user.id).count()
    if sessions:
        sys.exit(f'{username} has {sessions} logged session(s) — refusing. This script is '
                 f'only for accounts with no training history.')

    templates = WorkoutTemplate.query.filter_by(user_id=user.id).all()
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()

    lines = [f'{username} (id {user.id})',
             f'  {len(templates)} template(s)',
             f'  {len(subscriptions)} push subscription(s)',
             '  0 sessions']
    for line in lines:
        print(line)

    if commit:
        # Templates first: their exercise rows cascade, and the user row cannot
        # go while anything still references it.
        for template in templates:
            db.session.delete(template)
        for subscription in subscriptions:
            db.session.delete(subscription)
        db.session.flush()
        db.session.delete(user)
        db.session.commit()
        print('\ndeleted.')
    else:
        print('\ndry run — nothing written. Re-run with --commit to do it.')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username', help='the account to remove')
    parser.add_argument('--commit', action='store_true',
                        help='actually delete; without it this is a dry run')
    args = parser.parse_args()
    with app.app_context():
        delete_user(args.username, args.commit)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Make `scripts/` importable**

`tests/test_scripts.py` does `from scripts.delete_user import delete_user`, which needs `scripts/` to be a package.

Create `scripts/__init__.py` as an empty file.

Run: `python -c "import scripts.delete_user; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_scripts.py -v`
Expected: PASS, 3 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add scripts/delete_user.py scripts/__init__.py tests/test_scripts.py
git commit -m "feat(gym): add a guarded delete-user script for the rollout"
```

---

### Task 7: `copy_templates.py` forks exercises

**Files:**
- Modify: `scripts/copy_templates.py`
- Test: `tests/test_scripts.py`

**Interfaces:**
- Consumes: `Exercise.user_id` from Task 1.
- Produces: nothing other tasks rely on. This is the last task.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scripts.py`:

```python
def test_copy_templates_forks_the_exercises_into_the_destination(throwaway_user):
    """After the catalogue became per-user, copied template rows cannot point
    at the source's exercises. Each one is recreated in the destination's own
    catalogue -- once per distinct exercise, even when two templates share it,
    and carrying the values that make a suggestion correct."""
    from extensions import db
    from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate
    from scripts.copy_templates import copy_templates

    made = []
    try:
        with flask_app.app_context():
            source_id = _admin_id()
            shared = Exercise(name='pytest fork lift', muscle_group='Brust',
                              weight_increment=9.0, is_unilateral=True,
                              user_id=source_id)
            db.session.add(shared)
            db.session.flush()
            made.append(('exercise', shared.id))
            # Two templates referencing the SAME exercise -- a plain create
            # would give the destination two copies of it.
            for name in ('pytest fork A', 'pytest fork B'):
                template = WorkoutTemplate(name=name, user_id=source_id)
                template.exercises.append(
                    TemplateExercise(exercise_id=shared.id, position=1, rest_seconds=150))
                db.session.add(template)
                db.session.flush()
                made.append(('template', template.id))
            db.session.commit()

            destination = db.session.get(AppUser, throwaway_user).username
            copy_templates(db.session.get(AppUser, source_id).username, destination,
                           commit=True)

        with flask_app.app_context():
            copies = Exercise.query.filter_by(user_id=throwaway_user,
                                              name='pytest fork lift').all()
            assert len(copies) == 1, f'expected one forked exercise, got {len(copies)}'
            assert copies[0].weight_increment == 9.0
            assert copies[0].is_unilateral is True
            assert copies[0].id != made[0][1], 'pointed at the source exercise'

            for template in WorkoutTemplate.query.filter_by(user_id=throwaway_user):
                for te in template.exercises:
                    assert te.exercise.user_id == throwaway_user, \
                        'a copied template row points at another user exercise'
    finally:
        with flask_app.app_context():
            for template in WorkoutTemplate.query.filter_by(user_id=throwaway_user):
                db.session.delete(template)
            for exercise in Exercise.query.filter_by(user_id=throwaway_user):
                db.session.delete(exercise)
            db.session.commit()
            for kind, row_id in reversed(made):
                model = {'exercise': Exercise, 'template': WorkoutTemplate}[kind]
                doomed = db.session.get(model, row_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_scripts.py -v -k forks`
Expected: FAIL — `ImportError: cannot import name 'copy_templates'`, because the script's logic currently lives inline in `main()`.

- [ ] **Step 3: Extract the logic and add the fork**

In `scripts/copy_templates.py`, replace the body of `main()` from `with app.app_context():` onward with a call to a new function, and add that function above it:

```python
def copy_templates(source_username, destination_username, commit):
    """Copy source's templates to destination, forking the exercises they use."""
    source, destination = _user(source_username), _user(destination_username)
    if source.id == destination.id:
        sys.exit('source and destination are the same account')

    templates = (WorkoutTemplate.query
                 .filter_by(user_id=source.id)
                 .order_by(WorkoutTemplate.name).all())
    if not templates:
        sys.exit(f'{source.username} has no templates to copy')

    already = WorkoutTemplate.query.filter_by(user_id=destination.id).count()
    if already:
        sys.exit(f'{destination.username} already has {already} template(s) — '
                 f'refusing to add more. Delete them first if you meant to redo this.')

    # The catalogue is per user, so a copied template row cannot point at the
    # source's exercises. Find-or-create, not create: the source's templates
    # overlap, and creating blindly would give the destination a duplicate of
    # every exercise appearing in more than one template.
    forked = {}

    def _destination_exercise(source_exercise):
        if source_exercise.id in forked:
            return forked[source_exercise.id]
        mine = Exercise.query.filter_by(user_id=destination.id,
                                        name=source_exercise.name).first()
        if mine is None:
            mine = Exercise(
                name=source_exercise.name,
                previous_name=source_exercise.previous_name,
                muscle_group=source_exercise.muscle_group,
                default_rest_seconds=source_exercise.default_rest_seconds,
                weight_increment=source_exercise.weight_increment,
                is_unilateral=source_exercise.is_unilateral,
                user_id=destination.id,
            )
            db.session.add(mine)
            db.session.flush()
        forked[source_exercise.id] = mine
        return mine

    print(f'{source.username} -> {destination.username}')
    for t in templates:
        print(f'  {t.name} ({len(t.exercises)} exercises)')
        if not commit:
            continue
        copy = WorkoutTemplate(name=t.name, user_id=destination.id)
        db.session.add(copy)
        db.session.flush()          # need copy.id before the children
        for te in t.exercises:
            db.session.add(TemplateExercise(
                template_id=copy.id,
                exercise_id=_destination_exercise(te.exercise).id,
                position=te.position,
                rest_seconds=te.rest_seconds,
            ))

    if commit:
        db.session.commit()
        print(f'\ncopied {len(templates)} template(s) and '
              f'{len(forked)} exercise(s).')
    else:
        print('\ndry run — nothing written. Re-run with --commit to do it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='username to copy templates FROM')
    parser.add_argument('destination', help='username to copy templates TO')
    parser.add_argument('--commit', action='store_true',
                        help='actually write; without it this is a dry run')
    args = parser.parse_args()
    with app.app_context():
        copy_templates(args.source, args.destination, args.commit)
```

Add `Exercise` to the model import at the top of the file:

```python
from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate  # noqa: E402
```

Update the module docstring's closing paragraph — it currently says *"The exercise catalogue is shared, so exercise_id values stay valid across users and need no remapping"*, which is no longer true. Replace that paragraph with:

```
The exercise catalogue is per user, so each referenced exercise is recreated in
the destination's own catalogue and the new template rows point at those copies.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_scripts.py -v`
Expected: PASS, 4 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add scripts/copy_templates.py tests/test_scripts.py
git commit -m "feat(gym): fork exercises when copying templates between users"
```

---

## Deployment

Not a task — run by the author. `scripts/delete_user.py` is already on `main` by itself (commit `065a232`), *without* the migration, so this is two ordinary deploys rather than checking a file out of a merge commit by hand.

1. Confirm the suite passes on `dev_personal`: `python -m pytest tests/ -v`

2. Confirm `PERSONAL_ADMIN_USER` and `PERSONAL_ADMIN_PASS` are still set in the VPS `.env`. The earlier `a4c81f2e5b76` migration reads them, and a failed upgrade restarts the web service onto a schema it cannot authenticate against.

3. **Verify the unique index's real name in production**, before anything irreversible:

```bash
mysql -u root -p personal_apps -e "SHOW INDEX FROM gym_exercises WHERE Non_unique = 0;"
```

Expect a row whose `Key_name` is `name`, on column `name`. The migration runs `drop_constraint('name', type_='unique')`, and that name was only ever verified against the *development* database. If production names it differently the migration dies at that statement with `user_id` already added, backfilled, set NOT NULL, indexed and foreign-keyed — and because MySQL DDL is not transactional and Alembic stamps the revision only after the whole function returns, the re-run then fails immediately on `Duplicate column name 'user_id'`. Recovery from that is restore-from-backup, on the entire training history. One command removes the only unverified assumption in the whole operation.

4. **Back up the production database.**

5. **First deploy.** `main` currently holds the delete script and nothing else new, so the deploy script's `flask db upgrade` finds no new revision and does nothing to the schema. The app keeps running exactly as it is.

6. Remove the empty second account, dry run first:

```bash
/root/coc-stats/venv/bin/python /root/coc-stats/personal_apps/scripts/delete_user.py jglaser
```

then the same command with `--commit`. It reports `0 exercise(s)` here — `gym_exercises` has no owner column yet, and the script checks rather than assuming. It refuses outright if he has logged a session; if that happens, stop and reassess, because the single-user premise the migration depends on is no longer true.

7. **Second deploy.** Merge `dev_personal` to `main`, push, run the deploy script. Now the migration runs, against a single-user database.

If it aborts with *"template/session row(s) reference an exercise belonging to another user"*, step 6 did not happen or did not complete. Nothing has been changed at that point — the guard runs before any DDL — so fix the accounts and re-run.

8. Recreate jglaser at `/admin/users`.

9. Copy the templates, dry run first, then `--commit`:

```bash
/root/coc-stats/venv/bin/python /root/coc-stats/personal_apps/scripts/copy_templates.py mgemmel jglaser --commit
```

The dry run previews only the template names — the exercise forking it now also does is not shown until `--commit`.

10. Create the third account at `/admin/users`. Nothing further: an empty catalogue is the default.

11. Verify per user: she sees an empty exercise list, and can rename and delete an exercise she creates; jglaser sees his own copies of mgemmel's lifts with increments intact; neither can open the other's exercise detail page.

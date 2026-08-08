# Gym React Islands — Step 2b: The Session JSON Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the live workout screen a Pydantic-validated JSON payload and a `/gym/session/<id>/detail.json` endpoint, both built by one function that `session_detail` also renders from — so the page and the endpoint cannot disagree.

**Architecture:** Exactly the shape step 1 used for `exercise_detail`. `session_detail`'s 310-line body becomes `_session_payload(session_)` returning a validated `SessionDetailPayload`; the HTML route renders from `payload.model_dump()` and the JSON route returns `model_dump(mode='json')`. No markup changes — that is step 2c.

**Tech Stack:** Pydantic v2, Flask, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-08-gym-react-islands-design.md`
**Precedent:** `docs/superpowers/plans/2026-08-08-gym-react-islands-step-1-exercise-detail.md`, Tasks 2–3. Read them — this is the same two moves against a much larger surface.

## Global Constraints

- **No behaviour change and no markup change.** `session_detail.html` and `_session_queue.html` render exactly as they do now. Step 2c replaces them.
- **The oracle is 543 pytest + 42 vitest.** Run both. Any new failure means the extraction was wrong.
- **Every model sets `extra='forbid'`.** The schema is a mirror of what the route already computes, not a subset. A field added on one side and not the other must fail loudly — that is how step 1 caught `state=None`.
- **Read the producer before typing a field.** Step 1's schema was wrong in five places because it was written from template usage rather than from the code that builds the value. `git log` those fixes if tempted to guess.
- **Tests must iterate, not sample.** Step 1's suite passed green over a real crash because every test picked the first exercise, which happened to have history. Loop over every session in the dev database.
- **The new route MUST be added to the table in `tests/test_gym_ownership.py`** (~line 340). `test_every_id_taking_gym_route_is_covered_by_a_table` fails otherwise, and registering it is what makes the suite verify cross-user rejection.
- **Branch:** `dev_personal`. Never commit to `main`.

## The surface being typed

`session_detail` (`features/gym/routes/workout.py:283-592`) passes 30 template keys:

`session`, `live_se`, `visible_exercises`, `live_id`, `live_increment`, `live_index`, `tick_states`, `sets_done`, `sets_total`, `sets_open`, `session_volume`, `resting`, `rest_total_seconds`, `suggestions`, `stagnation_counts`, `record_set_ids`, `ready_for_more`, `min_full_reps`, `default_plan_weight`, `default_plan_reps`, `exercises`, `muscle_groups`, `vapid_public_key`, `has_completed_set`, `deload_applied`, `deload_pcts`, `deload_default_pct`, `partners`, `partner_status`, `session_is_shared`

Three of those are ORM objects that must be serialized rather than passed through: `session` (a `WorkoutSession`), `live_se` and `visible_exercises` (`SessionExercise`, each with `.sets` of `SessionSet` and an `.exercise`), and `exercises` (the catalogue for the add sheet).

`_live_context` (`workout.py:245`) contributes `visible_exercises` and `live_id` and is also rendered by `gym_session_queue` (`workout.py:1188`). It keeps working unchanged.

---

### Task 1: Type the session payload

Schemas only. Nothing calls them yet, so this cannot break the app.

**Files:**
- Modify: `personal_apps/features/gym/schemas.py`
- Create: `personal_apps/tests/test_gym_session_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SessionDetailPayload` with `.model_validate(dict)` and `.model_dump(mode='json')`, plus the nested `SessionMeta`, `LiveSet`, `LiveExercise`, `CatalogueExercise`, `PartnerStatus`. Task 2 builds and returns it.

- [ ] **Step 1: Read the producers before writing a line of schema**

For each of the 30 keys, find where `session_detail` computes it and note the actual type — especially `None` cases. Run:

```bash
cd personal_apps && sed -n '283,592p' features/gym/routes/workout.py
```

Write down, for each: the Python type, and whether it can be `None` or empty. Four that are known to need care:

- `record_set_ids` is a **set** in Python and must become a `list[int]` — `set` is not JSON-serializable and Pydantic will not coerce it silently under `extra='forbid'`.
- `live_se` is `None` for a session with no visible exercises.
- `rest_total_seconds` is `0` rather than `None` when nothing is resting.
- `vapid_public_key` comes from config and is `None` when unset in `.env`.

- [ ] **Step 2: Confirm the nested ORM shapes against the model, not the template**

```bash
cd personal_apps && sed -n "$(grep -n 'class SessionSet' models.py | cut -d: -f1),+25p" models.py
cd personal_apps && sed -n "$(grep -n 'class SessionExercise' models.py | cut -d: -f1),+30p" models.py
```

Type only the columns the template actually reads. `extra='forbid'` applies to what you *pass in*, so the builder in Task 2 constructs these dicts explicitly rather than dumping the ORM row — that is the point, and it is what keeps a new database column from silently widening the payload.

- [ ] **Step 3: Write the failing test**

`personal_apps/tests/test_gym_session_schema.py`:

```python
"""The live-workout JSON contract.

Mirrors what session_detail already computes. Every model forbids extra
fields on purpose: a field added to the route and not to the schema should
fail here rather than silently vanish from the payload and leave the screen
missing a number.
"""
import pytest
from pydantic import ValidationError

from features.gym.schemas import SessionDetailPayload


def _minimal():
    """A session with one exercise, one incomplete set -- the shape a freshly
    started workout has."""
    return {
        'session': {
            'id': 1, 'started_at': '2026-08-08T10:00:00', 'finished_at': None,
            'is_deload': False, 'deload_pct': None,
            'rest_ends_at': None, 'resting_set_id': None,
            'template_id': None, 'template_name': None,
        },
        'visible_exercises': [{
            'id': 10, 'exercise_id': 5, 'name': 'Bankdrücken',
            'muscle_group': 'Brust', 'position': 1, 'skipped': False,
            'is_unilateral': False, 'rest_seconds': 90, 'increment': 2.5,
            'sets': [{
                'id': 100, 'weight': 60.0, 'reps': 8, 'completed': False,
                'base_weight': None, 'is_record': False,
            }],
        }],
        'live_id': 10, 'live_index': 1, 'live_increment': 2.5,
        'tick_states': [], 'sets_done': 0, 'sets_total': 1, 'sets_open': 1,
        'session_volume': 0.0, 'resting': False, 'rest_total_seconds': 0,
        'suggestions': {}, 'stagnation_counts': {}, 'record_set_ids': [],
        'ready_for_more': {}, 'min_full_reps': 5,
        'default_plan_weight': 20.0, 'default_plan_reps': 8,
        'exercises': [{'id': 5, 'name': 'Bankdrücken', 'muscle_group': 'Brust'}],
        'muscle_groups': ['Brust'], 'vapid_public_key': None,
        'has_completed_set': False, 'deload_applied': False,
        'deload_pcts': [10, 20], 'deload_default_pct': 20,
        'partners': [], 'partner_status': [], 'session_is_shared': False,
    }


def test_accepts_a_fresh_session():
    payload = SessionDetailPayload.model_validate(_minimal())
    assert payload.live_id == 10
    assert payload.visible_exercises[0].sets[0].reps == 8


def test_accepts_a_session_with_nothing_live():
    """Every exercise skipped or finished leaves live_id None -- the screen
    still renders, so the schema must allow it."""
    data = _minimal()
    data['live_id'] = None
    data['live_index'] = 0
    assert SessionDetailPayload.model_validate(data).live_id is None


def test_rejects_an_unknown_field():
    data = _minimal()
    data['surprise'] = 1
    with pytest.raises(ValidationError, match='surprise'):
        SessionDetailPayload.model_validate(data)


def test_record_set_ids_is_a_list_not_a_set():
    """It is a set in the route. A set is not JSON-serializable, so the
    builder converts it -- if that conversion is ever dropped, the endpoint
    500s at jsonify() rather than here, which is much harder to read."""
    data = _minimal()
    data['record_set_ids'] = [100, 101]
    payload = SessionDetailPayload.model_validate(data)
    assert payload.model_dump(mode='json')['record_set_ids'] == [100, 101]


def test_round_trips_to_json_mode():
    dumped = SessionDetailPayload.model_validate(_minimal()).model_dump(mode='json')
    assert dumped['session']['started_at'].startswith('2026-08-08')
    assert dumped['visible_exercises'][0]['name'] == 'Bankdrücken'
```

- [ ] **Step 4: Run it and watch it fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_session_schema.py -q
```

Expected: `ImportError: cannot import name 'SessionDetailPayload'`.

- [ ] **Step 5: Write the models**

Append to `personal_apps/features/gym/schemas.py`, reusing the existing `_Model` base (which already sets `extra='forbid'`).

**This step deliberately does not pre-write all 30 fields, unlike the rest of this plan and unlike step 1.** That is a considered choice, not an omission. Step 1's schema was written ahead of time from template usage and was wrong in five places — `axis_lo`/`axis_hi` missing, `is_main` missing, `e1rm`/`started_at` missing from each point, and `state` typed `str` when `None` is a documented value. Every one of those would have been an `extra='forbid'` failure or a crash, and the last one shipped past a green suite. Writing this schema from anything other than the producer reproduces that. Step 1 above is the instruction: read the 310 lines, record each type, then type it.

The fixture in Step 3 is illustrative of the *shape*; the route is authoritative on the *types*.

Field-by-field notes that matter:

```python
class LiveSet(_Model):
    id: int
    weight: float
    reps: int
    completed: bool
    # Non-NULL exactly when this set's weight is deload-scaled. It is what
    # `deload_applied` is derived from -- the session's is_deload flag is not,
    # because a session flagged after a set was logged keeps its full weights.
    base_weight: float | None
    is_record: bool
```

```python
class SessionDetailPayload(_Model):
    ...
    # A set in the route; a list here. json.dumps cannot serialize a set, so
    # the builder converts and this type is what makes that conversion
    # non-optional.
    record_set_ids: list[int]
    # 0 when nothing is resting, never None -- the bar divides by it.
    rest_total_seconds: int
    # None when VAPID_PUBLIC_KEY is unset in .env, which is the normal state
    # on a fresh checkout.
    vapid_public_key: str | None
```

- [ ] **Step 6: Run the tests**

```bash
cd personal_apps && python -m pytest tests/test_gym_session_schema.py -q
```

Expected: `5 passed`.

- [ ] **Step 7: Run the full suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `548 passed` — 543 plus the 5 new.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/features/gym/schemas.py personal_apps/tests/test_gym_session_schema.py
git commit -m "feat(gym): type the live-workout JSON contract with Pydantic"
```

---

### Task 2: Extract the payload builder and add the endpoint

The move that matters. `session_detail`'s body becomes a builder both routes call.

**Files:**
- Modify: `personal_apps/features/gym/routes/workout.py:283-592`
- Modify: `personal_apps/tests/test_gym_ownership.py` (~line 340, the route table)
- Create: `personal_apps/tests/test_gym_session_json.py`

**Interfaces:**
- Consumes: `SessionDetailPayload` from Task 1.
- Produces: `_session_payload(session_) -> SessionDetailPayload`, exported from `features.gym.routes` for tests. New route `GET /gym/session/<int:session_id>/detail.json`.

- [ ] **Step 1: Write the failing test**

`personal_apps/tests/test_gym_session_json.py`:

```python
"""The live-workout JSON endpoint.

It must agree with the page, which is why both call _session_payload. The
breadth test at the bottom is the one that matters: step 1 shipped a crash
past a green suite because every test sampled the first record.
"""
import json
import re

import pytest

from conftest import _admin_id, acting_as


def _a_session_id():
    from app import app as flask_app
    from models import WorkoutSession
    with flask_app.app_context():
        row = (WorkoutSession.query.filter_by(user_id=_admin_id())
               .order_by(WorkoutSession.id.desc()).first())
        assert row is not None, 'the dev database needs at least one session'
        return row.id


def test_returns_the_payload_shape(client):
    response = client.get(f'/gym/session/{_a_session_id()}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) >= {
        'session', 'visible_exercises', 'live_id', 'sets_done', 'sets_total',
        'resting', 'record_set_ids', 'exercises', 'session_is_shared',
    }


def test_agrees_with_the_page(client):
    """Both call _session_payload, so the live exercise cannot differ."""
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import owned_session

    session_id = _a_session_id()
    with flask_app.app_context():
        with acting_as(_admin_id()):
            direct = _session_payload(owned_session(session_id))

    from_endpoint = client.get(f'/gym/session/{session_id}/detail.json').get_json()
    assert from_endpoint['live_id'] == direct.live_id
    assert from_endpoint['sets_total'] == direct.sets_total


def test_every_session_builds_a_valid_payload():
    """Breadth, not a sample. An unfinished session, a finished one, a deload,
    a shared one and an empty one all reach different branches, and whichever
    sorts first is not representative of any of them."""
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import my_sessions, owned_session

    failures = []
    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions().all()]
            assert ids, 'the dev database needs sessions'
            for session_id in ids:
                try:
                    _session_payload(owned_session(session_id))
                except Exception as exc:
                    failures.append(f'{session_id}: {exc}')
    assert not failures, 'payload failed for:\n' + '\n'.join(failures)


def test_every_session_page_renders(client):
    from app import app as flask_app
    from features.gym.scope import my_sessions

    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions().all()]

    bad = [(i, client.get(f'/gym/session/{i}').status_code) for i in ids]
    assert all(status == 200 for _, status in bad), \
        f'non-200 responses: {[p for p in bad if p[1] != 200]}'


def test_requires_a_login(anon_client):
    response = anon_client.get(f'/gym/session/{_a_session_id()}/detail.json')
    assert response.status_code in (302, 401, 403)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_session_json.py -q
```

Expected: 404s and `ImportError` for `_session_payload`.

- [ ] **Step 3: Extract the builder**

In `workout.py`, rename the body of `session_detail` into `_session_payload(session_)` placed immediately above it. It keeps the finished-session early return? **No** — that branch renders `session_finished.html` and is a different page. Leave it in the route:

```python
@gym_bp.route('/gym/session/<int:session_id>')
@login_required
def session_detail(session_id):
    session_ = owned_session(session_id)
    if session_.finished_at:
        # The finished workout is its own page and its own payload; it is
        # ported in a later step, not this one.
        ...unchanged early-return block...
    payload = _session_payload(session_)
    context = payload.model_dump()
    # The template still runs datetimes through |local and reaches into ORM
    # relationships, so it keeps receiving the objects alongside the payload.
    # Step 2c is what removes this.
    return render_template(
        'gym/session_detail.html', session=session_, live_se=live_se, **context)
```

**If the template turns out to need an ORM object the payload flattens** — likely, since it reads `se.exercise.name` and similar — pass that object through as it is passed today and note it in the commit. Do not reshape the template: that is step 2c's job, and doing it here makes this diff unreviewable.

- [ ] **Step 4: Add the endpoint**

```python
@gym_bp.route('/gym/session/<int:session_id>/detail.json')
@login_required
def gym_session_detail_json(session_id):
    """The live workout as JSON.

    Distinct from gym_session_sync, which answers only "has the structure
    changed" for the follower's poll. This is the whole screen.
    """
    session_ = owned_session(session_id)
    return jsonify(_session_payload(session_).model_dump(mode='json'))
```

- [ ] **Step 5: Register the route for ownership checking**

In `personal_apps/tests/test_gym_ownership.py`, beside the other session entries:

```python
    ('GET',  '/gym/session/{}/detail.json',   'session_id'),
```

Without this, `test_every_id_taking_gym_route_is_covered_by_a_table` fails. With it, the suite verifies the route rejects another user's session.

- [ ] **Step 6: Export the builder**

In `personal_apps/features/gym/routes/__init__.py`, add `_session_payload` to the `from .workout import ...` line.

- [ ] **Step 7: Run the new tests**

```bash
cd personal_apps && python -m pytest tests/test_gym_session_json.py -q
```

Expected: `5 passed`.

- [ ] **Step 8: Run the full suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `553 passed`.

- [ ] **Step 9: Prove the page did not change**

The session screen is the most complex in the app and this task rewrote how its context is built. Render it before and after and diff, the way step 1's Task 3 did:

Write `personal_apps/scratchpad/render_sessions.py`:

```python
"""Dump every session page's HTML, for before/after comparison."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tests'))

from app import app as flask_app          # noqa: E402
from conftest import _admin_id            # noqa: E402
from models import WorkoutSession         # noqa: E402

flask_app.config['TESTING'] = True
with flask_app.app_context():
    user_id = _admin_id()
    ids = [s.id for s in WorkoutSession.query.filter_by(user_id=user_id)
           .order_by(WorkoutSession.id).all()]

out = []
with flask_app.test_client() as client:
    with client.session_transaction() as session:
        session['user_id'] = user_id
    for session_id in ids:
        response = client.get(f'/gym/session/{session_id}')
        out.append(f'===== {session_id} status={response.status_code} =====')
        out.append(response.get_data(as_text=True))

pathlib.Path(sys.argv[1]).write_text('\n'.join(out), encoding='utf-8')
print(f'wrote {sys.argv[1]}: {len(ids)} sessions')
```

Then:

```bash
cd personal_apps && python scratchpad/render_sessions.py after.html && git stash push -- features/gym/routes/workout.py && python scratchpad/render_sessions.py before.html && git stash pop && diff before.html after.html | head -40
```

Any difference other than `int` → `float` normalisation from Pydantic (step 1 saw `y="12"` become `y="12.0"`) is a bug in the extraction. Delete the two HTML dumps afterwards; they are not artefacts worth keeping.

- [ ] **Step 10: Commit**

```bash
git add -A personal_apps
git commit -m "feat(gym): serve the live workout as JSON, sharing its payload with the page"
```

---

## Verification checklist

- [ ] `python -m pytest tests/ -q` reports `553 passed`
- [ ] `npm test` reports `42 passed` — untouched, but cheap to confirm
- [ ] `/gym/session/<id>/detail.json` returns 200 for every session in the dev database
- [ ] The page and the endpoint agree on `live_id` for every session
- [ ] The rendered session page is unchanged apart from numeric normalisation
- [ ] The new route is in the ownership table and the suite verifies cross-user rejection

## What this deliberately does not do

- **No markup change.** `session_detail.html` keeps its 953 lines of script. Step 2c replaces them.
- **No optimistic writes.** The mutation routes still return HTML and `refreshBody` still swaps it. 2c is where that path is built.
- **No `_session_queue.html` change.** `gym_session_queue` keeps rendering the partial from `_live_context`; the follower's poll works exactly as it does now.

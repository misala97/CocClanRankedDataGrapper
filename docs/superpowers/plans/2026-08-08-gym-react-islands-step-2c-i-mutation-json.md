# Gym React Islands — Step 2c-i: Mutations Answer in JSON

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the 14 in-place mutation routes on the live workout return the full session payload as JSON when the caller asks for it, while a plain form post keeps getting exactly the redirect it gets today.

**Architecture:** One helper, `_mutation_response(session_)`, replaces the trailing `redirect(...)` in each route. It returns `jsonify(_session_payload(session_).model_dump(mode='json'))` when the request's `Accept` header asks for JSON and not HTML, and the original redirect otherwise. Content negotiation on the existing URLs rather than parallel `/json` routes: one URL, one ownership check, one place the mutation happens.

**Tech Stack:** Flask, Pydantic, pytest. No new dependencies, no frontend change.

**Spec:** `docs/superpowers/specs/2026-08-08-gym-react-islands-design.md`
**Depends on:** step 2b (`758d072`) — `_session_payload` is what this returns.

## Global Constraints

- **The existing page must not change at all.** `session_detail.html` posts plain forms and follows redirects; `refreshBody` then parses the resulting HTML. Nothing about that path may move. If a form post's behaviour changes, the change is wrong.
- **The oracle is 558 pytest + 42 vitest**, plus the byte-identical render check from 2b (`personal_apps/scratchpad/render_sessions.py`).
- **Two routes are deliberately excluded.** `gym_start` creates a session and `gym_finish_session` ends one — both are navigations to a different page, not in-place mutations, and returning a live-session payload from either would be a lie. They keep redirecting unconditionally.
- **Every route must be reachable from a session.** Some receive a set or a session-exercise id and have to walk up to the session (`set_.session_exercise.session`). Do that walk explicitly rather than re-querying by id.
- **Branch:** `dev_personal`. Never commit to `main`.

## Why content negotiation and not a second set of routes

Each of these routes carries an ownership check (`owned_set`, `owned_session_exercise`), a mutation, and in several cases a propagation rule — `_propagate_default_correction` and `_apply_typed_weight_reps` are 90 lines of behaviour between them. Duplicating a route to change only its return type duplicates all of that, and the copies drift. The 2a split exists because that already happened once at file scale.

The negotiation test is `request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html`. Both halves are needed:

- A browser form post sends `Accept: text/html,application/xhtml+xml,...,*/*;q=0.8`. `accept_json` is **true** via the `*/*` wildcard, so testing `accept_json` alone would flip every form post to JSON and break the page.
- `fetch()` with no `Accept` header sends `*/*`, which is also both. The island therefore must send `Accept: application/json` explicitly, and step 2c-iii's API client does.

---

### Task 1: The helper, and one route through it

Proves the negotiation on the smallest route before touching the other thirteen.

**Files:**
- Modify: `personal_apps/features/gym/routes/workout.py`
- Create: `personal_apps/tests/test_gym_mutation_json.py`

**Interfaces:**
- Consumes: `_session_payload(session_)` from step 2b.
- Produces: `_mutation_response(session_, endpoint, **values)` — returns a Flask response. Every mutation route in Task 2 ends with it.

- [ ] **Step 1: Write the failing test**

`personal_apps/tests/test_gym_mutation_json.py`:

```python
"""Mutations answer in JSON when asked, and redirect otherwise.

The redirect half is not a formality: session_detail.html still posts plain
forms and refreshBody still parses the HTML that comes back. Breaking that
while adding the JSON path would take the live workout screen down.
"""
import datetime as dt

import pytest

from conftest import _admin_id


JSON = {'Accept': 'application/json'}
# What a browser actually sends when a <form> is submitted. The */* at the end
# is why the negotiation cannot test accept_json alone.
FORM = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}


@pytest.fixture()
def live_session():
    """An unfinished session with one exercise and two sets, one completed."""
    from app import app as flask_app
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        user_id = _admin_id()
        exercise = (Exercise.query.filter_by(user_id=user_id)
                    .order_by(Exercise.id).first())
        assert exercise is not None, 'the dev database needs an exercise'
        session_ = WorkoutSession(user_id=user_id, started_at=dt.datetime.utcnow())
        db.session.add(session_)
        db.session.flush()
        se = SessionExercise(session_id=session_.id, exercise_id=exercise.id, position=1)
        db.session.add(se)
        db.session.flush()
        sets = [
            SessionSet(session_exercise_id=se.id, weight=60.0, reps=8, completed=True),
            SessionSet(session_exercise_id=se.id, weight=60.0, reps=8, completed=False),
        ]
        db.session.add_all(sets)
        db.session.commit()
        ids = {'session': session_.id, 'se': se.id,
               'done_set': sets[0].id, 'open_set': sets[1].id}

    yield ids

    with flask_app.app_context():
        row = db.session.get(WorkoutSession, ids['session'])
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def test_a_form_post_still_redirects(client, live_session):
    """The path the current page uses. If this breaks, the live workout
    screen breaks."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=FORM)
    assert response.status_code in (302, 303)


def test_a_json_request_gets_the_session_payload(client, live_session):
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON)
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    body = response.get_json()
    assert body['session']['id'] == live_session['session']
    assert 'visible_exercises' in body


def test_the_payload_reflects_the_mutation(client, live_session):
    """The point of returning it: the client needs the post-mutation state,
    not the state it already had."""
    before = client.get(
        f"/gym/session/{live_session['session']}/detail.json").get_json()
    assert before['sets_done'] == 1

    after = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON).get_json()
    assert after['sets_done'] == 2


def test_a_bare_fetch_does_not_get_json(client, live_session):
    """fetch() with no Accept header sends */*, which accepts HTML too. The
    island has to opt in explicitly, and this pins that it must."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers={'Accept': '*/*'})
    assert response.status_code in (302, 303)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd personal_apps && python -m pytest tests/test_gym_mutation_json.py -q
```

Expected: the two redirect tests pass already; the two JSON tests fail with a 302 where 200 was expected.

- [ ] **Step 3: Write the helper**

In `workout.py`, immediately below `_session_payload`:

```python
def _mutation_response(session_, endpoint, **values):
    """JSON for the island, the original redirect for a plain form post.

    Negotiated on the existing URL rather than served from a parallel /json
    route: each of these routes carries an ownership check, a mutation and in
    several cases a propagation rule, and duplicating a route to change only
    its return type duplicates all of that. The 2a split exists because that
    kind of duplication already drifted once.

    Both halves of the test are load-bearing. A browser form post sends
    `Accept: text/html,...,*/*;q=0.8`, so accept_json is TRUE via the wildcard
    -- testing it alone would flip every form post to JSON and take the page
    down. A bare fetch() sends */* and lands here too, which is why the island
    must send `Accept: application/json` explicitly.
    """
    wants_json = (request.accept_mimetypes.accept_json
                  and not request.accept_mimetypes.accept_html)
    if wants_json:
        return jsonify(_session_payload(session_).model_dump(mode='json'))
    return redirect(url_for(endpoint, **values))
```

- [ ] **Step 4: Route one mutation through it**

In `gym_toggle_set_complete`, replace the trailing redirect with:

```python
    return _mutation_response(
        set_.session_exercise.session, 'gym.session_detail',
        session_id=set_.session_exercise.session_id)
```

Walk up the relationship rather than re-querying: the row is already loaded, and a second query by id would be a second chance to get the ownership scope wrong.

- [ ] **Step 5: Run the tests**

```bash
cd personal_apps && python -m pytest tests/test_gym_mutation_json.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Run the full suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `562 passed`.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/routes/workout.py personal_apps/tests/test_gym_mutation_json.py
git commit -m "feat(gym): let a mutation answer in JSON when the caller asks"
```

---

### Task 2: The remaining thirteen routes

Mechanical, once the helper is proven. Each route's final `redirect(...)` becomes `_mutation_response(...)` with the same endpoint and values.

**Files:**
- Modify: `personal_apps/features/gym/routes/workout.py`
- Modify: `personal_apps/tests/test_gym_mutation_json.py`

**Interfaces:**
- Consumes: `_mutation_response` from Task 1.
- Produces: nothing new. Every in-place mutation now negotiates.

- [ ] **Step 1: Convert each route**

The thirteen, with how each reaches its session:

| Route | Session reached via |
|---|---|
| `gym_add_session_exercise` | `session_` already in scope |
| `gym_replace_session_exercise` | `se.session` |
| `gym_update_session_exercise_rest` | `se.session` |
| `gym_update_session_meta` | `session_` already in scope |
| `gym_update_session_exercise_meta` | `se.session` |
| `gym_update_exercise_increment` | `se.session` |
| `gym_add_set` | `se.session` |
| `gym_delete_session_exercise` | `se.session` |
| `gym_toggle_skip_session_exercise` | `se.session` |
| `gym_delete_set` | `set_.session_exercise.session` |
| `gym_update_set` | `set_.session_exercise.session` |
| `gym_reorder_session_exercises` | `session_` already in scope |
| `gym_skip_rest` | `session_` already in scope |

`gym_start` and `gym_finish_session` are **not** on this list and must not be converted — both navigate to a different page, and answering either with a live-session payload would describe a session that is no longer live.

**A route that deletes the thing the payload describes still returns the payload of the surviving session.** `gym_delete_session_exercise` removes an exercise; the response is the session without it, which is exactly what the client needs to render. Capture the session reference *before* the delete, or the relationship walk fails on a detached row.

- [ ] **Step 2: Extend the tests to cover every route**

Add to `test_gym_mutation_json.py` — a table-driven test, so a route added later without negotiation is caught:

```python
def test_every_in_place_mutation_negotiates(client, live_session):
    """Table-driven so a new mutation route added without negotiation shows
    up here rather than being discovered from the client side."""
    ids = live_session
    cases = [
        (f"/gym/session/{ids['session']}/exercises/add", {'exercise_id': ''}),
        (f"/gym/session-exercise/{ids['se']}/rest", {'rest_seconds': '90'}),
        (f"/gym/sessions/{ids['session']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercises/{ids['se']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercise/{ids['se']}/increment", {'weight_increment': '2.5'}),
        (f"/gym/session-exercise/{ids['se']}/sets/add", {}),
        (f"/gym/session-exercise/{ids['se']}/skip", {}),
        (f"/gym/set/{ids['open_set']}/update", {'weight': '62.5', 'reps': '8'}),
        (f"/gym/session/{ids['session']}/exercises/reorder", {'order': str(ids['se'])}),
        (f"/gym/session/{ids['session']}/rest/skip", {}),
    ]
    problems = []
    for url, data in cases:
        response = client.post(url, data=data, headers=JSON)
        if response.status_code != 200 or response.mimetype != 'application/json':
            problems.append(f'{url}: {response.status_code} {response.mimetype}')
    assert not problems, 'routes that did not answer in JSON:\n' + '\n'.join(problems)


def test_the_two_navigations_still_redirect(client, live_session):
    """gym_start and gym_finish_session go to a different page. Answering
    either with a live-session payload would describe a session that is no
    longer live."""
    response = client.post(
        f"/gym/session/{live_session['session']}/finish", headers=JSON)
    assert response.status_code in (302, 303)
```

`gym_delete_session_exercise` and `gym_delete_set` are left out of the table on purpose: they destroy the fixture's rows and would make the other cases order-dependent. Give each its own test with its own fixture.

- [ ] **Step 3: Run the tests**

```bash
cd personal_apps && python -m pytest tests/test_gym_mutation_json.py -q
```

Expected: all passing. A failure names the exact URL that did not negotiate.

- [ ] **Step 4: Run the full suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

- [ ] **Step 5: Prove the page still behaves**

```bash
cd personal_apps && python scratchpad/render_sessions.py after.html
```

Stash the change, render `before.html`, pop, and diff. Expected: zero difference, as in 2b. The form-post path was not touched, so anything else means the negotiation is leaking into it.

- [ ] **Step 6: Commit**

```bash
git add -A personal_apps
git commit -m "feat(gym): every in-place workout mutation answers in JSON on request"
```

---

## Verification checklist

- [ ] A plain form post to every mutation still returns a redirect
- [ ] `Accept: */*` returns a redirect, not JSON
- [ ] `Accept: application/json` returns the post-mutation session payload
- [ ] `gym_start` and `gym_finish_session` redirect regardless of `Accept`
- [ ] The 37 session pages render byte-identically
- [ ] Full pytest suite green

## What this deliberately does not do

- **No frontend change.** No component, store or fetch call. 2c-ii and 2c-iii are those.
- **No optimistic behaviour.** These routes still do the work before answering; the optimism lives in the client.
- **No change to `gym_session_sync`.** The follower's poll is a separate mechanism and keeps working as it does.

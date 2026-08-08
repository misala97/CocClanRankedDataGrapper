# Gym React Islands — Step 2a: Split `routes.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `personal_apps/features/gym/routes.py` (2912 lines) into a `features/gym/routes/` package split by domain, with **zero behaviour change and zero call-site change**.

**Architecture:** A package whose `__init__.py` creates `gym_bp`, imports each domain module so its routes register, and re-exports the private helpers that 11 test call sites import. Every module receives the blueprint by importing it from `._blueprint`, which holds nothing else — that is what keeps the imports acyclic.

**Tech Stack:** Flask blueprints, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-08-gym-react-islands-design.md` — "`features/gym/routes.py` is 2863 lines and will grow before it shrinks. Splitting it by concern is part of the `session_detail` step, not a separate project."

**Why first:** `session_detail` alone is 310 lines (`routes.py:591-900`). Step 2b adds a Pydantic payload builder on top of it, the way `_exercise_detail_payload` sits above `exercise_detail`. Adding that to an already-2900-line module is the wrong order.

## Global Constraints

- **No behaviour change whatsoever.** This is a move. If a diff changes anything other than which file code lives in and which imports it needs, it is out of scope.
- **The 543-test suite is the oracle.** Run `python -m pytest tests/ -q` from `personal_apps/` after every task. Any new failure means the move was wrong — do not adjust the test.
- **`from features.gym.routes import <name>` must keep working** for every name any test or script imports today. Verified list, all of which `__init__.py` must re-export:
  `gym_bp`, `load_performed`, `_to_stack_steps`, `_clean_equipment`, `_clean_secondary_groups`, `_exercise_detail_payload`, `_chart_geometry`, `_session_rest_entries`, `_last_full_performance`, `_to_increment`.
  Call sites: `app.py:50`, `scripts/make_chart_fixture.py:29`, `tests/test_gym_equipment.py:116,127,135`, `tests/test_gym_exercise_detail_json.py:28,75,126`, `tests/test_gym_rest.py:303`, `tests/test_gym_routes_smoke.py:277,386,407,591,597`, `tests/test_gym_schemas.py:111,114`.
- **Do not "improve" code while moving it.** No renames, no reformatting, no comment edits, no dead-code removal. Those are separate commits if wanted at all. A move commit that also edits logic cannot be reviewed.
- **Comments move with their code.** This file's comments carry the reasoning for past bugs; losing them loses the reason.
- **Branch:** `dev_personal`. Never commit to `main`.
- **On moving code, the plan gives exact source line ranges and a destination rather than reproducing thousands of lines.** That is the instruction, not a placeholder — copy the range verbatim.

---

## File structure

`features/gym/routes.py` becomes `features/gym/routes/`:

| Module | Responsibility | Source lines |
|---|---|---|
| `_blueprint.py` | Creates `gym_bp` and nothing else. Exists so every module can import the blueprint without importing each other. | new |
| `helpers.py` | Request-value coercion and cleaning, the `local` template filter, the nav context processor, `_get_active_session` | 82–222, 40–41 (`gym_service_worker`) |
| `history.py` | The performed-history pipeline: `load_performed`, `_to_performed`, `_session_rest_entries`, `performed_from_session` | 274–386 |
| `workout.py` | The live workout: `gym_heute`, `gym_start`, `_live_context`, `session_detail`, and every set / session-exercise mutation | 387–1500, plus 223–273 (`_template_exercises_from_session`, `_cancel_pending_push`, `_schedule_rest`) |
| `partners.py` | Invites and shared sessions | 1497–1728 |
| `session_admin.py` | Deload, summary, delete, template save / rename / delete | 1729–1947 |
| `reports.py` | `gym_verlauf`, `gym_statistik`, `gym_export`, `_progression_view` | 1948–2269 |
| `catalogue.py` | `gym_uebungen`, exercise add / update / delete | 2270–2390, 2778–2872 |
| `exercise_detail.py` | `_default_position`, `_chart_geometry`, `_exercise_detail_payload`, and the three exercise-detail routes | 2391–2777 |
| `push_routes.py` | Push subscribe / unsubscribe | 2873–end |
| `__init__.py` | Imports every module above so routes register, then re-exports the public surface | new |

Ordering inside `__init__.py` matters: `_blueprint` first, then modules, because importing a module is what registers its routes onto `gym_bp`.

---

### Task 1: Package skeleton, helpers, and history

Creates the package and moves the two lowest-coupling groups. Ends with the app importing and the full suite green — proving the package structure works before any route moves.

**Files:**
- Create: `personal_apps/features/gym/routes/__init__.py`
- Create: `personal_apps/features/gym/routes/_blueprint.py`
- Create: `personal_apps/features/gym/routes/helpers.py`
- Create: `personal_apps/features/gym/routes/history.py`
- Create: `personal_apps/features/gym/routes/_legacy.py` (temporary, holds everything not yet moved)
- Delete: `personal_apps/features/gym/routes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gym_bp` (Flask `Blueprint`) from `features.gym.routes._blueprint`. Every later task's module does `from ._blueprint import gym_bp`. `helpers.py` produces `_to_float(value, fallback=None)`, `_to_increment(value)`, `_to_int(value, fallback=None)`, `_clean_muscle_group(value, current=None)`, `_clean_equipment(raw, current='stack')`, `_to_stack_steps(raw)`, `_clean_secondary_groups(values, primary)`, `_get_active_session()`. `history.py` produces `load_performed(exercise_ids=None, since=None, include_active=False, exclude_session_exercise_ids=None)`, `_to_performed(session_exercise, completed_sets)`, `_session_rest_entries(session_)`, `performed_from_session(session_)`.

- [ ] **Step 1: Record the baseline**

Run from `personal_apps/`:

```bash
python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`. Write the number down — every later step compares against it. If it is not 543, stop and find out why before moving anything.

- [ ] **Step 2: Create the directory and the blueprint module**

```bash
mkdir -p personal_apps/features/gym/routes
```

`personal_apps/features/gym/routes/_blueprint.py`:

```python
"""The gym blueprint, alone in its own module.

Every routes/ module imports gym_bp from here rather than from the package,
so importing one module never pulls in the others. That is the whole reason
this file exists and the only thing it may ever contain -- adding a helper
here would reintroduce the cycle it was created to break.
"""
from flask import Blueprint

gym_bp = Blueprint('gym', __name__)
```

Verified against the pre-split file: `routes.py:37` is exactly `gym_bp = Blueprint('gym', __name__)` — no `url_prefix`, no `template_folder`. The line above reproduces it. If that ever changes, copy it verbatim; a mismatch here silently changes every URL in the app.

- [ ] **Step 3: Move the file wholesale into the package as `_legacy.py`**

```bash
cd personal_apps && git mv features/gym/routes.py features/gym/routes/_legacy.py
```

Using `git mv` keeps the history attached, so `git log --follow` still works on the moved code.

Then in `_legacy.py`, replace the blueprint construction line (found in Step 2) with:

```python
from ._blueprint import gym_bp
```

- [ ] **Step 4: Write the package `__init__.py`**

`personal_apps/features/gym/routes/__init__.py`:

```python
"""Gym routes, split by domain.

Importing a module here is what registers its routes onto gym_bp, so every
module must be imported below even though the names are unused -- hence the
noqa markers.

The re-exports at the bottom are not decoration. Eleven test call sites and
scripts/make_chart_fixture.py import these private helpers from
`features.gym.routes`, and keeping that path working is what let this split
happen without touching a single caller.
"""
from ._blueprint import gym_bp

from . import helpers          # noqa: F401
from . import history          # noqa: F401
from . import _legacy          # noqa: F401

from .helpers import (         # noqa: F401
    _to_float, _to_increment, _to_int, _clean_muscle_group,
    _clean_equipment, _to_stack_steps, _clean_secondary_groups,
    _get_active_session,
)
from .history import (         # noqa: F401
    load_performed, _to_performed, _session_rest_entries,
    performed_from_session,
)
from ._legacy import (         # noqa: F401
    _exercise_detail_payload, _chart_geometry, _last_full_performance,
)

__all__ = ['gym_bp']
```

- [ ] **Step 5: Verify the app still imports and every test passes**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`, identical to Step 1.

If this fails with `ImportError: cannot import name '_last_full_performance' from '._legacy'`, that name is re-exported by the original file from `seeding.py` rather than defined in it — keep the same re-export in `_legacy.py`.

- [ ] **Step 6: Commit the structural move on its own**

```bash
git add -A personal_apps/features/gym/routes personal_apps/features/gym/routes.py
git commit -m "refactor(gym): make features/gym/routes a package"
```

Committing the structure separately from the content moves means a bisect can tell "the package broke it" from "moving workout.py broke it".

- [ ] **Step 7: Move helpers out of `_legacy.py`**

Cut lines 82–222 of the original (`_to_float` through `inject_gym_nav_context`) plus the `/sw.js` route at 40–41 and its function, and paste into `personal_apps/features/gym/routes/helpers.py` with this header:

```python
"""Request-value coercion, the `local` template filter, and the nav context.

Every value here arrives from a form post or a query string, so each function
answers the same question: what does this mean when the input is missing,
blank, or not a number. Moved verbatim from the pre-split routes.py.
"""
```

Add whatever imports the moved code needs (check each function body) plus:

```python
from ._blueprint import gym_bp
```

Delete the moved lines from `_legacy.py`, and add `from .helpers import *`-style explicit imports there for any name `_legacy.py` still uses — prefer explicit names over a star import so the coupling stays visible.

- [ ] **Step 8: Run the suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`.

A `NameError` here names exactly which helper `_legacy.py` still needs imported. Add it and re-run.

- [ ] **Step 9: Move the history pipeline**

Cut lines 274–386 of the original (`load_performed`, `_to_performed`, `_session_rest_entries`, `performed_from_session`) into `personal_apps/features/gym/routes/history.py` with this header:

```python
"""The performed-history pipeline.

Turns stored sessions into the `performed` rows that seeding, stats and the
exercise pages all read. Kept apart from the routes that call it because
sharing.py and seeding.py need it too, and neither may import a module that
registers routes.
"""
```

Delete them from `_legacy.py` and import what it still needs.

- [ ] **Step 10: Run the suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`.

- [ ] **Step 11: Commit**

```bash
git add -A personal_apps/features/gym/routes
git commit -m "refactor(gym): move request helpers and the history pipeline out of _legacy"
```

---

### Task 2: The live workout module

The largest move and the one step 2b builds on. `workout.py` becomes the file the React port actually touches.

**Files:**
- Create: `personal_apps/features/gym/routes/workout.py`
- Modify: `personal_apps/features/gym/routes/_legacy.py` (remove the moved range)
- Modify: `personal_apps/features/gym/routes/__init__.py` (import the new module)

**Interfaces:**
- Consumes: `gym_bp` from `._blueprint`; `_to_int`, `_to_float`, `_to_increment` from `.helpers`; `load_performed`, `performed_from_session` from `.history`.
- Produces: `_live_context(session_)` — the dict `session_detail.html` and `_session_queue.html` both render from. Step 2b's payload builder wraps exactly this.

- [ ] **Step 1: Move the range**

Cut lines 223–273 (`_template_exercises_from_session`, `_cancel_pending_push`, `_schedule_rest`) and 387–1500 (`gym_heute` through `gym_session_queue`) of the original into `personal_apps/features/gym/routes/workout.py`, with this header:

```python
"""The live workout: starting a session, the session screen, and every
mutation the screen performs.

This is the domain the React port replaces. `_live_context` is the seam --
it is what session_detail.html renders from today and what step 2b's JSON
payload will wrap, so the page and the endpoint cannot disagree about which
exercise is live.

Moved verbatim from the pre-split routes.py.
"""
```

Add the imports the moved code needs.

- [ ] **Step 2: Register it**

In `__init__.py`, add `from . import workout  # noqa: F401` after the `history` import and before `_legacy`.

- [ ] **Step 3: Run the suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`.

- [ ] **Step 4: Verify no route was lost**

A move that drops a route registration passes most tests silently. Check the count directly:

```bash
cd personal_apps && python -c "
from app import app
gym = sorted(str(r) for r in app.url_map.iter_rules() if str(r).startswith('/gym') or str(r)=='/sw.js')
print(len(gym), 'gym routes')
for r in gym: print(' ', r)
" | head -60
```

Expected: **44 rules** — measured against the pre-split tree on 2026-08-08, not estimated. Any other number means a route registration was lost in the move, which most tests would not catch.

- [ ] **Step 5: Commit**

```bash
git add -A personal_apps/features/gym/routes
git commit -m "refactor(gym): move the live workout routes into workout.py"
```

---

### Task 3: Partners, session admin, reports, catalogue, exercise detail, push

The remaining moves. Each is the same shape as Task 2, so they share one task: a reviewer rejecting one would reject all of them for the same reason.

**Files:**
- Create: `personal_apps/features/gym/routes/partners.py`, `session_admin.py`, `reports.py`, `catalogue.py`, `exercise_detail.py`, `push_routes.py`
- Delete: `personal_apps/features/gym/routes/_legacy.py`
- Modify: `personal_apps/features/gym/routes/__init__.py`

**Interfaces:**
- Consumes: `gym_bp`, plus helpers and history as each module needs.
- Produces: `_exercise_detail_payload(exercise, raw_position)` and `_chart_geometry(series, pr_e1rm=None)` now live in `exercise_detail.py`; `__init__.py` re-exports both, so `scripts/make_chart_fixture.py` and three test call sites keep working unchanged.

- [ ] **Step 1: Move each range into its module, one at a time, running the suite after each**

| Destination | Source lines | Module docstring |
|---|---|---|
| `partners.py` | 1497–1728 | `"""Invites and shared sessions: inviting a partner, and the confirm / accept / decline flow they land in."""` |
| `session_admin.py` | 1729–1947 | `"""What you do to a session rather than in it: deload, summary, delete, and saving it back to a template."""` |
| `reports.py` | 1948–2269 | `"""Read-only history and statistics pages, plus the JSON export."""` |
| `catalogue.py` | 2270–2390, 2778–2872 | `"""The exercise catalogue: the list page and exercise create / update / delete."""` |
| `exercise_detail.py` | 2391–2777 | `"""The single-exercise page. _chart_geometry turns history into SVG coordinates -- inline SVG rather than a canvas, because a canvas can only read a resolved rgb() and a themed canvas silently loses its colours."""` |
| `push_routes.py` | 2873–end | `"""Web-push subscribe and unsubscribe for this device."""` |

After each single move:

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed` every time. Do not batch the moves — a failure after six moves at once tells you nothing about which one caused it.

- [ ] **Step 2: Delete `_legacy.py` and finish `__init__.py`**

`_legacy.py` should now be empty apart from imports. Delete it, and update `__init__.py` to its final form:

```python
"""Gym routes, split by domain.

Importing a module here is what registers its routes onto gym_bp, so every
module must be imported below even though the names are unused -- hence the
noqa markers.

The re-exports at the bottom are not decoration. Eleven test call sites and
scripts/make_chart_fixture.py import these private helpers from
`features.gym.routes`, and keeping that path working is what let this split
happen without touching a single caller.
"""
from ._blueprint import gym_bp

from . import helpers          # noqa: F401
from . import history          # noqa: F401
from . import workout          # noqa: F401
from . import partners         # noqa: F401
from . import session_admin    # noqa: F401
from . import reports          # noqa: F401
from . import catalogue        # noqa: F401
from . import exercise_detail  # noqa: F401
from . import push_routes      # noqa: F401

from .helpers import (         # noqa: F401
    _to_float, _to_increment, _to_int, _clean_muscle_group,
    _clean_equipment, _to_stack_steps, _clean_secondary_groups,
    _get_active_session,
)
from .history import (         # noqa: F401
    load_performed, _to_performed, _session_rest_entries,
    performed_from_session,
)
from .workout import _live_context                       # noqa: F401
from .exercise_detail import (                           # noqa: F401
    _exercise_detail_payload, _chart_geometry, _default_position,
)
# Re-exported, not defined here. The pre-split routes.py imported it from
# seeding.py (line 33) and three tests import it from `features.gym.routes`,
# so the path has to survive the split. seeding.py owns it because sharing.py
# needs it too and cannot import a module that registers routes.
from ..seeding import _last_full_performance             # noqa: F401

__all__ = ['gym_bp']
```

- [ ] **Step 3: Verify the whole public surface**

```bash
cd personal_apps && python -c "
from features.gym.routes import (
    gym_bp, load_performed, _to_stack_steps, _clean_equipment,
    _clean_secondary_groups, _exercise_detail_payload, _chart_geometry,
    _session_rest_entries, _last_full_performance, _to_increment,
)
print('all re-exports resolve')
from app import app
n = len([r for r in app.url_map.iter_rules() if str(r).startswith('/gym') or str(r)=='/sw.js'])
print(n, 'gym routes')
"
```

Expected: `all re-exports resolve` and the same route count recorded in Task 2 Step 4.

- [ ] **Step 4: Confirm no file is oversized and none is empty**

```bash
cd personal_apps && wc -l features/gym/routes/*.py | sort -n
```

Expected: no module over ~1200 lines, none at 0. `workout.py` will be the largest by a wide margin — that is correct, it is the largest domain, and step 2c shrinks it.

- [ ] **Step 5: Run the full suite and the frontend suite**

```bash
cd personal_apps && python -m pytest tests/ -q 2>&1 | tail -2
```

Expected: `543 passed`.

```bash
cd personal_apps && npm test 2>&1 | tail -3
```

Expected: `42 passed`. Unchanged — no frontend file was touched — but it is cheap and proves it.

- [ ] **Step 6: Verify the exercise page still renders identically**

The split touched `_exercise_detail_payload`'s module. Re-run step 1's screenshot check:

```bash
python shoot_exercise_detail.py post-split
```

from the scratchpad, then pixel-diff `post-split` against `node24`. Expected: zero difference on the empty-state pages, and chart pages within the animation-noise band (~400 px) established in step 1. Anything else means the move changed behaviour.

- [ ] **Step 7: Commit**

```bash
git add -A personal_apps/features/gym/routes
git commit -m "refactor(gym): finish the routes split and drop _legacy"
```

---

## Verification checklist

- [ ] `python -m pytest tests/ -q` reports `543 passed`, the same as before the split
- [ ] `npm test` reports `42 passed`
- [ ] The gym route count matches the pre-split count exactly
- [ ] Every name in the Global Constraints re-export list imports from `features.gym.routes`
- [ ] `features/gym/routes.py` no longer exists and `_legacy.py` is gone
- [x] ~~`git log --follow` on a domain module reaches pre-split commits~~ — **this was wrong and was removed.** Git follows renames one-to-one; splitting one file into nine is one-to-many, so no domain module can carry the old history. What actually survives: the `routes.py → routes/_legacy.py` rename preserves it up to `_legacy`'s deletion, and `git log -S'<some code>'` finds any moved line's real history. Use those.
- [ ] The exercise detail page pixel-diffs clean against the pre-split baseline

## What this deliberately does not do

- **No logic changes.** Not one. Anything that looks wrong while moving gets noted, not fixed.
- **No `session_detail` shrinking.** It stays 310 lines here; step 2c is what replaces it.
- **No new tests.** The existing 543 are the oracle; adding tests during a move makes the move unreviewable.

# Gym React Islands — Step 1: `exercise_detail` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `personal_apps/templates/gym/exercise_detail.html` to a React island, carrying all one-time frontend setup (Vite, TypeScript, Vitest, the Flask asset helper, Pydantic schemas, the deploy change) so that steps 2–8 of the spec inherit a proven pipeline.

**Architecture:** Flask keeps the route and the URL. The template becomes a thin shell that embeds the page payload as `<script type="application/json">` and mounts one React root. A new Pydantic-validated JSON endpoint serves the same payload for later refetches. Nothing about routing, auth, or navigation changes.

**Tech Stack:** React 19, TypeScript, Vite, TanStack Query, Zustand, Vitest + @testing-library/react, Pydantic v2, Flask/Jinja (unchanged), pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-gym-react-islands-design.md`

## Global Constraints

- **No intentional visual change.** Layout, spacing, and German copy stay byte-identical unless a deviation is listed in the task. Not a pixel gate — see the spec's Verification section.
- **All UI copy is German.** Copy strings move from Jinja to TSX verbatim, including `·` separators, `—` em-dashes, and comma decimal separators (`12,5` not `12.5`).
- **Decimal formatting:** German. `'%.1f'|format(x)` + `.replace('.', ',')` in Jinja becomes `x.toFixed(1).replace('.', ',')` in TSX. Thousands separators use `.` — `'{:,.0f}'.format(v).replace(',', '.')` becomes `Math.round(v).toLocaleString('de-DE')`.
- **The chart is inline SVG and must stay inline SVG.** It reads `var(--done)`, `var(--record)`, `var(--unlit)`, `var(--edge)` directly. A canvas cannot resolve CSS variables — this codebase has been bitten by that before. Do not introduce a charting library.
- **Existing CSS is untouched.** `static/gym/gym.css` (3613 lines) keeps every class name. Components emit the same class names the Jinja emitted.
- **Branch:** `dev_personal`. Never commit to `main`.
- **Python:** existing venv, `personal_apps/requirements.txt`. **Node:** 22 LTS.
- **Tests run from `personal_apps/`:** `python -m pytest tests/ -q`. The suite runs against the real local dev database (see `tests/conftest.py`), which is disposable dev data.

---

### Task 1: Frontend toolchain and the Flask asset helper

Establishes Vite, TypeScript and Vitest, and gives Jinja a way to resolve hashed bundle filenames. Ends with a build that produces a bundle and a Flask helper that can find it — no page changes yet.

**Files:**
- Create: `personal_apps/package.json`
- Create: `personal_apps/vite.config.ts`
- Create: `personal_apps/tsconfig.json`
- Create: `personal_apps/vite_assets.py`
- Create: `personal_apps/static/gym/src/entries/smoke.tsx`
- Create: `personal_apps/tests/test_vite_assets.py`
- Modify: `.gitignore` (repo root)
- Modify: `personal_apps/app.py` (register the Jinja global)

**Interfaces:**
- Consumes: nothing.
- Produces: `vite_asset(entry: str) -> str` as a Jinja global, returning a URL path such as `/static/gym/dist/assets/exercise-a1b2c3d4.js`. Raises `ViteManifestError` when the manifest or the entry is missing. Later tasks call it as `{{ vite_asset('exercise') }}`.

- [ ] **Step 1: Add the build ignores**

Append to `.gitignore` at the repo root:

```
node_modules/
personal_apps/static/gym/dist/
```

The VPS deploy does `git reset --hard origin/main`, so `dist/` must be built there after the reset. Committing it would conflict on every `dev_personal` → `main` merge.

- [ ] **Step 2: Create `personal_apps/package.json`**

```json
{
  "name": "personal-apps-gym",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite build --watch",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^5.2.0",
    "jsdom": "^25.0.1",
    "typescript": "^5.7.2",
    "vite": "^7.3.6",
    "vitest": "^4.1.10"
  }
}
```

**Versions corrected during execution.** The originally-planned Vite 6 / Vitest 2 pulled an esbuild with advisory GHSA-67mh-4wv8-2f99 — 5 reported vulnerabilities, all the same root cause, and only exploitable against an esbuild dev server this project never runs. Bumping to current majors clears it to 0. Vite 8 was tried first and reverted: it requires Node ^20.19 || >=22.12 and the dev machine is on 20.18. Vite 7 declares the same floor but builds fine on 20.18 with a warning — **local Node should move to 22 LTS**, matching the VPS target in Task 7, before this gets deeper.

`build` runs `tsc --noEmit` first so a type error fails the build rather than shipping.

**TanStack Query and Zustand are deliberately absent.** The spec names both, but this page embeds its payload and never refetches, and its only client state is one boolean (the stack-steps field). Installing a library no file imports is dead weight a reviewer should reject. Both arrive with `session_detail` in step 2, which is the page that actually needs them.

- [ ] **Step 3: Create `personal_apps/vite.config.ts`**

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

// defineConfig comes from vitest/config, not vite: the `test` block below is
// not part of Vite's own config type and fails to type-check against it.
//
// import.meta.url rather than __dirname -- package.json sets "type": "module",
// so this file is ESM and __dirname does not exist in it.
const here = fileURLToPath(new URL('.', import.meta.url))

// One build, one entry per gym page. Only `smoke` exists now; steps 2-8 of the
// spec add their own entries here. Output lands in static/gym/dist/ with a
// manifest that vite_assets.py reads for the hashed filenames.
//
// `root` is left at this directory rather than pointed at static/gym/src, so
// that outDir stays inside the root and Vite does not warn about emptying a
// directory outside it. The consequence is that manifest keys are paths
// relative to here -- 'static/gym/src/entries/<name>.tsx' -- which is what
// vite_assets.resolve_asset looks up.
export default defineConfig({
  plugins: [react()],
  base: '/static/gym/dist/',
  build: {
    outDir: resolve(here, 'static/gym/dist'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        smoke: resolve(here, 'static/gym/src/entries/smoke.tsx'),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [resolve(here, 'static/gym/src/test-setup.ts')],
  },
})
```

**Three corrections applied during execution**, all verified against a real build: `defineConfig` must come from `vitest/config`; `__dirname` does not exist in an ESM config; and `root` stays at `personal_apps/` so `outDir` is inside it. That last one sets the manifest key format below.

- [ ] **Step 4: Create `personal_apps/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["static/gym/src/**/*.ts", "static/gym/src/**/*.tsx"]
}
```

- [ ] **Step 5: Create the test setup file and the smoke entry**

`personal_apps/static/gym/src/test-setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

`personal_apps/static/gym/src/entries/smoke.tsx`:

```tsx
// Proves the toolchain end to end: TSX compiles, React mounts, the hashed
// bundle resolves through vite_asset(). Deleted in Task 6 once a real entry
// exists.
import { createRoot } from 'react-dom/client'

const el = document.getElementById('gym-root')
if (el) {
  createRoot(el).render(<p data-testid="smoke">ok</p>)
}
```

- [ ] **Step 6: Install and build**

Run from `personal_apps/`:

```bash
npm install && npm run build
```

Expected: `static/gym/dist/.vite/manifest.json` exists and contains a `entries/smoke.tsx` key whose `file` value is a hashed path like `assets/smoke-a1b2c3d4.js`.

- [ ] **Step 7: Write the failing test for the asset helper**

`personal_apps/tests/test_vite_assets.py`:

```python
"""The Jinja side of the Vite build. The VPS deploy does `git reset --hard`
and then builds, so a missing manifest means the build did not run -- it must
fail loudly at render time rather than emitting a <script src=""> that 404s
silently."""
import json

import pytest

from vite_assets import ViteManifestError, resolve_asset


def test_resolves_hashed_filename(tmp_path):
    manifest = tmp_path / '.vite' / 'manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        'static/gym/src/entries/exercise.tsx': {'file': 'assets/exercise-a1b2c3d4.js'},
    }), encoding='utf-8')

    assert resolve_asset('exercise', dist_dir=tmp_path) == \
        '/static/gym/dist/assets/exercise-a1b2c3d4.js'


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ViteManifestError, match='npm run build'):
        resolve_asset('exercise', dist_dir=tmp_path)


def test_unknown_entry_raises(tmp_path):
    manifest = tmp_path / '.vite' / 'manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({}), encoding='utf-8')

    with pytest.raises(ViteManifestError, match='exercise'):
        resolve_asset('exercise', dist_dir=tmp_path)
```

- [ ] **Step 8: Run the test to verify it fails**

Run from `personal_apps/`:

```bash
python -m pytest tests/test_vite_assets.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vite_assets'`.

- [ ] **Step 9: Write `personal_apps/vite_assets.py`**

```python
"""Resolve Vite's hashed bundle filenames for Jinja.

Vite content-hashes every entry, so the template cannot name the file. The
build writes `.vite/manifest.json` mapping source paths to output paths; this
reads it.

The manifest is read once and cached, because in production it never changes
while the process lives -- the VPS deploy rebuilds and then restarts the
service. `flask --debug` reloads on file change, so development picks up a
rebuild on the next reload.
"""
import json
from pathlib import Path

_DIST = Path(__file__).parent / 'static' / 'gym' / 'dist'
_cache: dict[str, str] = {}


class ViteManifestError(RuntimeError):
    """The bundle for an entry could not be resolved."""


def resolve_asset(entry: str, dist_dir: Path | None = None) -> str:
    """URL path for a built entry, e.g. resolve_asset('exercise').

    `entry` is the basename under static/gym/src/entries/, without extension.
    """
    dist = dist_dir or _DIST
    cache_key = f'{dist}:{entry}'
    if cache_key in _cache:
        return _cache[cache_key]

    manifest_path = dist / '.vite' / 'manifest.json'
    if not manifest_path.exists():
        raise ViteManifestError(
            f'No Vite manifest at {manifest_path}. Run `npm run build` in '
            f'personal_apps/ -- on the VPS this runs after `git reset --hard`, '
            f'which deletes the untracked dist/ directory.')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    key = f'static/gym/src/entries/{entry}.tsx'
    record = manifest.get(key)
    if record is None:
        raise ViteManifestError(
            f'Entry {entry!r} (looked for {key!r}) is not in the Vite '
            f'manifest. Add it to rollupOptions.input in vite.config.ts.')

    url = f'/static/gym/dist/{record["file"]}'
    _cache[cache_key] = url
    return url
```

- [ ] **Step 10: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vite_assets.py -q
```

Expected: PASS, 3 passed.

- [ ] **Step 11: Register the Jinja global**

In `personal_apps/app.py`, after the blueprint registrations (near line 56, after `app.register_blueprint(gym_bp)`), add:

```python
from vite_assets import resolve_asset

# Templates call {{ vite_asset('exercise') }} for the hashed bundle path.
app.jinja_env.globals['vite_asset'] = resolve_asset
```

- [ ] **Step 12: Run the whole suite**

```bash
python -m pytest tests/ -q
```

Expected: PASS, no new failures against the pre-task baseline.

- [ ] **Step 13: Commit**

```bash
git add .gitignore personal_apps/package.json personal_apps/package-lock.json personal_apps/vite.config.ts personal_apps/tsconfig.json personal_apps/vite_assets.py personal_apps/static/gym/src personal_apps/tests/test_vite_assets.py personal_apps/app.py
git commit -m "build(gym): add Vite, TypeScript and the Jinja asset helper"
```

---

### Task 2: Pydantic schemas for the exercise-detail payload

Types the contract before anything serves it. Mirrors what `stats.exercise_progress()` and `_chart_geometry()` already return, so nothing is invented.

**Files:**
- Create: `personal_apps/features/gym/schemas.py`
- Create: `personal_apps/tests/test_gym_schemas.py`
- Modify: `personal_apps/requirements.txt`

**Interfaces:**
- Consumes: `vite_asset` from Task 1 (not directly — Task 2 is independent).
- Produces: `ExerciseDetailPayload` with `.model_validate(dict)` and `.model_dump(mode='json')`. Task 3 calls both. Field names are the JSON keys the React code in Tasks 4–5 reads.

- [ ] **Step 1: Add Pydantic to requirements**

In `personal_apps/requirements.txt`, add after `SQLAlchemy`:

```
pydantic
```

Then run:

```bash
pip install pydantic
```

- [ ] **Step 2: Write the failing test**

`personal_apps/tests/test_gym_schemas.py`:

```python
"""The exercise-detail JSON contract. These assert the shape the React page
reads, so a rename on the Python side fails here rather than rendering an
empty page."""
import pytest
from pydantic import ValidationError

from features.gym.schemas import ExerciseDetailPayload


def _minimal():
    """The empty-history case: a brand new exercise with nothing logged."""
    return {
        'exercise': {
            'id': 1, 'name': 'Bankdrücken', 'muscle_group': 'Brust',
            'is_unilateral': False, 'default_rest_seconds': 90,
            'weight_increment': 2.5, 'equipment': 'barbell',
            'bar_weight': 20.0, 'stack_kg': None,
            'secondary_muscle_groups': ['Trizeps'],
        },
        'table': [], 'series': [], 'available_positions': [],
        'selected_position': None, 'selected_position_is_default': False,
        'selected_position_reason': None,
        'last_overall': None, 'pr_weight': None, 'pr_e1rm': None,
        'last_progression': None,
        'state': 'neu', 'sessions_since_pr': 0, 'chart': None,
        'chip_class': None, 'chip_label': None, 'can_delete': True,
        'muscle_groups': ['Brust', 'Trizeps'],
        'equipment_labels': {'barbell': 'Langhantel'},
    }


def test_accepts_empty_history():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    assert payload.exercise.name == 'Bankdrücken'
    assert payload.chart is None
    assert payload.table == []


def test_accepts_a_populated_row():
    data = _minimal()
    data['table'] = [{
        'session_id': 7, 'started_at': '2026-08-01T18:30:00',
        'position': 2, 'is_deload': False, 'sets_display': '3 × 8',
        'best_weight': 80.0, 'volume': 1920.0, 'e1rm': 100.0,
    }]
    data['available_positions'] = [2]
    payload = ExerciseDetailPayload.model_validate(data)
    assert payload.table[0].session_id == 7
    assert payload.table[0].e1rm == 100.0


def test_rejects_a_row_missing_e1rm():
    data = _minimal()
    data['table'] = [{
        'session_id': 7, 'started_at': '2026-08-01T18:30:00',
        'position': 2, 'is_deload': False, 'sets_display': '3 × 8',
        'best_weight': 80.0, 'volume': 1920.0,
    }]
    with pytest.raises(ValidationError, match='e1rm'):
        ExerciseDetailPayload.model_validate(data)


def test_round_trips_to_json_mode():
    payload = ExerciseDetailPayload.model_validate(_minimal())
    dumped = payload.model_dump(mode='json')
    assert dumped['exercise']['name'] == 'Bankdrücken'
    assert dumped['chart'] is None
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
python -m pytest tests/test_gym_schemas.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'features.gym.schemas'`.

- [ ] **Step 4: Write `personal_apps/features/gym/schemas.py`**

```python
"""The exercise-detail JSON contract.

Mirrors what stats.exercise_progress() and routes._chart_geometry() already
return -- this types an existing shape rather than designing a new one. The
React page in static/gym/src/ reads exactly these field names.

Datetimes serialize as ISO 8601 through model_dump(mode='json'); the client
formats them for display, because German date formatting is a presentation
concern and the server should not decide it twice.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ExerciseMeta(_Model):
    """The editable identity of the exercise -- backs both the header and the
    edit sheet."""
    id: int
    name: str
    muscle_group: str | None
    is_unilateral: bool
    default_rest_seconds: int | None
    weight_increment: float | None
    equipment: str | None
    bar_weight: float | None
    stack_kg: list[float] | None
    secondary_muscle_groups: list[str] | None


class SessionRow(_Model):
    """One performed session, as rendered in the Einheiten log."""
    session_id: int
    started_at: datetime
    position: int
    is_deload: bool
    sets_display: str
    best_weight: float
    volume: float
    e1rm: float


class LastOverall(_Model):
    """Newest session of the WHOLE exercise, never scoped to the position
    filter -- identity metadata is not filtered."""
    started_at: datetime
    position: int


class WeightPR(_Model):
    # session_id is required: exercise_detail.html:233 matches the record row
    # on it. Two sessions on one day both matched a date-based test and both
    # went gold, so the match is on the session, never the date.
    weight: float
    reps: int
    position: int
    started_at: datetime
    session_id: int


class E1rmPR(_Model):
    e1rm: float
    weight: float
    reps: int
    position: int
    started_at: datetime
    session_id: int


class ChartPoint(_Model):
    x: float
    y: float
    is_best: bool
    is_deload: bool


class ChartTick(_Model):
    y_pct: float
    text: str


class ChartSeries(_Model):
    position: int
    opacity: float
    width: float
    label_x: float
    label_y: float
    label_anchor: str
    points: list[ChartPoint]


class ChartGeometry(_Model):
    """SVG coordinates from routes._chart_geometry(). None when there is
    nothing to draw."""
    width: float
    height: float
    lo: float
    hi: float
    ticks: list[ChartTick]
    dates: list[str]
    series: list[ChartSeries]
    has_record: bool
    has_deload: bool


class ExerciseDetailPayload(_Model):
    exercise: ExerciseMeta
    table: list[SessionRow]
    series: list[dict]
    available_positions: list[int]
    selected_position: int | None
    selected_position_is_default: bool
    selected_position_reason: str | None
    last_overall: LastOverall | None
    pr_weight: WeightPR | None
    pr_e1rm: E1rmPR | None
    last_progression: SessionRow | None
    state: str
    sessions_since_pr: int | None
    chart: ChartGeometry | None
    chip_class: str | None
    chip_label: str | None
    can_delete: bool
    muscle_groups: list[str]
    equipment_labels: dict[str, str]
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_gym_schemas.py -q
```

Expected: PASS, 4 passed.

If `test_accepts_a_populated_row` fails on an unexpected key, that means the real `exercise_progress()` output has a field the schema does not list. Add it to `SessionRow` — `extra='forbid'` is deliberate, so the schema and the producer cannot drift silently.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/schemas.py personal_apps/tests/test_gym_schemas.py personal_apps/requirements.txt
git commit -m "feat(gym): type the exercise-detail JSON contract with Pydantic"
```

---

### Task 3: The JSON endpoint, sharing position logic with the HTML route

`exercise_detail` resolves the position filter with ~25 lines of logic (`routes.py:2634-2660`). The JSON route must use exactly the same rule or the two views will disagree about which slot is shown. Extract it once, call it twice.

**Files:**
- Modify: `personal_apps/features/gym/routes.py:2631-2680`
- Create: `personal_apps/tests/test_gym_exercise_detail_json.py`

**Interfaces:**
- Consumes: `ExerciseDetailPayload` from Task 2.
- Produces: `_exercise_detail_payload(exercise, raw_position) -> ExerciseDetailPayload`, called by both `exercise_detail` (Task 6) and `gym_exercise_detail_json`. New route `GET /gym/exercises/<int:exercise_id>/detail.json`.

- [ ] **Step 1: Write the failing test**

`personal_apps/tests/test_gym_exercise_detail_json.py`:

```python
"""The exercise-detail JSON endpoint. It must agree with the HTML route about
which position is selected -- they share _exercise_detail_payload precisely so
the default-slot rule cannot drift between them."""
from conftest import _admin_id


def _an_exercise_id():
    from app import app as flask_app
    from models import GymExercise
    with flask_app.app_context():
        ex = GymExercise.query.filter_by(user_id=_admin_id()).order_by(GymExercise.id).first()
        assert ex is not None, 'the dev database needs at least one gym exercise'
        return ex.id


def test_returns_the_payload_shape(client):
    response = client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) >= {
        'exercise', 'table', 'available_positions', 'selected_position',
        'chart', 'state', 'can_delete', 'muscle_groups', 'equipment_labels',
    }
    assert body['exercise']['id'] == _an_exercise_id()


def test_position_all_clears_the_filter(client):
    response = client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json?position=all')
    assert response.status_code == 200
    assert response.get_json()['selected_position'] is None


def test_agrees_with_the_html_route_on_the_default_slot(client):
    """The whole reason the helper is shared. If these disagree, the page and
    any later refetch would show different slots."""
    exercise_id = _an_exercise_id()
    from app import app as flask_app
    from features.gym.routes import _exercise_detail_payload
    from features.gym.scope import owned_exercise
    with flask_app.test_request_context():
        from flask import session as flask_session
        flask_session['user_id'] = _admin_id()
        payload = _exercise_detail_payload(owned_exercise(exercise_id), None)

    json_response = client.get(f'/gym/exercises/{exercise_id}/detail.json')
    assert json_response.get_json()['selected_position'] == payload.selected_position


def test_rejects_another_users_exercise(anon_client):
    response = anon_client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code in (302, 401, 403)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_gym_exercise_detail_json.py -q
```

Expected: FAIL — 404 on the new URL, and `ImportError` for `_exercise_detail_payload`.

If the `from features.gym.scope import owned_exercise` import fails, find the real module with:

```bash
grep -rn "def owned_exercise" personal_apps/
```

and correct the import in the test.

- [ ] **Step 3: Extract the payload builder**

In `personal_apps/features/gym/routes.py`, replace the body of `exercise_detail` (currently `routes.py:2631-2680`) with a call to a new helper defined immediately above it:

```python
def _exercise_detail_payload(exercise, raw_position):
    """Everything the exercise page shows, for one exercise and one requested
    position.

    Shared by the HTML route and the JSON route so the default-slot rule below
    cannot drift between them -- the two would otherwise silently disagree
    about which slot the page is showing.

    The default view is one slot, not all of them. "Alle" draws every position
    at once, which is the comparison view -- useful when you want it, and a
    poor thing to land on: the answer to "how is this lift going" is a single
    line, and overlapping slots bury it.

    Which slot: the best-performing one, meaning highest best-e1RM -- but only
    among slots with at least two sessions. A slot used once is a data point,
    not a track record. With nothing qualifying, fall back to the slot the
    exercise actually lives in (the most sessions).
    """
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)

    default_reason = None
    if raw_position == 'all':
        position = None
    else:
        position = _to_int(raw_position)
        if position is None:
            position, default_reason = _default_position(
                stats.exercise_progress(rows, position=None)['series'])

    # Whether the page CHOSE this slot or was told to. Without it the chart and
    # the session list were silently filtered on arrival: a pill was lit that
    # the reader never pressed.
    position_is_default = (raw_position is None and position is not None)
    if not position_is_default:
        default_reason = None

    data = stats.exercise_progress(rows, position=position)
    chip_class, chip_label = EXERCISE_STATE_CHIP.get(data['state'], (None, None))

    return ExerciseDetailPayload.model_validate({
        'exercise': {
            'id': exercise.id,
            'name': exercise.name,
            'muscle_group': exercise.muscle_group,
            'is_unilateral': exercise.is_unilateral,
            'default_rest_seconds': exercise.default_rest_seconds,
            'weight_increment': exercise.weight_increment,
            'equipment': exercise.equipment,
            'bar_weight': exercise.bar_weight,
            'stack_kg': exercise.stack_kg,
            'secondary_muscle_groups': exercise.secondary_muscle_groups,
        },
        'selected_position_is_default': position_is_default,
        'selected_position_reason': default_reason,
        'chart': _chart_geometry(data['series'], data.get('pr_e1rm')),
        'chip_class': chip_class,
        'chip_label': chip_label,
        # Only offer deletion when nothing depends on it.
        'can_delete': not exercise.session_exercises and not exercise.template_exercises,
        'muscle_groups': list(MUSCLE_GROUPS),
        'equipment_labels': dict(EQUIPMENT_LABELS),
        **data,
    })
```

Add the import at the top of `routes.py`, beside the other `features.gym` imports:

```python
from features.gym.schemas import ExerciseDetailPayload
```

- [ ] **Step 4: Point the HTML route at the helper**

Replace `exercise_detail`'s body so it keeps rendering the existing template unchanged for now — Task 6 swaps the template, not this task:

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return render_template(
        'gym/exercise_detail.html',
        exercise=exercise,
        muscle_groups=payload.muscle_groups,
        equipment_labels=payload.equipment_labels,
        chip_class=payload.chip_class,
        chip_label=payload.chip_label,
        selected_position_is_default=payload.selected_position_is_default,
        selected_position_reason=payload.selected_position_reason,
        chart=payload.chart.model_dump() if payload.chart else None,
        can_delete=payload.can_delete,
        **stats.exercise_progress(
            load_performed(exercise_ids=[exercise.id], include_active=True),
            position=payload.selected_position),
    )
```

The template still receives the raw `exercise_progress()` output because it reads `datetime` objects through the `|local` filter. Task 6 removes this entirely.

- [ ] **Step 5: Add the JSON route**

Immediately after `gym_exercise_progress_json` (`routes.py:2685`), add:

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>/detail.json')
@login_required
def gym_exercise_detail_json(exercise_id):
    """The full exercise page as JSON. Distinct from progress.json above,
    which backs the in-workout quick-glance modal and falls back to all-time
    data when a slot is empty -- this one honours the filter exactly, because
    the page's pills must mean what they say."""
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return jsonify(payload.model_dump(mode='json'))
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/test_gym_exercise_detail_json.py -q
```

Expected: PASS, 4 passed.

- [ ] **Step 7: Run the whole suite — the HTML page must be unchanged**

```bash
python -m pytest tests/ -q
```

Expected: PASS with no new failures. `test_gym_routes_smoke.py` covers `/gym/exercises/<id>` and proves the refactor did not change the rendered page.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/features/gym/routes.py personal_apps/tests/test_gym_exercise_detail_json.py
git commit -m "feat(gym): serve exercise detail as JSON, sharing position logic with the page"
```

---

### Task 4: The chart component

The most exacting part of the port: ~85 lines of SVG whose colours, opacities and radii each carry a documented contrast decision. Built and unit-tested in isolation; not mounted on the real page until Task 6.

**Files:**
- Create: `personal_apps/static/gym/src/types.ts`
- Create: `personal_apps/static/gym/src/components/ExerciseChart.tsx`
- Create: `personal_apps/static/gym/src/components/ExerciseChart.test.tsx`

**Interfaces:**
- Consumes: `ChartGeometry` from Task 2's schema, mirrored in TypeScript.
- Produces: `ExerciseChart({ chart, sessionCount, firstDate, lastDate })` and the shared type module `types.ts` exporting `ExerciseDetailPayload`, `ChartGeometry`, `SessionRow`, `ExerciseMeta`. Task 5 imports all of these.

- [ ] **Step 1: Create the shared types**

`personal_apps/static/gym/src/types.ts`:

```ts
// Mirrors features/gym/schemas.py exactly. If a field is added there, add it
// here -- the Pydantic model uses extra='forbid', so drift fails loudly on
// the Python side first.

export interface ExerciseMeta {
  id: number
  name: string
  muscle_group: string | null
  is_unilateral: boolean
  default_rest_seconds: number | null
  weight_increment: number | null
  equipment: string | null
  bar_weight: number | null
  stack_kg: number[] | null
  secondary_muscle_groups: string[] | null
}

export interface SessionRow {
  session_id: number
  started_at: string
  position: number
  is_deload: boolean
  sets_display: string
  best_weight: number
  volume: number
  e1rm: number
}

export interface WeightPR {
  weight: number
  reps: number
  position: number
  started_at: string
  session_id: number
}

export interface E1rmPR {
  e1rm: number
  weight: number
  reps: number
  position: number
  started_at: string
  session_id: number
}

export interface ChartPoint {
  x: number
  y: number
  is_best: boolean
  is_deload: boolean
}

export interface ChartSeries {
  position: number
  opacity: number
  width: number
  label_x: number
  label_y: number
  label_anchor: string
  points: ChartPoint[]
}

export interface ChartGeometry {
  width: number
  height: number
  lo: number
  hi: number
  ticks: { y_pct: number; text: string }[]
  dates: string[]
  series: ChartSeries[]
  has_record: boolean
  has_deload: boolean
}

export interface ExerciseDetailPayload {
  exercise: ExerciseMeta
  table: SessionRow[]
  // Present in the payload but unread here: the page draws from `chart`, which
  // is this same data already turned into SVG coordinates. Typed loosely on
  // purpose rather than omitted, so the interface stays a true mirror of
  // schemas.ExerciseDetailPayload.
  series: unknown[]
  available_positions: number[]
  selected_position: number | null
  selected_position_is_default: boolean
  selected_position_reason: string | null
  last_overall: { started_at: string; position: number } | null
  pr_weight: WeightPR | null
  pr_e1rm: E1rmPR | null
  last_progression: SessionRow | null
  state: string
  sessions_since_pr: number | null
  chart: ChartGeometry | null
  chip_class: string | null
  chip_label: string | null
  can_delete: boolean
  muscle_groups: string[]
  equipment_labels: Record<string, string>
}
```

- [ ] **Step 2: Create the German formatting helpers**

`personal_apps/static/gym/src/format.ts`:

```ts
// German number and date formatting, matching what the Jinja filters produced.
// Comma decimal separator, dot thousands separator, dd.MM.yyyy dates.

export function kg1(value: number): string {
  return value.toFixed(1).replace('.', ',')
}

export function volume(value: number): string {
  return Math.round(value).toLocaleString('de-DE')
}

export function shortDate(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}
```

- [ ] **Step 3: Write the failing test**

`personal_apps/static/gym/src/components/ExerciseChart.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExerciseChart } from './ExerciseChart'
import type { ChartGeometry } from '../types'

const chart: ChartGeometry = {
  width: 320, height: 160, lo: 90, hi: 110,
  ticks: [{ y_pct: 6, text: '110' }, { y_pct: 94, text: '90' }],
  dates: ['01.06.2026', '01.07.2026', '01.08.2026'],
  has_record: true, has_deload: true,
  series: [{
    position: 2, opacity: 1, width: 2,
    label_x: 300, label_y: 20, label_anchor: 'end',
    points: [
      { x: 10, y: 140, is_best: false, is_deload: false },
      { x: 160, y: 80, is_best: false, is_deload: true },
      { x: 310, y: 20, is_best: true, is_deload: false },
    ],
  }],
}

describe('ExerciseChart', () => {
  it('draws one line segment fewer than it has points', () => {
    const { container } = render(
      <ExerciseChart chart={chart} sessionCount={3}
        firstDate="01.06.2026" lastDate="01.08.2026" />)
    // 3 gridlines + 2 segments between 3 points
    expect(container.querySelectorAll('line')).toHaveLength(5)
  })

  it('dots any segment touching a deload point', () => {
    const { container } = render(
      <ExerciseChart chart={chart} sessionCount={3}
        firstDate="01.06.2026" lastDate="01.08.2026" />)
    const dashed = [...container.querySelectorAll('line')]
      .filter((l) => l.getAttribute('stroke-dasharray') === '3 4')
    // both segments touch the middle deload point
    expect(dashed).toHaveLength(2)
  })

  it('rings the record dot and leaves the deload dot hollow', () => {
    const { container } = render(
      <ExerciseChart chart={chart} sessionCount={3}
        firstDate="01.06.2026" lastDate="01.08.2026" />)
    const circles = [...container.querySelectorAll('circle')]
    const record = circles.find((c) => c.classList.contains('chart__pr'))
    const deload = circles.find((c) => c.getAttribute('fill') === 'none')
    expect(record).toHaveAttribute('r', '6')
    expect(record).toHaveAttribute('stroke', 'var(--done)')
    expect(deload).toHaveAttribute('stroke', 'var(--unlit)')
  })

  it('shows the deload legend key only when a deload is present', () => {
    render(<ExerciseChart chart={{ ...chart, has_deload: false }}
      sessionCount={3} firstDate="01.06.2026" lastDate="01.08.2026" />)
    expect(screen.queryByText('Deload')).not.toBeInTheDocument()
  })

  it('omits the position label when only one series is drawn', () => {
    render(<ExerciseChart chart={chart} sessionCount={3}
      firstDate="01.06.2026" lastDate="01.08.2026" />)
    expect(screen.queryByText('P2')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run from `personal_apps/`:

```bash
npm test
```

Expected: FAIL — cannot resolve `./ExerciseChart`.

- [ ] **Step 5: Write the component**

`personal_apps/static/gym/src/components/ExerciseChart.tsx`:

```tsx
import type { ChartGeometry } from '../types'
import { kg1 } from '../format'

interface Props {
  chart: ChartGeometry
  sessionCount: number
  firstDate: string
  lastDate: string
}

/**
 * Inline SVG, not a canvas. It inherits the palette directly -- a canvas can
 * only read a resolved rgb(), so a themed canvas silently loses its colours,
 * which this project has been bitten by once already.
 *
 * One group per slot. Opacity, not hue: the palette is fixed at three semantic
 * hues and a slot number is not a state. A deload is a real point but not a
 * real trend, so its legs are dotted and grey -- a solid line through a
 * deliberately light week reads as a collapse that never happened.
 */
export function ExerciseChart({ chart, sessionCount, firstDate, lastDate }: Props) {
  const mid = Math.trunc(chart.height / 2)
  const bottom = chart.height - 10

  return (
    <div className="chart">
      {/* The y labels are HTML, not SVG text: the SVG is stretched to the
          container, so anything inside it scales with the drawing and would
          read at a different size on every screen. */}
      <div className="chart__y" aria-hidden="true">
        {chart.ticks.map((tick) => (
          <span className="label" key={tick.text} style={{ top: `${tick.y_pct}%` }}>
            {tick.text}
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${Math.trunc(chart.width)} ${Math.trunc(chart.height)}`}
        role="img"
        aria-label={`Verlauf des e1RM über ${sessionCount} Einheiten, ${firstDate} bis ${lastDate}. Zwischen ${kg1(chart.lo)} und ${kg1(chart.hi)} Kilogramm. Die Tabelle darunter enthält dieselben Werte.`}
      >
        <g stroke="var(--edge)" strokeWidth="1">
          <line x1="0" y1="10" x2={Math.trunc(chart.width)} y2="10" />
          <line x1="0" y1={mid} x2={Math.trunc(chart.width)} y2={mid} />
          <line x1="0" y1={bottom} x2={Math.trunc(chart.width)} y2={bottom} />
        </g>
        {/* One wrapper around every drawn series, so the whole plot wipes in as
            a single left-to-right gesture -- along the axis it is drawn on,
            which is time. The gridlines stay put: they are the frame. */}
        <g className="chart__ink">
          {chart.series.map((entry) => (
            <g opacity={entry.opacity} key={entry.position}>
              {entry.points.slice(0, -1).map((a, i) => {
                const b = entry.points[i + 1]!
                const touchesDeload = a.is_deload || b.is_deload
                return (
                  <line
                    key={`${entry.position}-seg-${i}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={touchesDeload ? 'var(--unlit)' : 'var(--done)'}
                    strokeWidth={entry.width}
                    strokeLinecap="round"
                    {...(touchesDeload ? { strokeDasharray: '3 4' } : {})}
                  />
                )
              })}
              {entry.points.map((point, i) => (
                /* The record dot is ringed. Gold on the light panel measures
                   1,86:1 -- the weakest mark on the chart -- and a ring in
                   --done (7,29:1) gives the shape a readable edge without
                   giving up the gold that means "record" everywhere else.

                   Deload dots are HOLLOW: --unlit is an ink, and filling with
                   it made the deload the darkest mark on a chart where it is
                   meant to be the quietest. */
                <circle
                  key={`${entry.position}-pt-${i}`}
                  cx={point.x} cy={point.y}
                  r={point.is_best ? 6 : 3.5}
                  {...(point.is_best ? {
                    className: 'chart__pr',
                    style: { '--at': (point.x / chart.width).toFixed(3) } as React.CSSProperties,
                    stroke: 'var(--done)',
                    strokeWidth: 1.5,
                  } : {})}
                  {...(point.is_deload ? { stroke: 'var(--unlit)', strokeWidth: 1.5 } : {})}
                  fill={point.is_deload ? 'none' : (point.is_best ? 'var(--record)' : 'var(--done)')}
                />
              ))}
              {chart.series.length > 1 && (
                <text
                  x={entry.label_x} y={entry.label_y} fill="var(--done)"
                  textAnchor={entry.label_anchor} fontSize="10" fontWeight="700"
                >
                  P{entry.position}
                </text>
              )}
            </g>
          ))}
        </g>
      </svg>
      {/* Three marks, not two: with only the ends labelled there is nothing to
          judge the middle of the line against. */}
      <div className="chart__axis">
        {chart.dates.map((d) => <span className="label" key={d}>{d}</span>)}
      </div>
      <div className="chart__legend">
        <span className="key">
          <span className="key__dot" style={{ background: 'var(--done)' }} />e1RM
        </span>
        {chart.has_record && (
          <span className="key">
            <span className="key__dot" style={{ background: 'var(--record)', boxShadow: '0 0 0 1.5px var(--done)' }} />Rekord
          </span>
        )}
        {chart.has_deload && (
          <span className="key">
            <span className="key__dot" style={{ background: 'transparent', boxShadow: 'inset 0 0 0 1.5px var(--unlit)' }} />Deload
          </span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
npm test
```

Expected: PASS, 5 passed.

- [ ] **Step 7: Type-check**

```bash
npx tsc --noEmit
```

Expected: no output (success).

- [ ] **Step 8: Commit**

```bash
git add personal_apps/static/gym/src/types.ts personal_apps/static/gym/src/format.ts personal_apps/static/gym/src/components/ExerciseChart.tsx personal_apps/static/gym/src/components/ExerciseChart.test.tsx
git commit -m "feat(gym): port the exercise e1RM chart to a React component"
```

---

### Task 5: The remaining page components

Header, records band, state note, position pills, session log, maintenance section, and the edit sheet. Built and tested in isolation; still not mounted.

**Files:**
- Create: `personal_apps/static/gym/src/components/Icon.tsx`
- Create: `personal_apps/static/gym/src/components/ExerciseHeader.tsx`
- Create: `personal_apps/static/gym/src/components/RecordsBand.tsx`
- Create: `personal_apps/static/gym/src/components/SessionLog.tsx`
- Create: `personal_apps/static/gym/src/components/EditSheet.tsx`
- Create: `personal_apps/static/gym/src/pages/ExerciseDetail.tsx`
- Create: `personal_apps/static/gym/src/pages/ExerciseDetail.test.tsx`

**Interfaces:**
- Consumes: `ExerciseChart` and every type from Task 4.
- Produces: `ExerciseDetailPage({ payload, nameTaken })`, the single component Task 6's entry file mounts.

- [ ] **Step 1: Write the failing page test**

`personal_apps/static/gym/src/pages/ExerciseDetail.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExerciseDetailPage } from './ExerciseDetail'
import type { ExerciseDetailPayload } from '../types'

function payload(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return {
    exercise: {
      id: 1, name: 'Bankdrücken', muscle_group: 'Brust', is_unilateral: false,
      default_rest_seconds: 90, weight_increment: 2.5, equipment: 'barbell',
      bar_weight: 20, stack_kg: null, secondary_muscle_groups: null,
    },
    table: [], series: [], available_positions: [], selected_position: null,
    selected_position_is_default: false, selected_position_reason: null,
    last_overall: null, pr_weight: null, pr_e1rm: null, last_progression: null,
    state: 'neu', sessions_since_pr: null, chart: null,
    chip_class: null, chip_label: null, can_delete: true,
    muscle_groups: ['Brust'], equipment_labels: { barbell: 'Langhantel' },
    ...over,
  }
}

const aRow = {
  session_id: 7, started_at: '2026-08-01T18:30:00', position: 2,
  is_deload: false, sets_display: '3 × 8', best_weight: 80,
  volume: 1920, e1rm: 100,
}

describe('ExerciseDetailPage', () => {
  it('shows the empty state when nothing is logged', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken={false} />)
    expect(screen.getByText(/Noch keine Sätze protokolliert/)).toBeInTheDocument()
  })

  it('names the exercise as the h1', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken={false} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bankdrücken')
  })

  it('formats volume with a German thousands separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [aRow] })} nameTaken={false} />)
    expect(screen.getByText('1.920')).toBeInTheDocument()
  })

  it('scopes the session count to the selected position', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [aRow], selected_position: 2, available_positions: [1, 2] })}
      nameTaken={false} />)
    expect(screen.getByText('Pos. 2 · 1 Einheit')).toBeInTheDocument()
  })

  it('hides the delete form when the exercise is in use', () => {
    render(<ExerciseDetailPage payload={payload({ can_delete: false })} nameTaken={false} />)
    expect(screen.queryByText('Übung löschen')).not.toBeInTheDocument()
  })

  it('reopens the edit sheet when the rename was rejected', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken />)
    expect(screen.getByText('Name nicht geändert')).toBeInTheDocument()
  })

  it('shows the stack-steps field only for stack equipment', () => {
    const { rerender } = render(
      <ExerciseDetailPage payload={payload()} nameTaken={false} />)
    expect(screen.getByLabelText(/Stack-Stufen/)).not.toBeVisible()

    rerender(<ExerciseDetailPage
      payload={payload({ exercise: { ...payload().exercise, equipment: 'stack' } })}
      nameTaken={false} />)
    expect(screen.getByLabelText(/Stack-Stufen/)).toBeVisible()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npm test
```

Expected: FAIL — cannot resolve `./ExerciseDetail`.

- [ ] **Step 3a: The shared icon set**

`templates/gym/_icon.html` is one 16px `currentColor` set used by every gym page, so it becomes a shared component now rather than later. Only the two icons this page uses are ported; each later page adds the ones it needs.

`personal_apps/static/gym/src/components/Icon.tsx`:

```tsx
/**
 * One 16px, currentColor icon set for the whole gym app. Ported from
 * templates/gym/_icon.html -- add cases as later pages need them.
 *
 * aria-hidden throughout: every call site supplies its own accessible name on
 * the surrounding <button> / <a>.
 */
const PATHS: Record<string, React.ReactNode> = {
  back: <path d="M10 3.2L5.2 8l4.8 4.8" />,
  edit: (
    <>
      <path d="M11.3 2.2a1.6 1.6 0 0 1 2.3 2.3l-7.4 7.4-3 .7.7-3z" />
      <path d="M10.2 3.3l2.3 2.3" />
    </>
  ),
}

export function Icon({ name }: { name: keyof typeof PATHS }) {
  return (
    <svg className={`icon icon-${name}`} viewBox="0 0 16 16" width="16" height="16"
      fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  )
}
```

- [ ] **Step 3b: The header**

`personal_apps/static/gym/src/components/ExerciseHeader.tsx`:

```tsx
import type { ExerciseMeta } from '../types'
import { shortDate } from '../format'
import { Icon } from './Icon'

interface Props {
  exercise: ExerciseMeta
  lastOverall: { started_at: string; position: number } | null
  chipClass: string | null
  chipLabel: string | null
}

export function ExerciseHeader({ exercise, lastOverall, chipClass, chipLabel }: Props) {
  return (
    <header className="session-top">
      <a href="/gym/uebungen" className="session-top__back" aria-label="Zurück zu den Übungen">
        <Icon name="back" />
      </a>
      <span className="session-top__name stack">
        {/* The page's h1. It had NO heading of any level -- the exercise name
            was a span, so the document outline was empty. */}
        <h1 className="exdetail__name">{exercise.name}</h1>
        <span className="exdetail__sub">
          {exercise.muscle_group || 'Ohne Gruppe'}
          {/* lastOverall, not table[0]: `table` is the FILTERED view, so under
              ?position=5 this announced "Zuletzt ... Pos. 5" as though that
              were the last time you did the lift at all. Identity metadata is
              never scoped to a filter. */}
          {lastOverall && ` · Zuletzt ${shortDate(lastOverall.started_at)} · Pos. ${lastOverall.position}`}
          {exercise.is_unilateral && ' · einseitig'}
        </span>
      </span>
      {chipLabel && <span className={`vtag vtag--${chipClass}`}>{chipLabel}</span>}
    </header>
  )
}
```

- [ ] **Step 3c: The records band**

`personal_apps/static/gym/src/components/RecordsBand.tsx`:

```tsx
import type { E1rmPR, SessionRow, WeightPR } from '../types'
import { kg1, shortDate } from '../format'

interface Props {
  prWeight: WeightPR | null
  prE1rm: E1rmPR | null
  state: string
  sessionsSincePr: number | null
  lastProgression: SessionRow | null
}

export function RecordsBand({ prWeight, prE1rm, state, sessionsSincePr, lastProgression }: Props) {
  return (
    <>
      {prWeight && prE1rm ? (
        <div className="prs">
          <span className="pr">
            <span className="pr__val">{kg1(prWeight.weight)}<small>kg</small></span>
            <span className="label">Bestes Gewicht</span>
            <span className="pr__sub">
              {prWeight.reps} Wdh. · Pos. {prWeight.position} · {shortDate(prWeight.started_at)}
            </span>
          </span>
          <span className="pr">
            <span className="pr__val">{kg1(prE1rm.e1rm)}<small>kg</small></span>
            <span className="label">Bestes e1RM</span>
            <span className="pr__sub">
              {kg1(prE1rm.weight)} kg × {prE1rm.reps} · Pos. {prE1rm.position} · {shortDate(prE1rm.started_at)}
            </span>
          </span>
        </div>
      ) : (
        <p className="empty">Noch kein Rekord — bisher nur Deload-Sätze protokolliert.</p>
      )}

      {state === 'stagniert' && lastProgression ? (
        <section className="next-time">
          <div className="next-time__lbl">Stagniert</div>
          <p className="next-time__body">
            Seit {sessionsSincePr} Workouts kein neuer e1RM-PR — mehr Gewicht
            oder mehr Wiederholungen versuchen, ausgehend von{' '}
            <b>{kg1(lastProgression.best_weight)} kg</b>.
          </p>
        </section>
      ) : sessionsSincePr && sessionsSincePr > 0 ? (
        <p className="exdetail__since">
          Seit {sessionsSincePr} {sessionsSincePr === 1 ? 'Workout' : 'Workouts'} kein neuer e1RM-PR
        </p>
      ) : null}
    </>
  )
}
```

- [ ] **Step 3d: The session log**

`personal_apps/static/gym/src/components/SessionLog.tsx`:

```tsx
import type { E1rmPR, SessionRow, WeightPR } from '../types'
import { kg1, shortDate, volume } from '../format'

interface Props {
  table: SessionRow[]
  selectedPosition: number | null
  isUnilateral: boolean
  prWeight: WeightPR | null
  prE1rm: E1rmPR | null
}

export function SessionLog({ table, selectedPosition, isUnilateral, prWeight, prE1rm }: Props) {
  return (
    <section className="sec sec--log" aria-labelledby="sec-log">
      {/* Same scoping as the chart above: this list is filtered too, and a bare
          "Einheiten" over 10 of 13 rows is a quiet miscount. */}
      <div className="sec__head">
        <h2 className="label" id="sec-log">Einheiten</h2>
        <span className="sec__sp" />
        <span className="label">
          {selectedPosition ? `Pos. ${selectedPosition}` : 'Alle Positionen'}
        </span>
      </div>
      {isUnilateral && (
        <p className="exdetail__note">
          Einseitig: Gewicht &amp; Wdh. sind je Seite geloggt, Volumen zählt beide Seiten (×2).
        </p>
      )}
      {table.map((row) => {
        /* Matched on session_id, not started_at. Two sessions on one day both
           matched the date and both went gold; and because .row.is-record
           tinted .vol, the gold landed on VOLUME. The record is an e1RM or a
           weight, never a volume. */
        const isE1rmPr = !!prE1rm && row.session_id === prE1rm.session_id && row.position === prE1rm.position
        const isWeightPr = !!prWeight && row.session_id === prWeight.session_id && row.position === prWeight.position
        const isRecord = isE1rmPr || isWeightPr
        return (
          <a
            key={`${row.session_id}-${row.position}`}
            className={`row row--top${isRecord ? ' is-record' : ''}`}
            href={`/gym/session/${row.session_id}`}
          >
            <span className="row__main stack">
              <span className="dateline">
                <span className="dateline__d">{shortDate(row.started_at)}</span>
                {/* A word as well as the colour: the tint alone was the only
                    carrier, so a record was invisible in greyscale and absent
                    for a screen reader. */}
                {isRecord && <span className="vtag vtag--record">Rekord</span>}
                {row.is_deload && <span className="vtag vtag--neu">Deload</span>}
              </span>
              <span className="row__meta">Pos. {row.position} · {row.sets_display}</span>
            </span>
            <span className="row__trail row__trail--stack">
              <span className="vol">{volume(row.volume)}<small>kg</small></span>
              <span className="e1rm">e1RM {kg1(row.e1rm)}</span>
            </span>
          </a>
        )
      })}
      <p className="exdetail__note">
        Deload-Einheiten bleiben in der Liste — sie sind das Protokoll. Sie halten
        keine Rekorde und zählen nicht gegen die Stagnation.
      </p>
    </section>
  )
}
```

- [ ] **Step 3e: The edit sheet**

Stays a native `<dialog>` and a native `<form method="post">`. These are deliberate one-off edits followed by a redirect — the spec's optimistic-write path is for the workout screen, not here.

`personal_apps/static/gym/src/components/EditSheet.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import type { ExerciseMeta } from '../types'

interface Props {
  exercise: ExerciseMeta
  muscleGroups: string[]
  equipmentLabels: Record<string, string>
  openOnMount: boolean
}

export function EditSheet({ exercise, muscleGroups, equipmentLabels, openOnMount }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  // Replaces the old document-level 'change' listener. The stack-steps field
  // only applies to a stack: on a dumbbell it is not an empty answer, it is a
  // meaningless question.
  const [equipment, setEquipment] = useState(exercise.equipment ?? '')

  useEffect(() => {
    // The rename was rejected, so reopen the editor with the typed name still
    // in it rather than making the user find the sheet again.
    if (openOnMount) ref.current?.showModal()
  }, [openOnMount])

  const num = (v: number | null) => (v === null ? '' : String(v))

  return (
    <dialog className="sheet" id="sheet-edit" aria-labelledby="sheet-edit-title" ref={ref}>
      <div className="sheet__head">
        <h2 className="sheet__title" id="sheet-edit-title">Übung bearbeiten</h2>
        <button type="button" className="sheet__close" onClick={() => ref.current?.close()}>
          Abbrechen
        </button>
      </div>
      <div className="sheet__body">
        <form method="post" action={`/gym/exercises/${exercise.id}/update`}>
          <div className="field grow">
            <label className="label" htmlFor="meta-name">Name</label>
            <input type="text" id="meta-name" name="name" className="input"
              defaultValue={exercise.name} required />
          </div>
          <div className="field grow">
            <label className="label" htmlFor="meta-group">Muskelgruppe</label>
            <select id="meta-group" name="muscle_group" className="select"
              defaultValue={exercise.muscle_group ?? ''}>
              <option value="">— keine —</option>
              {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
              {exercise.muscle_group && !muscleGroups.includes(exercise.muscle_group) && (
                <option value={exercise.muscle_group}>{exercise.muscle_group} (alt)</option>
              )}
            </select>
          </div>
          <div className="field">
            <label className="label" htmlFor="meta-rest">Standard-Pause (Sek.)</label>
            <input type="number" id="meta-rest" name="default_rest_seconds" min="0"
              className="input input--num" placeholder="90"
              defaultValue={num(exercise.default_rest_seconds)} />
          </div>
          <div className="field">
            <label className="label" htmlFor="meta-increment">Schrittweite (kg)</label>
            <input type="number" id="meta-increment" name="weight_increment" step="0.25" min="0"
              className="input input--num" placeholder="2,5"
              defaultValue={num(exercise.weight_increment)} />
          </div>
          <div className="field grow">
            <label className="label" htmlFor="meta-equipment">Art</label>
            <select id="meta-equipment" name="equipment" className="select"
              value={equipment} onChange={(e) => setEquipment(e.target.value)}>
              {Object.entries(equipmentLabels).map(([value, label]) => (
                <option value={value} key={value}>{label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="label" htmlFor="meta-bar">Stangengewicht (kg)</label>
            <input type="number" id="meta-bar" name="bar_weight" step="0.5" min="0"
              className="input input--num" placeholder="0"
              defaultValue={num(exercise.bar_weight)} />
          </div>
          {/* Only meaningful on an uneven stack. Even ones are already
              described by Schrittweite above. */}
          <div className="field grow" hidden={equipment !== 'stack'}>
            <label className="label" htmlFor="meta-stack">Stack-Stufen (kg, kommagetrennt)</label>
            <input type="text" id="meta-stack" name="stack_kg" className="input"
              placeholder="5, 13, 21, 29"
              defaultValue={exercise.stack_kg ? exercise.stack_kg.join(', ') : ''} />
          </div>
          <div className="field grow">
            <label className="label" htmlFor="meta-secondary">Sekundäre Muskelgruppen</label>
            <select id="meta-secondary" name="secondary_muscle_groups" className="select"
              multiple size={5}
              defaultValue={exercise.secondary_muscle_groups ?? []}>
              {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
            </select>
          </div>
          <label className="sheet__row">
            <input type="checkbox" name="is_unilateral" className="check"
              defaultChecked={exercise.is_unilateral} />
            <span className="label">Einseitig (pro Seite)</span>
          </label>
          <button type="submit" className="btn btn--live btn--block">Speichern</button>
        </form>
      </div>
    </dialog>
  )
}
```

**Note on `hidden` and CSS.** `gym.css` has bitten this project repeatedly by overriding `[hidden]` with a `display` rule. Verify in the browser that the stack field is genuinely hidden on a non-stack exercise; if it is not, the fix is a CSS specificity change in `gym.css`, not a workaround in the component.

- [ ] **Step 3f: The page composer**

`personal_apps/static/gym/src/pages/ExerciseDetail.tsx`:

```tsx
import { useRef } from 'react'
import type { ExerciseDetailPayload } from '../types'
import { shortDate } from '../format'
import { Icon } from '../components/Icon'
import { ExerciseHeader } from '../components/ExerciseHeader'
import { RecordsBand } from '../components/RecordsBand'
import { ExerciseChart } from '../components/ExerciseChart'
import { SessionLog } from '../components/SessionLog'
import { EditSheet } from '../components/EditSheet'

interface Props {
  payload: ExerciseDetailPayload
  nameTaken: boolean
}

/**
 * Order: what state it is in, the two records, the progression chart, every
 * session, and finally maintenance. Nothing here re-derives anything -- every
 * value comes from _exercise_detail_payload on the server.
 *
 * Position stays a SERIES, not just a filter: the same lift in slot 1 and slot
 * 3 is two different stories. The pills below isolate one, and they are real
 * links so deep links and the back button keep working.
 */
export function ExerciseDetailPage({ payload, nameTaken }: Props) {
  const p = payload
  const id = p.exercise.id
  const editRef = useRef<HTMLDialogElement>(null)
  const count = p.table.length

  return (
    <div className="exdetail">
      <ExerciseHeader exercise={p.exercise} lastOverall={p.last_overall}
        chipClass={p.chip_class} chipLabel={p.chip_label} />

      {nameTaken && (
        <section className="next-time">
          <div className="next-time__lbl">Name nicht geändert</div>
          <p className="next-time__body">Eine Übung mit diesem Namen gibt es schon.</p>
        </section>
      )}

      {count > 0 ? (
        <>
          {/* Two wrappers, so the desktop grid has two stable children to
              place. Inert on phones; the analysis column and the log column
              at 900px. */}
          <div className="exdetail__main">
            <RecordsBand prWeight={p.pr_weight} prE1rm={p.pr_e1rm} state={p.state}
              sessionsSincePr={p.sessions_since_pr} lastProgression={p.last_progression} />

            <section className="sec sec--chart" aria-labelledby="sec-chart">
              <div className="sec__head">
                <h2 className="label" id="sec-chart">Verlauf e1RM</h2>
                <span className="sec__sp" />
                {/* The count is scoped, so it says what it is counting. */}
                <span className="label">
                  {p.selected_position ? `Pos. ${p.selected_position} · ` : ''}
                  {count} {count === 1 ? 'Einheit' : 'Einheiten'}
                </span>
              </div>

              {p.available_positions.length > 1 && (
                <>
                  <div className="pills">
                    {/* ?position=all, not a bare URL: a bare URL means "decide
                        for me" and lands on the default slot. */}
                    <a className={`pill${p.selected_position === null ? ' is-on' : ''}`}
                      href={`/gym/exercises/${id}?position=all`}>Alle</a>
                    {p.available_positions.map((pos) => (
                      <a key={pos} className={`pill${p.selected_position === pos ? ' is-on' : ''}`}
                        href={`/gym/exercises/${id}?position=${pos}`}>Position {pos}</a>
                    ))}
                  </div>
                  {/* Arriving on a filtered page with a pill already lit reads
                      as a choice the reader made and forgot. It is the page's
                      choice, so the page says so and on what grounds. */}
                  {p.selected_position_is_default && (
                    <p className="exdetail__scope">
                      Zeigt Position {p.selected_position} —{' '}
                      {p.selected_position_reason === 'strongest'
                        ? 'die stärkste mit mindestens zwei Einheiten'
                        : 'die einzige mit nennenswerter Historie'}.
                    </p>
                  )}
                </>
              )}

              {p.chart && (
                <ExerciseChart chart={p.chart} sessionCount={count}
                  firstDate={shortDate(p.table[count - 1]!.started_at)}
                  lastDate={shortDate(p.table[0]!.started_at)} />
              )}
            </section>
          </div>

          <div className="exdetail__log">
            <SessionLog table={p.table} selectedPosition={p.selected_position}
              isUnilateral={p.exercise.is_unilateral}
              prWeight={p.pr_weight} prE1rm={p.pr_e1rm} />
          </div>
        </>
      ) : (
        /* Says what fills the page, not just that it is empty. */
        <p className="empty">
          Noch keine Sätze protokolliert. Sobald du diese Übung in einem Workout
          loggst, stehen hier Rekorde, der e1RM-Verlauf und jede einzelne Einheit.
        </p>
      )}

      <section className="sec sec--maint" aria-label="Übung verwalten">
        <button type="button" className="finished__correct"
          onClick={() => document.querySelector<HTMLDialogElement>('#sheet-edit')?.showModal()}>
          <Icon name="edit" />
          Name, Muskelgruppe, Standard-Pause bearbeiten
        </button>
        {p.can_delete && (
          <form method="post" action={`/gym/exercises/${id}/delete`}
            onSubmit={(e) => { if (!confirm('Übung löschen?')) e.preventDefault() }}>
            <button type="submit" className="quiet-acts__btn quiet-acts__btn--danger">
              Übung löschen
            </button>
          </form>
        )}
      </section>

      <EditSheet exercise={p.exercise} muscleGroups={p.muscle_groups}
        equipmentLabels={p.equipment_labels} openOnMount={nameTaken} />
    </div>
  )
}
```

**Note:** `editRef` is declared but the maintenance button reaches the dialog by id, matching how the old delegated `.sheet-open` handler worked. Drop the unused `useRef` import when implementing — `tsc --noEmit` with `strict` will flag it.

**Note on the first/last date labels.** The Jinja chart used `table[-1]` and `table[0]` for the aria-label range. `table` is newest-first, so `table[count - 1]` is the oldest. Both are guarded by `count > 0`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm test
```

Expected: PASS, all tests in both files green.

- [ ] **Step 5: Type-check**

```bash
npx tsc --noEmit
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/static/gym/src/components personal_apps/static/gym/src/pages
git commit -m "feat(gym): port the exercise detail page body to React components"
```

---

### Task 6: Mount the island and retire the Jinja body

The only task that changes what a user sees. Everything before it was additive.

**Files:**
- Create: `personal_apps/static/gym/src/entries/exercise.tsx`
- Delete: `personal_apps/static/gym/src/entries/smoke.tsx`
- Modify: `personal_apps/vite.config.ts` (swap the entry)
- Modify: `personal_apps/templates/gym/exercise_detail.html` (383 lines → ~25)
- Modify: `personal_apps/features/gym/routes.py` (`exercise_detail` passes the payload)
- Create: `personal_apps/scratchpad/shoot_exercise_detail.py`

**Interfaces:**
- Consumes: `ExerciseDetailPage` from Task 5, `vite_asset` from Task 1, `_exercise_detail_payload` from Task 3.
- Produces: the finished page. Nothing later depends on it.

- [ ] **Step 1: Capture the "before" screenshots**

With the dev server running on port 5001 (see `reference_personal_apps_local_run`), write `personal_apps/scratchpad/shoot_exercise_detail.py` to visit one exercise with history and one without, at 390×844 and 1280×800, in both colour schemes, saving to `scratchpad/shots/before/`. Run it and **view every PNG with the Read tool** — an unviewed screenshot proves nothing.

- [ ] **Step 2: Create the real entry**

`personal_apps/static/gym/src/entries/exercise.tsx`:

```tsx
import { createRoot } from 'react-dom/client'
import { ExerciseDetailPage } from '../pages/ExerciseDetail'
import type { ExerciseDetailPayload } from '../types'

// The payload is embedded in the document by the Jinja shell rather than
// fetched, so the first render has everything and there is no waterfall on
// load. The JSON endpoint from Task 3 exists for later refetches.
const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: ExerciseDetailPayload = JSON.parse(dataEl.textContent ?? '{}')
  const nameTaken = new URLSearchParams(window.location.search).has('name_taken')
  createRoot(rootEl).render(
    <ExerciseDetailPage payload={payload} nameTaken={nameTaken} />)
}
```

- [ ] **Step 3: Swap the Vite entry**

In `vite.config.ts`, replace the `input` block:

```ts
      input: {
        exercise: resolve(__dirname, 'static/gym/src/entries/exercise.tsx'),
      },
```

Then delete `static/gym/src/entries/smoke.tsx` and rebuild:

```bash
npm run build
```

- [ ] **Step 4: Replace the template**

`personal_apps/templates/gym/exercise_detail.html` becomes:

```html
{% extends 'gym/_base.html' %}

{# Exercise detail (Puls): the single-exercise instrument. The page body is a
   React island -- see static/gym/src/pages/ExerciseDetail.tsx. This shell
   embeds the payload rather than having the island fetch it, so the first
   render has everything and there is no waterfall on load.

   The payload is the same object gym_exercise_detail_json serves, built once
   by routes._exercise_detail_payload so the page and the endpoint cannot
   disagree about which position slot is selected. #}

{% block title %}{{ exercise.name }} · Gym Tracker{% endblock %}

{% block content %}
<div id="gym-root"></div>
{% endblock %}

{% block scripts %}
<script type="application/json" id="gym-data">{{ payload_json | tojson }}</script>
<script type="module" src="{{ vite_asset('exercise') }}"></script>
{% endblock %}
```

Flask's `tojson` escapes `<`, `>` and `&` for embedding in HTML, so no manual escaping is needed and `|safe` must not be added.

- [ ] **Step 5: Simplify the route**

Replace `exercise_detail` in `routes.py` with:

```python
@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return render_template(
        'gym/exercise_detail.html',
        exercise=exercise,
        payload_json=payload.model_dump(mode='json'),
    )
```

- [ ] **Step 6: Capture the "after" screenshots and compare**

Re-run the screenshot script into `scratchpad/shots/after/`, then **view every PNG with the Read tool** and compare against the before set. Any difference must be explainable. Record explained differences in the commit message; fix everything else.

- [ ] **Step 7: Run the whole suite**

```bash
python -m pytest tests/ -q
```

Expected: PASS. `test_gym_routes_smoke.py` may assert on HTML that no longer exists — if it asserts on markup rather than status, update it to assert on the embedded payload instead, and say so in the commit.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/templates/gym/exercise_detail.html personal_apps/features/gym/routes.py personal_apps/static/gym/src personal_apps/vite.config.ts personal_apps/tests
git commit -m "feat(gym): render the exercise detail page as a React island"
```

---

### Task 7: The VPS deploy change

The deploy script is **not in this repository** — it lives on the VPS and michi runs it manually. This task produces documentation, not code, plus the one-time Node install. The build must run *after* `git reset --hard origin/main`, because that deletes the untracked `dist/`.

**Files:**
- Create: `personal_apps/DEPLOY_FRONTEND.md`

- [ ] **Step 1: Write the deploy note**

`personal_apps/DEPLOY_FRONTEND.md` documenting:

1. **One-time on the VPS:** install Node 22 LTS, then `cd /root/coc-stats/personal_apps && npm ci`.
2. **Deploy script insertion point:** after `git fetch --all && git reset --hard origin/main` and after `pip install -r requirements.txt`, before the `personal_apps_web` restart:

```bash
cd /root/coc-stats/personal_apps && npm ci && npm run build
```

3. **Why it goes there:** `git reset --hard` deletes untracked files, and `static/gym/dist/` is gitignored. Building before the reset would have the output wiped.
4. **Failure mode:** if the build does not run, every gym page raises `ViteManifestError` with a message naming the fix. It fails loudly and identically on every page rather than serving a broken bundle. The service will 500 — so the build must be verified before the restart, not after.
5. **Rollback:** `git reset --hard <previous-sha>` then rerun the build.

- [ ] **Step 2: Commit**

```bash
git add personal_apps/DEPLOY_FRONTEND.md
git commit -m "docs(gym): document the frontend build step for the VPS deploy"
```

- [ ] **Step 3: Hand the VPS steps to michi**

The deploy script edit and the Node install are manual actions on the VPS. Do not attempt them — report the exact commands from `DEPLOY_FRONTEND.md` and let michi run them. Per the standing rule, deploy commands are only ever handed over for standalone scripts, never executed for app code.

---

## Verification checklist

Before declaring step 1 complete:

- [ ] `python -m pytest tests/ -q` passes from `personal_apps/`
- [ ] `npm test` passes from `personal_apps/`
- [ ] `npx tsc --noEmit` is clean
- [ ] `npm run build` produces `static/gym/dist/.vite/manifest.json`
- [ ] Before/after screenshots viewed at 390×844 and 1280×800, light and dark, for an exercise with history and one without
- [ ] `/gym/exercises/<id>?position=all` and `?position=N` both work, and the back button returns correctly
- [ ] The edit sheet saves, and a duplicate name reopens it with `?name_taken`
- [ ] The delete form appears only when the exercise is unused

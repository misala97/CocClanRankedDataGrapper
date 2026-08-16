# Windowed, Uncapped Fortschritt Section — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Fortschritt section of `/gym/statistik` shows every qualifying exercise instead of eight, and a four-position control re-measures it over Alles / 6 Monate / 3 Monate / 30 Tage.

**Architecture:** The server precomputes all four windows by calling one Python ranking function four times with different cutoffs; the payload carries four blocks; the React component swaps which block it renders on click. No fetch, no reload, and no ranking arithmetic outside `analytics.py`.

**Tech Stack:** Flask + SQLAlchemy + pydantic payload schemas (`features/gym/schemas.py`), pure-Python analytics (`features/gym/analytics.py`), React 19 + TypeScript islands built by Vite, pytest, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-16-statistik-progression-window-design.md`

## Global Constraints

- `analytics.py` contains **no German prose** and never imports SQLAlchemy/Flask/Jinja. It returns figures; the component writes the sentence.
- Window keys are the exact strings `all`, `6m`, `3m`, `30d`, in that order.
- Cutoffs are plain day counts from `now`: `30d` = 30 days, `3m` = 91 days, `6m` = 182 days. Not calendar arithmetic.
- German copy, verbatim:
  - Headings: `Fortschritt seit dem ersten Mal` (all), `Fortschritt in 6 Monaten`, `Fortschritt in 3 Monaten`, `Fortschritt in 30 Tagen`.
  - Control labels: `Alles`, `6 Monate`, `3 Monate`, `30 Tage`.
  - Empty window: `Keine Übung mit zwei Einheiten in diesem Zeitraum.`
  - Existing no-history copy is unchanged: `Noch zu wenig Historie, um Fortschritt zu messen.`
- Deload rows stay excluded from this section (`stats.progression_rows`), windowed or not.
- The local dev server runs on port **5001** (`PYTHONPATH=. python -m flask --app app run --port 5001`), and MySQL80 must be running (start needs an elevated shell: `net start MySQL80`).
- Four pre-existing test failures are expected and unrelated: `test_gym_ownership.py::test_every_pre_existing_row_was_backfilled_to_the_admin`, `test_gym_exercise_ownership.py::test_every_pre_existing_exercise_was_backfilled_to_the_admin`, `test_gym_routes_smoke.py::test_exercise_detail_renders_for_every_exercise`, `test_gym_routes_smoke.py::test_session_pages_render_for_every_finished_session`. Do not try to fix them.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `personal_apps/features/gym/analytics.py` | ranking arithmetic | `progression_ranking` gains `since` |
| `personal_apps/tests/test_gym_analytics.py` | analytics unit tests | new window tests |
| `personal_apps/features/gym/routes/reports.py` | view geometry + payload assembly | `_progression_view` uncapped; four blocks built |
| `personal_apps/features/gym/schemas.py` | payload contract | new `ProgressionWindow` model |
| `personal_apps/tests/test_gym_routes_smoke.py` | route contract | asserts the four blocks |
| `personal_apps/static/gym/src/statistik/types.ts` | client payload types | new `ProgressionWindow` |
| `personal_apps/static/gym/src/statistik/StatistikPage.tsx` | the section + control | window state, heading, empty state |
| `personal_apps/static/gym/src/statistik/StatistikPage.test.tsx` | component tests | fixture + control tests |
| `personal_apps/static/gym/gym.css` | control styling | `.winsel` |

---

### Task 1: Window the ranking

**Files:**
- Modify: `personal_apps/features/gym/analytics.py:144` (`progression_ranking`)
- Test: `personal_apps/tests/test_gym_analytics.py`

**Interfaces:**
- Consumes: `stats.progression_rows(rows)`, `stats.best_e1rm(row)`, existing test helpers `perf(...)` and `day(n)` in the test module.
- Produces: `analytics.progression_ranking(rows, since=None)` — `since` is a naive UTC `datetime` or `None`; returns the same list of dicts as today, sorted by `change_pct` descending then name.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_gym_analytics.py`:

```python
def test_progression_ranking_measures_from_the_first_session_inside_the_window():
    """A window moves BOTH ends. The baseline is the first qualifying session
    in the window, not the all-time first -- otherwise '3 Monate' would report
    a change earned before it started."""
    rows = [
        perf([(60.0, 10)], started_at=day(0), session_id=1),
        perf([(80.0, 10)], started_at=day(40), session_id=2),
        perf([(90.0, 10)], started_at=day(50), session_id=3),
    ]
    windowed = analytics.progression_ranking(rows, since=day(30))
    assert len(windowed) == 1
    assert windowed[0]['first_e1rm'] == round(stats.epley_1rm(80.0, 10), 1)
    assert windowed[0]['sessions'] == 2


def test_progression_ranking_drops_an_exercise_with_one_session_in_the_window():
    """One session inside the window has no first-versus-current, exactly as
    one session all-time does not."""
    rows = [
        perf([(60.0, 10)], started_at=day(0), session_id=1),
        perf([(80.0, 10)], started_at=day(50), session_id=2),
    ]
    assert analytics.progression_ranking(rows, since=day(30)) == []


def test_progression_ranking_without_a_window_is_unchanged():
    rows = [
        perf([(60.0, 10)], started_at=day(0), session_id=1),
        perf([(90.0, 10)], started_at=day(50), session_id=2),
    ]
    assert (analytics.progression_ranking(rows, since=None)
            == analytics.progression_ranking(rows))


def test_progression_ranking_still_ignores_deloads_inside_a_window():
    rows = [
        perf([(80.0, 10)], started_at=day(40), session_id=1),
        perf([(90.0, 10)], started_at=day(50), session_id=2),
        perf([(20.0, 10)], started_at=day(55), session_id=3, is_deload=True),
    ]
    windowed = analytics.progression_ranking(rows, since=day(30))
    assert windowed[0]['sessions'] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd personal_apps && PYTHONPATH=. python -m pytest tests/test_gym_analytics.py -q -k progression_ranking`
Expected: FAIL — `TypeError: progression_ranking() got an unexpected keyword argument 'since'`

- [ ] **Step 3: Add the parameter**

In `personal_apps/features/gym/analytics.py`, change the signature and docstring opening of `progression_ranking`, and filter before grouping. Replace:

```python
def progression_ranking(rows):
    """Fortschritt: every exercise ranked by all-time change in estimated 1RM.
```

with:

```python
def progression_ranking(rows, since=None):
    """Fortschritt: every exercise ranked by its change in estimated 1RM.

    `since` narrows the question to a window, and moves BOTH ends of the
    comparison: an exercise is measured from its first qualifying session
    inside the window to its most recent one. Anything else would print a
    change earned outside the span the caller asked about. None is the whole
    history, which is the page's default.
```

Then replace the grouping loop:

```python
    by_exercise = defaultdict(list)
    for row in stats.progression_rows(rows):
        by_exercise[row.exercise_id].append(row)
```

with:

```python
    by_exercise = defaultdict(list)
    for row in stats.progression_rows(rows):
        if since is not None and row.started_at < since:
            continue
        by_exercise[row.exercise_id].append(row)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd personal_apps && PYTHONPATH=. python -m pytest tests/test_gym_analytics.py -q`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/gym/analytics.py personal_apps/tests/test_gym_analytics.py
git commit -m "feat(gym): progression_ranking can answer a window"
```

---

### Task 2: Ship four windows in the payload

**Files:**
- Modify: `personal_apps/features/gym/routes/reports.py:198` (`_progression_view`), `:335` (payload assembly)
- Modify: `personal_apps/features/gym/schemas.py:724` area (new model), `:917` (`progression` field)
- Test: `personal_apps/tests/test_gym_routes_smoke.py`

**Interfaces:**
- Consumes: `analytics.progression_ranking(rows, since=None)` from Task 1.
- Produces: payload key `progression` = `list[ProgressionWindow]`, where `ProgressionWindow` is `{key: str, entries: list[ProgressionRow]}`; keys in order `all`, `6m`, `3m`, `30d`. Also `reports.PROGRESSION_WINDOWS`, a tuple of `(key, days_or_None)` pairs.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_gym_routes_smoke.py`:

```python
def test_statistik_ships_every_progression_window(client):
    """Four windows, precomputed. The client swaps between them without a
    round trip, so they have to arrive together."""
    from conftest import embedded_payload
    response = client.get('/gym/statistik')
    assert response.status_code == 200
    payload = embedded_payload(response.get_data(as_text=True))
    assert [block['key'] for block in payload['progression']] == ['all', '6m', '3m', '30d']


def test_statistik_no_longer_caps_the_progression_list(client):
    """The cap was hiding lifts: eight up, unbounded down. Every exercise the
    ranking qualifies belongs in the all-time block."""
    from conftest import embedded_payload
    response = client.get('/gym/statistik')
    payload = embedded_payload(response.get_data(as_text=True))
    all_block = next(b for b in payload['progression'] if b['key'] == 'all')
    assert len(all_block['entries']) > 8, (
        'this database should hold more than eight ranked lifts -- check the '
        'count with the command in Step 2 before blaming the code')


def test_every_progression_window_scales_its_own_bars(client):
    """bar_pct is a share of that window's biggest move. Scaling every window
    against the all-time widest would draw a narrow window as a row of stubs."""
    from conftest import embedded_payload
    response = client.get('/gym/statistik')
    payload = embedded_payload(response.get_data(as_text=True))
    for block in payload['progression']:
        if block['entries']:
            assert max(entry['bar_pct'] for entry in block['entries']) == 50.0, block['key']
```

Note: `embedded_payload` already exists in `tests/conftest.py`. `50.0` is the
full half-width of the diverging bar — `_progression_view` scales the widest
absolute change to it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd personal_apps && PYTHONPATH=. python -m pytest tests/test_gym_routes_smoke.py -q -k progression`
Expected: FAIL — `TypeError: string indices must be integers` or a pydantic `ValidationError`, because `progression` is still a flat list of rows.

Sanity-check the ranked count first:

```bash
cd personal_apps && PYTHONPATH=. python -c "
from app import app
from features.gym import analytics
from features.gym.routes.history import load_performed
with app.test_request_context():
    from flask import session; session['user_id']=1
    print(len(analytics.progression_ranking(load_performed())), 'ranked exercises')
"
```

- [ ] **Step 3: Uncap the view helper**

In `personal_apps/features/gym/routes/reports.py`, replace the whole of `_progression_view`'s signature, docstring tail and head/tail selection. Replace:

```python
def _progression_view(ranking, limit=8):
    """Progression rows with their sparkline drawn and their bar sized.
```

with:

```python
def _progression_view(ranking):
    """Progression rows with their sparkline drawn and their bar sized.
```

Replace this docstring paragraph:

```python
    Both ends are kept: the biggest movers AND the biggest losers, because a
    page that only shows what went up is a highlight reel, not a report.
    """
    if not ranking:
        return []
    head = ranking[:limit]
    tail = [entry for entry in ranking[limit:] if entry['change_pct'] < 0]
    shown = head + [entry for entry in tail if entry not in head]

    widest = max((abs(entry['change_pct']) for entry in shown), default=1.0) or 1.0
```

with:

```python
    Every ranked exercise is returned. There used to be a top-eight cap with
    an exception that kept every loser below it -- the exception existed only
    so truncation could not turn the section into a highlight reel, and with
    nothing truncated it has nothing left to protect. The cap also made the
    section grow only when things went wrong: bounded upward, unbounded down.
    """
    if not ranking:
        return []
    shown = list(ranking)

    widest = max((abs(entry['change_pct']) for entry in shown), default=1.0) or 1.0
```

- [ ] **Step 4: Add the window table and build the blocks**

In `personal_apps/features/gym/routes/reports.py`, above `_progression_view`, add:

```python
# The windows the Fortschritt section offers, newest question last. Plain day
# counts rather than calendar months: a month here is a rough span, and no
# consumer needs it to land on the same day of the month. None is all time.
#
# Precomputed all four rather than served per request: the client switches
# between them with no round trip, and every figure still comes from one
# Python function instead of a second implementation in TypeScript.
PROGRESSION_WINDOWS = (('all', None), ('6m', 182), ('3m', 91), ('30d', 30))
```

Then in `gym_statistik`, replace:

```python
        progression=_progression_view(analytics.progression_ranking(performed)),
```

with:

```python
        progression=[
            {'key': key,
             'entries': _progression_view(analytics.progression_ranking(
                 performed,
                 since=None if days is None else now - dt.timedelta(days=days)))}
            for key, days in PROGRESSION_WINDOWS
        ],
```

- [ ] **Step 5: Widen the payload schema**

In `personal_apps/features/gym/schemas.py`, directly after the `ProgressionRow` class, add:

```python
class ProgressionWindow(_Model):
    """One window's ranking. `key` is one of 'all', '6m', '3m', '30d' -- an
    identifier, not a label: the component owns the German, exactly as it does
    for month and weekday names."""
    key: str
    entries: list[ProgressionRow]
```

and change the payload field from:

```python
    progression: list[ProgressionRow]
```

to:

```python
    #: All four windows, precomputed. The client swaps between them without a
    #: round trip, so they travel together.
    progression: list[ProgressionWindow]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd personal_apps && PYTHONPATH=. python -m pytest tests/test_gym_routes_smoke.py -q -k progression`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/routes/reports.py personal_apps/features/gym/schemas.py personal_apps/tests/test_gym_routes_smoke.py
git commit -m "feat(gym): the statistik payload carries every progression window"
```

---

### Task 3: The control, the heading, and every lift on screen

**Files:**
- Modify: `personal_apps/static/gym/src/statistik/types.ts:31-45` and `:212`
- Modify: `personal_apps/static/gym/src/statistik/StatistikPage.tsx:417-430` (the section), plus the destructure at `:98-103`
- Modify: `personal_apps/static/gym/gym.css` (near `.sec__head`, around line 2710)
- Test: `personal_apps/static/gym/src/statistik/StatistikPage.test.tsx`

**Interfaces:**
- Consumes: payload `progression: ProgressionWindow[]` from Task 2, keys `all` / `6m` / `3m` / `30d`.
- Produces: no exported symbols; the section is internal to `StatistikPage`.

- [ ] **Step 1: Update the client types**

In `personal_apps/static/gym/src/statistik/types.ts`, after the `ProgressionRow` interface add:

```ts
export interface ProgressionWindow {
  /** 'all' | '6m' | '3m' | '30d' -- an identifier; the component owns the label. */
  key: string
  entries: ProgressionRow[]
}
```

and change the payload field from `progression: ProgressionRow[]` to:

```ts
  progression: ProgressionWindow[]
```

- [ ] **Step 2: Update the test fixture, then write the failing tests**

In `personal_apps/static/gym/src/statistik/StatistikPage.test.tsx`, replace the `progression:` fixture entry:

```ts
  progression: [{
    exercise_id: 9, name: 'Bench Press (Dumbbell)', sessions: 10,
    first_e1rm: 27.1, current_e1rm: 76, change_pct: 180.1, best_weight: 60,
    points: [27.1, 76], spark: '0.0,22.0 74.0,2.0', bar_pct: 50, is_up: true,
  }],
```

with:

```ts
  progression: [
    {
      key: 'all',
      entries: [{
        exercise_id: 9, name: 'Bench Press (Dumbbell)', sessions: 10,
        first_e1rm: 27.1, current_e1rm: 76, change_pct: 180.1, best_weight: 60,
        points: [27.1, 76], spark: '0.0,22.0 74.0,2.0', bar_pct: 50, is_up: true,
      }],
    },
    {
      key: '6m',
      entries: [{
        exercise_id: 9, name: 'Bench Press (Dumbbell)', sessions: 8,
        first_e1rm: 40, current_e1rm: 76, change_pct: 90, best_weight: 60,
        points: [40, 76], spark: '0.0,22.0 74.0,2.0', bar_pct: 50, is_up: true,
      }],
    },
    {
      key: '3m',
      entries: [{
        exercise_id: 7, name: 'Hammer Curl', sessions: 4,
        first_e1rm: 20, current_e1rm: 22, change_pct: 10, best_weight: 22,
        points: [20, 22], spark: '0.0,22.0 74.0,2.0', bar_pct: 50, is_up: true,
      }],
    },
    { key: '30d', entries: [] },
  ],
```

Every other reference to `base.progression[0]` in this file must become
`base.progression[0]!.entries[0]`. There is one, in the "-12 %" test, which
becomes:

```ts
        progression: [
          { key: 'all', entries: [{ ...base.progression[0]!.entries[0]!, change_pct: -12.4, is_up: false }] },
          ...base.progression.slice(1),
        ],
```

Then add this describe block beside the existing `describe('progression', ...)`:

```tsx
  describe('the progression window', () => {
    it('opens on the whole history', () => {
      mount()
      expect(screen.getByText('Fortschritt seit dem ersten Mal')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Alles' })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByText('Bench Press (Dumbbell)')).toBeInTheDocument()
    })

    it('re-ranks from the window the reader picked', async () => {
      // The whole point of precomputing four blocks: the click swaps which
      // one renders, with no fetch.
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: '3 Monate' }))
      expect(screen.getByText('Hammer Curl')).toBeInTheDocument()
      expect(screen.queryByText('Bench Press (Dumbbell)')).not.toBeInTheDocument()
    })

    it('moves the heading with the window, so label and number agree', async () => {
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: '6 Monate' }))
      expect(screen.getByText('Fortschritt in 6 Monaten')).toBeInTheDocument()
      expect(screen.queryByText('Fortschritt seit dem ersten Mal')).not.toBeInTheDocument()
    })

    it('says a window is empty rather than showing a headed void', async () => {
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: '30 Tage' }))
      expect(screen.getByText('Keine Übung mit zwei Einheiten in diesem Zeitraum.'))
        .toBeInTheDocument()
    })

    it('keeps the no-history copy when every window is empty', () => {
      // A brand-new account still gets all four blocks -- they are just all
      // empty. "Keine Übung in diesem Zeitraum" would blame the window for a
      // history that does not exist yet, and a picker over four empty windows
      // is a control with nothing to control.
      mount({ progression: base.progression.map((b) => ({ ...b, entries: [] })) })
      expect(screen.getByText('Noch zu wenig Historie, um Fortschritt zu messen.'))
        .toBeInTheDocument()
      expect(screen.queryByRole('button', { name: '3 Monate' })).not.toBeInTheDocument()
    })
  })
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd personal_apps/static/gym && npx vitest run src/statistik`
Expected: FAIL — TypeScript/runtime errors from `progression.map` on the new shape, and "Unable to find an accessible element with the role button and name Alles".

- [ ] **Step 4: Build the control**

In `personal_apps/static/gym/src/statistik/StatistikPage.tsx`:

Add near the other module-level constants (below `joinAnd`):

```tsx
/** The windows the section offers, and what each one calls itself. Keys match
 *  routes/reports.py's PROGRESSION_WINDOWS; the German lives here because
 *  analytics.py holds no user-visible copy. */
const PROGRESSION_WINDOWS = [
  { key: 'all', label: 'Alles', heading: 'Fortschritt seit dem ersten Mal' },
  { key: '6m', label: '6 Monate', heading: 'Fortschritt in 6 Monaten' },
  { key: '3m', label: '3 Monate', heading: 'Fortschritt in 3 Monaten' },
  { key: '30d', label: '30 Tage', heading: 'Fortschritt in 30 Tagen' },
]
```

Inside the component, beside the existing `useState` for `sel`:

```tsx
  // Which window the Fortschritt section is answering. All four arrived in the
  // payload, so this is a choice of array, not a fetch.
  const [window_, setWindow] = useState('all')
```

Then replace the whole progression `<section>` (currently lines 417-430) with:

```tsx
          <section aria-labelledby="prog-h">
            <div className="sec__head">
              <h2 className="label" id="prog-h">
                {PROGRESSION_WINDOWS.find((w) => w.key === window_)?.heading
                  ?? PROGRESSION_WINDOWS[0]!.heading}
              </h2>
              <span className="sec__sp" />
              {/* Only offered when some window has something to show. A new
                  account gets all four blocks too, just empty, and a picker
                  over four empty windows is a control with nothing to
                  control. */}
              {hasProgression && (
                <span className="winsel" role="group" aria-label="Zeitraum">
                  {PROGRESSION_WINDOWS.map((w) => (
                    <button type="button" key={w.key} className="winsel__b"
                      aria-pressed={w.key === window_}
                      onClick={() => setWindow(w.key)}>
                      {w.label}
                    </button>
                  ))}
                </span>
              )}
            </div>
            {shownProgression.length > 0 ? (
              shownProgression.map((entry) => (
                <Progression entry={entry} key={entry.exercise_id} />
              ))
            ) : (
              {/* Which silence this is matters: an empty WINDOW is a fact
                  about the window, an empty history is a fact about the log. */}
              <p className="empty">
                {hasProgression
                  ? 'Keine Übung mit zwei Einheiten in diesem Zeitraum.'
                  : 'Noch zu wenig Historie, um Fortschritt zu messen.'}
              </p>
            )}
          </section>
```

Add the derived list beside the other `const` derivations (near `topShare`):

```tsx
  const shownProgression = (progression.find((block) => block.key === window_)
    ?? progression[0])?.entries ?? []
  const hasProgression = progression.some((block) => block.entries.length > 0)
```

`progression` is already destructured from the payload; its type is now
`ProgressionWindow[]`, so no destructure change is needed.

- [ ] **Step 5: Style the control**

In `personal_apps/static/gym/gym.css`, directly after the `.sec__sp` rule (around line 2983), add:

```css
/* The Fortschritt window picker. Sits in the section head where a static
   caption used to, so it inherits that row's alignment; the pressed state is
   the fill, because a control with four options needs to say which one is
   live without a second carrier. */
.winsel { display: flex; gap: 2px; }
.winsel__b {
  border: 0; background: transparent; cursor: pointer;
  font: inherit; font-size: var(--t-micro); font-weight: var(--w-semi);
  letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--unlit); padding: var(--sp-1) var(--sp-2);
  border-radius: 999px; min-block-size: var(--tap);
}
.winsel__b:hover { color: var(--ink); }
.winsel__b[aria-pressed="true"] { background: var(--raised); color: var(--ink); }
.winsel__b:focus-visible { outline: 2px solid var(--live); outline-offset: 2px; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd personal_apps/static/gym && npx vitest run src/statistik && npx tsc --noEmit`
Expected: PASS, and tsc silent.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/static/gym/src/statistik/types.ts personal_apps/static/gym/src/statistik/StatistikPage.tsx personal_apps/static/gym/src/statistik/StatistikPage.test.tsx personal_apps/static/gym/gym.css
git commit -m "feat(gym): the Fortschritt section takes a window and shows every lift"
```

---

### Task 4: Verify against real data, then rebalance

**Files:**
- Possibly modify: `personal_apps/static/gym/src/statistik/StatistikPage.tsx`, `personal_apps/static/gym/gym.css`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: nothing new; this task closes the known consequence recorded in the spec.

- [ ] **Step 1: Build and run the app**

```bash
cd personal_apps && npm run build && PYTHONPATH=. python -m flask --app app run --port 5001
```

If MySQL refuses the connection, it needs an elevated shell: `net start MySQL80`.

- [ ] **Step 2: Screenshot all three viewports and measure the columns**

Use python-playwright (not the browser MCP), minting a session cookie rather than logging in:

```python
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\personal_apps')
from app import app
from flask.sessions import SecureCookieSessionInterface
from playwright.sync_api import sync_playwright

cookie = SecureCookieSessionInterface().get_signing_serializer(app).dumps({'user_id': 1})
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, w, h in (('phone', 390, 844), ('tablet', 768, 1024), ('desk', 1200, 800)):
        ctx = browser.new_context(viewport={'width': w, 'height': h})
        ctx.add_cookies([{'name': 'session', 'value': cookie,
                          'domain': '127.0.0.1', 'path': '/'}])
        page = ctx.new_page()
        page.goto('http://127.0.0.1:5001/gym/statistik', wait_until='networkidle')
        print(name, page.evaluate('''() => [...document.querySelectorAll('.stat-col')].map(c => {
            const box = c.getBoundingClientRect()
            return {w: Math.round(box.width),
                    content: Math.round(c.lastElementChild.getBoundingClientRect().bottom - box.top)}})'''))
        page.screenshot(path=f'{name}.png', full_page=True)
        ctx.close()
    browser.close()
```

Read every PNG with the Read tool. Confirm: the control renders in the section head, `Alles` is filled, no horizontal overflow, and the section lists every ranked lift.

- [ ] **Step 3: Click through the windows in the real browser**

Add to the script: click each `.winsel__b` in turn, and after each click assert the heading text and print the rendered `.prog__name` count. Confirm the numbers change and that `30 Tage` shows either lifts or the empty sentence — whichever the data actually supports.

- [ ] **Step 4: Rebalance the columns if the measurement says so**

The two `.stat-col` content heights were 1517 and 1536 before this change. If they now differ by more than roughly 400px, move one section across: the narrow column holds compact name+number lists (`Stufen erklommen`, `Am längsten ohne Bestwert`) and the wide one holds bar charts, so the candidate to move is whichever section fits its new column's shape — do not move a bar chart into the 361px column, where `.prog--plain .prog__name` at 15rem plus `.prog__pct` at 5rem leaves the bar no width.

If they are within 400px, change nothing and say so.

- [ ] **Step 5: Run both suites**

```bash
cd personal_apps && PYTHONPATH=. python -m pytest tests/ -q
cd personal_apps/static/gym && npx vitest run
```

Expected: green except the four pre-existing failures listed in Global Constraints.

- [ ] **Step 6: Commit**

```bash
git add -A personal_apps
git commit -m "fix(gym): the statistik columns rebalance around the longer Fortschritt list"
```

Skip this commit if Step 4 changed nothing.

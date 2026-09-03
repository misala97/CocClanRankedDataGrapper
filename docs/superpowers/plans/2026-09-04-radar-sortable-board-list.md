# Radar Sortable Board List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the radar board's ticker list sortable by six keys from its column header, re-ranking the whole candidate set server-side rather than reordering the rows already on screen.

**Architecture:** The sort is a `Selection` field like `venues`: it travels through `queryFor` into the request and into the address bar. The server sorts in `board.build` **between the filters and `ranked[:limit]`** — not in `leaderboard.build_rows`, which `board.py` already calls with `limit=None`. The header's five `aria-hidden` labels become six real buttons; a sort collapses the two tier captions into one flat list and leaves Watching pinned.

**Tech Stack:** Flask + SQLAlchemy (MySQL 8 dev, MariaDB prod), React 18 + TypeScript island built by Vite, vitest + testing-library for the island, pytest for the server.

**Spec:** `docs/superpowers/specs/2026-09-04-radar-sortable-board-list-design.md` — read it first. Where this plan deviates (listed in Task 6), the plan wins; Task 6 updates the spec.

## Global Constraints

- Paths are relative to `personal_apps/` unless they start with `docs/`. Run pytest from `personal_apps/` as `python -m pytest <files> -q -p no:cacheprovider`; run vitest as `npx vitest run -c vite.radar.config.ts`; run `git` from the repo root. The full pytest suite takes ~20 min — run the files each task names.
- **The six sort keys are exactly** `ticker`, `mentions`, `divergence`, `ratio`, `move`, `lean`. This spelling is the wire format, the `Selection` field and the Python constant; it does not vary between them.
- **Default direction per key:** `ticker` ascending; the other five descending. Second click reverses; third click clears the sort entirely.
- **A row whose sort value is `None` sorts LAST in both directions.** Never `reverse=True` on a key that can be missing — it would lift the missing rows to the top. Sort ascending always and negate numeric values for descending (see Task 1's `ordering` closure inside `sort_rows`).
- **`ratio` is `phrasing.ratio_value(row.mentions, row.expected)`** — the same call `routes/api.py:382` already serialises. It is a pure function of two fields the pre-limit row already carries.
- **`lean` is `(bullish - bearish) / (bullish + neutral + bearish)`**, and `None` when that total is 0. It needs `board._tones()`, which today runs only over the post-limit rows — so a lean sort fetches tones for the whole candidate set first (106 candidates against a limit of 50, measured live 2026-09-04).
- **Invalid parameters raise `BadQuery`, never fall back.** `routes/api.py:296` states the rule: answering with a board under a selection the viewer never made is what every parameter there is validated rather than coerced to avoid.
- **Sorting is desktop-only.** `radar.css:894` hides `.cols` below 900px because the rows stack there. Do not add a mobile control; do not unhide the header.
- **Do not change the default ranking.** With no sort asked for, the board must be byte-identical to today's.
- Commit after every task; never stage `.superpowers/`, `.claude/`, `static/radar/dist/`, `scratchpad/`. Work on `dev_personal`.

---

### Task 1: The server sort

**Files:**
- Modify: `features/radar/board.py` (add `SORT_KEYS`, `_sort_value`, `sort_rows`; call it in `build` between the `min_venues` filter at ~488 and `ranked = ranked[:limit]` at ~495; `build`'s signature at ~440)
- Test: `tests/test_radar_board_sort.py` (create)

**Interfaces:**
- Produces: `board.SORT_KEYS: tuple[str, ...]`, `board.sort_rows(ranked, key, direction, leans) -> list`, and `board.build(..., sort=None, direction='desc')`.
- Consumes: `phrasing.ratio_value(mentions, expected)`, `board._tones(tickers, sources, since, now)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_board_sort.py
"""Sorting the board: six keys, missing values last, and the sort happening
BEFORE the row limit -- which is the whole point of doing it server-side."""
import dataclasses

import pytest

from features.radar import board


def row(ticker, mentions=10, expected=5.0, divergence=None, price_move=None):
    """A stand-in for leaderboard.Row carrying only the sorted fields.

    sort_rows reads five attributes and a tones map; it never touches the
    quote, the marks or the series, so a namespace is a truthful fixture
    and keeps this suite independent of the DB.
    """
    return dataclasses.make_dataclass(
        'R', ['ticker', 'mentions', 'expected', 'divergence', 'price_move'])(
        ticker, mentions, expected, divergence, price_move)


def tickers(rows):
    return [r.ticker for r in rows]


def test_the_six_keys_are_the_wire_format():
    assert board.SORT_KEYS == ('ticker', 'mentions', 'divergence', 'ratio',
                               'move', 'lean')


def test_mentions_sorts_loudest_first_then_reverses():
    rows = [row('AAA', mentions=5), row('BBB', mentions=50),
            row('CCC', mentions=20)]

    assert tickers(board.sort_rows(rows, 'mentions', 'desc', {})) == [
        'BBB', 'CCC', 'AAA']
    assert tickers(board.sort_rows(rows, 'mentions', 'asc', {})) == [
        'AAA', 'CCC', 'BBB']


def test_ticker_sorts_case_insensitively():
    rows = [row('bbb'), row('AAA'), row('Ccc')]

    assert tickers(board.sort_rows(rows, 'ticker', 'asc', {})) == [
        'AAA', 'bbb', 'Ccc']
    assert tickers(board.sort_rows(rows, 'ticker', 'desc', {})) == [
        'Ccc', 'bbb', 'AAA']


def test_a_missing_value_sorts_last_in_BOTH_directions():
    """The trap: reverse=True would lift every unpriced row to the top, so
    reversing a price sort would answer with a wall of dashes."""
    rows = [row('AAA', divergence=0.5), row('GONE', divergence=None),
            row('BBB', divergence=0.1)]

    assert tickers(board.sort_rows(rows, 'divergence', 'desc', {})) == [
        'AAA', 'BBB', 'GONE']
    assert tickers(board.sort_rows(rows, 'divergence', 'asc', {})) == [
        'BBB', 'AAA', 'GONE']


def test_ratio_is_mentions_against_its_own_expected():
    """Not raw volume: a 5-mention ticker that normally sees 0.5 is louder
    against itself than a 50-mention ticker that normally sees 100."""
    rows = [row('LOUD', mentions=50, expected=100.0),
            row('ODD', mentions=5, expected=0.5)]

    assert tickers(board.sort_rows(rows, 'ratio', 'desc', {})) == ['ODD', 'LOUD']


def test_lean_reads_the_tone_map_and_ranks_by_net_share():
    rows = [row('BULL'), row('BEAR'), row('QUIET')]
    # Real Tone dataclasses -- what _tones actually hands sort_rows.
    leans = {'BULL': board.Tone(bullish=8, neutral=2, bearish=0),
             'BEAR': board.Tone(bullish=0, neutral=2, bearish=8),
             'QUIET': board.Tone(bullish=0, neutral=0, bearish=0)}

    # QUIET has no tone at all -- last, not "most bearish".
    assert tickers(board.sort_rows(rows, 'lean', 'desc', leans)) == [
        'BULL', 'BEAR', 'QUIET']
    assert tickers(board.sort_rows(rows, 'lean', 'asc', leans)) == [
        'BEAR', 'BULL', 'QUIET']


def test_an_unknown_key_leaves_the_order_alone():
    """sort_rows is not the validator -- the route is. Given something it
    does not know it must not invent an order."""
    rows = [row('AAA', mentions=1), row('BBB', mentions=99)]

    assert tickers(board.sort_rows(rows, 'nonsense', 'desc', {})) == ['AAA', 'BBB']
    assert tickers(board.sort_rows(rows, None, 'desc', {})) == ['AAA', 'BBB']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_board_sort.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'features.radar.board' has no attribute 'SORT_KEYS'`.

- [ ] **Step 3: Implement the sort**

In `features/radar/board.py`, add above `def build(`:

```python
# The board's sort keys, in the order the header reads left to right. This
# spelling IS the wire format: the query parameter, the island's Selection
# field and this tuple never diverge.
SORT_KEYS = ('ticker', 'mentions', 'divergence', 'ratio', 'move', 'lean')


def _lean_value(tone):
    """Net bullish share, or None when nothing was said.

    Tone is a distribution and a sort needs a scalar. Bullish share minus
    bearish share puts a balanced argument in the middle, which is what it
    is -- and a ticker nobody used a sentiment word about has no lean at
    all rather than a neutral one, so it sorts with the missing.
    """
    if tone is None:
        return None
    # Attribute access, not subscript: _tones returns board.Tone dataclasses
    # (board.py:61), and `tone['bullish']` raises TypeError on the first
    # lean sort rather than at import.
    total = tone.bullish + tone.neutral + tone.bearish
    if total <= 0:
        return None
    return (tone.bullish - tone.bearish) / total


def _sort_value(row, key, leans):
    """The one number (or string) a key ranks on. None means 'this row has
    no such measurement', which sorts last however the sort is pointed."""
    if key == 'ticker':
        return row.ticker.lower()
    if key == 'mentions':
        return row.mentions
    if key == 'divergence':
        return row.divergence
    if key == 'ratio':
        return phrasing.ratio_value(row.mentions, row.expected)
    if key == 'move':
        return row.price_move
    if key == 'lean':
        return _lean_value(leans.get(row.ticker))
    return None


def sort_rows(ranked, key, direction, leans):
    """`ranked` reordered by one key. Unknown or absent key: unchanged.

    NEVER `reverse=True`. A descending sort with reverse would lift every
    row whose value is None to the top, so reversing a price sort would
    answer with a wall of dashes -- the rows that have nothing to say about
    the very thing being sorted. Missing sorts last in both directions
    instead, and descending is expressed by negating the number.
    """
    if key not in SORT_KEYS:
        return list(ranked)
    descending = direction != 'asc'

    def ordering(row):
        value = _sort_value(row, key, leans)
        if value is None:
            return (1, 0)
        if isinstance(value, str):
            return (0, value)
        return (0, -value if descending else value)

    ordered = sorted(ranked, key=ordering)
    if descending and key == 'ticker':
        # A string cannot be negated. Reverse the rows that HAVE a ticker
        # and keep the (impossible, but not assumed) missing ones last.
        present = [r for r in ordered if _sort_value(r, key, leans) is not None]
        missing = [r for r in ordered if _sort_value(r, key, leans) is None]
        ordered = list(reversed(present)) + missing
    return ordered
```

Change `build`'s signature (~line 440) from

```python
def build(sources, now, window_hours=4, segments=(), limit=50,
```

to

```python
def build(sources, now, window_hours=4, segments=(), limit=50, sort=None,
          direction='desc',
```

(keep the remaining parameters exactly as they are). Then replace the single line `ranked = ranked[:limit]` (~495) with:

```python
    # BEFORE the limit, which is the whole reason this is server-side.
    # Sorting the already-limited rows would answer "the loudest among the
    # top 50 by divergence" -- indistinguishable on screen from "the
    # loudest 50", and a different list. Measured 2026-09-04: 106
    # candidates against a limit of 50, so 56 rows are in play.
    if sort in SORT_KEYS:
        # _entries computes tones for the rows that SURVIVE the limit; a
        # lean sort has to know them before choosing which those are.
        leans = (_tones(tuple(row.ticker for row in ranked), sources,
                        now - dt.timedelta(hours=window_hours), now)
                 if sort == 'lean' else {})
        ranked = sort_rows(ranked, sort, direction, leans)
    ranked = ranked[:limit]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_board_sort.py -q -p no:cacheprovider`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/board.py personal_apps/tests/test_radar_board_sort.py
git commit -m "feat(radar): sort the board's candidates before the row limit

Six keys, sorted where the limit actually is -- board.build, not
leaderboard.build_rows, which board.py already calls with limit=None.
Missing values sort last in both directions: reverse=True would have
lifted every unpriced row to the top of a reversed price sort.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The query parameters

**Files:**
- Modify: `features/radar/routes/api.py` (`parse_query` — beside the `segment` block at ~293-300; and the `build(...)` call the parsed query feeds)
- Test: `tests/test_radar_api.py` (append)

**Interfaces:**
- Consumes: `board.SORT_KEYS` (Task 1), `BadQuery`.
- Produces: `parse_query` returns `sort` and `direction`; `?sort=` and `?dir=` reach `board.build`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_api.py` (match the file's existing client fixture and import names):

```python
# --- board sort parameters (sortable-list plan, Task 2) --------------------

def test_a_sort_parameter_reaches_the_board(client, monkeypatch):
    """The route's job is to carry the reader's ask through intact."""
    from features.radar import board as board_mod
    seen = {}
    original = board_mod.build

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(board_mod, 'build', spy)
    assert client.get('/radar/api/board?sort=mentions&dir=asc').status_code == 200
    assert seen['sort'] == 'mentions'
    assert seen['direction'] == 'asc'


def test_no_sort_asked_for_leaves_the_default_ranking(client, monkeypatch):
    from features.radar import board as board_mod
    seen = {}
    original = board_mod.build

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(board_mod, 'build', spy)
    assert client.get('/radar/api/board').status_code == 200
    assert seen['sort'] is None


def test_an_unknown_sort_is_refused_rather_than_ignored(client):
    """The rule this file already follows for segment, source and market:
    answering with a board under a selection the viewer never made is worse
    than saying no."""
    assert client.get('/radar/api/board?sort=nonsense').status_code == 400


def test_an_unknown_direction_is_refused(client):
    assert client.get('/radar/api/board?sort=mentions&dir=sideways').status_code == 400


def test_the_payload_echoes_the_sort_back(client):
    """The island seeds its Selection from the payload, never from the URL
    (BoardPage.tsx:25-31). Without the echo, reloading a ?sort= link draws
    sorted rows under a header that believes nothing is sorted."""
    body = client.get('/radar/api/board?sort=mentions&dir=asc').get_json()
    assert body['sort'] == 'mentions'
    assert body['dir'] == 'asc'

    plain = client.get('/radar/api/board').get_json()
    assert plain['sort'] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_api.py -q -p no:cacheprovider -k "sort or direction"`
Expected: FAIL — `KeyError: 'sort'`, and the unknown-sort case returns 200 instead of 400.

- [ ] **Step 3: Implement the parsing**

In `features/radar/routes/api.py`, inside `parse_query`, directly after the `segments` validation block, add:

```python
    # Validated, never coerced -- the rule stated on the segment block above.
    # A sort the server silently ignored would draw the default ranking under
    # a header claiming it was sorted, which is the same lie in a new place.
    sort = args.get('sort') or None
    if sort is not None and sort not in board.SORT_KEYS:
        raise BadQuery('unknown sort')
    direction = args.get('dir', 'desc')
    if direction not in ('asc', 'desc'):
        raise BadQuery('unknown sort direction')
```

Add `sort` and `direction` to the `Query` dataclass `parse_query` returns (beside `min_venues`, ~line 44) and pass them into `board.build(...)` as `sort=` and `direction=` at the call site (~line 322).

**The payload must echo them back.** `BoardPage.tsx:25-31` seeds its `Selection` from the payload's echo fields (`initial.market`, `initial.sources`, `initial.segments`, `initial.window_hours`, `initial.min_venues`) and never parses the URL for them — only `?t=` is read from the address bar. Without an echo, a reload of a `?sort=` URL would render sorted rows under a header that thinks nothing is sorted, and the reader's first click would go the wrong way.

So: add `sort: str | None` and `direction: str` to the `Board` dataclass (`board.py`, beside `min_venues` at ~125), set them in the `Board(...)` construction at the end of `build`, and serialise them beside `'min_venues': board.min_venues` (`routes/api.py:343`):

```python
        'sort': board.sort,
        'dir': board.direction,
```

If `board` is not already imported in this module, add `from features.radar import board` beside the existing feature imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_api.py -q -p no:cacheprovider`
Expected: all pass, including the pre-existing parameter tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): ?sort= and ?dir= on the board, validated not coerced

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The sort in the island's state and URL

**Files:**
- Modify: `static/radar/src/types.ts` (`Selection`, ~316), `static/radar/src/api.ts` (`queryFor`, ~43), `static/radar/src/board/BoardPage.tsx` (the initial `Selection` and `writeUrl`)
- Test: `static/radar/src/api.test.ts` (append)

**Interfaces:**
- Produces: `Selection.sort: SortKey | null`, `Selection.dir: 'asc' | 'desc'`, exported `type SortKey`, `SORT_KEYS` and `defaultDirection(key)`.

- [ ] **Step 1: Write the failing tests**

Append to `static/radar/src/api.test.ts`:

```ts
describe('sort in the query', () => {
  it('is absent when no sort is asked for', () => {
    const query = queryFor({ ...baseSelection, sort: null, dir: 'desc' })
    expect(query).not.toContain('sort=')
    expect(query).not.toContain('dir=')
  })

  it('carries the key and the direction when one is', () => {
    const query = queryFor({ ...baseSelection, sort: 'mentions', dir: 'asc' })
    expect(query).toContain('sort=mentions')
    expect(query).toContain('dir=asc')
  })
})

describe('defaultDirection', () => {
  it('reads ticker A to Z and every number largest first', () => {
    expect(defaultDirection('ticker')).toBe('asc')
    for (const key of ['mentions', 'divergence', 'ratio', 'move', 'lean'] as const) {
      expect(defaultDirection(key)).toBe('desc')
    }
  })
})
```

Add `defaultDirection` to this file's import from `./api`, and define `baseSelection` at the top of the file as a complete `Selection` if the file does not already have one — copy the shape from `static/radar/src/list/tiers.test.tsx:26-29` and add `sort: null, dir: 'desc'`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts src/api.test.ts`
Expected: FAIL — `defaultDirection is not exported`.

- [ ] **Step 3: Implement**

In `static/radar/src/types.ts`, add above `Selection`:

```ts
/** The board's sort keys, in the order the header reads. Same spelling as
 *  the query parameter and as board.SORT_KEYS on the server. */
export const SORT_KEYS = ['ticker', 'mentions', 'divergence', 'ratio',
                          'move', 'lean'] as const
export type SortKey = typeof SORT_KEYS[number]
```

and two fields to `Selection`:

```ts
  /** null is the default two-tier ranking. Server-side: changing it
   *  refetches, because it changes WHICH rows are on the board. */
  sort: SortKey | null
  dir: 'asc' | 'desc'
```

In `static/radar/src/api.ts`, add to `queryFor`, after the `venues` line:

```ts
  // Omitted at the default, the way venues is omitted at 1, so an unsorted
  // board keeps a clean URL.
  //
  // queryFor also builds every row's detail href (TickerRow.tsx:155), so the
  // sort rides into the detail link and comes back with the reader. That is
  // wanted: returning from a ticker to a board that had forgotten its sort
  // would be the same lost-place complaint the ?t= parameter exists to fix.
  if (selection.sort) {
    params.set('sort', selection.sort)
    params.set('dir', selection.dir)
  }
```

and export beside it:

```ts
/** Ticker reads A→Z; every number opens largest-first, because "show me the
 *  biggest" is the question a reader clicks a number to ask. */
export function defaultDirection(key: SortKey): 'asc' | 'desc' {
  return key === 'ticker' ? 'asc' : 'desc'
}
```

In `static/radar/src/types.ts`, add the two echo fields to `BoardPayload` beside `min_venues` (~278):

```ts
  /** Echoed so the island can seed its Selection from the server's own
   *  parsed answer rather than re-parsing the URL. null is unsorted. */
  sort: SortKey | null
  dir: 'asc' | 'desc'
```

In `BoardPage.tsx`, seed from the echo the way every other field is seeded (~25-31) — **not** from the URL, which is only read for `?t=`:

```ts
    sort: initial.sort,
    dir: initial.dir,
```

`writeUrl` needs no change: it already serialises through `queryFor`.

Update `static/radar/src/fixtures.ts` — `payload()` gains `sort: null, dir: 'desc'` — so every existing test keeps compiling.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all pass, and the typecheck is clean — every existing `Selection` literal in the test files now needs the two new fields, so fix each one the compiler names.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/api.ts personal_apps/static/radar/src/board/BoardPage.tsx personal_apps/static/radar/src/api.test.ts personal_apps/static/radar/src
git commit -m "feat(radar): the board's sort lives in Selection and in the URL

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The header becomes controls

**Files:**
- Modify: `static/radar/src/list/ListPane.tsx` (the `cols` div at ~426-432), `static/radar/radar.css` (`.cols` at ~671-685)
- Test: `static/radar/src/list/cols.test.tsx` (create)

**Interfaces:**
- Consumes: `SORT_KEYS`, `SortKey` (Task 3), `defaultDirection` (Task 3), the `onChange(next: Selection)` the pane already takes.
- Produces: `SortCols` — a component rendering the header row.

- [ ] **Step 1: Write the failing tests**

```tsx
// static/radar/src/list/cols.test.tsx
/** The column header stopped being decoration. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SortCols } from './ListPane'
import type { Selection } from '../types'

const selection: Selection = {
  market: 'us', sources: ['bluesky'], segments: [], window: 4,
  minVenues: 1, sort: null, dir: 'desc',
}

function setup(over: Partial<Selection> = {}) {
  const onChange = vi.fn()
  render(<SortCols selection={{ ...selection, ...over }} onChange={onChange} />)
  return onChange
}

it('offers one control per sort key and nothing for price', () => {
  setup()
  for (const name of [/ticker/i, /talk/i, /score/i, /ratio/i, /move/i, /lean/i]) {
    expect(screen.getByRole('button', { name })).toBeTruthy()
  }
  // "price" appears twice as a label and is a control neither time.
  expect(screen.queryByRole('button', { name: /^sort by price$/i })).toBeNull()
})

it('opens a number largest-first and a ticker A to Z', async () => {
  const onChange = setup()
  await userEvent.click(screen.getByRole('button', { name: /talk/i }))
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'mentions', dir: 'desc' }))

  const second = setup()
  await userEvent.click(screen.getByRole('button', { name: /ticker/i }))
  expect(second).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'ticker', dir: 'asc' }))
})

it('reverses on the second click and clears on the third', async () => {
  const onChange = setup({ sort: 'mentions', dir: 'desc' })
  await userEvent.click(screen.getByRole('button', { name: /talk/i }))
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'mentions', dir: 'asc' }))

  const cleared = setup({ sort: 'mentions', dir: 'asc' })
  await userEvent.click(screen.getByRole('button', { name: /talk/i }))
  expect(cleared).toHaveBeenCalledWith(expect.objectContaining({ sort: null }))
})

it('names the action and marks the active column for assistive tech', () => {
  setup({ sort: 'mentions', dir: 'desc' })
  const talk = screen.getByRole('button', { name: /sort by mentions/i })
  expect(talk.closest('[aria-sort]')?.getAttribute('aria-sort'))
    .toBe('descending')
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts src/list/cols.test.tsx`
Expected: FAIL — `SortCols is not exported from './ListPane'`.

- [ ] **Step 3: Implement**

In `ListPane.tsx`, add above the `ListPane` component:

```tsx
/** One header token and what it sorts by. `null` is a label that is not a
 *  control: `price` is a sparkline in one column and the quoted price in
 *  the other, and neither is a ranking anyone asks for. */
const TOKENS: { text: string; key: SortKey | null; name?: string }[][] = [
  [{ text: 'Ticker', key: 'ticker', name: 'ticker A to Z' }],
  [{ text: 'Talk', key: 'mentions', name: 'mentions' },
   { text: 'price', key: null }],
  [{ text: 'Score', key: 'divergence', name: 'divergence' }],
  [{ text: 'Ratio', key: 'ratio', name: 'ratio to normal' },
   { text: 'price', key: null },
   { text: 'move', key: 'move', name: 'price move' }],
  [{ text: 'Lean', key: 'lean', name: 'lean' }],
]

/** The ledger's column header, and the board's only sort control.
 *
 *  Was `aria-hidden` decoration until 2026-09-04. Each dot-separated token
 *  is its own button, so six keys fit without a new control and without
 *  touching the grid: `.cols` is INSIDE the rows scroller and shares one
 *  grid with the rows, so anything that changes a cell's width drifts the
 *  columns off the figures under them (radar.css:671).
 *
 *  Hidden below 900px with the rest of the header -- the rows stack there
 *  and there is no column to head. A sort in the URL is still honoured;
 *  only the means of changing it is absent. */
export function SortCols({ selection, onChange }: {
  selection: Selection
  onChange: (next: Selection) => void
}) {
  function click(key: SortKey) {
    if (selection.sort !== key) {
      onChange({ ...selection, sort: key, dir: defaultDirection(key) })
    } else if (selection.dir === defaultDirection(key)) {
      onChange({ ...selection, dir: selection.dir === 'asc' ? 'desc' : 'asc' })
    } else {
      // Third click: back to the default ranking, where a reader's hand
      // already is rather than at a Reset that exists to undo furniture.
      onChange({ ...selection, sort: null, dir: 'desc' })
    }
  }

  return (
    <div className="cols">
      {TOKENS.map((group, index) => {
        const active = group.find((t) => t.key && t.key === selection.sort)
        return (
          <span key={index} className={index === 2 || index === 4 ? 'r' : undefined}
                aria-sort={active
                  ? (selection.dir === 'asc' ? 'ascending' : 'descending')
                  : undefined}>
            {group.map((token, at) => (
              <Fragment key={token.text}>
                {at > 0 && ' · '}
                {token.key ? (
                  <button type="button"
                          className={token.key === selection.sort ? 'on' : undefined}
                          aria-label={`Sort by ${token.name}`}
                          onClick={() => click(token.key as SortKey)}>
                    {token.text}
                  </button>
                ) : token.text}
              </Fragment>
            ))}
          </span>
        )
      })}
    </div>
  )
}
```

Replace the existing `cols` div (~426-432) with `<SortCols selection={selection} onChange={onChange} />`. Add `SortKey` to the `types` import and `defaultDirection` to the `api` import.

In `radar.css`, after `.cols .r { text-align: right; }` add:

```css
/* The tokens are buttons now (2026-09-04). Everything here exists to keep
   them the same size as the text they replaced: .cols shares one grid with
   the rows, so a button's default padding, border and font would drift
   Score and Lean off the figures under them. */
.cols button {
  appearance: none; background: none; border: 0; padding: 0; margin: 0;
  font: inherit; letter-spacing: inherit; text-transform: inherit;
  color: inherit; cursor: pointer;
}
.cols button:hover { color: var(--fg); }
.cols button.on { color: var(--fg); font-weight: 700; }
.cols button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
```

If `--focus` is not a token in this stylesheet, use the value the rest of the file uses for focus rings — grep `focus-visible` and match it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all pass. Two existing suites build their own `Selection` literal and will not compile until each gains `sort: null, dir: 'desc'` — `src/list/tiers.test.tsx` (~26) and `src/list/watchtier.test.tsx`. `tiers.test.tsx` also asserts that `#radar-rows`' FIRST child is `.cols`; `SortCols` still renders a `.cols` div as the first child, so that assertion holds — check it does rather than assuming.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/static/radar/src/list/ListPane.tsx personal_apps/static/radar/radar.css personal_apps/static/radar/src/list/cols.test.tsx personal_apps/static/radar/src/list/tiers.test.tsx
git commit -m "feat(radar): the column header sorts the board

Six buttons on the tokens that were aria-hidden decoration. The CSS keeps
them the exact size of the text they replaced -- .cols shares one grid with
the rows, and a default button box would drift Score and Lean off the
figures under them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: One flat list while sorting

**Files:**
- Modify: `static/radar/src/list/ListPane.tsx` (the tier rendering after the header)
- Test: `static/radar/src/list/tiers.test.tsx` (append)

**Interfaces:**
- Consumes: `Selection.sort` (Task 3), the existing `splitTiers` and `TierCaption`.

- [ ] **Step 1: Write the failing tests**

Append to `static/radar/src/list/tiers.test.tsx`:

```tsx
describe('a sorted board', () => {
  it('drops the tier captions for one flat list', () => {
    const rows = [row('AAA', 0.5), row('BBB', null), row('CCC', 0.2)]
    const sorted: Selection = { ...selection, sort: 'mentions', dir: 'desc' }
    render(<ListPane payload={{ ...payload, rows }} selection={sorted}
                     selected={null} busy={false} onSelect={() => {}}
                     onChange={() => {}} />)

    // The captions name the two quantities; a sort is one quantity.
    expect(screen.queryByText(/scored against/i)).toBeNull()
    expect(screen.queryByText(/chatter only/i)).toBeNull()
    expect(screen.getByText(/sorted by/i)).toBeTruthy()
  })

  it('keeps the captions when no sort is asked for', () => {
    const rows = [row('AAA', 0.5), row('BBB', null)]
    render(<ListPane payload={{ ...payload, rows }} selection={selection}
                     selected={null} busy={false} onSelect={() => {}}
                     onChange={() => {}} />)

    expect(screen.queryByText(/sorted by/i)).toBeNull()
  })

  it('leaves Watching pinned above the sorted rows', () => {
    const rows = [row('AAA', 0.5), row('BBB', null)]
    const sorted: Selection = { ...selection, sort: 'mentions', dir: 'desc' }
    render(<ListPane payload={{ ...payload, rows, watch_rows: [row('ZZZ', 0.1)] }}
                     selection={sorted} selected={null} busy={false}
                     onSelect={() => {}} onChange={() => {}}
                     watching={['ZZZ']} />)

    expect(screen.getByText('Watching')).toBeTruthy()
  })
})
```

Update this file's `selection` literal (~26) to include `sort: null, dir: 'desc'`, and use its existing `payload` — if it has none, import `payload` from `../fixtures`.

This file also pins the CLOSED-MARKET rule: with the market shut there are no captions at all. A sort must not resurrect one — check that existing test still passes rather than assuming, since the new "Sorted by" line is rendered from the same region.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts src/list/tiers.test.tsx`
Expected: FAIL — the captions still render and no "Sorted by" line exists.

- [ ] **Step 3: Implement**

In `ListPane.tsx`, where the two tiers are rendered, branch on the sort. Add above the return:

```tsx
  // A sort is ONE quantity that every row either has or explicitly lacks,
  // so the split between "ranked on divergence" and "ranked on chatter"
  // has nothing to say about it -- and two captions over one ordering
  // would be the very confusion they were added to prevent.
  const sorting = selection.sort !== null
  const sortLabel: Record<SortKey, string> = {
    ticker: 'ticker', mentions: 'mentions', divergence: 'divergence',
    ratio: 'ratio to normal', move: 'price move', lean: 'lean',
  }
```

and render, in place of the two captioned tiers when `sorting` is true:

```tsx
        {sorting ? (
          <>
            <p className="tier">
              <b>Sorted by {sortLabel[selection.sort as SortKey]}</b>
              <span className="dot"> ·</span>{' '}
              <span className="what">
                {selection.dir === 'asc' ? 'smallest first' : 'largest first'}
                , across the whole board
              </span>
              <span className="n">{ranked.length}</span>
            </p>
            {ranked.map(renderRow)}
          </>
        ) : theExistingTwoTierBlock}
```

`theExistingTwoTierBlock` above is a stand-in for the JSX that is in the file **right now** — the `<TierCaption tier="scored" .../>`, the scored rows, the second caption and the chatter rows. Move that existing JSX into the `else` branch **verbatim**, character for character; do not retype or restructure it. It is long, it encodes several earlier decisions, and every difference is a regression.

The rows arrive in the server's order in both branches; the island never reorders.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/static/radar/src/list/ListPane.tsx personal_apps/static/radar/src/list/tiers.test.tsx
git commit -m "feat(radar): a sorted board is one flat list, not two tiers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Spec deviations, the full gate, and a live look

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-radar-sortable-board-list-design.md`

- [ ] **Step 1: Record the deviations in the spec**

Append before "## Out of scope":

```markdown
## Built as (2026-09-04, deviations from the text above)

- **The sort lives in `board.build`, not `leaderboard.build_rows`.** The
  spec named the wrong file: `board.py:462` already calls `build_rows` with
  `limit=None`, and the real top-N is `ranked = ranked[:limit]` at
  `board.py:495`, after the segment and venue filters. The sort goes
  immediately before that line. Measured 2026-09-04: 106 candidates against
  a limit of 50, so 56 rows are genuinely in play.
- **An invalid `sort` or `dir` raises `BadQuery` (400)** rather than falling
  back to the default ranking as the spec said. `routes/api.py` validates
  every other parameter and refuses rather than coerces, for the reason
  stated there: answering with a board under a selection the viewer never
  made is what that discipline exists to prevent. A silently-ignored sort
  would draw the default ranking under a header claiming otherwise.
- **A lean sort fetches tones for the whole candidate set.** `_tones` runs
  inside `_entries`, which today sees only the rows that survived the limit
  -- so ranking by lean has to know the tones before choosing which rows
  those are. It doubles one grouped query (106 tickers instead of 50) on a
  candidate build that measures 1.7 s, and only when that key is chosen.
- **Sorting is desktop-only**, recorded above under "Width".
```

Change the status line to `**Status:** built 2026-09-04 (plan docs/superpowers/plans/2026-09-04-radar-sortable-board-list.md)`.

- [ ] **Step 2: Full gate**

From `personal_apps/`:

```bash
python -m pytest tests/test_radar_board_sort.py tests/test_radar_api.py tests/test_radar_leaderboard.py tests/test_radar_scoring.py -q -p no:cacheprovider && npx vitest run -c vite.radar.config.ts && npx tsc --noEmit
```

Expected: every suite green.

- [ ] **Step 3: A live look at both widths**

Run the app locally (`personal_apps` on port 5001, `PYTHONPATH=.`), then with python-playwright — NOT the browser MCP — screenshot `/radar/` at 1440×900 and at 390×844, first unsorted and then with `?sort=mentions&dir=desc`. Read the PNGs.

Check: the header columns still line up with the figures under them at 1440 (the grid trap), the active token is visibly active, the flat list replaces the two captions, Watching is still on top, and at 390 there is no header and no sort affordance while a `?sort=` URL still renders sorted rows.

- [ ] **Step 4: Commit and merge**

```bash
git add docs/superpowers/specs/2026-09-04-radar-sortable-board-list-design.md
git commit -m "docs(radar): sortable-list spec marked built, with the deviations

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git checkout main && git merge dev_personal && git push origin main && git push origin dev_personal && git checkout dev_personal
```

- [ ] **Step 5: Operator sequence (Michi, on the VPS)**

Routine deploy. No migration, no new service, no backfill — the change is a query parameter, a sort, and a header. Nothing to check afterwards beyond opening the board and clicking a column.

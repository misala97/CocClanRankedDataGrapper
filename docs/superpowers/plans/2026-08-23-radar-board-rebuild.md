# Radar Board Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the radar board with a two-pane surface — a scannable list whose rows say *why* in words, and a detail panel that answers *is this real* with years of price, the actual posts, and a chatter breakdown.

**Architecture:** One route, two panes. The list payload stays small and carries a per-row phrase built server-side; the panel fetches one ticker from its own endpoint so three years of closes never ride in the list. Selection is a URL parameter. Judgement about data — which phrase a row deserves, what the written read says — lives in Python where pytest can reach it.

**Tech Stack:** Flask + SQLAlchemy (MySQL 8 dev / MariaDB prod), React 19 + TypeScript + Vite island, vitest + Testing Library, pytest.

## Global Constraints

- **Green and red mean price direction and nothing else.** Violet (`--mark`) carries chatter, selection and focus. No green/red tone bar — this has been built and deleted twice.
- **An absence is never a zero.** `expected == 0` means *no baseline*, not *we expected none*. `against 0 typical` must not survive this rebuild.
- **A mark carried by every row is not a mark.** Page-level facts (market closed, everything provisional) are stated once by the page.
- Working directory is `personal_apps`. Branch `dev_personal`. Never commit on `main`.
- Files are **CRLF**. Use the Edit tool for edits; a scripted `str.replace` keyed on `\n` silently no-ops.
- PowerShell 5.1 has no `&&`. Use `;` or separate lines.
- `npm run build` runs `tsc --noEmit` first; `static/radar/src` is in `tsconfig.json` and must stay there.
- Visual execution — palette, type, spacing, motion — is **out of scope**. This plan ends at working structure. `impeccable` follows.
- Mobile gets a single-column fallback and no design attention.
- Spec: `docs/superpowers/specs/2026-08-23-radar-board-rebuild-design.md`.
  Approved mockups: `docs/superpowers/mockups/2026-08-23-radar-board-busy.html` and `-quiet.html`. **Read the mockups before the frontend tasks** — they are the agreed arrangement.

---

## File Structure

**Created**
- `features/radar/phrasing.py` — the row phrase and the panel's written read, as typed clauses. Judgement about data, no formatting.
- `features/radar/detail.py` — everything one ticker's panel needs: identity, chart at a span, breakdown, posts.
- `tests/test_radar_phrasing.py`, `tests/test_radar_detail.py`
- `static/radar/src/list/TickerRow.tsx`, `static/radar/src/list/ListPane.tsx`
- `static/radar/src/detail/DetailPane.tsx`, `Identity.tsx`, `PriceChart.tsx`, `Breakdown.tsx`, `Posts.tsx`
- `static/radar/src/list/TickerRow.test.tsx`, `static/radar/src/detail/PriceChart.test.tsx`

**Modified**
- `features/radar/history.py` — three years instead of one; refetch shallow tickers.
- `features/radar/leaderboard.py` — count what the floor excluded, and why.
- `features/radar/board.py` — carry clauses and exclusions; the per-row year-long chart moves out.
- `features/radar/routes/api.py` — new serializers, new endpoint.
- `static/radar/src/types.ts`, `api.ts`, `board/Controls.tsx`, `board/geometry.ts`, `board/BoardPage.tsx`

**Deleted**
- `static/radar/src/board/LeadCard.tsx`, `board/ScanRow.tsx`, `board/Marks.tsx` — the two-tier arrangement collapses into one list.

---

### Task 1: Three years of price, and a way to notice shallow tickers

`HISTORY_DAYS = 260` stores about one year. The panel offers a 3Y span. Raising the constant alone is not enough: `tickers_needing_history` only refetches when the newest close is stale, and every ticker's newest close is current, so nothing would ever deepen.

**Files:**
- Modify: `personal_apps/features/radar/history.py`
- Test: `personal_apps/tests/test_radar_history.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `history.HISTORY_DAYS == 780`; `history.tickers_needing_history(candidates, today, stale_after_days=2)` unchanged signature, now also returns tickers whose stored span is shallower than `MIN_STORED_RATIO * HISTORY_DAYS`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_history.py`:

```python
def test_three_years_are_requested(clean_history):
    """The panel offers a 3Y span. 260 trading days is about one year."""
    assert history.HISTORY_DAYS >= 780


def test_a_ticker_stored_shallow_is_refetched(clean_history):
    """Raising HISTORY_DAYS does nothing on its own: every stored ticker has
    a current newest close, so the staleness rule never fires and the store
    stays one year deep forever."""
    today = dt.date(2026, 8, 23)
    history.record_closes('ZZSHALLOW', [
        (today - dt.timedelta(days=n), decimal.Decimal('1.00'))
        for n in range(40)
    ], NOW)

    assert 'ZZSHALLOW' in history.tickers_needing_history(
        ['ZZSHALLOW'], today)


def test_a_ticker_stored_deep_is_left_alone(clean_history):
    today = dt.date(2026, 8, 23)
    history.record_closes('ZZDEEP', [
        (today - dt.timedelta(days=n), decimal.Decimal('1.00'))
        for n in range(history.HISTORY_DAYS)
    ], NOW)

    assert 'ZZDEEP' not in history.tickers_needing_history(['ZZDEEP'], today)
```

If `clean_history`, `NOW` or the `decimal` import are not already in that file, read its top and reuse whatever fixture the existing tests use; do not add a second fixture.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_radar_history.py -q -k "three_years or shallow or deep"
```

Expected: FAIL — `assert 260 >= 780`, and `'ZZSHALLOW' not in []`.

- [ ] **Step 3: Implement**

In `features/radar/history.py`, change the constant and its comment:

```python
# Three years. The detail panel offers 1M / 6M / 1Y / 3Y, and the longest span
# is the one that answers "has this stock done this before" -- which is the
# whole reason a reader opens the panel on a ticker they have never seen.
#
# ~780 trading days x 247 tickers is about 190k rows, which is nothing, and
# one full backfill takes about an hour against the provider's eight-per-
# minute limit.
HISTORY_DAYS = 780

# A stored ticker counts as deep enough at this fraction of HISTORY_DAYS.
# Not 1.0: a recent IPO has less history than we ask for and always will, and
# refetching it every cycle forever would spend the whole rate limit on the
# tickers that can never satisfy it.
MIN_STORED_RATIO = 0.9
```

Then in `tickers_needing_history`, after the existing missing/stale partition, add shallow tickers. Read the function first — it returns most-urgent-first and keeps the caller's order within each group. Add a third group **last**, because a ticker we can already draw is less urgent than one we cannot:

```python
    stored = _stored_counts(candidates)
    floor = int(HISTORY_DAYS * MIN_STORED_RATIO)
    shallow = [t for t in candidates
               if t not in missing and t not in stale
               and stored.get(t, 0) < floor]

    return missing + stale + shallow
```

And the helper it needs:

```python
def _stored_counts(tickers):
    """How many closes are stored per ticker. Absent means none."""
    if not tickers:
        return {}
    rows = (db.session.query(RadarDailyClose.ticker, sa.func.count())
            .filter(RadarDailyClose.ticker.in_(list(tickers)))
            .group_by(RadarDailyClose.ticker).all())
    return dict(rows)
```

Add `import sqlalchemy as sa` at the top if it is not already there.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/test_radar_history.py -q
```

Expected: PASS, all of them.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/history.py personal_apps/tests/test_radar_history.py
git commit -m "feat(radar): store three years of closes, and notice shallow tickers"
```

---

### Task 2: The row phrase, as typed clauses

**Files:**
- Create: `personal_apps/features/radar/phrasing.py`
- Create: `personal_apps/tests/test_radar_phrasing.py`

**Interfaces:**
- Consumes: `leaderboard.Row` (has `.ticker .mentions .expected .authors .sources .price_move .price_status .baseline_days .mention_z`).
- Produces: `phrasing.Clause(kind: str, text: str)` and `phrasing.row_clauses(row, session) -> list[Clause]`. Valid kinds: `'ratio' 'venues' 'people' 'price-up' 'price-down' 'price-flat' 'new' 'warn'`. The client styles by `kind` and never re-derives wording.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_radar_phrasing.py`:

```python
# personal_apps/tests/test_radar_phrasing.py
"""The row phrase is the answer to "why is this on the list".

The live board's failure was not that the numbers were wrong -- it was that
the biggest number on the page belonged to the row that scored nothing, and
nothing said why. These tests pin the wording, because the wording IS the
feature.
"""
import dataclasses

from features.radar import phrasing


@dataclasses.dataclass
class FakeRow:
    ticker: str = 'ZZZ'
    mentions: int = 40
    expected: float = 1.0
    authors: int = 11
    sources: tuple = ('bluesky', 'fourchan')
    price_move: float | None = 0.182
    price_status: str = 'ok'
    baseline_days: int | None = 30
    mention_z: float | None = 4.1


def kinds(clauses):
    return [c.kind for c in clauses]


def text(clauses):
    return ' '.join(c.text for c in clauses)


def test_a_measurable_row_says_how_unusual_how_broad_and_what_price_did():
    clauses = phrasing.row_clauses(FakeRow(), session='regular')

    assert kinds(clauses) == ['ratio', 'venues', 'people', 'price-up']
    assert '40x its normal' in text(clauses).replace('×', 'x')
    assert '2 venues' in text(clauses)
    assert '11 people' in text(clauses)


def test_no_baseline_is_not_a_ratio_against_zero():
    """The live page prints "209 mentions in 4h against 0 typical" and then
    scores it with an em-dash. Expected of zero means there is no baseline;
    rendering it as a quantity is the absence-as-zero mistake."""
    clauses = phrasing.row_clauses(
        FakeRow(mentions=209, expected=0.0, mention_z=None), session='regular')

    assert kinds(clauses)[0] == 'new'
    assert '209 mentions' in text(clauses)
    assert 'nothing to compare against yet' in text(clauses)
    assert '0 typical' not in text(clauses)
    assert 'ratio' not in kinds(clauses)


def test_a_narrow_row_says_so_instead_of_counting_venues():
    """One channel and two voices is the shape of a pump. Saying "1 venue,
    2 people" in the same grammar as a broad row buries that."""
    clauses = phrasing.row_clauses(
        FakeRow(sources=('bluesky',), authors=2), session='regular')

    assert 'warn' in kinds(clauses)
    assert 'one venue only' in text(clauses) or '2 voices' in text(clauses)


def test_a_closed_market_carries_no_price_clause():
    """The page says "market closed" once. Repeating it on every row makes it
    noise, and printing 0.00% asserts the price held steady when nothing
    traded."""
    clauses = phrasing.row_clauses(
        FakeRow(price_status='closed', price_move=None), session='closed')

    assert not any(k.startswith('price') for k in kinds(clauses))


def test_a_frozen_tape_is_not_a_flat_price():
    clauses = phrasing.row_clauses(
        FakeRow(price_status='stale', price_move=None), session='regular')

    assert 'price-flat' not in kinds(clauses)
    assert 'warn' in kinds(clauses)
    assert 'not printed' in text(clauses)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd personal_apps && python -m pytest tests/test_radar_phrasing.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'features.radar.phrasing'`.

- [ ] **Step 3: Implement**

Create `personal_apps/features/radar/phrasing.py`:

```python
# personal_apps/features/radar/phrasing.py
"""Why a row is on the list, in words.

Server-side because deciding which phrase a row deserves is judgement about
data, and it belongs where the data is and where pytest can reach it. Typed
clauses rather than a finished sentence because the client styles the parts
differently, and a client that re-derived the wording from raw numbers would
be a second implementation of the same judgement.
"""
import dataclasses

# Below this, "n× its normal" is arithmetic on noise rather than a finding.
MIN_RATIO_BASELINE = 0.5

# One venue, or a handful of voices, is the shape of a pump. It gets said
# rather than counted, because "1 venue · 2 people" in the same grammar as a
# broad row buries the one fact that matters about it.
NARROW_VOICES = 3


@dataclasses.dataclass(frozen=True)
class Clause:
    """One styled fragment of a phrase.

    `kind` is the contract with the client: it styles by kind and never parses
    `text`. Adding a kind means adding a style, which is the intended friction.
    """
    kind: str
    text: str


def _ratio(mentions, expected):
    value = mentions / expected
    if value >= 10:
        return f'{round(value):.0f}×'
    return f'{value:.1f}×'.replace('.0×', '×')


def row_clauses(row, session):
    """The phrase for one leaderboard row, in reading order.

    `session` is the exchange state. With the market shut there is no price
    clause at all -- the page says "market closed" once, and a mark carried by
    every row is not a mark.
    """
    clauses = []

    # An expected of zero is not "we expected none", it is "no baseline".
    if not row.expected or row.expected < MIN_RATIO_BASELINE:
        clauses.append(Clause('new', 'new here'))
        clauses.append(Clause(
            'ratio', f'{row.mentions} mentions, '
                     f'nothing to compare against yet'))
    else:
        clauses.append(Clause(
            'ratio', f'{_ratio(row.mentions, row.expected)} its normal'))

    venues = len(row.sources)
    if venues < 2 or row.authors < NARROW_VOICES:
        parts = []
        if venues < 2:
            parts.append('one venue only')
        if row.authors < NARROW_VOICES:
            parts.append(f'{row.authors} voices')
        clauses.append(Clause('warn', ', '.join(parts)))
    else:
        clauses.append(Clause('venues', f'{venues} venues'))
        clauses.append(Clause('people', f'{row.authors} people'))

    clauses.extend(_price_clauses(row, session))
    return clauses


def _price_clauses(row, session):
    """Nothing at all when there is no price fact to state.

    Three different silences, and only one of them is about the stock: the
    exchange is shut (says nothing about this ticker), the tape froze (says
    something, and it is a warning), or we have no quote.
    """
    if session == 'closed' or row.price_status == 'closed':
        return []
    if row.price_status == 'stale':
        return [Clause('warn', 'tape has not printed')]
    if row.price_move is None:
        return []

    pct = row.price_move * 100
    if abs(pct) < 0.5:
        return [Clause('price-flat', 'price flat')]
    kind = 'price-up' if pct > 0 else 'price-down'
    return [Clause(kind, f'price {pct:+.0f}%')]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd personal_apps && python -m pytest tests/test_radar_phrasing.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/phrasing.py personal_apps/tests/test_radar_phrasing.py
git commit -m "feat(radar): say why a row is on the list, in words"
```

---

### Task 3: Count what the floor excluded, and why

A two-row board and a broken board are indistinguishable unless the page can say what did not make it.

**Files:**
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/board.py` (caller)
- Test: `personal_apps/tests/test_radar_leaderboard.py`

**Interfaces:**
- Consumes: `scoring.is_eligible`, `scoring.MIN_MENTIONS`, `scoring.MIN_DISTINCT_TEXT_RATIO`, `scoring._VOICE_FLOOR`.
- Produces: `leaderboard.Ranking(rows: list[Row], excluded: dict[str, int])`. `build_rows` returns a `Ranking`, **not** a list — every caller changes. Reason keys, exactly: `'too_few_mentions'`, `'too_few_voices'`, `'repeated_text'`, `'one_venue'`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_leaderboard.py`:

```python
def test_the_ranking_reports_why_tickers_were_dropped(clean):
    """Without this a quiet board and a dead ingest look identical, and the
    reader has no way to tell which one they are looking at."""
    # One loud ticker carried by a single voice: below the voice gate.
    for n in range(8):
        post(f'{PREFIX}ONE', author='solo', minutes_ago=30, text=f'take {n}')
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW, window_hours=4)

    assert ranking.rows == []
    assert ranking.excluded['too_few_voices'] == 1


def test_a_row_that_clears_the_floor_is_not_counted_as_excluded(clean):
    for n, who in enumerate(('a', 'b', 'c', 'd')):
        post(f'{PREFIX}OK', author=who, minutes_ago=30, text=f'distinct {n}')
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW, window_hours=4)

    assert [r.ticker for r in ranking.rows] == [f'{PREFIX}OK']
    assert sum(ranking.excluded.values()) == 0


def test_the_breadth_filter_reports_separately_from_the_floor(clean):
    """`one venue only` is the reader's own filter doing its job, not the
    eligibility floor rejecting something. Merging them would tell the reader
    the data was worse than it is."""
    for n, who in enumerate(('a', 'b', 'c', 'd')):
        post(f'{PREFIX}SOLO', author=who, minutes_ago=30, text=f'text {n}')
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW, window_hours=4,
                                     min_venues=2)

    assert ranking.rows == []
    assert ranking.excluded['one_venue'] == 1
    assert ranking.excluded.get('too_few_voices', 0) == 0
```

Reuse whatever `clean`, `post`, `PREFIX` and `NOW` helpers that file already defines — read its top first. If there is no `post` helper, use the same bucket/mention construction the neighbouring tests use.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd personal_apps && python -m pytest tests/test_radar_leaderboard.py -q -k "excluded or dropped or breadth"
```

Expected: FAIL — `AttributeError: 'list' object has no attribute 'rows'`.

- [ ] **Step 3: Implement**

In `features/radar/leaderboard.py`, add the dataclass beside `Row`:

```python
@dataclasses.dataclass
class Ranking:
    """Rows worth showing, and an account of what was left out.

    The account is not decoration. The eligibility floor is the single biggest
    reason this board is short, and until now it dropped tickers with no
    trace -- so a quiet market and a stopped daemon rendered identically.
    """
    rows: list
    excluded: dict
```

Add a helper that names why one ticker failed:

```python
def _rejection(contributions):
    """Which gate a ticker failed, or None if it passed.

    Reported against the ticker's BEST kind, not every kind it touched: a
    ticker carried by three Bluesky authors and one Telegram channel is not
    "too few voices" merely because the broadcast side was thin.
    """
    best = None
    for kind, part in contributions.items():
        if part.mentions < scoring.MIN_MENTIONS:
            reason = 'too_few_mentions'
        elif part.voices < scoring._VOICE_FLOOR.get(
                kind, scoring.MIN_DISTINCT_AUTHORS):
            reason = 'too_few_voices'
        elif part.text_ratio < scoring.MIN_DISTINCT_TEXT_RATIO:
            reason = 'repeated_text'
        else:
            return None
        # Later gates mean the earlier ones passed, so a ticker that got
        # further on one kind is better described by that kind's failure.
        order = ('too_few_mentions', 'too_few_voices', 'repeated_text')
        if best is None or order.index(reason) > order.index(best):
            best = reason
    return best
```

In `build_rows`, replace the eligibility guard:

```python
        if not scoring.is_eligible(contributions):
            excluded[_rejection(contributions)] += 1
            continue
```

Replace the breadth guard:

```python
        if len(contributing) < min_venues:
            excluded['one_venue'] += 1
            continue
```

Initialise the counter beside `rows = []`:

```python
    rows = []
    excluded = collections.Counter()
```

And change the return:

```python
    rows.sort(key=lambda r: (r.divergence is not None,
                             r.divergence if r.divergence is not None else 0,
                             r.mention_z or 0), reverse=True)
    return Ranking(rows=rows[:limit], excluded=dict(excluded))
```

Then fix the caller in `features/radar/board.py` — find the `leaderboard.build_rows(...)` call inside `build` and take `.rows` from it, keeping `.excluded` for Task 4:

```python
    ranking = leaderboard.build_rows(sources, now, window_hours=window_hours,
                                     segment=None, limit=None, session=session)
    ranked = ranking.rows
```

- [ ] **Step 4: Run the whole radar suite**

```bash
cd personal_apps && python -m pytest tests/ -q -k radar
```

Expected: PASS. Any other caller of `build_rows` that still treats the result as a list will fail here — fix it the same way.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/leaderboard.py personal_apps/features/radar/board.py personal_apps/tests/test_radar_leaderboard.py
git commit -m "feat(radar): account for the tickers the floor left out"
```

---

### Task 4: Board payload — clauses in, the year-long chart out

**Files:**
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Test: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Consumes: `phrasing.row_clauses`, `leaderboard.Ranking`.
- Produces: board payload rows gain `clauses: [{kind, text}]` and lose `chart`. Payload gains `excluded: {reason: count}`. `board.Entry.chart` and the `_chart` serializer are removed; `board.CHART_DAYS`, `_daily_counts`, `_first_watched_day` and `_chart_for` move to `detail.py` in Task 5 — leave them in place for now so nothing breaks between commits.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_a_row_carries_its_phrase_rather_than_raw_numbers(client, one_row):
    payload = json.loads(client.get('/radar/api/board').data)
    row = payload['rows'][0]

    assert [c['kind'] for c in row['clauses']]
    assert all({'kind', 'text'} == set(c) for c in row['clauses'])


def test_a_row_no_longer_ships_a_year_of_closes(client, one_row):
    """780 closes per row would make a twenty-row board carry sixteen thousand
    numbers to draw twenty sparklines. The panel fetches its own."""
    payload = json.loads(client.get('/radar/api/board').data)

    assert 'chart' not in payload['rows'][0]


def test_the_payload_says_what_was_left_out(client, one_row):
    payload = json.loads(client.get('/radar/api/board').data)

    assert isinstance(payload['excluded'], dict)
```

`one_row` must be a fixture that puts exactly one eligible ticker on the board. If `tests/test_radar_api.py` has no such fixture, add one — and note the lesson from 2026-08-22: a serializer bug shipped green because every test iterated an empty `rows` list. **Teeth-check it**: comment out the `clauses` line in `_row`, confirm the first test fails, restore.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_radar_api.py -q -k "phrase or year_of_closes or left_out"
```

Expected: FAIL — `KeyError: 'clauses'`.

- [ ] **Step 3: Implement**

In `features/radar/board.py`: add `clauses` to the `Entry` dataclass, remove `chart`:

```python
    triplet: dict         # hours -> z or None
    tone: Tone
    # Why this row is on the list, in words. See phrasing.py -- the client
    # styles by clause kind and never re-derives the wording.
    clauses: list
```

Add `excluded` to the `Board` dataclass:

```python
    min_venues: int
    # What the eligibility floor and the breadth filter left out, by reason.
    # Without it a quiet board and a stopped ingest render identically.
    excluded: dict
```

In `build`, import phrasing (`from . import phrasing`), build the clauses where the `Entry` is constructed, drop the `chart=` argument, and pass `excluded=ranking.excluded` into the `Board(...)` call:

```python
            clauses=phrasing.row_clauses(row, session),
```

In `features/radar/routes/api.py`: delete the `_chart` function and the `'chart': _chart(entry.chart),` line from `_row`, add the clauses, and add `excluded` to `serialize`:

```python
        'clauses': [{'kind': c.kind, 'text': c.text} for c in entry.clauses],
```

```python
        'segment_counts': board.segment_counts,
        'excluded': board.excluded,
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd personal_apps && python -m pytest tests/ -q -k radar
```

Expected: PASS. Tests asserting the old `chart` key will fail — delete those assertions; the panel covers it from Task 5.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar personal_apps/tests
git commit -m "feat(radar): the board payload carries phrases, not a year of closes"
```

---

### Task 5: The detail endpoint

**Files:**
- Create: `personal_apps/features/radar/detail.py`
- Create: `personal_apps/tests/test_radar_detail.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/features/radar/board.py` (move the chart helpers out)

**Interfaces:**
- Consumes: `history.closes_for`, `board._daily_counts`, `board._first_watched_day`, `universe`, `quotes`, `models.RadarPost`, `models.RadarMention`.
- Produces: `detail.SPAN_DAYS = {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}`; `detail.build(ticker, sources, now, window_hours=4, span='1Y') -> Detail`; route `GET /radar/api/ticker/<ticker>?sources=&window=&span=` returning `{identity, read, chart, breakdown, posts}`.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_radar_detail.py`:

```python
# personal_apps/tests/test_radar_detail.py
"""One ticker's panel. The surface that answers "is this real".

The board can honestly say three venues are talking. Only this can show what
each venue said, and that is the part that decides whether a spike is worth
anything.
"""
import datetime as dt
import decimal
import json

import pytest

from app import app as flask_app
from extensions import db
from features.radar import detail, history
from models import RadarPost, TickerUniverse

NOW = dt.datetime(2026, 8, 23, 15, 0, 0)
TICKER = 'ZZDETAIL'


@pytest.fixture()
def one_ticker():
    with flask_app.app_context():
        db.session.query(RadarPost).filter(
            RadarPost.external_id.like('zzd-%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter_by(symbol=TICKER).delete()
        db.session.add(TickerUniverse(
            symbol=TICKER, name='Zed Detail Corp - Common Stock',
            exchange='NASDAQ', first_seen=NOW - dt.timedelta(days=400),
            market_cap=decimal.Decimal('110000000')))
        history.record_closes(TICKER, [
            (NOW.date() - dt.timedelta(days=n), decimal.Decimal('1.00') + n)
            for n in range(400)
        ], NOW)
        db.session.commit()
        yield
        db.session.query(RadarPost).filter(
            RadarPost.external_id.like('zzd-%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter_by(symbol=TICKER).delete()
        db.session.commit()


def test_the_span_decides_how_much_price_comes_back(one_ticker):
    month = detail.build(TICKER, ['bluesky'], NOW, span='1M')
    year = detail.build(TICKER, ['bluesky'], NOW, span='1Y')

    assert len(month.chart.closes) == detail.SPAN_DAYS['1M']
    assert len(year.chart.closes) == detail.SPAN_DAYS['1Y']


def test_chatter_before_watching_began_is_null_not_zero(one_ticker):
    """Price goes back years and chatter starts on 2026-08-21. Drawing zeros
    for 2024 would assert silence we never observed."""
    built = detail.build(TICKER, ['bluesky'], NOW, span='1Y')

    assert built.chart.chatter[0] is None
    assert len(built.chart.chatter) == len(built.chart.closes)


def test_an_unknown_ticker_raises_rather_than_inventing_a_panel(one_ticker):
    with pytest.raises(detail.UnknownTicker):
        detail.build('ZZNOPE', ['bluesky'], NOW)


def test_the_endpoint_answers_with_every_zone(client, one_ticker):
    body = json.loads(client.get(f'/radar/api/ticker/{TICKER}').data)

    for key in ('identity', 'read', 'chart', 'breakdown', 'posts'):
        assert key in body, key


def test_the_endpoint_404s_on_a_ticker_that_does_not_exist(client):
    assert client.get('/radar/api/ticker/ZZNOPE').status_code == 404


def test_a_bad_span_is_rejected(client, one_ticker):
    assert client.get(
        f'/radar/api/ticker/{TICKER}?span=nonsense').status_code == 400
```

Reuse the `client` fixture from `tests/test_radar_api.py`'s conftest if one exists; otherwise add the same one this repo already uses for radar route tests.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd personal_apps && python -m pytest tests/test_radar_detail.py -q
```

Expected: FAIL with `ImportError: cannot import name 'detail'`.

- [ ] **Step 3: Implement the module**

Create `personal_apps/features/radar/detail.py`:

```python
# personal_apps/features/radar/detail.py
"""Everything one ticker's panel needs.

Separate from board.py because it answers a different question. The board
answers "which of these deserves attention" for many tickers; this answers
"is this real" for one, and the two have opposite shapes -- the board wants
every row small, this wants one ticker deep.

That split is also why the panel has its own endpoint. Three years is ~780
closes; carrying that per row would make a twenty-row board ship sixteen
thousand numbers to draw twenty sparklines.
"""
import collections
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost, TickerUniverse

from . import history, quotes as quotes_mod, universe

# Calendar days per span, not trading days: the chart is indexed by calendar
# day so price and chatter stay aligned through weekends.
SPAN_DAYS = {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}

# How many posts the panel shows. Enough to form an opinion, few enough to
# read; the count of the rest is stated beside them.
POST_LIMIT = 25


class UnknownTicker(Exception):
    """No universe row. Not a 500 -- a URL can name anything."""


@dataclasses.dataclass
class Chart:
    """Price and chatter over the same calendar days, sharing `start`.

    `closes[i]` is None where the market did not trade. `chatter[i]` is None
    where we were not yet watching. Different absences and drawn differently:
    the price line spans its gaps, the chatter lane stops at its boundary.
    """
    start: dt.date
    closes: list
    chatter: list
    watched_from: dt.date | None


@dataclasses.dataclass
class Venue:
    source: str
    mentions: int
    voices: int


@dataclasses.dataclass
class Breakdown:
    venues: list
    bullish: int
    neutral: int
    bearish: int
    # The pump tell. One account posting forty times reads as forty mentions
    # everywhere else on the surface; only this exposes it.
    top_author_share: float | None
    top_two_share: float | None
    peak_hour: dt.datetime | None
    peak_count: int
    first_seen: dt.date | None
    repeated_text: float | None


@dataclasses.dataclass
class Detail:
    ticker: str
    name: str | None
    exchange: str | None
    segment: str
    market_cap: object
    ipo_date: object
    price: object
    price_move: object
    price_status: str
    span: str
    chart: Chart
    breakdown: Breakdown
    posts: list
    post_total: int


def _chart(ticker, now, days):
    """Both arrays indexed by calendar day, oldest first."""
    start = now.date() - dt.timedelta(days=days - 1)
    stored = dict(history.closes_for([ticker], days=days,
                                     today=now.date()).get(ticker, []))
    counts = _daily_counts(ticker, start, now)
    watched = _first_watched_day()

    closes, chatter = [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        closes.append(stored.get(day))
        # None before we were watching: an absence, never a zero.
        chatter.append(None if watched is None or day < watched
                       else counts.get(day, 0))
    return Chart(start=start, closes=closes, chatter=chatter,
                 watched_from=watched)


def _daily_counts(ticker, start, now):
    """Mentions per calendar day. Buckets are retained forever."""
    from models import RadarBucketSource
    rows = (db.session.query(
                sa.func.date(RadarBucketSource.bucket_start),
                sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now)
            .group_by(sa.func.date(RadarBucketSource.bucket_start)).all())
    return {day if isinstance(day, dt.date) else
            dt.date.fromisoformat(str(day)): int(total or 0)
            for day, total in rows}


def _first_watched_day():
    """The first day any bucket at all exists. Before it, nothing was
    observed for any ticker, and a zero would be a lie about all of them."""
    from models import RadarBucketSource
    first = db.session.query(
        sa.func.min(RadarBucketSource.bucket_start)).scalar()
    return first.date() if first else None


def _posts(ticker, sources, since, now):
    rows = (db.session.query(RadarPost)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium')))
            .order_by(RadarPost.created_utc.desc())
            .limit(POST_LIMIT).all())
    total = (db.session.query(sa.func.count())
             .select_from(RadarMention)
             .join(RadarPost, RadarPost.id == RadarMention.post_id)
             .filter(RadarMention.ticker == ticker,
                     RadarPost.source.in_(list(sources)),
                     RadarPost.created_utc >= since,
                     RadarPost.created_utc < now,
                     RadarMention.confidence.in_(('high', 'medium')))
             .scalar())
    return rows, int(total or 0)


def _breakdown(ticker, sources, since, now):
    rows = (db.session.query(RadarPost.source, RadarPost.author,
                             RadarPost.created_utc)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium'))).all())

    by_source = collections.defaultdict(lambda: [0, set()])
    by_author = collections.Counter()
    by_hour = collections.Counter()
    for source, author, when in rows:
        entry = by_source[source]
        entry[0] += 1
        entry[1].add(author)
        by_author[author] += 1
        by_hour[when.replace(minute=0, second=0, microsecond=0)] += 1

    total = len(rows)
    ranked = by_author.most_common(2)
    peak = by_hour.most_common(1)

    return Breakdown(
        venues=[Venue(source=s, mentions=v[0], voices=len(v[1]))
                for s, v in sorted(by_source.items(),
                                   key=lambda kv: -kv[1][0])],
        bullish=0, neutral=0, bearish=0,   # filled by the caller from Tone
        top_author_share=(ranked[0][1] / total) if total and ranked else None,
        top_two_share=(sum(c for _, c in ranked) / total)
                      if total and ranked else None,
        peak_hour=peak[0][0] if peak else None,
        peak_count=peak[0][1] if peak else 0,
        first_seen=None,                   # filled below
        repeated_text=None,
    )


def build(ticker, sources, now, window_hours=4, span='1Y'):
    """One ticker's panel. Raises UnknownTicker if it is not in the universe."""
    if span not in SPAN_DAYS:
        raise ValueError('unknown span')

    profile = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
    if profile is None:
        raise UnknownTicker(ticker)

    since = now - dt.timedelta(hours=window_hours)
    status = quotes_mod.price_status(ticker, now)
    move = quotes_mod.move_since(ticker, hours=window_hours, now=now)

    latest = None
    if status != 'unknown':
        from models import RadarQuote
        latest = (RadarQuote.query
                  .filter(RadarQuote.ticker == ticker,
                          RadarQuote.fetched_at <= now)
                  .order_by(RadarQuote.fetched_at.desc()).first())

    posts, post_total = _posts(ticker, sources, since, now)
    breakdown = _breakdown(ticker, sources, since, now)
    breakdown.first_seen = _first_mention_day(ticker)

    return Detail(
        ticker=ticker,
        name=profile.name,
        exchange=profile.exchange,
        segment=universe.segment_for(profile.market_cap, profile.ipo_date,
                                     latest.price if latest else None,
                                     now.date()),
        market_cap=profile.market_cap,
        ipo_date=profile.ipo_date,
        price=latest.price if latest else None,
        price_move=move,
        price_status=status,
        span=span,
        chart=_chart(ticker, now, SPAN_DAYS[span]),
        breakdown=breakdown,
        posts=posts,
        post_total=post_total,
    )


def _first_mention_day(ticker):
    """The first day this ticker was ever mentioned, from buckets -- which are
    retained forever, unlike posts."""
    from models import RadarBucketSource
    first = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
             .filter(RadarBucketSource.ticker == ticker).scalar())
    return first.date() if first else None
```

- [ ] **Step 4: Add the route**

In `features/radar/routes/api.py`, import `detail as detail_mod` alongside the other feature imports and append:

```python
@radar_bp.route('/api/ticker/<ticker>')
@login_required
def ticker_detail(ticker):
    """One ticker's panel. Its own endpoint so three years of closes never
    ride in the list payload."""
    args = request.args
    span = args.get('span', '1Y')
    if span not in detail_mod.SPAN_DAYS:
        return jsonify({'error': 'unknown span'}), 400
    try:
        query = parse_query(args)
    except BadQuery as exc:
        return jsonify({'error': str(exc)}), 400

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    try:
        built = detail_mod.build(ticker.upper(), query.sources, now,
                                 window_hours=query.window, span=span)
    except detail_mod.UnknownTicker:
        return jsonify({'error': 'unknown ticker'}), 404
    return jsonify(serialize_detail(built))


def serialize_detail(d):
    b = d.breakdown
    return {
        'identity': {
            'ticker': d.ticker, 'name': d.name, 'exchange': d.exchange,
            'segment': d.segment,
            'market_cap': _decimal_or_none(d.market_cap),
            'ipo_date': d.ipo_date.isoformat() if d.ipo_date else None,
            'price': _decimal_or_none(d.price),
            'price_move': _decimal_or_none(d.price_move),
            'price_status': d.price_status,
        },
        'read': [],          # Task 6 fills this; the zone exists now.
        'chart': {
            'from': d.chart.start.isoformat(),
            'span': d.span,
            'closes': [_decimal_or_none(c) for c in d.chart.closes],
            'chatter': d.chart.chatter,
            'watched_from': (d.chart.watched_from.isoformat()
                             if d.chart.watched_from else None),
        },
        'breakdown': {
            'venues': [{'source': v.source, 'mentions': v.mentions,
                        'voices': v.voices} for v in b.venues],
            'top_author_share': b.top_author_share,
            'top_two_share': b.top_two_share,
            'peak_hour': (b.peak_hour.isoformat() + 'Z'
                          if b.peak_hour else None),
            'peak_count': b.peak_count,
            'first_seen': b.first_seen.isoformat() if b.first_seen else None,
        },
        'posts': [{
            'source': p.source, 'author': p.author, 'channel': p.channel,
            'created': p.created_utc.isoformat() + 'Z',
            'title': p.title, 'body': p.body, 'url': p.url,
        } for p in d.posts],
        'post_total': d.post_total,
    }
```

Add `import datetime as dt` at the top of that file if it is not already there.

- [ ] **Step 5: Run the tests**

```bash
cd personal_apps && python -m pytest tests/test_radar_detail.py -q
```

Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/detail.py personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_detail.py
git commit -m "feat(radar): a detail endpoint for one ticker"
```

---

### Task 6: The written read

**Files:**
- Modify: `personal_apps/features/radar/phrasing.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Test: `personal_apps/tests/test_radar_phrasing.py`

**Interfaces:**
- Consumes: `detail.Detail`, `phrasing.Clause`.
- Produces: `phrasing.read_clauses(detail, mentions, expected, authors, session) -> list[Clause]`. Kinds as Task 2 plus `'plain'`. The `read` key in `serialize_detail` stops being `[]`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_phrasing.py`:

```python
class FakeChart:
    closes = [1.0, 2.0]
    watched_from = None


@dataclasses.dataclass
class FakeDetail:
    ticker: str = 'ZZZ'
    price_move: float | None = 0.182
    price_status: str = 'ok'
    chart: object = dataclasses.field(default_factory=FakeChart)


def test_the_read_states_the_finding_before_the_caveat():
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, authors=11,
        session='regular')

    assert clauses[0].kind in ('plain', 'ratio')
    assert '284' in clauses[0].text


def test_the_read_names_its_own_weak_baseline():
    """A 40x reading off two days of history is not the same claim as one off
    thirty, and the page has to say which it is making."""
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, authors=11,
        session='regular', baseline_days=2)

    assert any(c.kind == 'warn' and 'baseline' in c.text for c in clauses)


def test_the_read_does_not_paraphrase_what_people_said():
    """Cut during mockup review: the page cannot summarise content it never
    understood, and the posts are directly below it."""
    text = ' '.join(c.text for c in phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, authors=11,
        session='regular'))

    for word in ('filing', 'squeeze', 'news', 'announced'):
        assert word not in text.lower()


def test_a_closed_market_says_there_is_nothing_to_compare_against():
    clauses = phrasing.read_clauses(
        FakeDetail(price_status='closed', price_move=None), mentions=26,
        expected=3.0, authors=6, session='closed')

    joined = ' '.join(c.text for c in clauses)
    assert 'market is shut' in joined or 'market is closed' in joined
    assert 'divergence' in joined
```

- [ ] **Step 2: Run to verify failure**

```bash
cd personal_apps && python -m pytest tests/test_radar_phrasing.py -q -k read
```

Expected: FAIL — `AttributeError: module 'features.radar.phrasing' has no attribute 'read_clauses'`.

- [ ] **Step 3: Implement**

Append to `features/radar/phrasing.py`:

```python
def read_clauses(detail, mentions, expected, authors, session,
                 baseline_days=None, venues=None):
    """The panel's written read: two or three sentences of finding.

    Confined to facts the pipeline computes. It does NOT paraphrase what the
    posts say -- the page cannot summarise content it never understood, and
    the posts sit directly beneath it.
    """
    out = []

    if not expected or expected < MIN_RATIO_BASELINE:
        out.append(Clause('plain',
                          f'{mentions} mentions in the window. '
                          f'This ticker has no baseline yet, so there is '
                          f'nothing to say how unusual that is.'))
    else:
        out.append(Clause(
            'plain',
            f'{mentions} mentions in the window, about '
            f'{_ratio(mentions, expected)} this ticker\'s own normal of '
            f'{expected:.0f}.'))

    venue_count = venues if venues is not None else 0
    if authors >= NARROW_VOICES:
        out.append(Clause('plain',
                          f'{authors} distinct people, so this is not one '
                          f'account repeating itself.'))
    else:
        out.append(Clause('warn',
                          f'Only {authors} distinct voices — one account '
                          f'can produce this much on its own.'))

    if session == 'closed' or detail.price_status == 'closed':
        out.append(Clause('plain',
                          'The market is shut, so there is no price move to '
                          'compare this against — divergence needs a live '
                          'tape and returns with one.'))
    elif detail.price_status == 'stale':
        out.append(Clause('warn',
                          'The tape has not printed in this window, so the '
                          'price cannot be taken at face value.'))
    elif detail.price_move is not None:
        pct = detail.price_move * 100
        verb = ('the talk and the tape agree' if abs(pct) >= 1
                else 'the talk has moved and the price has not')
        out.append(Clause('plain',
                          f'The price moved {pct:+.1f}% over the same '
                          f'window, so {verb}.'))

    if baseline_days is not None and baseline_days < 30:
        out.append(Clause('warn',
                          f'The baseline is {baseline_days} days old, not 30, '
                          f'so this rests on very little history.'))
    return out
```

Then in `serialize_detail`, replace `'read': [],` with a real call. `serialize_detail` needs the window figures, so give it the numbers the route already has — extend `detail.Detail` with `mentions`, `expected`, `authors`, `venues` and `baseline_days` fields populated in `detail.build` from the same bucket query `_breakdown` runs, and serialize:

```python
        'read': [{'kind': c.kind, 'text': c.text}
                 for c in phrasing.read_clauses(
                     d, d.mentions, d.expected, d.authors, d.session,
                     baseline_days=d.baseline_days,
                     venues=len(d.breakdown.venues))],
```

- [ ] **Step 4: Run the tests**

```bash
cd personal_apps && python -m pytest tests/ -q -k radar
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar personal_apps/tests
git commit -m "feat(radar): the panel says what it found, in sentences"
```

---

### Task 7: Frontend types and the detail client

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/api.ts`

**Interfaces:**
- Produces: `Clause`, `Detail`, `DetailChart`, `Breakdown`, `Post`, `PanelSpan`; `fetchDetail(ticker, selection, span, signal): Promise<Detail>`; `Row.clauses: Clause[]`, `Row.chart` removed, `BoardPayload.excluded: Record<string, number>`.

- [ ] **Step 1: Write the types**

In `types.ts`, remove the `Chart` import usage from `Row`, delete `Row.chart`, and add:

```ts
/** One styled fragment of a phrase. The client styles by `kind` and never
 *  parses `text` — the wording is decided server-side in phrasing.py so there
 *  is exactly one implementation of that judgement. */
export interface Clause {
  kind: 'ratio' | 'venues' | 'people' | 'price-up' | 'price-down'
      | 'price-flat' | 'new' | 'warn' | 'plain'
  text: string
}

export type PanelSpan = '1M' | '6M' | '1Y' | '3Y'

export interface DetailChart {
  from: string
  span: PanelSpan
  /** null where the market did not trade. */
  closes: (number | null)[]
  /** null where we were not yet watching — never a zero. */
  chatter: (number | null)[]
  watched_from: string | null
}

export interface Post {
  source: string
  author: string | null
  channel: string
  created: string
  title: string | null
  body: string | null
  url: string | null
}

export interface Detail {
  identity: {
    ticker: string; name: string | null; exchange: string | null
    segment: Segment; market_cap: number | null; ipo_date: string | null
    price: number | null; price_move: number | null; price_status: string
  }
  read: Clause[]
  chart: DetailChart
  breakdown: {
    venues: { source: string; mentions: number; voices: number }[]
    top_author_share: number | null
    top_two_share: number | null
    peak_hour: string | null
    peak_count: number
    first_seen: string | null
  }
  posts: Post[]
  post_total: number
}
```

Add `clauses: Clause[]` to `Row` and `excluded: Record<string, number>` to `BoardPayload`.

- [ ] **Step 2: Add the client**

In `api.ts`, beside `fetchBoard`:

```ts
export async function fetchDetail(
  ticker: string, selection: Selection, span: PanelSpan,
  signal?: AbortSignal,
): Promise<Detail> {
  const params = new URLSearchParams()
  params.set('sources', selection.sources.join(','))
  params.set('window', String(selection.window))
  params.set('span', span)
  const response = await fetch(
    `/radar/api/ticker/${encodeURIComponent(ticker)}?${params}`, { signal })
  if (!response.ok) throw new BoardError('http')
  return response.json() as Promise<Detail>
}
```

Reuse whatever error class and timeout wrapper `fetchBoard` already uses rather than inventing a second pattern — read it first.

- [ ] **Step 3: Typecheck**

```bash
cd personal_apps && npx tsc --noEmit
```

Expected: errors only in files Tasks 8–10 rewrite (`LeadCard.tsx`, `ScanRow.tsx`, `BoardPage.tsx`) because `Row.chart` is gone. That is the intended signal.

- [ ] **Step 4: Commit**

```bash
git add personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/api.ts
git commit -m "feat(radar): types and client for the detail panel"
```

---

### Task 8: The list pane

**Files:**
- Create: `personal_apps/static/radar/src/list/TickerRow.tsx`
- Create: `personal_apps/static/radar/src/list/ListPane.tsx`
- Create: `personal_apps/static/radar/src/list/TickerRow.test.tsx`
- Delete: `personal_apps/static/radar/src/board/LeadCard.tsx`, `board/ScanRow.tsx`, `board/Marks.tsx`

**Interfaces:**
- Consumes: `Row`, `Clause`, `BoardPayload`, `chatterRuns`/`peak` from `board/geometry`.
- Produces: `<TickerRow row selected onSelect />` and `<ListPane payload selected onSelect />`.

Read `docs/superpowers/mockups/2026-08-23-radar-board-busy.html` for the agreed row arrangement before writing this.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/static/radar/src/list/TickerRow.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TickerRow } from './TickerRow'
import type { Row } from '../types'

const row = (over: Partial<Row> = {}): Row => ({
  ticker: 'HOWL', name: 'Werewolf Therapeutics', segment: 'micro',
  divergence: 4.1, mention_z: 4.1, mentions: 284, expected: 7, authors: 11,
  text_ratio: 0.9, sources: ['bluesky', 'fourchan'], price: 0.31,
  price_move: 0.182, direction: 'up', price_status: 'ok', baseline_days: 2,
  marks: [], series: [], triplet: {},
  tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '40× its normal' },
            { kind: 'venues', text: '2 venues' }],
  ...over,
})

describe('a ticker row', () => {
  it('renders the phrase the server wrote', () => {
    render(<TickerRow row={row()} selected={false} onSelect={() => {}} />)

    expect(screen.getByText(/40× its normal/)).toBeInTheDocument()
    expect(screen.getByText(/2 venues/)).toBeInTheDocument()
  })

  it('never renders a ratio against a zero baseline', () => {
    /* The live page printed "209 mentions against 0 typical". The server
       decides the wording now; this pins that the row does not reconstruct
       its own from the raw numbers. */
    render(<TickerRow selected={false} onSelect={() => {}}
      row={row({ expected: 0, mentions: 209, clauses: [
        { kind: 'new', text: 'new here' },
        { kind: 'ratio', text: '209 mentions, nothing to compare against yet' },
      ] })} />)

    expect(screen.queryByText(/0 typical/)).not.toBeInTheDocument()
    expect(screen.getByText(/nothing to compare against yet/))
      .toBeInTheDocument()
  })

  it('reports selection by ticker', async () => {
    const onSelect = vi.fn()
    render(<TickerRow row={row()} selected={false} onSelect={onSelect} />)

    screen.getByRole('link', { name: /HOWL/ }).click()

    expect(onSelect).toHaveBeenCalledWith('HOWL')
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts src/list
```

Expected: FAIL — cannot resolve `./TickerRow`.

- [ ] **Step 3: Implement `TickerRow.tsx`**

```tsx
import type { Clause, Row } from '../types'
import { chatterRuns, peak } from '../board/geometry'

const BOX = { width: 54, height: 18, pad: 0 }

/** One row of the list: identity, the phrase, and the quiet facts.
 *
 *  The phrase is the row's reason for existing and comes from the server as
 *  typed clauses. This component styles by `kind` and never reads the numbers
 *  to build wording of its own -- that judgement has one home, in phrasing.py.
 */
export function TickerRow({ row, selected, onSelect }: {
  row: Row
  selected: boolean
  onSelect: (ticker: string) => void
}) {
  const runs = chatterRuns(row.series, BOX, peak(row.series))
  return (
    <a className={`row${selected ? ' on' : ''}`}
       href={`?t=${row.ticker}`}
       aria-current={selected ? 'true' : undefined}
       onClick={(event) => { event.preventDefault(); onSelect(row.ticker) }}>
      <div className="rtop">
        <span className="tk">{row.ticker}</span>
        <span className="nm">{row.name ?? '—'}</span>
        <svg className="spark" viewBox="0 0 54 18" aria-hidden="true">
          {runs.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="var(--mark)"
                  strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
      </div>
      <div className="phr">
        {row.clauses.map((clause: Clause, index) => (
          <span key={index} className={`c-${clause.kind}`}>{clause.text}</span>
        ))}
      </div>
      <div className="meta">{row.segment}</div>
    </a>
  )
}
```

- [ ] **Step 4: Implement `ListPane.tsx`**

```tsx
import { Controls } from '../board/Controls'
import { TickerRow } from './TickerRow'
import type { BoardPayload, Selection } from '../types'

/** Why a ticker is not listed, in the order a reader would ask. */
const REASONS: [string, (n: number) => string][] = [
  ['too_few_voices', (n) => `${n} came from a single voice`],
  ['one_venue', (n) => `${n} from one venue only`],
  ['too_few_mentions', (n) => `${n} were mentioned only once or twice`],
  ['repeated_text', (n) => `${n} were the same message pasted repeatedly`],
]

/** The list, and an account of what it left out.
 *
 *  The account is not a footnote. A two-row board and a stopped ingest look
 *  identical without it, and the eligibility floor is the single biggest
 *  reason this board is short.
 */
export function ListPane({ payload, selected, onSelect, ...controls }: {
  payload: BoardPayload
  selected: string | null
  onSelect: (ticker: string) => void
  selection: Selection
  busy: boolean
  onChange: (next: Selection) => void
}) {
  const parts = REASONS
    .filter(([key]) => payload.excluded[key])
    .map(([key, phrase]) => phrase(payload.excluded[key]!))
  const total = Object.values(payload.excluded).reduce((a, b) => a + b, 0)

  return (
    <aside className="list">
      <Controls payload={payload} {...controls} />
      <div className="rows">
        {payload.rows.map((row) => (
          <TickerRow key={row.ticker} row={row} onSelect={onSelect}
                     selected={row.ticker === selected} />
        ))}
        {total > 0 && (
          <p className="below">
            <b>{total} other tickers</b> were mentioned in this window and are
            not listed: {parts.join(', ')}.
          </p>
        )}
      </div>
    </aside>
  )
}
```

- [ ] **Step 5: Delete the two-tier components**

```bash
cd personal_apps && git rm static/radar/src/board/LeadCard.tsx static/radar/src/board/ScanRow.tsx static/radar/src/board/Marks.tsx
```

- [ ] **Step 6: Run the tests**

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts src/list
```

Expected: PASS, 3 tests. `BoardPage.test.tsx` will fail until Task 10 — that is expected and gets fixed there.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/static/radar/src
git commit -m "feat(radar): one list of rows that say why"
```

---

### Task 9: Controls that hold still

**Files:**
- Modify: `personal_apps/static/radar/src/board/Controls.tsx`
- Modify: `personal_apps/static/radar/src/format.ts`
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Produces: `Controls` renders every entry in `SEGMENT_ORDER` unconditionally; the chart-span group is removed from it entirely.

- [ ] **Step 1: Write the failing test**

Append inside the `describe('the controls', …)` block in `BoardPage.test.tsx`:

```tsx
  it('renders every segment chip whatever the data says', async () => {
    /* Michi's words: "the settings are bad and switch around". They did --
       chips were filtered by `counts[key]`, so a segment with no rows
       vanished and came back as data changed, moving everything else under
       the cursor. */
    render(<BoardPage initial={payload({ segment_counts: { all: 1, micro: 1 } })} />)

    for (const label of ['Small', 'All', 'Large', 'Mid', 'Micro',
                         'Recent IPO', 'Unknown']) {
      expect(screen.getByRole('button', { name: new RegExp(`^${label}`) }))
        .toBeInTheDocument()
    }
  })

  it('does not put the chart span in the board controls', () => {
    /* The span belongs to the panel now -- it changes one ticker's chart, not
       what the list contains. */
    render(<BoardPage initial={payload()} />)

    expect(screen.queryByRole('button', { name: /^3M$/ })).toBeNull()
  })
```

- [ ] **Step 2: Run to verify failure**

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts -t "switch around|every segment chip|chart span"
```

Expected: FAIL — `Unable to find role="button" and name /^Mid/`.

- [ ] **Step 3: Implement**

In `Controls.tsx`, replace the filtered map with an unconditional one:

```tsx
          {/* Every slot, always, in one order. Chips used to be dropped at a
              count of zero, so the strip changed shape between loads and
              things moved under the cursor. A dimmed zero is information; a
              missing chip is a moving target. */}
          {SEGMENT_ORDER.map((key) => {
            const value = key === 'all' ? null : (key as SegmentFilter)
            const count = counts[key] ?? 0
            const active = selection.segment === value
            return (
              <button key={key} type="button" aria-pressed={active}
                      className={count ? undefined : 'nil'}
                      onClick={() => onChange({ ...selection, segment: value })}>
                {segmentLabel(key)}
                <span className="n">{count}</span>
              </button>
            )
          })}
```

Remove the `span`/`onSpan` props, the `SPANS` constant and the whole Chart group from this component and from its call site's prop list.

- [ ] **Step 4: Run the tests**

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts
```

Expected: the two new tests PASS. `BoardPage` tests still red until Task 10.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/static/radar/src
git commit -m "fix(radar): the segment chips hold still"
```

---

### Task 10: The detail pane, and the two-pane page

**Files:**
- Create: `personal_apps/static/radar/src/detail/DetailPane.tsx`, `Identity.tsx`, `PriceChart.tsx`, `Breakdown.tsx`, `Posts.tsx`
- Create: `personal_apps/static/radar/src/detail/PriceChart.test.tsx`
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`, `board/geometry.ts`
- Modify: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Consumes: `fetchDetail`, `Detail`, `PanelSpan`, `pricePath`, `dailyBars`.
- Produces: `<DetailPane ticker selection />`; `geometry.laneBars(chatter, box, lane)`.

Read `docs/superpowers/mockups/2026-08-23-radar-board-busy.html` for the two-lane chart and zone order.

- [ ] **Step 1: Write the failing chart test**

Create `personal_apps/static/radar/src/detail/PriceChart.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PriceChart } from './PriceChart'
import type { DetailChart } from '../types'

const chart = (over: Partial<DetailChart> = {}): DetailChart => ({
  from: '2025-08-23', span: '1Y',
  closes: Array.from({ length: 365 }, (_, i) => 1 + i / 100),
  chatter: Array.from({ length: 365 }, (_, i) => (i < 362 ? null : i)),
  watched_from: '2026-08-21',
  ...over,
})

describe('the panel chart', () => {
  it('draws a price line on every span', () => {
    /* The regression that started this rebuild: SpanChart guarded the price
       path behind `span !== '24h'` and 24h was the default, so 62,061 stored
       closes never rendered once. */
    for (const span of ['1M', '6M', '1Y', '3Y'] as const) {
      const { container, unmount } = render(
        <PriceChart chart={chart({ span })} />)
      expect(container.querySelector('path.px')?.getAttribute('d'))
        .toBeTruthy()
      unmount()
    }
  })

  it('draws no chatter bar where nothing was observed', () => {
    /* null is "not watched", not "zero mentions". A bar of height zero and no
       bar at all look the same; a bar drawn from a null does not. */
    const { container } = render(<PriceChart chart={chart()} />)

    expect(container.querySelectorAll('rect.chat').length).toBe(3)
  })

  it('marks where watching began', () => {
    const { container } = render(<PriceChart chart={chart()} />)

    expect(container.querySelector('.watch-edge')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts src/detail
```

Expected: FAIL — cannot resolve `./PriceChart`.

- [ ] **Step 3: Implement `PriceChart.tsx`**

```tsx
import { pricePath } from '../board/geometry'
import type { DetailChart } from '../types'

const W = 860
const H = 300
const PRICE_H = 196
const GAP = 14
const CHAT_H = H - PRICE_H - GAP - 26

/** Price and chatter on one shared x-axis, in two lanes.
 *
 *  Two lanes rather than an overlay because the two series do not share a
 *  history: price goes back three years and chatter began on 2026-08-21 and
 *  grows a day per day. Overlaid, three days out of a thousand is invisible;
 *  in its own lane it stays legible at every span.
 *
 *  Nothing is drawn where chatter is null. That region is not silence, it is
 *  a period nobody was watching, and a zero-height bar would assert the
 *  former.
 */
export function PriceChart({ chart }: { chart: DetailChart }) {
  const path = pricePath(chart.closes, { width: W, height: PRICE_H, pad: 0 })
  const rising = firstAndLast(chart.closes)
  const slot = W / Math.max(chart.chatter.length, 1)
  const peak = chart.chatter.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0) || 1
  const watchIndex = chart.chatter.findIndex((v) => v !== null)

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`price over ${chart.span} with chatter beneath`}>
      <line x1="0" y1={PRICE_H} x2={W} y2={PRICE_H}
            stroke="var(--rule-soft)" strokeWidth="1" />
      {path && (
        <path className="px" d={path} fill="none" strokeWidth="1.6"
              strokeLinejoin="round" vectorEffect="non-scaling-stroke"
              stroke={rising ? 'var(--up)' : 'var(--down)'} />
      )}
      {watchIndex > 0 && (
        <line className="watch-edge" x1={watchIndex * slot}
              y1={PRICE_H + GAP} x2={watchIndex * slot}
              y2={PRICE_H + GAP + CHAT_H} stroke="var(--mark)"
              strokeWidth="1" strokeDasharray="3 3" />
      )}
      {chart.chatter.map((value, index) => {
        if (value === null) return null
        const h = Math.max(2, (value / peak) * CHAT_H)
        return (
          <rect className="chat" key={index} x={index * slot}
                y={PRICE_H + GAP + CHAT_H - h}
                width={Math.max(slot - 0.5, 2)} height={h}
                fill="var(--mark)" />
        )
      })}
    </svg>
  )
}

/** Direction over the whole visible span, for the line's colour. Green and
 *  red mean price direction and nothing else on this surface. */
function firstAndLast(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  return real.length < 2 || real[real.length - 1]! >= real[0]!
}
```

- [ ] **Step 4: Implement the remaining panel zones**

`Identity.tsx`, `Breakdown.tsx` and `Posts.tsx` render the payload fields directly — follow the zone order and content of the busy mockup. `DetailPane.tsx` owns the span state and the fetch:

```tsx
import { useEffect, useState } from 'react'
import { fetchDetail } from '../api'
import { Identity } from './Identity'
import { PriceChart } from './PriceChart'
import { Breakdown } from './Breakdown'
import { Posts } from './Posts'
import type { Detail, PanelSpan, Selection } from '../types'

const SPANS: PanelSpan[] = ['1M', '6M', '1Y', '3Y']

export function DetailPane({ ticker, selection }: {
  ticker: string | null
  selection: Selection
}) {
  const [span, setSpan] = useState<PanelSpan>('1Y')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!ticker) { setDetail(null); return }
    const controller = new AbortController()
    setFailed(false)
    fetchDetail(ticker, selection, span, controller.signal)
      .then(setDetail)
      .catch((error) => { if (error.name !== 'AbortError') setFailed(true) })
    return () => controller.abort()
  }, [ticker, span, selection])

  if (!ticker) return <main className="detail" />
  if (failed) {
    return <main className="detail"><p role="status">
      Could not load {ticker}.</p></main>
  }
  if (!detail) {
    return <main className="detail" aria-busy="true">
      <p role="status">Loading {ticker}…</p></main>
  }

  return (
    <main className="detail">
      <Identity identity={detail.identity} />
      <p className="read">
        {detail.read.map((clause, index) => (
          <span key={index} className={`c-${clause.kind}`}>{clause.text} </span>
        ))}
      </p>
      <h3>Price and chatter
        <span className="spans">
          {SPANS.map((option) => (
            <button key={option} type="button"
                    aria-pressed={option === span}
                    onClick={() => setSpan(option)}>{option}</button>
          ))}
        </span>
      </h3>
      <PriceChart chart={detail.chart} />
      <Breakdown breakdown={detail.breakdown} />
      <Posts posts={detail.posts} total={detail.post_total} />
    </main>
  )
}
```

- [ ] **Step 5: Rewrite `BoardPage.tsx` as two panes**

Keep the existing fetch/abort/URL machinery. Add selection state seeded from `?t=`, defaulting to the first row, written back with `history.replaceState`, and render `<ListPane>` beside `<DetailPane>`. Remove the `span`/`onSpan` state — the panel owns it now.

- [ ] **Step 6: Run everything**

```bash
cd personal_apps && npx tsc --noEmit
```

```bash
cd personal_apps && npx vitest run -c vite.radar.config.ts
```

Expected: both clean. Fix the `BoardPage.test.tsx` cases that assert the old two-tier markup — they should assert the list/panel arrangement instead.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/static/radar/src
git commit -m "feat(radar): the detail panel, and the two-pane board"
```

---

### Task 11: Verify against live data, then hand to impeccable

- [ ] **Step 1: Full suites**

```bash
cd personal_apps && python -m pytest tests -q
```

Expected: PASS except the four known gym dev-DB failures (`test_gym_exercise_ownership`, `test_gym_ownership`, two in `test_gym_routes_smoke`).

```bash
cd personal_apps && npm test
```

- [ ] **Step 2: Build**

```bash
cd personal_apps && npm run build
```

- [ ] **Step 3: Look at it, on seeded data**

```bash
cd personal_apps && PYTHONPATH=. python scratchpad/seed_radar_dev.py
```

Then start an instance and screenshot both panes at 1341×950 with python-playwright, minting a session cookie with `{'user_id': <first AppUser id>}` — do not use the Browser MCP for screenshots. Compare against the two approved mockups. Check specifically: the price line draws at every span, the segment chips do not move between a busy and an empty board, and the row phrases match what `phrasing.py` produces.

- [ ] **Step 4: Commit any fixes, then stop**

Styling is deliberately unfinished at this point. Report completion and hand the visual system to `impeccable` — that is a separate invocation with `IMPECCABLE_CONTEXT_DIR=personal_apps/features/radar`.

---

## Self-Review

**Spec coverage.** Layout → Task 10. Row phrase → Tasks 2, 8. Panel's five zones → Tasks 5, 6, 10. Controls with fixed slots → Task 9. Quiet state and the excluded account → Tasks 3, 4, 8. Three-year price store → Task 1. Detail endpoint → Task 5. Board payload loses `chart` → Task 4. The 24h price-path regression → Task 10 Step 1. Mobile fallback → single-column CSS, folded into `impeccable`, and noted as out of scope here.

**Known gap, deliberate:** `detail.Detail` needs `mentions`, `expected`, `authors`, `session` and `baseline_days` for the read. Task 5 does not populate them and Task 6 adds them — Task 6's implementer must extend the dataclass and `build()`, which its step text says.

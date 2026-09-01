# Radar board — layout round (ledger rows, tiers, collapsed controls, mobile)

**Status:** draft for sign-off 2026-09-01
**Source:** `.impeccable/critique/2026-09-01T18-45-03Z__personal-apps-static-radar.md`
(dual-agent critique, 31/40). This round takes the two P1s, the two structural
P2s and the three redesign levers Michi picked from the critique's questions.
Formats, keyboard shortcuts, post-card bugs and the loading dim-limbo are the
polish round that follows; they are out of scope here except where named.
**Builds on:** `2026-08-23-radar-board-rebuild-design.md` (two panes, one
route, `?t=` selection, typed clauses, fixed control slots). Everything not
mentioned here is unchanged.

## What the critique measured

- Desktop 1440×900: 11 rows × ~100px in a 420px column; ~7 visible, the rest
  behind a scroll while ~1000px of detail pane sits beside them. PRODUCT.md
  calls 10–15 rows the majority state; the board did not fit its own majority
  state.
- Mobile 390×844: a row tap changed nothing on screen for 1–2s. The panel sat
  under the whole list *and* the excluded account *and* the marks legend
  (~1900px down), and focus only moved there after the fetch resolved.
- One ranked column carried `DIV +0.10`, `Z 4.9`, `DIV not scored` as
  neighbours. Loud-and-unmoved and quiet-but-loud rows read as one ordering.
  (The server already sorts divergence-scored rows first — `leaderboard.py`
  sorts on `(divergence is not None, divergence, mention_z)` — so the order is
  right and the *presentation* hides the boundary.)
- Segment strip: `All` and `Discover` are aggregates rendered as peers of the
  five raw segments; pressing Discover lights four tabs; `Unknown 0` can render
  pressed-and-dimmed.
- Seventeen underlined text tabs in three rows on a tool whose sources "are a
  question the reader asks, not a setting they maintain".
- The board opens on DE by the 2026-08-30 decision, even while the US session
  is the live one. Michi reversed that decision on 2026-09-01: open on the
  market whose session is live.

## Decisions (arrangement B, picked from three grayscale wireframes)

### 1. The list becomes a ledger

One line per row, a column header above, ~46px per row. At 1440×900 twelve rows
fit without scrolling.

```
TICKER        24H TALK · PRICE     SCORE   RATIO · PRICE · MOVE / BREADTH      LEAN
GPRO          [chart]              +0.10   1.4× · 1,25 $ · −4.6%              ↑4 ↓10
GoPro, Inc.                                3 venues · 51 people
                                                                   warming-up · partial
```

Columns, left to right:

| Column | Content | Source |
|---|---|---|
| identity | ticker over company name (name truncates) | `ticker`, `name` |
| chart | the 24h chart-row exactly as today: chatter area, dashed own-normal, price line when `price_status === 'ok'`, price line coloured by `direction` | `series`, `normal_per_hour`, `price_series` |
| score | the number the tier is ordered by, no term prefix (the tier caption and the column header carry the term) | `divergence` in tier 1, `mention_z` in tier 2 |
| facts | line 1: ratio · price · move (move only in tier 1); line 2: breadth (`venues` · `people` clauses) or the `warn` clause | `ratio`, `quote`, `price_move`, `clauses` |
| lean | the ↑n ↓n chip, unchanged | `tone` |
| flags | full-width trailing line, only when present: deviant quote facts then marks, as today | `quote`, `marks` |

**Every dimension the current row encodes survives**: chatter magnitude
(area), own-normal (dashed line), price path and direction (line + colour),
score, ratio, price, move, breadth or warning, lean, marks, deviant quote facts,
selected state. Nothing is dropped. What goes: the `DIV`/`Z` prefix inside the
cell (10.5px, flagged by both the critique and the detector), replaced by the
tier caption.

**Widths.** The list is 560px at ≥1280px viewport, 460px between 900 and
1279px (chart column narrows, names truncate sooner). Below 900px the page
stacks (see §5). The detail pane takes the remainder; on 1440 that is 880px,
down from 1020. The chart in the panel already pans below its comfortable
width; nothing else in the panel depends on the extra 140px.

**Column header.** One line above the rows, inside the list's non-scrolling
head, so it stays put while the rows scroll. Its labels are plain column names,
not the tier terms — the terms belong to the captions.

### 2. Two tiers, one list

The rows the server ranks by divergence sit above a rule with a caption; the
rows it ranks by chatter sit under a second caption. Tier membership is
`quote.score_eligible && quote.score_term === 'divergence' && divergence !==
null` — the server's safety verdict first, then the value, the same predicate
the score cell prints by (`TickerRow.scoredAgainstPrice`). On real payloads
this is exactly `divergence !== null`; the stricter form keeps a cached
mixed-version row from reviving divergence the server refused. It matches the
server's sort, so the tiers are a presentation of the existing order and never
reorder it.

| Tier | Caption | Rows |
|---|---|---|
| 1 | **Scored against price** · chatter vs the *N*h price move · DIV | `divergence !== null` |
| 2 | **Chatter only** · unusual talk, no usable price move to compare · Z | everything else |

- A row whose `score_term` is `divergence` but whose `divergence` is null
  ("not scored" today: flat tape, frozen tape, no quote) belongs to tier 2 and
  shows its `mention_z` like its neighbours. *Why* it was not scored is already
  on the row — the `warn` clause ("tape has not printed"), `no quote`, or the
  price-flat clause — and stays there.
- **Open market, tier 1 empty** (the state captured at 21:35 on 2026-09-01:
  every row `warming-up`, nothing eligible): the tier-1 caption still renders,
  with its count of 0 and the board-wide reason after it when one exists
  (`baselines starting over`). An absent caption would read as "there is no
  such thing"; a 0 says "not yet".
- **Closed market**: every row is tier 2. No captions at all — the status
  line's `RANKED BY CHATTER` token already says which ranking is in force, and
  a single caption over a single tier is a heading with nothing to distinguish
  from.
- The captions are not controls. They do not collapse or filter.

### 3. Controls: a views row and a summary line

The two strips of eight and nine tabs become:

**Views row** — five fixed slots, counts beside each, the current lit/dim
pattern: `All · Discover · Large · IPO · Funds`. These are the things a reader
actually switches between. `Discover` is the default. `IPO` stays a top-level
view: a fresh listing is not obscure, which is exactly why it is not inside
Discover (`types.ts`), and it needs a slot of its own.

**Members line** — appears under the views row only while `Discover` or one of
its members is active: `within Discover: Mid 5 · Micro 3 · Unknown 1`. Each
member is a tab; pressing one narrows the board to that segment alone (the
selection becomes `[mid]`, Discover reads as covered rather than pressed);
pressing Discover restores the union. This is the one place the strip changes
shape, and it changes on a click the reader made, never between loads.

Union semantics are unchanged underneath (`selection.segments` is still a
list; the server still accepts any combination). Only the surface stops
presenting an aggregate and its members as equals.

**Summary line** — window, sources and venues collapse to one sentence with a
disclosure: `4h · 3 sources · any venue · change`. When the selection deviates
from the defaults the line says so in place of the default word: `12h ·
Bluesky, Reddit · 2+ venues`. Sources are listed by name whenever one is off,
so a narrowed board never looks like the whole one. `change` expands the
existing second strip (window | sources | venues, unchanged behaviour, fixed
slots, last-source lock) directly under the line; it stays open until the
reader collapses it. Expanded state is component state, default collapsed, and
is not persisted — a reader who changes a filter every visit can leave it open
for the visit.

Rows bought back at 1440×900: the views row is one line where the segment strip
was two, and the summary line is one where the second strip was one. Net ~30px
plus the row-height change. The measured target — 10–12 rows visible unscrolled
— is met by the ledger row alone; the control change is for the second-order
critique finding (seventeen same-looking underlined words), not for height.

### 4. Default market: the live session

`parse_query` currently defaults `market` to `de` (Michi, 2026-08-30). New
rule, Michi 2026-09-01:

- `us` when the US session is `regular` **and** the DE session is not;
- `de` otherwise — including when both are regular (15:30–17:30 CEST overlap:
  home market wins) and when neither is (nothing is live; DE is the venue the
  reader trades).

Sessions come from `market_calendars.session_state(market, now)`. The rule
lives beside the default it replaces, in `routes/api.py`, and
`test_market_defaults_to_de_and_unknown_market_is_rejected` becomes a
parametrised test over the four session combinations with a frozen clock. An
explicit `?market=` is honoured exactly as today.

### 5. Below 900px

Document order becomes: list head + controls + rows → **panel** → the account
(excluded, marks legend, spend). Today the account sits inside the rows
scroller, above the panel, which is what put the panel 1900px down.

- The account block is rendered once, by the page, in the slot that matches
  the width (a media-query hook, not two copies). On desktop it renders where
  it does today, at the bottom of the rows column.
- **Tapping a row scrolls the panel into view immediately**, at selection
  time, before the detail request goes out. The panel shows a loading skeleton
  shaped like its zones (identity block, chart box, two text lines) instead of
  the one-line `Loading X…`. Focus handoff on load stays as it is.
- Rows keep the ledger structure, narrowed: identity | chart | score on one
  line, facts under, lean beside the score. The column header hides below
  900px (there is no column to head at that width; the tier captions and the
  status line carry the terms).
- The `Back to board` link at the top of the panel stays.

Michi's answer to "does this content need a different arrangement on mobile?":
the panel moves and the tap answers immediately; the rows do not become cards.

### 6. Loading skeleton (both widths)

The panel's `Loading X…` line becomes a skeleton in the panel's own layout:
identity block, the read's two lines, the chart's box, the breakdown table's
header. It is the same component desktop and mobile. The dimmed
stale-while-revalidate state for same-ticker span/source changes is unchanged.

## Not in this round

- Percent and age format unification, the `title`-on-disabled-button lock
  explanation, post-card duplicates and double-encoding, date locale, Escape
  and arrow-key navigation, a debounce on control refetches, the `1h` /
  `2+ 48` labels. All from the critique; all to the polish round.
- The marks legend's placement. It moves to the end of the account block on
  mobile (§5) and otherwise stays where it is. Whether it deserves an inline
  affordance near the column header is an open question for polish.
- Anything in the detail pane other than the skeleton.

## Verification

- Playwright screenshots at 1440×900, 1200×800, 768×1024, 390×844, from the
  dev server with the prod-copy database (11 rows today).
- At 1440×900: the last row's bottom sits inside the rows scroller's
  viewport. (Not `scrollHeight ≤ clientHeight`: the excluded account and the
  marks legend scroll with the rows on a desk, by design, and count toward
  scrollHeight.) Measured 2026-09-01 22:02: 7 rows at 62px each — every row
  carried a flags line because one row lacked the otherwise-universal mark —
  all visible with the account under them.
- At 390×844: after a row tap, the panel's top is within the viewport before
  the detail response arrives (throttle the request in the test).
- Tier split: a payload with two divergence-scored rows and three chatter rows
  renders two captions with counts 2 and 3, in server order; a closed-session
  payload renders no captions; an open-session payload with no scored row
  renders the tier-1 caption with 0.
- Members line: absent under `All`/`Large`/`IPO`/`Funds`, present under
  `Discover` and under `mid` alone; pressing `Mid` sends `segments=mid`.
- Summary line: default sentence with defaults; names listed when a source is
  off; `2+ venues` when venues is 2.
- Default market: four session combinations, frozen clock.
- Existing tests (`TickerRow`, `BoardPage`, `marks`, `hardening`, `Spend`,
  `QuoteBadges`, `PriceChart`, `test_radar_api.py`) updated where they assert
  the old prefix, the old strip, or the DE default; nothing else.

## Open questions for impeccable

- The tier captions: how a rule-with-caption reads as a boundary and not as a
  section heading in a sectioned page.
- The column header's weight against the status line directly above it.
- The members line: how "covered" (Discover active) differs from "pressed"
  (Mid alone) without a third tab state that has to be learned.
- The summary line's disclosure — a word, a chevron, or the line itself.
- The skeleton's texture.

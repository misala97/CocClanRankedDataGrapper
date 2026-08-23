# Radar board rebuild — list and detail

**Status:** approved 2026-08-23
**Supersedes the surface** described in `2026-08-20-radar-social-sentiment-design.md` §9.
Ingest, scoring, eligibility and the price store are unchanged.

## Why

The board shipped on 2026-08-22 and was rebuilt against live data three times
since. Michi's verdict on 2026-08-23, looking at the real page:

> it looks completely chaotic. the settings are bad and switch around. i have
> no real idea why and what is worth looking at. i have no deeper info about a
> particular stock besides what i see on the front page.

Four complaints. Three of them share one cause and the fourth is the reason
the other three could not be fixed in place.

**There is no detail surface.** Every fact the tool knows has to fit a 300px
card. That is why company names truncate to `Subversive Congressional …`, why
the chart is 92px tall with no axis, why each card is a prose sentence rather
than aligned data, and why twenty controls try to make one list answer every
question. The board is overloaded because it has nowhere to hand anything off
to.

Two concrete defects were root-caused during the review and are fixed by this
rebuild rather than patched into the old page:

- **The price line never draws on the default span.** `SpanChart.tsx` sets
  `sliced = chart && !hourly ? … : null` and then `path = sliced ? … : ''`, so
  at `span === '24h'` — the default — `path` is always empty. 62,061 daily
  closes across 247 tickers, and the view you land on cannot render one of
  them. This is the whole of "the price thing is still not working".
- **The controls change shape between loads.** Segment chips are filtered by
  `counts[key]`, so a segment with no rows vanishes and returns as data
  changes. That is "the settings switch around", literally.

## Shape

Two panes on one route. Desktop is the primary target.

```
┌─ list ~400px ──────┬─ detail, remaining width ─────────────┐
│ controls           │ identity                              │
│ ───────────        │ the read                              │
│ row (selected)     │ chart: price + chatter, 1M/6M/1Y/3Y    │
│ row                │ chatter breakdown                     │
│ row                │ posts                                 │
└────────────────────┴───────────────────────────────────────┘
```

The **top row is selected on arrival**, so the page is useful with no clicks.
Selection is a URL parameter, `?t=HOWL`: back clears it, a ticker can be
bookmarked, and "what happened to the one I spotted yesterday" is answerable.

Below 900px the detail becomes a full-width view with a back control and the
list is the root. Secondary target — not equal, not broken.

### Rejected alternatives

- **Separate ticker page.** Cleaner separation and the same design at every
  width, but the panel keeps the list visible while reading, which is what
  Michi wanted, and desktop-first removes most of the page's advantage.
- **Rows that expand in place.** The detail is a multi-year chart plus posts
  plus a breakdown; expanding one row pushes the rest off screen, so the list
  is lost exactly when comparison matters. Not linkable either.

The panel can later gain a hover preview; a panel-first design cannot easily
be un-crammed. This is the least costly direction to be wrong about.

## The list row

Three lines. The middle line is the finding, in words.

```
HOWL   Werewolf Therapeutics                          ▁▂▁▅█
40× its normal · 3 venues · 11 people · price flat
micro · $0.31 · provisional
```

The phrase is generated from what is actually known, and its shape changes
with that. This is the part the current page gets wrong:

| State | Phrase |
|---|---|
| Measurable | `40× its normal · 3 venues · 11 people` |
| No baseline yet | `new here — 209 mentions, nothing to compare against yet` |
| Narrow | `40× its normal but one channel, 2 voices` |
| Below breadth | `40× its normal · one venue only` |

**`against 0 typical` must not survive this rebuild.** An expected of zero
does not mean "we expected none"; it means there is no baseline. Printing it
as a quantity is the absence-rendered-as-zero mistake the project exists to
avoid, and it is currently on the live page.

Market state is stated **once by the page**, not per row. A mark carried by
every row is not a mark — the same rule that was applied to `provisional` on
2026-08-22.

### Where the words are generated

Both the row phrase and the panel's read are **built server-side**, in their
own module, and shipped as a list of typed clauses rather than a finished
string:

```python
[Clause('ratio', '40× its normal'), Clause('venues', '3 venues'), …]
```

Server-side because deciding which phrase a row deserves is judgement about
data, and it belongs where the data is and where pytest can reach it. Typed
clauses rather than a rendered sentence because the client still has to style
the parts differently, and a client that re-derives the wording from raw
numbers would be a second implementation of the same judgement.

## The detail panel

Five zones.

**1. Identity.** Ticker, full company name untruncated, exchange, segment,
market cap, current price with move and status.

**2. The read.** Two or three generated sentences: how unusual this is against
its own history, how many independent voices across how many venues, what is
suspect about it. Observations only. PRODUCT.md's scope boundary forbids
anything that reads as a call, and that boundary holds here.

**3. The chart.** Price and chatter on one set of axes. Spans **1M / 6M / 1Y /
3Y**. A rule marks the date watching began, so the years before it read as
*not observed* rather than as silence — price history goes back years, chatter
starts 2026-08-21 and grows one day per day.

**4. Chatter breakdown.** Per source: mentions, voices, share. Tone counts.
First time this ticker was ever seen. Peak hour. And **concentration** — the
share of mentions from the loudest one or two accounts. That is the pump tell,
and no other figure on the surface exposes it.

**5. Posts.** Newest first: full text, author, source, timestamp, and a link
to the original. Retention is 30 days and `radar_posts.url` is already stored,
so this needs no new ingest.

## Controls

The chart-span row leaves the board — it belongs to the panel. Four chips gone.

Everything remaining gets **fixed slots**: a segment with no rows renders
dimmed showing `0`. It never disappears and never reorders. This reuses the
lit/dim pattern `Venues.tsx` already implements rather than inventing a second
one.

## Quiet state

Three rows is the normal state of this board, not a failure, and it must look
deliberate. The page states the situation as a finding — *market closed · 3
tickers above their normal in the last 4h* — and when nothing clears the bar,
says so plainly rather than rendering an empty frame.

**The list accounts for what is missing.** Below the rows:

> **14 other tickers** were mentioned in this window and are not listed: 9
> came from a single voice, 4 from one venue only, and 1 has no baseline old
> enough to measure against.

A two-row board and a broken board are otherwise indistinguishable. This is
also the eligibility floor made honest — today those tickers vanish with no
trace, and the reader cannot tell a quiet market from a dead ingest. It is
followed by a pointer at the two controls that widen the net.

## Approved mockups

Built and approved 2026-08-23, before any application code:

- `docs/superpowers/mockups/2026-08-23-radar-board-busy.html` — market open,
  seven rows, HOWL selected.
- `docs/superpowers/mockups/2026-08-23-radar-board-quiet.html` — market
  closed, two rows, SBFM selected. The majority case.

Static HTML, no scripts, chart geometry computed from generated series rather
than drawn, so what was approved is the shape the real component produces.

Decisions the mockups settled that the prose above did not:

- **Two lanes, not an overlay.** Price occupies the upper ~65% of the chart
  and chatter its own lane beneath, sharing one x-axis. Overlaying three days
  of chatter onto 365 days of price makes the chatter invisible; the lane
  keeps it legible at every span, and the "not yet observed" region is a
  dashed baseline with a small label rather than a filled slab, so it notes
  the absence without shouting it.
- **The read does not paraphrase post content.** An earlier draft said "the
  talk is about a shelf registration". Cut — the page cannot reliably
  summarise what it has not understood, and the posts are directly below.
  The read confines itself to facts the pipeline actually computes.
- **No tone bar.** Bull/bear/neutral are counts in words. A green/red tone bar
  was drafted, caught, and removed: green and red are price direction and
  nothing else, and this exact bar was already built and deleted once in
  August for the same reason.
- Mobile gets a plain single-column fallback and no design attention. Michi's
  call, 2026-08-23: desktop is where this is used, and doing mobile properly
  is its own session.

## Data work this requires

**Deepen the price store.** `HISTORY_DAYS = 260` stores about one year; 3Y
needs ~780. One full backfill of 247 tickers takes roughly an hour against
Twelve Data's eight-per-minute limit. Storage is ~190k rows, which is nothing.

**A detail endpoint.** Three years is ~780 closes per ticker. Embedding that
per row would make a twenty-row board ship sixteen thousand numbers to draw
three. The list payload stays small and the panel fetches one ticker.

The board payload therefore **loses** its per-row `chart.closes`; the row
sparkline needs only the chatter series it already carries.

## Out of scope

- The visual system — palette, type, spacing, the chart's own rendering. That
  goes through `impeccable` after the structure is built, per standing
  preference. This document fixes *what is on screen and why*, not how it
  looks.
- Source expansion. Separate work, deliberately after this.
- Source health on the surface (a venue that did not answer). Agreed as
  needed, folded into the source-expansion work where each new venue needs the
  same signal.

## Verification

- Real HTML mockups before any application code: the list, the panel, and the
  quiet state. One screen per turn. Two systems have been rejected after
  shipping for want of this.
- The `24h` price-path bug gets a regression test that fails when the span
  guard returns.
- Segment chips are asserted to render at a fixed count regardless of data.
- Distinctiveness-style checks against live data, not only fixtures — see
  `project_radar_thematic_fund_tokens`.

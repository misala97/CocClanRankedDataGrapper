# Radar — one chart, four spans

## The problem

Divergence answers one question: did the price move while people were talking?
It measures hours. That is the right question about a stock you already know.

It is the wrong question the first time you see a ticker. A stock can be flat
over four hours and down 80% on the year, or flat over four hours having
already tripled since June, and those are opposite situations behind an
identical score. Michi's framing: *"a stock explodes on social media, 50000
mentions in 2 hours — I want to be able to tell the state of the stock of the
last month or year."*

## The shape of the answer

**The board already draws chatter against price. It just only does it for 24
hours.** The first draft of this spec added a second, separate price-only
strip for the long view. That was wrong, and michi caught it: there is no
third series involved, only the same two over a longer span. Holding the 24h
chart fixed and building beside it produced two charts and two time controls
where one of each would do.

So: **one chart, with a span control — `24h · 1M · 3M · 1Y`.** Chatter in
violet, price in green or red, always on one axis. At 24h it is exactly what
ships today. At 1Y it degrades to very nearly the price-only strip the first
draft proposed, because there is not yet a year of chatter — which means
merging costs nothing at the long end and gains a control and a chart at the
short one.

It also improves on its own. `retention.prune_posts` deletes posts;
**`radar_buckets` is retained forever**, so chatter history accumulates from
2026-08-21 and the long spans fill in without further work.

## Scope boundary

**This does not touch divergence, the eligibility floor, or the ranking.**
Nothing here becomes an input to a score. The board ranks exactly as it does
today.

Restating the boundary it inherits (PRODUCT.md): the surface describes what was
observed. It must not acquire a verdict — no "oversold", no "near support", no
colour that reads as a recommendation.

## What the data actually is

Measured against the live free tier on 2026-08-22, not assumed:

- Twelve Data `/time_series` with `interval=1day` returns **exactly the
  `outputsize` requested**, no truncation. `outputsize=260` returned 260 rows
  spanning 2025-08-11 → 2026-08-21; `outputsize=400` returned 400.
- Free tier is ~800 API credits/day, **8 requests/minute**. The per-minute
  ceiling is the binding constraint, not the daily quota.
- Finnhub `/stock/candle` is 403 on free (measured earlier — it is why Twelve
  Data is in this codebase at all).
- `radar_bucket_sources` currently spans 2026-08-21 09:15 → now. That is all
  the chatter history that exists.

## The alignment problem the merge creates

Price has ~252 **trading** days a year. Chatter has 365 **calendar** days, and
weekend chatter is not noise to be dropped — it is the case michi asked for
("if a lot of people talk on the weekend I can prepare for Monday").

Positioning both by array index would drift them apart by over a hundred days
across a year. So **both series are indexed by calendar day** from one shared
start date:

```json
"chart": {
  "from": "2025-08-23",
  "closes":  [null, 12.1, 12.3, null, null, 12.4, ...],
  "chatter": [null, null, null, ...,  4,   12,   31]
}
```

- `closes[i]` is `null` on weekends and holidays — no trade happened. The price
  line is drawn **across** those gaps, as every stock chart does, because the
  price did not stop existing.
- `chatter[i]` is `null` before ingest began. Those bars are **not** drawn, and
  the emptiness is the point: it says we have only been watching two days.

Two different meanings for `null` in two arrays, which is exactly the
distinction the codebase already draws everywhere else — an absence is never a
zero.

**Size:** 365 entries × 2 arrays × ~46 rows is roughly 250KB of JSON, most of
it the literal `null`. nginx gzip is on (7.8× measured on `/ranked`), so this
lands around 30KB on the wire. Sending it whole and letting the client slice is
simpler than four server-side resolutions, and the client already holds the
year for the span switch to be instant.

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Chart | **One chart, chatter + price, span-switched** | A separate price strip (two charts and two time controls for one idea — michi rejected this) |
| Spans | **24h · 1M · 3M · 1Y**, default 24h | Fixed 1Y (loses the operational "is it spiking now" view); tying the span to the score window (scoring divergence over a year is meaningless) |
| Axis | **Calendar days**, both series | Trading-day index (drops weekend chatter, the case this was asked for); separate axes (defeats the point of one chart) |
| Where | **Every row**, always visible | Leads only (the unfamiliar ticker is rarely in the top three); tap to expand (click-gating per-row data has been rejected before) |
| Room for it | **Merge Mentions + Authors** into `22 / 8` | Dropping the company name (unfamiliar tickers are exactly the case this serves); widening the page |
| Controls | Two, relabelled **Score** and **Chart** | One control (see Spans); leaving `Window` unlabelled beside a second time control |

## Storage

New table `radar_daily_closes`:

| column | type | notes |
|---|---|---|
| `ticker` | VARCHAR(12) utf8mb4_bin | part of PK |
| `close_date` | DATE | part of PK |
| `close` | NUMERIC(18,4) | the daily close |
| `fetched_at` | DATETIME(6) | when written |

Primary key `(ticker, close_date)`. Not partitioned: a year of closes for a few
thousand tickers is small, and rows are replaced by date rather than
accumulated per source.

**`quotes.refresh_sigma` reads this table instead of calling the provider.**
Today it fetches 35 closes per ticker every 12 hours and discards them. On an
eight-request-a-minute budget that duplicate fetch competes directly with the
tickers that have no history at all.

Daily chatter comes from `radar_bucket_sources`, which is already stored — it
is a `GROUP BY DATE(bucket_start)` over data the board reads anyway, not a new
source.

## The job

`radar_history`, every 5 minutes, in `run_radar_ingest.py`:

1. Take the board's tickers (`_loud_tickers`).
2. Prefer those with **no** stored history, loudest first. A ticker the board
   cannot draw at all is worth more than a fresher copy of one it can.
3. Then refresh any whose newest `close_date` is more than **2 calendar days**
   old. Two, not one: over a weekend the provider has nothing newer than
   Friday, and a one-day rule would spend every cycle re-fetching rows that
   cannot change.
4. Cap at **20 symbols per cycle** — 4/minute against an 8/minute ceiling.

Failure is contained per symbol. A provider returning nothing leaves stored
rows untouched.

## Surface

- **One chart per lead card**, unchanged in position, now span-switched.
- **One sparkline per scan row**, now carrying both series: violet chatter,
  green/red price. At 124×26 that is two thin lines, and watching them
  separate is the product's whole idea at a glance.
- **Mentions and Authors merge** into one column reading `22 / 8` under a
  `Mentions / people` heading. The track count stays at seven: the chart column
  is not new, and the merge pays for nothing else being lost.
- **Two control groups, relabelled.** `Score: 1h · 4h · 24h` sets what is
  scored and ranked. `Chart: 24h · 1M · 3M · 1Y` sets what is drawn. The
  current single `Window` label becomes `Score`.
- **Chatter scale is zero-anchored; price is not.** A stock's floor is not
  zero and the question is shape; chatter's floor is zero and the question is
  magnitude. This is already true of the two sparkline helpers and does not
  change.
- **Price colour** follows its direction across the selected span, so a stock
  down on the year and up this month is green at 1M. Correctly.
- **No data** in either series draws the existing dashed "not measured" rule.

Mobile keeps the chart and drops the merged counts to the caption row,
following the existing `.meta` pattern.

## Testing

- Calendar alignment: a weekend gap in closes lines up with chatter bars on the
  same dates; the price line is drawn across the gap, chatter is not.
- Slicing: 24h/1M/3M/1Y take the right tail; a series shorter than the span
  comes back whole rather than padded.
- Nulls: leading chatter nulls (before ingest) draw nothing; interior close
  nulls do not break the price path into segments.
- Job: prefers tickers with no history; respects the per-cycle cap; a failing
  provider leaves stored rows intact; **the job is registered in `main()`** —
  the profile job shipped unscheduled, and an absence needs its own assertion.
- Sigma: reads the table, and still returns None below `MIN_CLOSES_FOR_SIGMA`.
- Surface: span switch re-slices without refetching; the two control groups are
  independently operable; no horizontal overflow at 1440/1080/390.

## Risks

- **Two time controls.** The mitigation is labelling (`Score`, `Chart`), not
  structure. If it still confuses in use, the fix is to move `Score` into the
  masthead as part of the stamp rather than to merge them.
- **Long spans are price-only today.** 1.5 days of chatter against a year of
  price. Correct and self-resolving, but the 1Y view will look one-sided for
  months. The default span is 24h partly for this reason.
- **Payload size.** ~250KB raw, ~30KB gzipped. If it bites, server-side weekly
  downsampling beyond 90 days is a payload-only change.
- **This spends the last of the row's width.** Any future per-row field needs
  something removed, not added.

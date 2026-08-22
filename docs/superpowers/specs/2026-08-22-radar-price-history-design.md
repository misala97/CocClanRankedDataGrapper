# Radar — price history as context

## The problem

Divergence answers one question: did the price move while people were talking?
It measures hours. That is the right question when you already know the stock.

It is the wrong question the first time you see a ticker. A stock can be flat
over four hours and down 80% on the year, or flat over four hours having
already tripled since June, and those are opposite situations behind an
identical divergence score. Michi's framing: *"a stock explodes on social
media, 50000 mentions in 2 hours — I want to be able to tell the state of the
stock of the last month or year."*

This adds that context. It is read **next to** the score, not folded into it.

## Scope boundary

**This does not touch divergence, the eligibility floor, or the ranking.**
Nothing here becomes an input to a score. The board ranks exactly as it does
today; the reader gets one more column with which to interpret the result.

Restating the product boundary it inherits (PRODUCT.md): the surface describes
what was observed. A one-year price line is a description. It must not acquire
a verdict — no "oversold", no "near support", no colour that reads as a
recommendation.

## What the data actually is

Measured against the live free tier on 2026-08-22, not assumed:

- Twelve Data `/time_series` with `interval=1day` returns **exactly the
  `outputsize` requested**, no silent truncation. `outputsize=260` returned 260
  rows spanning 2025-08-11 → 2026-08-21; `outputsize=400` returned 400.
- Free tier is ~800 API credits/day and 8 requests/minute.
- Finnhub `/stock/candle` is 403 on free (measured earlier — it is the reason
  Twelve Data is in this codebase at all), so it is not an option.

At ~46 board tickers refreshed daily, this costs under 6% of the daily quota.
The per-minute ceiling is the real constraint, not the daily one.

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| What to show | A **1-year price line** per ticker | Range position alone (says nothing about how it got there); trailing returns (three more numbers on a crowded row); line + number (no horizontal room) |
| Where | **Every row**, always visible | Leads only (the unfamiliar ticker is rarely in the top three); scan rows only (inconsistent with the cards above them); tap to expand (click-gating per-row data has been rejected before) |
| Time range | **Switchable 1M / 3M / 1Y**, default 1Y | Fixed 1Y (michi asked for "month or year"); tied to the chatter Window (couples two unrelated ideas) |
| Room for it | **Merge Mentions + Authors** into `22 / 8` | Dropping the company name (unfamiliar tickers are exactly the case this serves); stacking the sparklines (implies a shared time axis that does not exist); widening the page |

## Storage

New table `radar_daily_closes`:

| column | type | notes |
|---|---|---|
| `ticker` | VARCHAR(12) utf8mb4_bin | part of PK; case-sensitive like every other ticker column |
| `close_date` | DATE | part of PK |
| `close` | NUMERIC(18,4) | the daily close |
| `fetched_at` | DATETIME(6) | when this row was written |

Primary key `(ticker, close_date)`. Not partitioned: a year of closes for a few
thousand tickers is small, and unlike `radar_buckets` it does not grow without
bound — old dates are replaced, not accumulated per source.

**`quotes.refresh_sigma` reads this table instead of calling the provider.**
Today it fetches 35 closes per ticker every 12 hours and throws them away. One
fetch now serves both sigma and the history line; the volatility job keeps its
own schedule and simply reads what the history job stored.

## The job

`radar_history`, every 5 minutes, in `run_radar_ingest.py`:

1. Take the board's tickers (`_loud_tickers`, the existing helper).
2. Prefer those with **no** stored history, loudest first — the order
   `_loud_tickers` already returns. A ticker that appears out of nowhere is
   precisely the one this feature exists for, so it must not wait behind a
   refresh queue.
3. Then refresh any whose newest `close_date` is more than **2 calendar days**
   before today. Two, not one: a Monday-morning fetch must not treat Friday's
   close as stale, and the provider has nothing newer to give over a weekend.
   Re-fetching in that state would spend the whole cycle's budget on rows that
   cannot change.
4. Cap at **20 symbols per cycle** — 4/minute against an 8/minute ceiling,
   leaving headroom for the quote job running alongside.

Failure is contained per symbol, like every other radar job: a provider
returning nothing leaves existing rows untouched rather than deleting them.

## Payload

Per row:

```json
"price_history": { "from": "2025-08-11", "closes": [118.2, 119.0, ...] }
```

A bare number array, x-positioned by index, with the first trading date named.
About 260 values per row and ~100KB across a full board.

**The x-axis is trading days, not calendar days.** Holidays and weekends do not
appear as gaps. This is a deliberate trade: at 124px wide nobody reads a date
off the line, and index slicing gives exact trading-day windows — 21 for 1M, 63
for 3M, all of it for 1Y. It also means the client needs no date arithmetic.

`price_history` is `null` when nothing is stored yet. Null is not an empty
array: never fetched and genuinely no history are different facts, and the
surface renders them differently.

## Surface

- **Scan rows** gain an eighth column, the price line. Mentions and Authors
  merge into one column reading `22 / 8` under a `Mentions / people` heading.
- **Lead cards** gain a 1-year strip beneath their existing chart. The intraday
  chatter-vs-price chart is untouched: a third series on those axes would
  destroy the one comparison the card exists to make.
- **A fourth control group**, `History: 1M · 3M · 1Y`, defaulting to 1Y. Board
  level, not per row, so every line on screen shares a window.
- **Scaling** is per row, to its own min/max over the selected range. Not
  zero-anchored, unlike the chatter sparklines: a stock's floor is not zero and
  the question here is shape, not magnitude. (The chatter sparkline is
  zero-anchored for the opposite reason — see `geometry.ts`.)
- **Colour**: the price line uses `--up` / `--down` by its direction across the
  selected range, consistent with the reservation that green and red mean price
  and nothing else.
- **No history yet** draws the same dashed rule the chatter sparkline uses for
  "not measured", so an absence never reads as a flat price.

Mobile keeps the price line and drops the merged counts to the caption row,
following the existing `.meta` pattern.

## Testing

- Geometry: index slicing for 1M/3M/1Y; a series shorter than the window; an
  empty and a null history; per-row scaling independent of the chatter scale.
- Job: prefers tickers with no history; respects the per-cycle cap; a failing
  provider leaves stored rows intact; the job is registered in `main()` (the
  profile job shipped unscheduled — an absence needs its own assertion).
- Sigma: reads the table rather than the provider, and still returns None when
  there are fewer than `MIN_CLOSES_FOR_SIGMA` rows.
- Surface: the column renders per row; missing history is visibly distinct from
  flat; the History control re-slices without refetching the board.

## Risks

- **Payload size.** ~100KB per board load. Acceptable for a desk tool on a
  normal connection; if it becomes a problem, sending weekly closes beyond 90
  days would cut it by two thirds and is a payload-only change.
- **Trading-day x-axis.** Called out above. If it turns out to mislead, the fix
  is calendar-positioned points, which changes the geometry helper only.
- **A ninth column will not fit.** This spends the last of the row's width. Any
  future per-row field needs something removed, not added.

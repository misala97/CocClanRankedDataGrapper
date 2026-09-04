# Radar — the panel draws a price line

**Status:** designed 2026-09-04
**Builds on:** the panel chart from the 2026-08-30 UI overhaul
(`static/radar/src/detail/PriceChart.tsx`), the market-data v2 identity
model (`features/radar/market_data.py`, `radar_instruments`), and the
Xetra→Tradegate history seam of spec §8.2 (`features/radar/history.py`).
Everything not named here is unchanged.

## Why

The panel's price line is absent or a two-point stub on most tickers, on
most spans. Measured against the production database on 2026-09-04:

```
board=de   RZLV  1D=20/96  1W=4/168   1M=2/30   6M=2/182   1Y=2/365   3Y=2/1095
board=us   RZLV  1D=18/96  1W=12/168  1M=19/30  6M=123/182 1Y=249/365 3Y=750/1095
```

Same ticker, same instant, same table. RZLV holds **784 stored closes back
to 2023**; the German board reads two of them. `routes/api.py:258` makes
Germany the default board for roughly 19 hours of every 24, so this is the
majority experience, not an edge case.

Seven independent faults produce it. Every figure below is from production.

| # | Fault | Breaks |
|---|---|---|
| RC1 | Chart history identity is taken from the **quote**, and `_market_filter` has no US leg for `market='de'` | 1W + all daily spans, every German-quoted ticker |
| RC2 | Almost nothing writes a `de/XGAT` close — 257 rows, 185 tickers, 2026-09-01…09-03 | the same tickers |
| RC3 | The Xetra proxy needs an ISIN-matched sibling row: **712 of 2504** XGAT instruments have one | the 72% without a Xetra listing |
| RC4 | `_daily_anchors` accepts prints only inside the regular session, bell exclusive | 1W on both boards |
| RC5 | **10,676 of 12,599** active universe tickers have zero closes; of 4,356 tickers on the board in 24 h only **1,459** have any | all daily spans, two thirds of the board |
| RC6 | 1D prices from `radar_quotes` alone; only 298 US and 197 DE tickers have ≥2 prints in 24 h | 1D |
| RC7 | US closes are stale — 397 tickers 14 days behind, 128 at 11, only 88 fresh | the right edge of every daily span |

RC1–RC3 are one story: **the venue a quote comes from and the venue a price
history is read from are different questions, and `detail_panel` answers
both with one value** (`detail_panel.py:337-338`, `:346`). RC5–RC7 are a
second story: the store is thin because per-ticker fetching tops out near
250 tickers/day against a 12,599 universe.

## What the reader gets

A price line on every span for any ticker whose price is knowable, with one
sentence saying where the line came from whenever that is not the venue in
the header. No silent substitution: a converted line says it is converted,
and a span with genuinely nothing still says `no stored price for this span`.

## 1 · The history basis

The core change. A new value type answers "where does this line come from",
resolved independently of the quote badge.

```python
@dataclasses.dataclass(frozen=True)
class HistoryBasis:
    closes: tuple                # (date, close) oldest first, already converted
    market: str                  # 'us' | 'de'
    mic: str | None
    venue: str                   # 'Nasdaq Global Market', 'Xetra', 'Tradegate BSX'
    currency: str                # the currency `closes` is expressed in
    converted_from: str | None   # source currency when converted, else None
```

`history.resolve_basis(ticker, quote, days, today) -> HistoryBasis` replaces
`series_for`'s XGAT-only special case. It builds up to three candidates:

1. **Native** — the quote's own `(market, mic)`.
2. **Sibling** — the ticker's other instrument in the same market, matched by
   equal non-null ISIN and equal currency. Today that means Xetra beneath a
   Tradegate quote; the `proxy_allowed` test at `history.py:205-208` moves
   here unchanged in substance.
3. **Converted primary** — the ticker's `is_primary` US instrument, its
   closes converted into the quote's currency (§2).

**Selection rule: the candidate with the most closes inside the requested
span wins; ties break by the order above.** Deterministic, always picks the
drawable line, and evaluated per span — a ticker may sit on Xetra at 1M and
on a converted US series at 3Y. Each span states its own basis, so this is
legible rather than confusing.

A candidate with fewer than two closes in the span is discarded before the
comparison; if none survives, the basis is empty and the renderer's existing
`no stored price for this span` text stands.

The old stitching is deleted. `HistorySeries`, `history_proxy`, `proxy_mic`,
`proxy_venue`, `native_mic`, `native_venue` and `native_from` are superseded
by `HistoryBasis` — one basis per span, no seam, one sentence. Before
deletion, grep the frontend for every one of those names: a Jinja-era
contract silently surviving a React port has bitten this codebase three
times.

**`_market_filter` keeps its US legacy-NULL leg and gains nothing.** The
German read no longer needs a US escape hatch, because basis selection —
not the filter — is what reaches the US rows.

## 2 · FX

Conversion happens at **read** time against a stored daily rate series. The
close store stays single-currency-per-venue and honest; nothing on disk is
ever a derived number.

**Table `radar_fx_rates`**

| column | type | note |
|---|---|---|
| `rate_date` | `DATE` | ECB publication date |
| `base` | `VARCHAR(3)` | `'EUR'` |
| `quote` | `VARCHAR(3)` | `'USD'` |
| `rate` | `DECIMAL(18,8)` | units of `quote` per one `base` |
| `source` | `VARCHAR(16)` | `'ecb'` |
| `fetched_at` | `DATETIME(6)` | |

Unique on `(rate_date, base, quote)`; index on `(base, quote, rate_date)`.

**Provider `features/radar/prices/ecb.py`** parses the European Central
Bank's euro reference rates — `eurofxref-daily.xml` for the daily tick,
`eurofxref-hist.xml` for the full history. No key, no account, no quota.

**Conversion.** `price_eur = price_usd / rate(EUR→USD, day)`. The ECB
publishes on TARGET business days only, so a close on a day with no
published rate uses the most recent rate strictly at or before it —
carry-forward, never interpolation. A close whose date precedes the earliest
stored rate is **dropped from the series**, not guessed; that is the same
"absent means absent" rule the chatter lane already obeys.

**Schedule.** One job at 16:30 CET, after the ECB's ~16:00 publication, plus
a one-shot backfill script. A day whose rate never arrives leaves the
previous day's rate carried forward and is logged, not retried in a loop.

## 3 · Payload and renderer

`Chart` gains `currency`, `basis_venue`, `converted_from`, and `priced_from`
(`'intraday'` | `'daily'`, for §5). The API serialises them beside the
existing fields.

`PriceChart` takes its axis and hover currency from `chart.currency` rather
than the quote's. The existing `history-proxy-note` element becomes the
**basis note**, rendered whenever the basis venue differs from the quote's
venue:

> Nasdaq Global Market closes, converted to EUR at the ECB daily rate

and, for the unconverted sibling case:

> Xetra closes · quoted at Tradegate BSX

The header quote badge is untouched: it keeps saying `Tradegate BSX · EUR`,
because that is still where the headline price comes from. The note is what
keeps the line from reading as native — the same job §8.2 gave the seam.

## 4 · `_daily_anchors`

Per trading day, the anchors come from the first source that has anything:

1. regular-session prints, **bell inclusive** (`opens <= ts <= closes`),
2. extended-hours prints for that day,
3. the stored daily close, at the closing slot.

`detail.py:296` currently uses `opens <= ts < closes` against the regular
window only. That drops 100% of Tradegate prints (its poll window is the
late session) and every US print stamped exactly at the bell — 54 of RZLV's
54 prints on 2026-08-28. The up-to-three-anchors shape is unchanged.

## 5 · 1D falls back to anchors

`intraday_chart_for` for `'1D'`: if the quote-derived series yields fewer
than two non-null slots, re-derive it from `_daily_anchors` over the same 24
hours and set `priced_from='daily'` on the chart. The panel's existing
subtitle switches from `intraday quotes` to `daily closes`.

Coarse beats empty, and the subtitle already exists to say which it is. The
alternative — declaring per-ticker poll coverage in the payload — is
deliberately **not** in scope; it is a bigger honesty feature and this fix
does not need it.

## 6 · Whole-market closes

`RADAR_US_CLOSE_SOURCE=massive_grouped` with `RADAR_MASSIVE_API_KEY` set in
the production `.env`. Massive's grouped-daily endpoint returns **every US
stock's OHLCV in one request per trading day**; the free tier's five calls
per minute is ample for a daily tick and for a ~500-request backfill of two
years.

`features/radar/prices/massive.py` and the identity mapping in
`market_data.py` already exist, are tested, and are unused only because no
key is configured. The work here is: wire the daily job into the scheduler,
add the backfill script, and confirm `record_closes`' priority table does
the right thing — `massive_grouped` (12) outranks `yahoo_chart`/`twelvedata`
(10) and `legacy` (0), so it restates existing rows and takes ownership
without a migration.

Massive's free tier is end-of-day only and roughly two years deep. That is
exactly what a daily-close store wants, and tickers with deeper legacy rows
keep them: a lower-priority source cannot overwrite, and a date Massive does
not carry is simply not written.

## 7 · German history depth and a fair queue

**Depth.** Re-run the Yahoo Xetra backfill at the full `HISTORY_DAYS = 780`.
Stored Xetra history currently starts 2024-07-10, which is why even the
tickers that *do* have a Xetra sibling render 3Y at 545 of 1095 points.

**Fairness.** `refresh_history` feeds off `_loud_tickers` (top 100 by
`mention_z` over 4 h) at `HISTORY_LIMIT = 20` per cycle, and inside the
per-MIC loop spends its budget in alphabetical order and `break`s
(`run_radar_ingest.py:870`, `:890-903`). A ticker is therefore only ever
fetched if it was once loud, and there is no per-ticker `next_due`. Give the
job a durable due-schedule — the pattern the quote poller already uses —
seeded from board-visible ∪ watched ∪ ever-quoted, so the queue drains
monotonically and budget exhaustion **delays** a ticker rather than skipping
it forever.

Scope: German instruments. Massive covers the US side wholesale (§6), so the
per-ticker fetcher's remaining job is Xetra.

**No silent empty fetches.** `history.py:285-286` does `if not closes:
continue`. A fetch that returns nothing for an identity with a mapped
instrument becomes a counted, logged failure. `yahoo.py:126-128` refuses any
MIC outside `_EXCHANGE_ALLOWLIST` — which has no `XGAT` — so the German
per-ticker fetcher has been reporting success while storing nothing since it
was written. Asking Yahoo for Tradegate history is dropped rather than
fixed: Tradegate has no deep history to fetch, and §1 no longer needs it.

## 8 · German feed pacing

`radar_market_data_cycles` has carried `download budget spent 300/300` on
every cycle since mid-morning, every day. Four channel-passes at a
five-minute cadence is 48 downloads an hour, so `DE_DOWNLOAD_BUDGET_24H =
300` (`config.py:934`) is spent before noon and the feed is dark for the
whole German trading session — the "13h stale" badge and the empty right
half of every German 1D chart.

Three changes:

- **Collect only during the Tradegate session.** Overnight cycles spend the
  budget on files nobody will read.
- **Collect only for MICs that supply a quote identity** — XGAT today. Xetra
  closes come from the Yahoo history path (§7), not from the delayed feed.
- **Raise the budget to 400.** Session-gated five-minute polling over two
  channels costs ~348 downloads/day, against the ~170/hour rate that drew
  the original HTTP 429 on 2026-09-01. The budget stays as a safety net; it
  stops being the binding constraint.

Budget state joins the ops summary, so "the German feed has been dark since
11:00" is visible without reading a cycle row.

## Non-goals

- **Per-ticker poll-coverage in the payload.** §5 covers the user-visible
  need; the honesty feature is a separate piece of work.
- **Intraday German history beyond what the delayed feed gives.** The feed
  is delayed by design and this spec does not change that.
- **`default_market`.** Germany staying the default for most of the clock is
  correct once the German board can draw; changing it would have been a
  workaround for RC1, not a fix.
- **Quote identity selection.** `markets.py:194-197` deliberately prefers a
  verified German primary over a fresh US quote. That rule is untouched —
  §1 is precisely what makes it survivable.
- **Xetra-primary tickers.** The handful of US names mapped XETR-primary are
  left alone; §1's selection rule already draws them from whichever identity
  has depth.

## Data model

One migration: create `radar_fx_rates`, and add a nullable
`history_due_at DATETIME(6)` to `radar_instruments` for §7's queue. MariaDB-safe
DDL — no `CAST(... AS JSON)`, which is a parse error on the production server.

## Testing

- **Basis resolution** — a table of cases: native wins on depth; sibling
  wins when native is a two-day stub; converted US wins when neither
  qualifies; ties fall to precedence; all-empty yields an empty basis.
- **FX** — carry-forward across a weekend and a TARGET holiday; a close
  older than the first stored rate is dropped, not converted at the earliest
  rate.
- **Anchors** — a print exactly at the bell is kept; an extended-hours-only
  day still anchors; a day with neither falls to the stored close.
- **1D fallback** — one quote print in the window triggers the daily path;
  two do not.
- **Integration matrix** over `(ticker, board, span)` asserting non-null
  close counts, written as **effect assertions**: each must fail if the
  basis silently reverts to the quote identity. An assertion whose passing
  state is an absence gets the teeth experiment before it is trusted.
- **Regression pinned to RZLV's shape** — German quote, no Xetra sibling,
  780 US closes: 1Y draws ≥240 points, `currency == 'EUR'`,
  `converted_from == 'USD'`, and the basis note is present.

## Rollout

Built on `dev_personal`. Verified locally with python-playwright at 390×844
and at desktop width before merge, on a panel that actually renders a
converted line. Merged to `main` by me.

Deploy carries, in order:

1. `flask db upgrade` in `personal_apps/`
2. `RADAR_MASSIVE_API_KEY` added to the VPS `.env` (Michi's free key)
3. ECB rate backfill (one run, seconds)
4. Massive two-year close backfill (~500 requests at 5/min, ~100 minutes)
5. Xetra 780-day backfill

## Risks

- **Massive's symbol space vs `radar_instruments`.** Grouped rows are exact
  provider symbols; identity mapping is `market_data`'s existing job, but a
  wholesale source will surface mapping gaps that per-ticker fetching never
  exercised. Expect a first run that reports unmatched symbols, and treat
  that report as data rather than as failure.
- **A converted line and the headline quote will not tick together.** The
  quote is live Tradegate EUR; the line's last point is a converted US close
  from the previous session. The basis note is what makes that legible; if
  it reads as a bug in use, the fix is copy, not arithmetic.

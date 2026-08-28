# Radar German-market view and Berlin time

**Status:** approved in conversation on 2026-08-28  
**Owner:** Michi  
**Execution:** shared across Codex and Claude through the tracked plan, ledger,
and `HANDOFF.md`; repository evidence wins over chat memory.

## Outcome

Radar gains an explicit `US | Germany` market switch. The selected market
changes the price instrument, venue, currency, market calendar, quote quality,
and extended-session calculation without duplicating social chatter or company
identity. Every user-facing timestamp renders in `Europe/Berlin`, including
the weeks when US and European daylight-saving changes do not line up.

The German view follows the same companies Radar already discovers from US
ticker chatter. It does **not** become a separate universe of German issuers.
Each company is mapped to its German EUR listing where one exists. Xetra is the
initial German venue because EIX does not publish a general market-data API;
EIX remains an adapter-compatible future source. A company without a usable
German quote stays visible using an unmistakably labelled US/USD fallback.

## User decisions

- Display all dates and times in German local time, never UTC.
- Keep the existing companies and use their German listings; do not replace
  the universe with DAX/MDAX companies.
- Provide a single-page `US | Germany` switch.
- Show pre-/after-market movement for both markets when the feed supports it.
- Delayed German quotes are acceptable when their age is visible.
- End-of-day data may be shown but must never look live or produce a live
  divergence score.
- If a German quote is unavailable, substitute the US quote and mark the
  fallback, venue, and USD currency explicitly.
- Green and red remain reserved for price direction. Session state may also be
  colour coded, but it must carry text/icon semantics and must not rely on
  colour alone.

## Non-negotiable truth rules

1. A converted USD price is not a German venue price. Radar never creates a
   synthetic EUR quote by multiplying by FX.
2. A US fallback in Germany mode says `US fallback`, its venue, and `USD`.
3. `live`, `delayed`, `EOD`, `stale`, and `unavailable` are distinct states.
4. End-of-day or stale quotes remain readable but do not participate in live
   price-divergence ranking.
5. Extended movement is measured from the appropriate regular close, not from
   the previous extended print.
6. Provider errors are contained per instrument. One missing German symbol or
   provider failure does not break the board.
7. UTC remains the storage and wire-time convention. Only presentation changes
   to `Europe/Berlin`.

## Market model

### Stable company identity

`TickerUniverse.symbol` remains the social identity (`AAPL`, `TSLA`, and so
on). Extraction, posts, buckets, baselines, and mention scoring remain keyed by
that symbol. Market instruments live beneath the company identity:

```text
AAPL company identity
├── US / XNAS / AAPL / USD
└── DE / XETR / APC / EUR
```

A new `RadarInstrument` row carries:

| Field | Meaning |
|---|---|
| `ticker` | Existing Radar/social symbol |
| `market` | `us` or `de` |
| `venue` | Human label (`Nasdaq`, `NYSE`, `Xetra`) |
| `mic` | ISO 10383 MIC (`XNAS`, `XNYS`, `XETR`) |
| `provider_symbol` | Symbol passed to the quote/history adapters |
| `currency` | ISO 4217 (`USD`, `EUR`) |
| `isin` | Cross-venue security identifier where available |
| `is_primary` | Preferred instrument for that market |
| `mapping_status` | `mapped`, `unavailable`, or `unverified` |
| `mapped_at` | When provider reference data last established the mapping |

The unique key is `(ticker, market, mic)`. There is at most one primary row per
`(ticker, market)` by application invariant. The initial migration seeds a US
instrument for every active universe row so existing quotes remain addressable.

### Mapping German listings

The mapping job reads provider reference data, not company-name guesses:

1. obtain US and German instrument catalogs;
2. join listings by ISIN when the entitlement supplies it;
3. prefer `XETR` among German matches;
4. reject ambiguous or identifier-less matches rather than guessing;
5. store `unavailable` so the same impossible mapping is not retried every
   five minutes;
6. refresh mappings weekly and allow a manual refresh command.

The Twelve Data catalog accepts `mic_code` and exposes symbol, venue, currency,
FIGI and—when enabled—ISIN. Finnhub lists Xetra (`DE`) among its supported
German exchanges. The implementation probes the configured accounts and
records which catalog supplied each verified mapping. If the current account
cannot return stable identifiers, Germany mode still ships honestly with US
fallbacks rather than fuzzy company-name joins.

### Market-aware price storage

`RadarQuote` and `RadarDailyClose` gain `market`, `mic`, `currency`, and
`provider_symbol` context. Existing rows backfill as US/USD using the active
universe exchange mapping. All quote reads and retention partitions include
market/venue so US and German snapshots never overwrite or contaminate one
another.

One normalized quote value crosses provider adapters:

```python
Quote(
    ticker='AAPL', market='de', venue='Xetra', mic='XETR',
    provider_symbol='APC', currency='EUR', price=Decimal('194.20'),
    regular_close=Decimal('193.50'), quote_ts=..., fetched_at=...,
    quality='delayed', session='regular', is_fallback=False,
)
```

The database stores original provider prices and currencies. There is no FX
conversion in the ingest or display path.

## Sessions and calculations

Session calculation is selected by market and uses timezone-aware inputs.
Stored instants remain UTC.

### US

- timezone: `America/New_York`
- pre-market: 04:00–09:30 ET
- regular: 09:30–16:00 ET, including existing holiday/early-close handling
- after-hours: regular close–20:00 ET

### Germany / Xetra

- timezone: `Europe/Berlin`
- extended early: 08:00–08:55 local
- regular: 09:00–17:30 local
- extended late: after the closing auction–22:00 local
- closed: outside those windows or on a Xetra non-trading day

The Xetra calendar is maintained separately from the NYSE calendar. Calendar
functions take `market` explicitly; there is no process-global market state.
EIX can later add a calendar with its published 07:30–23:00 hours without
changing the board contract.

For each quote:

- **regular move** = latest usable regular-session price / previous regular
  close − 1;
- **pre-market move** = current pre-market price / previous regular close − 1;
- **after-hours move** = current after-hours price / current-day regular close
  − 1;
- **current total move** remains available as current price / previous regular
  close − 1, but does not replace the separately labelled extended move.

If the provider supplies only one undifferentiated delayed last price, Radar
uses its timestamp and the calendar to classify it. It does not claim a
separate extended move unless a regular-close baseline exists for the same
market instrument.

### Freshness and score eligibility

The normalized quality states are:

| Quality | Surface | Score eligibility |
|---|---|---|
| `live` | no delay warning | eligible while tape checks pass |
| `delayed` | exact age, e.g. `12 min delayed` | eligible at age ≤ 30 minutes |
| `eod` | `EOD · <date>` | never eligible for live divergence |
| `stale` | age plus stale warning | never eligible |
| `unavailable` | no price | never eligible |

The 30-minute delayed threshold accommodates the currently measured Finnhub
delay while bounding how far chatter can outrun the price input. Frozen-tape
detection remains distinct from provider delay. A delayed quote can still be a
frozen tape.

### Ranking with fallbacks

Session and eligibility become per row. A Germany-mode row backed by a genuine
German quote ranks on its German percentage move; a US-fallback row ranks on
its US percentage move only when that quote is fresh and carries the fallback
mark. Percent/z-score normalization makes currencies comparable, but the venue
and fallback remain visible. EOD/stale rows fall back to chatter-only ordering
under the same honest rules currently used when a market is closed.

## API contract

Both board and detail endpoints accept `market=us|de`; omission remains `us`
for bookmark and embedded-payload compatibility.

Board-level fields:

```json
{
  "market": "de",
  "display_timezone": "Europe/Berlin",
  "generated_at": "2026-08-28T11:30:00Z"
}
```

Every row and detail identity receives one `quote` object:

```json
{
  "market": "de",
  "venue": "Xetra",
  "mic": "XETR",
  "currency": "EUR",
  "price": 194.2,
  "regular_move": 0.0036,
  "extended_move": null,
  "session": "regular",
  "quality": "delayed",
  "age_seconds": 720,
  "quoted_at": "2026-08-28T11:18:00Z",
  "is_fallback": false
}
```

Legacy flat price fields remain during one compatibility phase, derived from
the US quote when `market` is omitted. The frontend moves to the nested shape
in the same release; removal is a later cleanup, not part of this feature.

The market is included in React Query keys, fetch URLs, embedded payload
validation, selected-detail requests, and cache boundaries. Switching market
retains `t`, score window, sources, segments, venue floor, and chart span.

## Interface

### Header and selection

An always-visible segmented control reads `US | Germany`. It is a market-data
choice, not a locale choice: the entire interface stays in Berlin time in both
modes. The header names the selected venue/session and next boundary, for
example `Xetra regular · closes 17:30`.

Switching market keeps the selected ticker and chart span. If its German
listing is unavailable, the same ticker opens with its marked US fallback.

### Quote presentation

- EUR uses German number formatting (`123,45 €`).
- USD remains explicit (`123,45 $ · USD`) in Germany-mode fallbacks.
- Genuine German rows carry `Xetra · EUR`.
- Fallback rows carry an outlined `US fallback · Nasdaq · USD` warning.
- Quote age is visible for every non-live value.
- A stale or EOD price never uses live-looking copy.

### Session presentation

- green/red: price direction only;
- amber clock + text: pre-market;
- violet moon + text: after-hours;
- neutral venue badge: regular session;
- colour is never the sole state carrier.

The price chart lightly shades extended ranges and labels session boundaries.
Chart timestamps, post timestamps, board freshness, peak hour, and accessible
labels all format with the fixed `Europe/Berlin` timezone. Tests set instants
around both DST mismatch windows to ensure output does not depend on the VPS or
browser timezone.

## Failure behaviour

- German mapping missing: use marked US fallback.
- German quote call fails but a recent German snapshot exists: retain it with
  its computed age/quality; do not replace it with zero.
- German snapshot crosses the stale threshold: display stale and remove price
  divergence eligibility.
- Provider returns a currency other than the instrument currency: reject the
  snapshot and record an operational warning.
- German daily history is unavailable: keep the current quote, show the chart
  as not measured for that market, and do not borrow US history.
- Market catalog refresh fails: preserve verified mappings.
- Invalid `market` query: API returns 400; the human page falls back to `us`,
  matching existing bad-query behaviour.

## Migration and deployment

This is a compatibility migration, not a destructive rewrite.

1. create `radar_instruments`;
2. add nullable market context to quote/daily-close tables;
3. backfill existing rows as US/USD and seed US instruments;
4. deploy readers and writers that default omitted market to US;
5. begin German mapping and polling;
6. verify no writer emits null market context;
7. make the new context required in a later contraction migration;
8. expose the switch only when migration and readers are live.

The nullable overlap is deliberate. Task 1 may be deployed while the old
daemon still writes ticker-only rows; requiring provider symbol, MIC and
currency before that writer is upgraded would turn a compatibility migration
into an outage. Null is temporary transition state, not a third market, and
new readers interpret it as the legacy US instrument until the contraction.

Downgrade removes German-context rows and columns but cannot restore German
data into the old ticker-only key, so the migration explicitly preserves US
rows and drops non-US rows on downgrade.

## Verification

Backend tests cover:

- Berlin/Xetra and New York calendars, holidays, early closes, and DST mismatch
  weeks;
- migration backfill, mixed-version nullable writes, and downgrade preservation
  of US rows;
- ISIN mapping, Xetra preference, ambiguity rejection, and cached unavailable
  mappings;
- provider normalization, currency mismatch rejection, partial failure, quote
  quality and exact age;
- per-market quote/history isolation and retention partitioning;
- regular/pre/after calculations and absent-baseline behaviour;
- board/detail query validation, US default compatibility, fallback marks, and
  score ineligibility for EOD/stale data.

Frontend tests cover:

- market switch fetches and cache keys while retaining all other controls;
- Berlin formatting in winter, summer, and US/EU DST mismatch weeks;
- EUR/USD formatting and explicit fallback copy;
- accessible pre-/after-hours states, quote age, stale/EOD states;
- session shading and boundary labels on the chart;
- embedded payload compatibility and invalid-market page fallback.

Final gates:

- all Radar pytest targets under an isolated test database;
- all 539 existing frontend tests plus new tests;
- production build;
- Playwright at desktop and mobile widths in light/dark themes, plus print;
- no console errors, horizontal overflow, or unlabeled colour-only state;
- live provider smoke test reports entitlements and timestamps without exposing
  API keys.

## Out of scope

- scraping the Scalable cockpit or using a private EIX endpoint;
- synthetic FX-converted German prices;
- broker order placement or portfolio integration;
- replacing the US social ticker universe with German issuers;
- mixing both quote markets side by side in every list row;
- localization of all English product copy;
- paid-feed purchase or automatic subscription changes;
- EIX implementation before a permitted feed exists.

## Primary references checked on 2026-08-28

- Deutsche Börse Xetra main and extended retail hours:
  <https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours>
- EIX hours, coverage, broker availability, and cockpit-only real-time prices:
  <https://european-investor-exchange.com/en/faq>
- EIX 2026 trading calendar:
  <https://www.boerse-hannover.de/handelskalender-handelszeiten/trading-calendar-2026-hannover-european-investor-exchange/>
- Finnhub API exchange coverage:
  <https://finnhub.io/docs/api/quote>
- Twelve Data exchange tiers and Xetra EOD availability:
  <https://twelvedata.com/exchanges?level=enterprise>
- Twelve Data reference-data fields and MIC/ISIN filters:
  <https://twelvedata.com/docs>

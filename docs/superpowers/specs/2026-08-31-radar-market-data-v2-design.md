# Radar market data v2: German-first prices

**Status:** approved in conversation on 2026-08-31

**Owner:** Michi

**Scope:** binding design only; implementation requires a separate reviewed plan

## 1. Outcome

Radar replaces its unreliable and incomplete price-provider path with a
German-first market-data architecture:

- **Germany:** Deutsche Börse's free 15-minute-delayed files, with Tradegate
  BSX (`XGAT`) as the preferred venue and Xetra (`XETR`) as the German
  fallback venue.
- **United States:** Yahoo Finance's chart endpoint, treated as a useful but
  non-contractual best-effort source.
- **History:** Yahoo performs the initial one-year backfill. Deutsche Börse
  then builds native German history forward from observed venue data.

The design optimizes for the user's actual use: a dependable German price is
far more valuable than an exact benchmark-venue price, differences of a few
cents between German venues are acceptable, 15-minute delay is acceptable,
and recurring provider cost must remain EUR 0.

This spec supersedes the provider, mapping-source, venue-priority, and German
polling parts of
`2026-08-28-radar-german-market-design.md`, and the provider/job portions of
`2026-08-22-radar-price-history-design.md`. It preserves their market-aware
instrument model, Berlin-time presentation, one-chart/four-span contract,
no-FX rule, explicit provenance, and honest stale/unavailable states.

## 2. User decisions

1. German prices are the primary product requirement.
2. Fifteen-minute-delayed prices are sufficient.
3. Recurring market-data API spend is EUR 0.
4. German ongoing prices come from Deutsche Börse, not Yahoo.
5. Tradegate BSX is preferred over Xetra because its longer retail trading
   hours and broader international equity coverage matter more here than a
   few cents of venue difference.
6. Xetra is the German fallback when no verified Tradegate listing exists.
7. US prices use Yahoo only. A Yahoo outage may degrade the US view but must
   not affect German collection or the rest of Radar.
8. German historical backfill is important. Yahoo may supply Xetra history as
   an explicitly identified proxy for the same EUR security.
9. The UI shows the actual venue, currency, freshness, and whether the value
   is a trade or an indicative midpoint.

## 3. Non-negotiable truth rules

1. Radar never manufactures a German price by converting a US price with FX.
2. A value from `XGAT`, `XETR`, or a US venue retains that identity through
   storage, scoring, API serialization, and display.
3. A Yahoo Xetra historical proxy is never relabelled as Tradegate history.
4. A US fallback in Germany mode is explicit, remains USD/US, and is never
   eligible for German price-divergence scoring.
5. Provider time is distinct from fetch time. Missing provider time makes a
   quote ineligible for scoring.
6. `trade`, `midpoint`, and `close` are distinct price bases. An indicative
   midpoint never looks like an executed trade.
7. Zero, malformed, crossed-book, wrong-currency, wrong-MIC, and wrong-symbol
   values are rejected, never stored as a price.
8. A transient provider or reference-data failure preserves the last known
   mapping and observation; it cannot turn a verified mapping into
   `unavailable`.
9. One instrument is pinned to one German venue. Radar does not silently hop
   between Tradegate and Xetra from poll to poll.
10. Stale, EOD, indicative, and unavailable values may be displayed honestly
    but do not produce a live divergence signal.
11. UTC remains the storage and wire-time convention. Market calendars and
    the interface render in `Europe/Berlin`.

## 4. Source and venue architecture

### 4.1 German live and delayed data

The German collector downloads Deutsche Börse delayed **pre-trade** and
**post-trade** files once per venue per polling cycle. It does not make one
remote request per ticker. The files are expected to be approximately 15
minutes delayed and updated at least as frequently as Radar's five-minute
polling cycle.

The collector reads both channels because they answer different questions:

- post-trade supplies executed prices and volume;
- pre-trade supplies the best bid and ask when a security has no sufficiently
  recent execution.

Only instruments in the active Radar set are materialized into quote rows.
The downloader nevertheless maintains a durable source cursor so a restart
can consume still-retained files in order. The cursor is keyed by source,
MIC, and channel and records the last accepted remote identity, event time,
and content checksum. Re-reading a file is idempotent.

The operator must personally accept Deutsche Börse's current delayed-data
terms before credentials, cookies, or access artifacts are configured. The
implementation must not automate acceptance or bypass access controls. The
free service is used only while the project's use remains permitted by those
terms; a commercial-use change stops this source pending a new rights review.

### 4.2 Venue priority and pinning

For each social ticker, the weekly mapping refresh chooses exactly one German
primary instrument:

1. a verified Tradegate BSX (`XGAT`) EUR listing;
2. otherwise a verified Xetra (`XETR`) EUR listing;
3. otherwise no German instrument.

The primary choice changes only during an atomic mapping refresh. A temporary
Tradegate feed failure leaves the last Tradegate quote to age into `stale`; it
does not substitute Xetra and create a false price move. A primary may change
only when a complete successful reference refresh proves it unavailable or
delisted and verifies the replacement.

When no German listing can be verified, Germany mode may retain the existing
explicit `US fallback` presentation for availability. That fallback is used
only for a genuinely absent German mapping, never for a transient German feed
failure, and is excluded from German price scoring. The user can switch to the
US view for the normal Yahoo-backed US price.

### 4.3 Price selection within a German venue

The selected price is deterministic:

1. Use the newest valid executed trade whose provider timestamp is no more
   than 30 minutes old.
2. Otherwise, if both delayed bid and ask are present, positive, not crossed,
   no more than 30 minutes old, and for the same instrument and book time,
   display `(bid + ask) / 2` as `indicative`.
3. Otherwise retain the previous observation with its increasing age, or show
   unavailable when none exists.

An indicative midpoint is visible because it is more useful than an empty
cell, but it is not eligible for divergence in this version. The spread is
returned for diagnosis; no hidden maximum-spread rule turns a very wide book
into an apparently precise trade. Daily closes always come from an executed
or officially identified closing value, never a midpoint.

### 4.4 German sessions

Tradegate is treated as open from 07:30 to 22:00 Berlin local time on its
trading days. To preserve the existing movement vocabulary:

- early: 07:30–09:00;
- regular reference window: 09:00–17:30;
- late: 17:30–22:00.

Xetra retains its own 08:00 early start, 09:00–17:30 core session, and late
retail phase to 22:00 where supported. Calendars are selected by MIC; they are
not one process-global German calendar.

For either venue, early movement uses the previous venue-session close. Late
movement uses that day's 17:30 regular-reference value. Prefer an official
closing value when the captured contract identifies one; otherwise use the
last valid executed trade at or before 17:30. If no such trade exists that
day, `regular_close` remains absent rather than borrowing a midpoint or the
other venue.

### 4.5 US data

US quotes and history use Yahoo's per-symbol chart endpoint. The implementation
must not depend on the currently unauthorized batch quote endpoint. Requests
use bounded concurrency, a cache, explicit timeouts, exponential backoff, and
a conservative application-side rate limit.

Every Yahoo result is checked against the requested provider symbol, expected
currency, exchange metadata where present, and provider timestamp. HTTP 401,
403, 429, malformed data, missing timestamps, or an identity mismatch makes
that instrument unavailable for the cycle. There is no cookie scraping,
browser automation, or escalating retry storm.

Yahoo is an unofficial, unsupported source without an availability contract.
Its failure degrades only US quotes/history and operational status. It cannot
block German ingestion, chatter ingestion, board rendering, or daemon health.

## 5. Binding German instrument mapping

### 5.1 Inputs

The mapping refresh uses:

- the existing US Radar instrument identity;
- OpenFIGI's public mapping API for share-class linkage;
- official German venue reference data for the final local instrument check;
- a small version-controlled reviewed-override file for exceptional issuer or
  ADR relationships that cannot be represented by the same share-class FIGI.

Company-name search is never an automatic live mapping source.

### 5.2 Automatic path

For each active Radar ticker:

1. Map the exact US ticker plus its known US exchange to one unique equity or
   ETF result. Reject multiple classes or unsupported security types.
2. Take its `shareClassFIGI` and request
   `ID_BB_GLOBAL_SHARE_CLASS_LEVEL` with `micCode=XGAT` and `currency=EUR`.
3. If no unique supported result exists, repeat for `micCode=XETR`.
4. Match the returned local mnemonic exactly against the complete official
   reference universe for that MIC. Confirm EUR currency and allowed security
   type; capture the official ISIN.
5. Accept only one candidate. Any ambiguity, missing official row, mismatched
   currency/type, or missing stable identifier remains `unverified` rather
   than guessed.

The path was read-only probed on 2026-08-31: AAPL resolved to APC, TSLA to TL0,
and NVDA to NVD on `XGAT`. SAP's US sponsored ADR did not resolve to the German
ordinary share, which is the correct reason for the override path rather than
loosening automatic matching.

### 5.3 Reviewed overrides

An override contains, at minimum:

```text
social ticker, US instrument identifier, German MIC, local mnemonic,
German ISIN, currency, evidence URL/reference date, reviewer, reviewed_at
```

Overrides are exact data, not regexes or aliases. Every weekly refresh must
reconfirm that the MIC/mnemonic/ISIN combination still exists in the complete
official reference universe. A missing or conflicting row disables the
override as `unverified`; it is not silently preserved forever.

### 5.4 Refresh semantics

- Refresh weekly and on an explicit operator command.
- Build and validate the complete candidate set before one transaction changes
  primary mappings.
- A partial catalog, transport error, rate limit, or parse error rolls back the
  refresh and preserves all prior verified rows.
- Mark `unavailable` only after both required reference universes were fetched
  completely and no valid mapping or override exists.
- Cache unavailable outcomes until the next weekly refresh, not forever.
- Log additions, removals, primary-venue changes, override use, and every
  refusal reason without logging secrets.

## 6. Provider-contract capture gate

The exact Deutsche Börse file index, compression, field names, event types,
and identifier representation have not yet been observed under accepted
terms. They must not be guessed into production code.

The first implementation task is therefore a read-only protocol capture after
the operator accepts the terms. It records, without committing licensed bulk
payloads:

- discoverable file/index behavior for `XGAT` and `XETR` pre/post-trade;
- compression and bounded uncompressed sizes;
- source timestamps, timezone/offset behavior, ordering, and sequence fields;
- the exact stable instrument identifier and how it joins the reference file;
- trade, correction/cancellation, bid, ask, volume, and official-close
  representations actually present;
- empty, duplicate, out-of-order, late, malformed, and market-closed examples;
- download size, parse time, and bandwidth for a full polling cycle.

The parser and schema plan may use only fields demonstrated by that capture.
Sanitized, hand-authored minimal fixtures reproduce the observed shapes in the
test suite; raw licensed market files do not enter Git. If the accessible files
lack stable identity, provider timestamps, or enough data to implement the
truth rules in §3, German implementation stops and this design is revised.

## 7. Normalized data and persistence

The existing provider-neutral `Quote` boundary remains. It gains provenance
without leaking provider JSON into board code:

```python
Quote(
    ticker='AAPL', market='de', venue='Tradegate BSX', mic='XGAT',
    provider_symbol='APC', currency='EUR', price=Decimal('194.21'),
    previous_close=Decimal('193.50'), regular_close=None,
    quote_ts=..., fetched_at=..., provider_delay='delayed',
    source='deutsche_boerse_delayed', price_basis='trade',
    bid=Decimal('194.20'), ask=Decimal('194.22'), volume=120,
)
```

Binding normalized additions are:

| Field | Values / meaning |
|---|---|
| `source` | `deutsche_boerse_delayed`, `yahoo_chart`, or explicit migration-era legacy source |
| `price_basis` | `trade`, `midpoint`, or `close` |
| `bid`, `ask` | nullable original EUR book values; both required to derive midpoint |
| `quote_ts` | provider event time in UTC; never replaced by `fetched_at` |
| `provider_delay` | `delayed` for these sources; `stale` remains age-derived |

`RadarQuote` persists those fields alongside the existing market, MIC,
currency, symbol, price, close, volume, and timestamps. One poll may store one
snapshot per selected instrument. Repeated polls with an unchanged provider
timestamp remain valid snapshots because frozen-tape detection depends on
that evidence; processing the same file twice within one poll does not create
duplicates.

`RadarDailyClose` gains source provenance. A daily-close write is uniquely
identified by ticker, market, MIC, and date. For the same identity/date,
verified Deutsche Börse data wins over Yahoo backfill; a lower-priority source
cannot overwrite it.

Invalid observations fail per instrument. The rest of a valid venue file is
committed, while transport/archive/parser-level corruption rejects the entire
file and does not advance its durable cursor.

Trade corrections and cancellations are applied before price selection. If a
captured feed can revoke an earlier trade, the collector retains enough event
state within the source's published correction horizon to recompute the latest
valid trade; a cancelled execution cannot survive merely because its first
message was already normalized.

## 8. Historical backfill and forward history

### 8.1 Yahoo backfill

After mappings are frozen, a bounded, resumable job fetches at least the last
400 calendar days at daily resolution:

- US instruments use their verified Yahoo US symbol and are stored under
  their US MIC/currency.
- German instruments use the verified Xetra mnemonic plus Yahoo's `.DE`
  convention only when Yahoo response metadata confirms the expected EUR
  Xetra identity.
- Failure to verify the exact Yahoo identity leaves history unavailable; the
  job does not fall back to search-result name guessing.

Backfill is idempotent and independently restartable. It records source and
fetch time, rejects future/duplicate/impossible prices, and never overwrites a
higher-priority native close.

### 8.2 Xetra history as a Tradegate proxy

Yahoo does not provide the chosen Tradegate tape. For a Tradegate-primary
instrument, verified Xetra daily closes may fill the older portion of the
one-year chart only when Xetra and Tradegate rows share the exact ISIN and EUR
currency.

The join is a single seam:

- Xetra proxy closes appear only before the first native Tradegate close;
- from the first native Tradegate date onward, missing Tradegate dates remain
  missing rather than being silently patched with Xetra;
- the API returns `history_proxy=true`, proxy MIC/venue, native MIC/venue, and
  the seam date;
- the UI states, for example, `Xetra history through 31 Aug · Tradegate now`.

Because this is the same identified EUR security and the user accepts small
venue differences, the Xetra proxy may seed historical volatility/sigma until
enough native Tradegate closes exist. It never supplies the current German
quote or pretends that a Tradegate trade occurred. US/USD history is never a
German volatility proxy.

### 8.3 Native German history

Deutsche Börse observations accumulate German history forward. After each
session and the source delay buffer:

- prefer a provider-designated official close when the captured contract
  proves one exists;
- otherwise use the final valid executed trade in that venue's session and
  retain `price_basis=close` plus the actual source/event provenance;
- never construct a close from a midpoint;
- rerun reconciliation the next morning while the official files are still
  retained, replacing only lower-priority data for the same MIC/date.

## 9. Polling, freshness, and active coverage

### 9.1 German cycle

Run every five minutes while either German venue may be open, plus one
post-close reconciliation cycle. Each cycle downloads source files once,
selects the currently mapped active Radar instruments, and persists one
normalized observation per instrument when possible.

The active set is the union of tickers needed by all current board windows and
segments, not merely the top rows of one default view. Intake ordering may
prioritize louder tickers, but a cap must not permanently starve a ticker that
the board can display.

### 9.2 US cycle

Yahoo polling runs independently on a 15-minute cadence for the same
board-eligible union. It uses a fair due queue, bounded concurrency, cache,
and backoff. Repeated provider failure may leave US stale without slowing the
German cycle.

### 9.3 Quality and eligibility

| State | Display | German divergence eligibility |
|---|---|---|
| delayed trade, age ≤ 30 min, moving tape | exact age and venue | eligible |
| delayed midpoint, age ≤ 30 min | `indicative`, bid/ask age | never |
| EOD/close | date and venue | never live |
| age > 30 min or frozen tape | `stale`, exact age | never |
| US fallback in Germany mode | `US fallback`, USD/venue | never German |
| unavailable | no fabricated number | never |

Age is computed from the provider event time. Fetch time is shown separately
in diagnostics and never makes old market data fresh.

## 10. API and interface contract

The existing `market=us|de` contract remains. Quote responses add:

```json
{
  "market": "de",
  "venue": "Tradegate BSX",
  "mic": "XGAT",
  "currency": "EUR",
  "price": 194.21,
  "price_basis": "trade",
  "bid": 194.20,
  "ask": 194.22,
  "quality": "delayed",
  "age_seconds": 1030,
  "quoted_at": "2026-08-31T12:43:00Z",
  "source": "deutsche_boerse_delayed",
  "is_fallback": false,
  "score_eligible": true
}
```

Surface rules:

- genuine values say `Tradegate · EUR` or `Xetra · EUR`;
- midpoint values add `indicative` and never use trade-like copy;
- US fallbacks say `US fallback · <venue> · USD`;
- every delayed/stale value exposes its age;
- history proxy metadata is visible near the chart, not hidden in a tooltip;
- no provider failure removes the row or breaks the page;
- green/red direction remains separate from freshness and basis.

Existing legacy flat fields survive one compatibility release and are derived
from the same selected quote. They must not apply different venue, freshness,
or eligibility logic from the nested quote object.

## 11. Operations and failure isolation

The daemon exposes a cached operational summary, not a new remote check on
every board request:

- last successful pre/post file per MIC and channel;
- source event lag and fetch lag;
- files seen, accepted, duplicated, rejected, and retried;
- parse duration, compressed/uncompressed bytes, and selected instrument
  count;
- mapped/unverified/unavailable counts and mapping refusal reasons;
- current trade/midpoint/stale/unavailable proportions;
- Yahoo success, latency, 401/403/429, identity mismatch, and backoff state;
- history coverage and native/proxy seam counts.

Safety limits reject unexpectedly large downloads, excessive decompression
ratios, invalid archives, malformed JSON, and unbounded collections before
they exhaust VPS memory. Logs contain remote identities and reason codes but
not cookies, terms tokens, API keys, or full licensed payloads.

German and Yahoo workers have separate schedules, state, transactions, and
feature switches. A failure in one is recorded and contained; neither worker
may terminate the general Radar daemon.

## 12. Rollout and activation gates

Deployment is staged and independently reversible:

1. **Terms and capture:** operator accepts permitted terms; complete §6.
2. **Expand:** add nullable provenance fields and compatible readers; old
   writers continue safely.
3. **Mapping shadow:** build `XGAT`/`XETR` mappings without changing board
   selection; audit refusals and overrides.
4. **History:** run the resumable Yahoo backfill and expose no proxy as native.
5. **German shadow:** collect for one complete Tradegate trading session
   without serving the new source.
6. **German activation:** switch Germany reads only after all gates below pass.
7. **US activation:** switch US reads to Yahoo independently; it is not a
   prerequisite for German activation.
8. **Contract:** make transition-null fields required only after every writer
   and rollback-compatible reader has been deployed.

German activation requires evidence from the full-session shadow:

- **identity:** zero wrong security, MIC, or currency in an audit of at least
  50 mapped instruments, including ordinary shares, ETFs, dual listings, and
  reviewed overrides;
- **mapping:** at least 90% of the top 100 30-day Radar tickers for which the
  complete official references show a German listing have a verified primary
  mapping; the remainder have explicit refusal reasons;
- **display coverage:** at least 95% of mapped active instruments have a valid
  trade or midpoint during open-session sampled cycles;
- **freshness:** p95 provider-event age is no more than 30 minutes during the
  open session;
- **transport:** at least 99% of scheduled source cycles either succeed or
  deterministically identify that no newer file exists;
- **history:** at least 95% of expected trading dates in a 20-instrument,
  one-year audit have verified Yahoo closes or an explicit provider-closed/
  suspended absence;
- **truth:** zero transient venue hops, zero midpoint-as-trade cases, zero US
  values labelled German, and zero proxy rows relabelled native;
- **resource:** measured download, decompression, parse time, and memory fit
  comfortably inside the VPS budget with the safety caps enabled.

Failure of any identity or truth gate blocks activation. Other failed gates
require either a fix and repeat shadow or an explicit spec revision; they are
not waived inside the implementation plan.

Rollback disables the new reader/writer independently per market and restores
the previous compatible read path. It does not delete captured quotes,
history, mappings, or cursors. A mapping rollback restores the previous atomic
mapping generation. Old Finnhub/Twelve Data adapters may remain for one
release as rollback code, but they receive no routine calls after the new
sources activate and are removed only in a later cleanup.

## 13. Required verification

### 13.1 Mapping

- unique US share class to `XGAT` success;
- `XGAT` absence to `XETR` success;
- ADR/share-class mismatch refusal and exact reviewed override;
- ambiguous class, wrong currency/type, missing official row, and incomplete
  catalog refusal;
- failed refresh preserves the previous complete generation;
- venue primary cannot change outside an atomic successful refresh;
- an override disappears when official mnemonic/MIC/ISIN no longer agrees.

### 13.2 Deutsche Börse parser and ingestion

- sanitized fixtures for captured pre/post shapes, compression, event times,
  corrections/cancellations, duplicates, ordering, and market-closed files;
- archive/decompression/size guard failures do not advance the cursor;
- exact instrument identity prevents cross-security contamination;
- newest valid trade wins; absent trade produces only a valid two-sided
  midpoint; crossed/one-sided/zero books produce none;
- repeated poll snapshots preserve frozen-tape evidence while duplicate file
  processing within a poll stays idempotent;
- one bad instrument does not discard other valid observations, while a
  structurally corrupt file is atomic and rejected;
- Berlin DST boundaries and both MIC calendars classify event time correctly.

### 13.3 Yahoo and history

- chart endpoint success, 401/403/429/backoff, timeout, malformed response,
  identity/currency/exchange mismatch, and missing provider timestamp;
- Yahoo failure cannot call, block, or roll back the German transaction;
- backfill resumes without duplicates and never overwrites native data;
- Xetra proxy requires exact ISIN+EUR, stops at one seam, is labelled in API
  and UI, and never supplies a current Tradegate quote;
- US/USD history cannot enter German sigma or chart data;
- native close selection never uses a midpoint and reconciles idempotently.

### 13.4 Board and compatibility

- actual venue, currency, basis, age, fallback, proxy, and score eligibility
  agree across board, detail, and legacy projection;
- a transient `XGAT` outage ages the pinned quote and never switches to Xetra
  or US;
- an unmapped German instrument may use only the explicitly marked,
  score-ineligible US fallback;
- midpoint/stale/EOD/fallback rows are absent from live divergence;
- market cache keys isolate US and Germany;
- Germany remains functional when every Yahoo call fails;
- the existing one-chart/four-span behavior and Berlin presentation remain
  unchanged apart from the new truthful provenance.

Tests for absence-shaped requirements must prove their teeth: first make the
forbidden behavior observable (for example, deliberately enable venue hopping,
midpoint eligibility, cursor advance on corruption, or proxy relabelling) and
show the assertion fails, then restore the correct implementation. Merely
passing because a fixture never enters the dangerous branch is insufficient.

Final verification includes the complete Python suite against the isolated
test database, frontend unit tests, production build, a full-session shadow
report, and desktop/mobile visual checks for every quote state.

## 14. Out of scope

- paid data subscriptions or automatic upgrades;
- real-time rather than delayed Deutsche Börse data;
- broker execution, portfolio valuation, or tax accounting;
- synthetic FX prices;
- fuzzy company-name mapping in a live job;
- sourcing German social chatter by German ticker symbols;
- treating Yahoo as a supported public API or circumventing its controls;
- dynamically choosing the venue with the newest price each poll;
- making indicative midpoint prices divergence-eligible;
- changing sentiment, extraction, ranking, or chatter retention logic;
- redesigning the market switch or chart beyond the provenance states here.

## 15. Primary references checked on 2026-08-31

- Deutsche Börse delayed data overview and retention:
  <https://www.mds.deutsche-boerse.com/mds-en/real-time-data/Delayed-data>
- Deutsche Börse Tradegate BSX market-data coverage:
  <https://www.mds.deutsche-boerse.com/mds-en/real-time-data/European-spot-markets/Tradegate-BSX-1341022>
- Tradegate trading hours:
  <https://www.tradegate.de/docs/ANNOUNCEMENT_Trading-Hours.pdf>
- Xetra tradable instruments and official reference downloads:
  <https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra>
- Xetra trading hours:
  <https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours>
- OpenFIGI mapping API and rate limits:
  <https://www.openfigi.com/api/documentation>
- Yahoo exchange coverage and delay disclosure:
  <https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html>
- yfinance's statement that Yahoo Finance has no supported public API and is
  intended for research/personal use:
  <https://github.com/ranaroussi/yfinance>

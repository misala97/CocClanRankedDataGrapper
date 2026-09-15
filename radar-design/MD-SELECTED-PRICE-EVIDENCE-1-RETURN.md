# MD-SELECTED-PRICE-EVIDENCE-1 — Researcher return

2026-09-15, Researcher (Claude Fable 5.1, no subagents). Return to the Mastermind. Research only: no application, test, config or schema change; no DB, production, service, capture, commit, push or deployment action.

Workspace C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore, branch codex/radar-ha1-us-daily-explore, HEAD daadf3868caedcb5db858378e919cba68b735f8a (verified before and after the work; matches the expected base). All pre-existing dirty and untracked files preserved. New files owned by this return: this report and radar-design/artifacts/md-selected-price/ (scripts, JSON, README). HA1 remains COMPLETE / DEPLOYED / CLOSED and was not touched.

Evidence attribution used throughout: **FRESH** = executed in this assignment on 2026-09-15; **SAVED** = the 2026-09-09/10 probe summary and comparison in the main workspace, read-only; **DOC** = primary-source documentation or terms read on 2026-09-15; **INFER** = my inference. Nothing marked FRESH was retried, rotated or worked around.

## 0. Answer in one paragraph

A truthful, timestamped 1D line for a selected US instrument is supported by two undocumented candidates (Nasdaq undated chart; Yahoo `1d/1m` with pre/post) and a genuine five-session 1W intraday series is supported by **Yahoo `5d/5m` only**: the Nasdaq chart endpoint returns daily OHLCV bars whenever dates are supplied and returned no intraday history for any dated window, so Nasdaq cannot supply 1W. Both undocumented sources carry site terms with explicit anti-automation and personal/non-commercial clauses and both hosts publish `robots.txt: Disallow: /`; Finnhub is the only documented, keyed source in the set and its `/quote` documentation says constant polling is not recommended. The paired quote sample (five instruments, one regular-session moment) shows all three sources agreeing within cents but cannot rank sustained reliability; Nasdaq's trade stamp has only minute resolution, which limits any event-time comparison rule to minute granularity. Recommended first increment: one **Yahoo chart adapter extension** (reusing `prices/yahoo.py` transport, identity allowlist and backoff) serving 1D (`1d/1m`, pre/post) and 1W (`5d/5m`, regular sessions) as independently timestamped price points through a **separate, isolated price-series endpoint**, with stored-series fallback, per-provider health counters, and a passive paired-age log that produces the MD-05 dataset. **No headline-source change** in this increment: the evidence supports a labelled on-open observation, not a new selection rule. Nasdaq stays a documented candidate for a later 1D density/bid-ask trial, not part of the first adapter. Usage-condition ambiguity is recorded, not resolved.

## 1. Candidate matrix

| Need | Candidate | Capability established | Evidence class | Not established / caveats |
| --- | --- | --- | --- | --- |
| 1D timestamped line | Nasdaq `GET api.nasdaq.com/api/quote/{sym}/chart?assetclass=stocks|etf` (no dates) | Current session so far, from 04:00 ET pre-market, one `{x,y,z}` point per traded minute; `exchange`, `symbol`, `company`, `previousClose`, `timeAsOf` in the envelope; AAPL 349 pts 04:00–09:48 ET, SPY 342, RZLV 188, GE 109, BRK.B 159 (second sample) | FRESH; SAVED (AAPL 868 pts 04:00–18:27 ET after-hours) | `x` is **ET wall-clock encoded as if UTC** (offset 4 h in EDT, see §2.3); no OHLCV; no currency (`null`, only a `$` string); points exist only at traded minutes (GE sparse); 3 of 29 Nasdaq calls returned HTTP 200 with `data: null` and a vendor error; latency 0.7–4.4 s; behaviour overnight/weekend not sampled |
| 1D timestamped line | Yahoo `GET query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m&includePrePost=true` | Same session from 04:00 ET; per-minute OHLCV bars where trades occurred (AAPL 352, SPY 306, RZLV 190, GE 48, BRK-B 50); `meta` gives `symbol`, `currency`, `exchangeName`, `instrumentType`, `exchangeTimezoneName`, `regularMarketPrice/Time`, `currentTradingPeriod` | FRESH | Sparser than Nasdaq in pre-market for NYSE names in this sample (GE 48 vs 109); one `null` bar at the in-progress minute plus a trailing off-grid point at `regularMarketTime`; unofficial; not sampled outside the regular session |
| Genuine multi-session 1W | Yahoo `range=5d&interval=5m&includePrePost=false` | **Five actual sessions returned for all five instruments** (2026-09-09, 10, 11, 14, 15): 78 five-minute OHLCV bars per completed regular session (09:30–15:55 ET) + partial today; spacing 300 s inside sessions, 63,300 s overnight, 236,100 s over the weekend; 0–1 null close per response; `chartPreviousClose` = close before range | FRESH | No `adjclose` on intraday; adjustment basis unverifiable (no corporate action in the window); `validRanges` differs per symbol (RZLV lacks `10y`); unofficial |
| Genuine multi-session 1W | Nasdaq `chart` with `fromdate/todate` | Returns **daily OHLCV bars only** (`z.open/high/low/close/volume`, `x` at ET-midnight-as-UTC); 9-day window → 5 daily bars 09-08..09-14, 2-day window → 1 bar (09-14), same-day window → `data: null` vendor error | FRESH | **Does not deliver intraday history for any dated window tested**; therefore not a 1W candidate; daily bars duplicate what Massive already stores |
| Selected-instrument headline | Nasdaq `GET /api/quote/{sym}/info?assetclass=…` | `lastSalePrice`, `bidPrice/askPrice`, sizes, `volume`, `lastTradeTimestamp` (minute resolution), `isRealTime: true`, `marketStatus`, `exchange`, `stockType`, `assetClass`, `isNasdaqListed`; HTTP 200 + `rCode 400 "Symbol not exists."` for unknown symbol or wrong `assetclass` | FRESH; SAVED (after-hours sample with `isRealTime: true`) | `currency: null`; prices are `$`-prefixed strings; volume string carries a fractional part; minute-resolution stamp; undocumented; no documented delay/consolidation statement |
| Selected-instrument headline | Finnhub `GET /api/v1/quote?symbol=` (keyed) | Documented `c,d,dp,h,l,o,pc` + `t` (epoch seconds); `X-RateLimit-Limit: 60`, `-Remaining`, `-Reset` headers; unknown symbol → `c: 0, t: 0` with HTTP 200 | FRESH; DOC | No bid/ask/volume; docs: "Constant polling is not recommended"; `t` lagged request time by 18–29 s in five regular-session samples (§3) |
| Selected-instrument headline | Yahoo chart `meta.regularMarketPrice/Time` (by-product of the series fetch) | Seconds-resolution stamp 1–7 s behind request time in the same five samples; currency and exchange in the same envelope | FRESH | A by-product, not a quote endpoint; unofficial; same terms exposure as the series |

Sources not in scope and not probed: TradingView, Massive, Deutsche Börse, Stooq, Twelve Data.

## 2. Sample and response semantics (deliverable 2)

### 2.1 Sample selection and identity

Five instruments plus one nonexistent symbol; identity from the Nasdaq Trader listing files dated 2026-08-24 in the main workspace (`personal_apps/nasdaqlisted.txt`, `otherlisted.txt`) and confirmed against the providers' own identity fields on 2026-09-15. This sample was chosen to cover the required classes; **it does not measure universe coverage**.

| Ticker | Why | Listing-file identity (2026-08-24) | Nasdaq `info` (FRESH) | Yahoo `meta` (FRESH) |
| --- | --- | --- | --- | --- |
| AAPL | Nasdaq common; continuity with the SAVED probe | nasdaqlisted, category Q (Global Select), ETF=N | `NASDAQ-GS`, Common Stock, `isNasdaqListed: true` | `NMS` / NasdaqGS, EQUITY, USD |
| GE | NYSE common; continuity with SAVED TradingView row | otherlisted, exchange N, ETF=N | `NYSE`, Common Stock | `NYQ` / NYSE, EQUITY, USD |
| SPY | ETF path (`assetclass=etf`) | otherlisted, exchange P (NYSE Arca), ETF=Y | `PSE`, `assetClass: ETF`, `stockType: null` | `PCX` / NYSEArca, ETF, USD |
| RZLV | small stock; used in the original comparison | nasdaqlisted, category G (Global Market), ETF=N | `NASDAQ-GM`, Ordinary Shares | `NGM` / NasdaqGM, EQUITY, USD |
| BRK.B | symbol edge case (dot vs hyphen vs slash) | otherlisted `BRK.B` (CQS `BRK.B`, Nasdaq symbol `BRK.B`) | `BRK.B` accepted by `info` and (second sample) `chart`; `BRK-B` → "Symbol not exists."; `BRK%2FB` → HTTP 404 empty body | Yahoo requires `BRK-B` (dot rejected implicitly: symbol is `BRK-B` in meta) |
| ZZZZZZ | empty/invalid behaviour | none | HTTP 200, `rCode 400`, "Symbol not exists.", `data: null` | HTTP 404 with JSON `error.code "Not Found"`; Finnhub HTTP 200 `c: 0, t: 0` |

Classification caveat: the listing files are three weeks old and Yahoo's `instrumentType` and Nasdaq's `assetClass` agreed with them for all five; current `is_etf` in `TickerUniverse` was not read (DB access excluded).

### 2.2 Session, range, spacing, nulls

Run window: 13:50:04–13:52:00 UTC (09:50–09:52 ET, **US regular session open**, Tuesday) plus a 4-request supplement at 13:56 UTC. The SAVED probe was at 22:28 UTC on 2026-09-09 (18:28 ET, after-hours). Two sessions are therefore covered (regular, after-hours); pre-market-only, closed/overnight and weekend request behaviour were **not** sampled and remain explicit gaps.

Nasdaq undated chart (FRESH): every response covered exactly one ET date (today) from 04:00 ET to the minute before the request. Spacing was 60 s for 348/348 gaps on AAPL, but GE had 56×60 s, 15×120 s, 15×180 s, 8×240 s, 4×300 s, 1×600 s: points exist only where a trade printed. No null or non-positive `y` in any response; `x` strictly monotonic. SAVED after-hours sample: 04:00–18:27 ET on one date. So "1D" from this endpoint means **the current or most recent session including extended hours, as of the request**.

Nasdaq dated chart (FRESH): `fromdate=2026-09-06&todate=2026-09-15` → 5 points dated 9/8, 9/9, 9/10, 9/11, 9/14 with `z.open/high/low/close/volume` (strings with thousands separators) and **no bar for the in-progress session**; `fromdate=todate=2026-09-15` → `data: null` with `bCodeMessage code 1000 "Something went wrong.Please try again later."`; `fromdate=2026-09-14` → one bar. INFER: dated requests select a daily series; the SAVED comparison's "1-minute bars" wording for the undated request and "daily OHLCV" for dated requests are both consistent with this.

Yahoo `5d/5m` (FRESH): 318 timestamps per response for all five symbols = 4 × 78 completed regular sessions + 6 for today, dates 09-09/10/11/14/15. AAPL/GE/SPY carried one all-null bar at the in-progress 09:50 slot plus one trailing point at `regularMarketTime` (spacing 18–104 s off the 300 s grid); RZLV and BRK-B had no null. Yahoo `1d/1m` (FRESH): from 04:00 ET; 1-minute where traded; pre-market rows for AAPL/SPY/RZLV/BRK-B carry `volume: 0`. All five `meta.exchangeTimezoneName = America/New_York`, `gmtoffset = -14400`, `currency = USD`, `currentTradingPeriod.regular = 09:30–16:00 ET`.

### 2.3 Timestamps and timezone

- Nasdaq `x` is milliseconds, but the value labelled `"4:00 AM ET"` was `1789444800000` = 2026-09-15T04:00:00**Z**. Yahoo's 04:00 ET bar was `1789459200` = 08:00Z. The difference is exactly 14,400 s. FRESH on all five symbols and consistent with the SAVED sample (`1788926400000` labelled 4:00 AM ET on 2026-09-09). Daily `x` values are ET midnight encoded the same way (`1788825600000` labelled 9/8/2026). **An adapter must convert `x` as an ET wall-clock instant (or parse `z.dateTime` with the ET zone), never as a UTC epoch**; the offset changes at the DST boundary.
- Nasdaq `lastTradeTimestamp` is a string with minute resolution ("Sep 15, 2026 9:50 AM ET"); after the close the SAVED sample showed a date-only `timeAsOf`.
- Yahoo `timestamp` and `regularMarketTime` are true epoch seconds; bars are stamped at bar **start**.
- Finnhub `t` is epoch seconds of the quote.

### 2.4 Listing, currency, price and adjustment basis

- Nasdaq: exchange named in both `chart` and `info` envelopes; **currency always `null`**; prices are strings such as `"$330.495"`; `y` is a float. The `$` is not proof of USD.
- Yahoo: `currency`, `exchangeName`, `instrumentType` present; the existing `_EXCHANGE_ALLOWLIST` in `prices/yahoo.py` already maps XNAS/XNGS/XNCM/XNYS/ARCX to the codes observed (NMS, NGM, NYQ, PCX).
- Price basis: Nasdaq undated `y` and Yahoo `close` are last-trade-derived values per minute/bar (INFER from field names and the `info` `lastSalePrice` agreement); neither provider documents consolidated-tape status for these endpoints. Nasdaq `isRealTime: true` is a flag in the payload, not a documented guarantee.
- Adjustment: no corporate action fell in the sampled window, so adjustment behaviour of either intraday series is **unverified**. Yahoo daily `close` is split-only per the existing adapter comment [A1]; intraday responses carry no `adjclose`.

### 2.5 Failures observed

- Nasdaq soft failures: 3 of 29 chart/info calls answered HTTP 200 with `rCode 200`, `data: null` and vendor error codes 1000/2001 (BRK.B chart twice at 13:51, AAPL same-day dated at 13:56). BRK.B chart succeeded five minutes later without any change. INFER: transient upstream errors are ordinary and must be classified as *unavailable*, never as an empty series or an unknown symbol.
- Nasdaq unknown symbol / wrong `assetclass` (SAVED): HTTP 200 with `rCode 400`. HTTP status alone cannot classify a Nasdaq response.
- Yahoo unknown symbol: HTTP 404 with a JSON error object.
- No 401/403/429 from any provider in 39 data requests; no `Retry-After` seen. Yahoo responses carried `Cache-Control: public, max-age=10, stale-while-revalidate=20`; Nasdaq `no-cache, no-store`.

## 3. Paired quote event age and identity (deliverable 3)

Credentials: `FINNHUB_API_KEY` exists in the repository root `.env` (read through python-dotenv, never printed; value not inspected). No other provider needs a key. Requests were sequential, so "paired" means within ~10–25 s of each other, not simultaneous.

| Ticker | Nasdaq `lastTradeTimestamp` (ET) / request (ET) | Finnhub `t` (ET) / request | Yahoo `regularMarketTime` (ET) / request | Prices: Nasdaq / Finnhub / Yahoo |
| --- | --- | --- | --- | --- |
| AAPL | 09:50 (minute) / 09:50:13 → age ≤ 13 s (0–60 s resolution) | 09:49:55 / 09:50:22 → 27 s | 09:50:18 / 09:50:19 → 1 s | 330.495 / 330.37 / 330.53 |
| GE | 09:50 / 09:50:36 → ≤ 36 s | 09:50:19 / 09:50:46 → 27 s | 09:50:36 / 09:50:43 → 7 s | 312.535 / 312.45 / 312.535 |
| SPY | 09:50 / 09:50:58 → ≤ 58 s | 09:50:43 / 09:51:07 → 24 s | 09:50:53 / 09:50:54 → 1 s | 759.29 / 759.38 / 759.31 |
| RZLV | 09:51 / 09:51:18 → ≤ 18 s | 09:50:57 / 09:51:26 → 29 s | 09:51:19 / 09:51:23 → 4 s | 2.2652 / 2.28 / 2.265 |
| BRK.B | 09:51 / 09:51:40 → ≤ 40 s | 09:51:30 / 09:51:48 → 18 s | 09:51:44 / 09:51:45 → 1 s | 514.98 / 515.24 / 514.965 |

Findings (FRESH, five samples, one moment, regular session, liquid-to-mid names):
- All three agreed within a few cents on every name, consistent with one moving tape; not an identity proof, and Nasdaq's `currency: null` means USD is inferred from the instrument, not confirmed by the provider.
- Finnhub's `t` was 18–29 s behind request time on every sample; Yahoo's `regularMarketTime` 1–7 s; Nasdaq's stamp is minute-truncated so its true age lies anywhere in 0–60 s. INFER: Finnhub `/quote` behaves like a periodically refreshed snapshot rather than a last tick, which its own docs hint at ("Use websocket if you need real-time updates").
- A minute-resolution stamp means any Nasdaq-vs-Finnhub event-time comparison rule can only be honest at minute granularity. This is a design constraint for MD-05, not a reliability verdict.
- This sample **cannot** establish sustained freshness, coverage, outage rates or justify retiring the Finnhub poller. The poller has other consumers (`radar_quotes` for `move_since`, frozen-tape status, scoring, `_daily_anchors`), none of which a display change touches.

## 4. Documentation and usage conditions (deliverable 4)

All accessed 2026-09-15.

Finnhub (DOC):
- https://finnhub.io/docs/api/quote — "Get real-time quote data for US stocks. Constant polling is not recommended. Use websocket if you need real-time updates." Schema `Quote`: `c` current price, `d` change, `dp` percent change, `h/l/o` day high/low/open, `pc` previous close; `t` appears in the sample response but is absent from the schema table. (Page is JavaScript-rendered; text extracted from the served HTML.)
- https://finnhub.io/docs/api/rate-limit — "If your limit is exceeded, you will receive a response with status code 429. On top of all plan's limit, there is a 30 API calls/ second limit." The plan limit is not stated on that page; the observed header `X-RateLimit-Limit: 60` with a 60-second `X-RateLimit-Reset` window is FRESH evidence of this key's plan limit.
- https://finnhub.io/terms-of-service — personal plans are "strictly for personal use"; "You hereby agree to not redistribute or share access to data or derived results from the data obtained from Finnhub with anyone or any 3rd party without written approval from Finnhub"; "Personal plan can't be used by any business even internally without a written approval"; "All data must be deleted should your subscription to that data ends." (Fetched through the summarising fetch tool; quotes as returned by it.) Radar already uses this key in production; whether Radar's multi-user personal deployment is "personal use" is an owner judgement I do not make.

Nasdaq (DOC):
- No public documentation for `api.nasdaq.com` was found; the endpoints are those used by nasdaq.com's own pages (SAVED review, confirmed by absence of any docs link on the legal page).
- https://www.nasdaq.com/legal — "Nasdaq Legal Information, Last Updated: May 11, 2026". Quotes: "Nasdaq grants you a personal, limited, revocable, non-exclusive, non-assignable, non-sublicensable and non-transferable license to use the Services solely for your personal, non-commercial use."; "Not access or use the Service, or any process, whether automated or manual, to capture data or content from the Service or circumvent any mechanisms for preventing the unauthorized reproduction or distribution of the Service for any reason"; "Not take any action that imposes a large load on the infrastructure of the Services"; a separate AI-training clause prohibits "scraping, data mining, and the use of any automated or manual process to capture or compile content" for that purpose.
- https://api.nasdaq.com/robots.txt — "This robots.txt file disallows all web crawlers from indexing any pages in this API application to prevent search engine indexing of API endpoints. User-agent: * Disallow: /". www.nasdaq.com/robots.txt sets `Crawl-delay: 30` for `*`.
- The SAVED comparison's observation that a non-browser User-Agent stalls rather than refuses is a dated observation, not a documented condition; this run used the single string `Mozilla/5.0` and did not test alternatives.

Yahoo (DOC):
- https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html (Terms of Service, version noted as effective May 2025 by the fetch) — prohibits use of "any automated means, devices, programs, algorithms or methodologies, including but not limited to robots, spiders, scrapers, data mining tools" to "access or collect data"; prohibits use of data "to create any database, archive, mobile application, data feed, widget or any other aggregated data source that competes with or constitutes a material substitute for the Services"; "you may not access or reuse the Services, or any portion thereof, for any commercial purpose" unless authorised.
- https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html (Yahoo APIs Terms of Use, REV 3-2022) — governs Yahoo's developer APIs; **does not mention the finance chart endpoint**; states "Yahoo's APIs may be subject to rate limits at Yahoo's absolute and sole discretion."
- https://query1.finance.yahoo.com/robots.txt — `User-agent: * Disallow: /`.
- The project's own 2026-08-31 design already restricts Yahoo to bounded roles and refuses to "treat Yahoo as a supported public API or circumvent its controls" (SAVED review §6); the owner has since directed that historical choices do not constrain the design, which is a product ruling, not a change in Yahoo's terms.

Usage-condition status (INFER, not a legal conclusion): Finnhub is the only source with a documented interface and a keyed licence whose personal-use scope Radar already operates under. Nasdaq and Yahoo both publish site terms that on their face forbid automated data capture and non-personal use, and both hosts disallow all crawlers. Successful HTTP 200s establish access, not permission. The brief asks that this ambiguity be preserved and not turned into a repeated approval ceremony; it is recorded here once for the Mastermind's scope ruling.

Recommended application limits (design choices, **not** provider allowances):

| Control | Recommendation | Basis |
| --- | --- | --- |
| Upstream requests per web process per provider | ≤ 10 per minute (token bucket), ≤ 1 in flight | Sync gunicorn workers handle one request at a time; observed Nasdaq latency 0.7–4.4 s |
| Global upstream bound | per-process cap × 2 web workers = ≤ 20/min per provider, plus the existing ingest daemon's Yahoo usage | Production runs `gunicorn --workers 2` (PERF1 ledger, HANDOFF radar-design/HANDOFF.md:636); process-local caches do not dedupe across workers |
| Cache key / TTL | (provider, provider_symbol, mic, span) → 60 s fresh; serve stale ≤ 15 min with `served_stale_age`; ≤ 200 keys per process, ≤ 128 KiB per entry | Detail refetch interval is 60 s (`REFRESH_MS`), so 60 s TTL bounds one open panel to ≤ 1 upstream/min/worker |
| Timeouts | connect 3.05 s, read 5 s; hard ceiling 6 s per upstream call | Same connect value as `YahooHttp`; a sync worker is blocked for the whole call |
| Backoff | on 401/403/429 or `Retry-After`: reuse `_BACKOFF_STEPS` (60 → 1800 s), honour `Retry-After` when larger; on Nasdaq `data: null` vendor errors: 30 s soft backoff, no retry inside the request | `prices/yahoo.py` ladder already exists |
| Health counters | per provider: success, empty, invalid (identity/shape/timestamp), timeout, throttle, served_stale, fallback, latency histogram; exposed through the existing ops route, labelled per process | MD-10 |
| Stale label | any series older than 60 s is labelled with its `received_at`; older than 15 min is not served as "1D" at all, only as a dated fallback | brief contract |

## 5. Current integration trace and interface recommendation (deliverable 5)

Fresh source inspection at HEAD daadf38, not runtime.

- `features/radar/detail.py:349 intraday_chart_for`: `INTRADAY_SPANS = {'1D': (96, 15), '1W': (168, 60)}`; `start = now - slots×step` (rolling 24 h / 168 h windows). 1D = `intraday_prices` from `radar_quotes` by `quote_ts` (last write per slot); below `MIN_INTRADAY_POINTS = 2` falls back to `_daily_anchors` over `history.resolve_basis(ticker, quote, 3, today)`. 1W = `_daily_anchors` (up to three real prints per day else the daily close). The `Chart` dataclass carries `closes` (slot array), `chatter`, `step_minutes`, `priced_from` ('intraday'|'daily'), `currency`, `basis_venue`, `converted_from`.
- `features/radar/detail_panel.py:350 build`: calls `quotes_mod.quote_views_for([ticker], market, now)` (line 367) for the headline `QuoteView`, `move_since`, then the chart. Everything is assembled in one request; any upstream call placed here blocks the whole panel and, on a sync worker, the worker.
- `features/radar/routes/api.py:785 ticker_detail` → `serialize_detail` (line 684) emits `chart.from` (ISO Z), `step_minutes`, `closes`, `chatter`, `sessions`, `priced_from`, etc. Frontend contract `static/radar/src/types.ts:110 DetailChart` mirrors it; `PriceChart.tsx` draws evenly spaced slots (`pricePaths`, `slotDate = from + index×step`). `ResearchContent.tsx:42 captionFor` special-cases `1D` + `daily`; the `1W` caption is the constant "intraday quotes · mentions per hour" even though the line is daily anchors — the caption should come from the data contract (`priced_from`/resolution), which the new contract fixes as a side effect.
- Consumers of `ChartSection`: `Research.tsx:113` and `ChatterWorkspace.tsx:378`; both own one `useDetail` (`queries.ts:706`, `refetchInterval: REFRESH_MS = 60_000` while visible). Adding a second hook (`usePriceSeries`) in `ResearchContent`'s callers keeps "one request per selected company" per data kind.
- `features/radar/quotes.py:287/311 statuses_for` orders by `fetched_at`; `_stored_quote` and `markets.select_quote` build the `QuoteView`. **Not touched** by the recommended increment: no display observation is written to `radar_quotes`.
- `features/radar/prices/yahoo.py`: `YahooHttp.get_chart(symbol, interval, period1, period2, include_prepost)` already provides one session, a 60 s process-local cache keyed by the full parameter tuple, `(3.05, 15)` timeouts, and the 401/403/429 backoff ladder; `_result`, `_identity_ok(meta, provider_symbol, currency, mic)` and `_bars` validate envelope, identity and parallel arrays. `YahooProvider` uses a 4-permit semaphore. The `range=` form used by the probe is equivalent to `period1/period2` for the adapter; `get_chart` takes epoch bounds, so 1D = `[start of the session's 04:00 ET, now]` and 1W = `[five sessions back, now]` computed from `market_calendars.session_bounds`. Gap: the module does not derive a Yahoo symbol from a dotted ticker (`BRK.B` → `BRK-B`); `RadarInstrument.provider_symbol` is a single column whose Yahoo value for class shares was not verified (DB excluded).
- `prices/__init__.py` `QUOTE_SOURCES` and the `radar_quotes` CHECK constraint enumerate sources; a display-only series needs **no** new source enum and no row writes, so no schema change.
- Web topology: production `gunicorn --workers 2 --bind 127.0.0.1:5001`, sync workers, no threads (radar-design/PERF1-LEDGER.md:59, :792); the board path already solved cross-process bounds with a DB-row lease (`board_store.py`). For this increment a process-local cache with the ×2 global bound is adequate at Radar's viewer count; a DB-backed shared cache is the documented upgrade path if the health counters show duplicate upstream fetches across workers.

Interface recommendation:
1. `prices/yahoo.py`: add `YahooProvider.intraday_points(instrument, *, session_window, interval, include_prepost)` returning a `PriceSeries` value object (`provider`, `provider_symbol`, `mic`, `currency`, `interval_seconds`, `session_dates`, `covered_from/to`, `price_basis='trade'`, `adjustment_basis='unadjusted'`, `event_points=[(ts_utc, price)]`, `received_at`, `stale_age`, `quality`). Null/zero/non-positive bars are dropped; identity failure or empty → `PriceUnavailable`, never an empty success.
2. New module `features/radar/price_series.py`: window semantics, cache/coalescing/backoff/health, fallback assembly (`fallback='stored_intraday'|'daily_anchors'|'none'` with the fallback's own provenance and age), and chatter alignment bounds.
3. New endpoint `GET /radar/api/ticker/<t>/price?span=1D|1W&market=us` (own login guard, own timing), returning `{series | null, fallback | null, window: {from, to, sessions}, provenance, health_note}`; `ticker_detail` unchanged.
4. Frontend: `usePriceSeries` hook; `PriceChart` learns to draw `event_points` on the existing linear time axis (`x = (t − from) / (to − from)`) while the chatter histogram keeps its 15-minute buckets; caption and legend read resolution/basis from the payload. `closes` stays for spans without a series so `Research.tsx` and `ChatterWorkspace.tsx` need no structural change.

## 6. Recommended first increment (deliverable 6)

Scope: **US-primary native-USD instruments**, Research page and shared Chatter research panel, display only. German/international behaviour unchanged.

Included:
- **1D**: Yahoo `interval=1m`, `includePrePost=true`, window = the current session's extended hours (04:00 ET → now) while the US calendar says pre-market/regular/after-hours; when closed, the most recent completed session (04:00–20:00 ET). Points at their own timestamps; gaps stay gaps; pre/post bands from the existing `_chart_sessions`.
- **1W**: Yahoo `interval=5m`, `includePrePost=false`, window = the **five most recent actual US sessions** (dates shown), regular hours only; overnight/weekend/holiday spans are drawn as closed bands, not as flat lines. This replaces the rolling 168-hour window and is the explicit date-window change the brief asks to state.
- **Chatter alignment**: chatter buckets are queried for exactly the session-window bounds above (1D: 04:00 ET → now; 1W: first session's 04:00 ET → now), keeping their own 15-minute timestamps; mentions unchanged; no invented values.
- **Fallback**: when the provider is unavailable/backed off/invalid: 1D → existing `intraday_prices` from `radar_quotes` for the same instrument if ≥ 2 points, else `_daily_anchors` labelled "daily"; 1W → `_daily_anchors` labelled "daily / sparse observed anchors". The fallback carries its own source and age; provider partial ranges are never stitched to stored data.
- **Headline**: unchanged selection path (`quote_views_for`). The chart's last event point is displayed inside the chart with its own timestamp only. The adapter records, for every on-open fetch, the provider's last event time and the stored headline quote's `quote_ts`/`fetched_at` age into the health log — this passively builds the paired dataset MD-05 needs without a poller change.
- **Resilience and health (MD-10)** as in §4's table, shipped with the adapter; ops surface shows per-process counters.
- Identity: pin `RadarInstrument` primary (`ticker, market, mic, provider_symbol, currency`); reject any Yahoo `meta` mismatch via `_identity_ok`; if `provider_symbol` for dotted tickers is not Yahoo-shaped, the instrument is reported "unsupported symbol" rather than guessed.

Explicitly deferred (with the reason):
- **Nasdaq adapter**: capable for 1D (denser pre-market points, bid/ask in `info`) but adds a second undocumented terms exposure, the ET-as-UTC timestamp quirk, `currency: null`, ~10 % soft vendor failures and 1–4 s latency on a sync worker, and it cannot serve 1W. Revisit as a bounded 1D/bid-ask trial only if Yahoo 1D pre-market sparsity is a demonstrated problem.
- **Headline source change (MD-05)**: not supported by five samples at one moment; the minute-resolution Nasdaq stamp constrains any future rule to minute granularity. Decide after the passive paired log covers multiple sessions.
- **Finnhub poller retirement**: outside evidence and outside this display change.
- Candles/volume/OHLCV rendering (MD-11), DB-shared cache, German venues, MD-03/08 scans, scoring changes, adjustment-aware seam detection beyond flagging `chartPreviousClose` discontinuities.

Acceptance evidence the implementation packet should demand: identity rejection test per allowlist code; timestamp/timezone tests across the DST boundary; null-bar and trailing-live-point handling; five-session window across a weekend and a holiday; fallback provenance labels; health counter increments for each failure class; total upstream request count under one open panel for 10 minutes ≤ 10 per worker.

## 7. Limitations of this return

- One regular-session moment (09:50 ET) plus one SAVED after-hours moment; no pre-market-only, closed, overnight, weekend or holiday sampling. Provider behaviour for "1D" outside sessions is inferred from range semantics, not observed.
- Five instruments; no coverage claim across the mapped universe; no illiquid/OTC/ADR/preferred sample.
- No corporate action in the window, so adjustment behaviour is unverified for both intraday sources.
- 39 data requests total (35 main + 4 supplement) plus 3 `robots.txt` reads and documentation page reads; 48-request ceiling respected; all sequential ≥ 2 s apart, 15 s timeout, fixed `User-Agent: Mozilla/5.0`, no Origin/Referer, cookies, proxies or retries. No throttling response was observed, which says nothing about limits.
- Finnhub `/quote` documentation and terms were read through rendered/served HTML and a summarising fetch; quotations are as extracted and should be re-read in a browser before being cited in a spec.
- The Yahoo symbol mapping for dotted class shares in `RadarInstrument.provider_symbol` was not verified (no DB access).
- Load, concurrency and sustained-reliability measurements were not performed and are not claimed.

## 8. Artifacts (local, uncommitted)

- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore/radar-design/artifacts/md-selected-price/probe_selected_price.py — main probe (35 requests).
- …/probe_summary.json — per-request log (status, latency, bytes, selected headers, parameters with the token redacted) and per-instrument semantic summaries.
- …/probe_raw_points.json — complete returned point arrays (public prices only) for later verification of spacing/timestamps.
- …/probe_supplement.py and probe_supplement.json — the 4-request supplement (dated Nasdaq windows, `BRK/B`, BRK.B second sample).
- …/README.md — request configuration and ledger.
- Documentation captures used for quotation live only in the session scratchpad and are not needed for continuity; URLs and access dates are in §4.

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Assess the Researcher return
for MD-SELECTED-PRICE-EVIDENCE-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Branch / base / current HEAD: codex/radar-ha1-us-daily-explore / daadf3868caedcb5db858378e919cba68b735f8a / daadf3868caedcb5db858378e919cba68b735f8a (verified before and after the work; no commits)
Working tree: all pre-existing dirty files (HANDOFF.md, radar-design/*.md notices, HA1 artifacts, docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md, MD-* files) preserved and untouched. New files owned by this return: radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md and radar-design/artifacts/md-selected-price/ (probe_selected_price.py, probe_summary.json, probe_raw_points.json, probe_supplement.py, probe_supplement.json, README.md). Nothing committed or pushed.
Binding brief / ledger / return: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore/radar-design/MD-SELECTED-PRICE-BRIEF.md ; …/radar-design/MD-SELECTED-PRICE-LEDGER.md ; …/radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md
Objective and authorized scope: resolve only the evidence gaps needed to scope selected-instrument price improvements (MD-02/07 + MD-05 + MD-10) and recommend the smallest useful implementation increment; read-only code inspection, public documentation, and a conservative local provider probe (ceiling 48 requests, sequential, ≥2 s apart, ≤15 s timeout, fixed ordinary configuration, stop on 401/403/429). No implementation, deployment, DB/production access, capture activation, commits, subagents or further dispatch.
Completed work: (1) candidate matrix for Nasdaq 1D line, multi-session history (Nasdaq dated, Yahoo 5d/5m) and Nasdaq/Finnhub/Yahoo headline; (2) five-instrument sample (AAPL Nasdaq-GS, GE NYSE, SPY NYSE Arca ETF, RZLV Nasdaq-GM small stock, BRK.B dotted class share) plus a nonexistent symbol, with identity, range, spacing, nulls, timestamps/timezone, currency, failures; (3) paired Nasdaq/Finnhub/Yahoo quote event-age sample using the local FINNHUB_API_KEY; (4) primary-source documentation and terms with URLs and access dates plus recommended application limits; (5) integration trace (detail.py, detail_panel.py, quotes.py, routes/api.py, prices/yahoo.py, ResearchContent/PriceChart consumers, two-sync-worker topology) with interface boundaries; (6) one recommended increment with explicit defers.
Evidence: 39 provider data requests on 2026-09-15 13:50–13:57 UTC (09:50–09:57 ET, US regular session open), all HTTP 200 except Yahoo 404 for the nonexistent symbol; no 401/403/429, no Retry-After. Key results: Nasdaq undated chart = current session from 04:00 ET, one point per traded minute (AAPL 349, SPY 342, RZLV 188, GE 109, BRK.B 159), x encodes ET wall-clock as if UTC (4 h offset vs Yahoo epoch), currency null, 3/29 Nasdaq calls returned HTTP 200 with data null vendor errors; Nasdaq dated chart returns daily OHLCV only (9-day window → 5 bars, same-day → data null), so no Nasdaq multi-session intraday; Yahoo 5d/5m returned five actual sessions (09-09/10/11/14/15), 78 regular-session bars per completed day, OHLCV, exchange/currency/timezone metadata, 0–1 null bar; Yahoo 1d/1m with pre/post comparable to Nasdaq for Nasdaq names, sparser pre-market for NYSE names (GE 48 vs 109). Paired ages: Finnhub t 18–29 s behind request, Yahoo regularMarketTime 1–7 s, Nasdaq stamp minute-resolution (≤60 s); prices agree within cents. Finnhub headers X-RateLimit-Limit 60. Docs/terms: finnhub.io/docs/api/quote, /rate-limit, /terms-of-service; nasdaq.com/legal (Last Updated May 11, 2026), api.nasdaq.com/robots.txt (Disallow: /); legal.yahoo.com OTOS, Yahoo APIs ToU, query1.finance.yahoo.com/robots.txt (Disallow: /). Artifacts: radar-design/artifacts/md-selected-price/*.json and *.py. SAVED evidence reused: main-workspace comparison and codex_review_probe_results.json (2026-09-09 after-hours AAPL 868 points).
Evidence attribution: fresh execution for all 2026-09-15 numbers; previous reports for the 2026-09-09/10 after-hours sample and the two-worker gunicorn topology (PERF1 ledger); inference for range semantics outside sessions, Finnhub snapshot behaviour, and price basis of undocumented fields.
Findings and limitations: identity — Nasdaq currency null and $-strings, Yahoo needs BRK-B while Nasdaq needs BRK.B, RadarInstrument.provider_symbol for dotted tickers unverified (no DB); range — Nasdaq cannot serve 1W, Yahoo 5d/5m can; session — only regular (fresh) and after-hours (saved) sampled, no pre-market-only/closed/weekend/holiday; adjustment — unverified, no corporate action in window; access — no throttling observed, which proves nothing about limits; usage conditions — Nasdaq and Yahoo site terms forbid automated data capture and non-personal use and both hosts disallow all crawlers; Finnhub is the only documented keyed source and its docs discourage constant polling; ambiguity recorded, no legal conclusion drawn. No sustained-reliability or poller-retirement claim is made.
Recommended first increment: Yahoo chart adapter extension (reuse prices/yahoo.py transport, identity allowlist, backoff) serving 1D (1m, pre/post, current or last session from 04:00 ET) and genuine 1W (5m, five most recent actual sessions, regular hours, dates displayed — replaces today's rolling 24 h/168 h windows) as independently timestamped price points via a new isolated endpoint /radar/api/ticker/<t>/price?span=, with stored-series fallback labelled by its own provenance/age, no stitching, chatter buckets aligned to the session window at their own timestamps; MD-10 controls: per-process ≤10 upstream/min/provider (global ≤20 with two sync workers), 60 s fresh / ≤15 min stale cache, connect 3.05 s / read 5 s, existing backoff ladder + Retry-After, per-provider success/empty/invalid/timeout/throttle/served_stale/fallback counters on the ops route; passive paired-age log for MD-05. Headline selection unchanged. Deferred: Nasdaq adapter (1D density/bid-ask trial later), MD-05 headline rule, Finnhub poller retirement, OHLCV/candles, DB-shared cache, German venues, MD-03/08, scoring.
Actions taken: created research scripts and sanitized JSON under radar-design/artifacts/md-selected-price/; 39 provider data reads + 3 robots.txt reads + documentation page reads; read the root .env only through python-dotenv for FINNHUB_API_KEY (never printed). No application/test/config/schema edits, no DB/production/service actions, no capture activation, no commits/pushes/deploys, no edits to main-workspace evidence or existing continuity files.
Protected state: other worktrees, B1C/5021, promotion/5033, databases/3306/3399, C:/Users/michi/.radar-ha1-local-qa, HA1 artifacts and all existing dirty files untouched.
Subagents: none
Updated artifacts: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore/radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md ; C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore/radar-design/artifacts/md-selected-price/ (all local, uncommitted)
Requested Mastermind decision: rule on the first-increment scope — Yahoo-only adapter for 1D + genuine 1W with fallback and MD-10 controls, headline unchanged, Nasdaq deferred — including the owner-level usage-condition acceptance for an undocumented source, or narrow to Option 2 (1D-only with stored fallback).
Next bounded action: prepare the supported implementation packet (binding spec/plan with the §6 window semantics, PriceSeries contract, endpoint isolation, limits table and acceptance evidence) for one Implementer and one focused Reviewer/QA.

Read current handoff and price ledger, verify Git/artifact evidence,
rule on scope and update planning continuity. HA1 remains closed.
Do not implement, deploy or dispatch workers automatically.
```

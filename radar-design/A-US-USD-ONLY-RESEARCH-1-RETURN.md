# A-US-USD-ONLY-RESEARCH-1 — Researcher return

Date: 2026-09-16
Role: Researcher (read-only repository investigation)
Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
Branch: `codex/radar-selected-price-charts`
Verified HEAD: `38591e0f5e98faccb5228d84d1677843fcdb2aea` = `origin/main` = `origin/codex/radar-selected-price-charts`
Binding spec: `radar-design/A-US-USD-ONLY-SPEC.md`; ledger: `radar-design/A-US-USD-ONLY-LEDGER.md`; prompt: `radar-design/A-US-USD-ONLY-RESEARCH-1-PROMPT.md`

All paths below are relative to `personal_apps/` unless prefixed otherwise. Line numbers are at HEAD 38591e0.

---

## 1. Executive conclusion

German/EUR support is **live and reachable on every layer** of Radar at HEAD, not dormant:

- **API default is Germany.** `routes/api.py:50` (`Query.market = 'de'`) and `routes/api.py:248-263` (`default_market`) open an unqualified board on `de` whenever the US regular session is not the *only* live one. `parse_query` (`api.py:273-275`) accepts `market=de`. The same parser feeds `/radar/api/board`, the shared-board path, the detail endpoint, the hub HTML shell and the legacy board page.
- **Two UI selectors exist**: `static/radar/src/board/MarketSwitch.tsx` (legacy board, radio US/DE) and `static/radar/src/hub/Filters.tsx:33-35, 87-96` (hub `<select>` US/Germany). `Hub.tsx:699-702` names the market; `embedded.ts:41` coerces the embedded payload to `de`.
- **Four scheduler paths run German work regardless of flag** (`run_radar_ingest.py:1380-1401`): `radar_de_market_data` every 5 min (Twelve Data DE poll under `legacy`, Deutsche Börse collector under `shadow|active`), `radar_ecb_fx` daily 16:30 Berlin, `radar_mappings` weekly (Xetra/OpenFIGI mapping only), and `radar_history` which calls `refresh_de_history` (Yahoo `.DE`) **in every mode** (`run_radar_ingest.py:1072-1076`) plus native-close materialization under non-legacy.
- **Two background writers reach the DE board**: `board_producer.WARM_MARKETS = ('us','de')` (4 of 8 warm boards are German) and `observations.MARKETS = ('us','de')` (quarter-hourly archive captures the German board when capture is enabled).
- **FX conversion is active at read time**: `history._converted_basis` (`history.py:259-289`) converts US closes to EUR for any EUR-quoted row; `leaderboard._quote_sigmas` (`leaderboard.py:134-150`) seeds German sigma from that converted basis; `detail.intraday_chart_for` and `serialize_detail` expose `converted_from`; `detail/PriceChart.tsx:64-65` prints "converted to EUR at the ECB daily rate".
- **US fallback inside Germany mode** is a first-class code path (`markets.select_quote`, `quotes.quote_views_for`, `QuoteBadges.tsx`, `TickerRow.tsx:302`, `Identity.tsx:61`, `ResearchContent.tsx:307`).

The **protected US paths are already US-only by construction** and need no functional change: selected-price charts (`routes/price_chart.py:46-54` rejects `market=de` with 422 today; reader SQL pins `market = 'us'`; contract pins `currency: 'USD'`), HA1 analysis (`analysis.py:79,95`, `analysis_contract.py:256-278`), grouped-close ingestion (`market_data.grouped_instrument_map` filters `market == 'us'`; `test_grouped_ingest_never_touches_a_german_row`), and the US quote cycle (`_run_us_price_cycle`).

**Schema boundary is clean to state**: five tables are DE-only (`radar_fx_rates`, `radar_mapping_generations`, `radar_market_data_cursors`, `radar_market_data_cycles`, `radar_market_trade_events`); three shared tables carry `market IN ('us','de')` CHECK constraints (`radar_instruments`, `radar_quotes`, `radar_daily_closes`) and `source IN (... 'deutsche_boerse_delayed' ...)` CHECKs; `radar_provider_session_states` is shared (US uses it). All are created by four immutable migrations. Old DE rows exist in production (2,517 DE-mapped tickers, 3,229 DE instrument rows per `US-USD-ONLY-DECISION.md`; quote/close/FX row counts not measured).

**Two current behaviours contradict the "untouched" rule and need a Mastermind ruling** (section 8): `retention._prune_daily_closes` already deletes old DE Yahoo closes (it excepts only `deutsche_boerse_delayed`), and `retention.prune_market_data` deletes DE journal/cycle rows nightly.

Confidence: high on backend reachability (every entry point traced to code); high on frontend inventory (grep over all `.ts/.tsx` plus reading each hit); medium on test disposition counts (collected, not executed); production flag *values* unknown by design. Coverage limits in section 1a.

### 1a. Coverage and limits

Inspected: all of `features/radar/` (backend), `routes/`, `prices/`, `market_calendars/`, `run_radar_ingest.py`, `run_radar_board_producer.py` (via `board_producer.py`), `models.py` Radar models, all 64 migration files (grep) and the 4 DE-relevant ones (read), `scripts/` (headers of all; full read of DE ones), `static/radar/src/**` (grep all, read every hit), `templates/radar/`, `tests/` (grep all Radar suites, test-name listing, `--collect-only` on DE-only and protected suites), `deploy/`, `requirements.txt`, repo docs and `radar-design` continuity for flag names.

Not done / not authorized: no database read; no production `.env` read (only variable **names** observed in the committed release journal `radar-design/artifacts/md-selected-price-alpaca-release/release-unit-38591e0.journal.txt:52-55`, which lists `RADAR_DE_PRICE_MODE`, `OPENFIGI_API_KEY`, `RADAR_MASSIVE_API_KEY`, `RADAR_US_CLOSE_SOURCE` as present; values unknown); no test execution beyond `pytest --collect-only`; no provider call; no VPS systemd unit inspection (units are not in this repository; `DEPLOY_FRONTEND.md:108,126` names the `radar_ingest` unit). Untracked-file enumeration in this worktree is limited by Git's earlier warning about the unreadable global ignore file (recorded in `MASTERMIND-STATE.md`); `git ls-files --others` in code directories returned nothing.

---

## 2. Path-and-symbol inventory

Disposition key: **DELETE** = active DE/EUR-only, remove; **SURGICAL** = shared file, edit the DE parts only; **ARCHIVAL** = keep for schema/ORM/migration/history compatibility; **REJECT-TEST** = keep/add as proof that unsupported input fails; **OOS** = out of scope.

### 2a. Backend modules

| Path : symbol | Role today | Reachability evidence | Shared US dependency | Disposition |
|---|---|---|---|---|
| `features/radar/prices/deutsche_boerse.py` (whole, 499 lines) | DBAG delayed-file transport/parser, XGAT/XETR | imported by `market_data.py:34` (`FeedRejected`) and `run_radar_ingest.py:733` | none | **DELETE** |
| `features/radar/prices/ecb.py` (whole) | ECB eurofxref fetch/parse | `run_radar_ingest.py:989`, `scripts/backfill_radar_fx.py:16` | none | **DELETE** |
| `features/radar/prices/openfigi.py` (whole) | US→German venue share-class mapping | `instruments.py:26`, `run_radar_ingest.py:176` | none (US never mapped via OpenFIGI) | **DELETE** |
| `features/radar/fx.py` (whole) | EUR/USD rate store + `convert_usd_to_eur` | `history.py:281`, `run_radar_ingest.py:34,985`, `scripts/backfill_radar_fx.py` | none | **DELETE** |
| `features/radar/reference_universe.py` (whole) | Xetra/Frankfurt CSV + Tradegate crawl catalogs | `run_radar_ingest.py:174-182` only | none | **DELETE** |
| `features/radar/market_calendars/de.py`, `tradegate.py` | Xetra/Tradegate session calendars | `market_calendars/__init__.py:18,28-31` | none | **DELETE** |
| `features/radar/market_calendars/__init__.py:18,21-35` | registry; `_calendar` selects `de`/`XGAT`/`XETR` | every `session_state(...)`/`session_bounds(...)` caller | **yes** — `us` branch serves board, API, quotes, detail, US cycle | **SURGICAL**: import only `us`; `_calendar` accepts only `'us'`; keep `mic` parameter for callers (US MIC is passed through, ignored) |
| `features/radar/market_calendar.py` | legacy US wrapper | `run_radar_ingest.py:215` | US | keep (no change) |
| `features/radar/markets.py:12` `Market = Literal['us','de']`; `:176` `expected_currency` map; `:188-216` `select_quote` DE validation + US-fallback branch; `:93,142-148` `is_fallback` | quote selection + fallback | `quotes.py:27`, `routes/api.py` via QuoteView; `run_radar_ingest.py:38` (`classify_quality`) | **yes** — `QuoteView`, `classify_quality`, `from_snapshot` are the US quote contract | **SURGICAL**: literal `'us'`; USD only; remove fallback branch; `is_fallback` becomes constant False (contract decision, §4) |
| `features/radar/quotes.py:65-93` `_stored_quote` (Xetra/XETR/EUR defaults); `:95-156` `quote_views_for` (queries both markets, DE fallback rule); `:102,112,120,135,147` | quote read path | `leaderboard.py:445,531`, `detail_panel.py:367` | **yes** — same function serves US boards | **SURGICAL**: single-market US read; drop non-US defaults; keep `_quote_matches` NULL-market compatibility (legacy US rows have `market IS NULL`) |
| `features/radar/history.py:24-32` `CLOSE_SOURCE_PRIORITY['deutsche_boerse_delayed']`; `:234-257` `_sibling_basis`; `:259-289` `_converted_basis`; `:292-325` `resolve_basis`; `HistoryBasis.converted_from` | close store + chart basis | `detail.py`, `leaderboard.py`, `run_radar_ingest.py`, `market_data.py`, backfill script | **yes** — `record_closes`, `closes_for`, `fetch_into_store`, `tickers_needing_history`, `due_instruments` are the US history writers/readers | **SURGICAL**: delete `_converted_basis` and the `fx` import; `resolve_basis` = native (+ optional market-agnostic sibling); `converted_from` always None (contract §4). Priority entry: delete (no writer remains; see §8) |
| `features/radar/leaderboard.py:115-157` `_quote_sigmas` DE branch; `:413-414,445,512,531` `market` param | ranking | `board.py:565`, `market_data.active_price_tickers` (`chatter_candidates`) | **yes** | **SURGICAL**: remove `market == 'de'` branch; keep batched US path |
| `features/radar/board.py:104-135` `Board.market/market_venue`; `:543-618` `board_mic`, `market_venue` string, `market=` param; `:253` `row.quote.market or 'us'` | board build | API, producer, observations | **yes** | **SURGICAL**: constants `'us'` / `'US markets'`; keep `market` field in payload (contract §4) |
| `features/radar/board_shared.py:353-377` `_selection_echo` (XGAT mic, "Tradegate-first Germany") | shared-board waiting echo | shared read path | **yes** | **SURGICAL** |
| `features/radar/board_keys.py:34` `KEY_VERSION=2`; `:67` market check `('us','de')`; `:151-159` | store key canon | producer/store | **yes** | **SURGICAL**: accept only `'us'`; **bump `KEY_VERSION`** so stored DE-keyed blobs are retired as unreadable rather than half-valid (hazard §8) |
| `features/radar/board_producer.py:72` `WARM_MARKETS` | warm 8 boards | `run_radar_board_producer.py` | **yes** | **SURGICAL**: `('us',)` |
| `features/radar/observations.py:70` `MARKETS`; `:129-132` `_queries` | archive both boards | `run_radar_ingest.py` job `radar_board_observations` (flag-gated) | **yes** | **SURGICAL**: `('us',)`; consider `SCHEMA_VERSION` note (§8) |
| `features/radar/detail.py:70-99` `Chart.currency/converted_from`; `:349-440` `intraday_chart_for` basis logic | detail chart | `detail_panel.py` | **yes** | **SURGICAL**: simplify to native basis; keep `currency` (always USD) |
| `features/radar/detail_panel.py:88,351,367,441` `market` param | panel | API | **yes** | **SURGICAL** (param stays `'us'`) |
| `features/radar/routes/api.py:50` `Query.market='de'`; `:248-263` `default_market`; `:273-275`; `:69-200` `_chart_sessions` (generic, mic-aware); `:215-240` `_quote` (`is_fallback`); `:350-352`; `:693,731-738` | API | all clients | **yes** | **SURGICAL** (contract in §4): default `'us'`; delete `default_market`; explicit non-`us` → 400 |
| `features/radar/routes/views.py:34-51,53-79` | HTML pages; BadQuery → default board | browsers | **yes** | keep (see §4 for `?market=de` HTML behaviour) |
| `features/radar/routes/operations.py:76` `market_data.ops_summary` | ops payload | admin | **yes** | unchanged; payload shape changes via `ops_summary` |
| `features/radar/routes/price_chart.py:50-54` | selected-price query | hub | **protected** | **SURGICAL**: `('us',)` only → `de` falls to `invalid_market` 400 (today 422 `unsupported_instrument`); update `tests/selected_price_unit/test_route_ops.py:63` deliberately |
| `features/radar/market_data.py` DE-only: `XETR_PRETRADE_LIMITS:50`, `Selected:55`, `CycleSummary:65`, `select_price:79`, `_mapped_decisions:106`, `_journal_upsert:133`, `_journal_trades:162`, `_advance_cursor:170`, `DE_COLLECT_MICS:197`, throttle `:204-220`, `downloads_last_24h:222`, `collect_german_cycle:240`, `_collect_channel:293`, `_record_cycle_row:491`, `materialize_native_closes:509`, `_all_decisions:567`, `_quote_for:999`, imports `:34` (`FeedRejected`), `VENUE_BY_MIC`, `MappingDecision` | German collector + native closes | `run_radar_ingest.py:730-762,1078-1085`, `scripts/report_radar_market_data_shadow.py`, `operations` | **yes** — same file holds `active_price_tickers:576`, `grouped_instrument_map:602`, `grouped_active_symbols_by_day:637`, `ingest_grouped_day:729`, `claim_post_close:865`, `ops_summary:907` | **SURGICAL**: delete DE half; `ops_summary` drops `cycles`, `mapping_generations`, `de_download_budget_24h` (frontend `Admin.tsx`/`types.ts` change with it) |
| `features/radar/instruments.py` (738 lines): everything except `_active_us_instruments:612` is Xetra/OpenFIGI mapping (`XETRA_*:29-32`, `VENUE_BY_MIC`, overrides `:36-46,191-228`, `decide_mapping:239`, generations `:346-574`, `map_xetra:581`, `_load_catalogs:622`, `_upsert_de_row:643`, `mapping_preview:682`, `refresh_mappings:703`) | DE instrument mapping | `run_radar_ingest.py:126-210,543`, `market_data.py` (`VENUE_BY_MIC`, `MappingDecision`) | `_active_us_instruments` is DE-mapping input only today, but is the natural seed for workstream B | **DELETE** module contents; keep `_active_us_instruments` only if B claims it (B boundary, §8) |
| `features/radar/prices/twelvedata.py:110-115` (`mic=mic_code or 'XNAS'`), `:139-195` `stock_catalog` (XETR/EUR filter) | quotes + catalog | catalog only via `CatalogFallbackProvider` (DE); quotes via `_legacy_de_poll` (DE) and `refresh_history` (US, legacy/shadow close source) | **yes** — `daily_closes`/history stays US | **SURGICAL**: delete `stock_catalog`; keep quote/history |
| `features/radar/prices/finnhub.py:140-170` `stock_catalog`, `FINNHUB_EXCHANGE_BY_MIC` | catalog | `CatalogFallbackProvider` only | **yes** — quotes/profile are the permanent US source | **SURGICAL**: delete `stock_catalog` |
| `features/radar/prices/yahoo.py:358` `currency = 'EUR' if mic_code == 'XETR'` | history identity check | `history.fetch_into_store`, `_yahoo_deep_tail`, backfill | **yes** — US history + selected-price uses `_identity_ok` | **SURGICAL**: USD only |
| `features/radar/prices/__init__.py:23-30` `QUOTE_SOURCES` / `CLOSE_SOURCES` contain `'deutsche_boerse_delayed'` | source vocabulary validators | `Quote.__init__`, `validate_close_source` | **yes** | **ARCHIVAL** (allowed residual: DB CHECK constraints name the value; keeping the Python set aligned with the immutable constraint is compatibility, not support). No writer will produce it. |
| `features/radar/retention.py:49-104` `prune_market_data`; `:126-141` DE-native exception in `_prune_daily_closes` | nightly deletes | `run_radar_ingest.py:1174` | **yes** — `_prune_daily_closes` bounds US grouped ingestion | **SURGICAL + RULING** (§8): scope close pruning to `market='us' OR market IS NULL`; stop pruning DE journal/cycle tables (or rule they are operational and may keep draining) |
| `features/radar/config.py:833-870` `price_provider_config` (`RADAR_DE_PRICE_MODE`), `:1060-1068` `DE_FILES_PER_CYCLE`, `DE_DOWNLOAD_BUDGET_24H`, `DE_THROTTLE_BACKOFF_SECONDS` | flags | daemon, market_data | **yes** — same function validates US provider/close source | **SURGICAL**: return 2-tuple; delete DE constants; decide env handling (§6) |
| `features/radar/scheduling.py:113` | comment only | — | US | keep |
| `run_radar_ingest.py`: `DE_QUOTE_LIMIT:70`, `DE_HISTORY_LIMIT:96`, `_german_quote_sample:109`, `probe_german_data:124`, `_mapping_provider:138`, `_scheduled_mappings:146`, `_build_mapping_generation:172`, `_xetra_history_instruments:473`, `_mapping_refresh_due:482`, `poll_quotes:512` + `_scheduled_quotes:558` (**unreachable**: no scheduler registration; test-only callers `tests/test_radar_daemon.py:221-281`), `_current_de_generation_id:673`, `_legacy_de_poll:687`, `_de_should_collect:700`, `_scheduled_de_market_data:730`, `refresh_de_history:943`, `_yahoo_de_history_provider:969`, `refresh_ecb_rates:975`, `_scheduled_ecb_fx:988`, `_scheduled_history:1053` DE parts (`:1072-1085`), CLI flags `:1282-1295`, job registrations `:1380-1401`, import `fx:34` | daemon | systemd `radar_ingest` | **yes** — US cycle, grouped closes, history, profiles, volatility, prune, sentiment live in the same file | **SURGICAL**: delete listed symbols; `_scheduled_history` keeps `refresh_history` + `_yahoo_deep_tail`; remove three job registrations |
| `models.py:546-598` `RadarInstrument` (CHECK `market IN ('us','de')`, `mapping_generation_id` FK); `:875-947` `RadarQuote` (market/source CHECKs); `:950-996` `RadarDailyClose`; `:999-1031` `RadarFxRate`; `:1034-1060` `RadarMappingGeneration`; `:1063-1083` `RadarMarketDataCursor`; `:1086-1129` `RadarMarketDataCycle`; `:1132-1167` `RadarMarketTradeEvent`; `:1212-1225` `RadarProviderSessionState` | ORM | everywhere | shared tables are US storage | **ARCHIVAL** for all (§5). Docstrings may be re-worded to say "archival"; no column/constraint edits |
| `migrations/versions/a4c8e2f19b70`, `f5a8c2d91e30`, `d4e7a1b93c25`, `6a21d4e8c9f0` | DDL | chain | — | **ARCHIVAL / immutable** |
| `features/radar/data/german_instrument_overrides.json` (`{"overrides": []}`) | override input | `instruments.load_overrides` | none | **DELETE** with `instruments.py` |
| `features/radar/data/ordinary_words.txt:2408 'de'`, `:3128 'ecb'` | extraction stop-word list | extraction | unrelated | **OOS** (allowed residual: word list) |
| `app.py:169-170` comment "no good German half" | Gym/language comment | — | — | **OOS** |
| `features/radar/PRODUCT.md:28`, `PRODUCT.md:26,111` | Gym UI language notes | — | — | **OOS** |

### 2b. Scripts, fixtures, deploy

| Path | Role | Reachability | Disposition |
|---|---|---|---|
| `scripts/backfill_radar_fx.py` | ECB history backfill | operator-run | **DELETE** |
| `scripts/capture_deutsche_boerse_contract.py` + `tests/test_capture_deutsche_boerse_contract.py` (17 tests) | offline DBAG contract capture | operator-run; evidence already in `docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md` | **DELETE** (spec: obsolete source-specific probes leave active tooling; the captured contract document stays as history) |
| `scripts/backfill_radar_market_history.py:8,14,50-56,84-96` `--market de` mode | Yahoo `.DE` backfill | operator-run | **SURGICAL**: keep `us` and `us-universe`; delete `de` |
| `scripts/report_radar_market_data_shadow.py:6,95-298,564-596,629` `--gate german`, `_german_gates`, `_active_generation` | activation report | operator-run | **SURGICAL**: keep `--gate us-closes` (`_grouped_gate:310`) — it is the grouped-close activation evidence tool; delete German gate. `tests/test_radar_market_data_report.py` (17) converts |
| `scripts/seed_radar_universe.py`, `refresh_corpus_instruments.py` | US universe / corpus | — | keep (no DE) |
| `tests/fixtures/radar_market_data/{xetr,xgat}_{pre,post}trade.json`, `reference_tradegate_index.html`, `reference_xetr.csv`, `reference_xfra.csv` | DBAG/reference fixtures | DE tests only | **DELETE** with their suites |
| `deploy/radar-encoder-trial.{service,timer}` | encoder | — | **OOS** |
| systemd units `radar_ingest`, `personal_apps_web`, board producer | not in repo | VPS | **OOS for edits**; note the ingest unit restarts with the new job set; no unit file change needed |
| `requirements.txt` | deps | — | no DE-only package: ECB uses stdlib `xml.etree`, DBAG uses `gzip`/`json`/`requests` (shared). **Nothing becomes unused.** |
| `docs/superpowers/{plans,specs}/2026-08-28-radar-german-market*.md`, `2026-08-31-radar-deutsche-boerse-feed-contract.md`, `2026-08-31-radar-market-data-v2*.md`, `2026-09-01-radar-xetra-history-proxy-mapping-fix*.md`, `2026-09-04/05-radar-price-chart-basis*.md` | historical evidence | — | **OOS** (immutable history; allowed residual) |

### 2c. Frontend (`static/radar/src/`)

| Path : symbol | Role | Disposition |
|---|---|---|
| `board/MarketSwitch.tsx` (whole) | legacy board radio | **DELETE**; remove import/use in `list/ListPane.tsx:5,630` |
| `hub/Filters.tsx:33-36` `MARKETS`; `:85-96` select; `:252-257` `summariseAll` | hub selector | **SURGICAL** |
| `hub/Hub.tsx:233-239` context by market; `:295` `MARKET_NAME`; `:698-702` | top bar | **SURGICAL** (constant "US markets") |
| `types.ts:60` `Market`; `:74-80` `MarketQuote.market/venue/mic/currency`; `:93-99` `is_fallback`; `:132-139` `chart.currency/basis_venue/converted_from`; `:210,305-308,436` `market`, `market_venue`; `:513-540` `OpsPayload.market_data` (`cycles`, `mapping_generations`, `de_download_budget_24h`) | contract types | **SURGICAL** per §4 |
| `api.ts:58-60,173` `params.set('market', selection.market)` | request | **SURGICAL**: either always `'us'` or omit (§4) |
| `embedded.ts:38-43` `market: board.market === 'de' ? 'de' : 'us'` | embedded payload coercion | **SURGICAL** |
| `hub/navigation.ts:149,232` `pick<Market>(..., ['us','de'], ...)` | URL parsing | **SURGICAL**: no market key, or accept only `us` |
| `hub/queries.ts:53,76,735-779` market in keys; `market === 'us'` gate | cache keys | **SURGICAL** |
| `hub/priceChart.ts:343` `params.set('market','us')` | selected price | **protected**, keep |
| `hub/ResearchContent.tsx:82` `selection.market === 'us'`; `:233` currency label; `:295-307` price/venue/"fallback listing"; `:442-469` copy "window and market"; `:501-505` `formatPrice` EUR `€` branch | research pane | **SURGICAL** |
| `hub/Overview.tsx:50,258-264`; `hub/Chatter.tsx:536-548,769,807-811,826,863,907`; `hub/CandidateList.tsx:180,240-244`; `hub/Watching.tsx:55,150,248-252` | duplicated `formatPrice` with `€`; "grouped by currency … rather than converted" caption; `market_venue` captions | **SURGICAL**: delete EUR branches; `market_venue` may stay as server-provided text |
| `hub/chatterSort.ts:73-98,140` currency grouping | sort | **SURGICAL** (single currency; grouping collapses) |
| `hub/Admin.tsx:100-135` "German download budget", cycles table, mapping generations | ops panel | **SURGICAL** (mirror `ops_summary`) |
| `QuoteBadges.tsx:17-20` "US fallback · …"; `:31` `currencyLabel` | badges | **SURGICAL** |
| `list/TickerRow.tsx:288-302` fallback fact; `list/ListPane.tsx:195-215` German-board caption comment | list | **SURGICAL** |
| `detail/Identity.tsx:61` `explicitCode: quote.is_fallback` | identity | **SURGICAL** |
| `detail/PriceChart.tsx:59-65` "converted to … ECB", `:82,131-132,227` currency | chart | **SURGICAL**: drop converted branch; `money(..., 'USD')` |
| `format.ts:274-282` `money` EUR sign; `:284-294` `formatPrice(currency)` (Intl, generic) | formatters | **SURGICAL**: remove `€` branch; `formatPrice` may keep a currency parameter but only `'USD'` is ever passed |
| `detail/DetailPane.tsx:135-195` market in stale-while-revalidate key and mismatch check | pane | **SURGICAL** |
| `fixtures.ts:89-98` `detail(ticker, market)` DE fixture text | test fixtures | **SURGICAL** |
| `static/radar/radar.css:393-420,1597` `.market-switch` | CSS | **DELETE** rules |
| `hub/hub.css:157`, `selected-price.css:4` | comments | keep |

---

## 3. Flow maps

### 3a. UI / API reads

```
Browser (hub)  Filters.tsx select / navigation.ts ?market= / api.ts params.set('market')
Browser (legacy /radar/legacy/)  MarketSwitch.tsx → BoardPage.tsx load()
        │
        ▼
routes/views.py hub_page/board_page → build_payload(request.args)   [BadQuery → default board]
routes/api.py  /api/board, /api/board (shared), /api/ticker/<t>
        parse_query(args): market = args.get('market') or default_market(now)   ← 'de' when US not exclusively live
        Query.market default 'de'
        │
        ├─ board_shared.read_payload → board_keys.canonical(query) [market in key] → store
        │        └─ miss → board_producer (WARM_MARKETS us+de) / _wait_for_a_build
        ├─ build_payload_direct → board.build(market) → session_state(market, mic='XGAT' if de)
        │        └─ leaderboard.build_rows(market) → quotes.quote_views_for(tickers, market)
        │                 ├─ RadarInstrument primaries for BOTH 'us' and 'de'
        │                 ├─ statuses_for / _stored_quote (Xetra/XETR/EUR defaults for non-US)
        │                 └─ markets.select_quote → DE primary, else US fallback (is_fallback=True)
        │            leaderboard._quote_sigmas → market=='de' → history.resolve_basis
        │                 └─ _native | _sibling | _converted_basis(fx.rate_series, convert_usd_to_eur)
        └─ detail_panel.build(market) → detail.intraday_chart_for(quote) → history.resolve_basis (same FX path)
                 serialize_detail: chart.currency / basis_venue / converted_from; identity.quote.is_fallback
        │
        ▼
Frontend render: QuoteBadges (US fallback label), PriceChart ("converted to EUR at the ECB daily rate"),
                 Overview/Chatter/CandidateList/Watching/ResearchContent formatPrice(EUR → €)
```

Selected-price (`/api/ticker/<t>/price-chart`) and HA1 (`/radar/api/analysis…`) branch off **before** `parse_query`'s market and pin `market='us'` in SQL: not on this map, protected.

### 3b. Ingestion / scheduling (`run_radar_ingest.py main()`)

| Job id | Interval | DE reach | US reach |
|---|---|---|---|
| `radar_us_quotes` | 5/15 min | none | Finnhub/Yahoo US cycle (protected) |
| `radar_de_market_data` | 5 min | `legacy` → `_legacy_de_poll` (Twelve Data DE); `shadow/active` → `collect_german_cycle` (DBAG XGAT) | none → **remove job** |
| `radar_us_grouped_closes` | 23:30 UTC | none | Massive grouped (protected) |
| `radar_ecb_fx` | 16:30 Berlin | ECB daily → `fx.record_rates` | none → **remove job** |
| `radar_mappings` | weekly (+2 min after restart under non-legacy) | Xetra mapping (`refresh_mappings`) or OpenFIGI generation | none (US instruments are never written here) → **remove job** |
| `radar_history` | 5 min | `refresh_de_history` (Yahoo `.DE`, every mode) + `materialize_native_closes` (non-legacy) | `refresh_history` (Twelve Data, legacy/shadow close) + `_yahoo_deep_tail` → **surgical** |
| `radar_volatility`, `radar_profiles`, `radar_scoring`, `radar_cycle`, `radar_reddit`, `radar_sentiment` | — | none | keep |
| `radar_prune` | 04:30 | `prune_market_data` (DE journal/cycles), `_prune_daily_closes` (deletes DE Yahoo closes older than horizon) | US close pruning → **ruling §8** |
| `radar_board_observations` | 15 min (flag) | captures `de` board | captures `us` → **surgical** |
| CLI `--probe-german-data`, `--refresh-mappings` | manual | DE | — → **delete** |

Board producer (`run_radar_board_producer.py` → `board_producer.warm_queries`): 8 warm boards = 2 markets × 2 segments × 2 windows → 4 after removal.

### 3c. Mappings / reference data

`RadarInstrument` rows: US rows were seeded by migration `a4c8e2f19b70` and are the identity for every US read/write; nothing in the active codebase creates or refreshes US instrument rows (this is the workstream-B gap: 146 identities without rows). DE rows are created only by `instruments._upsert_de_row` (legacy) or `_apply_generation` (v2), both scheduled through `radar_mappings`. Reference inputs: Twelve Data `/stocks` + Finnhub `/stock/symbol` catalogs (legacy), or `reference_universe` (DBAG CSVs + Tradegate crawl) + OpenFIGI (v2), plus `german_instrument_overrides.json` (empty). Removing `radar_mappings` and `instruments.py` leaves **no writer of DE instrument rows and no writer of any instrument row** — A must state this plainly rather than hide it (B boundary).

### 3d. FX / fallback

- FX write: `radar_ecb_fx` → `refresh_ecb_rates` → `fx.record_rates` → `radar_fx_rates`. Backfill: `scripts/backfill_radar_fx.py`.
- FX read: only `history._converted_basis` (`quote.currency == 'EUR'` gate) → `fx.rate_series` / `convert_usd_to_eur`. Consumers: `resolve_basis` → `leaderboard._quote_sigmas` (DE branch) and `detail.intraday_chart_for` (any span; gated by quote currency). With no EUR quote ever selected, the branch is dead; delete it and `fx.py` together.
- US-fallback: `markets.select_quote(allow_us_fallback)` ← `quotes.quote_views_for` ← DE requests only. Frontend surfaces listed in §2c.
- Non-US defaults hidden in shared code: `quotes._stored_quote` ('Xetra','XETR','EUR'), `twelvedata._quote` (`mic_code or 'XNAS'`), `yahoo.daily_closes` (`'EUR' if XETR`), `history.record_closes` defaults (`market='us'`, `currency='USD'` — fine).

---

## 4. API / frontend contract delta

**Board / shared board / detail (`parse_query`)**

| Input | Today | Required |
|---|---|---|
| no `market` | `default_market(now)` → `de` most of the day | `'us'` |
| `market=us` | ok | ok (keep accepting; the protected selected-price client sends it explicitly, `priceChart.ts:343`) |
| `market=de` | ok, German board | `400 {"error": "unsupported market"}` (BadQuery). Not a redirect, not normalization |
| `market=xx` | `400 unknown market` | unchanged |

Implementation: `Query.market: str = 'us'`; `parse_query`: `market = args.get('market') or 'us'; if market != 'us': raise BadQuery('unsupported market')`; delete `default_market`. `board_keys.canonical` accepts only `'us'` and `KEY_VERSION` is bumped. `board_producer.WARM_MARKETS`/`observations.MARKETS` → `('us',)`.

**HTML pages** (`views.py`): `?market=de` on `/radar/` or `/radar/legacy/` currently falls back to the default board because BadQuery is swallowed for humans; after the change the default board *is* the US board, so a bookmarked German link opens US without an error page. This is existing documented behaviour for address-bar typos and satisfies "no silent normalization" at the API layer; Mastermind may prefer a visible notice — decision, not a research finding.

**Selected-price** (`price_chart.py:50-54`): allowed set `('us',)`; `market=de` → `400 invalid_market` (today `422 unsupported_instrument`). `tests/selected_price_unit/test_route_ops.py:63` must be updated deliberately. `market` remains **required** on this endpoint (unchanged).

**Payload fields** — recommended shape (keep keys, freeze values) so clients and the observation archive schema do not break:

| Field | Today | Recommendation |
|---|---|---|
| `market` (board, detail) | `us`/`de` | keep, always `us` |
| `market_venue` | "US markets" / "Tradegate-first Germany" | keep, always "US markets" |
| `identity.quote.market/venue/mic/currency` | per selected venue | keep; currency always `USD` |
| `identity.quote.is_fallback` | bool | keep, always `false` **or** drop; frontend must stop rendering the label either way |
| `chart.currency` | USD/EUR | keep, always `USD` |
| `chart.basis_venue` | venue string | keep (native venue) |
| `chart.converted_from` | `USD`/null | keep, always `null` **or** drop with type change |
| `market_data_ops.cycles`, `.mapping_generations`, `.de_download_budget_24h` | present | **drop** (frontend `Admin.tsx` + `types.ts OpsPayload` change in the same commit) |
| `market_data_ops.grouped_closes`, `.post_close_claims`, `.quote_basis_24h` | present | keep |

Frontend `Selection.market`: remove (or type as `'us'` literal). `navigation.ts` stops reading/writing `market`; `api.ts` omits it or sends `us`. `queries.ts` keys drop market. `embedded.ts` stops coercing. `MarketSwitch`, `Filters` market select, `Hub` `MARKET_NAME`, all `€` branches, fallback labels, "converted to EUR" text, German ops panel: removed.

---

## 5. Historical-data / schema compatibility

What remains, and why it is compatibility rather than support:

| Object | Remains? | Why |
|---|---|---|
| `radar_instruments.market` CHECK `('us','de')`, `mapping_generation_id` FK, `mapping_source` | yes | column/constraint of a live US table; DE rows exist; the ORM must match the DB to read US rows |
| `radar_quotes.market/mic/currency/provider_symbol/source/price_basis/bid/ask/is_shadow` + CHECKs naming `'de'` and `'deutsche_boerse_delayed'` | yes | same table stores US quotes; constraints are DDL from immutable migrations |
| `radar_daily_closes` same | yes | same |
| `radar_fx_rates` table + `RadarFxRate` model | yes, ORM class kept | rows exist; no reader after `fx.py` deletion. Keeping the model avoids an autogenerate that would propose `DROP TABLE` |
| `radar_mapping_generations`, `radar_market_data_cursors`, `radar_market_data_cycles`, `radar_market_trade_events` + models | yes, ORM classes kept | same reasoning; no reader/writer after removal |
| `radar_provider_session_states` | yes | shared; US post-close claim uses `(source, market='us')` |
| `history_due_at` on `radar_instruments` | yes | US history scheduling uses it |
| Migrations `a4c8e2f19b70`, `f5a8c2d91e30`, `d4e7a1b93c25`, `6a21d4e8c9f0` | untouched | immutable |

Inertness guards required (all read filters already exist for the protected paths; these are the shared ones):

- `quotes._quote_matches` / `statuses_for` / `moves_for`: query only `market == 'us' OR (market IS NULL AND mic IS NULL)`; never build a `'de'` identity list.
- `history._market_filter` / `closes_for` / `tickers_needing_history`: callers pass `market='us'` only; `_sibling_basis` filter `market == quote.market` stays US.
- `leaderboard`, `board`, `detail`: `market='us'` constant.
- `retention._prune_daily_closes`: add `market == 'us' OR market IS NULL` so DE rows are neither read nor deleted (ruling §8).
- `market_data.ops_summary`: stop reading `RadarMarketDataCycle` / `RadarMappingGeneration`.
- No writer: after removing `radar_mappings`, `radar_de_market_data`, `radar_ecb_fx`, `refresh_de_history`, `materialize_native_closes`, `backfill_radar_fx.py`, `backfill … --market de`, nothing constructs a `Quote`, close, instrument, generation, cursor, cycle, event or FX row with `market='de'`/`EUR`.

Not authorized and not recommended here: dropping tables, narrowing CHECKs, deleting rows, editing migrations. A future contraction migration is a separate retention decision.

DB-compatibility check the Implementer can run without touching production: apply the full migration chain to a fresh SQLite/MariaDB test database, then `flask db migrate --dry-run`-equivalent (autogenerate compare) must show **no** diff; existing `tests/test_radar_migration.py` (18 tests, DE fixtures) continues to pass unchanged.

---

## 6. Scheduler / config / operations / deployment cleanup map

| Item | Action |
|---|---|
| Jobs `radar_de_market_data`, `radar_ecb_fx`, `radar_mappings` | remove registrations and functions |
| Job `radar_history` | keep; remove DE half |
| Job `radar_prune` | keep; see ruling §8 |
| Job `radar_board_observations` | keep; single market |
| CLI `--probe-german-data`, `--refresh-mappings` | remove |
| `RADAR_DE_PRICE_MODE` | stop reading. Production `.env` **contains the name** (release journal). Recommendation: ignore the variable (optionally log once "ignored, German mode removed"); do **not** refuse startup on its presence, or the next deploy fails until the owner edits `.env`. Env cleanup is a separate owner-authorized step |
| `OPENFIGI_API_KEY` | becomes unused (only `prices/openfigi.py:… os.getenv`) ; leave in `.env` until owner cleanup |
| `RADAR_US_PRICE_PROVIDER`, `RADAR_US_CLOSE_SOURCE`, `RADAR_MASSIVE_API_KEY`, `RADAR_US_CLOSE_*` evidence trio | keep (US) |
| `DE_FILES_PER_CYCLE`, `DE_DOWNLOAD_BUDGET_24H`, `DE_THROTTLE_BACKOFF_SECONDS` (`config.py`) | delete |
| Ops payload `/radar/api/ops` → `market_data` | drop DE keys; `Admin.tsx` panel "German download budget", cycles table, mapping generations removed |
| Logs | log lines `radar de quotes …`, `radar de collection …`, `radar ECB …`, `radar mapping …`, and the `de_yahoo/de_empty/de_native` fields of `radar history …` disappear; no metrics scrape depends on them in-repo |
| Scripts | delete `backfill_radar_fx.py`, `capture_deutsche_boerse_contract.py`; trim `backfill_radar_market_history.py` and `report_radar_market_data_shadow.py` |
| Deployment units | no unit-file change; `radar_ingest` restart picks up the new job set; `personal_apps_web` restart + frontend build for the hub bundle (`DEPLOY_FRONTEND.md`) |
| Board store | bumping `KEY_VERSION` retires stored blobs; producer re-warms 4 US keys on first cycle |

---

## 7. Test disposition matrix and acceptance gates

Counts are `pytest --collect-only` (backend) or grep test-name/hit counts (frontend); no suite was executed.

**DE-only suites → DELETE with their modules** (collected total of the group below incl. shared: 295)

| Suite | Tests | Protects |
|---|---|---|
| `tests/test_radar_deutsche_boerse.py` | 22 | `prices/deutsche_boerse.py` |
| `tests/test_radar_ecb.py` | 7 | `prices/ecb.py` |
| `tests/test_radar_fx.py` | 7 | `fx.py` |
| `tests/test_radar_calendar_de.py` | 11 | `market_calendars/de.py`, `tradegate.py` |
| `tests/test_radar_reference_universe.py` | 28 | `reference_universe.py` |
| `tests/test_radar_openfigi.py` | 24 | `prices/openfigi.py` |
| `tests/test_radar_instruments.py` | 22 | `instruments.py` |
| `tests/test_radar_history_basis.py` | 11 | sibling/converted basis (keep any native-only case as US regression) |
| `tests/test_capture_deutsche_boerse_contract.py` | 17 | capture script |
| `tests/fixtures/radar_market_data/*` | — | above |

**Shared suites → CONVERT (delete DE cases, keep US, add rejection cases)**

| Suite | Tests | DE-flavoured cases (by name) | Note |
|---|---|---|---|
| `tests/test_radar_market_data.py` | 47 | collector/cycle/throttle/budget/native-close/`de_backfill` cases (~15) | keep grouped-close cases incl. `test_grouped_ingest_never_touches_a_german_row` (rename or keep as REJECT-TEST: DE instrument rows must stay invisible to grouped writes) |
| `tests/test_radar_market_data_report.py` | 17 | German gate | keep `us-closes` gate cases |
| `tests/test_radar_daemon.py` | 69 | `test_german_*` (4), ECB (3), mapping (8), `test_the_five_market_data_jobs_…` (assert job set → three jobs), `test_scheduled_history_always_runs_the_bounded_yahoo_xetra_queue`, `poll_quotes` cases (unreachable code) | assert `radar_de_market_data`/`radar_ecb_fx`/`radar_mappings` are **absent** (REJECT-TEST) |
| `tests/test_radar_markets.py` | 18 | DE selection/fallback cases | add: `select_quote` refuses non-`us`; USD-only |
| `tests/test_radar_quotes.py` / `_batch.py` | 26 / 9 | `test_mapped_de_primary_with_dead_feed_never_falls_back_to_us`, `test_explicit_market_windows_never_read_another_venue` | rewrite as "DE rows in `radar_quotes` are never read for a US identity" (REJECT-TEST) |
| `tests/test_radar_history.py` | 28 | `test_german_history_…`, `test_native_close_cannot_be_overwritten_by_yahoo`, `test_the_basis_takes_the_deeper_venue_whole` | keep NULL-market compatibility cases |
| `tests/test_radar_detail.py` | 62 | `test_a_converted_basis_…`, `test_a_german_intraday_chart_…`, `test_germany_detail_marks_us_fallback_…`, `test_a_quote_only_eur_week_…`, `test_a_week_anchors_an_xgat_primary_…`, `test_chart_carries_its_basis_…` | keep US basis/venue cases |
| `tests/test_radar_leaderboard.py` | 49 | `test_germany_row_uses_a_marked_us_quote_fallback`, `test_eod_german_quote_cannot_produce_divergence`, `test_german_quote_does_not_use_the_us_cached_sigma` | — |
| `tests/test_radar_api.py` | 56 | `default_market` param cases (`:53-82`), `test_board_echoes_market…` (`market=de` → 200 today), `test_intraday_chart_at_xetra_premarket_end…`, `:877 span=1M&market=de`, `test_panel_chart_states_its_basis` | add REJECT-TEST: omitted → `us`; `market=de` → 400; `market=us` → 200 |
| `tests/test_radar_board_parity.py` | 9 | entire suite is a US/DE parity harness incl. `default_market` clocks | rewrite as US-only parity or delete; decide in plan |
| `tests/test_radar_board_shared_api.py` | 34 | `:209-219` DE echo, `:564`, `:849` warm keys `['us','de']`, `:1033-1036` | convert |
| `tests/test_radar_observations.py` | 23 | `:131,163,197,218-223` two-market pair | convert to single market |
| `tests/test_radar_hub_page.py` | 11 | `:90-120` shell market `de` | convert: `?market=de` → default US shell |
| `tests/test_radar_board.py` | 34 | `:126 _next_boundary('de', …)` | one case |
| `tests/test_radar_yahoo.py`, `test_radar_prices.py` | 13 / 21 | `test_xetr_instrument_accepts_german_metadata`, XETR quote/catalog cases, `test_radar_prices.py:36-58` DE default fixture | convert fixtures to US |
| `tests/test_radar_calendar.py` | 17 | `:42-70` `de` bounds cases | keep US; add REJECT-TEST: `session_state('de', …)` raises `ValueError` |
| `tests/test_radar_operations_api.py` | 25 | `:371` monkeypatch of `collect_german_cycle` | drop that patch |
| `tests/test_radar_quote_retention.py` | 12 | `:159-175` dual-market retention, `:217` native exception | rewrite per §8 ruling |
| `tests/test_radar_models.py` | 25 | DE-row model cases (`:201-215,274,409-415`) | **KEEP** as ARCHIVAL proof the ORM still reads/represents DE rows (they exercise model shape, not product behaviour) |
| `tests/test_radar_migration.py` | 18 | DE fixtures through up/down | **KEEP** unchanged (immutable migrations) |
| `tests/test_scripts.py` | 7 | `:280 test_sums_the_week_in_german` is Gym | OOS |

**Protected suites → must stay green, with one deliberate edit**

| Suite | Collected | Note |
|---|---|---|
| `tests/selected_price_unit/` + `tests/ha1_unit/` + `tests/test_radar_massive.py` | 515 | `selected_price_unit/test_route_ops.py:63` expects `422 unsupported_instrument` for `market=de` → becomes `400 invalid_market`; `test_reader.py:59-62`, `test_window.py:259`, `test_normalize.py:141`, `ha1_unit/test_analysis_contract.py:190-225`, `test_analysis_reader.py:126-200` use `market='de'`/`currency='EUR'` rows as **rejection fixtures** → KEEP (REJECT-TEST) |

**Frontend (Vitest)** — files with DE cases: `board/BoardPage.test.tsx` (Germany radio flows, ~6 cases), `QuoteBadges.test.tsx` (3), `detail/PriceChart.test.tsx` (3), `hub/state.test.tsx` (3), `hub/navigation.test.ts` (5), `hub/Hub.test.tsx` (2), `hub/Chatter.test.tsx` (3), `hub/chatterSort.test.ts` (3), `format.test.ts` (2), `embedded.test.ts` (2), `hub/pending.test.tsx` (1), `hub/queries.test.ts` (2), `list/TickerRow.test.tsx` (2), `hardening.test.tsx` (1 converted-basis case), `hub/SelectedPriceSection.test.tsx` (1 `de` parameter). Convert; add: no market control rendered; `?market=de` in the URL yields the US selection; `formatPrice`/`money` never print `€`.

**Acceptance gates (proposed)**

1. Backend: full Radar pytest green; `tests/selected_price_unit tests/ha1_unit tests/test_radar_massive.py` 515 collected → all pass with exactly the one deliberate expectation change.
2. New REJECT-TESTs pass: API omitted→us, `market=de`→400 (board, shared, detail), price-chart `market=de`→400, `session_state('de')`→ValueError, daemon job set excludes the three DE jobs, `quote_views_for` never returns a non-USD quote even when DE rows exist in the test DB, `_prune_daily_closes` leaves a seeded DE row untouched.
3. Frontend: `tsc` 0, `npm run build` ok, Vitest green (28 pre-existing `pending.test.tsx` failures noted in HANDOFF are a known baseline, to be re-stated by the Implementer).
4. Static residual search (§9) returns only allowed categories.
5. Autogenerate diff empty against the migrated schema.
6. Local US-only smoke: hub shell renders `market: 'us'`, no market control, admin ops panel without German block.

---

## 8. Shared-code hazards and ordering constraints

1. **Retention already touches DE rows — ruling needed.** `_prune_daily_closes` deletes any close older than the horizon whose `source != 'deutsche_boerse_delayed'`, which includes DE Yahoo closes; `prune_market_data` drains `radar_market_trade_events` (48 h) and `radar_market_data_cycles` (14 d) nightly. Spec says historical rows are not deleted. Options: (a) scope close pruning to `market='us' OR market IS NULL` and drop the DE-journal pruning call (rows become inert and stop shrinking); (b) rule that operational journal/cycle tables are not "historical price data" and may keep draining. Recommend (a) for closes, Mastermind's call for the journal tables.
2. **`default_market` removal is coupled to calendar removal.** `default_market` calls `session_state('de', …)`; deleting `de.py` before rewriting `parse_query` breaks every board request. Do API contract and calendar registry in one slice.
3. **Board store keys.** Stored blobs carry `market` in `key_json`; `query_from_json` will raise `BadKey` on `'de'` once the check narrows. Bump `KEY_VERSION` so old keys are rejected by version, not by a field error; the producer re-warms. Verify no reader enumerates stored keys expecting all to parse.
4. **Observation archive shape.** `payload_json` becomes `{'us': …}` instead of `{'us': …, 'de': …}` and `selections_json.queries` likewise. Consider `SCHEMA_VERSION = 2` so analysts can distinguish; old rows untouched.
5. **`ops_summary` and `Admin.tsx`/`types.ts` must change together**, or the admin page renders `undefined` fields.
6. **`market_calendars.session_state(market, when, mic=)`** keeps its signature; callers pass US MICs (`XNAS`, `XNYS`) which the registry ignores today and must continue to ignore (no `ValueError` for a US MIC).
7. **`prices/__init__.py` source sets vs DB CHECKs**: keep `'deutsche_boerse_delayed'` in `QUOTE_SOURCES`/`CLOSE_SOURCES` (archival) or the residual grep must allow it; removing it is also safe because no code constructs such a `Quote` after removal, but `_stored_quote` would raise if a DE row were ever read — which the filters prevent. Recommend keep (allowed residual, documented).
8. **`instruments.py` and workstream B.** After A, no code creates instrument rows at all. A's ledger must state "146 US identities remain unmapped; A removed the DE mapper and added no US mapper". If B wants `_active_us_instruments`, keep that one function in a slimmed module.
9. **`test_radar_board_parity.py`** encodes `default_market` clocks; it will fail en bloc. Decide rewrite-vs-delete in the plan, not ad hoc.
10. **Twelve Data stays.** It is still the US history writer under `RADAR_US_CLOSE_SOURCE=legacy|shadow` (`_scheduled_history`) — only its `stock_catalog` and the DE quote poll go. Do not remove the provider module.
11. **Yahoo `.DE` suffixing** exists in two places (`run_radar_ingest.py:952-955`, backfill script `:84-86`); both go with their DE callers.
12. **Unreachable legacy `poll_quotes`/`_scheduled_quotes`** are test-only; deleting them removes 4 daemon tests that assert nothing about production.
13. **Frontend `Selection` type** is threaded through navigation, queries, DetailPane, ResearchContent, Filters, Hub, BoardPage; removing the field is a compile-checked refactor — rely on `tsc`.
14. **Ordering**: (1) backend contract + calendar + store keys + producer/observations; (2) quote/history/leaderboard/detail read path + `fx.py`; (3) daemon/config/market_data/providers/instruments/reference/retention; (4) scripts/fixtures; (5) frontend + ops types; (6) residual sweep and gates. Slices 2–4 are mutually independent after slice 1; slice 5 depends on 1 and on the `ops_summary` change in 3.

---

## 9. Residual-search checklist (post-edit)

Run from `personal_apps/` (ripgrep; exclude `node_modules`, `__pycache__`, `static/radar/dist`, `scratchpad`, `artifacts`):

```
rg -n -i "deutsche|boerse|börse|xetra|xetr|xgat|frankfurt|xfra|tradegate|\becb\b|eurofxref|openfigi|figi" --glob '!migrations/**' features run_radar_ingest.py scripts static/radar/src templates
rg -n "'de'|\"de\"|market=de|Market = |\bEUR\b|€|\\u20ac|convert_usd_to_eur|converted_from|is_fallback|allow_us_fallback|default_market|RADAR_DE_|DE_[A-Z_]+ =|radar_de_|radar_ecb|radar_mappings|refresh_de_|_german|german_|_de_|probe-german|refresh-mappings" --glob '!migrations/**' features run_radar_ingest.py scripts static/radar/src static/radar/radar.css
rg -n -i "german|germany" --glob '!migrations/**' features run_radar_ingest.py scripts static/radar/src tests
rg -n "market IN \('us', 'de'\)|deutsche_boerse_delayed|radar_fx_rates|radar_mapping_generations|radar_market_data_|radar_market_trade_events" models.py migrations
```

Allowed remaining references, each must fit one category:

| Category | Expected residuals |
|---|---|
| A. Immutable migration/history | everything under `migrations/versions/`; `docs/superpowers/**`; `radar-design/**` |
| B. Archival schema compatibility | `models.py`: CHECK constraint strings, `RadarFxRate`, `RadarMappingGeneration`, `RadarMarketDataCursor`, `RadarMarketDataCycle`, `RadarMarketTradeEvent`, `RadarInstrument.mapping_generation_id`, docstrings marked archival; `prices/__init__.py` source-name sets; `tests/test_radar_models.py`, `tests/test_radar_migration.py` DE fixtures |
| C. Intentional rejection tests | `market='de'`/`currency='EUR'` fixtures in `tests/selected_price_unit/`, `tests/ha1_unit/`, and the new REJECT-TESTs in `test_radar_api.py`, `test_radar_calendar.py`, `test_radar_daemon.py`, `test_radar_quotes.py`, `test_radar_market_data.py`, `test_radar_quote_retention.py` |
| D. Unrelated vocabulary | `features/radar/data/ordinary_words.txt` tokens `de`, `ecb`; `format.ts` `de-DE` **locale** for Berlin clock formatting (`formatMarketTime`, `formatPrice` Intl locale — a locale, not a market); `Europe/Berlin` timezone strings; `tests/test_scripts.py::test_sums_the_week_in_german` (Gym) |
| E. Out-of-scope products | Gym German UI (`features/gym/**`, `templates/gym/**`, `static/gym/**`, `PRODUCT.md`), `app.py:169-170` comment |
| F. Retention exception (only if ruling keeps it) | `retention.py` `'deutsche_boerse_delayed'` guard |

Anything else is a defect. Reviewer additionally confirms: no scheduler job id starting `radar_de`/`radar_ecb`/`radar_mappings`; no `os.getenv('RADAR_DE_PRICE_MODE')`; `market_calendars/` contains only `__init__.py` and `us.py`; `prices/` contains no `deutsche_boerse.py`, `ecb.py`, `openfigi.py`; no `fx.py`, `reference_universe.py`; `tests/fixtures/radar_market_data/` gone; frontend bundle contains no "Germany", "Xetra", "Tradegate", "ECB", "€".

---

## 10. Recommended implementation slices (planning inputs only)

| Slice | Content | Evidence anchors | Gate |
|---|---|---|---|
| A1 API contract + clocks + stores | `routes/api.py` Query/parse_query/default_market; `market_calendars/__init__.py` US-only (+ delete `de.py`, `tradegate.py`); `board.py`, `board_shared.py` constants; `board_keys.py` (KEY_VERSION bump); `board_producer.WARM_MARKETS`; `observations.MARKETS`; `price_chart.py` allowed set; tests: api, board, board_shared_api, parity, observations, hub_page, calendar, selected_price `test_route_ops.py:63` | §2a, §4, §8.2-4 | REJECT-TESTs 1-3 of §7 |
| A2 Quote/history read path | `markets.py`, `quotes.py`, `history.py` (delete `_converted_basis`, `fx` import), delete `fx.py`, `leaderboard._quote_sigmas`, `detail.py`, `detail_panel.py`; tests: markets, quotes, quotes_batch, history, history_basis (delete), detail, leaderboard, fx (delete) | §3a, §3d | no non-USD quote/close ever surfaces with DE rows seeded |
| A3 Daemon/config/providers/mapping/retention | `run_radar_ingest.py` symbols + jobs + CLI; `config.py` flags/constants; `market_data.py` DE half + `ops_summary`; delete `prices/deutsche_boerse.py`, `prices/ecb.py`, `prices/openfigi.py`, `reference_universe.py`, `instruments.py` (B boundary), overrides JSON; `twelvedata`/`finnhub` `stock_catalog`; `yahoo.py:358`; `retention.py` per ruling; tests: daemon, market_data, deutsche_boerse/ecb/openfigi/reference_universe/instruments (delete), yahoo, prices, quote_retention, operations_api | §3b, §3c, §6, §8.1,8.7,8.8,8.10 | job set + env handling + autogenerate diff empty |
| A4 Scripts/fixtures | delete `backfill_radar_fx.py`, `capture_deutsche_boerse_contract.py` (+test), fixtures; trim backfill `--market de`, shadow report German gate; tests: market_data_report | §2b | scripts import clean |
| A5 Frontend | types, Selection, navigation, api, embedded, queries, Filters, MarketSwitch (delete), Hub, ListPane, QuoteBadges, TickerRow, Identity, ResearchContent, Overview, Chatter, CandidateList, Watching, chatterSort, PriceChart, DetailPane, Admin, format, fixtures, radar.css; Vitest files in §7 | §2c, §4 | tsc/build/vitest; visual check of hub top bar, admin panel, detail chart caption |
| A6 Residual sweep + closure | §9 checklist; ledger statement of B gap; env cleanup carry (`RADAR_DE_PRICE_MODE`, `OPENFIGI_API_KEY`) as owner-authorized follow-up | §6, §9 | all residuals categorized |

Estimated blast radius: ~20 backend modules edited, 8 deleted; ~25 frontend files edited, 1 deleted; ~10 test files deleted, ~20 converted; 0 migrations; 0 dependency changes.

---

## 11. Actions confirmation

- No application, test, migration, script, configuration, dependency or environment file was edited.
- No database read or write, schema change, generated migration or historical migration edit.
- No file deleted or moved; no formatter run; no commit, push, deployment or service change.
- No provider/network request; no credential or `.env` value read (variable names only, from an already committed release journal).
- No subagents.
- Only `pytest --collect-only` was run (two invocations, offline; 295 and 515 tests collected respectively). `git` inspection commands used per-command `-c safe.directory='*'`.
- Files created: this return. Files updated: current-status sections of `radar-design/A-US-USD-ONLY-LEDGER.md` and root `HANDOFF.md` (historical text preserved).
- Pre-existing dirty tracked files (8 continuity documents) and untracked artifacts were not touched.

Evidence attribution: every code fact above is from fresh worker reads/greps of HEAD 38591e0 in this worktree. Production counts (2,517 DE-mapped tickers, 3,229 DE instrument rows, 12,599 mapped US) and production flag names are quoted from repository documents (`US-USD-ONLY-DECISION.md`, `US-UNIVERSE-REFRESH-2026-09-16.md`, release journal), not re-measured. The "28 pre-existing Vitest failures" baseline is quoted from `HANDOFF.md`, not re-run.

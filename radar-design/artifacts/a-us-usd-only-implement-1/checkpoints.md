# A-US-USD-ONLY-IMPLEMENT-1 — task checkpoints (uncommitted candidate)

All pytest runs go through a process-local wrapper (`wt_db.py`, session
scratchpad) that pins `PERSONAL_DB_NAME=personal_apps_radar_wt` after every
dotenv load, refuses unless both the engine URL and server `select database()`
name that clone, and blocks every non-loopback socket connection. The worktree
has no `.env`; without the wrapper `app.py` binds the protected `personal_apps`.
Destructive suites (board store/producer/shared API/parity, migration suites)
stay refused: no `RADAR_DESTRUCTIVE_TEST_TARGET`/registry exists for
`localhost:3306/personal_apps_radar_wt`, and none was provisioned.

## Baseline (pre-edit, HEAD 38591e0)

- Vitest radar config: 911 tests, 883 passed, 28 failed — all 28 in
  `static/radar/src/hub/pending.test.tsx`. Identities: `baseline/vitest-radar-pre-failures.txt`.
- Protected DB-free pytest (with `--confcutdir`): selected_price_unit 256 passed;
  ha1_unit 241 passed; test_radar_massive 18 passed.
- DB-backed `tests/ -k radar` on the clone: 1849 passed, 14 failed, 220 errors,
  1 skipped (663 s). Identities: `baseline/radar-db-pre-nonpass.txt`.

## Task 1 — US-only HTTP, calendar, cache and archive contract

Changed: `routes/api.py` (Query.market='us'; `default_market` deleted; explicit
non-US → `BadQuery('unsupported market')`), `routes/views.py` (explicit non-US
market → `abort(400)` before the friendly fallback), `routes/price_chart.py`
(span required; omitted market = US; any other → `invalid_market`/400),
`market_calendars/__init__.py` (US only; MIC accepted, not consulted),
`board.py` (US clock; Xetra-gap branch removed; `MARKET_VENUE`),
`board_shared.py`, `board_keys.py` (KEY_VERSION 3; market must be US in both
directions), `board_namespace.py` (PAYLOAD_VERSION 2), `board_producer.py`
(WARM_MARKETS ('us',); per the owner addendum below, WARM_WINDOWS
(1, 4, 12, 24)), `board_store.py` (warm_limit 8 -- briefly 4 before the
addendum), `observations.py` (SCHEMA_VERSION 2, MARKETS ('us',)).
Deleted: `market_calendars/de.py`, `market_calendars/tradegate.py`,
`tests/test_radar_calendar_de.py` (see Task 1 note below).
Tests changed: test_radar_api, test_radar_hub_page, test_radar_calendar,
test_radar_board, test_radar_board_cache, test_radar_board_keys,
test_radar_board_namespace, test_radar_board_store, test_radar_board_producer,
test_radar_board_shared_api, test_radar_board_parity (US-only rewrite with inert
archived rows), test_radar_observations, selected_price_unit/test_route_ops.

Pre-change focused run: 30 failed / 180 passed (new assertions) + 29 refused
errors; route_ops 3 failed / 24 passed.
Post-change focused run (12 files): 240 passed, 7 failed, 159 refused errors.
Remaining failures at this checkpoint: quote serializer / panel basis /
discover board (Task 2 read path still queries the retired market), namespace
price fingerprint (Task 3 config), `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`
(baseline failure). Two stale test constants (key version, warm limit) fixed.
route_ops: 27 passed.

Owner addendum (`radar-design/A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`,
received mid-run, applied before closing the task): the producer keeps eight
warm boards, all US -- 1 market x 2 segment selections x 4 windows.
`WARM_WINDOWS = (1, 4, 12, 24)`; `Limits.warm_limit` stays 8. Tests now prove
exactly 8 unique warm keys, every query US, both parser-normalized segment
selections (`[]` and `['discover','mid','micro','unknown']`) four times each,
windows `[1, 1, 4, 4, 12, 12, 24, 24]`, every (segment, window) pair once, and
each warm key equal to the key of the bare-URL question it stands for
(test_radar_board_producer). Readiness tests and the store limits test are back
to 8; the shared-API derived-count test uses 1 x 2 x 6 = 12. Warm-set tests:
3 passed (DB-free); limits test: 1 passed. The readiness/claim tests stay in
the refused destructive suites. Direct check: `warm_queries()` -> 8, markets
['us'], windows [1, 1, 4, 4, 12, 12, 24, 24].

Incident: the two calendar deletions were first made with `git rm`, which
staged them. They were immediately unstaged with `git restore --staged`;
`git diff --cached` is empty. All later deletions use plain `rm`.

## Task 2 — US/USD read path; FX and ECB removed

Changed: `markets.py` (Market literal 'us'; `QuoteView.is_fallback` and the
fallback branch removed; `select_quote` refuses non-US; `from_snapshot`
refuses non-US or non-USD snapshots), `quotes.py` (US-only `quote_views_for`;
`_quote_matches`, `statuses_for`, `moves_for` read only US/legacy-US rows and
refuse non-US identities; `record_quotes` refuses non-US/non-USD writes;
`_stored_quote(row, instrument)` without market), `history.py`
(`_converted_basis` and `converted_from` removed; `_market_filter` US-only;
`record_closes` refuses non-US/non-USD writes; `resolve_basis` refuses a
non-US quote; sibling basis is US-only; `deutsche_boerse_delayed` priority
removed; `due_instruments` removed with its only DE caller -- the daemon
function itself goes in Task 3), `leaderboard.py` (DE sigma branch removed),
`detail.py` (`Chart.converted_from` removed; non-US quote refused),
`detail_panel.py`, `routes/api.py` (`is_fallback`, `converted_from` removed
from the wire), `phrasing.py` (fallback-listing clause removed -- an active
residual not listed in the research inventory), `run_radar_ingest.py`
(`fx` import, `ZoneInfo`, `refresh_ecb_rates`, `_scheduled_ecb_fx`,
`radar_ecb_fx` job removed).
Deleted: `features/radar/fx.py`, `features/radar/prices/ecb.py`,
`scripts/backfill_radar_fx.py`, `tests/test_radar_ecb.py`, `tests/test_radar_fx.py`.
Tests changed: test_radar_markets, test_radar_quotes, test_radar_quotes_batch,
test_radar_history, test_radar_history_basis (rewritten US-only, archived rows
and FX rows seeded as inert), test_radar_detail, test_radar_leaderboard,
test_radar_phrasing, test_radar_api, test_radar_daemon (Task 2 + Task 3 parts).

Pre-change focused run (8 files): 42 failed, 239 passed.
`py -3.12 -c "import app; import run_radar_ingest"`: ok.
Post-change focused run (11 files): 390 passed, 19 failed -- 16 daemon and 1
history assertions that belong to Task 3 (DE jobs/functions/vocabulary still
present), the baseline page-embed failure, and two API tests updated in this
task; after the update those two pass (2 passed).

## Task 3 — atomic DE runtime removal

Changed: `run_radar_ingest.py` (removed `DE_QUOTE_LIMIT`, `DE_HISTORY_LIMIT`,
`_german_quote_sample`, `probe_german_data`, `_mapping_provider`,
`_scheduled_mappings`, `_build_mapping_generation`, `_xetra_history_instruments`,
`_mapping_refresh_due`, unreachable `poll_quotes`/`_scheduled_quotes`,
`_current_de_generation_id`, `_legacy_de_poll`, `_de_should_collect`,
`_scheduled_de_market_data`, `refresh_de_history` incl. its
`RadarInstrument.history_due_at` write and `.DE` suffixing,
`_yahoo_de_history_provider`, the DE half of `_scheduled_history`, CLI flags
`--probe-german-data`/`--refresh-mappings`, job registrations
`radar_de_market_data`/`radar_mappings`; `_scheduled_prune` now calls
`retention.prune_closes`; unused `has_app_context`, `RadarQuote`,
`classify_quality` imports dropped), `config.py` (`price_provider_config()` ->
`(us_quote_provider, us_close_source)`, `RADAR_DE_PRICE_MODE` no longer read;
DE quota constants removed), `market_data.py` (collector, journal, cursor,
throttle, budget, native-close and mapping helpers removed; `ops_summary`
returns only `quote_basis_24h` (US/legacy-US rows), `grouped_closes`,
`post_close_claims` (market 'us'); grouped ingestion, claims and memo
unchanged), `retention.py` (`prune_market_data` replaced by `prune_closes`
= `_prune_daily_closes` + `_prune_massive_shadow`; close prune scoped to
market 'us' OR NULL; quote prune ranks only US/legacy-US rows via
`_ranked_quotes()` -- filter inside the ranked subquery; no DE event/cycle
deletion), `prices/__init__.py` (`deutsche_boerse_delayed` removed from
active source sets), `prices/finnhub.py` and `prices/twelvedata.py`
(`stock_catalog`, catalog maps and `CatalogInstrument` imports removed; Twelve
Data quotes/history kept), `prices/yahoo.py` (XETR allowlist and EUR history
identity removed; docstring), `scripts/backfill_radar_market_history.py`
(only `us` and `us-universe`), `scripts/report_radar_market_data_shadow.py`
(German gates, identity audit, generation lookup removed; `us-closes` is the
sole/default gate).
Deleted: `features/radar/instruments.py` (incl. `_active_us_instruments`),
`features/radar/reference_universe.py`, `prices/deutsche_boerse.py`,
`prices/openfigi.py`, `data/german_instrument_overrides.json`,
`scripts/capture_deutsche_boerse_contract.py`, tests
`test_radar_deutsche_boerse.py`, `test_radar_reference_universe.py`,
`test_radar_openfigi.py`, `test_radar_instruments.py`,
`test_capture_deutsche_boerse_contract.py`, and the seven
`tests/fixtures/radar_market_data/*` files.
Tests changed: test_radar_daemon, test_radar_market_data (rebuilt from its US
sections + retirement assertions), test_radar_market_data_report,
test_radar_quote_retention, test_radar_operations_api, test_radar_prices,
test_radar_yahoo.

Test-first note: these tests were written before the source edits, but only the
daemon (16) and history (1) assertions were observed red (Task 2's post run); the
other Task 3 conversions were not run red separately.
`py -3.12 -c "import app; import run_radar_ingest; import scripts..."`: imports ok.
Focused run (10 files): 282 passed, 5 failed before one test fix; the fix was
a newline-sensitive split in the new ranked-subquery test (retention suite
then 14 passed). The other 4 failures are baseline identities:
`test_active_price_tickers_is_the_union_of_the_three_windows` and three
`test_radar_yahoo::test_daily_closes_*`.
test_radar_massive (confcutdir): 18 passed.
`git diff -- personal_apps/models.py personal_apps/migrations`: empty.
`git diff --cached`: empty.

## Task 4 — frontend market dimension removed, USD-only rendering

Changed: `types.ts` (`Market = 'us'`; `QuoteCurrency = 'USD'`;
`MarketQuote.currency`/`DetailChart.currency` narrowed to `'USD' | null`;
`is_fallback`, `converted_from`, `deutsche_boerse_delayed` and the ops
`cycles`/`mapping_generations`/`de_download_budget_24h` removed;
`Selection.market` removed), `api.ts` (no market in board/detail queries),
`embedded.ts` (payload without market reads as US; any other market is
refused, never relabelled), `hub/navigation.ts` (no market read/written;
legacy `market` key still routes a root link to Human Chatter),
`hub/queries.ts` (no market in detail/price-chart keys or selections;
price-chart activation unchanged otherwise), `hub/Filters.tsx` (market select
removed), `hub/Hub.tsx` (top bar context = board on screen or opening board;
constant 'US markets'), `board/BoardPage.tsx` (market state/flip tracking
removed), `list/ListPane.tsx` (MarketSwitch removed; fallback lift removed),
`list/TickerRow.tsx` (fallback fact removed), `QuoteBadges.tsx`,
`detail/Identity.tsx`, `detail/PriceChart.tsx` + `detail/ChartHover.tsx`
(no conversion note; `money()` is dollars only), `detail/DetailPane.tsx`,
`format.ts` (`money(value, scale)`; `formatPrice` en-US USD, unknown for any
other currency; new shared `usdText`), `hub/ResearchContent.tsx`,
`hub/Overview.tsx`, `hub/Chatter.tsx` (currency-group caption removed),
`hub/CandidateList.tsx`, `hub/Watching.tsx` (all use `usdText`; no EUR
branch), `hub/chatterSort.ts` (only USD prices are comparable;
`priceCurrencies` removed), `hub/Admin.tsx` (German download budget and
Collection cycles panel removed), `hub/selectedPriceGeometry.ts`
(DBAG source word removed), `hub/ChatterWorkspace.tsx`,
`hub/EvidenceRail.tsx`, `board/Search.tsx` (copy), `fixtures.ts`,
`radar.css` (`.market-switch` rules removed).
Deleted: `board/MarketSwitch.tsx`.
Tests changed: api, embedded, format, QuoteBadges, hardening, motion (comment),
board/BoardPage, board/Controls, board/narrow, board/pending,
detail/ChartHover, detail/ChatterHistogram, detail/PriceChart,
list/TickerRow, list/cols, list/keys, list/marks, list/tiers,
list/watchtier, hub/Admin, hub/Chatter, hub/chatterSort, hub/Filters,
hub/Hub, hub/navigation, hub/pending, hub/queries,
hub/SelectedPriceSection, hub/selectedPriceGeometry, hub/state.

Baseline identities for `hub/pending.test.tsx` captured before the frontend
edit (`task4/pending-pre-failures.txt`, 28, identical to the HEAD full-suite
baseline). Deviation, stated plainly: the frontend conversion was driven by
`tsc` after the type change, so the new frontend assertions were written
alongside the implementation rather than run red first.

`npx tsc --noEmit`: exit 0. `npm run build`: exit 0.
Focused Vitest (11 files incl. the plan's 8): 197 passed.
Full radar Vitest: 913 tests, 885 passed, 28 failed; the 28 failing identities
are exactly the baseline `hub/pending.test.tsx` set (`pre == post`: True).
`hub/pending.test.tsx` alone: 58 tests, 30 passed, 28 failed, identical
failing identities; one passing test was replaced
(`the top bar while a new market loads names the market the reader chose...`
-> `the top bar while a new selection loads names the US market and offers
no market to choose`), no status change on any other test.

## Task 5 — residual sweep, full gates, visual verification

Sweeps (`task5/sweep1.txt`..`sweep3.txt`, `task5/extra-checks.txt`): every
remaining hit is immutable/historical (migrations, docs, radar-design),
archival schema compatibility (`models.py` CHECK strings, model/migration test
fixtures), an intentional rejection/inertness test, unrelated locale or
vocabulary (`de-DE` Berlin clock, word lists), an out-of-scope product (Gym,
Tips, quizbank, `PRODUCT.md`) or a regex false positive (`INCLUDE_PREPOST =`,
`SIDE_BY_SIDE =`). Left for Mastermind classification: `config.py:533`
comment and subreddit `mauerstrassenwetten` in `REDDIT_SUBS` (German-language
chatter source, not a market/price path). Extra checks: `RADAR_DE_PRICE_MODE`
appears only in test `setenv`/`delenv`; `market_calendars/` = `__init__.py`,
`us.py`; `prices/` = `__init__`, `alpaca`, `finnhub`, `massive`, `twelvedata`,
`yahoo`; `fx.py`, `reference_universe.py`, `instruments.py`,
`tests/fixtures/radar_market_data/` absent; built bundle has 0 x Germany,
Xetra, XETR, Tradegate, ECB, EUR sign, EUR, deutsche_boerse, fallback listing.

Line endings: five edited files had been written with LF
(`board/pending.test.tsx`, `hub/Filters.tsx`, `hub/pending.test.tsx`,
`test_radar_history_basis.py`, `test_radar_observations.py`); normalized to the
working copy's CRLF. `git diff --check` (`task5/diff-check-final.txt`): exit 0;
the only warnings name pre-existing continuity documents not touched by code
work.

Final gates on final code:
- `npx tsc --noEmit`: exit 0 (`task5/tsc-final.log`).
- Vitest radar: 913 tests, 885 passed, 28 failed; failing identities equal the
  HEAD baseline (`task5/vitest-radar-final-failures.txt`; comparison True).
- `npm run build`: exit 0 (`task5/build-final.log`).
- Protected DB-free (confcutdir): selected_price_unit 261 passed, ha1_unit 241
  passed, test_radar_massive 18 passed.
- DB-backed `tests/ -k radar` on the clone after Task 4
  (`task5/radar-db-post.*`): 1698 passed, 12 failed, 193 errors, 1 skipped; no
  status change on any shared identity versus baseline; disappeared non-pass
  identities are deleted/renamed cases and the activity migration test (F1);
  new non-pass identities are renamed parity cases refused for the missing
  destructive opt-in. Final rerun on final code: see the section below.
- `git diff -- personal_apps/models.py personal_apps/migrations`: empty.
  `git diff --cached`: empty.

Visual (`browser/verify_us_only.py`, Python Playwright, headless Chromium,
1200/390/320): exit 0, 29 cases, 184 checks, 0 failures, 0 outbound attempts,
0 unmocked API calls; 24 screenshots viewed. Real app on the proved clone
(contract, chrome, admin) plus the built hub bundle on saved selected-price
fixtures (populated USD rendering). Two harness checks were corrected after the
first run: the design hides the top-bar venue text on mobile and the candidate
list below 860 px, so those checks read the DOM/page lead instead.

Finding F1 (pre-existing, flagged): `test_radar_activity.py::
test_the_migration_adds_and_removes_only_its_own_two_tables` runs
downgrade/upgrade on the bound database without the destructive-target guard;
the baseline run upgraded the disposable clone from `a7c31f0b52d4` to
`b7e3f9c1a2d4`. Not fixed (out of scope).

## Task 5 — final DB-backed rerun (final code)

Wrapper proof: engine and server database `personal_apps_radar_wt`, 0 FKs,
47 base tables, Alembic `b7e3f9c1a2d4`, MySQL 8.0.46.
`pytest tests/ -k radar` (`task5/radar-db-final.*`): 1698 passed, 12 failed,
193 errors, 1 skipped, 643 s. Status/identity set identical to the post-Task-4
run; every failure is a baseline identity; every error is the destructive
opt-in refusal. Two baseline failures count residue rows that grow by a fixed
step on each full run (103 -> 128 -> 153 ingest artifacts; 54 -> 64 -> 74
mentions): the non-destructive tests leave rows in the disposable clone (F5).

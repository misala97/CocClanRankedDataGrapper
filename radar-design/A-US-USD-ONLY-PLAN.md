# Radar US/USD-only Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task with recorded checkpoints. Do not dispatch subagents; Radar's workflow requires one owner-selected Implementer followed by one independent Reviewer.

**Goal:** Remove every active German/EU/EUR path from Radar so the product exposes only US listings and native USD prices, while preserving old German/EUR database rows as inert archival data and keeping all functioning US behavior.

**Architecture:** Narrow the public contract and stored-board identity to one US market, remove DE/EUR reads and presentation, then atomically excise provider/mapping/FX writers and their imports. Preserve generic database metadata and immutable migrations, but make every active reader, writer, scheduler and retention query US-only. Remove the frontend market dimension end-to-end rather than leaving a hidden constant or dormant flag.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, APScheduler, React/TypeScript, Vitest, pytest, Vite, existing Python Playwright harness. No new dependency, service or migration.

**Spec:** `radar-design/A-US-USD-ONLY-SPEC.md`

## Global Constraints

- Binding inputs: `A-US-USD-ONLY-SPEC.md`, `A-US-USD-ONLY-RESEARCH-1-RULING.md`, `A-US-USD-ONLY-VERIFY-1-RULING.md`, `A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`, and this plan.
- Warm every supported US window for both existing segment selections: exactly eight US boards.
- Preserve all pre-existing dirty/untracked work. No commit, push, deployment, production access, provider request, credential read or environment edit is authorized.
- Do not edit `models.py` constraint/table definitions or any historical migration. Do not delete, rewrite or convert old database rows.
- Active Radar accepts only US and USD. Omitted market means US; explicit non-US means 400. Never relabel EUR as USD.
- Preserve Alpaca selected price, US grouped closes, US quote/history paths, HA1, Gym German UI and unrelated `Europe/Berlin` clock behavior.
- `TWELVEDATA_API_KEY`, `RADAR_US_PRICE_PROVIDER`, `RADAR_US_CLOSE_SOURCE`, Massive and Alpaca configuration remain.
- The 146 imported US identities lacking instrument rows remain explicit workstream-B debt; A adds no replacement mapper.
- Every task starts with focused failing tests, implements the smallest behavior, reruns the focused gate, and records results. Leave one coherent uncommitted candidate for independent review.
- Before any DB-backed test, prove the configured database is the documented disposable worktree target. If it is not exactly `personal_apps_radar_wt`, stop DB-backed testing. Its known missing foreign keys mean it cannot prove migration/FK parity; report that limit rather than hiding it.
- Run implementation/test/build commands from `personal_apps/` unless a step explicitly names the repository root.

---

## Phase 0: Documentation Discovery — completed for planning

Three read-only discovery passes inspected established repository patterns at HEAD `38591e0`.

**Allowed APIs and patterns:**

- Shared query validation: `routes/api.py::BadQuery` and `parse_query(args, now=None)`; JSON routes already serialize `BadQuery` as 400 at `routes/api.py:640-644,798-801`.
- Selected-price validation: `routes/price_chart.py::ChartError`, `_refused`, and `parse_chart_query`.
- Stored-board identity: `board_keys.canonical`, `query_from_json`, `round_trips`, explicit `KEY_VERSION`; payload namespaces use `board_namespace.PAYLOAD_VERSION`, revision and fingerprint.
- Observation archives: `observations.SCHEMA_VERSION` is stored on each insert; rows are insert-only and old versions remain readable.
- Legacy-US SQL scope: copy the `sa.or_` structure from `quotes._quote_matches` (`quotes.py:165-174`) and `history._market_filter` (`history.py:68-79`). For retention, filter `market == 'us' OR market IS NULL` before ranking/deletion.
- Scheduler tests: copy `CapturingScheduler`/`_captured_jobs` from `tests/test_radar_daemon.py:1076-1104` and assert the exact job-id set.
- US grouped-close transaction: preserve `market_data.ingest_grouped_day`'s `commit=False` writes and single outer commit/rollback at `market_data.py:836-857`.
- Frontend dimension removal: remove type → control → URL/parser → request → query key → tests together. Preserve `queryFor`/`readSelection` inverse tests for remaining dimensions.
- Strict USD exemplar: selected-price types/runtime checks in `hub/priceChart.ts:22-31,80-99,245,283-284` and formatter in `selectedPriceGeometry.ts:297-300`.
- Responsive checks: use the existing batched Python Playwright harness pattern in `radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py`.

**Anti-pattern guards:**

- Do not silently normalize explicit `market=de` to US.
- Do not leave `Selection.market='us'`, hidden controls, market cache keys, empty German ops objects or ignored German runtime flags.
- Do not delete `prune_market_data` and accidentally disable `_prune_daily_closes`/`_prune_massive_shadow`.
- Do not filter DE rows only after `prune_quotes` has ranked them.
- Do not delete provider/mapping modules before removing every top-level importer.
- Do not delete archival ORM classes/CHECK strings or edit migrations.
- Do not remove `TWELVEDATA_API_KEY` handling or weaken grouped-close transactionality.
- Do not call an entire Vitest run green by excluding `hub/pending.test.tsx` or comparing only failure counts.

---

### Task 1: Establish the US-only HTTP, calendar, cache and archive contract

**Files:**

- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/features/radar/routes/views.py`
- Modify: `personal_apps/features/radar/routes/price_chart.py`
- Modify: `personal_apps/features/radar/market_calendars/__init__.py`
- Delete: `personal_apps/features/radar/market_calendars/de.py`
- Delete: `personal_apps/features/radar/market_calendars/tradegate.py`
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/board_shared.py`
- Modify: `personal_apps/features/radar/board_keys.py`
- Modify: `personal_apps/features/radar/board_namespace.py`
- Modify: `personal_apps/features/radar/board_producer.py`
- Modify: `personal_apps/features/radar/observations.py`
- Modify focused tests: `test_radar_api.py`, `test_radar_hub_page.py`, `test_radar_calendar.py`, `test_radar_board.py`, `test_radar_board_keys.py`, `test_radar_board_namespace.py`, `test_radar_board_store.py`, `test_radar_board_producer.py`, `test_radar_board_cache.py`, `test_radar_board_shared_api.py`, `test_radar_board_parity.py`, `test_radar_observations.py`, `selected_price_unit/test_route_ops.py`
- Delete: `personal_apps/tests/test_radar_calendar_de.py`

**Interfaces:**

- Produces `Query.market == 'us'`, `parse_query` omission→US and explicit non-US→`BadQuery('unsupported market')`.
- Produces HTML 400 only for an explicitly supplied non-US market; preserves current friendly fallback for malformed non-market filters.
- Produces selected-price omission→US and explicit non-US→`ChartError('invalid_market', 400, 'unsupported market')`.
- Produces `KEY_VERSION = 3`, `PAYLOAD_VERSION = 2`, `SCHEMA_VERSION = 2`, `WARM_MARKETS = ('us',)`, `WARM_WINDOWS = (1, 4, 12, 24)`, `MARKETS = ('us',)`.
- Produces exactly eight warm queries: one US market × two existing segment selections × all four supported windows.
- Later tasks rely on server payload `market='us'`, `market_venue='US markets'`, not on a selectable dimension.

- [ ] **Step 1: Write the failing contract tests.**

Add assertions equivalent to:

```python
assert parse_query({}).market == 'us'
assert parse_query({'market': 'us'}).market == 'us'
with pytest.raises(BadQuery, match='unsupported market'):
    parse_query({'market': 'de'})
assert client.get('/radar/api/board?market=de').status_code == 400
assert client.get('/radar/?market=de').status_code == 400
assert client.get('/radar/hub/?market=moon').status_code == 400
assert client.get('/radar/?window=nonsense').status_code == 200
```

Move selected-price `span=1D` out of the refusal table and prove it follows the same successful US path as `span=1D&market=us`; change `market=de` to `invalid_market`/400. Assert `session_state('de', when)` raises `ValueError`; observation maps contain exactly `{'us'}`; v1 keys fail and v3 US keys round-trip. For producer warming, assert exactly eight unique queries, only US, both existing segment selections, and windows `[1, 1, 4, 4, 12, 12, 24, 24]`.

- [ ] **Step 2: Run the focused tests and record the expected pre-change failures.**

```powershell
py -3.12 -m pytest tests/test_radar_api.py tests/test_radar_hub_page.py tests/test_radar_calendar.py tests/test_radar_board_keys.py tests/test_radar_board_namespace.py tests/test_radar_board_producer.py tests/test_radar_observations.py tests/selected_price_unit/test_route_ops.py -q -p no:cacheprovider
```

Expected before implementation: new US-default, explicit-400 and version assertions fail; existing unrelated assertions remain unchanged.

- [ ] **Step 3: Implement the narrow contract.**

Use these established shapes:

```python
market = args.get('market') or 'us'
if market != 'us':
    raise BadQuery('unsupported market')
```

In HTML routes, pre-check `request.args.get('market')` before the broad fallback and return/abort with status 400 and visible text `unsupported market`. Do not catch that error and rebuild `{}`. Keep the broad fallback for errors when market is absent or `us`.

In `parse_chart_query`:

```python
if 'span' not in seen:
    raise ChartError('missing_query', 400, 'span is required')
market = seen.get('market', 'us')
if market != 'us':
    raise ChartError('invalid_market', 400, 'unsupported market')
```

Delete `default_market`, DE calendar registry branches and German calendars. Narrow board constants and selection echoes to US. Set `WARM_MARKETS = ('us',)` and expand `WARM_WINDOWS` to `(1, 4, 12, 24)` while preserving `WARM_SEGMENTS = ('', DEFAULT_SEGMENT)`. Increment all three versions and leave old database rows untouched.

- [ ] **Step 4: Run the focused gate.**

Run the Step 2 command plus `test_radar_board.py`, `test_radar_board_store.py`, `test_radar_board_cache.py`, `test_radar_board_shared_api.py`, and the rewritten US-only parity suite. Expected: pass on a proven safe local target; otherwise run DB-free selected-price/key tests and report DB-backed tests unavailable.

- [ ] **Step 5: Record the Task 1 checkpoint without committing.**

Record changed/deleted files, commands, counts and any unavailable DB gate in the implementation return draft. Do not stage or commit.

---

### Task 2: Remove DE quote selection, fallback and EUR conversion reads

**Files:**

- Modify: `personal_apps/features/radar/markets.py`
- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/history.py`
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/detail.py`
- Modify: `personal_apps/features/radar/detail_panel.py`
- Modify: `personal_apps/run_radar_ingest.py` only for ECB/FX imports, functions and job removal in the same checkpoint
- Delete: `personal_apps/features/radar/fx.py`
- Delete: `personal_apps/features/radar/prices/ecb.py`
- Delete: `personal_apps/scripts/backfill_radar_fx.py`
- Delete: `personal_apps/tests/test_radar_ecb.py`
- Delete: `personal_apps/tests/test_radar_fx.py`
- Modify: `personal_apps/tests/test_radar_history_basis.py`; delete converted-EUR/DE sibling cases, retain native-US depth/span/empty/single-close and explicit no-conversion coverage
- Modify focused tests: `test_radar_markets.py`, `test_radar_quotes.py`, `test_radar_quotes_batch.py`, `test_radar_history.py`, `test_radar_detail.py`, `test_radar_leaderboard.py`, `test_radar_daemon.py`

**Interfaces:**

- `quote_views_for` reads US and legacy-US rows only; seeded DE rows cannot be selected.
- `select_quote` has no US-fallback-in-Germany mode; any compatibility `is_fallback` field is always false.
- `resolve_basis` uses native US data only; chart currency is USD and `converted_from` remains null if the wire key is retained.
- ECB/FX scheduler and backfill entry points no longer exist.

- [ ] **Step 1: Write failing isolation tests.**

Seed US, legacy-US and DE rows for the same ticker. Assert US lookup returns only USD-native data, DE rows never affect quote, sigma or chart basis, and missing US data remains unavailable rather than falling back or converting. Assert the daemon job set excludes `radar_ecb_fx`.

- [ ] **Step 2: Run the focused read-path tests and capture failures.**

```powershell
py -3.12 -m pytest tests/test_radar_markets.py tests/test_radar_quotes.py tests/test_radar_quotes_batch.py tests/test_radar_history.py tests/test_radar_detail.py tests/test_radar_leaderboard.py tests/test_radar_daemon.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement US/USD-only reads and remove FX atomically.**

Narrow active market literals to US, preserve `(market IS NULL AND mic IS NULL)` only as legacy-US compatibility, remove `_converted_basis`, DE sigma and fallback branches, and remove ECB/FX imports/functions/job/backfill together. Keep native USD provenance and unavailable states truthful; do not rewrite old FX rows or remove `RadarFxRate` from `models.py`.

- [ ] **Step 4: Prove imports and focused behavior.**

```powershell
py -3.12 -c "import app; import run_radar_ingest"
py -3.12 -m pytest tests/test_radar_markets.py tests/test_radar_quotes.py tests/test_radar_quotes_batch.py tests/test_radar_history.py tests/test_radar_detail.py tests/test_radar_leaderboard.py tests/test_radar_daemon.py -q -p no:cacheprovider
```

- [ ] **Step 5: Record the Task 2 checkpoint without committing.**

Confirm deleted FX files have no imports and archival model/migration files are unchanged.

---

### Task 3: Atomically remove DE ingestion, mapping, providers, scripts and retention access

**Files:**

- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/features/radar/market_data.py`
- Modify: `personal_apps/features/radar/retention.py`
- Modify: `personal_apps/features/radar/prices/__init__.py`
- Modify: `personal_apps/features/radar/prices/finnhub.py`
- Modify: `personal_apps/features/radar/prices/twelvedata.py`
- Modify: `personal_apps/features/radar/prices/yahoo.py`
- Delete: `personal_apps/features/radar/instruments.py`
- Delete: `personal_apps/features/radar/reference_universe.py`
- Delete: `personal_apps/features/radar/prices/deutsche_boerse.py`
- Delete: `personal_apps/features/radar/prices/openfigi.py`
- Delete: `personal_apps/features/radar/data/german_instrument_overrides.json`
- Delete: `personal_apps/scripts/capture_deutsche_boerse_contract.py`
- Modify: `personal_apps/scripts/backfill_radar_market_history.py`
- Modify: `personal_apps/scripts/report_radar_market_data_shadow.py`
- Delete DE-only tests/fixtures: `test_radar_deutsche_boerse.py`, `test_radar_reference_universe.py`, `test_radar_openfigi.py`, `test_radar_instruments.py`, `test_capture_deutsche_boerse_contract.py`, and `tests/fixtures/radar_market_data/{xetr,xgat}_{pre,post}trade.json`, `reference_tradegate_index.html`, `reference_xetr.csv`, `reference_xfra.csv`
- Modify shared tests: `test_radar_config.py`, `test_radar_daemon.py`, `test_radar_market_data.py`, `test_radar_market_data_report.py`, `test_radar_prices.py`, `test_radar_yahoo.py`, `test_radar_quote_retention.py`, `test_radar_operations_api.py`

**Interfaces:**

- `price_provider_config()` returns only the US quote provider and US close source; every caller unpacks that exact shape.
- Scheduler contains no `radar_de_market_data`, `radar_mappings` or German history work. `radar_history`, `radar_us_grouped_closes`, `radar_prune` and US jobs survive.
- `market_data.py` retains grouped-close ingestion, claims and US ops summary; DE collector/journal/mapping/native-close paths disappear.
- Retention ranks/deletes only US or legacy-US quote/close rows and never reads or deletes existing DE/EUR rows.
- Scripts expose only US history/universe and `us-closes` reporting gates.

- [ ] **Step 1: Write failing scheduler, retention, ops and script tests.**

Use the existing scheduler recorder and assert:

```python
assert {'radar_de_market_data', 'radar_ecb_fx', 'radar_mappings'}.isdisjoint(jobs)
assert {'radar_us_quotes', 'radar_us_grouped_closes', 'radar_history', 'radar_prune'} <= set(jobs)
```

In retention tests, seed enough old US and DE quotes/closes to trigger deletion. Assert US/legacy-US rows follow the existing bounded rule and every DE row survives. Assert the ranked quote input is US/null scoped. Assert old DE event/cycle rows are untouched. Assert ops contains `quote_basis_24h`, `grouped_closes`, `post_close_claims` and omits `cycles`, `mapping_generations`, `de_download_budget_24h`.

- [ ] **Step 2: Run the focused tests and capture expected failures.**

```powershell
py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_daemon.py tests/test_radar_market_data.py tests/test_radar_market_data_report.py tests/test_radar_quote_retention.py tests/test_radar_operations_api.py tests/test_radar_prices.py tests/test_radar_yahoo.py -q -p no:cacheprovider
```

- [ ] **Step 3: Perform the atomic runtime deletion.**

In one coherent working-tree change, remove every module above and all importers. Remove `RADAR_DE_PRICE_MODE`, DE constants, DE CLI flags, job registrations, mapping/reference/catalog functions, `.DE` suffixing, XETR/XGAT provider entries, `refresh_de_history` including its `RadarInstrument.history_due_at` write, and active `deutsche_boerse_delayed` source vocabulary.

Retain `prune_market_data` as a reduced US close-retention wrapper or rename it consistently across caller/tests. Its body must call `_prune_daily_closes` and `_prune_massive_shadow` but not delete DE event/cycle rows. Filter `_prune_daily_closes` and the input query of `prune_quotes` with:

```python
sa.or_(Model.market == 'us', Model.market.is_(None))
```

Keep `TWELVEDATA_API_KEY`, grouped ingestion transactionality and `RadarProviderSessionState`. Make shadow-report `us-closes` its sole/default gate. Remove `de` and `all` modes from history backfill so no alias reaches German behavior.

- [ ] **Step 4: Prove import atomicity and US maintenance.**

```powershell
py -3.12 -c "import app; import run_radar_ingest"
py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_daemon.py tests/test_radar_market_data.py tests/test_radar_market_data_report.py tests/test_radar_quote_retention.py tests/test_radar_operations_api.py tests/test_radar_prices.py tests/test_radar_yahoo.py tests/test_radar_massive.py -q -p no:cacheprovider
```

Expected: imports succeed; US grouped rollback/non-interference tests pass; DE rows survive retention; removed job ids and ops keys are absent.

- [ ] **Step 5: Record the Task 3 checkpoint without committing.**

Record the complete deletion manifest and confirm `models.py` plus `migrations/` have no diff.

---

### Task 4: Remove the frontend market dimension and render USD-only data

**Files:**

- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/api.ts`
- Modify: `personal_apps/static/radar/src/embedded.ts`
- Modify: `personal_apps/static/radar/src/hub/navigation.ts`
- Modify: `personal_apps/static/radar/src/hub/queries.ts`
- Modify: `personal_apps/static/radar/src/hub/Hub.tsx`
- Modify: `personal_apps/static/radar/src/hub/Filters.tsx`
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Delete: `personal_apps/static/radar/src/board/MarketSwitch.tsx`
- Modify: `personal_apps/static/radar/src/list/ListPane.tsx`
- Modify: `personal_apps/static/radar/src/QuoteBadges.tsx`, `detail/Identity.tsx`, `detail/PriceChart.tsx`, `detail/DetailPane.tsx`, `list/TickerRow.tsx`
- Modify: `personal_apps/static/radar/src/hub/ResearchContent.tsx`, `Overview.tsx`, `Chatter.tsx`, `CandidateList.tsx`, `Watching.tsx`, `chatterSort.ts`, `Admin.tsx`, `selectedPriceGeometry.ts`
- Modify: `personal_apps/static/radar/src/format.ts`, `fixtures.ts`, `static/radar/radar.css`
- Modify frontend tests: `api.test.ts`, `embedded.test.ts`, `format.test.ts`, `QuoteBadges.test.tsx`, `hardening.test.tsx`, `board/BoardPage.test.tsx`, `board/Controls.test.tsx`, `detail/PriceChart.test.tsx`, `list/TickerRow.test.tsx`, `hub/Admin.test.tsx`, `hub/Chatter.test.tsx`, `hub/chatterSort.test.ts`, `hub/Filters.test.tsx`, `hub/Hub.test.tsx`, `hub/navigation.test.ts`, `hub/pending.test.tsx`, `hub/queries.test.ts`, `hub/SelectedPriceSection.test.tsx`, `hub/selectedPriceGeometry.test.ts`, `hub/state.test.tsx`

**Interfaces:**

- `Selection` has no market field; URL/query/cache helpers do not read, write or key on market.
- Active server provenance types narrow to literal `'us'`; active quoted currency narrows to `'USD' | null` where unavailable quotes remain null.
- UI has no market control, Germany label, EUR formatter, fallback-listing badge, conversion copy, German ops panel or DBAG source wording.
- Market prices use en-US USD formatting. Retained Berlin time/date formatting may keep its locale/timezone behavior.
- Genuine US provenance—venue, MIC, freshness, provider source, price basis, session—remains visible.

- [ ] **Step 1: Capture the exact frontend baseline and write failing tests.**

Reproduce `hub/pending.test.tsx` and save the exact failing test identities. Add tests proving no accessible market/Germany control, `queryFor`/`urlFor` never emit `market`, cache keys omit it, USD renders like `$194.20`, DE fallback/conversion text is absent, Admin omits German fields, and DBAG is absent from active source wording/types.

- [ ] **Step 2: Run the focused frontend tests and capture failures.**

```powershell
npx vitest run -c vite.radar.config.ts static/radar/src/hub/pending.test.tsx
npx vitest run -c vite.radar.config.ts static/radar/src/hub/navigation.test.ts static/radar/src/hub/queries.test.ts static/radar/src/hub/Filters.test.tsx static/radar/src/board/BoardPage.test.tsx static/radar/src/hub/Admin.test.tsx static/radar/src/QuoteBadges.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/selectedPriceGeometry.test.ts
```

- [ ] **Step 3: Remove the dimension end-to-end.**

Remove `Selection.market`, `MarketSwitch`, hub market options, market-only race state and market URL/request/cache keys. Narrow wire types without deleting useful US provenance. Remove EUR/fallback/conversion branches and German ops/source copy. Use the selected-price strict USD formatter pattern; do not coerce unknown/EUR values to USD.

- [ ] **Step 4: Run type, focused and build gates.**

```powershell
npx tsc --noEmit
npx vitest run -c vite.radar.config.ts static/radar/src/hub/navigation.test.ts static/radar/src/hub/queries.test.ts static/radar/src/hub/Filters.test.tsx static/radar/src/board/BoardPage.test.tsx static/radar/src/hub/Admin.test.tsx static/radar/src/QuoteBadges.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/selectedPriceGeometry.test.ts
npm run build
```

Re-run `hub/pending.test.tsx` and compare exact failing identities to the baseline. No new failure is acceptable; do not claim the suite green if the verified baseline remains.

- [ ] **Step 5: Record the Task 4 checkpoint without committing.**

Record the type/build output, focused Vitest counts and exact baseline comparison.

---

### Task 5: Residual sweep, integrated regression and visual proof

**Files:**

- Create sanitized evidence under `radar-design/artifacts/a-us-usd-only-implement-1/`.
- Update only current-status sections of `radar-design/A-US-USD-ONLY-LEDGER.md` and workspace-root `HANDOFF.md` after verification.
- Create `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`.

- [ ] **Step 1: Run the residual searches.**

From `personal_apps/`, excluding migrations, historical docs/design artifacts, generated bundles, `node_modules`, caches and scratchpads:

```powershell
rg -n -i "deutsche|boerse|börse|xetra|xetr|xgat|frankfurt|xfra|tradegate|\becb\b|eurofxref|openfigi|figi|\.DE'" features run_radar_ingest.py scripts static/radar/src templates tests
rg -n "'de'|\"de\"|market=de|\bEUR\b|€|convert_usd_to_eur|converted_from|is_fallback|allow_us_fallback|default_market|RADAR_DE_|DE_[A-Z_]+ =|radar_de_|radar_ecb|radar_mappings|refresh_de_|_german|german_|_de_|probe-german|refresh-mappings|deutsche_boerse_delayed" features run_radar_ingest.py scripts static/radar/src static/radar/radar.css tests
rg -n -i "german|germany" features run_radar_ingest.py scripts static/radar/src tests
```

Allowed residuals only: immutable migrations and historical docs/design records; ORM CHECK strings and archival model classes; model/migration fixtures; intentional rejection fixtures/tests; unrelated word lists; `Europe/Berlin` and date/time locale use; Gym. Every other hit is a defect. Active Python/TypeScript source vocabularies and retention exceptions are not allowed residuals.

- [ ] **Step 2: Prove protected code and schema files.**

```powershell
git diff --check
git diff -- personal_apps/models.py personal_apps/migrations
py -3.12 -c "import app; import run_radar_ingest"
py -3.12 -m pytest tests/selected_price_unit tests/ha1_unit tests/test_radar_massive.py -q -p no:cacheprovider
```

Expected: diff check clean; no model/migration diff; imports succeed; protected suites pass with only the intentional selected-price query-contract expectation changes.

- [ ] **Step 3: Run the complete relevant backend/frontend gates.**

After proving `personal_apps_radar_wt`, run:

```powershell
py -3.12 -m pytest tests/ -k radar -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts
npx tsc --noEmit
npm run build
```

Record exact passed/failed/skipped counts and environmental limits. For `hub/pending.test.tsx`, compare exact failing identities with the pre-edit capture; a new or changed failure is a regression even when the total remains 28.

- [ ] **Step 4: Perform actual-app visual verification.**

Use one batched Python Playwright script against the built local hub and legacy board at desktop 1200px, mobile 390px and 320px/reflow. Inspect the PNGs. Verify: no market selector or blank control gap; no Germany/EUR/fallback/conversion copy; USD price display; no hidden market tab stop; filters/focus/selected-price remain usable; no horizontal overflow. Do not use the embedded browser pane.

- [ ] **Step 5: Produce the implementation return and stop.**

List every modified/deleted file, test command/result, baseline comparison, screenshot and unavailable gate. State that old DB rows/migrations/models were untouched, A added no US mapper, the 146 mapping gap remains, and production env cleanup is a deployment carry. Leave the candidate uncommitted and all production state unchanged. The next step is one fresh independent Reviewer/QA, not deployment.

## Independent review after implementation

The Reviewer receives the spec, both research/verification rulings, this plan, the implementation return, complete diff and artifacts. Review only: residual active DE/EUR reachability, explicit HTTP contract, selected-price protection, historical-row inertness, retention scoping, import completeness, US grouped/quote/history behavior, frontend selector/format removal, schema/migration preservation, exact Vitest baseline and responsive proof. Findings precede any correction task. Commit/push/deployment and production environment cleanup require separate owner authorization.

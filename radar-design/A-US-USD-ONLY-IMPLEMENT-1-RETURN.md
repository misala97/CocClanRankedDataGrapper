# A-US-USD-ONLY-IMPLEMENT-1 — Implementer return

Date: 2026-09-17
Role: Implementer (Claude Opus 5, one session, no subagents)
Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
Branch: `codex/radar-selected-price-charts`
Base = HEAD: `38591e0f5e98faccb5228d84d1677843fcdb2aea` (= `origin/main` = `origin/codex/radar-selected-price-charts`, verified with per-command `safe.directory`)
Status: **one complete, uncommitted local candidate**. Nothing staged, committed, pushed or deployed.

Binding inputs followed: `WORKFLOW.md`, `A-US-USD-ONLY-SPEC.md`, `A-US-USD-ONLY-LEDGER.md`,
`A-US-USD-ONLY-RESEARCH-1-RETURN.md`/`-RULING.md`, `A-US-USD-ONLY-VERIFY-1-RETURN.md`/`-RULING.md`,
`A-US-USD-ONLY-PLAN.md`, `US-UNIVERSE-REFRESH-2026-09-16.md`, `MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md`,
the current notices, and the owner addendum `A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md` (received mid-run).

Evidence: `radar-design/artifacts/a-us-usd-only-implement-1/` — `checkpoints.md` (per-task record),
`baseline/`, `task1/`..`task5/`, `browser/` (harness, `results.json`, 24 screenshots). `.log` files are
local (git-ignored); XML/JSON/TXT are untracked.

---

## 1. Outcome

Radar is US-listings/USD-only on every active path in this candidate:

- **HTTP contract.** Omitted `market` = US everywhere. Any explicit non-US value (`de`, `moon`, `US`, `eu`)
  is `400 {"error": "unsupported market"}` on `/radar/api/board`, the shared-board path and
  `/radar/api/ticker/<t>`; the HTML routes `/radar/`, `/radar/hub/`, `/radar/legacy/` answer a visible
  `400` page ("unsupported market: Radar shows US listings only …") **before** the friendly fallback, which
  still serves malformed non-market filters. `default_market` is gone. Selected price: `span` required,
  omitted market = US, explicit `market=us` accepted, every other value `invalid_market`/400
  (acquisition, reader, rate limits, fallback and geometry untouched).
- **Calendar.** `market_calendars` holds only `__init__.py` and `us.py`; any non-US market raises
  `ValueError('unknown market: …')` whatever MIC it names; US callers' MICs are accepted and ignored.
- **Cache/archive identity.** `board_keys.KEY_VERSION` 2→3 (market must be US in both directions),
  `board_namespace.PAYLOAD_VERSION` 1→2, `observations.SCHEMA_VERSION` 1→2 with `MARKETS = ('us',)`.
  Old rows untouched.
- **Warm boards (owner addendum).** `WARM_MARKETS = ('us',)`, `WARM_SEGMENTS = ('', DEFAULT_SEGMENT)`,
  `WARM_WINDOWS = (1, 4, 12, 24)`; `warm_queries()` returns exactly 8 unique US queries;
  `Limits.warm_limit` stays 8.
- **Read path.** No DE quote selection, no US fallback, no EUR conversion: `QuoteView.is_fallback`,
  `HistoryBasis.converted_from`, `Chart.converted_from`, `history._converted_basis`, the DE sigma branch
  and the `phrasing` fallback-listing clause are removed; `quote_views_for`, `_quote_matches`,
  `statuses_for`, `moves_for`, `history._market_filter`/`closes_for`/`tickers_needing_history`,
  `resolve_basis`, `select_quote`, `QuoteView.from_snapshot` and `detail.intraday_chart_for` read only US
  or legacy-US (NULL market) rows and refuse any other market. Missing US data stays unavailable.
- **Writers.** `quotes.record_quotes` and `history.record_closes` refuse any non-US or non-USD row
  (`ValueError`), so no active writer can add to the archived lane.
- **Daemon/config/ops.** Jobs `radar_de_market_data`, `radar_ecb_fx`, `radar_mappings` and the DE half of
  `radar_history` (Yahoo `.DE` queue incl. its `RadarInstrument.history_due_at` write, native-close
  materialization) are removed, as are `--probe-german-data`/`--refresh-mappings`, the unreachable
  `poll_quotes`/`_scheduled_quotes`, all DE helpers and constants. `price_provider_config()` returns
  `(us_quote_provider, us_close_source)` and no longer reads `RADAR_DE_PRICE_MODE`; a stale value (even
  an invalid one) neither blocks startup nor adds a job. `market_data.ops_summary` returns exactly
  `quote_basis_24h` (US/legacy rows), `grouped_closes`, `post_close_claims` (market `us`).
- **Retention.** `prune_market_data` is replaced by `prune_closes` (= `_prune_daily_closes` +
  `_prune_massive_shadow`, same call site); close pruning is scoped `market='us' OR market IS NULL`
  (no source exception); `prune_quotes` ranks through `_ranked_quotes()`, whose market filter sits
  **inside** the ranked subquery; no DE event/cycle deletion remains. Nothing deletes archived rows.
- **Providers/vocabulary.** `deutsche_boerse_delayed` removed from `QUOTE_SOURCES`/`CLOSE_SOURCES`, the
  history priority table, the frontend `QuoteSource` type and the selected-price source wording (it
  remains only in `models.py` CHECK strings and immutable migrations). Finnhub/Twelve Data
  `stock_catalog` and maps removed (Twelve Data quotes/history and `TWELVEDATA_API_KEY` kept); Yahoo's
  `XETR` allowlist entry and EUR history identity removed.
- **Deleted modules.** `fx.py`, `prices/ecb.py`, `prices/deutsche_boerse.py`, `prices/openfigi.py`,
  `instruments.py` (incl. `_active_us_instruments`), `reference_universe.py`,
  `market_calendars/de.py`, `market_calendars/tradegate.py`, `data/german_instrument_overrides.json`,
  scripts `backfill_radar_fx.py`, `capture_deutsche_boerse_contract.py`, their DE-only test suites and
  the seven `tests/fixtures/radar_market_data/*` files. All importers removed atomically;
  `import app; import run_radar_ingest` succeeds.
- **Scripts.** `backfill_radar_market_history.py` offers only `us` and `us-universe` (`de`/`all` are
  argparse errors). `report_radar_market_data_shadow.py` keeps only the `us-closes` gate (sole/default);
  German gates, identity audit and generation lookup removed.
- **Frontend.** `Selection.market` removed end-to-end (type, URL read/write, request params, board/detail/
  price-chart cache keys, embedded payload — a payload naming another market is refused, never
  relabelled). `MarketSwitch.tsx` deleted with its CSS; hub market select removed; top bar names
  "US markets". EUR/`€` branches, fallback badge/fact/lift, conversion note, currency-group caption, the
  German download budget and Collection cycles admin panels removed. `format.money()` is dollars only;
  `formatPrice` is en-US USD (`$194.20`) and unknown for any non-USD value; shared `usdText` backs the hub
  price figures. `QuoteCurrency = 'USD'`; `Market = 'us'`. Genuine US provenance (venue, MIC, basis,
  session, freshness, source) remains. The protected selected-price client still sends `market=us`.

## 2. Task-by-task (checkpoints in `artifacts/.../checkpoints.md`)

| Task | Pre-change focused run | Post-change focused run |
|---|---|---|
| 1 contract/calendar/keys/warm/observations | 30 failed / 180 passed (+29 refused); route_ops 3 failed / 24 passed | 240 passed, 7 failed (all attributed: later tasks or baseline), 159 refused; route_ops 27 passed; warm-set after addendum 3 passed, limits 1 passed |
| 2 read path, FX/ECB | 42 failed / 239 passed | 390 passed, 19 failed (16 daemon + 1 history owned by Task 3, 1 baseline, 2 updated tests then 2 passed) |
| 3 atomic DE runtime removal | tests written before the source edits; only the daemon (16) and history (1) assertions were seen red (in Task 2's post run); the retention, market-data, report, prices, Yahoo and ops conversions were not run red separately | imports ok; 282 passed + retention 14 passed; 4 remaining = baseline identities; massive 18 passed |
| 4 frontend | pending baseline captured (28, identical to HEAD) | tsc 0; build 0; focused 197 passed; full Vitest 913/885/28 with identical failing identities |
| 5 sweep/gates/visual | — | see §3 |

Test-first deviations (stated plainly): Tasks 1 and 2 were run red before implementation and the output is
saved. Task 3's tests were written before its source edits, but only part of them was observed failing
(see the table). The frontend conversion was driven by `tsc` after the type change, so the new frontend
assertions were written alongside the implementation rather than run red first.

## 3. Evidence (all fresh Implementer execution unless marked)

Pytest runs use a process-local wrapper that pins `PERSONAL_DB_NAME=personal_apps_radar_wt` after every
dotenv load, refuses unless the engine URL **and** server `select database()` both name that clone, and
refuses every non-loopback socket. The worktree has no `.env`; without the wrapper `app.py` binds the
protected `personal_apps` (proved by URL inspection, no SQL). Clone identity: local MySQL 8.0.46,
0 foreign keys (the documented missing-FK signature).

| Gate | Command (from `personal_apps/`) | Result |
|---|---|---|
| diff check | `git diff --check` | exit 0 (`task5/diff-check-final.txt`; warnings name only pre-existing continuity documents) |
| schema files | `git diff -- personal_apps/models.py personal_apps/migrations` | empty |
| index | `git diff --cached --name-only` | empty |
| imports | `py -3.12 -c "import app; import run_radar_ingest"` (+ both scripts) | ok |
| protected selected price | `pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit` | 256 → **261 passed** (+5 new contract cases; `span=1D` alone now succeeds as US; `market=de` → `invalid_market`/400) |
| protected HA1 | `pytest tests/ha1_unit --confcutdir=tests/ha1_unit` | 241 → 241 passed |
| protected Massive | `pytest tests/test_radar_massive.py --confcutdir=tests/selected_price_unit` | 18 → 18 passed |
| DB-backed radar | `pytest tests/ -k radar` (wrapper) | baseline 1849 passed / 14 failed / 220 errors / 1 skipped → post 1698 / 12 / 193 / 1; **final (final code) 1698 / 12 / 193 / 1**, identities identical to post (§9) |
| TypeScript | `npx tsc --noEmit` | exit 0 |
| build | `npm run build` | exit 0 (both Vite builds) |
| Vitest radar | `npx vitest run -c vite.radar.config.ts` | baseline 911 / 883 / 28 → final **913 / 885 / 28**; failing identities **identical** (all 28 in `hub/pending.test.tsx`) |
| pending alone | `npx vitest run -c vite.radar.config.ts static/radar/src/hub/pending.test.tsx` | 58 / 30 / 28 before and after; failing identities identical; one passing test replaced (market-switch top-bar test → "names the US market and offers no market to choose"); no other status change |
| bundle | grep built `static/radar/dist/assets/*` | 0 × Germany, Xetra, XETR, Tradegate, ECB, €, EUR, deutsche_boerse, "US fallback", "converted to" |
| visual | `py -3.12 -u ../radar-design/artifacts/a-us-usd-only-implement-1/browser/verify_us_only.py` | exit 0; 29 cases, 184 checks, 0 failures, 0 outbound attempts, 0 unmocked API calls, 24 screenshots viewed |

DB-backed identity comparison (post vs baseline, `task5/radar-db-post-nonpass.txt` vs
`baseline/radar-db-pre-nonpass.txt`): no status changes on shared identities. Non-pass identities that
disappeared are the deleted DE parametrizations of the (refused) parity suite, the renamed
`test_human_page_bad_market_falls_back_to_the_default_payload`, and
`test_radar_activity::test_the_migration_adds_and_removes_only_its_own_two_tables` (see §5-F1: it failed at
baseline only because the clone was behind head). New non-pass identities are the renamed parity cases,
refused for the same missing destructive opt-in. Remaining failures are all baseline identities
(e.g. `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`,
`test_active_price_tickers_is_the_union_of_the_three_windows`, three Yahoo `daily_closes` cases, the
watch FK pair).

### 3a. Final DB-backed rerun
On final code: 1698 passed / 12 failed / 193 errors / 1 skipped; identity set identical to the post run; details in §9.

### 3b. Visual verification (Python Playwright, headless Chromium, 1200/390/320)
A. Real Flask app on 127.0.0.1:5051 bound to the proved clone (charts ON, Alpaca/Yahoo OFF, APCA names
removed from the process, shared store OFF, in-memory admin session cookie never printed). The clone's
board is empty (old data), so this part proves contract and chrome: `/radar/?market=de&window=24` → 400
page with the reason and no hub mounted; hub `#chatter` → "US markets · afterhours", window/size filters,
no market select/option/radio, no hidden or market tab stop (40 tabs), no overflow; `/radar/legacy/` →
no switch, no empty slot beside the wordmark; `#admin` → Market data panel with US facts only, no
download budget, no Collection cycles.
B. The built hub bundle from the real `templates/radar/hub.html` on 127.0.0.1:5052 with the saved
MD-SELECTED-PRICE fixtures (stripped of the removed keys; synthetic envelopes as documented there):
Human Chatter with AAPL open shows `$330.46` (and `$7.39` in the side-by-side list at 1200), the
selected-price chart draws, window change keeps the URL market-free, board/detail requests carry no
`market`, the protected price-chart client still sends `market=us`; Research AAPL shows `$330.46` and
"NASDAQ · USD · XNMS … delayed" with no fallback; Overview shows `$7.39 +1.2%`. No retired-market/EUR copy,
no overflow, no hidden tab stop at any width. Screenshots inspected, including
`real-400-1200`, `real-hub-1200/390`, `real-legacy-1200/320`, `real-admin-390`,
`fixture-chatter-AAPL-1200/390`, `fixture-chatter-AAPL-320-chart`, `fixture-research-AAPL-320`,
`fixture-overview-1200`. Two harness checks were corrected after the first run because they read visible
text where the design hides the top-bar venue span and the candidate list below 860 px; the page lead
and the DOM still name "US markets".

## 4. Residual sweep (plan §Task 5 Step 1; outputs in `task5/sweep1..3.txt`, `extra-checks.txt`)

Every hit falls in an allowed category:

- **Immutable/historical**: `migrations/`, `docs/`, `radar-design/` (excluded by the plan).
- **Archival schema compatibility**: `models.py` CHECK strings and archival classes (no diff);
  `tests/test_radar_models.py`, `tests/test_radar_migration.py` fixtures (unchanged).
- **Intentional rejection/inertness tests**: `market='de'`/`currency='EUR'`/`deutsche_boerse_delayed`
  fixtures and `default_market`/`is_fallback`/`converted_from`/`RADAR_DE_PRICE_MODE` absence
  assertions in the converted backend suites; HA1/selected-price rejection fixtures
  (`ha1_unit`, `selected_price_unit`, `test_radar_analysis_api.py`); frontend absence assertions
  (`embedded`, `QuoteBadges`, `format`, `Chatter`, `chatterSort`, `PriceChart`, `Admin`, `BoardPage`,
  `Filters`, `navigation`, `selectedPriceGeometry`).
- **Unrelated vocabulary/locale**: `data/ordinary_words.txt`, `data/name_shapes.txt`; `de-DE` Berlin clock
  and count-locale comments in `format.ts`, `list/Spend.tsx` and their tests; Berlin-DST test wording.
- **Out-of-scope products**: Gym German UI/tests, Tips `€` copy, quizbank prompt text, `features/radar/PRODUCT.md`.
- **Regex false positives**: `INCLUDE_PREPOST =`, `SIDE_BY_SIDE =` (match `DE_[A-Z_]+ =`).
- **For Mastermind classification**: `features/radar/config.py:533` comment and the subreddit
  `mauerstrassenwetten` in `REDDIT_SUBS` — a German-language chatter source, not a market/price path;
  left unchanged because changing sources moves the source-config generation and is outside A's price scope.

Reviewer checks: no job id starting `radar_de`/`radar_ecb`/`radar_mappings`; no code reads
`RADAR_DE_PRICE_MODE` or `OPENFIGI_API_KEY` (only test `setenv/delenv`); `market_calendars/` = `__init__.py`,
`us.py`; `prices/` = `__init__, alpaca, finnhub, massive, twelvedata, yahoo`; `fx.py`,
`reference_universe.py`, `instruments.py`, `tests/fixtures/radar_market_data/` absent.

## 5. Findings and limitations

- **F1 (safety, pre-existing, flagged not fixed).** `tests/test_radar_activity.py::test_the_migration_adds_and_removes_only_its_own_two_tables`
  runs `flask_migrate.downgrade()`/`upgrade()` on whatever DB is bound, **without** the destructive-target
  guard. My authorized baseline run on the disposable clone therefore upgraded `personal_apps_radar_wt`
  from `a7c31f0b52d4` (45 tables) to head `b7e3f9c1a2d4` (47 tables, adding the board-results tables) —
  an unintended DDL side effect of the plan's own test command, on the disposable target only. Each full
  run repeats downgrade/upgrade there. Against the default `personal_apps` binding it would do the same to
  the shared dev database. Not fixed (unrelated scope); a follow-up task chip was raised in the session.
- **F2 (process incident, resolved).** The two calendar deletions were first made with `git rm`, which
  staged them; they were unstaged immediately with `git restore --staged`. `git diff --cached` is empty;
  all later deletions used plain `rm`.
- **F3 (inventory gap, fixed).** `phrasing._quote_limits` still emitted a "Quoted from a fallback listing"
  warning from `is_fallback`; not in the research inventory; removed with its test.
- **F4 (behaviour choice).** An embedded/fetched board payload naming any market other than US is now
  refused (`parsePayload` → null, page shows words) instead of being coerced to US; a payload without a
  market still reads as US. Test `hardening` updated accordingly.
- **F5 (test residue, pre-existing).** Each full DB-backed run leaves rows in the disposable clone (two baseline failures count them: 103 → 128 → 153 and 54 → 64 → 74); see §9.
- **Unavailable gates.** The destructive suites (board store, producer, shared API, parity, board-results and
  projection migrations; HA1 analysis API) stay refused: no `RADAR_DESTRUCTIVE_TEST_TARGET`/registry exists
  for `localhost:3306/personal_apps_radar_wt`, and none was provisioned. Their converted tests (incl. the
  parity US-only rewrite with inert archived rows, readiness at 8 warm boards) are written but unexecuted.
  Alembic autogenerate-diff and FK/migration parity were not run (clone lacks FKs; no disposable target
  registered). Production DB contents/env were not touched or read.
- **Assumption.** `record_closes`' USD guard relies on US instrument rows being `USD`; the only writer of
  those rows is migration `a4c8e2f19b70`, which seeds `'USD'`. A non-USD US row would make a grouped day
  roll back rather than write.
- **Workstream B.** A adds no US mapper; with `instruments.py` gone nothing in the codebase creates or
  refreshes instrument rows. The 146 newly imported US identities remain unmapped and without prices;
  the 51 changed entries remain unchecked.
- **Deployment carries (not authorized here).** Back up and remove `RADAR_DE_PRICE_MODE` and
  `OPENFIGI_API_KEY` from production `.env` during an authorized deploy; restart `radar_ingest`
  (new job set) and `personal_apps_web` with a fresh frontend build; the board namespace rotates via
  revision + fingerprint + `PAYLOAD_VERSION`, and the producer warms 8 US keys.

## 6. Actions taken

- Modified 115 tracked paths (57 application/script/CSS, 58 tests) and deleted 27 tracked paths under
  `personal_apps/` (lists in §8); created
  this return, `checkpoints.md`, evidence files and the browser harness; updated only current-status
  sections of `A-US-USD-ONLY-LEDGER.md` and root `HANDOFF.md`.
- No commit, stage (after F2), push, merge, deploy, production/VPS access, service restart, flag or
  environment-file change, credential display, provider/network request, account action, migration
  creation/edit, `models.py` edit or historical-row mutation. The only schema change anywhere is F1's
  test-driven upgrade of the disposable clone.
- `npm run build` rewrote the git-ignored `static/*/dist` bundles.
- No subagents.

## 7. Protected state

Alpaca selected-price acquisition/reader/fallback/admission/geometry untouched (only the query-input
contract, the frontend cache key's market element and the retired source wording changed); production
flags untouched. US grouped-close ingestion code and its single transaction untouched (transaction tests
pass); US quote cycle, US history, provider-session state (claims now reported for `us` only), HA1,
`TWELVEDATA_API_KEY` path, `models.py`, `migrations/`, all pre-existing dirty/untracked files (the 8
modified continuity documents and ~30 untracked A/HA1/selected-price artifacts, plus the owner's addendum)
and other worktrees preserved.

## 8. File manifest (uncommitted)

Deleted (27): `features/radar/{fx.py, instruments.py, reference_universe.py, data/german_instrument_overrides.json,
market_calendars/de.py, market_calendars/tradegate.py, prices/deutsche_boerse.py, prices/ecb.py, prices/openfigi.py}`,
`scripts/{backfill_radar_fx.py, capture_deutsche_boerse_contract.py}`, `static/radar/src/board/MarketSwitch.tsx`,
`tests/fixtures/radar_market_data/{reference_tradegate_index.html, reference_xetr.csv, reference_xfra.csv,
xetr_posttrade.json, xetr_pretrade.json, xgat_posttrade.json, xgat_pretrade.json}`,
`tests/{test_capture_deutsche_boerse_contract.py, test_radar_calendar_de.py, test_radar_deutsche_boerse.py,
test_radar_ecb.py, test_radar_fx.py, test_radar_instruments.py, test_radar_openfigi.py, test_radar_reference_universe.py}`.

Modified backend (28): `features/radar/{activity.py, board.py, board_keys.py, board_namespace.py,
board_producer.py, board_shared.py, config.py, detail.py, detail_panel.py, history.py,
leaderboard.py, market_calendars/__init__.py, market_data.py, markets.py, observations.py, phrasing.py,
prices/__init__.py, prices/finnhub.py, prices/twelvedata.py, prices/yahoo.py, quotes.py, retention.py,
routes/api.py, routes/price_chart.py, routes/views.py}`, `run_radar_ingest.py`,
`scripts/{backfill_radar_market_history.py, report_radar_market_data_shadow.py}`.

Modified frontend app (29): `static/radar/radar.css`, `static/radar/src/{api.ts, embedded.ts, fixtures.ts,
format.ts, QuoteBadges.tsx, types.ts, board/BoardPage.tsx, board/Search.tsx, detail/ChartHover.tsx,
detail/DetailPane.tsx, detail/Identity.tsx, detail/PriceChart.tsx, hub/Admin.tsx, hub/CandidateList.tsx,
hub/Chatter.tsx, hub/ChatterWorkspace.tsx, hub/EvidenceRail.tsx, hub/Filters.tsx, hub/Hub.tsx,
hub/Overview.tsx, hub/ResearchContent.tsx, hub/Watching.tsx, hub/chatterSort.ts, hub/navigation.ts,
hub/queries.ts, hub/selectedPriceGeometry.ts, list/ListPane.tsx, list/TickerRow.tsx}`.

`features/radar/board_store.py` ends with no diff: `warm_limit` went 8→4 during Task 1 and back to 8
under the owner addendum.

Modified tests (58): backend `tests/{selected_price_unit/test_route_ops.py, test_radar_api.py, test_radar_board.py,
test_radar_board_cache.py, test_radar_board_keys.py, test_radar_board_namespace.py, test_radar_board_parity.py,
test_radar_board_producer.py, test_radar_board_shared_api.py, test_radar_board_store.py, test_radar_calendar.py,
test_radar_daemon.py, test_radar_detail.py, test_radar_history.py, test_radar_history_basis.py,
test_radar_hub_page.py, test_radar_leaderboard.py, test_radar_market_data.py, test_radar_market_data_report.py,
test_radar_markets.py, test_radar_observations.py, test_radar_operations_api.py, test_radar_phrasing.py,
test_radar_prices.py, test_radar_quote_retention.py, test_radar_quotes.py, test_radar_quotes_batch.py,
test_radar_yahoo.py}`; frontend `static/radar/src/{api, embedded, format, hardening, motion, QuoteBadges}.test.*`,
`board/{BoardPage, Controls, narrow, pending}.test.tsx`, `detail/{ChartHover, ChatterHistogram, PriceChart}.test.tsx`,
`hub/{Admin, Chatter, chatterSort, Filters, Hub, navigation, pending, queries, SelectedPriceSection,
selectedPriceGeometry, state}.test.*`, `list/{cols, keys, marks, tiers, TickerRow, watchtier}.test.tsx`.

## 9. Final DB-backed rerun (final code)

Started after the owner addendum, the line-ending normalization and every code edit; nothing changed
afterwards except documents. Command (from `personal_apps/`, through the wrapper):
`pytest tests/ -k radar -q -p no:cacheprovider -rfE --junitxml=../radar-design/artifacts/a-us-usd-only-implement-1/task5/radar-db-final.xml`.

- Target proof printed by the wrapper before any test: engine `localhost:3306/personal_apps_radar_wt`,
  server `select database()` = `personal_apps_radar_wt`, 0 foreign keys, 47 base tables, Alembic
  `b7e3f9c1a2d4`, MySQL 8.0.46. Non-loopback sockets refused.
- Result: **1698 passed, 12 failed, 193 errors, 1 skipped**, 1486 deselected, 643 s (pytest exit 1).
  Identities: `task5/radar-db-final-nonpass.txt`.
- Status/identity set is **identical** to the post-Task-4 run (`task5/radar-db-post-nonpass.txt`).
  Versus baseline: no new failing identity; two baseline failures are gone
  (`test_radar_activity::test_the_migration_adds_and_removes_only_its_own_two_tables`, see F1, and the
  renamed `test_human_page_bad_market_falls_back_to_the_default_payload`); all 32 vanished and all 5 new
  error identities are `test_radar_board_parity` cases (31 DE parametrizations and the old
  omitted-market cases removed or renamed; new: `test_an_omitted_market_is_the_us_key_at_every_hour` x3,
  `test_an_unsupported_market_is_refused_before_the_store`, `[market-omitted]`), all refused at setup.
- All 193 errors are setup refusals: "destructive Radar work is not opted in for the actual bound target".
- The 12 failures are all baseline identities: `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`;
  `test_radar_ingest` x3 (`test_a_parent_context_comment_keeps_its_ticker`,
  `test_fresh_mentions_carry_the_local_model_version` — `MultipleResultsFound`;
  `test_an_empty_healthy_source_stays_ok_without_database_artifacts`);
  `test_active_price_tickers_is_the_union_of_the_three_windows`; `test_mentions_go_with_their_posts`;
  `test_a_lexicon_tone_carries_no_model_name`; the watch FK pair (missing-FK signature); three Yahoo
  `daily_closes` cases.
- **Database fact (F5, pre-existing test behaviour).** Two of those baseline failures count leftover
  rows in the shared clone, and the counts grow by the same step on every full run: ingest artifacts
  103 → 128 → 153 and orphan mentions 54 → 64 → 74 (baseline → post → final). The non-destructive radar
  tests therefore leave rows behind in the disposable clone on each run. They are test-created rows in
  the disposable target, not historical DE/EUR rows; nothing ran against `personal_apps` or production.

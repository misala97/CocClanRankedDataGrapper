# A-US-USD-ONLY-VERIFY-1 — independent Verifier / QA return

Date: 2026-09-16 (verification executed 2026-09-16 late evening, file written 2026-09-17 00:xx local)
Role: Verifier / QA (fresh, read-only; did not produce the Researcher return)
Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
Branch: `codex/radar-selected-price-charts`
Verified HEAD: `38591e0f5e98faccb5228d84d1677843fcdb2aea` = `origin/codex/radar-selected-price-charts` (`git for-each-ref refs/remotes/origin`); log head `38591e0 docs(radar): record Alpaca selected-price acceptance`
Working tree at start and end: 8 modified continuity documents (root `HANDOFF.md`, `radar-design/{ASSIGNMENTS,HANDOFF,MARKET-DATA-ROADMAP,MASTERMIND-STATE,MD-SELECTED-PRICE-LEDGER,ROADMAP,WORKFLOW}.md`) plus the untracked A/HA1/selected-price documents and `radar-design/artifacts/**` listed by `git status --short`; none touched. Line-ending warnings only.
Binding artifacts read fully, in order: `radar-design/WORKFLOW.md`, `A-US-USD-ONLY-SPEC.md`, `A-US-USD-ONLY-LEDGER.md`, `A-US-USD-ONLY-RESEARCH-1-PROMPT.md`, `A-US-USD-ONLY-RESEARCH-1-RETURN.md`, `A-US-USD-ONLY-RESEARCH-1-RULING.md`, `US-USD-ONLY-DECISION.md`, `US-UNIVERSE-REFRESH-2026-09-16.md`, `MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md`, current notices of `MASTERMIND-STATE.md`, `ASSIGNMENTS.md`, root `HANDOFF.md`, and `A-US-USD-ONLY-VERIFY-1-PROMPT.md`.

Paths below are relative to `personal_apps/` unless prefixed. Line numbers are at HEAD 38591e0 and were read by this Verifier.

---

## 1. Verdict

**PASS WITH FINDINGS** for inventory completeness and removal safety.

Basis: the Researcher's inventory correctly identifies every active DE/EUR entry point I could reproduce (API default, two UI selectors, three DE-only jobs plus the DE half of `radar_history`, producer/observation warm boards, read-time FX conversion, US-fallback-in-Germany, DE mapping/reference/collector code, scripts, fixtures, schema boundary). It is safe to plan from **after** the corrections in section 10. One Critical omission exists: nightly `retention.prune_quotes` deletes historical German `radar_quotes` rows and is not in the inventory. Several Important corrections concern the HTML/frontend contract, the selected-price contract, retention call chaining, import-order atomicity, protected-path residuals the Researcher missed, and the `deutsche_boerse_delayed` vocabulary. This verdict is not implementation authorization.

---

## 2. Independent evidence summary

Everything below is fresh Verifier execution unless marked otherwise.

Git (per-command `-c safe.directory`): `rev-parse --abbrev-ref HEAD` → `codex/radar-selected-price-charts`; `rev-parse HEAD` → `38591e0f5e98faccb5228d84d1677843fcdb2aea`; `for-each-ref refs/remotes/origin` → `origin/codex/radar-selected-price-charts 38591e0` (no `origin/main` ref appears in this worktree's remote-ref listing; the Researcher's "= origin/main" is repository-report evidence from the Alpaca closure, not reproduced here); `status --short`, `diff --stat`, `log --oneline -12` as stated above.

Static searches run (`grep -rniE`, excluding `node_modules`, `__pycache__`, `dist`, `scratchpad`, `migrations/versions`, `radar-design/artifacts`):

1. Semantic aliases `deutsche|boerse|börse|xetra|xetr|xgat|frankfurt|xfra|tradegate|\becb\b|eurofxref|openfigi|figi` over `*.py *.ts *.tsx *.html *.css *.json *.txt *.md *.sh *.service *.timer` → 42 non-test files. Hits **not in the Researcher's inventory**: `features/radar/data/name_shapes.txt:653-654` (word list), `static/radar/src/hub/selectedPriceGeometry.ts:273`, `static/radar/src/hub/Admin.test.tsx:21`, `static/radar/src/types.ts:105`, `features/radar/prices/finnhub.py:26`, `features/radar/prices/yahoo.py:6,53`. `features/quizbank/llm.py` matched on an unrelated token and has no DE content (out of scope).
2. Literal `'de'|market|EUR|€|is_fallback|converted_from|deutsche_boerse_delayed|Germany|German|Xetra|Tradegate|ECB|currency` over `static/radar/src/**` non-test → 36 files; every extra file versus the Researcher's list was read and is a false positive (`market closed`, `pre-market`, `market cap`, analysis fixtures already pinned to `'us'`), except the four listed above.
3. Env names `RADAR_DE_*|OPENFIGI_API_KEY|DE_FILES_PER_CYCLE|DE_DOWNLOAD_BUDGET_24H|DE_THROTTLE_BACKOFF_SECONDS|TWELVEDATA_API_KEY|RADAR_DBAG_*|RADAR_ECB*|RADAR_XETRA*|RADAR_TRADEGATE*|RADAR_MAPPING*` over the whole repository; `getenv/environ` reads in every Radar module and script named DE.
4. `deutsche_boerse_delayed` writers/readers over `features`, `run_radar_ingest.py`, `scripts`, `models.py`.
5. `git ls-files` for tracked service/timer/env files; `git ls-files static/radar/dist` → empty (bundle is gitignored, `DEPLOY_FRONTEND.md:6`).

Tests executed (both DB-free):

- `npx vitest run -c vite.radar.config.ts static/radar/src/hub/pending.test.tsx` → `Tests 28 failed | 30 passed (58)` at HEAD 38591e0. **The "28 pre-existing pending.test.tsx failures" baseline is real at HEAD**; the failing assertions are unrelated to markets (e.g. `:942 No company cleared this selection`).
- `PYTHONPATH=. python -m pytest tests/selected_price_unit/test_route_ops.py --confcutdir=tests/selected_price_unit -p no:cacheprovider -q -k "query or market or missing"` → `9 passed, 13 deselected`. Confirms the current selected-price contract: `span=1D` alone → `missing_query` 400; `market=xx` → `invalid_market` 400; `market=de` → `unsupported_instrument` 422 (`tests/selected_price_unit/test_route_ops.py:60-63`).

Not executed: every DB-backed pytest suite. `tests/conftest.py:1-2` states suites run against the real local development database; the destructive suites require the `RADAR_DESTRUCTIVE_TEST_TARGET`/registry opt-in (`tests/radar_disposable.py`, `destructive_target.py:15-18`), which is absent. DB identity could not be proved disposable, so those suites are reported unavailable.

---

## 3. Coverage matrix by subsystem

| Subsystem | Reconstructed from | Researcher inventory | Verifier result |
|---|---|---|---|
| Browser controls / URL state | `hub/Filters.tsx:33-36,85-96`; `board/MarketSwitch.tsx`; `list/ListPane.tsx:5,630`; `hub/navigation.ts:149,232,283-285`; `api.ts:58-60,173`; `embedded.ts:41`; `hub/queries.ts:53,76,776-779`; `hub/Hub.tsx:233-239,295,698-701` | complete | agree; add frontend contract correction (§7) |
| HTML routes | `routes/views.py:34-51` (`/legacy/`), `:53-79` (`/`, `/hub/`): `BadQuery` swallowed → default board | identified, but proposed keeping silent fallback | **disagree**: must 400 (§7) |
| API routes | `routes/api.py:50` (`Query.market='de'`), `:248-263` (`default_market`), `:266-275` (`parse_query`), `:643`/`:800` (400 on BadQuery), `:350-352,380` (payload), `:215-240` (`_quote`, `is_fallback` :234), `:731-739` (`chart.currency/converted_from`) | complete | agree |
| Selected price route | `routes/price_chart.py:31,38-63` | identified, proposed keeping `market` required | **disagree**: omission→US (§7) |
| Board / shared store | `board.py:543-618` (`board_mic` :560, `market_venue` :617), `:142-171`, `:253`; `board_shared.py:353-377`; `board_keys.py:34,48-86,98-160`; `board_producer.py:72,142-158,252-257`; `board_store.py:362-423,510-551,572-638,674-705`; `board_namespace.py:31-32,106-147,150-174` | complete | agree; versioning mechanics refined (§8) |
| Quote / history / leaderboard / detail reads | `quotes.py:65-93,95-156,158-178,252-289,372-416`; `history.py:26-32,66-82,85-163,165-190,226-325,327-360`; `leaderboard.py:115-156,445,531`; `detail.py:96-99,182-224,349-438`; `detail_panel.py:350-351,367,441`; `markets.py:12,176,188-216` | complete | agree |
| Scheduler / CLI | `run_radar_ingest.py:33-37` (top-level `fx`, `instruments` imports), `:70,96`, `:109-208`, `:463-486`, `:512-575` (unreachable `poll_quotes`/`_scheduled_quotes`: no `add_job` registers them, confirmed at `:1350-1446`), `:672-762`, `:943-1000`, `:1052-1089`, `:1159-1177`, `:1282-1295`, `:1376-1401` | complete | agree; `refresh_de_history` also **writes** `RadarInstrument.history_due_at` on DE rows (`:963-965`), a DE-row writer the Researcher listed only as a close writer |
| Board producer / observations | `board_producer.WARM_MARKETS:72`; `observations.py:68,70,120-146,148-186`; job `:1138-1156` | complete | agree |
| Providers | `prices/deutsche_boerse.py` (whole), `prices/ecb.py` (whole), `prices/openfigi.py` (whole; env reads `:83,97,126`), `prices/twelvedata.py:27,110-115,138-195`, `prices/finnhub.py:26-30,140-170`, `prices/yahoo.py:6,53,199-209,358` | mostly | **missed** `finnhub.py:26` (`'XETR': 'DE'`), `yahoo.py:53` (`'XETR'` allowlist), `yahoo.py:6` docstring |
| Mapping / reference data | `instruments.py` (all symbols; `_active_us_instruments:612`, callers only `:567,684,705`), `reference_universe.py`, `data/german_instrument_overrides.json`, `market_calendars/{de,tradegate}.py`, `market_calendars/__init__.py:18,21-35` | complete | agree; ruling 6 confirmed: `_active_us_instruments` has no US consumer → delete |
| Collector / native closes | `market_data.py:32,34` (imports), `:50-293,491-575,999-1010` DE symbols; `:576-593`, `:602-634`, `:637-863`, `:865-898`, `:907-996` US/shared | complete | agree |
| FX / conversion / fallback | `fx.py`; `history._converted_basis:259-289` (`fx` import `:281`); `markets.select_quote:208-213`; `quotes.py:144-149`; frontend `PriceChart.tsx:59-65`, `QuoteBadges.tsx:17-20`, `Identity.tsx:61`, `TickerRow.tsx:288-302`, `ResearchContent.tsx:501-505`, `format.ts:274-282`, `chatterSort.ts:73-98` | complete | agree |
| Retention | `retention.py:49-110` (`prune_market_data`, calls `_prune_daily_closes` `:109` and `_prune_massive_shadow` `:110`), `:123-148`, `:185-215`, **`:257-303` (`prune_quotes`)**, scheduled `:1159-1177` | incomplete | **missed `prune_quotes`** (§6, Critical) |
| Operations / admin | `routes/operations.py:76`; `market_data.ops_summary:907-996` (`cycles` :922-936, `mapping_generations` :938-941, `de_download_budget_24h` :976,985-989); `hub/Admin.tsx:100-135`; `types.ts:513-540` | complete | agree |
| Config / env | `config.py:832-870` (`RADAR_DE_PRICE_MODE` read `:842`), `:1060-1068`; `openfigi.py:83,97,126`; `twelvedata.py:27` | complete | agree (§8) |
| Models / migrations | `models.py:546-598,870-996,999-1167,1212-1226`; `migrations/versions/{a4c8e2f19b70,f5a8c2d91e30,d4e7a1b93c25,6a21d4e8c9f0}`; `migrations/env.py:49-52`; FK `6a21…:189-193` | complete | agree; archival necessity proven (§6) |
| Scripts | `scripts/backfill_radar_fx.py`, `capture_deutsche_boerse_contract.py`, `backfill_radar_market_history.py:8-22,36-56,84-96,124`, `report_radar_market_data_shadow.py:6,95-298,564-596,624-662` | complete | agree; `--gate` **defaults to `german`** (`:629-630`) → default must become `us-closes` |
| Frontend protected selected-price path | `hub/priceChart.ts:343`; `hub/selectedPriceGeometry.ts:268-274`; `types.ts:103-105` | incomplete | **missed** `selectedPriceGeometry.ts:273` (`deutsche_boerse_delayed: 'Deutsche Börse (delayed)'`) and `types.ts:105` union member |
| Tests | see §9 | mostly | **missed** `tests/test_radar_board_keys.py:95`, `test_radar_board_store.py:1477`, `test_radar_board_producer.py:254`, `test_radar_board_cache.py:53`, `test_radar_calendar.py:69-70`, `static/radar/src/hub/Admin.test.tsx:21`, `QuoteBadges.test.tsx:24` |
| Templates / deploy | `templates/radar/{hub,board}.html` no market text; tracked units `deploy/radar-encoder-trial.{service,timer}`, `radar-design/perf3-release/radar_board_producer.service` carry no DE env; `sync.bat` dead | complete | agree |
| Out of scope confirmed | Gym German UI, `PRODUCT.md:26,111`, `features/radar/PRODUCT.md:28`, `Europe/Berlin` timezone strings, `format.ts` `de-DE` locale, `data/ordinary_words.txt`, `data/name_shapes.txt:653-654`, `list/Spend.tsx:86` comment, `tests/test_scripts.py:280`, `tests/test_gym_*` | complete | agree |

---

## 4. Deletion-safety matrix (whole-file / module removals)

| File | Surviving importers / callers at HEAD | US runtime role | Safe to delete? |
|---|---|---|---|
| `features/radar/prices/deutsche_boerse.py` | `market_data.py:34` (top-level `FeedRejected`), `run_radar_ingest.py:733` (local import), `scripts/capture_deutsche_boerse_contract.py`, `tests/test_radar_deutsche_boerse.py` | none | yes, **only in the same commit** as the `market_data.py` DE excision (the app blueprint imports `market_data` at `routes/api.py:14`; a dangling import breaks every Radar route) |
| `features/radar/prices/ecb.py` | `run_radar_ingest.py:989` (local), `scripts/backfill_radar_fx.py:16`, `tests/test_radar_ecb.py` | none | yes |
| `features/radar/prices/openfigi.py` | `instruments.py:26`, `run_radar_ingest.py:176` (local), `tests/test_radar_openfigi.py` | none; sole reader of `OPENFIGI_API_KEY` | yes, with `instruments.py` |
| `features/radar/fx.py` | `history.py:281` (local, inside `_converted_basis`), `run_radar_ingest.py:34` (**top-level** import) and `:985`, `scripts/backfill_radar_fx.py`, `tests/test_radar_fx.py` | none | yes, after removing the daemon top-level import and `_converted_basis` |
| `features/radar/reference_universe.py` | `run_radar_ingest.py:174` (local), `tests/test_radar_reference_universe.py` | none | yes |
| `features/radar/market_calendars/de.py`, `tradegate.py` | `market_calendars/__init__.py:18`; `us.py` imports only `SessionBounds` from the package (`us.py:5`) | none | yes, with the registry edit; `_calendar('us', mic=<any US MIC>)` must keep returning `us` (`__init__.py:22-23`) because every US caller passes a MIC (`api.py:120,166,196`, `detail.py:321`, `markets.py:141`) |
| `features/radar/instruments.py` | `market_data.py:32` (`MappingDecision`, `VENUE_BY_MIC`), `prices/finnhub.py:17` and `prices/twelvedata.py:18` (`CatalogInstrument`, used only by their `stock_catalog`), `reference_universe.py:28`, `run_radar_ingest.py:34` (top-level) + `:127,162,183,186,544`, `scripts/report_radar_market_data_shadow.py:118`, tests | `_active_us_instruments:612` is called only from `:567,684,705` inside the module → **no US consumer** | yes, **atomically** with `market_data.py`, `finnhub.py`, `twelvedata.py`, `reference_universe.py`, daemon and report-script edits; otherwise the US quote provider module fails to import |
| `features/radar/data/german_instrument_overrides.json` | `instruments.py:41-42` (`load_overrides`) | none | yes (tracked file) |
| `static/radar/src/board/MarketSwitch.tsx` | `list/ListPane.tsx:5,630`; `board/BoardPage.test.tsx`; CSS `radar.css:396-418,1597` | none | yes |
| `scripts/backfill_radar_fx.py` | none (operator-run) | none | yes |
| `scripts/capture_deutsche_boerse_contract.py` + `tests/test_capture_deutsche_boerse_contract.py` | test only | none | yes; contract evidence remains in `docs/superpowers/specs/2026-08-31-…` |
| `tests/fixtures/radar_market_data/*` (7 tracked files) | DE suites only | none | yes with their suites |
| `features/radar/prices/twelvedata.py` | `run_radar_ingest.py:1063-1064` (`_scheduled_history`, US close writer under `RADAR_US_CLOSE_SOURCE` legacy/shadow), `:142,562,687` (DE, go) | **US** | **must NOT be deleted**; delete only `stock_catalog:138-195`; the `XNAS` default at `:112` is US and may stay |

Proven: no dependency becomes unused (`requirements.txt` unchanged; ECB uses stdlib XML, DBAG uses `gzip`/`json`/`requests` shared with US providers). Agrees with the Researcher.

---

## 5. Shared-US preservation findings

Protected paths are US-only by construction at HEAD and need only the input-contract edit:

- Selected price: `price_chart_reader.py:69-71,79-82` SQL pins `market = 'us'`; `:216,234` refuse anything but a single native-USD US primary; contract `price_chart_contract.py:46` uses `market_calendars.us` directly; `priceChart.ts:343` always sends `market=us`. Reader-level rejection fixtures `tests/selected_price_unit/test_reader.py:59,62` (`currency='EUR'`, `market='de'`) are genuine REJECT-TESTs and stay.
- HA1: `analysis.py:79,95` pin `market='us'`; `:304,310` and `analysis_contract.py:256-278` refuse non-US/non-USD rows; `Hub.tsx:282` already prints "US primary · USD". `ha1_unit` DE/EUR fixtures (`test_analysis_reader.py:126,136,183,200`, `test_analysis_contract.py:190-225`) stay.
- Grouped closes: `market_data.grouped_instrument_map:612-616` filters `market == 'us'`; `test_grouped_ingest_never_touches_a_german_row` (`tests/test_radar_market_data.py:852`) stays as a REJECT-TEST.
- US quote cycle: `_run_us_price_cycle:601-657` → `active_price_tickers` (chatter union + watch list, market-independent, `market_data.py:576-593`) → `_market_instruments(due, 'us'):641`; `claim_post_close` has exactly one caller, US (`run_radar_ingest.py:618`). `_market_instruments:463-471` is shared and must survive; `_xetra_history_instruments:473` and `_mapping_refresh_due:482` go.
- US history: `refresh_history:893-941` and `_yahoo_deep_tail:1002-1050` are US-only; `_scheduled_history:1052-1089` keeps `:1057-1068` and loses `:1070-1088` plus the `de_*` log fields.
- Surgical boundaries the Researcher proposed are sufficient for: `markets.py` (drop the `'de'` literal `:12`, the `expected_currency` map `:176` becomes `USD`, delete `:208-213`; keep `QuoteView`, `classify_quality`, `from_snapshot`); `quotes.py` (single-market read at `:112,117-121,135`; **keep** `_quote_matches` NULL-market/NULL-MIC compatibility `:165-175` and `statuses_for:281-282`, `moves_for:389-390`, because legacy US rows have `market IS NULL`); `history.py` (delete `_converted_basis`; `resolve_basis` keeps native + sibling; sibling is already `market == quote.market`); `leaderboard._quote_sigmas` (delete `:135-149`, keep the batched path `:150-155`); `board.py` (constants at `:560,617`); `board_shared._selection_echo` (`:368,376`); `detail.py` (native basis, `converted_from` always null); `market_calendars/__init__` (see §4).
- `price_provider_config()` (`config.py:832-870`) returns a 3-tuple consumed at `run_radar_ingest.py:733,1055,1376` and by `board_namespace._fingerprint_inputs:171` (`list(...)`); the arity change is safe and intentionally rotates the board namespace (§8). Test `tests/test_radar_daemon.py:1131` monkeypatches a 3-tuple and converts.

---

## 6. Historical schema / data / retention findings

**Every path that can read, write, prune or cascade existing DE/EUR rows at HEAD** (all must stop or be scoped):

Reads: `quotes.quote_views_for:112,117-121,135` (loads DE instruments/quotes on every board), `history._sibling_basis:242-243` and `_converted_basis:270-277` (via a DE quote), `leaderboard._quote_sigmas:135-149`, `run_radar_ingest._german_quote_sample:109`, `_xetra_history_instruments:473`, `_mapping_refresh_due:482`, `_current_de_generation_id:672`, `_de_should_collect:700` (cursor `:715-717`), `market_data.ops_summary:922-941,976` (cycles, generations, `downloads_last_24h:222`), `_all_decisions:567`, `instruments.*`, `scripts/report_radar_market_data_shadow.py:95-298`, `scripts/backfill_radar_market_history.py:50-56`.

Writes: `_legacy_de_poll:685` → `radar_quotes`; `collect_german_cycle:240` → quotes/cursors/cycles/trade events; `materialize_native_closes:509-566` → `radar_daily_closes` (`market='de'` `:559`); `refresh_de_history:943-967` → closes **and** `RadarInstrument.history_due_at` on DE rows (`:963-965`); `refresh_ecb_rates:975` → `radar_fx_rates`; `instruments.refresh_mappings/_upsert_de_row/persist_generation/_apply_generation/activate_generation/rollback_generation` → instruments and generations; both scripts.

Prunes / deletes (**ruling 1 applies to all of these**):

1. **`retention.prune_quotes:257-303`, MISSED by the Researcher.** Ranks by `(ticker, market, mic)` (`:286`) and deletes every row past `keep` and older than `QUOTE_RETENTION_DAYS` (`:292`) with **no market filter**, so historical DE `radar_quotes` rows are deleted nightly (`_scheduled_prune:1168`). Correction: add `sa.or_(RadarQuote.market == 'us', RadarQuote.market.is_(None))` to the ranked subquery. Existing test `tests/test_radar_quote_retention.py:157-175` asserts DE rows *are* pruned to `STALE_QUOTE_POLLS` → must be rewritten to assert the DE rows are untouched.
2. `_prune_daily_closes:123-148` deletes all markets except source `deutsche_boerse_delayed` (`:137-140`). Correction: replace the source exception with `market == 'us' OR market IS NULL`; test `:207-226` (`NATV` row is `market='us'` with DBAG source) must be rewritten to seed a `market='de'` row and assert it survives.
3. `prune_market_data:49-110` drains trade events (48 h) and cycles (14 d). Remove those loops, **but** it is also the only call site of `_prune_daily_closes` and `_prune_massive_shadow` (`:109-110`). If the plan deletes the function wholesale, US close pruning silently stops. Keep a US-only function at the same call site (`run_radar_ingest.py:1174`).
4. `_prune_massive_shadow:185-215` is source-scoped (`massive_grouped`, shadow) and cannot reach DE rows. Unchanged.

Cascades: none. `RadarInstrument.mapping_generation_id` is a plain FK without `ondelete` (`models.py:584-588`; migration `6a21d4e8c9f0:189-193`); no `db.relationship(... cascade=...)` exists on any Radar market table (the only Radar cascades are `RadarPost→RadarMention:636` and the sentiment/watch FKs `:1273,1336`). Deleting any parent model path cannot delete DE rows indirectly. Post/mention/quote/close pruning are the only deleters and are covered above.

Archival schema, what must remain and why:

- All five DE-only ORM classes (`RadarFxRate:999`, `RadarMappingGeneration:1033`, `RadarMarketDataCursor:1063`, `RadarMarketDataCycle:1086`, `RadarMarketTradeEvent:1132`) must stay: `migrations/env.py:49-52` hands Alembic the complete `db.metadata` with no `include_object` filter, so removing a class autogenerates `DROP TABLE`. `RadarMappingGeneration` has a second, harder reason: `RadarInstrument` declares `db.ForeignKey('radar_mapping_generations.id')` (`:586`), and SQLAlchemy cannot configure the mapper without the target table in metadata. Docstrings may be re-worded to "archival"; no column/constraint edits.
- CHECK strings naming `'de'` and `'deutsche_boerse_delayed'` in `models.py:558,889,894-896,962,964-966` must stay: they mirror immutable DDL and `tests/test_radar_models.py` reads constraint names from `__table__` (`:417-420`); `test_radar_models.py`/`test_radar_migration.py` are the only `create_all` users.
- **`deutsche_boerse_delayed` in active Python source sets is NOT required** (ruling 7 answered): the only consumers of `QUOTE_SOURCES`/`CLOSE_SOURCES` are `Quote.__init__` (`prices/__init__.py:98`, reached from `quotes._stored_quote:86` when adapting a stored row) and `history.record_closes:96-97`. ORM loading of `RadarQuote`/`RadarDailyClose` does not validate `source`. The only writers of that source are DE-only (`market_data._quote_for:1001,1005` hard-codes `market='de'`; `materialize_native_closes:559-562` writes `market='de'`), and once the read filters (`quotes._quote_matches`, `statuses_for`, `history._market_filter`) never load a `market='de'` row, no `Quote` with that source can be constructed. Remove it from `QUOTE_SOURCES`, `CLOSE_SOURCES` and `history.CLOSE_SOURCE_PRIORITY:31`; keep only the models.py CHECK strings. `tests/test_radar_models.py:404-415` builds an ORM `RadarQuote` with that source (no validator involved) and stays as archival; `static/radar/src/QuoteBadges.test.tsx:24` fixture converts.
- Sibling reasoning for the `radar_instruments.market` CHECK, the `radar_quotes`/`radar_daily_closes` CHECKs and `radar_provider_session_states` (US uses it via `claim_post_close`): agree with the Researcher.

---

## 7. API / HTML / frontend input-contract findings

Ruling on the Researcher's section 4:

- **HTML `?market=de` opening US is rejected.** `views.py:44-46` and `:72-74` catch `BadQuery` and rebuild with `{}`. After `parse_query` defaults to `us`, a bookmarked German link would silently open the US board. Ruling 2 requires a client error. Narrow safe change: in both HTML routes, before `build_payload`, read `request.args.get('market')`; if present and not `'us'`, return a 400 page. The generic typo fallback for other keys can remain if the Mastermind wants it, but the ruling text ("`market=de` or another unsupported market") also covers `market=moon`; today `tests/test_radar_hub_page.py:85-90` (`?market=moon&window=nonsense` → 200) and `tests/test_radar_api.py:84-99` (`/radar/?market=moon` → 200) assert the opposite and must change to 400. `tests/test_radar_hub_page.py:93-96,113-121` (`market=de` → shell market `de`) become 400 REJECT-TESTs. The Researcher's proposed "`?market=de` → default US shell" conversion must not be written.
- **Frontend URL parsing.** `navigation.ts:232` `pick<Market>(params.get('market'), ['us','de'], fallback.market)` silently falls back for any unknown value; `embedded.ts:41` coerces. Correction: remove `market` from `Selection` (`types.ts:305`), from `boardKeys` (`navigation.ts:149`), from `urlFor`, `api.ts:58-60,173`, `queries.ts:53,76,735-779`, `embedded.ts:41`; the server-side 400 on the shell route is the enforcement point, so the SPA never boots on such a URL. The Researcher's Vitest "`?market=de` in the URL yields the US selection" must be dropped; replace it with tests that `readSelection` has no market field and `urlFor` never writes `market`. `navigation.test.ts:20,27,141-144,290-301` convert.
- **Selected price.** `price_chart.py:46-47` requires `market` (`missing_query`), `:50-51` rejects unknown values (`invalid_market` 400), `:52-54` rejects `de` (`unsupported_instrument` 422). Binding rule: omission→US, explicit non-US→400. Safe change, no compatibility blocker found: keep `ALLOWED_QUERY_KEYS:31` (the client still sends `market=us`, `priceChart.ts:343`); require only `span`; `market = seen.get('market', 'us')`; `if market != 'us': raise ChartError('invalid_market', 400, 'unsupported market')`; the internal `parse_query({'market': 'us', ...})` at `:59` is unchanged. Tests: `test_route_ops.py:60` (`span=1D` → today `missing_query` 400) must become the success path; `:62` unchanged; `:63` → 400 `invalid_market`. Reader/acquisition/rate/geometry code is untouched (`price_chart_reader.py`, `price_chart_acquisition.py`, `prices/alpaca.py` contain no market branching).
- Board / shared board / detail: agree with the Researcher. `Query.market='us'`; delete `default_market:248-263` **together with** the calendar registry edit (it calls `session_state('de', …)` `:261`); `parse_query` raises `BadQuery('unsupported market')` for any value other than `us`; `board_keys.canonical:67` and `query_from_json` accept only `'us'`. `tests/test_radar_api.py:64-82` (`default_market` parametrised clocks) delete; `:104-109,134,877` convert; add omitted→`us`, `market=de`→400, `market=us`→200 on `/api/board`, the shared path and `/api/ticker/<t>`.
- Payload fields: keep `market`/`market_venue`/`identity.quote.*`/`chart.currency`/`basis_venue` with frozen values; `is_fallback` and `converted_from` may stay constant (`false`/`null`), because the observation archive stores these keys and keeping them avoids a payload-shape change; drop `market_data_ops.cycles/mapping_generations/de_download_budget_24h` with `Admin.tsx:100-135` and `types.ts:513-540` in the same commit (see §8 on `PAYLOAD_VERSION`).
- Existing tests that silently map explicit `market=de` to US: none found at HEAD (today `de` is a real board). The hazards are the Researcher's *proposed* conversions above, not existing tests.

---

## 8. Cache/archive versioning and deployment/config findings

Board store: the namespace is `sha256(PAYLOAD_VERSION:revision:fingerprint)` (`board_namespace.py:106-114,136-147`); `revision` is the deployed build revision (`:62-90`) and `fingerprint` includes `list(config.price_provider_config())` (`:171`). Both change with this work, so every deploy of A opens a fresh namespace, old rows (including the four DE warm keys) are never claimed again, and `retire_namespaces` (`board_store.py:362-423`) deletes them after `retire_seconds`. Within an **unchanged** namespace (same revision, e.g. a developer database), a stored `market:'de'` key would be claimed (`claim:572-638`), fail `round_trips` (`board_producer.py:252-257`, via `query_from_json:131-132` or the narrowed market check), be marked failed with backoff (`fail:674-705`) and retried indefinitely. Bumping `KEY_VERSION` (`board_keys.py:34`) makes that rejection explicit by version rather than by field error and is **necessary** (ruling 5). `PAYLOAD_VERSION` (`board_namespace.py:32`) is documented as the marker for payload-shape changes (`:31`); dropping the three `market_data_ops` keys is a shape change, so bump it too for honesty, although namespace rotation by revision already guarantees no old blob is served. Both bumps together with namespace rotation are **sufficient**; no reader enumerates stored keys expecting all to parse (`read_payload:140-188` canonicalises the incoming query first).

Observations: `SCHEMA_VERSION:68` and `MARKETS:70` → `('us',)`; `_queries:120-132`, `_selections:135-146`, `capture:148-186` write `{'us': …}`. No in-repo reader parses `payload_json` by market (`activity.py:85` refers to a different envelope); `latest_observed_at` is a timestamp read. Existing rows are never updated (insert-only, unique `slot_start`, `models.py:1620`). Set `SCHEMA_VERSION = 2` per ruling 5: necessary for analysts, and sufficient because nothing else reads the shape. `tests/test_radar_observations.py:131,163,197,218-223` convert.

Configuration: DE-only environment names and their consumers at HEAD:

| Name | Consumer | After removal |
|---|---|---|
| `RADAR_DE_PRICE_MODE` | `config.py:842` only (validated; refuses startup only on an *invalid* value; a stale valid value is harmless) | code stops reading it; presence does not block startup; remove from production `.env` during the later authorized deployment after backup (name present per release journal `radar-design/artifacts/md-selected-price-alpaca-release/release-unit-38591e0.journal.txt:52`; value unknown) |
| `OPENFIGI_API_KEY` | `prices/openfigi.py:83,97,126` only | unused; deployment carry (journal `:53`) |
| `TWELVEDATA_API_KEY` | `prices/twelvedata.py:27` | **keep** (US history writer under `RADAR_US_CLOSE_SOURCE` legacy/shadow, `run_radar_ingest.py:1060-1065`; production value of `RADAR_US_CLOSE_SOURCE` unknown, name present journal `:55`) |
| `DE_FILES_PER_CYCLE`, `DE_DOWNLOAD_BUDGET_24H`, `DE_THROTTLE_BACKOFF_SECONDS` | Python constants `config.py:1060-1068` → `market_data.py:188-190` | delete; not env |
| `RADAR_DBAG_DELAYED_COOKIE` | documents only (`docs/superpowers/…2026-08-31…`); no code read | not a runtime variable |
| Job ids `radar_de_market_data`, `radar_ecb_fx`, `radar_mappings` | `run_radar_ingest.py:1380-1401` | remove; `radar_history`, `radar_prune`, `radar_board_observations`, `radar_us_quotes`, `radar_us_grouped_closes` survive |
| CLI `--probe-german-data`, `--refresh-mappings` | `:1282-1295` | remove |

No tracked systemd/env file carries a DE variable; `radar_ingest`/`personal_apps_web` units live only on the VPS. The `personal_apps_web` and `radar_ingest` restarts plus `npm run build` (bundle is gitignored) are the deployment units affected; no unit-file change.

---

## 9. Test / residual-search assessment

Dispositions I agree with: DE-only suites listed in Researcher §7 delete with their modules (I confirmed each protects only deleted code); `test_radar_models.py` and `test_radar_migration.py` keep unchanged; `selected_price_unit`, `ha1_unit`, `test_radar_massive.py` stay green with the deliberate route-contract edits (§7).

Incorrect or missing dispositions:

- `tests/test_radar_quote_retention.py:157-175` and `:207-226`: not "rewrite per ruling" in the abstract; both currently assert DE deletion and must assert DE rows untouched (§6 items 1-2).
- `tests/test_radar_hub_page.py:85-96,113-121`, `tests/test_radar_api.py:84-99`: must become 400 REJECT-TESTs, not fallback tests (§7).
- `tests/test_radar_daemon.py:1107-1125` asserts the DE jobs exist → rewrite as "absent"; `:1128-1143` deletes; `:875,905,926,947,980,1047` (`RADAR_DE_PRICE_MODE` monkeypatches) delete with their functions; `:250` (`test_german_quote_failure_does_not_block_us_quotes`) exercises unreachable `poll_quotes` → delete.
- Missed one-line conversions: `tests/test_radar_board_keys.py:95`, `test_radar_board_store.py:1477`, `test_radar_board_producer.py:254` (asserts 4 `de` + 4 `us` warm queries), `test_radar_board_cache.py:53`, `test_radar_calendar.py:69-70` (naive-input case uses `'de'`), `static/radar/src/hub/Admin.test.tsx:21`, `QuoteBadges.test.tsx:24`, `hub/SelectedPriceSection.test.tsx:19-26,45` (`['1D','de']` case; `queries.ts:776-777` market gate collapses).
- `test_radar_board_parity.py` (disposable-DB suite, 10 `'de'` uses, docstring `:14-16`): rewrite as US-only parity; deleting it would drop the only stored-vs-direct parity proof.
- Frontend baseline: the 28 `hub/pending.test.tsx` failures reproduce at HEAD (my run). The acceptance gate must require the Implementer to show the identical failure set at the untouched base and after, not accept the number from continuity; a Vitest run that excludes that file is not "green".
- Smallest sufficient gates: (a) `tests/selected_price_unit tests/ha1_unit tests/test_radar_massive.py` with `--confcutdir` (DB-free), all passing with exactly the two `test_route_ops.py` expectation changes; (b) new REJECT-TESTs: API/shared/detail omitted→us, `market=de`→400, HTML `?market=de`→400, selected-price omitted→200 path and `market=de`→400, `session_state('de')`→`ValueError`, daemon job set excludes the three ids, `quote_views_for` with seeded DE rows returns only USD, `prune_quotes`/`_prune_daily_closes` leave seeded DE rows; (c) `tsc`, `npm run build`, Vitest with the reproduced baseline; (d) autogenerate diff empty on a disposable database (needs the destructive-target opt-in, currently unavailable on this machine); (e) residual sweep below.

Residual-search checklist audit:

- Blind spots: add a pattern for Yahoo `.DE` suffixing (`\.DE'`: `run_radar_ingest.py:952-955`, `backfill_radar_market_history.py:84-86`; not matched by any current pattern), `XETR`/`XGAT` allowlist entries in `yahoo.py:53` and `finnhub.py:26` (matched by the first regex, but the Researcher's expected-residual table does not list them, so a reviewer would wrongly allow them), `SOURCE_WORD` in `selectedPriceGeometry.ts:273`, and the `--gate` default in the shadow report.
- Excessive allowed categories: **B** must not include "`prices/__init__.py` source-name sets" (§6: remove them); **F** (retention DBAG exception) must be deleted because ruling 1 forbids keeping that exception; the filter becomes market-based; **D** correctly lists the `de-DE` locale (see Minor M1).
- Every remaining permitted residual (migrations, `docs/superpowers/**`, `radar-design/**`, models.py CHECK strings and the five archival classes, `test_radar_models.py`/`test_radar_migration.py` fixtures, selected-price/HA1 rejection fixtures, new REJECT-TESTs, word lists, `Europe/Berlin`, Gym) is necessary under one of the four allowed reasons.

---

## 10. Findings

### Critical

**C1: `retention.prune_quotes` deletes historical German quote rows and is missing from the inventory.** `retention.py:257-303` (`partition_by=(ticker, market, mic)` `:286`, `fetched_at < cutoff` `:292`), scheduled at `run_radar_ingest.py:1168`. Violates ruling 1 the first night after A ships unless scoped. Correction for the plan: scope the ranked subquery to `market == 'us' OR market IS NULL`; rewrite `tests/test_radar_quote_retention.py:157-175` to assert DE rows are untouched; add it to the retention slice and to the residual-search checklist ("no retention query without a US market filter").

### Important

**I1: HTML routes and frontend URL parsing must reject, not normalize.** `views.py:44-46,72-74`; `navigation.ts:232,283-285`; `embedded.ts:41`. Correction: explicit `market` pre-check → 400 on `/radar/`, `/radar/hub/`, `/radar/legacy/`; remove the `market` key from the SPA; replace the Researcher's fallback tests (`test_radar_hub_page.py:85-96,113-121`, `test_radar_api.py:84-99`, proposed Vitest normalization case) with 400 tests. Mastermind decision needed only on whether non-market typos keep the friendly fallback.

**I2: Selected-price contract must accept an omitted market.** `price_chart.py:46-54`. Correction as in §7; two deliberate test edits (`test_route_ops.py:60,63`); acquisition/reader untouched. No compatibility blocker.

**I3: Retention call chaining.** `prune_market_data:49-110` is the only caller of `_prune_daily_closes` and `_prune_massive_shadow` (`:109-110`); deleting it as "DE-only" stops US close pruning. Correction: keep a US-only entry at `run_radar_ingest.py:1174`; change `_prune_daily_closes:137-140` to a market filter; rewrite `test_radar_quote_retention.py:207-226`.

**I4: Import-chain atomicity for the mapping/collector deletions.** `market_data.py:32,34`, `finnhub.py:17`, `twelvedata.py:18`, `reference_universe.py:28`, `run_radar_ingest.py:34` (top-level `fx`, `instruments`), `routes/api.py:14`. Correction: the plan must state that `instruments.py`, `prices/deutsche_boerse.py`, `prices/openfigi.py`, `reference_universe.py`, `fx.py` are deleted in the same commit as the edits to `market_data.py`, `finnhub.py`, `twelvedata.py`, `history.py` and the daemon import list, with `python -c "import app"` and `import run_radar_ingest` as the gate; `_active_us_instruments` is deleted (ruling 6 confirmed, no US consumer).

**I5: Missed residuals in protected/shared code.** `selectedPriceGeometry.ts:273` (`SOURCE_WORD.deutsche_boerse_delayed`; `sourceWord` falls back to the raw string, so deleting the entry is safe), `types.ts:105` (`QuoteSource` union), `finnhub.py:26` (`'XETR': 'DE'`, goes with `stock_catalog`), `yahoo.py:53` (`'XETR'` allowlist entry; no US caller can pass `XETR`; delete with `:358`), `yahoo.py:6` docstring, `Admin.test.tsx:21`, `QuoteBadges.test.tsx:24`, the four board test files and `test_radar_calendar.py:69-70` (§9), `scripts/report_radar_market_data_shadow.py:629-630` (`--gate` default `german` → `us-closes`). Add all to the inventory and residual table.

**I6: Active source vocabulary.** Remove `deutsche_boerse_delayed` from `prices/__init__.py:23-30` and `history.py:31`; keep only the `models.py` CHECK strings (§6). Correct the Researcher's ARCHIVAL disposition for `prices/__init__.py` and category B.

**I7: Versioning mechanics.** `KEY_VERSION` bump necessary; `PAYLOAD_VERSION` bump recommended because `market_data_ops` keys are dropped; `SCHEMA_VERSION = 2` for observations; namespace rotation by revision + fingerprint is what actually retires stored DE boards (§8). Record all three in the plan.

**I8: DE-row writer not classified as such.** `refresh_de_history:963-965` updates `RadarInstrument.history_due_at` on DE rows; it goes with the function, but the inertness table must list `radar_instruments` DE rows among the rows whose last writer is removed.

### Minor

**M1** `format.ts:284-294` `formatPrice` uses the `de-DE` locale for USD (renders `194,20 $`); a locale, not a market, and out of A's binding scope; the owner may separately decide on `en-US`. **M2** `data/name_shapes.txt:653-654`, `data/ordinary_words.txt` tokens: word lists, category D. **M3** `board.py:157-159` Xetra-gap comment inside generic `_next_boundary`: comment cleanup. **M4** `test_radar_board_parity.py` docstring `:14-16` describes German fixtures: rewrite with the suite. **M5** The Researcher's "= origin/main" statement is repository-report evidence; this worktree's remote refs list only `origin/codex/radar-selected-price-charts` at 38591e0. **M6** `hub/queries.ts:776-777` `market === 'us'` gate becomes constant: simplify with the `Selection` change.

---

## 11. Not verified, and why

- Production database contents (DE row counts, whether any US row carries `source='deutsche_boerse_delayed'`), production `.env` values, VPS systemd units: no production/DB access authorized; counts are quoted from `US-USD-ONLY-DECISION.md`/`US-UNIVERSE-REFRESH-2026-09-16.md` and names from the committed release journal.
- DB-backed pytest suites (API, hub page, quotes, history, detail, leaderboard, retention, board store/producer/parity, migration, observations): `tests/conftest.py:1-2` binds them to the real local development database and the destructive suites require an opt-in target that is not configured; DB identity could not be proved disposable, so none was run.
- Whole Vitest suite, `tsc`, `npm run build`: only `hub/pending.test.tsx` was run (to verify the baseline claim); the other frontend claims are code-read.
- Alembic autogenerate diff: needs a disposable database (unavailable).
- No provider/network call was made.

---

## 12. Actions confirmation

- Created exactly one file: `radar-design/A-US-USD-ONLY-VERIFY-1-RETURN.md` (this return).
- No application, test, migration, script, config, dependency, environment, spec, ledger or handoff edit; no file deleted or moved; no formatter; no commit, push, deployment, service, flag, credential or provider action; no implementation plan written; no worker dispatched; no subagents.
- Commands executed were read-only Git inspection, static searches, one Vitest file run and one DB-free pytest file run with `--confcutdir` and `-p no:cacheprovider` (bytecode caches under ignored `__pycache__`/`node_modules` only). `git status --short` after the runs shows the same pre-existing dirty/untracked set as before, plus this return file.

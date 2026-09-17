# A-US-USD-ONLY-REVIEW-1 — independent Reviewer/QA return

Date: 2026-09-17
Role: Reviewer/QA (Claude Opus 5, fresh task, no subagents)
Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
Branch / HEAD: `codex/radar-selected-price-charts` / `38591e0f5e98faccb5228d84d1677843fcdb2aea` (HEAD = base; candidate is the uncommitted working tree)

## Verdict

**FIX REQUIRED BEFORE A ACCEPTANCE**

There are no Critical findings and one Important finding (I1). I1 is a one-line test correction. It changes no runtime behaviour and does not affect any user. Everything else in the candidate is sound on the evidence below. After I1 is fixed, only that single test file needs a focused check. The whole candidate does not need another review.

## Independence attestation

1. I did not implement `A-US-USD-ONLY-IMPLEMENT-1`.
2. I did not perform `A-US-USD-ONLY-RESEARCH-1` or `A-US-USD-ONLY-VERIFY-1` in this task or session.
3. I had not reviewed this candidate before this task.

---

## Findings

### Critical

None.

### Important

**I1 — A passing frontend test keeps the retired DBAG source code as rendered text.**
- **Where:** `personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts:140-145`. The failing expectation is at line 144: `expect(sourceWord('deutsche_boerse_delayed')).toBe('deutsche_boerse_delayed')`.
- **Why it breaches the rules:**
  - The test was added by this candidate. It asserts that `sourceWord()` returns the retired token verbatim, which `SelectedPriceChart.tsx:131,158,186,190` and `Admin.tsx:164` would print as visible text.
  - It is not a rejection test, and it does not prove the value is withheld. It would fail if the UI stopped showing the retired code.
  - VERIFY-1 ruling 7 keeps `deutsche_boerse_delayed` only in immutable migrations and ORM CHECK strings. The plan's Task 5 residual rule allows only intentional rejection tests; every other hit counts as a defect. The review prompt adds that a passing test which preserves retired behaviour is not automatically allowed. This is the only remaining occurrence of the token in active TypeScript, test files included.
- **Impact:** None at runtime. The token cannot reach `sourceWord()`:
  - `price_chart_reader.py:71,82` read only rows where `market = 'us'`.
  - The token has been removed from `QUOTE_SOURCES` and `CLOSE_SOURCES` in `prices/__init__.py`, from `history.CLOSE_SOURCE_PRIORITY`, from the TypeScript `QuoteSource` type and from `SOURCE_WORD`.
  - Admin `ops.source` only ever holds `alpaca_sip`, `yahoo_chart` or null.
  - The built bundle contains no occurrence of `deutsche_boerse`.

  The defect is a binding-rule breach inside a test contract only.
- **Smallest fix (test only):** On line 144, replace the retired token with a neutral unknown code, e.g. `expect(sourceWord('some_future_feed')).toBe('some_future_feed')`. Adjust the test title and comment on lines 140 and 143 to match. Leave `sourceWord()` unchanged. Then run `npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts` and repeat the TypeScript residual sweep for `deutsche`.

### Minor (non-blocking)

**M1 — A duplicated `market` parameter is resolved silently, first value wins.**
- **Where:** `routes/api.py:259` (`args.get('market') or 'us'`) and `routes/views.py:29`.
- **Behaviour:**
  - `?market=us&market=de` opens the US board with status 200 on `/radar/api/board`, `/radar/api/ticker/<t>` and the HTML routes.
  - `?market=de&market=us` returns 400.
  - The selected-price route already rejects duplicates (`duplicate_query`, 400).
- **Scope:** Only hand-crafted URLs can produce this. Old clients sent a single `market` value, and first-value-wins is the existing behaviour for every board parameter.
- **Optional fix:** Reject the request when any value in `args.getlist('market')` is outside `('', 'us')`, in both places.

**M2 — `ChartHover` keeps an unused `currency` prop.**
- **Where:** `static/radar/src/detail/ChartHover.tsx:51-54` (`currency = 'USD'`, typed `string`).
- **Why it matters:** `money()` now always renders dollars, so a future caller passing a non-USD code would be printed with `$` without warning. No caller passes the prop today (`PriceChart.tsx:223`).
- **Optional fix:** Delete the prop.

**M3 — The evidence narrative does not quite match the saved JUnit files.**
- **The claims:**
  - `checkpoints.md` (Task 1) says the owner addendum was applied before Task 1 closed.
  - Return §3 and §9 say the final DB identity set is identical to the post-Task-4 run.
- **What the files show:**
  - `task5/radar-db-post.xml` (01:31) still contains the pre-addendum tests `test_the_warm_set_is_four_selections_nobody_typed` and `test_the_four_warm_hashes_do_not_move_with_the_clock`.
  - `radar-db-final.xml` (01:44) has the "eight" versions of both.
  - So the addendum landed after the post run.
  - The non-pass sets are identical, which I checked independently. The full identity sets differ only by these two renamed passing tests.
- **Coverage:** The final run and my own run both cover the addendum.
- **Optional fix:** Correct the wording in continuity only. No code change.

**M4 — A doc comment was dropped by accident.**
- **Where:** `static/radar/src/hub/chatterSort.ts:207`.
- **What happened:** The doc comment for `knownCount` ("How many of the loaded rows this key could actually order…") was deleted together with `priceCurrencies`.
- **Optional fix:** Restore the comment.

**Pre-existing, not a candidate regression (reported for the record):**
- **Arctic Shift DNS lookups from DB-backed tests.** Without a guard, these tests try to reach `arctic-shift.photon-reddit.com`: 204 attempts from `test_radar_daemon.py`, whose `main()` Arctic Shift probe is unchanged by the diff, and 34 from other suites. My guard refused all 238. None was a price provider.
- **Known debt.** F1 (the unguarded activity migration test) and F5 (residue left in the clone) are pre-existing and were not touched.

---

## Mandatory residual rulings

### R1 — `features/radar/config.py:533,539` `mauerstrassenwetten` in `REDDIT_SUBS`

**Ruling: legitimate. This is chatter-source configuration outside A's market-price boundary. No finding.**

- **Scope basis:**
  - The owner decision (`US-USD-ONLY-DECISION.md`) is to "Remove German/EUR *market-price* functionality". Every item in its scope list concerns prices, providers, mapping, selectors, EUR display or fallback.
  - The spec's in-scope line is "every active German/EU market-price path inside Radar". The spec also keeps unrelated German-language functionality and excludes ranking or source changes.
  - The subreddit is a deliberate owner source decision dated 2026-09-02. The config comment says "regional ones except the German WSB stay out".
- **Reachability:**
  - `REDDIT_SUBS` feeds `build_fetchers`, the `radar_reddit` job (`run_radar_ingest.py:994`, Arctic Shift reader) and `retire_untracked('reddit', REDDIT_SUBS)` (`:139`).
  - Mentions are resolved only against `TickerUniverse` (`universe.load_lookup`, the US Nasdaq directory), so the source can only add chatter to US identities. Those identities are then priced only by the US/USD paths.
  - `config.expand_sources` exposes `reddit:mauerstrassenwetten` as a valid concrete source.
- **User-visible impact:**
  - `chatterPresentation.ts:262` shows `r/mauerstrassenwetten` as a venue label, and German-language post excerpts appear as chatter evidence.
  - The subreddit brings no market selector, German listing, exchange, EUR amount, conversion or German price.
  - Its known ticker-collision risk is a chatter-quality matter.
- **If the owner wants no German-language chatter at all:** that is a new source-list decision, a one-line config change handled by `retire_untracked`. It would change populations and rankings, so it does not belong in A.

### R2 — `static/radar/src/hub/selectedPriceGeometry.test.ts` and `deutsche_boerse_delayed`

**Ruling: breach.** The test is a positive contract to render the retired code, not a legitimate rejection test. It is reported above as **I1**, with the smallest fix.

---

## Conclusions by area

### Public contract and cache/archive identity — PASS (apart from M1)

- **Omitted market means US.**
  - `Query.market='us'`; `parse_query` treats `args.get('market') or 'us'` as US; `default_market` was deleted.
  - The HTML routes `/radar/`, `/radar/hub/` and `/radar/legacy/` call `_refuse_unsupported_market` (`views.py:59,85`) before the friendly `BadQuery` fallback. That fallback still serves malformed non-market filters.
  - JSON board and ticker routes return `{"error": "unsupported market"}` with status 400.
  - My tests: the api and hub_page suites passed, except the one baseline failure `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`.
  - Playwright showed a real 400 page reading "unsupported market: Radar shows US listings only…", with no hub mounted.
- **Selected price** (`price_chart.py:47-52`):
  - `span` is still required.
  - An omitted market means US; `market=us` is accepted; any other value returns `invalid_market` with status 400.
  - An empty `market=` also returns 400 (strict, and the frontend never sends it).
  - Acquisition, reader, admission and geometry code are untouched, and 261 selected-price tests passed.
- **Stored identity versions:**
  - `KEY_VERSION=3` (`board_keys.py:37`): the market must be US in both `canonical` and `query_from_json`. A v2 key fails the version check, and the producer records that as a per-key failure rather than crashing.
  - `PAYLOAD_VERSION=2` (`board_namespace.py:33`).
  - `SCHEMA_VERSION=2` with `MARKETS=('us',)` (`observations.py:71`). Old rows are not rewritten.
- **Warm boards** (`board_producer.py:72-77`):
  - `WARM_MARKETS=('us',)`, `WARM_SEGMENTS=('', DEFAULT_SEGMENT)`, `WARM_WINDOWS=(1,4,12,24)`; `warm_limit` stays 8 (`board_store.py:118`, no diff).
  - `test_the_warm_set_is_eight_us_selections_nobody_typed` proves 8 unique keys, all US, both parser-normalised segment selections, windows `[1,1,4,4,12,12,24,24]`, and a key identical to the bare-URL parse.
  - The readiness and claim tests remain in the refused destructive suites.

### Historical data and retention — PASS

- **No schema changes:** `git diff -- personal_apps/models.py personal_apps/migrations` is empty and the index is empty.
- **Quote pruning:** `prune_quotes` uses `_ranked_quotes()` (`retention.py:234,253-263`). The `market='us' OR market IS NULL` filter is inside the ranked subquery, which is proven by compiled SQL in `test_the_ranked_prune_input_is_us_scoped_before_ranking`.
- **Close pruning:**
  - `prune_closes` = `_prune_daily_closes` (US/NULL scoped) + `_prune_massive_shadow` (only `massive_grouped` shadow rows).
  - All removed deletion code was DE-only: event/cycle pruning and the source exception.
  - DE quotes and closes survive retention, and archived trade events and cycles are untouched; my retention tests (14) passed.
- **Legacy NULL-market rows are US:** migration `a4c8e2f19b70` backfilled every ticker-only row as `us`/`USD`.
- **Writers:**
  - `quotes.record_quotes` validates the whole batch before adding any row.
  - `history.record_closes` refuses non-US or non-USD rows before any write.
  - The grouped-close write keeps `commit=False` plus a single commit/rollback (`market_data.py:283-303`). Its only currency input is US instrument rows, which are seeded as USD.
- **Reads:** Every active read path refuses a non-US identity and never loads archived rows: `quote_views_for`, `_quote_matches`, `statuses_for`, `moves_for`, `history._market_filter`, `resolve_basis`, `_sibling_basis`, `intraday_chart_for`, `select_quote` and `QuoteView.from_snapshot`.
- **Other deletes:** No deletes remain against DE tables. `board_store.retire_namespaces` removes only board cache namespaces; the observation archive is not deleted.

### Atomic runtime removal — PASS

- **Deleted modules:** A fresh import of `app`, `run_radar_ingest`, both scripts and the three route modules succeeds. `fx`, `instruments`, `reference_universe`, `prices.deutsche_boerse`, `prices.ecb`, `prices.openfigi`, `market_calendars.de` and `market_calendars.tradegate` all raise `ModuleNotFoundError`.
- **No remaining importers:** An importer sweep across the worktree (excluding radar-design and docs) found none.
- **Daemon:** No attribute names German, `_de_`, ECB, mapping, Xetra or FX. The job set is exactly the US set (`test_the_us_market_data_jobs_register_and_no_german_job_does` passed).
- **Configuration:** `price_provider_config()` returns 2 values and ignores a stale or invalid `RADAR_DE_PRICE_MODE`. `OPENFIGI`, `RADAR_DE_`, `refresh-mappings` and `probe-german` appear only in rejection tests.
- **Protected US paths:**
  - Twelve Data quotes/history and `TWELVEDATA_API_KEY` are kept.
  - The Yahoo XETR allowlist entry and EUR identity were removed; the Yahoo US paths are kept.
  - The Finnhub and Twelve Data `stock_catalog` functions were removed.
- **Ops and scripts:** The ops summary is US-only (`quote_basis_24h`, `grouped_closes`, `post_close_claims`). The scripts offer only `us`/`us-universe` and `us-closes`.
- **Removed daemon tests:** They covered `poll_quotes`, which was already unscheduled dead code at HEAD, or DE-only behaviour.

### Frontend and USD formatting — PASS (apart from I1, M2 and M4)

- **Market dimension removed:**
  - `Selection.market` is gone, along with `MarketSwitch`, the hub market select and market keys in URLs, requests and caches.
  - The detail and price-chart keys carry no market; the protected price-chart client still sends `market=us`.
  - `readSelection` ignores `market` by design (plan Task 4). The server gate is the only enforcement, and `hub.html` and `board.html` are rendered only by the two gated routes. `popstate` only replays URLs written by the SPA, which contain no market.
- **Embedded payloads:** A payload naming any market other than US is refused (`embedded.ts:40`). Playwright check: the hub then shows "The board embedded in this page was unreadable" and does not relabel the payload.
- **Strict USD:**
  - `formatPrice` renders en-US USD and shows UNKNOWN for anything else; `usdText` shows the bare number for a null currency and UNKNOWN for any non-USD value.
  - Adversarial Playwright case with EUR-currency rows: the overview showed `— +1.2%` with 0 dollar signs, and chatter list rows showed `—` with no `€` or `EUR`.
  - `de-DE` remains only for the Berlin clock and locale comments.
- **Vitest:** 913 total, 885 passed, 28 failed. My failing identities are identical to the saved HEAD baseline and to the implementer's post run: all 28 are in `hub/pending.test.tsx`, with no additions or removals.
- **Changed-test sweep:** Every frontend test that keeps DE or EUR tokens is an absence or rejection assertion, except I1.

### Protected US behaviour — PASS

- Protected suites under an outbound-socket guard: selected-price 261, HA1 241 and Massive 18 passed, with 0 outbound attempts.
- In my DB run: grouped-close tests (23), basis (23), retention (14), quotes (37), quotes_batch (13), history (27) and history_basis (10) all passed. The 3 Yahoo `daily_closes` failures are date-dependent baseline failures.

---

## Commands and results (all executed by me in this task)

From `personal_apps/`, with `PYTHONDONTWRITEBYTECODE=1`.

**Required gates**

| Command | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npx vitest run -c vite.radar.config.ts` (JSON reporter to scratch) | 913 / 885 / 28, exit 1. Failing identities == `baseline/vitest-radar-pre.json` == `task4/vitest-radar-post.json` (set comparison True, both differences empty) |
| `npm run build` | exit 0; `hub-vKJ17uRt.js`, `board-DF-2RG95.js`, `embedded-DUY_46Ar.js`, `hub-Czy1AMuW.css`. Rewrote only the git-ignored `static/*/dist` |
| `py -3.12 <guard> tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | 261 passed; 0 outbound attempts |
| same for `tests/ha1_unit` | 241 passed; 0 outbound attempts |
| same for `tests/test_radar_massive.py --confcutdir=tests/selected_price_unit` | 18 passed; 0 outbound attempts |

`<guard>` is a scratch runner: in-process pytest with every non-loopback `connect`/`getaddrinfo` refused. It does not change the environment passed to child processes.

**DB-backed checks (disposable clone only)**

Target proof, printed before any test ran:
- engine `mysql+pymysql://***@localhost:3306/personal_apps_radar_wt`
- server `select database()` = `personal_apps_radar_wt`
- MySQL 8.0.46, 47 base tables, **0 FKs**, Alembic `b7e3f9c1a2d4`
- `RADAR_DESTRUCTIVE_TEST_TARGET` = None

How the wrapper stayed safe:
- It re-pins `PERSONAL_DB_NAME` after every dotenv load and removes any destructive opt-in.
- It refuses non-loopback sockets.
- It exits before running any test unless the URL and the server database both name the clone.
- Credentials were never printed or read into output.

| Run | Result |
|---|---|
| 27 changed suites (api, hub_page, board_keys, board_producer, board_namespace, board, board_cache, board_store, board_shared_api, board_parity, observations, calendar, markets, quotes, quotes_batch, history, history_basis, detail, leaderboard, phrasing, daemon, market_data, market_data_report, quote_retention, operations_api, prices, yahoo) | **693 passed / 5 failed / 159 errors** in 80 s |
| `test_radar_daemon.py` alone | 63 passed; 204 refused Arctic Shift DNS lookups |
| 11-suite subset | 353 passed / 5 failed / 29 errors; 34 refused Arctic Shift DNS lookups |

What the 27-suite run shows:
- Statuses are identical to the implementer's `task5/radar-db-final.xml` on all 857 shared identities, and no identity from those files is missing.
- The 5 failures are baseline identities: `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`, `test_active_price_tickers_is_the_union_of_the_three_windows` and three Yahoo `daily_closes` tests.
- All 159 errors are the "destructive Radar work is not opted in" setup refusal.
- The 238 refused outbound attempts were all `arctic-shift.photon-reddit.com` DNS lookups (pre-existing code).

I deliberately did not run `test_radar_activity.py` (F1, the unguarded downgrade/upgrade test). I did not rerun the full `-k radar` set.

**Other checks**

- **Reconciliation of the implementer's JUnit files:**
  - Baseline 1849/14/220/1; post and final 1698/12/193/1.
  - One status change on a shared identity: `test_radar_activity::test_the_migration_adds_and_removes_only_its_own_two_tables`, failure at baseline → passed. This is the F1 side effect.
  - 34 non-pass identities disappeared: that activity test, the renamed `test_human_page_bad_market_falls_back_to_the_default_payload`, and 32 DE or omitted-market parity refusals.
  - 5 new non-pass identities: all parity setup refusals.
  - All 12 final failures are baseline identities, and all 193 final errors are refusals.
  - 264 passing identities were removed. Most were in deleted DE-only suites (`calendar_de` 31, `deutsche_boerse` 36, `ecb` 7, `fx` 7, `instruments` 22, `openfigi` 27, `reference_universe` 32); the rest were in converted suites, and I inspected every removed or renamed test function (see M3 for post vs final).
- **Edge probe** (direct calls, no DB):
  - Board: `{}`, `market=` and `market=us` all resolve to US; `[us,de]` resolves to US (M1); `[de,us]` raises `BadQuery`.
  - Chart: `span` alone is accepted as US; `market=` returns 400; duplicates return 400; a missing `span` returns 400.
- **Residual sweeps:** the plan's three `rg` patterns over `features`, `run_radar_ingest.py`, `scripts`, `static/radar/src`, `radar.css` and `templates` (non-test files).
  - Only allowed hits: quizbank prompt text, the `ordinary_words` and `name_shapes` word lists, Tips `€`, `lang="de"` in Gym, Tips and Auth templates, `de-DE` clock comments, the `SIDE_BY_SIDE`/`INCLUDE_PREPOST` regex false positives, `PRODUCT.md`, and `config.py:533` (R1).
  - Test-file sweep: every hit is a rejection or inertness proof, or a model/migration fixture, except I1.
- **Git checks** (after my runs, before this file): `git diff --check` exit 0 (CRLF warnings only, on pre-existing continuity documents); index empty; `git status --short` shows 182 entries, the same as at the start.

## Screenshots inspected and visual/accessibility ruling

I reran the implementer's harness from a scratch copy, so its evidence directory was not overwritten. The copy writes its outputs to scratch and adds a Chromium-level route that aborts any non-loopback request, plus three reviewer cases.

- **Result:** 29 cases, 184 checks, 0 failures; 0 refused outbound attempts (Python and Chromium); 0 unmocked API calls; 27 PNGs.
- **Viewed fresh:**
  - `real-400-1200`, `real-hub-1200`, `real-hub-390`, `real-legacy-320`, `real-admin-390`
  - `fixture-chatter-AAPL-1200`, `fixture-chatter-AAPL-390`, `fixture-chatter-AAPL-320-chart`, `fixture-research-AAPL-320`, `fixture-overview-390`
  - `review-embedded-de-1200`, `review-eur-chatter-1200`
  - Implementer-saved `real-legacy-1200`, for consistency.

**Ruling: PASS.**
- No market control, and no gap where one used to be. The legacy wordmark sits directly next to the search box.
- No Germany, EUR, fallback or conversion copy.
- Prices appear as `$330.46`, `$431.18` and `$7.39`, and chart gutters as `$331.70` / `$329.99`.
- The US provenance line reads "NASDAQ · USD · XNMS · quoted … Berlin · delayed", and the Alpaca SIP provenance is intact.
- The selected-price chart draws at 1200, 390 and 320 (panned at 320).
- A 40-stop tab walk found no hidden tab stop and no market tab stop, and focus rings are visible.
- No horizontal overflow at 1200, 390 or 320.
- The top bar names "US markets" at desktop width; on mobile it shows the session only, by design.

**Notes:**
- The 400 page is Werkzeug's unstyled default "Bad Request" page. It is clear and meets the "human-readable 400" ruling.
- The "Find a compa" placeholder truncation at 320 px predates A.

## Unavailable gates and remaining risk

- **Destructive suites:** board store, producer readiness/claims, shared API and parity: 159 refused in my run. The HA1 analysis API and migration suites were refused in the implementer's full run. No registered target exists, and I did not set or invent one. The converted tests were inspected but never executed, including the US-only parity rewrite with inert archived rows and readiness at 8 warm boards.
- **Alembic autogenerate diff and FK/migration parity:** not run. The clone has 0 FKs, which is the known limitation.
- **Full `-k radar` DB run:** not rerun by me. I ran only the 27 changed suites and deliberately excluded F1.
- **Pre-existing debt:** F1 (unguarded migration test), F5 (clone residue grows with each run) and Arctic Shift DNS lookups from unguarded test runs.
- **Deployment carries (unchanged):**
  - Back up the production `.env`, then remove `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY`.
  - Restart `radar_ingest` and `personal_apps_web` with a fresh build.
  - The namespace rotates through `PAYLOAD_VERSION` 2, and v2 keys are retired by `KEY_VERSION` 3.
- **Workstream B:** 146 unmapped US identities and 51 changed entries. A has no instrument writer.

## Actions and protected state

- **Written:** only this file, `radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md`.
- **Outside the repository:** scratch harnesses, logs and PNGs are in the session scratchpad. `npm run build` refreshed the git-ignored `dist`. Nothing else was written.
- **Not done:** no fix, no test/application/continuity edit, no dependency install, no reading of credential values, no environment-file change, no historical-row mutation, no provider contact, no service/production/VPS action, and no stage, commit, push or deploy.
- **Disposable clone:** my non-destructive DB tests created and removed their own prefixed rows there, and ran the retention prune on its data (the known F5 behaviour).
- **Protected:** `personal_apps` and production were never bound. `models.py` and `migrations/` have no diff. The implementer's evidence files are unmodified (checked by mtime and count). All pre-existing dirty and untracked work is preserved.

---

## Copy/paste Mastermind prompt

```text
You are Radar's Mastermind / Overview. Assess this Reviewer/QA return for assignment A-US-USD-ONLY-REVIEW-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / 38591e0f5e98faccb5228d84d1677843fcdb2aea / 38591e0f5e98faccb5228d84d1677843fcdb2aea (the candidate is uncommitted)
Working tree: unchanged from the start of the review (182 status entries: the implementer's uncommitted personal_apps delta of 115 modified and 27 deleted paths, plus pre-existing continuity and evidence dirt), plus this new untracked return file. The index is empty. Nothing is committed, pushed or deployed. models.py and migrations/ have no diff.
Binding artifacts: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/{A-US-USD-ONLY-SPEC.md, A-US-USD-ONLY-RESEARCH-1-RULING.md, A-US-USD-ONLY-VERIFY-1-RULING.md, A-US-USD-ONLY-PLAN.md, A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md, A-US-USD-ONLY-LEDGER.md, A-US-USD-ONLY-IMPLEMENT-1-RETURN.md, A-US-USD-ONLY-IMPLEMENT-1-RULING.md, A-US-USD-ONLY-REVIEW-1-RETURN.md}; evidence in radar-design/artifacts/a-us-usd-only-implement-1/

Independence: fresh task. I did not implement IMPLEMENT-1, did not perform RESEARCH-1 or VERIFY-1 in this session, and had not reviewed this candidate before. No subagents.

VERDICT: FIX REQUIRED BEFORE A ACCEPTANCE (one Important finding, test-only, no runtime impact; no Critical findings).

Findings
- IMPORTANT I1: personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts:140-145 (line 144) asserts sourceWord('deutsche_boerse_delayed') === 'deutsche_boerse_delayed'. That is a positive contract to render the retired DBAG code as visible text, not a rejection test. It breaches VERIFY-1 ruling 7 and the plan's Task 5 residual rule, and it is the only remaining active TypeScript occurrence of the token. Runtime impact is none: price_chart_reader.py:71,82 read only market='us' rows, the source vocabularies no longer contain the token, and Admin ops.source is alpaca_sip, yahoo_chart or null. Smallest fix: on line 144 use a neutral unknown code (e.g. 'some_future_feed') and adjust the title/comment; leave sourceWord unchanged. Then run a focused Vitest on that file and repeat the TypeScript 'deutsche' sweep.
- MINOR M1 (optional): routes/api.py:259 and routes/views.py:29 use args.get, so ?market=us&market=de silently serves US (status 200) on the board API, ticker API and HTML routes, while ?market=de&market=us returns 400. Only hand-crafted URLs can do this. Optional fix: reject when any args.getlist('market') value is outside ('', 'us').
- MINOR M2 (optional): detail/ChartHover.tsx:51-54 keeps an unused `currency` prop even though money() is now dollars-only. Delete it.
- MINOR M3 (continuity wording): task5/radar-db-post.xml (01:31) still contains the pre-addendum "four warm" test names; final (01:44) has "eight". The addendum therefore landed after the post run. Non-pass sets are identical, and only two passing identities differ (renames). Correct the checkpoints and return wording; no code change.
- MINOR M4 (optional): chatterSort.ts:207 lost the knownCount doc comment when priceCurrencies was removed.
- Pre-existing, not the candidate's: unguarded DB tests try Arctic Shift DNS lookups (238 refused by my guard; none was a price provider). F1 and F5 debt unchanged.

Mandatory residual rulings
- R1 config.py:533,539 mauerstrassenwetten: LEGITIMATE, no finding. The owner decision and the spec scope A to market-price functionality; the spec keeps unrelated German-language functionality and excludes source/ranking changes; the 2026-09-02 owner source decision is recorded in the comment. Reachability: REDDIT_SUBS feeds the radar_reddit job (Arctic Shift) and retire_untracked. Mentions resolve only against the US TickerUniverse and are priced only by US/USD paths. Visible impact: an "r/mauerstrassenwetten" venue label and German-language post excerpts; no selector, listing, EUR or German price. Removing it would be a separate owner source-list decision, not part of A.
- R2 selectedPriceGeometry.test.ts: BREACH, reported as I1.

Conclusions
- Contract: omitted market is US everywhere. Explicit non-US returns 400 on the JSON routes and on the HTML routes before the friendly fallback, which still serves non-market typos. Selected price requires span, treats omitted market as US and returns invalid_market/400 otherwise; its acquisition, reader, rate limits, fallback and geometry are unchanged (261 passed). KEY_VERSION=3 (market must be US both ways), PAYLOAD_VERSION=2, SCHEMA_VERSION=2 with MARKETS=('us',).
- Warm boards: exactly 8 US queries (All plus the default Discover selection, windows 1/4/12/24); warm_limit 8. Readiness and claim tests are in the refused destructive suites.
- Retention and history: prune_quotes has its US/NULL filter inside the ranked subquery (proven on compiled SQL); prune_closes keeps US close and Massive-shadow pruning; DE quotes, closes, events and cycles survive. Writers refuse non-US or non-USD rows before writing. Legacy NULL rows are US per migration a4c8e2f19b70. There is no schema, model, migration or historical-row change.
- Atomic removal: all imports succeed; the 8 deleted modules raise ModuleNotFoundError; no importer remains; the daemon has no DE, ECB or mapping symbols or jobs; a stale or invalid RADAR_DE_PRICE_MODE is ignored; the Twelve Data, Yahoo US, Finnhub, Massive and Alpaca paths are kept; ops and scripts are US-only.
- Frontend and USD: the market dimension is removed end to end, and the price-chart client still sends market=us. An embedded non-US payload is refused ("unreadable" page). formatPrice and usdText are strict; an adversarial EUR row renders "—" with no $ or EUR. de-DE remains only for the Berlin clock.
- Protected US: selected price 261, HA1 241 and Massive 18 passed with 0 outbound attempts; grouped-close, basis, quote, history and retention suites passed on the clone.

Commands and results (my own execution, from personal_apps/, PYTHONDONTWRITEBYTECODE=1)
- npx tsc --noEmit: exit 0
- npm run build: exit 0 (hub-vKJ17uRt.js, board-DF-2RG95.js, embedded-DUY_46Ar.js, hub-Czy1AMuW.css)
- npx vitest run -c vite.radar.config.ts: 913 total / 885 passed / 28 failed. The failing identity set exactly equals the HEAD baseline and the implementer's post run (28, all in hub/pending.test.tsx).
- Guarded pytest: selected_price_unit 261, ha1_unit 241, test_radar_massive 18 passed; 0 outbound attempts.
- DB-backed, 27 changed suites, on a proven clone (engine localhost:3306/personal_apps_radar_wt; select database() = same; MySQL 8.0.46; 47 tables; 0 FKs; Alembic b7e3f9c1a2d4; no destructive opt-in; loopback-only sockets): 693 passed / 5 failed (baseline) / 159 errors (all destructive refusals). Statuses are identical to the implementer's final JUnit on all 857 identities. test_radar_activity (F1) was deliberately not run, and the full -k radar set was not rerun.
- Implementer JUnit reconciliation: 1849/14/220/1 → 1698/12/193/1. The only status change on a shared identity is F1's activity test (fail → pass). The 34 vanished non-pass identities and 5 new ones are all explained (DE or renamed parity refusals). All final failures are baseline; all errors are refusals.
- Residual sweeps: only allowed categories plus R1 and I1. git diff --check exit 0; index empty; status count unchanged (182).
- Playwright (scratch copy of the implementer harness; Chromium and Python non-loopback blocked; outputs in scratch): 29 cases, 184 checks, 0 failures, 0 outbound attempts, 0 unmocked calls. Adversarial cases: an embedded market 'de' payload is refused; EUR rows show no $.

Screenshots inspected (fresh): real-400-1200, real-hub-1200, real-hub-390, real-legacy-320, real-admin-390, fixture-chatter-AAPL-1200, fixture-chatter-AAPL-390, fixture-chatter-AAPL-320-chart, fixture-research-AAPL-320, fixture-overview-390, review-embedded-de-1200, review-eur-chatter-1200; plus the implementer's real-legacy-1200. Visual and accessibility ruling: PASS. No control or gap, no retired copy, $ formatting, US provenance intact, chart at every width, no hidden or market tab stop, no overflow at 1200, 390 or 320. The 400 page is Werkzeug's plain default but readable.

Unavailable gates and risks: destructive suites (no registered target; nothing set or invented); Alembic autogenerate and FK parity (clone has 0 FKs); full -k radar rerun; F1 and F5 and the Arctic Shift DNS test hygiene (pre-existing); deployment carries (back up the .env and remove RADAR_DE_PRICE_MODE and OPENFIGI_API_KEY; restart radar_ingest and personal_apps_web with a fresh build); workstream B (146 unmapped US identities, 51 changed entries).

Actions taken: only radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md was written. Scratch harnesses, logs and PNGs are outside the repository; the build refreshed the git-ignored dist. No fix; no test, application or continuity edit; no install; no credential values read; no environment-file change; no historical-row mutation; no provider contact; no service, production or VPS action; no stage, commit, push or deploy. The disposable clone received only non-destructive test fixture rows and prune runs (known F5 behaviour).
Protected state: personal_apps and production were never bound; the implementer's evidence files are unmodified; all pre-existing dirty and untracked work is preserved.
Subagents: none.

Requested Mastermind decision: rule on I1 and authorize one bounded, test-only correction (I1; optionally M1, M2 and M4; fix M3 in continuity). Do not rerun the whole review. A focused check of the corrected file plus a TypeScript residual sweep is enough to close I1.
Next bounded action recommendation: one small correction assignment for selectedPriceGeometry.test.ts:144, then a focused Vitest and sweep; then A proceeds to commit/deployment planning under separate owner authorization.

Read the current handoff, ledger and this return; verify the Git and artifact evidence; make the product ruling and update planning continuity. Do not implement, commit or deploy yourself.
```

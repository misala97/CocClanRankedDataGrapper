# A-US-USD-ONLY-CORRECTION-1 — Implementer return

Date: 2026-09-17
Role: correction Implementer (Claude Opus 5, one session, no subagents)
Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
Branch / base / HEAD: `codex/radar-selected-price-charts` / `38591e0f5e98faccb5228d84d1677843fcdb2aea` / `38591e0f5e98faccb5228d84d1677843fcdb2aea` (unchanged)
Status: both accepted corrections (C1, C2) applied test-first to the existing **uncommitted** A candidate. Nothing staged, committed, pushed or deployed.

Binding inputs read completely: root `HANDOFF.md`, `A-US-USD-ONLY-LEDGER.md`, `A-US-USD-ONLY-SPEC.md`,
`A-US-USD-ONLY-VERIFY-1-RULING.md`, `A-US-USD-ONLY-PLAN.md`, `A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`,
`A-US-USD-ONLY-REVIEW-1-RETURN.md`, `A-US-USD-ONLY-REVIEW-1-RULING.md`.

---

## 1. Files and lines changed by this correction

All five paths were already `M` in the candidate. This correction changed only the lines below. Line numbers refer to the current working tree.

| File | Lines | Change |
|---|---|---|
| `personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts` | 140, 143, 144 | C1: test title, comment and the unknown-source example (`deutsche_boerse_delayed` → `some_future_feed`) |
| `personal_apps/features/radar/routes/api.py` | 245-266 (new), 275-279 (docstring), 283-284 | C2: new `_supplied_markets(args)` and `require_us_market(args)`. `parse_query` now calls `require_us_market(args)` and sets `market = 'us'`, replacing `market = args.get('market') or 'us'` / `if market != 'us': raise BadQuery(...)` |
| `personal_apps/features/radar/routes/views.py` | 17, 25-26 (docstring), 28-31 | C2: imports `require_us_market`. `_refuse_unsupported_market` calls it inside `try/except BadQuery` and aborts with the same 400 description, replacing `market = args.get('market')` / `if market and market != 'us':` |
| `personal_apps/tests/test_radar_api.py` | 73-120 (new) | C2 regressions: pure parser, JSON board/ticker routes |
| `personal_apps/tests/test_radar_hub_page.py` | 106-149 (new) | C2 regressions: `/radar/`, `/radar/hub/`, `/radar/legacy/` |

No other application, test, model, migration, config, template, frontend runtime or continuity file was edited. The only other new repository file is this return.

## 2. C1 — test-only retired-source vocabulary

- **Before:** the test `'names the US sources and gives the retired feed no friendly name'` asserted `sourceWord('deutsche_boerse_delayed') === 'deutsche_boerse_delayed'`. That is a positive contract to render the retired code. The TypeScript sweep found exactly this one match (`selectedPriceGeometry.test.ts:144`, rg exit 0). This was the recorded red state of the residual requirement.
- **After:** the test is `'names the US sources and passes an unknown source code through'`, with the comment "A source code with no entry is shown as its raw code, never dressed up." and the assertion `sourceWord('some_future_feed') === 'some_future_feed'`.
- **Unchanged:** `sourceWord()` in `selectedPriceGeometry.ts:275-277` and all frontend runtime behaviour.
- **Result:** focused Vitest 1 file / 16 tests passed. `rg -n "deutsche_boerse_delayed" static/radar/src --glob "*.ts" --glob "*.tsx"` returns no matches (exit 1).

## 3. C2 — every supplied `market` value is validated

**Mechanism:**
- `_supplied_markets(args)` uses `args.getlist('market')` when the object has `getlist` (Flask `MultiDict`). For a plain mapping it returns `[args.get('market')]`, or `[]` when that value is absent or `None`. Existing plain-dict callers (the producer's warm set, `price_chart.py:57`, unit tests) keep working.
- `require_us_market(args)` raises the existing `BadQuery('unsupported market')` when any supplied value is not `''` or `'us'`.
- `parse_query` (board API, shared-board path, ticker API) and the HTML pre-fallback guard both use this one function. The HTML guard still runs before `build_payload` and before the friendly fallback, and still aborts with the same visible 400 description. No board or hub payload is rendered on that response.
- The selected-price endpoint (`price_chart.py`, including its `duplicate_query` rejection) is untouched.

**Behaviour before and after** (JSON board/ticker and the three HTML routes):

| Query | Before | After |
|---|---|---|
| omitted `market` | US | US |
| `market=` | US | US |
| `market=us` | US | US |
| `market=us&market=us`, `market=&market=us`, `market=us&market=&market=us` | US | US |
| `market=us&market=de` | **200, US board (only the first value read)** | **400 `unsupported market`** |
| `market=de&market=us` | 400 | 400 |
| `market=&market=moon` | **200, US board** | **400** |
| `market=us&market=US` | **200, US board** | **400** |
| `market=us&market=us&window=nonsense` (HTML) | 200, friendly fallback, US | 200, friendly fallback, US (unchanged) |
| `market=de` (any route) / `{'market': 'de'}` (plain mapping) | 400 / `BadQuery` | 400 / `BadQuery` (unchanged) |

### New regression cases

`tests/test_radar_api.py`:
- `test_every_supplied_market_value_is_checked_not_only_the_first` (pure, no client). It checks:
  - `MultiDict` inputs `[us,de]`, `[de,us]`, `['',moon]` and `[us,US]` all raise `BadQuery('unsupported market')`.
  - `[]`, `['']`, `[us]`, `[us,us]`, `['',us]` and `[us,'']` all parse as `market == 'us'`.
  - Plain-mapping compatibility: `{'market':'us','window':'24'}` parses as US, and `{'market':'de'}` raises.
- `test_a_repeated_market_with_any_unsupported_value_is_a_400`, parametrized over four paths. Each returns 400 with `{"error": "unsupported market"}`:
  - `/radar/api/board?market=us&market=de`
  - `/radar/api/board?market=de&market=us`
  - `/radar/api/ticker/AAPL?span=1M&market=us&market=de`
  - `/radar/api/ticker/AAPL?span=1M&market=de&market=us`
- `test_a_repeated_supported_market_still_answers_us`:
  - The board with `market=us&market=us` and with `market=&market=us` returns 200 and `market == 'us'`.
  - The ticker with `span=1M&market=us&market=us` returns 200 and `identity.quote.market == 'us'`.

`tests/test_radar_hub_page.py`:
- A new helper, `_legacy_payload(html)`, reads the legacy page's `radar-data` JSON.
- `test_a_repeated_market_with_any_unsupported_value_is_a_visible_400`, parametrized 3 routes × 2 orderings (`market=us&market=de` and `market=de&market=us`, each with `&window=24`). Each response returns 400, contains `unsupported market`, and contains neither `radar-hub-data` nor `radar-data`.
- `test_a_repeated_supported_market_opens_the_us_board`, for each of the 3 routes: `?market=us&market=&market=us&window=24` returns 200, and the embedded board has `market == 'us'` and `window_hours == 24`.
- `test_a_malformed_filter_beside_supported_markets_still_falls_back`, for each of the 3 routes: `?market=us&market=us&window=nonsense` returns 200 with the fallback US board.

Test-first evidence: before the source edits, the new selection (18 tests) gave **6 failed / 12 passed**.
- The failures were the pure parser test (`DID NOT RAISE BadQuery`), the two `market=us&market=de` JSON cases, and the three `market=us&market=de` HTML cases (`assert 200 == 400`).
- The reverse-order and supported-value cases already passed, as expected.

After the edit: **18 passed**.

## 4. Commands and results (all executed by me, from `personal_apps/`, `PYTHONDONTWRITEBYTECODE=1`)

### DB safety

- **Why a guard:** the worktree has no `.env`. Without a guard, `app.py`'s `load_dotenv(override=True)` binds the protected `personal_apps` (Implementer evidence). So every DB-backed pytest ran in-process through a scratch runner, `wt_guard.py` in the session scratchpad, outside the repository.
- **What the runner did:**
  - Pinned `PERSONAL_DB_NAME=personal_apps_radar_wt` before and after every dotenv load. The load used the same `.env` that `app.py` resolves from `personal_apps/`.
  - Removed `RADAR_DESTRUCTIVE_TEST_TARGET`/`_REGISTRY`, and never set either.
  - Refused every non-loopback `connect`/`connect_ex`/`getaddrinfo`.
  - Exited before running any test unless the engine URL database **and** the server's `select database()` were both the clone and the host was loopback.
- **Proof line printed before each DB run:** `engine mysql+pymysql://***@localhost:3306/personal_apps_radar_wt; select database()=personal_apps_radar_wt; server 8.0.46; foreign keys=0; destructive opt-in=[]; loopback-only sockets`.
- **Credentials:** no values were read, printed or persisted.
- **Prompt commands:** the literal bare commands `py -3.12 -m pytest tests/test_radar_api.py tests/test_radar_hub_page.py ...` were **not** run unwrapped. The same arguments ran through the guard instead.

### Results

| Gate | Command | Result |
|---|---|---|
| C1 residual (red) | `rg -n "deutsche_boerse_delayed" static/radar/src --glob "*.ts" --glob "*.tsx"` | 1 match, `selectedPriceGeometry.test.ts:144` |
| C1 focused Vitest | `npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts` | 1 file, **16 passed** (run after C1 and again at the end) |
| C1 residual (green) | same `rg` | **no matches** (exit 1) |
| C2 red | guard + `tests/test_radar_api.py tests/test_radar_hub_page.py -q -p no:cacheprovider -k "repeated or every_supplied_market or malformed_filter_beside"` | 6 failed / 12 passed / 75 deselected; 0 refused outbound |
| C2 focused green | same | **18 passed** / 75 deselected; 0 refused outbound |
| Required suites | guard + `tests/test_radar_api.py tests/test_radar_hub_page.py -q -p no:cacheprovider` | **92 passed, 1 failed**; 0 refused outbound (run twice; the final run followed the last docstring edit). The failure is the baseline identity `test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`, with the same assertion (`'id="radar-root"' in <hub page>`) recorded in `baseline/radar-db-pre-nonpass.txt:223` and `task5/radar-db-final-nonpass.txt:194`. The 93 total is the previous 75 plus 18 new tests. |
| Consumer: board keys / producer (plain-mapping `parse_query`) | guard + `tests/test_radar_board_keys.py tests/test_radar_board_producer.py -q -p no:cacheprovider` | 28 passed, **0 failed**, 29 errors. All 29 errors are the known setup refusal "destructive Radar work is not opted in". |
| Protected selected price (DB-free) | socket-only guard mode (no dotenv, no `app` import) + `tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **261 passed**; 0 outbound; `app` not imported |
| TypeScript | `npx tsc --noEmit` | exit 0 |
| Whitespace | `git diff --check` (repository root) | exit 0 |

**Harness incident (disclosed, not a code regression):** my first selected-price run went through the *DB* guard, and one test failed: `test_child_lifecycle.py::test_a_real_child_returns_a_series_without_flask_the_database_or_the_parent_environment`.
- **Cause:** the DB guard imports `app`, and `app.py`'s `load_dotenv(override=True)` put the two Alpaca credential variables into the parent test process. That test asserts that the parent's environment contains no such names.
- **Exposure:** the assertion output printed only the two already-documented variable **names** (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`), never values.
- **Resolution:** the suite is DB-free by design. Rerun in socket-only mode, exactly as the Implementer and Reviewer ran it, it gives 261 passed.

**Not run (outside correction scope):** full Radar Vitest, `npm run build`, Playwright and the full `-k radar` DB run. C1 is test-only. C2 changes no frontend code or template, and its HTML behaviour is proven by the Flask client tests above.

### Unavailable gates

- **Destructive suites:** board store, producer readiness/claims, shared API and parity remain refused. No registered destructive target exists, and none was set or invented. The shared-board path reaches `parse_query` too, so its repeated-market refusal is covered at the parser level only. Its store-backed route tests were not executed.
- **Alembic / FK parity:** not applicable to this correction. The clone has 0 FKs.

## 5. Residual sweep

`rg -n "deutsche_boerse_delayed" static/radar/src --glob "*.ts" --glob "*.tsx"` → **no matches**.

## 6. Git state and protected files

- **Branch / HEAD:** `codex/radar-selected-price-charts` / `38591e0f5e98faccb5228d84d1677843fcdb2aea`, unchanged.
- **Index:** empty (`git diff --cached --name-only` → 0 lines).
- **Dirty status:**
  - Before this return: `git status --short` had 185 entries, **identical** to the snapshot taken before my first edit (all five edited paths were already `M`).
  - After this return: 186 entries, the only addition being untracked `radar-design/A-US-USD-ONLY-CORRECTION-1-RETURN.md`.
- **Models / migrations:** `git diff -- personal_apps/models.py personal_apps/migrations` is empty.
- **Untouched unrelated candidate content:**
  - `ChartHover.currency`, the `chatterSort.ts` comment and `mauerstrassenwetten`.
  - Selected-price duplicate handling.
  - All other query semantics.
  - F1/F5/network-test hygiene.
  - Continuity files (`HANDOFF.md`, ledger).
  - The Implementer's and Reviewer's evidence.
  - All other pre-existing tracked and untracked changes.
- **Disposable clone:** the non-destructive api/hub_page tests ran there. The `plain_user` fixture creates and deletes its own account. No destructive work ran. `personal_apps` and production were never bound.
- **Not done:** no subagent, stage, commit, push, reset/clean/stash/restore/checkout, environment-file edit, credential inspection, provider or network request (0 refused outbound attempts in every run), DB-history mutation, service, production or deployment action.

---

## Copy/paste Mastermind prompt

```text
You are Radar's Mastermind / Overview. Assess the correction return for A-US-USD-ONLY-CORRECTION-1 with a changed-lines check and focused verification (no second full review).

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / HEAD: codex/radar-selected-price-charts / 38591e0f5e98faccb5228d84d1677843fcdb2aea / 38591e0f5e98faccb5228d84d1677843fcdb2aea (unchanged; candidate uncommitted)
Return: radar-design/A-US-USD-ONLY-CORRECTION-1-RETURN.md
Role: correction Implementer, Claude Opus 5, one session, no subagents.

Changed lines (all five paths were already M in the candidate):
- personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts:140,143,144 — C1. Test title, comment and example changed from 'deutsche_boerse_delayed' to 'some_future_feed' ("passes an unknown source code through"). sourceWord() and all runtime frontend code are unchanged.
- personal_apps/features/radar/routes/api.py:
  - 245-266: new _supplied_markets(args), which uses getlist when present and otherwise a single plain-mapping value, and require_us_market(args), which raises BadQuery('unsupported market') if any value is not '' or 'us'.
  - 275-279: parse_query docstring.
  - 283-284: parse_query now calls require_us_market(args) and sets market = 'us' (previously args.get('market') or 'us' plus an if/raise).
- personal_apps/features/radar/routes/views.py:17,25-26,28-31 — imports require_us_market. _refuse_unsupported_market wraps it in try/except BadQuery and aborts with the same 400 description, still before build_payload and the friendly fallback.
- personal_apps/tests/test_radar_api.py:73-120 — new C2 regressions.
- personal_apps/tests/test_radar_hub_page.py:106-149 — new C2 regressions plus a _legacy_payload helper.

Behaviour:
- C1: the only active TypeScript occurrence of the retired token is gone. Runtime is unchanged.
- C2 before: the JSON board/ticker routes and /radar/, /radar/hub/, /radar/legacy/ read only the first market value. market=us&market=de, market=&market=moon and market=us&market=US served the US board with 200.
- C2 after: any such request returns 400 unsupported market, and the HTML 400 embeds no radar-hub-data or radar-data.
- Unchanged:
  - omitted, market=, market=us and repeated supported values (us/us, ''/us, us/''/us) all resolve to US;
  - market=de&market=us returns 400;
  - plain-mapping parse_query callers (producer, price_chart.py:57) still work;
  - malformed non-market filters beside supported markets still get the friendly 200 US fallback;
  - the selected-price endpoint and its duplicate_query rejection are untouched.

New regression cases:
- test_every_supplied_market_value_is_checked_not_only_the_first (pure MultiDict + plain-mapping).
- test_a_repeated_market_with_any_unsupported_value_is_a_400: board and ticker, both orderings.
- test_a_repeated_supported_market_still_answers_us: board us/us and ''/us; ticker span=1M us/us.
- test_a_repeated_market_with_any_unsupported_value_is_a_visible_400: 3 HTML routes × both orderings; 400, no embedded payload.
- test_a_repeated_supported_market_opens_the_us_board: 3 routes; 200, market us, window 24.
- test_a_malformed_filter_beside_supported_markets_still_falls_back: 3 routes, window=nonsense; 200 US.

Commands and results (my execution, from personal_apps/, PYTHONDONTWRITEBYTECODE=1):
- DB-backed runs went through an in-process scratch guard. It pinned PERSONAL_DB_NAME after every dotenv load, stripped the destructive opt-in and allowed loopback-only sockets. Before any test it printed: "engine mysql+pymysql://***@localhost:3306/personal_apps_radar_wt; select database()=personal_apps_radar_wt; server 8.0.46; foreign keys=0; destructive opt-in=[]". The bare unwrapped pytest command was not run, because without the guard app.py binds the protected personal_apps.
- C1: rg for deutsche_boerse_delayed found 1 match before the edit and none after (exit 1). Focused Vitest selectedPriceGeometry.test.ts: 16 passed.
- C2 red (new selection): 6 failed / 12 passed. All failures were the us-first orderings plus the pure test (DID NOT RAISE). Green: 18 passed.
- Guarded tests/test_radar_api.py tests/test_radar_hub_page.py -q -p no:cacheprovider: 92 passed / 1 failed. The failure is the baseline identity test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch, with the same assertion as baseline/radar-db-pre-nonpass.txt:223. There were 0 outbound attempts.
- Guarded board_keys + board_producer: 28 passed, 0 failed, 29 errors, all destructive opt-in refusals.
- selected_price_unit (socket-only, no app import): 261 passed, 0 outbound.
- An earlier run of that suite through the DB guard had 1 harness-caused failure. The guard's app import had loaded the two APCA credential variables into the parent process, and that test forbids them in the parent. Only the names were shown in the assertion, never values. The DB-free rerun is the valid gate.
- npx tsc --noEmit: exit 0. git diff --check: exit 0.
- Not run (outside scope): full Vitest, build, Playwright, full -k radar.

Unavailable gates:
- Destructive suites (no registered target; nothing set or invented). The shared-board route's repeated-market refusal is proven at the parse_query level only.
- Alembic/FK parity (clone has 0 FKs; not relevant to this change).

TypeScript residual sweep: rg -n "deutsche_boerse_delayed" static/radar/src --glob "*.ts" --glob "*.tsx" finds no matches.

Git:
- Branch codex/radar-selected-price-charts at HEAD 38591e0f5e98faccb5228d84d1677843fcdb2aea; index empty.
- git status --short showed 185 entries before the return, identical to the pre-edit snapshot. The return adds 1 untracked file (186).
- git diff -- personal_apps/models.py personal_apps/migrations is empty.
- Unrelated candidate files, continuity files and the Implementer/Reviewer evidence are untouched. ChartHover.currency, the chatterSort comment, mauerstrassenwetten, selected-price duplicate handling, F1/F5 and network-test hygiene were not changed.

Confirmations: no subagent, stage, commit, push, reset/clean/stash/restore/checkout, environment-file edit, credential-value inspection, provider/network request, DB-history mutation, service, production or deployment action. Only the disposable clone was bound, with non-destructive tests.

Requested Mastermind action: perform the changed-lines assessment and focused verification. Suggested checks:
- the five-file diff above;
- the rg sweep;
- the focused Vitest file;
- guarded tests/test_radar_api.py + tests/test_radar_hub_page.py on the proven clone;
- selected_price_unit DB-free;
- tsc and git diff --check.
If these pass, close the A correction gate. Commit, push, production .env cleanup and deployment remain a separate owner decision.
```

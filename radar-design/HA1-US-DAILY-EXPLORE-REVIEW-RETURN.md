# HA1 US Daily Explore — independent Reviewer/QA return

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-REVIEW-1 · Radar Reviewer with QA evidence-assessment duties (owner-selected model; Claude Opus 5). Read-only application review. No fixes, DB, services, browser login, commits or deployment. Subagents: none.

**Disposition: NOT ACCEPTABLE AS-IS.** Core reducers, routes, identity revalidation, transport and cache lifecycle largely meet SPEC §§3–7. Before HA1 acceptance and before any DB/preview harness runs, fix three P1 harness defects and six P2 product/contract defects. C11/C13/C14/C15/C16 runtime gates stay OPEN.

## 1. Git and workspace verification

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`; branch `codex/radar-ha1-us-daily-explore`; HEAD `1ac39fe4e1a5dd7d04830e96a96563183687b447` (base), no upstream, nothing committed.
- The tracked diff has 14 modified files (817 insertions, 35 deletions) and was the same at the start and end of the review. It matches the ledger's Implementer and planner ownership. The untracked files match the ledger inventory. New untracked application, test and script files were read in full, as was the tracked diff.
- Files added by this review, and nothing else: this return, plus `radar-design/artifacts/ha1/review/{contract_repro.py, contract_repro.out.txt, reducer_budget_estimate.py, reducer_budget_estimate.out.txt}`.
- `npm run build` rewrote the git-ignored `static/radar/dist`, which the Implementer had already built from the same source.

## 2. Executed by this Reviewer (independent)

| Command (from `personal_apps`) | Result |
| --- | --- |
| `py -3.12 -m pytest -p no:cacheprovider --confcutdir=tests/ha1_unit tests/ha1_unit -q` | `95 passed in 0.93s` (imports inspected first: `features/radar/__init__.py` empty; `extensions.py` only builds `SQLAlchemy()`; no app/DB) |
| `npx vitest run -c vite.radar.config.ts` navigation, Hub, queries, analysisApi, analysisQueries, Analysis, AnalysisChart, Chatter, ChatterWorkspace | `Test Files 9 passed (9)`, `Tests 210 passed (210)` |
| `npm run build` | passed (TypeScript + both Vite builds, `built in 1.62s` / `1.78s`) |
| SQLAlchemy compile check, pymysql dialect, no engine/connection | driver statement `... WHERE ticker = %s LIMIT %s`; `sa.text('EXPLAIN ' + driver_sql)` compiles to `%%s` with `bind names: []` |
| `py -3.12 ../radar-design/artifacts/ha1/review/contract_repro.py` | see `contract_repro.out.txt`; reproductions quoted in findings |
| `py -3.12 ../radar-design/artifacts/ha1/review/reducer_budget_estimate.py` | 43,008 row dicts 9.52 MiB; peak rows+reducer 15.78 MiB; chatter JSON 99,582 bytes (lower bound; excludes driver/SQLAlchemy/Flask/price) |
| Token contrast from `hub.css` hex values | dim #8fa3b8 on panel #112331 6.19:1, on selected #1a3042 5.24:1; muted 8.74; amber 8.63; price 7.93; chatter 7.82. All text tokens are at or above 4.5:1 on paper; rendered contrast is not verified |

Not executed, per hold: `tests/test_radar_analysis_api.py`, `scratchpad/ha1/local_runtime.py`, `probe_analysis.py`, `verify_preview.py`, any DB query/fixture, preview server or browser. Broad whole-radar Vitest and the 28 `pending.test.tsx` baseline failures were not repeated (Implementer-reported). No screenshots exist and none were substituted.

## 3. Findings (P1 blocks harness execution; P2 fix before acceptance; P3 low)

### P1-1 — R1 CONFIRMED: broad `ZQ%` deletion with no ownership (harness)
`scratchpad/ha1/probe_analysis.py:50-56` (`wipe`, called before seeding at :157 and at the end at :200) and `tests/test_radar_analysis_api.py:38-44` (`_wipe`, called before seeding and at teardown by `seeded`). Both bulk-delete every `radar_bucket_sources`/`radar_daily_closes`/`radar_instruments`/`radar_ticker_universe` row whose ticker/symbol is `LIKE 'ZQ%'`.
- Impact: this destroys rows the run did not create, including rows owned by another suite or the preview. Being authorized to use a disposable DB does not make those rows ours.
- Correction: record the exact symbols/IDs created by this run; refuse if a chosen symbol already exists; delete only those identities in `try/finally`.

### P1-2 — R2 CONFIRMED, extended: the probe cannot reach measurement, and neither EXPLAIN path can bind
1. `probe_analysis.py:167` reads `session['user_id'] = admin.id` after the app context (:152-164) has closed.
   - Before that, `wipe()`/`seed()` committed, so `admin` is expired, and context teardown removed the session.
   - With the installed Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.49, reading an expired attribute of a detached instance raises `DetachedInstanceError`. This is static reasoning; not executed per hold.
2. `:95` and `:115` call `event.listen/remove(db.engine, ...)` inside `measure()` with no app context. In Flask-SQLAlchemy 3.x, `db.engine` requires `current_app`.
3. `:118-127` and `tests/test_radar_analysis_api.py:284-298` both re-wrap cursor-level SQL in `sa.text('EXPLAIN ' + bare)` with guessed named parameters.
   - Reproduced by compiling with the pymysql dialect: the driver SQL uses positional `%s`; the re-wrapped text has zero bind names and escapes to `%%s`.
   - The named parameters never bind. No working EXPLAIN evidence path exists.
- Correction:
  - Keep every engine/session access inside an app context, and use `_admin_id()`-style id capture.
  - Run EXPLAIN on the reader's own named SQL constants (`analysis.DAILY_CLOSES` etc.) with named binds, or run `EXPLAIN` + the driver statement with the captured driver parameters on the same raw DBAPI cursor.

### P1-3 — NEW: the unexecuted C14 store-failure API test cannot pass for test-authoring reasons
`tests/test_radar_analysis_api.py:314-328`: the monkeypatched `broken` calls `self.session.execute(...)` directly and bypasses `SqlStore._rows` error mapping.
- The resulting `ProgrammingError` is not a `ContractError`, and `routes/analysis.py:57-62` catches only `ContractError`.
- conftest sets `TESTING=True`, so Flask propagates the exception into the test client. The test errors instead of observing the 503.
- Correction: raise through `_rows` (for example `self._rows('SELECT * FROM zq_no_such_table')`).

### P2-1 — R5 CONFIRMED: price line bridges missing dates, against SPEC §3
`static/radar/src/hub/analysisTypes.ts:178-199` (join condition :186-189) joins observed closes across intervening `missing` dates hinted `modeled_closed`. The tests enshrine this: `analysisApi.test.ts:138-145` expects `[[0, 1, 4]]` and `:157` expects `[3, 6]`.
- SPEC §3 says connect "only neighboring dates with usable compatible observations, without crossing a missing/invalid date or regime boundary", and "A conservative broken line across a weekend is acceptable".
- `contract_repro.out.txt` #3 shows the payload marks the weekend `missing`/`modeled_closed`, and the backend `regime_runs` yields `[["2026-09-11"], ["2026-09-14"]]`. Frontend and backend therefore disagree.
- Correction: join only index-adjacent observations with an equal regime, and update both tests. `AnalysisChart.test.tsx:13-17` already expects adjacency-only runs for its fixture.

### P2-2 — NEW: a ticker-only link with invalid explicit dates silently fetches the default window (C01/C15)
The code path:
1. `Analysis.tsx:45` sets `range = null` for an invalid `rawRange`.
2. The resolve effect (`:49-55`) passes that `null` into `onNavigate(..., range, { replace: true })`.
3. `Hub.tsx:201-203` writes `null`, so `replace` drops `analysis_from`/`analysis_to` from the URL and sets `analysisRange` to `null`.
4. The pinned re-render then computes `range = fallback` (`:45`), and `useAnalysis` fetches the default seven days.

- SPEC §3: "Invalid dates show an editable validation notice without fetching a guessed range; a bare Analysis URL alone gets the default."
- Only the pinned invalid case is tested (`Analysis.test.tsx:198-205`).
- Correction: preserve the raw address strings through the canonical replace (or do not pin until the window is valid), and add a ticker-only + invalid-dates test.

### P2-3 — NEW: the reader deadline is not enforced while a statement runs (C14)
`features/radar/analysis.py:38-39,191-199`: `_Deadline.check()` runs only between statements (:289, :304, :313, :320; resolve :259), and every statement gets a fixed 2 s timeout.
- Worst case, four data statements run about 8 s before the 5 s deadline is noticed. That coincides with the browser's 8 s abort.
- SPEC §7: "no request survives the enforced deadline".
- Correction: per-statement limit = min(2 s, remaining) (MariaDB `max_statement_time` accepts fractions); check before each statement; add a fake-clock test.

### P2-4 — Ruling unit CONFIRMED VIOLATED in consumer copy
`static/radar/src/hub/Analysis.tsx:408` renders "`N` slots before the company record excluded". But `identity_excluded_slots` counts source-bucket rows (`analysis_contract.py:480`).
- `contract_repro.out.txt` #1: 48 quarter-hours × 3 sources gives `identity_excluded_slots: 144`.
- `Analysis.test.tsx:146` asserts the wrong unit ("4 slots").
- The backend warning text (`analysis_contract.py:589-592`, "bucket row(s)") is correct.
- Correction: say "source-bucket rows" in the UI and the test.

### P2-5 — NEW: mobile targets below 44 px (SPEC §3)
- `analysis.css:40` `.rh-an-range .rh-button { min-height: 40px }` (specificity 0,2,0) overrides `hub.css:1941` `.rh-button { min-height: 44px }` inside `@media (max-width: 860px)`.
- `analysis.css:187` `.rh-an-table th[scope='row'] .rh-textbutton { min-height: 32px }` overrides `hub.css:1942` 44 px.
- Correction: make these controls ≥44 px at narrow widths. Confirm on real screenshots.

### P2-6 — NEW, runtime hypothesis: an invalid address date will not appear "as typed"
`Analysis.tsx:248,253` use `<input type="date">`. In real browsers, HTML value sanitization empties a non-conforming value (e.g. `2026-13-07`). The return's "shows the typed values" is proven only in jsdom (`Analysis.test.tsx:202`).
- The notice still renders, but the reader cannot see or edit what was wrong.
- Correction: echo the raw values in the notice, or use validated text inputs. Verify in actual-app QA.

### P2-7 — NEW: re-resolution can reuse a cached old mapping (C02 recovery path)
`analysisQueries.ts:34-46` (`staleTime: 0`, `gcTime` 5 min) together with `Analysis.tsx:49-55`, which pins as soon as `resolve.data` exists.
- A search hit for a ticker resolved within the last 5 minutes pins the cached IDs before the stale refetch returns.
- Server revalidation turns a remap into a visible 409, so wrong data is not shown. But the "search again" recovery can loop on stale IDs until GC.
- Correction: pin only on data fetched after this mount (e.g. `isFetchedAfterMount && !isFetching`), or use `gcTime: 0` for resolve.

### P3 (low; correct opportunistically or record)
- `Analysis.tsx:475` `aria-selected` on `<tr>` inside a non-grid table is unsupported ARIA. Focusable `.rh-tablewrap` regions (`:413`, `:458`) have no accessible name. The `aria-live` day-detail section (`:390-391`) re-announces whole tables on each selection.
- Slot partition: unaligned rows are counted `invalid` but sit outside the 96-slot partition (`analysis_contract.py:505-506,528-529`). Repro #2: slot fields sum to 98 of `expected_slots` 96. Document the unit or count unaligned rows separately.
- A source whose only rows precede `first_seen` is still represented as an `unavailable` source (`analysis_contract.py:454`; repro #4 `stocktwits`). Disclose or exclude.
- At ≤860 px, `hub.css:1943` hides `.rh-venue`, so the top bar (`Hub.tsx:271-274`) reads only "USD · retrospective". The identity strip still states the full scope.
- Day buttons use `padding-left: 50px` (`analysis.css:147`; 0 at ≤760 px) against SVG `LEFT=52/RIGHT=14` viewBox units (`AnalysisChart.tsx:22-24`). Columns likely misalign at non-720 px widths (visual hypothesis). `.rh-an-empty` is defined for both SVG text and the empty-state div (`analysis.css:120,188`).
- `read_company` does not detect a second eligible primary added after pinning (`analysis.py:273-320`). This is consistent with the ≤4-SELECT budget; noted as spec ambiguity, no correction unless ruled.
- Hypothesis: `SELECT SLEEP(3)`-only timeout probes (`probe_analysis.py:188`, API test :346) may return 1 rather than raise on some MySQL-family engines. If so the gate false-fails (not false-passes). Verify on the target.

## 4. R3 / R4 dispositions (harness)

**R3 CONFIRMED.**
- The probe records figures but never enforces budgets (`probe_analysis.py:128-139`; only `status_code == 200` is asserted at :109). Recorded figures are not passed gates.
- `main()` (:142-201) has no `try/finally`. A failure leaves fixtures, the extra overflow row and the mutated `analysis_mod.STATEMENT_TIMEOUT_S` (:185-192) behind.
- The overflow case (:172-180) adds a 65th source and the 43,009th row at once, so the two limits are conflated. SPEC wants the 43,009th row as its own refusal.
- `tracemalloc` peak is absolute for the last request, not the reader's incremental allocation.
- The API hygiene check (`test_radar_analysis_api.py:343-349`) may compare `@@max_statement_time` on different pooled connections after rollback, so it is a weak proof.
- Reviewer estimate: rows+reducer alone peak at 15.78 MiB and chatter JSON is 99,582 bytes. The 32 MiB/1 MiB budgets are plausible but unproven.

**R4 CONFIRMED.**
- `verify_preview.py:22-32` has no HA1 target/registry gate and no check of the listening server's candidate/DB identity.
- `implementation-evidence.md:34` ("each refuses before importing the app without `RADAR_HA1_TARGET` + `RADAR_HA1_REGISTRY`") is false for this script, which refuses only on missing `RADAR_HA1_USER`/`RADAR_HA1_PASSWORD`.
- The default ticker `ZQHAT` (:32) is deleted by the probe (:200) and by API teardown, so no preview fixture lifecycle exists.
- Cases are recorded, not asserted (:64-104).
- Not covered: loading/error/partial/truncated/config/overlap states, 200% zoom, reduced motion, focus visibility, contrast, touch, session expiry, and overflow checks on most screenshots. C16 is incomplete.
- `local_runtime.py` is correctly gated before app import (`:30-48`, `:78-79`). `app.py` has no import-time SQL by grep. Its `test` mode also runs three pre-existing suites whose own gating was not reviewed here.

## 5. Scope/regression review that found no material defect

- **Auth:** both routes are `login_required` and not admin-only. Login redirect/HTML is read as session expiry (`analysisApi.ts:63-67`). The gap: no ordinary non-admin API test exists (conftest `client` is admin), so C11 needs one.
- **Validation:** strict repeated-key-aware query validation, stable codes; the ticker regex guards before any read; JSON escaping; no SQL in messages.
- **Identity:** resolve uses `LIMIT 2` with 409 on ambiguity and no `.first()`. Reads revalidate: 404 missing, 409 remap/nonprimary/mismatch, 422 ineligible. There is no retargeting, and `mapped_at` is not used as a clamp.
- **Price:** live lane, selected MIC, `fetched_at <= read_start`; shadow/DE/null-MIC excluded; invalid kept distinct from missing with provenance; regime tuple; `interior_missing` by set membership, with adjacent two closes giving `[]`. Q4 195/225 is not used as an oracle.
- **Chatter:** 96 UTC slots, half-open bounds; ok+truncated counted; observed zero vs "0 in observed buckets — coverage incomplete"; config transitions in-day and across days; bare/child Reddit overlap gives `null` pooled; `configured_source_coverage: unknown`. There is no `mention_z`, return, tone or provider call.
- **Transport/cache:** no board filters sent; key includes IDs, ticker, dates, schema; no placeholder, retry, polling or refocus refetch; 8 s abort; a failed refresh is labelled with its read time. A session failure latches `expired` and runs `client.clear()` + SignedOut (`Hub.tsx:142-151`).
- **`useBoard(enabled)`:** reaches `useQuery` (`queries.ts:536`); expiry/minute clocks are gated (:586, :631); the look-back effect keys on `visible && enabled` (:661-679). Other pages default to `true`. Hub/queries/Chatter/ChatterWorkspace suites pass (independent). The request pattern when a board page re-enables is unmeasured runtime QA.
- **Fixtures and preserved behavior:** `analysisFixtures.ts` is imported only by test files (grep), so there is no production fallback. Legacy root/`t`/invalid-hash behavior, the Human Chatter sort path and DE board context stay unchanged, per the tests and the diff.

## 6. Gate status

C01–C10 pure logic: independently re-run tests pass, except the P2-1/P2-2/P2-4 contract or copy defects above. C12: component level passes, with P2-7 noted. The runtime portions of C02 (transport), C11, C13, C14, C15 and C16 are OPEN: no target, harness on hold, and P1 defects present. No actual-app, mobile, zoom or keyboard screenshot evidence exists.

## 7. Recommendation (bounded, not dispatched)

One Implementer correction task in this candidate:
- **Product:** P2-1 through P2-5. Include P2-6/P2-7 if cheap; P3 items optional.
- **Harness:** P1-1 through P1-3, plus the R3 enforcement fixes: asserted budgets, separate overflow cases, `finally` restore/cleanup, same-connection hygiene, incremental allocation measured around the reader only.
- **Preview:** the R4 fixes: HA1 gate plus server/DB identity check, owned persistent preview fixture seed/cleanup commands, assertions and C16 state coverage.
- **C11:** a non-admin C11 test.
- **Rules:** rerun only the changed focused tests and the build. No DB, preview or harness execution.

Then a focused re-review of only that delta. Only after that, a separately authorized HA1 disposable-target environment step for C11/C13–C16. Deployer stays unauthorized.

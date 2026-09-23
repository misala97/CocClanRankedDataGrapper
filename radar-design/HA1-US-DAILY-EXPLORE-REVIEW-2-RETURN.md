# HA1 US Daily Explore — REVIEW-2 return (CORRECTION-1 delta)

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-REVIEW-2 · Radar Reviewer/QA (Claude Opus 5). Read-only review plus DB-free tests/build. Subagents/workers: none.

**Disposition.** Every REVIEW-1 P1 and every product P2/P3 correction is resolved in code, with some parts runtime-only unverified. The harness now has no data-loss path I could find: no broad delete, collision refusal before mutation, gates before app import/SQL, exact-key cleanup. It is **not yet able to close C11/C15/C16 as written**. Five P2 harness/evidence defects remain; one is demonstrated by reproduction, one by a toy reproduction, three by static reasoning. No P1. Runtime C02/C11/C13/C14/C15/C16 stay OPEN.

Evidence and commands: `radar-design/artifacts/ha1/review-2/evidence.md`.

## 1. Git and scope

- Workspace, branch and HEAD/base `1ac39fe4e1a5dd7d04830e96a96563183687b447` verified at start and end; no upstream. The tracked diff is 14 files, +942/−35, and this review did not change it. Status entries are unchanged apart from this review's files.
- Correction delta located from the CORRECTION-1-RETURN ownership inventory, because most HA1 files are untracked.
- Read in full:
  - `ha1_harness.py`, `ha1_fixtures.py`, `preview_fixtures.py`, `probe_analysis.py`, `local_runtime.py`, `verify_preview.py`
  - `test_radar_analysis_api.py`, `test_ha1_harness.py`, `analysis.py`, `analysis_contract.py`, `routes/analysis.py`
  - `Analysis.tsx`, `AnalysisChart.tsx`, `analysisTypes.ts`, `analysisQueries.ts`, `analysisApi.ts`, `analysis.css`
  - the Hub/navigation diff, and the relevant tests, models, auth, `app.py` gate, `destructive_target.py`, `radar_disposable.py` and `conftest.py`
- Review-owned writes: this file and `radar-design/artifacts/ha1/review-2/*`. No commits or pushes.

## 2. Fresh execution (this Reviewer)

- ha1_unit ran under a socket-blocking guard: **170 passed**, and neither `app` nor `pymysql` was imported.
- Focused Vitest, 10 files: **228 passed**.
- `tsc --noEmit`: clean. `npm run build`: passed.
- REVIEW-1 `contract_repro.py`: slot fields sum to 96, the pre-identity-only source is no longer represented, and backend weekend runs are broken.
- DB-free reproductions:
  - Git foreign-owner simulation: plain `git -C` exits 128; per-command `safe.directory` succeeds.
  - Toy Flask test-client host-cookie check: 302 on a foreign `base_url`.
  - SQLAlchemy dialect: `is_mariadb=False` before the first connect.
- My first pytest wrapper launch failed at collection on `sys.path`. That was my wrapper error, not the candidate's, and it is recorded.

## 3. Corrected harness (reviewed first)

| # | Area | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | P1-1/R1 exact ownership, collision before mutation, partial-failure cleanup, manifests, rollback, cleanup reporting | **RESOLVED** (static + fake-store tests); runtime-only for FK/constraint surprises | Real callers use `OwnedFixtures`: `probe_analysis.py:216`, `preview_fixtures.py:191`, `test_radar_analysis_api.py:72-86`. Deletes/counts are exact `id AND symbol` or full PK tuples (`ha1_fixtures.py:50-70`). The existence check covers all five touched tables (`:73-90`) before `_checked` (`ha1_harness.py:214-223`); a raising `__enter__` never reaches `__exit__`. Order is buckets→closes→instruments→companies→users, after a rollback first (`:268-292`). The manifest is written inside the block, so a write failure cleans up (`preview_fixtures.py:191-202`). The target check is `:311-313`. Model columns fit the fixtures (e.g. `source` NULL is allowed by the check constraint; `source_config_version` is nullable). P3 residue: see U7 |
| 2 | P1-2/R2/P1-3 context, scalar IDs, listeners, EXPLAIN, exception translation | **RESOLVED** (static); plans runtime-only | The admin id is read as a scalar inside the context (`probe_analysis.py:209-215`). Listeners register and remove inside it (`:127,140`). EXPLAIN uses the reader's named SQL with the store's own binds (`probe_analysis.py:176-181`, `analysis.py:128-137,232-237`). The API failure goes through `_rows` (`test_radar_analysis_api.py:342-344`) and hits DBAPIError→`analysis_unavailable` (`analysis.py:205-218`) |
| 3 | R3 asserted budgets, 65-source and 43,009-row cases, incremental allocation, 20 warm/p95, restoration and reporting | **RESOLVED** (static + rule tests); P3 gaps U5/U7 | Every budget is asserted and an unmeasured value fails (`ha1_harness.py:58-85`). The 65-source/65-row case is separate from the 43,009-row/64-source off-grid sentinel, which is removed afterwards with a 200 re-check (`probe_analysis.py:236-263`). tracemalloc wraps only `read_company`, with the baseline taken just before (`:149-170`). Latency is measured without tracemalloc, 1 cold + 20 warm. No constant is mutated. The report is written in `finally` and exits 1 (`:272-282`) |
| 4 | Remaining-budget fractional timeout; same-connection hygiene (code only) | **RESOLVED in code; runtime-only unverified**; P3 U4/U5 | `min(2, remaining)`, a <1 ms refusal and ms-floored `SET STATEMENT max_statement_time=N.NNN FOR` (`analysis.py:140-190,254-282`). Fake-clock tests are genuine (`test_analysis_reader.py:243-298`). The probe uses one `engine.connect()` and compares `CONNECTION_ID()`/`@@session.max_statement_time` (`ha1_fixtures.py:207-240`). `SET STATEMENT` cannot change session state, so this check is structurally weak but honest |
| 5 | Preview gate order, target/runtime/manifest identity, nonce/PID/stale records, loopback, fixture lifecycle | **RESOLVED except U1 and U8** | The gate runs before network and browser (`verify_preview.py:77-108`); the harness test pins this. Target, registry, root, branch, head, port and nonce are compared (`ha1_harness.py:339-354`). PID liveness is checked via tasklist and the nonce defeats PID reuse. The server binds `127.0.0.1` and refuses an occupied port (`local_runtime.py:137-159`). `bind()` asserts the URL and `destructive_target.require` (`:94-116`) |
| 6 | Runtime Git subprocess under ownership restriction | **UNRESOLVED — U1 (P2, demonstrated)** | See U1 |
| 7 | Replacement coverage for excluded search/hub_page suites | **UNRESOLVED — U3 (P2)**; exclusion itself correct | See U3 |
| 8 | C16 assertions prove behaviour? | **PARTIAL — U2 (P2), U6 (P2), U9 (P3)** | Behavioural and real: keyboard arrows/Enter, errors (loading, timeout, network+Retry, session expiry), identity (409/422/ambiguous, DE-entry US label), invalid-range no-fetch, overflow, 44 px sizes. Weak or vacuous: listed in U2/U6/U9 |

**Harness-safety verdict (for a later, separately authorized disposable run).** Safe with respect to data ownership and target isolation:
- No path found that deletes or adopts rows the run did not create.
- No path found that binds a non-loopback, protected-port or unregistered DB.
- No path found that runs SQL before both gates.

The known failures are fail-closed, not unsafe:
- U1 crashes `serve`/`verify_preview` with `CalledProcessError`.
- U2 fails C16.

**But the run as written cannot produce valid C11/C15/C16 closure:**
- U2 false-fails.
- The U4 host test false-passes.
- U3 leaves C15 cases uncovered.
- U6 lets contrast pass vacuously.

Correct U1–U4 and U6 before spending an environment run.

## 4. Product corrections

| Correction | Verdict | Evidence |
| --- | --- | --- |
| P2-1 adjacent observed-date price runs, regime breaks, weekend gaps | **RESOLVED**; actual-app line rendering runtime-only | `analysisTypes.ts:186-204` joins index-adjacent observed same-regime days only, matching `analysis_contract.py:400-420`. Tests: `analysisApi.test.ts:138-183`, `AnalysisChart.test.tsx:41`. Repro #3 was rerun |
| P2-2/P2-6 malformed raw dates preserved, editable, no guessed fetch | **RESOLVED** (component); real-browser runtime-only | `pinRange = rawRange ?? fallback` (`Analysis.tsx:49,62-63`). `range=null` disables the query (`:46,66-67`). Text inputs with `aria-invalid`/`aria-describedby` echo the raw values (`:262-287`). `readAnalysisRange` keeps half-present strings; Hub replace writes them (`Hub.tsx` diff). Tests: `Analysis.test.tsx:68,304-327`; Hub ticker-only malformed |
| P2-7 fresh resolution under stale cache, remap, reselection, races | **RESOLVED** | Pins only `isSuccess && isFetchedAfterMount && !isFetching` (`Analysis.tsx:56-64`), plus the ticker guard and `gcTime 0` (`analysisQueries.ts:34-51`). The tests really seed a stale cache and hold the fetch (`Analysis.test.tsx:104-160`). The server still revalidates (`analysis.py:376-394`) |
| P2-3 remaining budget, ms floor, <1 ms refusal, materialization/reduction checks, disclosure | **RESOLVED in code; runtime-only**; contract limit in §5 | `analysis.py:140-157,254-282,341-346,376-417`; docstring `:19-31` |
| P2-4 source-bucket-row units | **RESOLVED** | `Analysis.tsx:426,447-448`; `analysisTypes.ts:56-78`; `analysis_contract.py:451-460,612-614`; repro #1 |
| P3 96-slot partition, `excluded_rows`, off-grid/duplicate, pre-identity-only denominator/disclosure, fetched-source cap | **RESOLVED** (rulings honoured) | Partition `ok+truncated+missing+invalid+absent=96` (`analysis_contract.py:525-553`). Excluded rows block full coverage (`:559-561,604-606`). The cap is on fetched sources before exclusion (`:466-470`). `pre_identity_only` is disclosed (`:509-513,622-626`). Repro #2/#4 |
| P2-5 mobile 44 px targets, scroll box | **RESOLVED statically**; rendered runtime-only | Specificity checked against hub.css: range inputs/button (0,2,x) 44 px (`analysis.css:51-52`); table day button 44 px at ≤860 (`:221`); company/notice/refusal buttons (`:222-224`); day buttons `min 44×44` (`:173-174`); ≤560 `min-width:440px` gives ≈57 px columns (`:238`). Every Analysis control is covered |
| P3 a11y/layout: aria-selected removed, named regions, concise live status, alignment, empty styles, mobile identity | **RESOLVED** (component); alignment rendered runtime-only | `aria-current` (`Analysis.tsx:524-525`); named `role=region` (`:453-454,504`); one polite status (`:338`), detail not live. Percentage padding is relative to the plots box width and equals the SVG `LEFT/RIGHT` scale with `height:auto`; gap 0 (`AnalysisChart.tsx:64-65`, `analysis.css:161-166`). `.rh-an-scope` renders at every width (`Analysis.tsx:176`) |
| Preserve auth, pinned revalidation, transport/session cache clearing, board suspension, Chatter/legacy/navigation | **PRESERVED** (static + focused suites) | Routes unchanged, `login_required` only (`routes/analysis.py:32-63`). `expired` now includes Analysis expiry and feeds the existing latched clear/SignedOut. `useBoard(..., route.page !== 'analysis')`, and the board banner is hidden on Analysis (`Hub.tsx` diff). Hub/navigation/queries/Chatter/ChatterWorkspace pass. Legacy/root behaviour remains component-proven only (U3) |

## 5. Five-second reader contract (ruling 6)

**Enforced by code:**
- Every reader and resolver statement carries a server-side, statement-scoped limit of `min(2 s, remaining of 5 s)`, ms-floored, never 0, and is refused below 1 ms.
- The monotonic budget is re-checked after each materialized read and after reduction.
- A 200 is therefore returned only if reader work up to the last check finished within 5 s. Only JSON serialization and the finish stamp follow that check.

**Not enforced (post-hoc refusal, not a strict elapsed bound):**
- **Interrupt latency.** How promptly MariaDB actually stops a statement when its limit fires.
- **Result transfer time.** Transfer beyond what the server attributes to the statement.
- **Reduction overshoot.** A reduction that starts just before 5 s runs to completion and is refused only afterwards. It is bounded by the 43,008-row/64-source caps but unmeasured.
- **Pre-reader connection wait.** Auth's `current_user()` (`auth.py:24-37`) checks out the pooled connection before `ReaderBudget` exists, and the reader reuses it. Pool wait, up to SQLAlchemy's default 30 s queue timeout, therefore falls outside the reader budget rather than inside it.

The browser's 8 s abort bounds the reader's wait, not server work.

**Mastermind decision needed.** Should SPEC §7 "no request survives the enforced deadline" mean:
- reader scope with post-hoc refusal (met in code, pending runtime), or
- request wall-clock (not met, and not meetable without request-level cancellation)?

**Must be proven at runtime:**
- fractional `SET STATEMENT` acceptance, including sub-second values (see U5)
- CPU-bound interruption error 1969 within the limit plus grace
- pooled connection health after a timeout
- 503 translation on the engine
- 20-warm p95 ≤ 1 s

## 6. Unresolved findings

Demonstrated = reproduced here; static = code-path reasoning; hypothesis = plausible, unproven.

- **U1 — P2, demonstrated. Runtime Git ignores ownership safety.**
  - Where: `local_runtime.py:123-125` runs `git -C <candidate>` with `check=True` and no per-command `safe.directory`. It is used by `serve` (`:151-152`) and by `verify_preview.preflight` (`verify_preview.py:92-93`).
  - Reproduction: under a foreign-owner condition (`GIT_TEST_ASSUME_DIFFERENT_OWNER=1`) the plain form exits 128; `-c safe.directory=<candidate>` succeeds.
  - Effect: in the ownership-restricted shell the ledger documents, `serve` raises `CalledProcessError` after `bind()` and before writing its runtime record. `preflight` raises after its unauthenticated `/login` probe. Both fail closed, but no preview run can start.
  - Test gap: the unit test monkeypatches `git` (`test_ha1_harness.py:438`), which hides this.
  - Fix: `git -c safe.directory=<CANDIDATE> -C <CANDIDATE> ...`, turning a failure into `SystemExit`. Do not change global config.
- **U2 — P2, static. C16 `resolve_pin_replace` false-fails every time.**
  - Where: `verify_preview.py:221-228` asserts `history.length` is unchanged across the search pick.
  - Why: on Analysis a search hit goes through `go(openRoute(...))`, which **pushes** `#analysis/<TICKER>` (`Hub.tsx:268`, `openRoute` `:398-401`, `go` pushState). The pin then replaces it. Correct behaviour is therefore `length + 1`, and the SPEC agrees: selection is a user change, the pin is a replace.
  - Fix: assert +1 exactly across pick+pin, and assert that Back from the canonical URL returns to `#analysis` rather than to the ticker-only form.
- **U3 — P2, static. C15 runtime coverage is incomplete after the suite exclusion.**
  - Dropping `test_radar_search.py` and `test_radar_hub_page.py` is correct (`local_runtime.py:16-24,57`).
  - No safe runtime check replaces them. `verify_preview.py` never exercises:
    - `/radar/hub/` alias, `/radar/legacy/`
    - root `?t=VALID` → Human Chatter
    - invalid-hash fallback, filter-only bookmark
    - server route auth/mounts
    - "no Analysis board poll" (no network assertion on `/radar/api/board` while on Analysis)
  - It covers only: Back to a DE `#chatter` board, DE entry, explicit range push/back/refresh, and pin.
  - C15 stays OPEN until owned-identity route checks or preview assertions cover these.
- **U4 — P2, demonstrated (toy). The C11 full-access-host test passes vacuously.**
  - Where: `test_radar_analysis_api.py:144-151` accepts `302 or 403` with `base_url=http://<FULL_ACCESS_HOST>`.
  - Why: the test client's session cookie is scoped to the default host. A stand-in app with `app.py:121-134`'s gate shape answers `302 /login` on the foreign host (Flask 3.1.3/Werkzeug 3.1.8). The non-admin 403 branch is never reached, so the test would pass even if the member gate were deleted.
  - Fix: set the session on that host (`session_transaction` with a matching `base_url`/server name) and assert `403` exactly. Keep ruling 4's distinction between loopback 200 and production-host refusal.
- **U5 — P3, static. The timeout probe never exercises a fractional or sub-second limit.**
  - Where: `probe_analysis.py:66` sets `LIMIT_S = 1.0`; `ha1_fixtures.timeout_probe` calls `_rows(sql, limit_s)` directly, bypassing `ReaderBudget`. The API test also uses `1.0` (`test_radar_analysis_api.py:354-365`).
  - Gap: MariaDB acceptance of values like `0.437`/`0.001`, the reason for the ms floor, is unproven by the harness.
  - Fix: add one sub-second probe, e.g. 0.250 s CPU-bound.
- **U6 — P2, static. Contrast, and any zero-check case, can pass vacuously.**
  - `contrast_text` skips unparsed colours and empty selector matches (`verify_preview.py:270-276`, `ha1_harness.py:383-391`).
  - It ignores background alpha and never checks SPEC's ≥3:1 for meaningful graphics.
  - A `Case` with zero executed checks records success (`verify_preview.py:111-135`, `ha1_harness.c16_failures:374-378`).
  - Fix: require a minimum number of evaluated pairs or checks per case; composite or refuse translucent backgrounds; add graphic-token pairs.
- **U7 — P3, static. A cleanup failure after an exception reaches stderr only.**
  - `ha1_harness.py:225-235` prints it; `probe_analysis.py:272-280`'s JSON `failures` never records it.
  - The original exception still exits non-zero, but the report omits the orphan rows.
- **U8 — P3, static. Runtime identity cannot detect uncommitted code drift.**
  - The runtime record binds branch+HEAD (`local_runtime.py:149-154`), but nearly all HA1 code is uncommitted or untracked and `dist` is ignored.
  - A server started before an edit still passes identity.
  - Fix: add a working-tree digest (porcelain + diff + HA1 untracked files + dist manifest).
- **U9 — P3, static. Other weak C16 evidence.**
  - Touch: `has_touch` is set but only sizes are measured; there is no tap and no ≤560 scroll-box reachability or clipping check (`verify_preview.py:204-251`).
  - Zoom: `zoom_200` checks overflow only (`:403-411`).
  - Refresh: refresh "restoration" is `page.url == first` after already waiting for that URL (`:286-290`); the rendered range and request are not checked.
  - Price line: no positive in-app check that adjacent same-regime closes connect and weekends break (`:342-344` only asserts zero lines on the regime case).
  - Alignment: button-to-column alignment is left to screenshot viewing.
  - Keyboard: Tab order, skip link and Escape are not asserted.
  - Attribution: nested `with case(...)` blocks attribute an exception only to the inner case.
- **U10 — P3, static/hypothesis. The timeout-dialect choice depends on engine initialization order.**
  - `_timed` reads `get_bind().dialect.is_mariadb` before `execute` connects (`analysis.py:183-190`), and `is_mariadb` is False before the first connect (demonstrated).
  - HTTP routes are safe: auth queries first (`auth.py:24-37,72-77`).
  - `probe_analysis.py:208` records `timeout_dialect` before any connection, so the report may read `mysql:max_execution_time` on MariaDB. That label is cosmetic; `timeout_failures` uses the post-connect value.
- **U11 — P3, hypothesis. Plan-type strictness may false-fail.**
  - `plan_failures` requires `const/eq_ref/ref/range` on every EXPLAIN row (`ha1_harness.py:40,88-92`).
  - Zero-row or const-impossible plans on MariaDB can report other shapes. That would be a false fail, never a false pass.
- **U12 — P3, static, pre-existing.** The ambiguous-resolve copy reads as a stale link.
  - Where: every 409 maps to `conflict` (`analysisApi.ts:43`). An `ambiguous_primary` resolve therefore shows "This link no longer matches today's mapping", the old-link explanation, and hides Retry (`Analysis.tsx:215,223-233`). The test enshrines this (`Analysis.test.tsx:92`).
  - Scope: this is outside the CORRECTION-1 scope. Record it or fix it opportunistically.
- **U13 — P3, hypothesis. The pin effect may re-fire.**
  - Where: `fallback` is memoised on the default `now` param, which is a new function every render (`Analysis.tsx:31,44,49`). `pinRange`, and so the effect deps, change each render, and the effect can call the idempotent `replace` more than once before the route updates.
  - Why tests miss it: tests pass a fixed `now`.

## 7. Open runtime gates

- **C02 transport:** resolve 200/404/409/422 and stale-ID 409 over real HTTP.
- **C11:** loopback non-admin 200 plus a real full-access-host 403 (U4).
- **C13:** ≤4 data SELECTs, EXPLAIN index-constrained plans, ≤43,008 rows/64 sources/1 MiB/32 MiB on MariaDB.
- **C14:** fractional statement limits, CPU interruption 1969, same-connection and pool hygiene, engine 503 translation, 20-warm p95 ≤ 1 s, five-second reader scope (§5).
- **C15:** root/alias/legacy, `?t=`, invalid hash, filter bookmark, canonical Analysis link, Back/refresh, no Analysis board poll in the actual app (U3).
- **C16:** viewed screenshots at 1440/1920/768/390/320, keyboard, 200% zoom, touch, overflow, contrast, errors, identity (U2/U6/U9).

Nothing here is runtime proof. Capture OFF, shared boards ON and migration `b7e3f9c1a2d4` remain release-attributed and were not probed.

## 8. Protected state and actions not taken

No DB/provider/production access, API integration test, fixture, EXPLAIN, timeout probe, preview server or browser. No provisioning, registry, service or migration change. No global Git config change, no commits/pushes/deploy, no workers.

Main and other worktrees, B1C DB/5021, default 3306, promotion DB 3399/5033 and all prior artifacts, including `artifacts/ha1/review/*` and `correction-1/*`, are untouched. Candidate dirty work is preserved. Git-ignored `dist` and `__pycache__` were refreshed by build/test.

## 9. Recommendation (first necessary step only)

One bounded, harness-only Implementer correction for **U1, U2, U3, U4 and U6** (U5/U7/U8 cheap optional). No product change, DB-free verification of that delta only. Mastermind can assess it against this list without another full review loop.

After that, a separately authorized disposable HA1 environment step for C02/C11/C13–C16. The §5 deadline interpretation is Mastermind's ruling. Deployment is not in scope.

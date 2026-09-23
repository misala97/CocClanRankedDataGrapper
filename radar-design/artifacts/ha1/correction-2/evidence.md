# HA1 CORRECTION-2 evidence — Implementer, 2026-09-15

Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`, no upstream (`fatal: no upstream configured`). Implementer: Claude Opus 5, no subagents/workers. Harness-only assignment. Every command below was run by this Implementer, DB-free. No database, provider, production, API integration test, fixture, EXPLAIN, timeout probe, preview server or browser was executed; all new runtime assertions are UNEXECUTED.

## Git (start and end)

- Start: branch/HEAD as above; `git status --short` 59 entries; tracked `git diff --stat` 14 files +982/−35 (the +942 in the REVIEW-2 ruling predates Mastermind's continuity update, per that ruling). All Git commands used per-command `-c safe.directory=<candidate>`; global config read-only (`git config --global --get-all safe.directory` lists two pre-existing entries for the main checkout and `radar-pipeline-audit`, unchanged at end; repro confirms `global_safe_directory_unchanged: true`).
- End of harness work: same branch/HEAD; tracked diff still 14 files +982/−35 (no tracked file touched); `git diff --check` exit 0 (CRLF warnings only); status 60 entries. The one new top-level entry is `personal_apps/downloaded_files/` containing `dashboard.lock` (0 bytes, created 2026-09-15 12:57:49 +0200, during this session's verification batch); no harness, test or reproduction code references that path, its origin is not established, and it is preserved. `git.out.txt`. The continuity notices written afterwards add lines to the two tracked handoffs only (final re-check in the return).
- Owned-file hashes before/after: `baseline/pre-correction-sha256.txt`, `post-correction-sha256.txt`. No application file (features/, static/, app.py, auth.py, models.py, templates/) was edited.

## Commands and results (from `personal_apps` unless noted)

| Command | Result | Log |
| --- | --- | --- |
| `py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py pytest` (REVIEW-2 socket guard, unmodified; `--confcutdir=tests/ha1_unit tests/ha1_unit`) | `236 passed`; `guard: app_imported=False pymysql_imported=False` (was 170; +66 CORRECTION-2 regressions) | `pytest-ha1_unit.out.txt` |
| `py -3.12 ../radar-design/artifacts/ha1/correction-2/mutation_check.py` (first run) | baseline passed; **14/16 mutants caught, 2 survived**: removing the `*/runtime/*` exclusion (redundant and untested) and dropping the sub-second probe from `timeout_failures` (no test) | `mutation_check.first-run-2-survivors.out.txt` |
| same, after removing the redundant exclusion (it could also hide a real `runtime/` source folder), adding an exclusion-rule test on the scripts' real output paths and two `timeout_failures` sub-second cases | baseline 71 passed; **17/17 mutants caught**, every mutant exit 1 with failed tests, guard clean in each subprocess | `mutation_check.out.txt` |
| `py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py ../radar-design/artifacts/ha1/correction-2/repro_correction2.py` | see Reproductions; exit 0; guard clean | `repro_correction2.out.txt`, `fingerprint-inputs.txt` |
| `py_compile` over the six `scratchpad/ha1/*.py`, `tests/test_radar_analysis_api.py`, `tests/ha1_unit/test_ha1_harness.py` and the two correction-2 scripts | `compiled 10` (compile only) | `py_compile.out.txt` |
| from candidate root: `git diff --check` | exit 0 | `git.out.txt` |

The first all-green pytest run (233) was not taken as proof; the mutation check is what established the tests catch regressions, and it caught two gaps that were then closed (236).

## Reproductions (DB-free, this Implementer)

- **U1** (real `git` subprocess on the candidate, `GIT_TEST_ASSUME_DIFFERENT_OWNER=1`, global/system config isolated): CORRECTION-1 form `git -C <candidate> rev-parse HEAD` → exit 128 `detected dubious ownership`; CORRECTION-2 `local_runtime.git('rev-parse','HEAD')` → `1ac39fe4…`; a failing command → `SystemExit: git rev-parse HEAD failed in … (exit 128) …`; global safe.directory unchanged. Unit regression `TestRuntimeGit` does the same on a temporary repository with a space in its path.
- **U4** (app.py's own `_require_login_on_full_access_host` and `_MEMBER_BLUEPRINTS`, parsed from source, in a toy Flask 3.1.3 app; app never imported): CORRECTION-1 form (session on default host) → `302`; `host_session_get` non-admin on full-access host → `403`; admin → `200`; non-admin on loopback → `200`; member gate removed → `200` (so the API suite's `== 403` would fail).
- **U6/U9**: zero-check case → `no check was evaluated; a case with zero checks is not a pass`; shared-block exception attributed to both `resolve_pin_replace` and `de_entry_us_label`; empty selector, `oklch()` colour and no opaque background each fail with attribution; `rgba(255,255,255,0.2)` text on the panel composited to 1.90:1 and fails.
- **U5**: `ReaderBudget(0.250).statement_timeout()` rendered by `SqlStore._timed` as `SET STATEMENT max_statement_time=0.250 FOR SELECT 1` (production code, fake dialect, no engine).
- **U8**: 154 covered inputs (80 radar Python + top-level app modules, 6 HA1 harness, 61 radar frontend source, 2 radar templates, 5 served build files); digest at the last run `f2f48b33…` — it moves with every later edit by design. Full list with per-file SHA-256: `fingerprint-inputs.txt`.
- **U10**: an unconnected SQLAlchemy engine → `initialized: false`, no dialect label, explicit failure.

## Finding dispositions

| Finding | Disposition | Where / regression |
| --- | --- | --- |
| U1 runtime Git | FIXED; DB-free demonstrated | `local_runtime.git(*args, candidate=None)`: `git -c safe.directory=<resolved candidate> -C <resolved candidate> …`, SystemExit on non-zero or unstartable git; used by `serve` and `verify_preview.preflight`. `TestRuntimeGit` (4 tests, real subprocess + scoping/argv + failures) |
| U2 navigation | FIXED in harness; runtime UNEXECUTED | `verify_preview.py` shared block `resolve_pin_replace` / `de_entry_us_label` / `c15_back_to_pre_selection_analysis`: `history.length == length + 1` after pick+pin and a 1.5 s settle, URL unchanged after settling (U13 exposure), Back → `#analysis` and the pre-selection address, Forward → canonical. Static wiring test |
| U3 C15 coverage | FIXED in harness; runtime UNEXECUTED | `c15_routes()` at 1440/390: root/alias/legacy mounts and return link, valid `?t=`, valid hash over `t`, invalid-hash fallback, filter-only + refresh, canonical Analysis link (address, identity, exact request, nav current, Legacy link); `c15_signed_out_redirects` (5 paths, no redirects followed); `c15_no_board_poll_on_analysis` (130 s quiet window > 60 s minute read and 120 s stale re-ask, boot-time board requests recorded not failed, positive control on leaving). Owned `typical` identity only; no restored unsafe suites |
| U4 host authorization | FIXED; toy regression DB-free; API test UNEXECUTED | `tests/test_radar_analysis_api.py`: signed-out control `302 /login`, then `harness.host_session_get(…, FULL_ACCESS_HOST, …)` → exactly `403` on company and resolve; separate loopback test → `200`. Application authorization unchanged. `TestFullAccessHostGate` (4 tests incl. two gate-removal mutations and a static check that `in (302, 403)` is gone) |
| U6 contrast/case checks | FIXED; DB-free | `ha1_harness.Case/cases/record_case/case_failures`, `parse_color` (unsupported raises), `effective_background` (composites translucent layers over nearest opaque ancestor; image/no-opaque → unverified), `contrast_failures` (empty selector, unsupported, unverified, transparent, zero evaluated all fail; attribution per selector; 4.5:1 text, 3:1 graphics). `verify_preview` samples required text pairs and graphics pairs (observed dots, solid and partial count bars, gap outlines, price line, closed-day dash). `TestCaseRecording`, `TestContrast` |
| U5 sub-second timeout | PREPARED; UNEXECUTED | `ha1_fixtures.timeout_probe` adds `cpu_subsecond` via `ReaderBudget(0.250)` + `_timed`: requested/effective, rendered prefix, elapsed, overshoot, post-hoc `budget.check()`, then `SELECT 1` recovery on the same connection; `harness.subsecond_failures` + `timeout_failures` require it. `TestTimeout` |
| U7 cleanup failure reports | FIXED; DB-free | `OwnedFixtures.cleanup_report()` (`not_run/complete/incomplete/kept`, error, remaining exact keys), `CleanupIncomplete.remaining`, exception note; `harness.run_failure_report` keeps original + cleanup failure, redacts credentials, exit 1. Used by `probe_analysis.py` (report `original_failure`/`cleanup`) and `preview_fixtures.py` (`runtime/preview-fixtures-report.json`, manifest kept on failed cleanup). `TestCleanupReport` |
| U8 source/build identity | FIXED; DB-free | `harness.source_fingerprint/fingerprint_inputs/fingerprint_excluded/fingerprint_failures`; runtime record v2 carries it; `serve` refuses without build assets; `preview_identity_failures(fingerprint=…)` refuses drift; `verify_preview` rechecks at the end (`source_build_identity`); `probe_analysis` records start/end and fails on drift. Nothing stops a process. `TestFingerprint`, `TestPreviewIdentity` |
| U9 behavioural strengthening | FIXED in harness; runtime UNEXECUTED | real `tap()` of first/last day with scroll-box and viewport containment; 200% zoom (720×500 @2×) selects a day, 44 px, changes range; refresh checks controls, request and day count; `price_line_runs` on a new `lines` fixture (own window with trading ends and an interior closed date; expected runs from `harness.adjacent_runs`); `chart_control_alignment` (button vs price and count column centres, 2 px); `skip_link_and_tab_order`; `menu_escape`; partial bars patterned (SPEC §3); shared-block attribution; unsupported = failure. `TestChartExpectations`, `TestCaseRecording` |
| U10 dialect | FIXED; DB-free | `probe_analysis` records `harness.dialect_record(...)` only after the admin lookup connected; no eager connection, no product change. `TestDialect` |
| U11 EXPLAIN strictness | DEFERRED by ruling | `plan_failures` unchanged (comment added) |
| U12 ambiguous copy | DEFERRED by ruling | not touched; preview still asserts current `ambiguous_primary` text |
| U13 pin re-fire | DEFERRED hypothesis | U2 block would expose extra history entries or a moving URL; product unchanged |
| Deadline ruling | MEASUREMENT PREPARED; UNEXECUTED | see below |

## Deadline ruling — measurement plan (prepared, not run)

`probe_analysis.py` on the max fixture records, separately:
1. **Statement interruption delay**: CPU probe elapsed − 1.0 s; sub-second probe overshoot (elapsed − effective limit).
2. **Reader elapsed and overshoot**: `read_company` with a store whose company/instrument/closes statements first `SLEEP` just under the limit the reader handed them, so the reader's own budget expires inside the read; records every handed limit and when it was issued, the outcome, elapsed and `elapsed − 5.0`.
3. **Full-request duration**: the same exhaustion through the authenticated route (store methods wrapped for one request, restored in `finally`), with time before the first reader statement (auth/pool) recorded.
Pass/fail (`harness.deadline_failures`) is semantic only: a budget-exhausted read must answer 503 `analysis_limit`, every handed limit in [1 ms, 2 s], ≤4 data statements, all durations measured. Overshoot is reported with `acceptance: mastermind_ruling_required` and never judged against a tolerance chosen here. Normal reads additionally record reader-only elapsed time next to 20-run warm full-request p95 (≤1 s, unchanged) and all resource budgets (unchanged). No claim that post-hoc refusal proves server work stopped at five seconds.

## Static observations for Mastermind (not fixed: product code out of scope)

- `analysis.css` `.rh-an-fill { fill: var(--chatter) }` is an author rule and outranks the `fill="url(#rh-an-hatch)"` presentation attribute `AnalysisChart.tsx` sets on partial bars, so partial bars likely render solid (text `*` still marks them). SPEC §3 requires pattern + text. Static reasoning only; the new `partial_truncated_zero` preview check (`getComputedStyle(...).fill` contains `url(`) would demonstrate it at runtime.
- Harness bug fixed in passing: CORRECTION-1's `reduced_motion` check interpolated a selector containing double quotes into a double-quoted JS string (`querySelector("[role=group][aria-label="Select a day"] button")`), a syntax error at runtime; now `json.dumps`.

## Not executed (held)

`tests/test_radar_analysis_api.py`; `scratchpad/ha1/{local_runtime,probe_analysis,preview_fixtures,verify_preview}.py` against any target, server or browser; any fixture, EXPLAIN, timeout or deadline probe; whole radar Vitest/frontend build (no frontend file changed; no concrete reason to rerun).

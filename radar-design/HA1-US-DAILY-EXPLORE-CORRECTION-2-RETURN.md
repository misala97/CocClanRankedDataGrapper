# HA1 US Daily Explore — CORRECTION-2 return (harness only)

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-CORRECTION-2 · Radar Implementer (Claude Opus 5). Subagents/workers: none. Binding: `HA1-US-DAILY-EXPLORE-CORRECTION-2.md`, `HA1-US-DAILY-EXPLORE-REVIEW-2-RULING.md`. Evidence: `artifacts/ha1/correction-2/evidence.md`.

**Disposition.** U1, U4, U6, U7, U8 and U10 are fixed and demonstrated DB-free (real `git` subprocess under Git's foreign-owner simulation; app.py's own member gate in a toy Flask app; contrast/case rules; cleanup reports; fingerprint; dialect record). U2, U3, U5, U9 and the deadline ruling are implemented as runtime harness assertions and remain **UNEXECUTED**. U11–U13 deferred as ruled. No application code changed. Runtime gates C02/C11/C13/C14/C15/C16 remain OPEN.

## 1. Git and scope

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`; branch `codex/radar-ha1-us-daily-explore`; HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`; no upstream. Verified at start and end with per-command `safe.directory`; no global Git configuration changed (two pre-existing global entries unchanged).
- Tracked diff before the continuity notices: 14 files +982/−35, identical at start and after the harness work — no tracked application file touched. The notices then add lines only to the two tracked handoffs.
- CORRECTION-2 owned edits (all untracked files except the two handoffs):
  - Harness: `personal_apps/scratchpad/ha1/{ha1_harness,local_runtime,verify_preview,probe_analysis,ha1_fixtures,preview_fixtures}.py`
  - Tests: `personal_apps/tests/test_radar_analysis_api.py`, `personal_apps/tests/ha1_unit/test_ha1_harness.py`
  - New evidence: `radar-design/artifacts/ha1/correction-2/*` and this return.
  - Continuity: new current notices in `HANDOFF.md`, `radar-design/HANDOFF.md`, `radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md`, `radar-design/MASTERMIND-STATE.md`, `radar-design/ASSIGNMENTS.md` (+ register row), and a status notice appended to `radar-design/HA1-US-DAILY-EXPLORE-CORRECTION-2.md`.
- Preserved: all other implementation, planner, reviewer and ruling dirt; `artifacts/ha1/{implementation-evidence.md,review,review-2,correction-1}` untouched (REVIEW-2's `dbfree_guard.py` was only executed). Ignored `__pycache__` refreshed.
- Unexplained, preserved: `personal_apps/downloaded_files/dashboard.lock` (0 bytes, created 2026-09-15 12:57:49 +0200, during this session's verification batch). No harness, test or reproduction code references that path; origin not established; not deleted.
- No commits, pushes, deploys, services, registry/migration changes, DB/provider/browser/preview execution.

## 2. Fresh verification (this Implementer, DB-free)

| Check | Result |
| --- | --- |
| `tests/ha1_unit` under REVIEW-2's socket guard | **236 passed** (170 → 236); `app_imported=False pymysql_imported=False` |
| Mutation check (in-memory single-string mutants in subprocesses, sockets blocked) | first run 14/16 caught — two gaps found and closed; final **17/17 caught**, baseline passes |
| DB-free reproductions | U1 plain 128 / scoped HEAD / global unchanged; U4 old 302, new 403, admin 200, loopback 200, gate removed 200; U6/U9 failures attributed; U5 `max_statement_time=0.250`; U8 154 inputs, 5 build files; U10 unconnected engine not labelled |
| `py_compile`, 10 files | compiled |
| `git diff --check` | exit 0 |

Frontend suites and build were not rerun: no frontend or application file changed.

## 3. Finding dispositions

- **U1 — FIXED, demonstrated.** `local_runtime.git` runs `git -c safe.directory=<resolved candidate> -C <resolved candidate> …` and raises a SystemExit naming the command and Git's message; an unstartable git is also a SystemExit. `TestRuntimeGit` creates a real temporary repository, isolates global/system config, sets `GIT_TEST_ASSUME_DIFFERENT_OWNER=1`, proves plain Git exits 128, and proves the runtime reads HEAD without persisting trust.
- **U2 — PREPARED, unexecuted.** Search pick plus pin must grow `history.length` by exactly 1, the URL must not move after a 1.5 s settle, Back must land on `#analysis` at the pre-selection address, and Forward must return to the canonical URL.
- **U3 — PREPARED, unexecuted.** Actual-app C15 coverage with the owned `typical` identity:
  - root and alias mounts; legacy mount and return link
  - five signed-out redirect paths
  - valid `?t=`; a valid hash overriding `t`; invalid-hash fallback
  - filter-only bookmark, plus refresh
  - canonical Analysis link, with exact request and nav state
  - no `/radar/api/board` request during 130 s on Analysis, with a positive control when leaving

  Boot-time board requests are recorded, not failed. The unsafe suites stay excluded.
- **U4 — FIXED, toy-demonstrated; API test unexecuted.**
  - The signed-out control must be `302 /login`.
  - A non-admin session established on `FULL_ACCESS_HOST` must get exactly `403` on company and resolve.
  - A separate loopback test asserts `200`.
  - `TestFullAccessHostGate` runs app.py's own gate code. Removing the member check, or adding `radar` to the members, flips it to 200.
  - Authorization is unchanged.
- **U5 — PREPARED, unexecuted.** A `cpu_subsecond` probe runs through `ReaderBudget(0.250)` and `SqlStore._timed`. It records requested and effective limits, the rendered prefix, elapsed time, overshoot and the post-hoc budget check, then a `SELECT 1` recovery on the same connection. `timeout_failures` requires it, the recovery and connection hygiene.
- **U6 — FIXED.**
  - A case with zero checks fails.
  - An empty required selector fails.
  - Unsupported colours fail explicitly.
  - Translucent layers are composited over the nearest opaque ancestor. An image or no opaque ancestor is an unverified failure.
  - Text pairs need 4.5:1 and meaningful graphics 3:1. The graphics are observed dots, solid and partial bars, gap outlines, the price line and the closed-day dash.
  - Failures are attributed per selector.
- **U7 — FIXED.**
  - `OwnedFixtures.cleanup_report()` returns the status, the error and the exact remaining keys.
  - `run_failure_report` keeps the original and the cleanup failure, redacts credentials and exits 1.
  - Wired into `probe_analysis` and `preview_fixtures`. A failed cleanup keeps the manifest.
- **U8 — FIXED.**
  - The fingerprint is a deterministic digest over the radar app Python and top-level app modules, HA1 harness, radar templates, radar frontend source and served `dist`. Untracked files are included.
  - Excluded: `radar-design/artifacts/*` (runtime records, manifests, reports, screenshots), caches, logs, tmp and frontend test files.
  - Runtime record v2 carries it, and `serve` refuses without build assets.
  - The preview refuses on drift at preflight and at the end of the run. The probe records it at start and end.
  - Nothing stops a process.
  - Covered list: `fingerprint-inputs.txt`.
- **U9 — PREPARED, unexecuted.**
  - Real taps on the first and last day, with scroll-box and viewport containment.
  - Usable 200% zoom: select a day, 44 px targets, change the range.
  - Refresh restores the controls, the request and the day count.
  - `price_line_runs` on a new `lines` fixture (trading days at both ends, a closed date inside): exact drawn runs and point counts, no crossing.
  - Day-button to column-centre alignment within 2 px.
  - Skip link, Tab order and menu Escape.
  - Partial bars patterned, per SPEC §3.
  - Shared-block attribution; unsupported checks are failures.
- **U10 — FIXED.** The dialect is recorded via `harness.dialect_record` only after the admin lookup connected; an uninitialized dialect is refused. No eager connection, no reader change.
- **U11 — DEFERRED.** Plan checks are unchanged.
- **U12 — DEFERRED.** Copy is untouched.
- **U13 — DEFERRED hypothesis.** U2's settle and history checks would expose it; product unchanged.

## 4. Deadline ruling in the measurement plan (no guarantee claimed)

Five seconds is treated as the reader/resolver budget, excluding pre-reader auth and pool wait. `probe_analysis.py` separately records:

- **Statement interruption delay:** CPU and sub-second probe overshoot.
- **Reader elapsed and overshoot:** measured on a read whose statements spend the limits the reader hands them, with every handed limit and its issue time.
- **Full-request duration:** the same exhaustion over HTTP, with the time before the first reader statement.

Semantics asserted:
- 503 `analysis_limit`, never success
- every limit in [1 ms, 2 s]
- ≤4 data statements
- all durations measured

Overshoot carries `acceptance: mastermind_ruling_required` and is never judged against a self-chosen tolerance. Existing unchanged items:
- 20-run warm full-request p95 ≤1 s
- row, source, byte and memory budgets
- `TIMEOUT_GRACE_S` from CORRECTION-1

Nothing here proves server work stops at five seconds.

## 5. Remaining defects and deviations

- **Static observation, product, not fixed.** The `.rh-an-fill` CSS fill outranks the partial bar's `fill="url(#rh-an-hatch)"` attribute. Partial bars therefore likely render solid, against SPEC §3's "pattern + text". The new preview check would demonstrate it at runtime. This is a Mastermind decision.
- **Harness bug fixed in passing.** CORRECTION-1's `reduced_motion` JS selector quoting was a runtime syntax error.
- **Mutation-found gaps, closed.** The redundant `*/runtime/*` exclusion was removed: it was untested and could hide a real `runtime/` source folder. A sub-second requirement test was also missing.
- **Tolerances not specified by SPEC and newly chosen for harness checks:**
  - 2 px alignment
  - 130 s board-quiet window (derived from 60 s and 120 s client timers)
  - 1.5 s pin settle

  Each is recorded in facts and open to Mastermind adjustment. `TIMEOUT_GRACE_S` 1.0 s is unchanged from CORRECTION-1.
- **Unexplained untracked file.** `personal_apps/downloaded_files/dashboard.lock`; see §1.
- **Runtime-only.** Every new browser, API, probe and fixture assertion is unexecuted. Their selectors (e.g. nav link names, `#radar-hub-data`, Human Chatter nav text) come from source reading and the promotion script, not from execution.

## 6. Open gates and next step

- **C02:** resolve transport.
- **C11:** loopback 200 and full-access-host exactly 403.
- **C13:** statements, EXPLAIN, rows and memory on MariaDB.
- **C14:** timeouts including the 0.250 s probe, recovery, 503 translation, warm p95 and the deadline measurements.
- **C15:** actual-app routes and board-poll suppression.
- **C16:** viewed screenshots, keyboard, zoom, touch, contrast, errors and identity.

All six are OPEN and UNEXECUTED; no authorized HA1 target exists and none was sought. Capture OFF, shared boards ON and migration `b7e3f9c1a2d4` remain release-attributed and were not probed.

Requested decision: a focused Mastermind assessment of this harness delta against U1–U10. If satisfactory, prepare a separately authorized disposable environment and QA; not another full product review.

## 7. Protected state

Untouched:
- main and other worktrees
- B1C DB and port 5021
- default 3306
- promotion 3399/5033 and their artifacts
- prior HA1 artifacts and reviews
- application code

The two global `safe.directory` entries were unchanged. No process was stopped, no port bound, no network used by tests.

# HA1 REVIEW-2 evidence — Reviewer/QA execution, 2026-09-15

Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`, no upstream (`fatal: no upstream configured`). Reviewer: Claude Opus 5, no subagents/workers. Every command below was run by this Reviewer. No database, provider, production, preview server, browser, fixture, `test_radar_analysis_api.py` or DB/preview script was executed. All Git commands used per-command `-c safe.directory=<candidate>` (or `*` for the first read-only status); no global Git config was changed.

## Git

- Start and end: branch/HEAD as above. `git diff --stat`: `14 files changed, 942 insertions(+), 35 deletions(-)` at end (tracked files untouched by this review). `git status --short`: 56 lines, same entries as at start; this review adds only files under the already-untracked `radar-design/artifacts/ha1/` plus `radar-design/HA1-US-DAILY-EXPLORE-REVIEW-2-RETURN.md`. `git diff --check`: no output.
- `npm run build` rewrote the git-ignored `personal_apps/static/*/dist`; pytest refreshed existing `__pycache__` files.

## Commands and results (from `personal_apps` unless noted)

| Command | Result | Log |
| --- | --- | --- |
| `py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py pytest` (blocks `socket.connect`/`connect_ex`/`create_connection`, then `pytest -p no:cacheprovider --confcutdir=tests/ha1_unit tests/ha1_unit -q`) | `170 passed in 1.21s`; `guard: app_imported=False pymysql_imported=False` | `pytest-ha1_unit.out.txt` |
| Attempt 1 of the same, launched as a script without the cwd on `sys.path` | collection error `ModuleNotFoundError: No module named 'features'` — reviewer wrapper error, not a candidate defect; fixed by `sys.path.insert(0, os.getcwd())` | `pytest-ha1_unit.attempt1-wrapper-syspath.out.txt` |
| `py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py ../radar-design/artifacts/ha1/review/contract_repro.py` (REVIEW-1 script, unmodified) | #2 slot fields sum 96, invalid 0; #3 backend runs `[["2026-09-11"],["2026-09-14"]]`; #4 only `bluesky` represented (pre-identity-only `stocktwits` gone); #1 144 source-bucket rows | `contract_repro.review-2.out.txt` |
| `npx vitest run -c vite.radar.config.ts` navigation, Hub, queries, analysisApi, analysisQueries, Analysis, AnalysisChart, analysisCss, Chatter, ChatterWorkspace | `Test Files 10 passed (10)`, `Tests 228 passed (228)` | `vitest-focused.out.txt` |
| `npx tsc --noEmit` | exit 0, no output | `tsc.out.txt` |
| `npm run build` | exit 0; `built in 1.40s` / `built in 1.65s` | `build.out.txt` |
| `GIT_TEST_ASSUME_DIFFERENT_OWNER=1 git -C <candidate> rev-parse HEAD` (the form `local_runtime.git` uses) vs `git -c safe.directory=<candidate> -C <candidate> rev-parse HEAD` | plain: `fatal: detected dubious ownership`, exit 128; per-command safe.directory: HEAD, exit 0 (git 2.39.1.windows.1). Without the simulation variable the plain form succeeds for this shell's user | `git_ownership_simulation.out.txt` |
| `py -3.12 -c "... sa.create_engine('mysql+pymysql://u:p@127.0.0.1:1/x') ..."` (create_engine does not connect) | `is_mariadb before first connect: False`, 0 connections checked out (SQLAlchemy 2.0.49) | `dialect_preconnect.out.txt` |
| `py -3.12 toy_full_access_host_cookie.py` (from this directory; stand-in Flask app with app.py's gate shape; imports neither the Radar app nor models; no DB/socket) | Flask 3.1.3 / Werkzeug 3.1.8: session request on default host `200`; same client with `base_url=http://mgemmel.viewdns.net` answers `302 /login` — the session cookie does not reach the other host, so the gate's non-admin 403 branch is never reached | `toy_full_access_host_cookie.py`, `toy_full_access_host_cookie.out.txt` |

## DB-freeness before execution

- `tests/ha1_unit` has no conftest; `--confcutdir` stops `tests/conftest.py` (which imports `app`). Imports inspected: `ha1_harness` (stdlib), `local_runtime` (no app import until `bind()`), `ha1_fixtures` (models -> `extensions.SQLAlchemy()`, no engine), `features.radar.analysis{,_contract}`. The guard would have raised on any socket connect; `app` and `pymysql` were never imported.
- `contract_repro.py` imports only the pure contract (as REVIEW-1 recorded); ran under the same guard.
- The toy script and dialect check construct no connection.

## Not executed (held)

`tests/test_radar_analysis_api.py`; `scratchpad/ha1/{local_runtime,probe_analysis,preview_fixtures,verify_preview}.py`; any fixture, EXPLAIN, timeout probe, preview server or browser; whole radar Vitest and `pending.test.tsx` (28 prior failures remain Implementer-attributed).

# PERF3 progress

The record of `PERF3-PLAN.md`'s execution, under `PERF2-CODEX-RULING.md`.
Every number names the script that produced it, the database it ran on and
the buffer pool it found. A `pending` answer is never reported as a board.

## Workspace

| | |
| --- | --- |
| Worktree | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3` |
| Branch | `codex/radar-perf3`, created from `afe1246` (the reviewed PERF2 tip; `personal_apps/` byte-identical to the deployed `4221196`) |
| Drift check | `git diff --stat 4221196 origin/main -- personal_apps/` is EMPTY at `origin/main = fe68454`; the two commits above `4221196` on `main` are documentation only. No source drift to reconcile. |
| First commit | `4f8ad5f` — Codex's uncommitted PERF2 ruling edits (`CODEX-DECISIONS.md` +63, `HANDOFF.md` +4) carried in unchanged, plus `PERF2-CODEX-RULING.md`. The `radar-perf2` worktree still holds them uncommitted, untouched. |
| Test database | `personal_apps_radar_perf3` — `mysqldump --single-transaction --routines --events` of `personal_apps_radar_te1` restored into a fresh schema: stamp `a7c31f0b52d4`, **29 foreign keys**, 1,103,010 `radar_bucket_sources` rows, seeded admin present, 34 gym exercises. The worktree `.env` (untracked, ignored) names it. |
| Scale database | `personal_apps_radar_perf3_scale` — dump of `personal_apps_radar_perf1` WITHOUT the spike's `radar_board_results` and the `perf_numbers`/`perf_write_numbers` helper tables. Physical `radar_bucket_sources` indexes on the source were exactly the deployed three (`PRIMARY`, `ix_radar_bucket_sources_start`, `ix_radar_bucket_sources_coverage`); the held index is absent. Its `alembic_version` arrives as `c4e17b90d3f2` (PERF1's stamp) and is reset on THIS CLONE ONLY to `a7c31f0b52d4` after the physical schema is re-verified — see "Scale database stamp" below. `personal_apps_radar_perf1` itself is not modified. |
| Engine | MySQL 8.0.46, `innodb_buffer_pool_size` 2560 MB, strict `sql_mode` (`STRICT_TRANS_TABLES,...`). Target is MariaDB 10.11.14 — mechanism transfers, seconds do not. |
| MariaDB rehearsal | portable `mariadb-10.11.14-winx64` already on this machine from P1, run on port 3399 with a fresh datadir in this session's scratchpad. Command recorded under Task 2. |
| Frontend | `npm ci` + `npm run build` in the worktree: both Vite builds emitted, manifests present. |
| Interpreter | Python 3.12.6; Flask 3.1.3, SQLAlchemy 2.0.49, Flask-Migrate 4.1.0, alembic 1.18.4, PyMySQL 1.2.0, APScheduler 3.11.2, pytest 9.0.3, playwright 1.61.0; node 24.19.0, npm 11.17.0. |

## Baseline before any code change

`PYTHONPATH=. py -3.12 -m pytest tests/test_radar_api.py tests/test_radar_hub_page.py tests/test_radar_board_cache.py tests/test_radar_watch_api.py tests/test_radar_observations.py tests/test_vite_assets.py tests/test_gym_routes_smoke.py tests/test_radar_board.py tests/test_radar_board_sort.py tests/test_radar_projection_migration.py -q`
on `personal_apps_radar_perf3`: **223 passed, 5 skipped** in 72.9 s. The
five skips are `test_radar_projection_migration.py`, which pins the
disposable name `personal_apps_radar_wt` and skips on any other database.

## Task ledger

| Task | Status | Commits | Review |
| --- | --- | --- | --- |
| 1 key + namespace | open | | |
| 2 tables, migration, store | open | | |
| 3 producer | open | | |
| 4 read path, flag, API | open | | |
| 5 old board client | open | | |
| 6 hub client | open | | |
| 7 parity | open | | |
| 8 scale verification + browser | open | | |
| 9 suites + release package | open | | |
| whole-branch review | open | | |

## Findings and rulings

(appended per task: every reviewer finding, its severity and disposition;
every deviation from the plan with the measurement or reason that forced it)

## Measurements

(appended by Task 8)

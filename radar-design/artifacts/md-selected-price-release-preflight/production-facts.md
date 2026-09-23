# Production facts — read-only, 2026-09-15 23:16–23:27 CEST (sanitized)

Executed by the Deployer over the existing SSH credential (`ssh root@194.164.29.97`). Every command was a read; the only host mutations were the creation and removal of the scratch directory named below. No service was stopped, restarted or reloaded; no migration, flag, unit file or `.env` change.

## Identity and checkout

| Fact | Value |
| --- | --- |
| hostname / kernel | `ubuntu`, Linux 6.8.0-138-generic |
| checkout | /root/coc-stats on `main` at **daadf3868caedcb5db858378e919cba68b735f8a**; local ref origin/main = same |
| tracked tree | clean; untracked only: personal_apps/nasdaqlisted.txt, personal_apps/otherlisted.txt, personal_apps/scratchpad/arctic_backfill_resume.json, reports/, venv/ (same five as the HA1 release record) |
| release wrapper | /root/update_coc.sh sha256 `1991e9655599d26b45ae837040e17bf0ecbef0ec93a9bfa5325bcb7270b6711c` = tracked radar-design/perf3-release/update_coc_wrapper.sh at HEAD (byte-equal) |
| runner | wrapper takes a release lock, runs /root/backup_db.sh FIRST, fetches, then executes origin/main's radar-design/perf3-release/deploy_perf3.sh in `routine` mode against `origin/main` |
| /root/perf3-release/ | deploy-ad531ef.sh, env-before-ad531ef, ha1-smoke-daadf38.{py,out.json}, hub-before-design-reference.html, update_coc.before-ad531ef.sh (unchanged before/after this preflight) |

## Web launcher, interpreter, workers

| Fact | Value |
| --- | --- |
| unit | /etc/systemd/system/personal_apps_web.service: `WorkingDirectory=/root/coc-stats/personal_apps`, `Environment="PATH=/root/coc-stats/venv/bin"`, `ExecStart=/root/coc-stats/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5001 app:app`; no EnvironmentFile |
| processes | master 215016 + workers 215064, 215065 (argv[0] `/root/coc-stats/venv/bin/python3`), up since 15:16:25 CEST (HA1 release), NRestarts=0; coc_web is a separate gunicorn (3 workers, :5000) on the same checkout |
| interpreter | venv/bin/python3 → /usr/bin/python3, Python 3.12.3; `sys.executable` inside the venv = `/root/coc-stats/venv/bin/python`, `sys.prefix` = `/root/coc-stats/venv`; requests 2.34.2, SQLAlchemy 2.0.52, PyMySQL 2.2.8 |
| main-process environment (names only) | HOME INVOCATION_ID JOURNAL_STREAM LANG LOGNAME MEMORY_PRESSURE_WATCH MEMORY_PRESSURE_WRITE PATH SHELL SYSTEMD_EXEC_PID USER — no PYTHONPATH/PYTHONHOME/PYTHONSTARTUP, no WEB_CONCURRENCY |
| flag source | app.py `load_dotenv(override=True)` at import reads /root/coc-stats/.env into os.environ; personal_apps/.env does not exist. A flag change therefore needs a `.env` edit plus `systemctl restart personal_apps_web` |
| selected-price flags | `RADAR_SELECTED_PRICE_CHARTS_ENABLED` / `RADAR_SELECTED_PRICE_YAHOO_ENABLED`: **0 lines in .env, absent from the process environment → both OFF** (candidate default) |
| other flags | `.env:41 RADAR_BOARD_SHARED_RESULTS=on`; RADAR_OBSERVATION_CAPTURE_ENABLED absent (unchanged from HA1 record) |
| worker topology | 2 gunicorn workers → at most 2 fetch children host-wide for this feature; WEB_CONCURRENCY unset, so Admin's "Unknown" is the honest configured state |

## Schema, services, health, backups

| Fact | Value |
| --- | --- |
| `flask db current` (venv, personal_apps) | `b7e3f9c1a2d4 (head)`; the candidate adds no migration |
| units | personal_apps_web, coc_web, coc_scheduler, personal_apps_gym_notifier, radar_ingest, radar_board_producer: all active + enabled; 0 failed units |
| HTTP | `GET http://127.0.0.1:5001/radar/` → 302 (signed out) in 2 ms; gunicorn journal, last 2 h, priority err: no entries |
| MariaDB | 10.11.14-MariaDB-0ubuntu0.24.04.1 on 127.0.0.1:3306 (mariadbd pid 161528); global max_statement_time=0 (unlimited), max_connections=151, wait_timeout=28800, tx_isolation REPEATABLE-READ; Threads_connected 18 before and after the checks |
| app DB account | `.env` key DB_USER (value not recorded here) = `coc_user@localhost`, GRANT ALL on personal_apps.* and coc_stats.*; SET STATEMENT max_statement_time needs no extra privilege |
| backups | cron `15 3 * * * /root/backup_db.sh >> /root/db_backups/backup.log`; /root/db_backups latest: db_2026-09-15_0315.sql.gz 248,454,169 B (nightly), db_2026-09-15_1512.sql.gz 238,232,516 B (HA1 release, SHA-256 981e466e…, gdrive copy listed per the HA1 record); disk 24G/232G used |
| backup-first procedure | the wrapper runs /root/backup_db.sh before any mutation (verified by reading the wrapper); restore mechanism proven in FOUNDATIONS-LEDGER "P2 backup restore" — not repeated |

## Scratch work on the host (removed)

- Directory: `/root/sp-preflight-scratch-daadf38-20260915` (non-served, not under /root/coc-stats), from tarball `sp-preflight-scratch-daadf38-20260915.tgz` sha256 `4e4e2b719bad872c8846913644dcf7a9536bd7ce1e370304d7ff8f82d7a794ad` (22 files: LF-normalized copies of the accepted package files listed in linux-subprocess-harness.out.json plus tests/__init__.py, the two harness scripts and fingerprint-final.json) and `data.tgz` sha256 `2b7383182ab87d92aecf6d1d5c6bcee4f0861d30eb4165da17898dee0f96ed8f` (features/radar/data/*, tracked, unchanged; config.py reads them at import).
- Runs: preflight_harness.py (one child at a time), preflight_db.py (read-only), probe_debug.py (one more synthetic child, stderr visible). No dependency installed; the serving checkout untouched.
- Cleanup 23:27 CEST: `pgrep -af "tests.selected_price_unit|preflight_harness|probe_debug|preflight_db"` empty; `rm -rf` of exactly the directory and tarball; `ls` confirms both gone; `ls /root | grep -i preflight` empty.
- After cleanup: HEAD daadf38 unchanged, same five untracked paths, six units active, 0 failed, personal_apps_web MainPID 215016 / ActiveEnter 15:16:25 CEST unchanged, selected-price flag lines still 0, wrapper hash unchanged, Threads_connected 18.

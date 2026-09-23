# MD-SELECTED-PRICE-RELEASE-PREFLIGHT — Deployer return, 2026-09-15

Deployer: Claude Fable 5.1, one worker, no subagents. Assignment: radar-design/MD-SELECTED-PRICE-RELEASE-PREFLIGHT-PROMPT.md (binding bounds). Evidence: radar-design/artifacts/md-selected-price-release-preflight/ (git-facts.md, production-facts.md, yahoo-usage-conditions.md, linux-subprocess-harness.out.json, mariadb-readonly-probe-FT.out.json, probe-child-debug.txt, the two harness scripts).

**Outcome: decision-ready. No blocker for deploying the accepted candidate with both flags OFF, and the evidence supports the owner additionally turning `RADAR_SELECTED_PRICE_CHARTS_ENABLED` on (stored-fallback charts). `RADAR_SELECTED_PRICE_YAHOO_ENABLED` is NOT supported by evidence: Yahoo's published terms condition automated collection on express prior permission, so no live request was made and live request-form/closed-session/throttle behaviour stays unverified. Nothing was committed, pushed, deployed, restarted, migrated or activated; production flags unchanged.**

## 1. Commits, drift, fingerprint (verified fresh)

| Item | Value |
| --- | --- |
| Candidate | C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts, branch codex/radar-selected-price-charts, HEAD **daadf3868caedcb5db858378e919cba68b735f8a**, application changes uncommitted |
| origin/main (fetched) | daadf3868caedcb5db858378e919cba68b735f8a |
| Production HEAD (root@194.164.29.97:/root/coc-stats, branch main) | daadf3868caedcb5db858378e919cba68b735f8a, tracked tree clean |
| Drift | **none** — candidate base = origin/main = production |
| Accepted fingerprint | recomputed with the correction-2 script: **0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0**, 16 modified / 29 added / 5 generated, `differs_from_compare: []` |
| Local `main` ref | fe684540… (worktree CodingStuff-worktrees/radar-release-merge), 89 commits behind origin/main, currently clean: stale, must not be the integration path |
| Hygiene | `git diff --check` clean; no migration files in the candidate; secret scan: only the documented dummy sentinel in test_launcher_isolation.py |

## 2. Findings by area

### 2.1 Linux / gunicorn / venv (VERIFIED on the host, synthetic)

Facts: personal_apps_web = `/root/coc-stats/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5001 app:app`, WorkingDirectory /root/coc-stats/personal_apps, unit environment PATH only; workers' interpreter is the venv python3 → /usr/bin/python3 3.12.3; `sys.executable` in that venv resolves to `/root/coc-stats/venv/bin/python` (what `subprocess_launcher` will use); requests 2.34.2. No PYTHON* variables and no WEB_CONCURRENCY in the process environment; 2 workers → ≤2 fetch children on the host. Flags are loaded from /root/coc-stats/.env by `load_dotenv(override=True)` at app import, so any flag change is `.env` edit + `systemctl restart personal_apps_web`.

Scratch run (`/root/sp-preflight-scratch-daadf38-20260915`, non-served, removed after; copied accepted files hash-match the manifest, `copied_all_match: true`):
- `python -E -s -B -c "import features.radar.price_chart_fetch"` with `env={}` from the package root: rc 0, sys.prefix = venv, flags E/s/B all set, no flask/sqlalchemy/models/app/dotenv/pymysql loaded, certifi bundle present. Child environment on POSIX is `{}` as coded (Python itself adds only `LC_CTYPE` through C-locale coercion).
- The **real production child program** (`price_chart_fetch.main()` via the test-only probe wrapper) issued exactly `/v8/finance/chart/AAPL?interval=5m&period1=1788960600&period2=1789502400&includePrePost=false` to a loopback server (headers Accept, Accept-Encoding, Connection, Host, User-Agent; no cookie) and wrote a valid `{"kind":"ok","bars":[[…,100.0],[…,100.5],[…,null]],…}` result to stdout — the candidate's exact 1W epoch form, on Linux, under the venv interpreter and the minimal environment.
- Lifecycle through the production `Coordinator` + `subprocess_launcher`, one child at a time: normal 0.267 s success; **hanging → timeout at 6.219 s, SIGTERM (-15), reaped**; oversized 0.385 s invalid, reaped; early_exit rc 3; garbage; nonzero rc 5; stderr_flood success. Every child: `poll()` set, `os.kill(pid,0)` gone, reader thread ended, both pipes closed; no quarantine; `pgrep` shows no leftover; the six services were unaffected throughout.

**Concrete runtime defect (test-only, not patched):** `tests/selected_price_unit/probe_child.py:35` raises `TypeError: argument of type 'NoneType' is not iterable` on this Ubuntu/venv because a system `sitecustomize` module is in `sys.modules` even under `-E -s` and its `__doc__` is None. It fires AFTER `price_chart_fetch.main()` returned its result, so production behaviour is unaffected, but `test_launcher_isolation.py` would fail on the host as written (Windows evidence stands). Details: probe-child-debug.txt.

Limits: synthetic children and a loopback, not the live provider; harness scheduling numbers are this host's, not a guarantee; not exercised inside a gunicorn worker (same interpreter, same cwd, same env source — but not the forked worker itself).

### 2.2 Provider / usage conditions (READ; live requests NOT made)

Yahoo ToS §2.4(i) forbids collecting data "using any automated means … for any purpose without our express, prior permission"; §2.5/§2.4(j)/§2.8 add commercial/redistribution limits; the Developer API ToU covers keyed APIs, not this endpoint; the Finance help page forbids redistribution. Technical access exists (radar_ingest already uses `YahooProvider(YahooHttp())` on the same endpoint), but per SPEC §1 that does not establish permission. Because the documented conditions are not consistent with unattended automated requests without permission, **0 of the optional 4 requests were made**. Live epoch-form acceptance, closed-session/holiday shape and throttling remain unverified. Source: yahoo-usage-conditions.md.

### 2.3 MariaDB (VERIFIED on existing data, read-only)

pymysql 2.2.8 as the app's own `coc_user@localhost`, one connection, `SET SESSION TRANSACTION READ ONLY` + `START TRANSACTION READ ONLY`, rolled back and closed:
- Timeout mechanism: `SET STATEMENT max_statement_time=1 FOR SELECT SLEEP(2)` → **errno 1969** "Query execution was interrupted (max_statement_time exceeded)" after 1.001 s; `SELECT 1` on the same connection succeeded; global and session `max_statement_time` stayed 0 before/after (statement-scoped, pool-safe). This is exactly `analysis.TIMEOUT_ERRNOS` → `read_limit` 503.
- EXPLAIN + timed execution for ticker **FT** (XNYS, USD, mapped 2026-08-30; HA1's smoke ticker), 36 concrete sources, windows 1D 2026-09-15 08:00Z→now and 1W 2026-09-09 13:30Z→09-15 20:00Z:

| reader statement | plan | executed (max_statement_time=1) |
| --- | --- | --- |
| company_by_symbol | const on ix_radar_ticker_universe_symbol | 1 row, 0.5 ms |
| primary_candidates | ref on ix_radar_instrument_primary | 1 row, 0.5 ms |
| bucket_rows 1W | range on PRIMARY (ticker,bucket_start,source), est. 5,534 | 2,595 rows, 40.2 ms |
| bucket_rows 1D | range on PRIMARY, est. 2,676 | EXPLAIN only |
| quote_rows 1D | range on uq_radar_quote_market, est. 26, filesort | 24 rows, 1.7 ms |
| daily_rows 1W | range on uq_radar_daily_close_market, est. 4 | 4 rows, 1.3 ms |
| tone_rows 1W (48 h retention bound) | derived: e range on ix_radar_mention_events_bucket est. 1,097; p eq_ref uq_radar_post_source_ext; m ref ix_radar_mentions_post; temp+filesort on 1,097 derived rows | 36 rows, 93.7 ms |

No full scan on any large table (radar_bucket_sources ≈11.4 M rows, radar_daily_closes ≈5.8 M, radar_mention_events ≈1.5 M). Row counts are far inside the reader bounds (98,304 source rows, 20,000 quotes, 32 daily). Limits: one ticker, one moment, cold cache not controlled; not a latency benchmark; DB-backed pytest suites not run (excluded by the prompt).

### 2.4 Topology, schema, services, backup (VERIFIED)

Schema `b7e3f9c1a2d4 (head)`; candidate adds no migration (both `flask db upgrade` calls will be no-ops). Six units active+enabled, 0 failed; `/radar/` 302 in 2 ms signed out; no gunicorn error journal lines in 2 h. Wrapper /root/update_coc.sh is byte-equal to the tracked update_coc_wrapper.sh (sha256 1991e965…), runs /root/backup_db.sh first, then origin/main's deploy_perf3.sh `routine` (stop six units → reset --hard → pip → npm ci+build → both migrations → producer readiness → restore units; routine mode requires RADAR_BOARD_SHARED_RESULTS=on, which .env:41 has). Nightly backup cron 03:15; latest db_2026-09-15_0315.sql.gz (248 MB) and the HA1 release backup db_2026-09-15_1512.sql.gz; 209 GB free. Restore mechanism proven earlier (FOUNDATIONS-LEDGER P2), not repeated.

## 3. Recommended flags

**Release with both flags OFF (the candidate default, no `.env` change in the release window), then, as a separate owner-approved step, turn `RADAR_SELECTED_PRICE_CHARTS_ENABLED=on` — leaving `RADAR_SELECTED_PRICE_YAHOO_ENABLED` OFF.**

- Both OFF: the new route answers 404 `feature_disabled`, the hub keeps the original chart, no reader query and no child ever runs. Zero behavioural change; proves the build/deploy path only.
- Charts ON / Yahoo OFF: supported by 2.1 (nothing spawns when Yahoo is off), 2.3 (plans/timeouts on real data) and the accepted local QA; FT has 24 stored 1D quotes and 4 daily closes inside the current windows, so the stored fallback has data. Acquisition state is `disabled`, ops shows `yahoo_enabled=false`, 0 starts.
- Both ON: **not recommended** — usage conditions unresolved (2.2) and no live request evidence. If the owner later rules the usage question, a further bounded live check is the next gate, not a flag flip.

## 4. Exact backup-first deployment sequence (not executed)

Local, in the candidate worktree (the local stale `main` worktree stays untouched):
1. `git fetch origin`; require `git rev-parse origin/main` = daadf3868caedcb5db858378e919cba68b735f8a (abort on drift); re-run the fingerprint `--check-only --compare` → must print `differs_from_compare: []`.
2. Stage narrowly: the 45 `modified`/`added` paths from fingerprint-final.json (all under personal_apps; dist is ignored and rebuilt on the host; exclude __pycache__, planner docs, PNG/logs). Commit `feat(radar): selected-instrument 1D/1W price charts (both flags off)`. Optional second commit: radar-design MD-SELECTED-PRICE-* records, notices and text evidence (HA1 precedent).
3. `git diff --check`; fingerprint check again (application files unchanged by committing).
4. `git push -u origin codex/radar-selected-price-charts`; then `git push origin HEAD:main` — fast-forward only (base == origin/main). Record the pushed SHA = release SHA.

Host (window away from 03:15; ~106 s personal_apps_web outage expected, coc_web restarts too):
5. Preflight reads: HEAD still daadf38, six units active, `grep -c RADAR_SELECTED_PRICE .env` = 0, disk, no release unit present.
6. `systemd-run --unit=radar-selected-price-release-<sha7> --description=Radar-selected-price-authorized-routine-release /root/update_coc.sh`; follow `journalctl -u radar-selected-price-release-<sha7> -f` and /var/log/perf3-release/perf3-release-*.log. Expect: backup `OK … + gdrive` (record file, size, gzip -t, SHA-256), `git reset --hard <sha>`, pip satisfied, `npm run build` emitting a new hub-*.js/css, both `flask db upgrade` no-ops at b7e3f9c1a2d4, producer readiness pass, `release succeeded candidate=<sha> activated=1`, six units restored.
7. Post-release smoke (bounded, admin test-client method as HA1, GET only, no writes): `/radar/` 200 with hub mount; `/radar/api/ops` 200 containing `selected_price_ops` with `charts_enabled=false`, `yahoo_enabled=false`, pid/scope=process; `/radar/api/ticker/FT/price-chart?span=1D&market=us` → 404 `feature_disabled` signed in, 302 signed out; served hub bundle contains the selected-price code; radar_ingest cycles `ok` within 5 min; six units active, 0 failed; no traceback lines in the gunicorn journal.

Optional activation step (separate owner approval, reversible in seconds):
8. `cp /root/coc-stats/.env /root/perf3-release/env-before-selected-price-<sha7>` (private, chmod 600); append `RADAR_SELECTED_PRICE_CHARTS_ENABLED=on`; `systemctl restart personal_apps_web`; smoke: price-chart FT 1D and 1W → 200, `acquisition.state="disabled"`, `price.kind` stored_quote / daily_close with `fallback=true`, chatter slots and tone present, `warnings` sane; ops `charts_enabled=true`, `yahoo_enabled=false`, rolling starts 0, in_flight false; Research and shared Chatter panel render the new chart in the owner's browser (owner look, optional).

## 5. Rollback (target freshly verified)

- **Rollback SHA: daadf3868caedcb5db858378e919cba68b735f8a** (= production HEAD and origin/main at 23:16 and again at 23:27 CEST after the checks).
- Flag-level (fastest): remove the `RADAR_SELECTED_PRICE_*` lines from `.env` (or restore env-before-…), `systemctl restart personal_apps_web`. Charts OFF stops new admissions immediately; with Yahoo OFF no child ever existed. If Yahoo had been ON: a child lives at most 6 s deadline + 1 s cleanup, the coordinator reaps on `atexit`, and the gunicorn restart ends the owning worker anyway — no waiting needed beyond the restart.
- Code-level (durable across the wrapper's reset): `git revert <app commit sha>` (single-parent commit, no `-m`; revert the docs commit too if made) on main, push, then run /root/update_coc.sh again through a transient unit → backup, reset to the reverted SHA, migrations no-op (no migration to keep), readiness, restore. A bare `git reset --hard daadf38` on the host is NOT durable (the next wrapper run re-applies origin/main) and is emergency-only with the wrapper inhibited.
- Schema: nothing to downgrade.

## 6. Actions, ownership, cleanup

- Actions: read-only Git/SSH/DB inspection; scratch directory created and **removed** (verified gone, no leftover processes); zero provider requests; no application edits, dependency installs, commits, pushes, deployments, restarts, migrations or flag changes. Production flags/services verified unchanged after the checks (same HEAD, MainPID 215016, ActiveEnter 15:16:25 CEST, 0 flag lines, wrapper hash).
- Dirty ownership: this return, radar-design/artifacts/md-selected-price-release-preflight/, and CURRENT notices in HANDOFF.md, radar-design/HANDOFF.md and radar-design/MD-SELECTED-PRICE-LEDGER.md. Everything else in the candidate tree is preserved as found. Main/other worktrees, source workspace, B1C/5021, promotion/5033, DB 3306/3399, HA1/3461, C:/Users/michi/.radar-ha1-local-qa untouched.
- Preserved: accepted local QA and the known baselines (28 pending.test.tsx, 3 Yahoo regression fails) are carried, not rerun. The Linux test-harness defect in 2.1 is reported, not patched, and needs no new review cycle before an OFF/charts-only release.

## 7. Requested decision

Approve, or not, the release scope: commit the accepted fingerprint 0b8554d0… as one application commit (+ optional docs commit) on codex/radar-selected-price-charts, fast-forward push to origin/main, routine wrapper deployment with both flags OFF, bounded smoke; and separately whether to activate `RADAR_SELECTED_PRICE_CHARTS_ENABLED=on` (stored fallback) afterwards. Yahoo activation is not requested and stays blocked on the usage-condition ruling.

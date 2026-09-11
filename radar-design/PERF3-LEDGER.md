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

`git log` is the truth if this table and it disagree.

| Task | Status | Commits | Review |
| --- | --- | --- | --- |
| 1 key + namespace | **complete** | `a5017e7`, `20429d0`, `a188bb3` | approved after two fix rounds |
| 2 tables, migration, store | **complete** | `0eba6a4`, `c2d0ca9`, `c199d06` | approved after one fix round; carried items closed in `c199d06` |
| 3 producer | **complete** | `fd810c1`, `55f0d7f` (+ `6752492` for its carried items) | approved after one fix round |
| 4 read path, flag, API | **complete** | `9097621`, `6752492` | approved after one fix round |
| 5 old board client | implemented; fix committed, **not yet re-reviewed** | `0ed59e2`, `2b90885` | review of `0ed59e2`: needs fixes (I1–I3) |
| 6 hub client | open | | |
| 7 parity | open | | |
| 8 scale verification + browser | open | | |
| 9 suites + release package | open | | |
| whole-branch review | open | | |

## Databases, as they now stand

| Database | Stamp | How it got there |
| --- | --- | --- |
| `personal_apps_radar_perf3` (tests) | `b7e3f9c1a2d4` | te1 clone at `a7c31f0b52d4`, then `flask db upgrade` in Task 2 Step 7. The migration tests downgrade and re-upgrade in-process and leave it at the head. |
| `personal_apps_radar_perf3_scale` (timings) | `b7e3f9c1a2d4` | perf1 dump, minus the spike's `radar_board_results` and the `perf_numbers`/`perf_write_numbers` helpers. The dump carried PERF1's stamp `c4e17b90d3f2`. The physical schema was checked against `a7c31f0b52d4` first: the six projection columns are on `radar_ingest_runs`, and `ix_radar_bucket_sources_agg` is absent. The stamp was then reset **on this clone only**, and the clone was upgraded through a launcher that stops `app.py`'s `load_dotenv(override=True)` from re-pointing it at the test database. Result: 9,269,184 `radar_bucket_sources` rows; indexes `PRIMARY`, `ix_radar_bucket_sources_start`, `ix_radar_bucket_sources_coverage`; buffer pool 2560 MB. |
| `personal_apps_radar_perf1` | `c4e17b90d3f2` | **not modified**; still PERF1's evidence fixture. |

**The environment-variable trap.** `app.py` calls `load_dotenv(override=True)`,
so a `PERSONAL_DB_NAME` set in a script's environment is silently replaced by
the worktree `.env`'s value, and `find_dotenv()` asserts when a script comes
from stdin. The first scale-migration attempt died on the second and would
have hit the first. The plan's Task 8 carries an amendment naming the launcher
every scale script must use.

**The fixtures' clocks.** Read 2026-09-11 00:57 UTC, read-only:

| Database | `radar_bucket_sources` span | Other spans |
| --- | --- | --- |
| `personal_apps_radar_perf3` | 2026-08-21 09:15 → 2026-09-01 18:15 (1,103,010 rows) | quotes end 2026-09-01; 0 posts |
| `personal_apps_radar_perf3_scale` | 2026-08-18 13:00 → 2026-09-10 12:00 (9,269,184 rows, monthly partitions) | quotes 2026-09-09 13:00 → 09-10 12:00; mention events from 2026-09-08 13:00; 0 posts |

Every board query is bounded above by `now`, so a fixture that ends in the
past gives real-clock boards a partial or empty window: the scale fixture's
24h window held 201,504 rows at that moment, against about 405,000 for a full
day. Task 8 therefore starts by extending the scale fixture forward by whole
days, which the `now` bound makes safe, and runs everything there, the
browser included. Neither fixture has posts, so tone and the `lean` sort are
not exercised at scale.

## MariaDB 10.11.14 rehearsal server

A portable mariadb.org build already on this machine from P1, started with a
fresh datadir in the session scratchpad. It is not installed, registered or a
service, and MySQL80 is untouched.

```
B=C:/Users/michi/AppData/Local/Temp/claude/c--Users-michi-Desktop-CodingStuff/1067a3f3-80ea-40f8-86f1-2098692a7340/scratchpad/mariadb/mariadb-10.11.14-winx64/bin
D=<session scratchpad>/mariadb-data/data
"$B/mariadb-install-db.exe" --datadir="$D" --password=""
"$B/mariadbd.exe" --datadir="$D" --port=3399 --console
cd personal_apps && PYTHONPATH=. py -3.12 scratchpad/perf3/rehearse_board_results_mariadb.py
```

| Run | Commit | Checks |
| --- | --- | --- |
| first | `0eba6a4` | 53, all passed |
| after the namespace fixes | `c2d0ca9` | 54, all passed (check 47: reader traffic keeps a generation alive) |
| after `GREATEST` on every `last_seen_at` writer | `c199d06` | 54, all passed |

The server process stopped with the session break below. It is restarted only
when a store or migration change needs the rehearsal again.

## Session break, 2026-09-11

Claude Code's OAuth token expired mid-run. The API answered 401, the client
logged the owner out, and the session restarted, now on Opus 5 (it had been
Fable 5.1). Every commit through `6752492` survived. Two things did not:

- The first Task 5 fix agent died mid-edit. Its uncommitted edits in six
  `static/radar/` files were kept, measured at `tsc` clean and 181 of 182
  radar tests passing (the failure was its own new I3 test), backed up to the
  session scratchpad as `perf3/task5-fix-partial-20260911-024801.patch`, and
  handed to a second fixer to finish.
- The portable MariaDB process.

## Findings and rulings

Every reviewer finding, its severity and its disposition. Minor findings are
listed where they were fixed or carried; nothing below was dismissed without a
reason.

### Task 1 — key and namespace

| Finding | Severity | Disposition |
| --- | --- | --- |
| `canonical`/`query_from_json` validated with bare `assert`, which `python -O` strips; `round_trips` depended on catching `AssertionError` | Important (plan-mandated wording) | `BadKey(ValueError)` raised instead; `20429d0` |
| relative `gitdir:`, CRLF ref files, and `round_trips`' second check untested | Minor ×3 | tests added; `20429d0` |
| **regression introduced by that fix**: `round_trips` narrowed to `BadKey` while `canonical` still raised `TypeError` on an unhashable stored source | Important | `query_from_json` validates every field's shape, `canonical` rejects non-string entries; `a188bb3` |
| a hand-built `Query` with a non-iterable `sources` still raises `TypeError` from `canonical` | Minor | carried; unreachable through `round_trips`, predates the fix |
| the brief said "two levels above `personal_apps/`" and also "the directory containing `.git`" | ambiguity | the latter; `parents[3]` verified against this worktree's real gitfile |

### Task 2 — tables, migration, store

| Finding | Severity | Disposition |
| --- | --- | --- |
| `ensure_namespace`'s `ON DUPLICATE KEY UPDATE` never wrote `producer_revision` onto a control row a reader adopted first, so it stayed NULL for the generation's life | Important | the update arm sets revision and version; `c2d0ca9` |
| readers never refreshed `last_seen_at`, so a namespace with live readers and a dead producer could be retired | Minor | `GREATEST(last_seen_at, :now)` inside the admission lock; `c2d0ca9` |
| `retire_namespaces` X-locked every control row it scanned, live generations' included | Minor | unlocked candidate scan, then lock-recheck-delete one generation at a time; `c2d0ca9` |
| `rowcount` read after the transaction block; `ConfigError` branch, warm+failed row, migration-vs-model agreement untested; demand ordering; duplicated test helper | Minor ×6 | fixed; `c2d0ca9` |
| `ensure_namespace`/`heartbeat` assigned `last_seen_at` plainly while readers used `GREATEST`; the retirement loop never ran under the transaction-depth listener; one inaccurate comment | Minor ×3 | fixed; `c199d06` |
| every admission, polls included, now writes the namespace row | Minor | **carried to Task 8**: measure it; gate it to minute resolution if it shows |
| **found by Task 3's implementer**: the migration test passed `sa.func.now(6)` as a bound VALUE and left `sql_mode=''` on a pooled connection, so the strict long-key case had never inserted under strict mode | Important | real datetime, a dedicated connection per mode with a restoring `finally`, `@@session.sql_mode` asserted on that connection; `c199d06`, made hermetic with a literal `STRICT_TRANS_TABLES` in `6752492` |
| deviation: the rehearsal stamps `b3d9e1f5a274` and upgrades through `a7c31f0b52d4` rather than stamping the latter | accepted | a stamped-only schema lacks `radar_board_observations`, so the "neighbour intact after downgrade" check would be vacuous |

### Task 3 — producer

| Finding | Severity | Disposition |
| --- | --- | --- |
| the sustained-run fairness test's warm bound was satisfied by the run's own arithmetic (20 s of simulated time against a 20 s bound) | Important | 80 ticks and `count('warm') >= 4`; shown to fail with rotation disabled; `55f0d7f` |
| a failing tick retried every 0.5 s with a traceback, forever | Important | capped exponential backoff, traceback on the first failure only; `55f0d7f`. The exponent itself was capped after the re-review found an `OverflowError` at 1,024 consecutive failures, about 8.5 h; `6752492` |
| nothing proved `build_blob` produces the request path's payload | Important (plan-mandated duplication) | an equivalence test over a warm query and `?sources=reddit:wallstreetbets`, the only shape where the source rooting is not the identity; `55f0d7f` |
| duplicate `utcnow`, `depth.peak` not load-bearing, `KeyMismatch` recorded twice, post-build failures marking a built key failed, warm-hash time-invariance, owner truncation, negative durations, wall-clock housekeeping | Minor ×8 | fixed; `55f0d7f` |
| a `publish` that raises leaves the row `building`, holding one of the 32 queue slots until the lease expires | Minor | **carried to the release runbook** |
| nine deviations from the brief (a clock callable for `build_blob`, `serve_once(revision=)`, the idle wait in `run`, a module-level `readiness`, the derived-count check, compressed `payload_bytes`, a per-position demand bound, a `session_transaction()` helper, a housekeeping boundary test) | accepted | each with its reason in the review |
| `board_producer.py`: one blank line between `_backoff` and `class Loop` | Minor (style) | carried |

### Task 4 — read path, flag, API

| Finding | Severity | Disposition |
| --- | --- | --- |
| the pending shell hardcoded `failed: false`, so a key whose last build failed did not say so while waiting | Important (plan-mandated contract) | `failed` read from the pre-admit row; `6752492` |
| the flag-off test left a fake board in the process-global `board_cache` | Important | isolated per test; `6752492` |
| two copies of the per-account block; no shell-vs-board equivalence; negative age unclamped; `warm_total` read the configured cap; `building` rows untested; the tripwire missed the BadQuery fallback; `ops_collected_at` via `setdefault`; `poll=true` undocumented; envelope completeness unasserted | Minor ×9 | fixed; `6752492` |
| the archive would have taken on 13 delivery fields | concern, ruled | `observations.EXCLUDED` widened by the envelope keys; `SCHEMA_VERSION` stays 1; a test pins that `generated_at` survives and no envelope key does |
| the read path writes `producer_revision` through `ensure_namespace` | concern, ruled | kept: a namespace IS a revision, so reader and producer write the same value; docstring reworded |
| `/api/ops` catches only `ProgrammingError` (table missing), not an outage | concern, ruled | kept: the ops page reads the database earlier anyway, so an outage fails it there, and catching it here would only mislabel an outage as a missing table |
| server facts the client review asked for | answered | a parked answer is `{pending: true, busy: false, failed: true, rows: null}`; every pending/busy shell carries `venue_counts: {any: 0, multi: 0}` and `segment_counts: {}` |

### Task 5 — old board client (fix committed, re-review pending)

Review of `0ed59e2`: **needs fixes.**

| Finding | Severity | Disposition |
| --- | --- | --- |
| I1 `Poller.resume()` during an in-flight poll starts a second permanent chain | Important | fixed in `2b90885`, unreviewed |
| I2 a poll for the old selection can repaint the old rows under the new selection's controls inside the 250 ms debounce | Important (ruling) | fixed in `2b90885`, unreviewed |
| I3 `fresh_seconds` is read by nothing, so a board that ages past it on the client clock is shown unmarked until hard expiry | Important (ruling) | fixed in `2b90885` for shared boards only, see below; unreviewed |
| I4 the hub renders "nothing cleared" over a pending shell | Important | **Task 6's**; its dispatch carries it |
| M1–M8, M10, M12, M13 | Minor | fixed in `2b90885`, unreviewed; M9 (`isReady` unused until Task 6) and M11 (a render-time ref write, idempotent) dropped with those reasons |
| copy: the brief said `humanAge(age)` but its acceptance strings read "Calculated 0s ago"/"3m ago" | ambiguity | the acceptance strings win; a local `boardAge()` hands over to `humanAge` past 90 minutes |

**What the second fixer found and decided (`2b90885`, not yet re-reviewed).**
It finished the edits the first fixer left when the session broke. It reports
245 of 245 in the listed suites, 584 of 584 in the whole radar suite, 403 of
403 in the root suite, `tsc` exit 0 and a passing build, with no act()
warnings or unhandled rejections. For each finding the partial edits had
already addressed, it showed the test has teeth by reverting the fix and
watching the test fail: 21 such checks, files restored byte for byte. Three
things for the re-review to judge:

1. The partial edits carried two regressions, both now fixed and tested. A
   poll that came due during a slow Retry aborted it and left the controls
   stuck busy with pointer events off. The expiry refetch restarted polling
   in a hidden tab.
2. **I3 was narrowed on purpose.** Only shared-path boards count as stale by
   the page's own clock and poll for a refresh. On the flag-off direct path,
   which is production until the flag flips, a poll would rebuild a board
   synchronously every few seconds per open tab, and "refreshing" would be a
   claim no producer backs. Widening it is one condition in `untilStale`.
   The ruling did not decide this case explicitly, so the re-review should.
3. After a board passes its fresh bound, the first poll goes out after 1 s
   and then every 5 s. That first poll is what makes the server queue the
   refresh.

**Paused** on 2026-09-11 at the owner's request, after `2b90885`, with this
ledger and the handoff committed. No agent is running.

## Measurements

(appended by Task 8)

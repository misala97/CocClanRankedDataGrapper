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
| 5 old board client | **complete** | `0ed59e2`, `2b90885`, `17128b8`, `52af950`, `27738b2` | approved after five fix rounds; minors carried |
| 6 hub client | **complete** | `103b8ba`, `d429378` | approved after one fix round; minors carried |
| 7 parity | **complete** | `29cc2ac` | approved first time; minors carried |
| 8 scale verification + browser | reviewed: evidence honest; one Important fixed in the ledger; an optional ready series under load awaits the owner | `9fa42aa`, `6ecba5a` | one Important (ledger), eight Minor |
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

## Facts settled from source, not assumed

**Gunicorn and `--threads`.** The PERF2 ledger said `--threads` is ignored by
the sync worker class, and Codex's ruling asked for the version's own source
to settle that before it is repeated. For the version installed here it is
wrong. Gunicorn 26.2.0's `Config.worker_class` (`gunicorn/config.py:122-128`)
substitutes `gunicorn.workers.gthread.ThreadWorker` whenever the configured
class is `sync` and `threads > 1`; `worker_class_str` (`config.py:110-119`)
reports `gthread` in the same case; and the `threads` setting's own
documentation (`config.py:791-795`) says the gthread worker "will be used
instead". So on 26.2.0, `--threads 2` alone changes the worker model. It is
not a silent no-op, and adding `--worker-class gthread` beside it is redundant
rather than required. The target's gunicorn version has never been read, so
this settles the statement for 26.2.0 only. The threading change itself stays
deferred, as the ruling decided.

**The browser.** python-playwright 1.61 launches headless Chromium
149.0.7827.55 on this machine: a 390×844 page, `document.visibilityState`
readable, a screenshot written, in 3.5 s. Task 8's browser runs need no
setup.

**systemd unit escaping, from systemd v255's own documentation.** Ubuntu
24.04 ships systemd 255. The text was fetched from the systemd repository at
tag `v255` (`man/systemd.service.xml`, `man/standard-specifiers.xml`), because
freedesktop.org refuses automated fetches. `ExecStart=` "accepts % specifiers
as described in systemd.unit(5)", and the specifier table says "Use %% in
place of % to specify a single percent sign". The same section says "To pass a
literal dollar sign, use $$", and a `:` prefix on the executable suppresses
environment-variable substitution but not specifiers. So gunicorn's access-log
format, `%(t)s %(m)s %(U)s %(s)s %(B)s %(L)s`, has to be written inside
`ExecStart=` with every `%` doubled, and quoted as one argument because it
contains spaces. PERF2's paste-ready delta doubled none of them.

**journald's defaults, same source** (`man/journald.conf.xml` at `v255`).
`Storage=` defaults to `auto`, which is persistent only when
`/var/log/journal` exists. `SystemMaxUse=` defaults to 10% of the file system
and `SystemKeepFree=` to 15%, each capped at 4G. `MaxRetentionSec=` defaults to
0, which turns time-based deletion off. Rate limiting is per service, 10,000
messages per 30 s by default, scaled up by free disk space. None of the
target's own journald settings have been read.

**The build revision file, corrected (2026-09-11).** `board_namespace.build_revision()` reads a `BUILD_REVISION` file at the repository root (`/root/coc-stats` on the VPS), not in `personal_apps/` as the plan said. The VPS checkout is a git repository, so the git fallback already yields the deployed commit, and a file written once would outrank git and pin an old revision across deploys. The plan carries the correction as an amendment, and the release package recommends writing no file.

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

### Task 5 — old board client (complete, approved after five fix rounds)

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

**Re-review of `2b90885`, 2026-09-11: needs fixes.** Resolved: I1, I2,
M1–M8, M10, M12, M13, and both regressions the interrupted edits had carried.
**I3 is half done, and the reviewer ruled on the fixer's narrowing.** Not
polling a flag-off board is compliant: nothing stands behind it to refresh,
and a poll would only trigger a synchronous build. Not MARKING it stale is not
compliant: ruling §5 says a board between the fresh bound and hard expiry may
remain visible "ONLY as stale", with no exception by path, and flag-off is
production until the flag flips. Required: every board with rows is marked
stale past `fresh_seconds` on the page's clock; shared boards keep the
automatic wait and "refreshing"; flag-off boards say "not refreshed" and offer
Retry, with no automatic request at the bound. New minors: a hidden flag-off
tab refetches about every ten minutes; a failed expiry refetch leaves
"recalculating" on screen with nothing recalculating; a poll can undo a row
the reader just clicked; an aborted poll zeroes the server's retry floor
once; one misleading comment. Round 3 waits for the Task 7 implementer, to
keep one implementation worker at a time. The same ruling binds the hub in
Task 6.

**Round 3, `17128b8`, and its re-review.** Round 3 resolved all six items it
was given. Every board with rows is now marked stale past `fresh_seconds` on
the page's clock: shared boards say "refreshing" and poll, flag-off boards say
"not refreshed" and offer Retry without any automatic request. A hidden
flag-off tab defers its expiry refetch to the next visible transition, a
failed refetch no longer claims "recalculating", a poll keeps the reader's
ticker, and an aborted poll no longer drops the server's retry floor. The
re-review found one new Important: the "not refreshed" Retry had no guard
against a request already out, so repeated clicks aborted and resent, and on
the flag-off path each resend starts a synchronous build the client's abort
cannot cancel. Minor: non-poll answers still restored the ticker they were
sent with; the expired-and-failed state showed two Retry buttons that behaved
differently; two comments were wrong; the age line should pick its word with
`refreshDue`. All of these went to round 4.

**The flaky test, measured.** `BoardPage.test.tsx` "the controls > coalesces
a burst of control changes into one request" failed intermittently in the
whole radar suite. Six whole-suite runs on each tree, alternating, in a
temporary worktree of the deployed baseline with its own `npm ci`:

| Tree | Clean runs | Failures of that test |
| --- | --- | --- |
| deployed baseline `4221196` (532 tests) | 6 of 6 | 0 |
| this branch at `17128b8` (596 tests) | 3 of 6 | 3 |

Each failure was a request sent mid-burst with an intermediate selection:
`expected '/radar/api/board?sources=bluesky%2Creddit&window=4&segment=&market=us'
to contain 'sources=bluesky&'`. The test races the real 250 ms debounce
against real-time simulated clicks, so it was timing-sensitive before this
branch; the re-review traced the extra full-page render per toggle that round
2 added inside that window, when it moved the poll-question bump into the
selection effect. The measurement settles the size: from never to half the
time. Round 4 makes the test deterministic with fake timers, keeps its three
assertions, audits the file for other races against the debounce, and must
show ten consecutive clean whole-suite runs. The temporary worktree was
removed; its cleanup first failed on a Windows path-length limit inside
`node_modules` and was finished with a long-path delete after checking the
tree held no links into real data.

**Round 4, `52af950`, and its re-review.** Round 4 resolved all seven items:
every Retry joins the request already out, every answer reads the reader's
current ticker, the expired-and-failed state shows one Retry, two comments are
corrected, the age line picks its word with `refreshDue`, and the coalescing
test runs on the fake clock with its three assertions kept and one added. It
then ran clean in ten of ten whole-suite runs (600 tests). A second test that
had never been checking the answer it waited for was converted too.

**The watch refetch, confirmed and blocking.** The fixer reported, and the
re-review traced from the code, that the refetch after a star uses the
selection captured when the star was clicked. Change a filter while the
mark is being saved, and that refetch, holding the newest request number,
passes the generation check, aborts the new selection's request, paints the
OLD board under the NEW controls with a fresh stamp, and rewrites the address
bar to the old query. On the flag-off path nothing asks again until Retry or
the ten-minute expiry. It predates this branch, but it defeats exactly the
guarantee this slice added ("never under the new selection's labels"), so it
is fixed here. Round 5: read the current selection when the queue empties,
wait for the reader's own request instead of aborting it, and skip the
refetch while a control change is inside its debounce. Two minors ride along:
a Retry must select the top row for a reader with no ticker, and must treat a
failed non-market filter change as that change would have; and the banner
must not claim "Showing the last board that loaded" over a waiting shell,
where no board exists. Round 5 waits for the Task 6 implementer, to keep one
implementation worker at a time.

**Stopping rule, agreed with the owner on 2026-09-11.** Round 5 is the last automatic round for Task 5. Its re-review may block only on a critical or important finding that round 5 itself introduced, or on a direct violation of the PERF2 ruling. Every other finding is carried to the whole-branch review. If a blocker remains after round 5, work stops and the owner decides, with a recommendation such as simplifying the old board request handling rather than patching it again.

**Round 5, `27738b2`, approved under the stopping rule.** The first round-5
fixer died on the API session limit; a second verified its partial edits by
mutation (14 of 14 failing their tests), finished, and committed both. The
star's refetch now reads the selection on screen when it sends, waits for the
reader's own request instead of aborting it, and is skipped while a control
change is still settling; a Retry gives a reader with no ticker the top row
and repeats a failed filter change as it would have succeeded; the banner no
longer claims a previous board over a waiting shell; and a second failed poll
in a row says so inside the waiting line. Whole radar suite 655 of 655 in five
of five runs, root 403, typecheck and build clean. The re-review found nothing
that round 5 introduced above Minor and no ruling violation, so Task 5 is
complete.

**Carried from Task 5 to the whole-branch review:**

- a poll landing after a failed non-market filter change still keeps a ticker the new board does not list;
- a Retry or the expiry refetch within 250 ms of a control change sends one extra request (one extra synchronous build on flag-off); gating both on `settling` fixes it;
- a busy or delayed Waiting Retry can sit beside the banner's Retry;
- the star's refetch has no hidden-tab gate, so it can send one request for the correct selection from a hidden tab;
- a parked board whose polls fail now says only "Radar is still retrying." because its branch never receives the failure note;
- when the reader's own request fails (including the 8 s timeout on a slow flag-off build) the star's refetch re-asks at once;
- untested but correct by construction: the `settling` reset path, the star's refetch while hidden, poll failures over a parked board.

### Task 6 — hub client (complete, approved after one fix round)

`103b8ba`. The whole radar suite ran clean three times at 641 tests, the root
suite at 403, and the typecheck and build pass; on the old code the new tests
failed 37 of 45. The reviewer found the waiting machinery careful: requests
the page drives itself never double up, every Retry joins a request already
out with `cancelRefetch: false`, a key change abandons the old answer, the
placeholder board is replaced by Loading, and the compile-only null guards are
gone. The pages taking `BoardPayload | null` plus a stand-in, instead of
`ReadyBoard`, was accepted, because it keeps Human chatter's filters usable
while waiting.

| Finding | Severity | Disposition |
| --- | --- | --- |
| the flag-off hub no longer re-reads every 60 s or on returning to the tab; the implementer read the fresh-bound ruling as forbidding it, but that ruling only forbids an automatic request AT or past the bound, and flag-off is meant to behave as it always has | Important | fix: one visible-only read at arrival + 60 s, armed only while inside the fresh bound |
| a pending or busy shell whose polls fail still says "Calculating", and after 30 s gives the wrong diagnosis | Important | fix: show the reason and one Retry, keep polling |
| a timed-out or rate-limited board request is auto-retried twice, and on flag-off each retry starts another synchronous build | Important (pre-existing, inside this task's request ruling) | fix: never auto-retry `timeout` or `busy` |
| top bar shows the previous market while placeholder data is on screen; two `poll=1` edge cases; an owed expiry refetch lost on a failed request; the mark's cache update clears the error; hints name controls a page lacks; a copied age helper; one vacuous test; a pre-existing stuck `marking` flag | Minor ×8 | fix in the same round where small; the last one may be carried |

The same stopping rule as Task 5 applies: this is Task 6's one fix round; its
re-review may block only on something the round itself broke or on a direct
violation of the PERF2 ruling, and anything else is carried to the
whole-branch review.

**The fix round, `d429378`, approved under the stopping rule.** All eleven
findings were fixed, including the pre-existing stuck `marking` flag, which
took a few lines. The flag-off hub again re-reads its board once, a minute
after it arrives, while visible and only inside the fresh bound; a failing
wait shows its reason and one Retry and keeps polling; a timed-out or
rate-limited request is never resent; and `poll=1` now follows the old
board's single rule. Beyond the list, the fixer turned off react-query's
refetch on reconnect, which was another way a request could go out past the
bound. Radar suite 681 of 681 in three runs in a row, root 403, typecheck and
build clean. The re-review traced every finding through the code and through
query-core where it mattered, ran nothing because a timing measurement was
running, and found nothing the round introduced above Minor and no ruling
violation.

**Carried from Task 6 to the whole-branch review:**

- the minute's read, if sent while the browser reports offline, is paused and goes out on reconnect without re-checking the fresh bound;
- a star gives the board a new object with the same arrival time, which can re-arm the minute's read and send a second read for one arrival after a failed read and a failed mark refetch;
- the failure count is not reset on a selection change, so returning to a selection shows its old "Still trying." until its first answer lands;
- the reader-asks marker has no try/finally, so a mark refetch paused offline could go out as `poll=1`;
- pre-existing: the reader's own asks are still resent twice on server or network errors, and on a flag-off board past its bound each resend is another synchronous build;
- the reader's own failed Retry over a shell is announced as a polite status, where the old board uses an alert;
- with reconnect refetching off, a first read that failed while the browser still reported online no longer recovers by itself on reconnect.

**Second interruption, 2026-09-11.** The API session limit stopped the Task 5
round-5 fixer mid-run. Its uncommitted edits in three `static/radar/src/board`
files measured `tsc` clean and 220 of 220 old-board tests passing, with no
report; they were backed up to the session scratchpad as
`perf3/round5-partial-20260911-171255.patch` and handed to a continuation
fixer, told to verify each finding against them before finishing.

### Task 8 — production-scale verification (reviewed; the one Important fixed in the ledger)

Delivered as two dispatches, so a session limit could cost less: 8a measured
(`9fa42aa`, eleven scripts and the `## Measurements` section), 8b checked both
boards in a real browser (`6ecba5a`). Their tables are under Measurements; the
review follows. What the evidence surfaces for Codex:

| Finding | Evidence | Status |
| --- | --- | --- |
| **the 120 s fresh bound fails under representative write contention** | worst warm age 142.8 s, about 7% of warm samples stale; the 600 s hard expiry holds; the write itself was not slowed | a failed criterion, returned as the ruling requires rather than hidden with a larger limit. Cause: the refresh target and the fresh bound are both 120 s, so any build time or delay crosses the bound. Refreshing earlier would fix it at more producer duty; that is Codex's decision |
| after an empty store the eight warm boards rebuild in `key_hash` order, not in the order readers ask | a reader of one of them waited up to about 44 s (median 22.8 s, p95 42.8 s) | open; ordering warm work by waiting readers first is the obvious remedy |
| a restarted web worker's first read misses the 500 ms ready target | p95 769 ms (imports and pool set-up), against 70–73 ms p95 for ready reads | reported apart, as the ruling asks |
| the cold goal stays unmet | build-to-usable median about 5.8 s; 0 of 60 within 2 s | UNMET, preserved |
| **the core win holds** | a non-Radar request beside two cold boards, in the two-process MODEL (not gunicorn): worst 78.7 ms with the flag on, 9,522 ms with it off | the web workers no longer build |
| the old board's detail panel takes focus when a board arrives after a wait | on a 390×844 phone it scrolls the reader about 4,219 px away from the list; new with the pending path | carried to the whole-branch review |
| the Discover tab asks for a board spelled differently from the warm default | a cold second key with the same rows | open: warm that spelling too, or have the client send the default spelling |
| the old board's view tabs read "0" while a board is pending | the shell carries empty `segment_counts` | carried (Minor) |

**The review of 8a and 8b.** The reviewer read all twelve scripts in full
and checked ten named risks. The evidence is honest and correctly guarded:
the subreddit patch and its 100% coverage check run before every
measurement; every process in a run resolved one namespace and a mismatch
aborts the run; a pending answer structurally cannot enter a board
statistic; the alignment kept unique keys and reconciles to 9,269,184 rows;
no script can reach another database; the failed 120 s criterion and the
unmet cold goal are returned plainly with correct causes; every browser
check asserts what the ledger says, and the in-page hidden emulation reaches
both clients' real visibility code. **One Important, fixed here in the
ledger:** the ready verdict was an idle-producer figure presented without
that condition; reads issued as a build starts reached p95 492 ms. The
verdict row and both prose passages now say so. Measuring a ready series
under load is new work, so it waits for the owner's go.

**Carried from Task 8 (Minor):** the preflight blocks of most runs live only
in uncommitted logs; worker memory under contention was not reported,
though `two_workers_perf3.py` records the peaks; the empty-store sample was
measured with warm processes, so a deploy adds a cold producer (prewarm
60.7 s); the read at publication is unchecked and shares a worker; the old
board's detail pane says "Nothing on the board to look at." while a board is
pending, which check 1 did not look for; two screenshot pairs are
byte-identical renders presented as separate evidence; the first paint is
not asserted to be the waiting copy; the write restore has no checksum; and
two scripts hard-code the revision default and the 120/600 s limits.

**Open decisions for Codex surfaced by the evidence:**

1. **The fresh bound.** Under (f)'s load the producer spent about 52% on
   on-demand builds and 32% on warm work. The reviewer's arithmetic, not a
   measurement: a 100 s refresh target raises the warm share to about 42%,
   about 94% in total, so lowering the refresh target alone likely makes
   lateness worse. Headroom points to a second producer, cheaper builds, or
   less on-demand work.
2. **Every deploy is an empty store.** The namespace is the build revision,
   so each release puts readers into the empty-store state with a cold
   producer on top. The readiness gate covers the first rollout only; decide
   whether routine deploys wait for the new namespace's `--readiness` before
   the web workers switch, and whether warm keys a reader is waiting for
   should jump the `key_hash` order.
3. **The ready target in steady state:** must p95 <= 500 ms hold while the
   producer is building?
4. **A restarted worker's first read** (p95 769 ms): accept it as a
   once-per-worker cost, warm the caches on boot, or narrow the target.
5. **The hub has no debounce:** browser check 2 sent one request per control
   change, and every cold intermediate became an admitted build nobody sees.
   Together with the cold Discover duplicate, this is a client and
   key-contract decision.
6. **The per-account rule at 25 marks** (150 ms median): decide whether it
   must hold beside a building producer; measured with the producer stopped,
   p95 reached 150-165 ms.

### Task 7 — parity (approved)

`29cc2ac`, one test file, no application code. 63 cases pass in 29 s; with
three neighbour suites, 175 of 175 in both orders and no rows left behind.
Deliberately breaking the producer made 49 cases fail when the sort was
dropped and 5 when segments were deduplicated the PERF2 way. The reviewer
checked seven named risks against the application code and found no critical
or important issue: the digest strips only the envelope keys; the fixture's
adversarial properties are asserted, not assumed; the stored side is an
independent build through admit, claim, `round_trips`, `build_blob` and
publish, read back at the same instant; cleanup deletes the fixture's exact
tickers, so real listings sharing its prefix are safe; the long key stores
1,044 characters and round-trips; the source and segment proofs compare both
the key and the payload; and the omitted-market case pins which market each
clock resolves to. The implementer's three concerns were judged sound.

| Finding | Severity | Disposition |
| --- | --- | --- |
| the membership self-check asserts less than was measured; divergence's top 50 equals the default ranking's, so its matrix cases cannot see a limit-before-sort regression | Minor (partly plan-mandated) | carried: assert every key except divergence moves the cut, and say why divergence cannot |
| the pre-split score check sums two buckets of the same count, so one wrong reading also gives the expected total | Minor | carried: give the root bucket a distinct count |
| namespaces left by an aborted run are never swept | Minor | carried |
| `== 37` ties the long-key test to today's subreddit count | Minor | carried: compare with `api.MAX_SOURCES` |
| `default=str` in the digest could hide a wire-format difference | Minor (plan-mandated) | carried; low risk, since `serialize` formats every instant |
| the failing-account test sets `TESTING` without restoring it | Minor | carried |
| **every new PERF3 suite pins the database `personal_apps_radar_perf3` and skips on any other**, so after a merge they would skip silently on the dev database and anywhere else | Minor here, branch-wide | **carried to the whole-branch review**, which must decide what those guards should be |

## Measurements

Task 8a: Step 0 (align the fixture), Steps 1-3 and the ledger half of Step 5.
The browser half (Step 4) is a separate dispatch. Every number below was
taken on `personal_apps_radar_perf3_scale` -- MySQL 8.0.46 on Windows, buffer
pool 2560 MB, the deployed three `radar_bucket_sources` indexes, stamp
`b7e3f9c1a2d4` -- with nothing else running. **The target is MariaDB
10.11.14: the mechanisms transfer, the seconds do not.** The limits the plan
asks to be stated beside every number are stated once here and hold for every
table in this section:

- synthetic perf1-derived fixture, clock-aligned (below); hourly buckets,
  16,792 rows an hour, 403,008 in any 24-hour window;
- no `radar_posts`, so tone and the `lean` sort do no real work: every lean
  timing is a lower bound;
- the source names are the fixture's own -- three real subreddits
  (`pennystocks`, `shortsqueeze`, `wallstreetbets`) and the placeholders
  `reddit:sub03`..`sub32`, 33 in all -- spelled through the `REDDIT_SUBS`
  patch below (the dispatch's "sub00..sub32" is three names off; the patch
  reads the fixture, so it is right either way);
- one fixture `app_user`; every watch-profile account was created by a script
  and deleted afterwards;
- quotes exist for the US market only (`us`/`XNAS`), so DE boards carry no
  prices;
- "MODEL" means two OS processes with one request thread each serving the real
  WSGI app, never gunicorn, which does not run on Windows.

### What the numbers say

| criterion (PERF2 ruling, Task 8 brief) | measured | verdict |
| --- | --- | --- |
| ready read, p95 <= 500 ms | `read_payload` p95 70-73 ms; over HTTP p95 118-140 ms; 25 watched tickers: whole read p95 185 ms -- all with the producer idle | **met with the producer idle**; reads issued as a build starts reached p95 492 ms, max 623 ms, and no ready series was taken under load |
| ready read, first request of a freshly started worker | a board 20 of 20, but p95 769 ms (median 666 ms) | **not met** -- the restart cost |
| first missing result within 2 s (kept as an UNMET goal) | empty store: median 22.8 s, p95 42.8 s; cold on-demand: median 5.8-8.4 s, p95 8.2-9.4 s; 0 of 60 within 2 s | **UNMET**, as ruled; the build alone is about 5 s |
| the eight warm keys within the 120 s fresh bound, with headroom, under contention | age when replaced median 126 s, p95 148 s, max 159 s (f); p95 140 s, max 143 s (g); about 7% of warm samples stale | **FAILED** |
| hard expiry 600 s | worst warm age 159 s | held |
| on-demand demand under that load | 60 of 60 served in (f) and in (g); median 8.3 / 8.9 s, p95 11.6 / 16.6 s | served |
| write side beside the producer | write_cost's UPDATE 5.63-5.75 s under the sweep, 6.03-6.30 s alone | no slowdown |
| a non-Radar request during two cold boards (MODEL) | flag ON: median 23.4 ms, worst 78.7 ms; flag OFF: median 307 ms, worst 9,522 ms | **the block is gone** with the flag on |
| memory | producer about 237 MB working set, peak 518 MB; each web-model worker 128-138 MB, peak 142 MB | recorded |
| decision 6: the control-row write per admission | +0.7-0.8 ms p95 alone, +1.7 ms with two admitters; the same 3,999 lock waits without it | **not triggered**, not gated |
| decision 7: the per-account half, 25 tickers | worst median 112.5 ms (run 2), 88.8 ms (run 1) | **not triggered**, no memo |

For the whole-branch review, each measured, none changed here:

1. **The 120 s fresh bound fails by construction and by load** -- refresh and
   fresh are both 120 s, so a warm board is always past its bound while its
   successor builds, and the on-demand turns stretch that to a p95 of
   140-148 s. The remedies (a refresh target below the fresh bound, or a
   second producer) are the owner's call.
2. **After an empty store, a reader waits for its board's place in the
   eight-key rebuild** -- up to about 44 s -- because warm claims are ordered
   by `key_hash` once every `as_of` is NULL, and nothing prefers the warm key
   somebody is waiting on. The pending retry hint ranks by `enqueued_at` and
   cannot see it either. The readiness gate keeps a planned rollout out of
   this state; the prewarm from empty took 60.7 s.
3. **A freshly started worker's first read with watches takes 0.6-0.8 s**,
   over the 500 ms target; every gunicorn worker a deploy restarts pays it
   once.
4. **The first 1h and first 4h builds in a producer process take 12-16 s**,
   two to five times a later build of the same window: the on-demand queue
   right after a producer restart backs up behind them.
5. **Warm build lines log `queue_wait=0.0` in steady state even when the board
   is late**: a due key is enqueued at the next tick and claimed in the same
   one. An operator must read lateness off the age, not the queue wait.
6. **A read issued the instant a board is published can take 0.5-0.6 s**
   while the producer's next build runs on the same database.

### The launcher

`app.py` calls `load_dotenv(override=True)`, so no environment variable can
select the database. Every script and subprocess goes through
`scratchpad/perf3/scale_env.py`:

1. loads the worktree `.env` by explicit path without override (credentials);
2. replaces `dotenv.load_dotenv` with a no-op before `app` is imported;
3. sets `PERSONAL_DB_NAME=personal_apps_radar_perf3_scale` and
   `RADAR_BUILD_REVISION=0b50952459fb009a710520f163bc92fcdfd968f6`, the fixed
   revision, so a commit during a run cannot move the namespace; every process
   printed namespace `1bc195083a27bc38545d0624b189ceba3740b9c680d67c18592bc0603d4e96a7`
   (fingerprint `3586f78497044d4d`) and the parents asserted agreement;
4. reads the fixture's DISTINCT `reddit:%` names with a direct pymysql query
   and sets `features.radar.config.REDDIT_SUBS` to them, bare, BEFORE `app` is
   imported, so `routes.api.MAX_SOURCES` (bound at import) agrees; it then
   checks every loaded `features.radar` module that binds the name;
5. after the import, asserts `db.engine.url.database` and that
   `expand_sources` of the warm set's own sources (`bluesky`, `fourchan`,
   `reddit`, from `board_producer.warm_queries`) covers 100% of the 24h
   window's rows, by comparing the two counts.

Subprocesses run as `<python 3.12> scratchpad/perf3/scale_env.py <script>
[args]` (runpy with the remaining argv). The interpreter is named directly
rather than through `py -3.12` -- the same interpreter,
`Python312\python.exe` 3.12.6 -- because `py.exe` is a launcher that runs
python.exe as its CHILD: killing it would orphan the real process, and its
working set is the launcher's own few megabytes. Children log to files, never
to an undrained pipe (PERF2's deadlock). Child log lines carry a UTC stamp;
the launcher's `logging.basicConfig` makes the targets' own call a no-op and
changes no message.

### Step 0: the fixture aligned with the wall clock

`scratchpad/perf3/align_scale_fixture.py`, run 2026-09-11 17:34 UTC. Each
table's most recent 24-hour slice was copied forward by +1, +2 and +3 days
(the smallest whole number that reaches now + 24 h), and the three oldest
24-hour spans were deleted from `radar_bucket_sources` only. Keys were read
from `information_schema` first: the bucket primary key carries the shifted
`bucket_start`; mention events and quotes let the server assign `id`; quotes'
unique key carries the shifted `fetched_at`; mention events' unique
`(source, external_id, ticker)` was kept unique by suffixing `external_id`
with `@YYYYMMDD` of the target day. Every datetime column of a copied row
moved by the same whole days. Each hour was one transaction; a target hour
already holding rows is skipped, so a re-run finishes an interrupted run
instead of duplicating it, and a run with the data already reaching
now + 24 h writes nothing. The three tables were ANALYZEd afterwards.

Three `reddit:zzarcbf` mention events dated 2027-01-04 are a test's residue.
They were left untouched and ignored when finding the end of the data, or that
table would have looked aligned already.

| table | rows before | rows after | span after | 24h rows | 12h rows |
| --- | --- | --- | --- | --- | --- |
| `radar_bucket_sources` | 9,269,184 | 9,269,184 | 2026-08-21 13:00 -> 2026-09-13 12:00 | 403,008 | 201,504 |
| `radar_mention_events` | 576,000 (+3 residue) | 1,440,000 (+3 residue) | 2026-09-08 13:00 -> 2026-09-13 12:59 | 288,000 | 144,000 |
| `radar_quotes` | 110,400 | 441,600 | 2026-09-09 13:00 -> 2026-09-13 12:00 | 110,400 | 55,200 |

Window rows at 2026-09-11 17:39 UTC; before the run, every window held 0.
Copy and trim took 37.9 s + 90.3 s (buckets), 146.0 s (mention events) and
38.9 s (quotes). One ops figure is affected in content, not in kind:
`market_data.py:944` counts quotes with only a lower bound, so the copied
future quotes inflate that one ops count. Every board query is bounded above
by `now`.

The preflight after alignment (`env_check.py`, printed by every script):

```
PREFLIGHT  align_scale_fixture: after
  database     personal_apps_radar_perf3_scale   engine 8.0.46   alembic b7e3f9c1a2d4
  buffer pool  2560 MB (target 2560 MB)
  indexes      deployed three
  rows         9,269,184 radar_bucket_sources; 0 radar_posts; 1 app_user; 0 radar_watch
  span         radar_bucket_sources   2026-08-21 13:00:00 -> 2026-09-13 12:00:00
  span         radar_mention_events   2026-09-08 13:00:00 -> 2026-09-13 12:59:00
  span         radar_quotes           2026-09-09 13:00:00 -> 2026-09-13 12:00:00
  residue      3 radar_mention_events rows dated more than 7 days ahead (test residue; untouched)
  window rows  24h 403,008   12h 201,504   at 2026-09-11 17:39:44 UTC
  reddit       REDDIT_SUBS patched: 33 names; warm-set coverage 403,008 of 403,008 = 100%
  namespace    1bc195083a27bc38545d0624b189ceba3740b9c680d67c18592bc0603d4e96a7  revision 0b50952459fb  fingerprint 3586f78497044d4d
  store        0 radar_board_results rows, 0 namespaces
```

### How each number was taken

One chain, 2026-09-11 17:59-18:56 UTC, every leg alone, nothing else running
on the machine's database: `align_scale_fixture.py` (a no-op re-check),
`admit_cost_perf3.py`, `measure_perf3.py --phase all`,
`profile_watch_perf3.py`, `two_workers_perf3.py`; then, alone, a second
`profile_watch_perf3.py` run (18:57-18:58) after its whole-read guard was
fixed (Step 3). Step 1's topology: the real
`run_radar_board_producer.py` (poll interval 0.5 s, the default) and two
web-model workers (`serve_perf3.py`, one request thread each, flag on) as
three subprocesses; the measuring process is every client and reads the
table directly. It truncated both tables first, so the run starts from an
empty store with a producer that has never built anything.

- **(a) ready.** `read_payload` in the measuring process with the account
  `perf3_m03` watching the US 24h board's top three tickers, n = 20 per
  window, the US All board (a warm key); then n = 20 of the same request over
  HTTP through the two workers in turn. One read per process and window was
  taken first, outside the n: the first board read with watched tickers in a
  process fills its coverage cache with a full scan, which is (c)'s cost, not
  a steady read. Ready and stale answers are counted apart; both are boards.
- **(b) empty store.** n = 20, the eight warm selections in turn. Each rep
  waits until every warm board is fresh and nothing is queued, TRUNCATEs both
  tables, and asks once: the answer must be `pending` with `rows: null` (it is
  timed, and it is NOT a board). The client then polls as the real one does
  (`poll=1`, at the server's `retry_after_ms`), while this process watches
  the row every 50 ms and, the moment a payload exists, issues one fresh read.
  Three parts are reported apart -- the pending answer, request to publish,
  and publish to a board in hand -- and two totals, both labelled with the
  UNMET 2 s goal: a read issued at publication, and the client's own poll.
  After TRUNCATE the producer rebuilds all eight warm keys in `key_hash`
  order (`as_of IS NULL` ties), so the requested board's place in that order
  decides its wait; the place is recorded per rep.
- **(c) restart.** n = 20: kill one worker (TerminateProcess), start it
  again, and when it listens ask for the US All 24h board; then ask again.
  Spawn-to-listening -- interpreter start, the launcher's DISTINCT-names
  query, the app import and the launcher's 24h coverage count -- is reported
  apart and is not part of the read. A deployed worker has no launcher, so
  that number overstates a real restart by those two queries.
- **(d) cold on-demand.** n = 20 each for `sort=lean` 24h and `limit=100` 24h
  (US, All): the key is deleted before each rep, so it is genuinely missing,
  and the producer runs throughout with whatever warm work is due -- the queue
  wait is the real one. Then n = 20 repeated reads of the limit=100 board.
- **(e) memory.** Windows working set (the local analogue of RSS), peak and
  private bytes, read from outside through `GetProcessMemoryInfo`: right after
  the prewarm, idle after (a), and after 100 more HTTP reads per worker.
- **(f) queue age.** Ten minutes: the warm keys on their 120 s refresh and one
  on-demand request every 10 s, alternating between the two workers, each a
  new cold key (60 distinct: windows 1/4/12/24 x US/DE x fifteen variants of
  sort, direction, limit, breadth and segment; none of them warm), each
  followed by a polling client until a board is in hand. The table is sampled
  every 5 s. The worst warm age is reported two ways: the sampled maximum, and
  the exact age each warm board had when its replacement was published
  (`built_at` of the new board minus `as_of` of the old).
- **(g) contention.** The write alone first (producer stopped while idle,
  three runs back to back), then (f) again with a fresh set of 60 cold keys
  while the same write runs three times, 60, 240 and 420 s into the window.
  The write is `write_cost.py`'s UPDATE, copied into
  `write_contention_perf3.py` (the perf1 helper is never pointed at this
  database), on the 16,792 rows of the LIVE hour: every hour here holds
  exactly 16,792 rows, so write_cost's "busiest hour" degenerates to the
  latest, which after alignment is a future hour no board reads. Each run is
  restored by writing the original `mention_z` values back exactly, because
  `+1.0` then `-1.0` is not an identity on a FLOAT; the restore is timed apart.
  The write runs in its own OS process so it does not share the GIL with the
  samplers.

### The scripts

All in `personal_apps/scratchpad/perf3/`, run from `personal_apps/`.

| script | what it does |
| --- | --- |
| `scale_env.py` | the launcher: credentials, the dotenv no-op, the database, the fixed revision, the REDDIT_SUBS patch, the coverage check; runs a target with runpy |
| `env_check.py` | the preflight block every script prints first; refuses a wrong database, pool, index set, stamp or coverage |
| `perf3_common.py` | statistics, child processes, working sets, HTTP with a minted session cookie, accounts, store rows |
| `align_scale_fixture.py` | Step 0; `--dry-run` prints the plan |
| `serve_perf3.py` | one web-model worker (MODEL, not gunicorn): the real WSGI app, one process, `--threads 1`, `/perf3/stats` |
| `measure_perf3.py` | Step 1 (a)-(g); `--phase` takes a comma list |
| `write_contention_perf3.py` | the ingest-shaped write for (g) |
| `admit_cost_perf3.py` | decision 6: the control-row write per admission |
| `profile_watch_perf3.py` | Step 3 / decision 7: the per-account half |
| `two_workers_perf3.py` | Step 2 / decision 8: the non-Radar request, MODEL, flag on and off |
| `ledger_tables_perf3.py` | the tables below, derived from the scripts' saved JSON |
| `request_timing_overhead.py` | Task 9a: the request-timing hooks' cost per request, on against off, through the Flask test client; no database |

### Step 1: the shared path at production scale

Prewarm from an empty store, producer start to eight fresh warm boards: **60.7 s**; builds [16565, 8580, 5048, 4943, 4999, 5092, 4876, 5131] ms (the first build in a fresh process fills its caches). Web-model workers listening after [4.75, 5.05] s.

#### (a) Ready reads, an account watching three tickers
Tickers ['T03947', 'T02561', 'T02522'] (the US 24h board's top three); the US All board, a warm key.

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| 12h `read_payload` (20 ready, 0 stale) | 20 | 54.8 | 72.7 | 76.4 | ms |
| 12h over HTTP, web-model worker (20 ready, 0 stale) | 20 | 106.6 | 140.0 | 142.8 | ms |
| 24h `read_payload` (20 ready, 0 stale) | 20 | 53.5 | 70.2 | 72.3 | ms |
| 24h over HTTP, web-model worker (20 ready, 0 stale) | 20 | 80.8 | 118.3 | 135.9 | ms |

First read per process and window, outside the n (the first read with watches in a process meets its caches empty): read_payload 12h 566.4 ms, web5081 12h 896.9 ms, web5082 12h 729.5 ms, read_payload 24h 97.6 ms, web5081 24h 108.3 ms, web5082 24h 126.9 ms.

**Scope, added after the Task 8 review.** Every read in this table was
taken right after the prewarm, with the producer idle. The only reads taken
as a build begins are (b)'s "read issued at publication": n=20, p95 492 ms,
max 623 ms, on a one-thread worker shared with the client's own poll, so
that figure is confounded as well. No ready series was taken during the
(f) or (g) load, when the producer was building 84-85% of the time, so
whether p95 <= 500 ms holds in steady state is unproven.

With the producer idle, ready reads meet the ruling's p95 <= 500 ms ready-response
target with a wide margin -- `read_payload` p95 70-73 ms, over HTTP 118-140 ms
through a loopback web-model worker (the HTTP figure adds WSGI, JSON encoding
of the decompressed board and the transfer). Both include the per-account half
for three watched tickers, which is most of the cost of a ready read (Step 3).
Every one of the 80 reads was `ready`; none was stale. The first read with
watched tickers in each process, kept outside the n, costs 0.57-0.90 s (12h)
because it meets that process's caches empty -- among them coverage.py's
covered-slot cache, which starts with a full scan (`coverage.py:75-81`) and
repeats that full scan every ten minutes (`FULL_RESCAN`, `coverage.py:41`), so
a long-running worker pays something like it again periodically. That is an
inference from the code, not a profile; (c) measures the restart case.

#### (b) Empty store: TRUNCATE both tables, then one request

The eight warm selections in turn; the requested board was built in position [1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 6, 6, 7, 7, 8, 8] of 8.

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| first answer: `pending`, rows null (NOT a board) | 20 | 40.8 | 55.5 | 57.4 | ms |
| queue wait (`enqueued_at` -> `as_of`) | 20 | 17.05 | 37.04 | 38.29 | s |
| build (`build_ms`) | 20 | 5.34 | 5.60 | 5.62 | s |
| request -> publish (row polled every 50 ms) | 20 | 22.44 | 42.73 | 43.77 | s |
| a read issued at publication | 20 | 119.0 | 492.1 | 623.0 | ms |
| **cold, read at publication -- UNMET <= 2 s goal** | 20 | 22.82 | 42.83 | 43.89 | s |
| build-to-usable (`as_of` -> board in hand) | 20 | 5.86 | 6.38 | 6.53 | s |
| **cold, as the client polls -- UNMET <= 2 s goal** | 20 | 23.21 | 42.93 | 44.01 | s |

Boards delivered: 20 of 20. First missing result within 2 s: **0 of 20** -- the goal stays UNMET.

After an empty store -- what a deploy with a new
namespace, or losing both tables, looks like -- the first request answered
`pending` in median 41 ms (p95 56 ms), every time a shell with `rows: null`
and no timestamp, never a board. The board the reader asked for then arrived
after median 22.8 s, p95 42.8 s, max 43.9 s (read at publication; the
client's own poll adds its cadence: median 23.2 s, p95 42.9 s). **The 2 s
first-missing-result goal is UNMET: 0 of 20.**

Nearly all of that is queue, not build: queue wait median 17.1 s, p95 37.0 s,
against a build of median 5.34 s. After a TRUNCATE the producer adopts all
eight warm keys at once and claims them oldest-board-first, and with every
`as_of` NULL the tie is broken by `key_hash` -- so the key a reader is
waiting for is built first, eighth or anywhere between, by hash: in these
runs `de/default/12h` was always first (published at 5.7 s) and `de/all/12h`
always eighth (at about 43 s). Nothing in the claim order prefers a warm key
somebody is actually waiting on. (The pending answer's retry hint cannot say
so either: it ranks by `enqueued_at`, where the reader's own admission comes
first.) This is a measured property of the design, recorded for the
whole-branch review, not changed here. The planned rollout keeps viewers out
of it -- the flag is turned on only after `--readiness` passes -- and the
prewarm from an empty store took 60.7 s in this run.

A read issued at the moment of publication took median 119 ms but p95 492 ms
and max 623 ms: the producer starts the next warm build immediately, and the
first reads of a fresh board meet that build's load on the same database.

#### (c) Restart: kill a web-model worker, start it, read

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| spawn -> listening (interpreter, launcher queries, app import) | 20 | 5.14 | 5.48 | 5.62 | s |
| first read afterwards | 20 | 666.2 | 769.4 | 774.2 | ms |
| second read | 20 | 106.8 | 143.4 | 150.2 | ms |

The first read was a board in 20 of 20 (1 stale).

The store survives a worker restart -- the first read
afterwards was a real board in 20 of 20 (one of them stale, served with its
age), never `pending` -- which is what the shared path promises. But that
first read is slow: median 666 ms, p95 769 ms, max 774 ms, against 107 ms for
the second read in the same process. **The ruling's <= 500 ms p95
ready-response target is therefore NOT met for the first read of a freshly
started worker**, while every steady read in (a), taken with the producer
idle, meets it by a wide margin.
The cost is the new process meeting its caches empty -- the account's pinned
rows (Step 3) among them, and coverage.py's covered-slot cache, whose first
call is a full scan -- and every gunicorn worker a deploy restarts pays it
once, on its first request with watched tickers. Spawn to listening was
median 5.14 s, p95 5.48 s; that includes the launcher's two queries, which a
deployed worker does not run.

#### (d) Cold on-demand selections, the producer running

**sort=lean 24h** (key deleted before every rep)

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| first answer: `pending`, rows null (NOT a board) | 20 | 43.1 | 60.2 | 65.0 | ms |
| queue wait (`enqueued_at` -> `as_of`) | 20 | 0.52 | 2.90 | 3.35 | s |
| build (`build_ms`) | 20 | 5.06 | 5.34 | 5.53 | s |
| request -> publish (row polled every 50 ms) | 20 | 5.72 | 8.06 | 8.93 | s |
| a read issued at publication | 20 | 103.9 | 131.7 | 132.5 | ms |
| **cold, read at publication -- UNMET <= 2 s goal** | 20 | 5.82 | 8.17 | 9.04 | s |
| build-to-usable (`as_of` -> board in hand) | 20 | 5.85 | 6.13 | 6.53 | s |
| **cold, as the client polls -- UNMET <= 2 s goal** | 20 | 6.42 | 9.38 | 9.50 | s |

Boards delivered: 20 of 20. First missing result within 2 s: **0 of 20** -- the goal stays UNMET.

**limit=100 24h** (key deleted before every rep)

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| first answer: `pending`, rows null (NOT a board) | 20 | 41.2 | 53.0 | 58.0 | ms |
| queue wait (`enqueued_at` -> `as_of`) | 20 | 2.00 | 2.91 | 2.95 | s |
| build (`build_ms`) | 20 | 5.15 | 5.47 | 5.49 | s |
| request -> publish (row polled every 50 ms) | 20 | 7.45 | 8.35 | 8.36 | s |
| a read issued at publication | 20 | 100.5 | 166.6 | 205.2 | ms |
| **cold, read at publication -- UNMET <= 2 s goal** | 20 | 7.55 | 8.46 | 8.56 | s |
| build-to-usable (`as_of` -> board in hand) | 20 | 5.81 | 6.32 | 6.36 | s |
| **cold, as the client polls -- UNMET <= 2 s goal** | 20 | 8.38 | 8.50 | 9.49 | s |

Boards delivered: 20 of 20. First missing result within 2 s: **0 of 20** -- the goal stays UNMET.

**limit=100 repeated:** 20 ready reads of 100 rows, median / p95 / max 103.9 / 144.3 / 149.5 ms.

A cold on-demand selection answers `pending` at once
(sort=lean: median 43 ms, p95 60 ms -- NOT a board) and is in the reader's
hands after median 5.8-6.4 s, p95 8.2-9.4 s, depending on whether the reader
asks at the instant of publication or at the client's own poll cadence. The
parts, stated apart as the ruling asks: the queue wait is short (median
0.5 s, p95 2.9 s, max 3.4 s). The producer alternates warm and on-demand
turns, so a cold key waits behind the build in flight and, when a warm key is
due as well, one warm build; here it never waited more than 3.4 s. The build
itself is the floor (median 5.06 s, p95 5.34 s), and the build-to-usable span
is median 5.85 s, p95 6.13 s. **The first-missing-result goal of 2 s is UNMET:
0 of 20 within it.** The build alone is 2.5 times the goal, so no queueing
policy can meet it at this scale; only a cheaper build could. The lean timing
is a lower bound (no `radar_posts`, so no tone work).

The `limit=100` board, which the ruling asks to be tested as a real cold and
repeated-use case, behaves the same way: `pending` in median 41 ms, a build of
median 5.15 s (p95 5.47 s) -- measured no dearer than the 50-row standing
boards, which build in about 5.0 s -- and a board in hand after median
7.6-8.4 s, p95 8.5 s, again 0 of 20 within 2 s. Its queue wait was longer than
lean's (median 2.0 s, p95 2.9 s): its reps met warm builds in flight more
often. Once built it is an ordinary ready read: 20 of 20 ready, 100 rows,
median 104 ms, p95 144 ms over HTTP.

#### (e) Memory, Windows working set (the local analogue of RSS), MB

| process | started | at rest | after 100 reads | peak | private |
| --- | --- | --- | --- | --- | --- |
| producer | 237.6 | 236.6 | 236.6 | 517.9 | 216.5 |
| web5081 | 127.5 | 131.5 | 131.8 | 141.4 | 111.4 |
| web5082 | 127.7 | 138.2 | 132.2 | 141.8 | 111.9 |
| producer at the end of Step 1 | | | 275.3 | 518.0 | 255.8 |

The producer holds about 237 MB of working set at rest and
peaked at about 518 MB -- a build holds its result sets while it runs -- with
about 217 MB private. Each web-model worker starts at about 128 MB, settles at
about 132 MB after reads and peaked at about 141 MB, with about 111 MB
private; 100 reads added nothing measurable. These are Windows working sets
of Python 3.12 processes; on the target the RSS of forked gunicorn workers and
of a systemd producer will differ -- the relative sizes transfer, the
megabytes do not.

#### (f) Queue age

120 table samples every 5 s; 36 warm and 60 on-demand builds; the producer was building 84% of the window.

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| warm board age when its refresh landed | 35 | 126.1 | 148.2 | 159.2 | s |
| warm refresh interval (`as_of` to `as_of`) | 35 | 120.6 | 142.7 | 153.8 | s |
| on-demand: request -> board in hand | 60 | 8.28 | 11.56 | 19.97 | s |
| on-demand queue wait | 60 | 2.75 | 5.49 | 9.05 | s |
| on-demand first answer (pending) | 60 | 39.9 | 58.6 | 67.1 | ms |

Worst warm age sampled: **156.0 s**; 70 of 960 warm samples (7%) past 120 s, 0 past 600 s. On-demand delivered 60 of 60; longest sampled queued: 15.0 s. Build seconds median/p95/max: warm [5.3, 5.6, 5.7], on-demand [5.2, 6.1, 16.1]. Slowest on-demand: us/all/1h sort=mentions 16.1 s; us/all/4h sort=mentions 12.3 s; de/all/4h dir=asc sort=ticker 6.3 s; de/all/4h sort=mentions 6.1 s; de/all/12h venues=2 6.1 s. Row-lock waits: 2 (9 ms).

**A failed criterion, stated plainly: the eight warm keys
do not stay within the 120 s fresh bound.** Over ten minutes of one on-demand
request every 10 s, each warm board was 126 s old at the median, 148 s at p95
and 159 s at worst when its replacement was published, and 70 of 960 warm
samples (7.3%) found a warm board past 120 s -- served, correctly, as stale
with its age and a refresh under way. The 600 s hard expiry held with a wide
margin. Two causes, one structural and one of load:

- *Structural.* `refresh_seconds` and `fresh_seconds` are both 120, and a key
  is only enqueued once it is due, so every warm board is past its fresh
  bound for at least the time its successor takes to be claimed and built --
  about 5.5 s -- on every cycle, whatever the load. The refresh interval
  measured median 120.6 s: the schedule itself is kept.
- *Load.* The producer was building 84% of the window. With one producer
  alternating warm and on-demand turns, a due warm key also waits behind the
  on-demand build in flight, which stretches the overshoot to p95 148 s, max
  159 s. In steady state that lateness does not show as queue wait on the
  build line: `refresh_warm` only enqueues a due key at the next tick,
  between builds, and the claim usually follows in the same tick (in (f)
  every warm build logged `queue_wait=0.0`). The age is therefore the number
  reported, not the queue wait.

Nothing was tuned to hide this. Moving the fresh bound would only rename it,
and the ruling says to return the failed criterion rather than widen the age
limit. What would change the structure is a refresh target below the fresh
bound (for example refresh at 100 s, fresh at 120 s) or a second producer;
both are decisions for the owner, not measurements.

On-demand work was fully served: 60 of 60 delivered, request to board in hand
median 8.3 s, p95 11.6 s, max 20.0 s, queue wait median 2.75 s, p95 5.5 s. The
two slowest builds were the process's FIRST 1h build (16.1 s) and FIRST 4h
build (12.3 s); later ones were median 3.2 s (1h) and 5.9 s (4h), against
5.1 s for 24h. (g)'s restarted producer showed the same thing with different
selections (its first 1h build 13.4 s, first 4h 12.6 s), so this reads as a
per-process, per-window cold start in a producer that had only built 12h and
24h boards -- an inference from the pattern, not a profile.

#### (g) Under write contention

121 table samples every 5 s; 38 warm and 61 on-demand builds; the producer was building 85% of the window.

| | n | median | p95 | max | unit |
| --- | --- | --- | --- | --- | --- |
| warm board age when its refresh landed | 38 | 125.9 | 139.8 | 142.8 | s |
| warm refresh interval (`as_of` to `as_of`) | 38 | 120.5 | 134.2 | 137.7 | s |
| on-demand: request -> board in hand | 60 | 8.91 | 16.58 | 22.80 | s |
| on-demand queue wait | 60 | 4.17 | 11.74 | 17.12 | s |
| on-demand first answer (pending) | 60 | 39.5 | 54.2 | 58.7 | ms |

Worst warm age sampled: **141.2 s**; 65 of 968 warm samples (7%) past 120 s, 0 past 600 s. On-demand delivered 60 of 60; longest sampled queued: 20.0 s. Build seconds median/p95/max: warm [5.3, 5.8, 5.9], on-demand [5.3, 6.2, 13.4]. Slowest on-demand: de/large/1h 13.4 s; de/large/4h 12.6 s; us/fund/4h 7.5 s; us/all/4h limit=100 venues=2 6.2 s; de/all/4h limit=100 venues=2 6.2 s. Row-lock waits: 4 (17 ms).

| write (16,792 live-hour rows) | update runs, s | restore runs, s |
| --- | --- | --- |
| alone, producer stopped | 6.03, 6.30, 6.17 | 6.45, 6.02, 6.59 |
| under the sweep | 5.64, 5.63, 5.75 | 5.47, 5.55, 5.66 |

Under the write the sweep held the same profile: warm
boards 126 s old at the median when replaced, p95 140 s, max 143 s, 65 of 968
samples (6.7%) stale, the hard expiry held; 60 of 60 on-demand requests
delivered, median 8.9 s, p95 16.6 s, max 22.8 s. **The fresh bound failed
here too (worst 142.8 s), for the reasons above; write contention did not make
it worse.** The longer on-demand tail than (f) (queue wait p95 11.7 s against
5.5 s) is attributable, from the producer's own timestamped build lines, to
the phase's start rather than to the writes: (g) needed the producer stopped
for the write-alone baseline, so it ran on a freshly started producer whose
first 1h and 4h builds took 13.4 s and 12.6 s at 18:39:08-18:39:25, and the
queue backed up behind them -- on-demand waits of 8.7-17.1 s and warm waits of
10.7-14.0 s at 18:39:25-18:41:08, all before or clear of the first write
(18:39:59-18:40:10). Inside the three write windows the waits were the usual
0-7 s.

The write side: write_cost's UPDATE of the live hour's 16,792 rows took
6.03-6.30 s alone (producer stopped) and 5.63-5.75 s under the sweep; the
exact restore 6.02-6.59 s alone and 5.47-5.66 s under it. No slowdown under
the producer's reads; the run-to-run spread is larger than any difference.
This is MySQL 8.0.46 with the producer's reads only -- not the ingest
daemon's real cycle, its scoring pass or partition maintenance.

### Decision 6: the control-row write on every admission -- measured, not gated

Carried from the Task 2 review: every admission, polls included, runs
`UPDATE radar_board_namespaces SET last_seen_at = GREATEST(last_seen_at, :now)`
inside `_under_lock`. `admit_cost_perf3.py` timed 1,000 admissions and 1,000
polls through `board_store.admit` with that UPDATE and without it (the second
arm replaces `_under_lock` with a copy minus the one statement, for the
comparison only), in one process and in two OS processes admitting at once,
two rounds in alternating order, in a bench namespace of 16 already-queued
keys that no producer claims. The rule was written into the script before the
first run: gate the write if it adds more than 5 ms at p95 in any arm, or
shows lock waits of its own -- any wait in the one-process arm with the
UPDATE, or, with two processes, over 20% more waits or wait time with it than
without, by at least 10 waits, in every round.

`admit_cost_perf3.py`: 1000 admissions and 1000 polls per arm and round, 2 rounds, alternating order.

| arm | kind | p50 with | p50 without | p95 with | p95 without | p95 delta |
| --- | --- | --- | --- | --- | --- | --- |
| one process | admit | 5.99 | 5.38 | 8.48 | 7.7 | +0.78 |
| one process | poll | 5.9 | 5.44 | 8.55 | 7.83 | +0.72 |
| two processes | admit | 10.92 | 9.69 | 14.69 | 12.94 | +1.75 |
| two processes | poll | 10.8 | 9.77 | 14.39 | 12.7 | +1.69 |

| arm | round | mode | row-lock waits | wait time ms |
| --- | --- | --- | --- | --- |
| single | 0 | with | 0 | 0 |
| single | 0 | without | 0 | 0 |
| single | 1 | without | 0 | 0 |
| single | 1 | with | 0 | 0 |
| pair | 0 | with | 3999 | 18233 |
| pair | 0 | without | 3999 | 15287 |
| pair | 1 | without | 3999 | 16048 |
| pair | 1 | with | 3999 | 17899 |

Verdict: **NOT TRIGGERED**

**Not triggered, so not gated, and no store change or test was needed.** The
statement costs about 0.7-0.8 ms at p95 alone and about 1.7 ms with two
concurrent admitters, a third of the 5 ms line at worst. An admission costs
about 6 ms on its own because every commit is flushed (`log_bin=1`,
`sync_binlog=1`, `innodb_flush_log_at_trx_commit=1`), and the admission
already commits a write to the results row, so the extra statement adds its
own redo but no extra flush. With two processes, 3,999 of 4,000 calls waited
for the control row in EVERY run, with the UPDATE and without it alike: that
is the `SELECT ... FOR UPDATE` serializing two admitters, the mutex the store
chose, and the statement under test never waits itself, because its
transaction already holds the row. What the statement does is lengthen the
critical section: total wait time rose 19.3% and 11.5% in the two rounds,
about 0.5-0.7 ms per call, which is inside the p95 delta above. A caveat on
my own rule: its wait-time branch also required ten more waits, which cannot
happen when every call already waits; on wait time alone the second round
(+11.5%) still misses "every round". The lock waits under the real two-worker
load are in Step 2.

### Step 2 / decision 8: a non-Radar request beside two cold boards -- MODEL

**A MODEL of gunicorn, not gunicorn.** Two OS processes (`serve_perf3.py`),
one request thread each, serving the real WSGI app: the model of `--workers 2`
with sync workers. Nothing of gunicorn's arbiter, worker lifecycle, reload,
signals or timeouts is modelled. PERF2 ran the same model on the OLD
synchronous path and measured a cheap request at 7,602 ms worst with one
thread per process (9 ms with two). `two_workers_perf3.py` re-measures it on
the new path, as the ruling asks:

- **flag ON** -- the real producer builds; the two workers only read (a
  pending answer, polls at the server's retry hint, then the board);
- **flag OFF** -- no producer, today's deployment; each worker builds its own
  board inside the request.

Ten episodes per flag. Each asks two cold selections at the same moment, one
per worker -- `us/All/24h` and `de/All/12h` with a distinct `limit` per
episode (60-69 on, 80-89 off), so each costs what a standing board costs and
neither can be answered by the 60-second memo or the store -- and each client
waits the way the real one does until a board is in hand. Meanwhile one
sequential client requests `/` (the app overview: a user lookup and a render)
round-robin across both workers every 100 ms, as PERF2's did. The idle
baseline is twelve `/` requests with the first two discarded. The cookie is
the fixture account's, minted with the app's own serializer; it watches
nothing.

| flag | `/` idle median / p95 / max ms | `/` during two cold boards: n, median / p95 / max ms | boards in hand, median / p95 / max s | statuses |
| --- | --- | --- | --- | --- |
| ON | 15.7 / 30.6 / 30.6 | 1205, 23.4 / 29.5 / 78.7 | 10.12 / 17.64 / 20.20 | [200] |
| OFF | 28.6 / 34.2 / 34.2 | 29, 306.6 / 6,769.0 / 9,521.6 | 4.87 / 6.77 / 16.39 | [200] |

Row-lock waits across the flag-ON episodes: 23 (135 ms).

**The shared path removes the block -- in this MODEL.** With the flag ON, a
cheap non-Radar request during two cold board requests took median 23.4 ms,
p95 29.5 ms and 78.7 ms at worst over 1,205 requests, close to what it takes
idle (median 15.7 ms); every one answered 200. With the flag OFF, as deployed
today, the same request took median 307 ms, p95 6,769 ms, worst 9,522 ms:
whenever the round-robin landed on a worker that was building, it waited out
the build -- PERF2's 7,602 ms again, 9.5 s this time with the first build of a
cold process. The flag-off sample is small (29 requests) for exactly that
reason: one sequential client, each request waiting out a build.

The price is paid by the boards, not by the site. With the flag off each
worker builds its own board, so the two are built in parallel and arrive in
median 4.9 s (the first episode, in cold processes, 6.8 s and 16.4 s). With it
on, the one producer builds them in turn and interleaves the warm refreshes,
so they arrive in median 10.1 s, p95 17.6 s, max 20.2 s -- the cold cost of a
single producer. Row-lock waits across the ten flag-on episodes: 23, 135 ms in
total, so the control-row contention decision 6 measured in isolation is
negligible at this load.

### Step 3 / decision 7: the per-account half

`profile_watch_perf3.py`. A stored board is viewer-invariant; the reader's
marks are added per request by `routes.api.account_fields` --
`watch.tickers_for` and `board.build_pinned_rows` -- and no cache can remove
that half. Accounts `perf3_w00`/`w03`/`w10`/`w25` watched the first 0, 3, 10
and 25 tickers of the stored US 24h All board (the ones a reader would star),
n = 20 each after one discarded call, on the US 12h, US 24h and DE 24h boards.
The ORM session is removed after every call, outside the timer, so each call
checks a connection out and pings it as a request does. The script started
its own producer so the whole-`read_payload` series met fresh boards (one read
per series taken outside the n: the first read with watches in a process meets
its caches empty), then stopped it while idle, so the `account_fields`
timings ran on a quiet database. The accounts were deleted afterwards.

Run 2, reported:

Watched tickers from the stored US 24h All board (as_of 2026-09-11 18:57:51.052895): ['T02561', 'T03317', 'T03947', 'T04703', 'T03356', 'T04742', 'T02891', 'T02878', 'T03330', 'T04716', 'T03343', 'T04729', 'T02522', 'T03908', 'T02865', 'T02904', 'T03660', 'T03673', 'T03686', 'T03208', 'T03699', 'T04972', 'T02548', 'T03934', 'T02535'].

| board | watching | n | median ms | p95 ms | max ms | watch rows |
| --- | --- | --- | --- | --- | --- | --- |
| us 12h | 0 | 20 | 0.8 | 2.4 | 2.4 | 0 |
| us 12h | 3 | 20 | 36.2 | 51.5 | 53.4 | 3 |
| us 12h | 10 | 20 | 56.8 | 86.8 | 98.2 | 10 |
| us 12h | 25 | 20 | 109.6 | 129.4 | 134.3 | 25 |
| us 24h | 0 | 20 | 1.3 | 1.8 | 2.1 | 0 |
| us 24h | 3 | 20 | 51.4 | 71.9 | 73.6 | 3 |
| us 24h | 10 | 20 | 67.5 | 95.1 | 96.5 | 10 |
| us 24h | 25 | 20 | 112.5 | 150.5 | 177.4 | 25 |
| de 24h | 0 | 20 | 1.0 | 2.0 | 2.5 | 0 |
| de 24h | 3 | 20 | 42.4 | 75.2 | 112.9 | 3 |
| de 24h | 10 | 20 | 57.0 | 94.2 | 99.5 | 10 |
| de 24h | 25 | 20 | 111.6 | 165.3 | 176.2 | 25 |

| whole `read_payload`, US 24h, watching | median ms | p95 ms | max ms | ready/stale |
| --- | --- | --- | --- | --- |
| 0 | 3.6 | 5.3 | 10.8 | 20/0 |
| 3 | 51.5 | 63.5 | 78.5 | 20/0 |
| 10 | 67.6 | 99.1 | 107.1 | 20/0 |
| 25 | 109.1 | 184.6 | 192.7 | 20/0 |

The worst 25-ticker median (US 24h): **112.5 ms** against 150 ms -> NOT TRIGGERED.

Run 1 -- the same script before its whole-read guard was fixed; per-account half only:

| board | watching | n | median ms | p95 ms | max ms | watch rows |
| --- | --- | --- | --- | --- | --- | --- |
| us 12h | 0 | 20 | 1.9 | 3.3 | 3.4 | 0 |
| us 12h | 3 | 20 | 27.5 | 35.4 | 37.8 | 3 |
| us 12h | 10 | 20 | 39.9 | 45.1 | 45.7 | 10 |
| us 12h | 25 | 20 | 80.4 | 135.6 | 192.9 | 25 |
| us 24h | 0 | 20 | 0.8 | 1.4 | 1.6 | 0 |
| us 24h | 3 | 20 | 31.9 | 41.0 | 44.8 | 3 |
| us 24h | 10 | 20 | 50.9 | 65.5 | 68.4 | 10 |
| us 24h | 25 | 20 | 85.4 | 129.2 | 140.8 | 25 |
| de 24h | 0 | 20 | 0.9 | 1.8 | 2.8 | 0 |
| de 24h | 3 | 20 | 32.3 | 48.3 | 50.7 | 3 |
| de 24h | 10 | 20 | 44.9 | 64.3 | 76.5 | 10 |
| de 24h | 25 | 20 | 88.8 | 131.2 | 140.0 | 25 |

The worst 25-ticker median (DE 24h): **88.8 ms** against 150 ms -> NOT TRIGGERED.

**Decision 7 was not triggered: no memo, no test.** The worst 25-ticker
median was 112.5 ms in run 2 (US 24h; US 12h 109.6 ms, DE 24h 111.6 ms) and
88.8 ms in run 1 (DE 24h), against the brief's 150 ms. The brief does not
name a board for "the 25-mark case", so the worst of the three governs. The
per-account half grows with the marks: about 1 ms with none, 27-51 ms for
three, 40-68 ms for ten and 80-113 ms for twenty-five (medians, both runs) --
roughly 2.4-3.3 ms for each mark beyond the third. The margin is not wide.
Medians moved by a quarter to a third between the two full runs (a two-call
smoke run saw 133 ms), and at p95 the 24h boards reach 150-165 ms at
twenty-five marks. Twenty-five is not a ceiling on what an account can mark;
the memo the brief describes (keyed on account, marks, key and `as_of`, 64
entries) remains the prepared remedy if the target's median moves.

This half is most of a ready read. The whole `read_payload` on a fresh stored
board took median 3.6 ms with no marks, 51.5 ms with three and 109.1 ms (p95
184.6 ms) with twenty-five: inside the 500 ms ready target, but a stored board
alone does not make a read cheap for a heavy watcher, which is the ruling's
point about per-account enrichment. Run 1 skipped the whole-read series: its
guard refused a stored board 92 s old, stricter than the fresh bound needed.
Run 2 waits, with the producer running, for a board under 60 s old instead.
Both runs' per-account tables are given; run 2 is the one reported above.

### Browser: both boards in a real browser (Task 8b)

Task 8's Step 4 and the browser half of Step 5, dispatched after Task 8a.
One script, `scratchpad/perf3/browser_perf3.py`, on the same aligned scale
database, through the same launcher and under the same limits as everything
above in this section.

**What ran.** python-playwright 1.61.0 driving headless Chromium
149.0.7827.55, at 1440x900 except the phone shots (390x844). The real app,
served by `serve_perf3.py` as one web-model process with two request threads
-- the concurrency of the deployed two sync workers; a MODEL, not gunicorn --
on port 5090 with the flag on (5091 with it off, check 7), and the real
`run_radar_board_producer.py` beside it, started, stopped and restarted by the
script as each check needs. Nothing was mocked: every page and every board
answer came from those two processes and the store they share. The session
cookie was minted with the app's own signing serializer for a disposable
account, `perf3_browser`, created with no marks and deleted afterwards with
its marks; no password was typed anywhere.

**One revision for every process.** The dispatch pins `RADAR_BUILD_REVISION`
to the HEAD this run started from, `caa92bb`, and `scale_env.py` had Task 8a's
revision written into it. It now takes the pin from `PERF3_REVISION`, which the
script sets before the launcher is imported and every child inherits; the
launcher's own default is still Task 8a's revision, so Task 8a's scripts run as
they did. That is the one change to a Task 8a file. Every process printed
namespace `8d69315904e6dbc1f5d3a62bf79f248f0a71393350f6a844f15e3cf478cfa485`
(fingerprint `3586f78497044d4d`) and the script refused any other. Between
`0b50952` and `caa92bb` only scratchpad scripts and this ledger changed, so the
application under test is the one Task 8a measured.

**The bundle under test is the reviewed source.** `static/radar/dist` is
untracked, and it was built 72 s before the last client commit (`d429378`) was
made. A fresh `vite build -c vite.radar.config.ts` of HEAD into a scratch
directory produced byte-identical files -- `board-BbirrnOH.js`,
`hub-BiVrB4HX.js`, `hub-BaOZANf0.css`, `embedded-Do395cc6.js` and the
manifest -- so both pages ran exactly the code Tasks 5 and 6 committed.

**How the page is read.** An init script, installed in every page before the
page's own scripts run, wraps `fetch` -- every request, and a digest of every
board answer (the selection it echoes, `as_of`, its flags, its ticker list),
on the page's own clock -- and a MutationObserver records every distinct state
the page paints: the ticker rows, the waiting notice, the age line, the
context line, the controls, the busy flag. Times are the page's
`performance.now()`, counted from navigation start, so no number depends on
how often the script looked. Two of them are defined once, here:

- *time to rows*: navigation start to the first ticker row in the DOM;
- *time to usable*: navigation start to the first moment the board can be
  used -- rows, no waiting notice, an age line, nothing in flight and, on the
  old board, the selected ticker's detail panel settled -- followed by an idle
  main thread (`requestIdleCallback`).

On the hub every check uses Human chatter (`/radar/hub/?…#chatter`), the page
that carries the window and size controls and lists every row; Overview shows
the same waiting notice under its own heading.

**Hidden is emulated, and why.** Headless Chromium reports `visible` for a page
whatever is done to it. Probed in both headless modes before the script was
written: bringing a second page to the front, CDP focus emulation off,
`Page.setWebLifecycleState`, a minimised window -- `document.visibilityState`
stayed `visible` every time. So the init script overrides the
`visibilityState` and `hidden` getters and dispatches a bubbling
`visibilitychange`, which is what the old board's Poller, the hub's
`useVisible` and react-query's focusManager all read. What check 3 proves is
how both pages act on that signal, not that a browser sends it.

Preflight, as the run printed it:

```
PREFLIGHT  browser_perf3 (Task 8b): both boards in a real browser
  database     personal_apps_radar_perf3_scale   engine 8.0.46   alembic b7e3f9c1a2d4
  buffer pool  2560 MB (target 2560 MB)
  indexes      deployed three
  rows         9,269,184 radar_bucket_sources; 0 radar_posts; 1 app_user; 0 radar_watch
  span         radar_bucket_sources   2026-08-21 13:00:00 -> 2026-09-13 12:00:00
  span         radar_mention_events   2026-09-08 13:00:00 -> 2026-09-13 12:59:00
  span         radar_quotes           2026-09-09 13:00:00 -> 2026-09-13 12:00:00
  residue      3 radar_mention_events rows dated more than 7 days ahead (test residue; untouched)
  window rows  24h 403,008   12h 201,504   at 2026-09-11 19:44:46 UTC
  reddit       REDDIT_SUBS patched: 33 names; warm-set coverage 403,008 of 403,008 = 100%
  namespace    8d69315904e6dbc1f5d3a62bf79f248f0a71393350f6a844f15e3cf478cfa485  revision caa92bba99b8  fingerprint 3586f78497044d4d
  store        8 radar_board_results rows, 1 namespaces
```

#### What the checks found

Three runs, all with this script in this environment on 2026-09-11: **run
1**, every check (19:44-19:56 UTC); **run 2**, checks 3, 6 and the phone shots
again, after the fix to the hidden check's clock described below; **run 3**,
the phone shots once more, after a fix to when the phone check measures (also
below). The screenshots of checks 3 and 6 are run 2's, the phone shots are
run 3's, and every other screenshot is run 1's.

| check | old board `/radar/` | hub `/radar/hub/` | what decided it |
| --- | --- | --- | --- |
| 1 empty store | PASS | PASS | the pending copy first (0.31 s / 0.08 s): no row, no "Nothing cleared", no stamp; rows at 18.8 s, usable at 22.3 s / 18.8 s |
| 2 rapid switching, from a ready board | PASS | PASS | final rows = `read_payload`'s for the final selection, 50 of 50, same order; no paint of another selection's rows |
| 2 rapid switching, from a pending board | PASS | PASS | the same, with a poll in flight when the burst began |
| 3 hidden tab while pending | run 1 FAIL (the harness's clock, see below); run 2 PASS | run 1 PASS; run 2 PASS | no poll in 10 s hidden; one poll on return |
| 4 stale to fresh | PASS | PASS | "Calculated 5m ago · refreshing" at load; cleared by a poll at 5.9 s / 11.4 s, no reload |
| 5 hard-expired | PASS | PASS | the pending state, not the 700 s board; rebuilt board by poll at 8.7 s / 8.6 s |
| 6 delayed | PASS, both runs | PASS, both runs | at 31 s "Still calculating…", the reason, the way out and Retry; after the producer started, rows with no reload |
| 7 flag off | PASS | PASS | old: "not refreshed" with Retry at 120.0 s, no request in 140 s; hub: one read 60.0 s after arrival, and 125.7 s after the next |
| 8 the star | PASS, A and B | not applicable | address bar and final board on the new selection; every request after the move was for it; the mark kept |
| phone, 390x844 | PASS | PASS | a pending and a ready shot each; the old board's page jumps 4,219 px to its panel when the panel loads (finding 2) |

**1, empty store.** Both store tables truncated, then the page opened on
`us/all/24h`, a warm key. The document came back in 106 ms (old board) and
26 ms (hub) carrying the pending shell (`pending: true`, `rows: null`), and the
first thing painted was the waiting copy: "Calculating this board…", no row, no
empty-board sentence, no age line, no ticker count on the old board's status
line. The producer rebuilt the eight warm keys in `key_hash` order and this key
was third both times, published 16.4 s and 15.7 s after the TRUNCATE; both
pages had rows at 18.8 s, each after seven `poll=1` asks and nothing else. Time
to usable was 22.3 s on the old board -- 3.4 s after its rows, spent on the
detail panel of the ticker it selected -- and 18.8 s on the hub, which has no
panel. As third in the rebuild, neither page reached 30 s, so the delayed copy
was not seen here: Task 8a's eighth key (`de/all/12h`) waits about 44 s, past
it. Check 6 shows the delayed state on its own.

**2, rapid switching.** Six changes 200 ms apart (measured 188-220 ms),
alternating window and segment, twice per page: from a ready `us/all/12h` to
`us/discover/24h`, and from a pending `us/fund/4h`, with its poll in flight, to
`us/all/24h`. On both pages the final rows were exactly `read_payload`'s for
the final selection -- 50 of 50 in the same order, the answer on screen with
the store's own `as_of` -- and the rendered context named 24 hours: the hub's
context line ("US markets · last 24 hours"), the old board's tier caption
("chatter vs the 24h price move"). Every paint after the first change was held
against its moment: on the hub, every set of rows on screen was the answer to
the selection its own controls showed then; on the old board, only the board it
already had (marked busy once the request was out) or the final board, and
nothing after the final one. No violation in the four runs. The two clients
take the burst differently, as designed: the old board's 250 ms debounce sent
nothing inside the burst and one request after it (then four polls, when the
final key was cold), while the hub asked once per change -- six requests, each
for its own selection, none a poll -- and drew only the current key's answer.

**3, hidden tab while pending.** With the producer stopped, so the wait could
not end, each page opened on a cold key, polled once, and was hidden for 10 s,
then shown. Run 2: neither page asked anything while hidden (0 board requests in the
10.02 s, none in flight at the hide), and each asked exactly once on
return, a `poll=1`: the old board 0.2 ms after the stamp taken before the
`visibilitychange` dispatch -- from inside the handler, as
`Poller.resume()` does -- and the hub 1.7 ms after it, from the effect
that follows the dispatch. Both were still waiting afterwards, with no row
and no stamp (`8b-3-old-hidden-returned.png`,
`8b-3-hub-hidden-returned.png`). Run 1's old-board FAIL and its cause are
set out below.

**4, stale to fresh.** A warm row aged to 300 s by moving its `as_of` and
`built_at` back together. Both pages loaded the stale board with "Calculated 5m
ago · refreshing" -- the embedded answer `stale: true`, age 300.1 s -- while the
store queued the refresh and the producer rebuilt it. The pages' polls, at the
server's 5 s floor, brought the new board in: the marker cleared at 5.9 s on the
old board (one poll) and 11.4 s on the hub (two), with no reload and no request
that was not a poll.

**5, hard-expired.** A warm row aged to 700 s is past the 600 s hard expiry,
and the store answers it as missing. Both pages opened on the pending shell, not
on the old board -- no rows, no stamp, "Calculating this board…" -- and the
rebuilt board arrived by poll after 8.7 s and 8.6 s.

**6, delayed.** With the producer stopped, a cold key (DE Large 4h on the old
board, DE Large 1h on the hub) was open on both pages at once. At 31 s both
said "Still calculating…", why ("A board nobody has asked for recently is built
from scratch."), the way out ("Change the window or the feeds to ask for one
that may already be built.") and offered Retry. The producer was then started
(5.2 s to its namespace line) and the boards arrived with no reload -- the
page's own time origin unchanged -- 44.7 s (old board) and 56.7 s (hub) after it
was spawned in run 1. Most of that is the restarted producer's own queue: all
eight warm keys were overdue after more than a minute without a producer, and a
fresh process's first 4h and 1h builds are the slow ones Task 8a measured
(12-16 s). Run 1's "poll gaps after 30 s" is empty because the script took it at
the 31 s mark, when one poll at most had happened; run 2 measures the cadence
from 30 s until the board: the old board's polls
came 5,050-5,978 ms apart (seven gaps) and the hub's 5,070-6,017 ms (ten) --
the schedule's 5 s plus up to a fifth of jitter; the hub times each ask from
the previous answer, so a gap also carries that answer's round trip -- and
the boards arrived 39.8 s and 55.9 s after the producer was spawned, again
with no reload.

**7, flag off.** The server restarted with `RADAR_BOARD_SHARED_RESULTS=off` and
no producer: today's deployment. Both embedded boards said `shared: false`,
built in the request. The old board crossed its 120 s bound on its own clock at
120.0 s and then read "Calculated 2m ago · not refreshed" with a Retry, marked
stale, and sent no board request at all in the 140 s it was watched, the last
20 s past the bound. The hub read its board again 59.96 s after arrival -- a
read, not a poll -- which the server answered with a new synchronous build in
5.7 s; that answer armed the next minute, and the next read went out at
125.67 s. One read per arrival, as the hub always read its board.

**8, the star (old board).** The mark's PUT was held in flight by route
interception and released on cue. A: star on `us/all/24h`, window moved to 12 h
149 ms later, the mark released 1.6 s after that, with the 12 h board already
up. B: star on `us/all/12h`, window moved to 24 h, the mark released 195 ms
later, inside the controls' 250 ms debounce. Both times the address bar ended
on the new query (`window=12`, then `window=24`), every board request after the
move was for the new selection (A: the debounced read, then the mark's
refetch; B: the one debounced read, which carried the mark), the final rows
were the new selection's with the starred tickers in Watching, and the star
stayed on.

**Phone, 390x844.** A pending and a ready screenshot per page, on cold keys
with the producer running. Rows arrived at 22.4 s (old board) and 8.8 s (hub)
in run 3 -- which ran this first, on a producer whose first 4h build is the
slow one Task 8a measured -- and at 8.6 s and 8.7 s in run 1. Both pages drew
the waiting state and then the board in their stacked layouts. The hub's page
stayed where it was; the old board's jumped to its detail panel when the
panel's detail loaded, 3.5 s after the rows: finding 2. Since run 3 the check
measures at that moment; run 2 measured 1.5 s after the rows, before the
detail had loaded, and saw nothing move.

**Check 3, old board: a failure of the harness, found, corrected and re-run.**
The full run recorded FAIL for the old board's hidden check -- one poll counted
"while hidden" and none "on return" -- and PASS for the hub. The cause was the
script's clock, not the page. `setHidden` stamped the moment AFTER
`dispatchEvent` returned, but a listener runs inside the dispatch, and the old
board's `Poller.resume()` sends its poll synchronously from the
`visibilitychange` handler (`resume` -> `fire` -> `load` -> `fetch`, no await
before the request). That poll therefore started before the "visible" stamp and
was counted as sent while hidden; the hub asks from a React effect, after the
dispatch, and was counted correctly. The script now stamps both sides of every
dispatch and classifies against the stamp taken before it, and saves each
request's time relative to the hide. Re-run (run 2): the old board sent no
board request in the 10.02 s it was hidden and exactly one `poll=1` on return,
0.2 ms after the stamp, from inside the handler; the hub, again, none while
hidden and one on return 1.7 ms after the stamp, from its effect. That is run
1's "one while hidden, none on return" exactly, read with the right clock. The
full run's own numbers stay in its table below, as printed.

**Findings the checks were not written to catch.** Each was seen in this run's
own screenshots or numbers, none changes a verdict above, and each is carried
to the whole-branch review.

1. **The Discover tab asks for a cold duplicate of a warm board.** The old
   board's Discover tab and the hub's Discover size both send
   `segment=discover`. The producer keeps `DEFAULT_SEGMENT`,
   `discover,mid,micro,unknown`, warm, and segments enter the key verbatim
   (Task 1), so these are two keys: `091c0c1b805c`, not warm, and
   `7bb7964cf50c`, warm. Read side by side in this run, the two hold the same
   rows in the same order (US, 24h). A reader who opens the default board,
   moves off it and comes back through the tab is served an on-demand board --
   pending, then a build -- for a board the producer already keeps warm. Check
   2's ready start ends on this key, which is why the old board's final rows
   landed 8.5 s after the last change there against 0.4 s from the pending
   start, whose final key is warm. Canonicalising the group before keying, or
   warming the tab's spelling, would remove the duplicate; both change the key
   contract and neither is made here.
2. **On a phone, a board arriving after a wait moves the reader to the detail
   panel.** `DetailPane` hands focus to its panel whenever the detail of a new
   ticker loads, deliberately without `preventScroll` (DetailPane.tsx:144-153),
   and starts its memory at the page's opening ticker "so the FIRST panel does
   not steal focus from the top of the document on page load"
   (DetailPane.tsx:122-126). A page that opens on a waiting shell has no opening
   ticker. When the board arrives and the top row is selected, the first panel
   does take focus, and at 390x844, where the panel sits under the whole list,
   the page scrolls to it. Measured in run 3, on the old board at 390x844:
   while pending the page sat at the top (scroll 0, focus on the body, the
   panel's top 404 px down); when the rows arrived it had not moved (scroll 0,
   the panel now 3,941 px down, under the list); 3.5 s later, when the
   panel's detail loaded, it was at scroll 4,219 px with focus on
   `main.detail` and the panel's top 278 px above the viewport --
   `8b-m-old-ready-390.png` is that moment. (Run 1's phone shot, taken 0.8 s
   after the rows, happened to catch the same jump; run 2 measured at 1.5 s,
   before the detail had loaded, and saw nothing -- hence run 3.) Before
   PERF3 no page opened without rows, so this arrives with the pending path;
   on a desk the same focus move happens without the scroll.
3. **The old board's view tabs read zero while pending.** A waiting shell
   carries `segment_counts: {}` (board_shared.py:397) and the tabs render a
   missing count as a dimmed 0: "All 0 · Discover 0 · Large 0 …" above
   "Calculating this board…" (`8b-1-old-empty-pending.png`,
   `8b-5-old-expired-pending.png`, `8b-6-old-delayed.png`,
   `8b-m-old-pending-390.png`). The status line beside them prints no count on
   purpose -- "'0 tickers' over a board that is still being built is a
   measurement nobody made" (ListPane.tsx:286-289) -- and the tabs say exactly
   that. The hub's Size select carries no counts and is not affected.
4. **Two small visual notes.** At 1440x900 the old board's age line wraps onto
   three lines in its corner once "refreshing" is added ("Calculated / 5m ago ·
   / refreshing", `8b-4-old-stale-refreshing.png`). The hub's top bar prints the
   session value raw, "Tradegate-first Germany · afterhours"
   (`8b-6-hub-delayed.png`), where the old board says "after hours".

#### The numbers, as the script printed them

Every figure above is in these tables, printed by `browser_perf3.py --tables`
from each run's saved JSON. The JSON and the producer and server logs are kept
under `%TEMP%/radar-perf3-task8b/{full1,rerun2,rerun3}/`, not committed. Times
are the page's own clock unless a column says otherwise; a "case" is the
check's own title.

##### Run 1, check 1: empty store

| page | case | document ms | pending copy at s | time to rows s | time to usable s | delayed copy at s | board requests while waiting | age line on arrival | rebuild position of 8 | published s after TRUNCATE | build ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old | empty store -> us/all/24h | 106 | 0.31 | 18.82 | 22.25 | n/a | 7 | Calculated 7s ago | 3 | 16.4 | 5170 |
| hub | empty store -> us/all/24h | 26 | 0.08 | 18.78 | 18.82 | n/a | 7 | Calculated 8s ago | 3 | 15.7 | 4978 |

##### Run 1, check 2: rapid switching

| page | case | change intervals ms | board requests from the first change on | ...of them poll=1 | same order as the final answer | start and final boards distinguishable by rows | window in the rendered context line | rows on screen / in read_payload | same order as read_payload | paints after the first change | final rows painted ms after the last change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old | six changes 200 ms apart from a ready board (us/all/12h -> us/discover/24h) | 217, 188, 203, 203, 200 | 5 | 4 | yes | yes | 24 | 50 / 50 | yes | 10 | 8483 |
| hub | six changes 200 ms apart from a ready board (us/all/12h -> us/discover/24h) | 220, 189, 197, 209, 200 | 6 | 0 | yes | yes | 24 | 50 / 50 | yes | 12 | n/a |
| old | six changes 200 ms apart from a pending board (us/fund/4h -> us/all/24h) | 202, 202, 207, 198, 208 | 1 | 0 | yes | yes | 24 | 50 / 50 | yes | 10 | 378 |
| hub | six changes 200 ms apart from a pending board (us/fund/4h -> us/all/24h) | 212, 201, 206, 198, 189 | 6 | 0 | yes | yes | 24 | 50 / 50 | yes | 12 | n/a |

##### Run 1, check 3: hidden tab

| page | case | polls before hiding | poll in flight at the hide | board requests during 10 s hidden | ...of them poll=1 | board requests within 1.5 s of visible | first request after visible ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old | hidden while pending (us/recent_ipo/4h) | 1 | no | 1 | 1 | 0 | n/a |
| hub | hidden while pending (us/recent_ipo/1h) | 1 | no | 0 | 0 | 1 | 2 |

- FAILED [old] 1 board request(s) while hidden

- FAILED [old] 0 request(s) on return, not one

##### Run 1, check 4: stale to fresh

| page | case | embedded age s | age line at load | marker cleared at s | age line after | board requests until then | refreshed board as_of |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old | stale to fresh (us/all/24h) | 300.1 | Calculated 5m ago · refreshing | 5.88 | Calculated 5s ago | 1 | 2026-09-11T19:48:26.444110Z |
| hub | stale to fresh (us/all/12h) | 300.1 | Calculated 5m ago · refreshing | 11.44 | Calculated 10s ago | 2 | 2026-09-11T19:48:43.937666Z |

##### Run 1, check 5: hard-expired

| page | case | time to rows s | age line then |
| --- | --- | --- | --- |
| old | hard-expired (us/all/12h) | 8.72 | Calculated 8s ago |
| hub | hard-expired (us/all/24h) | 8.61 | Calculated 8s ago |

##### Run 1, check 6: delayed

| page | case | waited s | waiting copy | poll gaps after 30 s ms | producer start to namespace line s | rows s after the producer was spawned | rows s after it logged its namespace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old | delayed, producer stopped, then started (de/large/4h) | 31.25 | Still calculating…A board nobody has asked for recently is built from scratch. Change the window or the feeds to ask for one that may already be built.Retry | (none) | 5.2 | 44.74 | 39.42 |
| hub | delayed, producer stopped, then started (de/large/1h) | 31.14 | Still calculating…A board nobody has asked for recently is built from scratch. Change the window or the feeds to ask for one that may already be built.Retry | (none) | 5.2 | 56.71 | 51.51 |

##### Run 1, check 7: flag off

| page | case | embedded shared / age s | "not refreshed" at page-clock age s | age line | board requests from load to +20 s past the bound | observed s after arrival | board reads at s after arrival | first read answered s later | its answer: shared / age s | hub age line now |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old | flag off: past 120 s on the page clock (us/all/24h) | False / 0.0 | 120.0 | Calculated 2m ago · not refreshedRetry | 0 | 140.18 | n/a | n/a | n/a | n/a |
| hub | flag off: one re-read about 60 s after arrival (us/all/12h) | False / 0 | n/a | n/a | n/a | n/a | 59.96, 125.67 | 5.71 | False / 0 | Calculated 13s ago |

##### Run 1, check 8: the star

| page | case | starred | filter moved ms after the star | mark held ms (star to release) | mark released ms after the filter moved | on screen when released | address bar | board requests after the filter moved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old | star A: the mark lands after the new board is up (us/all/24h -> us/all/12h) | T03947 | 149 | 1748 | 1599 | 50 rows, controls 12h/All, busy False | window=12 segment='' t=T00543 | us/all/12h@314ms, us/all/12h@1623ms |
| old | star B: the mark lands inside the controls' debounce (us/all/12h -> us/all/24h) | T01929 | 143 | 337 | 195 | 51 rows, controls 24h/All, busy False | window=24 segment='' t=T02561 | us/all/24h@331ms |

##### Run 1, check m: phone, 390x844

| page | case | time to rows s |
| --- | --- | --- |
| old | 390x844 (us/mid/4h) | 8.63 |
| hub | 390x844 (us/micro/4h) | 8.67 |

##### Run 2, check 3: hidden tab

| page | case | hidden for s | polls before hiding | poll in flight at the hide | board requests during 10 s hidden | ...of them poll=1 | board requests within 1.5 s of visible | first request after visible ms | sent inside the visibilitychange handler |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| old | hidden while pending (us/recent_ipo/4h) | 10.02 | 1 | no | 0 | 0 | 1 | 0.2 | yes |
| hub | hidden while pending (us/recent_ipo/1h) | 10.02 | 1 | no | 0 | 0 | 1 | 1.7 | no |

##### Run 2, check 6: delayed

| page | case | waited s | waiting copy | producer start to namespace line s | poll gaps from 30 s until the board ms | rows s after the producer was spawned | rows s after it logged its namespace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old | delayed, producer stopped, then started (de/large/4h) | 31.28 | Still calculating…A board nobody has asked for recently is built from scratch. Change the window or the feeds to ask for one that may already be built.Retry | 5.2 | 5943, 5235, 5050, 5905, 5116, 5907, 5978 | 39.75 | 34.47 |
| hub | delayed, producer stopped, then started (de/large/1h) | 31.12 | Still calculating…A board nobody has asked for recently is built from scratch. Change the window or the feeds to ask for one that may already be built.Retry | 5.2 | 5991, 5925, 6017, 5390, 5635, 5070, 5139, 5465, 5104, 5713 | 55.85 | 50.65 |

##### Run 3, check m: phone, 390x844

| page | case | while pending: scroll, focus, panel top | time to rows s | right after the rows: scroll, focus, panel top | usable s after the rows | panel settled: scroll, focus, panel top |
| --- | --- | --- | --- | --- | --- | --- |
| old | 390x844 (us/mid/4h) | {'y': 0, 'active': 'BODY.', 'panel_top': 404} | 22.35 | {'y': 0, 'active': 'BODY.', 'panel_top': 3941} | 3.51 | {'y': 4219, 'active': 'MAIN.detail', 'panel_top': -278} |
| hub | 390x844 (us/micro/4h) | {'y': 0, 'active': 'BODY.', 'panel_top': None} | 8.81 | {'y': 0, 'active': 'BODY.', 'panel_top': None} | 0.04 | {'y': 0, 'active': 'BODY.', 'panel_top': None} |

#### Screenshots

30 files in `radar-design/perf3-shots/`, each viewed before it was relied on;
1440x900 unless the name says 390.

| file | run | what it shows |
| --- | --- | --- |
| `8b-1-hub-empty-pending.png` | run 1 | empty store: the pending copy, no rows, no stamp |
| `8b-1-hub-empty-ready.png` | run 1 | empty store: the board arrived, with its age line |
| `8b-1-old-empty-pending.png` | run 1 | empty store: the pending copy, no rows, no stamp |
| `8b-1-old-empty-ready.png` | run 1 | empty store: the board arrived, with its age line |
| `8b-2-hub-switch-pending-final.png` | run 1 | after six changes from a pending board: us/all/24h |
| `8b-2-hub-switch-ready-final.png` | run 1 | after six changes from a ready board: us/discover/24h |
| `8b-2-old-switch-pending-final.png` | run 1 | after six changes from a pending board: us/all/24h |
| `8b-2-old-switch-ready-final.png` | run 1 | after six changes from a ready board: us/discover/24h |
| `8b-3-hub-hidden-returned.png` | run 2 | hidden 10 s while pending, then visible: still pending |
| `8b-3-old-hidden-returned.png` | run 2 | hidden 10 s while pending, then visible: still pending |
| `8b-4-hub-stale-cleared.png` | run 1 | the producer's refresh landed: the marker cleared, no reload |
| `8b-4-hub-stale-refreshing.png` | run 1 | a warm board aged to 300 s: "Calculated 5m ago · refreshing" |
| `8b-4-old-stale-cleared.png` | run 1 | the producer's refresh landed: the marker cleared, no reload |
| `8b-4-old-stale-refreshing.png` | run 1 | a warm board aged to 300 s: "Calculated 5m ago · refreshing" |
| `8b-5-hub-expired-pending.png` | run 1 | a warm board aged to 700 s: the pending state, not the board |
| `8b-5-hub-expired-rebuilt.png` | run 1 | the rebuilt board arrived by poll |
| `8b-5-old-expired-pending.png` | run 1 | a warm board aged to 700 s: the pending state, not the board |
| `8b-5-old-expired-rebuilt.png` | run 1 | the rebuilt board arrived by poll |
| `8b-6-hub-delayed.png` | run 2 | producer stopped, 31 s: the delayed copy and its Retry |
| `8b-6-hub-recovered.png` | run 2 | the producer started: the board arrived with no reload |
| `8b-6-old-delayed.png` | run 2 | producer stopped, 31 s: the delayed copy and its Retry |
| `8b-6-old-recovered.png` | run 2 | the producer started: the board arrived with no reload |
| `8b-7-hub-flagoff-reread.png` | run 1 | flag off: the hub after its minute's re-read |
| `8b-7-old-flagoff-not-refreshed.png` | run 1 | flag off, past 120 s on the page clock: "not refreshed" with Retry |
| `8b-8-old-star-A.png` | run 1 | star A: the new selection, the mark kept, the address bar on the new query |
| `8b-8-old-star-B.png` | run 1 | star B: the new selection, the mark kept, the address bar on the new query |
| `8b-m-hub-pending-390.png` | run 3 | phone, 390x844: pending |
| `8b-m-hub-ready-390.png` | run 3 | phone, 390x844: where the page is once the board and its panel have arrived |
| `8b-m-old-pending-390.png` | run 3 | phone, 390x844: pending |
| `8b-m-old-ready-390.png` | run 3 | phone, 390x844: where the page is once the board and its panel have arrived |

**Left as found.** Every server and producer the script started was stopped;
after each run the account `perf3_browser` and its marks were deleted, and so
was every on-demand board the run had caused (13 in run 1, 4 in run 2, 2 in run
3; rows of other namespaces left: 0). The aligned fixture is untouched; the
store holds this namespace's eight warm boards.

### Request timing (Task 9a)

`personal_apps/request_timing.py`, installed from `app.py`, registers nothing
unless `PERSONAL_REQUEST_TIMING_LOG` is `1`, `true`, `yes` or `on`. On, it
writes one stdout line per request on `app.request` --
`request method=GET route=/radar/api/ticker/<ticker> status=200 bytes=2048 ms=41.3`,
the route a rule TEMPLATE, `<unmatched>` or `<static>`, never a path value,
query string, cookie, header, address or account -- and hangs the same handler
on `radar.board`, with propagation cut on both. Tests:
`tests/test_request_timing.py`, 32.

**The gap it closes, confirmed before any change.** The web process configures
no handler for `radar.board`: `app.py` sets up none, and gunicorn 26.2.0's
`glogging.Logger.setup` touches only `gunicorn.error` and `gunicorn.access`.
So the logger inherits the root's WARNING, and every `board read` line has
been dropped before it was formatted; only the producer's lines, after its
own `basicConfig`, reached journald.
`test_a_freshly_imported_app_drops_every_board_line_with_the_variable_unset`
shows it (a fresh interpreter importing `app`: INFO disabled, no handler at
INFO, `log_read` prints nothing) and passed on the unchanged code. **With the
variable unset -- the default, and the state the release deploys with -- that
is still true.**

**Overhead.** `personal_apps/scratchpad/perf3/request_timing_overhead.py`,
run from `personal_apps/`: two minimal Flask apps with the same cheap dynamic
route, one installed on and one off (no hooks); per round 1,000 requests to
each through the Flask test client, alternating, after 200 warm-up pairs; the
enabled handler writing to `os.devnull`, a write and a flush per line. Windows
11, Python 3.12.6, Flask 3.1.3, no database. Microseconds per request:

| round | off median | off p95 | on median | on p95 | on - off, median | on - off, p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 172.9 | 219.1 | 219.3 | 293.3 | +46.4 | +74.2 |
| 2 | 174.6 | 468.0 | 222.2 | 598.4 | +47.6 | +130.4 |
| 3 | 172.1 | 283.7 | 219.3 | 341.3 | +47.2 | +57.6 |

About **47 us per request at the median**, steady across rounds; the p95
difference moves with the machine (round 2's p95 rose for both apps alike).
That is under 0.1% of the fastest ready read above (`read_payload` p95
70-73 ms). Not modelled: journald's side of the line (a socket write on
Linux, and its rate limit), gunicorn, MariaDB. Retention is journald's and is
not verified here: the target's journald settings are unread.

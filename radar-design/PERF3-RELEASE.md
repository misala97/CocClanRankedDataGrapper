# PERF3 release package: a proposal

**Nothing in this package has been applied.** No unit is installed, no script is edited and no flag is set. No migration has run outside the disposable databases, and the target was not contacted while this was written. The target is still at `4221196`, on migration head `a7c31f0b52d4`. Merging, pushing, deploying and every step below are separate decisions for the owner. Every command is his to run, after the reads in section 9.

**What would ship** is `codex/radar-perf3` on top of the deployed `4221196`. Leaving out tests and scratch scripts, the application files it touches are:

- **New server files:**
  - under `personal_apps/features/radar/`: `board_keys.py`, `board_namespace.py`, `board_store.py`, `board_producer.py`, `board_shared.py` and `board_metrics.py`;
  - `personal_apps/request_timing.py` and `personal_apps/run_radar_board_producer.py`;
  - the migration `b7e3f9c1a2d4`.
- **Changed server files:** `app.py`, `models.py`, `features/radar/observations.py`, `features/radar/routes/api.py` and `routes/operations.py`.
- **Client:** 17 non-test files under `static/radar/`, which give both boards their pending, stale, busy and failed states.

The evidence is in `PERF3-LEDGER.md`. The whole suites are in its Task 9b section.

## 1. Migration `b7e3f9c1a2d4`

| | |
| --- | --- |
| File | `personal_apps/migrations/versions/b7e3f9c1a2d4_add_radar_board_results.py`, unchanged since `0eba6a4` |
| Chain | Revises `a7c31f0b52d4`, the target's head. It is the single head on this branch. No other revision names either one as its parent, and the suite's in-process `upgrade()` to `head` ran `a7c31f0b52d4 -> b7e3f9c1a2d4`, which alembic refuses when there are several heads |
| Upgrade | Additive. It creates `radar_board_namespaces` (primary key `namespace`) and `radar_board_results` (primary key `(namespace, key_hash)`), plus three indexes on the second table: `ix_radar_board_results_queue`, `_warm` and `_demand`. It alters, reads and writes no existing table, and moves no data |
| Downgrade | Drops `radar_board_results`, then `radar_board_namespaces`, and nothing else. All it loses is cached boards, which the producer rebuilds |
| First deploy | Both tables are created empty. Nothing backfills them, and with the flag off nothing reads them |
| Run by | The `FLASK_APP=app.py flask db upgrade` that `update_coc.sh` already runs in `personal_apps/` (TARGET-FACTS §1). No new step |

**Rehearsed on MariaDB 10.11.14**, the target's version. The rehearsal used a portable mariadb.org build with a fresh datadir and `personal_apps/scratchpad/perf3/rehearse_board_results_mariadb.py` (PERF3-LEDGER, "MariaDB 10.11.14 rehearsal server"). It passed 53 checks at `0eba6a4`, then 54 at `c2d0ca9` and 54 at `c199d06`. The checks covered:

- the upgrade from the previous stamp, with a neighbour table left intact;
- the column shapes: `key_json` TEXT, `payload` MEDIUMBLOB, microsecond timestamps;
- a 4,000-character key and a 12 KB payload round-tripping under both strict and permissive `sql_mode`;
- the store on that engine: admission, claim, fenced publish, backoff, queue cap, eviction and retirement;
- the downgrade, which dropped exactly the two tables, kept the neighbour's rows and left the previous stamp;
- a second upgrade.

The store module has changed once since the last run (`6752492`). The migration has not, and the rehearsal was not repeated.

**Writers.** No writer has to stop for this migration, because no existing table is touched. The script stops `radar_ingest` before the checkout anyway. It never stops the web unit (TARGET-FACTS §1.1), and the old code has no model for these tables.

**If `flask db upgrade` fails partway.** The upgrade is five DDL statements: two `CREATE TABLE` and three `CREATE INDEX`. MariaDB commits each one on its own. If the run is interrupted between them, the stamp stays at `a7c31f0b52d4` and a blind re-run fails on whichever table already exists. This case was not rehearsed. On a first deploy both tables are empty and nothing reads them, so the recovery is to drop whichever of the two exists and re-run `flask db upgrade`. Do not stamp.

**Once it has run, the stamp is `b7e3f9c1a2d4`, which older code cannot resolve.** That matters only if the code is rolled back (section 6).

## 2. The producer unit

The full text is in `radar-design/perf3-release/radar_board_producer.service`. **It is not installed.**

| Line | Value | Why |
| --- | --- | --- |
| `ExecStart=` | `/root/coc-stats/venv/bin/python run_radar_board_producer.py` | the venv `update_coc.sh` installs into, run from the checkout it resets; the same interpreter the web uses |
| `WorkingDirectory=` | `/root/coc-stats/personal_apps` | the directory the web's `app:app` has to run from. **Reconcile against `personal_apps_web.service`, which has never been read** |
| `User=` | `root` | **Reconcile against `personal_apps_web.service`, which has never been read** |
| `EnvironmentFile=` | `/root/coc-stats/.env` | **Reconcile against `personal_apps_web.service`, which has never been read.** Redundant for the app's own keys, because `app.py` loads the same file with `override=True` (section 4) |
| `Restart=`, `RestartSec=` | `always`, `10` | this is the only process that builds boards, so a crash must not leave readers waiting |
| `KillSignal=` | `SIGTERM` | the handler sets the stop event, and the loop finishes the build in flight before it exits (`run_radar_board_producer.py:45-62`, `features/radar/board_producer.py:450-492`) |
| `TimeoutStopSec=` | `150` | above the 120 s lease. A build still running at 150 s has lost its lease and could not publish, so the SIGKILL that follows loses nothing. A normal stop takes one build: about 5-6 s, or 12-16 s for a fresh process's first 1h or 4h board |
| `StandardOutput=`, `StandardError=` | `journal` | the producer logs through `logging.basicConfig`, which writes to stderr (section 5) |

The three values to reconcile are the ones in the repository's own `personal_apps/deploy/radar-encoder-trial.service`, which match the layout `update_coc.sh` shows: `/root/coc-stats`, its `venv`, and `/root/coc-stats/.env`. The file contains no `%`, so no specifier escaping arises.

**Installing it (proposal):**

1. Copy it to `/etc/systemd/system/`.
2. Run `systemctl daemon-reload`.
3. Run `systemctl enable radar_board_producer`.

Start it only after the deploy that brings its code and creates its tables (section 4, step 3). Started before that deploy, it would find no `run_radar_board_producer.py` and would restart every 10 s.

## 3. Deploy-script additions, and the build revision

### 3.1 Two lines in `update_coc.sh`: proposed, not applied

These are written against the order of operations TARGET-FACTS §1 recorded on 2026-09-09. That listing shows the order, not necessarily the literal text, so re-read the script (section 9) before editing it.

- Next to `systemctl stop radar_ingest`, before the checkout, add `systemctl stop radar_board_producer`.
- Change the closing start line to `systemctl start coc_scheduler personal_apps_gym_notifier radar_ingest radar_board_producer`.

Stopping the producer before the checkout keeps it off while `pip install` replaces packages underneath it, the same treatment `radar_ingest` gets. The stop waits for the build in flight: normally 5-16 s, never more than `TimeoutStopSec=150`. Once the flag is on, the old web workers' readers have no producer for the rest of that window. Warm boards are served as stale, with their age, and a new selection waits. The web restart ends it.

**Add these lines only after the unit file is installed.** The script runs under `set -e`, and `systemctl stop` exits non-zero for a unit systemd has never loaded. The script would then abort before the checkout, right after stopping `coc_scheduler`, the notifier and `radar_ingest`, and nothing would be started again. A unit that is installed but inactive stops with exit 0.

### 3.2 The build revision: write no file on the VPS

Re-verified in `personal_apps/features/radar/board_namespace.py` at this commit:

1. `build_revision()` (lines 62-92) takes the first of these that yields a revision, and raises `ConfigError` if none does:
   1. the `RADAR_BUILD_REVISION` environment variable (78-81);
   2. a `BUILD_REVISION` file at `_repo_root()` (83-86);
   3. git's own files (88-90).

   A value that is present but is not a revision is refused, not skipped (`_configured`, 196-209).
2. `_repo_root()` is `Path(__file__).resolve().parents[3]` (176-181). That is the repository root, `/root/coc-stats` on the VPS. PERF3-PLAN's Step 2 said `personal_apps/`; the plan's third amendment corrects that.
3. The git fallback reads `.git`, `HEAD`, loose refs and `packed-refs` directly, with no subprocess (212-298). The VPS checkout is a git repository that `update_coc.sh` resets to `origin/main`, so every process resolves the deployed commit without any file.

**Recommendation: no `BUILD_REVISION` file on the VPS, and no `RADAR_BUILD_REVISION` anywhere.** The trap is this:

- the file outranks git;
- it is untracked, and not listed in `.gitignore`;
- `git reset --hard` leaves untracked files alone.

So a file written once and not rewritten by every deploy pins an old revision. Every later deploy would keep serving boards that the old code built, which is exactly the failure the namespace exists to prevent. `RADAR_BUILD_REVISION`, set in `.env` or in a unit, outranks both, so it is the same trap. If a deploy ever ships without `.git`, every deploy must rewrite the file before any process starts. Section 9 checks that the file is absent.

The web workers, the producer and a `--readiness` run each resolve the namespace for themselves. With nothing pinned they all read the same `HEAD` and agree. Section 4 compares them.

### 3.3 Every deploy starts on an empty store (Task 8's open decision 2)

The namespace is `sha256(payload_version:revision:fingerprint)` (`board_namespace.py:106-114`), and the revision is the `HEAD` of the whole shared checkout. So any commit on `main` gives the next deploy a new namespace with no rows, including a coc_stats change or a documentation commit. Readers then meet `pending` while a fresh producer rebuilds the eight warm boards in `key_hash` order.

Measured at scale (PERF3-LEDGER, Step 1 (b) and (f)):

- the prewarm from an empty store took 60.7 s;
- a reader's warm board arrived after a median 22.8 s, p95 42.8 s, and about 44 s at worst;
- a fresh producer's first 1h and 4h builds take 12-16 s.

The old namespace's rows stay until they are retired, 24 h after last use.

**A proposed ordering, for the owner and Codex to decide. It is not part of 3.1.** Once the flag is on, a routine deploy would start the new producer before restarting the web, and wait a bounded time for its warm set:

```
# after `npm ci && npm run build`, in place of the immediate restarts:
systemctl start radar_board_producer
for i in $(seq 1 18); do
  (cd /root/coc-stats/personal_apps &&
   /root/coc-stats/venv/bin/python run_radar_board_producer.py --readiness >/dev/null) && break
  sleep 5
done
systemctl restart coc_web
systemctl restart personal_apps_web
systemctl start coc_scheduler personal_apps_gym_notifier radar_ingest
```

- **What it gains.** Readers after the restart find eight ready warm boards instead of up to about 44 s of `pending`. The producer's slow first builds happen before anyone asks.
- **What it costs.** The web restart moves later by the length of the prewarm: 60.7 s from empty locally, unmeasured on the target.
  - During that wait the old workers serve old code against the new checkout. Templates are read per request, static files and the Vite manifest come from the new tree, and the dependencies have been reinstalled. That is the mixed-version window TARGET-FACTS §1.1 describes and Codex ruled against for migrations, and it grows from about 25 s to about 25 s plus the prewarm.
  - The old workers' reads go to the old namespace, and its producer was stopped before the checkout. Its warm boards are served stale, with their age, and a new selection waits in a queue nobody serves until the restart.
- **Bounded, and never fatal.** Each probe is a fresh interpreter importing the app, about 5 s here, so 18 rounds come to roughly three minutes. On timeout the loop falls through and the deploy carries on with today's empty-store behaviour. Under `set -e`, a failing left side of `&&` does not abort the script, and the loop's last command is `sleep`, so the loop always exits 0.
- **A moment, not a state.** Refresh target and fresh bound are both 120 s, so every warm board is past its bound while its successor builds. `--readiness` therefore answers "not ready" some of the time even when the producer is healthy. Under load about 7% of warm samples were stale, and with eight boards a single probe is caught out more often than that. Pass it once; it is not a health check.

**Alternatives:**

- **(i)** Keep 3.1 only. The web restarts at once, and every deploy puts readers through the empty-store wait.
- **(ii)** Stop the web unit as well and start it after readiness, which is the RELEASE-RUNBOOK's shape. There is no mixed window, but the outage grows by the prewarm.
- **(iii)** Code changes that shrink the problem, for Codex:
  - claim first the warm keys a reader is waiting on (Task 8);
  - or derive the revision only from what can change a payload, meaning `personal_apps/` and its dependencies, rather than the repository's `HEAD`, so coc_stats-only and documentation deploys keep the store.

## 4. Flag sequencing and the readiness gate

### 4.1 Where each flag is set: a trap Task 9a found

`app.py:12` calls `load_dotenv(override=True)`. Three facts follow from that.

- **Which file.** python-dotenv's `find_dotenv()` (1.2.2 here, `dotenv/main.py:332-372`) starts from the directory of the file that called it, which is `personal_apps/`, and walks up. It does not start from the working directory. On the VPS it takes `/root/coc-stats/personal_apps/.env` if one exists, and otherwise `/root/coc-stats/.env`, the file both apps read.
- **Which value wins.** With `override=True`, every key in that file replaces the value systemd gave the process, whether it came from `Environment=` or from `EnvironmentFile=`.
- **Which processes.** Every long-running process imports `app`:
  - the web (`gunicorn ... app:app`);
  - the producer (`run_radar_board_producer.py:31`);
  - `radar_ingest` (`run_radar_ingest.py:29`);
  - the notifier (`run_gym_notifier.py:6`).

So a unit's value for a key holds only while `.env` says nothing about that key. A rollback made in the unit while `.env` holds the key changes nothing.

**`RADAR_BOARD_SHARED_RESULTS`: set it in `/root/coc-stats/.env` and nowhere else.**

- `.env` is the one layer nothing overrides.
- Only the web request path reads the flag. `routes/api.py:490-500` reads it on each call, for `build_payload` and for `/radar/api/ops`.
- No other process uses it. The capture job builds boards directly and never reads it (`features/radar/observations.py:44-49`). The producer never reads it. The other processes that load `.env` are unaffected.
- It takes effect at the next web restart, because `load_dotenv` fills `os.environ` once, at import.
- Any of `1`, `true`, `yes` or `on` means on.
- **Rollback changes that same line to `off` and restarts the web unit.** Write `off` rather than deleting the line, so that no stray value set in a unit can come back into force.

**`PERSONAL_REQUEST_TIMING_LOG`: also `/root/coc-stats/.env` and nowhere else, and only when the owner decides to switch it on (section 5).** The precedence is the same, so the place is the same. What that entry switches on:

- **The web:** request lines and board read lines.
- **The producer**, because it imports `app`: its `radar.board` lines move from basicConfig's stderr handler (`INFO:radar.board:...`) to the stdout handler (`radar.board ...`). Each line is still printed once.
- **`radar_ingest` and the notifier:** nothing. They serve no requests and write no `radar.board` lines. The only callers of `board_metrics` are `board_shared.py:433` and `board_producer.py:282,316`.

**Rollback removes the key where it was set, then restarts the web unit and the producer.** One more consequence: a `.env` that holds the key on a development machine makes `tests/test_request_timing.py`'s fresh-import OFF test fail with a dict mismatch. It also blinds the board suites' caplog assertions.

Set neither flag in a unit's `Environment=` or in a drop-in.

### 4.2 The first rollout, in order

1. **Before anything else:**
   - the reads in section 9;
   - a fresh backup through the established, verified mechanism (RELEASE-RUNBOOK §3);
   - a check that `.env` has no `RADAR_BOARD_SHARED_RESULTS` line. With no such line, the flag is off.
2. **Deploy with the flag off.** Run the existing `update_coc.sh` without 3.1's lines, because the producer unit does not exist yet.
   - `flask db upgrade` creates the two empty tables, and `flask db current` then shows `b7e3f9c1a2d4`.
   - The web restarts on the new code. The server builds every board inside the request, as it does today.
   - The new client code ships with this deploy (Task 8b check 7):
     - a board older than 120 s by the page's clock reads "not refreshed", with a Retry;
     - the hub re-reads once, a minute after a board arrives, while the page is visible.
   - The timing line stays off.
3. **Install and start the producer.** Install section 2's file, run `systemctl daemon-reload`, then run `systemctl enable --now radar_board_producer`. Follow `journalctl -u radar_board_producer -f`. It should show:
   1. `radar board producer namespace=<64 hex> payload_version=1 revision=<the deployed commit> fingerprint=<16 hex> owner=<...>`;
   2. `board producer running ...`;
   3. eight `board build key=<12 hex> class=warm ... result=published` lines, which took about a minute locally;
   4. after that, a `board queue ...` line every minute.

   No page changes yet.
4. **Add 3.1's two lines to `update_coc.sh`.** The unit exists now.
5. **The readiness gate.** Run `cd /root/coc-stats/personal_apps && ../venv/bin/python run_radar_board_producer.py --readiness`. It prints one JSON object, and exits 0 once every warm board is fresh. Repeat until it exits 0. A ready answer reads:

   ```
   {"fresh_seconds": 120.0, "missing": [], "namespace": "<...>", "ready": true, "warm_limit": 8, "warm_ready": 8, "warm_total": 8}
   ```

   - The printed `namespace` must equal the one in the producer's start line. If they differ, the two resolved different revisions or configuration: stop.
   - If it is not ready within about five minutes, read the producer's journal and do not turn the flag on.
6. **Turn the flag on.** Add `RADAR_BOARD_SHARED_RESULTS=on` to `/root/coc-stats/.env`, then run `systemctl restart personal_apps_web`.
7. **Verify** through the `board_results` block of `/radar/api/ops`. The route is admin-only (`operations.py:62-63`), so this uses the owner's own session; no session is minted for it. The block should show:
   - `enabled: true`;
   - a `namespace` equal to the producer's;
   - `producer.seen_at` within the last minute, a recent `producer.success_at`, and `producer.error` null;
   - `warm_ready: 8` out of `warm_total: 8`;
   - `queue.pending`, `queue.building` and `queue.failed_due` near zero, and a small `on_demand_rows`.

   Also check that a board page says "Calculated … ago", and that `journalctl -u radar_board_producer` shows `class=ondemand` builds as readers pick other selections.
8. **Routine deploys from then on** run with the flag on, and the script stops and starts the producer. The ordering question in 3.3 applies to them.

## 5. Telemetry: prepared, nothing activated

**The request-timing line** (Task 9a, `personal_apps/request_timing.py`, `e3aedfb`) is off by default. With `PERSONAL_REQUEST_TIMING_LOG` unset, `install` registers no hook and touches no logger. When it is on (`1`, `true`, `yes` or `on`, in `.env` per 4.1), each request writes one INFO record on the logger `app.request`. The handler's format is `%(name)s %(message)s`, so the journal receives the logger's name first:

```
app.request request method=GET route=/radar/api/ticker/<ticker> status=200 bytes=1234 ms=12.3
```

- **`route`** is the matched rule's template, `<unmatched>` when no rule matched, or `<static>` for every static file. It never carries a path value, query string, cookie, header, client address or account.
- **`method`** is one of seven methods, and `<other>` for anything else.
- **`ms`** runs from the first `before_request` hook to the last `after_request` hook, which makes it the application's time, not the client's. It leaves out:
  - URL matching and opening the session, which happen earlier, when the request context is pushed (`flask/ctx.py:404`);
  - saving the session, which happens after the hooks (`flask/app.py:1322`);
  - sending the body, which happens after the WSGI app returns.
- **`bytes`** is the Content-Length as `after_request` sees it, or `-` for a streamed body. Werkzeug later sends no body for HEAD, 1xx, 204 and 304 (`werkzeug/wrappers/response.py:536-538`), so those lines report a size that was never sent. A static revalidation reads `status=304 bytes=<full size>`. **Do not add up `bytes` as traffic.**
- **Overhead** is about +47 µs per request at the median: +46.4, +47.6 and +47.2 µs in three rounds, and +58 to +130 µs at p95. It was measured through the Flask test client on Windows, with the handler writing to `/dev/null`. Journald's socket write, gunicorn and MariaDB are not modelled (PERF3-LEDGER, "Request timing (Task 9a)").

**The same variable is what brings the board's read metrics out.** In the web process, `board_metrics.log_read` writes one line per board read:

```
radar.board board read demand=initial|poll class=warm|ondemand key=<12 hex> outcome=ready|stale|pending|busy|failed cache_age=<s> queue_age=<s> read_ms=<n> account_ms=<n>
```

Nothing in the web process configures a handler for that logger. `app.py` sets none, and gunicorn 26.2.0 configures only `gunicorn.error` and `gunicorn.access`. **With the variable off, which is the deploy default, the web process's read lines are dropped before they are formatted and never reach journald. Only the producer's lines do** (Task 9a's fresh-import test).

The demand and outcome metrics the ruling asks for therefore exist in production only once the variable is on: initial demand against polls, ready, stale, pending and busy outcomes, and queue and cache age per key. Switching it on is a separate owner decision, not part of this rollout.

**The producer's own lines** are always on. `run_radar_board_producer.py:80` calls `logging.basicConfig(level=INFO)`, which writes to stderr and so to journald:

- **At start:** `radar board producer namespace=... payload_version=... revision=... fingerprint=... owner=...`, then `board producer running owner=... poll_interval=0.50s`.
- **Per build:** `board build key=<12 hex> class=warm|ondemand queue_wait=<s> build_ms=<n> payload_bytes=<n> result=published|overtaken|failed`.
- **Once a minute:** `board queue pending=<n> building=<n> failed_due=<n> on_demand=<n> warm_ready=<n> evicted=<n> retired=<n>`.
- **On failure:** the first failure with its traceback, then `board producer tick failed failures=<n> next_wait=<s>`, backing off to 30 s.
- **At stop:** `board producer asked to stop signal=15`, then `board producer stopped owner=...`.

A warm build logs `queue_wait=0.0` even when the board is late, so read lateness from the board's age, not from the queue wait (PERF3-LEDGER finding 5). None of the lines NAMED above carries a query, the JSON of a key, a user or a path. **The traceback beside them can.** `board_producer.py:269,298` log the first failure with `logger.exception`, and a SQLAlchemy error's traceback carries the failing statement and its bound parameters -- a key hash and a namespace among them. The same caveat as Flask's own line below: the journal is not free of such values, and this package does not claim that it is.

**What the journal can carry anyway.** Flask's own error line on any unhandled exception, `Exception on <path> [<METHOD>]` (`flask/app.py:876`), writes the raw request path to stderr, and journald keeps it. This predates the branch, and the new module does not forward it. The journal is therefore not free of path values, and this package does not claim that it is.

**journald defaults.** systemd v255, on Ubuntu 24.04, defaults to the following (PERF3-LEDGER, "Facts settled"):

- `Storage=auto`, which is persistent only if `/var/log/journal` exists;
- `SystemMaxUse=` 10% and `SystemKeepFree=` 15% of the file system, each capped at 4G;
- `MaxRetentionSec=0`, meaning nothing is deleted by age;
- a rate limit of 10,000 messages per 30 s per service, scaled up with free disk. The timing line alone would need about 333 requests a second to reach it.

**The target's journald settings are unread.** Before relying on them, check `journalctl --disk-usage`, `/etc/systemd/journald.conf` and `/etc/systemd/journald.conf.d/*.conf`, and whether `/var/log/journal` exists.

**What this assumes about the web unit, which is unread.** The timing line and the read lines reach journald only if all three of these hold:

1. **No logging configuration.** gunicorn runs without `--log-config`, `--log-config-dict` or `--log-config-json`. With one, gunicorn's defaults give the root logger an INFO console handler, so the read lines would already reach the journal; with this module on, they would still print once.
2. **No captured output.** gunicorn does not combine `--capture-output` with an `--error-logfile` that is a file. That combination `dup2`s stdout and stderr into the file (`gunicorn/glogging.py:211-217`, 26.2.0), and then nothing on stdout reaches journald.
3. **No redirect.** The unit does not redirect `StandardOutput=`.

The process listing read on the target (PERF1-LEDGER, 2026-09-10) is `gunicorn --workers 2 --bind 127.0.0.1:5001 app:app`, and there is no `gunicorn.conf.py` in its working directory. So none of those flags is on the command line. But `GUNICORN_CMD_ARGS` and `StandardOutput=` live in the unit, and that is why section 9 reads the unit.

**The gunicorn access log is a documented alternative only, not a proposal.** `--access-logfile -` sends it to stdout and so to journald. Inside `ExecStart=`, every `%` must be doubled (systemd v255 specifiers), and the format must be quoted as one argument:

```
--access-logfile - --access-logformat "%%(t)s %%(m)s %%(U)s %%(s)s %%(B)s %%(L)s"
```

- **Not identifier-free.** `%(U)s` is the path without its query string, and dynamic routes put identifiers in the path: `/radar/api/ticker/NVDA`, or the gym's per-session routes. gunicorn's atoms cannot print a route template, which is why the application logs one instead.
- **Version unverified.** The target's gunicorn version has not been read. Here it is 26.2.0, where a sync worker given `--threads` above 1 becomes gthread. That matters to anyone editing that line.
- **Not paste-ready.** The line above only shows the escaping. It needs reconciling with the real unit before use.

## 6. Rollback

- **Behaviour.** Set `RADAR_BOARD_SHARED_RESULTS=off` in `/root/coc-stats/.env`, the one place it was set, and run `systemctl restart personal_apps_web`. That is a complete behavioural rollback ON THE SERVER: the web builds every board inside the request again (verified by Task 8b's check 7), and no reader touches the store. It is not a complete rollback of the SCREEN -- with the flag off the new client still marks a board stale at 120 s on the page's own clock and offers "not refreshed" with a Retry, and the hub still re-reads a worker-built board once a minute. That is deliberate, it is ruling §5's, and section 4.2 step 2 sets it out. Turning the flag off anywhere else changes nothing while `.env` says on.
- **The producer** can keep running, or be stopped with `systemctl disable --now radar_board_producer`.
  - Left running, it keeps the eight warm boards fresh. That costs about a third of its time: 8 builds of about 5.3 s every 120 s, which is arithmetic from measured builds, not a measurement.
  - If 3.1's lines are in `update_coc.sh`, the next deploy starts it again, so remove those lines first to keep it off.
  - Do not `mask` it while the script still names it, because the script's start line would then fail.
- **The migration.** The downgrade exists, and `flask db downgrade a7c31f0b52d4` drops exactly the two tables. It is not required: with the flag off, nothing reads them.
- **Rolling the code back** to a commit without `b7e3f9c1a2d4`, such as `4221196`: run the downgrade first, while this code is still checked out. Otherwise `update_coc.sh`'s `flask db upgrade` meets a stamp the older code cannot resolve and prints `Can't locate revision identified by 'b7e3f9c1a2d4'`, as `4221196` did in this task's baseline run. flask-migrate exits 1, and `set -e` then stops the script after the checkout and `pip install`. That is before the web restart, with `coc_scheduler`, the notifier and `radar_ingest` still stopped.
- **Telemetry.** Remove `PERSONAL_REQUEST_TIMING_LOG` where it was set (`.env`), then restart the web unit and the producer.
- **Logs.** None of this writes a log file; everything goes to journald. Nothing deletes a log, a journal or a directory. The evidence stays.

## 7. Resource measurements

These come from Task 8 (PERF3-LEDGER, "Measurements"). Every number was taken on `personal_apps_radar_perf3_scale`:

- MySQL 8.0.46 on Windows, with a 2560 MB buffer pool and the three deployed `radar_bucket_sources` indexes;
- 9,269,184 bucket rows, aligned to the wall clock;
- no `radar_posts`, so tone and `lean` do no work and their timings are lower bounds;
- one app user.

MODEL means two OS processes serving the real WSGI app. It never means gunicorn. **The target runs MariaDB 10.11.14: the mechanisms transfer, the seconds do not.**

| What | Measured | Condition |
| --- | --- | --- |
| Producer memory | about 237 MB working set at rest; peak about 518 MB while a build holds its result sets; about 217 MB private | Windows working set; RSS on Linux will differ |
| Web-model worker memory | about 128 MB at start, 132 MB after reads, peak 141 MB; 100 more reads added nothing measurable | same |
| One board build | 12h and 24h: median 5.1-5.3 s, p95 5.3-5.6 s; a fresh producer's first 1h and 4h builds took 12-16 s | one producer |
| Prewarm, from empty store to eight fresh warm boards | 60.7 s | fresh producer |
| Producer duty under load | building for 84-85% of a ten-minute window, about 52% on-demand and 32% warm | one cold request every 10 s |
| Ready read | `read_payload` p95 70-73 ms; over HTTP p95 118-140 ms | **the ready verdict holds with the producer idle.** Reads issued as a build started reached p95 492 ms, max 623 ms. No ready series was taken under load |
| First read of a restarted worker | median 666 ms, p95 769 ms | once per worker per start |
| Cold selection | `pending` in about 40-43 ms (not a board); a board in hand at median 5.8-8.4 s, p95 8.2-9.4 s; 0 of 60 within 2 s | the 2 s goal is UNMET |
| Warm freshness | age when replaced: median 126 s, p95 140-148 s, max 159 s; about 7% of warm samples past 120 s; none past 600 s | the 120 s bound FAILS; the 600 s hard expiry holds |
| Control-row write per admission | +0.7-0.8 ms p95 alone, +1.7 ms with two admitters | not gated |
| Per-account half, 25 marks | worst median 112.5 ms; p95 150-165 ms on the 24h boards | producer stopped |
| A non-Radar request beside two cold boards | flag on: median 23.4 ms, worst 78.7 ms; flag off: median 307 ms, worst 9,522 ms | MODEL |
| The ingest-shaped write | 5.6-5.8 s under the producer's sweep, 6.0-6.3 s alone | MySQL; the producer's reads only |

**Table size per live namespace.** A namespace holds at most 8 warm rows plus 128 on-demand rows (`max_on_demand`). Eviction runs once a minute, oldest request first, and never touches a warm row or a row being built (`board_store.py:419-427`, `787-804`). A stored board is 6-13 KB compressed (PERF2-LEDGER, zlib level 6), so the payload comes to about 136 × 13 KB ≈ 1.8 MB. On top of that is each row's `key_json`, usually well under 1 KB and about 4,000 characters for a maximal selection.

**Retirement.** A namespace nobody has read or produced for 24 h (`RADAR_BOARD_NAMESPACE_RETIRE_SECONDS`, default 86400) is deleted whole by the producer's once-a-minute housekeeping, which runs only while the producer does. Every deploy makes a new namespace, so the table holds the current one plus every namespace used in the previous 24 h. On a day with five deploys, as on 2026-09-08, that is about six namespaces, or about 11 MB at the bound. These are logical bytes. InnoDB's pages, and the space retirement frees inside the tablespace, come on top and are unmeasured on MariaDB.

## 8. Not in this package

- **Threading** (`--threads` on the web unit) is deferred by the ruling. The ledger records only that on gunicorn 26.2.0, `--threads 2` on its own turns a sync worker into gthread.
- **The held index `c4e17b90d3f2`** is not on this branch. The chain is `a7c31f0b52d4 -> b7e3f9c1a2d4`.
- **Capture enablement.** `RADAR_OBSERVATION_CAPTURE_ENABLED` stays unset, and capture builds its boards directly whatever the flag says.
- **Root promotion.** `/radar/` stays the original page, and `/radar/hub/` keeps its own route.
- **B1**, the price-narrative correction on `codex/radar-b1`, is its own carry.
- **Also not proposed:**
  - switching the timing line on;
  - the gunicorn access log;
  - a `BUILD_REVISION` file;
  - any change to `personal_apps_web.service`;
  - the 3.3 ordering, which is a decision.

## 9. Pre-deploy target reads, for the owner to authorize

All of these are read-only.

1. **The deploy script.** `/root/update_coc.sh` in full. It was last read on 2026-09-09, and 3.1 edits it.
2. **The deployed commit.** `git -C /root/coc-stats rev-parse HEAD`, expected to be `4221196`. Also `ls -l /root/coc-stats/BUILD_REVISION`, which must report no such file. `git status` would list an untracked file, but read the path directly.
3. **The web unit.** Run `systemctl cat personal_apps_web` and read these lines:
   - `User=`, `WorkingDirectory=` and `EnvironmentFile=`;
   - `Environment=`, including any `GUNICORN_CMD_ARGS`;
   - `ExecStart=`;
   - `StandardOutput=` and `StandardError=`.

   Reconcile section 2's three lines against them. Also run `systemctl cat radar_ingest`, for the daemon conventions.
4. **gunicorn's version and logging.** Run `/root/coc-stats/venv/bin/gunicorn --version`. Then find out, from the `ExecStart=` line, `GUNICORN_CMD_ARGS` and any `gunicorn.conf.py` in the working directory, whether gunicorn runs with either of these:
   - `--capture-output` with a file `--error-logfile`, which sends stdout to that file instead of journald (`glogging.py:211-217`);
   - a logging configuration (`--log-config`, `--log-config-dict`, `--log-config-json`, or a `logconfig` in a `gunicorn.conf.py`), which would already bring the read lines out.
5. **journald.** `journalctl --disk-usage`, `/etc/systemd/journald.conf`, `/etc/systemd/journald.conf.d/*.conf`, and `ls -d /var/log/journal`.
6. **The deploy `.env`, key names only, never values.** For example: `grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*' /root/coc-stats/.env`. Confirm that:
   - `RADAR_BOARD_SHARED_RESULTS`, `PERSONAL_REQUEST_TIMING_LOG`, `RADAR_BUILD_REVISION` and any `RADAR_BOARD_*` tuning key are absent;
   - `/root/coc-stats/personal_apps/.env` does not exist, because it would be found first.
7. **The migration stamp.** `flask db current`, run from `/root/coc-stats/personal_apps` with the venv: `FLASK_APP=app.py /root/coc-stats/venv/bin/flask db current`. Expect `a7c31f0b52d4`.
8. **Free disk.** `df -h /`, plus the MariaDB data directory's file system if it is separate.
9. **No producer unit yet.** `systemctl list-unit-files 'radar_board_producer*'` should list nothing before installation.

## 10. Open risks, and the open decisions for Codex

**Risks.**

1. **MariaDB has not been measured for the build.** Every timing is MySQL 8.0.46 on Windows. The store and the migration were rehearsed on MariaDB 10.11.14 for correctness (54 checks), but never timed there. A build holds one read transaction for about 5-5.6 s while `radar_ingest` writes. On MySQL that did not slow the write; on MariaDB it is unknown.
2. **gunicorn never ran here.** Every two-worker figure comes from the MODEL.
3. **The 2 s cold goal is unmet.** A cold selection takes a median of about 5.8 s to a board in hand, and the build alone is about 5 s.
4. **The 120 s fresh bound fails.** The refresh target equals the bound. Under load a warm board's age reaches p95 140-148 s and max 159 s, and about 7% of warm samples are stale.
5. **Every deploy is an empty store** (3.3), for any commit to the shared checkout.
6. **A restarted worker's first read** is p95 769 ms. It happens once per worker per start, and every deploy restarts both workers.
7. **The hub has no debounce.** It sends one request per control change, and every cold intermediate becomes an admitted build. **The Discover tab asks for a cold duplicate** of a board that is kept warm under the default segment spelling.
8. **A publish that raises leaves its row `building`** (from Task 3, carried to the runbook). The row stays `building` until its 120 s lease expires and holds one of the 32 queue slots meanwhile. It frees itself, because an expired lease can be reclaimed. If `building` stays above 1 for more than two minutes, in the `board queue` line or in `/radar/api/ops`, read the producer's journal.
9. **`--readiness` answers "not ready" some of the time, even in a healthy steady state** (3.3). It is a gate, not a health probe.
10. **The old board's detail panel takes focus** when a board arrives after a wait, and on a phone it scrolls the reader about 4,219 px. This is new with the pending path and goes to the fix wave.
11. **Every new PERF3 test suite pins the database `personal_apps_radar_perf3`** and skips anywhere else, so after a merge they would skip silently (Task 7). The whole-branch review decides what to do.
12. **The carried lists wait for the whole-branch review.** They are PERF3-LEDGER's carried items from Tasks 1, 3, 5, 6, 7 and 8, plus Task 9b's one failure caused by this branch, which is a test expectation.

**Open decisions for Codex.** Task 8 left six:

1. **The fresh bound.** By the reviewer's arithmetic (not a measurement), refreshing at 100 s would raise the warm share to about 42%, and the total to about 94%, under (f)'s load. Headroom points to a second producer, cheaper builds, or less on-demand work.
2. **Every deploy is an empty store.** Should routine deploys wait for `--readiness` (3.3)? Should warm keys a reader is waiting on jump the `key_hash` order?
3. **The ready target** (p95 ≤ 500 ms): must it hold while the producer is building?
4. **A restarted worker's first read:** accept it, warm the caches on boot, or narrow the target.
5. **The hub's debounce and the Discover duplicate:** a client and key-contract decision.
6. **The per-account rule at 25 marks** beside a building producer.

This package adds three more:

7. **Where the flags live.** This package puts both in `.env` (4.1).
8. **Whether to adopt the readiness-ordered deploy** (3.3).
9. **What the revision covers.** Should it cover only what can change a payload, meaning `personal_apps/` and its dependencies, instead of the repository's `HEAD`?

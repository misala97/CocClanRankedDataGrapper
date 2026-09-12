# CURRENT — PERF3-close review-fix round is CLOSED (2026-09-12)

**Read this block first. Everything below it is historical where it differs.**

| | |
| --- | --- |
| Workspace | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3` (a git worktree) |
| Branch | `codex/radar-perf3` — **not merged, not pushed, not moved** |
| Final HEAD | the commit carrying this handoff |
| Review-fix delta | `12b3873f0c961ecc7dcd7adec81e12e778c60580` (six findings) then `09621fe0061e2a661bafe0a1b95659e3ab7d9104` (the re-review's four) |
| Round base | `6f9534bbbe03021608fc01a0e40e5a7b567722de`; closure base `197be30c2c1028c0b46f8110783f1da5e428d481` |
| Dirty files | none tracked. Untracked: only the two protected preview scripts, `personal_apps/scratchpad/perf3/cleanup_preview.py` and `preview_perf3.py` — never read, executed, edited, deleted or staged by this round |
| Deployed | still `4221196`, migration head `a7c31f0b52d4`. **Nothing was deployed, migrated, configured or restarted.** All target facts are conditional 2026-09-11 records |

**Verdict: closed.** The six blocking findings against `197be30..6f9534b` are
resolved, and so are the four blocking findings the scoped re-review raised
against `6f9534b..12b3873`. Nothing blocking is open.

**Immediate next action: release approval, or Codex's decision on the two
disclosed numbers below.** Not another design slice, and not another review
round. The concrete deploy proposal is `radar-design/perf3-release/
deploy_perf3.sh first|routine FULL_SHA`, prepared and **unexecuted**.

**Evidence, all fresh this round.**

- Registered backend regression, one pass: the seven accepted suites (243,
  unchanged) plus `test_perf3_release_artifacts.py` (9) and
  `test_perf3_migration_recovery_policy.py` (4) — **256 passed in 73.99 s**.
- Registered disposable MariaDB 10.11.14, fresh datadir: **67/67 checks**, up
  from 60/60. Without the opt-in it refuses before creating an engine. Server
  stopped afterwards.
- Loaded ready matrix, corrected: **16/16 critical US/DE × 12h/24h ×
  0/3/10/25-watch cases, n=20 each, 320 samples, all p95 <=500 ms**, worst p95
  122.2 ms. Writes were in flight 21.7–24.7 s of each ~28 s case — 370.1 s
  across a 454 s matrix — and all 66 per-case producer builds landed inside
  their own case's writer window.
- Watched-account initialization, measured as itself: first request 793.4 /
  771.5 ms per worker, subsequent 107.7 / 89.3 ms.
- Freshness defaults unchanged at **120 / 120 / 600 s**.
- Raw artifacts: `.superpowers/sdd/perf3-close-fix-measure/` (ignored, local).
  Full narrative: `PERF3-LEDGER.md`, "Review-fix round, 2026-09-12".

**Two disclosed numbers that are Codex's call, not defects.**

1. 40 of 320 samples (12.5%) answered `stale`, not `ready` — all of
   US/12h/25-watch and all of DE/24h/0-watch, at cache ages 122–140 s against
   the 120 s line. Higher than the ~7% recorded earlier, and caused by this
   harness deliberately holding the producer at its queue cap for the whole
   matrix. Those boards were still served in ~100–120 ms with their true age
   reported. No freshness default was touched to improve it.
2. The once-per-worker watched initialization (~793 ms) remains a disclosed
   exception, consistent with the accepted restart p95 769 ms.

**Still unmet / still conditional.** The `<=2 s` first-result goal (unmet,
non-blocking under the accepted asynchronous contract); the accepted mixed/write
cold p95 16.6 s / max 22.8 s (not re-run); every target fact, because no target
host coordinate or authorized remote surface was available and no bypass was
attempted — re-read them read-only, without printing secret values, immediately
before deploying.

**Two scope facts worth not discovering on deploy day.** `deploy_perf3.sh` has
no interrupted-migration branch: that recovery policy is rehearsed and
unit-tested, but on the target it is still the written procedure in
`PERF3-RELEASE.md`, run by hand with the web units stopped. And none of the
`PERF3_*` path variables may contain whitespace, because the runner word-splits
its command variables on purpose so the tests can inject fakes.

**Boundaries honoured:** no merge, push, deployment, production
migration/configuration/restart, capture enablement, root promotion, threading,
held index, or B1/TE1/history/PERF1 fixture change. The two protected preview
scripts were never touched.

# CURRENT CODEX RULING — 2026-09-12: implement PERF3-close

Read PERF3-CODEX-RULING.md (also appended to CODEX-DECISIONS.md). Architecture accepted; release awaits bounded closure, not another design slice. Keep freshness defaults and disclose the measured stale share. Complete loaded ready/watch measurements, explicit destructive-test target registration, demanded-warm ordering, Discover request alignment, and coherent stopped-web/readiness/recovery release path. Omitted fix-wave review is closed. Fresh Codex frontend check: 31 tests/2 files passed. Reviewed HEAD197be30. Two newly untracked preview scripts are not Codex-owned: preserve them. This ruling/handoff documentation is Codex-owned. No production changes authorized. Prior return below is historical where this notice differs.
# CURRENT — PERF3: reviewed, fixed, and ready to return to Codex (2026-09-12)

Claude implements under the PERF2 ruling; Codex owns planning. **Nothing is
merged, pushed, deployed or configured on the VPS**; the deployed SHA is still
`4221196` and the target's migration head `a7c31f0b52d4`. The release package
is a proposal, not a change.

| | |
| --- | --- |
| Workspace | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3` (a git worktree) |
| Branch | `codex/radar-perf3`, from `afe1246` (`personal_apps/` there is byte-identical to the deployed `4221196`) |
| HEAD | the commit carrying this handoff, on top of `fec7feb` (the re-review's two fixes). The wave is `dba911a..98459d8`, seven commits; `fec7feb` follows it. `git log` is the truth |
| Dirty files | none tracked. Untracked and ignored: the worktree `.env` (names the tests database; never print it), `node_modules`, `static/*/dist` (rebuilt by the fix wave), `.superpowers/` (controller scratch, never committed) |
| Binding | `PERF2-CODEX-RULING.md`; plan `PERF3-PLAN.md` (four amendments); ledger `PERF3-LEDGER.md`; release package `PERF3-RELEASE.md` |
| Controller scratch | `.superpowers/sdd/`: task briefs, implementer reports 1–9b, the whole-branch review (`review-whole-branch-report.md`), the fix wave's report (`fix-wave-report.md`), `progress.md` |
| Tests DB | `personal_apps_radar_perf3`: stamp `b7e3f9c1a2d4`; te1 clone with 29 FKs and gym data; no radar posts; its board data ends 2026-09-01. The suites no longer pin its NAME — see "the database guard" below |
| Scale DB | `personal_apps_radar_perf3_scale`: stamp `b7e3f9c1a2d4`, aligned forward by Task 8 to 2026-09-13 12:00 UTC. Re-run `scratchpad/perf3/align_scale_fixture.py` through `scale_env.py` before any timing or preview after that |
| MariaDB | the portable 10.11.14 rehearsal server is STOPPED. The restart command is in the ledger. Needed only if the store or migration changes |

| Task | State | Commits |
| --- | --- | --- |
| 1 key + namespace | complete | `a5017e7`, `20429d0`, `a188bb3` |
| 2 store + migration | complete; MariaDB rehearsal 54/54 | `0eba6a4`, `c2d0ca9`, `c199d06` |
| 3 producer | complete | `fd810c1`, `55f0d7f` (+ `6752492`) |
| 4 read path, flag, API | complete | `9097621`, `6752492` |
| 5 old board client | complete after five fix rounds | `0ed59e2`, `2b90885`, `17128b8`, `52af950`, `27738b2` |
| 6 hub client | complete after one fix round | `103b8ba`, `d429378` |
| 7 parity | complete | `29cc2ac` |
| 8 scale verification + browser | reviewed; six decisions go to Codex | `9fa42aa`, `6ecba5a`; ledger `7dc682e`, `c423b33` |
| 9a request-timing line | approved by a read-only review | `e3aedfb`, `3062ed9` |
| 9b suites, release package | done | `ed96885` |
| whole-branch review | done: **ready to return with fixes, no Critical** | `dba911a` (ledger section) |
| **fix wave** | **done**: every "fix before the return" item closed | `267811d`, `21c3591`, `a1c5a9e`, `add355d`, `27fb905`, `360066f`, `98459d8` |
| the wave's re-review | **done**, narrow by the owner's quota decision: three commits of eight read; two Important, both fixed | `fec7feb`, and the commit carrying this handoff |

**Immediate next action.**

**The return to Codex** -- the exact SHA, this ledger, `PERF3-RELEASE.md`
and the local preview below. Nothing else is owed by this session. The one
piece of work on this branch that was never independently reviewed is five of
the fix wave's eight commits: the owner scoped the re-review to the three that
carry behavioural risk because the weekly quota was nearly gone, and the
ledger's "Narrow re-review of the fix wave" section records exactly which
commits were read and which were not. Codex decides whether that gap is worth
closing before acting.

Nothing is deployed, and nothing in the package is authorized.

**What the fix wave changed** (ledger, "Fix wave, 2026-09-12"; full report at
`.superpowers/sdd/fix-wave-report.md`):

- the branch's one red test, which asserted a property of the whole migration
  chain rather than of its own step;
- an arriving board no longer takes focus from a reader who chose nothing
  (measured in a browser: 4,402 px of scroll at 390x844 before, 0 after, with
  the reader's own click still moving focus), and a pending shell no longer
  reports zeroes it never measured;
- a parked board says whose failure the reader is looking at, in both clients;
- nothing auto-resends a failed board request on the flag-off path, and the
  star's refetch, Retry and the expiry refetch no longer add a build on top of
  one that is already running;
- the hub debounces a burst of control changes to one request, on the old
  board's own 250 ms, applied before the selection becomes a query key;
- a mistyped or nonsensical tuning variable can no longer 500 the flag-off
  path, and the producer refuses to start on one;
- the producer side of cross-generation isolation is pinned by four tests, the
  parity suite's pre-split check discriminates, and `TESTING` is restored;
- **the database guard, branch-wide** — see below;
- two release sentences, a fourth plan amendment, and three small guards.

**The database guard (new, and it changes how the suites are run).**
`personal_apps/tests/radar_disposable.py`. The six radar suites no longer pin a
database NAME. They skip only on `personal_apps` (both the dev and the deployed
name) and `coc_stats`, **fail** where the bound database is disposable but does
not carry the tables they need, and run everywhere else. So:

- point `PERSONAL_DB_NAME` at any disposable clone and they run;
- `test_radar_projection_migration.py`'s five long-standing silent skips are
  gone — it no longer pins `personal_apps_radar_wt`, and both migration suites
  can run in one pass;
- both migration suites now restore the schema to `head`, not to their own
  revision, so neither leaves the database short for whatever runs next.

**Suite results at `98459d8`** (all run after that commit; `fec7feb` then re-ran the two migration suites with the store suite -- 76 passed -- and the limits tests, 17 passed):

- **The seven focused backend suites, one pass**, on
  `personal_apps_radar_perf3`: `cd personal_apps && PYTHONPATH=. py -3.12 -m
  pytest tests/test_radar_board_store.py tests/test_radar_board_producer.py
  tests/test_radar_board_shared_api.py tests/test_radar_board_parity.py
  tests/test_radar_board_results_migration.py tests/test_radar_activity.py
  tests/test_radar_projection_migration.py -q -p no:cacheprovider` →
  **238 passed** in 47.8 s.
- **Frontend:** radar vitest **700/700** (681 before the wave), root vitest
  **403/403**, `npx tsc --noEmit` clean, `npm run build` clean.
- **The whole backend suite was NOT re-run.** Task 9b classified it at
  `3062ed9`: 6 failed, 2,956 passed, 5 skipped. Of those, the single
  branch-caused failure is fixed by `267811d` and the five skips are gone with
  the guard. The other five failures are pre-existing and each fails
  identically at `4221196`: `test_diagnose_extractor_feedback.py`'s read-only
  run, `test_radar_trial_writes.py`'s lexicon label, and three
  `test_radar_yahoo.py::test_daily_closes_*` whose pinned dates fell out of the
  provider's window on 2026-09-09. Expect **5 failures and 0 skips** from a
  fresh whole-suite run; nobody has taken one since.

**The release package** (`PERF3-RELEASE.md`, a proposal):

- Migration `b7e3f9c1a2d4`: additive, run by the upgrade `update_coc.sh` already does.
- `perf3-release/radar_board_producer.service`: not installed. Three of its lines must be reconciled against the unread `personal_apps_web.service`.
- Two lines for `update_coc.sh`, added only after the unit is installed, because the script runs under `set -e`.
- No `BUILD_REVISION` file on the VPS.
- First rollout: deploy with the flag off, start the producer, and wait for `--readiness` to exit 0. Then set `RADAR_BOARD_SHARED_RESULTS=on` in `/root/coc-stats/.env`, restart the web unit, and verify through `/radar/api/ops`. `.env` is the one place for both flags, because `app.py` calls `load_dotenv(override=True)`.
- Telemetry prepared, and off.
- Rollback: the flag off in `.env`, then a web restart. Complete on the SERVER; the client still marks a board stale at 120 s and the hub still re-reads once a minute (§4.2 step 2, and the plan's fourth amendment).
- Resource numbers, the target reads the owner must authorize, and the open risks and nine decisions for Codex.

**The local preview**, for the return. Both processes must go through the
launcher, or the producer binds the TESTS database while the server binds the
SCALE one and they never share a board:

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3/personal_apps
py -3.12 scratchpad/perf3/scale_env.py run_radar_board_producer.py                  # terminal 1
py -3.12 scratchpad/perf3/scale_env.py scratchpad/perf3/serve_perf3.py --port 5071  # terminal 2
```

Then open `http://127.0.0.1:5071/radar/` and `/radar/hub/`. `scale_env` turns
the flag on and pins one revision for both processes. The pages need a signed-in
session, as any local run does. Port 5001 is the owner's own instance.

For the client alone, with no database and no producer, the fix wave's browser
harness serves the real shell, assets and bundle against a stubbed API:

```
cd personal_apps && py -3.12 scratchpad/perf3/browser_focus_check.py
```

**Owner decisions in force.** One implementation worker at a time, a separate
review per task, and full proof runs ("do it properly"). The stopping rule for
Tasks 5 and 6 is recorded in the ledger.

**Open decisions for Codex.** Task 8's six are in the ledger's Task 8 section;
`PERF3-RELEASE.md` §10 lists nine. The whole-branch review's "Carry to Codex"
list is in the ledger's review section and the fix wave did not touch any of
it — in particular the 120 s fresh bound, which FAILS by construction and whose
remedies are capacity decisions.

**Traps.**

- `app.py` loads `.env` with `override=True`. An environment variable therefore cannot pick the database, and every process that imports `app` takes every key in that file over its unit's environment.
  - Scale scripts go through `scratchpad/perf3/scale_env.py`, which also pins the build revision (`PERF3_REVISION`) and patches the fixture's placeholder subreddit names.
  - The same rule decides where the release's flags live.
- `test_radar_activity.py` and the two migration suites drop and recreate radar tables in the bound database each time they run, and now do so wherever the guard lets them. Both migration suites end at `head`.
- The three `test_radar_yahoo.py` failures now fail on every machine.
- Never print `.env`. An earlier listing put real credentials into a transcript, and the owner was told.

**Protected:**

- `personal_apps_radar_perf1` (PERF1's evidence, stamp `c4e17b90d3f2`) and the dev database `personal_apps`;
- the `radar-perf2` worktree, with Codex's uncommitted edits there, and every other worktree;
- the planning checkout `C:/Users/michi/Desktop/CodingStuff` and its dirty files;
- every `.env`;
- `.superpowers/`, which is never committed;
- the raw PERF2 suite log in session `db04c240`'s scratchpad, which was read but not moved.

No deployment carry has been executed; the release package is the proposal for
them.

---

# CURRENT — Codex accepted PERF2 with amendments; implement PERF3

Read the latest PERF2 ruling appended to CODEX-DECISIONS.md. Full local PERF3 implementation is authorized in a new isolated worktree; no production changes. Eight warm keys initially, explicit asynchronous pending and visible stale states in both clients, separate producer process, generation-safe cache and fair bounded queue. Index and threading remain deferred. Product performance acceptance remains open. Reviewed afe1246, 21 commits from 4221196; Codex's only fresh executable check reproduced the segment-key collision without database access. These decisions/handoff edits are intentional Codex-owned changes. Historical returns below are superseded where this ruling differs.
# Latest Codex ruling — PERF1 reviewed, performance acceptance OPEN

Read the appended PERF1 ruling in CODEX-DECISIONS.md. It supersedes the current-dispatch conclusions below. Index deployment is held; threading and telemetry are preparation only. Next: PERF2 shared background-result design and disposable feasibility proof, with an explicit freshness and cold-miss contract. Correct the retracted concurrency claims and inventory reproducible evidence artifacts. No production changes authorized. Reviewed HEAD 691f33a (12 commits from 4221196); these decision/handoff edits are Codex-owned. No fresh benchmark or test run by Codex.
# PERF2 RETURN — design and feasibility, for Codex's review, 2026-09-10

Supersedes the dispatch below. **Nothing is deployed, merged or pushed. No
migration, no service change, no target contact, no capture, no root
promotion.** `git status` clean; `personal_apps/` byte-identical to `4221196`.

| | |
| --- | --- |
| Branch / HEAD | `codex/radar-perf2` at the tip listed by `git log` |
| Base | `4221196`, the deployed SHA |
| Deliverables | `PERF2-PLAN.md` (design + spike), `PERF2-LEDGER.md` (every number), `PERF2-TELEMETRY.md` (access log), `perf2-spike/` (disposable), `perf1-bench/` (PERF1's evidence, now reachable) |
| Review | one independent read-only reviewer, findings and disposition in the ledger |

## The answer, in one table

| Question the ruling asked | Measured | Verdict |
| --- | --- | --- |
| Do two independent processes reuse one published result? | two `subprocess` readers, identical digests, `fence=1` | **YES** |
| Warm read | **33.5 ms** median, 37.6 ms p95 (target 500 ms) | **PASS**, 13x |
| First-ever missing result | `pending` in **8.8 ms** — *not a board*; a board **6,901 ms** later | **FAILS** the 2 s target by 3.5x |
| Can one producer keep the warm set fresh? | 16 keys in **65.8 s** warm; 120 s cadence fits at 55% duty | **YES, on a quiet database** |
| Do arbitrary filters keep exact semantics? | **12/12 payloads byte-identical**, ops blocks included | **YES** |
| Is failure bounded? | lease reclaim 29.8 s; overtaken publish affects **0 rows**; parked backoff 30-900 s | **YES** |
| Do private watches stay isolated? | no account data in the blob, structurally and by test | **YES** |
| Is freshness truthful? | age exact to the millisecond at all three thresholds | **YES in the payload, NO on the screen** |

## The three things Codex should decide first

**1. The cold contract, and it is the whole product question.** An unwarmed
selection costs **6.9 s** end to end. Moving the build off the request path
does not shorten it — it only stops it occupying a web worker. That leaves
**1.1 s of margin against the client's own 8,000 ms abort**, so an unwarmed
board on a busier database dies in the browser. Either the warm set covers
what people actually ask for, or the client learns to poll, or the 2 s target
moves. **Nobody knows which boards people ask for**, because the box has no
request log — which is what `PERF2-TELEMETRY.md` is for. The warm sixteen are
an assumption.

**2. The `pending` state is a precondition, not a refinement.** The current
client has no concept of it, so it renders the board's genuine empty state —
*"Nothing cleared the bar in this window. Try a longer window"* — for a board
that was never built, under a header stamped with a time. Absent presented as
empty, with a timestamp: the same class of defect as stale presented as fresh.
Screenshot: `perf2-spike/shots/s8-unwarmed.png`. A stale board likewise
renders with `stale: true` and `age_seconds` in the payload and **no sign of
either on screen**.

**3. `--threads` is now the largest measured number in this workstream, and it
is not PERF2's.** In a **model** of the two configurations — gunicorn does not
run on Windows and there is no WSL, so this is not gunicorn — a cheap
**non-Radar** request during two board builds took **7,602 ms** under two sync
processes and **9 ms** under two threaded ones. Two people opening Radar take
down the gym tracker and the login page for seven seconds. That is a
service-configuration change nobody has authorized, and PERF2 does not depend
on it; it is stated here because it is the cheapest large win on the table and
it stands independently of everything else in this return.

## What the design got wrong, found by measuring it

Part I has been corrected in place rather than annotated. Four of its own
statements were wrong:

- **The retry rule had no backoff at all.** "Stops being retried until a
  reader asks again, which resets `attempts`" — readers poll constantly.
  Measured: **360 polls, 360 rebuilds** of a broken key, backoff never past
  30 s. Replaced with a park timer: same run, **6 attempts**.
- **`key_json VARCHAR(1024)` would 500 a legal request**, and with strict mode
  off would serve a **wrong board**: `parse_query` bounds the source count but
  not name length, so a legal URL produces a **3,958-character** key. `TEXT`
  now, plus a round-trip assert. Found by the reviewer, reproduced
  independently. **The only wrong-board vector in the design.**
- **`MAX_PENDING = 32` is not a queue bound**; the real ceiling is the row cap.
- **Two of five key-normalization predictions were backwards.**

## What was not measured, and cannot be from here

gunicorn itself; MariaDB; a real ingest cycle beside the producer; the
target's own end-to-end build; the target's request volume — `ssh` is refused
by this session's command classifier, so nginx's existing access log could not
be counted. The lean sort could not test the sort-before-limit contract
because **0 of 50 fixture rows carry a tone**, so the contract was proven on
`sort=mentions` instead, where membership moved 4 of 50.

## The suite, and a warning about the fixture

`pytest tests -q`, whole, no `-x`: **2,706 tests, `17 failed, 2650 passed,
9 skipped, 30 errors`, 38 minutes.** None attributable to this branch, and
that is checkable: **`git diff 4221196..HEAD -- personal_apps/` is empty.**
The failures name their own cause — *"the dev database needs at least one
exercise"* — because this worktree points at a radar fixture with no gym data.
Two figures quoted earlier in this workstream were partial and should not be
reused: the spike's own `-x` run stopped at 72 tests, and `PERF1-LEDGER.md`
says 227.

**One failure is a warning rather than noise.** `personal_apps_radar_perf1` is
stamped `alembic_version = c4e17b90d3f2` — the **held** migration — because
PERF1 ran `flask db upgrade` against it, and this branch does not carry that
revision, so alembic cannot resolve the stamp. That is the third place the
held change had to be found and dealt with here: the physical index still on
the fixture (which contaminated this spike's first pass until S9 caught it),
this stamp, and the branch lineage — which is why PERF2 is based on the
deployed SHA. **Production is untouched and at `a7c31f0b52d4`.** The fixture's
stamp is left as it is, because resetting it is a write nobody asked for; the
next person to use that fixture with a branch lacking `c4e17b90d3f2` needs to
know.

## Still owed, and it is small

The adopted `sort sources` normalization is ruled but not implemented in the
spike. `producer_revision` is written and never read. Both are named in
Part I; neither changes a number in this return.

# Current dispatch — PERF2 design and feasibility, 2026-09-10

Supersedes every status and next-action statement below except Codex's notice
above, which governs. **Performance acceptance is OPEN and still precedes B2.**

| Fact | Value |
| --- | --- |
| Workspace | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf2` |
| Branch | `codex/radar-perf2` |
| Base | **`4221196`** — the deployed SHA, read from the target |
| Live record | `PERF2-PLAN.md`, `PERF2-LEDGER.md` in this workspace |
| Binding ruling | `PERF1-CODEX-RULING.md`, also appended to `CODEX-DECISIONS.md` |

**This branch deliberately carries no PERF1 code.** It is based on the deployed
SHA and brings forward PERF1's *documentation* only, so the held migration
`c4e17b90d3f2` and the in-process single-flight cannot reach a release
candidate by way of a routine `flask db upgrade`. `codex/radar-perf1` at
`691f33a` is preserved untouched as the evidence branch. `codex/radar-b1` at
`6c63959` is likewise untouched; its price-narrative correction remains its own
deployment carry.

**PERF1's benchmark scripts are now reachable.** They lived only in an
ephemeral session scratchpad, which is why the Git delta did not contain them.
They are carried into `radar-design/perf1-bench/` with an inventory and their
prerequisites; see `perf1-bench/README.md`.

---

# PERF1 — closed as an investigation, and corrected, 2026-09-10

Codex accepted PERF1 as a completed investigation with a useful negative
result, and did **not** accept product performance. This section replaces the
one that stood here, which led with a concurrency conclusion that is retracted.

## What is retracted

**"The bottleneck is two readers building the same board at once" is
withdrawn.** The `7.85s / 7.92s` pair that motivated it was two THREADS in one
process. Production runs `gunicorn --workers 2` with no `--threads`: two
single-threaded SYNC processes (`NLWP=1` on both, read from the target). Two
concurrent readers there are in two PROCESSES, which do not share a GIL, so
the pair is *cheaper* in production than that measurement — and the in-process
single-flight cannot fire there at all.

That measurement is local evidence about threads. It is **not** a production
outcome and **not** proof of the owner's timeout. The cause of the owner's
timeout remains unidentified, and the target has no latency telemetry with
which to identify it.

## What survives, with its limits stated

Measured on `personal_apps_radar_perf1` — 9,272,064 rows, within 0.7% of the
target's `radar_bucket_sources` — on **MySQL 8.0.46** with the buffer pool
raised to the target's 2560 MB. The target runs **MariaDB 10.11.14**. Ratios
and mechanisms transfer; seconds do not.

| 24h, All companies, one reader, n=20 | median | p95 |
| --- | --- | --- |
| deployed code | 5.38s | 5.72s |
| with the held index `c4e17b90d3f2` | **4.50s** | **4.72s** |

- The index is worth **~0.9s per build**, repeatably, and payload parity is
  identical at 4h, 12h and 24h.
- It costs **639 MB** (net ~181 MB if the redundant `ix_radar_bucket_sources_start`
  goes too, which is measured but not attempted) and **+50%** on ONE
  representative bulk `UPDATE` of an indexed column — not a measured +50% on
  the whole scoring pass.
- The pass-one aggregate is roughly 40% of the build. **A 4.5-second build is
  still a 4.5-second build**, against a ≤2s cold target and an 8.00s client
  abort (`static/radar/src/api.ts`).
- The 59-second index build and its `ALGORITHM=INPLACE, LOCK=NONE` are local.
  `PREPARE` on the target proved the statement parses on MariaDB; it proved
  nothing about online-DDL duration, locking or concurrent writers there.
- Total radar data (3871 MB) exceeding the target's 2500 MB pool is a fact
  about total size. It does **not** establish that the active working set does
  not fit.

## What was never measured

- **The target's own end-to-end build.** Running code on the target
  (`python -c` over ssh) is refused by the session's command classifier and
  was not routed around. Plain ssh reads, `mariadb -e`, `EXPLAIN` and
  `PREPARE` all work and were used.
- **Any production latency at all.** nginx logs no `$request_time`, gunicorn
  runs with no access log, the slow query log is OFF at `long_query_time` 10s,
  and `performance_schema` is OFF.
- **Cross-worker duplication**, which is what PERF2 addresses.

## Codex's disposition

| | |
| --- | --- |
| Index `c4e17b90d3f2` | **HELD.** Not to ship for a marginal read gain with unquantified ingest cost. Do not drop `ix_radar_bucket_sources_start`. |
| In-process single-flight | Not approved as a general solution; the shared path replaces it. Not to be polished further. |
| `--threads N` on the unit | Local evaluation approved as a candidate. **No service change.** |
| Latency telemetry | Bounded gunicorn access-log proposal, prepared and locally verified only. **No live activation.** |
| Product performance acceptance | **OPEN.** |

Nothing on the target was changed by PERF1 — no schema, no configuration, no
restart, no code.

**`RELEASE-RECORD-VC1.md` says the deployed SHA is `1f8016c`. It is stale.**
The target is at `4221196`.

---

# Previous dispatch — VC1 deployed, 2026-09-10

This section supersedes historical status/next-action/deploy statements below.
Workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate.
Branch codex/radar-release-candidate. **Production is now `1f8016c`**, merged
from candidate `31ae58a` plus the documentation-only ruling commit `8e3fd00`.
Migration head **unchanged at a7c31f0b52d4** -- this update added no migration.
Capture remains off and `/radar/` remains the original route.

**RELEASE-RECORD-VC1.md is the full account of the deployment**, including the
89-second second outage caused by operator error and how it was recovered. The
first release's record is RELEASE-RECORD.md and remains accurate for that one.

**`origin/main` sits ahead of the deployed SHA by documentation commits, and
that is expected.** The record and this handoff were written after the deploy
and pushed after it; they change nothing the server runs. Compare the deployed
checkout against the last commit that touches `personal_apps/`, not against the
tip of `main`, before concluding the target has drifted.

## What is live

The corrected Human chatter: a platform count with the concrete feeds behind
it, a tone percentage with a bar over the directional sample, compact rows,
deliberate column proportions, and sortable columns with a stacked-layout
selector. Verified on real production rows -- all 50 carry `activity_sources`,
and the six sampled show 2-4 feeds talking out of 34-36 looked at, which is the
defect the owner rejected. Production has real directional tone samples, so the
percentage and bar render on live data rather than only on the fixture.

## Immediate next action

**The owner's own authenticated look at the deployed hub**, at
`https://mgemmel.viewdns.net/radar/hub/`. Every check in the record is
unauthenticated or server-side; no owner session was minted and none should be.

After that, historical analysis is the next NEW feature, ahead of portfolio and
news. Capture enablement and root promotion remain separate, untaken decisions.

## Two honesty defects found on the live board, 2026-09-10

Both are the same mistake VC1 fixed in the tone column: **a deliberate
suppression rendered as an absence.** Neither is caused by the release; both
predate it. Neither has been changed — they alter what the board says and that
is the owner's call.

**1. "Move unknown" on every row while the market is closed.**
`leaderboard._assemble` sets `move = moves.get(...) if quote.score_eligible
else None`. When the exchange is shut, `score_eligible` is False, so the move
is discarded — and the row prints *Move unknown*. Measured live at 00:01 UTC
with the session `closed`: **50 of 50 rows had a price and 0 had a move**,
while `quotes.moves_for` returned the moves perfectly well for the same window
(META +6.55%, GOOGL −2.28%, PL −3.31%). The number is known; the row throws it
away and then calls it unknown.

The gate is right for the DIVERGENCE score — a frozen tape reporting no
movement while mentions explode is an artifact, and `_assemble` says so. But
divergence is already gated separately (`quote.score_eligible and move is not
None and mention_z is not None`), so the move could be carried and displayed
with its session context without weakening that. The fix is small; what it
should SAY when closed is a design decision.

**2. "wording" on a mention the encoder has not reached yet.**
`detail_panel._judged_by` returns `'lexicon'` whenever only the local float has
scored a mention — and the lexicon scores every mention at ingest. So the
`judged_by: null` case in the contract is unreachable in practice, and a
mention waiting for the 10-minute sentiment pass is attributed to the wording
score rather than shown as unjudged. Measured: 100% of mentions under 10
minutes old are unjudged, 0.0% beyond 40 minutes; 15,463 encoder against 181
wording over 24 hours. Nothing is broken — the label is just wrong about why.

## Named follow-ups, none of them blocking

- Duplicate desktop cell labels on Activity and Watching -- the same defect
  Chatter's item D fixed, deferred by ruling to those pages' next UI pass.
- Watching's tone/source presentation, with a populated mockup first.
- The zero-feed question in legacy `sources` / `venues` / breadth filtering,
  which is a ranking decision and not a display one.
- ~~OT1: the retired encoder trial's watchdog~~ **DONE 2026-09-10** on the
  owner's direct instruction. Timer, service, unit files and `/root/trial-audit`
  are gone; 1,439 pointless invocations a day with them. OT1-RECORD.md has the
  account, the archive location and the reversal. **The `radar_judge_trial` row
  stays**: with no row, `judge_config._encoder_or_none` raises `ConfigError`
  and the ingest daemon fails at startup. Making a missing row survivable is a
  small code change and the prerequisite for deleting it.
- Inert generic flex declarations on Chatter cells below 700px -- clean them
  when that CSS is next edited, per the Eighth return.

## Verified state

Assert the disposable test database before any backend test or migration; the
worktree `.env` names `personal_apps_radar_te1`, the schema-preserving rebuild
carrying all 29 foreign keys:

```
cd personal_apps && PYTHONPATH=. py -3.12 -c "from app import app; from extensions import db; app.app_context().push(); print(db.engine.url.database)"
```

The preview is still runnable and still useful for fixture edge cases the live
board does not currently show:

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate/personal_apps
PYTHONPATH=. py -3.12 scratchpad/vc1_serve.py 5071
```

Protected: all .env/credentials/backups/private fixtures, unrelated planning
checkout research changes, and the foundations worktree. No staging all files.

---

## Historical handoff preserved for evidence
# Radar current handoff

Updated 2026-09-09, by Claude, during implementation. Supersedes the planning-stage handoff.

## Roles and next action

Codex designs and plans; Claude implements and verifies. **Release 0 (F1-F3) and Release 1 (H1-H4)
are both built, each task independently reviewed, and every finding resolved.** Codex then reviewed
the return (radar-design/CODEX-DECISIONS.md, carried in as 243db22) and set two follow-ups, **R1 and
R2, both complete**; it then ruled on the second return (carried in as 3c93ad8) and set **R3, also
complete**.

**Immediate next action: Codex reviews the P2 release package**, then the owner grants the access
three gates need. R3, P1 and the local half of P2 are done; the release itself is not authorized.

**There is a second worktree now.** `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate`
holds `codex/radar-release-candidate`, the isolated release candidate built off fetched `origin/main`
with the 38 release commits transplanted and the 12 unpublished research commits excluded. **The P2
work lives there, not on this branch**, because Codex required the foundations branch and worktree to
stay unchanged. RELEASE-RUNBOOK.md and the P2 ledger evidence exist only on the candidate.

The owner has said they would rather compare the two interfaces on the VPS with live data than
locally, so local visual approval is not a prerequisite to preparing the side-by-side deployment.
The visual review stays open until it is actually performed. Do not re-dispatch anything the
ledgers mark complete.

The release sequence in CODEX-DECISIONS.md section C is **planning, not authorization**: merging,
deploying, running a migration outside the disposable clone, enabling capture and promoting
`/radar/hub/` to `/radar/` all remain untaken decisions.

## Verified workspace state

Implementation worktree: `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations`
Branch: `codex/radar-foundations`, branched from `dev_personal` at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD: the tip of `codex/radar-foundations`. Verify with `git rev-parse --short HEAD` --
this file cannot name the commit that carries it. The table below lists every commit before it.
Planning checkout: `C:/Users/michi/Desktop/CodingStuff` (branch dev_personal, unchanged)

A second worktree exists at `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-baseline-probe`,
detached at 7a9ffe4. It was created only to prove three `test_radar_ingest.py` failures predate this
work. **It is disposable** -- `git worktree remove` it when convenient.

Commits on this branch, oldest first:

| Commit | What |
| --- | --- |
| 9e8d446 | the planning package, carried in and committed |
| e4a27e9 | F1 ingest-run recording |
| d79da27 | F1 review fixes |
| 3d22902 | F2 board archive |
| 328074a | F3 activity/ops APIs |
| 236f862 | F2 review fixes |
| a178ba6 | F3 review fixes |
| ed62b32 | ledgers |
| 92da7c8 | H1 hub shell |
| 765f4f6 | handoff |
| 0f3767b | H2 chatter, research, search + the H1 review's fixes |
| c88266b | H3 watching and overview |
| 8864189 | H4 activity and administration |
| 39e8042 | the H2 and H3/H4 reviews' fixes |
| 1e30096 | ledgers and this handoff |
| 07e7cef | CODEX-RETURN.md, the entrypoint back to Codex |
| b78b5d2 | the handoff names the commits that carry it |
| 243db22 | Codex's rulings (CODEX-DECISIONS.md), carried into this worktree |
| e25f223 | R1: unchecking the last feed selected other feeds instead of refusing |
| ffbdd37 | R2: the activity endpoint measured instead of guessed at |
| 917cb15 | the R1 review's fixes |
| 08c5b47 | the R2 review's blocking finding: the envelope shape was not production's |
| 3c2eb77 | ledgers name 08c5b47 |
| 78b17c6 | the jsdom navigation flake in Hub.test.tsx |
| 8c50cda | hub ledger records R1 and the flake |
| 8bbd57e | the R2 re-review: both scheduling models measured, the recommendation corrected |
| 482d954 / b480116 | documents name their commits |
| 3c93ad8 | Codex's binding ruling on the second return, carried in |
| c4e0455 | **R3** typed activity counters + migration a7c31f0b52d4 |
| 278625c | R3 acceptance evidence, and two fixtures that had outlived their schema |
| cfe39e7 | the R3 review's findings |
| c6efdd5 | R3 in the ledgers, handoff and return |
| 140267f | Codex accepts R3 and sets the release-preparation task |
| 01b056d | **P1** both migrations rehearsed on MariaDB 10.11.14 |
| 5664a83 / 8f78850 | the release package, then its review's findings |
| (candidate) | **P2** on `codex/radar-release-candidate`, a separate branch and worktree |

Working tree is clean. Verify with `git status --porcelain`; if it is not, the difference is
somebody else's and belongs to them.

### Untracked and protected

`.env` in the worktree root is untracked and **must stay untracked**. It is a copy of the
repository-root `.env` with one line changed: `PERSONAL_DB_NAME="personal_apps_radar_wt"`.

`personal_apps/static/*/dist/` is untracked build output. A fresh worktree has none, and three
`test_radar_api.py` tests fail until `npm run build` has run. That is a workspace prerequisite, not
a defect.

In the planning checkout, `personal_apps/scripts/discover_telegram_sources.py` and
`personal_apps/telegram_candidates.json` are modified, and many untracked probes, datasets and
scratch scripts exist. **None of it was touched.** Nothing was staged there beyond reading.

## The database

`personal_apps_radar_wt` on the local MySQL 8.0.46: a clone of the local `personal_apps` dev
database (43 base tables, 0 views, 456 MB, every row count equal at clone time). It is disposable.

**It is NOT schema-identical to production.** It carries **none** of the 29 foreign keys that
production and local dev both have -- the likely signature of `CREATE TABLE ... LIKE`. Two
`test_radar_watch` tests fail here for that reason alone and pass against production's schema;
see FOUNDATIONS-LEDGER.md, "P2-close: the two watch-integrity failures". Any work that touches
cascade or referential behaviour needs a clone rebuilt from the verified nightly backup.

Assert it before any backend test or migration:

```
cd personal_apps && PYTHONPATH=. py -3.12 -c "from app import app; from extensions import db; app.app_context().push(); print(db.engine.url.database)"
```

It must print `personal_apps_radar_wt`. If it prints `personal_apps`, the worktree `.env` is missing
or wrong -- stop, because migrations run there would hit the shared dev database.

Production is MariaDB; local is MySQL. Keep DDL portable and do not rely on MySQL-only JSON
behaviour. The migration head on this branch is **a7c31f0b52d4** (R3's projection columns),
following d82f9afb5898. Single head. MariaDB compatibility is a rollout rehearsal, not
something local MySQL success establishes.

## Tests and their results

Recorded at cfe39e7, all against the disposable database:

- `npm test`: **403 passed** (root config, 32 files) and **438 passed** (radar config).
  The radar count rose from 419 by R1's 19 new tests.
- `npm run build`: exit 0. Emits `hub-*.js` and `hub-*.css` beside `board-*.js`.
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py`: **85 passed**.
- `pytest tests/test_radar_hub_page.py tests/test_radar_api.py tests/test_radar_watch_api.py tests/test_gym_routes_smoke.py`: **135 passed**.
- R1: `npx vitest run -c vite.radar.config.ts static/radar/src/hub/`: **171 passed**, 12 files.
  Mutation-checked -- reverting only the reducer fails 6 of them.
- R3: `pytest` over the seven radar suites (activity, observations, operations_api,
  activity_projection, projection_migration, api, daemon): **253 passed**.
- R3 acceptance, 30-day upper-bound fixture: peak incremental Python heap **0.8 MiB**
  (target <=16), median endpoint **390 ms** (target <=500), four concurrent 30-day reads
  **0 errors** with RSS 135 -> 136 MiB. Repeatable via `scratchpad/bench_activity.py`.
- P1: `scratchpad/rehearse_mariadb.py` against **MariaDB 10.11.14** -- the target's own
  version, not MySQL -- **39 checks, all passing**. Needs a disposable MariaDB on port 3399;
  this machine has none installed, so one is fetched as a portable server into the
  scratchpad. See FOUNDATIONS-LEDGER.md "P1 rehearsal" for how to repeat it.
- The radar frontend suite was FLAKY and is no longer: `Hub.test.tsx` let a real navigation reach
  jsdom, which throws on a timer and failed a random neighbouring test about one run in six. Fixed
  in 78b17c6; four consecutive clean `npm test` runs since.
- R2 benchmark: `PYTHONPATH=. py -3.12 scratchpad/bench_activity.py`, which asserts the disposable
  database by name, seeds into 2019 and removes its rows afterwards. Results in FOUNDATIONS-LEDGER.md.
- Browser: 13 captures across all six pages and the recovery view at 1440x1000, 768x1024 and
  390x844, plus a separate keyboard and live-endpoint pass over all five destinations at all three
  widths. No document horizontal scroll, no console or page errors anywhere; the skip link is the
  first tab stop, carries a visible ring and focuses the page without replacing it.
  `reports/hub/EVIDENCE.md` records which pixels are real data and which are the one labelled
  fixture. Two more for R1: `reports/hub/hub-feeds-unlocked-1440.png` and
  `hub-feeds-locked-1440.png`. A forced real click on the locked checkbox left it checked, showed
  the floor note once, and issued zero `/radar/api/board` requests.

**Known environment failure, not caused by this work.** `tests/test_radar_ingest.py` fails three
tests on every run after the first against a persistent database
(`test_an_empty_healthy_source_stays_ok_without_database_artifacts`,
`test_fresh_mentions_carry_the_local_model_version`, `test_a_parent_context_comment_keeps_its_ticker`).
Its `_wipe()` helper does not delete `RadarMention` rows for its own ticker. Reproduced identically
at the base commit in the probe worktree with no source changes. Left alone as an unrelated suite; a
background task was raised for it.

## Findings, rulings and deviations

- Every F1-F3 review returned **no blocking findings**. All should-fix items were resolved; see
  FOUNDATIONS-LEDGER.md for the item-by-item record.
- The H1 review returned **one blocking** finding (the skip link destroyed the page) and the H2
  review **four** (absent evidence printed as zero; a tone percentage board.py returns three counts
  to prevent; a chart caption claiming a resolution the line lacked; the previous company rendered
  under the new company's heading). All resolved. H3+H4 returned none. HUB-LEDGER.md has the
  item-by-item record.
- **Scope gap found by review, now closed:** Human Chatter shipped with no server-side filters,
  which is half of its acceptance row. `static/radar/src/hub/Filters.tsx` is new and is the only
  file in Release 1 the plan does not name.
- **Deviation:** the activity payload carries one key beyond the shape the plan enumerates,
  `counted_runs`. Off-version runs were skipped from the counters while still counted as completed,
  so a per-run rate read off the payload was silently wrong. Removing it is a one-line change if
  Codex prefers the enumerated shape.
- **RESOLVED by R3.** R2 measured the activity read at 12,728 rows / 56.8 MiB / ~1.4 s /
  ~201 MiB of peak Python heap for 120 integers; Codex chose typed counter columns, and R3 built
  them. The read now names eight scalar columns and streams them: **0.8 MiB peak heap, 390 ms
  median** at the widest window. `summary_json` is unchanged and is never fetched by the read.
- **A day is not immutable at Berlin midnight.** Runs are grouped by `started_at` but
  `finish_run` closes them later, so a run spanning midnight changes the previous day --
  roughly one day in five. R3 adds no cache, so nothing depends on this today; it is recorded
  because any future memoisation would need a `no running rows` condition, not a date key.
- **Parity with the old reducer is exact for every shape production writes, and deliberately
  not exact in three places**: a `schema_version` of `1.0` or `True` is no longer countable,
  and a counter outside the accepted domain is null rather than summed or raising. Each is
  pinned by a test asserting the difference. See FOUNDATIONS-LEDGER.md, "R3 evidence".
- **Accepted limit, wording corrected under R2:** `observations.capture()` will accept a backdated
  `now`. `now` is an injected clock and the parameter exists for deterministic tests; the docstring
  no longer claims the function guarantees real time. The guarantee is a property of the call path.
  The docstring cited a test pinning that call path which **did not exist**; the R2 review found it
  and `test_the_scheduled_job_captures_the_wall_clock` now supplies it, mutation-checked.
- `RADAR_OBSERVATION_CAPTURE_ENABLED` and `RADAR_PRODUCER_REVISION` are set nowhere. Capture is off,
  which is the intended default until a staging pass.

## Deployment carries

Nothing here is deployed and no live migration has been run.

**TWO migrations are required, not one.** An earlier version of this paragraph named only
d82f9afb5898, which is now wrong: applying it alone leaves the new writer and reader without the
projection columns they both depend on, which is a broken deployment rather than a partial one.

| revision | what it does |
| --- | --- |
| d82f9afb5898 | creates `radar_ingest_runs` and `radar_board_observations` |
| a7c31f0b52d4 | adds six projection columns to `radar_ingest_runs` and backfills them |

Both are additive, both downgrades were rehearsed as exact inverses on MariaDB 10.11.14, and
`summary_json` is never modified by either. **The procedure is not here**: `/root/update_coc.sh` is
the single migration owner and RELEASE-RUNBOOK.md is the single execution path. Do not run
`flask db upgrade` by hand alongside it. Check the target's heads again before the release rather
than trusting the pair above to still be the top of the chain -- see RELEASE-PROPOSAL.md section 2.

`radar_ingest` must be STOPPED for the migration. It is the writer of `radar_ingest_runs`, and
MariaDB's DDL auto-commits, so there is no supported window in which the old writer stores
envelopes while the new reader expects projections.

Rehearsed on **MariaDB 10.11.14**, the target's own version, by
`scratchpad/rehearse_mariadb.py`: 39 checks covering a clean upgrade over pre-existing rows, BOTH
downgrades, interruption after partial column creation, interruption partway through the backfill,
recovery from both, the pre-DDL domain refusal, and the application's writer and reader on that
engine. Note what the first deployment actually is: `radar_ingest_runs` does not exist on the
target, so it is created empty and the backfill projects zero rows. The seeded cases rehearse the
second deployment onward. **If `flask db upgrade` fails partway, do not re-run it blindly** -- the
revision is unstamped and some columns may exist, and a blind retry fails on a duplicate column.
**Two different failures with two different procedures** -- an interrupted FIRST migration and an
interrupted SECOND one -- are in RELEASE-RUNBOOK.md section 7.

Capture is a separate decision after a healthy deployment: `RADAR_OBSERVATION_CAPTURE_ENABLED=true`
and `RADAR_PRODUCER_REVISION=<the deployed sha>` on the ingest host. The board-observation job is
registered whether or not capture is enabled, returns immediately when it is off, and logs
`radar board observation capture is disabled` at startup, so enabling it is an environment change
plus a restart rather than a code change.

`/radar/` is unchanged and is the rollback: a code-only rollback is complete, because the old code
neither reads nor writes the new columns and they can be left in place. `/radar/hub/` is the
opt-in route for owner review. Promoting the hub to the root route is a separate decision that has
not been made, and once it is, "the old /radar/ is the rollback" stops being sufficient.

The full plan -- drift, gates, service ordering, verification, rollback and open decisions -- is
**RELEASE-PROPOSAL.md**. Nothing in it is authorized or executed.

Local preview: `PYTHONPATH=. py -3.12 scratchpad-served app on port 5051` (a two-line `app.run`
script), then `/radar/hub/`. Port 5001 belongs to the owner's own instance -- do not take it.

## Before the next session switch

Replace the sections above with the then-current worktree, branch, HEAD, dirty ownership, completed
and open tasks, review findings, exact tests and results, protected files and deployment carries.
Verify this file against Git and the reports before trusting it; if they disagree, the evidence wins
and the discrepancy belongs in the ledger.


## Owner clarification — staged design ambition (2026-09-09)

The interactive prototype is the near-term fidelity target for VC1 and the next
iterations, NOT the desired final product or a permanent ceiling. The longer-term
ambition remains the visual richness, sophistication and research depth of the
original image concepts: A's welcoming overview and B's focused research workflow,
unified in the selected light/green identity. C remains rejected.

As history, portfolio and news capabilities mature, design their pages and revisit
the hub's composition with richer charts, evidence interactions, hierarchy and
polish, using fresh mockups before implementation. Aim for the original concepts'
level of craft and complexity where it serves research; their fictional content
is not a promise of available data. The current prototype's simplified layout and
components do not bind future design. Do not freeze the product at VC1 fidelity.

This does not expand VC1: deliver the current interactive-reference correction
first, then evolve deliberately alongside the roadmap. No new implementation or
deployment is authorized by this clarification alone.

## Codex review update — 2026-09-10

See CODEX-DECISIONS.md Eighth return. TE1 accepted with local-schema limits;
principal VC1 accepted for owner preview. VC1-close remains before deployment:
approximate-bar explanation, scope table breakpoint changes to Chatter, responsive
accessible labels. Do not redispatch completed work. Owner may review now;
no deployment authorized. Current reviewed HEAD d66b52e; Codex documentation
edits are intentional and uncommitted. Fresh focused Vitest: 56 passed/2 files.

2026-09-10 owner addition: sortable Chatter is OPEN within VC1-close. Read the appended binding sorting contract in VISUAL-CORRECTION-PLAN.md. Preserve completed tasks; return sorting with the same closure review/preview. No deployment authorized.


2026-09-10 Codex Ninth return: VC1-close/sorting accepted for owner visual review at 31ae58a. A-D settled with no new implementation gate. Fresh focused tests: 78 passed/2 files. Next: owner reviews sortable preview; deployment is a separate decision. See CODEX-DECISIONS.md. These Codex documentation edits are intentional.


## Owner approval — VC1 deployment, 2026-09-10

The owner visually accepted the sortable preview ('Looks good just like I
imagined'), then authorized proceeding with the proposed merge/push/deployment
('lets go ahead') after confirming historical snapshot capture is for later.

Claude is authorized to merge/push the reviewed VC1 candidate 31ae58a plus
reviewed documentation-only ruling updates and deploy the updated hub in the
next suitable window. Preserve /radar/ as the original page and keep observation
capture off. Include the established fresh backup, temporary service stops,
matching build, restart/smoke verification and code-only rollback if needed.
No capture enablement, root promotion, OT1 cleanup, schema downgrade or live
restore is bundled into this authorization.

Execution must use current facts: production was reported at ba1c381 and already
at migration head a7c31f0b52d4. This update introduces no new migration. Do not
reuse the first release's 'both tables absent' preflight or drop/stamp anything
to recreate it. Verify remote/target drift before merging and deploying, record
the exact merge/deployed SHA, and assess unexpected code/schema changes before
continuing. Retain the existing migration chain for routine upgrades/rollback.

Claude should prepare the concise deployment delta and execute within this
approval without asking for the same approval again. Announce the actual window,
follow the accepted service ordering and backup procedure, then verify old Radar,
hub assets/sorting, current activity_sources and tone on real data, service health,
unchanged migration head and capture off. Do not mint an owner login session;
use existing authorized verification methods. Report any authenticated checks
that need the owner's session honestly. Record results in RELEASE-RECORD.md and
HANDOFF.md. Production has not changed merely because this approval is recorded.

---

# PERF3-close implementation complete locally — 2026-09-12

Workspace `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3`, branch
`codex/radar-perf3`, began at `197be30c2c1028c0b46f8110783f1da5e428d481`.
Use Git for the final commit SHA. PERF3-close adds the exact destructive-target
plus registry gate, stable demanded-warm priority, hub Discover warm-key alias,
loaded measurement/recovery helpers, first-demand schema field and the one
authoritative stopped-web release path. Freshness remains 120/120/600.

Fresh evidence: 235 focused backend tests including both migration suites;
701 Radar frontend tests; production frontend build/typecheck; Python compile;
MariaDB 10.11.14 rehearsal 60/60; loaded two-process HTTP matrix 320/320 board
responses with five overlapping producer builds and a 16,792-row update and
restore. Fifteen of sixteen cases met p95 <=500 ms. US/12h/3-watch was p95
564.8 ms/max 629.5 ms due to the account-enrichment tail under the write and is
an explicit local concern. The <=2 s cold goal also remains unmet/non-blocking.

No target read, deployment, merge, push, production write, service/config
change, migration, restart, capture change, thread/index/producer expansion or
freshness change occurred. No target connection coordinate or authorized
remote execution surface was available; old target facts are conditional.
The required deploy proposal is in the top PERF3-close section of
`PERF3-RELEASE.md` and is explicitly unexecuted.

Protected `cleanup_preview.py` and `preview_perf3.py` were not read, run,
edited, deleted or staged. `.superpowers/`, the local registry, measurement
JSON/logs, secrets/environment and generated build products remain unstaged.


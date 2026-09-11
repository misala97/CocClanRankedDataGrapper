# CURRENT — PERF3: Tasks 1–7 complete, Task 8 in review, Task 9 HELD for the owner's go (2026-09-11)

Claude implements under the PERF2 ruling; Codex owns planning. **Nothing is
merged, pushed, deployed or configured on the VPS**; the deployed SHA is still
`4221196`. The owner asked that Task 9 not start until he says so, after his
usage limit resets.

| | |
| --- | --- |
| Workspace | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3` |
| Branch | `codex/radar-perf3`, from `afe1246` |
| HEAD | the commit carrying this handoff; the last code commit is `6ecba5a` (Task 8b) |
| Binding | `PERF2-CODEX-RULING.md`; plan `PERF3-PLAN.md` (Task 8 carries two 2026-09-11 amendments, Task 9 one); ledger `PERF3-LEDGER.md` |
| Controller scratch | `.superpowers/sdd/`: task briefs 1–9, implementer reports 1–8b, review packages, `progress.md` (the running log, including owner decisions). Working files, not committed. |
| Tests DB | `personal_apps_radar_perf3`, stamp `b7e3f9c1a2d4`, te1 clone with 29 FKs; its board data ends 2026-09-01, so real-clock boards there are empty |
| Scale DB | `personal_apps_radar_perf3_scale`, stamp `b7e3f9c1a2d4`; Task 8 ALIGNED its data forward by whole days so real-clock windows are full. Re-run `personal_apps/scratchpad/perf3/align_scale_fixture.py` before any new timing, through `scale_env.py` |
| MariaDB | the portable 10.11.14 rehearsal server is STOPPED; restart command in the ledger; needed only if the store or migration changes |

| Task | State | Commits |
| --- | --- | --- |
| 1 key + namespace | complete | `a5017e7`, `20429d0`, `a188bb3` |
| 2 store + migration | complete; MariaDB rehearsal 54/54 | `0eba6a4`, `c2d0ca9`, `c199d06` |
| 3 producer | complete | `fd810c1`, `55f0d7f` |
| 4 read path, flag, API | complete | `9097621`, `6752492` |
| 5 old board client | complete after five fix rounds, under the owner's stopping rule | `0ed59e2`, `2b90885`, `17128b8`, `52af950`, `27738b2` |
| 6 hub client | complete after one fix round, same rule | `103b8ba`, `d429378` |
| 7 parity | complete | `29cc2ac` |
| 8 scale verification + browser | implemented; **review running or just returned — see the ledger's Task 8 section** | `9fa42aa` (8a), `6ecba5a` (8b) |
| 9 suites + release package | **HELD until the owner's go**; brief ready and amended (telemetry) | |
| whole-branch review | open; the carried lists from Tasks 1–8 are in the ledger | |

**Immediate next action.** If the Task 8 review's verdict is not yet in the
ledger, record it. Then WAIT for the owner. On his go: Task 9 (full backend
suite with every failure classified, the frontend suites and builds, the
app-level request-timing log behind `PERSONAL_REQUEST_TIMING_LOG` (off by
default), `PERF3-RELEASE.md` with the producer unit, deploy-script additions,
flag sequencing, readiness gate, telemetry, rollback and resource numbers, and
this handoff); then one whole-branch read-only review over the carried lists,
one fix wave, and the return to Codex. Any fix round the Task 8 review asks for
also waits for the owner's go.

**Owner decisions in force.** One implementation worker at a time, a separate
review per task, full proof runs ("do it properly"). The stopping rule for
Tasks 5 and 6 (one last fix round; a re-review blocks only on what that round
introduced or on a ruling violation) is recorded in the ledger.

**Open decisions for Codex from Task 8's evidence** (ledger, Task 8 section):
the 120 s fresh bound fails under write contention (worst 142.8 s, about 7%
stale, because the refresh target equals the bound); after an empty store the
warm boards rebuild in `key_hash` order, so a reader can wait about 44 s; a
restarted worker's first read p95 is 769 ms; the cold goal stays unmet
(about 5.8 s); the Discover tab asks for a cold duplicate of a warm board. The
core win holds: beside two cold boards a non-Radar request stayed under 79 ms
with the flag on against 9.5 s with it off, in the two-process MODEL. A new
old-board defect for the fix wave: a board arriving after a wait moves focus to
the detail panel and scrolls a phone reader about 4,219 px from the list.

**Test evidence so far.** Radar vitest 681/681 three runs in a row and root
403/403 at `d429378` (no frontend code changed since); parity 63 cases at
`29cc2ac`; 255 backend tests across the board, store, API and migration suites
at `6752492`. The whole backend suite has not been run on this branch; that is
Task 9.

**Traps.** `app.py` loads `.env` with `override=True`, so an environment
variable cannot pick the database: scale scripts go through
`scratchpad/perf3/scale_env.py`, which also pins the build revision
(`PERF3_REVISION`) and patches the fixture's placeholder subreddit names. Two
session breaks so far (an expired login token, then the API session limit);
the ledger records what each cost. Never print `.env`: an earlier listing put
real credentials into this session's transcript, and the owner was told.

**Protected:** `personal_apps_radar_perf1`; the `radar-perf2` worktree and
Codex's uncommitted edits there; every other worktree; the planning
checkout's dirty files; every `.env`. No deployment carries exist yet; the
release package is Task 9.

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



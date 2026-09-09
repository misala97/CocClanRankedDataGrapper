# Codex entrypoint: the implementation is back

Counterpart to CLAUDE-START.md. Codex plans; Claude implements and verifies. Both plans are
complete, every task was independently reviewed, and every finding was resolved.

**Fifth pass, 2026-09-09.** You accepted P1, chose `origin/main` as the integration
target and set P2. **The isolated candidate exists, the single-path runbook is
written, and three gates are blocked on access this workspace has never had.**

```
candidate branch   codex/radar-release-candidate
worktree           C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate
branched from      origin/main 2a83905
transplanted       38 commits, chronological, 7a9ffe4..codex/radar-foundations
excluded           the 12 unpublished research commits below the base
```

`codex/radar-foundations` and its worktree are untouched, as you required. **The P2
work lives on the candidate only.**

The transplant is clean and, more to your point, it was *tested* rather than
inspected: no excluded commit is an ancestor, the candidate changes none of the 19
paths those twelve touch, and every regression number on the candidate matches the
source branch exactly — 403 + 438 frontend, 253 backend, 96 shared-helper, single
head `a7c31f0b52d4`. Nothing in the release imports any of the twelve, so there is
no minimal dependency to bring back for scope review.

**All three access gates are now CLOSED.** The owner authorized read-only VPS
access, so the deploy script and the target were read and the nightly backup was
restored into a disposable MariaDB and verified. **Four things this runbook had
wrong were found by doing that**, which is what the gates were for -- including a
requirement the deploy script does not meet and a MySQL-ism in my own preflight SQL
that MariaDB rejects outright. See "P2: the gates, and what reading the target
found".

**Earlier this pass.** P1 rehearsed both migrations on MariaDB 10.11.14 (39 checks),
and the independent review of my own runbook found a blocking defect in it, described
below.

P1 needed a disposable MariaDB and this machine had none — no MariaDB, no Docker or
Podman, WSL not installed. Rather than record the gate as pending, the owner agreed to
a portable MariaDB **10.11.14**, the version the VPS runs, run from the scratchpad on
its own port with its own datadir. **39 checks, all passing**: both migrations, both
downgrades, interruption after partial column creation, interruption partway through
the backfill, recovery from each, the pre-DDL refusal, and the application's own writer
and reader on that engine.

**RELEASE-PROPOSAL.md** is the concrete side-by-side plan. It was independently
reviewed and the review found one blocking defect in it, described below — worth your
attention, because it would have bitten an operator following my runbook.

**Earlier this pass.** R3 was accepted with strict integers confirmed; the three
divergences from the old reducer are kept and tested as divergences, and the counter
contract is not described anywhere as exact parity for arbitrary JSON.

| 30-day upper-bound fixture, 14,652 rows | before | after | your target |
| --- | --- | --- | --- |
| peak incremental Python heap | ~228 MiB | **0.8 MiB** | <= 16 MiB |
| median endpoint | ~1,586 ms | **390 ms** | <= 500 ms |

Four concurrent 30-day reads: 0 errors, 1958–2042 ms, process RSS 135 → 136 MiB. Cold reads
match warm, so the gain is the read getting cheaper rather than a second request getting
lucky. `summary_json` is unchanged, still stored, and never fetched by the read.

**One thing needs your attention and one thing does not.** The first is that parity with the
old reducer is deliberately not total — three cases, one of which I had neither documented
nor tested until the review found it. See "Where R3 departs from the old reducer". The
second is that no compatibility exception arose: the disposable clone holds no counter
outside the accepted domain, so there is nothing to bring you under requirement 6.

**Earlier passes.** R1 was a real defect, fixed with tests that fail without it. R2 measured
what you asked for; the estimate had been five times low, and my first measurement of it was
then twice too high — caught by review and corrected before it reached you.

Read this first, then HUB-LEDGER.md and FOUNDATIONS-LEDGER.md for the item-by-item
record, then HANDOFF.md for exact workspace state. **Where a document and Git disagree,
Git wins.**

## Where the work is

```
Worktree   C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations
Branch     codex/radar-foundations
Base       dev_personal @ 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD       verify with `git rev-parse --short HEAD`; the table below lists every commit
```

Count them with `git log --oneline 7a9ffe4..codex/radar-foundations`; this document cannot
name the commit that carries it.

The planning package (radar-design/ and both dated plans) was untracked in the planning
checkout, so it was carried in and committed first as 9e8d446 — a worktree made from HEAD
alone would not have contained the contract being implemented against.

Nothing is merged, nothing is deployed, no live migration has run, and `/radar/` is
untouched. The planning checkout at `C:/Users/michi/Desktop/CodingStuff` is unchanged
apart from these documents being refreshed in place.

| Commit | Task |
| --- | --- |
| 9e8d446 | the planning package, carried in |
| e4a27e9 / d79da27 | F1 run recording, then its review's fixes |
| 3d22902 / 236f862 | F2 board archive, then its review's fixes |
| 328074a / a178ba6 | F3 activity and ops APIs, then its review's fixes |
| 92da7c8 | H1 hub shell |
| 0f3767b | H2 chatter, research, search + the H1 review's fixes |
| c88266b | H3 watching and overview |
| 8864189 | H4 activity and administration |
| 39e8042 | the H2 and H3+H4 reviews' fixes |
| ed62b32 / 765f4f6 / 1e30096 | ledgers and handoff |
| 07e7cef / b78b5d2 | this document, and the handoff naming its commits |
| 243db22 | CODEX-DECISIONS.md, carried into the worktree it applies to |
| e25f223 / 917cb15 | **R1** the final-feed defect, then its review's fixes |
| ffbdd37 / 08c5b47 / 8bbd57e | **R2** the endpoint measured, twice corrected under review |
| 3c93ad8 | your binding ruling on the second return, carried in |
| c4e0455 / 278625c / cfe39e7 | **R3** typed counters, acceptance evidence, review findings |
| 78b17c6 | a jsdom navigation flake that had been failing random tests since H1 |
| 3c2eb77 / 8c50cda | ledgers and handoff |

## What was delivered against the plans

**Release 0 (F1–F3), all of it.** `RadarIngestRun` and `RadarBoardObservation` in one
additive migration (d82f9afb5898, downgrade verified as an exact inverse against a
disposable database); the run recorder with its own transaction and full failure
containment; the quarter-hour board archive with the fixed US/DE pair, disabled by
default; and `/radar/api/activity` and `/radar/api/ops`.

**Release 1 (H1–H4), all six pages** at the opt-in `/radar/hub/`: Overview, Human chatter,
Research, Watching, Activity, Administration. `/radar/` is unchanged and is the rollback.

## What the reviews found — five blocking defects

Every one of these was in code that passed its own tests. This is the part worth your
attention, because four of the five are the failure mode the spec is written against:
the surface saying something the data does not support.

1. **The skip link destroyed the page.** `#rh-main` is an element id and the router
   claimed every fragment as a route name, so the first control a keyboard reader meets
   landed on "there is nothing at this address". (H1)
2. **Absent evidence printed as zero.** Research showed "0 independent voices across 0
   posts" beside a clause, from the same payload, saying 80 mentions. The bucket totals
   outlive the per-mention rows behind them, so an older window legitimately has totals
   and no evidence. (H2)
3. **A tone percentage `board.py` returns three counts specifically to prevent** — its own
   docstring calls a single "% bullish" over them "noise wearing a percentage sign" — and
   it rounded, so one bullish post in two hundred would have read "0% positive". (H2)
4. **A 1D chart drawn from daily closes captioned "intraday quotes".** The board panel has
   a guard for exactly that; the caption table was copied and the guard was not. (H2)
5. **The previous company rendered under the new company's heading and URL**, from cached
   placeholder data. (H2)

H3 and H4 returned no blocking findings. Roughly forty should-fix items across the nine
reviews were also resolved; the two ledgers list them.

## The follow-ups you set

### R1 — unchecking the last feed. Real, reproduced, fixed.

Your reading was exact. With `['reddit']` selected, unchecking Reddit ran
`all.filter(name => name !== source)` and returned `['bluesky','fourchan']`. The reader
asked for one fewer feed and silently got two different ones — a board built from sources
they had explicitly turned off, which is the same class of defect as the five blocking
ones above: the surface answering a question nobody asked.

The rule now: a feed whose root is the only one selected cannot be turned off. `toggle`
roots **both** sides before comparing and returns the identical array when the removal
would empty the selection; the handler compares by identity and returns without calling
`onChange`, so no history entry is pushed and no board is fetched.

`aria-disabled`, not `disabled` — following the board's own recorded decision at
`board/Controls.tsx:192-196`: a disabled control leaves the tab order, which would put the
explanation of the lock out of reach of the readers who most need it. The native input
still toggles and still fires `change`; the handler is what holds the line, and a browser
test proves it.

Commits **e25f223** then **917cb15** (the review's six findings). Tests: 171 in
`static/radar/src/hub/`, 438 across the radar config, `npm run build` exit 0. **Reverting
only the reducer fails 6 tests.** Before this work the same revert failed **0** — Chatter's
one guard asserted `sources.length > 0`, which the defect satisfied. That test is deleted;
it tested nothing. Browser proof in `reports/hub/hub-feeds-{un,}locked-1440.png`: a forced
real click on the locked box left it checked, showed the note once, and issued zero
`/radar/api/board` requests.

### R2 — the estimate was five times low, and it named the wrong writer

`RadarIngestRun` rows are not written by the board archive's 15-minute job. They are
written by `tick`, and **two** schedulers call `tick`: `radar_cycle`, which reschedules
itself at `interval_for(session_state(now))` — 180 s in pre-market and regular hours,
600 s after hours, 1800 s overnight and at weekends — and `radar_reddit`, fixed at
`ARCTIC_SHIFT_INTERVAL_SECONDS` = 300 s, all day, every day.

That is **14,792 firings** over 30 days on a drift-free walk, five times the guess.
APScheduler rebuilds the interval trigger on reschedule, so the next firing is *finish* +
interval; a 38 s cycle gives **12,855**, and `coalesce=True` on the reddit job can only
reduce it further. The drift-free figure is the upper bound.

**Then my first measurement of it was itself ~2x too high, and the review caught it.** I
modelled one envelope for both jobs, keyed by all 36 concrete sources. `run_cycle` keys
`aggregate_status` and `catchup_depth` by the **root** fetcher name (`ingest.py:288,306`)
and the schedulers pass disjoint fetcher sets, so no run has ever written a 36-key
`aggregate_status`. Real shapes: a `radar_cycle` envelope is **631 bytes**, a `radar_reddit`
one **7,447**. Same class of error the task existed to remove, so I am flagging it rather
than quietly restating the table.

Measured again, against the disposable clone (MySQL 8.0.46; production is MariaDB), with
rows and bytes asked of the **database** over the same Berlin-day window `summary()` queries.
Both scheduling models are seeded and measured, rather than one measured and the other
asserted:

start + interval, the drift-free upper bound:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 276 | 1.3 MiB | 27 ms | 31 ms | 4 ms | 4 MiB |
| 7 days | 3,212 | 14.3 MiB | 307 ms | 320 ms | 40 ms | 50 MiB |
| 30 days | 14,652 | 64.2 MiB | 1,609 ms | 1,586 ms | 196 ms | **228 MiB** |

finish + interval with 38 s runs — what APScheduler actually does:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 239 | 1.1 MiB | 26 ms | 25 ms | 4 ms | 4 MiB |
| 7 days | 2,791 | 12.6 MiB | 297 ms | 262 ms | 35 ms | 45 MiB |
| 30 days | 12,728 | 56.8 MiB | 1,390 ms | 1,413 ms | 160 ms | **201 MiB** |

Anchored on a **Wednesday** on purpose: one Sunday is 336 firings against a weekday's 568.
Milliseconds are best-of-five on a warm buffer pool — lower bounds; the endpoint is timed
last over already-warm rows, so where it reads under the function it wraps, that is the noise
floor. Peak heap is `tracemalloc` — Python allocations, a floor on RSS. Bytes assume every run
succeeded with all eight intake reasons on every source — an upper bound, and
`intake_reasons` is 84% of the reddit envelope.

**The two right-hand columns are the actual finding, and neither was in the first pass.**
Without `summary_json` the same window takes 160 ms against 1,390, so the envelopes dominate.
And `summary()` ends in `.all()`, holding every row *and* every decoded dict at once:
**~201 MiB of Python heap for one request**, on a `login_required`, uncached route any
signed-in reader can repeat. On a small host that is what ends the process, not the seconds.

Also corrected: `capture(now)`'s docstring claimed the function guarantees a real-time
observation. It does not and cannot — `now` is an injected clock and the parameter exists so
tests are deterministic. It now says what is true: `observed_at` is the instant the caller
supplied, copied verbatim, and the real-time guarantee belongs to the call path.

**One correction you should know about, because your ruling assumed otherwise.**
CODEX-DECISIONS.md:29 says "preserve that call-path test". There was no such test. Nothing
asserted that `_scheduled_observations` passes `_utcnow()` — it could have passed the slot
boundary or a local time and the suite would have stayed green.
`test_the_scheduled_job_captures_the_wall_clock` now supplies it; mutation-checked, it is the
only test that fails when the caller is changed.

## The decision that was waiting on you — now made, and built

**The activity endpoint's cost.** R2 brought you five options with what each cost, and a
recommendation. You chose **option 3, typed counter columns, before the first rollout**, and
declined the memoisation and the `ALLOWED_DAYS` cut I had put ahead of it — on the grounds
that a memo does not bound a cold request and that a schema change was already needed. The
measurements bear that out: cold reads now match warm, which a cache would not have given.

R3 built it. See "R3 — typed activity counters" below.

One fact from R2 survives the change and is recorded because a future memoisation would need
it: **a day is not immutable at Berlin midnight.** `summary()` groups runs by
`_berlin_date(started_at)`, but `finish_run` writes `status` at *finish* time and never
touches `started_at`, so a run starting at 23:59:5x Berlin and closing after midnight rewrites
the previous day — roughly one day in five at the measured cadence. R3 adds no cache, so
nothing depends on it today.

## What you already ruled on, now closed

Per CODEX-DECISIONS.md, all four kept as built: **`counted_runs`** stays in the activity
payload; **`Filters.tsx`** stays; **`api.ts`'s 403 read/write split** stays; and
**`vite_assets.resolve_asset_css`** with its manifest memo stays. Nothing was reverted.

`counted_runs` earns its place again under R3: it is now the count of ok rows that were
`summary_countable` AND at the reader's own schema version, which is exactly the population
the counters were summed from. Without it a day whose totals were all skipped would still be
indistinguishable from a day that reported nothing.

## Still open from the first return, unchanged

`tests/test_radar_ingest.py` is not re-runnable against a persistent database: its `_wipe()`
helper does not delete `RadarMention` rows for its own ticker, so every run after the first
fails three tests. **Reproduced identically at the base commit 7a9ffe4** in a separate probe
worktree with no source changes, so it predates this work. Left alone as an unrelated suite;
a background task was raised for it.

## R3 — typed activity counters

Six additive columns beside `summary_json`, migration **a7c31f0b52d4** on the verified head.
`finish_run` writes the projection in the same transaction under the same terminal guard. The
read names eight scalar columns and streams them with `yield_per`, folding into at most thirty
Berlin-day accumulators. `_counted`/`_counters` are gone from production — the old reducer
lives in the tests as an oracle, because a JSON fallback in production would leave the read
able to fetch envelopes, which is the cost being removed.

The marker/version split you specified is what makes parity possible. `summary_countable` says
the envelope was structurally well formed and versioned; the reader alone applies
`== SCHEMA_VERSION`. A counter missing from an otherwise valid summary is null and leaves the
row countable — the case a nullable column alone cannot express.

**Migration.** Backfill is Python, batched 500 by primary key, with the projection rules as a
frozen copy pinned to the live ones by a 20-case test. The domain scan runs **before any DDL**,
and that was a real defect in my first version: MySQL commits implicitly on `ALTER TABLE`, so
refusing after the columns were added left them present with the revision unstamped, and the
retry then failed on a duplicate column. I hit that state and repaired the clone by hand. One
state remains that cannot be made clean — a backfill dying part-way — and the recovery SQL is
now in the migration's docstring.

## Where R3 departs from the old reducer

Parity is exact for every shape production writes. It is deliberately **not** exact in three
places, and the review was right that my test module claimed otherwise while routing every
disagreeing case around the oracle:

- A `schema_version` of **`1.0`** counted before and does not now. `1.0 == 1` is true in
  Python, so the old equality check accepted it. **This one I had neither documented nor
  tested** — it existed only as an accident of `isinstance`.
- A `schema_version` of **`True`** likewise, since `isinstance(True, int)` is true.
- A counter of **`-4`, `True` or `1.5`** was summed before and is refused now; **`'5'`** raised
  TypeError out of the endpoint and is now null for that counter.

Each is the behaviour your ruling implies: an Integer column recording `1` for a declared `1.0`
would claim the envelope said something it did not, and requirement 6 forbids coercing
counters. Four tests now assert the DIFFERENCE against the oracle rather than avoiding it. If
you would rather `1.0` and `True` stay countable, that is a one-line change and a decision, not
a defect — say so and I will make it.

## What R3 did not need from you

No compatibility exception under requirement 6: the disposable clone holds no counter outside
the accepted domain, so the refusal path is tested but never fired on real data. No cache, no
rollup table, no JSON-path SQL, as instructed. `ALLOWED_DAYS` is still `(1, 7, 30)` and the
month selector is untouched.

Recorded because a future memoisation would need it: **a day is not immutable at Berlin
midnight** — runs are grouped by `started_at` but `finish_run` closes them later, so a run
spanning midnight rewrites the previous day, roughly one day in five. R3 adds no cache, so
nothing depends on it today.

## P1 and the release package

### The blocking defect the review found in my own runbook

My first runbook told the operator to learn about domain violations ahead of the window
by "attempting the upgrade, which will refuse without touching the schema, so it is
safe". **That was false and it would have performed the entire release.**

`radar_ingest_runs` does not exist on the target — `d82f9afb5898` creates it, and the
deployed code declares no `RadarIngestRun` model at all. The domain scan lives inside
the *second* revision, so `flask db upgrade` applies the first, creates both tables,
and then reaches an empty table it cannot refuse. Verified on a disposable MariaDB: the
full upgrade ran and stamped `a7c31f0b52d4`. An operator doing my "safe preflight"
would have migrated the schema outside the window with the old web process still
serving against it.

Three things follow, and they change what this release is:

- The backfill projects **zero rows** on this deployment. The expected output is
  `radar_ingest_runs: projected 0 rows`; anything else means the target is not in the
  assumed state.
- The pre-DDL domain refusal **cannot fire** here. It matters from the second
  deployment onward, which is what the rehearsal's twelve seeded rows actually cover.
- There is no safe partial dry run: `flask db upgrade` performs the schema
  mutation, so it can never be a read-only preflight. Nor does it by itself
  complete the release — the deployment and the verification are separate steps
  that follow it.

### Also corrected after review

- The `origin/main` drift was attributed backwards. `origin/main` and
  `origin/dev_personal` have the **identical tree**; the two merge commits change no
  files. The 19 files I credited to them come from the 12 unpushed local commits —
  which was already item 1, counted twice.
- `d82f9afb5898`'s downgrade — the `drop_table` the rollback command actually reaches —
  had never run on MariaDB, while a note beside it said "both revisions". It does now.
- The runbook ignored `/root/update_coc.sh`, which hard-resets to `origin/main` and
  runs migrations itself. A hand-deploy of this branch would be silently reverted by
  the next routine deploy.
- The hub adds three routes, not one; `radar-encoder-trial.timer` is pre-existing and
  would have read as a violation of my own "no new process" check; and the
  verification checks were 200-level only, which an entirely broken projection would
  also pass.

### What P1 does not establish

The rehearsal ran the mariadb.org binary distribution on a default configuration; the
VPS runs the Ubuntu package `10.11.14-MariaDB-0ubuntu0.24.04.1` with its own tuning
file. Same upstream version, different build. And it ran on a fresh database stamped at
`b3d9e1f5a274`, not on a copy of the target's data — the 60 revisions below that are
*expected* to be applied on the target, asserted from the repository rather than
measured against it, since this workspace has no production access.

### Open, for you and the owner

1. **The integration target is ambiguous.** Local `dev_personal` has 12 commits on
   neither remote, so what this branch was built on is not what is published.
2. **Who deploys, and with what** — `update_coc.sh` or by hand. They interact badly.
3. **Backup verification** is listed as a gate. A restore has not been rehearsed.

## P2: the candidate, and what it proved

`git cherry-pick 7a9ffe4..codex/radar-foundations` onto fetched `origin/main`, no
conflicts. Acceptance evidence:

- 38 selected, 38 transplanted, counts match.
- **No excluded commit is an ancestor** — checked individually for all twelve.
- The twelve touch 19 paths; the candidate changes **none** of them, so nothing
  entered through conflict resolution.
- Candidate diff against `origin/main`: 114 files, +14,287 / −32.
- Regressions on the candidate, against the disposable clone: `npm test` 403 + 438,
  `npm run build` exit 0, `flask db heads` single `a7c31f0b52d4`, 253 backend across
  the seven radar suites, 96 across the shared-helper and old-surface suites.
- No release file imports any module the twelve introduced.

## P2: first-migration recovery, which P1 did not cover

P1 rehearsed a failure inside `a7c31f0b52d4`. A failure inside `d82f9afb5898` leaves
a different state and the projection-column recipe does not apply to it — assuming
one procedure fixes both is how an operator drops something they should not.

`scratchpad/rehearse_first_migration.py`, MariaDB 10.11.14, **33 checks** across
**four** interruption points: after each of the DDL statements that migration issues,
including the case where all four applied but the stamp was never written.
Inspection reports what is actually present, a blind re-run fails loudly, recovery
drops **only** the partial tables and rebuilds a schema **byte-identical** to a clean
run — and two refusals: it will not drop a table that holds records, and it will not
run at all when the stamp shows the first migration completed. Each partial state is
asserted to be one the migration could actually leave, checked before recovery drops
it.

## P2: the gates, and what reading the target found

The owner authorized read-only VPS access. Nothing was written: no service change,
no migration, no deployment, no file modified on the host. The only transfer off the
box was a copy of the already-existing nightly backup. Everything read is in
**TARGET-FACTS.md**.

**Every preflight expectation was confirmed.** Stamp `b3d9e1f5a274`, both new tables
absent, `sql_mode` and `REPEATABLE-READ` identical to the rehearsal, engine
`10.11.14-MariaDB-0ubuntu0.24.04.1`, capture off in the ingest process's own
environment.

**And four things this runbook had wrong, three of them precisely because it was
written without the access:**

1. **`update_coc.sh` does not stop `personal_apps_web`.** It only restarts it at the
   end, so the web process serves throughout the migration. I argued this was
   acceptable for this release; **you overruled that in the Fifth return and were
   right to**. Both web units now stop before the checkout. See "P2-close" below.
2. **My preflight SQL was wrong.** It asked for `@@transaction_isolation`, which does
   not exist on MariaDB 10.11 — `ERROR 1193 Unknown system variable`. MariaDB spells
   it `@@tx_isolation`. A MySQL-ism carried in from the development environment,
   which is the exact class of difference this gate existed to find.
3. **`radar-encoder-trial.timer` is a confirmed database writer firing every
   minute**, and `update_coc.sh` does not stop it. Its own unit says it "persists
   `recovering`" and "needs the database and nothing else". Masking it for the window
   is now required rather than conditional on an inspection.
4. **The nightly backup is a cron job at 03:15, not a systemd timer.** The
   `list-timers` inventory I specified would never have surfaced it. A window
   overlapping 03:15 would run a `mysqldump` of the database being migrated.

Also: the deployed SHA is `b7d8adf`, **one commit behind `origin/main`**, so the
drift check must compare against the deployed SHA and not only the remote.

## P2: the backup restore

`db_2026-09-09_0315.sql.gz`, 190 MB, SHA-256 verified on the box and again after
transfer. Restored into the disposable MariaDB — never anything live, and neither
rehearsal harness was pointed at it.

From within that one snapshot: **43 `personal_apps` base tables**, stamp
`b3d9e1f5a274`, `radar_watch` 4 rows, `app_user` 3, `radar_buckets` 1,133,729,
`radar_mentions` 283,970, gym tables populated. Representative rows rather than only
counts: the four watch rows read back as `RZLV`, `HTZ`, `UUUU`, `REI` and **all four
join to a real `app_user`**, so the account relationship survives the round trip.

`radar_buckets` differs from the live count (1,225,015 read at 20:35). **That is not
a discrepancy** — your ruling is explicit that comparing an old backup to a
still-changing live database is not a valid check. It is useful for one thing: it
makes the **data-loss window** concrete at ~91,000 buckets over ~17 hours. Backups
are daily, so worst case is just under 24 hours.

## P2: what I did not do, and why

- **No merge and no push.** The candidate exists locally. Merging it to `main` is
  step 4.1 of the runbook and is not authorized here.
- **The proposal's second runbook is gone**, not amended. One migration owner.
- **No write to production of any kind.** Read-only access was authorized by the
  owner and used for exactly that: reading the script, the units, the settings and
  the backup. No service state changed, no migration ran, nothing on the host was
  modified.

## P2-close

```
candidate branch   codex/radar-release-candidate
final SHA          P2CLOSE_SHA
```

### 1. Service ordering — you overruled me, and the runbook now says so

Both `personal_apps_web` and `coc_web` stop **before** the checkout. The outage is
declared in section 1, begun at step 7 and ended at step 17. No permanent edit to
`update_coc.sh`; the stops are orchestration around it.

`radar-encoder-trial` gets its **service** stopped as well as its timer, and the
timer masked — stopping a timer does not kill a running invocation. Units the script
must restart are explicitly not masked. The backup is avoided by choosing a window
away from 03:15, not by inhibiting it.

**The self-contradiction is gone, and the review found two more of the same kind
that I had left in.** The script restarts `coc_web` and `personal_apps_web`
*itself*, after a successful build and migration, so all schema and API checks are
post-restart verification and there is no pre-start SQL gate to promise. Beyond
that:

- **I wrote that a non-zero exit means the restarts never happened. That is
  false.** The script's last three statements *are* the restarts, under `set -e`, so
  a failure in the tail exits non-zero with the migrations complete and the web apps
  already serving. The runbook now says: establish **where** it stopped first, with
  two read-only commands, then choose recovery or rollback.
- **Section 6 still carried the contradictions section 4 had just lost.** The
  rollback runs `update_coc.sh` again — another checkout, `npm ci` and build — so it
  needs the same stops, including `coc_web`, and it must not hand-start services the
  script restarts. Both fixed.

Also corrected: `--no-ff` on the release merge so `git revert -m 1` has a merge
parent, in both places it is needed; the first-migration figure is 33 checks across
four interruption points, not 25 across three; and a fresh verified backup is
required before the window, per your section A, rather than a re-verification of the
one already restored.

### 2. The two watch failures — the contract is intact

The exact assertions were `assert 1 == 0` (no cascade) and
`DID NOT RAISE IntegrityError` (no orphan rejection). Both are the signature of a
missing foreign key.

`models.py:1271` declares it. **Production has it** —
`radar_watch_ibfk_1 FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE
CASCADE`, read read-only — and so does the nightly backup. **The disposable clone
does not.**

`scratchpad/probe_watch_integrity.py` builds production's exact DDL on a disposable
MariaDB 10.11.14 and runs your four scenarios with temporary fixtures and no
production rows:

| scenario | production schema | clone schema |
| --- | --- | --- |
| normal add and remove | works | works |
| per-account isolation | holds | holds |
| orphan mark | **refused** | **accepted** |
| deleting the account | **marks cascade away** | **marks survive** |

**Classification: a test-environment defect, not a product defect, and not caused by
this release.** I checked for a second cause the foreign key might be masking and
found none: `watch.py:56-65` re-raises `IntegrityError` unless the duplicate row is
really present, and the account delete is a bulk `DELETE` relying on the database
cascade, so restoring the constraint is both necessary and sufficient.

**The wider finding matters more than the two tests.** The clone is missing not one
constraint but **all 29** — production and local dev both have 29, the clone has 0.
Every backend test run against `personal_apps_radar_wt` has therefore run without
referential integrity. That is bounded to three worktrees, not the whole project,
and it does not weaken this release's evidence, because the two new tables declare
no foreign keys and depend on none. The likely mechanism is `CREATE TABLE ... LIKE`,
which copies indexes but not foreign keys.

Worth stating because it is the more dangerous direction: a constraint-free test
database produces false **passes**, not only false failures. `radar_watch` is
written by the hub's watch surface and those tests have never run against the
constraint. Low risk — a session-authenticated `user_id` always has a real parent
row — but not a risk this clone could ever have surfaced.

**Proposed, not carried out:** rebuild the clone from the verified nightly backup,
which is now known to contain the constraints. That is a workspace change beyond
P2-close, so it is a finding rather than an action. No live data touched, no broad
schema cleanup.

### 3. Go / no-go

**GO for scheduling, NO-GO for execution until you authorize it.**

Everything you blocked on is closed: the service ordering is corrected and internally
consistent, and the watch failures are explained with schema and behavioural evidence
rather than an assumption. Two independent reviews were run on this closure; the
second found the two contradictions above, which are now fixed.

What still stands between this and a deployment is **authorization, not work**:

1. Your ruling on this closure.
2. Owner authorization naming the final candidate SHA and the window.
3. A fresh verified backup taken before that window.
4. The drift re-check at 4.1, against the **deployed** SHA `b7d8adf` as well as
   `origin/main`.

Capture enablement and root-route promotion remain separate and untaken.

## Evidence, if you want to check rather than take my word

All against `personal_apps_radar_wt`, a disposable clone of the local dev database
(**not a full one** — see "P2-close": it is missing all 29 foreign keys),
asserted before every backend run. Local is **MySQL 8.0.46**; production is MariaDB, and no
result here establishes MariaDB behaviour — that is a rollout rehearsal, as your section C
says.

- `npm test` → **403 passed** (root config) and **438 passed** (radar config), four consecutive runs
- `npm run build` → exit 0
- `pytest` over the seven radar suites (activity, observations, operations_api,
  activity_projection, projection_migration, api, daemon) → **253 passed**
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py -q` → **85 passed**
- Both migrations, upgrade → downgrade → upgrade, with a column-shape fingerprint of every
  table and row counts taken either side. d82f9afb5898 moves exactly its two tables;
  a7c31f0b52d4 moves exactly its six columns and preserves every envelope, checked against
  eleven seeded row shapes rather than an empty table
- R3 acceptance, 30-day upper-bound fixture (14,652 rows): peak incremental Python heap
  **0.8 MiB** (your target ≤16), median/max endpoint **390/414 ms** (target ≤500 median),
  four concurrent 30-day reads **0 errors** at 1958–2042 ms with process RSS 135 → 136 MiB.
  Repeatable: `PYTHONPATH=. py -3.12 scratchpad/bench_activity.py`, which refuses any database
  but the clone, seeds into 2019 and clears in a `finally`
- Mutation-checked rather than asserted: selecting `summary_json` fails the query-level test;
  a fixed-width `_day_bounds` fails the two DST boundary tests and neither grouping test;
  reverting the R1 reducer fails six frontend tests

`reports/hub/` holds 13 screenshots at 1440, 768 and 390 across all six pages plus the
recovery view, and `reports/hub/EVIDENCE.md` states precisely **which pixels are real
serializer output and which are the one labelled fixture** — Watching and Overview need
marks and this account has none, so their `watch_rows` are the board's own top rows
presented as marks. Activity and Admin are the live endpoints against a database with no
recorded runs and capture off, which is why they read as empty. That is correct, not a
rendering failure.

A separate keyboard and live-endpoint pass covers all five destinations at all three
widths: no document horizontal scroll, no console or page errors, the skip link is the
first tab stop and focuses the page without replacing it.

## What is explicitly not done

Deployment, promoting `/radar/hub/` to `/radar/`, and enabling capture are three separate
decisions, none of them taken. `RADAR_OBSERVATION_CAPTURE_ENABLED` and
`RADAR_PRODUCER_REVISION` are set nowhere; the capture job is registered either way and
returns immediately when the flag is off, so enabling it is an environment change plus a
restart rather than a code change.

The immediate next step is the owner's visual review of `/radar/hub/`. Prototype approval
was never approval of the finished implementation, and neither is this document.

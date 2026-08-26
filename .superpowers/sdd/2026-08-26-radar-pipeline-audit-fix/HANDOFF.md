# HANDOFF — radar pipeline audit fix

## CURRENT AUTHORITATIVE CHECKPOINT — Task 7 closed, 2026-08-27

This checkpoint supersedes the live-worker checkpoint immediately below.
There are **no active workers** at this instant.

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`
Code HEAD: `3b74f32` (`test(radar): pin healthy empty source results`)

Task 7 is complete and review-clean. The initial review returned 0 Critical,
2 Important, 1 Minor, teeth 4/6. Fix round 1 commit `3b74f32` addressed both
Important findings; scoped high-capability re-review approved 2/2 with zero
new findings. The full evidence is in `task-7-review.md`,
`task-7-fix-round-1.md`, `task-7-report.md`, and
`task-7-re-review-1.md`. The false-valued `COIN_SYMBOLS_MEAN_STOCKS` key pin is
the one deferred Minor and is recorded in `progress.md`.

Immediate next action: commit this checkpoint's SDD artifacts by exact path,
then dispatch Task 9 from the **hardened** `task-9-brief.md`. The Task 9
rulings and migration caveat are fully recorded in the live checkpoint below
and in `progress.md`; they remain binding. Task order remains:

`9 -> 8 -> 10-13 -> 14-17 -> 18-19 -> final review`.

---

## LIVE AUTHORITATIVE CHECKPOINT — Codex continuation, 2026-08-27

This checkpoint supersedes every checkpoint below it. Michi explicitly asked
that the continuation be complete enough for Claude to take over without chat
memory.

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`
HEAD when this checkpoint was written: `a3f0b73`

### Current live worker

Task 7 fix-round implementer **Archimedes**, Codex agent
`01a0406f-ec5d-7fe3-927a-8daef4b34a89`, is active. Do not dispatch another
Task 7 fixer while it is running. It owns transient changes in:

- `personal_apps/features/radar/ingest.py` — currently a deliberate teeth
  mutation may be present; do not review or preserve it until the worker
  reports that the mutation was restored.
- `personal_apps/tests/test_radar_ingest.py`
- possibly `personal_apps/tests/test_radar_daemon.py`
- an append to ignored `task-7-report.md`

Controller-owned dirty files:

- `progress.md`
- ignored `task-7-fix-round-1.md`
- ignored `task-9-brief.md`, generated and then hardened
- this `HANDOFF.md`
- ignored `task-7-review.md`

At the instant of this checkpoint, `git status --short` showed
`progress.md`, `personal_apps/features/radar/ingest.py`, and
`personal_apps/tests/test_radar_ingest.py` modified. The SDD files are ignored
unless already force-added, so their absence from status does not mean they do
not exist.

### Task 7 review and fix loop

The exceptional high-capability StockTwits review completed and wrote
`task-7-review.md`:

`VERDICT: NEEDS_FIXES | critical: 0 | important: 2 | minor: 1 | teeth: 4/6`

Production retirement is compliant. Open Important findings:

1. Surviving tests prove `missing -> ok` but not `empty healthy ok -> missing`.
   Reddit has a live no-work-due branch returning empty `ok`; a reviewer
   mutation changed every empty healthy result to `missing` and all four
   status-sensitive ingest tests still passed.
2. `test_a_source_can_opt_into_reading_coin_symbols_as_companies` calls the
   config helper directly, so mutating ingest to ignore the opt-in survives.
   It must exercise `_extract_for` or `run_cycle`.

The one Minor is deferred to final review: the StockTwits retirement pin does
not directly assert key absence from `COIN_SYMBOLS_MEAN_STOCKS`; adding a
false-valued key survives `not any(values)`.

Fix round 1 requirements are in `task-7-fix-round-1.md`. When Archimedes
returns:

1. Confirm the teeth mutations are restored and inspect its commit/report.
2. Generate a scoped review package from `a3f0b73` to the implementation HEAD
   (the intervening controller files are uncommitted/ignored, not code).
3. Run one high-capability scoped re-review because Task 7 is StockTwits.
4. If both Important findings are ADDRESSED, ledger Task 7 complete, force-add
   `task-7-review.md`, report, fix brief, progress and handoff, commit docs,
   then start Task 9. If not, continue the fix loop per SDD.

### Task 9 preflight rulings already made

Do not dispatch Task 9 from the unamended plan extract. The binding hardened
brief is `task-9-brief.md`. Codex found these load-bearing defects before any
Task 9 implementation:

1. The draft adds both `statuses['reddit']` and concrete statuses. Because
   `buckets.roll_up` treats every non-missing status key as countable, that
   writes a fake aggregate root child with zero mentions. Rollup must receive
   concrete names only whenever `per_source_status` exists.
2. Aggregate Reddit status can be `missing` after one successful sub and a
   later unavailable/throttled sub. The current `if result.status == 'missing'`
   gate would discard the successful sub's posts. Partial successes must
   survive under their concrete statuses.
3. `run_radar_ingest.score_all` iterates root `SOURCES`; after the split,
   `score_source('reddit')` matches no new rows. API expansion and scoring need
   one shared concrete-source expansion.
4. `RadarPost.source` is `String(16)`, so `reddit:wallstreetbets` cannot be
   stored. Widen it to 48 in model/migration alongside `RadarBucketSource` and
   `RadarPollState`; journal source is already 48. Cursor and poll-state keys
   stay rooted at `reddit` by design.
5. Current Alembic head is `1d26ac48e744`, not Task 1's `c489b7c94875`.
   The new migration must chain from `1d26ac48e744` and leave one head.
6. `SOURCES` and `REDDIT_SUBS` membership do not change in Task 9, so the
   promised source-config bump would otherwise not happen. Add a dedicated,
   documented source-name/population generation to the hash; do not silently
   repurpose the journal-specific `ROLLUP_GENERATION = 2`.
7. Required extra tests and mandatory teeth mutations are listed at the end of
   the hardened brief: per-sub status isolation/no root child, partial-success
   survival, three 48-character model/live DB widths, API root expansion plus
   viewer-selection echo, concrete daemon scoring, real config-version bump,
   and preservation of root cursor/poll state.

Migration note from `caveman:migration`: forward and rollback paths must be
explicit, mixed-version operation considered, retries observable, and existing
data preserved. Widening is the forward expand step. Before narrowing
`radar_posts.source` back to 16 on downgrade, prefixed posts must be normalized
to root `reddit`. Per-subreddit bucket history cannot be losslessly collapsed
to the old aggregate shape (distinct authors/text/status are not algebraically
mergeable from child summaries); the report/deploy carry must state that
semantic rollback limit rather than claim full compatibility.

### Standing continuation order and model rule

`7 fix/re-review -> 9 -> 8 -> 10-13 -> 14-17 -> 18-19 -> final review`.

Reviews stay on Sonnet except StockTwits and Reddit, which use the most capable
available reviewer. In Codex, Task 7's reviewer used `gpt-5.6-sol` at ultra.
Task 9 and Task 8 are Reddit and get the same exception. Keep implementer and
review reports in this SDD directory; subagents write full reports to file and
return only the required status line.

The frontend toolchain is installed: `tsc` is clean and vitest passed 78/78 in
Task 7. Do not repeat the superseded claim below that frontend verification is
blocked.

---

## AUTHORITATIVE CHECKPOINT — Claude to Codex, 2026-08-26 (late)

Michi stopped Claude near its session limit. **There are no active workers.**
The Task 7 implementer returned DONE and is shut down.

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`
HEAD at stop: `945c9d7` (`fix(radar): retire StockTwits, which Cloudflare has refused since launch`)
Working tree: **clean**. Nothing to rescue, nothing to discard.

### State of the plan

Complete and review-clean: **Tasks 1, 2, 3, 3b, 3c, 4, 5, 6.**

**Task 7 is IMPLEMENTED but NOT REVIEWED.** That is the whole of the open work
at this checkpoint. Its commit is `945c9d7`; its report is `task-7-report.md`
in this directory (gitignored, force-add it with the next docs commit — it is
not yet committed). The ledger does not yet record Task 7 at all.

### Codex's immediate next action

1. Read this file, `progress.md`, and `task-7-report.md` in full.
2. Verify `git status --short` is clean and `git log -1` is `945c9d7`.
3. **Dispatch the Task 7 review.** The review package is already generated:
   `.superpowers/sdd/review-73981db..945c9d7.diff` (1 commit, ~110 KB).
   Do not regenerate it. Give the reviewer that path, `task-7-brief.md`, and
   `task-7-report.md`.
4. **Michi's standing ruling on review models: Sonnet for every review EXCEPT
   StockTwits and Reddit.** Task 7 IS StockTwits — this review goes to the most
   capable model available, not Sonnet. Tasks 9 and 8 (Reddit) likewise.
5. Fix round only if the review returns Critical or Important. Then update the
   ledger, force-add the docs, and continue with Task 9.

### What the Task 7 review must scrutinise

The implementer went materially beyond the brief's file list. Most of it looks
justified, but none of it has been independently checked. Point the reviewer at:

- **Three deleted daemon tests.** `test_the_request_budget_is_a_sane_fraction_of_the_hourly_one`,
  `test_a_blocked_source_reports_missing_not_ok`, and
  `test_nothing_due_on_a_healthy_source_is_still_ok` were deleted, not renamed,
  because they called `daemon._stocktwits_fetcher` and `daemon.SYMBOL_BUDGET_PER_CYCLE`
  directly. The claim is that the general missing-vs-ok distinction stays covered
  at the `ingest.run_cycle` level. **Verify that claim by mutation** — break the
  missing-vs-ok distinction and confirm something still fails. Deleting a test
  because its subject is gone is legitimate; deleting the last thing guarding a
  surviving behaviour is not, and the two look identical from a diff.
- **Three pre-existing tests rewritten**, in `test_radar_config.py` and
  `test_radar_ingest.py`, because no surviving source has `BARE_TOKENS_ALLOWED`,
  `COIN_SYMBOLS_MEAN_STOCKS` or `SINGLE_LETTER_CASHTAGS` set `True` any more.
  They were replaced with monkeypatch-based extension-point tests. Confirm the
  replacements have teeth and are not asserting the monkeypatch rather than the
  mechanism.
- **~12 prose restatements** across `config.py`, `run_radar_ingest.py`,
  `reddit.py`, `profile.py`, `models.py:616`, `test_radar_reddit.py`,
  `test_radar_scheduling.py`. The rule applied was: present-tense claims that
  StockTwits is live or shares a mechanism get restated; past-tense measurements
  and incidents stay as history. Spot-check that line.
- `models.py:660` (`count_stocktwits`) and
  `test_radar_bucket_sources.py:114-116` were deliberately LEFT — real historical
  column names from migrations `7883c6e08708` and `01da83522036`. Correct call;
  do not let a reviewer "fix" them. The migration files themselves were never
  touched, which is also correct.

### Two things that change how later tasks are planned

**1. The frontend is NOT blocked. The standing note in this file saying `tsc` is
not installed is now WRONG.** The Task 7 implementer ran a real `npm install`:
`tsc` type-checks clean and **vitest passes 78/78**, including
`BoardPage.test.tsx`. Tasks 11, 15 and 16 touch the frontend and were planned
around that command being unavailable — replan them with the runner available.
Side effect: `node_modules/` now exists on disk in the worktree. It is
gitignored and harmless.

**2. `source_config_version()` moved, as the brief intended:**
`fc1a0ee4cab51d65` → `8106787f1fa72179`. It bumped automatically from the
`SOURCES` hash with no manual edit. **Deploy carry:** this starts a baseline
warm-up on deploy — buckets stamped with the old version are outside current
baselines until enough new-generation history accumulates. Expected, not a bug.

### Test-count bookkeeping

The broad gate now reports **594 passed, 2 skipped**, plus exactly the two
known API template failures from the missing gitignored
`personal_apps/static/radar/dist/.vite/manifest.json`. It read 605 before
Task 7. The drop is the 11 deleted `test_radar_stocktwits.py` tests and the 3
deleted daemon tests, less the new tests added. Do not read the drop as a
regression, and do not fix the two manifest failures.

### Remaining order

**7 review → 9 → 8 → 10-13 → 14-17 → 18-19 → final branch review.**

Task 9 precedes Task 8 by standing ruling: Reddit's aggregate status is the
wrong population, so no truncated observation is made scoreable until each
subreddit owns its own status. Batch the rest per the ceremony table further
down this file — Michi's call, made on cost.

### Deferred Minors the final branch review must triage

- **Task 4+5:** `_extract_for` says four per-source judgements but its prose
  enumerates only three, omitting the single-letter-cashtag judgement.
- **Task 6:** the `int()`-at-the-boundary comment claims `COUNT` returns
  `Decimal`; empirically only `SUM` does on this driver. Left because the same
  phrasing is an existing house convention at `features/radar/journal.py:204`.
  Misleads a reader, changes no behaviour.

---

The material below is historical context from earlier handoffs. Where it
conflicts with the checkpoint above, the checkpoint above wins — in particular
its `tsc`-is-not-installed claim is now disproved, and its "Task 6 is not
started" checkpoint is closed.


Written 2026-08-26 by Claude, handing to Codex at a session limit.

## Superseded: Codex-to-Claude stop checkpoint, 2026-08-26 (Task 6 now complete)

Michi asked Codex to stop because the Codex session was near its limit. The
Task 6 implementer Socrates (`01a03f75-a03d-78f1-a7e1-b8e700f41c42`) was
interrupted and is now shut down. **There are no active workers.**

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`

Branch: `codex/radar-pipeline-audit`

HEAD at stop: `ee24d65` (`docs(radar): close config cleanup and pin backfill safety`)

Exact working-tree state at stop:

- Modified: this `HANDOFF.md` only, to record the stop.
- Ignored/untracked: `task-7-brief.md`; it is intentionally force-added by the
  handoff checkpoint commit so Claude has the prepared Task 7 package.
- No Task 6 implementation or test files were created or modified. In
  particular, `personal_apps/scripts/backfill_radar_buckets.py`,
  `personal_apps/tests/test_radar_backfill.py`, and `task-6-report.md` do not
  exist as work in progress. Nothing needs to be rescued or discarded.

Completed and review-clean: Tasks 1, 2, 3, 3b, 3c, 4 and 5. Task 4+5 has one
deferred Minor for final review: `_extract_for` says four source judgements but
its prose enumerates only three. No production issue was found there.

Task 6 is **not started**. Its authoritative implementation package is
`task-6-brief.md`, and the plan/ledger contain the hardened safety requirements:
`ticker_prefix='ZZBF'` isolation in every test, genuine dry-run rollback,
apply/idempotence, Decimal conversion, all four score fields cleared, status
and old source-config version preserved, secondary aggregates repaired even
when the high count is equal, and stale cleanup keyed on any non-NULL score.

### Claude's immediate next action

1. Read this file, `progress.md`, the plan/spec, and `task-6-brief.md` in full.
2. Verify `git status --short`, `git log -5 --oneline`, and that HEAD is the
   handoff checkpoint commit written after `ee24d65`.
3. Start Task 6 from scratch using TDD. Do not rerun or rewrite completed tasks.
4. Run the focused Task 6 gate, the script's real dry-run path, and then
   `python -m pytest tests/ -k radar -q` from `personal_apps`.
5. Commit only Task 6 files/report and send that commit through one independent
   review before advancing.

Remaining order: **6, 7, 9, 8, 10–13, 14–17, 18–19, final branch review**.
Task 9 deliberately precedes Task 8 because Reddit aggregate status is the
wrong population until each subreddit owns its own status. `task-7-brief.md`
is prepared but Task 7 must not start before Task 6 is complete and reviewed.

The broad gate most recently passed 601 radar tests plus exactly two known API
template failures caused by the missing ignored
`personal_apps/static/radar/dist/.vite/manifest.json`. Do not treat those two
as a Radar backend regression and do not fix them in these tasks. Production
is MariaDB; tests use the real shared local MySQL database.

The material below is historical context from earlier handoffs. Where it says
Task 3c or Task 6 is active, this authoritative checkpoint supersedes it.

## Codex continuation checkpoint — 2026-08-26, session ~50%

Codex verified the original handoff against Git, reports and tests, then
continued in the same isolated worktree. The cross-agent handoff protocol is
now also persisted globally in both `C:\Users\michi\.codex\AGENTS.md` and
`C:\Users\michi\.claude\CLAUDE.md` (outside this repository).

Current branch/worktree: `codex/radar-pipeline-audit` at
`C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`.

Current committed sequence:

- `7791963` — Task 3c implementation.
- `c0f6f6b` — Claude→Codex handoff/report/fix brief checkpoint.
- `c553c47` — Task 3c fix round 1: all eight Claude review findings fixed.
- `4850c9a` — Task 3c fix round 2: shared scoring-test cleanup scoped to
  exact owned tickers with an unowned-ZZ sentinel regression.
- `fa66e70` — Task 3c fix round 3: remove query-only `SSNOPE`; replace the
  fixed/pre-deleted sentinel with a unique 12-character exact-cleanup ticker.

Task 3c re-review verdict on `c0f6f6b..c553c47`: all eight original findings
ADDRESSED, but NOT APPROVED because `test_radar_scoring.rows` broadened shared
DB cleanup to every `ZZ%` ticker. That can erase another test's or user's data.

Task 3c is COMPLETE and review-clean through `fa66e70`. Final scoped review
approved both remaining shared-DB findings. Its six-file gate is 141 passed;
latest broad radar gate is 598 passed plus exactly the two known missing-Vite-
manifest API template failures.

Tasks 4+5 are complete in `c6ff071`: spec review approved, no Critical or
Important findings; broad radar gate 601 passed plus the two known manifest
failures. One deferred Minor is in the ledger: `_extract_for` says four source
judgements but enumerates three. The final branch review must triage it.

Controller checkpoint committed as `ee24d65`. **Active work:** Task 6 is running
with implementer Socrates (`01a03f75-a03d-78f1-a7e1-b8e700f41c42`) from the
hardened `task-6-brief.md`. Immediate next action: inspect its commit/report,
generate a review package from `ee24d65` to its HEAD, and run one independent
review focused on dry-run/apply safety, shared-DB isolation, Decimal boundaries,
partial lower-bound semantics, stale-score NULLs and idempotence.

Latest verified tests before fix round 2: Task 3c covering gate 140 passed;
broad radar gate 598 passed with exactly the two known missing-Vite-manifest
API template failures.

Expected dirty state while fix round 2 runs:

- `personal_apps/tests/test_radar_scoring.py` — implementer-owned fix.
- `docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md` —
  controller-owned Task 6 safety/test amendment; do not stage with Task 3c.
- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/progress.md` —
  controller-owned ledger updates; do not stage with Task 3c.
- `personal_apps/run_radar_ingest.py` may appear modified from line-ending/stat
  churn, but its blob hash equals HEAD (`3f9263b4...`) and `git diff` is empty.

Task 6 plan amendment pending a controller docs commit: add real dry-run,
apply, idempotence, Decimal, stale-score and shared-DB isolation tests; compare
all recoverable lower-bound fields; scope tests with `ticker_prefix='ZZBF'`.

Plan: `docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md`
Spec: `docs/superpowers/specs/2026-08-26-radar-pipeline-audit-design.md`
Ledger: `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/progress.md`

## Where things stand

| Branch | Commit | State |
|---|---|---|
| `dev_personal` (main checkout) | `b9c8ef8` | Tasks 1, 2, 3, 3b done. Green: 587 radar tests. |
| `codex/radar-pipeline-audit` (worktree) | `7791963` | Task 3c implemented and reviewed. Ahead of `dev_personal`. |

Work in the worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`.
`dev_personal` fast-forwards onto this branch when the work is done.

Tasks complete: **1, 2, 3, 3b, 3c** (3c pending its fix round, below).
Tasks remaining: **4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19**.

## IMMEDIATE NEXT ACTION — Task 3c fix round

An Opus review of `7791963` found the **production logic correct in all seven
behaviours**. Every gap is in the tests: several behaviours can be deleted or
inverted with the whole suite staying green. Eight findings, none yet fixed.

`personal_apps/tests/test_radar_daemon.py` is **modified and uncommitted** —
that is the reviewer's own rewrite for Finding 1, written but never verified.
Keep it, verify it has teeth, do not assume it is right.

### Important

**1. `main()` can swallow the fail-closed abort and every test stays green.**
The old test asserted only that three substrings appear in
`inspect.getsource(daemon.main)` in order. Wrapping the
`_prepare_rollup_generation` call in `try/except Exception: recovered,
invalidated = 0, 0` left the substrings in place, all 40 daemon tests green,
and the daemon starting ingest over evidence it could not recover.
The replacement test is in the working tree. Re-apply that exact wrapper,
confirm the test FAILS, revert the wrapper. Do not commit the wrapper.

**2. Behaviour 5's generation filter is unpinned, and deleting it puts a
phantom spike on the board.** `scoring._rows_by_ticker` filters to
current-generation rows. Delete the filter and the entire radar suite stays
green, because every existing test uses tickers whose rows are *entirely*
incompatible — so `baselines.usable()`'s pre-existing filter already covers
them. The missing case: a ticker with 30 days of current-generation history
PLUS one old-generation `ok` row inside the same lookback, so `usable()` still
yields a baseline and the row-level write loop is handed every row. Without
the filter the reviewer measured:

```
AssertionError: a generation-1 row was given a generation-2 z-score of 31.5298
```

`pooled_z` and `window_z` both select on `mention_z.isnot(None)`, so that row
reaches the leaderboard as a 31-sigma spike. Write the regression in
`tests/test_radar_scoring.py` (~20 lines), watch it fail with the filter
deleted, restore the filter.

**3. Four new tests are one ingest cycle from failing, today.**
`tests/test_radar_daemon.py` (the `now = 2026-08-26 06:00` cases) and
`tests/test_radar_journal.py:338-339` (`assert recovered == 1` /
`assert invalidated == 1`) take GLOBAL counts over the shared local dev
database, and today is 2026-08-26. Demonstrated: one ordinary `NVDA` bucket at
`2026-08-26 05:00` makes the "genuinely quiet" test raise `RuntimeError`; one
old-generation scored row at `2026-08-25` turns `assert invalidated == 1` into
`assert 2 == 1`. `personal_apps/scratchpad/seed_radar_dev.py` seeds 32 days
back from `now`, so re-running the dev seeder fills the window outright.
Move each affected `now` to **2027-06-01**, beyond any real or seeded row, and
confirm the shift did not move any test's meaning.

### Minor

**4.** `_prepare_rollup_generation`'s `db.session.commit()` is unpinned. Remove
it and all 49 daemon+journal tests stay green — but in production the
`invalidate_incompatible_scores` bulk UPDATE (`synchronize_session=False`) is
discarded when the `app_context()` block tears down, so startup invalidation
silently does nothing while still logging a non-zero count.

**5.** Nothing pins WHICH version reaches invalidation. Replace
`source_config_version()` with `'wrong-version'` at the call site and all 49
tests stay green. In production a wrong version also clears *current*-generation
scores. `test_prepare_rollup_generation_bootstraps_then_invalidates_then_commits`
already captures `calls[1][1]` — make it assert on it.

**6.** The `high_confidence_count > 0` predicate is unpinned. Weaken it to
`>= 0` and all 49 tests stay green, because the dev database holds zero rows of
any kind in the test window, so "no legacy row" and "no legacy row carrying
evidence" are indistinguishable there. Under `>= 0` the daemon fails closed on
ANY bucket in the window — including a `missing`-status row with no mentions —
which is the spurious 3am page. Add one `high_confidence_count=0` row to the
quiet test to separate the two.

**7.** The "carries at least one non-NULL score column" guard in `scoring.py` is
unpinned. Replace the `sa.or_(… isnot(None) …)` block with `sa.true()` and the
scoring suite stays green. Without it the UPDATE writes NULL over NULL on every
unscored row in a 30-day window, four times per scoring pass.

**8.** (efficiency) `score_source`'s defensive `invalidate_incompatible_scores`
call has no `source` filter, so `score_all` runs it four times per pass over the
same rows — a write-locking 30-day range scan matching zero rows in steady
state. Add `RadarBucketSource.source == source` there; keep the startup call
unscoped so it still covers every source.

**Skipped deliberately:** a ninth finding about continuation lines sitting one
column short of the file's visual-indent convention. Cosmetic, no linter config
exists in the repo.

## After 3c: run the rest in BATCHES, not one task at a time

Michi's call, and the reason is cost. The per-task ceremony
(implement → review → fix → re-review) ran ~1 hour regardless of whether the
task was a schema migration or deleting one constant. Task 17 is a docstring.
Task 5 deletes one constant. Those do not need four dispatches.

| Unit | Tasks | Ceremony |
|---|---|---|
| Config cleanup | 4 + 5 | one implement, one review |
| Backfill script | 6 | one implement, one review |
| Retire StockTwits | 7 | FULL loop — touches 8 test files |
| Reddit | 9 **then** 8 | FULL loop — the real remaining engineering |
| Absence-shaped | 10 + 11 + 12 + 13 | one implement, one review |
| Tone and marks | 14 + 15 + 16 + 17 | one implement, one review |
| Ops | 18 + 19 | one implement, one review |

Re-review only when a review returns something Important or Critical.

**Task 9 runs before Task 8** — ruling already in the ledger. Reddit's aggregate
status is known to be the wrong population; score truncated rows only after each
subreddit owns its own status.

**Task 5 changed.** The original plan's universal config-reachability test was
rejected and replaced with targeted behavioural guards: the draft counted
comments, docstrings and unused imports as call sites, so it would have passed
the exact dead-hook defect it claimed to prevent. The plan is already amended.

## Conventions that must not drift

- **cwd is split.** Run `pytest` and `flask` from the worktree's `personal_apps`;
  run `git` from the worktree root.
- **Do not touch** `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`,
  `personal_apps/reddit_candidates.json` — Michi's unrelated work in progress.
  Stage only the files a task changes, by name. Never commit on `main`.
- **Tests share the REAL local dev MySQL database.** No test database, no
  transactional rollback. Fixtures namespace on tickers matching `ZZ%` and clean
  up both before and after, including `radar_mention_events`.
- **The gate** is `python -m pytest tests/ -k radar -q`, currently **595 passed
  with 2 pre-existing failures** from a missing `static/radar/dist` Vite build
  (built assets are gitignored and absent in this worktree). Those two are
  expected — confirm they are the only failures, do not fix them.
- **`tsc` is reportedly not installed locally**, so `npm run build` cannot run.
  Tasks 11, 15 and 16 touch the frontend and name that command. Verify before
  planning around it.
- **The teeth experiment is mandatory.** Every test whose passing state is an
  absence — a NULL, an exclusion, a count that did not grow — must be WATCHED
  FAILING under the mutation it targets, then the mutation reverted. All eight
  3c findings exist because that step was skipped. This is the single highest
  yield rule in the whole plan.
- **The circular import between `buckets.py` and `journal.py` is deliberate and
  fragile.** `journal.py` imports `buckets` as a MODULE and calls
  `buckets.MentionRow(...)` at call time; `buckets.py` does `from . import
  journal` at the top. A name-import in either direction breaks it. Verify with
  fresh processes: `python -c "from features.radar import buckets"`,
  `... import journal`, `... import ingest`.
- **This ledger directory is gitignored** (`.gitignore:8`) and force-added
  anyway. Keep force-adding it — it is what makes the handoff survive.

## Standing rules from the audit

- **An absence is never a zero.** A missing verdict, a failed fetch, an unpriced
  model and an unobserved bucket all stay NULL.
- **SQL NULL is not Python None.** `column != 'x'` does not match NULL rows.
- **Production is MariaDB, local dev is MySQL 8.** Both must accept every query.
  `CAST(... AS JSON)` is a parse error on MariaDB, and DDL there commits even
  when the surrounding migration then fails.
- **Every datetime is naive UTC.** Never `utcnow()`.
- **`int()` at the query boundary** — `COUNT()`/`SUM()` return Decimal on both
  engines, and Decimal reaching float maths or `jsonify` has bitten this
  codebase before.
- **`source_config_version()` moves only** for changes to WHICH mentions get
  counted — not for changes to how a counted mention is scored or aggregated.
- **Green and red are reserved for price direction** anywhere on the surface.
- **Decided, do not re-propose:** using a model to judge whether a token is a
  ticker (measured and killed — volume-gating selects the junk); dropping either
  the lexicon or the model sentiment score (their disagreement is the sarcasm
  detector); green/red for anything but price direction.

## Deploy carries, for whoever merges

- The journal is empty at deploy, so the first cycle touching an already-written
  bucket rebuilds it from the post-deploy slice alone and erases its pre-deploy
  counts. Bounded to the quarter-hour open at deploy, wider if that first cycle
  is a catch-up. Task 3c's bootstrap is what addresses this — verify it ran.
- Task 6's backfill script must be run against production after deploy: once as
  a dry run, then with `--apply`. It repairs understated bucket counts AND
  clears the 399 rows carrying a score they earned under a different status.

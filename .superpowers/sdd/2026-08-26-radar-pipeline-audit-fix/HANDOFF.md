# HANDOFF — radar pipeline audit fix

Written 2026-08-26 by Claude, handing to Codex at a session limit.

## AUTHORITATIVE STOP CHECKPOINT — Codex to Claude, 2026-08-26

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

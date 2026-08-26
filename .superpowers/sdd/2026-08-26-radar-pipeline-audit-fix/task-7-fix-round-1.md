# Task 7 fix round 1/5

Read `task-7-brief.md`, `task-7-report.md`, and `task-7-review.md` first.
Task 7's production removal is approved; this round fixes only the two open
Important test-teeth findings below.

## Important 1 — healthy empty fetch can regress to missing

The surviving `run_cycle` tests cover `missing -> ok`, but no test proves an
empty healthy `FetchResult(posts=[], status='ok')` remains `ok`. The reviewer
mutated every empty healthy result to `missing`; all four status-sensitive
tests still passed. Reddit has a live no-work-due branch returning empty `ok`.

Add a behavioral regression in `personal_apps/tests/test_radar_ingest.py` that
passes an empty healthy result through `run_cycle`, asserts the source remains
`ok`, and leaves no database artifact. Also adapt/preserve the no-due Reddit
fetcher behavior in `test_radar_daemon.py` if that is the clearest way to pin
the live branch. Use exact `ZZ%` ownership and exact cleanup where DB rows are
involved.

Teeth requirement: temporarily mutate the production boundary so an empty
healthy result becomes `missing`, run the focused test and record its observed
failure, then restore production code before committing.

## Important 2 — coin-symbol opt-in test bypasses ingest

`test_a_source_can_opt_into_reading_coin_symbols_as_companies` currently
monkeypatches config and calls `config.coin_collision_dropped` directly. A
mutation at `features/radar/ingest.py` that ignores the opt-in survives. Rewrite
this test so it exercises `ingest._extract_for` or `run_cycle` and proves `$LINK`
is admitted as a high-confidence company mention when the source opts in.

Teeth requirement: temporarily make ingest ignore the opt-in, run the focused
test and record its observed failure, then restore production code.

## Scope and report

- Do not change production behavior unless a test cannot be written against
  the existing intended behavior; if that happens, return `NEEDS_CONTEXT`.
- Do not address the review's Minor finding in this round.
- Do not touch migrations, protected discovery/candidate files, or controller
  artifacts.
- Run the focused amended tests and the relevant ingest/daemon covering files.
- Append the fix-round evidence, commands, outputs, changed files, and commit
  SHA to `task-7-report.md`.
- Commit only Task 7 fix files.
- Do not dispatch subagents.

Return only:
`STATUS: DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED | commit: <sha> | tests: <one line> | concerns: <one line>`

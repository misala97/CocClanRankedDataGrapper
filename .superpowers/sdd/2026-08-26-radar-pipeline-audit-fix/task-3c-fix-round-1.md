# Task 3c fix round 1 — test teeth and scoped invalidation

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`

Read first:

- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/task-3c-brief.md`
- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/task-3c-report.md`
- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/HANDOFF.md`

Base reviewed commit: `7791963`. Production logic satisfied the seven binding
behaviours, but its tests did not prove several of them. The working tree already
contains the reviewer's uncommitted rewrite of
`personal_apps/tests/test_radar_daemon.py::test_main_prepares_the_rollup_generation_before_building_fetchers`.
Own that change: inspect it, verify its mutation, and commit it only if correct.

Address all eight review findings with red/green mutation evidence:

1. Runtime-test fail-closed `main()`. Temporarily catch and swallow
   `_prepare_rollup_generation`'s exception in `main()` and prove the rewritten test
   fails because `build_fetchers` runs; restore production code and prove it passes.
2. Pin `_rows_by_ticker`'s exact-generation filter with one ticker containing enough
   current-generation history to score plus one incompatible `ok` row in the same
   lookback. With the SQL generation predicate temporarily deleted, prove the old row
   receives a phantom z-score; restore it and assert that row remains unscored.
3. Move every new Task 3c global-window test date in `test_radar_daemon.py` and
   `test_radar_journal.py` to `2027-06-01` (with nearby offsets as needed), beyond
   real and seeded rows. Do not change the behaviour being asserted.
4. Pin `_prepare_rollup_generation`'s `db.session.commit()`. The wiring test must
   observe bootstrap, invalidation, then commit in that order; deleting the commit
   must fail it.
5. In that wiring test assert invalidation receives the exact current
   `source_config_version()`. Replacing the call-site value with a wrong literal must
   fail.
6. In the quiet-database test seed an incompatible/legacy bucket in the overlap
   window with `high_confidence_count=0`. The path must continue. Mutating the
   production predicate from `> 0` to `>= 0` must fail.
7. Pin the score-presence guard in `invalidate_incompatible_scores`: an incompatible
   row whose four score columns are already NULL must not be counted/written. Replacing
   the `isnot(None)` disjunction with an unconditional predicate must fail.
8. Avoid four identical 30-day range scans in `score_all`. Extend
   `invalidate_incompatible_scores` with an optional source scope. `score_source`
   passes its source; startup omits it and remains all-source. Add tests proving both
   call paths. Mutation/removal of the scorer's source scope must fail.

Constraints:

- Naive UTC only. SQL NULL is explicitly incompatible; absence remains NULL, never 0.
- Preserve Task 3c production semantics except the optional source scope in finding 8.
- Tests use the real shared dev DB. Namespace created rows with `ZZ...` tickers and
  clean before/after. Never rely on global row counts in an occupied time window.
- Do not touch unrelated Telegram files, plan/spec/ledger/HANDOFF, or later tasks.
- One implementation worker only; do not spawn helpers or reviewers.
- Append a complete fix-round section to `task-3c-report.md`: watched failing
  mutations, final commands/output, files, commit, concerns.

Covering gate from `personal_apps`:

```text
py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_profile.py tests/test_radar_scoring.py tests/test_radar_daemon.py -v
py -3.12 -m pytest tests/ -k radar -q
```

The known broad-gate baseline is 595 passed plus exactly two unrelated API-template
failures caused by the missing ignored Vite manifest.

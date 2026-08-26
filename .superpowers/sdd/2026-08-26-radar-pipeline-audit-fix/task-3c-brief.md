## Task 3c implementation brief: start a compatible rollup generation safely

Work only in `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`.
Implement Task 3c from
`docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md` exactly as now
amended. Use red/green TDD, run the named covering tests plus
`py -3.12 -m pytest tests/ -k radar -q` from `personal_apps`, commit only the
listed Task 3c files, and write a report to
`.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/task-3c-report.md`.

The binding behavior is:

1. Add `config.ROLLUP_GENERATION = 2` to the explicit
   `source_config_version()` payload.
2. Add idempotent `journal.bootstrap_from_mentions(since) -> int`, recovering
   retained high/low `RadarPost x RadarMention` evidence through `record()`.
3. Make `profile.build_profile(source, until, config_version, weeks=...)`
   require and filter the exact compatibility version; update all callers.
4. Add `scoring.invalidate_incompatible_scores(version, since) -> int` for SQL
   NULL or different versions with any score field present. Startup invokes it
   before ingest; scorer invokes it defensively only in its active lookback.
5. `_rows_by_ticker` and `score_source` may read/write only current-generation
   rows. `score_source` passes the current version to the profile builder.
6. In `buckets.roll_up`, capture an existing child version before restamping.
   NULL/different generation clears expected, variance, mention_z and
   baseline_days regardless of status. Same-generation `ok` refresh preserves
   scores; Task 3's non-`ok` clearing remains.
7. Add `_prepare_rollup_generation(now)` to the daemon. It opens app context,
   bootstraps the retention window, fails closed if recovered is zero while a
   legacy bucket in that window has `high_confidence_count > 0`, invalidates
   incompatible scores, commits, and returns/logs counts. `main()` calls it
   before `build_fetchers` or scheduler creation. Exceptions propagate.

Required regressions include: hash boundary; required versioned profile and
scorer wiring; explicit old hash plus real SQL NULL with all four score fields
seeded; bucket restamp clearing versus same-generation preservation; bootstrap
field fidelity/idempotence; the full deploy-boundary integration case; zero-
bootstrap invariant; and startup ordering/failure. Use naive UTC datetimes.

Do not add an unversioned profile fallback, journal generation column, board
schema migration, full-history 15-minute scan, or manual mutation exercise.
Do not modify the controller-owned spec, plan, ledger, or Task 3b files.

# Task 3b fix round 1 report

## Fix

`journal.mark_promoted()` now replaces the current promotion decision for every
recomputed low/medium event: it resets those rows to `promoted=False`, then
sets only the rows that `_promote()` currently made `medium` to `True`. This
keeps extractor confidence frozen and leaves the existing 15-minute window and
`MAX_BARE_PER_VOUCHER` rules unchanged.

The new journal regression reaches the cap with one high voucher and four bare
mentions, verifies those bare event flags are true, then adds a fifth bare
event in the same bucket. It proves all five flags are false after recompute,
the journal counts only the high voucher as one distinct voice, and the bucket
has one scored mention.

## Files changed

- `personal_apps/features/radar/journal.py`
- `personal_apps/tests/test_radar_journal.py`
- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/task-3b-report.md`

## Watched failing regression

Before changing production code:

```text
$ py -3.12 -m pytest tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions -v
tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions FAILED [100%]
E       assert False
E        +  where False = all(<generator object ...>)
============================== 1 failed in 1.81s ==============================
```

The failure was at `assert all(not event.promoted for event in bare_events)`:
the first four bare rows retained their earlier `promoted=True` decision after
the fifth bare mention exceeded the cap.

## Test commands and outputs

```text
$ py -3.12 -m pytest tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions -v
tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions PASSED [100%]
============================== 1 passed in 0.21s ==============================

$ py -3.12 -m flask db upgrade
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.

$ py -3.12 -m pytest tests/test_radar_leaderboard.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_bucket_sources.py -v
collected 66 items
============================= 66 passed in 2.30s ==============================
```

Teeth check: temporarily restored the original one-way, true-only
`mark_promoted()` implementation, then ran the new regression:

```text
$ py -3.12 -m pytest tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions -v
tests/test_radar_journal.py::test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions FAILED [100%]
E       assert False
E        +  where False = all(<generator object ...>)
============================== 1 failed in 1.66s ==============================
```

Restored the correction immediately, then reran the passing focused regression
and the 66-test Task 3b covering set above.

The brief's full gate was also run:

```text
$ py -3.12 -m pytest tests/ -k radar -v
collected 1233 items / 646 deselected / 587 selected
585 passed, 2 failed
```

The only failures were the unrelated page tests
`test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch` and
`test_the_page_falls_back_to_the_default_board_on_a_bad_query`. Both fail
while rendering `templates/radar/board.html` because this fork lacks the
ignored `static/radar/dist/.vite/manifest.json`; neither traceback reaches a
Task 3b file. The repository's prescribed prerequisite also could not run:

```text
$ npm run build
> build
> tsc --noEmit && vite build && vite build -c vite.radar.config.ts
Der Befehl "tsc" ist entweder falsch geschrieben oder konnte nicht gefunden werden.
```

## Commit

Commit: the commit containing this report (`fix(radar): reset stale promotion decisions`).

## Concerns

- The focused Task 3b regression and covering suites pass.
- The full radar gate is blocked only by missing frontend build artifacts and
  the absent local TypeScript toolchain in this fork. No source, Telegram, or
  unrelated files were changed to work around that environment issue.

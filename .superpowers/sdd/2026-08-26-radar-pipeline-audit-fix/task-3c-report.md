# Task 3c report: start a compatible rollup generation safely

Branch `codex/radar-pipeline-audit`, worktree
`C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`.

## Summary

Implemented all seven binding behaviours from
`.superpowers/sdd/task-3c-brief.md` (the plan-derived path, per the
instruction that it governs over the condensed copy inside the worktree --
in the end the two were identical for everything that mattered). The
inherited red-state tests were sound in their assertions against the brief;
two were mechanically broken (an editing accident, not a design
disagreement) and two needed a date change to stay isolated from real
seeded data in this specific dev database. Both are described below with
full reasoning. I also added daemon-level tests for the fail-closed startup
behaviour that the inherited diff had not reached yet.

## What changed and why

**`personal_apps/features/radar/config.py`** -- added
`ROLLUP_GENERATION = 2` and folded `'rollup_generation': ROLLUP_GENERATION`
into `source_config_version()`'s hashed payload. This is the only new input
to the hash; nothing about extraction membership changed, but a change to
how completely a bucket's count is aggregated is exactly the kind of
discontinuity the stamp exists to wall off.

**`personal_apps/features/radar/journal.py`** -- added
`bootstrap_from_mentions(since) -> int`, implemented verbatim from the
brief's pseudocode: joins `RadarMention` to `RadarPost`, filters
`created_utc >= since` and `confidence IN ('high', 'low')`, builds
`buckets.MentionRow` objects (engagement = `score + num_comments`,
`medium` never invented), and replays them through the existing `record()`
path, which is idempotent through record's own unique key. Returns
`len(recovered)`, i.e. rows *found*, not rows newly inserted -- calling it
twice returns the same count both times while leaving one event per
`(source, external_id, ticker)`.

**`personal_apps/features/radar/buckets.py`** -- in `roll_up`, `child`'s
`source_config_version` is now read into `previous_version` *before* the
loop restamps it. The existing `if child.status != 'ok':` clear became
`if child.status != 'ok' or previous_version != version:` -- one condition
covering both reasons a stored score stops being trustworthy: a status
leaving `ok`, or a generation that no longer matches (NULL included, since
a brand-new row's unset `source_config_version` reads as Python `None`,
which `!=` already treats as a mismatch). A same-generation `ok` refresh
still skips both clauses and keeps its scores.

**`personal_apps/features/radar/profile.py`** -- `build_profile` now
requires `config_version` as its third positional parameter and filters the
query by `RadarBucketSource.source_config_version == config_version`. No
optional/fallback mode, per the brief. Its only production caller is
`scoring.score_source`, updated to pass the current version through.

**`personal_apps/features/radar/scoring.py`**:
- `_rows_by_ticker` gained a required `config_version` parameter and now
  filters its query to exact-version rows only. Reasoning captured in the
  new docstring: `baselines.usable()` already filters incompatible rows out
  of the *rate estimate*, but the write loop beneath it scores every `ok`
  row it is handed regardless of version -- so without this filter, a
  ticker straddling a generation boundary (some current rows plus one old
  row `invalidate_incompatible_scores` had not yet reached) could have its
  old row overwritten with a fresh z computed from the *current* baseline,
  disguising it as current while its own stamp still said otherwise.
- Added `invalidate_incompatible_scores(version, since) -> int`: a bulk
  UPDATE clearing the four score columns on rows at or after `since` whose
  `source_config_version` is SQL NULL (tested with `.is_(None)`, not `!=`,
  since NULL never satisfies `!=` in SQL) or differs from `version`, and
  which carry at least one non-NULL score column.
- `score_source` now computes `version` first, calls
  `invalidate_incompatible_scores(version, since)` defensively before doing
  anything else (comment explains this is a backstop for whatever the
  startup-time pass at the wider retention window does not reach, scoped to
  `lookback_days` rather than a full scan), then passes `version` into both
  `profile.build_profile` and `_rows_by_ticker`.

**`personal_apps/run_radar_ingest.py`** -- added `_prepare_rollup_generation
(now)`: opens `app.app_context()`, computes `since = now (naive) -
MENTION_EVENT_RETENTION_HOURS`, calls `journal.bootstrap_from_mentions
(since)`, and if that recovers zero events, queries the same window for any
`RadarBucketSource` with `high_confidence_count > 0` (no ticker filter, by
design -- production must catch any source's bootstrap failure, not one
ticker's) and raises `RuntimeError` if one exists. Otherwise it calls
`scoring.invalidate_incompatible_scores(source_config_version(), since)`,
commits, and returns `(recovered, invalidated)`. `main()` calls this before
`build_fetchers()` or the scheduler, with no try/except, logs both counts,
and lets any exception abort startup.

## Assessment of the inherited tests

**Sound, and correctly derived from the brief:** all of
`test_version_changes_when_the_rollup_generation_changes`
(test_radar_config.py), `test_a_profile_uses_only_its_exact_config_
generation` (test_radar_profile.py), `test_scoring_passes_the_current_
generation_to_the_profile` and `test_scoring_clears_old_and_sql_null_
scores_inside_its_lookback` (test_radar_scoring.py), and
`test_a_generation_restamp_clears_every_stale_score[None|old-generation]`
(test_radar_buckets.py). I traced each one against the exact clause of the
brief it exercises and none asked for behaviour the brief did not specify,
nor contradicted it. The scoring test correctly seeds a real SQL NULL
(assigns Python `None` to the ORM attribute and commits, which persists as
NULL) alongside an explicit old-hash row, and seeds all four score columns
first, so it has teeth against the pre-fix code -- I confirmed this
analytically: under the unmodified `score_source`, a ticker whose only rows
are old-version would hit `if not good: continue` before ever reaching the
row-level write loop, meaning its stale scores were never touched at all,
which is exactly what the new test catches.

**Two mechanical defects, not disagreements with the brief**, both in
`test_radar_journal.py`'s new `clean_retained_mentions` fixture:

1. It had two `yield` statements. Reading the diff against HEAD made the
   cause obvious: while inserting the new fixture, the interrupted agent's
   edit accidentally cut `clean_events`' own teardown half (the code after
   its `yield`) out of `clean_events` and pasted it, verbatim, onto the end
   of `clean_retained_mentions` -- one slip that broke two fixtures at
   once. I confirmed this by diffing the committed HEAD version of
   `clean_events`, which still had its `yield` and teardown intact. Fix:
   removed the duplicated tail from `clean_retained_mentions` and restored
   `clean_events` to its committed form. This alone turned 2 of the
   original run's failures into passes (`test_the_table_accepts_one_event`,
   `test_the_same_mention_cannot_be_stored_twice`) -- neither test touches
   anything Task-3c-related; they were pure collateral damage from the
   editing accident, confirmed by running them in total isolation both
   before and after the fix.

2. `bootstrap_from_mentions` has *no ticker filter* -- correctly, per the
   brief's own pseudocode, since production must recover every retained
   decision in the window, not one ticker's. The two inherited tests that
   exercise it used this file's usual `2026-04-15` convention for isolation.
   That convention works everywhere else in this file because every other
   function here is ticker- or bucket-scoped. It does not work for an
   unbounded `created_utc >= since` scan: I found the dev database holds
   1,432 real seeded `RadarPost`/`RadarMention` rows dated 2026-08-22/23
   (from `scratchpad/seed_radar_dev.py`) and 32,005 `RadarBucketSource` rows
   back to 2026-07-22. `2026-04-15` is *before* all of that, and the query
   has no upper bound, so it matched all 1,432 rows in addition to the
   test's own two. I moved both tests' dates to 2026-08-24/25/26 (confirmed
   empirically to be clear of every real row in both tables -- see the
   probe queries in the command log below) and added a `created_utc`
   override parameter to the shared `_row()` helper so only these two tests
   needed to move; every other test in the file keeps its original
   2026-04-15 dates unchanged. This is an environment-specific isolation
   gap in the chosen constants, not a logic error, and not something any
   implementation could have satisfied while the real rows exist -- no
   fix to `bootstrap_from_mentions` itself could make it ignore rows within
   its own stated time window.

**Gap, not a defect -- filled rather than reported:** the inherited diff
touched five files, not six. `test_radar_daemon.py` was untouched, even
though the brief's Step 1 item 7 calls for proving the fail-closed startup
behaviour, and both the brief and plan list it under "Modify" and in the
Step 5 covering-test command. (The task instructions I was given separately
name only the five files in the "COVERING TESTS" block, which is a real
difference in scope between the two documents.) I added four tests to
`test_radar_daemon.py`:

- `test_prepare_rollup_generation_bootstraps_then_invalidates_then_commits`
  -- pure wiring/order check, fully monkeypatched, no real DB writes.
- `test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_
  evidence` -- seeds one real `RadarBucketSource` row (`ZZDAEMON`,
  `high_confidence_count=6`) in the overlap window, stubs bootstrap to
  return 0, and asserts `RuntimeError` -- and that invalidation is never
  reached, since a failed-closed bootstrap must not let any further work
  happen before the process exits.
- `test_prepare_rollup_generation_continues_when_the_database_is_
  genuinely_quiet` -- the complementary case: zero recovered, no legacy
  evidence anywhere in the window, must not raise.
- `test_main_prepares_the_rollup_generation_before_building_fetchers` --
  `inspect.getsource(daemon.main)`-based ordering check, matching this
  file's existing style for `main()`-shape assertions (real execution would
  block forever in the scheduler's loop).

I judged this necessary rather than optional: behaviour 7 is explicitly one
of the seven I was told to implement regardless of test coverage, the
architecture review specifically flagged "bootstrap-evidence failure was
not pinned strongly enough" as an unresolved concern before ruling on this
task, and shipping fail-closed startup logic with zero regression coverage
in a codebase whose stated culture is "every behaviour gets a dedicated
test" seemed like the wrong thing to leave undone. Both real-DB tests use
`now = 2026-08-26 06:00` for the same reason as the journal fixes above --
confirmed clear of the seeded `RadarBucketSource` history -- and both clean
up their seeded `ZZDAEMON` row in a `finally` block.

One design point worth surfacing rather than silently deciding: brief item
5 ("`_rows_by_ticker` and `score_source` may read and write only
current-generation rows") is explicit in the brief's Step 4 as an interface
requirement, but the given regression tests for item 3 use tickers whose
*only* rows are incompatible, so `usable()`'s own version filter already
keeps the row-level write loop from ever reaching them -- meaning no
inherited or added test actually forces `_rows_by_ticker`'s SQL-level
version filter to exist. I implemented it anyway, per the explicit
instruction and the real gap it closes (a ticker straddling a generation
boundary, some current rows and one old row not yet invalidated, could
otherwise have the old row's score silently refreshed under the current
baseline). I did not construct a same-ticker mixed-generation regression
for it since none was asked for and Task 3c's explicit scope excludes "a
manual mutation exercise" -- flagging this so the gap in direct test
coverage for that one interface change is visible rather than implied.

## Commands and full output

Circular import check (all four required orders, fresh processes):

```
$ python -c "from features.radar import buckets" && echo "OK: import buckets"
OK: import buckets
$ python -c "from features.radar import journal" && echo "OK: import journal"
OK: import journal
$ python -c "from features.radar import ingest" && echo "OK: import ingest"
OK: import ingest
$ python -c "import run_radar_ingest" && echo "OK: import run_radar_ingest"
OK: import run_radar_ingest
```

Dev-database probes that informed the date fix above:

```
>>> RadarPost.query.count()
1432
>>> min/max(RadarPost.created_utc)
2026-08-22 20:03:00 .. 2026-08-23 20:00:00
>>> RadarBucketSource.query.count()
32005
>>> min/max(RadarBucketSource.bucket_start)
2026-07-22 20:00:00 .. 2026-08-23 19:45:00
>>> RadarBucketSource rows with high_confidence_count > 0 AND bucket_start >= 2026-08-24
0
```

Covering suites (task-specified five plus `test_radar_daemon.py`, matching
the plan's Step 5 command in full):

```
$ python -m pytest tests/test_radar_config.py tests/test_radar_journal.py \
    tests/test_radar_buckets.py tests/test_radar_profile.py \
    tests/test_radar_scoring.py tests/test_radar_daemon.py -v
...
collected 137 items
...
============================ 137 passed in 33.99s =============================
```

Full detail, file by file (all from the same final run):

- `tests/test_radar_config.py` -- 27 passed
- `tests/test_radar_journal.py` -- 9 passed (includes both new bootstrap
  tests and the two previously-broken `clean_events`-only tests, now fixed)
- `tests/test_radar_buckets.py` -- 25 passed (includes both parametrized
  cases of the new restamp test)
- `tests/test_radar_profile.py` -- 10 passed
- `tests/test_radar_scoring.py` -- 26 passed
- `tests/test_radar_daemon.py` -- 40 passed (36 pre-existing + 4 new)

Every individual test name PASSED; none skipped or xfailed in this set. The
task's own named command
(`tests/test_radar_config.py tests/test_radar_journal.py
tests/test_radar_profile.py tests/test_radar_scoring.py
tests/test_radar_buckets.py`, five files) was also run standalone and
produced `97 passed in 33.54s` with the identical set of individual results
above minus the daemon file.

Full gate:

```
$ python -m pytest tests/ -k radar -q
...
FAILED tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch
FAILED tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query
2 failed, 595 passed, 2 skipped, 646 deselected, 2 warnings in 63.52s
```

The two failures and two skips are all the same pre-existing cause:
`static/radar/dist/.vite/manifest.json` does not exist in this worktree
(`npm run build` has never been run here; the directory is absent, not just
empty). This is the exact gap Task 3b's report already documented as
unrelated ("local npm build is unavailable because tsc is not installed")
and it is untouched by anything in this task -- confirmed by directory
listing (`static/radar/dist`: No such file or directory) and by the
traceback pointing at `vite_assets.py`'s manifest loader, nothing in
`features/radar/` or `run_radar_ingest.py`. 595 >= 587, the required floor.

Post-suite ZZ%-namespace cleanup check, run after the final full gate:

```
radar_buckets ZZ%: 0
radar_bucket_sources ZZ%: 0
radar_mention_events ZZ%: 0
radar_posts zz-bootstrap-%: 0
```

## Deviations from the brief, with reasoning

1. **Fixed two mechanical defects in the inherited test file** (duplicate
   `yield` / truncated `clean_events`) rather than reproducing them. These
   were editing accidents, not requirement disagreements -- covered in
   detail above.
2. **Shifted the dates in two bootstrap-related tests** (and added a
   `created_utc` override to `_row()` to do it without touching any other
   test) from 2026-04-15 to a window confirmed clear of this dev database's
   seeded content. Same section above.
3. **Added test coverage in `test_radar_daemon.py`** that the inherited
   diff had not reached, because behaviour 7 is binding regardless and the
   architecture review had specifically flagged it as under-pinned. Also
   covered above, including the one open question about `_rows_by_ticker`'s
   own test coverage that I chose not to manufacture a regression for.
4. **Did not modify `scratchpad/seed_radar_dev.py`.** Its ~30-day
   `RadarBucketSource` seed predates `ROLLUP_GENERATION = 2` and will now
   read as incompatible with every future scoring/profile pass (by design
   -- that population genuinely was aggregated under generation 1's rules,
   or under no rollup at all). This is outside Task 3c's file list and
   outside its stated scope (no board-schema or backfill work here); noted
   for whoever next touches local dev seeding, not acted on.

No other deviations. `config.ROLLUP_GENERATION`, the `bootstrap_from_
mentions` body, and the `_prepare_rollup_generation` four-step sequence
were implemented to match the brief's given code/pseudocode as closely as
the surrounding code's own conventions allow.

## Commit

```
git add personal_apps/features/radar/config.py \
        personal_apps/features/radar/journal.py \
        personal_apps/features/radar/buckets.py \
        personal_apps/features/radar/profile.py \
        personal_apps/features/radar/scoring.py \
        personal_apps/run_radar_ingest.py \
        personal_apps/tests/test_radar_config.py \
        personal_apps/tests/test_radar_journal.py \
        personal_apps/tests/test_radar_buckets.py \
        personal_apps/tests/test_radar_profile.py \
        personal_apps/tests/test_radar_scoring.py \
        personal_apps/tests/test_radar_daemon.py
git commit -m "fix(radar): start corrected rollups as a new baseline generation"
```

## Fix round 1 — test teeth and scoped invalidation

Base: `c0f6f6b`. This round owns and replaces the reviewer's uncommitted
`test_main_prepares_the_rollup_generation_before_building_fetchers` rewrite.
Only the Task 3c scorer, Task 3c tests, and this report are staged for the
round commit.

### Changes

- Replaced the daemon source-text ordering assertion with runtime proof that a
  `_prepare_rollup_generation` exception propagates and never reaches
  `build_fetchers`.
- Pinned the prepare wiring's bootstrap → invalidation → commit order and the
  exact `source_config_version()` passed to invalidation. The quiet path now
  contains a `ZZQUIET` legacy row with `high_confidence_count=0`, proving that
  zero is not evidence of a failed bootstrap.
- Moved the Task 3c global-window daemon and journal fixtures to a
  `2027-06-01` window (with same-test offsets), beyond real and seeded rows.
- Added a mixed-generation `ZZGEN` regression: enough current history to
  score plus one incompatible `ok` row must leave the old row unscored.
- Pinned invalidation's score-presence guard with a scored and an already-null
  incompatible row.
- Added optional `source=None` scope to
  `invalidate_incompatible_scores`. Startup omits it and remains all-source;
  `score_source` passes its active source so one `score_all` pass does not run
  four identical all-source range updates.

### Watched failing mutations, then restoration

1. Wrapped `main()` prepare in a swallowing `try/except`: runtime daemon test
   failed after `build_fetchers` ran.
2. Removed `_rows_by_ticker`'s generation predicate: mixed `ZZGEN` test
   failed with old-row `mention_z == 357.92`.
3. Removed `db.session.commit()`: prepare wiring test failed because its
   observed sequence lacked `commit`.
4. Replaced the prepare call-site version with `wrong-version`: wiring test
   failed its exact-version assertion.
5. Mutated `high_confidence_count > 0` to `>= 0`: quiet-database test raised
   on the seeded zero-count legacy row.
6. Replaced the score-presence `isnot(None)` disjunction with `sa.true()`:
   invalidation test reported two writes instead of one.
7. Removed `source=source` from the scorer invalidation call: the unrelated
   Bluesky row was cleared by a StockTwits scoring pass.
8. The source-scoped regression was written first and initially failed against
   the inherited all-source scorer call; it passed after adding the optional
   scope and passing the active source.

### Final verification

Focused regressions:

```text
py -3.12 -m pytest [nine Task 3c focused tests] -v
9 passed in 2.47s
```

Required covering gate:

```text
py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_profile.py tests/test_radar_scoring.py tests/test_radar_daemon.py -v
140 collected; exit 0
```

Required broad gate:

```text
py -3.12 -m pytest tests/ -k radar -q
2 failed, 598 passed, 2 skipped, 646 deselected, 2 warnings in 66.84s
```

The only broad failures are the established unrelated Radar API template
tests, both caused by the ignored missing
`static/radar/dist/.vite/manifest.json`. The test-created `ZZ...` rows are
cleaned before and after each affected test.

## Fix round 2 — shared-DB scoring cleanup ownership

The scoring fixture had widened its cleanup from its original `SS%` prefix
to `SS% OR ZZ%` when the Task 3c `ZZ...` regressions were added. Because the
development database is shared, that broad `ZZ%` deletion could erase rows
owned by another test or user.

`test_radar_scoring.py` now declares the exact ticker set owned by this file:
`SSA`, `SSB`, `SSNEW`, `SSOLD`, `SSNULL`, `SSNOPE`, `ZZGEN`, `ZZSCORED`,
`ZZSCOPE`, and `ZZUNSCORED`. Its setup and teardown use the shared
`_clear_owned_rows()` helper with `ticker.in_(...)`, not namespace prefixes.
The new `test_row_cleanup_preserves_an_unowned_zz_sentinel` creates
`ZZSENTINEL`, calls that helper, asserts the sentinel remains, and explicitly
deletes its own sentinel in `finally`.

### Watched failing mutation

Temporarily replacing the exact `ticker.in_(_OWNED_TICKERS)` predicate with
the former `ticker.like('SS%') | ticker.like('ZZ%')` predicate made the
sentinel test fail with `assert 0 == 1`: the helper deleted the unowned
`ZZSENTINEL` row. The exact predicate was then restored and the regression
passed.

### Final verification

```text
py -3.12 -m pytest tests/test_radar_scoring.py -v
30 passed in 45.09s

py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_profile.py tests/test_radar_scoring.py tests/test_radar_daemon.py -v
141 passed in 47.63s
```

## Fix round 3 — collision-safe shared-DB sentinel

The round-2 exact ownership list still incorrectly included `SSNOPE`, which
this file only queries and never creates. It has been removed. The ownership
list now contains only tickers this file writes:
`SSA`, `SSB`, `SSNEW`, `SSOLD`, `SSNULL`, `ZZGEN`, `ZZSCORED`, `ZZSCOPE`, and
`ZZUNSCORED`.

The sentinel regression now generates a per-run 12-character ticker as
`ZZX` plus nine uppercase UUID hex characters. It performs no pre-delete,
inserts that exact row, calls `_clear_owned_rows()`, asserts the row remains,
and deletes only that exact ticker in `finally`.

### Watched failing mutation

Replacing the exact `ticker.in_(_OWNED_TICKERS)` cleanup predicate with the
former broad `ticker.like('SS%') | ticker.like('ZZ%')` predicate failed the
sentinel regression with `assert 0 == 1`; the generated `ZZX994168F8A`
sentinel was deleted. The exact predicate was restored.

### Final verification

```text
py -3.12 -m pytest tests/test_radar_scoring.py -v
30 passed in 47.10s

py -3.12 -m pytest tests/test_radar_config.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_profile.py tests/test_radar_scoring.py tests/test_radar_daemon.py -v
141 passed in 48.35s
```

# Task 6: Backfill the buckets the old rollup truncated

Date: 2026-08-26

## Files

- Created: `personal_apps/scripts/backfill_radar_buckets.py`
- Created: `personal_apps/tests/test_radar_backfill.py`

Not touched (unrelated user work in progress, confirmed untouched via `git status`):
`personal_apps/scripts/discover_telegram_sources.py`,
`personal_apps/telegram_candidates.json`, `personal_apps/reddit_candidates.json`.

## What was built

`repair(apply=False, ticker_prefix=None) -> dict`, transcribed from the task
brief's script body with one deviation (see Deviations). It:

1. Recomputes the true `high`-confidence lower bound for every
   `(ticker, bucket_start, source)` from `radar_posts` x `radar_mentions`
   (the `_TRUTH` query), and for every existing `RadarBucketSource` row it
   still applies to, raises `high_confidence_count`, `mention_count`,
   `distinct_authors`, and `engagement_weighted_count` to `max(old, truth)`
   and lowers `distinct_text_ratio` to `min(old, truth)` -- never regressing
   a column, since the truth is itself an undercount (promoted `medium`
   mentions and `low` mentions are unrecoverable, per the brief).
2. Whenever a row's counts actually change, clears `expected`, `variance`,
   `mention_z`, `baseline_days` on that row (the old score was computed off
   the understated count) while leaving `status` and `source_config_version`
   untouched -- a partial repair must never look like current-generation
   data.
3. Separately, clears the same four columns on any row whose `status != 'ok'`
   and which still carries a non-NULL score in any of the four columns --
   this is the Task 3 follow-up: Task 3 stopped `roll_up` from producing that
   state going forward but could not reach the ~399 rows that already had it,
   since a closed quarter-hour is never revisited.
4. Is read-only unless `--apply` is passed; the dry-run path always ends in
   `db.session.rollback()`.
5. `ticker_prefix` is accepted by `repair()` for test scoping only and is not
   exposed on the CLI (`main()` calls `repair(apply=args.apply)` with no
   prefix argument).

## Deviations

**`distinct_text_ratio` and `engagement_weighted_count` equality check
replaced with a tolerant compare (`math.isclose`), not `==`.**

Both columns are MySQL `FLOAT` (confirmed via `SHOW COLUMNS FROM
radar_bucket_sources` against the real dev database -- 4-byte single
precision, not the 8-byte double SQLAlchemy's generic `Float` type might
suggest). Empirically:

```python
>>> v = 2/3                      # what Python computes for n_hashes/n_high
>>> # ... stored into distinct_text_ratio, committed, reread on a fresh session ...
>>> reread_value
0.6666666865348816               # NOT 0.6666666666666666
>>> reread_value == v
False
```

The brief's literal `all(getattr(bucket, field) == value for field, value in
candidate.items())` short-circuit check therefore never actually
short-circuits for any bucket whose true `distinct_text_ratio` isn't exactly
float32-representable (i.e. almost all of them) -- every rerun would find
"a difference" against the just-persisted, precision-rounded value and
report `repaired > 0` forever, directly contradicting the brief's own
required behavior ("a second apply is idempotent (`repaired == 0`)"). I
confirmed this failure mode live (see the "Bug found and fixed" note below)
before shipping the fix.

Fix: added a module-level `_FLOAT_FIELDS = ('distinct_text_ratio',
'engagement_weighted_count')` and a small `_unchanged(field, old, new)`
helper that uses `math.isclose(old, new, rel_tol=1e-6, abs_tol=1e-9)` for
those two fields (comfortably above float32's ~1e-7 relative precision, so
it cannot mask a genuine difference) and exact `==` for the three integer
fields. `engagement_weighted_count` is always a sum of two `Integer` columns
in practice, so it never actually needed the tolerance, but it shares the
column type and the same failure mode, so I treated both columns
consistently rather than special-casing only the one my test happened to
exercise. Nothing else in the brief's script was changed -- every comment,
docstring, variable name and code path is otherwise verbatim.

## Bug found and fixed during testing (test helper, not production code)

While building the idempotency test I hit a second, unrelated staleness bug
-- this one entirely in my own test helper, not in `backfill_radar_buckets.py`.
`RadarBucketSource.query...` reads inside one long-lived pytest test function
share `db.session` (Flask-SQLAlchemy scopes `db.session` by
`id(current app context)`, confirmed by reading
`flask_sqlalchemy/session.py::_app_ctx_id`). A test's *first* plain read
opens a MySQL REPEATABLE READ snapshot on that session; if that session is
never explicitly committed/rolled back, every later "reread" on it --
`db.session.expire_all()` included -- still executes inside the *same
frozen snapshot* and cannot see a commit made by `repair()`'s own,
separately-scoped nested `app_context()` session. I reproduced this with
engine-level `begin`/`commit`/`rollback` event listeners and a raw-SQL read
inside the same session (still stale) versus a fresh process (correctly
`None`), isolating it to session/transaction staleness rather than a write
failure. Fixed by having the test's `_reread()` helper call
`db.session.rollback()` before `expire_all()` and the requery, so the
requery opens a brand-new transaction/snapshot. This matches ambiguity
resolution #4's phrase "fresh session" and is now documented inline in
`_reread()`'s docstring.

## Teeth-experiment table

All mutations were applied to `personal_apps/scripts/backfill_radar_buckets.py`,
run against the one relevant test, observed failing for the stated reason,
then reverted (confirmed via `grep -n MUTATION scripts/backfill_radar_buckets.py`
returning nothing, and a full green rerun of `test_radar_backfill.py`).

| # | Assertion (absence-shaped) | Mutation | Exact failure observed | Reverted |
|---|---|---|---|---|
| 1 | `test_dry_run_...`: every bucket field is unchanged after a dry run | `if apply:` -> `if True:` around the final commit/rollback | `assert row.high_confidence_count == 1` -> `AssertionError: assert 2 == 1` | Yes, confirmed via a clean pass of the same test |
| 2 | `test_apply_...`: second `apply` call has `repaired == 0` | `if all(_unchanged(...) ...): continue` -> `if False: continue` | `assert second['repaired'] == 0` -> `AssertionError: assert 1 == 0` | Yes |
| 3 | `test_apply_...`: `baseline_days is None` after apply | Dropped the `bucket.baseline_days = None` line | `assert row.baseline_days is None` -> `AssertionError: assert 10 is None` | Yes |
| 4 | `test_apply_...`: `source_config_version == 'old-gen-2'` (never restamped) | Added `bucket.source_config_version = source_config_version()` (current generation) before the count writes | `assert row.source_config_version == 'old-gen-2'` -> `AssertionError: assert 'fc1a0ee4cab51d65' == 'old-gen-2'` | Yes |
| 5 | `test_equal_high_confidence_count_...`: `distinct_authors`/`distinct_text_ratio`/`engagement_weighted_count` still repair when `high_confidence_count` alone is already equal | Short-circuit changed to check `high_confidence_count` only (the exact bug item 3 in the brief warns against) | `assert report['repaired'] == 1` -> `AssertionError: assert 0 == 1` | Yes |
| 6 | `test_stale_scores_...`: dry-run leaves the stale row untouched | Both dry-run guards removed at once (`if apply and stale_count:` -> `if stale_count:`, and the final `if apply:` -> `if True:`) -- see note below on why the inner guard alone was insufficient | `assert stale.baseline_days == 7` -> `AssertionError: assert None == 7` | Yes |
| 7 | `test_stale_scores_...`: `dry['stale_scores'] == 1` / all four columns clear, not just `mention_z` | `sa.or_(expected/variance/mention_z/baseline_days .isnot(None))` -> `mention_z.isnot(None)` alone | `assert dry['stale_scores'] == 1` -> `AssertionError: assert 0 == 1` | Yes |
| 8 | `test_stale_scores_...`: an `ok` row's legitimately earned score is never touched | Dropped `RadarBucketSource.status != 'ok'` from the stale filter | `assert dry['stale_scores'] == 1` -> `AssertionError: assert 2 == 1` | Yes |

Note on #6: my first attempt mutated only the inner `if apply and
stale_count:` guard. That mutation passed unchanged -- not because the
dry-run guarantee is untested, but because the script has two independent
layers of protection (the inner `apply` check before the bulk `.update()`,
and the outer `if apply: commit() else: rollback()` at the very end), and
removing only one layer left the other still rolling back the (redundant)
write. I recorded this as a real finding rather than treating it as
successful teeth, then re-ran with both layers removed to get a genuine
failure, which is what's reported in row 6.

Every mutation above was reverted before the next one was applied, and a
full `python -m pytest tests/test_radar_backfill.py -v` run after the last
revert shows all four tests green (see Gate 1 output below).

## Gate 1: `python -m pytest tests/test_radar_backfill.py -v` (from `personal_apps/`)

```text
tests/test_radar_backfill.py::test_dry_run_reports_an_understated_row_but_writes_nothing PASSED [ 25%]
tests/test_radar_backfill.py::test_apply_repairs_clears_scores_preserves_generation_and_is_idempotent PASSED [ 50%]
tests/test_radar_backfill.py::test_equal_high_confidence_count_does_not_block_other_repairs PASSED [ 75%]
tests/test_radar_backfill.py::test_stale_scores_clear_on_any_column_and_only_for_non_ok_status PASSED [100%]

============================== 4 passed in 0.47s ==============================
```

## Gate 2: `python -m pytest tests/ -k radar -q` (from `personal_apps/`)

```text
FAILED tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch
FAILED tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query
2 failed, 605 passed, 2 skipped, 646 deselected, 2 warnings in 70.01s (0:01:10)
```

Both failures are the expected pre-existing `vite_assets.ViteManifestError`
(`No Vite manifest at .../static/radar/dist/.vite/manifest.json`) -- the
gitignored build artifact is absent in this worktree, unrelated to this
task. No third failure. (605 rather than the brief's estimated ~601 because
this batch adds 4 new tests plus whatever earlier-task test growth already
landed; the two expected failures are the same two named in the brief.)

## Gate 3: `python -m scripts.backfill_radar_buckets` (from `personal_apps/`, real dry run)

```text
examined 210 bucket rows, 165 understated
0 rows carry a score they earned under a different status
dry run -- nothing written, pass --apply
```

Run a second time immediately after, to confirm the dry run truly wrote
nothing (identical output would be impossible if the first run had mutated
the rows it found understated):

```text
examined 210 bucket rows, 165 understated
0 rows carry a score they earned under a different status
dry run -- nothing written, pass --apply
```

Identical both times -- confirms no writes occurred. This local dev database
does hold real radar data (unlike the "examined 0" case the brief anticipated
for an empty database), so this is exercising the real recovery path, not
just the empty-database code path. The production run against the live
database is deliberately left for Michi to trigger after deploy, per the
brief.

## Gate 4: circular-import check (fresh processes, from `personal_apps/`)

```text
$ python -c "from features.radar import buckets"
buckets OK
$ python -c "from features.radar import journal"
journal OK
$ python -c "from features.radar import ingest"
ingest OK
```

All three import cleanly with no error.

## Commit

```text
git add personal_apps/scripts/backfill_radar_buckets.py personal_apps/tests/test_radar_backfill.py
git commit -m "feat(radar): a one-shot repair for buckets the old rollup truncated"
```

## Concerns

- The float-precision fix (see Deviations) is the one place I diverged from
  a verbatim transcription of the brief. I'm confident it's necessary and
  correctly scoped (confirmed both by direct empirical reproduction against
  the real dev database and by the teeth experiment for idempotency), but
  flagging it clearly since ambiguity resolution #5 asked for explicit
  callout of any such fix.
- Gate 3 ran against the real local dev database's actual radar data (210
  examined, 165 understated) rather than an empty database. I did not
  `--apply` it -- only the dry-run path ran, matching "Read-only until
  --apply" and "the production run ... is Michi's call to trigger." No
  production/live database was touched by this task.
- All ZZBF-prefixed fixture rows and the `zzbf-backfill-test`-channel
  `RadarPost`/`RadarMention` rows were confirmed absent both before the test
  run (fixture setup) and after (fixture teardown); no broader `LIKE 'ZZ%'`
  sweep was used anywhere in the new test file.

## Fix round 1

Date: 2026-08-26. Scoped fix round against the independent review's two
findings (Important + Minor #3; Minor #2 on the COUNT/Decimal comment was
explicitly left alone per the review's own verdict that it's a pre-existing
house convention). Only the two in-scope files were touched.

### Fix 1 (Important) -- `ticker_prefix` scoping on the stale-score query had no data-independent test

`personal_apps/tests/test_radar_backfill.py`,
`test_stale_scores_clear_on_any_column_and_only_for_non_ok_status`: added,
immediately after the existing `assert dry['stale_scores'] == 1` (scoped to
`ticker_prefix='ZZBF'`):

```python
assert backfill.repair(apply=False, ticker_prefix='ZZNOPE')['stale_scores'] == 0
```

`ZZNOPE` is not created or queried anywhere else in this file, so the
assertion is genuinely data-independent -- it does not rely on what else is
in the database, and no rows needed to be pre-created or pre-deleted under
that prefix.

**Teeth experiment**: temporarily deleted the `if ticker_prefix: stale =
stale.filter(...)` block (`backfill_radar_buckets.py:152-154` pre-fix) --
i.e. exactly the mutation the review already identified in its own Teeth
audit row 5 (the mutation the old suite couldn't catch). Ran the single
covering test:

```text
$ python -m pytest tests/test_radar_backfill.py::test_stale_scores_clear_on_any_column_and_only_for_non_ok_status -v
...
>       assert backfill.repair(apply=False, ticker_prefix='ZZNOPE')['stale_scores'] == 0
E       assert 1 == 0
tests\test_radar_backfill.py:223: AssertionError
FAILED tests/test_radar_backfill.py::test_stale_scores_clear_on_any_column_and_only_for_non_ok_status
```

Confirmed FAILED with `assert 1 == 0`, exactly as the review predicted. The
mutation was then reverted completely (replaced the placeholder comment with
the original `if ticker_prefix: stale = stale.filter(...)` block, verified
via `git diff --stat` showing only the intended datetime-coercion insertions
remaining), and a full rerun of `test_radar_backfill.py` showed 4/4 green
again. `git status --short` at the end of the session showed no leftover
mutation.

### Fix 2 (Minor #3) -- explicit datetime conversion for `bs` instead of implicit MySQL coercion

`personal_apps/scripts/backfill_radar_buckets.py`:
- Added `import datetime as dt` (alphabetically ordered with the existing
  `argparse` / `math` / `sys` imports).
- In the `for src, tk, bs, ...` loop, right after the `ticker_prefix`
  continue-check and before the `RadarBucketSource.query.filter_by(...,
  bucket_start=bs, ...)` lookup, added:

```python
# sa.text() applies no DateTime type processor to a computed
# DATE_ADD(...) expression, so bs comes back a str, not a
# datetime, on this driver. MySQL 8 coerces the string implicitly
# for the filter_by() comparison below, but that coercion is not
# something this codebase can verify on MariaDB (production), so
# make the conversion explicit instead of leaning on it. Tolerate
# a driver that already hands back a real datetime.
if isinstance(bs, str):
    bs = dt.datetime.strptime(bs, '%Y-%m-%d %H:%M:%S')
```

This tolerates a driver/engine that already returns a `datetime` (the
`isinstance` guard skips conversion in that case, so it can't crash on a
type it doesn't need to touch) and stays naive UTC throughout -- no
`utcnow()`, no timezone attached, matching every other datetime in this
script. Minor #2 (the COUNT/Decimal comment at lines ~83-85, now shifted a
few lines by this change) was left untouched, per the task's explicit
instruction and the review's own finding that it's a pre-existing house
convention used verbatim in `features/radar/journal.py:204`.

### Verification gates (in order, this fix round)

**Gate 1** -- `python -m pytest tests/test_radar_backfill.py -v` (from `personal_apps/`):

```text
tests/test_radar_backfill.py::test_dry_run_reports_an_understated_row_but_writes_nothing PASSED [ 25%]
tests/test_radar_backfill.py::test_apply_repairs_clears_scores_preserves_generation_and_is_idempotent PASSED [ 50%]
tests/test_radar_backfill.py::test_equal_high_confidence_count_does_not_block_other_repairs PASSED [ 75%]
tests/test_radar_backfill.py::test_stale_scores_clear_on_any_column_and_only_for_non_ok_status PASSED [100%]

============================== 4 passed in 0.51s ==============================
```

**Gate 2** -- `python -m scripts.backfill_radar_buckets` (from `personal_apps/`, real dry run, post-datetime-fix):

```text
examined 210 bucket rows, 165 understated
0 rows carry a score they earned under a different status
dry run -- nothing written, pass --apply
```

`examined`/`understated` (210 / 165) are identical to the pre-fix run
recorded in the original report and the review -- the explicit datetime
conversion changed nothing observable about the recovery math, as expected
(it only replaces an implicit coercion with an explicit, equivalent one on
this driver).

**Gate 3** -- `python -m pytest tests/ -k radar -q` (from `personal_apps/`):

```text
FAILED tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch
FAILED tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query
2 failed, 605 passed, 2 skipped, 646 deselected, 2 warnings in 63.68s (0:01:03)
```

Exactly the two expected pre-existing failures (`vite_assets.ViteManifestError`
-- missing gitignored Vite manifest for `/radar/`), same two named in the
original report. No third failure.

### Scope check

`git status --short` (worktree root) before staging showed only the two
in-scope files modified:

```text
 M personal_apps/scripts/backfill_radar_buckets.py
 M personal_apps/tests/test_radar_backfill.py
```

`personal_apps/scripts/discover_telegram_sources.py`,
`personal_apps/telegram_candidates.json`, and
`personal_apps/reddit_candidates.json` were not touched. Staged and
committed only the two in-scope files by name:

```text
$ git add personal_apps/scripts/backfill_radar_buckets.py personal_apps/tests/test_radar_backfill.py
$ git commit -m "test(radar): pin backfill stale-score scoping and datetime coercion"
[codex/radar-pipeline-audit 8b0a07d] test(radar): pin backfill stale-score scoping and datetime coercion
 2 files changed, 15 insertions(+)
```

Final diff shape: `backfill_radar_buckets.py` +10/-0 (import + the
isinstance/strptime block + comment), `test_radar_backfill.py` +5/-0 (the
new assertion + its comment). Both findings closed; nothing else in either
file changed.

# Final branch fix report — radar pipeline audit

Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`
Starting HEAD: `a9055b4` (working tree clean)
Fix commit: `d9c7f76`

## 0. Reconstruction of the six earlier commits

The previous fix worker committed six commits addressing the final branch
review's I1–I3 (Important) and M1–M3 (Minor, all ruled FIX BEFORE MERGE) but
was cut off before writing a report. Reconstructed from `git show` on each
commit, cross-checked against `final-branch-review.md`:

### `3d2dced` — test(radar): scope shared database cleanup (I1)

Replaced every broad `ticker.like('ZZ%')` / `symbol.like('ZZ%')` teardown
predicate with an explicit `.in_(_OWNED_...)` exact-identity set, across six
files: `test_radar_bucket_sources.py`, `test_radar_buckets.py`,
`test_radar_daemon.py`, `test_radar_journal.py`, `test_radar_retention.py`
(only its `aged_posts`/`prune_posts` fixture — the `prune_mention_events`
fixture was already exact-identity), `test_radar_universe.py`. Added
`test_clean_buckets_preserves_an_unowned_zz_sentinel` in `test_radar_buckets.py`
proving an unowned `ZZ...` row survives setup and teardown.

**This commit is the actual cause of Failure 2** — see section 2 below.

### `2bc2c19` — fix(radar): align stale scores with final policy (I2)

Moved `SCOREABLE_STATUSES = frozenset({'ok', 'truncated'})` from
`scoring.py` into `config.py` as the single shared definition.
`buckets.roll_up` now clears a `RadarBucketSource`'s score when
`status not in SCOREABLE_STATUSES` (was `status != 'ok'`) **or** the
generation doesn't match — so a current-generation `truncated` row keeps its
score across a rollup instead of losing it. `backfill_radar_buckets.py`'s
one-shot stale-score query was rewritten from "any `status != 'ok'` row
carrying a score" to "status is NULL/not scoreable, OR
`source_config_version` is NULL/not the current version, AND the row still
carries a score" — closing the exact contradiction I2 described (the old
backfill would have wiped legitimate current-generation `truncated` scores
that Task 8 made valid). Rewrote `test_radar_backfill.py`'s stale-score test
into `test_stale_scores_follow_final_status_and_generation_policy`, covering
current-truncated (kept), old-generation-truncated (cleared),
NULL-generation-truncated (cleared), current-missing (cleared), current-ok
(kept), plus a rerun-is-idempotent check. Renamed
`test_a_downgrade_to_truncated_clears_the_stale_score` to
`test_current_generation_truncated_preserves_its_score` with the assertions
inverted to match.

### `f107380` — fix(radar): report aggregate ingest health (I3)

Added a root-level `aggregate_status` dict to `ingest.run_cycle`'s returned
summary, populated from `result.status` on every fetch (or `'missing'` on an
exception) — kept **separate** from `statuses`/`per_source`, which still only
ever receives concrete per-subreddit-style statuses and is the only map
passed to `buckets.roll_up` (so a partial Reddit cycle still never writes a
zero-count root child row). Added `_format_operational_map` in
`run_radar_ingest.py`, rendering a `None` catch-up depth as the literal string
`unknown` rather than `0`, and wired both `aggregate_status` and
`catchup_depth` into the `tick()` info log. Added two new regression tests in
`test_radar_ingest.py`:
- `test_tick_reports_reddit_aggregate_without_root_rollup` — a partial Reddit
  cycle (`status='truncated'`, one sub `ok`/one `missing`) reports
  `aggregate_status == {'reddit': 'truncated'}` and logs
  `aggregate=reddit=truncated`, while `roll_up` never receives `'reddit'` as a
  key and no `'reddit'` row is stored.
- `test_tick_visibly_logs_failed_fetch_depth_as_unknown` — a fetch that raises
  logs `catchup_depth=bluesky=unknown`, never `=0`.

**This same commit also introduced Failure 1**: inside the pre-existing
`test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement`
(a Task 13 extract-once test, unrelated to aggregate health), it added the
line `assert result['aggregate_status'] == {'reddit': 'missing'}` — see
section 1 below.

### `3a3c4b1` — fix(radar): preflight source downgrade widths (M1)

`08316d3e4d77_widen_radar_source_columns.py`'s `downgrade()` used to `ALTER`
`radar_poll_state` first and only afterward check `radar_bucket_sources` for
over-length names, so a `radar_bucket_sources` violation would raise *after*
the (non-transactional, auto-committing) `radar_poll_state` ALTER had already
run — a half-applied downgrade. Now both tables are measured
(`SELECT MAX(CHAR_LENGTH(source))`, `int()`'d at the query boundary) and
validated against the 24-char narrow target *before either* `ALTER` runs.
Added `test_radar_migration.py` (new file) with a fake `op`/bind harness that
never touches the real database, proving: (a) a violation in either table
aborts before any DDL event fires, and (b) the success path checks both
tables before altering in the original order.

### `9139749` — test(radar): pin strict scored read boundaries (M2)

Added four direct mutation-provable regressions, one per boundary M2 named as
untested: `test_triplets_exclude_pre_split_root_reddit_scores` (board.py),
`test_window_figures_exclude_pre_split_root_reddit_scores` (detail_panel.py),
`test_pooled_z_excludes_pre_split_root_reddit_scores` and
`test_window_z_excludes_pre_split_root_reddit_scores` (scoring.py). Each
seeds a current-generation concrete-subreddit score alongside a huge
pre-split root `reddit` score and asserts only the concrete score
contributes — proving `expand_sources` (strict) is really in use, not
`expand_sources_for_history`. Also updated a stale docstring in
`test_radar_buckets.py::test_scoring_columns_are_left_untouched` to describe
the new `SCOREABLE_STATUSES`-based clearing policy instead of the old
`status != 'ok'` wording.

### `a9055b4` — test(radar): pin StockTwits policy removal (M3)

One line: `assert 'stocktwits' not in config.COIN_SYMBOLS_MEAN_STOCKS` added
to `test_stocktwits_is_retired`, closing the gap M3 described (the existing
`not any(values())` assertion could pass with a stale, false-valued
`stocktwits` key still present in that mapping).

All six commits' stated intent matches actual code on inspection; I found no
other undisclosed behavior changes in any of the six diffs.

## 1. Failure 1 — `tests/test_radar_ingest.py:447`

### Diagnosis

`test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement`'s
own fixture is `fetcher_for(FetchResult(posts=duplicate, status='ok'))` with
`fetcher_for`'s default `source='bluesky'` (test_radar_ingest.py:79) — no
Reddit involved anywhere in this test. Production is correct:
`ingest.run_cycle` (features/radar/ingest.py:257) sets
`aggregate_statuses[source] = result.status` for a normal, non-exception
fetch, so `result['aggregate_status']` for this fixture is genuinely
`{'bluesky': 'ok'}`. The asserted `{'reddit': 'missing'}` was never true for
this fixture; it reads as a copy/paste from a Reddit-specific fixture into an
unrelated test, both added by the same commit (`f107380`) that introduced the
`aggregate_status` field.

### Which of the three options, and why

**Option 2: the assertion does not belong in this test at all.** Its
docstring is "One identity means one extraction decision, even when it
appears twice" — a Task 13 concern with no relationship to Reddit aggregate
health. `f107380`, the same commit that added the bad line, also added the
two tests that actually own I3's mandated behaviors:
`test_tick_reports_reddit_aggregate_without_root_rollup` (partial Reddit
cycle reports root health without writing a root child row) and
`test_tick_visibly_logs_failed_fetch_depth_as_unknown` (failed fetch reports
unknown, not zero, catch-up depth). I verified both are present, both pass,
and — see the teeth table — both have real teeth against the exact
behaviors I3 names. Adding a corrected-but-unrelated `{'bluesky': 'ok'}`
assertion to the extract-once test would not exercise any code path the two
I3 tests don't already cover; it would only couple an unrelated test to a
feature it isn't testing. I ruled out option 3 (production bug) because the
`aggregate_statuses[source] = result.status` line is exactly right for this
fixture, confirmed by both direct inspection and the teeth check in section 3.

### Fix

Removed the one line (`tests/test_radar_ingest.py`, was line 447). No
production code changed for this failure.

## 2. Failure 2 — `tests/test_radar_retention.py:164`

### Diagnosis

`prune_mention_events` is a real, unscoped-by-ticker production DELETE
(`features/radar/retention.py:105-139`); its return value is a genuine count
over the *entire* `radar_mention_events` table for the given cutoff, not just
this test's three rows. The pre-existing assertion `assert deleted == 1`
hard-codes an expectation that is only true when nothing else in the shared
database has a row inside the April-2026 test window at that moment.

**Root cause traced to `3d2dced` (I1), not `f107380`.** I confirmed this
empirically rather than assuming it:

- At `a9055b4` (current, pre-fix), running just
  `test_radar_leaderboard.py test_radar_retention.py` together reproduces
  `assert 3 == 1`.
- At `8752c02` (the commit immediately before the six-commit wave), running
  the identical two files together: `35 passed` — no failure.
- Direct query during the failure: the two extra rows are
  `('ZZA', 'bluesky', 'zz-h', 2026-04-15 14:03)` and
  `('ZZA', 'bluesky', 'zz-l', 2026-04-15 14:07)` — written by
  `test_radar_leaderboard.py::test_a_promoted_mention_counts_towards_the_author_floor`
  (line 550-551) via `buckets.roll_up(...)`, using identities `zz-h`/`zz-l`
  that were **never** registered in `test_radar_journal.py`'s
  `_OWNED_EVENT_IDENTITIES` list (that test imports `clean_buckets`/
  `clean_events` from `test_radar_journal.py`).
- Before `3d2dced`, `test_radar_journal.py`'s `clean_events` fixture teardown
  was a broad `RadarMentionEvent.ticker.like('ZZ%')` delete — which,
  incidentally, *also* swept up `zz-h`/`zz-l` (ticker `ZZA` matches `ZZ%`)
  even though they were never on the "official" owned list. `3d2dced`
  correctly tightened this to the exact `_OWNED_EVENT_IDENTITIES` predicate
  per I1 — but that removed the incidental safety net that had been masking
  `test_radar_leaderboard.py`'s own unregistered-identity gap. `zz-h`/`zz-l`
  now leak permanently (until something else's unscoped DELETE happens to
  catch them — which is exactly what `prune_mention_events` does here).

So: Failure 2 is a real second-order regression from the I1 fix, not a
literal line changed in `test_radar_retention.py` itself, and not one of the
"two defects" being a from-scratch new bug — it is the same defect *class*
called out in the branch's own history (the "Task 3c had four tests fail
exactly this way" precedent), now newly triggered by `3d2dced` closing a
different, correctly-identified hazard.

**I did not modify `test_radar_leaderboard.py`.** Registering `zz-h`/`zz-l`
in `test_radar_journal.py`'s owned-identity list would only suppress today's
specific leak; the retention test would remain fragile to the *next* such
leak from any other file. I flag this as a concern below rather than fixing
it, since it is outside the two failures I was asked to fix and the correct
general remedy is to make the retention assertion leak-proof regardless.

### Fix

Replaced the hard-coded `assert deleted == 1` with a dynamically-measured
expected count: immediately before calling `prune_mention_events`, query
`RadarMentionEvent.query.filter(RadarMentionEvent.created_utc < cutoff).count()`
using the identical predicate, and assert `deleted == expected_deleted`. This
value is correct regardless of what else is sitting in the shared window at
that moment — it is not a global count in the sense the review's remedy
warns against, because it is measured from the live table state at the exact
moment before the delete, not asserted as a literal. The boundary claim
itself (a row at exactly the cutoff survives, one 72h old does not) is
proven the way the review's own I1/Task-3c remedy calls for: by exact row
identity (`remaining == {'zz-new', 'zz-boundary'}`), which was already
present and untouched.

I did not touch `retention.py` production code — the `<` boundary logic was
already correct; only the test's assertion was wrong.

## 3. Teeth table

| # | Assertion | Mutation | File:line mutated | Result | Restored |
|---|---|---|---|---|---|
| 1 | `test_the_journal_is_pruned_by_when_the_post_was_written`: `assert deleted == expected_deleted` (my rewritten fix) | `RadarMentionEvent.created_utc < cutoff` → `<= cutoff` | `features/radar/retention.py:122` | **FAIL**, `tests/test_radar_retention.py:185: assert 2 == 1` | Yes — `git diff --exit-code` clean, hash `0f3680be...d9d69` unchanged |
| 2 | `test_tick_reports_reddit_aggregate_without_root_rollup`: `assert summary['aggregate_status'] == {'reddit': 'truncated'}` (pre-existing, verifying I3 is genuinely covered — substantiates my Option-2 conclusion for Failure 1) | Removed `aggregate_statuses[source] = result.status` (success path) | `features/radar/ingest.py:257` | **FAIL**, `assert {} == {'reddit': 'truncated'}` | Yes — `git diff --exit-code` clean |
| 3 | `test_tick_visibly_logs_failed_fetch_depth_as_unknown` + `test_a_failed_fetch_reports_no_catchup_depth`: `catchup_depth=bluesky=unknown` / `is None` (pre-existing, substantiates Option-2) | `depths[source] = None` → `depths[source] = 0` on the exception path | `features/radar/ingest.py:251` | **FAIL** on both tests: `assert 0 is None` and no `catchup_depth=bluesky=unknown` in log | Yes — `git diff --exit-code` clean |

Mutation 1 is the mandatory tooth for my own fix. Mutations 2 and 3 were run
to independently substantiate that I3's mandated behaviors are already
exercised by real, teeth-bearing tests (added by `f107380`), which is the
basis for concluding Failure 1's stray assertion should be removed rather
than corrected in place.

A `git status --short` quirk was observed during this work: after editing
and then reverting `features/radar/ingest.py` back to its original text,
`git status` continued to flag it `M` while `git diff`, `git diff --cached`,
`git diff HEAD`, and `git diff --raw` all reported zero differences, and an
independent reconstruction of the git blob (via `git show HEAD:...`,
CRLF-normalized) byte-for-byte matched the working-tree file. This is a
stat-cache artifact of this Windows checkout, not a real content
difference — `git diff --exit-code` was used as the authoritative signal for
"is this file actually changed" throughout, consistent with how the original
review verified the retention.py restoration.

## 4. Before/after row counts and gates

- `radar_mention_events`: **1432 before, 1432 after.** No shrinkage.
- `flask db current`: `35c3ae366677 (head)` — single head, both before and
  after. No downgrade was ever run.
- Protected files untouched: `git diff --exit-code` clean on
  `scripts/discover_telegram_sources.py` and `telegram_candidates.json`.
  `reddit_candidates.json` was not touched (not read, not written).

### Gate 1 — both failing tests individually

```
tests/test_radar_ingest.py::test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement PASSED
tests/test_radar_retention.py::test_the_journal_is_pruned_by_when_the_post_was_written PASSED
2 passed in 1.03s
```

### Gate 2 — full radar suite, twice

Run 1:
```
655 passed, 646 deselected, 2 warnings in 78.99s (0:01:18)
```

Run 2:
```
655 passed, 646 deselected, 2 warnings in 69.96s (0:01:09)
```

(Baseline before any fix, for reference: `2 failed, 653 passed, 646
deselected` — the two named failures, reproduced first to confirm diagnosis
before changing anything.)

### Gate 3 — `flask db current`

```
35c3ae366677 (head)
```

## 5. Diff

Only two files changed, both tests:

```
 personal_apps/tests/test_radar_ingest.py    |  1 -
 personal_apps/tests/test_radar_retention.py | 23 ++++++++++++++++++++++-
 2 files changed, 22 insertions(+), 2 deletions(-)
```

No production code was changed. No teeth mutation was left in the tree
(`git diff --exit-code` on `features/radar/ingest.py` and
`features/radar/retention.py` both clean).

## 6. Commit

```
git add personal_apps/tests/test_radar_ingest.py personal_apps/tests/test_radar_retention.py
git commit -m "fix(radar): stop the extract-once test asserting a Reddit cycle it never ran, and stop the retention boundary counting rows it does not own"
```

Commit: `d9c7f76`. `git status --short` after commit: clean (only the
untracked `.agents/`, `.codex/`, and gitignored `.superpowers/` remain, none
of which this task touched).

## 7. Concerns for follow-up (not fixed here, out of scope for the two named failures)

1. **`test_radar_leaderboard.py`'s `board` fixture still uses a broad
   `ticker.like('LB%')` / `external_id.like('LB%')` teardown** (lines 37-50).
   This file was not among the six files I1 flagged or `3d2dced` fixed, and
   it is the direct cause of Failure 2 having become reproducible (see
   section 2). It also separately imports `clean_buckets`/`clean_events`
   from `test_radar_journal.py` for one test
   (`test_a_promoted_mention_counts_towards_the_author_floor`) and writes
   `zz-h`/`zz-l` identities that were never added to that file's
   `_OWNED_EVENT_IDENTITIES` list, so those two rows are never cleaned up by
   anything and currently only get removed as an incidental side effect of
   `prune_mention_events` running in the same suite. Recommend either
   registering `zz-h`/`zz-l` in `_OWNED_EVENT_IDENTITIES`, or giving that one
   test its own exact-identity teardown, plus tightening `board`'s own LB*
   teardown the same way I1 tightened the other six files.
2. Per the standing "shared-database safety" convention, my retention fix's
   `assert expected_deleted >= 1` is a sanity floor, not a strength claim —
   it only confirms the fixture's own row would be counted at all; it does
   not (and structurally cannot, given `prune_mention_events`'s unscoped
   delete) prove no *other* file's rows were included in the count. That is
   by design: the point of the fix is that the test no longer cares.

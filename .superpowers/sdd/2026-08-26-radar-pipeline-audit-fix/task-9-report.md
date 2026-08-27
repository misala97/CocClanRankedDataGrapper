# Task 9 WIP report — stopped for session handoff

Date: 2026-08-27

This is a work-in-progress checkpoint, not a completion report. The user
stopped the task before final verification, self-review, report completion, or
commit. Task 8 must not begin from this checkpoint.

## Workspace state

- Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
- Branch: `codex/radar-pipeline-audit`
- Unchanged HEAD/base: `88a2b50bb4a3be7a3ea7b5267ce7ab23eaf795d8`
- No commit was created.
- No deliberate production mutation is currently applied. Read-only checks at
  stop confirmed:
  - ingest uses `result.per_source_status or {source: result.status}` and does
    not add the aggregate root to concrete statuses;
  - the missing gate checks all concrete statuses rather than aggregate
    `result.status`;
  - rollup receives `statuses` without an injected root;
  - source cursors advance under the root fetcher key;
  - API root validation, board selection restoration, and detail expansion are
    restored;
  - poll state records under root `reddit`;
  - daemon scoring iterates expanded concrete names;
  - `source_name_generation` is present in the config-version hash.
- Working tree is safe to resume. The local database is already migrated to
  the new revision, so abandoning these uncommitted files would leave the DB
  physically backward-compatible (wider columns) but ahead of Git.

## Completed implementation

- Added `config.source_root(source)` and routed all five per-source policy
  helpers through it: source kind, single-letter cashtags, coin collision,
  bare-token allowance, and bare-token confidence.
- Added shared `config.expand_sources(names)` so root `reddit` expands to the
  configured `reddit:<sub>` names while a concrete link stays concrete.
- Added documented `SOURCE_NAME_GENERATION = 2` to
  `source_config_version()`.
- Added `FetchResult.per_source_status`.
- Reddit posts now emit `RawPost.source='reddit:<sub>'`; `fetch()` reports each
  attempted subreddit's concrete status while retaining the aggregate cycle
  status.
- Ingest sends only concrete statuses to rollup when provided and preserves
  successful posts even if aggregate status is `missing`.
- API parsing accepts known prefixed roots, rejects unknown roots, expands
  board/detail queries, and restores the viewer's root selection before
  serialization.
- Daemon scoring expands root sources to concrete Reddit names.
- Reddit scheduler poll state and ingest source cursors remain rooted at
  `reddit`.
- Model widths are now 48 for `RadarPost.source`,
  `RadarBucketSource.source`, and `RadarPollState.source`.
- Created migration `08316d3e4d77_widen_radar_source_columns.py`, chained from
  `1d26ac48e744`, widening all three columns. Downgrade normalizes prefixed
  `radar_posts.source` values to root `reddit` before narrowing that column to
  16.

## Migration and DB state

- Before changes:
  - Alembic head/current: `1d26ac48e744` / `1d26ac48e744`
  - `source_config_version()`: `8106787f1fa72179`
- Current:
  - single Alembic head: `08316d3e4d77`
  - local DB current: `08316d3e4d77 (head)`
  - `source_config_version()`: `705b043693b533db`
- Forward upgrade was applied successfully with:
  `python -m flask db upgrade`.
- The live-width regression reflected all three DB columns at 48 and inserted
  then exactly cleaned up a post using the longest configured concrete Reddit
  source.
- Downgrade has not yet been executed or empirically verified.
- Deployment boundary: run the widening migration before deploying the new
  writer. Old root writers are physically compatible with widened columns,
  but old and new daemons must not overlap: root `reddit` and concrete
  `reddit:<sub>` rows are different semantic populations and neither reader
  sees the other's names as its own population.
- Rollback boundary: prefixed post rows can be normalized to root Reddit, but
  per-subreddit bucket summaries cannot be losslessly collapsed into the old
  aggregate summary. Distinct voices/text ratios/statuses are not algebraically
  reconstructable from child summaries. Concrete bucket names fit the old
  24-character width, but old root-only readers will not consume them. Do not
  claim a lossless semantic downgrade.
- MySQL/MariaDB DDL is non-transactional. The three `MODIFY COLUMN` operations
  can commit independently; a failed production run must be inspected column
  by column before retrying. The partitioned bucket-source alter rebuilds the
  table and can briefly block ingest writes.

## RED evidence before production changes

The initial 15-node regression command collected 15 failures. Thirteen failed
immediately for the intended missing behavior:

- missing `SOURCE_NAME_GENERATION`, `source_root`, and `expand_sources`;
- prefixed policy lookup fell through to defaults;
- Reddit post source was root `reddit`;
- `FetchResult` lacked `per_source_status`;
- model widths were 16/24/24 rather than 48/48/48;
- ingest rejected the new result field;
- concrete API source was rejected;
- detail and daemon scoring saw only root `reddit`.

Two tests exposed setup defects instead of a clean feature failure: the board
capture lacked a Flask app context, and the real shared poll queue could select
an existing subreddit instead of the exact owned fixture. Only the tests were
corrected. Re-running those two then produced the intended RED failures:

- board build received `['reddit']` instead of all configured concrete names;
- poll test reached the owned symbol and failed because `FetchResult` still
  lacked `per_source_status`.

After the non-schema production code was added but before migration, the
14-node gate was 12 passed / 2 failed. Both failures were the intended live DB
boundary: MySQL error 1406, `Data too long for column 'source'`, when inserting
`reddit:wallstreetbets` and `reddit:pennystocks`.

## GREEN evidence completed so far

- New focused regression gate after migration: `15 passed in 2.20s`.
- Covering suites:
  `python -m pytest tests/test_radar_config.py tests/test_radar_reddit.py tests/test_radar_ingest.py tests/test_radar_api.py tests/test_radar_daemon.py -q`
  produced `147 passed, 2 failed`. The only failures were the two established
  missing-Vite-manifest page tests:
  - `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`
  - `test_the_page_falls_back_to_the_default_board_on_a_bad_query`

## Teeth mutations completed and restored

Every mutation below was applied temporarily, its focused test was watched
failing, and it was restored immediately:

1. Added aggregate `statuses['reddit']` beside concrete statuses: per-source
   result failed with an extra root `reddit` entry.
2. Injected a non-missing root only into `buckets.roll_up`: the DB row map
   failed with an extra root `reddit` child, directly proving the no-root-row
   assertion has teeth.
3. Reverted ingest to `if result.status == 'missing': continue`: partial
   success failed with `posts_new == 0` instead of 1.
4. Reverted daemon scoring to root `SOURCES`: scoring test failed with extra
   root `reddit` and all concrete Reddit names absent.
5. Advanced the cursor under the concrete post source: cursor test failed
   because root `reddit` was absent; exact cleanup includes the hypothetical
   concrete cursor key.
6. Recorded poll state under `reddit:<sub>`: poll-state test failed with an
   extra concrete row beside the exact owned root row.
7. Disabled unknown-root rejection: API test failed because `BadQuery` was not
   raised.
8. Removed viewer-selection restoration: board payload serialized eight
   concrete Reddit names instead of root `reddit`.
9. Removed detail-query expansion: detail builder received root `reddit`.
10. Removed the source-name generation hash input: changing the generation
    left the version at `8106787f1fa72179`, so the version regression failed.

## Current modified files

Tracked modifications:

- `personal_apps/features/radar/config.py`
- `personal_apps/features/radar/ingest.py`
- `personal_apps/features/radar/routes/api.py`
- `personal_apps/features/radar/sources/__init__.py`
- `personal_apps/features/radar/sources/reddit.py`
- `personal_apps/models.py`
- `personal_apps/run_radar_ingest.py`
- `personal_apps/tests/test_radar_api.py`
- `personal_apps/tests/test_radar_config.py`
- `personal_apps/tests/test_radar_daemon.py`
- `personal_apps/tests/test_radar_ingest.py`
- `personal_apps/tests/test_radar_reddit.py`

Untracked migration:

- `personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py`

Ignored WIP report:

- `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/task-9-report.md`

Protected Telegram discovery files were not touched.

## Unfinished work — resume from here

1. Inspect the full diff and finish self-review; no independent review has
   occurred and Task 8 must not begin.
2. Complete remaining policy-helper teeth mutations (rooting for bare-token
   allowance/confidence, source kind, single-letter cashtags, and coin
   collision) if retaining the current combined tests.
3. Re-run the focused GREEN gate after all restored mutations.
4. Decide whether to perform a controlled downgrade/upgrade verification on
   the shared local DB. Before any downgrade, verify there are no unowned
   prefixed Reddit posts that its normalization would change. Do not broadly
   mutate shared data.
5. Run required fresh-process imports for `buckets`, `journal`, `ingest`, and
   `run_radar_ingest.build_fetchers`.
6. Re-verify one Alembic head/current and all three live widths.
7. Run the required full gate once:
   `python -m pytest tests/ -k radar -q`. Exactly the two known manifest
   failures may remain; no others.
8. Complete this report with final commands/results, full self-review, final
   migration ruling, concerns, and committed SHA.
9. Stage only the Task 9 implementation/test/migration files by exact path and
   commit. Do not stage this ignored report or controller docs.


## Resumed session — completion

Session resumed 2026-08-27 from the WIP checkpoint above. Working through the
report's "Unfinished work" items 1-9 in order.

### Item 2 — policy-helper teeth mutations (rooting)

Both covering tests (`test_a_prefixed_source_inherits_its_roots_policy` and
`test_every_policy_lookup_uses_the_prefixed_sources_root`) were confirmed
green before starting. For each helper: replaced its `source_root(source)`
lookup key with the raw `source`, ran the one covering test that actually
detects that helper's rooting (the other covering test does not always
detect it -- e.g. `source_kind('reddit:thetagang')` degrades to the same
`'forum'` default whether or not it is rooted, since `'reddit:thetagang'`
was never going to be a `SOURCE_KIND` key either way), confirmed the exact
failure, then reverted immediately.

| Helper | Mutation | Covering test | Exact failure |
|---|---|---|---|
| `bare_tokens_allowed` | `BARE_TOKENS_ALLOWED.get(source, False)` | `test_a_prefixed_source_inherits_its_roots_policy` | `AssertionError: assert False is True` at `assert config.bare_tokens_allowed('reddit:wallstreetbets') is True` |
| `bare_token_confidence` | `BARE_TOKEN_CONFIDENCE.get(source, 'low')` | `test_a_prefixed_source_inherits_its_roots_policy` | `AssertionError: assert 'low' == 'high'` at `assert config.bare_token_confidence('reddit:pennystocks') == 'high'` |
| `source_kind` | `SOURCE_KIND.get(source, 'forum')` | `test_every_policy_lookup_uses_the_prefixed_sources_root` | `AssertionError: assert 'forum' == 'broadcast'` at `assert config.source_kind('reddit:wallstreetbets') == 'broadcast'` |
| `single_letter_cashtags_allowed` | `SINGLE_LETTER_CASHTAGS.get(source, False)` | `test_every_policy_lookup_uses_the_prefixed_sources_root` | `AssertionError: assert False is True` at `assert config.single_letter_cashtags_allowed('reddit:wallstreetbets') is True` |
| `coin_collision_dropped` | `COIN_SYMBOLS_MEAN_STOCKS.get(source, False)` (only the internal `source_root` call, not the `symbol in COIN_COLLISION_SYMBOLS` line) | `test_every_policy_lookup_uses_the_prefixed_sources_root` | `AssertionError: assert True is False` at `assert config.coin_collision_dropped('reddit:wallstreetbets', 'LINK') is False` |

All five reverted, confirmed ✓. After the last revert, the full
`tests/test_radar_config.py` file was re-run: `34 passed in 0.18s`, and
`git diff personal_apps/features/radar/config.py` matched the pre-mutation
WIP diff exactly (no residual mutation). No coverage gap was found -- both
existing combined tests together exercise all five helpers' rooting; no new
test was needed.

### Item 4 — the downgrade (per the controller's ruling)

Prefixed-row counts, checked before touching anything:

```sql
SELECT COUNT(*) FROM radar_posts          WHERE source LIKE 'reddit:%'  -> 0
SELECT COUNT(*) FROM radar_bucket_sources  WHERE source LIKE 'reddit:%'  -> 0
SELECT COUNT(*) FROM radar_poll_state      WHERE source LIKE 'reddit:%'  -> 0
```

All three zero. Per the ruling, this means the downgrade's `reddit:%` ->
`reddit` normalization touches nothing, so the round trip was exercised as a
pure DDL exercise rather than skipped or merely documented.

Before: `flask db current` = `08316d3e4d77 (head)`; live widths
`radar_bucket_sources.source`=48, `radar_poll_state.source`=48,
`radar_posts.source`=48.

`python -m flask db downgrade`:
```
Running downgrade 08316d3e4d77 -> 1d26ac48e744, widen radar source columns
```
After: `flask db current` = `1d26ac48e744`; live widths dropped to
`radar_bucket_sources.source`=24, `radar_poll_state.source`=24,
`radar_posts.source`=16 -- exactly the pre-Task-9 widths, confirming the
downgrade's narrowing actually ran (not a silent no-op).

`python -m flask db upgrade`:
```
Running upgrade 1d26ac48e744 -> 08316d3e4d77, widen radar source columns
```
After: `flask db heads` = single head `08316d3e4d77 (head)`; `flask db
current` = `08316d3e4d77 (head)`; live widths back to 48/48/48.

Decision: **exercised**, not merely documented, because every prefixed-row
count was genuinely zero and no row of any kind (owned or otherwise) had to
be deleted first. Worktree/DB end state: single head `08316d3e4d77`, all
three columns at 48, matching Git.

### Item 5 — fresh-process imports

Each run as its own `python -c` process from `personal_apps/`:

```
python -c "from features.radar import buckets"           -> OK, no error
python -c "from features.radar import journal"            -> OK, no error
python -c "from features.radar import ingest"              -> OK, no error
python -c "from run_radar_ingest import build_fetchers"    -> OK, no error
```

All four exit cleanly. The deliberate `buckets`/`journal` circular import
(module-level `from . import journal` in `buckets.py`, call-time
`buckets.MentionRow(...)` via a module-level `import ... as buckets` in
`journal.py`) is undisturbed by this task's changes.

### Item 6 — Alembic head/current and live widths (re-verified standalone)

```
flask db heads   -> 08316d3e4d77 (head)      [single head]
flask db current -> 08316d3e4d77 (head)
information_schema.COLUMNS (source column):
  radar_bucket_sources  48
  radar_poll_state      48
  radar_posts           48
```

### Item 7 — the broad gate

```
python -m pytest tests/ -k radar -q
```
Result: `2 failed, 606 passed, 2 skipped, 646 deselected, 2 warnings in 63.01s`.

The only two failures are the pre-existing, expected ones, both raising
`vite_assets.ViteManifestError: No Vite manifest at
...\personal_apps\static\radar\dist\.vite\manifest.json`:

- `tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`
- `tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query`

No third failure. Left as-is per instructions (gitignored build artifact,
unrelated to Task 9).

### Items 1 and 8 — full diff self-review

Read the complete `git diff` (all 12 tracked files) plus the new migration
file in full. Findings:

- `config.source_root` and all five policy helpers: correct, covered by item
  2's teeth above.
- `sources/reddit.py`: `_to_raw_post` emits `source='reddit:%s' % sub`;
  `fetch` builds `by_sub` alongside the flat `statuses` list and returns
  `per_source_status={'reddit:%s' % sub: status for sub, status in
  by_sub.items()}` -- verified this covers all three branches (`ok`,
  `RedditThrottled` -> break, `RedditUnavailable` -> continue), each recording
  into `by_sub` before the loop moves on.
- `sources/__init__.py`: `FetchResult.per_source_status` documented, default
  `{}` so non-Reddit sources (bluesky, fourchan) are unaffected.
- `ingest.run_cycle`: `result_statuses = result.per_source_status or
  {source: result.status}` -- falls back correctly for single-name sources;
  `statuses.update(result_statuses)` never adds a root `reddit` key when
  concrete statuses exist (confirmed nothing later re-adds `source` itself
  to `statuses`); the missing-gate is `all(status == 'missing' for status in
  result_statuses.values())`, so one surviving concrete `ok`/`truncated`
  keeps the cycle's posts. Traced into `buckets.roll_up`:
  `countable = {source for source, status in statuses.items() if status in
  _COUNTABLE}` only ever contains concrete names for Reddit, so the
  per-ticket-bucket `for source in countable` loop cannot manufacture a root
  `reddit` child row -- confirmed structurally, not just by the (already
  green) covering tests.
- `run_radar_ingest.py`: `_reddit_fetcher` still schedules/tracks by bare
  `REDDIT_SUBS` under root `'reddit'`, matching the "poll state and cursor
  stay rooted" requirement; `score_all` now iterates `expand_sources(SOURCES)`
  -- the same `config.expand_sources` used by the API, so there is one
  source of truth for the root -> concrete expansion, not two.
- `routes/api.py`: `parse_query` accepts a name whose `source_root` is known
  and rejects one whose root is not (`notreddit:wallstreetbets` -> 400,
  confirmed in `test_a_concrete_reddit_source_is_accepted_but_an_unknown_root_is_not`);
  `build_payload` expands for `board_mod.build` then overwrites
  `board.sources = list(query.sources)` *before* `serialize(board)` runs, so
  the payload's `sources`/chip-lit field reflects the viewer's actual
  selection, not the expansion. `ticker_detail` expands the same way for
  `detail_panel.build`. Distinguished this from `_row`'s unrelated
  `r.sources` (a leaderboard row's own contributing venues) -- that field is
  untouched by this task and correctly still reports concrete names, since it
  describes which venues actually contributed to that ticker.
- `models.py`: `RadarPost.source` 16->48, `RadarBucketSource.source` 24->48,
  `RadarPollState.source` 24->48. Matches migration and live DB.
- Migration `08316d3e4d77`: `down_revision = '1d26ac48e744'` (the actual
  pre-Task-9 head, no fork); upgrade widens all three columns; downgrade
  narrows `radar_poll_state` and `radar_bucket_sources` first, then
  normalizes `radar_posts.source` (`UPDATE ... WHERE source LIKE
  'reddit:%'`) before narrowing `radar_posts.source` last -- ordered so the
  UPDATE runs while the column is still wide enough to hold the values being
  read (the column is only narrowed after the UPDATE completes, which is the
  correct order regardless, since `'reddit'` re-fits under any width already
  in play).
- Test fixtures (`test_radar_ingest.py`, `test_radar_reddit.py`,
  `test_radar_daemon.py`, `test_radar_api.py`): every new fixture cleans up
  by exact identity (`TEST_TICKER == 'ZZG'`, exact `external_id`/`channel`
  pairs, exact `(source, symbol)` tuples) both before and after, never a
  broad `LIKE 'ZZ%'` sweep. `test_radar_ingest.py`'s `TEST_SOURCES` was
  correctly widened to include `'reddit:wallstreetbets'` so its cursor
  cleanup filter still covers every source name the new tests touch.

No defects found. No changes made during self-review beyond the five
teeth-mutation revert cycles already logged under item 2, which `git diff`
confirms left no residue.

### Concerns

None blocking. Two carried-forward notes from the original WIP report worth
restating for whoever picks up Task 8: (1) the deployment boundary -- run
this migration before deploying the new writer, and do not let an old
root-writing daemon and a new concrete-writing daemon overlap; (2) the
rollback boundary -- a real downgrade (if ever needed against a database that
*does* hold prefixed rows) collapses `radar_posts.source` back to `reddit`
losslessly, but per-subreddit `radar_bucket_sources` history cannot be
losslessly re-aggregated into the old single-row-per-cycle shape. Distinct
voices/text ratios/statuses are not reconstructable from the concrete
children after the fact.

### Item 9 — commit

Staged the 13 Task 9 paths by exact name (`git add --` with each path listed
individually, no `-A`, no glob). `git status --short` confirmed exactly
those 13 staged and the SDD report left unstaged. Committed:

```
commit dedc90b
feat(radar): give every subreddit its own source identity
13 files changed, 423 insertions(+), 33 deletions(-)
 create mode 100644 personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py
```

Post-commit `git status --short` shows only this report file modified
(expected -- it is intentionally left uncommitted). Task 9 is complete and
review-clean; Task 8 is unblocked.

---

## Fix round 1

Review verdict addressed: **NOT APPROVED — 2 Critical, 2 Important, 6 Minor**
(`task-9-review.md`). All ten findings are accounted for below; nine were
coded, one (Minor 10) was assessed and deliberately left as no-change with the
reasoning recorded.

Worktree `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`,
branch `codex/radar-pipeline-audit`, parent commit `dedc90b`.

### Critical 1 — a not-due Reddit cycle wrote a zero-count root `reddit` row

Neither fix the review offered was taken. Both write zero children claiming
coverage that may be false: the first (an `ok` entry for every configured sub)
turns one wrong zero into eight, and the second (restricting to the subs whose
`last_polled_at` covers the window) still asserts an observation for a cycle in
which no request was made.

The controller's ruling was applied instead, literally: when nothing is due,
Reddit was **not read at all**, so there is no observation. Not an `ok` zero
(we did not measure a quiet period), not a `missing` (we did not try and
fail). Neither belongs in the bucket population.

Implemented by making `per_source_status` distinguish "no per-source
information" from "explicitly no sources observed":

- `features/radar/sources/__init__.py` — `FetchResult.per_source_status` is
  now `dict | None = None`. The three states and what each means are
  documented on the field: `None` = this fetcher does not report per-source
  status (Bluesky, 4chan), a populated map = these names were observed, and an
  empty map = explicitly nothing was observed.
- `run_radar_ingest.py:138` — the not-due branch returns
  `FetchResult(posts=[], status='ok', per_source_status={})`.
- `features/radar/ingest.py:246` — tests `if result.per_source_status is None`
  rather than truthiness, so an explicit empty map records nothing while
  `None` keeps the `{source: result.status}` fallback. The
  everything-failed guard became `if not result_statuses or all(... ==
  'missing' ...)`, so "no source observed" takes the skip path explicitly
  rather than by the vacuous truth of `all([])`.

Regression: `tests/test_radar_ingest.py::test_a_source_that_observed_nothing_writes_no_row_at_all`
runs `run_cycle` with an explicitly empty per-source map under the key
`'reddit'` alongside a producing Bluesky fetcher, and asserts no
`source='reddit'` child row exists — plus that `RadarBucket.sources_ok` reads
1, not 2. Absence-shaped; watched failing under mutation (teeth table, row T1).

### Critical 2 — `expand_sources` dropped the root, hiding all pre-deploy Reddit history

The review's recommended two-helper split was adopted with its exact call-site
list.

`features/radar/config.py` now carries a block comment above both helpers
saying WHY there are two and what merging them breaks in each direction — a
raw count is addition and pooling the older half is correct; a z is relative
to a baseline and the older rows carry the previous `source_config_version`.

- `expand_sources(names)` — STRICT, concrete only. Docstring names its
  callers.
- `expand_sources_for_history(names)` — concrete PLUS the bare `reddit`, and
  only when the root was actually selected (a reader who asked for one
  subreddit does not get the undifferentiated pre-split history).

Call sites, each expanding inside the function so the choice cannot be lost by
a caller:

| Family | Function | Helper |
|---|---|---|
| scored | `leaderboard.build_rows` (bucket aggregate) | strict |
| scored | `board._triplets` | strict |
| scored | `detail_panel.window_figures` | strict |
| scored | `scoring.pooled_z`, `scoring.window_z` | strict |
| scored | `run_radar_ingest.score_all` | strict (unchanged) |
| raw | `board._covered_hours`, `_hourly_counts`, `_tones` | history |
| raw | `detail.daily_counts`, `first_watched_day`, `intraday_counts`, `_watched_from_index` | history |
| raw | `detail_panel.breakdown_for`, `_posts` | history |
| raw | `journal.distinct_voices` | history |

`window_figures` is not in the review's history list and is strict here: it
reads `expected` and `baseline_days`, and the written read quotes `mentions`
against `expected` in one sentence.

`routes/api.py` no longer expands. It hands `query.sources` — the viewer's
selection — to `board_mod.build` and `detail_panel.build`, because once the
list is expanded the root is gone and no downstream query can tell it was ever
asked for. `board.build` and `detail_panel.build` docstrings state that they
receive a selection.

`journal.py` imports `expand_sources_for_history` by name from `.config`,
which is safe: the fragile cycle is `buckets` <-> `journal`, and `config`
imports nothing from the package. Fresh-process imports re-verified (gate 4).

Regressions, all against an owned bucket/post fixture written under the bare
`reddit` name with the real pre-split stamp `8106787f1fa72179`:

- `test_radar_board.py::test_the_pre_split_reddit_history_still_counts_on_the_series`
  (raw bucket read — teeth T2)
- `test_radar_board.py::test_the_pre_split_reddit_history_still_counts_towards_tone`
  (raw post read — teeth T3)
- `test_radar_board.py::test_the_pre_split_reddit_history_is_kept_out_of_the_ranking`
  (scored read still excludes it)
- `test_radar_board.py::test_one_named_subreddit_does_not_reach_the_undifferentiated_history`
  (history expansion is root-only)
- `test_radar_detail.py::test_the_chart_still_draws_the_pre_split_reddit_history`
  (`daily_counts` + `first_watched_day` — teeth T4)
- `test_radar_leaderboard.py::test_the_pre_split_reddit_voices_still_count`
  (`journal.distinct_voices` — teeth T5)

### Important 3 — two subreddits read as two independent venues

Venues are counted by ROOT. `leaderboard.Row` gained a `venues: int` field
carrying the count of distinct roots among the contributing names; `sources`
stays concrete because it is the breakdown. Fixed together, as one decision:

- `leaderboard.py` — the `single-source` mark compares rooted contributing
  against rooted *selected* counts; the `min_venues` gate uses `venues`.
- `board.py:289,296` — `venue_counts['multi']` and the `min_venues` filter use
  `row.venues`.
- `phrasing.py:102` — `venues = row.venues`.
- `buckets.py:149` (**Minor 9**) — `sources_ok` counts distinct roots among
  the `ok` statuses, so it no longer rises and falls with
  `REDDIT_SUBS_PER_CYCLE`.

Regression: `test_radar_board.py::test_two_subreddits_are_one_venue` — a
ticker in r/wallstreetbets and r/pennystocks and nowhere else does not clear
`min_venues=2`, reports `venues == 1`, keeps both concrete names in `sources`,
and carries the `single-source` mark. Absence-shaped (the row is NOT in the
result); teeth T6.

`tests/test_radar_phrasing.py::FakeRow` gained `venues` as a derived property
rather than a field, so the fake cannot claim a breadth its own source list
does not support.

### Important 4 — the detail panel rendered raw internal source names

Ruling applied: **Task 9 changes the population, not the presentation.** The
venue breakdown is pooled back under a single `Reddit` row exactly as before
this task, and no `r/<sub>` label ships.

- `detail_panel.breakdown_for` groups its venue map on `source_root(source)`,
  so the eight `reddit:<sub>` names and the pre-split bare `reddit` pool into
  one `reddit` venue with one voices count and one share of mentions. This
  also makes `venues=len(b.venues)` in the written read a rooted count for
  free.
- `static/radar/src/format.ts::sourceLabel` roots the key before the lookup
  and falls through as the WHOLE key when the root is unknown, so
  `discord:general` still renders as itself. This covers the post badges,
  whose `source` stays concrete on the wire.
- **Minor 6** follows from the same rooting: `build_payload` now sets
  `board.sources` to the sorted set of roots of the selection, so
  `?sources=reddit:wallstreetbets` filters to that sub and still lights the
  Reddit chip instead of rendering every chip off.

Regressions: `format.test.ts` ("names the venue, not the subreddit", plus an
unknown-root-with-suffix case); `test_radar_detail.py::test_the_breakdown_still_shows_one_reddit_row`;
`test_radar_api.py::test_a_concrete_subreddit_link_lights_the_reddit_chip`.

### Minor 5 — `sources=` cardinality is now capped

`routes/api.py` gained `MAX_SOURCES = len(SOURCES) + len(REDDIT_SUBS)` — the
largest selection that can name anything real — and `parse_query` raises
`BadQuery('too many sources')` above it. Covered by
`test_a_selection_longer_than_every_real_name_is_rejected`, which asserts the
boundary in both directions.

### Minor 7 — undocumented width dependency in the downgrade

`migrations/versions/08316d3e4d77_widen_radar_source_columns.py` `downgrade()`
now states the dependency (longest configured name is
`reddit:smallstreetbets` at 22; a sub name over 17 characters breaks it) and
guards it with a `SELECT COUNT(*) ... WHERE CHAR_LENGTH(source) > 24` that
raises a readable `RuntimeError` before the narrowing rather than failing with
MySQL 1406 after `radar_poll_state`'s DDL has auto-committed. `int()` at the
query boundary. `CHAR_LENGTH` parses on MySQL 8 and MariaDB alike. No
migration was run in either direction; the DB stays at `08316d3e4d77`.

### Minor 8 — the migration did not state what the downgrade cannot restore

The report's rollback-boundary paragraph now lives in the `downgrade()`
docstring: what it restores (the `radar_posts` normalisation), what it cannot
(per-subreddit bucket history is not re-aggregatable, so it is left under its
prefixed names and reads as absent rather than as a wrong aggregate), and that
a re-upgrade recovers it intact.

### Minor 9 — `RadarBucket.sources_ok` counted concrete names

Fixed in the same pass as Important 3; see above.

### Minor 10 — historical root Reddit buckets are never re-invalidated

**Assessed as closed. No code written.** Reasoning:

1. `score_all` walks the strict expansion of `SOURCES`, which is concrete
   only, so `score_source('reddit', ...)` never runs and the root rows' stale
   `mention_z` (stamp `8106787f1fa72179`) is never cleared outside the daemon
   start's bootstrap window.
2. That stale value is unreadable. After this fix every SCORED read expands
   strictly — `leaderboard.build_rows`, `board._triplets`,
   `detail_panel.window_figures`, `scoring.pooled_z` / `window_z` — so no
   query carrying `mention_z IS NOT NULL` ever has `'reddit'` in its `IN
   (...)` list. The reads that DO see the root select only `mention_count`,
   `bucket_start` and `status`; none touches `expected`, `variance`,
   `mention_z` or `baseline_days`.
3. It cannot contaminate a baseline either, and for two independent reasons:
   `scoring._rows_by_ticker` filters on
   `source_config_version == config_version`, and `baselines.usable` filters
   on `o.config_version == config_version`. The `source_config_version()` bump
   this task made is what puts the old rows on the wrong side of both.

So the hole the review describes ("it becomes load-bearing the moment the root
is re-admitted to any scored read") is precisely what the two-helper split
makes structurally impossible: the root is admitted to raw-count reads only,
and a raw count has no stamp dependency. Writing an invalidation pass for the
root would clear a column nothing reads, on rows nothing baselines from — and
it would have to walk the whole retained history rather than a lookback
window to do it.

The genuine residual risk is that a future change re-admits the root to a
scored read without noticing. That is addressed by documentation rather than
by code: the block comment above the two helpers in `config.py` states the
rule and why the helpers must not be merged, and each helper's docstring names
its call sites.

### Collateral test changes

- `tests/test_radar_scoring.py` — `pooled_z` now expands strictly, so the
  literal `'reddit'` those fixtures wrote is a SELECTION rather than a stored
  name and expands to eight subs that match nothing. The suite's second source
  became `REDDIT = 'reddit:pennystocks'`, a concrete configured name, with the
  reason on the constant. Substance unchanged (two sources pooling, a missing
  source dropping out).
- `tests/test_radar_api.py` — the two tests that asserted the API expands
  before calling `build` now assert the opposite, which is the fix:
  `test_the_board_gets_the_selection_and_echoes_the_root` and
  `test_the_detail_panel_gets_the_selection`. The expansion itself is proved
  where it now happens, by the historical-root tests in the board and detail
  suites, which is stronger than capturing a call argument.

### Teeth

Every mutation is a targeted edit to PRODUCTION code, reverted by the inverse
edit immediately after the failure was observed. **Not** by `git checkout --`:
these files hold uncommitted work, and reverting the file reverts the fix
along with the mutation. That mistake was made once on `ingest.py` during T1,
caught by the covering test failing after the "revert", and the fix was
re-applied and re-verified before continuing.

| # | Assertion under test | Shape | Mutation | Exact failure | Reverted |
|---|---|---|---|---|---|
| T1 | no `source='reddit'` child row when Reddit observed nothing; `sources_ok == 1` | absence | `ingest.py`: `result_statuses = result.per_source_status or {source: result.status}` (truthiness instead of `is not None`) | `AssertionError: assert {'bluesky': '...reddit': 'ok'} == {'bluesky': 'ok'}` / `Left contains 1 more item: {'reddit': 'ok'}`; the row-level probe under the same mutation printed `child rows : {'bluesky': ('ok', 1), 'reddit': ('ok', 0)}`, `root 'reddit': 1`, `sources_ok: {2}` | ✓ |
| T2 | the pre-split root bucket still counts on the 24h series | absence (row IS visible) | `board._hourly_counts`: `expand_sources_for_history` → `expand_sources` | `assert 10 == 17` — `Point(hour=2026-01-15 14:00, count=10).count` | ✓ |
| T3 | the pre-split root posts still count towards tone | absence | `board._tones`: `expand_sources_for_history` → `expand_sources` | `assert 1 == 2` — `Tone(bullish=1, neutral=0, bearish=0).bullish` | ✓ |
| T4a | `detail.daily_counts` sees the pre-split root day | absence | `detail.daily_counts`: history expansion filtered to drop `'reddit'` | `KeyError: ('DTH', datetime.date(2025, 8, 24))` | ✓ |
| T4b | `detail.first_watched_day` sees the pre-split root day | absence | `detail.first_watched_day`: history expansion filtered to drop `'reddit'` | `AssertionError: assert None == (datetime.date(2026, 3, 12) - datetime.timedelta(days=200))` | ✓ |
| T5 | `journal.distinct_voices` counts the pre-split root authors | absence | `journal.distinct_voices`: history expansion filtered to drop `'reddit'` | `assert 2 == 4` | ✓ |
| T6 | a ticker in two subreddits and nowhere else does NOT clear `min_venues=2` | absence (row NOT in result) | `leaderboard`: `venues = len({source_root(n) ...})` → `venues = len(contributing)` | `AssertionError: assert ['BDA', 'BDB'] == ['BDB']` / `Left contains one more item: 'BDB'` | ✓ |
| T7 | the venue breakdown holds exactly `{bluesky, reddit}` — no per-subreddit rows | absence (rows NOT present) | `detail_panel.breakdown_for`: `venue = source_root(source)` → `venue = source` | `AssertionError: assert {'bluesky', '...llstreetbets'} == {'bluesky', 'reddit'}` / `Extra items in the left set: 'reddit:pennystocks', 'reddit:wallstreetbets'` | ✓ |
| T8 | a concrete-subreddit link lights the Reddit chip | value | `routes/api.build_payload`: rooted set → `list(query.sources)` | `AssertionError: assert ['reddit:wallstreetbets'] == ['reddit']` | ✓ |
| T9 | `sourceLabel('reddit:wallstreetbets') === 'Reddit'` | value | `format.ts`: `const root = key.split(':')[0] ?? key` → `const root = key` | `AssertionError: expected 'reddit:wallstreetbets' to be 'Reddit'` (`format.test.ts > labels > names the venue, not the subreddit`) | ✓ |

Nine of the ten new/changed assertions were watched failing; the tenth (Minor
5's cardinality cap) is a plain boundary test asserting 200 on the largest
real selection and 400 one entry past it, which is not absence-shaped and
fails by construction if the cap is removed.

After the last revert, `git diff` was grepped for every mutation marker
(`if n != 'reddit'`, `venue = source$`, `const root = key$`,
`board.sources = list(query`, `result.per_source_status or`) and none
appears; `py_compile` is clean on all fourteen touched Python files.

### Gates

**Gate 1 — focused, every file touched** (from `personal_apps/`):

```
python -m pytest tests/test_radar_board.py tests/test_radar_detail.py \
  tests/test_radar_leaderboard.py tests/test_radar_ingest.py \
  tests/test_radar_scoring.py tests/test_radar_phrasing.py \
  tests/test_radar_buckets.py tests/test_radar_journal.py \
  tests/test_radar_config.py tests/test_radar_reddit.py \
  tests/test_radar_daemon.py -q
-> 281 passed in 56.09s
```

**Gate 2 — full radar suite**:

```
python -m pytest tests/ -k radar -q
-> 2 failed, 617 passed, 2 skipped, 646 deselected, 2 warnings in 67.25s
FAILED tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch
FAILED tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query
```

Exactly the two known `ViteManifestError` failures from the gitignored
`static/radar/dist/.vite/manifest.json`. No third failure. Not fixed, per
instruction. (Baseline before this round was `2 failed, 606 passed`; the round
adds 11 passing tests.)

**Gate 3 — frontend**:

```
npx tsc --noEmit                          -> clean (exit 0, no output)
npx vitest run -c vite.radar.config.ts    -> Test Files 9 passed (9) | Tests 80 passed (80)
npx vitest run                            -> Test Files 32 passed (32) | Tests 403 passed (403)
```

**Gate 4 — fresh-process imports** (four separate processes, from
`personal_apps/`):

```
python -c "from features.radar import buckets"          -> buckets OK
python -c "from features.radar import journal"          -> journal OK
python -c "from features.radar import ingest"           -> ingest OK
python -c "from run_radar_ingest import build_fetchers" -> build_fetchers OK
```

The deliberate `buckets` <-> `journal` cycle survives the new
`from .config import expand_sources_for_history` in `journal.py`, as expected:
`config` imports nothing from the package, so it can never be the module
mid-import.

**Gate 5 — Alembic**:

```
python -m flask db current -> 08316d3e4d77 (head)
python -m flask db heads   -> 08316d3e4d77 (head)
```

Single head, unchanged. No migration was run in either direction; the
`downgrade()` edit is documentation plus a pre-flight guard and does not
require a re-run to take effect.

**Gate 6 — no leftover teeth mutation**: see the teeth section above.

### Shared-database hygiene

No broad `LIKE 'ZZ%'` teardown was added. New fixtures reuse the owning
suites' existing namespaces and their existing cleanup:

- `test_radar_board.py` — `BD*` tickers under the file's `clean` fixture.
- `test_radar_detail.py` — `DT*` tickers under the file's `clean` /
  `panel_ticker` fixtures.
- `test_radar_leaderboard.py` — `LBH` under the file's `board` fixture, which
  already clears `RadarMentionEvent` for `LB%`.
- `test_radar_ingest.py` — the existing `TEST_TICKER = 'ZZG'` /
  `TEST_CHANNEL` exact-identity `_wipe`.

The one-off root-row probe used during T1 wrote and deleted its own rows by
exact identity (`channel == 'zz_teeth_t1'`, `ticker == 'ZZG'`, cursors for
`bluesky`/`reddit`) and left nothing behind.

The pre-existing broad `ZZ%` teardowns the review flagged in
`test_radar_daemon.py` and `test_radar_journal.py` were NOT touched — they are
not this task's and fixing them here would widen the diff past the review's
scope. They remain worth a separate cleanup.

### Concerns

1. **`scoring.pooled_z` / `window_z` have no production caller.** Applying the
   strict expansion there is future-proofing with zero runtime effect today
   (they are reached only from tests and from `is_sustained`, which nothing
   calls). It did force two test fixtures to stop using the bare `'reddit'` as
   a stored source name — see "Collateral test changes". If the intended
   contract is instead that these two take already-expanded stored names, the
   two `expand_sources(sources)` lines and the `REDDIT` constant in
   `test_radar_scoring.py` come straight back out.

2. **`Row.venues` is not serialized.** `_row()` still sends only the concrete
   `sources`. Nothing on the client counts venues today — the marks and both
   filters are decided server-side — so this is not a bug, but a future client
   that wants a venue count must be given `venues` rather than
   `row.sources.length`.

3. **`board.excluded['one_venue']` is still never populated from `board.build`,**
   which passes `min_venues=1` down to `build_rows` and applies its own filter
   afterwards. Pre-existing, unchanged by this round, and orthogonal to the
   rooting — flagged only because the venue code was read closely here.

4. **Blast radius of Critical 2 is still unmeasured locally.** The local dev
   DB holds no root `reddit` rows at all, so every historical-root test runs
   against an inserted fixture. The mechanism is proved; how much production
   history it restores depends on the 4372 + 478 root Reddit bucket rows the
   brief cites, which cannot be checked from here.

5. **MariaDB.** `CHAR_LENGTH` and the `SELECT COUNT(*)` guard added to
   `downgrade()` are engine-neutral by inspection but have only been parsed
   against local MySQL 8 — and only by `py_compile` plus reading, since no
   downgrade was run.

### Commit

```
commit cc2d278  fix(radar): keep historical Reddit visible and stop zero-count root rows
23 files changed, 667 insertions(+), 52 deletions(-)
```

Staged by exact path (23 paths listed individually to `git add --`, no
`-A`, no glob). Protected files untouched: `git show --stat cc2d278`
contains no `discover_telegram_sources.py`, no `telegram_candidates.json`,
no `reddit_candidates.json`. Post-commit `git status --short` shows only
this report file modified, which is deliberate.

Nine of ten findings fixed in code; Minor 10 assessed as closed with the
reasoning above and no code written.

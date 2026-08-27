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


# Final branch fix re-review — radar pipeline audit

Review date: 2026-08-28
Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`
Reviewed HEAD: `d9c7f76e655571b78ad7256c3bb8fabe706cde11`
Review range: `8752c02..d9c7f76` (seven commits)
Reviewer standing: the six-commit wave `3d2dced..a9055b4` was treated as unreviewed
code, not as approved work. Every claim in `final-branch-fix-report.md` was
re-derived against the tree, the database, or a mutation, not accepted on the
strength of the report.

---

## Merge verdict

**VERDICT: MERGE.**

Addressed: **6 of 6**. New Critical: **0**. New Important: **0**. New Minor: **4**.

All three Important findings (I1, I2, I3) and all three FIX-BEFORE-MERGE Minor
findings (M1, M2, M3) are genuinely closed. Every teeth claim in the wave was
re-derived independently: eleven mutations were applied by hand, each failed for
the intended reason, and each was reverted with `git diff --exit-code` proving the
restoration.

The seventh commit's count-assertion rewrite — the single highest-risk item in this
re-review, because a test rewritten to go green is this branch's most repeated
failure mode — **has teeth**. It is not tautological. Two independent mutations of
the prune's predicate both fail at the count assertion itself (`test_radar_retention.py:185`),
not at the downstream identity assertion.

The four new Minor findings are follow-up debt: two one-line test-ownership fixes,
one teeth gap in a pre-existing assertion, and one residual instance of M1's own
defect class on a downgrade path documented as never-for-production. None of them
touch production behaviour and none of them block the merge.

State on exit: HEAD `d9c7f76`, `git diff --exit-code` clean, `git status --short`
empty of source modifications, `radar_mention_events` = **1432** before and after.

---

## Finding-by-finding

### I1 — Shared-DB test cleanup can delete data it does not own → **ADDRESSED**

Commit `3d2dced`.

**What I did.**

1. *Predicate sweep.* Scanned every `.like(` occurrence in `tests/test_radar_*.py`
   with both `grep` and an independent regex pass over the raw file text (to catch
   multi-line calls the line-oriented grep would miss). **None of the six named files
   contains a broad prefix delete any more.** The surviving `LIKE` deletes are all in
   files outside I1's scope, each on its own distinct namespace: `test_radar_board.py`
   / `test_radar_detail.py` / `test_radar_history.py` / `test_radar_profile_order.py` /
   `test_radar_quote_retention.py` / `test_radar_quotes_batch.py` (per-file `PREFIX`),
   `test_radar_leaderboard.py` (`LB%`), `test_radar_profile.py` (`PP%`),
   `test_radar_quotes.py` (`QQ%`), `test_radar_llm_sentiment.py` (`zztest%`),
   `test_radar_api.py` (per-test `tag`).

2. *Ownership, both directions.* I1 asks two things: a fixture must not delete what it
   does not own, and (implicitly, since the DB is shared and real) it must clean what it
   does create. I verified the second empirically. Snapshot of all seven radar tables,
   then `pytest tests/test_radar_buckets.py tests/test_radar_bucket_sources.py
   tests/test_radar_journal.py tests/test_radar_universe.py tests/test_radar_daemon.py`
   (125 passed), then re-snapshot: **identical on every table.** The destructive file
   was run separately (`tests/test_radar_retention.py`, 6 passed): **also identical.**

   ```
   radar_buckets 0 | radar_bucket_sources 29460 | radar_mention_events 1432
   radar_posts 1432 | radar_mentions 1432 | radar_ticker_universe 12509 | radar_quotes 3744
   ```

3. *Identity-list completeness.* Checked the one place the tightening could have
   under-covered: `clean_retained_mentions` narrowed from `external_id.like('zz-bootstrap-%')`
   to an exact three-element `_OWNED_RETAINED_POST_IDS`. `_OWNED_EVENT_IDENTITIES` lists a
   fourth `zz-bootstrap-post`, which looks like a gap — it is not. `zz-bootstrap-post`
   (`test_radar_journal.py:361`) is created via `_row(...)` as a mention *event* only;
   `_retained_post(...)` is called for `high`/`low`/`pre` alone. The two lists are correct
   as written.

4. *Sentinel regression, re-derived.* Confirmed first that the dev DB currently holds
   **zero** `ZZ%` rows in `radar_bucket_sources`, `radar_buckets`, `radar_mention_events`
   and `radar_ticker_universe` — so widening the predicate could only touch the sentinel
   the test creates. Then applied the mutation (see teeth table, mutation 1). It fails.

**Verdict: ADDRESSED.** One shared-DB hazard was not traded for another *inside these six
files*. A related, lower-severity ownership gap in a file I1 did not scope is raised as
new finding **N1** below.

---

### I2 — The one-shot backfill erases scores that Task 8 made legitimate → **ADDRESSED**

Commit `2bc2c19`. This is the finding with production consequences, so it got the most
scrutiny.

**What I did.**

1. *Read the predicate as SQL, not as Python.* Compiled the live query with
   `literal_binds` against the MySQL dialect:

   ```sql
   (status IS NULL
    OR (status NOT IN ('truncated', 'ok'))
    OR source_config_version IS NULL
    OR source_config_version != '705b043693b533db')
   AND (expected IS NOT NULL OR variance IS NOT NULL
        OR mention_z IS NOT NULL OR baseline_days IS NOT NULL)
   ```

   The two `.filter()` positional arguments AND correctly. Crucially, **both NULL cases are
   explicit branches**: `status NOT IN (...)` and `version != '...'` both evaluate to
   `UNKNOWN` (not `TRUE`) under SQL three-valued logic when the column is NULL, and the
   preceding `IS NULL` branches are what actually catch those rows. Getting that wrong is
   the classic way this predicate silently leaves relabelled rows ranked; it is right here.

2. *The four boundaries, all covered by test and all confirmed against the predicate:*

   | Row | status | generation | predicate | outcome | pinned at |
   |---|---|---|---|---|---|
   | `ZZBF4` | `truncated` | current | no branch true | **kept** | `test_radar_backfill.py:207` |
   | `ZZBF5` | `truncated` | `old-gen-5` | `version != current` | **cleared** | `:210` |
   | `ZZBF6` | `truncated` | NULL | `version IS NULL` | **cleared** | `:212` |
   | `ZZBF7` | `missing` | current | `status NOT IN (...)` | **cleared** | `:215` |
   | `ZZBF8` | `ok` | current | no branch true | **kept** | `:218` |

   `test_stale_scores_follow_final_status_and_generation_policy` covers all five plus a
   dry-run/apply/rerun idempotence check (`rerun['stale_scores'] == 0`) and a
   `ticker_prefix='ZZNOPE'` scoping guard proving the stale query — not just the repair
   loop — is prefix-scoped.

3. *Teeth, both halves.* Re-derived rather than trusted (teeth table, mutations 8 and 9).
   Restoring the exact pre-fix policy (`status != 'ok'`) makes `ZZBF4` stale →
   `assert 4 == 3`. Disabling the generation half makes `ZZBF5`/`ZZBF6` survive →
   `assert 1 == 3`. Both halves of the new predicate are load-bearing.

4. *The rollup half of the same commit.* `2bc2c19` also changed production behaviour in
   `buckets.roll_up` (`buckets.py:236`), which the review did not explicitly ask for but
   which is required for coherence — otherwise the next rollup would clear exactly the
   scores the backfill now preserves. Its tooth was re-derived too (mutation 10):
   reverting it to `child.status != 'ok'` kills
   `test_current_generation_truncated_preserves_its_score`.

5. *Dry-run safety.* `repair(apply=False)` ends in `db.session.rollback()`; only the
   `apply` path commits. Confirmed by reading `scripts/backfill_radar_buckets.py:172-179`.

6. *Live read-only check.* Ran the compiled predicate against the real dev DB as a pure
   count: **0 stale rows** out of 29,460 (`status='ok'` on all of them, all at the current
   generation). Nothing was written.

7. *Definition drift.* `SCOREABLE_STATUSES` moved from `scoring.py` to `config.py`.
   Grepped every reference: `buckets.py:236`, `scoring.py:156`,
   `scripts/backfill_radar_buckets.py:153` all read the single definition, and
   `test_radar_scoring.py:160`'s `scoring.SCOREABLE_STATUSES` still resolves through
   scoring's import. Three call sites, one definition, no import cycle.

**Verdict: ADDRESSED.** Current-generation `truncated` scores survive; old-generation,
NULL-generation and unscoreable rows clear; the script is idempotent on rerun.

---

### I3 — Reddit aggregate health and failed-fetch depth stop at test-only dictionaries → **ADDRESSED**

Commit `f107380`.

**What I did.**

1. *Traced to a real consumer, not a test double.* `run_cycle` now returns a separate
   `aggregate_status` map (`ingest.py:257`, `:249` on the exception path), and
   `run_radar_ingest.tick()` renders both it and `catchup_depth` into its `logger.info`
   line (`run_radar_ingest.py:214-219`) through `_format_operational_map`, which prints
   `unknown` for `None` rather than `0`. `tick()` is reached from two live APScheduler
   jobs — `_scheduled_cycle` (`:232`, the 180-second `radar_cycle` job at `:584`) and
   `_scheduled_reddit` (`:455`, the separate Reddit interval job at `:589`). The value
   reaches an operator through the daemon's own log, which is exactly the consumer the
   review demanded.

2. *Storage stays clean.* `statuses` (the only map handed to `buckets.roll_up`) is still
   populated exclusively from `result.per_source_status` when it exists. `aggregate_statuses`
   is a parallel dict that never reaches rollup. Verified by reading `ingest.py:255-275`
   and by mutation.

3. *Three teeth re-derived* (teeth table, mutations 5–7), because a reporting path
   observed only by a test double would leave the finding open:
   - dropping `aggregate_statuses[source] = result.status` → the partial-Reddit test fails
     with `assert {} == {'reddit': 'truncated'}`, and the captured log line degrades to
     `aggregate=none`;
   - `depths[source] = None` → `0` on the exception path → **two** tests fail and the
     captured log reads `catchup_depth=bluesky=0`, the exact string the review named;
   - forcing the aggregate into storage (`if result.per_source_status is None:` → `if True:`)
     → the rollup-recording assertion fails with
     `[{'reddit': 'truncated'}] != [{'reddit:pennystocks': 'ok', 'reddit:wallstreetbets': 'missing'}]`.

   The partial-cycle test monkeypatches `roll_up` to *record and delegate* — the real
   rollup still runs, and the test then re-reads `RadarBucketSource` from the database to
   assert `stored_sources == {'reddit:pennystocks'}`. That is a runtime observation, not a
   double.

4. *Schema consistency.* The `tick()` exception fallback now returns
   `'aggregate_status': {}, 'catchup_depth': {}` alongside `'per_source': {}`, pinned by
   `test_a_cycle_that_raises_does_not_kill_the_daemon`.

**Verdict: ADDRESSED.** A partial Reddit cycle reports root health without writing a root
child row, and a failed fetch reports `unknown` rather than a zero depth — both at runtime,
both through the production logger.

---

### M1 — The width guard runs after irreversible downgrade DDL → **ADDRESSED**

Commit `3a3c4b1`. **No downgrade was run.**

**What I did.** Read `08316d3e4d77_widen_radar_source_columns.py` in full. `downgrade()` now
opens with two read-only `SELECT MAX(CHAR_LENGTH(source))` probes — `radar_poll_state` first,
then `radar_bucket_sources` — accumulates violations, and raises before the first
`op.alter_column`. Nothing is half-applied on a failed preflight, which is the correct
shape for MariaDB, where each `ALTER` auto-commits and no surrounding transaction can undo
one. `int(maximum or 0)` at the query boundary handles the `Decimal`/`None` return-type
difference between drivers.

`tests/test_radar_migration.py` is a genuine behavioural guard, not a smoke test: a fake
`op`/bind harness records an ordered event log, so `test_..._aborts_before_ddl_for_either_violation`
asserts the event list is *exactly* `[('check','radar_poll_state'), ('check','radar_bucket_sources')]`
— i.e. it proves the absence of any DDL event, parameterised over both violating tables.
The success-path test pins that both checks precede the DDL and that the original ALTER
order is preserved. The harness never opens a connection; `exec_module` only defines
functions.

**Verdict: ADDRESSED.** A residual instance of the same defect class on a third table is
raised as new finding **N4** below.

---

### M2 — Four strict scored-read boundaries have no direct mutation tooth → **ADDRESSED**

Commit `9139749`.

**What I did.** The obvious way for these four tests to be fake is for the pre-split root
row to be excluded by a *generation* filter rather than by strict source expansion — three
of the four fixtures stamp the root row with the old `'8106787f1fa72179'`, which would make
the tooth an illusion. So I read all four readers before trusting any of them:
`board._triplets` (`board.py:186-198`), `detail_panel.window_figures`
(`detail_panel.py:102-108`), `scoring.pooled_z` (`scoring.py:187-192`) and
`scoring.window_z` (`scoring.py:257-264`). **None of the four filters on
`source_config_version`.** The only thing excluding the root row is
`source.in_(expand_sources(...))`, so the old generation stamp in the fixtures is inert
decoration and the teeth are real.

Then I re-derived **all four** strict-to-history mutants rather than the two required
(teeth table, mutations 2–4 plus the board one at mutation 2). Every one fails, and each
fails only its own test — mutating `pooled_z` left `window_z`'s test green and vice versa,
which proves the four are independent rather than one tooth counted four times.

One note on method: mutating `scoring.py` naively produces a `NameError`, because
`expand_sources_for_history` is not imported there. A `NameError` is not a tooth — it fails
for the wrong reason. I added the import as part of the mutation so that the mutant was the
semantically valid "someone consolidated the two helpers" change the finding actually
describes, and only then recorded the failure.

**Verdict: ADDRESSED.**

---

### M3 — StockTwits retirement does not pin the last policy-map key → **ADDRESSED**

Commit `a9055b4`.

**What I did.** Re-derived the exact mutant the finding names: inserted
`'stocktwits': False` into `COIN_SYMBOLS_MEAN_STOCKS` (`config.py:95-98`) and ran
`test_stocktwits_is_retired`. It fails on the new line with
`assert 'stocktwits' not in {'bluesky': False, 'fourchan': False, 'stocktwits': False}` —
the false-valued key that the trailing `not any(values())` assertion would have let through
is now killed. Reverted, and confirmed the generation stamp is back to
`705b043693b533db`, matching the value the final branch review recorded (the mutation moves
it, since `coin_means_stocks` is hashed into `source_config_version` at `config.py:667`).

**Verdict: ADDRESSED.**

---

## Seventh-commit audit (`d9c7f76`)

### Fix 1 — removing the `aggregate_status` assertion from the extract-once test

**Correct call. Confirmed, not assumed.**

`test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement` builds its cycle
as `fetcher_for(FetchResult(posts=duplicate, status='ok'))`, and `fetcher_for`'s signature
is `def fetcher_for(result, source='bluesky')` (`test_radar_ingest.py:79-82`). The fixture
is a single-source **bluesky** fetch that succeeds. The removed assertion claimed
`{'reddit': 'missing'}` — a value that was never reachable for this fixture under any
correct implementation. The production line is right: `aggregate_statuses[source] = result.status`
yields `{'bluesky': 'ok'}` here. So option 3 (production bug) is genuinely excluded, and
"correcting" the assertion in place would have coupled a Task 13 extract-once test to a
feature it does not test.

The load-bearing question is whether removing it deleted the only coverage. **It did not,
and I verified this by mutation rather than by reading the test names.** Both dedicated
tests from `f107380` exist and both have real teeth against the exact behaviours I3 names —
mutations 5, 6 and 7 in the teeth table below kill them. `test_tick_reports_reddit_aggregate_without_root_rollup`
covers root-health-without-root-storage (and re-reads the database to prove the storage
half), `test_tick_visibly_logs_failed_fetch_depth_as_unknown` covers unknown-not-zero depth
against the real captured log line.

### Fix 2 — the count assertion: **HAS TEETH, not tautological**

This is the item the re-review was told to judge hardest, and the concern is legitimate in
the general case: measuring an expectation with the same predicate the implementation uses
usually means a wrong predicate satisfies its own assertion. **It does not here, for one
specific structural reason:** the expectation is computed from a predicate *re-stated
independently in the test* (`test_radar_retention.py:176-178`), not obtained by calling the
implementation. The test hard-codes its own `cutoff = now - timedelta(hours=retention.MENTION_EVENT_RETENTION_HOURS)`
and its own `created_utc < cutoff`. That is oracle duplication, not tautology — the two
sides can and do diverge the moment the implementation's predicate changes.

I proved that rather than reasoning about it. Two mutations of the prune's own comparison
and its window arithmetic:

- `retention.py:122` `created_utc < cutoff` → `<= cutoff`:
  **fails at `tests/test_radar_retention.py:185: assert 2 == 1`** — the count assertion, not
  the downstream identity assertion.
- `retention.py:115` `hours=MENTION_EVENT_RETENTION_HOURS` → `hours=... * 2`:
  **fails at `tests/test_radar_retention.py:185: assert 0 == 1`** — again the count
  assertion, and again first.

In both cases the count assertion is the line that goes red, so it is doing work rather than
being carried by the identity assertions. The identity assertion
(`remaining == {'zz-new', 'zz-boundary'}`) independently covers the one axis the count
cannot: a change to the shared `MENTION_EVENT_RETENTION_HOURS` constant itself, which moves
both sides of the count equally. The two assertions are complementary, and neither is
redundant.

**Judgement: the spec did not silently loosen.** The rewrite removed a global-count
assertion over a shared table — a genuine defect — and replaced it with an assertion that
is strictly harder to satisfy accidentally than the literal `== 1` was, because the literal
`1` was itself only correct in a database no other suite had touched.

Two caveats, raised as new findings N2 and N3 below, neither of which changes this verdict:
the surviving `bucket_start`-for-`created_utc` mutant is a *pre-existing* teeth gap that
`d9c7f76` neither introduced nor was asked to close, and the `remaining` read is still
scoped by ticker rather than by owned identity.

### On routing around the leak rather than fixing it

`d9c7f76` deliberately did not touch `test_radar_leaderboard.py`, which is the actual source
of the rows that broke the old assertion. I judge that call **correct**: making the retention
assertion leak-proof is the right general remedy regardless of who leaks, and registering
`zz-h`/`zz-l` would only have suppressed today's specific instance. But the leak itself is a
real, still-open defect and is graded below as N1 — the report flagged it as a concern and
left it, and this gate is where it gets a grade.

---

## Teeth re-derivation

Eleven mutations, applied by hand at the reviewed HEAD. Every one reverted with
`git checkout --` followed by `git diff --exit-code` returning clean.

| # | Finding | Mutation | Site | Result | Reverted |
|---|---|---|---|---|---|
| 1 | I1 | `_clear_owned_rows`: `ticker.in_(_OWNED_TICKERS)` → `ticker.like('ZZ%')` | `tests/test_radar_buckets.py:26` | **FAIL** `test_clean_buckets_preserves_an_unowned_zz_sentinel` — `AssertionError: assert 0 == 1` (sentinel `ZZF565547688` swept by setup) | ✓ |
| 2 | M2 | `expand_sources` → `expand_sources_for_history` | `features/radar/board.py:186` | **FAIL** `test_triplets_exclude_pre_split_root_reddit_scores` — `assert {1: 449.0024498819578, …} == {1: 2.0, 4: 2.0, 24: 2.0}` | ✓ |
| 3 | M2 | same | `features/radar/detail_panel.py:102` | **FAIL** `test_window_figures_exclude_pre_split_root_reddit_scores` — `assert (1006, 902.0, 1.0) == (5, 1.0, 12.0)` | ✓ |
| 4 | M2 | same (+ import added, so the mutant is semantically valid rather than a `NameError`) | `features/radar/scoring.py:187` | **FAIL** `test_pooled_z_excludes_pre_split_root_reddit_scores` — `assert 449.0024498819578 == 2.0`; `window_z`'s test stayed green, proving independence | ✓ |
| 5 | M2 | same | `features/radar/scoring.py:257` | **FAIL** `test_window_z_excludes_pre_split_root_reddit_scores` — `assert 449.0024498819578 == 2.0`; `pooled_z`'s test stayed green | ✓ |
| 6 | I3 | drop `aggregate_statuses[source] = result.status` | `features/radar/ingest.py:257` | **FAIL** `test_tick_reports_reddit_aggregate_without_root_rollup` — `assert {} == {'reddit': 'truncated'}`; log degraded to `aggregate=none` | ✓ |
| 7 | I3 | `depths[source] = None` → `= 0` (exception path) | `features/radar/ingest.py:251` | **FAIL** ×2: `test_a_failed_fetch_reports_no_catchup_depth` and `test_tick_visibly_logs_failed_fetch_depth_as_unknown`; captured log read `catchup_depth=bluesky=0` | ✓ |
| 8 | I3 | `if result.per_source_status is None:` → `if True:` (aggregate leaks into storage) | `features/radar/ingest.py:270` | **FAIL** `test_tick_reports_reddit_aggregate_without_root_rollup` — `[{'reddit': 'truncated'}] != [{'reddit:pennystocks': 'ok', 'reddit:wallstreetbets': 'missing'}]` | ✓ |
| 9 | I2 | `~status.in_(SCOREABLE_STATUSES)` → `status != 'ok'` (exact pre-fix policy) | `scripts/backfill_radar_buckets.py:153` | **FAIL** `test_stale_scores_follow_final_status_and_generation_policy` — `assert 4 == 3` | ✓ |
| 10 | I2 | both generation branches → `sa.false()` | `scripts/backfill_radar_buckets.py:155-157` | **FAIL** same test — `assert 1 == 3` | ✓ |
| 11 | I2 (rollup half) | `child.status not in SCOREABLE_STATUSES` → `child.status != 'ok'` | `features/radar/buckets.py:236` | **FAIL** `test_current_generation_truncated_preserves_its_score` — `assert None == 4.2` | ✓ |
| 12 | M3 | insert `'stocktwits': False` into the mapping | `features/radar/config.py:95-98` | **FAIL** `test_stocktwits_is_retired` — `assert 'stocktwits' not in {'bluesky': False, 'fourchan': False, 'stocktwits': False}` | ✓ |
| 13 | 7th commit | `created_utc < cutoff` → `<= cutoff` | `features/radar/retention.py:122` | **FAIL** at the **count** assertion, `tests/test_radar_retention.py:185: assert 2 == 1` | ✓ |
| 14 | 7th commit | `hours=MENTION_EVENT_RETENTION_HOURS` → `* 2` | `features/radar/retention.py:115` | **FAIL** at the **count** assertion, `tests/test_radar_retention.py:185: assert 0 == 1` | ✓ |
| 15 | 7th commit (negative control) | `created_utc < cutoff` → `bucket_start < cutoff` | `features/radar/retention.py:122` | **SURVIVES** — `6 passed`. See finding N3. | ✓ |

Mutation 15 is recorded as a survivor on purpose: a teeth table that only lists kills has
not looked for the gap.

---

## Gates

| Gate | Result |
|---|---|
| `python -m pytest tests/ -k radar -q` — **run 1** | **655 passed**, 646 deselected, 2 warnings, 93.32s. 0 failed. |
| `python -m pytest tests/ -k radar -q` — **run 2** (separate process, after all mutations reverted) | **655 passed**, 646 deselected, 2 warnings, 101.89s. 0 failed. |
| Historically-expected template failures | **Gone.** Both runs are 0-failure; the Vite manifest is present, so no failure is being written off. |
| `npx tsc --noEmit` | exit 0, no output |
| `npm test` (vitest ×2 configs) | 32 files / **403 passed**; 9 files / **84 passed** |
| `npm run build` (tsc + both Vite builds) | ✓ built. `static/gym/dist/` and `static/radar/dist/` are both gitignored, so no build output entered the tree. |
| `python -c "from features.radar import buckets"` | OK |
| `python -c "from features.radar import journal"` | OK |
| `python -c "from features.radar import ingest"` | OK |
| `python -c "from run_radar_ingest import build_fetchers"` | OK |
| `flask db current` | `35c3ae366677 (head)` |
| `flask db heads` | `35c3ae366677` — **single head, no fork** |
| `source_config_version()` | `705b043693b533db` — matches the final branch review's recorded stamp |

The four fresh-process imports were each run in their own interpreter, which is what makes
them a real test of the deliberate `buckets`/`journal` circular import rather than a
re-check of an already-warm `sys.modules`.

### Shared-database safety

| Point | `radar_mention_events` |
|---|---|
| Baseline, before any work | **1432** |
| After all M2/M3/I1/I2/I3 mutations and reverts | **1432** |
| After deliberately reproducing the leaderboard leak (see N1) | 1434 — the two rows I created (`ZZA`/`bluesky`/`zz-h`, `zz-l`) deleted by exact identity |
| After both full suite runs and every gate | **1432** |

`radar_bucket_sources` held 29460 rows throughout, with **0** `ZZ%`-prefixed rows remaining
at exit. No `downgrade()` was ever invoked — the M1 verification used the fake-`op` harness
and direct reading only. `prune_mention_events` was called only through its own test, whose
`now` is fixed at 2026-04-20; the real table's rows are from 2026-08-22/23 and cannot enter
that window. Every mutation was chosen so that it widened or held the retention cutoff,
never narrowed it toward the present. Protected files
(`scripts/discover_telegram_sources.py`, `telegram_candidates.json`,
`reddit_candidates.json`) were neither read nor written.

### Worktree state on exit

```
HEAD                d9c7f76e655571b78ad7256c3bb8fabe706cde11
git diff --exit-code   clean
git status --short     (empty — no source modifications)
```

Nothing was committed.

---

## New findings

### N1 — Minor — `test_radar_leaderboard.py` writes journal identities no fixture owns

**Location:** `personal_apps/tests/test_radar_leaderboard.py:548-552` (the
`buckets.roll_up([...])` call in `test_a_promoted_mention_counts_towards_the_author_floor`),
with the incomplete owned-list at `personal_apps/tests/test_radar_journal.py:20-37`.

**Failure mode.** That test imports `clean_buckets`/`clean_events` from
`test_radar_journal.py` and writes mention events under `external_id` `zz-h`/`zz-l`,
ticker `ZZA` — identities that are **not** in `_OWNED_EVENT_IDENTITIES`. Its own `board`
fixture only sweeps the `LB%` namespace, so nothing cleans them. Before `3d2dced` the broad
`ticker.like('ZZ%')` teardown swept them incidentally; tightening that predicate (correctly,
per I1) removed the accident that was hiding the gap.

**Reproduced, not inferred.** With the tree at `d9c7f76` and the table at 1432:

```
$ python -m pytest tests/test_radar_leaderboard.py -q     → 29 passed
total = 1434
LEAKED: ZZA bluesky zz-h 2026-04-15 14:03:00
LEAKED: ZZA bluesky zz-l 2026-04-15 14:07:00
```

I removed exactly those two rows by exact identity afterwards; the table is back to 1432.

**Impact.** Bounded — two rows, and they are swept whenever the retention suite runs later
in the same session (their April-2026 timestamps fall before that test's cutoff). Test-only;
no production path is affected. But it is the direct cause of the failure `d9c7f76` had to
work around, and it means a run of the leaderboard suite alone leaves residue in a real
shared database.

**Fix.** Two lines in `personal_apps/tests/test_radar_journal.py`, inside
`_OWNED_EVENT_IDENTITIES`:

```python
    ('bluesky', 'zz-h', 'ZZA'),
    ('bluesky', 'zz-l', 'ZZA'),
```

Optionally also tighten `test_radar_leaderboard.py`'s own `board` fixture (`:36-52`) from
`LIKE 'LB%'` to exact identities, the same way the six I1 files were tightened.

---

### N2 — Minor — the retention boundary's identity assertion is scoped by ticker, not by owned identity

**Location:** `personal_apps/tests/test_radar_retention.py:187-189`.

```python
remaining = {e.external_id for e in
             RadarMentionEvent.query.filter_by(ticker='ZZA').all()}
assert remaining == {'zz-new', 'zz-boundary'}
```

**Failure mode.** `ZZA` is not this test's private namespace — every entry in
`test_radar_journal.py`'s `_OWNED_EVENT_IDENTITIES` uses it, and so does the N1 leak. Any
foreign `ZZA` row whose `created_utc` is at or after the cutoff would fail this assertion on
data the test does not own. Today's foreign `ZZA` rows all sit at 2026-04-15, safely before
the 2026-04-18 cutoff, so they are deleted by the prune and never appear — which is exactly
the kind of incidental safety I1 ruled unacceptable. This is the same defect class the
adjacent count assertion was just fixed for, one line further down.

**Fix.**

```python
remaining = {e.external_id for e in RadarMentionEvent.query.filter(
    RadarMentionEvent.ticker == 'ZZA',
    RadarMentionEvent.external_id.in_(('zz-new', 'zz-old', 'zz-boundary'))).all()}
```

---

### N3 — Minor — the retention test does not pin `created_utc` against `bucket_start`

**Location:** `personal_apps/tests/test_radar_retention.py:163-189` (pre-existing; not
introduced by `d9c7f76`).

**Failure mode.** The test's headline claim is its own name — pruned by *when the post was
written*. Mutating `retention.py:122` from `created_utc < cutoff` to `bucket_start < cutoff`
leaves the whole file green (**verified: 6 passed**, teeth-table mutation 15). The fixture
builds `bucket_start` by hour-flooring `created_utc`, and `now` is on the hour, so
`bucket_start ≤ created_utc` never straddles the cutoff and the two columns are
indistinguishable. Since the count assertion's expectation is computed with the *same*
column the test also uses for the fixture, it cannot separate them either.

**Fix.** Add a fourth fixture row whose two columns straddle the cutoff, and assert it
survives:

```python
db.session.add(RadarMentionEvent(
    source='bluesky', external_id='zz-late-bucket', ticker='ZZA', channel='c',
    created_utc=cutoff + dt.timedelta(minutes=30),   # after the cutoff: must survive
    bucket_start=cutoff - dt.timedelta(hours=1),     # before it: a bucket_start prune would delete
    author='u1', simhash=1, confidence='high', sentiment=None, engagement=0.0))
```

with `'zz-late-bucket'` added to `clean_events`'s `idents` tuple (`:118`) and to the expected
`remaining` set.

---

### N4 — Minor — the third narrowing in the source-width downgrade is still unguarded

**Location:** `personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py:99-105`.

**Failure mode.** M1's fix correctly preflights the two tables the finding enumerated. But
`downgrade()` performs a **third** narrowing — `radar_posts.source` 48 → 16 — after both
auto-committed `ALTER`s and after a data-modifying `UPDATE`. It has no preflight of its own.
If any `radar_posts.source` value exceeds 16 characters once the `reddit:` prefix has been
collapsed, that final `ALTER` raises with two ALTERs and one UPDATE already committed: the
exact half-applied state M1 was raised about, one table further along.

**Practical risk is low** — after normalisation the longest historical value is `stocktwits`
(10), and the longest configured source root is `fourchan` (8). This is a completeness gap
in a path the migration's own docstring says is not a production rollback mechanism, not a
live hazard.

**Fix.** Add the post-normalisation width to the same preflight loop, measured as it will
exist after the `UPDATE`:

```python
limits = (
    ('radar_poll_state', 24, 'source'),
    ('radar_bucket_sources', 24, 'source'),
    ('radar_posts', 16, "IF(source LIKE 'reddit:%', 'reddit', source)"),
)
```

and extend `test_source_width_downgrade_aborts_before_ddl_for_either_violation`'s
parametrisation to cover `radar_posts` as a third violating table.

---

## Summary table

| Finding | Ruling | Verdict |
|---|---|---|
| I1 — shared-DB cleanup deletes unowned data | Important, FIX BEFORE MERGE | **ADDRESSED** |
| I2 — backfill erases legitimate `truncated` scores | Important, FIX BEFORE MERGE | **ADDRESSED** |
| I3 — aggregate health / catch-up depth have no consumer | Important, FIX BEFORE MERGE | **ADDRESSED** |
| M1 — width guard after irreversible DDL | Minor, FIX BEFORE MERGE | **ADDRESSED** |
| M2 — four strict scored-read boundaries untested | Minor, FIX BEFORE MERGE | **ADDRESSED** |
| M3 — StockTwits policy-map key unpinned | Minor, FIX BEFORE MERGE | **ADDRESSED** |
| 7th commit, fix 1 — stray `aggregate_status` assertion removed | — | **Correct**; coverage independently verified by mutation |
| 7th commit, fix 2 — count assertion measured, not literal | — | **Has teeth**; not tautological |
| N1 — leaderboard writes unowned journal identities | new | Minor |
| N2 — retention identity assertion scoped by ticker | new | Minor |
| N3 — `created_utc` vs `bucket_start` unpinned | new | Minor |
| N4 — `radar_posts` narrowing unguarded in downgrade | new | Minor |

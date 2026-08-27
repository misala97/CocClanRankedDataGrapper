# Final whole-branch architecture review — radar pipeline audit

Review date: 2026-08-27  
Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`  
Branch: `codex/radar-pipeline-audit`  
Original feature base: `b9c8ef8`  
Code package head: `3782dd5`  
Reviewed HEAD: `21384efc7bd3fa1332cb239cd5fe29cf0a8cadee`

## Verdict and readiness

**VERDICT: NEEDS FIXES.** Critical: 0. Important: 3. Minor: 3. Retention teeth: 1/1.

**Merge readiness:** not ready. The strict/history source split, generation boundaries, forward migrations, retention boundary, scheduling, API/UI contracts, and Tasks 18–19 fixes are coherent. Merge is blocked by three integration defects: shared-real-DB tests still delete unowned namespaces; Task 6's stale-score backfill contradicts Task 8's current `truncated` scoreability; and two branch-touched operational status values have no production consumer. Three deferred test/migration weaknesses also have a FIX BEFORE MERGE ruling.

**Plan-compliance verdict: NEEDS FIXES.** The implementation is substantially faithful to all 19 task briefs, but the Task 6/Task 8 contradiction and the unconsumed Task 9/Task 10 status values violate the integrated plan's semantics and this final review's explicit consumer requirement.

**Quality verdict: NEEDS FIXES.** The production source-expansion and generation design is sound, but destructive shared-DB test ownership, an unsafe downgrade preflight, and missing mutation teeth at the architecture's most important read boundary are not acceptable at the final merge gate.

The code after package head `3782dd5` is unchanged: `git diff --quiet 3782dd5..HEAD -- personal_apps` succeeded. HEAD `21384ef` is a documentation-only successor. The handoff's current top checkpoint names `3782dd5`; Git evidence governs.

## Strengths

- The two source-expansion helpers are unusually well documented and every current production caller chooses the right one. No later task reopened the historical-data-loss or cross-generation scoring defect.
- `source_config_version()` covers active roots, subreddit membership, `ROLLUP_GENERATION`, and `SOURCE_NAME_GENERATION`. Scoring writes and profiles require the exact current generation; startup fails closed before any scheduler job can run when journal recovery is inconsistent.
- Reddit's durable source identity, per-subreddit status, partial-success behavior, scheduler identity, and root-level presentation are cleanly separated. An explicitly empty per-source map writes no fabricated root zero.
- All new user-facing values with an intended surface have end-to-end consumers: `unpriced_tokens`, `disagreements`, `warming-up`, and `one_venue` reach API types and visible React components; the journal-prune count reaches service logs.
- The two forward migrations form one linear Alembic head and the final model widths match the live MySQL schema. Current indexed widths remain within MySQL/MariaDB limits.
- The Task 19 boundary fixture owns exact identities and a structural April-2026 window. The required mutant failed for the intended reason while the 1,432-row shared-table canary remained unchanged.
- Task 18's discovery guard executes before entering the app context or opening the output file, and `--anyway` is now asserted against the exact successful return contract.

## Critical findings

None.

The highest-risk question in this review was whether a later read path used strict expansion for history or historical expansion for scores. The caller audit below found no wrong production choice, so there is no Critical history-hiding or generation-mixing finding.

## Important findings

### I1 — Shared-DB test cleanup can delete data it does not own

**Locations:**

- `personal_apps/tests/test_radar_buckets.py:25-37`
- `personal_apps/tests/test_radar_bucket_sources.py:26-34`
- `personal_apps/tests/test_radar_journal.py:22-26` and `:53-58`
- `personal_apps/tests/test_radar_retention.py:42`
- `personal_apps/tests/test_radar_universe.py:22-26`
- `personal_apps/tests/test_radar_daemon.py:559-582` and `:602-624`

**Failure mode:** these tests execute real `DELETE ... WHERE ticker LIKE 'ZZ%'` or the equivalent symbol predicate against the shared development MySQL database, before and/or after the test. They can erase another suite's rows, a concurrently running test's rows, or Michi's manually namespaced evidence. There is no test database and no transaction rollback.

**Rationale:** ledger N3 recorded five pre-existing files and noted that this exact hazard had already caused three review rounds. Current code has six affected files: the five deferred sites plus broad cleanup introduced on this branch in `test_radar_daemon.py` by `7791963`. The current DB happens to contain zero `ZZ%` rows; that is incidental, not structural safety. Destructive correctness cannot depend on today's population.

**Fix:** replace every broad prefix deletion with an explicit set of identities each fixture creates. The daemon tests should delete only `ZZDAEMON` and `ZZQUIET`; shared fixtures should publish exact owned ticker/external-ID sets. Add a sentinel mutation regression proving an unowned `ZZ...` row survives setup and teardown. This is **FIX BEFORE MERGE** and elevates deferred N3 from Minor to Important because the database is shared and real.

### I2 — The one-shot backfill erases scores that Task 8 made legitimate

**Locations:**

- `personal_apps/scripts/backfill_radar_buckets.py:136-159`
- `personal_apps/tests/test_radar_backfill.py:203-243`
- `personal_apps/features/radar/scoring.py:42` and `:157-170`
- Related stale explanation: `personal_apps/features/radar/buckets.py:222-237`

**Failure mode:** Task 8 defines both `ok` and `truncated` as scoreable and writes scores to current-generation truncated rows. Task 6's later-deployed backfill still treats every `status != 'ok'` row carrying any score field as stale. A rerun after the new scorer has run—or an initial deploy where scoring's two-minute startup job beats the dry-run/apply sequence—clears valid current-generation Reddit scores. The next scoring pass can restore them, but the board under-reports Reddit in the meantime, and a scorer failure extends the outage. The script is therefore not idempotent under the final branch semantics.

**Rationale:** this is a cross-task contradiction, not an accepted Task 6 tradeoff. The existing test deliberately asserts that a `truncated` score is always cleared, but its fixture uses `source_config_version='old-gen-4'`; it never protects a current-generation score. Comments at `backfill_radar_buckets.py:141-142` and `buckets.py:225-226` also retain the pre-Task-8 claim that truncated rows are refused by scoring.

**Fix:** define stale score state against the final policy: clear a score when its status is not in `{'ok', 'truncated'}` or its `source_config_version` is NULL/incompatible with `source_config_version()`. Preserve current-generation truncated scores. Add dry-run/apply/rerun coverage for both current-generation truncated and old-generation truncated rows, and update the stale comments. Keep the daemon stopped through the production dry-run/apply as an additional deployment safeguard.

### I3 — Reddit aggregate health and failed-fetch depth stop at test-only dictionaries

**Locations:**

- `personal_apps/features/radar/sources/reddit.py:243-260`
- `personal_apps/features/radar/sources/__init__.py:42-62`
- `personal_apps/features/radar/ingest.py:249-269` and `:302-304`
- `personal_apps/run_radar_ingest.py:190-220`

**Failure mode:** Reddit computes a root aggregate `FetchResult.status`, and the source contract says that aggregate is what the cycle reports. Once `per_source_status` is present, `run_cycle` discards `result.status` and returns only concrete subreddit statuses. Separately, Task 10 writes `catchup_depth[source] = None` for a failed fetch and returns it in the summary, but the only production caller logs neither catch-up depth nor a Reddit aggregate and ignores `tick()`'s return. Both values are exercised only by direct tests; neither informs an operator, API, schedule, or storage decision.

**Rationale:** concrete statuses must remain the only map passed to `buckets.roll_up`, or a fabricated root child reappears. That does not require throwing away the aggregate operational verdict. The ledger itself says the aggregate remains useful for cycle reporting, and the Task 10 plan acknowledges that nothing reads catch-up depth. This repeats Task 14's defect class: a branch-touched value is computed and serialized without an actual production consumer.

**Fix:** separate storage statuses from report statuses. Keep concrete `per_source_status` for rollup, add a root-level aggregate report map (or equivalent explicit field), and log it together with catch-up depth in `tick()`. Make the fallback summary schema consistent. Add a runtime/log-capture regression proving a partial Reddit cycle reports root `truncated`/`missing` without passing `reddit` to rollup, and that a failed fetch visibly reports unknown—not zero—depth.

## Minor findings

### M1 — The width guard runs after irreversible downgrade DDL

**Location:** `personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py:67-82`.

**Failure mode:** downgrade narrows `radar_poll_state.source` before checking `radar_bucket_sources` for names over 24 characters. MariaDB/MySQL auto-commits the first `ALTER`; a later guard failure leaves a half-applied schema. The first ALTER can itself fail if poll-state source names exceed 24 because that table is not preflighted at all.

**Fix:** run read-only length checks for both tables before any DDL, or make the downgrade fail closed before its first ALTER. Preserve the operational rule that neither this migration nor the destructive fractional-baseline downgrade is a production rollback mechanism. Deferred N1 is **FIX BEFORE MERGE**.

### M2 — Four strict scored-read boundaries still have no direct mutation tooth

**Locations:**

- `personal_apps/features/radar/board.py:173-198`
- `personal_apps/features/radar/detail_panel.py:88-109`
- `personal_apps/features/radar/scoring.py:177-198`
- `personal_apps/features/radar/scoring.py:253-270`
- The sole direct integrated closure is `personal_apps/tests/test_radar_board.py:485-502` for leaderboard ranking.

**Failure mode:** `board._triplets`, `detail_panel.window_figures`, `scoring.pooled_z`, and `scoring.window_z` currently call strict expansion correctly, but changing any one to `expand_sources_for_history` is not directly killed by a pre-split-root score sentinel. A future helper consolidation can silently mix old aggregate-Reddit scores with current per-subreddit scores while the suite stays green.

**Fix:** for each reader, add an extreme pre-split root row plus a current concrete row and assert that only the concrete scored components contribute. Confirm each local strict-to-history mutant fails. Deferred N2 is **FIX BEFORE MERGE**.

### M3 — StockTwits retirement does not pin the last policy-map key

**Location:** `personal_apps/tests/test_radar_config.py:327-355`.

**Failure mode:** `test_stocktwits_is_retired` directly checks four retired config surfaces but not `COIN_SYMBOLS_MEAN_STOCKS`. The following `not any(values())` assertion survives a false-valued `stocktwits` key, so the retirement test can pass with stale source configuration still present and hashed into the generation stamp.

**Fix:** assert `'stocktwits' not in config.COIN_SYMBOLS_MEAN_STOCKS` and kill the false-valued-key mutant. The current production mapping is clean; this is a regression-strength defect. Deferred Task 7 Minor is **FIX BEFORE MERGE**.

## Cross-task coherence matrix

| Interaction | Final branch behavior | Verdict |
|---|---|---|
| Tasks 2, 3b, 3c: journal rebuild, revocable promotion, rollup generation | Journal records the full window; promotion writes the latest complete verdict; generation 2 prevents corrected counts sharing a baseline with understated counts. | Coherent |
| Tasks 3c, 7, 9: generation transitions | StockTwits retirement changes the source-list hash; source-name generation 2 expresses aggregate-to-concrete Reddit even when roots/sub membership are unchanged; exact-version profile/write filters prevent cross-generation scoring. | Coherent |
| Task 9 source expansions with Tasks 10–17 readers | Every scored reader uses strict expansion; every raw count/status/timestamp reader uses historical expansion. Root presentation remains pooled. | Coherent; M2 is test debt |
| Task 9 not-due and partial-success semantics | `None`, `{}`, and populated status maps remain distinct; only concrete attempted sources reach rollup; earlier successful subreddits survive a later failure. | Storage coherent; I3 blocks operational reporting |
| Tasks 6 and 8: stale cleanup versus truncated scoreability | Backfill still equates all non-`ok` rows with stale scores after Task 8 made current-generation `truncated` scores valid. | **Contradiction — I2** |
| Task 8 baseline/profile versus score writes | Profiles and baseline observations remain `ok`-only; score writes accept `ok` and `truncated`; `missing` remains unscored. | Coherent |
| Tasks 10–13 absence semantics | Unknown rate/depth uses NULL/None; uncovered chart slots use `None`; exclusion accounting reaches the visible UI. | Coherent except dead catch-up consumer in I3 |
| Task 13 and deferred N4 | `one_venue` is computed in leaderboard/board, serialized in the board payload, and rendered by `Excluded.tsx`. | Deferred defect resolved |
| Tasks 14–15 consumer chain | Model/lexicon disagreement is computed from real rows, serialized, typed, and rendered only when non-zero. | Coherent |
| Task 16 model/schema/UI chain | Fractional `baseline_days` is stored as FLOAT, rounded in prose, and split into `provisional`/`warming-up` with client support. | Coherent forward path |
| Tasks 18–19 operational batch | Discovery yields to the daemon; journal retention is scheduled and strict at the cutoff; commit `200bde3` fixes are valid. | Coherent; teeth 1/1 |
| Test ownership across tasks | Five deferred broad fixtures plus one branch-added daemon test still delete shared namespaces. | **Contradiction — I1** |

## Source expansion and generation checks

### Scored reads — strict, current stored names only

| Reader | Source policy | Evidence |
|---|---|---|
| `leaderboard.build_rows` | `expand_sources` | `leaderboard.py:146-166`; pre-split ranking regression exists |
| `board._triplets` | `expand_sources` | `board.py:183-198` |
| `detail_panel.window_figures` | `expand_sources` | `detail_panel.py:88-109` |
| `scoring.pooled_z` | `expand_sources` | `scoring.py:177-198` |
| `scoring.window_z` | `expand_sources` | `scoring.py:253-270` |
| `run_radar_ingest.score_all` | `expand_sources(SOURCES)` | `run_radar_ingest.py:225-244`; daemon scores concrete subreddit names |

### Historical raw reads — current concrete names plus pre-split root

| Reader group | Source policy | Data read |
|---|---|---|
| `board._covered_hours`, `_hourly_counts`, `_tones` | `expand_sources_for_history` | status, mention counts, post tone |
| `detail.daily_counts`, `intraday_counts`, `first_watched_day`, `watched_slots` | `expand_sources_for_history` | raw chart counts and observation coverage |
| `detail_panel.breakdown_for`, `_posts` | `expand_sources_for_history` | retained posts, voices, tone |
| `journal.distinct_voices` | `expand_sources_for_history` | raw retained event identities |

Concrete selections such as `reddit:wallstreetbets` stay concrete in both helpers; only a root `reddit` selection receives the undifferentiated pre-split root. This avoids falsely attributing aggregate history to one subreddit.

### Generation boundary proof

- Current stamp: `705b043693b533db`.
- Current inputs include `SOURCES=('bluesky', 'fourchan', 'reddit')`, all eight `REDDIT_SUBS`, `ROLLUP_GENERATION=2`, and `SOURCE_NAME_GENERATION=2` (`config.py:622-686`).
- Task 7 moved the stamp from `fc1a0ee4cab51d65` to `8106787f1fa72179` by removing StockTwits; Task 9's source-name generation moved it again to the current stamp. No manual magic hash is used.
- `_rows_by_ticker` requires exact `source_config_version`; `profile.build_profile` requires exact version and `status == 'ok'`; `baselines.usable` repeats exact-version and `ok` filtering.
- Startup bootstraps retained evidence before scheduler construction and clears incompatible scored fields across the 48-hour overlap. `score_source` repeats source-scoped invalidation across its 30-day lookback.
- Production scored surfaces read at most current 24-hour windows, inside startup's invalidation overlap; old root Reddit scores remain physically retained but strict source naming makes them unreachable to scored surfaces. Raw history remains readable.

**Conclusion:** no current production path scores or pools scores across incompatible generations.

## Migration checks

- Alembic reports exactly one head: `35c3ae366677`.
- The live local DB reports current `35c3ae366677 (head)` using MySQL's non-transactional DDL implementation.
- Linear chain: `1d26ac48e744 -> 08316d3e4d77 -> 35c3ae366677`.
- Live schema inspection: `radar_posts.source VARCHAR(48)`, `radar_bucket_sources.source VARCHAR(48)`, `radar_poll_state.source VARCHAR(48)`, and `radar_bucket_sources.baseline_days FLOAT`.
- Longest configured source is `reddit:smallstreetbets` (22 characters), inside 48 and the old 24-width downgrade bound. The widened indexed combinations remain below both modern 3072-byte and legacy 767-byte InnoDB index limits: the largest is `radar_posts(source 48 + external_id 128)` at at most 704 utf8mb4 bytes before small index overhead.
- `08316d3e4d77` widens before a concrete writer can deploy and documents the partitioned-table blocking ALTER. `35c3ae366677` then converts the same table's `baseline_days` to FLOAT.
- Forward deployment is compatible with MariaDB/MySQL constraints. DDL is non-transactional and can block ingest briefly, so the daemon must be stopped and migrations observed to completion.
- Downgrade is not a production rollback. M1 must still move/fail the preflight before irreversible DDL; the Task 16 downgrade knowingly truncates fractional days. Never invoke either downgrade on real data.

## Task 18–19 fix verification and retention tooth

Commit `200bde3` changes three things, all inspected against current code:

1. `retention.py:134-137` exits after a short final batch, avoiding an unnecessary empty query and pause. The fixed cutoff is stable for the run; rows concurrently arriving after a short batch can safely wait for the next nightly pass.
2. `test_radar_discovery.py:81-95` now requires `--anyway` to return only `None`/`0`, rather than accepting every value except `1`. The exact test passed; `_daemon_is_running()` returned `False` on this Windows host.
3. `test_radar_retention.py:126-152` owns an exact-cutoff row and asserts it survives.

The top handoff calls the fix round “test-only,” but Git evidence shows the three-line production retention early-exit change. It is correct; the discrepancy is documentation imprecision, not a code defect.

### Mandated boundary tooth — 1/1

- Precondition: `radar_mention_events=1432`; bounds `2026-08-22 20:03:00..2026-08-23 20:00:00`; no `ZZ%` event rows.
- Original raw SHA-256 of `features/radar/retention.py`: `0F3680BEBD299DDD6C49857AB47258E198838582634BAB9BA64C2EB60EDD9D69`; Git blob hash `1af22a74275e5ca977caacd061690c08443a179b`.
- Mutant: only `RadarMentionEvent.created_utc < cutoff` changed to `<= cutoff`.
- Exact command: `python -m pytest tests/test_radar_retention.py::test_the_journal_is_pruned_by_when_the_post_was_written -q`.
- Mutant result: expected failure, `tests/test_radar_retention.py:149`, `assert 2 == 1`.
- Restored result: `1 passed in 0.21s`.
- Restoration: raw SHA-256 returned exactly to `0F3680...D9D69`; Git blob hash returned to `1af22a...`; `git diff --exit-code` succeeded.
- DB postcondition: `radar_mention_events=1432`; owned April IDs remaining `0`.

No retention command used a present-day window.

## Deferred Minor triage

For status-line accounting, `deferred_fixed` is the count ruled **FIX BEFORE MERGE**, and `deferred_accepted` is the count ruled **ACCEPT**.

1. **ACCEPT — Task 4+5 `_extract_for` prose:** `ingest.py:69-72` says four judgements but lists three; the fourth argument is visible at `:84`, behavior is tested, and this prose omission does not justify blocking merge.
2. **ACCEPT — Task 6 COUNT/SUM Decimal comment:** `backfill_radar_buckets.py:93-95` overstates this driver's COUNT behavior, but all values are explicitly converted at the SQL boundary and behavior is unaffected; retain as house-style wording debt.
3. **FIX BEFORE MERGE — Task 7 StockTwits key absence:** add the direct `COIN_SYMBOLS_MEAN_STOCKS` absence assertion described in M3.
4. **FIX BEFORE MERGE — Task 9 N1 downgrade guard:** preflight every narrowed table before any DDL, as described in M1.
5. **FIX BEFORE MERGE — Task 9 N2 scored-read strictness teeth:** add four direct root-score exclusion regressions, as described in M2.
6. **FIX BEFORE MERGE — Task 9 N3 broad `LIKE 'ZZ%'` teardown:** replace all five deferred sites and the sixth branch-added daemon site with exact ownership, as described in I1.
7. **ACCEPT — Task 9 N4 dead `one_venue`:** later Task 13 resolved it. Current chain is `board.py:318` -> `routes/api.py:125` -> `static/radar/src/list/Excluded.tsx:12`; it is no longer dead.
8. **ACCEPT — Tasks 10–13 `spend.py` local `total` shadow:** `spend.py:105-115` is readability-only; closure resolution and returned `unpriced_tokens` behavior are correct, and the value is visibly consumed.

**Tally:** FIX BEFORE MERGE 4; ACCEPT 4.

## Consumer audit

Branch-created or branch-completed value chains:

| Value | Producer | Actual consumer | Result |
|---|---|---|---|
| `RadarMentionEvent.promoted` | journal promotion persistence | `journal.distinct_voices` and rollup reconstruction | Consumed |
| `per_source_status` | Reddit fetch | `ingest.run_cycle` storage-status selection | Consumed |
| Reddit `rates` | Reddit fetch | scheduler `record_poll` | Consumed |
| `one_venue` | leaderboard/board | board JSON and `Excluded.tsx` | Consumed |
| `unpriced_tokens` | spend summary | board JSON, TypeScript type, `Spend.tsx` | Consumed |
| `disagreements` | detail breakdown | detail JSON, TypeScript type, `Breakdown.tsx` | Consumed |
| `warming-up` | leaderboard marks | TypeScript union, list wording/row rendering | Consumed |
| fractional `baseline_days` | scoring | leaderboard, API, phrasing, client | Consumed |
| pruned event count | retention | daemon log | Consumed |
| Reddit aggregate status | Reddit `_roll_up` | none after per-source map exists | **I3** |
| failed-source `catchup_depth=None` | ingest summary | tests only; scheduled caller ignores/log omits | **I3** |

Two known dead values are not branch-introduced: `RadarBucket.sources_ok` and the board-row `tone` payload existed at `b9c8ef8`. This branch adjusts the former's unit to rooted venues and deliberately leaves board tone rendering to the separately scoped visual-design cycle. They are accepted existing scope, not a claim that new dead output is acceptable.

## Error handling, scheduling, retention, and source-status checks

- `ingest.run_cycle` isolates broad exceptions per source and records failure as `missing` without advancing cursors or writing zero buckets. `tick` contains cycle-level failures so scheduling continues.
- `score_all` isolates one source's scoring failure from the rest. Startup generation preparation remains deliberately uncaught and occurs before fetcher/scheduler construction, so migration/bootstrap inconsistency fails closed.
- Reddit has a fixed 120-second job independent of market session cadence; root poll state and per-subreddit durable source names remain intentionally separate. Retired subreddit poll state is removed.
- `None` (no per-source contract), `{}` (nothing observed), populated maps, `missing`, and `truncated` remain behaviorally distinct at storage. A partial fetch keeps successful concrete children and writes no missing child.
- Scoring writes `ok` and `truncated`; profiles and baselines use only `ok`; missing remains NULL. I2 is the only later policy contradiction found.
- Pruning runs nightly at 04:30 UTC, deletes posts, then quotes, then mention events in bounded batches, and commits each batch. Journal cutoff is by post `created_utc`, strict at the boundary, and does not use insertion time.
- The discovery script refuses while `radar_ingest` is active unless the explicit override is supplied. It does not coordinate with a differently named/custom unit; the deployed unit named in this repository is `radar_ingest`, so current deployment is coherent.
- Backend/client contracts match for sources, `unpriced_tokens`, `disagreements`, `warming-up`, fractional baselines, and exclusions. Concrete subreddit names remain an internal breakdown while user-facing venue labels are rooted.

## Ordered deploy checklist

Do not deploy until I1–I3 and M1–M3 are fixed and the affected scopes are independently re-reviewed.

1. **Prepare recovery evidence.** Take the normal production backup/snapshot; record current Alembic revision, row counts, current radar daemon PID/unit state, and current `source_config_version`. Do not treat Alembic downgrade as the rollback plan.
2. **Stop competing writers and discovery.** Stop the old `radar_ingest` daemon and verify it is inactive. Ensure `discover_reddit_sources.py` is not running and do not use `--anyway`. Disable automatic service restart for the maintenance window.
3. **Apply both forward migrations.** Upgrade through `08316d3e4d77` and `35c3ae366677` before any new daemon starts. Expect blocking ALTERs on the partitioned `radar_bucket_sources` table. Verify exactly one head, `35c3ae366677`, and the three `source` columns at 48 plus `baseline_days FLOAT`.
4. **Install the new application/static build while the daemon remains stopped.** Do not allow an old root writer and a new concrete writer to overlap; they describe incompatible populations and can double-count history.
5. **Run Task 6 backfill before the first new scoring pass.** First run `python -m scripts.backfill_radar_buckets` as a dry run, inspect the production counts, then run with `--apply`, then dry-run once more to prove idempotence. Local evidence was 210 examined / 165 understated and the historical target included 399 stale-score rows; production numbers may differ and must be reviewed, not hard-coded. Keeping the daemon stopped also prevents I2's current-generation race, even after the code fix.
6. **Start exactly one new daemon.** Confirm no old PID remains. Its startup must run `_prepare_rollup_generation` before scheduler creation.
7. **Verify journal bootstrap and invalidation in logs.** Record `recovered` and `invalidated`. If recovery is zero while retained legacy buckets carry high-confidence evidence, startup must abort; do not bypass it. This prevents the first post-deploy cycle from rebuilding a partial bucket and erasing its pre-deploy counts.
8. **Verify source semantics.** Confirm new posts/buckets use `reddit:<sub>`, poll state remains rooted at `reddit`, not-due cycles write no root child, partial cycles preserve successful subreddits, and no old/new daemon overlap produced duplicate root/concrete observations.
9. **Expect and communicate baseline warm-up.** The final stamp incorporates the StockTwits retirement and source-name generation change. Old-stamp rows must remain outside current baselines; `warming-up` is expected until enough new data accumulates.
10. **Verify the visible contracts.** Check the board/detail endpoints and built client for exclusions, unknown-priced tokens, disagreement count, rooted venue labels, and warming-up wording. Confirm the operational cycle log now consumes the aggregate status and catch-up-depth fix from I3.
11. **Observe the first scheduled retention run.** Verify the 04:30 job logs bounded post/quote/event pruning and that only rows strictly older than the 48-hour event cutoff are removed. Never validate this on production with an artificial present-day prune call.
12. **Rollback forward, never down.** If deployment must be reversed, stop the daemon and deploy compatible application code or a new forward migration. Do not run either branch migration's downgrade against real data: Task 9 can half-apply/narrow source identity and Task 16 truncates the fractional baseline values it was created to preserve.

## Commands and evidence inspected

No subagents were dispatched. The prebuilt package was read in full and was not rebuilt. No full backend, radar, frontend, TypeScript, Vitest, or Vite gate was rerun; their evidence remains the ledger's 645-pass backend gate plus clean frontend gates.

Read/inspection evidence included:

- Full reads of `HANDOFF.md`, `progress.md`, `final-branch-review-package.md`, the binding plan, and the design spec.
- `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse HEAD`, `git status --short --branch`, recent log, and `git diff --name-status 3782dd5..HEAD`.
- `rg` caller matrices for `expand_sources`, `expand_sources_for_history`, generation/version filters, scoreable statuses, branch value producers/consumers, StockTwits, and every `ZZ%` deletion.
- Current surrounding reads of config, ingest, buckets, journal, scoring, profile, leaderboard, board, detail, detail panel, routes, retention, daemon scheduling, discovery, models, tests, and both migrations.
- `python -m flask db heads`, `python -m flask db current`, and `python -m flask db history -r 1d26ac48e744:35c3ae366677`.
- SQLAlchemy live-schema inspection for dialect/version and the changed column types. Local evidence: MySQL 8.0.46, head `35c3ae366677`.
- Read-only DB counts and date bounds before mutation; source-length maxima; score/status grouping; `ZZ%` ownership counts.
- `git show`/`git blame` for `200bde3`, broad daemon cleanup provenance, and pre-existing dead fields.
- Narrow checks only: the exact mutated/restored retention boundary regression, the exact `--anyway` discovery regression, and local `_daemon_is_running()` behavior.

Artifact SHA-256 values held constant through review:

- `HANDOFF.md`: `54418A55179AC800DE9C6E38677703CC28E22506C95D10C9576682358C495C12`
- `progress.md`: `B041E8C3DF460F55ECD470A3AF579744C67E8EE517251E38DF8BBAA92CA245C2`
- `final-branch-review-package.md`: `D74FEED320E66D1069ADDDE08BDFF428EB428210909C6B2836D3F3539CB824F1`
- plan: `A99A51F2226CA4672A4BDF107B5CCE0389C178C3489443686FDD4923FD56E9E8`
- spec: `8BE19C57EFFC7E824FFA5FEF0294B161DDC0342614D8FB8FDDEB18A400F7943E`

## Worktree, hash, protected-file, and DB restoration proof

- Before the report write, the worktree was clean on `codex/radar-pipeline-audit` at `21384efc7bd3fa1332cb239cd5fe29cf0a8cadee`.
- The only persistent review write is this report.
- Retention implementation raw SHA-256 before mutation and after restoration: `0F3680BEBD299DDD6C49857AB47258E198838582634BAB9BA64C2EB60EDD9D69`; Git blob hash `1af22a74275e5ca977caacd061690c08443a179b`; no retention/test diff.
- `radar_mention_events`: 1,432 before and 1,432 after. Real bounds remained August 22–23, 2026. Test-owned April rows remaining: 0.
- Protected tracked files were not modified. Review-time hashes: `personal_apps/scripts/discover_telegram_sources.py` `4B65EB90241FDA132464B8040AAFBD2B43BD7BBF227268CDC7BE2110D3C18E7A`; `personal_apps/telegram_candidates.json` `4F53CDA18C2BAA0C0354BB5F9A3ECBE5ED12AB4D8E11BA873C2F11161202B945`.
- The ignored `personal_apps/reddit_candidates.json` is not materialized in this linked worktree; the main checkout copy was read only and hashed `473DF0BBF4D088C6C4448299739FF2092F8EE73B9CE8D29EFD869412E0881FE9`. No review command wrote it.
- No migration, branch, HEAD, index, production file, plan, spec, ledger, handoff, package, or protected artifact was changed.

## Final disposition

Resolve I1–I3 and M1–M3, rerun only their focused mutation/contract tests plus the normal post-fix covering gates, and conduct an independent re-review of the fix range. The branch's core architecture is worth preserving; the required fixes are narrow and do not call for redesigning source expansion, generation stamping, or retention.

# Codex rulings on Claude's return

## Second return: binding ruling, 2026-09-09

This section supersedes the earlier open R1/R2 instructions below. Verified implementation HEAD: b4801167ca04635255fcff4b525fa1351d8903b7 on codex/radar-foundations at C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations. Git status reported clean, with ignore/cache access warnings. Read Claude's return, R2/R1 ledger evidence, handoff and relevant source/test code. Benchmark numbers and passing tests below are Claude's recorded evidence, not fresh executions by Codex. No application, database or deployment changes are authorized in this ruling-writing turn.

### Completed work and correction to my earlier ruling

F1–F3, H1–H4, R1 and R2 remain complete. Do not redispatch them. R1 needs no further work.

My earlier instruction to 'preserve that call-path test' assumed a test I had not verified existed. That was my error. The new test_the_scheduled_job_captures_the_wall_clock is exactly the intended check: inject an off-boundary naive UTC sentinel into _utcnow and assert capture receives it unchanged. Claude's reported mutation check supports that assertion. Accept the test and corrected injected-clock documentation; no further clock work requested.

### A. Choose typed counters now; retain the month view

Choose option 3, before the first rollout. Do not implement the proposed sequence of removing 30 days and adding permanent completed-day memoisation. Keep ALLOWED_DAYS=(1,7,30) and the month selector. The current implementation may remain available for controlled local visual review, but its unbounded JSON materialisation is a rollout blocker until R3 below passes. No interim production deployment of the expensive endpoint.

Reason: the application has not been rolled out and already needs a migration. Additive typed fields remove envelope transfer on cold as well as warm requests, improve all three windows, and preserve the intended month experience. A memo alone does not bound a cold request, and permanently running rows prevent freezing some days. We do not need both a cache and a schema change for this release.

Accept the measured local risk: 12,728 rows, 56.8 MiB of JSON and about 201 MiB peak Python allocations at 30 days under the finish-plus-interval model; the upper-bound model is larger. These are synthetic representative workloads on local MySQL, not measured production capacity. Even seven days has a material per-request allocation. Retain those caveats in the report.

No JSON-path SQL, daily rollup table, per-day memo or additional service in R3. Use portable typed projections and bounded-memory Python aggregation. A date with no running rows is not an unconditional immutability guarantee if a future importer or delayed insertion can add older starts; no such cache contract is needed now.

### Claude task R3: typed activity reads with exact semantic parity

Scope: models.py; a NEW additive Alembic revision following the verified current head; features/radar/activity.py; focused activity/API/migration tests; scratchpad/bench_activity.py; ledger/handoff. Do not rewrite the reviewed d82f9afb5898 migration. No frontend contract or navigation change expected.

1. Add nullable summary_schema_version (integer), summary_countable (boolean, server default false, non-null), and four nullable signed BIGINT fields named posts_seen, posts_new, mentions and buckets_written to RadarIngestRun. The existing summary_json remains unchanged as provenance. A structurally valid summary under a representable schema version sets the marker; the reader separately filters version equality with its SCHEMA_VERSION. Missing, malformed or unversioned envelopes must not become compatible countable rows. A missing counter inside an otherwise compatible summary stays null and does not make the whole summary uncountable.
2. Write projection fields and the JSON envelope in the SAME existing finish_run transaction under its terminal/idempotency guard. Running/error records do not contribute counters. Preserve recorder failure containment and isolation from ingest transactions. Do not make a second counter writer or increment a separate day total.
3. Query only started_at, status, summary_schema_version, summary_countable and the four scalar counters for the requested UTC bounds. No summary_json selection or lazy ORM load in the activity read path. Iterate bounded batches and fold directly into at most 30 Berlin-day accumulators; do not retain per-day lists of rows. Use the existing Python ZoneInfo boundaries. This avoids database timezone dependence and per-counter SQL NULL pitfalls. Use a consistent read snapshot for the window; do not assemble pages from unrelated transaction snapshots.
4. For each day count all ok/running/error rows in their existing status fields. counted_runs includes ONLY ok rows with summary_countable=true AND summary_schema_version==SCHEMA_VERSION. Only those rows participate in counter sums. For each counter, return null when counted_runs is zero OR any participating row omitted that counter; otherwise return the sum, including genuine zero. Preserve completeness, recording_started_at, generated_at, from/to and date semantics exactly. Noncountable and off-version ok rows affect completed_runs but neither poison nor add to compatible counters.
5. Preserve existing rows during migration. Do not assume the table is empty merely because no rollout is recorded. Implement a bounded, portable Python projection backfill as part of the migration, with a frozen version of the projection rules (no imports of mutable app services). Scan by primary key in batches of at most 500; retain JSON and status values, change only new fields. A malformed individual envelope receives countable=false; a missing individual counter in a valid summary receives null. Test unsupported versions explicitly. Upgrade runs with relevant workers stopped; no mixed old writer/new reader interval is supported. Downgrade removes only the new fields and preserves the original tables/envelopes. Document that a later downgrade loses projections, which can be rebuilt.
6. Accepted production counter domain is nonnegative integers fitting signed BIGINT. Do not silently coerce strings/floats, clamp overflow or invent zeros. If pre-existing data violates this domain, report the exact nonsecret shape/count and bring that compatibility exception to Codex; do not silently alter historical semantics to force the migration through.

Required acceptance evidence:

- Differential tests compare the old envelope-based reference reducer with the new read result for empty days, genuine zero, missing/null individual counters, malformed/missing envelopes, compatible and incompatible versions mixed together, error/running runs, and multiple independent sources. Reference oracle lives in tests, not a production JSON fallback.
- A run started before Berlin midnight and finished after midnight changes the prior day's result on the next read, including incomplete/completed/counted counts and totals. Also test a run that remains running, terminal retries, and Berlin spring/autumn DST windows. No day result is frozen by date.
- Migration upgrade/downgrade/upgrade on the verified disposable database preserves existing JSON and unrelated tables/rows. Include existing valid, incomplete, malformed and off-version run fixtures; do not test an empty table only. Verify backfill output equals the new writer's projection for the same envelopes.
- A query-level test fails if activity summary fetches summary_json. Do not prove this merely by shrinking fixtures. Verify recorder failures and ingest transaction isolation still pass.
- Rerun both benchmark scheduling models for 1/7/30 days, including cold application state and repeated reads. Report median and maximum timings over five measured requests, peak incremental Python heap, and process memory if available; distinguish DB buffer warmth from application caching. At the existing 30-day upper-bound fixture, target peak incremental Python heap <=16 MiB and median endpoint <=500 ms on the same local environment. These are new acceptance targets, not predicted results or production guarantees. If they fail, return the measurements before expanding architecture. Also exercise four concurrent 30-day reads and report errors/peak process memory; do not infer concurrency safety from one request.
- Independent read-only review of semantic parity, migration/backfill and measured allocation. Fix findings, commit only R3 work, and update CODEX-RETURN.md plus FOUNDATIONS-LEDGER.md/HANDOFF.md. Existing completed tasks stay complete; add R3 as a new task.

### B. Owner visual review can proceed

No additional known Release 0/1 issue blocks controlled local visual review of /radar/hub/. R3 runs in parallel with that feedback process; it blocks rollout, not looking at the interface. This is not a declaration that Codex has independently audited every page or that the owner has approved production visuals. Keep fixture provenance visible in review evidence. Do not require the owner to wait for more backend work before reviewing the design.

### C. Sequence the release; do not execute it yet

The ordered path is now specified, but none of these actions is authorized by this document:

1. Owner reviews the local opt-in hub. Claude resolves agreed UI feedback and R3, with evidence and review. Prepare an integration/release plan against the THEN-current target branch; this long-lived branch must be checked for drift and migration-head conflicts, not blindly merged.
2. After separate release authorization: preserve a rollback artifact, stop affected writers, back up/verify recovery, apply the existing and new additive migrations on the actual target engine, deploy/restart web and ingest on the reviewed revision with capture OFF. Check writer projection consistency and authenticated activity/ops/read/watch flows. Keep /radar/ serving the old board and /radar/hub/ opt-in. Rehearse MariaDB compatibility before production; local MySQL success alone is not that check.
3. After separate capture-enable authorization and healthy deployed reads/writes: set RADAR_PRODUCER_REVISION to the actual deployed SHA and enable RADAR_OBSERVATION_CAPTURE_ENABLED on the ingest host; restart as required. Observe at least two successive scheduled slots for timestamp/provenance/US-DE pair integrity and monitor resource/ingest impact. Failure action is disable capture while retaining already recorded rows. This can precede root-route promotion so useful history starts accumulating.
4. After owner acceptance of the deployed opt-in hub and stable operational checks: separately authorize promotion to /radar/. Prepare explicit old-route/asset rollback and old-link/deep-link handling; 'the old /radar/ is the rollback' is no longer sufficient once that route changes. Capture operation remains independent of navigation promotion.

Claude's immediate implementation scope is R3 only. Preparing a rollout proposal is allowed; running migrations outside the disposable environment, merging, deploying, enabling capture and changing the main route remain untaken decisions. Do not expand R3 into the later news/portfolio/analysis releases.

---

## First return (historical rulings; superseded where stated above)

Reviewed 2026-09-09. Source inspected in C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations, branch codex/radar-foundations. Actual HEAD is b78b5d284f703c484581b01780ae8b16f63beb9a, newer than CODEX-RETURN.md's 1e30096. Git status reported no changes (with access warnings for ignore/cache paths). Later commits are handoff documentation. No application code, database or deployment was changed during this review; tests reported by Claude were read, not rerun by Codex.

## 1. counted_runs: approved

Keep it and adopt it into the activity contract. completed_runs counts successful runs; counted_runs counts compatible summaries contributing to the counters. Activity.tsx displays their difference. Removing the key to match the original enumeration would reduce accuracy. Null per-counter handling remains required; counted_runs does not prove all counters were present or all source activity was captured.

## 2. Filters.tsx: approved, with a focused correction

The file fulfills an existing requirement, not additional product scope. Separate ownership of filter controls is appropriate.

However, toggle() currently returns all other feeds when the last selected feed is unchecked. Example: sources=['reddit'] with all_sources=['bluesky','fourchan','reddit'] becomes ['bluesky','fourchan']. Its comment says the action is refused, but the implementation changes the selection to unrelated feeds. This needs correction before marking the returned implementation fully accepted.

Claude task R1: retain the current selection when removing its final selected root would leave none; optionally disable that final checked checkbox with an accessible explanation. Preserve concrete subreddit selections. Add a behavior test that begins with only Reddit, clicks its checkbox, and asserts Reddit remains selected and no request for unrelated feeds is issued. Also cover a concrete reddit:subreddit selection and normal removal when a second feed is selected. Run the focused Filters/hub tests, obtain read-only review, and record the fix commit in HUB-LEDGER.md. Do not repeat completed H1–H4 tasks.

## 3. Recorded limits

### Activity query: retain temporarily; measurement required before rollout

Keep portable Python aggregation for the local review. Do not approve its capacity using the quoted 2,880 runs/30 days estimate: that uses the observation archive's 15-minute cadence. Ingest is scheduled separately; config.py has CYCLE_SECONDS=180 and REDDIT_INTERVAL_SECONDS=120, with session/provider-dependent scheduling. The actual number and size of recorded runs must be measured from those writers, not inferred from capture frequency.

Claude task R2: correct the estimate in source comments and handoff/ledger. Prepare a repeatable disposable-DB benchmark using representative envelopes and actual configured ingest schedules. Record run count, total JSON bytes, DB query/aggregation time and endpoint response time for 1/7/30 days. Real-server measurement remains a rollout check; do not access production by inference. If the measured endpoint is slow, propose a portable typed-counter or daily-rollup design with existing schema/null semantics rather than introducing unverified JSON SQL expressions. This does not block visual review.

### capture(now): accepted as an internal injected-clock interface

The only production scheduler caller passes _utcnow(); accepting a time argument makes deterministic tests possible and is not itself a defect. No public backfill endpoint or user-supplied timestamp is authorized.

Correct the wording: observed_at is copied from the supplied now; the function does not independently enforce wall-clock truth. The guarantee holds through the reviewed scheduler call path. Preserve that call-path test, naive-UTC convention, actual payload generated_at and immutable slots. Any future backfill/import feature requires a distinct provenance contract.

## 4. Shared-code changes: approved for this scope

Keep 403 read/write distinction in api.ts: the new admin read can be forbidden while writes can fail at the existing CSRF gate. Do not generalize every future write403 to session if permission-controlled mutations are later added.

Keep resolve_asset_css and manifest memoization. The hub entry needs its emitted stylesheet and the helper preserves the separate feature asset directories. Existing recorded asset/Gym regression checks support this change. This approval is for the current entry graph, not a claim that every future dynamic-chunk CSS ordering scenario has been verified.

## Other finding and next handoff

Leave the independently reproduced pre-existing ingest-test cleanup defect in its separate task. It is not a reason to alter the product scope or rerun completed implementation tasks.

Next: Claude applies R1, corrects documentation and supplies R2 measurement evidence; owner can review the opt-in hub visually in parallel. No merge, deployment, root-route promotion or capture enablement is approved here. Codex has not yet performed a full independent implementation or visual audit.

This ruling file is currently in the planning checkout. Carry it into the implementation worktree and update its canonical ledgers/handoff before continuing; do not rely on chat memory.

## Third return: R3 acceptance and remaining release work — 2026-09-09

This section supersedes the second-return instruction to implement R3. Verified worktree HEAD c6efdd5e06f2fff8603dff22fae0b9b75909f2e7, branch codex/radar-foundations. Git status is clean apart from ignore/cache access warnings before this ruling edit. Read CODEX-RETURN.md, R3 ledger evidence, HANDOFF.md, activity.py and migration a7c31f0b52d4. No tests or benchmark were rerun by Codex, no database inspected or changed, and no application code changed. Acceptance uses Claude's recorded verification plus source review; it is not MariaDB certification.

### Decision: strict integers are correct

Accept schema_version only as an integer excluding bool. Keep 1.0 and True uncountable; do not restore Python's incidental equality coercion. The supported format is the producer's explicitly versioned envelope, not every value Python happens to compare equal to 1. Keep tests that explicitly demonstrate divergence from the old reducer. Preserve original JSON unchanged.

Accept the counter contract as implemented: a genuine nonnegative integer within signed BIGINT is countable; missing/null stays null; invalid values are never coerced or clamped. On the live projection path an invalid counter becomes null with a warning and makes that participating day's counter unavailable. This is an explicitly accepted change from the old reducer's accidental summing of negatives/bools/floats or TypeError on strings. It must not be described as exact parity for arbitrary JSON. The migration separately refuses invalid historical counters before DDL; that refusal remains required, rather than silently converting history.

### A. Compatibility evidence: accepted within its measured scope

Claude reports no accepted-domain violation in the disposable clone. No compatibility exception needs adjudication for that dataset. This does not establish the content of the eventual target database; retain the target preflight/domain scan with writers stopped. If it finds violations, preserve the source values and return their nonsecret shapes/counts for a ruling. Do not interpret the migration's phrase 'fix the data' as permission to rewrite source history automatically.

### R3 acceptance

R3 is accepted and complete. Recorded upper-bound results meet both specified targets: 0.8 MiB incremental Python heap and 390 ms median endpoint (414 ms maximum). Four concurrent requests returned without errors, with about two-second latency each and RSS 135 to 136 MiB. This supports the tested workload only; concurrency is slower and local MySQL timings do not establish VPS/MariaDB behavior. Keep the month view and 1/7/30-day contract.

Do not redispatch F1–F3, H1–H4, R1, R2 or R3. No further application change is requested by this ruling.

### B. Migration failure state: accept explicit recovery, rehearse before rollout

Accept the pre-DDL domain refusal and the documented drop-derived-columns/re-upgrade strategy for an interrupted backfill. Atomic rollback of the DDL is not assumed. The original envelope remains the recovery source, and no source table or row should be dropped. A resumable migration framework is not required for this release.

The literal six-column DROP in the docstring applies only when all six columns exist. A failure during the sequence of ALTER TABLE operations can leave fewer columns. Before recovery, the operator must verify the database identity, actual Alembic stamp, actual column inventory and stopped writers/readers; remove only projection columns confirmed to belong to this failed, unstamped revision. Never execute the full statement blindly or stamp the revision merely to bypass failure. For a successfully stamped revision use the tested downgrade procedure when appropriate, not the unstamped-failure recipe. Keep a verified backup and preserve summary_json, status, times and row counts throughout.

Remaining release-preparation task P1 for Claude (documentation/rehearsal, not reopening R3): carry these prerequisites into the rollout runbook and demonstrate recovery on a disposable target-compatible MariaDB environment from (a) interruption after only some columns exist and (b) interruption partway through backfill. Verify recovery followed by upgrade produces the same projections and unchanged source envelopes/row counts as a clean upgrade. Also verify the normal upgrade/downgrade path on that engine. Record version, commands, results and any engine-specific findings. If no suitable disposable MariaDB environment is available, record that release gate as pending rather than substituting MySQL evidence. No production access or migration is authorized here.

Correct the stale HANDOFF.md 'Deployment carries' paragraph when preparing that runbook: both d82f9afb5898 AND a7c31f0b52d4 must be applied before this code runs. Applying only the first is insufficient for the new writer/reader. Check migration heads again against the actual integration target; do not assume today's head remains current.

### C. Visual review and next step

Nothing known in this return blocks the owner's visual review of /radar/hub/. R3's memory blocker is resolved under its local acceptance criteria. Owner acceptance of the visuals remains separate from these backend rulings.

The owner has expressed a preference to compare both interfaces on the VPS using the same live data. Therefore local visual approval is not a prerequisite to preparing a side-by-side VPS review deployment. Prepare that concrete release proposal next: existing /radar/ remains, new /radar/hub/ is opt-in, both use the same authenticated account/data and the same ingestion process. Do not start a duplicate ingest daemon. Shared watch changes are expected. The proposal includes target-branch drift review, both migrations, P1 rehearsal, service ordering, rollback and live-data comparison checks.

The existing section C release sequence otherwise stands: deploy opt-in with capture off after the release checks and authorization; enable capture as a separate decision after healthy deployment; promote the root route only after owner acceptance. This turn expressly authorizes ruling/documentation only. No merge, deployment, target migration, capture enablement or root-route change is executed or newly authorized here.

Claude's next return should be the concrete side-by-side release proposal and outstanding environment checks, not another implementation of completed work. Update ledgers/handoff to mark this decision resolved and P1/release preparation open. Keep owner visual review open until actually performed.

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

## Fourth return: P1 accepted; release target and remaining gates — 2026-09-09

Supersedes conflicting release-preparation directions above. Verified HEAD 8f788503fba1e9fa0b7e62e8d0dc8ec925d2489a on codex/radar-foundations; status clean before this documentation edit, with ignore/cache access warnings. Read RELEASE-PROPOSAL.md, return/ledger P1 evidence, handoff deployment carries and rehearse_mariadb.py. P1's 39 passing checks are recorded Claude evidence, not freshly rerun by Codex. No live state was inspected. No merge, push, application change, database operation, deployment, enablement or promotion is authorized by this ruling.

### A. Architecture approved; operator runbook not yet release-ready

Approve the side-by-side design: /radar/ remains the existing destination; /radar/hub/ is opt-in on the same database, session, watching and single ingestion daemon. Capture stays off, and root-route promotion remains separate. Do not call the old board's code completely untouched: shared API error handling and Vite resolution changed in this release. Its required behavior is preserved, subject to regression checks. Returning to the old page is a UI fallback, not rollback of shared services or schema.

The corrected first-deployment reasoning is right CONDITIONAL ON target read-only checks: if both new tables are absent and the actual revision is b3d9e1f5a274, the first migration creates them and the second backfills zero rows with writers stopped. Repository code cannot prove the live tables or revision. Verify BOTH radar_ingest_runs and radar_board_observations are absent. Unexpected tables/stamps/rows mean stop and diagnose; never delete them to force the assumption true. 'projected 0 rows' is the expected post-upgrade check, not a guarantee in advance.

Attempting flask db upgrade is never a read-only preflight. Also avoid saying schema upgrade alone 'completes the release': it performs the schema mutation, while deployment and verification remain separate. Keep the corrected prohibition on using it as a dry run.

### Integration target: origin/main; no separate push of the 12 local commits

Choose the fetched origin/main as the eventual integration target because the established VPS deployment resets to it. Do not hand-deploy codex/radar-foundations and accept later silent reversion. Do not push local dev_personal first or merge it wholesale as a prerequisite.

Prepare an isolated candidate branch starting at freshly fetched origin/main and transplant only the release commits introduced AFTER 7a9ffe4, preserving their chronological order. Preserve the existing foundations branch and worktree unchanged. This avoids silently including the twelve unpublished ML/research commits beneath the feature branch. Preparing this LOCAL candidate is the proposed next task for Claude when dispatched, not authorization to merge/push anything in this turn. Do not reset, rebase or force-push the original branches.

Acceptance: record selected/excluded commit SHAs and the resulting file diff; confirm no excluded commit is an ancestor of the candidate and no unapproved research change enters through conflict resolution. Run the release's relevant frontend/backend/shared-helper regressions and migration-head checks on the candidate with disposable databases. A clean textual transplant alone proves no dependency safety. If tests or code require one of the twelve, bring the minimal dependency and its diff back for explicit scope review; do not silently import all twelve. Docs may retain original evidence SHAs, but label their provenance and record new candidate test evidence separately.

### Deployment operator and mechanism

Planning decision: Claude is the implementer/operator once the owner separately authorizes deployment with the necessary access; the owner need not manually transcribe shell commands. Until then Claude prepares the runbook only. Codex reviews the concrete candidate and gate evidence.

Use the existing /root/update_coc.sh deployment mechanism as the intended single migration owner, ONLY after its actual contents and service/environment paths are inspected. The report of what it does is not enough. Remove the alternative hand-migration branch from the executable runbook. Steps that describe script internals must not look like commands to run a second time.

Require fail-closed sequencing: pin/check the exact approved origin/main SHA; stop required readers/writers BEFORE changing checkout/schema; build with the correct runtime; apply both revisions once; verify head/columns; start services only after success. Confirm the script actually stops the web reader and exits without restarting on migration/build failure. If it cannot satisfy these requirements, propose a minimal script/wrapper change for review; do not improvise production edits. Discover actual unit names, WorkingDirectory, virtualenv, Flask entrypoint and privileges from service definitions, rather than treating the runbook's bare flask command as executable evidence.

### B. Required P2 release-package corrections and gates

P2 is NEW release preparation, not a repeat of completed P1 or feature tasks. Claude prepares the following and obtains independent read-only review:

1. One authoritative numbered execution path through the script, with exact verified commands/runtime paths, expected results, explicit stop conditions and ownership. No manual/script double migration. Record the approved candidate SHA, actual deployed SHA and current remote SHA; abort on drift. Record configured capture flag, not just absence in this worktree, and require it false on the target.
2. Read-only target preflight: database identity, actual Alembic revision and relevant schema inventory, engine build, sql_mode, transaction isolation, charset/collation and service/deploy-script settings. Compare with rehearsal. Version difference of any kind requires assessment; a different minor is not the only possible incompatible setting. A stamp is evidence of migration state, not proof every underlying table matches it. Do not replay or stamp old revisions based on repository assumptions.
3. Inventory active services AND timers capable of starting jobs; preserve their prior states. Stop/mask or otherwise inhibit relevant triggers for the maintenance window so a timer cannot undo a stopped-service guarantee. Identify whether radar-encoder-trial can start a writer or compete for the affected resources; don't assume its pre-existence makes it irrelevant. Check actual processes/unit state, not only loaded units, to verify one ingest instance. Restore only previously enabled/running services after success.
4. BACKUP RESTORE IS A HARD GATE, not 'restore or accept without'. Use a consistent backup with recorded timestamp, schema/version, checksum and scope. Restore to an isolated disposable MariaDB target; verify table inventory/schema plus representative Radar/account/watch data and counts from the SAME backup snapshot. Comparing an old backup's counts to a still-changing live DB is not a valid restore check. Document recovery commands, storage/permissions and achievable data-loss window. Never run rehearse_mariadb.py against the restored backup: that harness drops its schema. No live restore or production write is authorized. If access to a suitable backup is missing, report that exact gate pending and complete independent planning work.
5. Rollback must survive update_coc.sh's hard reset. Specify an approved revert on main or a deliberately pinned rollback artifact with routine deploy inhibited until main is reconciled. A detached git checkout alone is not durable rollback. Stop affected units before rollback, retain/build matching assets/dependencies, verify the actual deployed previous SHA. Prefer code-only rollback with additive schema retained. If schema downgrade is separately authorized, run it while the NEW migration files/runtime are still available and workers stopped, BEFORE checking out code that lacks those revisions. Dropping the new tables after runs exist loses recorded data; back them up and obtain explicit data-loss approval rather than treating it as harmless.
6. Failure recovery must distinguish stamp b3d9e1f5a274 with partial FIRST-migration tables/indexes from stamp d82f9afb5898 with partial projection columns. Existing P1 proves second-migration recovery; it does not prove a projection-column DROP fixes interruption in first-table creation. Document inspection-based first-migration recovery and validate that additional failure branch on a disposable database before executing it anywhere else. No blanket DROP TABLE or stamp-to-skip recipe; preserve any records discovered. This is additional runbook failure coverage, not rerunning the completed P1 checklist.
7. Verification: authenticated old-board/hub comparison with equivalent filters and aligned generated_at (live refresh may otherwise legitimately differ); restore any temporary watch changes; admin200/nonadmin403/signed-out expected behavior; first successful run stored with matching JSON/projection fields and counted_runs; baseline capture remains off. Include shared-app smoke checks because asset helpers are shared. Record wall-clock deadlines for first cycle/service readiness based on actual schedules; never leave an operator waiting indefinitely or repeatedly restarting a healthy slow job.

A newly changed migration head is a stop-and-reconcile gate, not a permanent rejection. Resume only after the candidate's migration chain and verification are updated. The short duration of an empty-table backfill is not evidence of the total downtime: builds, locks, restarts and verification contribute too.

### C. P1 limits accepted; target checks still required

Accept P1 as complete evidence for these two migrations, projection behavior and the exercised recovery cases on upstream MariaDB 10.11.14. No request to repeat the 39 checks or replay the sixty historical revisions. The portable/default-config result does not establish Ubuntu build/tuning behavior, current VPS schema, actual deployed code or backup recoverability. Those are P2/target gates, not reasons to reopen P1. The target's reported version remains a fact to verify when access is authorized.

The rehearsal script drops an arbitrary permitted local schema. It is a dedicated destructive harness, not the backup verification tool or a generic live preflight; use only its isolated throwaway environment. Preserve strict-integer behavior and all previously accepted feature decisions.

### Disposition and next work

Release architecture and P1 approved. Release execution remains blocked on P2 candidate/single-path runbook, verified target facts and demonstrated backup restore. Local visual review can proceed; preparing side-by-side VPS review remains the next delivery objective. Capture enablement and main-route promotion remain separate untaken decisions.

After this release work, the next FEATURE is historical analysis ahead of portfolio/news. The planning checkout contains the newer ROADMAP.md, HISTORY-ANALYSIS-PLAN.md and HISTORY-ANALYSIS-LEDGER.md. Carry only those reviewed planning files at the next coordination point; do not overwrite active execution handoffs with stale copies. This does not add analysis implementation to P2.

Claude's next dispatch should prepare P2 and return its candidate SHA, reviewed runbook, evidence and precise remaining access gates. Do not repeat F1–F3, H1–H4, R1–R3 or P1. No deployment action follows automatically from this document.

## Fifth return: P2 review and final bounded closure — 2026-09-09

Verified candidate HEAD 97bb9a6cd5795a260bbb8f78da2fc90b9bf79854 on codex/radar-release-candidate; Git status clean before this doc edit, with ignore/cache access warnings. Read runbook, target facts, P2 return/ledger sections and candidate/recovery harness source. Target reads, restore, rehearsal and test counts are Claude's recorded evidence; Codex did not rerun them or access production. No application, database, merge, push, deployment or service change made here.

### A. Accepted package components

Accept the isolated candidate and exclusion of the twelve research commits, subject to the normal final-SHA drift gate. Accept the recorded target inspection and backup restore as closing those access/evidence gates. Accept P1 and first-migration recovery evidence, including all-four-DDL-before-stamp case; do not repeat completed work. Keep strict-integer behavior and the approved side-by-side architecture: same data/account/ingest, old route retained, capture off, no root promotion.

The restored snapshot proves recoverability of that snapshot. It does not authorize nearly 24 hours of potential user-data loss. Before the scheduled window obtain a fresh consistent backup through the verified mechanism, record its checksum/timestamp and verify integrity; do not repeat the entire restore rehearsal solely because another backup is taken by the same verified process. Disclose the remaining loss window if full restore becomes necessary. A full live restore remains an exceptional separately authorized operation, not an automatic rollback step. Prefer tested code-only rollback retaining migration files and additive schema.

### B. Overrule serving through the in-place deployment; no permanent script edit required

The narrow schema compatibility argument is reasonable, but 'no model means cannot touch it' is not a general guarantee and does not address templates/assets/dependencies changing beneath old workers. The claim neither interface breaks 'in practice' lacks a mixed-version deployment test. Stop personal_apps_web BEFORE checkout/build. Because update_coc.sh also updates the shared checkout and restarts coc_web, stop that web unit too for this maintenance window. Record the associated temporary outage.

Use pre-stop orchestration around the existing script; a permanent edit to /root/update_coc.sh is not required for THIS release if this procedure is faithfully documented and checked. Stop/inhibit radar-encoder-trial.timer AND ensure an already-running radar-encoder-trial.service has stopped; stopping a timer does not terminate its current invocation. Keep the scheduled backup outside the window. Preserve prior enabled/active/masked states, using temporary inhibition and restoring the original state only.

The current runbook contradicts itself: section 1 permits serving, step 6 stops the web, and section 4.4 claims checks happen before services start even though update_coc.sh already restarts them. Fix this explicitly. Choose the actual script behavior: successful build/migration is followed by its restarts; subsequent schema/API checks are POST-restart verification. A nonzero script exit stops the procedure and requires inspection/recovery, not blindly starting everything. No false promise of a separate pre-start SQL gate. Do not mask units the script itself must restart; inhibit the trial trigger separately. Check prior service states: if they differ from the script's unconditional restart assumptions, stop and revise before execution.

### D. Full-suite disposition

Accept the disclosed 13 failures as reproduced at the old baseline; do not call the full suite green or reopen all unrelated failures. The baseline 7a9ffe4 is not the deployed candidate base, so baseline reproduction alone is not proof of target behavior. Release-specific suites remain useful evidence.

Two shared-watch failures require a focused explanation before the go decision: test_deleting_the_account_deletes_its_marks and test_a_mark_for_an_account_that_does_not_exist_is_an_error. These assert cascade and foreign-key integrity, not merely list rendering. Four valid restored watch rows prove neither constraint works. No assumption that these are just dirty fixtures is accepted without the actual failing assertion and schema/session evidence.

### P2-close: only the following remains for Claude

1. Correct RELEASE-RUNBOOK.md/TARGET-FACTS.md interpretations per B without altering historical read facts. Record the true script restart boundary; correct failure-path cross-references (script failure currently points at section 5 verification instead of rollback/recovery); remove the stale 'backup timer' wording. State 33 first-migration checks/four interruption points instead of stale 25/three. Keep the preferred rollback migration files and specify a no-fast-forward release merge so the documented git revert -m 1 has a merge parent to reference. Do not actually merge.
2. For the two watch failures, capture exact failing assertions and classify using a disposable restored MariaDB copy: SHOW CREATE TABLE radar_watch, foreign-key/delete rule, engine and session foreign_key_checks. Test account deletion cascade, orphan insert rejection, per-account isolation and normal add/remove with uniquely owned temporary fixtures. Compare with the candidate-base definitions/migration; if needed use read-only target constraint inspection under existing read authorization, without dumping private rows. If fixtures/config explain it and intact production-compatible schema passes, record that evidence and close. If the shared contract is genuinely broken, return the narrow finding and proposed repair for a ruling; do not expand into broad schema cleanup or change live data.
3. Independently review ONLY these closure changes/checks. Update CODEX-RETURN.md with the resulting candidate SHA, exact watch results and a single go/no-go summary. Do not rerun all 2,692 backend tests just to chase unrelated baseline failures. No repeat of F/H/R/P1 or completed P2 work.

### C. Scheduled release disposition and outstanding authorization

Provisionally accept the candidate for a side-by-side release. Execution is NO-GO until P2-close resolves the contradictory service ordering and the two watch failures. This is a small final closure, not another feature iteration or access exercise. A tentative window can be chosen now, outside the backup job, but it must not execute before closure.

After closure, what remains is explicit owner authorization naming the final candidate/release SHA and window to (1) merge/push the reviewed release into main and (2) run the VPS deployment with both migrations and the documented temporary stops/restarts. No authorization to enable capture or promote /radar/ is bundled into that. If unexpected drift or target state appears, stop and report rather than improvising. Claude remains the operator after authorization; Codex owns the go/no-go ruling.

No application or infrastructure modification is requested in this ruling turn. Claude's next dispatch is P2-close as defined above. Preserve completed ledgers; append these two outstanding closure items, do not relabel all of P2 incomplete.

## Sixth return: P2-close accepted; GO for scheduling — 2026-09-09

Verified candidate 71a5f1b2936648f192e3bf12399430ce445047a9 on codex/radar-release-candidate. Working tree clean before this documentation edit, apart from Git ignore/cache access warnings. Read the return's P2-close section, runbook sections 1/4/6/7, corrected target interpretation, watch-integrity ledger and probe, and watch.add/remove source. Recorded test/probe/target evidence was not freshly rerun by Codex; no production access, database operation or application change occurred in this turn.

### A. P2-close accepted

Accept the service orchestration and failure/rollback ordering. Both web units stop before checkout; the trial timer is inhibited and any active trial service stopped; the existing script owns migrations and restarts. A nonzero script exit requires identifying the completed stage and actual service/schema state, not assuming everything remains down. Preserve original unit states and keep the backup job outside the window.

One stale summary cell remains in RELEASE-RUNBOOK.md requirement 1.2: it still says YES even though the detailed path and TARGET-FACTS.md correctly say PARTLY. This ruling supersedes that cell: a tail failure can occur after some restarts. Correct the cell when carrying this documentation forward; no new implementation/review cycle is required for that editorial correction.

Accept the watch investigation's classification: the two failures are caused by the disposable schema's absent FK, not a demonstrated product regression. The production-DDL SQL probe plus source inspection supports the expected cascade/orphan behavior; do not describe the probe as an application/ORM integration test. Production read evidence and backup DDL are snapshots; refresh pertinent target facts during the usual preflight.

The historical 24–27 second ingest-stop/start intervals are useful planning evidence, not measured downtime for THIS release. The roughly 60-second budget is an estimate, not a kill timeout or guarantee. If exceeded, inspect progress and report; do not interrupt a progressing migration solely to meet that estimate.

### B. Missing 29 constraints: material evidence limitation, accepted for this release

Reject the assertion that this finding 'does not weaken this release's evidence'. It weakens conclusions about integrity-sensitive paths tested against that clone, including hub watching. It does not invalidate every passing test or the separate MariaDB migration/recovery results. The new archive/run tables themselves have no FKs, and the targeted watch SQL evidence plus unchanged backend ownership/error-handling logic limits the residual risk sufficiently for this release. Accept that bounded risk; no requirement to rerun the entire backend suite before scheduling.

Create a post-release test-environment task TE1, to be completed BEFORE further backend feature implementation (including historical capture/analysis): build a NEW disposable database from a proper schema-preserving dump/restore, rather than destroying the current clone in place. Verify the expected FK definitions/delete rules (29 at the recorded base), unique keys, engine/settings and migration stamp; apply accepted migrations in the disposable environment. Run actual watch service/API/account-integrity tests with constraints enabled, plus affected migration/recorder tests. Keep existing evidence labelled as constraint-free and record replacement evidence separately. If the restored data needs sanitization, do not silently remove constraints to make fixtures pass. No live change or clone rebuild is authorized in this ruling-writing turn.

The remaining unrelated baseline failures stay disclosed; they are not a green full-suite result. Do not reopen F1–F3, H1–H4, R1–R3, P1 or completed P2 work.

### C. Go/no-go and precise authorization boundary

GO for scheduling the side-by-side release of candidate 71a5f1b. No unresolved implementation or investigation gate remains for this bounded release. Normal execution preconditions still apply: fresh consistent verified backup, final target/remote/schema/capture/service-state checks, no competing deploy, and a window clear of the 03:15 backup. Changed facts require assessment; they are not permission to improvise.

NO-GO for execution until the OWNER explicitly authorizes the release window and these actions together:

- merge the reviewed candidate into main with --no-ff, push main and record the resulting merge SHA;
- create the fresh pre-window backup using the verified mechanism;
- temporarily stop the named web/background units and inhibit/restore the trial timer as documented;
- run /root/update_coc.sh to deploy that exact approved merge result, apply both migrations and restart;
- perform the documented authenticated comparison and health checks, restoring temporary watch changes;
- if required, perform the documented code-only rollback retaining both migration files and recorded data.

Authorization may name 'the next suitable window' rather than requiring the owner to choose a timestamp. Claude must announce the actual window and record the candidate/merge SHA before taking services down. A docs-only commit carrying this ruling does not reopen code review, but record its SHA and verify it changes documentation only. Any application change or unexpected integration diff returns for review.

Do not bundle capture enablement, root-route promotion, schema downgrade or full live backup restoration into this authorization. Those remain separate decisions. /radar/ remains the existing board and /radar/hub/ the opt-in live-data comparison.

Suggested owner authorization, if desired: 'Authorize Claude to merge/push the reviewed 71a5f1b release (plus documentation-only ruling updates) and deploy it side by side in the next suitable window under the accepted runbook, including the fresh backup, temporary service stops and code-only rollback if needed. Keep capture off and /radar/ unchanged.' This is a proposed authorization, not a statement that it has been granted.

Next action is owner release authorization, then Claude executes the accepted runbook. No further planning handoff loop is required. Record TE1 as post-release work and preserve historical-analysis-first as the next feature priority.

## Seventh return: executed release accepted; visual acceptance outstanding — 2026-09-09

Reviewed RELEASE-RECORD.md, the d3bc795 documentation diff, runbook and relevant judge_trial.py source. Verified candidate branch HEAD d3bc795 and no reported tracked changes (Git emitted ignore/cache permission warnings). Verified ba1c381 has parents 2a83905/745eb2c and the same tree as 745eb2c. Production execution, timings and checks below are Claude's recorded evidence, not fresh Codex target measurements. No application, database or deployment change is made by this ruling.

### A. Accept the executed side-by-side release

Accept ba1c381 as the completed operational release on the reported evidence: successful script, migration head a7c31f0b52d4, services restored, live projection smoke check and shared-surface checks. No repeat release rehearsal or new deployment gate. The 60-second recorded web outage is the release measurement; historical ingest restart intervals are not its downtime. One matching production row demonstrates a smoke check, not exhaustive counter parity. The 1/7/30-day timings use a newly populated dataset and do not replace R3's capacity measurements.

Capture remains off; /radar/ remains the original route. Acceptance of deployment is NOT visual/product acceptance. The owner has now compared the live chatter table with the interactive mockup and rejected its fidelity: repeated source labels, oversized rows, poor column balance and missing tone bar/percentage. Record that review as performed with corrections required, not awaiting the owner's first look.

### B. Carry the release documentation forward, with bounded editorial corrections

Approve carrying d3bc795 into main as documentation, with this ruling and corrected current-state summaries, through Claude's next dispatch. No separate full implementation/review cycle or VPS deployment is needed for documentation. This ruling does not itself execute a push.

Before carrying: label the runbook as the executed first-release procedure with RELEASE-RECORD.md as the outcome; its opening 'nothing executed' and pre-migration expectations must not masquerade as current target facts. Update HANDOFF.md's stale P2/access/authorization next action. Preserve historical evidence and exact deployed SHA separately from documentation HEAD.

Accept disable --now plus inactive/empty-next-elapse verification for this recorded timer and window. It prevents the scheduled trigger, not all possible manual/dependency starts. In BOTH forward and rollback paths restore enabled and active states independently (enabled/inactive and disabled/active are valid combinations); the current 'only if enabled AND active' recipe is incomplete for reuse, although it restored the actual recorded enabled/active state correctly. Do not change the unit file to force masking. Check the final documentation diff only; no new feature testing is required.

### C. Immediate priority and TE1

TE1 remains the first implementation prerequisite for further backend feature work: a NEW disposable schema-preserving database, verified FK definitions/delete rules and unique constraints, appropriate engine/settings/stamp, then real watch/API/account-integrity and affected recorder/migration tests. Preserve the old clone and label its evidence accurately. The already accepted SQL probe is not a substitute for those application tests. Follow the Sixth return acceptance criteria; do not reopen completed F/H/R/P work.

The immediate product priority is correcting the hub to the approved interactive mockup. Codex prepares the binding visual correction plan; Claude implements it. Design work can proceed while TE1 is completed; backend changes for that correction wait for TE1. Retain the compact tone bar AND percentage with an explicit valid denominator and unknown/unjudged handling. Inspect actual data semantics before choosing that denominator; never present tone as probability of a price rise. Investigate whether repeated feeds describe configured or contributing sources before defining their compact summary. Require visual comparison against the prototype using realistic long names, many sources, sparse/missing data and desktop/mobile widths, not only fictional tidy rows.

Historical analysis remains the next NEW feature after this correction and prerequisite work, ahead of portfolio and news. Carry the newer ROADMAP.md and HISTORY-ANALYSIS-PLAN.md/HISTORY-ANALYSIS-LEDGER.md from the planning checkout without overwriting current execution ledgers. Capture enablement still requires a separate decision; no retrospective data is being captured while it remains off.

### D. Retired watchdog: separate bounded cleanup task OT1

Accept creating OT1, independent of visual acceptance and not a release blocker. Source confirms TRIAL_RETIRED suppresses the deadline and automatic recovery; it deliberately retains the trial row and operator recovery path. Therefore do NOT simply change running to recovered/completed/failed to tidy the UI. Such a state could falsely claim recovery or alter retention, judging or rollback behavior.

Claude should prepare the exact operational retirement change: verify timer/service dependencies and restart/install paths; propose disabling/stopping only the retired watchdog with recorded prior state and a reversal command. Separately map every consumer of trial status, including retention pins, judging eligibility, audit and manual recovery. Keep the raw row unchanged until a truthful retirement representation preserving those contracts is designed and tested on the repaired disposable environment. A display of 'retired; automatic watchdog disabled' can be proposed with the stored lifecycle status distinguished explicitly. No fabricated audit success, deletion of evidence or automatic recovery.

Acceptance: no scheduled watchdog invocations after the approved operational change, ingestion/judging unaffected, retained evidence and manual rollback behavior unchanged, accurate status presentation. Return the concrete commands and any required data/code change for authorization before live execution. This release authorization does not extend to OT1 or capture/root promotion.

## Eighth return — TE1/VC1 reviewed, 2026-09-10

Verified codex/radar-release-candidate at d66b52e (nine commits after d3bc795;
836d232 is the documentation commit omitted from the return's short list).
Only CODEX-DECISIONS.md was reported dirty before this ruling, with Git
ignore/cache permission warnings. Read the VC1 ledger/current handoff, source
projection diff, tone/source helpers and row/disclosure implementation. Inspected
after-fixture-1440/390 and page-watching/activity-768 PNGs against the owner's
prototype reference. Independently ran the two focused Chatter/presentation
Vitest files: 56 passed, 2 files, after sandbox config-read denial was resolved
with an approved escalation. Other suite/database measurements remain Claude's
reported evidence, not fresh Codex runs. Production is still ba1c381 according
to the return; no fresh target inspection or production mutation here.

### TE1 and VC1 disposition

Accept TE1 as closing the known constraint-free TEST ENVIRONMENT defect. A
schema-preserving local-development restore and actual application integrity
tests supply the previously missing evidence. Do not call it a production clone:
MySQL 8 and utf8mb4_0900_ai_ci differ from target MariaDB and its collation;
matching local FKs/unique indexes does not establish every production constraint.
This limit does not require rebuilding again before this additive display change.
Existing independent MariaDB migration evidence retains its original scope.

Accept VC1a and the principal Chatter correction for owner visual review. The
rendered result fixes the reported source dump, missing bar, excessive tone
stacking and weak column hierarchy. Five measured fixture rows total 474px,
including warning rows; 430px for five plain rows is arithmetic only. The 133px
three-warning case remains explicitly disclosed and acceptable. The interactive
prototype is the near-term reference, not the final visual ceiling; original A/B
ambition remains binding for future design evolution.

Do not call VC1 unconditionally release-ready: the small closure below is due
before a deployment proposal. Owner can review the current preview immediately.
No rerun of completed TE1/F/H/R/P work. No merge, push, deploy or capture/root
change is authorized.

### A. Ratify the 2px minimum as an approximate visual indicator

Accept the minimum for a genuinely nonzero segment; true zero must remain absent.
Exact percentage/counts remain authoritative. Do not describe the resulting
geometry as strictly proportional or 'exact against every clause': tiny shares
are exaggerated for visibility. Add one sentence to the existing tone explanation:
'Tiny nonzero shares are drawn at a minimum width so they remain visible; use the
percentage and counts for the exact balance.' Keep it out of the primary row.
Retain rare-share geometry and percentage tests. No redesign of the bar required.

### B. Navigation accepted; restore the unrelated table breakpoints

Accept navigation collapse at 1080 and Chatter stacking at 860, including the
skip-link correction. Scope the new TABLE stacking breakpoint to Chatter; keep
Watching and Activity's previous 700px table breakpoint in this delivery. Their
mobile styles must still apply below 700 and the shared navigation may collapse
at 1080. The examined Watching capture is EMPTY, so it does not verify the changed
populated table. More available width above 860 also does not establish usability
of a newly stacked layout below it. This is a bounded scope correction, not a
claim that 860 is inherently wrong for those pages.

Verify populated Watching and populated Activity at 768 and near 700/701 and
860/861, plus Chatter at 768/390. Use labelled representative fixtures if local
rows are absent. No need for a whole new cross-page design cycle.

### C. Accept the measured column proportions

Ratify 26/13/10/18/17/12/4. Attention keeps its allocation and the screenshot
supports the trade. Do not turn approximate design proportions into pixel dogma.
Retain readable type, sample line, long-name access and wrapping warning badges.

### D. Fix duplicate accessible cell labels in the same small closure

Worth fixing now; do not defer a repeated announcement across every row. On
Chatter's desktop table, use native headers and keep supplementary cell labels
out of both visual and accessibility trees (display:none). In the stacked view,
show the real labels and retain the explicit roles/associations. Avoid permanently
aria-hiding the mobile labels or introducing JS viewport state for a CSS issue.
Check desktop/table and mobile/stacked accessibility representation and keyboard
behavior. Do not claim an actual screen-reader run if only DOM/AX checks ran.

### E. Watching treatment is a later design slice

Yes to eventual consistency of tone/source presentation where Watching shows
those metrics. Reuse the helpers and new Row field then. Do not insert metrics
into all pinned overview rows merely because their data shape permits it, or
remove watching-specific status/actions. No Watching redesign in VC1-close.
Record it as a future visual task with a populated mockup first. Historical
analysis remains the next NEW feature; future visual improvement can accompany
that roadmap without pretending the other hub pages are already accepted.

### Claude dispatch: VC1-close only

1. Apply A's explanation, B's scoped table breakpoints, D's responsive labels.
2. Verify focused tests/build and the populated responsive cases named above;
   inspect resulting PNGs. Keep all current tone/data/filter contracts intact.
3. One independent read-only review of these narrow changes, resolve findings,
   update VC1 ledger and HANDOFF with exact SHA, results and preview instructions.
   Preserve the prior evidence and disclose that this is a small closure, not
   redispatched VC1a-c. Carry this ruling as documentation when committing it.
4. Return the corrected preview for owner visual acceptance. Deployment remains
   a subsequent explicit decision. OT1/documentation carry are separate.

## VC1-close addition — sortable Chatter, owner approved 2026-09-10

The owner explicitly approved sorting after trying the preview. Add this to the
current closure alongside the Eighth-return fixes; do not defer it to a future
redesign or reopen completed TE1/VC1 work. Claude implements; Codex plans.

### User interaction and scope

- Default is Radar order: the exact order of the current board.rows response.
- Desktop headers are real buttons: Company (ticker A–Z initially), Attention,
  Voices, Sources, Tone, Price, and Today (numeric columns descending initially).
  Price and Today are two distinct controls within the existing price/move area;
  do not make one ambiguous combined sort. Repeated click toggles direction.
- Visible active arrow plus accessible sort state/name. Apply aria-sort to the
  active header, with a name distinguishing price from daily move when both
  controls share a header. Keyboard Enter/Space behaves like click.
- A compact 'Radar order' reset restores response order. On stacked/mobile rows,
  show a labelled Sort by selector with the same keys and direction control;
  do not leave sorting accessible only through hidden headers.
- Show 'Sorts these N candidates' near the control/summary. This reorders the
  loaded candidate set, not the whole market or the backend eligibility/ranking.
  Do not fetch, alter server sort parameters, or widen the candidate set.
- Filter companies and then sort; preserve the selected sort while typing and
  while refreshing/changing server filters. Reset uses the newest response order.
  Keep sort state in the hub's Chatter view state so Research -> Back restores
  it. No new backend persistence or requirement for cross-session storage.

### Comparator contract

Use a pure stable helper on a copied array; never mutate board.rows or cached
watch rows. Equal keys retain current response order. Missing/invalid values
stay LAST in both directions, including when direction reverses.

Company sorts by ticker using locale-aware numeric comparison, not truncated
company text. Attention uses row.ratio, never recomputes a guarded ratio.
Voices uses authors. Sources uses the number of unique platforms from validated
activity_sources through the existing presentation helper: missing is unknown,
empty is measured zero; never fall back to legacy sources. Tone uses raw
bullish/(bullish+bearish) under the same validation as the display; zero directional
sample is unknown, never 0% bullish. Do not compare formatted percentages or the
minimum-width bar geometry. Price uses the displayed usable quote price; absent
currency or unavailable quote is unknown. For multiple known currencies, group
by currency code (label this in the sort explanation), then sort price within
currency, rather than pretending USD and EUR are converted. Today uses the raw
usable price_move fraction, with null unavailable and zero a valid value.

### Files and acceptance

Modify hub/Chatter.tsx, hub/Hub.tsx only as needed to retain Chatter sort state,
hub/hub.css and their focused tests. Add hub/chatterSort.ts and
hub/chatterSort.test.ts for comparator logic (or a comparably focused existing
helper). Preserve selection/query contracts and row navigation/disclosures.

Tests must demonstrate numeric ordering (2 vs 10), both directions, ties, nulls
last in both directions, all-no-tone rows, two distinct raw tone fractions with
the same rounded label, active platforms vs concrete feeds, mixed currencies,
input array unchanged, filter+sort composition, refresh retains selection,
Research/Back restores selection, and Radar-order reset. Check clicking a sort
header produces no board request. Verify desktop keyboard/accessible state and
mobile selector parity. Capture the sorted fixture at 1440 and 390, inspect it,
and confirm arrows/controls do not break accepted density/column widths.

Return this with the same VC1-close preview and independent review. No merge,
push, deployment, capture enablement or root promotion authorized.

## Ninth return — VC1-close and sorting accepted for owner review, 2026-09-10

Verified candidate 31ae58a on codex/radar-release-candidate; no changes reported
by Git status before this documentation edit (ignore/cache permission warnings).
Read the new closure/review ledger sections and current handoff; inspected the
sorting comparator and desktop/mobile sorted captures. Fresh focused verification:
chatterSort.test.ts plus Chatter.test.tsx, 78 passed, 2 files. The broader 527/403
suite results and 128 browser checks are Claude's recorded evidence, not freshly
rerun here. No backend or production operations performed by Codex.

Accept VC1-close and sortable Chatter. No further implementation gate is raised
by A-D below. Next action is the owner's visual review of the corrected sortable
preview, then a separate deployment decision if accepted. Do not redispatch
completed work or create another closure loop for discretionary refinements.

A. Accept the documented currency/price tuple ordering in both directions for
this release. Currency groups reverse too; price remains sorted within each
currency, with unknowns last. This is a reasonable disclosed interpretation of
the contract, not currency conversion. No comparator change required. Stable
collator-equivalent ticker ties likewise comply with the tie contract.

B. Accept the remaining 860px control sizing/padding as harmless responsive
adaptation for this delivery. The requested table breakpoint isolation is met.
Inert generic flex alignment declarations are not a runtime defect while the
Chatter cells remain block layout. Clean them when that CSS is next edited;
do not change tested styles solely to eliminate inert declarations now.

C. Keep Activity/Watching duplicate desktop labels as a named accessibility
follow-up for those pages' next UI pass, with real populated table/stacked checks.
No need to hold the corrected Chatter for an unchanged out-of-scope issue.

D. Keep sort in view memory for now, as explicitly scoped. Shareable ordering
can accompany future saved views; use a separate validated client view parameter
then, never overload backend ranking selection. No URL work in this release.

The screenshots show the core correction and sorting in place. The explanatory
sorting block could become more compact in a later polish pass; this is not a
new blocker. Owner visual acceptance is still open. This near-term milestone
does not replace the original A/B ambition or authorize deployment.

After owner acceptance: prepare a concise current-SHA deployment delta using the
existing operational procedure, not the old first-migration assumptions. This
update adds no migration beyond the already deployed a7c31f0b52d4. Check remote
and target drift, matching build, additive activity_sources compatibility and
current migration head; retain capture off and the original /radar/ route.
Owner authorization to merge/push/deploy is separate; none is granted here.

## Owner approval — VC1 deployment, 2026-09-10

The owner visually accepted the sortable preview ('Looks good just like I
imagined'), then authorized proceeding with the proposed merge/push/deployment
('lets go ahead') after confirming historical snapshot capture is for later.

Claude is authorized to merge/push the reviewed VC1 candidate 31ae58a plus
reviewed documentation-only ruling updates and deploy the updated hub in the
next suitable window. Preserve /radar/ as the original page and keep observation
capture off. Include the established fresh backup, temporary service stops,
matching build, restart/smoke verification and code-only rollback if needed.
No capture enablement, root promotion, OT1 cleanup, schema downgrade or live
restore is bundled into this authorization.

Execution must use current facts: production was reported at ba1c381 and already
at migration head a7c31f0b52d4. This update introduces no new migration. Do not
reuse the first release's 'both tables absent' preflight or drop/stamp anything
to recreate it. Verify remote/target drift before merging and deploying, record
the exact merge/deployed SHA, and assess unexpected code/schema changes before
continuing. Retain the existing migration chain for routine upgrades/rollback.

Claude should prepare the concise deployment delta and execute within this
approval without asking for the same approval again. Announce the actual window,
follow the accepted service ordering and backup procedure, then verify old Radar,
hub assets/sorting, current activity_sources and tone on real data, service health,
unchanged migration head and capture off. Do not mint an owner login session;
use existing authorized verification methods. Report any authenticated checks
that need the owner's session honestly. Record results in RELEASE-RECORD.md and
HANDOFF.md. Production has not changed merely because this approval is recorded.

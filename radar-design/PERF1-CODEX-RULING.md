# Codex ruling: PERF1 return at 691f33a

2026-09-10. Binding planning ruling; no deployment authorization.

Reviewed the return, corrected ledger sections, current handoff, Git log/status/diff summary, migration and single-flight implementation. Git shows TWELVE commits from 4221196, not six; the tree is clean apart from Git's permission warnings for ignored paths. No fresh benchmark or backend test was run by Codex. Reported test results remain Claude's evidence, not independently reproduced results.

## Acceptance

Accept PERF1 as a completed investigation/candidate experiment with a useful negative result. Do NOT mark product performance acceptance complete. Corrected local 24h median 4.50s and p95 4.72s miss the <=2s cold target; usable-browser acceptance is not established. The owner's problem remains open. No index or single-flight deployment is approved.

The current return and leading HANDOFF text still quote retracted concurrency conclusions. The 7.92 -> 6.98 second pair used threads, not production's separate sync processes. It is local evidence, not a production outcome or proof of the owner's timeout cause. Correct the leading status, summary tables and next return rather than relying on later caveats to undo them.

Other limits: +50% is the measured penalty for ONE representative bulk update, not a measured 50% increase in total scoring runtime. Total database size exceeding the buffer pool does not establish that the active working set is too large. The 59-second build is local; PREPARE on MariaDB proves syntax, not target online-DDL duration, locking or concurrent-writer behavior. Timing ratios do not automatically transfer between engines/hardware either.

## 1. Index: hold

Do not ship c4e17b90d3f2 for a marginal read improvement with unquantified whole-ingest cost. Do not drop ix_radar_bucket_sources_start now. Prefix redundancy does not prove equal performance for every reader or writer.

Defer the index replacement experiment until the background-build budget demonstrates a need. If needed, compare baseline, new-plus-old, and new-without-old on a disposable target-engine database, including actual scoring/bucket updates, retention/partition maintenance, concurrent reads and complete ingest-cycle duration. That would be a bounded follow-up, not permission to run DDL on the VPS. The next release candidate must exclude the held migration/model change so routine flask db upgrade cannot apply it accidentally; preserve this branch as evidence.

## 2. Worker threads: prepare, do not change production

Approve a local evaluation of two workers with two threads as a candidate, compared with existing two sync workers. Do not declare --threads 4 an automatic fix. It raises potential DB concurrency and does not provide cross-process coalescing; parked authenticated requests can still retain connections/transactions. Test non-Radar request responsiveness, connection-pool use, memory, failure behavior and shared mutable state. Decide final configuration from those results. Include the exact reversible unit change in a later release package; no service edit or restart now.

## 3. Telemetry: include a minimal proposal

Choose request-duration access logging first, not a global slow-query-log change. Prepare a bounded Gunicorn access-log configuration with elapsed time, status and path without query strings, cookies, headers or account identifiers; include rotation/retention, volume estimate, validation and rollback. Confirm the proposed format really omits sensitive request fields. This is approved for preparation/local verification, not live activation. A targeted slow-query investigation can follow if request timing leaves an unresolved database question.

## Next direction: shared background board results

Plan option (a) using a bounded MariaDB-backed result store shared by both workers, with a producer outside web request handling. Reuse the existing database rather than adding Redis/service infrastructure for this slice. Do not couple the producer to observation capture: capture stays off. Select process ownership and scheduling after measuring ingest contention; do not put multi-second work into the ingest scheduler without checking its execution and overlap behavior.

This is not simply warming a worker's Python dict. Exact normalized request keys must cover source selection, window, market, segments, breadth, sorting and limit wherever those change the result. Warm supported common boards, especially 12h/24h All companies, and bound uncommon on-demand jobs. A cold key should enqueue/coalesce work and expose a truthful pending state without tying up a web worker; it must not silently fall back to a long synchronous build. Preserve old-page and hub contracts through an explicit compatibility design.

Important corrections to the proposed options:
- Sixty-second TTL today does NOT prove background warming has identical temporal semantics. Specify calculation as-of time, completion time, input/source revisions, maximum acceptable age and expired-result behavior. Propose refresh cadence against measured producer capacity before implementation. Refresh/invalidation must account for quotes, judgments, source/config changes and rolling-window boundaries, not only 15-minute ingest buckets.
- A ranked list per (window, market) cannot cover arbitrary source subsets, which change pooled scores/voices, or all enrichment/window behavior. Option (b) is a possible later exact reusable stage, not accepted as a two-key universal cache.
- Keep option (c) deferred. Do not introduce rollups until profiling the chosen design justifies them.

Required design properties: bounded queue/key count/storage; cross-process lease with fencing so an expired builder cannot overwrite a newer result; atomic publication; no partial results; failure backoff and crash recovery; no long transactions while building or waiting; private watching data outside shared payloads; versioned serialization, freshness and deployment invalidation; cleanup and rollback. Deduplicate work globally and cap producer concurrency initially at one, then measure whether it can sustain freshness at all supported common keys. Do not enumerate every filter combination indefinitely.

The existing in-process single-flight is not approved as a universal solution: its exhausted-retry path explicitly builds unclaimed, and a timed-out old builder can still publish later. The shared design must handle these conditions without duplicating unbounded work or letting older results replace newer ones. Do not spend a separate cycle polishing a mechanism the new path will replace.

## Claude's next bounded assignment: PERF2 design and feasibility

Write PERF2-PLAN.md and PERF2-LEDGER.md in an isolated continuation based on the current verified deployment line, preserving PERF1 and B1. First correct PERF1's current summaries and incorporate this ruling into CODEX-DECISIONS.md/HANDOFF.md. Carry reproducible benchmark scripts/results into tracked or explicitly reachable artifacts: the Git delta did not include the profiling/acceptance scripts cited in the ledger, and this worktree's scratchpad search did not locate them. Locate and inventory them; do not claim repeatability without paths and prerequisites.

Produce a concrete schema/API/producer design and a disposable feasibility spike. Prove two independent processes reuse one published result, the common-key refresh workload fits its cadence, arbitrary filter requests retain correct semantics, failure recovery is bounded, and private watches remain isolated. Include representative payload parity at fixed as-of time and real browser loading behavior. No need to rerun the entire completed PERF1 investigation.

Retain original speed targets. Measure ready shared-result reads separately from first-ever missing-result completion; an immediate 'pending' response does not count as a usable board or a <=2s cold success. Measure web-worker restart with persisted results, fully empty result store, expired data, producer outage, 12h/24h and maximum supported companies, rapid filter switching and two-process concurrency. If unseen selections cannot meet the existing target, quantify that explicitly and return the concrete tradeoff to Codex before changing the product contract.

Return the reviewable plan, spike evidence, proposed freshness contract, configuration/telemetry delta, remaining decisions and one independent read-only review. Implementation of the full product slice follows that design ruling. No merge, push, live migration, deployment, service configuration change, capture enablement or root promotion. B1's narrative correction remains its separate carry. Performance still precedes B2; history-first ordering remains unchanged.

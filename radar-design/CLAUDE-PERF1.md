# PERF1 — make Radar usable at production data volume

Codex owns planning; Claude implements. This task takes priority over B2 and further visual expansion. The owner reports unusable waits on the VPS, especially 12h/24h and All companies. The defect predates B1 and affects the original Radar too. Do not treat a small seeded preview or a cache hit as acceptance evidence.

## Start and continuity

Start from C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1, branch codex/radar-b1, last reviewed HEAD df139ff. Read its HANDOFF.md, B1-LEDGER.md and latest CODEX-DECISIONS.md completely. Verify Git state; preserve Codex's uncommitted documentation and all completed B1 work. Establish an isolated performance worktree carrying the relevant current state; record its exact base and any deployment differences. Never seed or alter TE1 or another workstream's database.

Create PERF1-PLAN.md, PERF1-LEDGER.md and update HANDOFF.md in that execution workspace. Copy this brief there. Record completed steps, commands, evidence, unresolved findings and the next action. Do not redispatch completed foundations, release or B1 tasks. B1's remaining price-narrative correction remains a separate deployment carry.

## P0 — establish the actual bottleneck

Use existing authorized read-only VPS access for bounded diagnostics. No target code/configuration/schema edits, service restarts, cache flushing, synthetic load tests or authentication bypass. Do not mint an owner session. If authenticated browser timings are unavailable, report that limit and use authorized server-side measurements; do not claim they measure the browser experience. Keep logs free of credentials and personal post content.

Record current deployed SHA, engine/version, relevant indexes, worker configuration and dataset cardinalities. Identify what All companies means in the actual query parameters; distinguish segment selection from row limit. Compare original /radar/ and /radar/hub/ on equivalent inputs, and distinguish deployed VC1 from local B1.

Measure serial samples of default, 12h and 24h with All companies, ordinary and maximum supported row limits. Capture initial navigation, filter switching and selected-ticker loading separately. Separate HTML/TTFB, board API, detail API, transfer size and browser rendering. Record cache state honestly: first observed request is not necessarily a cold request. Reproduce cold application caches locally against a safely restored, production-scale disposable database with genuine constraints and indexes. Verify database identity before every write or backend test.

Instrument locally: SQL count and cumulative/worst query durations, rows materialized, Python stage timings, serialization, memory and query plans for the measured expensive reads. Reproduce retained-history and candidate-count scale, not just five mock companies. Record exact fixture characteristics and differences from VPS. Avoid executing expensive diagnostic queries repeatedly on the VPS.

Source leads found by Codex, NOT proven root causes:
- board.build calls leaderboard.build_rows with limit=None before final selection. Establish which work ranking genuinely requires before moving limits.
- leaderboard enriches survivors with quote views, moves and historical sigmas; measure these and voice counting.
- board._entries adds hourly counts/prices, triplets and tones. Measure their SQL and Python cost and which consumers require them.
- routes/api.py caches boards per process for 60 seconds; builds run outside the lock, so concurrent misses can duplicate work. TTL starts from request time. Verify actual worker/cache behavior.
- build_payload adds uncached per-account watched rows. Include realistic watching lists without sharing private results between accounts.
- inspect frontend cancellation, redundant requests, refreshes and stale-response races. A fast shell alone does not satisfy this task.

The earlier R3 activity-summary memory fix is complete and unrelated; do not redispatch it.

## P1 — fix the measured cause

Once profiling identifies a credible mechanism, write the bounded implementation plan and implement locally. Prefer reducing unnecessary database/Python work at its owning layer. Caching, precomputation, indexes or API splitting are choices to justify with evidence, not a predetermined solution. If a migration is necessary, include engine-compatible rehearsal and recovery; applying it to production is not authorized.

Preserve full filter/ranking/sorting semantics, source-version rules, distinct voices, tone denominator/null contracts, instrument identity, timestamps and account isolation. No silent smaller universe, shorter window, sampled counts or removed charts to hit a target. Do not apply a top-N limit before calculations needed for globally correct sorting. Keep old Radar and B1 consumers compatible. Freshness must remain explicit; stale data must not be presented as a newly computed result.

While loading, keep controls responsive and make pending filter state unambiguous. Older results may remain visible only with clear updating state; a late response must not overwrite the newest selection. Do not disguise backend latency with animation.

## P2 — acceptance and independent review

Targets for production-scale local evidence: cold board API p95 <=2 seconds; warm p95 <=500 ms; requested board usable in the browser <=3 seconds under documented network conditions; local sort/mode interactions <=100 ms where no new server result is needed. These are product acceptance targets, not claims about current performance. Report sample counts, median, p95 and maximum with at least 20 serial local samples for each critical 12h/24h All-companies case. Distinguish cold application caches from database buffer caches. If a target cannot be met, return the measured limiting factor and a concrete next option; do not silently relax it.

On the disposable environment, test two simultaneous readers and rapid filter changes for bounded memory, duplicate work, stale responses and errors. Match VPS worker topology where possible. Compare before/after on the same dataset, configuration and fixed input time; verify semantic payload parity apart from explicitly reviewed changes. Test realistic watches and empty/null/fallback cases. Run focused regression tests and required build checks; classify baseline failures honestly.

Use one implementation worker followed by an independent read-only review. Resolve findings and record evidence. Return exact SHA, clean/dirty state, bottleneck proof, before/after table, correctness tests, remaining limits and deployment carries. Production confirmation after deployment remains a distinct step; local success alone does not prove the live fix.

No merge, push, deployment, production migration, capture enablement or root-route promotion is authorized by this brief. Return the reviewable patch and release delta to Codex.

## Roadmap priority

PERF1 comes first. Preserve B1's completed design work and open acceptance items. After performance acceptance, finish B1 review/carries and plan its release; then B2 Overview and the existing history-first/data-coverage roadmap. History remains ahead of portfolio and full news. Capture remains off. This priority supersedes older next-action paragraphs; it does not reopen completed tasks.

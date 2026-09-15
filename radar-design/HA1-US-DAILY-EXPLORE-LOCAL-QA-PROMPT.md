You are Radar's Implementer / local QA operator. Complete HA1-US-DAILY-EXPLORE-LOCAL-QA.

This is the owner's bounded authorization, when handed to you, to make the named hatch fix, provision a NEW disposable local HA1-only environment, and run its local verification. It does not authorize deployment, production access/data copying, providers, commits/pushes, capture, or modifying existing databases/services/registries. Do not dispatch subagents/workers.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Branch codex/radar-ha1-us-daily-explore; expected base/HEAD 1ac39fe4e1a5dd7d04830e96a96563183687b447; no upstream; existing work uncommitted.

Read both handoffs and HA1 ledger completely; WORKFLOW.md, HA1 spec/plan, REVIEW-2-RULING, CORRECTION-2 assignment/return/evidence and CORRECTION-2-RULING under radar-design. Verify Git with per-command safe.directory, preserve existing dirt and unexplained downloaded_files/dashboard.lock. Do not repeat completed product work.

1. Narrow product fix:
Correct the CSS cascade so partial count bars retain url(#rh-an-hatch), full bars remain solid and text disclosure remains. Edit only analysis.css and the smallest meaningful focused regression (AnalysisChart/test or analysisCss/test as needed). Run relevant tests and production build/typecheck. Record source/build fingerprint AFTER build; refuse drift before/during QA. No redesign or unrelated U12/U13 changes.

2. New isolated environment:
Inspect available local MariaDB/runtime tooling without using existing database contents. Establish a new HA1-only instance/data directory, database, user and dedicated registry at unused loopback ports. Never use DB3306/3399, preview5021/5033, B1C/promotion targets, main/other worktrees or existing data directories. Prefer temporary non-service processes; Windows background processes hidden. Do not stop another process or modify global services/configuration. Do not download/install system software or use Docker/network pulls without a separate authorization if required tooling is absent.

Record exact executable/version, data directory, host/port/database, ownership, registry, credentials handling and cleanup commands before starting. Do not log secrets. Initialize schema from candidate migrations only in the newly created database; synthetic fixtures only. No production snapshot or provider data. Preserve existing gate checks; use independently identified HA1-only target/registry, never bypass a failing gate. If no safe local runtime is available, return the exact blocker and concrete setup requirement instead of improvising a protected target.

3. Runtime verification:
Run the gated HA1 API suite and corrected probe against this exact target. Record engine/version/hardware, <=4 data SELECTs, EXPLAIN, <=43,008 rows/64 sources, 43,009/65-source refusals, <=1MiB response, <=32MiB incremental reader allocation, twenty warm full-request p95<=1s.
Verify fractional/sub-second statement timeout, 503 translation, same-connection recovery and pooled health. Separately record interruption delay, reader duration/overshoot and full-request duration. Five seconds is the reader/resolver budget, not HTTP wall-clock termination. One-second diagnostic grace is not acceptance; return measured overruns for Mastermind ruling.
Prove loopback non-admin 200 and FULL_ACCESS_HOST policy 403 using LOCAL test-client host simulation only; never contact the production host.

Seed owned preview fixtures and start only the new gated loopback candidate server. Verify source/build/runtime/target identity before authenticated checks. Use Python Playwright for actual-app verification and inspect resulting screenshots. Cover C02/C11/C13-C16 per SPEC/PLAN and corrected harness: routes/alias/legacy/bookmarks, pin/Back/refresh, no recurring Analysis board poll, invalid dates/errors/identity, hatch vs solid bars, adjacent price lines and gaps, keyboard, touch/scroll, contrast, zoom and alignment at 1440/1920/768/390/320.
130s polling observation must allow progress updates at intervals <=60s. Treat 2 CSS px alignment and 1.5s pin settle as test settings only. Viewport/DPR emulation is not proof of real 200% browser zoom: obtain actual zoom evidence or explicitly keep that item open.
No mocked response may be cited as real backend evidence; distinguish injected error-state UI checks from engine tests.

4. Failure boundaries:
Small harness/selector fixes needed to make intended assertions valid are allowed, with focused tests and exact disclosure. Never weaken assertions or budgets to get green. Other product defects, security/isolation failures, unexpected plan shapes, material performance failures or unavailable runtime prerequisites return to Mastermind with evidence. No automatic broad fix/review loop.

5. Cleanup/return:
Finally clean exact owned fixtures, preserve failure reports/manifests if cleanup is incomplete, stop only processes created by this assignment. Preserve the new local data directory and logs for reproducibility; no recursive deletion of existing paths. Record residual state and exact safe teardown instructions. Do not leave an unreported listener or claim cleanup without verification.

Write radar-design/HA1-US-DAILY-EXPLORE-LOCAL-QA-RETURN.md and artifacts/ha1/local-qa/ evidence. Update ledger, both handoffs and state/assignments with exact Git/dirt, environment ownership, per-gate results, viewed screenshot paths, timings, open findings and next action. Capture OFF/shared boards ON/migration b7e3f9c1a2d4 remain prior release-attributed; local schema findings do not update production facts.

Stop at Mastermind return. No merge/commit/push/deployment. Include a fully populated COPY/PASTE return prompt:

You are Radar's Mastermind / Overview. Assess HA1-US-DAILY-EXPLORE-LOCAL-QA.
Workspace/branch/base/HEAD/upstream: [verified]
Dirty ownership and hatch/harness changes: [exact files]
Local environment: [version, executable, data path, target/registry, owned processes, no secrets]
Binding artifacts: [absolute paths]
Fresh tests and per-gate C02/C11/C13-C16 results: [commands/results]
Performance/deadline measurements: [full values and overshoot needing ruling]
Browser evidence: [viewed screenshots, real zoom vs emulation, injected vs real responses]
Unresolved defects/deviations: [specific evidence]
Cleanup/residual state: [verified fixture/process status and retained directory]
Protected state/actions not taken: [no production/provider/commit/deploy]
Updated continuity/evidence: [absolute paths]
Requested decision: assess actual runtime results and hatch fix; rule on remaining findings and release readiness. Deployment remains separately unauthorized.
Do not implement/deploy or dispatch workers; verify repository evidence.


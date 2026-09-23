You are Radar's Implementer. Complete HA1-US-DAILY-EXPLORE-CORRECTION-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Branch: codex/radar-ha1-us-daily-explore
Expected base/HEAD: 1ac39fe4e1a5dd7d04830e96a96563183687b447; no upstream; existing work uncommitted.

Read both HANDOFF.md files and radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md completely. Read WORKFLOW.md and HA1-US-DAILY-EXPLORE-{SPEC,PLAN,IMPLEMENTATION-RULING,IMPLEMENTATION-RETURN,REVIEW-RETURN,REVIEW-1-RULING}.md under radar-design, plus artifacts/ha1 implementation and review evidence. Verify Git path/branch/HEAD/status/diff/log against them. Preserve unrelated dirty work and resume only these corrections.

Authorized: HA1 code/test/harness corrections in this candidate, DB-free tests/typecheck/build, correction evidence and continuity. No workers/subagents, database/provider/production access, API integration or DB/preview harness execution, browser preview, provisioning, registry/service/migration changes, commits, pushes or deployment.

Complete these corrections:
1. P1-1/R1: replace broad ZQ% deletes in probe/API fixtures with exact created identities, collision refusal before mutation and try/finally cleanup. Never adopt or delete pre-existing matching rows.
2. P1-2/R2: capture scalar admin ID inside its live app/session context; keep engine access in app context. Fix EXPLAIN using actual named reader SQL/binds or matching driver SQL/positional parameters. Do not wrap driver %s SQL in sa.text.
3. P1-3: inject database failure through SqlStore._rows so the API test exercises production exception translation. Do not weaken handling to make the test pass.
4. P2-1/R5: price lines connect only adjacent observed calendar dates in the same provenance/adjustment regime. Missing modeled-closed weekend dates break lines. Correct contradictory tests.
5. P2-2/P2-6: preserve malformed raw date strings through ticker resolution and canonical pinning. Keep them visible/editable even when native date inputs sanitize them. Never fetch a guessed default for an invalid explicit range. Test ticker-only and pinned links.
6. P2-3: use monotonic remaining reader budget and per-statement timeout <=min(2 seconds, remaining five-second budget), with supported fractional MariaDB syntax. Refuse expired statements and check materialization/reduction. Add fake-clock regressions; disclose connection-wait/cancellation limits pending runtime proof.
7. P2-4: identity exclusions count source-bucket rows, not time slots. Correct labels/tests and document units while preserving compatibility where practical.
8. P2-5: Analysis controls, including range/table buttons, must reach 44px touch targets at narrow widths.
9. P2-7: do not pin cached resolve IDs before fresh resolution settles. Test seeded stale cache, remapping, reselection and response races; preserve server revalidation.
10. P3 integrity: keep unaligned invalid rows outside the 96-slot partition; expose separate excluded-row counts and uncertainty. Exclude pre-first_seen-only sources from the represented post-identity source denominator while retaining exclusion totals/disclosure. Never claim known historical source-set completeness.
11. P3 accessibility/layout: remove unsupported aria-selected on ordinary rows; name focusable table regions; limit live announcements to concise status. Align chart dates/day controls and separate conflicting SVG/HTML empty-state styles. Keep US-primary/USD identity visible in Analysis on mobile. No global header/chart redesign.
12. R3: assert query/row/source/payload/memory/latency budgets. Guarantee fixture/overflow-row/temporary-setting restoration on failure. Separate 65-source low-row rejection from 43,009-row rejection with <=64 sources; an intentional off-grid timestamp can supply the sentinel since 7*96*64 aligned unique rows fill the cap. Measure incremental reader allocation including materialization separately from latency. Verify timeout hygiene on the same physical connection; handle MariaDB SLEEP semantics without claiming uncancelled queries succeeded.
13. R4/C11/C16: gate preview tooling before app/connection use; verify candidate server and exact independently registered HA1 DB identity before mutation/authenticated checks. Provide owned preview fixture lifecycle, real assertions and all SPEC C16 states including keyboard/mobile/zoom/errors/ranges/identity. Add ordinary authenticated non-admin access coverage. Inspect pre-existing suites selected by local_runtime before retaining them. Record a dated correction to the unsupported claim that verify_preview already refused safely; preserve historical reports.

Pinned reads must revalidate the chosen eligible current mapping. No extra scan for a later second primary is required; resolver ambiguity rejection remains required. Do not claim global uniqueness from a pinned read.

Preserve SPEC: actual authenticated dark hub; current ID-pinned native-USD US primary; independent daily closes and retained UTC counts; 1–7 completed UTC days/default seven; missing/zero/truncation/config/overlap/identity/provenance disclosures; modeled calendar only. No returns, z aggregation, replay, tone, provider/capture/schema changes or wider history.
Budgets: <=4 data SELECTs, <=43,008 rows with 43,009 sentinel, <=64 sources, <=1MiB response, <=32MiB incremental reader allocation, <=2s per statement and five-second reader budget, browser eight seconds, warm local MariaDB p95<=1s over 20 measured requests. Runtime proof remains OPEN.

Edit only existing HA1 implementation/integration, corresponding tests and scratchpad/ha1 scripts as required. Small DB-free HA1 harness helpers/tests are allowed. Preserve original spec/plan, reviewer reports/reproductions and unrelated code. Record additive contract clarifications explicitly.

Run affected DB-free ha1_unit and focused frontend tests, typecheck/build and git diff --check; add meaningful behavior/safety/SQL-compilation regressions. Do not execute test_radar_analysis_api.py or DB/preview scripts even if a target appears. Do not claim integration, visual or performance acceptance from mocks. Prior pending.test.tsx baseline failures remain attributed and outside scope.

Write radar-design/HA1-US-DAILY-EXPLORE-CORRECTION-1-RETURN.md and artifacts/ha1/correction-1/ evidence. Update ledger, both handoffs and assignment/state notices with exact Git state, dirty ownership, finding dispositions, commands/results and open gates. Protect main/other worktrees, B1C DB/5021, default DB3306, prior promotion DB/3399/5033 and artifacts. Capture OFF/shared boards ON/migration b7e3f9c1a2d4 are release-attributed, not fresh probes.

Stop after corrections and DB-free verification. Mastermind then assesses; owner selects independent focused re-review. DB/preview execution remains held until corrected harness review and separately authorized disposable environment. No dispatch or release.

FINAL RESPONSE MUST INCLUDE THIS FULLY POPULATED COPY/PASTE RETURN PROMPT:

You are Radar's Mastermind / Overview. Assess HA1-US-DAILY-EXPLORE-CORRECTION-1.
Workspace: [absolute path]
Branch/base/HEAD/upstream: [verified values]
Git status/dirty ownership: [exact files/groups, preserved prior work, no commits/pushes]
Binding artifacts: [absolute spec/plan/ledger/review/ruling/correction-return paths]
Completed corrections: [each finding and evidence]
Tests executed: [exact commands/results/evidence paths]
Attribution: [fresh execution vs static reasoning vs prior reports]
Unresolved findings/deviations: [explicit list]
Open gates: [C02/C11/C13/C14/C15/C16 runtime portions; no fabricated runtime proof]
Protected state/actions not taken: [details]
Updated continuity/artifacts: [absolute paths]
Requested decision: assess corrections and prepare independent focused Reviewer/QA prompt; retain DB/preview hold until harness review and separate environment authorization.
Next action: focused review, not provisioning/deployment.
Read continuity and verify Git/artifacts. Do not implement/deploy or dispatch workers.

---

Status notice (appended 2026-09-15; the prompt above is unchanged): DISPATCHED and RETURNED. Implementer return: HA1-US-DAILY-EXPLORE-CORRECTION-1-RETURN.md; evidence: artifacts/ha1/correction-1/evidence.md. Runtime gates remain open; next is Mastermind assessment.


# Current status — independent final review COMPLETE

The owner supplied the completed independent review on 2026-09-14: no material issues found; the implementation satisfies the binding Human Chatter ranking contract. Implementation and independent review are COMPLETE for this uncommitted candidate. No repeat implementation/review assignment is open.

Independent reviewer-reported fresh evidence: backend focused suite 29 passed; frontend focused suite 4 files / 125 tests passed; git diff --check passed. The reviewer reported preserving all dirty files and making no code or documentation changes. The Product Overview planner verified current Git state and read the handoff/plan/ledger/return, but did not rerun those tests or independently reproduce the reviewer results. The production build/typecheck pass remains implementer-reported evidence, not an independent review build.

Residual verification limits remain explicit: direct/shared producer, API and parity integration could not safely run because only protected localhost:3306/personal_apps was available. Do not bypass the gate, use B1C's database or create an improvised target. No safely isolated actual-app preview was available, so no screenshots exist. The 6.5-hour price-period assumption remains unaudited and outside scope. Review completion does not mean these gates passed or that release readiness was demonstrated.

Current candidate: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-human-chatter; branch codex/radar-human-chatter; verified HEAD/base a161dc3793aede70b31e1cb1cf851607f918881f. Implementation and planning changes remain uncommitted. Git's ignore-file/.pytest_cache permission warnings limit untracked enumeration. Existing dirty implementation and historical B1C files were preserved; this status reconciliation changes planning documents only.

Product recommendation: owner approval for a scoped local commit of the reviewed candidate and its planning evidence. Commit, integration, push and deployment are NOT authorized by this record. Keep the integration/visual gaps visible for any later integration/release decision; no automatic test/review loop. Historical analysis remains next after disposition of this candidate. Capture remains OFF. No migrations, root promotion, B1C/PERF3 changes, port-5021 use or production access.

Contract unchanged: default membership/order is independent of price, quotes, freshness, direction and session; price remains visible and explicitly sortable within the selected candidates; existing mention_z with no new score/weights/boosts/predictive claims; original /radar/ defaults unchanged.

This notice supersedes older open-review, worktree-creation and next-action instructions below. Detailed historical evidence is retained.

---
# Human Chatter ranking — binding product brief

Date: 2026-09-14. Status: implementation and independent final review COMPLETE; uncommitted candidate with recorded verification limits.

## Goal and scope

The hub Human Chatter default selects and orders candidates by unusual human discussion, independently of price. Price remains visible and explicitly sortable. Original /radar/ ranking remains unchanged. Use the existing mention_z calculation provisionally; do not invent a composite score or claim predictive value.

## Continuity and authority

This repository copy is binding; the earlier visualization-folder copy is a delivery snapshot. Progress lives in HUMAN-CHATTER-RANKING-LEDGER.md. These planning edits are uncommitted: explicitly carry this plan, ledger and current handoff/roadmap/history documents into the new worktree. Owner selects the primary agent/model. Authorized subagents must use exactly the same model, including nested agents; no different or higher-cost models. If the match cannot be verified, do not delegate. No application changes are authorized in the existing B1C worktree.

## Verified baseline

Read-only inspection: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1c, branch codex/radar-b1c, HEAD a161dc3793aede70b31e1cb1cf851607f918881f. Recorded deployed SHA 200c51cc402e053575bf9e0008db597ea27b36a5. Git reports no tracked edits and an untracked radar-design/artifacts/b1c-resume/missing-bars-local.png; ignore/cache permission warnings limit untracked inspection.

leaderboard.py build_rows orders divergence-present rows first, then divergence, then mention_z. board.py build obtains all survivors, applies filters and explicit sorting before truncation. Existing SORT_KEYS has no mention_z sort. hub/Chatter.tsx preserves server order by default; hub/chatterSort.ts only reorders returned candidates. board_keys.py includes the server sort in the shared cache key. These are source observations, not runtime verification.

## Ranking contract

Add an explicit server sort key `chatter` that sorts finite mention_z descending, missing/nonfinite last, then finite mentions descending and ticker ascending for deterministic chatter-only ties. Zero remains a valid measurement. Existing eligibility, relevance and duplicate safeguards remain; verify that no price gate affects default membership. Do not add source/breadth/quality weights. Preserve source, window and market filters.

Request chatter descending for the hub Human Chatter candidate set before the top-N limit. Do not change the global leaderboard default. Keep frontend alternate sorts as explicitly labelled sorts of the selected candidates; returning to default restores server order. Do not imply Attention ratio and mention_z are the same measure.

Label default `Unusual activity`; explanation: `Discussion ranked by how unusual it is against its baseline. Price movement is shown separately.` Measured nonpositive rows remain below positive rows. All measured rows nonpositive: `No elevated discussion in this selection.` Unknown baseline: `Not enough history to measure unusual activity.` Do not claim quiet when coverage is missing. Reuse existing accessible presentation; no redesign.

## Historical execution checklist — closed; current ledger governs

- [ ] In a new isolated feature worktree based on the verified planning HEAD, preserve a copy of this brief, a ranking ledger, and a root HANDOFF.md. Do not reuse or modify the running B1C preview workspace.
- [ ] Trace hub request/bootstrap, query validation, producer and cache paths. Inspect mention_z computation and its validity contract. If materially invalid, return evidence before redesigning its formula. Record any visible price-calculation concern separately, without expanding this patch.
- [ ] Add meaningful failing backend tests for price-invariant membership/order, deterministic ties, signed/missing/nonfinite scores, and a candidate beyond the old top-N boundary. Implement explicit chatter sort before truncation using the existing board path. Keep legacy defaults and divergence calculations intact.
- [ ] Carry the explicit sort through hub fetch, initial payload matching, refresh/navigation and shared/direct paths. Ensure a legacy cached/bootstrap board cannot masquerade as a chatter-sorted response. Preserve PERF3 producer architecture; no synchronous request-time fallback or migration.
- [ ] Update hub default/reset copy, workspace/table consistency and truthful low-activity/missing-baseline states. Preserve existing explicit client sorts and price display. Add focused UI/request tests.
- [ ] Run focused backend ranking/query/cache/producer parity and legacy compatibility checks, affected frontend suites and build/typecheck. Verify actual-app desktop and phone presentation using Python Playwright if a safely isolated preview is available; inspect screenshots. No production claims from fixtures.
- [ ] Return exact workspace/branch/HEAD, changed files, test commands/results, evidence locations, limitations and one independent-review handoff. Update ledger and HANDOFF. Stop; owner selects reviewer.

## Acceptance and exclusions

Changing only prices, price direction, quote presence/freshness or session status cannot change hub default membership/order. Positive surprise precedes quiet activity, missing measurements remain unknown, ties are independent of incoming divergence order, and sorting precedes truncation. Shared and direct responses agree; existing /radar/ and legacy cache semantics remain intact. No deployment, push, migration, capture activation, root promotion, provider work, B1C latency work, new prototype or unauthorized model selection. Protect main checkout, PERF3 scripts and all other worktrees. Capture remains OFF. Historical analysis follows this bounded interruption.

## Planning ledger

- Product direction: COMPLETE, owner approved.
- Source-path assessment: COMPLETE, bounded read-only inspection above.
- Implementation: COMPLETE.
- Independent review: COMPLETE; reviewer-reported 29 backend / 125 frontend passes and diff check. Integration and visual gates remain unverified.
- Deployment: NOT AUTHORIZED.

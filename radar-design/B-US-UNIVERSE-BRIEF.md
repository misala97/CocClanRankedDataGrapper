# Radar Workstream B — US Universe and Mapping Maintenance Brief

Status: **B1 CODE/REVIEW GATE CLOSED; CODE-ONLY DEPLOY PACKET READY / NOT DISPATCHED**  
Current gate: **OWNER SELECTION AND PASTE OF `B-US-UNIVERSE-B1-DEPLOY-PROMPT.md`**  
Release A remains **CLOSED** at `0fdad7327292cd3cd0b62dbe3f6b460873263053`.

Binding assessments: `B-US-UNIVERSE-EVIDENCE-1-RULING.md`, `B-US-UNIVERSE-EVIDENCE-2-RULING.md`, `B-US-UNIVERSE-AUTHORITY-1-RULING.md`, `B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md`, `B-US-UNIVERSE-B1-CORRECTION-1-RULING.md`, and `B-US-UNIVERSE-B1-REVIEW-1-RULING.md`.

## 1. Objective

Establish repository- and data-backed requirements for maintaining Radar's active US-listing/USD universe and provider mappings without reopening release A or repeating the completed 2026-09-16 manual import.

The first assignment is evidence gathering only. It must identify and classify the recorded:

- 146 newly imported US identities that did not receive `RadarInstrument` mappings;
- 51 directory entries whose imported identity data changed;
- 87 previously known listings absent from the completed directory snapshot.

It must also define a failure-safe, auditable daily directory-maintenance design that can later become a bounded implementation plan.

## 2. Binding starting facts

- The completed manual Nasdaq Trader directory import is historical evidence, not pending work. It must not be rerun merely to reproduce its counts.
- The accepted import result recorded 12,745 active universe identities and 12,599 mapped instruments.
- Active Radar behavior is US-listings/USD-only. Charts use Alpaca; Yahoo is disabled.
- Historical DE/EUR database rows and schema remain protected.
- Release A is deployed, verified, and closed. Workstream B may consume A's final state but must not revise A's closure.
- Existing identity upsert behavior does not itself create or maintain `RadarInstrument` mappings.
- An absent listing is not proof of delisting. Any automated absence policy must fail closed and preserve history.

## 3. Questions the Researcher must answer

For each of the 146, 51, and 87 cohorts:

1. Produce the exact symbol/identity set from retained evidence or bounded read-only queries.
2. State whether the count is a 2026-09-16 snapshot fact or still matches current data.
3. Explain any count drift without changing data.
4. Classify every row into a disposition useful for a later implementation plan.

At minimum, distinguish safe automatic mapping candidates; symbol/provider normalization; venue/MIC ambiguity; rename, reassignment, or corporate-action risk; unsupported/non-US/non-USD cases; existing-mapping conflicts; continued absence observation; and manual review.

Document a proposed primary US/USD mapping contract: identity/listing keys, exchange-to-MIC rules, Alpaca provider-symbol rules, currency and uniqueness invariants, provenance/status/effective time, history-preserving rename/reassignment behavior, and safe failure behavior.

Recommend a daily maintenance flow that validates both official inputs before staging, produces a reviewable dry-run diff, is transactional/idempotent/serialized/auditable, uses circuit breakers, performs no mutation on suspicious inputs, ages absences conservatively, preserves history, and defines rollback and scheduler boundaries.

## 4. Scope boundary

Authorized now: repository planning artifacts and inspection of repository code, migrations, tests, and retained non-secret workspace evidence.

Requires explicit owner authorization at dispatch: production-host reads, bounded `SELECT`-only queries, retained evidence outside this worktree, and fresh official-directory fetches.

Not authorized: importer reruns, database writes, mapping/delisting changes, migrations, implementation, service/job/environment/provider changes, commits, resets, cleans, discards, deployment, or release-A work.

## 5. Required Researcher deliverables

1. Git/workspace continuity proof.
2. Reproducible source/evidence inventory.
3. Exact 146/51/87 cohort tables with classifications and reconciled totals.
4. Historical-versus-current comparison and drift explanation.
5. Mapping contract and unresolved decisions.
6. Failure-safe daily maintenance contract.
7. Schema/migration assessment.
8. Focused test and operational verification matrix.
9. Risks ranked by severity and reversibility.
10. Smallest safe implementation slice, without implementation.

## 6. Mastermind exit gate

The evidence assignment is complete only when its counts reconcile, every cohort row has a disposition, provenance is reproducible, and remaining policy choices are explicit. Only then may the Mastermind propose an implementation spec or independent verification assignment.

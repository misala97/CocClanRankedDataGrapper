# Radar Workstream B — US Universe Evidence Ledger

This ledger is the source of truth for Workstream B assignment status. It does not reopen release A.

## Current state

| Assignment | Role | State | Result |
|---|---|---|---|
| `B-US-UNIVERSE-EVIDENCE-1` | Researcher | **ACCEPTED / SUPERSEDED** | Repository trace and tooling accepted; its exact-row blocker was closed by Evidence‑2. |
| `B-US-UNIVERSE-EVIDENCE-2` | Researcher | **COMPLETE / ACCEPTED** | Exact cohorts, current drift, conflicts and bounded capture accepted under `B-US-UNIVERSE-EVIDENCE-2-RULING.md`. |
| `B-US-UNIVERSE-AUTHORITY-1` | Researcher | **COMPLETE / ACCEPTED** | Eight of eight directory mappings confirmed under `B-US-UNIVERSE-AUTHORITY-1-RULING.md`; no remapping or added code. |
| `B-US-UNIVERSE-B1-IMPLEMENT-1` | Implementer | **ASSESSED — CORRECTION REQUIRED / NOT ACCEPTED INTO REVIEW** | Binding ruling `B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md`. Focused proof passes, but C1–C5 block review: pre-lock transaction snapshot reuse, incomplete idempotent rechecks, D2 violation for unmapped name drift, missing pair validation in the seed path, and noisy all-unmapped provider access. No real apply, commit or deployment. |
| `B-US-UNIVERSE-B1-CORRECTION-1` | Implementer | **COMPLETE / ACCEPTED INTO REVIEW** | Binding ruling `B-US-UNIVERSE-B1-CORRECTION-1-RULING.md`. Mastermind reproduced 153 focused tests and 31/31 cohort checks; C1–C5 accepted. Poll stamping is accepted fairness bookkeeping. No real apply, commit or deployment. |
| `B-US-UNIVERSE-B1-REVIEW-1` | Reviewer / QA | **COMPLETE / ACCEPTED — CODE/REVIEW GATE CLOSED** | Binding ruling `B-US-UNIVERSE-B1-REVIEW-1-RULING.md`. No Critical/High/Medium findings. F6 and R1 accepted as Low non-blocking carries with explicit future-apply safeguards. Candidate remains uncommitted/undeployed; real apply unauthorized. |
| `B-US-UNIVERSE-B1-DEPLOY` | Deployer | **READY — NOT DISPATCHED** | Paste-ready `B-US-UNIVERSE-B1-DEPLOY-PROMPT.md`; exact 18-path code and 23-path docs integration plus backup-first code deployment only. Real apply/import/data mutation excluded. |

## Binding facts

- Expected workspace refs: `0fdad7327292cd3cd0b62dbe3f6b460873263053`.
- Expected branch: `codex/radar-selected-price-charts`.
- Release A: **DEPLOYED / VERIFIED / CLOSED**.
- Manual 2026-09-16 directory import: **COMPLETE — DO NOT RERUN AS PENDING WORK**.
- Recorded cohorts: 146 unmapped new identities; 51 changed entries; 87 absent listings.
- Workstream B1 implementation/correction/review: **COMPLETE / ACCEPTED as an uncommitted local candidate** (2026-09-18). The real 114-row apply, commit and deployment: **NOT RUN / NOT AUTHORIZED**.

## Evidence return checklist

- [x] Git/workspace continuity verified; pre-existing dirt preserved.
- [x] Sources and exact queries inventoried.
- [x] Exact 146, 51, and 87 cohorts returned and fully classified.
- [x] Historical snapshot and current counts distinguished.
- [x] Mapping contract proposed with conflicts/manual review explicit.
- [x] Failure-safe daily maintenance contract proposed.
- [x] Schema/migration impact assessed.
- [x] Test/operational verification matrix proposed.
- [x] Smallest safe implementation slice recommended without implementation.
- [x] Self-contained Mastermind return prompt supplied.

## Rulings

- **B-R1 — A remains closed.** B may consume A's accepted state but may not redispatch, review, deploy, smoke-test, or clean up A.
- **B-R2 — Completed import is evidence.** Research must not recreate the completed event through a write run.
- **B-R3 — Absence fails closed.** One missing snapshot cannot authorize destructive delisting or mapping removal.
- **B-R4 — No implicit host authorization.** Packet preparation does not authorize host, database, network, or provider access.
- **B-R5 — Segment MICs remain authoritative.** Preserve `XNGS`/`XNMS`/`XNCM`; record operating MIC separately and do not normalize to `XNAS`.
- **B-R6 — Authority gate closed.** All eight current mappings are confirmed; no further Researcher is needed before owner decisions.
- **B-R7 — D1 approved.** Keep segment MICs, preserve history, record operating MIC separately, and review continuity before any mapping transition.
- **B-R8 — D2 approved.** A first-token name change may update identity text but cannot automatically reset a baseline or mapping.
- **B-R9 — D3 approved.** The 26 non-common listings remain identities but receive no price mapping in B1.
- **B-R10 — D8 approved.** Unknown or unmapped identities must be skipped/quarantined, never assigned fallback `XNAS`/`XXXX` identities.
- **B-R11 — B1 is not review-ready.** C1–C5 in `B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md` require a bounded correction before independent review.
- **B-R12 — F1 accepted.** The explicit-MIC provider call-site changes are necessary and remain in the candidate.
- **B-R13 — unsafe wider gate prohibited.** Do not rerun the DB-backed wider selector until the destructive migration test is independently guarded to a verified disposable database.
- **B-R14 — C1–C5 accepted.** The bounded correction passes fresh Mastermind verification and advances the complete candidate to independent review.
- **B-R15 — C5 poll stamp accepted.** Scheduling attempt state may be advanced for an all-unmapped batch to prevent starvation; no provider or quote write occurs.
- **B-R16 — B1 code/review accepted.** Independent review found no Critical, High, or Medium defect. No further B1 correction/review is pending.
- **B-R17 — F6 apply rule.** Until B2 unifies serialization/full under-lock reconciliation, any real apply requires no concurrent seed/import and a fresh immediately preceding dry-run over the exact reviewed bytes.
- **B-R18 — R1 audit rule.** Any real apply requires report-path preflight, independent stdout/stderr capture, preserved manifest/digests/exit status, and post-run row reconciliation. Report failure does not authorize continued work.

## Next Mastermind action

Owner selects and pastes `B-US-UNIVERSE-B1-DEPLOY-PROMPT.md` to one Deployer. Do not dispatch automatically. Keep the real 114-row apply as a separate, later authorization with B-R17/B-R18 safeguards and preferably a disposable MariaDB rehearsal. Do not apply mappings, start B2, or reopen A.

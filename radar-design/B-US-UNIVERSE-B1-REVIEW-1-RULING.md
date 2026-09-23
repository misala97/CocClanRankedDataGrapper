# Radar Workstream B1 — Independent Review Ruling

Date: 2026-09-18  
Assignment: `B-US-UNIVERSE-B1-REVIEW-1`  
Verdict: **ACCEPTED WITH NON-BLOCKING CARRIES — B1 CODE/REVIEW GATE CLOSED**

## 1. Acceptance

The fresh independent Reviewer/QA return is accepted. No Critical, High, or Medium defect was found. The complete uncommitted B1 candidate conforms to the approved D1/D2/D3/D8 decisions and the binding B1 plan, including the accepted C1–C5 correction.

Git continuity remains correct: workspace `.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, and `HEAD`, `origin/main`, and `origin/codex/radar-selected-price-charts` all remain `0fdad7327292cd3cd0b62dbe3f6b460873263053`. The index is empty. Assessment-time status had 471 paths: 19 tracked modifications and 452 untracked paths; adding this ruling made it 472. The 18-file candidate manifest re-hashes with zero mismatches, and `git diff --check` passes.

The Reviewer independently reproduced 153 focused tests through the unreachable-DB harness and all 31 Evidence-2 checks. These match the still-current Mastermind correction verification because the candidate hashes have not changed. Models and migrations remain untouched.

This closes the B1 implementation/correction/review loop only. It does not authorize commit, push, deployment, the real 114-row mapping apply, production/database/provider access, B2, or Radar A work.

## 2. F6 ruling — Low, non-blocking operational and B2 carry

The reviewer correctly found that corporate-action pairing and absence context are calculated before the named lock, while the manual identity seed/import path does not take that lock. The lock therefore serializes mapping applies against other mapping applies, not every possible universe write.

This does not block B1 code acceptance because the importer is manual-only, each apply command reconciles current state first, the candidate identity/name/active state and mapping conflicts are re-read under the lock, and the narrow race produces a valid serial order rather than a broken mapping invariant.

Binding rules for any future real mapping apply:

- no seed/import/universe-identity writer may run concurrently;
- use the exact reviewed directory bytes and approval manifest;
- run a fresh dry-run immediately before apply and require the expected cohorts/digests;
- capture the no-concurrent-import condition in the operator evidence;
- prefer a successful disposable MariaDB lock/writer rehearsal before production authorization.

B2 must unify maintenance serialization and/or recompute the complete reconciliation—including pairing/absence context—inside the locked writer transaction. Documentation must not claim the current lock serializes the manual seed/import path.

## 3. R1 ruling — Low, non-blocking operational and audit carry

The reviewer correctly found that database commit precedes report-file replacement and printed summary. A report-path or disk failure after commit can therefore leave inserted rows without the intended report file. The result is recoverable through the insert-only/idempotent contract, `mapping_source`/`mapped_at`, and an immediate rerun that reports the rows as skipped.

No new correction loop is required. For any future real apply, the operator packet must:

- preflight the exact report directory with a disposable create/write/replace check before apply;
- capture stdout and stderr independently of the report file;
- preserve the reviewed manifest, directory digests, command exit status, and post-run row verification;
- on report-write failure, stop further action and reconcile/rerun idempotently before claiming success.

Durable database-backed run auditing may be considered in B2. R1 does not authorize an apply now.

## 4. Accepted limitations and debt

- Live MySQL/MariaDB named-lock plus writer execution remains unavailable.
- The 59 DB-backed regression tests and wider selector remain unavailable.
- The unguarded destructive migration test remains pre-existing safety debt; B-R13 still prohibits the wider selector.
- The seed path's `datetime.utcnow()` deprecation warning remains non-blocking.
- The documented parser tolerances and unchanged out-of-scope readers are accepted as reviewed.

## 5. Next owner decision

The safest next step is an owner decision on preparing one exact-manifest B1 integration/release packet. That packet should integrate and deploy the accepted code without running the 114-row apply. The real mapping apply should remain a separate, later owner-authorized operation with the F6 and R1 safeguards above and, preferably, a disposable MariaDB rehearsal.

No integration, release, or apply packet is prepared or dispatched by this ruling.

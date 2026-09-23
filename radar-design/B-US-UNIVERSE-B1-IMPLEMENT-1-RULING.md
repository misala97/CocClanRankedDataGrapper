# Radar Workstream B1 — Implementer Assessment

Date: 2026-09-18  
Assignment: `B-US-UNIVERSE-B1-IMPLEMENT-1`  
Verdict: **CORRECTION REQUIRED — NOT ACCEPTED INTO INDEPENDENT REVIEW**

## 1. Scope and continuity

The Mastermind assessed the uncommitted candidate and its return without changing product code, running a real mapping apply, contacting production or providers, committing, deploying, or reopening Radar A.

Git continuity is correct: workspace `.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, and `HEAD`, `origin/main`, and `origin/codex/radar-selected-price-charts` all resolve to `0fdad7327292cd3cd0b62dbe3f6b460873263053`. The index is empty. Existing tracked and untracked dirt remains preserved.

Radar A remains **LIVE / VERIFIED / CLOSED**. The completed manual directory import remains historical evidence and must not be rerun as pending work.

## 2. Evidence accepted

The candidate substantially implements the planned parser, reconciliation report, approval-bound insert path, explicit-MIC quote contract, mapped-primary readers, and `IEXG` recognition. The following fresh, database-isolated checks passed:

- `125 passed in 1.51s` for the three focused B1 test modules through the DB-poisoned gate harness;
- the offline Evidence-2 verifier passed all 31 checks and reproduced the accepted 114 safe mapping candidates, 26 non-common rows, 6 corporate-action candidates, 7 drift rows, and 87 absent rows;
- no real 114-row mapping apply ran.

These results establish useful implementation progress, but they do not prove the apply path's concurrency and policy safety.

## 3. Required corrections

### C1 — Critical: apply rechecks can use a pre-lock database snapshot

The CLI builds the report with `load_current_state(session)` and then calls the apply function with the same SQLAlchemy session. That read opens a transaction before the named lock is acquired. The named lock uses another connection, while the apply-time queries continue through the already-open session. Under MySQL/MariaDB repeatable-read semantics, those queries may see the pre-lock snapshot rather than state established after serialization.

Required correction: end the report transaction and perform all apply-time reads and writes in an explicitly fresh writer transaction acquired after the named lock. The lock must span the complete fresh transaction. Add focused proof that a stale pre-lock session/snapshot cannot satisfy apply-time rechecks.

### C2 — Critical: the idempotent skip path bypasses safety rechecks

`apply_approved_mappings` checks `_already_applied` before `_apply_time_problem`. A row that appears already mapped is therefore skipped without revalidating the approval directory digest, current active identity, current reconciliation binding, or all mapping fields. `_already_applied` also omits venue comparison.

Required correction: every approved row, including a no-op/idempotent rerun, must pass the same current-state, approval-hash, active-identity, directory-binding, and complete-field checks before it may be reported as skipped. Add tests for a stale digest, missing/inactive identity, and wrong venue on the idempotent path.

### C3 — Critical: unmapped name changes can enter the automatic safe set

`_classify_unmapped` does not compare the current identity name with the directory name. A future unmapped identity with a first-token/company-name change can therefore become a safe mapping candidate. This violates approved decision D2: name changes require review and cannot automatically authorize mapping action.

Required correction: classify name drift for unmapped identities before safe-candidate admission; first-token changes and other policy-defined name changes must be review-only. Add focused unmapped-name-change tests.

### C4 — Major: the legacy seed mutation path does not validate the input pair

`seed_radar_universe.py` strict-parses individual files but retains first-file-wins behavior and does not call `validate_pair`. Cross-file overlap can therefore bypass the new pair-level fail-closed contract.

Required correction: parse both snapshots before application import/upsert, require exactly one valid file of each type, and run `validate_pair`; alternatively disable this mutation path in favor of the validated workflow. Add overlap/order tests. Do not run a real import.

### C5 — Major: an all-unmapped ingest batch makes a pointless provider call and logs an error

The `run_radar_ingest.py` all-unmapped branch can still call the provider with unmapped symbols. `record_quotes` then rejects the resulting `mic=None` quotes. This fails closed for storage, but it is noisy, wastes a provider call, and is not the approved D8 skip/quarantine behavior.

Required correction: when no mapped instruments exist, skip the provider request and record a truthful non-error/no-mapped outcome. Add a test proving zero provider calls, zero writes, and no fallback MIC.

## 4. Rulings on returned findings

- **F1 accepted.** The Finnhub and Twelve Data call-site edits are necessary consequences of removing the implicit `XNAS` default. They remain within B1's explicit-MIC contract.
- **F2 requires C5.** Rejecting unmapped storage is correct, but an avoidable provider request plus error log is not the desired quarantine behavior.
- **F4 is confirmed pre-existing safety debt.** The unguarded migration test is outside this B1 product correction. Do not run the wider DB-backed selector again until that test has a verified disposable-database guard. Track its repair separately.

## 5. Local database incident

The Implementer ran the plan's wider selector against the local development database `personal_apps@localhost`. The unguarded migration test downgraded it and dropped `radar_ingest_runs`, `radar_board_observations`, `radar_board_results`, and `radar_board_namespaces`. With explicit owner authorization, `flask db upgrade` recreated the schema at head; the four tables are empty and their former local rows are lost. Production and the VPS were not contacted.

This incident is permanent evidence. All further B1 verification must remain database-poisoned/offline unless the owner separately authorizes a verified disposable database.

## 6. Next gate

Prepare one bounded correction packet only after owner approval. It must address C1–C5, preserve all existing work, and forbid a real mapping apply, network/provider access, production/database mutation, commits, deployment, B2, and A work. After the correction returns and passes focused Mastermind verification, send the complete candidate to one fresh independent Reviewer/QA. No Reviewer prompt is prepared or dispatched by this ruling.

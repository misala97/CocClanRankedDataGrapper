# Copy/paste prompt — B-US-UNIVERSE-B1-REVIEW-1

```text
You are Radar's fresh independent Reviewer / QA. Return your result to the Mastermind.

Assignment ID: B-US-UNIVERSE-B1-REVIEW-1

Objective:
Independently review the complete uncommitted B1 candidate—including the accepted C1–C5 correction—for correctness, concurrency safety, policy compliance, regression risk, evidence quality, and scope. This is read-only product review. Do not fix code and do not run the real 114-row mapping apply.

Independence requirement:
- You must not be the Implementer who produced B-US-UNIVERSE-B1-IMPLEMENT-1 or B-US-UNIVERSE-B1-CORRECTION-1.
- No subagents. Perform the review yourself.
- Do not assume the returns are correct; verify claims against the code and safe evidence.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / expected base and current HEAD:
codex/radar-selected-price-charts
0fdad7327292cd3cd0b62dbe3f6b460873263053

Before reviewing:
- Verify workspace, branch, HEAD, origin refs, index, status, diff, and recent log with per-command `safe.directory`.
- Expected refs are HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053; the candidate is intentionally uncommitted and unstaged.
- Preserve every tracked and untracked path.
- Read completely, in order:
  1. HANDOFF.md — newest notice
  2. radar-design/WORKFLOW.md
  3. radar-design/B-US-UNIVERSE-BRIEF.md
  4. radar-design/B-US-UNIVERSE-LEDGER.md
  5. radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
  6. radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md
  7. radar-design/B-US-UNIVERSE-B1-PLAN.md
  8. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md
  9. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md
  10. radar-design/B-US-UNIVERSE-B1-CORRECTION-1-PROMPT.md
  11. radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md
  12. radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RULING.md
  13. radar-design/A-US-USD-ONLY-RELEASE-CLOSURE.md
  14. newest notices in radar-design/HANDOFF.md, ASSIGNMENTS.md, and MASTERMIND-STATE.md
- Inspect every product and test file in `radar-design/artifacts/b-us-universe-b1-correction-1/candidate-manifest.txt`, the complete Git diff, the correction delta, and relevant evidence scripts/transcripts.

Critical database-safety boundary:
- A prior broad selector reached `personal_apps@localhost`; an unguarded migration test dropped four local Radar tables. The owner-authorized schema upgrade recreated them empty. Production was untouched.
- Never run `pytest tests/`, `pytest tests/ -k ...`, `test_radar_activity.py`, migration tests, `test_radar_daemon.py`, or another broad/DB-backed selector.
- Every Python test must run through `radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py`, which disables dotenv and binds the app to the unreachable host `b1-gate.invalid`.
- Do not use the local `personal_apps` database or any production/VPS/database/network/provider endpoint. Do not attempt a schema repair.

Binding product decisions:
- D1: keep segment MICs and preserve history; never normalize tiers to `XNAS` or rewrite existing MICs.
- D2: name changes are review-only for mapping action.
- D3: the 26 non-common listings remain identities only, without price mappings.
- D8: unknown/unmapped identities are skipped or quarantined; never fabricate `XNAS` or `XXXX`.
- The completed manual directory import is historical evidence and must not be rerun.
- Release A remains closed and out of scope.

Review the complete B1 contract:
- strict, source-aware parsing with exact headers, eight official rules, pair validation, and no undocumented alias;
- deterministic mutation-free dry-run reconciliation and exact retained-evidence cohorts;
- explicit reviewed approval manifest and source-hash binding;
- insert-only, serialized, transactional, all-or-nothing mapping capability with current-state rechecks and safe idempotency;
- no existing mapping update/delete/rewrite;
- explicit MIC quote behavior, mapped-primary readers, no fabricated fallback, and IEXG recognition;
- no real mapping apply, import, production action, schema/migration change, B2 work, or A work.

Mandatory adversarial questions:
1. Does the MySQL/MariaDB named lock actually span a newly begun writer transaction, with no pre-lock snapshot reuse and no connection-lifetime gap?
2. Can any approval be inserted or skipped without rechecking its digest, directory binding, active/name-stable identity, provider-symbol ownership, and every required contract-row field?
3. Is batch refusal truly all-or-nothing for every ordering of inserted, skipped, and refused approvals?
4. Can an unmapped name change, non-common listing, corporate-action candidate, unknown code, or drift row enter the safe set or apply path?
5. Does the seed path always reject missing, duplicate, unknown, or overlapping directory inputs before application/database access?
6. Does an all-unmapped ingest batch make zero provider calls and quote writes while the accepted poll stamp prevents starvation without inventing a MIC or reporting an error?
7. F6: corporate-action pairing/absence context is not recomputed under the lock. Determine whether a concurrent/import-between-report-and-apply change can make an approved candidate unsafe, whether existing serialization prevents that race, and assign severity. Do not fix it.
8. Are the private `in_sync`/name fields sufficient and non-leaking, and does the serialized dry-run report remain unchanged?
9. Are the offline SQLite transaction tests a faithful bounded regression proof without overstating unavailable live-MySQL evidence?
10. Did the candidate preserve models, migrations, DE/EUR history boundaries, existing US mappings, accepted cohorts, unrelated dirt, and release A?

Safe verification permitted:
- Run only these four modules through the DB-free harness:
  `py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short`
- Run the offline Evidence-2 verifier:
  `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .`
- Run read-only static checks such as `git diff --check`, manifest hashing, targeted searches, and `git diff -- personal_apps/models.py personal_apps/migrations`.
- You may mark live MySQL and DB-backed regression evidence unavailable. Never replace an unavailable gate with an unsafe database.

Finding standard:
- Report only actionable Critical, High, Medium, or Low findings, with exact file/line evidence, impact, reproduction/reasoning, and smallest correction.
- Separate candidate defects from pre-existing debt and unavailable environmental proof.
- Do not reject merely because live MySQL, the destructive suite, or the wider 59 DB-backed tests are unavailable; assess whether the code/evidence honestly handles those limits.
- Explicitly state whether the complete B1 candidate is ACCEPTED, ACCEPTED WITH NON-BLOCKING CARRIES, or REJECTED pending correction.

Authorized writes:
- Create only `radar-design/B-US-UNIVERSE-B1-REVIEW-1-RETURN.md`.
- Create sanitized review evidence only under `radar-design/artifacts/b-us-universe-b1-review-1/` if necessary.
- Do not edit product code, tests, candidate evidence, ledgers, handoffs, roadmaps, or existing returns/rulings.

Not authorized:
- Fixes, formatting changes, new product tests, implementation, or deletion/discard of any file.
- Real mapping apply, importer run, any non-test database write, production/VPS/network/provider/account access, credential/environment inspection, commit, push, merge, deployment, config/schema/migration/service/job/timer change, B2, or Radar A action.
- Stage, clean, reset, checkout, discard, or subagents.

Stop condition:
Stop when the complete candidate and C1–C5 have been independently assessed, safe focused evidence has been reproduced or accurately marked unavailable, all findings are severity-ranked, and the review return is complete. Do not implement fixes or prepare deployment/apply work.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this independent Reviewer/QA return for assignment B-US-UNIVERSE-B1-REVIEW-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [candidate and review-only additions; staged/committed/pushed state]
Binding artifacts: [absolute plan, rulings, implementation/correction returns, review return/evidence, ledger]

Objective and scope reviewed: [complete B1 plus C1–C5; read-only boundaries]
Verdict: [ACCEPTED / ACCEPTED WITH NON-BLOCKING CARRIES / REJECTED]
Findings: [severity, exact path:line, impact, proof/reasoning, smallest correction; or none]
C1–C5 assessment: [one explicit result per correction]
F6 judgment: [blocking/non-blocking decision and reasoning]
Original B1 contract assessment: [parser, reconcile, apply, fallback, IEXG, scope]
Evidence: [exact safe commands and results]
Evidence attribution: [fresh reviewer execution vs Implementer/accepted evidence vs inference]
Unavailable gates: [live MySQL and DB-backed limitations]
Actions taken: [review artifacts only; explicitly no product/test edit, apply, DB/network/provider access, commit or deployment]
Protected state: [A, DE/EUR history/schema, existing US mappings/cohorts, unrelated dirt]
Subagents: none
Updated artifacts: [absolute review return/evidence paths]
Requested Mastermind decision: [accept B1 code/review gate or issue one bounded correction ruling]
Next bounded action recommendation: [one action; do not authorize real apply or deployment yourself]

Read the current handoff, ledger, all B1 rulings and returns, verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy, or apply mappings yourself.
```

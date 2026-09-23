# Copy/paste prompt — B-US-UNIVERSE-B1-CORRECTION-1

```text
You are Radar's Implementer. Return your result to the Mastermind.

Assignment ID: B-US-UNIVERSE-B1-CORRECTION-1

Objective:
Correct only the five safety defects C1–C5 in the existing uncommitted B1 candidate, prove them with focused database-poisoned/offline tests, and leave one coherent uncommitted candidate ready for independent review. Do not run the real 114-row mapping apply.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / expected base and current HEAD:
codex/radar-selected-price-charts
0fdad7327292cd3cd0b62dbe3f6b460873263053

Required execution method:
- Use `superpowers:receiving-code-review` to validate the ruling against the current code before editing, then `superpowers:test-driven-development` for each correction.
- No subagents. One Implementer owns the complete correction.
- Work from the existing uncommitted B1 candidate. Preserve every pre-existing tracked and untracked file.
- Do not stage or commit. Do not dispatch a Reviewer.

Before acting:
- Verify the exact workspace, branch, HEAD, available origin refs, index, status, diff, and recent log using per-command `safe.directory`.
- Expected refs are HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053.
- Read these files completely, in order:
  1. HANDOFF.md — newest notice
  2. radar-design/WORKFLOW.md
  3. radar-design/B-US-UNIVERSE-BRIEF.md
  4. radar-design/B-US-UNIVERSE-LEDGER.md
  5. radar-design/B-US-UNIVERSE-B1-PLAN.md
  6. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md
  7. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md
  8. radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md
  9. radar-design/A-US-USD-ONLY-RELEASE-CLOSURE.md
  10. newest notices in radar-design/HANDOFF.md, ASSIGNMENTS.md, and MASTERMIND-STATE.md
- Inspect the complete existing B1 diff before editing. Treat the ruling's C1–C5 as binding unless current code evidence directly contradicts it; if so, stop that item and report exact evidence rather than broadening scope.

Critical database-safety warning:
- A previous wider test selector reached the local development database `personal_apps@localhost`. Its unguarded migration test downgraded the schema and dropped four Radar tables. The owner-authorized upgrade recreated those tables empty; the lost local rows are not recoverable from this assignment. Production was untouched.
- Never run `pytest tests/`, `pytest tests/ -k ...`, `test_radar_activity.py`, migration tests, or any broad selector.
- Run every Python test through `radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py`, which must keep dotenv disabled and the application database host unreachable.
- Do not use the local `personal_apps` database. Do not attempt another schema repair. If a required behavior cannot be proved offline or with the existing isolated seams, mark it unavailable.

Binding owner decisions:
- D1: preserve segment MICs and history; never normalize tiers to `XNAS` or rewrite an existing MIC.
- D2: name changes are review-only for mapping decisions; never let a changed-name identity enter automatic mapping before review.
- D3: the 26 non-common listings remain identity-only and price-unmapped.
- D8: unknown or unmapped identities are skipped/quarantined; never fabricate `XNAS` or `XXXX`.

Required corrections:

1. C1 — fresh apply transaction under the named lock
   - The report/dry-run read must not leave the apply path using a transaction or repeatable-read snapshot opened before lock acquisition.
   - Acquire the named maintenance lock first, then create/begin a fresh writer transaction for every apply-time read, invariant check, insert/flush, and commit. Keep the lock held until that transaction has committed or rolled back.
   - Preserve SQLite/injected-lock testability and MySQL `GET_LOCK`/`RELEASE_LOCK` behavior.
   - Add a regression test that fails if a pre-lock report session/snapshot is reused for apply-time rechecks. Do not claim live MySQL proof unless a verified disposable database was actually available.

2. C2 — full safety validation before an idempotent skip
   - Do not return `skipped` merely because one existing US row looks similar.
   - Before either insert or idempotent skip, revalidate the approval directory digest, active/current identity, current directory/reconciliation binding, source/code/MIC rule, market, currency, ticker, provider symbol, venue, primary flag, and mapping status.
   - An exact existing mapping may be skipped only after all current safety checks pass. A stale hash, missing/inactive identity, wrong venue, conflicting row, collision, or any other mismatch refuses the whole batch with zero partial inserts.
   - Add focused tests for stale digest, missing/inactive identity, wrong venue, and a valid exact idempotent rerun.

3. C3 — apply D2 to unmapped identities
   - Compare the current identity name with the directory name before admitting an unmapped identity to `safe_mapping_candidates`.
   - First-token changes and every name-drift case covered by the existing D2 policy must go to `name_review`/review-only, never the automatic safe set.
   - Preserve the accepted Evidence-2 totals for the retained snapshot; do not add symbol exceptions.
   - Add focused tests for first-token and relevant non-first-token name drift on previously unmapped identities.

4. C4 — enforce pair validation in the legacy seed path
   - `seed_radar_universe.py` must parse the complete supplied directory pair before entering application/ORM mutation work.
   - Require exactly one `nasdaqlisted.txt` and one `otherlisted.txt`, reject unknown/duplicate/missing inputs, call `validate_pair`, and reject cross-file symbol overlap regardless of argument order.
   - Preserve all other identity-upsert behavior. Do not run the importer.
   - Add focused missing/duplicate/overlap/order tests that prove failure happens before app/database access.

5. C5 — skip an all-unmapped ingest batch before provider access
   - When a due batch has no mapped instruments, make zero quote-provider calls and zero quote writes.
   - Record/return the existing truthful non-error or explicitly named `no_mapped_instruments` outcome consistent with the surrounding ingest contract. Do not fabricate a MIC and do not turn ordinary unmapped input into a cycle error.
   - Preserve mixed-batch behavior for mapped instruments.
   - Add a focused test proving zero provider calls, zero writes, no fallback MIC, and no error outcome for the all-unmapped case.

Owned product/test paths:
- personal_apps/features/radar/universe_reconcile.py
- personal_apps/scripts/reconcile_radar_universe.py
- personal_apps/scripts/seed_radar_universe.py
- personal_apps/run_radar_ingest.py
- personal_apps/tests/test_radar_universe_directory.py
- personal_apps/tests/test_radar_universe_reconcile.py
- personal_apps/tests/test_radar_universe_mapping_apply.py
- the smallest existing or new focused test module needed for C5

Authorized artifacts:
- Create `radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md`.
- Create sanitized correction evidence only under `radar-design/artifacts/b-us-universe-b1-correction-1/`.
- After verification, update only the current B1 assignment status in `radar-design/B-US-UNIVERSE-LEDGER.md` and root `HANDOFF.md`.

Not authorized:
- Any change outside the owned paths except the three authorized return/status locations above.
- The real 114-row apply, the completed manual importer run, or any database mutation outside isolated in-memory/disposable test state.
- Production/VPS access, network directory fetch, provider/account call, credential/environment inspection, or external write.
- Models, migrations, schema, frontend, services, configuration, environment, scheduler/job/timer, identity-upsert semantics, absence aging, delisting, reassignment, MIC transition, provider-presence lookup, rollback machinery, or B2.
- Any change to historical DE/EUR rows or reopening/retesting release A.
- Stage, commit, push, merge, deploy, clean, reset, discard, or delete pre-existing work.
- Subagents.

Protected state:
- Radar A remains LIVE / VERIFIED / CLOSED at `0fdad73` with active US/USD-only behavior, eight warm boards, Charts ON, Alpaca ON, and Yahoo OFF.
- Preserve all historical DE/EUR data and schema.
- Preserve all existing US mappings and quote/close history, the seven drift rows, the 26 non-common identities, and the six corporate-action-review identities.
- Preserve Evidence-1, Evidence-2, Authority-1, the original B1 return/evidence, and all unrelated dirt.

Verification:
- For each C1–C5, first add a focused regression test that fails for the defect, then make the smallest responsible correction and rerun it.
- Run the existing three B1 modules plus the focused C5 test only through the DB-free gate harness, for example:
  `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py <C5-test-path> -q -p no:cacheprovider --tb=short`
- Rerun `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .` and require all accepted cohort/hash checks to remain exact.
- Run `git diff --check`.
- Require `git diff -- personal_apps/models.py personal_apps/migrations` to remain empty.
- Record exact commands, pass/fail/skip counts, and whether each result is fresh execution, accepted prior evidence, or inference.
- Never substitute an unsafe database or broad suite for an unavailable gate.

Stop condition:
Stop after C1–C5 are corrected, focused gates pass or are honestly marked unavailable, retained Evidence-2 results remain exact, protected paths/state are unchanged, the correction return is complete, and no real apply occurred. Leave the candidate unstaged and uncommitted. Do not prepare or dispatch a Reviewer or production/apply packet.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this Implementer return for assignment B-US-UNIVERSE-B1-CORRECTION-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [all modified/untracked paths, ownership, staged/committed/pushed status]
Binding artifacts: [absolute ruling, original return/evidence, correction return/evidence, plan and ledger paths]

Objective and authorized scope: Correct C1–C5 only in the existing uncommitted B1 candidate; no real apply, production access, commit or deployment.
Correction C1: [fresh under-lock transaction implementation and regression proof]
Correction C2: [complete pre-skip safety checks and regression proof]
Correction C3: [unmapped name-drift review classification and regression proof]
Correction C4: [seed pair validation and pre-app-access proof]
Correction C5: [all-unmapped zero-provider-call behavior and regression proof]
Evidence: [exact safe commands and pass/fail/skip counts; Evidence-2 comparison; diff checks]
Evidence attribution: [fresh worker execution vs accepted prior evidence vs inference]
Database safety: [DB-free harness identity, exact target behavior, no local personal_apps/production access, no real apply]
Findings and limitations: [remaining unavailable MySQL/DB-backed gates or discrepancies]
Actions taken: [files modified/created; explicitly no stage/commit/push/deploy/network/provider/config/schema/history mutation]
Protected state: [A closure, mappings/history, cohorts, models/migrations and unrelated dirt]
Subagents: none
Updated artifacts: [absolute local/uncommitted paths]
Requested Mastermind decision: Verify only the bounded correction and, if accepted, prepare one fresh independent Reviewer/QA prompt; do not implement further fixes, commit, deploy or run the real mapping apply.
Next bounded action recommendation: One fresh independent Reviewer/QA inspects the complete B1 candidate plus correction evidence.

Read the current handoff, ledger, B1 ruling, original return, correction return and evidence. Verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy or apply mappings yourself.
```

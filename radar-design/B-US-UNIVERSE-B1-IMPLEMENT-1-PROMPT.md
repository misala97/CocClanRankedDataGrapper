# Copy/paste prompt — B-US-UNIVERSE-B1-IMPLEMENT-1

```text
You are Radar's Implementer. Return your result to the Mastermind.

Assignment ID: B-US-UNIVERSE-B1-IMPLEMENT-1

Objective:
Execute the binding B1 plan and produce one thoroughly verified, uncommitted local candidate for strict Nasdaq-directory validation, dry-run reconciliation, a guarded insert-only US mapping capability, elimination of fabricated XNAS/XXXX fallbacks, and IEXG calendar recognition. This is local implementation and verification only. Do not run the real 114-row apply.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / expected base and current HEAD:
codex/radar-selected-price-charts
0fdad7327292cd3cd0b62dbe3f6b460873263053

Required execution method:
- Use the `superpowers:executing-plans` skill and execute `radar-design/B-US-UNIVERSE-B1-PLAN.md` task-by-task.
- No subagents. One Implementer owns the complete candidate.
- Work test-first and record a checkpoint after every task.
- Do not stage or commit. Leave one coherent candidate for independent review.

Before acting:
- Verify the exact workspace, branch, HEAD, available origin refs, status, diff, index and recent log using per-command safe.directory.
- Expected refs are HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053.
- Preserve every pre-existing tracked and untracked path. The planning documents, returns, evidence, release records and current notices are intentional.
- Read these files completely, in order:
  1. HANDOFF.md — newest notice
  2. radar-design/WORKFLOW.md
  3. radar-design/B-US-UNIVERSE-BRIEF.md
  4. radar-design/B-US-UNIVERSE-LEDGER.md
  5. radar-design/B-US-UNIVERSE-EVIDENCE-1-RULING.md
  6. radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
  7. radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md
  8. radar-design/B-US-UNIVERSE-EVIDENCE-1-RETURN.md — mapping contract, B1 boundary and test matrix
  9. radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md — exact cohorts/current drift
  10. radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md — official corrections and qualifications
  11. radar-design/B-US-UNIVERSE-B1-PLAN.md
  12. radar-design/A-US-USD-ONLY-RELEASE-CLOSURE.md — protected closed release state
  13. newest notices in radar-design/HANDOFF.md, ASSIGNMENTS.md and MASTERMIND-STATE.md
- Read the retained Evidence-2 source and cohort artifacts only as local inputs. Do not modify them.
- If the plan conflicts with current Git/code evidence, stop the affected slice and report the exact discrepancy. Do not silently broaden scope.

Binding owner decisions:
- D1: keep segment MICs; record MIC type and operating MIC in the contract; never normalize Nasdaq tiers to XNAS or rewrite an existing MIC.
- D2: first-token/name changes are report-only in B1; do not reset baselines, first_seen or mappings.
- D3: the 26 non-common listings remain identities only; do not price-map them.
- D8: unknown/unmapped identities are skipped or quarantined; never fabricate XNAS or XXXX.

Binding B1 outcome:
- A strict parser recognizes only exact nasdaqlisted.txt and otherlisted.txt contracts, their exact documented columns and their file-specific code namespaces.
- The mapping table contains all eight confirmed codes plus mic_type and operating_mic. Current Radar venue labels remain.
- The undocumented `Listing Exchange` alias is not accepted.
- A deterministic dry-run reconciler reports safe, non-common, name-review, MIC-drift, absent, conflict and quarantined cohorts without mutation.
- The retained evidence reconciles to the accepted 114 safe, 26 non-common, 6 corporate-action review and seven drift facts, or the worker stops with a precise discrepancy.
- Mapping apply code is insert-only, approval-manifest-bound, hash-bound, transactional, serialized and all-or-nothing. It rechecks every invariant at apply time.
- No existing RadarInstrument is updated, rewritten, disabled or deleted.
- Quote readers do not admit unmapped identities through stored rows or a default XNAS MIC. Quote requires an explicit MIC.
- IEXG is included in the confirmed modeled-US MIC set.

Authorized actions:
- Modify/create only the product and test paths named by `B-US-UNIVERSE-B1-PLAN.md`.
- Run DB-free unit tests and static checks.
- Run DB-backed tests only against isolated SQLite tables or after proving the exact registered disposable database is `personal_apps_radar_wt`.
- Use the retained local Evidence-2 directory files/current-state artifacts for offline comparison.
- Create `radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md` and sanitized evidence under `radar-design/artifacts/b-us-universe-b1-implement-1/`.
- Update only the current B1 status in `radar-design/B-US-UNIVERSE-LEDGER.md` and root `HANDOFF.md` after verification.

Not authorized:
- The real 114-row apply or any write to production or a non-disposable database.
- Production/VPS access, network directory fetch, provider/account call, credential or private environment inspection.
- Rerunning the completed manual import.
- Identity upsert changes, name writes, baseline/first_seen reset, absence aging, delisting, reassignment, MIC transition, provider-presence lookup, rollback machinery, scheduler/job/timer work, or B2 implementation.
- Editing models.py, migrations, schema, frontend, services, configuration or environment.
- Touching historical DE/EUR rows or reopening release A.
- Stage, commit, push, merge, deploy, clean, reset, discard or delete pre-existing work.
- Subagents.

Protected state:
- Release A's active US/USD-only behavior, eight warm boards, Charts ON, Alpaca ON and Yahoo OFF.
- Every historical DE/EUR database row, schema object and migration.
- All 12,599 existing mapped US primaries and their quote/close history.
- The seven existing drift rows remain unchanged.
- All 26 non-common and six corporate-action-review identities remain unmapped.
- Evidence-1, Evidence-2 and Authority-1 returns/artifacts and every unrelated dirty file.

Verification and evidence:
- Follow every failing/pass gate in the plan.
- `git diff --check` must pass.
- `git diff -- personal_apps/models.py personal_apps/migrations` must be empty.
- Attribute every result as fresh worker evidence, accepted prior evidence, or inference.
- If a required database gate is unavailable, record it as unavailable. Never redirect to production or claim it passed.
- A local disposable test of apply capability is allowed; the real 114-row apply is forbidden.

Stop condition:
Stop with one complete uncommitted candidate only when all five plan tasks are reconciled, focused gates pass or are honestly unavailable, protected files are unchanged, the return is complete, and no real apply occurred. Do not commit, deploy, dispatch a reviewer, or prepare a production/apply packet.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this Implementer return for assignment B-US-UNIVERSE-B1-IMPLEMENT-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [all modified/untracked paths, ownership, staged/committed/pushed status]
Binding artifacts: [absolute brief, rulings, plan, ledger, implementation return and evidence paths]

Objective and authorized scope: Build and locally verify B1 only; no real 114-row apply, production access, commit or deployment.
Completed work: [task-by-task implementation]
Directory contract: [exact headers, eight mapping rules, MIC type/operating MIC, validation behavior]
Reconciliation: [fresh offline counts and exact comparison with accepted 114/26/6/seven-drift evidence]
Mapping safety: [approval binding, hash binding, apply-time rechecks, lock/transaction/invariant behavior, idempotency]
D1/D2/D3/D8 proof: [tests and code locations for every approved decision]
Fallback/IEXG proof: [unmapped behavior, explicit MIC requirement, IEXG calendar test]
Evidence: [exact commands and pass/fail/skip counts, static checks, artifact hashes]
Evidence attribution: [fresh worker execution vs accepted prior reports vs inference]
Database safety: [SQLite/disposable target identity, tests run, explicitly no production/non-disposable access and no real 114-row apply]
Findings and limitations: [unavailable gates, exact discrepancies, B2 exclusions]
Actions taken: [files created/modified; explicitly no stage/commit/push/deploy/network/provider/config/schema/historical-row mutation]
Protected state: [release A, existing mappings/history, seven drift rows, non-common/corporate-action rows, models/migrations, unrelated dirt]
Subagents: none
Updated artifacts: [absolute local/uncommitted paths]
Requested Mastermind decision: Assess B1 and, if accepted for review, prepare one fresh independent Reviewer/QA prompt; do not implement fixes, commit, deploy or run the real apply.
Next bounded action recommendation: One fresh independent Reviewer/QA inspects the complete candidate and evidence against the binding plan.

Read the current handoff, B ledger, all three rulings, plan, implementation return and evidence. Verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy or apply mappings yourself.
```

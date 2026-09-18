# Copy/paste prompt — B-US-UNIVERSE-B1-DEPLOY

```text
You are Radar's Deployer. Return your result to the Mastermind.

Assignment ID: B-US-UNIVERSE-B1-DEPLOY

Authorization model:
This packet was prepared at the owner's request but is not dispatched by preparation alone. If the owner pastes it into a Deployer task, that dispatch authorizes exactly the Git integration, backup-first production deployment, bounded read-only verification, and rollback actions below. It does NOT authorize the real 114-row mapping apply, a universe import, product fixes, B2, or Radar A work.

Objective:
Integrate the exact accepted 18-file B1 application/test candidate, commit the exact B1 continuity documents, fast-forward the feature branch and main normally, deploy the code through the established backup-first production wrapper, and verify that the existing Radar product remains healthy. Deploy code only. Do not apply any of the 114 mappings and do not run the universe importer.

Workspace and release identity:
- workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
- branch: codex/radar-selected-price-charts
- expected base/current HEAD before release commits: 0fdad7327292cd3cd0b62dbe3f6b460873263053
- expected origin/main and origin/codex/radar-selected-price-charts before release: the same 0fdad73 SHA
- expected production HEAD before release: 0fdad7327292cd3cd0b62dbe3f6b460873263053
- production checkout: root@194.164.29.97:/root/coc-stats
- release method: established backup-first `/root/update_coc.sh` transient-systemd wrapper

No subagents. Preserve every unrelated tracked/untracked path, other worktree, production untracked file, environment line, database row, and service.

Read completely before acting:
1. HANDOFF.md — newest notice
2. radar-design/WORKFLOW.md
3. radar-design/B-US-UNIVERSE-BRIEF.md
4. radar-design/B-US-UNIVERSE-LEDGER.md
5. radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
6. radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md
7. radar-design/B-US-UNIVERSE-B1-PLAN.md
8. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md
9. radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md
10. radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md
11. radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RULING.md
12. radar-design/B-US-UNIVERSE-B1-REVIEW-1-RETURN.md
13. radar-design/B-US-UNIVERSE-B1-REVIEW-1-RULING.md
14. radar-design/A-US-USD-ONLY-RELEASE-CLOSURE.md
15. radar-design/A-US-USD-ONLY-DEPLOY-RETURN.md

Binding release facts:
- Radar A is LIVE / VERIFIED / CLOSED at 0fdad73. Active behavior is US-listings/USD-only with eight warm boards; Charts ON, Alpaca ON, Yahoo OFF.
- The completed 2026-09-16 manual directory import is historical evidence. Do not rerun it.
- The accepted B1 candidate is local, uncommitted, and undeployed. Its implementation/correction/review gate is closed with no Critical/High/Medium findings.
- F6 and R1 are Low carries for a later real mapping apply. This release runs no apply, but must preserve the documented safeguards and must not claim that the current named lock covers the seed/import path.
- The prior local-database incident is permanent evidence. Never run a broad selector, `test_radar_activity.py`, migration tests, `test_radar_daemon.py`, or any test outside the explicit safe commands below.

Exact accepted application/test manifest:
- Source of truth: `radar-design/artifacts/b-us-universe-b1-correction-1/candidate-manifest.txt`.
- Exactly 18 hash-bearing manifest lines are accepted. Parse only lines of the form `<status> <64 lowercase hex sha256> <path>`; the trailing numstat lines are evidence, not paths to stage.
- Accepted paths are exactly:
  1. personal_apps/features/radar/analysis_contract.py
  2. personal_apps/features/radar/prices/__init__.py
  3. personal_apps/features/radar/prices/finnhub.py
  4. personal_apps/features/radar/prices/twelvedata.py
  5. personal_apps/features/radar/quotes.py
  6. personal_apps/features/radar/universe_directory.py
  7. personal_apps/features/radar/universe_reconcile.py
  8. personal_apps/run_radar_ingest.py
  9. personal_apps/scripts/reconcile_radar_universe.py
  10. personal_apps/scripts/seed_radar_universe.py
  11. personal_apps/tests/fixtures/radar_universe/approved_safe_sample.csv
  12. personal_apps/tests/ha1_unit/test_analysis_contract.py
  13. personal_apps/tests/test_radar_ingest_unmapped_batch.py
  14. personal_apps/tests/test_radar_prices.py
  15. personal_apps/tests/test_radar_quotes.py
  16. personal_apps/tests/test_radar_universe_directory.py
  17. personal_apps/tests/test_radar_universe_mapping_apply.py
  18. personal_apps/tests/test_radar_universe_reconcile.py

Before staging:
- re-hash all 18 files and require exact agreement with the manifest;
- require the expected modified/untracked status for each path and no missing path;
- require `git diff --check` success and zero diff/status under `personal_apps/models.py` and `personal_apps/migrations`;
- inspect the complete accepted diff and scan it for secrets, private environment values, host data, and accidental generated files;
- stop on any mismatch. Do not repair, reset, clean, or broaden the manifest.

Stage only those 18 paths using an explicit NUL-safe pathspec file built outside the repository. Do not use `git add .`, `git add -A`, directory-wide adds, globs, or a hand-inferred set. Verify the cached path/status set and cached file hashes equal the accepted manifest exactly.

Application commit message:
`feat(radar): add guarded US universe reconciliation`

Exact documentation commit:
After the application commit, stage exactly these documentation paths and no others:
- radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
- radar-design/B-US-UNIVERSE-BRIEF.md
- radar-design/B-US-UNIVERSE-LEDGER.md
- radar-design/B-US-UNIVERSE-EVIDENCE-1-PROMPT.md
- radar-design/B-US-UNIVERSE-EVIDENCE-1-RETURN.md
- radar-design/B-US-UNIVERSE-EVIDENCE-1-RULING.md
- radar-design/B-US-UNIVERSE-EVIDENCE-2-PROMPT.md
- radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md
- radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
- radar-design/B-US-UNIVERSE-AUTHORITY-1-PROMPT.md
- radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md
- radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md
- radar-design/B-US-UNIVERSE-B1-PLAN.md
- radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-PROMPT.md
- radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md
- radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md
- radar-design/B-US-UNIVERSE-B1-CORRECTION-1-PROMPT.md
- radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md
- radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RULING.md
- radar-design/B-US-UNIVERSE-B1-REVIEW-1-PROMPT.md
- radar-design/B-US-UNIVERSE-B1-REVIEW-1-RETURN.md
- radar-design/B-US-UNIVERSE-B1-REVIEW-1-RULING.md
- radar-design/B-US-UNIVERSE-B1-DEPLOY-PROMPT.md

Exclude all `radar-design/artifacts/b-us-universe-*` directories from commits; preserve them locally as evidence. Exclude root/radar-design HANDOFF files, ASSIGNMENTS, MASTERMIND-STATE, roadmaps, WORKFLOW, A/selected-price ledgers and artifacts, unrelated specs, and every other dirty path.

Documentation commit message:
`docs(radar): record US universe B1`

Local gates before staging/commit:
1. Fetch origin. If either expected origin ref differs from 0fdad73, stop without rebase, merge, reset, cherry-pick, or force push.
2. Run the accepted four correction modules only through the DB-free harness:
   `cd personal_apps`
   `py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short`
   Require 153 passed, 0 failed, 0 skipped; the two known `utcnow()` warnings are allowed.
3. Run the offline verifier from the repository root and require 31/31 `ALL OK`:
   `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .`
4. Through the same DB-free harness, run `tests/test_radar_prices.py` and `tests/ha1_unit/test_analysis_contract.py`; require a clean pass. Run only the isolated D8 quote tests selected by these exact names: `test_a_ticker_with_no_mapped_primary_stays_unavailable`, `test_a_mapped_ticker_still_reads_its_legacy_null_snapshot`, `test_an_explicit_unknown_mic_is_read_as_itself`, `test_mapped_and_unmapped_tickers_in_one_batch`, and `test_record_quotes_refuses_a_snapshot_with_no_venue`. Do not run the rest of `test_radar_quotes.py`.
5. Through the same harness, run `tests/selected_price_unit --confcutdir=tests/selected_price_unit` and `tests/test_radar_massive.py --confcutdir=tests`; require the accepted 261 and 18 passes.
6. Compile/import the changed Python modules with bytecode/cache writes disabled. Exercise only `--help`/usage for the new CLIs; do not run either importer or reconciliation against a database.
7. Repeat the fallback sweep. `Listing Exchange` may appear only in rejection tests; `ELSE 'XXXX'` only in the immutable archival migration; no active default `XNAS`/`XXXX` behavior may remain.
8. Do not run the unsafe wider selector or substitute the local `personal_apps` database for an unavailable gate. The 59 DB-backed regressions and live MySQL writer test remain unavailable.

After both commits:
- prove the application commit contains exactly 18 paths and each committed blob matches the accepted hash;
- prove the docs commit contains exactly the 23 paths listed above;
- prove accepted app/docs paths are clean, the index is empty, and every unrelated dirty/untracked path is preserved;
- push the feature branch normally, then fast-forward `main` to the exact two-commit release SHA with a normal push;
- no merge commit, force push, rebase, reset, or history rewrite;
- fetch again and require both origin refs equal the release SHA before production access.

Production preflight:
- verify production HEAD is exactly 0fdad73 and the tracked tree is clean;
- inventory known untracked paths without deleting them;
- verify schema head remains `b7e3f9c1a2d4`;
- verify the six expected services are active/enabled, zero units failed, eight US boards are ready, ingest/producer are healthy, no fetch child is stuck, and recent errors are quiet;
- record Radar feature flags by name and normalized state only: Charts ON, Alpaca ON, Yahoo OFF; do not print credentials or values;
- verify no universe import, seed, reconciliation apply, or directory-maintenance process is active;
- make a normal full database backup through the established wrapper flow and require gzip/hash/off-host-copy proof before replacement.

Before deployment, create private canonical fingerprints for:
- every `radar_instruments` row, with stable primary-key ordering;
- the protected historical DE/EUR datasets used by release A, using the established sanitized fingerprint helper or equivalent count+SHA-only method.

Record only counts and SHA-256 values, never row content. The complete `radar_instruments` fingerprint must remain identical because this release performs no mapping apply. Historical DE/EUR fingerprints must also remain identical. Do not fingerprint continuously changing US quote/board tables as a release invariant.

Backup-first deployment:
1. Use `/root/update_coc.sh` through the established transient-systemd wrapper against the exact fetched release SHA.
2. Require backup completion before application replacement, normal dependency/build work, migration/no-op, service restoration, and producer readiness.
3. There is no migration. Schema must remain `b7e3f9c1a2d4`.
4. Make no environment change. Preserve every `.env` line and permission exactly; do not display or hash secret values.
5. Do not run `seed_radar_universe.py`, `reconcile_radar_universe.py --apply-mappings`, any approval manifest, or any command that creates/updates/deletes universe or mapping rows.
6. Do not copy the retained directory source/current-state evidence to production and do not run a fresh directory fetch.

Production acceptance smoke—code deployment only:
- exact deployed SHA and clean tracked tree;
- all 18 application/test paths match committed blobs and the two new runtime modules plus reconciliation CLI import successfully;
- schema unchanged; complete `radar_instruments` count/hash unchanged; protected DE/EUR fingerprints unchanged;
- six expected services active/enabled, zero failed units, normal worker counts/restarts, producer ready, no stuck child, no new traceback/5xx/error burst;
- exactly eight warm US boards remain ready: All and Discover across 1h/4h/12h/24h;
- `/radar/`, `/radar/hub/`, `/radar/legacy/`, board/ticker APIs, operations, HA1, and selected-price routes retain the accepted US/USD-only behavior;
- Charts ON, Alpaca ON, Yahoo OFF remain unchanged;
- existing mapped US quote/history/grouped-close ingestion remains healthy, with no new MIC-less/fabricated-XNAS behavior and no `radar US quote cycle failed` burst;
- do not manually invoke a provider. Reuse normal service/cache/stored evidence; no account, trading, billing, asset, or paid action;
- confirm no seed/import/apply ran and no `RadarInstrument` row changed.

F6/R1 release carry:
- This deployment does not exercise the real apply. Record that no seed/import ran concurrently because neither ran at all.
- Do not claim the named lock covers the seed/import path.
- Preserve the future-apply rules: fresh dry-run immediately before apply, no concurrent identity writer, report-path preflight, independent stdout/stderr capture, exact manifest/digests/exit status, and post-run row reconciliation.
- A later real apply remains separately owner-authorized and should preferably follow a disposable MariaDB rehearsal.

Rollback:
- Record the pre-release stable SHA 0fdad73 and the new application/docs/release SHAs before production mutation.
- On code/service/smoke failure, durably revert the application commit (and docs commit if desired) on a clean checkout, push normally, and redeploy through the wrapper. Do not use production `git reset --hard` as durable rollback.
- No schema downgrade or data rollback is expected.
- If the `radar_instruments` or protected historical fingerprint changes, stop relevant writers, preserve before/after evidence and the full backup, and stop for Mastermind direction. Do not delete, rewrite, or reverse rows automatically.
- Preserve normal runtime data produced by unrelated services.

Hard limits:
- No product/test fix, manifest adjustment, dependency change, schema/migration edit, environment/config/service-unit/nginx change, data cleanup, importer, mapping apply, fresh directory fetch, provider/account/trading action, B2, or Radar A work.
- No secret/credential/private-row content in commands, logs, evidence, Git, or the return.
- No clean/reset/stash/checkout/discard/delete of user or production work.
- Stop on ref drift, manifest/hash drift, unexpected staged path, unsafe database requirement, backup failure, schema drift, mapping fingerprint change, service instability, or regression. Do not improvise.

Evidence and return:
- Write sanitized release evidence only under `radar-design/artifacts/b-us-universe-b1-release/`.
- Write exactly one return: `radar-design/B-US-UNIVERSE-B1-DEPLOY-RETURN.md`.
- The return/evidence and newest CURRENT notices may remain local/uncommitted, matching release precedent.

The return must include:
- exact base, application commit, docs commit, release SHA, origin refs, and deployed SHA;
- exact 18-path application manifest and 23-path docs manifest with blob/hash proof;
- local gate commands/results and every unavailable gate;
- pre/post Git status and preservation of unrelated dirt;
- backup path/size/SHA/off-host proof without secret contents;
- schema and feature-flag states;
- before/after `radar_instruments` and protected archival counts/hashes only;
- exact deployment/wrapper/build/restart/readiness outcome and outage duration;
- eight-board, routes/APIs/ops/HA1/selected-price/ingest/service/log health;
- explicit proof that no importer, real mapping apply, directory fetch, provider invocation, environment edit, schema change, or mapping-row change occurred;
- F6/R1 future-apply carries;
- rollback targets, whether rollback ran, and actual final state;
- any discrepancy or limitation.

Stop after the return. Do not prepare or run the 114-row apply.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this Deployer return for assignment B-US-UNIVERSE-B1-DEPLOY.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / application commit / docs commit / release SHA: [exact values]
Origin refs and production HEAD: [exact verified values]
Working tree and manifests: [18 app paths, 23 docs paths, unrelated dirt, index]
Binding artifacts: [absolute B1 rulings, review return/ruling, deploy prompt/return/evidence, ledger]

Objective and authorized scope: Exact-manifest B1 code integration and backup-first deployment only; explicitly no 114-row mapping apply or importer.
Git integration: [fetch/no-drift, commits, path/hash proof, normal pushes]
Local gates: [exact safe commands/results and unavailable gates]
Backup and deployment: [backup proof, wrapper/build/migration/restart/readiness, outage]
Production verification: [exact SHA/tree/schema/flags/services/eight boards/routes/APIs/ops/HA1/selected price/ingest/logs]
Data preservation: [radar_instruments and protected DE/EUR before/after counts+hashes; no row content]
No-apply proof: [no seed/import/apply/fetch/provider/env/schema/mapping-row action]
F6/R1 carries: [preserved future-apply safeguards]
Rollback: [targets, whether run, final state]
Evidence attribution: [fresh Deployer evidence vs accepted prior evidence vs inference]
Findings and limitations: [exact discrepancies/unavailable checks]
Actions taken: [commits/push/deploy only within scope]
Protected state: [A, mappings/history, unrelated dirt, secrets]
Subagents: none
Updated artifacts: [absolute return/evidence/current-notice paths]
Requested Mastermind decision: Assess deployment and either close the B1 code release or order rollback; do not authorize or run the real mapping apply.
Next bounded action recommendation: After release closure only, seek separate owner authorization for a disposable MariaDB rehearsal and/or the guarded real mapping apply; do not start B2 automatically.

Read the current handoff, B ledger, all B1 rulings, deploy prompt/return and evidence. Verify Git/artifact evidence, make the release ruling, and update repository continuity. Do not implement fixes, deploy again, or apply mappings yourself.
```

You are Radar's Deployer / release-preflight operator. Return to the Mastermind.
Assignment: MD-SELECTED-PRICE-RELEASE-PREFLIGHT.

Prepare a concrete release decision for the accepted selected-price candidate. This assignment authorizes bounded preflight checks when the owner pastes it, not commit/push/deployment or feature activation. Do not repeat implementation/review. One worker, no subagents.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Base/HEAD: daadf3868caedcb5db858378e919cba68b735f8a
Accepted fingerprint: 0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0

Read HANDOFF.md, radar-design/WORKFLOW.md, MD-SELECTED-PRICE-LEDGER.md, MD-SELECTED-PRICE-FINAL-ACCEPTANCE.md, SPEC and latest rulings (MD-SELECTED-PRICE- prefix). Read RELEASE-RUNBOOK.md, PERF3-RELEASE.md, HA1-US-DAILY-EXPLORE-DEPLOY-RETURN.md and RELEASE-CLOSURE.md under radar-design. Current release evidence overrides obsolete first-install gates; never reopen HA1.

Verify Git/status/fingerprint read-only; preserve all dirt. Fetch/inspect remote Git if needed without altering checkout or branches. Last recorded production target: root@194.164.29.97, checkout /root/coc-stats, wrapper /root/update_coc.sh. Verify current target identity and procedure before any remote scratch work; do not guess another host. Existing SSH credentials only, never log secrets.

Perform these bounded checks in one pass:
1. Establish production HEAD, tracked drift, actual web launcher/venv/cwd, worker count, relevant flag values, schema revision and service health. Read only selected settings, not whole secret environments. Verify current backup/rollback procedure; no service stop/restart, migrations or release now.
2. Verify the accepted subprocess on Linux using the actual venv interpreter and a separately named non-served scratch directory on the verified host. Copy only necessary accepted package files and safe synthetic harness; record hashes. Never replace the serving checkout or install dependencies. Exercise module import/minimal environment, normal output and timeout/reap with synthetic data, bounded to one child at a time. Preserve production imports/DB isolation. If scratch cannot safely reproduce package layout, report the exact limitation without improvising a service.
3. Inspect provider usage conditions from official sources in light of this application's use; distinguish technical access from permission. Do not manufacture a legal conclusion. If permitted by the documented use conditions, run at most four single-attempt public Yahoo chart requests total for one eligible mapped US USD ticker, using the exact candidate epoch request form for 1D/1W. Reuse those responses for normalization/window checks; no broad ticker scan, fallback-host probing, auth/cookie workaround or forced throttle. Stop on 401/403/429 and honor Retry-After. Closed-session behavior only if observable now; do not wait for a market close or claim a fixture proves it. If usage conditions block or remain materially unclear, keep source activation unresolved and continue other checks.
4. Bounded database proof on existing data: read-only credentials/transactions where available; no fixture writes, DDL, migrations, destructive pytest or restoration. Check actual MariaDB timeout mechanism and bounded EXPLAIN for the new reader queries on one eligible ticker/window. Use a session-scoped <=1s timeout and a harmless bounded SELECT SLEEP to verify timeout/recovery only if appropriate to existing host policy; restore session settings/close connection. At most a small fixed set of SELECTs, no whole-universe scan or load benchmark. Do not run the candidate reader if its query plan is unsafe; report concrete issue. Existing local DBs are not test targets.

Keep both production flags unchanged. Synthetic probes are not production API/browser smoke; record that distinction. Total checks bounded, serial; no new dependency/service, no production application edits. Remove only your verified exact scratch directory after checks, preserving sanitized evidence locally and recording process cleanup. Never touch main/other worktrees, B1C/5021, promotion/5033, DB3306/3399, HA1/3461 or C:/Users/michi/.radar-ha1-local-qa.

Deliver one decision-ready packet:
- Exact candidate/main/production commits and drift; accepted fingerprint.
- Each remaining Linux/provider/DB/topology question: verified facts, unverified facts or concrete blocker, with commands/results and source links.
- Proposed release flags and why: both OFF, charts ON/Yahoo OFF (stored fallback), or both ON only with supporting evidence. Do not change them.
- Exact existing backup-first deployment and rollback sequence for this candidate: narrow staging scope, safe integration without dirty-main overwrite, normal push, wrapper, flags/service ordering and post-release smoke. No new migration owner. Rollback target must be freshly verified production SHA; flag-off stops new admissions, account for any current child deadline/cleanup and restart behavior.
- Preserve baseline failures and accepted local QA; no full review/test rerun. If a concrete runtime defect appears, return it without patching or starting a new review cycle.

Write radar-design/MD-SELECTED-PRICE-RELEASE-PREFLIGHT-RETURN.md and sanitized evidence under radar-design/artifacts/md-selected-price-release-preflight/. Update candidate HANDOFF/ledger current notices. No commit/push/deploy/activation. Stop with recommended release decision and exact remaining approval scope.

MANDATORY FINAL OUTPUT — complete populated copy/paste return prompt:
You are Radar's Mastermind / Overview. Assess MD-SELECTED-PRICE-RELEASE-PREFLIGHT.
Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch/HEAD/fingerprint: [verified]. Remote main/production SHA and target: [verified].
Report: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-RELEASE-PREFLIGHT-RETURN.md
Linux/provider/usage/DB/topology findings: [facts, limits, blockers].
Fresh checks and provider request count: [commands/results]. Carried evidence: [attributed].
Recommended flags and exact deployment/rollback plan: [summary and artifact paths].
Actions/dirty ownership/scratch cleanup: [facts]. Production flags/services unchanged: [verified].
Requested decision: [specific release scope ready for owner approval, or concrete issue].
HA1 closed. No workers dispatched, code fixes, commit/push/deploy or activation performed. Subagents: none.
Read artifacts/Git and update continuity; do not implement, deploy or dispatch automatically.
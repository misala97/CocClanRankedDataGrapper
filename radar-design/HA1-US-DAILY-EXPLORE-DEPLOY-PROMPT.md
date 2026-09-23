You are Radar's Deployer. Return your result to the Mastermind.
Assignment: HA1-US-DAILY-EXPLORE-DEPLOY.

Owner explicitly approved deployment with "Ok lets go" after final HA1 acceptance. This authorizes scoped commit/integration/normal push, the established backup-first deployment, smoke verification and necessary rollback. Do not ask for this approval again. Do not dispatch workers/subagents.

Candidate: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Branch codex/radar-ha1-us-daily-explore
Expected base/HEAD 1ac39fe4e1a5dd7d04830e96a96563183687b447; no upstream; accepted changes uncommitted.
Accepted source/build fingerprint: 6588be5e8dabf471befda62addc380d0775703948a5e7d22a9d96f55a2e50886.

Read root/radar-design handoffs and HA1 ledger completely; radar-design/WORKFLOW.md, HA1-US-DAILY-EXPLORE-FINAL-ACCEPTANCE.md, FINAL-UI-CHECK-RETURN.md, LOCAL-QA-RULING.md and HA1 spec/plan/ownership reports (all HA1 filenames have HA1-US-DAILY-EXPLORE- prefix). Read RELEASE-RUNBOOK.md, PERF3-RELEASE.md and latest promotion deployment evidence. Current release procedure overrides historical first-install instructions.

Verify Git path/branch/HEAD/status/diff/log and accepted fingerprint before changes. Use per-command safe.directory. Most HA1 files are untracked: inventory explicitly. Preserve unrelated dirty planner/research files and other worktrees. Stage only accepted HA1 application changes, relevant tests and intentionally selected HA1 release/continuity documents after reviewing the exact staged diff. Do not use blanket git add, force-push or destructive reset/clean. Do not include runtime scripts/artifacts/secrets/registries/DB files/ignored dist by accident; build through established process.

Fetch and inspect current remote state. Integrate accepted candidate with current main using the established safe workflow without overwriting dirty main. Resolve only routine scoped integration issues; substantive drift or defects require a concrete return, not unrelated fixes. Record exact candidate/integrated/release SHA. No new full review or repeated QA loop: accepted evidence carries forward; run release-required checks and checks justified by integration changes.

Production destination was last recorded as root@194.164.29.97, deployment wrapper /root/update_coc.sh; verify from current release configuration and remote identity before mutation. Do not infer from an old host or deploy elsewhere. Use the existing backup-first release procedure, fresh recoverable backup, matching build, established stop/start ordering and rollback. Never bypass the wrapper or introduce parallel migration ownership.

HA1 has no new schema/provider/capture change. Preserve capture OFF, shared boards ON, current host access policy and migration b7e3f9c1a2d4 unless fresh evidence shows unrelated drift requiring assessment. Do not reset/stamp schema to old expectations. No new provider calls, price-system overhaul or polishing deferred F2/header issues.

After release verify exact deployed SHA, application/services health, hub/root/alias/legacy, existing Chatter and selected-stock Analysis on bounded existing data: range/identity, daily price/count response, expected refusal/auth behavior. Use authorized existing verification methods; never fabricate a user session or seed production fixtures. Separate authenticated checks that require owner interaction from passing checks. No broad production scan or synthetic benchmark. If deployment fails, follow established rollback and verify recovery.

Protect local DB3306/3399, B1C5021/promotion5033, retained C:/Users/michi/.radar-ha1-local-qa, main/other worktrees and all unrelated artifacts. No cleanup of the disappeared dashboard.lock. Secrets never go into logs/commits.

Write radar-design/HA1-US-DAILY-EXPLORE-DEPLOY-RETURN.md and release evidence. Update both handoffs, HA1 ledger, MASTERMIND-STATE, ASSIGNMENTS and roadmap with exact final Git/production status, backup/build/release/smoke evidence and any residual work. Stop after verified deployment or concrete blocker/rollback; do not launch the next price work.

Final response MUST include this fully populated copy/paste return:
You are Radar's Mastermind / Overview. Assess HA1-US-DAILY-EXPLORE-DEPLOY.
Workspace/branch/base/final SHAs: [verified]
Integrated/pushed/deployed SHA and target: [exact]
Scoped changes and preserved dirt: [files/groups]
Backup/release/build evidence: [paths/results]
Production smoke and health: [executed results; unverified items explicit]
Capture/shared-board/schema state: [fresh facts vs attribution]
Rollback/blockers/residual work: [details]
Updated continuity/release artifacts: [absolute paths]
Requested decision: close HA1 release if verified; next product priority is selected-instrument price improvements. Do not redispatch accepted implementation/reviews.


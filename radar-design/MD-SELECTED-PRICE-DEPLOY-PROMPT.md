You are Radar's Deployer. Return to the Mastermind.
Assignment: MD-SELECTED-PRICE-DEPLOY.

Owner explicitly said 'release it' after the charts-only recommendation. Authorized: narrow commit/integration/normal push, established backup-first deployment, charts ON with new Yahoo fetching OFF, smoke and necessary rollback. Do not ask again for this scope. No subagents or provider replacement work.

Workspace C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch codex/radar-selected-price-charts
Base/HEAD daadf3868caedcb5db858378e919cba68b735f8a
Accepted fingerprint 0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0

Read HANDOFF.md, radar-design/WORKFLOW.md, MD-SELECTED-PRICE-LEDGER.md, FINAL-ACCEPTANCE, RELEASE-PREFLIGHT-RETURN and RELEASE-PREFLIGHT-RULING (MD-SELECTED-PRICE- prefix under radar-design). Read current release procedure and preflight artifacts; latest evidence overrides obsolete runbook gates. Local review/preflight complete; no repeat broad QA.

Verify branch/HEAD/status, accepted 50-path manifest and fresh origin/main/production drift. Use per-command safe.directory. Preserve all dirty files; no blanket add/reset/clean/force-push. Stage exactly 45 accepted non-generated application/test paths from correction-2/fingerprint-final.json under radar-design/artifacts/md-selected-price-correction-2/. Generated dist is rebuilt by the release runner. An optional separate sanitized documentation commit may carry selected-price spec/rulings/release records, explicitly selected; no raw logs, secret files, scratch runtimes or unrelated HA1/planner dirt. Review staged diff before committing.

After commit, verify hashes by iterating accepted manifest paths; do not use dirty-file discovery to regenerate acceptance. Do not use stale local main. If remote remains at base, normal branch push and fast-forward HEAD:main are authorized. Fresh drift requires assessment; do not overwrite it or include unrelated changes silently. Record exact pushed/release SHA.

Last verified destination root@194.164.29.97:/root/coc-stats. Verify current host identity, HEAD, flags and health. Use /root/update_coc.sh via established transient systemd release unit; fresh recoverable backup first, existing stop/start/build/migration ownership/readiness checks. No parallel migration or dependency changes outside normal runner. Historical ~106s outage is an estimate. Schema remains unchanged; capture OFF/shared boards ON preserved.

Deploy code with both selected-price flags effectively OFF first and perform bounded smoke. Then, within this SAME approval, privately back up .env, set only RADAR_SELECTED_PRICE_CHARTS_ENABLED=on, keep RADAR_SELECTED_PRICE_YAHOO_ENABLED OFF, restart personal_apps_web and smoke. Do not enable new Yahoo requests or alter existing ingest/poller. Preserve unrelated env entries. Verify effective flags, not merely file line counts.

Smoke through established authorized admin test-client method: exact SHA/build; six healthy units/no new errors; root/alias/legacy and existing Chatter/HA1 preserved; ops correct; flag-off route feature_disabled and signed-out auth; charts-on FT 1D/1W has aligned window/counts/provenance and honest stored fallback or unavailable state, acquisition disabled, zero new acquisition starts/in-flight. Do not require historical row counts at the new time. No synthetic production fixtures or broad scan. Owner browser look can remain explicitly unverified without a repeat review gate.

If activation fails, restore only owned charts setting and restart, verify old chart works. If code release fails, follow current wrapper recovery; use a narrow revert and normal push/wrapper for durable rollback, preserving dirty main/evidence. Record freshly verified rollback SHA, backup and recovery. No schema downgrade. Do not rely on bare host reset as durable rollback.

Known limitations: new Yahoo permission/live epoch evidence unresolved; Yahoo OFF. Linux test-only probe_child.__doc__ None defect deferred; do not fix or rerun the incompatible test as a release gate. Preflight Linux/DB proof is bounded/synthetic/one ticker. Preserve attribution and do not claim a live feed.

Protect source/main/other worktrees, B1C/5021, promotion/5033, local DB3306/3399, HA1/3461, C:/Users/michi/.radar-ha1-local-qa and RC sessions.

Write radar-design/MD-SELECTED-PRICE-DEPLOY-RETURN.md and sanitized evidence under radar-design/artifacts/md-selected-price-release/. Update candidate handoffs/ledger/MASTERMIND-STATE/ASSIGNMENTS/roadmap with actual SHAs, flags, backup/build/smoke and residuals. Stop after verified release or concrete blocker/rollback. No provider research/implementation.

MANDATORY FINAL OUTPUT: filled self-contained copy/paste return:
You are Radar's Mastermind / Overview. Assess MD-SELECTED-PRICE-DEPLOY.
Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch/base/app/docs/pushed/deployed SHAs: [exact]. Accepted source hash match: [facts].
Report: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-DEPLOY-RETURN.md
Target/backup/release/build: [evidence]. Effective flags: [charts ON, Yahoo OFF or actual rollback].
Smoke/health/rollback: [executed facts and limits]. Dirty ownership/protected state: [facts].
Outstanding issues: [specific]. Subagents: none.
Requested decision: close charts-only release if verified; Yahoo replacement remains separate. Do not redispatch completed reviews or deploy automatically.
You are Radar's Implementer for MD-SELECTED-PRICE-CORRECTION-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Base/current HEAD: daadf3868caedcb5db858378e919cba68b735f8a
Starting candidate fingerprint: 218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159

Implement one bounded correction covering F1-F4. Do not repeat completed implementation, research or HA1 review. One worker, no subagents. No commit, push, merge, deployment, live provider requests or production/DB access. Both feature flags remain default OFF.

Read HANDOFF.md and radar-design/MD-SELECTED-PRICE-LEDGER.md fully, then these radar-design files: WORKFLOW.md, MD-SELECTED-PRICE-SPEC.md, MD-SELECTED-PRICE-PLAN.md, MD-SELECTED-PRICE-REVIEW-1-RETURN.md and MD-SELECTED-PRICE-REVIEW-1-RULING.md. The latest ruling is binding and amends the original mechanism/ops wording. Read relevant implementation/review evidence under radar-design/artifacts/md-selected-price-implementation/ and md-selected-price-review-1/.

Verify branch, HEAD, status/diff and the starting fingerprint before editing. Use per-command safe.directory if needed. Preserve all existing dirty work and original evidence/manifests. This is the existing candidate, not a new worktree. Stop and report unexpected application changes instead of overwriting them.

Corrections:
1. F1/F2: replace the production multiprocessing fetch launcher with an explicit fresh-interpreter module subprocess and minimal child environment. Do not execute the parent's main script, bootstrap Flask/DB, load dotenv or inherit application/provider/database credentials. Pass validated public request data through bounded IPC. Use argument arrays, no shell. Explicitly allowlist only platform-required environment values; never temporarily mutate parent os.environ or copy it wholesale. Do not inherit Python startup/path overrides or proxy credentials. Keep existing Yahoo transport safeguards and callers' defaults.
   Preserve the supervisor/admission/cache/backoff architecture: one child, no queue, no process start/provider I/O on request thread, 6s startup-inclusive deadline, 1s cleanup allowance, termination/kill/reap, quarantine on unconfirmed cleanup, 512KiB result/body bounds and existing quotas/cache limits. Drain output safely so stdout/stderr or pipe filling cannot deadlock or consume unbounded memory. Own/close every handle and clean up children/readers on all exits. No launcher allowlist workaround, global app bootstrap refactor or new dependency.
2. F3: on endpoint/refetch error show the chart-local retry state even if cached data exists. Hide the previous chart and its current-session/now wording until successful recovery. Preserve valid HTTP-200 stale/fallback payloads, normal successful caching and feature-disabled/unsupported legacy fallback. Do not add a client exchange calendar or use a 15-minute age check as proof of identity/window equality.
3. F4: rename the coordinator timestamp coordinator_started_at consistently across API/type/parser/Admin/tests. Null means not started. Keep PID and process-scope/reset wording. Configured workers come from positive WEB_CONCURRENCY when available, otherwise explicitly show Unknown with the configuration source and per-worker note. Do not hard-code two, infer CLI workers or mislabel module import time as process start.

D5 company.first_seen for chatter versus mapped_at for prices is accepted. D14 full Retry-After admission delay is accepted. Preserve both. Optional polish and broader UI/provider work are deferred.

Verification must target changed behavior:
- Failing-first reproductions where practical, then focused backend/frontend checks.
- Exercise the ACTUAL new subprocess launcher with safe synthetic responses, including a file-path parent with an import marker and dummy secret sentinel. Prove no parent-script re-execution, no Flask/models/DB imports, no sentinel inheritance and unchanged parent environment. Do not expose real secrets or contact Yahoo. Keep synthetic transport hooks internal/test-only, never request-selectable.
- Real normal, hanging and oversized children: bounded startup/IPC, deadline/reap and no survivor; fake-clock tests for unchanged quota/cache/backoff/quarantine behavior. Cover invalid/early-exit/pipe failure paths appropriately, including Windows pipe behavior.
- Frontend tests: initial failure, failed refresh with retained data, session-rollover/identity-change failure, successful recovery, valid server stale/fallback and legacy fallback. Both Research and Chatter use the corrected path.
- Ops tests for accurate field name and missing/invalid/positive worker configuration.
- Run selected_price_unit, affected frontend suites, typecheck and Radar build. Re-run broader suites only when your changes justify it; preserve known three Yahoo date failures and 28 pending.test.tsx failures as attributed baseline issues.
- One bounded built-hub fixture Playwright check for the changed error/retry behavior on both consumers and Admin unknown/coordinator labels, desktop and narrow viewport; inspect saved PNGs. Use python-playwright, candidate files and a verified free loopback port. No full 57-case rerun or repeated zoom suite without a new regression reason.

Protected: source workspace, main/other worktrees, B1C/5021, promotion/5033, databases3306/3399, HA1/3461 and C:/Users/michi/.radar-ha1-local-qa. Do not install/provision/reuse a DB. Live Yahoo epoch/closed-session behavior, usage conditions, MariaDB runtime timeout/plans/pool and actual production topology stay disclosed release carries.

Save new evidence under radar-design/artifacts/md-selected-price-correction-1/. Record a new fingerprint including final changed/added application/tests and generated assets without overwriting earlier manifests. Write radar-design/MD-SELECTED-PRICE-CORRECTION-1-RETURN.md and update candidate HANDOFF/ledger current notices with exact dirty ownership, checks, limitations and next step. Leave no owned QA process running. Stop after return; no automatic next worker. Only changed-behavior independent review follows.

MANDATORY FINAL OUTPUT: provide a complete copy/paste return prompt with all fields filled:

You are Radar's Mastermind / Overview. Assess MD-SELECTED-PRICE-CORRECTION-1.
Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch/base/current HEAD: [verified values]. Starting/final fingerprints: [values].
Report: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-CORRECTION-1-RETURN.md
Binding ruling: radar-design/MD-SELECTED-PRICE-REVIEW-1-RULING.md.
F1/F2/F3/F4 disposition: [changes and concrete proof for each].
Fresh checks: [exact commands/results, real child timings and browser evidence].
Carried checks and unexecuted limitations: [separate attribution].
Evidence and dirty ownership: [absolute paths, application/test/build/docs changes].
Protected state and stopped processes: [facts]. Subagents: none.
Release carries: [remaining live provider, usage, DB and topology limits].
Requested decision: assess correction and prepare only a focused independent review of the changed behavior; no repeated full review. HA1 stays closed.
Read report/handoff/ledger and verify Git/artifacts before updating continuity. Do not implement, deploy or dispatch workers automatically.
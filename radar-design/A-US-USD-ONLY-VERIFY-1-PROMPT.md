# Copy/paste prompt — A-US-USD-ONLY-VERIFY-1

```text
You are Radar's independent Verifier / QA. Return your result to the Mastermind.

Assignment ID: A-US-USD-ONLY-VERIFY-1

Objective:
Independently verify the completeness and safety of the Researcher's repository inventory for removing all active German/EU/EUR functionality from Radar while preserving US behavior and historical database compatibility. Challenge omissions, false deletion recommendations, dormant-support leftovers and test gaps. This is a fresh read-only verification assignment, not implementation and not an implementation plan.

Independence requirement:
- You must not be the Researcher who produced A-US-USD-ONLY-RESEARCH-1-RETURN.md.
- Do not rely on the Researcher's searches as proof. Reproduce the important traces from repository evidence and report agreements and disagreements.
- No subagents.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / expected current HEAD:
codex/radar-selected-price-charts
38591e0f5e98faccb5228d84d1677843fcdb2aea

Before acting:
- Verify workspace, branch, HEAD, origin refs, status, diff and recent log with per-command safe.directory.
- Preserve all dirty and untracked files. The spec, ledger, Researcher return/ruling and this prompt are intentionally local and uncommitted.
- If Git or code evidence conflicts with continuity prose, evidence wins and the discrepancy must be reported.
- Do not touch another worktree, production, databases, services, environment files, credentials or provider accounts.

Read fully, in this order:
1. C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/WORKFLOW.md
2. .../radar-design/A-US-USD-ONLY-SPEC.md
3. .../radar-design/A-US-USD-ONLY-LEDGER.md
4. .../radar-design/A-US-USD-ONLY-RESEARCH-1-PROMPT.md
5. .../radar-design/A-US-USD-ONLY-RESEARCH-1-RETURN.md
6. .../radar-design/A-US-USD-ONLY-RESEARCH-1-RULING.md
7. .../radar-design/US-USD-ONLY-DECISION.md
8. .../radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
9. .../radar-design/MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md
10. Current notices at the top of .../radar-design/MASTERMIND-STATE.md, .../radar-design/ASSIGNMENTS.md and the workspace-root HANDOFF.md.

Binding target:
- Radar only: US listings and native USD prices everywhere, with no market selector or German/EU/EUR provider, formatter, fallback, job, mapping path, FX path or supported mode.
- Omitted market input uses US on every Radar HTTP surface, including selected price unless you identify a concrete compatibility blocker for Mastermind ruling.
- Explicit `market=de` or any unsupported market returns a clear client error on API and HTML shell routes. It is never normalized, redirected or swallowed into US.
- Historical German/EUR rows, including operational journal/cycle/mapping/FX rows, stay untouched and inert. Active reads/writes/retention must not reach them. Migrations stay immutable.
- Preserve Alpaca selected-price acquisition/rendering, US grouped-close ingestion, US quote/history behavior, HA1 and unrelated Radar behavior.
- Do not alter Gym's German UI or unrelated `Europe/Berlin` timezone behavior.
- The 146 unmapped US identities remain explicit workstream-B debt, not something A hides or solves.

Mandatory independent checks:
1. Reconstruct each active flow without trusting the return: browser controls and URL state; HTML/API routes; board/shared store; quote/history/leaderboard/detail reads; scheduler/CLI; board producer and observations; providers; mapping/reference data; FX/conversion/fallback; retention; operations/admin rendering.
2. Search all Radar-owned backend, frontend, templates, scripts, models, migrations, tests, deployment files and relevant configuration for both literal and semantic DE/EU/EUR aliases. Identify any path/symbol the Researcher missed or classified incorrectly.
3. For every DELETE recommendation, prove there is no surviving US caller/import/runtime role. Pay special attention to `market_data.py`, `run_radar_ingest.py`, `history.py`, `instruments.py`, provider modules, report/backfill scripts and frontend shared types.
4. For every SURGICAL recommendation, identify the precise protected US behavior and whether the proposed boundary is sufficient.
5. Verify the archival schema claim: which ORM classes/constraint strings must remain for an existing migrated database and autogenerate stability? Specifically determine whether active Python source sets must retain `deutsche_boerse_delayed`, or whether only schema/ORM metadata needs it.
6. Verify historical inertness. Find every read, write, prune, cascade or cleanup that can touch existing DE/EUR rows. Confirm the ruling that all such retention paths must stop. Check whether deleting a parent/model path could trigger cascades indirectly.
7. Verify input contracts across every HTTP route. Flag any proposal or existing test that silently maps explicit `market=de` to US. Determine the narrow safe change for selected-price omission→US and explicit unsupported→400 without disturbing its protected acquisition behavior.
8. Verify cache/archive compatibility: board `KEY_VERSION`, observation `SCHEMA_VERSION`, stored query parsing, producer warming and old-row readability. State whether both version bumps are necessary and sufficient.
9. Verify configuration/deployment cleanup: all DE-only env names and job ids; which are definitely unused after code removal; whether any listed key has a non-DE consumer. Code must not read them; later deployment should remove verified DE-only variables after backup.
10. Audit the test disposition. Identify tests incorrectly proposed for deletion, missing rejection/regression tests, false baseline claims and the smallest sufficient gates protecting US selected price, grouped closes, US quotes/history, migrations and frontend behavior.
11. Audit the residual-search checklist for blind spots and excessive allowed categories. Every permitted residual must be necessary for immutable history, archival schema compatibility, an intentional rejection test or unrelated product behavior.
12. Evaluate the six proposed slices only as planning inputs. Report dependency/order corrections, but do not write an implementation plan.

Known issues you must explicitly rule on:
- Research section 4 says HTML `?market=de` may open US and frontend tests may normalize it. This conflicts with the binding ruling; verification must require explicit error behavior.
- Research says the selected-price endpoint may continue requiring `market`. Binding rule is omission→US and explicit non-US→400; verify the safe contract change.
- Research originally offered continued pruning of some DE operational tables. Binding rule is that all existing DE/EUR rows become untouched archival data.
- Research recommends retaining `deutsche_boerse_delayed` in active Python source sets. Prove whether that is necessary; do not retain dormant acceptance vocabulary by convenience.
- Research mentions 28 pre-existing frontend failures from continuity evidence. Verify the exact current baseline source and do not convert an unverified historical statement into an acceptance allowance.
- Research suggests possibly retaining `_active_us_instruments` for B. Keep it only if current A-protected US code uses it; future usefulness alone is insufficient.

Authorized actions:
- Read files and Git metadata.
- Run static searches, import/reference checks and non-mutating inspection commands.
- Run narrowly selected existing tests or collection commands only when needed to verify a claim, provided they use the documented disposable/local test setup and cannot reach production. If DB identity cannot be proved safe, do not run DB-backed tests; report them as unavailable.
- Create only `radar-design/A-US-USD-ONLY-VERIFY-1-RETURN.md`.

Not authorized:
- Any application, test, migration, script, config, dependency, environment, spec, ledger or handoff edit other than the single return file.
- Database mutation, generated migration, production access, provider/network call, credential inspection, account action or service change.
- File deletion/move, formatting rewrite, commit, push, deployment, implementation-plan writing or worker dispatch.
- Subagents.

Required return structure:
1. Verdict: PASS, PASS WITH FINDINGS or FAIL for inventory completeness and removal safety. Do not treat PASS WITH FINDINGS as implementation authorization.
2. Independent evidence summary with exact path:symbol/line citations and commands.
3. Coverage matrix by subsystem and any missed/misclassified items.
4. Deletion-safety matrix for every whole-file/module removal.
5. Shared-US preservation findings.
6. Historical schema/data/retention findings, including cascades and active source vocabulary.
7. API/HTML/frontend input-contract findings, including selected price.
8. Cache/archive versioning and deployment/config findings.
9. Test/residual-search assessment.
10. Findings ordered by Critical / Important / Minor, each with evidence and the exact correction needed in the later plan. If none, say none.
11. Explicit statement of what you did not verify and why.
12. Confirmation that no implementation/config/schema/DB/production/commit/deploy action occurred.

Stop condition:
Stop when the Mastermind can decide whether the repository inventory is complete enough to write a phased implementation plan without risking hidden DE functionality, historical-row mutation or US regressions. Do not perform the removal.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this independent Verifier/QA return for assignment A-US-USD-ONLY-VERIFY-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [dirty/untracked paths and ownership; committed/pushed status]
Binding artifacts: [absolute spec, ledger, Researcher return/ruling, Verifier prompt and return paths]

Objective and authorized scope: Independently verify the completeness and safety of the Radar US/USD-only removal inventory; read-only, no implementation.
Verdict: [PASS / PASS WITH FINDINGS / FAIL, with one-sentence basis]
Completed work: [independent searches, traces, checks and matrices]
Evidence: [exact commands/results and path:symbol or path:line citations]
Evidence attribution: [fresh Verifier execution vs repository reports vs inference]
Coverage and limitations: [subsystems inspected and anything unavailable]
Findings: [Critical/Important/Minor, or explicitly none]
Required planning corrections: [exact corrections before an implementation prompt]
Actions taken: [single return file; explicitly no app/test/config/schema/DB/production/commit/deploy action]
Protected state: [US paths, historical data/migrations, other worktrees, credentials and dirty files]
Subagents: none
Updated artifacts: [absolute local/uncommitted return path]
Requested Mastermind decision: [accept verification and write phased plan / require bounded research correction]
Next bounded action recommendation: [one action; never implementation unless Mastermind first accepts Gate 2 and prepares the plan]

Read the current handoff, ledger, Researcher ruling and Verifier return; verify relevant Git/artifact evidence; make the product ruling and update planning continuity. Do not implement, deploy or dispatch workers automatically.
```


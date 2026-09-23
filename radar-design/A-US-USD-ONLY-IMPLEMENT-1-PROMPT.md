# Copy/paste prompt — A-US-USD-ONLY-IMPLEMENT-1

```text
You are Radar's Implementer. Return your result to the Mastermind.

Assignment ID: A-US-USD-ONLY-IMPLEMENT-1

Objective:
Execute the binding phased plan to remove every active German/EU/EUR path from Radar and leave one thoroughly verified, uncommitted US-listings/USD-price-only candidate. Preserve historical rows/schema and all protected US behavior. This is implementation and local verification only, not deployment.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / expected base and current HEAD:
codex/radar-selected-price-charts
38591e0f5e98faccb5228d84d1677843fcdb2aea

Required execution method:
- Use the `superpowers:executing-plans` skill and execute `A-US-USD-ONLY-PLAN.md` task-by-task.
- No subagents. One Implementer owns the complete candidate.
- Work test-first and record a checkpoint after every task. Do not commit between tasks; the final candidate remains uncommitted for independent review.

Before acting:
- Verify workspace, branch, HEAD, available origin refs, status, diff and recent log with per-command safe.directory.
- Preserve every pre-existing modified/untracked file. The A planning documents, selected-price closure and artifacts are intentional and must not be overwritten.
- Read the following completely, in order:
  1. radar-design/WORKFLOW.md
  2. radar-design/A-US-USD-ONLY-SPEC.md
  3. radar-design/A-US-USD-ONLY-LEDGER.md
  4. radar-design/A-US-USD-ONLY-RESEARCH-1-RETURN.md
  5. radar-design/A-US-USD-ONLY-RESEARCH-1-RULING.md
  6. radar-design/A-US-USD-ONLY-VERIFY-1-RETURN.md
  7. radar-design/A-US-USD-ONLY-VERIFY-1-RULING.md
  8. radar-design/A-US-USD-ONLY-PLAN.md
  9. radar-design/A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md
  10. radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
  11. radar-design/MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md
  12. Current notices at the top of radar-design/MASTERMIND-STATE.md, radar-design/ASSIGNMENTS.md and root HANDOFF.md.
- If the plan conflicts with Git/code evidence, stop that slice and report the exact discrepancy. Do not silently reinterpret product scope.

Binding outcome:
- Radar UI has no market selector and no Germany/EU/EUR/Xetra/Tradegate/DBAG/ECB/fallback/conversion behavior.
- Active prices are native US/USD and display in US dollar format. Missing US data stays unavailable.
- Omitted market input means US everywhere. Explicit non-US input returns clear 400 on APIs and HTML routes; never silently opens US.
- Old DE/EUR rows and schema remain untouched and inert. No active read, write or retention query may reach them.
- Remove German provider/mapping/FX/jobs/config/scripts/tests atomically while preserving US shared code.
- Keep exactly eight proactively warmed backend boards: US only, both existing segment selections, and every supported window `(1, 4, 12, 24)`.

Authorized actions:
- Modify/delete exactly the application, test, script, fixture and CSS/TypeScript paths covered by the plan.
- Add focused rejection/regression tests and sanitized local evidence.
- Run DB-free tests, typecheck, build, static searches and Python Playwright.
- Run DB-backed tests only after proving the target is exactly the documented disposable `personal_apps_radar_wt`; never use `personal_apps`, production or an unverified database. Record the known missing-FK limitation.
- Create `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md` and evidence under `radar-design/artifacts/a-us-usd-only-implement-1/`.
- Update only current-status sections of `radar-design/A-US-USD-ONLY-LEDGER.md` and root `HANDOFF.md` after verification.

Not authorized:
- Commit, stage, push, merge, deploy, production/VPS access, service restart, flag or environment change, credential inspection, provider/network request, account action, schema migration, migration edit or historical-row mutation.
- Editing unrelated Gym language behavior, host timezone behavior, encoder/ranking/headline work or workstream B.
- Fixing the 28 pre-existing `hub/pending.test.tsx` failures or any unrelated failure.
- Creating a replacement US mapper; the 146 US mapping gap remains B.
- Subagents.

Protected state:
- `models.py` archival tables/CHECK strings and every existing migration.
- Alpaca selected-price acquisition, reader, fallback, admission, geometry and production flag state except the two query-input expectations specified by the plan.
- US grouped-close transactionality and report gate; US quotes/history; provider-session state; HA1; Twelve Data US key/path.
- All pre-existing dirty/untracked files and other worktrees.

Verification and evidence:
- Follow every task's focused failing/pass gates and final residual sweep.
- Reproduce exact `hub/pending.test.tsx` failing identities before edits and compare after; failure count alone is insufficient.
- `git diff --check` must pass. `models.py` and `migrations/` must have no diff.
- Use batched Python Playwright, inspect screenshots, and prove no control gap/hidden tab stop/overflow at 1200, 390 and 320 px.
- If a required gate is unsafe or environmentally unavailable, mark it unavailable with evidence; never redirect it to a less-safe database or claim it passed.

Stop condition:
Stop with one complete local candidate only when every active DE/EUR path in the residual checklist is removed or categorized, protected US gates are green, exact baseline deltas are documented and the return is complete. Do not commit or deploy. If a binding conflict prevents a safe candidate, stop and return the blocker rather than broadening scope.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this Implementer return for assignment A-US-USD-ONLY-IMPLEMENT-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [all modified/deleted/untracked paths, ownership, staged/committed/pushed status]
Binding artifacts: [absolute spec, rulings, plan, ledger, implementation return and evidence paths]

Objective and authorized scope: Remove all active Radar German/EU/EUR functionality and produce a locally verified US/USD-only candidate; no commit or deployment.
Completed work: [task-by-task implementation and deletions]
Evidence: [exact commands, pass/fail/skip counts, import checks, residual-search results, screenshots]
Evidence attribution: [fresh worker execution vs prior reports vs inference]
Database safety: [target identity, tests run, known missing-FK limit, explicitly no production access]
Frontend baseline comparison: [exact pre/post pending.test.tsx failing identities and all focused/full results]
Findings and limitations: [remaining allowed residuals, unavailable gates, B mapping gap]
Actions taken: [files changed/deleted/created; explicitly no commit/push/deploy/config/schema/DB-history mutation]
Protected state: [Alpaca selected price, US grouped/quotes/history, HA1, models/migrations, other dirty work]
Subagents: none
Updated artifacts: [absolute local/uncommitted paths]
Requested Mastermind decision: Assess the candidate and prepare one fresh independent Reviewer/QA prompt; do not commit or deploy.
Next bounded action recommendation: One fresh independent Reviewer/QA inspects the complete diff and evidence against the binding plan.

Read the current handoff, ledger, spec, rulings, plan and implementation return; verify Git/artifact evidence; make the product ruling and update planning continuity. Do not implement fixes, commit or deploy yourself.
```

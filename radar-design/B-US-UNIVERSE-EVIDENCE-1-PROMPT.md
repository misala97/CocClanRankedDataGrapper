# Assignment Prompt — `B-US-UNIVERSE-EVIDENCE-1`

You are Radar's Researcher. Return your result to the Mastermind.

## Assignment

- Stable ID: `B-US-UNIVERSE-EVIDENCE-1`
- Objective: reconstruct and classify the exact 146 unmapped-new, 51 changed, and 87 absent US-listing cohorts from the completed 2026-09-16 directory refresh, then propose an evidence-backed mapping contract and failure-safe daily maintenance design. Do not implement or mutate anything.
- Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- Expected `HEAD`, `origin/main`, and feature ref: `0fdad7327292cd3cd0b62dbe3f6b460873263053`

## Start gate

1. Verify the workspace, branch, three refs, index, and tracked/untracked dirt. Preserve every pre-existing or unrelated modification.
2. If workspace, branch, or refs differ, stop and report the discrepancy; do not repair Git state.
3. Confirm whether the owner's dispatch explicitly authorizes read-only production-host evidence, bounded `SELECT`-only queries, and/or fresh official-directory reads. Do not use a category not explicitly authorized. Complete the repository portion and report any missing authority precisely.

## Required reading

Read these completely before drawing conclusions:

1. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\HANDOFF.md`
2. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-BRIEF.md`
3. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-LEDGER.md`
4. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\US-UNIVERSE-REFRESH-2026-09-16.md`
5. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\A-US-USD-ONLY-RELEASE-CLOSURE.md`
6. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\A-US-USD-ONLY-LEDGER.md`
7. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\WORKFLOW.md`
8. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\HANDOFF.md`
9. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\ASSIGNMENTS.md`
10. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\MASTERMIND-STATE.md`

Inspect all relevant code/schema evidence, including `personal_apps/scripts/seed_radar_universe.py`, `personal_apps/features/radar/universe.py`, Radar universe/instrument models and migrations, active mapping consumers in market-data/quote/history/ingest paths, related tests, and retained refresh/preflight artifacts. Use repository search to locate exact definitions and consumers; cite paths and line numbers.

## Binding current facts

- Selected-price C and Radar A are live/closed; A is closed at `0fdad73`.
- Active Radar is US-listings/USD-only with eight warm boards; charts/Alpaca are on and Yahoo is off.
- Historical DE/EUR rows and schema are protected.
- The manual directory import completed and must not be rerun.
- Its recorded result is 12,745 active identities and 12,599 mapped instruments, leaving 146 newly imported identities unmapped; it also recorded 51 changed entries and 87 absent listings.
- These are historical snapshot facts until reconciled; do not silently present them as current.
- Identity upsert does not automatically maintain `RadarInstrument` mappings.
- One absent snapshot cannot authorize delisting, deletion, or deactivation.

## Owned scope

### Repository evidence

- Trace identity import, `RadarInstrument` mappings, readers, invariants, migrations, fixtures, and tests.
- Assess whether current columns represent provenance, status, effective time, rename/reassignment history, and manual review.
- Identify later implementation touch points without editing them.

### Cohort reconstruction

For the exact 146, 51, and 87 cohorts, return a machine-readable table with stable identity keys, symbols, names, directory/exchange fields, current mapping state, conflicts, classification, proposed disposition, and evidence source. Reconcile totals, list exclusions/unresolved rows, compare historical/current state when authorized, and separate safe automation from ambiguity/corporate-action/manual-review cases.

### Contract research

Propose exchange-to-MIC rules; Alpaca provider-symbol normalization/validation; currency, primary, uniqueness, and collision invariants; provenance/status/effective-time requirements; rename/reassignment and unsupported/provider-missing behavior; and a conservative absence lifecycle.

### Daily-maintenance design

Cover: acquisition of both official inputs; completeness/freshness/schema/footer/minimum-count/uniqueness/hash validation; normalized staging and dry-run diff; circuit breakers; transactional/idempotent application with locking; audit evidence and deterministic exits; no mutation on partial/stale/malformed/implausible data; safe absence aging and rollback; scheduler/observability boundaries; focused tests and future live verification.

## Authorized actions

Always authorized: repository/Git reads, existing non-secret workspace artifacts, and read-only local analysis that does not alter tracked files, caches, databases, or services.

Only if explicitly authorized in the owner's dispatch: retained production-host evidence, bounded auditable `SELECT`-only queries, and fresh official Nasdaq Trader directory reads.

## Prohibited actions

- Do not rerun `seed_radar_universe.py` or any importer against a database.
- Do not write databases, run migrations, modify mappings, delist symbols, or change jobs/services/configuration.
- Do not edit product code, tests, release-A documents, or production artifacts.
- Do not commit, stage, discard, clean, reset, merge, deploy, or change production.
- Do not call trading/account/order endpoints or expose secrets.
- Do not create subagents unless the owner explicitly authorizes them.

## Acceptance criteria and evidence format

Return: Git continuity; source inventory; counts reconciliation; machine-readable cohort tables; exact sanitized query text/results if authorized; path/line citations; mapping and maintenance contracts; schema assessment; test matrix; ranked risks/owner decisions; and the smallest safe implementation slice without implementing it. Every cohort must reconcile exactly or every discrepancy must be explicit. Historical and current facts must be separated.

## Stop condition

Stop when the evidence package and recommendation are complete. If exact recovery needs missing authority or artifacts, exhaust authorized repository/retained evidence, state the precise blocker, and do not improvise with writes or a fresh import.

## Required final section — Mastermind return prompt

End with this completed block:

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-EVIDENCE-1
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref: <exact hashes>
Observed index and worktree dirt: <exact summary and ownership caveats>

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
5. <research return and cohort artifact paths>

Research result:
- Historical 146 cohort: <reconciled result>
- Historical 51 cohort: <reconciled result>
- Historical 87 cohort: <reconciled result>
- Current-state drift: <result or not authorized>
- Mapping-contract recommendation: <result>
- Daily-maintenance recommendation: <result>
- Schema/migration assessment: <result>
- Open decisions/risks: <exact list>
- Smallest safe next assignment: <recommendation>

Release A remains CLOSED. Do not rerun the completed manual import. Do not implement, deploy, mutate production, or dispatch another worker until this return is reconciled into the B ledger and the owner approves the next step.
```


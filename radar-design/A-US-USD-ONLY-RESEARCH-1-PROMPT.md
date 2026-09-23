# Copy/paste prompt — A-US-USD-ONLY-RESEARCH-1

```text
You are Radar's Researcher. Return your result to the Mastermind.

Assignment ID: A-US-USD-ONLY-RESEARCH-1

Objective:
Produce a complete, repository-grounded inventory and removal-risk map for making Radar US-listings/USD-price only. Trace every active German/EU/EUR entry point and every shared dependency that must be preserved. This is read-only product-code research, not implementation, cleanup or a final implementation plan.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / verified expected current HEAD:
codex/radar-selected-price-charts
38591e0f5e98faccb5228d84d1677843fcdb2aea

Before acting:
- Verify the workspace, branch, HEAD, origin refs, status, diff and recent log with per-command safe.directory.
- Treat repository/Git/test evidence as authoritative if continuity prose differs, and record discrepancies.
- Preserve every tracked modification and untracked artifact. Do not stage, commit, discard or rewrite another worker's files.
- Do not touch production, databases, services, provider credentials, environment files or provider accounts.

Read fully, in this order:
1. C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/WORKFLOW.md
2. .../radar-design/A-US-USD-ONLY-SPEC.md
3. .../radar-design/A-US-USD-ONLY-LEDGER.md
4. .../radar-design/US-USD-ONLY-DECISION.md
5. .../radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
6. .../radar-design/MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md
7. Current notices at the top of .../radar-design/MASTERMIND-STATE.md, .../radar-design/ASSIGNMENTS.md and C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/HANDOFF.md.

Binding product decisions:
- Scope is Radar only. Do not alter the Gym German-language UI or the host/application Europe/Berlin timezone when it is unrelated to German-market support.
- Radar must expose only US listings and native USD prices. There is no market selector and no German/EU/EUR provider, label, badge, formatter, fallback or supported mode.
- A missing US price remains unavailable. Never relabel or implicitly convert an EUR observation into USD.
- Omitted market input uses US. Explicit legacy `market=de` or other unsupported market input must receive a clear client error, not silent US normalization.
- Existing German/EUR database rows must remain untouched but inaccessible and inert. Historical migrations are immutable. Schema retained solely to read historical rows is compatibility, not dormant product support.
- Preserve the live Alpaca selected-price path, US grouped-close ingestion, US mappings and unrelated Radar behavior.
- The 146 new US identities without instrument rows remain workstream B. A must neither solve that separate scope nor hide the gap.

Mandatory investigation:
1. Build an end-to-end reachability map from every Radar route/UI control/CLI/scheduler/config entry point through services, providers, mappings, storage and rendering. Identify active, test-only, archival and unreachable references separately.
2. Search the complete Radar-owned backend, frontend, scripts, configuration, models, migrations, templates, tests and operational documentation for German/EU/EUR concepts. Include semantic aliases, not only literal `de` or `EUR`: Deutsche Boerse/Börse, Xetra, Frankfurt/XFRA, Tradegate, ECB, German MICs/suffixes, FX conversion, market switches and source names.
3. For every relevant file and symbol, classify the safest disposition:
   - DELETE active DE/EUR-only code;
   - SURGICAL EDIT because US behavior shares the file/module;
   - KEEP ARCHIVAL COMPATIBILITY for schema/ORM/migration/history only;
   - KEEP REJECTION TEST to prove unsupported inputs fail;
   - OUT OF SCOPE with reason.
4. Trace all request defaults, query parameters, validation, cache keys, serialized payload fields and frontend types involving market/currency. State the exact API behavior changes needed to make US implicit and reject explicit unsupported markets without breaking clients accidentally.
5. Trace all active reads and writes that can select, create, refresh, convert, fall back to or display DE/EUR data. Identify the precise filters/guards needed to make historical rows inert.
6. Trace schedulers, job names, imports, environment/config variables, operations endpoints, logs/metrics, deployment units and maintenance/backfill/report scripts. Identify what must be removed and what shared US scheduling must survive.
7. Inspect models and the complete migration chain. Distinguish immutable historical DDL and constraints needed for old rows from genuinely removable runtime models/tables. Do not recommend destructive migration or row deletion under this assignment.
8. Map DE/EUR tests to the product code they protect. Identify obsolete suites, shared suites needing conversion, and required new rejection/US regression coverage. Explicitly protect selected-price Alpaca and grouped-close behavior.
9. Identify dependencies/imports/packages that become unused after removal, but recommend deletion only when repository evidence proves no non-DE consumer.
10. Provide a static residual-search checklist that an Implementer and Reviewer can run after edits. Every expected residual must have an allowed category and reason.

Known starting leads to verify, not blindly accept:
- `features/radar/markets.py` and `routes/api.py` market parsing/fallbacks.
- `features/radar/board.py`, `history.py`, `quotes.py` and leaderboard/detail paths.
- `run_radar_ingest.py`, `market_data.py`, `reference_universe.py` and `instruments.py`; several also own protected US behavior.
- `features/radar/prices/deutsche_boerse.py`, `prices/ecb.py` and `fx.py`.
- Radar frontend `MarketSwitch`, `BoardPage`, hub filters/types/formatters, quote badges and price-chart provenance.
- Radar maintenance/capture/backfill/shadow-report scripts.
- `models.py` market/source constraints and historical Radar FX/mapping/market-data records.
- German-focused backend/frontend tests plus non-US boundary fixtures that may still be useful.

Authorized actions:
- Read repository files and Git metadata.
- Run static searches and non-mutating inspection commands.
- Run narrowly selected existing tests only when needed to establish current behavior; do not run live provider calls or production-connected checks.
- Create only `radar-design/A-US-USD-ONLY-RESEARCH-1-RETURN.md`.
- Update only the current status sections of `radar-design/A-US-USD-ONLY-LEDGER.md` and root `HANDOFF.md` to point to the completed return. Preserve historical text.

Not authorized:
- Any application, test, migration, script, config, dependency or environment edit.
- Database reads or writes, schema changes, generated migrations or historical migration edits.
- Deleting or moving files, formatting/rewrite tools, commit, push, deployment or service changes.
- Provider/network requests, external account actions, flag changes or secret inspection.
- Writing the implementation plan or dispatching the Verifier/Implementer.
- Subagents.

Required return:
1. Executive conclusion and confidence/coverage limits.
2. A path-and-symbol inventory table with current role, reachability evidence, shared-US dependency and recommended disposition.
3. Entry-point-to-storage/rendering flow maps for UI/API reads, ingestion/scheduling, mappings/reference data and FX/fallback behavior.
4. API/frontend contract delta, including legacy `market=de` rejection and elimination of market selection.
5. Historical-data/schema compatibility assessment explaining exactly what remains and why it is not active support.
6. Scheduler/config/operations/deployment cleanup map.
7. Test disposition matrix and proposed acceptance gates.
8. Shared-code hazards and ordering constraints.
9. Exact residual-search checklist with allowed remaining-reference categories.
10. Evidence-backed recommended implementation slices for later planning. These are planning inputs only, not an implementation plan.
11. Explicit confirmation that no application/test/config/schema/DB/production/commit/deploy action occurred.

Stop condition:
Stop when the Mastermind and an independent Verifier can determine, from path-and-symbol evidence, that the inventory covers every active Radar DE/EUR entry point and safely distinguishes removable functionality from protected US behavior and archival database compatibility. Do not begin removal.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess this Researcher return for assignment A-US-USD-ONLY-RESEARCH-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [dirty/untracked paths and ownership; committed/pushed status]
Binding artifacts: [absolute spec, ledger, prompt and return paths]

Objective and authorized scope: Inventory every active Radar German/EU/EUR path, shared US dependency and archival compatibility requirement; repository research only, no implementation.
Completed work: [bounded searches, traces, classifications and deliverables]
Evidence: [exact commands/results, path:symbol or path:line citations, selected tests if any]
Evidence attribution: [fresh worker execution vs repository reports vs inference]
Coverage and confidence: [areas inspected, exclusions, unresolved evidence gaps]
Findings and limitations: [active entry points, hidden fallbacks, shared-code hazards, schema/data boundary]
Recommended dispositions: [delete / surgical edit / archival keep / rejection-test keep / out-of-scope summary]
Actions taken: [documents created/updated; explicitly no app/test/config/schema/DB/production/commit/deploy action]
Protected state: [US paths, historical rows/migrations, other worktrees, credentials and dirty files]
Subagents: none
Updated artifacts: [absolute local/uncommitted paths]
Requested Mastermind decision: Assess completeness and prepare one independent Verifier prompt; do not write the implementation plan until verification is accepted.
Next bounded action recommendation: One fresh independent Verifier reviews this inventory for omissions and unsafe removals.

Read the current handoff and ledger, verify relevant Git/artifact evidence, make the product ruling and update planning continuity. Do not implement, deploy or dispatch workers automatically.
```


# Radar A — US/USD-only removal ledger

## Current state — 2026-09-17 (owner authorized deployment; packet ready)

- Owner explicitly authorized deployment: **“Yes lets deploy.”**
- Deployer packet: `A-US-USD-ONLY-DEPLOY-PROMPT.md` — **READY / NOT DISPATCHED**. One Deployer, no subagents or product fixes.
- Authorized scope: exact 142-path accepted application commit; dedicated A docs/evidence commit; fetch/no-drift proof; normal fast-forward pushes; backup-first wrapper release; remove only `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY`; restart ingest/web; verify Hub + legacy + APIs + selected price + ops, eight warm US boards, protected US behavior, service health and byte-stable archived DE/EUR rows.
- Alpaca charts remain ON, Yahoo OFF and credentials untouched. Workstream B remains out of scope.
- Deployment is authorized but has not yet been dispatched or performed by this notice.

## Current state — 2026-09-17 (correction accepted; code/review gate closed)

- `A-US-USD-ONLY-CORRECTION-1`: **ACCEPTED**. C1 removes the positive retired-source test token without runtime change; C2 validates every repeated `market` value across API, Hub and legacy routes.
- Fresh Mastermind checks: focused Vitest 16 passed; selected-price 261 passed; tsc 0; TypeScript retired-token sweep empty; diff check 0; changed-lines inspection passed. Implementer guarded clone evidence: API + Hub tests 92 passed / 1 known baseline failure, zero outbound.
- Binding closure: `A-US-USD-ONLY-CORRECTION-1-RULING.md`. No further Implementer or full Reviewer cycle is required.
- Radar A is accepted for a **separate owner commit/deployment decision**. Nothing is staged, committed, pushed or deployed by this closure.
- Carries: destructive/Alembic/FK gates unavailable; F1/F5/network-test debt remains; deployment must back up/remove the two retired env variables, build/restart, and verify US/USD-only Hub + legacy + APIs + selected price + ops and all eight warm boards. Workstream B remains separate.

## Current state — 2026-09-17 (independent review accepted; bounded correction ready)

- `A-US-USD-ONLY-REVIEW-1`: independent review **ACCEPTED** with verdict `FIX REQUIRED BEFORE A ACCEPTANCE`; no Critical findings.
- Required C1: replace the positive frontend test contract for raw `deutsche_boerse_delayed` rendering with a neutral unknown-source case; runtime `sourceWord()` stays unchanged.
- Required C2: repeated market parameters must reject when **any** supplied value is unsupported. The reviewer called this optional; Mastermind upgrades it because `market=us&market=de` currently violates the binding explicit-non-US→400 contract.
- Accepted classification: `mauerstrassenwetten` remains as US-universe chatter, outside A's market-price removal. Cleanup-only M2/M4 are rejected from scope.
- Evidence clarification: the eight-board addendum landed before the final DB run, but after the saved post-Task-4 snapshot; final coverage is authoritative and the non-pass set did not change.
- Ruling: `A-US-USD-ONLY-REVIEW-1-RULING.md`. Next packet: `A-US-USD-ONLY-CORRECTION-1-PROMPT.md` — **READY / NOT DISPATCHED**. After its return, Mastermind changed-lines verification closes the gate; no second full review.
- Commit, push, production environment cleanup and deployment remain unauthorized.

## Current state — 2026-09-17 (implementation assessed; independent review ready)

- Mastermind ruling: `A-US-USD-ONLY-IMPLEMENT-1-RULING.md` — **accepted into independent review**, not accepted for commit/deployment.
- Repository checks confirm HEAD remains `38591e0f5e98faccb5228d84d1677843fcdb2aea`, the index is empty, models/migrations have no diff, the eight-board owner addendum is present, and quote ranking is US/legacy-US scoped before deletion.
- Two mandatory review classifications: active `mauerstrassenwetten` Reddit source; frontend test preserving raw `deutsche_boerse_delayed` rendering. Destructive suites/Alembic/FK parity remain unavailable and must not be presented as passes.
- Next packet: `A-US-USD-ONLY-REVIEW-1-PROMPT.md` — **READY / NOT DISPATCHED**, one genuinely fresh independent Reviewer/QA, no subagents, fixes, commit or deployment.
- Commit, push, production environment cleanup and deployment remain unauthorized.

## Current state — 2026-09-17 (after implementation)

- `A-US-USD-ONLY-IMPLEMENT-1`: **RETURNED** — one complete, **uncommitted** local candidate in `.worktrees/radar-selected-price-charts` on `codex/radar-selected-price-charts`, HEAD `38591e0f5e98faccb5228d84d1677843fcdb2aea` unchanged. Nothing staged, committed, pushed or deployed. Return: `A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`; per-task checkpoints and evidence: `artifacts/a-us-usd-only-implement-1/`.
- Scope delivered: explicit non-US `market` → 400 on APIs and HTML routes (omitted = US); selected-price `span` required, `market=us` only; US-only calendar; `KEY_VERSION` 3, `PAYLOAD_VERSION` 2, observations `SCHEMA_VERSION` 2; read path/writers US/USD only (no fallback, no FX); DE jobs/helpers/config/scripts/tests and `fx`, `ecb`, `deutsche_boerse`, `openfigi`, `instruments`, `reference_universe`, DE calendars removed atomically; retention scoped to US/legacy-US (ranked-subquery filter); frontend market dimension, EUR and fallback rendering removed, USD-only formatting. 115 tracked paths modified (57 app/script/CSS, 58 tests), 27 deleted; `models.py`/`migrations/` no diff.
- Owner warm-board addendum implemented: `WARM_MARKETS=('us',)`, `WARM_SEGMENTS=('', DEFAULT_SEGMENT)`, `WARM_WINDOWS=(1, 4, 12, 24)`; tests prove 8 unique US warm queries, both parser-normalized segment selections, windows `[1,1,4,4,12,12,24,24]`; `warm_limit` 8.
- Gates (fresh Implementer execution): tsc 0; build 0; Vitest radar 913/885/28 with failing identities identical to HEAD (all `hub/pending.test.tsx`); selected_price_unit 261, ha1_unit 241, massive 18 passed; `git diff --check` 0; Python Playwright 1200/390/320 exit 0 (29 cases, 184 checks, 0 failures, 0 outbound); DB-backed on proved disposable `personal_apps_radar_wt` only: 1698 passed / 12 failed / 193 errors / 1 skipped on final code (baseline 1849/14/220/1); identity set identical to the post-Task-4 run, no new failing identity; all errors are destructive opt-in refusals; residue rows from non-destructive tests grow each run (F5).
- Unavailable: destructive suites (no `RADAR_DESTRUCTIVE_TEST_TARGET`/registry for the clone); Alembic/FK parity (clone has 0 FKs, known missing-FK limitation).
- Findings for Mastermind: F1 — unguarded `test_radar_activity` migration test upgraded the disposable clone `a7c31f0b52d4`→`b7e3f9c1a2d4` (pre-existing, not fixed); classification needed for `config.py:533` / subreddit `mauerstrassenwetten`; embedded payload naming another market is now refused (F4); 146 US mapping gap remains B (no instrument writer remains); deployment carries: remove `RADAR_DE_PRICE_MODE`/`OPENFIGI_API_KEY` from production `.env`, restart ingest + web with fresh build.
- Next: Mastermind assesses the return and prepares **one fresh independent Reviewer/QA** prompt. Commit, push, deploy, production env and database changes remain unauthorized.

## Current state — 2026-09-17 (owner warm-board addendum; implemented, superseded)

- Owner requires all supported US board windows preloaded: 1h, 4h, 12h and 24h for All and the default Discover segment selection, exactly eight US warm boards.
- Binding addendum: `A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`; folded into `A-US-USD-ONLY-PLAN.md` and `A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md`.
- `A-US-USD-ONLY-IMPLEMENT-1` appears active in the shared worktree; deliver the addendum as an in-flight correction before the worker closes Task 1.
- All other gates and authorization limits remain unchanged.

## Current state — 2026-09-17 (after independent verification and planning; superseded)

- Gate 1 Researcher: **ACCEPTED WITH RULING**.
- Gate 2 independent Verifier: **ACCEPTED — PASS WITH FINDINGS**. Binding: `A-US-USD-ONLY-VERIFY-1-RULING.md`; no further research loop.
- Critical planning correction: `retention.prune_quotes` must exclude all DE rows before ranking; reduced market-data retention must preserve US close pruning while ceasing DE event/cycle deletion.
- Binding plan: `A-US-USD-ONLY-PLAN.md`.
- Next assignment: `A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md`, **READY / NOT DISPATCHED**. One Implementer, no subagents, uncommitted candidate.
- Independent review: required after implementation; not prepared or dispatched yet.
- Commit, push, deployment, production env cleanup and database/schema changes: not authorized.

## Current state — 2026-09-16 (after Mastermind Researcher assessment; superseded)

- Product design: **APPROVED** by owner.
- Gate 1 — Researcher inventory: **ACCEPTED WITH BINDING CLARIFICATIONS**. Return: `A-US-USD-ONLY-RESEARCH-1-RETURN.md`; ruling: `A-US-USD-ONLY-RESEARCH-1-RULING.md`.
- Binding clarifications: all existing DE/EUR rows become untouched archival data; API and HTML surfaces explicitly reject unsupported markets; omitted market means US across Radar; stale DE-only variables are ignored by code and removed during a later authorized deployment; board-key and observation-schema changes require versioning; no orphan DE mapper helper is retained merely for workstream B.
- Gate 2 — `A-US-USD-ONLY-VERIFY-1`: prompt prepared, **READY / NOT DISPATCHED**. It must be performed by a fresh independent Verifier and is read-only.
- Implementation plan: not written; blocked on accepted Gate 2.
- Implementation, commit, push, deployment, production/config/database changes: none authorized or performed for A.

## Current state — 2026-09-16 (after Researcher return; superseded)

- Product design: **APPROVED** by owner.
- Binding specification: `A-US-USD-ONLY-SPEC.md`.
- Gate 1 — Research assignment `A-US-USD-ONLY-RESEARCH-1`: **RETURNED**, awaiting Mastermind assessment. Return: `radar-design/A-US-USD-ONLY-RESEARCH-1-RETURN.md` (local/uncommitted). Verified HEAD 38591e0f5e98faccb5228d84d1677843fcdb2aea on `codex/radar-selected-price-charts`.
- Headline findings: DE default in `routes/api.py` (`Query.market='de'`, `default_market`); two UI selectors; three DE-only scheduler jobs plus DE half of `radar_history`; producer/observations warm and archive the DE board; read-time FX conversion in `history._converted_basis`; five DE-only tables and three shared tables with `('us','de')` CHECKs are archival; protected selected-price/HA1/grouped paths already US-only. Two rulings requested: retention currently deletes DE rows (`retention.py`), and `market=de` on the selected-price route moves from 422 to 400.
- Gate 2 — independent Verifier: **NOT DISPATCHED**; Mastermind prepares the prompt after assessing the return.
- Implementation plan: not written; blocked on gates 1–2 acceptance.
- Implementation, commit, push, deployment, production/config/database changes: none authorized or performed for A. Researcher performed no app/test/config/schema/DB/commit/deploy action; only `pytest --collect-only` (offline).

## Current state — 2026-09-16 (before research; historical)

- Product design: **APPROVED** by owner.
- Binding specification: `A-US-USD-ONLY-SPEC.md`.
- Research assignment: `A-US-USD-ONLY-RESEARCH-1` prepared, **not dispatched**.
- Implementation plan: not written; blocked on accepted Researcher and independent Verifier returns.
- Implementation, commit, push, deployment, production/config/database changes: none authorized or performed for A.

## Binding owner decisions

- Radar only; do not alter unrelated German-language product functionality or the host timezone.
- Radar becomes US-listings/USD-price only everywhere.
- Remove German/EU functionality; do not merely hide or feature-flag it.
- Remove Germany/EU/EUR controls, labels, formatting, sources and fallbacks from UI and supported APIs.
- Explicit legacy `market=de` input returns a clear unsupported-market client error; it is not silently redirected to US.
- Retain old German/EUR database records solely for historical/audit safety. They must be inaccessible, inert and never relabelled as USD.
- Preserve functioning US behavior, especially Alpaca selected-price charts and US grouped-close ingestion.
- Keep the 146 newly imported but currently unmapped US identities visible as workstream B debt; A must not mask them.

## Ordered gates

1. Researcher repository inventory and risk map.
2. Independent Verifier completeness review.
3. Mastermind ruling and phased implementation plan.
4. Owner-selected Implementer.
5. Independent Reviewer/QA, bounded corrections if genuinely required.
6. Separate owner deployment authorization and US-only production verification.

Do not skip gates 1–3 or redispatch the closed selected-price workstream.

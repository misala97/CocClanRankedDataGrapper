## CURRENT — Owner addendum: preload eight US boards (2026-09-17)

Both existing segment selections are now warmed for every supported US window (1h, 4h, 12h, 24h), keeping eight total preloaded boards after DE removal. Binding: `A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`; implementation plan/prompt updated. No deployment authorization added.

---

## CURRENT — Research/verification accepted; implementation packet ready (2026-09-17)

Binding verification ruling: `A-US-USD-ONLY-VERIFY-1-RULING.md`; phased plan: `A-US-USD-ONLY-PLAN.md`; next packet: `A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md`, READY / NOT DISPATCHED. The plan includes the Verifier's missed `prune_quotes` DE-row deletion, preserves US close retention, explicitly rejects unsupported market input on API/HTML routes, and keeps archival rows/schema untouched. No implementation, commit, deploy, environment or database action has occurred.

---

## CURRENT — Manual universe refreshed; maintenance/encoder priorities (2026-09-16)

Binding update: radar-design/US-UNIVERSE-REFRESH-2026-09-16.md. Owner-authorized manual import completed: 146 added, 51 updated, 12,745 active; 87 absent older symbols retained. Only 12,599 mapped US instruments: 146 new identities need mapping reconciliation. Earlier all-symbols-mapped counts are pre-import history. Services healthy. Next plan: US/USD-only removal + US mapping reconciliation and automatic validated daily universe refresh; accepted continuous area chart/selected feed work remains. Encoder v3 already active; future directional-label/head work separate, no retrain started. No worker dispatched, code deployed or flags changed. Supersedes conflicting older priorities below.

# US/USD-only product decision — 2026-09-16

Status: owner approved; planning only, implementation not dispatched.

## Decision
Remove German/EUR market-price functionality completely, rather than hide or retain it as a supported dormant feature. Radar focuses on US listings and USD. Scope includes German price providers and scheduling, German instrument mapping/refresh paths, market selectors, EUR display and DE fallback/configuration branches. Identify shared dependencies before removal; preserve the functioning US path and unrelated features. No relabeling EUR amounts as USD.

Historical database deletion is not required or authorized by this decision. Do not drop historical records or shared schema merely to remove runtime support. Remove active functionality without maintaining an alternative German system. Future EU support would be new work.

## Evidence
Mastermind executed a production read-only transaction on 2026-09-16 local date (server session timestamp not captured), using max_statement_time=8, no app import and rollback/close. Active universe: 12,599; with US row: 12,599; mapped US: 12,599; mapped DE: 2,517; DE mapped without mapped US: 0; DE row without US row: 0. Total mapped DE instrument rows: 3,229. Script: artifacts/md-selected-price-personal-preview/count_market_coverage.py. Counts are session-observed, not a guarantee of future coverage or live quote availability.

Removing DE support removes no currently counted active ticker identity. German prices and US prices are not identical; currency/session/venue differences remain real, but owner does not need both for Radar's current purpose.

## Accepted chart direction
Owner positively selected preview-area.html: compact continuous area chart connecting actual reported prices, subtle fill, no dots/dashed gaps at every missing minute. Candles and earlier fragmented previews were rejected. Connections are visual guides, not new price observations. Preview discussion counts remain explicitly synthetic. Production renderer changes and acquisition activation remain separate implementation/release scope.

Nasdaq undated FT chart succeeded: 69 total points; 64 regular-session points matched Yahoo's same-time prices within 0.0001, using ET labels. Numeric Nasdaq x timestamps encode ET wall-clock as UTC in this response; do not ingest blindly. This supersedes the earlier statement that independent FT comparison remained unavailable. Neither feed supplies denser regular-session FT observations in this sample. AAPL Yahoo control had 390/390 regular minutes.

## Next bounded action
Prepare a repository-grounded removal plan/Implementer prompt: exact DE-only entry points, shared US dependencies, relevant regressions and deployment scheduling changes. Do not redispatch completed selected-price or HA1 reviews. Owner chooses worker/model and pastes the prompt; every worker return must include a self-contained Mastermind return prompt. No automatic worker dispatch, implementation, commit, deployment, flag activation or DB deletion.

## Baseline
Workspace C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts; branch codex/radar-selected-price-charts; verified HEAD f632e5db5dd92e27480cbfccdf7b0638b26533ed. Charts-only release closed; new Yahoo acquisition OFF. HA1 closed. Existing dirty application-independent continuity and evidence files preserved. This decision changes product scope, not current running state.

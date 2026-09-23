# Mastermind ruling — A-US-USD-ONLY-VERIFY-1

Date: 2026-09-17  
Status: Gate 2 accepted; implementation planning authorized, implementation not dispatched

## Decision

Accept the independent Verifier's **PASS WITH FINDINGS**. Gate 2 is closed. The Critical omission and Important findings are fully evidenced and become binding planning corrections; no additional research cycle is required.

The Verifier independently reproduced the Researcher's active-path inventory and found one missed writer/deleter boundary: nightly `retention.prune_quotes` ranks and deletes German quote rows. It also confirmed the corrected HTTP contract, selected-price default, cache/archive versioning, active-source vocabulary cleanup, import-chain atomicity and test baseline.

## Binding corrections

1. Scope the ranked input of `prune_quotes` to `market='us' OR market IS NULL` before the window subquery. Existing DE quote rows must never enter the deletion candidate set.
2. Preserve US close retention. Replace DE event/cycle deletion in `prune_market_data` with a US-only close-retention entry that still calls `_prune_daily_closes` and `_prune_massive_shadow`; do not delete the entire call chain.
3. Scope `_prune_daily_closes` by `market='us' OR market IS NULL`, not by a `deutsche_boerse_delayed` source exception. Remove DE event/cycle retention completely.
4. Explicit unsupported `market` input returns 400 on API and HTML routes. Keep the existing friendly HTML fallback only for malformed non-market filters; never use it for an explicit non-US market.
5. Selected price requires `span`, defaults omitted `market` to US, accepts explicit `market=us`, and returns `invalid_market`/400 for every explicit non-US value. Its acquisition, reader, rate limits, fallback and geometry do not otherwise change.
6. Increment board `KEY_VERSION` 2→3, board `PAYLOAD_VERSION` 1→2 when DE-only operations fields are dropped, and observation `SCHEMA_VERSION` 1→2 while changing observation markets to US only. Old rows remain untouched.
7. Delete `deutsche_boerse_delayed` from active Python/TypeScript source vocabularies and history priority. Retain it only inside immutable migrations and ORM CHECK strings required to mirror existing DDL.
8. Delete DE mapping/provider/FX modules atomically with every top-level importer. `_active_us_instruments` has no surviving consumer and is deleted; B will build a dedicated US maintenance path later.
9. Remove the additional residuals identified by the Verifier: selected-price source wording, frontend source type, Finnhub/Yahoo XETR entries, board tests, calendar fixture, shadow-report default, `.DE` suffix paths and the DE `history_due_at` writer.
10. `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY` cease to be read by code. Their verified names are removed from production environment only during a separately authorized, backup-first deployment.
11. Preserve archival ORM classes, shared market/currency columns, CHECK strings, historical migrations and model/migration tests. No schema migration or historical-row mutation belongs to A.
12. Preserve `TWELVEDATA_API_KEY`, US history, US grouped-close ingestion, provider-session state, Alpaca selected-price behavior, HA1 and all unrelated Radar features.

## Product rulings

- Non-market address-bar typos may keep the current friendly HTML fallback. Only an explicitly supplied unsupported `market` bypasses that fallback and returns a clear 400.
- Radar monetary formatting uses US/USD presentation (`$194.20` style). A `de-DE` locale may remain only where it formats the retained Berlin clock/date behavior; it must not format market prices.
- The 28 failing assertions in `hub/pending.test.tsx` are a verified HEAD baseline, not a blanket allowance. Implementation evidence must compare the exact failing test identities before and after.

## Next action

The binding phased plan is `A-US-USD-ONLY-PLAN.md`. The only next worker is one Implementer using `A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md`. The packet is prepared but not dispatched. After a complete implementation return, require one fresh independent Reviewer/QA before any commit, push, production environment edit or deployment.


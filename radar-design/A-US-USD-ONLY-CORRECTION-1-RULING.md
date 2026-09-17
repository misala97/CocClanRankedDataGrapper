# Ruling — A-US-USD-ONLY-CORRECTION-1

Date: 2026-09-17  
Status: Accepted; Radar A code/review gate closed

## Decision

Accept `A-US-USD-ONLY-CORRECTION-1`. The correction is confined to the two authorized findings and satisfies `A-US-USD-ONLY-REVIEW-1-RULING.md`. No second full review is required.

### C1 — retired source test

`selectedPriceGeometry.test.ts` now tests generic unknown-source passthrough using `some_future_feed`. Runtime `sourceWord()` is unchanged, and `deutsche_boerse_delayed` has no remaining TypeScript/TSX occurrence under `static/radar/src`.

### C2 — repeated market validation

The shared `require_us_market()` boundary inspects every Flask `MultiDict` value while remaining compatible with plain mappings. Omitted, empty and repeated supported values resolve to US. Any supplied unsupported value raises the existing `BadQuery('unsupported market')`, regardless of ordering. API board/ticker and HTML `/radar/`, `/radar/hub/`, `/radar/legacy/` paths have focused regressions; HTML rejection remains before friendly fallback and embeds no Radar payload. Selected-price duplicate handling is untouched.

## Mastermind verification

Fresh from the unchanged candidate:

- focused `selectedPriceGeometry.test.ts`: 16 passed;
- complete DB-free selected-price suite: 261 passed;
- `npx tsc --noEmit`: exit 0;
- TypeScript/TSX `deutsche_boerse_delayed` sweep: no matches;
- `git diff --check`: exit 0;
- changed-lines inspection: pass;
- index empty; `models.py` and migrations have no diff.

The correction Implementer's guarded disposable-clone run is accepted as matching-state evidence: `test_radar_api.py` plus `test_radar_hub_page.py` produced 92 passed and one known baseline failure, with zero outbound attempts. The bare DB-backed command was not repeated by the Mastermind because the repository's unwrapped test setup binds the protected `personal_apps` database.

## Closure and carries

Radar A is accepted for a separate owner commit/deployment decision. This ruling does not authorize commit, push, production environment edits or deployment.

Known carries remain explicit:

- destructive suites are unavailable without a registered disposable target;
- Alembic/FK parity was unavailable because the clone has zero foreign keys;
- F1 migration-test safety, F5 clone residue and Arctic Shift test-network hygiene are pre-existing follow-up debt;
- deployment must back up the production environment, remove `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY`, build fresh assets, restart `radar_ingest` and `personal_apps_web`, verify namespace/key rotation and all eight warm US boards, and perform US/USD-only API/Hub/legacy/selected-price/ops smoke checks;
- workstream B still owns the 146 unmapped US identities and 51 changed entries.

No additional A Implementer or Reviewer is pending.

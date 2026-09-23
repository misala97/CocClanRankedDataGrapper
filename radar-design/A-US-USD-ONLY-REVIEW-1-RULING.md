# Ruling — A-US-USD-ONLY-REVIEW-1

Date: 2026-09-17  
Status: Independent review accepted; one bounded correction required before A acceptance

## Decision

The Reviewer satisfies the independence gate and provides sufficient fresh evidence. Accept the review verdict `FIX REQUIRED BEFORE A ACCEPTANCE`. There are no Critical findings and the broader US/USD-only candidate passes review, subject to the two bounded corrections below.

No second full review cycle is required. After the correction return, the Mastermind performs a changed-lines assessment, focused tests and residual sweeps. If those pass, A may proceed to a separate owner commit/deployment decision.

## Required corrections

### C1 — remove the retired source token from the positive frontend test

Accept Reviewer I1. `static/radar/src/hub/selectedPriceGeometry.test.ts` positively contracts that `deutsche_boerse_delayed` is rendered raw. This is not a rejection test and conflicts with the binding rule that the token remain only in immutable migrations and ORM CHECK strings. Replace it with a neutral unknown source code and update the test title/comment. Do not change runtime `sourceWord()` behavior.

### C2 — reject every unsupported value in repeated market parameters

Upgrade Reviewer M1 to required. The binding contract says every explicit non-US market is rejected. `?market=us&market=de` currently succeeds because `args.get()` reads only the first value. Both API parsing and the HTML pre-fallback guard must inspect all supplied `market` values and return the existing unsupported-market 400 when any value is neither empty nor `us`. Preserve omitted/empty market → US, explicit `us` → US, repeated supported values, friendly fallback for unrelated malformed filters, and the selected-price route's existing strict duplicate-query contract.

Add focused regressions covering both orderings on board/ticker JSON routes and `/radar/`, `/radar/hub/`, `/radar/legacy/`; prove no embedded payload is rendered on the HTML 400 responses.

## Other review items

- Accept the `mauerstrassenwetten` ruling: it is a German-language chatter source resolved exclusively against the US ticker universe and priced through US/USD paths. Removing it would be a separate source/ranking decision, not part of this market-price removal.
- Do not include M2 (`ChartHover.currency`) or M4 (lost comment) in the correction. They are cleanup without a demonstrated current defect.
- Record M3 accurately in current continuity: the owner warm-board addendum landed before the final DB run, not before the earlier post-Task-4 snapshot. Final evidence covers eight boards; non-pass identities were unchanged.
- F1, F5, Arctic Shift network-test hygiene, destructive-suite unavailability and zero-FK clone limitations remain explicit follow-up/risk items, not correction scope.

## Next action

Use `A-US-USD-ONLY-CORRECTION-1-PROMPT.md` with one Implementer. No commit, push, production environment change or deployment is authorized.

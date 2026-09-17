# Mastermind ruling — A-US-USD-ONLY-RESEARCH-1

Date: 2026-09-16  
Status: Research Gate 1 accepted with binding clarifications; independent verification required

## Decision

The Researcher return is accepted as a sufficiently broad repository inventory for Gate 1. It covers the active UI/API, quote/history/detail reads, ingestion and scheduling, mapping/reference paths, FX/fallback behavior, operational scripts, frontend rendering, schema/migrations and test surface with path-and-symbol evidence. No implementation work was performed.

This acceptance does not validate every proposed deletion. Gate 2 remains mandatory because the return recommends edits across shared US/DE modules and contains contract ambiguities that an independent Verifier must challenge.

## Binding rulings

1. **Historical retention means all existing German/EUR rows.** Once the German writers are removed, Radar retention must stop selecting or deleting German/EUR daily closes, mapping generations, cursors, cycles, trade events and FX rows. Scope shared close pruning to US/legacy-US rows only and remove DE-only journal/cycle pruning. Operational-table age does not override the approved no-deletion boundary.
2. **No HTTP surface silently converts an explicit unsupported market.** API endpoints and HTML shell routes receiving `market=de` or another unsupported market must return a clear client error. The HTML route may render a human-readable 400 page, but it may not swallow the error and open the US board. Frontend URL parsing must not turn `?market=de` into a normal US selection.
3. **Omitted market means US across Radar.** This includes the selected-price endpoint unless independent verification proves a concrete compatibility blocker requiring a new owner ruling. Internal clients may continue sending `market=us`, but omission cannot select or require a non-US mode. Explicit non-US remains 400.
4. **Stale production variables are not runtime support.** New code must stop reading `RADAR_DE_PRICE_MODE`, `OPENFIGI_API_KEY` and any other DE-only setting. Their mere pre-deploy presence must not block candidate startup. The eventual authorized deployment must back up the environment and remove verified DE-only variables; this is a deployment carry, not a reason to retain code branches or log recurring warnings.
5. **Stored artifacts must be unambiguous.** Bump the board-key version when the key domain narrows. Version the observation payload/schema when the archived shape changes from two markets to US-only, while leaving old observation rows untouched.
6. **Do not preserve orphan DE modules for future B.** If `instruments.py::_active_us_instruments` has no active US consumer after A, remove it with the DE mapper. Workstream B may create a dedicated US mapping/maintenance abstraction later. The 146 unmapped US identities remain explicit B debt.
7. **Archival vocabulary must be minimal.** Immutable migrations and ORM metadata required to represent the existing database stay. The Verifier must determine whether `deutsche_boerse_delayed` is actually required in active Python source-validator sets; prefer removing it from active validation if historical ORM loading does not depend on those sets. A CHECK constraint string may remain for schema compatibility without retaining an active writer vocabulary.
8. **Selected-price behavior stays protected.** Its Alpaca acquisition, stored US fallback, rate controls, geometry and production activation remain unchanged except for the consistent unsupported/omitted-market input contract and necessary tests.

## Required corrections to planning inputs

- Replace the proposed HTML silent fallback and frontend `?market=de` normalization tests with explicit unsupported-market behavior.
- Reconcile the selected-price route's currently required market parameter with the binding omitted-market-US rule.
- Treat every DE/EUR retention path as removal scope.
- Include observation schema versioning, board-key versioning and environment cleanup in the later plan if the Verifier confirms the exact mechanics.
- Do not describe the Researcher's proposed slices as an accepted implementation plan.

## Next gate

Dispatch one fresh independent Verifier using `A-US-USD-ONLY-VERIFY-1-PROMPT.md`. The Verifier is read-only and must independently confirm completeness, deletion safety, archival necessity and the corrected contract. The Mastermind writes no implementation plan until that return is accepted.


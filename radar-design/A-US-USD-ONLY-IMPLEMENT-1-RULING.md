# Ruling — A-US-USD-ONLY-IMPLEMENT-1

Date: 2026-09-17  
Status: Implementer return accepted into independent review; candidate not yet accepted, committed or deployable

## Decision

Accept the Implementer's return as a complete enough, evidence-backed candidate for the mandatory fresh independent Reviewer/QA gate. This ruling does not accept the product delta for commit or deployment.

Repository evidence confirms the uncommitted candidate is still based on `38591e0f5e98faccb5228d84d1677843fcdb2aea`, the index is empty, `models.py` and migrations have no diff, the owner addendum is present in code (`WARM_MARKETS=('us',)`, both existing segment selections, `WARM_WINDOWS=(1, 4, 12, 24)`), and the quote-retention ranking query filters to US/legacy-US before ranking. The Implementer's reported type/build, focused-suite, full Vitest, DB-backed and Playwright evidence is internally consistent and is preserved under `artifacts/a-us-usd-only-implement-1/`.

## Mandatory review targets

The Reviewer must independently inspect the complete application/test diff and must not treat the return prose as proof. In addition to the binding plan, it must resolve these items explicitly:

1. `features/radar/config.py` still actively includes `mauerstrassenwetten` in `REDDIT_SUBS`. Determine against the owner-approved Radar-only US/USD scope whether this German-language Radar source is an active German feature that must be removed, or a US-equity chatter source legitimately outside the market-price removal boundary. State the product consequence and severity; do not silently classify it as an unrelated word-list hit.
2. `static/radar/src/hub/selectedPriceGeometry.test.ts` still names `deutsche_boerse_delayed` and asserts that `sourceWord()` renders it raw. The binding ruling removes that token from active Python/TypeScript source vocabularies, retaining it only in immutable migrations and ORM CHECK strings. Determine whether this is a valid rejection fixture or a test that preserves accessible retired-source rendering. Require the smallest correction if it breaches the binding rule.
3. Destructive DB suites, Alembic autogenerate and FK parity were unavailable. Verify that the test conversions and code are correct by inspection and run only gates whose database target is independently proven disposable. Never weaken or bypass the destructive-test guard.
4. Confirm that deleted modules have no surviving import/runtime chain, historical DE/EUR rows are unreachable and untouched, non-US input is rejected rather than normalized, and US selected-price/grouped-close/quote/history behavior remains intact.

The pre-existing unguarded migration test and accumulating disposable-clone residue are follow-up safety debt, not permission to expand A. Workstream B's 146 unmapped US identities remains separate.

## Next gate

Use `A-US-USD-ONLY-REVIEW-1-PROMPT.md` in one genuinely fresh task. Findings precede any correction task. Commit, push, production environment cleanup and deployment remain unauthorized.

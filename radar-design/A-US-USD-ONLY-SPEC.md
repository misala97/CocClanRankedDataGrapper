# Radar A — US/USD-only binding specification

Date: 2026-09-16  
Status: owner-approved product design; research and independent verification accepted; implementation planned but not dispatched

## Outcome

Radar is a US-listings, USD-price product. Every active user-visible and operational path uses US market data and USD presentation only. German/EU functionality is removed rather than hidden behind a flag or retained as a dormant supported mode.

## User-visible contract

- Radar exposes no country or market selector.
- Radar UI, labels, badges, source descriptions, charts, tables, filters and detail views contain no Germany, EU, DE, EUR, Xetra, Frankfurt, Tradegate, Deutsche Boerse or ECB option or fallback.
- Every displayed Radar market price is a native USD value from the supported US path and is formatted as USD. Existing non-price product copy is changed only when it exists solely to describe removed German/EU behavior.
- EUR observations are never relabelled, converted or presented as USD.
- Unavailable US data remains unavailable; Radar must not substitute German/EUR data.

## API and runtime contract

- Radar's active public and internal market-price behavior is US-only.
- Requests that omit a market use the US path.
- Explicit legacy requests for `market=de`, or another unsupported market, fail with a clear client error such as HTTP 400. They are never silently normalized or redirected to US.
- German providers, reference downloads, instrument mapping, price ingestion, refresh schedules, FX conversion and fallback branches do not run.
- German/EU configuration flags and environment branches cease to control active behavior. Obsolete operational scripts and source-specific probes are removed from active tooling.
- Shared modules that also own functioning US behavior must be changed surgically. Alpaca selected-price charts, US grouped-close ingestion, US instrument identity and unrelated Radar functionality are protected.

## Historical-data boundary

- Existing German/EUR database rows remain stored for audit and rollback safety. This work does not delete, rewrite, convert or relabel them.
- Historical migrations are immutable.
- Generic market/currency columns, ORM access and existing constraints may remain where required to read an existing production database safely. Their presence is archival compatibility, not supported German functionality.
- Active Radar reads must exclude German/EUR records, and active writers, jobs and tools must not create or update them.
- Old German/EUR rows are unreachable from the Radar UI and supported API behavior.
- Dropping old rows, narrowing constraints or removing legacy tables is a separate migration/retention decision and is not authorized.

## Scope boundaries

In scope is every active German/EU market-price path inside Radar: backend routes and services, frontend UI and formatting, schedulers, providers, reference-universe and mapping flows, FX behavior, configuration, maintenance/backfill/reporting scripts, operations surfaces and tests that exist solely for removed functionality.

Out of scope:

- the unrelated Gym German-language interface;
- the host/application `Europe/Berlin` timezone where it is not a German-market feature;
- deletion or transformation of historical production data;
- rewriting historical migrations or evidence documents;
- adding another market, currency or provider;
- resolving the 146 newly imported US identities or building automatic universe maintenance. Those remain workstream B, although A must not conceal or misreport their unmapped state;
- changes to ranking, headlines, encoder behavior or visual redesign unrelated to removing the selector and DE/EUR presentation.

## Required safety properties

1. No active German/EU provider request, scheduled job, reference refresh, mapping activation, FX lookup or data write remains reachable.
2. No UI control or supported API can select or surface German/EUR prices.
3. No EUR amount is rendered with a dollar sign or converted implicitly.
4. Unsupported legacy market input produces an explicit error.
5. Existing German/EUR rows and schema remain intact and inert.
6. US behavior remains green, including Alpaca selected-price charts and grouped daily-close ingestion.
7. The post-change repository contains no unexplained active Radar references to DE/EUR providers, modes or presentation. Remaining references must be classified as immutable migration/history, archival schema compatibility or intentional rejection tests.

## Evidence gates

Before implementation planning, one Researcher must produce a path-and-symbol inventory, reachability trace, shared-code hazards, schema/data compatibility assessment, test map and deployment/config cleanup map. An independent Verifier then checks the inventory for omissions and challenges every proposed residual DE/EUR reference.

Only after both returns are accepted may the Mastermind write the phased implementation plan. Implementation must use narrow commits and prove the safety properties with focused backend/frontend tests, builds, static searches, database-compatibility checks and US-only smoke coverage. Production deployment and any configuration cleanup remain separately owner-authorized.

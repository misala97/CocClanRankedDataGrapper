# Radar: first production releases

Status: proposed implementation contract, prepared for Claude on 2026-09-09. The owner approved the overall light/green direction and asked Codex to plan and Claude to implement. This document specifies the first slices; it does not claim approval of every interaction or authorize deployment.

## Product outcome

Open Radar, understand current chatter, find a company, inspect the actual evidence and price context, and save it to Watching. This is the first useful part of the larger stock hub described in BRIEF.md and ROADMAP.md.

Release 0 records operational observations and establishes a reproducible baseline. Release 1 delivers Overview, Human Chatter, Stock Research, Watching, Activity, and read-only Admin. The hub may be implemented while the recording period accumulates. Historical recommendations do not depend on fabricated backfills.

## Binding constraints

- Radar has its own light/green identity. Use DESIGN.md and the approved prototype as visual references; do not inherit another app's design.
- Desktop is primary; usable at 390px, 768px, and 1440px viewport widths.
- Keep Flask, React, TypeScript, Vite, and the existing Radar asset boundary for these releases. No new frontend dependency is necessary.
- Production screens use real API data. Fictional prototype fixtures remain test/design assets only.
- Missing measurements remain missing; zero means measured zero.
- UTC instants travel with explicit timezone; display Europe/Berlin and state the selected price market and currency.
- A social ticker is not a globally unique tradable listing. Preserve market, venue/MIC, quote timestamp, currency, fallback, and chart conversion provenance.
- Scalable availability remains unknown unless verified. A German quote is not evidence of broker availability.
- Watch state is account-specific; preserve server authentication and CSRF protection.
- No automated trading, broker connection, portfolio ledger, news pipeline, alerts, replay, or buy/sell recommendation engine in these releases.
- Existing scoring remains an input for ordering, never a claimed probability of profit or a buy recommendation.
- No production deployment or live database migration is included in this handoff.
- Preserve unrelated changes, including discovery scripts, source candidates, classifier artifacts, and other apps.

## Release 0: recording contract

Introduce two additive tables, without changing retention of existing tables.

`RadarIngestRun`: UUID string primary key; started_at and finished_at naive UTC (existing database convention); status running/ok/error; summary_json nullable JSON; error_code nullable string. Persist a start marker before running intake. On success store the returned summary exactly, with a schema_version of 1 in the envelope. On failure record only a stable error code, no raw exception text or secrets. A crashed process leaves a running row; classify it as incomplete in reads, never as a zero run. Do not claim this is transactionally exhaustive intake accounting: intake has internal commits and a process may fail before reporting its totals.

Counts retain their actual definitions: posts_seen counts fetch deliveries and can repeat posts between cycles; posts_new counts new stored posts; mentions counts returned mention rows; buckets_written is work performed, not unique historical buckets. Per-source intake reason counters are not automatically exclusive categories. Do not sum them into an invented discarded-total. Recording judged/discarded totals needs separate instrumentation in a later scoped plan.

`RadarBoardObservation`: UUID primary key; unique slot_start (15-minute UTC boundary); observed_at; schema_version=1; producer_revision (Git revision supplied via configuration, unknown allowed); selections_json; payload_json. One observation contains two viewer-independent boards: US and DE, sources explicitly configured at capture time, segment empty (all), window 24h, venues 1, default ordering. Record the precise query with each payload. Exclude watching/watch_rows, spend, sentiment_ops, and market_data_ops from this research archive. Never archive account state or raw post bodies. Store only successfully built complete pairs; a failed pair leaves a gap. Repeated capture of the same slot must not overwrite the first observation. Record actual capture time, not a manufactured historical time.

This archive preserves what those board selections showed when captured, including selected rows and coverage marks. It is **not** a full-universe event store, raw-evidence archive, or proof that arbitrary historical strategies can be replayed. Existing retention still limits later source-post retrieval. Later analysis specifications must respect this scope or add more capture prospectively.

Capture runs as its own 15-minute scheduler job, max_instances=1, coalesce=true, with a separate database session boundary. It must never call an external quote provider directly. Capture failure logs and leaves a gap; it must not stop ingest or scoring. No retroactive observations. Keep these small records until storage is measured at 7 and 30 days; do not introduce an automatic deletion policy in this release. Disable capture through RADAR_OBSERVATION_CAPTURE_ENABLED (default false until migration and staging verification).

Activity API: authenticated GET /radar/api/activity?days=7, allow 1/7/30 only. Return UTC from/to bounds for Berlin calendar days, generated_at, recording_started_at, and days containing completed-run sums plus completed_runs/incomplete_runs/error_runs. A day without completed runs has null counters. Label these as recorded fetch activity; completeness is partial/unknown, never 100% from successful runs alone. DST days use actual boundaries, not a fixed 24h subtraction.

Admin API: GET /radar/api/ops, auth.admin_required. Return generated_at, existing spend.summary(), llm_sentiment.ops_summary(), market_data.ops_summary(now), and capture latest_observed_at. No provider requests, credentials, source post bodies, machine paths, or control actions. Preserve existing board API compatibility in this release; removing its existing operational fields requires a separate compatibility decision.

## Release 1: navigation and data

Opt-in initial route: /radar/hub/. Keep /radar/ available as rollback during review. Use hash navigation inside the hub: #overview, #chatter, #research/TICKER, #watching, #activity, #admin. Filters live in the URL query; back/forward restores route, selection and research ticker. Detail span also travels in the URL. Unknown routes show a recovery link. Admin navigation is rendered only for admins; the API independently enforces authorization.

Reuse existing API query spelling: market, sources, window, segment, venues, sort, dir. Use existing Selection and queryFor; explicitly send segment empty for All. Default hub selection follows existing server defaults until the user changes it. Preserve concrete source selections in requests; do not accidentally widen subreddit filters to all Reddit.

Use shared React Query state for board/watch state. Query keys include every selection dimension; detail keys include ticker, market, sources, window, span. Search results are a separate query. Clear account-specific caches on an expired session; do not persist watch state in localStorage. Board refresh every 60 seconds only while visible; detail refresh every 60 seconds while its page is visible; stop retries for authentication/permission errors. Retain last successful data during refresh with its timestamp and an explicit refresh-failed notice. Abort obsolete reads; old replies may not replace the current market/ticker.

### Page acceptance

| Page | First-release content | Deliberate boundary |
| --- | --- | --- |
| Overview | Greeting-free heading, current session/market context, up to 3 current chatter candidates in server order, first 5 Watching rows, link to full chatter, visible generated time | No invented daily narrative, 'since last visit', return, or recommendation |
| Human Chatter | Ranked list with company, mentions, independent authors, relative activity when available, actual sources, quote/move and qualifying marks; filters and search; row opens research | Existing rank is described as chatter/price context, not conviction |
| Research | Company/quote identity, chart with price and chatter, source breakdown and actual posts, watch action, compact evidence summary using server clauses | No mock thesis or fake news. Source body is text, not injected HTML. Missing chart points remain gaps according to existing chart semantics |
| Watching | All caller watch_rows even if ineligible, with explicit quiet/unavailable states; search/add, remove and open research | No alerts, portfolio or promise of a tradable listing |
| Activity | Recorded daily fetch activity from Release 0, recording start, gaps and incomplete runs; existing coverage separately labelled | No total comments judged/discarded until explicitly recorded |
| Admin | Existing operational summaries and capture age, read-only, admin-only | No retry/restart/retrain controls |

News, Combined, Portfolio and Analysis stay in the design prototype and roadmap. Do not fill the production sidebar with disabled destinations. Research is reachable by search and row links; it need not be an empty top-level destination.

### Visual and interaction contract

Adapt the prototype's hierarchy: pine navigation; warm near-white workspace; white content surfaces; green primary action; Inter and tabular figures. Port token values from preview.css into a scoped hub.css; do not import prototype JS or change old radar.css globally. Keep charts central and raw operational counters off the research overview.

At 1440px research shows a compact candidate rail and central evidence with a narrow summary where space permits. Below 1100px the summary follows evidence. Below 700px navigation becomes a labelled toggle and research is one column: identity/actions, chart, summary, posts. No whole-document horizontal scroll. Data tables may scroll within a labelled region; do not hide the company, price currency, evidence quality, or watch action. Touch actions at least 44px; visible keyboard focus; chart information has textual equivalents; green/red is never the sole signal. Reduced motion respected.

Search uses a labelled input, 250ms debounce, keyboard navigation, Enter selection, Escape dismissal. Research opens in the same hub and Back returns to the preserved list. Watching mutation disables the affected control until completion; success adopts the server's entire watching list and refetches board/watch_rows; failure leaves prior state and displays an actionable error. No optimistic multi-click races.

Each page has first-load, measured-empty, partial/delayed, failed-refresh and unavailable states. Distinguish an expired session from a missing ticker and a forbidden admin endpoint. A quote timestamp is not the observation time of the chatter. Tests and screenshots use coherent fixture data and identify it as a fixture in review reports.

## Review and promotion

Claude implements one task at a time and obtains an independent read-only review before proceeding. Fix findings before marking tasks complete. Capture six pages at desktop and mobile plus the research tablet state. Compare composition with the approved prototype, not just absence of overflow. Owner visual review occurs on the opt-in route. Switching /radar/ to the hub and deploying require a subsequent explicit release step, including rollback and production migration checks.

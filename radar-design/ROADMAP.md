# Radar — from the current engine to the new hub

9 September 2026 · Proposed release roadmap · Planning only

## Recommendation

Build a genuinely useful first release around Overview → Human chatter → Stock research → Watching, with basic Activity and read-only Administration. Reuse the existing engine where it answers the new product's needs; replace the presentation and change APIs where it does not. Start historical evidence capture alongside this work. Add manual portfolio/trades next, then original news/professional coverage, then historical evaluation and combined recommendations.

The accepted light/green design and A-overview/B-research experience guide the work. Existing UI, old scoring and old feature exclusions are not binding. The mockup is a design reference, not production-ready application code. No implementation or deployment has been performed for this roadmap.

## Evidence and limits of this assessment

Inspected local checkout: C:/Users/michi/Desktop/CodingStuff, branch dev_personal, HEAD 7a9ffe445076e57d02fea5627e8cd185ec9cb39f. This assessment inspected code and documentation, not the running production database, feed entitlements or fresh production tests. “Exists” means an implemented repository capability; its live coverage, configuration and deployment must be checked before wiring the new UI.

The newest commit and `docs/superpowers/specs/2026-09-08-judge-hard-negatives-retrain.md` document a retrained encoder deployed as artifact v3. Older next-step notes saying there is no judge, or that its initial merge is still pending, are stale for this roadmap. Deployment of a classifier does not establish reliable directional sentiment or predictive trading value. Do not redispatch completed model work from old plans.

## What we have, and how far it gets us

| Future area | Available foundation | Remaining work |
|---|---|---|
| New hub / navigation | Flask Radar blueprint, authenticated routes, React/TypeScript frontend and Vite build | New shell, routes, selected theme, shared components, mobile navigation and page contracts |
| Human chatter | Board ranking; counts, expected activity, ratio, authors, sources, price context, quality marks and time series | New comparison experience, product-facing explanations, sorting/filter choices and live quality review |
| Stock research | Detail API with price/chatter history, source breakdown, concentration, original posts/URLs and tone provenance | Full research page, better chart/evidence interactions, listing clarity; cannot invent news or a trade thesis from a score |
| Watching/search | Search endpoint and per-account add/remove watching | Dedicated page, saved lists if useful, last-visit/seen state and alert rules/events |
| Overview | Board, watches, timestamps and research material | Overview aggregation and prioritization; “since last visit” needs saved visit state/snapshots; portfolio and news modules arrive later |
| Prices/listings/FX | Instrument mapping, venue/currency-aware quotes, daily closes, historical basis selection and FX storage | Verify live availability and quality; broker availability mapping; trade-ledger FX and price entitlement suitability |
| Activity | Durable 15-minute buckets and source coverage; ingest returns cycle counts/reasons | Aggregation endpoints and durable stage counters; exact all-time read/judged/discarded totals cannot be inferred from surviving rows |
| Administration | Sentiment backlog, market-data cycle summaries and model spend accounting | Read-only admin endpoints/view, access checks, incident history and any missing service-level telemetry |
| Portfolio/trades | Auth and per-user ownership pattern; instrument and price foundations | New financial ledger, entries/exits, partial closes, fees, cost basis, FX, corrections, notes and performance calculations |
| News/professional radar | Generic company identity and ingestion/classification experience | A distinct news source pipeline, original-event grouping, entity links, timestamps, rights/access and professional-opinion model |
| Historical analysis | Aggregated chatter, daily closes and some recent raw records | Point-in-time evidence/assessment archive, replay and comparison methodology; surviving aggregates are not historical knowledge snapshots |
| Combined recommendations | Chatter signals plus quote context | Original news evidence, evaluation, versioned decision policy, horizon-specific rules, counter-evidence and abstention |

### Specific reusable entry points

- `personal_apps/features/radar/routes/api.py:475` — `build_payload(args, now=None, user_id=None)`; board at `/radar/api/board` (line 507).
- Same file, `_row` (line 386) and `serialize_detail` (line 554) — the existing fields, not an assumed design API.
- Same file, watch PUT/DELETE (lines 517/528), search (line 538), ticker detail (line 652).
- `personal_apps/features/radar/watch.py:41` — `tickers_for(user_id)`; `add`/`remove` at lines 49/69. `RadarWatch` in models.py is already account-scoped.
- `personal_apps/features/radar/history.py:292` — `resolve_basis(ticker, quote, days, today)`; instrument and FX handling live beside it in instruments.py and fx.py.
- `personal_apps/features/radar/llm_sentiment.py:1123` — `ops_summary(now=None)`; `market_data.py:907` — `ops_summary(now)`; `spend.py:126` — `summary(today=None)`.
- `personal_apps/features/radar/ingest.py:348` returns cycle `posts_seen`, `posts_new`, `mentions`, source statuses and `intake_reasons`; `run_radar_ingest.py:378` logs the summary. A durable counter contract is additional work.
- `personal_apps/features/radar/config.py:691` — 30-day posts; line 698 — 48-hour mention events; line 705 — seven-day quote snapshots. Retention code has additional exceptions/pins. Inspect actual configuration before changes.
- `personal_apps/features/radar/journal.py:1` — ingestion journal, NOT a user trading journal. `RadarMarketTradeEvent` likewise describes provider market events, not the owner's buys/sells.

## Release 0 — Establish the baseline and start saving the future

**Outcome:** the new UI has a trustworthy data contract, and future analysis starts accumulating usable history.

- Inspect live endpoint payloads, migrations and enabled sources; compare with checked-out code. Record coverage, quote age, empty fields, model provenance and deployment differences.
- Map each first-release mockup field to an existing field, a new query, or a new capability. Design requirements may change the backend; missing fields do not become invented frontend values.
- Define company versus instrument identity, market/currency/timestamp labels, per-user ownership and common loading/gap states.
- Add a versioned observation archive sized to a realistic storage budget: observed/received time, evidence references, selected quote basis, signal features and source/method versions. Later recommendation snapshots extend it.
- Preserve enough original evidence to interpret snapshots, subject to source access/retention terms. Store compact summaries where full retention is inappropriate. Do not silently turn all raw retention into forever retention.
- Add durable per-cycle/per-day stage counts, with clear units: posts versus company-post judgments. Include retry/deduplication semantics so totals reconcile.

**Dependency:** must precede claims of historical replay or complete processing statistics. Snapshot capture can proceed alongside the first UI release; it need not block basic navigation or research.

**Exit checks:** representative payloads and mappings documented; archive writes are idempotent and versioned; privacy boundaries hold; counters reconcile; existing ingestion output is unchanged by observational instrumentation. Do not change trial populations or classifiers incidentally.

## Release 1 — A real research hub using today's engine

**Outcome:** the accepted design becomes a useful daily product immediately.

Build:

1. The independent Radar shell and responsive navigation.
2. Human chatter with current coverage, meaningful comparisons, source breadth and evidence-quality states.
3. Stock research with price/chatter, original posts, concentration and clear listing/currency provenance.
4. Dedicated watching and company search.
5. A first Overview: current notable chatter, watched-stock changes, direct research entry. Use “current activity” until true visit-to-visit changes can be computed.
6. Basic Activity and read-only Administration from available aggregates/operational summaries; richer counts appear once Release 0 has collected them.

Do not ship mock portfolio figures, fabricated stories or recommendation labels merely to fill the overview. Build the navigation to grow, but keep unavailable features out of the daily route until useful; the full future mockup remains available separately.

**Architecture recommendation:** retain the working Flask/React/TypeScript stack for this release. A new product experience does not require a framework or backend rewrite. Create reusable production components from the selected design, rather than importing preview.js and its local-storage sample ledger. Decouple operational summaries from normal board reads where it improves response cost and ownership. Maintain a reversible rollout path until the new experience is accepted.

**Exit checks:** real-data content across normal, sparse, missing-quote, stale and failed-source states; owner-specific watching; no duplicate count semantics; keyboard/mobile paths; focused API/component tests; screenshot review at desktop/tablet/phone. No “buy” inference from the existing divergence rank.

## Release 2 — Your trades, positions and alerts

**Outcome:** Radar becomes your personal workspace, not only a discovery tool.

- Manual buy/sell ledger with instrument, venue, original currency, timestamp, quantity, execution price and fees. Support partial exits and corrected entries without erasing history.
- Open/closed positions; realized and unrealized P/L; journal notes and linked research snapshots. Keep actual and hypothetical ledgers separate.
- Design EUR reporting explicitly. An existing historical FX helper is a reusable building block, not a complete transaction-accounting policy. Preserve recorded FX and expose missing rates.
- Choose and disclose cost-basis and performance methods before implementation. First deliver absolute P/L and holdings; percentage return/equity charts require cash-flow handling and a defined method.
- Identify splits/transfers/dividends within scope or explicitly require a recorded adjustment; do not silently report wrong holdings when these occur. No tax-reporting claim.
- Persist last-seen state and meaningful alert rules/events for watched stocks. Begin with in-app alerts, cooldowns, deduplication and acknowledgment; external delivery is a separate increment.
- Add real portfolio/watch changes to Overview once they exist.

**Dependency:** shell, user identity and stock/instrument contracts. Does not require news or a predictive recommendation engine. Basic in-app alerts can be split out and shipped before the ledger if faster.

**Exit checks:** known ledger examples for multiple entries, partial closes, fees, corrections, FX and dates; oversell rejection; account isolation; no automatic orders; alert deduplication and no-repeat behavior. Prototype calculations are not the acceptance oracle.

## Release 3 — Original news and professional context

**Outcome:** the second radar brings genuinely different evidence into research.

- Select an accessible first news source after checking coverage, rights, delay and cost. Prove it covers the small stocks that matter before adding many providers.
- Separate company releases, original reporting, syndication and professional opinion. Link the event to the company and instruments.
- Preserve published, received and corrected times; group coverage by original event while retaining attribution and opposing opinions.
- Evaluate entity resolution and professional sentiment on a labeled sample. Reuse infrastructure where appropriate, but do not assume a human-chatter classifier performs the same job on news.
- Ship News & professional, relevant event context on Stock research and truthful coverage modules on Overview.
- Add an event calendar increment only with a reliable event source; a news headline is not automatically a verified future date.

**Dependency:** identity/timestamps/archive from Release 0 and shared research destinations. Can run independently of portfolio work once shared foundations are stable.

**Exit checks:** no company/ticker confusion; syndicated articles do not inflate corroboration; corrections stay visible; missing professional coverage remains unknown; source permission/cost contract recorded.

## Release 4 — Replay, evaluation and learning

**Outcome:** the Analysis page answers what happened and what Radar actually knew.

- Start with descriptive price/chatter history where existing records permit it. Label it retrospective, not point-in-time evidence.
- Add true replay for periods covered by the new observation archive; freeze the information available at each instant.
- Link personal trades and notes to the evidence available at entry/exit.
- Evaluate chatter-only and chatter-plus-news cohorts against matched comparisons, including fees/spread, latency and coverage exclusions.
- Show sample size, outcome windows and uncertainty. Missing periods and unavailable prices must not disappear silently from evaluation.

**Dependency:** archive age/quality, appropriate price resolution, stable signal versions; news is needed for combined-source studies, not for all descriptive analysis.

**Exit checks:** later reports cannot leak into earlier snapshots; out-of-sample evaluation is reproducible; costs and quote availability are explicit; study cohorts and exclusions can be audited. The waiting period for enough observations is empirical, not a fabricated calendar estimate.

## Release 5 — Combined radar and qualified recommendations

**Outcome:** the hub combines evidence into a clear, explainable assessment.

Two separate milestones:

1. **Evidence synthesis:** connect human interest, original news, opposing evidence and price reaction. A useful combined view can ship without claiming predictive power.
2. **Decision policy:** introduce horizon-specific Consider entry / Wait / Avoid / Insufficient evidence only after defining and evaluating what each means. Version every recommendation and its supporting evidence.

Keep liquidity, spread, quote freshness, instrument availability, counter-evidence and invalidation conditions visible. Confidence measures need calibration; a decorative 92% score is not a decision system. No automated execution. If evaluation does not support an edge, retain useful evidence synthesis and keep predictive claims off.

**Dependency:** news plus historical/evaluation foundation for qualified recommendations. Evidence synthesis can arrive at the end of Release 3; it need not wait for the full analysis UI.

**Exit checks:** assessments reproduce from their saved inputs, abstain on insufficient evidence, separate horizons, and meet owner-approved evaluation criteria. Existing model relevance accuracy is not a substitute for trade-outcome evaluation.

## Expansion lane — longer-term depth and broader coverage

Keep long-term strategy tags and holdings possible from Release 2. Deeper long-term research is an increment: fundamentals, filings, earnings/catalyst history and sustained narrative change. It needs appropriate sources and analysis, not just a longer chart or different label.

Broker availability mapping is a separate research task: verified available / unavailable / unknown, with provenance and freshness. Scalable-specific filtering remains unverified until a maintainable source exists. International discovery stays broader than broker availability. Add more brokers, sources and exchanges by demonstrated coverage value, not by source count. Do not assume OTC coverage or executable German prices from an international company listing.

## How we should execute the roadmap

- Use one small, independently useful release at a time. Before each implementation, turn its slice into a binding spec plus detailed implementation plan with exact files/interfaces/tests.
- Keep the design, plan, progress ledger and HANDOFF.md together in that release's isolated worktree. One implementation worker followed by an independent read-only review. Do not repeat work marked complete without new contrary evidence.
- Treat the current source-discovery/extractor/judge work as a separate engine track. Coordinate API/schema and version boundaries. A missing classifier improvement does not block the shell or manual portfolio; it may block stronger sentiment/recommendation claims.
- Show each real-data release before deployment and agree the changed behavior. Preserve unrelated research artifacts and other apps.
- Record field/coverage limitations in the product naturally. The future vision remains intact while intermediate releases stay truthful and usable.

## Concrete next step

Prepare the Release 0/1 execution plan for a first real-data vertical slice: new shell → Human chatter → Stock research → Watching. Add the first truthful Overview around it. Start archive/counter instrumentation alongside it with its own isolated verification.

This is the largest immediate improvement available without waiting for news ingestion, portfolio accounting or recommendation validation. Calendar estimates should follow a live-data baseline and that bounded implementation plan; relative scope is clear now, completion dates are not.

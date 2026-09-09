# Radar — independent stock research hub

Design review 02 · 9 September 2026 · Light and green direction selected

## Selected direction

The owner chose A's welcoming overview and B's focused research workflow, both in A's light/green identity. C is rejected and is not part of the plan. The images remain historical probes, not templates to reproduce. Shared navigation, typography and components must make overview and research feel like one product.

The interactive review now lives in index.html, preview.css and preview.js. See REVIEW.md for routes, simulation boundaries and validation. Existing app files remain untouched.

## Authority and scope

This directory is an isolated design workspace, not application code. The owner's decisions in this conversation are the authority. Nothing in the existing UI, layout, palette, navigation or backend is binding. Radar has its own identity, independent of Gym, Clash of Clans and every other personal app. Do not apply `redesigning-pages-from-data`.

The existing `personal_apps/features/radar/PRODUCT.md` describes the CURRENT product. Its exclusions of recommendations, portfolio and alerts are explicitly superseded for this FUTURE design. Preserve the existing file for the working application. Source inspection is context, never a ceiling on the design.

Deliverables: whole-hub product design, contrasting visual directions, then sophisticated interactive mockups of every agreed page and important states. Desktop is primary; mobile gets a deliberate workflow. No production implementation, deployment, trading integration or automatic orders.

## Confirmed product intent

- Primary use: short holding periods and day trading, especially small-cap and penny stocks. Long-term research and holdings also supported.
- German owner, currently trades through Scalable externally. International discovery should remain possible even when a security cannot be traded there.
- Record buys and sells manually; show open positions, actual trade performance and research context. Hypothetical results must remain separate.
- Human chatter, professional/news sentiment, combined recommendations, historical analysis, activity statistics and administration all belong to one coherent hub.
- Backend changes and new capabilities are welcome to support the future experience.
- Every proposed page gets a mockup; do not silently reduce this to redesigning the current chatter table.

## Product thesis

Help me find unusual attention, understand the evidence, decide whether it deserves a trade, record what I actually did, and learn from the outcome.

The experience follows five activities: Discover → Investigate → Record → Monitor → Review. No page should exist solely because a backend subsystem exists.

## Proposed navigation and page contracts

These are recommendations for review, not yet approved structure. Grouping matters more than the exact labels. Avoid putting twelve peers in one flat navigation list.

| Area / page | Question it answers | Main content and action |
|---|---|---|
| Overview (signed-in landing) | What deserves my attention since I last visited? | Prioritized changes, watched-stock updates, portfolio context, upcoming catalysts; open a specific research thread |
| Discover / Human chatter | Where is independent human interest accelerating? | Candidates, change over baseline, breadth, sentiment and source evidence; investigate a company |
| Discover / News & professional | What new information or professional opinion emerged? | Deduplicated stories/events, publication time, publisher, reporting vs opinion, linked stocks; investigate evidence |
| Discover / Combined radar | Which setups deserve action, waiting or avoidance for my horizon? | Explainable recommendations, corroborating and opposing evidence, freshness, execution constraints; inspect thesis |
| Research / Stock detail | What is the case for and against this stock now? | Price, chatter, news, events, listings, availability, thesis history, related holdings and source posts; watch or record a trade |
| My stocks / Watchlists & alerts | What changed for companies I care about? | Saved lists, triggered and muted alerts, acknowledged changes; jump to evidence |
| My stocks / Portfolio & trades | What do I own, and how have my decisions performed? | Open/closed positions, transaction ledger, cash flows, actual performance, notes; record or correct a transaction |
| Review / Analysis | Did these signals help, using only what was known then? | Point-in-time replay, price response, comparison groups, costs and outcome windows; inspect a historical setup |
| Review / Activity | How active is discussion today, and how much did Radar process? | Separate market discussion patterns from ingestion/judging/discard counts; inspect volume and coverage by source |
| Administration (separate utility area) | Is the system healthy and what requires intervention? | Source delays, failures, backlog, model/provider health and cost; inspect incidents |

Research is a shared destination linked from all surfaces, not a second isolated universe. A public marketing landing is optional and deferred; the default landing proposed here is the signed-in overview.

Calendar events live in Overview and Stock detail initially. Journal notes live with trades and saved research. A separate calendar or journal page is justified later only if usage calls for it. Global search covers companies, tickers, stories and personal records.

## Shared rules that make the hub coherent

### Research horizon

Intraday is the initial research default. Long-term changes the analytical lens, time ranges and relevant evidence; it is not merely a chart range switch. Always identify the horizon of a recommendation. Portfolio strategy tags are independent: changing the research lens never hides or reclassifies actual holdings without an explicit portfolio filter.

### Identity and availability

A company connects its listings, source aliases and instruments. Prices belong to a specific instrument, venue, currency, session and timestamp. A dollar quote must not masquerade as the user's available euro execution price. Broker availability has three states: verified available (with time/source), unavailable, and unknown. Unknown is never silently treated as available. International discovery remains available when broker filtering is off.

### Recommendations

Future assessment should express an action, horizon, explanation and invalidation condition. Candidate vocabulary: Consider entry / Wait / Avoid / Insufficient evidence. The exact labels and decision methodology remain design proposals, not validated investment signals. Display why a setup surfaced, counter-evidence, quote freshness, relevant liquidity/spread constraints, and what would change the assessment. Do not use an unexplained confidence percentage as a substitute for evidence.

### Human vs professional evidence

News events, original reporting, analyst opinion and social discussion are different evidence types. Ten syndications of one story must not look like ten independent confirmations. Show supporting sources on demand, while keeping the reason and material uncertainty visible in the default view. Public anonymous commentary and a named professional's opinion should never be visually interchangeable.

### Portfolio and journal

Manual buy/sell entry captures instrument, venue, transaction currency, date/time, quantity, execution price, fees and optional linked research/strategy/notes. Support multiple fills and partial closes. Preserve original transaction amounts and FX basis; label reporting currency. Define and disclose cost-basis method before implementation. Corrections need a reviewable history. Corporate actions and transfers require explicit handling; never manufacture a profit because of a split or deposit. No tax-reporting claim.

Actual and hypothetical portfolios have separate ledgers and performance. Distinguish realized P/L, unrealized P/L, deposits and withdrawals. Portfolio percentage performance needs a stated calculation method; mockup numbers are illustrative until the accounting contract is agreed. Broker authentication and order routing are outside this design's scope.

### Analysis and learning

Persist what Radar knew at each timestamp: evidence observed/available time, recommendation revision, model/method version, quote basis and source coverage. Retrospective evaluation must not quietly use later stories or revised data. Allow outcome windows, spread/fees and plausible execution delay. Compare signals with a relevant baseline; show sample size, missing coverage and uncertainty. A replay is not a claim that a trade would have filled.

### Activity vs operations

Activity offers two explicit views: Market discussion and Processing. Distinguish read, eligible, judged, duplicate, discarded and pending counts using a defined time window; stages must reconcile before charts imply a funnel. Source downtime must not look like a quiet market. Admin owns actionable failures, backlog, configuration and costs. Ordinary research receives only the quality notices needed to interpret its evidence.

## Proposed interaction journeys

1. First visit → short personal overview → emerging company → linked price/chatter/news evidence → save to watchlist → choose meaningful alert.
2. Alert received → see what changed and when → compare supporting/opposing evidence → execute elsewhere → Record trade prefilled with instrument and linked thesis (never with an assumed execution price).
3. Open position → review latest company evidence → manually record partial sell → inspect remaining quantity, realized P/L and original reasoning.
4. Weekly review → actual trade performance → choose a trade → replay information available at entry → annotate lesson; do not rewrite historical evidence.
5. International discovery → instrument availability unknown/unavailable → continue research or create hypothetical entry → remain visibly outside actual portfolio.
6. Longer-term research → longer horizon with catalyst and evidence history → save thesis → distinguish long-term holdings in portfolio without losing intraday context.

## Visual directions to compare

### A. Daily Brief — proposed default for the hub

Scene: checking Radar at a desk in afternoon daylight before US activity picks up, wanting a clear starting point. Bright neutral reading surface, restrained pine accent/navigation, readable single-family typography. A considered morning briefing and a research portal are structural references, not aesthetics to copy. Prioritized stories and watchlist changes lead. Advantage: strongest welcome and broad hub cohesion. Tradeoff: needs a fast route into dense research during active trading.

### B. Research Desk

Scene: focused evening investigation alongside a broker window. Dark neutral surface and restrained selection colors. Candidate list, shared chart/evidence workspace and thesis panel. Reference objects: an analyst's working desk and a split-view document reader. Advantage: least navigation between candidate and evidence. Tradeoff: can recreate the current development-tool feeling if density and micro-metrics creep back in; should not dictate every page.

### C. Discovery Atlas — rejected; historical option only

Scene: an exploratory desk session comparing where attention and price are diverging across the universe. Light neutral surface, cobalt analytical accent, large labeled comparison plot and explanatory selection. Reference objects: an annotated scientific atlas and a museum collection browser. Advantage: reveals relationships a list hides. Tradeoff: less direct as the daily home; requires thoughtful handling of small datasets, missing prices and mobile. Provide a synchronized list alternative.

These probes mixed page purpose with visual style, so they were not a controlled same-page aesthetic comparison. The owner nevertheless selected A's overview plus B's workflow, then explicitly selected light/green styling. C is excluded. Do not combine the palettes or crowd the layouts onto the landing page.

## Mockup coverage after direction review

All page contracts above require desktop designs. The following flow-specific states must also be visible, not only listed in a spec:

- Chatter: busy, quiet, no matches, weak baseline, missing/delayed price, missing source coverage.
- News: shared/syndicated event, conflicting opinion, corrected story, no recent coverage.
- Combined: actionable assessment, wait/avoid, insufficient evidence, stale assessment, horizon change.
- Research: selected company/listing, source evidence, counter-evidence, chart annotations, unknown broker availability.
- Watchlist: first-use, list with changes, create/edit/mute alert, acknowledged event.
- Portfolio: empty account, filled account, entry form, partial sell, invalid quantity, corrected transaction, missing quote, separate hypothetical account.
- Analysis: select historical moment, replay, cohort comparison, insufficient sample, missing observations.
- Activity: quiet market vs collection outage; market vs processing tabs.
- Admin: healthy overview, degraded source and incident detail; controls shown as simulated proposals only.
- Shared: loading, recoverable failure, search with/no results, long company names, keyboard navigation and selected context on return.

## Mobile strategy

Phone home prioritizes changed watched stocks, active holdings and alerts. Full research remains reachable. Desktop multi-pane research becomes sequential candidate → detail navigation with preserved filters and return position. Chart interaction must work by tap and expose the same key values without hover. Recording trades uses a full-page form. Administration is available but not prominent in mobile navigation. Tablet is a layout of its own when two panes no longer fit comfortably. The first prototype stacks the overview in content order; a stronger mobile prioritization remains a review question.

## Future capability needs (proposals, not implemented)

- Company/listing/broker availability mapping and provenance.
- Timestamped news/event normalization and professional evidence classification.
- Versioned combined assessments and point-in-time snapshots.
- Quote/execution-context data appropriate to intended horizons; gaps stay explicit.
- Private per-user watchlists, alerts, notes and transaction records. Shared market data does not imply shared private portfolios.
- Transaction and FX ledger, corporate-action handling, documented performance accounting.
- Historical replay and evaluation datasets with observation-time semantics.
- Source coverage, processing-stage counters, incident state and cost observability.

## Decisions deferred until visible review

Exact navigation labels; recommendation wording and methodology; production portfolio cost basis/performance calculation; availability data source. English UI and Berlin-local display times are working mockup assumptions, not a binding inheritance from the current app. All concept prices, returns, news and companies are fictional. No claims of predictive accuracy or verified broker availability.

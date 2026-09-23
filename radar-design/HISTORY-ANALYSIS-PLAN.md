# Current status — independent final review COMPLETE

The owner supplied the completed independent review on 2026-09-14: no material issues found; the implementation satisfies the binding Human Chatter ranking contract. Implementation and independent review are COMPLETE for this uncommitted candidate. No repeat implementation/review assignment is open.

Independent reviewer-reported fresh evidence: backend focused suite 29 passed; frontend focused suite 4 files / 125 tests passed; git diff --check passed. The reviewer reported preserving all dirty files and making no code or documentation changes. The Product Overview planner verified current Git state and read the handoff/plan/ledger/return, but did not rerun those tests or independently reproduce the reviewer results. The production build/typecheck pass remains implementer-reported evidence, not an independent review build.

Residual verification limits remain explicit: direct/shared producer, API and parity integration could not safely run because only protected localhost:3306/personal_apps was available. Do not bypass the gate, use B1C's database or create an improvised target. No safely isolated actual-app preview was available, so no screenshots exist. The 6.5-hour price-period assumption remains unaudited and outside scope. Review completion does not mean these gates passed or that release readiness was demonstrated.

Current candidate: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-human-chatter; branch codex/radar-human-chatter; verified HEAD/base a161dc3793aede70b31e1cb1cf851607f918881f. Implementation and planning changes remain uncommitted. Git's ignore-file/.pytest_cache permission warnings limit untracked enumeration. Existing dirty implementation and historical B1C files were preserved; this status reconciliation changes planning documents only.

Product recommendation: owner approval for a scoped local commit of the reviewed candidate and its planning evidence. Commit, integration, push and deployment are NOT authorized by this record. Keep the integration/visual gaps visible for any later integration/release decision; no automatic test/review loop. Historical analysis remains next after disposition of this candidate. Capture remains OFF. No migrations, root promotion, B1C/PERF3 changes, port-5021 use or production access.

Contract unchanged: default membership/order is independent of price, quotes, freshness, direction and session; price remains visible and explicitly sortable within the selected candidates; existing mention_z with no new score/weights/boosts/predictive claims; original /radar/ defaults unchanged.

This notice supersedes older open-review, worktree-creation and next-action instructions below. Detailed historical evidence is retained.

---
# Current priority — 2026-09-14, Human Chatter ranking

The owner approved a bounded ranking change before historical analysis. Binding scope: [HUMAN-CHATTER-RANKING-PLAN.md](HUMAN-CHATTER-RANKING-PLAN.md); progress: [HUMAN-CHATTER-RANKING-LEDGER.md](HUMAN-CHATTER-RANKING-LEDGER.md). For root-level readers these files are under radar-design/.

Human Chatter will select and rank unusual discussion independently of price, before top-N truncation. Price remains visible and explicitly sortable. Use existing mention_z provisionally; no new composite formula or predictive claim. Preserve original /radar/ behavior and PERF3 shared-board architecture. Implementation and independent review are COMPLETE with the recorded verification limits; owner decision on a local commit is pending. No agents have been dispatched by the planner.

Historical analysis remains the next new feature after this bounded interruption, ahead of portfolio/news. Future HA captures must identify the ranking policy and selection; legacy divergence selections and new chatter selections are different populations and must not be silently pooled or relabelled. No HA implementation is included here. Use the actual app for future UI work, not a separate interactive prototype; this supersedes older prototype instructions.

B1/PERF3/B1C remain complete and deployed at 200c51cc402e053575bf9e0008db597ea27b36a5. Bars are owner-confirmed; tone latency is accepted, not a passed target. Capture remains OFF. No push, deployment, migration or root promotion is authorized. Preserve main checkout, PERF3 files, other worktrees, port 5021 preview and the untracked missing-bars-local.png investigation screenshot.

This notice supersedes historical next-action and assignment text below, not the recorded evidence.

---
# Current status — 2026-09-13, B1C live and owner confirmed

B1C deployed at 200c51cc402e053575bf9e0008db597ea27b36a5 with explicit owner authorization. The owner subsequently confirmed the chatter bars work; the apparent missing-bars issue was resolved by scrolling. Investigation cancelled, no product fix required. Busy-ticker tone latency is accepted for this iteration, not a passed performance target. Capture remains OFF; /radar/hub/ remains alongside /radar/; no root promotion.

Deployment evidence and exact operational state: root HANDOFF.md. Prior pending-release, unimplemented-tone and latency-blocker statements below are historical and superseded by this notice. Preserve historical evidence; do not redispatch completed work.

---
Current design direction: B dark research workspace. HA remains the next new feature before portfolio/news. B1C retained-evidence bars are implemented; durable historical tone is not. Earlier light/green and planned-only statements below are superseded.

> Accepted addition, 2026-09-13: [B1-TONE-CHART-ADDENDUM.md](B1-TONE-CHART-ADDENDUM.md) adds per-interval bullish/bearish/neutral-or-unjudged stacked chatter bars to upcoming B1 chart work, carried into HA1 and Combined Radar. Planned, not built. Preserve completed B1 and deployed PERF3 work.

# Historical analysis before portfolio and news

Planning draft, 2026-09-09. Owner requested this priority change while Claude prepares the first hub release. Codex owns this design; no application changes or changes to Claude's active worktree are made here. This is a product/data plan, not a task-level implementation dispatch.

## Decision and scope

Next feature after the first hub: historical chatter/price analysis. Portfolio and news follow it; neither is required to learn from the existing human-chatter radar. The aim is to answer: what was being discussed, when did Radar notice it, what did prices subsequently do, and where did the apparent signal fail?

Approaches considered:

| Approach | Value | Limitation |
| --- | --- | --- |
| Existing history only | Fast retrospective explorer | Current aggregates can contain later corrections; cannot establish what was known then |
| Current fixed board archive only | Honest replay of what selected boards displayed | Rank-capped population, incomplete evidence and insufficient intraday price outcomes |
| Staged explorer plus targeted prospective capture — selected | Useful first page now and a defensible path to evaluation | Additional capture contract and storage/coverage measurements required |

Keep the light/green identity and research-first workflow. No buy/sell verdicts, paper-trade ledger, news placeholders or claim of a profitable strategy in this release.

## Three increments

**HA0 — capture readiness.** Specify and implement the small additional archive needed for the studies below. Existing board capture can still start as planned: its first day remains valuable for display replay. Record separate start dates for each dataset; enhanced capture does not retroactively improve earlier snapshots. Do not delay the side-by-side hub release or require Claude to change its current release package.

**HA1 — historical explorer.** Search a company, select a period, inspect price and chatter on a shared time axis, examine activity peaks and their available evidence. Existing daily closes and 15-minute chatter buckets support a retrospective view where data exists. Intraday prices appear only at their actual retained resolution. Replay a saved board exactly where observations exist. Show data availability before inviting detailed interpretation.

**HA2 — signal evaluation.** Evaluate a predeclared chatter-only cohort over captured periods. Include quiet/unsuccessful cases and exclusions, display sample sizes and distributions, and compare to an appropriate contemporaneous baseline. This is a study of signal outcomes, not an executable trading strategy. Entry/exit simulation and spread/fee assumptions are an explicitly separate mode with stricter data requirements. No fixed calendar wait promises: readiness depends on coverage, events, distinct companies/sessions and validation quality.

## Questions and defaults

1. Did chatter rise before, during or after a price move? Explorer supports this question; it describes temporal alignment rather than causation.
2. After a company first appeared on a saved radar selection, what price observations followed at 15m, 1h, 4h and next regular-session close? First cohort uses new appearances, not an arbitrary optimized threshold. Horizons unavailable in the price archive remain unavailable.
3. Do broader-source signals differ from single-source ones? Compare strata within the captured population and source-config version, never treat syndicated/repeated source activity as independent votes.
4. How often did nothing happen, the price move against the signal, or data become unavailable? Keep all three categories visible.
5. How much does a later correction change the retrospective picture? Compare a captured observation to today's reconstructed view where possible; never silently replace one with the other.

Initial study event: first appearance of a company in one selected market board after an observed prior board omits it. At least 24 hours between counted events for that company/market/selection. A first snapshot or appearance following a capture gap has unknown prior membership and is excluded from the new-appearance cohort, but remains visible in exploration. Keep all snapshots; event deduplication belongs to a versioned study, not the archive. The one-hour default chart context around an event does not change the event rule.

Initial cohort scope is explicitly 'companies appearing in this saved top-50 board selection'. It does not establish results for all penny stocks or all companies. US and German price contexts are separate studies; duplicated social identity does not create independent observations. An all-universe claim requires the broader decision population described below.

## Page and interaction design

Add one Analysis destination when HA1 is ready. Within it use three modes, with a shared market/time context:

- **Explore:** company search, date range and resolution, synchronized price/chatter plot, coverage strip, selectable event markers, evidence beneath the plot. Default to the most recent seven available days; allow one day and custom ranges within availability. Empty history opens a coverage explanation instead of an empty chart shell.
- **Radar replay:** choose an archived selection/date/time. Previous/next moves between actual snapshots. A gap remains visibly a gap; do not interpolate a ranked list. Selecting a company opens its research at that observation, with current research offered as a separate labelled link.
- **Studies:** choose an immutable saved study definition/run, see outcome distribution and coverage before any headline return. Drill into every event and exclusion. An 'insufficient history' state explains missing inputs and links to exploration; do not fill it with mock performance.

Desktop composition: slim controls above the main plot; an approximately 70/30 plot/context layout where width permits; evidence and event table below. At phone width: controls, coverage notice, plot, selected event, evidence. No tiny chart required to convey the result: selected point values, times and measurement quality have a text/table equivalent. Retain visible currency, market, source selection and 'retrospective'/'captured then' labels at every width.

Mockup review packet before UI implementation: (1) company with usable daily price/chatter but no retained posts, (2) complete intraday event with delayed quotes, (3) snapshot gap, (4) split/venue change, (5) failed/flat event, (6) study with exclusions and too few observations. Render desktop and phone Explore plus desktop Replay/Studies, using one coherent labelled fixture dataset. The existing analysis prototype is a direction reference only; it does not implement these contracts. These mockups remain to be created/reviewed before a detailed frontend execution plan.

## What the existing code can and cannot supply

Inspected repository evidence: models.RadarBucket/RadarBucketSource retain aggregate bucket history; history.py resolves venue/FX price basis; the detail API serializes chart data and retained posts; observations.py captures two fixed market boards with limit=50 and excludes account/ops data. Config currently names post retention 30 days, mention events 48 hours and quote retention 7 days, with exceptions in retention.py. Treat those as code policies, not proof of current server coverage. Current price sources can restate stored closes. Before implementation, recheck against Claude's then-current integrated branch and actual dataset.

| Question/data | Existing basis | Missing contract |
| --- | --- | --- |
| Retrospective chatter history | Per-source 15-minute buckets and coverage flags | A range query beyond the current now-relative detail API; distinguish unmeasured from zero |
| Retrospective price history | Daily closes, selected quote history, basis resolver | Explicit actual availability, adjustments and gaps; no 15-minute return from daily closes |
| What the board showed | Fixed-selection immutable board observations | Selection-constrained replay UI and query; cannot freely change historical filters |
| What was known when | Snapshot observed_at and generated_at | Individual inputs' received/available times and model/config identity are not guaranteed by a Git SHA alone |
| Original explanation | Posts/judgments while retained | Evidence availability ledger and permissible selected-event retention strategy |
| Outcome after appearance | Some quote/close history | Durable, venue-specific follow-up prices and first-available times before quote pruning |
| Nonselected comparisons | Current buckets/catalogue | Point-in-time candidate membership, exclusions and eligibility; today's catalogue is not the old population |

Do not sum distinct_authors across buckets and label it unique people over a day. Without retained identities or a validated distinct-count representation, display the per-bucket series or call the sum author-bucket observations. Likewise preserve root/concrete-source grouping to avoid counting Reddit twice. Do not average ratios or z-scores across time as if they were counts. Archive the actual feature values needed by a study or recompute from demonstrably point-in-time inputs.

## HA0 capture additions: proposed contracts

Prefer separate append-only records over altering the meaning of the current board snapshot schema. Final table/index/task details follow the measurement gate below.

**Observation manifest:** capture_id, actual UTC captured_at, board generated_at, selection, schema version, deployed revision, scoring-policy version, model artifact identifier/hash when available, source-configuration identity, and input-quality flags. Unknown provenance stays unknown. One company's identity includes stable internal identifier if available plus the observed ticker/name and selected listing/MIC/currency; preserve mapping effective at observation. A Git revision does not identify a separately deployed model artifact.

**Decision population:** if capturing the population becomes affordable, one compact record per evaluated company per capture with inclusion/eligibility reason and the specific score inputs, not full chart arrays. This enables comparison beyond winners. Snapshot top-ranked members plus membership lists alone are insufficient for arbitrarily re-running thresholds. Start with the top-50 appearance study if population capture fails the storage/latency gate; label its limit explicitly rather than block HA1.

**Evidence summary:** preserve counts, source breakdown, observed judgment/model availability, source-reference IDs and evidence availability status at capture. Raw body retention is not automatically extended. If selected excerpts are later retained, first establish the source access/retention policy and deletion handling; do not assume a hash substitutes for the content. Deleted/expired posts show 'evidence no longer available', never zero original posts. Archive no account watch state or user trade data.

**Outcome sampling:** register study candidates from actual observed appearances and collect future price observations into a durable analysis dataset. Store observation time, provider price time, receipt time, listing/MIC, currency, trade/midpoint/close basis, quality/delay, bid/ask when present and selected horizon. A collector retries missing data with bounded effort and records unavailable, not a replacement company or an invented price. Persist outcomes for failures/delistings as unresolved/unavailable when appropriate; don't remove them from denominators. Copying existing provider observations is preferable to adding new paid requests; measure provider coverage before promising minute-resolution outcomes.

Quote outcomes at target horizons use the first eligible observation at or after the target within a predeclared tolerance; no nearest-price rule that picks an earlier observation opportunistically. Define tolerance per source/resolution in the study manifest. Daily-only data supports close-to-close outcomes and must not be labelled an intraday result. Retain after-hours/closed session labels; unavailable targets remain unavailable. For simulated execution use a future observable quote after the chosen decision latency, never the price from before the chatter was received. Midpoints are valuation references, not guaranteed fills.

**Time and revisions:** event time, first received time, judgment available time and captured time are distinct. A late-arriving post may contribute to today's reconstruction of yesterday but must not appear in yesterday's knowledge replay. Corrections append with revision/effective/received timestamps; do not mutate prior study inputs. Point-in-time readiness is the latest required input availability time, not just the post publication time.

Do not enable extra collection simply because this document exists. Current v1 board capture can follow the authorized release process independently. HA0 adds a later capture schema/start boundary; expose that boundary on the Analysis page and in Admin.

## Measurement and implementation gates

HA0 implementation starts only after a source-grounded detailed plan against the integrated release branch. Its first task measures representative trading-day candidate count, snapshots/day, serialized bytes, follow-up price availability and retention implications. Forecast 7/30/90 days including indexes and study outcomes, and time capture under normal ingest load. Set an explicit storage budget and bounded collector batch size from those results; do not infer a safe budget from an idle local database. Collector reads/writes remain isolated; failure cannot stop ingestion. Retry/idempotency and job-instance limits are mandatory.

Retain captured observations and study inputs for a defined analysis period selected at this gate; no blanket forever-retention expansion. If retention removes inputs, the study manifests retain provenance and mark exact reproduction unavailable. Do not silently continue to claim replay fidelity.

HA1 backend interfaces proposed:

- GET /radar/api/analysis/availability?market=us&ticker=... returns independent coverage/resolution ranges for price, chatter, snapshots and evidence; no source body leakage.
- GET /radar/api/analysis/company/<id>?from=...&to=...&market=... returns bounded retrospective series, provenance and gaps. Reject unbounded ranges; use downsampling chosen by output resolution, not silently changed measurements.
- GET /radar/api/analysis/observations?selection_id=...&from=...&to=...&cursor=... returns actual snapshot IDs/times; GET by snapshot ID returns the stored payload.
- Saved study definitions/runs are versioned resources introduced in HA2, not computed synchronously on every page refresh. Initial access is authenticated; expensive run creation should be owner/admin-gated and queued with quotas at implementation time.

These are proposed interfaces, not existing endpoints. Resolve stable company IDs and listing behavior in the detailed plan; if unavailable, require ticker plus observed market/listing identifiers and explicitly handle symbol reuse. Never reassign historical records to a today's company name solely by ticker.

## Evaluation rules for HA2

Freeze selection, event policy, cooldown, horizons, price tolerances, data/model versions and exclusion rules before calculating the held-out period. Keep exploration and evaluation periods separate. Include baseline event outcomes drawn from the same time/market/eligible population where that population is captured; otherwise say the comparison is unavailable. A rank-capped sample cannot justify broad market claims.

Show event count, distinct companies, sessions, available/missing outcomes and exclusions alongside return distribution. Repeated events from one company or one market day are dependent; do not inflate confidence by treating them as independent. No arbitrary minimum count makes a result reliable: require a study-specific review of coverage and effective sample diversity before a summary verdict. Avoid optimizing many thresholds then advertising the best result without held-out validation.

Corporate actions, ticker reuse, delistings and trading halts need explicit flags. Use consistent raw/adjusted price basis and a documented adjustment policy; never compare opposite sides of a split as an ordinary return. Preserve currency throughout; EUR reporting and FX attribution are separate from native-listing outcomes. Availability on Scalable remains unknown unless verified, and outcome studies must not imply the owner could have executed every trade.

## Delivery and verification map

| Increment | Deliverable | Exit evidence |
| --- | --- | --- |
| HA0 | Bounded prospective capture and availability manifest | Late-arrival, immutable-version, candidate-denominator, retention-gap and idempotency tests; storage/load measurements; capture failure leaves ingest healthy |
| HA1 | Explore + saved-board Replay | Coherent desktop/mobile mockups; real-range API tests; missing vs zero, source distinct counts, daily vs intraday, currency, snapshot-gap and expired-evidence cases |
| HA2 | Reproducible appearance study and drill-down | Frozen manifests, repeatable event inclusion/exclusion, no future-data leakage, missing outcomes retained, action/price-basis tests, independent review |

News enriches analysis later without replacing chatter-only studies. Portfolio later links actual entries/exits to observation IDs. Combined recommendations remain last and depend on stronger evidence than simply having an Analysis page.

## Coordination with Claude

Claude's current task remains the release proposal/MariaDB rehearsal in CODEX-DECISIONS.md. No change to its active worktree, migration head, runtime flags or completed task ledgers is made here. After that return, Codex will carry this planning package into the next isolated feature workspace and produce the HA0/HA1 execution plans. Do not dispatch HA0 from this draft or repeat R3. Owner review of historical-analysis mockups is still open.

## Market-data dependency amendment — 2026-09-10

Read MARKET-DATA-ROADMAP.md alongside this plan. The owner requested integration
of the OpenTerminal review. MD-01 establishes current coverage/history needs;
MD-02/07/05 and MD-10 improve selected-instrument lines, history, quotes and
failure handling alongside HA0/HA1. MD-03/08 evaluate broad US/German observations;
MD-04 uses that evidence for source-aware selection and scoring. All remain open.

Do not wait for every provider evaluation to ship an honest daily-resolution
HA1 explorer. Do not treat current fixed slots, providers or scoring logic as
future constraints. HA0 must preserve source/event/available-time, identity,
venue/currency/basis and policy versions through transitions; HA2 must distinguish
regimes and require actual horizon data. Capture is still off and separately
commissioned. No adapter implementation or provider promotion is authorized here.

MD-06 earnings and linked news context follows the first usable HA1, before the
full news/professional workstream; later-retrieved news is retrospective unless
its historical availability is recorded. MD-09 follows basic context. MD-11's
chart richness grows with HA1 and beyond, but candles/volume need real OHLCV.
Original A/B visual ambition remains the long-term target. Next work is a
coordinated measurement/design packet, not implementation from this amendment.

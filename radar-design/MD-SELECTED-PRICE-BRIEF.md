# Selected-instrument prices — decision brief

2026-09-15. Mastermind planning only. Owner approved preparation of this brief, not implementation, deployment or automatic worker dispatch.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore. Branch: codex/radar-ha1-us-daily-explore. Verified HEAD: daadf3868caedcb5db858378e919cba68b735f8a. HA1 remains COMPLETE / DEPLOYED / CLOSED. Ledger: MD-SELECTED-PRICE-LEDGER.md in this directory.

## Outcome and recommended boundary

Improve the price displayed when someone opens an instrument in Research or the shared Chatter research panel: useful 1D detail, genuine multi-session 1W history where evidenced, and an honestly timestamped headline. Coordinate MD-02/07, MD-05 and MD-10 in one decision packet. Recommend US-primary native-USD as the first adapter scope, preserving existing German/international behavior. This is not a global USD policy.

Three options:

1. **Recommended: selected-instrument adapter with independent timestamped series.** Validate Nasdaq 1D and Nasdaq/Finnhub headline candidates; investigate a bounded Yahoo multi-session candidate. Include only capabilities established by the evidence. Ship cache/failure/health controls with the adapter. Gives useful detail without coupling source acquisition to board collection.
2. **1D-only first increment.** If multi-session or headline evidence is insufficient, deliver a truthful 1D line and explicit stored daily/observed-anchor fallback. Retain headline selection until it can be justified. This is an acceptable result of the same investigation, not a reason for repeated review cycles.
3. **Broad price-system replacement.** Defer. MD-03/08 discovery scans, German venue strategy, MD-04 scoring selection and poller retirement have wider dependencies and are not prerequisites for this increment.

## Existing evidence, recovered and qualified

The following original files were located and read in the main workspace; they were absent from this worktree. Keep them read-only and use their absolute paths on handoff:

- C:/Users/michi/Desktop/CodingStuff/docs/superpowers/specs/2026-09-10-radar-openterminal-comparison.md — Claude's dated source comparison, including reported probes. Its candle, scan-write, permanent-source-failure and User-Agent causal claims are qualified/corrected by the independent review.
- C:/Users/michi/Desktop/CodingStuff/personal_apps/scratchpad/openterminal_probe/codex_review_probe_results.json — saved 2026-09-09T22:28:43Z result summary: AAPL 868 x/y timestamped line points, first/last samples, info trade timestamp and bid/ask. This file is a summary with samples, not the complete 868-point response. Quote currency is null; USD cannot be inferred solely from a dollar sign.
- C:/Users/michi/Desktop/CodingStuff/personal_apps/scratchpad/openterminal_probe/ — original probe scripts and copied provider sources remain available. Original Claude raw execution outputs were not established by this inspection.

Local binding interpretation: docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md and radar-design/MARKET-DATA-ROADMAP.md. They establish candidates and questions, not production-ready providers. Nasdaq's sampled last session does not establish five-session history or OHLCV. A real-time flag is not sustained freshness evidence or a consolidated-tape guarantee. Historical access says nothing conclusive about current access or usage conditions.

MD-01C-RULING.md accepts attributed daily coverage evidence: 12,294/12,599 eligible mapped US instruments had a usable daily close in the measured seven-day window. It does not measure current intraday coverage. Q4 195/225 remains provisional and is not an oracle. Do not repeat MD-01 coverage or HA1 acceptance to start this work.

## Current integration evidence

Fresh local source inspection at the HEAD above, not runtime execution:

- personal_apps/features/radar/detail.py:349 intraday_chart_for uses shared price/chatter slots. 1D samples retained quote observations; 1W uses daily/selected observed anchors through history.resolve_basis and _daily_anchors. The existing 1W path is not a genuine dense multi-session series.
- personal_apps/features/radar/detail_panel.py:350 build assembles quote, chart and other detail; quote_views_for is called at line 367. Trace its consumers before choosing an interface so a slow upstream cannot stall unrelated detail.
- personal_apps/features/radar/quotes.py:287 and :311 still order candidates by fetched_at. Do not insert display observations into this path as a shortcut to headline selection.
- personal_apps/static/radar/src/hub/ResearchContent.tsx supplies ChartSection to Research.tsx:113 and ChatterWorkspace.tsx:378. Both need contract compatibility. Its captionFor special-cases daily 1D but has a fixed intraday 1W caption; resolution labels belong in the planned data contract. This is a static observation, not a new HA1 defect/review assignment.
- personal_apps/features/radar/prices/yahoo.py already has bounded transport/cache/backoff and identity helpers; assess reuse before building another transport. Existing code is not proof that all required multi-session behavior works.

## Contract to settle in the implementation packet

- Pin company/instrument/provider symbol, listing/MIC and native currency. Preserve identity verification and make unknown metadata explicit. No invisible cross-venue or converted/native series splicing.
- Separate price points and chatter buckets on an actual time axis. Keep mentions unchanged; no invented candles, volume, observations or historical z-score. Gaps and source/adjustment regime boundaries remain visible.
- Specify whether 1D means current/last trading session and whether 1W means five sessions or a trailing calendar week. Recommended provider request: current/last session and five actual sessions, with displayed dates and aligned chatter bounds. This changes today's rolling windows and must be explicit in the final spec.
- Define provider event time, received time, session, delay, price basis, adjustment basis, covered range and resolution separately. Null/zero/invalid observations are unavailable, not successful prices. A fallback carries its own provenance and age.
- Headline selection must compare compatible event times/session/basis, not fetch order. Do not retire Finnhub's poller through a display-only change; assess its other consumers first if retirement is later proposed.
- Bound cache keys/cardinality/bytes/TTL and stale age, coalesce concurrent requests, cap upstream requests and total read latency, stop on throttle/auth failures with backoff, and count success/empty/invalid/timeout/throttle/stale/fallback distinctly. Account for actual web-process topology; process-local deduplication is not a global traffic bound. Numeric limits must be stated in the implementation spec as application choices, not inferred provider allowances.
- Prefer coherent stored-series fallback for the same instrument/basis, labelled daily or sparse observed anchors. Do not silently stitch a provider partial range and incompatible stored data into one continuous line. Unsupported symbols and offline upstreams leave usable explanatory states.

## Only decision-critical evidence still needed

One Researcher assignment, MD-SELECTED-PRICE-EVIDENCE-1:

1. Verify candidate response semantics across a small disclosed instrument sample (US equity on Nasdaq and NYSE, ETF, small-stock candidate and symbol edge case), including empty/invalid behavior. Sample classification must be evidenced, not assumed current.
2. Establish the returned multi-session range, spacing, missing/null values, venue/currency and adjustment evidence. Yahoo is a candidate, not a settled choice. A last-session endpoint cannot pass this requirement.
3. Compare paired Nasdaq/Finnhub quote event age and identity where credentials/access already exist locally. A short sample can recommend trial priority but cannot establish sustained reliability; absent access is an explicit limitation, not a reason to obtain production secrets or start infrastructure work.
4. Check current primary-source documentation/usage conditions for the actual intended use and recommend conservative operational limits. Preserve unresolved ambiguity without inventing legal conclusions or an automatic extra approval ceremony.
5. Trace the minimum code interfaces/cache reuse and recommend the smallest useful implementation scope, including explicit defer decisions. No full architecture review, benchmark or HA1 retest.

Public provider research is a proposed worker assignment only. No provider requests, DB access, production operations or implementation occurred during this brief. Owner chooses the worker/model and pastes the prompt. No worker is running merely because this brief exists.

## Stop and next decision

Researcher returns one durable evidence report plus small sanitized artifacts and a self-contained Mastermind return prompt. Mastermind then selects the supported capabilities and writes one binding implementation packet. Unavailable evidence can narrow the first increment; do not commission repeat broad reviews. Normal eventual path: one implementer, one independent focused reviewer/QA, then owner-authorized deployment.

Preserve all existing dirty/untracked continuity, HA1 evidence, main and other worktrees, B1C/5021, promotion/5033, databases/3306/3399 and C:/Users/michi/.radar-ha1-local-qa. Capture OFF/shared boards ON remain Deployer-attributed state. No application/test/schema/config edit, commit, push, deployment, capture activation or automatic dispatch authorized here.

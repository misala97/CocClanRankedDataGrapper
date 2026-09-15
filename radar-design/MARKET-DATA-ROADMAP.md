# CURRENT — Selected-price local implementation and review ACCEPTED / CLOSED (2026-09-15)

Binding acceptance: radar-design/MD-SELECTED-PRICE-FINAL-ACCEPTANCE.md. FINAL-CHECK clean; F1-F4/R2-1/N1 closed. No further local correction/review/test assignment. Fresh-context-after-/clear review accepted with its stated provenance; REVIEW-2 retains same-session qualification. Next: OWNER RELEASE-SCOPE DECISION, no Deployer dispatched or activation authorized.

Accepted candidate C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts; codex/radar-selected-price-charts; base/HEAD daadf3868caedcb5db858378e919cba68b735f8a, uncommitted. Fingerprint 0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0: all 50 files freshly verified, zero mismatches. FINAL-CHECK reviewer 13 tests + 5/5 scenarios; wider checks remain worker-attributed. Mastermind Git/artifact/hash verification only, no test reruns. Dirty ownership unchanged except this acceptance and current notices; all code/build/evidence preserved. Ignore-file warning qualifies enumeration.

Both flags default OFF; selected-price changes NOT DEPLOYED. Live Yahoo/usage conditions, Linux/gunicorn/venv/cwd, MariaDB runtime and actual topology remain release carries. HA1 remains COMPLETE / DEPLOYED / CLOSED. No workers/commits/production/RC action. Headline MD-05 promotion deferred, MD-03/08 separate. Latest notice supersedes historical next steps.

---
> Status cross-reference, 2026-09-13: ROADMAP.md governs current priority. VC1 and PERF3 are deployed; B1 remains separate/undeployed. The MD/HA dependencies below remain planned, not completed. Capture remains off. Original B is the primary visual direction.

# Market data within the Radar redesign

Planning integration, 2026-09-10. Source: [independent OpenTerminal comparison review](../docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md). All MD items remain proposed/open; incorporating research is not evidence that a provider was selected or an adapter implemented.

## Sequencing decision

Historical analysis stays ahead of portfolio and full news/professional radar. Market-data improvements are its enabling workstream, with independently useful improvements to current Research and discovery. Do not make every provider experiment a prerequisite for a useful retrospective explorer. Do not change the authorized VC1 deployment to include these items. Capture stays off until separately commissioned; planning these tasks does not enable it.

Three distinct needs guide the architecture: broad discovery observations, detailed prices/history for an opened instrument, and explicitly selected inputs for scoring. Their cadence, resolution, storage and source need not be identical. Providers, fixed chart slots, quote selection and scoring internals may change when justified. Preserve truthful identity/time/basis contracts, not incumbent implementations.

## Integrated work packages

| Timing | IDs | Deliverable and dependency | Visible product change |
| --- | --- | --- | --- |
| After VC1 deployment; before choosing history adapters | MD-01 | Current mapped-universe coverage, event age, history depth, sessions, failures, operating burden and usage conditions; EUR 0 is a disclosed working assumption, not newly confirmed budget | Coverage/quality requirements for Research, Analysis and discovery mockups |
| Alongside HA0/HA1 design | MD-02 + MD-07 + MD-10 | Prototype selected-instrument 1D line and investigate actual multi-session intraday availability; bounded cache, request coalescing, timeouts/backoff and source health from first adapter | Better 1D/1W Research charts; independent timestamped price/chatter series on one axis; clear gaps and degraded daily fallback |
| After selected-source comparison | MD-05 | Compare Nasdaq/Finnhub on observed age, coverage and failures; choose priority/fallback and whether a poller remains useful | Headline quote, bid/ask where supplied, provider/event-time/session provenance follows selected observation |
| Alongside HA0 measurement, without blocking initial HA1 | MD-03 + MD-08 + MD-10 | Bounded TradingView shadow comparison against mapped US/German universe, ETFs/small caps; German source/venue strategy including relevant additional venues; validate timestamp semantics, delay, truncation and operating cost | Broader usable discovery coverage and explicit listing/venue choices; no prototype promise of live or tradable data |
| After MD-03/08 evidence; before broad-source scoring promotion | MD-04 | Source-aware event-time observation selection, reference prices, retention, duplicate/frozen-tape handling and eligibility; compare ranking usefulness/false signals | Improved board coverage and scoring when validated; policy/version changes visible in Analysis |
| After first usable HA1; small context increment before full news radar | MD-06 | Earnings dates first, then linked ticker news (Google News candidate); validate dates/timezones/entity matching and independent slow cache | Catalyst markers and explanation links on Research/Explore; does not count as social chatter or automatically suppress a score |
| After initial historical delivery, portfolio/news continue as planned | Existing workstreams | Manual trades/positions/alerts and full news/professional pipeline retain their own plans; MD-06 is not a professional-sentiment engine | Personal performance, news feed and later synthesis |
| After basic earnings/news context, as research depth expands | MD-09 | Form 4 parser/transaction/amendment validation, then FINRA context with precise coverage and meaning | Richer evidence panels; short-sale volume is not short interest or a bearish-position measure |
| Progressive visual evolution alongside the above | MD-11 | Better chart interactions may accompany HA1; candles/volume require genuine OHLCV; choose library/indicators for a demonstrated task | Move toward original A/B concepts' richness, rather than freeze at the interactive prototype; retain price/chatter comparison |

IDs preserve the source review's identities, not a serial schedule. MD-10 ships with each adapter; it is never postponed to a final admin polish phase. MD-02 is display-only initially; MD-03 shadow is separate from live quote selection/scoring. Both are validation stages, not permanent prohibitions on becoming primary sources. MD-04 may replace existing selection/storage/scoring logic after evidence supports it.

## Historical-analysis integration

- HA0 can capture limited board replay using the existing archive independently of the provider redesign, once explicitly enabled. Keep capture start dates and limitations visible.
- HA0 enhanced manifests must identify source, instrument/listing/MIC/currency, provider event time, received/available time, delay/session, reference basis, adjustment policy and selection/scoring-policy version. Do not mutate already saved observations after switching providers.
- HA1 can ship an honest daily-resolution retrospective explorer before broad scans or multi-session intraday are ready. Daily anchors are a degraded fallback, not the target end state for intraday research.
- Never manufacture candles/OHLCV from sampled line points or reconstruct minute history from periodic scans. Price resolution need not equal the chatter bucket interval; gaps remain gaps.
- HA2 intraday horizons require actual retained observations at those horizons. Validate tolerances/event-time availability and preserve failed/unavailable outcomes. Compare cohorts within compatible source/venue/policy regimes; identify regime changes rather than silently pool incompatible observations.
- News retrieved later can explain an old move retrospectively, but cannot appear in 'known then' replay without its actual availability timestamp. MD-06 must preserve this distinction from its first implementation.

## Provider decisions remain open

Nasdaq, TradingView, Massive, Finnhub, DBAG and other evidenced candidates compete on measured usefulness. The review favors Massive's broad US daily-history architecture; it does not grant permanent ownership. Nasdaq samples establish timestamped line data, not candle coverage or a universal freshness guarantee. TradingView scans need per-row timing/delay and mapped coverage checks before promotion. Never insert a freshly fetched delayed scan into the existing fetch-time-ranked quote path as if it were fresher market data.

German venue selection may change, including a replacement/hybrid collector, but price movements must not splice incompatible venues invisibly. International discoverability is distinct from Scalable availability, which remains verified/unknown separately. Provider conditions and traffic budgets must be established before implementation; no rate-limit probing by excessive requests or access-control workarounds.

## Execution and continuity

Next planning packet after VC1 release: MD-01 measurement brief plus coordinated HA0/HA1 data contracts and Explore/Replay mockups. Use the review, the original Claude comparison and captured probe results together; recheck dated observations when a provider decision is actually made. No new provider recommendation or probe is claimed by this integration.

For each chosen slice, Codex writes the binding spec/plan and Claude implements in the designated isolated workspace with an execution ledger and independent review. Carry this document, updated ROADMAP and history-plan amendments into the next worktree at kickoff; do not overwrite the active deployment handoff. Source review remains unchanged as an independent account.

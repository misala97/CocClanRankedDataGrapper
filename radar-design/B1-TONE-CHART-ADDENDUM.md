# B1 follow-up: sentiment-coloured chatter histogram

Owner approved 2026-09-13. Planning only; not implemented. This adds scope to the next B1 chart/integration packet, not a redispatch of completed B1.1/B1.2. Codex plans; implementer works in the actual app on the integrated PERF3 base.

## Accepted behaviour

Replace the single-colour chatter area with stacked bars per displayed time interval. Total height is total chatter volume in that interval. Green is bullish; red is bearish; grey is neutral or unjudged. Tooltip/tap details must distinguish neutral from unjudged, even if visually combined into one grey segment. Mixed sentiment stays mixed rather than colouring the entire spike by a majority verdict.

Hover on desktop and tap on mobile show interval/timezone, total volume, bullish/bearish/neutral/unjudged counts and percentages with their denominator stated. Percentages for the stack use total interval volume; any directional-only percentage must be separately labelled. Legend/text supplies meaning beyond colour. Bullish discussion does not imply a buy recommendation or a favourable future price move.

## Data and implementation requirements

- Establish the existing chart's counting unit, time bins, tone provenance and retained coverage before implementation. Keep category counts mutually exclusive and exhaustive within that same total; do not mix posts, mentions and unique voices.
- Use sentiment for each interval. Never paint historical bars with a ticker's present overall percentage. Missing classification is unjudged/unavailable, not neutral and not zero activity.
- If retained data cannot truthfully split old intervals, keep their totals grey with an explicit tone-unavailable explanation. Do not invent missing sentiment. Preserve real zero versus missing coverage and existing time/price alignment.
- Existing provenance rules still apply: heuristic wording is not silently relabelled as judged sentiment. Identify limitations in the detail view.
- Inspect the shared PriceChart surface before changing geometry; preserve /radar/ behaviour or explicitly scope the adaptation. Keep PERF3 shared-result, pending/stale and performance contracts intact; avoid per-request scans or per-bar queries over raw history. Propose any required aggregate/API/schema work in the bounded implementation packet.
- Acceptance: real per-bin totals reconcile with segments; mixed/all-unjudged/missing/zero intervals remain distinguishable; desktop hover and mobile tap work; legend and accessible text are readable. Verification scope belongs to implementation, not this documentation update.

## Roadmap carry

B1 owns the first actual-app chart delivery. HA1 reuses it for price/chatter retrospective analysis, with availability and classification timestamps distinguished from known-then replay. Later Combined Radar reuses the visual semantics without silently combining social and professional sample populations. No capture enablement or deployment is authorized by this amendment.
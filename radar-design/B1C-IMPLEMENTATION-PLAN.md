# Current status — 2026-09-13, B1C live and owner confirmed

B1C deployed at 200c51cc402e053575bf9e0008db597ea27b36a5 with explicit owner authorization. The owner subsequently confirmed the chatter bars work; the apparent missing-bars issue was resolved by scrolling. Investigation cancelled, no product fix required. Busy-ticker tone latency is accepted for this iteration, not a passed performance target. Capture remains OFF; /radar/hub/ remains alongside /radar/; no root promotion.

Deployment evidence and exact operational state: root HANDOFF.md. Prior pending-release, unimplemented-tone and latency-blocker statements below are historical and superseded by this notice. Preserve historical evidence; do not redispatch completed work.

---
# B1C — integrated B workspace and sentiment histogram Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans. Follow the owner's one implementation worker at a time, followed by independent read-only review. Checkboxes track the new work only; completed B1/PERF work is not redispatched.

**Goal:** Deliver the actual dark Human Chatter workspace on top of deployed PERF3, with a truthful, usable bullish/bearish chatter histogram, ready for the owner's local review.

**Architecture:** Port the completed B1 application delta onto the current deployed application. Add an opt-in selected-ticker tone-series projection using retained event membership and recorded judgments; keep totals and the existing shared-board pipeline intact. Extend the shared chart with a hub-only histogram mode and reuse it in standalone hub Research.

**Tech stack:** Existing Flask/SQLAlchemy/MySQL-MariaDB, React/TypeScript, TanStack Query, SVG/Vite. No new chart library, daemon or cache service.

**Spec:** B1-TONE-CHART-ADDENDUM.md; B1-IMPLEMENTATION-PLAN.md; B1 return ruling in the source worktree's CODEX-DECISIONS.md. This packet governs new work and supersedes old deployment/next-action statements, not accepted data semantics.

## Authority, workspaces and boundaries

Planning source: C:/Users/michi/Desktop/CodingStuff/radar-design.
Verified source B1: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1, codex/radar-b1, 6c63959c3553607fd96e45ed43136256e9390d96, clean tracked tree when inspected for this plan. B1.1/B1.2 and their reviews are complete. The TE1 documentation correction is complete at 6c63959. Do not rebuild them.
Verified deployed/main PERF3: ad531ef6d697eac7c67179a40d7fca56812095fd; application migration b7e3f9c1a2d4. Source worktree radar-perf3 remains at that commit with post-deployment documentation and protected untracked owner files. Fetch before branching; if origin/main has moved, inspect and record its actual delta rather than reset it backwards.

Create NEW branch codex/radar-b1c in C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1c from the current integrated main. Preserve all other worktrees. In the new worktree keep this plan, the tone addendum, B1 original brief/ruling/reference images, B1C-LEDGER.md, and current HANDOFF.md together. Copy source ledgers as clearly labelled historical evidence; never replace current handoff with an old B1 handoff.

Authorized: local implementation, local integration commits, disposable-database work through the existing explicit registration/target guards, local preview and verification. Not authorized: push/main publication, deployment, VPS changes, production migration/restart/configuration, capture enablement, root promotion, held index, B2/portfolio/news/history implementation, provider/scoring changes. No new prototype. No production credentials or account session fabrication.

No production access is required for this packet. Read archived release facts; do not re-run a release rehearsal or all PERF phases. Existing 120/120/600 freshness defaults, async pending/stale behaviour, queue cap, namespace fencing, account isolation and deployment runner remain intact.

## Product decisions made here

1. Keep B1's accepted 1600px three-column breakpoint, dark navy/orange identity, candidate/selected-company/evidence arrangement, Research/Table toggle and URL/back behaviour. This is an integration, not a new visual direction.
2. Histogram total height is the EXISTING count of eligible high/promoted mentions, not people, price volume or directional-only samples. Green bullish, red bearish, grey non-directional/unjudged/unavailable. Tooltip and accessible details distinguish those grey meanings. Caption: "Chatter tone — recorded judgments". It may differ from wording-inclusive headline tone; do not silently change headline/table tone rules.
3. Model attitude positive/negative and legacy bullish/bearish supply directional colour. Explicit mixed/none or legacy neutral supply non-directional grey (label "Neutral / mixed"). Legacy unclear or no directional judgment is "Unjudged / unresolved". Raw lexicon scores alone do not create a judged green/red bar. Already stored model verdicts remain usable even if old rows lack a modern judged timestamp. Missing retained evidence is "Tone unavailable", not known unjudged.
4. This packet intentionally uses the reliable RECENT event horizon. config.MENTION_EVENT_RETENTION_HOURS is currently 48; post retention is 30 days, but posts omit low-only events and do not by themselves establish the bucket's promoted population. Do not promise 30-day exact counts from post retention. The 1D chatter span can be fully coloured when coverage supports it; longer spans retain their complete total bars, with older/unsupported portions grey. Boundary bins are partial. Explain this limitation beside the chart. Do not reinterpret a daily-price fallback as a reason to discard the independent intraday chatter bins.
5. Durable historical tone summaries and retrospective backfill are an HA data follow-up, not silently built in B1C. Record the horizon and required future summary contract in HISTORY-ANALYSIS-LEDGER.md. The chart is current recorded interpretation of past chatter, NOT known-then replay; later judgments can change a retained bin. No capture enablement.
6. A green spike means bullish discussion, not a predicted price rise or buy instruction.

## Code findings behind the scope

- detail.Chart, daily_counts and intraday_counts in features/radar/detail.py expose scalar counts, not sentiment partitions. 1D is 96 x15-minute slots; 1W is168 x60-minute slots; longer spans are calendar-day bins. Respect the ACTUAL returned start and step, including fallback paths, not a second independently calculated timeline.
- RadarBucketSource retains source counts; sentiment_mean is not enough to derive bullish/bearish counts.
- RadarMentionEvent has unique (source, external_id, ticker), indexed (ticker,bucket_start), pre-promotion confidence, materialized promoted and counts_as_human_chatter. Use high OR promoted, with chatter eligibility not explicitly false. Do NOT use only event.confidence, re-run promotion over a selected slice, or substitute post counts.
- journal.write_promotions records complete-bucket decisions. bucket rebuild and judgment updates can temporarily diverge: reconcile event population with source-bucket totals before colouring.
- detail_panel tone helpers currently allow lexical fallback and collapse undecided tone. Do not change those helpers globally just to implement this chart's explicit judged-only contract.
- detail_panel's B1 move alignment still exposes phrasing._read_price's unjustified "talk and tape agree" and false closed-session "no price move" statements. The B1 ruling already requires descriptive correction; it remains open.
- PriceChart is shared with /radar/. B1 fixed label/gutter geometry; preserve it. Hub queries.ts has PERF3 state handling absent from old B1: do not copy old files wholesale over PERF3.

## Task 1 — integrated actual-app candidate and gallery carry

Files: port B1 changes under features/radar/detail_panel.py, static/radar/src/detail/PriceChart.tsx, static/radar/src/hub/ and tests/test_radar_detail.py. Use `git diff 472f345..6c63959 -- personal_apps` as the source delta, not the whole source worktree. Overlaps include Hub.tsx and Chatter.tsx. New docs: B1C-LEDGER.md and HANDOFF.md.

- [ ] Read source B1 ledger and current ruling, PERF3 deployment record/current handoff, then verify source branch/HEAD/status and actual diff. Record completed tasks and remaining findings accurately.
- [ ] Create isolated B1C worktree. Carry this packet and original B references into it.
- [ ] Apply/port the reviewed B1 application delta locally, resolving overlapping logic in favour of preserving BOTH PERF3 and B1 behaviour. Retain current pending/busy/stale/retry/timestamp states, demand admission, query keys, shared board response, selection, sort and watch semantics. Do not import old deployment docs as current.
- [ ] Preserve the owner-requested gallery in source control: static/radar/design-reference/index.html plus combined.png/chatter.png/overview.png copied from planning mobile-gallery/index.html, probes/b-research-desk.png and b-direction/*-concept.png. Add a genuine accessible "Future Radar design" link in the B shell. Remove duplication of the temporary template banner if carried in. These are public fictional mockups already uploaded at the owner's request. Live template changes currently are uncommitted and WILL otherwise disappear at a later reset; no remote edits now.
- [ ] Establish a NEW registered disposable database with schema-preserving dump/restore provenance and current migration head. Do not seed B1, TE1, PERF1/PERF3 scale or any existing database. Do not weaken scale_env/registry guards or use CREATE TABLE LIKE as a constraint-equivalent clone. Only create minimal owned fixtures after the effective host/database tuple is checked.
- [ ] Run focused existing B1 selection/navigation/table tests and PERF3 hub-state tests once on the integration. Fix actual integration regressions. Commit the integrated candidate and evidence.

## Task 2 — close the already-ruled shared price narrative

Files: features/radar/phrasing.py; affected tests/test_radar_phrasing.py and tests/test_radar_detail.py. No scoring changes.

- [ ] Add failing focused cases for positive/negative/sub-1%/absent move, closed/stale, fallback and non-trade basis. Example expected clause for price_move=-0.023: "The price moved -2.3% over the measured window." It must not contain "agree" or causation.
- [ ] Preserve measured moves independently of score eligibility. Closed state adds "Market closed; this is a historical window move." rather than denying a measured move. Existing stale/quality warnings remain, without asserting a fresh/tradable quote. Missing move must not become zero.
- [ ] Verify the old board detail remains coherent and scoring's score_eligible gate is unchanged. Commit this bounded fix. TE1's historical correction is already complete; do not redispatch it.

## Task 3 — opt-in recent tone-series API, bounded by source evidence

Create features/radar/chatter_tone.py and tests/test_radar_chatter_tone.py. Modify features/radar/routes/api.py (ticker_detail/serialize_detail only), static/radar/src/types.ts, api.ts and hub/queries.ts. Avoid changing the board producer or board payload version: this is a selected-ticker detail extension.

Interface (new module):
```python
def chart_tone(ticker, sources, chart, *, now):
    """Return version1 tone envelope aligned exactly with chart.chatter."""
```
`chart_tone` uses the existing request-scoped db.session. It performs no writes. It returns:
```ts
type ChatterToneSlot = null | {
  bullish: number; bearish: number; neutral: number;
  unjudged: number; unavailable: number;
  status: 'complete' | 'partial' | 'unavailable';
}
type ChatterTone = {
  version: 1; basis: 'recorded-judgments'; calculated_at: string;
  retained_from: string; slots: ChatterToneSlot[];
}
// DetailChart gains optional chatter_tone?: ChatterTone
```
Null slot means total chatter was unobserved (existing null), not zero. For every observed slot, all five counts are nonnegative integers and sum EXACTLY to chart.chatter[i]. Status complete means unavailable=0, partial means some classified/matched population and some unavailable, unavailable means all positive total volume lacks reliable partition evidence. Observed zero returns zero counts with status complete; percentages display an em dash, never NaN or 0/0.

- [ ] Pin pure classification and reconciliation cases first. A 10-mention bin with 4 bullish,2 bearish,1 explicit non-directional,3 unresolved becomes (4,2,1,3,0); tooltip percentages40/20/10/30/0 of total10. A model-negative verdict with lexical-positive input stays bearish. Lexical-positive without a recorded verdict stays unjudged. Old/pruned evidence for a known total10 becomes (0,0,0,0,10). Null total stays null.
- [ ] Read recent eligible events by indexed ticker/bucket_start bounds intersecting the chart and full-bucket retention boundary. Join RadarPost on BOTH source and external_id, and RadarMention on post_id AND ticker. Outer joins must preserve events without retained mention evidence, assigning those unavailable, not neutral. Use materialized promotion and event eligibility, not a different panel population. Explicit model/eligibility contradictions with the materialized rollup invalidate that source-bin until reconciled.
- [ ] Aggregate scalar CASE/SUM counts in SQL by source and UTC15-minute bucket, not ORM post objects or JSON extraction. Reconcile each source-bin's eligible event count against its actual RadarBucketSource.mention_count before combining sources; source A's shortage must never cancel source B's excess. On mismatch mark THAT source-bin's whole total unavailable; do not clamp directional counts or infer missing members. Zero-total bins need no imagined members. Snapshot skew/unknown record mapping results in unavailable, never a misleading ratio or endpoint exception.
- [ ] Sum source-bin partitions into the existing chart's returned slots, preserving gaps and its exact `_slot_index`/daily alignment and source-history expansion. Include pre-retention contributions only as unavailable totals. A partly retained hour/day can show its verified sub-bins plus unavailable remainder. Use source-bucket totals from the same read snapshot as the chart, or conservative reconciliation if that cannot be established; never mix two completed reads to claim identity without checking.
- [ ] Add `tone=1` to ticker detail opt-in. Absence retains its old cost/shape; malformed nonempty tone values return400. Compute after Detail is built and attach in serialize_detail via optional argument, so observations/direct board serializers do not pay for it. Old clients can ignore the additive field.
- [ ] Extend fetchDetail's existing fourth signal argument with an optional fifth `includeTone=false`; set tone=1 only when true. Hub useDetail requests it and includes tone-version1 in its query key so old cached detail cannot satisfy the new contract. Both hub Research and Chatter use the same query; original DetailPane remains defaultfalse. Abort, selected-company placeholder guard and retries remain intact.
- [ ] Test inclusion/exclusion of high/promoted/low/false-eligibility events, duplicate arrivals, same external ID across sources, pending judgments, orphan evidence, source mismatch, pruned bins, partial hour/day, observed zero/interior gap, old-client omission and invalid opt-in. A newer judgment must appear on refetch without changing totals. Do not mistake this for known-then replay.
- [ ] No migration or new background process in this packet. If the indexed bounded read cannot meet the scoped performance acceptance below, report the measured blocker and a bounded aggregate proposal; do not silently add a new performance subsystem or call the chart complete using fabricated data.

## Task 4 — histogram and accessible interval inspection

Files: static/radar/src/detail/PriceChart.tsx; new detail/ChatterHistogram.tsx and its focused tests; hub/ResearchContent.tsx; relevant hub.css. Retain shared helpers rather than forking the whole price chart.

- [ ] Add `chatterMode?: 'area' | 'sentiment-bars'` defaultarea to PriceChart. Hub ResearchContent selects sentiment-bars. Old /radar/ retains its current area and API cost. Preserve B1's readable12px axis/gutter fixes.
- [ ] Draw each slot as one stacked bar with green bullish/red bearish/grey remainder. All segment y positions share one total-count scale with the normal baseline. Green/red are sentiment ONLY; price line colour never controls these bars. Leave clear gaps between readable bars; long spans may pool adjacent slots only by summing all five counts AND total with explicit pooled interval labels. No selective sampling or averaged percentages.
- [ ] Provide hover on desktop, tap on mobile, keyboard interval navigation and an accessible detail panel. Use a focusable chart/interval cursor with arrow keys, Home/End and Escape rather than1095 tab stops. Announce UTC interval start/end, total, counts, total-denominator percentages, basis and unavailable reason. Mobile taps must not prevent normal horizontal chart scrolling. No colour-only legend; unavailable is distinguishable with text and optionally a grey pattern.
- [ ] Show visible concise coverage copy: "Tone colours use retained recent judgments. Older or unmatched chatter stays grey." Add the actual retained horizon; do not claim all past spikes have reconstructed tone. Retain price-basis/delay/fallback captions and source-window context.
- [ ] Tests pin bar heights, mixed tone, unknown versus neutral, zero/gaps, tooltip percentages, tap/keyboard dismissal, legend, stale API data and absent tone field fallback. Verify unchanged legacy area mode. Commit the chart implementation with screenshots of the actual local application.

## Task 5 — bounded proof, independent review, owner return

No repeated full research/review cycles. One implementation worker finishes the packet; one independent read-only reviewer checks the final delta, rendered app and evidence. Resolve findings; re-review only changed failure-prone paths, not all closed PERF history.

- [ ] Run affected backend tests under the registered disposable target: test_radar_chatter_tone.py, test_radar_detail.py, test_radar_phrasing.py and any actual modified API contract tests. Before each destructive suite assert the effective registered target; never just print an env database name and assume it wins over URL query options.
- [ ] Run focused histogram/PriceChart, B1 workspace, navigation and PERF3 hub query-state tests during work. At completion run `npm test` and `npm run build` once in personal_apps. Explain any baseline failure with actual evidence; do not launch an unrelated suite-fixing project.
- [ ] Scoped local performance evidence only: use owned recent fixtures for a quiet ticker and a busy ticker (20,000 eligible events in48h, including mixed judgments), both1D/1W and a long span with old totals. Record engine, fixture sizes, query counts, returned bytes,20 warm requests per relevant case and paired opt-in versus opt-out. Target added tone work median<=100ms/p95<=200ms and incremental Python heap<=8MiB; DB round trips bounded independently of bins/sources (no N+1), output at most the existing1095 slots. Long-span tone query still reads only the retained48h. If base detail is already slow, report base and delta separately; do not credit PERF3 board timings to detail. No production load tests.
- [ ] Confirm board-read/PERF3 modules were not changed, and the integrated hub still uses one shared board response plus one selected detail request; no per-row chart requests. Run relevant existing PERF3 frontend regressions; do not rerun its saturation/MariaDB/deployment matrix when those paths are unchanged. For new grouped SQL, validate correctness on registered disposable MariaDB10.11 if available; if unavailable, state that target-engine gate plainly instead of presenting MySQL timing as VPS proof.
- [ ] Use python-playwright headlessly on the actual app at1440,1920 and390px; add320px overflow/interaction check. Capture selected-company view, Table mode, grey old history, mixed-tone spike, mobile tap details and old /radar/. View the PNGs. Add named response-fixture cases only for otherwise unavailable states; label them. No separate interactive prototype.
- [ ] Leave actual app running locally with a NEW local-only preview account in the owned database. Report URL/port, how to start it and screenshots. No production login session.
- [ ] Independent reviewer checks integration, count identity/denominators, sources and retention, no account leakage, chart accessibility, narrative, gallery carry and scope. Fix findings before returning.
- [ ] Update B1C-LEDGER.md and top HANDOFF with exact branch/SHA/status, completed/open tasks, tests and measurements, environmental failures, protected files and future deploy carries. Write CODEX-RETURN-B1C.md: what owner can review, what is truly supported (including48h tone horizon), measured blockers, migration status and no-deployment statement. Copy the compact return pointer to planning checkout if needed for discoverability; do not overwrite unrelated planning changes.

## Acceptance and stop condition

The owner can review B's actual workspace with real measured per-interval colour, a preserved Table mode and fast shared-board behaviour. Older unsupported tone is visibly unavailable, not silently neutral. The shared narrative no longer invents price/talk agreement. Gallery is durable in the candidate. Tests/review and the local performance delta are documented honestly. Stop with the completed local candidate and owner-review return; B2, durable historical tone storage and deployment are separate next decisions.

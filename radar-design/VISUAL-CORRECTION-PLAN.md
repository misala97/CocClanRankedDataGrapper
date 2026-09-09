# Radar hub visual correction — VC1

**Binding design and implementation brief, 2026-09-09.** Codex plans; Claude implements. Owner approved restoring fidelity to the interactive prototype. This is a correction to the shipped hub, not a new visual direction.

## Goal and authority

Make Human Chatter feel like the approved light/green research dashboard with compact, balanced rows, useful source summaries, a tone percentage and bar, and obvious entry into research. Preserve the A overview + B research identity across the existing hub. A working deployment and passing tests do not constitute visual acceptance.

This document supersedes the old hub prohibition on tone percentages and green/red tone bars, including comments and tests encoding that prohibition. It does not supersede valid unknown-data, authorization, filter, pricing or baseline contracts. Do not apply the unrelated redesigning-pages-from-data skill. Do not reopen F1–F3, H1–H4, R1–R3, P1 or P2.

References in the planning checkout `C:/Users/michi/Desktop/CodingStuff/radar-design/`:

- `index.html`, `preview.js`, `preview.css`: approved interactive prototype; `#chatter` is the primary visual reference, not the old board.
- `references/chatter-live-owner.png`: owner's rejected deployed table.
- `references/chatter-prototype-owner.png`: owner's approved reference comparison.
- `CODEX-DECISIONS.md`, Seventh return: release accepted operationally, visual corrections required; TE1 prerequisite.

Keep the prototype unchanged as the reference. Its fictional numbers, fixed bearish segment, claims of independence and mobile-hidden tone are not production data contracts. Preserve its composition, not those shortcuts.

## Verified diagnosis

Read against candidate `d3bc795`, deployed merge `ba1c381` (same application tree). These are source findings plus the owner's screenshots, not a fresh authenticated VPS inspection.

| Gap | Evidence | Required correction |
| --- | --- | --- |
| Sources take most of the table width | `hub/Chatter.tsx` maps each concrete source through `sourceLabel()` then joins every label; many subreddit IDs all become Reddit | Compact platform summary, concrete IDs only in expandable detail |
| The source count can include zero-mention feeds | `leaderboard._aggregate()` admits scored bucket rows without a positive mention condition; `_assemble()` builds `contributing` from all `parts` | Add an explicitly measured positive-activity feed field; do not merely deduplicate misleading labels |
| Tone became a vertical report | `Chatter.Tone()` emits three count lines; `.rh-table strong` forces block display; the screenshot shows tall stacked lines | Percentage + horizontal bar + one compact sample line; exact counts in accessible detail |
| Layout follows the longest feed text | Automatic table sizing, company minimum width, no deliberate column allocation | Explicit chatter column proportions and bounded secondary text |
| Prototype bar styling survived unused | `.rh-tonebar` already exists; conflicting comments forbid its use | One intentional tone component and remove obsolete prohibitions/dead rules |
| The data caveat is real, the visual downgrade was not necessary | `board._tones()` uses attitude, legacy verdict, then lexicon sign; residual neutral combines non-directional and unread | Use the explicitly defined directional denominator below; no claim of universal model coverage |

## Visual contract

Retain pine navigation, near-white canvas, white surfaces, Inter, sage positive tone, muted red negative tone and restrained amber qualifications. Do not inherit styling from another app. Scope styles under `.rh`; chatter-only column rules must not affect Activity/Admin tables.

### Page composition

1. Existing shell: clear active Chatter navigation, search, market/session context.
2. Page heading: **Human chatter**; subtitle **Find unusual discussion, then inspect the evidence.** Keep market/window and last update in a quiet context line. No repeated paragraphs of disclaimers above the data.
3. Compact filter toolbar: market, window and company segment primary; existing additional controls under an accessible **More filters** disclosure with active selection summary. Retain every current option and the R1 last-feed guard. Company search stays immediately above/within the table header area, labelled **Filter companies**. Do not confuse its client-side narrowing with server filters.
4. One table panel: heading **Ranked companies**, subtitle **Unusual attention, with voices and sources in view.**, and right-aligned `N companies` / `N of M shown`. Same spacing and hierarchy as the approved panel.
5. Columns: Company / Attention / Voices / Sources / Tone / Price · today / open affordance. Keep the server's ordering; no new ranking model.
6. Footer: actual visible count, actual market price context and a short attention-baseline explanation. Put fuller definitions in one accessible **How to read this** disclosure. Do not repeat warnings in every cell.

At 1440×1000 with the sidebar visible, target approximately 26 / 13 / 11 / 15 / 19 / 12 / 4 percent of table content width. Adjust a few percentage points to avoid collisions; do not compress Attention to make room for source prose. Use a chatter-specific colgroup/table layout or equivalent stable grid preserving semantic table associations. At 1920, do not stretch secondary prose across empty space; keep readable column bounds.

Typography at 100% zoom: primary row values 13–14px, secondary text 12px, headings 12px, panel heading 18px. Do not shrink labels below 11px to pass a width check. Base row approximately 76–88px; a row with one qualification line may reach 108px. At 1440, five ordinary rows should occupy no more than 440px excluding panel headings/footer. These are default-state targets, not fixed heights that clip enlarged text.

Company: 34px mark, ticker, company name clamped to one desktop line, full name available through a keyboard/touch-accessible details control or the research destination. Preserve full accessible name. Qualifications remain visible, wrapping when needed; never silently hide a partial window, stale print or warming baseline. The row may grow for multiple warnings.

Attention: ratio and one-line `its normal rate`; null ratio remains an em dash and the existing honest baseline explanation. Voices: current count and current mentions count; retain the backend's meaning, never relabel it as investors or globally unique people. Price: currency-aware price and signed move, tabular numerals; unavailable stays unavailable. Open: restrained green chevron, useful accessible name, opens the same research destination as the company control. Avoid making every cell a separate tab stop or nesting interactive controls in a clickable row.

Hover adds a subtle wash; keyboard focus is visible. Source/tone details are reachable by keyboard and touch, dismiss with Escape, and do not trigger research navigation. No hover-only essential definitions.

### Tone: percentage and bar are required

Use the existing counts, with **B = bullish**, **S = bearish**, **U = neutral residual**, **D = B + S**, **T = D + U**. Do not use `row.mentions` as T: the snapshot already shows it can differ from the tone population. Preserve `_tones()` eligibility/window and attitude → legacy → lexicon precedence.

When D > 0:

- Primary label: **`P% bullish`**, P = 100 × B / D.
- Directly beneath: a 96–112px wide, 5–6px high horizontal bar, sage B/D and muted red S/D. Segment widths use unrounded ratios; zero contributes no segment. The bar and primary percentage have the SAME denominator.
- One visible secondary line: **`D directional / T total`**. This is descriptive sample size, not judging coverage. On the panel's Tone definition say **“Share of directional signals that are bullish. Signals may come from model judgments or keyword rules.”**
- Accessible detail gives exact B bullish, S bearish and U unread or non-directional; explains that U includes balanced/mixed/unclear and unclassified signals and is excluded from the directional percentage. It is not known neutral sentiment. “Total” means this tone sample of eligible mention rows in the selected window, not all posts/people read.
- Display to one decimal, trim trailing `.0`. If rounding would turn a nonzero/non-full share into 0%/100%, use `<0.1%`/`>99.9%`. True zeros and full shares may show 0%/100% with sample size always visible, including 1 directional / 1 total. Do not invent a confidence threshold or label small samples reliable.

When D = 0 and T > 0: **No directional signal**, neutral empty track, secondary **`T unread or non-directional`**. No 0% or 50% placeholder. When T = 0: **No tone sample**, empty track and no invented counts. Invalid/missing/nonfinite/negative counts: **Tone unavailable**; do not coerce to zero.

The original prototype used an invented fixed bearish slice. This plan intentionally uses two meaningful directional segments and a neutral empty track, preserving the bar's visual role without inventing a third partition. Never call the percentage chance of rising, buy confidence, percentage of investors, or percentage model-judged. A future true neutral/unjudged split is useful but is NOT required to deliver this correction.

Example: B=10, S=16, U=45 → **38.5% bullish**, bar 10:16, **26 directional / 71 total**. This works even when the nearby bucket mentions count is 68. B=1,S=199,U=0 → **0.5% bullish**, not 0%. B=0,S=0,U=45 → no directional signal.

### Sources: compact and truthful

Add `activity_sources: string[]` to the serialized board row, defined as unique concrete sources whose summed mentions are >0 among that ticker's existing selected-window scored bucket aggregates. This is bucket-observed activity, not independence or verification of the claims. Reuse aggregated `parts`; no per-ticker queries, raw post scans or migration.

Carry it on the leaderboard row with a backward-compatible default if existing constructors require one, populate in `_assemble`, serialize in `routes/api._row`, and add optional `activity_sources?: string[]` to the frontend Row during compatibility. Missing field means **Source activity unavailable**, not fallback to the old inaccurate count. Empty array means **No active feeds in this sample**. Check pinned/watch serialization too.

Group known concrete IDs by the established `source_root` convention, then label once: **3 platforms**, secondary **Reddit · Bluesky · 4chan**. One platform: **1 platform**, secondary **Reddit**. If many platforms, show at most two names plus `+N`; a details control exposes every platform and concrete feed identifier, e.g. r/options, not 34 identical Reddit labels. Count concrete feeds in that detail. Unknown roots get a human-readable safe label, not silently mapped to Reddit. Multiple subreddits are one platform and are not claimed independent.

Do not change legacy `sources`, `venues`, ranking, eligibility or breadth filtering as a side effect. Their zero-feed behavior needs a separately recorded follow-up because changing them can change which stocks appear. This correction's explicit additive field fixes its display without disguising a ranking change. Explain in the filter definition that existing venue-floor filtering follows legacy scoring breadth; do not claim the new display count controls that filter. Record this distinction in evidence. If a clean additive field cannot preserve the shared contract, return the specific issue rather than silently broadening ranking work.

## Responsive and cross-page scope

At 1024/768, collapse the sidebar when content becomes too narrow rather than shrinking every column. Use the same labelled mobile navigation pattern; test 700/701 boundary. Where seven columns no longer fit, switch Chatter to compact stacked rows: company and price in the top line; attention and voices below; sources and tone below that; qualifications visible. Tone must remain visible on mobile (improves on the prototype's hiding shortcut). At 390×844 and 320px width, no document horizontal scroll, no overlap, no source dump; controls have at least 44px touch targets. At 200% zoom allow natural row growth and vertical flow.

This delivery corrects Chatter fully and checks shared styling across Overview, Research, Watching, Activity and Administration. Do not claim all six are prototype-identical. Make only changes on those pages required by altered shared tokens/components, navigation or obvious clipping/regressions. Research retains its actual chart resolution labels and actual evidence; Overview retains truthful current-board content. Do not add fictional stories, recommendation cards, prices, portfolio/news features or unfinished navigation destinations just because the prototype has them. Record any remaining page-specific fidelity work as named follow-ups with screenshots, not as already accepted.

## Implementation sequence for Claude

Use the existing candidate worktree unless evidence shows another worker owns it. Read its handoff and ledgers completely; verify branch, HEAD, diff and deployed-vs-local state. Preserve the Codex-owned uncommitted decisions/planning files. Read AGENTS.md. One implementation worker at a time, followed by an independent read-only review as the repository requires. No repeated full release review.

### TE1 — repair the test environment (existing task, not a new release gate)

- [ ] Complete Sixth/Seventh return TE1 before editing backend feature code: NEW disposable schema-preserving restore, expected base 29 personal-app FKs and their delete rules, unique constraints, engine/settings/stamp, correct migrations, constraints enabled in actual test sessions.
- [ ] Run actual watch service/API/account-integrity paths plus affected recorder/migration tests. Record counts, environment and any remaining failures; never call the old constraint-free clone equivalent. Verify database name before every destructive command. Keep backup/private rows out of Git and reports.
- [ ] Update evidence and proceed directly to VC1 when its criteria pass; no intermediate Codex round trip solely to confirm completion.

### VC1a — source contract and presentation helpers

Files: `personal_apps/features/radar/leaderboard.py`, `personal_apps/features/radar/routes/api.py`, `personal_apps/static/radar/src/types.ts`; create `personal_apps/static/radar/src/hub/chatterPresentation.ts` and `chatterPresentation.test.ts`. Relevant backend tests: `tests/test_radar_leaderboard.py`, `tests/test_radar_api.py`.

- [ ] Add tests using one ticker with a zero-mention scored feed and a positive feed. Assert only positive feed enters activity_sources while legacy sources, order, eligibility, marks and scores remain unchanged. Test multiple subreddit roots, no active feed, selected-window restriction and pinned rows. Existing aggregate query count must not grow with row count.
- [ ] Add the additive field through the existing aggregate/row serializer; no migration or JSON format rewrite. Do not change `_tones()`.
- [ ] Implement pure `tonePresentation(tone)` returning display label, bull/bear fractions or null, sample text and full explanation. Implement `sourcePresentation(activitySources)` returning platform count/summary and concrete details. Tests exercise the exact examples above plus malformed counts, rare shares, missing vs empty sources, duplicate subreddit labels and unknown roots.

### VC1b — actual Chatter UI

Files: `hub/Chatter.tsx`, `hub/Filters.tsx`, `hub/hub.css`, corresponding tests; new `hub/Tone.tsx` if extracting keeps Chatter readable. Reuse current navigation callbacks and query state.

- [ ] Render the defined hierarchy, toolbar, compact row, source detail and required tone component. Add column sizing and responsive row structure scoped to Chatter.
- [ ] Replace tests asserting absence of percentage/bar with tests asserting correct denominator, accessible counts, empty/unavailable states and rendering. Preserve the R1 guard/request tests, URL/back/forward behavior, stale response protections, baseline nulls and currency/price handling.
- [ ] Remove obsolete comments/tests that forbid the now-required treatment. An old comment is not a reason to downgrade the approved design.
- [ ] Build and inspect the production bundle locally with real API data where available and labelled fixtures for controlled comparisons. Do not modify the approved prototype to resemble the weaker implementation.

### VC1c — visual acceptance and independent review

- [ ] Capture BEFORE and AFTER Chatter using the same dataset and viewport, plus the unchanged prototype at the same viewport. Use python-playwright for batched screenshots, then actually open/read the PNGs. Do not replace visual inspection with DOM assertions.
- [ ] Required widths: 1440×1000, 1920×1080, 1024×768, 768×1024, 390×844 and 320px. Check 200% zoom/reflow and 700/701 transition. Verify no console/page errors or document overflow.
- [ ] Primary fixture: at least five rows, one long legal company name, 36 scored feeds with several zero contributions, bullish/negative/mixed samples, null baseline/price, two warnings and a missing activity_sources compatibility row. Also show 45-row density, all-empty, search-no-match, loading/error and stale refresh states. Never label fixture pixels live data.
- [ ] Measure row heights and column widths at 1440; include an annotated before/after comparison. If measurements pass but the result still looks materially worse than the prototype, keep iterating.
- [ ] Keyboard/touch check: open company, expand source/tone detail, close it, modify filters, last-feed refusal, open/close navigation, Back restores selection. Check text contrast and non-color interpretation.
- [ ] Run focused hub Vitest suites, root/shared tests if their code changed, and `npm run build` from personal_apps. Run affected backend suites on TE1 environment. Record exact commands/results; do not claim unrelated baseline failures fixed or rerun the whole backend solely for a CSS change.
- [ ] Independent reviewer checks semantic correctness AND actual screenshots against this contract. Resolve concrete findings in this worktree; do not create another speculative release-preparation loop.
- [ ] Deliver runnable local preview URL, screenshot paths, commits, changed files, exact test results and remaining limitations in `VISUAL-CORRECTION-LEDGER.md` and current `HANDOFF.md`. Ask owner to review the rendered result before proposing deployment. No merge/push/deploy/capture/root promotion in this implementation dispatch.

## Completion standard

TE1 verified; meaningful active-source summary; visible tone percentage/bar/sample; prototype-like hierarchy and density; real-data edge cases readable; existing interactions preserved; screenshots inspected and independently reviewed. The owner retains final visual acceptance. No claim of visual completion based only on passing tests.

Historical analysis remains the next new feature after this correction, ahead of portfolio/news. Documentation carry and retired watchdog OT1 remain separate supporting work and must not consume this delivery. OT1 has no live-change authorization here.

## Owner clarification — staged design ambition (2026-09-09)

The interactive prototype is the near-term fidelity target for VC1 and the next
iterations, NOT the desired final product or a permanent ceiling. The longer-term
ambition remains the visual richness, sophistication and research depth of the
original image concepts: A's welcoming overview and B's focused research workflow,
unified in the selected light/green identity. C remains rejected.

As history, portfolio and news capabilities mature, design their pages and revisit
the hub's composition with richer charts, evidence interactions, hierarchy and
polish, using fresh mockups before implementation. Aim for the original concepts'
level of craft and complexity where it serves research; their fictional content
is not a promise of available data. The current prototype's simplified layout and
components do not bind future design. Do not freeze the product at VC1 fidelity.

This does not expand VC1: deliver the current interactive-reference correction
first, then evolve deliberately alongside the roadmap. No new implementation or
deployment is authorized by this clarification alone.

## VC1-close addition — sortable Chatter, owner approved 2026-09-10

The owner explicitly approved sorting after trying the preview. Add this to the
current closure alongside the Eighth-return fixes; do not defer it to a future
redesign or reopen completed TE1/VC1 work. Claude implements; Codex plans.

### User interaction and scope

- Default is Radar order: the exact order of the current board.rows response.
- Desktop headers are real buttons: Company (ticker A–Z initially), Attention,
  Voices, Sources, Tone, Price, and Today (numeric columns descending initially).
  Price and Today are two distinct controls within the existing price/move area;
  do not make one ambiguous combined sort. Repeated click toggles direction.
- Visible active arrow plus accessible sort state/name. Apply aria-sort to the
  active header, with a name distinguishing price from daily move when both
  controls share a header. Keyboard Enter/Space behaves like click.
- A compact 'Radar order' reset restores response order. On stacked/mobile rows,
  show a labelled Sort by selector with the same keys and direction control;
  do not leave sorting accessible only through hidden headers.
- Show 'Sorts these N candidates' near the control/summary. This reorders the
  loaded candidate set, not the whole market or the backend eligibility/ranking.
  Do not fetch, alter server sort parameters, or widen the candidate set.
- Filter companies and then sort; preserve the selected sort while typing and
  while refreshing/changing server filters. Reset uses the newest response order.
  Keep sort state in the hub's Chatter view state so Research -> Back restores
  it. No new backend persistence or requirement for cross-session storage.

### Comparator contract

Use a pure stable helper on a copied array; never mutate board.rows or cached
watch rows. Equal keys retain current response order. Missing/invalid values
stay LAST in both directions, including when direction reverses.

Company sorts by ticker using locale-aware numeric comparison, not truncated
company text. Attention uses row.ratio, never recomputes a guarded ratio.
Voices uses authors. Sources uses the number of unique platforms from validated
activity_sources through the existing presentation helper: missing is unknown,
empty is measured zero; never fall back to legacy sources. Tone uses raw
bullish/(bullish+bearish) under the same validation as the display; zero directional
sample is unknown, never 0% bullish. Do not compare formatted percentages or the
minimum-width bar geometry. Price uses the displayed usable quote price; absent
currency or unavailable quote is unknown. For multiple known currencies, group
by currency code (label this in the sort explanation), then sort price within
currency, rather than pretending USD and EUR are converted. Today uses the raw
usable price_move fraction, with null unavailable and zero a valid value.

### Files and acceptance

Modify hub/Chatter.tsx, hub/Hub.tsx only as needed to retain Chatter sort state,
hub/hub.css and their focused tests. Add hub/chatterSort.ts and
hub/chatterSort.test.ts for comparator logic (or a comparably focused existing
helper). Preserve selection/query contracts and row navigation/disclosures.

Tests must demonstrate numeric ordering (2 vs 10), both directions, ties, nulls
last in both directions, all-no-tone rows, two distinct raw tone fractions with
the same rounded label, active platforms vs concrete feeds, mixed currencies,
input array unchanged, filter+sort composition, refresh retains selection,
Research/Back restores selection, and Radar-order reset. Check clicking a sort
header produces no board request. Verify desktop keyboard/accessible state and
mobile selector parity. Capture the sorted fixture at 1440 and 390, inspect it,
and confirm arrows/controls do not break accepted density/column widths.

Return this with the same VC1-close preview and independent review. No merge,
push, deployment, capture enablement or root promotion authorized.

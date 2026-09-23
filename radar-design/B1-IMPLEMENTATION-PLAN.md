> Accepted addition, 2026-09-13: [B1-TONE-CHART-ADDENDUM.md](B1-TONE-CHART-ADDENDUM.md) adds per-interval bullish/bearish/neutral-or-unjudged stacked chatter bars to upcoming B1 chart work, carried into HA1 and Combined Radar. Planned, not built. Preserve completed B1 and deployed PERF3 work.

# B1 — dark research shell and Human Chatter in the actual hub

Binding implementation brief, 2026-09-10. Owner approved B's appearance and explicitly rejected another standalone interactive prototype: the working application is the review surface. Codex plans; Claude implements. This dispatch authorizes local implementation and verification, not merging/pushing/deploying.

## Outcome

Replace the hub's light/green sidebar identity with B's navy/orange/cyan identity, and turn Human Chatter into an integrated candidate/evidence workspace. Preserve its useful sorting, tone percentages, source summaries and real data. This is a substantial visual/layout change, not merely a dark theme applied to the existing table.

Overview receives compatible shared styling in B1, but its new composition is B2. Do not implement the generated Overview's research queue, totals or recent-history features here. Price-provider changes and historical analysis continue as separate MD/HA workstreams. No standalone demo application or replacement prototype.

## Entry and source of truth

Last inspected implementation worktree: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate, branch codex/radar-release-candidate, HEAD 472f345. CODEX-DECISIONS.md and HANDOFF.md had Codex-owned uncommitted edits. Latest recorded deployment is 4221196 in RELEASE-RECORD-VC1.md; older handoff text still says 1f8016c. Verify Git and latest records, do not infer current production from those stale headings.

Read AGENTS.md, the full current HANDOFF and relevant ledgers before edits. Use an isolated implementation branch/worktree from the current integrated application state if another task owns the candidate. Default new branch codex/radar-b1, worktree C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1. Verify full-tree differences against the intended base, including root build files; do not drop the closed-session move and judged-label fixes. Carry only this package and required reference/decision files, not stale planning copies of execution ledgers. Record chosen base/branch/workspace in B1-LEDGER.md. Preserve unrelated work, secrets and the foundations worktree.

References:

- Original ../radar-design/probes/b-research-desk.png: primary aesthetic anchor.
- b-direction/chatter-concept.png: approved current direction, not literal data/wording authority.
- b-direction/overview-concept.png: future B2 direction.
- b-direction/REVIEW.md: known generated-image errors and capabilities not yet implemented.

These are in C:/Users/michi/Desktop/CodingStuff/radar-design and copied beside this brief. Do not use redesigning-pages-from-data. B's appearance supersedes the previous light/green choice. The images guide composition, visual depth and hierarchy; this plan governs factual content and behavior.

## B1 visual system

Use Inter and tabular numeric figures. Starting tokens: canvas #091722, raised surface #112331, selected surface #1a3042, border #2b4355, primary text #edf3fa, secondary text #b1c1d3, orange action/selection #ff9e48, cyan price #28c8db, positive #45dda0, negative #ff6b7c. Verify rendered contrast: normal text 4.5:1, focus/UI indicators 3:1; adjust tokens if needed rather than reduce readability. No low-contrast gray placeholder text. Keep chart grid subdued but visible. Green/red remain data semantics, not a green application identity.

Use subtle layered surfaces and thin borders, radius 8–10px, no glowing/glass effects or decorative finance graphics. Data labels 12px minimum, primary values 13–14px; company heading 26–30px, price 32–36px. Maintain 44px mobile tap targets and clear focus rings. Orange indicates active selection/actions; cyan identifies price series, orange chatter series. Tone keeps its existing positive/negative semantics and a labeled denominator. Color never carries meaning alone.

### Horizontal shell

Remove the permanent left navigation rail and its workspace margin. Top bar approximately 64px: Radar mark/name left, global company search centered/right, market/session context. Second band approximately 48px: Overview, Human chatter, Watching, Activity; Administration right-aligned and shown only for admins. Research gets a contextual tab/breadcrumb when open. Do not copy inactive News/Combined/Portfolio routes or duplicate Discover/Research/Portfolio groups from the image just to fill space. No unimplemented theme/language/account controls.

Active navigation has orange text/underline; other destinations remain readable. At narrow widths, collapse to the existing accessible menu behavior adapted to the new shell, preserve skip link, Escape/focus return and no hidden tab stops. Search remains usable at all widths. No green sidebar survives inside the hub. Styling remains scoped to .rh; original /radar/ and other apps are unaffected.

### Human Chatter: integrated research mode

At >=1280px viewport: three columns, approximately 300–340px candidate rail, flexible center at least 500px, 280–320px evidence rail. 12–16px gutters and 16–24px outer padding. At 1440 this should fit without clipping; if it cannot, move the right rail below the center before shrinking chart labels. At 1920 allow a wider center, not arbitrarily stretched text.

Left candidate rail:

- Heading Human chatter, selected market/window, compact Filter companies input.
- Sort by selector and direction button using ALL current keys, plus Radar order reset. Full table mode retains clickable headers as below.
- Existing market/window/segment/source/breadth controls behind a labelled Filters disclosure with applied summary. Preserve last-feed guard and scope warning. Do not quietly drop filters for visual space.
- Each candidate row: ticker/name, price/change, attention ratio, voices and compact tone bar/percentage. Active platforms accessible with the row's evidence details or selection panel; show critical qualification badges. Selected row has an orange border/wash, not an orange confidence score.
- Consistent roughly 100–124px row at desktop, natural growth for warnings and larger text. Use short metric labels; do not cram seven table columns into 320px. Scrollable candidate region with keyboard reachability and visible selected row.

Center selected company:

- Identity from the detail response, currency/session/delay and headline price from its actual quote. Preserve all closed-session movement and judged-label fixes.
- Reuse existing PriceChart, chart-basis note, supported spans and truthful caption logic. Cyan price, orange chatter with independent labels/units. Do not invent minute history, OHLCV, prev-close lines, bid/ask, volume/market cap fields or catalyst annotations absent from the API.
- Show the currently supported chart at its actual retained resolution. Gaps stay gaps; daily fallback remains explicitly labeled. A dark chart that is still a daily fallback is acceptable; do not fake B's dense series.
- Below chart, tabs Evidence and Source posts. Evidence uses existing clauses/breakdown; Source posts uses the current real Posts component and preserves judged provenance. No generated investment thesis or news story.

Right evidence rail:

- Heading Evidence at a glance, selected-window context, attention ratio, voices, active platforms, tone percentage/bar/sample drawn from the same board row as the candidate. Show unknown when absent; never replace this with incompatible detail counts while claiming it is the same window/population.
- Accessible disclosures preserve exact counts, concrete feeds, tone fallback/denominator explanation and tiny-segment note. Do not add a made-up neutral partition.
- What needs checking: existing qualification marks/available concentration facts, not invented warning sentences for every ticker. No claim that distinct platforms prove independent corroboration.
- Watch/unwatch uses the existing authenticated mutation, pending/error behavior and account isolation. One coherent control, not independent local watch state. Broker availability remains unverified where unknown.
- Reflow this rail below the center when needed. Do not hide it on mobile.

### Preserve the comparison table

A visible Table / Research view toggle near the Chatter heading lets the owner compare all loaded candidates in the accepted sortable table or use B's integrated workspace. Default Research view on a fresh Chatter visit; preserve the user's mode in hub view state during the session. Table mode uses the SAME filters, ordering, samples, source logic and cached response; apply the new dark identity without duplicating the data model.

Opening a company from either mode selects it for Research view. Returning to Table retains filter and sorting. This preserves the recently approved table's comparison value while giving B its actual workflow. Do not build a second standalone app for it.

## Navigation and request contract

Extend existing hash parsing with #chatter/<encoded ticker> for a selected company. Keep #chatter, #research/<ticker> and all existing query/selection links valid. Put the selected company in the route, not a competing unsynchronized state store. Keep sort and text filter in Hub session view state so company navigation/Back does not reset them; do not use backend ranking parameters for client sorting.

- Fresh #chatter in Research mode selects the first visible response-order candidate using replaceState, not a new history entry. Empty candidate list gets an honest selection/empty state without a detail request.
- Explicit company selection pushes history; Back/Forward restores it. Keep selected ticker fixed during auto-refresh/sort, never silently switch because rank changed.
- If selection is outside the current filtered candidates, retain its detail with a clear 'Outside this candidate list' note and action to select the first visible candidate. Unavailable selected company has its own retry/unavailable panel; candidate list stays usable.
- Deep link to unknown ticker gets normal unavailable handling, no substitution of a different company.
- One existing useBoard query and one selected useDetail query, not a query per candidate or separate queries for center/right. Reuse query cache keys; stale previous ticker content must not render under a new heading. Right rail board data and detail data retain their own explicit time context.
- Do not rewrite global selection or provider logic. Escape closes disclosures/menu; it does not unexpectedly reset the selected stock.

At <=760px: candidate list and selected company are sequential screens within the same app/route, with a visible Back to candidates control. Selection displays center then evidence rail vertically. No compressed desktop three-column grid, no hidden tone, no off-screen price. At 761–1279px: candidate rail plus center when their minimum widths fit, otherwise sequential; evidence below chart. Match breakpoints to available width, not a fixed imitation of desktop screenshot dimensions.

## Implementation tasks

### B1.1 — shared shell and token migration

Primary files: personal_apps/static/radar/src/hub/Hub.tsx, hub.css, Hub.test.tsx, Search.tsx/styles if needed. Inspect templates/radar/hub.html and entry only if outer-page color/font loading requires it; do not make shared-template edits incidentally.

1. Establish new scoped tokens and horizontal shell; remove obsolete sidebar margins/layout rules.
2. Verify Overview, Watching, Activity, Admin, standalone Research, loading/error states and dialogs remain readable under new tokens. Re-map reused chart variables explicitly; no black-on-dark axes or leftover white panels.
3. Preserve auth/admin gate, global search, URL selection, skip link, focus and mobile menu behavior. Run focused existing shell/navigation/search tests plus build.

### B1.2 — shared selected-company content and Chatter workspace

Primary files: hub/Chatter.tsx, Research.tsx, Hub.tsx, navigation.ts, hub.css. Create hub/ChatterWorkspace.tsx, hub/CandidateList.tsx and hub/ResearchContent.tsx if extracting those responsibilities reduces duplication. Reuse chatterPresentation.ts and chatterSort.ts as the SINGLE metric/sorting rules.

1. Extract presentational research content from current Research without changing its data semantics. Keep standalone Research working. Selected detail request has one owner; no render of two full Research components to obtain two panels.
2. Add selected Chatter route and state transitions above; test parsing/encoding/malformed IDs and old bookmarks.
3. Add candidate rail and full table toggle; lift current text-filter state only as needed for persistent navigation. Retain all sortable keys and null-last/tie/currency contracts.
4. Compose center/evidence rail from actual fields and existing components. Reuse watch mutation. Scope errors/loading to the affected region; do not blank the candidate list on detail failure.
5. Implement tablet/mobile behavior and accessible selection indicators (aria-current on the selected candidate link or equivalent semantic state; not aria-selected on arbitrary divs). Avoid nested interactive row controls.

### B1.3 — actual-app review and verification

Use the working Flask/React hub locally against the isolated test environment. Verify database name before backend tests; TE1 environment already exists and its local-schema limitation remains. No new database migration is expected. If necessary API changes emerge, identify them explicitly and test on TE1; do not fabricate fields to finish the layout.

Required behavior tests: list/table toggle keeps order/filter; all existing sort keys; company selection and Back/Forward; stable selection on refresh; selection filtered out; no prior ticker data flash; no per-row requests; malformed/deep link; empty board; selected-detail failure/retry; watch pending/error; admin hidden/refused; keyboard/menu/disclosure focus. Existing closed-session move and judged-label tests stay passing. Test the behavior, not every CSS token.

Build from personal_apps (`npm run build`), run affected hub/navigation/research/sort suites and shared frontend checks as warranted. Only run backend suites if backend code changes or local integration needs them; don't repeat completed migration rehearsals for a layout change.

Use python-playwright to capture the ACTUAL local app at 1920×1080, 1440×1000, 1024×768, 768×1024 and 390×844, plus 320px/reflow checks. Label fixture response overrides for edge cases; never present them as live data. Open the PNGs and inspect them against original B and the new Chatter concept. Browser fixtures are verification aids, not the requested deliverable.

Show populated selected-company view and Table view; zero-directional tone, long names, multiple warnings, absent detail/price, daily fallback, stale data and sparse sources. Inspect other hub pages at desktop/mobile for theme regressions. Capture contrast/focus and chart label legibility, no document overflow or invisible menus. Do not claim mobile fidelity based on one desktop image.

One implementation worker followed by independent read-only review of code, tests AND rendered images. Resolve findings before returning. No chain of speculative review gates; return when this finite scope works and matches B's character.

## Return and completion

Deliver the runnable local ACTUAL APP URL, screenshots, exact branch/HEAD/files, test results and limitations in B1-LEDGER.md and current HANDOFF.md. Document any missing field as a named MD/HA follow-up. No mockup-only substitute, no 'dark theme applied' completion with unchanged table-only composition.

Owner reviews the working result before deployment. No merge/push/deploy, capture enablement, root promotion, provider swap, OT1 changes or scoring change in this dispatch. Do not add a light/dark theme switch unless separately requested. Overview B2 follows after this shell/workspace foundation; its saved queue/activity aggregation needs its own data design.

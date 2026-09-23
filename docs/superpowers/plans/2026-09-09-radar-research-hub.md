# Radar Research Hub Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Claude implements one task at a time, followed by an independent read-only review. Codex owns the plan and product decisions. Do not dispatch tasks marked complete in the ledger.

**Goal:** Deliver the approved light/green direction as a usable opt-in hub backed by current Radar data.

**Architecture:** A separate React entry and Jinja shell at /radar/hub/ reuse existing typed APIs, authentication and chart semantics. New hub components own layout and navigation. Release 0 provides Activity and Admin endpoints; H1–H3 can proceed without those endpoints, H4 requires F3.

**Tech Stack:** Existing React19, TypeScript, React Query5, Vite7, Flask, Vitest, Testing Library, Python Playwright.

**Spec:** `radar-design/IMPLEMENTATION-SPEC.md`; visual reference `radar-design/index.html`, `preview.css`, `DESIGN.md` and `screenshots/`.

## Global Constraints

- Radar has its own light/green identity. Use DESIGN.md and the approved prototype as visual references; do not inherit another app's design.
- Desktop is primary; usable at 390px, 768px, and 1440px viewport widths.
- Production screens use real API data. Fictional prototype fixtures remain test/design assets only.
- Watch state is account-specific; preserve server authentication and CSRF protection.
- No production deployment or live database migration is included in this handoff.
- All binding-spec constraints apply. No dependency additions or copy of preview.js into production.

## Entry gate

- [ ] Read HANDOFF.md, HUB-LEDGER.md, the spec and this plan completely; verify Git/worktree/HEAD/diff. Reuse the foundations implementation worktree after F3 if doing these sequentially. If independently starting H1–H3, create a separate `codex/radar-research-hub` worktree and record it; integrate the reviewed F3 commit before H4. Never overwrite shared dirty files.
- [ ] Ensure the entire radar-design package is present and tracked in the implementation worktree. Inspect prototype desktop overview/research and phone research images. This plan narrows production scope; do not reproduce future simulated capabilities as real features.
- [ ] Run `npm test` and `npm run build` in personal_apps; record before-change results. Backend tests require the verified disposable database described in the foundations plan.

## File map and interfaces

Create under `personal_apps/static/radar/src/hub/`: `Hub.tsx` (composition), `navigation.ts` (URL contract), `queries.ts` (shared server state), `hub.css` (scoped visual system), `Overview.tsx`, `Chatter.tsx`, `Research.tsx`, `Watching.tsx`, `Activity.tsx`, `Admin.tsx`, `Search.tsx`, `PageState.tsx`, and colocated tests. Keep components focused; do not add a generic dashboard framework.

Create `personal_apps/static/radar/src/entries/hub.tsx` and `personal_apps/templates/radar/hub.html`. Modify `vite.radar.config.ts` to add the entry, and `features/radar/routes/views.py` to add the authenticated shell. Existing board entry/template stay available.

Reuse `api.ts` exports fetchBoard, fetchDetail, fetchSearch, setWatch, queryFor; `types.ts` BoardPayload, Row, Detail, Selection, PanelSpan; `fixtures.ts` for test payload factories. Inspect `detail/PriceChart.tsx` and its tests before adapting its renderer: retain tested units, null handling, sessions, converted basis and keyboard/text alternatives. Reuse low-level logic where sound; old layout/CSS is not authoritative.

## Task H1: shell, navigation and shared reads

**Interfaces:** `Hub({initial, isAdmin}: {initial: BoardPayload; isAdmin: boolean})`; `HubRoute = {page:'overview'|'chatter'|'watching'|'activity'|'admin'} | {page:'research'; ticker:string} | {page:'missing'}`; `readRoute(hash: string): HubRoute`; `boardKey(selection: Selection): readonly unknown[]`; `detailKey(ticker: string, selection: Selection, span: PanelSpan): readonly unknown[]`.

- [ ] Write route tests and cache-key tests before implementation:

```ts
it('keeps listing context in cache identity', () => {
  const us = {...selection, market: 'us' as const}
  expect(boardKey(us)).not.toEqual(boardKey({...us, market: 'de'}))
  expect(detailKey('AAA', us, '1D')).not.toEqual(detailKey('AAA', us, '1M'))
})
it('opens direct research links', () => {
  expect(readRoute('#research/AAA')).toEqual({page: 'research', ticker: 'AAA'})
  expect(readRoute('#nonsense')).toEqual({page: 'missing'})
})
```

Define selection from a fixture payload's echoed fields, with minVenues from min_venues, window from window_hours; do not invent unsupported filter values. Test malformed percent encoding as missing instead of crashing.
- [ ] Run `npx vitest run -c vite.radar.config.ts static/radar/src/hub/navigation.test.ts static/radar/src/hub/queries.test.ts` and inspect intended failures.
- [ ] Implement cache keys that include the complete query, not only market:

```ts
export const boardKey = (s: Selection) => ['radar-hub', 'board', queryFor(s)] as const
export const detailKey = (t: string, s: Selection, span: PanelSpan) =>
  ['radar-hub', 'detail', t, s.market, s.sources.join(','), s.window, span] as const
```

Use one QueryClient per page session; initial board data only seeds the matching selection. React Query owns cancellation signals, refetchInterval 60000, refetchIntervalInBackground false. Authentication errors clear caches and show sign-in recovery. URL updates preserve hash and filter query; popstate and hashchange resynchronize state.
- [ ] Add /hub/ view using the same BadQuery fallback/build_payload convention as board_page; embed `{board: payload, is_admin: is_admin()}` with Jinja tojson in a distinct hub-data element. New entry validates required payload fields before mount, displays a useful failure view if invalid, and wraps Hub with a QueryClientProvider and error boundary. Add hub Vite input beside board; resolve bundle using the existing template asset helper convention.
- [ ] Build shell navigation, responsive menu, scoped tokens and page-state component. Only valid implemented destinations appear. During this task render a labelled loading content area, then implement real pages in H2–H4 before delivery. Do not claim shell-only work is a finished hub.
- [ ] Test authenticated shell, escaped JSON, direct links, back/forward, keyboard menu, expired session and old board route availability. Run focused tests and `npm run build`; commit H1 and obtain review.

## Task H2: chatter, research and search

**Interfaces:** `Chatter({board, selection, onOpen}: {board: BoardPayload; selection: Selection; onOpen:(ticker:string)=>void})`; `Research({ticker, selection, span}: {ticker:string; selection:Selection; span:PanelSpan})`; Search selects ticker through onOpen. Query ownership stays in queries.ts, not duplicated fetching in child rows.

- [ ] Add fixture-based behavior tests: a row opens research; 404 research offers return/search; source/window selection reaches detail request; quick US→DE navigation cannot display late US data; null quote displays unavailable; 0 move displays 0%; single-source and partial marks remain visible. Render server clauses as text/semantic spans, never parsing numbers out of prose.

```tsx
it('preserves unavailable quotes', () => {
  const r = row({price: null, quote: {...quote(), price: null, quality: 'unavailable'}})
  render(<Chatter board={payloadWithRows([r])} selection={selection} onOpen={vi.fn()} />)
  expect(screen.getByText(/unavailable/i)).toBeVisible()
  expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
})
```

Define local fixtures using the verified exports below. Use these definitions in the H1 and H3 test modules too.

```ts
import {payload, row, quote} from '../fixtures'
import type {Row, Selection} from '../types'
const payloadWithRows = (rows: Row[]) => payload({rows})
const initial = payload()
const selection: Selection = {market:initial.market, sources:initial.sources,
  segments:initial.segments, minVenues:initial.min_venues,
  window:initial.window_hours, sort:initial.sort, dir:initial.dir}
```
- [ ] Run new tests and confirm intended failures. Implement the ranked list and filters using existing server query values. Search calls fetchSearch after 250ms, cancels old requests and supports keyboard selection/dismissal; do not restrict it to current board rows.
- [ ] Implement Research with fetchDetail(ticker, selection, span). Keep identity and price/chart provenance visible. Adapt tested chart and breakdown behavior to new layout; source posts render text with safe HTTP(S) external links and rel=noopener noreferrer. The right summary describes available clauses/source concentration, not a generated trade thesis.
- [ ] Add tests for raw HTML in source bodies, absent chart data, daily vs intraday basis, source filters, search request race, and opening a ticker absent from current ranked rows. Run focused tests plus existing api, PriceChart, Posts and Identity suites to catch helper regressions.
- [ ] Capture research at 1440/768/390 with fixture responses. Inspect PNGs using image viewing; fix typography, chart legibility and overflow. Commit H2 and obtain independent data/interaction review.

## Task H3: Watching and Overview

**Interfaces:** `useWatchMutation()` calls existing setWatch(ticker,on), adopts returned full watching list, then invalidates board queries. `Watching({board}: {board:BoardPayload})` uses watch_rows rather than filtering ranked rows. Overview also uses that same board result.

- [ ] Test watch→research→overview consistency, failed mutation preserving old state, rapid repeat click disabled, and watched-but-ineligible row retained:

```tsx
it('keeps quiet watched companies visible', () => {
  const p = payloadWithRows([])
  p.watching = ['AAA']
  p.watch_rows = [row({ticker:'AAA', eligible:false})]
  render(<Watching board={p} />)
  expect(screen.getByText('AAA')).toBeVisible()
})
```

- [ ] Confirm failures, implement mutation hook and Watching. Distinguish undefined watch_rows (older/incomplete payload) from an empty caller list. No localStorage account data. Preserve CSRF token behavior in setWatch and display a clear error on rejected writes.
- [ ] Build Overview from real rows: first3 in returned rank order, first5 watch_rows, market session and generated_at. Label results 'Current chatter' and show the selected window; do not aggregate authors or mentions across tickers as a unique system total. Link all candidates and the complete lists.
- [ ] Test empty board with active watching, empty watching with active board, delayed quotes, failed refresh retaining timestamp, session expiry clearing personal cached state. Verify a second account cannot see the first account's marks with existing backend ownership patterns.
- [ ] Run hub tests and existing watch/API tests. Capture Overview and Watching at 1440/390, inspect PNGs against prototype composition. Commit H3 and review.

## Task H4: Activity/Admin and integrated review

**Dependency:** F3 reviewed and integrated. If absent, finish H1–H3 and record H4 blocked on F3; never substitute prototype totals.

**Files:** Add Activity/Admin components and tests; extend api.ts and types.ts with explicit ActivityPayload/OpsPayload matching F3. Because old getJson treats403 as session, add a distinct forbidden error reason for the admin API and test it without changing the semantics of expired sessions.

**Interfaces:** `fetchActivity(days:1|7|30, signal?:AbortSignal): Promise<ActivityPayload>`; `fetchOps(signal?:AbortSignal): Promise<OpsPayload>`. Copy exact nullable fields from F3, including recording_started_at and capture.latest_observed_at. Do not use `any` to accept drifting contracts.

- [ ] Add tests: missing day counters render a gap, a recorded zero renders zero, partial completeness is labelled, invalid ops access displays forbidden, nonadmin has no admin nav, and page retry does not trigger provider/control endpoints.
- [ ] Run failing tests; implement simple daily activity columns with equivalent table/text, recording-start explanation, and separate incomplete/error run counts. Admin groups ingestion/capture, market data, judgment pipeline and model API spend, using actual returned field names. Do not equate zero API spend with zero total infrastructure cost.
- [ ] Run all frontend tests with `npm test`, build with `npm run build`, and focused F1–F3/backend route regression tests on the disposable DB. Record exact output summaries and any reproducible environment block.
- [ ] Use Python Playwright to batch six page screenshots at1440x1000 and390x844 plus research768x1024. Check keyboard navigation, focus, document overflow, empty/partial/error states and watch mutation recovery. Fixture screenshots must be labelled in report; also do one authenticated local real-API smoke without writing a trade or contacting a broker.
- [ ] Save review evidence under `radar-design/reports/hub/` with test commands/results, screenshots, observed API limitations and comparison to approved prototype. Do not claim visual acceptance solely from passing dimensions.
- [ ] Commit H4, obtain independent review, resolve findings, update HUB-LEDGER.md and HANDOFF.md. Present opt-in /radar/hub/ for owner review. Keep root /radar/ unchanged until a separate promotion decision.

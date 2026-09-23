# Selected-instrument price charts — implementation plan

2026-09-15. For one owner-selected Implementer using executing-plans inline. User's role workflow overrides automatic subagents, commits and per-task reviews in generic skills. No subagents; one focused independent Reviewer/QA after the whole candidate returns. This is a prepared assignment, not a dispatched worker.

**Goal:** detailed selected US 1D/1W prices on the same truthful timeline as retained chatter/tone, without delaying the stock's other information.

**Architecture:** additive authenticated chart endpoint, bounded local chart reader, lazy background coordinator and killable public-data fetch child; independent typed hub chart component. Existing Yahoo parsing/transport and recorded-tone semantics reused where compatible. Two default-off flags separate new chart UI from outbound source activation.

**Stack:** existing Python/Flask/SQLAlchemy/MariaDB, requests, standard-library multiprocessing spawn, React/TypeScript/TanStack Query/SVG/Vitest. No new dependency/service/schema migration.

**Spec:** MD-SELECTED-PRICE-SPEC.md in the same directory. Ruling: MD-SELECTED-PRICE-EVIDENCE-1-RULING.md. Ledger: MD-SELECTED-PRICE-LEDGER.md. Read all three fully.

## Workspace and authorized setup

Source (read-only): C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore; branch codex/radar-ha1-us-daily-explore; HEAD daadf3868caedcb5db858378e919cba68b735f8a. Current dirty documents and untracked research are intentional.

Candidate: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts; branch codex/radar-selected-price-charts; base daadf3868caedcb5db858378e919cba68b735f8a. Worker creates this worktree only when owner dispatches the prompt. Verify Git/status/log before setup and after. Use per-command safe.directory. If candidate already exists, inspect ownership/HEAD and resume only matching assignment work; never reset, delete or overwrite a conflicting candidate.

Example setup from source (after fresh checks):

```powershell
git -c safe.directory=C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore worktree add -b codex/radar-selected-price-charts C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts daadf3868caedcb5db858378e919cba68b735f8a
```

Copy the exact current uncommitted planning versions below from source to the identical relative candidate paths, without committing. Record SHA-256 source/copy comparisons in candidate radar-design/artifacts/md-selected-price-implementation/carry-manifest.json. Do not assume uncommitted files follow a worktree. Snapshot hashes before adding candidate current notices.

Carry manifest:

- HANDOFF.md
- radar-design/HANDOFF.md
- radar-design/WORKFLOW.md
- radar-design/MASTERMIND-STATE.md
- radar-design/ASSIGNMENTS.md
- radar-design/ROADMAP.md
- radar-design/MARKET-DATA-ROADMAP.md
- radar-design/MD-01C-RULING.md
- radar-design/HA1-US-DAILY-EXPLORE-RELEASE-CLOSURE.md
- radar-design/MD-SELECTED-PRICE-BRIEF.md
- radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md
- radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RULING.md
- radar-design/MD-SELECTED-PRICE-SPEC.md
- radar-design/MD-SELECTED-PRICE-PLAN.md
- radar-design/MD-SELECTED-PRICE-IMPLEMENT-1-PROMPT.md
- radar-design/MD-SELECTED-PRICE-LEDGER.md
- docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md
- radar-design/artifacts/md-selected-price/README.md
- radar-design/artifacts/md-selected-price/probe_selected_price.py
- radar-design/artifacts/md-selected-price/probe_supplement.py
- radar-design/artifacts/md-selected-price/probe_summary.json
- radar-design/artifacts/md-selected-price/probe_supplement.json
- radar-design/artifacts/md-selected-price/probe_raw_points.json

Historical HA1 ledger/spec/QA files already exist in the base commit and require no extra carry or review. Original main-workspace comparison/probe remain reachable by absolute path in the brief, read-only. The new candidate gets a current HANDOFF identifying its actual path/branch, inherited planner dirt versus worker edits, first open step and protections. Never rewrite source continuity from the Implementer.

## Owned application files and interfaces

Paths below relative to candidate; inspect current symbols before editing. These are allowed ownership areas, not a requirement to touch every file. A small adjacent test/type file may be added if needed; record why without expanding product scope.

| Files | Responsibility / interface |
| --- | --- |
| New personal_apps/features/radar/price_chart_contract.py | Pure window/normalization/chatter reducers; Window and PriceChartResponse dictionary schema matches SPEC §3 |
| New personal_apps/features/radar/price_chart_reader.py | Identity, bounded SQL and local fallback/chatter/tone composition; read_local_chart(ticker, sources, span, now, *, store=None) returns identity/window/chatter/fallback |
| New personal_apps/features/radar/price_chart_acquisition.py | Coordinator; get_or_start(identity, window, *, now) returns acquisition state plus cached normalized price; snapshot() returns process-scoped health |
| New personal_apps/features/radar/price_chart_fetch.py | Spawn-safe fetch_child(request_spec, result_connection); no Flask/DB imports or arbitrary URLs; public bytes/normalized result only |
| personal_apps/features/radar/prices/yahoo.py | Reuse identity/shape/transport helpers; additive bounded streaming/cache-disabled options for this child; old defaults/callers unchanged |
| personal_apps/features/radar/chatter_tone.py, only if needed | Injectable bounded source/event reader for new caller; old call path and classification/reconciliation semantics preserved |
| New personal_apps/features/radar/routes/price_chart.py; routes/__init__.py | Auth, explicit query validation, response assembly and route registration; GET /api/ticker/<ticker>/price-chart |
| personal_apps/features/radar/config.py; routes/views.py | Default-off flags and shell selected_price_charts_enabled boolean; source flag never browser-authoritative |
| personal_apps/features/radar/routes/operations.py | Additive selected_price_ops, no acquisition from reads |
| New personal_apps/static/radar/src/hub/priceChart.ts | PriceChartResponse types, validation and fetchPriceChart(ticker, sources, span, signal) |
| New personal_apps/static/radar/src/hub/SelectedPriceChart.tsx and selectedPriceGeometry.ts | New renderer with timestamped price/slot geometry, accessible hover/focus, existing visual language |
| personal_apps/static/radar/src/hub/queries.ts | usePriceChart query keyed by full selection/identity; visibility/pending policies |
| personal_apps/static/radar/src/hub/ResearchContent.tsx, Research.tsx, ChatterWorkspace.tsx, Hub.tsx, entries/hub.tsx | Carry flag/selection/visibility, choose chart payload atomically; preserve old renderer and nonchart sections |
| personal_apps/static/radar/src/hub/Admin.tsx and relevant ops type/parser | Small process-scoped provider-health section |
| New personal_apps/static/radar/src/hub/selected-price.css, if needed | Scoped chart states only; no page redesign |
| New personal_apps/tests/selected_price_unit/*; adjacent frontend *.test.ts(x) | Isolated tests, fake-clock/transport/store fixtures; avoid DB-loading root conftest for unit run |
| personal_apps/static/radar/dist/* | Generated Radar bundle/manifest only; preserve unrelated generated Gym changes |

Do not modify HA1 application/tests, provider quote-source enums, migrations, DB constraints, poller/scores, global source mappings or legacy chart semantics. Plan snippets define interfaces/behavior, not permission to bypass identity or auth.

## Task 1 — Data contract and local reader

- [ ] Record candidate identity/carry manifest and baseline relevant tests. Existing failed tests are recorded with exact commands, not silently fixed.
- [ ] Add pure window tests first, then implement bounded calendar lookup. Cases: Tuesday at 03:59/04:00/09:29/09:30/16:00/20:00 ET; weekend; Labor Day; early close; DST shift. At Tuesday 09:29, 1W excludes Tuesday; at 09:30 it includes Tuesday. Validate UTC from/to and slot ends independently of price-point count.
- [ ] Add normalization tests using committed copies of saved Yahoo arrays plus explicit synthetic metadata. Prove null-gap breaks, one point, missing session, off-grid omission, provisional bar, incorrect symbol/currency/MIC, zero/NaN and overflow. Then implement pure normalization. Do not contact the provider for tests.
- [ ] Implement new reader against an injected store using the spec's bounded projections and per-statement budget. Reuse analysis.SqlStore where possible; translate its errors to new route codes without changing HA1. Tests record exact statement count, bound parameters, sentinel rejection, identity-before-acquisition, mapping changes and no fallback regime splicing.
- [ ] Implement count/coverage and retained-tone alignment with current source choices; preserve bullish/bearish/neutral/unjudged/unavailable partitions and old tone tests. Add explicit 1W 09:30-anchored slot tests, clipped final bucket, source outage/truncation/config overlap and expired tone cases. Tone failure degrades only tone, not valid prices/counts.

Representative acceptance assertions (the worker supplies fixture constructors matching its pure input types):

```python
# Tuesday 2026-09-15, before regular open: five completed modeled sessions.
w = window_for('1W', datetime(2026, 9, 15, 13, 29, tzinfo=timezone.utc))
assert w.session_dates == ['2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11', '2026-09-14']
assert w.to == datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
# Missing price is not a continuous segment, missing chatter is not zero.
assert normalized.points[2].break_before is True  # after an explicit null bar
assert normalized.adjustment_basis == 'unknown'
assert unknown_slot.count is None
assert sum(tone_slot[k] for k in ('bullish','bearish','neutral','unjudged','unavailable')) == count_slot.count
```

Use dictionary/object syntax consistently with implementation; semantics above are binding, fixture naming is illustrative. Keep one shared set of wire types; no parallel subtly different contracts.

## Task 2 — Bounded acquisition and HTTP

- [ ] Test the coordinator with injected monotonic clock/child launcher first: stable-key cache reuse despite moving now, same-key coalescing, busy other-key refusal, exact rolling-start cap, negative cooldown, LRU/byte bounds, identity invalidation, stale expiry and flag-off no child.
- [ ] Implement lazy supervisor + spawn child per SPEC §6. Child import must not bootstrap the Flask app or inherit pooled DB connections. Reuse YahooHttp with new bounded/cache-disabled mode only in child. Verify existing Yahoo tests retain their previous behavior.
- [ ] Exercise a real synthetic hanging child, a pipe-filling oversized child and normal child using localhost/IPC only. Confirm route-side admission does not wait for child completion; child timeout triggers termination/reap and cleanup failure prevents another acquisition. Record observed deadline/cleanup timings; distinguish scheduler tolerance from configured deadlines. Use a fake clock for quota tests, not ten minutes of idle waiting.
- [ ] Add the authenticated route: only span, market and sources query keys. Call existing source parser on a validated subset; prevent arbitrary provider parameters, duplicate keys and GET side effects before auth. Response assembly never does provider I/O; tests assert local fallback pending -> cached ready transitions and DB errors don't become empty success.
- [ ] Add server bootstrap flags and additive ops data. Ops test: admin succeeds, non-admin refused, reading health never schedules work. Flag-off leaves the legacy route/payload and existing selected chart unchanged.

## Task 3 — Shared hub chart and candidate proof

- [ ] Add typed validation/fetch/query and tests for pending polls, 60s refresh, Retry-After, hidden/unmounted states, source/ticker/span changes, late replies and stale identity. Request only span/market/sources, not unrelated board window/segment/limit. Reuse the QueryClient for both consumers; no provider fetch per visual subcomponent.
- [ ] Build the timestamp geometry and component tests before wiring. Distinct price/chatter array lengths must still align by actual UTC time; a clipped last slot does not stretch other slots. Keyboard hover shows bar interval and provisional/coverage state; zero/one-point and no-price states remain usable.
- [ ] Integrate into ChartSection and both callers using the bootstrap flag. Keep legacy PriceChart untouched where possible. Preserve sentiment-coloured bars in the new component; never feed a rolling-window tone array into it. Preserve other panels' loading/quote behavior and explicitly label the chart's own window/summary.
- [ ] Add compact process-health output to Admin; no full admin refresh/redesign.
- [ ] Run isolated backend suite from personal_apps: `<python> -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q`. Resolve actual Python from existing local/bundled runtime; shell `python` is not on the Mastermind PATH. Do not assume it works. Run compatible focused Yahoo/tone regression tests in a DB-free harness or the existing safe fixture setup; report which were run.
- [ ] Run frontend suite: `npx vitest run -c vite.radar.config.ts`, then Radar build/typecheck: `npx tsc --noEmit` and `npx vite build -c vite.radar.config.ts`, from personal_apps. Do not run the full Gym build solely for this change. Capture baseline failures separately; new relevant failures must be resolved.
- [ ] Use python-playwright in one batch to exercise the **built real hub components**, both Research and Chatter research panel, with explicit synthetic API responses at 1440/768/390/320 and one real 200% browser zoom. Serve only candidate files on loopback port 5042 after checking free; do not stop any occupied port. Mock provider/API data at the network boundary, not by inventing a separate showcase. Save/view PNGs for ordinary, partial/null-gap, stored fallback, unavailable, long provenance and stale-switch states. Verify no horizontal document overflow, keyboard reachability, correct date/axis labels and unchanged headline. Label this fixture browser evidence, not full DB or production QA.
- [ ] Optional local DB proof: if installed MariaDB binaries are available, worker may provision a NEW fixture-only target under candidate radar-design/artifacts/md-selected-price-implementation/runtime on free loopback port 3462, isolated credentials, no existing data restore or production credentials. Create only required synthetic schema/data; record target identity, statement timeout/refusal/recovery and query plans. Never reuse default3306, 3399, HA1/3461 or existing B1C/promotion databases. If this cannot be done with the available installation, complete DB-free/browser proof and clearly record DB runtime evidence unavailable; do not spend a handoff round recreating HA1 QA.
- [ ] Update candidate ledger/HANDOFF and write MD-SELECTED-PRICE-IMPLEMENT-1-RETURN.md with actual source/compiled artifact fingerprint, commands/results, fixture identity, screenshots, exact edited/dirty paths and limitations. Keep copied reports unchanged. No commits/push/live activation/deployment or next worker dispatch.

## Acceptance matrix (one focused review, not per-task gates)

| ID | Required result | Proof |
| --- | --- | --- |
| P01 | Correct pinned US USD identity; unsupported safe fallback; no cross-venue mutation | Pure/reader/route tests |
| P02 | Current/last session and five-session bounds, DST/holiday/early close/partial now | Pure independently expected timestamps |
| P03 | Independent points/slots, null gaps, provisional bar ends, unknown adjustment | Recorded-array and synthetic geometry tests |
| P04 | Counts/tone align and reconcile; unavailable remains unavailable | Reader/reducer and shared component tests |
| P05 | Coherent stored fallback and accurate source/cache/event ages | Cache/reader/UI cases |
| P06 | No provider I/O on web thread, bounded child lifecycle, no queue/retry storm | Real local hanging/oversized child + fake-clock quota tests |
| P07 | Auth/validation/flags/ops and old responses preserve behavior | Route and regression tests |
| P08 | Both real hub chart surfaces usable desktop/mobile/zoom/keyboard; old headline unchanged | Built-hub fixture browser artifacts |
| P09 | DB statement/row limits and source request-form evidence honestly attributed | Fake-store assertions; local fixture DB if available; live Yahoo explicitly not run |

Reviewer evaluates the changed scope and unresolved findings once. No completed HA1 or Researcher work is redispatched. Deterministic implementation readiness can be accepted with explicitly recorded live-source/production limitations; it is not permission to claim operational readiness without those facts.

## Release carries and stop condition

Stop at a locally verified, uncommitted candidate plus self-contained Mastermind return. Both new flags default OFF. No live data request in this assignment. The later Deployer must know exact candidate SHA/fingerprint, intended flags, actual process topology, usage-condition disposition and whether exact epoch request form/closed-session behavior was ever checked against Yahoo. No unverified claim may disappear in that handoff. Rollback is flag-off plus normal code rollback; no new schema or poller changes to unwind.

If a bounded implementation detail needs adjustment, keep the spec's product/truthfulness/resource boundaries, record the decision in the candidate ledger and continue. Return a concrete blocker only for a material scope conflict or unavailable mandatory proof; don't ask the owner to decide routine code organization. Full copy/paste assignment and mandatory return template: MD-SELECTED-PRICE-IMPLEMENT-1-PROMPT.md.

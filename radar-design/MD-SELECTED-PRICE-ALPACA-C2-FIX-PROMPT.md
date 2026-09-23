# Prompt — MD-SELECTED-PRICE-ALPACA-C2-FIX

You are Radar's correction Implementer. Apply the smallest test-first patch for the accepted findings in `MD-SELECTED-PRICE-ALPACA-C2-RULING.md`, verify it locally, and stop. Do not broaden the C1 feature.

This prompt is prepared but not self-dispatching. Start only when the owner deliberately pastes it into an implementation task. Do not spawn subagents.

## Workspace and state

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
expected HEAD/origin-main: f632e5db5dd92e27480cbfccdf7b0638b26533ed
candidate: existing uncommitted C1 tracked + untracked delta
```

Preserve every existing dirty/untracked file. Do not create another worktree, reset, clean, stash, restore, stage, commit or push.

Read completely before editing:

1. root `HANDOFF.md`
2. `radar-design/MD-SELECTED-PRICE-LEDGER.md`
3. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`
4. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-RULING.md`
5. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RETURN.md`
6. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RULING.md`

Verify branch, HEAD, origin/main, status and tracked/untracked diff. Repository evidence wins over prose.

## Authorized corrections

### 1. Reject an unknown child-result source

Files:

- `personal_apps/features/radar/price_chart_acquisition.py`
- `personal_apps/tests/selected_price_unit/test_acquisition.py`

Write a failing test using an `ok` result with `source: "not_a_source"`. It must prove:

- the result increments `invalid`, not `success`;
- no cache entry is stored;
- the key enters the existing bounded invalid-result cooldown;
- the reader can continue to its coherent stored fallback/unavailable behavior rather than raising.

Then add the narrow validation at `_settle()`:

```python
result.get('source', contract.YAHOO_SOURCE) in contract.PROVIDER_PROFILES
```

Preserve the historical missing-source default for Yahoo compatibility. Do not harden unrelated pre-existing bar-element shapes in this patch.

### 2. Keep the sparse chart gutter visible when it fits

Files:

- `personal_apps/static/radar/src/hub/SelectedPriceChart.tsx`
- the smallest focused component/browser test or fixture-harness assertion

Start with a failing sparse-1D case. Compute the latest observation's rendered x position and the maximum scroll position. If the rightmost position still leaves at least half the viewport between its left edge and the latest observation, use the rightmost position so the price axis and window-end label are visible. Otherwise preserve the current latest-observation positioning for narrow mobile.

Prove at minimum:

- sparse FT-like desktop/tablet: latest marker and price-axis gutter are visible at rest;
- sparse FT-like 390px: latest marker remains visible and the chart does not sacrifice it merely to show the gutter;
- dense 1D and 1W behavior remains correct;
- no document overflow or smooth-motion regression.

Do not make the 912-unit chart fluid, change lane proportions or alter the accepted area rendering.

### 3. Preserve deliberate scroll-to-zero across refreshes

Files:

- `personal_apps/static/radar/src/hub/SelectedPriceChart.tsx`
- `personal_apps/static/radar/src/hub/SelectedPriceChart.test.tsx` and/or the existing deterministic browser harness

Replace the `scrollLeft !== 0` sentinel with explicit positioning state. Requirements:

- auto-position once for a newly selected ticker/span chart identity;
- ordinary data refreshes and resize callbacks preserve the reader's scroll position, including exactly `0`;
- a user scroll event marks the chart as reader-positioned;
- switching ticker or span resets auto-positioning for the new chart;
- programmatic initial positioning must not accidentally mark itself as a reader scroll.

Use the smallest refs/effects/listeners that meet those requirements. Avoid a new abstraction or dependency.

### 4. Report the actual operations source

Files:

- `personal_apps/features/radar/price_chart_acquisition.py`
- `personal_apps/tests/selected_price_unit/test_acquisition.py` and/or `test_route_ops.py`
- `personal_apps/static/radar/src/hub/Admin.test.tsx` only if the UI assertion needs adjustment

When Yahoo is the selected historical source, `ops_snapshot()['source']` must be `yahoo_chart`, not `alpaca_sip`; when Alpaca is selected it must remain `alpaca_sip`. Disabled/missing-credential states must stay truthful and non-secret-bearing. Preserve the current `source_state` vocabulary unless a focused test proves a change is required.

Do **not** rename `ALPACA_REFUSALS` and do not add a credential helper; both are explicitly outside this correction.

## Boundaries

- No other application behavior, refactor, cleanup, naming pass or test expansion.
- Do not open, parse, hash, search for or otherwise inspect the private root `.env` or real credential values. Use synthetic sentinels only.
- No live/outbound provider request, dependency install, flag activation, configuration, database, schema, migration, service, production action, commit, push or deployment.
- Keep the Alpaca and Yahoo flags off in actual configuration.

## Verification

Run the changed tests first after each correction, then:

```powershell
cd personal_apps
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts static/radar/src/hub/SelectedPriceChart.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/priceChart.test.ts static/radar/src/hub/Admin.test.tsx
npx tsc --noEmit
npm run build
```

Run the deterministic local browser harness for the sparse 1200/768/390 cases and one dense/1W control. It must make zero unmocked/outbound requests. Inspect the actual PNGs. Record exact commands and results; do not hide baseline failures.

## Stop and return

Create `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FIX-RETURN.md`, update only the current notices in root `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`, and stop with the candidate uncommitted and all flags off.

Return:

- exact files changed and why;
- failing-first and passing evidence for each accepted finding;
- full focused test/build/browser results;
- proof unknown source is rejected before caching and fallback no longer raises;
- measured initial pan results at 1200/768/390 and proof scroll position zero survives refresh;
- truthful Alpaca/Yahoo operations snapshots;
- inspected screenshot paths;
- branch/HEAD/origin-main and dirty status;
- confirmation of no real credential inspection, outbound provider request, activation, DB/service/production action, commit, push or deploy;
- recommendation for a **fresh-session independent** final C2 review, without dispatching it.

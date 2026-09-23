# Selected-price Alpaca C1 implementation plan

> Execute only after the owner deliberately dispatches `MD-SELECTED-PRICE-ALPACA-C1-PROMPT.md`. Work test-first, one implementation worker at a time, followed by an independent focused review.

**Goal:** replace the dormant selected-chart provider assumption with a bounded Alpaca SIP adapter and render actual price observations as the accepted compact segmented area chart, preserving real Radar chatter and coherent fallback.

**Architecture:** keep the existing Flask endpoint, pinned instrument identity, acquisition admission, isolated child, normalized-series boundary and stored fallback. Add a source-specific Alpaca HTTP/normalization module, switch source admission to a new default-off flag, and make the React geometry consume explicit hard-segment identity. The provider is one request for one selected symbol; no polling, pagination or storage fan-out.

**Tech stack:** Python/Flask, existing isolated subprocess protocol, React/TypeScript/SVG/CSS, pytest and Vitest, existing Radar build and python-playwright verification. No new runtime dependency, service or schema.

**Binding documents:** `MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`, `MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`, `MD-SELECTED-PRICE-SPEC.md`, and the accepted area preview under `artifacts/md-selected-price-personal-preview/`.

## Global constraints

- Preserve unrelated dirty work. Do not create another worktree, commit, push, deploy, activate flags or touch production.
- Do not make live provider requests or inspect credential values. Tests use sanitized local fixtures derived from the accepted evidence.
- Every implementation step begins with a failing focused test and ends with that test passing.
- Keep the new flag false by default. The locally configured production state remains selected charts ON, Yahoo OFF, Alpaca OFF.
- Use one implementation worker. After its complete return, use one independent read-only reviewer; do not overlap them.

## Task 1 — Specify and implement the bounded Alpaca adapter

**Files:**

- Create `personal_apps/features/radar/prices/alpaca.py`.
- Modify `personal_apps/features/radar/price_chart_contract.py` only for provider-neutral request/normalization interfaces and explicit hard-segment metadata.
- Modify `personal_apps/features/radar/price_chart_fetch.py` to select the Alpaca adapter.
- Create `personal_apps/tests/selected_price_unit/test_alpaca_bounded.py`.
- Extend `personal_apps/tests/selected_price_unit/test_normalize.py` and `test_window.py`.

**Failing tests first:**

Write fixtures representing one exact-symbol response, an empty bars map, fractional timestamps, an exact-close bar and a non-null page token. Assert a request equivalent to:

```python
{
    "symbols": "BRK.B",
    "timeframe": "1Min",
    "feed": "sip",
    "adjustment": "raw",
    "sort": "asc",
    "limit": 10_000,
    "start": "<UTC RFC3339>",
    "end": "<min(contract end, now-16m) UTC RFC3339>",
}
```

Assert one call only, the fixed `https://data.alpaca.markets` origin, no redirects, no ambient proxies, bounded timeout/body, and no secret values in raised or serialized output. Assert that one-symbol requests reject an unexpected bars key or non-null page token.

Add normalization cases proving:

```text
1W [13:30,20:00): 19:55 accepted, 20:00 excluded
1D after-hours [20:00,00:00): 20:00 accepted as after-hours
missing minute: no placeholder created
duplicate/out-of-order/non-positive/non-finite close: invalid result
```

**Implementation:**

Model the adapter after the safety properties of `prices/yahoo.py`, not its response shape. Build authentication headers at the last responsible point, redact provider response text from errors, cap bytes before JSON parsing, and classify HTTP/network/shape failures. Add a provider-neutral normalized point field or helper that yields a stable hard-segment key from session date, state and source/regime.

In `price_chart_fetch.py`, perform exactly one Alpaca call and emit the existing capped child-result envelope. If the 16-minute clamp leaves no range, emit a deterministic waiting/unavailable result without an HTTP call. Do not retain a Yahoo fallback inside the child; stored fallback remains the parent/reader responsibility.

**Verify:**

```powershell
py -3.12 -m pytest personal_apps/tests/selected_price_unit/test_alpaca_bounded.py personal_apps/tests/selected_price_unit/test_normalize.py personal_apps/tests/selected_price_unit/test_window.py -q
```

## Task 2 — Wire secrets, flags, admission and truthful operations status

**Files:**

- Modify `personal_apps/config.py` (or the existing Radar config module containing selected-price flags).
- Modify `personal_apps/features/radar/price_chart_acquisition.py`.
- Modify only the existing operations/status route and admin presentation files that currently expose the Yahoo selected-chart source state.
- Extend `test_launcher_isolation.py`, `test_acquisition.py`, `test_child_lifecycle.py`, `test_route_ops.py` and their frontend admin test if applicable.

**Failing tests first:**

Assert `RADAR_SELECTED_PRICE_ALPACA_ENABLED` defaults false and is independent of both selected-chart and Yahoo flags. Assert acquisition starts only when selected charts and Alpaca are enabled. Assert the child environment equals the existing platform minimum plus exactly:

```python
{"APCA_API_KEY_ID", "APCA_API_SECRET_KEY"}
```

for both Windows and POSIX constructions. Test with sentinel credential values and prove neither sentinel appears in captured command arguments, logs, stdout/stderr, result envelopes or error text. Cover missing credentials without starting a child.

Assert operations output names Alpaca truthfully and does not report the source active merely because charts are enabled. Preserve current coalescing, process caps, per-key cooldown and shutdown behavior.

**Implementation:**

Add `selected_price_alpaca_enabled()` and use it as the provider admission flag. Extend the narrow child allowlist with the two Alpaca names only. Keep the Yahoo function/flag for historical compatibility, but remove it from the active Alpaca admission path. Generalize misleading Yahoo-specific status labels only where required; do not delete unrelated code.

**Verify:**

```powershell
py -3.12 -m pytest personal_apps/tests/selected_price_unit/test_launcher_isolation.py personal_apps/tests/selected_price_unit/test_acquisition.py personal_apps/tests/selected_price_unit/test_child_lifecycle.py personal_apps/tests/selected_price_unit/test_route_ops.py -q
```

## Task 3 — Preserve endpoint, fallback and provenance truth

**Files:**

- Modify `personal_apps/features/radar/price_chart_reader.py` and the smallest endpoint serializer seam required.
- Modify `personal_apps/static/radar/src/hub/priceChart.ts` and fixtures/types only as required for explicit segment/provenance fields.
- Extend `test_reader.py`, focused API/route tests, `priceChart.test.ts` and fixtures.

**Failing tests first:**

Cover successful `alpaca_sip` data, empty/truncated/malformed/waiting/permission/throttle/transient results, and disabled source. For every non-success, assert the response contains one coherent stored series or a truthful unavailable state—never a mixture. For success, assert provenance reports delayed consolidated SIP, raw provider closes, actual count and latest timestamp without saying real-time.

Use a case with a valid Alpaca regular segment plus a stored fallback point and assert the stored point is not appended. Use real-shaped chatter slots for observed, partial, zero and unknown states and assert they pass through unchanged.

**Implementation:**

Map adapter classifications into the existing acquisition/reader result model. Preserve endpoint and selected-instrument identity. Add only stable, explicit segment metadata the renderer needs. Ensure fallback retains its own source/cadence/coverage labels. Keep real chatter and tone independently timestamped.

**Verify:**

```powershell
py -3.12 -m pytest personal_apps/tests/selected_price_unit/test_reader.py personal_apps/tests/selected_price_unit/test_route_ops.py -q
npm --prefix personal_apps/static/radar test -- --run src/hub/priceChart.test.ts
```

Adjust the npm invocation only to the repository's existing script syntax; do not install packages.

## Task 4 — Implement segmented area geometry and the accepted chart composition

**Files:**

- Modify `personal_apps/static/radar/src/hub/selectedPriceGeometry.ts`.
- Modify `personal_apps/static/radar/src/hub/SelectedPriceChart.tsx`.
- Modify `personal_apps/static/radar/src/hub/selected-price.css`.
- Extend `selectedPriceGeometry.test.ts`, `SelectedPriceChart.test.tsx`, `SelectedPriceSection.test.tsx` and `priceChartFixtures.ts`.

**Failing tests first:**

Create a 64-observation FT-like regular-session fixture with time gaps but a stable hard-segment key. Assert one line path, one area path, 64 inspectable observations and no per-point dot cloud. Then prove:

```text
same session/state/source with missing minutes -> one segment
regular to after-hours -> two segments
session day change -> two segments
source/regime change -> two segments
one observation -> one point marker, no area
multi-point segment -> no per-point markers; latest valid observation gets one marker
```

Compare the ordered `{timestamp, value}` pairs available to pointer/keyboard inspection with the ordered actual non-null inputs; they must be identical. A line segment is visual geometry only and adds no datum.

Use actual chatter fixtures to prove observed/partial/zero/unknown counts and tone are unchanged. Add accessible-name and keyboard cases, plus reduced-motion behavior if the component currently animates.

**Implementation:**

Group actual observations by the explicit hard-segment identity. Generate one linear line and baseline-closing area per multi-point group; do not use smoothing that overshoots values. Add a subtle cyan-to-transparent gradient and compact the lane proportions to the accepted preview. Keep chatter visually separate on the same time scale. Retain one latest marker and one-point segment markers only.

Do not copy the preview's synthetic discussion fixture into runtime. Do not add resampling, forward fill, candles, a market selector or DE/EUR behavior.

**Verify:**

```powershell
npm --prefix personal_apps/static/radar test -- --run src/hub/selectedPriceGeometry.test.ts src/hub/SelectedPriceChart.test.tsx src/hub/SelectedPriceSection.test.tsx src/hub/priceChart.test.ts
npm --prefix personal_apps/static/radar run build
```

## Task 5 — Integrated regression and visual proof

**Files:**

- Update built Radar assets only through the repository's normal build.
- Create sanitized visual evidence under a new C1 artifact directory.
- Update the current notices in the ledger and handoff with exact test results and dirty files.

**Backend verification:**

Run the full selected-price unit directory and focused Radar API tests. Then run the repository's relevant headline/board/HA1 regression targets already documented in current handoff evidence. Do not broaden into unrelated failing suites without recording why.

```powershell
py -3.12 -m pytest personal_apps/tests/selected_price_unit -q
```

**Frontend verification:**

Run focused Vitest, TypeScript checking through the existing build, and the production Radar build. Record exact commands, counts and failures.

**Visual verification:**

Use one batched python-playwright script against the built real hub components, not an embedded browser pane. Capture 1200, 768 and 390 CSS-pixel widths plus 200% zoom for:

- sparse FT-like 1D;
- dense liquid 1D;
- 1W provider success;
- stored fallback/unavailable;
- chatter partial and unknown.

Compare with `artifacts/md-selected-price-personal-preview/area-1200.png` and `area-390.png`. Inspect the PNGs, keyboard through actual observations, and confirm no clipping, overnight fill, false real-time wording or dot cloud. Material visual changes require owner review; do not silently reinterpret the accepted direction.

**Stop and return:**

Leave a locally verified, uncommitted candidate with the Alpaca flag off. Report changed files, tests, screenshots, limitations, exact flag state and any environmental failure. Update continuity so the next action is one independent focused review. Do not activate, commit, push or deploy.

## Independent C2 review after implementation

The reviewer receives the binding ruling/spec, implementation return, full diff and verification artifacts. Review only source-contract compliance, child isolation/secrets, one-call/no-pagination behavior, observation preservation, segment breaks, fallback truthfulness, real chatter and accepted desktop/mobile/zoom presentation. Findings precede any fix dispatch. Production activation remains a separate owner decision even after a clean review.

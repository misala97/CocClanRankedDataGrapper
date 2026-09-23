# Prompt — MD-SELECTED-PRICE-ALPACA-C2

You are Radar's independent focused C2 Reviewer/QA. Review the uncommitted `MD-SELECTED-PRICE-ALPACA-C1` candidate against its binding source contract, specification and implementation plan. This is a read-only product-code review: identify defects and return a verdict; do not fix application or test code.

This prompt is prepared but not self-dispatching. Start only when the owner deliberately pastes it into a separate review task. Do not spawn subagents.

## Workspace and candidate identity

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
base/current HEAD: f632e5db5dd92e27480cbfccdf7b0638b26533ed
origin/main: f632e5db5dd92e27480cbfccdf7b0638b26533ed
candidate: uncommitted tracked + untracked working-tree delta
```

Base and current HEAD are intentionally identical. `git diff BASE..HEAD` is therefore empty and is **not** the review surface. Inspect `git status --short`, tracked `git diff`, and the authorized untracked files directly. Preserve every pre-existing dirty/untracked file. Never reset, clean, stash, restore, checkout, stage, commit or push.

## Read completely before judging

1. root `HANDOFF.md`
2. `radar-design/MD-SELECTED-PRICE-LEDGER.md`
3. `radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`
4. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`
5. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-PLAN.md`
6. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-RULING.md`
7. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-RETURN.md`
8. `radar-design/artifacts/md-selected-price-alpaca-c1/evidence.md`
9. `radar-design/artifacts/md-selected-price-alpaca-c1/browser/results.json`
10. the accepted area preview HTML and `area-1200.png` / `area-390.png`

Verify branch, HEAD, origin/main and status. Treat repository/test evidence as authoritative when prose conflicts.

## Exact review surface

Review every C1 change in:

- `personal_apps/features/radar/prices/alpaca.py`
- `personal_apps/features/radar/config.py`
- `personal_apps/features/radar/price_chart_contract.py`
- `personal_apps/features/radar/price_chart_fetch.py`
- `personal_apps/features/radar/price_chart_acquisition.py`
- `personal_apps/features/radar/price_chart_reader.py`
- selected-chart/Admin frontend source files changed by C1
- all changed selected-price tests/fixtures, `probe_child.py`, `helpers.py`
- untracked `personal_apps/tests/selected_price_unit/test_alpaca_bounded.py`
- generated Radar assets only insofar as build evidence says they correspond to source

Separate the C1 application/test delta from pre-existing continuity and research artifacts. Do not review unrelated historical work.

## Required review questions

### Source and identity contract

- Is every acquisition exactly one pinned symbol and at most one fixed-host Alpaca request with `1Min|5Min`, `sip`, `raw`, ascending, limit 10000?
- Is the end clamped to `min(contract end, now-16m)`, with no call for an empty interval?
- Are redirects, ambient proxies/netrc, cookies, retries, pagination, IEX, asset calls and alternate-symbol fallthrough impossible?
- Are exact bars key, strict increasing RFC-3339 timestamps, finite positive closes, response/body/result caps and non-null page-token rejection enforced?
- Does Radar remain the US/USD identity authority and preserve `BRK.B`?
- Are missing minutes absent rather than null/zero/forward-filled?
- Is the exact regular-close timestamp excluded from 1W and retained only as a separate 1D after-hours segment when eligible?

### Isolation, secrets and operations

- Does the child receive only the platform minimum plus `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`?
- Can values escape through arguments, stdin spec, results, exceptions, logs, ops status, repr, provider text or tests?
- Are flags independent and default-off, with admission requiring charts + Alpaca + both nonblank names?
- Are permission, throttle, waiting, empty, truncated, malformed, network/server and missing-credential outcomes distinct and bounded without retry loops?
- Is operations status truthful and non-secret-bearing?

Use synthetic sentinels only. **Do not open, parse, hash, search for or otherwise inspect real credential values or the private root `.env`.** Do not make any provider/network request.

### Data integrity and fallback

- Does a provider success publish only one complete Alpaca series?
- Does every incomplete/failure case select one whole stored fallback or truthful unavailable state, never splice sources?
- Are hard segments guaranteed to change across session date, market state and source/regime while quiet missing minutes remain connected only as visual geometry?
- Do plotted and inspectable timestamp/value pairs exactly equal actual non-null observations?
- Are real chatter/tone counts and observed/partial/zero/unknown meanings preserved independently?

### Interface and accessibility

- Is there one linear line plus subtle baseline-closing area per multi-point hard segment, one dot for a singleton, one latest marker and no dot cloud or smoothed/invented values?
- Is delayed SIP/raw/fallback provenance accurate and never labeled real-time?
- Are keyboard navigation, focus, accessible summary/readout and reduced-motion behavior sound?
- Inspect representative 1200px, 390px and real-200%-zoom screenshots. The Mastermind accepts the existing 912-unit panned canvas for C2; report a finding only for a demonstrated defect such as hidden latest data, unreachable history, clipped controls/readout, focus loss or document overflow—not merely because a fluid alternative exists.
- Check that opening on the latest actual observation does not override deliberate user scrolling on rerender or range changes.

## Verification

Run the smallest independent proof set first:

```powershell
cd personal_apps
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts static/radar/src/hub/SelectedPriceChart.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/priceChart.test.ts static/radar/src/hub/Admin.test.tsx
npx tsc --noEmit
```

Sample the recorded broader gates when needed to resolve a finding. Do not install dependencies, contact a provider or run DB/production tests. Browser verification may reuse the deterministic local fixture harness; it must have zero unmocked/outbound requests. Inspect the actual PNGs rather than trusting `results.json` alone.

## Severity and verdict

Report only evidenced findings with exact file and line references:

- **Critical:** security exposure, wrong identity/source, fabricated/spliced data, uncontrolled provider behavior, or a broken primary chart path.
- **Important:** binding contract breach, meaningful fallback/segment/accessibility defect, or material missing test that must be fixed before acceptance.
- **Minor:** bounded maintainability or presentation issue that does not block acceptance.

Explicitly distinguish a product-code defect from the two already-recorded process exceptions: the Implementer unnecessarily inspected real credential values in memory, and Task 1's red run was reconstructed after implementation. Do not repeat either action and do not report them as new code findings.

Choose exactly one verdict:

1. `ACCEPT C1 FOR OWNER ACTIVATION/DEPLOYMENT DECISION` — no Critical or Important findings.
2. `FIX REQUIRED BEFORE C1 ACCEPTANCE` — one or more Critical/Important findings; provide the smallest bounded fix packet.
3. `REVIEW BLOCKED` — evidence cannot be obtained without new authority; name the exact blocker.

Even an accept verdict does not authorize activation, configuration changes, commit, push, database/service/production action or deployment.

## Return contract

Create `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RETURN.md` as the only allowed repository write, then return a copy/paste Mastermind prompt. Include:

- exact verdict;
- strengths;
- findings grouped Critical / Important / Minor with `file:line`, impact and smallest fix;
- commands and exact results;
- screenshot paths inspected and visual/accessibility ruling;
- source/identity, child isolation/secrets, one-call/no-pagination, fallback, observation and chatter conclusions;
- unresolved release carries;
- branch/HEAD/origin-main and final status;
- confirmation of no real credential inspection, live/outbound provider request, product/test edit, activation, commit, push or deploy.

Do not update continuity files; the Mastermind will record the independent verdict.

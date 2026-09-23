# Prompt — MD-SELECTED-PRICE-ALPACA-C1

You are Radar's selected-price C1 Implementer. Build one locally verified, uncommitted candidate that uses Alpaca Basic consolidated SIP behind the existing isolated acquisition boundary and renders the accepted segmented area chart with Radar's real aligned chatter.

This prompt is prepared by the Mastermind but is not self-dispatching. Start only when the owner deliberately pastes it into an implementation task.

## Workspace and evidence authority

Work only in:

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
expected starting HEAD: f632e5db5dd92e27480cbfccdf7b0638b26533ed
expected origin/main: f632e5db5dd92e27480cbfccdf7b0638b26533ed
```

The worktree already contains intentional uncommitted planning/evidence files. Preserve all of them and all unrelated changes. Do not create another worktree, reset, clean, stash, restore, commit or push.

Before editing, read these files completely in order:

1. root `HANDOFF.md`
2. `radar-design/MD-SELECTED-PRICE-LEDGER.md`
3. `radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`
4. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`
5. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-PLAN.md`
6. `radar-design/MD-SELECTED-PRICE-SPEC.md`
7. `radar-design/MD-SELECTED-PRICE-AREA-DATA-PLAN.md`
8. `radar-design/MD-SELECTED-PRICE-ALPACA-VALIDATE-1-RETURN.md`
9. `radar-design/artifacts/md-selected-price-alpaca-validate-1/README.md`
10. the accepted preview HTML/builder under `radar-design/artifacts/md-selected-price-personal-preview/`

Verify branch, HEAD, origin/main, status, diff and recent log against those documents. Evidence wins if continuity text conflicts. Do not re-run the provider validation and do not read or print credential values.

## Binding outcome

Implement the plan task by task, failing test first. Preserve the current selected-price endpoint, pinned US/USD identity, admission/coalescing, isolated child, stored fallback and real chatter/tone reads.

The provider contract is:

- exactly one selected symbol and at most one Alpaca historical-bars request per child;
- 1D one-minute extended-window bars; 1W five-minute regular-session bars;
- `feed=sip`, `adjustment=raw`, `sort=asc`, `limit=10000`;
- clamp end to `min(contract end, now UTC minus 16 minutes)` and make no call if the resulting interval is empty;
- fixed HTTPS data host, bounded response/result, no redirects, ambient proxies, cookies, retries, pagination, IEX fallback or asset call;
- exact returned symbol-key match, strictly increasing RFC-3339 timestamps, finite positive closes, and rejection of any non-null `next_page_token`;
- missing minutes remain absent;
- 1W regular intervals exclude the exact close timestamp; eligible 1D windows retain it only as after-hours and start a new hard segment.

Use Radar's instrument record for US/USD identity. Preserve `BRK.B` dot form. A provider failure or incomplete result selects one coherent stored fallback; never splice sources.

Add `RADAR_SELECTED_PRICE_ALPACA_ENABLED`, default false and independent of the existing chart/Yahoo flags. Only `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` may be added to the acquisition child's minimal environment. Values must never appear in arguments, output, logs, errors, fixtures, docs or responses.

For rendering, connect only actual observations within a stable session/state/source-regime hard segment. Missing minutes inside a segment do not split it. Produce a subtle area fill per multi-point segment, one latest marker, and one dot for a one-observation segment. Never make interpolated geometry inspectable. Preserve actual observation pairs exactly, real chatter/tone and their observed/partial/zero/unknown semantics. Match the accepted compact desktop/mobile direction.

## Authorized code scope

Own only the smallest necessary delta in:

- `personal_apps/features/radar/prices/alpaca.py` (new)
- `personal_apps/features/radar/price_chart_contract.py`
- `personal_apps/features/radar/price_chart_fetch.py`
- `personal_apps/features/radar/price_chart_acquisition.py`
- `personal_apps/features/radar/price_chart_reader.py`
- the existing selected-chart config, endpoint and ops/admin status seams strictly required by the spec
- `personal_apps/static/radar/src/hub/priceChart.ts`
- `personal_apps/static/radar/src/hub/selectedPriceGeometry.ts`
- `personal_apps/static/radar/src/hub/SelectedPriceChart.tsx`
- `personal_apps/static/radar/src/hub/selected-price.css`
- their focused fixtures/tests and normally generated Radar build assets
- a new sanitized C1 evidence directory and current notices in the selected-price ledger/root handoff

Stop and report before changing schema, shared quote persistence, headline/ranking/board logic, HA1, market identity beyond the selected chart, services or dependencies.

## Required workflow

1. Follow every task and test matrix in `MD-SELECTED-PRICE-ALPACA-C1-PLAN.md` in order.
2. Make no live Alpaca request. Use deterministic sanitized fixtures; do not inspect the private `.env`.
3. Keep the Alpaca flag off. Do not activate Yahoo, alter production configuration, touch a database, start a service, deploy, commit or push.
4. Run the focused tests after each task, then the full selected-price and specified regression/build verification.
5. Use one batched python-playwright script for 1200/768/390 and 200% zoom visual proof. Inspect the produced PNGs and compare them with the accepted area preview. Do not use an embedded browser pane for screenshots.
6. If a test exposes a conflict with the binding contract, stop and return the conflict rather than broadening scope.
7. Update continuity with the exact commands/results, changed and dirty files, generated evidence, known environmental failures, flag state and immediate next action.

## Return contract

Return a self-contained implementation report containing:

- outcome and whether every C1 acceptance condition is satisfied;
- exact changed/generated files and why;
- source request/normalization/failure behavior implemented;
- proof of secret isolation and default-off flags;
- backend/frontend/build/visual commands and exact results;
- screenshot paths and visual findings;
- remaining limitations or environmental failures;
- confirmation that there were no live provider calls, activation, DB/production/service action, commit, push or deploy;
- exact branch/HEAD/origin-main and final dirty status;
- recommendation for one independent focused C2 review, with no dispatch.

Do not claim completion from code inspection alone. If verification cannot run, report the candidate as incomplete and preserve the evidence needed for the next decision.

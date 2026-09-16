# Selected-price area chart and usable data path — bounded C plan

2026-09-16. Mastermind planning only. This plan implements owner priority C before A and B. It does not authorize implementation, provider activation, account creation, subscription, purchase, commit, push or deployment.

**Goal:** make the selected US/USD 1D view immediately readable as the accepted compact continuous area chart, powered by real reported price observations and real aligned Radar chatter, with a provider path that is actually usable under the owner's EUR0/private-personal constraints.

**Architecture:** preserve the deployed selected-price endpoint, identity pinning, background acquisition isolation, coherent stored fallback and independently timestamped chatter. Replace only the price drawing and compact chart composition after a source decision. A source-specific adapter may replace the dormant Yahoo child behind the existing normalized-series boundary; it must not enter headline selection, board scoring, polling or shared quote storage.

**Tech stack:** existing Flask/Python reader and isolated acquisition child; React/TypeScript/SVG; existing Radar MariaDB chatter/tone reads; no new service, schema migration or frontend dependency.

**Spec and accepted design:** `radar-design/MD-SELECTED-PRICE-SPEC.md`, amended by this plan; `radar-design/artifacts/md-selected-price-personal-preview/preview-area.html` and `build_area.py`. The accepted artifact governs the visual direction, not its synthetic discussion fixture.

## Current C0 ruling — PASSED 2026-09-16

Binding acceptance: `radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`. The bounded account-backed validation passed: Alpaca Basic consolidated SIP is accepted for the owner-only selected US/USD chart role, with a 16-minute live-end clamp, one symbol and one request per child, no pagination, no IEX mixing, and coherent stored fallback. Radar's pinned instrument remains the identity authority. Existing half-open intervals govern the exact closing-minute bar: excluded from 1W regular data, but eligible as a separate after-hours point in the 1D extended window.

The implementation packet is ready in `MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`, `MD-SELECTED-PRICE-ALPACA-C1-PLAN.md` and `MD-SELECTED-PRICE-ALPACA-C1-PROMPT.md`. It is **PREPARED / NOT DISPATCHED**. No validation rerun, implementation, provider activation or production action is authorized by this update. Stored-only remains fallback and the new Alpaca flag must default off.

## Current evidence and decision gate

- Deployed at `f632e5db5dd92e27480cbfccdf7b0638b26533ed`: selected charts ON, new Yahoo acquisition OFF. Stored fallback and real aligned chatter are live.
- The deployed reader already returns real 15-minute 1D / hourly 1W chatter slots and retained recorded tone for the exact chart window. No production implementation may use the preview's synthetic discussion arrays.
- The current renderer deliberately splits the price line at every null or missing expected bar and draws isolated dots. That behavior conflicts with the accepted preview.
- Accepted renderer rule: connect actual reported prices within one market session and compatible price regime; the connection is a visual guide, not a new observation. Do not join overnight/session or incompatible-regime boundaries. Use a subtle area fill. Show only a latest marker (and a single-observation marker when necessary), not a dot at every reported price.
- FT evidence is sufficient to judge rendering, not source coverage: Yahoo returned 64 regular-session observations; Nasdaq returned the same 64 regular-session time/price pairs within `0.0001`. AAPL Yahoo returned 390/390. More FT points are not a prerequisite for a readable chart.
- No reviewed source currently clears the operating gate. Yahoo and Nasdaq technically work but their reviewed terms do not establish permission for unattended automated capture. Finnhub's existing personal key proves `/quote`; repository evidence says the free tier returned 403 for `/stock/candle`. Twelve Data is currently used for daily data and its intraday entitlement is unproved. Massive is a licensed/keyed daily source; minute aggregates on the existing entitlement are unproved. Stored Radar quotes/daily closes remain a truthful but sparse fallback, not the intended 1D improvement.

**Gate C0:** before an Implementer is assigned, select one source that passes all mandatory criteria below, or return that no eligible source exists. If none passes, C stops at the accepted renderer plan and the owner receives a concrete choice: keep stored-only data, permit a named free-account requirement, or relax a different stated constraint. Do not implement another source assumption.

Mandatory source criteria:

1. EUR0 and no paid subscription or purchase. Creating a new free account/API credential is not authorized; report it as an owner decision if it is the only remaining route.
2. Current official documentation or applicable terms support automated private/personal use for this integration. Successful HTTP access, robots rules or existing unrelated use are not permission.
3. US equities with native USD identity metadata; representative evidence must include a liquid common share, ETF, small/less-liquid listing and class-share symbol behavior.
4. 1D priority: current or most recent regular session, timestamped actual observations suitable for a connected reported-price line. Complete 390-minute coverage is not required. The response must distinguish unavailable data from a zero price.
5. Sustainable on-open use at no more than one refresh per visible chart per minute, with a documented quota or a conservative enforceable application budget. No polling or whole-universe acquisition is in scope.
6. 1W intraday is desirable but not required for gate passage. If absent, the current coherent stored daily-close fallback remains for 1W and is labelled as such.

## Task C0 — Select the usable data path

**Role:** one owner-selected Researcher. Assignment: `MD-SELECTED-PRICE-FREE-DATA-PATH-1`.

**Files produced:**

- Create `radar-design/MD-SELECTED-PRICE-FREE-DATA-PATH-1-RETURN.md`.
- Create sanitized evidence under `radar-design/artifacts/md-selected-price-free-data-path-1/`.
- Update only the current notice in `radar-design/MD-SELECTED-PRICE-LEDGER.md` and root `HANDOFF.md`; do not edit application code.

**Required work:**

1. Reuse the existing Yahoo/Nasdaq/Finnhub research; do not repeat their broad comparison. Treat Yahoo and Nasdaq as technically demonstrated but permission-blocked unless a current authoritative source directly changes that conclusion.
2. Check existing configured, documented providers first: Finnhub chart/candle entitlement, Twelve Data intraday entitlement and Massive minute-aggregate entitlement. Inspect credential presence without printing values. A current repository-proven 403 or plan exclusion may close a candidate without another live call.
3. Screen at most three additional documented EUR0 candidates. Prefer official APIs/downloads over page scraping. Separate "works after a free account" from "works with current authorized state".
4. Use primary-source documentation/terms. Live probes are optional and only for a candidate that first passes the documentation gate. Maximum 12 provider requests total, sequential, one attempt per request shape/instrument, fixed ordinary configuration, no retry after 401/403/429, no proxy/cookie/credential acquisition and no rate-limit discovery.
5. Return a pass/fail matrix against the six criteria, exact request/response semantics for any passing candidate, observed sample limits, intended traffic budget, and the smallest integration seam into `price_chart_fetch.py` / `price_chart_acquisition.py`.
6. Recommend exactly one of: `implement <named source>`, `stored-only renderer`, or `owner decision required for <named free-account/constraint change>`. Do not recommend implementation with unresolved permission or entitlement.

**C0 acceptance:** the Mastermind can name the selected source, exact permitted role, credential/account state, supported 1D/1W ranges, identity validation, quota and known coverage limitations without inference. Otherwise the result explicitly closes the gate as unavailable. The 2026-09-16 Researcher return completed the survey but did not satisfy this acceptance condition for Alpaca because no account/probe exists and representative identity/response behavior remains unverified.

## Task C1 — Implement the accepted area renderer and selected adapter

**Start condition:** satisfied by the Alpaca source ruling. The owner may now deliberately dispatch `MD-SELECTED-PRICE-ALPACA-C1-PROMPT.md`. This task is implementation-ready but not yet dispatched.

**Files expected to change:**

- `personal_apps/static/radar/src/hub/SelectedPriceChart.tsx`
- `personal_apps/static/radar/src/hub/selectedPriceGeometry.ts`
- `personal_apps/static/radar/src/hub/selected-price.css`
- their focused tests and built Radar assets
- only the provider-specific fetch/normalization files named by the C0 ruling; preserve the current endpoint/reader contract where possible

**Interfaces and behavior:**

- Keep `GET /radar/api/ticker/<ticker>/price-chart` and its pinned US/USD identity, acquisition states, real aligned chatter/tone and coherent fallback.
- Add a hard segment identity to normalized price points (session date plus compatible source/regime) or an equivalent explicit interface. Null/missing expected bars remain disclosed observations but do not split the visual line inside a hard segment. Hard session and regime boundaries always split it.
- Geometry produces one line path and one area path per hard segment. The area closes to the price-lane baseline and uses a subtle cyan-to-transparent gradient. One-point hard segments render one dot. Multi-point segments render no per-observation dots; the latest valid point keeps one marker.
- The renderer must never create extra points, resample, smooth or claim an OHLC candle. Hover/keyboard reads only an actual returned observation and retains the existing provenance/coverage wording.
- Compact the price lane to the accepted proportions and keep the discussion lane visually separate but on the same actual time frame. Use real `data.chatter.slots` and `data.chatter.tone.slots`; no synthetic chart fixture reaches runtime.
- 1D is the acceptance priority. 1W may use the selected provider only if C0 proves it; otherwise keep the current stored daily fallback and label it plainly.
- Remove active DE/EUR assumptions from new code. Task A will remove remaining existing functionality later; C1 must not introduce a new market selector, EUR branch or DE fallback.

**Failing-first tests:**

1. Sixty-four FT-like observations separated by null expected minutes create one regular-session line/area segment, not dozens of dots or broken paths.
2. Two sessions create two independent filled segments; no overnight fill or line.
3. A source/regime change inside a session creates two segments.
4. A one-observation segment renders a dot; a multi-point segment renders only the latest marker.
5. The number and timestamps of plotted/inspectable values exactly match the non-null input observations; connected geometry adds no data values.
6. Actual chatter arrays with observed, partial, zero and unknown slots retain their counts/tone and align by timestamps.
7. Provider unavailable/backoff/unsupported uses one coherent stored fallback with its own labels and never splices it into a provider segment.

**Verification:** focused backend adapter/normalization tests; focused Vitest geometry/component/query tests; TypeScript and Radar build; one batched python-playwright run of the built real hub components at 1200/768/390 plus 200% zoom, covering ordinary sparse 1D, complete 1D control, 1W fallback, unavailable source and real chatter unknown/partial states. Compare to `area-1200.png` and `area-390.png`; material visual departures require owner review.

**Stop:** locally verified uncommitted candidate, flags default safe, no live activation, commit, push or deployment. Return to Mastermind for one focused independent Reviewer/QA.

## Task C2 — Focused independent review

One owner-selected Reviewer/QA checks only the C1 delta: source gate compliance, actual observation preservation, session/regime breaks, real chatter, fallback truthfulness, 1D desktop/mobile/zoom presentation and no regression to headline/board/HA1. No repeat of the closed selected-price release review or provider research. Deployment remains a separate owner decision.

## What the owner will see improve

On 1D, the price stops looking like scattered fragments. Radar draws one calm cyan area line through the prices the source actually reported during the session, with a light fill and a single current marker. The discussion bars underneath are Radar's real retained mention/tone buckets for that same time window. Moving or tabbing across the chart reports actual observations and coverage; it does not invent minute prices. On illiquid FT, 64 real observations remain 64 observations—the line simply makes their movement readable. On a liquid stock, denser actual observations naturally produce a denser line.

The data path will be the C0-selected documented free source for on-open 1D observations. Until that source returns, or whenever it is unavailable, Radar continues to show its coherent stored quote/daily fallback with explicit provenance. No new provider is silently enabled by this plan.

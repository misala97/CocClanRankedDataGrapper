# Selected-price C1 binding specification — Alpaca SIP + accepted area chart

Date: 2026-09-16  
Status: implementation-ready, **not dispatched**  
Binding source ruling: `MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`

## Outcome

When the source flag is enabled later, Radar's owner can open a pinned US/USD instrument and see a readable 1D or 1W selected-price chart made from delayed consolidated-SIP observations. The chart connects reported observations inside compatible segments, uses the accepted restrained area treatment, and aligns Radar's real retained chatter beneath the same time axis. When Alpaca is disabled or unavailable, the existing coherent stored fallback remains truthful and usable.

This task produces a locally verified candidate only. Both the new Alpaca flag and the historical Yahoo source flag remain off. Activation and deployment require a separate owner decision.

## Data-source contract

### Request shapes

The isolated child makes at most one Alpaca request for the exact selected symbol:

- 1D: one-minute bars for the contract's extended-hours session intervals.
- 1W: five-minute bars for the contract's regular-session intervals.
- Common parameters: `feed=sip`, `adjustment=raw`, `sort=asc`, `limit=10000`, UTC RFC-3339 start/end.
- End clamp: `min(window.end, now_utc - 16 minutes)` whenever the contract end is newer. If the result is not after the start, skip the provider call.

No batch symbols, pagination, retries, redirects, IEX requests, asset request, automatic source switching or background polling are allowed.

### Normalization

The normalized source name is `alpaca_sip`; price kind is provider bar close; adjustment is raw. Parse RFC-3339 timestamps including fractional seconds. Accept only an exact bars-map key match, a list payload, strictly increasing timestamps and finite positive closes. Clip observations to the existing half-open intervals and assign their existing session/state classification.

Omitted minutes remain omitted. Do not manufacture null bars, zero bars, forward-filled bars or synthetic intermediate values. Deduplication may only reject an invalid duplicate timestamp; it may not silently choose one duplicate.

Any non-null `next_page_token` invalidates the provider result as truncated. An empty `bars` map or empty exact-symbol list is an empty result. Both select the existing coherent fallback; neither is a successful zero-valued series.

### Closing-minute behavior

Keep half-open intervals:

- 1W regular: exclude the exact regular-close timestamp.
- 1D extended: retain that timestamp only if it lies in the existing after-hours interval, mark it after-hours, and begin a new hard segment.

Do not alter calendar boundaries to accommodate the provider.

### Failure behavior

Map bounded failure classes into the existing acquisition/result vocabulary without returning secret-bearing provider text. Required distinctions are disabled, credentials missing, waiting-for-delay, empty, truncated, malformed, authentication/permission, throttled, timeout/network and provider/server unavailable. A too-recent SIP refusal is source-unavailable/waiting for this acquisition and must not start a retry loop or a provider-wide throttle ladder.

Only a fully valid Alpaca result is stored/published as provider data. On every other result, use one complete stored fallback and retain its own source, cadence and coverage labels. Never merge stored points with Alpaca points.

## Identity and security

`RadarInstrument` remains the identity authority: pinned US market, USD currency, exact canonical ticker and existing MIC/exchange metadata. Alpaca does not override currency or identity. `BRK.B` stays in dot form. The exact response symbol key is an additional integrity check.

The parent must pass only `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` into the acquisition child, plus the existing minimal platform variable. The adapter sends them only as Alpaca authentication headers over the fixed HTTPS host. Do not place credential values in command arguments, stdout/stderr, structured child results, exceptions, application logs, tests, screenshots or documentation. The HTTP client must ignore ambient proxy configuration, disallow redirects, enforce existing time/body/result caps and use no cookies.

## Flags, admission and rate budget

Add `selected_price_alpaca_enabled()` backed by `RADAR_SELECTED_PRICE_ALPACA_ENABLED`, default false. Provider acquisition requires both selected charts and Alpaca source flags; the Yahoo flag does not authorize Alpaca. Preserve current per-key admission/coalescing/backoff behavior and the maximum product budget of two visible-chart acquisitions per minute, far below the observed account limit.

Operations output must truthfully report selected-chart enablement, Alpaca-source enablement and current source state. Remove Yahoo-specific wording from generic selected-chart status where it would become misleading, but do not delete historical Yahoo code in C1.

## API and provenance

Keep `GET /radar/api/ticker/<ticker>/price-chart` and the current response structure wherever possible. Extend only what the renderer needs to receive a stable hard-segment identity or equivalent explicit fields.

For valid provider data, the UI must disclose delayed consolidated SIP, raw closes, actual-observation count, expected/covered intervals and the latest observation timestamp. It must never label the series real-time. Existing stored fallback labels remain unchanged. Chatter and tone keep their independent timestamps and completeness states; preview fixture text or counts must not enter runtime.

## Rendering contract

Implement the accepted artifact direction from `artifacts/md-selected-price-personal-preview/preview-area.html`:

- Derive hard segments from actual non-null price observations. At minimum, split on session, market state and source/regime identity.
- Missing expected minutes inside one hard segment do not break the line. The straight connection is a visual guide between real observations, not a new datum.
- Produce one line path and one area path per multi-point hard segment. Close each area to the price-lane baseline and use a subtle cyan-to-transparent fill.
- Render a dot for a one-observation segment. For multi-point segments, omit per-point dots and retain one latest-observation marker.
- Hover, focus and keyboard inspection may land only on actual returned observations. Geometry must not add inspectable timestamps or values.
- Do not connect or fill across sessions, regular/after-hours boundaries, source changes or fallback/provider boundaries.
- Keep price and real chatter lanes visually distinct on the same actual time frame. Preserve observed, partial, zero and unknown chatter meanings.
- Preserve accessible names, keyboard navigation, reduced-motion behavior and compact desktop/mobile layout. At 200% zoom the chart remains usable without clipped controls or unreadable labels.

1D is the primary acceptance view. 1W uses Alpaca five-minute bars when a complete provider result succeeds; otherwise it uses the current stored fallback. No synthetic discussion data, smoothed curve, OHLC implication or new market selector is allowed.

## Acceptance tests

The candidate is acceptable only when deterministic tests prove:

1. Request parameters, 16-minute clamp, one-symbol/one-call limit, fixed host, redirect/proxy rejection and response caps.
2. Fractional RFC-3339 parsing, positive finite closes, exact symbol key, strict ordering, empty-series handling and page-token rejection.
3. A regular-close timestamp is excluded from 1W regular data and retained as a separate after-hours segment in eligible 1D data.
4. Credentials are absent from parent/child diagnostic output and only the two named variables enter the child environment.
5. Disabled, missing-credential, too-recent, empty, truncated, malformed, permission, throttle and transient failures preserve coherent fallback and admission semantics.
6. FT-like sparse observations produce one readable line/area segment inside the same state; two sessions or incompatible states/sources produce separate segments.
7. Plotted and inspectable timestamp/value pairs equal the input's actual non-null observations exactly.
8. Single-observation and latest-marker rules hold; no dot cloud returns.
9. Real chatter counts/tone and their unknown/partial states remain unchanged and aligned.
10. Existing selected-price, headline, board and HA1 behavior remains green.

Visual verification uses the built real hub components at 1200, 768 and 390 CSS pixels plus 200% zoom, covering sparse 1D, dense 1D, 1W, fallback/unavailable and chatter partial/unknown states. Material departures from the accepted area artifact require owner review.

## Explicit non-goals

No live provider probe, activation, production/config mutation, schema migration, service, new dependency, whole-universe capture, quote-store write, headline/ranking change, DE/EUR cleanup, account/trading endpoint, commit, push or deployment is part of C1.

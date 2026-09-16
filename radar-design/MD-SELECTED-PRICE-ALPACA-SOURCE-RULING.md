# Selected-price Alpaca source acceptance ruling

Date: 2026-09-16  
Decision: **PASS C0 — Alpaca Basic consolidated SIP is accepted for C1**  
Scope: owner-only Radar selected-instrument charts; local planning only

## Evidence accepted

The Mastermind accepts `MD-SELECTED-PRICE-ALPACA-VALIDATE-1-RETURN.md` and its sanitized evidence directory `artifacts/md-selected-price-alpaca-validate-1/` as satisfying the C0 validation gate. The ledger contains 11 bounded, read-only requests. It parses as JSON, contains no credential/header values, and agrees with the human-readable return. Ten requests returned HTTP 200 and the deliberately unknown asset returned the expected HTTP 404. No permission, throttle, retry, proxy, cookie, trading, account or billing behavior was exercised.

The evidence proves the exact role needed by Radar:

- Alpaca Market Data Basic serves delayed consolidated SIP historical bars for the representative US-equity set AAPL, SPY, FT, RZLV and `BRK.B`.
- Those instruments resolved as active `us_equity`; Radar remains the authority for the pinned US/USD instrument identity because the asset response does not carry currency.
- Single-symbol 1D one-minute and 1W five-minute requests return strictly increasing RFC-3339 bar-start timestamps and positive numeric closes. Missing trade minutes are omitted, not encoded as null or zero.
- The single-symbol AAPL week completed with 847 bars and no page token. The multi-symbol experiment paginated, so C1 must remain single-symbol and must reject, rather than silently truncate or paginate, any response with a non-null `next_page_token`.
- SIP is the accepted source. IEX is a materially partial tape and is not part of C1.
- The observed 200-request/minute account limit leaves ample room for Radar's enforced maximum of two chart requests per minute.
- The owner has accepted the Basic plan's delay and Radar has one owner/user, closing the audience decision for this product gate.

## Binding source contract

C1 may add one Alpaca adapter behind the existing isolated chart-acquisition child. Its role is narrowly bounded to the selected, pinned US/USD instrument and the requested 1D or 1W chart. It must not feed ranking, headlines, polling, shared quote storage or a universe-wide collector.

Use the historical bars endpoint with exactly one symbol per request, `feed=sip`, `adjustment=raw`, `sort=asc`, and `limit=10000`. Use one provider request per child execution. Do not paginate, retry, follow redirects, fall through to IEX or combine providers.

For a live or recently closed window, clamp the request end to `min(contract_end, now_utc - 16 minutes)`. The extra minute is an intentional safety margin over the documented 15-minute Basic delay. If the clamped end is not later than the requested start, do not call Alpaca; return the existing truthful unavailable/fallback state. Historical closed windows older than the clamp retain their contract end.

The adapter must require all of the following before normalizing a provider series:

1. HTTP success and a bounded JSON body.
2. An exact returned bars key equal to the requested Alpaca symbol.
3. Strictly increasing, parseable timestamps and finite positive close values.
4. No non-null `next_page_token`.
5. Every accepted timestamp lies inside an existing half-open contract interval.

An empty or absent symbol series is `empty`, never a zero-price series. A page token is `truncated` and falls back coherently. Authentication/permission, throttle, malformed, timeout/network and server failures retain distinct internal classifications without exposing secrets. A too-recent SIP refusal is treated as source-unavailable for that acquisition, not as permission to retry or switch feeds.

Runtime asset lookup is deliberately excluded from C1. The validation asset calls proved symbol behavior, including `BRK.B`; making another asset call for every chart would add traffic without improving Radar's already pinned identity. C1 must preserve the exact class-share symbol form and validate the bars response key instead.

## Closing-minute ruling

The existing half-open interval semantics remain binding. Request `end` may be inclusive at the provider boundary, but normalization clips observations against Radar's intervals.

- A 1W regular session is `[regular_open, regular_close)`. A bar timestamped exactly at 20:00:00Z for the validated session is outside that regular interval and must not be labeled or joined as a regular-session observation.
- A 1D extended-hours window already classifies `[regular_close, market_close)` as after-hours. The same 20:00:00Z timestamp may therefore be retained as an after-hours observation when it lies inside that 1D interval, with an explicit regime/state boundary. It must not be joined to the regular-session segment.
- No change to market-calendar close times, no special timestamp subtraction and no silent relabeling are authorized.

This keeps provider timestamp semantics intact and makes rendering behavior follow Radar's existing market-state contract.

## Product and operational boundaries

- The accepted renderer connects actual reported observations only within a compatible hard segment, adds a subtle area fill, and keeps one latest marker. It does not create inspectable interpolated values.
- A hard segment changes at least on market session, market state or source/regime. No line or fill crosses one of those boundaries.
- The current stored-series fallback remains whole and coherent. Provider and stored points are never spliced into one series.
- The new provider source is labeled `alpaca_sip`, with raw adjustment and delayed consolidated-SIP provenance. The chart must not imply real-time data.
- Add a separate `RADAR_SELECTED_PRICE_ALPACA_ENABLED` flag, default off. Existing selected-chart enablement remains separate. The historical Yahoo source flag stays off and is not reused as the Alpaca switch.
- Only `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` may cross from the parent environment into the isolated child, in addition to the existing platform minimum. Values must never enter logs, errors, response payloads, fixtures or artifacts.
- C1 does not authorize live requests, credential inspection, provider activation, production changes, database/schema changes, deployment, commit or push.

## Limitations carried into C1

The validation was conducted while the market was closed. It did not directly observe the live clamp, a too-recent refusal, authentication failure, throttling or provider 5xx behavior. C1 must cover those paths with deterministic tests and sanitized fixtures, not new live probes. Validation also found an undocumented practical multi-symbol response/page boundary; C1 avoids it structurally by allowing one symbol only.

With these constraints, C0 is closed as passed. `MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`, `MD-SELECTED-PRICE-ALPACA-C1-PLAN.md` and `MD-SELECTED-PRICE-ALPACA-C1-PROMPT.md` form the implementation packet. The packet is prepared, not dispatched.

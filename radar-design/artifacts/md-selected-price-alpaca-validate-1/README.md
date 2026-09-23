# MD-SELECTED-PRICE-ALPACA-VALIDATE-1 — sanitized evidence

Researcher / Verifier, 2026-09-16. Provider requests were made between 2026-09-16 00:36:49 UTC and 00:38:05 UTC (02:36–02:38 CEST), while the US market was closed. Every request was sequential, single-attempt, `timeout=15`, fixed headers (`Accept: application/json`, `User-Agent: radar-selected-price-validate/1`, the two documented `APCA-API-*` headers), `allow_redirects=False`, `trust_env=False` (no proxy/netrc), no cookie, no browser session, no retry. Credentials were read from the private root `.env` by variable name inside the script and never printed, copied, persisted or returned; `request-ledger.json` was checked programmatically to contain neither value.

**Provider request count: 11 of the 12 allowed. No 401, 403 or 429 occurred; nothing was stopped early.**

What is saved here: this README and `request-ledger.json` (per-request sanitized summary: sanitized URL, UTC send time, HTTP status, elapsed, byte count, content type, the numeric `X-RateLimit-Limit` / `X-RateLimit-Remaining` values, and computed per-symbol statistics). No raw authenticated body, no request header, no response header other than the two numeric rate-limit values, and no account identifier is stored. The ledger keeps only first/last timestamps and first/last/min/max closes per symbol, not the price series.

## Request ledger

| # | Sent (UTC) | Request (sanitized) | HTTP | ms | bytes | RL limit/remaining |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 00:36:49 | `GET paper-api.alpaca.markets/v2/assets/AAPL` | 200 | 675 | 451 | 200/199 |
| 2 | 00:36:50 | `GET paper-api.alpaca.markets/v2/assets/SPY` | 200 | 104 | 486 | 200/198 |
| 3 | 00:36:50 | `GET paper-api.alpaca.markets/v2/assets/FT` | 200 | 102 | 464 | 200/197 |
| 4 | 00:36:50 | `GET paper-api.alpaca.markets/v2/assets/RZLV` | 200 | 103 | 460 | 200/197 |
| 5 | 00:36:50 | `GET paper-api.alpaca.markets/v2/assets/BRK.B` | 200 | 103 | 453 | 200/196 |
| 6 | 00:36:50 | `GET data.alpaca.markets/v2/stocks/bars?symbols=AAPL,SPY,FT,RZLV,BRK.B&timeframe=1Min&start=2026-09-15T13:30:00Z&end=2026-09-15T20:00:00Z&feed=sip&adjustment=raw&sort=asc&limit=10000` | 200 | 1059 | 170,190 | 200/199 |
| 7 | 00:36:51 | same, `timeframe=5Min&start=2026-09-09T13:30:00Z&end=2026-09-15T20:00:00Z` (five modeled sessions) | 200 | 598 | 265,815 | 200/199 |
| 8 | 00:36:52 | same as #6 with `feed=iex` | 200 | 1098 | 122,858 | 200/199 |
| 9 | 00:36:53 | `…/v2/stocks/bars?symbols=ZZZZQX&timeframe=1Min&start=2026-09-15T13:30:00Z&end=2026-09-15T20:00:00Z&feed=sip&adjustment=raw&sort=asc&limit=1` | 200 | 114 | 34 | 200/199 |
| 10 | 00:38:04 | `…/v2/stocks/bars?symbols=AAPL&timeframe=5Min&start=2026-09-09T13:30:00Z&end=2026-09-15T20:00:00Z&feed=sip&adjustment=raw&sort=asc&limit=10000` (single-symbol week, the adapter's real per-chart shape) | 200 | 790 | 91,802 | 200/199 |
| 11 | 00:38:05 | `GET paper-api.alpaca.markets/v2/assets/ZZZZQX` | 404 | 666 | 56 | 200/199 |

`BRK-B` was never requested: `BRK.B` resolved on the first attempt, so the alternative spelling was not needed. Requests 10 and 11 are additions inside the 12-request budget, one attempt each, made to settle two ambiguities the first nine requests exposed (multi-symbol pagination; unknown-symbol envelope on the identity path). No request approached the documented 15-minute SIP boundary: the newest `end` was 2026-09-15T20:00:00Z, more than four hours old at request time. No trading, order, account, billing, plan or any mutating endpoint was called.

## Aggregate results

### Identity (requests 1–5, 11)

| Symbol | class | exchange | status | tradable | name (as returned) |
| --- | --- | --- | --- | --- | --- |
| AAPL | us_equity | NASDAQ | active | true | Apple Inc. Common Stock |
| SPY | us_equity | ARCA | active | true | State Street SPDR S&P 500 ETF Trust |
| FT | us_equity | NYSE | active | true | Franklin Universal Trust Shares of Beneficial Interest |
| RZLV | us_equity | NASDAQ | active | true | Rezolve AI PLC Ordinary Shares |
| BRK.B | us_equity | NYSE | active | true | BERKSHIRE HATHAWAY Class B |
| ZZZZQX | — | — | — | — | HTTP 404 `{"code":40410000,"message":"asset not found for ZZZZQX"}` |

Asset object keys returned (excluding `id`): attributes, borrow_status, class, easy_to_borrow, exchange, fractionable, maintenance_margin_requirement, margin_requirement_long, margin_requirement_short, marginable, name, shortable, status, symbol, tradable. **There is no `currency` field on the asset object.** The symbol is echoed exactly as requested (dot form for the class share). Exchange values are Alpaca's own names (NASDAQ, NYSE, ARCA), not ISO MICs.

### 1D consolidated SIP, last completed regular session 2026-09-15 (request 6)

`start=13:30:00Z`, `end=20:00:00Z`, 1Min, raw, asc, limit 10000. Response top-level keys: `bars`, `next_page_token` (null). No `currency` key in the response. `bars` is an object keyed by the requested symbol; each bar has exactly `c h l n o t v vw`.

| Symbol | bars | first `t` | last `t` | inside [13:30,20:00) | bar at exactly 20:00:00Z | strictly increasing | null close | zero/negative close | zero volume | off grid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | 391 | 13:30:00Z | 20:00:00Z | 390 | 1 | yes | 0 | 0 | 0 | 0 |
| SPY | 391 | 13:30:00Z | 20:00:00Z | 390 | 1 | yes | 0 | 0 | 0 | 0 |
| BRK.B | 390 | 13:30:00Z | 19:59:00Z | 390 | 0 | yes | 0 | 0 | 0 | 0 |
| RZLV | 385 | 13:30:00Z | 20:00:00Z | 384 | 1 | yes | 0 | 0 | 0 | 0 |
| FT | 65 | 13:30:00Z | 20:00:00Z | 64 | 1 | yes | 0 | 0 | 0 | 0 |

Observed semantics: `t` is the bar START, RFC-3339 with a `Z` suffix and whole seconds in every returned bar (the documentation reserves nanosecond precision, so a parser must accept fractional seconds). Minutes without an eligible trade are simply ABSENT from the array; there is no null bar and no zero close anywhere in 1,622 bars, so "unavailable" is absence and zero never appears as a price. `end` is inclusive: a bar with `t == end` was returned for four of five symbols. That 20:00:00Z bar is the 16:00 ET minute (closing auction print), which the modeled contract classifies as `afterhours` rather than `regular`. FT's 64 regular-minute bars equal the 64 regular-session observations Yahoo and Nasdaq returned for the same session on 2026-09-15 (saved DIAGNOSIS evidence); AAPL's 390 equals Yahoo's 390/390.

### 1W consolidated SIP, five modeled sessions 2026-09-09 … 2026-09-15 (requests 7 and 10)

Multi-symbol request 7 (5 symbols, 5Min, extended hours inside the span because `start`/`end` bracket the whole week): **paginated**. It returned 2,576 bars / 265,815 bytes with a non-null `next_page_token` although `limit=10000`; SPY was cut at 2026-09-10T08:05:00Z (127 bars) while RZLV (761), AAPL (847), BRK.B (634) and FT (207) were complete. The documentation says only that the API "may return less, even if there are more available data points" and that the limit applies to total data points; the actual page cap observed here is undocumented (the byte count sits just above 256 KiB).

Single-symbol request 10 (AAPL alone, same window): 847 bars / 91,802 bytes, `next_page_token` null, identical AAPL statistics to request 7. Per regular session: 78/78/78/78/78 bars for AAPL, SPY (session 09-09 only, before the cut), BRK.B and RZLV; FT 43/38/33/42/45. Each session also returned exactly one bar at its 20:00:00Z close instant (five per complete symbol). Extended-hours bars outside regular sessions: AAPL 452, RZLV 366, BRK.B 239, FT 1. All symbols strictly increasing, no null/zero close, no off-grid timestamp.

### IEX partial tape, same 1D window (request 8)

| Symbol | IEX bars | SIP bars (req. 6) | IEX first `t` | IEX last `t` |
| --- | --- | --- | --- | --- |
| AAPL | 390 | 391 | 13:30:00Z | 19:59:00Z |
| SPY | 391 | 391 | 13:30:00Z | 20:00:00Z |
| BRK.B | 320 | 390 | 13:30:00Z | 19:59:00Z |
| RZLV | 80 | 385 | 13:31:00Z | 19:59:00Z |
| FT | 5 | 65 | 13:34:00Z | 19:58:00Z |

IEX is a single-exchange tape: FT has 5 IEX minutes against 65 consolidated, RZLV 80 against 385. Closes differ from SIP closes for the same minute (e.g., AAPL first close 331.04 vs 331.03). IEX bars cannot be merged into the SIP series; they are a separate regime.

### Empty / error behaviour (requests 9 and 11)

- Bars for a nonexistent symbol: **HTTP 200**, body `{"bars":{},"next_page_token":null}` (34 bytes). The unknown symbol is not an error on the bars endpoint; its key is simply absent from `bars`.
- Asset lookup for a nonexistent symbol: **HTTP 404**, `{"code":40410000,"message":"asset not found for ZZZZQX"}`.
- Not observed on purpose: the documented "subscription does not permit querying recent SIP data" refusal (FAQ example code 42210000), 401/403/429 and 5xx.

### Quota (observed and documented)

Every response carried `X-RateLimit-Limit: 200`; `X-RateLimit-Remaining` moved 199 → 196 across the five asset calls within one second and showed 199 on each market-data call. Official documentation (accessed 2026-09-16 00:34 UTC): "Historical API calls 200 / min" for the Basic plan.

## Official sources rechecked 2026-09-16 00:34 UTC

- https://docs.alpaca.markets/docs/about-market-data-api — Basic: "US Stocks & ETFs", real-time "IEX", "Historical data limitation* latest 15 minutes", "Historical API calls 200 / min"; "The Basic plan serves as the default option for both Paper and Live trading accounts, ensuring all users can access essential data with zero cost."
- https://docs.alpaca.markets/docs/market-data-faq — "For historical queries, the end parameter must be at least 15 minutes old to query SIP data without a subscription. The default value for feed is always the 'best' available feed based on the user's subscription."; error text "subscription does not permit querying recent SIP data" (example `{"code":42210000,…}`).
- https://docs.alpaca.markets/reference/stockbars — `end` default: "the current time if the user has a real-time access for the feed, otherwise 15 minutes before the current time"; `limit` 1–10000 default 1000, "The API may return less, even if there are more available data points in the requested interval. Always check the next_page_token for more pages. The limit applies to the total number of data points, not per symbol!"; `adjustment` defaults to raw; `currency` query parameter "ISO 4217 format. Default: USD"; 429 "Use the X-RateLimit-... response headers".
- https://docs.alpaca.markets/reference/get-v2-assets-symbol_or_asset_id — `GET https://paper-api.alpaca.markets/v2/assets/{symbol_or_asset_id}`, 200 Asset object, 404 Not Found.
- https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf (27,092 bytes, text recovered by inflating the content streams; no effective date in the text) — unchanged from the 2026-09-16 excerpts: "Alpaca offers a 'Basic' market data plan, which is made available at no cost"; "you agree to use the Services and Content solely for your own personal and non-commercial purposes. Should you wish to use the Services and Content for any other purposes, including without limitation commercial usage, or making the Services and Content available to others through your own application (a 'User Application'), you shall provide Alpaca with 30 days advance written notice prior to making such User Application available to others."

Fetched page copies live only in the session scratchpad and are not part of the repository.

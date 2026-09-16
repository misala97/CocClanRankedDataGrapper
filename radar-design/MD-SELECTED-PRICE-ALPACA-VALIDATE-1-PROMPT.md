# Copy/paste prompt — MD-SELECTED-PRICE-ALPACA-VALIDATE-1

```text
You are Radar's Researcher / Verifier. Return your result to the Mastermind.

Assignment ID: MD-SELECTED-PRICE-ALPACA-VALIDATE-1

Objective:
Close or reject selected-price gate C0 for Alpaca Market Data Basic using the owner's new free Paper Only account. Validate the already documented path with bounded credentialed requests. This is verification only: no adapter, UI, application, test, configuration, schema, provider activation, commit, push or deployment work.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Expected branch/base/HEAD:
codex/radar-selected-price-charts
f632e5db5dd92e27480cbfccdf7b0638b26533ed

Before acting:
- Verify branch, HEAD, origin/main, status, diff and recent log with per-command safe.directory.
- Preserve every dirty/untracked file and every protected environment.
- Confirm only that APCA_API_KEY_ID and APCA_API_SECRET_KEY are present in the project's private root .env. Never print, copy, return, persist or expose either value.
- If either name is absent, stop without provider requests and return BLOCKED: credentials not locally configured.
- Do not modify the .env or any credential store.

Read fully:
1. radar-design/WORKFLOW.md
2. radar-design/MD-SELECTED-PRICE-AREA-DATA-PLAN.md
3. radar-design/MD-SELECTED-PRICE-FREE-DATA-PATH-1-RETURN.md
4. radar-design/MD-SELECTED-PRICE-FREE-DATA-PATH-1-RULING.md
5. radar-design/MD-SELECTED-PRICE-ALPACA-OWNER-DECISION.md
6. radar-design/artifacts/md-selected-price-free-data-path-1/documentation-excerpts.md
7. personal_apps/features/radar/price_chart_contract.py
8. personal_apps/features/radar/price_chart_fetch.py
9. personal_apps/features/radar/price_chart_acquisition.py

Binding owner decisions:
- Radar is owner-only.
- A consolidated SIP line delayed by at least 15 minutes is acceptable.
- Alpaca Basic is the chosen path to validate.
- The IEX live tail is a partial tape and must remain a separate regime; it is optional for first implementation and must never be silently spliced into SIP.
- EUR0, US-primary/native-USD and no paid plan remain binding.

Request safety:
- Maximum 12 Alpaca provider requests total, sequential, one attempt per request shape, no retries.
- Timeout <=15 seconds per request; ordinary fixed headers; no proxy, cookie, browser session or workaround.
- Stop all provider calls immediately on 401, 403 or 429 and report the sanitized status/error class.
- Never print full request headers, credential-bearing commands, response headers containing account identifiers, or secret values.
- Save only sanitized summaries. Do not save raw authenticated responses.
- Use historical SIP end <= now minus 16 minutes to stay outside the documented 15-minute restriction without probing the boundary.
- No trading/order/account mutation endpoint. Market-data and read-only asset-reference endpoints only.

Required validation matrix:
1. Account/entitlement: authenticated Basic market-data access works at EUR0. Do not query billing or mutate plans. Record only the observed entitlement behavior, not account identifiers.
2. Identity: use Alpaca's read-only asset reference for AAPL, SPY, FT, RZLV and the accepted Berkshire class-B spelling. Establish symbol echo, asset class, exchange, active status and native USD assumption boundary. Try BRK.B and BRK-B at most once each only as needed to settle spelling.
3. Current/recent 1D SIP: one multi-symbol 1Min bars request for the most recent regular session, raw adjustment, ascending order, end <= now-16m. Record per symbol: HTTP class, returned symbol key, count, first/last timestamp, strict monotonicity, null/zero distinction and whether timestamps lie inside the modeled regular session. Do not reproduce the full price series.
4. 1W SIP: one bounded multi-symbol 5Min request covering five modeled sessions. Record counts/session coverage and pagination state.
5. Partial-tape comparison: at most one equivalent IEX request. Record only counts and first/last timestamps. State explicitly that it cannot be merged into SIP.
6. Empty/error behavior: one clearly nonexistent symbol through the least expensive read-only shape. Record sanitized HTTP/envelope semantics. Do not manufacture rate-limit or permission errors.
7. Quota/budget: confirm current official 200/minute Basic documentation and compare it with Radar's <=2 requests/minute worst-case two-worker budget. Do not load-test.
8. Terms/audience: recheck current official personal/non-commercial and user-application language. The owner-only fact closes the audience issue for this engineering gate; report any changed wording.

Pass conditions:
- Authentication succeeds without paid entitlement.
- Representative AAPL, SPY, FT, RZLV and one class-B Berkshire symbol resolve unambiguously as active US equities/ETF as applicable.
- The recent regular-session SIP request returns timestamped actual bars for the representative set, with unavailable distinguishable from price zero.
- Exact bar timestamp and close semantics, symbol spelling, empty/error behavior and pagination are observed rather than inferred.
- The 15-minute clamp and <=1 visible refresh/minute design fit the documented entitlement/quota.
- No permission, identity, entitlement or response-shape ambiguity remains that would change the adapter contract.

Fail closed:
- Any paid-plan requirement, account ineligibility, permission contradiction, unresolved identity/class-share behavior, unusable representative coverage, or undocumented response ambiguity that affects the adapter means FAIL C0. Do not recommend implementation around it.

Deliverables:
- Create radar-design/MD-SELECTED-PRICE-ALPACA-VALIDATE-1-RETURN.md.
- Create radar-design/artifacts/md-selected-price-alpaca-validate-1/README.md containing the sanitized request ledger, request count, UTC timestamps, official URLs/access dates and aggregate results.
- Add other sanitized small artifacts only if necessary; no raw authenticated bodies.
- Update only the current notices in radar-design/MD-SELECTED-PRICE-LEDGER.md and root HANDOFF.md. Preserve historical text.
- Final recommendation must be exactly one of:
  - PASS C0 — PREPARE ALPACA C1 PACKET
  - FAIL C0 — USE STORED-ONLY RENDERER
  - BLOCKED — <one concrete reason>

Stop when the Mastermind can name the exact authenticated Basic entitlement, accepted symbols/identity checks, actual 1D/1W response semantics, traffic budget, delay, error behavior and remaining limitations without inference. Do not implement or activate anything.

Your final response must end with a complete copy/paste prompt returning the actual workspace/Git state, all dirty ownership, exact provider request count, sanitized results/evidence paths, evidence attribution, PASS/FAIL/BLOCKED recommendation, protected state and the one requested Mastermind decision. Tell the Mastermind to verify Git/artifacts and update planning continuity without implementing, deploying, activating a provider or dispatching workers automatically.
```

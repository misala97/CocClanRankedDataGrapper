# MD-SELECTED-PRICE-ALPACA-C1 — Implementer return

2026-09-16, Implementer (Claude Opus 5, no subagents). Return to the Mastermind.

**Outcome: COMPLETE as a locally verified, uncommitted candidate. Every C1
acceptance condition in `MD-SELECTED-PRICE-ALPACA-C1-SPEC.md` §"Acceptance
tests" is satisfied by executed tests and inspected screenshots, with the
limitations in §7 below.** No live provider request, no activation, no
configuration, database, production, service, commit, push or deploy action.
The new flag is off.

Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`,
branch `codex/radar-selected-price-charts`, HEAD = base = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed` (verified before and after the work).
All pre-existing dirty and untracked files preserved.

## 1. Changed and generated files

**New application code**

| File | Why |
| --- | --- |
| `personal_apps/features/radar/prices/alpaca.py` | The only module that knows Alpaca's bars JSON: fixed HTTPS host, one symbol per request, `trust_env=False`, blocked cookie jar, `allow_redirects=False`, chunked body bound, no retry, no pagination. Credentials are read BY NAME at the last responsible point inside the one request and become the two documented headers; the instance holds none and its `__repr__` is explicit so no default repr can ever grow one. |

**Modified application code** (smallest delta that satisfies the ruling)

| File | Change |
| --- | --- |
| `features/radar/price_chart_contract.py` | `ALPACA_SOURCE`/`ALPACA_REGIME`/`PROVIDER_PROFILES`; `alpaca_symbol` (dot form preserved); `alpaca_request_spec` with the 16-minute clamp and three refusal codes; `request_spec_for`; `cache_key(..., source=)`; `spec_ok`/`_alpaca_spec_ok`; `normalize_alpaca`; `provider_points`/`provider_price`/`provider_warnings` (source-dispatched, replacing the Yahoo-named entry points); a `segment` hard key on every point, including both stored fallbacks; `observations` and `expected_intervals` on every price block; `expected_intervals(window)`; `provider_symbol_supported`. |
| `features/radar/price_chart_fetch.py` | Dispatches on `spec['source']`; `_run_alpaca` (empty clamp → deterministic `waiting` with no HTTP call; missing credentials → `credentials_missing` with no HTTP call); `classify_alpaca` (credentials / timeout / network / redirect / oversized / invalid_body / too-recent-SIP `waiting` / 401-403 `permission` / 429 `throttle` with Retry-After / 404 `unsupported` / 5xx / normalize). |
| `features/radar/price_chart_acquisition.py` | `CREDENTIAL_ENV` and its two names added to `child_environment` (blank = absent); `get_or_start(..., source=)` building the admitted source's spec and a source-scoped cache key; `selected_source()`; `Admission` requiring charts AND Alpaca AND credentials; new outcomes `truncated` / `waiting` / `permission` / `credentials_missing` with their own counters, cooldowns and reasons; a named backoff reason so a permission pause does not claim to be throttling; ops fields `alpaca_enabled`, `credentials_present`, `source`, `source_state`. |
| `features/radar/config.py` | `selected_price_alpaca_enabled()` — its own variable, default false, independent of both older flags in both directions. |
| `features/radar/price_chart_reader.py` | Three call sites moved to the provider-neutral helpers. No other change: the endpoint, identity, admission, bounded SQL, local cache, chatter, tone and fallback selection are untouched. |
| `static/radar/src/hub/priceChart.ts` | `segment` on `PricePoint`, `observations`/`expected_intervals` on `PriceSeries`, validated at the boundary (including `observations` reconciling to the non-null points); the four new optional `SelectedPriceOps` fields. |
| `static/radar/src/hub/selectedPriceGeometry.ts` | `priceSegments` replaces `priceRuns`; `areaPathOf`; compact lane constants (912x306); `coverageWord`; `alpaca_sip` source wording. |
| `static/radar/src/hub/SelectedPriceChart.tsx` | One line and one baseline-closing gradient area per multi-point hard segment, a dot for a one-observation segment, exactly one latest marker; a per-instance gradient id; coverage on the provenance line and in the summary; the pan opens on the latest actual observation. |
| `static/radar/src/hub/selected-price.css` | The area class and its two gradient stops in the price token; the canvas aspect ratio follows the new lane proportions. |
| `static/radar/src/hub/Admin.tsx` | "Chart / Alpaca switch", an effective source state in words, and whether the credential variables hold anything — never what. |

**Tests and fixtures**: `tests/selected_price_unit/test_alpaca_bounded.py` (new);
extended `test_normalize.py`, `test_window.py`, `test_acquisition.py`,
`test_launcher_isolation.py`, `test_route_ops.py`, `test_reader.py`,
`helpers.py`, `probe_child.py`; extended `priceChart.test.ts`,
`priceChartFixtures.ts`, `selectedPriceGeometry.test.ts`,
`SelectedPriceChart.test.tsx`, `Admin.test.tsx`.

**Generated**: `static/radar/dist` through the repository's normal build
(Git-ignored).

**Evidence**: `radar-design/artifacts/md-selected-price-alpaca-c1/`
(`evidence.md`; `browser/fixtures.py`, `browser/verify_browser.py`,
`browser/fixtures/`, `browser/results.json`, `browser/screenshots/` — 96 PNGs).

**Continuity**: this return, plus one new CURRENT notice prepended to
`radar-design/MD-SELECTED-PRICE-LEDGER.md` and root `HANDOFF.md`.

## 2. Source behaviour implemented

**Request.** One `GET https://data.alpaca.markets/v2/stocks/bars` per child, for
exactly one symbol: `symbols=<pinned ticker, dot form preserved>`,
`timeframe=1Min|5Min`, `feed=sip`, `adjustment=raw`, `sort=asc`, `limit=10000`,
`start` = the contract window start, `end` = `min(window end, now_utc - 16 min)`
in RFC-3339 Z. 1D uses one-minute bars over the extended-hours intervals, 1W
five-minute bars over the five regular sessions. No batch symbols, pagination,
retry, redirect, ambient proxy, cookie, IEX fallback, asset lookup or automatic
source switching. If the clamp leaves `end <= start`, no request is built at
all: admission answers `unavailable` with "delayed consolidated SIP data does not
reach this window yet", and the child re-checks and answers `waiting` without an
HTTP call.

**Normalization.** Exactly one bars key, equal to the requested symbol (anything
else is `identity_mismatch`); a non-null `next_page_token` is `truncated`, never
a completed answer; `t` is the bar START, parsed as RFC-3339 with fractional
seconds accepted and truncated to microseconds; timestamps must be strictly
increasing; a close that is null, non-numeric, non-finite, zero or negative
invalidates the whole answer, because Alpaca OMITS a minute it has nothing for.
Off-grid and out-of-interval bars are counted and dropped. Missing minutes stay
missing — no placeholder, no forward fill, no zero. An empty `bars` map or an
empty symbol list is `empty`.

**Closing minute.** Half-open intervals decide it, with no calendar change and no
timestamp arithmetic: the 20:00:00Z bar is outside `[regular_open, regular_close)`
so 1W drops it, and inside the 1D extended `[open, close)` so 1D keeps it,
classified `afterhours` — which gives it a different `segment` key and therefore
a new hard segment. Verified in unit tests and visible in
`sparse_1d-*`/`chatter_gaps-*` as one 64-point line plus one separate dot.

**Failure.** `disabled`, `credentials_missing`, `waiting`, `empty`, `truncated`,
`invalid`, `permission`, `throttle`, `timeout`, `upstream_error` and
`identity_mismatch` are distinct internally, each with its own counter, cooldown
and human reason. A too-recent SIP refusal (documented code 42210000) is
`waiting`: a 60-second cooldown for that chart, no retry and no throttle ladder.
Permission opens the provider-wide ladder but says it is a credential refusal,
not throttling. Only a fully valid result is stored and published; on every
other result the reader serves ONE complete stored series (1D quotes, else daily
closes; 1W daily closes) with its own source, cadence and coverage labels, or a
truthful absence. Provider and stored points are never mixed — proved by
`test_a_provider_series_is_never_spliced_with_a_stored_point`.

**Identity.** `RadarInstrument` remains the authority: pinned US market, USD,
canonical ticker, MIC. `BRK.B` stays `BRK.B` and is sent exactly. The returned
bars key is an additional integrity check. No runtime asset call.

## 3. Secret isolation and default-off flags

- Child environment = platform minimum + exactly `APCA_API_KEY_ID`,
  `APCA_API_SECRET_KEY` (blank treated as absent). An end-to-end test starts a
  real parent whose `__main__` is a file path with unguarded top-level code,
  carrying sentinel credentials, a decoy secret and Python/proxy overrides; the
  child reports SHA-256 **digests**, never values — both sentinels arrive intact,
  the decoy does not, `argv_carries_a_credential` is false, and its whole
  environment is a subset of allowlist + credentials.
- No sentinel appears in the Popen argument array, the request spec, stdout, the
  result envelope, an error, a log line or the ops snapshot; a 403/429/422 result
  carries neither a sentinel nor the provider's own message text.
- A scan of all 1,584 worktree text files for the REAL values read from the
  private root `.env` found **0 occurrences**; the values were compared in memory
  and never printed. The `.env` is unmodified and was never otherwise read.
- With no selected-price variable set: `charts False yahoo False alpaca False`,
  `selected_source (None, 'charts_off')`, `Admission -> disabled`, and no
  coordinator is created. Acquisition needs charts AND Alpaca AND both
  credential names. The historical Yahoo flag is untouched and no longer
  authorizes Alpaca.

## 4. Commands and exact results

Failing-first records for all five test groups, and every command with its
counts, are in `radar-design/artifacts/md-selected-price-alpaca-c1/evidence.md`.
In short, from `personal_apps`:

| Command | Result |
| --- | --- |
| `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **239 passed** (173 at base) |
| the same under an outbound-socket guard | **239 passed**, `OUTBOUND ATTEMPTS: []` |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | **269 passed, 1 skipped, 3 failed** — the same three date-dependent `test_daily_closes_*` baseline failures |
| `npx vitest run -c vite.radar.config.ts` | **876 passed, 28 failed** — the same 28 pre-existing `pending.test.tsx` failures |
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | passed; `assets/hub-BAY3z_IW.js`, `assets/hub-Czy1AMuW.css` |
| `py -3.12 -u radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py` | **37 cases, 850 checks, 0 failures**, 0 unmocked requests, 87 s, port free afterwards |

## 5. Screenshots and visual findings

96 PNGs in `radar-design/artifacts/md-selected-price-alpaca-c1/browser/screenshots/`,
all viewed. Key frames:

- `sparse_1d-research-1200.png` — FT's 64 actual reported minutes as ONE calm
  cyan line with a subtle fill, the 20:00:00Z closing bar as its own dot, real
  chatter beneath, "65 of 960 reported".
- `sparse_1d-research-390-chart.png` — the same at phone width, opening on the
  price rather than on empty after-hours.
- `week_1w-research-1200.png` — five separate filled session segments, nothing
  drawn or filled across a night.
- `dense_1d-research-1200.png` — a liquid session reads as one calm area, not a
  dot cloud; the pre-market/regular boundary is the only break.
- `fallback_1d-research-1200.png` — stored Finnhub quotes in three segments
  split at a 90-minute hole and a state boundary, labelled as the fallback.
- `unavailable_1w-research-1200.png` — "No price inside this window · provider
  chart paused (the provider refused this process's credentials)", chatter still
  readable, no credential named.
- `zoom200-*-390css*.png` — real 200% zoom, readable, nothing clipped, no
  horizontal document overflow.

**Findings, with the one correction made.** Opening the pan at the newest end of
the WINDOW (the shipped behaviour) put FT's whole session off screen at 390 px
behind four empty after-hours hours, because a 1D window runs to the extended
close. The pan now opens on the latest actual observation, with a browser check
asserting the latest marker is visible. Three deliberate, disclosed differences
from the standalone preview remain, all inherited from the deployed contract
rather than reinterpretations: the 1D window is the extended session, not a
regular-session-only span; the shipped component carries a provenance/basis
block, legend, market-state bands, readout, accessible summary and data notes
that the preview never had; and the canvas stays 912 px wide and pans below that
width, which is the reviewed shipped behaviour rather than the preview's
full-bleed responsive drawing. Lane proportions were compacted toward the
preview (912x306; price lane 170, discussion lane 48). If the Mastermind or the
owner reads the pan-vs-responsive difference as a material departure, that is a
design decision to rule on, not something this task changed.

## 6. Remaining limitations and environmental failures

- **Live provider paths unobserved**: the intra-session clamp against a live
  session, a real too-recent-SIP refusal, real 401/403/429/5xx envelopes and real
  throttling. They are covered only by deterministic fixtures built from the
  shapes the 2026-09-16 validation recorded. The 422-plus-code-42210000 mapping
  to `waiting` is the documented form, not an observed one.
- **Baseline failures, unchanged by this work**: three date-dependent
  `test_radar_yahoo.py::test_daily_closes_*` failures (fixture timestamps older
  than that adapter's rolling date floor) and 28 pre-existing
  `hub/pending.test.tsx` failures.
- **Release carries unchanged**: POSIX/gunicorn child behaviour on the release
  host, MariaDB runtime and plans, DB-backed route suites, real worker topology.
- Browser evidence is fixture evidence: no database, no provider, no production.
- The `next_page_token` path is exercised only with a synthetic token; the real
  multi-symbol page cap is structurally unreachable because C1 is single-symbol.

## 7. Boundaries honoured

No live Alpaca (or any other provider) request; no credential value read outside
the in-memory scan described above, and none written anywhere; no flag
activation; no configuration, database, schema, migration, service, dependency
or production change; no commit, push or deployment; no second worktree, reset,
clean, stash or restore. Schema, shared quote persistence, headline/ranking/board
logic, HA1 and market identity beyond the selected chart are untouched. No
subagents.

Branch `codex/radar-selected-price-charts`; HEAD = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed`; `git diff --check` clean. Final dirty
status: 24 modified tracked files (7 pre-existing continuity documents plus root
`HANDOFF.md`, and the 16 application/test files this task owns), 2 new untracked
application/test files (`prices/alpaca.py`, `test_alpaca_bounded.py`), the new
`radar-design/artifacts/md-selected-price-alpaca-c1/` evidence directory, this
return, and all pre-existing untracked planning/research/release/preview/audit
artifacts preserved.

## 8. Recommendation

**ONE independent focused C2 review of this delta, not dispatched by me.** Scope
per the plan: source-contract compliance, child isolation and secrets,
one-call/no-pagination behaviour, observation preservation, segment breaks,
fallback truthfulness, real chatter, and the accepted desktop/mobile/zoom
presentation — including a ruling on the pan-versus-responsive difference above.
Production activation remains a separate owner decision even after a clean
review.

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Assess this Implementer return for assignment MD-SELECTED-PRICE-ALPACA-C1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / f632e5db5dd92e27480cbfccdf7b0638b26533ed / f632e5db5dd92e27480cbfccdf7b0638b26533ed (= origin/main; nothing committed or pushed)
Binding artifacts: .../radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md ; .../MD-SELECTED-PRICE-ALPACA-C1-SPEC.md ; .../MD-SELECTED-PRICE-ALPACA-C1-PLAN.md ; .../MD-SELECTED-PRICE-ALPACA-C1-RETURN.md ; .../artifacts/md-selected-price-alpaca-c1/evidence.md ; .../artifacts/md-selected-price-alpaca-c1/browser/results.json ; .../MD-SELECTED-PRICE-LEDGER.md

Outcome: COMPLETE as a locally verified, uncommitted candidate; every C1 acceptance condition satisfied by executed tests and inspected screenshots, with the stated limitations.

What was built: personal_apps/features/radar/prices/alpaca.py (new bounded single-symbol SIP transport) plus the smallest delta in price_chart_contract.py, price_chart_fetch.py, price_chart_acquisition.py, config.py, price_chart_reader.py, priceChart.ts, selectedPriceGeometry.ts, SelectedPriceChart.tsx, selected-price.css, Admin.tsx and their focused tests/fixtures. One request per child: symbols=<pinned ticker, dot form>, timeframe=1Min|5Min, feed=sip, adjustment=raw, sort=asc, limit=10000, end clamped to min(window end, now-16m); no pagination, retry, redirect, proxy, cookie, IEX or asset call. Normalization requires an exact single bars key, strictly increasing RFC-3339 timestamps (fractional seconds accepted), finite positive closes, and rejects any non-null next_page_token as truncated; missing minutes stay absent. The 20:00:00Z bar is excluded from 1W regular data and kept in the 1D extended window as a SEPARATE after-hours segment. RADAR_SELECTED_PRICE_ALPACA_ENABLED is a new independent flag, default false; admission needs charts AND Alpaca AND both credential names. The renderer draws one line and one baseline-closing gradient area per hard segment (market state + session date + source/regime), a dot for a one-observation segment, one latest marker and no dot cloud, over real chatter/tone.

Verification (worker-executed): selected_price_unit 239 passed, and 239 passed again under an outbound-socket guard with ZERO outbound attempts; tone/Yahoo/HA1 269 passed with the same 3 date-dependent baseline failures; whole Radar Vitest 876 passed with the same 28 pre-existing pending.test.tsx failures; tsc 0; npm run build passed (hub-BAY3z_IW.js); built-hub python-playwright 37 cases / 850 checks / 0 failures at 1200/768/390 CSS px plus REAL 200% zoom, 96 PNGs viewed. Failing-first records for all five test groups are in evidence.md.

Secrets: child environment = platform minimum + exactly APCA_API_KEY_ID and APCA_API_SECRET_KEY, proved end to end with sentinels and SHA-256 digests; no sentinel in arguments, spec, stdout, results, errors, logs or ops; a scan of all 1,584 worktree text files for the REAL .env values found 0 occurrences; .env unmodified.

One visual correction: the panned chart now opens on the latest actual observation instead of the newest end of the window, which at 390 px had put FT's whole session off screen behind four empty after-hours hours.

Disclosed differences from the standalone preview, all from the deployed contract: the 1D window is the extended session; the shipped component carries provenance/basis, legend, bands, readout, summary and data notes; the canvas stays 912 px and pans below that width instead of being full-bleed responsive. Lane proportions were compacted to 912x306.

Limitations: no live provider path was observed (intra-session clamp, real too-recent refusal, real 401/403/429/5xx, real throttling) — deterministic fixtures only; the 422 + code 42210000 -> waiting mapping is the documented form, not an observed one; POSIX/gunicorn, MariaDB runtime, DB-backed suites and real topology remain release carries; browser evidence is fixture evidence.

Actions taken: application/test/build changes listed above; created radar-design/artifacts/md-selected-price-alpaca-c1/ and radar-design/MD-SELECTED-PRICE-ALPACA-C1-RETURN.md; prepended one CURRENT notice each to radar-design/MD-SELECTED-PRICE-LEDGER.md and root HANDOFF.md. Explicitly NO live provider request, flag activation, configuration, database, schema, migration, service, dependency, production, commit, push or deploy action; no second worktree, reset, clean, stash or restore; no subagents.
Protected state: production 194.164.29.97, databases, services, other worktrees, Remote Control sessions, saved credentials and provider flags (charts ON / Yahoo OFF / Alpaca OFF) untouched; all pre-existing dirty and untracked files preserved.
Requested Mastermind decision: accept this candidate for ONE independent focused C2 review, and rule on the pan-versus-responsive presentation difference described above.
Next bounded action recommendation: prepare the C2 reviewer prompt (source contract, child isolation/secrets, one-call/no-pagination, observation preservation, segment breaks, fallback truthfulness, real chatter, accepted desktop/mobile/zoom presentation). Do not redispatch this implementation, re-run the provider validation, activate the flag or deploy.
```

# MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW — fresh-session Reviewer/QA return

2026-09-16. This is the final independent C2 review of the whole uncommitted
selected-price Alpaca C1 candidate, including the C2-FIX corrections. It was
read-only for product and test code. The only repository write is this file.

## 0. Independence attestation

This review ran in a genuinely fresh task/session (Claude Opus 5). Before any
repository work, all three gate statements were confirmed true:

1. I did not implement `MD-SELECTED-PRICE-ALPACA-C1` in this session.
2. I did not perform the same-session `MD-SELECTED-PRICE-ALPACA-C2` review in this session.
3. I did not implement `MD-SELECTED-PRICE-ALPACA-C2-FIX` in this session.

No subagents were used. Every probe below was written and run by this reviewer.

## 1. Verdict

**ACCEPT C1 FOR OWNER ACTIVATION/DEPLOYMENT DECISION**

There are no Critical or Important findings. There are two Minor findings: one in
product code and one in the evidence harness only. Neither blocks acceptance.
This verdict does not authorize activation, a configuration change, a commit,
a push or a deployment.

## 2. Scope and candidate identity

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- HEAD: `f632e5db5dd92e27480cbfccdf7b0638b26533ed`, equal to `origin/main`
- Candidate: the uncommitted working tree
- Reviewed product delta:
  - tracked: `features/radar/{config,price_chart_acquisition,price_chart_contract,price_chart_fetch,price_chart_reader}.py`
    and `static/radar/src/hub/{Admin.tsx,SelectedPriceChart.tsx,priceChart.ts,selected-price.css,selectedPriceGeometry.ts}`
  - untracked: `features/radar/prices/alpaca.py`
- Reviewed focused tests:
  - backend: the selected_price_unit changes, plus untracked `test_alpaca_bounded.py`
  - frontend: `Admin`, `SelectedPriceChart`, `priceChart`, `priceChartFixtures` and `selectedPriceGeometry` tests
- Excluded: the pre-existing planning, research, release and preview documents and
  artifacts, and the continuity files. These are unrelated to this review.

## 3. Strengths

- **The source contract is structurally narrow.**
  - `prices/alpaca.py` has one path constant, `BARS_PATH`, and one fixed
    production host (`alpaca.py:35-37`). It does not mention IEX, assets, paper
    or trading endpoints.
  - The session disables proxy and netrc (`trust_env=False`, `:92`). Its cookie
    policy allows no domain (`:94`). It never follows redirects (`:118`).
  - The body is capped by the declared length and again while streaming (`:133`, `:139`).
  - Credentials are read by name inside the one request, and appear only in the
    two headers.
- **The 16-minute clamp is enforced twice.**
  - The parent never builds a request when the clamp leaves nothing
    (`price_chart_contract.py:423-425`).
  - The child answers `waiting` without any HTTP call (`price_chart_fetch.py:145`).
- **Hard segments come from the interval algebra, not from special cases.** Each
  point's `segment` is `state_at` (state plus session date) plus the regime
  (`price_chart_contract.py:721`). The half-open intervals (`:670`) exclude the
  exact close from 1W. In 1D, the same bar becomes its own after-hours segment.
  No calendar edit or timestamp subtraction is involved.
- **Fallback is never spliced.** The stored fallback is read or used only when no
  provider price exists (`price_chart_reader.py:408-431`). Both stored paths drop
  non-finite values before building points (`price_chart_contract.py:907-910`,
  `analysis_contract.py:273-276`). The new frontend `observations` check
  (`priceChart.ts:256`) therefore cannot reject a valid fallback.
- **Rendering adds no data.**
  - `priceSegments` groups actual non-null points by the server's key
    (`selectedPriceGeometry.ts:67`).
  - `areaPathOf` adds only two baseline vertices (`:92`).
  - Inspection resolves only to actual points through `pointsInSlot` and `latestValid`.
- **The pan ownership rewrite is sound in lifecycle terms.**
  - The listener is added before the first placement and removed on cleanup.
  - The refs survive effect re-runs. `readerMoved` resets only when the
    `ticker|span` identity changes.
  - `placing` is set only when an assignment will actually move the scroller
    (`SelectedPriceChart.tsx:293-325`).

## 4. Findings

### Critical

None.

### Important

None.

### Minor

**M1 — the C2-1 guard checks that `source` is a known source, not that it equals
the admitted source.** `personal_apps/features/radar/price_chart_acquisition.py:479`
(called at `:454`; its reason text is at `:482`).

What the independent in-process probe found, using the real `Coordinator` with a
real `threading.Thread`, the real reader and an in-process fake child:

- **An unhashable `source`** (`["alpaca_sip"]` or `{"x":1}`) raises
  `TypeError: unhashable type` inside `_settle`, on the supervisor thread.
  - `threading.excepthook` reports the error.
  - The `invalid` counter stays at 0 and no cooldown entry is written.
  - Nothing is cached, so the reader still serves the coherent stored fallback
    (`finnhub`, 3 observations) without a request-path exception.
  - Re-admission is still bounded by the 60 s per-key start interval (`backoff`,
    "this chart was acquired less than a minute ago").
  - `_inflight`, `_child`, latency and quarantine are all released before the raise.
- **A known source that differs from the admitted spec** (a `yahoo_chart` result
  answering an `alpaca_sip` request) is treated as valid.
  - It counts as `success` and is cached under the Alpaca cache key.
  - It is then served as a Yahoo-labelled series although only Alpaca is admitted.
  - The label is truthful to the result, but the source does not match the admission.
- **The refusal reason text is misleading.** For an unknown source it reads "the
  series exceeded its bound".

**Impact:** none of these is reachable today. The only writer of `source` is the
fixed child module. It picks its adapter from the spec's `source`, and each
`normalize_*` function stamps its own constant. The string, `null` and integer
forgeries named in the correction behave exactly as ruled (§6, C2-1). Severity is
Minor: the gap is defence in depth and counter accuracy only. There is no
request-path error, no cache entry, no unbounded retry and no exposure.

**Smallest fix (optional before release):**

1. Pass `spec` into `_settle`, e.g. `self._settle(key, spec, outcome, data)`.
2. Replace the membership clause with an equality test:
   `result.get('source', contract.YAHOO_SOURCE) != spec.get('source', contract.YAHOO_SOURCE)`.
   - Equality needs no hashing.
   - It subsumes the membership test, because a spec only ever carries a known source.
   - It keeps the historical missing-source default for Yahoo specs.
3. Optionally give this case its own reason text.
4. Add two unit tests:
   - `source: ["alpaca_sip"]`: counts `invalid`, caches nothing, backs off for 60 s;
   - a `yahoo_chart` result for an Alpaca spec: counts `invalid`.

**M2 (evidence harness only, not product) — the candidate harness does not prove
the data-refresh half of C2-3, and its 200% zoom "chart" frames do not show the drawing.**
`radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py:466-471`
and `:186-211`.

- The comment says "A refetch (new data object) and a resize both re-run the
  effect", but the code only resizes the viewport. Resizing triggers only the
  `ResizeObserver` path. It changes no dependency of the effect, so the effect's
  cleanup and re-run on new `data` was never exercised in a browser.
- `zoom200-sparse_1d-research-390css-chart.png` shows the header and provenance,
  with the plot only just starting at the bottom edge.
  `zoom200-sparse_1d-research-390css-focus.png` shows the quote card above the
  chart section.
- The return's claim "real 200% zoom, readable, nothing clipped" is therefore true
  only of what those frames show. The zoom checks in `results.json` (overflow,
  keyboard, focus, marker, gutter rule and `devicePixelRatio`) do pass.

**Impact:** the gap is in the evidence only. This review closed the refresh gap
with its own fake-clock refetch probe (§5, P4), and took layout-equivalent
DPR-2 element shots (§7).

**Smallest fix (optional):**

- In `run_reader_scroll_case`, install `page.clock` and call
  `fast_forward(61_000)` while serving a changed payload.
- Frame zoom captures on the chart element, for example with a clip.

### Pre-existing and out of scope (not C1 findings)

- `_settle` accepts a `NaN` or `Infinity` `received_at`, because `json.loads`
  allows them by default. The reader's `from_epoch` would then raise on the
  request thread. The `received_at` clause is unchanged from HEAD. It is also
  unreachable, because the child encodes with `allow_nan=False` and stamps
  `clock()`. Smallest hardening: add `math.isfinite`.
- The shape of a malformed bars element was already recorded in the first C2
  return as identical at HEAD.

### Notes, not findings

- **Credentials reach every child.** `child_environment` passes the two `APCA_*`
  variables to every child, including a historical Yahoo child that never reads
  them (`price_chart_acquisition.py:110-130`). The source ruling permits exactly
  these two names in the child, and the Yahoo flag is off. Least privilege would
  pass them only for Alpaca specs.
- **At 390 px the no-price message is off screen at rest.** In the unavailable
  1W state the pan opens at the rightmost position (`latestX === null`), so the
  in-plot "No price observation" text is not visible. The provenance line above
  states the absence. This is the same rightmost rule as before C1.
- **Timestamps of the saved evidence.** The PNGs and `results.json` (04:36-04:38)
  predate the current bundle file's mtime (04:41). The bundle has the same
  content-hashed name, `hub-Dycy3Xpo.js`, which `results.json` records. This
  review's own browser probes ran against the current bundle.

## 5. Commands and exact results (all run by this reviewer)

All commands ran from `personal_apps` with `PYTHONDONTWRITEBYTECODE=1`, unless noted.

| # | Command | Result |
| --- | --- | --- |
| 1 | `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **245 passed** in 18.40 s |
| 2 | same, plus `-p c2final_no_outbound`: this reviewer's scratchpad plugin, which refuses and records any non-loopback `connect`, `connect_ex` or `getaddrinfo` | **245 passed** in 18.98 s; `REVIEW GUARD OUTBOUND ATTEMPTS: []` |
| 3 | `npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts static/radar/src/hub/SelectedPriceChart.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/priceChart.test.ts static/radar/src/hub/Admin.test.tsx` | **5 files, 97 tests passed** |
| 4 | `npx tsc --noEmit` | exit 0 |
| 5 | `git diff --check` (worktree root) | exit 0; line-ending warnings only |
| P1 | `c2_final_probe_settle.py`: real `Coordinator` with a real thread, real `price_chart_reader.build_response`, fake in-process child | 8 cases; see §6 C2-1 and M1 |
| P2 | `c2_final_probe_ops.py`: `ops_snapshot()` and `Admission` over all 24 combinations of charts × Yahoo × Alpaca × {no, blank-secret, sentinel} credentials, with `coordinator()` replaced so nothing can start | **0 truth-table mismatches, 0 sentinel/`APCA` leaks**; defaults `False False False` |
| P3 | `c2_final_probe_contract.py`: `fetch.run` against a counting loopback server, with `alpaca.DATA_HOST` replaced in-process, every proxy variable pointing at a dead port, and a hostile `NETRC` | 26 loopback requests in total; see §6 |
| P4 | `c2_final_probe_pan.py`: built hub plus the candidate's loopback server and fixtures (imported; `main()` not run). Real 60 s refetches driven by `page.clock.fast_forward(61_000)` with changed payloads | 6 contexts (1200@1, 390@1, 390@1.25, 390@1.5, 768@1.25, 1200@1.5); **all checks pass**; FT 1D served 5× per context (4 real refetches); 0 unmocked requests, `server_404` empty, port 5043 free afterwards |
| P5 | `c2_final_probe_shots.py`: element screenshots at 390 CSS px, DPR 2 | no document overflow; span buttons 39-44 px wide × 44 px tall and inside the viewport; 0 unmocked requests |

The probe scripts and outputs are in this session's scratchpad, not the
repository:
`C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\3d027496-8d35-4e6e-b4b9-85f596368ef5\scratchpad\`
(`c2_final_probe_*.py`, `c2final_no_outbound.py`, `c2_final_pan/`, `c2_final_shots/`).
Before the probes ran, this review confirmed that importing the reader and the
acquisition module loads neither `dotenv` nor `app`.

The broader recorded gates were sampled from `results.json` (39 cases, 891
checks, 0 failures, 0 live requests) and `evidence.md`, but not re-executed:

- the tone/Yahoo/HA1 regression run (269 passed, 3 baseline failures);
- the whole Radar Vitest suite (883 passed, 28 baseline failures);
- the production build.

## 6. Conclusions

### Corrections C2-1 to C2-4

- **C2-1 — confirmed for the ruled scope, with residual M1.**
  - Forged `ok` results with source `"not_a_source"`, `null` or `7` each:
    - count `invalid: 1` and cache nothing (0 entries, 0 bytes);
    - make the next read `backoff` with a 60 s retry;
    - let the reader serve one whole stored fallback (`finnhub`, `fallback: true`,
      3 observations) without an exception;
    - re-admit the chart after 61 s (`pending`, second child).
  - Valid `alpaca_sip`, valid `yahoo_chart` and the legacy result with no source
    each count `success: 1`, cache one entry and read back as `ready`. They
    resolve through `provider_price` to their own source.
  - Residual: unhashable sources and mismatches between result and spec (M1).
- **C2-2 — confirmed.**
  - At rest, sparse FT opens at 134 of 816 px (1200) and 250 of 700 px (768),
    with both the marker and the gutter visible. At 390 it opens at 411 of
    322 px: the latest observation stays in view and the gutter is traded away.
    This matches `results.json` and was re-measured.
  - Dense 1D, 1W and the stored fallback take the rightmost position (628 at 390).
  - This review's refetch payload moved the latest observation 25 bars earlier,
    below the half-viewport threshold. The chart then correctly placed at 0 at
    1200 and 768, and at 270 at 390, keeping the observation in view. This
    matches the ruled rule.
- **C2-3 — confirmed, including the data-refresh path the candidate harness did
  not exercise.** Results in all six contexts, including fractional DPR 1.25 and 1.5:
  - A reader at the middle position (67, 314 or 125) stayed there across a real
    refetch. It also stayed across a refetch whose latest observation moved, and
    across a resize.
  - A reader at exactly 0 stayed at 0 across a real refetch and a resize.
  - Programmatic placement is not treated as reader input. After open (411 at
    390), a refetch with a moved latest observation re-placed the chart (270).
  - Switching ticker (FT to AAPL) placed the new chart at the rightmost position.
    Switching span (AAPL 1D, with the reader at 0, to 1W) placed it again.
- **C2-4 — confirmed.** Over all 24 combinations:
  - `source` is `yahoo_chart` only when charts and Yahoo are on and Alpaca is off.
  - `source` is `alpaca_sip` whenever the Alpaca switch is on, whether the state
    is `active`, `credentials_missing` or `charts_off`.
  - `source` is `null` otherwise. Alpaca is never invented.
  - Admission starts only for charts + Alpaca + both credentials, or for
    charts + Yahoo with Alpaca off. There is no Yahoo fallthrough when Alpaca
    credentials are missing.
  - The snapshot JSON never contains the sentinel values or `APCA`.
  - The Admin Vitest rows cover `alpaca_sip` (active / credentials missing /
    charts off), `yahoo_chart` and "None selected". The test also asserts the
    page contains no `APCA`, `key id` or `secret` text.

### Original contract sample

- **Request.** Loopback capture of a live 1D request at 15:00Z:
  - path `/v2/stocks/bars`;
  - `symbols=BRK.B`, `timeframe=1Min`, `start=2026-09-15T08:00:00Z`;
  - `end=2026-09-15T14:44:00Z`, which is now minus 16 minutes, although the
    window end was 15:00Z;
  - `feed=sip`, `adjustment=raw`, `sort=asc`, `limit=10000`;
  - exactly one request.

  A closed 1W window keeps its contract end (`2026-09-18T20:00:00Z`) and uses
  `5Min`. When the clamp leaves nothing, no spec is built (`waiting_for_delay`).
  A child given `start >= end` makes 0 requests and returns `waiting`.
- **Isolation.**
  - The key and secret sentinels appeared only in their own two headers.
  - There was no `Authorization` header despite the hostile netrc, and no cookie
    was sent back after `Set-Cookie`.
  - The request reached loopback although every proxy variable pointed at a
    dead port.
  - A 302 was not followed (`invalid/redirect`).
  - Bodies were refused both for an oversized declared length and for an
    oversized stream with no length (`invalid/oversized`).
  - A blank secret made 0 requests and returned `credentials_missing`.
  - `AlpacaHttp` repr is `<AlpacaHttp max_body_bytes=10>`.
- **Child environment.** The platform minimum plus exactly the two names: on
  Windows `SYSTEMROOT` plus both `APCA_*`; on POSIX only both `APCA_*`.
  `APCA_API_BASE_URL`, `ALPACA_API_KEY` and `HTTPS_PROXY` do not cross.
  The existing launcher tests prove the argv, the stdin spec and the real child's
  environment digests with sentinels; this review read them and they passed in
  runs 1 and 2.
- **Validation and classification.** Non-null page token → `truncated`. Other
  symbol key or two keys → `identity_mismatch`. Empty map or empty list →
  `empty`. Each of the following → `invalid`, with no provider text or sentinel
  in any result:
  - duplicate or decreasing timestamps;
  - `null`, `0`, `NaN` or `true` close;
  - naive timestamp;
  - non-JSON 200.

  Status codes: 401 and 403 → `permission`; 429 → `throttle`; 422 with code
  42210000 → `waiting`; any other 422 → `invalid/status`; 500 → `upstream_error`.
  A fractional timestamp (`.000000000Z`) was accepted.
- **Closing minute.** In 1W, 19:55Z was kept and 20:00Z excluded. In a closed 1D
  window, 19:58Z and 19:59Z were `regular:2026-09-15|alpaca_sip:provider_bar_close:raw`,
  while 20:00Z was `afterhours:2026-09-15|…`, a separate segment. The result
  carried source `alpaca_sip`, adjustment `raw`, 3 observations of 960 expected.
- **Flags.** `RADAR_SELECTED_PRICE_ALPACA_ENABLED` is independent and off by
  default (`config.py:1237`). The Yahoo flag does not admit Alpaca.
- **Fallback and observations.** No provider/stored splice (reader `:429`). The
  inspectable pairs are only actual points. Chatter and tone are untouched by
  the diff.

## 7. Screenshots inspected and visual/accessibility ruling

From `radar-design/artifacts/md-selected-price-alpaca-c1/browser/screenshots/`:

- `sparse_1d-research-1200.png`: FT line and fill, separate after-hours dot at
  22:01 CEST, gutter `$7.43`/`$7.36`, "02:00 session end CEST", "65 of 960
  reported", "Adjustment basis raw", and "the line between two of them is a
  guide, not a price".
- `sparse_1d-research-390-chart.png`: line, fill and latest marker in view;
  gutter scrolled off as ruled.
- `week_1w-research-1200.png` (control): separate filled regular sessions with
  nothing across nights or the weekend; "316 of 316"; "5 segments" in the summary.
- `fallback_1d-research-390-chart.png` (control): Finnhub "stored quotes ·
  fallback while the provider chart unavailable", "Adjustment basis unknown",
  3 segments, no expected-grid claim.
- `zoom200-sparse_1d-research-390css-chart.png` and `-focus.png`: see M2.

This review's own element shots (scratchpad `c2_final_shots/`) are
`sparse-390-dpr2-wrap.png`, `week-390-dpr2-wrap.png` and
`unavailable-390-dpr2-wrap.png`. They show crisp lines, a subtle fill, one
latest marker, a readable axis and no dot cloud. The short partial Tue 15
segment in 1W is a real narrow segment under the marker.

**Ruling: the accepted area language is present and truthful.**

- One calm line and baseline-closing fill per hard segment, a dot only for a
  one-observation segment, one latest marker, no dot cloud.
- No line or fill crosses a session, state or source boundary.
- The provenance says "delayed" consolidated SIP and "raw", and never claims
  real-time.

**Accessibility:**

- All 39 recorded cases pass keyboard reachability, visible focus, readout and
  no-document-overflow checks.
- Span controls measure 44 px tall at 390 CSS px / DPR 2.
- No motion was added. The pan is a plain `scrollLeft` assignment.

Real 200% zoom is backed by the recorded check results rather than by those two
frames (M2). The DPR-2 shots are layout-equivalent, not real zoom. This does
not block acceptance.

## 8. Remaining release carries

- **No live Alpaca path has ever been exercised:** not the intra-session clamp
  against a live session, a real 422/42210000 envelope, real 401/403/429/5xx, or
  real throttling. All browser evidence uses fixtures.
- **POSIX/gunicorn on the release host is unverified:** the child running with
  the two `APCA_*` variables, venv and cwd, and the production `.env` actually
  holding both names (names only; values never inspected).
- **Database and topology are unverified:** MariaDB runtime, DB-backed route
  suites, and the real `WEB_CONCURRENCY` worker topology.
- **Release packaging.** `price_chart_contract.py` imports `prices.alpaca` when
  the module loads, so the untracked `features/radar/prices/alpaca.py` and
  `tests/selected_price_unit/test_alpaca_bounded.py` must be committed
  explicitly with the tracked delta. Omitting `alpaca.py` would break the chart
  route even with every flag off.
- **The Radar dist must be rebuilt on release** through the normal wrapper.
- **Activation is a separate owner decision.** It means setting
  `RADAR_SELECTED_PRICE_ALPACA_ENABLED` on the host and restarting the web service.
  Charts ON / Yahoo OFF / Alpaca OFF remains the recorded production state.
- **Optional before release:**
  - the M1 equality guard;
  - passing the `APCA_*` variables only to Alpaca children (a note, not a finding);
  - the M2 harness refinements.

## 9. State and confirmations

- Branch `codex/radar-selected-price-charts`. HEAD
  `f632e5db5dd92e27480cbfccdf7b0638b26533ed` equals `origin/main`, re-verified at
  the end.
- Before this file: 31 modified tracked files and 37 untracked entries, unchanged
  by the review. After this file: the same 31 modified plus 38 untracked (this
  return added).
- No continuity file was updated. The continuity files' mtimes (04:47-04:48)
  predate this session.
- No other file under the worktree changed during the review.

Confirmed:

- **No real credential was inspected.** No real credential value and no private
  root `.env` was opened, parsed, hashed or searched. Only variable names, code
  paths and synthetic sentinels were used: `PKFINALREVIEWSENTINEL01` and
  `PKCONTRACTPROBESENTINEL`, with made-up secrets.
- **No outbound or provider request was made.** P3 used a loopback server with
  `DATA_HOST` replaced in-process. P4 and P5 mocked every API call at the browser
  boundary: 0 unmocked requests, empty `server_404`. The guarded pytest run
  recorded zero outbound attempts.
- **No product or test file was edited.**
- **No other action was taken:** no dependency install, build, flag activation,
  configuration change, database, schema, service or production action, commit,
  push or deploy.
- **Git state was left alone:** no reset, clean, stash, restore, checkout or stage.
- **No subagents were used.**

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Assess this fresh-session Reviewer/QA return for assignment MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / f632e5db5dd92e27480cbfccdf7b0638b26533ed / f632e5db5dd92e27480cbfccdf7b0638b26533ed (= origin/main; candidate uncommitted)
Return: radar-design/MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RETURN.md (the only repository write)

INDEPENDENCE: this ran in a genuinely fresh task/session (Claude Opus 5, no subagents). All three gate statements were confirmed true before any repository work: I did not implement C1, did not perform the same-session C2 review, and did not implement C2-FIX.

VERDICT: ACCEPT C1 FOR OWNER ACTIVATION/DEPLOYMENT DECISION. No Critical, no Important, two Minor. This does not authorize activation, configuration, commit, push or deploy.

STRENGTHS:
- prices/alpaca.py has one path constant and a fixed host. trust_env=False, cookie policy allows no domain, no redirects, body capped by declared length and while streaming. Credentials are read by name inside the one request and appear only in the two headers.
- The 16-minute clamp is enforced in the parent (contract.py:423-425) and again in the child (fetch.py:145).
- Hard segments = state_at (state + session date) + regime (contract.py:721). The half-open intervals do the close-minute work.
- The reader never splices provider and stored data (reader.py:408-431). Stored fallbacks drop non-finite values, so the new frontend observations check (priceChart.ts:256) is safe.
- priceSegments/areaPathOf add no data.
- The pan ref lifecycle is sound: listener added before placement and removed on cleanup; refs keyed on ticker|span.

FINDINGS:
- M1 (Minor, product, unreachable). price_chart_acquisition.py:479 (called at :454; reason text :482). The C2-1 guard tests membership, not equality with the admitted spec's source. Probe with a real Coordinator, real thread, real reader and a fake child:
  (a) source ["alpaca_sip"] or {"x":1} raises "TypeError: unhashable type" in the supervisor thread. invalid stays 0 and no cooldown entry is written. Nothing is cached, the reader still serves one whole stored fallback (finnhub, 3 observations) with no request-path error, and re-admission stays bounded by the 60 s per-key start interval.
  (b) a yahoo_chart result answering an alpaca_sip spec counts success, is cached under the Alpaca key and is served (labelled Yahoo chart) although only Alpaca is admitted.
  (c) the refusal reason reads "the series exceeded its bound".
  Only the fixed child writes source, so this is not reachable today.
  Smallest fix: pass spec to _settle and use `result.get('source', YAHOO_SOURCE) != spec.get('source', YAHOO_SOURCE)`. Equality needs no hashing, subsumes membership and keeps the missing-source Yahoo default. Add two unit tests. Optional before release.
- M2 (Minor, evidence harness only). verify_browser.py:466-471: the comment claims a refetch but the code only resizes, so the effect's re-run on new data was not browser-proven by the candidate. verify_browser.py:186-211: the zoom200 "-chart"/"-focus" PNGs do not show the drawing, so the C2-FIX "real 200% zoom, nothing clipped" claim rests on results.json checks, not those frames. This review closed the refresh gap itself (below). Optional harness fix.
- Pre-existing, out of scope: _settle accepts NaN/Infinity received_at (json.loads default) and the reader would raise. This is unchanged from HEAD and unreachable (child uses allow_nan=False).
- Notes, not findings: APCA_* are passed to every child, including the historical Yahoo child (the ruling permits it; least-privilege note). At 390 px the unavailable-state in-plot message is off screen at rest; the provenance states the absence.

COMMANDS (reviewer-executed, from personal_apps, PYTHONDONTWRITEBYTECODE=1):
- pytest tests/selected_price_unit: 245 passed (18.40 s).
- Same under this reviewer's non-loopback socket guard: 245 passed, OUTBOUND ATTEMPTS [].
- Five focused Radar Vitest suites: 5 files / 97 passed.
- tsc --noEmit: exit 0.
- git diff --check: exit 0.
- Probes, all in session scratchpad, never in the repo:
  - P1 settle/reader: 8 cases.
  - P2 ops/admission: 24-combination truth table; 0 mismatches, 0 sentinel/APCA leaks.
  - P3 contract: counting loopback, DATA_HOST replaced in-process, dead-port proxies, hostile NETRC; 26 loopback requests.
  - P4 pan: built hub + candidate fixtures with real 60 s refetches via page.clock and changed payloads; 1200@1, 390@1, 390@1.25, 390@1.5, 768@1.25, 1200@1.5; all pass; 4 refetches per context; 0 unmocked; server_404 empty.
  - P5: DPR-2 element shots.
- Broader gates were sampled from results.json (39/891/0) and evidence.md, not re-run.

C2-1..C2-4:
- C2-1 CONFIRMED for the ruled scope. "not_a_source", null and 7 each give: invalid 1, cache 0, backoff 60 s, whole finnhub fallback without exception, re-admitted after 61 s. Valid alpaca_sip, valid yahoo_chart and the missing-source shape succeed and resolve to their own source. Residual: M1.
- C2-2 CONFIRMED. Sparse FT opens at 134/816 (1200) and 250/700 (768) with marker + gutter visible, and 411/322 at 390 with the latest kept. Dense/1W/fallback open rightmost. A refetch with an earlier latest correctly re-places to keep it in view.
- C2-3 CONFIRMED, including the data-refresh path. In all six contexts, including DPR 1.25/1.5:
  - middle 67/314/125 survives a real refetch, a refetch with a moved latest, and a resize;
  - exactly 0 survives a real refetch and a resize;
  - placement is not reader input (390: 411 -> 270 after a moved-latest refetch);
  - a ticker switch (FT -> AAPL) and a span switch (AAPL 1D, reader at 0 -> 1W) each re-place.
- C2-4 CONFIRMED.
  - yahoo_chart only for charts+Yahoo with Alpaca off; alpaca_sip whenever the Alpaca switch is on (active / credentials_missing / charts_off); null otherwise; Alpaca never invented.
  - Admission only for charts+Alpaca+both credentials, or charts+Yahoo with Alpaca off; no Yahoo fallthrough.
  - No credential in output. Admin tests cover "None selected" and yahoo_chart.

ORIGINAL SAMPLE:
- Live 1D at 15:00Z sent one GET /v2/stocks/bars: symbols=BRK.B, 1Min, start 08:00Z, end 14:44Z (window end 15:00Z), sip/raw/asc/10000. Closed 1W keeps end 18 Sep 20:00Z with 5Min. An empty clamp builds no spec; a child with start>=end makes 0 requests and returns waiting.
- Sentinels appeared only in their two headers; no netrc Authorization; no cookie echo; dead-port proxies ignored; 302 not followed; oversized declared and streamed bodies refused; blank secret made 0 requests (credentials_missing).
- Child environment = SYSTEMROOT (nt) plus exactly both APCA_* names.
- page token -> truncated; other/two keys -> identity_mismatch; empty -> empty; duplicate/decreasing timestamps, null/0/NaN/true close, naive timestamp, non-JSON 200 -> invalid. 401/403 -> permission; 429 -> throttle; 422+42210000 -> waiting; 500 -> upstream_error. No provider text or sentinel in any result. Fractional timestamps accepted.
- 1W keeps 19:55Z and drops 20:00Z; 1D keeps 20:00Z as a separate afterhours segment; source alpaca_sip, raw, 3 of 960.
- Flag independent and off by default. No splice. Only actual points are inspectable. Chatter/tone unchanged.

SCREENSHOTS AND RULING:
- Inspected: sparse_1d 1200 and 390-chart; week_1w 1200 and fallback_1d 390-chart as controls; zoom200 sparse -chart/-focus (see M2); own DPR-2 element shots for sparse/week/unavailable at 390.
- Area language present and truthful: one line + fill per hard segment, one latest marker, no dot cloud, nothing across nights, delayed consolidated SIP and raw disclosed, never real-time; sparse 1200 shows line + after-hours dot + gutter + end label together.
- Keyboard, focus, readout and no-overflow pass in all 39 recorded cases; span buttons 44 px tall at 390/DPR 2; no motion added.

RELEASE CARRIES:
- No live Alpaca path ever exercised (live clamp, real 422/42210000, 401/403/429/5xx, throttling).
- POSIX/gunicorn child with APCA env on the host; production .env name presence.
- MariaDB runtime and DB-backed suites; real WEB_CONCURRENCY.
- Commit must explicitly include untracked prices/alpaca.py (imported by price_chart_contract at load; omitting it breaks the chart route even flags-off) and test_alpaca_bounded.py.
- Dist rebuild on release.
- Activation (RADAR_SELECTED_PRICE_ALPACA_ENABLED + restart) remains a separate owner decision; recorded production state is charts ON / Yahoo OFF / Alpaca OFF.
- Optional: M1 fix, M2 harness fix, APCA-only-for-Alpaca-children.

STATE:
- HEAD = origin/main = f632e5d re-verified; 31 modified tracked + 38 untracked (37 pre-existing + this return); no continuity file updated; no other worktree file changed.
- CONFIRMED: no real credential or private .env opened, parsed, hashed or searched (sentinels only); no outbound/provider request; no product/test edit; no dependency install, build, activation, configuration, DB/schema/service/production action, commit, push or deploy; no reset/clean/stash/restore/checkout/stage; no subagents.

Requested Mastermind decision: close C2 and accept C1 for the owner's activation/deployment decision. Decide whether M1 (a small equality guard plus two tests) should land before release or be carried.
Next bounded action recommendation: if the owner wants M1, one tiny Implementer patch plus a changed-lines check. Otherwise prepare the owner release/activation decision with the carries above. Do not reopen the source contract, isolation design, segment model or area language; do not rerun provider validation.
```

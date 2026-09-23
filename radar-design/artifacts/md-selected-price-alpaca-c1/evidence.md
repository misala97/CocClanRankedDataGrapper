# MD-SELECTED-PRICE-ALPACA-C1 — implementation evidence

Implementer (Claude Opus 5, no subagents), 2026-09-16. Every command below was
run by this worker in the candidate worktree
`C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
(branch `codex/radar-selected-price-charts`, HEAD = base = origin/main
`f632e5db5dd92e27480cbfccdf7b0638b26533ed`, nothing committed or pushed).
Python `py -3.12` (3.12.6); Node/npx from the existing `personal_apps/node_modules`
(no install, no download). **Zero live provider requests.**

## 1. Failing-first record

| Task | New/changed tests run against the PRE-CHANGE sources | Result |
| --- | --- | --- |
| 1 — adapter | `test_alpaca_bounded.py`, `test_normalize.py`, `test_window.py` | `test_alpaca_bounded.py` **collection ImportError** (`cannot import name 'alpaca' from 'features.radar.prices'`); the other two **24 failed, 38 passed** |
| 2 — flags/secrets/admission/ops | `test_acquisition.py`, `test_launcher_isolation.py`, `test_route_ops.py` | **36 failed, 47 passed** |
| 3 — wire contract | `priceChart.test.ts` | **2 failed, 17 passed** |
| 4 — geometry/component | `selectedPriceGeometry.test.ts`, `SelectedPriceChart.test.tsx` | **16 failed, 15 passed** |
| 4 — admin status | `Admin.test.tsx` | **5 failed, 17 passed** |

Task 1's tests were written before its implementation but first executed after
it; the failing-first record above was then produced by restoring the three
Task 1 sources to their HEAD content in place (`git show HEAD:<path> > <path>`
for the two tracked files, `prices/alpaca.py` moved aside), running the tests,
and restoring the worker's versions from a byte-for-byte backup. All three
SHA-256 digests matched before and after; no Git operation touched the index,
the working tree's other files or the stash. Tasks 2-4 were run failing-first
in the ordinary way.

## 2. Backend verification

| Command (from `personal_apps`) | Result |
| --- | --- |
| `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **239 passed** in 18.4 s (was 173 at base: +66) |
| the same, with an outbound-socket guard (`-p no_outbound`, patching `socket.connect`, `connect_ex` and `getaddrinfo` to refuse anything but loopback) | **239 passed**, `OUTBOUND ATTEMPTS: []` |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | **269 passed, 1 skipped, 3 failed** — exactly the three date-dependent `test_radar_yahoo.py::test_daily_closes_*` baseline failures the 2026-09-15 implementation recorded (fixture timestamps older than the adapter's rolling date floor), unchanged by this work |

## 3. Frontend verification

| Command (from `personal_apps`) | Result |
| --- | --- |
| `npx vitest run -c vite.radar.config.ts static/radar/src/hub/{selectedPriceGeometry.test.ts,SelectedPriceChart.test.tsx,SelectedPriceSection.test.tsx,priceChart.test.ts,Admin.test.tsx}` | **5 files, 90 passed** |
| `npx vitest run -c vite.radar.config.ts` (whole Radar suite) | 54 files, **876 passed, 28 failed** — all 28 in `hub/pending.test.tsx`, identical to the recorded baseline (847 passed / 28 failed before this work: +29 new tests) |
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | passed; Radar bundle `assets/hub-BAY3z_IW.js`, `assets/hub-Czy1AMuW.css` |

## 4. Visual verification

`py -3.12 -u radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py`
against the built real hub bundle: **37 cases, 850 checks, 0 failures**, 0
unmocked requests, 0 stray server hits, 87 s, port 5043 free afterwards. 96
PNGs under `browser/screenshots/`, all viewed. Results: `browser/results.json`.

- Viewports 1200, 768 and 390 CSS px, plus REAL 200% browser zoom at 390 CSS px
  (headed Chromium with its own default page-zoom preference, a 780 device-px
  window; `real_zoom_in_effect` asserts `devicePixelRatio >= 1.9`).
- Both chart surfaces: standalone Research and the Human Chatter research panel.
- Six states, each the real reader/contract output over the real
  `normalize_alpaca` (`browser/fixtures.py`, manifest in `browser/fixtures/manifest.json`):

| State | Shape | Segments drawn |
| --- | --- | --- |
| `sparse_1d` | FT 1D, `alpaca_sip`, 65 of 960 expected minutes | 1 multi-point (64 regular) + 1 dot (the 20:00:00Z closing bar, after-hours) |
| `dense_1d` | AAPL 1D, `alpaca_sip`, 350 of 350 | 2 multi-point (pre-market, regular) |
| `week_1w` | AAPL 1W, `alpaca_sip` 5-minute, 316 of 316 | 5 multi-point, one per modeled regular session |
| `fallback_1d` | MSFT 1D, Alpaca unavailable (delay clamp), stored Finnhub quotes | 3 multi-point (a 90-minute hole and a state boundary) |
| `unavailable_1w` | NVDA 1W, provider refused the credentials, nothing stored | none — "No price observation inside this window" |
| `chatter_gaps` | FT 1D with 9 unknown, 55 partial and 1 zero chatter slot | 1 multi-point + 1 dot |

The 32 distinct checks include: one line and one area path per multi-point hard
segment; a dot only for a one-observation segment; exactly one latest marker and
no dot cloud; one line vertex per actual observation and no more; the area adds
only its two baseline corners, is closed and is filled from a gradient that
resolves inside its own SVG and fades the price colour to nothing; no fill
crosses a night on 1W; the panned chart opens on the latest observation; the
provenance names delayed consolidated SIP and the raw basis, discloses
`observations of expected_intervals`, and never says real-time; an absent price
says so in both the plot and the provenance, and a credential refusal names
itself without a credential; keyboard reachable with a visible focus ring and a
readout that reports the interval and its counts; no document overflow; no page
errors.

### Against the accepted preview

Compared with `artifacts/md-selected-price-personal-preview/area-1200.png` and
`area-390.png`: same visual language — one calm cyan line through the reported
prices, a subtle cyan-to-transparent fill closed to the price-lane baseline, one
latest marker, no per-point dots, a separate discussion lane beneath on the same
time axis. Deliberate, disclosed differences, all from the deployed contract
rather than a reinterpretation of the direction:

1. The 1D window is the extended session (04:00-20:00 ET) the shipped contract
   computes, not the preview's regular-session-only span, so a listing that
   stops trading at the bell leaves visible empty pre/after-hours bands.
2. The shipped component carries a provenance/basis block, a legend, market-state
   bands, a live readout, an accessible summary and a data-notes disclosure; the
   standalone preview carried none of them.
3. The canvas stays 912 px wide and pans below that width, which is the reviewed
   shipped behaviour, rather than the preview's full-bleed responsive drawing.
   **One correction was made here**: opening the pan at the newest end of the
   WINDOW put FT's whole session off screen to the left behind four empty
   after-hours hours at 390 px. It now opens on the latest actual observation
   (`the_panned_chart_opens_on_the_latest_observation`).
4. Lane proportions were compacted toward the preview: the chart is now
   912 x 306 user units (price lane 170, discussion lane 48) instead of
   912 x 344 (134 / 122).

## 5. Secret isolation

- `child_environment()` copies the platform minimum plus exactly
  `('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY')`, treating blank as absent.
  `test_only_the_two_named_alpaca_variables_join_the_platform_minimum` proves
  `APCA_API_BASE_URL`, `ALPACA_API_KEY`, `SECRET_KEY` and `FINNHUB_API_KEY` do
  not cross.
- The end-to-end launcher test starts a real parent whose `__main__` is a file
  path with unguarded top-level code, sets sentinel credentials plus a decoy
  secret and Python/proxy overrides, and runs the production launcher. The child
  reports SHA-256 **digests** (never values): both sentinels arrive intact, the
  decoy does not, `argv_carries_a_credential` is false, and the child's whole
  environment is a subset of allowlist + credentials.
- `test_an_alpaca_child_is_started_with_no_credential_in_its_arguments` asserts
  neither sentinel is in the Popen argument array or in the request spec written
  to stdin.
- `test_no_credential_value_leaves_the_process_outside_the_two_headers` and
  `test_a_provider_failure_never_carries_credentials_or_provider_text` assert
  the sentinels appear only in the two documented headers, and that the
  classified result of a 403/429/422 carries neither a sentinel nor the
  provider's own message text.
- `test_ops_names_the_source_truthfully_and_never_reports_a_credential` asserts
  the ops snapshot reports only `credentials_present: bool`.
- A scan of all 1,584 text files in the worktree for the REAL values of
  `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` read from the private root `.env`
  found **0 occurrences**. The values were compared in memory and never printed.
  The `.env` itself was not modified.

## 6. Flags

`RADAR_SELECTED_PRICE_ALPACA_ENABLED` is a new independent variable, default
false. With no selected-price variable set at all:

```text
charts False yahoo False alpaca False
selected_source (None, 'charts_off')
Admission -> {'state': 'disabled', ..., 'reason': 'provider acquisition is switched off'}
coordinator instance None
```

Acquisition needs charts AND Alpaca AND both credential names non-blank;
`test_admission_needs_both_the_chart_and_alpaca_flags` and
`test_missing_credentials_refuse_without_starting_a_child` prove each. The
historical Yahoo flag is untouched and no longer authorizes Alpaca.

## 7. Not verified here

- The live provider: no Alpaca request was made. The live intra-session clamp,
  a real SIP-too-recent refusal, real 401/403/429/5xx envelopes and real
  throttling remain unobserved; they are covered only by deterministic fixtures
  built from the 2026-09-16 validation's recorded shapes.
- POSIX/gunicorn child behaviour on the release host, MariaDB runtime, DB-backed
  route suites and real worker topology: unchanged release carries.
- The browser evidence is fixture evidence: no database, no provider, no
  production.

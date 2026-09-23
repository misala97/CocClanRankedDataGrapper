# HA1 LOCAL-QA evidence — Implementer / local QA operator, 2026-09-15

Assignment HA1-US-DAILY-EXPLORE-LOCAL-QA. Claude Opus 5, no subagents/workers. Every command below was executed by this operator on the local machine against the NEW disposable HA1 target only. Synthetic fixtures only. No production host, production data, provider, commit, push or deployment.

## Git

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`, no upstream (`fatal: no upstream configured`). Per-command `-c safe.directory=<candidate>`; global `safe.directory` entries unchanged (main checkout, `radar-pipeline-audit`).
- Tracked diff 14 files +1040/−35 at start and end (the tracked files are handoffs/ledgers/plans plus the earlier hub changes; this assignment's tracked edits are continuity notices only). `git diff --check` exit 0. `git-start.out.txt`, `git-end.out.txt`.
- Status 63 entries at start → 62 at end: the unexplained untracked `personal_apps/downloaded_files/dashboard.lock` (0 bytes, created 12:57:49) and its directory **disappeared during this assignment** (present in the 13:2x `status -uall` listing and the 13:34 snapshot; absent at 14:0x). No command of this assignment referenced that path; no other `downloaded_files`/`dashboard.lock` exists under CodingStuff or Temp. Cause not established. Not attributed; reported.

## Environment

See `environment.md`. MariaDB 10.11.14 (portable copy) at `C:\Users\michi\.radar-ha1-local-qa`, `127.0.0.1:3461/radar_ha1_localqa`, dedicated registry, candidate migrations to `b7e3f9c1a2d4` (47 tables). Hardware: Intel Core i9-11900K (8C/16T), 31.9 GiB RAM, Windows 11 Home 10.0.26200, Python 3.12.6, Chromium 149.0.7827.55.

## 1. Hatch fix

- Test first: `analysisCss.test.ts` new block "partial count bars keep their hatch" → `2 failed | 7 passed` against the unfixed CSS (full-bar selector missing; `.rh-an-fill` fill reaches partial bars).
- Fix: `analysis.css` `.rh-an-fill { fill: var(--chatter) }` → `.rh-an-fill:not(.partial) { fill: var(--chatter) }` (+2-line comment). `AnalysisChart.tsx` unchanged: partial bar keeps `fill="url(#rh-an-hatch)"`, `*` text disclosure and `.rh-an-fill.partial` stroke.
- Focused Vitest after fix: 3 files 40 passed; HA1 focused list 10 files **230 passed** (was 228 + 2). One TS strictness fix in the new test (`?.[1]?.trim()`) after `tsc` flagged it.
- `npm run build` (tsc + gym + radar Vite) passed three times; final build before serving → fingerprint `8781d5381f8141f28720a469e3c415fe64f84a032b4a3dce952450398fde36c9` (154 inputs, 5 served build files; `fingerprint-after-build.final.json`). Radar CSS bundle `hub-Dwv8T12n.css` unchanged across rebuilds.
- Runtime: computed `fill` of `svg.counts rect.rh-an-fill.partial` = `url("#rh-an-hatch")` at 1440 and 390 (`partial_truncated_zero`); screenshots show hatched partial bars (e.g. Fri 11 Sep `40*`) beside solid full bars; graphics contrast full-bar fill 7.82:1, partial stroke 7.82:1.

## 2. Harness corrections (bounded, disclosed, tested)

| # | Fault found at runtime | Correction | Regression |
| --- | --- | --- | --- |
| H1 | MariaDB 10.11.14 cuts `BENCHMARK()` at `max_statement_time` but returns `0` with no error (1.005 s, `diag_timeout.out.json`); CPU probe classified `not_interrupted` (API suite 30 passed / 1 failed) | `ha1_harness.CPU_PROBE_SQL` row scan `SELECT COUNT(*) AS value FROM seq_1_to_1000000000 WHERE MOD(seq, 7) = 3` (~58 s unlimited; 1969 at 1 s and 0.25 s) used by both CPU probes in `ha1_fixtures.timeout_probe` | `test_the_cpu_probes_scan_rows_instead_of_a_silently_truncated_benchmark` |
| H2 | 130 s board-quiet wait was one uninterrupted call | `ha1_harness.quiet_segments` (≤30 s segments summing exactly to 130 s) + flushed progress lines in `verify_preview` | `test_the_board_quiet_window_is_observed_in_progress_segments_not_shortened` |
| H3 | `tracemalloc` slowed the 43,008-row bucket fetch from ~0.6 s to 2.6–2.9 s, straddling the reader's 2 s statement limit; probe aborted (`probe_analysis.run1.json`, `diag_max_read.out.json`) | traced allocation reads only send `max(handed, ha1_harness.TRACED_STATEMENT_LIMIT_S=30 s)`; handed limit still recorded; all time limits asserted on untraced reads | `test_only_traced_allocation_reads_send_the_widened_statement_limit` |
| H4 | `'t=' not in location.search` matched inside normalized `segment=` | parsed `'t' not in parse_qs(...)` | `test_local_qa_run2_harness_faults_stay_corrected` |
| H5 | `unroute` before releasing held routes raised "Route is already handled!" and left the handler installed | release/abort held routes before `unroute`, in `finally` | same |
| H6 | skip-link check started Tab from focus left by earlier keyboard cases | fresh tab; asserts focus is `body` on load first | same |
| H7 | injected loading/timeout/network/session cases reused a tab whose keys were cached (no request sent → nothing intercepted; run3) | each injected case in a fresh tab and must PROVE injection engaged: ≥1 held/aborted request, 302 on the expired request | same |
| H8 | Chromium refuses port 5061 (`net::ERR_UNSAFE_PORT`) | preview on 5041 (operational, no code) | — |

No assertion or budget was loosened; H6/H7 add checks. `ha1_unit` under REVIEW-2 socket guard: 236 (start) → **240 passed**, `app_imported=False pymysql_imported=False`. Mutation check `mutation_check_localqa.py`: baseline clean, **10/10 mutants caught**, every file restored by SHA-256. These tests were written after the harness edits (hatch test was failing-first); the mutation run is the evidence they catch reverts.

## 3. Gated API suite (C02/C11/C13/C14 transport)

`py -3.12 scratchpad/ha1/local_runtime.py test` on the final fingerprint → **31 passed** (`api-suite.final.out.txt`): resolve 404/409/422, stale 409/404, range/query 400 codes, independent series/gaps, future-fetched close excluded, JSON escaping, ≤4 data SELECTs + EXPLAIN, 65-source 503, store failure 503 `analysis_unavailable` with no SQL leak then recovery 200, statement timeout + hygiene + 0.250 s probe, signed-out 302, loopback non-admin 200, and `FULL_ACCESS_HOST` non-admin exactly **403** on company and resolve via Flask test-client host sessions (`base_url=http://mgemmel.viewdns.net`; no network contact — test client only).

## 4. Probe (C13/C14) — `probe_analysis.final.json`, 0 failures

| Fixture | rows / sources | statements | bytes | cold ms | warm median / p95 ms (20) | reader-only ms (5) | traced alloc bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zero | 0 / 0 | 4 | 3,839 | 8.53 | 4.80 / 5.92 | 2.2–2.8 | 69,645 |
| typical | 2,016 / 3 | 4 | 9,359 | 33.57 | 32.50 / 36.73 | 31.2–36.5 | 1,276,532 |
| max | 43,008 / 64 | 4 | 111,050 | 716.27 | 752.13 / **781.18** | 712–849 | **26,195,307** (25.0 MiB) |

EXPLAIN (all fixtures): company_by_id const/PRIMARY; instrument_by_id const/PRIMARY; daily_closes range/`uq_radar_daily_close_market` (Using index condition; Using where); bucket_sources range/PRIMARY (Using where; est. rows 23,161 for max). Refusals: 65 sources in 65 rows → 503 `analysis_limit`; 43,009th row with 64 sources → 503 `analysis_limit`, 200 after sentinel removal.

Timeout on one physical connection (id 33→33, session `max_statement_time` 0.0→0.0): SLEEP(3) @1 s → 1969 at 1.005 s; CPU row scan @1 s → 1969 at 1.009 s; CPU @0.250 s (rendered `SET STATEMENT max_statement_time=0.250 FOR`) → 1969 at 0.264 s, overshoot 0.014 s, post-hoc budget refused; same-connection `SELECT 1` recovery true; next HTTP read 200.

Deadline (ruled semantics; `acceptance: mastermind_ruling_required`): statement interruption delay CPU 0.009 s, sub-second 0.014 s. Reader exhaustion: 503 `analysis_limit`, elapsed 5.052 s, **overshoot 0.052 s**, handed limits [2.0, 2.0, 1.079, 0.047] s. Full HTTP: 503 `analysis_limit`, 5,058.9 ms, **overshoot 0.059 s**, 0.0016 s before first reader statement, handed [2.0, 2.0, 1.078, 0.031] s; next request 200.

Additional measured fact for ruling (diag, not a probe assertion): with tracing, a bucket SELECT handed 2.0 s returned successfully after 2.855–2.889 s client-side — `max_statement_time` bounds server execution, not client materialization; the reader's 5 s post-hoc check then passed (3.3 s). Earlier probe run1: one traced read was refused at that statement.

## 5. Actual-app browser QA

Server: `py -3.12 scratchpad/ha1/local_runtime.py serve 5041` (hidden, loopback, reload off), runtime record v2 + `X-HA1-Runtime` nonce, fingerprint `8781d538…` verified by `verify_preview.preflight` before login and again at the end (`source_build_identity`). Fixtures: `preview_fixtures.py seed` — 15 owned cases + owned non-admin `zq-ha1-<token>-plain`, window 2026-09-08..14 (default at 2026-09-15); synthetic.

Runs (all `py -3.12 -u scratchpad/ha1/verify_preview.py <port>`):
- run1 (5061): browser refused `net::ERR_UNSAFE_PORT` before any case — environment, not product.
- run2 (5041, fingerprint 9629c007…): 58 cases, 7 failing → diagnosed harness faults H4–H6 plus the cached-tab fault later fixed as H7 (`diag_preview.out.json`: every injected state and the skip link pass in fresh contexts). Report `run2/verify_preview.json`.
- run3 (5041, 63e5543d…): 55/58; timeout/network/session injected cases failed only because the shared tab had cached keys (H7). Report `run3/verify_preview.json`.
- **run4 (5041, final 8781d538…): 58/58 cases recorded, 0 failures, 285 checks, 179.4 s.** Report and PNGs `run4/`.

Run4 facts: board-quiet 130 s in 30 s segments, 0 `/radar/api/board` requests on Analysis, 0 bootstrap board requests for the Analysis load, positive control observed after leaving; U2 selection+pin adds exactly one history entry, URL stable after 1.5 s, Back → pre-selection `#analysis`, Forward → canonical; C15 root/alias/legacy/return link/signed-out 302s (5 paths)/valid `t`/hash over `t`/invalid-hash fallback/filter-only + refresh/canonical link with exact request at 1440 and 390; alignment max button-to-column deviation 0.07 px (1440) and 0.33 px (390) vs 2 px parameter; touch taps on first/last day inside scroll box (390: 440/322 px, 320: 440/252 px), no control <44 px at 390/320 and emulated zoom; text contrast min 6.19:1 (identity dt, axis), graphics min 6.19:1; drawn price runs `[0,1,2,3]` with 4 points and break at the modeled weekend; partial computed fill `url("#rh-an-hatch")`; Tab order from document: skip → … → Find another company → from → to → submit → day; menu Escape at 390/320; reduced motion transition 0s; non-admin loopback reads Analysis.

Injected UI states (browser route interception — NOT backend evidence): loading (1 held request), 8 s timeout notice (1 held), network abort alert + Retry recovery (≥1 aborted), session expiry (cookies cleared; real server answered 302 to the company request; `Session expired.` shown, data hidden). Real engine evidence for errors is §3/§4 (503 `analysis_limit`/`analysis_unavailable` from the actual reader), and the `limit_503` browser case used a real 65-source fixture answered by the server.

Emulated `zoom_200` (720×500 @ device scale 2) passed but is labelled emulation; real zoom evidence is §6.

Screenshots viewed by this operator: run2/run4 `typical-1440`, `lines-1440`, `empty-1440`, `typical-390`, `partial_truncated_zero-1440`, run4 `typical-320`, `typical-768`, `session-expired-1440`, `zoom-200` (emulated), `limit_503-1440`, `stale-390`, `invalid-pinned-1440`, `loading-1440`; `zoom-real-200-headed.png` (invalid capture, see §6), `zoom-real-200-cdp-top.png`, `zoom-real-200-cdp-chart.png`.

Visual findings (not fixed; product scope):
- F1 (C16 clipping, minor): at 320 px the two date inputs clip their value (`scrollWidth 126 > clientWidth 117`, `input_clip_check.out.txt`; screenshot shows `2026-09-0`/`2026-09-1`). 390 and 768 not clipped. Harness `no_document_overflow` does not detect in-control clipping.
- F2 (polish, minor): on selected pages the retrospective line wraps as `RETROSPECTIVE` / `— current retained records … ZQ… HA1 fixture.` (company name appended to the caveat line); empty/limit/invalid pages render it on one line.
- F3 (harness capture artifact): full-page screenshots with the sticky header show the header/skip link painted mid-image (`zoom-200.png`); not a layout defect in live viewports (CDP viewport captures are clean).
- Fixture note: `typical` has a close on Sat 12 Sep (modeled closed); the app joins Fri–Sat and warns `a close is stored on a modeled_closed day` — consistent with SPEC §5 (observation kept + discrepancy warning).

## 7. Cleanup and residual state

- `preview_fixtures.py cleanup` → `removed the owned preview fixtures recorded for 127.0.0.1:3461/radar_ha1_localqa`, exit 0, manifest removed (copy kept: `preview-fixtures.manifest.before-cleanup.json`). Probe runs and `diag_max_read` report cleanup `complete`, remaining `{}`; API suite cleans per test.
- Residual DB (`residual-db.out.txt`): radar_ticker_universe / radar_instruments / radar_daily_closes / radar_bucket_sources = 0 / 0 / 0 / 0 rows. `app_user`: id 1 `admin` (created by a candidate migration), id 2 `zq-ha1-localqa-admin` (environment-owned) — retained inside the retained data directory.
- Processes: every preview server this assignment started (5061 ×2, 5041 ×4, each `py.exe` launcher + `python.exe`) stopped by PID after command-line match; `mariadbd.exe` stopped by recorded PID after executable-path match (see §8 of the return for the listener check). No other process stopped; MySQL80/3306 untouched.
- Left in the worktree (harness-owned runtime records, untracked, kept): `artifacts/ha1/runtime/preview-runtime-5041.json` and `preview-runtime-5061.json` (stale identity records: the servers were stopped by PID, so their `atexit` removal did not run; the harness refuses them because the pid is dead), `artifacts/ha1/runtime/probe_analysis.json` (last probe), `artifacts/ha1/preview/*` (run4 PNGs + JSON, also copied to `local-qa/run4/`).

## 6. Real 200% zoom

`zoom_real.py`: new temporary Chromium profile with the browser's own `partition.default_zoom_level` = log 2 / log 1.2 (200%), no viewport/DPR emulation. Headed (window off-screen): innerWidth 720, outerWidth 1440, devicePixelRatio 2, visualViewport scale 1, screen 1920 → real browser zoom. No document overflow, day selection works, no control under 44 CSS px, one-day range renders 1 day → pass. Headless ignored the preference (inner=outer=1440, DPR 1) → recorded, not counted. Playwright `page.screenshot` under real zoom captured only a device-pixel quarter (invalid visual); CDP `Page.captureScreenshot` captures `zoom-real-200-cdp-{top,chart,table}.png` viewed: header collapses to menu, controls stack, hatch/solid bars and day buttons readable. Not a human Ctrl+ keypress, not a physical display test.

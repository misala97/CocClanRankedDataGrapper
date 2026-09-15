# MD-SELECTED-PRICE-IMPLEMENT-1 — implementation evidence

Implementer (Claude Opus 5, no subagents), 2026-09-15. All commands run by this worker in the candidate worktree `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts` (branch `codex/radar-selected-price-charts`, HEAD = base `daadf3868caedcb5db858378e919cba68b735f8a`, nothing committed). Python `py -3.12` (3.12.6); Node from `C:/Program Files/nodejs`; `personal_apps/node_modules` copied from the source workspace with robocopy (caches `.vite`/`.vitest` excluded), no install or download.

Attribution: **EXECUTED** below = run in this assignment on this machine. **SAVED** = the Researcher's 2026-09-15 arrays, reused as test input only. Nothing here is a live provider request, a database run or production evidence.

## 1. Candidate and carry

- Worktree created from the source workspace with `git worktree add -b codex/radar-selected-price-charts … daadf3868caedcb5db858378e919cba68b735f8a`; source branch/HEAD verified `codex/radar-ha1-us-daily-explore` / `daadf38…` before and after.
- 23/23 PLAN carry files copied byte-for-byte and SHA-256 verified before any candidate edit: `carry-manifest.json` (`all_match: true`). Candidate `HANDOFF.md` and `MD-SELECTED-PRICE-LEDGER.md` are updated afterwards by design; the other 21 stay identical to source.

## 2. Baselines before any application edit (EXECUTED)

| Command (cwd `personal_apps`) | Result |
| --- | --- |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | 269 passed, 1 skipped, **3 failed**: `test_radar_yahoo.py::test_daily_closes_{use_the_split_only_close_series_not_adjclose,survive_a_split_shaped_series,deduplicate_by_date_and_sort_oldest_first}` (fixture timestamps older than the adapter's rolling date floor; date-dependent, pre-existing) |
| `npx vitest run -c vite.radar.config.ts` | 50 files, 799 passed, **28 failed**, all in `static/radar/src/hub/pending.test.tsx` (pre-existing; matches the HA1 records) |

## 3. Backend (EXECUTED)

| Command | Result | Log |
| --- | --- | --- |
| `SELECTED_PRICE_EVIDENCE_FILE=… py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **139 passed** in 12.5 s (windows, saved-array normalization, chatter/tone, reader + SQLite SQL, coordinator with fake clocks, real spawned children, loopback bounded transport, route/shell/ops) | `logs/pytest-selected_price_unit.log` |
| Same regression command as the baseline | 269 passed, 1 skipped, the same 3 pre-existing failures — Yahoo default transport and callers unchanged | `logs/pytest-regression-tone-yahoo-ha1.log` |

Real spawned children (`child-lifecycle.json`, this machine's scheduling, not a guarantee):

| Case | Observed |
| --- | --- |
| Normal child | admission returned in <1 ms (request thread never waits); supervisor 0.81 s; exit 0; heavy modules loaded in child: none of flask, flask_sqlalchemy, sqlalchemy, extensions, models, app, auth |
| Production `fetch_child` in a spawned process, bad spec | `{'kind': 'invalid', 'reason': 'request_spec'}` in 0.77 s, exit 0, no network |
| Hanging child | configured deadline 6.0 s from before start; supervisor 6.22 s; terminated (exit −15) and reaped; a second chart during the hang answered `busy` and no second child started; not quarantined |
| Pipe-filling oversized child (4 MiB of frames) | cut off at the 512 KiB result bound after 1.11 s; terminated (exit −15) and reaped; counted `invalid`; nothing cached |

Cleanup-failure quarantine, rolling-start cap, per-chart interval, cooldowns, Retry-After ladder/day cap, stale expiry, LRU/byte bounds and identity invalidation are proved with the injected clock/launcher (`test_acquisition.py`), not by waiting. After the runs no spawned child or QA process remained (read-only process listing).

SQL: every new statement is `SET STATEMENT max_statement_time=… FOR` on a MariaDB dialect (captured), each with its sentinel `LIMIT`; bucket/quote/daily/tone SQL executed on in-memory SQLite for syntax, expanding `IN`, filters, and tone classification parity. **No MariaDB/MySQL runtime evidence**: see limitations.

## 4. Frontend (EXECUTED)

| Command | Result |
| --- | --- |
| `npx tsc --noEmit` | exit 0 (`logs/tsc.log`) |
| `npx vite build -c vite.radar.config.ts` | exit 0; final bundle `assets/hub-BtAJD2zg.js`, `assets/hub-CfTgC9Wd.css` (`logs/vite-build-radar.log`). `static/radar/dist` is Git-ignored. Gym build not run. |
| `git -c safe.directory=* diff --check` | clean |

## 5. Final frontend runs on the final sources (EXECUTED)

| Command | Result | Log |
| --- | --- | --- |
| `npx vitest run -c vite.radar.config.ts` (whole Radar suite) | 54 files; **847 passed, 28 failed** — all 28 in `hub/pending.test.tsx`, identical to the baseline count; +48 new tests | `logs/vitest-radar-full.log` |
| Focused: priceChart, selectedPriceGeometry, SelectedPriceChart, SelectedPriceSection, Admin, Research, ChatterWorkspace, queries, Hub, ChatterHistogram, PriceChart | 11 files, 180 passed (before the last two wording fixes); after them the three chart suites 30/30 and the whole suite above | `logs/vitest-focused.log` |
| `npx tsc --noEmit` | exit 0 | `logs/tsc.log` |

## 6. Built-hub browser QA — FIXTURE evidence (EXECUTED)

`py -3.12 -u radar-design/artifacts/md-selected-price-implementation/browser/verify_browser.py` (python-playwright 1.x, Chromium). Run 3 on the final bundle `hub-BtAJD2zg.js`: **57 cases, 744 checks, 0 failures**, no request reached the loopback server outside the page/static files, port 5042 free afterwards, 120 s. Results `browser/results.json`; log `logs/verify_browser.run3.log`; 109 PNGs in `browser/screenshots/`.

- Server: a thread inside the script on 127.0.0.1:5042 (checked free first) rendering the real `templates/radar/hub.html` with a synthetic shell and serving only candidate `personal_apps/static`. No Flask app, database or provider.
- API: every `/radar/api/*` answered by `page.route`. Price-chart answers are `fixtures/price-*.json` produced by `fixtures.py` through the REAL `price_chart_reader.build_response` over the unit suite's fake store/admission (Yahoo series = SAVED arrays + synthetic meta; everything else synthetic). `fixtures/manifest.json` records states and file hashes.
- Coverage: states `ordinary` (1W ready, AAPL saved 5d/5m), `partial_gap` (1D ready, AAPL saved 1d/1m, unknown hour, truncated bucket, Reddit overlap), `stale` (receipt 249 s old, refresh pending), `fallback` (MSFT stored Finnhub quotes, 90-minute gap, pending), `unavailable` (NVDA backoff, no price, day-and-a-half unknown chatter), `long` (BRK.B stored daily closes, long venue, config change, overlap, off-grid row), on both Research and the Human Chatter research panel at 1440/768/390/320 (touch emulation under 768; `stale` at 1440/390); `stale-switch` at 1440/390; 422 `unsupported` at 1440/390; flag off at 1440; REAL 200% zoom (headed Chromium default page zoom, windows 640/780 device px = 320/390 CSS px, DPR 2 and outer = 2 × inner asserted) for `ordinary` and `partial_gap` on both surfaces.
- Checks per case include: no document horizontal overflow; new chart present and old chart absent; the chart request carries exactly `market, sources, span`; ET session dates in the header; `now` only on live windows, `session end` otherwise; summary names the company; no return/direction wording; narrow scroller opens at the newest end; the chart group is reachable with Tab, End/ArrowLeft/Home readouts report interval, count and price, focus outline visible; no page errors; no unmocked API request. Flag off: original chart, no chart request, and the headline price/provenance text identical to the flag-on page. Unsupported: original chart kept. Stale switch: a held AAPL answer released after the reader moved to MSFT never replaced MSFT's chart.
- Viewed by the worker: ordinary-research-1440, partial_gap-chatter-1440, fallback-research-768, unavailable-chatter-390, unavailable-research-1440, long-research-320, long-chatter-768, partial_gap-research-320, stale-research-1440, stale-switch-1440 (run 1) and -390, ordinary-chatter-390-focus, zoom200-ordinary-research-320css(-focus), zoom200-partial_gap-chatter-390css(-focus), flag-off-research-1440, unsupported-research-1440/-390.
- Found and fixed through the browser runs: Chromium's `en-GB` day padding ("Wed 09 Sep") and ICU's "Sept" (dates now built from numeric parts); 1W tick labels printing over the end label (start/end labels moved to their own axis line). Harness-only fixes: SVG `innerText`, fixture lookup, header-aware capture framing.
- Capture framing limitation: the top-anchored real-zoom captures show the headline above the chart; the `-focus` real-zoom captures show the chart itself. The zoom checks are metric/DOM assertions, not the images.

## 7. Candidate fingerprint (EXECUTED)

`py -3.12 radar-design/artifacts/md-selected-price-implementation/fingerprint.py` → `fingerprint.json`: digest **218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159** over 16 modified + 27 added application/test files under `personal_apps` (LF-normalized) and the 5 generated `static/radar/dist` files (bytes). Any later edit or rebuild changes it.

## 8. What was not executed

- No live Yahoo (or any provider) request; `period1/period2` request form, closed/overnight/holiday answers and real throttling behaviour are unverified. The loopback test proves the query string this code sends, not Yahoo's answer to it.
- No MariaDB/MySQL runtime: statement timeout firing, cancellation, plans and pool behaviour are unverified. The only MariaDB binary here lives in the protected HA1 environment; MySQL 8 is another engine and the protected 3306 installation.
- DB-backed suites not run (they import the app against the protected dev database): `test_radar_operations_api.py` (whose exact key set this change updated), `test_radar_hub_page.py`, `test_radar_api.py`, `test_radar_detail.py`. The DB-free `test_radar_chatter_tone.py`, `test_radar_yahoo.py` and `ha1_unit` did run (section 3).
- No gunicorn multi-worker run; process-scoped limits are proved per coordinator instance only.

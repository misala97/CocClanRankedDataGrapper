# HA1 FINAL-UI-CHECK evidence — Implementer / local QA operator, 2026-09-15

Assignment HA1-US-DAILY-EXPLORE-FINAL-UI-CHECK (F1 only). Claude Opus 5, no subagents. Every command below was executed fresh by this operator against the retained authorized HA1 environment only. Synthetic fixtures. No production, provider, commit, push or deployment. Backend, performance, API and mutation acceptance is carried from LOCAL-QA (ruled accepted) and was not rerun: no backend file changed.

## Git

Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`, no upstream. Start: tracked diffstat 14 files +1096/−35, 65 status entries (includes Mastermind's new ruling/prompt). Per-command `safe.directory`; nothing committed.

## F1 change

- `personal_apps/static/radar/src/hub/analysis.css`, inside the existing `@media (max-width: 400px)` block: `.rh-an-range { grid-template-columns: 1fr; }` plus a two-line comment. At <=400 px the From field, To field and submit button stack; each input spans the form (320: 252×44 px; 390: 322×44 px). 401–760 px keeps the two-column grid; >760 px keeps the three-column row. No markup, validation, navigation or other rule changed.
- Regression `personal_apps/static/radar/src/hub/analysisCss.test.ts`, describe "range fields keep a whole date visible at 320px (F1)": stacking rule at 400 px (failing first: `1 failed | 10 passed`), and inputs keep `min-width: 0; width: 100%` at 760 px.
- Actual-app assertion `personal_apps/scratchpad/ha1/verify_preview.py`: `DATE_CLIP_JS` measures each range input's `scrollWidth` vs `clientWidth` AND the value's rendered text width (canvas `measureText` with the computed font) vs the content box (clientWidth − padding). Every `viewport_<width>` case now requires two inputs holding 10-character values, none clipped. Static harness test `test_every_viewport_asserts_the_range_inputs_show_whole_dates`. The measurement covers the standard dates tested, not arbitrary text.

## Tests, build, fingerprint

| Command (cwd personal_apps) | Result | Log |
| --- | --- | --- |
| `npx vitest run -c vite.radar.config.ts static/radar/src/hub/analysisCss.test.ts` before the CSS change | 1 failed, 10 passed (the new stacking test) | console |
| `npx vitest run -c vite.radar.config.ts` 10 HA1 hub files (navigation, Hub, queries, analysisApi, analysisQueries, Analysis, AnalysisChart, analysisCss, Chatter, ChatterWorkspace) | 10 files, **232 passed** | `vitest-focused.out.txt` |
| `py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py pytest` | **241 passed**, app/pymysql not imported | `pytest-ha1_unit.out.txt` |
| `npm run build` (tsc --noEmit + gym + radar Vite) | passed; radar CSS `hub-wkhbpWXX.css` (was `hub-Dwv8T12n.css`) | `build.out.txt` |
| `ha1_harness.source_fingerprint` after build | **`6588be5e8dabf471befda62addc380d0775703948a5e7d22a9d96f55a2e50886`** (154 inputs, 5 build files); served and verified by preflight + end check | `fingerprint-after-build.json` |

## Environment and recovery

- `C:\Users\michi\.radar-ha1-local-qa` (environment.md). Before start: recorded PID 24776 not running, 3461 and 5041 not listening, 3306 listening (protected MySQL80, untouched), no assignment processes.
- `setup.ps1 -StartOnly` → `mariadbd.exe` PID 36868 on 127.0.0.1:3461 (executable path matched). Log (`restart-recovery.mariadbd.err.txt`): Aria recovery done; InnoDB `Starting crash recovery from checkpoint LSN=71383551` → `End of log at LSN=115222349`, `To recover: 1112 pages`, `ready for connections`.
- Post-recovery `CHECK TABLE` radar_ticker_universe, radar_instruments, radar_daily_closes, radar_bucket_sources, app_user, alembic_version: all `OK`; alembic `b7e3f9c1a2d4`; radar rows 0/0/0/0; app_user id 1 `admin`, id 2 `zq-ha1-localqa-admin`. Only then were fixtures seeded.
- `preview_fixtures.py seed`: 15 owned cases on `127.0.0.1:3461/radar_ha1_localqa`, window 2026-09-08..14.
- `local_runtime.py serve 5041`: py 36432 → python 27092, fingerprint `6588be5e…`.

## Focused actual-app check — `final_ui_check.py`, 0 failures (`final_ui_check.out.json`)

Gated by `verify_preview.preflight` (target, registry, runtime record, nonce, live pid, branch/HEAD, current fingerprint, manifest). Owned `typical` fixture. Per context: values at rest and focused/End; keyboard editing; >=44 px fields and submit; no document overflow; one-day submission with exact request; refresh restores values, request and day count; Back restores the week; malformed raw input `2026-9-8x`.

| Context | Mode | CSS width | Layout | Inputs at rest (scrollWidth/clientWidth; text/content px) | Focus scrollLeft | Submit | Checks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 320 | viewport emulation, DPR 1, touch | 320 | stacked | 250/250; 94.3/228 and 91.1/228 | 0, 0 | 252×44 | 23 |
| 390 | viewport emulation, DPR 1, touch | 390 | stacked | 320/320; 94.3/298 | 0, 0 | 322×44 | 23 |
| 768 | viewport | 768 | two-column | 237/237; 94.3/215 | 0, 0 | 129×44 | 23 |
| 1440 | desktop viewport | 1440 | three-column row | 193/193; 76.6/171 | 0, 0 | 129×44 | 23 |
| zoom200-real-320css | REAL browser zoom 200% (headed Chromium default_zoom_level preference, 640 px window) | 312 (+scrollbar); inner 320, outer 640, DPR 2, visualViewport 1 | stacked | 243/243; 94.3/221 | 0, 0 | 244×44 | 24 |
| zoom200-real-390css | REAL browser zoom 200% (780 px window) | 382; inner 390, outer 780, DPR 2 | stacked | 313/313; 94.3/291 | 0, 0 | 314×44 | 24 |

Malformed input in every context: value `2026-9-8x` kept in the field, `aria-invalid="true"`, `aria-describedby="rh-an-rangeproblem"`, `role=alert` notice `Dates must be written YYYY-MM-DD and be real calendar days. Asked for “2026-9-8x” to “2026-09-14”.`, 0 company requests, value not clipped, no overflow. No control under 44 px at <=860 px or real zoom.

## Full preview regression — `verify_preview.py 5041` run5 (`run5/verify_preview.json`)

58/58 cases, 0 failures, 295 checks (285 + new date checks), 181.1 s, fingerprint `6588be5e…` start and end. New `date_inputs` facts: 1440/1920 193/193, 768 237/237, 390 320/320, 320 250/250 — all `clipped: false`. Board-quiet 130/130 s with 0 board requests; touch targets 390/320 none small; emulated zoom_200 none small. Injected loading/timeout/network/session states remain UI-only interception checks.

## Screenshots viewed by this operator

`320-rest.png`, `320-focus.png`, `320-malformed.png` (emulated 320): full `2026-09-08`/`2026-09-14`, stacked, focus ring, raw `2026-9-8x` with notice. `390-rest.png` (emulated 390): stacked, full dates. `768-rest.png`: two-column row, full dates, layout sensible. `1440-malformed.png`: desktop row unchanged, raw value + notice. `zoom200-real-320css-rest.png`, `zoom200-real-320css-focus.png`, `zoom200-real-390css-malformed.png` (REAL zoom, CDP surface captures): full dates at 2× scale, caret after `14`, malformed disclosure. All under `radar-design/artifacts/ha1/final-ui-check/`.

## Cleanup

- `preview_fixtures.py cleanup` → removed the owned preview fixtures, exit 0, manifest removed (copy `preview-fixtures.manifest.before-cleanup.json`). Residual (`residual-db.out.txt`): radar tables 0/0/0/0; app_user ids 1/2 unchanged (environment, retained).
- Preview server: polite `taskkill /PID 27092` refused (`must be forcibly terminated (/F)` — hidden console process), then `Stop-Process` on 27092 and launcher 36432 after command-line match.
- MariaDB: graceful SQL `SHUTDOWN` as root → `Normal shutdown … InnoDB: Shutdown completed; log sequence number 116718975 … Shutdown complete` (`shutdown.mariadbd.err.txt`); process 36868 exited.
- After: 3461 and 5041 not listening; 0 processes with `scratchpad/ha1` or `radar-ha1-local-qa` in the command line; 3306 still listening (untouched). Environment directory, data and logs retained.
- `artifacts/ha1/runtime/preview-runtime-5041.json` overwritten by this run's server (dead pid now; historical); `artifacts/ha1/preview/*` overwritten by run5 and copied to `run5/`.

## Observations (not fixed)

- F2 retrospective caveat wrap: deferred per ruling, unchanged.
- The hub header's global search placeholder is truncated at 320/390 and under real zoom (`Find a`, `Find a compan`). That is the shared hub header, not the Analysis range form; it was already visible in LOCAL-QA screenshots and is outside F1 scope. Reported, not changed.
- 390 px now also stacks the range fields (rule applies at <=400 px); previously two columns fit at 390. Both are full-width, >=44 px and unclipped.

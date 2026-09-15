# HA1 US Daily Explore — FINAL-UI-CHECK return (F1)

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-FINAL-UI-CHECK · Radar Implementer / local QA operator (Claude Opus 5). Subagents/workers: none. Binding: `HA1-US-DAILY-EXPLORE-FINAL-UI-CHECK-PROMPT.md`, `HA1-US-DAILY-EXPLORE-LOCAL-QA-RULING.md`. Evidence: `artifacts/ha1/final-ui-check/evidence.md`.

**Disposition.** F1 resolved. At <=400 CSS px the range form stacks, so each date field spans the form. 320 px fields are 252×44 with no in-control clipping at rest, focus or editing, and the same holds under real 200% browser zoom at 320/390 CSS px. Malformed raw input stays visible and disclosed. Range submission, refresh and Back work. Wider layouts are unchanged. Build fingerprint `6588be5e8dabf471befda62addc380d0775703948a5e7d22a9d96f55a2e50886`. Environment recovered cleanly and shut down gracefully; fixtures cleaned. F2 deferred. No commit/push/deploy.

## 1. Git and owned changes

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`; branch `codex/radar-ha1-us-daily-explore`; HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`; no upstream; uncommitted.
- Product: `personal_apps/static/radar/src/hub/analysis.css` — in `@media (max-width: 400px)`: `.rh-an-range { grid-template-columns: 1fr; }` + comment. No markup change.
- Regression: `personal_apps/static/radar/src/hub/analysisCss.test.ts` (+1 describe, 2 tests; failing first).
- Harness: `personal_apps/scratchpad/ha1/verify_preview.py` (`DATE_CLIP_JS`, date assertion in every `viewport_<width>` case); `personal_apps/tests/ha1_unit/test_ha1_harness.py` (+1 static test).
- Evidence (new): `radar-design/artifacts/ha1/final-ui-check/*` including `final_ui_check.py`, `run5/`. Harness-written runtime/preview records were overwritten (`artifacts/ha1/runtime/preview-runtime-5041.json`, `artifacts/ha1/preview/*`).
- Continuity: this return; current notices in `HANDOFF.md`, `radar-design/HANDOFF.md`, HA1 ledger, `MASTERMIND-STATE.md`, `ASSIGNMENTS.md` (+row).
- Ignored build output: `static/radar/dist`, `static/gym/dist`.
- All prior dirt and historical reports preserved. `dashboard.lock` disappearance remains unattributed; nothing recreated or deleted.

## 2. Verification (fresh)

- Vitest HA1 hub suites: 10 files **232 passed** (new test first failed 1/11).
- `ha1_unit` under the REVIEW-2 socket guard: **241 passed**.
- `npm run build` (typecheck + both Vite builds): passed.
- Fingerprint after build: `6588be5e…` (154 inputs, 5 build files).
- Not rerun, per assignment (no backend change; acceptance carried from ruled LOCAL-QA): backend API suite, performance probe, mutation suite.

## 3. Actual-app evidence

`final_ui_check.py`: 0 failures, 140 checks.

| Context | Mode | Fields | Result |
| --- | --- | --- | --- |
| 320 | viewport emulation | stacked, 252×44 | 250/250 px at rest; focus scrollLeft 0 |
| 390 | viewport emulation | stacked, 322×44 | 320/320 px |
| 768 | viewport | two columns | 237/237 px |
| 1440 | desktop viewport | row | 193/193 px |
| real 320 CSS | headed Chromium, 200% zoom preference, 640 px window | stacked, 245×44 | inner 320 / outer 640, DPR 2 |
| real 390 CSS | same, 780 px window | stacked, 315×44 | inner 390 / outer 780, DPR 2 |

Every context:
- no page overflow
- keyboard editing
- one-day submit with exact request
- refresh restores values, request and one day
- Back restores the week
- `2026-9-8x` kept, `aria-invalid=true`, described by the `role=alert` notice quoting it, no request

`verify_preview.py 5041` run5: 58/58 cases, 295 checks, 0 failures; new date facts `clipped: false` at 1440/1920/768/390/320.

Viewed screenshots (all in `artifacts/ha1/final-ui-check/`):
- `320-rest`, `320-focus`, `320-malformed`, `390-rest` (emulated)
- `768-rest`, `1440-malformed`
- `zoom200-real-320css-rest`, `zoom200-real-320css-focus`, `zoom200-real-390css-malformed` (real zoom, CDP captures)

Real zoom is headed-browser page zoom, distinct from viewport/DPR emulation and not a physical device.

## 4. Environment, recovery, cleanup

- Target `127.0.0.1:3461/radar_ha1_localqa`, registry `C:\Users\michi\.radar-ha1-local-qa\registry.json`.
- Pre-start: old PID gone, ports free, 3306 protected listener untouched.
- `setup.ps1 -StartOnly` started `mariadbd` PID 36868.
- InnoDB crash recovery: checkpoint 71383551 → end 115222349, 1112 pages, `ready for connections`. `CHECK TABLE` OK on the 4 radar tables, app_user and alembic_version; 0 radar rows before seeding.
- Owned fixtures seeded (15 cases) and cleaned (exit 0, manifest removed); radar rows 0/0/0/0 after.
- Preview 5041 (py 36432 / python 27092): polite taskkill refused for the hidden console process, then stopped by PID after command-line match.
- MariaDB: graceful SQL `SHUTDOWN` → `Shutdown complete`.
- After: 3461/5041 not listening, no assignment processes; data, logs and environment retained.

## 5. Remaining findings

- F2 caveat wrap: deferred, unchanged.
- Observation, out of scope: the shared hub header's search placeholder truncates at 320/390 and under real zoom. Pre-existing, not part of the Analysis range form. Reported only.
- Scope note: 390 px also stacks now (rule at <=400 px), with full-width, unclipped 44 px fields.
- No new Analysis defect found.

## 6. Protected / not done

No production host, production data or providers were touched. No commit, push, merge, deploy, capture or service change, and no workers.

Also untouched:
- main and other worktrees
- B1C and port 5021
- DB 3306 and 3399
- promotion port 5033

Capture OFF / shared boards ON / migration `b7e3f9c1a2d4` remain release-attributed.

Requested decision: final HA1 readiness assessment. Deployment remains separately unauthorized.

# HA1 US Daily Explore — LOCAL-QA return

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-LOCAL-QA · Radar Implementer / local QA operator (Claude Opus 5). Subagents/workers: none. Binding: `HA1-US-DAILY-EXPLORE-LOCAL-QA-PROMPT.md`, `HA1-US-DAILY-EXPLORE-CORRECTION-2-RULING.md`, `HA1-US-DAILY-EXPLORE-REVIEW-2-RULING.md`, SPEC/PLAN. Evidence: `artifacts/ha1/local-qa/evidence.md` (commands, numbers, viewed screenshots) and `artifacts/ha1/local-qa/environment.md`.

**Disposition.** Hatch fixed and verified at runtime. A new disposable MariaDB 10.11.14 HA1 instance was created, gated and used; all runtime gates executed on it. Final candidate fingerprint `8781d5381f8141f28720a469e3c415fe64f84a032b4a3dce952450398fde36c9`: gated API suite 31/31, probe 0 failures, actual-app QA 58/58 cases (285 checks) at 1440/1920/768/390/320, real 200% browser zoom evidenced. Eight bounded harness corrections were needed to make intended assertions valid (none loosened; two add checks). Open for Mastermind: deadline overshoot values, one minor 320 px input clipping finding (F1), minor copy wrap (F2), a disappeared unexplained lock file, and the traced-read statement-limit observation. No commit/push/deploy/production/provider.

## 1. Git and scope

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`; branch `codex/radar-ha1-us-daily-explore`; HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`; no upstream. Verified start/end with per-command `safe.directory`; global config unchanged. Tracked diff 14 files +1040/−35 unchanged by the QA work (tracked edits here are continuity notices only); `git diff --check` 0.
- Owned edits:
  - Product (hatch): `personal_apps/static/radar/src/hub/analysis.css` (`.rh-an-fill` → `.rh-an-fill:not(.partial)`, +comment); regression `personal_apps/static/radar/src/hub/analysisCss.test.ts` (new describe, 2 tests).
  - Harness: `personal_apps/scratchpad/ha1/{ha1_harness,ha1_fixtures,verify_preview,probe_analysis}.py`; tests `personal_apps/tests/ha1_unit/test_ha1_harness.py` (+5 tests).
  - Evidence (new): `radar-design/artifacts/ha1/local-qa/*` (reports, run2/run3/run4 copies, diag scripts, mutation check, env record); harness-written `radar-design/artifacts/ha1/runtime/{preview-runtime-5041.json,preview-runtime-5061.json,probe_analysis.json}` and `radar-design/artifacts/ha1/preview/*`.
  - Continuity: this return; current notices in `HANDOFF.md`, `radar-design/HANDOFF.md`, HA1 ledger, `MASTERMIND-STATE.md`, `ASSIGNMENTS.md`.
  - Ignored outputs rebuilt: `static/radar/dist`, `static/gym/dist`, `__pycache__`.
  - Outside the repository: `C:\Users\michi\.radar-ha1-local-qa\` (environment, retained).
- **Unexplained file disappeared:** `personal_apps/downloaded_files/dashboard.lock` (and its directory) was present at start (63 status entries) and absent later (62). No command here referenced it; no copy exists elsewhere under CodingStuff/Temp. Cause not established; not attributed.

## 2. Environment (no secrets)

- Tooling found: MySQL 8.0.46 service on 3306 (protected, not MariaDB, untouched); Docker/WSL present, not used; a portable MariaDB 10.11.14 binary tree in an earlier Claude session scratchpad — copied (not modified, not executed in place).
- Instance: `C:\Users\michi\.radar-ha1-local-qa\mariadb-10.11.14-winx64\bin\mariadbd.exe` (`10.11.14-MariaDB for Win64`), new data dir `C:\Users\michi\.radar-ha1-local-qa\data`, logs `…\logs`, hidden `Start-Process`, `127.0.0.1:3461` only.
- Target: DB `radar_ha1_localqa`, user `ha1qa@127.0.0.1`, target `127.0.0.1:3461/radar_ha1_localqa`, dedicated registry `C:\Users\michi\.radar-ha1-local-qa\registry.json`. Credentials in `secrets.json` there, loaded by `env.ps1`, never printed.
- Schema: candidate migrations only → head `b7e3f9c1a2d4`, 47 tables (local fact only). Gate proven: the first migration attempt was refused (registry BOM) before any SQL.
- Hardware: i9-11900K 8C/16T, 31.9 GiB, Windows 11 10.0.26200, Python 3.12.6, Chromium 149.
- Preview: 5041. Port 5061 was abandoned because Chromium blocks it (`ERR_UNSAFE_PORT`).
- Owned processes: `mariadbd` PID 24776; six preview server launches (py + python pairs); all stopped (§8).

## 3. Hatch fix (step 1)

- Failing first: new CSS test 2 failed / 7 passed. After fix: focused 3 files 40 passed; HA1 frontend list 10 files 230 passed; `npm run build` passed (final build before serving, then fingerprint above).
- Runtime: computed partial fill `url("#rh-an-hatch")` at 1440 and 390; screenshots show hatched partial bars with `*` next to solid full bars (also under real zoom); contrast full fill and partial stroke 7.82:1. `AnalysisChart.tsx` unchanged.

## 4. Per-gate results (fresh, synthetic, this operator)

| Gate | Result | Evidence |
| --- | --- | --- |
| C02 identity/transport | PASS (local) | API suite: resolve 404/409/422, stale 409/404, 400 codes; browser `stale_link_409`, `ineligible_422`, `ambiguous_resolve_409` |
| C11 auth | PASS (local) | signed-out 302; loopback non-admin 200 (API + browser); `FULL_ACCESS_HOST` non-admin exactly 403 on company and resolve via Flask test-client host sessions only (no network contact); injection-style ticker 400 |
| C13 bounds | PASS | 4 data statements; EXPLAIN const/PRIMARY, const/PRIMARY, range/`uq_radar_daily_close_market`, range/PRIMARY; max 43,008 rows/64 sources; 111,050 bytes; traced reader allocation 26,195,307 B (25.0 MiB); 65 sources → 503 `analysis_limit`; 43,009th row → 503, 200 after removal |
| C14 timeouts/latency | PASS (semantics); overshoot for ruling | SLEEP@1 s 1969 at 1.005 s; CPU row scan@1 s 1969 at 1.009 s; CPU@0.250 s rendered `max_statement_time=0.250`, 1969 at 0.264 s; post-hoc budget refused; same connection 33→33, session limit 0.0→0.0, `SELECT 1` recovery; 503 translation (`analysis_unavailable` + `analysis_limit`); warm max p95 **781.18 ms** (median 752.13, cold 716.27) |
| C15 routes | PASS | run4: root/alias/legacy + return, signed-out redirects, `t`/hash/invalid-hash/filter-only+refresh, canonical link exact request, pin adds exactly one history entry, URL stable after 1.5 s, Back/Forward, **0 board requests in 130 s** (30 s progress segments) with positive control |
| C16 app QA | PASS with open F1 | run4 58/58 at 1440/1920/768/390/320: states, keyboard/table/skip/Tab order/Escape, taps + scroll-box reach, 44 px, contrast text ≥6.19 / graphics ≥6.19, alignment max 0.07 px (1440) / 0.33 px (390), price runs `[0,1,2,3]` with weekend break, reduced motion, non-admin, source/build identity start+end |

## 5. Performance and deadline measurements (ruling required)

- Statement interruption delay: CPU 0.009 s over 1 s; sub-second 0.014 s over 0.250 s; SLEEP 0.005 s.
- Reader budget exhaustion (identity/closes statements spend their handed limits): 503 `analysis_limit`, elapsed **5.052 s → overshoot 0.052 s**, handed [2.0, 2.0, 1.079, 0.047] s.
- Full HTTP of the same: 503, **5,058.9 ms → overshoot 0.059 s**, 1.6 ms before first reader statement, handed [2.0, 2.0, 1.078, 0.031] s; next request 200.
- Normal reads: reader-only max 712–849 ms, HTTP warm p95 781 ms (≤1 s by ~219 ms margin on this hardware; not a production claim).
- Observation for ruling: `max_statement_time` bounds server execution, not client materialization — a traced bucket SELECT handed 2.0 s returned after 2.86–2.89 s client-side without interruption; another traced run was interrupted. The reader's post-hoc 5 s check is the only bound on client-side time.
- Engine observation: MariaDB 10.11.14 silently truncates `BENCHMARK()` under `max_statement_time` (returns 0, no error). Not used by the reader.

## 6. Harness corrections (bounded; disclosed; tested)

- H1: CPU timeout probe switched from `BENCHMARK` to a row scan (`CPU_PROBE_SQL`). Reason: the engine truncates `BENCHMARK` silently.
- H2: the 130 s board-quiet window is observed in ≤30 s segments with progress lines. The total is unchanged.
- H3: traced allocation reads only send a 30 s statement limit (`TRACED_STATEMENT_LIMIT_S`). Reason: `tracemalloc` made the reader breach 2 s. Time limits are asserted on untraced reads only, and the handed limit is recorded.
- H4: filter-only check uses parsed `t`. Reason: the substring `t=` matched inside `segment=`.
- H5: held routes are released before `unroute`.
- H6: skip link and Tab order are checked from a fresh tab, and the page must load with body focused (new check).
- H7: injected loading/timeout/network/session states run in fresh tabs and must prove the injection engaged: ≥1 held/aborted request, 302 for expiry (new checks). Reason: the shared tab served cached keys, so nothing was intercepted.
- H8: preview on 5041 instead of the Chromium-blocked 5061.

Unit suite `ha1_unit` under the REVIEW-2 socket guard: 236 → **240 passed**. Mutation check: **10/10** reverts caught, baseline clean. The harness tests were written after their edits; the mutation run is the catch evidence. The hatch test was failing-first. Isolation diagnosis for run2 failures: `diag_preview.out.json` (every injected state and the skip link pass in fresh contexts).

## 7. Browser evidence

- Viewed: typical-1440/390/320/768, lines-1440, empty-1440, partial_truncated_zero-1440, session-expired-1440, zoom-200 (emulated), limit_503-1440, stale-390, invalid-pinned-1440, loading-1440, zoom-real-200-cdp-top/chart. Listed in evidence §5.
- **Real zoom vs emulation:**
  - `zoom_200` (720×500 @2×) is emulation only.
  - `zoom_real.py`: headed Chromium with its own default page zoom preference at 200%, no emulation. Result: innerWidth 720 / outerWidth 1440, DPR 2, visualViewport 1, screen 1920. No overflow, day select works, no control under 44 px, range change works.
  - Headless ignored the preference; recorded, not counted.
  - Playwright screenshots under real zoom were invalid (quarter capture). CDP surface captures were used and viewed.
  - Not a human keypress or physical display.
- **Injected vs real:** loading/timeout/network/session are browser route interceptions (UI only). Real server behaviour:
  - 302 on the expired request.
  - `limit_503` from a real 65-source fixture.
  - The engine/API 503s in §4/§5.
- Touch is emulated (`has_touch`), not a physical device.

## 8. Cleanup and residual state

- Fixtures: preview cleanup exit 0, manifest removed (copy kept). Probe and diag cleanups complete. API tests clean per test. Radar tables 0/0/0/0 rows.
- `app_user` keeps id 1 `admin` (migration) and id 2 `zq-ha1-localqa-admin` (environment). Both are retained inside the data directory.
- Processes:
  - All preview servers stopped by PID after command-line match.
  - `mariadbd` 24776 stopped by PID after executable-path match. This was a hard stop: the log shows aborted pooled connections, and InnoDB recovery will run on the next start.
  - Listeners 3461/5041/5061 closed. No process with `scratchpad/ha1` or `radar-ha1-local-qa` in its command line remains. 3306 untouched.
- Retained:
  - `C:\Users\michi\.radar-ha1-local-qa\` (214.5 MB data, logs, scripts, secrets, registry).
  - Stale harness identity records `artifacts/ha1/runtime/preview-runtime-{5041,5061}.json` (dead PIDs; refused by the harness).
- Restart: `& 'C:\Users\michi\.radar-ha1-local-qa\setup.ps1' -StartOnly`.
- Removal (owner decision): see `environment.md` teardown. It deletes only that new directory.

## 9. Open findings for Mastermind

1. Deadline overshoot: reader 0.052 s, HTTP 0.059 s, interruption 0.009–0.014 s. Also the client-materialization observation in §5.
2. F1 (C16, minor product): at 320 px the date inputs clip their values (scrollWidth 126 > clientWidth 117). 390/768 fine. The harness does not detect in-control clipping.
3. F2 (minor copy/layout): on selected pages the retrospective caveat wraps with the company name appended.
4. Disappeared `dashboard.lock` (§1).
5. U11/U12/U13: nothing here demonstrated a material failure. EXPLAIN strict types all passed; no pin re-fire (history +1, URL stable).
6. Emulation-only items remain: touch and physical devices.

## 10. Protected state / actions not taken

Not touched:
- production host or data, and no providers
- DB 3306/3399, previews 5021/5033
- B1C and promotion targets, main and other worktrees, existing data directories
- global services and configuration

No commit, push, merge, deploy or capture. No workers.

Capture OFF / shared boards ON / migration `b7e3f9c1a2d4` remain release-attributed; the local schema is not a production fact.

Next bounded action: Mastermind rules on §9 and HA1 release readiness. Deployment remains separately unauthorized.

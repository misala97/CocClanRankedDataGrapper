# CURRENT — B1C Codex local review, 2026-09-13

This notice supersedes earlier claims that the whole B1C packet is complete. Initial verified HEAD c97583e on codex/radar-b1c was clean. Corrections and evidence are recorded in the following local commit; use git log for its full SHA. No main checkout, PERF3 files, production services or other worktrees were modified.

## Ruling

Local owner preview may continue. Final B1C acceptance is OPEN: the required busy-ticker tone latency target fails. Do not deploy, push, merge main, promote root, enable capture, or redispatch completed B1/PERF work.

## Corrections completed this review

- Bounded tone source-bucket reads to retained48h rather than loading full chart history.
- Fixed double counting of a mismatched source so valid other-source colours survive.
- Eligibility contradictions invalidate their whole source-bin.
- Restored the price line/session context that histogram mode had accidentally removed.
- Preserved pooled gaps and valid count partitions; normal baseline shares the count scale; zero-volume intervals can be selected.
- Bullish/bearish now use independent green/red instead of inheriting cyan price tokens; SVG labels readable. Legend swatch reflects the tone mix.
- Price and histogram use matching912-unit canvases; mobile explanatory text stays pinned while plots pan together.

## Fresh evidence and limits

- Backend9 passed in4.64s, including guarded real-SQL regression cases. Helper source mismatch test failed before its correction.
- Frontend75 tests across4 affected suites passed in12.65s; after the mobile text adjustment Research17 passed in2.93s. Final production build/typecheck passed after the mobile text adjustment.
- Local authenticated actual-app checks: price path plus histogram, correct computed green/red and light axis labels, no document overflow at1440/390/320, keyboard selection/Escape and pointer interval selection. Screenshots/JSON: radar-design/artifacts/b1c-resume/. These are disposable seeded data, not live market evidence; pointer-click emulation is not a physical-phone gesture test.
- Independent read-only corrective review found no new material defect in the backend fixes or restored-price/pooling changes. The subsequent colour/sticky-text changes were directly verified by Codex, not represented as independently reviewed.
- MySQL8.0.46 rollback-only fixture probe: quiet24events, busy20,000events;20samples per span. Two SQL queries per read; max incremental heap0.729MiB, below8MiB. All reserved probe tickers absent after rollback. Preview fixtures preserved.
- Busy added tone calculation:1D median280/p95320ms;1W500/613ms;3Y461/547ms. Targets100ms median/200ms p95 FAIL. Quiet reads7–10ms. Evidence: radar-design/artifacts/b1c-tone-probe.json; executable guarded probe personal_apps/scratchpad/b1c/probe_tone.py.
- Probe measures chart_tone directly, not paired full-detail HTTP requests. It is sufficient to establish the added-work failure, NOT completion of the endpoint acceptance matrix. Target MariaDB correctness/timing for new SQL remains unverified.

## Next bounded assignment

Inspect the new aggregate query's execution plan on the registered disposable target; reduce redundant per-event/per-category aggregation while preserving duplicate-membership and conflict checks. Re-run this same bounded fixture probe after a meaningful fix, then the missing paired endpoint/target-engine gate. Do not add a daemon, cache layer, migration or reopen PERF3 without an explicit ruling. If query-only correction cannot meet the target, return the measured trade-off rather than silently weakening the target.

## Local app and continuity

Keep http://127.0.0.1:5021/radar/hub/ running. Local-only b1cadmin / b1c-local-only; database personal_apps_radar_b1c. Restart from personal_apps using `py -3.12 scratchpad/b1c/serve_b1c.py`; launcher refuses a non-B1C database. Logs .b1c-preview.stdout.log/.stderr.log stay local. Do not seed or run destructive suites just to resume.

Gallery is preserved in the candidate; no remote action performed. Preserve protected owner files and historical evidence. Root HANDOFF.md is current; radar-design/HANDOFF.md contains old history below its pointer.

---
Earlier return is historical where it differs.
# CODEX-RETURN-B1C

## Result

Claude’s existing B1 candidate was completed locally on the existing worktree.
The runnable app is the dark Human Chatter hub with the retained-evidence tone
histogram and the ruled descriptive price narrative. No deployment, push, merge,
VPS change, or main-checkout edit was performed.

## Exact return location

- Workspace: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-b1c`
- Branch: `codex/radar-b1c`
- Implementation commit: `dda65fa` (`feat(radar): add B1C retained tone histogram`)
- Return-packet commit: the following local documentation commit; final `HEAD` and
  clean/dirty status are reported by Codex after this file is committed.
- Protected main checkout was not touched.

## Run it

- App already running locally at: `http://127.0.0.1:5021/radar/hub/`
- Local-only login: `b1cadmin` / `b1c-local-only`
- Open Human chatter from the top navigation to see the histogram.
- Disposable database: `personal_apps_radar_b1c`; the seed is guarded by the exact
  target plus independent registry in `personal_apps/scratchpad/b1c/`.

## What changed

- Added opt-in backend `chart_tone()` envelope from retained mention events, posts,
  materialized recorded judgments, and indexed source membership.
- Preserved authoritative chatter totals and reconciled every non-null slot into
  bullish, bearish, neutral, unjudged, and unavailable counts.
- Added hub-only stacked histogram with pooled long spans, explicit denominator
  percentages, grey unavailable states, hover/tap detail, and one focusable group
  for ArrowLeft/Right, Home, End, and Escape.
- Hub detail fetches use `tone=1` and a versioned cache key; the old detail API and
  `/radar/` area chart remain backward compatible.
- Carried Claude’s B1 gallery and dark workspace plus the measured descriptive price
  narrative fix.
- Added B1C seed-only preview enrichment so the disposable app visibly exercises
  recorded bullish/bearish/mixed judgments without changing production storage.

## Evidence

- Backend affected/API/detail suite: `128 passed`, 98 existing deprecation warnings.
- Tone unit suite: `7 passed`.
- Full general frontend suite: `32 files / 403 tests passed`.
- Full radar frontend suite: `45 files / 737 tests passed`.
- `npm run build`: TypeScript check, gym production build, and radar production build passed.
- Python syntax compilation passed for changed backend, seed, and preview helpers.
- Disposable DB integration: 1,432 judged mentions; bullish/bearish/neutral sample
  slots; zero exact-total reconciliation violations; authenticated `tone=1` 200;
  malformed `tone=2` 400.
- Playwright at 1440, 1920, 390, and 320px: histogram present; 320px overflow false;
  ArrowRight changed interval detail; Escape cleared it.
- Screenshots: `radar-design/artifacts/b1c-1440.png`, `b1c-1920.png`,
  `b1c-390.png`, `b1c-320.png`.

## Honest limitation / owner decisions

Tone evidence is deliberately retained for 48 hours. Older or unmatched chatter is
grey/unavailable even when the durable chart total remains present; no historic tone
was invented. Durable historical tone belongs to future HA work. Product ownership
still decides whether to promote the hub from opt-in and when to add that history.

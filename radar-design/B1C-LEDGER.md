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
# B1C progress ledger

Updated 2026-09-13 after implementation, verification, and independent read-only review.

Binding: `B1C-IMPLEMENTATION-PLAN.md`, `B1-TONE-CHART-ADDENDUM.md`, and `CLAUDE-B1C.md`.

## Workspace and boundary

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-b1c`
- Branch: `codex/radar-b1c`
- Base/deployed PERF3 commit: `ad531ef6d697eac7c67179a40d7fca56812095fd`
- Claude’s carried B1 commits: `020baee`, `df04fcf`
- Codex B1C integration is local only; no deploy, push, merge to main, VPS, capture, held-index, root-promotion, B2, history-engine, or provider work.
- PERF3 owner scripts `personal_apps/scratchpad/perf3/cleanup_preview.py` and `preview_perf3.py` were not touched.

## Work completed

| Task | Status | Evidence |
| --- | --- | --- |
| Integrate Claude’s B1 dark Human Chatter workspace/gallery onto PERF3 | Complete | Existing B1 commits retained; local app preview verified |
| Descriptive price narrative ruling | Complete | Carried Claude fix `df04fcf`; affected API/detail suite green |
| Opt-in recent tone envelope | Complete | `features/radar/chatter_tone.py`; `tone=1` only; legacy detail shape remains unchanged |
| Stacked interval histogram | Complete | `ChatterHistogram.tsx`; hub Research uses bars, old `/radar/` keeps area mode |
| Accessibility/mobile interaction | Complete | One focusable chart group; arrows/Home/End/Escape; Playwright 1440/1920/390/320 checks |
| Local preview account and seed | Complete | Guarded `b1cadmin` / `b1cplain`; disposable database `personal_apps_radar_b1c` |
| Independent review and return packet | Complete | `CODEX-RETURN-B1C.md`; final diff/scope review passed |

## Tone implementation ruling

- The authoritative denominator is the existing per-source bucket count; every non-null slot reconciles exactly across bullish, bearish, neutral, unjudged, and unavailable.
- Tone reads retained mention events joined to posts and mentions by `(source, external_id, ticker)`; eligibility mismatches are unavailable, not neutral.
- Recorded positive/negative/mixed/none attitudes and legacy model verdicts are classified; lexical-only scores never colour a bar.
- Retained tone coverage is 48 hours. Older, unmatched, malformed, or source-mismatched evidence remains grey/unavailable. Durable historical tone remains future HA work.
- The API accepts only `tone=1`; malformed nonempty values return 400. Hub detail requests opt in and cache keys carry tone schema version 1. Old board/detail callers keep the legacy payload and area renderer.

## Verification

- Backend focused: `128 passed, 98 warnings` — `tests/test_radar_chatter_tone.py`, `tests/test_radar_api.py`, `tests/test_radar_detail.py`.
- Tone unit contract: `7 passed`.
- Radar frontend: `45 files, 737 tests passed`.
- General frontend: `32 files, 403 tests passed`.
- `npm run build`: TypeScript plus gym and radar production Vite builds passed.
- Python syntax compilation passed for changed backend/seed/preview helpers.
- Disposable DB integration: `1,432` judged mentions; sample slots included bullish/bearish/neutral; zero reconciliation violations; authenticated `tone=1` returned 200/version 1; `tone=2` returned 400.
- Playwright: authenticated local hub screenshot set at 1440, 1920, 390, and 320px; histogram found; 320px horizontal overflow false; ArrowRight changed detail; Escape cleared detail.

## Current local app

- Runnable URL: `http://127.0.0.1:5021/radar/hub/`
- Local-only account: `b1cadmin` / `b1c-local-only`
- The server is intentionally loopback-only and must not be deployed from this packet.
- Screenshots: `radar-design/artifacts/b1c-1440.png`, `b1c-1920.png`, `b1c-390.png`, `b1c-320.png`.

## Remaining owner decisions

- Decide whether B1’s hub remains opt-in or is promoted later.
- Decide whether/when HA should persist durable historical tone. This delivery deliberately does not invent tone for the older chart span.

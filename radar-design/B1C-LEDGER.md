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

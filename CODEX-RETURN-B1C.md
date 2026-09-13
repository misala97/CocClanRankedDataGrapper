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

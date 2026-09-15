# MD-SELECTED-PRICE-REVIEW-1 — reviewer evidence

Independent Reviewer / QA (Claude Opus 5), 2026-09-15, no subagents. Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, HEAD = base `daadf3868caedcb5db858378e919cba68b735f8a`, uncommitted.

Attribution key: **FRESH** = executed by this reviewer in this assignment. **SAVED** = worker artifact inspected, not re-executed. **STATIC** = source reading/inference, no execution.

## 1. Candidate identity (FRESH)

| Check | Result |
| --- | --- |
| `git rev-parse --abbrev-ref HEAD` / `rev-parse HEAD` | `codex/radar-selected-price-charts` / `daadf3868caedcb5db858378e919cba68b735f8a` |
| `git status --porcelain` | 54 entries at start: 22 modified (16 personal_apps + HANDOFF + 5 radar-design carry docs), 32 untracked, matching the return's ownership split |
| `git diff --check` | clean (only CRLF conversion warnings on carried docs) |
| Read-only fingerprint recompute (`scratchpad/fp_readonly.py`, same algorithm as the worker's `fingerprint.py`, never writes) | digest `218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159` = recorded; counts 16 modified / 27 added / 5 generated; 0 mismatched paths. The worker's `fingerprint.py` was inspected and NOT run (it overwrites `fingerprint.json`). |

## 2. Backend (FRESH, cwd `personal_apps`, `py -3.12` 3.12.6)

Harness inspected first: `tests/selected_price_unit/helpers.py`, `test_route_ops.py` (minimal Flask app, auth helpers patched, fake store), `test_yahoo_bounded.py` (`yahoo.API_BASE` monkeypatched to a loopback server; unreachable-host case uses 127.0.0.1:9), `test_child_lifecycle.py` + `child_targets.py` (real spawn, IPC only; writes JSON only when `SELECTED_PRICE_EVIDENCE_FILE` is set). No provider, DB or network beyond loopback.

| Command | Result | Log |
| --- | --- | --- |
| `SELECTED_PRICE_EVIDENCE_FILE=<review>/child-lifecycle-review.json py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **139 passed** in 12.04 s | `logs/pytest-selected_price_unit.log` |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | **269 passed, 1 skipped, 3 failed** — the same three `test_radar_yahoo.py::test_daily_closes_*` tests the worker recorded as pre-existing | `logs/pytest-regression-tone-yahoo-ha1.log` |

Fresh real-child timings (`child-lifecycle-review.json`, this machine's scheduling): normal child supervisor 0.656 s, exit 0, heavy modules in child `[]` (under pytest, i.e. a module-named `__main__`); production child bad spec 0.719 s exit 0; hanging child terminated at 6.219 s supervisor time (deadline 6.0 s), exit −15, other chart `busy` meanwhile; oversized child cut at 0.859 s, exit −15. The worker's original `child-lifecycle.json` was not overwritten.

## 3. Frontend (FRESH, cwd `personal_apps`, Node from `C:/Program Files/nodejs`)

| Command | Result | Log |
| --- | --- | --- |
| `npx tsc --noEmit` (tsconfig has `noEmit: true`) | exit 0 | `logs/tsc.log` |
| `npx vitest run -c vite.radar.config.ts` filtered to hub/priceChart, hub/selectedPrice*, hub/SelectedPrice*, hub/Admin, hub/queries, hub/Research*, hub/ChatterWorkspace, hub/Hub, detail/ChatterHistogram, detail/PriceChart | **11 files, 180 passed** | `logs/vitest-focused.log` |
| `npx vite build -c vite.radar.config.ts --outDir <scratchpad>/radar-dist-review --emptyOutDir` (scratch output, candidate dist untouched) | exit 0; SHA-256 of all 5 output files **identical** to candidate `static/radar/dist` (`hub-BtAJD2zg.js`, `hub-CfTgC9Wd.css`, `board-rWQq9mLW.js`, `embedded-DT-Q2QoO.js`, `.vite/manifest.json`) | `logs/vite-build-scratch-outdir.log`, `logs/rebuild-hashes.txt`, `logs/candidate-dist-hashes.txt` |

Not re-executed: whole Radar Vitest (worker: 847 passed / 28 pre-existing `pending.test.tsx` failures) — unrelated files, not duplicated.

## 4. D17 spawn/launcher probe (FRESH)

`d17_spawn_main_probe.py` (this directory) uses the production `price_chart_acquisition.spawn_launcher()` and `price_chart_fetch.fetch_child` with a bad spec, which refuses before any transport exists (no network, no DB, no app import). Result `d17_probe.json`:

- **File-path `__main__`** (models `python app.py`, `py scratchpad/b1c/serve_b1c.py`): the child (pid 11196) appended a marker as `__mp_main__` — the launcher script's unguarded top level ran inside the fetch child — and saw the environment variable the parent set before spawn.
- **`-c` `__main__`** (models `python -c "from app import app; app.run(...)"`): the child executed no top level (only the parent's marker line).

Launcher inventory (STATIC): `personal_apps/app.py` top level bootstraps the app (`load_dotenv(override=True)` line 12, `db.init_app` 46, `from models import *` 49, all blueprints 52-66) with its own `__main__` entry at 188-196; tracked `personal_apps/scratchpad/b1c/serve_b1c.py:5` imports `app` unguarded; tracked `scratchpad/perf3/serve_perf3.py:27` calls `scale_env.bind()` unguarded (but is itself run through `scale_env.py`, not further traced); `scratchpad/ha1/local_runtime.py:124` imports the app inside a function (safe); `.claude/launch.json` uses `flask run` (pip console script, guarded `__main__`); production is release-attributed `gunicorn --workers 2` (pip console script, guarded) — gunicorn cannot run on this Windows machine, so the production case is inference, not execution.

## 5. Browser evidence (SAVED, recounted FRESH from JSON; not rerun)

`implementation/browser/results.json`: 57 cases (dict keyed by case), 744 checks, 0 non-true values, `server_404: []`, `port_free_after: true`, bundle `assets/hub-BtAJD2zg.js` (which the scratch rebuild reproduces byte-for-byte). Screenshots viewed by the reviewer: `ordinary-research-1440.png` (1W, five sessions, gaps, partial/unknown slots, end label "now 15:50 CEST", readout text), `fallback-chatter-390-focus.png` (1D stored Finnhub quotes, amber fallback provenance, keyboard readout), `zoom200-partial_gap-chatter-390css-focus.png` (real 200% zoom, legend wraps, chart readable), `long-research-320-focus.png` (1W stored daily closes, long venue wraps, adjustment basis "split", dominant partial outlines — disclosed UX tradeoff), `stale-switch-390.png` (MSFT chart with MSFT headline after a held AAPL reply). No new browser run was needed for any finding.

## 6. Not executed / limits

No live Yahoo or other provider request; no MariaDB/MySQL runtime; no DB-backed pytest (`test_radar_operations_api.py`, `test_radar_hub_page.py`, `test_radar_api.py`, `test_radar_detail.py`); no gunicorn or multi-worker run; no full browser rerun; no production access. Carried release limitations are unchanged and are not claimed passed.

## 7. Files written by the reviewer

This directory (`evidence.md`, `d17_spawn_main_probe.py`, `d17_probe.json`, `child-lifecycle-review.json`, `logs/*`), `radar-design/MD-SELECTED-PRICE-REVIEW-1-RETURN.md`, and short current notices at the top of candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`. Scratch-only: `<scratchpad>/fp_readonly.py`, `<scratchpad>/radar-dist-review/`. Pytest/probe imports may have refreshed ignored `__pycache__` files; they are excluded from the fingerprint.

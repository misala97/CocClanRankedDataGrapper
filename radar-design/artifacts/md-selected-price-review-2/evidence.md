# MD-SELECTED-PRICE-REVIEW-2 — reviewer evidence

2026-09-15. Radar Reviewer / QA (Claude Opus 5), no subagents. Scope: CORRECTION-1 only.

**Independence qualification:** this review ran in the same agent session that implemented CORRECTION-1. It is attributed here as executed checks plus source reading, NOT as an independent second pair of eyes in the WORKFLOW sense.

## Git and fingerprint (EXECUTED)

- Branch `codex/radar-selected-price-charts`, HEAD `daadf3868caedcb5db858378e919cba68b735f8a`, 62 status lines (intentional dirt), uncommitted.
- `py -3.12 radar-design/artifacts/md-selected-price-correction-1/fingerprint.py --check-only --compare …/fingerprint-final.json` → digest `ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce`, 16/29/5, 0 differing paths (`logs/fingerprint-recompute.log`). Read-only, nothing written.
- Independent re-hash of all 50 manifest entries with reviewer code (`post_popen_cleanup_repro.py`) → same digest, 0 mismatches.
- Implementation map (218c1a53…) vs correction map: 21 paths (`logs/fingerprint-map-diff.log`):
  - 15 changed: acquisition, fetch, dist manifest, Admin.test, Admin, ResearchContent, SelectedPriceChart, SelectedPriceSection.test, priceChart.ts, selected-price.css, child_targets, test_acquisition, test_child_lifecycle, test_route_ops, test_yahoo_bounded;
  - 4 added: hub-Bmvv_e8B.css, hub-CZqS9Prw.js, probe_child.py, test_launcher_isolation.py;
  - 2 removed: hub-BtAJD2zg.js, hub-CfTgC9Wd.css.

## Fresh checks (EXECUTED)

| Command | Result | Log |
| --- | --- | --- |
| `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` (cwd personal_apps) | 167 passed, 15.63 s (includes real subprocess normal/hang/oversized/stderr-flood/early-exit/garbage/exit-5 children and the file-path parent isolation test) | `logs/pytest-selected_price_unit.log` |
| `npx vitest run -c vite.radar.config.ts` on SelectedPriceSection, Admin, SelectedPriceChart, Research, ChatterWorkspace, queries, priceChart | 7 files, 117 passed | `logs/vitest-focused.log` |
| `npx tsc --noEmit` | exit 0 | `logs/tsc.log` |
| `npx vite build -c vite.radar.config.ts --outDir <temp> --emptyOutDir` (scratch, deleted after) | exit 0; all files byte-identical to candidate `static/radar/dist` | `logs/scratch-build-hashes.txt`, `logs/candidate-dist-hashes.txt` |
| `py -3.12 radar-design/artifacts/md-selected-price-review-2/post_popen_cleanup_repro.py` | see R2-1 | `post_popen_cleanup_repro.json`, `logs/post-popen-repro.log` |

Not run: whole Radar Vitest, tone/Yahoo/HA1 regression, browser suite (no concrete concern needing a new browser reproduction), DB/provider anything.

## Source inspection (EXECUTED)

**Launch.** `price_chart_acquisition.py:201-241` builds `[sys.executable, -E, -s, -B, -m, module, *args]` and calls Popen with:
- no `shell`, `env=child_environment()` (new dict from the allowlist, nt SYSTEMROOT / posix none);
- `cwd=APP_ROOT`;
- stdin/stdout PIPE, `stderr=DEVNULL`, `bufsize=0`.

The spec is refused above 2048 B before Popen.

**Test hooks cannot be selected by requests.**
- `module`/`args` are validated by `_MODULE_NAME` and string arguments.
- The only production construction is `coordinator()` → `Coordinator()` (`:599`), which takes the default launcher; `Admission.get_or_start` (`:608-611`) passes no launcher.
- Grep found no other `subprocess_launcher`/`Coordinator(` caller in `features/`.

**Child.** `price_chart_fetch.py:107-126`:
- reads at most 2049 bytes and refuses more than 2048;
- runs `run()` (spec validated by `contract._spec_ok`);
- writes one `encode_result` capped at 512 KiB and returns 0.

No shadowing risk from the application directory being first on `sys.path`: no top-level `personal_apps` module or package matches a stdlib name (`sys.stdlib_module_names`).

**Lifecycle.**
- The supervisor measures `started` before `_launch`, so the 6 s deadline includes startup.
- `Child.collect` (`:153-174`) returns `done` only after reader EOF plus exit 0 within the deadline.
- The reader stops at over-limit output.
- `Child.reap` (`:176-198`) runs wait → terminate → kill within cleanup_s, joins the reader, closes stdout only when the reader has ended, and returns exit AND reader confirmed; `_supervise` (`:398-411`) quarantines otherwise.
- The one-child/no-queue admission code is unchanged.

**Post-Popen exception path** (`:236-239` → `_kill_now` `:260-268`; `_supervise` `:391-396`): see R2-1.

**F3.** `ResearchContent.tsx`:
- `failed = selected && Boolean(error)` switches the caption to "not loaded";
- `SelectedChartBody` returns the alert/Retry before touching `data`;
- unsupported/disabled refusals still make `selected` false, so the original chart is drawn.

Tests cover live-session and remapped retained data, recovery, 200 stale, 200 stored fallback, unsupported-on-refresh and disabled. Research and ChatterWorkspace both render this ChartSection.

**F4.**
- `_configured_workers` accepts only a full ASCII-digit match greater than 0.
- `configured_web_workers_source` is `WEB_CONCURRENCY`.
- `coordinator_started_at` comes from `self._created = wall()` in `Coordinator.__init__`, and is null from `ops_snapshot` when no instance exists.
- Admin renders Unknown with the source, the day/time stamp or "not started in this process", PID and the note.
- No remaining `process_started_at` consumer (grep hits are only negative assertions in tests).

## R2-1 reproduction (EXECUTED, safe fakes)

`post_popen_cleanup_repro.py` runs the real `Coordinator` and the real `subprocess_launcher()` with `subprocess.Popen` replaced by an in-memory process. That process ignores kill/terminate, its `wait()` always raises `TimeoutExpired`, and its `poll()` stays `None`.

| Scenario | After first acquisition | Second, different chart |
| --- | --- | --- |
| Reader thread cannot start (post-Popen exception → `_kill_now`) | counters `invalid: 1`, **quarantined False**, kill called once, process still running | **`pending`, a second process started** (2 Popen) |
| Control: reader starts, child never answers, `Child.reap` unconfirmed | `timeout: 1`, `cleanup_failed: 1`, **quarantined True** | `unavailable` "cleanup_failed…", 1 Popen |

## Saved evidence inspected (CARRIED, worker-executed)

- `child-lifecycle.json`: normal 0.593 / hang 6.219 / oversized 0.812 / stderr flood 0.656 / early exit 0.563 / garbage 0.563 / exit-5 0.657 s.
- `launcher-isolation.json`:
  - the child had env keys `['SYSTEMROOT']`, no heavy modules, no sentinel, no hook, and the `-E/-s/-B` flags;
  - the parent script's top level ran once, in the parent;
  - one loopback request carried no Cookie or Proxy-Authorization.

  The probe child points `yahoo.API_BASE` at loopback, so this is synthetic transport proof, not a live Yahoo request.
- `failing_first_spawn.json`: historical, the pre-correction spawn launcher; not rerun.
- `browser/results.json` recounted: 12 cases, 96 checks, 0 false, no failures or server 404s, `hub-CZqS9Prw.js`, port free after.
- Screenshots viewed by the reviewer: `refresh-failure-research-390-failed`, `refresh-failure-chatter-1440-recovered`, `admin-unknown-1440`, `admin-configured-390`. Retry state without chart/now wording; recovered chart with its live labels; Unknown/not-started and 2 (from WEB_CONCURRENCY)/15 Sep 10:00 Berlin; no clipping.

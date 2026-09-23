# MD-SELECTED-PRICE-CORRECTION-1 — correction evidence

Implementer (Claude Opus 5, no subagents), 2026-09-15. Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, HEAD = base `daadf3868caedcb5db858378e919cba68b735f8a`, uncommitted. Python `py -3.12` (3.12.6, Windows 11); Node `C:/Program Files/nodejs`. Binding ruling: `radar-design/MD-SELECTED-PRICE-REVIEW-1-RULING.md`.

Attribution: **EXECUTED** = run by this worker in this assignment. Earlier implementation/review evidence is carried, not re-run, and its directories were not written.

## 1. Start verification (EXECUTED)

- Branch/HEAD verified; status matched the ruling's dirty set.
- `fingerprint.py --check-only --compare ../md-selected-price-implementation/fingerprint.json` → digest `218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159`, 16/27/5, **0 mismatches**. No unexpected application change.

## 2. Failing-first (EXECUTED, before any application edit)

| Check | Result | Artifact |
| --- | --- | --- |
| `failing_first_spawn_probe.py` (file-path `__main__`, top-level `import flask`, dummy sentinel) on the ORIGINAL spawn launcher | child pid 23728 ran the parent script as `__mp_main__`, had flask loaded through it, saw the sentinel; 0.922 s | `failing_first_spawn.json`, `logs/failing-first-spawn-probe.log` |
| New/changed backend tests on original code | 53 failed, 114 passed (no `subprocess_launcher`/`Child.collect`, no `coordinator_started_at`, `WEB_CONCURRENCY=0` → 0) | `logs/failing-first-pytest.log` (first invocation used an unsupported `--timeout` flag and did not run) |
| New frontend tests on original code | 6 failed, 29 passed: 4 refresh-failure cases (old chart + amber notice still drawn), 2 Admin label cases | `logs/failing-first-vitest.log` |

Qualification: one of the 6 (`unsupported` refusal on refresh → legacy chart) asserted synchronously after `act()`. It was changed to `waitFor` because TanStack notifies after `act()` resolves. It passes on the corrected code; whether the original code would pass with `waitFor` was not checked. The other test-only fix: the recovery test used `getAllByText` because the caption and chart header both repeat the title.

## 3. Final backend (EXECUTED)

| Command (cwd `personal_apps`) | Result | Log |
| --- | --- | --- |
| `SELECTED_PRICE_EVIDENCE_FILE=… SELECTED_PRICE_ISOLATION_EVIDENCE_FILE=… py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **167 passed** in 15.68 s | `logs/pytest-selected_price_unit.log` |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | 269 passed, 1 skipped, **the same 3 baseline** `test_daily_closes_*` failures | `logs/pytest-regression-tone-yahoo-ha1.log` |

### Real children through the production launcher (`child-lifecycle.json`; this machine's scheduling, not a guarantee)

| Case | Supervisor s | Exit | Facts |
| --- | --- | --- | --- |
| normal | 0.593 | 0 | admission 0.0 s; heavy modules in child none; child env keys `['SYSTEMROOT']` |
| production module, bad spec | 0.609 (wall) | 0 | `{'kind':'invalid','reason':'request_spec'}` |
| hanging (never answers) | 6.219 (wall to idle 6.235) | 1 (Windows TerminateProcess) | deadline 6.0 from before start; other chart `busy` meanwhile; one child only; not quarantined |
| oversized (4 MiB stdout) | 0.812 | 1 | cut at 512 KiB, terminated, counted invalid, nothing cached |
| stderr flood 8 MiB | 0.656 | 0 | success: stderr is the null device |
| early exit before reading stdin | 0.563 | 3 | invalid, no exception on the request write |
| garbage stdout | 0.563 | 0 | invalid |
| complete answer then exit 5 | 0.657 | 5 | invalid, not cached |

Every real case also asserts: `Popen.poll()` set, the pid is not alive according to the OS (`OpenProcess`/`GetExitCodeProcess`), the reader thread ended, and both stdin/stdout handles are closed.

### File-path parent isolation (`launcher-isolation.json`)

The pytest process starts `parent_launcher.py` by file path. Its environment has `PYTHONPATH` → a `sitecustomize.py` hook, `PYTHONSTARTUP`, credentialed `HTTP(S)_PROXY`, dummy `SECRET_KEY`/`DATABASE_URL`. The script itself sets `RADAR_SP_DUMMY_SECRET` at top level and runs the real `Coordinator` with `subprocess_launcher(module='tests.selected_price_unit.probe_child', …)`. The test child runs the production `price_chart_fetch.main()` against a loopback server.

- Parent: admission 0.015 s → `pending`; supervisor 0.578 s → `ready` with the 2 loopback bars; sentinel present; `dict(os.environ)` unchanged before/after.
- Marker: `sitecustomize` ran only in the parent pid 32612, and the script's top level ran once (as `__main__`) in that pid.
- Child pid 40740: `__main__.__spec__` = probe module; heavy modules (flask, flask_sqlalchemy, sqlalchemy, extensions, models, app, auth, dotenv, pymysql, MySQLdb) = none; env keys `['SYSTEMROOT']`; sentinel absent; hook not loaded; flags `-E`/`-s`/`-B` = 1.
- Loopback: exactly 1 request, headers `Accept, Accept-Encoding, Connection, Host, User-Agent` (no Cookie, no Proxy-Authorization, not routed via the dead proxy).

Unit checks in `test_launcher_isolation.py`:
- **Explicit allowlist.** A hostile mapping (PATH, HOME, PYTHON*, proxies, CA bundle, secrets, LD_PRELOAD) yields `{'SYSTEMROOT'}` on `nt` and `{}` on `posix`.
- **Popen arguments.** An argument list `[sys.executable, -E, -s, -B, -m, features.radar.price_chart_fetch]`, no shell, `env` = allowlist, stdin/stdout PIPE, stderr DEVNULL, cwd `personal_apps`, bufsize 0. `os.putenv`/`os.unsetenv` are never called and `os.environ` is unchanged.
- **Refusals before start.** An oversized spec or a malformed module name starts nothing.
- **Handle cleanup.** A `BrokenPipeError` on the request write is absorbed. A reader thread that cannot start kills the child and closes both pipes.
- **Quarantine.** Unconfirmed subprocess cleanup quarantines, and no second child starts.

The fake-clock coordinator tests are unchanged in substance (quota, per-chart interval, cooldowns, Retry-After ladder, day cap, stale expiry, LRU/bytes, identity invalidation, quarantine). Only their fake child moved to the new `collect`/`reap` contract.

## 4. Final frontend (EXECUTED)

| Command (cwd `personal_apps`) | Result | Log |
| --- | --- | --- |
| `npx vitest run -c vite.radar.config.ts` on 11 affected files (SelectedPriceSection, Admin, SelectedPriceChart, priceChart, selectedPriceGeometry, Research, ChatterWorkspace, queries, Hub, ChatterHistogram, PriceChart) | **188 passed** | `logs/vitest-focused.log` |
| `npx vitest run -c vite.radar.config.ts` (whole Radar suite; justified by the shared ChartSection change) | 855 passed, **28 failed — all `hub/pending.test.tsx`**, the baseline count | `logs/vitest-radar-full.log` |
| `npx tsc --noEmit` | exit 0 | `logs/tsc.log` |
| `npx vite build -c vite.radar.config.ts` | exit 0; `assets/hub-CZqS9Prw.js`, `assets/hub-Bmvv_e8B.css` (replacing hub-BtAJD2zg.js / hub-CfTgC9Wd.css) | `logs/vite-build-radar.log` |
| `git diff --check` | clean | — |

## 5. Built-hub browser check — FIXTURE evidence (EXECUTED)

`py -3.12 -u radar-design/artifacts/md-selected-price-correction-1/browser/verify_correction.py`: **12 cases, 96 checks, 0 failures**, 31.4 s. Port 127.0.0.1:5047 was checked free before and was free after, with no unmocked request.

- **Server and data.** An in-script thread serves the real `hub.html` and the new bundle. `/radar/api/*` is answered by `page.route`, and chart fixtures are read read-only from the implementation's `browser/fixtures/`.
- **Coverage.** 1440×1000 and 390×844 (touch). Research and Human Chatter: initial 503 → retry state; refresh failure; recovery. Admin: Unknown workers / not started, and 2 (from WEB_CONCURRENCY) / 15 Sep, 10:00 Berlin.
- **Refresh failure.** The answered `stale` 1D live chart first shows "Current session so far" and a "now 15:54" end label. When the 2-second pending poll fails, the retry state appears 2.88–2.89 s later with no svg, no now/current-session wording, no legacy chart, and the caption "Current or last session · not loaded". Request sequence: ok, fail, fail (the hook's one retry), then ok after Retry.
- **Screenshots.** 20 PNGs in `browser/screenshots/`. The worker viewed:
  - `refresh-failure-research-1440-{answered,failed,recovered}`
  - `refresh-failure-chatter-390-failed`
  - `initial-failure-chatter-390`
  - `admin-unknown-390`
  - `admin-configured-1440`

  All labels were readable, wrapping was clean, and nothing overflowed.

## 6. Final fingerprint (EXECUTED)

`py -3.12 radar-design/artifacts/md-selected-price-correction-1/fingerprint.py --compare ../md-selected-price-implementation/fingerprint.json` → `fingerprint-final.json`, digest **`ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce`** (16 modified / 29 added / 5 generated). The 21 paths that differ from 218c1a53… are listed in `logs/fingerprint-final.log`. The earlier `fingerprint.json` and all implementation/review artifacts are untouched.

## 7. Correction decisions (bounded, within the ruling)

| # | Decision | Reason |
| --- | --- | --- |
| C1 | `sys.executable -E -s -B -m features.radar.price_chart_fetch` with `cwd=personal_apps`, not `-I` | `-I` implies safe-path and drops the working directory, so `features` would not import. `-E` still ignores every PYTHON* variable (none are passed anyway), and `-s` drops user site. `requests`/`tzdata` were confirmed to import under `-E -s` from the global site-packages. |
| C2 | Allowlist `nt: SYSTEMROOT`, `posix: ()` | Empirical on Windows: with an empty environment, `socket()` fails with WinError 10106. No POSIX child was executed here (see limitations). |
| C3 | IPC: spec JSON on stdin (≤ 2048 B, written then closed); result JSON on stdout until EOF (≤ 512 KiB); `done` needs EOF plus exit 0 within the deadline; stderr → DEVNULL | 2048 B is under the smallest default pipe buffer (4 KiB Windows), so the request write never waits on the child. A reader thread holds ≤ limit and stops at overflow. Trade-off: child tracebacks are discarded, so outcomes are the only diagnostics. |
| C4 | `reap` = wait/terminate/kill inside the 1 s allowance, then join the reader; stdout closed only once the reader ended; confirmed only when both exit and reader end are confirmed | Never close a handle a live reader blocks on; an unconfirmed reader quarantines like an unconfirmed exit. |
| C5 | `subprocess_launcher(module, args)` parameters exist for test child programs only | The dotted name and string args are validated. `Coordinator()`/`Admission` always use the default; no request path reaches them. Test programs live under `tests/selected_price_unit/`. |
| C6 | Multiprocessing framing (`fetch_child`, `send_framed`) removed; `price_chart_fetch.main()`/`read_spec()` added | Replaced mechanism, per ruling. The reviewer's `d17_spawn_main_probe.py` and this worker's `failing_first_spawn_probe.py` can no longer run against the candidate. Their saved JSON results remain. |
| C7 | F3: any query error renders the retry state before retained data; the amber "Showing the chart answered…" notice and its `.rh-sp-refresh` rule are removed; caption reads "not loaded" | Ruling. Unsupported/disabled refusals still pick the original chart. 200 stale/fallback answers are drawn. `usePriceChart`, the query key and polling are unchanged. |
| C8 | F4: `coordinator_started_at` (null = not started); `configured_web_workers` only from ASCII-digit positive `WEB_CONCURRENCY`, plus `configured_web_workers_source: 'WEB_CONCURRENCY'`; Admin "Configured web workers: Unknown — WEB_CONCURRENCY is not set to a positive number; each worker keeps its own limits"; coordinator start shown with day | Ruling. There is no runtime ops parser (`fetchOps` is typed `getJson`); the type, Admin and tests changed together. `tests/test_radar_operations_api.py` asserts only the top-level key set, which is unchanged. |

## 8. Not executed

- No POSIX/Linux child or gunicorn worker. The production interpreter path, the empty POSIX child environment and `CREATE_NO_WINDOW`-free startup are unverified on the release host.
- No live Yahoo request (period1/period2 form, closed-session/holiday answers, throttling). No provider usage permission.
- No MariaDB runtime (statement timeout, cancellation, plans, pool). DB-backed suites (`test_radar_operations_api.py`, hub page/API/detail) were not run.
- No real multi-worker topology; `WEB_CONCURRENCY` presence in production is unknown.
- No 57-case browser rerun or zoom suite (unchanged renderer paths); the whole Radar Vitest suite covered them at component level.

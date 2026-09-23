# MD-SELECTED-PRICE-CORRECTION-1 — Implementer return

2026-09-15. Radar Implementer (Claude Opus 5), one worker, no subagents. Return to the Mastermind. Binding ruling: `radar-design/MD-SELECTED-PRICE-REVIEW-1-RULING.md`. Detailed evidence: `radar-design/artifacts/md-selected-price-correction-1/evidence.md`.

## Workspace and Git

- Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, base = HEAD `daadf3868caedcb5db858378e919cba68b735f8a` (verified at start and end), uncommitted, nothing pushed/merged/deployed.
- Starting fingerprint recomputed `218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159`, 0 mismatches, no unexpected application change.
- Final fingerprint `ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce` (16 modified / 29 added / 5 generated), in the new `fingerprint-final.json`. Earlier manifests untouched.
- `git diff --check` clean. Both flags still default OFF (config untouched).

## Disposition

### F1 + F2 — fixed: explicit module subprocess with minimal environment

**What changed**

`price_chart_acquisition.py` no longer uses multiprocessing. `subprocess_launcher()` starts `[sys.executable, -E, -s, -B, -m, features.radar.price_chart_fetch]`:
- argument array, no shell;
- `cwd=personal_apps`;
- `env=child_environment()`, a new dict from the explicit allowlist `CHILD_ENV_ALLOWLIST` (`nt: SYSTEMROOT`, needed for Winsock; `posix`: nothing); `os.environ` is never copied or modified;
- `stdin`/`stdout` pipes, `stderr=DEVNULL`, `bufsize=0`, `close_fds`.

Request and result:
- The validated spec goes in on stdin (≤ 2048 B, below any default pipe buffer) and stdin is closed.
- `Child` drains stdout on a reader thread, keeping ≤ 512 KiB and stopping at overflow.
- `collect` returns `done` only on EOF plus exit 0 inside the 6 s startup-inclusive deadline.

Cleanup:
- `reap` waits, then terminates, then kills within 1 s, joins the reader, and closes the handles.
- It is confirmed only when both exit and reader end are confirmed; otherwise the process is quarantined.
- A failed start after `Popen` kills the child and closes its pipes.

Unchanged: supervisor, admission, cache, backoff, quotas, one child, no queue, no request-thread process start.

`price_chart_fetch.py` gains `main()`/`read_spec()` (bounded stdin, one stdout result) and loses the pipe-framing target. The Yahoo transport and its callers' defaults are untouched.

**Proof (executed)**

1. **Failing first.** The original spawn launcher, run from a file-path parent, re-ran the script as `__mp_main__` with flask loaded and the dummy sentinel visible (`failing_first_spawn.json`). The new tests failed 53× on the original code.
2. **Actual launcher, file-path parent.** The parent had a top-level marker, dummy secret, `PYTHONPATH` sitecustomize hook, `PYTHONSTARTUP`, credentialed proxies and dummy app/DB secrets. Results:
   - the script's top level ran once, only in the parent;
   - the hook loaded only in the parent;
   - the child was the explicit module with no Flask/models/DB/dotenv modules, env keys `['SYSTEMROOT']`, no sentinel and `-E/-s/-B` flags;
   - the parent environment was unchanged;
   - the real Coordinator went `pending` in 0.015 s and `ready` in 0.578 s via one direct loopback request with no Cookie/Proxy-Authorization.
3. **Real children through the same launcher.** Timings (supervisor s): normal 0.593, bad spec to production module 0.609, hanging 6.219 (other chart `busy`, one child), 4 MiB oversized 0.812, 8 MiB stderr flood 0.656 success, early exit 0.563, garbage 0.563, exit-5 0.657 (all invalid, nothing cached). Each case asserts reaped, OS says not alive, reader ended and pipes closed.
4. **Unit tests.**
   - hostile-environment allowlist on both platforms;
   - exact Popen arguments with no shell, and no `putenv`/`unsetenv`;
   - oversized spec and bad module name start nothing;
   - BrokenPipe on the request write is absorbed;
   - a reader thread that cannot start kills the child and closes its handles;
   - unconfirmed subprocess cleanup quarantines.

   Fake-clock quota/cache/backoff/quarantine tests are preserved; only their fake child adopts the new `collect`/`reap` contract.

Test hooks (`probe_child.py`, `child_targets.py`, and the launcher's `module`/`args` parameters) are test-only and not reachable from any request.

### F3 — fixed: honest refresh failure

**What changed**

In `ResearchContent.tsx`, `SelectedChartBody` renders the chart-local retry state whenever the query has an error, even when TanStack still holds earlier data:
- the message is "The latest 1D chart for X could not be loaded, so the earlier chart is hidden." plus the reason, with a Retry button;
- the section caption becomes "Current or last session · not loaded" (`selectedCaption` gained a `missing` state);
- the amber "Showing the chart answered…" notice and its CSS rule are removed.

Kept as before:
- Unsupported/disabled refusals still render the original chart.
- Valid HTTP-200 stale/fallback answers render normally.
- The query key, polling and caching are unchanged.
- No client calendar or age check was added.

Both Research and the Human Chatter panel use this `ChartSection`.

**Proof**

- Failing-first: 4 refresh cases failed on the original code.
- Vitest covers:
  - initial failure;
  - failed refresh with retained data, for a live session (rollover) and for a closed session with a different fingerprint (remap), with the data still in cache but no svg, no now/current-session/so-far wording and no old notice;
  - recovery via Retry;
  - a valid 200 stale answer and a stored-fallback answer drawn;
  - unsupported on refresh → original chart;
  - disabled → original chart.
- Built-hub browser, both surfaces at 1440 and 390:
  - initial failure;
  - answered live chart ("now 15:54"), then the poll fails and the retry state appears after 2.9 s with no svg or now wording;
  - Retry recovers the chart.

  Screenshots viewed.

### F4 — fixed: accurate health labels

**What changed**

- `coordinator_started_at` replaces `process_started_at` in the API snapshot, type, Admin and tests; null means not started.
- `configured_web_workers` is a positive ASCII-digit `WEB_CONCURRENCY` only, else null. The new `configured_web_workers_source: 'WEB_CONCURRENCY'` names the source.
- Admin shows "Acquisition coordinator started" (day + time Berlin, or "not started in this process") and "Configured web workers" ("2 (from WEB_CONCURRENCY)", or "Unknown — WEB_CONCURRENCY is not set to a positive number; each worker keeps its own limits").
- PID, scope and the reset note are kept.
- No hard-coded count and no CLI inference.
- There is no runtime ops parser: `fetchOps` is a typed `getJson`.

**Proof**

- Pytest: missing, blank, 0, 00, −2, +2, "two", 2.5, "²", "٣" and "2 workers" all give null; 1, " 3 " and 12 give the number.
- `coordinator_started_at` is null before any coordinator and equals the coordinator's wall creation time after; there is no `process_started_at`.
- The route ops test (admin client) sees the renamed field and source, and never launches.
- Vitest covers positive and Unknown Admin labels.
- Browser: Admin Unknown/not-started and configured/started at 1440 and 390, screenshots viewed.

### D5 / D14

Preserved unchanged (reader/contract/Retry-After code untouched; the D14 fake-clock test passes).

## Fresh checks (executed by this worker; logs under the evidence directory)

- `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` → **167 passed** (was 139).
- `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` → 269 passed, 1 skipped, the **same 3** baseline Yahoo date failures.
- `npx vitest run -c vite.radar.config.ts <11 affected files>` → **188 passed**.
- `npx vitest run -c vite.radar.config.ts` → 855 passed, **28 failed, all `pending.test.tsx`** (baseline).
- `npx tsc --noEmit` → exit 0.
- `npx vite build -c vite.radar.config.ts` → exit 0, `hub-CZqS9Prw.js` / `hub-Bmvv_e8B.css`.
- `verify_correction.py` → 12 cases / 96 checks / 0 failures on 127.0.0.1:5047 (verified free before, free after). Fixture evidence only.

Test-harness-only adjustments during the run:
- `waitFor` after `act()` for TanStack notifications. One failing-first case (unsupported-on-refresh) may have failed only for that timing reason; this is not proven.
- `getAllByText` for a title shown twice.

## Carried (not re-executed)

- Implementation evidence: carry manifest 23/23, original 57-case/744-check browser run, saved-array normalization, and the implementation's spawn-era `child-lifecycle.json`, which is now historical.
- Reviewer's 139/180/269 runs, scratch rebuild and D17 probe.
- Unchanged renderer, geometry, reader, contract and route behaviour, which is covered by the passing suites above but not re-browsed at 768/320 or 200% zoom.

## Limitations and release carries

- **POSIX.** No Linux/POSIX or gunicorn child was executed. The empty POSIX environment, the production venv `sys.executable`, and `personal_apps` as the child's working directory on the release host are unverified.
- **Live Yahoo.** No live request: epoch request form, closed-session/holiday answers and throttling are unverified. Provider usage conditions are not established.
- **MariaDB.** No runtime: statement timeout, cancellation, plans and pool are unverified, and the DB-backed suites were not run.
- **Topology.** Real process topology and whether `WEB_CONCURRENCY` is set in production are unknown. Admin will say Unknown otherwise.
- **Diagnostics.** stderr is discarded by design, so child failures are visible only as outcome counters.

## Dirty ownership

**This correction owns:**

- Application files (already IMPLEMENT-1 worker dirt, now modified again):
  - `personal_apps/features/radar/price_chart_acquisition.py`, `price_chart_fetch.py`;
  - `personal_apps/static/radar/src/hub/priceChart.ts`, `Admin.tsx`, `ResearchContent.tsx`, `SelectedPriceChart.tsx`, `selected-price.css`.
- Tests modified: `static/radar/src/hub/Admin.test.tsx`, `SelectedPriceSection.test.tsx`; `tests/selected_price_unit/child_targets.py`, `test_acquisition.py`, `test_child_lifecycle.py`, `test_route_ops.py`, `test_yahoo_bounded.py`.
- Tests added: `tests/selected_price_unit/probe_child.py`, `test_launcher_isolation.py`.
- Regenerated, Git-ignored `personal_apps/static/radar/dist` (manifest plus new hub js/css; old hub assets replaced by the build).
- `radar-design/artifacts/md-selected-price-correction-1/`: evidence.md, fingerprint.py, fingerprint-final.json, failing_first_spawn_probe.py and .json, child-lifecycle.json, launcher-isolation.json, browser/ (script, results.json, 20 PNGs), logs/.
- This return, and the new top notices in candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`.

**Everything else is unchanged by this worker:**

- other IMPLEMENT-1 worker files;
- reviewer artifacts;
- planner/Mastermind documents and carry, including SPEC §6's multiprocessing wording, which the ruling amends — the SPEC file was not edited.

## Protection and processes

- No commit, push, merge, deploy, flag activation, DB provisioning/reuse, live provider or production access.
- Untouched: source workspace, main/other worktrees, B1C/5021, promotion/5033, databases 3306/3399, HA1/3461 and `C:/Users/michi/.radar-ha1-local-qa`.
- Read-only listener check at the end: none of 5021/5033/5042/5047/3306/3399/3461 was listening.
- Every test child was reaped (asserted). The browser server thread and Chromium closed, and port 5047 was free afterwards. No owned process is left running.

## Requested decision

Assess the correction and prepare only a focused independent review of the changed behaviour: child isolation/lifecycle, refresh-error rendering and the ops labels. No repeat full review. HA1 stays closed.

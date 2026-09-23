# MD-SELECTED-PRICE-REVIEW-2 — Reviewer / QA return

2026-09-15. Radar Reviewer / QA (Claude Opus 5), no subagents. Scope: CORRECTION-1 only; HA1 closed. Evidence: `radar-design/artifacts/md-selected-price-review-2/evidence.md`.

## Independence qualification

This review ran in the **same agent session that implemented CORRECTION-1**, so it is not independent in the WORKFLOW sense. Every result below is either executed here or read from source. Confirmation bias cannot be excluded. The owner may want a separate session to re-check R2-1 and the F3/F4 reading before final acceptance.

## Verdict

**Accept the correction for the default-off local candidate, with one low finding open (R2-1).**

| Item | Disposition |
| --- | --- |
| F1 | CLOSED |
| F2 | CLOSED |
| F3 | CLOSED |
| F4 | CLOSED, one nonblocking wording note |
| New regressions | One low cleanup gap in the new launcher's rare post-Popen failure path. No blocker for the flags-off candidate; fix before provider activation. |

## Git and fingerprint

- Branch `codex/radar-selected-price-charts`; base/HEAD `daadf3868caedcb5db858378e919cba68b735f8a`; uncommitted.
- Fingerprint `ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce` verified twice: the correction's script run read-only, and independent reviewer re-hash code. 50 files, 0 mismatches.
- The implementation → correction map differs in exactly 21 paths, all expected (15 changed, 4 added, 2 removed; listed in evidence).
- A scratch Radar build is byte-identical to the candidate `dist`.

## F1 / F2 — CLOSED

**Production launch** (`price_chart_acquisition.py:201-241`):
- argument array `[sys.executable, -E, -s, -B, -m, features.radar.price_chart_fetch]`;
- no shell;
- a new allowlisted environment (Windows SYSTEMROOT only, POSIX empty);
- `cwd=personal_apps`, stderr to DEVNULL;
- spec refused above 2048 B before Popen.

**Test hooks unreachable.** The `module`/`args` parameters are validated, and the only production construction is `Coordinator()` inside `coordinator()` (`:599`), reached from `Admission` with no launcher argument. No request input reaches them.

**Proof.**
- The file-path-parent test passed fresh (in the 167): no parent re-execution, no Flask/models/DB/dotenv modules, no sentinel, hook or proxy in the child, parent environment unchanged.
- Saved `launcher-isolation.json` agrees.
- This is **synthetic loopback proof**: the test child redirects `yahoo.API_BASE` to a local server. It is not a live Yahoo run.
- No stdlib-shadowing module sits in the child's working directory.

## Lifecycle and limits — correct in the normal paths; R2-1 open

**Correct:**
- 6 s deadline measured before launch, so startup is included;
- stdin ≤ 2048 B; stdout reader stops above 512 KiB;
- `done` requires EOF plus exit 0;
- `Child.reap` confirms exit and reader end before closing stdout, and `_supervise` quarantines otherwise;
- one child, no queue, unchanged.

**Real children**, fresh in the 167 and saved worker timings: normal, hanging (6.219 s), oversized, 8 MiB stderr flood, early exit, garbage, exit 5 — all reaped, OS-level not alive, reader ended, pipes closed.

**Failure paths** (unit tests): reader-start failure kills and closes the pipes; BrokenPipe on the request write is absorbed.

### R2-1 — Low: unconfirmed cleanup after a post-Popen launcher exception does not quarantine

- **Where:**
  - `personal_apps/features/radar/price_chart_acquisition.py:236-239`: `except BaseException: _kill_now(process); raise`.
  - `:260-268`: `_kill_now` swallows `OSError`/`TimeoutExpired` and reports nothing.
  - `:391-396`: `_supervise` sees `child is None`, so `confirmed` stays `True`.
- **Contract:** ruling "quarantine on unconfirmed cleanup"; "clean up children/readers on every exit".
- **Reproduction:** `radar-design/artifacts/md-selected-price-review-2/post_popen_cleanup_repro.py` → `post_popen_cleanup_repro.json`. The real Coordinator and launcher run with a fake Popen that ignores kill and whose `wait` always times out.
  - Reader thread fails to start: `invalid: 1`, **quarantined False**, process still running, and a second chart is immediately `pending` with a **second process started**.
  - Control (unconfirmed `Child.reap`): quarantined, second chart `unavailable`, 1 process.
- **Impact:** low probability. It needs a thread-start failure (resource exhaustion) plus a child that does not die within 1 s of kill. When it happens, an unreaped child and its handles can accumulate while acquisition continues, which is the resource leak quarantine exists to stop. No current exposure: both flags are default OFF.
- **Narrow remedy:**
  1. Make `_kill_now` return whether the exit was confirmed.
  2. On an unconfirmed exit, raise a dedicated exception (e.g. `UnconfirmedCleanup`) from the launcher.
  3. In `_supervise`, treat that exception as `confirmed = False`, which increments `cleanup_failed` and quarantines.
  4. Add one fake-process unit test mirroring the reproduction.

  No architecture change.

## F3 — CLOSED

- `ResearchContent.tsx`: any query error renders the retry alert before retained `data` is touched, and the caption reads "not loaded".
- Unsupported/disabled refusals still pick the original chart; 200 stale/fallback answers render.
- Both Research and Human Chatter use this `ChartSection`.
- Fresh focused Vitest (117 in 7 files) covers:
  - live-session and remapped retained data hidden;
  - recovery on success;
  - 200 stale and stored-fallback drawn;
  - unsupported-on-refresh and disabled → original chart.
- Worker browser run recounted: 12 cases, 96 checks, 0 failures. Reviewer viewed the failed (390 Research), recovered (1440 Chatter) and Admin screenshots.

## F4 — CLOSED

- `coordinator_started_at` = `Coordinator.__init__` wall time; null when no coordinator exists.
- Workers: a positive ASCII-digit `WEB_CONCURRENCY` or null, with `configured_web_workers_source` named.
- Admin shows Unknown with the source, "not started in this process", PID and the process-scope note.
- No leftover `process_started_at` consumer. No inferred topology.

**Nonblocking note N1.** The comments in `price_chart_acquisition.py` `_snapshot_shape` and `static/radar/src/hub/priceChart.ts` (`SelectedPriceOps.coordinator_started_at`) say the coordinator is created "on its first admitted chart". `Admission.get_or_start` (`:608-611`) actually creates it on the first chart request that reaches acquisition with the provider flag on, even if that request is then refused (busy, backoff, unsupported symbol, waiting window). The field value is still the true creation time. Only the comment wording is imprecise; fix it opportunistically with R2-1.

## Fresh checks (reviewer-executed)

- Fingerprint recompute (read-only) plus independent re-hash: 50 files, 0 mismatches, `ad06a94a…`.
- `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` → 167 passed (15.63 s).
- `npx vitest run -c vite.radar.config.ts` on SelectedPriceSection, Admin, SelectedPriceChart, Research, ChatterWorkspace, queries and priceChart → 117 passed.
- `npx tsc --noEmit` → exit 0.
- Scratch `npx vite build -c vite.radar.config.ts --outDir <temp>` → exit 0, byte-identical to candidate dist; temp deleted.
- `py -3.12 radar-design/artifacts/md-selected-price-review-2/post_popen_cleanup_repro.py` → R2-1 reproduced, control quarantines.

## Carried (worker-executed, inspected not rerun)

- Whole Radar Vitest 855 passed / 28 baseline `pending.test.tsx` failures.
- Tone/Yahoo/HA1 regression 269 passed / 3 baseline failures.
- Browser run: 12 cases / 96 checks (results recounted, screenshots viewed).
- `child-lifecycle.json` timings; `launcher-isolation.json`.
- Historical `failing_first_spawn.json`, not rerun because the spawn launcher no longer exists.

## Unexecuted limitations / release carries

- **POSIX.** No POSIX/Linux or gunicorn child: the empty POSIX environment, the production venv `sys.executable` and `personal_apps` as working directory on the release host are unverified.
- **Provider.** No live Yahoo request (epoch form, closed-session/holiday answers, throttling); provider usage conditions not established.
- **DB.** No MariaDB runtime (statement timeout, cancellation, plans, pool); DB-backed suites not run.
- **Topology.** Actual process topology and production `WEB_CONCURRENCY` unknown.
- **Diagnostics.** DEVNULL stderr is an accepted tradeoff.
- **Carried constraints.** D5/D14 closed; optional polish deferred.

## Changed files / ownership

Reviewer wrote only:
- this return;
- `radar-design/artifacts/md-selected-price-review-2/`: evidence.md, post_popen_cleanup_repro.py and .json, logs/;
- short review-returned notices at the top of candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`.

No application, test, build or other evidence changes; the scratch build went to a temp directory that was removed. The fingerprint is unchanged.

## Protected state and processes

- No commit, push, merge, fix, flag activation, DB, provider, production or worker dispatch.
- Source workspace, main/other worktrees, B1C/5021, promotion/5033, databases 3306/3399, HA1/3461, `C:/Users/michi/.radar-ha1-local-qa` and Remote Control sessions untouched.
- No server or port opened; the only child processes were those the test suite started and reaped.

## Requested decision

Accept F1-F4 as closed for the default-off local candidate. Rule on R2-1: either a tiny bounded correction (the four-step remedy plus one test, and optionally the N1 comment wording) with a changed-lines-only check, or record it as a pre-activation carry. Given the independence qualification, optionally have a different session confirm R2-1 only. No repeated full review.

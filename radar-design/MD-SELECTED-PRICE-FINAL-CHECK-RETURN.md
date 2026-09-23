# MD-SELECTED-PRICE-FINAL-CHECK — Reviewer return

2026-09-15. Independent Reviewer (Claude Opus 5), read-only application scope, no subagents. Return to the Mastermind. Evidence: `radar-design/artifacts/md-selected-price-final-check/evidence.md`.

## Independence

This is a fresh session, started after `/clear`. It did not implement CORRECTION-1 or CORRECTION-2 and did not run REVIEW-2. Everything it knows about those came from the repository records listed below, and it checked those records against Git and the source.

Read: `HANDOFF.md`, `radar-design/MD-SELECTED-PRICE-LEDGER.md`, `radar-design/WORKFLOW.md` (roles and return sections), the REVIEW-1, REVIEW-2 and CORRECTION-2 rulings, the CORRECTION-2 return, and the correction-1/correction-2 artifact listings. It also read the correction-2 check and fingerprint scripts.

## Verdict

**CLEAN. R2-1 is closed. F1-F4 are confirmed in source. N1 comments are correct. No new concrete defects.**

## Workspace

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`.
- Base = HEAD `daadf3868caedcb5db858378e919cba68b735f8a`. Uncommitted, 70 porcelain entries, all preserved.
- Fingerprint recomputed read-only: `0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0` (16 modified / 29 added / 5 generated).
- Against the correction-2 manifest: 0 differing paths.
- Against the correction-1 manifest: exactly `personal_apps/features/radar/price_chart_acquisition.py`, `personal_apps/static/radar/src/hub/priceChart.ts` and `personal_apps/tests/selected_price_unit/test_launcher_isolation.py` differ. None of the 5 generated dist files differ.
- `git diff --check` exit 0.

## R2-1 — closed

Source is `personal_apps/features/radar/price_chart_acquisition.py`.

- **`_kill_now` reports confirmed exit** (272-288). It calls `kill()` and ignores `OSError`. Exit counts as confirmed only when `process.wait(timeout=CLEANUP_S)` returns. `TimeoutExpired` or `OSError` from `wait` returns False. Stdin and stdout are closed on every path. A failed kill, or a kill call on its own, never counts as exit: a kill that raised still depends on `wait`.
- **Launcher propagates the cause** (223-242). Everything after `Popen` is inside `try/except BaseException as exc`. If `_kill_now` is False, it raises `UnconfirmedCleanup(exc) from exc`, so `__cause__` is the original error and the message names its type. If `_kill_now` is True, it re-raises the original error. `UnconfirmedCleanup` subclasses `RuntimeError` (246-252).
- **Supervisor quarantines before further admission** (406-439). `except UnconfirmedCleanup` sets `confirmed = False` and is listed before the generic `except Exception`. In `finally`, under `self._lock`, one block clears `_inflight` and sets `_quarantined = True` and `cleanup_failed += 1`. No request can see a free slot without also seeing quarantine. `_refusal` checks `_quarantined` first (365-366).
- **No wrong quarantine.**
  - If `wait` proves exit, `_kill_now` is True, the original error is re-raised, the generic handler runs and `confirmed` stays True.
  - Pre-Popen failures raise outside the `try`: spec bound `ValueError`, missing `sys.executable`, and `Popen` itself. The generic handler runs, `child` is None and `confirmed` stays True.
  - Both paths settle as ordinary `invalid` with a 60 s key cooldown.
- **Handles and normal reap.** On success the launcher still closes stdin before returning `Child`. `Child.reap` (176-198) and the supervisor's reap-based quarantine path (424-428) are unchanged, and the reap control scenario still quarantines.
- **Regression tests read** (test_launcher_isolation.py 317-421). They use the real Coordinator and the real launcher with a fake `Popen`, and a reader thread that refuses to start:
  - unconfirmed case: quarantined, `cleanup_failed` 1, `invalid` 1, second chart `unavailable`, 1 Popen;
  - parametrized confirmed controls (killed-and-reaped, already-exited);
  - pre-Popen `FileNotFoundError` control, which checks after a sleep that exactly 2 Popen attempts were made;
  - `_kill_now` unit cases;
  - cause-chaining assertion.

Non-defect observations, not findings or gates:
- `_kill_now` waits the module `CLEANUP_S` (1 s), not the coordinator's injected `cleanup_s`. It is still bounded and matches the 1 s rule.
- A `BaseException` such as `SystemExit` combined with unconfirmed cleanup is converted to `UnconfirmedCleanup`, which quarantines. That is the conservative choice.

## F1-F4 — confirmed from source (brief)

- **F1/F2.**
  - Production child is `[sys.executable, '-E', '-s', '-B', '-m', 'features.radar.price_chart_fetch']`: an argument array with no shell, `cwd=APP_ROOT`, `stderr=DEVNULL` (219-222).
  - `env=child_environment()` builds a new dict from `CHILD_ENV_ALLOWLIST` (`nt`: SYSTEMROOT only; `posix`: none). `os.environ` is only read (100-115).
  - The child imports only `price_chart_contract` and `prices.yahoo`. Their import chains (`analysis_contract`, `market_calendars`, `prices/__init__`, empty `features/__init__.py` and `features/radar/__init__.py`) have no flask/models/extensions/app/sqlalchemy/dotenv/auth imports.
  - The `module`/`args` test hooks are unreachable from requests. The route (`routes/price_chart.py:76`) passes `Admission()`, which takes no parameters. `Admission` calls `coordinator()`, which calls `Coordinator()`, which calls `subprocess_launcher()` with no arguments. Only three query keys are accepted.
  - The fresh file-path-parent real-child test passed in this reviewer's run.
- **F3.** `SelectedChartBody` (`ResearchContent.tsx:188-219`) checks `if (error)` before `if (!data)` and before drawing. It renders the chart-local Retry (with an "earlier chart is hidden" message when cached data exists) and never draws the cached series. The caption also switches to `failed` (88, 132). `unsupported`/`disabled` refusals keep the legacy chart (85-87). A stale or fallback HTTP 200 is data rather than an error, so `SelectedPriceChart` draws it with stale/fallback provenance (`SelectedPriceChart.tsx:141-155`). The component is shared by Research and Chatter; `SelectedPriceChart` is only mounted from here.
- **F4.**
  - Backend `_snapshot_shape` emits `coordinator_started_at` (null when no coordinator exists), `configured_web_workers` and `configured_web_workers_source='WEB_CONCURRENCY'`.
  - `_configured_workers` returns a count only for a positive explicit integer; otherwise None. It does not infer `--workers`.
  - Admin (`Admin.tsx:162-172`) shows "not started in this process" or the stamp, and either `N (from WEB_CONCURRENCY)` or an explicit "Unknown — WEB_CONCURRENCY is not set to a positive number…".
  - The frontend and browser evidence from CORRECTION-1 is carried, not rerun.

## N1 — confirmed

`coordinator()` (621-629) creates the instance lazily. `Admission.get_or_start` calls it only when Yahoo is enabled, and before admission is decided. `ops_snapshot` never creates one. The comments at `_snapshot_shape` (589-592) and `priceChart.ts:127-129` say exactly that: first provider-enabled chart request that reaches acquisition, admitted or not, and not the OS process start.

## Fresh checks (this reviewer)

- `post_popen_cleanup_check.py` (copied into own evidence dir, read first) `final-check` → `all_met: true`, 5/5 scenarios. The original correction-2 JSON is unchanged (hash equal before and after).
- `pytest tests/selected_price_unit/test_launcher_isolation.py --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` → **13 passed** (2.43 s).
- `fingerprint.py --check-only` versus the correction-1 and correction-2 manifests: results above.
- `git diff --check` → exit 0.
- Not rerun: the full 59 and 167 sets, Vitest, tsc, build and browser. No concrete reason came up.

## Carried evidence (attributed, not re-executed)

- CORRECTION-1 Implementer: `selected_price_unit` 167 passed; focused Vitest 188; whole Radar 855 with 28 baseline `pending.test.tsx` failures; tsc 0; build `hub-CZqS9Prw.js`; fixture browser 12 cases / 96 checks (Admin Unknown/configured and refresh-failure screenshots); tone/Yahoo/HA1 269 passed with 3 baseline failures.
- REVIEW-2 (same session as CORRECTION-1): 167 / 117 Vitest, scratch build identical, saved R2-1 reproduction.
- CORRECTION-2 Implementer: failing-first check, 3 failed / 10 passed before the fix, focused 59 passed.
- REVIEW-1 (independent) stands for unchanged scope.

## Ownership

This check owns only:
- `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-FINAL-CHECK-RETURN.md`
- `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/md-selected-price-final-check/` (evidence.md, the two copied scripts, `post_popen_cleanup_check-final-check.json`, logs/)
- the short returned notices at the top of candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`

Nothing else was changed: application, test and generated files, older artifacts and manifests, rulings and prompts, and all other dirt.

## Protected state and processes

- No application edits, dependencies, provider/Yahoo, DB, production, commit, push, merge, deploy or flag change. Both flags remain default OFF.
- Untouched: source workspace, main/other worktrees, B1C/5021, promotion/5033, DB 3306/3399, HA1/3461, `C:/Users/michi/.radar-ha1-local-qa`, Remote Control sessions. HA1 stays closed.
- The only real processes came from the isolation test (a parent, its probe child, and an in-test loopback server). All completed, and none are left running.

## Limitations / release carries (retained)

- Fake cleanup proof is not a real unkillable-OS-process test.
- POSIX/Linux, gunicorn, production venv `sys.executable` and cwd are unverified.
- Live Yahoo epoch form, closed-session/holiday behaviour and provider usage conditions are unresolved release considerations.
- MariaDB runtime (timeouts, cancellation, plans, pool) and the actual topology/`WEB_CONCURRENCY` are unverified.

## Requested decision

Close local implementation/review, keeping the operational limitations above, with a separate owner release decision. No repeated full review.

# MD-SELECTED-PRICE-CORRECTION-2 — Implementer return

2026-09-15. Radar Implementer (Claude Opus 5), one worker, no subagents. Return to the Mastermind. Binding ruling: `radar-design/MD-SELECTED-PRICE-REVIEW-2-RULING.md`. Evidence: `radar-design/artifacts/md-selected-price-correction-2/evidence.md`.

This session also implemented CORRECTION-1 and ran REVIEW-2; nothing here is independent review.

## Workspace and Git

- Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, base = HEAD `daadf3868caedcb5db858378e919cba68b735f8a`, uncommitted, nothing pushed.
- Starting fingerprint `ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce` recomputed read-only, 0 differing paths.
- Final fingerprint `0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0` (16 modified / 29 added / 5 generated). Versus the correction-1 map it differs in exactly three paths: `price_chart_acquisition.py`, `priceChart.ts`, `test_launcher_isolation.py`.
- `git diff --check` clean. Both flags default OFF.

## R2-1 — fixed

**Change** (`personal_apps/features/radar/price_chart_acquisition.py`):
- `_kill_now` now returns `bool`. It kills (ignoring `OSError`), waits ≤ `CLEANUP_S`, and returns True only when `wait()` returns an exit; on timeout or `OSError` it returns False. It always closes the pipes. A kill call, or a kill that raised, is never taken as confirmation.
- The launcher's post-Popen `except` raises the new `UnconfirmedCleanup(exc) from exc` when that cleanup is unconfirmed, and otherwise re-raises the original error. The original failure stays attached via `__cause__` and the type name.
- `_supervise` catches `UnconfirmedCleanup` as `outcome='invalid'`, `confirmed=False`. Its existing locked `finally` then sets quarantine and `cleanup_failed += 1` in the same step that releases admission.

No retry, no new process management; deadlines, normal `Child.reap` quarantine, admission, cache and backoff are untouched. Nothing new reaches the browser.

**Failing-first** (real Coordinator and real launcher, fake Popen ignoring kill with `wait` timing out, reader thread failing to start):
- The adapted check (`post_popen_cleanup_check-pre-edit.json`): not quarantined, `cleanup_failed` 0, second chart `pending`, 2 Popen. The four controls already behaved correctly.
- New tests on unchanged code: 3 failed, 10 passed.

**After** (`post_popen_cleanup_check-post-edit.json`, all 5 scenarios met):

| Scenario | Result |
| --- | --- |
| Unconfirmed post-Popen cleanup | **quarantined True, `cleanup_failed` 1, second chart `unavailable` ("cleanup_failed…"), exactly 1 Popen** |
| Confirmed post-Popen cleanup (killed and reaped) | not quarantined, ordinary invalid start, second chart `pending` |
| Kill raised but `wait` proved exit | not quarantined, ordinary invalid start, second chart `pending` |
| Pre-Popen failure (Popen raised) | not quarantined, second chart `pending` |
| Existing `Child.reap` unconfirmed control | still quarantines |

Unit tests (6 cases) prove the same, plus two things: `_kill_now` is False despite a kill call, and the launcher raises `UnconfirmedCleanup` chained to the original `RuntimeError`.

## N1 — fixed

The comments in `_snapshot_shape` and `static/radar/src/hub/priceChart.ts` (`SelectedPriceOps.coordinator_started_at`) now say the coordinator is created lazily on the first provider-enabled chart request that reaches acquisition, whether or not it is admitted. Comments only.

## Fresh checks (implementer-executed)

- `py -3.12 radar-design/artifacts/md-selected-price-correction-2/post_popen_cleanup_check.py pre-edit` → R2-1 scenario unmet, controls met.
- `py -3.12 -m pytest tests/selected_price_unit/test_launcher_isolation.py --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` on unchanged code → 3 failed, 10 passed.
- `py -3.12 radar-design/artifacts/md-selected-price-correction-2/post_popen_cleanup_check.py post-edit` → all 5 met.
- `py -3.12 -m pytest tests/selected_price_unit/test_launcher_isolation.py tests/selected_price_unit/test_acquisition.py tests/selected_price_unit/test_child_lifecycle.py --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` → **59 passed** (12.88 s). Includes real normal/hang/oversized/stderr-flood/early-exit/garbage/exit-5 children, file-path parent isolation, and fake-clock quota/cache/backoff/quarantine.
- `git diff --check` → clean.
- Final fingerprint compare → 3 differing source/test paths; the 5 generated dist files are byte-identical to the correction-1 manifest.

## Carried evidence (not re-executed here)

CORRECTION-1 (same session):
- `selected_price_unit` 167 passed;
- focused Vitest 188 and whole Radar 855 passed with 28 baseline `pending.test.tsx` failures;
- tsc 0, build `hub-CZqS9Prw.js`;
- fixture browser 12 cases / 96 checks;
- tone/Yahoo/HA1 269 passed with 3 baseline failures.

REVIEW-2 (same session): 167 / 117 focused Vitest, scratch build identical, the saved R2-1 reproduction (immutable, not rerun). REVIEW-1 (independent) stands for unchanged scope.

No frontend, tsc, build or browser rerun: TypeScript changed in a comment only and generated assets are unchanged by hash.

## Paths and ownership

**This correction owns:**
- Application: `personal_apps/features/radar/price_chart_acquisition.py` (R2-1 + N1 comment); `personal_apps/static/radar/src/hub/priceChart.ts` (N1 comment).
- Tests: `personal_apps/tests/selected_price_unit/test_launcher_isolation.py` (5 appended tests).
- Evidence: `radar-design/artifacts/md-selected-price-correction-2/` — evidence.md, post_popen_cleanup_check.py and its pre-edit/post-edit JSON, fingerprint.py, fingerprint-final.json, logs/.
- This return, and the new top notices in candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`.

**Generated assets:** `static/radar/dist` unchanged: manifest, `hub-CZqS9Prw.js`, `hub-Bmvv_e8B.css`, `board-rWQq9mLW.js`, `embedded-DT-Q2QoO.js`. Hashes match the correction-1 manifest.

**Unchanged by this worker:** all other dirt (IMPLEMENT-1 / CORRECTION-1 / REVIEW-1 / REVIEW-2 files, planner/Mastermind documents, earlier manifests and reproductions).

## Limitations / release carries

- No POSIX/Linux or gunicorn child: the production venv `sys.executable` and working directory are unverified.
- No live Yahoo request (epoch form, closed-session/holiday answers, throttling); provider usage conditions not established.
- No MariaDB runtime (statement timeout, cancellation, plans, pool).
- Actual topology and production `WEB_CONCURRENCY` unknown.
- The fake-process check proves supervisor state handling, not how any real OS behaves when a process cannot be killed.

## Protection and processes

- No live provider, DB, production, dependency install, commit, push, merge, flag activation or deployment.
- Source workspace, main/other worktrees, B1C/5021, promotion/5033, databases 3306/3399, HA1/3461, `C:/Users/michi/.radar-ha1-local-qa` and Remote Control sessions untouched.
- The only real child processes came from `test_child_lifecycle.py` and were reaped (asserted). No server or port opened; no owned process left running.

## Requested decision

Assess this tiny correction. Prepare a different-session check of the changed lines only (R2-1 delta and its regression) plus a brief F1-F4 source confirmation, to resolve REVIEW-2's same-session qualification. No full review or test repeat.

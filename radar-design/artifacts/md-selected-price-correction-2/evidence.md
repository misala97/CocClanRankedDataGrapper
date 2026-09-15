# MD-SELECTED-PRICE-CORRECTION-2 — evidence

2026-09-15. Radar Implementer (Claude Opus 5), no subagents. Binding: `radar-design/MD-SELECTED-PRICE-REVIEW-2-RULING.md`.

This is the **same session** that implemented CORRECTION-1 and ran REVIEW-2. Every result here is implementer-executed; none of it is independent review.

## Start (EXECUTED)

- Branch `codex/radar-selected-price-charts`, HEAD `daadf3868caedcb5db858378e919cba68b735f8a`, 66 status lines (intentional dirt).
- `py -3.12 radar-design/artifacts/md-selected-price-correction-1/fingerprint.py --check-only --compare …/fingerprint-final.json` → `ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce`, 16/29/5, 0 differing paths. Nothing written.

## Failing-first (EXECUTED, before any application edit)

**Adapted check.** `post_popen_cleanup_check.py pre-edit` → `post_popen_cleanup_check-pre-edit.json`. It is copied/adapted from the immutable `../md-selected-price-review-2/post_popen_cleanup_repro.py`, which is unchanged, and uses the real Coordinator and real `subprocess_launcher()` with fake Popen.

| Scenario | Required | Pre-edit |
| --- | --- | --- |
| post_popen_unconfirmed (reader cannot start; kill ignored, wait times out) | quarantined, cleanup_failed 1, second unavailable, 1 Popen | **NOT MET**: not quarantined, cleanup_failed 0, second pending, 2 Popen |
| post_popen_confirmed (kill ends it, wait returns) | not quarantined, second pending, 2 Popen | met |
| post_popen_kill_raises_but_exited (kill raises, wait returns exit code) | not quarantined | met |
| pre_popen_failure (Popen raises FileNotFoundError) | not quarantined, second pending | met |
| control_reap_unconfirmed (Child.reap path) | quarantined, second unavailable, 1 Popen | met |

**New tests on unchanged code.** `pytest tests/selected_price_unit/test_launcher_isolation.py` → 3 failed, 10 passed (`logs/failing-first-pytest.log`):
- failed: quarantine test; `_kill_now` process-evidence test; `UnconfirmedCleanup` test;
- passed: both confirmed-cleanup controls and the pre-Popen control.

## Change

`personal_apps/features/radar/price_chart_acquisition.py`:
- **`_kill_now(process) -> bool`:**
  - kill, where an `OSError` is ignored;
  - wait ≤ `CLEANUP_S`, where `True` only if `wait()` returns an exit;
  - `TimeoutExpired`/`OSError` → `False`;
  - pipes are always closed.

  A kill call, or a kill that raised, is not treated as confirmation.
- **Launcher `except BaseException as exc`:** if `_kill_now` is unconfirmed, raise `UnconfirmedCleanup(exc) from exc`; otherwise re-raise the original error. Attribution is kept through `__cause__` and the exception type name in the message. No retry.
- **New `UnconfirmedCleanup(RuntimeError)`.**
- **`_supervise`:** `except UnconfirmedCleanup` sets `outcome='invalid'` and `confirmed=False`. The existing locked `finally` sets `_quarantined` and `cleanup_failed += 1` in the same step that clears `_inflight`, before any further admission. Other exceptions stay ordinary invalid starts.
- **N1:** the `_snapshot_shape` comment now says creation happens on the first provider-enabled chart request reaching acquisition, admitted or not.

`personal_apps/static/radar/src/hub/priceChart.ts`: the N1 comment on `SelectedPriceOps.coordinator_started_at` changed. Comment only; no functional frontend change.

`personal_apps/tests/selected_price_unit/test_launcher_isolation.py`, 5 tests (6 cases) appended:
- post-Popen unconfirmed quarantines before another start;
- confirmed cleanup (killed-and-reaped, already-exited) is an ordinary invalid start;
- pre-Popen failure never quarantines;
- `_kill_now` reports exit only from process evidence;
- the launcher raises `UnconfirmedCleanup` chained to the original error.

## Post-edit (EXECUTED)

| Command | Result | Artifact |
| --- | --- | --- |
| `py -3.12 radar-design/artifacts/md-selected-price-correction-2/post_popen_cleanup_check.py post-edit` | all 5 scenarios met: unconfirmed → quarantined, cleanup_failed 1, second `unavailable` "cleanup_failed…", 1 Popen; controls unchanged | `post_popen_cleanup_check-post-edit.json`, `logs/check-post-edit.log` |
| cwd personal_apps: `py -3.12 -m pytest tests/selected_price_unit/test_launcher_isolation.py tests/selected_price_unit/test_acquisition.py tests/selected_price_unit/test_child_lifecycle.py --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **59 passed** in 12.88 s (includes real subprocess children, file-path parent isolation, fake-clock quota/cache/backoff/quarantine) | `logs/pytest-focused.log` |
| `git diff --check` | clean | — |
| `py -3.12 radar-design/artifacts/md-selected-price-correction-2/fingerprint.py --compare ../md-selected-price-correction-1/fingerprint-final.json` | digest **`0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0`**, 16/29/5; differs only in `price_chart_acquisition.py`, `priceChart.ts`, `test_launcher_isolation.py`. All 5 `static/radar/dist` files unchanged. | `fingerprint-final.json`, `logs/fingerprint-final.log` |

`fingerprint.py` here is a copy of the correction-1 script. It writes only into this directory; earlier manifests are untouched.

## Not executed (by ruling or scope)

- Rest of `selected_price_unit` (normalize, window, reader, chatter tone, route/ops, bounded Yahoo) — code untouched by this change.
- Frontend, tsc and build — TypeScript comment only; generated assets unchanged by hash.
- Browser, full Radar/Yahoo/tone/HA1 suites.
- Release carries unchanged: POSIX/gunicorn/venv/cwd, live Yahoo form/closed sessions, usage conditions, MariaDB runtime, actual topology/WEB_CONCURRENCY.

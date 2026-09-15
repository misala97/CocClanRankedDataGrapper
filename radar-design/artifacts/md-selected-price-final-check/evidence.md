# MD-SELECTED-PRICE-FINAL-CHECK — evidence

2026-09-15. Reviewer: Claude Opus 5, fresh session (started after /clear), no subagents. This session did not implement CORRECTION-1/2 or run REVIEW-2.

Everything here was executed by this reviewer unless marked carried.

## Files in this directory

- `post_popen_cleanup_check.py`: byte copy of `../md-selected-price-correction-2/post_popen_cleanup_check.py`, read before running. Its output goes to its own directory, so the correction-2 JSON is untouched (post-edit JSON SHA-256 compared before and after: equal).
- `post_popen_cleanup_check-final-check.json`: this reviewer's run, all 5 scenarios met.
- `fingerprint.py`: byte copy of the correction-2 fingerprint script. Run with `--check-only`, so it wrote nothing.
- `logs/check-final.log`, `logs/fingerprint-vs-correction-1.log`, `logs/fingerprint-vs-correction-2.log`, `logs/pytest-launcher-isolation.log`.

## Commands (from the candidate root, PowerShell)

```
git -c safe.directory=* rev-parse --abbrev-ref HEAD      -> codex/radar-selected-price-charts
git -c safe.directory=* rev-parse HEAD                   -> daadf3868caedcb5db858378e919cba68b735f8a
git -c safe.directory=* status --porcelain               -> 70 entries (dirty, preserved)
py -3.12 radar-design/artifacts/md-selected-price-final-check/post_popen_cleanup_check.py final-check
    -> all_met true; 5/5 scenarios met
py -3.12 radar-design/artifacts/md-selected-price-final-check/fingerprint.py --check-only --compare radar-design/artifacts/md-selected-price-correction-1/fingerprint-final.json
    -> digest 0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0; 16 modified / 29 added / 5 generated
    -> differs: price_chart_acquisition.py, priceChart.ts, test_launcher_isolation.py (only)
py -3.12 radar-design/artifacts/md-selected-price-final-check/fingerprint.py --check-only --compare radar-design/artifacts/md-selected-price-correction-2/fingerprint-final.json
    -> same digest; differs: [] (all 50 paths, including the 5 generated dist files, match)
cd personal_apps; py -3.12 -m pytest tests/selected_price_unit/test_launcher_isolation.py --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
    -> 13 passed in 2.43s
git -c safe.directory=* diff --check                     -> exit 0 (only LF/CRLF working-copy warnings on docs)
```

The 5 generated assets are unchanged against both manifests because neither comparison lists a dist path. Hashes show which paths changed; they are not a full source diff.

## Scenario results (`post_popen_cleanup_check-final-check.json`)

| Scenario | Required | Met |
| --- | --- | --- |
| post_popen_unconfirmed | quarantined, cleanup_failed 1, second chart unavailable, 1 Popen | yes |
| post_popen_confirmed | not quarantined, second pending, 2 Popen | yes |
| post_popen_kill_raises_but_exited | not quarantined, second pending, 2 Popen | yes |
| pre_popen_failure | not quarantined, second pending, 2 Popen | yes |
| control_reap_unconfirmed | quarantined, second unavailable, 1 Popen | yes |

## Not executed

The full 59-test set, `selected_price_unit` 167, Vitest, tsc, build, browser, tone/Yahoo/HA1 regressions, provider, DB, POSIX. No reason to rerun them came up: the diff is 3 paths and the TypeScript change is a comment only.

## Processes

The only real processes were in `test_a_file_path_parent_is_not_re_executed...`: a parent run by `subprocess.run` with a 60 s timeout, its probe child, and an in-test loopback HTTP server that the fixture shuts down. The test finished and passed. No server or port was left open.

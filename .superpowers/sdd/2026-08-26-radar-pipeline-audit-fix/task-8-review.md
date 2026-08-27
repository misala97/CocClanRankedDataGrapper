# Task 8 independent review: Reddit scoring hardening

Review range: `47d1c2c665b8024b5ca96594c362fe7832e94e5c..aee4e2fc97f0a02619212356569bbecc5045640d`

Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`

## Verdict

**APPROVED.** Critical: **0**. Important: **0**. Minor: **0**.

The implementation admits exactly `ok` and `truncated` rows to the scoring
write path, while both baseline inputs remain `ok`-only. The behavioral
regressions exercise persisted current-generation rows, assert all four score
fields, and kill both required mutants. The change is confined to the two
Task 8 files and leaves the prerequisite generation/source behavior intact.

Required mutation-teeth score: **2/2**. Hardened acceptance criteria: **6/6**.

## Findings

### Critical

None.

### Important

None.

### Minor

None.

No actionable correctness, regression-risk, test-quality, scope-discipline,
or plan-adherence issue was found.

## Acceptance-criteria matrix

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Scoring accepts exactly statuses `ok` and `truncated`. | **Pass** | `SCOREABLE_STATUSES` is exactly the required `frozenset` at `personal_apps/features/radar/scoring.py:42`, and the write guard consumes it at `personal_apps/features/radar/scoring.py:158`. The exact-set pin is at `personal_apps/tests/test_radar_scoring.py:157-159`; the behavioral truncated regression is at `personal_apps/tests/test_radar_scoring.py:138-154`. |
| 2 | Baselines and profile remain `ok`-only. | **Pass** | `baselines.usable` retains `o.status == 'ok'` at `personal_apps/features/radar/baselines.py:47`; `profile.build_profile` retains `RadarBucketSource.status == 'ok'` at `personal_apps/features/radar/profile.py:64`. Their behavioral pins pass at `personal_apps/tests/test_radar_baselines.py:71` and `personal_apps/tests/test_radar_profile.py:108`. Neither production file is in the Task 8 diff. |
| 3 | A real current-generation missing row receives none of the four score fields. | **Pass** | The test helper stamps the current generation by default at `personal_apps/tests/test_radar_scoring.py:46-53`. `test_a_current_generation_missing_bucket_keeps_all_scores_null` persists a `missing` row after scoreable `ok` history and asserts `expected`, `variance`, `mention_z`, and `baseline_days` are all NULL at `personal_apps/tests/test_radar_scoring.py:162-177`. Its guard-bypass mutation fails, proving the row really reaches the scoring loop rather than passing vacuously through generation exclusion. |
| 4 | Restoring `status != 'ok'` breaks the truncated regression. | **Pass** | Independently mutated `personal_apps/features/radar/scoring.py:158` to `if row.status != 'ok':`. The focused test failed at `personal_apps/tests/test_radar_scoring.py:151` because `truncated.expected` remained `None`. |
| 5 | Bypassing the scoreable-status guard breaks the missing-row regression. | **Pass** | Independently mutated the same guard to `if False:`. The missing-row test failed at `personal_apps/tests/test_radar_scoring.py:174`: `expected` became `1.86722` instead of `None`. |
| 6 | Cleanup owns exact `ZZ` tickers and uses no broad `LIKE`. | **Pass** | `ZZTRUNCATED` and `ZZMISSING` are explicit members of `_OWNED_TICKERS` at `personal_apps/tests/test_radar_scoring.py:24-27`; cleanup is exact `ticker.in_(_OWNED_TICKERS)` at line 33. No `.like(...)`, raw `LIKE`, or broad table cleanup appears in this test file. The unowned-`ZZ` sentinel regression at line 67 passed, and a post-test DB query returned zero rows for both owned Task 8 tickers. |

## Teeth audit — 2/2

Each mutation was applied only to the working copy of
`personal_apps/features/radar/scoring.py`, the named test was run, and the
original condition was restored with a byte-for-byte blob-hash check before
the next mutation.

| # | Mutant | Test/result | Verdict |
|---|---|---|---|
| 1 | Replace `row.status not in SCOREABLE_STATUSES` with the pre-task `row.status != 'ok'`. | `test_a_truncated_bucket_is_scored_from_ok_baselines` failed: `assert None is not None` for `truncated.expected`; `1 failed, 32 deselected in 3.45s`. | **Killed** |
| 2 | Bypass the guard with `if False:`. | `test_a_current_generation_missing_bucket_keeps_all_scores_null` failed: `assert 1.86722 is None` for `missing.expected`; `1 failed, 32 deselected in 3.45s`. | **Killed** |

After restoration, the three hardened tests passed together: `3 passed, 30
deselected in 3.50s`. The restored production file's Git blob hash was
`63efa851c01020718fb30bcec1eef8d6d8f4ad47`, identical to `HEAD`.

## Correctness, regression risk, and scope

- `score_source` still builds both the source profile and each ticker's
  `good` observations from `ok` rows only; `truncated` changes only write
  eligibility. Therefore an undercount can be ranked without contaminating
  the expectation or dispersion estimate.
- The missing regression has enough `ok` history to form a baseline and uses
  the current `source_config_version`, so the NULL result is attributable to
  the status guard. The successful guard-bypass mutation independently proves
  this causal path.
- All four score fields are asserted on both sides: non-NULL for `truncated`,
  NULL for `missing`.
- The existing leaderboard regression confirms a scored truncated source
  carries the `partial` mark (`personal_apps/tests/test_radar_leaderboard.py:202`).
- Commit `aee4e2f` has parent `47d1c2c` and changes exactly
  `personal_apps/features/radar/scoring.py` and
  `personal_apps/tests/test_radar_scoring.py`. `git diff --check` is clean.

## Commands and results

All pytest commands were run from `personal_apps/` against the configured real
local MySQL development database.

1. Repository and scope checks:

   ```powershell
   git rev-parse HEAD
   git show -s --format="commit:%H%nparent:%P%nsubject:%s" aee4e2f
   git diff --name-only 47d1c2c..aee4e2f
   git diff --check 47d1c2c..aee4e2f
   git status --short
   ```

   Result: HEAD and parent match the requested anchors; exactly two task files
   changed; diff check passed; source worktree was clean before review writes.

2. Focused covering gate:

   ```powershell
   python -m pytest tests/test_radar_scoring.py tests/test_radar_baselines.py tests/test_radar_profile.py tests/test_radar_leaderboard.py -v
   ```

   Result: **87 passed in 38.29s**.

3. Old-guard mutation:

   ```powershell
   python -m pytest tests/test_radar_scoring.py -v -k "truncated_bucket_is_scored"
   ```

   Result under mutation: **1 failed, 32 deselected in 3.45s**; failure was
   `truncated.expected is None`. Mutant killed.

4. Guard-bypass mutation:

   ```powershell
   python -m pytest tests/test_radar_scoring.py -v -k "current_generation_missing_bucket"
   ```

   Result under mutation: **1 failed, 32 deselected in 3.45s**; failure was
   `missing.expected == 1.86722`. Mutant killed.

5. Restored hardened regressions:

   ```powershell
   python -m pytest tests/test_radar_scoring.py -v -k "truncated_bucket_is_scored or scoreable_statuses_exclude_missing or current_generation_missing_bucket"
   ```

   Result: **3 passed, 30 deselected in 3.50s**.

6. Cleanup residue and source scan:

   ```powershell
   python -c "... count ZZTRUNCATED and ZZMISSING ..."
   rg -n "_OWNED_TICKERS|ticker\.in_|\.like\(|LIKE|ZZTRUNCATED|ZZMISSING" tests/test_radar_scoring.py
   ```

   Result: `{'ZZTRUNCATED': 0, 'ZZMISSING': 0}`; the only shared cleanup is the
   exact `IN` list, with no broad `LIKE`.

7. Broad Radar gate:

   ```powershell
   python -m pytest tests/ -k radar -q
   ```

   Result: **620 passed, 2 skipped, 2 failed, 646 deselected, 2 warnings in
   65.76s**. The two failures are the known page-render tests
   `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch` and
   `test_the_page_falls_back_to_the_default_board_on_a_bad_query`; both stop at
   `ViteManifestError` because
   `personal_apps/static/radar/dist/.vite/manifest.json` is absent. No other
   Radar test failed, and neither failure touches the Task 8 diff.

## Deferred minor observations

None. The absent generated Vite manifest is an environment/build-artifact
condition already documented by the implementation report, not a Task 8 code
or test finding.

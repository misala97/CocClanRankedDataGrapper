# Task 8 report: Score truncated buckets

## Scope and result

Task 8 widens `score_source` write eligibility from `ok` to `ok` and
`truncated` while leaving baseline and profile populations `ok`-only. It does
not alter Reddit source expansion, source identity, UI presentation, migrations,
or config generation.

Commit: `aee4e2fc97f0a02619212356569bbecc5045640d`

## RED: regression tests before production change

Command, from `personal_apps`:

```powershell
python -m pytest tests/test_radar_scoring.py -v -k "truncated_bucket_is_scored or scoreable_statuses_exclude_missing or current_generation_missing_bucket"
```

Result: `2 failed, 1 passed, 30 deselected in 5.48s`.

The required failures were observed:

```text
test_a_truncated_bucket_is_scored_from_ok_baselines
E assert None is not None

test_scoreable_statuses_exclude_missing
E AttributeError: module 'features.radar.scoring' has no attribute
  'SCOREABLE_STATUSES'
```

The new current-generation missing-row regression passed against the pre-task
`row.status != 'ok'` guard, as expected: the behavior already existed and the
new test hardens it to all four score fields.

## GREEN: implementation and focused verification

Added `SCOREABLE_STATUSES = frozenset({'ok', 'truncated'})` and made the
`score_source` write loop skip only rows outside that set. `baselines.usable`
and `profile.build_profile` were not changed.

Command, from `personal_apps`:

```powershell
python -m pytest tests/test_radar_scoring.py tests/test_radar_baselines.py tests/test_radar_profile.py tests/test_radar_leaderboard.py -v
```

Result: `87 passed in 39.94s`.

This includes behavioral, not source-text, protection that baseline and profile
inputs remain `ok`-only:

- `test_missing_and_truncated_are_not_usable`
- `test_missing_and_truncated_buckets_are_ignored`

It also includes `test_a_truncated_source_is_marked_partial`, confirming the
now-reachable leaderboard caveat remains present.

## Required teeth mutations

1. Restored the pre-task guard temporarily:

   ```python
   if row.status != 'ok':
       continue
   ```

   Command:

   ```powershell
   python -m pytest tests/test_radar_scoring.py -v -k "truncated_bucket_is_scored"
   ```

   Result: `1 failed, 32 deselected in 3.60s` with
   `assert None is not None` for the truncated row's `expected` field.

2. Bypassed the eligibility guard temporarily with `if False:`.

   Command:

   ```powershell
   python -m pytest tests/test_radar_scoring.py -v -k "current_generation_missing_bucket"
   ```

   Result: `1 failed, 32 deselected in 3.88s` with
   `assert 1.86722 is None` for the current-generation missing row's
   `expected` field.

Both mutations were restored before focused verification and commit.

## Broad Radar gate

Command, run once from `personal_apps`:

```powershell
python -m pytest tests/ -k radar -q
```

Result: `2 failed, 620 passed, 2 skipped, 646 deselected, 2 warnings in 65.59s`.
The only failures were the two known permitted page tests:

- `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`
- `test_the_page_falls_back_to_the_default_board_on_a_bad_query`

Both fail because `static/radar/dist/.vite/manifest.json` is absent, raising
the known `ViteManifestError`. No other Radar test failed. The two warnings are
the existing SQLAlchemy `datetime.utcnow()` deprecation warnings in auth tests.

## Changed files

- `personal_apps/features/radar/scoring.py`
- `personal_apps/tests/test_radar_scoring.py`

## Self-review

- Confirmed `score_source` retains its current-generation row query and only
  broadens the score write guard.
- Confirmed the directly owned `ZZTRUNCATED` and `ZZMISSING` fixtures are added
  to the exact `_OWNED_TICKERS` cleanup list; no broad `ZZ%` or table cleanup
  was introduced.
- Confirmed `baselines.usable` and `profile.build_profile` still filter status
  with `== 'ok'` and their behavioral tests passed.
- Confirmed the Task 9 concrete Reddit-source behavior is untouched.
- Ran `git diff --check`; no whitespace errors. The commit staged exactly the
  two implementation/test paths above.

## Concerns

No Task 8 concern. The broad gate retains only the explicitly permitted missing
Vite-manifest page failures.

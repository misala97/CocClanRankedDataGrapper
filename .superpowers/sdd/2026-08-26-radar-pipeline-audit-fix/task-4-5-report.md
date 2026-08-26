# Radar config-cleanup batch: Tasks 4 and 5

Date: 2026-08-26
Base SHA: `48c5246dea577cdc4bf8db49c264f610127d6143`
Batch SHA: `c6ff0719921d33eab321bb925f098438e7a278e3`
Commit: `fix(radar): wire source cashtag policy and remove page cap`

## Files

- `personal_apps/features/radar/ingest.py`
- `personal_apps/features/radar/config.py`
- `personal_apps/tests/test_radar_ingest.py`
- `personal_apps/tests/test_radar_config.py`

Unrelated pre-existing work in `.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/HANDOFF.md`,
`.superpowers/sdd/2026-08-26-radar-pipeline-audit-fix/progress.md`, and
`docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md` was preserved.

## Watched RED failures

Task 4, before wiring the policy:

```text
python -m pytest tests/test_radar_ingest.py::test_a_single_letter_cashtag_is_refused_on_a_general_network -v
FAILED tests/test_radar_ingest.py::test_a_single_letter_cashtag_is_refused_on_a_general_network
E       AssertionError: assert [('B', 'high')] == []
============================== 1 failed in 2.09s ==============================
```

Task 5, before deleting the constant:

```text
python -m pytest tests/test_radar_config.py::test_the_superseded_page_cap_is_gone -v
FAILED tests/test_radar_config.py::test_the_superseded_page_cap_is_gone
E       AssertionError: assert not True
E        +  where True = hasattr(<module 'features.radar.config' from '...personal_apps\\features\\radar\\config.py'>, 'PAGE_CAP')
============================== 1 failed in 1.98s ==============================
```

## Mutation/deletion evidence

The Task 4 implementation was deliberately mutated to `allow_single_letter=True`:

```text
FAILED tests/test_radar_ingest.py::test_a_single_letter_cashtag_is_refused_on_a_general_network
E       AssertionError: assert [('B', 'high')] == []
============================== 1 failed in 1.90s ==============================
```

The Task 5 deletion was deliberately mutated by restoring `PAGE_CAP = 10`:

```text
FAILED tests/test_radar_config.py::test_the_superseded_page_cap_is_gone
E       AssertionError: assert not True
============================== 1 failed in 1.98s ==============================
```

Both mutations were reverted before the final gate and commit.

## Focused gates

```text
python -m pytest tests/test_radar_ingest.py tests/test_radar_extraction.py -v
============================= 64 passed in 16.55s ==============================
```

```text
python -m pytest tests/test_radar_config.py tests/test_radar_ingest.py -k "bot_feed or single_letter or page_cap" -v
====================== 3 passed, 45 deselected in 0.15s =======================
```

```text
python -m pytest tests/test_radar_daemon.py -k "schedules_a_profile_job or schedules_a_sentiment_job" -v
====================== 2 passed, 38 deselected in 0.33s =======================
```

## Required full gate

```text
py -3.12 -m pytest tests/ -k radar -q
2 failed, 601 passed, 2 skipped, 646 deselected, 2 warnings in 76.03s (0:01:16)
```

## Concerns

The two failures are pre-existing/unrelated Radar API page tests:

- `tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`
- `tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query`

Both fail because `personal_apps/static/radar/dist/.vite/manifest.json` is absent,
raising `vite_assets.ViteManifestError`. The full gate also emitted two existing
SQLAlchemy `datetime.utcnow()` deprecation warnings. All Task 4/5 focused gates
passed.

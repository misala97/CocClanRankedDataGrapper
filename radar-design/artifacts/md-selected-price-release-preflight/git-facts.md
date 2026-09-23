# Git facts — 2026-09-15 (read-only)

| Item | Value |
| --- | --- |
| candidate workspace | C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts |
| branch / HEAD | codex/radar-selected-price-charts at daadf3868caedcb5db858378e919cba68b735f8a (no upstream) |
| `git fetch origin` | origin/main = daadf3868caedcb5db858378e919cba68b735f8a → **zero drift** between candidate base, origin/main and production HEAD |
| origin branches | origin/main, origin/codex/radar-ha1-us-daily-explore, origin/dev_coc, origin/dev_personal |
| local `main` ref | fe684540f64cf7c840aa734d1e4661ab319313bf, checked out in C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-merge; ancestor of origin/main, 89 commits behind; `git status --short` there is empty now. Stale — must not be used for integration (push `HEAD:main` from the candidate, as HA1 did) |
| fingerprint | `py -3.12 radar-design/artifacts/md-selected-price-correction-2/fingerprint.py --check-only --compare …/fingerprint-final.json` → digest **0b8554d0f73cac233dc5e55ba5e72c3f137841b10eabda2b5ba908801682b2c0**, counts 16 modified / 29 added / 5 generated, `differs_from_compare: []` |
| `git diff --check` | clean (only the known CRLF advisories on planner documents) |
| migrations | none added or modified under personal_apps/migrations |
| secret scan of untracked personal_apps files | one hit: tests/selected_price_unit/test_launcher_isolation.py — the documented dummy `RADAR_SP_DUMMY_SECRET` sentinel, not a credential |
| dirty tree | all pre-existing dirt preserved (see `git status --short`); this preflight added only radar-design/MD-SELECTED-PRICE-RELEASE-PREFLIGHT-RETURN.md, radar-design/artifacts/md-selected-price-release-preflight/ and CURRENT notices in HANDOFF.md, radar-design/HANDOFF.md, radar-design/MD-SELECTED-PRICE-LEDGER.md |

## Narrow staging scope for the application commit

Exactly the 45 non-generated paths in `radar-design/artifacts/md-selected-price-correction-2/fingerprint-final.json` with kind `modified` or `added` (all under personal_apps; the 5 `generated` dist files are Git-ignored and are rebuilt on the host by the runner's `npm run build`). Exclude `__pycache__`, dist, planner documents, PNG/log artifacts. A second documentation-only commit may carry radar-design MD-SELECTED-PRICE-* records and text evidence, following the HA1 precedent.

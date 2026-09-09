# Radar current handoff

Updated 2026-09-09, by Claude, during implementation. Supersedes the planning-stage handoff.

## Roles and next action

Codex designed and planned; Claude implemented. **Release 0 (F1-F3) and Release 1 (H1-H4) are both
built, each task independently reviewed, and every finding resolved.**

**Immediate next action: owner visual review of the opt-in `/radar/hub/`.** Nothing in either plan is
open. Do not re-dispatch anything the ledgers mark complete.

Everything after that review is the owner's decision and outside this package: whether to promote
`/radar/hub/` to `/radar/`, whether to deploy, and whether to enable board-observation capture.

## Verified workspace state

Implementation worktree: `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations`
Branch: `codex/radar-foundations`, branched from `dev_personal` at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD: 39e8042
Planning checkout: `C:/Users/michi/Desktop/CodingStuff` (branch dev_personal, unchanged)

A second worktree exists at `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-baseline-probe`,
detached at 7a9ffe4. It was created only to prove three `test_radar_ingest.py` failures predate this
work. **It is disposable** -- `git worktree remove` it when convenient.

Commits on this branch, oldest first:

| Commit | What |
| --- | --- |
| 9e8d446 | the planning package, carried in and committed |
| e4a27e9 | F1 ingest-run recording |
| d79da27 | F1 review fixes |
| 3d22902 | F2 board archive |
| 328074a | F3 activity/ops APIs |
| 236f862 | F2 review fixes |
| a178ba6 | F3 review fixes |
| ed62b32 | ledgers |
| 92da7c8 | H1 hub shell |
| 765f4f6 | handoff |
| 0f3767b | H2 chatter, research, search + the H1 review's fixes |
| c88266b | H3 watching and overview |
| 8864189 | H4 activity and administration |
| 39e8042 | the H2 and H3/H4 reviews' fixes |

Working tree is clean apart from the ledger/handoff edits in flight.

### Untracked and protected

`.env` in the worktree root is untracked and **must stay untracked**. It is a copy of the
repository-root `.env` with one line changed: `PERSONAL_DB_NAME="personal_apps_radar_wt"`.

`personal_apps/static/*/dist/` is untracked build output. A fresh worktree has none, and three
`test_radar_api.py` tests fail until `npm run build` has run. That is a workspace prerequisite, not
a defect.

In the planning checkout, `personal_apps/scripts/discover_telegram_sources.py` and
`personal_apps/telegram_candidates.json` are modified, and many untracked probes, datasets and
scratch scripts exist. **None of it was touched.** Nothing was staged there beyond reading.

## The database

`personal_apps_radar_wt` on the local MySQL 8.0.46: a full clone of the local `personal_apps` dev
database (43 base tables, 0 views, 456 MB, every row count equal at clone time). It is disposable.

Assert it before any backend test or migration:

```
cd personal_apps && PYTHONPATH=. py -3.12 -c "from app import app; from extensions import db; app.app_context().push(); print(db.engine.url.database)"
```

It must print `personal_apps_radar_wt`. If it prints `personal_apps`, the worktree `.env` is missing
or wrong -- stop, because migrations run there would hit the shared dev database.

Production is MariaDB; local is MySQL. Keep DDL portable and do not rely on MySQL-only JSON
behaviour. The migration head on this branch is d82f9afb5898.

## Tests and their results

Recorded at HEAD 39e8042, all against the disposable database:

- `npm test`: **403 passed** (root config, 32 files) and **419 passed** (radar config, 37 files).
- `npm run build`: exit 0. Emits `hub-*.js` and `hub-*.css` beside `board-*.js`.
- `pytest tests/test_radar_activity.py tests/test_radar_observations.py tests/test_radar_operations_api.py tests/test_radar_api.py tests/test_radar_daemon.py`: **194 passed**.
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py`: **85 passed**.
- `pytest tests/test_radar_hub_page.py tests/test_radar_api.py tests/test_radar_watch_api.py tests/test_gym_routes_smoke.py`: **135 passed**.
- Browser: 13 captures across all six pages and the recovery view at 1440x1000, 768x1024 and
  390x844, plus a separate keyboard and live-endpoint pass over all five destinations at all three
  widths. No document horizontal scroll, no console or page errors anywhere; the skip link is the
  first tab stop, carries a visible ring and focuses the page without replacing it.
  `reports/hub/EVIDENCE.md` records which pixels are real data and which are the one labelled
  fixture.

**Known environment failure, not caused by this work.** `tests/test_radar_ingest.py` fails three
tests on every run after the first against a persistent database
(`test_an_empty_healthy_source_stays_ok_without_database_artifacts`,
`test_fresh_mentions_carry_the_local_model_version`, `test_a_parent_context_comment_keeps_its_ticker`).
Its `_wipe()` helper does not delete `RadarMention` rows for its own ticker. Reproduced identically
at the base commit in the probe worktree with no source changes. Left alone as an unrelated suite; a
background task was raised for it.

## Findings, rulings and deviations

- Every F1-F3 review returned **no blocking findings**. All should-fix items were resolved; see
  FOUNDATIONS-LEDGER.md for the item-by-item record.
- The H1 review returned **one blocking** finding (the skip link destroyed the page) and the H2
  review **four** (absent evidence printed as zero; a tone percentage board.py returns three counts
  to prevent; a chart caption claiming a resolution the line lacked; the previous company rendered
  under the new company's heading). All resolved. H3+H4 returned none. HUB-LEDGER.md has the
  item-by-item record.
- **Scope gap found by review, now closed:** Human Chatter shipped with no server-side filters,
  which is half of its acceptance row. `static/radar/src/hub/Filters.tsx` is new and is the only
  file in Release 1 the plan does not name.
- **Deviation:** the activity payload carries one key beyond the shape the plan enumerates,
  `counted_runs`. Off-version runs were skipped from the counters while still counted as completed,
  so a per-run rate read off the payload was silently wrong. Removing it is a one-line change if
  Codex prefers the enumerated shape.
- **Accepted limit:** the activity query still transfers each run's `summary_json`; at `days=30`
  that is ~2,880 envelopes. Extracting the counters in SQL needs JSON path functions whose MariaDB
  behaviour cannot be verified from here. Worth measuring against the real server.
- **Accepted limit:** `observations.capture()` will accept a backdated `now`. The tests need it and
  the only production caller passes the wall clock; the guarantee that matters -- `observed_at` is
  never manufactured -- is structural.
- `RADAR_OBSERVATION_CAPTURE_ENABLED` and `RADAR_PRODUCER_REVISION` are set nowhere. Capture is off,
  which is the intended default until a staging pass.

## Deployment carries

Nothing here is deployed and no live migration has been run.

Before any rollout: apply migration d82f9afb5898 (additive, two tables, downgrade verified as an
exact inverse), then decide separately whether to set `RADAR_OBSERVATION_CAPTURE_ENABLED=true` and
`RADAR_PRODUCER_REVISION=<git sha>` on the ingest host. The board-observation job is registered
whether or not capture is enabled and returns immediately when it is off, so enabling it is an
environment change plus a restart.

`/radar/` is unchanged and is the rollback. `/radar/hub/` is the opt-in route for owner review.
Promoting the hub to the root route is a separate decision that has not been made.

Local preview: `PYTHONPATH=. py -3.12 scratchpad-served app on port 5051` (a two-line `app.run`
script), then `/radar/hub/`. Port 5001 belongs to the owner's own instance -- do not take it.

## Before the next session switch

Replace the sections above with the then-current worktree, branch, HEAD, dirty ownership, completed
and open tasks, review findings, exact tests and results, protected files and deployment carries.
Verify this file against Git and the reports before trusting it; if they disagree, the evidence wins
and the discrepancy belongs in the ledger.

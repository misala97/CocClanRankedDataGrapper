# Radar German Market — progress ledger

This file is the binding execution record for
`2026-08-28-radar-german-market.md`. Repository/test evidence wins over chat
memory. A task becomes complete only after implementation, focused tests,
commit, and independent read-only review acceptance.

## Workspace

- Worktree: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-german-market`
- Branch: `codex/radar-german-market`
- Base: `main` at `5a741e8bb05e32e8a157a5ddbd899da1603451e0`
- Approved design commit: `608ce93` (`docs(radar): specify German market view`)
- Protected unrelated primary-checkout files: `personal_apps/scripts/discover_telegram_sources.py`, `personal_apps/telegram_candidates.json`, `.agents/`, `.codex/`, `personal_apps/reddit_candidates.json`

## Task status

| Task | Deliverable | Status | Implementation commit | Review |
|---|---|---|---|---|
| 1 | Market-aware persistence | complete | `1372193`, `7210ef2` | accepted after fix round 1 |
| 2 | US/Xetra calendar registry | complete | `3350fb4`, `b8731cc` | accepted after fix round 1 |
| 3 | Quote quality/movement/fallback domain | complete | `ce486d7`, `70ef18a`, `1768074` | accepted after fix rounds |
| 4 | Verified Xetra instrument mapping | pending | — | — |
| 5 | Per-market polling/history/retention | pending | — | — |
| 6 | Market-aware ranking/board/detail/API | pending | — | — |
| 7 | Market selection and Berlin formatting | pending | — | — |
| 8 | Quote/session/fallback presentation | pending | — | — |
| 9 | Chart session bands | pending | — | — |
| 10 | Full verification and integration handoff | pending | — | — |

## Baseline evidence — 2026-08-28

- `npm test` from `personal_apps`: PASS, 403 general + 136 Radar = 539 tests.
- `npm run build` from `personal_apps`: PASS; gym and Radar Vite manifests built.
- Backend broad run after build: 649 passed, 2 skipped, 4 failed.
- The two API failures were setup-only (`static/radar/dist/.vite/manifest.json`
  absent in the fresh worktree); rerun after build: 2/2 PASS.
- The two remaining failures are pre-existing shared-development-database
  contamination in `test_radar_profile.py`: the fixture deletes only `PP%`
  tickers while `build_profile('bluesky', ...)` reads other persisted rows.
  Focused result: 8 passed, 2 failed. Do not weaken these assertions. Task 10
  must use an isolated test DB or fix fixture isolation outside feature logic.

## Provider research evidence — 2026-08-28

- EIX is available through Scalable and publishes 07:30–23:00 trading hours,
  but its FAQ points real-time prices to the Scalable cockpit and advertises no
  general public market-data API.
- Xetra publishes 09:00–17:30 main trading and extended retail windows 08:00–
  08:55 and after the closing auction–22:00.
- Finnhub documents Xetra and other German exchange coverage; entitlement and
  latency must be measured with the configured account.
- Twelve Data documents Xetra as EOD at the checked tier and provides catalog
  filters/fields for MIC, FIGI and optionally ISIN.

## Decisions and rulings

- All displayed times use `Europe/Berlin`; UTC remains storage/wire only.
- Germany mode maps the existing Radar companies, not a German-issuer universe.
- Xetra is initial; EIX is adapter-ready but out of scope without permitted data.
- Missing German data falls back to explicitly marked US/USD quotes.
- Delayed quotes are accepted up to 30 minutes for divergence; EOD/stale never
  look live and never contribute live price divergence.
- Regular and extended movement are separate values. Green/red retain price
  direction semantics; session colour also requires text/icon labelling.
- Task 1 is expand-only: market context columns remain nullable through the
  legacy-writer overlap. Task 5 upgrades writers/keys; a later contraction
  makes columns required after null-row verification. This corrects the
  original same-migration non-null plan, which would break the old daemon.

## Open findings

- No open Task 1 findings. Continue with Task 2 only after preserving the
  Task 1 compatibility rules in later writer/key work.

## Immediate next action

Implement Task 4: map verified Xetra instruments from permitted provider catalogs.

## Task 3 evidence — 2026-08-28

- Focused quote-domain suite advanced from 18 to 24 passing tests across two
  review-driven fixes.
- Accepted corrections: frozen/no-print tape status is injected without DB
  coupling; timestamp-less DE snapshots do not block US fallback; price
  divergence eligibility requires tape status exactly `ok`.
- Final scoped re-review of `70ef18a..1768074` was clean with no Critical or
  Important findings. Task 3 complete.

## Task 1 evidence — 2026-08-28

- TDD red: 4 intended failures for missing `RadarInstrument`, market columns,
  and migration.
- Focused green: `test_radar_models.py` + `test_radar_migration.py` = 16 passed.
- Isolated real migration path: upgrade, backfill, legacy nullable write, and
  downgrade preservation all executed on SQLite; 6 migration tests passed.
- Local MariaDB: upgraded `35c3ae366677 -> a4c8e2f19b70` successfully.
- MariaDB preservation counts after upgrade: 12,509 active universe rows and
  12,509 seeded instruments; 3,744/3,744 quotes and 11,004/11,004 daily closes
  backfilled with non-null market context.
- Broad Radar regression: 653 passed, with only the same 2 pre-existing
  shared-database profile-fixture failures documented in the baseline section.
- `git diff --check`, targeted `compileall`, `flask db heads`, and
  `flask db current`: clean; Alembic current/head both `a4c8e2f19b70`.
- Safety correction: the migration is expand-only and retains legacy keys and
  nullable overlap columns until Task 5 upgrades every writer.

## Task 1 review and acceptance — 2026-08-28

- Independent read-only review of `62b506b..1372193` found two accepted
  load-bearing issues: downgrade would retain German rows after context-column
  removal, and market values lacked database enforcement. It also noted the
  SQLite autoincrement mismatch between model and migration.
- Fix round 1 commit `7210ef2` deletes non-US price rows before downgrade,
  constrains instruments and transitional price rows to `us|de` (or NULL during
  the legacy overlap), and aligns the SQLite INTEGER autoincrement variant.
- TDD evidence for the fix: red conditions reproduced for German rollback
  retention, invalid markets, and ORM ID allocation; focused green command
  `python -m pytest tests/test_radar_models.py tests/test_radar_migration.py -q`
  passed 20 tests in 0.56s; `git diff --check` passed.
- Scoped independent re-review of `1372193..7210ef2` accepted every finding,
  reported no new Critical/Important breakage, and confirmed the fix against
  the design downgrade rule.
- Task 1: complete (commits `62b506b..7210ef2`, review clean after fix round 1).

## Task 2 evidence — 2026-08-28

- TDD red: the focused calendar run initially failed at collection because the
  registry package did not exist.
- Initial green: `python -m pytest tests/test_radar_calendar.py
  tests/test_radar_calendar_de.py -q` passed 19 tests.
- Independent review found implementation-complete but test coverage gaps for
  `session_bounds`, exact Xetra boundaries/closures, and registry error/
  compatibility behaviour.
- Fix round 1 commit `b8731cc` added black-box registry UTC-bound tests (US
  normal and early close, DE summer/winter), all seven 2026 Xetra closures,
  Dec 30 normal close, every requested boundary, exact unknown-market error,
  and legacy-wrapper equivalence.
- Focused green after the fix: the same calendar command passed 39 tests in
  0.20s; `git diff --check` passed. Scoped re-review accepted every finding
  and reported no new breakage.
- Task 2: complete (commits `3fce2b3..b8731cc`, review clean after fix round 1).

## Task 3 scoped re-review fix — 2026-08-28

- Finding: quote scoring excluded only a `stale` tape verdict, allowing fresh
  live and delayed quotes with externally supplied `closed` or `unknown` tape
  status to contribute divergence.
- TDD red: four parameterized black-box cases (`closed|unknown` ×
  `live|delayed`) failed because `score_eligible` was `True`.
- Fix: score eligibility now requires both an eligible quote quality and
  `tape_status == 'ok'`.
- Focused green: `python -m pytest tests/test_radar_markets.py
  tests/test_radar_prices.py -q` passed 24 tests in 0.14s.

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
| 4 | Verified Xetra instrument mapping | complete | `1e54ebb`, `7ce012d` | accepted after fix round 1 |
| 5 | Per-market polling/history/retention | complete | `e21a7da`, `708de59` | accepted after fix round 1 |
| 6 | Market-aware ranking/board/detail/API | complete | `55a95c5`, `c767c66`, `14d7ec4` | accepted after fixes |
| 7 | Market selection and Berlin formatting | complete | `55c8392`, `f58d413` | accepted after fix round 1 |
| 8 | Quote/session/fallback presentation | complete | `27c39e8`, `aee5e507` | accepted after fix round 1 |
| 9 | Chart session bands | complete | `28e65f9`, `73464ba` | accepted after fix round 1 |
| 10 | Full verification and integration handoff | verification complete; independent review pending | — | pending parent-dispatched whole-branch review |

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

Dispatch the independent whole-branch read-only review. Do not merge, push, or
deploy until it is clean and a final integration decision is made.

## Task 10 verification evidence — 2026-08-30

- Isolated backend gate: created the disposable local MariaDB database
  `personal_apps_radar_verify_20260830`, applied the current SQLAlchemy schema
  and only the minimal admin/exercise seed required by Radar's shared client
  fixture. The runner prevented `.env` from overwriting that database target.
  `python -m pytest` over the explicit list of all 39
  `tests/test_radar_*.py` files passed **745/745** in **52.26s**. This avoids
  the shared-development-database contamination documented in the baseline.
  The exact disposable database was dropped after the gate.
- Frontend gate: `npm test` passed **403 general + 162 Radar = 565** tests.
  `npm run build` passed, producing both gym and Radar Vite manifests.
- Redacted provider probe: configured Twelve Data and Finnhub credentials were
  detected without printing their values. The permitted combined catalog probe
  returned `catalog_reachable=False`, `xetra_rows=0`, `isin_rows=0`,
  `mapped_active_tickers=0`, `unavailable_active_tickers=0`, and no retained
  German quote sample (`age=unavailable`, `quality=unavailable`). Therefore
  current German intraday/catalog entitlement is **unavailable**; deployment
  must retain the explicit US/USD fallback path and must not present an Xetra
  quote as live. No catalog payload or credential was recorded.
- Playwright audit used the built local app and deterministic fixture payloads:
  US regular at 1440×1000/light, US after-hours at 1440×1000/dark, genuine
  Xetra EUR at 390×844/light, explicit US/USD fallback at 390×844/dark, plus
  print. Every page had a visible market radiogroup, no body horizontal
  overflow, and no console errors. Screenshots are local-only under
  `.artifacts/radar-german-market/screenshots/`; desktop light and mobile dark
  samples were inspected with the local image viewer. The narrow fallback
  header is dense but did not overflow its viewport.
- Diff hygiene: after removing two pre-existing trailing spaces from the
  approved design header, `git diff --check main...HEAD` is clean. The focused
  secret scan found only its documented search pattern and historical `...`
  placeholders in an older plan; it found no key value. Local-only artifacts
  remain intentionally untracked and must not be committed.
- Task 10 is not accepted yet: whole-branch independent review is intentionally
  deferred to the parent dispatch. No merge, push, deploy, or broad review was
  performed in this task.

## Task 9 evidence — 2026-08-30

- Initial implementation `28e65f9` added selected-market UTC intraday session
  intervals, Berlin chart ticks, and session-band rendering; focused API,
  calendar, chart tests and build passed.
- Review correction `73464ba` extended bands across price and chatter lanes,
  made Xetra 08:55 exclusive consistently, and clipped SVG labels/rectangles.
- Corrected API/calendar suite passed 62 tests, chart suite 16, and build/diff
  check passed. Scoped re-review found no Critical/Important findings.
  Task 9 complete.

## Task 8 evidence — 2026-08-30

- Initial UI implementation `27c39e8` added shared accessible quote badges,
  fallback/quality/session labels, separate regular/extended moves, and session
  tokens; focused and full frontend tests plus production build passed.
- Review correction `aee5e507` serialized row eligibility/tape state, retained
  no-print warnings, formatted EOD instants directly in Berlin time, and
  prevented unavailable rows from rendering `null` labels.
- Corrected focused suites, full frontend suite (403 + 158), build, and diff
  check passed. Scoped re-review found no Critical/Important findings.
  Task 8 complete.

## Task 7 evidence — 2026-08-29

- Initial implementation `55c8392` added typed market/quote contracts,
  accessible US/Germany selection, Berlin-fixed date formatting, and explicit
  currency formatting; full frontend suite and production build passed.
- Review found market-boundary defects in stale detail rendering and ticker
  links. Fix `f58d413` keys detail response publication to full request identity
  and retains the complete selection in ticker URLs.
- Focused 29 tests, full frontend suite 548 tests, and production build passed;
  scoped re-review found no Critical/Important findings. Task 7 complete.

## Task 6 evidence — 2026-08-29

- Initial backend contract commit `55a95c5` passed 212 focused tests.
- Review corrections added persistent regular-close data and timestamp-less DE
  fallback safety (`c767c66`), then provider-to-storage regular-close baselines
  (`14d7ec4`).
- Final focused gate passed 89 tests; final scoped review found no
  Critical/Important issues. Task 6 complete.

## Task 5 evidence — 2026-08-29

- Initial implementation `e21a7da` passed 129 focused tests, compile, diff
  check, and migration-head verification.
- Review found mixed-version rollback key collisions and legacy NULL/NULL US
  rows excluded by market-aware primary-MIC readers. Fix `708de59` dedupes
  rollback collisions deterministically, preserves binary ticker collation,
  and includes the legacy US identity in single/batched/history reads.
- Focused regression suite passed 57 tests; scoped re-review found no
  Critical/Important issues. Task 5 complete.

## Task 4 evidence — 2026-08-29

- Initial implementation used ISIN-only Xetra mapping, provider-failure
  preservation, and a redacting read-only probe; focused gate passed 72 tests.
- Review-driven correction `7ce012d` added FIGI-code compatibility,
  fail-closed catalog pagination, strict Finnhub type filtering, and manual
  plus weekly mapping refresh paths; remediation suite passed 63 tests.
- Scoped re-review accepted the correction with no Critical/Important findings.
  Task 4 complete.

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

## Task 4 review remediation — 2026-08-29

- Accepted review findings addressed: Twelve Data now reads provider `figi_code`
  (falling back to `figi`), requires a declared catalog total and retrieves every
  `/stocks` page before treating the catalog as complete, and fails closed on
  incomplete catalog evidence so the existing mapping-preservation path applies.
- Finnhub directory rows now require a recognized common-stock/ETF instrument
  type; missing or unknown types cannot establish a mapping.
- `run_radar_ingest.py` exposes `--refresh-mappings` and schedules the same
  contained `refresh_mappings` operation weekly as `radar_mappings`.
- TDD evidence: new provider-shaped, pagination, untyped-Finnhub, manual-CLI,
  and scheduler tests were observed failing before implementation. Focused
  green: `python -m pytest tests/test_radar_instruments.py
  tests/test_radar_daemon.py -q` passed 51 tests; the Task 4 suite including
  `test_radar_prices.py` remains the commit gate.

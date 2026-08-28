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
| 1 | Market-aware persistence | pending | — | — |
| 2 | US/Xetra calendar registry | pending | — | — |
| 3 | Quote quality/movement/fallback domain | pending | — | — |
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

## Open findings

None. Implementation has not started.

## Immediate next action

Execute Task 1 using TDD, commit it, request an independent read-only review,
then update this ledger and `HANDOFF.md`. Do not start Task 2 until Task 1 is
accepted.


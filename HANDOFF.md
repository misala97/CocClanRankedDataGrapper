# HANDOFF — Radar German market

## Exact state

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-german-market`
- Branch: `codex/radar-german-market`
- Base/main at worktree creation: `5a741e8bb05e32e8a157a5ddbd899da1603451e0`
- Current implementation HEAD before this handoff update: `acd76d1`
- Working tree at this handoff: intentionally dirty only in
  `personal_apps/tests/test_radar_quotes.py`, a Task 5 red test created before
  the user paused work. Preserve it; do not discard or commit it without
  completing Task 5's TDD cycle.

## Read completely before editing

1. `docs/superpowers/specs/2026-08-28-radar-german-market-design.md`
2. `docs/superpowers/plans/2026-08-28-radar-german-market.md`
3. `docs/superpowers/plans/2026-08-28-radar-german-market-ledger.md`
4. This file.

If any handoff statement conflicts with Git, migrations, tests, or provider
probe evidence, evidence wins and the discrepancy must be recorded in the
ledger.

## Objective

Build one Radar with `US | Germany`, German-local display time, real EUR German
venue quotes where verified, explicit US/USD fallback, and honest regular/
extended movement. Keep existing social identity/scoring inputs; isolate price
context by market and venue.

## Completed

- User decisions gathered and design approved.
- Official EIX/Xetra/provider capabilities researched.
- Isolated worktree created.
- Design spec written, self-reviewed and committed as `608ce93`.
- Existing frontend baseline: 539/539 PASS.
- Production frontend build: PASS.
- Backend API page tests after build: 2/2 PASS.
- Task 1 implementation committed as `1372193`, then hardened in `7210ef2`.
- Added expand-only `radar_instruments` plus nullable market context on quotes
  and daily closes; existing US rows are backfilled and legacy keys remain.
- Task 1 focused tests: 16/16 PASS.
- Local MariaDB migration applied at `a4c8e2f19b70`; active universe/instrument
  counts both 12,509, with zero null market values among 3,744 existing quotes
  and 11,004 existing daily closes.
- Independent review and scoped re-review accepted Task 1. Downgrade now
  preserves US and legacy-null price rows but deletes non-US market rows before
  context columns are removed; database constraints enforce `us|de` while
  legacy NULL overlap writes remain valid.
- Task 2 is accepted: the existing US calendar is retained through a
  compatibility wrapper, and the registry adds tested 2026 Xetra sessions,
  closures, UTC bounds, and Berlin DST handling.

## Open work

- Tasks 1–4 are accepted and complete.
- Tasks 5–10 remain pending. Never redispatch a ledger-complete task.
- After each task: focused tests, commit, independent read-only review, ruling,
  ledger update, handoff update. One implementation worker at a time.

## Known baseline issue

`tests/test_radar_profile.py` has two failures against the shared development
database because its fixture removes only `PP%` rows while profile queries see
other stored Bluesky history. This is pre-existing and unrelated to the feature.
Do not weaken profile behaviour. Use an isolated test database or repair test
isolation when running the final full backend gate.

## Protected/unrelated work

The primary checkout (not this worktree) contains user-owned changes:

- modified `personal_apps/scripts/discover_telegram_sources.py`
- modified `personal_apps/telegram_candidates.json`
- untracked `.agents/`
- untracked `.codex/`
- untracked `personal_apps/reddit_candidates.json`

Do not modify, clean, stage, move, or delete them. Feature edits belong only in
the isolated worktree.

## Tests and setup already run

- `npm install` in worktree `personal_apps`: complete, 0 vulnerabilities.
- `npm test`: 403 + 136 PASS.
- `npm run build`: PASS.
- Broad backend `python -m pytest tests -q -k radar`: 649 PASS, 2 skipped;
  setup API failures resolved after build; 2 profile isolation failures remain.

## Deploy carries

- Migration must preserve all existing US quote/daily-close rows.
- API omission of `market` must remain US for old bookmarks/embedded payloads.
- VPS needs `flask db upgrade` before the new daemon writes market columns.
- `npm run build` remains required after checkout/reset on the VPS.
- German data must be probed with configured keys without printing them.
- If German intraday entitlement is absent, deploy marked fallbacks/EOD honesty;
  never relabel EOD as live.

## Immediate next action

Implement Task 5 only: isolate polling, history, and retention by market.
Then run focused tests, commit, review, and update these handoff artifacts.
Start from the preserved Task 5 red test asserting German/Xetra/EUR quote
identity persists separately from US data.

# HANDOFF — Radar German market

## Exact state

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-german-market`
- Branch: `codex/radar-german-market`
- Base/main at worktree creation: `5a741e8bb05e32e8a157a5ddbd899da1603451e0`
- Current implementation HEAD before Task 10 documentation: `8aabbec`
  (`docs(radar): checkpoint chart sessions`).
- Working tree at this handoff: Task 10 documentation changes plus local-only
  untracked `.artifacts/radar-german-market/` verification logs, helper
  scripts, and screenshots. The artifacts contain no secrets and must not be
  committed. No protected primary-checkout file was touched.

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

- Tasks 1–9 are accepted and complete.
- Task 10 verification gates are complete, but Task 10 awaits the
  parent-dispatched independent whole-branch read-only review. Never
  redispatch a ledger-complete task.
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

- Isolated backend: all 39 `test_radar_*.py` files passed 745/745 in 52.26s
  against disposable `personal_apps_radar_verify_20260830`; the database was
  schema-created and minimally seeded locally for this run, not shared with
  development data, then dropped after the gate.
- Frontend `npm test`: 403 general + 162 Radar = 565 PASS.
- Frontend `npm run build`: PASS, including gym and Radar Vite manifests.
- Redacted provider smoke test: configured Twelve Data + Finnhub credentials
  were unable to obtain a usable Xetra catalog: reachable false, all catalog/
  mapping counts zero, and no retained German quote sample. No keys or payloads
  were printed. Treat current German intraday/catalog entitlement as unavailable.
- Playwright fixture audit: desktop 1440×1000 light/dark, mobile 390×844
  light/dark, and print; US regular/after-hours, Xetra EUR, and explicit US
  fallback were each exercised. No console errors or body horizontal overflow;
  local-only PNGs live under `.artifacts/radar-german-market/screenshots/`.

## Deploy carries

- Migration must preserve all existing US quote/daily-close rows.
- API omission of `market` must remain US for old bookmarks/embedded payloads.
- VPS needs `flask db upgrade` before the new daemon writes market columns.
- `npm run build` remains required after checkout/reset on the VPS.
- German data must be probed with configured keys without printing them.
- Current probe result is unavailable Xetra catalog/intraday entitlement. Deploy
  only marked US/USD fallbacks (or clearly EOD Xetra data if that entitlement
  later becomes available); never relabel either as live.

## Immediate next action

Task 10 verification evidence is complete. Parent must dispatch the independent
whole-branch read-only review next; resolve any accepted findings in focused
commits, then update this handoff/ledger before offering an integration decision.
Do not merge, push, deploy, or start a branch-final review from this task.

# HANDOFF — Radar Market Data v2

Read this + the execution ledger
(`docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`) completely
before touching code. Verify against `git log`/`git status` — evidence beats
prose.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-market-data-v2`
- Branch: `radar-market-data-v2`, created from `dev_personal` @ `9dadd9c`
- HEAD at last handoff update: `9dadd9c` (no implementation commits yet)
- Spec/plan commit: `9dadd9c` (binding, includes Codex amendment-review
  corrections)

## Dirty files and ownership

- This worktree: clean apart from ledger/HANDOFF until the first task commit.
- Main checkout `C:\Users\michi\Desktop\CodingStuff` (dev_personal): Michi's
  Telegram WIP (`personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`) + untracked scratchpad/measure
  scripts — PROTECTED, never commit, never touch, never clean.

## Completed / open

- Completed: Tasks 1–11 in full, INLINE, one commit per task (see the
  ledger's task table for commits and focused-test evidence). Task 1's
  capture supplement rules PASS (R1–R11); its independent review returned
  22 findings, all folded in (7ba4cd2). Dev DB is migrated to
  `6a21d4e8c9f0`.
- Open: Task 12 is DELIBERATELY DELAYED (post-rollback-window; Michi must
  authorize; the contraction migration is not written yet by design).
  Remaining operator gates are listed below.

## Operator gates before German shadow can even start

1. **R6 reference capture**: the Xetra "Tradable Instruments" file and a
   Tradegate BSX instrument list must pass their own capture-and-freeze
   (appended to the contract supplement as §3.5/§3.6, reviewed) BEFORE the
   weekly mapping job may build OpenFIGI generations. The job currently
   refuses with a loud log under shadow/active — by design.
2. Deploy with `RADAR_DE_PRICE_MODE=shadow` (+ `RADAR_MASSIVE_API_KEY` if
   also starting the close shadow), run one complete Tradegate session,
   then the report script with `--gate german`.
3. US closes: `RADAR_US_CLOSE_SOURCE=shadow`, full 2-year universe
   backfill (`--market us-universe --apply`), ≥3 accepted days,
   `--gate us-closes` + operator audit, then `massive` + evidence settings.

## Immediate next action

Final whole-branch verification (full backend suite + frontend + builds)
and one independent read-only review of Tasks 2–11; fold findings; then
report to Michi with the commit range and the operator-gate list.

## Tests

- Baseline full backend (`python -m pytest tests/ -q` in
  `personal_apps/`) + frontend (`npm test`): running in background at handoff
  write time; results go in the ledger. Known environmental quirks: none
  recorded yet.

## Rules that bind every later agent

- One implementation worker at a time; independent read-only review per task.
- Never re-dispatch a task the ledger marks complete.
- Operator gates (terms acceptance, downloads, audits, flag changes, deploys)
  belong to Michi exclusively.
- Provider flags stay at legacy defaults; no activation in this plan without
  Michi's explicit approval.
- Do not commit raw DBAG payloads, cookies, or API keys.

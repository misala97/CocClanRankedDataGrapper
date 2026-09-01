# HANDOFF — Radar Market Data v2

Read this + the execution ledger
(`docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`) completely
before touching code. Verify against `git log`/`git status` — evidence beats
prose.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-market-data-v2`
- Branch: `radar-market-data-v2`, created from `dev_personal` @ `9dadd9c`
- Implementation HEAD verified in this handoff: `0d3ea22` (the handoff-only
  bookkeeping commit follows it)
- Spec/plan commit: `9dadd9c` (binding, includes Codex amendment-review
  corrections)

## Dirty files and ownership

- This worktree: clean before this handoff/ledger refresh.
- Main checkout `C:\Users\michi\Desktop\CodingStuff` (dev_personal): Michi's
  Telegram WIP (`personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`) + untracked scratchpad/measure
  scripts — PROTECTED, never commit, never touch, never clean.

## Completed / open

- Completed: Tasks 1–11 in full, INLINE, one commit per task (see the
  ledger's task table for commits and focused-test evidence). Task 1's
  capture supplement rules PASS (R1–R11); its independent review returned
  22 findings, all folded in (7ba4cd2). Dev DB is migrated to
  `6a21d4e8c9f0`. Final Codex review findings were corrected in `0d3ea22`:
  Yahoo history identity, per-track activation truth, non-vacuous grouped
  coverage, report+map-bound audit, duplicate/basis/storage evidence,
  persisted Massive backoff, shadow-safe downgrade, and calendar compatibility.
- Open: Task 12 is DELIBERATELY DELAYED (post-rollback-window; Michi must
  authorize; the contraction migration is not written yet by design).
  Remaining operator gates are listed below.

## Operator gates before German activation

1. ~~R6 reference capture~~ **DONE 2026-09-01** (supplement §3.5/§3.6 +
   R12–R16; `features/radar/reference_universe.py`; the weekly mapping job
   now builds generations under shadow/active). See the ledger's
   "R6 reference capture" section.
2. Deploy with `RADAR_DE_PRICE_MODE=shadow` (+ `RADAR_MASSIVE_API_KEY` if
   also starting the close shadow), run one complete Tradegate session,
   then the report script with `--gate german`.
3. US closes: `RADAR_US_CLOSE_SOURCE=shadow`, full 2-year universe
   backfill (`--market us-universe --apply`), ≥3 accepted days,
   `--gate us-closes` + operator audit, then `massive` + evidence settings.

## Immediate next action

Merge the R6 reference work to `dev_personal`/`main` after its read-only
review, Michi deploys, then Michi sets `RADAR_DE_PRICE_MODE=shadow` and one
full Tradegate session runs before the `--gate german` report. Task 12
remains delayed.

## Tests

- Full backend: `python -m pytest tests/ -q` — **1752 passed** in 642.14s.
- Focused market-data regression suite — **223 passed**; fresh report suite
  after its final teeth edit — **14 passed**.
- Frontend: `npm test` — **403 general + 175 Radar = 578 passed**.
- Production builds: `npm run build` — TypeScript and both Vite builds pass.
- `git diff --check` passes (only Windows LF→CRLF notices).

## Rules that bind every later agent

- One implementation worker at a time; independent read-only review per task.
- Never re-dispatch a task the ledger marks complete.
- Operator gates (terms acceptance, downloads, audits, flag changes, deploys)
  belong to Michi exclusively.
- Provider flags stay at legacy defaults; no activation in this plan without
  Michi's explicit approval.
- Do not commit raw DBAG payloads, cookies, or API keys.

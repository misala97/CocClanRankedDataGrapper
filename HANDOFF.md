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

- Completed: Task 1 in full (INLINE — Michi rejected subagent-driven
  implementation). Michi accepted the DBAG terms in his browser and directed
  the worker to download; live capture ran 2026-09-01 during the open
  session. Supplement
  `docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md`
  rules **PASS** with rulings R1–R11 (NDJSON, one-redirect signed-GCS
  transport, no cookie, no observed corrections, XETR `lastTradeIndicator='C'`
  = closing auction, no reference channel, XETR-pre 200 MB/min ruling,
  empty-gzip market-closed). 15 capture/parity tests green.
- Open: independent read-only review of the supplement/fixtures (the Task 1
  hard checkpoint), then Tasks 2–11 sequentially inline.

## Immediate next action

1. Independent read-only review of the Task 1 supplement + fixtures +
   PASS ruling (subagent reviewer is acceptable; implementation stays inline).
2. On review-clean: Task 2 (schema expansion migration `6a21d4e8c9f0`).
3. Rulings R1–R11 adapt Tasks 5/6/7 (transport, corrections, references,
   XETR-pre fetch-on-demand); consult the supplement before those tasks.

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

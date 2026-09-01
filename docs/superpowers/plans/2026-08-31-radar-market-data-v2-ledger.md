# Radar Market Data v2 — Execution Ledger

Binding docs: `docs/superpowers/specs/2026-08-31-radar-market-data-v2-design.md`
and `docs/superpowers/plans/2026-08-31-radar-market-data-v2.md`, both at commit
`9dadd9c` (includes the 2026-09-01 `[A1]`/`[A2]`/`[A3]` amendments and the
binding Codex amendment-review corrections).

## Workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-market-data-v2`
- Branch: `radar-market-data-v2` (created from `dev_personal` @ `9dadd9c`)
- Starting HEAD: `9dadd9c` (docs(radar): tighten market data v2 rollout)
- Main checkout: `C:\Users\michi\Desktop\CodingStuff` on `dev_personal` — carries
  protected dirty files that this plan must never touch or commit:
  `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, plus untracked Telegram/scratchpad/
  measure-script WIP (see `git status` there). The worktree itself must stay
  clean of them.
- Alembic head before this plan: `f4b2d81c37a9`.
- Dev DB: MySQL 8 `personal_apps` @ localhost:3306 (tests use it directly).

## Operator gates (Michi-only; never bypassed by the worker)

- Task 1 Step 5: accept Deutsche Börse delayed-data terms, download the four
  current `DGAT/DETR` pre/post `.json.gz` files.
- Task 11 Step 8/9: shadow session, identity audit, activation flag changes.
- Any deploy. Provider flags default to legacy behavior throughout.

## Task state

| Task | State | Commit(s) | Focused tests | Independent review | Findings / notes |
|---|---|---|---|---|---|
| 1 | IN PROGRESS (steps 0–4 workable; step 5 waits on operator) | — | — | — | Hard PASS/STOP gate |
| 2 | blocked on Task 1 checkpoint | — | — | — | — |
| 3 | blocked | — | — | — | — |
| 4 | blocked | — | — | — | — |
| 4b | blocked | — | — | — | — |
| 5 | blocked (needs PASS supplement) | — | — | — | — |
| 6 | blocked | — | — | — | — |
| 7 | blocked | — | — | — | — |
| 8 | blocked | — | — | — | — |
| 9 | blocked | — | — | — | — |
| 10 | blocked | — | — | — | — |
| 11 | blocked | — | — | — | — |
| 12 | deliberately delayed (post-rollback-window; Michi authorizes) | — | — | — | — |

## Evidence log

- 2026-09-01: worktree created; baseline full backend+frontend suites started
  in background (result recorded below when finished).
- 2026-09-01: Task 1 Steps 1–4 done INLINE (Michi rejected subagent-driven
  execution — all tasks run inline in-session from here on). Capture script
  `scripts/capture_deutsche_boerse_contract.py` + tests green, read-only proof
  `grep requests|extensions|models|db\.` = no matches.
- 2026-09-01 ~10:50 UTC: operator gate satisfied — Michi accepted the DBAG
  delayed-data disclaimer in his browser and explicitly directed the worker
  to download the files itself. Live capture ran during the open session
  (08:34 UTC minute files). Discoveries: NDJSON payloads (capture tool gained
  a tested NDJSON branch), 301→signed-GCS-2s-expiry download transport,
  NO auth/cookie, zero observed corrections, `lastTradeIndicator='C'` =
  Xetra closing auction (observational proof: all C rows 15:35–15:39 UTC),
  no reference channel, XETR-pre = 200 MB/min uncompressed, empty gzip =
  market closed. Supplement written with rulings R1–R11; RULING: **PASS**.
  15 tests green incl. supplement↔fixture pointer-parity with teeth.
- Captured file SHA-256s (raw files NOT committed; local capture dir only):
  - XGAT pre  `DGAT-pretrade-2026-09-01T08_34.json.gz`
    `5bfbcd43d3b3a88ce2bba488b3ee347b9273124a71f6bdbd8928aff65076eb6b`
    (3,199,161 B comp / 42,212,673 B uncomp)
  - XGAT post `DGAT-posttrade-2026-09-01T08_34.json.gz`
    `1305b983cf6b9efe3e722cf090940773ada8e7b2f362a257bcbf72f399fe81ec`
    (12,632 B / 169,726 B)
  - XETR pre  `DETR-pretrade-2026-09-01T08_34.json.gz`
    `8dc542c60e8c1429c04debbd8af12f55265743e8f4bb68b6930b84f743a04b0b`
    (20,303,870 B / 200,552,648 B)
  - XETR post `DETR-posttrade-2026-09-01T08_34.json.gz`
    `5f391ddf43edcf2982c8620a6acebe43d471d8e128f84891718cb825c3e17125`
    (24,768 B / 369,581 B)

## Baseline

- Backend `python -m pytest tests/ -q`: RUNNING — error band visible mid-run,
  under investigation once complete (suspected worktree environment, not code;
  main-checkout suite was green at the sentiment-v2 tip).
- Frontend `npm test`: queued behind backend in same background task.

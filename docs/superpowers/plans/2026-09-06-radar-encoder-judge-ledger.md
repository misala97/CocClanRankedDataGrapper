# Radar encoder judge — execution ledger

Binding documents, both at commit `6403248` in this workspace and byte-identical
to the source working tree they were carried from:

- Spec: `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md`
  (sha256 `e7d3175…a74802`)
- Plan: `docs/superpowers/plans/2026-09-06-radar-encoder-judge.md`
  (sha256 `603699e…252831`)

Evidence and the controlled-trial ship decision are already reviewed
(`2026-09-06-radar-local-judge-REVIEW-2.md`) and are not reopened here.

## Workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge`
- Branch: `codex/radar-encoder-judge`, created from `dev_personal` @ `1f965a9`
- Starting HEAD: `1f965a9`; docs carried in as `6403248`
- Source checkout `C:\Users\michi\Desktop\CodingStuff` stays on `dev_personal`
  and carries Michi-owned dirty work (Telegram/candidate JSON, `.agents/`,
  `.codex/`, scratchpad probes, measure scripts and their tests, and the two
  revised documents still uncommitted there). **Protected: never edited,
  staged, cleaned or committed from this plan.** The root `HANDOFF.md` there
  belongs to the unrelated Xetra rollout and is not touched.
- Alembic head before this plan: `e5f8b2ca4d36`; the dev database is at it.
- `.env` copied from the source checkout (gitignored, holds DB credentials);
  same arrangement the `radar-market-data-v2` worktree already uses.

## Execution mode

Inline, at Michi's instruction (2026-09-06): I implement and review each unit
myself rather than dispatching subagents. Per unit: write the regression cases
first, watch them fail for the stated reason, implement, run the focused
checks, perform the marked mutations, restore them, rerun, review the diff,
then commit.

## Environment facts established before Task 1

1. **No isolated test database exists.** `tests/conftest.py` runs every suite
   against the real local development MySQL 8 (`personal_apps`), shared with
   every other worktree. Task 6 and Task 7a migrations land there; the columns
   they add are additive and nullable, so other branches tolerate them. The
   plan's "isolated MariaDB" for Task 8 is read as this local MySQL 8;
   MariaDB-specific behaviour (`GET_LOCK`, JSON storage) is proven on the VPS
   in Task 9.
2. **The pytest interpreter lacks `onnxruntime` and `tokenizers`.**
   `C:\Users\michi\AppData\Local\Programs\Python\Python312\python.exe` has
   flask/sqlalchemy/anthropic/pytest/alembic but neither ONNX package. Task 4
   installs exactly the two packages it also adds to `requirements.txt`.
   The training/export environment is the separate
   `C:\Users\michi\Desktop\radar_encoder_venv` (torch, onnx, onnxruntime).
3. **The exported ONNX on disk is NOT the shipping model.**
   `radar_labels/encoder/artifact/config.json` records
   `source_model: model-train8600`; `model-train13000` exists only as
   `weights.pt`. The VPS benchmark and its "verdicts identical to the PC"
   result therefore describe train8600. Task 9 must re-export train13000 to
   FP32 ONNX and redo the parity check. Tasks 1-8 are unaffected.
4. **The Haiku-era baseline is time-bound.** The removal-share baseline
   (spec §7.2) and the removal proportion `p` (spec §7.2c) come from
   `radar_sentiment_judgments` rows written 2026-08-31..09-03. Those cascade
   with their posts under 30-day retention, so they disappear around
   2026-10-01. One read-only production query is a Task 9 preflight input.
5. **Audit labour, stated before arming.** `sample_size = ceil(400 / p)`; with
   the removal share near 0.30 that is roughly 1,300 blind human labels
   between trial day 3 and day 7.

## Interpretations applied without a new design decision

Recorded so a reviewer can disagree with the reading rather than guess at it.

- "No DB transaction spans inference" (spec §7.2a) means no *locking*
  transaction — trial-row `SELECT … FOR UPDATE`, advisory lock — is held
  across a model call. The ordinary read transaction that exists today during
  an Anthropic call is unchanged, which is what keeps Task 3 a pure refactor.
- Advisory locks are taken on a dedicated `db.engine.connect()` held by the
  outer operation and released in `finally` on that same connection: a session
  commit would return the locked connection to the pool. Non-MySQL dialects
  (the sqlite model tests) no-op the guard.
- The bucket advisory guard wraps every existing `BUCKET_WRITE_LOCK` site —
  `buckets.roll_up`, `buckets.rebuild_windows`, and scoring's write — through
  one context manager rather than a second, parallel lock discipline.
- New columns follow the existing `MYSQL_DATETIME(fsp=6)` and `with_variant`
  idioms; `recipe` is `sa.JSON` (a LONGTEXT alias on MariaDB — never
  `CAST(... AS JSON)`, which that server cannot parse).
- Ledger and handoff live beside the plan as
  `2026-09-06-radar-encoder-judge-ledger.md` and
  `2026-09-06-radar-encoder-judge-HANDOFF.md`, the convention the
  market-data-v2 plan already set. The repository root `HANDOFF.md` is the
  Xetra project's and is left alone.

## Commands

Python: `C:/Users/michi/AppData/Local/Programs/Python/Python312/python.exe`,
run from `personal_apps/`. Frontend: `npm test` and `npm run build` from
`personal_apps/`. Git from the worktree root.

## Task state

Order: 1 → 2 → 3 → 4 → 5 → 6 → 7a → 7 → 7b → 7c → 8 → 9.

| Task | State | Commit(s) | Focused tests | Review | Notes |
|---|---|---|---|---|---|
| 1 stage fix | in progress | — | — | — | lands alone, first |
| 2 spec v2.1 amendment | not started | — | — | — | text only |
| 3 seam refactor | not started | — | — | — | pure refactor |
| 4 encoder adapter | not started | — | — | — | needs onnxruntime install |
| 5 trial writes | not started | — | — | — | |
| 6 provenance/spend/label | not started | — | — | — | migration |
| 7a durable state + pin | not started | — | — | — | migration |
| 7 bounded recovery | not started | — | — | — | |
| 7b audit evaluator | not started | — | — | — | |
| 7c configuration/expiry | not started | — | — | — | |
| 8 full verification | not started | — | — | — | |
| 9 package + runbook | not started | — | — | — | no deploy without Michi |

## Carried minor findings

(For the final whole-branch review. None yet.)

## Operator gates — Michi only, never bypassed

- Any deployment, artifact copy to the VPS, or trial arming.
- Any paid Anthropic call (audit labelling, prediction passes).
- Re-exporting `model-train13000` to ONNX: it runs on his PC in the ML venv
  and costs GPU/RAM and minutes, so it is asked for, not assumed.

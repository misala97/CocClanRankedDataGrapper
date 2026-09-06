# HANDOFF — Radar encoder judge

Read this and `2026-09-06-radar-encoder-judge-ledger.md` completely before
changing code. Verify every claim here against Git, the worktree and fresh
test runs; where this text and the evidence disagree, **the evidence wins**
and the discrepancy is recorded in the ledger.

This handoff belongs to the encoder-judge plan only. The repository root
`HANDOFF.md` is the unrelated Xetra history-proxy rollout — do not overwrite
or merge the two.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge`
- Branch: `codex/radar-encoder-judge`, from `dev_personal` @ `1f965a9`
- HEAD at this writing: `6403248`
  (`docs(radar): carry the revised encoder-judge spec and plan…`)
- Alembic head: `e5f8b2ca4d36`; the shared dev database is at it
- Binding docs live in this workspace at `6403248`, sha256 recorded in the
  ledger

## Dirty files and ownership

- This worktree: clean apart from the plan's own work in progress.
- Source checkout `C:\Users\michi\Desktop\CodingStuff` (branch `dev_personal`)
  holds Michi-owned WIP: `scripts/discover_telegram_sources.py`,
  `telegram_candidates.json`, `.agents/`, `.codex/`, `reddit_candidates.json`,
  the scratchpad probes, `scratchpad/label_export/`, the measure scripts and
  their tests, plus the two revised documents still uncommitted there.
  **Protected. Never edit, stage, clean or commit any of it from this plan.**

## Completed tasks

Setup only. `6403248` carries the spec and plan into the workspace; the
ledger and this handoff follow it. No implementation task is complete.

## Immediate next action

Task 1 — "Stage, not model id" — in
`personal_apps/features/radar/llm_sentiment.py`, landing alone and first
because it fails silently and every later task moves code around it.

Two changes: `apply_judgments` decides `review_stands` from one bulk
`radar_sentiment_judgments` lookup (`stage='review'`, current
`PROMPT_VERSION`, this batch's mention ids) instead of comparing
`mention.sentiment_model` to `REVIEW_MODEL`; and `review_candidates` drops
its `sentiment_model == PRIMARY_MODEL` filter while keeping
`V2_ACTIVATION_CUTOFF`, the prompt-version fence and the reviewed
`NOT EXISTS`.

## Unresolved findings and rulings

None open. Five environment facts and five interpretation rulings are
recorded in the ledger; they were surfaced before implementation began and
none of them required a new design decision.

## Tests and known environmental failures

Nothing has been run in this workspace yet. Baselines to establish with
Task 1: `tests/test_radar_sentiment_v2.py` (45 tests) and
`tests/test_radar_llm_sentiment.py` (10). Every suite uses the real local
development MySQL 8, so a failure that mentions missing seed data is
environmental, not a regression — say which, with the output, rather than
reporting a clean run.

## Protected files and deploy carries

- Never committed from this plan: anything under the source checkout listed
  above; `.claude/skills/`; the model artifact itself (566 MB of data, not
  code — it ships by `scp` and is pointed at by `active.json`).
- Deploy carries: two new Alembic revisions (Tasks 6 and 7a), two new pip
  dependencies (`onnxruntime`, `tokenizers`, no torch), a systemd
  service/timer pair for the trial watchdog, and a 2 GB swapfile. Michi runs
  every deploy himself. Nothing reaches production before Task 9, and Task 9
  stops at packaging plus the runbook until he authorises activation.

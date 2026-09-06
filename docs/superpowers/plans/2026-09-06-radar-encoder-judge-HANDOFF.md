# HANDOFF — Radar encoder judge

Read this and `2026-09-06-radar-encoder-judge-ledger.md` completely before
changing code. Verify every claim against Git, the worktree and fresh test
runs; where this text and the evidence disagree, **the evidence wins** and
the discrepancy is recorded in the ledger.

This handoff belongs to the encoder-judge plan only. The repository root
`HANDOFF.md` is the unrelated Xetra history-proxy rollout — do not
overwrite or merge the two.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge`
- Branch: `codex/radar-encoder-judge`, from `dev_personal` @ `1f965a9`
- Alembic head: `b3d9e1f5a274`; the shared dev database is at it
- `.env` copied from the source checkout (gitignored, DB credentials)

## Completed tasks

All eleven implementation units, the fixes for Codex's third review (all
six findings, `b8f4a82`..`55793b1`) and for its fourth (all four,
`aa380f4`); the ledger's review-round records have the tables. Nothing
is deployed; nothing is merged.

| task | commit |
|---|---|
| 1 stage fix | `fbbd774` |
| 2 spec v2.1 amendment | `af11dfa` |
| 3 seam refactor | `43f9b35` |
| 4 encoder adapter | `379cb9f` |
| 5 trial write path | `645ad49` |
| 6 provenance, spend, label | `524787b` |
| 7a durable trial + retention pin | `f320f6d` |
| 7 + 7b recovery and audit evaluator | `3fcfc0f` |
| 7c configuration, startup, expiry | `769f66c` |
| 8 verification | (this commit) |
| 9 runbook | `2026-09-06-radar-encoder-judge-runbook.md` |

## Immediate next action

Michi stopped the Codex loop after round 4 (the fifth brief exists and
was not sent). Next, in order:

1. **Merge to `dev_personal`.** Nothing here activates on merge: the
   default is `RADAR_JUDGE_PRIMARY` unset, which judges nothing.
2. **Deployment**, per the runbook. The owed preflight inputs are in its
   §0, §7 and §10: a named labeller, the four supplemental files from
   `build_supplemental_sets.py` (§7), and a chosen seed. The incumbent's
   predictions come from a Haiku subagent in Claude Code (§10), not the API.

## Unresolved findings and rulings

- **The exported ONNX is `model-train8600`, not the shipping
  `model-train13000`.** The VPS benchmark and its "verdicts identical to
  the PC's" result therefore describe the wrong model. Runbook §1: re-export
  in the training venv and redo the parity check. Nothing in Tasks 1–8
  depends on this.
- **The Haiku-era baseline expires around 2026-10-01** with 30-day post
  retention. One read-only production query, in runbook §0.
- **The audit needs roughly `ceil(400/p)` blind human labels** between trial
  day 3 and day 7 — near 1,300 at a removal share of 0.3. No labeller is
  named yet.
- **`evaluate` takes prediction files rather than making them.** Generating
  the Haiku set costs money, and quota is never spent unasked. The runbook
  documents it as an authorised step.
- One deliberate behaviour change from Task 3, recorded in its commit: a
  successful response with no usage object now counts as one call with zero
  tokens. Anthropic always sends usage; a free backend needs to be able to
  report `Usage(0, 0)` and still be seen to have run.
- **The locked natural set has no per-row predictions on disk.** The spec
  (7.2c/7.3) makes it a required input of a complete audit report, the
  code enforces that, and Codex ruled (round 4) that it stays required.
  Producing it is an operator step on the PC (runbook §10). Since round 4
  its MEMBERSHIP is also frozen at arming (runbook §7).
- **`recover_trial(apply=True)` now requires a stopped trial.** The CLI and
  the watchdog already stop first. Recorded in the ledger as an
  interpretation, not a design change.

## Tests, and the one environmental failure

Full suite rerun after the review fixes; the figures are at the end of
the ledger's review-round record. Frontend untouched this round: vitest
403 + 269, `tsc --noEmit` and both Vite builds were clean at Task 8 and
were not rerun.

**`test_diagnose_extractor_feedback.py::test_the_full_run_is_read_only_and_recommends_nothing_yet`
fails for a data reason, not a code one.** It asserts a `LEGACY-POLICY
cohort` — mentions with `first_seen < 2026-09-01` — and the dev database has
none. The Task 7a retention tests were dated 2027, so their cutoffs landed
in the future and the real pruners they call deleted this machine's
development posts, mentions, judgment history and journal. Buckets survived;
production was never touched. Michi's ruling: "I really dont care. Thats
what the dev db is for." The suite now lives in 2020 behind wrappers that
refuse any cutoff past 2021.

It passed before the wipe (13/13 during the Task 3 teeth check). It was not
made green by planting an old row, which would be doctoring the environment
to make a test pass.

The dev database also holds 476 posts and 614 mentions from an ingest daemon
that started accidentally during a Task 7c teeth check and was killed; its
cursor and poll-state rows were cleared, the posts were left.

## Protected files and deploy carries

- Never committed from this plan: the Michi-owned dirty work in the source
  checkout (`scripts/discover_telegram_sources.py`, `telegram_candidates.json`,
  `.agents/`, `.codex/`, the scratchpad probes, the measure scripts and their
  tests); `.claude/skills/`; the 566 MB model artifact, which is data and
  ships by `scp`.
- Deploy carries: two Alembic revisions (`a1c4f7b2e6d8`, `b3d9e1f5a274`),
  two pip dependencies (`onnxruntime`, `tokenizers`, no torch), a systemd
  service/timer pair for the trial watchdog, and a 2 GB swapfile.
- Michi runs every deploy. Nothing reaches production without him, and the
  trial cannot arm itself.

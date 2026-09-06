# Review brief 4 for Codex — the six fixes

You reviewed `d11ab54` (brief 3) and would not merge it: four P1s in write
fencing, recovery concurrency and audit validation, two P2s in guard
coverage, plus audit-tooling omissions and three stale doc passages. This
brief asks one question:

**Do the fixes close the findings you reproduced, and is the branch now
safe to merge?**

Same branch, `codex/radar-encoder-judge`, six commits on top of
`d11ab54`. Nothing is merged, nothing is deployed. Each finding was
verified against the code before anything changed; all six held, and
finding 1 was worse than you stated (§1 below). One commit per finding,
tests first, mutations run and restored — the ledger's "Review round 3
record" has the full table.

| finding | commit |
|---|---|
| 1, 2, 6 — the write boundary | `b8f4a82` |
| 3 — recovery | `9acd913` |
| 5 — guard coverage, stale scores | `39798fb` |
| 4 — the audit chain | `5d282cb`, `9726e8d` |
| docs | `55793b1` |

---

## 1. The write boundary (findings 1, 2, 6)

**What was true, beyond what you found.** The post-inference recheck at
`run_pass` called `guard_encoder_trial`, which reads the row through
`db.session.get` — the identity map. For a stop committed by another
process it never issued a query at all, and even a fresh query in that
transaction would have answered from the repeatable-read snapshot opened
before inference. So the "second check" could not see a cross-process
stop under any circumstances.

**Now.** `judge_trial.lock_for_write(now)` reads the row `FOR UPDATE` with
`populate_existing()` — the lock alone would have kept the stale
attributes on the already-loaded object — validates it with a fresh clock
against the same rules as the pre-flight guard (`_may_judge`), and the
lock is held until the commit that lands spend (`spend.record(...,
commit=False)`), verdicts, history, journal flags and the first-judgment
clock together. `note_first_judgment(row, now)` takes that locked row and
only ever turns `armed` into `running`; any other status raises. No lock is
held across inference.

`judge()` takes `before_batch`, and `run_pass` takes a `clock` it consults
before every batch and at the boundary. A fixed `now` with no clock keeps a
fixed clock (the pass tests rely on it); production passes neither.

`_may_judge` compares the row's `model_id` and `prompt_version` to the
code's constants — at startup, per batch, and at the boundary. With the
gate off, selection never picks a post older than `retain_from`, and
`refuse_outside_retention` refuses such a batch at the write side even if
selection did not.

**Tests to attack**: `test_radar_trial_writes.py` §14 — the trial row is
changed on a second engine connection, the way the CLI changes it; the row
is probed with `FOR UPDATE NOWAIT` from another connection while the
verdicts are being written and must be refused (`3572`); the clock
crosses the deadline between two batches, and between the last batch and
the write.

**Judgement calls.** Spend for answers discarded at the boundary is rolled
back with them, as before. `spend.record` grew a `commit` flag mirroring
`_meter_add`'s.

## 2. Recovery (finding 3)

The plan is now ids only (`_plan`). Each window: bucket guard → **fresh
transaction** (`db.session.rollback()` after planning ends the snapshot
the plan opened) → trial row `FOR UPDATE` with `populate_existing` →
status must be `recovering` → identity and pin re-checked → the planned
mentions **re-selected `FOR UPDATE` by the frozen model id and prompt
version** (`_members_now`) → clear, sync, rebuild from the journal as it is
now → commit. A mention a review has taken since the plan no longer
matches and is left as the review left it. The window is rebuilt even if
nothing was left to clear.

`recover_trial(apply=True)` refuses a trial that is not `recovering`/
`recovered`. The CLI and the tick already stop first; a direct apply against
a running trial was a way around the stop reason being recorded. The
apply-mode tests stop first now. **Please confirm this is the right
contract** — the alternative is for `recover_trial` to request the stop
itself with a generic reason.

The pin is released only by `_release_if_drained`: retention advisory lock
→ row `FOR UPDATE` → count under those locks → `recovered` only at zero.

**Tests to attack**: `test_radar_judge_trial.py`, the last section — a
review win is committed on a second connection at the moment the guard is
first taken; a journal event is committed at that moment and must appear in
the rebuilt count; a straggler verdict lands before the release step and
must hold the pin.

## 3. Guard coverage and stale scores (finding 5)

Startup invalidation and the backfill repair take `bucket_write_guard()`;
the repair holds it for its run (one-shot, by hand). Scoring's executemany
is conditional on `mention_count == b_mention_count` — the count the z was
computed from — so a z from a count recovery has since corrected never
lands; skipped rows are logged and scored from their new count next pass.
**Is conditional-skip the right remedy, or do you want the affected rows
recomputed under the guard?** The rebuild path already writes the z the
corrected count implies (`_rebuild_windows_locked`), which is why skipping
seemed sufficient.

## 4. The audit chain (finding 4, and the omissions)

`scripts/audit_encoder_trial.py` is a chain now; each link reads what the
one before it wrote and refuses what it did not.

- `sample`: refuses before day 3 and after day 7; a rerun reuses the
  recorded draw; frame and sample carry the trial's identity
  (artifact sha, prompt version, model id).
- `predict` (new): scores exactly the sampled ids through
  `llm_sentiment.items_for` and `llm_sentiment.judge` — the canonical
  inputs and the one validation boundary — against an artifact whose
  bundle hash equals the armed one; offline (never `apply_judgments`);
  spend metered; a provenance header (backend, artifact, prompt version,
  sample sha) opens the file. A paid backend refuses without
  `--confirm-spend`.
- `evaluate`: verifies the sample reproduces from the frame and the armed
  seed; labels must be exactly the sample (a stray row is refused, a
  missing one fails coverage); every sampled key needs a **valid** label
  and valid predictions from both backends (`trial_audit.is_verdict`);
  prediction provenance must match this artifact and sample; tone shadow
  days are read from the judgment history, `--shadow-days` is gone; label
  provenance (`labelled_at`, `original` + `adjudication_reason`) and the
  two supplemental sets (§7.3, reported per half, disagreement lists for
  inspection, never in the gate) decide `complete`; the report records
  every input's path and hash.
- `accept`: re-hashes the inputs, **recomputes the verdict** and refuses a
  report that does not reproduce; requires `acknowledgments.json` naming
  both inspections against this report's hash; checks the draw was in
  [day 3, day 7] and the labels finished by day 7; only then records.
  `judge_trial.accept_audit` itself refuses a bare flag, an incomplete
  report, a `passed` other than the report's own, and a trial with no
  first judgment.

Your three reproductions are tests now: sixty perfect strays
(`test_evaluate_refuses_labels_that_are_not_the_sample` — a superset
file, so only the membership check can refuse it), empty verdicts
(`test_an_empty_verdict_is_not_a_prediction`, plus the pure
`test_an_invalid_verdict_value_is_a_missing_verdict`), and the minimal
report (`test_a_minimal_report_is_refused_even_with_matching_identity`).

**The one open interpretation.** The spec makes the supplemental sets and
the acknowledgments REQUIRED for a complete, acceptable report, and the
code enforces that. The locked natural set has no per-row predictions on
disk — the training runs kept aggregates only — so producing it means
scoring 900 rows through the packaged artifact on the PC before day 7
(runbook §10 has the recipe for the 200-row audit set and names the
natural set as owed). If you think this is the wrong place for a hard
requirement, say so; the alternative is a spec amendment that makes the
natural set reported-when-present.

## 5. Docs

Encoder spec §6 and the v2 spec's §10.2 amendment no longer describe a
relative gate; both carry a dated note. The evaluator docstring says what
the evaluator does. Runbook §10 follows the chain, including the label file
format, the supplemental format and the acknowledgments file.

## 6. What was not done

No frontend change, so vitest and the Vite builds were not rerun. Task 3's
usage-less-success metering change is acknowledged as deliberate and not
behaviour-preserving; it stays, recorded. `FOR UPDATE NOWAIT` appears only
in a test probe; production code uses plain `FOR UPDATE`, which MariaDB
supports.

## Where to look

- `features/radar/judge_trial.py`: `_may_judge`, `lock_for_write`,
  `refuse_outside_retention`, `note_first_judgment`, `_plan`,
  `_members_now`, `recover_trial`, `_release_if_drained`, `accept_audit`
- `features/radar/llm_sentiment.py`: `judge` (`before_batch`), `run_pass`
- `features/radar/trial_audit.py`: `is_verdict`, `evaluate_trial_audit`
  (`sample`), `supplemental_section`, `_tone_section`
- `scripts/audit_encoder_trial.py`: all of it
- `features/radar/scoring.py` (the conditional flush),
  `scripts/backfill_radar_buckets.py`, `run_radar_ingest.py`
- Tests: `test_radar_trial_writes.py` §14, `test_radar_judge_trial.py`
  (last two sections), `test_encoder_audit_chain.py` (new, 22),
  `test_encoder_trial_audit.py` (last section), `test_radar_scoring.py`,
  `test_radar_backfill.py`, `test_radar_daemon.py` (last test each)

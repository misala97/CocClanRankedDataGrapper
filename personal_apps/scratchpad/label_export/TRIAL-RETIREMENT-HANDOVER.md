# Handover: retiring the encoder trial and deploying base

**For an independent verifier (Codex).** Written 2026-09-07 ~23:00 CEST by the
session that ran the day-1 audit. Verify against the boxes and the code before
anything is executed; where this document and the evidence disagree, the
evidence wins and the discrepancy gets recorded here.

> **Reviewed and corrected 2026-09-07 ~23:30 UTC** against production
> (`194.164.29.97`, HEAD `b1d1a7c`, read-only) and against deployed `main`.
> Corrections are marked **[CORRECTED]** inline. `TRIAL-RETIREMENT-PLAN.md` is
> now at **Revision 2**; its §A lists every claim Revision 1 got wrong. Read
> the plan's §0 (verified facts) and §1 (the artifact blocker) before acting on
> anything in this file.

Nothing in the plan section has been executed. Production is untouched beyond
what "State of the world" records as already shipped.

---

## 1. The decision Michi made, in his words

> "The smarter choice would be to just abandon the trial. Stop it. Put the
> better base encoder on the VPS and have better results instantly. We can
> still run tests and analysis from time to time, but encoder is literally the
> only choice. And it is better than the lexicon."

He is right on the substance and the reasoning is recorded in §4. The open
question is purely operational: the word "stop" has a specific and destructive
meaning in this codebase (§5).

## 2. State of the world

**Production is 194.164.29.97** (migrated from 82.165.240.212 earlier today;
the old box is stopped, disabled and intact as a fallback). Repo at
`/root/coc-stats`, deployed commit is main `b1d1a7c`.

Live and healthy: `coc_web`, `personal_apps_web`, `coc_scheduler`,
`personal_apps_gym_notifier`, `radar_ingest`, `radar-encoder-trial.timer`.

**The trial**: status `running`, model `radar-encoder-v1`, artifact sha256
`3bb32b5607a8a368...`, armed 2026-09-06 19:32:33 UTC, first judgment 19:38:24.
Deadline **2026-09-09 19:38:24 UTC**. At that moment, with no passing audit, the
watchdog stops it and recovers — i.e. UNDOES its judgments.

**[CORRECTED] — all of that verified first-hand on production**, plus three
things this file did not say:

- `audit_evaluated_at` and `audit_passed` are NULL; `retain_from` is
  2026-09-04 19:45:00; `stop_reason` is NULL. `radar-encoder-trial.timer` is
  `enabled` and `active`, firing every minute.
- **The trial has judged 1,546 mentions** (`radar_mentions` and
  `radar_sentiment_judgments` agree). That is **fewer than the watchdog's
  `--limit 2000`**, so one firing drains the trial completely, flips it to
  `RECOVERED` and releases the retention pin. There is no partial, catchable
  drain.
- **The labelling window is still open.** `AUDIT_LABEL_DAY = 2` puts
  `labels_due` at **2026-09-08 19:38:24 UTC**. The plan's Revision 1 claimed it
  had already closed "by luck"; it had not, so the `accept` route stayed a live
  destructive path.

**Shipped today, already on main and deployed:**
- Bluesky drain budget 45s -> 120s (`74482fe`), fixing a coverage collapse from
  889 to 374 captured minutes per day. Not an extraction change:
  `source_config_version` is unchanged at `3f96922d51fe4ef0`.
- The encoder now PUBLISHES tone (`b82aea0`), post cards say "Encoder". See §4
  for the measurement that justified it.

**Not shipped, sitting on `dev_personal`**: the extractor recall work, the span
dataset for the future NER model, the tone-head training recipe.

## 3. The day-1 audit, in full

Chain run tonight, all reproducible, files in `/root/trial-audit` on the VPS
and mirrored to `C:\Users\michi\Desktop\radar_labels\trial-audit`.

- `sample`: frame frozen at 6,207 mentions (the encoder's first 24h, cut
  19:38:24 UTC), 746 drawn with the arming seed 20260906.
- `predict --backend encoder`: all 746 scored offline against the frozen
  artifact.
- `export-prompts` + subagent Haiku pass + `import-predictions`: 746/746 after
  two rounds of correction (see §7).
- Reference: **`reference.jsonl`, 746 rows, produced by OpenAI's GPT "Astra"**,
  blind (no model answers visible). Provenance recorded in
  `reference.provenance.json`. NOT human, though the chain asks for a human —
  see §6.
- `evaluate`: **FAILED**, report at `/root/trial-audit/report.json`.

| criterion | encoder | incumbent (Haiku) | threshold | result |
|---|---|---|---|---|
| removal_precision (Wilson lower) | 0.803 (point 0.849, 247/291) | 0.700 (point 0.755, 203/269) | >= 0.93 | **FAIL** |
| relevance_agreement | 0.724 (540/746) | 0.594 (443/746) | >= incumbent point - 0.02 | pass (reported only) |
| content_origin_agreement | 0.930 (694/746) | 0.814 | reported only | pass |

The report is also marked `complete: NO` for two reasons, both mine to fix:
every reference row lacks a `labelled_at` field, and no supplemental audit /
natural sets were supplied.

## 4. Why abandoning the trial is defensible

**The gate asks a question whose premise is gone.** It was written to answer "is
the encoder safe enough to replace Haiku". Haiku has had no API credits since
2026-09-03. The real alternative is not Haiku at 0.755, it is **no judge at
all**, which means ~46% junk counts on the board.

**Nothing reachable clears 0.93.** Encoder 0.849, Haiku 0.755, and base
measured 0.881 removal precision on the locked sets, so base would likely land
near 0.88 and still fail. A bar no available option can reach is not
protecting anything.

**What 0.849 actually buys**, on the 746 sampled: 291 removed, 247 correctly,
44 real mentions wrongly deleted = 5.9% of the sample, against roughly 40% of
the sample being junk that would otherwise count. For a board that ranks by
chatter volume that is a good trade.

**The same error was already made once tonight and corrected.** Encoder tone
was suppressed on the reasoning that "a wrong arrow is worse than no arrow" —
but blank was never the alternative, the board falls back to the lexicon.
Measured over the 5,583 labelled rows where the author clearly took a side:

| | silent | wrong side |
|---|---|---|
| lexicon (was shipping) | 59.7% | 29.8% of the calls it makes |
| encoder small | — | 11.8% |
| encoder base | — | 6.2% |

Aggregation matters too: at a 12% per-mention reversal rate a ticker showing 7
bullish against 1 bearish reads the wrong net direction 3.6% of the time; under
the lexicon's rate, 28%. Michi identified this; I had argued the wrong way.

**Base is better on every tone measure** (6 epochs, same recipe, log
`encoder/base-2026-09-07.log`): reversals natural 11.8% -> 6.2%, hard 8.7% ->
6.8%, recall 8.7% -> 7.9%; attitude accuracy 0.587 -> 0.648. Relevance did NOT
improve (0.750 -> 0.733 natural), which contradicted my prediction.

**[CORRECTED] — "encoder small" in that table is NOT the model in production.**
Read out of the checkpoint configs: the 11.8% row is `model-train17090`
(deberta-v3-**small**, max_len **512**, 17,090 rows, tone mask + reversal
penalty). The **deployed** artifact is `model-train13000` (small, max_len
**256**, 13,492 rows, **no** tone mask, **no** reversal penalty), whose locked
natural numbers are rel F1 0.711 / origin F1 0.748 / attitude acc **0.720** /
removal P 0.880 / **reversals 16.5%**.

Against what is actually serving, base is:

| | deployed small@256 | base@512 | |
|---|---|---|---|
| polarity reversals (natural) | 16.5% | **6.2%** | much better |
| relevance macro-F1 | 0.711 | 0.733 | better |
| removal precision | 0.880 | 0.881 | flat |
| origin macro-F1 | 0.748 | 0.723 | **worse** |
| attitude accuracy | 0.720 | 0.648 | **worse** |

So "better on every tone measure" is not supportable. The defensible claim is
narrower and still strong: **base more than halves the rate at which a
directional call points the wrong way, at the cost of calling a direction less
often** — the expected effect of the tone mask added in the same jump, and the
trade the board wants. Four variables moved at once (backbone, window, training
set, loss), so the reversal gain cannot be attributed to the backbone alone.
Plan Revision 2 §1.3 carries the full table.

## 5. THE TRAP — why this is not just `stop`

`stop` sets the trial status to RECOVERING, and the watchdog then runs
`recover_trial(apply=True)`, which is **designed to undo the encoder's
judgments**. That is the same outcome as letting the deadline pass. So the
obvious way to "abandon the trial" produces exactly the thing we are trying to
avoid: the junk comes back.

Also blocking: `judge_config.py:179-184` **[CORRECTED — not `:173-178`]**
refuses to start the encoder when the deployed artifact's `bundle_sha256()`
differs from the armed trial's `artifact_sha256` — "replacing a file is a
different trial". So base cannot be deployed while this trial is armed.

**A workflow of four readers plus three adversarial verifiers was run to
establish the exact semantics and a safe path. Its output is §8 below.**

## 6. Things a verifier should be suspicious of

- **The reference is a model, not a human.** `cmd_export_labels` says "the
  blind file a human labels" and that the previous audit was discarded for
  insufficient independence. GPT-Astra is independent of BOTH judges (the
  encoder was trained on Sonnet labels, Haiku is the incumbent), which is the
  property that matters, but it is one pass with no majority vote, so
  inter-labeller disagreement is unmeasured. It calls **29% of the sample
  `uncertain`** against Haiku's historical 3.4% and the encoder's 16% — a far
  more cautious labeller than either judge. Whether that inflates or deflates
  the agreement numbers is NOT established.
- **The 0.93 threshold's provenance is unverified.** Whether it is a code
  constant, a value stored at arming, or config — and therefore whether a new
  trial could be armed at a different bar without editing code — is one of the
  questions the workflow was asked to settle.
- **`stored_row_carries_tone` replaced `writes_tone_for_model` today.** The old
  function judged a row by its model id; one id now covers both the tone-less
  rows written before tone was enabled and the tone-bearing ones after. If
  recovery or acceptance logic depends on that distinction anywhere I did not
  find, it needs re-checking.
- **I introduced and fixed a real safety regression today**: the trial gate was
  keyed on `writes_tone is False and id == ENCODER`. Turning tone on made that
  false and SILENTLY skipped the armed-trial requirement and the artifact
  check. Now keyed on identity. Look for other places keyed on incidental
  properties rather than identity.

## 7. Failures in tonight's process, for calibration

- Subagents silently dropped 7 of 746 items, and the batch that "self-reported
  all valid enums" still had two `attitude: uncertain` values, which that field
  does not allow. **Local validation caught both; the agents' own reports did
  not.** Do not trust a subagent's summary of its own output.
- The prompt files never named the JSON envelope (production supplies it via
  the API response schema), so workers invented their own shapes.
- I burned significant output guessing at a file's key names twice instead of
  reading its shape first.
- My first `reference.jsonl` carried a provenance header line, which the chain
  correctly refused ("line 1 names no mention_id"). Provenance now lives in a
  sidecar.

## 8. The plan

`TRIAL-RETIREMENT-PLAN.md`, beside this file. Produced by a workflow of four
code readers plus three adversarial verifiers (data-loss, deploy-correctness,
rollback), then synthesised by an agent that re-derived every load-bearing
claim against deployed `main` rather than against this worktree. The supporting
evidence is in the seven `TRIAL-RETIREMENT-read-*.md` / `-verify-*.md` files.

Its headings: §0 facts verified first-hand, §1 the recommended path (Phase 0
preserve / Phase 1 defuse deadline / Phase 2 ship base), §2 paths that look
attractive and destroy data, §3 open questions that need Michi, §4 the 0.93
threshold's provenance, §5 where the synthesiser disagrees with its own inputs.

**Three findings from that run change what a verifier must check, and one of
them invalidates part of what the reader agents themselves wrote:**

1. **This checkout has the WRONG trial schedule.** Deployed `main` carries
   `AUDIT_DRAW_DAY=1 / AUDIT_LABEL_DAY=2 / TRIAL_DEADLINE_DAYS=3`; `dev_personal`
   still has 3/7/10. So **every trial command run from
   `C:\Users\michi\Desktop\CodingStuff` against the production database computes
   with the wrong clock and lies** — `tick` would report nothing due on an
   expired trial, `accept` would refuse a valid day-1 draw. Trial commands must
   be run on the VPS from `/root/coc-stats`. For the same reason, reader
   citations into `judge_trial.py` past ~line 575 are a line or two off against
   production; check the symbol, not the number.
   **[CORRECTED]** The drift is not "a line or two". Verified against deployed
   `main`: everything below `judge_trial.py:600` is unshifted, `_may_judge`'s
   guards are **+10** (missing row is `:679-682`, not `:669-672`), and `tick`'s
   two `recover_trial(apply=True)` calls are **+14** — the `RECOVERING` branch
   is `:799-803` (call at **:801**) and the expiry branch `:805-816` (call at
   **:814**), not `:785-789`/`:790-792`. Plan Revision 1 wrote its hunks against
   the wrong numbers; Revision 2 §0.6 carries the full table.
2. **Disabling the timer does not defuse the deadline.**
   `run_radar_ingest.py:1272` calls `judge_trial.tick()` at daemon startup,
   before the judges initialise. After 2026-09-09 19:38:24 UTC, any restart of
   `radar_ingest` — including a routine `./update_coc.sh` — would itself drain
   the judgments. This is the single most important thing to re-verify.
   **[CORRECTED, two ways.]** (a) `update_coc.sh` is *not* the danger: it stops
   `radar_ingest`, does `git reset --hard origin/main`, and starts it last, so
   the startup tick always runs the code that deploy installed. (b) The real
   uncovered path is **`Restart=always` / `RestartSec=30` on `radar_ingest`** —
   after the deadline, any crash or reboot restarts the daemon on unpatched
   code 30 s later and fires the startup tick with no operator involved.
   Masking the timer does not touch it; only the deployed code, or a stopped
   daemon, does. The plan's deploy order must therefore be safe on either side
   of the deadline (Revision 2 §2.5), not assume a pre-deadline landing.
3. **The rollback asset is unprotected and cannot be recreated.** The audited
   small artifact exists only in a gitignored directory inside a stale worktree
   (`CodingStuff-worktrees/radar-encoder-judge/.../artifacts/judge/v1/`). Its
   bundle hash was re-derived and matches the armed trial's
   `3bb32b5607a8a368...` exactly. It cannot be rebuilt: the packager stamps
   `packaged_at_git_head` into `config.json`, and `config.json` is inside the
   bundle hash, so any repackage yields a different hash and fails the artifact
   check in §5. Copying it somewhere durable is step 0a of the plan.
   **[CORRECTED]** "exists only in" is wrong: production's
   `/root/coc-stats/personal_apps/artifacts/judge/v1/` holds the same three
   files, byte-identical (`e97bcb96... / 20643390... / fb20c709...`, both sides,
   verified). The worktree copy is a backup of it, not the original. Copying it
   somewhere durable is still worth doing — `git clean -xdf` on the worktree
   would leave production as the single copy — but the situation is not "one
   directory away from unrecoverable".

4. **[NEW - this is the finding that blocks Phase 2.] Base cannot be packaged
   today.** The checkpoint
   `radar_labels/encoder/model-train17090-20260907-192428/config.json:32`
   records `"max_len": 512`. Deployed `package_encoder_artifact.py:55` sets
   `MAX_LEN = 256` and `:122-124` rejects the checkpoint outright; deployed
   `judge_backends.py:163` / `:279-282` would reject a 512-token artifact even
   if one existed. `radar_labels/artifact-base/` does not exist — nothing was
   ever packaged. Plan Revision 1 §0.3 called the checkpoint "packageable"; it
   is not. The export also bakes the sequence length into the ONNX graph
   (`:174-175` makes **only** the batch axis dynamic), so the number has to
   agree in three places at once.

   **[RESOLVED 2026-09-08 — no retraining.]** More labelled data is coming and
   the GPU time is not being spent twice, so the path is: ship the existing
   base@512 weights and widen the window check. Two files: an allowed set
   `ENCODER_ALLOWED_MAX_LENS = (256, 512)` at `judge_backends.py:279-282`, and a
   `MAX_LEN` derived from the training config in the packager instead of the
   hardcoded 256. The runtime already reads the window off the artifact
   (`judge_backends.py:218`), so this keeps **both** artifacts valid and the
   `active.json` rollback to v1@256 alive. Two earlier objections do not hold:
   throughput is at ~2.4% of capacity (57 rows/hour against 57,600/day), and the
   rollback breakage is one comparison, not a redesign. The one open item is a
   **measurement** — peak RSS for a 12-layer model at sequence 512 on the 8 GB
   box beside MariaDB's 2500M buffer pool. If it does not fit, the fallback is
   exporting the same weights at a 256 window, which also needs no GPU. Do
   **not** relabel the checkpoint config. Revision 2 §1.2 carries the detail.

**Shape of the recommendation:** the trial is retired in CODE, not by data.
Nothing writes to `radar_mentions`, `radar_mention_events` or `radar_buckets`.
The trial row stays in the database, `running`, untouched, retention pin
intact, and `recover_trial` stays available to an operator who later chooses
it. Every step reverses with a `git revert`, a `systemctl enable`, or a `mv`.

**[CORRECTED] — the last sentence is the dangerous one.** Two of those three
"reversals" are not reversals:

- **`git revert` of Phase 1 after the deadline IS the destruction.** The
  deadline is a stored `first_judged_at + 3d`; once past, reverted code drains
  1,546 judgments on the deploy's own `systemctl start radar_ingest`, before
  the timer is ever unmasked. Model rollback (flip `active.json`) and
  restoring destructive trial behaviour are separate operations and must be
  written separately (Revision 2 §4).
- **`mv -f active.json.v1.bak active.json` consumes the backup** — the model
  rollback works exactly once. Revision 2 §3d replaces it with two immutable
  named pointer files and `cp`, so the switch is idempotent in both
  directions.

Also corrected: the plan's retention-pin option "(b) `DELETE FROM
radar_judge_trial` is safe after Phase 1" is **false**. Hunk C removes the
artifact-hash gate; nothing removes the row gate at `judge_trial.py:679-682`,
which still becomes `ConfigError` at `judge_config.py:178` and a dead ingest
daemon at `run_radar_ingest.py:1275`.

**Not executed.** It adds a retirement switch to a production safety mechanism,
which is exactly the kind of change that should be read by someone who did not
write it. Do not execute anything until you have verified its claims against
the code yourself.

## 9. What to verify, concretely

1. Every file:line citation in §8 actually says what it is claimed to say.
2. That the recommended path does NOT trigger `recover_trial(apply=True)` on
   any branch, including the watchdog's next tick.
3. That the deadline watchdog cannot fire mid-plan and undo the work.
4. That the base artifact swap passes `EncoderBackend._validate()` and that
   nothing checks hidden size / head count in a way a 2x model would break.
5. That a rollback to the small artifact exists and is one command.
6. That `source_config_version` is unchanged by the whole plan (it must be:
   none of this is an extraction change).
7. Whether the 44 wrongly-removed mentions in the audit sample show a pattern
   (one ticker, one source, one text length) that a cheap rule could fix.

**[CORRECTED] — status of that list after the 2026-09-07 review:**

| # | outcome |
|---|---|
| 1 | **Failed.** Citations into `judge_trial.py` above line 600 are off by up to 14 lines and the plan's own hunks quoted the wrong ones. Everything else (`judge_config`, `judge_backends`, `trial_audit`, `retention`, `spend`, `audit_encoder_trial`, `rollback_encoder_judge`, `manage_encoder_trial`, `llm_sentiment`, `run_radar_ingest`) re-read and correct, except `judge_config.py:173-178` in §5 above. |
| 2 | **Holds, once the hunks are moved to the right lines.** Hunk A makes `tick`'s expiry branch unreachable and Hunk B blocks the `RECOVERING` branch, which between them are the only `recover_trial(apply=True)` calls inside `tick`. |
| 3 | **Not fully.** Masking the timer plus the code change covers it; the timer alone does not, because of `Restart=always` on `radar_ingest` (§8 finding 2). |
| 4 | **Cannot be checked yet — no base artifact exists** (§8 finding 4). Confirmed separately that `_validate` inspects `active.json` id, the three files, `max_len` and the head names/order only: hidden size, layer count and vocabulary are never checked, and `MultiHead` reads `hidden_size` off the backbone (`train_encoder.py:201-205`), so a 2x model loads happily. The unchecked contract is the ONNX **output names**, zipped positionally at `judge_backends.py:346`/`:376-377` and indexed by field at `:381`, outside the `try` — a mismatch is a bare `KeyError` that kills every pass silently. Assert them in the staging smoke test. |
| 5 | **Conditionally.** One command only after §3d's pointer files exist, and only while `TRIAL_RETIRED` is true and `ENCODER_MAX_LEN` still matches v1's 256. |
| 6 | **Confirmed.** `config.py:832-874` hashes sources, token/stopword tables, patterns, the reddit fetcher, and the extraction/rollup generations — nothing about the trial, the switch, the artifact or the model's dimensions. Latest stored bucket still carries `3f96922d51fe4ef0`. Keep extraction work out of this change and the stamp cannot move. |
| 7 | Still open, still wanted or not per §6.7 of the plan. It needs the frozen artifact. |

**New, and not on the original list:** the trial has judged **1,546** mentions,
which is under the watchdog's `--limit 2000`, so any single tick on an expired
or `RECOVERING` row destroys the whole trial in one firing and releases the
retention pin. Verify that count before and after every step.

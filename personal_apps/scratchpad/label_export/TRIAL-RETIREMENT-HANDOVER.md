# Handover: retiring the encoder trial and deploying base

**For an independent verifier (Codex).** Written 2026-09-07 ~23:00 CEST by the
session that ran the day-1 audit. Verify against the boxes and the code before
anything is executed; where this document and the evidence disagree, the
evidence wins and the discrepancy gets recorded here.

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
Deadline **2026-09-09 19:38 UTC**. At that moment, with no passing audit, the
watchdog stops it and recovers — i.e. UNDOES its judgments.

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

## 5. THE TRAP — why this is not just `stop`

`stop` sets the trial status to RECOVERING, and the watchdog then runs
`recover_trial(apply=True)`, which is **designed to undo the encoder's
judgments**. That is the same outcome as letting the deadline pass. So the
obvious way to "abandon the trial" produces exactly the thing we are trying to
avoid: the junk comes back.

Also blocking: `judge_config.py:173-178` refuses to start the encoder when the
deployed artifact's `bundle_sha256()` differs from the armed trial's
`artifact_sha256` — "replacing a file is a different trial". So base cannot be
deployed while this trial is armed.

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

**PENDING** — the workflow (`retire-encoder-trial`, run
`wf_6ecda851-1a5`) was still running when this document was written. Its output
will be appended here as §8 with the exact ordered command sequence, the paths
that look attractive but destroy data, and the questions that need Michi rather
than a technical answer.

Do not execute anything until that section exists and you have verified its
claims against the code yourself.

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

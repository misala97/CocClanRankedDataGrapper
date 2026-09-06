# Review brief for Codex — radar local judge, session of 2026-09-05

Please review two things before Michi deploys:

1. **`3a0a335` on `main`** — a memory fix in the radar scoring pass. This is
   the only code change; it is already merged and pushed, not yet deployed.
2. **The encoder work** — a distilled classifier trained to replace the dead
   Claude API judge. No production code yet; the question is whether the
   method and the numbers are sound enough to build on.

Everything measured is stated with its measurement. Where something is a
guess, it says so. Push back hard on the parts marked OPEN QUESTION.

---

## 0. Why any of this happened

The Anthropic credit balance ran out on 2026-09-03. Since then every judge
batch fails with `Your credit balance is too low`, so `radar_mentions` get no
`relevance` / `content_origin` / `attitude` at all and the board falls back to
the hand lexicon. Nothing is removing junk from the counts.

Michi's constraint: no per-token metering, no credit cliff, no rate limit.
That ruled out topping up Haiku, hosted open-weight APIs (IONOS AI Model Hub
et al.), and `claude -p` on the subscription. A CPU-hosted LLM on a second
EUR 10 VPS was measured and rejected: Qwen3.5 4B/9B reach only 0.4-0.5
precision on the removal fields versus Haiku, and a 4-vCPU box does ~3k
mentions/day against 13k demand. Full research and numbers:
`memory/project_radar_local_judge_research.md`.

What survived: distil a small encoder from Claude labels, run it free and
unlimited on the VPS.

---

## 1. The code change to review: `3a0a335`

`personal_apps/features/radar/scoring.py`, 49 insertions, 15 deletions.

**Problem.** `_rows_by_ticker` hydrated ~128k `radar_bucket_sources` rows per
source as mapped instances, 36 sources per pass, and `score_source` wrote
through the unit of work. Measured on the VPS: `run_radar_ingest.py` at
1.48 GB resident, 1.69 GB peak, on a 3.8 GB box with **no swap** and 200 MB
free. Python keeps the high-water mark, so the process sits at its worst pass
forever.

**Change.**
- `_rows_by_ticker` selects the nine columns the loop reads via
  `sa.select(...)` — Core tuples, no identity map, no change tracking.
- `score_source` collects `pending` as dicts and issues one executemany
  `UPDATE` keyed on `(source, ticker, bucket_start)`.
- The statement targets `RadarBucketSource.__table__`, **not** the mapped
  class. Two failures got us here, both worth knowing: with the mapped class
  SQLAlchemy first demanded `synchronize_session=None` ("bulk synchronize of
  persistent objects not supported ... with additional WHERE criteria"), then
  read it as an ORM bulk-update-by-primary-key and demanded attribute keys
  instead of the bindparams. The Core table sidesteps both.

**Invariants I believe are preserved — please check these specifically:**
- return value is still rows WRITTEN, not scored (nine `written ==`
  assertions depend on it);
- `_worth_writing` still compares against the STORED value, so drift cannot
  accumulate past tolerance;
- the arithmetic still happens with no lock held; only the flush takes
  `buckets.BUCKET_WRITE_LOCK`; the `invalidate_incompatible_scores` UPDATE
  still commits separately (that separation exists to stop a deadlock with
  the cycles' `roll_up`, fixed in `50abbcb`);
- `_rows_by_ticker`'s `source_config_version` filter still fences
  old-generation rows out of the ticker loop.

**Tests:** `tests/test_radar_scoring.py` 44 passed; the whole radar suite
1,321 passed, 686 deselected, in 11 minutes, against the real dev database.

**Not verified:** the actual memory saving. It is an inference from what the
ORM costs per row, not a measurement. The check after deploy is
`grep -E "VmRSS|VmHWM" /proc/$(pgrep -f run_radar_ingest.py)/status`, read an
hour in (a fresh daemon is small regardless of this change). Expectation is
~0.7 GB against 1.48 GB, and I would like that number challenged if it looks
optimistic to you.

**OPEN QUESTION:** the write path is now the only place that touches these
rows as data rather than objects. Is there anything downstream that relied on
the ORM session holding those instances after `score_source` returned? I found
nothing, but I am the one who wrote the change.

---

## 2. The encoder work (no production code yet)

### 2.1 What was built

- `personal_apps/scratchpad/label_export/` (untracked, dev-machine only):
  - `export_label_set.py` — read-only stratified export from prod
  - `label_harness.py` — render / collect / status / compare
  - `select_rows.py` — uncertainty sampling for the next wave
  - `freeze_test_sets.py` — freezes the evaluation sets
  - `train_encoder.py`, `export_onnx.py`
- Data lives outside the repo in `C:\Users\michi\Desktop\radar_labels\`.
- Training venv: `C:\Users\michi\Desktop\radar_encoder_venv`.

### 2.2 Labels

50,000 mentions exported from prod (stratified over source, length, ticker,
day; 30-day retention meant this was time-critical). 10,200 of them labelled
by **Claude Sonnet 5** running as Claude Code subagents, using the **exact
production prompt bytes and schema** (`llm_sentiment._prompt_v2`, `V2_SCHEMA`)
and the same canonical input path (`sentiment_input.prepare_sentiment_input`).
Every verdict passed prod's own enum validation; 10,200/10,200 valid, nothing
defaulted, nothing re-queued.

Text over 2,000 chars is truncated and flagged, because the student reads at
most 512 tokens; labelling beyond its window is waste.

**Why Sonnet and not the stored Haiku labels:** on 3,553 rows judged by both,
Haiku agrees with Sonnet 78.6% on relevance and 71.2% on origin, and Haiku's
own removal precision against Sonnet is 0.875. Prior blind-audit work put
Haiku at 63% versus human labels and Sonnet-5-low at 79%. Training on the
weaker teacher would cap the student at the weaker teacher.

### 2.3 A methodology bug Michi caught, and the fix

The first two training runs recomputed the train/test split from whatever was
labelled at the time, so the test set moved every wave and the curve was not
comparable across runs. He called it out. Fixed by freezing two sets **by
mention id**, on disk, never trained on, with any row sharing a post with a
locked row excluded from training:

- `test-natural.json` — 900 rows over 883 posts, drawn only from the
  proportionally-sampled strata, so its numbers mean "behaviour on board
  traffic";
- `test-hard.json` — 500 rows over 454 posts, rare strata, diagnostic for the
  starved classes. Zero overlap.

This matters because the labelled pool is deliberately junk-heavy (2,600 rows
of one wave were selected as hard cases), so a split drawn from the pool would
flatter the removal numbers.

### 2.4 Results (locked sets, agreement with Sonnet)

Board traffic, 900 locked rows:

| train rows | relevance | origin | attitude | move | removal precision |
|---|---|---|---|---|---|
| 3,000 | 0.817 | 0.928 | 0.652 | 0.721 | 0.850 |
| 5,000 | 0.846 | 0.936 | 0.694 | 0.754 | 0.894 |
| 8,600 | 0.848 | 0.944 | 0.729 | 0.781 | 0.861 |

Hard cases, 500 locked rows:

| train rows | relevance | origin | attitude | move | removal precision |
|---|---|---|---|---|---|
| 3,000 | 0.686 | 0.828 | 0.660 | 0.680 | 0.941 |
| 5,000 | 0.776 | 0.880 | 0.714 | 0.700 | 0.962 |
| 8,600 | 0.862 | 0.942 | 0.734 | 0.754 | 0.952 |

Against Haiku on the same hard rows (490 of the 500 carry Haiku labels):
relevance 0.862 vs 0.786, origin 0.942 vs 0.712, removal precision 0.952 vs
0.875 — the encoder wins three of four. Haiku still leads attitude
(0.769 vs 0.734) and expected move.

Against the lexicon that is live right now, on the 900 natural rows: the
lexicon fires on 30% of posts, and of those 154 of 270 are posts with no
opinion at all; it catches 78 of 322 real opinions (24%) and gets 38 of 116
directional calls backwards. It produces no relevance and no content_origin,
so it cannot remove junk at all.

Model: DeBERTa-v3-small, one shared encoder, five heads, input
`<ticker> [SEP] <post>`, 6 epochs, lr 2e-5, ~5 min on an RTX 3080.

**Two traps hit and fixed, worth knowing if you touch the trainer:** bf16
autocast makes DeBERTa-v3 diverge to `loss nan` while still printing a full
report (the trainer now aborts on non-finite loss), and transformers 5 loads
the base model in fp16, which silently mismatches fp32 heads.

### 2.5 Deployment measurement

ONNX export, benchmarked at 4 threads to imitate the VPS:

| build | rows/s | relevance | origin | attitude | removal P | size |
|---|---|---|---|---|---|---|
| fp32 | 4.5 | 0.848 | 0.944 | 0.729 | 0.861 | 566 MB |
| INT8 dynamic | 8.6 | 0.692 | 0.918 | 0.696 | 0.750 | 172 MB |

Speed is a non-issue either way: demand is 0.15 rows/s average, 0.67 at peak.

**INT8 dynamic quantization breaks this model** — 16 points of relevance and
removal precision from 0.86 to 0.75, far past the "<1 point" the plan allows.
My reading is DeBERTa's disentangled attention has activation ranges a single
scale cannot cover. Untested alternatives: quantize only the feed-forward
layers, or static quantization with calibration. **I would value your opinion
here** — it decides whether the artifact is 566 MB or 172 MB, which in turn
decides whether Michi has to migrate to a bigger VPS (IONOS cannot resize in
place).

---

## 3. What is NOT done

- No production code for the encoder. The `JudgeBackend` seam described in
  the roadmap is unwritten.
- Two known traps in `llm_sentiment.py` if a backend swap ever happens:
  `apply_judgments` (~line 430) and `review_candidates` (~line 537) use the
  **model id as a stage proxy**, which breaks the moment ids change or
  coincide. And `Posts.tsx` renders the literal string "Claude".
- `spend.MODEL_RATES['claude-sonnet-5']` is stale at $3/$15; list is $2/$10.
  No Sonnet spend booked, so nothing is mis-billed today.
- The spec (`2026-08-31-radar-sentiment-v2-final-design.md`) §13 says "No
  local generative LLM in v2" and §10.1 requires a locked reference set that
  does not exist on disk. An encoder judge is a v2.1 amendment, and it has not
  been written.

---

## 4. Specific things I would like challenged

1. Is `3a0a335` safe to deploy as it stands? Especially the lock discipline
   and the executemany against the Core table.
2. Is the frozen-set methodology actually sound now, or is there still a leak
   I have not seen? Note the trainer excludes rows sharing a post with a
   locked row, but I have not verified that the near-duplicate rule used
   elsewhere in `train_radar_sentiment.py` (simhash Hamming <= 3) is applied
   here — **it is not**, and I think that is a real gap.
3. Are the removal-precision numbers meaningful given the labelled pool is
   junk-heavy by construction? The natural set exists to answer this, but the
   sampling that fed it was itself quota-based, not random over live traffic.
4. Is training a student on Sonnet labels, then measuring the student against
   Sonnet labels, circular in a way that matters? Every number above is
   agreement with the teacher, not with truth. Nobody has hand-checked a row.
5. Anything about the ONNX/INT8 result that suggests I measured it wrong
   rather than that quantization genuinely broke the model.

## 5. Where to look

- Roadmap and ledger: `docs/superpowers/specs/2026-09-05-radar-local-judge-roadmap.md`
- Research and rejected options: `memory/project_radar_local_judge_research.md`
- Code change: `git show 3a0a335`
- Scripts: `personal_apps/scratchpad/label_export/` (untracked)
- Data and models: `C:\Users\michi\Desktop\radar_labels\`

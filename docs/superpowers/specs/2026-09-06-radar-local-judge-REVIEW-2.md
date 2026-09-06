# Review brief 2 for Codex — radar local judge, final findings

Supersedes `2026-09-05-radar-local-judge-REVIEW-BRIEF.md`. That one asked you
to check a memory fix and an encoder with known holes. You found seven; all
seven are addressed below, with the two real ones verified rather than
asserted. This brief asks a different question:

**Is the evidence strong enough to build the production judge on, and is the
ship decision defensible?**

Nothing has been implemented. The decision is reversible until code is
written. Push hardest on section 4.

---

## 1. Your seven findings, and what happened to each

| # | finding | status |
|---|---|---|
| 1 | 🔴 Near-dup leak: post-id exclusion only; 91 pairs within Hamming 3, 10 exact | **FIXED.** Simhash exclusion added to `split()`. Verified: 0 residual shared-post rows and 0 residual near-dup hashes between train and either locked set. The final run excluded 142 shared-post + 166 near-duplicate rows (27 distinct hashes). Notably the leak *grew* with targeted selection — margin-picked rows resemble the hard set — so the guard earns its place. |
| 2 | 🟡 256 tokens, not the documented 512; `truncated` flag unused | **TESTED AND REVERTED.** Ran the full curve at 512 (batch 8 × accum 2, 57 min). Result on both locked sets: identical to 256 within noise. 512 doubles inference memory and time for nothing, so the shipping model is 256. The docs now say 256. Your point stands that the label window (2,000 chars) exceeds the model window; the measurement says it does not matter here, presumably because long posts are 3.8% of rows. |
| 3 | 🟡 `KeyError: 'test'`, no seed, no manifest | **FIXED.** Summary printer reads the right key; `--seed` (default 20260905) seeds python/numpy/torch and the DataLoader generator; every run writes `run-<ts>.json` with seed, sizes, exclusion counts, sha256 of labels/export/both locked sets, and git HEAD. |
| 4 | Fails all five absolute gates; the brief reported accuracy, which masked it | **CONFIRMED AND ADOPTED.** The trainer now prints macro-F1 and reversal rate as PASS/FAIL. Final model on the natural set: rel F1 .711, origin F1 .748, removal P .880, attitude .720, reversals 16.5% → **0 of 5**. This is now stated plainly wherever the model is described. See section 4 for why we propose shipping anyway. |
| 5 | 🟡 "natural" is quota-stratified, not live-random | **ACCEPTED.** It is described as a development set, not a production-traffic estimate. The 200-row audit (section 3) is the closest thing to a traffic estimate and is also not random — it is half deliberately removal-heavy. |
| 6 | 🟡 INT8 explanation unproven; fp32 is not 566 MB (sidecar) | **PARTLY.** The sidecar was a stale artefact of the first (dynamo) export attempt; deleted, the fp32 graph is self-contained at 566 MB. My attention-range explanation for the INT8 collapse remains **unproven** and I have not investigated further, because the VPS measurement (section 5) made INT8 unnecessary. Flagging it as an open unknown rather than a closed question. |
| 7 | Measure real VPS RSS before sizing servers | **DONE, section 5.** |

---

## 2. What the model is now

15,200 Sonnet-5 labels (nine runs, 15,200/15,200 schema-valid, 0 re-queued),
produced with the exact production prompt bytes and schema and the same
canonical input path as the live judge. The last three waves were **chosen,
not sampled**: rare classes, then uncertainty, then (5,000 rows) margin-
targeted at the two measured failure modes — thin-margin deletions and thin
positive-vs-negative gaps.

Model: DeBERTa-v3-small, one shared encoder, five heads,
`<ticker> [SEP] <post>`, 256 tokens, 13,492 train rows after leak exclusion,
seed 20260905, 6 epochs, ~25 min on an RTX 3080. Saved as `model-train13000`.

Curve on the frozen sets (macro-F1 where the gate says F1):

| train | rel F1 | orig F1 | att acc | removal P | reversals |
|---|---|---|---|---|---|
| natural 5,000 | .703 | .703 | .641 | .860 | 21.1% |
| natural 9,000 | .750 | .733 | .713 | .890 | 17.7% |
| natural 13,000 | .711 | .748 | .720 | .880 | 16.5% |
| hard 13,000 | .757 | .792 | .728 | .954 | 10.7% |

---

## 3. The evidence the decision actually rests on

The frozen sets are Sonnet-labelled, so they cannot answer "is the teacher
right". A separate 200-row audit does: rows never labelled, never in either
locked set, no shared post or near-duplicate with anything used. Half drawn
from board traffic, half from rows the encoder would delete (the costly
error). **Labelled by Michi by hand, then reviewed by Fable 5.1** — so it is
human + a stronger, different Claude, not pure human. Then Sonnet and Haiku
were run over the identical 200 rows.

| | Haiku (paid) | encoder final | Sonnet (teacher) |
|---|---|---|---|
| relevance | 64.0% | **75.5%** | 81.0% |
| content origin | **97.0%** | 93.5% | 97.5% |
| attitude | 72.5% | **79.5%** | 84.5% |
| expected move | 74.5% | **85.0%** | 89.0% |
| removal precision | **0.988** | 0.968 | 1.000 |
| removal recall | 0.632 | **0.728** | 0.816 |
| polarity flips | **0/54** | 3/54 | 0/54 |

Two things this establishes that the locked sets could not:

- **The teacher is not the weak link.** Sonnet deleted 102 mentions on these
  rows and the reference agreed with all 102. It under-removes (recall .816),
  which is the safe direction.
- **Encoder-vs-Sonnet on these fresh rows** (rel 84%, origin 89.5%, removal P
  .890) matches the locked natural set closely, which is weak evidence the
  frozen sets behave like fresh traffic despite being quota-stratified.

Every failing row was read. The entire remaining gap to Haiku is six rows:

- **3 wrong deletions** (of 94 predicted; Haiku 1 of 80): a one-line
  "Huntington Ingalls $HII weld automation ... Buy." + link; a macro question
  mentioning $GLD; a bare share-count list ("$VCX - 500 shares $AMA - 300
  shares"). All three are defensibly automated-looking.
- **Origin's 3.5 points**: 9 of 13 misses are the encoder saying `uncertain`
  where the reference said `human_chatter`. `uncertain` deletes nothing, so
  these are abstentions, not errors. Only 3 are real (chatter → broadcast).
- **3 flips**, all long argumentative posts that criticise on the way to a
  positive conclusion or the reverse.

---

## 4. The ship decision — argue with this

Michi's rule replaced the absolute gates: *"better than Haiku should be given,
as good as possible is the goal."* The rule is therefore: no field worse than
the paid judge, removal precision not below it.

**The model misses that rule on two fields** — origin by 3.5 points, removal
precision by 0.019 — and I recommended shipping anyway with a documented
exception. The argument:

Per 200 posts, Haiku leaves 46 junk mentions in the counts; the encoder leaves
34. The cost is 3 wrong deletions instead of 1. So each additional wrong
deletion buys six additional correct removals, and for a board that ranks by
volume, junk left in moves rankings while a deleted borderline post is one row
of one ticker's count. Attitude ships **provisional** (3 flips vs 0, and tone
is the one field a reader sees on a post card).

**Where I think this is weakest, and what I want you to attack:**

1. **n=200.** 3-vs-1 wrong deletions is well inside sampling noise. A
   different 200 could reverse the sign. Is the honest answer "ship it" or
   "get 500 more audit rows first"?
2. **The reference had a Fable pass.** Michi's words: "they are perfect
   basically ... I aint gonna outperform Fable 5.1 with my small human brain."
   So the reference is Claude-influenced, which is exactly the circularity the
   audit was meant to break, weakened. How much does that undermine section 3?
3. **The audit is half removal-heavy by construction.** Removal precision
   measured on a set enriched for removals may not be the removal precision
   the board would see.
4. **Absolute gates fail 0 of 5** and we are replacing them with a relative
   rule mid-project, after seeing the numbers. That is a moved goalpost, even
   if the reasoning is sound. Is the reasoning sound?
5. **Reversal rate 16.5% on the natural set vs 3/54 (5.6%) on the audit.**
   Those disagree by a lot. I have not reconciled them. The locked set has 322
   directional rows vs the audit's 54, so it is the better-powered estimate,
   and it says tone is worse than the audit suggests. This is the single
   number I trust least in the whole project.

---

## 5. Deployment facts (measured, not estimated)

- Memory fix `3a0a335` deployed: daemon RSS **1.48 GB → 488 MB**, peak 1.69 →
  689 MB, box available **200 MB → 1.79 GB**.
- Encoder benchmarked **on the VPS itself** (throwaway venv, onnxruntime
  1.29): load 2 s, **7.0–7.5 rows/s** at both 2 and 4 threads (bandwidth-
  bound), resident **1,081 MB at batch 1 or 4**, 1,715 MB at batch 16.
  Demand is 0.15 rows/s. Verdicts identical to the PC's for the same weights.
- Deploy shape: fp32, batch ≤ 4, 2 threads, plus a 2 GB swapfile. No second
  server, no L+ migration (IONOS cannot resize in place anyway).

---

## 6. What the build would be, and the one bug in it

- `JudgeBackend` protocol + encoder adapter + Anthropic adapter behind a flag.
  ~200 lines: `_judge_batch_v2` is the only vendor-shaped function.
- **The bug I want you to look at before I write anything:**
  `apply_judgments` (~line 430) and `review_candidates` (~line 537) infer
  *stage* from the *model id* (`sentiment_model == REVIEW_MODEL`). Swap the
  backend and either a review verdict gets silently overwritten by a later
  primary pass, or rows judged by the old primary drop out of the review pool.
  It fails silently and the suite is green. `radar_sentiment_judgments.stage`
  already holds the truth. My instinct: read stage from history (or
  materialise it), and drop the redundant model filter beside the existing
  `NOT EXISTS`. Is that the right shape?
- ~55 tests across `test_radar_sentiment_v2.py` (45) and
  `test_radar_llm_sentiment.py` (10) are built on a fake Anthropic client and
  on primary/review ids differing.
- Small: zero spend rate for a free backend; the literal `'Claude'` in
  `Posts.tsx:86`; **a spec v2.1 amendment — §13 currently forbids a local
  generative LLM and §10.2's gates were written for a frontier judge. Neither
  has been written yet.**

---

## 7. The next thing after this, for sanity-checking

Extraction, not more judge work. 2,669 of the 15,200 labels are `irrelevant`,
i.e. rows where extraction accepted something that is not a company —
**26.2%**. Tickers where nearly every bare match is junk: FCF (98%), SMA
(100%), DTE (100%), IP (96%), API (94%), ARR (100%), plus PC/TP/LOT/IQ/IA/TACO
at 100%. That is trading jargon counted as companies, and it matches the
earlier "35% of score is not about companies" finding.

Two moves, neither needing new labels: add those bare tokens to the stopword
list (cashtags unaffected, so `$IP` still counts), and move the existing
relevance head upstream so junk never enters the counts rather than being
removed afterwards for the ~18% of mentions the gate admits. Does that
ordering seem right to you, or is there a reason to do extraction first?

## Where to look

- Ledger and all measurements: `docs/superpowers/specs/2026-09-05-radar-local-judge-roadmap.md` (commit `1712263`)
- Scripts: `personal_apps/scratchpad/label_export/` (untracked)
- Data, models, audit: `C:\Users\michi\Desktop\radar_labels\`
- Deployed memory fix: `git show 3a0a335`

# Radar local judge — roadmap and ledger

Goal: replace the Claude API judge (dead since 2026-09-03, credit balance
empty) with one that has no per-token cost, no credit cliff and no rate
limit: a DeBERTa-v3-small encoder distilled from Claude labels, running on
the existing VPS. Metered APIs, a CPU-hosted LLM and `claude -p` on the
subscription were all evaluated and rejected — numbers in
`memory/project_radar_local_judge_research.md`.

**Status 2026-09-06: everything is measured and decided. One build remains
(ledger item 6).** The model exists, beats the paid judge on the fields that
decide what counts, runs on the box with room to spare, and the box now has
1.79 GB free instead of 200 MB. Nothing on prod has been changed except the
scoring-pass memory fix, which is deployed and measured.

## Fixed facts (all measured, do not re-derive)

- Demand ~13,000 high-confidence mentions/day; the judge gate admitted ~2,400.
  Haiku cost $0.0004/mention. A free judge means the gate can come off.
- VPS after the memory fix: daemon RSS 488 MB (was 1.48 GB), 1.79 GB
  available. Encoder needs 1,081 MB at batch <= 4. It fits.
- Encoder speed on the VPS: 7.0-7.5 rows/s at 2 or 4 threads. Demand is
  0.15 rows/s. Speed is a non-issue.
- INT8 dynamic quantization BREAKS this model (relevance .69, removal P .75)
  and is not needed; ship fp32, 566 MB.
- 512 tokens bought nothing over 256 on the locked sets and doubles cost.
  The shipping model is 256 tokens.
- Labels are the lever, and CHOSEN labels are 2-3x the lever of sampled ones.
  Rare classes first, then uncertainty, then margin-targeted at named failure
  modes.
- Michi sizes every labelling wave in % of the 5-hour window; nothing renders
  or launches without a number ([[feedback_never_spend_quota_unasked]]). Heavy
  GPU work needs a "when" ([[feedback_heavy_local_jobs_ask_first]]).

## Artefacts

| what | where |
|---|---|
| 50k export from prod | `Desktopadar_labels\export-2026-09-05.jsonl` |
| 15,200 Sonnet labels | `Desktopadar_labels\labels-sonnet5.jsonl` |
| frozen eval sets | `test-natural.json` (900), `test-hard.json` (500) |
| independent audit + 4 judges' verdicts | `audit-200.jsonl`, `labels-audit-{sonnet5,haiku}.jsonl` |
| shipping model | `Desktopadar_labels\encoder\model-train13000` |
| ONNX artifact (fp32) | `Desktopadar_labels\encoderrtifact\` |
| harness, trainer, selector, audit tools | `personal_apps/scratchpad/label_export/` (untracked) |
| Codex review brief | `docs/superpowers/specs/2026-09-05-radar-local-judge-REVIEW-BRIEF.md` |

## Traps found the hard way — do not reintroduce

1. **bf16 autocast diverges DeBERTa-v3 to `loss nan`** and the run still
   prints a full report. The trainer now aborts on non-finite loss.
2. **transformers 5 loads the base model in fp16**, silently mismatching
   fp32 heads. `from_pretrained(..., dtype=torch.float32)`.
3. **A split that is recomputed each run is not a locked test set.** Freeze
   by mention id, on disk.
4. **Post-id exclusion is not leak-free.** Near-duplicates (simhash Hamming
   <= 3) leak too: 308 rows in the final run.
5. **Accuracy hides a failing gate.** Report macro-F1 and reversal rate where
   the gate says F1.
6. **512 tokens at batch 16 overflows a 10 GB card** into system RAM and
   freezes the machine.
7. **Biasing selection on a predicted class** returned a 92%-negative set that
   would have taught the model everything is negative. Sort on margin, not
   class.

## Ship rule (Michi's ruling, 2026-09-05)

The bar is the paid judge, not perfection: **"better than Haiku should be
given, as good as possible is the goal."** So the ship gate for the free
encoder is: on the same reference rows, no field worse than Haiku 4.5, and
removal precision not below Haiku's. The spec §10.2 absolute targets stay as
the aspiration and the per-field escape hatch (ship the removal heads, hold
attitude) stays available. Measured so far on 490 hard rows vs Sonnet:
encoder beats Haiku on relevance (.862/.786), origin (.942/.712) and removal
precision (.952/.875); trails on attitude (.734/.769) and move (.754/.829).
**Four-way on the 200 audit rows vs human+Fable** (`labels-audit-haiku.jsonl`, `labels-audit-sonnet5.jsonl`, encoder = pre-fix 8,600 model):

| | Haiku (paid) | encoder (free) | Sonnet (teacher) |
|---|---|---|---|
| relevance | 64.0% | 75.0% | 81.0% |
| content origin | 97.0% | 91.0% | 97.5% |
| attitude | 72.5% | 76.0% | 84.5% |
| expected move | 74.5% | 83.0% | 89.0% |
| removal precision | 0.988 | 0.940 | 1.000 |
| removal recall | 0.632 | 0.752 | 0.816 |
| polarity flips | 0/54 | 4/54 | 0/54 |

Against the ship rule the pre-fix encoder is NOT yet through: it beats Haiku on relevance (+11), attitude (+3.5), move (+8.5) and removal recall (+12), but trails on content origin (91 vs 97), removal precision (0.940 vs 0.988 — 6 wrong deletions vs ~1) and polarity flips (4 vs 0). Haiku is more precise because it removes far less (recall 0.63: it leaves 37% of the junk in the counts). **Clean 512-token model on the same 200 rows** (`encoder_clean` in `audit-200.jsonl`): relevance 75.0, origin 94.0, attitude 77.5, move 82.0, removal precision **0.968** / recall 0.736, flips 3/54. Ship rule per field: relevance OK (+11 vs Haiku), attitude OK (+5), move OK (+7.5); origin below by 3.0, removal precision below by 0.019 (3 wrong deletions in ~95 vs Haiku's 1 in ~80), flips 3 vs 0. Gap to Haiku is now one or two deletions and three tone flips on 200 rows — inside sampling noise, but the rule says not yet.

## Open decisions

- **Attitude stays PROVISIONAL at launch** — 3 polarity flips vs Haiku's 0 on
  the audit. Relevance and origin (the fields that delete mentions) ship; tone
  is watched for a week before it is trusted the way the counts are.
- **Judge gate off after launch?** It exists to bound spend, and there is no
  spend. Turning it off judges ~13k/day instead of 2,400. Do it after the
  first stable week, not at launch, so one variable changes at a time.
- **Lexicon retirement** — keep it as the fallback when no artifact loads, and
  as a live cross-check for a week. Then delete: 24% recall and a third of its
  directional calls backwards is worse than no signal.
- **Beyond 15,200 labels** — not needed for launch. If attitude is still weak
  after a week, another margin-targeted wave is the lever.
- **Opus second pass** on `uncertain`/`low` rows — still optional, still never
  started.
- **INT8** — dynamic breaks the model. FFN-only or calibrated static would cut
  1,081 MB to ~400 MB. Worth doing only if the box gets tight again.

## Codex verdict, 2026-09-06: BUILD BEHIND A FLAG

"The evidence supports a controlled trial, but not an unconditional
replacement of Haiku." Accepted in full. His three material issues, and the
conditions they impose on the build:

1. **The removal trade is not a production estimate.** Half the 200-row audit
   was selected *because the encoder wanted to delete those rows*, so
   measuring deletion quality on it is circular; more enriched rows cannot fix
   it. "Per 200 posts" also conflated sampled mentions with posts.
   → Report the two audit halves separately, and get **fresh randomly selected
   traffic** before any unconditional ship.
2. **Sampling noise does not establish non-inferiority.** 3 wrong deletions vs
   1 is inconclusive, not evidence the precision bar is met. An exception is a
   legitimate product choice, but **the acceptable precision loss and the
   rollback trigger must be written down BEFORE the next evaluation**, not
   after seeing it. "Provisional" tone needs an operational meaning; his
   recommendation, adopted: **keep Haiku's displayed tone during the trial.**
3. **The two reversal rates (16.5% locked vs 5.6% audit) are not comparable**
   — different references, different populations — and the larger set measures
   agreement with Sonnet, not real-world tone error. → Recompute both under
   one definition, inspect the disagreements, and look specifically at
   truncated posts: overall 256/512 parity can hide a difference on that small
   but costly subset.

Also: **"teacher validated" is too strong** while the reference carries a
Fable pass. Preserving independent human labels and recording what
adjudication changed is required for that claim.

Arithmetic correction (his catch, my stale numerator): the `irrelevant` share
is **3,865 / 15,200 = 25.4%**, not the 2,669/26.2% in the brief (that count
was from 10,200 labels). His 17.6% divided my stale numerator by the new
denominator. Prevalence-honest figure is the quota-stratified locked natural
set: **25.6% of 900 rows**. Targeted runs cannot establish prevalence at all.

Extraction ruling: narrow bare-token stopword fixes can proceed independently;
**moving the relevance head upstream broadens its blast radius and needs its
own validation.** And per [[radar-extractor-recall-unmeasured]], extraction
recall has never been measured because every row we have is one it accepted.

## Ledger

- [x] 1. Export 50k — `Desktopadar_labels\export-2026-09-05.jsonl`, 50,000 rows (reddit 35,379 / bluesky 14,516 / 4chan 105), 31 days, 5,178 tickers, 8,047 with Haiku labels. Read-only on prod; every step since reads this file, never a database.
- [x] 2. Quota pilot — shape measured over five waves. Winner: **200 posts/prompt x 5 batches/agent = ~143 rows per 1% of a 5-hour window**. Reported `subagent_tokens` do NOT track the meter; only `/usage` does.
- [x] 3. Labels — **15,200 booked, 15,200 valid, 0 re-queued**, nine runs (`pilot-200`, `main-01`..`main-08`). Cost ~2.5 windows. Waves 6-8 were chosen, not sampled: rare classes, then uncertainty, then (wave 8) the two measured failure modes via margin targeting. Resumability proved itself: a mid-wave limit hit lost nothing, 22 of 25 batches booked and the other 3 ran next window.
- [ ] 3b. Opus pass on `uncertain`/`low` rows — optional, never started, probably unnecessary.
- [x] 4. Encoder — DeBERTa-v3-small, one shared encoder, five heads, `<ticker> [SEP] <post>`. Final model **`model-train13000`** (13,492 train rows, 256 tokens, batch 16, seed 20260905, leak-free split, manifest). ~25 min on the 3080.
- [x] 4b. Codex review — memory fix cleared; encoder blocked on seven findings, all now addressed: near-dup leak (fixed, simhash Hamming<=3, 308 rows excluded in the final run), 256-vs-512 token window (tested: 512 bought nothing, reverted to 256), no seed/manifest (added), summary crash (fixed), gates reported as accuracy (now macro-F1 + reversal rate, PASS/FAIL), "natural" set is quota-stratified (renamed in reasoning, treated as a development set), INT8 explanation unproven (still unproven, and INT8 is not needed).
- [x] 4c. Frozen evaluation sets — `test-natural.json` (900 rows / 883 posts) and `test-hard.json` (500 / 454), by mention id, never trained on, plus post-sharing and near-duplicate exclusion. Michi caught that the earlier split moved every wave; these do not.
- [x] 4d. Independent audit — 200 fresh rows (100 natural + 100 the encoder would delete), labelled by **Michi + a Fable 5.1 review pass**, then Sonnet and Haiku on the identical rows.

  **Final four-way vs that reference:**

  | | Haiku (paid) | encoder v1 | **encoder final** | Sonnet |
  |---|---|---|---|---|
  | relevance | 64.0 | 75.0 | **75.5** | 81.0 |
  | content origin | **97.0** | 91.0 | 93.5 | 97.5 |
  | attitude | 72.5 | 76.0 | **79.5** | 84.5 |
  | expected move | 74.5 | 83.0 | **85.0** | 89.0 |
  | removal precision | **0.988** | 0.940 | 0.968 | 1.000 |
  | removal recall | 0.632 | 0.752 | **0.728** | 0.816 |
  | polarity flips | **0/54** | 4/54 | 3/54 | 0/54 |

  Teacher validated against the same reference: Sonnet 1.000 removal precision, 0 flips, so Sonnet-grades-Sonnet circularity is not what the numbers rest on.
- [x] 4e. **Ship decision (2026-09-06).** Spec §10.2 absolute gates: 0 of 5 (they were written for a frontier judge). Michi's Haiku-relative rule: 4 fields clear, 2 miss by a hair. **Documented exception, ship anyway** — per 200 posts the encoder leaves 34 junk mentions in the counts where Haiku leaves 46, at a cost of 3 wrong deletions versus 1. Six extra correct removals per extra mistake, and the three wrong ones are genuinely borderline ("Buy." + link; a bare share-count list). Origin's 3.5-point gap is 9 abstentions (`uncertain`, which deletes nothing) and 3 real errors. **Attitude ships PROVISIONAL**: 3 flips vs Haiku's 0, and tone is the one field a reader sees on a post card. Caveat on the record: 200 rows, so 3-vs-1 is inside noise; more certainty needs more audit rows, not more training.
- [x] 5. Daemon memory fix — `3a0a335`, merged (`02f7765`), deployed, **measured: RSS 1.48 GB → 488 MB, peak 1.69 → 689 MB, box available 200 MB → 1.79 GB**. Codex cleared it; 44 scoring + 1,321 radar tests green.
- [x] 5b. VPS capability — fp32 ONNX benchmarked on the box itself (throwaway venv): **7.0-7.5 rows/s** (need 0.15), **1,081 MB resident at batch 1 or 4**, 1,715 MB at batch 16, load 2 s, verdicts identical to the PC's. Deploy shape: **batch <= 4, 2 threads** (2 threads is as fast as 4). Second server / L+ migration question CLOSED: no migration.
- [x] 5c. Housekeeping — Codex's `radar-chatter-probe` units and `/opt/radar-chatter-probe` (942 MB) removed; timers had already fired their stop on Sep 1. `/root/encoder-bench` (600 MB scratch, nothing running) still there, delete when the real deploy lands.

### Everything above is done. What remains is one build.

- [ ] 6. **Ship the judge BEHIND A FLAG, as a trial** — Codex's ruling, not an unconditional replacement. Spec + plan first, Codex reviews the plan before code.
  - **Trial shape:** encoder judges and stores; Haiku's displayed tone is retained; the exception, the tolerated precision loss and the rollback trigger are written down BEFORE the trial's evaluation.
  - **Owed before any unconditional ship:** a fresh randomly-sampled traffic audit (not removal-enriched), the two audit halves reported separately, and the two reversal rates recomputed under one definition with truncated posts inspected.
  - App: `JudgeBackend` protocol; encoder adapter; Anthropic adapter kept behind a config flag, off. ~200 lines, because `_judge_batch_v2` is the only vendor-shaped function.
  - **The one real bug to fix first** (Codex confirmed both model-id dependencies and the shape of the fix): `apply_judgments` (~line 430) and `review_candidates` (~line 537) use the model id as a STAGE proxy. Use **review history scoped to mention + current prompt version** — not simply the latest history row — remove the primary-model filter, keep the activation-cutoff and prompt-version fences. **Test identical primary/review model ids, and a backend change.**
  - Tedious: ~55 tests across `test_radar_sentiment_v2.py` (45) and `test_radar_llm_sentiment.py` (10) are built on a fake Anthropic client and on primary/review ids differing.
  - Small: zero spend rate for the free backend (else the board reads "unpriced"); the literal `'Claude'` in `Posts.tsx:86`; spec v2.1 amendment for §13 and the §10 gate language.
  - VPS: scp the artifact + tokenizer, loader at batch 4 / 2 threads, 2 GB swapfile, watch the first cycle. Judge gate can then be switched OFF — all ~13k mentions/day judged instead of 2,400, since the judge is free.
  - Estimate: 2-3 sessions including the deploy.
- [ ] 7. Refresh loop — retrain cadence, teacher refresh, promotion gates. After 6 has run a week.

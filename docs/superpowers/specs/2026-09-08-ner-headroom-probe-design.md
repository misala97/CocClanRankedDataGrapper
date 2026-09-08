# NER headroom probe — design

**Date:** 2026-09-08. **Branch:** `dev_personal`. **Status:** approved by Michi
("Ok go!"), building.

## The question

66.6% of captured Reddit posts (132,164 of 198,586 in the measured week)
produce no ticker candidate at all. A trained span model (NER) would search
that pool. Before building it: how many real company mentions are in there?
The only estimate so far is a zero-shot GLiNER probe over 300 posts, read by
eye: "call it 4-5%". That is a guess with error bars wider than the decision.

## The idea (Michi's)

Run the target architecture now, with GLiNER standing in for the model that
does not exist yet:

    zero-candidate post -> GLiNER finds a span -> lookup maps it to a symbol
                        -> the deployed encoder judges (symbol, text)

Nothing costs API money. The encoder is already trusted for relevance (0.93 /
0.88 / 0.90 precision on the locked sets). What comes out the end is the
prize, counted, and every relevant pair is a silver span for training the
real model on its real target population.

## Scope

**Sample of 3,000** zero-candidate posts, chosen to measure wall-clock as much
as the headroom. The full week (70,381 posts with >=40-char bodies) is the
follow-up if the number justifies it.

## Shape: two stages, two interpreters

The app (extractor, universe) lives in the main Python without torch; GLiNER
and CUDA live in `C:\Users\michi\Desktop\radar_encoder_venv` without the app.
Stage 1 writes files, stage 2 reads them. The sample is therefore a fixed
artifact any future finder can be re-run against.

### Stage 1 — `personal_apps/scripts/sample_zero_candidate_posts.py` (main Python)

- Load every raw line of the week (`radar_labels/raw/reddit/<day>/<sub>.jsonl`).
- Shuffle with a fixed seed. Uniform sample across days and subs, not the
  first 3,000 of whatever sub sorts first.
- Run the existing `measure_extractor_population.classify()` in that order;
  keep a post when `gate is None`, `accepted == []`, `rejected == []`, and the
  raw body is >= 40 chars (the probe's floor). Stop at N.
- Write `sample-<N>.jsonl` (external_id, source, kind, created_utc, title,
  body, author_text) and `lookup.json` (symbol -> name, distinctive tokens;
  plus the alias/metonym tables) so stage 2 needs no app and no DB.

### Stage 2 — `personal_apps/scratchpad/label_export/ner_probe.py` (encoder venv)

Three passes, each timed separately.

1. **Find.** GLiNER `urchade/gliner_small-v2.1` on GPU, labels
   `publicly traded company`, `company`, `stock ticker`, threshold 0.5 -- the
   probe's settings. Batched. Long posts are truncated by the model; noted,
   not worked around.
2. **Resolve.** `span_lookup.resolve(span_text)` -> (symbol, tier) or
   (None, 'unresolved'). Exact tiers, first hit wins:
   - `symbol`: the span stripped of `$`, uppercased, is a universe symbol.
   - `name`: the span normalised (lowercase, punctuation to spaces, corporate
     suffixes dropped) equals exactly one universe name normalised the same
     way.
   - `tokens`: the span's name-word tokens that appear in the distinctive
     index intersect to exactly one symbol. Same index rule as production:
     a token names at most `MAX_NAME_CLAIMANTS` (4) symbols, pooled vehicles
     and notes-due listings excluded.
   - `alias`: `NAME_ALIASES` and `METONYMS` from the population script
     (google -> GOOGL, zuck -> META).
   Unresolved spans are kept and counted. The top unresolved span texts are
   an output: they say what a real lookup would need.
   **No fuzzy matching.** Not installed anywhere, and fuzzy over 12,500
   names is how the headline number gets inflated by false resolutions.
3. **Judge.** One pair per `(post, symbol)`, deduplicated across spans. The
   deployed artifact via `ask_encoder.load/judge`, CPU, batches of 16.

### Outputs

`findings.jsonl` (one row per span, with every stage's result),
`summary.json`, `spotcheck.md` (50 random encoder-relevant pairs with text,
read by Claude before any number is reported), and the printed funnel:

    posts sampled                     3000
      with >=1 span                    n  (x%)
    spans                              n   by tier / unresolved (+ top 40)
    (post, symbol) pairs               n
      encoder relevant                 n   <- headline
      encoder kept (incl. uncertain)   n
    relevant rate per tier
    extrapolated prize/week = 132,164 x (relevant posts / 3000)
    timings: gliner / lookup / encoder

"Kept" is the board's own rule (`relevance != irrelevant` and
`content_origin != broadcast_or_automated`). "Relevant" is strict.

## Tests (first)

Pure parts only; the two model calls are glue.

- `span_lookup`: each tier resolves; ambiguity is unresolved; `fed`, `S&P`,
  `420C` are unresolved; `$nvda` and `lyft` resolve via `symbol`; suffix
  stripping (`Bank of America Corporation` == `bank of america`); the
  pooled-vehicle and notes-due exclusions hold; aliases win only when no
  exact tier does.
- `sample_zero_candidate_posts`: the predicate (gate / accepted / rejected /
  body floor); seeded order is deterministic; sampling stops at N; the
  written row carries the fields stage 2 needs.
- `ner_probe`: pair dedup across spans of one post; funnel aggregation from
  findings rows; extrapolation arithmetic.

## Cost

GLiNER small on the RTX 3080: ~2 GB VRAM, minutes. Encoder on CPU: ~10 min
for ~4,500 pairs. Michi approved the run.

## Non-goals

Fuzzy name matching; the full-week run; any change to production extraction;
training anything.

---

## Result — run 2026-09-08, 3,000 posts

Files: `C:\Users\michi\Desktop\radar_labels\ner\` (sample, lookup) and
`probe-3000\` (findings, verdicts, summary, spotcheck). Finder GLiNER
small-v2.1 on the RTX 3080; judge the **base@512 artifact production runs**.

    posts sampled                     3000
      with >=1 span                    419  (14.0%)
    spans                              527   symbol 65 / name 10 / tokens 12 / unresolved 440
    (post, symbol) pairs                78
      encoder relevant                  55   (kept 57)
    posts with a relevant pair          55   (1.83%)
    extrapolated                     1,290 relevant posts / week   (of 70,381)
    timings                          gliner 34 s (GPU)   encoder 53 s (CPU, 78 pairs)

**The extrapolation base is 70,381, not 132,164.** Stage 1 qualified 34.5% of
shuffled posts, not 66.6%: the 40-char floor removes the short comments, and
a rate measured on posts that clear it must not be scaled to the ones that do
not.

**Spot-check, all 50 read.** 9 clearly wrong, 2 borderline: ~80% precision on
"relevant". The wrong ones cluster: short generic symbols (`Na`, `V`, `MMs`,
`CSP`), index names resolving to a company (`Nasdaq` -> NDAQ, `Dow` -> DOW),
a generic phrase intersecting to one symbol (`Stablecoin infrastructure
companies` -> SDEV), a brand collision (`Oshkosh Bigosh` -> OSK). Corrected
prize: **~1,000 relevant posts a week**.

**The decisive table** — relevant / judged, by how the span resolved:

    symbol, Title-case span   35 / 38    Nvda, Avgo, Dell, Tsla, Goog, Htz, Sndk ...
    name                       8 / 10    Wendy's, Nasdaq(x), Scilex, Funko, etoro
    tokens                     7 / 10    Klaviyo, Colgate, Equinox, Endovia, SDEV(x), Oshkosh(x)
    symbol, lowercase span     1 / 11    na, hp ...
    symbol, one letter         2 /  4    L (Loews, genuinely), V(x), O
    symbol, other              2 /  5

**64% of the whole prize is one regex.** `BARE_PATTERN` is `[A-Z]{2,5}` --
all caps only -- so `Nvda`, `Avgo`, `Dell` are invisible to production AND to
the loose pass (these posts are zero-candidate: nothing caught them).
`$Duot` is invisible too: `CASHTAG_PATTERN` also demands upper case. A
Title-case candidate shape, gated by the existing ordinary-word and
name-shape instruments and judged by the encoder, recovers ~800 posts a week
without a model.

**The NER-only remainder** -- what a span model finds that no symbol shape
can -- is the `name` + `tokens` rows: 15 relevant pairs in 3,000 posts, two
of them false resolutions, **~350 posts a week**, 0.75% of counted volume.

**Unresolved (440 spans, 326 distinct, 267 once):** indices and futures
(`QQQ` x10 -- NOT in the universe, `VIX`, `SPX`, `S&P 500`, `NQ`, `KOSPI`),
jargon and memes (`WSB`, `DCA`, `ATH`, `gamma`, `shrek`, `pepetrump`),
private companies (`New Balance`, `Jane Street`, `Bloomberg`, `Axios`),
people (`Bessent`, `Warsh`, `Hock Tan`). Real misses in the tail: `Wendys`
(possessive form), `LQMT` (OTC, not in universe). A better lookup would add
little.

## Decision

Do not build the span model now. Measured NER-only headroom is ~350 posts a
week against ~8,000 real mentions a week sitting in the extractor's rejects
(prize A) and ~800 in Title-case symbols (a rule). Build those two; revisit
NER when the corpus grows or the sources change. The probe stays: any future
finder is scored against the same 3,000 posts.

Two lookup lessons for whenever the name tier ships: an index stoplist
(Nasdaq, Dow, Russell), and no `tokens`-tier resolution of multi-word
generic phrases.

## GLiNER recall check — 200 posts it flagged nothing in, read 2026-09-08

Michi's objection: an untrained zero-shot model's recall is unknown, so the
probe is a floor, not the prize. Direct check: 200 random posts from the
2,581 GLiNER-negative posts (ids in `probe-3000/miss-audit-ids.json`,
seed 20260908), read in full by Claude.

- **1 explicit miss** — #40 `puts or short on mu` (Micron, lowercase).
- **2 implicit references** no lookup could resolve — #57 "a company that
  makes yoga pants and 10 billion market cap" (Lululemon), #93 `Winzigweich`
  (mauerstrassenwetten German for Microsoft).
- Borderline, counted as no: #8 `farmmi` in a memecoin-trenches context,
  #20 "Michael Dell's wife".
- The other ~195: politics, options mechanics, jokes, links, sector words
  (`oil stocks`, `memory`), indices (`spx`, `S&P futures`), people (`Warsh`).

Miss rate 0.5% explicit, 1.5% counting the implicit two; Wilson 95% upper
bounds 2.8% and 4.3%. Over the 86% of posts GLiNER left blank that lifts the
14.0% flagged rate to at most ~16.4% (explicit) or ~17.6% (generous), i.e.
**GLiNER's post-level recall on this pool is >= 80-85% even at the bound**.
A trained span model's headroom over GLiNER is therefore at most ~20-25%:
~1,000 -> ~1,200-1,250 relevant posts a week. The decision stands.

The pool is ~98% posts that name no company at all. That is the finding
under the finding: the 66.6% the extractor sees nothing in is mostly
genuinely empty.

Not run: GLiNER over the 14,323 labelled posts with known spans (recall on
the easy kind). Would sharpen the bound; would not move the decision.

## Cross-check — GLiNER over the 13,933 confirmed spans, 2026-09-08

`scratchpad/label_export/gliner_recall_check.py`, 14,323 posts, 134 s on the
GPU. Results in `radar_labels/ner/gliner-recall/`.

    span recall      10,346 / 13,933 = 74.3%      post recall 77.0%
      ALLCAPS         8,460 / 10,860 = 77.9%      never in the zero-candidate pool
      Titlecase       1,144 /  1,388 = 82.4%      misses are mostly NOT companies: Jensen x25,
                                                  Zuck x25, Musk x24, Bezos x10, Japanese, Reddit,
                                                  Monday; real ones Robinhood x4, Bloom x4, Gopro x4
      other             165 /    190 = 86.8%      Wendy's x10 -- possessives
      cashtag           114 /    177 = 64.4%      production always catches these anyway
      lowercase         463 /  1,318 = 35.1%      spy x87, rdw, meta, dell, sndk, snow, lulu, avgo

**What it says about the bound.** The shapes that can exist in the
zero-candidate pool (Title-case, multi-word names) GLiNER finds at 82-87%,
and higher once the metonyms the span dataset counts (Jensen, Zuck, Musk are
"spans" because the teacher judged those rows relevant) leave the
denominator. Both methods now agree: **a trained span model's headroom over
GLiNER is ~15-25%, ~1,000 -> ~1,200 relevant posts a week.**

**The one shape training clearly wins:** lowercase symbols, 35% recall.
But lowercase symbols are the loose pass's territory -- they land in the
REJECT pool (prize A, 74% hit rate), not the zero-candidate pool -- except
where the ordinary-word filter eats them (`spy`, `snow`, `aim`). The 200-post
read found one such leak in 200 (`mu`).

GLiNER also produced 33,718 entities of which 23,375 (69%) cover no
confirmed span -- the same 84% unresolved rate the probe saw. Negatives are
not exhaustive, so that is an upper bound on its junk rate, not a measure.

## Our own tagger — DeBERTa-v3-small, 4 epochs, 2026-09-08

`scratchpad/label_export/train_ner.py`. 12,467 train examples, 1,856 held
out (every example touching a locked test set, 1,629 spans). bf16, batch 16,
lr 3e-5, max_len 256. **391 s on the RTX 3080** — bf16 and dynamic padding
made it 5x faster than the encoder's fp32 batch-8 recipe. Saved
`radar_labels/ner/model-ner-deberta-v3-small-20260908-133610/`.

    held-out   epoch 1  P 0.714  R 0.707  F1 0.711
               epoch 4  P 0.754  R 0.743  F1 0.749
    recall by kind, epoch 4: ALLCAPS 75.2%  Titlecase 65.8%  lowercase 78.2%  cashtag 61.9%  other 90.0%

### The same 3,000 posts, same lookup, same base@512 judge

    finder                    GLiNER small zero-shot    ours, small, 4 epochs
    posts with >=1 span             419  (14.0%)             240  (8.0%)
    spans / unresolved              527 / 440                255 / 187
    (post, symbol) pairs             78                       66
    relevant pairs                   55  (71% of pairs)       56  (85% of pairs)
    posts with a relevant pair       55  (1.83%)              56  (1.87%)
    extrapolated / week           1,290                    1,314
    finder time                      34 s                     20 s

**Two independent finders land on the same number.** The headroom in the
zero-candidate pool is ~1,300 relevant posts a week by the encoder's count,
~1,000 after the spot-check's precision. Ours produces less than half the
junk (187 unresolved vs 440) and its resolved pairs are judged relevant 85%
of the time against GLiNER's 71%. The decision does not move.

### What the held-out misses say: the labels teach the wrong job

Titlecase misses: `Nike x7, Nvidia x5, Google x5, Oracle x4, Amazon x4,
Microsoft x4`. False positives: `Nike x15, GOOG x8, Microsoft x7, Oracle x6`.
**The same names on both lists.** The span dataset's positives are RELEVANT
mentions and its negatives include posts where the company was named but
judged irrelevant, so the tagger is being asked to predict relevance -- the
encoder's job -- from surface form. It cannot, so it lands near 50/50 on
`Nike`. That is most of the 26% it misses and most of the 394 false
positives, and it is why the held-out recall is 74% on spans a teacher
confirmed.

The fix for a v2 is in the data, not the model: a row judged irrelevant
should stay a NEGATIVE only when its evidence token is an ordinary word
(`apple`, `spy`, `meta`, `snow`, `ai` -- the `common_words` instrument
already decides this); when the token is name-shaped or a distinctive
listing token, the mention is still a company reference and becomes a
POSITIVE span. The finder then learns "names a company", the encoder keeps
"is the post about it". Not run.

## v2 — fill and mask, 2026-09-08

`build_spans_v2.py` -> `spans-v2-2026-09-08.jsonl`: 72 name tokens (distinctive
∩ name-shaped − ordinary − stoplist, vouched ≥3 times by gold, + aliases),
3,250 silver spans in 1,604 posts, 21,813 masked symbol pieces. Same recipe,
391 s. Saved `model-ner-deberta-v3-small-20260908-135556/`.

**Held-out, same gold, both models scored the same lenient way** (a
prediction on a filled or masked region is neither hit nor miss):

    v1   P 0.862   R 0.742   F1 0.798
    v2   P 0.828   R 0.889   F1 0.857      Titlecase 65.8% -> 86.9%, ALLCAPS 75.2% -> 91.1%

Recall +14.7 points for −3.4 precision. The remaining 302 "false positives"
are led by `GOOG x14, meta x7, spy x6, BP x6, Musk x6, Lulu x5, nvda x4,
apple x4` -- real company references in posts the teacher judged irrelevant,
which the span dataset keeps as negatives. The finder is right to tag them;
relevance is the encoder's call. True precision is above 0.83.

**The probe, third finder in the same seat:**

    finder                     GLiNER     v1        v2
    posts with >=1 span          419       240       203
    unresolved spans             440       187       154
    (post, symbol) pairs          78        66        61
    posts with a relevant pair    55        56        48
    extrapolated / week        1,290     1,314     1,126

48 / 56 / 55 relevant posts in 3,000 is one number with noise (binomial sd
~7). Three finders, one answer: **~1.2k posts a week, ~1.7% of the pool.**
v2 is the finder to keep -- best held-out F1, least junk -- and the pool it
would search is confirmed small. Decision unchanged.

---

## Audit — Codex's four problems, verified independently 2026-09-08 (later)

`scratchpad/label_export/audit_ner_evidence.py`; outputs in
`radar_labels/ner/audit-2026-09-08/` (report.md, disagreements.md,
rejected-pairs-gliner.md, unresolved-gliner.txt). Every number below is from
the artifacts, not from the sections above. Where a section above is wrong,
this section wins.

### 1. Leakage — real, bounded, must still be repaired

`build_spans_v2.py` counted gold surfaces over ALL examples before the
hold-out split. With training-only gold, 8 names drop out of the vouched set:
`chevron, korea, marvell, mongodb, pfizer, qualcomm, starbucks, zscaler`. They
contributed **126 silver spans to training** (korea 57). In the HELD-OUT
gold those surfaces appear **12 times of 1,629** -- the most the leak could
have bought is 0.7 of the 14.8 recall points. **14 held-out rows share an
identical text with a training row** (3 gold spans); removing them moves P/R
by <= 0.001. Neither explains the improvement; both are defects. Repair: vouch
on training gold only, drop held-out rows whose text appears in training,
retrain. **Not done** (GPU job, ~7 min, needs Michi's go).

### 2. Scoring — not permissive in a way that matters

    rule                                 v1 P    v1 R    v2 P    v2 R
    any overlap                          0.862   0.742   0.828   0.890
    IoU >= 0.5                           0.848   0.732   0.823   0.886
    exact boundaries                     0.496   0.428   0.469   0.505

The exact collapse is the tokenizer: DeBERTa's offsets give a piece its
leading space, so 590 of v2's 1,449 overlapping predictions differ from
gold by whitespace only; 823 are exact; 26 narrower (`GPROI` for `$GPROI`,
the `$` convention); 6 wider; **4 genuinely partial** (`wendy` for
`wendy's`, ` d` for `dks`). Boundary-correct after strip: 97.5%.
Predictions covering two gold spans: 1. Predictions escaping FP by merely
touching a silver/ignore region: **0** for both models (the "Google garbage"
case does not occur; requiring >= 50% coverage changes nothing). End to end:
of the gold spans v2 overlaps, the predicted surface **resolves to the gold
ticker 1,404 times, to a different symbol 9, to nothing 36**.

### 4. Disagreement — read, all 44 posts

Codex's overlaps reproduce exactly (posts and pairs coincide: no post has
two relevant symbols). 33 pairs in all three finders: **31 true**, 2 the WSB
"Wendy's" meme. 44 posts in the union but not in all three: **17 true**
(3 of them borderline: `target` for an icee, `Musk`, `etoro`), **3 right
company / wrong ticker** (`go pro` -> GO, Grocery Outlet, three times; the
company is GPRO), **24 false**. So the union of 77 encoder-approved posts
holds **~48-50 true ones, 1.6% of the sample** -- and agreement between
finders is the strongest precision signal available (94% where all three
agree, 39% where they disagree).

**The judge is the weak stage on finder-proposed pairs.** False accepts, with
the encoder's own confidence: `corn` 1.00 ("buttcorn"), `Abt` 0.99 ("Abt to
full port" = about), `gold` 1.00 (the metal), `nat` 0.97 (nat gas), `twin`
0.96, `be` 0.93 ("bers"), `Dive` 1.00 ("Divedens"), `MT` 0.92 (inside
LQMT), `ws` 0.98 (inside wsb), `Alaska` 0.84 (the state). False rejects: 2 of
78 (`O` in "Vnq or O", Realty Income, 0.99 irrelevant; `Msft is guaranteed to
hit ath`, 0.71 irrelevant). The encoder was trained on pairs where the ticker
was always a plausible rule candidate; a pair like (CORN, "buttcorn took a
hit") is out of distribution and it reads the bearish text as relevant. Its
0.85 trial precision **does not transfer** to this population. Any finder
that ships needs either hard-negative pairs in the judge's training set
(finder junk labelled irrelevant) or a shape gate before the judge.

### 3. The recall-ceiling inference — wrong, and by about 2x

The "~1,200 ceiling" above treated one pipeline's yield as headroom. Split
by stage on the 3,000 posts:

- **Yield, human-validated**: ~48-50 true relevant posts (union of three
  finders, read), not 55.
- **Resolution losses**: of 440 unresolved GLiNER spans, **~35 are US-listed
  and resolvable in principle** -- `QQQ x10` (not in the universe), `Wendys
  x3` (possessive), `go pro x2`, `Door dash`, `jp morgan`, `AMEX`, `Pepsi`,
  `Fox News`, `planet labs`, `NTFLX`, `Microstrategy`, `Chili's`, `Tim
  Hortons`, `BRK`, `BLD` -- plus the 3 GoPro mis-resolutions. Roughly +25-30
  posts, half the current yield again, for a universe fix, possessive
  normalisation and a dozen aliases. ~30 more are foreign / OTC / private
  (LQMT, Porsche, Samsung, SpaceX, Stripe, Subway) and unresolvable by
  design. The remaining ~375 are indices, jargon, people, memes, crypto.
- **Detection losses**: the 200-blank read found 1 explicit miss (`mu`);
  scaled to the 2,581 blank posts that is ~13, up to ~70 at the Wilson upper
  bound. Two implicit references (unnamed yoga-pants company, `Winzigweich`)
  are not recoverable by any of this.
- **Judge losses**: 2 false rejects of 78 pairs.

Ceiling with everything repaired: ~90-115 relevant posts in 3,000 = **3.0-3.8%
= ~2,100-2,700 a week**, against the ~1,200 written above. Measured true
yield today: ~1.6% = ~1,100 a week. The order of the three prizes does not
change (prize A ~8,000, the Title-case shape ~800, this 1,100-2,700), but
what to fix INSIDE this pipeline does: the lookup first, the judge's
out-of-distribution pairs second, the finder last.

### What remains unverified

- A leak-free retrain (train-only vouching, text dedup). Until it runs, v2's
  0.857 is an upper estimate; the bound says the true number is >= 0.85.
- The 33 all-three pairs and 44 disagreements were read by Claude, not by
  Michi; the 31/33 and 17/44 are one reader's calls.
- The +25-30 from resolution is counted from surface forms, not re-run
  through the judge.

---

## Repairs — run 2026-09-08 (evening), after the audit

Commits `c05b19d`, `d3db162`. Benchmark reconstructed EXACTLY under the
universe and alias table it was drawn with (`--exclude-symbols`,
`--exclude-aliases`: 8,688 classified, all 514 posts any probe ever flagged
present). Resolution now uses production's universe (12,426 symbols; the dev
DB had been 88 short, `QQQ` among them -- a measurement artifact, not a
production gap) plus 16 aliases, apostrophe-insensitive names, an index
stoplist, a whole-word check on the finder's (trimmed) offsets, and an
ordinary-word gate on spans written entirely in lowercase.

**v3, leak-free** (train-only vouching, 14 shared texts dropped; 1,842 held
out): **P 0.826  R 0.882  F1 0.853** against v2's 0.828 / 0.889 / 0.857. The
leak was worth the ~0.7 recall points the bound said. v3 is the model to
quote. `model-ner-deberta-v3-small-20260908-163214/`.

**The probe, repaired lookup, same 3,000 posts:**

    finder                    GLiNER(old)  GLiNER   v1    v2    v3
    (post, symbol) pairs           78        90     61    56    57
    relevant posts                 55        69     58    54    57
    unresolved spans              440       429    191   156   156
    union 81 posts (2.70%); in every run 33

Gained, all read: `QQQ x9` (universe), `go pro` x2 -> GPRO, `Door dash` ->
DASH, `jp morgan` -> JPM, `AMEX` -> AXP, `Pepsi` -> PEP, `NTFLX` -> NFLX
(aliases), `$soxl`, `$spy`, `mu` (lowercase symbols the gate now passes
because they are not ordinary words). Lost, all correct: `Dow`, `Nasdaq` x2
(index stoplist). Residue: `QQQs` -> QQQS (a plural onto a real symbol),
three Wendy's memes, `Abt`, `Michael Dell's wife` -- and GLiNER's own junk
(`Oshkosh Bigosh`, `V`, `Na`, `CSP`, `MMs`, `Stablecoin ... companies`)
which the lowercase gate does not touch because it is written capitalised.

**Of the audit's 27 known-false pairs**: GLiNER still passes 7, v1 4, v2 2,
v3 3. The lookup repairs removed 20-25 of them without touching the judge.

**Measured true yield with the repaired lookup**: ~67-69 of the 81 union
posts, **~2.25% of the pool, ~1,580 a week** (was ~1,100). Ceiling with the
detection misses the 200-blank read bounded (+13 point, +70 at the Wilson
edge): **~2.7-4.6%, ~1,900-3,200 a week**. The audit's 2,100-2,700 sits
inside that. Prize A (~8,000) is still two to four times larger.

**What the trained finders still miss that GLiNER finds**: `Avgo`, `Goog`,
`Nvda` (one of three), `Dell` (one of eight), `Klaviyo`, `Endovia`,
`Scilex`, `Vnq`, and every two-word brand (`go pro`, `Door dash`, `jp
morgan`). Title-case SYMBOLS are the pool's largest prize and the span
dataset barely contains them -- its Title-case spans are names (Nvidia,
Apple), not symbols written as names (Nvda) -- so a tagger trained on it
under-finds exactly the shape that matters here. Zero-shot GLiNER, which
treats `Avgo` as ticker-like on sight, is the better finder for this pool
today. Either finder needs the Title-case symbol RULE beside it, and that
rule alone recovers most of this without a model.

---

## Shipped 2026-09-08 17:35 CEST — the extractor counts cased symbols and names alone

`a40eb4e`, `aabcb05`, `617917c`; deployed as `b7d8adf`. Stamp
`3f96922d51fe4ef0 -> f782308bdcb9366c`; every baseline restarts.

Four new candidate sources in `extraction._scan`, all at the source's bare
confidence (high on finance-native Reddit, low elsewhere), all gated by
two corpus-derived lists shipped as data files and hashed into the stamp
(`features/radar/data/ordinary_words.txt`, `name_shapes.txt`, regenerated
by `scripts/refresh_corpus_instruments.py`):

- `titlecase_symbol` -- `Nvda`, `Avgo`, `Dell` (`[A-Z][a-z]{2,4}`, not an
  ordinary word)
- `lowercase_symbol` -- `lulu`, `soxl`, `mu` (`[a-z]{3,5}`, not an ordinary
  word)
- `name_only` -- a distinctive listing token the corpus writes like a name,
  with exactly one claimant, not an ordinary word, not on the name stoplist,
  on the author's own text only
- `alias` -- NAME_ALIASES and METONYMS, moved into config, author text only

**Measured on the raw week before shipping**, first as built and then after
two defects the measurement itself exposed:

    mentions / week           46,527 -> 93,628 (as built) -> 74,820 (as shipped)
    posts with a mention      36,791 ->                      57,204
    name_only                       29,861 (as built) ->      9,005
    titlecase_symbol                                          7,198
    lowercase_symbol                                          7,241
    alias                                                     4,558

The two defects: r/thetagang's daily thread "The Lounge" handed LVLU 1,208
comments through the parent title (`lounge` is a listing token), so names
and aliases count on the author's own text only; and 36% of name_only rode
on tokens several listings share (`apple` -> APLE the REIT, `fidelity` ->
three listings none of them Fidelity), so a shared token names nobody
unless the alias table settles it (apple, alphabet, goldman, hertz, webull).

First cycle under the new daemon (17:37): Reddit wallstreetbets intake
`lowercase_symbol 7, bare_source_high 7, titlecase_symbol 2, name_only 1`;
2,738 bucket rows on the new stamp in 20 minutes. The prize as measured
today is ~28,000 real mentions a week, not the ~9,000 quoted earlier: the
earlier figure counted only posts the board had never seen.

Pre-existing, not fixed: `USD` draws ~2,000 bare mentions a week from
"EUR/USD"; a stopword entry, separate change. Judge hard negatives (§6 0c
of the handover) remain the open item; the ordinary-word gate keeps
`Abt`, `Gold`, `Corn` out of the judge's reach, but any finder that ships
later still needs them.

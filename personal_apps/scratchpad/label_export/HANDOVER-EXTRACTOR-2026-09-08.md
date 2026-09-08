# Handover: the radar extractor, the NER question, and where it landed

**For Codex.** Written 2026-09-08 ~14:30 CEST by the session that ran the
work. Branch `dev_personal`, repo `C:\Users\michi\Desktop\CodingStuff`, HEAD
`9982305`. Nothing in this document is merged to `main` or deployed. Verify
against the files and the numbers before acting; where this document and the
evidence disagree, the evidence wins and the discrepancy gets written down.

---

## 0. Corrections after Codex's audit (read first)

Codex audited this document and found four problems; the session then
verified each against the artifacts (`audit_ner_evidence.py`, outputs in
`radar_labels/ner/audit-2026-09-08/`, full write-up in the design doc's
last section "Audit"). What changes:

- **§4.6 leakage**: `build_spans_v2.py` vouched names on ALL gold, not
  training gold. 8 names leaked (126 training silver spans, 57 of them
  `korea`); 14 held-out rows duplicate training texts. Effect on the held-out
  number: at most 0.7 recall points and <= 0.001 respectively -- the v2 gain
  is real, but v2's 0.857 is an upper estimate until a leak-free retrain runs.
  **Not yet retrained.**
- **§4.6 scoring**: holds. IoU >= 0.5 moves nothing; 0 FP escapes; 97.5% of
  overlapping predictions are boundary-correct after whitespace; 97% resolve
  to the gold ticker.
- **§4.7 "~1.2k ceiling" is wrong by ~2x.** It was one pipeline's yield.
  Human-validated true yield is ~48-50 of 3,000 (1.6%, ~1,100/week); the
  ceiling with the lookup repaired and detection misses counted is
  ~3.0-3.8% (~2,100-2,700/week). Still a third of prize A.
- **New, and the most important finding of the audit**: the encoder
  rubber-stamps out-of-distribution pairs a finder proposes (`corn` 1.00,
  `Abt` 0.99, `gold` 1.00, `nat` 0.97, `twin` 0.96). Its trial precision
  does not transfer. **No finder can ship in front of this judge without
  hard-negative pairs in the judge's training or a shape gate.** Section 6
  is re-ordered accordingly.
- The lookup, not the finder, is the largest recoverable loss inside the
  pipeline: `QQQ` is absent from the universe (10 posts), possessives and a
  dozen aliases (`go pro`, `Door dash`, `jp morgan`, `AMEX`, `Pepsi`) are
  ~35 spans, roughly +50% on today's yield.

### 0.1 Repairs executed (evening, `c05b19d`, `d3db162`) -- read with §0

- **Leak-free v3 trained**: P 0.826 R 0.882 F1 0.853. Quote this, not v2.
  `model-ner-latest.txt` points at it.
- **Lookup repaired** (apostrophes, index stoplist, lowercase-only
  ordinary-word gate, whole-word check on trimmed offsets, 16 aliases in
  `NAME_ALIASES`) and the **dev universe reseeded from production's
  directory files** (+88 symbols, `QQQ` among them). The "QQQ not in the
  universe" finding was the DEV database, not production.
- **Benchmark reconstructed exactly** under the old universe and alias
  table; stage 1 has `--exclude-symbols` / `--exclude-aliases` for it.
- **Probe, repaired lookup**: GLiNER 69 relevant posts (was 55), v1 58,
  v2 54, v3 57; union 81 (2.70%). Of the 27 known-false pairs, 20-25 are
  gone per run without touching the judge. Measured true yield ~2.25%
  (~1,580/week); ceiling ~2.7-4.6%.
- **New finding**: the trained taggers under-find Title-case SYMBOLS
  (`Avgo`, `Goog`, `Nvda`) because the span dataset barely contains that
  shape; GLiNER finds them on sight. For this pool GLiNER is the better
  finder today, and the Title-case symbol rule beats both.
- `QQQs` -> QQQS is a new mis-resolution (a plural landing on a real
  symbol); three Wendy's memes and `Abt` survive the gates. Judge hard
  negatives (§6 0c) remain the fix for those.

### 0.2 Shipped (17:35 CEST, `b7d8adf`) -- §6 items 1 and 2 are DONE

The Title-case shape, the lowercase shape, names alone and the alias table
are in production (`a40eb4e`, `617917c`), measured on the raw week at
74,820 mentions/week against 46,527 (+61%), stamp moved to
`f782308bdcb9366c`, board warming up. Two corpus word lists ship as data
files under `features/radar/data/` and are hashed into the stamp;
`scripts/refresh_corpus_instruments.py` regenerates them from a raw week.
Names and aliases count on the author's own text only (the LVLU / "The
Lounge" defect); a name shared by listings names nobody unless the alias
table settles it (the APLE defect). Full write-up: design doc, last
section "Shipped". Still open from §6: 0c judge hard negatives, and a
`USD` stopword.

## 1. Why this work exists

The radar board counts company mentions in Reddit/Bluesky/4chan posts. Two
trained models were always the plan, and only one existed:

- **The judge** (exists, in production): a DeBERTa encoder that answers
  "is this text about ticker X, and what is the author's tone". It cannot
  FIND X; a rule has to propose the candidate first.
- **The finder** (did not exist): something that finds the words naming a
  company so the judge has a candidate. Today that is a regex extractor
  (`features/radar/extraction.py`): cashtags, ALL-CAPS symbols, and
  distinctive listing-name tokens, gated by stopword and casing rules.

Measured 2026-09-06/07 on a raw week of Reddit (198,586 posts, Arctic
Shift): the extractor **rejects ~11,450 real mentions a week** it did see
(a company named without its symbol, a lowercase symbol) against 46,527
counted, and **66.6% of posts produce no candidate at all** (132,164). The
first is "prize A". The second is the pool a trained finder (NER) would
search. Nobody knew how much was in it; the only estimate was a zero-shot
GLiNER probe over 300 posts, read by eye: "call it 4-5%".

Michi's long-standing architecture: **trained - static - trained**. A span
tagger finds the words, a static lookup maps a span to one of ~12,500
symbols (that many classes cannot be learned from 20k examples), the
existing encoder judges the pair. The span dataset for the tagger already
existed (`spans-2026-09-07.jsonl`: 14,323 posts, 13,933 spans derived from
the `evidence` token of every labelled row); the model did not.

## 2. The goal, as set today

Decide -- with a number, not a guess -- whether building the span model is
worth it, and if so build it. Two orders were on the table:

- A first: loosen two extractor rules and let the (now live, zero-cost)
  encoder judge the rejects. No model. ~8,000 real mentions a week.
- B first: build the span model for the 66.6% pool. The build Michi has
  wanted for months.

Michi chose to **measure B before building it**, with an idea of his own
(§4.1), then chose to build it anyway as an experiment (§4.5), which turned
out to be the right call for a reason nobody expected (§4.6).

## 3. State of the world

**Production** (194.164.29.97, `/root/coc-stats`, deployed `main` at
`c580fff` or later): the encoder trial was retired in code and the
**base@512 encoder is live**, judging **every** mention -- `JUDGE_GATE_ENABLED
= False` since `c580fff`. Coverage went from ~10% to 95-98% of mentions.
The feared baseline discontinuity did not materialise (worst `mention_z`
anywhere in 6h was -1.11). A 4 GB swapfile with `vm.swappiness=10` was added
because the box was at 872 MB free with no swap. **None of that is this
session's work to describe further**; it is context. See
`TRIAL-RETIREMENT-PLAN.md` and `TRIAL-RETIREMENT-HANDOVER.md` beside this
file, and the commits `45a7e39..f1d8aed`.

**This branch**, `dev_personal` at `9982305`: everything in §4 is committed.
80 tests pass (`tests/test_span_lookup.py`, `test_sample_zero_candidate_posts.py`,
`test_ner_probe.py`, `test_gliner_recall_check.py`, `test_ner_tagging.py`,
`test_span_dataset.py`, `test_span_tagging.py`). Two dirty files are NOT
mine and must be preserved: `scripts/discover_telegram_sources.py`,
`telegram_candidates.json`. 28 untracked files, all pre-existing scratch.

**Nothing changes production extraction.** `source_config_version()` is
untouched; no extractor rule was edited. The two things that would --
the Title-case shape and prize A -- are §6, not done.

**Two Pythons.** The app (extractor, universe, DB) runs in the system
Python 3.12 with `PYTHONPATH=.` from `personal_apps/`. Torch, CUDA, GLiNER
and the trainers run in `C:\Users\michi\Desktop\radar_encoder_venv`
(`Scripts\python.exe`), which has no Flask. Every script below says which.

## 4. Experiments and results, in order

All artifacts under `C:\Users\michi\Desktop\radar_labels\` (`radar_labels/`
below). The design doc with every number and every correction is
`docs/superpowers/specs/2026-09-08-ner-headroom-probe-design.md` at the
repo root -- read it after this.

### 4.1 The headroom probe (Michi's idea)

Run the target architecture NOW, with zero-shot GLiNER standing in for the
span model that does not exist: zero-candidate post -> GLiNER finds a span
-> lookup maps it to a symbol -> the production base@512 encoder judges the
pair. What comes out the end is the prize, counted. Nothing costs API money.

- Stage 1 `scripts/sample_zero_candidate_posts.py` (app Python): seeded
  uniform sample of 3,000 posts where `classify()` found nothing -- no gate,
  no production candidate, no loose-pass candidate -- with a >=40-char body.
  3,000 came from 8,688 shuffled posts (34.5%). Wrote `radar_labels/ner/
  sample-3000.jsonl` and `lookup.json` (universe dump). 55 s.
- Stage 2 `scratchpad/label_export/ner_probe.py` (venv): find, resolve
  (`span_lookup.py`: exact tiers only -- symbol, name, distinctive tokens,
  alias -- no fuzzy matching, unresolved is a correct answer), judge
  (`ask_encoder.py` loader, batches of 16, CPU), count.

Result (`radar_labels/ner/probe-3000/`):

    posts sampled 3000; with >=1 span 419 (14.0%); spans 527, 440 unresolved
    (post, symbol) pairs 78; encoder relevant 55; posts with a relevant pair 55 (1.83%)
    extrapolated 1,290 relevant posts / week; gliner 34 s GPU, encoder 53 s CPU

**Correction made and committed (`f0eedce`)**: the extrapolation base is
**70,381** (zero-candidate posts clearing the 40-char floor), not 132,164.
Stage 1's 34.5% x 198,586 = 68,512 agrees.

**Spot-check** (`probe-3000/spotcheck.md`, all 50 read): 9 wrong, 2
borderline, ~80% precision. Wrong ones cluster: short generic symbols
(`Na`->NA, `V`->Visa, `MMs`->Maximus, `CSP`->CSPI), index names to a company
(`Nasdaq`->NDAQ, `Dow`->DOW), a generic phrase through the tokens tier
(`Stablecoin infrastructure companies`->SDEV), a brand collision (`Oshkosh
Bigosh`->OSK). Corrected prize ~1,000 posts a week.

**The decisive table**, relevant / judged by how the span resolved:

    symbol, Title-case span   35 / 38    Nvda, Avgo, Dell, Tsla, Goog, Htz, Sndk
    name                       8 / 10
    tokens                     7 / 10
    symbol, lowercase          1 / 11

**64% of everything found is one regex.** `BARE_PATTERN` is `[A-Z]{2,5}`
and `CASHTAG_PATTERN` also demands caps (`config.py:197-201`), so `Nvda`,
`Avgo`, `Dell`, `$Duot` are invisible to production AND to the loose pass.
That is a candidate shape, not a model. The NER-only remainder (name +
tokens tiers) is ~350 posts a week, 0.75% of counted volume.

Unresolved top: `QQQ x10` (**not in the universe**), `VIX`, `SPX`, `S&P
500`, `WSB`, `Bessent`, `New Balance`, `Jane Street` -- indices, jargon,
private companies, people. A better lookup adds little.

### 4.2 Bounding GLiNER's recall (Michi's objection: "it's untrained")

A zero-shot finder's misses make the probe a floor. Two free bounds:

- **200 of its 2,581 blank posts read in full** (ids in `probe-3000/
  miss-audit-ids.json`): 1 explicit miss (`puts or short on mu`), 2 implicit
  (an unnamed "company that makes yoga pants", `Winzigweich` = Microsoft in
  mauerstrassenwetten German). Wilson 95% upper 2.8-4.3% -> GLiNER post
  recall >= 79-85%. ~195 of 200 name no company at all.
- **GLiNER over the 13,933 confirmed spans** (`gliner_recall_check.py`,
  `radar_labels/ner/gliner-recall/`, 134 s): span recall 74.3%; ALLCAPS
  77.9%, **Titlecase 82.4%** (misses mostly metonyms the dataset counts:
  Jensen, Zuck, Musk), other 86.8%, cashtag 64.4%, **lowercase 35.1%**.

Both say: a trained finder's ceiling over GLiNER is ~15-25%, ~1,200 a week.

### 4.3 Decision recorded at that point (`5da7098`)

Do not build the span model now; the pool is small and 64% of it is a
regex. Michi then asked to build it anyway as an experiment: "small instead
of base first, 4 epochs, see where it lands".

### 4.4 v1 tagger (`train_ner.py`, `aae0a94`)

DeBERTa-v3-small + dropout + one linear layer over BIO. Labels through
`span_tagging.align` with specials masked -100. Every example touching one
of the three locked test sets held out whole (1,856 of 14,323; 1,629 spans).
bf16, batch 16, lr 3e-5, max_len 256, OneCycle, checkpoint per epoch under
`checkpointing.py`. **391 s** -- 5x faster than the encoder's fp32 batch-8
recipe. Saved `radar_labels/ner/model-ner-deberta-v3-small-20260908-133610/`.

    held-out epoch 4   P 0.754  R 0.743  F1 0.749
    ALLCAPS 75.2%  Titlecase 65.8%  lowercase 78.2%  cashtag 61.9%  other 90.0%

In the probe (`--finder trained`, `probe-3000-trained/`): 240 posts with
a span, 187 unresolved (vs 440), 66 pairs, **56 relevant posts** (GLiNER 55),
85% of pairs relevant (GLiNER 71%). Same headroom, half the junk.

### 4.5 The diagnosis that was wrong, then right

Held-out Titlecase misses were `Nike, Nvidia, Google, Oracle, Amazon,
Microsoft`; false positives were `Nike, GOOG, Microsoft, Oracle`. Same names
both lists. I first claimed the cause was rows judged irrelevant being
negatives. **That was wrong**, and the preview of what such a rule would
promote (`AI, SPY, RSI, FCF, Monday, TACO`) showed it. The measured cause:

    name        unlabelled   gold   negative      (posts where the name appears in the text)
    nike            87        126      0
    google         244         29      3
    nvidia         198         82      0
    microsoft      107         30      2
    amazon         143         47      2
    apple          154          8     30

**The names are unlabelled.** Labelling waves sampled MENTIONS, so a post
labelled for NVDA that also names Google has no row for Google, and
`examples_from()` -- correctly, from what it was given -- left Google as
background. The tagger was trained that Google is O 244 times and B 29
times. Textbook partial annotation; not teacher noise.

### 4.6 v2: fill and mask (`build_spans_v2.py`, `e2b7484`)

- **silver**: an unlabelled occurrence of a NAME token becomes a positive
  span. Name token = distinctive listing token (`span_lookup.build_index`,
  <=4 claimants) AND name-shaped (`name_shapes`, capitalised mid-sentence
  >=10%) MINUS ordinary words (`ordinary-words.json`, lowercase >=50%) MINUS
  a small stoplist (`trump`, `reddit`, days, months) AND **vouched >=3 times
  by gold**, PLUS the alias table (`google` is not a listing token). 72
  tokens; 3,250 silver spans in 1,604 posts.
- **ignore**: an unlabelled symbol written as one (ALLCAPS or cashtag, in
  the universe) is masked to -100. `AI`, `SPY`, `RSI`, `FCF` are listed
  symbols and ordinary words at once. 21,813 pieces.
- Gold and judged negatives untouched. Evaluation keeps the original gold
  and charges nothing on a filled or masked region.

Inputs: `radar_labels/ordinary-words.json`, `promotion-instruments.json`
(name_shapes, STOPWORDS, universe), output `spans-v2-2026-09-08.jsonl`.
Saved model `model-ner-deberta-v3-small-20260908-135556/`;
`model-ner-latest.txt` points at it.

**Held-out, same gold, both scored the same lenient way:**

    v1   P 0.862  R 0.742  F1 0.798
    v2   P 0.828  R 0.889  F1 0.857     Titlecase 65.8 -> 86.9%,  ALLCAPS 75.2 -> 91.1%

Remaining v2 "false positives" are led by `GOOG x14, meta x7, spy x6, BP
x6, Musk x6, Lulu x5, nvda x4, apple x4`: real company references in posts
the teacher judged irrelevant, which stay negatives. The finder is right to
tag them; relevance is the encoder's job. True precision > 0.83.

**The probe, third finder** (`probe-3000-trained-v2/`): 203 posts with a
span, 154 unresolved, 61 pairs, **48 relevant posts**, 1,126 a week.

### 4.7 The answer

    finder                     GLiNER    v1     v2
    posts with a relevant pair    55     56     48     (of 3,000; binomial sd ~7)
    extrapolated / week        1,290  1,314  1,126

Three finders, one number: **~1.2k relevant posts a week in the
zero-candidate pool, ~1.7% of it**, against ~8,000 in prize A and 46,527
counted. **The span model works (F1 0.857, a 6.5-minute train) and the
pool it would search is small.** Both true at once.

## 5. Where we stand

- The NER question is closed, measured three ways. v2 is the finder to keep
  if the pool is ever opened. It is NOT packaged, NOT ONNX, NOT deployed, and
  should not be: its measured prize does not justify a fourth model in
  production today.
- The probe is a fixed benchmark: any future finder runs against the same
  `sample-3000.jsonl` through the same lookup and judge and the numbers
  compare.
- The decision on order stands as recorded in the design doc: (1) the
  Title-case symbol shape, (2) prize A, (3) NER only if sources or corpus
  change.

## 6. What comes next, in order (none started) -- re-ordered after the audit

0. **Leak-free retrain of v2** (vouch on training gold only; drop held-out
   rows whose text is in training). ~7 min GPU; ask Michi for the when. This
   is a repair of evidence, not a new experiment.
0b. **Lookup and universe**: add `QQQ` (and check `DIA`/`GLD`-class ETFs are
   present), possessive normalisation (`Wendys`, `Wendy's`), aliases for
   `go pro`->GPRO, `door dash`->DASH, `jp morgan`->JPM, `amex`->AXP,
   `pepsi`->PEP, `fox news`->FOX, `microstrategy`->MSTR, an index stoplist
   (`Nasdaq`, `Dow`, `Russell`) so those never resolve to NDAQ/DOW, and no
   `tokens`-tier resolution of a span the finder cut inside a word (`go` from
   `Avgo`, `MT` from `LQMT`, `ws` from `wsb`: require the span to be
   whole-word in the text). Re-run the fixed 3,000 sample; expect ~+25 posts.
0c. **The judge's junk pairs**: before any finder goes in front of the
   encoder, train the encoder with hard negatives -- (symbol, text) pairs a
   finder proposed and a reader rejected (the 24 false ones from
   disagreements.md are the seed) -- or gate short generic symbols before
   the judge. Without this every finder's precision is capped by the judge's
   worst habit.

1. **Title-case candidate shape** in `features/radar/extraction.py`: a
   `[A-Z][a-z]{2,4}` token whose uppercase is a universe symbol, gated by the
   existing ordinary-word and name-shape instruments, judged by the encoder.
   ~800 real mentions a week for a regex. **Extraction change -> bumps
   `source_config_version()` -> board-wide warm-up. That is the designed
   behaviour, not a bug; say so in the commit.** Measure first with
   `scripts/measure_extractor_population.py` over the raw week (it already
   has the loose pass; add the shape there before touching production).
2. **Prize A**: loosen name-only and lowercase-symbol rejections, encoder
   judges. Same stamp consequence. The loose pass in
   `measure_extractor_population.py` already implements the candidate side
   and `report_recall.py` the measurement; what is missing is the production
   rule change and its tests.
3. Housekeeping the probe found: `QQQ` is not in the universe (10 unresolved
   spans); `is_pooled_vehicle` misses "ProShares Ultra NVDA" and debt
   listings own their due month (both patched locally in
   `measure_extractor_population.py`, not in `universe.py`).

## 7. What Codex should verify, concretely

1. `python -m pytest tests/test_span_lookup.py tests/test_sample_zero_candidate_posts.py tests/test_ner_probe.py tests/test_gliner_recall_check.py tests/test_ner_tagging.py tests/test_span_dataset.py tests/test_span_tagging.py -q` from `personal_apps/` -> 80 passed.
2. `radar_labels/ner/probe-3000/summary.json`, `probe-3000-trained/summary.json`,
   `probe-3000-trained-v2/summary.json`: `relevant_posts` 55 / 56 / 48,
   `extrapolated_relevant_posts_per_week` 1290.32 / 1314.x / 1126.x.
3. `radar_labels/ner/model-ner-deberta-v3-small-20260908-135556/results.json`:
   epoch 4 `precision` 0.828, `recall` 0.889, `f1` 0.857.
4. That `span_prf` with `silver`/`ignore` present never counts a prediction
   on those regions as tp OR fp (`ner_tagging.py`, and
   `tests/test_ner_tagging.py::test_prf_does_not_charge_predictions_on_undecided_regions`).
   The v1-vs-v2 comparison in §4.6 depends on it.
5. That `build_spans_v2.py` never adds silver over a gold span or a judged
   negative (`tests/test_span_dataset.py::test_augment_never_touches_gold_or_judged_negatives`).
6. That the extrapolation constant is 70,381 with the reasoning in
   `ner_probe.py` (`ZERO_CANDIDATE_POSTS_PER_WEEK`), and that stage 1's
   34.5% supports it.
7. The claim "64% of the prize is Title-case symbols": recompute from
   `probe-3000/findings.jsonl` + `verdicts.jsonl` (35 of 55 relevant pairs
   with a `symbol`-tier span matching `[A-Z][a-z]{1,5}`).
8. `BARE_PATTERN`/`CASHTAG_PATTERN` really are caps-only
   (`features/radar/config.py:197,201`).

Reproduce any stage:

    # app Python, from personal_apps/
    PYTHONPATH=. python scripts/sample_zero_candidate_posts.py --raw C:/Users/michi/Desktop/radar_labels/raw/reddit --out C:/Users/michi/Desktop/radar_labels/ner --n 3000
    python scratchpad/label_export/build_spans_v2.py
    # venv, from personal_apps/
    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe scratchpad/label_export/ner_probe.py --finder trained --sample C:/Users/michi/Desktop/radar_labels/ner/sample-3000.jsonl --lookup C:/Users/michi/Desktop/radar_labels/ner/lookup.json --out <dir> --artifact-dir C:/Users/michi/Desktop/radar_labels/artifact-base
    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe scratchpad/label_export/train_ner.py --epochs 4 --spans C:/Users/michi/Desktop/radar_labels/spans-v2-2026-09-08.jsonl
    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe scratchpad/label_export/gliner_recall_check.py --spans C:/Users/michi/Desktop/radar_labels/spans-2026-09-07.jsonl --out <dir>

Training is a GPU job on Michi's workstation (~5 GB VRAM, ~7 min). **Ask
him before running it**; do not run it to "check".

## 8. Traps hit today, so they are not re-hit

- `common_words` is NOT "is this an ordinary word" in a finance sub:
  `SPY`, `AI`, `Meta` are written upper-case >50% of the time, so none of
  them is "ordinary". `name_shapes` ∩ distinctive − ordinary − stoplist,
  vouched by gold, is the instrument that worked. Both preview lists that
  led there are in the design doc.
- The cp1252 console kills a run on the first non-Latin-1 character in a
  span (a peace sign, `▁`). Every script now does
  `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`.
- A pipe eats an exit code: `python smoke.py | grep -v ... && python
  train.py` runs the trainer even when the smoke fails.
- The venv cannot import the app and the app Python cannot import torch;
  scripts that need both are split into stages with files between them.
- The span dataset counts metonyms (`Jensen`, `Zuck`, `Musk`) as gold
  spans because the teacher judged those rows relevant. A "Titlecase
  miss" list needs reading before it is believed.
- `test_span_lookup` fixture names must normalise the way real Nasdaq
  names do (`- Common Stock` suffixes, share classes); a fixture with
  `Capital Stock` briefly forced `capital` into the suffix list, which
  would have broken Capital One.
- `gliner 0.2.28` exposes `predict_entities` on the INSTANCE only;
  `dir(GLiNER)` on the class shows nothing.

## 9. Files

    docs/superpowers/specs/2026-09-08-ner-headroom-probe-design.md   the record; read it
    personal_apps/scripts/sample_zero_candidate_posts.py             stage 1 (app)
    personal_apps/scratchpad/label_export/span_lookup.py             span -> symbol, exact tiers
    personal_apps/scratchpad/label_export/ner_probe.py               stage 2, --finder gliner|trained
    personal_apps/scratchpad/label_export/gliner_recall_check.py     GLiNER vs confirmed spans
    personal_apps/scratchpad/label_export/ner_tagging.py             masking, BIO decode, hold-out, P/R/F1
    personal_apps/scratchpad/label_export/train_ner.py               the tagger (venv)
    personal_apps/scratchpad/label_export/build_spans_v2.py          fill + mask
    personal_apps/scratchpad/label_export/span_dataset.py            + augment()
    personal_apps/scratchpad/label_export/ask_encoder.py             the terminal toy the probe reuses
    radar_labels/ner/                                                sample, lookup, three probe dirs, two models, logs
    radar_labels/spans-v2-2026-09-08.jsonl, ordinary-words.json, promotion-instruments.json

## 10. Open questions for Michi

- Whether to go ahead with §6.1 and §6.2 now that the encoder is judging
  everything. Both bump the stamp; both are measured; neither is built.
- Whether v2 should be packaged to ONNX and kept as a shelf artifact (a
  30-minute job) or left as a checkpoint. My recommendation: leave it.

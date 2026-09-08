# Encoder judge: hard negatives + a new-shape wave, then one retrain of base

Ledger for the 2026-09-08 (evening) task. Branch `dev_personal`, repo
`C:\Users\michi\Desktop\CodingStuff`, work under `personal_apps/`. Data in
`C:\Users\michi\Desktop\radar_labels\` (outside the repo). Nothing here is
merged to `main` or deployed; Michi swaps artifacts himself.

Rules in force: no API quota without Michi naming the size; no GPU job
without VRAM/minutes stated and a "when"; TDD; locked sets never trained
on; the PC crashes on its own every ~5 days, checkpointing stays on.

## Why

Production (194.164.29.97) judges every high-confidence mention with
base@512 (`artifacts/judge/v1`, model `model-train17090-20260907-192428`,
gate off). Since 2026-09-08 15:35 UTC the extractor also counts Title-case
symbols, lowercase symbols, names alone and aliases: ~+40% volume, ~10.9k
judged a day. Two measured defects in the judge:

1. It rubber-stamps out-of-distribution pairs: `corn` 1.00 ("buttcorn"),
   `Abt` 0.99 ("about"), `gold` 1.00, `nat` 0.97, `twin` 0.96. The
   extractor's word lists keep most of these away from it; the fix belongs
   in the judge.
2. Removal precision 0.85 on the trial audit (746 rows, reference GPT
   "Astra"); false rejects are rare (2/78 on the probe), false accepts are
   the problem.

## Deliverable 1 -- the hard-negative set (DONE, commit on dev_personal)

**Finding first:** the second source Michi named -- `labels-recall.jsonl`
joined to `rejected-candidates.jsonl`, the rows the wave labelled
irrelevant -- is **already in the live model's training set**. The 4,500
recall labels are in `train_encoder.PAIRS`; `model-train17090` carries
`recall_labels_sha 9be2b91bafb58b5b`, the file's sha today. 1,765 of those
irrelevant rows are in training (902 are locked), and the model still
rubber-stamps `corn`. They are the loose pass's candidates, gated the same
way as production, not a finder's cuts: the wave's lowercase stratum never
held an ordinary word, and nothing in it was a symbol inside another word.
So the set had to come from somewhere else, and with no spend that means
construction from the raw week.

**Built** (`scratchpad/label_export/build_hard_negatives.py`, rules in
`hard_negatives.py`, 28 tests): 1,553 rows in
`radar_labels/labels-hardneg.jsonl` + `candidates-hardneg.jsonl`, ids in
their own block (-3,000,001..), report in `hardneg-report.md`, spot-read
in `hardneg-spotread-50.md`.

    kind      relevance    rows   what it is, and why it is pure
    subword   irrelevant    597   a symbol cut at a word's EDGE (butt|corn, LQ|MT, ws|b, Av|go),
                                  written nowhere else as a word, cashtag or company name;
                                  2-letter symbols only when they are words (be, go, ms).
                                  Irrelevant by construction: nobody mentioned it.
    ordinary  irrelevant    800   an ordinary word (corpus writes it lowercase >=50%) that is a
                                  symbol, written lowercase or at a sentence start, no $SYM, no
                                  CAPS, no name token of the company in the text, and the word
                                  NOT in the listing name (gold/Barrick Gold, corn/Corn Fund,
                                  target/Target are arguable and left out).
    index     irrelevant     80   Dow / Nasdaq as the index -> DOW Inc / NDAQ; company sense
                                  (Nasdaq Inc, $NDAQ) left alone.
    read      irrelevant     31   the audit's 24 false accepts (+3 go-pro->GO, +2 Wendy's memes)
    read      relevant       45   the audit's true disagreements + the 31 all-three pairs, tone
                                  read by the same reader; anchors Nvda/Avgo/Dell/Tsla as REAL

Sources: raw week `radar_labels/raw/reddit` (198,586 posts), the prod
universe `ner/lookup.json` (12,426 symbols), `features/radar/data/
ordinary_words.txt` + `name_shapes.txt`, `hardneg-read-2026-09-08.json`
(the verdicts, transcribed from `ner/audit-2026-09-08/disagreements.md`
and the all-three list; borderline pairs target/TGT, etoro/ETOR,
Muskrat/TSLA and the arguable Coke->COKE, hp->HP left out).

Exclusions: every post the three locked sets hold (by external id and by
text), the trial audit's 746 texts, the 200-row audit's texts, the NER
probe's 3,000 posts (kind `read` draws from those deliberately). Caps:
6 per symbol (subword), 8 (ordinary), 60 (index), one pair per post;
70% of the subword budget on word-shaped symbols first.

**Spot-read of 50** (seed 20260908, `hardneg-spotread-50.md`): **50 of 50
irrelevant as constructed.** Two rows were press-release / market-recap
posts, which exposed a defect: a constructed row's origin, tone and
confidence fields are placeholders. Fixed the same evening --
`tone_training.is_constructed` masks every head but relevance for the
three constructed strata (`hardneg:read` trains every head). Measured
through the trainer's own path: relevance trains on 18,643 rows, origin
and confidence on 17,166, tone heads on 11,102; 0 hard-negative ids in a
locked set; 0 dropped by the split.

Trainer changes: `train_encoder.PAIRS` reads the wave when the file
exists; `hardneg_labels_sha` is in the checkpoint settings
(`checkpointing.SETTINGS_THAT_MUST_MATCH`) and the manifest, with
`hardneg_rows`.

## Deliverable 2 -- the new-shape wave (PROPOSAL, nothing labelled)

`scripts/sample_new_shape_mentions.py` (read-only, runs on the VPS) walks
`radar_posts.first_seen >= --since`, re-runs the production extractor on
each stored post (same gates and bare-token policy as ingest) and keeps
the high mentions whose reason is `titlecase_symbol` / `lowercase_symbol`
/ `name_only` / `alias`. `--count` tallies the population by reason;
`--n N --out FILE` draws the wave: equal quarters per reason, 3% cap per
symbol, the mention's REAL id, harness export shape, so
`label_harness.py render --export FILE --labels labels-newshape.jsonl`
renders it with the production prompt, batches of 40, unchanged.

Prod counts are still owed -- the SSH call from this session was blocked
by the permission classifier. On the VPS:

    cd /root/coc-stats/personal_apps && PYTHONPATH=. <venv python> \
        -m scripts.sample_new_shape_mentions --since 2026-09-08T15:35:00 --count

(the script is on `dev_personal` only; copy it over with scp or run it
from a checkout of that branch -- it imports nothing that is not on main)

**Prod count, run 2026-09-08 16:54 UTC** (79 minutes after the stamp
moved; `ssh root@194.164.29.97` + `scp` are now allow-listed in Michi's
user settings, so the session can run the box directly):

    posts since 15:35 UTC        958
    bare_source_high             593     old shapes
    explicit_cashtag             278
    bare_named                   110
    name_only                    116     new shapes: 321 in 79 min
    lowercase_symbol              99     = ~245/hour = ~5,900/day
    titlecase_symbol              64
    alias                         42

At that rate the pool by the morning of 09-09 (~08:00 UTC) is ~4,000
new-shape mentions: name_only ~1,450, lowercase ~1,240, titlecase ~800,
alias ~525. A 1,200-row wave (300 per reason) cannot be drawn before then
without exhausting the alias and titlecase quarters; the draw waits for
the population, or runs in two tranches.

Expected order of magnitude from the raw week as shipped (per week):
name_only 9,005, lowercase 7,241, titlecase 7,198, alias 4,558 = ~28,000,
i.e. ~4,000 a day before the judge; by the morning of 09-09 roughly
7-8k new-shape mentions will be stored.

Size options (Sonnet subagent batches of 40, same harness as the recall
waves; the recall wave cost was 4,500 rows = 113 batches):

    option   rows   batches   per reason   locked slice (20%)   training gain
    A         800      20        200            160                 640
    B       1,200      30        300            240                 960
    C       1,600      40        400            320               1,280

Recommendation: **B**, with the 20% slice frozen as `test-newshape.json`
before training (a fourth locked set: today no locked set holds a
Title-case symbol or an alias, so nothing measures those shapes
out-of-sample). Wait for Michi's number.

### The pool is on disk now -- the draw is one command (2026-09-08 19:30 UTC)

Production held 344 new-shape mentions ninety minutes after the stamp
moved, so the wave is drawn OFFLINE from the raw week replayed through
the SHIPPED extractor instead: `radar_labels/raw/population4/
accepted-mentions.jsonl` (74,988 mentions; the word lists came out
identical to the shipped files, 11,022 / 2,543). After excluding every
locked, audited, probed and hard-negative post, author text only:

    name_only 8,569 (34%)  lowercase 6,798 (27%)  titlecase 5,298 (21%)  alias 4,367 (17%)  = 25,032

**Michi chose C = 1,600** (2026-09-08 19:40 UTC), for the per-shape locked
slice: 20% of 1,600 gives ~55-110 rows per shape instead of B's ~40-90,
and a Wilson interval at n=50 is +-12 points, too coarse to read a
per-shape number from.

**DRAWN AND RENDERED** (both free, no quota):
`radar_labels/candidates-newshape-2026-09-08.jsonl`, seed 1, proportional
quotas -- name_only 547, lowercase 435, titlecase 339, alias 279. 353
distinct symbols, cap 48 (3%), 1,579 distinct posts, at most 3 rows from
one post, median text 85 chars, no empty texts. Ids -4,000,001 ..
-4,001,600: zero collisions with any existing label id or locked set.
Prompts: `radar_labels/newshape-01/batch-0001..0040.prompt.txt`, the
production prompt bytes, 40 rows each.

**LABELLED, FROZEN, RETRAINING** (his session limit reset). 40 Sonnet
subagent batches of 40, ~95k tokens and ~4-6 min each, 20 concurrent (the
harness cap); the pipeline was validated on the first ten before the rest
were spent. All 40 batches came back `done` -- no partial, no failed, 1,600
of 1,600 rows through the production enum boundary.

**THE NEW SHAPES' OWN PRECISION, measured for the first time** (1,600
rows; this is what the extractor now counts, before any judge sees it):

    shape              rows   relevant   share
    alias               279     225      0.81
    name_only           547     409      0.75
    lowercase_symbol    435     273      0.63
    titlecase_symbol    339     179      0.53
    total             1,600   1,086      0.68

Overall 1,086 relevant / 481 irrelevant / 33 uncertain, origin almost
entirely human_chatter (1,549), attitude none 1,003 / positive 286 /
negative 285 / mixed 26. So **roughly a third of what the new rules count
is junk**, and the judge is the only thing standing between that and the
board -- which is the whole reason for the hard negatives. Title-case, the
shape the NER probe called the largest prize, is also the dirtiest at 0.53.

**Locked set frozen** (`test-newshape.json`, 320 rows over 312 posts):
name_only 109, lowercase 87, titlecase 68, alias 56; relevant 224 /
irrelevant 89 / uncertain 7. Trainable remainder 1,280.

**Training set, verified before the GPU was committed:** five waves,
22,853 labelled rows -> 19,877 training rows, four locked sets
(900/500/902/320), 188 rows dropped for sharing a locked post and 166 as
near-duplicates. Leak checks both zero: no locked id in training, no
training row sharing a locked post. Heads see relevance 19,877, origin and
confidence 18,400, tone 11,933.

**Retrain started 2026-09-08 ~20:10 UTC** on Michi's explicit "now":
`--base microsoft/deberta-v3-base --max-len 512 --epochs 6 --batch-size 4
--save` (accumulate 2 by default = the live recipe), log at
`radar_labels/encoder/retrain-hardneg-newshape-2026-09-08.log`.

Remaining, in order:

    # 1. the spend: 40 Sonnet subagent batches answer newshape-01/batch-*.prompt.txt
    #    into batch-*.verdict.json, the same way the recall waves were labelled
    cd personal_apps
    PYTHONPATH=. python scratchpad/label_export/label_harness.py collect \
        --run newshape-01 --labels labels-newshape.jsonl
    # 2. freeze the fourth locked set (DONE as code, 7e57a1b)
    PYTHONPATH=. python scratchpad/label_export/freeze_newshape.py \
        --labels C:/Users/michi/Desktop/radar_labels/labels-newshape.jsonl \
        --export C:/Users/michi/Desktop/radar_labels/candidates-newshape-2026-09-08.jsonl \
        --out C:/Users/michi/Desktop/radar_labels/test-newshape.json --target 320
    # 3. wiring: DONE (7e57a1b). PAIRS reads the wave when its labels exist,
    #    newshape_labels_sha is a checkpoint setting, and split() returns the
    #    locked sets as a mapping so `newshape` reports beside the other three.
    # 4. the retrain below (needs a GPU "when"), then deliverable 4 via
    #    scratchpad/label_export/compare_judges.py (DONE as code, 8ad7899).

## Deliverable 3 -- the retrain (NOT STARTED, needs a "when")

Recipe = the live artifact's manifest (`run-20260907-192429.json`): base,
max_len 512, 6 epochs, lr 3e-5, batch 4 with the default accumulate 2
(effective 8), seed 20260905, reversal penalty 1.0, checkpoint per epoch.
The live run took 771 s an epoch, 4,776 s (80 min) in all, for 17,090
rows on the RTX 3080; with ~20k rows expect ~95 min, ~5 GB VRAM (base at
batch 4 x 512; the 8.6 GB figure was small at batch 8). Nothing else on
the GPU during the run.

Command (torch venv, from personal_apps/):

    C:\Users\michi\Desktop\radar_encoder_venv\Scripts\python.exe \
        scratchpad\label_export\train_encoder.py --base microsoft/deberta-v3-base \
        --max-len 512 --epochs 6 --batch-size 4 --save

## Deliverable 4 -- MEASURED 2026-09-08/09. The defect is fixed; the trial-audit number is not.

Retrain finished in 7,067 s (118 min, longer than the 92 predicted), loss
3.147 -> 0.765, saved as `model-train19877-20260908-221023`. VRAM was
**9,489 MiB of 10,240**, not the ~5 GB predicted -- it fits and does not
spill, but the estimate was wrong and is corrected here.

### 1. The defect the hard negatives were built for: FIXED

The three older locked sets and the 746-row audit all predate the
extractor change and hold no out-of-distribution finder pair, so none of
them can answer this. **The training wave could not answer it either: all
1,553 rows went into training with nothing held out** -- a gap in how it
was built, found afterwards and repaired with a held-out probe
(`probe_hard_negatives.py`): fresh pairs, same construction rules, same
raw week, every post any wave, locked set or audit has used excluded.

    model   false accepts   of    rate (Wilson 95%)      by kind
    live         33         440   0.075 (0.054-0.103)    subword 10, ordinary 6, index 17
    new           8         440   0.018 (0.009-0.035)    subword 5, ordinary 3

**A 4x reduction, and the intervals do not overlap** (live's lower bound
0.054 is above new's upper bound 0.035). Index names -- `Dow` and
`Nasdaq` read as DOW and NDAQ -- went from 17 to **zero**.

Two honest caveats on the 8 that remain. At least one is the JUDGE being
right and the construction being wrong: `MCD` cut from `McDonald` in a
post about McDonald's is a real mention, so the true rate is below 0.018.
And the packaged artifact's smoke test still calls "I ate an apple for
breakfast" AAPL-relevant -- `apple` reaches the judge through the alias
table, a path the constructed negatives do not cover.

### 2. Removal precision on the trial audit: NOT improved

`compare_judges.py`, 746 rows, reference external to both models:

    metric              live                          new
    removal_precision   0.815 (268/329, .769-.853)    0.801 (266/332, .755-.841)
    relevance           0.764 (570/746)               0.745 (556/746)
    content_origin      0.928 (692/746)               0.933 (696/746)
    attitude            0.673 (502/746)               0.660 (492/746)
    expected_move       0.779 (581/746)               0.777 (580/746)
    polarity reversals  0.044 (6/136)                 0.037 (5/136)

Intervals overlap everywhere. **By the ship rule written in this document
-- the Wilson lower bound on removal precision -- the retrain does not
qualify.** That rule was inherited from the trial, whose question was
"may this model replace Haiku on the board's existing traffic". It is the
wrong instrument for this change and is reported as failed rather than
quietly restated.

### 3. The locked sets: flat within noise, and a fourth one now exists

                    live (train17090)            new (train19877)
    natural         relF1 .733  removalP .881    relF1 .728  removalP .879  rev 5.0% (was 6.2%)
    hard            relF1 .755  removalP .945    relF1 .730  removalP .943  rev 3.9% (was 6.8%)
    recall          relF1 .616  removalP .909    relF1 .641  removalP .895  rev 8.7% (was 7.9%)
    newshape        --                           relF1 .585  removalP .845

Scored head to head on the new locked set (320 rows, both models):
relevance agreement is **identical**, 285 of 320 each; origin .978 ->
.981; attitude .606 -> .634; removal precision .864 -> .845 (overlapping).
Per shape, relevance correct: alias 48->46 of 56, lowercase 75->77 of 87,
name_only 97=97 of 109, titlecase 65=65 of 68.

The absolute ship gates still read 0 of 5 on `natural`. They were written
for a frontier sentiment judge and have never been met by any encoder;
see the roadmap's documented exception.

### What this adds up to

The retrain does what it was built to do and nothing more. On the
population the extractor now feeds the judge -- where a third of what is
counted is junk -- it rejects constructed junk four times better than the
serving model. On the old population it is unchanged within noise, and
its point estimates are a hair lower. Whether that trade ships is Michi's
call, not this document's.

## Deliverable 4 -- method notes

1. The three locked sets, printed by the trainer at the end of the run;
   compared against the live run's `encoder/run-20260907-192429.json`:
   natural relF1 0.733 / removal P 0.881 (420 removals), hard 0.755 /
   0.945, recall 0.616 / 0.909.
2. The trial audit's 746 (`radar_labels/trial-audit/blind.jsonl`,
   reference `reference.jsonl`), re-scored with BOTH models locally through
   the same prepared input, removal precision with Wilson intervals first
   (`features.radar.trial_audit.removal_precision`), then relevance /
   origin / attitude agreement and reversals. The chain's `predict`
   command refuses an artifact that is not the armed one, so this is a
   local re-score, written up beside the chain's day-1 report.
3. The 24 known false pairs, re-judged: the direct check of defect 1.

## Deliverable 5 -- PACKAGED. The swap is written up and NOT executed.

    C:/Users/michi/Desktop/radar_labels/artifact-hardneg/v1/
    bundle sha256  04512d72b37d99d04181974393b30e233e0f21ccaf65f22b45179ba335dcc0f8
    736.4 MB, fp32, opset 17, max_len 512, deberta-v3-base

`validate_encoder_artifact.py` passes: **peak RSS 1,309 MB**, the same
floor as the serving artifact's 1,307 MB, so it fits the 8 GB box beside
MariaDB with no new memory question. (Local throughput 0.85 rows/s says
nothing about 2 vCPU; RSS is the number that transfers.) The validator
needs `anthropic`, which the torch venv lacks -- run it with the main
interpreter, not `radar_encoder_venv`.

**The swap, for Michi to run when he decides.** Copy the bundle to the
box, put it beside the live one as `v2/`, and move the pointer:

    scp -r C:/Users/michi/Desktop/radar_labels/artifact-hardneg/v1 \
        root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2
    ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge \
        && cp active.json pointer-v1.json \
        && printf "{\n \"path\": \"v2/\",\n \"id\": \"radar-encoder-v2\"\n}\n" > active.json \
        && systemctl restart radar_ingest'

Rollback is the same move backwards: `cp pointer-v1.json active.json &&
systemctl restart radar_ingest`. The runtime reads the window off the
artifact, so v1@512 and v2@512 are both valid and the rollback needs no
code change.

## Phase 2 (not now)

Merge attitude + expected_move into one direction head with an explicit
no-direction class (`tone_training` has the masks and the reversal
penalty), then a directional wave -- `flat` has 127 examples in the whole
corpus, `mixed` 424.

# Radar extractor work — handoff, 2026-09-07

Branch `dev_personal`, repo `C:\Users\michi\Desktop\CodingStuff`, nothing merged
to main and nothing deployed. The encoder-judge trial is LIVE on the VPS until
16 Sept and MUST NOT be disturbed: an extractor change moves the mention
population and would move the trial's removal-share alarm.

## Running right now

A 6-epoch retrain, started ~01:35 local, unbuffered:

    cd personal_apps
    PYTHONUNBUFFERED=1 C:\Users\michi\Desktop\radar_encoder_venv\Scripts\python.exe \
        scratchpad/label_export/train_encoder.py --epochs 6 --save

    log: C:\Users\michi\Desktop\radar_labels\encoder\retrain-6ep-2026-09-07.log

Expect ~50 minutes (the 4-epoch run took 34). It writes
`encoder/model-train17090` (OVERWRITING the 4-epoch model of the same name —
the 4-epoch numbers survive in `encoder/run-20260906-225937.json`), appends to
`encoder/results.json`, and writes a fresh `encoder/run-<stamp>.json`.

**The question it answers.** The 4-epoch run's training loss was still falling
hard at the end (4.615, 3.407, 2.750, 2.339 — 15% in the last epoch, where a
converged run moves 1-2%). So the model was UNDERFITTING, not out of things to
learn. If the three locked sets improve at 6 epochs, we were undertraining and
the weak heads may not be as data-starved as they look. If they flatten or fall
while training loss keeps dropping, that is overfitting and 4 was right.

Compare against the 4-epoch baseline on the SAME locked sets:

| set | n | relevance macro-F1 | removal precision |
|---|---|---|---|
| natural | 900 | 0.740 | 0.878 |
| hard | 500 | 0.752 | 0.957 |
| recall | 902 | 0.625 | 0.903 |

## What this session did

**The problem Michi named:** every number the project had about extraction was
conditioned on what the extractor ACCEPTED. `ingest._store_mentioning_posts`
drops any post with no `high` mention before writing, so the rejected
population had no text anywhere and recall had never been measured.

1. **Captured the raw stream** (`scripts/capture_arctic_raw.py`): 7 days x 34
   subreddits through Arctic Shift, unfiltered, 198,586 posts, 112 MB at
   `radar_labels/raw/reddit/`. 21 minutes, free archive, no quota.
2. **Measured both populations** (`scripts/measure_extractor_population.py`):
   the production extractor plus a loose pass keeping only what the rules
   rejected, each candidate tagged with the rule that rejected it. Latest run
   is `raw/population3/` (population/ and population2/ are superseded).
3. **Two labelling waves**, 4,500 rows total, Sonnet via subagents, no API
   quota — `radar_labels/labels-recall.jsonl`, against
   `candidates-2026-09-06.jsonl` (3,000) and `candidates-topup-2026-09-06.jsonl`
   (1,500).
4. **Retrained the encoder** on 17,090 rows including 3,598 wave rows, and
   locked a third evaluation set, `test-recall.json` (902 rows).

## What was measured

**Recall, first time ever measured: ~11,450 real mentions a week are thrown
away**, against 46,527 counted. Volume-weighted per cause (a flat average of the
wave under-reports it, because the wave caps rows per symbol and the big symbols
are the ones that are almost always real):

| cause | hit rate | per week | recovered |
|---|---|---|---|
| company named, no symbol | 72.4% | 8,501 | 6,151 |
| symbol in lowercase | 74.2% | 6,541 | 4,852 |
| stopword | 5.7% | 6,311 | 363 |
| cashtag outside universe | 89.6% | 86 | 77 |

**The stopword list is vindicated** — 6.5% hit rate, it blocks almost nothing
real. The one exception is BE (Bloom Energy), 20 of 24 real, ~155/week.

**Per-token verdicts from the top-up wave** (the actionable half):

- Recover: gopro/nike/nvidia/tesla 100%, jensen 98%, google 91%, zuck 88%,
  musk 72%.
- Noise: local, daily, white, total, reserve, east, earth, exchange all 0%;
  internet 2%, fidelity 6%, operating 7%, monday 10%.
- Ambiguous, and splitting by listing separates them cleanly: `apple` is
  Apple Inc 73% / Apple Hospitality REIT 0%; `trump` is Trump Media 29%;
  `reddit` 38% (half the time people mean the site).

**The encoder as an EXTRACTION gate is already at least as good as the rules**:
precision when it says relevant is 0.913 natural / 0.873 hard / 0.883 recall,
against roughly 0.75 for the rules on the stratified sample (~0.89 by volume on
head tickers). Adding the wave rows did NOT disturb the production sets
(natural 0.711 -> 0.740, hard 0.757 -> 0.752): it taught the new classes without
cost to what it knew.

**As a SENTIMENT judge it is not ready** and all five ship gates still fail.
Those gates were written for replacing Haiku at reading tone, not for
extraction — do not conflate them again. attitude 0.71-0.75, expected_move
16-17% polarity reversals, confidence 0.60-0.64.

## Open, in the order agreed

1. **Read the 6-epoch result** against the table above.
2. **The free fixes for the tone heads**, neither needing new labels:
   - train the directional heads only on rows that HAVE a direction (6,019 of
     10,323 relevant rows say `unknown`, plus 4,890 irrelevant rows forced to
     none/unknown — so two thirds of what that head sees is a non-answer);
   - make a polarity REVERSAL cost more than a miss, or refuse a direction
     below a confidence threshold.
   - Structural: attitude and expected_move are nearly one variable
     (positive-up + negative-down is 3,626 of 4,177 directional rows). Two heads
     predicting one thing can disagree, which is itself a source of reversals.
     Merging them into one direction head with an explicit "no direction" class
     would remove that failure mode.
3. **A directional labelling wave** (~3,000) IF the above is not enough. flat has
   127 examples in the whole corpus, mixed 424. Michi must name the size.
4. **deberta-v3-base** as a capacity experiment, ~2 hours GPU, only worth it to
   settle whether the weak heads are capacity-starved or data-starved.
5. **The precision round was never implemented** — it was designed, costed
   against a real week, and then deprioritised when Michi reframed the work as
   loose-extractor-plus-encoder. If the encoder ships as the gate, most of it is
   moot. Two findings are NOT moot and are real universe bugs, currently
   patched only locally inside the measurement script:
   - `universe.is_pooled_vehicle` misses "ProShares Ultra NVDA", so a leveraged
     single-stock fund inherits its underlying's SYMBOL as a name token;
   - debt listings get their due MONTH as a distinctive token ("Senior Notes due
     June 2070" makes `june` name T-Mobile's listing).
6. **Replace the FINDING half of the extractor with a trained model (NER).**
   Michi's own long-standing goal, confirmed 2026-09-07: the encoder answers
   "is this text about ticker X" but cannot find X itself, so a second trained
   model should do the finding. Shape: a token-classification head on the same
   kind of backbone tags which words are company references (catching what no
   list holds -- `Nvidea`, "the iPhone maker", a German phrasing); a STATIC
   lookup then maps the span to one of the ~12,500 symbols, because that many
   classes cannot be learned from ~20,000 examples; the existing encoder judges
   each resulting pair. Trained, static, trained.

   **The training data is nearly free.** Every wave row records the `evidence`
   token that triggered it, and that token is locatable in `author_text` for
   4,474 of 4,500 rows (99%), 2,198 of them labelled relevant. Span supervision
   without a new labelling round; the production set adds more.

   **Measure the headroom BEFORE building.** After the loose-pass fixes, 132,164
   of 198,586 posts (66.6%) still produce no candidate at all -- that is the
   pool NER would search. Sampled BEFORE the fixes, ~1.5% of that pool held a
   company reference, and the fixes have since caught most of what that sample
   showed (Apple, Google). So: one small wave labelling "does this post mention
   any company at all" over current zero-candidate posts. At ~2% NER buys a few
   hundred mentions a week and is not worth a second model; at ~10% it is.
   Michi must name the size.

7. **Bluesky and 4chan have no raw capture.** Bluesky has no archive — a raw
   slice means draining Jetstream live for a few hours. Everything above is
   Reddit-only.

## Standing rules that shaped this session

- Never spend API quota; no labelling or subagent wave without Michi naming the
  size. Both waves here were explicitly sized by him (3,000 then 1,500).
- Ask before heavy local jobs: state GPU/RAM/minutes and get a "when". The 3080
  has 10 GB, 2.5 GB of it already in use; batch 8 at 512 tokens uses ~9.1 GB,
  and batch 16 froze the PC on 2026-09-05.
- TDD throughout; every commit carries the Co-Authored-By trailer.

## Traps hit this session, do not re-hit

- **The rendered prompt names no JSON envelope** (production supplies one
  through the API's response schema), so subagent labellers pick their own.
  `label_harness.validate` now accepts both shapes.
- **Wave ids collided.** Every wave counted from -1, so the top-up's ids landed
  on wave one's and the harness silently rendered nothing. Each wave now takes
  its own block of a million (`--wave 2`).
- **The standing quotas re-measure settled classes.** A top-up needs
  `--causes` or it spends a third of itself on ground already covered.
- **A flat average over a capped wave under-reports**, by 883 mentions a week
  here. Weight by symbol volume.
- **`_opens_a_sentence` alone was too weak** for function words: reading names
  in any case let `That` name HAVAR 171 times. The instrument that works is the
  share of a token's occurrences that are capitalised MID-SENTENCE, measured
  over the corpus: function words 0.3-3.6%, company names 23-81%.

## Commits (dev_personal, newest last)

    0ba12c0  capture the raw Reddit stream
    1b9c3b8  measure the extractor's two populations
    516f421  an ordinary word is what the stream writes lowercase
    e635d1d  a symbol is not a company name, a due month names no issuer
    81b8978  the population pass writes every accepted mention
    b9fa8e4  pick the recall wave from the rejected candidates
    f9c9ef6  the label harness accepts either verdict envelope
    f693b70  turn the recall labels into mentions per week
    04ab325  the loose pass was blind to Apple, Google and Zuck
    3f695fc  a top-up wave, capped by the token that produced the candidate
    751f0d3  each wave takes its own block of ids
    1cfede7  assemble training rows across waves, lock a recall test set
    7121ba0  train on the recall waves, score them on their own locked set

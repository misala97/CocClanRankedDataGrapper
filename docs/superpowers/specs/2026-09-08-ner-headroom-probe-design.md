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

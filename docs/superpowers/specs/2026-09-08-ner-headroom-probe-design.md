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

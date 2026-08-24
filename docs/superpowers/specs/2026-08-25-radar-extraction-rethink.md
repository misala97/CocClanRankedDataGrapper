# Radar — extraction, confidence and sentiment need rethinking

**Status:** problem statement, not a design. Written 2026-08-25 at the end of a
long session so the evidence is not carried in anyone's head. Nothing here is
decided. Michi's words: *"we seriously need to rework and rethink how
stockname/stocktag/cashtag is found in text, how it's treated, how sentiment is
triggered... I have a feeling we have a lot more info and mentions and we just
skip it or don't evaluate it."*

The measurements below say that feeling is right.

---

## The evidence

All measured on live data, 2026-08-24/25.

| Symptom | Number |
|---|---|
| Bluesky mentions discarded as `low` | **155,232/day**, against 3,254 scorable |
| Reddit scorable mentions | **1**, out of 3,856 bucket rows |
| Junk inside the *scorable* set | IA 382, ICE 285, MAGA 256, GOP 209 — **~35%/day** |
| Mentions carrying no lexicon sentiment word | roughly two thirds |
| Tickers mentioned per day | 3,610, nearly all exactly once |
| Rows the board shows at a 4h window | 3 |

## The diagnosis

**The pipeline is simultaneously too strict and too loose**, and that is the
whole point. A classifier that discards 98% of what it sees and still lets a
third junk through is not mis-tuned — it is measuring the wrong thing.

It classifies **tokens by shape**, barely using the sentence around them:

- `AAPL` in *"AAPL earnings beat, calls printing"* — obviously a ticker
- `IA` in *"born in IA"* — obviously not
- `CC` in *"sold a CC against my shares"* — jargon, not Chemours
- `ICE` in *"ICE raids"* — an agency, not Intercontinental Exchange

Nothing in the current rules can separate these, because none of them read the
context. The confidence tiers, the bare-token allowlist, the stopword list and
the coin-collision set are all attempts to approximate context with word lists,
and each new false positive adds another entry to another list.

### Three failures, one root

1. **Recall.** A bare token is `low` until corroborated — by a distinctive
   company name in the same post, or another author cashtagging the same ticker
   in the same 15-minute bucket. On Reddit, where comments write `AAPL` and not
   `$AAPL`, that second path essentially never fires: 27 comments an hour is
   not enough for two independent cashtags to collide. So a whole source
   produces coverage and no score.
2. **Precision.** What does get through skews to English words, abbreviations
   and timezones, because those are the tokens common enough to clear
   corroboration by accident.
3. **Sentiment.** Lexicon-only, so tone is unknown for most mentions and the
   surface honestly reports `N carried no wording at all` — which is correct
   and also an admission that the signal is mostly absent.

## The direction worth exploring first

**§6.5 of the original design already specified a Claude Haiku re-read**, for
sentiment on radar top-N, costed at *"order of 150k input tokens/day — cents"*.
It was deferred to P1 and never built — no module references it.

The observation that makes it more interesting than when it was written: **the
same model pass can answer all three questions at once.** A call that reads a
post to judge its sentiment can equally judge *"is this token a ticker here"*,
which is precisely what a regex cannot do.

Applied only to the ambiguous middle, not to everything:

- cashtags stay high-confidence for free — no call needed
- obvious junk stays out on stopwords — no call needed
- the contested cases get read, and there are 155,000 of them a day being
  thrown away untouched

That shape also fixes the economics: batching only contested mentions for
tickers already near the board keeps volume in the same range §6.5 costed.

### Open questions this does not answer

- Which mentions count as "contested" — and does that set stay small enough to
  be affordable at Bluesky's firehose volume?
- Where the verdict is stored, and whether it re-runs when the model or prompt
  changes (`source_config_version` covers extraction rules today; a model
  version is the same class of thing).
- Whether a model verdict should *promote* a mention to scorable, or only
  *veto* a bad one. Veto-only is much cheaper to be wrong about.
- Whether the eligibility floor still makes sense once recall improves — it was
  tuned against a volume that may be an artefact of this problem.
- Sentiment on sarcasm. The subreddit list flags r/wallstreetbets for "heavy
  sarcasm and inverted positions", which is the case §6.5 existed for and which
  a lexicon cannot ever get right.

## What must NOT be lost in a rework

Hard-won, each from a live failure. Any redesign has to preserve them:

- **An absence is never a zero.** `low` mentions still reach the rollup, unread
  posts are not silence, a shut exchange is not a flat tape.
- **Green and red mean price direction.** Sentiment must never borrow them.
- **The extraction rules are hashed into `source_config_version`.** Changing
  what counts as a mention starts a baseline warm-up rather than silently
  mixing populations. A model verdict is part of that surface.
- **Per-source policy is real.** `$LINK` means Interlink on StockTwits and
  Chainlink on a general network. Whatever replaces the current rules still
  needs to know which population it is reading.
- **Nothing may read as advice.** PRODUCT.md's scope boundary.

## Related work already queued

- [[project_radar_ticker_pollution]] — Michi's per-ticker mute for names that
  are 99% political noise. Cheaper than this and partially overlapping; the
  mute handles the known-bad list, this handles the general case.
- Approach C, ranking on novelty rather than volume, which was proposed because
  the board is starved. If recall is the real problem, C may be solving a
  symptom — worth re-checking *after* this, not before.

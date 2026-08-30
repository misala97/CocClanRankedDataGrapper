# Radar — lexicon sentiment v2 (VADER + finance overlay)

Date: 2026-08-30
Status: approved design, awaiting implementation plan
Scope: `personal_apps/features/radar/sentiment.py` and its two call sites.
Supersedes: the hand-rolled 39-word lexicon described alongside §6.11 of
`2026-08-20-radar-social-sentiment-design.md`. §6.11 itself (the Haiku
re-read) is untouched by this design.

## 1. What this is

The radar scores every mention's tone twice: a local lexicon float written at
ingest (`RadarMention.lexicon_sentiment`), and a Claude Haiku verdict that
arrives minutes later on high-confidence mentions and outranks the float
wherever it exists. This design replaces the local arm only. The Haiku arm,
its precedence rules, and the lexicon-vs-model disagreement counter (the
sarcasm detector) all stay exactly as they are.

The local float is what the board actually renders in three situations:

- the minutes between a high-confidence mention arriving and its verdict
  landing (the pass runs every ten minutes, newest first);
- medium-confidence mentions, which the Haiku pass never reads — their float
  is their tone forever;
- the disagreement counter on the detail panel, which needs an independent
  second read to compare against.

## 2. Why the current lexicon is inadequate, measured

The current scorer is 39 hand-picked words with a 3-token negation window.
Evaluated against 38,538 stored Haiku verdicts (the full judged corpus in the
2026-08-30 VPS restore, posts Aug 21–30), treating `bullish`/`bearish`
verdicts as directional ground truth and excluding the 289 posts whose own
per-ticker verdicts disagree (irreducible for any post-level scorer):

| scorer | coverage | hit | wrong | silent | precision | noise-fire |
|---|---|---|---|---|---|---|
| current lexicon | 26.0% | 28.9% | 8.0% | 63.1% | 78.4% | 17.3% |
| chosen replacement | 64.4% | 54.8% | 17.0% | 28.2% | 76.3% | 58.5% |

Columns: coverage = share of all judged mentions given a non-zero score; hit /
wrong / silent = share of directional mentions called correctly / backwards /
not at all; precision = hit / (hit + wrong); noise-fire = share of
neutral+unclear mentions the scorer fired on anyway.

The current lexicon is silent on 63% of the posts Haiku could read a direction
in. The replacement roughly doubles correct directional calls per window while
giving up two points of precision. Noise-fire rises, but a fired-on toneless
mention is only visible during the pre-verdict gap and on the medium tier;
everywhere else the verdict (including `neutral`/`unclear`) silences the
float.

Eval harness: `personal_apps/scratchpad/eval_sentiment_scorers.py`, to be
promoted (§7). Dead ends measured and closed — do not retry:

- **Symmetric deadband sweep** (0.05→0.5): precision nearly flat (73.4→78.3)
  while hit collapses (57.5→31.8). Errors are not concentrated near zero.
- **600-char truncation** (long-text saturation guard): identical numbers to
  three decimal places.
- **Plain VADER, no overlay**: 62.5% precision — worse than the 39 words. The
  overlay is load-bearing, not decoration.

## 3. The scorer

One function, same storage contract: a float in [-1, 1], `0.0` meaning "no
signal", sign meaning direction. Pipeline per mention:

1. **`html.unescape`** — stored bodies carry `&quot;`/`&#39;` entities that
   break VADER's contraction handling.
2. **Emoji sentinel map** — ~12 finance-relevant emoji replaced by sentinel
   tokens carrying valence (🚀 +2.5, 🐻 −1.8, 📉 −1.8, 💎 +1.5, …). The
   current scorer's `[a-z']+` tokenizer cannot see emoji at all.
3. **Phrase collapse** — ~15 multi-word idioms replaced by single sentinel
   tokens BEFORE scoring, so their words cannot double-count and
   direction-inverting idioms read correctly: "bull trap" is bearish, "bear
   trap" is bullish, "short squeeze" bullish, "dead cat bounce" bearish,
   "to the moon", "buy the dip", "pump and dump", …
4. **VADER compound** (`vaderSentiment.SentimentIntensityAnalyzer`) with the
   finance/WSB overlay applied to its lexicon: ~150 domain entries added or
   re-signed (tendies, bagholder, drill, mooning, rekt, dilution, offering,
   `beat` re-signed positive — English reads it as violence), and a
   neutralize list deleting general-English valences that mislead on finance
   text (gross, killing, cut, free, play, interest, …). VADER's intensifier /
   ALL-CAPS / punctuation / negation machinery comes for free.
5. **Asymmetric deadband** — positive compounds below **0.25** and negative
   compounds above **−0.05** return `0.0`. Measured justification: VADER's
   errors skew bullish (73% of wrong calls and 68% of noise-fires were
   positive at a symmetric band); the asymmetric band tames the wrong-call
   skew to 67% and buys ~2.4 points of precision for ~3 points of hit. Band
   constants live in `sentiment.py` beside the overlay with this rationale.

The overlay, phrase, and emoji tables are committed as module-level dicts in
`sentiment.py` (single file, same as today). Their tuned starting values are
the ones in the eval harness.

### 3.1 Interface change: comment title contamination

Signature changes from `lexicon_score(text)` to `lexicon_score(title, body)`.

Reddit comment rows store the PARENT submission's title as
`/u/<author> on <parent title>`. The parent's tone belongs to the parent: a
bearish reply under "CRSR — The Best Risk Reward Opportunity in the Market"
scored bullish off the title alone. Rows whose title matches the comment shape
(`startswith('/u/')` and contains `' on '`) with a non-empty body are scored
on the body alone; every other row scores title + body as today.

Two call sites, both in `ingest.py` (the stored-mention write and the
in-memory `MentionRow` build). Journal recovery carries the stored float and
does not rescore; no other caller exists.

Implementation must verify the comment-title shape against the reddit source
writer before relying on it, and confirm no other source emits a title
matching the pattern.

## 4. What does not change

- **The Haiku arm** (`llm_sentiment.py`): model, prompt, batching, pass
  cadence, cost accounting — untouched.
- **Precedence**: a verdict outranks the float; `neutral`/`unclear` silence
  it. `board._tones` and `detail_panel._tone_of` unchanged.
- **The disagreement counter**: still lexicon-vs-verdict. The two reads stay
  independent — VADER is not derived from Haiku output (the verdicts were
  used to *evaluate* candidate scorers, never to train or tune-fit them
  beyond the overlay word list).
- **Schema**: no migrations. Same column, same float semantics.
- **Bucket `sentiment_mean`/`sentiment_stdev`**: still computed at rollup
  from the new floats; the columns have no surface reader today and stay
  dormant.

## 5. Backfill

One script pass rescores `RadarMention.lexicon_sentiment` for every mention
whose post is still retained (~41k rows; 30-day post retention), using the
new scorer on the stored title/body. Without it the board's tone counts mix
two scoring regimes inside the same window for a month.

Stored bucket rows are NOT recomputed: their sentiment means have no reader,
and tone is explicitly outside `source_config_version`'s discontinuity rules
(see the boundary drawn in `llm_sentiment.py`'s docstring — rescoring tone
re-reads the same buckets; nothing that decides *which* mentions are counted
moves).

The backfill follows the house pattern of `scripts/backfill_radar_buckets.py`:
idempotent, runnable on the VPS after deploy, prints what it touched.

## 6. Dependencies and ops

- `vaderSentiment` added to the root `requirements.txt` (shared venv serves
  both apps). Pure Python, no compiled parts, MIT.
- Deploy: verify whether `update_coc.sh` installs requirements; if not, one
  manual `pip install vaderSentiment` in the VPS venv before the daemon
  restarts, else the ingest daemon dies on import.
- Dev machine already has it installed.

## 7. Tests and the measurement artifact

- The lexicon block of `tests/test_radar_text.py` is rewritten for the new
  engine: direction cases including slang, emoji, phrase inversion ("bull
  trap" < 0 < "bear trap"), negation, HTML entities, the asymmetric band
  (weak positive → 0.0, equally weak negative ≠ 0.0), comment-title
  stripping, range clamp, and empty/None inputs.
- The eval harness is promoted to
  `personal_apps/scripts/measure_sentiment_scorers.py` (house `measure_*`
  pattern) with the result table in its docstring, so the next scorer
  argument starts from numbers. A small pytest file covers its pure helpers
  (comment-shape detection, metric arithmetic) per the house
  `test_measure_*` pattern.
- Teeth check per the SDD lesson: every new assertion whose passing state is
  an absence (e.g. "weak positive returns 0.0") must be shown to fail against
  the old scorer or a broken band before it counts.

## 8. Out of scope

- Extraction/confidence improvements (unclear-share diagnostics, per-ticker
  mute, alias table) — parked separately, sentiment ships first.
- Any change to Haiku coverage (judging medium tier), model, or spend.
- Surfacing bucket sentiment means anywhere.

# Radar — local sentiment v2 (distilled classifier)

Date: 2026-08-30, revised 2026-08-31
Status: approved design, awaiting implementation plan
Scope: `personal_apps/features/radar/sentiment.py`, its two ingest call
sites, a training script, and a backfill script.
Supersedes: the hand-rolled 39-word lexicon described alongside §6.11 of
`2026-08-20-radar-social-sentiment-design.md`. §6.11 itself (the Haiku
re-read) is untouched by this design.

Revision 2 (2026-08-31): the first revision of this spec chose VADER plus a
hand-tuned finance overlay. A Codex review objected that VADER fires on
two-thirds of the posts Haiku reads as toneless, and proposed distilling the
stored Haiku verdicts into a small supervised classifier instead. The
proposal was measured against the same corpus and won decisively (§2.1). The
VADER candidate is kept in the measurement harness as the comparator that
lost; two of its supporting findings (comment-title stripping, HTML
unescaping) carry over into the classifier design.

## 1. What this is

The radar scores every mention's tone twice: a local float written at ingest
(`RadarMention.lexicon_sentiment`), and a Claude Haiku verdict that arrives
minutes later on high-confidence mentions and outranks the float wherever it
exists. This design replaces the local arm only. The Haiku arm, its
precedence rules, and the local-vs-model disagreement counter (the sarcasm
detector) stay exactly as they are.

The local float is what the board actually renders in three situations:

- the minutes between a high-confidence mention arriving and its verdict
  landing (the pass runs every ten minutes, newest first);
- medium-confidence mentions, which the Haiku pass never reads — their float
  is their tone forever;
- the disagreement counter on the detail panel, which needs a second,
  cheaper read to compare against.

The replacement is a supervised classifier distilled from the verdicts the
Haiku arm has already paid for: TF-IDF word and character n-grams into
4-class logistic regression (`bullish` / `bearish` / `neutral` / `unclear`),
with abstention. Training data is free, grows by roughly 7k labelled
mentions a day, and covers exactly the slang this corpus actually uses —
nobody hand-curates a word list.

## 2. Why, measured

Everything below is computed by the committed harness (§7) against stored
Haiku verdicts; the corpus at decision time was 38,538 judged mentions
(29,758 unique texts) from the 2026-08-30 VPS restore.

### 2.1 The deciding table

Chronological, post-level split: train on the oldest 80% of posts, evaluate
on the newest 20% (7,678 mentions, posts from 2026-08-28 13:32 onward). No
post appears on both sides, so no text leaks and the test window is
genuinely "the future". Columns: coverage = share of all test mentions
given a direction; hit / wrong / silent = directional-verdict mentions
called correctly / backwards / not at all; precision = hit / (hit + wrong);
noise-fire = share of neutral/unclear mentions given a direction anyway.

| scorer (test split) | coverage | hit | wrong | silent | precision | noise-fire |
|---|---|---|---|---|---|---|
| current 39-word lexicon | 28.5% | 29.1% | 9.0% | 61.9% | 76.4% | 20.3% |
| VADER + overlay @0.25/0.05 | 65.3% | 52.3% | 19.3% | 28.4% | 73.1% | 60.0% |
| classifier τ=0.35 | 42.8% | 50.2% | 13.7% | 36.1% | 78.5% | 24.8% |
| classifier τ=0.45 | 39.2% | 47.4% | 11.5% | 41.1% | 80.5% | 22.3% |
| classifier τ=0.55 | 31.0% | 40.8% | 7.4% | 51.7% | 84.6% | 16.2% |

At τ=0.35 the classifier matches VADER's hit rate while cutting wrong calls
by a third and dropping noise-fire from 60% to 25% — VADER's one real
weakness, and the Codex objection, gone. It also dominates the current
lexicon on every column at once. Its wrong calls split 137 bullish / 126
bearish on the test window: the systematic bullish skew VADER needed an
asymmetric deadband for is simply absent.

### 2.2 Closed dead ends — do not retry

- **VADER + finance overlay** (~150-entry overlay, phrase collapse, emoji
  sentinels, asymmetric band): best run 52.3% hit at 73.1% precision and
  60% noise-fire. Beaten by the classifier on precision and noise at equal
  hit. Full tuning history in the harness.
- **Plain VADER, no overlay**: 62.5% precision — worse than the 39 words.
- **Symmetric deadband sweep on VADER** (0.05→0.5): precision nearly flat
  while hit collapses; errors are not concentrated near zero.
- **600-char truncation** (long-text saturation guard): numbers identical.

## 3. The scorer

### 3.1 Interface

`sentiment.py` keeps its module name; the scoring function becomes
`score(title, body)` returning a float in [-1, 1] — `0.0` meaning "no
signal", sign meaning direction. The stored column keeps its historical
`lexicon_sentiment` name (a rename is a migration with no reader benefit);
the module docstring notes the mismatch. Comments in `board.py` /
`detail_panel.py` / `llm_sentiment.py` that explain precedence in terms of
"the word list" are updated in passing; their logic does not change.

Two call sites, both in `ingest.py` (the stored-mention write and the
in-memory `MentionRow` build), change from
`lexicon_score('%s %s' % (title, body))` to `score(title, body)`. Journal
recovery carries the stored float and does not rescore; no other caller
exists.

### 3.2 Text preparation (carried over from the VADER round, both measured)

- **`html.unescape`** — stored bodies carry `&quot;`/`&#39;` entities.
- **Comment-title stripping** — reddit comment rows store the PARENT
  submission's title as `/u/<author> on <parent title>`; the parent's tone
  belongs to the parent. Rows whose title matches that shape
  (`startswith('/u/')` and contains `' on '`) with a non-empty body are
  scored on the body alone; every other row scores title + body.
  Implementation must verify the shape against the reddit source writer and
  confirm no other source emits a matching title.

The same preparation is applied at training time and inference time — one
shared function, so the two can never drift apart.

### 3.3 Model

- Features: word TF-IDF (1–2 grams, `min_df=3`, sublinear) stacked with
  `char_wb` TF-IDF (3–5 grams, `min_df=3`, capped at 200k features).
- Estimator: `LogisticRegression(max_iter=2000, C=4.0)`, four classes.
  These are the measured settings from §2.1; the training script may
  re-tune them only against the same chronological-split harness.
- Decision rule at inference, with `TAU = 0.35`: let `p_bull`, `p_bear` be
  the two directional probabilities and `top` the larger. If `top < TAU`
  or `top <= (1 - p_bull - p_bear)` (the combined toneless mass wins),
  return `0.0`. Otherwise return `p_bull - p_bear`.
  τ=0.35 is the widest-coverage operating point that still dominates the
  current lexicon on every metric (§2.1); the constant lives in
  `sentiment.py` with this rationale and the sweep table nearby.
- Inference cost: one sparse vectorize + dot per post, sub-millisecond on
  the VPS CPU. The artifact is loaded lazily once per process, the same
  pattern `llm_sentiment.py` uses for its client.

### 3.4 Training

A committed script, `scripts/train_radar_sentiment.py`, trains from the
local database (VPS trains from the VPS database, dev from dev):

- Rows: all mentions with a non-NULL `llm_sentiment`, joined to their
  retained post text, prepared per §3.2.
- Dedupe to unique prepared texts. Where one text carries several verdicts
  across tickers: a direction beats neutral/unclear; a text carrying BOTH
  directions is dropped from training (223 of 23,746 at decision time — a
  full-text model cannot learn two labels for one string).
- Artifact: vectorizers + estimator + metadata (trained-at timestamp, row
  count, class distribution, library versions) serialized with `joblib`
  into the Flask instance directory (`instance/radar_sentiment_model.joblib`
  — machine-local, never committed; weights are data, not code).
- The script prints the held-out chronological-split table for the model it
  just trained, so every retrain re-states its own evidence.
- Retraining is operator-triggered in v1 (run the script when it seems
  worth it; the label corpus grows ~7k/day and plateaus at the 30-day post
  retention window). A scheduled retrain is future work and needs nothing
  designed now.

### 3.5 Cold start

A process with no artifact on disk (fresh deploy, pre-first-training) must
not crash: `score()` returns `0.0` for everything and logs the absence once
per process. `0.0` is the honest "no signal" value — this is the same state
the board was in for two-thirds of posts under the old lexicon. The daemon
therefore deploys safely BEFORE the first training run.

## 4. What does not change

- **The Haiku arm** (`llm_sentiment.py`): model, prompt, batching, pass
  cadence, cost accounting — untouched.
- **Precedence**: a verdict outranks the float; `neutral`/`unclear` silence
  it. `board._tones` and `detail_panel._tone_of` unchanged.
- **The disagreement counter**: still local-vs-verdict. Caveat now on
  record: the local arm is distilled FROM Haiku labels, so agreement is
  partly by construction. The counter's meaning survives because a bag-of-
  n-grams model is still a surface reader — it diverges from Haiku exactly
  where tone is non-literal, which is what the counter exists to mark.
- **Schema**: no migrations. Same column, same float semantics.
- **Bucket `sentiment_mean`/`sentiment_stdev`**: still computed at rollup
  from the new floats; no surface reads them; they stay dormant.

## 5. Backfill

One script pass rescores `RadarMention.lexicon_sentiment` for every mention
whose post is still retained (~41k rows), using the trained model on the
stored title/body. Without it the board mixes two scoring regimes inside
the same window for up to 30 days. Follows the house pattern of
`scripts/backfill_radar_buckets.py`: idempotent, prints what it touched.
Stored bucket rows are not recomputed (no reader; tone is explicitly
outside `source_config_version`'s discontinuity rules — see the boundary
drawn in `llm_sentiment.py`'s docstring).

Deploy sequence: install deps → deploy code (daemon restarts into the
cold-start path, harmless) → run training script on the VPS → run backfill
→ done. No downtime step.

## 6. Dependencies and ops

- `scikit-learn` (pinned to the 1.4 line) and `scipy` added to the root
  `requirements.txt`; `joblib` ships with scikit-learn. The pin matters:
  joblib artifacts are not guaranteed portable across scikit-learn
  versions, and an unpinned upgrade would strand the on-disk model.
  Trained-on versions are recorded in the artifact metadata and checked at
  load (mismatch → cold-start behavior plus a log line, never a crash).
- `vaderSentiment` is NOT added to requirements — it lost. The measurement
  harness imports it optionally and skips its rows when absent, so the
  committed script runs on the VPS venv too.
- Deploy: verify whether `update_coc.sh` installs requirements; if not, one
  manual `pip install` in the shared VPS venv before the daemon restarts,
  else ingest dies on import.

## 7. Tests and the measurement artifact

- Scorer tests (rewriting the lexicon block of `tests/test_radar_text.py`):
  train a tiny model in-test on synthetic labelled fixtures — no committed
  binary — then assert: clear directional cases, abstention below τ,
  toneless-mass rule, float range and sign semantics, comment-title
  stripping, HTML entities, empty/None inputs, and the cold-start path
  (no artifact → `0.0` + one log line, no exception).
- The two scratchpad harnesses (`eval_sentiment_scorers.py`,
  `eval_sentiment_classifier.py`) merge into
  `scripts/measure_sentiment_scorers.py` (house `measure_*` pattern) with
  the §2.1 table in its docstring, so the next scorer argument starts from
  numbers. A `test_measure_*` file covers its pure helpers (comment-shape
  detection, split logic, metric arithmetic).
- Teeth check per the SDD lesson: every assertion whose passing state is an
  absence (abstention returns `0.0`, cold start does not raise) must be
  shown to fail against a broken variant before it counts.

## 8. Out of scope

- Ticker-aware context features (would let the model split multi-ticker
  posts the way Haiku does — the 289 conflicted posts / 975 mentions the
  harness excludes as irreducible today). Measured v2 candidate once v1 is
  live; changes nothing about v1's interfaces.
- Scheduled retraining; judging the medium tier with Haiku; any change to
  Haiku coverage, model, or spend.
- Extraction/confidence improvements (unclear-share diagnostics, per-ticker
  mute, alias table) — parked separately.
- Surfacing bucket sentiment means anywhere.

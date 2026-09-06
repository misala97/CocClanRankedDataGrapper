# Radar encoder judge — design

Replace the dead Anthropic judge with a distilled encoder that costs nothing
to run, **as a flagged trial first**, per Codex's review of 2026-09-06:
"build behind a flag; the evidence supports a controlled trial, but not an
unconditional replacement of Haiku."

Evidence, measurements and the traps behind every decision here:
`2026-09-05-radar-local-judge-roadmap.md`. This document specifies only what
gets built.

---

## 1. Decision

The judge becomes a **backend**, chosen by configuration, behind one small
protocol. Three backends exist at the end of this work:

| backend | id | role |
|---|---|---|
| `encoder` | `radar-encoder-v1` | the new judge; free, unlimited, local |
| `anthropic` | `claude-haiku-4-5` etc. | the existing path, unchanged, off by default |
| `none` | — | judging disabled; the pass makes no calls |

Everything the current module does apart from *how a batch of prepared items
becomes verdicts* stays exactly as it is: the binding prompt, the binding
schema, batching, enum validation, discard-never-default, the two-tier
storage, journal eligibility sync, the meters, the gate.

**The encoder does not use the prompt.** It reads `(ticker, author_text)` and
emits the five fields directly. The prompt and its sha256 pins remain in the
module because the Anthropic backend still needs them and because the
reference tooling labels with them. `PROMPT_VERSION` stays the version of the
*label semantics*, which both backends answer to; the backend id records who
answered.

### 1.1 What the trial is

Codex's conditions, adopted verbatim into the design:

- The encoder **judges and stores** all five fields.
- **Encoder tone never reaches any tone path** for the trial. This is a
  WRITE decision, not a display one: there are four consumers of attitude
  (`detail_panel._tone_of`, the detail breakdown query, `board.py`'s bull/bear
  SQL `CASE`, and `legacy_projection` writing the old `llm_sentiment`
  column), so changing a label achieves nothing. During the trial
  `apply_judgments` writes relevance, content_origin, model, prompt_version
  and judged_at to the mention, plus the FULL five-field history row — and
  leaves `sentiment_attitude`, `sentiment_expected_move`,
  `sentiment_confidence` and `llm_sentiment` untouched. Attitude is captured
  for evaluation and is absent from production by construction (§4.1).
- Relevance and content_origin — the fields that remove mentions from counts
  — DO take effect, because those are the fields the evidence supports.
- The **tolerated precision loss and the rollback trigger are written into
  this document before the trial's evaluation**, not decided after seeing it
  (§7).
- A **fresh randomly-sampled traffic audit** is owed before the trial can
  become an unconditional replacement (§7.3). The existing 200-row audit is
  half removal-enriched and cannot serve.

---

## 2. The seam

### 2.1 Protocol

```python
class JudgeBackend(Protocol):
    id: str            # <= 40 chars; the provenance value AND the spend key
    batch_size: int    # items per judge_batch call
    pass_limit: int    # items one scheduled pass will take
    supports_review: bool

    def judge_batch(self, batch: list[JudgeItem], *, preamble: str | None
                    ) -> tuple[dict[Any, Judgment], Usage]:
        """Verdicts for the items it could judge, keyed by item.key.

        A key absent from the result was NOT judged and stays NULL. Raises
        SentimentUnavailable for anything that is not a verdict: a refusal,
        a transport failure, unparseable output, a wrong-shaped answer.
        Never returns a defaulted verdict.
        """
```

`Usage` is a frozen dataclass `(input_tokens: int, output_tokens: int)`, zero
for a tokenless backend.

`judge()` becomes `judge(items, backend, on_usage=None, preamble=None)`. The
`client`, `model` and `effort` parameters leave the public signature; they are
Anthropic call parameters and belong inside its adapter.

**Validation does not move.** `_judge_batch_v2`'s enum check (spec §5.2.2: the
schema and enum validation are "the actual boundary") stays in
`llm_sentiment`, applied to whatever a backend returns. An adapter that
returned a bad enum is a bug caught in one place for all backends.

### 2.2 Adapters

**`AnthropicBackend(model, effort=None)`** — today's `_judge_batch_v2` moved
verbatim: `output_config` with the json_schema, `stop_reason == 'refusal'`,
the text-block parse, `usage.input_tokens`/`output_tokens`, and
`anthropic.APIError` translated to `SentimentUnavailable`. `effort` becomes a
constructor argument, which retires the "Sonnet-only" comment at the call site
and the model-id heuristic in `build_sentiment_reference.py`.

**`EncoderBackend(artifact_dir)`** — ONNX Runtime session plus tokenizer.

- **Validated at construction, session loaded on first use.** Construction
  reads `active.json` and the artifact's `config.json`, checks the files
  exist and that `heads` matches the code's `_FIELD_ENUMS`, and raises if not
  — a bad artifact fails daemon startup visibly. The ONNX session itself is
  built on the first `judge_batch` and held for the process lifetime; a
  session-load failure there raises `SentimentUnavailable`, is logged once,
  and the pass judges nothing. It must never fall back to another backend.
- `intra_op_num_threads=2`, `inter_op_num_threads=1`, `batch_size=4`
  (measured: 2 threads is as fast as 4; batch 16 spikes 1,715 MB where
  batch ≤ 4 stays flat at 1,081 MB).
- Input per item: the tokenizer applied to `(prepared.target_ticker,
  prepared.author_text)`, truncated to the artifact's `max_len` (256).
- Output: `argmax` per head mapped through the artifact's class lists.
- `Usage(0, 0)`.

**Artifact layout** (`RADAR_JUDGE_ARTIFACT_DIR`, default
`personal_apps/artifacts/judge/`), mirroring the existing local-arm pointer
idiom in `sentiment.py`:

```
active.json          {"path": "v1/", "id": "radar-encoder-v1"}
v1/model.onnx
v1/tokenizer.json
v1/config.json       {heads, max_len, base, manifest}
```

`config.json` carries the training manifest (seed, sizes, exclusion counts,
input hashes, git HEAD). The backend refuses to load an artifact whose
`heads` do not match the code's `_FIELD_ENUMS`, and logs which key differs.

### 2.3 Configuration

```
RADAR_JUDGE_PRIMARY   encoder | anthropic:claude-haiku-4-5 | none   (default: none)
RADAR_JUDGE_REVIEW    anthropic:claude-sonnet-5 | none              (default: none)
RADAR_REVIEW_TIER     '' | shadow | 1        (RADAR_SONNET_REVIEW still honoured)
```

House idiom, matching `RADAR_FORCE_IPV4` and `RADAR_US_PRICE_PROVIDER`. A
tiny registry parses the spec into a backend; an unknown spec is a startup
error, not a silent fallback. **Default `none`** so a deploy that forgets the
variable judges nothing rather than judging with the wrong thing.

---

## 3. The stage bug (fix first, alone, before the seam)

`apply_judgments` infers *stage* from the *model id*:

```python
review_stands = (stage == 'primary'
                 and mention.sentiment_model == REVIEW_MODEL
                 and mention.sentiment_prompt_version == PROMPT_VERSION)
```

and `review_candidates` filters `sentiment_model == PRIMARY_MODEL`. Both break
on a backend change, silently: a review verdict can be overwritten by a later
primary pass, or rows judged by a previous primary drop out of the review pool.
The suite stays green because it uses two different fake model ids.

**Fix**, in the shape Codex confirmed:

- `review_stands` asks the history, not the model column: does a
  `RadarSentimentJudgment` exist for **this mention** with `stage='review'`
  **and `prompt_version == PROMPT_VERSION`**? Scoped to mention + current
  prompt version — not "the latest history row", which would answer a
  different question.
- `review_candidates` drops the `sentiment_model == PRIMARY_MODEL` filter.
  The existing `~reviewed.exists()` already expresses "not yet reviewed at
  this prompt version"; the model filter was a second, wrong, stage proxy.
  **The activation-cutoff and prompt-version fences stay** — they exist so
  the bounded rejudge script cannot leak into live review spend (Codex's
  earlier blocker 1) and that reason is untouched by this change.

**Required tests** (both currently impossible to express):

1. Primary and review backends with **identical ids**: a review verdict must
   still stand against a later primary pass.
2. A **backend change**: rows judged by a previous primary id are still
   eligible for review, and a standing review verdict is still protected.

This lands as its own commit with its own tests, before any seam work, so a
regression here is attributable.

---

## 4. Provenance, spend and the surfaces

**Provenance.** `backend.id` flows unchanged into
`RadarSentimentJudgment.model`, `RadarMention.sentiment_model` and
`spend.record`, exactly as `PRIMARY_MODEL` does today. `String(40)` is the
budget; `radar-encoder-v1` is 17. A test asserts every registered backend id
fits, so a future long id fails in CI rather than in a MariaDB migration.

**Spend.** `MODEL_RATES` gains `'radar-encoder-v1': (0.0, 0.0)`. This is
deliberate and load-bearing: `cost_micros` returns `None` for an *unknown*
rate and the board then reports the tokens as `unpriced_tokens`. An explicit
zero says "free", not "unknown". `Spend.tsx` hides the meter when today,
month and unpriced are all zero, which is the correct reading for a free
backend — no dollar figure is more honest than `$0.00`.

**Stale rate, fix in passing.** `MODEL_RATES['claude-sonnet-5']` is
`(3.00, 15.00)`; list price is `(2.00, 10.00)`. No Sonnet spend has ever been
booked, so nothing is mis-billed, but the review tier would have overstated by
50%.

**Post cards.** `Posts.tsx:86` renders the literal `'Claude'` for
`judged_by === 'model'`. `_judged_by` in `detail_panel.py` is already
backend-neutral (it never reads `sentiment_model`), so the payload carries no
information about *who*. Add a server-side `judged_label` derived from
`sentiment_model` through the registry — `'Claude'`, `'model'`, or the
backend's display name — and render that. `judged_by`'s three-valued contract
stays untouched: tone precedence depends on it.

---

### 4.1 Trial write path — how encoder tone is excluded, exactly

Four places consume attitude. None of them is patched; instead the column
they read is never written during the trial:

| consumer | reads | why it is safe |
|---|---|---|
| `detail_panel._tone_of` (post cards) | `sentiment_attitude`, then `llm_sentiment`, then `lexicon_sentiment` | attitude stays NULL → falls through to the pre-existing chain, exactly as an unjudged row does today |
| `detail_panel` breakdown query (:219) | same three columns | same |
| `board.py:358` bull/bear SQL `CASE` | `sentiment_attitude`, `llm_sentiment`, `lexicon_sentiment` | same; the `att.isnot(None)` guard never fires |
| `legacy_projection()` → `llm_sentiment` | derived from attitude | **not called** on the trial write path |

`apply_judgments` gains a `write_tone: bool` decided by the backend's trial
mode. When false it writes `sentiment_relevance`, `sentiment_content_origin`,
`sentiment_model`, `sentiment_prompt_version`, `sentiment_judged_at` and the
complete five-field `RadarSentimentJudgment` history row; it does not touch
`sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence` or
`llm_sentiment`.

Consequences to check in the plan, not assume:

- `final_eligibility()` reads relevance and content_origin from the mention —
  unaffected, and it is the whole point of the trial.
- `pending()` keys on `sentiment_judged_at`, which IS written, so rows are not
  re-judged forever.
- `_judgment_of(mention)` (review routing) would build a Judgment with NULL
  attitude/confidence. Review is off by default in the trial
  (`RADAR_JUDGE_REVIEW=none`); if it is ever enabled alongside trial mode, the
  router must read the history row instead. A test pins this.
- `train_radar_sentiment.load_rows` filters `sentiment_attitude IS NOT NULL`,
  so trial rows never become training data for the local classifier. That is
  correct — a model must not train on its own output — and it is now
  load-bearing rather than incidental.

---

## 5. Throughput and the pass

`BATCH_SIZE = 20` and `PASS_LIMIT = 400` are module constants tuned for a
hosted model. They become backend attributes. For the encoder, 400 rows at the
measured 7 rows/s is ~57 s, comfortably inside the 10-minute cadence with
`max_instances=1`.

**With a free judge the gate's rationale disappears.** `judge_gate.py` exists
because judging cost money (it cut ~81% of spend). It is NOT removed in this
work: it stays enabled through the trial so that exactly one variable changes.
Turning it off — judging ~13k mentions/day instead of ~2,400 — is a separate,
later change with its own before/after (§7.4).

---

## 6. Spec v2.1 amendment (required, not optional)

The sentiment v2 spec forbids and mis-gates what this ships. Both need
amending in the same work, or this design contradicts the document it claims
to implement.

- **§13** — "No local generative LLM in v2; measured candidates missed the
  quality or throughput gate." An encoder classifier is not a generative LLM,
  but the sentence was written to exclude exactly this kind of substitution
  and must be amended honestly rather than lawyered around. New wording states
  what is now measured: local *generative* models remain excluded (Qwen 3.5
  4B/9B: irrelevant precision 0.4–0.5 vs Haiku); a distilled *encoder* is
  admitted subject to §10.
- **§10.2** — the absolute gates (80% attitude, 84% directional, ≤2%
  reversals, 90% F1s, 95% removal precision) were written for a frontier
  judge; the encoder scores 0 of 5. They stay as the standard for an
  unconditional replacement. A **trial** gate is added: relative to the
  incumbent, no field materially worse, with the tolerance stated in §7.1.
- **§5.1/§5.3** — the local arm and the review tier now describe backends
  rather than named models.

---

## 7. Trial gates, rollback, and what is owed

### 7.1 Tolerated loss, fixed now

Written before the evaluation, per Codex. On the fresh random audit (§7.3),
against the same reference, relative to the Haiku numbers on that same set:

| field | rule |
|---|---|
| removal precision | ≥ Haiku − 0.03, and ≥ 0.93 absolute |
| relevance / content_origin agreement | ≥ Haiku − 2.0 points |
| attitude | not gated during the trial; tone is not displayed from the encoder |
| polarity reversals | recorded, not gated during the trial |

Failing any of these ends the trial (§7.2). **Passing them authorises
nothing about tone.** Removal quality cannot license a tone change, and the
table above deliberately does not gate attitude — so tone stays disabled until
its own criteria are met, separately:

**Tone promotion criteria (all four, on the fresh random audit):**

| | rule |
|---|---|
| polarity reversals | ≤ Haiku's rate on the same set, with the Wilson upper bound below 5% |
| attitude agreement | ≥ Haiku − 2.0 points |
| `mixed` / `none` confusion | not worse than the incumbent on the same set |
| shadow period | ≥ 7 days of trial-mode history rows to compare against the displayed tone |

Until all four pass, `write_tone` stays false and the board's tone comes from
the pre-existing chain.

### 7.2 Rollback trigger, fixed now

Any one of these reverts `RADAR_JUDGE_PRIMARY` to `none` (or to `anthropic`
with credits) within the same day:

- the share of mentions removed per day moves by more than **±50% relative**
  versus the Haiku-era baseline in `radar_llm_spend`/journal history;
- `sentiment_ops.pending` p95 age exceeds **20 minutes** for two consecutive
  hours;
- daemon RSS exceeds **2.5 GB**, or the box drops under **300 MB** available;
- any bucket-count anomaly the journal's own rebuild cannot explain.

**Rollback is two steps, and the first one alone is not a rollback.**
Switching to `none` stops new judgments but leaves every encoder deletion
active in the counts, because `final_eligibility` already removed those
mentions from buckets and journal.

1. **Stop** (seconds): `RADAR_JUDGE_PRIMARY=none`, restart `radar_ingest`.
   No new encoder verdicts.
2. **Recover** (a bounded script, written as part of this work, not improvised
   during an incident): select mentions where
   `sentiment_model = 'radar-encoder-v1'` and `sentiment_prompt_version =
   PROMPT_VERSION`; clear `sentiment_relevance`, `sentiment_content_origin`,
   `sentiment_model`, `sentiment_prompt_version`, `sentiment_judged_at`
   (returning them to the unjudged state that counts provisionally);
   re-run `journal.sync_chatter_eligibility` for the affected windows and
   `journal.rebuild_windows` for those windows, in one transaction per window,
   the same discipline `_sync_eligibility` and `_rebuild_corrected` already
   use. History rows are append-only and are KEPT — they are the evidence of
   what the trial did.
   `--dry-run` prints the affected mention and window counts and writes
   nothing; that is the default.

The script is a deliverable of this work and is tested against the recovery
case before the trial starts. An untested rollback is not a rollback.

### 7.2b Trial deadline

An open-ended trial that changes live counts without ever testing its own
acceptance rules is not a trial. Therefore:

- The fresh random audit (§7.3) is drawn and labelled **within 7 days of the
  trial's first judged mention**. It is scheduled as part of starting the
  trial, not after it.
- If the audit has not been evaluated by **day 10**, the trial ends
  automatically: `RADAR_JUDGE_PRIMARY=none` plus the §7.2 recovery script.
- **Uncertainty, not point estimates, decides.** Each §7.1 threshold is
  applied to the **Wilson 95% lower bound** of the measured proportion, not to
  the point estimate. A trial that cannot demonstrate its bound with the audit
  it drew fails; it does not get to pass on a favourable point estimate with a
  wide interval. The audit is sized from this: to show removal precision ≥ 0.93
  at 95% confidence needs roughly 250-400 removal decisions, which fixes the
  sample size rather than leaving it to convenience.

### 7.3 The audit that is owed

The existing 200-row audit is half selected *because the encoder wanted to
delete those rows*, so it cannot estimate production removal precision, and
more enriched rows cannot fix it. Before any unconditional ship:

- a **fresh, randomly sampled** set from live traffic (not quota-stratified,
  not margin-targeted), sized for the precision question rather than for
  convenience;
- the two halves of the existing audit **reported separately**, never pooled;
- the two reversal rates (16.5% locked natural, 5.6% audit) **recomputed under
  one definition**, with the disagreements inspected and truncated posts
  looked at specifically — overall 256/512 parity can hide a difference on
  that small, costly subset;
- independent human labels preserved and adjudication changes recorded, so
  "teacher validated" can be claimed honestly. The current reference had a
  Fable 5.1 review pass and that claim is currently too strong.

### 7.4 Explicitly out of scope

Turning off the judge gate; retiring the lexicon; moving the relevance head
into extraction (broadens its blast radius and needs separate validation);
INT8 quantization (dynamic breaks the model and it is not needed at 1,081 MB);
extraction recall measurement (never measured — every row we have is one the
extractor accepted; see `radar-extractor-recall-unmeasured`).

---

## 8. Deployment

1. `scp` the artifact directory to the VPS; `pip install onnxruntime
   tokenizers` into the shared venv (~50 MB, no torch).
2. A **2 GB swapfile**. Measured headroom is ~0.7 GB with the encoder loaded
   and the slimmed daemon at 488 MB. Swap does NOT make an OOM impossible: it
   turns a transient spike into slowdown instead of a kill, and buys time for
   the RSS trigger in §7.2 to fire. A sustained leak still ends in an OOM,
   more slowly.
3. Set `RADAR_JUDGE_PRIMARY=encoder`, restart `radar_ingest`.
4. **Verify on the box before trusting it:** score the 200 audit rows through
   the deployed backend and compare verdicts with the PC's for the same
   weights. They were identical in the benchmark; a mismatch means a tokenizer
   or opset difference and the trial stops there.
5. Watch the first cycle's log line, then RSS, p95 backlog age, and the daily
   removal share against §7.2.

The artifact is **not** committed to git: 566 MB, and it is data, not code.
It ships by scp and is pointed at by `active.json`, the same shape the
existing local classifier arm already uses.

---

## 9. Testing

- `FakeBackend` returning verdicts, raising `SentimentUnavailable`, and
  returning partial results, used by every `judge()`/`run_pass`/
  `run_review_pass` test. The ~45 tests in `test_radar_sentiment_v2.py` and
  ~10 in `test_radar_llm_sentiment.py` that are built on a fake Anthropic
  client move to it.
- The Anthropic request-shape assertions (byte-exact prompt via
  `requests[0]['messages'][0]['content']`, `output_config`, `stop_reason`,
  `effort`, `anthropic.APIError` containment) move into a dedicated
  `AnthropicBackend` test that keeps today's `FakeClient`. **The sha256 pins
  on the prompt and schema stay exactly as they are** — they protect the
  binding text and are not backend-specific.
- New: encoder adapter against a real (small) artifact — enum-valid output,
  correct item keying, refusal-to-load on a head mismatch, `Usage(0,0)`.
- New: the two stage tests from §3.
- New: backend id length, and `MODEL_RATES` containing every registered id.
- `test_diagnose_extractor_feedback.py:127` monkeypatches
  `llm_sentiment._get_client` by name as its "no model call is possible"
  poison. It must poison the registry's construct function instead, or that
  guard loses its teeth silently.

## 10. Definition of done

The seam exists with three backends; the stage bug is fixed with tests that
would have caught it; provenance, spend and the post-card label carry the
backend truthfully; the spec is amended rather than contradicted; the full
suite is green; the artifact runs on the VPS producing verdicts identical to
the PC's; the trial gates and rollback trigger in §7 are written down before
any evaluation of the trial. Displayed tone still comes from the previous
path, and the judge gate is still on.

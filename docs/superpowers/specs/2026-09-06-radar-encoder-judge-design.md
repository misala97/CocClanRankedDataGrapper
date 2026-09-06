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

The binding prompt/schema, enum validation, discard-never-default, review
precedence, eligibility semantics, meters and gate are preserved. The explicit
exceptions are backend-sized batches, configuration/defaults, trial tone writes,
and the recovery/expiry machinery below. The implementation separates the
Anthropic seam refactor from these behavior changes.

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

Artifact identity for trial state/audit is SHA256 of UTF-8 lines
`model.onnx=<file-sha256>\n`, `tokenizer.json=<file-sha256>\n`,
`config.json=<file-sha256>\n` concatenated in that order, using lowercase hex.
Store this bundle hash in the deployment record/state, not inside config.json
(which would make the hash recursive). The config's manifest describes training
inputs/export provenance; startup verifies the complete bundle against the
armed trial. Replacing any constituent requires a separately reviewed trial.

### 2.3 Configuration

```
RADAR_JUDGE_PRIMARY   encoder | anthropic:claude-haiku-4-5 | none   (default: none)
RADAR_JUDGE_REVIEW    anthropic:claude-sonnet-5 | none              (default: none)
RADAR_REVIEW_TIER     '' | shadow | 1        (RADAR_SONNET_REVIEW still honoured)
RADAR_JUDGE_TONE      0                     (default: 0; encoder only)
```

House idiom, matching `RADAR_FORCE_IPV4` and `RADAR_US_PRICE_PROVIDER`. A
tiny registry parses the spec into a backend; an unknown spec is a startup
error, not a silent fallback. **Default `none`** so a deploy that forgets the
variable judges nothing rather than judging with the wrong thing.

Configuration is resolved once in `run_radar_ingest.main`, before fetchers or
scheduler jobs are created, outside `_scheduled_sentiment`'s exception handler.
Selected adapters are constructed there and retained for the process lifetime;
the ONNX session remains lazy. Web requests and maintenance commands do not
construct a judge merely by importing the registry. Metadata/display lookup is
pure and never opens an artifact or a client.

`RADAR_REVIEW_TIER`, when present (including an empty value), wins over the old
flag. Otherwise normalize the old flag's `shadow`, `1`, `true`, `True`; an
unset/empty old flag is off. Reject other nonempty values visibly. The resolved
mode is shared by the review pass and `_over_ceiling_gauge`. `none` as the
review backend prevents calls, demand stamps and review-meter writes even if
the mode is live/shadow; enabling review requires both a backend and a mode.
`supports_review` means an adapter may serve the review role: Anthropic true,
encoder/disabled false. Reject an unsupported review-role selection at startup.

The tone flag applies only to the encoder. In this work `0` is the only
accepted value: encoder writes are suppressed, Anthropic primary and review
writes retain their existing semantics. A nonzero value fails startup; passing
the separate tone criteria is evidence for a later explicit promotion change,
not an automatically enabled feature of this build.

The bounded rejudge CLI remains Anthropic-only and ignores the daemon's primary
selection; its default remains Haiku. Historical encoder rejudging is outside
this live-traffic trial. The reference-label CLI accepts explicit `--effort`
(`none`, `low`, `medium`, `high`); after the separate configuration task its
default is `none`,
and existing Sonnet/Opus labeling recipes must explicitly supply `--effort low`.
The review adapter is explicitly constructed with `effort='low'`.

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

**Required tests** (expressible now through `apply_judgments`'s model argument):

1. Primary and review backends with **identical ids**: a review verdict must
   still stand against a later primary pass.
2. A **backend change**: rows judged by a previous primary id are still
   eligible for review, and a standing review verdict is still protected.

Use a shared arbitrary id different from `REVIEW_MODEL` for test 1. Also test
two successive primary judgments using `REVIEW_MODEL` with no review history:
the second must update the mention. Another mention's review and an older
prompt generation's review must not protect this mention. The primary-only
case catches the opposite false-positive stage inference.

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
information about *who*. Add a server-side `judged_label` describing the source
of the **displayed tone**. Add nullable `RadarMention.sentiment_tone_model`
(`String(40)`), written alongside tone only when `write_tone=True`. Backfill it
from `sentiment_model` where a v2 attitude exists; legacy-only tone without
known provenance uses the generic label `model`. During suppressed encoder
writes, neither tone nor its provenance changes. Resolve the tone model through
pure registry metadata: Anthropic ids display `Claude`, unknown/missing ids
display `model`. `judged_by` remains `model | lexicon | None`; the new label is
null unless `judged_by == 'model'`. Never infer tone ownership from the new
relevance model. The migration and serializer/TypeScript contract changes are
deliverables, not UI-only edits.

---

### 4.1 Trial write path — how encoder tone is excluded, exactly

Four places consume attitude. None of them is patched; instead the column
they read is never written during the trial:

| consumer | reads | why it is safe |
|---|---|---|
| `detail_panel._tone_of` (post cards) | `sentiment_attitude`, then `llm_sentiment`, then `lexicon_sentiment` | existing values are preserved; a fresh NULL attitude falls through to the pre-existing chain |
| `detail_panel` breakdown query (:219) | same three columns | same |
| `board.py:358` bull/bear SQL `CASE` | `sentiment_attitude`, `llm_sentiment`, `lexicon_sentiment` | same; no encoder attitude activates its non-NULL branch |
| `legacy_projection()` → `llm_sentiment` | derived from attitude | **not called** on the trial write path |

`apply_judgments` gains a required keyword-only `write_tone: bool` decided by
the backend policy (encoder false, Anthropic true). All three callers — live
primary, live review, bounded Anthropic rejudge — pass it explicitly. When false
it writes `sentiment_relevance`, `sentiment_content_origin`,
`sentiment_model`, `sentiment_prompt_version`, `sentiment_judged_at` and the
complete five-field `RadarSentimentJudgment` history row; it does not touch
`sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence` or
`llm_sentiment`.

The Task 1 standing-review guard surrounds **all mention materialization**,
including provenance and timestamps; history is appended even when that guard
blocks an incoming primary. Suppression means preserve existing values, not
clear them. `sentiment_tone_model` follows the same preservation rule.

An enabled Anthropic review independently judges prepared text and writes all
five mention fields, its legacy projection and tone provenance as before. It
never copies an encoder history Judgment into a review write. Shadow review
reads/routes and meters demand as before, with no verdict/history/tone write.
The deployed trial has review off. This policy permits later explicitly enabled
Anthropic review without treating its own tone as encoder output.

Consequences to check in the plan, not assume:

- `final_eligibility()` reads relevance and content_origin from the mention —
  unaffected, and it is the whole point of the trial.
- `pending()` keys on `sentiment_judged_at`, which IS written, so rows are not
  re-judged forever.
- Review routing bulk-loads the latest **primary** history per candidate at
  the mention's current `PROMPT_VERSION`, ordered by `created_utc DESC, id DESC`.
  Do not filter by the currently configured backend id, or branch only on NULL
  attitude. `_judgment_of(mention, primary_history)` uses all five history fields
  together, never a mixture with preserved mention tone. Candidate fences and
  exclusion of any current-version review remain. Missing history permits the
  old mention-based fallback only for a non-encoder model with all five valid
  fields; otherwise skip the candidate with a visible warning. No defaulted
  Judgment and no per-mention query.
- `train_radar_sentiment.load_rows` keeps its existing selection. Fresh encoder
  rows have no attitude/confidence and are excluded. A row carrying a preserved
  earlier human/Anthropic tone, or an independent Anthropic review, may still be
  training-eligible: the invariant is **no encoder-generated tone labels enter
  training**, not “every mention ever seen by the encoder is excluded.” History
  is never used to fill missing training labels. Historical encoder rejudging
  is not exposed by this build.

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

Until all four pass, encoder `write_tone` stays false. This build only reports
tone qualification; enabling encoder tone requires a subsequent reviewed
promotion change. Independent Anthropic review retains its existing behavior.

### 7.2 Rollback trigger, fixed now

Any one of these stops the encoder and starts recovery within the same day.
The operator may select Anthropic with credits after recovery:

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

1. **Stop** (seconds): persist trial state `recovering` before changing service
   configuration. This overrides `RADAR_JUDGE_PRIMARY=encoder` at startup and
   before each batch/write, even if an old environment file survives. Then set
   `RADAR_JUDGE_PRIMARY=none` and restart `radar_ingest`. The durable state, not
   a successful edit to an environment file, is the enforcement boundary.
2. **Recover** (a bounded script, written as part of this work, not improvised
   during an incident): select mentions where
   `sentiment_model = 'radar-encoder-v1'` and `sentiment_prompt_version` equal to
   the trial's **frozen** prompt version; clear `sentiment_relevance`, `sentiment_content_origin`,
   `sentiment_model`, `sentiment_prompt_version`, `sentiment_judged_at`
   (returning them to the unjudged state that counts provisionally);
   re-run `journal.sync_chatter_eligibility` and rebuild the affected windows
   from the complete retained journal, **one transaction per window**. Tone
   values and `sentiment_tone_model` are preserved. Independent Anthropic review
   winners are not selected and their decisions survive recovery. History is
   append-only and KEPT — it is the evidence of what the trial did.
   `--dry-run` prints the affected mention and window counts and writes
   nothing; that is the default.

The script is a deliverable of this work and is tested against the recovery
case before the trial starts. An untested rollback is not a rollback.

### 7.2a Recovery evidence and transactions

The current helpers do not yet provide that recovery guarantee. Journal
retention is 48 hours, `journal.rebuild_windows` refuses older windows, and
`journal.mark_promoted` commits inside the bucket rebuild before its final
commit. This build must change those mechanics explicitly:

- A durable singleton `RadarJudgeTrial` row (`id=1`) is armed **before any
  encoder writes**. Fields: `model_id` (`String(40)`), `prompt_version`
  (`String(64)`), `artifact_sha256` (`String(64)`), `status` (`String(10)`,
  `armed | running | recovering | recovered`), `armed_at`, `retain_from`,
  nullable `first_judged_at`, nullable `audit_evaluated_at`, nullable
  `audit_passed` (Boolean), nullable `audit_report_sha256` (`String(64)`),
  `recipe` (JSON) and nullable `stop_reason` (Text). Timestamps use the existing
  microsecond UTC storage convention. The recipe holds frozen sampling parameters
  and baseline report hash. This build runs one trial; arming cannot overwrite
  an existing row or reset its clock.
- `retain_from` is the next quarter-hour boundary strictly after
  `armed_at - 48h`. The live judge gate's 24-hour input window is inside it.
  While status is armed/running/recovering, retention uses the earlier of its
  normal cutoff and `retain_from` for **both journal events and posts**; this
  also preserves mentions and cascading judgment history. Pin whole windows,
  including non-encoder and low-confidence events, not just judged mentions.
  Arming and retention serialize on a database advisory lock so a concurrent
  prune cannot cross a newly installed pin. Selecting encoder without an armed
  matching row fails startup. Batches outside the retained interval are refused.
- A passing audit does not release the pin or promote the backend. Continuing
  trial operation continues retaining recovery evidence. Only completed recovery
  releases the pin in this build; eventual unconditional promotion/release is a
  separate change. Record the storage cost in the deployment runbook and monitor
  free disk space while pinned. Lack of recovery evidence is an error, never a
  reason to rebuild incomplete historical buckets.
- Add `commit: bool = True` to `journal.mark_promoted`,
  `buckets.rebuild_windows` and its internal rebuild helper. With false, every
  nested write flushes but none commits. Existing callers keep the true default.
  Recovery calls the bucket helper with false after verifying its window is
  inside the durable retained interval; the ordinary journal horizon guard
  remains unchanged. The caller commits mention clears, journal flags,
  promotion flags and bucket totals together, or rolls all of them back.
- Extend the bucket write guard to a shared database advisory lock, in addition
  to the existing in-process lock, at live rollup/rebuild and recovery entry
  points. Recovery takes it before modifying mention/event state and holds it
  through commit. Primary/review materialization and recovery also serialize
  on the trial row, rechecking the state before writing. Lock order is bucket
  guard then trial row for recovery; live judgment releases its trial-row
  transaction before its existing subsequent bucket rebuild. Do not hold a DB
  transaction across model inference.
- `rollback_encoder_judge.py --apply --limit N` bounds **mentions** (positive
  N, default 2000), selects by window then mention id, and may recover a subset
  of mentions in its last window. Rebuild that whole window from all its events.
  Each committed subset is resumable because cleared rows no longer match.
  No final “recovered” state until a fresh count finds zero matching mentions.
  Default/`--dry-run` computes capped and total counts with no writes, state
  transition, model construction, or service changes. Explicit dry-run plus
  apply is a CLI error. No matching rows is an idempotent successful recovery.

Required recovery tests include a ten-day-old trial with the retention jobs
actually run, mixed sources/low-confidence events, independent review winners,
partial-window limits, interrupted/resumed runs and injected failure after
promotion but before totals. A failed window must leave **all** its pre-call
state intact, while earlier committed windows remain recovered.

### 7.2b Trial deadline

An open-ended trial that changes live counts without ever testing its own
acceptance rules is not a trial. Therefore:

- The fresh random audit (§7.3) is drawn and labelled **within 7 days of the
  trial's first judged mention**. It is scheduled as part of starting the
  trial, not after it.
- If the audit has not been evaluated by **day 10**, the trial ends
  automatically through the durable stop override plus the §7.2 recovery
  script. “Evaluated” means a valid passing report; a failed report stops the
  trial immediately. Both sampling and completed labels must meet day 7.
- **Uncertainty, not point estimates, decides the trial gates.** The removal
  and relevance/origin thresholds in §7.1 apply to the **Wilson 95% lower
  bound** of the encoder proportion. Separate tone criteria use the explicitly
  stated directions and comparisons in §7.2c. A trial that cannot demonstrate
  its bound with the audit
  it drew fails; it does not get to pass on a favourable point estimate with a
  wide interval. The audit is sized from this: to show removal precision ≥ 0.93
  at 95% confidence needs roughly 250-400 removal decisions, which fixes the
  sample size rather than leaving it to convenience.

**Enforcement deliverable.** `judge_trial.tick(now, limit=2000)` reads the row
without constructing a backend. At expiry (`now >= first_judged_at + 10 days`)
without a timely passing audit, or after a failed audit, it persists recovering
and calls the bounded recovery operation. Further ticks drain the remainder;
exceptions leave recovering/pinning intact and are logged for operator action.
`first_judged_at` is set in the same transaction as the first materialized
encoder verdict, never at daemon startup or from a failed call. A guard before
each encoder batch and again before materialization rejects an expired/stopped
trial and discards late in-flight answers without history/materialization.

No row or an armed row without a first judgment makes an unexpired tick inert;
recovering always drains recovery, even if no first judgment was recorded, and
recovered ticks are no-ops. A configured encoder with absent/mismatched trial
identity fails startup; an existing recovering/recovered trial instead resolves
the effective primary to none with a visible log, allowing ingestion to run.

Ship a one-minute systemd timer/service invoking
`python -m scripts.manage_encoder_trial tick --limit 2000` independently of
`radar_ingest`, with `Persistent=true`, and call the same guard on daemon
startup. An unavailable DB fails judging closed; the timer retries visibly.
The timer cannot promise execution while the host is down; startup and the
first timer run after recovery enforce the original deadline. Neither restart,
`PRIMARY=none`, nor a stale `PRIMARY=encoder` resets the clock or releases the
pin. State transitions serialize on the singleton row and duplicate ticks are
idempotent. The timer uses the service's existing environment/venv credentials,
not embedded secrets. Tone never auto-promotes on a passing audit.

### 7.2c Audit implementation contract

Deliver `scripts/audit_encoder_trial.py` with `sample`, `export-labels`,
`evaluate` and `accept` commands. Artifacts live in a per-trial data directory
outside git; `accept` is the only evaluation command that writes trial state.

- At arming, record a fixed seed, the baseline report hash and removal
  proportion `p` (0 < p <= 1), and `sample_size = ceil(400 / p)`. These are
  inputs fixed before new predictions, not constants chosen after seeing them.
  Freeze a frame of all retained extracted high-confidence mentions with post
  time in `[first_judged_at, first_judged_at + 3 days)`, across all sources and
  tickers, without gate/removal/confidence-of-judge enrichment. At day 3, choose
  `sample_size` ids uniformly without replacement using the recorded seed;
  insufficient traffic is a failed audit, not permission to change the frame.
  Persist the frame hash, sampled ids and draw timestamp; reruns reuse them.
- Obtain encoder and Haiku predictions for **exactly those ids** from the same
  canonical prepared inputs using the frozen artifact/prompt. Scoring is
  offline: no mention, history or spend writes through `apply_judgments`.
  Meter any paid labeling/prediction calls using the existing spend mechanism.
  Blind human exports omit both prediction sets. Preserve original human labels
  separately from adjudicated labels and record each change with its reason.
  Missing/invalid predictions or final labels fail coverage; never silently
  shrink a denominator. Do not reuse the quota-based reference sampler.
- For a backend, removal means irrelevant OR broadcast/automated; its removal
  precision denominator is its own predicted removals and the numerator is
  removals confirmed by the final reference. Agreement denominators are the
  complete sampled set. Compute Wilson intervals with z=1.959963984540054;
  zero denominators fail the corresponding criterion.
- Relative comparisons use the **Haiku point estimate** as the fixed threshold
  on this same sample: encoder removal LCB >= max(0.93, Haiku precision - 0.03);
  encoder relevance/origin agreement LCB >= Haiku agreement - 0.02, separately.
  Report both backends' numerators, denominators, points and bounds.
- Report tone separately: reversal denominator is reference-positive/negative
  rows; a reversal predicts the opposite polarity. Require encoder reversal
  point <= Haiku point and Wilson UCB < 0.05. Attitude agreement uses encoder
  LCB >= Haiku point - 0.02. Mixed/none confusion is the fraction of reference
  mixed/none rows predicted as the other of those two classes; require encoder
  point <= Haiku point. Missing that slice fails tone qualification. Seven days
  of primary history and the contemporaneously displayed tone must accompany
  the tone report. Capture displayed tone and its provenance with each encoder
  history row in nullable `displayed_tone` (`String(8)`),
  `displayed_tone_model` (`String(40)`) and `displayed_judged_by` (`String(8)`)
  diagnostics, before materialization, even though mention tone is not written;
  the five Judgment fields remain unchanged. Tone qualification never
  changes the trial pass/fail result or the runtime write policy.
- JSON plus Markdown reports include the original audit's two halves separately,
  and recompute the locked-natural and existing-audit reversal rates using that
  same denominator, with reversal/truncated-post disagreements listed for
  inspection. These supplementary sets never enter fresh-audit gate totals.
  Missing required supplemental files or label provenance makes the report
  incomplete. `accept` verifies all file hashes, trial/artifact/prompt identity,
  completed inspection acknowledgments, day-7 draw/label timestamps and the
  day-10 deadline before persisting result/time/report SHA. An invalid or late
  report cannot postpone expiry; a valid failing report requests recovery.

The baseline's actual report path and proportion are recorded at deployment;
if they cannot be supplied, do not arm. This is a concrete preflight input,
not a license for the implementer to invent a baseline from current traffic.

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
extractor accepted; see `radar-extractor-recall-unmeasured`); historical encoder
rejudging; actual tone or unconditional promotion. The evaluator reports tone
readiness but this build does not expose a tone-enabling switch.

---

## 8. Deployment

1. Deploy migrations/code with both judge backends none. `scp` the artifact
   directory to the VPS; `pip install onnxruntime tokenizers` into the shared
   venv (~50 MB, no torch). Shipping `v1/model.onnx` is FP32; the exploratory
   exporter's file with that basename is INT8 and must not be copied blindly.
2. A **2 GB swapfile**. Measured headroom is ~0.7 GB with the encoder loaded
   and the slimmed daemon at 488 MB. Swap does NOT make an OOM impossible: it
   turns a transient spike into slowdown instead of a kill, and buys time for
   the RSS trigger in §7.2 to fire. A sustained leak still ends in an OOM,
   more slowly.
3. **Verify before activation:** score the 200 audit rows through
   the deployed backend and compare verdicts with the PC's for the same
   weights. They were identical in the benchmark; a mismatch means a tokenizer
   or opset difference and the trial stops there.
4. Install and verify the independent watchdog timer; record baseline report,
   sampling recipe and labeling owner, and arm the durable retention pin before
   encoder activation. Confirm recovery storage capacity and a successful dry-run.
5. Set `RADAR_JUDGE_PRIMARY=encoder`, `RADAR_JUDGE_TONE=0`, review backend none,
   review mode empty, gate ON; restart `radar_ingest`. Verify first_judged_at is
   persisted with the first successful write; record and schedule the day-3,
   day-7 and day-10 actions from that clock the same day.
6. Watch the first cycle, RSS, p95 backlog and daily removal share against §7.2;
   record exact monitoring/stop/recover commands in the deployment runbook.
   Collect/evaluate the fresh audit on schedule. Deployment alone does not
   complete that audit or certify tone/promotion.

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
- New: the positive and negative stage/history tests from §3.
- New: backend id length, and `MODEL_RATES` containing every registered id.
- `test_diagnose_extractor_feedback.py:127` monkeypatches
  `llm_sentiment._get_client` by name as its "no model call is possible"
  poison. It must poison the registry's construct function instead, or that
  guard loses its teeth silently.
- New: the complete Task 5 write/routing matrix, including populated-value
  preservation, projection poison, live/shadow review and all four consumers.
- New: tone-provenance migration/backfill and encoder history display snapshots.
- New: actual day-10 retention/recovery, fault-injected atomic windows,
  cross-process lock serialization, bounded resume and write-poisoned dry-run.
- New: sampling/label provenance, Wilson-bound failures, deadline/hash checks,
  startup configuration and independent watchdog/in-flight expiry tests.

## 10. Definition of done

The seam exists with three backends; the stage bug is fixed with tests that
would have caught it; provenance, spend and the post-card label carry the
backend truthfully; the spec is amended rather than contradicted; the full
suite is green; the artifact runs on the VPS producing verdicts identical to
the PC's; the recovery evidence is pinned before the first encoder write;
recovery is proven across retention and crashes; the independent watchdog and
audit evaluator are installed/tested; the trial and tone rules remain fixed
before evaluation. Encoder tone is suppressed, independent Anthropic review
retains its defined behavior, and the judge gate stays on. Deployment handoff
records the pending live-audit dates/owner; audit completion requires the actual
report and acceptance record, not a checked deployment task.

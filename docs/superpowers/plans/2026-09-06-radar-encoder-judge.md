# Radar encoder judge — implementation plan

Spec: `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md`
(amended 2026-09-06 for Codex's five corrections).

Nine tasks, each its own commit on `dev_personal`, each with its own tests
green before the next starts. Tasks 1–2 change behaviour on their own and land
first so a regression is attributable. Nothing reaches prod until Task 9, and
what reaches prod is a flagged trial with `RADAR_JUDGE_PRIMARY` unset by
default.

**Verification discipline.** Every task states what proves it. Where a test's
passing state is an absence (a column NOT written, a verdict NOT overwritten),
the test is proven by breaking the code and watching it fail — the teeth check
this project already learned to insist on. Marked **[TEETH]** below.

---

## Task 1 — Stage, not model id

**Why first and alone:** it fails silently, the suite is green today because
it uses two different fake model ids, and every later task moves code around
it. Fixing it afterwards would make a regression unattributable.

`features/radar/llm_sentiment.py`:

- `apply_judgments`: replace
  `mention.sentiment_model == REVIEW_MODEL` with a history question — does a
  `RadarSentimentJudgment` exist for **this mention**, `stage='review'`,
  `prompt_version == PROMPT_VERSION`? Scoped to mention + current prompt
  version, **not** "the latest history row", which answers a different
  question. One query per `apply_judgments` call (a single `IN` over the
  batch's mention ids), not per row.
- `review_candidates`: delete the `RadarMention.sentiment_model ==
  PRIMARY_MODEL` filter. `~reviewed.exists()` already expresses "not yet
  reviewed at this prompt version". **Keep** `V2_ACTIVATION_CUTOFF` and the
  `sentiment_prompt_version == PROMPT_VERSION` fence — they exist so the
  bounded rejudge script cannot leak into live review spend, and that reason
  is untouched.

**Tests** (both impossible to express today):

1. **[TEETH]** primary and review backends with **identical ids**: a standing
   review verdict survives a later primary pass. Break it by restoring the
   model-id comparison and watch the test fail.
2. A **backend change**: rows judged by a previous primary id are still
   eligible for review, and a standing review verdict is still protected.

**Done when:** `test_radar_sentiment_v2.py` and `test_radar_llm_sentiment.py`
green, plus the two new tests, plus the teeth check recorded in the commit
message.

---

## Task 2 — Spec v2.1 amendment

Text only, no code, before the code that would contradict it.

`docs/superpowers/specs/2026-08-31-radar-sentiment-v2-final-design.md`:

- **§13** — replace "No local generative LLM in v2" with what is now
  measured: local *generative* models stay excluded (Qwen 3.5 4B/9B reached
  irrelevant precision 0.4–0.5 against Haiku); a distilled *encoder* is
  admitted subject to §10 and to a flagged trial. Amended honestly, not
  lawyered around on the technicality that an encoder is not generative.
- **§10.2** — the absolute gates stay as the bar for an unconditional
  replacement. Add the trial gate by reference to the new design's §7.1 and
  the separate tone criteria in §7.1b.
- **§5.1 / §5.3** — describe backends and roles rather than named models.

**Done when:** committed, and no statement in the new design contradicts the
amended spec.

---

## Task 3 — The seam, with the Anthropic backend only

No encoder yet. This task must be a **pure refactor**: same behaviour, same
statements, same stored values.

- `JudgeBackend` protocol, `Usage` dataclass, `backends.py` (or a section of
  `llm_sentiment.py` — decide by size, keep it in one module if it stays under
  ~150 lines).
- `AnthropicBackend(model, effort=None)`: today's `_judge_batch_v2` body moved
  verbatim, including the refusal check, the text-block parse, the usage
  attribute names and the `anthropic.APIError` translation.
- `judge(items, backend, on_usage=None, preamble=None)`. `client`, `model`,
  `effort` leave the signature.
- **Enum validation stays in `llm_sentiment`**, applied to whatever a backend
  returns.
- Registry parsing `RADAR_JUDGE_PRIMARY` / `RADAR_JUDGE_REVIEW`; unknown spec
  is a startup error. Default `none`.
- Callers updated: `run_pass`, `run_review_pass`, `scripts/rejudge_radar_sentiment.py`,
  `scripts/build_sentiment_reference.py` (its `effort = 'low' if model !=
  PRIMARY_MODEL` heuristic dies here).

**Tests:** the ~45 + ~10 existing tests move to a `FakeBackend`. The
Anthropic request-shape assertions (byte-exact prompt bytes, `output_config`,
`stop_reason`, `effort`, error containment) move into a dedicated
`AnthropicBackend` test that keeps today's `FakeClient`. **The prompt and
schema sha256 pins do not move and do not change.**

`tests/test_diagnose_extractor_feedback.py:127` monkeypatches
`llm_sentiment._get_client` by name as its "no model call is possible" poison
— repoint it at the registry's construct function, or that guard loses its
teeth silently. **[TEETH]** re-run its break-and-restore.

**Done when:** full radar suite green with no behavioural diff; `git diff`
shows no change to prompt bytes, schema, or stored values.

---

## Task 4 — Encoder backend

- `EncoderBackend(artifact_dir)`: validate at construction (read
  `active.json` + `config.json`, check files exist, check `heads` matches
  `_FIELD_ENUMS`, raise with the differing key named); build the ONNX session
  on first `judge_batch`; hold it for the process lifetime.
- `intra_op_num_threads=2`, `inter_op_num_threads=1`, `batch_size=4`,
  `pass_limit` 400.
- Tokenize `(prepared.target_ticker, prepared.author_text)` to the artifact's
  `max_len`; `argmax` per head through the artifact's class lists; `Usage(0,0)`.
- A session-load failure raises `SentimentUnavailable`, logs once, never falls
  back to another backend.
- `requirements.txt`: `onnxruntime`, `tokenizers`. **Not** torch.

**Tests** against a tiny real artifact committed as a fixture (a 2-layer
randomly-initialised model, a few hundred KB — the real 566 MB one never
enters git):

- enum-valid output for every head;
- verdicts keyed to the right `item.key` (shuffle the batch and check);
- refusal to construct on a head mismatch, with the key in the message;
- `Usage(0, 0)`;
- a corrupt session file yields `SentimentUnavailable`, not a crash.

---

## Task 5 — Trial write path

The task Codex's first correction demands, and the one most likely to be got
subtly wrong.

- `apply_judgments(..., write_tone: bool)`. When false: write
  `sentiment_relevance`, `sentiment_content_origin`, `sentiment_model`,
  `sentiment_prompt_version`, `sentiment_judged_at`, and the complete
  five-field history row. Do **not** touch `sentiment_attitude`,
  `sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment`.
  `legacy_projection()` is not called.
- `write_tone` comes from the backend/registry (`RADAR_JUDGE_TONE=0` default
  during the trial), not from a literal at the call site.

**Tests, all [TEETH] — these are the ones whose passing state is an absence:**

1. After a trial-mode pass, the mention's `sentiment_attitude`,
   `sentiment_expected_move`, `sentiment_confidence` and `llm_sentiment` are
   all still NULL, while relevance, origin, model and judged_at are set.
   *Break by setting `write_tone=True` and watch it fail.*
2. The history row for the same mention carries all five fields.
3. `_tone_of` on that mention returns what it returned before the pass (the
   legacy/lexicon chain), not a tone derived from the encoder.
4. `board.py`'s bull/bear `CASE` counts that mention the same before and
   after the pass.
5. `final_eligibility` still removes the mention when relevance is
   `irrelevant` — the trial's whole purpose still works.
6. `pending()` does not return the mention again (judged_at is set).
7. `train_radar_sentiment.load_rows` does not pick up trial rows.
8. With review enabled alongside trial mode, `_judgment_of` reads the history
   row rather than the NULL mention columns.

---

## Task 6 — Provenance, spend, label

- `MODEL_RATES['radar-encoder-v1'] = (0.0, 0.0)`. Explicit zero, because
  `None` means "unknown rate" and would report free tokens as `unpriced`.
- Fix `MODEL_RATES['claude-sonnet-5']` from `(3.00, 15.00)` to `(2.00, 10.00)`
  in passing; no Sonnet spend is booked so nothing is restated.
- Test: every registered backend id is ≤ 40 chars and present in
  `MODEL_RATES`. This fails in CI rather than in a MariaDB migration.
- `detail_panel` payload gains `judged_label` derived from `sentiment_model`
  through the registry; `Posts.tsx:86` renders it instead of the literal
  `'Claude'`. `judged_by`'s three-valued contract is untouched — tone
  precedence depends on it. Update `Posts.test.tsx`.

---

## Task 7 — Rollback recovery script

`scripts/rollback_encoder_judge.py`. Written and tested **before** the trial
starts, because an untested rollback is not a rollback.

- Select mentions with `sentiment_model = 'radar-encoder-v1'` and the current
  `PROMPT_VERSION`.
- Clear `sentiment_relevance`, `sentiment_content_origin`, `sentiment_model`,
  `sentiment_prompt_version`, `sentiment_judged_at` — returning them to the
  unjudged state that counts provisionally.
- Re-run `journal.sync_chatter_eligibility` for the affected windows and
  `journal.rebuild_windows` for those windows, one transaction per window, the
  same discipline `_sync_eligibility` / `_rebuild_corrected` already use.
- History rows are append-only and **kept**: they are the evidence of what the
  trial did.
- `--dry-run` is the **default**: prints affected mention and window counts,
  writes nothing. `--apply` and `--limit` bound a real run.

**Tests:** a seeded trial state is fully reverted; bucket counts return to
their pre-trial values; history rows survive; `--dry-run` writes nothing
(**[TEETH]**: assert via a read-only transaction guard, the way
`diagnose_extractor_feedback` already does).

---

## Task 8 — Full-suite verification

- Complete pytest suite and vitest, both green.
- `RADAR_JUDGE_PRIMARY` unset → judging disabled, no calls, no writes: the
  default must be inert.
- `anthropic:claude-haiku-4-5` → byte-identical requests to today (compare
  against the pinned prompt sha).
- `encoder` + trial mode → the Task 5 assertions hold end to end.

---

## Task 9 — Deploy the trial

1. Build the shipping artifact from `model-train13000` into the
   `active.json` layout; record the manifest in `config.json`.
2. `scp` to the VPS; `pip install onnxruntime tokenizers` into the shared
   venv (~50 MB, no torch).
3. 2 GB swapfile. It does not make an OOM impossible; it turns a spike into
   slowdown and buys time for the RSS trigger.
4. **Parity check before trusting it:** score the 200 audit rows through the
   deployed backend, compare verdicts with the PC's for the same weights. A
   mismatch means a tokenizer or opset difference and the trial stops here.
5. `RADAR_JUDGE_PRIMARY=encoder`, `RADAR_JUDGE_TONE=0`, review off, gate ON
   (one variable at a time). Restart `radar_ingest`.
6. Watch: the first cycle's log line, RSS, p95 backlog age, and the daily
   removal share against the §7.2 triggers.
7. **Schedule the fresh random audit the same day** — §7.2b gives it 7 days,
   and the trial ends automatically at day 10 if it has not been evaluated.

---

## Order, and what it costs

| task | roughly |
|---|---|
| 1. stage fix | half a session |
| 2. spec amendment | short |
| 3. seam + Anthropic backend | one session (the ~55 test moves are the bulk) |
| 4. encoder backend | half a session |
| 5. trial write path | half a session, most of the thinking |
| 6. spend + label | short |
| 7. rollback script | half a session |
| 8. verification | short |
| 9. deploy | half a session + Michi's deploy |

Two to three sessions. Tasks 1 and 2 can land tonight-equivalent without any
of the rest; they are improvements on their own terms.

## What this plan deliberately does not do

Turn the judge gate off; retire the lexicon; move the relevance head into
extraction; INT8 quantization; measure extraction recall. Each is named in the
spec's §7.4 with the reason. The extraction work in particular has its own
prerequisite: **every row we have is one the extractor accepted, so its recall
has never been measured** (`radar-extractor-recall-unmeasured`).

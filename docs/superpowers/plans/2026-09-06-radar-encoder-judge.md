# Radar encoder judge — implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` or
> `superpowers:subagent-driven-development` task by task. Follow the repository's
> handover discipline: one implementation worker, then an independent read-only
> review. Checkboxes describe future implementation, not completed work.

**Goal:** Add a local encoder as a controlled, recoverable live-traffic trial.

**Architecture:** Preserve Anthropic behavior behind a backend seam first.
Encoder writes materialize relevance/origin but preserve tone. A durable trial
record pins recovery evidence and enforces expiry independently of model calls.

**Tech stack:** Python, Flask/SQLAlchemy/Alembic, MariaDB, ONNX Runtime/tokenizers,
React/TypeScript, pytest/vitest, systemd. No torch runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md`
(revised after the build review against `dev_personal`, HEAD `1f965a9`).

## Global constraints and execution order

- Read the spec in full. Evidence and the controlled-trial ship decision are
  already reviewed; this plan implements the build corrections.
- Twelve commit/review units, in order:
  **1 → 2 → 3 → 4 → 5 → 6 → 7a → 7 → 7b → 7c → 8 → 9**.
  Original numbers remain stable. Task 1 lands alone and first; Task 2 is
  text-only; only Task 3 is a pure refactor.
- No production deployment or encoder activation before Task 9. Task 4 adds
  explicit adapter construction, not daemon selection. Environment/default
  changes belong to Task 7c, after recovery and evaluation exist.
- Preserve prompt/schema bytes and SHA256 pins, review precedence, enum
  validation, discard-never-default and the judge gate.
- Encoder: id `radar-encoder-v1`, batch 4, pass 400, threads 2/1, max_len 256,
  zero-token usage, explicit zero pricing, no backend fallback.
- Tone policy: encoder false; Anthropic primary/review/rejudge true.
  `RADAR_JUDGE_TONE=0` is encoder-only; reject nonzero in this build.
  Tone-promotion evidence never enables tone automatically.
- Bounded historical rejudging stays Anthropic-only and ignores daemon primary
  selection. Historical encoder rejudging is outside this live-traffic trial.
- Preserve unrelated dirty work. Before implementation, use an isolated workspace
  containing these revised documents. Create its per-plan progress ledger and
  `HANDOFF.md`; record branch/HEAD, task commits/reviews, tests, findings/rulings
  and deploy carries. Do not overwrite the root handoff for the unrelated Xetra
  project or redispatch completed ledger entries.
- For each unit: add its regression cases, observe intended failures, implement,
  run checks, perform marked mutations, restore mutations, rerun, review and
  commit only owned files. These implementation/VPS checks have **not** been
  run by this documentation revision.

**Commands:** Run Python commands with the project's usable venv interpreter
from `personal_apps/`, against the isolated test database. `python` below denotes
that interpreter; bare `python` on the shell is not assumed available.
`npm test` runs both vitest configurations; `npm run build` checks TypeScript.

**TEETH:** Each negative assertion gets its own targeted mutation. Forcing
`write_tone=True` does not prove history persistence, eligibility or expiry.

## File responsibilities

Paths in task lists are relative to `personal_apps/` unless prefixed `docs/`.

| file | responsibility |
|---|---|
| `features/radar/llm_sentiment.py` | canonical types/schema/prompt, common validation, batching, writes/routing |
| `features/radar/judge_backends.py` | protocol/Usage, adapters, pure metadata and explicit construction |
| `features/radar/judge_config.py` | environment parsing; no import-time construction |
| `features/radar/judge_trial.py` | lifecycle, retention floor, guards, bounded recovery |
| `features/radar/trial_audit.py` | pure sampling/gate/report calculations |
| `scripts/manage_encoder_trial.py` | arm/status/stop/tick CLI |
| `scripts/rollback_encoder_judge.py` | default dry-run and bounded apply CLI |
| `scripts/audit_encoder_trial.py` | sample/export-labels/evaluate/accept workflow |
| `deploy/radar-encoder-trial.service`, `.timer` | independent one-minute watchdog |

Adapters import canonical sentiment types/prompt helpers; `llm_sentiment` uses
type-only or local adapter imports to avoid a cycle. Registry metadata lookup
never creates an ONNX session or Anthropic client.

## Task 1 — Stage, not model id

**Files:** `features/radar/llm_sentiment.py`;
`tests/test_radar_sentiment_v2.py`, `tests/test_radar_llm_sentiment.py`.

**Interface:** Existing signatures stay. One bulk history query supplies this
batch's mention ids with stage review and current prompt version:

```python
review_stands = stage == 'primary' and mention.id in reviewed_ids
```

- [ ] Test primary → review → primary with shared id `same-backend` (different
  from `REVIEW_MODEL`): review fields survive, all histories append.
- [ ] Test two primaries using `REVIEW_MODEL` without review history: the second
  updates. Another mention's review and an older-prompt review cannot protect
  the target. **TEETH:** restore the old predicate and record missed-protection
  and false-protection failures.
- [ ] Test old-primary-id review eligibility and standing-review protection after
  changing ids. Remove only the primary-model candidate filter; keep activation
  cutoff, current prompt fence and reviewed NOT EXISTS.
- [ ] Implement the bulk lookup outside the materialization loop; history appends
  stay outside the guard. Test one lookup per apply call and repeated calls in
  the same uncommitted session.
- [ ] Run `python -m pytest tests/test_radar_sentiment_v2.py tests/test_radar_llm_sentiment.py`;
  restore mutations, rerun, review and commit this fix alone.

These tests are expressible today through the existing `model` argument; no
backend protocol or Task 3 dependency is required.

## Task 2 — Spec v2.1 amendment

**File:** `docs/superpowers/specs/2026-08-31-radar-sentiment-v2-final-design.md`.

- [ ] Amend §13: generative models remain excluded; the encoder is admitted only
  through this flagged trial. Keep §10.2 absolute gates for unconditional ship.
- [ ] Reference the new §7.1 trial table and separate tone criteria **within
  §7.1**, not nonexistent §7.1b. Amend §5.1/§5.3 to describe backend roles and
  reference the explicit trial write/recovery/expiry and promotion boundaries.
- [ ] Check contradictory prohibitions and references; review and commit. This
  task changes documentation, not runtime behavior.

## Task 3 — Pure seam refactor, Anthropic behavior preserved

**Files:** create `features/radar/judge_backends.py`; modify
`features/radar/llm_sentiment.py`, `scripts/rejudge_radar_sentiment.py`,
`scripts/build_sentiment_reference.py`; create `tests/test_radar_judge_backends.py`;
update sentiment/reference tests and `tests/test_diagnose_extractor_feedback.py`.

**Interfaces:** frozen `Usage(input_tokens, output_tokens)`; `JudgeBackend` as
spec §2.1; `AnthropicBackend(model, effort=None, *, client=None)` (adapter-level
test injection); `construct_backend(spec, *, effort=None, artifact_dir=None)`;
pure `backend_label(model_id)`. Anthropic batch/pass 20/400, supports_review true.
Public API: `judge(items, backend, on_usage=None, preamble=None)`.

- [ ] Test full request dictionaries, refusal/wrong shape/error handling and
  partial results. Preserve existing prompt/schema hash pins. Move shared enum
  filtering into judge before token shares: bad enums discard only their item;
  wrong batch shape raises `SentimentUnavailable`. Preserve usage integer totals.
- [ ] Move transport/JSON parsing to the adapter and translate `anthropic.APIError`
  there; retain lazy client construction. Explicit construction accepts Anthropic
  specs only here and does not read environment settings.
- [ ] Adapt passes to injected backends. Omitted arguments still select Haiku and
  Sonnet; review explicitly uses effort low. Keep legacy review flag/meters here.
  Batches/pass limits use adapter attributes with explicit test limit overrides.
  Rejudge explicitly constructs Haiku and uses its id for cost/spend/history.
- [ ] Preserve the reference CLI's existing effort heuristic **in this commit**,
  passing its result to the adapter. Removal/default changes move to Task 7c.
- [ ] Move caller tests to FakeBackend; retain FakeClient for adapter tests.
  Poison `judge_backends.construct_backend` in the diagnostic's no-call test.
  **TEETH:** deliberately reintroduce judging into the diagnostic and observe the
  poison fail; ensure the attempted call actually crosses the factory.
- [ ] Run radar/reference/diagnostic tests; compare explicit Haiku/Sonnet request
  dictionaries, stored fields, usage and meters with baseline. Review and commit
  only when behavior matches. Default none/startup/configuration are not in this
  commit's acceptance scope.

## Task 4 — Encoder adapter, explicit construction only

**Files:** `features/radar/judge_backends.py`, `requirements.txt`,
`tests/test_radar_judge_backends.py`; new fixture directory
`tests/fixtures/radar_encoder/` with active.json, v1/config.json, tokenizer.json,
model.onnx and README describing reproducible generation.

**Interface:** `EncoderBackend(artifact_dir)`; explicit encoder construction;
id must equal radar-encoder-v1, supports_review false, batch/pass 4/400.

- [ ] Create a tiny deterministic real ONNX fixture with distinct per-input
  outputs, so shuffled batches detect keying errors. Export tooling remains
  separate from runtime dependencies; no shipping weights in git.
- [ ] Validate files, pointer/id, max_len 256 and ordered head/class lists at
  construction (normalize JSON lists/Python tuples). Name differing keys.
  Load one CPU ONNX session on first use, threads 2/1. Tokenize ticker/text pairs,
  truncate/pad to max_len, use int64 tensors and map named outputs to heads.
  Return Usage(0,0).
- [ ] Latch session-load failure for the adapter lifetime; later calls raise
  SentimentUnavailable without load retries/fallback. Give the exception a
  log-once marker consumed by judge, avoiding repeated per-batch warnings while
  preserving ordinary Anthropic batch-failure logging.
- [ ] Test shuffled keys, partial final batch, ordered head mismatch, missing
  files/bad config, zero usage, lazy single load, corrupt-session containment and
  one log across batches/passes. Run `python -m pytest tests/test_radar_judge_backends.py`;
  review and commit. Daemon compatibility defaults still select Anthropic.

## Task 5 — Trial writes and history-based review routing

**Files:** `features/radar/{llm_sentiment,judge_backends}.py`,
`scripts/rejudge_radar_sentiment.py`; new `tests/test_radar_trial_writes.py`;
extend sentiment/detail/board/chatter-eligibility/training tests.

**Interfaces:** `apply_judgments(rows, judgments, stage, model, *, write_tone)`;
`writes_tone(backend)` (encoder false, Anthropic true);
`_judgment_of(mention, primary_history)` returns a complete Judgment or None.

```python
# Inside the existing not-review_stands branch only:
mention.sentiment_relevance = j.relevance
mention.sentiment_content_origin = j.content_origin
mention.sentiment_model = model
mention.sentiment_prompt_version = PROMPT_VERSION
mention.sentiment_judged_at = now
if write_tone:
    mention.sentiment_attitude = j.attitude
    mention.sentiment_expected_move = j.expected_move
    mention.sentiment_confidence = j.confidence
    mention.llm_sentiment = legacy_projection(j)
```

History appends all five fields even when the review guard blocks materialization.
Task 6 adds new provenance/diagnostic columns; do not reference them before its
migration exists.

- [ ] Thread required write_tone through all three callers. Live review uses its
  own Anthropic policy and independent prepared-text inference, never a copied
  encoder history answer. Rejudge remains Anthropic regardless of daemon env.
- [ ] Bulk-load latest primary history per candidate/current prompt by
  `(created_utc DESC, id DESC)`. Use all five fields even with populated old
  mention tone; retain candidate fences and reviewed exclusion. Missing history
  falls back only for non-encoder mentions with five valid fields; otherwise
  warn/skip. No per-row queries or defaulted Judgment.
- [ ] Add the following matrix; persistence assertions run after commit/reload.

| test | assertions / targeted mutation |
|---|---|
| fresh suppressed primary | four NULL tone columns; all five metadata/relevance fields set; exact full history; force tone true |
| populated suppressed primary | preserve all four differing old values; mutate suppression into clearing |
| projection poison | legacy_projection never called; reintroduce call even without assignment |
| surfaces | relevant/human-chatter row retains post tone, detail breakdown and board bull/bear counts; test legacy/lexicon separately |
| eligibility | irrelevant and broadcast each remove from actual journal/buckets; uncertain stays provisional; bypass sync |
| pending | materialized encoder row absent from next pending query; omit judged_at |
| partial/failure/history | absent verdict changes nothing; valid siblings persist; dropping any history field/write fails |
| training | fresh encoder rows excluded; preserved earlier tone/independent review labels may qualify; never fill training labels from encoder history |
| history routing | old prompt, multiple primaries, equal timestamps, old backend id, stale non-NULL tone; wrong history selection changes trigger/priority |
| missing history | complete non-encoder fallback; encoder/incomplete visibly skipped |
| live review | distinct Anthropic review writes five fields/projection, restores eligibility; histories survive; later primary cannot overwrite |
| shadow review | same history routing/demand accounting, no calls/verdict histories/tone writes; force live mode |
| bounded rejudge | Anthropic tone/spend/provenance unchanged despite encoder daemon env; no historical encoder path |

- [ ] Run `python -m pytest tests/test_radar_trial_writes.py tests/test_radar_sentiment_v2.py tests/test_radar_detail.py tests/test_radar_board.py tests/test_radar_chatter_eligibility.py tests/test_train_radar_sentiment.py`;
  restore targeted mutations, rerun, review and commit.

## Task 6 — Tone provenance, diagnostics, spend and label

**Files:** `models.py`; new Alembic revision in `migrations/versions/`;
`features/radar/{llm_sentiment,spend,detail_panel}.py`,
`features/radar/routes/api.py`, `static/radar/src/detail/Posts.tsx`, its tests
and `static/radar/src/types.ts`; migration/model/detail/spend tests.

**Schema:** nullable mention `sentiment_tone_model: String(40)`;
nullable history `displayed_tone: String(8)`, `displayed_tone_model: String(40)`,
`displayed_judged_by: String(8)`. These diagnostics are not new model heads.

- [ ] Migrate/backfill tone model from sentiment_model where attitude exists;
  leave unverifiable legacy-only ownership NULL. Test upgrade/backfill/downgrade.
- [ ] Write tone_model only with actual tone materialization, under both guards.
  Before an encoder write capture `_tone_of(...) or 'neutral'`, judged_by and
  tone model into its history diagnostics. Reuse pure helpers through local
  imports without querying the panel or creating an import cycle.
- [ ] Carry tone model through _posts and serialize_detail; add nullable
  judged_label only for judged_by=model. Pure registry metadata maps known
  Anthropic ids to Claude and unknown/missing to model. Update tuple unpacking,
  TypeScript payload and rendering; web requests never construct a backend.
- [ ] Test old tone plus new encoder relevance retains color/owner, unknown
  legacy owner is generic, fresh trial stays lexicon/None, independent review
  changes owner to Claude, late primary preserves review, and exact snapshots.
- [ ] Add encoder `(0.0,0.0)` and correct Sonnet-5 to `(2.00,10.00)`. Test all
  registered concrete ids <=40 chars and priced; reject too-long configured ids.
  Unknown historical ids remain renderable.
- [ ] Run migration/model/spend/detail tests, `npm test`, `npm run build`;
  review and commit with prompt/schema pins unchanged.

## Task 7a — Durable state and recovery retention pin

**Files:** `models.py`, new Alembic revision, `features/radar/judge_trial.py`,
`features/radar/retention.py`, `scripts/manage_encoder_trial.py`;
new `tests/test_radar_judge_trial.py`, retention/migration tests.

**Interfaces:** singleton schema/state fields exactly as spec §7.2a;
`arm_trial(now, *, artifact_sha256, baseline_report, baseline_removal_rate, seed)`;
`retention_floor()` returns timestamp/None; `request_stop(reason)`;
read-only `trial_status()`. CLI arm accepts those four named inputs, status is
read-only, stop requires `--reason`. Model/prompt are frozen from validated code.

- [ ] Implement singleton state/migration. Arm only once; never replace a row or
  reset its clock. Pin begins at next quarter-hour strictly after now minus 48h.
  Store baseline hash, p in (0,1], seed and ceil(400/p) sample size in recipe JSON.
- [ ] Journal/post pruning uses min(normal cutoff, retain_from) while armed,
  running or recovering. Arm and each prune chunk share DB advisory lock
  `radar_encoder_trial_retention`; release on the acquiring connection in finally.
  State/lock errors abort pruning rather than bypassing the pin.
- [ ] Test day-10/day-31 retention: whole windows including low-confidence-only
  events, posts, mentions/history survive inside pin; older evidence still prunes.
  Audit pass/primary none cannot release it; only recovered does. **TEETH:**
  restore either original cutoff and observe evidence loss. Test arm/prune race.
- [ ] Test duplicate arming, invalid hash/p/baseline, restart/status reads and
  serialized transitions. Stop persists; encoder activation still is not exposed.
- [ ] Run `python -m pytest tests/test_radar_judge_trial.py tests/test_radar_retention.py`
  plus migration tests; review and commit.

## Task 7 — Atomic bounded recovery across the retained trial

**Files:** `features/radar/{judge_trial,journal,buckets}.py`,
`scripts/rollback_encoder_judge.py`; new `tests/test_rollback_encoder_judge.py`;
journal/bucket tests.

**Interfaces:** `recover_trial(*, apply=False, limit=2000, now=None)` returns
total/selected mention and window counts, recovered count and remaining count.
Add keyword `commit=True` to journal.mark_promoted, buckets.rebuild_windows and
its internal helper; false propagates to every nested write and only flushes.

- [ ] Add injected failure after promotion/before totals proving the hidden
  commit defect. Add shared DB advisory guard `radar_bucket_write` alongside
  existing in-process guard at live rollup/rebuild and recovery entry points.
  Hold through commit/rollback; timeout raises, never runs unlocked. Acquire once
  per outer operation and release on its connection in finally, not in helpers.
- [ ] Propagate commit=False through nested rebuilds, preserving old defaults.
  Recovery owns one transaction per window subset: bucket guard → trial row →
  selected mention/event row locks → recheck frozen prompt/model/pin → clear
  five non-tone fields → sync journal → rebuild complete window → commit.
  Any failure rolls back the entire current window. Do not call hidden-commit
  helpers or the ordinary 48-hour horizon wrapper for historical recovery.
- [ ] Select encoder materialized winners at the frozen trial prompt, preserve
  independent review winners, tone/provenance and all history. Deterministic
  window/id ordering and positive mention limit permit a partial last window;
  rebuild it using all retained events, not only the selected mentions.
- [ ] CLI default/--dry-run writes nothing, including trial state; no model/service
  actions. Reject dry-run plus apply. --limit defaults 2000; show capped and total
  counts. Apply durably requests stop and drains a bounded subset; mark recovered
  only after a fresh zero-remaining count. Partial/failed runs keep the pin.
- [ ] Test ten-day recovery after actual retention, mixed sources/low confidence,
  partial windows, repeated/no-match runs, review winners, frozen prompt despite
  changed code, missing-pin/evidence errors and cross-process MariaDB lock order.
  Expected buckets equal the fixture with encoder decisions removed and review
  decisions retained.
- [ ] **TEETH:** restore nested commit and force failure; all current-window state
  must remain unchanged, earlier committed windows recovered. Poison every write
  in dry-run and run break-and-restore.
- [ ] Run `python -m pytest tests/test_rollback_encoder_judge.py tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_bucket_sources.py`;
  review and commit.

## Task 7b — Reproducible audit and acceptance record

**Files:** `features/radar/trial_audit.py`, `scripts/audit_encoder_trial.py`,
`features/radar/judge_trial.py`; new `tests/test_encoder_trial_audit.py`.

**Interfaces:** `wilson_interval(successes, total)` returns lower/upper, rejects
impossible counts and zero denominator; `evaluate_trial_audit(bundle)` returns
a report dict; `accept_audit(report_path, now)` verifies and persists result/hash.
CLI commands/files follow spec §7.2c.

```python
p = successes / total
z2 = 1.959963984540054 ** 2
denom = 1 + z2 / total
center = (p + z2 / (2 * total)) / denom
radius = (1.959963984540054 / denom) * (
    p * (1 - p) / total + z2 / (4 * total * total)
) ** 0.5
lower, upper = center - radius, center + radius
```

- [ ] Implement day-3 uniform sampling from the full frozen high-confidence
  traffic frame and armed recipe. Save frame/sample hashes and timestamps;
  reruns reuse ids. Insufficient traffic fails, not permission to shrink/change N.
- [ ] Export canonical inputs and blinded human files. Preserve original labels,
  adjudications/reasons and final reference separately. Obtain both predictions
  without apply_judgments; book paid calls through spend only, no mention/history
  mutation. Do not reuse the quota/enrichment reference sampler.
- [ ] Implement §7.2c exact denominators/Wilson gates and complete coverage;
  report each backend's counts/points/bounds and each failure. Tone criteria are
  separate and never determine trial pass/fail or enable tone. Use history tone
  snapshots for the shadow comparison.
- [ ] Report original audit halves separately and unified reversal/truncated-post
  disagreements; require supplementary data and inspection acknowledgments for
  a complete accepted report. Evaluate writes JSON/Markdown only. Accept verifies
  hashes/identity, draw/labels by day 7 and acceptance before day 10; a valid
  failure requests recovery. Invalid/late reports cannot certify/postpone expiry.
  Same-report acceptance is idempotent; different reports cannot silently replace
  a recorded result.
- [ ] Test hand-computed Wilson cases, point-pass/LCB-fail, equality, no removals,
  missing predictions, different removal denominators, absent mixed/none slice,
  shared reversal definition, reproducible prediction-independent sampling,
  blind exports/original label preservation, deadline boundaries and tampering.
  **TEETH:** replace LCB with point estimate and fail its boundary fixture.
- [ ] Run `python -m pytest tests/test_encoder_trial_audit.py tests/test_radar_judge_trial.py`;
  review and commit. Fresh production labels are a scheduled trial deliverable.

## Task 7c — Configuration, startup and automatic expiry

**Files:** `features/radar/{judge_config,judge_trial,judge_backends,llm_sentiment}.py`,
`run_radar_ingest.py`, `scripts/{manage_encoder_trial,build_sentiment_reference}.py`,
`deploy/radar-encoder-trial.service`, `.timer`; new
`tests/test_radar_judge_config.py`, daemon/trial/reference/diagnostic tests.

**Interfaces:** `resolve_settings(environ)` returns immutable backend specs,
review mode and tone policy; `initialize_judges(settings)` constructs/retains
selected instances; `tick(now, limit=2000)` uses Task 7 recovery;
`guard_encoder_trial(now)` fails closed on absent/mismatched/stopped/expired or
unavailable state. Disabled backend makes no calls/writes, supports_review false,
and is excluded from concrete pricing/provenance enumeration.

- [ ] Implement §2.3 parsing/precedence, default none, unknown/unsupported specs,
  artifact-directory override, role capability and encoder-only tone=0 checks.
  Web gauge and review pass share mode rules without web model construction.
- [ ] Initialize in main before fetchers/scheduler, outside enrichment catches;
  verify encoder's matching armed state/hash/prompt/pin, keep session lazy.
  Missing/mismatched identity fails startup; recovering/recovered resolves the
  effective primary to none with a visible log so ingestion can keep running.
  Primary none permits independently configured Anthropic review. Review backend
  none suppresses calls/stamps/meters regardless of shadow/live mode.
- [ ] First encoder materialization locks trial row and rechecks guard, then sets
  first_judged_at/status in the verdict transaction. No clock on failed/empty
  calls. Check before each encoder batch and before writing; discard late answers
  without history. No DB transaction spans inference. Anthropic materialization
  serializes with recovery while retaining its independent policy.
- [ ] Tick at expiry (first_judged_at + 10 days without timely passing audit)
  persists recovering before draining at most 2000 mentions. Retry partial/errors
  next tick with pin intact; errors return nonzero/log visibly. Startup checks
  the same guard. Audit pass does not release pin, reset time or change tone.
  No row or armed-without-first-write makes tick inert unless recovering;
  recovering drains regardless of first timestamp, recovered tick is a no-op.
- [ ] Ship oneshot service using the deployed app directory/venv, existing ingest
  user and environment file; timer `OnCalendar=*-*-* *:*:00`, Persistent=true,
  AccuracySec=1s. Resolve actual paths from the installed ingest unit in Task 9;
  no secrets or guessed server paths. Timer is independent of radar_ingest and
  needs DB access but does not construct a judge. Duplicate ticks serialize.
- [ ] Remove reference effort heuristic **now**: explicit --effort choices
  none/low/medium/high, default none. Update all Sonnet/Opus recipes to pass low.
  Test complete request dictionaries; keep review low and rejudge Haiku/none.
- [ ] Test flag precedence (including empty new flag), mode/backend combinations,
  unsupported role, startup errors before scheduling, lazy failure containment,
  retained instances, metadata/diagnostic no-construction. **TEETH:** move
  construction into the caught scheduled pass; startup-failure test must fail.
- [ ] Test atomic first clock, restart, exact expiry, failed/late audit, in-flight
  late answer, DB outage, stale encoder env after stop, daemon-independent tick,
  interrupted bounded recovery and pass-keeps-pin/tone. **TEETH:** bypass guard
  and demonstrate that expired/stopped write-prevention tests fail.
- [ ] Run config/trial/daemon/reference/diagnostic tests and review service files;
  commit explicitly as behavior changes, not a refactor.

## Task 8 — Full-suite and operational verification

- [ ] Run complete `python -m pytest`, `npm test`, `npm run build`. Separate
  pre-existing/environmental failures from regressions; unresolved required
  checks are not green.
- [ ] End-to-end: unset primary/review inert; explicit Haiku request parity;
  armed encoder tone suppression and eligibility; enabled independent review
  history routing and its own tone policy.
- [ ] Run day-10 recovery with real retention, dry-run, interrupted window and
  repeated ticks on isolated MariaDB. Verify complete buckets/review winners and
  shared cross-process locks, not substituted in-process-only mutexes.
- [ ] Record mutations/failures/restored runs; check coverage table, migration
  order and runtime dependencies. Independent read-only review closes before
  Task 9. Commit owned corrections/reports and update ledger/handoff.

## Task 9 — Package and deploy the guarded trial

**Deliverable:** create
`docs/superpowers/plans/2026-09-06-radar-encoder-judge-runbook.md` in the
implementation workspace; update ledger/handoff. Data artifacts stay outside git.

- [ ] Package model-train13000 FP32 into active.json/v1 with ordered heads,
  max_len 256 and manifest: seed, sizes/exclusions, input hashes, training/export
  HEADs and opset. Compute the three-file bundle hash exactly as spec §2.2 and
  record it outside config.json. Exploratory exporter model.onnx denotes INT8;
  explicitly select its FP32 output for shipping v1/model.onnx. No INT8 path.
- [ ] Record installed user/checkout/venv/environment paths; render concrete
  watchdog units. Record baseline report/hash, removal counts/p, seed/sample
  size and human labeler. Add exact monitoring commands, baseline interval and
  denominator, recovery commands and disk-capacity check for retained evidence.
  Missing baseline/labeling/operational inputs block arming.
- [ ] Deploy migrations/code with both backends none; copy artifact and install
  onnxruntime/tokenizers in shared venv, no torch. Set up 2 GB swap in the server's
  existing configuration. Verify service/migrations before activation.
- [ ] Compare all five verdicts for the same 200 rows on PC and VPS through the
  shipping adapter and weights; require exact parity and record hashes/output.
  A mismatch stops here.
- [ ] Enable independent timer and test its unarmed/inert tick while ingest is
  stopped. Arm singleton and verify pin before primary=encoder, tone=0, review
  backend none, review mode empty, gate ON; restart ingest.
- [ ] Verify first cycle and persisted first_judged_at, tone/history diagnostics,
  eligibility, RSS/backlog. Schedule actual day-3 sample/day-7 labels/day-10
  acceptance from that timestamp that day, not from deploy/restart time.
- [ ] Archive recovery dry-run; record stop/apply/resume/status/timer commands and
  retention storage cost. Check §7.2 operational triggers daily, RSS/backlog
  continuously during initial rollout; a trigger requests durable stop/recovery
  that day. Expiry enforcement is automatic.
- [ ] Draw at day 3, finish blinded labels/adjudication by day 7, evaluate/accept
  before day 10; preserve reports and inspection acknowledgments. Failure or
  incompleteness invokes/allows recovery. Pass only continues suppressed trial
  with its recovery pin.
- [ ] Handoff records deployed commits/schema/artifact, trial state, timer status,
  audit ownership/deadlines and recovery commands. Do not mark the fresh audit
  complete merely because deployment succeeded.

## Coverage and handoff

| spec | delivery / proof |
|---|---|
| §2 seam, validation, Anthropic requests | 3; 8 explicit-backend regression |
| §2 encoder layout/lifetime/failure | 4; 9 deployed parity |
| §2 config/roles/startup | 7c mode/startup matrix |
| §3 stage precedence | 1; 5 mixed-backend integration |
| §4 provenance/spend/label | 6 migration/API/UI tests |
| §4.1 writes/routing | 5; 6 snapshots; 8 end-to-end |
| §5 throughput/gate | 3/4 attributes; 8/9 checks |
| §6 amendment | 2 |
| §7.1/§7.3 audit/tone evidence | 7b; 9 scheduled audit |
| §7.2 retention/atomic recovery | 7a → 7; 8 crash/day-10 proof |
| §7.2b expiry/stop/retry | 7c; 8/9 watchdog |
| §8 deployment, §9 tests, §10 done | 8/9 and ledger |

The earlier two-to-three-session estimate omitted migrations, retention pinning,
transaction repairs and watchdog/evaluator. Re-estimate after review; do not
remove acceptance checks to meet it.

Gate removal, lexicon retirement, moving relevance into extraction, INT8,
extraction-recall measurement, historical encoder rejudging and actual tone or
unconditional promotion remain out of scope. Claude's next action is to review
these revised contracts, then implement from Task 1 in the isolated workspace,
recording independent reviews and progress in the ledger.

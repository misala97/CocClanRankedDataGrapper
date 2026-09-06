# Radar encoder judge — execution ledger

Binding documents, both at commit `6403248` in this workspace and byte-identical
to the source working tree they were carried from:

- Spec: `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md`
  (sha256 `e7d3175…a74802`)
- Plan: `docs/superpowers/plans/2026-09-06-radar-encoder-judge.md`
  (sha256 `603699e…252831`)

Evidence and the controlled-trial ship decision are already reviewed
(`2026-09-06-radar-local-judge-REVIEW-2.md`) and are not reopened here.

## Workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge`
- Branch: `codex/radar-encoder-judge`, created from `dev_personal` @ `1f965a9`
- Starting HEAD: `1f965a9`; docs carried in as `6403248`
- Source checkout `C:\Users\michi\Desktop\CodingStuff` stays on `dev_personal`
  and carries Michi-owned dirty work (Telegram/candidate JSON, `.agents/`,
  `.codex/`, scratchpad probes, measure scripts and their tests, and the two
  revised documents still uncommitted there). **Protected: never edited,
  staged, cleaned or committed from this plan.** The root `HANDOFF.md` there
  belongs to the unrelated Xetra rollout and is not touched.
- Alembic head before this plan: `e5f8b2ca4d36`; the dev database is at it.
- `.env` copied from the source checkout (gitignored, holds DB credentials);
  same arrangement the `radar-market-data-v2` worktree already uses.

## Execution mode

Inline, at Michi's instruction (2026-09-06): I implement and review each unit
myself rather than dispatching subagents. Per unit: write the regression cases
first, watch them fail for the stated reason, implement, run the focused
checks, perform the marked mutations, restore them, rerun, review the diff,
then commit.

## Environment facts established before Task 1

1. **No isolated test database exists.** `tests/conftest.py` runs every suite
   against the real local development MySQL 8 (`personal_apps`), shared with
   every other worktree. Task 6 and Task 7a migrations land there; the columns
   they add are additive and nullable, so other branches tolerate them. The
   plan's "isolated MariaDB" for Task 8 is read as this local MySQL 8;
   MariaDB-specific behaviour (`GET_LOCK`, JSON storage) is proven on the VPS
   in Task 9.
2. **The pytest interpreter lacks `onnxruntime` and `tokenizers`.**
   `C:\Users\michi\AppData\Local\Programs\Python\Python312\python.exe` has
   flask/sqlalchemy/anthropic/pytest/alembic but neither ONNX package. Task 4
   installs exactly the two packages it also adds to `requirements.txt`.
   The training/export environment is the separate
   `C:\Users\michi\Desktop\radar_encoder_venv` (torch, onnx, onnxruntime).
3. **The exported ONNX on disk is NOT the shipping model.**
   `radar_labels/encoder/artifact/config.json` records
   `source_model: model-train8600`; `model-train13000` exists only as
   `weights.pt`. The VPS benchmark and its "verdicts identical to the PC"
   result therefore describe train8600. Task 9 must re-export train13000 to
   FP32 ONNX and redo the parity check. Tasks 1-8 are unaffected.
4. **The Haiku-era baseline is time-bound.** The removal-share baseline
   (spec §7.2) and the removal proportion `p` (spec §7.2c) come from
   `radar_sentiment_judgments` rows written 2026-08-31..09-03. Those cascade
   with their posts under 30-day retention, so they disappear around
   2026-10-01. One read-only production query is a Task 9 preflight input.
5. **Audit labour, stated before arming.** `sample_size = ceil(400 / p)`; with
   the removal share near 0.30 that is roughly 1,300 blind human labels
   between trial day 3 and day 7.

## Interpretations applied without a new design decision

Recorded so a reviewer can disagree with the reading rather than guess at it.

- "No DB transaction spans inference" (spec §7.2a) means no *locking*
  transaction — trial-row `SELECT … FOR UPDATE`, advisory lock — is held
  across a model call. The ordinary read transaction that exists today during
  an Anthropic call is unchanged, which is what keeps Task 3 a pure refactor.
- Advisory locks are taken on a dedicated `db.engine.connect()` held by the
  outer operation and released in `finally` on that same connection: a session
  commit would return the locked connection to the pool. Non-MySQL dialects
  (the sqlite model tests) no-op the guard.
- The bucket advisory guard wraps every existing `BUCKET_WRITE_LOCK` site —
  `buckets.roll_up`, `buckets.rebuild_windows`, and scoring's write — through
  one context manager rather than a second, parallel lock discipline.
- New columns follow the existing `MYSQL_DATETIME(fsp=6)` and `with_variant`
  idioms; `recipe` is `sa.JSON` (a LONGTEXT alias on MariaDB — never
  `CAST(... AS JSON)`, which that server cannot parse).
- Ledger and handoff live beside the plan as
  `2026-09-06-radar-encoder-judge-ledger.md` and
  `2026-09-06-radar-encoder-judge-HANDOFF.md`, the convention the
  market-data-v2 plan already set. The repository root `HANDOFF.md` is the
  Xetra project's and is left alone.

## Commands

Python: `C:/Users/michi/AppData/Local/Programs/Python/Python312/python.exe`,
run from `personal_apps/`. Frontend: `npm test` and `npm run build` from
`personal_apps/`. Git from the worktree root.

## Task state

Order: 1 → 2 → 3 → 4 → 5 → 6 → 7a → 7 → 7b → 7c → 8 → 9.

| Task | State | Commit(s) | Focused tests | Review | Notes |
|---|---|---|---|---|---|
| 1 stage fix | **COMPLETE** | `fbbd774` | 63 v2+llm, 220 neighbours | inline, diff read | 3 mutations bit and were restored |
| 2 spec v2.1 amendment | **COMPLETE** | `af11dfa` | n/a (docs) | inline, diff read | six passages; §9 added beyond the plan's four |
| 3 seam refactor | **COMPLETE** | `43f9b35` | 279 across 10 suites | inline, diff read | parity proven by fingerprint diff |
| 4 encoder adapter | **COMPLETE** | `379cb9f` | 51 adapter, 255 wider | inline, diff read | 5 mutations bit; real ONNX fixture |
| 5 trial writes | **COMPLETE** | `645ad49` | 27 trial, 330 wider | inline, diff read | 9 mutations bit |
| 6 provenance/spend/label | not started | — | — | — | migration |
| 7a durable state + pin | not started | — | — | — | migration |
| 7 bounded recovery | not started | — | — | — | |
| 7b audit evaluator | not started | — | — | — | |
| 7c configuration/expiry | not started | — | — | — | |
| 8 full verification | not started | — | — | — | |
| 9 package + runbook | not started | — | — | — | no deploy without Michi |

## Task 1 record

Baseline before any change: 55 passed
(`test_radar_sentiment_v2.py` 45, `test_radar_llm_sentiment.py` 10).

Eight tests were written first and four of them failed against the unfixed
code, each for the bug's own reason:

- `…standing_review_survives_a_later_primary_from_the_same_id` —
  `assert 'positive' == 'negative'`: the missed-protection direction, a review
  verdict overwritten by a later primary sharing its id.
- `…two_primaries_under_the_review_id_do_not_protect_each_other` —
  `assert 'positive' == 'negative'`: the false-protection direction, a primary
  answer protecting itself because it was written by the review model.
- `…stage_lookup_is_one_query_for_the_whole_batch` — `assert 0 == 1`: no
  history lookup existed.
- `…previous_primary_id_stays_eligible_for_review` — `assert 58997 in []`: the
  review pool emptied by the primary-model filter.

The other four (neighbour's review, older prompt generation, uncommitted
review, standing review leaves the pool) passed both before and after; they
pin the new implementation's scoping rather than the old bug.

Implementation: `reviewed_at_this_version(mention_ids)` asks the history once
per `apply_judgments` call, scoped to the batch's judged mention ids, stage
`review`, and the current `PROMPT_VERSION`; `review_stands` reads that set.
`review_candidates` drops `sentiment_model == PRIMARY_MODEL` and keeps
`V2_ACTIVATION_CUTOFF`, the prompt-version fence and the reviewed
`NOT EXISTS`.

**Codex's blocker 1 is still closed.** The dropped filter never contributed to
it: `rejudge_radar_sentiment` books its work under `PRIMARY_MODEL` and
`apply_judgments` stamps the current `PROMPT_VERSION`, so what actually keeps
rejudged history out of live review spend is `RadarPost.created_utc >=
V2_ACTIVATION_CUTOFF` — untouched — with the prompt-version fence covering
rows never rejudged.

Mutations, each applied to the fixed code, observed, then restored:

| mutation | result |
|---|---|
| restore the `sentiment_model == REVIEW_MODEL` predicate | 2 failed, 51 passed |
| restore the `sentiment_model == PRIMARY_MODEL` candidate filter | 1 failed, 52 passed |
| make the lookup per-row instead of one bulk query | `assert 3 == 1` on the query-count test |

After restoring: 63 passed on the two suites; 220 passed across
`chatter_eligibility`, `detail`, `board`, `judge_gate`, `daemon`,
`diagnose_extractor_feedback`, `train_radar_sentiment`, `spend`.

## Task 2 record

The plan named §13, §10.2 and §5.1/§5.3. A fourth contradiction was found
while checking the document for them and is amended too: **§9's rollback
paragraph** ("Rollback disables Sonnet routing and/or reverts board reads to
the legacy projection. Additive fields and judgment history remain harmless")
is true of a change that only rescores and false of one that removes mentions
from the counting population — exactly the claim the new design's §7.2 exists
to correct. Leaving it would have left the spec asserting that switching the
backend off is a rollback.

§5.2 was amended as well, because §5.1's "the local arm now describes
backends" is only half the sentence: the encoder fills the *primary judgment*
role, and that is where "primary is a role, not a model name" belongs.

§14 was checked and deliberately left alone: "Shipping only the distilled
classifier, or only changing the prompt, is an experiment—not the completed
v2" already describes this trial correctly and needs no weakening.

Six amendment anchors, all marked *Amended 2026-09-06 (v2.1)* in place, plus
a summary in the document header. No acceptance gate was relaxed: §10.2's
five absolute gates stand unchanged as the bar for an unconditional
replacement, and the encoder still fails all five.

## Task 3 record

Proven, not asserted, to be a pure refactor: the pre-seam tree (`fbbd774`)
and the post-seam tree were each run against identical fake responses, and
their full request dictionaries, prompt bytes, verdicts and per-item token
attribution compared for both the Haiku and the Sonnet-with-preamble path.
Byte-identical. The prompt and schema sha256 pins never moved.

**One deliberate semantic difference**, recorded rather than hidden: a
successful response carrying no usage object now counts as one call with
zero tokens, where before it counted as no call at all. Anthropic always
sends usage, so production is unchanged — but a free backend must be able to
report `Usage(0, 0)` and still be seen to have run, which is what makes an
explicit 0.0 spend rate meaningful instead of "unknown". No test asserted
the old behaviour.

Validation deliberately did not move (spec §2.2). The adapter reports what
the model said, missing fields included; `_enums_valid` in `llm_sentiment`
is the single boundary, and it runs before the token split so a batch with
one botched item attributes its tokens to the items that were stored.

Tests split along the seam: vendor-shaped assertions to
`test_radar_judge_backends.py` with the fake client, pipeline-shaped ones to
a `FakeBackend`. The extractor diagnostic's poison moved from
`llm_sentiment._get_client` to `judge_backends.construct_backend` — the only
door to a backend now; the old name no longer exists, so poisoning it would
have passed while guarding nothing. **TEETH:** judging was reintroduced into
the diagnostic's own run and the poison fired.

Also pinned: the rejudge script constructs Haiku explicitly and books and
stores that id, and a dry run constructs no judge at all. It rewrites the
past, and the past must not acquire a different judge because a trial is
running later.

**Not covered:** `build_sentiment_reference.cmd_label`'s rewired call. Its
effort heuristic is preserved verbatim here by instruction, and Task 7c
replaces it with an explicit `--effort` flag and tests the request
dictionaries then.

## Task 4 record

The fixture is a real 12 KB ONNX graph and a real tokenizer, not a mock:
every risk in this adapter is a join between what the tokenizer emits, the
graph's input names, which output index is which head, and which class list
an argmax indexes — and a mock asserts that join against itself. It has no
weights; each head answers `(sum of unpadded ids + segment ids) mod
len(classes)`, so a test computes the expected verdict independently and can
assert which item got which verdict rather than that the answers differ.

Two fixture attempts were discarded for being too weak to catch the bug they
existed for: random weights collided on all five fields for two of four
ordinary inputs, and a version that accepted `token_type_ids` without using
it had the dead input pruned out of the graph by the exporter.

Mutations, each applied to the finished adapter and then restored:

| mutation | result |
|---|---|
| compare head classes as sets, not ordered tuples | 1 failed |
| drop the session-load failure latch | 1 failed |
| sort the batch before keying verdicts | 1 failed |
| stop feeding `token_type_ids` | 5 failed |
| drop the report-once marker | 1 failed |

Confirmed by import check: `judge_backends` pulls in neither onnxruntime,
tokenizers, numpy nor torch at import time, and constructing an Anthropic
backend pulls none of them either. The web process stays light.

## Task 5 record

`apply_judgments` gained a **required** keyword-only `write_tone`, which is
why 35 existing test call sites had to be edited: a required argument forces
every caller to decide rather than inherit. All three production callers read
it from the backend's declared policy via `judge_backends.writes_tone()`.

Review routing moved to history because the triggers read confidence,
relevance and attitude — all NULL on a suppressed row. `_judgment_of` takes
the newest primary history row for the current prompt version, ordered by
`(created_utc DESC, id DESC)` because one `now` stamps a whole batch and the
timestamp alone does not break ties.

Nine mutations, each applied to the finished code and restored:

| mutation | failures |
|---|---|
| force `write_tone` true | 11 |
| clear the tone columns instead of preserving them | 4 |
| drop a field from the history row | 2 |
| stop stamping `sentiment_judged_at` | 7 |
| route review from the mention instead of history | 1 |
| take the oldest history row instead of the newest | 2 |
| let an encoder-written mention serve as a fallback judgment | 1 |
| declare the encoder as tone-writing | 1 |
| hardcode `write_tone=True` in `run_pass` | 1 |

The last one is why `ToneFreeBackend` and the pass-level wiring test exist:
every other test calls `apply_judgments` directly and would have passed while
the pass ignored its backend's policy entirely.

Two of my own assumptions were wrong and caught by running: `board` exposes
`_tones`, not a `tone_counts` helper, and `train_radar_sentiment.load_rows`
keys its rows on `post_id`, not `mention_id`.

## Carried minor findings

(For the final whole-branch review. None yet.)

## Operator gates — Michi only, never bypassed

- Any deployment, artifact copy to the VPS, or trial arming.
- Any paid Anthropic call (audit labelling, prediction passes).
- Re-exporting `model-train13000` to ONNX: it runs on his PC in the ML venv
  and costs GPU/RAM and minutes, so it is asked for, not assumed.

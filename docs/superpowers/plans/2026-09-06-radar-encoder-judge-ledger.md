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
| 6 provenance/spend/label | **COMPLETE** | `524787b` | 363 py, 519 vitest | inline, diff read | 6 mutations bit; migration applied to dev |
| 7a durable state + pin | **COMPLETE** | `f320f6d` | 154 across 5 suites | inline, diff read | 7 mutations bit; found a lock self-deadlock |
| 7 bounded recovery | **COMPLETE** | `3fcfc0f` | 98 trial+audit, 44 scoring | inline, diff read | 7 mutations bit; 2 real defects found |
| 7b audit evaluator | **COMPLETE** | `3fcfc0f` | 32 audit | inline, diff read | landed with 7; 7 mutations bit |
| 7c configuration/expiry | **COMPLETE** | `769f66c` | 365 across 8 suites | inline, diff read | 5 mutations bit; corrected the deadline rule |
| 8 full verification | **COMPLETE** | `c236b1f` | 2251 passed, 1 environmental | inline | vitest 403+269, tsc clean |
| 9 package + runbook | **runbook delivered** | `c236b1f`, `64e9877` | n/a | inline | deployment awaits Michi |
| R3 Codex review fixes | **COMPLETE** | `b8f4a82`..`55793b1` | 261 across 9 suites; full suite below | inline, diff read | 6 findings, 15 mutations bit (1 survived and was fixed) |
| R4 Codex review fixes | **COMPLETE** | `aa380f4` | 245 across 5 suites; full suite below | inline, diff read | 4 findings, 4 mutations bit |

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

## Task 6 record

Alembic head is now `a1c4f7b2e6d8`; applied to the shared dev database,
backfilling 4301 of 4301 rows that carry a v2 attitude.

Six mutations bit: writing `sentiment_tone_model` unconditionally (3
failures), skipping the display capture (3), resolving the label from
`sentiment_model` (1), labelling regardless of `judged_by` (1), removing the
encoder rate so its tokens read as `unpriced` (2), and hardcoding 'Claude'
back into the serializer (1).

That last mutation initially **survived**, and finding out why exposed a
gap: nothing in the suite exercised `serialize_detail`'s post tuples at all,
so widening them would have reached the browser as a 500 rather than a red
test. The new detail-suite test pins the serializer as pass-through position
by position — and needed a deliberately non-Claude tone owner in the
fixture, because with every post Claude-or-nothing a hardcode is
indistinguishable from a pass-through.

## Task 7a record

Alembic head is now `b3d9e1f5a274`.

Seven mutations bit: journal pruning ignoring the pin (3 failures), post
pruning ignoring it (1), computing the cutoff once instead of per chunk (1),
letting a recovered trial keep pinning (2), allowing a second arming (1), and
a floor not landing on a quarter hour (1).

**A real defect the tests found:** `advisory_lock` opens a connection of its
own, so a nested acquisition blocked against its own outer holder for the
full timeout — a self-deadlock that reads exactly like contention with
another process. It is reentrant per thread now. The same class of bug then
turned up in `BUCKET_WRITE_LOCK`, which recovery nests: changed from `Lock`
to `RLock` in Task 7.

The cutoff-once mutation initially survived because the first version of the
arm-during-prune test armed on the FIRST floor read, which that mutation
still performs. It arms between chunks now.

## Task 7 record

Two defects found by writing the tests, both of which would have hung or
corrupted a real recovery:

- **`BUCKET_WRITE_LOCK` was a plain `threading.Lock`** and recovery nests
  the guard (it takes it for a window, then `rebuild_windows` takes it
  again). It is depth-guarded per thread now rather than made an `RLock`,
  because `RLock` has no `locked()` and `locked()` is how the existing
  "every bucket writer holds the lock while it writes" tests ask the
  question.
- **`~reviewed.exists()` in the recovery selection was wrong.** I wrote it
  to "preserve review winners", but a review WIN already fails the model
  filter; what the clause actually did was skip mentions whose ENCODER
  verdict was live merely because a review history row existed — leaving
  encoder decisions in the counts, `remaining` never reaching zero, and the
  retention pin never released. Removed, with a test for the case.

Mutations: nested commit restored (1), rebuild committing on its own (1),
clearing tone during recovery (1), ignoring the retention floor (1),
marking recovered before a fresh zero count (2), selecting by the live
prompt instead of the trial's frozen one (1), and selection ignoring the
model id so review winners are taken too (1).

**The dev database was damaged during this task and that is recorded here
rather than quietly fixed.** The Task 7a retention tests call the REAL
pruners against the whole table — deliberately, since a cutoff applied to
nothing proves nothing — and their fixtures were dated 2027, which put
every cutoff in the future. `prune_posts` and `prune_mention_events` then
deleted the development database's `radar_posts` (cascading to
`radar_mentions` and `radar_sentiment_judgments`) and
`radar_mention_events`. Buckets survived; production was never touched.
Michi's ruling: "I really dont care. Thats what the dev db is for." No
restore was performed.

The suite now lives entirely in 2020 and `prune_events`/`prune_posts`
wrappers refuse any cutoff later than 2021, so the mistake cannot be
repeated by editing one constant. Verified by restoring the 2027 dates: 7
tests fail with `this cutoff (2027-02-27) would delete real development
data` instead of deleting anything.

**Consequence for Task 8:** the dev database now has zero posts, mentions,
judgments and journal events. Suites that build their own fixtures are
unaffected; any that assume ingested data will fail for that reason, and
those failures must be reported as environmental with the reason named.

## Task 7b record

`trial_audit` is pure — no database, no model, no files — so the rules can
be read and argued with directly. Wilson bounds are pinned against values
computed independently in `decimal` at 30 significant digits.

A defect the tests found: a backend that removed NOTHING made
`removal_precision` raise, which aborted the whole evaluation instead of
failing that one criterion. Zero denominators now fail their criterion, as
the spec says.

Mutations: reading the point estimate instead of the lower bound for
removal (1) and for agreement (1), ignoring coverage (1), shrinking the
agreement denominator to answered rows (1), letting tone gate the trial
(5), letting a different report replace a recorded result (1), and
accepting a report after the deadline (1, in the trial suite).

The agreement-bound mutation initially survived: no fixture had an encoder
whose point estimate passed while its bound did not. One was added.

**Deviation, recorded:** `evaluate` takes prediction FILES rather than
producing them. The spec's four commands are all present, but generating
the two prediction sets means paid Haiku calls, and Michi's standing rule
is that quota is never spent unasked. The runbook documents that step as an
explicitly authorised one.

## Task 7c record

**A correction to my own earlier work.** `guard_encoder_trial` expired the
trial unconditionally at day 10. Spec §7.2b says "at expiry **without a
timely passing audit**": a trial that has tested its acceptance rules and
passed has answered the question the deadline exists to force, and keeps
running suppressed with its evidence pinned. The deadline is now lifted by
a passing audit and by nothing else, and the test that encoded the wrong
rule was replaced by three that encode the right one.

Mutations: construction moved into the caught scheduled pass (proved by
running `main()` with an invalid spec — it starts and schedules jobs, where
correctly placed it aborts with `unknown judge backend spec`), bypassing
the pre-pass guard (1 failed), never starting the deadline clock (1), and
not discarding late in-flight answers (needed a new test first — nothing
covered a batch outliving its trial).

**Two incidents during this task, both mine, both recorded:**

1. The startup teeth check called `main()` with a *valid* configuration
   under mutation, which **started the real ingest daemon**. It ran a cycle
   before I killed it (PID 18084), ingesting 476 posts and 614 mentions and
   writing 42 Reddit cursors, 3 source cursors and 203 poll-state rows. The
   cursor and poll-state rows made two tests fail; they were cleared. The
   posts and mentions were left — they are legitimate dev data and closer
   to a populated database than the empty one the earlier wipe left.
2. Stray `ZZT` buckets dated 2027, left by the trial fixtures *before* they
   were moved to 2020, tripped the daemon's rollup-bootstrap guard at
   startup. Buckets are never pruned by anything, so a fixture's residue
   outlives the run that made it. The wipe now removes every `ZZT` bucket
   regardless of date.

## Task 8 record

**Full suite: 2,251 passed, 2 failed in 10:54.** Frontend: vitest 403 + 269
passed, `tsc --noEmit` and both Vite builds clean. Single Alembic head
`b3d9e1f5a274`, chain intact.

Of the two failures, one was residue and is fixed; one is environmental and
stays. Neither is a regression.

**Fixed — `test_radar_scoring.py::test_each_ticker_is_screened_once_per_pass`.**
It asserts a scoring pass screens each ticker once and saw 185 screenings for
2 fixture tickers. Cause: the ingest daemon that started accidentally during
a Task 7c teeth check ran one cycle, creating buckets for 183 reddit tickers
in a 2-hour window on 2026-09-06. Nothing legitimate existed in that range
(zero rows on 09-05), so the residue was removed precisely: 8,874
bucket_sources, 262 buckets and 476 posts with `bucket_start`/`created_utc`
at or after 2026-09-06 09:00. Verified afterwards: scoring 44/44.

**Environmental, and named rather than left to be rediscovered:**

- `test_diagnose_extractor_feedback.py::test_the_full_run_is_read_only_and_recommends_nothing_yet`
  asserts the report contains a `LEGACY-POLICY cohort`, meaning mentions
  with `first_seen < 2026-09-01`. The dev database has none: the Task 7a
  wipe removed them, and the only mentions since are from the accidental
  daemon run, all dated today. It passed before the wipe (13/13 during the
  Task 3 teeth check). It is not a regression and was not "fixed" by
  planting an old row, which would be doctoring the environment to make a
  test green.

Frontend gates: vitest 403 + 269 passed, `tsc --noEmit` and both Vite
builds clean.

## Review round 3 record (Codex, 2026-09-06)

Codex reviewed `d11ab54` and would not merge: four P1 findings in write
fencing, recovery concurrency and audit validation, two P2s in guard
coverage, plus audit-tooling omissions and three stale doc passages. Every
finding was verified against the code before anything was changed; all six
held, and finding 1 was worse than stated. Fixed in a fresh session, one
commit per finding, tests first, mutations run and restored.

| finding | what was true | fix | commit |
|---|---|---|---|
| 1 (P1) stopped trial still receives judgments, can be resurrected | the post-inference recheck read the trial row through the session's identity map and repeatable-read snapshot -- for a stop committed by the CLI or the timer it never even queried; `note_first_judgment` then took a row lock too late and moved `recovered` back to `running` | the write side is one locked transaction: `lock_for_write` reads the row FOR UPDATE with `populate_existing`, re-validates with a fresh clock, and is held through the commit that lands spend, verdicts, history, journal flags and the clock together; `note_first_judgment` takes the locked row and only ever turns `armed` into `running` | `b8f4a82` |
| 2 (P1) deadline checked with the pass-start clock, no per-batch guard | `now` fixed at pass start | `judge()` asks `before_batch` before every batch; `run_pass` takes a `clock` it consults per batch and at the boundary | `b8f4a82` |
| 6 (P2) guard does not enforce the full armed contract | prompt version and model id never compared to the code's; gate-off selection could reach before the pin | `_may_judge` checks both identities; selection never picks a post older than `retain_from`; `refuse_outside_retention` at the write side | `b8f4a82` |
| 3 (P1) recovery erases a review that wins after selection; stale snapshot | planned ORM objects cleared under the guard without rechecking ownership; the plan's transaction kept its snapshot through the guard | the plan is ids only; each window opens a fresh transaction under the guard, locks the trial row, re-selects the planned mentions FOR UPDATE by the frozen identity, reads the journal as it is now; apply requires a stopped trial; the pin is released only after a count under the row lock and the retention lock | `9acd913` |
| 5 (P2) writers outside the bucket guard; stale score writes | startup invalidation and the backfill repair ran unguarded (the repair autoflushes throughout its loop); scoring's flush landed a z computed from a count recovery had since corrected | both take the guard; scoring's UPDATE is conditional on the count the z was computed from, skipped rows logged | `39798fb` |
| 4 (P1) an audit can lift the deadline without proving it audited this trial | `evaluate` took any files, made their keys the denominator; `accept` trusted the flag; empty verdicts agreed; a minimal report passed; acceptance possible before the first judgment | the chain: `sample` day-3/day-7/once with identity; new `predict` (exact ids, canonical inputs, frozen artifact, offline, metered, provenance header, `--confirm-spend` for paid); `evaluate` verifies sample reproduction, membership, provenance, validity, label provenance, shadow days from history, supplemental sets, completeness, input hashes; `accept` re-hashes, reproduces the verdict, requires acknowledgments against this report, checks day-3/day-7, then records; the primitive refuses a bare flag, an incomplete report, a foreign result, and a trial with no first judgment | `5d282cb`, `9726e8d` |
| docs | encoder spec section 6 and v2 spec section 10.2 still described the relative gate; the evaluator docstring too; runbook section 10 predates the chain | amended in place with dated notes; runbook follows the chain | `55793b1` (docstring in `5d282cb`) |

**Mutations, each applied to the finished code and restored.** Skipping
the per-batch check (1 failed), validating with the pass-start clock (1),
dropping `populate_existing` (1 -- the cross-process stop test), letting
the clock start a stopped trial (2, after a direct test was added: the
boundary refused first, so the second line had no test of its own),
clearing the planned objects without re-selecting (1), keeping the plan's
snapshot (1, re-run against the green suite), releasing without the
locked recount (1), scoring regardless of the count (1), backfill without
the guard (1), startup invalidation without the guard (1), accepting
without reproducing (1), skipping the provenance check (1), scoring an
invalid verdict as a verdict (5). **One survived**: dropping the
stray-label refusal -- the foreign file was still refused, for carrying no
valid label of any sampled row. The test is now a superset file (every
sampled row correctly labelled plus five strays), and the mutation bites
(`9726e8d`).

**Test adjustments, all deliberate.** The twelve apply-mode recovery tests
stop the trial first, as the CLI and the watchdog do. `report_for` in the
trial suite is a complete, schema-bearing report, because that is the least
the persistence step now accepts. The pure evaluator's `verdict()` helper
carries all five fields, because a three-field dict is not a verdict any
more. The three script round-trip tests and the pre-day-3 sampling test
were replaced by `test_encoder_audit_chain.py` (22 tests, real fixture
artifact for the prediction pass, fakes elsewhere). The old
`note_first_judgment(now)` clock test was replaced by one on the locked
row. Two of the new deadline tests initially passed for the wrong reason
-- their posts predated `V2_ACTIVATION_CUTOFF` and were never picked; they
use recent posts now and were watched to fail under mutation.

**Interpretations applied without a new design decision.**

- `recover_trial(apply=True)` refuses a trial that is not `recovering`
  or `recovered`. The CLI and the tick already stop first; a direct apply
  against a running trial was a way around the stop reason being recorded.
- The two supplementary sets (spec 7.3) and the inspection acknowledgments
  (spec 7.2c) are REQUIRED for a complete, acceptable report, as the spec
  says. The format is generic JSONL; the runbook gives the recipe for the
  200-row audit from the files on disk. The locked natural set has no
  stored per-row predictions (the training runs kept aggregates), so
  producing it means re-scoring 900 rows through the packaged artifact on
  the PC -- an owed operator step, recorded in the runbook. Michi may rule
  to waive it by amending the spec; the code enforces the spec as written.
- `predict` is a separate command rather than part of `evaluate`, keeping
  the earlier deviation's reason (an evaluating command must not spend),
  while closing the gap it opened (predictions of unknown origin).
- Spend for a pass whose answers are discarded at the boundary is NOT
  booked (rolled back with the rest), which is what happened before; spend
  for a pass discarded mid-batch by the per-batch guard is not booked
  either. The encoder's spend is zero-cost calls, so nothing is misstated.
- Codex's note on Task 3 -- a usage-less success counting as one call --
  is acknowledged as a deliberate metering change, not a pure refactor; it
  was already recorded in the Task 3 record and the commit. No change.

**Not done, and why.** No frontend was touched, so vitest and the Vite
builds were not rerun. The MariaDB-specific behaviour (`GET_LOCK`, `FOR
UPDATE`) is exercised on the local MySQL 8 as before; `FOR UPDATE NOWAIT`
appears only in a test probe, never in production code.

**Full suite after the fixes:** 2,300 passed, 1 failed, in 11:12. The one
failure is `test_diagnose_extractor_feedback.py::test_the_full_run_is_read_only_and_recommends_nothing_yet`,
the environmental `LEGACY-POLICY cohort` failure recorded at Task 8; no
regression. Task 8 had 2,251 passed; the 49 more are this round's tests
net of the five replaced.

## Review round 4 record (Codex, 2026-09-06)

Codex reviewed `128c9cc`: three P2s and a P3; everything else from round 3
closed against its own reproductions; the locked natural set to stay
hard-required (spec 7.2c). All four findings held.

| finding | what was true | fix | commit |
|---|---|---|---|
| 1 (P2) empty supplemental files satisfy completeness | `_supplemental` checked invalid rows only; two existing empty files gave `complete=True` and reached acceptance | membership frozen at arming (`arm_trial(..., supplemental=)`, `frozen_supplemental`; CLI `--supplemental-audit-keys`/`--supplemental-natural-keys`); `evaluate` requires every frozen key once, no extras, each audit row in its frozen half; any departure is an incomplete reason | `aa380f4` |
| 2 (P2) accept reproduces flags, not the report | booleans compared; numbers and supplemental content editable under a matching acknowledgment | `_report_from` shared by evaluate and accept; accept compares the JSON-canonical whole report minus `evaluated_at` | `aa380f4` |
| 3 (P2) lock wait carries the boundary past expiry | `when = clock()` before `lock_for_write` acquired the row | `lock_for_write(clock)`: lock, then read, validate with that reading, return `(row, when)`; the first-judgment clock starts from it | `aa380f4` |
| 4 (P3) row lock held into the retention lock | `break` on the recovered exit left the loop's FOR UPDATE open | `db.session.rollback()` before the break | `aa380f4` |

**Mutations, applied and restored.** Reading the clock before the lock (2
failed), dropping the rollback (1), skipping the membership check (4 of 5
-- the fifth is the wrong-half case, whose check that mutation left
intact), comparing flags only (2).

**Test adjustments.** Every arm helper (`arm`, `arm_now`, `armed`, the
chain fixture) passes a frozen membership; the chain fixture's matches the
rows its supplemental files hold. The four `lock_for_write(NOW)` calls
became `lock_for_write(lambda: NOW)` and unpack `(row, when)`.

**Interpretation applied.** The membership is frozen at ARMING because that
is where the spec fixes everything the evaluation may not choose for
itself; it makes the two membership files preflight inputs (runbook §0,
§7). Keys are strings; the recipe stores the sorted key lists and the audit
halves, not hashes, so an incomplete report can say what is missing.

**Full suite after the fixes:** 2,319 passed, 1 failed, in 11:56. The one failure is the environmental `LEGACY-POLICY cohort` failure recorded at Task 8; no regression. Round 3 had 2,300 passed; the 19 more are this round's tests.

## After round 4: Michi's rulings and what followed (2026-09-06)

- **No fifth Codex round.** Michi stopped the loop; the branch merges on
  the round-4 fixes.
- **No Haiku credits, ever again for this.** The incumbent's audit
  predictions come from a Haiku subagent inside Claude Code: `export-prompts`
  writes the API path's exact prompt text per batch, the subagent answers in
  the binding schema, `import-predictions` makes the prediction file with
  `via: claude-code-subagent` in its provenance header. Same enum boundary,
  same coverage rule; the report names the source. Four chain tests, one
  mutation (any value accepted as a verdict) bit. Commit `77b984e`.
- **The natural set stays required** (Codex, round 4) and now has a way to
  exist: `build_supplemental_sets.py` makes all four supplemental files from
  the PC's label files and the packaged artifact, scoring the 900 natural
  rows through the adapter. A row that cannot be built stops the build (one
  mutation bit). Same commit.
- **Audit size, open.** The armed recipe sizes the audit at `ceil(400/p)` =
  746 rows; Michi's next-steps note wanted 150-200. With 150 rows a good
  encoder fails the 0.93 lower-bound gate on noise alone (80 removal
  decisions: 78/80 -> 0.912). Recommendation recorded: keep 746, spread the
  labelling over days 3-7. Not changed.
- **The four supplemental files exist**, built on the PC into
  `C:/Users/michi/Desktop/radar_labels/supplemental/` (audit 200 rows in two
  halves of 100; natural 900 rows). The natural set reproduces the training
  run's recorded figures for train13000 exactly -- 401 predicted removals
  at precision 0.880, 53 reversals over 322 directional rows (0.1646),
  macro-F1 0.711 / 0.748 / 0.526 -- so the packaged artifact and the
  adapter's scoring path ARE the trained model. (The next-steps note's
  "relevance .711" is macro-F1; accuracy on the same rows is 0.846.)
- **Two docs commits overstated themselves** (`b1b49cc`, `bf91158`): each
  landed part of this edit while its message described all of it, because
  an edit script failed mid-way and the commit was chained behind it. The
  remainder is in the commit after this note. Lesson recorded: never chain
  a commit behind a fallible script.


- `llm_sentiment.py` still imports `os`, unused since Task 3 moved client
  construction into `judge_backends` (it is used twice on `dev_personal`).
  Found by an import scan after the review-3 fixes; left for the final
  whole-branch tidy rather than folded into a review-fix commit.
- `manage_encoder_trial.py`'s docstring still says `tick` "arrives with the
  watchdog"; it has been there since Task 7c.

## Operator gates — Michi only, never bypassed

- Any deployment, artifact copy to the VPS, or trial arming.
- Any paid Anthropic call (audit labelling, prediction passes).
- Re-exporting `model-train13000` to ONNX: it runs on his PC in the ML venv
  and costs GPU/RAM and minutes, so it is asked for, not assumed.


## Timing amendment — Michi, 2026-09-07

Michi approved changing the already-running trial from 3/7/10 to 1/2/3:
first-day frame and sampling from day 1, labels by day 2, acceptance before
day 3 or the existing watchdog stops and recovers it. Drawing hours late
is allowed through day 2 but never widens the first-24-hour frame or moves
the remaining deadlines. The original first-judgment timestamp, 746-row
recipe, quality thresholds, evidence pin, supplemental memberships and
seven-day tone qualification are unchanged; no rearming or database update.

Implementation is isolated on `codex/radar-trial-123` from production base
`d54c013`, excluding the newer training work on `dev_personal`. The runtime
change is the three shared timing constants; CLI terminology, existing
regression fixtures, spec, plan and runbook follow the same schedule.

Verification: three targeted schedule tests failed under the old constants
(deadline, guard, day-one sampling). After the update, **216 focused tests
passed**, covering trial/recovery, write fencing, audit chain and quality
gates, plus four explicit fixed-frame/late-draw cases. Tests used fresh
disposable LOCAL MySQL databases with a connection guard refusing every
other database; all temporary databases were removed. The first full run
found one clock-once fixture at the new expiry; its second write now occurs
on day 2, retaining the original test's purpose. No production tests or
shared-development data writes were performed. Independent read-only
review found no introduced blockers. Existing exact-deadline acceptance
versus watchdog boundary wording is outside this timing-only change.

Deployment carries: fast-forward the VPS checkout, preserving untracked
artifacts/reports, and restart `radar_ingest` and `personal_apps_web` to load
the constants. The watchdog is a fresh process on each minute's tick. No
dependency, migration, artifact, frontend or trial-row change is required.
Verify the live row remains running with first judgment
`2026-09-06 19:38:24.047717 UTC`; its new milestones are September 7/8/9
at **21:38:24 Berlin time**.


**Deployment verified:** runtime commit `d745e8e` was fast-forwarded onto
the VPS from `d54c013`; untracked reports/artifacts were preserved. Ingest
and web restarted successfully; the watchdog completed at
2026-09-07 00:57:02 CEST with exit 0. Read-only post-deploy checks confirmed
1/2/3 constants, running state, unchanged first judgment and retention
floor, sample size 746, tone shadow requirement 7, and refusal at the new
day-3 expiry. Ingest startup reports encoder primary, review off. No
trial-row or schema changes were made.

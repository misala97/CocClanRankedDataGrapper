# Review brief 3 for Codex — the encoder judge, built

You reviewed the evidence and the ship decision (`REVIEW-2.md`), then the
spec and plan. Both of those are settled and are **not** reopened here.

This asks a different question:

**Does the built thing do what the spec says, and is it safe to merge?**

Nothing is merged and nothing is deployed. The default configuration judges
nothing, so merging changes no behaviour on its own. Push hardest on §4 and
§5.

---

## 1. Where it is

- Branch `codex/radar-encoder-judge`, worktree
  `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge`
- 22 commits from `dev_personal` @ `1f965a9`; ~7,000 lines across 44 files
- Ledger: `docs/superpowers/plans/2026-09-06-radar-encoder-judge-ledger.md`
- Handoff: `…-HANDOFF.md`; runbook: `…-runbook.md`

Eleven plan units, each its own commit with its own tests and its own
mutations:

| unit | commit | what |
|---|---|---|
| 1 | `fbbd774` | stage read from history, not the model id |
| 2 | `af11dfa` | sentiment v2 spec amended to v2.1 |
| 3 | `43f9b35` | backend seam, pure refactor |
| 4 | `379cb9f` | encoder adapter |
| 5 | `645ad49` | trial write path (tone suppression) |
| 6 | `524787b` | tone provenance, diagnostics, spend, card label |
| 7a | `f320f6d` | durable trial record + retention pin |
| 7, 7b | `3fcfc0f` | bounded atomic recovery + audit evaluator |
| 7c | `769f66c` | configuration, startup, expiry watchdog |
| 8 | `c236b1f` | verification |
| 9 | `413967d` | artifact packaged, runbook |

**Verification:** full pytest 2,251 passed / 2 failed; vitest 403 + 269;
`tsc --noEmit` and both Vite builds clean; single Alembic head. Of the two
failures, one was residue from an accident of mine and is fixed (scoring is
44/44); the other is environmental and named in §6 below.

---

## 2. Six defects the tests found, and how they were fixed

Listed so you can judge the FIXES rather than re-find the bugs.

1. **`advisory_lock` self-deadlocked.** It takes a connection of its own, so
   a nested acquisition blocked against its own outer holder for the full
   timeout — indistinguishable from contention with another process. Now
   reentrant per thread via a thread-local set.
2. **`BUCKET_WRITE_LOCK` had the same flaw**, and recovery nests it (takes
   the guard for a window, then calls `rebuild_windows`, which takes it
   again). Depth-guarded per thread rather than changed to `RLock`, because
   `RLock` has no `locked()` and `locked()` is how the existing "every
   bucket writer holds the lock while it writes" tests ask the question.
3. **`~reviewed.exists()` in the recovery selection was wrong** — mine, and
   see §3.4.
4. **A zero removal denominator aborted the audit** instead of failing that
   one criterion.
5. **`guard_encoder_trial` expired the trial unconditionally** at day 10 —
   see §3.3.
6. **The board could 500 on a bad review flag.** The strict parser is shared
   by the daemon's startup and the board's over-ceiling gauge; a typo must
   stop the daemon, where somebody sees it, and must not take out every
   board request. The gauge now catches `ConfigError` and reads it as off.

---

## 3. Where I deviated, or made a judgement call

Each of these is a place I could be wrong. They are not buried in the diff.

### 3.1 Tasks 7 and 7b landed in one commit

Process slip, not design: I wrote 7b's additions to `judge_trial.py` before
committing 7, so splitting them afterwards would have been theatre. Both are
complete and tested. Cost: coarser bisect across those two units.

### 3.2 `evaluate` takes prediction files rather than producing them

The spec's four commands are all present, but generating the Haiku
prediction set means paid calls, and the standing rule here is that quota is
never spent unasked. An evaluation command that quietly spends is one
somebody runs twice. The runbook documents producing them as an explicitly
authorised step. **Is this the right call, or does splitting it create a way
to evaluate against a stale prediction file?**

### 3.3 A passing audit lifts the deadline

Spec §7.2b: the trial ends automatically "if the audit has not been
evaluated by day 10", and "evaluated means a valid passing report". I first
implemented an unconditional day-10 expiry, then corrected it: a trial that
has tested its acceptance rules and passed has answered the question the
deadline exists to force, so it keeps running — suppressed, with its
evidence still pinned, and needing a separate reviewed change to be
promoted. **Is that the right reading?** The alternative is that the trial
always ends at day 10 and a pass merely authorises a new one.

### 3.3b Only harm stops the trial now (changed after this brief was drafted)

The audit had four gating criteria, two measured relative to Haiku. Michi
pointed out what should have been obvious: there is no Haiku to fall back
to. The paid judge stopped on 2026-09-03 when the credits ran out, paying
again is not on the table, and radar has run with NO judge since. So the
alternative to this judge is nothing, and switching a working one off for
losing to a model that cannot run leaves the board strictly worse.

Changed in `5f3d877`, before any encoder has judged a production row:

- **One criterion stops the trial**: removal precision Wilson lower bound
  >= 0.93 absolute. Deleting real chatter is the only failure that leaves
  the board worse than no judging.
- The floor no longer moves with the incumbent.
- The Haiku comparisons are still computed and reported, and now feed
  `expansion_ready` — the separate later decision to turn the judge gate off
  and to display tone.

Spec §7.1 and §7.2c are amended to match, with the timing argument written
in: legitimate now, not on day 10.

**Please check**: is `passed` vs `expansion_ready` a clean split, and is
there anywhere else in the code or docs still asserting the old
beat-Haiku-or-stop rule?

### 3.4 Recovery selects only on model id, not on review history

I originally wrote `~reviewed.exists()` into the selection, reasoning from
"preserve independent review winners". That was wrong and the tests caught
it: a review WIN already fails the `sentiment_model == trial.model_id`
filter, so the clause's only effect was to skip mentions whose ENCODER
verdict was the live one merely because a review history row existed —
leaving encoder decisions in the counts, `remaining` never reaching zero,
and the retention pin never released. Removed, with a test for the case.
**Confirm the model filter alone is sufficient.**

### 3.5 A usage-less success now counts as one call

Task 3 was otherwise byte-identical (proven: pre- and post-seam trees run
against identical fake responses produced identical request dictionaries,
prompt bytes, verdicts and per-item token attribution). The one difference:
a successful response carrying no usage object used to count as no call at
all, and now counts as one call with zero tokens. Anthropic always sends
usage, so production is unchanged — but a free backend must be able to
report `Usage(0, 0)` and still be seen to have run, which is what makes an
explicit 0.0 spend rate meaningful rather than "unknown".

### 3.6 Task 2 amended two sections the plan did not name

The plan named §13, §10.2 and §5.1/§5.3. I also amended **§9**, whose
rollback paragraph ("Rollback disables Sonnet routing … additive fields and
judgment history remain harmless") is true of a change that only rescores
and false of one that removes mentions from the counting population — the
exact claim the new design exists to correct. And **§5.2**, because "primary
is a role, not a model name" belongs there rather than in §5.1.

---

## 4. What I want attacked hardest: recovery

`features/radar/judge_trial.py::recover_trial`. This is the highest-risk
code in the branch, because it is the thing that makes the trial reversible
and it runs during an incident.

The claims:

- **Atomic per window.** Bucket guard → trial row `FOR UPDATE` → clear the
  five non-tone fields → sync journal eligibility → rebuild the window from
  ALL its retained events → commit. A failure rolls that window back whole
  and leaves earlier windows recovered.
- **Resumable**, because a cleared mention no longer matches the selection.
- **Bounded by mentions**, exactly, with a partial last window permitted —
  the window is rebuilt from all its events either way.
- **Tone is never cleared.** The trial did not write it.
- **`recovered` only after a fresh zero count**, because that is what
  releases the retention pin.

Two hidden commits had to be removed first: `journal.mark_promoted`
committed in the middle of a bucket rebuild that committed again at its end.
Both now take `commit=False`; live callers keep the old default.

Questions I cannot answer about my own code:

- Is the lock ORDER right everywhere (bucket guard, then trial row), and is
  there a path that takes them the other way round?
- `_mark_recovered` takes the retention lock while recovery's per-window
  transactions take the bucket guard and a row lock. Different mechanisms
  for the same row — is that a gap?
- The partial-last-window case rebuilds a window while some of its mentions
  are still judged. That is a consistent intermediate state and the next run
  finishes it. **Is it?**
- Does anything still write buckets outside `bucket_write_guard()`?

---

## 5. Second: the trial guard, and whether a judgment can escape it

`guard_encoder_trial` is consulted at startup, before every batch, and again
before a verdict is written. The third is not redundant: a batch can outlive
its trial when a stop, a failed audit or the deadline lands while it is in
flight, and a late answer must be discarded rather than stored.

`note_first_judgment` starts the deadline clock in the SAME transaction as
the first materialized verdict — never at startup, never from a failed call.

- Is there a path where the encoder writes a judgment with no armed trial,
  or after one has ended?
- The encoder refuses to start unless the deployed artifact's bundle hash
  matches the armed trial's. Is hashing the three files in a fixed order the
  right identity?
- A trial found `recovering`/`recovered` at startup disables judging with a
  log and lets ingestion continue, rather than failing the daemon. Right
  call for a stale `RADAR_JUDGE_PRIMARY=encoder` surviving a rollback?

---

## 6. Two incidents, recorded rather than tidied away

Both mine, both in the ledger.

1. **I deleted the development database's radar tables.** The Task 7a
   retention tests call the REAL pruners against the whole table —
   deliberately, since a cutoff applied to nothing proves nothing — and
   their fixtures were dated 2027, putting every cutoff in the future.
   `prune_posts` and `prune_mention_events` then removed all posts,
   mentions, judgment history and journal events. Buckets survived;
   production was never touched. Michi's ruling: dev data is disposable, no
   restore. The suite now lives in 2020 behind wrappers that refuse any
   cutoff past 2021, verified by restoring the old dates and watching seven
   tests refuse instead of delete.

   **Consequence:** `test_diagnose_extractor_feedback.py::test_the_full_run_is_read_only_and_recommends_nothing_yet`
   now fails because it wants a `LEGACY-POLICY cohort` and the database has
   no mentions at all. It passed before the wipe. It was NOT made green by
   planting an old row.

2. **A teeth check started the real ingest daemon.** Verifying that startup
   aborts on a bad judge spec, I called `main()` with a *valid* one under
   mutation; it started and ran a cycle before I killed it. Its cursor rows
   and 183 tickers' worth of buckets broke two tests; the residue was
   removed precisely and both pass again.

---

## 7. The numbers, for context

Preflight inputs captured since the plan:

- **Haiku baseline**, read-only from production before those rows age out
  around 2026-10-01: 16,297 judged, 8,747 removed, **p = 0.5367**, so the
  audit is **746 rows**, not the ~1,300 the plan assumed from the
  quota-stratified label set's irrelevant rate.
- Composition: 5,589 broadcast-only, 2,509 irrelevant-only, 649 both. **Two
  thirds of what the paid judge removed is broadcast/automated content**,
  not junk tickers — which is a different problem from the one the queued
  extraction work targets.
- **The artifact was the wrong model.** The existing export was
  `model-train8600`; `model-train13000` existed only as `weights.pt`.
  Re-exported, and verified by re-scoring the 200-row audit: relevance
  75.5%, origin 93.5%, attitude 79.5%, move 85.0%, removal precision 0.968,
  recall 0.728, 3/54 flips — every figure reproducing the ledger exactly.
  The stored verdicts in that file agree on only 128/200, because they were
  train8600's. The §6 parity check would have compared the wrong model
  against itself and passed.

---

## Where to look

- Recovery and the trial: `personal_apps/features/radar/judge_trial.py`
- The seam and adapters: `…/judge_backends.py`
- Writes and routing: `…/llm_sentiment.py` (`apply_judgments`,
  `_judgment_of`, `latest_primary_history`, `run_pass`)
- Configuration: `…/judge_config.py`
- Audit arithmetic: `…/trial_audit.py`
- Locks and atomicity: `…/buckets.py`, `…/journal.py`, `…/retention.py`
- Tests: `test_radar_judge_trial.py` (55), `test_radar_trial_writes.py`
  (41), `test_radar_judge_backends.py` (40), `test_encoder_trial_audit.py`
  (25), `test_radar_judge_config.py` (23)

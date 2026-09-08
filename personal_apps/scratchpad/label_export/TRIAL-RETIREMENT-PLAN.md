# OPERATIONAL PLAN — retire the encoder trial, ship base, destroy nothing

**Revision 2, corrected 2026-09-07 ~23:30 UTC** against production and against
deployed `main`. Revision 1 is superseded; §A lists what was wrong in it and why
that mattered, so nobody re-derives a corrected claim from a stale one.

Verification stamp for everything below:

| what | value | how |
|---|---|---|
| production host | `194.164.29.97:/root/coc-stats` | ssh |
| production HEAD | `b1d1a7c47e53017d7728635f3fe5685a959bbec6`, branch `main`, clean | `git rev-parse HEAD`, `git status --porcelain` |
| local `main` | same sha — **so `git show main:…` IS the deployed file** | `git rev-parse main` |
| production clock at verification | `2026-09-07 22:38:29 UTC` | `date -u` |

All line numbers below are deployed `main` and were read out of
`git show main:<path>`, not out of this checkout.

> **EXECUTION LOG — Phase 1, 2026-09-07/08. SHIPPED to `main` as `45a7e39`.**
> §2.1 (artifact preserved at `radar_labels/artifact-small-v1`, bundle
> re-derived as `3bb32b5607a8a368…dccb5`), §2.3 (the three hunks plus the two
> stale tone docstrings) and §2.4 (tests) are done, committed, merged to `main`
> and pushed. Full suite: 2,462 passed, 1 pre-existing unrelated failure
> (`test_diagnose_extractor_feedback.py` wants a legacy-policy cohort the dev
> DB has no rows for — reproduced identically on unmodified `main` in a
> separate worktree against the same database).
>
> **Not run, and not mine:** §2.5 (deploy) and §2.6 (verify on the box).
> §2.2's timer mask is now **unnecessary** rather than pending: pre-deadline
> the timer already returns `{'action': 'none'}`, and once this commit is
> deployed Hunks A and B make it harmless permanently. It stays in this
> document as the fallback if the deploy slips past 2026-09-09 19:38:24 UTC.
> Production at 2026-09-07 23:41 UTC: `running`, audit columns NULL, 1,600
> judgments, timer enabled and active. Everything in §3 (Phase 2) is untouched.
>
> Two things the execution found that this document did not predict:
> - **8 tests went red, not 5.** The extra three are in
>   `test_radar_trial_writes.py` (the write-boundary deadline tests) and one
>   more in `test_radar_judge_trial.py`; `test_an_unevaluated_trial_still_expires_on_day_ten`
>   is really `…_on_day_three` after `d745e8e`. All 8 pinned the un-retired
>   semantics; none was a regression. They now take a shared `unretired`
>   fixture (`tests/conftest.py`) rather than a monkeypatch each.
> - **`tick()` had no test at all**, and `scripts/manage_encoder_trial.py` had
>   none either. Writing the CLI test surfaced a **pre-existing bug**:
>   `cmd_stop` read `row.status` after its `app.app_context()` closed, so the
>   command committed the stop and then died with `DetachedInstanceError` — a
>   traceback for a command that had in fact worked, on the one command where
>   believing it failed is worst. Fixed in the same commit.

---

## 0. VERIFIED FACTS

### 0.1 — The live trial row

`SELECT … FROM radar_judge_trial` on production:

```
id 1 | status running | model_id radar-encoder-v1
prompt_version     radar-sentiment-v2-attitude-origin-candidate-1
artifact_sha256    3bb32b5607a8a368…
armed_at           2026-09-06 19:32:33.651862
first_judged_at    2026-09-06 19:38:24.047717
audit_evaluated_at NULL
audit_passed       NULL
retain_from        2026-09-04 19:45:00
stop_reason        NULL
```

Production schedule is `AUDIT_DRAW_DAY = 1 / AUDIT_LABEL_DAY = 2 /
TRIAL_DEADLINE_DAYS = 3` (`judge_trial.py:576-578`). This checkout
(`dev_personal`) still carries `3 / 7 / 10`. Therefore:

- **Deadline: `2026-09-09 19:38:24 UTC`** — 45.0 h after the verification stamp.
- **Labelling window closes `2026-09-08 19:38:24 UTC`** — 21.0 h after the
  stamp. It is **open right now**. Revision 1 said this had "probably already
  closed, by luck". It has not. The `accept` route in §5.2/§5.3 is a live
  destructive path for another 21 hours, not a theoretical one.
- **Every `manage_encoder_trial` / `audit_encoder_trial` command run from
  `C:\Users\michi\Desktop\CodingStuff` against the production database computes
  with 3/7/10 and lies.** `tick` reports `action: none` on an expired trial;
  `accept` refuses a valid day-1 draw. Trial commands run on the VPS from
  `/root/coc-stats`, or from a checkout of `main`. Nowhere else.

### 0.2 — What is at risk, counted

```
radar_mentions WHERE sentiment_model = 'radar-encoder-v1'      → 1,546
radar_sentiment_judgments WHERE model = 'radar-encoder-v1'     → 1,546
  first 2026-09-06 19:38:24.051349   last 2026-09-07 22:39:27.100972
```

**1,546 is smaller than the watchdog's `--limit 2000`.** A single `tick` on an
expired or `RECOVERING` trial therefore drains *the entire trial in one
firing*, reaches `remaining == 0`, flips the row to `RECOVERED`
(`judge_trial.py:553-557`) and releases the retention pin. Revision 1 described
this as "would drain 2000 mentions", implying a partial, interruptible drain.
It is total and it completes inside one minute.

### 0.3 — The systemd picture, and the race Revision 1 missed

```
radar-encoder-trial.timer    enabled, active   OnCalendar=*-*-* *:*:00, Persistent=true
radar-encoder-trial.service  Type=oneshot, Restart=no
   ExecStart=/root/coc-stats/venv/bin/python -m scripts.manage_encoder_trial tick --limit 2000
radar_ingest                 active            Restart=always, RestartSec=30
```

Three ways `tick()` reaches an expired row:

1. **The timer**, every minute. Disabling it removes this one.
2. **`run_radar_ingest.py:1272`** — `judge_trial.tick(dt.datetime.utcnow())` at
   daemon startup, deliberately before `judge_config.initialize_judges` at
   `:1275`. Any start of the daemon runs it.
3. **`Restart=always` / `RestartSec=30` on `radar_ingest`.** This is the one
   nothing in Revision 1 covers. After 19:38:24 UTC on 09-09, *any* crash of
   the ingest daemon — an unhandled fetcher error, an OOM, a host reboot —
   restarts it 30 s later on unpatched code, and path 2 fires. Masking the
   timer does not touch it, and it needs no operator at all.

What is **not** a risk, verified: `update_coc.sh` stops `radar_ingest` *before*
`git reset --hard origin/main` and starts it *last*, so a normal deploy's
startup tick always runs the code that deploy installed.

What is also **not** a risk: with the timer off and no restart, passing the
deadline is non-destructive. `run_pass` calls `guard_encoder_trial`
(`llm_sentiment.py:791`), which raises `TrialError`, which
`_scheduled_sentiment`'s broad handler catches and logs
(`run_radar_ingest.py:1144-1152`). Judging stops; nothing is undone; the daemon
lives. The deadline only destroys through `tick()`.

### 0.4 — The rollback artifact exists **twice**, byte-identical

| copy | model.onnx | tokenizer.json | config.json |
|---|---|---|---|
| production `…/artifacts/judge/v1/` | `e97bcb96…d72e174` | `20643390…385a854a` | `fb20c709…3790c69341` |
| `CodingStuff-worktrees/radar-encoder-judge/personal_apps/artifacts/judge/v1/` | identical | identical | identical |

Bundle over the three in `judge_backends.bundle_sha256`'s fixed order
(`judge_backends.py:224-244`) = `3bb32b5607a8a368f…dccb5`, which is the armed
`artifact_sha256`. Production `active.json` = `{"path": "v1/", "id":
"radar-encoder-v1"}`. Its `config.json` records `max_len: 256`, `base:
microsoft/deberta-v3-small`, `source_model: model-train13000`,
`packaged_at_git_head: 221095c`.

It still cannot be *rebuilt*: `package_encoder_artifact.py:191` stamps
`packaged_at_git_head` into `config.json` and `config.json` is inside the hash,
so any repackage yields a different bundle. But Revision 1's "the only
byte-exact copy outside the VPS" framing understates the position — production
holds one too, and the local copy is a backup of it, not the original.

### 0.5 — `source_config_version` is untouched by this plan, by construction

Latest stored bucket carries `3f96922d51fe4ef0` (966,327 buckets total;
`3f96922d51fe4ef0` is the newest generation, max `bucket_start` 2026-09-07
22:30). `config.py:832-874` hashes sources, token/stopword tables, the cashtag
and bare patterns, the reddit fetcher, the extraction policy generation and the
rollup generation. **It hashes nothing about the trial, the retirement switch,
the artifact, the encoder's dimensions or its max_len.** No step in this plan
touches an input to it. Keep extraction work out of this change and the stamp
cannot move.

### 0.6 — Citation drift: the real offsets

Revision 1 §0.1 asserted "all reader citations at `judge_trial.py` ≥ 575 are
one line low". That is false, and it then used the wrong numbers throughout its
own §1 and §2. Measured against deployed `main`:

| symbol | Revision 1 said | deployed truth | drift |
|---|---|---|---|
| `AUDIT_DRAW_DAY` / `LABEL_DAY` / `DEADLINE_DAYS` | 576/577/578 | 576/577/578 | ✔ |
| `deadline()` passing-audit exit | 597-598 | 597-598 | ✔ |
| `accept_audit` incomplete-report refusal | 625-626 | 626-627 | +1 |
| `accept_audit` one-way ("already has a recorded audit") | 637-641 | 639-643 | +2 |
| failing audit sets `RECOVERING` | 657-660 | 657-661 | ✔ |
| `_may_judge` refuses a missing row | 669-672 | **679-682** | **+10** |
| `_may_judge` model-id check | 673-677 | **683-686** | **+10** |
| `_may_judge` prompt-version check | 682-686 | **687-691** | **+5** |
| `_may_judge` refuses `RECOVERING`/`RECOVERED` | 689-690 | **692-693** | **+3** |
| `_may_judge` deadline raise | 695-697 | 694-697 | −1 |
| `tick` `RECOVERING` → `recover_trial(apply=True)` | 785-789 | **799-803** (call at **801**) | **+14** |
| `tick` expiry → `request_stop` + recover | 790-792 | **805-816** (call at **814**) | **+14** |

Everything below `judge_trial.py:600` is unshifted. Citations into
`judge_config.py`, `judge_backends.py`, `trial_audit.py`, `retention.py`,
`spend.py`, `audit_encoder_trial.py`, `rollback_encoder_judge.py`,
`manage_encoder_trial.py`, `llm_sentiment.py` and `run_radar_ingest.py` were
each re-read and are correct as written, with one exception noted in the
handover (`judge_config.py:173-178` → **`:179-184`**).

---

## 1. THE ARTIFACT BLOCKER — Phase 2 cannot start today

**Revision 1 §0.3 said "the base checkpoint is present and packageable". It is
present and it is NOT packageable.** Verified:

```
C:/Users/michi/Desktop/radar_labels/encoder/model-train17090-20260907-192428/
  config.json:32   "max_len": 512          base: microsoft/deberta-v3-base
  weights.pt       735,464,799 bytes
C:/Users/michi/Desktop/radar_labels/artifact-base/   → does not exist
```

One number has to agree in three places, and 512 fails at both gates:

1. `package_encoder_artifact.py:55` `MAX_LEN = 256`; `:122-124` raises
   `SystemExit('the trained model uses max_len 512; this build reads 256
   tokens')`. **Packaging stops here.**
2. The export bakes the sequence length into the graph:
   `:161-163` tokenizes one example with `padding='max_length',
   max_length=MAX_LEN`, and `:174-175` makes **only axis 0 (batch) dynamic**.
   The sequence axis is fixed at whatever `MAX_LEN` was.
3. `judge_backends.py:163` `ENCODER_MAX_LEN = 256`; `:279-282` raises
   `EncoderArtifactError` for any artifact whose `config["max_len"]` differs,
   and `:218` / `:334-335` make that number the runtime tokenizer's
   pad-and-truncate length.

Hidden size is not part of the problem: `MultiHead.__init__` reads
`self.encoder.config.hidden_size` from the backbone
(`train_encoder.py:201-205`), and nothing in `_validate` inspects hidden size,
layer count or vocabulary. A 12-layer/768-hidden base model would load happily
if the `max_len` numbers agreed.

### 1.1 — Measurement that bears on the choice

Tokenized the full 50,000-row label export
(`radar_labels/export-2026-09-05.jsonl`) with the base checkpoint's own
`tokenizer.json`, as the pair `(ticker, author_text)` — exactly what
`train_encoder.py:182` trains on and what `judge_backends.py:361-363` judges:

```
median 50   p75 92   p90 212   p95 397   p99 2,897   max 17,125
over 256 tokens:  8.16%
over 512 tokens:  3.94%
```

So the 512 window fully covers **4.2 percentage points more** of the population
than 256 does; both truncate the same long tail. This bounds how much the
window can be worth on this data. It does **not** show that base-at-256 scores
as well as base-at-512 — nothing measured does, because no base-at-256 run
exists.

### 1.2 — Resolution: ship the 512 weights, widen the window check

**Decision recorded 2026-09-08: no retraining.** More labelled data is coming
and a GPU run is a cost that is not being paid twice for this. That removes the
"retrain base at `--max-len 256`" option entirely, and makes the constant change
the path rather than a fallback.

Two things an earlier draft of this section overstated against that choice, both
corrected here:

**Throughput is not a constraint.** Measured: 1,546 judgments over 27.0 h =
**~57 rows/hour**. Capacity at the deployed small@256 is `ENCODER_PASS_LIMIT =
400` × 144 passes/day = **57,600 rows/day** — about **2.4% utilised**. Even at a
5x slowdown (shape arithmetic: 2x layers × 2x sequence, ×4 on attention scores;
the only measured figure is small@256 at 7.0-7.5 rows/s, `judge_backends.py:151-158`)
a 400-row pass takes ~280 s inside a 600 s job, so daily capacity is unchanged.
**512 costs no throughput here.**

**The rollback objection is one comparison, not a redesign.** The runtime already
reads the window off the artifact — `judge_backends.py:218` `self.max_len =
self.config['max_len']`, used at `:334-335` — so inference is artifact-driven
already. `ENCODER_MAX_LEN` at `:279-282` is purely an assertion that the artifact
matches what this build was written for. Widening it keeps **both** artifacts
valid, so the `active.json` rollback to v1@256 survives.

**The change, in full:**

1. `judge_backends.py` — replace the single constant with an allowed set:
   ```python
   ENCODER_ALLOWED_MAX_LENS = (256, 512)     # was ENCODER_MAX_LEN = 256
   ```
   and at `:279-282`, `if config.get('max_len') not in ENCODER_ALLOWED_MAX_LENS:`.
   Keep the comment explaining why the set is closed rather than "any integer":
   an artifact whose window nobody chose is still a mistake.
2. `package_encoder_artifact.py` — `MAX_LEN = 256` at `:55` and the check at
   `:122-124` become **derived from the training config**, validated against the
   same allowed set. The packager uses it in two places — the export example's
   padding (`:161-163`) and the written artifact config (`:195`) — so deriving it
   once makes the ONNX graph's baked sequence axis and the config's `max_len`
   consistent by construction, instead of two hardcoded numbers that have to be
   hand-synced. This is also the shape that survives the next training round
   whatever window it uses.
3. Nothing else. `_may_judge`, the trial identity checks, `ENCODER_MODEL_ID`,
   `active.json`'s `id`, `spend.py` — all untouched.

**The one real unknown: resident memory.** small@256 at batch 4 is flat at
1,081 MB (1,715 MB at batch 16). base@512 is 2x layers and 2x sequence —
activations roughly 4x, weights ~740 MB against 566 MB — on an 8 GB box that also
runs MariaDB with a 2500M buffer pool. Plausible landing zone 1.8-3 GB, but
**that is arithmetic on shapes, not a measurement, and it is the only thing that
can veto this.** §3b measures it locally, on a staging root, before anything is
copied to the VPS. If it is uncomfortable, `ENCODER_BATCH_SIZE` drops from 4 to 2
in its own commit (§4.1).

**Fallback if RSS does not fit: export the existing 512 weights at a 256 window.**
Needs no GPU and no retraining. Architecturally sound — `MultiHead` reads
`hidden_size` off the backbone (`train_encoder.py:201-205`), and DeBERTa-v3 uses
relative attention (`relative_attention: True`, `position_buckets: 256` in both
published backbone configs), so there is no absolute position table left
half-trained by a shorter window. But it is a different inference regime from the
one every base number was measured in, so it needs the locked-set re-score first
(tokenizer capped at 256 against the existing weights — inference only, minutes)
and the artifact config must honestly record what was done. **Do not relabel the
checkpoint's `max_len`.**

**What neither option fixes.** 512 does not "handle long comments" in general: it
truncates **3.94%** of the population where 256 truncates 8.16%, and the tail runs
to p99 2,897 and max 17,125 tokens. Both trainer and runtime truncate the pair
`longest_first`, so the **end** of a long post is what is cut — favourable if the
thesis is stated up front, which is a hypothesis nobody has measured. Genuinely
covering long posts means chunking or head+tail truncation, which is separate
work and not on this plan.

**Still unmeasured, and worth knowing before or after the swap:** whether the 512
window earns anything at all on this data. base@512 scored removal precision
0.881 against the deployed small@256's 0.880 — confounded by backbone and
training set, so it argues neither way. The 256 re-score above answers it for
~minutes of inference, and it is the cheapest experiment available. It is not a
blocker for shipping 512.


### 1.3 — The quality claim needs restating

Revision 1 §4 and the handover both compare "encoder small 11.8% reversals" to
"encoder base 6.2%". **That "small" is not what is in production.** Read out of
the checkpoint configs and training logs:

| | backbone | max_len | train rows | objective | nat rel F1 | nat orig F1 | nat att acc | nat removal P | nat reversals |
|---|---|---|---|---|---|---|---|---|---|
| **deployed** `model-train13000` | small | **256** | 13,492 | no tone mask, no reversal penalty | 0.711 | 0.748 | **0.720** | 0.880 | **16.5%** |
| `model-train17090` (tonefix3) | small | 512 | 17,090 | tone mask + reversal penalty | 0.750 | 0.725 | 0.587 | 0.846 | 11.8% |
| **base candidate** `…-20260907-192428` | **base** | 512 | 17,090 | tone mask + reversal penalty | 0.733 | 0.723 | **0.648** | 0.881 | **6.2%** |

Against **what is actually serving**, base-at-512 is:

- **much better on polarity reversals** — 16.5% → 6.2%, which is the metric the
  board's bull/bear arrow depends on, and the whole reason to swap;
- better on relevance macro-F1 (0.711 → 0.733);
- **worse on attitude accuracy** (0.720 → 0.648) and on origin macro-F1
  (0.748 → 0.723);
- flat on removal precision (0.880 → 0.881).

"Better on every tone measure" is not supportable against the deployed model.
The defensible claim is narrower and still strong: *base more than halves the
rate at which a directional call points the wrong way, at the cost of calling a
direction less often* — which is the expected effect of the tone mask that was
added in the same jump, and which is the trade the board wants. Four variables
moved at once (backbone, window, training set, loss); the reversal improvement
cannot be attributed to the backbone alone from these logs.

---

## 2. PHASE 1 — retire the trial in code

Phase 1 has a hard clock and **no dependency on §1**. It should proceed on its
own. Phase 2 waits for the artifact question.

Shape: the trial ends by **code**, not by data. Nothing writes to
`radar_mentions`, `radar_mention_events` or `radar_buckets`. The row stays,
`running`, with its retention pin. `recover_trial` stays available to an
operator who deliberately chooses it.

### 2.0 — Prerequisites, all of which must hold before 2c

- [ ] `status` still reads `running`. **If it reads `recovering`, stop and
      re-plan** — with 1,546 outstanding and `--limit 2000`, a single tick
      finishes the drain, so "recovering" means "already gone", not "in
      progress".
- [ ] `first_judged_at` is still `2026-09-06 19:38:24.047717`.
- [ ] `audit_evaluated_at` and `audit_passed` are still NULL.
- [ ] The working branch's `AUDIT_DRAW_DAY/LABEL_DAY/TRIAL_DEADLINE_DAYS` read
      `1 / 2 / 3` **after** merging `main`. Editing `judge_trial.py` on the
      pre-`d745e8e` version and merging it back silently restores 3/7/10 to
      production.
- [ ] An ad-hoc database dump exists, dated after the last judgment. The
      nightly dump is not enough; take one now. It is the only true restore
      path for anything in §5.

### 2.1 — Preserve first (zero risk, ~10 minutes)

```bash
mkdir -p /c/Users/michi/Desktop/radar_labels/artifact-small-v1
cp -a "/c/Users/michi/Desktop/CodingStuff-worktrees/radar-encoder-judge/personal_apps/artifacts/judge/." \
      "/c/Users/michi/Desktop/radar_labels/artifact-small-v1/"
cd /c/Users/michi/Desktop/radar_labels/artifact-small-v1/v1 && sha256sum *
```
Expect `e97bcb96… / 20643390… / fb20c709…`. This copy is insurance against
`git worktree remove` or `git clean -xdf` on `CodingStuff-worktrees/`;
production still holds the original.

Record production state as the "nothing was undone" baseline:

```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps && \
  systemctl is-enabled radar-encoder-trial.timer; systemctl is-active radar_ingest; \
  df -h /; date -u'
```
```sql
SELECT status, first_judged_at, audit_evaluated_at, audit_passed, stop_reason
  FROM radar_judge_trial WHERE id = 1;
SELECT COUNT(*) FROM radar_mentions            WHERE sentiment_model = 'radar-encoder-v1';
SELECT COUNT(*) FROM radar_sentiment_judgments WHERE model          = 'radar-encoder-v1';
```

### 2.2 — Stop the watchdog. Mask, not disable.

```bash
ssh root@194.164.29.97 'systemctl mask --now radar-encoder-trial.timer && \
                        systemctl is-enabled radar-encoder-trial.timer'
```
Expect `masked`. `disable --now` also works today, but `mask` additionally
prevents the unit from being pulled in by a dependency or started by hand
during the window, and it is the state a later `unmask` reverses exactly.
*Rollback:* `systemctl unmask radar-encoder-trial.timer && systemctl enable
--now radar-encoder-trial.timer` — see §4.2 before doing that after the
deadline.

This closes path 1 of §0.3. **It does not close paths 2 and 3.** Until the code
lands, the daemon must not start on unpatched code after 19:38:24 UTC on 09-09.

### 2.3 — The change: three hunks, two files

Line numbers are deployed `main`; re-`grep` the symbol before editing, because
this checkout is not that file.

**Hunk A — a named switch, beside the schedule it retires.** After
`judge_trial.py:578`:

```python
# 2026-09-08: the trial is retired by DECISION, not by verdict. The gate was
# built to answer "is the encoder safe enough to replace Haiku"; Haiku has had
# no credits since 2026-09-03, so the alternative is no judge at all and ~46%
# junk counting on the board. Retired means two things and only two: the
# deadline no longer ends the trial, and nothing recovers automatically. The
# row stays, its retention pin stays, recover_trial is untouched and still
# available to an operator who decides to use it. Flip to False to restore the
# original behaviour exactly.
TRIAL_RETIRED = True
```

and in `deadline()`, immediately after the `row is None or row.first_judged_at
is None` guard at `:595-596`:

```python
    if TRIAL_RETIRED:
        return None
```

*Effect:* `_may_judge`'s deadline branch (`:694-697`) never raises, so the
encoder keeps judging past 19:38:24; `tick`'s `ends is None` early return
(`:805-807`) makes the expiry branch unreachable.

**Hunk B — a stop stops; it does not destroy.** `tick()`, at the `RECOVERING`
branch, deployed `:799-803`:

```python
    if row.status == RECOVERING:
        if TRIAL_RETIRED:
            # Retired: a stop halts judging and nothing more. Recovery is an
            # operator decision made deliberately with
            # scripts/rollback_encoder_judge.py --apply, never something a
            # timer does at 2000 rows a minute with no confirmation.
            return {'action': 'none', 'status': row.status}
        report = recover_trial(apply=True, limit=limit, now=now)
        …
```

*Effect:* this is the hunk that removes the bomb from **all three** paths in
§0.3 — timer, startup tick, and crash-restart alike — because after Hunk A the
expiry branch is unreachable and this one is the only remaining call to
`recover_trial(apply=True)` inside `tick`. After it, `manage_encoder_trial
stop` becomes non-destructive: it halts judging (`_may_judge:692-693`) and is
undone by `UPDATE radar_judge_trial SET status='running', stop_reason=NULL
WHERE id = 1`.
*Accepted risk:* a genuine emergency rollback now requires the explicit
`scripts/rollback_encoder_judge.py --apply`. That is the point.

**Hunk C — the artifact hash reports instead of gating.**
`judge_config.py:179-184` (**not** `:173-178`, as the handover says):

```python
    deployed = (backend.bundle_sha256()
                if getattr(backend, 'bundle_sha256', None) else None)
    if judge_trial.TRIAL_RETIRED:
        logger.info('radar judge: encoder artifact %s serving (trial retired; '
                    'the armed hash %s no longer gates the deploy)',
                    (deployed or 'unknown')[:12], (row.artifact_sha256 or '')[:12])
    elif row.artifact_sha256 and deployed and row.artifact_sha256 != deployed:
        raise ConfigError(
            'the deployed artifact does not match the armed trial '
            '(%s armed, %s deployed); replacing a file is a different trial'
            % (row.artifact_sha256[:12], deployed[:12]))
    return backend
```

*Effect:* this is what lets Phase 2 exist at all. The startup log line becomes
the only forensic record of which model is serving — keep it.
*What Hunk C deliberately does NOT remove* — and what therefore stays true
after retirement:

| still enforced | where | consequence if violated |
|---|---|---|
| a trial row must exist | `judge_trial.py:679-682` → `judge_config.py:178` | **ingest daemon fails to start** |
| `row.model_id == ENCODER_MODEL_ID` | `:683-686` | same |
| `row.prompt_version == PROMPT_VERSION` | `:687-691` | same |
| status not `RECOVERING`/`RECOVERED` | `:692-693` | judging silently off (`judge_config.py:170-177` returns None); daemon lives |
| `active.json` `id == 'radar-encoder-v1'` | `judge_backends.py:261-264` | dead daemon |
| artifact `max_len == ENCODER_MAX_LEN` | `judge_backends.py:279-282` | dead daemon |

**Same-commit doc fix (zero risk, recommended):** `judge_trial.py:443-445` and
`scripts/rollback_encoder_judge.py:22-23` both still assert *"Tone and its
provenance are NOT cleared. The trial never wrote them"*. False since
2026-09-07 (`judge_backends.py:210` `writes_tone = True`;
`llm_sentiment.py:493-502`). Correct the text so the next operator is not
misled about what a recovery leaves behind.

### 2.4 — Tests

These pin the behaviour Hunks A/B/C remove and **will go red**:

- `tests/test_radar_judge_trial.py` — `test_the_guard_refuses_on_the_deadline_itself`,
  `test_an_unevaluated_trial_still_expires_on_day_ten`,
  `test_a_failing_audit_does_not_lift_the_deadline`,
  `test_a_failing_audit_stops_the_trial_without_waiting_to_be_noticed`
- `tests/test_radar_judge_config.py` — `test_a_different_artifact_than_the_one_armed_is_refused`

Do not delete them. Monkeypatch `judge_trial.TRIAL_RETIRED = False` in each, so
the un-retired semantics stay tested — that is what makes the revert
trustworthy. Add, with `TRIAL_RETIRED = True`:

1. `deadline()` returns `None` past day 3;
2. `tick()` on a `RECOVERING` row recovers **zero** mentions *and* leaves
   `status == 'recovering'` (assert the row, not just the return value — a test
   that only reads the dict passes if `recover_trial` runs and returns nothing
   to do);
3. a mismatched bundle hash starts the encoder;
4. **a missing trial row still raises** — the guard Hunk C keeps, pinned so
   §6.1 cannot be misremembered as safe.

```
pytest personal_apps/tests/test_radar_judge_*.py \
       personal_apps/tests/test_radar_trial_writes.py \
       personal_apps/tests/test_encoder_*.py
```

### 2.5 — Deploy, in an order that is safe on either side of the deadline

Revision 1 assumed the deployment lands before 19:38:24 UTC on 09-09. Assume it
might not.

**Before the deadline** (timer already masked per §2.2), an ordinary deploy is
sufficient: `update_coc.sh` stops `radar_ingest`, resets to `origin/main`, and
starts it last, so the startup tick runs patched code. The pre-deadline
startup tick is `{'action': 'none'}` anyway (`:805-807`).

**After the deadline — or any time you are not certain which side you are on —
use this order:**

```bash
# 1. take the daemon out of the restart loop FIRST; Restart=always does not
#    fire after an explicit stop
ssh root@194.164.29.97 'systemctl stop radar_ingest && systemctl is-active radar_ingest'
# 2. confirm the timer is still masked
ssh root@194.164.29.97 'systemctl is-enabled radar-encoder-trial.timer'
# 3. deploy the code WITHOUT starting anything
#    (update_coc.sh restarts radar_ingest at the end; run its pull/migrate/build
#     steps, or run it and accept that the start in step 5 already happened —
#     either is safe ONLY once step 4 passes on the box)
# 4. prove the patch is on disk before anything reads it
ssh root@194.164.29.97 'cd /root/coc-stats && git rev-parse HEAD && \
  grep -n "TRIAL_RETIRED" personal_apps/features/radar/judge_trial.py \
                          personal_apps/features/radar/judge_config.py'
# 5. only now
ssh root@194.164.29.97 'systemctl start radar_ingest'
```

Step 4 is the gate. If `TRIAL_RETIRED` is not in both files on the box, do not
start the daemon.

### 2.6 — Verify, before touching any artifact

```bash
ssh root@194.164.29.97 'journalctl -u radar_ingest -n 80 --no-pager | grep -Ei "judge|encoder|trial|Traceback"'
```
Expect `radar judge: primary=radar-encoder-v1 review=…` and the new
`trial retired` line naming `3bb32b5607a8`. Then re-run the two `COUNT(*)`
queries from §2.1: **unchanged or higher, never lower.** Then wait one
ten-minute cycle and confirm a `radar sentiment judged N mentions` line.

At this point the deadline is dead, the 1,546 judgments are intact, nothing has
been swapped, and Phase 2 can wait as long as it needs to.

---

## 3. PHASE 2 — put base in production

**Blocked on §1.2's RSS measurement and on the two-file window change landing
first.** Order: (i) commit the `ENCODER_ALLOWED_MAX_LENS` / derived-`MAX_LEN`
change of §1.2 with its own tests, (ii) 3a-3b locally, (iii) only if RSS fits,
3c onward. If RSS does not fit, stop and take §1.2's 256-export fallback — that
changes what 3a produces but nothing after it.

**3a. Package into a separate root.** Heavy local job (`torch.onnx.export` of a
~184M-parameter fp32 model; several GB RAM, minutes). Name the window first.

```bash
cd /c/Users/michi/Desktop/CodingStuff/personal_apps
python scripts/package_encoder_artifact.py \
  --model "C:/Users/michi/Desktop/radar_labels/encoder/model-train17090-20260907-192428" \
  --out   "C:/Users/michi/Desktop/radar_labels/artifact-base" \
  --base  microsoft/deberta-v3-base \
  --trainer "C:/Users/michi/Desktop/CodingStuff/personal_apps/scratchpad/label_export"
```

`--out` is **not** the live root: `version_dir` is hardcoded to `v1`
(`:132`) and `active.json` is always written `{"path": "v1/"}` (`:197-199`), so
packaging into the live root overwrites the audited small bundle in place.
Pass `--trainer` explicitly rather than relying on the default (`:99-103`) —
the default points at this working tree, whose branch is not necessarily the
one the weights were trained from. Record the printed `bundle sha256` (`:207`).
The `size < 400` warning (`:203-205`) is calibrated for small and will not fire.

**3b. Validate locally on a v2-shaped staging root, before anything leaves the
machine.** Lay the three files out as `…/staging/v2/`, write
`{"path":"v2/","id":"radar-encoder-v1"}` as `staging/active.json`, construct
`EncoderBackend(staging)` and run one `judge_batch` of ~8 real texts.

This exercises `_validate` (`judge_backends.py:258-302`) and the one contract
**nothing validates**: that the ONNX graph's output names equal the five head
names. `self._outputs` comes from the graph (`:346`) and is zipped positionally
into `by_head` (`:376-377`), then indexed by field name at `:381` — outside the
`try` at `:371-374`. A mismatch is a bare `KeyError` that kills every pass,
silently, forever. Assert the five names and assert that the returned
`Judgment` fields are all legal enum values.

Print peak RSS at `ENCODER_BATCH_SIZE = 4`. If it is uncomfortable next to
MariaDB's 2500M buffer pool, lower it to 2 — **in its own commit**, not folded
into the swap (see §4.1).

**3c. Ship as `v2/`, overwriting nothing.**

```bash
ssh root@194.164.29.97 'mkdir -p /root/coc-stats/personal_apps/artifacts/judge/v2'
scp "…/artifact-base/v1/model.onnx"     root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
scp "…/artifact-base/v1/tokenizer.json" root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
scp "…/artifact-base/v1/config.json"    root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && sha256sum v1/* v2/*'
```

Compare v2's digests to local, and confirm **v1's three still equal
`e97bcb96… / 20643390… / fb20c709…`**.

*Target is `194.164.29.97`.* The runbook's `scp` at
`docs/superpowers/plans/2026-09-06-radar-encoder-judge-runbook.md:202` still
names `82.165.240.212`, the stopped fallback box.

*Why `v2/` and not in place:* `bundle_sha256` hashes
`os.path.dirname(self.model_path)` (`judge_backends.py:233`) and `model_path`
comes from the `active.json` pointer (`:258-268`), which is deliberately
outside the digest (`:228-231`). The pointer is the atomic switch. An in-place
`scp` writes into a file onnxruntime holds mapped (the session is built once
and held for process lifetime, `:318-347`) and shows no symptom until a restart
hours later kills all of ingest.

**3d. Flip the pointer — and leave a rollback that survives being used.**

```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && \
  printf "{\n \"path\": \"v1/\",\n \"id\": \"radar-encoder-v1\"\n}\n" > pointer-v1.json && \
  printf "{\n \"path\": \"v2/\",\n \"id\": \"radar-encoder-v1\"\n}\n" > pointer-v2.json && \
  cp -f pointer-v2.json active.json && cat active.json'
```

Two **immutable, named** pointer files, and `cp` rather than `mv`. Revision 1's
`mv -f active.json.v1.bak active.json` *consumes* the backup: the rollback
works once, and a second rollback — or a roll-forward and a second rollback —
has nothing to move. These two files make the switch idempotent and repeatable
in both directions.

`id` must stay `radar-encoder-v1` verbatim: `_validate` asserts pointer id ==
`ENCODER_MODEL_ID` (`judge_backends.py:261-264`) and `_may_judge:683-686`
compares the code constant against the frozen row.

**3e. Restart and watch.**

```bash
ssh root@194.164.29.97 'systemctl restart radar_ingest'
ssh root@194.164.29.97 'journalctl -u radar_ingest -n 100 --no-pager | grep -Ei "judge|encoder|sentiment|Traceback"'
```
Expect the `trial retired` line to now name the **base** bundle hash. Wait one
sentiment pass, confirm rows are judged, and take a real RSS reading
(`systemd-cgtop`, or `ps -o rss= -p $(systemctl show -p MainPID --value radar_ingest)`).

**3f. Record the swap timestamp — now, not later.** Base and small rows both
carry `sentiment_model = 'radar-encoder-v1'` (`judge_backends.py:215` →
`llm_sentiment.py:490`), so the **only** discriminator that will ever exist is
`radar_sentiment_judgments.created_utc` against the restart time. Write it and
the base bundle hash into `/root/trial-audit/base-swap.txt` and into the
handover. It is unrecoverable afterwards.

---

## 4. ROLLBACK — two different things, kept apart

### 4.1 — Model rollback (safe, repeatable, no clock)

```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && \
  cp -f pointer-v1.json active.json && systemctl restart radar_ingest'
```

Preconditions: §3d's two pointer files exist; `TRIAL_RETIRED` is still `True`
(otherwise Hunk C is gone and the v1 hash gate is back — which would in fact
*pass* for v1, but the trial's deadline would also be back); and the deployed
build still accepts v1's `max_len: 256`. **That is exactly what
`ENCODER_ALLOWED_MAX_LENS = (256, 512)` buys** (§1.2) — with a bare
`ENCODER_MAX_LEN = 512` instead, v1 would fail `_validate` at `:279-282` and
this rollback would be a dead daemon. Pin it with a test: construct
`EncoderBackend` against a 256 artifact and against a 512 artifact and assert
both load.

Keep this one command clean. Do not fold an `ENCODER_BATCH_SIZE` change, or any
other code edit, into the Phase-2 commit: the pointer flip reverses the model
and nothing else, and a bundled code change would survive the rollback silently.
If batch size must change, ship it separately and revert it separately.

### 4.2 — Restoring destructive trial behaviour (deliberate, dangerous)

`git revert` of the Phase-1 commit is **not** a rollback in the same sense.
After 2026-09-09 19:38:24 UTC the stored `first_judged_at + 3d` has passed, so
the moment reverted code runs:

- the deploy's own `systemctl start radar_ingest` hits
  `run_radar_ingest.py:1272` on unpatched code and drains all 1,546 judgments
  **before the timer is ever unmasked**;
- unmasking the timer afterwards would do the same thing within a minute.

So reverting Phase 1 is only correct together with a decision to destroy the
judgments, and it should be executed in that order, explicitly:

1. `scripts/rollback_encoder_judge.py` **without** `--apply` first — the dry
   run is the only safe form (`:64-66`); `--apply` calls `request_stop` before
   anything else (`:51-54`) and is one-way.
2. Then, if the report is what you want, `--apply`.
3. Then revert the code and unmask the timer, with nothing left to lose.

If the goal is only "put the small model back", use §4.1 and leave Phase 1
alone.

---

## 5. PATHS THAT LOOK ATTRACTIVE AND DESTROY DATA

Line numbers corrected against deployed `main`.

**5.1 `manage_encoder_trial stop --reason "abandoning the trial"` — the
operator's own word, and the single most likely mistake.** It writes two
columns (`judge_trial.py:297-298`) and prints *"the decisions already made are
still in the counts until recovery runs"* (`manage_encoder_trial.py:120-122`).
That sentence is true for about 59 seconds. `tick` treats `RECOVERING` as an
unconditional instruction to drain (`:799-803`) and the timer fires every
minute at `--limit 2000` — more than the 1,546 outstanding, so one firing
finishes it. The project's own runbook §9 presents this as step 1 under *"the
first alone is not a rollback"*. **The runbook is wrong.** After Hunk B this
command becomes harmless; before it, it is the delete button.

**5.2 `audit_encoder_trial accept …` on the current FAILING report.** A failing
report is a *result*, not an error: `accept_audit` passes the flag through
(`audit_encoder_trial.py:946`) and sets `status = RECOVERING` plus a
`stop_reason` itself (`judge_trial.py:657-661`), then prints *"The trial is now
recovering."* Identical outcome to 5.1, and one-way twice: once
`audit_evaluated_at` is set, a different report can never be recorded
(`:639-643`).

**5.3 "Let me just complete the report properly so the record is clean."** The
two blockers — every reference row lacking `labelled_at`, and no supplemental
sets — are the only reason 5.2 has not already happened
(`audit_encoder_trial.py:893-896`; `judge_trial.py:626-627`). Fixing them arms
the destruction. **Correction to Revision 1: the labelling window has not
closed.** `labels_due = first_judged_at + AUDIT_LABEL_DAY(2)` =
**2026-09-08 19:38:24 UTC**, which was still 21 hours away at verification
(`audit_encoder_trial.py:930-943`). `accept` would be refused only *after*
that. Until then this path is fully open.

**5.4 Lowering `REMOVAL_PRECISION_FLOOR` to force a pass.** Tempting because a
passing audit is the one in-code state where `deadline()` returns `None`
(`judge_trial.py:597-598`). Four reasons not to: it fabricates a verdict
against the module's own warning that "3-versus-1 wrong deletions out of 200
became an argument for shipping once already" (`trial_audit.py:10-13`); it
needs a `labelled_at`/`completed_at` that would have to be invented; it is
one-way (`:639-643`); and decisively **it does not get base deployed** — a pass
leaves `artifact_sha256` frozen at `3bb32b56…` and `judge_config.py:179-184`
still refuses the new bundle. It buys the deadline and forfeits the goal.

**5.5 `rollback_encoder_judge --apply --limit 1` "to see what happens".**
`--apply` calls `request_stop('recovery run')` first (`:51-54`), deliberately,
so a half-finished run cannot race the daemon. That one probe commits the trial
to `RECOVERING` permanently, and pre-Hunk-B the timer finishes the rest inside
a minute. **The flagless dry run is the only safe form** (`:64-66`).

**5.6 `DELETE FROM radar_judge_trial WHERE id = 1`.** Before Phase 1 *and after
it*: `_may_judge` raises on `row is None` (`judge_trial.py:679-682`) →
`ConfigError` (`judge_config.py:178`) → uncaught at
`run_radar_ingest.py:1275` → **the whole ingest daemon fails to start**, taking
all 13 scheduled jobs with it. Radar's sources are cursor-and-budget driven;
every minute down is mentions that are never collected and cannot be backfilled.
It also releases the retention pin instantly (`:167-170` → `retention.py:44-46`),
so the next prune cuts the journal back to 48 hours. **Revision 1 said this
becomes safe after Phase 1. It does not** — Hunk C removes the *hash* gate,
nothing removes the *row* gate. See §6.1.

**5.7 Deleting the row and arming a second trial for the base hash.** The worst
reachable end state. `_recoverable` selects on `model_id` + `prompt_version`
**only** (`judge_trial.py:333-337`) — never on the artifact hash — and both are
re-frozen from the same code constants (`:256-257`). A trial #2 armed today
therefore owns every mention the small model judged, while its `retain_from` is
`now − PIN_LOOKBACK`. The moment `_plan` (newest-first, `:368-372`) reaches an
older window, `recover_trial` raises (`:463-470`, `:505-507`); `remaining`
never reaches zero; `_release_if_drained` never flips to `RECOVERED`; the pin
is held forever; `_encoder_or_none` returns `None` so judging is off
permanently; and the watchdog logs a failure every 60 seconds.

**5.8 Packaging base with `--out personal_apps/artifacts/judge`, or `scp -r
artifacts/judge …` as the runbook says (`:202`).** Both overwrite `v1/` in
place. That destroys the byte-exact audited artifact on whichever side it hits,
and `audit_encoder_trial.py:329-335` then refuses `predict --backend encoder`
forever — the failed audit could never be re-run or extended, including on the
44 wrongly-removed rows.

**5.9 The runbook's `scp` target `82.165.240.212`.** Decommissioned 2026-09-07.
Copies ~740 MB to a stopped box; the symptom on the live box ("hash still
doesn't match") reads like a packaging bug.

**5.10 Bumping `ENCODER_MODEL_ID` to `radar-encoder-v2`, or touching
`PROMPT_VERSION`.** `_may_judge:683-686` and `:687-691` compare both against
the frozen row; either mismatch raises `TrialError` → `ConfigError` → dead
daemon. `active.json`'s `id` must move with the constant or `_validate` rejects
the pointer (`judge_backends.py:261-264`), also dead. Code and row would have
to change in the same restart. Also `spend.py:58` hardcodes
`'radar-encoder-v1': (0.0, 0.0)`; a v2 id makes `cost_micros` return `None` and
the board reports encoder tokens as "unpriced" instead of free.

**5.11 `RADAR_JUDGE_TONE=1`.** `judge_config.py:89-97` raises `ConfigError` for
any value but `'0'`: dead daemon. (Production has `RADAR_JUDGE_TONE=0`,
verified.) `Settings.write_encoder_tone` (`:102`) is hardwired `False` and read
by nothing; tone already publishes via `judge_backends.py:210`.

**5.12 `RADAR_JUDGE_PRIMARY=anthropic:radar-encoder-v1` as a hash-check
bypass.** It does skip the artifact check (no `bundle_sha256` attribute,
`judge_config.py:179-180`) — but the string becomes the Anthropic **API model
name** and 404s on the first call, while storing nothing under encoder
provenance. (Production is `RADAR_JUDGE_PRIMARY=encoder`, verified.)

**5.13 "Just let it recover, that's the safe option."** It is not safe and does
not even produce a clean pre-trial state. `recover_trial` clears five columns
(`judge_trial.py:511-515`) and leaves `sentiment_attitude`,
`sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment` and
`sentiment_tone_model` — which the encoder now writes
(`llm_sentiment.py:493-502`) and which `board.py` reads first for bull/bear. A
"complete" recovery would undo the encoder's effect on **volume** counts and
not on **direction** counts, leaving mentions that claim to be unjudged while
still carrying `sentiment_tone_model = 'radar-encoder-v1'`. That is a state no
code was written for. *(Read on both the writing and clearing sides; not
observed by running a recovery. The recommended path never triggers one.)*

**5.14 Running any trial command from this checkout against production.** See
§0.1. The reassuring reading and the destructive one come from the same command
name.

---

## 6. OPEN QUESTIONS THAT NEED THE OPERATOR

**6.1 The retention pin — and the correction that changes the options.**
With the row left `running`, `retention_floor()` keeps returning `retain_from`
= 2026-09-04 19:45 (`judge_trial.py:158-170`), and `retention._pinned` clamps
both pruners at it (`retention.py:23-46`).

Measured, so the decision is not made on a guess:

```
/ on 194.164.29.97       232G total, 12G used, 220G free
radar_mention_events     445,538 rows / 240 MB, spanning 2026-09-03 21:54 → now
```

That is roughly 110k rows and 60 MB per day of unbounded journal — about
22 GB/year against 220 GB free. **Revision 1's "on an 8 GB box" alarm confused
RAM with disk; there is no disk pressure here and no reason to trade optionality
for it.**

Revision 1 then offered "(b) after Phase 1, `DELETE FROM radar_judge_trial`" as
a safe way to release the pin. **It is not safe** (§5.6): the row gate at
`judge_trial.py:679-682` survives Phase 1 and turns a missing row into a dead
ingest daemon. The honest position is narrower:

- **(a) Leave it.** No disk problem, every judgment stays undoable. Recommended.
- **(b) Release it destructively** — only a completed `recover_trial` sets
  `RECOVERED` and lifts the pin (`:553-557`), and that is the destruction.
- **(c) Release it non-destructively** — would need a further code change so
  the encoder can run with no trial row at all (a `TRIAL_RETIRED` branch in
  `_may_judge`). Not in this plan, not reviewed, and it would remove the last
  structural reason recovery is still possible. Its own decision, later.

There is no supported state in which the judgments survive *and* the pin
releases. Phase 1 does not solve that; it makes it a decision someone takes
deliberately rather than one a timer takes on 09-09.

**6.2 Should base-model rows be distinguishable from small-model rows?**
Keeping `radar-encoder-v1` is the low-risk move but makes "undo only the base
model's week" permanently impossible — nothing separates them except the
timestamp recorded by hand in §3f. Distinguishing them means bumping
`ENCODER_MODEL_ID`, which means removing the id check from `_may_judge` (a
bigger diff) plus a `spend.py:58` entry. This is the exact trap the codebase
already fell into once: `stored_row_carries_tone` (`judge_backends.py:431-440`)
exists because one id could not tell two behaviours apart.

**6.3 [DECIDED 2026-09-08] Which artifact resolution?** Ship the existing
base@512 weights and widen the window check (§1.2). **No retraining** — more
labelled data is coming and the GPU time is not being spent twice. What remains
is not a decision but a measurement: peak RSS at batch 4 (§3b), which is the
only thing that can still veto 512. Its fallback needs no GPU either.

Still needing a named window, because it is a heavy *local* job even though it
is not training: `torch.onnx.export` of the ~184M-parameter fp32 model in 3a —
CPU and several GB of RAM, minutes, no GPU.

**6.4 Does the base model keep publishing tone?** Tone was never audited;
`trial_audit.py`'s docstring says tone is reported and never gates. The
measured case is strong on reversals (deployed 16.5% → base 6.2%) but base is
*worse* on attitude accuracy against the deployed model (0.720 → 0.648), see
§1.3. It is already live for small, and it is a code edit either way
(`judge_backends.py:210`), not a flag.

**6.5 The reference labeller was GPT, not a human, and calls 29% of the sample
`uncertain`** against Haiku's historical 3.4% and the encoder's 16%.
Independent of both judges, which is the property that matters — but one pass,
no majority vote, inter-labeller disagreement unmeasured. Doesn't block
anything here. It decides whether the 0.803/0.849 numbers can later be cited as
more than indicative.

**6.6 Keep the trial machinery dormant, or delete it?** Phase 1 leaves ~1,400
lines of arm/recover/audit code that nothing reaches. That is deliberate — it
is the revert path — but it is also a loaded gun in the repo. Retire
`deploy/radar-encoder-trial.{timer,service}` too, or leave them
installed-and-masked?

**6.7 The 44 wrongly-removed mentions** — is a pattern hunt still wanted, given
the trial is being retired? It needs the frozen artifact, which is why §0.4
matters.

---

## 7. THE 0.93 THRESHOLD — re-verified, unchanged

Lives at `personal_apps/features/radar/trial_audit.py:41`:

```python
REMOVAL_PRECISION_FLOOR = 0.93
```

A plain module constant, used at `:240` (copied into the report as
`criteria[…]['threshold']`), `:241-243` (`removal_passed`) and `:251-254` (the
human-readable rule). The module reads no environment and no files; it is
documented as pure at `:2-6`.

**A new trial cannot be armed at a different bar without editing code.**
`arm_trial` freezes only `seed`, `baseline_report`, `baseline_removal_rate`,
`sample_size`, `removal_decisions_wanted` and `supplemental` into `row.recipe`
(`judge_trial.py:262-270`). `RadarJudgeTrial` (`models.py:1382`) has no
threshold column. The arming CLI exposes no threshold flag. This is deliberate,
per the sibling comment on `Z` at `trial_audit.py:33-35`: *"this number decides
whether a trial passes, and it should be readable in the diff that changes
it."*

**And it cannot be back-doored:** `accept` recomputes the entire canonical
report from the inputs with the *current* code and demands byte-identical
reproduction (`audit_encoder_trial.py:913-925`). Changing the constant between
`evaluate` and `accept` makes the report fail to reproduce rather than silently
re-grading it.

None of this is on the recommended path — the plan never runs `evaluate` or
`accept` again.

---

## A. WHAT REVISION 1 GOT WRONG

Recorded because a corrected plan derived from a stale premise is worse than no
plan.

| # | Revision 1 | Corrected |
|---|---|---|
| 1 | "reader citations ≥ 575 are one line low" | Unshifted below 600; **+10** at `_may_judge`, **+14** at `tick`. Its own §1/§2 then cited `785-789`/`790-792` for code at `799-803`/`805-816`. §0.6 |
| 2 | "the base checkpoint is present and packageable" | Present, **not packageable**: `max_len 512` vs `MAX_LEN 256` at two independent gates, and `artifact-base/` does not exist. §1 |
| 3 | Disabling the timer + a pre-deadline deploy is enough | `Restart=always` on `radar_ingest` re-arms the startup tick after any crash, with no operator involved. §0.3, §2.5 |
| 4 | "a restart would drain 2000 mentions" | 1,546 outstanding < `--limit 2000`: one firing drains **everything** and releases the pin. §0.2 |
| 5 | "after Phase 1 the `DELETE` is safe but unnecessary" | Still a dead ingest daemon — Hunk C removes the hash gate, not the row gate. §5.6, §6.1 |
| 6 | Phase-2 rollback is `mv -f active.json.v1.bak active.json` | `mv` consumes the backup; the rollback works once. Two immutable pointer files + `cp`. §3d, §4.1 |
| 7 | `git revert` of Phase 1 listed as a rollback | Post-deadline it *is* the destruction, and it fires on the deploy's own restart before the timer is unmasked. §4.2 |
| 8 | Under Option B, "the rollback is one command" | Moving `ENCODER_MAX_LEN` to 512 makes v1 fail `_validate`; the pointer rollback becomes a dead daemon. §1.2 |
| 9 | "the labelling window closed today; `accept` is probably refused" | `labels_due` = 2026-09-08 19:38:24 UTC, still 21 h away at verification. The path is open. §5.3 |
| 10 | "base is better on every tone measure" | Against the **deployed** model: much better on reversals, better on relevance, **worse** on attitude accuracy and origin F1, flat on removal precision. The cited "small" was a different model. §1.3 |
| 11 | "unbounded journal growth on an 8 GB box" | 220 GB free; journal 240 MB / 4 days ≈ 60 MB/day. RAM was confused with disk. §6.1 |
| 12 | `judge_config.py:173-178` refuses a changed bundle (handover §5) | `:179-184`. §0.6 |

---

## B. BLOCKERS AND THE EXACT NEXT ACTION

**Blocked:**

1. **Phase 2** — the resolution is decided (ship base@512, widen the window
   check; **no retraining**) but nothing is packaged yet. Remaining gates, in
   order: the two-file window change with its tests; the `torch.onnx.export` in
   3a, which needs a named window as a heavy local job; and the **peak-RSS
   measurement in 3b, the only thing that can still veto 512.** None of it needs
   a GPU, and neither does the fallback.
2. **§6.1 (c), releasing the pin without destroying anything**, is blocked on a
   code change nobody has written or reviewed.
3. **Phase 1 itself is not blocked** — but it has 45 hours on the clock from
   the verification stamp, and 21 of those also carry the open `accept` path of
   §5.3. It does not depend on Phase 2 in any way.

**Exact next action, for the operator, one command:**

```bash
ssh root@194.164.29.97 'systemctl mask --now radar-encoder-trial.timer && systemctl is-enabled radar-encoder-trial.timer'
```

Expect `masked`. That closes the minute-by-minute path immediately and
reversibly, costs nothing, changes no data, and buys the time to do §2.3-§2.6
carefully. It does **not** close the crash-restart path — only the deployed
code does that, which is why §2 follows it rather than replacing it.

Nothing in this document has been executed.

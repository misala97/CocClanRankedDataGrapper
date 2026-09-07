# OPERATIONAL PLAN — retire the encoder trial, ship base, destroy nothing

All line numbers below are **deployed `main` (`b1d1a7c`)** unless marked otherwise. I re-read every load-bearing claim against `git show main:…` because the four readers read the checked-out worktree, which is a different file.

---

## 0. FACTS I VERIFIED MYSELF (three of them change the plan)

**0.1 — The four readers used the wrong schedule constants. The adversarial verdicts are right; I confirmed it.**

```
git show main:personal_apps/features/radar/judge_trial.py  →  575  # Schedule amended 2026-09-07: keep the original first-judgment clock.
                                                              576  AUDIT_DRAW_DAY = 1
                                                              577  AUDIT_LABEL_DAY = 2
                                                              578  TRIAL_DEADLINE_DAYS = 3
worktree (dev_personal afea39c) :575-577                    →  3 / 7 / 10
```
`git merge-base --is-ancestor dev_personal main` → **NO**. `dev_personal..main` = `d745e8e`, `13c9fce`, two merges. `main..dev_personal` = one docs commit (`afea39c`).

Consequences, both operational:
- The deadline is `first_judged_at + 3d` = **2026-09-09 19:38:24 UTC**, as the task states. Not 09-16.
- **Every `manage_encoder_trial` / `audit_encoder_trial` command run from `C:\Users\michi\Desktop\CodingStuff` against the production DB computes with 3/7/10 and lies to you.** `tick` would report `action: none` on an expired trial; `accept` would refuse a valid day-1 draw as "before day 3". Any command touching the trial must run on the VPS from `/root/coc-stats`, or from a checkout of `main`.
- All reader citations at `judge_trial.py` ≥ 575 are **one line low** vs. production (`d745e8e` added one comment line). Below 575 they are identical — I diffed the file: `git diff b82aea0..dev_personal -- …/judge_trial.py` is empty, so dev == the merge base and main == merge base + that one hunk.

**0.2 — The audited small artifact exists, byte-exact, and I confirmed its identity.** I re-implemented `judge_backends.bundle_sha256` (`judge_backends.py:224-244`) over `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-encoder-judge\personal_apps\artifacts\judge\v1\`:

```
model.onnx     = e97bcb9668cdeb40ce1413fb3e221406b56865f28799516af2833b392d72e174
tokenizer.json = 2064339078e4acd208a72f2db7f778996734cdcb53209119b0cbc289385a854a
config.json    = fb20c7093c0619a7c6768ddd394842d7a3c28a930db49bb000094d3790c69341
BUNDLE         = 3bb32b5607a8a368d8ff72179b41de00c6a971223bbed21302e95dcfb90dccb5   ← matches the armed trial
```
`config.json` records `"source_model": "model-train13000"`, `"packaged_at_git_head": "221095c"`. That directory is **gitignored, inside a worktree for already-merged work, and named by no procedure.** It is the rollback asset. Protecting it is step 1.

**0.3 — The base checkpoint is present and packageable.** `C:\Users\michi\Desktop\radar_labels\encoder\model-train17090-20260907-192428\` — `weights.pt` 735 MB, `config.json`, `tokenizer.json`; `model-latest.txt` points at it. The packager (`scripts/package_encoder_artifact.py:113-127`) validates head names/order and `max_len == 256` against the training config before exporting, so a mismatch fails loudly and locally.

---

## 1. RECOMMENDED PATH

**Shape of the recommendation:** the trial ends by **code**, not by data. Nothing in this plan writes to `radar_mentions`, `radar_mention_events` or `radar_buckets`. The trial row stays in the database, `running`, untouched. Every step reverts with a `git revert`, a `systemctl enable`, or a `mv`.

Two phases. **Phase 1 must be deployed before 2026-09-09 19:38:24 UTC**; Phase 2 has no clock on it.

---

### Phase 0 — preserve and record (do first, ~10 minutes, zero risk)

**0a. Get the small artifact out of the worktree.**
```bash
mkdir -p /c/Users/michi/Desktop/radar_labels/artifact-small-v1
cp -a "/c/Users/michi/Desktop/CodingStuff-worktrees/radar-encoder-judge/personal_apps/artifacts/judge/." \
      "/c/Users/michi/Desktop/radar_labels/artifact-small-v1/"
```
Then re-run the bundle-hash snippet against the copy and confirm `3bb32b56…`.
*Changes:* nothing but disk. *Risks:* none. *Why:* `git worktree remove` or `git clean -xdf` on `CodingStuff-worktrees/` destroys the only byte-exact copy outside the VPS, and it **cannot be recreated** — `package_encoder_artifact.py:191` writes `packaged_at_git_head` into `config.json`, and `config.json` is inside the hash (`judge_backends.py:236`), so any repackage yields a different `bundle_sha256`.

**0b. Snapshot production state, from the VPS.**
```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps && \
  ../venv/bin/python -m scripts.manage_encoder_trial status; \
  systemctl is-enabled radar-encoder-trial.timer; \
  systemctl is-active radar_ingest; df -h /'
```
```sql
SELECT status, model_id, prompt_version, LEFT(artifact_sha256,12), armed_at,
       first_judged_at, audit_evaluated_at, audit_passed, retain_from, stop_reason
  FROM radar_judge_trial WHERE id = 1;
SELECT COUNT(*) FROM radar_mentions WHERE sentiment_model = 'radar-encoder-v1';
SELECT COUNT(*) FROM radar_sentiment_judgments WHERE model = 'radar-encoder-v1';
```
Keep those two counts. They are the proof, later, that nothing was undone.

**0c. Take an ad-hoc DB dump** (there is a nightly one, but take one dated now). It is the only true restore path for anything in §2, and the runbook never names it as such.

**Hard gate: if `status` already reads `recovering`, stop and re-plan.** The drain has been running since that minute at 2000 rows/min (`judge_trial.py:785-789` + the minute timer), and the question changes from "how do we avoid this" to "how much is left".

---

### Phase 1 — defuse the deadline (must land before 2026-09-09 19:38:24 UTC)

**1a. Freeze the watchdog. Immediate, one command, reversible.**
```bash
ssh root@194.164.29.97 'systemctl disable --now radar-encoder-trial.timer && \
                        systemctl is-enabled radar-encoder-trial.timer'
```
*Changes:* stops the per-minute `ExecStart=… manage_encoder_trial tick --limit 2000` (`personal_apps/deploy/radar-encoder-trial.service`, `…​.timer` `OnCalendar=*-*-* *:*:00`, `Persistent=true`).
*Rollback:* `systemctl enable --now radar-encoder-trial.timer`.
*Risk it does NOT cover:* `run_radar_ingest.py:1272` calls `judge_trial.tick(utcnow())` **at daemon startup, before `initialize_judges`**, deliberately (`:1267-1271`). So after 19:38:24 UTC tomorrow, a restart of `radar_ingest` — which `./update_coc.sh` does — would itself drain 2000 mentions. Masking the timer buys time; it does not remove the bomb. Until 1c is deployed, `status` is `running` and `now < deadline`, so `tick` returns `{'action': 'none'}` (`judge_trial.py:790-792`) and deploys are safe.

**1b. Fix the branch before editing anything.**
```bash
git checkout dev_personal
git merge --no-edit main            # brings d745e8e; dev_personal is 1 docs commit ahead
grep -n "AUDIT_DRAW_DAY\|AUDIT_LABEL_DAY\|TRIAL_DEADLINE_DAYS" personal_apps/features/radar/judge_trial.py
```
**Do not proceed unless that grep prints 1 / 2 / 3.** `dev_personal` has not touched any `judge_*` file since the merge base (`git diff --stat b82aea0..dev_personal -- …judge_*.py` is empty), so the merge is clean — but editing `judge_trial.py` on the pre-`d745e8e` version and merging it back would silently restore 3/7/10 to production.

**1c. Three hunks, two files.** This is the entire behavioural change.

**Hunk A — a named retirement switch, next to the schedule it retires.**
`personal_apps/features/radar/judge_trial.py`, after `:578`:
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
and in `deadline()` (`:581-600`), immediately after the `row is None or row.first_judged_at is None` guard:
```python
    if TRIAL_RETIRED:
        return None
```
*Changes:* `_may_judge`'s deadline branch (`:695-697`) never raises, so the encoder keeps judging past 19:38:24; `tick`'s expiry branch (`:791-792`) returns `{'action': 'none'}` forever.
*Risk:* none to data. It does mean the trial has no automatic end at all — that is the decision.

**Hunk B — a stop stops, it does not destroy.** Same file, `tick()` at `:785-789`:
```python
    if row.status == RECOVERING:
        if TRIAL_RETIRED:
            # Retired: a stop halts judging and nothing more. Recovery is an
            # operator decision made deliberately with
            # scripts/rollback_encoder_judge.py --apply, never something a
            # timer does at 2000 rows a minute with no confirmation.
            return {'action': 'none', 'status': row.status}
        report = recover_trial(apply=True, limit=limit, now=now)
        ...
```
*Changes:* this is the hunk that actually removes the bomb — it covers **both** the minute timer and the startup tick at `run_radar_ingest.py:1272`. After it, `manage_encoder_trial stop` becomes non-destructive: it halts judging (`_may_judge:689-690`) and is undone by `UPDATE radar_judge_trial SET status='running', stop_reason=NULL WHERE id=1`.
*Risk:* a genuine emergency rollback now needs the explicit `rollback_encoder_judge.py --apply`. That is the point.

**Hunk C — the artifact hash reports instead of gating.** `personal_apps/features/radar/judge_config.py:179-184`:
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
*Changes:* this is what lets Phase 2 exist. `_encoder_or_none` (`:166-185`) is reached only for `primary.id == ENCODER_MODEL_ID` (`:144-145`), and the raise at `:181` is uncaught at `run_radar_ingest.py:1275` — it kills the **entire ingest daemon**, not just judging.
*What is deliberately kept:* the log line still prints the live artifact's hash every startup. That is the only forensic record of which model is serving.
*Risk:* nothing now proves the deployed files are the audited ones. Accepted — that proof was the trial's, and the trial is being retired. Mitigate by verifying hashes by hand at 2c.

**Optional same-commit doc fix (recommended, zero risk):** `judge_trial.py:443-445` and `scripts/rollback_encoder_judge.py:22-23` both still assert *"Tone and its provenance are NOT cleared. The trial never wrote them"*. That became false on 2026-09-07 (`judge_backends.py:210` `writes_tone = True`; `llm_sentiment.py:493-502`). Correct the text so the next operator is not misled about what a recovery would leave behind.

**1d. Tests.** These currently pin the behaviour Hunks A/B remove and **will go red**:
- `personal_apps/tests/test_radar_judge_trial.py:999` `test_the_guard_refuses_on_the_deadline_itself`
- `:1033` `test_an_unevaluated_trial_still_expires_on_day_ten`
- `:1023` `test_a_failing_audit_does_not_lift_the_deadline`
- `:897` `test_a_failing_audit_stops_the_trial_without_waiting_to_be_noticed`
- `personal_apps/tests/test_radar_judge_config.py:184` `test_a_different_artifact_than_the_one_armed_is_refused`

Do **not** delete them. Monkeypatch `judge_trial.TRIAL_RETIRED = False` in each so the un-retired semantics stay tested — that is what makes the revert trustworthy — and add three new ones asserting, with `TRIAL_RETIRED = True`: `deadline()` is `None` past day 3; `tick()` on a `RECOVERING` row recovers **zero** mentions; a mismatched bundle hash starts the encoder. Then `pytest personal_apps/tests/test_radar_judge_*.py personal_apps/tests/test_radar_trial_writes.py personal_apps/tests/test_encoder_*.py`.

**1e. Commit, merge, push, deploy.**
```bash
git add -A personal_apps/features/radar/judge_trial.py \
           personal_apps/features/radar/judge_config.py \
           personal_apps/scripts/rollback_encoder_judge.py personal_apps/tests/
git commit          # message names the decision, not just the diff
git checkout main && git merge --no-edit dev_personal && git push origin main dev_personal
git checkout dev_personal
```
Michi runs `./update_coc.sh`.

**1f. Verify on the VPS, before touching the artifact.**
```bash
journalctl -u radar_ingest -n 80 --no-pager | grep -Ei 'judge|encoder|trial'
```
Expect: `radar judge: primary=radar-encoder-v1 review=…`, plus the new `trial retired` line naming `3bb32b5607a8`. Then re-run the two `COUNT(*)` queries from 0b — **they must be unchanged or higher, never lower.** Then confirm a sentiment pass runs (`radar sentiment` lines, ten-minute cadence, `run_radar_ingest.py:1378-1381`).

At this point the 19:38 UTC deadline is dead, the judgments are intact, and nothing has been swapped. **Phase 2 can wait a day if it needs to.**

---

### Phase 2 — put base in production

**2a. Package base into a separate root** (heavy local job: `torch.onnx.export` of a ~184M-param fp32 model, several GB RAM, minutes — per standing preference, get Michi's "when" first):
```bash
cd /c/Users/michi/Desktop/CodingStuff/personal_apps
python scripts/package_encoder_artifact.py \
  --model "C:/Users/michi/Desktop/radar_labels/encoder/model-train17090-20260907-192428" \
  --out   "C:/Users/michi/Desktop/radar_labels/artifact-base" \
  --base  microsoft/deberta-v3-base
```
*Note:* `--out` root is **not** the live one. `version_dir` is hardcoded to `v1` (`package_encoder_artifact.py:132`) and `active.json` is always written `{"path": "v1/"}` (`:197-199`) — there is no `--version` flag, so packaging into the live root would **overwrite the audited small bundle in place**. Expect ~736 MB; the `size < 400` warning (`:203-205`) is calibrated for small and will not fire. Record the printed `bundle sha256` (`:207`).

**2b. Validate locally, on a v2-shaped staging root, before anything leaves the machine.** Lay the three files out as `…/staging/v2/`, write `{"path":"v2/","id":"radar-encoder-v1"}` as `staging/active.json`, then construct `EncoderBackend(staging)` and run one `judge_batch` of ~8 real texts, printing peak RSS. This exercises exactly the paths production will: `_validate` (`judge_backends.py:258-302` — files present, `max_len == 256`, head names as a set, head class lists as ordered tuples) and the one contract **nothing checks** — that the ONNX graph's output names equal the five head names (`:376-381`, outside the `try` at `:371-374`; a mismatch is a bare `KeyError` that kills every pass, silently, forever). Nothing validates hidden size, layer count or vocab, and `config["base"]` is written but read by no runtime code — so this smoke test is the only thing standing between you and a wrong model that loads happily.
Peak RSS matters: `ENCODER_BATCH_SIZE = 4` (`judge_backends.py:155`) was chosen because small was flat at 1,081 MB at batch 4 and jumped to 1,715 MB at batch 16, on a box now also running MariaDB with a 2500M buffer pool (`3681295`). Twelve layers instead of six roughly doubles activation memory. If peak RSS at batch 4 is uncomfortable, lower `ENCODER_BATCH_SIZE` to 2 in the same Phase-2 commit. `ENCODER_PASS_LIMIT = 400` (`:156`) almost certainly survives: at ~3.5 rows/s that is ~115 s inside a 600 s window, and `max_instances=1, coalesce=True` absorbs an overrun.

**2c. Ship as `v2/`, overwriting nothing.**
```bash
ssh root@194.164.29.97 'mkdir -p /root/coc-stats/personal_apps/artifacts/judge/v2'
scp "C:/Users/michi/Desktop/radar_labels/artifact-base/v1/model.onnx"     root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
scp "C:/Users/michi/Desktop/radar_labels/artifact-base/v1/tokenizer.json" root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
scp "C:/Users/michi/Desktop/radar_labels/artifact-base/v1/config.json"    root@194.164.29.97:/root/coc-stats/personal_apps/artifacts/judge/v2/
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && sha256sum v1/* v2/*'
```
Compare v2's three digests against local `sha256sum`, and confirm **v1's three still equal `e97bcb96… / 20643390… / fb20c709…`** — proof the small artifact survived the transfer untouched.
*Note the target:* `194.164.29.97`. The runbook's `scp` at `docs/superpowers/plans/2026-09-06-radar-encoder-judge-runbook.md:202` still names `82.165.240.212`, which is the stopped fallback box. Do not copy-paste it.
*Why v2/ and not in-place:* `bundle_sha256` hashes `os.path.dirname(self.model_path)` (`judge_backends.py:233`), and `model_path` comes from the `active.json` pointer (`:258-268`) — so the pointer, which is deliberately outside the digest (`:228-231`), is the atomic switch. In-place `scp` over a running daemon writes into a file onnxruntime holds mapped (`:318-347`, session built once and held for process lifetime), risks a truncated read, and shows no symptom until a restart hours later kills all of ingest.

**2d. Flip the pointer atomically.**
```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && \
  cp -a active.json active.json.v1.bak && \
  printf "{\n \"path\": \"v2/\",\n \"id\": \"radar-encoder-v1\"\n}" > active.json.new && \
  mv -f active.json.new active.json && cat active.json'
```
`id` must stay `radar-encoder-v1` verbatim — `_validate` asserts pointer id == `ENCODER_MODEL_ID` (`judge_backends.py:261-264`), and `_may_judge:673-677` compares the code constant against the frozen row. Changing `ENCODER_MODEL_ID` is a dead daemon in both directions (see §2.10).

**2e. Restart and watch.**
```bash
ssh root@194.164.29.97 'systemctl restart radar_ingest'
ssh root@194.164.29.97 'journalctl -u radar_ingest -n 100 --no-pager | grep -Ei "judge|encoder|sentiment|Traceback"'
```
Expect the `trial retired` line to now name **the base bundle hash**. Then wait for one sentiment pass and confirm rows are being judged, plus `ps -o rss= -C python` / `systemd-cgtop` for actual RSS.

**2f. Record the swap timestamp.** Because base and small rows both carry `sentiment_model = 'radar-encoder-v1'` (`judge_backends.py:215` → `llm_sentiment.py:497`), the **only** discriminator that will ever exist is `radar_sentiment_judgments.created_utc` against the restart time. Write it into `/root/trial-audit/base-swap.txt` and into the handover, with the base bundle hash. Do it now; it is unrecoverable later.

**Rollback for the whole of Phase 2, one command:**
```bash
ssh root@194.164.29.97 'cd /root/coc-stats/personal_apps/artifacts/judge && \
  mv -f active.json.v1.bak active.json && systemctl restart radar_ingest'
```
**Rollback for Phase 1:** `git revert` the commit, deploy, `systemctl enable --now radar-encoder-trial.timer`. Note the deadline is a *stored* `first_judged_at + 3d` and has passed by then, so re-arming the watchdog after a revert **will** drain. Reverting Phase 1 is only correct together with a decision to destroy the judgments.

---

## 2. PATHS THAT LOOK ATTRACTIVE AND DESTROY DATA

**2.1 `python -m scripts.manage_encoder_trial stop --reason "abandoning the trial"` — the operator's own word, and the single most likely mistake.** It writes two columns (`judge_trial.py:297-298`) and prints *"the decisions already made are still in the counts until recovery runs"* (`manage_encoder_trial.py:120-122`). That sentence is true for about 59 seconds. `tick` treats `RECOVERING` as an unconditional instruction to drain (`judge_trial.py:785-789`) and the timer fires every minute at `--limit 2000`. The project's own runbook §9 presents this as step 1 under *"the first alone is not a rollback"*. **The runbook is wrong.** After Phase 1 Hunk B this command becomes harmless; before it, it is the delete button.

**2.2 `python -m scripts.audit_encoder_trial accept …` on the current FAILING report.** A failing report is a *result*, not an error: `accept_audit` passes the flag through (`audit_encoder_trial.py:946`) and sets `status = RECOVERING` + a `stop_reason` itself (`judge_trial.py:657-660`), then prints *"The trial is now recovering."* Identical outcome to 2.1. It is also **one-way twice**: once `audit_evaluated_at` is set, a different report can never be recorded (`judge_trial.py:637-641`).

**2.3 "Let me just complete the report properly so the record is clean."** The two blockers — every reference row lacking `labelled_at`, and no supplemental sets — are the only reason 2.2 has not already happened (`audit_encoder_trial.py:893-896`; `judge_trial.py:625-626`). Fixing them arms the destruction. And under production's schedule the labelling window closed at `first_judged_at + AUDIT_LABEL_DAY(2)` = **2026-09-08 19:38:24 UTC, today** (`audit_encoder_trial.py:938-943`), so `accept` is probably refused anyway — by luck, not by design.

**2.4 Lowering `REMOVAL_PRECISION_FLOOR` to force a pass.** Tempting because a passing audit is the one in-code state where `deadline()` returns `None` (`judge_trial.py:597-598`). Four reasons not to: (a) it fabricates a verdict, against the module's explicit warning that "3-versus-1 wrong deletions out of 200 became an argument for shipping once already" (`trial_audit.py:12-15`); (b) it needs a `labelled_at`/`completed_at` that would have to be invented; (c) it is one-way (`judge_trial.py:637-641`); and decisively (d) **it does not get base deployed** — a pass leaves `artifact_sha256` frozen at `3bb32b56…` and `judge_config.py:179-184` still refuses the new bundle. It buys the deadline and forfeits the goal.

**2.5 `python -m scripts.rollback_encoder_judge --apply --limit 1` "to see what happens".** `--apply` calls `request_stop('recovery run')` first (`rollback_encoder_judge.py:51-54`) — deliberately, so a half-finished run cannot race the daemon. That one probe commits the trial to `RECOVERING` permanently, and (pre-Hunk-B) the timer finishes the rest. **The flagless dry run is the only safe form** (`:64-66`).

**2.6 `DELETE FROM radar_judge_trial WHERE id = 1` to clear the way for a new trial.** Before Phase 1: `_may_judge` raises on `row is None` (`judge_trial.py:669-672`) → `ConfigError` (`judge_config.py:178`) → uncaught at `run_radar_ingest.py:1275` → **the whole ingest daemon fails to start**, taking all 13 scheduled jobs with it (no fetch, no scoring, no quotes, no prune). Radar's sources are cursor-and-budget driven; every minute down is mentions that are never collected and cannot be backfilled. It also releases the retention pin instantly (`judge_trial.py:167-170` → `retention.py:44-46`), so the next 04:30 prune deletes the journal back to 48 hours — the only substrate any future bucket rebuild could read. After Phase 1 this DELETE is *safe but unnecessary*; see §3.1.

**2.7 Deleting the row and arming a second trial for the base hash.** The worst reachable end state, and the most obvious sequence. `_recoverable` selects on `model_id` + `prompt_version` **only** (`judge_trial.py:333-337`) — never on the artifact hash — and both are re-frozen from the same code constants. A trial #2 armed today therefore owns every mention the small model judged, while its `retain_from` is `now − 48h`. The moment `_plan` (newest-first, `:368-372`) reaches an older window, `recover_trial` raises (`:463-470`, `:505-507`); `remaining` never reaches zero; `_release_if_drained` never flips to `RECOVERED`; the pin is held forever; `_encoder_or_none` returns `None` so **judging is off permanently** (`judge_config.py:170-177`); and the watchdog logs a failure every 60 seconds. Reachable only after some rows have already been destroyed.

**2.8 Packaging base with `--out personal_apps/artifacts/judge`, or `scp -r artifacts/judge …` as the runbook says (`:202`).** Both overwrite `v1/` in place. That destroys the byte-exact audited artifact, and `audit_encoder_trial.py:329-335` then refuses `predict --backend encoder` forever — the failed audit can never be re-run or extended, including on the 44 wrongly-removed rows. Unrecreatable (§0.2).

**2.9 The runbook's `scp` target `82.165.240.212`.** Decommissioned 2026-09-07. Copies 740 MB to a stopped box; the symptom on the live box ("hash still doesn't match") reads like a packaging bug.

**2.10 Bumping `ENCODER_MODEL_ID` to `radar-encoder-v2`, or touching `PROMPT_VERSION`.** `_may_judge:673-681` and `:682-686` compare both against the frozen row; either mismatch raises `TrialError` → `ConfigError` (`judge_config.py:178`) → dead daemon. And `active.json`'s `id` must move with the constant or `_validate` rejects the pointer (`judge_backends.py:261-264`), also dead. Code and row would have to change in the same restart. Also `spend.py:58` hardcodes `'radar-encoder-v1': (0.0, 0.0)`; a v2 id makes `cost_micros` return `None` and the board reports encoder tokens as "unpriced" instead of free.

**2.11 `RADAR_JUDGE_TONE=1`** — the instinct when shipping a model whose tone you now trust. `judge_config.py:89-97` raises `ConfigError` for any value but `'0'`: dead daemon. And `Settings.write_encoder_tone` (`:102`) is hardwired `False` and read by nothing; tone already publishes via `judge_backends.py:210`.

**2.12 `RADAR_JUDGE_PRIMARY=anthropic:radar-encoder-v1` as a hash-check bypass.** It does skip the artifact check (no `bundle_sha256` attribute, `judge_config.py:180`) — but the string becomes the Anthropic **API model name** and 404s on the first call, while storing nothing under encoder provenance. Dead end; not an escape hatch.

**2.13 "Just let it recover, that's the safe option."** It is not safe and it does not even produce a clean pre-trial state. `recover_trial` clears five columns (`judge_trial.py:511-515`) and leaves `sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment`, `sentiment_tone_model` — which the encoder now writes (`judge_backends.py:210`; `llm_sentiment.py:493-502`) and which `board.py` reads first for bull/bear. A "complete" recovery undoes the encoder's effect on **volume** counts and not on **direction** counts, leaving mentions that claim to be unjudged while still carrying `sentiment_tone_model='radar-encoder-v1'`. That is a state no code was written for. *(I read the writing side and the clearing side directly; I did not run a recovery to observe it. The recommended path never triggers one, so it does not gate the plan — but it does kill "recovery is the conservative choice".)*

**2.14 Running any trial command from `C:\Users\michi\Desktop\CodingStuff` against production.** See §0.1. The reassuring reading and the destructive one come from the same command name.

---

## 3. OPEN QUESTIONS THAT NEED THE OPERATOR

**3.1 The retention pin: leave it, or release it later?** With the row left `running`, `retention_floor()` keeps returning `retain_from` ≈ 2026-09-04 (`judge_trial.py:158-170`), and `retention._pinned` clamps both pruners at it (`retention.py:23-46`). `radar_mention_events` normally lives 48 hours (`config.py:610`) and posts 30 days (`:603`); pinned, the journal accumulates from 2026-09-04 forward with no horizon, on an 8 GB box. The runbook already asked for daily `df -h` for a bounded 3-day trial; this is unbounded. Options: (a) leave it and watch disk — every judgment stays undoable; (b) after Phase 1 is verified, `DELETE FROM radar_judge_trial WHERE id = 1` — safe once the code no longer needs the row, releases the pin, resumes normal retention, and **does not touch a single judgment**, but ends the ability to undo anything and (per 2.7) must never be followed by an `arm`. My read: do (a) now, revisit at the first disk warning. **His call, because it is a "how much optionality do you want to pay disk for" question.**

**3.2 Should base-model rows be distinguishable from small-model rows?** Keeping `radar-encoder-v1` (the recommended path) is the low-risk move tonight but makes "undo only the base model's week" permanently impossible — nothing in `radar_mentions` or `radar_sentiment_judgments` separates them except a timestamp you have to record by hand (2f). Distinguishing them means bumping `ENCODER_MODEL_ID`, which means removing the id check from `_may_judge` (a bigger diff) plus a `spend.py:58` entry. This is the exact trap the codebase already fell into once — `stored_row_carries_tone` exists because one id could not tell two behaviours apart.

**3.3 Does the base model keep publishing tone?** Tone was never audited; `trial_audit.py`'s docstring says tone "is reported and never gates". The measured case is strong (reversals: lexicon 29.8% → small 11.8% → base 6.2%, over 5,583 clearly-sided rows) and it is already live for small. But turning it on for base is a decision, not a consequence, and it is currently a code edit either way (`judge_backends.py:210`), not a flag.

**3.4 The reference labeller was GPT, not a human, and calls 29% of the sample `uncertain`** against Haiku's historical 3.4% and the encoder's 16%. Independent of both judges, which is the property that matters — but one pass, no majority vote, inter-labeller disagreement unmeasured. Doesn't block tonight. It decides whether the 0.803/0.849 numbers can be cited later as anything more than indicative.

**3.5 Keep the trial machinery dormant, or delete it?** Phase 1 leaves ~1,400 lines of arm/recover/audit code that nothing reaches. That is deliberate (it is the revert path) but it is also a loaded gun in the repo. Retire the `deploy/radar-encoder-trial.{timer,service}` unit files too, or leave them installed-and-disabled?

**3.6 When may the heavy local packaging job run?** `torch.onnx.export` of a 184M-param fp32 model on his workstation — minutes, several GB RAM. Standing rule: name the window first.

**3.7 The 44 wrongly-removed mentions** (handover §9 item 7) — is a pattern hunt still wanted, given the trial is being retired? It needs the frozen artifact, which is why §0.2 matters.

---

## 4. THE 0.93 THRESHOLD

**Where it lives:** `personal_apps/features/radar/trial_audit.py:41`

```python
REMOVAL_PRECISION_FLOOR = 0.93
```

A plain module constant. Used at `:240` (copied into the report as `criteria[…]['threshold']`), `:243` (`removal_passed = coverage_ok and encoder_removal['lower'] >= REMOVAL_PRECISION_FLOOR`) and `:254` (the human-readable rule). The module reads no environment and no files — it is documented as pure at `:3-6`, and I confirmed there is no `os.environ`/`getenv` in it.

**Can a new trial be armed at a different bar without editing code? No.**
- `arm_trial` freezes only `seed`, `baseline_report`, `baseline_removal_rate`, `sample_size`, `removal_decisions_wanted` and `supplemental` into `row.recipe` (`judge_trial.py:245-270`). No threshold field.
- `RadarJudgeTrial` (`models.py:1382-1437`) has no threshold column.
- The arming CLI exposes only `--artifact-sha256`, `--baseline-report`, `--baseline-removal-rate`, `--seed`, `--supplemental-audit-keys`, `--supplemental-natural-keys` (`scripts/manage_encoder_trial.py`, `cmd_arm`).

This is deliberate, per the sibling comment on `Z` at `trial_audit.py:34-36`: *"this number decides whether a trial passes, and it should be readable in the diff that changes it."* The report's `threshold` field is a **copy** made at evaluate time, not a source of truth.

**And it cannot be back-doored:** `accept` recomputes the entire canonical report from the inputs with the *current* code and demands byte-identical reproduction (`audit_encoder_trial.py:917-925`). Changing the constant between `evaluate` and `accept` makes the report fail to reproduce rather than silently re-grading it.

For the record, none of this is on the recommended path — the plan never runs `evaluate` or `accept` again.

---

## 5. WHERE I DISAGREE WITH THE INPUTS, OR COULD NOT VERIFY

**Confirmed and consequential:**
- The 1/2/3 vs 3/7/10 correction (§0.1). All four readers' timing statements describe a checkout that is not in production. Their `judge_trial.py` citations ≥575 are one line low.
- The preserved bundle (§0.2). The *deploy-swap* reader's "the only complete artifact in the repo is the 12 KB test fixture" is true of git and misses the worktree copy. That single fact turns rollback from "repackage and re-arm" into "do not delete one directory" — and I verified the hash myself rather than taking it on trust.
- `stop-semantics` §1's *"`stop` does not itself undo anything"* is literally true of `request_stop` and materially false as operator guidance, because of the installed minute timer. Same for `manage_encoder_trial.py:120-122` and runbook §9.
- The `anthropic:radar-encoder-v1` "escape hatch" (*artifact-gate* §4) is a dead end, as the rollback verdict says: the string becomes the API model name.
- `deploy-swap` §3's "ship into a new `v2/` directory" is not something the packaging tool can do — `v1` is hardcoded at `package_encoder_artifact.py:132` and `:199`. The recommended path does it by hand, which works because `active.json` is outside the digest (`judge_backends.py:228-231`).

**Not verified by me — check on the box before executing:**
- The live trial row's actual `status`, `first_judged_at`, `audit_evaluated_at`. Everything here assumes `running` / `2026-09-06 19:38:24` / NULL, from the handover. Step 0b is the gate.
- That `radar-encoder-trial.timer` is actually enabled on `194.164.29.97` (the handover says yes; `systemctl is-enabled` settles it).
- Whether the VPS's `v1/` is byte-identical to the local copy — step 2c's `sha256sum` answers it.
- The reference labels' `completed_at` stamp, which decides whether the accept route is already closed. Irrelevant to the recommended path; relevant if anyone argues for 2.4.
- Free disk on `/` (§3.1).
- Whether `radar_sentiment_judgments` rows for this trial will start aging out around 2026-10-06 regardless of pin: the *data-loss* verdict argues `_pinned` takes `min(cutoff, floor)` and `retain_from` is later than `now − 30d`, so the pin cannot protect posts from the 30-day horizon. I read `retention.py:44-46` and it is consistent with that reading, but I did not trace `prune_posts` end-to-end. If the encoder's judgment evidence matters beyond a month, that needs its own answer — it is not a Phase-1 or Phase-2 blocker.

**One thing all inputs agree on and I confirmed:** there is no supported state in which the judgments survive *and* the retention pin releases. `_release_if_drained` (`judge_trial.py:553-557`) requires `_recoverable().count() == 0`, i.e. requires the destruction. Phase 1 does not solve that; it makes it a decision someone takes deliberately later (§3.1) instead of one a timer takes tomorrow at 19:38.
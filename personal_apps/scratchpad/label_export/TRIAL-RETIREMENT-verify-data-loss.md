## DATA LOSS lens — risk register

Verified against the working tree (`dev_personal`, `C:/Users/michi/Desktop/CodingStuff/personal_apps/…`) **and** against `main`, which is what is deployed (`b1d1a7c`). Where the two differ I say so — one of those differences invalidates part of all four readers' notes.

---

### 0. CORRECTION FIRST: every reader read the wrong deadline constants

`main` and `dev_personal` disagree, and `main` is what runs in production:

- `main:personal_apps/features/radar/judge_trial.py:576-578` — `AUDIT_DRAW_DAY = 1`, `AUDIT_LABEL_DAY = 2`, **`TRIAL_DEADLINE_DAYS = 3`**, above the comment `# Schedule amended 2026-09-07: keep the original first-judgment clock.`
- working tree / `dev_personal:…judge_trial.py:575-577` — `3 / 7 / 10`.

The change is commit `d745e8e fix(radar): shorten the live encoder trial to a 1/2/3-day audit schedule`, and `git merge-base --is-ancestor d745e8e dev_personal` → **NO**. `dev_personal` predates it and was never rebased.

Consequences for this plan:

1. **All four readers cite `judge_trial.py:575-577` as 3/7/10 and reason about "day 3 / day 7 / the 10-day deadline". That is the un-deployed file.** Production expires the trial at `first_judged_at + 3 days` = **2026-09-09 19:38 UTC**, i.e. ~30 h from now, exactly as the task statement says. The readers' arithmetic would have put it at 2026-09-16 and told the operator there is a week of slack. There is not.
2. Everything the readers cite at `judge_trial.py:575` and below is **one line low** relative to the deployed file (`deadline()` is at `:581` on main, `_may_judge` at `:668`, `guard_encoder_trial` at `:700`, `tick` at `:783`, `accept_audit`'s `row.status = RECOVERING` at `:660`). Citations at ≤ 574 are identical in both.
3. **Concrete destruction path:** if anyone runs `python -m scripts.manage_encoder_trial status`/`tick` **from this checkout** against the production database while working on the base deploy, `tick` computes `deadline()` with `TRIAL_DEADLINE_DAYS = 10`, returns `{'action': 'none'}` (`judge_trial.py:804-806`), and the operator concludes the trial is safely inside its window — while `radar-encoder-trial.timer` on the VPS, running main's code, stops and drains it at 19:38 UTC tomorrow. The reassuring reading and the destructive one come from the same command name.
4. A `git merge dev_personal` into main is *safe* here (merge base is `b82aea0`, `dev_personal` never touched `judge_trial.py`/`audit_encoder_trial.py` after it, so git keeps main's side). But **`scp`/`rsync` of files from this tree to the VPS is not** — it would silently revert `d745e8e` including the audit-chain timing (`audit_encoder_trial.py:930-943` becomes `day3 <= drawn_at <= day7`), which makes the already-drawn 2026-09-07 sample permanently un-acceptable.

---

### 1. Doing nothing destroys everything, on a clock

`deploy/radar-encoder-trial.timer:17` `OnCalendar=*-*-* *:*:00`, `Persistent=true`; `radar-encoder-trial.service:27` `ExecStart=… -m scripts.manage_encoder_trial tick --limit 2000`. The handover confirms it is **live in production** (`TRIAL-RETIREMENT-HANDOVER.md:31`).

At 2026-09-09 19:38 UTC the next firing hits `judge_trial.tick` → `request_stop(...)` → `recover_trial(apply=True, limit=2000)` (`judge_trial.py:811-813` dev / `:812-814` main), then every following minute drains another 2000. At the audit's own frame size (6,207 high-confidence mentions in the first 24 h alone, handover §3), the full set is plausibly 15k–40k rows — **destroyed in roughly 10–20 minutes, unattended, with no confirmation step**.

`Persistent=true` means stopping the VPS does not buy time; the first firing after boot enforces the original deadline.

---

### 2. `stop` is not "stop". It is "destroy, starting within 60 seconds"

- `scripts/manage_encoder_trial.py:117-123` → `request_stop` sets only `status = RECOVERING` (`judge_trial.py:297`) and prints *"This stops NEW judgments; the decisions already made are still in the counts until recovery runs."*
- That printed sentence is **false on the deployed layout**. `tick` treats `RECOVERING` as an instruction to drain unconditionally (`judge_trial.py:798-802`), and the timer fires every minute.
- `docs/superpowers/plans/2026-09-06-radar-encoder-judge-runbook.md` §9 repeats the same wrong reassurance — *"Two steps, and the first alone is not a rollback"* — then presents `manage_encoder_trial stop --reason …` as step 1. **An operator following the project's own runbook loses the judgments at step 1.** This is the single highest-probability destruction path in the whole plan, because the runbook is where anyone will look for "how do I retire the trial".
- There is no path back: `recover_trial` refuses to continue if it ever sees a status other than `RECOVERING`/`RECOVERED` (`judge_trial.py:498-501`), `note_first_judgment` refuses to revive (`:776-778`), `_may_judge` refuses to judge (`:691-692`). **`RECOVERING` is terminal in one direction only.**

### 2b. `rollback_encoder_judge.py --apply` issues the stop itself

`scripts/rollback_encoder_judge.py:51-54`: if the trial is not already recovering, `--apply` calls `request_stop('recovery run')` **before** recovering. So a "let me just drain 1 row to see what happens" (`--apply --limit 1`) permanently commits the trial to `RECOVERING`, and the minute timer finishes the other 20,000. Only the flagless dry run is safe (`:64-66`).

---

### 3. `audit … accept` on the failing report destroys the judgments

`judge_trial.accept_audit` accepts a failing report as a *result*, not an error, and sets `status = RECOVERING` + `stop_reason` itself (`judge_trial.py:656-660` dev / `:656-660` main). `scripts/audit_encoder_trial.py:950-952` then prints *"The trial is now recovering."* Same drain as §1.

So **"finish the audit properly so the record is complete" is a destruction command**, not a book-keeping one. The two things currently blocking `accept` (missing `labelled_at` on every reference row, missing supplemental sets — `audit_encoder_trial.py:893-896`, `judge_trial.py:625-626`) are the only reason the failing report has not already destroyed the trial. **Fixing them without deciding the retirement path first is the mistake to guard against.**

Note also that on production's schedule the labelling window closed at `first_judged_at + 2 days` = **2026-09-08 19:38 UTC (today)** (`audit_encoder_trial.py:938-943`), so an `accept` attempt after that is refused anyway — but that refusal is luck, not a safety design.

---

### 4. Exactly what recovery destroys, and what cannot be restored

Per window, one transaction (`judge_trial.py:485-528`), selected by the trial's frozen `(model_id, prompt_version)` (`_recoverable`, `:333-337`):

| what | where | recoverable afterwards? |
|---|---|---|
| `sentiment_relevance`, `sentiment_content_origin`, `sentiment_model`, `sentiment_prompt_version`, `sentiment_judged_at` → NULL on **every** encoder-judged mention (kept verdicts too, not just removals) | `judge_trial.py:511-515` | **No.** No redo path exists in the codebase. |
| a prior judge's verdict that the encoder had overwritten | same | **No** — nulled to unjudged, the earlier verdict is not on the mention anywhere. |
| `radar_mention_events.counts_as_human_chatter` → NULL, `chatter_decided_at` → **overwritten with the recovery timestamp** | `journal.py:239-245` | **No.** The original decision time is gone. |
| `radar_buckets`: all eight summary fields + `source_config_version`, overwritten in place | `buckets.py:438-441`, `_summarize` `:121-137` | **No.** `radar_buckets` is retained forever (`models.py:718`) and nothing versions it. The rebuild is a fresh recompute, not a restore. |
| `radar_bucket_sources`: same eight fields, plus `expected`/`variance`/`mention_z`/`baseline_days` **all NULLed** on any generation mismatch or non-scoreable status | `buckets.py:447-462` | Baselines only return on the next scoring pass. |
| `radar_mention_events.promoted` reset then re-marked | `journal.mark_promoted`, `journal.py:196-207` | recomputed, fine |

**Preserved, with three caveats:** `radar_sentiment_judgments` is append-only and untouched (`tests/test_radar_judge_trial.py:611-623` pins it). But (a) nothing reads it back to re-materialize a mention — `latest_primary_history` (`llm_sentiment.py:571-593`) is used only for review routing; (b) `mention_id` is `ON DELETE CASCADE` (`models.py:1334-1337`), mentions cascade from posts, and `POST_RETENTION_DAYS = 30` (`config.py:603`) — **and the pin cannot protect them, because `_pinned` takes `min(cutoff, floor)` (`retention.py:46`) and `retain_from` (≈2026-09-04) is *later* than `now − 30 d`. So the trial's own judgment evidence starts being deleted around 2026-10-06 no matter what status the trial is in;** (c) the `displayed_tone*` diagnostic columns stopped being written when the encoder started publishing tone (`llm_sentiment.py:485`), so `_shadow` (`audit_encoder_trial.py:587-600`) is frozen at whatever accumulated before 2026-09-07.

---

### 5. The tone orphan — confirmed, and it is a live board defect, not a footnote

`recover_trial`'s docstring asserts *"Tone and its provenance are NOT cleared. The trial never wrote them"* (`judge_trial.py:443-445`), and `scripts/rollback_encoder_judge.py:22-23` repeats it. **The premise became false on 2026-09-07.** `judge_backends.py:210` `writes_tone = True`; `llm_sentiment.py:493-502` writes `sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment` and `sentiment_tone_model = model` under `write_tone`; `run_pass` passes `write_tone=judge_backends.writes_tone(backend)` (`llm_sentiment.py:862`).

After a "complete" recovery, every affected mention is left with `sentiment_model = NULL` beside `sentiment_tone_model = 'radar-encoder-v1'` and a live `sentiment_attitude` — and `board.py:363-374` reads attitude first, legacy second, lexicon last. **The recovery therefore does not undo the encoder's effect on the board's bull/bear counts; it only undoes its effect on the volume counts.** The regression test that is supposed to protect this stages the row with `sentiment_tone_model = 'claude-haiku-4-5'` (`tests/test_radar_judge_trial.py:626-645`) — it tests the world where the tone belonged to someone else, so it will stay green through this defect.

Net: the "safe rollback" path does not produce a clean pre-trial state. It produces a state no code was written for.

---

### 6. Re-arming for the base model: three ways to lose the old judgments permanently

`arm_trial` refuses to overwrite the singleton (`judge_trial.py:247-250`), and **there is no delete path for `RadarJudgeTrial` anywhere in production code** — `grep -rn RadarJudgeTrial --include=*.py` outside `tests/` returns only reads and the one construction. So arming a second trial requires hand-written SQL. That is where the losses are:

- **Deleting the row releases the pin instantly.** `retention_floor()` returns `None` when `current()` is `None` (`judge_trial.py:167-170`) → `_pinned` (`retention.py:44-46`) stops clamping → `prune_mention_events` at the next 04:30 UTC (`run_radar_ingest.py:1373`) deletes everything older than 48 h (`retention.py:325-340`, `MENTION_EVENT_RETENTION_HOURS = 48`, `config.py:610`). That is **~5 days of journal, the only substrate any bucket rebuild can ever read**, gone in one nightly run. After it, no window in the trial's span can be corrected again by anything.
- **A new trial inherits the old trial's rows.** `_recoverable` keys on `(model_id, prompt_version)` only (`judge_trial.py:335-337`); there is no artifact hash on `radar_mentions` and `ENCODER_MODEL_ID` is a constant (`judge_backends.py:149`) `self.id = ENCODER_MODEL_ID` (`:215`). Base-model rows and small-model rows are indistinguishable in the database. So **any future stop of the base trial nulls the small model's judgments too** — the thing this whole exercise is trying to protect.
- **And that recovery can never complete.** A re-armed trial gets `retain_from = _quarter_hour_after(now − 48 h)` (`judge_trial.py:261`, `PIN_LOOKBACK` `:49`). Old encoder-stamped mentions sit in windows before that floor, so `recover_trial` raises at `:463-470` / `:505-507` once `_plan`'s newest-first ordering (`:371`) reaches them. `remaining` never reaches 0, `_release_if_drained` never flips to `RECOVERED` (`:553-557`), judging stays off (`_may_judge` `:691-692`), the pin is held forever, `radar_mention_events` grows without bound, and the timer logs a refusal every 60 seconds. **Permanent deadlock, reachable only after some rows have already been destroyed.**

Also: `_shadow` (`audit_encoder_trial.py:591-596`) filters on `model == row.model_id AND prompt_version == …` with no time or artifact bound, so a re-armed base trial would count the small model's shadow rows as its own evidence.

---

### 7. Artifact swap: the small model's bundle is destroyed by the documented command, and cannot be reconstructed

- `scripts/package_encoder_artifact.py:132` hardcodes `version_dir = os.path.join(args.out, 'v1')` with `os.makedirs(..., exist_ok=True)` (`:133`), and `:197-199` writes `active.json` as `{"path": "v1/", …}`. **There is no `--version`/`v2` flag.** The runbook's own invocation is `--out personal_apps/artifacts/judge` (runbook `:95-97`). Packaging the base model therefore **overwrites `v1/model.onnx`, `v1/tokenizer.json`, `v1/config.json` in place**. The "ship into `v2/` and repoint `active.json`" option the deploy-swap reader describes is not something the tooling can do without manual file moves.
- `runbook:202` then says `scp -r artifacts/judge root@…:/root/coc-stats/personal_apps/artifacts/` — which overwrites the **deployed** small artifact in place, under a running `radar_ingest` that holds the ONNX session.
- The bundle cannot be re-created byte-for-byte afterwards: `package_encoder_artifact.py:191` writes `'packaged_at_git_head': git_head()` into `config.json`, and `config.json` is inside the hash (`judge_backends.py:236`). **Re-exporting at any other commit yields a different `bundle_sha256`.** The armed hash `3bb32b5607a8a368…` then matches nothing that exists.
- What that costs: `audit_encoder_trial.py:329-335` refuses `predict --backend encoder` unless the artifact at hand *is* the armed one. **Once `v1/` is overwritten, the failed audit can never be re-run, re-examined, or extended — not for the 44 wrongly-removed rows (handover §9 item 7), not for anything.** The artifact is gitignored (`.gitignore:28`) and `personal_apps/artifacts/` does not exist in this checkout at all, so the VPS copies are the only ones.
- Stale target: `runbook:202` still names `82.165.240.212`. Production moved to `194.164.29.97` on 2026-09-07 and the old box is stopped. A copy-pasted `scp` succeeds against nothing that matters and leaves the operator believing base is deployed.

---

### 8. Traps that cause an ingest outage, which is itself unrecoverable data

Three separate startup failures kill the whole `radar_ingest` process, not just judging, because `initialize_judges` is called uncaught at `run_radar_ingest.py:1275` (the comment at `:1259-1264` says so deliberately):

- artifact hash ≠ armed hash → `ConfigError` (`judge_config.py:179-184`) — this is what you hit the moment base is deployed under the live trial;
- editing `ENCODER_MODEL_ID` to `radar-encoder-v2` → `_may_judge` raises (`judge_trial.py:682-685`) → `_encoder_or_none` re-raises as `ConfigError` (`judge_config.py:178`);
- any `EncoderArtifactError` from `_validate` (`judge_backends.py:258-302`) — missing file, `max_len ≠ 256`, reordered head classes.

The daemon dies **before** `build_fetchers()` (`:1277`) and the scheduler. Radar's live sources are cursor/drain-budget driven (the Bluesky "captured minutes per day" fix in `74482fe` is exactly this), so **every minute the daemon is down is mentions that are never collected and cannot be backfilled.** Treat a failed startup as data loss, not as a config error.

Nuance worth knowing: the artifact check is *skipped* once the trial is `RECOVERING`/`RECOVERED`, because `_encoder_or_none` returns `None` at `judge_config.py:170-177` before the hash is computed. So "drain the trial first, then deploy base" starts the daemon fine — and judges nothing (`llm_sentiment.py:783-784` returns 0). That is the shape of the trap: the path that makes the deploy *easy* is the path that destroys the judgments and then silently leaves the board unjudged.

---

### 9. Disabling things does not save you

- `RADAR_JUDGE_PRIMARY=none` / unset: the startup `tick` at `run_radar_ingest.py:1272` is **unconditional and runs before `initialize_judges`**. If the deadline has passed or the status is already `RECOVERING`, restarting the daemon drains 2000 rows regardless of the env var. Since `./update_coc.sh` restarts `radar_ingest`, **any deploy after 2026-09-09 19:38 UTC is itself a destruction event.**
- `systemctl disable --now radar-encoder-trial.timer` blocks the per-minute drain but not the startup one. Both have to be handled, and the only durable fix is a code change to `deadline()`/`tick()`/`_may_judge` landed *before* the deadline.
- Editing `retain_from` in SQL to widen the pin is the natural operator improvisation and it is a landmine: it does not affect `_recoverable`, but it does change `identity` (`judge_trial.py:460`), so any recovery already in flight aborts with *"the trial record changed while recovering"* (`:502-504`).

---

### 10. Two lower-confidence items, flagged honestly

- `_rebuild_windows_locked` skips any window with no `RadarBucketSource` children (`buckets.py:426-429`) while the mention clear and the journal sync for that window have already been applied. Such a window keeps its trial-era counts forever with no judgment behind them. Buckets are never pruned so this should be rare (windows predating a source's existence), but the failure is silent and permanent.
- If anything bumps `source_config_version` between now and a recovery, `buckets.py:452-457` NULLs `expected`/`variance`/`mention_z`/`baseline_days` on **every** rebuilt child, wholesale. Handover §9 item 6 already requires the version stay at `3f96922d51fe4ef0`; this is the reason it matters.

---

### 11. Reader claims I could not support

- **"day 3 / day 7 / 10-day deadline"** — wrong for production (§0). Every timing statement in the *accept-path* and *stop-semantics* notes that depends on `AUDIT_DRAW_DAY`/`AUDIT_LABEL_DAY`/`TRIAL_DEADLINE_DAYS` needs re-reading against `main`.
- **"`stop` does not itself undo anything"** (stop-semantics §1) — literally true of `request_stop`, materially false as operator guidance given the installed timer. The same is true of the runbook's §9 sentence and `manage_encoder_trial.py:120-122`'s printed reassurance.
- **`stored_row_carries_tone` at `llm_sentiment.py:431-441` and `backend_label` at `llm_sentiment.py:459-460`** (deploy-swap §3) — both are in `judge_backends.py` (`:431-441` and `:444-460`); `llm_sentiment.py:619` calls them through the module. Doesn't change the argument.
- **"ship into a new `v2/` directory"** (deploy-swap §3) — not supported by the packaging tool (§7); `v1` is hardcoded twice.
- Everything else the four readers asserted that I checked — the five nulled columns, the journal timestamp clobber, the bucket rewrite, the append-only history, the missing delete path, the `_encoder_or_none` branches, `writes_tone = True`, the 0.93 constant at `trial_audit.py:41`, the absence of any shape check on the ONNX graph — reproduces exactly as written.
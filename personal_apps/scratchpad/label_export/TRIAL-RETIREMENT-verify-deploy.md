## The premise the four readers worked from is not what production runs

The checked-out worktree is `dev_personal` at `b82aea0`; `main` is at `b1d1a7c` and **`main` is what deploys**. Commit `d745e8e` ("shorten the live encoder trial to a 1/2/3-day audit schedule") is on `main` and, per the ledger, was fast-forwarded onto the VPS and verified there on 2026-09-07. It changes exactly the constants at `personal_apps/features/radar/judge_trial.py:575-577`:

| | worktree (what the readers read) | production |
|---|---|---|
| `AUDIT_DRAW_DAY` | 3 | **1** |
| `AUDIT_LABEL_DAY` | 7 | **2** |
| `TRIAL_DEADLINE_DAYS` | 10 | **3** |

`first_judged_at = 2026-09-06 19:38:24.047717 UTC`, so production's milestones are 09-07 / **09-08** / 09-09, all at 19:38:24 UTC. Every "10-day deadline", "day 3", "day 7" statement in the stop-semantics and accept-path notes is wrong for the box this ships to, and one of those errors inverts a conclusion (R5 below).

---

## Deploy-correctness risks

**R1 — Swapping the artifact under the live trial row kills the entire ingest daemon, not just judging.**
`judge_config.py:179-184` raises `ConfigError` when `row.artifact_sha256` (frozen at `3bb32b5607a8a368d8ff72179b41de00c6a971223bbed21302e95dcfb90dccb5`) differs from `bundle_sha256()`. It is called from `run_radar_ingest.py:1275`, uncaught, *before* `build_fetchers()` and `scheduler.start()`. That takes down all 13 jobs at `run_radar_ingest.py:1300-1381`: ingest cycle, reddit, scoring, US quotes, DE market data, grouped closes, ECB FX, mappings, volatility, profiles, history, **the nightly prune**, and sentiment. The web app keeps serving a board that silently stops advancing. `update_coc.sh` restarts services, so this surfaces at deploy time and stays until someone reverts the files.

**R2 — There is no "retire without undoing". `stop` is a delete button with a 60-second fuse.**
Every non-passing exit writes `RECOVERING`: `request_stop` (`judge_trial.py:297`), `accept_audit(..., passed=False)` (`:659`), deadline `tick` (`:811`). `tick()` then calls `recover_trial(apply=True, limit=limit)` unconditionally on any `RECOVERING` row (`:798-802`), and `deploy/radar-encoder-trial.timer` runs it `OnCalendar=*-*-* *:*:00`. So `manage_encoder_trial stop` begins destroying up to 2,000 judged mentions per minute within one minute, with no confirmation and no operator gate in between. The CLI's own reassurance ("the decisions already made are still in the counts until recovery runs", `scripts/manage_encoder_trial.py:120-122`) is true for about 59 seconds.

**R3 — Masking the timer does not protect the data; the daemon drains too.**
`run_radar_ingest.py:1272` calls `judge_trial.tick(dt.datetime.utcnow())` with the default `limit=2000` at startup, before `initialize_judges`. So `systemctl restart radar_ingest` — i.e. every `./update_coc.sh` — drains 2,000 mentions synchronously whenever the row is `RECOVERING`. An operator who stops the watchdog to "freeze" the state and then deploys loses the data anyway.

**R4 — The 2026-09-09 19:38:24 UTC deadline destroys the judgments by itself, and downtime does not help.**
`deadline()` returns `None` only for `audit_evaluated_at is not None and audit_passed` (`judge_trial.py:596-597`). The timer is `Persistent=true`, and `tick` reads the original `first_judged_at`, so a host that is off through the deadline enforces it on the first firing after boot.

**R5 — In production, `accept` on the FAILING report is *not* blocked by timing, and it is irreversible.**
The accept-path reader concluded the day-1 draw falls outside the day-3..day-7 window. Under `main`'s 1/2 schedule the draw at day 1 **passes** `audit_encoder_trial.py:930-937`, and labels pass if `completed_at ≤ 2026-09-08 19:38:24 UTC`. `accept_audit` explicitly accepts a failing report as a result (`judge_trial.py:606-607`) and sets `status = RECOVERING` (`:659`). Running `accept` on the current report is therefore equivalent to running `stop`. Two further one-way doors: once *any* audit is recorded, a different report can never replace it (`judge_trial.py:638-642`), and no report is accepted after the deadline (`:647-651`).

**R6 — A passing audit keeps the encoder judging but forbids the new model.**
On a pass the row stays `running` with the *old* `artifact_sha256` frozen and the pin held (`judge_trial.py:653-655`, `:596-597`, `retention_floor` `:158-170`). Deploying deberta-base then re-enters R1. Under the current row, "keep judging" and "run the base model" are mutually exclusive — the plan needs to say which one the trial row ends up describing.

**R7 — Delete-and-re-arm produces a trial that can never be stopped, permanently disables judging, and never releases the retention pin.** This is the worst outcome and it is reachable by the most obvious sequence.
`arm_trial` refuses any existing row (`judge_trial.py:248-250`) and there is no delete path in the codebase, so re-arming means manual SQL. But `_recoverable` selects on **`model_id` + `prompt_version` only — never `artifact_sha256`** (`judge_trial.py:333-337`), and both are re-frozen from the same code constants (`:256-257`). A trial #2 armed today therefore owns every mention the old artifact judged, while its `retain_from` is `now - 48h` (`:261`). The moment `_plan` (newest-first, `:368-372`) reaches those older windows, `recover_trial` raises at `:463-470` / `:505-507`. Consequences, all simultaneous:
- `remaining` never reaches 0, so `_release_if_drained` never flips to `RECOVERED` (`:553-556`);
- `retention_floor()` keeps pinning (`:158-170`) → `retention._pinned` clamps every prune → `radar_mention_events` (normally 48h) and `radar_posts` (30d) grow without bound on the 8 GB box;
- `_encoder_or_none` sees `RECOVERING` and returns `None` (`judge_config.py:170-177`) → the encoder is off forever;
- the oneshot watchdog exits non-zero every minute (`Restart=no`), producing a failure log per minute and nothing else.

**R8 — Avoiding R7 via a new model id has four tripwires of its own.**
- `judge_backends.py:149` (`ENCODER_MODEL_ID`) and `scripts/package_encoder_artifact.py:56` (`MODEL_ID`, written into `active.json`) must change together, or `_validate` rejects the pointer (`judge_backends.py:260-263`) → `EncoderArtifactError` raised inside `construct_backend` at `judge_config.py:135`, uncaught → dead daemon.
- Any window where the code's id ≠ the live row's `model_id` hits `_may_judge` (`judge_trial.py:682-685`) → `ConfigError` (`judge_config.py:178`), **not** the benign "trial recovering, ingest continues" branch. Deploying the code before the row exists is a dead daemon; deploying the row before the code is a dead daemon. They must land in the same restart.
- `spend.py:58` hardcodes `'radar-encoder-v1': (0.0, 0.0)`; a v2 id makes `cost_micros` return `None` (`spend.py:69-73`) and the board reports the encoder's tokens as "unpriced" rather than free — the exact confusion that comment exists to prevent.
- `backend_label` matches the `radar-encoder` prefix (`judge_backends.py:458-460`) and `sentiment_model` is `String(40)` (`models.py:695`), so display and schema are fine.

**R9 — Do not touch `PROMPT_VERSION`** (`llm_sentiment.py:69`). `_may_judge` compares it to the frozen row (`judge_trial.py:686-690`) → startup `ConfigError`. (It would *not* trigger a re-judge wave — `pending()` filters on `sentiment_judged_at IS NULL`, not prompt version, `llm_sentiment.py:363-372` — so that particular fear is unfounded.)

**R10 — The copy itself is not atomic and there is no rollback.**
`bundle_sha256` hashes `model.onnx`, `tokenizer.json`, `config.json` from `os.path.dirname(self.model_path)` (`judge_backends.py:233-243`). `scp` into the live `v1/` writes in place: a restart during a ~740 MB transfer reads a truncated `model.onnx` and the daemon dies on a hash mismatch or an ORT load error. `active.json` is deliberately outside the digest (`:228-231`), which makes shipping into a fresh `v2/` and flipping the pointer last the only atomic swap available — and the only cheap rollback.

**R11 — Nothing validates the model, and the one unstated contract fails in the "silent" direction.**
`_validate` (`judge_backends.py:258-302`) checks file existence, `config['max_len'] == 256`, head names, and class-list order. It never opens the graph. There is no hidden-size, layer-count, vocab, or logit-width check, and `config['base']` is written by the packager and read by nothing at runtime — so a base model, a small model, or the wrong export all load identically as long as the hash matches the row.
The unchecked contract is that the ONNX **output names equal the five head names**: `by_head = {name: outputs[index]... for index, name in enumerate(self._outputs)}` then `self.heads[field][...]` (`judge_backends.py:376-381`). That lookup is *outside* the `try` at `:371-374`, so a re-export with different output names raises `KeyError`, not `SentimentUnavailable`; it is not latched, and it lands in `_scheduled_sentiment`'s broad `except Exception` (`run_radar_ingest.py:1144-1151`) — the pass dies every 10 minutes forever while the daemon reports healthy. Today this holds only because the packager passes `output_names=list(HEADS)`; export by any other route and you get the silent-stop failure.
Related: `config['max_len']` must still be exactly 256 (`judge_backends.py:279-282`). If the base model was retrained at 512, the packager refuses first (`package_encoder_artifact.py:120-123`) and the adapter refuses second — a loud failure, but it means "retrain at base size" is not a drop-in unless the window stayed at 256.

**R12 — The batch/thread constants are calibrations, they are not checked, and the measurement they came from described the wrong model.**
`ENCODER_BATCH_SIZE = 4`, `PASS_LIMIT = 400`, `INTRA_OP = 2` (`judge_backends.py:151-158`) rest on "7.0-7.5 rows/s, 1,081 MB flat at batch 4, 1,715 MB at batch 16". Runbook §1 records that this VPS benchmark actually measured `model-train8600`, not the shipped `train13000`. Twelve layers instead of six roughly doubles activation memory per item, and nothing bounds RSS. The failure mode is asymmetric: too large a batch is an OOM kill of `radar_ingest` (invisible in the judge path), too small is only slower. A slow pass does not error either — `max_instances=1, coalesce=True` (`run_radar_ingest.py:1379`) silently *skips* firings, so a 2x model shows up as a growing backlog, not a log line. Also note the box changed since §3 was written: MariaDB's buffer pool is now 2500M (commit `3681295`). Measure peak RSS with the base artifact before restarting the daemon — the one-liner already exists in `personal_apps/scratchpad/label_export/MIGRATION-VERIFICATION-2026-09-07.md` ("Encoder load" block).

**R13 — The runbook's copy step targets a decommissioned server.**
`docs/superpowers/plans/2026-09-06-radar-encoder-judge-runbook.md:202` — `scp -r artifacts/judge root@82.165.240.212:...`. Production has been 194.164.29.97 since the 2026-09-07 cutover; the new IP appears nowhere in that runbook. Following it copies 740 MB to a dead box while the live one keeps the old hash, and the symptom ("the deployed hash still doesn't match") reads like a packaging bug.

**R14 — Committing from this worktree silently reverts the deployed schedule.**
`features/radar/judge_trial.py:575-577` on disk holds 3/7/10. `dev_personal` is currently an ancestor of `main`, so nothing is broken yet — but any commit here that rewrites that file, or a merge resolved in the worktree's favour, re-lengthens the live trial to 2026-09-16 *and* makes the already-drawn day-1 sample permanently unacceptable (`audit_encoder_trial.py:930-937` would then demand a day-3..day-7 draw). Rebase onto `main` before editing anything under `features/radar/judge_*`.

**R15 — After a completed recovery the pin drops immediately, so the surgery window closes.**
`_release_if_drained` sets `RECOVERED` (`judge_trial.py:557`), `retention_floor()` returns `None` (`:158-170`), and `retention._pinned` lets the 48-hour journal horizon and 30-day post horizon resume at the next 04:30 prune. Any delete-and-re-arm decided *after* that point is unrecoverable for everything older than 48 hours. If surgery is going to happen, it has to happen while the row still pins.

**R16 — "Recovery" no longer undoes what the encoder wrote, so even the destructive path leaves corrupt state.**
`recover_trial` clears five columns (`judge_trial.py:511-515`) and leaves `sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment`, `sentiment_tone_model`. Since `b82aea0` the encoder writes exactly those (`judge_backends.py:210` `writes_tone = True`; `llm_sentiment.py:493-502`), and `board.py:362-374` reads `sentiment_attitude` first, the legacy projection second. Post-recovery the board still counts encoder tone on mentions that now claim to be unjudged — and those mentions are simultaneously restored to counting. Four places assert the opposite and are stale: `judge_trial.py:443-445`, `scripts/rollback_encoder_judge.py:22-23`, `trial_audit.py`'s module docstring, and runbook §8's "`attitude_written` MUST be 0 … stops the trial" check, which now fires on every row. If the drain is allowed to run, budget a follow-up `UPDATE ... SET sentiment_attitude=NULL, sentiment_expected_move=NULL, sentiment_confidence=NULL, llm_sentiment=NULL, sentiment_tone_model=NULL WHERE sentiment_model IS NULL AND sentiment_tone_model='radar-encoder-v1'`.

**R17 — `RADAR_JUDGE_TONE` is a trap for exactly this deploy.** `judge_config.py:89-97` raises `ConfigError` for any value but `'0'`, and `Settings.write_encoder_tone` is hardwired `False` (`:102`) and read by nothing (grep: no consumer). Someone deploying the retrained model and wanting its tone will set `RADAR_JUDGE_TONE=1`; that is a dead daemon, and the variable would not have done anything anyway.

**R18 — Two tempting bypasses that must be named and refused.** `artifact_sha256` is `nullable=False` (`models.py:1420`), so the reader's "if the hash is NULL the check is skipped" branch is unreachable through `arm_trial` (`judge_trial.py:229-231`) — but an empty string satisfies NOT NULL, and setting it by hand disables the only proof that the deployed files are the audited ones (`judge_config.py:179`). Likewise `RADAR_JUDGE_PRIMARY=anthropic:radar-encoder-v1` routes around the hash check (no `bundle_sha256` attribute, `:180`) while still demanding an armed trial and storing a hosted model's answers under the encoder's provenance — with no credits behind it.

---

## Ordering constraints that fall out of the above

1. Run `manage_encoder_trial status` first. If `audit` already reads `FAILED`, the row is `RECOVERING`, the drain has been running since that minute, and the question is no longer "how do we avoid destruction" but "how much is left" (`judge_trial.py:636-642` makes it unrecoverable-by-audit either way).
2. The only in-code way to keep the judgments *and* keep judging is a **passing** audit accepted before 2026-09-09 19:38:24 UTC. That requires editing `trial_audit.py:41`, re-running `evaluate` (accept recomputes and demands byte-identical reproduction, `audit_encoder_trial.py:917-925`), and re-writing `acknowledgments.json` against the new report hash (`:898-903`). The labels' `completed_at` must be ≤ 2026-09-08 19:38:24 UTC — check that stamp before planning anything else, because if it is already past, this route is closed and only manual DB work preserves the data.
3. That passing audit does not unlock the base model (R6). The new artifact needs its own trial row, which needs a manual delete plus either a new `ENCODER_MODEL_ID` (R8) or acceptance that the new trial is born un-recoverable (R7).
4. Whatever the sequence, hash the three files on the server with `EncoderBackend(...).bundle_sha256()` and compare against the packager's printed hash (`package_encoder_artifact.py:207`) *before* arming — the gate proves the files are the ones named, never that they are the model you meant (R11).
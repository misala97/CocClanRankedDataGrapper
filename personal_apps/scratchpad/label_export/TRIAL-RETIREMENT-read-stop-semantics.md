## 1. What `stop` does

`scripts/manage_encoder_trial.py:117-123` (`cmd_stop`) is a thin wrapper: it calls `judge_trial.request_stop(args.reason)` and prints. It touches **nothing but the trial row**.

`features/radar/judge_trial.py:280-301` (`request_stop`): under the `radar_encoder_trial_retention` advisory lock (`:291`), it errors if no row exists (`:293-294`), returns unchanged if already `RECOVERED` (`:295-296`), then sets exactly two columns and commits:

```
row.status = RECOVERING            # judge_trial.py:297
row.stop_reason = str(reason)      # judge_trial.py:298
db.session.commit()                # judge_trial.py:299
```

No write to `radar_mentions`, `radar_mention_events`, `radar_buckets`. The CLI says so itself: "This stops NEW judgments; the decisions already made are still in the counts until recovery runs." (`manage_encoder_trial.py:120-122`).

What `RECOVERING` *does* cause, immediately:
- `_may_judge` refuses (`judge_trial.py:691-692`), so `guard_encoder_trial` (`:699-714`) and `lock_for_write` (`:717-742`) raise. In `llm_sentiment.run_pass` that means a pass already in flight discards its answers and rolls back (`llm_sentiment.py:824-832`, `:846-856`).
- `judge_config._encoder_or_none` (`judge_config.py:166-177`) returns `None` on the next `initialize_judges`, so the primary judge is disabled rather than the daemon failing.

**`stop` does not itself undo anything, but it hands the job to an automatic drainer.** `tick()` (`judge_trial.py:782-815`) sees `status == RECOVERING` and calls `recover_trial(apply=True, limit=limit)` unconditionally (`:798-802`). `tick` runs in two places: at daemon startup (`run_radar_ingest.py:1272`) and — the important one — **every minute** via `deploy/radar-encoder-trial.timer` (`OnCalendar=*-*-* *:*:00`, `Persistent=true`) driving `deploy/radar-encoder-trial.service`, whose `ExecStart` is `... -m scripts.manage_encoder_trial tick --limit 2000`. So on the deployed layout, `stop --reason ...` starts an unattended destruction of up to 2000 judged mentions per minute until nothing is left. There is no confirmation step and no separate operator gate between `stop` and the data loss.

## 2. Exactly what `recover_trial(apply=True)` mutates

Per window (one transaction each, `judge_trial.py:485-528`), selected by the trial's **frozen** `model_id` + `prompt_version` (`_recoverable`, `:333-337`; re-checked under `FOR UPDATE` in `_members_now`, `:404-409`):

**a) `radar_mentions` — five columns nulled** (`judge_trial.py:511-515`):
```
mention.sentiment_relevance      = None
mention.sentiment_content_origin = None
mention.sentiment_model          = None
mention.sentiment_prompt_version = None
mention.sentiment_judged_at      = None
```
This hits **every** mention the encoder materialized, not only the removals — a `relevant`/`human_chatter` verdict is nulled the same as an `irrelevant` one.

**Answering your specific question: relevance and content_origin — yes. `sentiment_attitude` — NO.** The docstring at `:444-446` says "Tone and its provenance are NOT cleared. The trial never wrote them." **That premise is now false.** `judge_backends.py:210` sets `EncoderBackend.writes_tone = True` ("Tone PUBLISHES, changed 2026-09-07", `:190-210`), and `llm_sentiment.apply_judgments` under `write_tone` writes `sentiment_attitude`, `sentiment_expected_move`, `sentiment_confidence`, `llm_sentiment` (legacy projection) and `sentiment_tone_model = model` (`llm_sentiment.py:494-502`). `git log` confirms the ordering: `judge_backends.py`'s newest commit is `b82aea0 feat(radar): the encoder publishes tone`, while `judge_trial.py` has not been touched since `aa380f4`. Consequence after a recovery: the mention keeps `sentiment_attitude='...'`, `llm_sentiment='bullish'`, `sentiment_tone_model='radar-encoder-v1'` while `sentiment_model`/`judged_at` are NULL — an orphaned encoder tone with no owning judgment, and it still drives the board's bull/bear counts, which read `sentiment_attitude` first and `llm_sentiment` second (`board.py:358-373`). The regression test `tests/test_radar_judge_trial.py:626-645` (`test_tone_and_its_owner_are_never_cleared`) pins exactly this behaviour, but stages it with `sentiment_tone_model = 'claude-haiku-4-5'`, i.e. it tests the old world where the tone belonged to someone else.

**b) `radar_mention_events` (the journal) — via `journal.sync_chatter_eligibility(pairs)` with value `None`** (`judge_trial.py:516-519` → `journal.py:214-246`), keyed by `(post.source, post.external_id, mention.ticker)`:
```
row.counts_as_human_chatter = None            # journal.py:240 (only where it differed)
row.chatter_decided_at      = decided_at      # journal.py:244  — overwritten with the recovery time
```

**c) `radar_buckets` and `radar_bucket_sources` — YES, both are rewritten**, via `buckets.rebuild_windows([key], commit=False)` (`judge_trial.py:527`). Note the comment at `:522-526`: this deliberately bypasses `journal.rebuild_windows`, which would refuse anything past the 48-hour horizon. Inside `_rebuild_windows_locked` (`buckets.py:412-469`):
- `journal.mark_promoted(...)` resets `radar_mention_events.promoted` to `False` for every low/medium row in the window and re-marks the current mediums (`journal.py:170-205`);
- `RadarBucket` (creating the row if absent but children exist, `buckets.py:426-437`) gets all eight summary fields overwritten — `mention_count`, `high_confidence_count`, `low_count`, `distinct_authors`, `distinct_text_ratio`, `engagement_weighted_count`, `sentiment_mean`, `sentiment_stdev` (`_summarize`, `buckets.py:121-137`) — plus `source_config_version`;
- each `RadarBucketSource` child gets the same eight fields plus `source_config_version`, and either has `expected`, `variance`, `mention_z`, `baseline_days` **all set to NULL** (non-scoreable status or a generation mismatch, `buckets.py:451-456`) or has `mention_z` recomputed (`:457-460`).

**d) the trial row**: `_release_if_drained` (`:538-560`) sets `state.status = RECOVERED` (`:557`) only after a count under both the row lock and the retention lock finds `_recoverable(state).count() == 0`. That release also drops the retention pin — `retention_floor()` returns `None` once status leaves `PINNING` (`:158-170`), and `retention._pinned` (`retention.py:23-47`) then lets `prune_posts` (`:218-256`) and `prune_mention_events` (`:307-...`) resume the ordinary 30-day / 48-hour horizons.

## 3. Reversibility

**Recovery is irreversible from inside the application.** There is no "redo", no restore path, no archive of the pre-recovery mention or bucket values. Specifically:

- The five nulled mention columns are gone. Note the sharp edge: if the encoder's verdict had *overwritten* an earlier judge's materialized verdict, recovery does **not** restore the earlier one — it nulls to unjudged. That prior state exists nowhere on the mention.
- Bucket and bucket-source values are overwritten **in place**. `radar_buckets` is retained forever (`models.py:717`) and nothing versions it; the counts as they stood during the trial are destroyed. The rebuild is a *fresh recompute from the current journal*, not a restore of the pre-trial numbers.
- `chatter_decided_at` is clobbered with the recovery timestamp; the original decision time is lost.
- Once `RECOVERED`, the trial is terminal and un-restartable: `request_stop` no-ops (`:295-296`), `note_first_judgment` raises (`:776-778`), `_may_judge` refuses (`:691-692`), and `arm_trial` refuses to overwrite an existing row (`:248-250`). There is **no delete path for `RadarJudgeTrial` anywhere in the codebase** (grep over `features/`, `scripts/`, `models.py` yields only reads and the one construction) — so a recovered trial permanently blocks arming another without manual DB surgery.

**The encoder's judgment IS preserved, in `radar_sentiment_judgments`** (`models.py:1300-1360`), which is append-only and never written by recovery — `tests/test_radar_judge_trial.py:~610-622` asserts the row count is unchanged across `recover_trial(apply=True)`. Each row holds `stage`, `model`, `prompt_version`, `relevance`, `content_origin`, `attitude`, `expected_move`, `confidence`, tokens and `created_utc`. Three caveats:

1. Nothing reads it back to re-materialize. `latest_primary_history` (`llm_sentiment.py:571-592`) is used only for review routing (`:663`), never to restore a mention.
2. It is bounded: `mention_id` is `ON DELETE CASCADE` (`models.py:1334-1337`), mentions follow post retention, and `POST_RETENTION_DAYS = 30` (`config.py:603`). Once the pin is released by `RECOVERED`, the ordinary pruners resume, so the evidence starts aging out.
3. The `displayed_tone` / `displayed_tone_model` / `displayed_judged_by` diagnostic columns are written **only when `write_tone` is False** (`llm_sentiment.py:485`, `**({} if write_tone else _displayed_tone(mention))`). Since the encoder now writes tone, those are empty for current trial rows.

Even with the history table, a manual restore would have to redo the mention columns, the journal flags and the bucket rebuild in step — no tooling exists for that.

## 4. Valid statuses and transitions

Four, defined at `judge_trial.py:38-41` and enforced by a DB CHECK constraint (`models.py:1405-1407`: `status IN ('armed','running','recovering','recovered')`). `PINNING = (ARMED, RUNNING, RECOVERING)` (`:44`) — the three that hold the retention floor.

- **(no row) → `armed`**: `arm_trial` (`:251-272`), once only; a second arm raises (`:248-250`).
- **`armed` → `running`**: `note_first_judgment` (`:773-775`), only inside the transaction that materializes the first verdict; any other status raises (`:776-778`).
- **`armed`/`running` → `recovering`**: three writers — `request_stop` (`:297`, operator CLI or `rollback_encoder_judge.py:54`); `accept_audit(..., passed=False)`, which sets `status = RECOVERING` and a `stop_reason` of its own (`:656-660`); and `tick()` at the 10-day deadline, which calls `request_stop` then recovers (`:808-814`).
- **`recovering` → `recovered`**: only `_release_if_drained` (`:557`), and only when the under-lock count is zero.
- **`recovered` → anything**: none. Every writer short-circuits on it (`:295-296`, `:490-497`, `:550-552`, `:691-692`, `:776-778`).
- **`recovering` → `running`**: impossible in code; `recover_trial` raises "it was stopped when this recovery began and something restarted it" if it observes any other status mid-drain (`:498-501`).
- **Audit acceptance is orthogonal to status when it passes**: `accept_audit(passed=True)` writes only `audit_evaluated_at`, `audit_passed`, `audit_report_sha256` (`:653-655`) — the trial stays `running`.

## 5. Paths that end the trial WITHOUT undoing the judgments

Three, and one of them is the intended design:

**(a) A passing audit — the trial never ends at all, and nothing is undone.** `deadline(row)` returns `None` once `audit_evaluated_at is not None and audit_passed` (`:596-597`), so `tick()` hits `ends is None` and returns `{'action': 'none'}` forever (`:804-806`). The docstring is explicit (`:590-593`): "It keeps running suppressed, with its evidence still pinned; promoting it is a separate change." The trial stays `running`, judgments stay in the counts, and the retention pin stays on indefinitely — `retention_floor` deliberately keeps pinning for a passed trial (`:162-166`, echoed in `retention.py:32-36`). This is the only *good* ending, and it is not an ending in the status machine at all.

**(b) `recovering` → `recovered` with an empty drain.** If `_recoverable(state).count()` is already zero when `_release_if_drained` runs (`:553`), the trial flips to `RECOVERED` and releases the pin having undone nothing. Reachable when the trial was armed but never judged, or when every encoder-judged mention has since been superseded by an independent review (`_recoverable` excludes those by construction, `:318-331`) or has been pruned with its post.

**(c) Per-mention, not trial-wide: an independent review.** A Sonnet/Haiku review overwriting `sentiment_model` takes that mention permanently out of `_recoverable`'s filter (`:325-331`), so its encoder-era decision is neither in force nor ever recovered — it is simply replaced.

**And the near-miss worth flagging:** the encoder's **tone** survives every recovery path (§2a). So even a "complete" recovery ends with the encoder's `attitude` / `expected_move` / `confidence` / `llm_sentiment` still materialized and still counted by `board.py:358-373`, under `sentiment_tone_model = 'radar-encoder-v1'` with a NULL `sentiment_model` beside it. `recover_trial`'s own docstring (`:444-446`) and `scripts/rollback_encoder_judge.py:22-23` both still assert the opposite ("The trial did not write it").

One further operational trap in the same function: `recover_trial` raises outright if any **selected** window starts before `retain_from` (`:463-470`, re-checked per window at `:505-507`). Since `_plan` orders newest-first (`:371`), out-of-retention windows surface only on the last ticks — at which point every subsequent minute-timer firing raises, `remaining` never reaches zero, and the trial can never leave `RECOVERING` or release its pin. The write-side guard `refuse_outside_retention` (`:745-758`) is what is supposed to make that unreachable.
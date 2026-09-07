Findings — read-only, nothing changed. Files: `C:/Users/michi/Desktop/CodingStuff/personal_apps/features/radar/judge_config.py`, `.../judge_backends.py`, with the trace continuing into `.../judge_trial.py` and `C:/Users/michi/Desktop/CodingStuff/personal_apps/run_radar_ingest.py`.

## 1. The artifact-mismatch check: trigger and blast radius

It lives at the end of `_encoder_or_none`, `judge_config.py:179-184`:

```python
    if row.artifact_sha256 and getattr(backend, 'bundle_sha256', None) \
            and row.artifact_sha256 != backend.bundle_sha256():
        raise ConfigError(
            'the deployed artifact does not match the armed trial '
            '(%s armed, %s deployed); replacing a file is a different trial'
            % (row.artifact_sha256[:12], backend.bundle_sha256()[:12]))
```

Three conditions must all hold: the trial row carries a non-empty `artifact_sha256`; the constructed backend exposes a `bundle_sha256` attribute; and the two digests differ. If the armed row's hash is NULL/empty, or the backend has no `bundle_sha256` (an `AnthropicBackend` does not — `judge_backends.py:71-98`), the comparison is skipped entirely and the encoder is returned as-is. Note also that this check is only reached when `guard_encoder_trial` has already succeeded (`judge_config.py:168`), i.e. only for a trial in `armed`/`running`; for `recovering`/`recovered` the function returns `None` at `judge_config.py:177` before the hash is ever computed.

What the hash covers is `judge_backends.py:224-244`: SHA256 over `model.onnx`, `tokenizer.json`, `config.json` in `version_dir = os.path.dirname(self.model_path)`, in that fixed order. Since `model_path` is derived from the `active.json` pointer (`judge_backends.py:258-272`), repointing `active.json` at a different version directory changes which three files are hashed and therefore also trips the check — `active.json` itself is deliberately outside the digest.

**Effect on the daemon: the whole `radar_ingest` process dies at startup.** `initialize_judges` is called from `run_radar_ingest.main` at line 1275, inside `with app.app_context():` but with no `try` around it, and the module's own docstring says so explicitly (`judge_config.py:10-14`): resolution and construction happen "OUTSIDE the exception handler that keeps a failing enrichment from killing the daemon." The call site repeats it (`run_radar_ingest.py:1258-1264`): "Uncaught on purpose." A `ConfigError` there propagates out of `main()` and the process exits before `build_fetchers()` (line 1277), before `scheduler.add_job(...)`, before `scheduler.start()` — so no ingest cycle, no reddit pull, no sentiment pass, nothing. This is the opposite of the per-pass failure mode: a `TrialError` raised later, from inside `llm_sentiment.run_pass`, is swallowed by `_scheduled_sentiment`'s broad handler at `run_radar_ingest.py:1144-1152` (`logger.exception('radar sentiment pass failed'); return`) and ingest continues. Only the *startup* misconfiguration is fatal, and it is fatal to the entire service.

Same fatality applies one line earlier, at `judge_config.py:135-136`: `construct_backend` runs `EncoderBackend._validate()` in the constructor (`judge_backends.py:217`), which raises `EncoderArtifactError` for a missing `active.json`, a wrong `id`, a wrong `max_len`, or heads whose class lists are reordered (`judge_backends.py:258-302`). That exception is not caught by `_encoder_or_none` — it is raised before it — and likewise kills the daemon.

## 2. `_encoder_or_none()`

`judge_config.py:166-185`. It is the gate that turns "the encoder is configured" into "the encoder may actually run", applied at `judge_config.py:144-145` only when `primary.id == judge_backends.ENCODER_MODEL_ID`. The comment above that line (`judge_config.py:138-143`) records that the condition used to be `writes_tone is False and id == ENCODER`, which silently stopped applying when tone was turned on 2026-09-07; it is now keyed on identity alone.

It calls `judge_trial.guard_encoder_trial(now)` (`judge_trial.py:699-712`), which reads the row and delegates to `_may_judge`. Three outcomes:

- **Guard passes** (status `armed` or `running`, correct `model_id` and `prompt_version`, deadline not reached) → falls through to the artifact check and returns the backend (`judge_config.py:185`).
- **Guard raises `TrialError` and the current status is `RECOVERING` or `RECOVERED`** → returns `None` with a warning (`judge_config.py:170-177`): `'radar judge: the encoder is configured but its trial is %s (%s); judging is disabled and ingestion continues'`.
- **Guard raises `TrialError` for any other reason** → `raise ConfigError('the encoder cannot start: %s' % why)` (`judge_config.py:178`), which kills the daemon as in §1. Those other reasons are enumerated in `judge_trial._may_judge` (`judge_trial.py:675-696`): no trial row at all, `row.model_id != ENCODER_MODEL_ID`, `row.prompt_version != llm_sentiment.PROMPT_VERSION`, and `now >= deadline(row)`.

So: `None` for a trial that has ended normally; the backend for a live armed trial; a dead daemon for everything else.

## 3. `RECOVERED` / `RECOVERING`: can the encoder still judge?

No — and it cannot even be constructed into the active slot.

Trace: `judge_trial._may_judge` at `judge_trial.py:691-692` — `if row.status in (RECOVERING, RECOVERED): raise TrialError('the trial is %s and must not judge' % row.status)`. `guard_encoder_trial` re-raises. `_encoder_or_none` catches, re-reads the row via `judge_trial.current()`, sees the status in `(RECOVERING, RECOVERED)`, logs the warning and returns `None` (`judge_config.py:170-177`). That `None` becomes `_active['primary']` (`judge_config.py:157`) and the startup log prints `primary=none` (`judge_config.py:159-162`). `llm_sentiment.default_primary_backend()` returns it (`llm_sentiment.py:718-727`), and `run_pass` bails immediately: `backend = backend or default_primary_backend(); if backend is None: return 0`. Ingest keeps running; judging is simply off.

Two supporting details. First, startup runs `judge_trial.tick(dt.datetime.utcnow())` *before* `initialize_judges` (`run_radar_ingest.py:1266-1275`), and `tick` converts an expired `running` trial into `recovering` (`judge_trial.py:804-815`, via `request_stop` + `recover_trial`). That ordering is why a trial that blew its 10-day deadline while the host was down degrades to "no judging, ingest continues" rather than to the `ConfigError` the deadline branch of `_may_judge` (`judge_trial.py:694-696`) would otherwise produce — the comment at `run_radar_ingest.py:1270-1271` says exactly that.

Second, the same guard runs again per pass and per batch even if it were somehow bypassed at startup: `llm_sentiment.py:791` (pre-flight), `:824` (`before_batch=(lambda: trial.guard_encoder_trial(clock()))`), and `:848` `trial.lock_for_write(clock)` which re-validates the row under `SELECT ... FOR UPDATE`. A stop committed by another process mid-pass (`judge_trial.request_stop`, `:280-299`) is therefore caught at the write boundary and the verdicts are discarded.

## 4. Can the encoder judge without an armed trial?

Not through any configuration. The gate is keyed on the backend's id (`judge_config.py:144`), and `EncoderBackend.__init__` hardcodes `self.id = ENCODER_MODEL_ID` (`judge_backends.py:215`) — there is no constructor argument or environment variable that changes it. `construct_backend` accepts only two forms (`judge_backends.py:396-414`): `'encoder'` → `EncoderBackend`, `'anthropic:<model>'` → `AnthropicBackend`; anything else is a `ValueError`. So `RADAR_JUDGE_PRIMARY=encoder` always produces the id that triggers `_encoder_or_none`, and the second, independent gate in `llm_sentiment._trial_module_for` (`llm_sentiment.py:741-752`) tests the same id, so even a caller that passes `backend=` into `run_pass` explicitly still hits `guard_encoder_trial`.

The review slot is closed too: `RADAR_JUDGE_REVIEW=encoder` is not routed through `_encoder_or_none` at all (`judge_config.py:147-155`), but it fails the very next check because `EncoderBackend.supports_review = False` (`judge_backends.py:189`) → `ConfigError('... cannot serve the review role ...')`.

What *would* have to change: either (a) delete or weaken the `primary.id == judge_backends.ENCODER_MODEL_ID` test at `judge_config.py:144` (which is precisely the failure the comment at `:138-143` documents having already happened once, via a condition that included `writes_tone`), or (b) remove the `RECOVERING`/`RECOVERED`/no-row branches from `judge_trial._may_judge`, or (c) call `EncoderBackend.judge_batch` directly, outside `run_pass`. Path (c) exists today in offline tooling — `scripts/build_supplemental_sets.py:112` constructs `EncoderBackend(artifact_dir)` and calls `judge_batch` at `:126`, and `scripts/audit_encoder_trial.py:326` constructs a backend — but neither writes live verdicts; the audit script says so at its `:28` and `:304` ("never through `apply_judgments`"). So no *stored* judgment escapes the trial.

One edge worth naming: `RADAR_JUDGE_PRIMARY=anthropic:radar-encoder-v1` builds an `AnthropicBackend` whose `id` collides with `ENCODER_MODEL_ID`. That routes a hosted model *into* the encoder's trial gate — it would require an armed trial and would be stored under the encoder's provenance, while skipping the artifact check (no `bundle_sha256` attribute, `judge_config.py:180`). It adds constraints rather than removing them, but it is the one way to get encoder-labelled rows out of a non-encoder judge.

## 5. `RADAR_JUDGE_PRIMARY`

It names the primary judge's backend spec. `resolve_settings` reads it through `_spec` (`judge_config.py:48-52`), which strips whitespace and maps both empty and the literal `'none'` (`DISABLED`, `:25`) to `None`; the result lands in `Settings.primary` (`judge_config.py:99`). `initialize_judges` only constructs a backend `if settings.primary:` (`:134`), so unset / empty / `none` means `_active['primary'] is None`, `active_primary()` returns `None`, and `run_pass` returns 0 — nothing is judged, and the review tier is unaffected (it has its own `RADAR_JUDGE_REVIEW` + `RADAR_REVIEW_TIER` pair, `:100-101`, `:55-82`). That is the documented default (`judge_config.py:6-8`: "A deploy that forgets a variable judges nothing").

Set to something other than `encoder`:

- `anthropic:<model>` (e.g. `anthropic:claude-haiku-4-5`) → an `AnthropicBackend` (`judge_backends.py:409-413`). Its id is the model string, so `judge_config.py:144` is false, `_encoder_or_none` never runs, and `llm_sentiment._trial_module_for` returns `None` (`llm_sentiment.py:749-750`) — no trial, no deadline, no evidence pin, exactly as its docstring says. `writes_tone = True` (`judge_backends.py:82`) so its tone publishes, and `supports_review = True`.
- `anthropic:` with an empty model → `ValueError('anthropic backend spec names no model: ...')` (`judge_backends.py:412`).
- Anything unrecognised (`openai:gpt-5`, a bare model name, a typo like `encoders`) → `ValueError('unknown judge backend spec: %r')` (`judge_backends.py:414`). Deliberately an error rather than a fallback, per the docstring at `:398-402`. Note this is a `ValueError`, not `ConfigError` — but it is raised from the same uncaught startup call, so the practical outcome is identical to §1: the `radar_ingest` daemon fails to start.

Adjacent trap in the same resolver: `RADAR_JUDGE_TONE` must be exactly `'0'` in this build, or `resolve_settings` raises `ConfigError` before any backend is constructed (`judge_config.py:89-97`) — another whole-daemon startup failure, and `Settings.write_encoder_tone` is hardwired `False` (`:102`) regardless.
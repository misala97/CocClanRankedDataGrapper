## 1. What files make up the artifact, and how `bundle_sha256` is computed

The artifact is a two-level layout under an artifact root: a pointer file plus a version directory holding exactly three files.

Root default is `personal_apps/artifacts/judge/` — `judge_backends.py:165-166`:

```python
DEFAULT_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                                    'artifacts', 'judge')
```

overridable by `RADAR_JUDGE_ARTIFACT_DIR` (`judge_config.py:103-104`), which flows through `construct_backend(spec, artifact_dir=...)` (`judge_backends.py:396-408`) into `EncoderBackend.__init__` (`:214-216`).

The three hashed files are named literally in `bundle_sha256` (`judge_backends.py:224-244`):

```python
version_dir = os.path.dirname(self.model_path)
for name in ('model.onnx', 'tokenizer.json', 'config.json'):
    path = os.path.join(version_dir, name)
    file_digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            file_digest.update(chunk)
    line = '%s=%s\n' % (name, file_digest.hexdigest())
    digest.update(line.encode('utf-8'))
return digest.hexdigest()
```

So it is a hash-of-hashes: each file is SHA256'd in 1 MiB chunks, rendered as the UTF-8 line `"<name>=<lowercase hex>\n"`, and those three lines — in that fixed order, never sorted, never directory-listed — are fed into an outer SHA256. `active.json` is deliberately **not** in the bundle (the pointer can change without changing the model's identity), and `config.json` **is**, which is why the hash cannot be stored inside it (docstring, `:228-231`).

The rule is duplicated on purpose in the packaging script, `scripts/package_encoder_artifact.py:67-78`, which runs in the training venv and prints the hash to arm the trial with (`:207-210`). The spec pins the same wording at `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md:139-146`.

Note the local `personal_apps/artifacts/judge/` contains only `.gitkeep` — the artifact is not in git (566 MB, ships by scp; spec `:709-712`). The only complete artifact in the repo is the 12 KB test fixture at `personal_apps/tests/fixtures/radar_encoder/`.

## 2. `active.json`, and where `ENCODER_MODEL_ID` comes from

Content is two keys, written at `package_encoder_artifact.py:197-199` and mirrored by the fixture `tests/fixtures/radar_encoder/active.json`:

```json
{"path": "v1/", "id": "radar-encoder-v1"}
```

Both are consumed at the top of `_validate` (`judge_backends.py:258-268`):

```python
pointer = self._read_json(os.path.join(self.artifact_dir, 'active.json'),
                          'active.json pointer')
if pointer.get('id') != ENCODER_MODEL_ID:
    raise EncoderArtifactError(
        'active.json names id %r, this build serves %r'
        % (pointer.get('id'), ENCODER_MODEL_ID))
path = pointer.get('path')
if not path:
    raise EncoderArtifactError('active.json names no path')
version_dir = os.path.join(self.artifact_dir, path)
```

`path` is the only functional field — it selects the version directory. `id` is purely an **assertion**, checked and then discarded. No other key is read.

`ENCODER_MODEL_ID` is a **module constant**, `judge_backends.py:149`:

```python
ENCODER_MODEL_ID = 'radar-encoder-v1'
```

It comes from neither the pointer nor `config.json`. The backend's own identity is set from the constant, not from the file — `judge_backends.py:215`: `self.id = ENCODER_MODEL_ID`. The pointer's `id` can therefore never *become* the backend's id; it can only fail to match it. The value is also constrained to ≤ 40 chars because it is written into `RadarMention.sentiment_model = db.Column(db.String(40))` (`models.py:695`), asserted at `tests/test_radar_judge_backends.py:565`.

From `config.json`, the loader reads only `max_len` and `heads` (`:279-302`); `base` and `manifest` are written by the packager (`package_encoder_artifact.py:195-196`) but grepping `features/` and `scripts/` finds no runtime reader for either.

## 3. Deploying deberta-v3-base

**Files to replace** — all three, inside the version directory: `model.onnx`, `tokenizer.json`, `config.json`. That is forced twice over: `_validate` requires all three present (`:270-277`) and `bundle_sha256` hashes all three, so any partial swap produces a hash that fails the startup gate.

**What `active.json` must say.** Only `path` may change. If you ship into a new `v2/` directory it becomes `{"path": "v2/", "id": "radar-encoder-v1"}`; if you overwrite `v1/` in place, `active.json` need not change at all. The `id` field must equal `ENCODER_MODEL_ID` verbatim (`:261`), whatever that constant is.

**Must the id go to v2?** Mechanically, no — nothing in the loader ties the id to the architecture, so a base-sized model loads and judges under `radar-encoder-v1` without complaint. But changing it is a code edit at `judge_backends.py:149`, and it cascades further than it looks:

- `judge_trial.guard_encoder_trial` (`:682-685`) rejects the armed row: *"the code serves %r but the armed trial is %r; a different model is a different trial"* — `model_id` was frozen at arm time from the same constant (`judge_trial.py:256`).
- `judge_config._encoder_or_none` (`:166-185`) turns that `TrialError` into a startup `ConfigError`.
- `llm_sentiment._trial_module_for` (`:749`) decides "is this backend under a trial" by id equality.
- `backend_label` (`:459-460`) matches on the `radar-encoder` prefix, so a v2 id still renders "Encoder".
- Already-stored rows keep the old id in `sentiment_model`, and `stored_row_carries_tone` (`:431-441`) exists precisely because reusing one id across two behaviors made the id unable to distinguish them — the same trap a base model under the v1 id would re-enter.

**The gate you actually hit first, regardless of the id.** `judge_config._encoder_or_none:179-185`:

```python
if row.artifact_sha256 and getattr(backend, 'bundle_sha256', None) \
        and row.artifact_sha256 != backend.bundle_sha256():
    raise ConfigError(
        'the deployed artifact does not match the armed trial '
        '(%s armed, %s deployed); replacing a file is a different trial')
```

A new `model.onnx` changes the bundle hash, so the daemon refuses to start until a trial is armed for the new hash — and `arm_trial` (`judge_trial.py:213`, `:247-250`) refuses to overwrite the singleton row (`TRIAL_ID = 1`, `:36`): *"a trial record already exists; this build runs one trial and will not overwrite it"*. So a base-model deploy requires resolving the current trial and re-arming with a new hash, baseline report, removal rate, seed and supplemental sets via `scripts/manage_encoder_trial.py:103`.

Also on the packaging side: `--base` defaults to `microsoft/deberta-v3-small` (`package_encoder_artifact.py:97`) and would need `microsoft/deberta-v3-base`; the model class is imported from the training script rather than copied (`:114-115`), and `MultiHead` derives its head width from `self.encoder.config.hidden_size` (`scratchpad/label_export/train_encoder.py:202-205`), so the architecture swap itself is clean.

## 4. Shape validation — there is none

Construction-time validation is **metadata only** (`judge_backends.py:258-302`): file existence, `config['max_len'] == ENCODER_MAX_LEN` (256), the head *names* as a set, and each head's class list compared as tuples so order counts (`:297-301`). The ONNX graph is never opened during `_validate`.

At load (`:318-347`) the graph's interface is *recorded*, never checked:

```python
self._inputs = {value.name for value in session.get_inputs()}
self._outputs = [value.name for value in session.get_outputs()]
```

`self._inputs` is used only to decide whether to send segment ids (`:368`). `self._outputs` is used at `:376-377`:

```python
by_head = {name: outputs[index].argmax(-1)
           for index, name in enumerate(self._outputs)}
```

and then keyed by field name at `:381`. So the one unstated contract is that the graph's **output names equal the five head names**. Nothing asserts it. A re-export that named outputs `logits_0..4` would raise `KeyError` at `:381` — outside the `try` that wraps inference (`:371-374` covers only `session.run`), so it escapes `judge_batch` as a `KeyError`, is not caught by `except SentimentUnavailable` in the batch loop (`llm_sentiment.py:310-312`), and lands in `_scheduled_sentiment`'s broad handler (`run_radar_ingest.py:1145-1151`) — killing the whole pass every ten minutes instead of being latched and reported once, which is what the module's own failure design intends. Similarly, nothing compares a head's logit width to `len(heads[field])`, so a class-count mismatch either `IndexError`s at `:381` or silently mislabels.

**Dropping a base-sized model in place of a small one: nothing checks it, and nothing can.** Same tokenizer family, same three int64 inputs, same five output names of the same widths — hidden size and layer count are internal to the graph and are never inspected. There is no hidden-size check, no layer-count check, no vocab-size check, and no check that the tokenizer's vocab matches the model's embedding table. The two nearest things are both non-blocking:

- `package_encoder_artifact.py:203-205` warns only when the export is *too small* (`if size < 400`) and hard-codes the small model's `~566 MB` in its message — an fp32 base export (~184M params ≈ 736 MB) sails past it while the printed advice becomes wrong.
- `config['base']` records the backbone, and no runtime code reads it.

The bundle hash is the real guard, and it is a different question: it detects *that* the files changed, never *what* changed.

## 5. `ENCODER_BATCH_SIZE` / `ENCODER_PASS_LIMIT`

Defined at `judge_backends.py:155-156` and exposed as the protocol's per-backend economics at `:211-212` (`batch_size = ENCODER_BATCH_SIZE`, `pass_limit = ENCODER_PASS_LIMIT`), with the measurement recorded in the comment at `:151-154`: 7.0–7.5 rows/s on 2 vCPU at both 2 and 4 threads (memory-bandwidth bound), resident flat at 1,081 MB for batch 1 and batch 4, jumping to 1,715 MB at batch 16 — "which is the whole reason the batch is 4."

- **`batch_size = 4`** is items per `judge_batch` call: `llm_sentiment.py:306-307` slices `items[start:start + backend.batch_size]`. It is a peak-RSS knob, not a throughput knob.
- **`pass_limit = 400`** is items one scheduled pass takes: `llm_sentiment.py:785` (`limit = backend.pass_limit if limit is None else limit`), and the review pass draws a `backend.pass_limit * 5` candidate pool then takes `min(allowed, backend.pass_limit)` (`:958`, `:967`). The job fires every 10 minutes with `max_instances=1, coalesce=True` (`run_radar_ingest.py:1378-1381`), so 400 rows at 7.0–7.5 rows/s is ~53–57 s — about 9% of the window.

**For a 2x model:** neither is required to change for the code to run — both are calibrations, and neither is validated against the artifact (unlike `ENCODER_MAX_LEN`, which *is* checked at `:279-282` and so cannot drift silently). But both were derived from measurements a base model invalidates:

- `PASS_LIMIT` probably survives. Halving throughput to ~3.5 rows/s puts 400 rows at ~115 s, still comfortably inside the 10-minute interval with `coalesce=True` absorbing an overrun.
- `BATCH_SIZE` is the one to re-measure. Weights grow only ~1.3x (142M → 184M params fp32, 566 MB → ~736 MB, since both share the 128k×768 embedding table), but the 1,081 → 1,715 MB batch-16 spike was *activations*, which scale with layer count — 6 layers to 12. The flat-RSS-at-batch-4 result cannot be assumed to carry over on an 8 GB box also running MariaDB with a 2500M buffer pool.
- `ENCODER_INTRA_OP_THREADS = 2` / `ENCODER_INTER_OP_THREADS = 1` (`:157-158`) rest on the same "2 threads is as fast as 4" measurement and deserve the same re-measurement.

All four are module constants read at class-definition time, so tuning any of them is a code edit and redeploy, not an environment variable.
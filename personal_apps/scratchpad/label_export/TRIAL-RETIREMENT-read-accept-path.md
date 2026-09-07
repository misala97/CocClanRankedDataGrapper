**1. What `accept` requires before it records anything**

`cmd_accept` (`C:/Users/michi/Desktop/CodingStuff/personal_apps/scripts/audit_encoder_trial.py:864`) is a gauntlet of preconditions, in this order:

- *Schema*: the report must be a dict whose `schema` equals `radar-encoder-trial-audit-3` — `audit_encoder_trial.py:877-880` (`SCHEMA` at :59).
- *Named inputs*: `inputs` must contain all five of `labels`, `encoder`, `haiku`, `sample`, `frame` (`:882-884`).
- *Inputs still on disk and unchanged*: every input entry's `path` must exist and its `sha256` must still match (`:885-892`) — this covers the optional `supplemental_audit`/`supplemental_natural` entries too, since it loops over `inputs.items()`.
- *Report self-declares complete*: `:893-896`.
- *Acknowledgments file*: exists, `report_sha256` equals the actual sha256 of the report file (`:898-903`), lists every name in `REQUIRED_INSPECTIONS` (`:904-908`), and has a non-blank `by` (`:909-910`).
- *Full re-assembly from the inputs*, via `_assemble` (`:659`, called at `:913-916`). That re-runs, against the **live DB**, all of these:
  - a trial row exists at all — `_current_trial` raises `no trial is armed` (`:144-149`);
  - `sha256_of(frame_path) == sample['frame_sha256']` (`:667-668`);
  - the frame's and sample's `trial` identity (artifact sha, prompt version, model id) equal the armed row's (`:672-676`);
  - the sample's `sample_size` and `seed` equal the armed `recipe` (`:677-683`);
  - the draw reproduces: `random.Random(sample['seed']).sample(frame['mention_ids'], sample['sample_size'])` must equal `sample['mention_ids']` (`:684-688`);
  - labels are *exactly* the sample — a labelled row outside it, or a duplicate, is refused outright (`:531-536`);
  - prediction provenance for both backends: same `sample_sha256`, same `prompt_version`, encoder from the armed `model_id` and armed `artifact_sha256`, incumbent from a `claude-*` backend (`_check_provenance` `:560-584`, called `:695-699`);
  - neither prediction file answers ids outside the sample (`:700-705`).
- *Verdict reproduces*: the whole canonicalised report (everything but `evaluated_at`) recomputed from those inputs must be byte-identical, and the freshly assembled bundle must itself be complete (`:917-925`).
- *Timing*: the trial must have a `first_judged_at` (`:927-929`); `drawn_at` must fall between day 3 and day 7 of it (`:930-937`); the labels must carry a `completed_at` (`:938-940`) no later than day 7 (`:941-943`). Days come from `judge_trial.AUDIT_DRAW_DAY = 3` / `AUDIT_LABEL_DAY = 7` (`features/radar/judge_trial.py:575-576`).
- Then the persistence primitive adds its own checks (`judge_trial.accept_audit`, `judge_trial.py:601`): 64-char report hash (`:620`), report is a dict with a schema (`:622`), `complete is True` (`:625`), the passed flag matches the report's own (`:627`), a trial row exists (`:631`), it has judged something (`:633`), idempotent no-op for the identical report (`:636`), refusal to overwrite a *different* recorded audit (`:638`), artifact and prompt version match the row (`:643-646`), and the trial has not passed its 10-day deadline (`:647-651`).

**2. Does it refuse a report whose `passed` is false? No.**

A failing report is a *result*, not an error. `cmd_accept` passes the recomputed flag straight through — `audit_encoder_trial.py:946`: `judge_trial.accept_audit(report, report_sha, now, passed=fresh['passed'])` — and then prints `'PASSED' if fresh['passed'] else 'FAILED'` (`:947-952`), adding "The trial is now recovering. Run scripts/rollback_encoder_judge.py --apply to drain it." The only `passed`-related check is a *consistency* check, not a gate — `judge_trial.py:627-628`:

```python
if bool(report.get('passed')) != bool(passed):
    raise TrialError('the recorded result must be the report\'s own')
```

i.e. the file's flag must agree with the recomputed verdict. `accept_audit`'s docstring says it plainly (`judge_trial.py:606-607`): "A valid FAILING report is accepted and requests recovery -- failing is a result, not an error."

**3. What it writes to the trial row**

Only `accept` writes trial state, and only through `judge_trial.accept_audit` (`judge_trial.py:653-661`):

```python
row.audit_evaluated_at = now
row.audit_passed = bool(passed)
row.audit_report_sha256 = report_sha256
if not passed:
    row.status = RECOVERING
    row.stop_reason = 'audit failed (report %s)' % report_sha256[:12]
```

So: three audit columns always (`models.py:1430-1432`), and on failure additionally `status = 'recovering'` (`judge_trial.py:40`) plus a `stop_reason`. **On a pass it sets no status at all** — the row stays `running`; what a pass changes is that `deadline()` starts returning `None` (`judge_trial.py:230-231`: `if row.audit_evaluated_at is not None and row.audit_passed: return None`), so the trial stops expiring. Promotion is explicitly not part of this ("It keeps running suppressed, with its evidence still pinned; promoting it is a separate change", `judge_trial.py:227-228`). The whole write happens under `advisory_lock(RETENTION_LOCK)` with a single `db.session.commit()`.

**4. The acknowledgments file**

Passed as `--acknowledgments FILE`, documented as `{report_sha256, inspected: [...], by, at}` (`audit_encoder_trial.py:1001-1002`; the conventional filename `acknowledgments.json` is at `:64`). It is JSON and must contain:

- `report_sha256` — the sha256 of *this exact report file* (`:900-903`);
- `inspected` — a list containing both names in `REQUIRED_INSPECTIONS = ('reversal_disagreements', 'truncated_disagreements')` (`:68`, checked `:904-908`), which the comment at `:65-67` ties to spec 7.2c: a human must have looked at the reversal disagreements and the truncated-post disagreements the supplemental sets list;
- `by` — a non-blank name; "the acknowledgments name nobody" otherwise (`:909-910`). It is echoed in the final line (`:949`).

`at` is documented in the help string but never validated. Extra entries in `inspected` are harmless — the check is subset-of-inspected, not equality.

**5. Does it refuse an incomplete report? Yes, twice over.**

First against the report's own flag, `audit_encoder_trial.py:893-896`:

```python
if report.get('complete') is not True:
    raise AuditError('the report is incomplete: %s'
                     % '; '.join(report.get('incomplete_reasons')
                                 or ['no completeness recorded']))
```

That alone stops the current report. And it cannot be worked around by hand-editing `complete: true`, because the second check recomputes completeness from the inputs and also requires the *whole* canonical report to reproduce — `:922-925`:

```python
fresh = _report_from(assembled, now=None)
if _canonical(fresh) != _canonical(report) or assembled['incomplete']:
    raise AuditError('the report does not reproduce from its inputs; it '
                     'is not accepted')
```

A third refusal sits in the persistence primitive, `judge_trial.py:625-626`: `if report.get('complete') is not True: raise TrialError('an incomplete report cannot be recorded')`.

Both of your current reasons feed exactly this path: a missing `labelled_at` becomes a problem string in `_labels` (`:539-541`), and missing supplemental sets become reasons in `_supplemental` (`:616-617`); both land in `assembled['incomplete']` (`:711`) and hence in `report['complete'] / report['incomplete_reasons']` (`:751-752`). Note the ordering consequence: with `complete: false` the run dies at `:893` before the acknowledgments are even read, so an acknowledgments file cannot be "pre-approved" past it.

**6. Where 0.93 comes from**

It is a **module-level constant in code**, not trial state and not config: `C:/Users/michi/Desktop/CodingStuff/personal_apps/features/radar/trial_audit.py:41`

```python
REMOVAL_PRECISION_FLOOR = 0.93
```

Used at `trial_audit.py:240` (written into the criterion as `'threshold'`), `:243` (`removal_passed = coverage_ok and encoder_removal['lower'] >= REMOVAL_PRECISION_FLOOR`) and `:254` (the human-readable rule string). There is no `os.environ`/`getenv` read anywhere in that module — it is documented as pure ("no database, no model, no files", `trial_audit.py:4-6`). The report's `criteria[…]['threshold']` field is therefore a *copy* of the constant at evaluate time, not a source of truth.

**Could a new trial be armed with a different threshold without editing code? No.** `arm_trial` freezes only `seed`, `baseline_report`, `baseline_removal_rate`, `sample_size`, `removal_decisions_wanted` and `supplemental` into `row.recipe` (`judge_trial.py:260-268`), and the arming CLI exposes only `--artifact-sha256`, `--baseline-report`, `--baseline-removal-rate`, `--seed`, `--supplemental-audit-keys`, `--supplemental-natural-keys` (`C:/Users/michi/Desktop/CodingStuff/personal_apps/scripts/manage_encoder_trial.py:149-162`). Nothing in the row, the recipe (`models.py:1434-1437`) or the CLI carries a precision floor. Changing 0.93 requires editing `trial_audit.py:41` — which is deliberate, per the sibling comment on `Z` at `:32-34`: "this number decides whether a trial passes, and it should be readable in the diff that changes it." A related consequence: because `accept` recomputes the report with the *current* code, changing the constant between `evaluate` and `accept` makes the report fail to reproduce at `audit_encoder_trial.py:923` rather than silently re-grading it.
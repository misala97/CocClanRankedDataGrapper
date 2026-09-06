# Review brief 5 for Codex — the four round-4 findings

You reviewed `128c9cc` (brief 4): three P2s and a P3, everything else
closed, natural set to stay hard-required. This brief asks the same
question as the last one:

**Do the fixes close the four findings, and is the branch safe to merge?**

Same branch, `aa380f4` on top of `128c9cc`, plus the docs commit. Each
finding was verified against the code first; all four held. Tests first,
mutations run and restored — the ledger's "Review round 4 record" has the
table.

## 1. Empty supplemental files (P2) — frozen membership

`arm_trial` now takes `supplemental` and freezes it into the recipe:
`{'audit': {'keys': [...], 'halves': {key: half}}, 'natural': {'keys':
[...]}}`, keys normalised to strings and sorted; refused when a set is
empty, a key repeats, an audit key has no half, or the audit set has fewer
than two halves (`judge_trial.frozen_supplemental`). The CLI takes
`--supplemental-audit-keys` and `--supplemental-natural-keys` (JSON
lists; the runbook §7 has the recipe from `audit-200.jsonl` and
`test-natural.json`).

`evaluate` checks each supplied file against the frozen membership: every
frozen key present, each once, no extras, and for the audit set each row
in its frozen half. Any of those makes the report incomplete, which
`accept` refuses. Two empty files now give four `missing` reasons and
cannot be accepted (`test_an_empty_supplemental_file_is_not_evidence`,
`test_supplemental_membership_must_match_what_was_frozen` × 4).

**Judgement call**: membership is frozen at arming because that is where
the spec fixes everything the evaluation may not choose for itself. It
makes the two membership files preflight inputs, which the runbook's §0
table now lists.

## 2. Acceptance reproduces flags only (P2) — the whole report

`_report_from(assembled, now)` builds the report for both `evaluate` and
`accept`; `accept` compares `_canonical(fresh) == _canonical(report)` —
a JSON-normalised copy with only `evaluated_at` removed. Your two edits
(numerator/denominator to 99999, natural-set rows to 900) are the
parametrised `test_accept_refuses_a_report_whose_content_was_edited`, each
with an acknowledgment of the edited report's hash; both refused.

## 3. Lock wait past expiry (P2) — clock after the lock

`lock_for_write(clock)` acquires the row lock, THEN asks the clock,
validates with that reading and returns `(row, when)`; `run_pass` starts
the first-judgment clock from the same reading. The test's clock answers
"expired" only once this session holds the row (a `FOR UPDATE NOWAIT`
probe from a second connection), so it can tell whether the boundary asked
before or after acquiring — no timing, no threads
(`test_the_boundary_asks_the_clock_after_the_lock_is_held`,
`test_the_first_judgment_clock_is_the_reading_taken_under_the_lock`).

## 4. Row lock held into the retention lock (P3)

The already-recovered exit rolls back before `break`. The test wraps
`advisory_lock` and probes the row from another connection at the moment
the retention lock is requested: it must be free
(`test_a_recovered_trial_releases_the_row_before_the_retention_lock`).

## Where to look

- `features/radar/judge_trial.py`: `frozen_supplemental`, `arm_trial`,
  `lock_for_write`, the `RECOVERED` exit in `recover_trial`
- `features/radar/llm_sentiment.py`: the boundary in `run_pass`
- `scripts/audit_encoder_trial.py`: `_supplemental`, `_report_from`,
  `_canonical`, `cmd_accept`
- `scripts/manage_encoder_trial.py`: `_membership`, `cmd_arm`
- Tests: `test_radar_trial_writes.py` §15, `test_radar_judge_trial.py`
  (last two sections), `test_encoder_audit_chain.py` §6–7

# OT1 — the retired encoder trial, taken off the VPS

**2026-09-10, 01:20 CEST.** Executed by Claude on the owner's direct
instruction: get rid of everything related to the trial on the VPS.

**Result: nothing trial-related runs on the server any more.** The recurring
cost is gone. One database row stays, and the reason is a defect that would
take the ingest daemon down — see "What is still there, and why".

---

## What it was costing

| | |
| --- | --- |
| `radar-encoder-trial.timer` | fired **every minute**, `OnCalendar=*-*-* *:*:00`, `Persistent=true` |
| invocations in the preceding 24 hours | **1,439** |
| CPU per invocation | ~4.4 s (`Consumed 4.429s CPU time`) |
| so, per day | roughly **1.8 CPU-hours doing nothing** |

`TRIAL_RETIRED = True` has been deployed since 2026-09-08, so every one of
those 1,439 ticks read the row, saw `RECOVERING` under retirement, and returned
`{'action': 'none'}`. The work was already pointless; only the schedule was
left.

## What was removed

| | |
| --- | --- |
| `/etc/systemd/system/radar-encoder-trial.timer` | stopped, disabled, **file deleted** |
| `/etc/systemd/system/radar-encoder-trial.service` | stopped, **file deleted** |
| systemd's knowledge of both units | gone after `daemon-reload` — `list-unit-files` and `list-timers --all` match nothing |
| `/root/trial-audit` | **removed** — 87 files, 1.6 MB |

Prior state was recorded before anything was touched: the timer
`enabled + active`, the service `static + inactive`.

**Nothing was deleted without a copy first.** `/root/retired-encoder-trial/`
holds both unit files verbatim and `trial-audit-2026-09-10.tar.gz`
(273,206 bytes, sha256
`dee206c2b55d6537d45eb0d397ecc2c64f676d99d5867b42a4e922fd5596c9c9`). The audit
directory is the trial's own evidence; throwing it away outright would destroy
the record of whether the trial passed, which is not the same request as
stopping it from running.

Restoring the schedule, if it is ever wanted, is:

```
cp /root/retired-encoder-trial/radar-encoder-trial.* /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now radar-encoder-trial.timer
```

## Verified after

- No unit, unit file or timer on the box matches `trial`.
- **No invocation after removal**, checked past the next minute boundary the
  timer would have fired on.
- All five services — `personal_apps_web`, `coc_web`, `radar_ingest`,
  `coc_scheduler`, `personal_apps_gym_notifier` — still **active**.
- No `manage_encoder_trial` process anywhere.

## What is still there, and why

**The `radar_judge_trial` row (one row, status `RECOVERING`) stays. Deleting it
would fail the ingest daemon at startup.**

The chain, read rather than assumed:

- `judge_trial._may_judge(row, now)` — `features/radar/judge_trial.py:746` —
  raises `TrialError('the encoder is configured but no trial is armed…')` when
  `row is None`.
- `judge_config._encoder_or_none` — `features/radar/judge_config.py:166` —
  catches that, then asks `judge_trial.current()` whether the trial is
  `RECOVERING` or `RECOVERED` to decide between a warning and a hard failure.
  With the row deleted `current()` returns `None`, the check is False, and it
  falls through to `raise ConfigError('the encoder cannot start: …')`.
- The only `except ConfigError` in the tree is in `llm_sentiment.review_mode()`
  and is explicitly a WEB path: *"A bad flag value must fail the daemon's
  startup, where an operator sees it."* The daemon's configure path is uncaught
  on purpose.

So today the row being `RECOVERING` is exactly what keeps `radar_ingest`
starting: it takes the warning branch, judging stays disabled, ingestion
continues. Remove the row and the encoder's configuration raises instead.

That is a code defect, not a reason to keep the trial. **The fix is one small
change** — under `TRIAL_RETIRED`, a missing row should mean "no trial, judging
disabled" rather than a configuration error — and it belongs in the ordinary
review-and-deploy path, not typed into a live box at one in the morning. Once
that ships, the row can go in a second, five-second step.

Also still present, and deliberately untouched:

- The trial's **code**: `features/radar/judge_trial.py`, `judge_config.py`'s
  retirement branch, `scripts/manage_encoder_trial.py`,
  `scripts/audit_encoder_trial.py`, `scripts/rollback_encoder_judge.py`, and
  the `b3d9e1f5a274` migration that created the table. Ripping those out
  touches judging, retention and the bucket-write advisory lock; it is a
  refactor with its own review, not part of stopping a timer.
- **One no-op read at daemon startup.** `run_radar_ingest.py:1322` calls
  `judge_trial.tick()` once when the daemon starts, before the judges are
  initialised. Under retirement it returns immediately. It is not scheduled and
  costs nothing measurable — but it is why the daemon's log still says, once
  per restart: `encoder artifact 04512d72b37d serving (trial retired; the armed
  hash 3bb32b5607a8 no longer gates the deploy)`. That line is the only
  forensic record of which artifact is actually serving, and it is worth
  keeping.

## Named follow-ups this leaves

1. **Make a missing trial row survivable** — `judge_config._encoder_or_none`
   should treat "no row" under `TRIAL_RETIRED` as judging-disabled rather than
   a `ConfigError`. Small, testable, and the prerequisite for deleting the row.
2. **Then delete the row**, and decide whether to drop `radar_judge_trial`
   itself or leave the empty table with its migration intact.
3. **Retire the trial code** if the trial is never coming back — a deliberate
   refactor across `judge_trial`, `judge_config`, `retention` and `buckets`.
4. Decide how long `/root/retired-encoder-trial/` should be kept.

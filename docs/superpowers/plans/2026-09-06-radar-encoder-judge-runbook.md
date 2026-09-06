# Radar encoder judge — deployment runbook

Spec: `docs/superpowers/specs/2026-09-06-radar-encoder-judge-design.md`.
Plan: `docs/superpowers/plans/2026-09-06-radar-encoder-judge.md`.
Ledger: `docs/superpowers/plans/2026-09-06-radar-encoder-judge-ledger.md`.

Everything in Tasks 1–8 is built and verified locally. **Nothing here has
been executed.** This is the sequence for doing it, the inputs that must
exist first, and the numbers to watch afterwards.

Michi runs the deploy. Every step below that spends money, copies data to
the VPS, or arms the trial waits for him to say so.

---

## 0. What must be true before anything starts

These are preflight INPUTS, not things to invent while deploying. If any of
them cannot be supplied, the answer is not to arm the trial.

| input | why it must exist first | status |
|---|---|---|
| FP32 ONNX export of `model-train13000` | the artifact on disk is `model-train8600` (see §1) | **owed** |
| Baseline report path + its sha256 | the trial's gates are RELATIVE to the incumbent | **owed** |
| Haiku-era removal proportion `p` | fixes the audit sample size as `ceil(400/p)` | **owed** |
| Sampling seed | fixed before predictions exist, or the trial can pass itself | choose at arming |
| Named human labeller and their dates | ~`ceil(400/p)` blind labels between day 3 and day 7 | **owed** |
| Free disk for the retention pin | the pin stops the pruners; the tables grow | measure in §5 |

### The Haiku baseline expires

The removal-share baseline and `p` both come from `radar_sentiment_judgments`
rows written 2026-08-31..09-03, the only period the paid judge ran. Those
rows cascade with their posts under 30-day post retention, so they disappear
from production around **2026-10-01**. Capture them before then:

```sql
-- On the VPS, read-only. Removal share and its denominator, Haiku era.
SELECT COUNT(*) AS judged,
       SUM(relevance = 'irrelevant'
           OR content_origin = 'broadcast_or_automated') AS removed
FROM radar_sentiment_judgments
WHERE stage = 'primary' AND model = 'claude-haiku-4-5';
```

`p = removed / judged`. Record both counts, not just the ratio.

---

## 1. The artifact is not the one that was benchmarked

`C:\Users\michi\Desktop\radar_labels\encoder\artifact\config.json` records
`"source_model": "model-train8600"`. `model-train13000` — the model every
number in the ledger describes — exists only as `weights.pt`.

So the VPS benchmark (7.0–7.5 rows/s, 1,081 MB resident, "verdicts identical
to the PC's") describes **train8600**, and the parity check in §6 would
compare the wrong model against itself.

Before deploying:

1. Re-export `model-train13000` to FP32 ONNX in the training venv
   (`C:\Users\michi\Desktop\radar_encoder_venv`). Roughly 10 GB of RAM and a
   few minutes; ask before running it.
2. Take the **FP32** file. The exploratory exporter writes `model.onnx` as
   INT8 and `model-fp32.onnx` as FP32 — the plain name is the one that must
   NOT ship. INT8 was measured and rejected: relevance 0.848 → 0.692,
   removal precision 0.861 → 0.750.
3. Assemble the shipping layout:

```
artifacts/judge/active.json     {"path": "v1/", "id": "radar-encoder-v1"}
artifacts/judge/v1/model.onnx        (FP32, ~566 MB)
artifacts/judge/v1/tokenizer.json
artifacts/judge/v1/config.json       {heads, max_len: 256, base, manifest}
```

`config.json`'s manifest carries the training record: seed 20260905, 15,200
labelled rows, 13,492 train rows, the 142 shared-post and 166 near-duplicate
exclusions, the label/export/locked-set hashes, and the git HEAD. `heads`
must list the five class lists in the order `_FIELD_ENUMS` uses — the
adapter refuses to load otherwise, naming the key that differs, and a
reordered list would silently relabel every verdict.

4. Compute the bundle hash — this is the trial's identity:

```bash
python - <<'PY'
import sys; sys.path.insert(0, 'personal_apps')
from features.radar.judge_backends import EncoderBackend
print(EncoderBackend('personal_apps/artifacts/judge').bundle_sha256())
PY
```

The artifact is **not** committed to git: 566 MB, and it is data, not code.

---

## 2. Deploy the code, with judging off

Normal git flow — `main` is what deploys, and `~/update_coc.sh` does a
`git reset --hard`, so nothing is edited on the server.

```bash
# On the VPS, after main is pushed:
./update_coc.sh
```

That stops `radar_ingest`, resets, `pip install -r requirements.txt`
(bringing `onnxruntime` and `tokenizers`, ~50 MB, no torch), runs
`flask db upgrade` in `personal_apps/`, rebuilds the frontend, and restarts
the services.

Two migrations land here:

| revision | what |
|---|---|
| `a1c4f7b2e6d8` | `sentiment_tone_model` + three history display diagnostics |
| `b3d9e1f5a274` | `radar_judge_trial` |

`RADAR_JUDGE_PRIMARY` is unset at this point, so the daemon judges nothing
and the deploy is inert. Confirm it:

```bash
journalctl -u radar_ingest -n 30 | grep 'radar judge:'
# expect: radar judge: primary=none review=none mode=''
```

---

## 3. Swap

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -m
```

It does **not** make an OOM impossible. Measured headroom is ~0.7 GB with
the encoder loaded against the slimmed 488 MB daemon; swap turns a transient
spike into slowdown and buys time for the RSS trigger in §8 to fire. A
sustained leak still ends in an OOM, more slowly.

---

## 4. The artifact, and the watchdog

```bash
scp -r artifacts/judge root@82.165.240.212:/root/coc-stats/personal_apps/artifacts/
```

Then render the watchdog units from the templates in
`personal_apps/deploy/`, **confirming every path against the installed
`radar_ingest` unit** rather than trusting the template:

```bash
systemctl cat radar_ingest        # copy User=, WorkingDirectory=, EnvironmentFile=
cp personal_apps/deploy/radar-encoder-trial.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now radar-encoder-trial.timer
systemctl list-timers radar-encoder-trial.timer
```

Prove it is inert before anything is armed:

```bash
systemctl start radar-encoder-trial.service
journalctl -u radar-encoder-trial -n 20     # expect: nothing to do, exit 0
```

---

## 5. Storage for the retained evidence

The pin stops the pruners for the trial's whole life. Journal events are the
fast-growing half: they are normally kept 48 hours and will instead
accumulate for as long as the trial runs.

```bash
# Before arming, and daily afterwards.
df -h /
mysql -e "SELECT table_name, ROUND(data_length/1048576) AS mb
          FROM information_schema.tables
          WHERE table_schema='personal_apps'
            AND table_name IN ('radar_mention_events','radar_posts');"
```

Record the before figure here when it is measured. A trial that runs its
full ten days holds roughly five days of journal beyond the normal horizon.

---

## 6. Parity, before activation

Score the 200 audit rows through the deployed backend and compare all five
fields against the PC's answers **for the same weights**. They were
identical for train8600; a mismatch on train13000 means a tokenizer or opset
difference, and the trial stops here rather than being explained away.

```bash
# On the VPS, offline: no database writes, no spend.
python - <<'PY'
import json, sys
sys.path.insert(0, '/root/coc-stats/personal_apps')
from features.radar.judge_backends import EncoderBackend
from features.radar import sentiment_input, llm_sentiment
backend = EncoderBackend('/root/coc-stats/personal_apps/artifacts/judge')
items = []
for n, row in enumerate(map(json.loads, open('audit-200.jsonl', encoding='utf-8'))):
    item = llm_sentiment.JudgeItem()
    item.key = n
    item.prepared = sentiment_input.prepare_sentiment_input(
        row['source'], row.get('title'), row['text'], row['ticker'],
        author=row.get('author'), channel=row.get('channel'))
    items.append(item)
got, _usage = {}, None
for start in range(0, len(items), backend.batch_size):
    verdicts, _u = backend.judge_batch(items[start:start + backend.batch_size])
    got.update(verdicts)
json.dump({str(k): vars(v) if hasattr(v, '__dict__') else
           [v.relevance, v.content_origin, v.attitude, v.expected_move,
            v.confidence] for k, v in got.items()},
          open('vps-verdicts.json', 'w'), sort_keys=True, indent=1)
print('wrote', len(got))
PY
```

Diff `vps-verdicts.json` against the PC's file. Record both sha256s.

---

## 7. Arm, then activate — one variable at a time

**Arm first.** The trial record is what pins the evidence, and the encoder
refuses to start without one.

```bash
cd /root/coc-stats/personal_apps
venv/bin/python -m scripts.manage_encoder_trial arm \
    --artifact-sha256 <bundle hash from §1> \
    --baseline-report /root/coc-stats/reports/haiku-baseline.json \
    --baseline-removal-rate <p from §0> \
    --seed <chosen seed>
venv/bin/python -m scripts.manage_encoder_trial status
```

Verify the pin is in place (`evidence pinned from ...`) and the sample size
matches `ceil(400/p)`.

**Then activate**, changing nothing else:

```
RADAR_JUDGE_PRIMARY=encoder
RADAR_JUDGE_TONE=0
RADAR_JUDGE_REVIEW=none
RADAR_REVIEW_TIER=
```

The judge gate stays **ON** — it is not part of this change, and turning it
off would make two variables move at once.

```bash
systemctl restart radar_ingest
journalctl -u radar_ingest -f | grep -E 'radar judge:|radar sentiment'
```

Expect `radar judge: primary=radar-encoder-v1 review=none mode=''`.

---

## 8. The first cycle, and what to watch

```bash
# The clock starts with the FIRST WRITTEN VERDICT, not with the restart.
venv/bin/python -m scripts.manage_encoder_trial status | grep 'first judged'
```

Write that timestamp down. Day 3, day 7 and day 10 are all counted from it.

```sql
-- Tone must be absent by construction, not by a display rule.
SELECT COUNT(*) AS judged,
       SUM(sentiment_attitude IS NOT NULL)   AS attitude_written,
       SUM(llm_sentiment IS NOT NULL)        AS projection_written,
       SUM(sentiment_tone_model IS NOT NULL) AS tone_owner_written
FROM radar_mentions
WHERE sentiment_model = 'radar-encoder-v1';
-- attitude_written and projection_written MUST be 0 for rows with no
-- earlier Anthropic tone. Any nonzero value on a fresh row stops the trial.

-- The history keeps all five fields, plus what production was displaying.
SELECT attitude, displayed_tone, displayed_judged_by, COUNT(*)
FROM radar_sentiment_judgments
WHERE model = 'radar-encoder-v1'
GROUP BY 1, 2, 3;
```

Operational watch, daily unless noted:

| what | where | trigger (spec §7.2) |
|---|---|---|
| daily removal share | `radar_sentiment_judgments` vs the §0 baseline | ±50% relative |
| p95 backlog age | board `sentiment_ops.p95_age_minutes` | >20 min for 2 consecutive hours |
| daemon RSS | `systemctl status radar_ingest` | >2.5 GB |
| box free memory | `free -m` | <300 MB available |
| bucket anomalies | journal rebuild logs | anything the rebuild cannot explain |
| free disk | `df -h /` | the pin is holding evidence; watch it fall |

Continuously during the first hours: RSS and backlog.

---

## 9. Stopping, and recovering

Two steps, and **the first alone is not a rollback**: switching the backend
off stops new judgments and leaves every decision already made in the
counts.

```bash
# 1. Durable stop. Survives a restart and a stale environment file.
venv/bin/python -m scripts.manage_encoder_trial stop --reason "removal share -60% vs baseline"

# 2. Recovery. Reports by default; writes only with --apply.
venv/bin/python -m scripts.rollback_encoder_judge
venv/bin/python -m scripts.rollback_encoder_judge --apply --limit 2000
# ...repeat until "All recovered. The retention pin is released."
```

Recovery is resumable: each window is one transaction, and a cleared mention
no longer matches the selection. Tone and its provenance are never cleared —
the trial did not write them.

Archive a dry run before the trial starts, so the expected output is known:

```bash
venv/bin/python -m scripts.rollback_encoder_judge > /root/recovery-dry-run-day0.txt
```

Status and timer:

```bash
venv/bin/python -m scripts.manage_encoder_trial status
systemctl list-timers radar-encoder-trial.timer
journalctl -u radar-encoder-trial --since '1 hour ago'
```

---

## 10. The audit, on the clock

From `first_judged_at`:

| day | action | who |
|---|---|---|
| 3 | `audit_encoder_trial sample --out DIR` then `export-labels` | automatic + operator |
| 3–7 | label `ceil(400/p)` blind rows | **named human, owed** |
| 7 | labels and adjudication complete | labeller |
| ≤10 | `evaluate` then `accept` | operator |

```bash
venv/bin/python -m scripts.audit_encoder_trial sample --out /root/audit-day3
venv/bin/python -m scripts.audit_encoder_trial export-labels --out /root/audit-day3
# ... labelling happens here, blind: no predictions in the file ...
venv/bin/python -m scripts.audit_encoder_trial evaluate --out /root/audit-day3 \
    --labels /root/audit-day3/labels.jsonl \
    --encoder-predictions /root/audit-day3/encoder.jsonl \
    --haiku-predictions /root/audit-day3/haiku.jsonl \
    --shadow-days 7
venv/bin/python -m scripts.audit_encoder_trial accept --report /root/audit-day3/report.json
```

**Producing `haiku.jsonl` costs money.** It is a paid Haiku pass over the
sampled rows, scored offline — it never goes through `apply_judgments`, so
it cannot move a mention, a bucket or the spend meter beyond its own call
accounting. It is a separate authorised step, deliberately not folded into
`evaluate`, because an evaluation command that quietly spends is one
somebody runs twice.

If day 10 arrives without a recorded passing audit, the watchdog stops the
trial and drains recovery on its own. That is the design, not a failure of
process — but it is a worse outcome than evaluating on time.

**A passing audit changes almost nothing.** It lifts the deadline and
authorises the trial to keep running, suppressed, with its evidence still
pinned. It does not promote the encoder, release the pin, or enable tone.
Each of those is a separate, separately reviewed change.

---

## 11. What this deployment does not do

Turning the judge gate off; retiring the lexicon; moving the relevance head
into extraction; INT8; measuring extraction recall; historical encoder
rejudging; enabling encoder tone. Every one is named in spec §7.4 with its
reason.

Deployment succeeding does **not** complete the fresh audit. That needs the
actual report and its acceptance record.

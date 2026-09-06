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
| FP32 ONNX export of `model-train13000` | the old artifact was `model-train8600` (see §1) | **done 2026-09-06** |
| Haiku-era removal proportion `p` | fixes the audit sample size as `ceil(400/p)` | **captured, below** |
| Baseline report file + its sha256 | `arm` takes a path and records its hash | write it from the figures below |
| Sampling seed | fixed before predictions exist, or the trial can pass itself | choose at arming |
| Named human labeller and their dates | 746 blind labels between day 3 and day 7 | **owed** |
| Supplemental membership files (two) | `arm` freezes WHICH rows the two supplementary sets are; §7 has the recipe | make from `audit-200.jsonl` and `test-natural.json` |
| Free disk for the retention pin | the pin stops the pruners; the tables grow | measure in §5 |

### The baseline, captured 2026-09-06

Read-only query against production, over the only window the paid judge ever
ran — 2026-08-31 11:49:51 to 2026-09-03 16:37:37 UTC.

| | |
|---|---|
| judged (stage `primary`, model `claude-haiku-4-5`) | **16,297** |
| removed (`irrelevant` OR `broadcast_or_automated`) | **8,747** |
| **p** | **0.5367** |
| **audit sample size** `ceil(400 / p)` | **746** |

Daily removal share: 0.5517, 0.6233, 0.5402, 0.4441. The §7.2 rollback
trigger is ±50% relative on this, so the band is **0.268 – 0.805**; a daily
share outside it stops the trial that day.

Composition of the 8,747 removals — worth knowing, because it is not what
the extraction work assumes:

| | count | share of removals |
|---|---|---|
| broadcast/automated only | 5,589 | 64% |
| irrelevant only | 2,509 | 29% |
| both | 649 | 7% |
| (`uncertain` on either field, not removed) | 1,868 | — |

Roughly two thirds of what the incumbent removed is **broadcast or
automated content** — relayed headlines, templated price feeds, bulk market
lists — rather than junk tickers. The queued extraction work targets the
irrelevant third.

`p = 0.5367` is materially higher than the 0.30 assumed while planning,
which came from the *irrelevant* rate in the quota-stratified Sonnet label
set. The audit is therefore **746 rows, not ~1,300**.

The query, for reproducing it before the rows expire around **2026-10-01**
(they cascade with their posts under 30-day post retention):

```sql
SELECT COUNT(*) AS judged,
       SUM(relevance = 'irrelevant'
           OR content_origin = 'broadcast_or_automated') AS removed
FROM radar_sentiment_judgments
WHERE stage = 'primary' AND model = 'claude-haiku-4-5';
```

---

## 1. The artifact — packaged and verified

The exploratory export was the wrong model. `encoder/artifact/config.json`
recorded `"source_model": "model-train8600"`, while `model-train13000` — the
model every number in the ledger describes — existed only as `weights.pt`.

So the VPS benchmark (7.0–7.5 rows/s, 1,081 MB resident, "verdicts identical
to the PC's") described **train8600**, and the §6 parity check would have
compared the wrong model against itself and passed.

**Packaged 2026-09-06** with `scripts/package_encoder_artifact.py`, which
imports the model class from `train_encoder.py` rather than reimplementing
it, writes FP32 only, and carries the training manifest into the artifact:

```bash
/c/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe \
    personal_apps/scripts/package_encoder_artifact.py \
    --model C:/Users/michi/Desktop/radar_labels/encoder/model-train13000 \
    --out   personal_apps/artifacts/judge
```

```
artifacts/judge/active.json     {"path": "v1/", "id": "radar-encoder-v1"}
artifacts/judge/v1/model.onnx        565.8 MB, fp32, opset 17
artifacts/judge/v1/tokenizer.json
artifacts/judge/v1/config.json       {heads, max_len: 256, base, manifest}
```

| | |
|---|---|
| `source_model` | `model-train13000` |
| **bundle sha256** | `3bb32b5607a8a368d8ff72179b41de00c6a971223bbed21302e95dcfb90dccb5` |
| PC throughput | 4.1 rows/s over the 200 audit rows (48.4 s) |

**Verified to be the right model.** The 200-row audit was re-scored through
this artifact and compared against its human labels. Every figure reproduces
the ledger exactly:

| | fresh export | ledger |
|---|---|---|
| relevance | 75.5% | 75.5% |
| content origin | 93.5% | 93.5% |
| attitude | 79.5% | 79.5% |
| expected move | 85.0% | 85.0% |
| removal precision | 0.968 (91/94) | 0.968 |
| removal recall | 0.728 (91/125) | 0.728 |
| polarity flips | 3/54 | 3/54 |

The same comparison against the verdicts already stored in
`audit-200.jsonl` agrees on only **128 of 200** rows — those were
train8600's, which is exactly why the re-export was necessary.

PC-side verdicts for the §6 parity check are saved at
`C:\Users\michi\Desktop\radar_labels\pc-verdicts-train13000.json`,
sha256 `d096a97a052e51fd7bfcfccafabe1bf59d04bead661861e634bdd3722a13bd5f`.

The INT8 trap is gone: the packaging script writes no INT8 file at all. INT8
was measured and rejected — relevance 0.848 → 0.692, removal precision
0.861 → 0.750.

`config.json`'s manifest carries the training record: seed 20260905, 15,200
labelled rows, 13,492 train rows, the 142 shared-post and 166 near-duplicate
exclusions, the input hashes and git HEAD `c489f1c`. `heads` lists the five
class lists in the order `_FIELD_ENUMS` uses — the adapter refuses to load
otherwise, naming the key that differs, and a reordered list would silently
relabel every verdict.

The artifact is **not** committed to git: 566 MB, and it is data, not code.
`personal_apps/artifacts/` is gitignored.

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
got = {}
for start in range(0, len(items), backend.batch_size):
    verdicts, _usage = backend.judge_batch(
        items[start:start + backend.batch_size])
    got.update(verdicts)
json.dump({str(key): [v.relevance, v.content_origin, v.attitude,
                      v.expected_move, v.confidence]
           for key, v in got.items()},
          open('vps-verdicts.json', 'w'), sort_keys=True, indent=1)
print('wrote', len(got))
PY
```

Diff `vps-verdicts.json` against the PC's file. Record both sha256s.

---

## 7. Arm, then activate — one variable at a time

**Arm first.** The trial record is what pins the evidence, and the encoder
refuses to start without one.

Arming also freezes the membership of the two supplementary sets the audit
report must carry (spec §7.2c/§7.3): the original 200-row audit with its
two halves, and the 900-row locked natural set. `evaluate` later checks the
supplied files against exactly this membership -- every frozen row, each
once, in its frozen half -- so a file holding nothing, or a convenient
subset, is not the set. One command on the PC makes the two membership
files AND the two data files evaluate needs later, from what is on disk
(the natural set is scored through the packaged artifact here, ~4 minutes
of CPU, because the training runs kept no per-row predictions):

```bash
cd personal_apps
python -m scripts.build_supplemental_sets \
    --audit C:/Users/michi/Desktop/radar_labels/audit-200.jsonl \
    --audit-verdicts C:/Users/michi/Desktop/radar_labels/pc-verdicts-train13000.json \
    --natural C:/Users/michi/Desktop/radar_labels/test-natural.json \
    --labels C:/Users/michi/Desktop/radar_labels/labels-sonnet5.jsonl \
    --export C:/Users/michi/Desktop/radar_labels/export-2026-09-05.jsonl \
    --artifact-dir artifacts/judge \
    --out C:/Users/michi/Desktop/radar_labels/supplemental
```

It writes `supplemental-audit-keys.json`, `supplemental-natural-keys.json`
(for `arm`) and `supplemental-audit.jsonl`, `supplemental-natural.jsonl`
(for `evaluate`, §10). Copy all four to the VPS.

```bash
cd /root/coc-stats/personal_apps
venv/bin/python -m scripts.manage_encoder_trial arm \
    --artifact-sha256 3bb32b5607a8a368d8ff72179b41de00c6a971223bbed21302e95dcfb90dccb5 \
    --baseline-report /root/coc-stats/reports/haiku-baseline.json \
    --baseline-removal-rate 0.5367 \
    --seed <chosen seed> \
    --supplemental-audit-keys /root/coc-stats/reports/supplemental-audit-keys.json \
    --supplemental-natural-keys /root/coc-stats/reports/supplemental-natural-keys.json
venv/bin/python -m scripts.manage_encoder_trial status
```

Verify the pin is in place (`evidence pinned from ...`), the sample size
matches `ceil(400/p)`, and the arm line reports `audit 200 keys in 2
halves, natural 900 keys`.

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
| 3 | `sample --out DIR`, then `export-labels`, then `predict` twice | operator |
| 3–7 | label `ceil(400/p)` blind rows, with `labelled_at` on every row | **named human, owed** |
| 7 | labels and adjudication complete; supplemental sets ready | labeller + operator |
| ≤10 | `evaluate`, inspect the disagreement lists, acknowledge, `accept` | operator |

The commands are a **chain**: each reads what the one before it wrote and
refuses what it did not. Run them in order, in the same directory.

```bash
D=/root/audit-day3
venv/bin/python -m scripts.audit_encoder_trial sample         --out $D
venv/bin/python -m scripts.audit_encoder_trial export-labels  --out $D
venv/bin/python -m scripts.audit_encoder_trial predict        --out $D --backend encoder
venv/bin/python -m scripts.audit_encoder_trial export-prompts --out $D
# ... the incumbent: a Haiku subagent in Claude Code answers each prompt
#     in $D/prompts/ (see below); its answers land in $D/answers/ ...
venv/bin/python -m scripts.audit_encoder_trial import-predictions --out $D \
    --backend claude-haiku-4-5@claude-code-subagent --answers $D/answers
# ... labelling happens here, blind: no predictions in blind.jsonl ...
venv/bin/python -m scripts.audit_encoder_trial evaluate --out $D \
    --labels $D/labels.jsonl \
    --encoder-predictions $D/radar-encoder-v1.jsonl \
    --haiku-predictions $D/claude-haiku-4-5@claude-code-subagent.jsonl \
    --supplemental-audit $D/supplemental-audit.jsonl \
    --supplemental-natural $D/supplemental-natural.jsonl
# ... read report.md; look at the two disagreement lists in report.json ...
venv/bin/python -m scripts.audit_encoder_trial accept --report $D/report.json \
    --acknowledgments $D/acknowledgments.json
```

**`sample`** refuses before day 3 (the frame is not closed), after day 7
(a draw then could never be accepted), and never redraws: a rerun reuses
the recorded draw. Its `frame.json` and `sample.json` carry the trial's
artifact hash, prompt version and model id.

**`predict`** scores exactly the sampled ids, through the same prepared
inputs the live pass uses, and never through `apply_judgments` -- it cannot
move a mention, a bucket or the history. The encoder pass refuses an
artifact whose bundle hash is not the armed one and books its calls on the
spend meter. The output file's first line is a provenance header: backend,
artifact hash, prompt version, the sample file's hash.

**The incumbent has no API credits** (the paid judge stopped on 2026-09-03
and paying again is off the table -- Michi's ruling, 2026-09-06). Its
predictions come from a Haiku subagent inside Claude Code instead:

1. `export-prompts` writes `$D/prompts/batch-NNNN.txt` -- byte for byte the
   prompt `AnthropicBackend` would have sent, twenty items each, in sample
   order -- plus `manifest.json` (batch -> mention ids, sample hash, prompt
   version, and the answer shape).
2. Copy `$D/prompts/` to the PC. In Claude Code, one Haiku 4.5 subagent per
   batch (38 for 746 rows) receives the prompt text verbatim and returns
   the JSON `{"verdicts": [{"n": 1, "relevance": ..., "content_origin":
   ..., "attitude": ..., "expected_move": ..., "confidence": ...}, ...]}`,
   saved as `answers/batch-NNNN.json`. Nothing else is given to the
   subagent: no labels, no encoder verdicts.
3. Copy `answers/` back; `import-predictions` turns them into
   `claude-haiku-4-5@claude-code-subagent.jsonl` with the provenance header
   `via: claude-code-subagent`. A batch never answered, an answer outside
   the enums, or an `n` outside the batch is an unanswered row and fails
   coverage -- never a default.

It is not the API path and the report says so (`predictions.incumbent`).
The comparison it feeds is reported only; it cannot stop the trial.

**`labels.jsonl`** is the human's file, one row per sampled mention:

```json
{"mention_id": 123, "relevance": "relevant", "content_origin": "human_chatter",
 "attitude": "positive", "expected_move": "up", "confidence": "high",
 "labelled_at": "2026-09-14T10:22:00"}
```

`labelled_at` is required on every row; the latest one is when labelling
finished, and it must be on or before day 7. A row that was adjudicated
keeps its first label under `original` and says why:

```json
{"mention_id": 124, "relevance": "irrelevant", ..., "labelled_at": "...",
 "original": {"relevance": "relevant", "content_origin": "human_chatter",
              "attitude": "positive", "expected_move": "up", "confidence": "high"},
 "adjudication_reason": "the ticker is a common word here, not the company"}
```

An adjudication without a reason makes the report **incomplete**, and an
incomplete report cannot be accepted. Rows for mentions outside the sample
are refused outright; a sampled mention with no row fails coverage.

**The supplemental sets** (spec §7.3) are the two things the fresh audit is
not: the original 200-row audit, both halves, and the locked natural test
set. Both are required for a complete report, and each must hold exactly
the rows frozen at arming (§7), each once, in its frozen half -- a missing,
extra, duplicated or re-halved row makes the report incomplete. The format
is one JSON object per line:

```json
{"key": "removal-17", "half": "removal", "truncated": false,
 "reference": {five fields}, "prediction": {five fields}}
```

`evaluate` recomputes the reversal rate and removal precision per half under
the audit's own definitions, never pools them, never lets them near the
gate, and lists every reversal and every disagreement on a truncated post
in `report.json` for inspection. To produce the audit set from what is on
disk (`audit-200.jsonl` holds `half`, `human` and `n`;
`pc-verdicts-train13000.json` holds the shipping model's verdicts by `n`):

```python
import json
verdicts = json.load(open('pc-verdicts-train13000.json'))
fields = ('relevance', 'content_origin', 'attitude', 'expected_move', 'confidence')
with open('supplemental-audit.jsonl', 'w') as out:
    for row in map(json.loads, open('audit-200.jsonl', encoding='utf-8')):
        prediction = dict(zip(fields, verdicts[str(row['n'])]))
        out.write(json.dumps({'key': 'audit-%d' % row['n'], 'half': row['half'],
                              'truncated': bool(row.get('truncated')),
                              'reference': row['human'],
                              'prediction': prediction}) + '
')
```

The locked natural set (`test-natural.json`, 900 rows) has no stored
per-row predictions -- the training runs kept aggregates only. Producing
`supplemental-natural.jsonl` means scoring those rows through the packaged
artifact on the PC, the way the 200 were re-scored in §1. **Owed**, with
the labeller, before day 7.

**`evaluate`** writes `report.json` and `report.md`. The tone shadow period
is read from the judgment history (encoder primary rows carrying
`displayed_tone`), not from a flag. The report records the hash and path of
every input it used and says whether it is complete; the reasons it is not
are listed.

**`acknowledgments.json`** is written by whoever inspected the two
disagreement lists, against the exact report they inspected:

```json
{"report_sha256": "<sha256 of report.json>",
 "inspected": ["reversal_disagreements", "truncated_disagreements"],
 "by": "michi", "at": "2026-09-16T18:00:00"}
```

**`accept`** re-hashes every input the report names, recomputes the WHOLE
report from them -- every interval, every disagreement list, every
supplemental figure, not just the pass flag -- and refuses one that does
not reproduce, checks the
acknowledgments against this report's hash, checks the draw was between day
3 and day 7 and the labels finished by day 7, and only then records the
result. A failing report is accepted too: it stops the trial and starts
recovery. That is a result, not an error.

If day 10 arrives without a recorded passing audit, the watchdog stops the
trial and drains recovery on its own. That is the design, not a failure of
process -- but it is a worse outcome than evaluating on time.

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

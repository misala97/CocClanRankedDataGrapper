# Ranked Score TH-Ceiling Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the ranked-week score formula so a flawless week scores 100 at every townhall level, not just TH≤16 — by normalizing each player's adjusted-star sum against their own TH's maximum achievable multiplier instead of one flat constant.

**Architecture:** One new helper function (`_max_th_multiplier`) plus a one-line change to the existing normalization divisor inside `_ranked_score_from_adj`, both in `coc_stats/services/helpers.py`. Verification is a before/after snapshot diff run against the live-imported dev database (this repo has no automated test suite; verification is manual, against real data) rather than unit tests.

**Tech Stack:** Python 3, Flask/SQLAlchemy (existing `coc_stats` app), MySQL80 dev DB (already populated with the 2-month live import).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-ranked-score-th-ceiling-design.md`
- Code-only change on branch `dev_coc`. No deploy step — this app deploys via git, not ad-hoc server commands.
- Only `_ranked_score_from_adj` and its new helper `_max_th_multiplier` change. Do not touch `_league_mult`, `_ranked_verdict` thresholds, `_calc_th_multiplier`'s own multiplier table, or missing-attack averaging — all explicitly out of scope per the spec.
- `player_th == 0` (missing townhall data) must keep falling through to the `else` branch (multiplier 1.15 → ceiling 3.45) — identical to current behavior, no new error path.
- TH≤16 scores must come out byte-for-byte identical before and after the change (still divided by 3.45). Only TH17/TH18 scores may move.
- Run all Python commands from `C:\Users\michi\Desktop\CodingStuff\coc_stats` (or with that path inserted via `sys.path`, as shown below) so `from app import app` resolves — this loads the Flask app without hitting the live Clash of Clans API (per this project's established local-run pattern).
- Scratch/verification scripts and their JSON output live under the scratchpad directory below, not in the git repo:
  `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\`

---

### Task 1: Snapshot current ("before") ranked scores from live data

**Files:**
- Create: `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\snapshot_ranked_scores.py`
- Produces (data): `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_before.json`

**Interfaces:**
- Consumes: `coc_stats.services.helpers._is_attack`, `_calc_th_multiplier`, `_ranked_score_from_adj`, `_ranked_verdict` (all existing, unmodified in this task); `coc_stats.models.RankedWeek` (existing).
- Produces: a JSON file — list of row objects `{player_tag, season, th, league_tier, att_count, max_attacks, score_100, badge, label}` — that Task 3 and Task 4 both read by exact filename.

- [ ] **Step 1: Write the snapshot script**

```python
import sys, json

sys.path.insert(0, r"C:\Users\michi\Desktop\CodingStuff\coc_stats")

from app import app
from models import RankedWeek
from services.helpers import _is_attack, _calc_th_multiplier, _ranked_score_from_adj, _ranked_verdict

OUTPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "ranked_score_snapshot.json"

with app.app_context():
    weeks = RankedWeek.query.all()
    rows = []
    for w in weeks:
        att_max = w.max_attacks or 0
        if att_max <= 0:
            continue
        player_th = w.townhall or 0
        adj = []
        att_count = 0
        for l in w.battle_logs:
            if _is_attack(l):
                att_count += 1
                try:
                    opp_th = int(l.opponent_th)
                except (TypeError, ValueError):
                    opp_th = player_th
                diff = opp_th - player_th
                adj.append((l.stars or 0) * _calc_th_multiplier(diff, player_th))
        score, th_adj, lm = _ranked_score_from_adj(adj, att_max, w.league_tier or '', player_th)
        badge, label, _ = _ranked_verdict(score, att_count, att_max)
        rows.append({
            'player_tag': w.player_tag,
            'season': w.league_season_id,
            'th': player_th,
            'league_tier': w.league_tier,
            'att_count': att_count,
            'max_attacks': att_max,
            'score_100': score,
            'badge': badge,
            'label': label,
        })

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
```

- [ ] **Step 2: Run it to produce the "before" snapshot**

Run:
```bash
python "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\snapshot_ranked_scores.py" "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_before.json"
```
Expected: `Wrote 326 rows to C:\...\ranked_score_before.json`

- [ ] **Step 3: Spot-check three known rows against pre-computed values**

Run:
```bash
python -c "
import json
rows = json.load(open(r'C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_before.json'))
idx = {(r['player_tag'], r['season']): r for r in rows}
checks = [
    (('#2PGYUL28', '1782709200'), 91),   # TH18
    (('#2JUQY0JP', '1780894800'), 91),   # TH17
    (('#GCR08GUPC', '1783314000'), 98),  # TH15 (control, must not move later)
]
for key, expected in checks:
    actual = idx[key]['score_100']
    status = 'OK' if actual == expected else 'MISMATCH'
    print(key, 'expected', expected, 'got', actual, status)
"
```
Expected: all three print `OK` (91, 91, 98 respectively). If any prints `MISMATCH`, stop and re-check Step 1's script against `coc_stats/services/helpers.py` before proceeding — the baseline must be trustworthy before the fix is applied.

---

### Task 2: Apply the per-TH ceiling fix

**Files:**
- Modify: `C:\Users\michi\Desktop\CodingStuff\coc_stats\services\helpers.py:593-598`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_max_th_multiplier(player_th) -> float`, callable by name from `coc_stats.services.helpers` (used by Task 3's snapshot re-run and available for any future caller). `_ranked_score_from_adj` keeps its existing signature `(adj_scores, max_attacks, league_tier, player_th) -> (int, float, float)` — same three-tuple return shape, only the divisor inside changes.

- [ ] **Step 1: Edit `services/helpers.py`**

Replace:
```python
def _ranked_score_from_adj(adj_scores, max_attacks, league_tier, player_th):
    lm = _league_mult(league_tier, player_th)
    if not max_attacks:
        return 0, 0.0, lm
    th_adj = sum(adj_scores) / max_attacks
    return min(round(th_adj * lm * 100 / 3.45), 100), th_adj, lm
```

With:
```python
def _max_th_multiplier(player_th):
    if player_th >= 18: return 1.00
    if player_th == 17: return 1.05
    return 1.15


def _ranked_score_from_adj(adj_scores, max_attacks, league_tier, player_th):
    lm = _league_mult(league_tier, player_th)
    if not max_attacks:
        return 0, 0.0, lm
    th_adj = sum(adj_scores) / max_attacks
    ceiling = 3 * _max_th_multiplier(player_th)
    return min(round(th_adj * lm * 100 / ceiling), 100), th_adj, lm
```

- [ ] **Step 2: Verify the fix against the same three known rows, computed fresh from the DB**

Run:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from models import RankedWeek
from services.helpers import _is_attack, _calc_th_multiplier, _ranked_score_from_adj

TARGETS = [
    (('#2PGYUL28', '1782709200'), 100),  # TH18: was 91, ceiling 3.45->3.00 pushes it to the 100 cap
    (('#2JUQY0JP', '1780894800'), 99),   # TH17: was 91, ceiling 3.45->3.15
    (('#GCR08GUPC', '1783314000'), 98),  # TH15 control: unchanged, still divides by 3.45
]

with app.app_context():
    for (tag, season), expected in TARGETS:
        w = RankedWeek.query.filter_by(player_tag=tag, league_season_id=season).first()
        player_th = w.townhall or 0
        att_max = w.max_attacks or 0
        adj = []
        for l in w.battle_logs:
            if _is_attack(l):
                try:
                    opp_th = int(l.opponent_th)
                except (TypeError, ValueError):
                    opp_th = player_th
                diff = opp_th - player_th
                adj.append((l.stars or 0) * _calc_th_multiplier(diff, player_th))
        score, _, _ = _ranked_score_from_adj(adj, att_max, w.league_tier or '', player_th)
        status = 'OK' if score == expected else 'MISMATCH'
        print(tag, season, 'th', player_th, 'expected', expected, 'got', score, status)
"
```
Expected:
```
#2PGYUL28 1782709200 th 18 expected 100 got 100 OK
#2JUQY0JP 1780894800 th 17 expected 99 got 99 OK
#GCR08GUPC 1783314000 th 15 expected 98 got 98 OK
```
If any row prints `MISMATCH`, re-check the edit against Step 1 exactly — do not proceed to Task 3 with an unverified fix.

- [ ] **Step 3: Commit**

```bash
git add coc_stats/services/helpers.py
git commit -m "$(cat <<'EOF'
fix(ranked): normalize score ceiling per townhall, not one flat constant

TH18 can never face a higher-TH opponent so its per-attack multiplier
tops out at 1.00 (vs 1.15 for TH<=16, 1.05 for TH17), but every TH was
being normalized against the same flat 3.45 divisor. Flawless play
topped out around 87 for TH18 and 91 for TH17 instead of 100.
_max_th_multiplier() mirrors _calc_th_multiplier's own ceiling per TH
so perfect play now reaches 100 at every townhall level.
EOF
)"
```

---

### Task 3: Snapshot patched ("after") ranked scores

**Files:**
- Reuse: `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\snapshot_ranked_scores.py` (from Task 1, unmodified — it always calls the current `_ranked_score_from_adj`, so re-running it after Task 2's edit captures the patched behavior automatically)
- Produces (data): `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_after.json`

**Interfaces:**
- Consumes: the same script from Task 1 — no code changes.
- Produces: same JSON row shape as Task 1's output, for Task 4 to diff against `ranked_score_before.json`.

- [ ] **Step 1: Run the snapshot script again against the patched code**

Run:
```bash
python "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\snapshot_ranked_scores.py" "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_after.json"
```
Expected: `Wrote 326 rows to C:\...\ranked_score_after.json` — same row count as Task 1 (326). A different count means rows were added/removed from the DB between snapshots and the diff in Task 4 will not be trustworthy; re-run Task 1's snapshot first if so.

- [ ] **Step 2: Spot-check the same three known rows now show the patched values**

Run:
```bash
python -c "
import json
rows = json.load(open(r'C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_after.json'))
idx = {(r['player_tag'], r['season']): r for r in rows}
checks = [
    (('#2PGYUL28', '1782709200'), 100),
    (('#2JUQY0JP', '1780894800'), 99),
    (('#GCR08GUPC', '1783314000'), 98),
]
for key, expected in checks:
    actual = idx[key]['score_100']
    status = 'OK' if actual == expected else 'MISMATCH'
    print(key, 'expected', expected, 'got', actual, status)
"
```
Expected: all three print `OK`.

---

### Task 4: Diff before vs. after and present the comparison

**Files:**
- Create: `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\diff_ranked_scores.py`

**Interfaces:**
- Consumes: `ranked_score_before.json` and `ranked_score_after.json` (Tasks 1 and 3).
- Produces: a printed report (average score delta by TH, count of rows whose score changed per TH, full list of verdict-badge flips) — this is the artifact the user reviews before Task 5's commit is allowed to happen. No further task consumes this programmatically.

- [ ] **Step 1: Write the diff script**

```python
import json, sys
from collections import defaultdict

BEFORE = sys.argv[1] if len(sys.argv) > 1 else "ranked_score_before.json"
AFTER = sys.argv[2] if len(sys.argv) > 2 else "ranked_score_after.json"

with open(BEFORE, encoding='utf-8') as f:
    before = {(r['player_tag'], r['season']): r for r in json.load(f)}
with open(AFTER, encoding='utf-8') as f:
    after = {(r['player_tag'], r['season']): r for r in json.load(f)}

assert set(before.keys()) == set(after.keys()), "row set mismatch between snapshots — re-run Task 1 and Task 3 back to back"

by_th = defaultdict(list)
flips = []
for key, b in before.items():
    a = after[key]
    delta = a['score_100'] - b['score_100']
    by_th[b['th']].append(delta)
    if a['badge'] != b['badge']:
        flips.append((key, b['th'], b['score_100'], b['badge'], a['score_100'], a['badge']))

print("=== Average score delta by TH (TH<=16 must all be 0.00 / 0 nonzero) ===")
for th in sorted(by_th.keys()):
    deltas = by_th[th]
    avg = sum(deltas) / len(deltas)
    nonzero = sum(1 for d in deltas if d != 0)
    print(f"  TH{th:2d}: n={len(deltas):4d} avg_delta={avg:+6.2f} nonzero_deltas={nonzero}")

print(f"\n=== Verdict badge flips: {len(flips)} ===")
for key, th, b_score, b_badge, a_score, a_badge in sorted(flips, key=lambda r: -r[4]):
    print(f"  {key[0]:12s} season={key[1]} TH{th:2d}: {b_score:3d} {b_badge:16s} -> {a_score:3d} {a_badge:16s}")
```

- [ ] **Step 2: Run it**

Run:
```bash
python "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\diff_ranked_scores.py" "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_before.json" "C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\e3d84155-e55b-45b0-9e89-fedd0b5e890f\scratchpad\ranked_score_after.json"
```
Expected: no `AssertionError`; the "Average score delta by TH" block shows `avg_delta=+0.00` and `nonzero_deltas=0` for every TH from the data at or below 16, and nonzero positive average deltas for TH17 and TH18. If any TH≤16 row shows a nonzero delta, the fix has a bug — stop and re-check Task 2's edit (TH≤16 must be byte-for-byte unchanged per the Global Constraints).

- [ ] **Step 3: STOP — hand the printed report to the user**

This is a manual checkpoint, not an automated one: paste the full script output (both sections) into the conversation and wait for explicit approval before Task 5. Do not commit anything beyond Task 2's already-committed code change until the user has seen real before/after rows and confirmed the new numbers look right.

---

### Task 5: Close out

**Files:** none (verification-only task)

**Interfaces:**
- Consumes: user's go-ahead from Task 4, Step 3.
- Produces: nothing further — Task 2 already committed the only code change. This task exists to make explicit that no additional commit, deploy, or cleanup step is needed.

- [ ] **Step 1: Confirm with the user that Task 2's commit stands as final**

If the user wants any follow-up (e.g. they've decided one of the out-of-scope items from the spec should be revisited after seeing real numbers), stop here and re-enter brainstorming for that follow-up rather than expanding this plan.

- [ ] **Step 2: Leave scratch files in place**

The snapshot/diff scripts and JSON outputs stay in the scratchpad directory (session-scoped temp storage) — they are verification artifacts, not part of the shipped `coc_stats` codebase, and are not added to git.

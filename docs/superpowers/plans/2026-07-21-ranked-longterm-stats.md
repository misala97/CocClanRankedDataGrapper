# Ranked Long-Term Stats ("The Record") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder `/ranked/stats` page with a long-term Ranked record organized around trajectory over time, built on pure, independently-verifiable aggregation functions.

**Architecture:** All aggregation moves out of the route into a new pure-function module `features/ranked/stats.py` that takes ORM rows and returns plain dicts — no Flask, no DB session, no template concerns. The route becomes a thin caller with a cache wrapper. The template renders four zones from one JSON payload. Scoring is never reimplemented: `_calc_ranked_score`, `_ranked_verdict`, `_get_league_rank`, and `_is_attack` all come from `services/helpers.py`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy 2.x, PyMySQL, Jinja2, Chart.js (already wired via `{% set chartjs = true %}`), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-07-21-ranked-longterm-stats-design.md`

## Global Constraints

- **No pytest in this monorepo.** Verification is standalone Python scripts plus manual HTTP via `app.test_client()`. Do not add a test framework or a `tests/` directory.
- **Never reimplement scoring.** Import `_calc_ranked_score`, `_ranked_verdict`, `_get_league_rank`, `_is_attack` from `services/helpers.py`.
- **`_head.html` leaves a `<style>` tag open.** A page template writes CSS directly after the include. Opening a second `<style>` tag silently eats the next CSS rule.
- **All thresholds are named module constants**, never inline literals.
- **Mobile:** responsive data tables become dense divided `.mr` rows, never spacious per-player cards.
- **Accessibility:** `title` is mouse-only — use the native Popover API for touch/keyboard disclosures. Custom clickables must be real `<button>` elements. A sortable `<th>` gets `tabindex`, not `role`.
- **Visual execution is out of scope for this plan.** Class names and markup here are structural. Palette, typography, signature element, and motion go through the `impeccable` skill after Task 8 lands.
- **Working branch:** `dev_coc`. Only `main` deploys.
- Run Python with `PYTHONPATH=C:/Users/michi/Desktop/CodingStuff/coc_stats` and cwd `coc_stats`.
- Scratchpad for verification scripts: `C:/Users/michi/AppData/Local/Temp/claude/C--Users-michi-Desktop-CodingStuff/fe583947-d648-4d47-8783-9ed907f3f751/scratchpad/`

### Why synthetic fixtures, not database assertions

The dev database gains a new Ranked season every week, so any assertion hard-coded to a
live aggregate rots within days. Tasks 1-5 therefore assert against `SimpleNamespace`
fixtures that mimic `RankedWeek` and `RankedBattleLog`, giving exact, permanent
assertions. Task 8 runs the real database once as a smoke check, asserting only
structural invariants (never exact means).

## File Structure

| File | Responsibility |
|---|---|
| `coc_stats/features/ranked/stats.py` | **Create.** All aggregation, as pure functions. No Flask, no DB session. |
| `coc_stats/features/ranked/routes.py` | **Modify.** Replace the body of `ranked_stats_page` (currently lines 300-588). Add cache wrapper. |
| `coc_stats/templates/ranked/ranked_stats.html` | **Replace.** Four zones. |
| scratchpad `verify_stats_*.py` | Throwaway verification scripts, one per task. Never committed. |

---

### Task 1: Season windowing and per-week records

**Files:**
- Create: `coc_stats/features/ranked/stats.py`
- Test: scratchpad `verify_stats_1.py`

**Interfaces:**
- Consumes: `_calc_ranked_score`, `_ranked_verdict`, `_get_league_rank` from `services/helpers.py`
- Produces:
  - `WINDOWS: dict[str, int | None]`
  - `select_seasons(weeks, window) -> list[str]`
  - `build_week_records(weeks, season_ids) -> dict[str, list[dict]]`
  - Each week record dict has keys: `season_id, start_day, score, badge, label, attacks_used, max_attacks, townhall, league_tier, league_rank, trophies, rank`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_1.py`:

```python
# -*- coding: utf-8 -*-
import datetime as dt
from types import SimpleNamespace as NS
from features.ranked.stats import WINDOWS, select_seasons, build_week_records


def log(attack, stars, pct=0, opp_th=15):
    return NS(attack=attack, stars=stars, percentage=pct, opponent_th=opp_th,
              trophies=0, league_season_id='s', player_tag='#A')


def week(sid, day, done=True, tag='#A', th=15, maxa=12, used=12, tier='Titan League 25',
         logs=None, trophies=500, rank=10):
    return NS(league_season_id=sid, start_day=dt.date(2026, 5, day), is_done=done,
              player_tag=tag, townhall=th, max_attacks=maxa, attack_wins=used,
              attack_losses=0, league_tier=tier, trophies=trophies, rank=rank,
              battle_logs=logs or [])


# --- select_seasons ---
weeks = [week('s3', 20), week('s1', 4), week('s2', 11), week('s4', 25, done=False)]
assert select_seasons(weeks, 'all') == ['s1', 's2', 's3'], 'incomplete season must be excluded, order oldest-first'
assert select_seasons(weeks, '4') == ['s1', 's2', 's3'], 'window larger than data returns all'
assert WINDOWS['all'] is None

weeks10 = [week('s%d' % i, i + 1) for i in range(1, 9)]
assert select_seasons(weeks10, '4') == ['s5', 's6', 's7', 's8'], 'window keeps the most recent N'

# --- build_week_records ---
perfect = [log(True, 3, 100, 15) for _ in range(12)]
recs = build_week_records([week('s1', 4, logs=perfect)], ['s1'])
assert list(recs) == ['#A']
r = recs['#A'][0]
assert r['score'] == 100, 'twelve even-TH triples on 12 max attacks is a perfect score, got %r' % r['score']
assert r['badge'] == 'badge-godlike'
assert r['label'] == 'Godlike', 'label must be stripped of the missing-attacks suffix'
assert r['attacks_used'] == 12
assert r['league_rank'] == 25
assert r['townhall'] == 15

# attacks_used comes from ranked_week, NOT from the log count
half = [log(True, 3, 100, 15) for _ in range(6)]
r2 = build_week_records([week('s1', 4, used=6, logs=half)], ['s1'])['#A'][0]
assert r2['attacks_used'] == 6
assert r2['score'] == 50, 'six of twelve triples halves the score, got %r' % r2['score']
assert 'missing' in r2['label'].lower() or r2['label'] == 'Bad', r2['label']

# ordering follows season_ids, not input order
multi = [week('s2', 11, logs=perfect), week('s1', 4, logs=perfect)]
ordered = build_week_records(multi, ['s1', 's2'])['#A']
assert [x['season_id'] for x in ordered] == ['s1', 's2']

# seasons outside the window are dropped
assert build_week_records(multi, ['s2'])['#A'][0]['season_id'] == 's2'

print('TASK 1 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
export PYTHONPATH="C:/Users/michi/Desktop/CodingStuff/coc_stats"
cd "C:/Users/michi/Desktop/CodingStuff/coc_stats"
python "<scratchpad>/verify_stats_1.py"
```

Expected: `ModuleNotFoundError: No module named 'features.ranked.stats'`

- [ ] **Step 3: Write the implementation**

Create `coc_stats/features/ranked/stats.py`:

```python
"""Pure aggregation for the long-term Ranked record page (/ranked/stats).

Every function here takes ORM rows (or plain objects shaped like them) and
returns plain dicts. No Flask, no DB session, no template concerns — so the
whole module is verifiable from a standalone script with synthetic fixtures.

Scoring is never reimplemented; it comes from services.helpers.
"""

import datetime as dt
import statistics

from services.helpers import (
    _calc_ranked_score,
    _get_league_rank,
    _is_attack,
    _ranked_verdict,
)

# ── Tunable thresholds ────────────────────────────────────────────────────────
WINDOWS               = {'all': None, '12': 12, '4': 4}
DEFAULT_WINDOW        = 'all'

TREND_BAND            = 8.0     # points of score that qualify as surging / sliding
UNRELIABLE_SIGMA      = 15.0    # sigma at or above this is "erratic" / Unreliable
ABSENT_ATTENDANCE     = 0.50    # attendance below this is "not participating"
FORM_BAND             = 2.0     # clan-mean delta that separates holding from moving
GOOD_BAND_CUTOFF      = 58      # _ranked_verdict's "Good" floor, for roster depth

MIN_WEEKS_FOR_TREND   = 4       # trend and sigma are meaningless below this
MIN_WEEKS_FOR_RANKING = 3       # fewer than this drops to the "not enough data" tail

DEFENSE_BAND_MIN_N    = 250     # defenses needed before a league band is trusted
MATCHUP_MIN_N         = 10      # attacks needed before a TH bucket is rendered
NEAR_MISS_PCT         = 90      # 2-star at or above this destruction is a near-miss

LEGEND_RANK_FLOOR     = 34      # _get_league_rank returns 34/35/36 for Legend III/II/I

RELIABILITY_BANDS = ((5.0, 'metronome'), (10.0, 'steady'), (15.0, 'swingy'),
                     (None, 'erratic'))


def select_seasons(weeks, window):
    """Completed season ids, oldest first, trimmed to the requested window."""
    first_day = {}
    for w in weeks:
        if not w.is_done:
            continue
        sid = w.league_season_id
        day = w.start_day or dt.date.min
        if sid not in first_day or day < first_day[sid]:
            first_day[sid] = day
    ordered = sorted(first_day, key=lambda s: (first_day[s], s))
    limit = WINDOWS.get(window)
    return ordered[-limit:] if limit else ordered


def build_week_records(weeks, season_ids):
    """{player_tag: [week record, ...]} ordered to match season_ids.

    attacks_used comes from ranked_week (attack_wins + attack_losses), not from
    counting battle logs: the logs are a rolling API sample and can be short,
    while the week row is authoritative.
    """
    wanted = set(season_ids)
    out = {}
    for w in weeks:
        if not w.is_done or w.league_season_id not in wanted:
            continue
        max_attacks = w.max_attacks or 0
        used = (w.attack_wins or 0) + (w.attack_losses or 0)
        tier = w.league_tier or ''
        score, _, _ = _calc_ranked_score(w.battle_logs, w.townhall or 0, max_attacks, tier)
        badge, label, _ = _ranked_verdict(score, used, max_attacks)
        out.setdefault(w.player_tag, []).append({
            'season_id':    w.league_season_id,
            'start_day':    w.start_day,
            'score':        score,
            'badge':        badge,
            'label':        label.split(' (')[0],
            'attacks_used': used,
            'max_attacks':  max_attacks,
            'townhall':     w.townhall or 0,
            'league_tier':  tier,
            'league_rank':  _get_league_rank(tier),
            'trophies':     w.trophies or 0,
            'rank':         w.rank,
        })
    order = {sid: i for i, sid in enumerate(season_ids)}
    for records in out.values():
        records.sort(key=lambda r: order[r['season_id']])
    return out
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_1.py"
```

Expected: `TASK 1 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/features/ranked/stats.py
git commit -m "feat(ranked): add pure stats module — season windowing and week records"
```

---

### Task 2: Per-player aggregates

**Files:**
- Modify: `coc_stats/features/ranked/stats.py` (append)
- Test: scratchpad `verify_stats_2.py`

**Interfaces:**
- Consumes: week record dicts from Task 1
- Produces:
  - `reliability_word(sigma) -> str`
  - `score_trend(scores) -> float | None`
  - `player_aggregate(records) -> dict` with keys `weeks_played, mean, sigma, reliability, trend, attendance, attacks_used, attacks_max, attacks_wasted, league_move, league_now, league_rank_now, best, worst, verdict_record`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_2.py`:

```python
# -*- coding: utf-8 -*-
from features.ranked.stats import reliability_word, score_trend, player_aggregate


def rec(score, used=12, maxa=12, rank=25, tier='Titan League 25', badge='badge-wow'):
    return {'season_id': 's', 'start_day': None, 'score': score, 'badge': badge,
            'label': 'Very Good', 'attacks_used': used, 'max_attacks': maxa,
            'townhall': 15, 'league_tier': tier, 'league_rank': rank,
            'trophies': 500, 'rank': 10}


# --- reliability_word: boundaries are exclusive at the top of each band ---
assert reliability_word(0.0) == 'metronome'
assert reliability_word(4.9) == 'metronome'
assert reliability_word(5.0) == 'steady'
assert reliability_word(9.9) == 'steady'
assert reliability_word(10.0) == 'swingy'
assert reliability_word(14.9) == 'swingy'
assert reliability_word(15.0) == 'erratic'
assert reliability_word(99.0) == 'erratic'

# --- score_trend ---
assert score_trend([50, 50, 50]) is None, 'below 4 weeks there is no trend'
assert score_trend([]) is None
assert score_trend([40, 40, 60, 60]) == 20.0, 'n=4 uses last two minus first two'
assert score_trend([40, 40, 0, 60, 60]) == 20.0, 'n=5 ignores the middle'
assert score_trend([10, 10, 10, 20, 20, 20]) == 10.0, 'n=6 uses last three minus prior three'
assert score_trend([20, 20, 20, 10, 10, 10]) == -10.0
assert score_trend([0, 0, 0, 10, 10, 10, 20, 20, 20]) == 10.0, 'n>6 uses only the last six'

# --- player_aggregate ---
a = player_aggregate([rec(80), rec(80), rec(80), rec(80)])
assert a['weeks_played'] == 4
assert a['mean'] == 80.0
assert a['sigma'] == 0.0, 'a flat series has zero spread'
assert a['reliability'] == 'metronome'
assert a['trend'] == 0.0
assert a['attendance'] == 1.0
assert a['attacks_wasted'] == 0
assert a['best'] == 80 and a['worst'] == 80
assert a['verdict_record'] == {'badge-wow': 4}
assert sum(a['verdict_record'].values()) == a['weeks_played'], 'verdict record must account for every week'

# single week: sigma is 0, trend is None, nothing divides by zero
one = player_aggregate([rec(70)])
assert one['sigma'] == 0.0 and one['trend'] is None and one['weeks_played'] == 1

# attendance is attacks_used over max_attacks, summed across weeks
part = player_aggregate([rec(50, used=6, maxa=12), rec(50, used=12, maxa=12)])
assert part['attendance'] == 0.75, part['attendance']
assert part['attacks_used'] == 18 and part['attacks_max'] == 24 and part['attacks_wasted'] == 6

# zero max_attacks must not raise
zero = player_aggregate([rec(0, used=0, maxa=0)])
assert zero['attendance'] == 0.0

# league_move spans first-played to last-played, not calendar bounds
climb = player_aggregate([rec(70, rank=20, tier='Golem League 20'),
                          rec(70, rank=28, tier='Dragon League 28')])
assert climb['league_move'] == 8
assert climb['league_now'] == 'Dragon League 28'
assert climb['league_rank_now'] == 28

# an unranked week (rank 0) is skipped when locating first/last played
gap = player_aggregate([rec(70, rank=0, tier=''),
                        rec(70, rank=20, tier='Golem League 20'),
                        rec(70, rank=25, tier='Titan League 25')])
assert gap['league_move'] == 5, gap['league_move']

print('TASK 2 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_stats_2.py"
```

Expected: `ImportError: cannot import name 'reliability_word'`

- [ ] **Step 3: Write the implementation**

Append to `coc_stats/features/ranked/stats.py`:

```python
def reliability_word(sigma):
    """Sigma rendered as a word. Bands are exclusive at the top."""
    for cutoff, word in RELIABILITY_BANDS:
        if cutoff is None or sigma < cutoff:
            return word
    return 'erratic'


def score_trend(scores):
    """Points of score gained or lost, comparing recent weeks to earlier ones.

    Returns None below MIN_WEEKS_FOR_TREND — a two-week 'trend' is noise.
    """
    n = len(scores)
    if n >= 6:
        return round(sum(scores[-3:]) / 3 - sum(scores[-6:-3]) / 3, 1)
    if n >= MIN_WEEKS_FOR_TREND:
        return round(sum(scores[-2:]) / 2 - sum(scores[:2]) / 2, 1)
    return None


def player_aggregate(records):
    """Window-level summary for one player, from their ordered week records."""
    scores = [r['score'] for r in records]
    n = len(scores)
    mean = round(sum(scores) / n, 1) if n else 0.0
    sigma = round(statistics.pstdev(scores), 1) if n > 1 else 0.0

    attacks_max = sum(r['max_attacks'] for r in records)
    attacks_used = sum(r['attacks_used'] for r in records)

    ranked_weeks = [r for r in records if r['league_rank']]

    verdict_record = {}
    for r in records:
        verdict_record[r['badge']] = verdict_record.get(r['badge'], 0) + 1

    return {
        'weeks_played':    n,
        'mean':            mean,
        'sigma':           sigma,
        'reliability':     reliability_word(sigma),
        'trend':           score_trend(scores),
        'attendance':      round(attacks_used / attacks_max, 4) if attacks_max else 0.0,
        'attacks_used':    attacks_used,
        'attacks_max':     attacks_max,
        'attacks_wasted':  attacks_max - attacks_used,
        'league_move':     (ranked_weeks[-1]['league_rank'] - ranked_weeks[0]['league_rank'])
                           if ranked_weeks else 0,
        'league_now':      ranked_weeks[-1]['league_tier'] if ranked_weeks else '',
        'league_rank_now': ranked_weeks[-1]['league_rank'] if ranked_weeks else 0,
        'best':            max(scores) if scores else 0,
        'worst':           min(scores) if scores else 0,
        'verdict_record':  verdict_record,
    }
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_2.py"
```

Expected: `TASK 2 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/features/ranked/stats.py
git commit -m "feat(ranked): add per-player long-term aggregates"
```

---

### Task 3: League-normalized defense axis

**Files:**
- Modify: `coc_stats/features/ranked/stats.py` (append)
- Test: scratchpad `verify_stats_3.py`

**Interfaces:**
- Consumes: week records (Task 1); a `defense_logs_by_key` mapping `{(player_tag, season_id): [log, ...]}` containing defense logs only, each with a `.trophies` attribute
- Produces:
  - `defense_band(league_rank) -> str`
  - `build_defense_expectations(week_records_by_tag, defense_logs_by_key) -> dict`
  - `player_defense(tag, records, defense_logs_by_key, expectations) -> dict` with keys `n, tpd, index, thin`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_3.py`:

```python
# -*- coding: utf-8 -*-
from types import SimpleNamespace as NS
from features.ranked.stats import (
    DEFENSE_BAND_MIN_N, defense_band, build_defense_expectations, player_defense,
)


def rec(sid, rank, tier='x'):
    return {'season_id': sid, 'start_day': None, 'score': 70, 'badge': 'badge-wow',
            'label': 'Very Good', 'attacks_used': 12, 'max_attacks': 12,
            'townhall': 15, 'league_tier': tier, 'league_rank': rank,
            'trophies': 500, 'rank': 10}


def d(t):
    return NS(trophies=t)


# --- defense_band ---
assert defense_band(0) == 'unranked'
assert defense_band(1) == '1-5'
assert defense_band(5) == '1-5'
assert defense_band(6) == '6-10'
assert defense_band(16) == '16-20'
assert defense_band(20) == '16-20'
assert defense_band(31) == '31-35'
assert defense_band(33) == '31-35', 'the highest numbered league is 33 and lands in 31-35'
assert defense_band(34) == 'legend'
assert defense_band(36) == 'legend'

# --- build_defense_expectations: a well-populated band keeps its own mean ---
fat = DEFENSE_BAND_MIN_N + 10
records = {'#A': [rec('s1', 25)]}
logs = {('#A', 's1'): [d(20)] * fat}
exp = build_defense_expectations(records, logs)
assert exp['21-25']['n'] == fat
assert exp['21-25']['mean'] == 20.0
assert exp['21-25']['thin'] is False
assert exp['_global']['mean'] == 20.0

# --- a thin band falls back to the global mean and is flagged ---
records = {'#A': [rec('s1', 25)], '#B': [rec('s2', 2)]}
logs = {('#A', 's1'): [d(20)] * fat, ('#B', 's2'): [d(40)] * 5}
exp = build_defense_expectations(records, logs)
assert exp['1-5']['n'] == 5
assert exp['1-5']['thin'] is True
assert exp['1-5']['mean'] == exp['_global']['mean'], 'thin bands must use the global mean'
assert exp['21-25']['thin'] is False
assert exp['21-25']['mean'] == 20.0

# --- player_defense: index is measured against the band, not the global mean ---
pd = player_defense('#A', records['#A'], logs, exp)
assert pd['n'] == fat
assert pd['tpd'] == 20.0
assert pd['index'] == 0.0, 'a player exactly at band expectation indexes to zero'
assert pd['thin'] is False

# a player above their band indexes positive
logs2 = dict(logs)
logs2[('#C', 's1')] = [d(30)] * 10
pd2 = player_defense('#C', [rec('s1', 25)], logs2, exp)
assert pd2['index'] == 10.0, pd2['index']

# a player with no logged defenses returns nulls rather than dividing by zero
pd3 = player_defense('#Z', [rec('s1', 25)], {}, exp)
assert pd3 == {'n': 0, 'tpd': None, 'index': None, 'thin': True}

# a player whose weeks sit in a thin band inherits the thin flag
pd4 = player_defense('#B', records['#B'], logs, exp)
assert pd4['thin'] is True

print('TASK 3 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_stats_3.py"
```

Expected: `ImportError: cannot import name 'defense_band'`

- [ ] **Step 3: Write the implementation**

Append to `coc_stats/features/ranked/stats.py`:

```python
def defense_band(league_rank):
    """League-rank band used to normalize defense.

    Holding a base gets much harder as you climb (clan data: mean trophies per
    defense falls from 17.3 in band 16-20 to 6.7 in band 31-35), so raw
    cross-league comparison is invalid.
    """
    if not league_rank:
        return 'unranked'
    if league_rank >= LEGEND_RANK_FLOOR:
        return 'legend'
    low = ((league_rank - 1) // 5) * 5 + 1
    return '%d-%d' % (low, low + 4)


def build_defense_expectations(week_records_by_tag, defense_logs_by_key):
    """Expected trophies-per-defense per league band, across the whole clan.

    Bands with fewer than DEFENSE_BAND_MIN_N defenses fall back to the global
    mean and are flagged thin, rather than presenting a noisy band mean as if
    it were precise.
    """
    buckets = {}
    for tag, records in week_records_by_tag.items():
        for r in records:
            band = defense_band(r['league_rank'])
            for log in defense_logs_by_key.get((tag, r['season_id']), ()):
                buckets.setdefault(band, []).append(log.trophies or 0)

    every = [v for values in buckets.values() for v in values]
    global_mean = round(sum(every) / len(every), 2) if every else 0.0

    expectations = {}
    for band, values in buckets.items():
        thin = len(values) < DEFENSE_BAND_MIN_N
        expectations[band] = {
            'n':    len(values),
            'mean': global_mean if thin else round(sum(values) / len(values), 2),
            'thin': thin,
        }
    expectations['_global'] = {'n': len(every), 'mean': global_mean, 'thin': False}
    return expectations


def player_defense(tag, records, defense_logs_by_key, expectations):
    """One player's defense quality against what their leagues expected."""
    fallback = expectations['_global']
    values, expected, thin = [], [], False
    for r in records:
        band = expectations.get(defense_band(r['league_rank']), fallback)
        logs = defense_logs_by_key.get((tag, r['season_id']), ())
        if logs and band.get('thin'):
            thin = True
        for log in logs:
            values.append(log.trophies or 0)
            expected.append(band['mean'])

    if not values:
        return {'n': 0, 'tpd': None, 'index': None, 'thin': True}

    tpd = round(sum(values) / len(values), 1)
    return {
        'n':     len(values),
        'tpd':   tpd,
        'index': round(tpd - sum(expected) / len(expected), 1),
        'thin':  thin,
    }
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_3.py"
```

Expected: `TASK 3 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/features/ranked/stats.py
git commit -m "feat(ranked): add league-normalized defense axis"
```

---

### Task 4: Clan form and Movers bands

**Files:**
- Modify: `coc_stats/features/ranked/stats.py` (append)
- Test: scratchpad `verify_stats_4.py`

**Interfaces:**
- Consumes: week records (Task 1), aggregate rows (Task 2)
- Produces:
  - `clan_form(week_records_by_tag, season_ids, labels) -> dict` with keys `points, delta, direction, current, peak_mean, peak_label, vs_peak, depth`
  - `movers(rows) -> dict` with keys `surging, sliding, unreliable, absent`
  - A "row" is a player aggregate dict (Task 2) plus `player_tag` and `player_name`.

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_4.py`:

```python
# -*- coding: utf-8 -*-
from features.ranked.stats import clan_form, movers


def rec(sid, score):
    return {'season_id': sid, 'start_day': None, 'score': score, 'badge': 'badge-wow',
            'label': 'Very Good', 'attacks_used': 12, 'max_attacks': 12, 'townhall': 15,
            'league_tier': 'Titan League 25', 'league_rank': 25, 'trophies': 500, 'rank': 10}


def row(tag, mean=70.0, sigma=3.0, trend=0.0, attendance=1.0, weeks=9):
    return {'player_tag': tag, 'player_name': tag.strip('#'), 'mean': mean,
            'sigma': sigma, 'trend': trend, 'attendance': attendance,
            'weeks_played': weeks}


sids = ['s1', 's2', 's3', 's4', 's5', 's6']
labels = {s: s.upper() for s in sids}

# --- clan_form: rising clan ---
rising = {'#A': [rec(s, v) for s, v in zip(sids, [50, 50, 50, 70, 70, 70])]}
form = clan_form(rising, sids, labels, depth_source=[row('#A', mean=70.0)])
assert [p['mean'] for p in form['points']] == [50.0, 50.0, 50.0, 70.0, 70.0, 70.0]
assert form['points'][0]['label'] == 'S1'
assert form['points'][0]['participants'] == 1
assert form['delta'] == 20.0
assert form['direction'] == 'climbing'
assert form['current'] == 70.0
assert form['peak_mean'] == 70.0
assert form['vs_peak'] == 0.0

# --- falling clan, currently below its peak ---
falling = {'#A': [rec(s, v) for s, v in zip(sids, [70, 70, 70, 50, 50, 50])]}
f2 = clan_form(falling, sids, labels, depth_source=[])
assert f2['delta'] == -20.0
assert f2['direction'] == 'slipping'
assert f2['peak_mean'] == 70.0
assert f2['peak_label'] == 'S1'
assert f2['vs_peak'] == -20.0

# --- flat clan holds ---
flat = {'#A': [rec(s, 60) for s in sids]}
assert clan_form(flat, sids, labels, depth_source=[])['direction'] == 'holding'

# --- a season with no data is skipped, not rendered as zero ---
sparse = {'#A': [rec('s1', 60), rec('s3', 60)]}
pts = clan_form(sparse, ['s1', 's2', 's3'], {'s1': 'A', 's2': 'B', 's3': 'C'},
                depth_source=[])['points']
assert [p['season_id'] for p in pts] == ['s1', 's3']

# --- empty input must not raise ---
empty = clan_form({}, [], {}, depth_source=[])
assert empty['points'] == [] and empty['direction'] == 'holding'

# --- depth counts players at or above the Good cutoff (58) ---
depth = clan_form(flat, sids, labels,
                  depth_source=[row('#A', mean=90.0), row('#B', mean=58.0),
                                row('#C', mean=57.9)])
assert depth['depth'] == 2, depth['depth']

# --- movers ---
rows = [
    row('#surge',  trend=12.0),
    row('#slide',  trend=-12.0),
    row('#steady', trend=1.0),
    row('#wild',   trend=0.0, sigma=20.0),
    row('#gone',   trend=-30.0, sigma=25.0, attendance=0.10),
    row('#new',    trend=None, weeks=2),
    row('#edge',   trend=8.0),
]
m = movers(rows)
assert [r['player_tag'] for r in m['surging']] == ['#surge', '#edge'], 'threshold is inclusive, sorted by trend desc'
assert [r['player_tag'] for r in m['sliding']] == ['#slide']
assert [r['player_tag'] for r in m['unreliable']] == ['#wild']
assert [r['player_tag'] for r in m['absent']] == ['#gone']

# an absent player is listed ONLY under absent, even though they also slide and swing
for band in ('surging', 'sliding', 'unreliable'):
    assert '#gone' not in [r['player_tag'] for r in m[band]], band

# a player below the trend minimum appears in no computed band
for band in ('surging', 'sliding', 'unreliable'):
    assert '#new' not in [r['player_tag'] for r in m[band]], band

# empty bands are empty lists, not None
assert movers([])['surging'] == []

print('TASK 4 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_stats_4.py"
```

Expected: `ImportError: cannot import name 'clan_form'`

- [ ] **Step 3: Write the implementation**

Append to `coc_stats/features/ranked/stats.py`:

```python
def clan_form(week_records_by_tag, season_ids, labels, depth_source):
    """Clan mean score per season, plus a verdict on direction.

    depth_source is the list of player aggregate rows; depth counts how many
    clear the Good verdict band on their window mean.
    """
    by_season = {}
    for records in week_records_by_tag.values():
        for r in records:
            by_season.setdefault(r['season_id'], []).append(r['score'])

    points = []
    for sid in season_ids:
        scores = by_season.get(sid)
        if not scores:
            continue
        points.append({
            'season_id':    sid,
            'label':        labels.get(sid, sid),
            'mean':         round(sum(scores) / len(scores), 1),
            'participants': len(scores),
        })

    means = [p['mean'] for p in points]
    if len(means) >= 6:
        delta = round(sum(means[-3:]) / 3 - sum(means[-6:-3]) / 3, 1)
    elif len(means) >= 2:
        delta = round(means[-1] - means[0], 1)
    else:
        delta = 0.0

    if delta >= FORM_BAND:
        direction = 'climbing'
    elif delta <= -FORM_BAND:
        direction = 'slipping'
    else:
        direction = 'holding'

    peak = max(points, key=lambda p: p['mean']) if points else None
    return {
        'points':     points,
        'delta':      delta,
        'direction':  direction,
        'current':    points[-1]['mean'] if points else 0.0,
        'peak_mean':  peak['mean'] if peak else 0.0,
        'peak_label': peak['label'] if peak else '',
        'vs_peak':    round(points[-1]['mean'] - peak['mean'], 1) if points else 0.0,
        'depth':      sum(1 for r in depth_source if r['mean'] >= GOOD_BAND_CUTOFF),
    }


def movers(rows):
    """The four exception bands.

    Absent is computed first and its members are excluded from the other three:
    a player who did not attack is not "sliding", they are not playing, and
    that is the fact leadership needs.
    """
    absent = [r for r in rows if r['attendance'] < ABSENT_ATTENDANCE]
    absent_tags = {r['player_tag'] for r in absent}

    eligible = [r for r in rows
                if r['player_tag'] not in absent_tags
                and r['weeks_played'] >= MIN_WEEKS_FOR_TREND]

    return {
        'surging':    sorted([r for r in eligible
                              if r['trend'] is not None and r['trend'] >= TREND_BAND],
                             key=lambda r: -r['trend']),
        'sliding':    sorted([r for r in eligible
                              if r['trend'] is not None and r['trend'] <= -TREND_BAND],
                             key=lambda r: r['trend']),
        'unreliable': sorted([r for r in eligible if r['sigma'] >= UNRELIABLE_SIGMA],
                             key=lambda r: -r['sigma']),
        'absent':     sorted(absent, key=lambda r: r['attendance']),
    }
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_4.py"
```

Expected: `TASK 4 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/features/ranked/stats.py
git commit -m "feat(ranked): add clan form verdict and movers exception bands"
```

---

### Task 5: Drill-down aggregates

**Files:**
- Modify: `coc_stats/features/ranked/stats.py` (append)
- Test: scratchpad `verify_stats_5.py`

**Interfaces:**
- Consumes: week records (Task 1); attack logs with `.stars`, `.percentage`, `.opponent_th`, `.league_season_id`
- Produces:
  - `matchup_buckets(attack_logs, th_by_season) -> dict[int, dict]` keyed −2..+2
  - `near_misses(attack_logs) -> dict`
  - `career_markers(records) -> list[dict]`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_5.py`:

```python
# -*- coding: utf-8 -*-
from types import SimpleNamespace as NS
from features.ranked.stats import (
    MATCHUP_MIN_N, matchup_buckets, near_misses, career_markers,
)


def atk(stars, pct, opp_th, sid='s1'):
    return NS(stars=stars, percentage=pct, opponent_th=opp_th,
              league_season_id=sid, attack=True)


def rec(sid, th, rank, tier):
    return {'season_id': sid, 'start_day': None, 'score': 70, 'badge': 'badge-wow',
            'label': 'Very Good', 'attacks_used': 12, 'max_attacks': 12,
            'townhall': th, 'league_tier': tier, 'league_rank': rank,
            'trophies': 500, 'rank': 10}


# --- matchup_buckets: ends are open, so -3 folds into -2 and +3 into +2 ---
th = {'s1': 15}
logs = ([atk(3, 100, 12)] * 2 +            # diff -3 -> bucket -2
        [atk(3, 100, 13)] * 3 +            # diff -2 -> bucket -2
        [atk(2, 90, 14)] * 4 +             # diff -1
        [atk(3, 100, 15)] * MATCHUP_MIN_N +  # diff 0, enough
        [atk(1, 50, 18)] * 2)              # diff +3 -> bucket +2
b = matchup_buckets(logs, th)
assert set(b) == {-2, -1, 0, 2}
assert b[-2]['attacks'] == 5, b[-2]['attacks']
assert b[2]['attacks'] == 2
assert b[0]['attacks'] == MATCHUP_MIN_N
assert b[0]['avg_stars'] == 3.0
assert b[0]['avg_pct'] == 100.0
assert b[0]['enough'] is True, 'a bucket at the minimum is enough'
assert b[-1]['enough'] is False, 'four attacks is not enough to render a bucket'

# a log whose season has no town hall on record is skipped
assert matchup_buckets([atk(3, 100, 15, sid='unknown')], th) == {}

# an unparseable opponent TH is treated as an even matchup, not dropped
weird = matchup_buckets([NS(stars=3, percentage=100, opponent_th=None,
                            league_season_id='s1', attack=True)], th)
assert weird[0]['attacks'] == 1

# --- near_misses ---
nm = near_misses([atk(3, 100, 15)] * 6 + [atk(2, 95, 15)] * 3 + [atk(2, 70, 15)])
assert nm['attacks'] == 10
assert nm['three'] == 6 and nm['three_pct'] == 60.0
assert nm['near'] == 3, 'only 2-star at or above 90 percent counts'
assert nm['near_pct'] == 30.0
assert near_misses([])['near_pct'] == 0.0, 'no attacks must not divide by zero'

# a 2-star exactly at the threshold counts
assert near_misses([atk(2, 90, 15)])['near'] == 1
assert near_misses([atk(2, 89, 15)])['near'] == 0

# --- career_markers ---
records = [rec('s1', 15, 20, 'Golem League 20'),
           rec('s2', 15, 22, 'P.E.K.K.A League 22'),
           rec('s3', 16, 22, 'P.E.K.K.A League 22'),
           rec('s4', 16, 20, 'Golem League 20')]
marks = career_markers(records)
kinds = [(m['season_id'], m['kind']) for m in marks]
assert ('s2', 'promotion') in kinds
assert ('s3', 'townhall') in kinds
assert ('s4', 'demotion') in kinds
assert not [m for m in marks if m['season_id'] == 's1'], 'the first week is the baseline, not a change'
assert career_markers([]) == []
assert career_markers([rec('s1', 15, 20, 'Golem League 20')]) == []

th_mark = [m for m in marks if m['kind'] == 'townhall'][0]
assert th_mark['detail'] == 'TH15 -> TH16', th_mark['detail']

print('TASK 5 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_stats_5.py"
```

Expected: `ImportError: cannot import name 'matchup_buckets'`

- [ ] **Step 3: Write the implementation**

Append to `coc_stats/features/ranked/stats.py`:

```python
def matchup_buckets(attack_logs, th_by_season):
    """Attack performance per town-hall matchup, bucketed -2..+2 with open ends.

    A bucket below MATCHUP_MIN_N is still returned but flagged not-enough, so
    the page can say "you have only faced even matchups" rather than render a
    confident number over three attacks.
    """
    buckets = {}
    for log in attack_logs:
        own = th_by_season.get(log.league_season_id)
        if not own:
            continue
        try:
            opponent = int(log.opponent_th)
        except (TypeError, ValueError):
            opponent = own
        diff = opponent - own
        key = -2 if diff <= -2 else (2 if diff >= 2 else diff)
        bucket = buckets.setdefault(key, {'attacks': 0, '_stars': 0, '_pct': 0})
        bucket['attacks'] += 1
        bucket['_stars'] += log.stars or 0
        bucket['_pct'] += log.percentage or 0

    for bucket in buckets.values():
        n = bucket['attacks']
        bucket['avg_stars'] = round(bucket.pop('_stars') / n, 2)
        bucket['avg_pct'] = round(bucket.pop('_pct') / n, 1)
        bucket['enough'] = n >= MATCHUP_MIN_N
    return buckets


def near_misses(attack_logs):
    """Attacks that were one building short of a three-star."""
    total = len(attack_logs)
    near = sum(1 for l in attack_logs
               if (l.stars or 0) == 2 and (l.percentage or 0) >= NEAR_MISS_PCT)
    three = sum(1 for l in attack_logs if (l.stars or 0) == 3)
    return {
        'attacks':   total,
        'near':      near,
        'three':     three,
        'near_pct':  round(near / total * 100, 1) if total else 0.0,
        'three_pct': round(three / total * 100, 1) if total else 0.0,
    }


def career_markers(records):
    """Town-hall upgrades and league promotions/demotions along a career line.

    The first week is the baseline and never produces a marker.
    """
    markers = []
    for previous, current in zip(records, records[1:]):
        if current['townhall'] and previous['townhall'] and current['townhall'] != previous['townhall']:
            markers.append({
                'season_id': current['season_id'],
                'kind':      'townhall',
                'detail':    'TH%d -> TH%d' % (previous['townhall'], current['townhall']),
            })
        if current['league_rank'] and previous['league_rank'] and current['league_rank'] != previous['league_rank']:
            markers.append({
                'season_id': current['season_id'],
                'kind':      'promotion' if current['league_rank'] > previous['league_rank'] else 'demotion',
                'detail':    '%s -> %s' % (previous['league_tier'], current['league_tier']),
            })
    return markers
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_5.py"
```

Expected: `TASK 5 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/features/ranked/stats.py
git commit -m "feat(ranked): add drill-down aggregates — matchups, near-misses, career markers"
```

---

### Task 6: Page assembler, cache, and route rewire

**Files:**
- Modify: `coc_stats/features/ranked/stats.py` (append `build_record_page`)
- Modify: `coc_stats/features/ranked/routes.py` — replace the body of `ranked_stats_page` (lines 300-588)
- Test: scratchpad `verify_stats_6.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5
- Produces: `build_record_page(clan_players, weeks, window) -> dict` with keys `window, seasons, labels, form, movers, roster, tail_thin, tail_absent, players`
  - `clan_players` is a list of `Player` rows (needs `.tag`, `.name`)
  - `weeks` is a list of `RankedWeek` rows with `battle_logs` eager-loaded
  - `players` maps `player_tag -> {records, markers, matchups, near, defense, attendance_weeks}`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_stats_6.py`:

```python
# -*- coding: utf-8 -*-
import datetime as dt
from types import SimpleNamespace as NS
from features.ranked.stats import build_record_page, MIN_WEEKS_FOR_RANKING


def log(sid, attack, stars, pct=100, opp_th=15, troph=40):
    # league_season_id matters: matchup_buckets maps a log back to the town hall
    # the player had that season, so it must be built per-season, not shared.
    return NS(attack=attack, stars=stars, percentage=pct, opponent_th=opp_th,
              trophies=troph, league_season_id=sid)


def strong_logs(sid):
    return [log(sid, True, 3) for _ in range(12)] + [log(sid, False, 1, 70, 15, 27)]


def weak_logs(sid):
    return [log(sid, True, 1, 40) for _ in range(12)] + [log(sid, False, 3, 100, 15, 0)]


def week(tag, sid, day, logs, used=12, maxa=12, done=True):
    return NS(league_season_id=sid, start_day=dt.date(2026, 5, day), is_done=done,
              player_tag=tag, townhall=15, max_attacks=maxa, attack_wins=used,
              attack_losses=0, league_tier='Titan League 25', trophies=500,
              rank=10, battle_logs=logs)


players = [NS(tag='#A', name='Ace'), NS(tag='#B', name='Bit'), NS(tag='#C', name='Cy')]

weeks = []
for i, day in enumerate([4, 11, 18, 25], start=1):
    sid = 's%d' % i
    weeks.append(week('#A', sid, day, strong_logs(sid)))
    weeks.append(week('#B', sid, day, weak_logs(sid)))
weeks.append(week('#C', 's1', 4, strong_logs('s1')))                 # too few weeks
weeks.append(week('#A', 's9', 30, strong_logs('s9'), done=False))    # live season

page = build_record_page(players, weeks, 'all')

assert page['window'] == 'all'
assert page['seasons'] == ['s1', 's2', 's3', 's4'], 'the live season must be excluded'
assert 's9' not in page['labels']
assert page['labels']['s1'] == '04.05.26', page['labels']['s1']

# roster is sorted by mean descending and excludes the thin-data player
tags = [r['player_tag'] for r in page['roster']]
assert tags == ['#A', '#B'], tags
assert page['roster'][0]['player_name'] == 'Ace'
assert page['roster'][0]['mean'] > page['roster'][1]['mean']

# thin-data players land in their own tail, never interleaved
assert [r['player_tag'] for r in page['tail_thin']] == ['#C']
assert page['tail_thin'][0]['weeks_played'] < MIN_WEEKS_FOR_RANKING
assert page['tail_absent'] == []

# every roster row carries the defense axis
assert page['roster'][0]['defense']['n'] == 4
assert page['roster'][0]['defense']['index'] is not None

# form covers every season with data
assert len(page['form']['points']) == 4
assert page['form']['direction'] in ('climbing', 'holding', 'slipping')

# drill-down payload exists for every player that has records, thin ones included
assert set(page['players']) == {'#A', '#B', '#C'}
detail = page['players']['#A']
assert len(detail['records']) == 4
assert detail['near']['three_pct'] == 100.0
assert detail['matchups'][0]['attacks'] == 48, detail['matchups'][0]['attacks']
assert detail['markers'] == [], 'a static career has no markers'
assert detail['attendance_weeks'] == [], 'full attendance lists no short weeks'

# a short week is listed on the attendance record
short = [week('#D', 's1', 4, strong_logs('s1'), used=6)]
page2 = build_record_page([NS(tag='#D', name='Dee')], short, 'all')
assert page2['players']['#D']['attendance_weeks'][0]['missing'] == 6

# absent players are held out of the roster and listed in their own tail
absent_weeks = [week('#E', 's%d' % i, d, [log('s%d' % i, False, 3, 100, 15, 0)], used=0)
                for i, d in enumerate([4, 11, 18, 25], start=1)]
page3 = build_record_page([NS(tag='#E', name='Eve')], absent_weeks, 'all')
assert page3['roster'] == []
assert [r['player_tag'] for r in page3['tail_absent']] == ['#E']
assert [r['player_tag'] for r in page3['movers']['absent']] == ['#E']

# an empty clan must not raise
blank = build_record_page([], [], 'all')
assert blank['roster'] == [] and blank['seasons'] == [] and blank['players'] == {}

# a non-clan player in the week data is ignored entirely
outsider = weeks + [week('#ZZ', 's1', 4, strong_logs('s1'))]
assert '#ZZ' not in build_record_page(players, outsider, 'all')['players']

print('TASK 6 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_stats_6.py"
```

Expected: `ImportError: cannot import name 'build_record_page'`

- [ ] **Step 3: Write the assembler**

Append to `coc_stats/features/ranked/stats.py`:

```python
def _split_logs(weeks, in_clan_tags, wanted_seasons):
    """Battle logs split by direction, keyed (player_tag, season_id)."""
    attacks, defenses = {}, {}
    for w in weeks:
        if w.player_tag not in in_clan_tags or w.league_season_id not in wanted_seasons:
            continue
        key = (w.player_tag, w.league_season_id)
        for log in w.battle_logs:
            (attacks if _is_attack(log) else defenses).setdefault(key, []).append(log)
    return attacks, defenses


def build_record_page(clan_players, weeks, window):
    """Everything /ranked/stats renders, from ORM rows to plain dicts."""
    names = {p.tag: (p.name or p.tag) for p in clan_players}
    in_clan = set(names)

    season_ids = select_seasons([w for w in weeks if w.player_tag in in_clan], window)
    wanted = set(season_ids)

    labels = {}
    for w in weeks:
        sid = w.league_season_id
        if sid in wanted and sid not in labels and w.start_day:
            labels[sid] = w.start_day.strftime('%d.%m.%y')
    for sid in season_ids:
        labels.setdefault(sid, sid)

    clan_weeks = [w for w in weeks if w.player_tag in in_clan]
    records_by_tag = build_week_records(clan_weeks, season_ids)
    attack_logs, defense_logs = _split_logs(clan_weeks, in_clan, wanted)
    expectations = build_defense_expectations(records_by_tag, defense_logs)

    rows, details = [], {}
    for tag, records in records_by_tag.items():
        row = player_aggregate(records)
        row['player_tag'] = tag
        row['player_name'] = names[tag]
        row['defense'] = player_defense(tag, records, defense_logs, expectations)
        row['scores'] = [r['score'] for r in records]
        row['seasons'] = [r['season_id'] for r in records]
        rows.append(row)

        player_attacks = [l for key, logs in attack_logs.items() if key[0] == tag
                          for l in logs]
        details[tag] = {
            'records':   records,
            'markers':   career_markers(records),
            'matchups':  matchup_buckets(player_attacks,
                                         {r['season_id']: r['townhall'] for r in records}),
            'near':      near_misses(player_attacks),
            'defense':   row['defense'],
            'attendance_weeks': [
                {'season_id': r['season_id'], 'label': labels.get(r['season_id'], r['season_id']),
                 'used': r['attacks_used'], 'max': r['max_attacks'],
                 'missing': r['max_attacks'] - r['attacks_used']}
                for r in records if r['max_attacks'] > r['attacks_used']
            ],
        }

    bands = movers(rows)
    absent_tags = {r['player_tag'] for r in bands['absent']}

    roster = sorted(
        [r for r in rows
         if r['player_tag'] not in absent_tags and r['weeks_played'] >= MIN_WEEKS_FOR_RANKING],
        key=lambda r: -r['mean'])
    tail_thin = sorted(
        [r for r in rows
         if r['player_tag'] not in absent_tags and r['weeks_played'] < MIN_WEEKS_FOR_RANKING],
        key=lambda r: -r['mean'])

    return {
        'window':      window,
        'seasons':     season_ids,
        'labels':      labels,
        'form':        clan_form(records_by_tag, season_ids, labels, depth_source=roster),
        'movers':      bands,
        'roster':      roster,
        'tail_thin':   tail_thin,
        'tail_absent': bands['absent'],
        'players':     details,
    }
```

Note: `matchup_buckets` returns integer keys, which `json.dumps` renders as
strings. The template reads them as `"-2"`, `"-1"`, `"0"`, `"1"`, `"2"`.

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_stats_6.py"
```

Expected: `TASK 6 OK`

- [ ] **Step 5: Rewire the route**

In `coc_stats/features/ranked/routes.py`, delete the entire body of
`ranked_stats_page` (lines 300-588, from `def ranked_stats_page():` through the
closing `)` of its `render_template` call) and replace with:

```python
_RECORD_CACHE = {}          # (window, roster_hash) -> (expires_at, payload)
_RECORD_TTL   = 300         # seconds


def _record_page_cached(clan_players, window):
    """Clan-wide aggregates are viewer-invariant, so cache per (window, roster)."""
    tags = frozenset(p.tag for p in clan_players)
    key = (window, hash(tags))
    now = dt.datetime.now().timestamp()
    hit = _RECORD_CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]

    weeks = (
        RankedWeek.query
        .filter(RankedWeek.player_tag.in_(tags))
        .options(selectinload(RankedWeek.battle_logs))
        .all()
    ) if tags else []

    payload = build_record_page(clan_players, weeks, window)
    _RECORD_CACHE[key] = (now + _RECORD_TTL, payload)
    return payload


@ranked_bp.route('/ranked/stats')
def ranked_stats_page():
    window = request.args.get('window', DEFAULT_WINDOW)
    if window not in WINDOWS:
        window = DEFAULT_WINDOW

    clan_players = Player.query.filter_by(in_clan=True).all()
    page = _record_page_cached(clan_players, window)

    return render_template(
        'ranked/ranked_stats.html',
        window       = window,
        windows      = list(WINDOWS),
        form         = page['form'],
        movers       = page['movers'],
        roster       = page['roster'],
        tail_thin    = page['tail_thin'],
        tail_absent  = page['tail_absent'],
        labels       = page['labels'],
        seasons      = page['seasons'],
        page_json    = json.dumps(page, default=str),
    )
```

Add to the imports at the top of `routes.py` (keep existing imports intact):

```python
import datetime as dt

from flask import request

from features.ranked.stats import (
    DEFAULT_WINDOW, WINDOWS, build_record_page,
)
```

- [ ] **Step 6: Verify the route responds**

Create scratchpad `verify_route_6.py`:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from app import app

with app.test_client() as c:
    for window in ('all', '12', '4', 'garbage'):
        r = c.get('/ranked/stats?window=%s' % window)
        assert r.status_code == 200, (window, r.status_code)
        print('window=%-8s status=%s bytes=%d' % (window, r.status_code, len(r.data)))
print('ROUTE 6 OK')
```

Run: `python "<scratchpad>/verify_route_6.py"`
Expected: four 200 lines, then `ROUTE 6 OK`. An unknown window must not 500 — it falls back to `all`.

- [ ] **Step 7: Commit**

```bash
git add coc_stats/features/ranked/stats.py coc_stats/features/ranked/routes.py
git commit -m "feat(ranked): assemble record page payload, cache it, rewire the route"
```

---

### Task 7: Template — Zones 1 to 3

**Files:**
- Replace: `coc_stats/templates/ranked/ranked_stats.html`
- Test: scratchpad `verify_route_7.py`

**Interfaces:**
- Consumes: `window`, `windows`, `form`, `movers`, `roster`, `tail_thin`, `tail_absent`, `labels`, `seasons`, `page_json` from Task 6
- Produces: DOM contracts later tasks and `impeccable` rely on — `#form-chart` (canvas), `.mv-band[data-band]`, `#record-table`, `tr.rec-row[data-tag]`, `button.rec-toggle`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_route_7.py`:

```python
# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from app import app

with app.test_client() as c:
    html = c.get('/ranked/stats').get_data(as_text=True)

assert html.count('<style') == 1, 'exactly one style tag — _head.html opens it, the page must not open a second'
assert 'id="form-chart"' in html, 'zone 1 chart canvas missing'
assert re.search(r'class="[^"]*form-verdict', html), 'zone 1 direction verdict missing'
for band in ('surging', 'sliding', 'unreliable', 'absent'):
    assert 'data-band="%s"' % band in html, 'movers band missing: %s' % band
assert 'id="record-table"' in html, 'zone 3 table missing'
assert 'class="rec-row"' in html or 'rec-row' in html, 'roster rows missing'
assert 'rec-toggle' in html, 'drill-down toggles must be real buttons'
assert '<button' in html
assert 'tabindex="0"' in html, 'sortable headers need tabindex, not role'
assert 'none this window' in html.lower(), 'empty movers bands must say so'
print('ROUTE 7 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_route_7.py"
```

Expected: `AssertionError: zone 1 chart canvas missing`

- [ ] **Step 3: Write the template**

Replace `coc_stats/templates/ranked/ranked_stats.html` entirely. Structural markup
only — `impeccable` owns the visual layer afterward. Note there is no `<style>` open
tag: `_head.html` already opened one.

```html
<!DOCTYPE html>
<html lang="en">
{% set page_title = 'The Record – CoC Analytics' %}
{% set chartjs = true %}
{% include '_head.html' %}

    /* ═══ THE RECORD — long-term Ranked. Structural pass only; visual language
       comes from a later impeccable pass. ═══ */
    .container { padding-bottom: 72px; }

    .form-verdict { font-weight: 700; }
    .form-chart-wrap { position: relative; height: 220px; margin: 16px 0 28px; }

    .mv-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 28px; }
    .mv-band { border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
    .mv-band h3 { font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; margin: 0 0 10px; }
    .mv-entry { display: flex; justify-content: space-between; gap: 10px; padding: 4px 0; }
    .mv-empty { color: var(--muted); font-size: 12px; }

    #record-table { width: 100%; border-collapse: collapse; }
    #record-table th { text-align: left; font-size: 10.5px; letter-spacing: 1.2px;
                       text-transform: uppercase; padding: 8px 10px; cursor: pointer; }
    #record-table td { padding: 8px 10px; border-top: 1px solid var(--bord2); }
    .rec-toggle { background: none; border: 0; color: inherit; font: inherit;
                  cursor: pointer; text-align: left; width: 100%; }
    .rec-detail { display: none; }
    .rec-detail.open { display: table-row; }
    .rec-tail { margin-top: 24px; }
    .rec-tail h3 { font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; }

    @media (max-width: 760px) {
        .mv-grid { grid-template-columns: 1fr; }
        #record-table thead { display: none; }
        #record-table tr.rec-row { display: block; border-top: 1px solid var(--bord2); }
        #record-table tr.rec-row td { display: inline-block; border: 0; padding: 4px 8px; }
    }
</head>
<body>
{% include '_nav.html' %}

{% set page_header_title = 'The <span>Record</span>' %}
{% set page_header_desc = 'Long-term Ranked performance — who is improving, who is sliding, and who you can count on.' %}
{% set page_header_meta = [
    {'value': form.current,   'label': 'clan form'},
    {'value': form.vs_peak,   'label': 'vs peak (' ~ form.peak_label ~ ')',
     'tone': 'loss' if form.vs_peak < 0 else 'win'},
    {'value': form.depth,     'label': 'players at good+'},
    {'value': seasons | length, 'label': 'seasons'}
] %}
{% set page_primary_control %}
    <form method="get" class="window-form">
        <label for="window-select" class="sr-only">Window</label>
        <select id="window-select" name="window" onchange="this.form.submit()">
            {% for w in windows %}
            <option value="{{ w }}" {% if w == window %}selected{% endif %}>
                {{ 'All seasons' if w == 'all' else 'Last ' ~ w }}
            </option>
            {% endfor %}
        </select>
    </form>
{% endset %}
{% include '_page_header.html' %}

<div class="container">

    {# ── ZONE 1 — CLAN FORM ─────────────────────────────────────────── #}
    <section aria-labelledby="form-h">
        <h2 id="form-h" class="sr-only">Clan form</h2>
        <p class="form-verdict form-{{ form.direction }}">
            Clan form is <strong>{{ form.direction }}</strong> —
            {{ form.delta }} points across the last three seasons.
            Peak was {{ form.peak_mean }} on {{ form.peak_label }}; now {{ form.current }}.
        </p>
        <div class="form-chart-wrap"><canvas id="form-chart"></canvas></div>
    </section>

    {# ── ZONE 2 — MOVERS ────────────────────────────────────────────── #}
    <section class="mv-grid" aria-labelledby="mv-h">
        <h2 id="mv-h" class="sr-only">Movers</h2>
        {% for band, title, field, suffix in [
            ('surging',    'Surging',    'trend',      ' pts'),
            ('sliding',    'Sliding',    'trend',      ' pts'),
            ('unreliable', 'Unreliable', 'sigma',      ' σ'),
            ('absent',     'Absent',     'attendance', '')] %}
        <div class="mv-band" data-band="{{ band }}">
            <h3>{{ title }}</h3>
            {% if movers[band] %}
                {% for r in movers[band] %}
                <div class="mv-entry">
                    <span>{{ r.player_name }}</span>
                    <span>
                        {%- if band == 'absent' -%}
                            {{ (r.attendance * 100) | round(1) }}% ({{ r.attacks_used }}/{{ r.attacks_max }})
                        {%- else -%}
                            {{ r[field] }}{{ suffix }}
                        {%- endif -%}
                    </span>
                </div>
                {% endfor %}
            {% else %}
                <p class="mv-empty">None this window.</p>
            {% endif %}
        </div>
        {% endfor %}
    </section>

    {# ── ZONE 3 — THE RECORD ────────────────────────────────────────── #}
    <section aria-labelledby="rec-h">
        <h2 id="rec-h" class="sr-only">The record</h2>
        <table id="record-table">
            <thead>
                <tr>
                    <th tabindex="0" data-sort="rank">#</th>
                    <th tabindex="0" data-sort="name">Player</th>
                    <th tabindex="0" data-sort="mean">Mean</th>
                    <th>Form</th>
                    <th tabindex="0" data-sort="reliability">Reliability</th>
                    <th tabindex="0" data-sort="trend">Trend</th>
                    <th tabindex="0" data-sort="attendance">Attendance</th>
                    <th tabindex="0" data-sort="league">League</th>
                    <th tabindex="0" data-sort="defense">Defense</th>
                    <th>Verdicts</th>
                </tr>
            </thead>
            <tbody>
            {% for r in roster %}
                <tr class="rec-row" data-tag="{{ r.player_tag }}">
                    <td>{{ loop.index }}</td>
                    <td>
                        <button type="button" class="rec-toggle"
                                aria-expanded="false"
                                aria-controls="detail-{{ loop.index }}">
                            {{ r.player_name }}
                        </button>
                    </td>
                    <td class="rec-mean {{ r.verdict_record.keys() | list | first }}">{{ r.mean }}</td>
                    <td><canvas class="rec-spark" width="80" height="20"
                                data-scores="{{ r.scores | join(',') }}"></canvas></td>
                    <td>{{ r.reliability }}</td>
                    <td>{% if r.trend is not none %}{{ '%+.1f' % r.trend }}{% else %}—{% endif %}</td>
                    <td>{% if r.attendance < 1.0 %}{{ (r.attendance * 100) | round(1) }}%{% else %}✓{% endif %}</td>
                    <td>{{ r.league_now }}{% if r.league_move %} ({{ '%+d' % r.league_move }}){% endif %}</td>
                    <td>
                        {%- if r.defense.index is not none -%}
                            {{ '%+.1f' % r.defense.index }}{% if r.defense.thin %} <abbr title="limited data">*</abbr>{% endif %}
                        {%- else -%}—{%- endif -%}
                    </td>
                    <td class="rec-verdicts">
                        {% for badge, count in r.verdict_record.items() %}
                        <span class="{{ badge }}">{{ count }}</span>
                        {% endfor %}
                    </td>
                </tr>
                <tr class="rec-detail" id="detail-{{ loop.index }}" data-tag="{{ r.player_tag }}">
                    <td colspan="10"><div class="rec-detail-body"></div></td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        {% if tail_thin %}
        <div class="rec-tail">
            <h3>Not enough data</h3>
            {% for r in tail_thin %}
            <div class="mv-entry"><span>{{ r.player_name }}</span><span>{{ r.weeks_played }} week(s)</span></div>
            {% endfor %}
        </div>
        {% endif %}

        {% if tail_absent %}
        <div class="rec-tail">
            <h3>Not participating</h3>
            {% for r in tail_absent %}
            <div class="mv-entry">
                <span>{{ r.player_name }}</span>
                <span>{{ r.attacks_used }}/{{ r.attacks_max }} attacks</span>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </section>
</div>

<script>
const PAGE = {{ page_json | safe }};

// Zone 1 — clan form line
(function () {
    const el = document.getElementById('form-chart');
    if (!el || !window.Chart) return;
    const css = getComputedStyle(document.documentElement);
    // Chart.js draws to canvas and cannot resolve var() or color-mix(),
    // so tokens must be resolved to concrete values first.
    const accent = css.getPropertyValue('--accent').trim() || '#f0a500';
    const muted  = css.getPropertyValue('--muted').trim()  || '#8a8a8a';
    new Chart(el, {
        type: 'line',
        data: {
            labels: PAGE.form.points.map(p => p.label),
            datasets: [{
                data: PAGE.form.points.map(p => p.mean),
                borderColor: accent, backgroundColor: accent,
                tension: 0.3, pointRadius: 3
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { min: 0, max: 100, ticks: { color: muted } },
                x: { ticks: { color: muted } }
            }
        }
    });
})();

// Zone 3 — sparklines
document.querySelectorAll('.rec-spark').forEach(function (canvas) {
    const scores = canvas.dataset.scores.split(',').filter(Boolean).map(Number);
    if (!scores.length) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.strokeStyle = getComputedStyle(document.documentElement)
        .getPropertyValue('--accent').trim() || '#f0a500';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    scores.forEach(function (s, i) {
        const x = scores.length === 1 ? w / 2 : (i / (scores.length - 1)) * (w - 2) + 1;
        const y = h - 1 - (s / 100) * (h - 2);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
});

// Zone 3 — sortable headers (click and keyboard)
(function () {
    const table = document.getElementById('record-table');
    if (!table) return;
    const tbody = table.tBodies[0];
    const dir = {};
    function sortBy(key) {
        dir[key] = !dir[key];
        const sign = dir[key] ? 1 : -1;
        const pairs = [];
        for (let i = 0; i < tbody.rows.length; i += 2) {
            pairs.push([tbody.rows[i], tbody.rows[i + 1]]);
        }
        const tagOf = tr => tr.dataset.tag;
        const rowFor = tag => PAGE.roster.find(r => r.player_tag === tag) || {};
        pairs.sort(function (a, b) {
            const ra = rowFor(tagOf(a[0])), rb = rowFor(tagOf(b[0]));
            let va, vb;
            switch (key) {
                case 'name':    va = ra.player_name; vb = rb.player_name; break;
                case 'league':  va = ra.league_rank_now; vb = rb.league_rank_now; break;
                case 'defense': va = (ra.defense || {}).index; vb = (rb.defense || {}).index; break;
                case 'reliability': va = ra.sigma; vb = rb.sigma; break;
                default:        va = ra[key]; vb = rb[key];
            }
            if (va === null || va === undefined) va = -Infinity;
            if (vb === null || vb === undefined) vb = -Infinity;
            if (typeof va === 'string') return sign * va.localeCompare(vb);
            return sign * (va - vb);
        });
        pairs.forEach(p => { tbody.appendChild(p[0]); tbody.appendChild(p[1]); });
    }
    table.querySelectorAll('th[data-sort]').forEach(function (th) {
        th.addEventListener('click', () => sortBy(th.dataset.sort));
        th.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(th.dataset.sort); }
        });
    });
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_route_7.py"
```

Expected: `ROUTE 7 OK`

- [ ] **Step 5: Commit**

```bash
git add coc_stats/templates/ranked/ranked_stats.html
git commit -m "feat(ranked): build The Record — clan form, movers, roster table"
```

---

### Task 8: Drill-down rendering and database smoke check

**Files:**
- Modify: `coc_stats/templates/ranked/ranked_stats.html` (extend the `<script>` block)
- Test: scratchpad `verify_route_8.py`, `verify_db_8.py`

**Interfaces:**
- Consumes: `PAGE.players[tag]` from Task 6 — `{records, markers, matchups, near, defense, attendance_weeks}`
- Produces: drill-down DOM inside `.rec-detail-body`

- [ ] **Step 1: Write the failing verification script**

Create scratchpad `verify_route_8.py`:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from app import app

with app.test_client() as c:
    html = c.get('/ranked/stats').get_data(as_text=True)

assert 'renderDetail' in html, 'drill-down renderer missing'
assert 'MATCHUP_LABELS' in html, 'matchup bucket labels missing'
assert 'aria-expanded' in html
assert 'near-miss' in html.lower() or 'near miss' in html.lower()
assert 'clanMatchupMean' in html, 'matchup comparison against the clan is the actionable part'
print('ROUTE 8 OK')
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python "<scratchpad>/verify_route_8.py"
```

Expected: `AssertionError: drill-down renderer missing`

- [ ] **Step 3: Add the drill-down renderer**

Append inside the existing `<script>` block in
`coc_stats/templates/ranked/ranked_stats.html`, before `</script>`:

```javascript
// Zone 4 — drill-down
const MATCHUP_LABELS = {
    '-2': 'TH-2 or lower', '-1': 'TH-1', '0': 'Even TH',
    '1': 'TH+1', '2': 'TH+2 or higher'
};

// Clan mean stars per matchup bucket — the yardstick a player is measured against.
const clanMatchupMean = (function () {
    const totals = {};
    Object.values(PAGE.players).forEach(function (p) {
        Object.entries(p.matchups || {}).forEach(function ([k, b]) {
            const t = totals[k] || (totals[k] = { stars: 0, attacks: 0 });
            t.stars += b.avg_stars * b.attacks;
            t.attacks += b.attacks;
        });
    });
    const out = {};
    Object.entries(totals).forEach(function ([k, t]) {
        out[k] = t.attacks ? t.stars / t.attacks : null;
    });
    return out;
})();

function esc(s) {
    return String(s).replace(/[&<>"]/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function renderDetail(tag) {
    const p = PAGE.players[tag];
    if (!p) return '<p>No data.</p>';
    const parts = [];

    // Career line
    parts.push('<div class="dd-block"><h4>Career</h4>');
    parts.push('<canvas class="dd-career" width="640" height="140" data-tag="' + esc(tag) + '"></canvas>');
    if (p.markers.length) {
        parts.push('<ul class="dd-markers">' + p.markers.map(m =>
            '<li>' + esc(PAGE.labels[m.season_id] || m.season_id) + ' — ' +
            esc(m.kind) + ': ' + esc(m.detail) + '</li>').join('') + '</ul>');
    }
    parts.push('</div>');

    // Where the points go
    parts.push('<div class="dd-block"><h4>Where the points go</h4>');
    const keys = Object.keys(p.matchups).sort((a, b) => Number(a) - Number(b));
    if (!keys.length) {
        parts.push('<p>No attacks on record.</p>');
    } else {
        const rendered = keys.filter(k => p.matchups[k].enough);
        if (!rendered.length) {
            parts.push('<p>Too few attacks in any single matchup to judge — ' +
                       keys.map(k => esc(MATCHUP_LABELS[k]) + ' (' + p.matchups[k].attacks + ')').join(', ') +
                       '.</p>');
        } else {
            parts.push('<table class="dd-matchup"><thead><tr><th>Matchup</th><th>Attacks</th>' +
                       '<th>Avg ★</th><th>Clan avg ★</th><th>Delta</th></tr></thead><tbody>');
            rendered.forEach(function (k) {
                const b = p.matchups[k];
                const clan = clanMatchupMean[k];
                const delta = clan === null || clan === undefined ? null : b.avg_stars - clan;
                parts.push('<tr><td>' + esc(MATCHUP_LABELS[k] || k) + '</td><td>' + b.attacks +
                    '</td><td>' + b.avg_stars.toFixed(2) + '</td><td>' +
                    (clan === null || clan === undefined ? '—' : clan.toFixed(2)) + '</td><td>' +
                    (delta === null ? '—' : (delta >= 0 ? '+' : '') + delta.toFixed(2)) + '</td></tr>');
            });
            parts.push('</tbody></table>');
            const skipped = keys.filter(k => !p.matchups[k].enough);
            if (skipped.length) {
                parts.push('<p class="dd-note">Not shown (fewer than 10 attacks): ' +
                    skipped.map(k => esc(MATCHUP_LABELS[k]) + ' (' + p.matchups[k].attacks + ')').join(', ') + '.</p>');
            }
        }
    }
    parts.push('</div>');

    // Near-misses
    parts.push('<div class="dd-block"><h4>Near-misses</h4><p>' +
        p.near.near + ' of ' + p.near.attacks + ' attacks (' + p.near.near_pct +
        '%) were 2★ at 90% or better — one building short of a 3★. ' +
        'Three-star rate: ' + p.near.three_pct + '%.</p></div>');

    // Attendance
    parts.push('<div class="dd-block"><h4>Attendance</h4>');
    if (!p.attendance_weeks.length) {
        parts.push('<p>Every attack used, every week.</p>');
    } else {
        parts.push('<ul>' + p.attendance_weeks.map(w =>
            '<li>' + esc(w.label) + ' — ' + w.used + '/' + w.max +
            ' (' + w.missing + ' missed)</li>').join('') + '</ul>');
    }
    parts.push('</div>');

    // Defense
    parts.push('<div class="dd-block"><h4>Defense</h4>');
    if (!p.defense.n) {
        parts.push('<p>No defenses on record.</p>');
    } else {
        parts.push('<p>' + p.defense.tpd + ' trophies per defense across ' + p.defense.n +
            ' defenses — ' + (p.defense.index >= 0 ? '+' : '') + p.defense.index +
            ' against what this league expects.' +
            (p.defense.thin ? ' <em>Limited data for this league band.</em>' : '') + '</p>');
    }
    parts.push('</div>');

    return parts.join('');
}

function drawCareer(canvas) {
    const p = PAGE.players[canvas.dataset.tag];
    if (!p || !p.records.length) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const css = getComputedStyle(document.documentElement);
    const accent = css.getPropertyValue('--accent').trim() || '#f0a500';
    const muted = css.getPropertyValue('--muted').trim() || '#8a8a8a';
    const n = p.records.length;
    const x = i => n === 1 ? w / 2 : (i / (n - 1)) * (w - 20) + 10;
    const y = s => h - 10 - (s / 100) * (h - 20);

    ctx.strokeStyle = muted; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(10, y(0)); ctx.lineTo(w - 10, y(0)); ctx.stroke();

    const marked = new Set(p.markers.map(m => m.season_id));
    ctx.strokeStyle = muted; ctx.setLineDash([3, 3]);
    p.records.forEach(function (r, i) {
        if (!marked.has(r.season_id)) return;
        ctx.beginPath(); ctx.moveTo(x(i), 6); ctx.lineTo(x(i), h - 6); ctx.stroke();
    });
    ctx.setLineDash([]);

    ctx.strokeStyle = accent; ctx.lineWidth = 2; ctx.beginPath();
    p.records.forEach((r, i) => i ? ctx.lineTo(x(i), y(r.score)) : ctx.moveTo(x(i), y(r.score)));
    ctx.stroke();

    ctx.fillStyle = accent;
    p.records.forEach(function (r, i) {
        ctx.beginPath(); ctx.arc(x(i), y(r.score), 2.5, 0, Math.PI * 2); ctx.fill();
    });
}

document.querySelectorAll('.rec-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
        const row = btn.closest('tr');
        const detail = document.getElementById(btn.getAttribute('aria-controls'));
        const open = detail.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open && !detail.dataset.rendered) {
            detail.querySelector('.rec-detail-body').innerHTML = renderDetail(row.dataset.tag);
            detail.querySelectorAll('.dd-career').forEach(drawCareer);
            detail.dataset.rendered = '1';
        }
    });
});
```

Add the matching CSS, before `</head>` in the same file (inside the already-open style):

```css
    .dd-block { margin: 14px 0; }
    .dd-block h4 { font-size: 10.5px; letter-spacing: 1.2px; text-transform: uppercase;
                   color: var(--muted); margin: 0 0 6px; }
    .dd-matchup { width: 100%; border-collapse: collapse; }
    .dd-matchup th, .dd-matchup td { text-align: left; padding: 4px 8px; font-size: 12px; }
    .dd-note { color: var(--muted); font-size: 11.5px; }
    .dd-markers { margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: var(--muted); }
    .dd-career { max-width: 100%; }
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python "<scratchpad>/verify_route_8.py"
```

Expected: `ROUTE 8 OK`

- [ ] **Step 5: Run the database smoke check**

Create scratchpad `verify_db_8.py`. This asserts structural invariants only —
never exact means, which change every week as the season data grows:

```python
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from app import app
from models import Player, RankedWeek
from sqlalchemy.orm import selectinload
from features.ranked.stats import (
    build_record_page, MIN_WEEKS_FOR_RANKING, ABSENT_ATTENDANCE, GOOD_BAND_CUTOFF,
)

with app.app_context():
    players = Player.query.filter_by(in_clan=True).all()
    tags = [p.tag for p in players]
    weeks = (RankedWeek.query.filter(RankedWeek.player_tag.in_(tags))
             .options(selectinload(RankedWeek.battle_logs)).all())
    page = build_record_page(players, weeks, 'all')

    live = {w.league_season_id for w in weeks if not w.is_done}
    assert not (live & set(page['seasons'])), 'a live season leaked into the window'

    for r in page['roster']:
        assert 0 <= r['mean'] <= 100, r
        assert 0.0 <= r['attendance'] <= 1.0, r
        assert r['weeks_played'] >= MIN_WEEKS_FOR_RANKING, r
        assert r['attendance'] >= ABSENT_ATTENDANCE, 'an absent player leaked into the roster'
        assert sum(r['verdict_record'].values()) == r['weeks_played'], r
        assert len(r['scores']) == r['weeks_played'], r
        assert r['attacks_used'] + r['attacks_wasted'] == r['attacks_max'], r

    means = [r['mean'] for r in page['roster']]
    assert means == sorted(means, reverse=True), 'roster must be sorted by mean desc'

    seen = set()
    for group in ('roster', 'tail_thin', 'tail_absent'):
        for r in page[group]:
            assert r['player_tag'] not in seen, 'player appears in two groups: %s' % r['player_tag']
            seen.add(r['player_tag'])

    absent = {r['player_tag'] for r in page['movers']['absent']}
    for band in ('surging', 'sliding', 'unreliable'):
        for r in page['movers'][band]:
            assert r['player_tag'] not in absent, 'absent player in %s' % band

    assert page['form']['depth'] == sum(1 for r in page['roster'] if r['mean'] >= GOOD_BAND_CUTOFF)
    for p in page['form']['points']:
        assert 0 <= p['mean'] <= 100 and p['participants'] > 0

    print('roster=%d thin=%d absent=%d seasons=%d form=%s'
          % (len(page['roster']), len(page['tail_thin']), len(page['tail_absent']),
             len(page['seasons']), page['form']['direction']))
    print('DB SMOKE 8 OK')
```

Run: `python "<scratchpad>/verify_db_8.py"`
Expected: a summary line, then `DB SMOKE 8 OK`.

- [ ] **Step 6: Verify in the browser**

Start the app via `preview_start`, open `/ranked/stats`, then:
- `read_console_messages` — expect no errors
- `read_page` — confirm the form verdict, four movers bands, and the roster render
- Click a `.rec-toggle` and confirm the drill-down expands with matchup, near-miss, attendance, and defense blocks
- `resize_window` to 390x844 and confirm the table collapses to dense divided rows, not cards
- Screenshot to confirm

- [ ] **Step 7: Commit**

```bash
git add coc_stats/templates/ranked/ranked_stats.html
git commit -m "feat(ranked): add drill-down — career line, matchup leaks, near-misses, defense"
```

---

## After this plan

The structure is complete and correct but visually unstyled. Hand off to the
`impeccable` skill for the visual layer: palette against `DESIGN.md`'s night-ops
thermal-scope tokens, typography, the page's signature element, verdict-band
color mapping, sparkline and career-line treatment, and motion. Chart.js cannot
resolve `var()` or `color-mix()` on canvas, so any token used in a chart must be
resolved to a concrete value first — the pattern is already in place in Task 7.

## Self-Review

**Spec coverage** — every spec section maps to a task:

| Spec section | Task |
|---|---|
| Window selection, completed-only | 1, 6 |
| `mean`, `sigma`, `trend`, `attendance`, `league_move`, `reliability`, `verdict_record` | 2 |
| `def_index`, band normalization, thin-band fallback | 3 |
| Zone 1 Clan Form + direction verdict + depth | 4, 7 |
| Zone 2 Movers, four bands, absent exclusivity, "none this window" | 4, 7 |
| Zone 3 roster, sparkline, attendance-only-when-short, tails | 6, 7 |
| Zone 4 career line, matchup buckets, near-misses, attendance record, defense | 5, 8 |
| Pure functions extracted from the route | 1-6 |
| Cache per (window, roster) | 6 |
| Inline drill-down payload, no fetch | 6, 8 |
| Live season excluded, shown as pending | 1, 8 |
| Per-attack stats state their n | 5, 8 |

**Placeholder scan** — no TBD, no "add error handling", no "similar to Task N".
Every code step carries complete code.

**Type consistency** — `player_defense` returns `{n, tpd, index, thin}` in Task 3
and is read with those exact keys in Tasks 6, 7, and 8. `matchup_buckets` returns
`{attacks, avg_stars, avg_pct, enough}` in Task 5 and is read with those keys in
Task 8. `clan_form` gained a required `depth_source` parameter in Task 4 and is
called with it in Task 6. Week record keys defined in Task 1 are used unchanged
throughout.

**Known gap accepted:** the spec's "pending marker for the live season" is
satisfied by exclusion from the math plus the `impeccable` pass adding the visual
marker; Task 8's DB smoke check asserts the exclusion.

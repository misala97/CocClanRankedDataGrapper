# Insights Deep-Dive Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build five analytics studies over the war/CWL/ranked/raid data and serve them from `/admin/insights` as a briefing that opens with findings already computed.

**Architecture:** One DB-aware loader turns ORM rows into plain fact dicts; five pure study modules consume those dicts and return plain dicts. The route assembles all five behind a data-version cache. Same shape as `features/ranked/stats.py` and `features/admin/monitor_stats.py`, which are pure and fully unit-tested without a database.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy (Flask-SQLAlchemy `Model.query`), MySQL, pytest. No new dependencies — `statistics` is stdlib.

**Spec:** `docs/superpowers/specs/2026-08-05-insights-deep-dive-analytics-design.md`

## Global Constraints

- **Working directory is `coc_stats/`.** All paths in this plan are relative to it. Tests run as `python -m pytest tests/ -q` from there; there is no `conftest.py` and no pytest config — imports work because pytest puts the CWD on `sys.path`.
- **Study modules must not import Flask, `extensions.db`, or `models`.** Only `loaders.py` is DB-aware. This is what makes the studies testable with `SimpleNamespace`.
- **No study may read `is_opponent`.** Clan identity arrives as `fact['clan_tag']`, normalized in the loader. Spec §2: filtering CWL on `is_opponent` gives 44.8% where `clan_tag` gives 67.9% for the same statistic.
- **Scoring is never reimplemented.** Ranked and raid scores come from `services.helpers._calc_ranked_score` and `_raid_verdict`, exactly as `features/ranked/stats.py` does.
- **Existing tests must stay green.** 177 pass today; every task ends with the full suite passing, not just the new file.
- **Branch is `dev_coc`.** Commit after every task.
- **No template work in this plan.** Spec §8: the page's visual execution goes through `/impeccable` with mockups first. This plan ends with the route serving correct data, verified against the live database.

## File Structure

| File | Responsibility |
|---|---|
| `features/admin/insights/__init__.py` | Assembles the five studies into one briefing dict; owns the cache |
| `features/admin/insights/loaders.py` | **The only DB-aware file.** ORM rows → plain fact dicts; normalizes clan identity |
| `features/admin/insights/curve.py` | Study A — TH-differential buckets, expected-stars model, per-player SAE |
| `features/admin/insights/benchmark.py` | Study B — all 22 CWL clans through the curve |
| `features/admin/insights/consistency.py` | Study C — mean, sigma, floor, ceiling, the contrast pair |
| `features/admin/insights/upgrade.py` | Study D — before/after a town hall change |
| `features/admin/insights/correlation.py` | Study E — the Pearson r, lifted out of `routes.py` |
| `tests/test_insights_curve.py` | Tasks 2–3 |
| `tests/test_insights_benchmark.py` | Task 4 |
| `tests/test_insights_consistency.py` | Task 5 |
| `tests/test_insights_upgrade.py` | Task 6 |
| `tests/test_insights_correlation.py` | Task 7 |
| `tests/test_insights_loaders.py` | Task 1 — pure shaping functions only |
| `features/admin/routes.py` | Modified: `admin_insights()` gains data; `admin_skill_correlation()` removed |

`curve.py` is the hub: `benchmark.py` and `upgrade.py` both consume the curve object it produces rather than refitting one. Build it before them.

---

### Task 1: The loader and its clan-identity normalization

The whole plan rests on one join — an attack to the town hall it was aimed at — and on getting clan identity right for two sources that disagree about how to express it. `cwl_member` has a `clan_tag` column; `clan_war_member` does **not**, so the war side derives it from the war.

**Files:**
- Create: `features/admin/insights/__init__.py` (empty for now)
- Create: `features/admin/insights/loaders.py`
- Test: `tests/test_insights_loaders.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `war_fact(attack, attacker, defender, war) -> dict`
  - `cwl_fact(attack, attacker, defender, war) -> dict`
  - `load_attack_facts() -> list[dict]` (DB-aware)
  - Every fact dict has exactly these keys: `src`, `war_id`, `ended_at`, `attacker_tag`, `attacker_th`, `defender_th`, `stars`, `destruction`, `clan_tag`, `attack_order`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_loaders.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.loaders — the fact-shaping functions.

Only the pure shaping functions are covered here. load_attack_facts() talks to
the database and is verified against live data in Task 8 instead.

The clan-identity tests are the point of this file. clan_war_member has no
clan_tag column, so the war side must take it from the war row via is_opponent;
cwl_member carries it directly. Getting this wrong is not a crash, it is a
plausible wrong number — see the spec's section 2.
"""

import datetime as dt
from types import SimpleNamespace as NS

from features.admin.insights.loaders import cwl_fact, war_fact

T0 = dt.datetime(2026, 7, 1, 12, 0)

FACT_KEYS = {'src', 'war_id', 'ended_at', 'attacker_tag', 'attacker_th',
             'defender_th', 'stars', 'destruction', 'clan_tag', 'attack_order'}


def war(clan='#US', opp='#THEM'):
    return NS(id=7, end_time=T0, clan_tag=clan, opponent_tag=opp)


def member(tag, th, is_opponent=0, clan_tag=None):
    return NS(player_tag=tag, town_hall_level=th,
              is_opponent=is_opponent, clan_tag=clan_tag)


def attack(stars=3, dest=100.0, order=4):
    return NS(attacker_tag='#A', defender_tag='#D',
              stars=stars, destruction_pct=dest, attack_order=order)


def test_war_fact_has_exactly_the_documented_keys():
    f = war_fact(attack(), member('#A', 14), member('#D', 15, 1), war())
    assert set(f) == FACT_KEYS


def test_war_attack_by_our_side_is_credited_to_our_clan():
    f = war_fact(attack(), member('#A', 14, is_opponent=0),
                 member('#D', 15, is_opponent=1), war(clan='#US', opp='#THEM'))
    assert f['clan_tag'] == '#US'


def test_war_attack_by_the_opponent_is_credited_to_the_opponent():
    """Both sides of every war feed the curve, so opponent attacks must be
    loaded — and attributed to the opponent, not silently to us."""
    f = war_fact(attack(), member('#A', 14, is_opponent=1),
                 member('#D', 15, is_opponent=0), war(clan='#US', opp='#THEM'))
    assert f['clan_tag'] == '#THEM'


def test_cwl_clan_tag_comes_from_the_member_not_from_is_opponent():
    """Our clan is 'the opponent' in rivals' CWL wars. A member flagged
    is_opponent=1 but carrying our clan_tag is us, and must be counted as us."""
    f = cwl_fact(attack(), member('#A', 14, is_opponent=1, clan_tag='#US'),
                 member('#D', 14, is_opponent=0, clan_tag='#THEM'),
                 NS(id=3, end_time=T0))
    assert f['clan_tag'] == '#US'


def test_th_differential_inputs_are_carried_through_unmodified():
    f = war_fact(attack(), member('#A', 13), member('#D', 16, 1), war())
    assert (f['attacker_th'], f['defender_th']) == (13, 16)


def test_null_stars_and_destruction_become_zero():
    """A recorded attack with no result is a zero, not a None that poisons a mean."""
    f = war_fact(NS(attacker_tag='#A', defender_tag='#D', stars=None,
                    destruction_pct=None, attack_order=None),
                 member('#A', 14), member('#D', 14, 1), war())
    assert f['stars'] == 0 and f['destruction'] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_loaders.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/__init__.py` as an empty file (Task 8 fills it).

Create `features/admin/insights/loaders.py`:

```python
# -*- coding: utf-8 -*-
"""The only DB-aware file under features/admin/insights.

Turns ORM rows into plain fact dicts the study modules consume, and normalizes
clan identity so no study ever sees is_opponent.

That normalization is the reason this file exists. cwl_member carries clan_tag
directly, and our clan appears there as 'the opponent' in rivals' wars because
the CWL tables hold the whole group — so is_opponent answers a different
question than clan_tag (44.8% against 67.9% for the same statistic). Meanwhile
clan_war_member has no clan_tag column at all and must take one from the war.
Two sources, two different mistakes available; both closed here, once.
"""


def war_fact(attack, attacker, defender, war):
    """One clan_war_attack row plus its two member rows -> a fact dict.

    `war` supplies clan identity: clan_war_member has no clan_tag, so the
    attacker's side decides which of the war's two tags applies.
    """
    return {
        'src':          'war',
        'war_id':       war.id,
        'ended_at':     war.end_time,
        'attacker_tag': attack.attacker_tag,
        'attacker_th':  attacker.town_hall_level,
        'defender_th':  defender.town_hall_level,
        'stars':        attack.stars or 0,
        'destruction':  attack.destruction_pct or 0.0,
        'clan_tag':     war.opponent_tag if attacker.is_opponent else war.clan_tag,
        'attack_order': attack.attack_order,
    }


def cwl_fact(attack, attacker, defender, war):
    """One cwl_attack row plus its two member rows -> a fact dict.

    clan_tag comes off the member, never from is_opponent.
    """
    return {
        'src':          'cwl',
        'war_id':       war.id,
        'ended_at':     war.end_time,
        'attacker_tag': attack.attacker_tag,
        'attacker_th':  attacker.town_hall_level,
        'defender_th':  defender.town_hall_level,
        'stars':        attack.stars or 0,
        'destruction':  attack.destruction_pct or 0.0,
        'clan_tag':     attacker.clan_tag,
        'attack_order': attack.attack_order,
    }


def load_attack_facts():
    """Every war and CWL attack as a fact dict. Requires an app context.

    Members are indexed by (war, tag) up front so the attack loop stays linear
    instead of issuing a query per attack.
    """
    from models import (ClanWar, ClanWarAttack, ClanWarMember,
                        CWLAttack, CWLMember, CWLWar)

    facts = []

    wars = {w.id: w for w in ClanWar.query.all()}
    wmem = {(m.clan_war_id, m.player_tag): m for m in ClanWarMember.query.all()}
    for a in ClanWarAttack.query.all():
        war = wars.get(a.clan_war_id)
        att = wmem.get((a.clan_war_id, a.attacker_tag))
        dfn = wmem.get((a.clan_war_id, a.defender_tag))
        if war and att and dfn:
            facts.append(war_fact(a, att, dfn, war))

    cwars = {w.id: w for w in CWLWar.query.all()}
    cmem = {(m.war_id, m.player_tag): m for m in CWLMember.query.all()}
    for a in CWLAttack.query.all():
        war = cwars.get(a.war_id)
        att = cmem.get((a.war_id, a.attacker_tag))
        dfn = cmem.get((a.war_id, a.defender_tag))
        if war and att and dfn:
            facts.append(cwl_fact(a, att, dfn, war))

    return facts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_loaders.py -q`
Expected: PASS, 6 passed

Then the full suite: `python -m pytest tests/ -q`
Expected: 183 passed

- [ ] **Step 5: Verify the loader is lossless against live data**

The joins must drop nothing. Run:

```bash
python -c "
from app import app
from features.admin.insights.loaders import load_attack_facts
from models import ClanWarAttack, CWLAttack
with app.app_context():
    f = load_attack_facts()
    war, cwl = sum(1 for x in f if x['src']=='war'), sum(1 for x in f if x['src']=='cwl')
    print(f'war {war}/{ClanWarAttack.query.count()}  cwl {cwl}/{CWLAttack.query.count()}')
    assert war == ClanWarAttack.query.count(), 'war attacks dropped by the join'
    assert cwl == CWLAttack.query.count(), 'cwl attacks dropped by the join'
    print('lossless')
"
```

Expected: `war 877/877  cwl 2417/2417` then `lossless`.

If counts differ, an attack references a member or war row that does not exist — do not relax the join to hide it; report it.

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/ tests/test_insights_loaders.py
git commit -m "feat(insights): load war and CWL attacks as normalized fact rows"
```

---

### Task 2: The difficulty curve

**Files:**
- Create: `features/admin/insights/curve.py`
- Test: `tests/test_insights_curve.py`

**Interfaces:**
- Consumes: fact dicts from Task 1.
- Produces:
  - `DIFF_CLAMP = 3`, `MIN_BUCKET_N = 20`, `MIN_PLAYER_ATTACKS = 8`
  - `clamp_diff(attacker_th, defender_th) -> int` in `[-3, 3]`
  - `build_curve(facts) -> {(src, diff): {'n', 'mean_stars', 'triple_rate', 'merged'}}` — every diff in `[-3, 3]` present for every `src` seen.

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_curve.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.curve — Study A.

The curve is the model B and D also depend on, so its edges matter more than
its happy path. Bucket merging never fires on current data (all 14 buckets
clear n=20), which is exactly why it is tested here: a rule that only runs
under conditions nobody has seen is the kind that ships broken.
"""

from features.admin.insights.curve import (
    DIFF_CLAMP,
    MIN_BUCKET_N,
    build_curve,
    clamp_diff,
)


def facts(src, diff, n, stars):
    """n attacks at one differential, all scoring `stars`."""
    return [{'src': src, 'attacker_th': 14, 'defender_th': 14 + diff,
             'stars': stars, 'destruction': 100.0, 'attacker_tag': f'#P{i}',
             'clan_tag': '#US', 'war_id': 1, 'ended_at': None,
             'attack_order': i} for i in range(n)]


def test_clamp_holds_ordinary_differentials_unchanged():
    assert clamp_diff(14, 15) == 1
    assert clamp_diff(14, 14) == 0
    assert clamp_diff(15, 13) == -2


def test_clamp_folds_the_long_tail():
    """The war tail runs to +7 on single attacks; those are not their own bucket."""
    assert clamp_diff(9, 16) == DIFF_CLAMP
    assert clamp_diff(16, 4) == -DIFF_CLAMP


def test_clamp_survives_missing_town_halls():
    assert clamp_diff(None, 14) == DIFF_CLAMP
    assert clamp_diff(14, None) == -DIFF_CLAMP


def test_bucket_reports_mean_stars_and_triple_rate():
    f = facts('war', 0, 20, 3) + facts('war', 0, 20, 1)
    c = build_curve(f)
    assert c[('war', 0)]['n'] == 40
    assert c[('war', 0)]['mean_stars'] == 2.0
    assert c[('war', 0)]['triple_rate'] == 0.5


def test_war_and_cwl_are_fitted_separately():
    """They are not the same game - 76.6% against 44.8% same-TH triples."""
    c = build_curve(facts('war', 0, 30, 3) + facts('cwl', 0, 30, 1))
    assert c[('war', 0)]['mean_stars'] == 3.0
    assert c[('cwl', 0)]['mean_stars'] == 1.0


def test_every_differential_is_present_for_every_source():
    c = build_curve(facts('war', 0, 30, 2))
    for d in range(-DIFF_CLAMP, DIFF_CLAMP + 1):
        assert ('war', d) in c, d


def test_a_thin_outer_bucket_merges_toward_zero():
    """+3 with too few attacks folds into +2, and both report the merged stats."""
    f = facts('war', 2, MIN_BUCKET_N, 2) + facts('war', 3, 4, 0)
    c = build_curve(f)
    assert c[('war', 3)]['merged'] is True
    assert c[('war', 3)] == c[('war', 2)]
    assert c[('war', 2)]['n'] == MIN_BUCKET_N + 4


def test_a_bucket_at_the_threshold_stands_alone():
    """Exactly MIN_BUCKET_N is enough - the boundary, not one past it."""
    f = facts('war', 2, MIN_BUCKET_N, 2) + facts('war', 3, MIN_BUCKET_N, 0)
    c = build_curve(f)
    assert c[('war', 3)]['merged'] is False
    assert c[('war', 3)]['n'] == MIN_BUCKET_N
    assert c[('war', 3)]['mean_stars'] == 0.0


def test_thin_buckets_cascade_all_the_way_to_zero():
    f = facts('war', 0, MIN_BUCKET_N, 3) + facts('war', 2, 2, 1) + facts('war', 3, 2, 1)
    c = build_curve(f)
    assert c[('war', 3)] == c[('war', 2)] == c[('war', 0)]
    assert c[('war', 0)]['n'] == MIN_BUCKET_N + 4


def test_an_empty_bucket_reports_no_expectation_rather_than_zero():
    """A differential nobody attacked at must not claim an expected 0.0 stars."""
    c = build_curve(facts('war', 0, 30, 3))
    assert c[('war', -3)]['n'] == 0
    assert c[('war', -3)]['mean_stars'] is None


def test_no_facts_yields_no_curve():
    assert build_curve([]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_curve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights.curve'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/curve.py`:

```python
# -*- coding: utf-8 -*-
"""Study A - what attacking up actually costs, and who beats that cost.

The curve is fitted over every attack in the table: both sides of every war,
and every clan in the CWL group. A baseline drawn only from our own attacks
cannot say whether our attacks are good.

War and CWL are fitted separately. They are not the same game - 76.6% against
44.8% same-town-hall triples on current data - and pooling them would flatter
CWL and libel war.
"""

from collections import defaultdict

DIFF_CLAMP         = 3      # differentials beyond this are single attacks, not a bucket
MIN_BUCKET_N       = 20     # below this a bucket merges toward zero
MIN_PLAYER_ATTACKS = 8      # below this a player is listed but not ranked


def clamp_diff(attacker_th, defender_th):
    """Town-hall differential, clamped to the range that carries enough attacks
    to mean anything. The war tail runs to +7 on single attacks.

    A missing town hall clamps rather than raising: one unparseable member row
    should cost one attack's precision, not the whole study.
    """
    return max(-DIFF_CLAMP, min(DIFF_CLAMP, (defender_th or 0) - (attacker_th or 0)))


def _bucket(group, merged):
    n = len(group)
    if not n:
        return {'n': 0, 'mean_stars': None, 'triple_rate': None, 'merged': merged}
    return {
        'n':           n,
        'mean_stars':  sum(f['stars'] for f in group) / n,
        'triple_rate': sum(1 for f in group if f['stars'] == 3) / n,
        'merged':      merged,
    }


def build_curve(facts):
    """-> {(src, diff): bucket} with every diff in [-DIFF_CLAMP, DIFF_CLAMP].

    Thin buckets merge toward zero, which is where the attacks are: a sparse
    +3 folds into +2, and if +2 is also sparse the pair folds into +1, and so
    on. Both keys then report the same merged stats with merged=True, so a
    caller can tell a measured expectation from a borrowed one.
    """
    raw = defaultdict(list)
    for f in facts:
        raw[(f['src'], clamp_diff(f['attacker_th'], f['defender_th']))].append(f)

    curve = {}
    for src in {s for s, _ in raw}:
        centre_extra, centre_keys = [], []
        for sign in (1, -1):
            carried, carried_keys = [], []
            for d in range(DIFF_CLAMP * sign, 0, -sign):
                group = raw.get((src, d), []) + carried
                keys  = carried_keys + [d]
                if len(group) < MIN_BUCKET_N:
                    carried, carried_keys = group, keys
                    continue
                stats = _bucket(group, merged=len(keys) > 1)
                for k in keys:
                    curve[(src, k)] = stats
                carried, carried_keys = [], []
            # Whatever is still too thin at +/-1 folds into the centre bucket.
            centre_extra += carried
            centre_keys  += carried_keys

        centre = raw.get((src, 0), []) + centre_extra
        stats  = _bucket(centre, merged=bool(centre_keys))
        for k in [0] + centre_keys:
            curve[(src, k)] = stats

    return curve
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_curve.py -q`
Expected: PASS, 11 passed

Then: `python -m pytest tests/ -q` → 194 passed

- [ ] **Step 5: Teeth-check the merge rule**

The merge rule never fires on production data, so a test that merely passes proves nothing. Break it and confirm the tests notice.

In `build_curve`, temporarily change `if len(group) < MIN_BUCKET_N:` to `if False:`.

Run: `python -m pytest tests/test_insights_curve.py -q`
Expected: FAIL — `test_a_thin_outer_bucket_merges_toward_zero` and `test_thin_buckets_cascade_all_the_way_to_zero` both fail.

**Restore the line.** Re-run: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/curve.py tests/test_insights_curve.py
git commit -m "feat(insights): fit the town-hall difficulty curve"
```

---

### Task 3: Stars above expectation

The load-bearing idea. A, B and D all rest on it: raw stars reward whoever draws easy matchups, while SAE asks whether an attack beat what this population's attacks at that differential normally do.

**Files:**
- Modify: `features/admin/insights/curve.py` (append)
- Modify: `tests/test_insights_curve.py` (append)

**Interfaces:**
- Consumes: `build_curve`, `clamp_diff`, `MIN_PLAYER_ATTACKS` from Task 2.
- Produces:
  - `sae_of(fact, curve) -> float | None` — one attack's stars above expectation, `None` when the bucket has no expectation.
  - `player_sae(facts, curve, min_attacks=MIN_PLAYER_ATTACKS) -> list[dict]` with keys `tag`, `n`, `sae`, `thin`; sorted best-first with thin players last.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_insights_curve.py`:

```python
# ── stars above expectation ──────────────────────────────────────────────────

from features.admin.insights.curve import MIN_PLAYER_ATTACKS, player_sae, sae_of


def att(tag, diff, stars, src='war'):
    return {'src': src, 'attacker_tag': tag, 'attacker_th': 14,
            'defender_th': 14 + diff, 'stars': stars, 'destruction': 100.0,
            'clan_tag': '#US', 'war_id': 1, 'ended_at': None, 'attack_order': 1}


def flat_curve(mean):
    return {('war', d): {'n': 99, 'mean_stars': mean, 'triple_rate': 0.5,
                         'merged': False} for d in range(-3, 4)}


def test_sae_is_the_gap_between_the_attack_and_its_bucket():
    assert sae_of(att('#A', 0, 3), flat_curve(2.0)) == 1.0
    assert sae_of(att('#A', 0, 1), flat_curve(2.0)) == -1.0


def test_sae_is_none_when_the_bucket_has_no_expectation():
    curve = {('war', 0): {'n': 0, 'mean_stars': None,
                          'triple_rate': None, 'merged': False}}
    assert sae_of(att('#A', 0, 3), curve) is None


def test_identical_raw_stars_rank_differently_by_difficulty():
    """The whole point of the study. Both players score 2.0 stars an attack;
    one did it against equal bases, the other against bases two levels up.
    Raw stars call that a tie. SAE does not."""
    curve = {
        ('war', 0): {'n': 99, 'mean_stars': 2.5, 'triple_rate': .7, 'merged': False},
        ('war', 2): {'n': 99, 'mean_stars': 1.2, 'triple_rate': .2, 'merged': False},
    }
    facts = ([att('#EASY', 0, 2) for _ in range(MIN_PLAYER_ATTACKS)] +
             [att('#HARD', 2, 2) for _ in range(MIN_PLAYER_ATTACKS)])
    rows = {r['tag']: r for r in player_sae(facts, curve)}

    assert rows['#EASY']['sae'] < 0            # below what equal bases usually give
    assert rows['#HARD']['sae'] > 0            # above what +2 usually gives
    assert player_sae(facts, curve)[0]['tag'] == '#HARD'


def test_a_player_one_attack_short_is_marked_thin_and_sorted_last():
    facts = ([att('#THIN', 0, 3) for _ in range(MIN_PLAYER_ATTACKS - 1)] +
             [att('#SOLID', 0, 1) for _ in range(MIN_PLAYER_ATTACKS)])
    rows = player_sae(facts, flat_curve(2.0))
    by_tag = {r['tag']: r for r in rows}

    assert by_tag['#THIN']['thin'] is True
    assert by_tag['#SOLID']['thin'] is False
    # #THIN has the better SAE and still must not outrank a solid player.
    assert by_tag['#THIN']['sae'] > by_tag['#SOLID']['sae']
    assert rows[0]['tag'] == '#SOLID'


def test_a_player_exactly_at_the_threshold_is_not_thin():
    facts = [att('#EDGE', 0, 3) for _ in range(MIN_PLAYER_ATTACKS)]
    assert player_sae(facts, flat_curve(2.0))[0]['thin'] is False


def test_attacks_with_no_expectation_are_skipped_not_counted_as_zero():
    curve = {('war', 0): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5, 'merged': False},
             ('war', 1): {'n': 0, 'mean_stars': None, 'triple_rate': None, 'merged': False}}
    facts = [att('#A', 0, 3), att('#A', 1, 3)]
    row = player_sae(facts, curve)[0]
    assert row['n'] == 1
    assert row['sae'] == 1.0


def test_a_player_with_no_scorable_attacks_is_absent_entirely():
    curve = {('war', 0): {'n': 0, 'mean_stars': None,
                          'triple_rate': None, 'merged': False}}
    assert player_sae([att('#A', 0, 3)], curve) == []


def test_no_facts_yields_no_rows():
    assert player_sae([], flat_curve(2.0)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_curve.py -q`
Expected: FAIL — `ImportError: cannot import name 'sae_of'`

- [ ] **Step 3: Write the implementation**

Append to `features/admin/insights/curve.py`:

```python
def sae_of(fact, curve):
    """One attack's stars above expectation, or None if its bucket has none.

    None means "this attack cannot be judged", which is different from zero -
    counting it as zero would drag every average toward the mean and quietly
    reward players whose attacks landed in unmeasured buckets.
    """
    bucket = curve.get((fact['src'], clamp_diff(fact['attacker_th'],
                                                fact['defender_th'])))
    if not bucket or bucket['mean_stars'] is None:
        return None
    return fact['stars'] - bucket['mean_stars']


def player_sae(facts, curve, min_attacks=MIN_PLAYER_ATTACKS):
    """Per-attacker stars above expectation, best first, thin players last.

    Thin players keep their real figure - it is shown, just not ranked. A
    player with three lucky attacks should not appear above one with forty
    solid ones, and dropping them outright would silently shrink the roster.
    """
    by_player = defaultdict(list)
    for f in facts:
        by_player[f['attacker_tag']].append(f)

    rows = []
    for tag, player_facts in by_player.items():
        deltas = [d for d in (sae_of(f, curve) for f in player_facts) if d is not None]
        if not deltas:
            continue
        rows.append({
            'tag':  tag,
            'n':    len(deltas),
            'sae':  sum(deltas) / len(deltas),
            'thin': len(deltas) < min_attacks,
        })

    rows.sort(key=lambda r: (r['thin'], -r['sae']))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_curve.py -q`
Expected: PASS, 19 passed

Then: `python -m pytest tests/ -q` → 202 passed

- [ ] **Step 5: Sanity-check against live data**

```bash
python -c "
from app import app
from features.admin.insights.loaders import load_attack_facts
from features.admin.insights.curve import build_curve, player_sae
from models import Player
with app.app_context():
    facts = load_attack_facts()
    curve = build_curve(facts)
    names = {p.tag: p.name for p in Player.query.filter_by(in_clan=True)}
    rows = [r for r in player_sae(facts, curve) if r['tag'] in names]
    print(f'ranked {sum(1 for r in rows if not r[\"thin\"])}, thin {sum(1 for r in rows if r[\"thin\"])}')
    for r in rows[:3]:
        print(f'  +{r[\"sae\"]:.2f}  {names[r[\"tag\"]]}  ({r[\"n\"]} attacks)')
    for r in [x for x in rows if not x['thin']][-3:]:
        print(f'  {r[\"sae\"]:+.2f}  {names[r[\"tag\"]]}  ({r[\"n\"]} attacks)')
"
```

Expected: 27 ranked (spec §5), some thin, and a plausible spread of SAE roughly within ±1.0. A player at ±3 stars means the curve is being applied to the wrong bucket — investigate rather than accept.

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/curve.py tests/test_insights_curve.py
git commit -m "feat(insights): score attacks against the curve as stars above expectation"
```

---

### Task 4: The group benchmark

**Files:**
- Create: `features/admin/insights/benchmark.py`
- Test: `tests/test_insights_benchmark.py`

**Interfaces:**
- Consumes: `clamp_diff`, `sae_of` from `curve.py`.
- Produces:
  - `MIN_CLAN_ATTACKS = 30`
  - `clan_ranking(facts, curve, our_tag, min_attacks=MIN_CLAN_ATTACKS) -> list[dict]` with keys `clan_tag`, `n`, `sae`, `same_th_n`, `same_th_triple_rate`, `is_ours`, `thin`, `rank`, `percentile`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_benchmark.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.benchmark - Study B.

The only study that answers "are we actually good" rather than "who among us
is best", because the CWL tables hold all 22 clans in the group.

Clans are ranked on stars above expectation, not raw stars: a clan whose roster
happens to sit above its opponents' would otherwise win on matchup luck.
"""

from features.admin.insights.benchmark import MIN_CLAN_ATTACKS, clan_ranking

CURVE = {('cwl', d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5, 'merged': False}
         for d in range(-3, 4)}
CURVE.update({('war', d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5,
                           'merged': False} for d in range(-3, 4)})


def att(clan, stars, diff=0, src='cwl'):
    return {'src': src, 'clan_tag': clan, 'attacker_tag': '#P', 'attacker_th': 14,
            'defender_th': 14 + diff, 'stars': stars, 'destruction': 100.0,
            'war_id': 1, 'ended_at': None, 'attack_order': 1}


def clan(tag, stars, n=MIN_CLAN_ATTACKS, diff=0):
    return [att(tag, stars, diff) for _ in range(n)]


def test_clans_rank_by_stars_above_expectation():
    rows = clan_ranking(clan('#GOOD', 3) + clan('#BAD', 1), CURVE, '#GOOD')
    assert [r['clan_tag'] for r in rows] == ['#GOOD', '#BAD']
    assert rows[0]['sae'] == 1.0 and rows[1]['sae'] == -1.0


def test_regular_war_attacks_are_excluded():
    """War has no rival population - only CWL supports a benchmark."""
    facts = clan('#US', 3) + [att('#US', 0, src='war') for _ in range(50)]
    assert clan_ranking(facts, CURVE, '#US')[0]['n'] == MIN_CLAN_ATTACKS


def test_our_clan_is_flagged_and_the_others_are_not():
    rows = {r['clan_tag']: r for r in
            clan_ranking(clan('#US', 3) + clan('#THEM', 1), CURVE, '#US')}
    assert rows['#US']['is_ours'] is True
    assert rows['#THEM']['is_ours'] is False


def test_same_th_triple_rate_counts_only_equal_town_halls():
    facts = (clan('#US', 3, n=10, diff=0) + clan('#US', 0, n=10, diff=0) +
             clan('#US', 3, n=10, diff=2))
    row = clan_ranking(facts, CURVE, '#US')[0]
    assert row['same_th_n'] == 20
    assert row['same_th_triple_rate'] == 0.5


def test_a_clan_that_never_faced_an_equal_town_hall_reports_no_rate():
    row = clan_ranking(clan('#US', 3, diff=2), CURVE, '#US')[0]
    assert row['same_th_n'] == 0
    assert row['same_th_triple_rate'] is None


def test_a_thin_clan_is_marked_and_sorted_last_despite_a_better_figure():
    facts = clan('#THIN', 3, n=MIN_CLAN_ATTACKS - 1) + clan('#SOLID', 2)
    rows = clan_ranking(facts, CURVE, '#SOLID')
    assert rows[0]['clan_tag'] == '#SOLID'
    assert rows[1]['thin'] is True


def test_rank_is_dense_and_one_based():
    rows = clan_ranking(clan('#A', 3) + clan('#B', 2) + clan('#C', 1), CURVE, '#A')
    assert [r['rank'] for r in rows] == [1, 2, 3]


def test_percentile_spans_the_ranked_clans_only():
    facts = (clan('#A', 3) + clan('#B', 2) + clan('#C', 1) +
             clan('#THIN', 3, n=2))
    rows = {r['clan_tag']: r for r in clan_ranking(facts, CURVE, '#A')}
    assert rows['#A']['percentile'] == 100.0
    assert rows['#C']['percentile'] == 0.0
    assert rows['#B']['percentile'] == 50.0
    assert rows['#THIN']['percentile'] is None


def test_a_lone_clan_has_no_percentile():
    """One clan is not a benchmark - a percentile here would be meaningless."""
    assert clan_ranking(clan('#US', 3), CURVE, '#US')[0]['percentile'] is None


def test_no_facts_yields_no_rows():
    assert clan_ranking([], CURVE, '#US') == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_benchmark.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights.benchmark'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/benchmark.py`:

```python
# -*- coding: utf-8 -*-
"""Study B - the clan measured against the 21 others in its CWL group.

Every other study asks who among us is best. This one asks whether we are any
good, which only works because the CWL tables hold the whole group rather than
just our own wars.

Clans are ranked on stars above expectation rather than raw stars. A clan whose
roster sits above its opponents' draws easier matchups all season and would win
a raw-stars table without attacking any better.
"""

from collections import defaultdict

from .curve import clamp_diff, sae_of

MIN_CLAN_ATTACKS = 30   # below this a clan is shown but not ranked


def clan_ranking(facts, curve, our_tag, min_attacks=MIN_CLAN_ATTACKS):
    """-> one row per clan, best first, thin clans last.

    CWL only. Regular war has no rival population to compare against.
    """
    by_clan = defaultdict(list)
    for f in facts:
        if f['src'] == 'cwl':
            by_clan[f['clan_tag']].append(f)

    rows = []
    for tag, clan_facts in by_clan.items():
        deltas = [d for d in (sae_of(f, curve) for f in clan_facts) if d is not None]
        if not deltas:
            continue
        same_th = [f for f in clan_facts
                   if clamp_diff(f['attacker_th'], f['defender_th']) == 0]
        rows.append({
            'clan_tag':            tag,
            'n':                   len(clan_facts),
            'sae':                 sum(deltas) / len(deltas),
            'same_th_n':           len(same_th),
            'same_th_triple_rate': (sum(1 for f in same_th if f['stars'] == 3)
                                    / len(same_th)) if same_th else None,
            'is_ours':             tag == our_tag,
            'thin':                len(clan_facts) < min_attacks,
        })

    rows.sort(key=lambda r: (r['thin'], -r['sae']))
    ranked = sum(1 for r in rows if not r['thin'])
    for i, r in enumerate(rows, 1):
        r['rank'] = i
        # A percentile against a single clan says nothing, and thin clans are
        # not in the ranked population at all.
        r['percentile'] = (None if r['thin'] or ranked < 2 else
                           round(100.0 * (ranked - r['rank']) / (ranked - 1), 1))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_benchmark.py -q`
Expected: PASS, 10 passed

Then: `python -m pytest tests/ -q` → 212 passed

- [ ] **Step 5: Check the live figure against the spec**

```bash
python -c "
from app import app
from features.admin.insights.loaders import load_attack_facts
from features.admin.insights.curve import build_curve
from features.admin.insights.benchmark import clan_ranking
OUR = '#2QRC8998U'
with app.app_context():
    facts = load_attack_facts()
    rows = clan_ranking(facts, build_curve(facts), OUR)
    us = next(r for r in rows if r['is_ours'])
    print(f'clans ranked: {len(rows)}')
    print(f'us: rank {us[\"rank\"]}/{len(rows)}  pct {us[\"percentile\"]}  sae {us[\"sae\"]:+.3f}')
    print(f'same-TH triples  us {us[\"same_th_triple_rate\"]:.1%} (n={us[\"same_th_n\"]})')
"
```

Expected: 22 clans ranked (spec §5 — all 22 clear the threshold), and our same-TH triple rate at **67.9% on n=137**, matching the spec §2 figure. A different number means clan attribution regressed; do not proceed.

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/benchmark.py tests/test_insights_benchmark.py
git commit -m "feat(insights): rank all 22 CWL clans on the shared curve"
```

---

### Task 5: Consistency

**Files:**
- Create: `features/admin/insights/consistency.py`
- Test: `tests/test_insights_consistency.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — takes `{tag: [score, ...]}`.
- Produces:
  - `MIN_RANKED_WEEKS = 6`, `MIN_RAID_WEEKENDS = 4`, `MEAN_BAND = 3.0`
  - `series_stats(values) -> {'n','mean','sd','floor','ceiling'} | None`
  - `consistency(scores_by_player, min_n) -> list[dict]` (adds `tag`, `thin`; steadiest first)
  - `contrast_pair(rows, mean_band=MEAN_BAND) -> {'steady': row, 'streaky': row} | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_consistency.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.consistency - Study C.

The mean is already elsewhere in the app. What is new here is the spread, and
the finding is the contrast: two players with near-identical averages and very
different sigma are different roster decisions.
"""

from features.admin.insights.consistency import (
    MEAN_BAND,
    consistency,
    contrast_pair,
    series_stats,
)


def test_series_stats_reports_spread_and_extremes():
    s = series_stats([50, 60, 70])
    assert s['n'] == 3
    assert s['mean'] == 60
    assert s['floor'] == 50 and s['ceiling'] == 70
    assert round(s['sd'], 3) == 8.165


def test_a_flat_series_has_no_spread():
    assert series_stats([70, 70, 70])['sd'] == 0.0


def test_a_single_value_has_no_spread_rather_than_crashing():
    s = series_stats([70])
    assert s['n'] == 1 and s['sd'] == 0.0


def test_an_empty_series_is_none():
    assert series_stats([]) is None


def test_players_sort_steadiest_first():
    rows = consistency({'#SWINGY': [40, 100, 40, 100, 40, 100],
                        '#STEADY': [70, 71, 69, 70, 71, 69]}, min_n=6)
    assert [r['tag'] for r in rows] == ['#STEADY', '#SWINGY']


def test_a_player_one_week_short_is_thin_and_sorted_last():
    rows = consistency({'#THIN':  [70, 70, 70, 70, 70],
                        '#SOLID': [40, 100, 40, 100, 40, 100]}, min_n=6)
    assert rows[0]['tag'] == '#SOLID'
    assert rows[1]['tag'] == '#THIN' and rows[1]['thin'] is True


def test_a_player_exactly_at_the_threshold_is_not_thin():
    rows = consistency({'#EDGE': [70] * 6}, min_n=6)
    assert rows[0]['thin'] is False


def test_the_contrast_pair_matches_means_and_maximises_the_sigma_gap():
    """The finding: same average, different reliability."""
    rows = consistency({'#STEADY':  [70, 70, 70, 70, 70, 70],
                        '#STREAKY': [40, 100, 40, 100, 40, 100],   # mean 70
                        '#OTHER':   [20, 22, 21, 20, 22, 21]}, min_n=6)
    pair = contrast_pair(rows)
    assert pair['steady']['tag'] == '#STEADY'
    assert pair['streaky']['tag'] == '#STREAKY'


def test_no_pair_when_no_two_players_share_a_mean():
    rows = consistency({'#A': [90] * 6, '#B': [20] * 6}, min_n=6)
    assert contrast_pair(rows, mean_band=MEAN_BAND) is None


def test_thin_players_are_never_named_in_the_contrast():
    """Bluntness is a tone decision; sample size is not."""
    rows = consistency({'#STEADY': [70] * 6,
                        '#THIN':   [40, 100, 40, 100]}, min_n=6)
    assert contrast_pair(rows) is None


def test_no_players_yields_no_rows_and_no_pair():
    assert consistency({}, min_n=6) == []
    assert contrast_pair([]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_consistency.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights.consistency'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/consistency.py`:

```python
# -*- coding: utf-8 -*-
"""Study C - who is reliable, as distinct from who is good.

The mean already appears elsewhere in the app. The spread does not, and it is
a different roster question: a 70-average player who never drops below 65 and
a 70-average player who alternates 40 and 100 are not interchangeable.

Sigma is the population standard deviation over the weeks a player actually
played. Those weeks are the whole record, not a sample drawn from a larger one,
and pstdev is defined at n=1 where stdev raises.
"""

import statistics

MIN_RANKED_WEEKS  = 6      # below this a player is listed but not ranked
MIN_RAID_WEEKENDS = 4
MEAN_BAND         = 3.0    # how close two means must be to count as "the same"


def series_stats(values):
    """-> {'n', 'mean', 'sd', 'floor', 'ceiling'}, or None for an empty series."""
    if not values:
        return None
    return {
        'n':       len(values),
        'mean':    sum(values) / len(values),
        'sd':      statistics.pstdev(values) if len(values) > 1 else 0.0,
        'floor':   min(values),
        'ceiling': max(values),
    }


def consistency(scores_by_player, min_n):
    """-> one row per player, steadiest first, thin players last."""
    rows = []
    for tag, values in scores_by_player.items():
        stats = series_stats(values)
        if not stats:
            continue
        stats['tag']  = tag
        stats['thin'] = stats['n'] < min_n
        rows.append(stats)

    rows.sort(key=lambda r: (r['thin'], r['sd']))
    return rows


def contrast_pair(rows, mean_band=MEAN_BAND):
    """The two ranked players with the closest means and the widest sigma gap.

    This is the finding the study exists to state. Thin players are excluded:
    a wide sigma over four weeks is noise, and naming someone for it would be
    the study accusing its own sample.
    """
    solid = [r for r in rows if not r['thin']]
    best  = None
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if abs(a['mean'] - b['mean']) > mean_band:
                continue
            gap = abs(a['sd'] - b['sd'])
            if best is None or gap > best[0]:
                best = (gap, a, b)

    if best is None or best[0] == 0:
        return None
    _, a, b = best
    steady, streaky = (a, b) if a['sd'] < b['sd'] else (b, a)
    return {'steady': steady, 'streaky': streaky}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_consistency.py -q`
Expected: PASS, 11 passed

Then: `python -m pytest tests/ -q` → 223 passed

- [ ] **Step 5: Commit**

```bash
git add features/admin/insights/consistency.py tests/test_insights_consistency.py
git commit -m "feat(insights): measure per-player consistency and the contrast pair"
```

---

### Task 6: The post-upgrade slump

The weakest study, and it ships saying so. n=15 after thresholds, and a town hall upgrade coincides with new troops, new bases and whatever else was happening that month — this measures the whole bundle, not the upgrade alone.

**Files:**
- Create: `features/admin/insights/upgrade.py`
- Test: `tests/test_insights_upgrade.py`

**Interfaces:**
- Consumes: `sae_of` from `curve.py`.
- Produces:
  - `WINDOW = 10`, `MIN_SIDE = 5`, `RECOVERY_WINDOW = 5`
  - `upgrade_effect(facts, curve) -> {'players': [...], 'mean_dip': float|None, 'n_players': int, 'n_recovered': int, 'median_recovery': int|None}`
  - Each player row: `tag`, `from_th`, `to_th`, `before`, `after`, `dip`, `n_before`, `n_after`, `recovered_after`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_upgrade.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.upgrade - Study D.

The window is a count of attacks, not a span of days: players attack at very
different rates, and a calendar window would compare one player's ten attacks
against another's two.
"""

import datetime as dt

from features.admin.insights.upgrade import (
    MIN_SIDE,
    RECOVERY_WINDOW,
    WINDOW,
    upgrade_effect,
)

T0 = dt.datetime(2026, 6, 1, 12, 0)
CURVE = {(s, d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5, 'merged': False}
         for s in ('war', 'cwl') for d in range(-3, 4)}


def run(tag, th, stars_seq, start=0):
    """Consecutive attacks at one town hall level, ordered in time."""
    return [{'src': 'war', 'attacker_tag': tag, 'attacker_th': th,
             'defender_th': th, 'stars': s, 'destruction': 100.0,
             'clan_tag': '#US', 'war_id': start + i,
             'ended_at': T0 + dt.timedelta(days=start + i), 'attack_order': 1}
            for i, s in enumerate(stars_seq)]


def test_a_player_who_dips_after_upgrading_is_measured():
    facts = run('#A', 14, [3] * WINDOW) + run('#A', 15, [1] * WINDOW, start=WINDOW)
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert (row['from_th'], row['to_th']) == (14, 15)
    assert row['before'] == 1.0 and row['after'] == -1.0
    assert row['dip'] == -2.0


def test_a_player_who_improves_after_upgrading_reports_a_positive_dip():
    """The study must be able to find no slump at all."""
    facts = run('#A', 14, [1] * WINDOW) + run('#A', 15, [3] * WINDOW, start=WINDOW)
    assert upgrade_effect(facts, CURVE)['players'][0]['dip'] == 2.0


def test_a_player_who_never_upgraded_is_absent():
    assert upgrade_effect(run('#A', 14, [3] * 40), CURVE)['players'] == []


def test_a_player_one_attack_short_on_either_side_is_absent():
    short_after = (run('#A', 14, [3] * WINDOW) +
                   run('#A', 15, [1] * (MIN_SIDE - 1), start=WINDOW))
    short_before = (run('#B', 14, [3] * (MIN_SIDE - 1)) +
                    run('#B', 15, [1] * WINDOW, start=MIN_SIDE))
    assert upgrade_effect(short_after, CURVE)['players'] == []
    assert upgrade_effect(short_before, CURVE)['players'] == []


def test_exactly_the_minimum_on_each_side_qualifies():
    facts = (run('#A', 14, [3] * MIN_SIDE) +
             run('#A', 15, [1] * MIN_SIDE, start=MIN_SIDE))
    assert len(upgrade_effect(facts, CURVE)['players']) == 1


def test_the_window_is_capped_at_ten_attacks_a_side():
    """A player with fifty attacks before the upgrade is judged on the last ten,
    not on a career average that would drown the effect."""
    facts = (run('#A', 14, [0] * 40 + [3] * WINDOW) +
             run('#A', 15, [1] * WINDOW, start=50))
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert row['n_before'] == WINDOW
    assert row['before'] == 1.0          # the last ten, all 3-star


def test_only_the_first_upgrade_in_the_record_is_measured():
    """Two upgrades in one window would contaminate each other's comparison."""
    facts = (run('#A', 14, [3] * WINDOW) +
             run('#A', 15, [1] * WINDOW, start=WINDOW) +
             run('#A', 16, [0] * WINDOW, start=WINDOW * 2))
    rows = upgrade_effect(facts, CURVE)['players']
    assert len(rows) == 1
    assert (rows[0]['from_th'], rows[0]['to_th']) == (14, 15)


def test_attacks_are_ordered_in_time_not_by_arrival():
    """Facts come out of the loader in table order, not chronological order."""
    late = run('#A', 15, [1] * WINDOW, start=WINDOW)
    early = run('#A', 14, [3] * WINDOW)
    row = upgrade_effect(late + early, CURVE)['players'][0]
    assert row['before'] == 1.0 and row['after'] == -1.0


def test_recovery_is_the_first_point_the_trailing_mean_regains_the_baseline():
    before = run('#A', 14, [2] * WINDOW)                       # sae 0.0
    after  = run('#A', 15, [0] * RECOVERY_WINDOW + [2] * RECOVERY_WINDOW,
                 start=WINDOW)
    row = upgrade_effect(before + after, CURVE)['players'][0]
    assert row['recovered_after'] == WINDOW


def test_a_player_who_never_recovers_reports_none():
    facts = run('#A', 14, [3] * WINDOW) + run('#A', 15, [0] * WINDOW, start=WINDOW)
    assert upgrade_effect(facts, CURVE)['players'][0]['recovered_after'] is None


def test_the_aggregate_averages_the_players_it_found():
    facts = (run('#A', 14, [3] * WINDOW) + run('#A', 15, [1] * WINDOW, start=WINDOW) +
             run('#B', 14, [3] * WINDOW) + run('#B', 15, [2] * WINDOW, start=WINDOW))
    out = upgrade_effect(facts, CURVE)
    assert out['n_players'] == 2
    assert out['mean_dip'] == -1.5       # -2.0 and -1.0


def test_no_facts_yields_an_empty_aggregate_not_a_crash():
    out = upgrade_effect([], CURVE)
    assert out['players'] == [] and out['n_players'] == 0
    assert out['mean_dip'] is None and out['median_recovery'] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_upgrade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights.upgrade'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/upgrade.py`:

```python
# -*- coding: utf-8 -*-
"""Study D - what a town hall upgrade costs, and for how long.

The weakest of the five, and it is presented as an observation rather than a
verdict. Fifteen players clear the thresholds, and an upgrade coincides with
new troops, new defences and whatever else was happening that month; this
measures the bundle, not the upgrade.

The window is a count of attacks rather than a span of days. Players attack at
very different rates, and a calendar window would compare one player's ten
attacks against another's two.
"""

import statistics
from collections import defaultdict

from .curve import sae_of

WINDOW          = 10   # attacks either side of the upgrade
MIN_SIDE        = 5    # fewer than this on either side and the player is skipped
RECOVERY_WINDOW = 5    # trailing attacks averaged when testing for recovery


def _mean(values):
    return sum(values) / len(values) if values else None


def _upgrade_index(facts):
    """Index of the first attack at a higher town hall than anything before it.

    Only the first upgrade is measured. A second upgrade inside the same window
    would contaminate the comparison it is part of.
    """
    ths = [f['attacker_th'] or 0 for f in facts]
    return next((i for i in range(1, len(ths)) if ths[i] > max(ths[:i])), None)


def _recovery_point(after_sae, baseline):
    """Attacks after the upgrade before a trailing mean regains the baseline."""
    for j in range(RECOVERY_WINDOW - 1, len(after_sae)):
        window = after_sae[j - RECOVERY_WINDOW + 1: j + 1]
        if _mean(window) >= baseline:
            return j + 1
    return None


def upgrade_effect(facts, curve):
    """-> {'players', 'n_players', 'mean_dip', 'n_recovered', 'median_recovery'}"""
    by_player = defaultdict(list)
    for f in facts:
        by_player[f['attacker_tag']].append(f)

    rows = []
    for tag, player_facts in by_player.items():
        # The loader returns table order; the whole study depends on time order.
        ordered = sorted(player_facts,
                         key=lambda f: (f['ended_at'], f['attack_order'] or 0))
        idx = _upgrade_index(ordered)
        if idx is None:
            continue

        before = ordered[max(0, idx - WINDOW):idx]
        after  = ordered[idx:idx + WINDOW]
        b_sae  = [d for d in (sae_of(f, curve) for f in before) if d is not None]
        a_sae  = [d for d in (sae_of(f, curve) for f in after) if d is not None]
        if len(b_sae) < MIN_SIDE or len(a_sae) < MIN_SIDE:
            continue

        baseline = _mean(b_sae)
        rows.append({
            'tag':             tag,
            'from_th':         ordered[idx - 1]['attacker_th'],
            'to_th':           ordered[idx]['attacker_th'],
            'before':          baseline,
            'after':           _mean(a_sae),
            'dip':             _mean(a_sae) - baseline,
            'n_before':        len(b_sae),
            'n_after':         len(a_sae),
            'recovered_after': _recovery_point(a_sae, baseline),
        })

    rows.sort(key=lambda r: r['dip'])
    recoveries = [r['recovered_after'] for r in rows if r['recovered_after']]
    return {
        'players':         rows,
        'n_players':       len(rows),
        'mean_dip':        _mean([r['dip'] for r in rows]),
        'n_recovered':     len(recoveries),
        'median_recovery': int(statistics.median(recoveries)) if recoveries else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_upgrade.py -q`
Expected: PASS, 12 passed

Then: `python -m pytest tests/ -q` → 235 passed

- [ ] **Step 5: Check the live population matches the spec**

```bash
python -c "
from app import app
from features.admin.insights.loaders import load_attack_facts
from features.admin.insights.curve import build_curve
from features.admin.insights.upgrade import upgrade_effect
from models import Player
with app.app_context():
    facts = load_attack_facts()
    out = upgrade_effect(facts, build_curve(facts))
    names = {p.tag: p.name for p in Player.query}
    print(f'players {out[\"n_players\"]}  mean dip {out[\"mean_dip\"]:+.3f}  '
          f'recovered {out[\"n_recovered\"]}  median {out[\"median_recovery\"]}')
    for r in out['players'][:3]:
        print(f'  {r[\"dip\"]:+.2f}  {names.get(r[\"tag\"], r[\"tag\"])}  '
              f'TH{r[\"from_th\"]}->{r[\"to_th\"]}')
"
```

Expected: around **15 players** (spec §5). The figure covers everyone with a recorded upgrade, including ex-members — that is correct, it is a study of upgrades rather than of the current roster.

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/upgrade.py tests/test_insights_upgrade.py
git commit -m "feat(insights): measure the performance dip after a town hall upgrade"
```

---

### Task 7: Move the correlation study out of the route

85 lines of study currently live inline in `routes.py`. Four more studies modelled on that would be 400. Move it, split the pure part from the loading part, and give it the tests it never had.

**Files:**
- Create: `features/admin/insights/correlation.py`
- Modify: `features/admin/routes.py` — delete `admin_skill_correlation()` (lines 773–852) and its route
- Test: `tests/test_insights_correlation.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `MIN_PERIODS = 3`
  - `pearson_r(xs, ys) -> float | None`
  - `build_correlation(ranked_scores, raid_scores, players) -> {'players': [...], 'pearson_r': float|None, 'n_correlated': int}` where `ranked_scores` / `raid_scores` are `{tag: [score, ...]}` and `players` is `[{'tag','name','th'}]`.
  - `load_correlation_inputs() -> (ranked_scores, raid_scores, players, ranked_games, raid_attacks)` (DB-aware)

- [ ] **Step 1: Write the failing test**

Create `tests/test_insights_correlation.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.correlation - Study E.

This study shipped inline in routes.py with no tests. The zero-variance guard
below is the one that mattered: a clan where everyone scores the same makes the
denominator zero, and the page would have 500'd rather than saying "no signal".
"""

from features.admin.insights.correlation import (
    MIN_PERIODS,
    build_correlation,
    pearson_r,
)

PLAYERS = [{'tag': '#A', 'name': 'Ann', 'th': 15},
           {'tag': '#B', 'name': 'Bo',  'th': 14},
           {'tag': '#C', 'name': 'Cy',  'th': 13}]


def test_a_perfect_positive_relationship_is_one():
    assert pearson_r([1, 2, 3], [10, 20, 30]) == 1.0


def test_a_perfect_inverse_relationship_is_minus_one():
    assert pearson_r([1, 2, 3], [30, 20, 10]) == -1.0


def test_too_few_points_yield_no_coefficient():
    assert pearson_r([1, 2], [3, 4]) is None


def test_zero_variance_yields_no_coefficient_rather_than_a_crash():
    """Everyone scoring identically is a real state, not an error."""
    assert pearson_r([5, 5, 5], [1, 2, 3]) is None
    assert pearson_r([1, 2, 3], [5, 5, 5]) is None


def test_a_player_averages_across_their_periods():
    out = build_correlation({'#A': [60, 80, 70]}, {'#A': [50, 50, 50]}, PLAYERS[:1])
    row = out['players'][0]
    assert row['ranked_score'] == 70.0
    assert row['raid_score'] == 50.0
    assert row['ranked_weeks'] == 3 and row['raid_weekends'] == 3


def test_a_player_short_of_the_minimum_scores_none_but_still_appears():
    short = [70] * (MIN_PERIODS - 1)
    out = build_correlation({'#A': short}, {'#A': [50] * MIN_PERIODS}, PLAYERS[:1])
    row = out['players'][0]
    assert row['ranked_score'] is None
    assert row['raid_score'] == 50.0
    assert row['ranked_weeks'] == MIN_PERIODS - 1


def test_only_players_scored_on_both_axes_enter_the_correlation():
    out = build_correlation(
        {'#A': [60] * 3, '#B': [70] * 3, '#C': [80] * 3},
        {'#A': [10] * 3, '#B': [20] * 3, '#C': [30] * 1},   # C short on raids
        PLAYERS)
    assert out['n_correlated'] == 2


def test_a_player_with_no_data_at_all_still_appears_with_their_name():
    out = build_correlation({}, {}, PLAYERS[:1])
    row = out['players'][0]
    assert row['name'] == 'Ann' and row['th'] == 15
    assert row['ranked_score'] is None and row['raid_score'] is None


def test_players_sort_by_ranked_score_best_first():
    out = build_correlation(
        {'#A': [60] * 3, '#B': [90] * 3, '#C': [75] * 3},
        {'#A': [10] * 3, '#B': [10] * 3, '#C': [10] * 3}, PLAYERS)
    assert [p['tag'] for p in out['players']] == ['#B', '#C', '#A']


def test_no_players_yields_an_empty_result_not_a_crash():
    out = build_correlation({}, {}, [])
    assert out['players'] == [] and out['pearson_r'] is None
    assert out['n_correlated'] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights_correlation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.admin.insights.correlation'`

- [ ] **Step 3: Write the implementation**

Create `features/admin/insights/correlation.py`:

```python
# -*- coding: utf-8 -*-
"""Study E - does ladder skill predict raid-weekend output?

Lifted out of features/admin/routes.py, where it lived inline behind an AJAX
endpoint. The arithmetic is unchanged; what is new is that the pure part is
separated from the loading part and now has tests.
"""

from collections import defaultdict

MIN_PERIODS = 3   # weeks or weekends before a player's average means anything


def pearson_r(xs, ys):
    """-> r rounded to 3 places, or None when it is undefined.

    Undefined covers two real states: too few players, and no variance on an
    axis. Neither is an error, and neither should raise.
    """
    n = len(xs)
    if n < MIN_PERIODS:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return round(num / den, 3) if den else None


def build_correlation(ranked_scores, raid_scores, players,
                      ranked_games=None, raid_attacks=None):
    """-> {'players', 'pearson_r', 'n_correlated'}

    ranked_scores / raid_scores are {tag: [score per period]}. A player below
    MIN_PERIODS on an axis scores None there and sits out the correlation, but
    still appears in the table - the roster should not silently shrink.
    """
    ranked_games = ranked_games or {}
    raid_attacks = raid_attacks or {}

    rows, xs, ys = [], [], []
    for p in players:
        tag = p['tag']
        rk, rd = ranked_scores.get(tag, []), raid_scores.get(tag, [])
        ranked = round(sum(rk) / len(rk), 1) if len(rk) >= MIN_PERIODS else None
        raid   = round(sum(rd) / len(rd), 1) if len(rd) >= MIN_PERIODS else None

        rows.append({
            'tag': tag, 'name': p['name'], 'th': p['th'],
            'ranked_score': ranked, 'ranked_weeks': len(rk),
            'ranked_games': ranked_games.get(tag, 0),
            'raid_score': raid, 'raid_weekends': len(rd),
            'raid_attacks': raid_attacks.get(tag, 0),
        })
        if ranked is not None and raid is not None:
            xs.append(ranked)
            ys.append(raid)

    rows.sort(key=lambda r: -(r['ranked_score'] or -1))
    return {'players': rows, 'pearson_r': pearson_r(xs, ys), 'n_correlated': len(xs)}


def load_correlation_inputs():
    """Per-player ranked-week and raid-weekend score series. Needs an app context."""
    from extensions import db
    from models import Player, RankedWeek, RaidWeekendLog
    from services.helpers import _calc_ranked_score, _raid_verdict

    players = Player.query.filter_by(in_clan=True).all()
    tags    = [p.tag for p in players]

    ranked_scores, ranked_games = defaultdict(list), defaultdict(int)
    weeks = (RankedWeek.query
             .filter(RankedWeek.player_tag.in_(tags), RankedWeek.is_done == True)
             .options(db.joinedload(RankedWeek.battle_logs))
             .all())
    for week in weeks:
        attacks = sum(1 for l in week.battle_logs if l.attack)
        if not attacks:
            continue
        score, _, _ = _calc_ranked_score(week.battle_logs, week.townhall or 0,
                                         week.max_attacks or attacks,
                                         week.league_tier or '')
        ranked_scores[week.player_tag].append(score)
        ranked_games[week.player_tag] += attacks

    per_weekend = defaultdict(list)
    for log in RaidWeekendLog.query.filter(RaidWeekendLog.player_tag.in_(tags)).all():
        per_weekend[(log.player_tag, log.raid_weekend_id)].append(log)

    raid_scores, raid_attacks = defaultdict(list), defaultdict(int)
    for (tag, _), logs in per_weekend.items():
        if not logs:
            continue
        _, _, score = _raid_verdict(logs)
        raid_scores[tag].append(score)
        raid_attacks[tag] += len(logs)

    roster = [{'tag': p.tag, 'name': p.name or p.tag, 'th': p.current_th or 0}
              for p in players]
    return ranked_scores, raid_scores, roster, ranked_games, raid_attacks
```

- [ ] **Step 4: Delete the old inline endpoint**

In `features/admin/routes.py`, delete the whole `admin_skill_correlation()` function including its `@admin_bp.route('/admin/skill-correlation')` and `@require_super_admin` decorators — lines **773–852**, from the route decorator through `return jsonify(players=result, pearson_r=pearson_r(xs, ys), n_correlated=len(xs))`. Leave the `# ── CWL Roster Recommendation ──` comment at line 855.

Confirm nothing else referenced it:

Run: `grep -rn "skill-correlation\|skill_correlation" --include=*.py --include=*.html .`
Expected: only the two mentions in `admin_insights.html` (its `fetch()` call and a comment) and the stale comment in `admin_insights()`. Those are the template's, and Task 8 plus the `/impeccable` pass replace them. No other Python reference.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_insights_correlation.py -q`
Expected: PASS, 10 passed

Then: `python -m pytest tests/ -q` → 245 passed

Then confirm the app still imports with the endpoint gone:

Run: `python -c "from app import app; print(len(list(app.url_map.iter_rules())), 'routes')"`
Expected: prints a route count, no exception.

- [ ] **Step 6: Verify the moved study reproduces the old numbers**

```bash
python -c "
from app import app
from features.admin.insights.correlation import build_correlation, load_correlation_inputs
with app.app_context():
    rk, rd, roster, games, atts = load_correlation_inputs()
    out = build_correlation(rk, rd, roster, games, atts)
    print(f'players {len(out[\"players\"])}  r {out[\"pearson_r\"]}  n {out[\"n_correlated\"]}')
"
```

Expected: 44 players, a Pearson r, and `n_correlated` matching what `/admin/skill-correlation` returned before the move. The arithmetic did not change, so the numbers must not either.

- [ ] **Step 7: Commit**

```bash
git add features/admin/insights/correlation.py tests/test_insights_correlation.py features/admin/routes.py
git commit -m "refactor(insights): move the skill correlation out of the route and test it"
```

---

### Task 8: Assemble the briefing and wire the route

**Files:**
- Modify: `features/admin/insights/__init__.py`
- Modify: `features/admin/routes.py` — `admin_insights()` (lines 63–69)

**Interfaces:**
- Consumes: every study module.
- Produces: `build_briefing() -> dict` with keys `curve`, `players_sae`, `benchmark`, `consistency_ranked`, `consistency_raid`, `contrast_ranked`, `upgrade`, `correlation`, `names`, `our_clan_tag`.

- [ ] **Step 1: Write the implementation**

Replace `features/admin/insights/__init__.py`:

```python
# -*- coding: utf-8 -*-
"""Assembles the five Insights studies into one briefing.

Every study is viewer-invariant - the same answer for every admin - so the
result is cached rather than recomputed per view. The key is a census of the
source tables, so new wars, weeks or raids invalidate it on arrival; the TTL is
only a backstop for edits that do not change a row count.
"""

import datetime as dt

from . import benchmark, consistency, correlation, curve, upgrade
from .loaders import load_attack_facts

_CACHE = {}
_TTL   = 600          # seconds


def _data_version():
    """Row counts across the source tables. Cheap, and it changes on any sync."""
    from models import ClanWarAttack, CWLAttack, RaidWeekendLog, RankedWeek
    return (ClanWarAttack.query.count(), CWLAttack.query.count(),
            RankedWeek.query.count(), RaidWeekendLog.query.count())


def build_briefing():
    """-> the whole page's data. Requires an app context."""
    key = _data_version()
    now = dt.datetime.now().timestamp()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]

    from models import Player

    facts = load_attack_facts()
    fitted = curve.build_curve(facts)
    our_tag = _our_clan_tag()

    ranked_scores, raid_scores, roster, games, attacks = \
        correlation.load_correlation_inputs()

    ranked_rows = consistency.consistency(ranked_scores,
                                          consistency.MIN_RANKED_WEEKS)
    raid_rows   = consistency.consistency(raid_scores,
                                          consistency.MIN_RAID_WEEKENDS)

    data = {
        'curve':              fitted,
        'players_sae':        curve.player_sae(facts, fitted),
        'benchmark':          benchmark.clan_ranking(facts, fitted, our_tag),
        'consistency_ranked': ranked_rows,
        'consistency_raid':   raid_rows,
        'contrast_ranked':    consistency.contrast_pair(ranked_rows),
        'upgrade':            upgrade.upgrade_effect(facts, fitted),
        'correlation':        correlation.build_correlation(
                                  ranked_scores, raid_scores, roster,
                                  games, attacks),
        'names':              {p.tag: p.name or p.tag for p in Player.query.all()},
        'our_clan_tag':       our_tag,
    }

    _CACHE.clear()          # only the newest version is worth holding
    _CACHE[key] = (now + _TTL, data)
    return data


def _our_clan_tag():
    """The clan this installation tracks, read from the war history."""
    from models import ClanWar
    row = (ClanWar.query.filter(ClanWar.clan_tag.isnot(None))
           .order_by(ClanWar.id.desc()).first())
    return row.clan_tag if row else None
```

- [ ] **Step 2: Wire the route**

In `features/admin/routes.py`, replace `admin_insights()` (lines 63–69) with:

```python
@admin_bp.route('/admin/insights')
@require_super_admin
def admin_insights():
    # Clan-analytics home. Five studies over the war, CWL, ranked and raid
    # tables, computed on load behind a data-version cache — they are
    # viewer-invariant, so there is nothing to gain from making the admin ask.
    from features.admin.insights import build_briefing
    return render_template('admin/admin_insights.html', **build_briefing())
```

- [ ] **Step 3: Verify the whole briefing computes on live data**

```bash
python -c "
from app import app
from features.admin.insights import build_briefing
import time
with app.app_context():
    t = time.time(); d = build_briefing(); cold = time.time() - t
    t = time.time(); build_briefing();     warm = time.time() - t
    print(f'cold {cold*1000:.0f}ms   warm {warm*1000:.0f}ms')
    print(f'curve buckets   {len(d[\"curve\"])}')
    print(f'players ranked  {sum(1 for r in d[\"players_sae\"] if not r[\"thin\"])}')
    print(f'clans ranked    {len(d[\"benchmark\"])}')
    print(f'consistency     {len(d[\"consistency_ranked\"])} ranked, {len(d[\"consistency_raid\"])} raid')
    print(f'upgrade players {d[\"upgrade\"][\"n_players\"]}')
    print(f'pearson r       {d[\"correlation\"][\"pearson_r\"]}')
    assert d['our_clan_tag'], 'clan tag not resolved'
"
```

Expected: 14 curve buckets, 27 players ranked, 22 clans, 26 and 31 consistency rows, ~15 upgrade players, a Pearson r. Warm should be near zero. If cold exceeds ~2s, say so — the cache hides it from users but it still runs on the first view after every sync.

- [ ] **Step 4: Verify the page still serves**

The existing template will render with its old markup and its `fetch()` to the now-deleted endpoint; that is expected and the `/impeccable` pass replaces it. What matters is that the route returns 200 rather than 500.

```bash
python -c "
from app import app
with app.app_context():
    with app.test_client() as c:
        with c.session_transaction() as s:
            s['env_admin_logged_in'] = True
        r = c.get('/admin/insights')
        print(r.status_code, len(r.data), 'bytes')
        assert r.status_code == 200, r.status_code
"
```

Expected: `200` and a byte count.

`require_super_admin` accepts either the env admin flag or an `AppUser` that is
both `is_approved` and `is_super_admin` (`features/auth/routes.py:86-97`). The
env flag is used here because it needs no user row and no password.

A `302` means the session key was rejected, not that the page failed — check
`_is_super_admin` before assuming the route is broken.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: 245 passed

- [ ] **Step 6: Commit**

```bash
git add features/admin/insights/__init__.py features/admin/routes.py
git commit -m "feat(insights): serve all five studies from the route behind a data-version cache"
```

---

## After this plan

The engine is done and tested; the page is not. Next, in a separate pass:

1. `/impeccable` on `/admin/insights` — **mockups first**, per spec §8 and how the war, CWL and admin redesigns went. Five findings on one page is a real IA problem and drawing it in code first is how the reverted Monitor attempt started.
2. Rebuild `admin_insights.html` against the briefing dict: remove `runCorr()` and the `fetch('/admin/skill-correlation')` call, keep the `escapeHTML` helper and the `TH_COLORS` token map, which the new page still needs.
3. `/impeccable audit` before merge.

## Self-Review

**Spec coverage.** §1 problem → Task 8 (briefing replaces the Run button). §2 `is_opponent` trap → Task 1, tests 2–4, and re-checked live in Task 4 Step 5. §3 decisions: briefing → Task 8; name both ends → sorted rankings in Tasks 3–5; thin marked not ranked → `thin` flag in every study; separate war/CWL curves → Task 2; whole-group baseline → Task 4; D's caveat → carried in the module docstring, and the page copy lands in the `/impeccable` pass. §4 studies A–E → Tasks 2–7. §5 thresholds → all seven constants defined, and each live-check step asserts the qualifying population. §6 architecture and the fact contract → Tasks 1 and 8. §7 testing: curve edges, SAE sign, thresholds, the §2 regression, empty and degenerate inputs, teeth check → all present, teeth check in Task 2 Step 5. §8 visual → deliberately out, handed off above.

**Gap found and closed.** §7 asks for a zero-variance test — "the denominator case that killed the first Pearson implementation". That belongs to Study E, which was nearly scoped as a pure move; Task 7 now tests it explicitly.

**Type consistency.** Fact keys are identical in the loader, its test's `FACT_KEYS`, and every study's fixtures. `sae_of(fact, curve)` and `clamp_diff(attacker_th, defender_th)` keep one signature across Tasks 3, 4 and 6. `thin` is a bool in all four studies that rank. `build_curve` returns buckets whose `mean_stars` may be `None`, and every consumer checks for it.

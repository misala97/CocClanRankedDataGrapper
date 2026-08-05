# Insights deep-dive analytics — design

Date: 2026-08-05 · Branch: `dev_coc`

Turn `/admin/insights` from a one-tool shell into a briefing of five studies over
data the app already collects and has never looked at.

## 1. Where it stands

`/admin/insights` holds one module: the ranked×raid Pearson correlation, behind a
**Run analysis** button. Until you press it the page is empty, and the tab has
been empty since it was split off the Skill Correlation tool during the admin
redesign.

The tables underneath it are not empty. Measured 2026-08-05:

| table | rows | span |
|---|---|---|
| `clan_war_attack` | 877 | 12 wars, 2026-06-01 → 2026-07-23 |
| `cwl_attack` | 2,417 | 84 wars, **22 clans** |
| `ranked_battle_log` | 6,053 | 302 completed weeks |
| `raid_weekend_log` | 1,557 | 10 weekends |
| `player` (in clan) | 44 | TH 9–18 |

Nothing in the app joins an attack to the **town hall it was aimed at**. That
join is the largest unused seam in the schema, and three of the five studies
below rest on it.

## 2. The `is_opponent` trap

`cwl_member.is_opponent` is relative to each war's own perspective. Our clan is
*the clan* in its seven wars and *the opponent* in rivals' wars, because the CWL
tables hold the whole group. Filtering our attacks on `is_opponent = 0` answers a
different question than filtering on `clan_tag`:

```
same-TH triple rate, our clan   is_opponent = 0  →  44.8%   (n=137 of a partial slice)
                                clan_tag match   →  67.9%   (n=137, correct)
```

One of those is wrong and both look plausible. **`clan_tag` is the only correct
clan filter in CWL.** This is closed once, in the loader (§6), so no study can
reintroduce it.

Regular war reaches the same place by a different route: `clan_war_member` has
**no** `clan_tag` column, so the loader derives one — `is_opponent = 0` takes
`clan_war.clan_tag`, `is_opponent = 1` takes `clan_war.opponent_tag`. After that
both sources carry the same field and `is_opponent` never leaves the loader.

## 3. Decisions

1. **A briefing, not a lab.** The page opens with findings already stated; no Run
   buttons, including on the existing correlation module. All five studies are
   viewer-invariant and the dataset is small, so they compute on load behind a
   cache. A page that opens empty is the problem being fixed; five buttons would
   still open empty.
2. **Findings name both ends.** Over- and under-performers are named and ranked.
   The page is `@require_super_admin`, and the house voice is already blunt
   (`is_troll`, `is_rushed`, a verdict badge labelled *Useless*).
3. **Thin samples are marked, not ranked.** Below a study's threshold a player is
   listed with a thin-data marker and excluded from the ranking and from any
   named finding. Bluntness is a tone decision; sample size is not.
4. **War and CWL get separate curves.** They are not the same game — 76.6% vs
   44.8% same-TH triples. Pooling them would flatter CWL and libel war.
5. **The CWL baseline is the whole group**, all 22 clans, not just us. A
   self-referential baseline cannot tell you whether you are good.
6. **Study D ships with its caveat visible.** n=23 and confounded; it is offered
   as an observation, not a verdict.

## 4. The five studies

### A · The difficulty curve

Bucket every war and CWL attack by `defender_th − attacker_th`. Both sides of
every war feed the curve — opponent attacks are 408 of the 877 war rows and are
just as valid as evidence of what a differential costs.

```
E[stars | src, diff] = mean stars over all attacks in that bucket, every clan
```

Differentials clamp to `[-3, +3]`, tails as `≤-3` / `≥+3`; the war tail runs to
+7 on single attacks. A bucket with n < 20 merges into its nearer neighbour and
is reported as merged.

Both joins are lossless — every one of the 877 war and 2,417 CWL attacks lands
in a bucket, no orphans — and all 14 buckets clear n=20 today:

```
cwl   -3: 33   -2: 134   -1: 440   0: 1195   +1: 448   +2: 134   +3: 33
war   -3: 78   -2:  64   -1: 141   0:  354   +1: 150   +2:  56   +3: 34
```

So the merge rule never fires on current data. It stays anyway — it is the guard
for a thin future season, and a rule that only appears under conditions nobody
has seen is exactly the kind that ships broken. It gets a test (§7).

Per player, over their own attacks:

```
SAE = Σ(stars − E[stars | src, diff]) / n        "stars above expectation"
```

This is the point of the study. Raw stars reward whoever gets easy matchups; SAE
asks whether you did better than this clan's own attacks at that differential
normally do. A TH12 farming down and a TH15 always attacking up finally compare.

Findings: where the cliff is (between +1 and +2 on current data, not where
people assume), what one TH up costs in triple rate, and who is above and below
the curve.

### B · The group benchmark

Run all 22 clans through A's model. Rank on SAE per attack, not raw stars — a
clan with a top-heavy roster otherwise wins on matchup luck alone.

Reports our rank, our percentile, and per-differential us-vs-group. Current
same-TH figures: us 67.9% (n=137), group 54.5% (n=1,058).

CWL only. Regular war has no rival population.

### C · Consistency

Per player per mode — mean, standard deviation, floor, ceiling, n — over ranked
week scores (`_calc_ranked_score`) and raid weekend scores (`_raid_verdict`).

The finding names two players with near-identical means and different σ. That
contrast is the study; the mean is already elsewhere in the app.

### D · Post-upgrade slump

23 players have attacks on both sides of a town hall change. The upgrade point is
their first attack at the new TH, ordered by `(war.end_time, attack_order)` —
complete on all 12 wars and all 84 CWL wars.

The window is **the 10 attacks either side of that point**, or all available if a
player has fewer, subject to the 5-per-side minimum in §5. Fixed at a count of
attacks rather than a span of days: players attack at very different rates, and a
calendar window would compare one player's ten attacks against another's two.

Compare mean SAE before against mean SAE after, per player, then aggregate:
mean dip, and attacks-to-recovery measured as the first point where a trailing
5-attack mean SAE returns to the player's pre-upgrade mean.

**Stated on the page:** n=23, confounded with everything else in that player's
life, and offered as an observation rather than a verdict.

### E · Ranked × Raid

The existing Pearson r, unchanged in method, converted from a Run button to a
stated finding.

## 5. Thresholds

Measured against the live tables 2026-08-05:

| study | unit | minimum | qualifying today |
|---|---|---|---|
| A | player | 8 attacks | **27** of 44 in clan |
| A | curve bucket | 20 attacks, else merge | 7 of 7 both sources |
| B | clan | 30 attacks | **22** of 22 |
| C | player, ranked | 6 completed weeks | 26 |
| C | player, raid | 4 weekends | 31 |
| D | player | 5 attacks each side | **15** of the 23 with a TH change |
| E | player | 3 weeks and 3 weekends | unchanged |

Every threshold clears a usable population today, and none of them is doing
nothing — A excludes 17 players, D excludes 8. They are real filters, not
decoration.

## 6. Architecture

Follows the pattern proven by `/ranked/stats` and `monitor_stats` — pure modules
taking plain rows, a thin route, real tests.

```
features/admin/insights/
    __init__.py
    loaders.py       the only DB-aware file: ORM → plain fact rows
    curve.py         A — buckets, expected-stars model, per-player SAE
    benchmark.py     B — all 22 clans through curve.py's model
    consistency.py   C — mean, σ, floor, ceiling
    upgrade.py       D — before/after a TH change
    correlation.py   E — lifted out of routes.py
```

`loaders.py` emits one normalized attack fact that A, B and D all consume:

```python
{'src': 'war'|'cwl', 'war_id', 'ended_at',
 'attacker_tag', 'attacker_th', 'defender_th',
 'stars', 'destruction', 'clan_tag', 'attack_order'}
```

`clan_tag` sits on the fact row deliberately — it is how §2 stays closed. No
study sees `is_opponent` at all.

`curve.py` exposes the model as a value, not a side effect:

```python
build_curve(facts)          -> {(src, diff): {'n', 'mean_stars', 'triple_rate', 'merged'}}
player_sae(facts, curve)    -> [{'tag', 'n', 'sae', 'thin'}]
```

`benchmark.py` and `upgrade.py` take that same curve object rather than refitting
it. One model, three consumers.

**Route** computes all five and renders. No AJAX. Cached on a data-version key
(max `last_updated` across the source tables), the shape already used by
`_BULK_STANDING_CACHE`.

**Moving `correlation.py` out of `routes.py`** is not scope creep: it is the 85
inline lines that four more studies would otherwise be modelled on.

## 7. Testing

Studies are pure, so tests use `SimpleNamespace` fact rows and no database —
the same discipline as the 177 tests currently passing.

- The curve: known fact rows in, known expectations out; bucket merging at the
  n<20 boundary; clamping at `≤-3` / `≥+3`.
- SAE sign: an attacker who beats expectation everywhere scores positive, and
  one who trails it scores negative, *with identical raw stars*. This is the
  assertion the whole study rests on.
- Thresholds: a player one attack under the minimum is marked thin and absent
  from the ranking; one attack over is ranked.
- §2 as a regression test: a fact set where `is_opponent` and `clan_tag` disagree
  must produce the `clan_tag` answer.
- Empty and degenerate inputs: no attacks, one attack, all attacks at one
  differential (zero variance — the denominator case that killed the first
  Pearson implementation).
- **Teeth checks** on every assertion whose passing state is an absence: break
  the guard, confirm the test fails, restore. Per prior findings, a test that
  asserts "nothing bad appears" passes just as happily when nothing appears at
  all.

## 8. Visual execution

This spec locks structure and content only. Layout, type, colour and the
briefing's visual voice go through `/impeccable`, **mockups before code**, as the
war, CWL and admin redesigns did.

## 9. Out of scope

- Attack-*timing* effects. `attack_order` exists but there is no per-attack
  timestamp, so "last-minute attacker" would be a proxy dressed as a clock.
- Any change to `_calc_ranked_score`, `_raid_verdict` or the war scoring. The
  studies consume the existing scores; recalibrating them is its own decision and
  was explicitly settled against for raids.
- A cross-mode participation matrix. It is a table, not a study.
- Exposing any of this outside `@require_super_admin`.

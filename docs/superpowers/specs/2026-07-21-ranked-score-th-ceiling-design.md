# Ranked Score: Per-TH Ceiling Normalization

## Problem

The ranked-week verdict formula (`services/helpers.py`) scores each attack by TH-difficulty multiplier (`_calc_th_multiplier`), sums the adjusted stars across the week, then normalizes to a 0–100 scale in `_ranked_score_from_adj` by dividing by a flat constant, `3.45` (= 3 stars × 1.15, the highest multiplier the table ever produces).

That constant is only reachable by townhall levels ≤16, which can be matched against opponents 2+ TH levels above them (multiplier 1.15). Max townhall (18) can never face a higher-TH opponent — its ceiling multiplier is 1.00. TH17's ceiling is 1.05 (can only ever punch up one level, against TH18).

Because every TH divides by the same `3.45`, a flawless week (3-starring every attack) tops out at:
- TH ≤16: 100
- TH17: ≈91
- TH18: ≈87

Confirmed against the live 2-month import (326 scored ranked weeks): every occurrence of multiplier `1.00` (713 attacks) belongs to a TH18 player; no TH18 attack in the dataset ever received a bonus multiplier. Reaching "Godlike" (score ≥87) at TH18 requires a literally perfect week with zero slack for even one 2★ attack, while lower TH levels have real margin for error whenever matchmaking gives them an upward matchup.

## Fix

Add a helper that mirrors `_calc_th_multiplier`'s own branching, so the normalization ceiling can never drift out of sync with the multiplier table it measures:

```python
def _max_th_multiplier(player_th):
    if player_th >= 18: return 1.00
    if player_th == 17: return 1.05
    return 1.15
```

`_ranked_score_from_adj` replaces the hardcoded `3.45` with `3 * _max_th_multiplier(player_th)`:

```python
def _ranked_score_from_adj(adj_scores, max_attacks, league_tier, player_th):
    lm = _league_mult(league_tier, player_th)
    if not max_attacks:
        return 0, 0.0, lm
    th_adj = sum(adj_scores) / max_attacks
    ceiling = 3 * _max_th_multiplier(player_th)
    return min(round(th_adj * lm * 100 / ceiling), 100), th_adj, lm
```

Single call site — every consumer (`_calc_ranked_score`, the live weekly-scoring route, the season-stats accumulator) funnels through `_ranked_score_from_adj`, so the fix applies everywhere at once.

`player_th == 0` (missing townhall data) falls into the `else` branch → 1.15 → ceiling 3.45, identical to current behavior. No new error path.

## Explicitly out of scope

Decided during brainstorming, not to be touched by this change:
- The `diff <= -3` multiplier cliff (0.75 → 0.01) — real but rare (2 occurrences in 2 months); left as-is.
- `EXPECTED_LEAGUE_RANK` headroom asymmetry (TH15's expected slot at 17/36 leaves more room to earn league bonus than TH18's at 26/36) — a separate, softer effect; left as-is.
- Missing-attack averaging, `badge-useless` sharing between "0 attacks" and "low score", and the score-vs-rank axis divergence — all reviewed during analysis and found to be working as intended.

## Blast radius

- TH≤16 scores: byte-for-byte unchanged (still divided by 3.45).
- TH17/TH18 scores: shift upward. Some weeks will cross verdict-tier boundaries (e.g. a week that scored 82/Dominant may now score ~88/Godlike).
- `_league_mult`, verdict thresholds (87/80/65/58/43/29), and missing-attack math: untouched.

## Verification plan

No test suite covers this path (this project verifies manually against real data rather than via pytest). Plan:

1. **Snapshot (before).** Run a script against the dev server's live-imported DB that recomputes `score_100` + verdict badge for all 326 currently-scored `RankedWeek` rows using the *current* formula, keyed by `(player_tag, league_season_id)`. Save to a scratch JSON file.
2. **Apply the fix** to `services/helpers.py`.
3. **Snapshot (after).** Re-run the same script with the patched formula.
4. **Diff.** Compare before/after per row: score delta, badge change. Summarize by TH level (this is the whole point of the fix — TH17/18 should show upward movement, TH≤16 should show zero movement) and list every row whose verdict badge actually flipped tiers, so the user can eyeball real before/after performances and judge whether the new numbers feel right before committing.
5. User reviews the diff and decides whether to commit.

## Rollout

Code-only change on `dev_coc`. This app deploys via git, not manual server commands — commit only, no deploy step, once the before/after comparison is approved.

# Ranked Week — Long-Term Stats Page ("The Record")

**Date:** 2026-07-21
**Route:** `/ranked/stats`
**Status:** design approved, not implemented

## Context

The existing `/ranked/stats` page is a throwaway placeholder. This design replaces it
entirely; nothing about its current structure constrains what follows.

`/ranked` covers the current week. `/player/<tag>` is a cross-mode profile where Ranked
is one summary score among war/raid/battle. No Ranked deep-dive exists anywhere on the
site. This page fills that gap and owns the long-term Ranked story.

### Data the design was derived from

Dev database, 10 seasons, 2026-05-18 to 2026-07-21. 326 player-weeks across 63 players
(44 in clan), 6053 `ranked_battle_log` rows (3310 attacks, 2743 defenses). 261 completed
in-clan player-weeks after filtering.

Findings that drove design decisions, each verified against the database:

- The site's `_calc_ranked_score` behaves well over the long run: median 73, mean 67.1,
  p10 33, p90 89, full 0-100 range used, and all seven `_ranked_verdict` bands populated
  (Very Good 86, Dominant 49, Godlike 39, Bad 30, Good 28, Useless 13, No Attacks 12,
  Disaster 4).
- Mean, standard deviation, and trend separate players sharply. Trend spans +34.0
  (369alex) to -37.3 (N0RM4LPL4Y3R). Sigma spans 1.4 (Misala) to 29.1 (finn_2502).
- League tier is a numbered ladder (Skeleton 1 through Electro 33, then Legend III/II/I)
  and every player has a weekly promotion/demotion path. League movement tracks score but
  lags it badly — Germinator moved 23 to 24 across nine weeks whose scores ranged 0 to 84.
- Attendance is bimodal, not a gradient: 27 of 37 players sit at exactly 100%, then a
  cliff to 76%, 62%, 59%, then IAmDreamwing at 1 of 64 attacks.
- `ranked_battle_log.trophies` is a deterministic 0-40 per-battle score (attack: 3* = 40,
  2* = 16-32 scaling with destruction, 1* = 8-15, 0* = 0-4; defense mirrors it, held 0*
  = 40 down to 3* conceded = 0). Per-player mean trophies-per-defense spans 1.7 to 25.8.
- Defense quality falls steeply with league, so raw comparison across leagues is invalid.
  Mean trophies-per-defense by league band: 16-20 = 17.3, 21-25 = 12.8, 26-30 = 11.1,
  31-35 = 6.7, Legend = 8.1. Bands below rank 16 are thin (n = 86-161) and non-monotone.
- Near-miss rate discriminates independently of skill. Reaper: 15.1% of attacks are 2* at
  >= 90% destruction against only 18.9% 3*. Fremdwort: 11.9% near-miss against 60% 3*.

### Verified data-integrity facts

These were checked because the design makes public claims about named players:

- The "Absent" finding is genuine, not a sync failure. Dreamwing and IAmDreamwing weeks
  have complete `RankedWeek` rows with `attack_wins = 0` **and** 5-12 logged defenses per
  week, so the API sync was working. Their 182-431 trophies are entirely defensive.
- `attack_wins + attack_losses` is a reliable attacks-used measure: 2 mismatches against
  logged attacks in 296 completed weeks, average gap -0.02.
- `ranked_battle_log` is a rolling API sample and is sometimes short of the true total
  (observed week: 370 logged trophies against 454 recorded on `ranked_week`). `RankedWeek`
  is therefore authoritative for totals; logs are used only for distributions.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Merit unit | Existing `_calc_ranked_score` (0-100) + `_ranked_verdict` bands | Keeps this page speaking the same language as `/ranked`, player profiles, and skill correlation |
| Defense | Second axis, its own module, league-normalized | The score is attack-only; defense is ~22% of trophies earned and has a 1.7-25.8 spread that nothing else on the site surfaces |
| Personal detail | In-page drill-down from the roster row | One URL holds the whole Ranked story; serves leadership and members from the same surface |
| Page spine | Time / trajectory ("The Ledger") | "Long-term" means the time axis is the subject; the leadership goal names trends, consistency, improving/declining directly; trend and sigma are where the data's signal is strongest |

The league climb and the capability-typing framings were considered as alternative spines
and rejected as spines, but absorbed: the ladder appears as movement in the roster row and
as markers on the drill-down career line; the typing drives the Movers band computation and
the drill-down header.

## Metric definitions

Window = completed seasons only (`is_done = 1`). The in-progress season is excluded from
every aggregate. Window is selectable: Last 4 / Last 12 / All, defaulting to All.

| Metric | Definition |
|---|---|
| `mean` | Mean of per-week `_calc_ranked_score` results |
| `sigma` | Population standard deviation of those weekly scores |
| `trend` | Points of score. n >= 6: mean(last 3) - mean(prior 3). 4 <= n < 6: mean(last 2) - mean(first 2). n < 4: null, no trend rendered |
| `attendance` | Sum(`attack_wins` + `attack_losses`) / Sum(`max_attacks`) |
| `league_move` | `_get_league_rank` at the player's last played week in the window minus at their first played week in the window. Not the window's calendar bounds — a player who joined mid-window is measured across the weeks they actually played |
| `reliability` | Word rendered from `sigma`: metronome < 5, steady 5-9.9, swingy 10-14.9, erratic >= 15. The erratic cut is the same constant as the Unreliable band threshold |
| `def_index` | Player mean trophies-per-defense minus band expectation. Bands are 5 league ranks wide plus a Legend band. Bands with n < 250 defenses fall back to the global mean and render a "thin data" flag |
| `verdict_record` | Count of weeks in each of the 7 `_ranked_verdict` bands |

All thresholds are named module constants, never inline literals.

## Structure

### Zone 1 — Clan Form

Opens on a verdict about direction, not a leaderboard. Computed from clan mean of the last
3 completed seasons against the prior 3, mapped to Climbing / Holding / Slipping. On
current data this reads Slipping: peak 71.5 on 08.06, now 64.5.

Supporting content: clan mean line across all completed seasons with participant count per
point; delta against peak with the peak's date; roster depth, defined as the count of
players whose `mean` is at or above the Good band cutoff (58). The live season appears on
the line as a pending marker and is never included in the math.

### Zone 2 — Movers

Four lists, no chart. Each entry carries the number and the weeks behind it, and opens the
drill-down on click.

- **Surging** — trend >= +8 points
- **Sliding** — trend <= -8 points
- **Unreliable** — sigma >= 15 at any mean
- **Absent** — attendance < 50%

Surging, Sliding, and Unreliable all require n >= 4 completed weeks, since `trend` and
`sigma` are not meaningful below that. Absent has no n requirement.

Absent players are excluded from the Zone 3 ranking regardless of how many weeks they
played, and appear only here and in the Zone 3 tail. They would otherwise drag the roster
ranking with scores that measure non-participation rather than performance. An Absent
player who is also Sliding or Unreliable is listed under Absent only — it is the actionable
fact and the others are downstream of it.

A band with no qualifying players renders "none this window". Thresholds are never lowered
to fill space.

### Zone 3 — The Record

Roster table, sorted by `mean` descending, sortable by any column. Per row:

rank, name, TH, **mean** (colored by verdict band), **sparkline** of weekly scores across
the window, **reliability** as a word rather than a raw sigma, **trend**, **attendance**
*rendered only when below 100%* (27 of 37 players are at exactly 100%, so printing it every
row is noise), **league** tier plus net movement, **def_index**, and **verdict record** as
a compact 7-band strip.

The tail below the ranking holds two groups, labelled separately: players with fewer than 3
completed weeks ("not enough data") and Absent players ("not participating"). Neither
interleaves into the ranking.

### Zone 4 — Drill-down

Expands in place from the roster row. Opens with a characterization derived from mean,
sigma, trend, and attendance (for example "elite metronome", "boom-or-bust", "collapsing").

- **Career line** — weekly score across all weeks, with TH-upgrade and league
  promotion/demotion markers on the same axis. Shows what an upgrade costs and what a good
  run buys; nothing else on the site shows this.
- **Where the points go** — per TH-matchup bucket (-2 or lower, -1, 0, +1, +2 or higher;
  the observed range is -3 to +3), attacks and
  mean stars against the clan mean for that same bucket. A bucket renders only at n >= 10.
  Players with a single populated bucket (ruwell: 260 even-TH, 0 elsewhere) are told they
  have only faced one matchup, which is itself the finding.
- **Near-misses** — count of 2* attacks at >= 90% destruction, framed as attacks that were
  one building short of a 3*.
- **Attendance record** — which weeks were short and by how much, since missed attacks
  divide directly into the score.
- **Defense** — trophies-per-defense over time against band expectation, plus the star mix
  conceded.
- **Verdict record** — band counts, best and worst week with dates.

## Implementation shape

Aggregation moves out of the route into `features/ranked/stats.py` as pure functions
taking `(weeks, logs)` and returning dicts, testable without HTTP. The current route holds
290 lines of inline aggregation; the new route stays thin and calls into that module.

Scoring is reused, never reimplemented: `_calc_ranked_score`, `_ranked_verdict`,
`_get_league_rank`, and `_is_attack` all come from `services/helpers.py`.

Clan aggregates are viewer-invariant, so results are cached per `(window, roster)` using
the existing `_BULK_STANDING_CACHE` pattern.

Drill-down data ships inline in the initial payload — 261 player-weeks plus pre-bucketed
log aggregates, comfortably under 200KB — so expanding a row is instant with no fetch.

Visual execution (palette, typography, signature element, motion) is not specified here. It
goes through the `impeccable` skill after this structure is locked.

## Edge cases

- Season `1780894800` spans 14 days rather than 7. Treated as a single season; labels come
  from `start_day`.
- Rows with 0 attacks score 0 and land in the "No Attacks" verdict band. They count toward
  attendance and the Absent band, and are excluded from the mean-score ranking.
- `RankedWeek` is authoritative for attendance, trophies, and rank. `ranked_battle_log` is
  a rolling sample used only for quality distributions, and every per-attack statistic
  states its n.
- The page filters `in_clan = True`, so players who leave lose their history from this
  view. This matches the rest of the site and is accepted.
- Defense bands below league rank 16 are thin and non-monotone; they fall back to the
  global mean and are flagged rather than presented as precise.

## Cut deliberately

- **Attack-timing decay.** The aggregate gradient is real (day 0 of week: 32.8 trophies per
  attack and 57% 3*; day 7: 24.4 and 32%) but confounded by player composition, and 163 of
  288 player-weeks completed every attack on a single calendar day, so per-player n is a
  single point. The causal claim cannot be supported, so the module does not ship.
- **Nemesis / recurring-opponent analysis.** 3302 distinct opponents across 3310 attacks.
  Repeats effectively do not exist.
- **Hall of Fame trophy case.** Decorative, and "most seasons played" is not an achievement.
- **Player-by-week heatmap.** Unreadable past roughly 15 weeks, and the per-row sparkline
  communicates the same thing better.
- **Blended offense-plus-defense rating.** Breaks the cross-page consistency that motivated
  choosing the 0-100 score as the merit unit.

## Success criteria

- A leader can open the page and, without sorting or filtering, name who is improving, who
  is declining, who is unreliable, and who is absent.
- A player can open their own drill-down and leave with a specific, quantified thing to fix
  (a matchup bucket where they underperform the clan, a near-miss rate, or missed attacks).
- Every number on the page is either the site's existing 0-100 score, a direct aggregate of
  it, or an explicitly-labelled second axis. No new competing merit currency is introduced.
- No claim is rendered that the underlying n cannot support.

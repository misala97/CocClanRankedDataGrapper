# CWL Page Redesign — Design Spec

**Date:** 2026-07-20
**Route:** `features/cwl/routes.py` → `cwl_page()` → `templates/cwl/cwl.html`
**Type:** Single-page redesign. Second half of the two-page war cycle: it
**inherits the War Detail unit (M1–M6)** defined in
`2026-07-19-clan-war-redesign-design.md` and embeds it once per CWL round.
The theme ("Night Ops Scope", DESIGN.md) is locked; this page **extends** it,
does not reopen it. CWL's mode identity hue is **CWL Violet** (as War used War
Amber).

This is a **structure contract**: modules, information, per-state ordering,
behavior, data mapping, responsive arrangement, and component *function* —
never their *look*. Palette, type, spacing, component styling, the signature
moment, and motion are `impeccable`'s to decide (see §11).

---

## 1. Why

`/cwl` renders one CWL season — a **group of 8 clans** fighting **7 daily
rounds**, promoting/relegating by a group score. Today it is a single long
scroll of four collapsible bands (Standings → Rosters → League Performance →
Rounds), where **Rounds is the pre-redesign war layout replicated seven
times** — seven stacked round-cards, each with the old two-column
clan-panel header, a **"Compare & Predict" modal**, win-probability, verdict,
attack-log and positional-roster blocks. Plus four overlays: TH Matchup Rates,
Player Matchup History, Compare & Predict, and a CWL Season Overview modal.

Four structural problems, decided fresh from the route's data (§2), not the
old template:

1. **The daily rounds are the old war page, seven times over.** The war
   redesign already solved single-war reading (state-aware M1–M6, no overlay).
   CWL still ships the superseded layout ×7, including the exact "Compare &
   Predict" modal the war redesign retired. The rounds must become the new War
   Detail unit — but seven **full** M1–M6 units cannot stack on one scroll.
2. **The season stake is buried.** CWL's defining question — *are we
   promoting, safe, or relegating, and who's in our way* — is the Standings
   band, currently one collapsible among four with equal weight to a data
   dump. It should anchor the page.
3. **Primary analysis hidden in overlays.** Per-round "Compare & Predict" and
   the season "Overview" are the PRODUCT.md "data dump you dread opening,"
   doubly unusable on a phone. The war redesign's ruling applies: primary
   analysis is inline, never an overlay.
4. **The 7-round at-a-glance scan is worth keeping.** The current stacked
   round-cards, whatever their faults, let you see all seven days' matchups
   and results at once. A pure day-switcher would lose that. The redesign must
   preserve the whole-season glance *and* provide deep single-day drill-in.

---

## 2. The data (design material)

Every module maps to variables `cwl_page()` already passes. Listed so the
design is grounded in real data, not the old template's sections.

| Variable | Shape | Feeds |
|---|---|---|
| `season`, `seasons` | selected + all CWL seasons | Header season selector, meta |
| `our_tag`, `our_clan` | our clan tag + `CWLClan` | throughout (whose perspective) |
| `standings` (sorted) | per clan: `name, badge_url, tag, wars, wins, losses, draws, stars, destruction, attacks, attacks_possible, score, live_winning, rounds[]` | **Standings** |
| `standings[].rounds[]` | per round: `round, opp_name, opp_badge, our_stars, opp_stars, our_pct, opp_pct, state, result, atk_done, atk_total` | Standings 7-round strip |
| `sorted_rounds` | `[(round_number, detail)]`; each `detail` = full `_build_war_detail` output (mirrors clan-war logic) | **Round Rail + War Detail unit** |
| `current_enemy_tag`, `tomorrow_enemy_tag` | today's / next opponent | Round Rail default day, Rosters |
| `clan_rosters` | per clan: `members` (current-pos sorted), `avg_th/avg_league/avg_lr/avg_unranked/count`, `top15_*`, `active_members{}`, `active_avg_th/league/count/unranked`, `war_round_count`, `first/last_rounds` | **Rosters** |
| `clan_war_info` | per clan: `cwl_league, location, wars_won, war_frequency, win_streak` | Rosters profile |
| `current_day_attacks` | per clan: `{done, total}` | Rosters live progress, Round Rail |
| `fought_clans` | opp tag → `{round, result, state}` | Rosters ("we beat them D3") |
| `our_player_perf` | per **our** player, whole season: `name, th, map_pos, wars, attacks_used, missed, stars, avg_stars, avg_dest, three_star_rate, avg_score`, star buckets, full defense split, `avg_atk_th, avg_def_th`, `daily_details[]` (per round) | **Performance** (our roster) |
| `all_player_perf` | per player, **all 8 clans**: `name, clan_name, is_our_clan, th, wars, attacks_used, missed, three_stars, avg_stars, avg_dest, three_star_rate` | Performance (group benchmark) |
| `season_overview_our`, `season_overview_all` | aggregate: `attacks_done/possible`, star buckets, `avg_stars, three_star_rate, avg_th_diff, avg_def_stars, avg_def_th_diff, missed, flawless` | Performance (season summary; the retired Overview modal) |
| `cwl_matchup_rates`, `cwl_matchup_counts`, `cwl_total_atk_count` | global TH-matchup star distributions | War unit M2/M5 odds + **TH Matchup Rates** lookup |
| `player_all_time_perf` | per player, per TH-matchup counts, all seasons | War unit M5 deep table + **Player Rates** lookup |
| `cwl_player_attack_rate`, `cwl_global_attack_rate_our/enemy` | attack-usage (miss) rates | War unit M2 win engine |
| `now`, `league_rank` | UTC now, ranking fn | countdowns, league sort |

**Interactive engine already shared:** `static/js/war_shared.js` backs *both*
`/war` and `/cwl` today (`calcWinProb`, `buildWinCalcHTML`,
`buildAttackLogHTML`, `openMatchupRatesModal`, `registerWarCard`, `initRoster`,
verdict/log toggles). The redesign preserves these functions; only their host
markup changes. CWL math flavor (one attack/war, `get_cwl_verdict`,
`compute_cwl_win_status` → `safe_win`/`cant_win`/`contested`) is already
computed server-side in `_build_war_detail`.

---

## 3. Page anatomy (modules)

One vertical column (chosen arrangement: standings-led vertical deck with a
lazy war unit). Five modules plus the shared page header and two header-level
reference lookups. Order is fixed top-to-bottom (§4); the War Detail unit's
*internal* order is state-driven by the war spec.

### Page header (shared `_page_header`)
Reuse the existing slot API — no page-local header markup.
- `page_header_title`: "CWL" (one accent segment allowed; no emoji).
- `page_primary_control`: the **season selector** (`seasons`) — "which season
  am I looking at."
- `page_header_meta`: figures — season month/label, `season.league_name`, our
  standing (`#rank / group_size`), our record (`W–L–D`). Idle/empty → plain
  `page_header_desc`.
- `page_controls` (secondary): the two **reference lookups** (see below).
- `page_header_right`: unused.

### Reference lookups (header controls, on-demand — kept as lookups)
Two **global / all-season** reference tools, deliberately distinct from any
single round's own inline matchup analysis. They stay header-triggered
(memory: reference tools stay in the header), redesigned:
- **TH Matchup Rates** — global star-distribution per TH matchup
  (`cwl_matchup_rates`/`counts`/`cwl_total_atk_count`). Reuses the existing
  shared `_matchup_rates_modal.html` + `openMatchupRatesModal`.
- **Player Rates** — per-player attack history per TH matchup, all seasons
  (`player_all_time_perf`). Reuses `_player_matchup_modal.html`.
- These are supplementary reference (a glossary), not primary analysis, so an
  on-demand surface is legitimate here. Whether each renders as a modal, a
  native Popover, or a drawer is `impeccable`'s call (§11) — but it must **not**
  become the heavy multi-section overlay the war redesign rejected.

### S1 · Standings *(the hub — always first)*
The season stake, up front. All 8 clans ranked by `score` (= stars + 10/win +
10 live-lead bonus — **correct as-is, do not re-flag**; display only). Each
clan states: rank, badge, name, score, total stars, `W–L–D`, attacks
used/possible, and a **7-round result strip** — one cell per round showing
that clan's per-day result (win/loss/draw/live/prep) from `standings[].rounds`.
- **Our clan is emphasized** (its own row treatment).
- **Promotion / relegation zones** are marked by rank. Convention reused from
  `cwl_stats`: top 2 = promotion, bottom 2 = relegation (see §10 for the
  per-league-tier accuracy note).
- **Live round**: the in-progress day's cell reads live; `live_winning` marks
  who currently leads.
- A clan row **expands** to its seven rounds in detail (opponent, score,
  result per day).
- **Cross-link:** selecting **our** round cell jumps the Round Rail to that day
  and loads its War Detail unit (§6) — the "nesting."

### S2 · Round Rail *(whole-season glance + day switcher)*
The single component that satisfies both the kept at-a-glance scan and the
drill-in. A rail of **7 day-tiles** (our clan's schedule, from `sorted_rounds`
+ `current_/tomorrow_enemy_tag`). Each tile: Day N, opponent (badge + name),
state (Prep / Live / Ended), result or live star score (`our★–opp★`), attack
progress (`done/team_size`), and the win-status flag where it exists
(`safe_win`/`cant_win`/`contested`). The selected tile is marked.
- **Default selection:** the live round; else the most-recent ended; else the
  next preparation day.
- Selecting a tile loads S3 in place (§6). No seven-unit stack ever exists.

### S3 · War Detail unit *(inherited M1–M6 — loads for the selected day)*
The War Detail unit from the clan-war spec, rendered for the selected round's
`detail` dict, with CWL math. **Reads exactly as `/war`** — same modules, same
per-state ordering, same no-overlay rule, same responsive form. Summarized (the
clan-war spec §3–§6 is authoritative):
- **M1 Scoreboard** — our clan ↔ opponent, size, state verdict chip; prep
  countdown to `start_time`, live score + countdown to `end_time`, ended final
  result. (CWLWar carries `start_time`/`end_time`; no prep-start field needed —
  prep counts down to `start_time`.)
- **M1-sticky** — live-desktop-only situation strip (as war spec).
- **M2 Win Projection** — inline win engine (`calcWinProb` + CWL miss-rate
  inputs). CWL is **one attack per war**; projection models the single
  remaining slot per player.
- **M3 Roster Ledger** (default) + **Map view** (toggle) — one row per our
  player: their attack target (off-mirror flagged), result, verdict, and their
  own base defense. Prep = scouting read (positions/TH/league, rushed/troll
  flags). Editors get inline flag toggles via the **CWL** endpoints
  (`/cwl/api/war/<id>/castle-empty`, `/cwl/api/member/<id>/is-rushed`,
  `/is-troll`).
- **M4 Verdict Table** — our roster ranked by `get_cwl_verdict` score; expands
  to per-attack quality. Only for `inWar`/`warEnded`.
- **M5 Matchup Analysis** — inline (replaces the retired per-round "Compare &
  Predict" modal): side-by-side clan profiles, TH + league distributions and
  edges, matchup odds from `cwl_matchup_rates`, and the Favored/Even/Underdog
  rationale. Densest reference (full TH matrix; per-player history from
  `player_all_time_perf`) behind in-place expanders, never an overlay.
- **M6 Attack Log** — chronological, collapsed; needs `duration` (§10).

**Single source of truth (architectural mandate):** extract the War Detail
unit's markup + CSS from `clanwar.html` into a **shared partial** (e.g.
`templates/war/_war_detail_unit.html` + shared styles) that **both** `/war` and
`/cwl` include, parameterized by the `detail` dict and a math-flavor flag
(war = 2 attacks; cwl = 1). Do **not** fork a second copy — a fork guarantees
the two drift and breaks "reads exactly as `/war`." This refactor touches the
committed `clanwar.html`; it is in scope as a genuine cross-page structural need
(Non-Negotiable 3), not a theme reopening.

### S4 · Rosters *(per-clan scouting)*
Scouting for all 8 clans, from `clan_rosters` + `clan_war_info` +
`current_day_attacks` + `fought_clans`. A **clan selector** (our clan default;
today's opponent one tap away) shows the selected clan's:
- profile line — `cwl_league`, `location`, `wars_won`, `war_frequency`,
  `win_streak`, and our head-to-head this season (`fought_clans`: "beat them
  D3 / lost D5 / meet D6");
- roster strength — day-1 `avg_th`/`avg_league`/`count`/unranked **vs** the
  **active-15** they actually field (`active_avg_th`/`active_league`/
  `active_count`) — the scouting read is "who they *field*," not the paper
  roster;
- today's attack progress (`current_day_attacks`);
- member list — one row per member (current map-position order): position, TH,
  ranked league, wars selected / attacks done (from `active_members`), and
  editor rushed/troll flags (CWL clan-member endpoints
  `/cwl/api/clan-member/<id>/is-rushed`, `/is-troll`).

### S5 · Performance *(season judgment — who carried)*
The whole-season judgment layer; also absorbs the **retired Season Overview
modal** as an inline band. Three parts:
- **Season summary** — `season_overview_our` vs `season_overview_all` as a
  compact figure set: attacks done/possible, avg stars, 3★ rate, avg TH diff,
  avg defense stars, missed, and **flawless** count. Our clan read against the
  whole group.
- **Our roster** — per-player season table from `our_player_perf`: wars,
  attacks used/missed, avg stars, avg verdict score, 3★ rate, offense **and**
  defense split (`def_*`), avg attacked-TH / avg-defended-TH. Sortable; a row
  **expands** to `daily_details` (per-round score/badge/result chips — the
  member's whole CWL at a glance). "Who's carrying us."
- **Group benchmark** — per-player table across all 8 clans from
  `all_player_perf`: clan, TH, wars, attacks, avg stars, 3★ rate; our players
  highlighted (`is_our_clan`). Sortable. "How we rank against everyone."

---

## 4. Ordering & states

Top-to-bottom module order is fixed: **Header → S1 Standings → S2 Round Rail →
S3 War Detail (selected day) → S4 Rosters → S5 Performance.** State drives what
*within* the modules renders, not their order.

- **Season-level state** is a mix — some rounds ended, one may be live, later
  ones in prep. S1 and S2 always show all seven days at whatever state each is.
- **S3** obeys the war spec's per-state ordering (§4 there) for the *selected*
  day: prep → M1/M5/M2/M3; inWar → M1/M2/M3/M4/M5/M6; warEnded →
  M1/M4/M3/M2/M5/M6.
- **Empty / idle:**
  - No seasons at all → the existing "No CWL data yet" empty state, nothing
    else.
  - A season with clans but no wars started → S1 Standings (0–0 rows) + S2 rail
    (all Prep); S3 shows the prep unit for Day 1; S4 rosters render; S5 shows
    "no attacks yet," not empty tables.
  - Never a dead placeholder — show last real data (last season resolves from
    the selector; a finished season shows final standings + full rounds).

---

## 5. Behavior

- **Lazy war unit.** S3 renders the **selected** day only; switching a Round
  Rail tile (or an S1 our-round cell) swaps the unit in place. The 7-unit stack
  never exists.
- **Default day** = live → most-recent-ended → next-prep (§3, S2).
- **Cross-highlight / cross-link.** S1 our-round cell → S2 selection + S3 load.
  Within S3, the war spec's player cross-highlight (ledger ↔ map ↔ verdicts)
  is inherited unchanged.
- **Countdowns** tick client-side from `now` + the selected war's
  `start_time`/`end_time`; information, so they keep updating under reduced
  motion (only pulse/transform effects suppress).
- **Preserve the shared engine.** All `war_shared.js` functions keep their
  behavior; only host containers move.
- **Editor flag toggles** hit the CWL endpoints (war-level + member + clan-
  member); optimistic UI as today.
- **Disclosures** (S1 clan expand, S5 row expand, S3's inherited expanders,
  the reference lookups) follow the established a11y pattern: real `<button>`s,
  synced `aria-expanded`, keyboard-reachable, native Popover where a disclosure
  must escape a clipping container. No hover-only reveals.
- **Two sticky elements on a live day** (header controls bar + S3's M1-sticky)
  must not stack into a tall pinned block — same coordination the war spec
  flags (§11).

---

## 6. Responsive / mobile pass (real, not reflow)

Validated at **390×844**, **768×1024**, **1200×800**.

- **Single column throughout** (the deck is already single-column).
- **S1 Standings** — dense (8 clans × score/stars/W-L-D/attacks/7 cells) →
  the standing **divided roster-row** pattern (`.mr`): one clan per row (rank +
  badge + name + score + a compact 7-result strip), tap-to-expand for the full
  breakdown. **Never** per-clan cards.
- **S2 Round Rail** → **horizontal scrollable day-chip rail** (chosen); the
  selected day's unit below. No wrap to a grid.
- **S3 War Detail** → inherits the war unit's mobile form exactly (single
  column; M3/M4 as `.mr` rows tap-to-expand; map view is the desktop-oriented
  secondary; M5 distributions as compact bars, matrices behind expanders). No
  horizontal overflow at 390px.
- **S4 Rosters** → clan selector (scrollable chips or select) + the selected
  clan's members as `.mr` rows.
- **S5 Performance** → both tables as `.mr` divided rows, tap-to-expand
  (`daily_details` behind the expand); season-summary figures as a compact
  grid.
- No module introduces horizontal overflow at 390px; no truncated labels/
  legends.

---

## 7. Component reuse (existing shared vocabulary)

Reuse, don't reinvent: the whole **War Detail unit** (shared partial, §3 S3);
the DESIGN.md verdict/judgment badge vocabulary
(godlike/dominant/wow/good/warning/suck) for S1/S5/M4; the ticket /
featured-tile / compact-row / stat-cell tiers; the mobile `.mr` roster-row
pattern for every dense table (S1, S4, S5); the shared `_matchup_rates_modal`
/ `_player_matchup_modal` partials + `war_shared.js` for the reference lookups;
**CWL Violet** as this page's mode identity (already in the theme, distinct
from Threat Magenta "interactive"). Shared-shell edits (`_head`, `_nav`,
`_page_header`, footer) are in scope only for genuine cross-page structural
needs — the `_war_detail_unit` extraction is one; reopening the theme is not.

---

## 8. Out of scope

- `/cwl/stats` (`cwl_stats.html`) — the all-time cross-season aggregate page
  (Hall of Fame, MVPs, league progression); a later cycle.
- The scoring rules themselves — CWL group score (stars + 10/win + live bonus),
  `get_cwl_verdict`, `compute_cwl_win_status`, activity-score asymmetry — all
  correct and settled; display only, do not re-flag.
- The theme — locked; extended, not reopened.

---

## 9. Component function ≠ look

This spec names component **function** only (e.g. "7-round result strip,"
"compact per-player season row with expand"). Radii, colors, spacing values,
the signature moment, motion, and the modal-vs-popover-vs-drawer choice for the
reference lookups are all `impeccable`'s — see §11.

---

## 10. Backend / route changes

1. **Approved, minimal:** add `duration` to each dict in `_build_war_detail`'s
   `all_attacks_json` (from `CWLAttack.duration`, already on the model —
   verified). ~1 line; unlocks M6's attack-time column so the CWL log reads
   exactly like `/war`'s.

Nothing else is required — all matchup rates, per-player history, attack-usage
rates, and both clans' war time fields (`CWLWar.start_time`/`end_time`) are
already passed.

**Resolved at sign-off:**
- **Promotion/relegation zones** → ship the **top-2 / bottom-2** convention
  (reused from `cwl_stats`; zero backend cost, consistent across the two CWL
  pages). Per-league-tier exactness is explicitly *not* pursued this cycle.
- **War Detail unit reuse** → **shared-partial extraction approved** (§3 S3):
  M1–M6 comes out of the committed `clanwar.html` into one include both `/war`
  and `/cwl` render. Replication was rejected to prevent drift.

---

## 11. Open questions for `impeccable`

Look decisions, deliberately unresolved here:

1. **S1 Standings** visual form — the ranked list treatment, how our clan is
   emphasized vs the other seven, how promo/releg zones read without a >1px
   side-stripe (DESIGN.md ban), and how the 7-round result strip encodes
   win/loss/draw/live/prep at a glance.
2. **S2 Round Rail** — the day-tile treatment (opponent, state, score,
   win-status), the selected-tile mark, and the desktop rail vs mobile
   scroll-chip form.
3. **How S1 and S2 relate visually** — two adjacent "all-seven-days" reads
   (group-wide dots vs our-schedule tiles) must feel complementary, not
   redundant.
4. **S3** — inherits the war unit; the only new look question is how the unit
   sits inside the CWL page (its boundary, the day-context it carries) and how
   CWL Violet colors it vs War Amber on `/war`.
5. **S4 Rosters** — the day-1-vs-active-15 comparison form, and the clan
   selector treatment.
6. **S5 Performance** — season-summary figure form; whether the our-roster
   table uses a featured top-carriers tier + quiet rows (two-tier pattern) or a
   flat sortable table; how `daily_details` render on expand; how our players
   are highlighted in the group benchmark.
7. **Reference lookups** — modal vs native Popover vs drawer for TH Matchup
   Rates and Player Rates, and their redesigned contents (inherits war page's
   treatment of the shared render output where possible).
8. **Motion** — countdowns, live pulse, day-swap transition, expand/collapse,
   cross-link scroll — where restraint serves and where one signature moment
   earns its place.

---

## 12. Validation (before sign-off)

Playwright screenshots at **390×844**, **768×1024**, **1200×800**. Because a
live season spans states, capture: the season hub (S1+S2) at all three
viewports; the War Detail unit for **each** war state (prep / inWar /
warEnded) via day selection; S4 Rosters; S5 Performance. Check:
- module order matches §4; the war unit's internal order matches the war spec
  per state;
- only **one** War Detail unit is ever in the DOM/visible (lazy load works);
- S1/S4/S5 dense tables are `.mr` divided rows on mobile, not cards; no
  horizontal overflow at 390px; no truncated labels;
- S2 is a scrollable chip rail on mobile; nothing else pins on mobile;
- **no overlay anywhere except** the two intentional header reference lookups —
  no per-round "Compare & Predict," no "Season Overview" modal;
- prep day hides M4/M6 rather than showing empty tables; S5 shows "no attacks
  yet" for an unstarted season, not empty tables;
- empty (no seasons) shows the "No CWL data yet" fallback.

Run `/impeccable critique` on the built page. Show all screenshots + a critique
summary at the final gate.

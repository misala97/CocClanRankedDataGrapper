# Clan War Page Redesign — Design Spec

**Date:** 2026-07-19
**Route:** `features/war/routes.py` → `clan_war_page()` → `templates/war/clanwar.html`
**Type:** Single-page redesign, first of a two-page cycle. The reusable
"War Detail" unit defined here is the foundation the CWL page (`/cwl`,
a later cycle) will inherit — CWL embeds this same unit seven times, once
per round, with different math. That inheritance is a design *intent*, not
in scope to build now.

This is a **structure contract**. It defines the page's modules, their
information, per-state ordering, behavior, data mapping, and responsive
arrangement — never their look. Palette, type, spacing, component styling,
the signature moment, and motion are `impeccable`'s to decide (see §10,
Open questions).

---

## 1. Why

`/war` shows one clan war (a picker switches between them). Today it is a
fixed vertical stack of collapsible cards — win calculator, verdict table,
attack log, roster grid — plus a **"Compare & Predict" button that opens a
seven-section modal overlay** carrying the deep matchup analysis.

Three structural problems, decided fresh from the route's data rather than
the current template:

1. **The page ignores war state.** A war is in one of three states —
   `preparation`, `inWar`, `warEnded` — and each state makes a *different*
   question primary: prep asks "are we favored?", live asks "are we winning
   right now, and who still has attacks?", ended asks "what happened and who
   carried?". The current single layout serves all three the same way.
2. **Primary analysis is hidden in a modal.** The matchup breakdown is the
   single most useful view during preparation, yet it requires opening an
   overlay — the "data dump you dread opening" PRODUCT.md rejects, and a
   seven-section overlay is unusable on a phone.
3. **The roster grid conflates two jobs.** The positional two-column grid
   with drawn attack lines answers both "who hit whom for how many stars"
   and "the spatial picture" at once; arrow-tracing is the least legible way
   to answer the first.

The redesign fixes all three at the structural layer so `impeccable`
inherits clean bones.

---

## 2. The data (design material)

Every module below maps to variables the route already passes. Listed so the
design is grounded in real data, not the old template's sections.

| Variable | Shape | Feeds |
|---|---|---|
| `war` (`ClanWar`) | state, `team_size`, `start_time`/`end_time`/`preparation_start_time`, `clan_stars`/`opponent_stars`, `clan_attacks`/`opponent_attacks`, `clan_destruction_pct`/`opponent_destruction_pct`, both clans' `cwl_league`/`location`/`wars_won`/`war_frequency`/`win_streak`/`war_log_public`, `castle_empty` | M1, M2, M5, countdowns |
| `war_options`, `selected_id` | picker labels per war | Page header primary control |
| `members_our`, `members_opp` | sorted by `map_position`; `th`, `pos`, `name`, `ranked_league`, `is_rushed`, `is_troll`, `opponent_attacks` | M3, M5 |
| `avg_th_our/opp`, `avg_league_our/opp` | side averages | M1 chip, M5 edge |
| `members_our_json`, `members_opp_json` | `{tag, th, name, pos, league, lr}` | client render (M3, map, engine) |
| `all_attacks_json` | per attack: `order, attacker_name/pos/th/side, defender_name/pos/th, stars, pct, label` — **+ `duration` (added, §9)** | M3, M6, engine |
| `attacks_by_attacker`, `attacks_on_defender`, `member_by_tag` | server dicts | verdicts, log, open-base detection |
| `war_verdicts` | per our player: `name, tag, th, map_pos, league, attacks_used, score, badge, label, atk_labels`, `attack_details[{defender_name/th/pos, stars, pct, th_diff, pos_diff, label, stars_before, target_state}]` | M4, M3 row detail |
| `war_matchup_rates`, `war_matchup_counts`, `war_total_atk_count` | TH-matchup star distributions | M2, M5 odds |
| `war_player_history` | per-player per-matchup counts | M5 deep table, engine |
| `war_global_attack_rate_our` | `{used, possible}` | M2 miss-rate model |
| `now` | UTC now | countdown baseline |

**Interactive engine to preserve (function, not markup):** the win-probability
computation (`computeWarWinCalc`/`At`, `computeWarPrediction`,
`computeWarAttackHistory`, `computeWarAssignment`), verdict table build/sort/
expand, the roster/map render, and the three flag-toggle endpoints
(`/war/api/<id>/castle-empty`, `/war/api/member/<id>/is-rushed`,
`/war/api/member/<id>/is-troll`). These keep working; their DOM containers
move into the new modules.

---

## 3. Page anatomy (modules)

Six modules plus the shared page header. Every module's *presence and order*
is state-driven (§4); its *function* is fixed below.

### M1 · War Scoreboard  *(always first)*
The at-a-glance answer. Our clan ↔ opponent (badge, name), war size, and one
state verdict chip.
- **Prep:** countdown to battle day (`start_time − now`); verdict chip =
  Favored / Even / Underdog, derived from the matchup (avg TH edge, avg league
  edge, projected odds). Score is 0–0, not shown as a result.
- **Live:** live star score + destruction both sides; attacks used both sides
  (`X / team_size`); countdown to end (`end_time − now`); verdict chip =
  Winning / Losing / Tied from the *current* score (distinct from the M2
  projection — one is now, the other is forecast).
- **Ended:** final result (Win / Loss / Draw), final stars + destruction, star
  differential. No countdown.
- Result rule: more stars wins; equal stars broken by destruction %.

### M1-sticky · Situation strip  *(live only, desktop only)*
Arrangement **B**. On `inWar`, once M1 scrolls out of view on desktop, a
strip detaches and pins under the nav: reduced score + countdown + Winning/
Losing chip + one-line projection. Not rendered in prep or ended; not on
mobile. Must coexist with the header's own sticky controls bar without the two
stacking into a tall pinned block (§5).

### M2 · Win Projection
The win-probability engine, surfaced inline (never a card the user must hunt
for). Projected final stars our vs opp, likely outcome + confidence, and the
remaining-attack scenarios, computed from matchup rates and the attack-usage
(miss) rate.
- **Prep:** pre-war projection from rosters alone (no attacks yet).
- **Live:** projection from current score + modeled remaining attacks.
- **Ended:** retired by default. Whether a small "projected X, finished Y"
  retrospective appears is an open question for `impeccable` (§10).

### M3 · Roster Ledger  *(the redesigned grid)*
Replaces the positional-grid-as-default. Two coordinated views:

**Ledger (default).** One row per *our* player, ordered by map position. Each
row states:
- the player (name, TH, map position),
- their **actual** attack target(s) — including off-mirror — with the target's
  position and TH and an off-mirror direction flag (up / down N positions),
  the result (stars, destruction), and the matchup/verdict label,
- the player's own base defense: who attacked it, for how many stars, and base
  state (held / open / fresh).
- Row expands to full per-attack detail (war allows two attacks) from
  `war_verdicts.attack_details` + `target_state`, plus defense detail.
- Selecting a player cross-highlights the enemy base(s) they attacked, and
  vice-versa (shared with the Map view).
- Editors get inline flag toggles: opponent member `is_rushed`/`is_troll`,
  war-level `castle_empty`.

**Map view (optional toggle).** The positional two-column layout (our vs
opponent by map position) with attack connectors drawn attacker → defender,
off-mirror connections included, nodes selectable. Same underlying data as the
ledger (`all_attacks_json` + members). It is a secondary view, not the default,
because arrow-tracing is the least legible way to read attack outcomes.

Open enemy bases (fresh / partially-hit targets) are surfaced for the live
"who should I attack" need, derived from `attacks_on_defender` against
`members_opp`.

In **prep** there are no attacks: rows show positions, TH, league, mirror
pairing, and opponent rushed/troll flags — the scouting read; the map view
shows positions only.

### M4 · Verdict Table  *(our roster)*
Our players ranked by verdict score, with badge + label and attacks used;
rows expand to per-attack quality (defender, TH/position differential, stars,
target state). Sortable. From `war_verdicts`. Only meaningful once attacks
exist (`inWar` / `warEnded`); absent in prep.

**M3 vs M4 is a deliberate two-lens split, not redundancy** (decided with the
user): M3 is the *battlefield* — positional, both sides, defenses included;
M4 is the *judgment* — our roster only, ranked by score. Different questions,
cross-linked by player.

### M5 · Matchup Analysis  *(replaces the modal — no overlay anywhere)*
The retired modal's content, as real in-page sections:
- side-by-side clan profiles (name, `cwl_league`, `location`, `wars_won`,
  `war_frequency`, `win_streak`, `war_log_public`),
- TH distribution of both rosters + average TH edge,
- league distribution of both rosters + average league edge,
- matchup odds — expected stars per attack from `war_matchup_rates` /
  `war_matchup_counts`,
- the Favored / Even / Underdog rationale that backs M1's chip.
- The densest reference material (full TH star-distribution matrix with sample
  counts; per-player historical odds from `war_player_history`) lives behind
  **in-place expanders**, never an overlay.

### M6 · Attack Log  *(secondary, collapsed, always)*
Chronological attacks: order, attacker (name/position/side), defender
(name/position), stars, destruction, label, and **duration** (the new field).
From `all_attacks_json`.

### Page header (shared `_page_header`)
Reuses the existing slot API — no page-local header markup.
- `page_header_title`: "CLAN WAR" (one accent segment allowed; no emoji).
- `page_primary_control`: the **war picker** (`war_options`) — the page's
  "what am I looking at" selector.
- `page_header_meta`: figures — size (`{team_size}v{team_size}`), state, start
  date. Idle/empty state falls back to a plain `page_header_desc`.
- `page_header_right`: unused (a war is not a single-subject identity page).

---

## 4. Per-state ordering

State comes from `war.state`. Modules absent in a state do not render (no dead
placeholders).

| State | Module order |
|---|---|
| **preparation** | M1 (Favored + countdown) → **M5 Matchup Analysis (expanded)** → M2 Win Projection (pre-war) → M3 Roster Ledger (positions, scouting flags). M4 and M6 absent (no attacks). |
| **inWar** | M1 (live score + countdown + Winning/Losing) → M1-sticky on scroll → **M2 Win Projection** → **M3 Roster Ledger** (live, open bases) → M4 Verdict Table (in-progress) → M5 Matchup (collapsed) → M6 Attack Log. |
| **warEnded** | M1 (final result) → **M4 Verdict Table** (who carried) → **M3 Roster Ledger** (full map) → M2 (retired or retrospective) → M5 Matchup (collapsed) → M6 Attack Log. |

**Empty / idle states:**
- No wars at all → keep the existing "No war data yet" empty state.
- A war always resolves to the most recent one otherwise — show last real war,
  never a placeholder.
- Prep (no attacks) → M4 and M6 do not render as empty tables; if a slot would
  be empty, show a short "no attacks yet" line, not a dead grid.

---

## 5. Behavior

- **State detection** drives module presence and order (§4) and which M1
  variant renders.
- **Countdowns** tick client-side from `now` + `war.start_time` / `end_time`.
  Countdown is information and keeps updating under reduced motion; only the
  live-dot pulse and hover/press transforms are suppressed there.
- **Preserve the engine.** All existing interactive functions (§2) keep their
  behavior; only their host containers move into M1–M6.
- **Cross-highlight** links M3 (ledger + map) and M4 by player: selecting a
  player in one highlights the corresponding base/row in the others.
- **Two sticky elements on live desktop** — the header controls bar (from the
  page-header spec) and M1-sticky. They must not stack into a tall pinned
  block; how they coordinate (which pins, or whether M1-sticky replaces the
  controls bar while a war is live) is a behavior detail to resolve in build,
  flagged in §10.
- **Disclosures** (row expanders, M5 in-place expanders, the Map toggle) follow
  the established accessibility pattern: real `<button>`s, synced
  `aria-expanded`, keyboard-reachable, and native Popover where a disclosure
  must escape a clipping container. No hover-only reveals.

---

## 6. Responsive / mobile pass (real, not reflow)

Validated at 390×844 (iPhone 16e), 768×1024, 1200×800.

- **Single column** throughout (arrangement B is already single-column;
  M1-sticky is the only desktop-added element).
- **M1-sticky** is desktop-only; nothing pins on mobile.
- **M3 Roster Ledger and M4 Verdict Table** become the standing divided
  roster-row pattern (`.mr` rows), tap-to-expand — never per-player cards.
- **M3 Map view** — the ledger *is* the mobile form; the positional map is
  desktop-oriented (omitted or simplified on mobile is an open question, §10).
- **M5 distributions** render as compact bars; the full matrices stay behind
  expanders. No wide table forces horizontal scroll.
- No module introduces horizontal overflow at 390px.

---

## 7. Component reuse (existing shared vocabulary)

Reuse, don't reinvent: the DESIGN.md verdict/judgment badge vocabulary
(godlike/dominant/wow/good/warning/suck) for M1's chip and M4's badges; the
ticket / compact-row / stat-cell tiers; the mobile roster-row pattern; War
Amber as this page's mode identity (already fixed in the theme). Shared-shell
edits are in scope only for genuine cross-page structural needs (e.g. a
page-header slot gap) — not to reopen the theme.

---

## 8. Out of scope

- `/war/stats` (`war_stats.html`) — the all-time aggregate page; a later cycle.
- `/cwl` and `/cwl/stats` — the next cycle. This spec's War Detail unit
  (M1–M6 + engine) is written to be reused there, but building CWL is not part
  of this cycle.
- The theme itself — locked; not reopened here.

---

## 9. Backend / route changes

**One, approved:** add `duration` to each dict in `all_attacks_json` (from
`ClanWarAttack.duration`, already on the model). Roughly one line in
`clan_war_page()`. Enables attack time in M6.

Nothing else is needed. `war.end_time` and `war.preparation_start_time` are
already on the `war` object the template receives, so countdowns need no route
change. All matchup rates, player history, and attack-usage rates are already
passed.

---

## 10. Open questions for `impeccable`

Look decisions, deliberately unresolved here:

1. M1 Scoreboard's visual treatment across the three states — how the live
   score, countdown, and verdict chip read, and how War Amber mode identity is
   applied (bound by DESIGN.md's ban on >1px accent stripes).
2. M2 Win Projection's visual form — bar, gauge, plain figures, scenario list.
3. M3 ledger row density and the off-mirror direction glyphs; how row-expand
   and cross-highlight look; and how the optional Map view renders nodes and
   connectors (and whether connector color encodes stars).
4. M3 Map view on mobile — omitted vs simplified.
5. M5's distribution form (bars / histogram) and the profile-card treatment.
6. M1-sticky's exact appearance and its coordination with the header controls
   bar (DESIGN.md sanctions blur only for the nav, so likely a solid ground).
7. Whether the ended state shows a Win Projection retrospective at all.
8. Motion: countdown, live pulse, cross-highlight, expand/collapse transitions
   — where restraint serves the page and where a signature moment earns its
   place.

---

## 11. Validation (before sign-off)

Playwright screenshots at **390×844**, **768×1024**, **1200×800**, for **all
three states** (preparation, inWar, warEnded — requires test data or fixtures
for each). Check:
- module order matches §4 per state;
- mobile M3/M4 are divided roster rows, not cards; no horizontal overflow at
  390px; no truncated labels;
- M1-sticky pins on live desktop only, nothing sticky on mobile;
- no modal/overlay anywhere on the page;
- prep hides M4/M6 rather than showing empty tables;
- empty-war state shows the "No war data yet" fallback.

Run `/impeccable critique` on the built page. Show all screenshots + a critique
summary at the final gate.

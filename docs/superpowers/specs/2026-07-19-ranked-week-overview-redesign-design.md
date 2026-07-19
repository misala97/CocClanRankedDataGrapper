# Ranked Week Overview Redesign — Design Spec (Structure Contract)

**Date:** 2026-07-19
**Route:** `ranked_bp.ranked_weeks_page` → `GET /ranked` (`coc_stats/features/ranked/routes.py:27`)
**Template:** `coc_stats/templates/ranked/ranked_weeks.html`
**Status:** Structure locked, pending sign-off. Visual execution deferred to `impeccable` (see "Open questions for impeccable").

This spec fixes **structure, data mapping, behavior, and responsive arrangement only**. It does not decide palette, type, spacing, component styling, signature element, or motion — those are impeccable's, extending the established "Night Ops Scope" theme (`DESIGN.md` / `PRODUCT.md`). This is a *later* page in that system: the theme is extended, not re-opened.

---

## 1. Goal & audience

The clan's most-used page, two readers on it constantly:
- **Leader** scanning the whole roster: who's carrying, who's coasting, who's about to be relegated, who still owes attacks.
- **Member** checking their own standing and the sophisticated verdict on their week.

The page must do three jobs at once without any one drowning the others: **scan everyone at a glance**, **compare on the one cross-player-comparable number (the verdict/score)**, and **drill into one player's full receipts** (this week's attacks, the score math, and their multi-week history).

### What's wrong with the current page (the brief is the fix)
- **The verdict — the reason the page exists — is buried.** The comparable 0–100 score shows only as a small `· 87` tail on the verdict word, and its (genuinely sophisticated) TH-and-league-adjusted math sits **two nested disclosures deep** in the row detail.
- **The week summary is duplicated across two surfaces:** a persistent top "debrief band" *and* a separate Week Overview modal that auto-opens on finished weeks — both rendering the same aggregate (promotions/relegations, attacks used, verdict spread, top performers, missed attacks).
- **Week-over-week movement is invisible on the roster** — you see where a player sits now, but "climbing or sliding since last week" only exists deep inside the history drawer.
- **Mobile uses spacious per-player cards** — violates the site's standing divided-roster-row rule (re-introduced and removed more than once).
- **Live `DESIGN.md` violations** carried in the template (see §7).

Explicitly **not** wrong / **preserved by user instruction:** the table is dense on purpose. The user reads *every* column and wants all of them kept in the scannable view — this redesign does **not** thin the table or demote data to the drawer. It reorganizes and elevates; it does not remove.

---

## 2. Data source (route payload)

Everything rendered comes from the route. Current per-player entries in `week_data` (one per `Player.query.all()`, filtered client-side):

- **Identity:** `player_name`, `player_tag`, `player_th`, `in_clan`, `in_group_chat`.
- **League / standing:** `league_tier`, `league_icon`, `league_tier_prev` (for promote/relegate arrow), `league_rank`, `expected_league_rank`, `rank`, `rank_status` (`up`/`down`/`neutral`/`inactive`), `promo_spots`, `dem_spots`, `trophies`.
- **Attacks:** `att_count`, `att_max`, `att_0star…att_3star`, `att_avg`, `attack_details[]` (each: `opponent_name`, `opponent_th`, `stars`, `percentage`, `time`, `time_sort`).
- **Defenses:** `def_count`, `def_max`, `def_0star…def_3star`, `def_avg`, `defense_details[]` (same shape).
- **Verdict/score:** `score_100` (0–100, comparable), `th_adj_score`, `league_mult`, `badge_class`, `judge_label`, `is_active`.
- **League-group context:** `group_total_attacks`, `group_full_attackers` (of the 100-player group, how many used all attacks).
- `player_history` — per player, up to **52** weeks (`distinct_weeks[:52]`), each with full att/def stats, `score_100`, `badge_class`, league, `trophies`, `rank`, group attackers, `is_inactive`.
- Page-level: `distinct_weeks`, `selected_week_id`, `selected_week_info`, `current_week_id`.

The **week-level aggregate** (promotions/holdings/relegations, attacks used/max, clan avg attack/defense, verdict distribution, top performers, missed attacks) is derived client-side from `week_data` — no new backend needed for it.

### The verdict math (why it's the centerpiece — kept, made legible)
Per attack `adj = stars × th_mult(opp_th − player_th, player_th)` (rewards hitting up, discounts hitting down, scaled to own TH). `th_adj = Σ adj ÷ max_attacks` (missing attacks drag it, since divided by *max*). `× league_mult` (bonus for sitting in a higher league than the TH's expected league, penalty for lower). Normalized `→ score_100`. Verdict tiers: Godlike ≥87 · Dominant ≥80 · Very Good ≥65 · Good ≥58 · Bad ≥43 · Disaster ≥29 · Useless / No Attacks below. All inputs to explain this (`th_adj_score`, `league_mult`, `league_rank`, `expected_league_rank`, `player_th`, `attack_details`, `att_max`) are already in the payload.

---

## 3. Backend change (approved) — week-over-week movement

**New:** surface each player's previous-week rank and trophies on the roster row.

- The route already fetches `prev_ranked_week` and computes `rank_prev`; it currently only passes `league_tier_prev`.
- Add to each `week_data` entry: `rank_prev` and `trophies_prev` (from `prev_ranked_week`, else `None`).
- **Cost:** none of note — the previous week is already loaded in the same query (`season_filter` already includes `prev_week_id`). This is a two-field passthrough, no extra query.
- **Use (presentation):** the Zone cell shows rank movement (`▲Δ` / `▼Δ` / hold) and a trophy delta vs last week. Movement is most meaningful when the league is unchanged; when the player changed leagues the existing promote/relegate arrow already carries that, so the rank-delta is suppressed or de-emphasized on a league change (impeccable decides the exact treatment; the data distinction is: `league_tier_prev != league_tier` ⇒ league changed).

No other backend change. Scoring math, verdict tiers, and all existing fields are untouched — this redesign presents existing data, it does not re-tune it.

---

## 4. Page structure

Top to bottom: **Page header → Week-summary strip → Recent-attacks bar (collapsed) → Roster table.** Modals: the Week Overview modal is **removed** (folded into the strip); the Reminder modal is **kept** as-is.

### 4.1 Page header (reuse `_page_header.html` slots — no page-local header markup)
- `page_header_title` — the page title with one accent span (the Ranked mode identity word).
- `page_header_desc` — one orientation line.
- `page_primary_control` — the **week selector** (current week marked; finished weeks dated). One primary control.
- `page_controls` — the existing secondary cluster, preserved: search; the standing filter (all / promotion zone / holding / relegation zone / full attacks); "Show left"; "Reminder" (if permitted); "Week Analysis" (if the viewer has a linked player); "Show inactive".

The existing title/desc/primary-control/controls slots cover this page — no new slot required.

### 4.2 Week-summary strip (replaces BOTH the debrief band and the auto-opening modal)
Function: the single week-level overview, **one source of truth**, **state-aware** by week status.

- **Compact form** (default for the live/current week): standing counts (**N promoting · N holding · N relegated**), attacks logged / max + percent, clan average attack, who's leading (name + score), and **who still owes attacks** (count + names) — the live-week's most actionable line.
- **Expanded form** (auto-expanded when a **finished** week is opened; reachable on demand for the live week): adds the **verdict-spread** distribution, **top performers**, and the **missed-attacks** list.
- No modal, no auto-popup dialog. The expand control is keyboard- and touch-operable.
- Empty (no week data): the strip is omitted; the roster area shows the empty state (§6).

### 4.3 Recent-attacks bar
Function: "who's active now" — the 20 most recent ranked attacks across all players.
- A **collapsed** bar at the top by default; expands in place to a compact attack log (time · player · opponent + their TH/diff · stars · %).
- Kept at the top by explicit user instruction (this is how activity is checked mid-week). Collapsed so it never crowds the roster. Keyboard/touch operable.

### 4.4 Roster table — arrangement A ("Standing Ledger"), single dense aligned-column line per player
Standing-first spine, verdict promoted to a headline column, **all current columns preserved**. Column order, left→right:

1. **League** — icon + tier; promote/relegate arrow when `league_tier_prev` differs.
2. **Zone** — in-game `#rank` inside a promotion/relegation gauge instrument (the gauge marks where the player sits between the top `promo_spots` and bottom `dem_spots` of their 100-player group), **plus week-over-week movement** (rank Δ + trophy Δ vs last week, §3), plus the group-attendance caption (`group_full_attackers`/100) where present. This is the spine.
3. **Score · Verdict** — the 0–100 `score_100` as the loud, headline per-row number + the verdict badge. Promoted from today's right-side suffix to a headline column immediately after the standing.
4. **Player** — name (links to `/player/<tag>`), TH, trophies. "Left" tag when out of clan; self-highlight when it's the viewer's linked player.
5. **Attacks** — `att_avg` (Ø), `att_count`/`att_max` (with missing-count treatment), and the 0/1/2/3★ split.
6. **Avg Attack TH** — `att_avg_th` (computed client-side from `attack_details`) + its diff vs the player's TH.
7. **Defenses** — `def_avg` (Ø), `def_count`, and the 0/1/2/3★ split.
8. **Avg Def TH** — `def_avg_th` + diff.
9. **Expand affordance** — opens the drawer (whole row is also the click target, as today).

- **Ordering / sorting:** default keeps the standing-first read — league descending, then rank within league (unchanged). Every column stays sortable (a header sort by the Score·Verdict column gives the "who's best this week" ranking on demand). Column grouping between the standing block (League/Zone/Score), the player, the attack block, and the defense block is preserved as a structural separation (exact divider treatment is impeccable's).
- **Inactive players** (`is_active` false): shown as a demoted row carrying "Inactive this week," only when "Show inactive" is on.
- **Left-clan players:** shown only when "Show left" is on; carry a "Left" marker.

### 4.5 Detail drawer — tabbed
Opening a player row reveals a **tabbed** drawer (one panel at a time), matching the just-shipped player-profile idiom so the drawer stays short. Tabs, in order:

1. **Verdict** — makes the sophisticated score legible: the levers (player TH; the same-TH baseline average; the league multiplier with its bonus/penalty read; the final score + verdict). The **formula line** stating `score = Σ adj. stars ÷ max_attacks × league_mult`. Then, **one disclosure deep** (a single expand — not two nested levels), the **full per-attack breakdown table**: opponent, their TH + diff, the multiplier applied, stars, adjusted stars — including explicit "missing attack" rows up to `att_max`.
2. **Defenses** — the per-defense table (opponent, their TH, stars, %). Present only when defenses exist.
3. **History** — the deep ranked dive (up to 52 weeks), the richer counterpart to the profile page's light 10-week list (whose rows link back here). Contents: summary figures (full-attendance count, consistency σ, overall average attack, best score + its verdict), the two charts (avg attack/defense trend; league-progression), and the full per-week history table with week-over-week deltas. Present only when history exists.

- Tabs are **real keyboard-operable controls** (tablist semantics or buttons with `aria-selected` / `aria-controls`), per `project_coc_stats_a11y_disclosure_pattern`. The inner "full per-attack breakdown" disclosure and any per-cell detail are keyboard/touch reachable, never `title`-only.
- History charts are created lazily when the History tab is first opened and destroyed on close/rebuild (keep the current lazy-Chart lifecycle; keys must stay distinct between desktop and mobile renderings).

---

## 5. Behavior

- **Week selector** reloads the page for the chosen week (GET, as today).
- **Week-summary strip** is state-aware: compact for the live week, auto-expanded for a finished week; the expand toggle works either way. No modal auto-opens.
- **Filters/search/toggles** (standing filter, search, Show left, Show inactive) filter the roster client-side, as today. Sorting client-side, default league→rank.
- **Row → drawer:** click/keyboard toggles the tabbed drawer; row remains the target while inner controls (tabs, disclosure, links) stop propagation. Player-name links navigate to the profile and don't toggle the row.
- **Reminder** generates the DE/EN attack-reminder message (unchanged utility).
- **Reduced motion:** every transition/transform impeccable adds respects `prefers-reduced-motion` (theme rule); bar/score reveals use `transform`, not `transition: width`.

---

## 6. Empty / edge states (show last real data, never a dead placeholder)

- **No ranked week data at all:** the roster area shows the existing empty state (message + link home). Strip and recent bar omitted.
- **Selected week with no active players:** roster renders inactive/left rows per the toggles; the strip still summarizes what exists.
- **Player with no rank yet / inactive:** Zone shows an explicit "—" / "Inactive," not a fabricated position.
- **No previous week (first tracked week):** movement deltas are simply absent (no `▲0`), not shown as zero.
- **No defenses / no history:** that tab is omitted (not an empty tab), while the Verdict tab always exists for an active player.
- **League changed since last week:** rank-delta suppressed in favor of the promote/relegate arrow (§3).

---

## 7. Design-system compliance (structural fixes, not visual choices)

`DESIGN.md` rules the current template violates and the rebuild must honor:
- **Remove every `border-left: 3px` side-stripe accent** (`.rw-debrief`, `.mc`, `.recent-card` carry a 3px `--ops-ranked` left stripe) — `DESIGN.md` absolute ban on >1px side-stripe accents. Mode/verdict identity carries via full-border + tint and the accent word instead (treatment is impeccable's).
- **Mobile becomes divided roster-rows, not per-player cards** — replace the spacious `.mc` card stack with the shared `.mr`-style divided-row idiom (§8). Standing project preference, previously re-introduced and removed more than once.
- **Verdict badges use the fixed sitewide vocabulary/colors** (godlike / dominant / wow / good / warning / suck / useless-inactive) — one color per tier across the whole site, never re-themed per page.
- **No raw emoji as a functional UI icon** — the inline `🏆` used as a trophy-count label is a functional-icon use and must become the sanctioned line-icon language or the game's trophy asset. (Emoji inside the generated Reminder *message text* are message content, not UI chrome — those stay.)
- **Bars/animations via `transform`**, reduced-motion safe (consistent with the battles/raid/profile passes).
- **In-page scroll containers** (the desktop table's horizontal overflow, any drawer ledgers) use the thin inset theme-tinted scrollbar, not the native OS bar.

---

## 8. Responsive arrangement (decided)

- **Desktop:** the full aligned-column table; horizontal scroll inside its own container if the dense columns exceed width (page body never scrolls sideways).
- **Mobile:** **denser divided roster-rows + a complete tap-expand drawer.** Each player is a compact divided row showing the load-bearing signals (League · Zone/rank + movement · name/TH/trophies · Score·Verdict · attacks Ø + used/max · defenses Ø). One tap opens the **same tabbed drawer as desktop** — star splits, avg-TH figures, full defenses, the verdict math, and the 52-week history — **nothing dropped versus desktop.** No sideways-scrolling of the full table. (Chosen over a leaner headline-only row because the user reads all fields on the phone frequently.)
- **Week-summary strip:** wraps to stacked figure groups on narrow widths; the compact/expanded state logic is unchanged.
- **Recent-attacks log:** trims to its most legible columns on mobile (as the current recent-ledger already does), staying a divided list, not cards.
- Validation viewports: **390×844**, **768×1024**, **1200×800**.

---

## 9. Out of scope (this pass)
- The scoring math itself (`_calc_th_multiplier` / `_league_mult` / `_ranked_score_from_adj` / `_ranked_verdict`) — presented, not re-tuned.
- The `/ranked/analysis` week-analysis feature and its page — the entry control stays; the feature is untouched.
- The Reminder generator's message content/logic — kept as-is.
- Other pages (the player profile's light ranked history already links here; no change to it). One page per cycle.

---

## Open questions for impeccable (visual — genuinely open, not inherited)

The wireframe shown during brainstorming was grayscale/one-font on purpose; **none of its visual choices are binding.** Impeccable decides, extending the Night Ops Scope theme:
1. **Score·Verdict column** — how the 0–100 number relates to the verdict badge, and how it reads as the loudest per-row signal without overpowering the standing (League/Zone) block immediately to its left.
2. **Zone instrument** — the promotion/relegation gauge + the new week-over-week movement (rank Δ / trophy Δ) + the group-attendance caption, all in one compact cell; how up/hold/down map to theme semantic tokens without any side-stripe; how a league-change suppresses the rank-delta.
3. **Column grouping / density** — how the standing block, player, attack block, and defense block are separated in a dense aligned table (dividers, header grouping) so ten columns read as coherent groups, not a wall.
4. **Week-summary strip** — the compact↔expanded treatment; how "live vs finished" week state is signaled; the verdict-spread distribution, top-performers, and missed-attacks presentations.
5. **Tabbed drawer** — active-tab treatment (no side-stripe); the Verdict tab's formula + lever figures + the one-disclosure per-attack table; the Defenses table; the History tab's two charts (trend + league-progression) and summary figures — chart styling as design material (fills, grid, emphasized endpoints), reduced-motion safe.
6. **Recent-attacks bar** — the collapsed-bar and expanded-log treatment.
7. **Trophy / TH glyphs** — replacing the functional `🏆` emoji with the sanctioned icon language or asset.
8. **Motion** — row expand, tab switches, strip expand/collapse, bar/score reveals — all `prefers-reduced-motion` safe.

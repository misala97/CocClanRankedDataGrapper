# Player Profile Redesign — Design Spec (Structure Contract)

**Date:** 2026-07-19
**Route:** `player_bp.player_profile` → `GET /player/<tag>` (`coc_stats/features/player/routes.py:715`)
**Template:** `coc_stats/templates/player/player_profile.html`
**Status:** Structure locked, pending sign-off. Visual execution deferred to `impeccable` (see "Open questions for impeccable").

This spec fixes **structure, data mapping, behavior, and responsive arrangement only**. It does not decide palette, type, spacing, component styling, signature element, or motion — those are impeccable's to decide against the established "Night Ops Scope" theme (`DESIGN.md`/`PRODUCT.md`).

---

## 1. Goal & audience

One page, two readers: the **member checking their own week** (primary — this redesign leads with self-assessment: "where do I stand?"), and the **leader vetting a member**. The page must feel like a page a player is proud to open about themselves — a clear headline verdict, an at-a-glance map of where they're strong/weak, and drill-down receipts — not a data dump.

### What's wrong with the current page (the brief is the fix)
- **Twin redundancy:** Activity and Skill are two near-identical giant cards, each stacking 5 progress bars → 10 bars up top, no focal point.
- **Identical-card-grid smell:** ranked/raid/war/cwl render as 4 visually identical scroll-boxed list-cards — the pattern `DESIGN.md` explicitly bans.
- **No hierarchy, no moment:** page opens cold; nothing tells the player their headline standing first.
- **Live `DESIGN.md` violations** carried in the current template (must be fixed, see §7).

---

## 2. Data source (route payload)

Everything the page renders comes from the route. Current template variables:

- `player` — Player model: `name`, `tag`, `current_th`, `in_clan`, `league_tier`, `league_icon` (property), `join_date`, plus admin fields not shown here.
- `activity` — the `week` activity dict (default period convenience; superseded by `activity_periods`).
- `activity_periods` — dict keyed `week`/`month`/`6months`; only keys with `has_data` are passed. Each: `score`, `label` (Active/Regular/Casual/Inactive), `label_color`, and per-mode `ranked_score` / `battle_score` / `raid_score` / `war_score` (+`war_score_has_data`) / `cwl_score` (+`cwl_score_has_data`), each with a `_max` and a `_detail` string, plus top-level `has_data`.
- `skill_periods` — same shape; `label` ∈ Elite/Strong/Average/Weak/Novice; per-mode `*_skill` + `*_skill_has_data` + `_detail`.
- `ranked_history` — up to 10: `start_day`, `end_day`, `league_tier`, `league_icon`, `rank`, `trophies`, `att_count`/`att_max`, `att_avg`, `def_count`, `def_avg`, `is_done`, `badge_class`, `judge_label`, `score_100`, `league_season_id`.
- `raid_history` — per raid: `start`, `end`, `participated`, `att_count`, `avg_pct`, `solo_wipes`, `cleanups`, `badge_class`, `judge_label`, `score_100`, `raid_id`.
- `war_history` — up to 20: `start`, `end`, `opponent`, `att_count`, `att_max` (2), `avg_stars`, `score_100`, `badge_class`, `judge_label`, `war_id`.
- `cwl_history` — per season: `season`, `rounds_selected`, `att_used`, `att_possible`, `avg_stars`, `participated`, `score_100`, `badge_class`, `judge_label`, `season_id`.
- `battle_history` — up to 20: `time`, `opponent_tag`, `stars` (0–3), `percentage`, `gold`, `elixir`, `dark`, `type`, `attack` (bool).

---

## 3. Backend change (approved) — clan standing

**New:** a per-period standing so the hero can show "where you rank among clanmates" for both scores. Reuses the existing bulk path.

- Add `standing_periods` to the render context, keyed `week`/`month`/`6months`.
- For each period: `bulk = _calculate_scores_bulk(ranked_tags, period)` where `ranked_tags = {all in_clan player tags} ∪ {viewed player tag}` (so a left-clan player still gets placed).
- **Activity rank:** among players whose `activity.has_data` is true, `rank = 1 + count(others with strictly higher activity score)`; `size = count(has_data players)`; `pct = round(rank / size * 100)` (→ "top N%"). Same for **Skill** using `skill.has_data` + skill score.
- Per-period dict: `{ activity_rank, activity_size, activity_pct, activity_has_data, skill_rank, skill_size, skill_pct, skill_has_data }`. If the viewed player lacks data for a dimension in that period → its `*_has_data` false and the hero hides that rank line for that period.
- Serialize `standing_periods` to JS alongside `activity_periods`/`skill_periods` so the period toggle updates the rank line **client-side** with no extra request.

**Cost:** `_calculate_scores_bulk` runs 3× (once per period) over all clanmates per profile view. Accepted for this pass; a cache/precompute optimization is noted as a follow-up in "Open questions", not required now.

**Derived, no backend change:**
- **Trend indicator** — for the selected metric, compare the selected window to the next-longer available window (`week`→`month`, `month`→`6months`); show ▲/▼/– with the point delta. Not shown when `6months` is selected (nothing longer). Computed client-side from the already-serialized period dicts. Label wording must **not** imply stored historical snapshots (it's recent-window vs longer-window, not "last month's saved score") — see open questions.
- **Signature highlight** (optional accent) — the single highest per-mode component (across activity+skill) with its verdict, e.g. "CWL — Godlike". Pure max of the current-period payload.

---

## 4. Page structure (arrangement C — "fused scorecard")

Top to bottom: **Page header → Standing scorecard (fused) → Tabbed history → Recent battles.** Not-found (404) state handled by §6.

### 4.1 Page header (reuse `_page_header.html` slots — no new page-local header markup)
- `page_header_title` — player name, with a "You" affordance when `current_user.linked_player_tag == player.tag` (function: mark self-view). One accent span allowed by the component.
- `page_header_meta` — figures: Tag; clan status (In Clan / Left Clan, with tone); Joined date (if present).
- `page_header_right` — identity block: league icon + tier, and town hall. (The current id-chip already fits this slot; keep using the slot, restyle via impeccable.)
- `page_primary_control` — the **period toggle** (week / month / 6months). One control, drives the whole hero. Rendered from the available periods only.

No new slot is required — the existing title/meta/right/primary-control API covers the header. (If, during build, the "You" marker or standing needs a slot the component lacks, that's a `_page_header.html` extension proposed separately per Non-Negotiable 4 — not page-local markup.)

### 4.2 Standing scorecard (the hero — one card, replaces the twin score cards)
Function: headline verdict + the evidence that justifies it, together. Contents, in order:
1. **Period label** — which window is shown ("this month" etc.), driven by the toggle.
2. **Two headline scores** — Activity and Skill: the number (0–100) + its word label (Regular / Average / …). These are the focal elements of the page.
3. **Standing line** — from `standing_periods[period]`: activity rank ("#8 of 42") and skill rank + percentile ("#5 of 42 · top 12%"). Each half hidden if its `*_has_data` is false. Plus the **trend indicator** for the selected metric(s).
4. **Divider**, then the **strength map**.

**Strength map** (function: at-a-glance strong/weak across all modes — the analytical heart; replaces 10 stacked bars):
- 5 mode rows in fixed order: **Ranked, Raid, Farm Attacks, Clan War, CWL**.
- Each row has two cells: **Activity** and **Skill**. A cell = the mode's score for that dimension + a proportional bar (score/max) + access to the mode's `_detail` string.
- **No-data cell:** when a mode's `*_has_data` is false for the selected period, the cell shows an explicit no-data treatment (function: "not applicable this period"), not a zero bar that reads as "bad".
- Detail strings (`ranked_detail`, etc.) are available per cell — surfaced on demand (hover/expand/popover — mechanism is impeccable's, but it MUST be reachable by keyboard and touch per the project's a11y disclosure pattern, not `title`-only).

### 4.3 Tabbed history (one component, replaces 4 identical list-cards)
Function: drill into one mode's per-period receipts over time.
- Tabs: **Ranked / Raid / War / CWL** (only tabs with data present; a tab with an empty list still shows its empty state rather than vanishing if the mode is relevant — see §6).
- Active tab renders its stream as rows. Each row (per mode data mapping):
  - **Ranked:** date range; `#rank`; `trophies`; `att_count`/`att_max`; `att_avg` stars; `def_count`/`def_avg` if present; verdict badge (`judge_label`, cleaned of parenthetical) + `score_100`. Row links to `/ranked?week_id=<league_season_id>`.
  - **Raid:** date range; `att_count`/6; `avg_pct`; `solo_wipes`; `cleanups`; verdict + `score_100`. Links to `/raid?raid_id=<raid_id>`.
  - **War:** vs `opponent`; date range; `att_count`/`att_max`; `avg_stars`; verdict + `score_100`. Links to `/war?war_id=<war_id>`.
  - **CWL:** `season`; `rounds_selected`; `att_used`/`att_possible`; `avg_stars`; verdict + `score_100`. Links to `/cwl?season_id=<season_id>`.
- **Absent/skipped rows** (didn't participate / no attacks) render as a demoted state carrying the real reason ("Did not participate", "No attacks", "Skipped") — not hidden, not styled as a failure verdict.
- Tabs are real keyboard-operable controls (tablist semantics or buttons with `aria-selected`/`aria-controls`), matching the project a11y disclosure pattern. Only one stream visible at a time is intentional (the cross-mode compare job is done by the strength map above).

### 4.4 Recent battles (its own strip — kept separate from history)
Function: raw recent-activity log (attacks **and** defenses), distinct from the per-period verdict streams.
- Desktop: the wide table — Time, Type (Ranked/Home/other badge), Direction (ATK/DEF), Opponent, Stars (0–3), Damage %, Gold, Elixir, Dark.
- Loot values use the shared loot color semantics **defined as DESIGN.md tokens** (see §7 — the current hardcoded hex is removed).
- Empty state: "No battles recorded."

---

## 5. Behavior

- **Period toggle** is the single driver of the hero: switching it re-renders headline scores, standing line, trend, and the strength map — all **client-side** from pre-serialized `activity_periods` / `skill_periods` / `standing_periods`. Default selected period: `month` if available, else the first available.
- **History tabs** switch the visible stream client-side; do not reset the period toggle.
- **Row navigation:** history rows navigate to the corresponding mode page (links above). Must be real links/keyboard-activatable, not `onclick`-only divs.
- **Detail disclosure** (strength-map cell details): keyboard- and touch-reachable, per `project_coc_stats_a11y_disclosure_pattern` (native popover / real buttons; never `title`-only).
- **Reduced motion:** any transitions impeccable adds respect `prefers-reduced-motion` (theme rule).

---

## 6. Empty / edge states (show last real data, never a dead placeholder)

- **404 / unknown tag:** the route already renders `player=None`. Header shows "Player Not Found" + the tag; body omitted. Keep.
- **Period with no data:** excluded from the toggle already (only `has_data` periods passed). If a player has *no* periods at all, the hero shows an explicit "not enough data yet" state (not an empty grey card, not a `📊` emoji — see §7).
- **Mode no-data in the map:** explicit no-data cell (§4.2), not a zero bar.
- **Empty history tab:** show the mode's empty message ("No ranked history." etc.), keep the tab.
- **Left-clan player:** still ranked among the current in-clan set (§3) so the standing line still resolves; clan status meta reads "Left Clan".

---

## 7. Design-system compliance (structural fixes, not visual choices)

These are `DESIGN.md` rule fixes the current template violates and the rebuild must honor:
- **Remove the `border-left: 3px` verdict stripe** (`.bl-*`) on every history row — `DESIGN.md` absolute ban on >1px side-stripe accents. Verdict identity carries via the verdict badge + full-border/tint treatment instead (impeccable decides the exact treatment).
- **Loot colors become OKLCH design tokens**, not hardcoded `#f5b921` / `#d954d1` / `#9d8fd4`. Same loot hues used on the battles page — define once as tokens so a player's loot reads identically everywhere.
- **No emoji as functional UI icon** — the `📊` empty-state glyph is removed; empty states use the sanctioned icon language (or a text-only empty state). Emoji remain allowed only for celebratory moments (e.g. a signature-highlight flourish), per the theme's carve-out.
- **Bars animate via `transform`, not `transition: width`** — consistent with the battles-page motion pass.
- **Dense-table mobile rule:** Recent Battles must drop to the shared **divided roster-row** pattern on mobile (`.mr`-style rows: identity + verdict on top, wrap of mono stats below), **never** a stack of per-player cards. Standing project preference.

---

## 8. Responsive arrangement (decided)

- **Hero scores:** the two headline scores sit side by side even on mobile (they're short); the standing line wraps beneath.
- **Strength map:** **stays a matrix, narrower** on mobile — 5 mode rows, each with two compact Activity | Skill cells side by side (decided; not a dimension-toggle, not per-mode stacking). Preserves the compare-all-modes-at-once value.
- **Tabbed history:** tabs may scroll horizontally if cramped; rows reflow to the roster-row idiom.
- **Recent battles:** table → divided roster rows on mobile (§7).
- Validation viewports: **390×844**, **768×1024**, **1200×800**.

---

## 9. Out of scope (this pass)
- Hero levels / TH progression (`_hero_power` in `ranked_analysis.py`) — separate feature; id-chip already carries TH + league identity.
- Any change to the scoring math itself (`calculate_activity_score` / `calculate_skill_score` / verdict functions) — this redesign presents existing scores, it does not re-tune them.
- Other pages. One page per cycle.

---

## Open questions for impeccable (visual — genuinely open, not inherited)

The wireframe shown during brainstorming was grayscale/one-font on purpose; **none of its visual choices are binding**. Impeccable decides, extending the Night Ops Scope theme:
1. **Headline score treatment** — how the two big numbers + word-labels read as the page's focal moment (size, weight, how the verdict label relates to the number). How the label color maps (`label_color` values are `green`/`blue`/`purple`/`yellow`/`muted`/`red` — map to theme tokens).
2. **Strength-map cell** — bar style vs. alternative encoding; how Activity vs Skill columns are distinguished; how each mode's own category hue (Ranked=Recon Blue, Raid=Raid Red, War=War Amber, CWL=CWL Violet, Farm=?) appears without turning the map into a rainbow.
3. **Standing line & rank flex** — how "#5 of 42 · top 12%" is expressed to feel like an achievement without shouting; percentile/rank emphasis.
4. **Trend indicator** — visual form (arrow/delta/chip) and the exact honest wording (must not imply stored history).
5. **Signature highlight** — whether to include it, and if so its form (this is the sanctioned celebratory/emoji moment, if any).
6. **History tabs** — active-tab treatment (must not be a side-stripe); how verdict badges + `score_100` sit in a row; per-mode identity in the tab set.
7. **Recent-battles** loot token values (OKLCH) and the roster-row treatment on mobile.
8. **Motion** — score/bar reveal, tab switches, detail disclosure — all reduced-motion safe.
9. **Perf follow-up** (not blocking): whether the 3×-per-view clan bulk-score should move to a cached/precomputed source.

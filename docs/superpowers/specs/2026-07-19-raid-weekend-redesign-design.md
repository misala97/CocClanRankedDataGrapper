# Raid Weekend (`/raid`) — Redesign Design Spec

**Date:** 2026-07-19
**Page:** `/raid` → `coc_stats/templates/raid/raid_weekend.html`
**Route:** `raid_weekend_page` in `coc_stats/features/raid/routes.py`
**Status:** Structure contract. Locks sections, hierarchy, data mapping, behavior,
responsive arrangement, and component *function*. Visual treatment (palette, type,
spacing, component look, signature, motion) is out of scope here — it is decided by
`impeccable` at craft time. Open visual questions are collected at the end.

This is a **later page** in an established system (DESIGN.md / PRODUCT.md already exist
from the index, nav, page-header, and clan-overview passes). It **extends** that theme;
it does not re-open it.

---

## 1. Goal

Turn a single flat analyst table into a **state-aware raid command console**. The same
route serves two moments and two audiences (PRODUCT.md: leaders + members, equally):

- **Ongoing (mid-raid):** an action surface — who still has attacks, what districts
  remain, live attack feed, projected medals. Answers "what do I do next / who do I
  chase."
- **Ended (post-raid):** a recap — leaderboard, MVP + awards, and whether the clan beat
  its pre-raid medal estimate. Answers "how did we do / who carried."

Non-goals: reworking the medal-impact math itself, the verdict scoring, or the siege-map
inference logic — all of that is correct and stays. This is structure + presentation +
one backend data addition.

---

## 2. Backend change (the one addition)

The current route builds its player list **only from attack logs**, so any in-clan member
who has not attacked is invisible. The mid-raid war-room's core question ("who still has
attacks?") is therefore unanswerable today.

**Add:** the route builds a `roster_status` structure for the selected raid.

Per in-clan member (`Player.query.filter_by(in_clan=True)`), reconciled against this
raid's logs:

```
{
  player_name, player_tag,
  attacks_used,          # count of this member's logs, capped at 6
  attacks_left,          # 6 - attacks_used
  has_attacked,          # attacks_used > 0
}
```

Plus aggregates:

```
clan_attacks_remaining   # sum of attacks_left over in-clan members
participated             # count of in-clan members with has_attacked
roster_total             # count of in-clan members
participation_pct        # participated / roster_total
```

**Staleness rule.** `in_clan` reflects the roster **now**, not at raid time. Therefore:

- The **no-show name list** (members with `has_attacked == false`) renders **only when
  `selected_raid.state == 'ongoing'`**. On an old ended raid, a member who has since left
  would otherwise be wrongly named as a no-show.
- `roster_status` and its aggregates may be computed for any selected raid, but the
  *ended-state* surfaces use only the aggregate participation **count** (`participated /
  roster_total`) as a recap figure — never the individual no-show names.

`player_data`, the medal-impact buckets, verdict scoring, siege-map JSON, and the medal
estimate are all unchanged. `roster_status` is passed alongside them.

No new `_page_header.html` slot is required — see §7.

---

## 3. Page structure

Document order (single scroll). The two-column zone is the console's action tier; every
other band is full width.

```
HEADER            (shared component — existing slots)
REPORT BAND       state-aware headline figures
YOU BAND          personal readout (only when a player is linked)
┌─ LEFT COLUMN ──────────────┬─ RIGHT COLUMN ──────────────┐
│ ongoing: WAR-ROOM          │ SIEGE MAP  (primary)        │
│ ended:   HIGHLIGHTS        │ RECENT-ATTACKS FEED         │
└────────────────────────────┴─────────────────────────────┘
LEADERBOARD       verdict-led rows → expandable breakdown
FOOTER SUMMARY    count line (existing)
```

### 3.1 Header (existing shared component)

Reuses `_page_header.html` slots as-is:

- `page_header_title`: "Raid **Weekend**" (one accent span, as today).
- `page_header_meta` (mono readout figures), state-aware:
  - Ongoing: `{weekend dates}`, `{status: ONGOING}`, `{clan_attacks_remaining} attacks left`.
  - Ended: `{weekend dates}`, `{status: ENDED}`, `{raid medals}` (actual).
- `page_primary_control`: the raid-weekend selector (unchanged).
- `page_controls`: the player search input (unchanged).

### 3.2 Report band (state-aware headline figures)

A single band of headline figures. Content differs by state; it is the same *component*.

- **Ongoing:** attacks remaining (clan) · capital loot so far · districts destroyed ·
  ≈ projected medals (`est_medals_6atk`). "Projected" must read as an estimate.
- **Ended:** capital loot (final) · **raid medals** (`defensive_reward + offensive_reward
  × 6`) carrying a **delta vs the pre-raid estimate** as a first-class element (today this
  delta is hidden in a tooltip) · districts destroyed · avg attacks / district.

The actual-vs-estimate delta is a *verdict* on the number (PRODUCT.md: verdicts over raw
numbers), not decoration — surface it, don't bury it.

### 3.3 You band (personal — only when a player is linked)

Rendered only when `current_user` has a `linked_player_tag`. Pulls that player's own row.

- Shows: attacks used / 6, verdict, personal loot, solo wipes, overall impact.
- **Ongoing + attacks_left > 0:** a nudge ("2 attacks remaining").
- **Ongoing + linked player has no logs yet:** the band still renders, as a "you haven't
  attacked yet — 6 attacks waiting" prompt (data comes from `roster_status`, not
  `player_data`).
- **Ended:** static personal line, no nudge.
- Logged-out / unlinked: band omitted entirely (no on-ramp CTA in scope for this page).

### 3.4 Left column — War-room (ongoing) OR Highlights (ended)

**War-room (state == ongoing):** the attacks-remaining roster from `roster_status`.

- Header line: "N members · M attacks remaining".
- List members with `attacks_left > 0`, **most-remaining first** (a member who hasn't
  swung at all is the top priority to chase). Each row: name + attacks_left.
- Members who are done (`attacks_left == 0`) collapse under a "▸ K done" disclosure.
- Empty/edge: brand-new ongoing raid with zero logs → every in-clan member shows 6 left
  (this is correct and useful, not an empty state).

**Highlights (state == ended):** MVP + auto-awards, computed client-side from
`player_data`. See §4.

### 3.5 Right column — Siege Map + Recent-attacks feed

- **Siege Map** is the primary occupant of the right column and is **promoted out of its
  collapsed card** — it is the page's signature visual and should not be hidden behind a
  click. Mid-raid it defaults **open**; post-raid it may default collapsed (see open
  questions). The per-enemy-clan pyramid, district-unlock inference, efficiency coloring,
  medal-value hints, and attacker tooltips are all preserved from the current
  implementation — only its placement and default-open behavior change.
- **Recent-attacks feed** sits beneath the siege map in the same column: the last 20
  attacks (player · district · lvl · stars · % · cleanup), newest first. Mid-raid this is
  the live activity ticker.

### 3.6 Leaderboard (full width) — verdict-led, impact on demand

The always-visible row carries the **human-readable story**; the medal-impact math moves
into an expandable breakdown.

**Main row columns:** Player · Attacks · Loot · Solo Wipes · **Overall Impact** (one
signed number) · Verdict (+ score). Sortable, default sort by verdict score descending.
Search filters it (existing behavior). The linked player's own row is highlighted.

**Expandable breakdown (per row):** the full medal-impact detail that today occupies four
always-on columns — Medals/Atk (regular rate + impact delta), Peak Medals/Atk (rate +
impact), Overall Shift — **plus** the existing per-district adjusted-score verdict table
and the triple-solo-wipe banner. This is the current `buildVerdictDetails` output extended
with the impact rows. The quiet baseline reference (combined / district / peak medals per
attack) is presented as context for these numbers rather than as a standalone strip.

**Non-attackers (ongoing only):** in-clan members with no logs appear as a collapsed
"▸ N members didn't attack" tail beneath the ranked rows (sourced from `roster_status`),
so the leaderboard reflects the full roster without cluttering the ranked list. Gated to
ongoing per the staleness rule (§2).

### 3.7 Footer summary

The existing count line ("N players shown · S solo wipes · L capital loot"), unchanged in
function.

---

## 4. Highlights (ended state) — data mapping

All computed client-side from `player_data`; no backend support needed. An award renders
**only when it has a qualifying winner** (never an empty or zero award).

| Award | Winner rule |
|---|---|
| **MVP** | highest `score_100` (the headline verdict); ties broken by `overall_impact` |
| **Biggest Carry** | highest `overall_baseline_shift` (> 0) |
| **Cleanup Hero** | most `cleanup_count` (> 0) |
| **Peak Slayer** | highest `peak_medals_per_attack` among players with a peak attack |
| **Triple Wipe** | any player with `solo_wipes >= 3` (one chip per qualifying player) |

MVP is always shown when at least one player exists; the rest are conditional.

---

## 5. Responsive behavior

Mobile question (Non-Negotiable 2) answered: this content needs a **different
arrangement**, not just narrower columns.

- **Two-column zone collapses to one** below ~900px: left block (war-room / highlights)
  stacks **above** the right block (siege map, then feed), preserving document order.
- **Leaderboard → card list** below ~640px (the existing table→cards pattern is kept:
  table for desktop, per-player cards for mobile, both driven from the same `player_data`).
  The main card shows the same lean set (attacks, loot, solo wipes, impact, verdict); tap
  expands the same breakdown.
- **Siege pyramids** reflow via the existing auto-fill grid; verify no horizontal overflow
  and no clipped district names at 390px.
- **Report band** figures wrap to a 2-up / 1-up grid on narrow widths (existing ledger
  responsive behavior is a starting point).

Viewports to validate: **390×844**, **768×1024**, **1200×800**.

---

## 6. Empty / edge states

- **No raid data at all:** existing "No raid weekend data available yet" state.
- **Raid selected, no logs, ended:** existing "No attack logs recorded" state.
- **Raid selected, no logs, ongoing:** *not* a dead state — war-room shows the full roster
  (everyone 6 left), report band shows zeros/projection, siege map may be empty. Show the
  live scaffolding, not a placeholder.
- **Ended raid, medal estimate unavailable:** report band shows actual medals without the
  delta (delta requires `est_medals_6atk`).

Per the skill's quick-reference: prefer last real data over dead placeholders.

---

## 7. Shared-shell impact

- `_page_header.html`: **no change** — the page's data fits the existing
  title / desc / meta / primary-control / secondary-controls slots (§3.1). No page-local
  header markup, no new slot.
- `_nav.html`, `_head.html`, footer: no structural change. The page continues to run under
  the existing Raid mode identity (the `body.raid-page` retint hook stays).

---

## 8. What is explicitly preserved

- Medal-impact bucket math (regular vs peak, cleanup exclusion, baseline shift, overall
  weighting) — unchanged; only *where* it surfaces changes.
- Verdict scoring (`raid_score_verdict`) and the badge vocabulary — unchanged.
- Siege-map inference (district unlock order, efficiency thresholds, medal-value hints,
  attacker tooltips) — unchanged logic, new placement.
- Raid selector labels ("Current Weekend" / "Last Weekend" / date ranges) — unchanged.
- Per-district adjusted-score breakdown table — unchanged, folded into the expand.

---

## Open questions for impeccable

These are visual/interaction decisions deliberately **not** answered here — they belong to
the craft pass, not the structure contract:

1. **How the two states are visually distinguished.** Ongoing vs ended is a structural
   fork; how the console *reads* as "live" vs "recap" (treatment of the report band, the
   war-room, any live-pulse affordance) is impeccable's call, within the existing
   Raid-mode identity and DESIGN.md's motion/reduced-motion rules.
2. **Siege map default state post-raid** — open, collapsed, or a compact summary with
   expand. Structure allows any; pick the one that reads best.
3. **War-room list expression** — how "attacks remaining" and the most-remaining-first
   ordering are made scannable (the roster could be a list, chips, or a compact meter);
   function is fixed, form is open.
4. **Report-band actual-vs-estimate delta** — how the delta is expressed as a verdict
   (direction, emphasis) without a second accent hue competing with Raid red.
5. **Highlights / awards expression** — MVP prominence vs the conditional award chips;
   how a "Triple Wipe" moment is celebrated without a bolted-on banner.
6. **Leaderboard Impact column** — how one signed impact number reads at a glance, and how
   the expand transitions in.
7. **Right-column feed vs siege split** — stacked, tabbed, or a quiet secondary tier under
   the map.

Everything above the line is locked; everything in this section is genuinely open for
impeccable to decide and return with a rationale.

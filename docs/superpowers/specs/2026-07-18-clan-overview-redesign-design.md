# Clan Roster (/clan) redesign — design spec

## Scope

Structure and behavior only, for `coc_stats/templates/player/clan_overview.html`,
rendered by `clan_overview()` (`coc_stats/features/player/routes.py:1249-1277`,
scoring via `_calculate_scores_bulk`, `routes.py:947-1246`). Visual treatment
(palette, type, component styling) is out of scope — hands off to
`impeccable craft` after sign-off. This page already uses the shared
`_page_header` slots, OKLCH theme tokens, and `.action-btn`/`.selector`
control classes from the nav/header redesigns — those are reused as-is, not
reopened.

## Data source

Everything below comes from `clan_overview()`'s `render_template` call and
`_calculate_scores_bulk`. No template variable is treated as a given.

- **Page-level**: `period` (`week` / `month` / `6months`, query param)
- **`player_cards`** — one entry per in-clan player, each with:
  - `name`, `tag`, `tag_url`, `th`, `league_icon`
  - `activity`: `score`, `label`, `label_color`, `has_data`, plus per-mode
    `ranked_score`, `battle_score`, `raid_score` (always included),
    `war_score` + `war_score_has_data`, `cwl_score` + `cwl_score_has_data`
    (excluded from the average when the player had no roster opportunity —
    confirmed intentional, not a bug)
  - `skill`: `score`, `label`, `label_color`, `has_data`, plus per-mode
    `ranked_skill`, `raid_skill`, `battle_skill`, `war_skill`, `cwl_skill`,
    each with its own `_has_data` flag
  - `combined` — `activity.score + skill.score`, default sort key
- **Not currently passed to the template** but present on `Player`:
  `war_preference_in_game`, `war_preference_custom` — see Backend change.
- **Not in the data model at all**: clan role (leader/co-leader/elder),
  donations, trophies. Raised during brainstorming and explicitly left out
  of scope — no column exists for any of them.

## Backend change

Add one field to each `player_cards` entry: `war_pref`, computed as
`player.war_preference_custom or player.war_preference_in_game or None`
(values: `'in'`, `'out'`, or `None`) — the same effective-preference
resolution already shown split out as two columns in Admin Hub
(`admin/admin_hub.html:459-479`), collapsed here to one badge since this
page is read-only, not an editing surface.

This field is **only added to the response when the requesting user is a
super admin** (`_is_super_admin()`, same helper already imported in
`app.py:89`) — checked server-side in the route, not just hidden by CSS/JS.
Non-admins' `player_cards` JSON never contains the key, so it can't be read
from page source by a non-admin. Confirmed with the user: admin-only
visibility, matching the existing pattern used elsewhere for admin-only
member fields.

## Structure (desktop / tablet — unchanged)

The existing card grid, sort/search controls, mode legend, and always-visible
Activity/Skill halves (each with headline score + label + 5 labeled mode
bars) are confirmed still correct for desktop and tablet — not reopened.
This matches the standing rule that the whole point of this page is
scanning the full roster's per-mode breakdown in one pass, never gated
behind a click (`clan_overview` no-click-gating feedback, still binding).

- **Desktop (1200px)**: 4-column card grid, unchanged.
- **Tablet (768px)**: 2-column card grid, unchanged (existing 900px
  breakpoint already covers this width). Flagged for sign-off review since
  it wasn't re-examined this cycle the way mobile was — correct me here if
  tablet should also move to the new row layout below.

Card header gains one optional element: when `war_pref` is present (admin
only), a small badge showing `In` / `Out`, placed next to the existing TH
badge in the card header row. Absent for non-admins and for players with no
resolved preference — no empty placeholder.

## Structure (mobile — genuinely re-examined, not just reflow)

Confirmed with the user that mobile needs a real "quick overview of current
roster state" reading, distinct from a shrunk desktop card, with full detail
available one tap away on the player's own page (`/player/<tag>`, already
the card's link target).

**Chosen arrangement ("Option B" from wireframes):** one compact row per
player, replacing the full stacked card below the mobile breakpoint.

```
[rank · league · name          ]  [ACT 88]  [SKL 71]
[TH16 · (war-pref badge, admin)]  [██████████ 10-segment sparkline strip]
```

- Left: rank, league icon, name (truncated), TH badge, admin-only war-pref
  badge — same identity info as the desktop card header, just single-line.
- Right: the two headline numbers (Activity score, Skill score) — same
  values as desktop, no label/color decisions made here.
- Below the identity line: **one combined 10-segment strip** (5 Activity
  segments + 5 Skill segments, in the same ranked→raid→battle→war→cwl order
  as the desktop bars and the shared legend), replacing the two separately
  labeled 5-bar stacks. No per-segment text label on the row itself — the
  page's existing mode legend (already shown once above the list) plus
  per-segment tap/hold tooltip (same mechanism as the desktop bars' `title`
  attribute today) carry the meaning.
- A mode with no data (e.g. `war_score_has_data: false`) renders its segment
  in the existing "no data" treatment already used for the desktop bars —
  exact rendering (hollow tick vs. hatch pattern at this smaller size) is an
  open question for impeccable, not decided here.
- This is a density/layout change only — no data is hidden, no interaction
  is added to see it. All 10 values remain visible on first render, matching
  the no-click-gating rule.
- Search, sort, and period controls: unchanged, still rendered through the
  existing `page_primary_control`/`page_controls` slots.
- Legend: unchanged position (above the list), reused unchanged from
  desktop — becomes more load-bearing on mobile since bars lose their text
  labels, called out here so impeccable doesn't shrink or deprioritize it.

### Rejected mobile alternatives
- **Option A** (tightened version of today's full stacked card): kept as
  baseline in the wireframe round but not chosen — still only ~1.5 players
  per screen, doesn't deliver "quick overview."
- **Option C** (2-up tight card grid, bars kept but unlabeled): also
  presented, not chosen — ~5-6 players per screen, less dense than the row
  layout and still visually a card grid rather than a scannable list.

## What stays as-is

- Card→`/player/<tag>` link target (mobile row keeps the same link).
- Mode legend content and the `ranked/raid/battle/war/cwl` ordering.
- Sort options (Combined / Activity / Skill / Name) and client-side
  search-by-name filter.
- Empty states ("No Members Found", "No Matches") — unchanged copy/logic.
- Period toggle (week / month / 6 months).

## Out of scope / future opportunities (not this cycle)

- Clan role, donations, trophies — no backing data; would need new columns
  and a sync source, raised and explicitly deferred.
- Editing war preference from this page — Admin Hub remains the only place
  that mutates `war_preference_custom`; this page only ever displays it.
- Exact mobile breakpoint where the row layout takes over from the desktop
  card grid — implementation-time check against the existing 600–900px
  breakpoints, not spec-locked here.

## Open questions for impeccable

- How the 10-segment mobile sparkline strip should look (segment shape,
  gap, height, "no data" treatment) — function is locked (10 segments,
  fixed order, always visible), look is not.
- Whether the admin-only war-pref badge shares a visual language with the
  existing TH badge or gets its own treatment.
- Whether the mode legend needs a visual weight increase on mobile now that
  it's the only place mode labels appear in the row layout.
- Signature element / component styling for the row layout itself — nothing
  about type, color, spacing, or radii is decided in this spec.

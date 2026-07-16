# coc_stats Dashboard (`index.html`) Redesign — Design Spec

## Context

A prior ad-hoc redesign (`3245347 redesign`, `66c52a8 redesign fixes`) reworked
several coc_stats pages — including `index.html` — without going through a
proper design process. This spec redoes the dashboard page through
brainstorming: driven by the data the route actually produces, not by
carrying forward the old page's structure. Later pages (`clan_overview.html`,
`player_profile.html`, `ranked_weeks.html`, `raid_weekend.html`,
`battle_history.html`, and the untouched pages) get their own specs, one at a
time.

Shared shell (`_head.html` / `_nav.html`) stays in scope for refinement, not
replacement — see Visual Direction below.

## Data Source

Everything on the page comes from `app.py`'s `index()` route (`app.py:146`)
and the sitewide `inject_auth` context processor (`app.py:131`). No new
backend work — this is a template/CSS redesign only, but a few fields need
new derived states (see "Zero active events" below):

- `clan_name`, `clan_badge_url`
- `total_members`, `battle_logs_this_week`, `ranked_battles_this_week`, `week_start_name`
- `active_war`, `active_raid`, `active_raid_est_medals`
- `active_cwl_season`, `active_cwl_war`, `cwl_win_status`
- Personal (only populated when `current_user.linked_player` exists):
  `player_ranked_left`, `player_th`, `player_league`, `player_ore`,
  `player_attacks_this_week`, `player_war_stats` (`attacks`, `wars`),
  `player_cwl_stats` (`attacks`, `wars`), `player_gain_settings_json`
  (drives existing client-side ore rate calc, `pog-*-d`/`pog-*-m` spans —
  behavior unchanged)
- From context processor: `newbie_check_count` (admin tile alert badge)

## Visual Direction

**Ops Evolved** — refine the current dark/gold "war-room" identity
(`--bg`/`--accent`/`--purple` etc. in `_head.html`, hex badge shape, Big
Shoulders Display for display type) rather than replace it. This was chosen
over a from-scratch "clean minimal analytics" direction and a "playful
gamified" direction after reviewing mockups of all three.

## Page Structure

Four vertical bands, in order:

1. **You band** — personal, full-width
2. **Clan band** — clan-wide event + activity status, full-width
3. **Command Deck** — kept from the old page: tile grid linking to every
   section (Ranked/Battles/Raid/War/CWL/Clan/Admin). Restyle only, no
   structural change — nav bar already covers navigation but this launcher
   grid earns its place as a visual overview of "everything this app does."
4. **Footer** — kept, cosmetic refresh only

Neither the You band nor the Clan band is subordinate to the other — equal
visual weight, stacked rather than side-by-side (see Layout Mockups below).
The page reads as a calm status board: informational, not action-nudging —
no "you should attack now" banners, no urgency styling beyond the win/loss/
undecided color coding that's already present in the data (`cwl_win_status`).

### You band

- **Identity line**: player name, TH badge (`player_th`), league
  (`player_league`) — single compact row, not a large "Welcome back" headline.
  Kept explicitly personal per user feedback (name/TH/league matter more than
  strict minimalism here).
- **Chip row** (4 chips, fluid grid — see Responsive):
  - Ranked attacks left this week (`player_ranked_left`)
  - War attacks (`player_war_stats.attacks` / `.wars` wars, last 30d)
  - CWL attacks (`player_cwl_stats.attacks` / `.wars` rounds, last season)
  - Attacks since `{week_start_name}` (`player_attacks_this_week`, neutral
    color at 0 — no shame-coloring)
- **Ore strip**: shiny/glowy/starry (`player_ore`), existing client-side
  rate calc (`pog-*-d`/`pog-*-m`) and link to `/tools/equipment` unchanged —
  restyle only.
- **Guest / unlinked state**: the entire band collapses to one slim line —
  no empty chips, no wasted vertical space. Two distinct cases: no
  `current_user` (not logged in) shows "Log in to see your personal stats";
  logged in but no `linked_player` shows "Link your player tag to see your
  personal stats".

### Clan band

- **Event tickets**: one card per *currently active* event only
  (`active_war`, `active_cwl_war`, `active_raid` — 0 to 3 cards). Grid
  reflows to however many exist; cards are not padded out with idle
  placeholders for inactive events (war/CWL/raid are each only live a
  fraction of the month — permanent idle cards would be clutter most days).
  - War ticket: state (Preparation/In War), `clan_stars`★ vs
    `opponent_stars`★, attack counts, start time, link to `/war`
  - CWL ticket: score, round, win-status tag from `cwl_win_status`
    (Safe Win / Out of Reach / Undecided), link to `/cwl`
  - Raid ticket: `active_raid_est_medals` estimate, link to `/raid`
- **Idle events**: for any of War/CWL/Raid with no active instance, show a
  compact "last result" line instead of an empty card or dead link — e.g.
  "Last war: Won 42★–38★ · 3d ago". Requires a new backend query per event
  type (see Backend Changes below). If even the last-completed record
  doesn't exist (brand new clan, no history yet), fall back to a plain link
  to that section. Only when **none** of the three have any active or past
  record does the whole ticket row collapse to one line: "No activity yet."
- **Pulse strip**: `total_members`, `battle_logs_this_week`,
  `ranked_battles_this_week` — always shown (not event-tied, always has
  real data), single fluid row.

## Backend Changes

`index()` gains three new queries, mirroring the existing active-event
queries but filtered to the completed state and ordered most-recent-first,
`limit(1)` each:

- `last_war = ClanWar.query.filter(ClanWar.state == 'warEnded').order_by(ClanWar.start_time.desc()).first()`
- `last_raid = RaidWeekend.query.filter(RaidWeekend.state == 'ended').order_by(RaidWeekend.start_time.desc()).first()`
- `last_cwl_war = CWLWar.query.filter(CWLWar.state == 'warEnded', db.or_(CWLWar.clan_tag == CLAN_TAG, CWLWar.opp_tag == CLAN_TAG)).order_by(CWLWar.id.desc()).first()`

Each is only run when its corresponding `active_*` is `None` (no need to
query history for an event that's currently live). Passed to the template
alongside the existing `active_*` variables. This is the only backend
change — everything else in this spec is template/CSS.

## Responsive Approach

No separate hand-tuned mobile/tablet/desktop layouts. The chip row, ticket
row, and pulse strip all use CSS Grid `repeat(auto-fit, minmax(<min>, 1fr))`
so columns collapse naturally as width shrinks — same markup and CSS at
every breakpoint. Validated via mockup at 390px (iPhone 16e), 760px
(tablet), and 1200px (desktop):

- Chip row: `minmax(120px, 1fr)`
- Ticket row: `minmax(200px, 1fr)`
- Pulse strip: `minmax(90px, 1fr)`
- Ore strip stays a fixed 3-cell flex row (never more than 3 items, always
  fits down to 360px)

This deliberately avoids the previous project's pattern of bolting
`@media (max-width: 640px)` structural overrides onto desktop-first markup
after the fact (the cause of the earlier sticky-header mobile bug on other
pages). Desktop, tablet, and mobile get equal design consideration up front
instead of mobile being a final patch pass.

## Out of Scope

- Command Deck tile *content* or link targets (restyle only)
- Footer content (restyle only)
- Other pages (`clan_overview.html`, `player_profile.html`, etc.) — separate
  specs, one page at a time, per user's explicit request

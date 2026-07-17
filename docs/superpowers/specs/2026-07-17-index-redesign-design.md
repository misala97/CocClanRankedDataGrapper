# Index landing page redesign — design spec

## Scope

Structure and behavior only, for `coc_stats/templates/index.html`, rendered by
`index()` in `coc_stats/app.py:146-334`. Visual treatment (palette, type,
component styling, signature element) is out of scope — hands off to
`impeccable craft` after this spec is signed off. This is one page in a
multi-page redesign; other pages are separate cycles.

## Data source

Everything below comes from `index()`'s `render_template` call
(`app.py:306-334`) and the models it queries (`coc_stats/models.py`). No
template variable is treated as a given — each one is named here because the
route actually produces it.

- **Clan identity**: `clan_name`, `clan_badge_url`, `total_members`
- **Clan weekly activity**: `battle_logs_this_week`, `ranked_battles_this_week`, `week_start_name`
- **War**: `active_war` (`ClanWar` or `None`), `last_war` (only populated when `active_war` is `None`)
- **Raid**: `active_raid` (`RaidWeekend` or `None`), `active_raid_est_medals`, `last_raid` (only populated when `active_raid` is `None`)
- **CWL**: `active_cwl_season`, `active_cwl_war`, `cwl_win_status`, `last_cwl_war` (only populated when `active_cwl_season` is `None`)
- **You (personal)**: `player_th`, `player_league`, `player_ore` (shiny/glowy/starry stockpile), `player_attacks_this_week`, `player_ranked_left`, `player_war_stats` (attacks/wars, 30-day window), `player_cwl_stats` (attacks/wars, most recent ended season), `player_war_stats_json` / `player_cwl_stats_json` (projected ore gain, feeds the existing Ore Gain calculator), `player_gain_settings_json`
- `CLAN_TAG` — used for war/CWL side comparisons

## Backend change (agreed with user)

`compute_cwl_win_status` (`services/helpers.py:676`) computes
`safe_win`/`cant_win`/`undecided` for an in-progress `CWLWar`, but no
equivalent exists for a regular `ClanWar` — `active_war` is passed to the
template with no computed verdict. Field names differ between the two models
(`ClanWar.opponent_stars/opponent_attacks/opponent_destruction_pct` vs.
`CWLWar.opp_stars/opp_attacks/opp_destruction_pct`), so it isn't a drop-in
reuse.

**Add a sibling helper** (e.g. `compute_war_win_status(war, our_tag)` in
`services/helpers.py`) using `ClanWar`'s field names, and pass its result to
the template as `war_win_status`. This makes the War and CWL tickets
structurally identical while a war is in progress: both show
safe_win/cant_win/undecided, not just raw stars.

No other backend changes. A personal weekly verdict for the You band
(`_ranked_verdict`/`raid_score_verdict`-style) was considered and explicitly
declined — the You band stays numbers-only; verdicts live on the dedicated
ranked/war/raid pages.

## Structure

Information hierarchy, decided fresh from the data above, then revised
twice by the user after seeing the live build. Final structure: **Clan band
(full-width) → You + Events band (two columns, side by side)**.

```
┌────────────────────────────────────────────┐
│ CLAN — name + badge, member count           │
│ war attacks this wk · ranked battles this wk│
│ · week resets <week_start_name>             │
└────────────────────────────────────────────┘
┌────────────────────────┬─────────────────────┐
│ YOU                     │ WAR ROOM             │
│ TH · League              │ ┌─────────────────┐ │
│ Ore: shiny/glowy/starry  │ │ WAR — state, ver.│ │
│ Attacks this wk           │ └─────────────────┘ │
│ Ranked attacks left       │ ┌─────────────────┐ │
│ War: attacks/wars         │ │ CWL — state, ver.│ │
│ CWL: attacks/wars         │ └─────────────────┘ │
│ Projected ore this cycle  │ ┌─────────────────┐ │
│                            │ │ RAID — medals    │ │
│                            │ └─────────────────┘ │
└────────────────────────┴─────────────────────┘
```

Original brainstorm order was You → Events → Clan, each full-width
(personal status first). First revision: Clan → You → Events, still all
full-width bands. Second revision, after seeing that live: merge You and
Events into one band, side by side — personal stats on the left (wider,
1.3fr), event tickets stacked vertically on the right (narrower, 1fr) —
closer to the original page's hero layout, using the full band width
instead of three stacked tickets under a mostly-empty You band.

**Solo fallback**: when only one side has content (You hidden because no
linked player, or Events empty because the clan has no war/raid/CWL history
at all), that side's column takes the full band width — and the event
tickets revert to the 3-across grid (only cramped into a single stacked
column when they're actually sharing the band with the You column).

### Clan band

- Fields: `clan_name`, `clan_badge_url`, `total_members`,
  `battle_logs_this_week`, `ranked_battles_this_week`, `week_start_name`.
- No empty state concern — `clan_name` already defaults to "Our Clan" and
  `total_members` is always a real count. Always the first band on the page.

### You band

- Fields: `player_th`, `player_league`, `player_ore` (three-way stockpile),
  `player_attacks_this_week`, `player_ranked_left`, `player_war_stats`,
  `player_cwl_stats`, projected ore gain (derived client-side from
  `player_war_stats_json`/`player_cwl_stats_json`/`player_gain_settings_json`
  via the existing Ore Gain calculator — reuse that JS, don't reimplement).
- **Empty state**: if there's no logged-in user, or the logged-in user has no
  `linked_player`, **hide the band entirely**. No zeroed-out placeholder, no
  login prompt card.

### Events band

Three tickets, fixed order **War, Raid, CWL** — each independently either
"active" (live, actionable) or "last" (most recent completed, read-only) per
the route's existing active/last fallback logic:

- **War**: `active_war` or `last_war`. While active, show `war_win_status`
  (new field, see Backend change above) alongside `clan_stars`/`opponent_stars`.
  When showing `last_war`, show the final stars/destruction and a plain
  Win/Loss/Tie derived from comparing `clan_stars` vs `opponent_stars` — no
  new backend field needed for that comparison, it's a straight `>`/`<`/`==`.
- **Raid**: `active_raid` (+ `active_raid_est_medals`, labeled as an
  *estimate* — it's a projection, not final) or `last_raid` (show
  `offensive_reward`/`defensive_reward` as *final*, not estimated — that data
  already exists on the completed record, no projection needed).
- **CWL**: `active_cwl_war` (+ `cwl_win_status`) or `last_cwl_war` (state
  reached, final stars, Win/Loss/Tie by the same direct comparison as War).
- **Per-ticket empty state**: if a category has neither an active nor a last
  record (e.g. the clan has never done a raid), omit that ticket — the row
  renders with fewer columns rather than showing an empty placeholder card.

### Command Deck

A fourth section, added after the live build was reviewed (not part of the
original data-driven brainstorm — flagged here after the fact rather than
before, which was the mistake: it was silently dropped during the initial
build on the reasoning that the top nav already reaches every linked page,
without asking first). The user asked for it back. Static tile grid —
Ranked, Battle History, Raid Weekend, Clan War, War League, Clan Overview,
and (super-admin only) Admin Hub with the `newbie_check_count` alert badge.
Not driven by route data (no new backend field), sits after the Events band
and before the footer.

## Responsive strategy

- **You band, Clan band**: low field count (5-6 values each), not dense —
  standard fluid reflow (`repeat(auto-fit, minmax(...))`-style) is sufficient,
  no alternate mobile component needed.
- **Events band**: the dense case — three multi-field tickets. Decided with
  the user: **mobile stacks the same ticket component full-width in a single
  column**, not a different component (no tabs, no collapse/expand, no
  carousel). Same fields at every viewport, just narrower.
- Viewports to validate before sign-off: 390×844, 768×1024, 1200×800.

## Out of scope for this spec

- Visual identity (palette, type, component styling, signature element) —
  `impeccable craft`, next step.
- Personal weekly verdict for the You band — explicitly declined this cycle.
- Any page other than `/` (index) — separate redesign cycles.

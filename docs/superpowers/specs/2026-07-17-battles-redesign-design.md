# Battle History (/battles) redesign — design spec

## Scope

Structure and behavior only, for `coc_stats/templates/battles/battle_history.html`,
rendered by `battle_history_page()` (`coc_stats/features/battles/routes.py:16-137`).
Visual treatment (palette, type, component styling) is out of scope — hands off
to `impeccable craft` after this spec is signed off. `/battles/stats` (the
separate Long Term Stats page) is untouched — its own future cycle.

## Data source

Everything below comes from `battle_history_page()`'s `render_template` call
(`routes.py:124-137`). No template variable is treated as a given — each is
named here because the route actually produces it.

- **Filters**: `available_weeks` (list of `{start, label}`, includes an `'all'`
  entry), `selected_week_start`, `current_week_start`, `selected_type`,
  `week_label`
- **Clan-wide ledger**: `total_attacks`, `total_gold`, `total_elixir`, `total_dark`
  (all scoped to the selected week/type filter)
- **Roster**: `player_data` — every player who attacked in the filtered window,
  each with `player_name`, `player_tag`, `in_clan`, `att_count`, `total_gold`,
  `total_elixir`, `total_dark`, and a nested `attack_logs` list (`time`,
  `time_sort`, `opponent_tag`, `type`, `stars` 0–3, `percentage`, `gold`,
  `elixir`, `dark` — one entry per attack)
- **`top_by_attacks`**: top 10 of `player_data` by `att_count`. Currently
  computed and passed to the template but **never referenced** — dead
  computation. This cycle puts it to use (see Structure).

## Backend change

No new fields. `top_by_attacks` already carries everything needed (it's a
subset of `player_data`, so `attack_logs` is present on every entry) — it's
being *used*, not extended. The only route-level change is trimming the slice
from `[:10]` to `[:4]` in `routes.py:122` to match the Featured Tile
component's "small, bounded set" rule (DESIGN.md: 4 tiles, not a flat grid of
10) — a one-line adjustment to an already-dead computation, not a new field.

3★ rate (the quick-glance quality signal, see below) is computed **client-side**
from `attack_logs[].stars`, already present on every player — no schema or
route change. The JS already has this exact computation (`computeLogMetrics`,
`battle_history.html:373-386`); this cycle just also exposes it before the
tap-to-expand, not only inside it.

## Structure

Decided fresh from the data above, then revised once after the user flagged a
real usability gap in the current build: the existing per-player card (mobile)
and row (desktop) show attack count + loot totals, but **nothing about attack
quality** — a leader has to tap-expand every single player to see their star
rate, making "who's carrying, who's coasting" (PRODUCT.md's stated purpose)
require N taps instead of one glance at the list.

**Final order**: Ledger → Top Attackers → Recent Attacks → Roster.

```
┌─────────────────────────────────────────────┐
│ Filters: week ▾ · type ▾ · show left · search│
├─────────────────────────────────────────────┤
│ LEDGER — total attacks · gold · elixir · dark │
├─────────────────────────────────────────────┤
│ TOP ATTACKERS (featured, top 4 by att_count)  │
│ [name · attacks · 3★ rate] × 4                │
├─────────────────────────────────────────────┤
│ RECENT ATTACKS — collapsible chronological    │
│ feed across all players, kept as-is (useful   │
│ for checking current activity — not dropped)  │
├─────────────────────────────────────────────┤
│ ROSTER — sorted A–Z by default (attacks/gold/ │
│ elixir/dark/3★ rate still sortable by column) │
│ every row/card shows 3★ rate WITHOUT tapping  │
│ tap → heatmap + star distribution + full log  │
└─────────────────────────────────────────────┘
```

Recent Attacks moves ahead of the Roster — it answers "what just happened"
(a live-activity check), which reads naturally right after "who's leading"
(Top Attackers) and before the full reference list (Roster).

### Why Top Attackers gets its own tier instead of just sorting the roster
`player_data` already defaults-sorts by `att_count` descending, so a naive
"top 10 tile row" would just be a bigger-styled duplicate of the table's own
first 10 rows. To make the featured tier add real information instead of
decoration, **the roster below changes its default sort to alphabetical**
(player name, A–Z) — attack-count sort remains one click away via the existing
sortable column header. Top Attackers becomes the actual "who's leading right
now" answer; the roster becomes the full reference list, not a duplicate
ranking.

### Quick-glance quality signal (the fix for the flagged gap)
Every Top Attackers tile **and** every roster row/card shows **3★ rate**
(chosen over avg-destruction% or both, for glanceability) alongside the
existing attack count / gold / elixir / dark — computed client-side, always
visible, never behind a tap. Tap-to-expand is reserved for genuine drill-down
only: the attack-timing heatmap, full star distribution breakdown, and the
timestamped attack log — content that's inherently too dense to show
per-row/card regardless of the fix above.

### What stays as-is
- Filters (week/type/show-left/search) — existing pattern, not reopened.
- Recent Attacks collapsible panel — explicitly kept per user feedback
  ("good for checking current activity"), moved ahead of the Roster (see
  above), same collapsed-by-default behavior otherwise.
- Tap-to-expand mechanism itself (inline expansion, not a separate page/modal)
  — confirmed still right; the fix is *what's visible before* the tap, not
  the drill-down mechanism.

## Mobile (re-examined, not just reflow)

The existing table→card-list split (desktop table, mobile card list, already
two genuinely different components) is confirmed still correct for dense
multi-column roster data — kept, not reinvented.

- **Top Attackers on mobile**: 4 tiles in a 2×2 grid (matches the Command
  Deck tile pattern's existing mobile breakpoint behavior), not a horizontal
  scroll strip — all 4 stay visible without a swipe gesture.
- **Roster cards on mobile**: gain the 3★ rate signal directly in the
  collapsed card (alongside the existing gold/elixir/dark row), addressing
  the flagged gap. Tap-to-expand content (heatmap, distribution, full log)
  unchanged.
- **Recent Attacks on mobile**: unchanged — already horizontally scrollable
  table inside the collapsible panel.

## Out of scope / future opportunities (not this cycle)

- A computed "carrying/coasting" activity verdict (attack rate vs. clan
  average) — discussed and explicitly deferred; needs its own
  threshold/formula decision as a separate cycle.
- `/battles/stats` (Long Term Stats) — separate page, separate cycle.
- Exact mobile breakpoint for the 2×2 Top Attackers grid — implementation-time
  check against the existing Command Deck breakpoints, not spec-locked here.

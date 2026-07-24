# Equipment Planner — Full Redesign

**Date:** 2026-07-23
**Route:** `/tools/equipment` (GET render, POST `/tools/equipment/save`)
**Status:** design approved (structure), not implemented
**Prior work:** first design cycle for this page — no earlier spec. Theme is
already established (`PRODUCT.md` / `DESIGN.md`); this page extends it, does not
re-open it.

## Context

The existing page is a full-width grid of equipment cards with a separate
ore-balance strip, a bottom "plan" list, and — worst of all — the entire income
model buried in a hidden modal ("Daily Ore Gains"). It technically computes the
right numbers but reads as three unrelated widgets stapled together, and the
income calculator (the thing that makes the forecast meaningful) is invisible
until you find a button. The owner's brief: rethink it from scratch into a tool
players *want* to reopen every few days — an insider advantage, not a form.

### The thesis — why this can be more than a generic web calculator

Every other equipment calculator on the internet makes you type everything in.
This one already knows, for the logged-in member:

- their **real gear** — every equipment, its current and max level, and which
  hero it sits on (live from the CoC API);
- their **real Star Bonus rate** — derived from their actual Town Hall and
  Legend-league tier;
- the **ore they actually earned** from their own attacks — regular wars over
  the last 30 days and their most recent CWL season, reconstructed per-attack
  from logged war data.

So the tool can state a member's *true* earning rate and a *real* finish date
for their upgrade plan with almost nothing typed in. That zero-entry, grounded-
in-your-own-play quality is the moat, and it is what the redesign is built to
foreground.

### Data the design is derived from (the route + the client engine)

`equipment_calculator()` passes to the template:

| Variable | Meaning |
|---|---|
| `player` | the linked `Player` (or `None` if the user has linked no account) |
| `equipment` | list of owned equipment dicts: `name`, `level`, `maxLevel`, `village`, `equipped_on` (hero) — deduped, sorted by village → hero order → level |
| `error` | live-API error string, or `None` |
| `saved_goals_json` | `{equipment_name: {target, priority}}` — persisted goals |
| `saved_ores_json` | `{shiny, glowy, starry}` — persisted ore balance |
| `war_stats_json` | `{shiny, glowy, starry, attacks, wars}` earned from regular wars, last 30 days |
| `cwl_stats_json` | `{shiny, glowy, starry, attacks, wars}` earned from the most recent ended CWL season |
| `gain_settings_json` | serialized income-source config (`AppUser.gain_settings`) |
| `player.current_th`, `player.league_tier` | drive the Star Bonus rate |

The **math already exists** in the template's client engine and stays exactly as
is — this redesign recombines it, it does not re-derive it:

- `calcCost(from, to, maxLevel)` → per-piece ore cost, using `COMMON_COSTS`
  (maxLevel ≤ 18) or `EPIC_COSTS` (maxLevel > 18).
- `calcDailyGain()` → sums the **enabled** income sources (each carries
  shiny/glowy/starry at a `daily|weekly|monthly` frequency, normalized to
  per-day) into a daily ore rate.
- `calcTotalPlanCost()` → sums `calcCost` across all goals.
- `calcDaysToCover(total, balance, daily)` → per ore, `max(0, (cost −
  balance)/rate)`; the plan's finish is the **max across the three ores** (the
  bottleneck ore); `0` = affordable now; `∞` = a needed ore has no income.

The four income sources: **Star Bonus** (auto from TH + Legend tier), **War**
(auto, last-30-day actuals), **CWL** (auto, last season actuals), **Trader**
(manual — bundles bought per week; `TRADER_BUNDLES = shiny 500 / glowy 50 /
starry 5`).

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Page spine | **Forecast-first** — the personalized finish-date forecast is the hero; inventory and income are its inputs | Directly serves "insider advantage" + "reason to return": the forecast visibly moves as the member earns and upgrades |
| Income model | **Inline earning-rate readout**, no modal — a compact always-visible "you earn X/day" that opens in place to edit the 4 sources | Kills the buried modal; makes the rate first-class (it drives the hero number) but subordinate to the forecast. Star/War/CWL read as auto-filled from real play; the member mostly just sets Trader |
| Return hook | **Since-last-visit pulse** — each visit shows the ore the member's wars/CWL earned since they last checked, framed as plan progress, with a one-tap "add to balance" | Strongest "every few days" reward. Honest because the earned figure is real (auto), unlike the manually-typed balance |
| Layout | **Sticky forecast rail** (Arrangement C) — inventory scrolls in the main column; pulse + forecast + rate + balance are pinned in a rail always in view | Makes forecast-first literal and creates the live cause→effect loop: nudge a target, watch the finish date move. Turns a form into an instrument |
| Mobile inventory | **Dense divided rows**, not cards | Matches the site's standing mobile convention (roster-rows everywhere); skim the whole collection fast |

Rejected as spines but absorbed: *economy-first* (the ore economy is present and
prominent in the rail, just not the lead) and *inventory-first* (the inventory
is the main scrolling column and the primary edit surface — it simply isn't the
headline).

## Information dimensions that must survive

The old surface encoded these; the redesign must still carry every one (drop
none silently — Non-Negotiable 1):

- **Per equipment:** icon/identity, current level, max level, progress toward the
  chosen target *within* max, which hero it's on, home vs. builder village,
  per-piece upgrade cost in all three ores at the selected target, priority
  number.
- **Ore balance:** three currency values (starry only surfaces when something in
  play needs it — epic equipment).
- **Plan totals:** total cost in three ores, count of pieces, days-to-finish.
- **Income model, per source:** three ore values, a frequency, an enabled/disabled
  state; plus War/CWL attack + war counts, Star Bonus by TH/league, Trader
  bundle counts; and the aggregate daily rate, monthly rate, and days-to-plan.

## Page structure

Shared header via `_page_header.html` (reuse existing slots — no new slot
needed):

- `page_header_title` — working title "Equipment Planner" (final name is a
  copy/voice question for impeccable).
- `page_header_desc` — one orientation line.
- `page_header_meta` — identity readout figures: Town Hall, league tier,
  equipment-owned count. (The *live* numbers — rate, finish date — live in the
  forecast hero, not here, because they change as you edit.)
- `page_header_right` — the linked-player identity chip.
- `page_controls` (optional) — an inventory filter (by hero and/or
  home/builder village). Include only if it earns its place; the grouped
  inventory may make it redundant.

Two structural regions below the header (the Arrangement-C split):

### Rail (pinned; the forecast-first hero) — zones A–D

**Zone A — Since-last-visit pulse.**
Greets the returning member: "Since {relative date}: your {N} wars + {M} CWL
rounds earned **+X shiny, +Y glowy** (+Z starry if any)." A derived secondary
line frames it as progress: "~{d} days of plan progress at your current rate"
or "{pct}% of your remaining plan." A **one-tap "Add to balance"** action
increments the saved ore balance by the earned amount (closing the manual-
balance staleness gap). First-ever visit shows a baseline/welcome state instead
of a delta. Never shows an empty/zero delta as the headline (see Behavior).

**Zone B — Forecast (the hero).**
The upgrade plan in **priority order**, each piece stamped with its own ETA:
"affordable now", or "~{d} days · by {date}". The ETA is **cumulative** — a
piece's date accounts for every higher-priority piece being bought first (see
Behavior). Ends with the whole-plan finish ("Plan done: ~{d} days, by {date}")
and names the **bottleneck ore** ("glowy is gating your plan"). Empty when no
targets are set: a prompt to set targets in the inventory below.

**Zone C — Earning-rate readout.**
Collapsed: the aggregate rate — "{shiny}/d · {glowy}/d · ({starry}/d if > 0)",
with a monthly figure available. Expands in place (no modal) to the four source
controls: Star Bonus (auto, read-only value derived from TH+tier, with its
inputs shown), War (auto, shows count e.g. "4 wars / 30d", value overridable),
CWL (auto, overridable), Trader (manual — bundle-count buttons per ore). Each
source has an enable/disable toggle and a per-source frequency. Editing any of
these recomputes the rate → recomputes the forecast → autosaves.

**Zone D — Ore balance.**
The three ore inputs (starry hidden until something needs it). Editing
recomputes affordability and the forecast. This is also the target of Zone A's
"Add to balance".

### Main column — Zone E

**Zone E — Inventory.**
Every owned equipment, **grouped** (village → hero in canonical order:
Barbarian King, Archer Queen, Grand Warden, Royal Champion, Minion Prince), each
piece a row carrying all its dimensions (icon, name, current/max, target
control, priority, live per-piece cost). Editing a row's **target** or
**priority** updates the rail's forecast **live** — the signature interaction.
Maxed pieces read as done. A reset control clears all targets/priorities.

## Behavior

**The live loop (the point of Arrangement C).** Every edit to a target,
priority, ore balance, or income source recomputes, in order: per-piece cost →
daily rate → cumulative forecast ETAs → whole-plan finish + bottleneck → and
re-renders the rail, while the edited inventory row stays in place. Because the
rail is pinned, the member sees cause and effect at once.

**Cumulative per-piece ETA (forecast intelligence — built from existing math).**
Order goals by priority (nulls last, then name). Walk the list accumulating cost
per ore. For piece *i*, `cumulative_i` = summed cost of pieces 1..i;
`ETA_i = calcDaysToCover(cumulative_i, balance, dailyRate)`. "affordable now"
when `cumulative_i ≤ balance` for all ores. `by {date}` = today + ceil(ETA).
Whole-plan finish = ETA of the last piece. Bottleneck ore = the ore maximizing
`(total − balance)/rate`. If the bottleneck ore has zero income and cost >
balance, ETA is infinite → a "your rate can't cover this — enable another
source" state (preserve existing behavior).

**Since-last-visit pulse (needs the one backend field).** On GET, read the
*previous* `equip_last_seen_at`, compute ore earned from the member's wars and
CWL with `end_time >= previous_last_seen` (same machinery as `_compute_war_stats`
/ `_compute_cwl_stats`, cutoff swapped), then render Zone A from that delta.
**Advance rule:** only move `equip_last_seen_at` forward to now when the visit is
"fresh" — the elapsed gap since the stored value is at least ~8 hours *or* it
falls on a later calendar day. Otherwise leave it, so same-session refreshes show
the *same* pulse instead of collapsing to zero. First visit (`NULL`) → baseline
state, then stamp now. "Add to balance" counts as acknowledging and advances the
stamp. (The 8h/day threshold is a tunable — flagged below.)

**Persistence.** POST `/tools/equipment/save` keeps its current contract
unchanged: `{shiny, glowy, starry}` balance, `gainSettings` (source config), and
`goals` (`{name: {target, priority} | null}`). Autosave on edit stays. "Add to
balance" writes the incremented balance through the same endpoint. Star Bonus,
War, and CWL remain **synced from the database on each load**, never restored
from client storage.

## Responsive arrangement

- **Desktop (≥ ~1000px):** two columns — inventory main (scrolls), rail pinned
  (sticky) with zones A→B→C→D. This is Arrangement C.
- **Tablet (768):** the rail un-pins and becomes a top band (pulse + forecast +
  collapsed rate + balance), inventory below. If the band is tall, the forecast
  summary line may stay sticky-condensed; full source editing is inline.
- **Mobile (390):** single column, rail contents stacked on top in order
  (pulse → forecast → rate readout collapsed → balance), then the inventory as
  **dense divided rows** (icon, name+level, target control, priority, cost per
  row) grouped by hero. No card-per-piece. Confirm the target control is
  touch-workable at this width (see open questions).

## Empty / idle / error states

- **No linked player** (`player is None`): not a dead calculator — a clear
  "link your account to see your gear and forecast" state pointing at
  `/profile`.
- **Live-API error** (`error` set): show the error with a retry affordance;
  the rest of the tool has no inventory to act on, so keep it honest rather than
  rendering an empty grid.
- **No goals yet:** inventory renders normally; the forecast hero shows a
  "set target levels to build your forecast" prompt.
- **First visit / no history:** Zone A baseline state, no fabricated delta.

## Backend changes (approved during brainstorm)

1. **New column** `AppUser.equip_last_seen_at` (`DateTime`, nullable) + an
   Alembic migration. Sole purpose: the since-last-visit window.
2. **Route additions** in `features/tools/routes.py`:
   - a helper computing ore earned since a cutoff (war + CWL), reusing the
     existing per-attack ore logic with the cutoff swapped from a fixed 30/31
     days to `previous_last_seen`;
   - read-then-advance of `equip_last_seen_at` under the freshness rule above;
   - pass the pulse delta + previous-seen timestamp to the template.

   No change to the save contract, the cost tables, the rate math, the star/war/
   cwl derivations, or the equipment fetch/sort.

## Out of scope / explicitly preserved

- All upgrade-cost, rate, and days-to-cover math (client engine) — unchanged.
- The Star Bonus league table, Trader bundle sizes, war/CWL ore reconstruction —
  unchanged.
- The save endpoint and its payload shape — unchanged.
- No new page routes; this is the same two endpoints.

## Open questions for impeccable (visual + a few behavior tunables)

Everything about **look** is deliberately unspecified here and belongs to
impeccable:

- Palette / mode-hue for this page within the established night-ops system
  (every mode has its own accent — Ranked = Recon Blue, War = amber, etc.; this
  page needs its own), type treatment, spacing system, radii, the **signature
  element**, and motion.
- The **finish-date forecast** is the emotional core — what is its signature
  moment? (e.g. how "affordable now" vs. a future date reads; how the whole-plan
  finish is dramatized.)
- How the **live loop** is expressed as motion — the rail updating when a target
  changes is the signature interaction; how much motion, and reduced-motion
  behavior, is impeccable's call (an explicit `/impeccable animate` pass).
- Zone A **"add to balance"** micro-interaction and how the pulse is
  dramatized on return.
- The **name/voice** of the page and its copy (working title "Equipment
  Planner" is a placeholder).
- The dense inventory **row** design — how to fit icon, levels, progress, target
  control, priority, and three-ore cost without crowding; and the **mobile
  target control** (slider vs. stepper vs. tap-to-set) so it's touch-workable.
- How **auto** vs. **manual** income sources are visually distinguished so
  members trust the pre-filled ones.

Behavior tunable (not visual, but genuinely open): the pulse **freshness
threshold** (~8h / calendar-day) — pick the value that makes the "since last
visit" reward feel right without resetting on refresh.

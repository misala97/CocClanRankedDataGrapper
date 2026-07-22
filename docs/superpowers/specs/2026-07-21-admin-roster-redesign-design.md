# Admin Roster Rework — Structure Spec

**Date:** 2026-07-21
**Page(s):** `/admin/roster` (reworked) + new `/admin/insights` (extracted from it)
**Type:** rework / rethink (not a reskin). No JSON-endpoint logic changes; the change is
information architecture, per-tool shape, and one route split.
**Theme:** established "Night Ops Scope" system (PRODUCT.md / DESIGN.md), extended per the
Overview/Monitor precedent — **not re-litigated**. This spec is a *structure contract*:
sections, hierarchy, data mapping, behavior, responsive arrangement. Visual vocabulary
(colour / type / spacing / signature / motion) belongs to impeccable — see §9.

Supersedes §5.3 of `2026-07-21-admin-redesign-design.md` (which stacked three co-equal tools
on `/admin/roster`).

---

## 1. Problem

`/admin/roster` today is a shell hosting **three unrelated tools** as equal collapsible
accordions — War Roster Recommendation, CWL Bonus, Ranked×Raid Skill Correlation. Two
problems:

1. **Mixed job types.** War Roster and CWL Bonus are recurring *allocation decisions* (fill a
   scarce set — war slots / bonus medals — from the active roster, with an explainable pick).
   Skill Correlation is a standing *clan-wide analysis* (one Pearson r; does ladder skill
   predict raid performance) — it produces no roster and no action. It rides along only because
   there was nowhere else to put it.
2. **No hierarchy inside each tool.** Each tool dumps its full data table with equal weight to
   the actual decision. War Roster shows two co-equal side-by-side tables (roster + bench); CWL
   Bonus leads with a 5-season × player matrix, burying the one thing the admin is there to do
   ("who gets *this month's* bonus"). The answer is not surfaced; the raw data is.

## 2. Target shape

- **`/admin/roster`** becomes a **two-decision console**: War Roster + CWL Bonus only, each
  reshaped **decision-first** (lead with the recommendation/verdict, detail on demand).
- **Skill Correlation moves out** to a new **`/admin/insights`** page — framed as the clan
  **Insights** (analytics) home, with Skill Correlation as its first resident so future
  clan-analytics have a home rather than a thin one-tool page.
- Arrangement: **two stacked consoles** (chosen over in-page tabs / master-detail rail) — both
  decisions visible at a glance, matching the Overview-bands / Monitor-console language, short
  at rest via detail-on-demand.

## 3. Route / shell changes (approved 2026-07-21)

All are plumbing for the split; **no JSON endpoint gains or changes logic.**

1. **New route `/admin/insights`** (`@require_super_admin`) — thin shell, no context needed
   (data via the existing `/admin/skill-correlation` AJAX GET). Renders new
   `templates/admin/admin_insights.html`.
2. **`admin_roster` route** — unchanged (still passes `current_month` for the CWL default).
   The Skill Correlation markup/JS is removed from `admin_roster.html` and relocated verbatim
   (behavior-wise) into `admin_insights.html`.
3. **`_admin_tabs.html`** gains a **6th tab: Insights → `/admin/insights`** (active via
   `startswith`, consistent with the others). No count badge.
4. **Overview (`/admin`) copy fix:** the "Go To" Roster card sub-line changes from
   "War · CWL · Skill tools" to drop Skill (e.g. "war lineup · cwl bonus"). Adding a 5th
   "Insights" jump card to Overview's Go-To band is **recommended for discoverability** but
   optional — see §9.

**Unchanged AJAX endpoints** (called from the reworked pages, no edits):
`/admin/war-roster`, `/admin/cwl-bonus`, `/admin/cwl-bonus/suggest`, `/admin/cwl-bonus/apply`,
`/admin/cwl-bonus/toggle`, `/admin/skill-correlation`.

## 4. Data brief (what each endpoint actually produces)

Everything the reshaped pages render already exists in these responses — **no new fields.**

- **`/admin/war-roster` (POST)** → `roster[]` (`name, th, war_score`, `verdict` (skill),
  `war_pref, war_count, league, ranked_league, role/reason`), `bench[]` (same fields),
  `war_size, fill_ups, main_picks, pref_in_count, score_count, eligible_count, auto`.
- **`/admin/cwl-bonus` (GET)** → `months[]` (season keys, up to 5, incl. double-CWL months),
  `current_month`, `members[]` (`name, tag, ranked_league, league, cwl_pos, by_month{season →
  has_bonus, in_cwl, stars, attacks, max_attacks, total_wars}}`).
- **`/admin/cwl-bonus/suggest` (POST)** → `wins, guaranteed, total_bonuses, already_given,
  available, league, war_size, suggested_tags[], suggested_details[] (name, stars, attacks,
  max_attacks, total_wars, reason), participants[] (…, last_bonus, months_ago, destruction,
  has_bonus)`.
- **`/admin/skill-correlation` (GET)** → `players[] (name, th, ranked_score, ranked_weeks,
  ranked_games, raid_score, raid_weekends, raid_attacks)`, `pearson_r`, `n_correlated`.

## 5. Per-page structure

### 5.1 `/admin/roster` — two stacked decision consoles

Header (`_page_header.html` existing slots): title + accent span, one orientation line. No new
header slot needed. `_admin_tabs.html` immediately below. Then the two consoles, stacked
full-width, **War Roster first** (per-war, most frequent), **CWL Bonus second** (monthly).

Each console is **verdict-led + detail-on-demand**: a control/summary head that states the
current recommendation in words + numbers, the primary result surfaced immediately, and bulk
detail behind an in-place expand.

**Console 1 — War Roster**
- *Controls:* Auto / Manual mode toggle; Manual reveals war-size + fill-ups inputs; Generate.
  (unchanged behavior)
- *Verdict line* (on result): the recommendation in one read — war size, main-picks split,
  eligible pool, benched count. Data: `war_size, main_picks, fill_ups, eligible_count,
  bench.length`.
- *Primary result — the LINEUP:* the recommended roster as the single lead table/list:
  position, player (+league), TH, War Activity (`war_score`), Skill (`verdict`), and the
  per-pick **Why** (`role`/`reason`: Sparse data / War pref: In / Score N / Fill-up). This is
  the answer; it leads.
- *Secondary — "Not selected (N)":* the bench, collapsed behind an expand (exceptions, not a
  co-equal table). Same identity fields + verdict; sorted as the endpoint returns (skill desc).
- *Idle state* (no Generate yet): a clear prompt to generate, not a dead panel. It may name the
  eligible-pool size if cheap, otherwise a plain call-to-action.

**Console 2 — CWL Bonus**
- *This-month decision leads.* On load, fetch **both** the ledger (`/admin/cwl-bonus`) **and**
  the suggestion (`/admin/cwl-bonus/suggest` for `current_month`) so the decision shows without
  an extra click. (Client behavior only — both endpoints exist.)
- *Verdict line:* season + format + slot math — e.g. league · `war_size`v`war_size` ·
  `total_bonuses` slots · `already_given` given · `available` remaining. Data from the suggest
  response.
- *Primary result — THIS MONTH:* the suggested recipients (`suggested_details`: player, stars,
  attacks `x/max`, the fairness **Why** = `reason`), with **Apply** (existing
  `/admin/cwl-bonus/apply`) and **Copy Discord report** (existing client builder). This is the
  monthly job, surfaced first.
- *Secondary — "Full ledger":* the 5-season × player matrix (stars / attacks / bonus per month,
  current month emphasized; per-player double-click toggle; search) collapsed behind an expand.
  It is history/context — who's owed — not the lead.
- *Empty state — no active CWL season* (`suggest` → `ok:false`): a clean "no active CWL to
  assign" note, and still show the **last real season's ledger** if any exists (never a dead
  placeholder). The prior tool only alerted on this error — the rework must state it calmly.

### 5.2 `/admin/insights` — clan analytics home

Header + tabs as every admin page. One section today:
- **Ranked × Raid Skill Correlation** — Run Analysis (button-triggered; heavy compute) →
  summary figures (Pearson r + label, data points, has-ranked / has-raid counts), scatter +
  regression line, per-player breakdown table (TH, ranked score, raid score, Δ, weeks/weekends),
  and the four quadrant buckets (Elite / Raid Specialist / Ranked Specialist / Needs Growth).
  All behavior/data inherited from the existing tool — this is a **re-home, not a redesign of
  the tool's internals**, beyond fitting the established page chrome and the mobile rule below.
- *Empty / not-enough-data:* keep the existing "Not enough data" handling; if a prior run's
  data exists, show it rather than nothing.

## 6. Responsive strategy

- **War lineup & bench, CWL this-month suggestion** — dense per-entity tables → the established
  **divided roster-row pattern** on phone width (identity line on top, inline stats/verdict
  wrapping below). **Never** per-entity cards (DESIGN.md standing ban).
- **CWL full ledger matrix** — a true 2-D matrix (players × seasons), not a per-entity table;
  it stays a **horizontal-scroll container** on mobile (its current behavior). Divided rows
  don't apply to a matrix; the *decision* above it is what carries the rows.
- **Insights scatter** — the 2-D scatter is width-hungry; on phone it is replaced by a
  **compact ranked list** (e.g. by combined score), not a shrunken plot. The per-player table →
  divided rows; quadrant buckets stack.
- **Consoles / sections** reflow single-column; control clusters wrap.
- Validation viewports: **390×844**, **768×1024**, **1200×800**.

## 7. Reuse (don't reinvent)

- **Page header** — existing `_page_header.html` slots (title + accent, desc; controls slot
  available if a console control belongs in the header toolbar — impeccable's call). No new slot.
- **`_admin_tabs.html`** — extend to 6 tabs; do not fork.
- **Divided roster-row** mobile table pattern — established; reuse for the lineup / bench /
  suggestion / per-player tables.
- **Verdict / status / judgment badge** vocabulary — established; reuse for the pick "Why"
  chips, war-pref states, correlation quadrant labels.
- **Two-tier hierarchy** (featured + compact) and **verdict-led, exceptions-first** console
  language — established by Overview/Monitor; this page is the next expression of it.
- **Scope-console command-deck aesthetic** from `admin_overview.html` — extend, don't restyle.

## 8. Build sequence (mini-cycles)

1. **`/admin/roster` rework** — reshape both consoles decision-first (arrangement A); move the
   Skill Correlation block out of `admin_roster.html`. This is the primary cycle.
2. **`/admin/insights`** — new route + template; drop the relocated Skill Correlation tool into
   the established page chrome; apply the mobile scatter→list rule.
3. **Shell ripples** — `_admin_tabs.html` 6th tab; Overview Roster-card copy (+ optional
   Insights jump card).

Both pages hand off to `/impeccable` for visual execution (they share the theme — extension
passes, not a fresh direction); motion via a final `/impeccable animate` pass.

## 9. Open questions for impeccable

- **Console head treatment:** how each console's verdict line reads as a command-deck summary —
  weight of the numbers vs. words, how the War "Why" chips and the CWL fairness reasons render,
  how the slot-math (`4 · 3 given · 1 remaining`) is expressed as signal.
- **Detail-on-demand affordance:** how "Not selected (N)" and "Full ledger" expands present
  (inline disclosure vs. other) while obeying the a11y disclosure pattern (native, touch/keyboard
  reachable — not `title`-only).
- **Two consoles' visual parity:** War (transient generate) and CWL (standing ledger) are
  different temporally — how much they should look like siblings vs. distinct.
- **CWL ledger matrix** within the expand: current-month emphasis, the double-CWL-month columns,
  the flawless (✨) marker, and the bonus toggle affordance — how these read in the theme.
- **Insights page identity:** how a single-tool analytics page reads as a "home" that can grow;
  scatter styling (Chart-free inline SVG — align to design tokens, resolve to computed `rgb()`),
  quadrant buckets, and the mobile ranked-list form of the scatter.
- **Overview Go-To:** whether to add a 5th "Insights" jump card, and if so its live sub-line.
- **Motion:** verdict/count entrance, expand transitions, Apply/Generate button feedback — defer
  to `/impeccable animate`.

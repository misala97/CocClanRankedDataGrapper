# Tip Tracker Redesign — Design Spec

## Context

Personal app: bike-courier tip/shift log ("Trinkgeld Tracker", German UI).
Route: `personal_apps/features/tips/routes.py`. Template:
`personal_apps/templates/tips/tips.html`.

Full rethink requested by the user — visual design, input experience, data
presentation, and usability were all called out as bad. The underlying
functions and data are considered good; behavior is preserved, structure
and look are rebuilt from scratch.

Scope is isolated to this one page: it does not share theme with
coc_stats or with any other personal app (gym, pubquiz, quizbank). This
is a first-time `impeccable init` for this app, scoped to tips only.

## Primary use context (drives hierarchy)

- Primary: mobile, immediately after finishing a shift — logging must be
  fast and must be the first thing on the page.
- Secondary (but explicitly valued by the user): stats review, browsed
  more relaxedly, often on desktop.
- All three rate metrics (€/hour, €/delivery, €/trip) carry **equal**
  weight. No single metric is promoted as a headline number — wherever
  one appears, the other two appear alongside it.

## Data inventory (from routes.py / models.py — source of truth)

`DeliveryShift` fields: `shift_date`, `shift_start`, `shift_end`
(optional), `hours_worked` (fixed choice 4/6/8), `tips_cash`,
`tips_online`, `deliveries` (count), `trips` (count), `bike_size`
(small/big), `weather` (7 values), `notes`.

Per-shift derived values (computed in the route): `total` (cash +
online), `per_hour`, `per_delivery`, `per_trip`.

Route provides to the template:
- `rows` — full shift list with derived fields
- `periods` — `{week, month, year, all}` aggregates
- `best_rate` / `worst_rate`, `best_delivery_rate` / `worst_delivery_rate`,
  `best_trip_rate` / `worst_trip_rate` — six top/bottom-5 lists
- `breakdown_weekday` (7 groups, Mon–Sun order)
- `breakdown_time` (4 buckets: morning/afternoon/evening/night, fixed order)
- `breakdown_weather` (up to 7 groups, sorted by avg €/h desc)
- `breakdown_bike` (up to 2 groups, sorted by avg €/h desc)
- `chart_labels` / `chart_totals` / `chart_rates` — date-ordered time series
- `bike_choices` / `weather_choices` — form option lists

No backend changes for this redesign — all fields already cover it
(confirmed with the user; no new field requested).

## Page sections (top to bottom), function + data mapping

### 1. Log Shift (always first, both breakpoints)

Fast entry point for a just-finished shift.

Fields: `shift_date` (required), `shift_start`, `shift_end` (optional),
`hours_worked` (select: 4/6/8, required), `tips_cash`, `tips_online`,
`deliveries`, `trips`, `bike_size` (optional, incl. "—"), `weather`
(optional, defaults "clear"), `notes` (optional).

Submits to `tips.tips_add` (POST). Behavior unchanged from current
(redirect back to dashboard on success or validation failure).

### 2. Snapshot (period totals)

At-a-glance performance for a selected period.

Control: period switcher — Week / Month / Year / All, one active at a
time. Replaces today's four parallel cards.

Content for the selected period: avg €/h, avg €/delivery, avg €/trip
(equal weight, all three always shown together), plus `shift_count`,
`total_hours`, `total_deliveries`, `total_trips`, `total_tips` (with
cash/online split).

Data: `periods[selected_key]`. Default selected period: Week.

### 3. Trend

Performance over time.

Content: €/h and total € per shift, plotted across all logged shifts,
chronological, shown as a chart (not a table) so trajectory/magnitude
over time stays visible at a glance — matches how the old page encoded
this.

Data: `chart_labels`, `chart_totals`, `chart_rates`.

Empty state: section is omitted entirely if `chart_labels` is empty (no
shifts logged yet) — matches current behavior.

### 4. Patterns (breakdowns) — four blocks side by side, not tabbed

Compare performance across independent dimensions at once, so combined
patterns (e.g. "rain + evening") are visible in one glance rather than
hidden behind a switcher.

Four blocks, each showing avg €/h + avg €/delivery + shift count per
group, in the route's existing order (weekday: Mon–Sun; time:
morning→night; weather/bike: sorted by avg €/h desc). Each block must
support at-a-glance **magnitude** comparison across its groups, not just
a list of numbers — the old page encoded this as horizontal bar length
per group; the specific visual encoding is impeccable's choice, but
dropping relative-magnitude cues entirely would lose a dimension the old
page had.

a. By Weekday — `breakdown_weekday`
b. By Time of Day — `breakdown_time` (empty-state message if
   `breakdown_time` is empty, i.e. no shift has a recorded start time)
c. By Weather — `breakdown_weather`
d. By Bike — `breakdown_bike` (empty-state message if `breakdown_bike`
   is empty)

Entire Patterns section omitted if `rows` is empty.

### 5. Standout Shifts (best/worst)

Surface which specific shifts over/under-performed, per metric.

Control: metric switcher — €/hour / €/delivery / €/trip, one active at a
time. Replaces today's six parallel lists.

Content for the selected metric: Best 5 and Worst 5 shown side by side
(paired), each row = date + rate value.

Data: `{best_rate, worst_rate}` / `{best_delivery_rate,
worst_delivery_rate}` / `{best_trip_rate, worst_trip_rate}` depending on
the selected metric. Default selected metric: €/hour.

This switcher doesn't conflict with the equal-weight rule above: that
rule governs metric *value* displays (Snapshot, History rows), where all
three must appear together. Here the three metrics are inherently
separate rankings (a shift that's top-5 by €/h isn't necessarily top-5
by €/delivery) — showing one ranking at a time is a ranking view, not a
value display, so switching doesn't privilege any metric.

Omitted if `rows` is empty.

### 6. History

Browse, edit, delete any logged shift.

Content: full shift list (`rows`), each row collapsed by default showing
date + hours + deliveries + trips + bike + weather + all three rates +
total; click/tap to expand an inline edit form (same fields as Log
Shift, pre-filled) with Save (`tips.tips_update`) and Delete with
confirm (`tips.tips_delete`).

Behavior unchanged from current (expand-in-place, confirm-on-delete).

Empty state: "no shifts logged yet" message if `rows` is empty.

## Responsive arrangement

- **Desktop (≥ tablet):** Log Shift as a compact top panel — fields
  grouped logically, not one long field row. Snapshot and Trend may sit
  side by side or stacked (impeccable's call; no data reason to mandate
  either). Patterns as a 4-across (or 2×2) grid. Standout Shifts shows
  best+worst side by side for the selected metric. History as a
  scannable list.
- **Mobile (390px class):** Log Shift stays first, full width. Snapshot
  and Standout Shifts keep the same tab switchers as desktop — tabs are
  not a desktop-only affordance, they behave identically at both sizes.
  Patterns' four blocks stack to a single column. History rows stay
  list-style (dense divided rows, per this project's established mobile
  convention), not spacious per-item cards — tap to expand the edit form
  same as desktop.
- No content is dropped, or shown differently in kind, between
  breakpoints — only reflow/stacking, plus the already-tabbed sections,
  which behave identically at both sizes.

## Empty / idle states

- No shifts logged at all: Log Shift form still shown (it's the first
  entry point); Snapshot shows zeroed/dash values; Trend, Patterns,
  Standout Shifts, and History all show their empty-state messaging (or
  are omitted per the per-section rules above) rather than blank space.
- Partial data (e.g. no shift has a recorded start time →
  `breakdown_time` empty; no shift has `bike_size` set →
  `breakdown_bike` empty): that specific Patterns block shows an
  empty-state message while the others render normally — matches
  current per-block empty handling.

## Open questions for impeccable

- Visual identity for this page: palette, type pairing, spacing system,
  component styling — fully open. Not inherited from coc_stats, gym, or
  any other personal app. First-time init for this app.
- Signature element / overall mood — open.
- Exact tab-control visual treatment (pill tabs, underline tabs,
  segmented control, etc.) — open; only the function (single-select
  switcher) is specified above.
- Chart visual treatment (Trend line chart, Patterns comparison bars) —
  open; only the data and axes are specified above.
- Whether Snapshot and Trend sit side by side or stacked on desktop —
  open.
- Motion/animation — deferred to a later `/impeccable animate` pass per
  process.

# /admin/monitor — Redesign (Structure Contract)

Date: 2026-08-04 · Branch: `dev_coc` · Supersedes §5.2 (Monitor) of
`2026-07-21-admin-redesign-design.md`, whose Monitor pass was reverted in `757d536`.

## 0. Why this retry differs

The previous attempt burned five versions and was reverted wholesale. Root cause
was not taste: the browser-pane screenshots stalled for that entire session, so
the redesign was done **blind**. This cycle established working Playwright
screenshots first, then built three complete interactive mockups on real
production data, rendered them at all three viewports, and had the user choose.

**Direction C was approved from a rendered mockup, not from prose.** The mockup
files are the visual contract:

- `scratchpad/mockups/c.html` (+ `shared.css`, `shared.js`, `data.js`)
- Renders under `scratchpad/shots_mock/c-{incident,calm}-{mobile,tablet,desktop}.png`

## 1. What the data actually says

Profiled from a live VPS export: 10.720 runs across 6 tasks in 7 days.

| task | runs | err | skip | Ø dur | max | cadence |
|---|---|---|---|---|---|---|
| `task_update_raid_weekend` | 3361 | 12 | 0 | 0,78 s | 13,3 s | 3 min |
| `task_update_clan_members` | 2021 | 7 | 0 | 0,67 s | 12,9 s | 5 min |
| `task_update_battle_logs` | 2021 | 0 | 0 | 25,5 s | 124,9 s | 5 min |
| `task_update_clan_war` | 1250 | 12 | 118 | 1,85 s | 24,4 s | 3 min |
| `task_update_cwl` | 1053 | 1 | 125 | 4,26 s | 174,8 s | 3 min |
| `task_update_ranked_weeks` | 1014 | 0 | 0 | 39,1 s | 131,4 s | 10 min |

Three findings that drive the structure:

1. **31 of the 32 errors are one upstream incident.** On 2026-07-31 between
   12:17 and 12:52 UTC the Clash API returned `503 inMaintenance` / `500
   unknownException`, failing every task that happened to be due in that
   window — `raid_weekend`, `clan_war`, `clan_members`. The old page renders
   this as three unrelated per-task error counts, from which the fact "the API
   was down for 35 minutes" is **not recoverable**. The 32nd error is unrelated
   (`cwl`, `'Key: [season] could not be found'`, 2026-08-02).
2. **Incidents are rare; the quiet state is the normal state.** One gap in
   7 days. The page must be informative when nothing is wrong, not a dead
   "all clear" panel.
3. **Runtime is bimodal.** `battle_logs` (Ø 25,5 s) and `ranked_weeks`
   (Ø 39,1 s) dominate; the other four are sub-2 s. Runtime magnitude carries
   real signal and must survive the redesign.

## 2. Defects in the current page

Beyond structure, the shipped page violates three explicit DESIGN.md rules:

- **Side-stripe borders** — task cards carry a thick coloured `border-left`.
  Named as an absolute ban.
- **Flat grid of 6 identical icon+heading+text cards** — named as the
  "identical card grids" AI-slop tell; the system requires a featured/quiet
  split above ~4 items.
- **Raw emoji as functional UI icons** — ⚔️ 📊 👥 🏰 🥇 label controls.
  Sanctioned only for celebratory moments, never for controls.

Structural defects:

- **Every task is rendered three times** — status card, timeline lane, duration
  chart. Mobile is a 4361 px scroll of the same six tasks repeated.
- **Liveness is duplicated from the shell.** `_nav_task_status()` (app.py:88)
  already shows per-task staleness on *every* page. The Monitor opened by
  restating it.
- **`skipped` is presented next to errors** though it is by design
  (`clan_war` skips outside war, `cwl` outside a season).

## 3. Jobs the page must serve

All four confirmed by the user, none droppable:

1. Investigate an incident (what broke, when, for how long, why)
2. Daily glance (are all six healthy)
3. Trigger a task manually
4. Watch runtime performance

## 4. Structure — Direction C

Three zones, top to bottom. **Liveness does not lead** (the shell answers it);
the page opens with what only it can answer.

### Zone 1 · Systemlage

The cross-cutting instrument. Answers "did one cause hit several tasks at once?"

- **Befund headline** — one sentence naming the period's dominant finding, with
  the multi-task case stated as such ("Ein Fremdsystem-Ausfall erklärt 31 der
  32 Fehlläufe"), plus the counter-statement when nothing correlated
  ("Keine übergreifende Störung").
- **Figure block** — four readouts: tasks in cadence (n/6), total runs, failed
  runs, longest silence.
- **Laufspuren** — six lanes, one per task, on **one shared time axis**.
  Per lane: run coverage marks (dimmed for `skipped`), error marks, silence
  voids. Correlated windows (a failure cluster touching >1 task) draw a single
  highlight column across all six lanes — this is the signature moment and the
  reason this direction was chosen. Axis labels below; legend below that.
- **Ursachen** — failures rolled up **by message across all tasks**, not per
  task. Each row: occurrence count, human cause label, raw message, the set of
  affected tasks, first occurrence. Single-task causes are visually
  distinguished from multi-task ones.

### Zone 2 · Tasks

One row per task, fixed order, each task appearing **exactly once**.
Columns: identity (icon + name + purpose) · health · cadence + last-run age ·
runs + skipped · errors · Ø duration + max · Run Now.

`skipped` reads as "planmäßig", never as a failure. Error count is the only
red figure; a clean task reads "sauber", not "0".

### Zone 3 · Per-task depth (on demand)

Row expands in place: error groups with wording, gap list, last summary,
runtime extremes. No modal.

## 5. Responsive

Confirmed with the user: **all content on mobile, in a form that works at
390px** — not a narrowed desktop.

- **Laufspuren survive on mobile.** Verified in the mockup: lane labels
  truncate, the shared axis drops alternate date ticks, the correlation column
  stays legible. This zone is not hidden on small screens — it is the page's
  reason to exist.
- **Task rows** drop to the established divided-row pattern (identity + health
  on line one, a wrap of Mono figures below). **Never** per-task cards
  (standing preference, DESIGN.md → Mobile Roster).
- Figure blocks reflow 4→2 columns; cause rows put the affected-task chips on
  their own full-width line.
- Verified at 390 / 768 / 1200 with no horizontal overflow and no JS errors.

## 6. Backend changes (approved)

`admin_monitor()` currently computes `error_count` but exposes only the *last*
run's `error_message`, so the 31-failure incident is invisible by construction.

1. **Grouped errors per task** — approved by the user. For each task, failures
   grouped by message with count, first and last occurrence.
2. **Correlated incidents** — derived: failure groups whose windows overlap or
   fall within 20 minutes are one incident; an incident touching more than one
   task is typed `upstream`. Silence (`gap_events`) becomes a typed incident
   too. This is the only new *derivation*; it reads no new columns.
3. **Downsampled run series replaces `by_function`.** The route currently ships
   every run to the template (~45k rows at 30 days) for client-side charting.
   The new page needs a bounded series for the lane strip, so `by_function` is
   replaced rather than added to — a payload reduction, and no other template
   consumes it.

No schema change, no migration. `POST /admin/trigger-task` unchanged.

Logic lands in a **pure module** `features/admin/monitor_stats.py` with a
`tests/test_monitor_stats.py` suite, following the
`features/ranked/stats.py` + `tests/test_ranked_stats.py` precedent. The
correlation rule is the load-bearing claim of this redesign and must be tested,
including the negative case (unrelated single-task errors must NOT merge).

## 7. Known issue, deliberately not fixed here

`health` is `minutes_since > median_gap × 2.5 → down`. `clan_war` alternates
between a 3-minute and a 60-minute cadence, so its median gap understates the
tolerance and it reports "down" after 9 minutes of normal quiet. Visible in
both mockup states. This is a **pre-existing rule defect, not a redesign
defect** — changing the threshold changes what the whole site's nav status
strip reports. Flagged for its own pass; out of scope here.

## 8. Shared shell

No changes needed. `_page_header.html`'s existing slots cover this page
(title, desc, `page_primary_control` for the period selector);
`_admin_tabs.html` is reused unchanged.

Noted for a later pass (inherited from the admin redesign spec, still open):
the sitewide nav status strip duplicates the Overview's System Pulse band.

## 9. Open questions for impeccable

- Motion: the Laufspuren strip and the cause rollup have no entrance treatment
  yet. Does the correlation column deserve a reveal that draws the eye to the
  vertical alignment, or does that overstate a rare event? Defer to an explicit
  `/impeccable animate` pass on the built page.
- Should a multi-task cause row carry a stronger weight than a single-task one
  beyond the current count colour?

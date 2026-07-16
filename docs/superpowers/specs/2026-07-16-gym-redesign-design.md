# Gym Tracker Redesign — Design Spec

**Date:** 2026-07-16
**Scope:** `personal_apps/templates/gym/*.html`, `personal_apps/static/gym/*`, `personal_apps/features/gym/routes.py` (import-path removal only)
**Status:** Approved by user, pending final spec review

## Context

The Gym Tracker (`/gym/*`) currently reuses the same dark "ops" visual language (purple/cyan accents, Space Grotesk + Inter, card-based layout) that the coc_stats app and other personal_apps pages use. Each of the 4 gym templates is already a self-contained HTML document (no shared base template, no dependency on `_head.html` or coc_stats assets) — the coupling is purely aesthetic, not structural.

This redesign gives the gym pages their own distinct visual identity, independent of both the rest of personal_apps and coc_stats, and takes the opportunity to make some UX improvements to the pages it touches. It is a from-scratch visual/UX redesign, not a reskin constrained by the current layout's structure.

**Pages in scope:**
- `dashboard.html` — start/resume workout, past sessions, templates, exercise catalog
- `session_detail.html` — active/finished workout: per-exercise set logging, rest timer, reorder, exercise substitution, stagnation nudges
- `session_summary.html` — post-workout PR/volume recap
- `exercise_detail.html` — per-exercise history, PRs, progress chart

**Non-goals:** no changes to underlying workout/session/exercise data model or calculations (e1RM, volume, stagnation threshold, etc. all stay as-is). No changes to the push-notification/rest-timer backend logic. No changes to unrelated personal_apps or coc_stats pages.

## Visual System

**Vibe:** bold, energetic, gym-specific — deliberately distinct from the muted purple/cyan "ops" theme used elsewhere in the repo.

**Palette:** dark base (`#0a0a0a` background, `#151515` card/tile surface, `#272727` hairline borders, `#e8e8ec` primary text, `#8a8a92` muted text), with a single accent — volt lime (`#d4ff3f`) — used sparingly and meaningfully: PR highlights, the active/current row or set, the rest-timer indicator, primary confirm actions. Lime signals "this matters right now," not decoration.

A separate muted red (existing `--red`-equivalent, e.g. `#fb7185`) is kept only for destructive actions (delete workout/exercise/template). No warning/amber color is needed given current features.

**Typography:** **Outfit** (Google Fonts, free, no licensing concerns) as the bold geometric display font for headings and all numeric displays (weights, reps, timers, stat tiles), at heavy weight (700–900) with tight tracking. Body text uses a standard system-ui/Inter stack. Numbers get the heaviest visual weight throughout — they're what gets glanced at mid-set.

**Shape language:** rounded bento-style tiles (14–16px radius) for stat blocks, summary cards, and the dashboard — this is the "Athletic Grid" direction validated via mockup. The active-workout logging screen deliberately breaks from bento tiles into a **dense table** layout (see below) — that screen prioritizes density and one-glance scanability over friendliness.

## Navigation

- **Mobile:** fixed bottom tab bar — Dashboard / Active / History / Exercises. Shows a small lime dot on the "Active" tab when a session is currently running.
- **Desktop:** slim top bar, same 4 destinations, no bottom chrome.
- Both are part of the new shared `gym.css`/`gym.js` (see Architecture below), not tied to any other page's nav.

## Page-by-page Design

### Dashboard

- **Active session tile** (bento style) when a workout is running: large elapsed-time display, workout name, "Weiter →" action. Replaces today's `.active-session` card visually but keeps the same data (`active_session.started_at`, live-updating JS timer).
- **No active session:** start-workout form (name + template picker), same fields/behavior as today, restyled to the new component set.
- **Past sessions:** compact list, same data (name, date, duration, exercise names), restyled rows, delete action unchanged.
- **Templates:** compact list, same data/actions, restyled.
- **Exercise catalog — grouped by muscle group** (using the existing `Exercise.muscle_group` / `MUSCLE_GROUPS` field, no schema change): collapsible sections per muscle group, plus an "Sonstige" section for exercises with no muscle group set. Add-exercise form stays pinned at the bottom of this section.
- **Import card: removed entirely.** The Strong-app text-import feature is already retired (all historical data was imported once; see project memory) and is not part of the redesigned dashboard.

### Active Workout (session_detail)

- **Set logging — dense table** per exercise: position / weight / reps / completion-checkmark columns. The currently-open/in-progress row is outlined in lime. This favors information density and precise tapping over large touch targets, per the validated mockup direction.
- **Rest timer** renders as a slim lime bar/badge pinned under the active exercise card — not a full-screen takeover, since the user is mid-workout and other exercises/sets must stay reachable.
- **Stagnation nudge** (existing `STAGNATION_THRESHOLD` logic, 4+ sessions without a new e1RM PR) renders as a small lime-outlined pill on the exercise header (e.g. "4 Sessions ohne PR") — visible but not a blocking popup.
- **Exercise reorder:** stays drag-handle based (existing interaction/endpoint `gym_reorder_session_exercises`), restyled to the new component set.
- **Exercise replace:** stays the same modal/dropdown flow (existing endpoint `gym_replace_session_exercise`), restyled to match the dense-table row style.
- **Add set / toggle complete / delete set:** same endpoints and data, restyled controls.

### Session Summary

- **Hero celebration** for PR exercises: each PR'd exercise gets a lime-gradient badge card up top (weight/volume PR + delta), matching the validated mockup. Below that, a plain stat row for total volume and volume delta vs. average (existing `_session_summary_data` fields — `total_volume`, `total_volume_delta_pct`, `pr_count`, etc., no backend changes).
- **No PRs this session:** the hero block simply does not render; the page goes straight to the plain stat row. No fake/empty celebration state.

### Exercise Detail

- **Progress chart — best/worst band**: a filled band between each session's best-set weight and worst-set weight (existing `chart_weights` / `chart_min_weights` data from `_exercise_progress_data` — no backend change needed), per the validated mockup direction. PR callouts (`pr_max_weight`, `pr_max_volume`) displayed above the chart.
- **Session log table** below the chart: same data (per-session sets, best/worst weight, volume), restyled to the new dense-table look.
- **Position filter** (existing `available_positions`/`selected_position` logic): rendered as a small pill-toggle group instead of today's control.

## Architecture

**Shared gym-only assets, not per-page duplication:** a single `static/gym/gym.css` and `static/gym/gym.js` hold the palette, type scale, and shared components (bento tile, dense table, nav bar, countdown/rest-timer logic, PR badge), included by all 4 templates via `<link>`/`<script>`. This keeps the 4 gym pages visually consistent with each other without each template embedding a duplicate `<style>` block or reimplementing shared JS (e.g. the rest-timer countdown) — avoiding the exact kind of duplication debt recently cleaned up in coc_stats (5 separate `renderStars()` implementations, per-page palette copies). These assets remain fully scoped to `static/gym/` — no dependency on and no dependency from `_head.html`, coc_stats palettes/JS, or any other personal_apps page.

**Backend cleanup (import removal):** since the import UI is dropped, its route and supporting code become dead and are removed from `features/gym/routes.py`:
- `gym_import` route
- `_parse_import_text`, `_parse_german_datetime`
- `GERMAN_MONTHS`, `IMPORT_DATE_LINE_RE`, `IMPORT_SET_LINE_RE`
- the `imported`/`skipped`/`imported_sets` query-param handling on the dashboard route

`Exercise.previous_name` and its fallback lookup are **not** removed — they're harmless and already confirmed to stay (see project memory), even though their only consumer (`gym_import`) is going away; the field itself isn't exclusively tied to import and rename-history is still a reasonable thing to preserve on the model.

**Data/model changes:** none. All calculations (e1RM, volume including unilateral doubling, stagnation counting, PR detection) are unchanged; this is a template/static-asset and single-route-removal change only.

## Empty States

- No active session → start-workout form (unchanged data/behavior).
- No past sessions / no templates / no exercises in catalog → existing empty-state copy, restyled to match the new system.
- No PRs in session summary → hero block omitted (see above), not faked.

## Verification Plan

Manual browser verification after implementation, per the project's established pattern:
- Dashboard: with an active session, without one, with a populated and an empty exercise catalog (grouping renders correctly).
- Active workout: logging a set, rest timer counting down, stagnation nudge appearing when applicable, reorder, replace.
- Session summary: with at least one PR, and with none.
- Exercise detail: chart renders with band data, position filter switches correctly.
- Checked at mobile viewport 390×844 and at a standard desktop width.

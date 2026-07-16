# Gym Tracker Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 4 gym-tracker pages (`dashboard`, `session_detail`, `session_summary`, `exercise_detail`) a new, self-contained dark/volt-lime visual identity and a handful of approved UX tweaks, replacing the current purple/cyan "ops" look they copied from the rest of the repo.

**Architecture:** One new shared, gym-only asset pair (`static/gym/gym.css`, `static/gym/gym.js`) plus a shared nav partial (`templates/gym/_nav.html`) hold the whole design system and are linked from all 4 templates — no per-page duplicate `<style>` blocks. Each template keeps its existing HTML structure, ids, and JS-bound class names (the drag-reorder/AJAX-refresh/rest-timer/progress-modal logic in `session_detail.html` is complex and already works — it is restyled in place, not rebuilt). `routes.py` gets the retired text-import feature deleted, a small view-model addition (exercises grouped by muscle group) for the dashboard, and one new blueprint-wide context processor so every gym page knows whether a session is currently active (for the nav).

**Tech Stack:** Flask + Jinja2, vanilla CSS/JS (no build step, no framework), Chart.js 4 (already a CDN dependency, kept), Google Fonts (Outfit + Inter, kept as a CDN link like today).

## Global Constraints

- **Palette** (exact hex, define once in `gym.css` as CSS custom properties): `--gym-bg:#0a0a0a`, `--gym-surface:#151515`, `--gym-surface-2:#1c1c1c`, `--gym-border:#272727`, `--gym-border-soft:#1c1c1c`, `--gym-text:#e8e8ec`, `--gym-muted:#8a8a92`, `--gym-lime:#d4ff3f`, `--gym-lime-dim:#a8d92a`, `--gym-red:#fb7185`.
- **Typography:** `Outfit` (weights 500/600/700/800) for headings and all numeric displays; `Inter` (weights 400/500/600) for body text. Both loaded via one Google Fonts link per template, same pattern as today.
- **No automated test suite exists anywhere in this repo** (no `pytest`, no `conftest.py`, no test files). This plan does not introduce one — that would be scope creep beyond "redesign the gym pages." Every task's verification step is a **manual check against the running dev server** instead of a `pytest` step: run `python app.py` from `personal_apps/` (boots on `http://127.0.0.1:5000`, confirmed working), log in at `/login`, and exercise the page/feature in a browser. This applies even to the two backend logic changes (import removal, muscle-group grouping) since there is no harness to unit-test Flask routes in this codebase today.
- **JS-bound selectors that must keep their exact names** (referenced by `getElementById`/`querySelector`/`classList` in `session_detail.html`'s script — renaming any of these breaks drag-reorder, the AJAX partial-refresh, the rest timer, or the progress modal): `#session-duration`, `#rest-fill` (+ its `data-rest-ends`/`data-rest-total` attributes), `#notify-row`, `#notify-enable-btn`, `#exercise-cards` (+ `.read-only` class), `.exercise-card` (+ `data-se-id` attribute), `.card-title-area`, `.dragging`, `.drag-ghost`, `.collapsed`, `#add-exercise-form`, `#exercise-select`, `#new-exercise-fields`, `#new-exercise-muscle-group`, `.rest-form`, `input[name="rest_seconds"]`, `.progress-open-btn` (+ `data-exercise-id`/`data-position` attributes), `#progress-modal`, `#progress-modal-title`, `#progress-modal-close`, `#progress-modal-body`, `form[data-confirm]`. These are **not renamed** anywhere in this plan — only their CSS declarations change.
- **Text-import feature is fully removed** — route, parsing helpers, regexes, and the dashboard's `imported`/`skipped` query-param UI. `Exercise.previous_name` and its fallback lookup (used elsewhere, not import-specific) are **not** touched.
- **Bottom tab bar has 4 destinations, but only 2 are real routes.** "Dashboard" → `gym.gym_dashboard`, "Aktiv" → `gym.session_detail` (of the current active session, if any). "Verlauf" and "Übungen" are **not** separate pages — they resolve to anchors on the dashboard (`#history` on the past-sessions card, `#exercises` on the muscle-group-grouped catalog card), since that's where those sections actually live. This is called out explicitly here so it isn't mistaken for an oversight.

---

## File Structure

**New:**
- `personal_apps/static/gym/gym.css` — the entire shared design system (palette, type, nav/tab-bar, cards, buttons, forms, badges, dense-table set rows, rest bar, modal, PR hero cards, charts container, tables). Union of what the 4 old per-page `<style>` blocks defined, re-themed and de-duplicated into one file.
- `personal_apps/static/gym/gym.js` — `window.GymChart.renderProgressChart(canvas, data)` (the one chart look, used by both `exercise_detail.html` and the progress modal in `session_detail.html`) and `window.GymUtils.escapeHtml(value)` (moved out of `session_detail.html`'s inline script so it's available wherever needed).
- `personal_apps/templates/gym/_nav.html` — shared top-bar + bottom-tab-bar include, used by all 4 templates.

**Modified:**
- `personal_apps/templates/gym/dashboard.html` — new head/links, muscle-group-grouped exercise catalog, import card removed.
- `personal_apps/templates/gym/session_detail.html` — new head/links, dense-table set rows, card-level rest bar (was a per-row overlay), progress-modal chart now calls the shared helper.
- `personal_apps/templates/gym/session_summary.html` — new head/links, hero PR cards.
- `personal_apps/templates/gym/exercise_detail.html` — new head/links, pill-style position filter, chart now calls the shared helper (best/worst band).
- `personal_apps/static/manifest.json` — `background_color`/`theme_color` updated to the new dark bg.
- `personal_apps/features/gym/routes.py` — delete the import feature; add muscle-group grouping to `gym_dashboard()`; add a blueprint-wide context processor exposing the active session to `_nav.html`.

---

### Task 1: Shared design system foundation

**Files:**
- Create: `personal_apps/static/gym/gym.css`
- Create: `personal_apps/static/gym/gym.js`
- Create: `personal_apps/templates/gym/_nav.html`
- Modify: `personal_apps/features/gym/routes.py` (add context processor near `_get_active_session`, e.g. after its definition around line 153)

**Interfaces:**
- Produces: CSS custom properties and classes listed in Global Constraints' palette + all classes referenced below; `window.GymChart.renderProgressChart(canvas: HTMLCanvasElement, data: {labels: string[], weights: number[], minWeights: number[], volumes: number[]}) -> Chart`; `window.GymUtils.escapeHtml(value: any) -> string`; Jinja context variable `gym_active_session` (a `WorkoutSession` instance or `None`), available in every template rendered by a `gym_bp` view without any view needing to pass it explicitly.
- Consumes: nothing from other tasks (this is the foundation everything else builds on).

This task is purely additive — none of the 4 page templates reference these new files yet, so the running app is unaffected until Task 2 starts wiring them in.

- [ ] **Step 1: Add the context processor**

In `personal_apps/features/gym/routes.py`, immediately after the `_get_active_session` function definition (currently ends around line 153), add:

```python
@gym_bp.context_processor
def inject_gym_nav_context():
    """Makes the active session available to `_nav.html` on every gym page,
    not just the dashboard -- so the nav can show a "session running" dot
    and link straight to it from anywhere. Reuses `_get_active_session`,
    which is already idempotent (it only mutates state once, the first time
    it notices a session has gone stale past the timeout)."""
    return {'gym_active_session': _get_active_session()}
```

- [ ] **Step 2: Create `gym.css`**

Create `personal_apps/static/gym/gym.css`:

```css
/* Gym Tracker design system. Self-contained: no dependency on _head.html,
   coc_stats, or any other personal_apps page/palette. Shared by all 4 gym
   templates via <link>. */

:root {
    --gym-bg: #0a0a0a;
    --gym-surface: #151515;
    --gym-surface-2: #1c1c1c;
    --gym-border: #272727;
    --gym-border-soft: #1c1c1c;
    --gym-text: #e8e8ec;
    --gym-muted: #8a8a92;
    --gym-lime: #d4ff3f;
    --gym-lime-dim: #a8d92a;
    --gym-red: #fb7185;
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--gym-bg);
    color: var(--gym-text);
    min-height: 100vh;
    padding-bottom: 72px; /* room for the fixed bottom tab bar on mobile */
}
@media (min-width: 861px) {
    body { padding-bottom: 0; }
}

a { text-decoration: none; color: inherit; }

h1 { font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 28px; letter-spacing: -0.5px; margin-bottom: 4px; }
h2 { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 17px; letter-spacing: -0.2px; }

.gym-page-wrap { max-width: 1000px; margin: 0 auto; padding: 28px 24px 56px; position: relative; z-index: 1; }
@media (max-width: 700px) {
    .gym-page-wrap { padding: 20px 16px 40px; }
}

/* ===== Top nav (desktop) + bottom tab bar (mobile) ===== */
.gym-nav {
    position: sticky; top: 0; z-index: 100;
    background: rgba(10,10,10,0.92);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border-bottom: 1px solid var(--gym-border);
}
.gym-nav-inner {
    max-width: 1000px; margin: 0 auto; padding: 0 24px;
    height: 58px; display: flex; align-items: center; justify-content: space-between;
}
.gym-nav-logo { display: flex; align-items: center; gap: 10px; }
.gym-logo-icon {
    width: 34px; height: 34px; background: var(--gym-lime); color: #0a0a0a;
    border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 16px;
}
.gym-nav-logo span { font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 18px; }
.gym-nav-links { display: flex; align-items: center; gap: 4px; }
.gym-nav-links a {
    font-size: 13px; font-weight: 600; color: var(--gym-muted);
    padding: 7px 14px; border-radius: 999px; transition: color 0.15s, background 0.15s;
}
.gym-nav-links a:hover { color: var(--gym-text); background: var(--gym-surface); }
.gym-nav-links a.active { color: var(--gym-bg); background: var(--gym-lime); }
.gym-nav-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--gym-lime); margin-left: 5px; }

.gym-tabbar {
    display: none;
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 100;
    background: rgba(10,10,10,0.95);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border-top: 1px solid var(--gym-border);
    padding: 6px max(6px, env(safe-area-inset-left)) max(6px, env(safe-area-inset-bottom));
}
@media (max-width: 860px) {
    .gym-nav-links { display: none; }
    .gym-tabbar { display: flex; }
}
.gym-tabbar a {
    flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: 6px 4px; font-size: 10px; font-weight: 600; color: var(--gym-muted);
    border-radius: 12px;
}
.gym-tabbar a .gym-tab-icon { font-size: 18px; line-height: 1; position: relative; }
.gym-tabbar a.active { color: var(--gym-lime); }
.gym-tabbar a .gym-tab-icon .gym-nav-dot { position: absolute; top: -2px; right: -6px; margin: 0; }

/* ===== Cards ===== */
.card {
    background: var(--gym-surface); border: 1px solid var(--gym-border);
    border-radius: 16px; overflow: hidden; margin-bottom: 18px;
}
.card-header {
    padding: 14px 18px; border-bottom: 1px solid var(--gym-border);
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; row-gap: 8px; column-gap: 12px;
}
.card-body { padding: 18px; }

/* ===== Buttons ===== */
.btn {
    padding: 8px 16px; border-radius: 999px; font-size: 13px; font-weight: 700;
    font-family: inherit; cursor: pointer; border: 1px solid transparent; transition: all 0.15s;
    white-space: nowrap;
}
.btn-primary { background: var(--gym-lime); color: #0a0a0a; border-color: transparent; }
.btn-primary:hover { background: var(--gym-lime-dim); }
.btn-ghost { background: transparent; color: var(--gym-muted); border-color: var(--gym-border); }
.btn-ghost:hover { color: var(--gym-text); border-color: var(--gym-text); }
.btn-danger { background: transparent; color: var(--gym-red); border-color: var(--gym-red); }
.btn-danger:hover { background: rgba(251,113,133,0.1); }
.btn-sm { padding: 5px 11px; font-size: 12px; }
.icon-btn {
    width: 32px; height: 32px; padding: 0; flex-shrink: 0;
    display: inline-flex; align-items: center; justify-content: center; font-size: 14px;
}

/* ===== Forms ===== */
.form-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--gym-muted); }
.form-group input, .form-group select, .form-group textarea {
    background: var(--gym-surface-2); border: 1px solid var(--gym-border); border-radius: 8px;
    color: var(--gym-text); padding: 7px 10px; font-size: 13px; font-family: inherit;
    transition: border-color 0.15s;
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { outline: none; border-color: var(--gym-lime); }
.form-group.grow { flex: 1; min-width: 130px; }
.form-group.grow input, .form-group.grow select { width: 100%; }
.num-input { width: 90px; }
.num-input-sm {
    width: 64px; background: var(--gym-surface-2); border: 1px solid var(--gym-border); border-radius: 8px;
    color: var(--gym-text); padding: 5px 8px; font-size: 13px; font-family: inherit;
}
.num-input-sm:focus { outline: none; border-color: var(--gym-lime); }
.unit { color: var(--gym-muted); font-size: 12px; }

/* ===== Badges / pills ===== */
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.badge-active { background: rgba(212,255,63,0.15); color: var(--gym-lime); }
.badge-done { background: rgba(139,145,167,0.15); color: var(--gym-muted); }
.gym-pill {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700;
    color: var(--gym-muted); background: var(--gym-surface-2); border: 1px solid var(--gym-border);
    border-radius: 999px; padding: 4px 11px; cursor: pointer; transition: all 0.15s;
}
.gym-pill.active, .gym-pill:hover { color: var(--gym-bg); background: var(--gym-lime); border-color: var(--gym-lime); }

.empty { text-align: center; padding: 28px; color: var(--gym-muted); font-size: 13px; }

/* ===== Dashboard: active-session hero ===== */
.active-session { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; }
.active-session .name { font-family: 'Outfit', sans-serif; font-size: 16px; font-weight: 700; }
.active-session .elapsed { font-family: 'Outfit', sans-serif; font-size: 30px; font-weight: 800; color: var(--gym-lime); }

/* ===== Dashboard: lists ===== */
.list-row {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 10px 18px; border-bottom: 1px solid var(--gym-border-soft); font-size: 13px;
}
.list-row:last-child { border-bottom: none; }
.list-row .main { font-weight: 700; }
.list-row .meta { font-size: 11px; color: var(--gym-muted); }
.list-row .actions { display: flex; align-items: center; gap: 8px; }

/* ===== Dashboard: exercise catalog grouped by muscle group ===== */
.gym-muscle-section { border-bottom: 1px solid var(--gym-border-soft); }
.gym-muscle-section:last-child { border-bottom: none; }
.gym-muscle-header {
    padding: 10px 18px; font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.6px; color: var(--gym-lime); background: rgba(212,255,63,0.06);
    cursor: pointer; display: flex; align-items: center; justify-content: space-between;
}
.gym-muscle-section.collapsed .gym-muscle-rows { display: none; }

/* ===== Active workout: dense-table set logging ===== */
.session-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; margin-bottom: 16px; }
.session-header .duration { font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 800; color: var(--gym-lime); }
.notify-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 18px; font-size: 13px; color: var(--gym-muted); }

.sets-list { margin-bottom: 12px; }
.set-row {
    position: relative; overflow: hidden;
    display: flex; align-items: center; gap: 10px; padding: 7px 8px; margin: 0 -8px;
    border-top: 1px solid var(--gym-border-soft); font-size: 13px;
    border-left: 3px solid transparent; transition: opacity 0.15s, border-color 0.15s;
}
.set-row:first-child { border-top: none; }
.set-row.set-pending { opacity: 0.55; border-left-style: dashed; border-left-color: var(--gym-border-soft); }
.set-row.set-done { border-left-color: var(--gym-lime); background: rgba(212,255,63,0.05); }
.pending-hint { font-size: 11px; color: var(--gym-muted); margin-bottom: 8px; }
.stagnation-note {
    font-size: 12px; font-weight: 600; color: var(--gym-lime); background: rgba(212,255,63,0.08);
    border: 1px solid rgba(212,255,63,0.35); border-radius: 999px; padding: 6px 12px; margin-bottom: 10px;
    display: inline-block;
}
.replace-note { font-size: 11px; color: var(--gym-muted); margin-top: 4px; }
.replace-details { margin-top: 12px; }
.replace-details summary { cursor: pointer; list-style: none; display: inline-block; }
.replace-details summary::-webkit-details-marker { display: none; }
.set-row > * { position: relative; z-index: 1; }
.set-index { width: 20px; color: var(--gym-muted); font-weight: 600; }
.set-edit-form { display: flex; align-items: center; gap: 6px; flex: 1; }
.set-check {
    width: 30px; height: 30px; flex-shrink: 0; border-radius: 999px;
    border: 1px solid var(--gym-border); background: var(--gym-surface-2); color: transparent;
    font-size: 14px; font-weight: 700; line-height: 1; cursor: pointer; transition: all 0.15s;
}
.set-check.checked { background: var(--gym-lime); border-color: var(--gym-lime); color: #0a0a0a; }
.set-value { font-family: 'Outfit', sans-serif; font-weight: 700; }

/* ===== Active workout: rest timer (card-level bar, not a per-row overlay) ===== */
.rest-bar { margin: 4px 0 12px; }
.rest-bar-top { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; color: var(--gym-muted); margin-bottom: 4px; }
.rest-bar-label { font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 13px; color: var(--gym-lime); }
.rest-bar-track { height: 6px; border-radius: 999px; background: var(--gym-surface-2); overflow: hidden; }
.rest-bar-fill { height: 100%; background: var(--gym-lime); transition: width 1s linear; }

.exercise-card.dragging { position: relative; z-index: 50; box-shadow: 0 8px 24px rgba(0,0,0,0.5); cursor: grabbing; touch-action: none; }
.exercise-card.dragging.drag-ghost { z-index: 200; }
#exercise-cards { user-select: none; -webkit-user-select: none; }
.rest-form { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }

.card-header-title-row { display: flex; align-items: center; gap: 6px; flex: 1 1 140px; min-width: 0; }
.card-title-area { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; cursor: pointer; touch-action: none; }
.card-title-area h2 { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#exercise-cards:not(.read-only) .card-title-area { cursor: grab; }
.exercise-card.dragging .card-title-area { cursor: grabbing; }
.exercise-card.collapsed .card-body { display: none; }

.progress-badge {
    font-size: 11px; font-weight: 700; font-family: 'Outfit', sans-serif; flex-shrink: 0;
    color: var(--gym-muted); background: var(--gym-surface-2); border: 1px solid var(--gym-border);
    border-radius: 999px; padding: 2px 8px;
}
.progress-badge.all-done { color: var(--gym-lime); border-color: var(--gym-lime); background: rgba(212,255,63,0.1); }
.progress-open-btn {
    background: transparent; border: none; color: var(--gym-muted); font-size: 16px;
    cursor: pointer; flex-shrink: 0; line-height: 1;
    width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
}
.progress-open-btn:hover { color: var(--gym-text); }

/* ===== Modal (quick-glance progress) ===== */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 20px; }
.modal-overlay.hidden { display: none; }
.modal-box { background: var(--gym-surface); border: 1px solid var(--gym-border); border-radius: 16px; max-width: 480px; width: 100%; max-height: 80vh; overflow-y: auto; }
.modal-header {
    display: flex; align-items: center; justify-content: space-between; padding: 14px 18px;
    border-bottom: 1px solid var(--gym-border); position: sticky; top: 0; background: var(--gym-surface);
}
.modal-body { padding: 18px; }
.pr-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.pr-card { background: var(--gym-surface-2); border: 1px solid var(--gym-border); border-radius: 12px; padding: 12px; }
.pr-card .label { font-size: 10px; color: var(--gym-muted); text-transform: uppercase; letter-spacing: 0.4px; font-weight: 700; }
.pr-card .val { font-family: 'Outfit', sans-serif; font-size: 20px; font-weight: 800; color: var(--gym-lime); margin: 4px 0 2px; }
.pr-card .sub { font-size: 11px; color: var(--gym-muted); }
.modal-chart-wrap { height: 200px; margin-bottom: 8px; }
.modal-position-note { font-size: 11px; color: var(--gym-muted); margin-bottom: 12px; }

.actions-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }

/* ===== Exercise detail: period cards + table ===== */
.chart-wrap { padding: 18px; height: 280px; }
.period-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-bottom: 20px; }
.period-card { background: var(--gym-surface); border: 1px solid var(--gym-border); border-radius: 16px; padding: 16px; }
.period-card .label { font-size: 11px; color: var(--gym-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
.period-card .rate-val { font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 800; color: var(--gym-lime); margin: 8px 0 4px; }
.period-card .sub { font-size: 12px; color: var(--gym-muted); }
.period-card .sub.positive { color: var(--gym-lime); }
.period-card .sub.negative { color: var(--gym-red); }

table.sets { width: 100%; border-collapse: collapse; font-size: 13px; }
table.sets th { text-align: left; color: var(--gym-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; padding: 8px; }
table.sets td { padding: 8px; border-top: 1px solid var(--gym-border-soft); }
table.sets td.num { font-family: 'Outfit', sans-serif; font-weight: 700; }

/* ===== Session summary: hero PR cards ===== */
.gym-pr-hero { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 16px; }
.gym-pr-hero-card {
    background: linear-gradient(135deg, var(--gym-lime), var(--gym-lime-dim)); color: #0a0a0a;
    border-radius: 16px; padding: 14px;
}
.gym-pr-hero-card .name { font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; opacity: 0.75; }
.gym-pr-hero-card .headline { font-family: 'Outfit', sans-serif; font-size: 22px; font-weight: 800; margin: 4px 0 2px; }
.gym-pr-hero-card .sub { font-size: 11px; font-weight: 700; }

.summary-exercise { padding: 14px 18px; border-top: 1px solid var(--gym-border-soft); }
.summary-exercise:first-child { border-top: none; }
.summary-exercise .name { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 15px; margin-bottom: 6px; }
.summary-exercise .stats { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--gym-muted); margin-bottom: 6px; }
.summary-exercise .stats strong { color: var(--gym-text); font-family: 'Outfit', sans-serif; }
.pr-badges { display: flex; flex-wrap: wrap; gap: 6px; }
.pr-badge {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700;
    color: #0a0a0a; background: var(--gym-lime);
    border-radius: 999px; padding: 3px 10px;
}
.summary-delta { font-size: 12px; color: var(--gym-muted); }
.summary-delta.positive { color: var(--gym-lime); }
.summary-delta.negative { color: var(--gym-red); }
```

- [ ] **Step 3: Create `gym.js`**

Create `personal_apps/static/gym/gym.js`:

```js
// Gym Tracker shared JS -- chart rendering + small utilities used across
// exercise_detail.html (static Jinja-rendered data) and session_detail.html's
// quick-glance progress modal (dynamically fetched JSON). Kept as one
// implementation so the two never drift into two different chart looks.
window.GymUtils = {
    escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    },
};

window.GymChart = {
    // Renders the best/worst-weight band + a volume reference line onto
    // `canvas`. `data` = { labels, weights, minWeights, volumes }. Returns
    // the Chart instance -- caller owns its lifecycle (call .destroy()
    // before re-rendering onto the same canvas, same as Chart.js always
    // requires).
    renderProgressChart(canvas, data) {
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        // Drawn first (order:2) so the fill on the dataset
                        // below it (order:1, fill:'-1') has this as its
                        // "previous" dataset to band against.
                        label: 'Leichtestes Gewicht (kg)',
                        data: data.minWeights,
                        borderColor: 'rgba(232,232,236,0.25)',
                        backgroundColor: 'transparent',
                        borderDash: [4, 4],
                        pointRadius: 0,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y',
                        order: 2,
                    },
                    {
                        label: 'Bestes Gewicht (kg)',
                        data: data.weights,
                        borderColor: '#d4ff3f',
                        backgroundColor: 'rgba(212,255,63,0.18)',
                        tension: 0.3,
                        fill: '-1',
                        yAxisID: 'y',
                        order: 1,
                    },
                    {
                        label: 'Volumen (kg)',
                        data: data.volumes,
                        borderColor: '#8a8a92',
                        backgroundColor: 'transparent',
                        borderDash: [2, 3],
                        pointRadius: 0,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y1',
                        order: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#8a8a92', maxRotation: 0 }, grid: { color: '#272727' } },
                    y: { position: 'left', ticks: { color: '#8a8a92' }, grid: { color: '#272727' } },
                    y1: { position: 'right', ticks: { color: '#8a8a92' }, grid: { display: false } },
                },
                plugins: {
                    legend: { labels: { color: '#e8e8ec', boxWidth: 12, font: { size: 10 } } },
                },
            },
        });
    },
};
```

- [ ] **Step 4: Create the shared nav partial**

Create `personal_apps/templates/gym/_nav.html`:

```jinja
{# Shared gym nav: top bar (desktop, >860px) + bottom tab bar (mobile).
   `gym_active_session` is injected into every gym-blueprint template's
   context automatically by inject_gym_nav_context() in routes.py -- no
   view needs to pass it explicitly. "Verlauf"/"Übungen" are anchors on the
   dashboard (there is no separate history/exercises route), see the Global
   Constraints note in the plan this was built from. #}
<nav class="gym-nav">
    <div class="gym-nav-inner">
        <div class="gym-nav-logo">
            <div class="gym-logo-icon">🏋️</div>
            <span>Gym Tracker</span>
        </div>
        <div class="gym-nav-links">
            <a href="{{ url_for('gym.gym_dashboard') }}" class="{{ 'active' if request.endpoint == 'gym.gym_dashboard' else '' }}">Dashboard</a>
            {% if gym_active_session %}
            <a href="{{ url_for('gym.session_detail', session_id=gym_active_session.id) }}" class="{{ 'active' if request.endpoint == 'gym.session_detail' else '' }}">Aktiv<span class="gym-nav-dot"></span></a>
            {% endif %}
            <a href="{{ url_for('gym.gym_dashboard') }}#history" class="{{ 'active' if request.endpoint == 'gym.gym_session_summary' else '' }}">Verlauf</a>
            <a href="{{ url_for('gym.gym_dashboard') }}#exercises" class="{{ 'active' if request.endpoint == 'gym.exercise_detail' else '' }}">Übungen</a>
            <a href="/logout">Logout</a>
        </div>
    </div>
</nav>

<div class="gym-tabbar">
    <a href="{{ url_for('gym.gym_dashboard') }}" class="{{ 'active' if request.endpoint == 'gym.gym_dashboard' else '' }}">
        <span class="gym-tab-icon">🏠</span>Dashboard
    </a>
    <a href="{{ url_for('gym.session_detail', session_id=gym_active_session.id) if gym_active_session else url_for('gym.gym_dashboard') }}" class="{{ 'active' if request.endpoint == 'gym.session_detail' else '' }}">
        <span class="gym-tab-icon">🏋️{% if gym_active_session %}<span class="gym-nav-dot"></span>{% endif %}</span>Aktiv
    </a>
    <a href="{{ url_for('gym.gym_dashboard') }}#history" class="{{ 'active' if request.endpoint == 'gym.gym_session_summary' else '' }}">
        <span class="gym-tab-icon">📜</span>Verlauf
    </a>
    <a href="{{ url_for('gym.gym_dashboard') }}#exercises" class="{{ 'active' if request.endpoint == 'gym.exercise_detail' else '' }}">
        <span class="gym-tab-icon">📋</span>Übungen
    </a>
</div>
```

- [ ] **Step 5: Verify nothing broke**

Run: `cd personal_apps && python app.py`
Expected: server boots on `http://127.0.0.1:5000` with no traceback (the new context processor must not error — `_get_active_session` is already proven code, just newly wired into every gym page's context).

Log in at `/login`, visit `/gym`, `/gym/session/<any existing session id>`, `/gym/exercises/<any existing exercise id>` — all should render **exactly as they did before this task** (old styles, old nav), since no template references the new files yet. This is the pre-redesign regression baseline.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/static/gym/gym.css personal_apps/static/gym/gym.js personal_apps/templates/gym/_nav.html personal_apps/features/gym/routes.py
git commit -m "feat(gym): add shared design-system CSS/JS and nav partial

Foundation for the gym pages redesign -- palette, typography, and
component styles in one place instead of per-page duplicates, plus a
context processor so every gym page knows about the active session for
the new nav. Not yet wired into any template."
```

---

### Task 2: Dashboard redesign + import-feature removal

**Files:**
- Modify: `personal_apps/templates/gym/dashboard.html` (full rewrite)
- Modify: `personal_apps/features/gym/routes.py` (delete import feature, add muscle-group grouping to `gym_dashboard`)

**Interfaces:**
- Consumes: `gym.css`, `gym.js` (unused here, no chart on this page), `_nav.html`, `gym_active_session` context var — all from Task 1.
- Produces: nothing new consumed by later tasks (this page is a leaf).

- [ ] **Step 1: Remove the import feature from `routes.py`**

In `personal_apps/features/gym/routes.py`, delete:
- The `GERMAN_MONTHS` dict (currently ~lines 44-47)
- The `IMPORT_DATE_LINE_RE` / `IMPORT_SET_LINE_RE` regexes (~lines 48-49)
- The `_parse_german_datetime` function (~lines 52-63)
- The `_parse_import_text` function (~lines 66-105)
- The `gym_import` route (~lines 448-498)
- The comment block above `GERMAN_MONTHS` describing the "Strong app" text format (~lines 37-43)

- [ ] **Step 2: Add muscle-group grouping to the dashboard route**

In `gym_dashboard()` (personal_apps/features/gym/routes.py, currently ~lines 424-445), replace:

```python
@gym_bp.route('/gym', strict_slashes=False)
@login_required
def gym_dashboard():
    active_session = _get_active_session()
    exercises = Exercise.query.order_by(Exercise.name).all()
    templates = WorkoutTemplate.query.order_by(WorkoutTemplate.name).all()
    past_sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .order_by(WorkoutSession.started_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        'gym/dashboard.html',
        active_session=active_session,
        exercises=exercises,
        templates=templates,
        past_sessions=past_sessions,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
    )
```

with:

```python
@gym_bp.route('/gym', strict_slashes=False)
@login_required
def gym_dashboard():
    active_session = _get_active_session()
    exercises = Exercise.query.order_by(Exercise.name).all()
    templates = WorkoutTemplate.query.order_by(WorkoutTemplate.name).all()
    past_sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .order_by(WorkoutSession.started_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        'gym/dashboard.html',
        active_session=active_session,
        exercises=exercises,
        exercises_by_group=_group_exercises_by_muscle(exercises),
        templates=templates,
        past_sessions=past_sessions,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
    )
```

Then add the helper just above `gym_dashboard` (after `_get_active_session`'s neighboring helpers, e.g. right before the `@gym_bp.route('/gym', ...)` line):

```python
def _group_exercises_by_muscle(exercises):
    """Buckets exercises by MUSCLE_GROUPS (in that fixed vocabulary's
    order), with anything that doesn't match a current group -- no
    muscle_group set, or a legacy free-text value from before the enum
    existed -- collected into a trailing "Sonstige" bucket instead of being
    silently dropped. `exercises` is expected pre-sorted by name (as
    gym_dashboard already queries it), so each bucket stays alphabetical."""
    grouped = {mg: [] for mg in MUSCLE_GROUPS}
    other = []
    for e in exercises:
        if e.muscle_group in grouped:
            grouped[e.muscle_group].append(e)
        else:
            other.append(e)
    result = [(mg, grouped[mg]) for mg in MUSCLE_GROUPS if grouped[mg]]
    if other:
        result.append(('Sonstige', other))
    return result
```

- [ ] **Step 3: Rewrite `dashboard.html`**

Replace the full contents of `personal_apps/templates/gym/dashboard.html` with:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gym Tracker</title>
    <link rel="manifest" href="/static/manifest.json">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="apple-touch-icon" href="/static/gym/icons/icon-192.png">
    <meta name="theme-color" content="#0a0a0a">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='gym/gym.css') }}">
</head>
<body>

{% include 'gym/_nav.html' %}

<div class="gym-page-wrap">
    <h1>Gym Tracker</h1>
    <p style="color:var(--gym-muted);font-size:14px;margin-bottom:24px">Workouts, Sätze und Fortschritt verfolgen</p>

    {% if active_session %}
    <div class="card">
        <div class="card-header"><h2>Workout läuft</h2></div>
        <div class="card-body active-session">
            <div>
                <div class="name">{{ active_session.name or 'Workout' }}</div>
                <div class="elapsed" id="active-elapsed" data-started="{{ active_session.started_at.isoformat() }}">--:--:--</div>
            </div>
            <a class="btn btn-primary" href="{{ url_for('gym.session_detail', session_id=active_session.id) }}">Weiter →</a>
        </div>
    </div>
    {% else %}
    <div class="card">
        <div class="card-header"><h2>Workout starten</h2></div>
        <div class="card-body">
            <form method="post" action="{{ url_for('gym.gym_start') }}">
                <div class="form-row">
                    <div class="form-group grow">
                        <label>Name (optional)</label>
                        <input type="text" name="name" placeholder="z.B. Push Day">
                    </div>
                    <div class="form-group grow">
                        <label>Vorlage</label>
                        <select name="template_id">
                            <option value="">— Ohne Vorlage —</option>
                            {% for t in templates %}
                            <option value="{{ t.id }}">{{ t.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">Workout starten</button>
                </div>
            </form>
        </div>
    </div>
    {% endif %}

    <div class="card" id="history">
        <div class="card-header"><h2>Vergangene Workouts</h2></div>
        {% if past_sessions %}
        <div>
            {% for s in past_sessions %}
            <div class="list-row">
                <a href="{{ url_for('gym.session_detail', session_id=s.id) }}" style="flex:1;min-width:0">
                    <div class="main">{{ s.name or 'Workout' }}</div>
                    <div class="meta">{{ s.started_at.strftime('%d.%m.%Y %H:%M') }} · {{ s.finished_at - s.started_at }}</div>
                    <div class="meta">{{ s.exercises|map(attribute='exercise.name')|join(', ') }}</div>
                </a>
                <div class="actions">
                    <form method="post" action="{{ url_for('gym.gym_delete_session', session_id=s.id) }}" onsubmit="return confirm('Workout unwiderruflich löschen?')">
                        <button type="submit" class="btn btn-danger btn-sm">Löschen</button>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="empty">Noch keine abgeschlossenen Workouts.</div>
        {% endif %}
    </div>

    <div class="card">
        <div class="card-header"><h2>Vorlagen</h2></div>
        {% if templates %}
        <div>
            {% for t in templates %}
            <div class="list-row">
                <div>
                    <div class="main">{{ t.name }}</div>
                    <div class="meta">{{ t.exercises|map(attribute='exercise.name')|join(', ') }}</div>
                </div>
                <div class="actions">
                    <form method="post" action="{{ url_for('gym.gym_delete_template', template_id=t.id) }}" onsubmit="return confirm('Vorlage löschen?')">
                        <button type="submit" class="btn btn-danger btn-sm">Löschen</button>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="empty">Noch keine Vorlagen gespeichert. Speichere ein Workout als Vorlage, um es hier zu sehen.</div>
        {% endif %}
    </div>

    <div class="card" id="exercises">
        <div class="card-header"><h2>Übungen</h2></div>
        {% if exercises_by_group %}
        {% for group_name, group_exercises in exercises_by_group %}
        <div class="gym-muscle-section">
            <div class="gym-muscle-header">{{ group_name }} ({{ group_exercises|length }})</div>
            <div class="gym-muscle-rows">
                {% for e in group_exercises %}
                <div class="list-row">
                    <a href="{{ url_for('gym.exercise_detail', exercise_id=e.id) }}">
                        <div class="main">{{ e.name }}</div>
                        <div class="meta">{% if e.default_rest_seconds %}{{ e.default_rest_seconds }}s Pause{% endif %}</div>
                    </a>
                    <div class="actions">
                        {% if not e.session_exercises and not e.template_exercises %}
                        <form method="post" action="{{ url_for('gym.gym_delete_exercise', exercise_id=e.id) }}" onsubmit="return confirm('Übung löschen?')">
                            <button type="submit" class="btn btn-danger btn-sm">Löschen</button>
                        </form>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
        {% else %}
        <div class="empty">Noch keine Übungen im Katalog.</div>
        {% endif %}
        <div class="card-body" style="border-top:1px solid var(--gym-border)">
            <form method="post" action="{{ url_for('gym.gym_add_exercise') }}">
                <div class="form-row">
                    <div class="form-group grow">
                        <label>Neue Übung</label>
                        <input type="text" name="name" placeholder="z.B. Bankdrücken" required>
                    </div>
                    <div class="form-group grow">
                        <label>Muskelgruppe</label>
                        <select name="muscle_group">
                            <option value="">— optional —</option>
                            {% for mg in muscle_groups %}
                            <option value="{{ mg }}">{{ mg }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Pause (Sek.)</label>
                        <input type="number" name="default_rest_seconds" min="0" class="num-input" placeholder="90">
                    </div>
                    <div class="form-group">
                        <label>
                            <input type="checkbox" name="is_unilateral" style="width:auto;margin-right:4px">
                            Einseitig (pro Seite)
                        </label>
                    </div>
                    <button type="submit" class="btn btn-primary">Hinzufügen</button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
{% if active_session %}
const startedAt = new Date(document.getElementById('active-elapsed').dataset.started + 'Z');
function pad(n) { return String(n).padStart(2, '0'); }
function tick() {
    const diff = Math.max(0, Date.now() - startedAt.getTime());
    const totalSec = Math.floor(diff / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    document.getElementById('active-elapsed').textContent = `${pad(h)}:${pad(m)}:${pad(s)}`;
}
tick();
setInterval(tick, 1000);
{% endif %}
</script>

</body>
</html>
```

- [ ] **Step 4: Verify**

Run: `cd personal_apps && python app.py`, log in, visit `/gym`.

Check:
- Page loads with the new dark/lime look (top nav on a wide window, bottom tab bar under 860px width).
- No import card anywhere on the page.
- Exercise catalog is grouped into muscle-group sections (plus "Sonstige" if any exercise has no/legacy muscle group), each showing a count.
- With no active session: start-workout form shows. Start one, confirm it redirects into `session_detail` and the dashboard now shows the active-session hero tile with a live-ticking elapsed time when you go back to `/gym`.
- Deleting a past session / template / exercise (native `confirm()` dialogs) still works.
- `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/gym/import` (while logged in) returns `404` — the route is gone.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/templates/gym/dashboard.html personal_apps/features/gym/routes.py
git commit -m "feat(gym): redesign dashboard, drop retired text-import feature

New dark/lime dashboard with muscle-group-grouped exercise catalog.
Also removes the Strong-app text-import route and its parsing helpers,
which were already confirmed retired (all historical data was imported
once, on the VPS)."
```

---

### Task 3: Active workout (session_detail) redesign

**Files:**
- Modify: `personal_apps/templates/gym/session_detail.html` (full rewrite)

**Interfaces:**
- Consumes: `gym.css`, `gym.js` (`GymChart.renderProgressChart`), `_nav.html` — from Task 1.
- Produces: nothing consumed by later tasks.

This is the highest-risk task: the drag-reorder / AJAX-partial-refresh / rest-timer / progress-modal JavaScript is complex and already works correctly. Every id and class listed in Global Constraints as "JS-bound" is kept **exactly as-is** below — only their CSS (now in `gym.css`, not touched here) and, for the rest timer, their position in the markup changes.

- [ ] **Step 1: Rewrite `session_detail.html`**

Replace the full contents of `personal_apps/templates/gym/session_detail.html` with:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ session.name or 'Workout' }} · Gym Tracker</title>
    <link rel="manifest" href="/static/manifest.json">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="apple-touch-icon" href="/static/gym/icons/icon-192.png">
    <meta name="theme-color" content="#0a0a0a">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='gym/gym.css') }}">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <script src="{{ url_for('static', filename='gym/gym.js') }}"></script>
</head>
<body>

<div class="modal-overlay hidden" id="progress-modal">
    <div class="modal-box">
        <div class="modal-header">
            <h2 id="progress-modal-title">Fortschritt</h2>
            <button type="button" class="btn btn-ghost btn-sm" id="progress-modal-close">✕</button>
        </div>
        <div class="modal-body" id="progress-modal-body"></div>
    </div>
</div>

{% include 'gym/_nav.html' %}

<div class="gym-page-wrap">
    <div class="session-header">
        <div>
            <h1>{{ session.name or 'Workout' }}</h1>
            <span class="badge {{ 'badge-active' if not session.finished_at else 'badge-done' }}">
                {{ 'Aktiv' if not session.finished_at else 'Beendet' }}
            </span>
            {% if session.finished_at %}
            <a href="{{ url_for('gym.gym_session_summary', session_id=session.id) }}" class="btn btn-ghost btn-sm" style="margin-left:8px">📊 Zusammenfassung</a>
            {% endif %}
        </div>
        {% if session.finished_at %}
        <div class="duration">{{ session.finished_at - session.started_at }}</div>
        {% else %}
        <div class="duration" id="session-duration" data-started="{{ session.started_at.isoformat() }}">--:--:--</div>
        {% endif %}
    </div>

    {% if not session.finished_at %}
    <div class="card">
        <div class="card-header"><h2>Benachrichtigungen</h2></div>
        <div class="notify-row" id="notify-row">
            <span>Erhalte eine Push-Benachrichtigung, wenn deine Pause vorbei ist (installiere die App zuerst über "Zum Home-Bildschirm").</span>
            <button type="button" class="btn btn-ghost btn-sm" id="notify-enable-btn">Aktivieren</button>
        </div>
    </div>
    {% endif %}

    <div id="exercise-cards" class="{{ 'read-only' if session.finished_at else '' }}">
    {% for se in visible_exercises %}
    {% set completed_count = se.sets|selectattr('completed')|list|length %}
    {% set total_count = se.sets|length %}
    {% set all_done = total_count > 0 and completed_count == total_count %}
    {% set resting_set = se.sets|selectattr('id', 'equalto', session.resting_set_id)|list|first if session.resting_set_id else none %}
    <div class="card exercise-card {{ 'collapsed' if all_done else '' }}" data-se-id="{{ se.id }}">
        <div class="card-header">
            <div class="card-header-title-row">
                <div class="card-title-area">
                    <h2>{{ se.exercise.name }}</h2>
                    {% if total_count %}
                    <span class="progress-badge {{ 'all-done' if all_done else '' }}">{{ completed_count }}/{{ total_count }}</span>
                    {% endif %}
                </div>
                <button type="button" class="progress-open-btn" data-exercise-id="{{ se.exercise_id }}" data-position="{{ se.position }}" title="Fortschritt anzeigen">📊</button>
            </div>
            {% if session.finished_at and (se.replaces or se.replaced_by) %}
            <div class="replace-note">
                {% if se.replaces %}🔁 Ersetzt: {{ se.replaces.exercise.name }}{% endif %}
                {% if se.replaces and se.replaced_by %}<br>{% endif %}
                {% if se.replaced_by %}🔁 Ersetzt durch: {{ se.replaced_by.exercise.name }}{% endif %}
            </div>
            {% endif %}
            {% if not session.finished_at %}
            <form method="post" action="{{ url_for('gym.gym_update_session_exercise_rest', session_exercise_id=se.id) }}" class="rest-form" title="Pause in Sekunden -- speichert automatisch">
                <span class="unit">⏱</span>
                <input type="number" name="rest_seconds" min="0" class="num-input-sm" value="{{ se.rest_seconds if se.rest_seconds is not none else '' }}">
                <span class="unit">s</span>
            </form>
            {% endif %}
        </div>
        <div class="card-body">
            {% if se.sets %}
            {% if not session.finished_at and total_count > completed_count %}
            <div class="pending-hint">{{ total_count - completed_count }} Satz{{ 'e' if total_count - completed_count != 1 else '' }} aus letztem Mal -- Werte anpassen und antippen zum Bestätigen</div>
            {% endif %}
            <div class="sets-list">
                {% for s in se.sets %}
                <div class="set-row {{ 'set-done' if s.completed else 'set-pending' }}">
                    <span class="set-index">{{ loop.index }}</span>
                    {% if not session.finished_at %}
                    <form method="post" action="{{ url_for('gym.gym_toggle_set_complete', set_id=s.id) }}" class="set-edit-form">
                        <input type="number" name="weight" step="0.5" min="0" class="num-input-sm" value="{{ s.weight }}">
                        <span class="unit">kg ×</span>
                        <input type="number" name="reps" min="0" class="num-input-sm" value="{{ s.reps }}">
                        <button type="submit" class="set-check {{ 'checked' if s.completed else '' }}" title="{{ 'Erledigt -- antippen zum Zurücksetzen' if s.completed else 'Werte speichern & als erledigt markieren (startet die Pause)' }}">{{ '✓' if s.completed else '' }}</button>
                    </form>
                    <form method="post" action="{{ url_for('gym.gym_delete_set', set_id=s.id) }}">
                        <button type="submit" class="btn btn-ghost icon-btn">✕</button>
                    </form>
                    {% else %}
                    <span class="set-value">{{ s.weight }} kg × {{ s.reps }}</span>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty">Noch keine Sätze protokolliert.</div>
            {% endif %}

            {% if resting_set and not session.finished_at %}
            <div class="rest-bar">
                <div class="rest-bar-top"><span>Pause</span><span class="rest-bar-label" id="rest-bar-label">--:--</span></div>
                <div class="rest-bar-track"><div class="rest-bar-fill" id="rest-fill" data-rest-ends="{{ session.rest_ends_at.isoformat() }}" data-rest-total="{{ se.rest_seconds or se.exercise.default_rest_seconds or 0 }}"></div></div>
            </div>
            {% endif %}

            {% if not session.finished_at %}
            {% set suggestion = suggestions.get(se.id) %}
            {% if se.id in stagnation_counts %}
            <div class="stagnation-note">💡 {{ stagnation_counts[se.id] }} Workouts ohne neuen e1RM-PR — mehr Gewicht oder Wdh. versuchen (progressive overload)</div>
            {% endif %}
            <form method="post" action="{{ url_for('gym.gym_add_set', session_exercise_id=se.id) }}">
                <div class="form-row">
                    <div class="form-group">
                        <label>Gewicht (kg)</label>
                        <input type="number" name="weight" step="0.5" min="0" class="num-input" required
                               value="{{ suggestion.weight if suggestion else '' }}">
                    </div>
                    <div class="form-group">
                        <label>Wdh.</label>
                        <input type="number" name="reps" min="0" class="num-input" required
                               value="{{ suggestion.reps if suggestion else '' }}">
                    </div>
                    <button type="submit" class="btn btn-primary">Satz hinzufügen</button>
                </div>
            </form>
            {% if suggestion and not se.sets %}
            <div class="empty" style="padding-top:8px">Letzte Leistung: {{ suggestion.weight }} kg × {{ suggestion.reps }}</div>
            {% endif %}
            <details class="replace-details">
                <summary class="btn btn-ghost btn-sm">🔁 Übung ersetzen</summary>
                <form method="post" action="{{ url_for('gym.gym_replace_session_exercise', session_exercise_id=se.id) }}" style="margin-top:8px">
                    <div class="form-row">
                        <div class="form-group grow">
                            <label>Ersatzübung</label>
                            <select name="exercise_id">
                                <option value="">— Neue Übung —</option>
                                {% for e in exercises if e.muscle_group == se.exercise.muscle_group and e.id != se.exercise_id %}
                                <option value="{{ e.id }}">{{ e.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group grow">
                            <label>Name der neuen Übung</label>
                            <input type="text" name="new_exercise_name" placeholder="z.B. Kabelzug">
                        </div>
                        <button type="submit" class="btn btn-primary btn-sm">Ersetzen</button>
                    </div>
                </form>
            </details>
            <form method="post" action="{{ url_for('gym.gym_delete_session_exercise', session_exercise_id=se.id) }}" data-confirm="Übung aus Workout entfernen?" style="margin-top:12px">
                <button type="submit" class="btn btn-ghost btn-sm">Übung entfernen</button>
            </form>
            {% endif %}
        </div>
    </div>
    {% endfor %}
    </div>

    {% if not session.finished_at %}
    <div class="card">
        <div class="card-header"><h2>Übung hinzufügen</h2></div>
        <div class="card-body">
            <form method="post" action="{{ url_for('gym.gym_add_session_exercise', session_id=session.id) }}" id="add-exercise-form">
                <div class="form-row">
                    <div class="form-group grow">
                        <label>Übung</label>
                        <select name="exercise_id" id="exercise-select">
                            <option value="">— Neue Übung —</option>
                            {% for e in exercises %}
                            <option value="{{ e.id }}">{{ e.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="form-group grow" id="new-exercise-fields">
                        <label>Name der neuen Übung</label>
                        <input type="text" name="new_exercise_name" placeholder="z.B. Kniebeuge">
                    </div>
                    <div class="form-group grow" id="new-exercise-muscle-group">
                        <label>Muskelgruppe</label>
                        <select name="muscle_group">
                            <option value="">— optional —</option>
                            {% for mg in muscle_groups %}
                            <option value="{{ mg }}">{{ mg }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">Hinzufügen</button>
                </div>
            </form>
        </div>
    </div>

    <div class="actions-row">
        <form method="post" action="{{ url_for('gym.gym_finish_session', session_id=session.id) }}" onsubmit="return confirm('Workout beenden?')">
            <button type="submit" class="btn btn-primary">Workout beenden</button>
        </form>
    </div>
    {% endif %}

    <div class="card">
        <div class="card-header"><h2>Als Vorlage speichern</h2></div>
        <div class="card-body">
            <form method="post" action="{{ url_for('gym.gym_save_as_template', session_id=session.id) }}">
                <div class="form-row">
                    <div class="form-group grow">
                        <label>Name der Vorlage</label>
                        <input type="text" name="template_name" placeholder="z.B. Push Day" required>
                    </div>
                    <button type="submit" class="btn btn-ghost">Speichern</button>
                </div>
            </form>
        </div>
    </div>
</div>

<script>
function pad(n) { return String(n).padStart(2, '0'); }

const SESSION_FINISHED = {{ 'true' if session.finished_at else 'false' }};

{% if not session.finished_at %}
const startedAt = new Date(document.getElementById('session-duration').dataset.started + 'Z');
function tickDuration() {
    const diff = Math.max(0, Date.now() - startedAt.getTime());
    const totalSec = Math.floor(diff / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    document.getElementById('session-duration').textContent = `${pad(h)}:${pad(m)}:${pad(s)}`;
}
tickDuration();
setInterval(tickDuration, 1000);
{% endif %}

// Re-run after every AJAX refresh of #exercise-cards (a fresh #rest-fill
// element, or none at all, may now exist), tracking the timer so old and
// new tick loops don't pile up.
let restFillTimer = null;
function startRestFillTick() {
    if (restFillTimer) clearTimeout(restFillTimer);
    const restFill = document.getElementById('rest-fill');
    if (!restFill) return;
    const restEndsAt = new Date(restFill.dataset.restEnds + 'Z');
    const restTotalSeconds = parseFloat(restFill.dataset.restTotal) || 0;
    function tick() {
        const el = document.getElementById('rest-fill');
        const label = document.getElementById('rest-bar-label');
        if (!el) return; // removed by a newer refresh
        const diff = restEndsAt.getTime() - Date.now();
        if (diff <= 0 || restTotalSeconds <= 0) {
            el.style.width = '0%';
            if (label) label.textContent = '0:00';
            return;
        }
        const pct = Math.max(0, Math.min(100, (diff / 1000 / restTotalSeconds) * 100));
        el.style.width = pct + '%';
        if (label) {
            const remain = Math.ceil(diff / 1000);
            const m = Math.floor(remain / 60);
            const s = remain % 60;
            label.textContent = `${m}:${pad(s)}`;
        }
        restFillTimer = setTimeout(tick, 1000);
    }
    tick();
}
startRestFillTick();

const exerciseSelect = document.getElementById('exercise-select');
const newExerciseFields = document.getElementById('new-exercise-fields');
const newExerciseMuscleGroup = document.getElementById('new-exercise-muscle-group');
if (exerciseSelect) {
    function syncNewExerciseFields() {
        const display = exerciseSelect.value ? 'none' : 'flex';
        newExerciseFields.style.display = display;
        if (newExerciseMuscleGroup) newExerciseMuscleGroup.style.display = display;
    }
    exerciseSelect.addEventListener('change', syncNewExerciseFields);
    syncNewExerciseFields();
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

const notifyBtn = document.getElementById('notify-enable-btn');
if (notifyBtn) {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        const reason = window.isSecureContext
            ? 'Dein Browser unterstützt keine Push-Benachrichtigungen.'
            : 'Push-Benachrichtigungen brauchen eine sichere Verbindung (HTTPS). Über die lokale Netzwerk-Adresse (http://...) geht das nicht -- erst nach dem Deployment mit echtem HTTPS.';
        document.getElementById('notify-row').innerHTML = `<span>${reason}</span>`;
    } else {
        notifyBtn.addEventListener('click', async () => {
            try {
                const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/gym/' });
                const permission = await Notification.requestPermission();
                if (permission !== 'granted') {
                    notifyBtn.textContent = 'Abgelehnt';
                    return;
                }
                const subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array('{{ vapid_public_key or "" }}'),
                });
                await fetch('{{ url_for("gym.gym_push_subscribe") }}', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(subscription.toJSON()),
                });
                notifyBtn.textContent = 'Aktiviert ✓';
                notifyBtn.disabled = true;
            } catch (err) {
                notifyBtn.textContent = 'Fehler';
                console.error('Push subscribe failed', err);
            }
        });
    }
}

(function setupDragReorder() {
    const DRAG_THRESHOLD = 8;
    const SCROLL_EDGE_ZONE = 80;
    const SCROLL_MAX_SPEED = 16;
    let dragCard = null;
    let dragGhost = null;
    let titleArea = null;
    let activePointerId = null;
    let startX = 0;
    let startY = 0;
    let lastClientY = 0;
    let dragStarted = false;
    let dragGrabOffsetY = 0;
    let dragGhostBaseTop = 0;
    let dragGhostBaseClientY = 0;
    let openIdsBeforeDrag = null;
    let autoScrollRAF = null;

    function beginDrag() {
        dragStarted = true;
        try { titleArea.setPointerCapture(activePointerId); } catch (err) {}

        const container = document.getElementById('exercise-cards');
        if (container) {
            openIdsBeforeDrag = new Set();
            container.querySelectorAll('.exercise-card').forEach((c) => {
                if (!c.classList.contains('collapsed')) openIdsBeforeDrag.add(c.dataset.seId);
                c.classList.add('collapsed');
            });
        }

        const rect = dragCard.getBoundingClientRect();
        dragGrabOffsetY = lastClientY - rect.top;
        dragCard.classList.add('dragging');
        dragCard.style.visibility = 'hidden';

        dragGhost = dragCard.cloneNode(true);
        dragGhost.removeAttribute('id');
        dragGhost.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
        dragGhost.classList.add('drag-ghost');
        dragGhost.setAttribute('inert', '');
        dragGhost.style.position = 'fixed';
        dragGhost.style.left = rect.left + 'px';
        dragGhost.style.width = rect.width + 'px';
        dragGhostBaseClientY = lastClientY;
        dragGhostBaseTop = lastClientY - dragGrabOffsetY;
        dragGhost.style.top = dragGhostBaseTop + 'px';
        dragGhost.style.margin = '0';
        dragGhost.style.pointerEvents = 'none';
        dragGhost.style.visibility = 'visible';
        document.body.appendChild(dragGhost);

        if (!autoScrollRAF) autoScrollRAF = requestAnimationFrame(autoScrollTick);
    }

    function resetDragState() {
        if (autoScrollRAF) {
            cancelAnimationFrame(autoScrollRAF);
            autoScrollRAF = null;
        }
        if (dragGhost) {
            dragGhost.remove();
            dragGhost = null;
        }
        if (dragCard) {
            dragCard.classList.remove('dragging');
            dragCard.style.visibility = '';
        }
        if (titleArea && activePointerId !== null) {
            try { titleArea.releasePointerCapture(activePointerId); } catch (err) {}
        }
        if (openIdsBeforeDrag) {
            const container = document.getElementById('exercise-cards');
            if (container) {
                container.querySelectorAll('.exercise-card').forEach((c) => {
                    if (openIdsBeforeDrag.has(c.dataset.seId)) c.classList.remove('collapsed');
                });
            }
        }
        openIdsBeforeDrag = null;
        dragCard = null;
        titleArea = null;
        activePointerId = null;
        dragStarted = false;
    }

    function updateDragPosition(clientY) {
        const container = document.getElementById('exercise-cards');
        if (!container || !dragGhost) return;

        dragGhost.style.transform = `translateY(${clientY - dragGhostBaseClientY}px)`;

        const dragRect = dragGhost.getBoundingClientRect();
        const dragCenter = dragRect.top + dragRect.height / 2;
        const cards = Array.from(container.children);
        const dragIndex = cards.indexOf(dragCard);

        const nextSib = cards[dragIndex + 1];
        if (nextSib) {
            const nextRect = nextSib.getBoundingClientRect();
            if (dragCenter > nextRect.top + nextRect.height / 2) {
                container.insertBefore(dragCard, nextSib.nextElementSibling);
                return;
            }
        }
        const prevSib = cards[dragIndex - 1];
        if (prevSib) {
            const prevRect = prevSib.getBoundingClientRect();
            if (dragCenter < prevRect.top + prevRect.height / 2) {
                container.insertBefore(dragCard, prevSib);
            }
        }
    }

    function autoScrollTick() {
        if (!dragStarted || !dragCard) {
            autoScrollRAF = null;
            return;
        }
        const vh = window.innerHeight;
        let delta = 0;
        if (lastClientY < SCROLL_EDGE_ZONE) {
            delta = -Math.ceil(SCROLL_MAX_SPEED * (SCROLL_EDGE_ZONE - lastClientY) / SCROLL_EDGE_ZONE);
        } else if (lastClientY > vh - SCROLL_EDGE_ZONE) {
            delta = Math.ceil(SCROLL_MAX_SPEED * (lastClientY - (vh - SCROLL_EDGE_ZONE)) / SCROLL_EDGE_ZONE);
        }
        if (delta !== 0) {
            window.scrollBy(0, delta);
            updateDragPosition(lastClientY);
        }
        autoScrollRAF = requestAnimationFrame(autoScrollTick);
    }

    function onMove(e) {
        if (!dragCard) return;
        lastClientY = e.clientY;

        if (!dragStarted) {
            if (SESSION_FINISHED) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (Math.sqrt(dx * dx + dy * dy) < DRAG_THRESHOLD) return;
            beginDrag();
        }

        e.preventDefault();
        updateDragPosition(e.clientY);
    }

    function finish(isCancel) {
        if (!dragCard) return;
        const card = dragCard;
        const wasDragging = dragStarted;
        const container = document.getElementById('exercise-cards');
        const order = wasDragging && container ? Array.from(container.children).map((c) => c.dataset.seId) : null;
        resetDragState();

        if (wasDragging) {
            if (order && order.length) {
                fetch('{{ url_for("gym.gym_reorder_session_exercises", session_id=session.id) }}', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order: order }),
                    credentials: 'same-origin',
                })
                    .then((r) => r.text())
                    .then(refreshExerciseCards);
            }
        } else if (!isCancel) {
            card.classList.toggle('collapsed');
        }
    }

    document.addEventListener('pointerdown', (e) => {
        const area = e.target.closest && e.target.closest('.card-title-area');
        if (!area) return;
        dragCard = area.closest('.exercise-card');
        titleArea = area;
        activePointerId = e.pointerId;
        startX = e.clientX;
        startY = e.clientY;
        lastClientY = e.clientY;
        dragStarted = false;
        e.preventDefault();
    });
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', () => finish(false));
    document.addEventListener('pointercancel', () => finish(true));
})();

function refreshExerciseCards(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const newCards = doc.getElementById('exercise-cards');
    const oldCards = document.getElementById('exercise-cards');
    if (newCards && oldCards) {
        const collapsedIds = new Set();
        const openIds = new Set();
        oldCards.querySelectorAll('.exercise-card').forEach((c) => {
            (c.classList.contains('collapsed') ? collapsedIds : openIds).add(c.dataset.seId);
        });
        oldCards.replaceWith(newCards);
        newCards.querySelectorAll('.exercise-card').forEach((c) => {
            if (collapsedIds.has(c.dataset.seId)) c.classList.add('collapsed');
            else if (openIds.has(c.dataset.seId)) c.classList.remove('collapsed');
        });
    }
    startRestFillTick();
}

document.addEventListener('submit', (e) => {
    const form = e.target;
    const container = document.getElementById('exercise-cards');
    if (!container || form.tagName !== 'FORM' || !container.contains(form)) return;
    e.preventDefault();
    if (form.dataset.confirm && !confirm(form.dataset.confirm)) return;
    fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin' })
        .then((r) => r.text())
        .then(refreshExerciseCards);
});

document.addEventListener('change', (e) => {
    const input = e.target;
    if (input.name !== 'rest_seconds') return;
    const form = input.closest('form');
    if (form && form.requestSubmit) form.requestSubmit();
});

// Quick per-exercise progress modal -- PRs + recent history without leaving
// the workout. Fetches JSON (not HTML) so nothing needs script-execution
// tricks for content injected via innerHTML. Chart rendering delegates to
// the shared GymChart helper (gym.js) so this modal's chart and the full
// exercise-detail page's chart never drift into two different looks.
(function setupProgressModal() {
    const modal = document.getElementById('progress-modal');
    const title = document.getElementById('progress-modal-title');
    const body = document.getElementById('progress-modal-body');
    if (!modal) return;

    const esc = window.GymUtils.escapeHtml;
    let modalChart = null;

    function render(data) {
        let html = '';
        if (data.pr_max_weight) {
            const volLabel = data.is_unilateral ? 'Bestes Satzvolumen (beidseitig)' : 'Bestes Satzvolumen';
            const volReps = data.is_unilateral ? `${esc(data.pr_max_volume.reps)} je Seite` : esc(data.pr_max_volume.reps);
            html += `<div class="pr-grid">
                <div class="pr-card"><div class="label">Max. Gewicht</div><div class="val">${esc(data.pr_max_weight.weight)} kg</div><div class="sub">${esc(data.pr_max_weight.reps)} Wdh. &middot; ${esc(data.pr_max_weight.date)}</div></div>
                <div class="pr-card"><div class="label">${volLabel}</div><div class="val">${esc(data.pr_max_volume.volume)} kg</div><div class="sub">${esc(data.pr_max_volume.weight)} kg &times; ${volReps} &middot; ${esc(data.pr_max_volume.date)}</div></div>
            </div>`;
        }
        if (data.position) {
            html += `<div class="modal-position-note">Basierend auf Position ${esc(data.position)} im Workout (gleiche Reihenfolge wie heute)</div>`;
        }
        if (data.chart_labels && data.chart_labels.length) {
            html += '<div class="modal-chart-wrap"><canvas id="modal-chart"></canvas></div>';
        } else {
            html += '<div class="empty">Noch keine erledigten Sätze für diese Übung.</div>';
        }
        html += `<div style="margin-top:14px"><a href="/gym/exercises/${data.exercise_id}" class="btn btn-ghost btn-sm">Vollständige Ansicht &amp; Diagramm →</a></div>`;
        body.innerHTML = html;

        if (modalChart) {
            modalChart.destroy();
            modalChart = null;
        }
        if (data.chart_labels && data.chart_labels.length) {
            modalChart = GymChart.renderProgressChart(document.getElementById('modal-chart'), {
                labels: data.chart_labels,
                weights: data.chart_weights,
                minWeights: data.chart_min_weights,
                volumes: data.chart_volumes,
            });
        }
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest && e.target.closest('.progress-open-btn');
        if (btn) {
            const exerciseId = btn.dataset.exerciseId;
            const position = btn.dataset.position;
            title.textContent = 'Fortschritt';
            body.innerHTML = '<div class="empty">Lädt…</div>';
            modal.classList.remove('hidden');
            fetch(`/gym/exercises/${exerciseId}/progress.json?position=${encodeURIComponent(position)}`, { credentials: 'same-origin' })
                .then((r) => r.json())
                .then((data) => { title.textContent = data.name; render(data); })
                .catch(() => { body.innerHTML = '<div class="empty">Fehler beim Laden.</div>'; });
            return;
        }
        if (e.target.id === 'progress-modal-close' || e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') modal.classList.add('hidden');
    });
})();
</script>

</body>
</html>
```

- [ ] **Step 2: Verify — this is the highest-risk task, check everything**

Run: `cd personal_apps && python app.py`, log in, start a workout from `/gym` (or open an existing active one).

Check, in order:
1. Elapsed session time ticks live.
2. Add a set (weight+reps) — appears in the dense list.
3. Tap the checkmark on a pending set — it marks done, a `.rest-bar` appears under that exercise's sets showing a label (`m:ss`) counting down alongside a shrinking lime bar, and the page does **not** reload/scroll (AJAX refresh).
4. Wait for (or shrink) the rest period — bar reaches empty, label shows `0:00`.
5. Edit weight/reps on a set and re-tap its checkmark to toggle it back to pending, then done again — values persist.
6. Delete a set (✕) — row disappears, no reload.
7. Drag an exercise card by its title to reorder — order persists after the AJAX refresh (reload the page to confirm it's saved server-side too).
8. Tap a card's title without dragging — it collapses/expands.
9. Add a new exercise via the bottom form.
10. Open "Übung ersetzen" on a card, replace with another exercise of the same muscle group — original is preserved in history, substitute takes over the slot.
11. Tap the 📊 icon on an exercise card — progress modal opens, shows PR cards (if any history exists) and a best/worst-band chart (lime fill, dashed grey worst-line, grey volume line) rendered via `GymChart`.
12. Finish the workout (native `confirm()`), land on the summary page (Task 4 territory — just confirm the redirect works for now).
13. Open a **finished** (read-only) session — sets are read-only text, no drag/replace/add-set controls, tapping a card title still collapses/expands it.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/templates/gym/session_detail.html
git commit -m "feat(gym): redesign active-workout page (dense set table, card-level rest bar)

Restyles the active-workout screen to the new dark/lime dense-table look
and moves the rest timer from a per-row background overlay to a labeled
bar under the exercise's sets. All drag-reorder/AJAX-refresh/push-notify
JS logic is unchanged -- same ids/classes, only presentation and the rest
timer's markup position changed. Progress-modal chart now goes through
the shared GymChart helper instead of a second inline Chart.js config."
```

---

### Task 4: Session summary redesign (hero PR cards)

**Files:**
- Modify: `personal_apps/templates/gym/session_summary.html` (full rewrite)

**Interfaces:**
- Consumes: `gym.css`, `_nav.html` — from Task 1. `exercises` list items' `is_weight_pr`/`is_volume_pr`/`is_e1rm_pr`/`session_best_weight`/`session_volume`/`session_best_e1rm`/`name` fields — from `_session_summary_data()` in routes.py (unchanged).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Rewrite `session_summary.html`**

Replace the full contents of `personal_apps/templates/gym/session_summary.html` with:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zusammenfassung · {{ session.name or 'Workout' }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='gym/gym.css') }}">
    <meta name="theme-color" content="#0a0a0a">
</head>
<body>

{% include 'gym/_nav.html' %}

<div class="gym-page-wrap" style="max-width:720px">
    <h1>{{ session.name or 'Workout' }}</h1>
    <p style="color:var(--gym-muted);font-size:14px;margin-bottom:24px">{{ session.started_at.strftime('%d.%m.%Y') }} &middot; Zusammenfassung</p>

    {% if request.args.get('just_finished') and session.template %}
    <div class="card" style="border-color:var(--gym-lime)">
        <div class="card-body" style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap">
            <span>Vorlage <strong>{{ session.template.name }}</strong> mit dieser Übungsliste &amp; Reihenfolge aktualisieren?</span>
            <form method="post" action="{{ url_for('gym.gym_update_template', session_id=session.id) }}">
                <button type="submit" class="btn btn-primary btn-sm">Vorlage aktualisieren</button>
            </form>
        </div>
    </div>
    {% endif %}

    {% if pr_count %}
    <div class="gym-pr-hero">
        {% for ex in exercises if ex.is_weight_pr or ex.is_volume_pr or ex.is_e1rm_pr %}
        <div class="gym-pr-hero-card">
            <div class="name">{{ ex.name }}</div>
            {% if ex.is_weight_pr %}
            <div class="headline">{{ ex.session_best_weight }} kg</div>
            <div class="sub">🏆 Gewichts-PR</div>
            {% elif ex.is_volume_pr %}
            <div class="headline">{{ ex.session_volume }} kg</div>
            <div class="sub">🏆 Volumen-PR</div>
            {% else %}
            <div class="headline">~{{ ex.session_best_e1rm }} kg</div>
            <div class="sub">🏆 e1RM-PR</div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <div class="period-grid">
        <div class="period-card">
            <div class="label">Dauer</div>
            <div class="rate-val">{{ session.finished_at - session.started_at if session.finished_at else '--' }}</div>
        </div>
        <div class="period-card">
            <div class="label">Gesamtvolumen</div>
            <div class="rate-val">{{ total_volume }} kg</div>
            {% if total_volume_delta_pct is not none %}
            <div class="sub {{ 'positive' if total_volume_delta_pct >= 0 else 'negative' }}">{{ '%+d'|format(total_volume_delta_pct) }}% ggü. Schnitt</div>
            {% endif %}
        </div>
        <div class="period-card">
            <div class="label">Sätze</div>
            <div class="rate-val">{{ total_sets }}</div>
        </div>
        <div class="period-card">
            <div class="label">Neue PRs</div>
            <div class="rate-val" style="{{ 'color:var(--gym-lime)' if pr_count else '' }}">{{ pr_count }}</div>
        </div>
    </div>

    <div class="card">
        <div class="card-header"><h2>Nach Übung</h2></div>
        {% if exercises %}
        <div>
            {% for ex in exercises %}
            <div class="summary-exercise">
                <div class="name">{{ ex.name }}</div>
                <div class="stats">
                    <span><strong>{{ ex.session_volume }} kg</strong> Volumen</span>
                    <span><strong>{{ ex.session_best_weight }} kg</strong> bestes Gewicht</span>
                    <span><strong>~{{ ex.session_best_e1rm }} kg</strong> e1RM</span>
                </div>
                {% if ex.is_weight_pr or ex.is_volume_pr or ex.is_e1rm_pr %}
                <div class="pr-badges">
                    {% if ex.is_weight_pr %}<span class="pr-badge">🏆 Gewicht</span>{% endif %}
                    {% if ex.is_volume_pr %}<span class="pr-badge">🏆 Volumen</span>{% endif %}
                    {% if ex.is_e1rm_pr %}<span class="pr-badge">🏆 1RM</span>{% endif %}
                </div>
                {% elif ex.has_history %}
                <div class="summary-delta {{ 'positive' if ex.volume_delta_pct is not none and ex.volume_delta_pct >= 0 else 'negative' }}">
                    {{ '%+d'|format(ex.volume_delta_pct) if ex.volume_delta_pct is not none else '±0' }}% Volumen ggü. Schnitt ({{ ex.avg_volume }} kg)
                </div>
                {% else %}
                <div class="summary-delta">Erste Aufzeichnung für diese Übung</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="empty">Keine erledigten Sätze in diesem Workout.</div>
        {% endif %}
    </div>

    <div class="actions-row">
        <a href="{{ url_for('gym.session_detail', session_id=session.id) }}" class="btn btn-ghost">Workout-Details ansehen</a>
        <a href="{{ url_for('gym.gym_dashboard') }}" class="btn btn-primary">Zur Übersicht</a>
        <form method="post" action="{{ url_for('gym.gym_delete_session', session_id=session.id) }}" onsubmit="return confirm('Workout unwiderruflich löschen?')" style="margin-left:auto">
            <button type="submit" class="btn btn-danger">Workout löschen</button>
        </form>
    </div>
</div>

</body>
</html>
```

- [ ] **Step 2: Verify**

Finish a workout that includes at least one PR (or manually navigate to `/gym/session/<id>/summary` for a past session that has one) — confirm the lime gradient hero cards render above the stat grid, with the right headline metric per PR type. Then check a session summary with **zero** PRs — confirm the hero block is entirely absent (no empty card, straight to the stat grid) and `pr_count` shows `0`.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/templates/gym/session_summary.html
git commit -m "feat(gym): add hero PR cards to session summary

New dark/lime look for the post-workout summary, with lime-gradient hero
cards for each PR'd exercise (weight > volume > e1RM priority for which
metric headlines the card) shown above the existing stat grid. No hero
block at all when there were no PRs this session."
```

---

### Task 5: Exercise detail redesign (best/worst band chart)

**Files:**
- Modify: `personal_apps/templates/gym/exercise_detail.html` (full rewrite)

**Interfaces:**
- Consumes: `gym.css`, `gym.js` (`GymChart.renderProgressChart`), `_nav.html` — from Task 1.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Rewrite `exercise_detail.html`**

Replace the full contents of `personal_apps/templates/gym/exercise_detail.html` with:

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ exercise.name }} · Gym Tracker</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='gym/gym.css') }}">
    <meta name="theme-color" content="#0a0a0a">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <script src="{{ url_for('static', filename='gym/gym.js') }}"></script>
</head>
<body>

{% include 'gym/_nav.html' %}

<div class="gym-page-wrap">
    <h1>{{ exercise.name }}</h1>
    {% if request.args.get('name_taken') %}
    <div class="card" style="border-color:var(--gym-red)">
        <div class="card-body">
            <span>Name nicht geändert -- es gibt bereits eine Übung mit diesem Namen. Andere Änderungen wurden trotzdem gespeichert.</span>
        </div>
    </div>
    {% endif %}
    <form method="post" action="{{ url_for('gym.gym_update_exercise', exercise_id=exercise.id) }}" style="margin-bottom:24px">
        <div class="form-row">
            <div class="form-group grow">
                <label>Name</label>
                <input type="text" name="name" value="{{ exercise.name }}" required>
            </div>
            <div class="form-group grow">
                <label>Muskelgruppe</label>
                <select name="muscle_group">
                    <option value="">— keine —</option>
                    {% for mg in muscle_groups %}
                    <option value="{{ mg }}" {{ 'selected' if exercise.muscle_group == mg else '' }}>{{ mg }}</option>
                    {% endfor %}
                    {% if exercise.muscle_group and exercise.muscle_group not in muscle_groups %}
                    <option value="{{ exercise.muscle_group }}" selected>{{ exercise.muscle_group }} (alt)</option>
                    {% endif %}
                </select>
            </div>
            <div class="form-group">
                <label>Standard-Pause (Sek.)</label>
                <input type="number" name="default_rest_seconds" min="0" class="num-input" value="{{ exercise.default_rest_seconds if exercise.default_rest_seconds is not none else '' }}" placeholder="90">
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" name="is_unilateral" style="width:auto;margin-right:4px" {{ 'checked' if exercise.is_unilateral else '' }}>
                    Einseitig (pro Seite)
                </label>
            </div>
            <button type="submit" class="btn btn-ghost btn-sm">Speichern</button>
        </div>
    </form>

    {% if available_positions|length > 1 %}
    <div class="card">
        <div class="card-body" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <span style="font-size:12px;color:var(--gym-muted)">Diese Übung wurde an unterschiedlichen Positionen im Workout gemacht (Reihenfolge beeinflusst die Werte) &middot; Nach Position filtern:</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
                <a href="{{ url_for('gym.exercise_detail', exercise_id=exercise.id) }}" class="gym-pill {{ 'active' if selected_position is none else '' }}">Alle</a>
                {% for p in available_positions %}
                <a href="{{ url_for('gym.exercise_detail', exercise_id=exercise.id, position=p) }}" class="gym-pill {{ 'active' if selected_position == p else '' }}">Position {{ p }}</a>
                {% endfor %}
            </div>
        </div>
    </div>
    {% endif %}

    {% if rows %}
    <div class="period-grid">
        <div class="period-card">
            <div class="label">Max. Gewicht</div>
            <div class="rate-val">{{ pr_max_weight.weight }} kg</div>
            <div class="sub">{{ pr_max_weight.reps }} Wdh. · {{ pr_max_weight.date.strftime('%d.%m.%Y') }}</div>
        </div>
        <div class="period-card">
            <div class="label">Bestes Satzvolumen{{ ' (beidseitig)' if exercise.is_unilateral else '' }}</div>
            <div class="rate-val">{{ pr_max_volume.volume }} kg</div>
            <div class="sub">{{ pr_max_volume.weight }} kg × {{ pr_max_volume.reps }}{{ ' je Seite' if exercise.is_unilateral else '' }} · {{ pr_max_volume.date.strftime('%d.%m.%Y') }}</div>
        </div>
    </div>

    <div class="card">
        <div class="card-header"><h2>Verlauf</h2></div>
        <div class="chart-wrap">
            <canvas id="progressChart"></canvas>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <h2>Sätze pro Workout</h2>
            {% if exercise.is_unilateral %}
            <span style="font-size:12px;color:var(--gym-muted)">Einseitig: Gewicht/Wdh. je Seite geloggt, Volumen zählt beide Seiten (×2)</span>
            {% endif %}
        </div>
        <div class="card-body">
            <table class="sets">
                <thead><tr><th>Datum</th><th>Pos.</th><th>Sätze</th><th>Volumen</th></tr></thead>
                <tbody>
                    {% for r in rows %}
                    <tr>
                        <td>{{ r.session.started_at.strftime('%d.%m.%Y') }}</td>
                        <td>{{ r.position }}</td>
                        <td>{{ r.sets_display }}</td>
                        <td class="num">{{ r.volume }} kg</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% else %}
    <div class="card">
        <div class="empty">Noch keine Sätze für diese Übung protokolliert.</div>
    </div>
    {% endif %}
</div>

{% if rows %}
<script>
GymChart.renderProgressChart(document.getElementById('progressChart'), {
    labels: {{ chart_labels | tojson }},
    weights: {{ chart_weights | tojson }},
    minWeights: {{ chart_min_weights | tojson }},
    volumes: {{ chart_volumes | tojson }},
});
</script>
{% endif %}

</body>
</html>
```

- [ ] **Step 2: Verify**

Visit `/gym/exercises/<id>` for an exercise with history — confirm:
- Chart shows a lime-filled band between best and worst weight per session, plus a thin grey dashed volume line on the secondary axis.
- Position filter pills (if the exercise has multiple positions) switch correctly and highlight the active one.
- Editing the exercise's name/muscle-group/rest/unilateral flag and saving still works.
- An exercise with **no** history shows the empty state, no chart/table.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/templates/gym/exercise_detail.html
git commit -m "feat(gym): redesign exercise-detail page, best/worst band chart

Switches the progress chart from two separately-colored lines to a
lime-filled best/worst band (via the shared GymChart helper added in the
foundation task), and restyles the position filter as pill toggles."
```

---

### Task 6: PWA metadata polish

**Files:**
- Modify: `personal_apps/static/manifest.json`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (leaf task).

- [ ] **Step 1: Update manifest colors**

Replace the contents of `personal_apps/static/manifest.json`:

```json
{
  "name": "Gym Tracker",
  "short_name": "Gym",
  "start_url": "/gym/",
  "scope": "/gym/",
  "display": "standalone",
  "background_color": "#0a0a0a",
  "theme_color": "#0a0a0a",
  "icons": [
    {
      "src": "/static/gym/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/gym/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

(The 4 templates' `<meta name="theme-color" content="#0a0a0a">` tags were already updated to this value in Tasks 2, 3, 4, and 5 — this step just brings the PWA manifest itself in line with the same value. The existing icon PNGs are kept as-is; regenerating raster app-icon assets is out of scope for this redesign.)

- [ ] **Step 2: Verify**

`python -c "import json; json.load(open('personal_apps/static/manifest.json'))"` — must not raise (valid JSON). Then in the browser devtools Application tab (or by re-installing the PWA), confirm the manifest reports the new colors.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/static/manifest.json
git commit -m "chore(gym): match PWA manifest colors to the new dark theme"
```

---

### Task 7: Full manual verification pass

**Files:** none (verification only).

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: nothing.

- [ ] **Step 1: Run the full spec verification checklist**

Run: `cd personal_apps && python app.py`, log in at `/login`. Using the browser's device toolbar, check every item below first at **390×844** (mobile) and then at a **desktop width** (e.g. 1280px):

- **Dashboard** (`/gym`): with an active session (hero tile + live timer); without one (start form); exercise catalog grouped by muscle group with a populated group and confirm an exercise with no muscle group lands in "Sonstige"; past-sessions and templates lists render and delete correctly; bottom tab bar visible only under ~860px width, top nav only above it.
- **Active workout** (`/gym/session/<id>`): add/toggle/delete a set; rest timer bar + label count down after completing a set; stagnation pill appears for an exercise with 4+ PR-less sessions (if such data exists) or skip if none does; drag-reorder persists; replace-exercise via the inline disclosure; add-exercise form; finish workout; progress modal opens with the best/worst-band chart; a **finished** session renders read-only (no drag/edit controls).
- **Session summary** (`/gym/session/<id>/summary`): hero PR cards for a session with PRs; no hero block for a session without; stat grid and per-exercise list both correct.
- **Exercise detail** (`/gym/exercises/<id>`): best/worst band chart renders; position-filter pills switch and highlight correctly; edit form saves.
- Confirm `/gym/import` now 404s and no page has any leftover reference to it.

- [ ] **Step 2: Report results**

If every item above checks out, the redesign is complete — no commit needed for this task (verification-only). If anything fails, fix it in the relevant task's files and re-run this checklist before considering the plan done.

---

## Post-Plan Note

`.superpowers/` (the visual-companion mockups from the brainstorming session that produced this plan's design direction) was already added to the repo's root `.gitignore` before this plan was written — no action needed here.

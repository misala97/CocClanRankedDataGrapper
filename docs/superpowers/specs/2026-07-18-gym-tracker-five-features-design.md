# Gym Tracker: Skip, Edit History, Sticky-Bar Fix, Export, Reorder Lock

**Date:** 2026-07-18
**App:** `personal_apps` (Gym Tracker feature)
**Branch:** `dev_personal`
**Type:** Five independent, small-to-medium changes, bundled into one spec because they share the same models/routes/templates (`models.py`, `features/gym/routes.py`, `templates/gym/session_detail.html`, `templates/gym/dashboard.html`, `static/gym/gym.css`).

Each section below is independently implementable and independently shippable — the implementation plan may split them into separate commits/PRs, but they don't need separate specs.

---

## 1. Skip Exercise (add)

**Problem:** The existing "swap" (`gym_replace_session_exercise`) substitutes an exercise for a different one, and "delete" (`gym_delete_session_exercise`) removes it from the session entirely — which also means it vanishes from `_template_exercises_from_session` if the session is later saved/updated as a template. There's no way to say "not doing this exercise today" without either lying via swap or losing it from the template via delete.

### Data model
New column on `SessionExercise`:
```python
skipped = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
```
Migration follows the same additive pattern as the existing `d4f8b2a91c6e_add_replaces_id_to_session_exercises.py`.

### Route
One toggle route handles both skip and undo (mirrors `gym_toggle_set_complete`'s toggle pattern):
```
POST /gym/session-exercise/<int:session_exercise_id>/skip
```
- Only valid for an active (unfinished) session — 404/no-op if `session.finished_at` is set.
- **Skip (`skipped: False → True`):** delete all of this `SessionExercise`'s `sets` where `completed == False` (the pending, pre-filled-from-history suggestions). Any already-`completed` sets are left untouched — a partial exercise (e.g. 2 of 4 sets done) can still be skipped for "the rest."
- **Undo (`skipped: True → False`):** if `se.sets` is now empty, re-derive pending sets via `_last_full_performance(se.exercise_id, position=se.position)`, same call the reorder route already makes. If sets exist (the partial-completion case), leave them as-is.

### Template-safety guarantee
**No change needed** to `_template_exercises_from_session`. It already iterates `session_.exercises` and only excludes rows where `se.replaces_id is not None` (mid-workout substitutes). A skipped `SessionExercise` is neither deleted nor a substitute, so it's automatically included when the session is saved/updated as a template — satisfying "doesn't delete it in the template" by construction, not by adding new exclusion logic.

### UI (`session_detail.html`)
- New button alongside the existing "🔁 Übung ersetzen" (`<details class="replace-details">`) and "Übung entfernen" (delete form): **"⏭️ Überspringen"**, same `btn btn-ghost btn-sm` styling, posts to the skip route.
- When `se.skipped` is true: the card shows a "Übersprungen" badge (next to the existing progress badge) and the add-set form / suggestion hint is replaced with a single **"Rückgängig"** (Undo) button that posts the same toggle route. Swap and delete buttons remain available on a skipped exercise (you can still swap or remove it if you change your mind about more than just skipping).
- Goes through the existing global AJAX submit-interceptor (`refreshExerciseCards`) — no new JS plumbing needed, just a new form in the card matching the existing pattern.

---

## 2. Edit History Values (add)

**Problem:** Once `session.finished_at` is set, `session_detail.html` renders sets as plain text (`<span class="set-value">{{ s.weight }} kg × {{ s.reps }}</span>`) — no way to fix a typo after the fact.

### Route
```
POST /gym/set/<int:set_id>/update
```
- Accepts `weight` (float) and `reps` (int) form fields, same validation (`_to_float`/`_to_int`) as `gym_add_set`.
- Updates **only** `weight` and `reps` — does not touch `completed`, does not allow changing which exercise/session the set belongs to, does not add/delete sets. No `finished_at` check — this route is specifically for editing history, so it must work on finished sessions (and works on active ones too, though the active workflow already has `gym_toggle_set_complete` for that).

### UI (`session_detail.html`, finished-session branch)
Each set row gets a small pencil (✏️) icon next to the `set-value` text. Tapping it swaps the static text for two inline number inputs (weight, reps) + a "💾" save button, matching the visual weight of the existing active-session `set-edit-form` but without the checkmark/complete-toggle behavior. Submits through the existing global AJAX interceptor (the listener already checks `container.contains(form)`, not the `read-only` class, so it works without changing that gate).

---

## 3. Sticky Bottom Bar Bug (fix)

**Confirmed symptom:** past a certain scroll depth, `.gym-tabbar` stops staying pinned and scrolls away with the page content, instead of remaining fixed at the bottom of the viewport.

### What's ruled out
`.gym-tabbar` uses `position: fixed`, and its own `backdrop-filter` doesn't affect its own fixed positioning (only its descendants'). A static audit of `gym.css` and every gym template's inline styles found **no ancestor** (`body`, `html`, `.gym-page-wrap`, `.gym-nav`) with `transform`, `filter`, `backdrop-filter`, `perspective`, `will-change`, or `contain` — the classic cause of a `position: fixed` element becoming contained by an ancestor instead of the viewport. That's not what's happening here.

### Leading hypothesis (to be confirmed live, not coded blind)
`session_detail.html` is the one page that repeatedly replaces a large DOM subtree via AJAX: nearly every form inside `#exercise-cards` (add set, toggle complete, delete set, rest change, swap, delete exercise — and after this spec, skip and edit-history too) goes through a global submit interceptor that does `oldCards.replaceWith(newCards)`. Each of these swaps can change document height while the user is scrolled deep into a long exercise list. This is a known class of mobile-Safari/PWA bug (this app runs `apple-mobile-web-app-capable`) where a `position: fixed` element desyncs from the visual viewport after a DOM height change mid-scroll. This would explain why the bug is scroll-depth-dependent and most likely specific to the active-workout page, not the dashboard or history pages (which don't do this kind of frequent reflow).

### Fix approach
At implementation time, this goes through **live reproduction** (device or Chrome DevTools mobile emulation, a long exercise list, repeated AJAX swaps while scrolled near the bottom) before any fix is written — per the project's systematic-debugging discipline; the hypothesis above is a lead, not a diagnosis. Candidate fixes, in order of preference once confirmed:
1. Preserve scroll position explicitly across `replaceWith` (capture `window.scrollY` before, restore after, or use a targeted patch instead of a full subtree swap).
2. Patch only the changed child card(s) in `refreshExerciseCards` instead of replacing the entire `#exercise-cards` subtree.
3. A `visualViewport.addEventListener('resize', ...)` handler that re-asserts the bar's position after layout settles.

---

## 4. Export Training History (feature)

### Route
```
GET /gym/export?from=YYYY-MM-DD&to=YYYY-MM-DD
```
Returns a downloadable JSON file (`Content-Disposition: attachment`), containing every **finished** session with `started_at` in `[from, to]`:

```json
{
  "exported_at": "2026-07-18T00:00:00Z",
  "range": { "from": "2026-01-01", "to": "2026-07-18" },
  "sessions": [
    {
      "id": 123,
      "name": "Push Day 14.07.2026",
      "template_name": "Push Day",
      "started_at": "2026-07-14T17:02:00Z",
      "finished_at": "2026-07-14T18:11:00Z",
      "exercises": [
        {
          "exercise_name": "Bankdrücken",
          "muscle_group": "Chest",
          "position": 1,
          "rest_seconds": 120,
          "skipped": false,
          "replaces": null,
          "sets": [
            { "position": 1, "weight": 80.0, "reps": 8, "completed": true }
          ]
        }
      ]
    }
  ]
}
```
- Active/in-progress sessions are excluded (incomplete data).
- Skipped exercises are included with `"skipped": true` and whatever sets survived (useful signal for a future analysis agent — missed/skipped patterns are data, not noise).
- Filename: `gym-export-<from>_<to>.json`.

### UI (`dashboard.html`, history section)
An "Export" control near the existing history list (`#history` anchor): preset buttons (Letzte 30 Tage / Letzte 90 Tage / Alle) that fill the date fields and submit, plus custom von/bis date inputs for a manual range. Plain GET form/link — the browser handles the download via the response's `Content-Disposition` header, no JS needed.

---

## 5. Reorder Lock (safety)

**Problem:** Dragging is triggered by `pointerdown` on `.card-title-area` plus movement past `DRAG_THRESHOLD` — easy to trigger by accident (e.g. in a pocket, or a scroll gesture that starts on the title).

### Design
Pure client-side, no backend/model/route change — the existing `gym_reorder_session_exercises` endpoint is unchanged; only the client decides whether it's allowed to send it.

- A lock toggle (button, "🔒 Gesperrt" / "🔓 Entsperrt") appears near the exercise list header, active-session only (the drag JS already exits immediately when `SESSION_FINISHED`, so history/finished views need no change).
- **Starts locked on every page load/reload** (per your answer — no persistence, no localStorage).
- While locked: `onMove`'s `beginDrag()` call is gated behind the unlocked flag — tapping a card title still toggles collapse/expand (that's the existing non-drag click path, untouched), but movement past the threshold no longer starts a drag.
- Unlocking arms the existing drag logic exactly as it works today; re-locking (or reloading) disarms it again.

---

## Migrations

One new migration: add `SessionExercise.skipped` (Boolean, default False, server_default `'0'`), following the existing `d4f8b2a91c6e_add_replaces_id_to_session_exercises.py` pattern. No other schema changes — items 2, 3, 4, and 5 need no new columns.

## Out of scope (explicitly, not silently)

- Editing which exercise or session a set belongs to (item 2) — weight/reps only.
- Adding/deleting sets on a finished session (item 2) — confirmed out of scope.
- CSV export alongside JSON (item 4) — JSON only, confirmed.
- Persisting the reorder-lock state across reloads (item 5) — confirmed always-locked-on-load.
- A guaranteed root-cause / fix for item 3 — the investigation lead above is documented, but the actual fix is determined via live reproduction at implementation time, not guessed here.

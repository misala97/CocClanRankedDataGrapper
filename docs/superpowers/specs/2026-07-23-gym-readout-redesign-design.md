# Gym Tracker — "Readout" redesign

**Date:** 2026-07-23
**Scope:** `personal_apps` gym feature — navigation shell, dashboard, exercise detail, session detail, session summary
**Visual reference:** `2026-07-23-gym-readout-reference.html` (same directory) — a
one-pass sketch the owner chose the direction from. Evidence of the approved *feel*;
not a specification of its execution. See §4.0.

---

## 1. Why this exists

The gym feature's logging flow works. Everything around it is "what got built": the
dashboard is a junk drawer of four unrelated cards, two of the four nav links are fake
(anchors onto the dashboard, not routes), a finished workout is split across two pages
that are each incomplete, and every template repeats its own `<head>`.

This spec rebuilds those surfaces from the question "what does a user actually need
here", and gives the whole app one visual identity that is its own — unrelated to
`coc_stats` or any other app in this repo.

## 2. Users and usage

- Single user today; possibly a few friends later. **No multi-user complexity** — no
  per-user scoping, no permissions. Don't design in a way that forecloses it either.
- **Mobile-first.** Primary use is logging and checking things at the gym, on a phone,
  standing up, one-handed.
- **Desktop matters.** Progression checking and planning happen there. Desktop must use
  the width meaningfully, not stretch the phone layout.
- **UI language is German.** All user-facing copy in German. Code, comments and
  identifiers in English, matching the existing codebase.

## 3. Decisions locked during design

These were decided explicitly. Do not relitigate them during implementation.

| Decision | Outcome |
|---|---|
| Logging mechanics | Were open to change. On review, only one change earns its keep — the live/collapsed/unlit panel behaviour in §6.4. Every endpoint, form field, and gesture stays as it is. Prefill-from-last-time and tap-to-complete-starts-rest are good and survive unchanged. |
| Landing surface | Genuinely different composition per breakpoint: phone = launcher, desktop = cockpit. |
| Formal planning features | **None.** No routine builder, no rotation scheduler, no per-exercise target setting. Routines keep being derived from finished sessions. Desktop must make history legible enough to plan from in your head. |
| Signals the desktop must answer | All four: am I still progressing / am I training everything / am I training regularly / is total load going up. |
| Workout position (1st vs 3rd in a session) | **First-class dimension.** The gym is busy and exercise order genuinely shifts and genuinely affects performance. Position is visible wherever history appears, not merely a filter that hides data. |
| Finished workout | **One page**, not two. Stats and records on top, the actual logged sets below. |
| Post-finish moment | Receipt **plus** what to change next time. The debrief is the point. |
| Theme | **Dark only.** One committed identity, tuned properly. |
| Visual character | "Readout" — see §4. |
| Navigation | Three real routes as tabs; the active workout is a persistent resume strip, not a tab. |
| Analytics code location | Extracted to a pure `stats.py`. |

## 4. Design brief — "Readout"

**This section is the brief impeccable designs against — not a design to transcribe.**

### 4.0 What is locked, and what impeccable decides

The reference HTML beside this spec is a **sketch**, produced in one pass to let the
owner choose a direction. It used Windows system fonts as stand-ins and hex values that
were invented, not derived, and never contrast-tested. It is committed as **evidence of
the approved feel**, nothing more. Do not treat its values, spacing, radii, or component
layouts as specification.

| Locked — an owner decision, do not overturn | Open — impeccable's job |
|---|---|
| Dark only | The actual palette: every value re-derived and validated |
| The thesis: an equipment readout (§4.1) | How that thesis is expressed in colour, weight, and rhythm |
| The five-state model and its meanings (§4.2) | How each state is rendered |
| Token **names and semantics** (§4.3) — templates reference them | Token **values** |
| Numerals condensed, tabular, largest in their container (§4.4) | Which family; the full type scale; every size and weight |
| Machined not soft; motion mechanical not elastic (§4.5) | Radii, depth, shadow, easing, duration |
| The anti-references (§4.6) | Everything not named above |

If a locked item turns out to be wrong under real execution — e.g. the state model
cannot be made accessible, or the direction fights the content — say so and raise it.
Don't silently deviate, and don't silently comply either.

### 4.1 Thesis

The display on a serious piece of equipment — a rowing monitor, a timing system, a
scoreboard. Industrial condensed numerals and machined chassis edges, with emissive
semantic colour. **The numbers glow because they are lit, not because a gradient was
applied.**

This is a deliberate synthesis of two rejected-alone directions: a pure industrial
treatment reads as grey and shouty; a pure athletic treatment reads as every other
fitness app. Readout is both, and neither.

### 4.2 The state model — the load-bearing rule

Five states. **Every surface in the app inherits them**: set rows, exercise panels,
rest bar, tab bar, dashboard tiles, verdict chips, catalogue rows, history rows. This
is what makes it one app rather than five screens.

| State | Means | Treatment |
|---|---|---|
| **Unlit** | Present but not yet done — e.g. a set prefilled from last time | Outline only, dimmed text, transparent fill |
| **Live** | Happening now — the current set, the running rest timer, the primary action | Amber, with a soft emissive halo. **Only ever one thing at a time on screen.** |
| **Done** | Logged and settled | Full-brightness white, solid filled tick. Reads as fact, not achievement. |
| **Rekord** | Beat a previous best | Cyan, one sharp flare then settles. Rare by construction — that rarity is what makes it land. |
| **Stagniert** | Needs attention | Red outline **plus the word**. |

**Every state must carry a shape or a word as well as a colour.** Colour alone is not
an acceptable signal — it has to survive daylight on a phone screen and colour
blindness.

### 4.3 Token contract

**The names and their meanings are the contract** — templates reference these tokens
directly, so the set must exist and a token may never be repurposed. **The values are
impeccable's to derive.**

```
--ground     page background; the unlit bezel
--chassis    panel surface
--raised     inset / nested surface
--edge       panel border
--edge-hi    the lit top edge of a panel
--ink        primary text; the DONE state — reads as fact
--dim        labels, secondary text
--unlit      inert text, content not yet reached
--live       NOW: current set, running rest, primary action
--live-deep  the pressed / bottom edge of a live control
--record     RECORD: a previous best beaten
--stall      ATTENTION: stagnation, destructive actions
```

Constraints on the palette, in priority order:

1. `--live`, `--record`, and `--stall` must be **unmistakable from each other** at a
   glance, in daylight, on a phone, and under deuteranopia and protanopia. This is the
   binding constraint — if a hue choice fails it, the hue is wrong, however good it
   looks.
2. Every text/background pairing that actually occurs must meet **WCAG AA**. Check the
   real pairings, not the convenient ones: `--live` and `--record` appear on `--chassis`
   far more often than on `--ground`, and `--dim` on `--chassis` is the easiest one to
   get wrong.
3. Neutrals are chosen, not defaulted — give them a deliberate hue bias rather than
   using pure greys.
4. Exactly three semantic hues. No fourth. Nothing decorative gets a colour.

The sketch used an amber / cyan / red triad on a near-black cool-neutral ground. That
combination satisfies constraint 1 and is a reasonable starting hypothesis — but it is a
hypothesis. Derive and validate; don't inherit.

### 4.4 Type

Three roles are required: a **condensed face for display and numerals**, a **body
face**, and something for **dense tabular data and small uppercase labels**. Whether
those are three cuts of one family or a deliberate pairing is impeccable's call — as is
the family itself. IBM Plex (Sans Condensed / Sans / Mono) satisfies the roles and is
one candidate, not a requirement; the note in §4.6 about avoiding the faces that read as
templated applies here too.

Self-hosted Flask app, so a webfont link is fine — there is no CSP constraint. Whatever
is chosen must ship real weights and **true tabular figures**; a face without them fails
the first rule below and is disqualified regardless of how it looks.

Rules that are not negotiable:
- **Numerals are condensed, tabular (`font-variant-numeric: tabular-nums`), and the
  largest thing in their container.** Weight, volume, e1RM, duration, countdown.
- Labels are small, uppercase, letterspaced, and quiet.
- Exercise names are condensed uppercase.
- Body copy stays modest — this app is read in glances, not paragraphs.

### 4.5 Surface and motion

The required qualities, with the sketch's implementation given only as one way to reach
them:

- **Panels read as machined, never soft.** They should look lit from above and edged,
  not floated on a diffuse shadow. *(Sketch: `--chassis` fill, 1px `--edge` border with
  `--edge-hi` on the top edge only, small radius.)*
- **Primary controls have real press depth** — pressing one should feel like it
  travelled. *(Sketch: solid `--live`, inset top highlight, hard `--live-deep` bottom
  edge that compresses on `:active`.)*
- **Motion is mechanical.** Bars fill linearly, counters tick, the record flare is a
  single sharp pulse that settles. **No bounce, no elastic easing.** Honour
  `prefers-reduced-motion`: it disables the flare, the fills, and every transition.

### 4.6 Anti-references

Explicitly not: lime or acid-green on near-black (what this replaces); violet-to-teal
fitness gradients; large soft-rounded cards with wide diffuse shadows; colour used
decoratively; emoji as section markers; the faces that currently read as an AI default
pick (Inter and Space Grotesk as the "safe" choice, Outfit — the two this app is
replacing).

### 4.7 How impeccable is invoked

The visual system (`static/gym/gym.css`) is produced by running the `impeccable` skill
against §4, **before** templates are written against it.

**There is no `PRODUCT.md` anywhere in this repo today.** Verified against
`.claude/skills/impeccable/scripts/context.mjs`: its resolution order is (1) active
project root, (2) that project's `.agents/context/` then `docs/`, (3) monorepo root by
the same order, (4) `$IMPECCABLE_CONTEXT_DIR`, (5) give up. With nothing found it emits
`NO_PRODUCT_MD` and diverts into its from-scratch init flow, which is not what we want
here. `personal_apps/` has no JS workspace marker, so it is not detected as its own
project root and resolution falls through to the repo root.

**Required setup, before invoking impeccable:**

1. Create `personal_apps/PRODUCT.md` containing the product framing (what the gym
   tracker is, who uses it, mobile-first with a real desktop surface) and the design
   brief from §4 of this spec, including a `## Platform` value of `web`.
2. Invoke with `IMPECCABLE_CONTEXT_DIR=personal_apps` from the repo root. Because steps
   1–3 of the resolution order find nothing, the environment variable is consulted and
   wins. Do **not** put a `PRODUCT.md` at the repo root or in the repo's `docs/` — that
   would take precedence and would also apply to `coc_stats`, which has its own
   unrelated identity.

Second gotcha: impeccable's detectors false-positive on em-dashes and numbered markers
in this codebase's CSS comments. Don't chase those findings.

---

## 5. Architecture

### 5.1 Files

```
features/gym/
  routes.py               thin: HTTP handling, mutations, redirects
  stats.py                NEW — pure functions, no Flask import
  push.py                 unchanged
templates/gym/
  _base.html              NEW — single head for all gym pages
  _nav.html               REMADE — tab bar, desktop top bar, resume strip
  _progress_modal.html    NEW — extracted, shared
  heute.html              NEW — replaces dashboard.html
  uebungen.html           NEW
  verlauf.html            NEW
  exercise_detail.html    REMADE
  session_detail.html     REMADE — live logging only
  session_finished.html   REMADE from session_summary.html
static/gym/
  gym.css                 rebuilt from §4
  gym.js                  extended
```

`dashboard.html` and `session_summary.html` are deleted.

### 5.2 Routes

| Method | Path | Renders |
|---|---|---|
| GET | `/gym` | `heute.html` |
| GET | `/gym/uebungen` | `uebungen.html` |
| GET | `/gym/verlauf` | `verlauf.html` |
| GET | `/gym/session/<id>` | `session_detail.html` if `finished_at is None`, else `session_finished.html` |
| GET | `/gym/session/<id>/summary` | **302 → `/gym/session/<id>`** (kept so old links and the finish-redirect keep working) |
| GET | `/gym/exercises/<id>` | `exercise_detail.html` |
| GET | `/gym/export` | unchanged; its UI moves to Verlauf |
| GET | `/gym/exercises/<id>/progress.json` | unchanged |

**Frozen contract.** Every POST route keeps its exact URL, form field names, and
redirect target:

```
/gym/start
/gym/session/<id>/exercises/add
/gym/session/<id>/exercises/reorder
/gym/session/<id>/finish
/gym/session/<id>/delete
/gym/session/<id>/update_template
/gym/session/<id>/save_as_template
/gym/session-exercise/<id>/replace
/gym/session-exercise/<id>/rest
/gym/session-exercise/<id>/sets/add
/gym/session-exercise/<id>/delete
/gym/session-exercise/<id>/skip
/gym/set/<id>/delete
/gym/set/<id>/toggle_complete
/gym/set/<id>/update
/gym/templates/<id>/delete
/gym/exercises/add
/gym/exercises/<id>/update
/gym/exercises/<id>/delete
/gym/push/subscribe
/gym/push/unsubscribe
```

`gym_finish_session` currently redirects to `gym_session_summary`. It now redirects to
`session_detail` directly, keeping the `just_finished=1` query parameter.

### 5.3 `stats.py`

Pure functions. **No Flask import, no `db.session` mutation, no query construction.**
Takes already-loaded rows and primitives, returns plain dicts and lists. This is what
makes the maths checkable without an app context.

```python
epley_1rm(weight, reps)
set_volume(weight, reps, is_unilateral)
session_report(session, history)
exercise_progress(session_exercises, is_unilateral, position=None)
bulk_exercise_state(rows)
stall_report(rows, threshold)
muscle_group_volume(rows, weeks)
weekly_tonnage(rows, weeks)
consistency(sessions, weeks)
routine_memory(templates, sessions)
```

Migrated from `routes.py`: `_epley_1rm`, `_set_volume`, `_sessions_since_last_pr`,
`_session_summary_data`, `_exercise_progress_data`, `_group_exercises_by_muscle`.

**Signature change:** `set_volume` takes `(weight, reps, is_unilateral)` instead of
`(exercise, set)`, so it needs no ORM objects. All callers adapt. The unilateral rule
is unchanged — logged weight and reps are per side, so volume doubles; weight and reps
themselves are never doubled for display.

Staying in `routes.py`: `_to_float`, `_to_int`, `_clean_muscle_group`,
`_get_active_session`, `inject_gym_nav_context`, `_last_session_exercise`,
`_last_performance`, `_last_full_performance`, `_template_exercises_from_session`,
`_cancel_pending_push`, `_schedule_rest`. These touch the session, the request, or
issue queries.

`STAGNATION_THRESHOLD = 4` moves to `stats.py` and is passed into `stall_report`.

### 5.4 The N+1 problem — must be solved, not inherited

`_sessions_since_last_pr` issues one query per exercise today. Übungen needs a state
chip for every exercise in the catalogue, and the desktop board needs the same shape
for the stall list. Naively, that is ~40 queries per page load and it will get worse.

**Required:** a single loader in `routes.py` that pulls completed sets joined to
`SessionExercise` → `WorkoutSession` → `Exercise` for the relevant window, **once**.
Every bulk function in §5.3 consumes that one result set and computes in Python. No
per-exercise queries on Übungen, Heute, or Verlauf.

### 5.5 Time handling

`WorkoutSession.started_at` is `dt.datetime.utcnow()` — naive UTC. All relative-time
maths ("vor 5 Tagen", "2,8/Woche", 4-week windows) must compare against
`dt.datetime.utcnow()`, not local time. Client-side elapsed timers must keep appending
`'Z'` when parsing the ISO string, as `dashboard.html` does today.

### 5.6 Derived signals — exact definitions

Every window is measured back from `dt.datetime.utcnow()`.

**Exercise state chip** (Übungen rows, exercise-detail verdict band). Mutually
exclusive, first match wins:

| Chip | Condition |
|---|---|
| **neu** | No completed sets have ever been logged for this exercise. |
| **Rekord** | The most recent session containing this exercise set a new all-time best e1RM. |
| **stagniert** | Sessions since the last e1RM PR ≥ `STAGNATION_THRESHOLD` (4). Position-scoped with the existing all-positions fallback when a slot has fewer than 2 sessions of history. |
| **steigend** | None of the above, and the most recent session's best e1RM exceeds that of the session before it. |
| *(no chip)* | None of the above — stable. |

e1RM, not raw weight, is the yardstick throughout, so a rep increase at the same weight
still counts as progress. This matches the existing `_sessions_since_last_pr` logic.

**Consistency** (`consistency`): completed sessions in the last 28 days, divided by 4,
rendered as e.g. "2,8/Woche", alongside days since the most recent finished session.

**Muscle-group balance** (`muscle_group_volume`): working sets per muscle group over
the last 28 days. A group is flagged `--stall` (under-trained) when it has **zero**
sets, or **fewer than 25 % of the sets of the highest group** in that window. Relative
rather than absolute, so the flag stays meaningful as overall volume changes. Only
groups that have at least one exercise in the catalogue are listed.

**Weekly tonnage** (`weekly_tonnage`): total volume per ISO week for the last 8 weeks
including the current, partial week. The current week is lit `--live`; it is expected to
be short and must not be read as a decline — label it as running.

**Stall report** (`stall_report`): every exercise whose chip is **stagniert**, sorted by
sessions-since-PR descending. Each entry carries the exercise, its position, the weight
it is stuck at, the date it got stuck, and the count.

**Routine memory** (`routine_memory`): per template, the most recent finished session
with that `template_id`, expressed as days ago. Templates never used sort last.

### 5.7 Shell

- **Mobile:** bottom tab bar. Three tabs — Heute / Übungen / Verlauf. All real routes.
  Active tab lit amber.
- **Desktop (≥900px):** top bar with wordmark, the same three links, and logout. Not a
  sidebar — the cockpit needs the vertical space.
- **Resume strip:** rendered by `_base.html` whenever `gym_active_session` exists and
  the current page is not that session. Amber chassis strip, pinned above the tab bar
  on mobile and below the top bar on desktop. Carries workout name, live elapsed time,
  current exercise, and links into the session. `inject_gym_nav_context()` already
  provides the session — reuse it unchanged.
- **Logout** lives in the desktop top bar, and as a quiet footer link at the bottom of
  Heute on mobile.

---

## 6. Page specifications

### 6.1 Heute (`/gym`)

**Phone composition** — you are standing in a doorway, about to train:

1. Thin header: date, plus a consistency line — *"Zuletzt vor 2 Tagen · 2,8/Woche"*.
2. **Routinen**, sorted longest-since-done first so the one you probably want is on
   top. Each is a chassis panel: name, when it was last done, its exercise list, and
   its own **Starten** button. One tap from routine to running workout.
3. **Freies Workout starten** — ghost button below, with the optional name field.
4. **Letzte Workouts** — the last 5, as compact readout rows linking to the finished
   page.
5. The board, stacked and condensed.

**Desktop composition** — you are planning:

1. Full-width bar: **Letzte 4 Wochen** heading, consistency line, and the amber
   **Workout starten** action.
2. Three-panel board:
   - **Steht still** — stalled exercises, worst first, position-scoped, each showing
     the exercise, its position, the weight it's stuck at, and how many workouts since
     its last e1RM PR.
   - **Sätze pro Muskelgruppe** — working sets per muscle group over a rolling 4 weeks,
     as bars. Under-trained groups flagged in `--stall`.
   - **Tonnage pro Woche** — weekly total volume as bars, the current week lit amber.
3. Below, two columns: **Routinen** and **Letzte Workouts**.

Both compositions come from **one template**. The order flip is CSS grid areas and
`order`, not duplicated markup. A block that genuinely exists at only one breakpoint is
hidden in CSS — Jinja cannot see a viewport.

Routine management (rename, delete) sits behind a small edit affordance on each routine
panel. Deleting a template must continue to null `template_id` on past sessions rather
than cascade — workout history is never destroyed by deleting a routine.

### 6.2 Übungen (`/gym/uebungen`)

- Search box filtering client-side, no round trip.
- Sort control: **nach Muskelgruppe** (default, grouped by `MUSCLE_GROUPS` order with a
  trailing "Ohne Muskelgruppe" bucket) · **am längsten ohne PR** · **zuletzt gemacht**
  (both flat lists).
- Each row: name · when last done · current best (weight, and e1RM) · a lit state chip:
  **Rekord** (a PR in the most recent session) / **steigend** / **stagniert** / **neu**
  (no completed sets yet).
- Sorted by stall, this page answers "what needs attention" without opening anything.
- Add-exercise form at the bottom: name, muscle group, default rest seconds, unilateral
  checkbox.
- Delete offered only for exercises with no session and no template references — the
  existing rule.

### 6.3 Exercise detail (`/gym/exercises/<id>`)

1. **Verdict band** — state chip, last performance, current best (weight **and** e1RM),
   sessions since last PR, and the concrete next step where one applies.
2. **Chart** — every session plotted, with **position encoded as a series** so you can
   see Pos 1 sitting above Pos 3 rather than hiding data to compare them. The existing
   position filter survives for isolating a single slot. Chart.js is already a
   dependency and stays; charts must resolve CSS custom properties to concrete colour
   values before handing them to canvas, which cannot read `var()`.
3. **History table** — date, position, sets as logged, volume, e1RM. Record rows lit
   cyan. Unilateral exercises keep their explanatory note: weight and reps are logged
   per side, volume counts both.
4. **Metadata** — name, muscle group, default rest, unilateral — demoted behind a
   `Bearbeiten` disclosure. It is maintenance, not the reason you opened the page. The
   existing `name_taken` warning path is preserved.

**Desktop:** chart large, verdict and PR rail to its right, history table full-width
below.

### 6.4 Session detail — live (`/gym/session/<id>`, unfinished)

Every endpoint and interaction is preserved. What changes is that the state model does
real work:

- **Exactly one exercise panel is live at a time.** Exercises with all sets completed
  collapse to a settled summary row. Exercises not yet reached render unlit. The screen
  always shows the one thing you are currently doing.
- Set rows move unlit → live → done. Tapping the check completes the set and starts
  rest, exactly as today.
- The rest bar is amber and lives inside the live panel, with the per-set progress
  behaviour that exists today.
- Per-exercise controls retained: rest seconds (auto-saving), progress modal, skip,
  replace (scoped to the same muscle group, as today), remove.
- Page-level retained: add exercise (including creating a new one inline), finish
  workout, save as template, reorder lock, push-notification enable row.
- The stagnation nudge stays, restyled as a `--stall` note.

### 6.5 Session finished (`/gym/session/<id>`, finished)

1. **Record flare** — cyan, top of screen, largest record first. Rendered only when
   there is one.
2. **Readouts** — Volumen (with percentage against your average), Sätze, Dauer,
   Rekorde. The whole-workout volume comparison remains scoped to sessions sharing the
   same `template_id`; freeform sessions omit it, as today.
3. **Nach Übung** — per exercise: name, position, the sets as logged, and a verdict
   chip (*Rekord* / *+6 % Vol.* / *4 ohne PR*). Replaced-away originals stay excluded
   from this session's totals; substitutes represent their slot.
4. **Nächstes Mal** — the stalled lifts with a concrete suggestion, e.g. *"Schrägbank
   KH steht seit 4 Workouts auf 20 kg — auf 22,5 kg gehen, notfalls 2 Wdh. weniger."*
5. Template-update prompt when arriving fresh from a template-linked workout
   (`just_finished=1`). Then: zur Übersicht, Workout löschen.

Visited later from Verlauf, this same page is the complete record of that workout —
which is why the two former pages merge.

### 6.6 Verlauf (`/gym/verlauf`)

Not in the original file list, but required: it absorbs what the dashboard was holding
and is one of the three real routes.

- Chronological list of finished workouts: name, date, duration, exercise list, total
  volume, and a record count chip where applicable. Each links to its finished page.
- Delete per workout, with confirmation, as today.
- **Export panel** — the JSON export with its from/to date inputs and the 30-day /
  90-day / all presets, moved here from the dashboard.

---

## 7. Accessibility and interaction requirements

- Every interactive control is a real `<button>` or `<a>`; nothing clickable is a
  styled `<div>`.
- Visible keyboard focus on every focusable element.
- Touch targets at least 44×44 CSS px for anything tapped during a workout.
- Colour is never the sole carrier of state — see §4.2.
- All text meets WCAG AA contrast against its actual background. Verify the amber and
  cyan against `--chassis`, not against `--ground`, where they are used on panels.
- `prefers-reduced-motion` disables the flare, the linear fills, and any transition.

## 8. Out of scope

- The PWA manifest, service worker, and push-notification daemon (`run_gym_notifier.py`,
  `push.py`) — behaviour unchanged. Only the `theme-color` meta value updates, to
  `--ground`.
- The data model. No migrations. No new columns or tables.
- Any planning feature: routine builder, rotation scheduler, per-exercise targets.
- Multi-user support.
- Other features in `personal_apps` (tips, pubquiz, quizbank) and anything in
  `coc_stats`.

## 9. Verification

There is no test suite in this monorepo today. Two layers:

1. **`pytest` for `stats.py`.** The functions are pure, which makes them cheap to test
   and is exactly where assumption-bugs surface. Cover: Epley at boundary reps,
   unilateral volume doubling, stall counting when history is shorter than the
   threshold, position fallback when a slot has too little history, empty-history
   paths on every aggregate (the `None` aggregate crash class), and week-boundary
   behaviour in the rolling windows.
2. **Manual HTTP verification for routes and templates**, using `app.test_client()`
   with `session_transaction()` to satisfy `@login_required`. Assert 200 on each of the
   six GET routes, the 302 on the legacy `/summary` URL, and that each POST in §5.2
   still redirects where it did before.

Browser verification of the rendered result at 390×844 (phone) and at desktop width,
per the visual requirements in §4.

## 10. Implementation order

1. `stats.py` — extract, add the new functions, add the bulk loader in `routes.py`,
   verify nothing regressed on the existing pages.
2. `gym.css` — run `impeccable` against §4 to produce the token system and components.
3. `_base.html` + `_nav.html` — the shell, including the resume strip.
4. `session_detail.html` — the live view. Highest risk; do it while the most context is
   available.
5. `session_finished.html` + the route merge + the legacy redirect.
6. `heute.html`, `uebungen.html`, `verlauf.html`.
7. `exercise_detail.html`.
8. Delete `dashboard.html` and `session_summary.html`.

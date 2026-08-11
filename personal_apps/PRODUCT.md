# Gym Tracker — Product context

This file is the impeccable design context for the **gym** feature of
`personal_apps`. It is scoped to that feature only; other features in this repo
(tips, pubquiz, quizbank) and `coc_stats` have their own, unrelated identities
and share nothing visual with this one.

## Register

product

## Platform

web

## Users

Single user today; possibly a few friends later. There is **no multi-user
complexity** — no per-user scoping, no permissions — but nothing should be
designed in a way that forecloses it either.

- **Mobile-first.** Primary use is logging and checking things at the gym, on a
  phone, standing up, one-handed.
- **Desktop matters.** Progression checking and planning happen there. Desktop
  must use the width meaningfully, not stretch the phone layout.
- **UI language is German.** All user-facing copy is in German. Code, comments
  and identifiers are in English, matching the existing codebase.

## What it is

A gym-training tracker. The logging flow — start a workout, log sets of
weight×reps, complete a set to start a rest timer, finish the workout — already
works. This redesign rebuilds the surfaces around it (navigation shell,
dashboard, exercise detail, session detail, finished-session summary) from the
question "what does a user actually need here", and gives the whole app one
visual identity that is its own.

The four signals the tool exists to answer: am I still progressing / am I
training everything / am I training regularly / is total load going up. Formal
planning features are deliberately absent — no routine builder, no scheduler, no
per-exercise targets; routines are derived from finished sessions, and the
desktop surface must make history legible enough to plan from in your head.

### Heute vs Statistik

Two surfaces answer the same kinds of question at different **time horizons**,
and that is the whole rule for deciding where a new figure belongs:

- **Heute is windowed.** 28-day muscle balance, eight weeks of tonnage, the
  last five workouts, what is stalling now. It answers *what should I do
  today*.
- **Statistik has no window.** Cumulative totals, all-time progression per
  exercise, behavioural patterns, every record ever. It answers *what does my
  training say about me*.

Ask of any new statistic: is this about now, or about everything? The answer
picks the page — and the module, since `stats.py` serves the first and
`features/gym/analytics.py` the second. Statistik is desktop-only: it is
composed for the width and is not in the mobile tab bar, though its URL stays
reachable.

## Positioning

The thing you operate mid-set and read between sessions: log the set in front of
you without thinking about the app, and see the workout add up while you do it.
Between sessions it answers what is still moving, what has stalled, and what
needs attention — at a glance, on a phone, in a busy gym.

---

## Design brief — "Puls"

**This section is the brief impeccable designs against — not a design to
transcribe.**

### 4.0 What this replaces, and why the last two failed

Two full visual systems were built and rejected before this one:

- **Readout** (equipment panel: industrial condensed numerals, machined chassis,
  amber/cyan/red). Rejected in place. It was simultaneously the first-order
  reflex for this category — dark + neon accent + big numerals — and the
  second-order one, the "not-neon" escape into industrial/console.
- **Athletik** (sport broadcast: heavy oblique numerals, electric blue for NOW,
  gold for records). Rejected in place. Its own brief flagged the risk on day
  one — the lane was crowded and the execution had to beat the lane. It didn't.
  What went wrong is specific and worth keeping: the locked signature was *the
  lean*, so heavy italic ended up on names, buttons, labels and headings at
  once. Everything shouted. Exercise names ran four lines deep in italic caps,
  breaking this brief's own sentence-case rule. Chrome (deload toggle, reorder
  lock) occupied the top third of the session screen before any content. Set
  rows nested a card inside a card inside a card.

**The shared root cause: both briefs designed an instrument you consult.** The
app is used standing up, one-handed, between sets — it is a thing you *operate*,
and the reward for operating it should be visible. That is what changed.

Puls was chosen from four rendered directions, at 390×844, against real
mid-workout data. It won on one property none of the others had: the session
visibly grows while you use it.

| Locked — an owner decision, do not overturn | Open — impeccable's job |
|---|---|
| The thesis: the session accumulates in front of you (§4.1) | How that is expressed in colour, weight and rhythm |
| Committed colour strategy — the surface *is* the colour | The exact values, re-derived and validated |
| Light **and** dark, following the phone | How each theme is composed; both must pass AA independently |
| Mobile-first (390×844 primary) | How each breakpoint composes |
| One skin across every screen | Per-screen intensity (§4.6) |
| Token **names and semantics** (§4.3) — templates reference them | Token **values** |
| Exercise names: sentence case, body face, never caps, never italic | The full type scale |
| German UI copy | — |

If a locked item turns out to be wrong under real execution, say so and raise
it. Don't silently deviate, and don't silently comply either.

### 4.1 Thesis

**The workout fills up.** Every logged set advances something visible — a tick
on the session strip, a chip going solid, the kg total counting up. The
accumulation is the reward, and it is on screen the whole time rather than
saved for a summary at the end.

Colour is committed, not accented: the page is deep aubergine in dark and pale
plum in light, so the app has an identity before a single accent is placed. A
hot orange is reserved entirely for NOW.

### 4.2 The state model — the load-bearing rule

Four states plus a label. **Every surface inherits them**: set chips, exercise
panels, rest bar, dashboard tiles, verdict chips, catalogue rows, history rows.
This is what makes it one app rather than eight screens.

| State | Means | Treatment |
|---|---|---|
| **Offen** | Present, not yet done | Outline only, dimmed text, transparent fill |
| **Jetzt** | Happening now | Hot orange fill, with lift. **Only ever one thing at a time on screen.** |
| **Erledigt** | Logged and settled | Pale rose fill, solid. Reads as fact, not achievement. |
| **Rekord** | Beat a previous best | Gold, one flare, then settles. Rare by construction. |
| **Stagniert** | Needs attention | **Cold cyan** plus the word. |

**Every state carries a shape or a word as well as a colour.**

Attention is deliberately cold, not red. Two reasons, both load-bearing:
orange, gold and red are inseparable under deuteranopia while orange, gold and
cyan are not; and a lift that has stopped moving is not an error, it has gone
cold. The semantics and the accessibility arithmetic point the same way here.

**Deload is a label, not a state.** It carries **no hue** and renders as `--dim`
ink plus the literal word `Deload`. It describes a whole session rather than one
set's progress, and its job is to stop the statistics reading a planned light
week as a plateau. Do not promote it to a colour.

### 4.3 Token contract

**The names and their meanings are the contract** — templates reference these
tokens directly, so the set must exist and a token may never be repurposed. The
names carried over unchanged from the previous system on purpose: they were
always semantic rather than descriptive, so only the values move.

```
--ground     page field — the committed colour, not a neutral
--chassis    panel surface, the one lifted plane
--raised     inset / nested surface (number cells, steppers)
--edge       hairline divider
--edge-hi    lifted border
--ink        primary text
--dim        labels, secondary text
--unlit      inert text, content not yet reached
--live       NOW: current set, running rest, primary action   (hot orange)
--live-deep  the pressed / bottom edge of a live control
--done       LOGGED: a completed set, a finished exercise     (pale rose)
--record     RECORD: a previous best beaten                   (gold)
--stall      ATTENTION: stagnation                            (cold cyan)
--on-live / --on-done / --on-record / --on-stall   text sitting ON those fills
--live-ink / --done-ink / --record-ink / --stall-ink
             the same four roles when the accent is TEXT on a surface
```

Two additions, both forced by measurement rather than taste:

`--done` is new. The previous system had no token for "logged" — it reused
`--ink`, which is why completed work read as plain text rather than as a state.

`*-ink` is new and is the light theme's doing. A colour bright enough to be a
**fill** under dark label text is not dark enough to be **text** on a pale
surface. In the dark theme the two coincide (a bright accent reads fine on an
aubergine field) and `*-ink` simply equals its fill. In the light theme they
cannot: gold at `#F0B429` is a fine chip but fails as text at 1.9:1, while gold
dark enough to read as text is a brown. This is the same arithmetic collision
the previous system hit with its blue and solved with `--on-live`; it is
recorded here so the next person does not rediscover it.

Measured with `scratchpad/palette_puls.py`, which is the source of truth and is
runnable: **25/25 pairings pass AA in each theme** (light floor 4.79, dark floor
4.57), and the three accent fills stay separable under protanopia and
deuteranopia (closest pair 62 of 255 in dark, 109 in light).

Constraints on the palette, in priority order:

1. **Both themes are first-class.** Base values are light; `prefers-color-scheme:
   dark` overrides them; an explicit `html[data-theme]` beats both. Every
   pairing is validated in **both** themes — a value that only passes in one is
   not done.
2. `--live`, `--record` and `--stall` must be **unmistakable from each other** at
   a glance, in daylight, on a phone, and under deuteranopia and protanopia.
3. Every text/background pairing that **actually occurs** meets **WCAG AA** —
   including text on the accent fills, not only accent-on-panel.
4. Exactly three semantic hues plus `--done`. Nothing decorative gets a colour.
5. `--ground` is a committed colour, not a tinted neutral. If it reads as
   "near-black" or "off-white", it is wrong.

Values and the arithmetic behind them are documented in gym.css's header
comment, measured rather than asserted.

### 4.4 Type

**Figtree**, self-hosted. One family, weights 400–800. Vendored into
`static/gym/fonts/` and served from this app — never linked from Google at
runtime, for the same reason the previous face was vendored.

Rules that are not negotiable:

- **No italic anywhere.** The previous system's signature was a lean, and it is
  the single thing most responsible for how loud that build felt.
- **Numerals are tabular (`font-variant-numeric: tabular-nums`) and the largest
  thing in their container.**
- **Exercise names are sentence case in the body face.** Never uppercase, never
  the display weight. A roster of exercise names is not a label. This rule
  existed in the previous brief and was broken by the build; it is restated
  here because it is the most-violated rule in this project's history.
- Uppercase is allowed only on tiny meta labels (≤12px), letterspaced, quiet,
  and never on anything a user reads as content.
- Body copy stays modest — this app is read in glances, not paragraphs.

### 4.5 Surface and motion

- **One lifted plane per screen.** The live exercise is the only thing that
  sits above the field. Everything else is on the field, divided by hairlines.
  This is what stops a page reading as a card grid.
- **Repeated identical cards are banned outright.** Where a list has more than
  one entry, it is divided rows in one shared surface.
- **Those divided rows stay one component: `.row`.** Anatomy is `__lead?` ·
  `__main` (`.name` + `__meta`, optionally `__sub`) · `__wide?` · `__trail?`,
  with `--top` and `__trail--stack` as the only modifiers. Every list on Heute,
  Verlauf and the finished-session debrief uses it. **Do not add a second
  family.** A new list surface composes `.row`; if it genuinely cannot, the
  component needs a variant, not the page its own classes.
- **The confirm target is ≥64px tall and lives in the thumb zone.** No keyboard
  ever opens during a workout: weight and reps are ± steppers.
- **Motion conveys accumulation.** Confirming a set: the chip snaps
  outline→filled, one tick lights on the session strip, the total counts up.
  Same gesture everywhere. Records get one gold flare, then settle.
  Ease-out, 90–220 ms, no bounce, no elastic. `prefers-reduced-motion` replaces
  every one of these with an instant state change.

### 4.6 Per-screen intensity

One skin, but not one volume. The chosen direction is warm and loud, and the
standing risk is that it wears out over a year of daily use. The guard is
designed in rather than argued about:

- **Session (live)** — full intensity. It is a focus mode: no tab bar, one way
  back, the live exercise as the only lifted surface, accumulation always
  visible.
- **Heute, Verlauf, Übungen, exercise detail** — same palette, lower
  saturation. These are read, not operated.
- **Finished-session debrief** — the one place a full-intensity moment is
  earned, because it is the end of the thing that was accumulating.

**Statistik stays desktop-only** and is not in the mobile tab bar; its URL stays
reachable, and opening it on a phone renders single-column rather than
redirecting — cramped is better than hidden, but it must not be *broken*, so
the multi-column layout needs a real fallback rather than horizontal scroll.

Three changes it carries beyond a restyle:

- **It leads with a sentence, not a table.** The page answers what the numbers
  say before it shows them.
- **The record timeline is bounded by year bands**, current year open and older
  years folded with their counts. It ran unbounded at 47 rows and growing,
  roughly two thirds of the page height, and no row was ever removed to fix it.
- **A career strip**: one bar per month since the first workout, height =
  tonnage, with record months, deload months and gaps marked. This is the one
  figure an all-time page should obviously have and did not — Heute holds eight
  weeks, and nothing held the whole history. It needs a new
  `analytics.monthly_tonnage(rows)`; it belongs in `analytics.py` rather than
  `stats.py` by the time-horizon rule above.

### 4.7 Anti-references

Explicitly not: the amber-on-near-black instrument panel two systems ago; the
electric-blue-on-near-black sport broadcast one system ago; lime or acid-green
on near-black; violet-to-teal fitness gradients; any near-black page background
at all — the field is a committed colour; italic as a signature; uppercase
exercise names; colour used decoratively; **emoji as icons** (the app has one
shared inline-SVG set — `static/gym/src/components/Icon.tsx` — precisely so
that emoji never come back); the faces that read as an AI default pick (Inter, Space Grotesk,
Outfit).

## Accessibility & Inclusion

- Colour is never the sole carrier of state — every state also carries a shape or
  a word (§4.2).
- All text meets WCAG AA against its **actual** background, **in both themes** —
  verify the accents against `--chassis` (where they sit on panels), not only
  against `--ground`, and verify the on-fill label colours against the fills.
- Every interactive control is a real `<button>` or `<a>`; nothing clickable is a
  styled `<div>`. Visible keyboard focus on every focusable element.
- Touch targets at least 44×44 CSS px for anything tapped during a workout; the
  primary confirm target is at least 64px tall.
- `prefers-reduced-motion` disables the flare, the fills, the count-up, and every
  transition.


## Implementation (since 2026-08-11)

Where a design change actually lands. The gym pages are **React islands**:
Flask routes embed a validated JSON payload (`features/gym/schemas.py`) into a
thin Jinja shell, and everything below the nav renders from
`static/gym/src/`. The Jinja templates are mount points — do not design in
them.

- **Tokens** live in `static/gym/gym.css` (its header carries the measured
  palette arithmetic). Components reference tokens only.
- **Shared primitives** — change once, every page inherits: the `.row` list
  grammar, `Sheet` (bottom sheets), `Icon.tsx` (the one SVG set),
  `Stepper`, the `.sheet-row` menu rows, `.sset` set-editor grid, the
  `.field` form vocabulary, `UndoToast`.
- **Guard rails a design pass must keep green:** vitest asserts on rendered
  markup (`*.test.tsx` beside each page); the chart has a golden-master
  against the captured original drawing (`ExerciseChart.golden.test.tsx` —
  overlays go outside `.chart__ink`); the pairing test in
  `tests/test_gym_routes_smoke.py` checks every form's action and fields
  against the real routes.
- **Process:** real HTML mockups against live `gym.css` before component
  code, one screen per turn; visual verification via python-playwright
  screenshots at 390×844 and 1280×800, both themes.

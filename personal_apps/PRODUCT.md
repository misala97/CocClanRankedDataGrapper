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

The instrument you read mid-set and plan from between sessions: what is still
moving, what has stalled, what needs attention — answered at a glance, on a
phone, in a busy gym.

---

## Design brief — "Athletik"

**This section is the brief impeccable designs against — not a design to
transcribe.**

Supersedes the earlier "Readout" brief (equipment panel: industrial condensed
numerals, machined chassis, amber/cyan/red). Readout was built and shipped; the
owner reviewed it in place and rejected it. Note *why*, because it is the useful
part: Readout was simultaneously the first-order reflex for this category (dark
+ neon accent + big numerals) and the second-order one (the "not-neon" escape
into industrial/console). Both at once. Any future direction has to clear both.

Athletik was one of two directions rejected *alone* during the original
brainstorm — dismissed then as "reads as every other fitness app." The owner
reconsidered and chose it in a later cycle. That criticism is real and is the
standing risk on this brief: the lane is crowded, so the execution has to be
better than the lane, not merely inside it.

### 4.0 What is locked, and what impeccable decides

| Locked — an owner decision, do not overturn | Open — impeccable's job |
|---|---|
| Dark only | The actual palette: every value re-derived and validated |
| Mobile-first (390×844 primary) | How each breakpoint composes |
| The thesis: sport broadcast (§4.1) | How that thesis is expressed in colour, weight, and rhythm |
| The five-state model and its meanings (§4.2) | How each state is rendered |
| Token **names and semantics** (§4.3) — templates reference them | Token **values** |
| German UI copy | — |
| Numerals tabular and dominant in their container (§4.4) | Which family; the full type scale; every size and weight |

If a locked item turns out to be wrong under real execution, say so and raise
it. Don't silently deviate, and don't silently comply either.

### 4.1 Thesis

Sport broadcast. Heavy oblique numerals that lean into the direction of travel,
a single electric accent reserved entirely for NOW, and **gold for a record
because gold already means record** — the one piece of semantics the app does
not have to teach.

The lean is the signature. It appears on names, numerals and the primary
action, and nowhere else, so it reads as one gesture rather than a texture.

### 4.2 The state model — the load-bearing rule

Five states. **Every surface in the app inherits them**: set rows, exercise
panels, rest bar, tab bar, dashboard tiles, verdict chips, catalogue rows,
history rows. This is what makes it one app rather than five screens.

| State | Means | Treatment |
|---|---|---|
| **Unlit** | Present but not yet done | Outline only, dimmed text, transparent fill |
| **Live** | Happening now | Electric blue, with lift. **Only ever one thing at a time on screen.** |
| **Done** | Logged and settled | Full-brightness ink, solid filled tick. Reads as fact, not achievement. |
| **Rekord** | Beat a previous best | Gold, one sharp flare then settles. Rare by construction. |
| **Stagniert** | Needs attention | Red **plus the word**. |

**Every state must carry a shape or a word as well as a colour.**

**Deload is a label, not a sixth state.** A session can be marked as a
deliberately light one. It carries **no hue** — the three-hue rule stands — and
renders as `--dim` ink plus the literal word `Deload`, the same treatment as
the `neu` chip. It describes a whole session rather than one set's progress,
and its job is to stop the statistics reading a planned light week as a
plateau. Do not promote it to a colour.

### 4.3 Token contract

**The names and their meanings are the contract** — templates reference these
tokens directly, so the set must exist and a token may never be repurposed.

```
--ground     page background, deepest field
--chassis    panel surface
--raised     inset / nested surface
--edge       panel border
--edge-hi    lifted border, inert bar fill
--ink        primary text; the DONE state
--dim        labels, secondary text
--unlit      inert text, content not yet reached
--live       NOW: current set, running rest, primary action
--live-deep  the pressed / bottom edge of a live control
--record     RECORD: a previous best beaten
--stall      ATTENTION: stagnation, destructive actions
--on-live / --on-record / --on-stall   text sitting ON a saturated fill
```

Constraints on the palette, in priority order:

1. `--live`, `--record`, and `--stall` must be **unmistakable from each other**
   at a glance, in daylight, on a phone, and under deuteranopia and protanopia.
2. Every text/background pairing that **actually occurs** must meet **WCAG AA** —
   including text on the accent fills, not only accent-on-panel.
3. Neutrals are chosen, not defaulted — a deliberate hue bias, not pure grey.
4. Exactly three semantic hues. No fourth. Nothing decorative gets a colour.

Current values, and the arithmetic behind them, are documented in gym.css's
header comment; `scratchpad/palette.py` is the script that measured them. One
finding worth carrying forward: a single blue cannot satisfy both "readable as
text on a dark panel" and "readable under white text in a button" at AA — the
two requirements are arithmetically incompatible. Hence `--on-live`.

### 4.4 Type

**Saira**, one variable family carrying all three roles via its **width axis**
rather than a second typeface: 112% for display and numerals, 100% for body,
80% for dense tables and small uppercase labels. It ships true tabular figures
(verified by measurement, not assumption).

Rules that are not negotiable:
- **Numerals are tabular (`font-variant-numeric: tabular-nums`) and the largest
  thing in their container.**
- Labels are small, uppercase, letterspaced, narrow, and quiet.
- **A roster of exercise names is not a label.** Proper nouns get sentence case
  and the body face. Uppercasing a seven-item exercise list turns it into a
  block the reader has to decode word by word — this was the single least
  readable thing in the previous build and it must not come back.
- Body copy stays modest — this app is read in glances, not paragraphs.

### 4.5 Surface and motion

- **Panels are borderless at rest.** A panel is legible because it sits on a
  darker ground, not because a line is drawn around it. A visible border MEANS
  something (live, stall). This is what stops a page of panels reading as a
  card grid.
- **Repeated identical cards are banned outright.** Where a list has more than
  one entry, use two tiers: one featured item carrying the primary action, the
  rest as divided rows in a single shared panel. See `.routine--lead` /
  `.routine-rest`, and `.stat-grid` (a divided readout band, not four tiles).
- **Those divided rows are one component: `.row`.** Anatomy is
  `__lead?` · `__main` (`.name` + `__meta`, optionally `__sub`) · `__wide?` ·
  `__trail?`, with `--top` and `__trail--stack` as the only modifiers. Every
  list on Heute, Verlauf and the finished-session debrief uses it. It replaced
  four hand-rolled families (`.recent-row`, `.ex-report-row`, `.routine-row`,
  `.verlauf-row`) that had drifted apart after the Athletik rebuild — three of
  them carried a byte-identical divider rule. **Do not add a fifth.** A new
  list surface composes `.row`; if it genuinely cannot, that is a signal the
  component needs a variant, not that the page needs its own classes.
  The one deliberate exception is `.uebungen-row`, which is `display: contents`
  inside a grid table so its cells align to shared column tracks — same word,
  different job.
- **Controls are pills; boxes are not.** `--r-control` is a pill radius — it is
  correct on buttons and on 44×44 icon targets, and wrong on anything that
  holds more than one line of text. Those take `--r-panel`.
- **Motion is fast and decisive.** Ease-out curves, 90–220 ms. **No bounce, no
  elastic.** Honour `prefers-reduced-motion`: it disables the flare, the fills,
  and every transition.

### 4.6 Anti-references

Explicitly not: the amber-on-near-black instrument panel this replaces; lime or
acid-green on near-black (what *that* replaced); violet-to-teal fitness
gradients; colour used decoratively; **emoji as icons** (the app now has one
shared inline-SVG set — `_icon_edit.html`, `_icon_chart.html` — precisely so
that emoji never come back); the faces that read as an AI default pick (Inter,
Space Grotesk, Outfit).

## Accessibility & Inclusion

- Colour is never the sole carrier of state — every state also carries a shape or
  a word (§4.2).
- All text meets WCAG AA against its **actual** background — verify amber and cyan
  against `--chassis` (where they sit on panels), not only against `--ground`.
- Every interactive control is a real `<button>` or `<a>`; nothing clickable is a
  styled `<div>`. Visible keyboard focus on every focusable element.
- Touch targets at least 44×44 CSS px for anything tapped during a workout.
- `prefers-reduced-motion` disables the flare, the linear fills, and every
  transition.

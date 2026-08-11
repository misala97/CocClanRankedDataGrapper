---
name: Gym Tracker — Puls
description: The workout fills up in front of you — a committed-colour training instrument you operate one-handed, mid-set.
colors:
  ground: "#F3EAF7"
  chassis: "#FFFFFF"
  raised: "#EEE5F3"
  edge: "#DACAE3"
  edge-hi: "#C2ABCF"
  ink: "#291238"
  dim: "#634674"
  unlit: "#6C537E"
  live: "#C2410C"
  live-ink: "#A83409"
  live-deep: "#8E2C07"
  on-live: "#FFF4EE"
  done: "#8B3A62"
  done-ink: "#7A3256"
  on-done: "#FFF0F6"
  record: "#F0B429"
  record-ink: "#6B4400"
  on-record: "#3A2600"
  stall: "#0C7382"
  stall-ink: "#0F6B78"
  on-stall: "#ECFBFD"
typography:
  name:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
  label:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.11em"
  numeral:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 800
    letterSpacing: "-0.04em"
    fontVariation: "tabular-nums"
rounded:
  field: "12px"
  control: "16px"
  panel: "22px"
  chip: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
components:
  button-live:
    backgroundColor: "{colors.live}"
    textColor: "{colors.on-live}"
    rounded: "{rounded.control}"
    height: "64px"
  button-ghost:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "44px"
  chip-done:
    backgroundColor: "{colors.done}"
    textColor: "{colors.on-done}"
    rounded: "{rounded.chip}"
  chip-record:
    backgroundColor: "{colors.record}"
    textColor: "{colors.on-record}"
    rounded: "{rounded.chip}"
  chip-stall:
    backgroundColor: "{colors.stall}"
    textColor: "{colors.on-stall}"
    rounded: "{rounded.chip}"
---

# Design System: Gym Tracker — "Puls"

## 1. Overview

**Creative North Star: "The workout fills up."**

Puls is an instrument you *operate*, not a dashboard you consult: standing up,
one-handed, between sets. Every logged set advances something visible — a tick
on the session strip, a chip going solid, the kilogram total counting up — and
that accumulation stays on screen the whole time rather than being saved for a
summary. The reward for using the app is watching the session grow.

Colour is **committed, not accented**: the page field is pale plum in light and
deep aubergine in dark, so the app has an identity before a single accent is
placed. Exactly three semantic hues exist — hot orange for NOW, gold for a
RECORD, cold cyan for ATTENTION — plus a pale rose that means LOGGED. Nothing
decorative gets a colour. Attention is deliberately *cold*, not red: a lift
that stopped moving is not an error, it has gone cold — and orange/gold/cyan
survive deuteranopia where orange/gold/red collapse.

This system explicitly rejects its own two predecessors: the amber-on-near-black
instrument panel and the electric-blue sport broadcast. Both designed a thing
you look at; Puls designs a thing you use mid-set.

**Key Characteristics:**
- One committed page colour per theme; both themes first-class, every pairing AA in both.
- Four states plus a label, inherited by every surface (see The Word-Plus-Colour Rule).
- One lifted plane per screen; everything else divided by hairlines on the field.
- Numerals are tabular and the largest thing in their container.
- Fast, decisive motion (90–220 ms, ease-out); accumulation is the choreography.

## 2. Colors

Two full palettes — light is the base, `prefers-color-scheme: dark` overrides —
validated at 25/25 AA pairings per theme (`scratchpad/palette_puls.py` is the
runnable source of truth; gym.css's header carries the arithmetic).

### Primary
- **Hot Orange — NOW** (`--live` #C2410C light / #FF7A4D dark): the current
  set, a running rest, the primary confirm. The single loudest thing on any
  screen, by construction. `--on-live` (#FFF4EE) carries text on the fill;
  `--live-ink` (#A83409) is the same role as text on a surface — a colour
  bright enough to be a fill is not dark enough to be text in the light theme.

### Secondary
- **Gold — RECORD** (`--record` #F0B429 / #FFC861): a previous best beaten.
  One flare, then it settles. Rare by construction; `--record-ink` (#6B4400)
  for gold as text on light surfaces, where raw gold measures 1.9:1.
- **Cold Cyan — ATTENTION** (`--stall` #0C7382 / #5FDDEC): stagnation, always
  accompanied by the word ("Stagniert", "N ohne PR").

### Tertiary
- **Pale Rose — LOGGED** (`--done` #8B3A62 / #F1C8DD): a completed set, a
  finished exercise, the chart's line. Reads as settled fact, not achievement.

### Neutral
- **Plum Field** (`--ground` #F3EAF7 / #241132): the page itself — a committed
  colour, never near-white or near-black.
- **Chassis** (`--chassis` #FFFFFF / #371B49): the one lifted panel surface.
- **Raised** (`--raised` #EEE5F3 / #1B0B26): inset cells — steppers, number
  fields, icon tiles.
- **Edges** (`--edge` #DACAE3 / #472B5A, `--edge-hi` #C2ABCF / #634077):
  hairline dividers and lifted borders.
- **Ink / Dim / Unlit** (#291238 / #634674 / #6C537E light): primary text,
  labels, and content not yet reached.

### Named Rules
**The One-Now Rule.** Only ever one thing on screen is NOW. Two oranges
meaning different things is a broken screen — destructive actions, for
example, are *not* orange.

**The Word-Plus-Colour Rule.** Every state carries a shape or a word as well
as a colour. Colour is never the sole carrier of state.

**The Deload-Is-A-Label Rule.** Deload carries no hue: `--dim` ink plus the
literal word. It describes a session, not a set's progress. Never promote it
to a colour.

## 3. Typography

**Display Font:** Figtree (system-ui fallback)
**Body Font:** Figtree — one family, weights 400–800, self-hosted from
`static/gym/fonts/`, never linked from Google at runtime.

**Character:** friendly geometric sans doing serious counting. The scale is
fixed rem (product UI, consistent DPI), and the personality lives almost
entirely in weight and numeral size, never in slant — no italic exists
anywhere in the system.

### Hierarchy
- **Numerals** (800, 1.375–3.25rem ladder: `--num-sm` 22px set loads,
  `--num-md` 34px clock and metrics, `--num-lg` 40px debrief readouts,
  `--num-xl` 52px the record flare; tracking −0.04em): always
  `font-variant-numeric: tabular-nums`, always the largest thing in their
  container.
- **Name** (700, 1.375rem / 22px, −0.025em): exercise and panel names.
  Sentence case in the body face — never uppercase, never the display weight.
- **Body** (400–600, 1rem / 16px): sentences. Read in glances, kept modest.
- **Small / Meta** (0.875rem / 0.8125rem): dense rows, secondary meta.
- **Label** (600, 0.75rem / 12px, +0.11em, uppercase): tiny panel captions
  only — the single place uppercase is allowed.

### Named Rules
**The Sentence-Case Rule.** Exercise names are content, not labels: sentence
case, body face, never caps, never italic. Historically the most-violated rule
in this project; treat any uppercase exercise name as a bug.

**The Numerals-Lead Rule.** In any container that shows a number, the number
is the biggest thing in it.

## 4. Elevation

Lifted, not glowing — and rationed. Exactly **one lifted plane per screen**
(the live exercise panel; the debrief's flare), carried by `--lift`
(`0 1px 2px rgba(41,18,56,.05), 0 10px 30px -16px rgba(41,18,56,.32)` light).
Everything else sits flat on the field, separated by 1px `--edge` hairlines.
Inset depth (`--raised` cells) signals "editable value", not elevation. The
two `--glow-*` shadows are soft coloured seats under live/record elements,
not halos.

### Named Rules
**The One-Lifted-Plane Rule.** If two panels float, one of them is wrong.
Lists are divided rows in one shared surface — repeated identical cards are
banned outright.

## 5. Components

The implementation is a React component library (`static/gym/src/`); these are
its shared primitives. Changing one changes every page — that is the point.

### Buttons
- **Shape:** pill-cornered rectangles (16px radius); true pills only for chips.
- **Primary (`.btn--live`):** hot orange fill, `--on-live` text, ≥64px tall —
  the thumb-zone confirm. One per screen (One-Now Rule).
- **Ghost (`.btn--ghost`):** `--raised` fill, ink text, 44px minimum.
- **Quiet-danger:** ink text, *no hue* — the word and a confirm/undo carry the
  weight, never red or orange.

### Chips / Tags (`.chip`, `.vtag`)
- **Style:** full pills, 11–13px semibold, letterspaced uppercase.
- **States:** filled chips (done rose, record gold) carry dark on-fill text;
  outline chips (live, stall) carry the hue as text — state reads by shape as
  well as colour. Deload: transparent, `--edge` border, `--dim` word.

### Rows (`.row` — the one list grammar)
- **Anatomy:** `__lead?` · `__main` (name + meta, optional sub) · `__trail?`;
  modifiers `--top` and `__trail--stack` only.
- **Rule:** every list on every page composes this. A new list surface that
  "cannot" use it needs a variant, not its own classes.

### Sheets (`Sheet` + `.sheet-row` + `.sset`)
- **Container:** native `<dialog>` bottom sheet, 22px top radius, platform
  backdrop/Esc/focus-trap.
- **Menu rows:** 38px raised icon tile · semibold name · `--dim` meta line
  answering what the label alone would leave open. Danger rings its tile.
- **Set editor (`.sset`):** one grid — ordinal · weight · kg · × · reps ·
  actions — with numbers in raised cells matching the live steppers.

### Inputs / Fields (`.field`)
- **Style:** label above input, 12px radius, `--raised`-tinted fill, 44px min
  height; numeric fields narrow, centred, tabular.
- **Focus:** visible ring on every focusable element, no exceptions.

### Signature: the accumulation set
The session strip (one tick per set, `now` pulsing), the set chips
(outline → solid on confirm), and the counting kg total are one gesture:
confirming a set advances all three in 90–220 ms ease-out. Records get one
gold flare, then settle. `prefers-reduced-motion` replaces every one of these
with an instant state change.

## 6. Do's and Don'ts

### Do:
- **Do** keep both themes first-class — validate every new pairing AA in both
  before shipping; the light theme is usually the binding constraint.
- **Do** give every state a word or shape alongside its colour.
- **Do** put numerals in tabular figures at the top of their container's scale.
- **Do** compose new lists from `.row` and new menus from `.sheet-row`.
- **Do** keep the confirm target ≥64px and in the thumb zone; every other
  target ≥44px.
- **Do** prefer silence: an unanswerable figure is absent, never a confident 0.

### Don't:
- **Don't** use "the amber-on-near-black instrument panel" or "the
  electric-blue-on-near-black sport broadcast" — both were built and rejected.
- **Don't** use "lime or acid-green on near-black; violet-to-teal fitness
  gradients; any near-black page background at all — the field is a committed
  colour."
- **Don't** use "italic as a signature" — no italic anywhere.
- **Don't** set "uppercase exercise names" — sentence case, body face, always.
- **Don't** spend colour decoratively; three semantic hues plus rose is the
  entire budget.
- **Don't** use "emoji as icons" — the one inline-SVG set is
  `static/gym/src/components/Icon.tsx`, stroke 1.5, 16-grid.
- **Don't** reach for "the faces that read as an AI default pick (Inter,
  Space Grotesk, Outfit)" — the face is Figtree, vendored.
- **Don't** nest cards, repeat identical cards, or float a second plane.
- **Don't** promote Deload to a colour, ever.

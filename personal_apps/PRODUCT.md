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

## Positioning

The instrument you read mid-set and plan from between sessions: what is still
moving, what has stalled, what needs attention — answered at a glance, on a
phone, in a busy gym.

---

## Design brief — "Readout"

**This section is the brief impeccable designs against — not a design to
transcribe.**

A one-pass visual sketch (`2026-07-23-gym-readout-reference.html`) was produced
to let the owner choose a direction. It used Windows system fonts as stand-ins
and hex values that were invented, not derived, and never contrast-tested. It is
evidence of the approved **feel**, nothing more. Its values, spacing, radii, and
component layouts are **not** specification.

### 4.0 What is locked, and what impeccable decides

The reference HTML beside the spec is a **sketch**, produced in one pass to let
the owner choose a direction. It used Windows system fonts as stand-ins and hex
values that were invented, not derived, and never contrast-tested. It is
committed as **evidence of the approved feel**, nothing more. Do not treat its
values, spacing, radii, or component layouts as specification.

| Locked — an owner decision, do not overturn | Open — impeccable's job |
|---|---|
| Dark only | The actual palette: every value re-derived and validated |
| The thesis: an equipment readout (§4.1) | How that thesis is expressed in colour, weight, and rhythm |
| The five-state model and its meanings (§4.2) | How each state is rendered |
| Token **names and semantics** (§4.3) — templates reference them | Token **values** |
| Numerals condensed, tabular, largest in their container (§4.4) | Which family; the full type scale; every size and weight |
| Machined not soft; motion mechanical not elastic (§4.5) | Radii, depth, shadow, easing, duration |
| The anti-references (§4.6) | Everything not named above |

If a locked item turns out to be wrong under real execution — e.g. the state
model cannot be made accessible, or the direction fights the content — say so and
raise it. Don't silently deviate, and don't silently comply either.

### 4.1 Thesis

The display on a serious piece of equipment — a rowing monitor, a timing system,
a scoreboard. Industrial condensed numerals and machined chassis edges, with
emissive semantic colour. **The numbers glow because they are lit, not because a
gradient was applied.**

This is a deliberate synthesis of two rejected-alone directions: a pure
industrial treatment reads as grey and shouty; a pure athletic treatment reads as
every other fitness app. Readout is both, and neither.

### 4.2 The state model — the load-bearing rule

Five states. **Every surface in the app inherits them**: set rows, exercise
panels, rest bar, tab bar, dashboard tiles, verdict chips, catalogue rows,
history rows. This is what makes it one app rather than five screens.

| State | Means | Treatment |
|---|---|---|
| **Unlit** | Present but not yet done — e.g. a set prefilled from last time | Outline only, dimmed text, transparent fill |
| **Live** | Happening now — the current set, the running rest timer, the primary action | Amber, with a soft emissive halo. **Only ever one thing at a time on screen.** |
| **Done** | Logged and settled | Full-brightness white, solid filled tick. Reads as fact, not achievement. |
| **Rekord** | Beat a previous best | Cyan, one sharp flare then settles. Rare by construction — that rarity is what makes it land. |
| **Stagniert** | Needs attention | Red outline **plus the word**. |

**Every state must carry a shape or a word as well as a colour.** Colour alone is
not an acceptable signal — it has to survive daylight on a phone screen and colour
blindness.

### 4.3 Token contract

**The names and their meanings are the contract** — templates reference these
tokens directly, so the set must exist and a token may never be repurposed. **The
values are impeccable's to derive.**

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

1. `--live`, `--record`, and `--stall` must be **unmistakable from each other** at
   a glance, in daylight, on a phone, and under deuteranopia and protanopia. This
   is the binding constraint — if a hue choice fails it, the hue is wrong, however
   good it looks.
2. Every text/background pairing that actually occurs must meet **WCAG AA**. Check
   the real pairings, not the convenient ones: `--live` and `--record` appear on
   `--chassis` far more often than on `--ground`, and `--dim` on `--chassis` is the
   easiest one to get wrong.
3. Neutrals are chosen, not defaulted — give them a deliberate hue bias rather than
   using pure greys.
4. Exactly three semantic hues. No fourth. Nothing decorative gets a colour.

The sketch used an amber / cyan / red triad on a near-black cool-neutral ground.
That combination satisfies constraint 1 and is a reasonable starting hypothesis —
but it is a hypothesis. Derive and validate; don't inherit.

### 4.4 Type

Three roles are required: a **condensed face for display and numerals**, a **body
face**, and something for **dense tabular data and small uppercase labels**.
Whether those are three cuts of one family or a deliberate pairing is impeccable's
call — as is the family itself. IBM Plex (Sans Condensed / Sans / Mono) satisfies
the roles and is one candidate, not a requirement; the note in §4.6 about avoiding
the faces that read as templated applies here too.

Self-hosted Flask app, so a webfont link is fine — there is no CSP constraint.
Whatever is chosen must ship real weights and **true tabular figures**; a face
without them fails the first rule below and is disqualified regardless of how it
looks.

Rules that are not negotiable:
- **Numerals are condensed, tabular (`font-variant-numeric: tabular-nums`), and
  the largest thing in their container.** Weight, volume, e1RM, duration,
  countdown.
- Labels are small, uppercase, letterspaced, and quiet.
- Exercise names are condensed uppercase.
- Body copy stays modest — this app is read in glances, not paragraphs.

### 4.5 Surface and motion

The required qualities, with the sketch's implementation given only as one way to
reach them:

- **Panels read as machined, never soft.** They should look lit from above and
  edged, not floated on a diffuse shadow. *(Sketch: `--chassis` fill, 1px `--edge`
  border with `--edge-hi` on the top edge only, small radius.)*
- **Primary controls have real press depth** — pressing one should feel like it
  travelled. *(Sketch: solid `--live`, inset top highlight, hard `--live-deep`
  bottom edge that compresses on `:active`.)*
- **Motion is mechanical.** Bars fill linearly, counters tick, the record flare is
  a single sharp pulse that settles. **No bounce, no elastic easing.** Honour
  `prefers-reduced-motion`: it disables the flare, the fills, and every
  transition.

### 4.6 Anti-references

Explicitly not: lime or acid-green on near-black (what this replaces);
violet-to-teal fitness gradients; large soft-rounded cards with wide diffuse
shadows; colour used decoratively; emoji as section markers; the faces that
currently read as an AI default pick (Inter and Space Grotesk as the "safe"
choice, Outfit — the two this app is replacing).

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

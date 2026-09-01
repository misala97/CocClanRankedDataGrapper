---
name: Radar — Briefing
description: A pale, tabular board read beside a dark broker terminal; violet is talk, green and red are price, amber is a number not to be trusted.
colors:
  paper: "oklch(0.988 0.002 290)"
  pane: "oklch(0.970 0.004 290)"
  raise: "oklch(1 0 0)"
  rule: "oklch(0.888 0.007 290)"
  rule-soft: "oklch(0.940 0.005 290)"
  ink: "oklch(0.230 0.021 285)"
  ink-2: "oklch(0.395 0.018 285)"
  muted: "oklch(0.480 0.016 285)"
  dim: "oklch(0.545 0.012 285)"
  chatter-violet: "oklch(0.470 0.185 296)"
  chatter-violet-hi: "oklch(0.560 0.180 296)"
  chatter-violet-soft: "oklch(0.470 0.185 296 / 0.13)"
  chatter-violet-wash: "oklch(0.470 0.185 296 / 0.07)"
  price-up: "oklch(0.470 0.130 150)"
  price-down: "oklch(0.500 0.175 27)"
  price-up-soft: "oklch(0.470 0.130 150 / 0.14)"
  price-down-soft: "oklch(0.500 0.175 27 / 0.13)"
  caution-amber: "oklch(0.480 0.110 65)"
  caution-amber-soft: "oklch(0.480 0.110 65 / 0.11)"
  session-after: "oklch(0.440 0.145 302)"
  session-after-soft: "oklch(0.440 0.145 302 / 0.11)"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tabular-nums"
  meta:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.35
    fontFeature: "tabular-nums"
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "10.5px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.06em"
rounded:
  r: "8px"
  pill: "100px"
  swatch: "2px"
spacing:
  s1: "4px"
  s2: "6px"
  s3: "8px"
  s4: "12px"
  s5: "16px"
  s6: "20px"
  s7: "26px"
  s8: "34px"
  s9: "44px"
  pane-pad: "24px"
components:
  tab:
    textColor: "{colors.muted}"
    typography: "{typography.meta}"
    padding: "0 0 8px"
  tab-pressed:
    textColor: "{colors.ink}"
    typography: "{typography.meta}"
    padding: "0 0 8px"
  button-pill:
    backgroundColor: "{colors.raise}"
    textColor: "{colors.ink-2}"
    typography: "{typography.meta}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  chip-lean:
    backgroundColor: "{colors.rule-soft}"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 6px 1px"
  chip-lean-bull:
    backgroundColor: "{colors.price-up-soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0 6px 1px"
  chip-lean-bear:
    backgroundColor: "{colors.price-down-soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0 6px 1px"
  pill-session-after:
    backgroundColor: "{colors.session-after-soft}"
    textColor: "{colors.session-after}"
    rounded: "{rounded.pill}"
    padding: "1px 5px"
---

# Design System: Radar — Briefing

## 1. Overview

**Creative North Star: "The Pre-Open Tape"**

A short list checked before the open and between coffees, read at a desk beside a broker terminal that is almost certainly dark. So the board is pale — a near-white paper tinted 0.002–0.006 toward its own violet — because a pale surface stays legible in a bright morning room and stays visually separate from the terminal next to it. Dark ships too, for the 23:00 read, on `prefers-color-scheme` with `html[data-theme]` overriding it. Everything on the surface is a number read against the number above it: one typeface, fixed pixel sizes, tabular figures everywhere except in prose.

The whole system falls out of one constraint. This is a data tool that must never read as a recommendation (PRODUCT.md: no BUY affordances, no traffic-light verdicts, no gauge), so green and red are spent entirely on price direction and appear nowhere else. The one hue the domain leaves unclaimed — violet — carries chatter, selection and focus. Chatter is violet, price is green or red, and the product *is* the place where the two disagree: a violet body climbing while the price line stays flat. Every chart on the page, from the 26px row drawing to the 300px panel, draws exactly those two things on one axis.

Density is built for the twelve-row board that actually exists, not a hypothetical fifty: one line per row under a column header, the quiet two-row board as the normal case with its account of what was left out at the foot of the pane. Motion answers questions the reader asked and nothing else: a chart draws itself in time order, presses respond, arrivals settle. Nothing pulses, nothing draws the eye on its own initiative.

**Key Characteristics:**
- Pale paper with a violet-tinted neutral ramp; dark theme is the same ramp inverted.
- Three colours with fixed meanings: violet = chatter/selection, green/red = price direction, amber = caution on a number.
- One family (Inter, vendored), weight and size carry the hierarchy; fixed px, never `clamp()`.
- Tabular figures by default; hairline rules and three surface tones instead of shadows.
- Controls are underlined text tabs in fixed slots; a zero-count tab dims, never disappears.
- Every reveal animates the FROM; a stilled animation is a finished surface.

## 2. Colors

A violet-tinted neutral ramp carrying three semantic colours whose meanings are fixed on this surface and nowhere negotiable.

### Primary
- **Chatter Violet** (`oklch(0.470 0.185 296)`): the accent, and it means one thing — talk. The chatter area and outline in every chart, the selected row's ticker and score, the pressed tab's underline, every focus ring, the `RANKED BY CHATTER` state flag. **Chatter Violet Hi** (`oklch(0.560 0.180 296)`) is its hover. **Soft** (13% alpha) fills chart bodies; **Wash** (7%) is the row hover.

### Secondary
- **Price Up** (`oklch(0.470 0.130 150)`) and **Price Down** (`oklch(0.500 0.175 27)`): price direction over the score window, and nothing else — the price line, the move figure, the panel's quote move. Their **Soft** tints (14% / 13%) exist for exactly one sanctioned exception: the lean chip's wash on a row's bullish/bearish word count, faint enough to read as annotation rather than verdict.

### Tertiary
- **Caution Amber** (`oklch(0.480 0.110 65)`): a number that cannot be taken at face value — every mark (`no-print`, `provisional`, `single-source`, `partial`, `warming-up`), a stale or fallback quote fact, the board-wide caution in the status line, the amber sentence in the panel's read, a `closed` session word. Its **Soft** (11%) tints the pre-market session pill.
- **Session After** (`oklch(0.440 0.145 302)`): the after-hours session pill only — a violet-adjacent hue, deliberately not the accent.

### Neutral
- **Paper** (`oklch(0.988 0.002 290)`): the page and the selected row (the row takes the panel's ground so the two read as one surface).
- **Pane** (`oklch(0.970 0.004 290)`): the list column.
- **Raise** (`oklch(1 0 0)`): pill buttons and fallback badges — the one pure white, used sparingly.
- **Rule** (`oklch(0.888 0.007 290)`) and **Rule Soft** (`oklch(0.940 0.005 290)`): pane borders and row dividers respectively; every division on the page is one of these two 1px lines.
- **Ink** (`oklch(0.230 0.021 285)`), **Ink 2** (`oklch(0.395 0.018 285)`), **Muted** (`oklch(0.480 0.016 285)`), **Dim** (`oklch(0.545 0.012 285)`): four text tones. Ink is a value the reader acts on, Ink 2 a fact beside it, Muted a label or explanation, Dim a control that is present but quiet (a zero-count tab, a separator dot). Dim still clears 4.5:1 on Pane.

### Named Rules
**The Direction Rule.** Green and red mean price direction and appear nowhere else — not on a button, a badge, a brand mark or a tone bar. A green/red tone bar has been built and deleted twice.

**The Amber Rule.** Amber is reserved for a number that cannot be taken at face value. The board's own sort key (`DIV`) is never amber: colouring it so would say the ranking is suspect.

**The Once Rule.** A caution every row carries is not a caution; it is stated once in the status line and lifted off the rows. What remains on a row is only what deviates.

## 3. Typography

**Display Font:** Inter (with ui-sans-serif, system-ui fallback)
**Body Font:** Inter
**Label/Mono Font:** none — Inter throughout, tabular figures do the mono's job.

**Character:** One family, vendored, weight and size carrying the whole hierarchy. There is no display face because every heading here is a label on data rather than a thing to look at. Fixed pixel sizes on a ~1.15 ratio, never `clamp()`: the reader is at a consistent desk DPI and a heading that shrank with the viewport would only make the tiers harder to tell apart.

### Hierarchy
- **Display** (700, 30px, 1.1, −0.015em): the panel's ticker, once per screen.
- **Headline** (700, 15px, 1.2, −0.01em): a row's ticker; the wordmark at 17px.
- **Title** (600, 13.5px): zone headings in the panel, the tier caption's bold, the row's score figure (650).
- **Body** (400, 15px, 1.45): the panel's read and prose. Prose uses proportional figures (`.prose`); everything else on the page is tabular.
- **Meta** (400, 11.5px, 1.35): row figures, the status line, tabs, post heads, the summary line. The floor for load-bearing text; the amber marks live here.
- **Label** (500, 10.5px, 0.06em, uppercase): column headers, table heads, the marks glossary terms, the `RANKED BY CHATTER` flag, chart axis text. Labels only — never a heading, never an eyebrow over a section.

### Named Rules
**The Tabular Rule.** `font-variant-numeric: tabular-nums` on the body; every column is a number read against the number above it, and proportional figures make that comparison a re-read instead of a glance. Prose opts out.

**The No-Weight-Jump Rule.** A pressed tab is ink plus an underline, never bold: a weight change alters the tab's width, and a strip that reflows on click moves the other tabs under the cursor.

## 4. Elevation

Flat, tonal, hairline. There are no shadows anywhere in the system — not on the panel, not on a hover, not on a popover. Depth is carried by three surface tones (Paper under the page and the selected row, Pane under the list, Raise on the rare pill) and by two weights of 1px rule (Rule between panes, Rule Soft between rows). The selected row punches a 1px hole through the pane divider so it and the panel read as one continuous surface — the whole "elevation" vocabulary is that one gesture.

### Named Rules
**The Hairline Rule.** Every division is a 1px line in Rule or Rule Soft. No borders thicker than 1px, no side stripes, no cards inside cards; a group is made by proximity and a rule, not by a box.

## 5. Components

Restrained instruments: text that becomes a control by an underline, a washed pill where a count needs a chip, and one signature drawing repeated at two sizes.

### Tabs (the instrument strip)
- **Shape:** flat text, 11.5–12.5px, no box; a 2px bottom border that is transparent at rest and Chatter Violet when pressed.
- **Default:** Muted text. **Hover:** Ink. **Pressed:** Ink with the violet underline; its count in violet 600. **Zero count:** Dim, never removed — fixed slots, nothing moves between loads.
- **Focus:** 2px Chatter Violet outline, 1px offset. **Inert (last source):** `aria-disabled`, Ink, with the reason written beside it in amber Label size.
- **Members line:** the same tab at Meta size under the views row, `covered` (Ink 2, no underline) when in force through the bundle.

### Buttons
- **Pill** (Reload, Retry, Show X instead): Raise background, 1px Rule border, pill radius, Ink 2 text at Meta size, padding 1px 8px; hover to Ink. The only boxed control on the surface.
- **Text link buttons** (`change`, `done`): Chatter Violet 600 at Meta size, 2px underline when expanded. No fill.

### Chips
- **Lean chip** (`↑4 ↓2`): pill, Label size, Muted text, Rule Soft background; washed Price Up Soft when bullish leads, Price Down Soft when bearish leads, gray when even; the dominant side bold in Ink. The one sanctioned use of green/red tint off the price line.
- **Session pill:** pill, 1px 5px; Rule Soft/Muted for regular and closed, Caution Amber Soft/Amber for pre-market, Session After Soft/Session After for after-hours.
- **Fallback badge** (`US fallback · NYSE · USD`): pill, 1px Rule border, Raise background, Ink 2.

### Cards / Containers
- None. The list is a pane, the panel is a pane, both scroll themselves; content is grouped by hairlines and spacing. A tier caption is a rule with a label, not a section header.

### Inputs / Fields
- None on the surface (the only form is the market switch: two radio labels rendered as tabs).

### Navigation
- **Masthead:** wordmark (Headline 17px) · market switch (`US / DE` as tabs) · freshness stamp right-aligned in Meta, turning amber with a Reload pill once stale.
- **Status line:** Meta-size tokens separated by real `·` text (announced by screen readers), the session word bold, cautions amber, `RANKED BY CHATTER` as a violet Label-size flag.
- **Mobile:** the panel follows the list; a `← Back to board` link in Chatter Violet at the panel's top.

### The chart-row (signature)
Every row draws 24h of chatter as a violet area with its outline, the ticker's own normal as a dashed Dim line across it, and the price line riding above in Price Up or Price Down — on one hairline axis, 26px tall in the list and 300px in the panel. The price line draws only when there is a price story; a frozen tape draws no line rather than a flat one. The panel version wipes in along x (time) over 420ms on the sweep curve; the axes fade in; both are `backwards` fills so a stilled animation still shows a finished chart.

### Skeleton
The panel's loading state in its own shape — ticker, name, two read lines, the chart box, the breakdown head — as Rule Soft blocks with a slow shimmer, delayed 260ms so a fast answer never flashes it.

## 6. Do's and Don'ts

### Do:
- **Do** keep every negative in U+2212 (`−4.5%`), every percent in one dialect, every age in `humanAge` units (`45h`, not `2743 min`).
- **Do** render an unknown as words or an em-dash (`no quote`, `not scored`, `—`) — never as `0`, `0.00` or `$0.00`. Absence is never zero.
- **Do** state a board-wide fact once, in the status line, and lift it off the rows.
- **Do** keep marks visible on the row in amber at Meta size; the glossary defines them below the list.
- **Do** animate the FROM only: base rules hold the final geometry, keyframes declare `from`, fills are `backwards`.
- **Do** keep desk density: rows ~46px, list 560px at ≥1280, the twelve-row board unscrolled at 1440×900.
- **Do** use `tabular-nums` on anything a reader compares vertically.

### Don't:
- **Don't** put green or red on anything but price direction — no buttons, badges, brand marks, tone bars, or verdict strips. "No BUY affordances, no traffic-light verdicts, no gauge that reads like a recommendation" (PRODUCT.md).
- **Don't** collapse divergence into one badge or bar; mention z-score and price move must stay legible as separate quantities beside the number that combines them.
- **Don't** hide a trust mark behind a tooltip or a `title`; `title` is mouse-only and the reader who needs the definition is the one who just met the word.
- **Don't** introduce a display face, a second family, or `clamp()` sizes.
- **Don't** add shadows, side-stripe borders, cards inside cards, or pill-shaped filter chips; controls are underlined text.
- **Don't** let a tab appear, disappear or change width between loads; zero dims, pressed underlines, nothing bolds.
- **Don't** stagger the list, reveal on scroll, or pulse anything — motion that says "look here" is a call the surface is not allowed to make.
- **Don't** design for a fifty-row table; the majority state is two to twelve rows, and the quiet board must look deliberate.

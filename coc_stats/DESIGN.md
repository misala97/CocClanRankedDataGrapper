---
name: CoC Analytics
description: Night-ops thermal-scope command center for Clash of Clans clan analytics
colors:
  gunmetal-black: "oklch(0.10 0.004 330)"
  scope-housing: "oklch(0.16 0.010 330)"
  scope-housing-raised: "oklch(0.21 0.012 330)"
  bezel-line: "oklch(0.28 0.014 330)"
  bezel-line-2: "oklch(0.24 0.012 330)"
  readout-white: "oklch(0.95 0.006 330)"
  dim-readout: "oklch(0.66 0.014 330)"
  threat-magenta: "oklch(0.62 0.190 330)"
  threat-magenta-deep: "oklch(0.42 0.150 330)"
  iff-green: "oklch(0.72 0.150 165)"
  recon-blue: "oklch(0.68 0.140 230)"
  raid-red: "oklch(0.60 0.200 25)"
  caution-amber: "oklch(0.78 0.150 85)"
  cwl-violet: "oklch(0.62 0.170 290)"
  war-amber: "oklch(0.68 0.170 55)"
  star-gold: "oklch(0.83 0.165 90)"
typography:
  display:
    fontFamily: "'Big Shoulders Display', sans-serif"
    fontSize: "clamp(30px, 6vw, 52px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.5px"
  headline:
    fontFamily: "'Big Shoulders Display', sans-serif"
    fontSize: "clamp(22px, 2.6vw, 30px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.4px"
  title:
    fontFamily: "'Big Shoulders Display', sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "'Manrope', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "'Manrope', sans-serif"
    fontSize: "10.5px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "1.2px"
  data:
    fontFamily: "'JetBrains Mono', monospace"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  pill: "20px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  band: "44px"
components:
  ticket:
    backgroundColor: "{colors.scope-housing}"
    rounded: "{rounded.lg}"
    padding: "18px 20px"
  ticket-hover:
    backgroundColor: "{colors.scope-housing-raised}"
  featured-tile:
    backgroundColor: "{colors.scope-housing}"
    rounded: "{rounded.lg}"
    padding: "22px 24px"
  featured-tile-hover:
    backgroundColor: "{colors.scope-housing-raised}"
  compact-row:
    backgroundColor: "{colors.scope-housing}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
  compact-row-hover:
    backgroundColor: "{colors.scope-housing-raised}"
  action-button:
    backgroundColor: "transparent"
    textColor: "{colors.threat-magenta}"
    rounded: "{rounded.sm}"
    padding: "7px 14px"
  action-button-hover:
    backgroundColor: "{colors.threat-magenta}"
---

# Design System: CoC Analytics

## 1. Overview

**Creative North Star: "The Night Ops Scope"**

CoC Analytics reads as a thermal-scope readout, not a SaaS dashboard: a near-black gunmetal surface that everything else sits on top of, with color reserved for signal, not decoration. Two hues carry the identify-friend-or-foe logic that the whole page runs on — Threat Magenta flags urgency and primary interaction, IFF Green flags a positive or friendly result — and a small family of category hues (War Amber, Raid Red, CWL Violet, Recon Blue) let a clan leader tell which mode a card belongs to at a glance, without reading the label first. This is a **product** surface (PRODUCT.md), not a brand page: the system exists to serve fast, trustworthy verdicts for two audiences at once — the leader making a bench call and the member checking their own week — never to perform for its own sake.

What this system explicitly rejects, per PRODUCT.md's anti-references: the flattened, generic bordered-stat-tile SaaS-dashboard cliché, and anything that reads as a cold, soulless spreadsheet. Precision is the personality here, not sterility — the page should invite clicking around, not feel like a data dump.

**Key Characteristics:**
- Committed color strategy on identity-driven surfaces: Threat Magenta carries real visual weight, not a 10%-of-screen accent dab.
- Flat by default — depth comes from tonal layering (bg → surface → raised surface), not drop shadows.
- One shared easing curve and a complete hover → focus → active state chain on every interactive card; quiet at rest, decisive on interaction.
- A strict two-tier information hierarchy wherever a section would otherwise become a flat repeated grid: a small set of featured, live-aware cards, plus a visually quieter compact-row tier for everything secondary.

## 2. Colors

The palette is built on one true-neutral-leaning-cool background with two signal hues doing the real communicative work, plus a bounded family of category hues for wayfinding between game modes.

### Primary
- **Threat Magenta** (`oklch(0.62 0.190 330)`): the sitewide interactive/primary-action color — nav active state, every keyboard focus ring, primary CTAs, and the "urgent/undecided" verdict state. Reserved for interactive and primary-action semantics only; it does not double as any single game mode's identity color.

### Secondary
- **IFF Green** (`oklch(0.72 0.150 165)`): positive/friendly signal — win states, safe-win verdicts, ore-gain positives, "all clear" status. The counter-signal to Threat Magenta in the IFF metaphor: magenta reads hostile/urgent, green reads friendly/resolved.

### Tertiary
- **War Amber** (`oklch(0.68 0.170 55)`): War's own dedicated mode color, deliberately distinct from Threat Magenta so "this is War" and "this is selected/focused" are never the same visual signal on the page at once.

### Neutral
- **Gunmetal Black** (`oklch(0.10 0.004 330)`, `--bg`): page background. Near-black with a whisper of cool tint toward the brand hue, not a pure achromatic black.
- **Scope Housing** (`oklch(0.16 0.010 330)`, `--surface`): resting surface for every card — tickets, tiles, compact rows, stat cells.
- **Scope Housing, Raised** (`oklch(0.21 0.012 330)`, `--surf2`): the hover/active surface one step up the tonal ramp.
- **Bezel Line** (`oklch(0.28 0.014 330)`, `--border`): default card/divider border.
- **Readout White** (`oklch(0.95 0.006 330)`, `--text`): primary text.
- **Dim Readout** (`oklch(0.66 0.014 330)`, `--muted`): secondary/meta text, labels, timestamps.

### Semantic / Category Colors
- **Raid Red** (`oklch(0.60 0.200 25)`): Raid mode identity, plus loss/danger states generally (e.g. "Out of Reach" war verdict, defeat scores).
- **CWL Violet** (`oklch(0.62 0.170 290)`): CWL mode identity.
- **Recon Blue** (`oklch(0.68 0.140 230)`): Ranked mode identity.
- **Caution Amber** (`oklch(0.78 0.150 85)`): tie/warning states, distinct from War Amber despite the shared name root — used for score ties and the `badge-warning` judgment tier.
- **Star Gold** (`oklch(0.83 0.165 90)`): reserved specifically for in-game star ratings (★), matching the game's own iconography rather than any UI category.

### Named Rules
**The One Hue, One Job Rule.** Threat Magenta means "interactive or primary," never "this belongs to War." War, Raid, CWL, and Ranked each carry their own dedicated hue so a color never has to answer two different questions at once.

**The Tonal Depth Rule.** Depth is bg → surface → raised-surface, not shadow. If an element needs to read as "above" its neighbor, step it one tonal level up; reach for `box-shadow` only on floating overlay chrome (dropdowns, tooltips) that genuinely leaves the document flow.

## 3. Typography

**Display Font:** Big Shoulders Display (with `sans-serif` fallback)
**Body Font:** Manrope (with `sans-serif` fallback)
**Label/Mono Font:** JetBrains Mono (with `monospace` fallback); Rajdhani for the sitewide judgment-badge vocabulary specifically

**Character:** A condensed, uppercase display face for anything that needs to shout briefly (page titles, section headers) paired with a warm, humanist sans for everything read at length — the contrast is structural (condensed display vs. open body), not just a weight change.

### Hierarchy
- **Display** (800, `clamp(30px, 6vw, 52px)`, line-height 1): sitewide page-header titles (e.g. "CLAN ROSTER" on other pages). Uppercase, letter-spacing 0.5px.
- **Headline** (800, `clamp(22px, 2.6vw, 30px)`, line-height 1): band-level section headers on this page — the clan name, "Command Deck," the You-band welcome line. Uppercase, letter-spacing 0.4px.
- **Title** (700, 19px, line-height 1.2): component-level headings — Command Deck tile titles, footer brand heading (18px variant).
- **Body** (400–500, 13–15px, line-height 1.5–1.6): descriptions, footer copy. Caption variant at 11–12px for meta text (timestamps, ticket meta) at the same weight.
- **Label** (700, 10–11px, letter-spacing 1–1.4px, uppercase): tile tags, ticket-state chips, section labels like "REPORTS & TOOLS."
- **Data** (600–700, JetBrains Mono, sized by prominence from 13px inline stats up to 32px hero numbers): every score, stat, and ore value on the page. Monospace is load-bearing here — it's what lets stacked numbers align without a table.

### Named Rules
**The Numbers Are Mono Rule.** Any value a user reads as data — a score, a count, a stat — renders in JetBrains Mono, full stop. Manrope carries everything else. Mixing the two inside a single stat is the tell that a page was assembled, not designed.

## 4. Elevation

Flat by default. This system does not use drop shadows to lift cards off the surface — every card (ticket, tile, compact row, stat cell) sits at the same elevation and communicates state through border color, background tint, and tonal-layer shift on hover, never through a shadow. Shadows are reserved narrowly for chrome that actually leaves the document flow: dropdown menus, tooltips, the mobile nav panel.

### Shadow Vocabulary
- **Overlay shadow** (`box-shadow: 0 8px 24px rgba(0,0,0,.5)` to `0 12px 32px rgba(0,0,0,.55)`, scaled to the overlay's size): dropdown menus, tooltips, the mobile burger panel. Pure black, not brand-tinted — these are structural "this is floating above everything" cues, not decoration.
- **Status glow** (`box-shadow: 0 0 5–6px color-mix(in oklch, <semantic-color> 50–55%, transparent)`): a soft colored halo behind small status indicators (nav sync dots, the footer's "operational" dot, the live-pulse dot). Purely additive — the dot's fill color already carries the meaning; the glow is atmosphere, not information.

### Named Rules
**The Flat Deck Rule.** Cards never cast a shadow to prove they're clickable. A card's clickability is carried by its border, its hover tonal-shift, and its cursor — not by pretending it's floating above the surface it's actually flush with.

## 5. Components

Quiet at rest, decisive on interaction: every interactive element in this system holds a genuinely flat, low-contrast resting state, then responds unambiguously on hover and press. Nothing announces itself before it's touched.

### Tickets
- **Shape:** full-perimeter border, mode-tinted (`{rounded.lg}`, 10px) — never a side-stripe accent.
- **Identity:** border color and a 5%-opacity full-surface background tint both derive from the mode's category color (`color-mix(in oklch, var(--mode) 30%, var(--ops-line))` for the border, 5% for the wash).
- **Live indicator:** a 6px dot in the mode color, pulsing (1.8s ease-in-out, opacity 1→0.35) only while genuinely live; static otherwise. Pulse suppressed entirely under `prefers-reduced-motion: reduce`.
- **Hover / Active:** `translateY(-2px)` + one-tonal-step-lighter background on hover (150ms, `cubic-bezier(0.25,1,0.5,1)`); adds `scale(0.99)` and drops to 100ms on press. Hover/press transforms are removed entirely under reduced motion.
- **Verdict chip:** a small pill (10px, uppercase, 700) using the same color-mix formula as the ticket border but at higher opacity (12–35%), independent of the ticket's own mode color — a war ticket's "Safe Win" chip renders in IFF Green even though the ticket itself is War Amber.

### Featured Tiles
- **Shape:** `{rounded.lg}` (10px), same full-border + tint-wash treatment as Tickets, larger internal padding (22px/24px vs. 18px/20px) to read as the more prominent tier.
- **Icon box:** 40px rounded square (`{rounded.md}`), neutral background, nudges to `scale(1.08)` on parent hover.
- **Reserved for a small, bounded, meaningful set** (the four live game modes) — not a general-purpose card. A flat grid of 6+ identical tiles is the AI-slop tell this system explicitly avoids; four featured tiles differentiated by color + live-state is the accepted exception.

### Compact Rows
- **Shape:** `{rounded.md}` (8px), single-line icon + bold label + one-line sub-label, flex-wrap layout, no description paragraph.
- **Use:** the quiet tier under Featured Tiles ("Reports & Tools") and the demoted state for anything that was a full Ticket but isn't currently live ("Last completed"). Same component in both places — this tier is a structural pattern, not a one-off.
- **Icon:** 30px rounded square, neutral, nudges to `scale(1.08)` on hover, matching Featured Tiles' icon behavior at a smaller scale.

### Verdict / Judgment Badges
- **Style:** pill shape (`{rounded.pill}`, 20px), 12px Rajdhani uppercase text, background at 8–15% opacity of the badge's semantic color, border at 15–40% opacity of the same color, text at full color.
- **Vocabulary:** godlike (CWL Violet) → dominant (Threat Magenta) → wow (IFF Green) → good (Recon Blue) → warning (Caution Amber) → suck (Raid Red) → useless/inactive (Dim Readout, dashed border for `undefined`).
- **Rule:** every badge tier maps to exactly one color across the entire site; a "wow" verdict is IFF Green everywhere it appears, never re-themed per page.

### Stat Cells
- **Shape:** no independent border-radius of their own — they live inside a shared-border container (`{rounded.lg}`) with internal 1px dividers between cells.
- **Content:** JetBrains Mono value (Data role) over a Manrope caption label (Body role, 10.5–12px).
- **Hover / Active:** `translateY(-1px)` background shift on hover, `scale(0.97–0.98)` on press — a smaller lift than Tickets/Tiles since these are denser, more numerous elements.

### Navigation
- **Style:** sticky top bar, `backdrop-filter: blur(20px)` over a semi-transparent Gunmetal Black — the one sanctioned use of glass-style blur in the system, justified because it's a functional always-on-top sticky header, not decoration.
- **Active state:** background tint only (`color-mix` of Threat Magenta at low opacity), on desktop (`.nl-active`) and mobile (`.nmp-active`) alike; **never** a side-stripe border.
- **Status dots:** 7px filled circles, color = sync-health state, each keyboard-focusable with a spoken-word `aria-label` ("War sync: Error, 481h ago") rather than relying on the hover-only visual tooltip alone.
- **Mobile:** collapses to a full-width slide-down panel below 900px; dropdown submenus are hover-only on desktop (a known gap, not yet keyboard-reachable — see Do's and Don'ts).

### Action Buttons
- **Shape:** `{rounded.sm}` (6px), transparent background, Threat-Magenta text and border at rest.
- **Hover:** fills to a low-opacity Threat Magenta wash, border goes solid, adds a soft magenta glow (`box-shadow`).
- **Use:** shared controls bar (filters, period toggles) on other pages built on this same token system.

### Scrollbars
- **Any internal scroll region** — equal-height console panes, capped feeds, overflow lists — uses a **thin, inset, theme-tinted** scrollbar, never the native OS bar. The chunky native bar reads as "stuck on" over the flat gunmetal surfaces.
- **Recipe:** `scrollbar-width: thin` + `scrollbar-color` (Firefox); an 11px `::-webkit-scrollbar` with a transparent track and a thumb of `color-mix(in oklch, var(--muted) 38%, transparent)`, `border: 3px solid transparent; background-clip: padding-box` so the thumb floats inset, going to ~62% on hover.
- The page's own (document) scrollbar stays the browser default — only *in-page* scroll containers get restyled.

### Mobile Roster (responsive data table)
- When a dense desktop table (many players × many stats) drops below its breakpoint, it becomes a **single bordered container of divided rows** — one player per row (`.mr`), two tight lines: identity + verdict/chevron on top, a wrap of Mono stats below, tap-to-expand for detail. **Never** a stack of full-width per-player cards.
- **Why:** the table's whole value is scanning many players at a glance; a card-per-player spends a full block of vertical space on each and destroys that. This is the shared pattern across every data-table page (battles, raid) — reuse it, don't reinvent a card layout per page (see Don'ts).

### War Detail unit (shared, mode-parameterized)
- The M1–M6 clan-war unit (scoreboard · win projection · roster ledger/map · verdict table · matchup · attack log) lives in one shared partial pair (`templates/war/_war_detail_unit.html` + `_war_unit_style.html`) rendered by **both** `/war` and `/cwl` — a single source so the two pages can't drift.
- **Mode hue is parameterized:** the unit's CSS reads `var(--unit-mode, var(--ops-war))` throughout, so `/war` falls back to **War Amber** and `/cwl` sets `--unit-mode: var(--purple)` on its wrapper for **CWL Violet**. Reuse on a new page = include the partial, set `--unit-mode`, and pass the `u` (a `_build_war_detail`-shaped detail dict) + `opt` (attacks-per-war, editor flags, API endpoints) it expects.
- Win/loss semantics stay independent of the mode hue: a win chip is IFF Green and a loss is Raid Red whether the unit renders Amber or Violet — the mode color answers "which game mode," never "what result."

## 6. Do's and Don'ts

### Do:
- **Do** use OKLCH for every color token — no hex, no HSL. It's what lets the tonal-layer ramps (bg → surface → raised) stay perceptually even.
- **Do** give every game mode its own dedicated hue, distinct from Threat Magenta. War Amber exists specifically so War never shares a color with "selected/focused."
- **Do** carry a verdict, not just a number, wherever the underlying logic supports one (Safe Win / Out of Reach / Undecided, not just a raw star count) — this is PRODUCT.md's "verdicts over raw numbers" principle made visual.
- **Do** give every interactive card the full state chain: resting, hover (lift + tonal shift), focus-visible (2px Threat Magenta outline), active/press (scale-down, faster transition). A card missing `:active` feedback is an unfinished component here.
- **Do** respect `prefers-reduced-motion: reduce` for every transform-based hover/press effect and the live-dot pulse — drop straight to the resting position, don't just shorten the transition.
- **Do** reuse the Compact Row component wherever a section needs a quiet secondary tier, instead of inventing a new small-card pattern per page.
- **Do** confine gradient fills to the **brand marks only** — the nav crest and the user-avatar chip (small identity glyphs), plus the status-strip health hairline. Every surface, card, and heading stays flat; depth is tonal (bg → surface → raised), never a gradient. (Gradient *text* is separately banned below.)

### Don't:
- **Don't** use a `border-left`/`border-right` stripe greater than 1px as a colored accent on any card, list item, or nav-active state — this is PRODUCT.md and this system's explicit absolute ban.
- **Don't** use `background-clip: text` gradient text for any heading — emphasis comes from color, weight, or size, never a gradient fill.
- **Don't** reach for a drop shadow to make a card read as "elevated" or "clickable." Depth is tonal (bg → surface → raised surface); shadows are reserved for chrome that's genuinely floating (dropdowns, tooltips) or small colored status glows.
- **Don't** build a flat grid of 6+ identically-shaped icon+heading+text cards. If a section has more than ~4 meaningfully different items, split into a featured tier (Featured Tile) and a quiet tier (Compact Row) instead — this is the direct fix for the "identical card grids" AI-slop tell.
- **Don't** use raw text emoji as a **functional UI icon** — nav, controls, buttons, form fields, stat labels. Those are always a real image asset or an `aria-hidden` inline SVG matching the line-icon language (stroke-based, `currentColor`, 16–24px). **Sanctioned exception:** emoji are allowed as a deliberate accent in **celebratory / personality moments** — award chips, the MVP crown, a triple-wipe honor — where they carry the warmth PRODUCT.md explicitly asks for ("inviting, not sterile"). The line: an emoji may decorate a *moment*, never label a *control*.
- **Don't** let Threat Magenta answer more than one question on a single screen. It means "interactive/primary" — if a mode-specific color is also needed there, it must be a distinct hue (see War Amber).
- **Don't** ship a hover-only interaction with no keyboard equivalent. The nav's mode dropdowns are the one place this system currently fails that rule — fix forward from here, don't repeat it.
- **Don't** reflow a dense data table into a stack of spacious per-player cards on mobile. The table's whole value is at-a-glance comparison across rows; a card-per-player loses it. Drop to the divided roster-row list instead (see Components → Mobile Roster). This has been re-introduced and removed more than once — it is a standing preference, not a per-page judgment call.
- **Don't** let the native OS scrollbar show on an in-page scroll container — restyle it thin and inset (see Components → Scrollbars).

// Contracts in radar.css that nothing else can catch.
//
// jsdom does not run CSS, so these read the stylesheet as text. That is a
// blunt instrument and it is used for exactly one class of thing: a rule whose
// absence changes nothing visible in a test, nothing visible in a screenshot,
// and only shows up as motion quietly not happening on a real machine.
//
// Everything else about the motion pass was verified in a browser instead --
// the wipe screenshotted mid-sweep at 100/210/320ms, the frame rate measured
// during it, `--mag` sampled through an interpolation.

/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'

// Imported through Vite rather than read with `node:fs`. Two things that
// bought: the path is resolved relative to THIS file instead of to whatever
// the runner's cwd happens to be, and the suite does not need @types/node --
// which `tsc --noEmit` would otherwise demand, and that typecheck is the gate
// inside `npm run build`.
import css from '../radar.css?raw'

/** The file with comments stripped. Several assertions below look for a token
 *  that also appears in the prose explaining it. */
const rules = css.replace(/\/\*[\s\S]*?\*\//g, '')

describe('the busy board recedes without dimming text', () => {
  it('quiets the chart drawing, not the words beside it', () => {
    // The magnitude bar this block used to police retired with the
    // chart-row (2026-08-30); what recedes while a new board is in flight
    // is the chart SVG, which carries no text and so cannot fail the 4.5:1
    // floor the old opacity-on-everything version failed.
    expect(rules).toMatch(
      /\.rows\[aria-busy="true"\] \.chart svg \{[^}]*opacity/)
  })
})

describe('every reveal degrades to a finished surface', () => {
  // The rule the whole pass hangs on. A `forwards` fill holds whatever frame
  // the animation stopped on, so one frozen at 0% leaves the chart clipped to
  // nothing and the panel ships blank. A `backwards` fill falls back to the
  // element's own base state, which is the finished chart. The failure mode
  // has to be "it did not animate", never "it is not there".
  const animated = [...rules.matchAll(/animation:\s*([^;]+);/g)].map((m) => m[1]!)

  it('has animations to check', () => {
    expect(animated.length).toBeGreaterThan(3)
  })

  it('never fills forwards', () => {
    for (const decl of animated) {
      expect(decl, decl).not.toMatch(/\bforwards\b|\bboth\b/)
    }
  })

  it('states a fill mode rather than relying on the default', () => {
    for (const decl of animated) {
      expect(decl, decl).toContain('backwards')
    }
  })

  it('animates the FROM: no keyframe sets a visible end state', () => {
    // Each @keyframes here declares only `from` (or a midpoint). The `to` is
    // the element's own base rule, so an element that never animates is
    // already at its final state.
    const frames = [...rules.matchAll(/@keyframes\s+([\w-]+)\s*\{([\s\S]*?)\n\}/g)]
    expect(frames.length).toBeGreaterThan(0)
    for (const [, name, body] of frames) {
      expect(body, `@keyframes ${name}`).not.toMatch(/(^|\s)(to|100%)\s*\{/)
    }
  })
})

describe('accessibility contracts in the stylesheet', () => {
  it('does not dim the count inside a pressed filter chip', () => {
    // It was `color: var(--mark); opacity: 0.75`, which measured 3.48:1 in
    // light and 3.67:1 in dark at 11.5px -- the only text on the surface
    // under the 4.5 floor. Opacity on small text is the specific move that
    // caused it, and it is easy to reintroduce because it looks like a
    // hierarchy decision rather than a contrast one.
    const rule = rules.match(
      /\.t\[aria-pressed="true"\] \.n \{[^}]*\}/)?.[0] ?? ''
    // A vacuous match would pass on an empty string; pin that the selector
    // still exists before checking what it avoids.
    expect(rule).not.toBe('')
    expect(rule).not.toContain('opacity')
  })

  it('raises the touch targets on a coarse pointer', () => {
    // Measured at 390x844 before this: span buttons 21.4px tall against a
    // WCAG 2.5.8 floor of 24, chips exactly on the line at 24.3px.
    expect(rules).toMatch(/@media \(pointer: coarse\)/)
  })

  it('keeps the column-header styling off the row header', () => {
    // The venue cell is a `th scope="row"` so a screen reader names the venue
    // when reading a figure. Styled by a bare `.bd th` it would inherit the
    // uppercase tracked 10.5px column treatment and render "Bluesky" as a
    // column heading.
    expect(rules).toMatch(/\.bd thead th \{/)
    expect(rules).not.toMatch(/\n\.bd th \{/)
  })

  it('stacks the identity price below its facts on a 390px screen', () => {
    /* The compact USD fallback label can be longer than the available inline
       space beside an unbroken company name.  Keeping price as a flex item
       made its right edge clip; the small layout needs one full-width price
       lane instead. */
    const mobile = rules.slice(rules.indexOf('@media (max-width: 900px)'))
    expect(mobile).toMatch(/\.ident\s*\{[^}]*flex-wrap:\s*wrap/)
    expect(mobile).toMatch(/\.ident \.px\s*\{[^}]*flex-basis:\s*100%/)
    expect(mobile).toMatch(/\.ident \.px\s*\{[^}]*text-align:\s*left/)
  })
})

describe('reduced motion', () => {
  it('still turns everything off', () => {
    // Not new, but the pass above added the first real animations to this
    // file, which is what makes it load-bearing rather than decorative.
    expect(rules).toMatch(/@media \(prefers-reduced-motion: reduce\)/)
    expect(rules).toMatch(/animation-duration:\s*0\.01ms\s*!important/)
    expect(rules).toMatch(/transition-duration:\s*0\.01ms\s*!important/)
  })
})

describe('expanding retained posts', () => {
  it('does not animate the height of every post in the panel', () => {
    // The previous rule matched every retained post (25 in the measured
    // panel), forcing layout work across the reading column whenever one wall
    // of text opened. Expansion may be instant; it may not animate height.
    const postRules = rules.match(/\.post p[^{]*\{[^}]*\}/g) ?? []
    for (const rule of postRules) {
      expect(rule, rule).not.toMatch(/transition:[^;]*\bheight\b/)
    }
  })
})

describe('printing from a narrow viewport', () => {
  it('does not print controls that only make sense on a panning screen', () => {
    // Width media queries still match while Chromium renders print media. At
    // 390px the mobile return link and swipe hint leaked onto paper unless the
    // later print block explicitly hid them again.
    const print = rules.slice(rules.indexOf('@media print'))
    const hidden = print.match(/[^{}]+\{\s*display:\s*none;\s*\}/)?.[0] ?? ''
    expect(hidden).toContain('.backboard')
    expect(hidden).toContain('.panhint')
  })
})

// Static regressions on analysis.css (HA1 CORRECTION-1, REVIEW-1 P2-5 and
// P3 layout). jsdom applies no stylesheet, so these read the rules
// themselves. They are NOT rendered-pixel evidence: actual 44px targets,
// column alignment and overflow stay open for the actual-app preview.
/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest'

import css from './analysis.css?raw'

interface Rule { media: string | null; selector: string; body: string }

function parse(text: string): Rule[] {
  const rules: Rule[] = []
  const walk = (chunk: string, media: string | null) => {
    let at = 0
    while (at < chunk.length) {
      const open = chunk.indexOf('{', at)
      if (open < 0) break
      const prelude = chunk.slice(at, open).trim()
      let depth = 1
      let end = open + 1
      while (end < chunk.length && depth > 0) {
        if (chunk[end] === '{') depth += 1
        else if (chunk[end] === '}') depth -= 1
        end += 1
      }
      const inner = chunk.slice(open + 1, end - 1)
      if (prelude.startsWith('@media')) walk(inner, prelude)
      else rules.push({ media, selector: prelude, body: inner })
      at = end
    }
  }
  walk(text.replace(/\/\*[\s\S]*?\*\//g, ''), null)
  return rules
}

function px(body: string, property: string): number | null {
  const match = body.match(new RegExp(`(?:^|[;\\s])${property}\\s*:\\s*(\\d+)px`))
  return match ? Number(match[1]) : null
}

const rules = parse(css)
const NARROW = '@media (max-width: 860px)'

describe('analysis.css touch targets (P2-5)', () => {
  it('never sets a button, input or day control below 44px', () => {
    const controls = rules.filter((rule) => /rh-button|input|rh-an-day\b/.test(rule.selector))
    expect(controls.length).toBeGreaterThan(3)
    for (const rule of controls) {
      const height = px(rule.body, 'min-height')
      if (height !== null) expect(height, rule.selector).toBeGreaterThanOrEqual(44)
    }
  })

  it('raises the table day buttons to 44px at narrow widths', () => {
    const rule = rules.find((r) => r.media === NARROW && r.selector.includes(".rh-an-table th[scope='row'] .rh-textbutton"))
    expect(rule).toBeDefined()
    expect(px(rule!.body, 'min-height')).toBe(44)
    expect(px(rule!.body, 'min-width')).toBe(44)
  })

  it('keeps the range button and inputs above hub.css specificity at 44px', () => {
    for (const selector of ['.rh-an-range .rh-button', '.rh-an-range .rh-field input']) {
      const rule = rules.find((r) => r.media === null && r.selector === selector)
      expect(px(rule!.body, 'min-height'), selector).toBe(44)
    }
  })

  it('keeps seven day buttons at least 44px wide on a phone via the scroll box', () => {
    const plots = rules.find((r) => r.media === '@media (max-width: 560px)' && r.selector === '.rh-an-plots')
    const minWidth = px(plots!.body, 'min-width')!
    const column = (minWidth * (720 - 52 - 14)) / 720 / 7
    expect(column - 6).toBeGreaterThanOrEqual(44)
    expect(rules.find((r) => r.selector === '.rh-an-plotscroll')!.body).toContain('overflow-x: auto')
  })
})

describe('analysis.css range fields keep a whole date visible at 320px (F1)', () => {
  // LOCAL-QA F1: at 320px the two-column range grid left each 16px input
  // 117px wide, which clipped "2026-09-08". Phones this narrow stack the
  // fields so each input spans the form.
  it('stacks From, To and the button in one column at phone widths', () => {
    const stacked = rules.find((r) => r.media === '@media (max-width: 400px)' && r.selector === '.rh-an-range')
    expect(stacked).toBeDefined()
    expect(stacked!.body).toMatch(/grid-template-columns:\s*1fr\s*;/)
  })

  it('still lets each input shrink to the column instead of overflowing it', () => {
    const input = rules.find((r) => r.media === '@media (max-width: 760px)' && r.selector === '.rh-an-range .rh-field input')
    expect(input!.body).toMatch(/min-width:\s*0/)
    expect(input!.body).toMatch(/width:\s*100%/)
  })
})

describe('analysis.css partial count bars keep their hatch (LOCAL-QA)', () => {
  // AnalysisChart.tsx paints a partial bar with the presentation attribute
  // fill="url(#rh-an-hatch)". Any author rule that sets `fill` on an element
  // carrying .rh-an-fill.partial outranks that attribute and paints it solid.
  const selectors = rules.flatMap((rule) =>
    rule.selector.split(',').map((one) => ({ selector: one.trim(), body: rule.body })))
  const fill = (body: string) => body.match(/(?:^|[;\s])fill\s*:\s*([^;]+)/)?.[1]?.trim() ?? null

  it('sets no author fill that can reach a partial bar', () => {
    const reaching = selectors.filter(({ selector }) =>
      /\.rh-an-fill\b/.test(selector) && !selector.includes(':not(.partial)'))
    expect(reaching.length).toBeGreaterThan(0)
    for (const { selector, body } of reaching) expect(fill(body), selector).toBeNull()
  })

  it('keeps full bars solid chatter and partial bars outlined', () => {
    const full = selectors.filter(({ selector }) => selector.includes('.rh-an-fill:not(.partial)'))
    expect(full.map(({ body }) => fill(body))).toEqual(['var(--chatter)'])
    const partial = selectors.find(({ selector }) => selector === '.rh-an-fill.partial')
    expect(partial!.body).toMatch(/stroke:\s*var\(--chatter\)/)
  })
})

describe('analysis.css chart alignment and empty states (P3)', () => {
  it('puts no fixed px padding or gap between the day button columns', () => {
    for (const rule of rules.filter((r) => r.selector === '.rh-an-days')) {
      expect(rule.body).not.toMatch(/padding(-left|-right)?\s*:/)
      expect(rule.body).toMatch(/gap:\s*0/)
    }
  })

  it('does not cap panel height, which would letterbox the columns', () => {
    for (const rule of rules.filter((r) => r.selector.includes('rh-an-svg'))) {
      expect(rule.body).not.toContain('max-height')
    }
  })

  it('styles SVG empty text and the HTML empty state separately', () => {
    expect(rules.some((r) => r.selector === '.rh-an-emptytext' && r.body.includes('fill'))).toBe(true)
    const htmlEmpty = rules.filter((r) => /rh-an-empty\b/.test(r.selector))
    expect(htmlEmpty.length).toBeGreaterThan(0)
    for (const rule of htmlEmpty) expect(rule.body).not.toContain('fill')
  })
})

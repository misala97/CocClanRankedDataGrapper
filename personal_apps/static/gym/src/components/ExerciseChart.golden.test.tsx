/**
 * Golden-master: the React chart must draw exactly what the Jinja chart drew.
 *
 * The fixture holds real geometry from the dev database alongside the SVG the
 * Jinja template rendered from that same geometry, captured before the
 * template was replaced. Unit tests prove the component behaves; this proves
 * it is the *same drawing*, which is the actual promise of the port.
 *
 * Two cases, because the default view resolves to a single position slot and
 * therefore only ever plots one series -- the per-slot P-labels and the
 * opacity/stroke-width ramps are unreachable there. ?position=all is the
 * comparison view and the only way to reach them.
 *
 * Regenerate with `python scripts/make_chart_fixture.py` only when
 * _chart_geometry legitimately changes shape. Do NOT regenerate to make a
 * failure go away -- a diff here means the drawing moved. Once the template is
 * a React shell the Jinja side is gone and this fixture is the only surviving
 * record of the original, which is the point.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExerciseChart } from './ExerciseChart'
import golden from './__fixtures__/chart-golden.json'
import type { ChartGeometry } from '../types'

interface GoldenCase {
  exercise_id: number
  query: string
  chart: unknown
  session_count: number
  first_date: string
  last_date: string
  jinja_svg: string
}

/** "12" and "12.0" are the same SVG coordinate; compare numerically so
 *  serialization differences do not read as movement. */
function normalize(value: string | null): string {
  if (value === null) return ''
  const asNumber = Number(value)
  return Number.isFinite(asNumber) && value.trim() !== ''
    ? String(asNumber)
    : value.replace(/\s+/g, ' ').trim()
}

/** React serializes a style object with a trailing semicolon and Jinja's
 *  literal does not. A trailing semicolon in a CSS declaration list is
 *  optional and changes nothing, so compare the declarations themselves. */
function normalizeStyle(value: string): string {
  return value.split(';').map((d) => d.trim()).filter(Boolean).sort().join('; ')
}

function shapes(svg: Element, tag: string) {
  return [...svg.querySelectorAll(tag)].map((el) => {
    const attrs: Record<string, string> = {}
    for (const a of [...el.attributes]) {
      attrs[a.name] = a.name === 'style' ? normalizeStyle(a.value) : normalize(a.value)
    }
    return attrs
  })
}

const collapse = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim()

const cases = golden as unknown as Record<string, GoldenCase>

describe.each(Object.entries(cases))(
  'ExerciseChart against the Jinja original (%s)',
  (_name, snapshot) => {
    const parsed = new DOMParser()
      .parseFromString(snapshot.jinja_svg, 'image/svg+xml')
      .documentElement

    const { container } = render(
      <ExerciseChart
        chart={snapshot.chart as ChartGeometry}
        sessionCount={snapshot.session_count}
        firstDate={snapshot.first_date}
        lastDate={snapshot.last_date}
      />)
    const mine = container.querySelector('svg')!

    it('draws the same lines', () => {
      expect(shapes(mine, 'line')).toEqual(shapes(parsed, 'line'))
    })

    it('draws the same circles', () => {
      expect(shapes(mine, 'circle')).toEqual(shapes(parsed, 'circle'))
    })

    it('draws the same series labels', () => {
      expect(shapes(mine, 'text')).toEqual(shapes(parsed, 'text'))
      expect([...mine.querySelectorAll('text')].map((t) => t.textContent))
        .toEqual([...parsed.querySelectorAll('text')].map((t) => t.textContent))
    })

    it('applies the same per-series opacity', () => {
      const opacity = (root: Element) =>
        [...root.querySelectorAll('.chart__ink > g')]
          .map((g) => normalize(g.getAttribute('opacity')))
      expect(opacity(mine)).toEqual(opacity(parsed))
    })

    it('uses the same viewBox', () => {
      expect(normalize(mine.getAttribute('viewBox')))
        .toBe(normalize(parsed.getAttribute('viewBox')))
    })

    it('carries the same accessible description', () => {
      // The Jinja label was written across several source lines, which HTML
      // collapses to single spaces; normalize both sides the same way.
      expect(collapse(mine.getAttribute('aria-label')))
        .toBe(collapse(parsed.getAttribute('aria-label')))
    })

    it('is not comparing against an empty fixture', () => {
      expect(shapes(parsed, 'circle').length).toBeGreaterThan(2)
      expect(shapes(parsed, 'line').length).toBeGreaterThan(3)
    })
  })

it('covers the multi-series case, which single-position views cannot reach', () => {
  expect(Object.keys(cases)).toContain('multi_series')
  const multi = cases.multi_series!
  expect((multi.chart as ChartGeometry).series.length).toBeGreaterThan(1)
})

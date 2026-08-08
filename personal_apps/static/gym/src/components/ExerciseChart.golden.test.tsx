/**
 * Golden-master: the React chart must draw exactly what the Jinja chart drew.
 *
 * The fixture holds real geometry from the dev database alongside the SVG the
 * Jinja template rendered from that same geometry, captured before the
 * template was replaced. Unit tests prove the component behaves; this proves
 * it is the *same drawing*, which is the actual promise of the port.
 *
 * Regenerate with scripts/make_chart_fixture.py if _chart_geometry changes
 * shape. Do not regenerate to make a failure go away -- a diff here means the
 * drawing moved.
 *
 * Known gap: the dev database has no exercise plotted in two positions with
 * enough history, so the fixture is single-series and the per-series P-labels
 * are covered only by ExerciseChart.test.tsx.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExerciseChart } from './ExerciseChart'
import golden from './__fixtures__/chart-golden.json'
import type { ChartGeometry } from '../types'

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

function shapes(svg: SVGElement | Element, tag: string) {
  return [...svg.querySelectorAll(tag)].map((el) => {
    const attrs: Record<string, string> = {}
    for (const a of [...el.attributes]) {
      attrs[a.name] = a.name === 'style'
        ? normalizeStyle(a.value)
        : normalize(a.value)
    }
    return attrs
  })
}

describe('ExerciseChart against the Jinja original', () => {
  const chart = golden.chart as unknown as ChartGeometry
  const parsed = new DOMParser()
    .parseFromString(golden.jinja_svg, 'image/svg+xml')
    .documentElement

  const { container } = render(
    <ExerciseChart
      chart={chart}
      sessionCount={golden.session_count}
      firstDate={golden.first_date}
      lastDate={golden.last_date}
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
  })

  it('uses the same viewBox', () => {
    expect(normalize(mine.getAttribute('viewBox')))
      .toBe(normalize(parsed.getAttribute('viewBox')))
  })

  it('carries the same accessible description', () => {
    // The Jinja label was written across several source lines, which HTML
    // collapses to single spaces; normalize both sides the same way.
    const collapse = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim()
    expect(collapse(mine.getAttribute('aria-label')))
      .toBe(collapse(parsed.getAttribute('aria-label')))
  })

  it('is not comparing against an empty fixture', () => {
    expect(shapes(parsed, 'circle').length).toBeGreaterThan(2)
    expect(shapes(parsed, 'line').length).toBeGreaterThan(3)
  })
})

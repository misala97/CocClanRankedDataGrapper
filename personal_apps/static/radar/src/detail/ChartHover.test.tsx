import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ChartHover, whenLabel } from './ChartHover'
import type { DetailChart } from '../types'

function chart(over: Partial<DetailChart> = {}): DetailChart {
  return {
    from: '2026-08-20T00:00:00Z', span: '1M', step_minutes: 1440,
    closes: [null, 1.5, 1.7, null, 2.1],
    chatter: [null, null, 4, 0, 9],
    normal_per_slot: 2, sessions: [], watched_from: '2026-08-22',
    currency: null, basis_venue: null, converted_from: null,
    priced_from: 'daily',
    ...over,
  }
}

const geometry = { priced: true, low: 1.5, high: 2.1, peak: 9, band: 0.52 }

function hover(over: Partial<DetailChart> = {}) {
  const utils = render(
    <svg><ChartHover chart={chart(over)} geometry={geometry} /></svg>)
  return { ...utils, hit: utils.container.querySelector('.hover-hit')! }
}

describe('the chart answering the cursor', () => {
  it('shows nothing until the pointer is in the plot', () => {
    const { container } = hover()

    expect(container.querySelector('.hover-readout')).toBeNull()
  })

  it('reads out the slot under the pointer, and clears when it leaves', () => {
    /* jsdom has no SVG geometry, so every pointer lands on slot 0 -- which
       is also the interesting slot: before watching began, with no close. */
    const { container, hit } = hover()

    fireEvent.pointerMove(hit, { clientX: 10, clientY: 10 })
    const lines = [...container.querySelectorAll('.hover-text')].map((t) => t.textContent)
    expect(lines).toEqual(['20 Aug 2026', 'no close', 'not observed'])
    expect(container.querySelector('.hover-line')).not.toBeNull()

    fireEvent.pointerLeave(hit)
    expect(container.querySelector('.hover-readout')).toBeNull()
  })

  it('never invents a number: a zero count is a zero, an unobserved slot is not', () => {
    const { container, hit } = hover({
      closes: [1.5, 1.6], chatter: [0, null], from: '2026-08-25T00:00:00Z',
    })

    fireEvent.pointerMove(hit, { clientX: 0, clientY: 0 })

    const lines = [...container.querySelectorAll('.hover-text')].map((t) => t.textContent)
    expect(lines).toEqual(['25 Aug 2026', '$1.50', '0/d'])
    expect(container.querySelectorAll('.hover-dot')).toHaveLength(2)
  })

  it('names the instant exactly, in Berlin time, per span grain', () => {
    expect(whenLabel(chart(), 2)).toBe('22 Aug 2026')
    expect(whenLabel(chart({ from: '2026-09-01T12:00:00Z', step_minutes: 15 }), 3))
      .toBe('1 Sep 2026 · 14:45')
  })
})

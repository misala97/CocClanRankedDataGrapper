import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ChatterHistogram, percentageText, poolHistogram } from './ChatterHistogram'
import type { DetailChart } from '../types'

const chart = (over: Partial<DetailChart> = {}): DetailChart => ({
  from: '2026-09-13T00:00:00Z', span: '1D', step_minutes: 15,
  closes: [100, 101], chatter: [10, 0, null], sessions: [],
  normal_per_slot: null, watched_from: null, currency: 'USD',
  basis_venue: 'XNAS', priced_from: 'intraday',
  chatter_tone: {
    version: 1, basis: 'recorded-judgments', calculated_at: '2026-09-13T01:00:00Z',
    retained_from: '2026-09-11T01:00:00Z',
    slots: [
      { bullish: 4, bearish: 2, neutral: 1, unjudged: 3, unavailable: 0,
        status: 'complete' },
      { bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: 0,
        status: 'complete' },
      null,
    ],
  },
  ...over,
})

describe('ChatterHistogram', () => {
  it('uses the full interval total as the percentage denominator', () => {
    expect(percentageText(4, 10)).toBe('40%')
    expect(percentageText(0, 0)).toBe('—')
  })

  it('keeps mixed tone categories and unobserved gaps separate', () => {
    const bins = poolHistogram(chart())
    expect(bins[0]?.slot).toMatchObject({ bullish: 4, bearish: 2, neutral: 1, unjudged: 3 })
    expect(bins[2]?.total).toBeNull()
  })

  it('inspects an interval by tap and keyboard without one tab stop per bar', async () => {
    const user = userEvent.setup()
    const { container } = render(<ChatterHistogram chart={chart()} />)
    const cursor = screen.getByRole('group', { name: /chatter tone intervals/i })
    expect(cursor).toHaveAttribute('tabindex', '0')
    expect(screen.getByText(/total 10 mentions/i)).toBeVisible()
    await user.click(container.querySelector('rect')!)
    await user.click(cursor)
    await user.keyboard('{ArrowRight}')
    expect(screen.getByText(/total 0 mentions/i)).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByText(/total 0 mentions/i)).not.toBeInTheDocument()
  })

  it('explains an absent tone envelope instead of colouring by guess', () => {
    render(<ChatterHistogram chart={chart({ chatter_tone: undefined })} />)
    expect(document.querySelector('.chatter-interval-detail')).toHaveTextContent(
      /tone unavailable/i)
  })
})


describe('histogram reconciliation and geometry', () => {
  it('does not bridge an unobserved day while pooling a long span', () => {
    const values = Array<number | null>(402).fill(2)
    values[1] = null
    const bins = poolHistogram(chart({ chatter: values, chatter_tone: undefined }))
    expect(bins.slice(0, 3).map(bin => [bin.start, bin.end, bin.total]))
      .toEqual([[0, 1, 2], [1, 2, null], [2, 4, 4]])
  })

  it('preserves verified colour while assigning absent evidence to unavailable', () => {
    const base = chart()
    const bins = poolHistogram(chart({ chatter: Array(402).fill(10),
      chatter_tone: { ...base.chatter_tone!, slots: [base.chatter_tone!.slots[0]!] } }))
    expect(bins[0]?.slot).toMatchObject({ bullish: 4, bearish: 2, unavailable: 10, status: 'partial' })
    expect(bins[0]?.total).toBe(20)
  })

  it('refuses an overfull partition instead of producing negative unavailable counts', () => {
    const base = chart()
    base.chatter_tone!.slots[0]!.bullish = 100
    expect(poolHistogram(base)[0]?.slot).toMatchObject({ bullish: 0, unavailable: 10, status: 'unavailable' })
  })

  it('uses one zero-based scale for normal volume and each stacked segment', () => {
    const { container } = render(<ChatterHistogram chart={chart({ normal_per_slot: 20 })} />)
    const rects = [...container.querySelectorAll('rect[data-tone]')].slice(0, 5)
    const heights = rects.map(rect => Number(rect.getAttribute('height')))
    expect(heights.reduce((a, b) => a + b, 0)).toBeCloseTo(132)
    expect(heights[0]! / heights[1]!).toBeCloseTo(2)
    expect(container.querySelector('line.tone-normal')).toHaveAttribute('y1', '8')
  })

  it('allows tapping a zero-volume interval', async () => {
    const { container } = render(<ChatterHistogram chart={chart()} />)
    await userEvent.click(container.querySelectorAll('rect.tone-hit')[1]!)
    expect(screen.getByText(/total 0 mentions/i)).toBeVisible()
    expect(container.querySelector('.chatter-interval-detail')).not.toHaveTextContent('NaN')
  })
})


it('keeps bullish and bearish colours independent of the price chart tokens', () => {
  const { container } = render(<ChatterHistogram chart={chart()} />)
  expect(container.querySelector('[data-tone="bullish"]')).toHaveAttribute('fill', '#45dda0')
  expect(container.querySelector('[data-tone="bearish"]')).toHaveAttribute('fill', '#ff6b7c')
})

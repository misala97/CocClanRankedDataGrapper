import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ChatterHistogram, percentageText, poolHistogram } from './ChatterHistogram'
import type { DetailChart } from '../types'

const chart = (over: Partial<DetailChart> = {}): DetailChart => ({
  from: '2026-09-13T00:00:00Z', span: '1D', step_minutes: 15,
  closes: [100, 101], chatter: [10, 0, null], sessions: [],
  normal_per_slot: null, watched_from: null, currency: 'USD',
  basis_venue: 'XNAS', converted_from: null, priced_from: 'intraday',
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

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Spend } from './Spend'
import type { BoardPayload } from '../types'

const payload = (spend?: {
  today_usd: number
  month_usd: number
  unpriced_tokens: number
}) =>
  ({ spend, excluded: {}, rows: [] } as unknown as BoardPayload)

describe('the spend footnote', () => {
  it('reports today and the month', () => {
    render(<Spend payload={payload({ today_usd: 0.196, month_usd: 4.12, unpriced_tokens: 0 })} />)

    expect(screen.getByText(/\$0\.196/)).toBeTruthy()
    expect(screen.getByText(/\$4\.12/)).toBeTruthy()
  })

  it('says nothing before the first pass has booked anything', () => {
    /* A meter reading $0.00 is a claim that nothing was spent. Having nothing
       to report yet is a different fact, and the difference matters on the
       first day the key is installed -- when "$0.00" would look like proof
       the pass was running when it was not. */
    const { container } = render(<Spend payload={payload(undefined)} />)

    expect(container.textContent).toBe('')
  })

  it('is silent on a zero rather than drawing an empty band', () => {
    const { container } = render(
      <Spend payload={payload({ today_usd: 0, month_usd: 0, unpriced_tokens: 0 })} />)

    expect(container.textContent).toBe('')
  })

  it('drops to cents once there are dollars to round', () => {
    /* Three places below a dollar: at two decimal places a sub-dollar spend
       ("$0.20") reads as a rounding of something unknown. Above a dollar the
       third place is noise. */
    render(<Spend payload={payload({ today_usd: 1.5, month_usd: 12.345, unpriced_tokens: 0 })} />)

    expect(screen.getByText(/\$1\.50/)).toBeTruthy()
    expect(screen.getByText(/\$12\.35/)).toBeTruthy()
  })

  it('surfaces tokens that have no price without inventing one', () => {
    render(<Spend payload={payload({
      today_usd: 0,
      month_usd: 0,
      unpriced_tokens: 501_000,
    })} />)

    expect(screen.getByText(/tokens at an unknown rate/)).toBeTruthy()
  })

  it('groups the token count the way every other figure here is grouped', () => {
    /* A bare toLocaleString() follows the READER's locale. Under a German one
       this rendered `1.284.392` -- the only figure on a surface that is
       otherwise entirely en-US and UTC. Seen on the running board. */
    render(<Spend payload={payload({
      today_usd: 0, month_usd: 0, unpriced_tokens: 1_284_392,
    })} />)

    expect(screen.getByText(/1,284,392 tokens/)).toBeTruthy()
  })
})

describe('the review meter line', () => {
  const withReview = (review: {
    demanded: number; attempted: number; served: number
    capped: number; over_ceiling: number
  }) =>
    ({
      spend: { today_usd: 1.0, month_usd: 2.0, unpriced_tokens: 0 },
      sentiment_ops: { pending: 3, p95_age_minutes: 4, review },
      excluded: {},
      rows: [],
    } as unknown as BoardPayload)

  it('shows served over unique demand once the tier wants anything', () => {
    render(
      <Spend
        payload={withReview({ demanded: 12, attempted: 9, served: 8, capped: 3, over_ceiling: 1 })}
      />,
    )

    expect(screen.getByText(/Review:/)).toBeTruthy()
    expect(screen.getByText(/12 served/)).toBeTruthy()
    expect(screen.getByText(/3 capped/)).toBeTruthy()
  })

  it('stays silent while the review tier has demanded nothing', () => {
    const { container } = render(
      <Spend
        payload={withReview({ demanded: 0, attempted: 0, served: 0, capped: 0, over_ceiling: 0 })}
      />,
    )

    expect(container.textContent).not.toContain('Review')
  })
})

describe('the judge gate line', () => {
  it('says how many mentions the gate left unread', () => {
    const withGate = {
      spend: { today_usd: 0.42, month_usd: 3.1, unpriced_tokens: 0 },
      sentiment_ops: { pending: 12, gated_pending: 1234, p95_age_minutes: 3,
        review: { demanded: 0, attempted: 0, served: 0, capped: 0, over_ceiling: 0 } },
      excluded: {}, rows: [],
    } as unknown as BoardPayload
    render(<Spend payload={withGate} />)

    expect(screen.getByText(/1,234/)).toBeInTheDocument()
    expect(screen.getByText(/left unread/)).toBeInTheDocument()
  })

  it('says nothing while the gate has held nothing back', () => {
    const quiet = {
      spend: { today_usd: 0.42, month_usd: 3.1, unpriced_tokens: 0 },
      sentiment_ops: { pending: 12, gated_pending: 0, p95_age_minutes: 3,
        review: { demanded: 0, attempted: 0, served: 0, capped: 0, over_ceiling: 0 } },
      excluded: {}, rows: [],
    } as unknown as BoardPayload
    const { container } = render(<Spend payload={quiet} />)

    expect(container.textContent).not.toMatch(/unread/)
  })
})

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

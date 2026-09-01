import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SpendMark } from './Spend'
import type { BoardPayload } from '../types'

const payload = (spend?: BoardPayload['spend']): BoardPayload =>
  ({ spend } as BoardPayload)

describe('the spend mark in the masthead', () => {
  it('says today\'s figure and carries the month for anyone who asks', () => {
    /* The full sentence sits at the foot of the list, after the excluded
       account and the marks legend -- 2,660px down a 24h board and off the
       pane's bottom edge even on an empty one (Michi, 2026-09-02: "where is
       the api usage? i can't find it"). The masthead gets the one figure
       that changes during a day. */
    render(<SpendMark payload={payload({
      today_usd: 0.00108, month_usd: 0.42, unpriced_tokens: 0,
    })} />)

    const mark = screen.getByTitle(/spent reading tone today/)
    expect(mark).toHaveTextContent(/^\$0\.001 today/)
    // Not an aria-label: a bare span is naming-prohibited, so the month
    // travels as hidden text a screen reader actually reaches.
    expect(mark.querySelector('.aural')).toHaveTextContent('$0.42 this month')
    expect(mark).not.toHaveAttribute('aria-label')
  })

  it('is absent until the first pass books something', () => {
    /* A "$0.000 today" before any call would look like a working meter
       reading zero, which is a different claim from nothing to report. */
    const { container, rerender } = render(<SpendMark payload={payload(undefined)} />)
    expect(container).toBeEmptyDOMElement()

    rerender(<SpendMark payload={payload({ today_usd: 0, month_usd: 0, unpriced_tokens: 0 })} />)
    expect(container).toBeEmptyDOMElement()
  })
})

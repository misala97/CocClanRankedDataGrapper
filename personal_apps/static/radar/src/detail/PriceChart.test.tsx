import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PriceChart } from './PriceChart'
import type { DetailChart } from '../types'

const chart = (over: Partial<DetailChart> = {}): DetailChart => ({
  from: '2025-08-23',
  span: '1Y',
  closes: Array.from({ length: 365 }, (_, i) => 1 + i / 100),
  chatter: Array.from({ length: 365 }, (_, i) => (i < 362 ? null : i)),
  watched_from: '2026-08-21',
  ...over,
})

describe('the panel chart', () => {
  it('draws a price line on every span', () => {
    /* The regression that started this rebuild. SpanChart guarded the price
       path behind `span !== "24h"` and 24h was the default, so 62,061 stored
       closes never rendered once and Michi reported the price as broken. */
    for (const span of ['1M', '6M', '1Y', '3Y'] as const) {
      const { container, unmount } = render(
        <PriceChart chart={chart({ span })} />)

      expect(container.querySelector('path.px')?.getAttribute('d'))
        .toBeTruthy()
      unmount()
    }
  })

  it('draws no chatter bar where nothing was observed', () => {
    /* null is "not watched", not "zero mentions". A zero-height bar and no
       bar look the same; a bar drawn FROM a null does not. */
    const { container } = render(<PriceChart chart={chart()} />)

    expect(container.querySelectorAll('rect.chat')).toHaveLength(3)
  })

  it('marks where watching began', () => {
    const { container } = render(<PriceChart chart={chart()} />)

    expect(container.querySelector('.watch-edge')).toBeTruthy()
  })

  it('draws no boundary when everything in view was observed', () => {
    const { container } = render(<PriceChart chart={chart({
      chatter: Array.from({ length: 365 }, (_, i) => i),
    })} />)

    expect(container.querySelector('.watch-edge')).toBeNull()
  })

  it('spans the days the market was shut rather than breaking the line', () => {
    /* A weekend is not a day the price stopped existing. Breaking there would
       render a year as 52 fragments. */
    const { container } = render(<PriceChart chart={chart({
      closes: [1, null, null, 4, null, 6],
      chatter: [null, null, null, null, null, null],
    })} />)

    const d = container.querySelector('path.px')!.getAttribute('d')!
    expect(d.match(/M/g)).toHaveLength(1)
  })

  it('says so when there are no closes at all, rather than drawing flat', () => {
    /* An empty box reads as a price that held perfectly steady. */
    const { container } = render(<PriceChart chart={chart({
      closes: Array.from({ length: 365 }, () => null),
    })} />)

    expect(container.querySelector('path.px')).toBeNull()
    expect(container.querySelector('.px-none')).toBeTruthy()
  })

  it('colours the line by direction and nothing else', () => {
    /* Green and red mean price direction on this surface. Nothing else may
       use them, and this is the only place they appear. */
    const up = render(<PriceChart chart={chart({ closes: [1, 2, 3] })} />)
    expect(up.container.querySelector('path.px')).toHaveAttribute(
      'stroke', 'var(--up)')
    up.unmount()

    const down = render(<PriceChart chart={chart({ closes: [3, 2, 1] })} />)
    expect(down.container.querySelector('path.px')).toHaveAttribute(
      'stroke', 'var(--down)')
  })

  it('emits nothing for a measured zero, and something for a one', () => {
    /* Ported from the geometry suite when the chart moved here. A zero is a
       day we watched and nothing was said; a 2px stub would overstate it into
       looking like a little chatter. */
    const { container } = render(<PriceChart chart={chart({
      closes: [1, 2],
      chatter: [0, 1],
    })} />)

    expect(container.querySelectorAll('rect.chat')).toHaveLength(1)
  })

  it('keeps calendar position, not the order of surviving points', () => {
    /* Ported from the geometry suite. A Monday sits three days after the
       Friday before it whether or not anything traded between, so the line
       must be indexed by calendar day rather than by which points survived. */
    const { container } = render(<PriceChart chart={chart({
      closes: [1, null, null, null, null, null, null, null, null, 2],
      chatter: Array.from({ length: 10 }, () => null),
    })} />)

    const d = container.querySelector('path.px')!.getAttribute('d')!
    const xs = [...d.matchAll(/[ML]([\d.]+),/g)].map((m) => Number(m[1]))
    expect(xs[0]).toBe(0)
    // The last real close is at index 9 of 10, which is the full width.
    expect(xs[1]).toBeCloseTo(860, 0)
  })
})

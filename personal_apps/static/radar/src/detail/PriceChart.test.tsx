import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PLOT_R, PriceChart } from './PriceChart'
import type { DetailChart } from '../types'

const chart = (over: Partial<DetailChart> = {}): DetailChart => ({
  from: '2025-08-23T00:00:00Z',
  span: '1Y',
  step_minutes: 1440,
  closes: Array.from({ length: 365 }, (_, i) => 1 + i / 100),
  chatter: Array.from({ length: 365 }, (_, i) => (i < 362 ? null : i)),
  sessions: [],
  history_proxy: false, proxy_mic: null, proxy_venue: null,
  native_mic: null, native_venue: null, native_from: null,
  normal_per_slot: null,
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

  it('draws no chatter where nothing was observed', () => {
    /* null is "not watched", not "zero mentions". The violet area begins at
       the first observed slot and nothing is drawn left of it. The fixture
       observes only the last 3 of 365 slots, so exactly one run renders. */
    const { container } = render(<PriceChart chart={chart()} />)

    const areas = container.querySelectorAll('path[fill="var(--mark-soft)"]')
    expect(areas).toHaveLength(1)
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

  it('says so when there are no closes at all, rather than framing a void', () => {
    /* The old layout kept the full price lane as empty frame with a dashed
       rule floating in it. The chatter lane takes the whole plot now, and
       one line of text says why there is no price. */
    const { container, getByText } = render(<PriceChart chart={chart({
      closes: Array.from({ length: 365 }, () => null),
    })} />)

    expect(container.querySelector('path.px')).toBeNull()
    expect(getByText('no stored price for this span')).toBeTruthy()
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

  it('rides the floor for a measured zero rather than overstating it', () => {
    /* A zero is a day we watched and nothing was said. As an area it sits ON
       the baseline -- present, flat, honest -- where the old 2px bar stub
       would have overstated it into looking like a little chatter. */
    const { container } = render(<PriceChart chart={chart({
      closes: [1, 2],
      chatter: [0, 1],
    })} />)

    const area = container.querySelector('path[fill="var(--mark-soft)"]')!
    const d = area.getAttribute('d')!
    // One run covering both slots: the zero anchors the shape at the floor.
    expect(container.querySelectorAll('path[fill="var(--mark-soft)"]'))
      .toHaveLength(1)
    expect(d).toContain('Z')
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
    // The last real close is at index 9 of 10, which is the plot's right
    // edge. Against PLOT_R rather than a literal: the plot narrowed once
    // already when the axis labels moved out into a gutter, and pinning the
    // number instead of the relationship is what made that a failure.
    expect(xs[1]).toBeCloseTo(PLOT_R, 0)
  })
})

describe('the axis on an intraday span', () => {
  const intraday = (step: number, span: '1D' | '1W'): DetailChart => ({
    from: '2026-08-25T00:00:00Z',
    span,
    step_minutes: step,
    closes: Array.from({ length: 96 }, (_, i) => 10 + i * 0.01),
    chatter: Array.from({ length: 96 }, () => 1),
    sessions: [],
    history_proxy: false, proxy_mic: null, proxy_venue: null,
    native_mic: null, native_venue: null, native_from: null,
    normal_per_slot: null,
    watched_from: null,
  })

  it('labels a 24-hour chart with times, not month names', () => {
    /* The slots are fifteen minutes wide. Reading month names under them
       would place the reader a year out from where they actually are. */
    const { container } = render(<PriceChart chart={intraday(15, '1D')} />)

    // The gridlines only. The leftmost label legitimately carries a date --
    // a bare "00:00" does not say which day it belongs to. Selected by
    // `g.tick`, not by "any text.ax inside any g": the chart's furniture now
    // shares one `.axes` group so it can fade in as one piece, and a
    // structural selector quietly widened to include the axis-end labels.
    const ticks = [...container.querySelectorAll('g.tick text.ax')]
      .map((n) => n.textContent ?? '')
    expect(ticks.length).toBeGreaterThan(0)
    expect(ticks.every((l) => /^\d{2}:\d{2}$/.test(l))).toBe(true)
  })

  it('ends at "now" rather than "today" when the span is hours', () => {
    /* "today" is a calendar day. On a chart whose last slot is the last
       fifteen minutes it names the wrong unit entirely. */
    const { container } = render(<PriceChart chart={intraday(15, '1D')} />)

    expect(container.textContent).toContain('now')
    expect(container.textContent).not.toContain('today')
  })

  it('still says "today" on a day-indexed span', () => {
    /* Teeth: the intraday branch must not have replaced the daily one. */
    const daily: DetailChart = {
      from: '2026-01-01T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, () => 5),
      chatter: Array.from({ length: 365 }, () => 1), sessions: [],
      history_proxy: false, proxy_mic: null, proxy_venue: null,
      native_mic: null, native_venue: null, native_from: null,
      normal_per_slot: null, watched_from: null,
    }

    const { container } = render(<PriceChart chart={daily} />)

    expect(container.textContent).toContain('today')
  })

  it('labels chart ticks in Berlin rather than UTC', () => {
    const inBerlin = {
      ...intraday(15, '1D'),
      from: '2026-08-28T19:00:00Z',
    }
    const { container } = render(<PriceChart chart={inBerlin} />)

    expect(container.textContent).toContain('21:00')
  })

  it('renders named extended-session bands', () => {
    const withSessions = {
      ...intraday(15, '1D'),
      sessions: [{
        start: '2026-08-25T18:00:00Z',
        end: '2026-08-25T20:00:00Z',
        kind: 'afterhours',
      }],
    } as unknown as DetailChart
    const { container } = render(<PriceChart chart={withSessions} />)

    expect(container.querySelector('[data-session="afterhours"]')).not.toBeNull()
    expect(screen.getByText('After hours')).toBeInTheDocument()
  })

  it('extends an extended-session band through the chatter lane', () => {
    /* Removing the lower part makes the context stop at price, leaving the
       chatter it belongs to outside the same session. */
    const withSessions = {
      ...intraday(15, '1D'),
      sessions: [{
        start: '2026-08-25T18:00:00Z',
        end: '2026-08-25T20:00:00Z',
        kind: 'afterhours',
      }],
    } as unknown as DetailChart
    const { container } = render(<PriceChart chart={withSessions} />)

    expect(container.querySelector('[data-session="afterhours"] rect'))
      .toHaveAttribute('height', '264')
  })

  it('clips session bands and their labels to the shared plot', () => {
    /* A band that begins or ends beside the plot must not paint into the
       axis gutter, and the label needs the same boundary as its rectangle. */
    const withSessions = {
      ...intraday(15, '1D'),
      sessions: [{
        start: '2026-08-25T18:00:00Z',
        end: '2026-08-25T20:00:00Z',
        kind: 'afterhours',
      }],
    } as unknown as DetailChart
    const { container } = render(<PriceChart chart={withSessions} />)

    const clip = container.querySelector('clipPath')!
    const reference = `url(#${clip.id})`
    const band = container.querySelector('[data-session="afterhours"]')!
    expect(band.querySelector('rect')).toHaveAttribute('clip-path', reference)
    expect(band.querySelector('text')).toHaveAttribute('clip-path', reference)
  })
})


describe('the Xetra->Tradegate history seam label', () => {
  it('states the proxy venue, the seam date, and the native venue', () => {
    render(<PriceChart chart={chart({
      history_proxy: true, proxy_mic: 'XETR', proxy_venue: 'Xetra',
      native_mic: 'XGAT', native_venue: 'Tradegate BSX',
      native_from: '2026-08-31',
    })} />)
    expect(
      screen.getByText(/Xetra history through .* · Tradegate BSX now/),
    ).toBeInTheDocument()
  })

  it('an all-proxy chart before native accumulation drops the through-date', () => {
    render(<PriceChart chart={chart({
      history_proxy: true, proxy_mic: 'XETR', proxy_venue: 'Xetra',
      native_mic: 'XGAT', native_venue: 'Tradegate BSX', native_from: null,
    })} />)
    expect(
      screen.getByText(/Xetra history · Tradegate BSX now/),
    ).toBeInTheDocument()
  })

  it('renders no note at all without a proxy', () => {
    const { container } = render(<PriceChart chart={chart()} />)
    expect(container.querySelector('.history-proxy-note')).toBeNull()
  })
})

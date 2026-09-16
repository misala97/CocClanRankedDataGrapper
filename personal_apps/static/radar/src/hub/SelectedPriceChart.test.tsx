import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PREMARKET, alpacaPrice, bar, counted, priceChartResponse, yahooPrice } from './priceChartFixtures'
import { SelectedPriceChart, chartSummary, panOffset, slotReadout } from './SelectedPriceChart'

function show(data = priceChartResponse()) {
  return render(<div className="rh"><SelectedPriceChart data={data} ticker="AAA" /></div>)
}

const marks = (container: HTMLElement) => ({
  lines: container.querySelectorAll('path.price-line').length,
  areas: container.querySelectorAll('path.rh-sp-area').length,
  dots: container.querySelectorAll('circle.price-dot').length,
  latest: container.querySelectorAll('circle.price-last, circle.price-provisional').length,
})

describe('what the chart says in words', () => {
  it('names the window, the listing, the provenance and the unknown adjustment basis', () => {
    show()
    expect(screen.getByText('Current session so far')).toBeInTheDocument()
    expect(screen.getByTestId('rh-sp-provenance')).toHaveTextContent(
      'Yahoo chart · NASDAQ (XNMS) · USD · 1-minute bar closes · 5 of 67 reported · received 30 s ago')
    expect(screen.getByText(/Adjustment basis unknown/)).toBeInTheDocument()
  })

  it('summarises coverage without inventing a direction or a return', () => {
    const { container } = show()
    expect(chartSummary(priceChartResponse())).toContain(
      '5 15-minute slots, 2 observed, 2 partial, 1 unknown, 6 mentions counted')
    expect(container.textContent).not.toMatch(/over this span|%/)
  })

  it('labels a closed window by its session end, never "now"', () => {
    const data = priceChartResponse()
    data.window.partial = false
    const { container } = show(data)
    const labels = [...container.querySelectorAll('svg text')].map((t) => t.textContent)
    expect(labels.some((l) => l?.includes('session end'))).toBe(true)
    expect(labels.some((l) => l?.startsWith('now'))).toBe(false)
  })

  it('says when there is no price, and why', () => {
    const data = priceChartResponse({
      price: null, acquisition: { state: 'pending', retry_after_seconds: 2, reason: 'acquiring' },
    })
    show(data)
    expect(screen.getByText('No price observation inside this window')).toBeInTheDocument()
    expect(screen.getByTestId('rh-sp-provenance')).toHaveTextContent(
      'No price inside this window · provider chart still loading (acquiring)')
  })

  it('marks a stale series and names a stored fallback as a fallback', () => {
    show(priceChartResponse({ price: yahooPrice({ stale: true, cache_age_seconds: 240 }) }))
    const line = screen.getByTestId('rh-sp-provenance')
    expect(line).toHaveTextContent('received 4 min ago · stale')
    expect(line).toHaveClass('rh-sp-stale')
  })

  it('describes a daily-close fallback with its own source', () => {
    const data = priceChartResponse({
      acquisition: { state: 'disabled', retry_after_seconds: null, reason: 'off' },
      price: yahooPrice({ source: 'massive_grouped', kind: 'daily_close', price_basis: 'close',
                          adjustment_basis: 'split', fallback: true, interval_seconds: null,
                          cache_age_seconds: null }),
    })
    show(data)
    expect(screen.getByTestId('rh-sp-provenance')).toHaveTextContent(
      'Massive · NASDAQ (XNMS) · USD · stored daily closes · fallback while the provider chart switched off')
  })

  it('discloses its data notes', () => {
    show()
    expect(screen.getByText('Data notes (1)')).toBeInTheDocument()
  })
})

describe('the segmented area (C1)', () => {
  const sparse = () => priceChartResponse({
    price: alpacaPrice(Array.from({ length: 64 }, (_, i) => i)),
  })

  it('draws one line and one filled area per hard segment, and no dot cloud', () => {
    const { container } = show(sparse())
    expect(marks(container)).toEqual({ lines: 1, areas: 1, dots: 0, latest: 1 })
    const area = container.querySelector('path.rh-sp-area')!
    expect(area.getAttribute('fill')).toMatch(/^url\(#/)
    expect(area.getAttribute('d')!.endsWith('Z')).toBe(true)
  })

  it('splits at a session, a market state and a source change, and never fills across one', () => {
    const points = [bar('08:00', 100), bar('08:01', 101),
                    bar('08:02', 102, { segment: `regular:2026-09-15|alpaca_sip:provider_bar_close:raw`,
                                        regime: 'alpaca_sip:provider_bar_close:raw' }),
                    bar('08:03', 103, { segment: `regular:2026-09-15|alpaca_sip:provider_bar_close:raw`,
                                        regime: 'alpaca_sip:provider_bar_close:raw' })]
    const { container } = show(priceChartResponse({
      price: yahooPrice({ points, observations: counted(points) }),
    }))
    expect(marks(container)).toEqual({ lines: 2, areas: 2, dots: 0, latest: 1 })
    const ds = [...container.querySelectorAll('path.price-line')].map((p) => p.getAttribute('d')!)
    expect(ds[0]!.match(/[ML]/g)).toHaveLength(2)
    expect(ds[1]!.match(/[ML]/g)).toHaveLength(2)
  })

  it('renders a one-observation segment as a dot with no area', () => {
    const points = [bar('08:00', 100),
                    bar('08:30', 102, { segment: `regular:2026-09-15|yahoo_chart:provider_bar_close:unknown` })]
    const { container } = show(priceChartResponse({
      price: yahooPrice({ points, observations: counted(points) }),
    }))
    expect(marks(container)).toEqual({ lines: 0, areas: 0, dots: 2, latest: 1 })
  })

  it('reports only actual observations however long the drawn line is', () => {
    const data = sparse()
    const summary = chartSummary(data)
    expect(summary).toContain('64 1-minute bar closes')
    expect(summary).toContain('in 1 segment')
    expect(summary).toContain('64 of 67 expected 1-minute intervals reported')
    expect(summary).not.toMatch(/real.time|live price/i)
  })

  it('names delayed consolidated SIP and raw closes, never real-time', () => {
    show(sparse())
    const line = screen.getByTestId('rh-sp-provenance')
    expect(line).toHaveTextContent('Alpaca consolidated SIP (delayed)')
    expect(line).toHaveTextContent('1-minute bar closes')
    expect(line.textContent).not.toMatch(/real.time/i)
    expect(screen.getByText(/Adjustment basis raw/)).toBeInTheDocument()
  })

  it('keeps the same segment key for a run interrupted by a disclosed gap', () => {
    const points = [bar('08:00', 100), bar('08:02', null, { breakBefore: true }),
                    bar('08:40', 101, { breakBefore: true })]
    expect(points.every((p) => p.segment === PREMARKET)).toBe(true)
    const { container } = show(priceChartResponse({
      price: yahooPrice({ points, observations: counted(points) }),
    }))
    expect(marks(container)).toEqual({ lines: 1, areas: 1, dots: 0, latest: 1 })
  })
})

// C2-2: the drawing is 912 units wide and pans below that width. Where it
// pans, it must open on the latest actual observation -- a 1D window runs to
// the extended close, so a listing that stopped trading at the bell would
// otherwise open on empty after-hours hours. But where the RIGHTMOST position
// still leaves a usable amount of line on screen, take it: that is where the
// price axis and the window-end label live.
describe('where the panned chart opens', () => {
  // FT: 912-unit drawing, the last reported minute four hours before the
  // window ends. The numbers are the widths measured on the built hub.
  const sparse = (clientWidth: number) =>
    panOffset({ scrollWidth: 950, clientWidth, drawingWidth: 912, latestX: 636 })
  const visible = (left: number, clientWidth: number, x: number) =>
    x >= left && x <= left + clientWidth

  it('takes the rightmost position where the gutter fits without hiding the line', () => {
    expect(sparse(816)).toBe(134)            // 1200 px: maxLeft, gutter visible
    expect(sparse(700)).toBe(250)            // 768 px: maxLeft, gutter visible
    // The price gutter sits past the plot at 848..912; it is on screen in both.
    expect(visible(134, 816, 912)).toBe(true)
    expect(visible(250, 700, 912)).toBe(true)
  })

  it('keeps the latest observation rather than the gutter when both cannot fit', () => {
    expect(sparse(322)).toBe(410)            // 390 px: the latest stays on screen
    expect(visible(410, 322, 636)).toBe(true)
    expect(visible(410, 322, 912)).toBe(false)
  })

  it('never hides the latest observation at any of the measured widths', () => {
    for (const clientWidth of [816, 700, 322]) {
      expect(visible(sparse(clientWidth)!, clientWidth, 636)).toBe(true)
    }
    // A dense session whose latest observation is at the window end keeps the
    // rightmost position at every width.
    for (const clientWidth of [816, 700, 322]) {
      const left = panOffset({ scrollWidth: 950, clientWidth, drawingWidth: 912, latestX: 848 })
      expect(left).toBe(950 - clientWidth)
      expect(visible(left!, clientWidth, 848)).toBe(true)
    }
  })

  it('does nothing when the drawing fits, and falls back to the newest end with no observation', () => {
    expect(panOffset({ scrollWidth: 900, clientWidth: 900, drawingWidth: 912, latestX: 636 })).toBeNull()
    expect(panOffset({ scrollWidth: 950, clientWidth: 322, drawingWidth: 912, latestX: null })).toBe(628)
  })

  it('places by the rendered drawing width rather than assuming 912 CSS pixels', () => {
    // A half-size drawing puts the same observation at 318 CSS px, so the
    // trailing room -- which is CSS pixels, not user units -- gives 253.
    expect(panOffset({ scrollWidth: 475, clientWidth: 161, drawingWidth: 456, latestX: 636 }))
      .toBe(253)
  })
})

describe('reading intervals from the keyboard', () => {
  it('reports the price bar, provisional state, count, coverage and provenance', () => {
    show()
    const canvas = screen.getByRole('group', { name: /price and chatter intervals for AAA/i })
    const readout = screen.getByTestId('rh-sp-readout')
    canvas.focus()
    fireEvent.keyDown(canvas, { key: 'Home' })
    expect(readout).toHaveTextContent('3 mentions, observed')
    expect(readout).toHaveTextContent('price $101.50, 1-minute bar 10:04–10:05 close')
    expect(readout).toHaveTextContent('Yahoo chart, adjustment basis unknown')
    expect(readout).toHaveTextContent('bullish 2, bearish 1 (recorded judgments)')
    fireEvent.keyDown(canvas, { key: 'ArrowRight' })
    expect(readout).toHaveTextContent('0 mentions, observed')
    fireEvent.keyDown(canvas, { key: 'ArrowRight' })
    expect(readout).toHaveTextContent('mentions unknown: nothing valid was recorded, which is not zero')
    fireEvent.keyDown(canvas, { key: 'End' })
    expect(readout).toHaveTextContent('1 mention, partial coverage')
    expect(readout).toHaveTextContent('provisional: the bar was still open when received at 11:06')
    expect(readout).toHaveTextContent('tone unavailable 1')
    fireEvent.keyDown(canvas, { key: 'Escape' })
    expect(readout).toHaveTextContent(/Focus the chart/)
  })

  it('never reports a number the chart did not draw', () => {
    const data = priceChartResponse()
    expect(slotReadout(data, 2)).not.toMatch(/0 mentions/)
    expect(slotReadout(data, 1)).toContain('no price bar in this interval (pre-market)')
  })

  it('is one described, focusable control', () => {
    show()
    const canvas = screen.getByRole('group', { name: /price and chatter intervals/i })
    expect(canvas).toHaveAttribute('tabindex', '0')
    const described = document.getElementById(canvas.getAttribute('aria-describedby')!)
    expect(described?.textContent).toMatch(/^AAA, session Tue 15 Sep/)
    expect(within(canvas).getByRole('img')).toBeInTheDocument()
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { priceChartResponse, yahooPrice } from './priceChartFixtures'
import { SelectedPriceChart, chartSummary, slotReadout } from './SelectedPriceChart'

function show(data = priceChartResponse()) {
  return render(<div className="rh"><SelectedPriceChart data={data} ticker="AAA" /></div>)
}

describe('what the chart says in words', () => {
  it('names the window, the listing, the provenance and the unknown adjustment basis', () => {
    show()
    expect(screen.getByText('Current session so far')).toBeInTheDocument()
    expect(screen.getByTestId('rh-sp-provenance')).toHaveTextContent(
      'Yahoo chart · NASDAQ (XNMS) · USD · 1-minute bar closes · received 30 s ago')
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

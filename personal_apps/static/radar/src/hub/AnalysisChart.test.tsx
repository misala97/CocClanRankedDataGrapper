import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AnalysisChart } from './AnalysisChart'
import { analysis, chatterDay, priceDay, sourceDay } from './analysisFixtures'

describe('the two panels (C16)', () => {
  it('draws one column per requested date and joins only what may be joined', () => {
    const payload = analysis()
    const { container } = render(
      <AnalysisChart payload={payload} selected="2026-09-10" onSelect={() => undefined} />)
    // Three observed closes: 8, 10, 11. 9 is a missing open day, so 8 stands
    // alone and 10-11 are one run: exactly one polyline, two points.
    const lines = container.querySelectorAll('polyline.rh-an-line')
    expect(lines).toHaveLength(1)
    expect(lines[0]!.getAttribute('data-run')).toBe('3,4')
    expect(container.querySelectorAll('circle[data-state="observed"]')).toHaveLength(3)
    expect(container.querySelectorAll('circle[data-state="missing-open"]')).toHaveLength(1)
    expect(container.querySelectorAll('line[data-state="missing-closed"]')).toHaveLength(3)
    // Counts: 12, 0 (observed zero tick), 40 partial (hatched), 3, and three gaps.
    expect(container.querySelectorAll('rect[data-coverage="observed"]')).toHaveLength(2)
    expect(container.querySelectorAll('rect[data-coverage="zero"]')).toHaveLength(1)
    expect(container.querySelectorAll('rect[data-coverage="partial"]')).toHaveLength(1)
    expect(container.querySelector('rect[data-coverage="partial"]')!.getAttribute('fill'))
      .toBe('url(#rh-an-hatch)')
    expect(container.querySelectorAll('rect[data-coverage="unavailable"]')).toHaveLength(3)
    expect(screen.getAllByText('n/a')).toHaveLength(3)
    // The partial bar is labelled as such, not as a plain count.
    expect(screen.getByText('40*')).toBeInTheDocument()
    // Seven day buttons, the selected one pressed, and the caption.
    const group = screen.getByRole('group', { name: 'Select a day' })
    const buttons = within(group).getAllByRole('button')
    expect(buttons).toHaveLength(7)
    expect(buttons[3]).toHaveAttribute('aria-pressed', 'true')
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText(/Daily closes use the stored trading date/)).toBeInTheDocument()
    expect(container.querySelectorAll('rect.rh-an-selected')).toHaveLength(2)
  })

  it('never draws a line across a weekend between two closes (R5)', () => {
    const base = analysis()
    const days = [priceDay('2026-09-10', { close: 10 }), priceDay('2026-09-11', { close: 11 }),
                  priceDay('2026-09-12'), priceDay('2026-09-13'), priceDay('2026-09-14', { close: 12 })]
    const payload = analysis({
      request: { ...base.request, from: '2026-09-10', to: '2026-09-14' },
      price: { ...base.price, days, usable_count: 3, first_usable: '2026-09-10',
               last_usable: '2026-09-14', interior_modeled_missing: [] },
      chatter: { ...base.chatter, days: days.map((d) => chatterDay(d.date)) },
    })
    const { container } = render(
      <AnalysisChart payload={payload} selected={null} onSelect={() => undefined} />)
    const lines = container.querySelectorAll('polyline.rh-an-line')
    expect(lines).toHaveLength(1)
    expect(lines[0]!.getAttribute('data-run')).toBe('0,1')
    expect(container.querySelectorAll('circle[data-state="observed"]')).toHaveLength(3)
  })

  it('pads the day buttons by the plot margins and keeps SVG empty text apart from the HTML empty state', () => {
    const base = analysis()
    const none = analysis({
      price: { ...base.price, days: base.price.days.map((d) => priceDay(d.date)), usable_count: 0,
               first_usable: null, last_usable: null, interior_modeled_missing: null },
    })
    const { container } = render(<AnalysisChart payload={none} selected={null} onSelect={() => undefined} />)
    const group = screen.getByRole('group', { name: 'Select a day' })
    // LEFT 52 and RIGHT 14 of the 720-unit viewBox, as percentages of the
    // shared box: the button columns sit under the plotted columns.
    expect(group.style.paddingLeft).toBe(`${(52 / 720) * 100}%`)
    expect(group.style.paddingRight).toBe(`${(14 / 720) * 100}%`)
    const empty = screen.getByText('No usable close in this window')
    expect(empty).toHaveClass('rh-an-emptytext')
    expect(empty).not.toHaveClass('rh-an-empty')
    // The panels and the buttons share the scroll box; the caption does not.
    const plots = container.querySelector('.rh-an-plotscroll .rh-an-plots')!
    expect(plots.contains(group)).toBe(true)
    expect(plots.querySelectorAll('svg')).toHaveLength(2)
    expect(plots.contains(screen.getByText(/Daily closes use the stored trading date/))).toBe(false)
  })

  it('says what a one-close and a no-close window are, without a trend', () => {
    const one = analysis({
      price: { ...analysis().price, days: analysis().price.days.map((d) =>
        (d.date === '2026-09-10' ? d : priceDay(d.date))), usable_count: 1,
        first_usable: '2026-09-10', last_usable: '2026-09-10', interior_modeled_missing: null },
    })
    const { container, rerender } = render(
      <AnalysisChart payload={one} selected={null} onSelect={() => undefined} />)
    expect(container.querySelectorAll('polyline')).toHaveLength(0)
    expect(container.querySelectorAll('circle[data-state="observed"]')).toHaveLength(1)
    const none = analysis({
      price: { ...one.price, days: one.price.days.map((d) => priceDay(d.date)), usable_count: 0,
        first_usable: null, last_usable: null },
    })
    rerender(<AnalysisChart payload={none} selected={null} onSelect={() => undefined} />)
    expect(screen.getByText('No usable close in this window')).toBeInTheDocument()
    expect(container.querySelectorAll('circle[data-state="observed"]')).toHaveLength(0)
  })

  it('marks invalid, unverified and overlap days by shape and text', () => {
    const base = analysis()
    const payload = analysis({
      price: { ...base.price, days: base.price.days.map((d) =>
        (d.date === '2026-09-09' ? priceDay(d.date, { state: 'invalid', reason: 'currency is not USD', source: 'finnhub' })
          : d.date === '2026-09-07' ? priceDay(d.date, { state: 'identity_unverified' }) : d)) },
      chatter: { ...base.chatter, days: base.chatter.days.map((d) =>
        (d.date === '2026-09-11'
          ? chatterDay(d.date, { mentions: null, coverage: 'partial', overlap_ambiguous: true,
                                 sources: [sourceDay('reddit', { mentions: 1 }), sourceDay('reddit:wsb', { mentions: 2 })] })
          : d)) },
    })
    const { container } = render(
      <AnalysisChart payload={payload} selected={null} onSelect={() => undefined} />)
    expect(container.querySelectorAll('path[data-state="invalid"]')).toHaveLength(1)
    expect(container.querySelectorAll('g[data-state="identity_unverified"]')).toHaveLength(1)
    expect(container.querySelectorAll('rect[data-coverage="overlap"]')).toHaveLength(1)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('selects by pointer and by keyboard arrows, Home and End', async () => {
    const onSelect = vi.fn()
    render(<AnalysisChart payload={analysis()} selected="2026-09-08" onSelect={onSelect} />)
    const group = screen.getByRole('group', { name: 'Select a day' })
    const buttons = within(group).getAllByRole('button')
    await userEvent.click(buttons[2]!)
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-09')
    buttons[1]!.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-09')
    expect(document.activeElement).toBe(buttons[2])
    await userEvent.keyboard('{End}')
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-13')
    await userEvent.keyboard('{Home}')
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-07')
    await userEvent.keyboard('{ArrowLeft}')
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-07')
    // Only the selected button is in the tab order (roving tabindex).
    expect(buttons.filter((b) => b.getAttribute('tabindex') === '0')).toHaveLength(1)
  })
})

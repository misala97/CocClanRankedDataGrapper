// Keyboard paths the critique of 2026-09-01 found missing: no way down the
// list but Tab, and Escape did nothing anywhere.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Controls } from '../board/Controls'
import { ListPane } from './ListPane'
import type { BoardPayload, Row, Selection } from '../types'

const row = (ticker: string): Row => ({
  ticker, name: ticker, segment: 'micro', divergence: null, mention_z: 2,
  mentions: 20, expected: 6, ratio: 20 / 6, authors: 5, text_ratio: 0.1,
  sources: ['bluesky'], price: 1.5, price_move: null, direction: 'flat',
  price_status: 'ok', quote: {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 1.5,
    regular_move: 0.02, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: false, score_term: 'chatter',
    is_fallback: false, source: 'legacy', price_basis: 'trade',
    bid: null, ask: null,
  }, baseline_days: 20, marks: [], series: [], price_series: [],
  normal_per_hour: null, triplet: {},
  tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '3.3x its normal' }],
})

const selection: Selection = {
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [],
  window: 4, minVenues: 1,
}

const payload = (over: Partial<BoardPayload> = {}): BoardPayload => ({
  generated_at: '2026-08-22T19:00:00Z',
  market: 'us', display_timezone: 'Europe/Berlin',
  market_venue: 'US markets', next_boundary_label: 'closes',
  next_boundary_at: '2026-08-22T20:00:00Z',
  sources: ['bluesky', 'fourchan', 'reddit'],
  all_sources: ['bluesky', 'fourchan', 'reddit'],
  segments: [], session: 'regular', window_hours: 4,
  min_venues: 1, venue_counts: { any: 3, multi: 1 },
  segment_counts: { all: 3, micro: 3 },
  triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
  rows: [row('AAA'), row('BBB'), row('CCC')], excluded: {},
  ...over,
})

describe('walking the list', () => {
  function list(onSelect = vi.fn()) {
    render(<ListPane payload={payload()} selection={selection} selected="AAA"
                     busy={false} onSelect={onSelect} onChange={() => {}} />)
    return onSelect
  }
  const link = (ticker: string) => screen.getByRole('link', { name: new RegExp(ticker) })

  it('moves focus down and up the rows with the arrow keys', async () => {
    list()
    link('AAA').focus()

    await userEvent.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(link('BBB'))
    await userEvent.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(link('CCC'))
    await userEvent.keyboard('{ArrowUp}')
    expect(document.activeElement).toBe(link('BBB'))
  })

  it('stops at the ends rather than wrapping', async () => {
    list()
    link('CCC').focus()

    await userEvent.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(link('CCC'))
    link('AAA').focus()
    await userEvent.keyboard('{ArrowUp}')
    expect(document.activeElement).toBe(link('AAA'))
  })

  it('jumps to either end with Home and End', async () => {
    list()
    link('BBB').focus()

    await userEvent.keyboard('{End}')
    expect(document.activeElement).toBe(link('CCC'))
    await userEvent.keyboard('{Home}')
    expect(document.activeElement).toBe(link('AAA'))
  })

  it('does not select on focus -- Enter still does that', async () => {
    /* Selecting on every arrow press would fetch a panel per keystroke. */
    const onSelect = list()
    link('AAA').focus()

    await userEvent.keyboard('{ArrowDown}')
    expect(onSelect).not.toHaveBeenCalled()
    await userEvent.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith('BBB')
  })
})

describe('the folded filters', () => {
  it('fold again on Escape, with focus back on the control that opened them', async () => {
    render(<Controls payload={payload()} selection={selection} busy={false}
                     onChange={vi.fn()} />)
    const change = screen.getByRole('button', { name: /change/i })
    await userEvent.click(change)
    expect(screen.getByRole('button', { name: /Bluesky/ })).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')

    expect(screen.queryByRole('button', { name: /Bluesky/ })).toBeNull()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /change/i }))
  })
})

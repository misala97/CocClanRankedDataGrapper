import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ListPane, splitTiers } from './ListPane'
import type { BoardPayload, Row, Selection } from '../types'

const row = (ticker: string, divergence: number | null): Row => ({
  ticker, name: ticker, segment: 'micro', divergence, mention_z: 2,
  mentions: 20, expected: 6, ratio: 20 / 6, authors: 5, text_ratio: 0.1,
  sources: ['bluesky'], price: 1.5, price_move: divergence === null ? null : 0.02,
  direction: divergence === null ? 'flat' : 'up',
  price_status: 'ok', quote: {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 1.5,
    regular_move: 0.02, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: divergence !== null,
    score_term: divergence === null ? 'chatter' : 'divergence',
    is_fallback: false, source: 'legacy', price_basis: 'trade',
    bid: null, ask: null,
  }, baseline_days: 20, marks: [], series: [], price_series: [],
  normal_per_hour: null, triplet: {},
  tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '3.3x its normal' }],
})

const selection: Selection = {
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [],
  window: 4, minVenues: 1, sort: null, dir: 'desc' as const,
}

function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    market: 'us', display_timezone: 'Europe/Berlin',
    market_venue: 'US markets', next_boundary_label: 'closes',
    next_boundary_at: '2026-08-22T20:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, sort: null, dir: 'desc' as const, venue_counts: { any: 5, multi: 3 },
    segment_counts: { all: 5, micro: 5 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [], excluded: {},
    ...over,
  }
}

function list(over: Partial<BoardPayload> = {}) {
  return render(
    <ListPane payload={payload(over)} selection={selection} selected={null}
              busy={false} onSelect={() => {}} onChange={() => {}} />)
}

/** The sequence of captions and rows as the reader meets them. */
function sequence(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.tier, .row')).map((node) =>
    node.classList.contains('tier')
      ? `tier:${node.textContent!.replace(/\s+/g, ' ').trim()}`
      : `row:${node.querySelector('.tk')!.textContent}`)
}

describe('the two tiers', () => {
  it('split where the server\'s divergence ordering ends', () => {
    /* leaderboard.py sorts scored rows first, then everything else by
       chatter. The tiers are a presentation of that order, never a
       reordering of it. */
    const rows = [row('A', 0.5), row('B', 0.1), row('C', null), row('D', null)]

    expect(splitTiers(rows).map((tier) => tier.rows.map((r) => r.ticker)))
      .toEqual([['A', 'B'], ['C', 'D']])
  })

  it('caption both tiers with their counts, in server order', () => {
    const { container } = list({
      rows: [row('A', 0.5), row('B', 0.1), row('C', null), row('D', null),
             row('E', null)],
    })

    const seen = sequence(container)
    expect(seen[0]).toMatch(/^tier:Scored against price/)
    expect(seen[0]).toMatch(/4h/)
    expect(seen[0]).toMatch(/\b2\b/)
    expect(seen.slice(1, 3)).toEqual(['row:A', 'row:B'])
    expect(seen[3]).toMatch(/^tier:Chatter only/)
    expect(seen[3]).toMatch(/\b3\b/)
    expect(seen.slice(4)).toEqual(['row:C', 'row:D', 'row:E'])
  })

  it('render no captions on a closed market', () => {
    /* Every row is chatter-ranked with the exchange shut, and the status
       line already says RANKED BY CHATTER. One caption over one tier would
       be a heading with nothing to distinguish from. */
    list({ session: 'closed', rows: [row('A', null), row('B', null)] })

    expect(screen.queryByText(/Scored against price/)).toBeNull()
    expect(screen.queryByText(/Chatter only/)).toBeNull()
  })

  it('keep the scored caption at zero when an open market has nothing scored', () => {
    /* Seen live 2026-09-01 21:35: US open, every row warming up, nothing
       eligible. An absent caption reads as "there is no such thing"; a
       zero says "not yet". */
    const { container } = list({ rows: [row('A', null), row('B', null)] })

    const seen = sequence(container)
    expect(seen[0]).toMatch(/^tier:Scored against price/)
    expect(seen[0]).toMatch(/\b0\b/)
    expect(seen[1]).toMatch(/^tier:Chatter only/)
    expect(seen.slice(2)).toEqual(['row:A', 'row:B'])
  })

  it('sit under a column header that scrolls with them, so both share one width', () => {
    /* Outside the scroller the header was laid out 560px wide while the
       rows, inside the scrollbar, were 540px -- the fr column absorbed the
       difference and Score and Lean drifted ~20px off the cells under them
       (live mode, 2026-09-02: "most of the stuff does not line up with the
       header"). Inside, it is one grid on one width, and sticky. */
    const { container } = list({ rows: [row('A', 0.5), row('B', null)] })

    const header = container.querySelector('#radar-rows > .cols')
    expect(header).not.toBeNull()
    expect(container.querySelector('#radar-rows')!.firstElementChild).toBe(header)
  })

  it('settle in only after a refetch, never on first paint', () => {
    /* The board loads into a task and must not perform an entrance; a board
       that REPLACES the one on screen may settle, as one block, so the swap
       reads as arrival rather than a hard cut. The class arms the CSS; the
       browser animates whatever is inserted while it is on. */
    const { container, rerender } = render(
      <ListPane payload={payload({ rows: [row('A', 0.5)] })} selection={selection}
                selected={null} busy={false} onSelect={() => {}} onChange={() => {}} />)
    expect(container.querySelector('#radar-rows')!.className).not.toContain('settled')

    rerender(
      <ListPane payload={payload({ rows: [row('A', 0.5), row('B', null)],
                                   generated_at: '2026-08-22T19:05:00Z' })}
                selection={selection} selected={null} busy={false}
                onSelect={() => {}} onChange={() => {}} />)

    expect(container.querySelector('#radar-rows')!.className).toContain('settled')
  })

  it('name the term each tier is ordered by, so the rows need no prefix', () => {
    const { container } = list({ rows: [row('A', 0.5), row('B', null)] })

    expect(screen.getByText(/Scored against price/).closest('.tier'))
      .toHaveTextContent(/DIV/)
    expect(screen.getByText(/Chatter only/).closest('.tier'))
      .toHaveTextContent(/\bZ\b/)
    expect(container.querySelector('.row .score .k')).toBeNull()
  })
})

describe('a sorted board', () => {
  it('drops the tier captions for one flat list', () => {
    const rows = [row('AAA', 0.5), row('BBB', null), row('CCC', 0.2)]
    const sorted: Selection = { ...selection, sort: 'mentions', dir: 'desc' }
    render(<ListPane payload={payload({ rows })} selection={sorted}
                     selected={null} busy={false} onSelect={() => {}}
                     onChange={() => {}} />)

    // The captions name the two quantities; a sort is one quantity.
    expect(screen.queryByText(/Scored against price/)).toBeNull()
    expect(screen.queryByText(/Chatter only/)).toBeNull()
    expect(screen.getByText(/Sorted by mentions/)).toBeTruthy()
  })

  it('keeps the captions when no sort is asked for', () => {
    const rows = [row('AAA', 0.5), row('BBB', null)]
    render(<ListPane payload={payload({ rows })} selection={selection}
                     selected={null} busy={false} onSelect={() => {}}
                     onChange={() => {}} />)

    expect(screen.queryByText(/Sorted by/)).toBeNull()
  })

  it('leaves Watching pinned above the sorted rows', () => {
    const rows = [row('AAA', 0.5), row('BBB', null)]
    const sorted: Selection = { ...selection, sort: 'mentions', dir: 'desc' }
    render(<ListPane payload={payload({ rows, watch_rows: [row('ZZZ', 0.1)] })}
                     selection={sorted} selected={null} busy={false}
                     onSelect={() => {}} onChange={() => {}}
                     watching={['ZZZ']} />)

    expect(screen.getByText('Watching')).toBeTruthy()
  })
})

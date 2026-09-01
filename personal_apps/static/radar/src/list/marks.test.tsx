import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { universalMarks, universalQuoteFacts } from './ListPane'
import { TickerRow } from './TickerRow'
import type { Mark, MarketQuote, Row } from '../types'

const withQuote = (ticker: string, over: Partial<MarketQuote>): Row => {
  const base = row(ticker, [])
  return { ...base, quote: { ...base.quote, ...over } }
}

describe('quote facts carried by the whole board', () => {
  it('lift the age when every QUOTED row is stale, whatever the unquoted ones say', () => {
    /* Seen live 2026-09-01: six stale rows and one `unavailable` (QQQ has
       no quote at all). The lift needed every row stale, so one unquoted
       row kept "quote 1h old" on the other six -- and a flags line on every
       row, which is exactly the wallpaper the lift exists to prevent. A row
       with no quote has no age to lift; it says "no live quote" itself. */
    const rows = [
      withQuote('A', { quality: 'stale', age_seconds: 3600 }),
      withQuote('B', { quality: 'stale', age_seconds: 7200 }),
      withQuote('C', { quality: 'unavailable', age_seconds: null }),
    ]

    expect(universalQuoteFacts(rows).keys).toContain('aged')
    expect(universalQuoteFacts(rows).tokens).toContain('quotes 2h old')
  })

  it('lift nothing when no row has a quote to be old', () => {
    const rows = [
      withQuote('A', { quality: 'unavailable', age_seconds: null }),
      withQuote('B', { quality: 'unavailable', age_seconds: null }),
    ]

    expect(universalQuoteFacts(rows).keys).not.toContain('aged')
  })

  it('leave "no live quote" on the row even when the age was lifted', () => {
    const { container } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 quoteSuppress={['aged']}
                 row={withQuote('C', { quality: 'unavailable', age_seconds: null })} />)

    expect(container.querySelector('.flags')!.textContent).toContain('no live quote')
  })
})

const row = (ticker: string, marks: Mark[]): Row => ({
  ticker, name: ticker, segment: 'micro', divergence: 1, mention_z: 2,
  mentions: 20, expected: 6, ratio: 20 / 6, authors: 5, text_ratio: 0.1,
  sources: ['bluesky'], price: 1.5, price_move: 0.02, direction: 'up',
  price_status: 'ok', quote: {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 1.5,
    regular_move: 0.02, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: true, score_term: 'divergence',
    is_fallback: false,
    source: 'legacy',
    price_basis: 'trade',
    bid: null,
    ask: null,
  }, baseline_days: 2, marks, series: [], price_series: [],
  normal_per_hour: null,
  triplet: {}, tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '3.3x its normal' }],
})

describe('a mark carried by every row', () => {
  it('is lifted off the rows when the whole board has it', () => {
    /* The rule the session state already follows. Fourteen rows each saying
       "provisional" is not fourteen warnings, it is wallpaper. */
    const rows = [row('A', ['provisional']), row('B', ['provisional'])]

    expect(universalMarks(rows)).toEqual(['provisional'])
  })

  it('stays on the row when only some rows carry it', () => {
    const rows = [row('A', ['provisional']), row('B', [])]

    expect(universalMarks(rows)).toEqual([])
  })

  it('stays put on a one-row board', () => {
    /* "Every row" is trivially true of one row, and moving its only mark into
       the header would take it out of the place the reader is looking. */
    expect(universalMarks([row('A', ['provisional'])])).toEqual([])
  })

  it('is not rendered twice: the row drops what the header states', () => {
    const { container } = render(
      <TickerRow session="regular" row={row('A', ['provisional', 'single-source'])}
                 selected={false} suppress={['provisional']}
                 onSelect={() => {}} />)

    const meta = container.querySelector('.flags')!.textContent!
    expect(meta).toContain('single-source')
    expect(meta).not.toContain('provisional')
  })

  it('still renders a mark nobody suppressed', () => {
    /* The teeth check for the one above: if the row rendered no marks at all
       that test would pass on an empty string. */
    const { container } = render(
      <TickerRow session="regular" row={row('A', ['provisional'])} selected={false}
                 onSelect={() => {}} />)

    expect(container.querySelector('.flags')!.textContent)
      .toContain('provisional')
  })
})

describe('warming-up, a second thin-baseline mark', () => {
  /* leaderboard.py splits one badge into two: a NEW ticker is `provisional`,
     but a board-wide config-version change makes EVERY ticker `warming-up`
     instead -- see leaderboard.py's own comment where the mark is written.
     A mark the client does not know about renders as a raw key or nothing at
     all; these pin that it is lifted, rendered and worded the same way
     `provisional` already is. */
  it('is lifted off the rows when the whole board has it, like provisional', () => {
    const rows = [row('A', ['warming-up']), row('B', ['warming-up'])]

    expect(universalMarks(rows)).toEqual(['warming-up'])
  })

  it('stays on the row when only some rows carry it', () => {
    const rows = [row('A', ['warming-up']), row('B', [])]

    expect(universalMarks(rows)).toEqual([])
  })

  it('renders on the row like any other mark', () => {
    const { container } = render(
      <TickerRow session="regular" row={row('A', ['warming-up'])} selected={false}
                 onSelect={() => {}} />)

    expect(container.querySelector('.flags')!.textContent)
      .toContain('warming-up')
  })
})

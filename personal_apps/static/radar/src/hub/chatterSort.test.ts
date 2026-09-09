import { describe, expect, it } from 'vitest'

import { row, quote } from '../fixtures'
import type { Row } from '../types'
import {
  firstDirection, knownCount, nextSort, priceCurrencies, sortRows,
} from './chatterSort'

const tickers = (rows: Row[]) => rows.map((r) => r.ticker)

describe('the order it produces', () => {
  it('leaves the response order alone when nothing is sorted', () => {
    const rows = [row({ ticker: 'CCC' }), row({ ticker: 'AAA' })]
    expect(tickers(sortRows(rows, null))).toEqual(['CCC', 'AAA'])
  })

  it('never touches the array it was given', () => {
    const rows = [row({ ticker: 'CCC', authors: 1 }),
                  row({ ticker: 'AAA', authors: 9 })]
    const before = tickers(rows)
    const sorted = sortRows(rows, { key: 'voices', dir: 'desc' })
    expect(tickers(rows)).toEqual(before)
    expect(sorted).not.toBe(rows)
  })

  it('orders figures numerically, not as text', () => {
    // The whole reason this is not a string sort: "10" sorts before "2".
    const rows = [row({ ticker: 'TWO', authors: 2 }),
                  row({ ticker: 'TEN', authors: 10 }),
                  row({ ticker: 'NINE', authors: 9 })]
    expect(tickers(sortRows(rows, { key: 'voices', dir: 'desc' })))
      .toEqual(['TEN', 'NINE', 'TWO'])
    expect(tickers(sortRows(rows, { key: 'voices', dir: 'asc' })))
      .toEqual(['TWO', 'NINE', 'TEN'])
  })

  it('keeps the response order among rows that tie', () => {
    const rows = [row({ ticker: 'CCC', authors: 5 }),
                  row({ ticker: 'AAA', authors: 5 }),
                  row({ ticker: 'BBB', authors: 5 })]
    for (const dir of ['asc', 'desc'] as const) {
      expect(tickers(sortRows(rows, { key: 'voices', dir })))
        .toEqual(['CCC', 'AAA', 'BBB'])
    }
  })

  it('parks unknown values last in BOTH directions', () => {
    // Reversing a sort must not promote the rows nobody measured.
    const rows = [row({ ticker: 'NONE', ratio: null }),
                  row({ ticker: 'LOW', ratio: 1.2 }),
                  row({ ticker: 'HIGH', ratio: 8.4 })]
    expect(tickers(sortRows(rows, { key: 'attention', dir: 'desc' })))
      .toEqual(['HIGH', 'LOW', 'NONE'])
    expect(tickers(sortRows(rows, { key: 'attention', dir: 'asc' })))
      .toEqual(['LOW', 'HIGH', 'NONE'])
  })

  it('keeps unknown rows in response order among themselves', () => {
    const rows = [row({ ticker: 'N2', ratio: null }),
                  row({ ticker: 'K', ratio: 3 }),
                  row({ ticker: 'N1', ratio: null })]
    expect(tickers(sortRows(rows, { key: 'attention', dir: 'desc' })))
      .toEqual(['K', 'N2', 'N1'])
  })
})

describe('company', () => {
  it('sorts by ticker, not by the clamped company name', () => {
    // The name is truncated to one line on the desk layout; ordering by text
    // the reader cannot see is ordering by nothing.
    const rows = [row({ ticker: 'ZZZ', name: 'Aardvark Inc' }),
                  row({ ticker: 'AAA', name: 'Zephyr Inc' })]
    expect(tickers(sortRows(rows, { key: 'company', dir: 'asc' })))
      .toEqual(['AAA', 'ZZZ'])
  })

  it('compares tickers with digits the way a person reads them', () => {
    const rows = [row({ ticker: 'A10' }), row({ ticker: 'A2' })]
    expect(tickers(sortRows(rows, { key: 'company', dir: 'asc' })))
      .toEqual(['A2', 'A10'])
  })

  it('opens A-Z while every figure opens with its largest value', () => {
    expect(firstDirection('company')).toBe('asc')
    for (const key of ['attention', 'voices', 'sources', 'tone', 'price',
                       'move'] as const) {
      expect(firstDirection(key)).toBe('desc')
    }
  })
})

describe('sources', () => {
  it('orders by platforms, not by concrete feeds', () => {
    // Four subreddits are FOUR feeds and ONE platform. The cell says one
    // platform, so the sort has to agree with it.
    const rows = [
      row({ ticker: 'SUBS', activity_sources: ['reddit:a', 'reddit:b',
                                               'reddit:c', 'reddit:d'] }),
      row({ ticker: 'TWO', activity_sources: ['bluesky', 'reddit:a'] }),
    ]
    expect(tickers(sortRows(rows, { key: 'sources', dir: 'desc' })))
      .toEqual(['TWO', 'SUBS'])
  })

  it('tells a measured zero apart from a missing field', () => {
    const rows = [row({ ticker: 'MISSING', activity_sources: undefined }),
                  row({ ticker: 'ZERO', activity_sources: [] }),
                  row({ ticker: 'ONE', activity_sources: ['bluesky'] })]
    // Zero is a measurement and sorts; unknown is parked.
    expect(tickers(sortRows(rows, { key: 'sources', dir: 'desc' })))
      .toEqual(['ONE', 'ZERO', 'MISSING'])
    expect(tickers(sortRows(rows, { key: 'sources', dir: 'asc' })))
      .toEqual(['ZERO', 'ONE', 'MISSING'])
  })

  it('never falls back to the legacy source list', () => {
    // `sources` is every feed that was LOOKED AT -- the misleading count this
    // whole correction exists to stop displaying.
    const rows = [
      row({ ticker: 'LOOKED', sources: Array.from({ length: 36 },
             (_, i) => `reddit:s${i}`), activity_sources: ['bluesky'] }),
      row({ ticker: 'TALKING', sources: ['bluesky', 'fourchan'],
            activity_sources: ['bluesky', 'fourchan'] }),
    ]
    expect(tickers(sortRows(rows, { key: 'sources', dir: 'desc' })))
      .toEqual(['TALKING', 'LOOKED'])
  })
})

describe('tone', () => {
  it('separates two raw shares that print the same rounded label', () => {
    // Both label as "<0.1% bullish". The sort must still know which is larger.
    const rarer = row({ ticker: 'RARER',
                        tone: { bullish: 1, bearish: 2999, neutral: 0 } })
    const rare = row({ ticker: 'RARE',
                       tone: { bullish: 1, bearish: 1999, neutral: 0 } })
    expect(tickers(sortRows([rarer, rare], { key: 'tone', dir: 'desc' })))
      .toEqual(['RARE', 'RARER'])
  })

  it('treats a sample with no direction as unknown, never as 0% bullish', () => {
    const rows = [
      row({ ticker: 'NODIR', tone: { bullish: 0, bearish: 0, neutral: 45 } }),
      row({ ticker: 'NOSAMPLE', tone: { bullish: 0, bearish: 0, neutral: 0 } }),
      row({ ticker: 'BEARISH', tone: { bullish: 0, bearish: 9, neutral: 0 } }),
    ]
    // A truly 0% bullish row is a measurement and outranks the unknowns.
    expect(tickers(sortRows(rows, { key: 'tone', dir: 'asc' })))
      .toEqual(['BEARISH', 'NODIR', 'NOSAMPLE'])
    expect(tickers(sortRows(rows, { key: 'tone', dir: 'desc' })))
      .toEqual(['BEARISH', 'NODIR', 'NOSAMPLE'])
  })

  it('leaves a board with no tone at all in response order', () => {
    const rows = [row({ ticker: 'C', tone: { bullish: 0, bearish: 0, neutral: 0 } }),
                  row({ ticker: 'A', tone: { bullish: 0, bearish: 0, neutral: 0 } }),
                  row({ ticker: 'B', tone: { bullish: 0, bearish: 0, neutral: 0 } })]
    expect(tickers(sortRows(rows, { key: 'tone', dir: 'desc' })))
      .toEqual(['C', 'A', 'B'])
  })

  it('rejects malformed counts rather than scoring them zero', () => {
    const rows = [row({ ticker: 'BAD', tone: { bullish: -1, bearish: 2, neutral: 0 } }),
                  row({ ticker: 'OK', tone: { bullish: 1, bearish: 9, neutral: 0 } })]
    expect(tickers(sortRows(rows, { key: 'tone', dir: 'asc' })))
      .toEqual(['OK', 'BAD'])
  })
})

describe('price and today', () => {
  const priced = (ticker: string, price: number | null, currency: string | null,
                  quality = 'ok', move: number | null = 0.01) =>
    row({ ticker, price, price_move: move,
          quote: { ...quote(), price, currency, quality } as Row['quote'] })

  it('groups by currency rather than pretending they are converted', () => {
    const rows = [priced('USD_LO', 5, 'USD'), priced('EUR_HI', 400, 'EUR'),
                  priced('USD_HI', 300, 'USD'), priced('EUR_LO', 4, 'EUR')]
    // Descending reverses the whole ordering, currency group included.
    expect(tickers(sortRows(rows, { key: 'price', dir: 'desc' })))
      .toEqual(['USD_HI', 'USD_LO', 'EUR_HI', 'EUR_LO'])
    expect(tickers(sortRows(rows, { key: 'price', dir: 'asc' })))
      .toEqual(['EUR_LO', 'EUR_HI', 'USD_LO', 'USD_HI'])
  })

  it('names the currencies present so the page can say it groups', () => {
    const rows = [priced('A', 5, 'USD'), priced('B', 4, 'EUR'),
                  priced('C', 9, 'USD'), priced('D', null, null, 'unavailable')]
    expect(priceCurrencies(rows)).toEqual(['EUR', 'USD'])
    expect(priceCurrencies([priced('A', 5, 'USD')])).toEqual(['USD'])
  })

  it('treats an unavailable quote as unknown, both ways', () => {
    const rows = [priced('GONE', null, null, 'unavailable'),
                  priced('CHEAP', 1, 'USD'), priced('DEAR', 90, 'USD')]
    expect(tickers(sortRows(rows, { key: 'price', dir: 'desc' })))
      .toEqual(['DEAR', 'CHEAP', 'GONE'])
    expect(tickers(sortRows(rows, { key: 'price', dir: 'asc' })))
      .toEqual(['CHEAP', 'DEAR', 'GONE'])
  })

  it('keeps a zero move as a value and a missing one as unknown', () => {
    // 0% is a fact: the price did not move.
    const rows = [priced('UNKNOWN', 10, 'USD', 'ok', null),
                  priced('FLAT', 10, 'USD', 'ok', 0),
                  priced('DOWN', 10, 'USD', 'ok', -0.05)]
    expect(tickers(sortRows(rows, { key: 'move', dir: 'desc' })))
      .toEqual(['FLAT', 'DOWN', 'UNKNOWN'])
    expect(tickers(sortRows(rows, { key: 'move', dir: 'asc' })))
      .toEqual(['DOWN', 'FLAT', 'UNKNOWN'])
  })

  it('sorts the move without regard to the currency it moved in', () => {
    // A percentage move is comparable across currencies; a price is not.
    const rows = [priced('EUR_UP', 4, 'EUR', 'ok', 0.09),
                  priced('USD_UP', 400, 'USD', 'ok', 0.02)]
    expect(tickers(sortRows(rows, { key: 'move', dir: 'desc' })))
      .toEqual(['EUR_UP', 'USD_UP'])
  })
})

describe('the control’s own rules', () => {
  it('flips the active column and opens any other one', () => {
    expect(nextSort(null, 'tone')).toEqual({ key: 'tone', dir: 'desc' })
    expect(nextSort({ key: 'tone', dir: 'desc' }, 'tone'))
      .toEqual({ key: 'tone', dir: 'asc' })
    expect(nextSort({ key: 'tone', dir: 'asc' }, 'tone'))
      .toEqual({ key: 'tone', dir: 'desc' })
    expect(nextSort({ key: 'tone', dir: 'asc' }, 'company'))
      .toEqual({ key: 'company', dir: 'asc' })
  })

  it('counts how many rows a key can actually order', () => {
    const rows = [row({ ratio: 1 }), row({ ratio: null }), row({ ratio: 3 })]
    expect(knownCount(rows, 'attention')).toBe(2)
    expect(knownCount(rows, 'company')).toBe(3)
  })
})

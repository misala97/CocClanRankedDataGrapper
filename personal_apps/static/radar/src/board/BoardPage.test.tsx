import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BoardPayload, Row } from '../types'
import { BoardPage } from './BoardPage'

function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, authors: 9,
    text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    price_series: [{ at: 't0', price: 10 }, { at: 't1', price: 10.1 }],
    ...over,
  }
}

function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    sources: ['stocktwits', 'bluesky', 'fourchan'],
    all_sources: ['stocktwits', 'bluesky', 'fourchan'],
    segment: null, window_hours: 4,
    segment_counts: { all: 4, large: 4 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' }),
           row({ ticker: 'CCC' }), row({ ticker: 'DDD' })],
    ...over,
  }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, redirected: false, json: async () => payload(),
  })))
  window.history.replaceState(null, '', '/radar/')
})
afterEach(() => vi.unstubAllGlobals())

describe('what the board shows', () => {
  it('promotes the first three rows and tabulates the rest', () => {
    const { container } = render(<BoardPage initial={payload()} />)

    expect(container.querySelectorAll('.lead')).toHaveLength(3)
    expect(container.querySelectorAll('.row')).toHaveLength(1)
  })

  it('does not fetch on mount -- the first board is already in the document', () => {
    render(<BoardPage initial={payload()} />)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps mention z and price move visible as separate quantities', () => {
    // PRODUCT.md's one non-negotiable: loud-and-unmoved and quiet-and-dumping
    // can score alike, so the two parts may never collapse into the score.
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row')!

    const cells = within(scan as HTMLElement)
    expect(cells.getByText('+0.50')).toBeInTheDocument()
    expect(cells.getByText('3.2')).toBeInTheDocument()
    // Twice: the wide grid's own cell, plus the caption the mobile layout
    // shows instead. Exactly one of the two is displayed at any width.
    expect(cells.getAllByText('+1.20%')).toHaveLength(2)
  })
})

describe('a number that cannot be taken at face value', () => {
  it('shows no price move at all when the tape is frozen', () => {
    // The bug this pins: a stale tape reports move 0.0 because both prints are
    // identical, and rendering "0.00%" asserts the price held steady when in
    // fact nothing traded.
    const frozen = payload({
      rows: [row(), row(), row(), row({
        ticker: 'ZZZ', price_status: 'stale', price_move: 0,
        divergence: null, marks: ['no-print'],
      })],
    })
    const { container } = render(<BoardPage initial={frozen} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(within(scan).queryByText('0.00%')).not.toBeInTheDocument()
    expect(within(scan).getAllByText('—')).toHaveLength(2)
    expect(within(scan).getByText('not scored')).toBeInTheDocument()
  })

  it('puts every mark on the row rather than behind a hover', () => {
    const marked = payload({
      rows: [row(), row(), row(),
             row({ ticker: 'ZZZ', marks: ['provisional', 'single-source'] })],
    })
    render(<BoardPage initial={marked} />)

    expect(screen.getByRole('button', { name: /^provisional/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /^single-source/ })).toBeVisible()
  })

  it('explains a mark when it is pressed', async () => {
    const marked = payload({
      rows: [row(), row(), row(), row({ ticker: 'ZZZ', marks: ['no-print'] })],
    })
    render(<BoardPage initial={marked} />)

    await userEvent.click(screen.getByRole('button', { name: /^no-print/ }))

    expect(screen.getByRole('status')).toHaveTextContent(/tape has not printed/)
  })
})

describe('the controls', () => {
  it('refetches and rewrites the address bar when a source is dropped', async () => {
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('button', { name: /4chan/ }))

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
    expect(vi.mocked(fetch).mock.calls[0][0])
      .toBe('/radar/api/board?sources=stocktwits%2Cbluesky&window=4')
    await waitFor(() =>
      expect(window.location.search).toBe('?sources=stocktwits%2Cbluesky&window=4'))
  })

  it('will not let the last source be turned off', async () => {
    const one = payload({ sources: ['bluesky'] })
    render(<BoardPage initial={one} />)

    const chip = screen.getByRole('button', { name: /Bluesky/ })
    expect(chip).toBeDisabled()
    await userEvent.click(chip)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps the selected segment visible even when it now holds nothing', async () => {
    // Otherwise the reader stares at an empty board with no control on screen
    // saying which filter emptied it.
    const filtered = payload({
      segment: 'micro', rows: [], segment_counts: { all: 0 },
    })
    render(<BoardPage initial={filtered} />)

    const chip = screen.getByRole('button', { name: /^Micro/ })
    expect(chip).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Nothing in this segment/)).toBeInTheDocument()
  })

  it('keeps the previous board on screen when a refresh fails', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    const { container } = render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('button', { name: '24h' }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(container.querySelectorAll('.lead')).toHaveLength(3)
  })
})

describe('an empty board', () => {
  it('explains the floor rather than announcing a void', () => {
    render(<BoardPage initial={payload({ rows: [], segment_counts: { all: 0 } })} />)

    expect(screen.getByText(/Nothing has cleared the floor/)).toBeInTheDocument()
    expect(screen.getByText(/distinct authors and distinct/)).toBeInTheDocument()
  })

  it('names the sources in the words the chips use', () => {
    render(<BoardPage initial={payload({
      rows: [], sources: ['fourchan'], segment_counts: { all: 0 },
    })} />)

    // The chip carries the same words, so scope to the empty panel.
    const panel = document.querySelector('.empty') as HTMLElement
    expect(within(panel).getByText(/4chan \/biz\//)).toBeInTheDocument()
  })
})

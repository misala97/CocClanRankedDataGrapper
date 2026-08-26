import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BoardPayload, Detail, Row } from '../types'
import { BoardPage } from './BoardPage'

function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, ratio: 20 / 6,
    authors: 9,
    text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    clauses: [{ kind: 'ratio', text: '3x its normal' },
              { kind: 'venues', text: '2 venues' }],
    ...over,
  }
}

function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, venue_counts: { any: 4, multi: 2 },
    segment_counts: { all: 4, large: 4 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' }),
           row({ ticker: 'CCC' }), row({ ticker: 'DDD' })],
    excluded: {},
    ...over,
  }
}

function detail(ticker = 'AAA'): Detail {
  return {
    identity: {
      ticker, name: 'Alpha Inc', exchange: 'NASDAQ', segment: 'large',
      market_cap: 1e9, ipo_date: '2020-01-01', price: 10, price_move: 0.012,
      price_status: 'ok', session: 'regular',
    },
    read: [{ kind: 'plain', text: `${ticker} is being discussed.` }],
    chart: {
      from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, (_, i) => 100 + i),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
      watched_from: '2026-08-18',
    },
    breakdown: {
      venues: [{ source: 'bluesky', mentions: 20, voices: 9 }],
      bullish: 4, neutral: 10, bearish: 2,
      top_author_share: 0.2, top_two_share: 0.3,
      peak_hour: '2026-08-22T14:00:00Z', peak_count: 9,
      first_seen: '2026-08-18', mentions: 20, voices: 9,
    },
    posts: [], post_total: 0,
  }
}

/** Route by URL. The page makes two different requests now, and a stub that
 *  answered both with a board payload would hand the panel the wrong shape. */
function stubFetch(board: BoardPayload = payload()) {
  const spy = vi.fn(async (url: string) => ({
    ok: true,
    redirected: false,
    json: async () => (url.includes('/api/ticker/')
      ? detail(url.split('/api/ticker/')[1]!.split('?')[0]!)
      : board),
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => {
  stubFetch()
  window.history.replaceState(null, '', '/radar/')
})
afterEach(() => vi.unstubAllGlobals())

const boardCalls = () => vi.mocked(fetch).mock.calls
  .map((c) => String(c[0])).filter((u) => u.includes('/api/board'))

describe('the two panes', () => {
  it('lists one row per ticker, with no promoted tier', () => {
    /* The two-tier arrangement is gone. It bought visual variety at the cost
       of making identical data look like two different kinds of thing. */
    const { container } = render(<BoardPage initial={payload()} />)

    expect(container.querySelectorAll('.row')).toHaveLength(4)
    expect(container.querySelectorAll('.lead')).toHaveLength(0)
  })

  it('opens on the top row so the page is useful with no clicks', async () => {
    render(<BoardPage initial={payload()} />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /AAA/ }))
        .toHaveAttribute('aria-current', 'true'))
  })

  it('opens on the ticker in the address bar instead, when there is one', async () => {
    /* "What happened to the one I spotted yesterday" is a real question for a
       radar, so a bookmarked ticker has to survive a reload. */
    window.history.replaceState(null, '', '/radar/?t=CCC')

    render(<BoardPage initial={payload()} />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /CCC/ }))
        .toHaveAttribute('aria-current', 'true'))
  })

  it('does not fetch the board on mount -- it is already in the document', () => {
    render(<BoardPage initial={payload()} />)

    expect(boardCalls()).toHaveLength(0)
  })

  it('fetches the panel for the opening ticker', async () => {
    render(<BoardPage initial={payload()} />)

    await waitFor(() => expect(vi.mocked(fetch).mock.calls
      .some((c) => String(c[0]).includes('/api/ticker/AAA'))).toBe(true))
  })
})

describe('selecting a ticker', () => {
  it('swaps the panel without refetching the board', async () => {
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))

    await screen.findByText(/BBB is being discussed/)
    expect(boardCalls()).toHaveLength(0)
  })

  it('puts the ticker in the address bar', async () => {
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))

    await waitFor(() =>
      expect(window.location.search).toContain('t=BBB'))
  })
})

describe('the controls', () => {
  it('refetches and rewrites the address bar when a source is dropped', async () => {
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('button', { name: /4chan/ }))

    await waitFor(() => expect(boardCalls()).toHaveLength(1))
    expect(boardCalls()[0]).toBe(
      '/radar/api/board?sources=bluesky%2Creddit&window=4&segment=')
    await waitFor(() =>
      expect(window.location.search)
        .toContain('sources=bluesky%2Creddit&window=4&segment='))
  })

  it('keeps All in the address bar rather than omitting it', async () => {
    /* The server's default segment is Small, so a URL with no segment param
       reloads as Small. Sharing the All view has to survive a reload, which
       means the empty value is the state, not the absence of one. */
    render(<BoardPage initial={payload({ segments: ['small'] })} />)

    await userEvent.click(screen.getByRole('button', { name: /^All/ }))

    await waitFor(() => expect(window.location.search).toContain('segment='))
    expect(window.location.search).not.toContain('segment=small')
  })

  it('will not let the last source be turned off', async () => {
    render(<BoardPage initial={payload({ sources: ['bluesky'] })} />)

    expect(screen.getByRole('button', { name: /Bluesky/ })).toBeDisabled()
  })

  it('renders every segment chip whatever the data says', () => {
    /* Michi, 2026-08-23: "the settings are bad and switch around". They did --
       chips were filtered by count, so a segment with no rows vanished and
       came back as data changed, moving everything else under the cursor. */
    render(<BoardPage initial={payload({
      segment_counts: { all: 1, micro: 1 },
    })} />)

    for (const label of ['Small', 'All', 'Large', 'Mid', 'Micro',
                         'Recent IPO', 'Unknown']) {
      expect(screen.getByRole('button', { name: new RegExp(`^${label}`) }))
        .toBeInTheDocument()
    }
  })

  it('does not put the chart span in the board controls', () => {
    /* The span belongs to the panel: it changes one ticker's chart, not which
       rows the board lists. */
    render(<BoardPage initial={payload()} />)

    expect(screen.queryByRole('button', { name: /^3M$/ })).toBeNull()
  })
})

describe('when the board changes under the selection', () => {
  it('moves to the top row if the selected ticker is filtered out', async () => {
    /* Leaving the panel on a ticker the list no longer contains puts a stock
       on screen that the list beside it says is not in view. */
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    stubFetch(payload({ rows: [row({ ticker: 'ZZZ' })] }))
    await userEvent.click(screen.getByRole('button', { name: /2\+/ }))

    await waitFor(() =>
      expect(window.location.search).toContain('t=ZZZ'))
  })
})

describe('the account of what was left out', () => {
  it('is shown beneath the rows', () => {
    render(<BoardPage initial={payload({
      excluded: { too_few_voices: 9, one_venue: 4 },
    })} />)

    expect(screen.getByText(/13 other tickers/)).toBeInTheDocument()
  })
})

describe('when the board cannot be reached', () => {
  it('keeps the last board and says the refresh failed', async () => {
    render(<BoardPage initial={payload()} />)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('nope') }))

    await userEvent.click(screen.getByRole('button', { name: /4chan/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not reach/)
    expect(screen.getByRole('link', { name: /AAA/ })).toBeInTheDocument()
  })
})

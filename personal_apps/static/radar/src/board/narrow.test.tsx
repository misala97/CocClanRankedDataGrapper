// Below 900px the page stacks, and the critique of 2026-09-01 measured what
// that did: a row tap changed nothing on screen for 1-2s because the panel
// sat under the list, the excluded account AND the marks legend, ~1900px
// down, and focus only moved there once the detail had loaded.

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BoardPage } from './BoardPage'
import type { BoardPayload, Detail, MarketQuote, Row } from '../types'

function quote(): MarketQuote {
  return {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 10,
    regular_move: 0.012, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: true, score_term: 'divergence',
    is_fallback: false, source: 'legacy', price_basis: 'trade',
    bid: null, ask: null,
  }
}

function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, ratio: 20 / 6,
    authors: 9, text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    price_series: Array.from({ length: 25 }, () => null),
    normal_per_hour: null,
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    clauses: [{ kind: 'ratio', text: '3x its normal' }],
    ...over, quote: over.quote ?? quote(),
  }
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
    min_venues: 1, venue_counts: { any: 2, multi: 1 },
    segment_counts: { all: 2, large: 2 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' })],
    excluded: { too_few_voices: 9 },
    ...over,
  }
}

function detail(ticker = 'AAA'): Detail {
  return {
    market: 'us', display_timezone: 'Europe/Berlin',
    identity: {
      ticker, name: 'Alpha Inc', exchange: 'N', segment: 'large',
      market_cap: 1e9, ipo_date: '2020-01-01', price: 10, price_move: 0.012,
      price_status: 'ok', session: 'regular', quote: quote(),
    },
    read: [{ kind: 'plain', text: `${ticker} is being discussed.` }],
    chart: {
      from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, (_, i) => 100 + i),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
      sessions: [], history_proxy: false, proxy_mic: null, proxy_venue: null,
      native_mic: null, native_venue: null, native_from: null,
      normal_per_slot: null, watched_from: '2026-08-18',
    },
    breakdown: {
      venues: [{ source: 'bluesky', mentions: 20, voices: 9 }],
      bullish: 4, neutral: 10, bearish: 2, disagreements: 1,
      top_author_share: 0.2, top_two_share: 0.3,
      peak_hour: '2026-08-22T14:00:00Z', peak_count: 9,
      first_seen: '2026-08-18', mentions: 20, voices: 9,
    },
    posts: [], post_total: 0,
  }
}

/** A detail request that answers only when the test says so. */
function stubFetch(release?: { resolve: () => void }) {
  const gate = release
    ? new Promise<void>((resolve) => { release.resolve = resolve })
    : Promise.resolve()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/api/ticker/')) await gate
    return {
      ok: true, redirected: false, status: 200,
      json: async () => (url.includes('/api/ticker/')
        ? detail(url.split('/api/ticker/')[1]!.split('?')[0]!)
        : payload()),
    }
  }))
}

/** jsdom has no layout, so the stacked layout is declared, not measured. */
function viewport(narrow: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: narrow && query.includes('max-width'),
    media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })))
}

beforeEach(() => {
  stubFetch()
  window.history.replaceState(null, '', '/radar/')
  HTMLElement.prototype.scrollIntoView = vi.fn()
})
afterEach(() => vi.unstubAllGlobals())

const follows = (a: Element, b: Element) =>
  Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)

describe('the stacked layout', () => {
  it('puts the account of what was left out after the panel', async () => {
    viewport(true)
    const { container } = render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    const account = screen.getByText(/9 other tickers/)
    expect(follows(container.querySelector('.detail')!, account)).toBe(true)
    expect(account.closest('.list')).toBeNull()
  })

  it('keeps that account inside the list on a desk', async () => {
    viewport(false)
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    expect(screen.getByText(/9 other tickers/).closest('.list')).not.toBeNull()
  })

  it('brings the panel into view the moment a row is tapped', async () => {
    viewport(true)
    const release = { resolve: () => {} }
    stubFetch(release)
    const { container } = render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))

    // Before the detail answers: the scroll is the tap's own feedback.
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled()
    expect(vi.mocked(HTMLElement.prototype.scrollIntoView).mock.instances[0])
      .toBe(container.querySelector('.detail'))
    release.resolve()
    await screen.findByText(/BBB is being discussed/)
  })

  it('does not scroll on a desk, where the panel is already beside the list', async () => {
    viewport(false)
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))
    await screen.findByText(/BBB is being discussed/)

    expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('the panel while a ticker loads', () => {
  it('is a skeleton in the panel\'s own shape, not a line of grey text', async () => {
    const release = { resolve: () => {} }
    stubFetch(release)
    render(<BoardPage initial={payload()} />)

    const main = await screen.findByRole('main', { busy: true })
    expect(main.querySelectorAll('.sk').length).toBeGreaterThanOrEqual(3)
    // Still announced in words: the skeleton is decoration to a reader who
    // cannot see it.
    expect(main).toHaveTextContent('Loading AAA')

    release.resolve()
    await waitFor(() => expect(screen.queryByRole('main', { busy: true })).toBeNull())
  })
})

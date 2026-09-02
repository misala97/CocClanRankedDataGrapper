// Shapes for tests: one quote, one board row, one payload, one detail -- the
// ones BoardPage.test.tsx grew, exported so the newer suites do not each
// carry a forty-line copy. Not imported by app code, so never bundled.
import type { BoardPayload, Detail, MarketQuote, Row } from './types'

export function quote(): MarketQuote {
  return {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 10,
    regular_move: 0.012, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: true, score_term: 'divergence',
    is_fallback: false,
    source: 'legacy',
    price_basis: 'trade',
    bid: null,
    ask: null,
  }
}

export function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, ratio: 20 / 6,
    authors: 9,
    text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    price_series: Array.from({ length: 25 }, () => null),
    normal_per_hour: null,
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    clauses: [{ kind: 'ratio', text: '3x its normal' },
              { kind: 'venues', text: '2 venues' }],
    eligible: true,
    ...over, quote: over.quote ?? quote(),
  }
}

export function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    market: 'us', display_timezone: 'Europe/Berlin',
    market_venue: 'US markets', next_boundary_label: 'closes',
    next_boundary_at: '2026-08-22T20:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, venue_counts: { any: 4, multi: 2 },
    segment_counts: { all: 4, large: 4 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' }),
           row({ ticker: 'CCC' }), row({ ticker: 'DDD' })],
    excluded: {},
    watching: [], watch_rows: [],
    ...over,
  }
}

export function detail(ticker = 'AAA', market: Detail['market'] = 'us'): Detail {
  return {
    market, display_timezone: 'Europe/Berlin',
    identity: {
      ticker, name: 'Alpha Inc', exchange: 'NASDAQ', segment: 'large',
      market_cap: 1e9, ipo_date: '2020-01-01', price: 10, price_move: 0.012,
      price_status: 'ok', session: 'regular',
      quote: quote(),
    },
    read: [{ kind: 'plain', text: market === 'de'
      ? `${ticker} on de is being discussed.`
      : `${ticker} is being discussed.` }],
    chart: {
      from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, (_, i) => 100 + i),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
      sessions: [],
      history_proxy: false, proxy_mic: null, proxy_venue: null,
      native_mic: null, native_venue: null, native_from: null,
      normal_per_slot: null,
      watched_from: '2026-08-18',
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

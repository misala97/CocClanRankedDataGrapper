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
    text_ratio: 0.9, sources: ['bluesky'], activity_sources: ['bluesky'],
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

/** The delivery fields every board response carries, in the shape a worker
 *  that built its own board writes them: shared with nobody, waiting for
 *  nothing, and as old as the instant it was built.
 *
 *  Exported because four other suites keep their own payload factory -- each
 *  for its own reason -- and none of them is about the envelope. Spreading
 *  this keeps them describing what they are actually testing.
 */
export type Envelope = Pick<BoardPayload,
  'shared' | 'pending' | 'busy' | 'stale' | 'failed' | 'as_of' | 'built_at'
  | 'age_seconds' | 'fresh_seconds' | 'hard_expiry_seconds' | 'retry_after_ms'
  | 'queue_age_seconds' | 'ops_collected_at'>

export function envelope(over: Partial<Envelope> = {}): Envelope {
  return {
    shared: false, pending: false, busy: false, stale: false, failed: false,
    as_of: '2026-08-22T19:00:00Z', built_at: '2026-08-22T19:00:00Z',
    age_seconds: 0,
    // board_store.Bounds' own defaults, so a fixture cannot quietly disagree
    // with the server about when a board goes stale or stops counting.
    fresh_seconds: 120, hard_expiry_seconds: 600,
    retry_after_ms: null, queue_age_seconds: null,
    ops_collected_at: '2026-08-22T19:00:00Z',
    ...over,
  }
}

export function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    ...envelope(),
    generated_at: '2026-08-22T19:00:00Z',
    market: 'us', display_timezone: 'Europe/Berlin',
    market_venue: 'US markets', next_boundary_label: 'closes',
    next_boundary_at: '2026-08-22T20:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, venue_counts: { any: 4, multi: 2 },
    sort: null, dir: 'desc',
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
      currency: null, basis_venue: null, converted_from: null,
      priced_from: 'daily',
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

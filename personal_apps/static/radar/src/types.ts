// The board payload, exactly as features/radar/routes/api.py serializes it.
//
// One shape, two delivery routes: embedded in the document on first paint and
// fetched from /radar/api/board on every control change. There is deliberately
// no separate "initial" type -- a second shape is a second thing to keep in
// sync, and the first divergence would show up as a blank panel.

/** A mention count for one hour. `null` means the hour was never measured --
 *  ingest was down, or the sources were unreachable. It is not a quiet hour
 *  and must never render as a zero. */
export interface Point {
  hour: string
  count: number | null
}

export interface Tone {
  bullish: number
  neutral: number
  bearish: number
}

/** Why a number on this row cannot be taken at face value. Rendered, never
 *  hidden behind a hover -- see PRODUCT.md. */
export type Mark =
  'no-print' | 'provisional' | 'single-source' | 'partial' | 'warming-up'

/** `fund` is a pooled vehicle -- an ETF, an ETN, an index product. It is
 *  deliberately outside the `small` group and therefore off the default
 *  board: a fund has no market cap to look up, so before it had a segment
 *  of its own it fell through to `unknown`, and SPY sat in the tab meant
 *  for penny stocks nobody has heard of. */
export type Segment = 'large' | 'mid' | 'micro' | 'unknown' | 'recent_ipo'
                    | 'fund'

/** What the reader can filter BY, which is a wider vocabulary than what a row
 *  can BE. `small` is a group over the three segments below mid; no row ever
 *  reports it, so Row.segment stays the narrower type. */
export type SegmentFilter = Segment | 'small'

/** One styled fragment of a phrase.
 *
 *  The client styles by `kind` and never parses `text`. The wording is decided
 *  in features/radar/phrasing.py, so there is exactly one implementation of
 *  that judgement -- a component that rebuilt "40x its normal" from mentions
 *  and expected would be a second one, free to disagree. */
export interface Clause {
  kind: 'ratio' | 'venues' | 'people' | 'price-up' | 'price-down'
      | 'price-flat' | 'new' | 'warn' | 'plain'
  text: string
}

/** How far back the panel's chart reaches. Owned by the panel, not the board:
 *  it changes one ticker's chart, not which rows are listed. */
export type PanelSpan = '1D' | '1W' | '1M' | '6M' | '1Y' | '3Y'

/** Price context is independent from Radar's stable social ticker identity. */
export type Market = 'us' | 'de'

/** The provider's freshness classification, never inferred from a missing
 * price on the client. */
export type QuoteQuality = 'live' | 'delayed' | 'eod' | 'stale' | 'unavailable'

/** One selected venue quote. Germany-mode fallbacks retain their real US/USD
 * identity rather than appearing as converted German quotes. */
export interface MarketQuote {
  market: Market
  venue: string | null
  mic: string | null
  currency: string
  price: number | null
  regular_move: number | null
  extended_move: number | null
  session: Session
  quality: QuoteQuality
  age_seconds: number | null
  quoted_at: string | null
  is_fallback: boolean
}

/** Price and chatter over the same calendar days, sharing `from`.
 *
 *  `closes[i]` null means the market did not trade that day -- the line is
 *  drawn across it. `chatter[i]` null means we were not watching yet -- no bar
 *  is drawn at all. Two different absences, deliberately not collapsed. */
export interface DetailChart {
  /** ISO instant. A datetime, not a date -- a 15-minute slot cannot be
   *  placed by a calendar day alone. */
  from: string
  span: PanelSpan
  /** How wide one slot is. 1440 on the day-indexed spans, minutes on the
   *  intraday ones. The chart draws evenly spaced slots and cannot tell
   *  minutes from days without being told. */
  step_minutes: number
  closes: (number | null)[]
  chatter: (number | null)[]
  /** The day observation began. Before it the chatter lane is unobserved
   *  rather than silent, and the panel draws that boundary. */
  watched_from: string | null
}

export interface Post {
  source: string
  author: string | null
  channel: string
  created: string
  title: string | null
  body: string | null
  url: string | null
}

export interface Venue {
  source: string
  mentions: number
  voices: number
}

export interface Breakdown {
  venues: Venue[]
  bullish: number
  neutral: number
  bearish: number
  /** How often the word list and the model read the same post the opposite
   *  way -- the sarcasm the lexicon alone cannot see. */
  disagreements: number
  /** The pump tell: one account posting forty times reads as forty mentions
   *  everywhere else on the surface. */
  top_author_share: number | null
  top_two_share: number | null
  peak_hour: string | null
  peak_count: number
  first_seen: string | null
  mentions: number
  voices: number
}

export interface Detail {
  market: Market
  display_timezone: 'Europe/Berlin'
  identity: {
    ticker: string
    name: string | null
    exchange: string | null
    segment: Segment
    market_cap: number | null
    ipo_date: string | null
    price: number | null
    price_move: number | null
    price_status: string
    session: Session
    quote: MarketQuote
  }
  read: Clause[]
  chart: DetailChart
  breakdown: Breakdown
  posts: Post[]
  post_total: number
}

export interface Row {
  ticker: string
  name: string | null
  segment: Segment
  /** null when the row could not be scored -- no quote, or a frozen tape. */
  divergence: number | null
  mention_z: number | null
  mentions: number
  expected: number
  /** How many times its own normal this is. `null` where there is no baseline
   *  worth dividing by -- the same guard that makes the phrase say "new here",
   *  decided once in phrasing.py. The row draws its bar from this and never
   *  from `mentions / expected`, which would be a second opinion about when a
   *  baseline is thick enough to mean anything. */
  ratio: number | null
  authors: number
  text_ratio: number
  sources: string[]
  price: number | null
  price_move: number | null
  direction: 'up' | 'down' | 'flat'
  /** 'closed' is the exchange being shut; 'stale' is this tape not printing
   *  while the market is open. Only the second says anything about the stock,
   *  and only the second earns the no-print mark. */
  price_status: 'ok' | 'closed' | 'stale' | 'unknown'
  quote: MarketQuote
  baseline_days: number | null
  marks: Mark[]
  series: Point[]
  /** Keyed by window length in hours, as a string: {"1": 3.1, "4": ...}. */
  triplet: Record<string, number | null>
  tone: Tone
  /** Why this row is on the list. The chart used to live here and moved to
   *  the panel: at the 3Y span it is ~780 numbers, and a twenty-row board
   *  would have carried sixteen thousand of them to draw twenty sparklines. */
  clauses: Clause[]
}

/** The exchange's state. It changes what the ranking MEANS, not merely how it
 *  is decorated: with the market shut there is no price movement to diverge
 *  from, so the board ranks on chatter alone. */
export type Session = 'premarket' | 'regular' | 'afterhours' | 'closed'

export interface BoardPayload {
  generated_at: string
  market: Market
  display_timezone: 'Europe/Berlin'
  sources: string[]
  all_sources: string[]
  /** What the board was filtered to. Empty means All. */
  segments: SegmentFilter[]
  session: Session
  /** 1 = any, 2 = only rows more than one venue is talking about. */
  min_venues: number
  venue_counts: Record<string, number>
  window_hours: number
  segment_counts: Record<string, number>
  triplet_hours: number[]
  series_hours: number
  lead_count: number
  rows: Row[]
  /** What the eligibility floor and the breadth filter left out, by reason.
   *  Without it a quiet board and a stopped ingest look identical. */
  excluded: Record<string, number>
  /** What the model tone pass has cost. SPEND, never a balance -- the Claude
   *  API has no balance endpoint, so nothing here knows what is left. Absent
   *  until the first pass books something. */
  spend?: { today_usd: number; month_usd: number; unpriced_tokens: number }
}

export interface Selection {
  market: Market
  sources: string[]
  /** Server-side filter, unlike the chart span -- changing it refetches. */
  minVenues: number
  /** Several, and a union -- picking a second chip asks to see more. Empty
   *  is no filter, which is what the All chip sets. */
  segments: SegmentFilter[]
  window: number
}

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

export interface PricePoint {
  at: string
  price: number | null
}

/** Why a number on this row cannot be taken at face value. Rendered, never
 *  hidden behind a hover -- see PRODUCT.md. */
export type Mark = 'no-print' | 'provisional' | 'single-source' | 'partial'

export type Segment = 'large' | 'mid' | 'micro' | 'unknown' | 'recent_ipo'

export interface Row {
  ticker: string
  name: string | null
  segment: Segment
  /** null when the row could not be scored -- no quote, or a frozen tape. */
  divergence: number | null
  mention_z: number | null
  mentions: number
  expected: number
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
  baseline_days: number | null
  marks: Mark[]
  series: Point[]
  /** Keyed by window length in hours, as a string: {"1": 3.1, "4": ...}. */
  triplet: Record<string, number | null>
  tone: Tone
  /** Only the lead rows carry one; everything else gets an empty array. */
  price_series: PricePoint[]
}

/** The exchange's state. It changes what the ranking MEANS, not merely how it
 *  is decorated: with the market shut there is no price movement to diverge
 *  from, so the board ranks on chatter alone. */
export type Session = 'premarket' | 'regular' | 'afterhours' | 'closed'

export interface BoardPayload {
  generated_at: string
  sources: string[]
  all_sources: string[]
  segment: Segment | null
  session: Session
  window_hours: number
  segment_counts: Record<string, number>
  triplet_hours: number[]
  series_hours: number
  lead_count: number
  rows: Row[]
}

export interface Selection {
  sources: string[]
  segment: Segment | null
  window: number
}

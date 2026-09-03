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
 *  deliberately outside the `discover` group and therefore off the default
 *  board: a fund has no market cap to look up, so before it had a segment
 *  of its own it fell through to `unknown`, and SPY sat in the tab meant
 *  for the stuff nobody has heard of. */
export type Segment = 'large' | 'mid' | 'micro' | 'unknown' | 'recent_ipo'
                    | 'fund'

/** What the reader can filter BY, which is a wider vocabulary than what a row
 *  can BE. `discover` is a group over mid, micro and unknown (recent IPOs
 *  stay out -- a fresh listing is not automatically obscure); no row ever
 *  reports it, so Row.segment stays the narrower type. */
export type SegmentFilter = Segment | 'discover'

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
export type QuoteScoreTerm = 'divergence' | 'chatter'

/** A named extended trading range, kept in UTC like every chart instant. */
export interface ChartSession {
  start: string
  end: string
  kind: Extract<Session, 'premarket' | 'afterhours' | 'closed'>
}

/** One selected venue quote. Germany-mode fallbacks retain their real US/USD
 * identity rather than appearing as converted German quotes. */
export interface MarketQuote {
  market: Market
  venue: string | null
  mic: string | null
  currency: string | null
  price: number | null
  regular_move: number | null
  extended_move: number | null
  session: Session
  quality: QuoteQuality
  age_seconds: number | null
  quoted_at: string | null
  /** Frozen-tape verdict from quote history, independent of provider freshness. */
  tape_status: 'ok' | 'closed' | 'stale' | 'unknown'
  /** Server-side decision; never re-derived from the displayed session. */
  score_eligible: boolean
  score_term: QuoteScoreTerm
  is_fallback: boolean
  /** Market-data v2 provenance. Null on legacy rows; never controls
   *  client-side eligibility. */
  source: QuoteSource | null
  price_basis: PriceBasis | null
  bid: number | null
  ask: number | null
}

export type PriceBasis = 'trade' | 'midpoint' | 'close'
export type QuoteSource =
  | 'legacy' | 'finnhub' | 'twelvedata'
  | 'deutsche_boerse_delayed' | 'yahoo_chart'

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
  /** The ticker's own normal chatter rate per SLOT of this chart, through
   *  the same server-side guard as `ratio` -- null when the baseline is too
   *  thin to divide by. Drawn as the dashed line, exactly as on the rows. */
  normal_per_slot: number | null
  /** Extended-session ranges, clipped to this chart's intraday window. */
  sessions: ChartSession[]
  /** The day observation began. Before it the chatter lane is unobserved
   *  rather than silent, and the panel draws that boundary. */
  watched_from: string | null
  /** Xetra->Tradegate history-seam provenance (spec 8.2): older Xetra
   *  closes may seed a Tradegate chart for the same ISIN, labelled, with
   *  one seam at `native_from`. All false/null on every other identity
   *  and on the intraday spans. */
  history_proxy: boolean
  proxy_mic: string | null
  proxy_venue: string | null
  native_mic: string | null
  native_venue: string | null
  native_from: string | null
}

export interface Post {
  source: string
  author: string | null
  channel: string
  created: string
  title: string | null
  body: string | null
  url: string | null
  /** The §7.1 tone read the tallies use, per post -- 'neutral' covers a
   *  decided even-handed read and a not-yet-scored mention alike. */
  tone: 'bullish' | 'bearish' | 'neutral'
  /** Who decided `tone`: the model (a decided neutral included), the local
   *  wording score, or nothing yet. */
  judged_by: 'model' | 'lexicon' | null
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
  /** The review signal: how often the local scorer and the model's final
   *  judgment read the same post differently. A strong contradiction marks
   *  an item worth reviewing (sentiment v2 §7.1). */
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
  /** Price per hour on the SAME grid as `series`; null is an hour nobody
   *  priced, and the chart-row's line breaks there rather than flat-lining
   *  through a stretch that was never quoted. */
  price_series: (number | null)[]
  /** The ticker's own normal chatter rate, mentions per hour, drawn as the
   *  dashed line the chart-row measures "above normal" against. null when
   *  the baseline is too thin to divide by -- phrasing.py's guard, decided
   *  server-side like `ratio`. */
  normal_per_hour: number | null
  /** Keyed by window length in hours, as a string: {"1": 3.1, "4": ...}. */
  triplet: Record<string, number | null>
  tone: Tone
  /** Why this row is on the list. The chart used to live here and moved to
   *  the panel: at the 3Y span it is ~780 numbers, and a twenty-row board
   *  would have carried sixteen thousand of them to draw twenty sparklines. */
  clauses: Clause[]
  /** False only on a watched row the floor would have dropped: the island
   *  renders it quiet and its warn clause says why. Absent on payloads
   *  embedded before 2026-09-02, which is the same as true. */
  eligible?: boolean
}

/** The exchange's state. It changes what the ranking MEANS, not merely how it
 *  is decorated: with the market shut there is no price movement to diverge
 *  from, so the board ranks on chatter alone. */
export type Session = 'premarket' | 'regular' | 'afterhours' | 'closed'

export interface BoardPayload {
  generated_at: string
  market: Market
  display_timezone: 'Europe/Berlin'
  /** Selected market context, stated once above its rows. */
  market_venue: string
  next_boundary_label: 'opens' | 'closes'
  /** Explicit UTC wire time for the selected market's next transition. */
  next_boundary_at: string
  sources: string[]
  all_sources: string[]
  /** What the board was filtered to. Empty means All. */
  segments: SegmentFilter[]
  session: Session
  /** 1 = any, 2 = only rows more than one venue is talking about. */
  min_venues: number
  /** Echoed so the island can seed its Selection from the server's own
   *  parsed answer rather than re-parsing the URL. null is unsorted. */
  sort: SortKey | null
  dir: 'asc' | 'desc'
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
  /** The caller's marks, oldest first, and one row per mark for the
   *  current selection -- whatever the floor said. Absent on older embeds. */
  watching?: string[]
  watch_rows?: Row[]
  /** What the model tone pass has cost. SPEND, never a balance -- the Claude
   *  API has no balance endpoint, so nothing here knows what is left. Absent
   *  until the first pass books something. */
  spend?: { today_usd: number; month_usd: number; unpriced_tokens: number }
  /** Judgment-pipeline health (sentiment v2 §10.4): pending backlog and its
   *  p95 post age, plus the review tier's unique-demand meters and the live
   *  over-ceiling gauge. Visibility, never control. */
  sentiment_ops?: {
    pending: number
    /** Unjudged mentions in the window the judge gate held back -- what
     *  was not spent. Absent on payloads embedded before the gate. */
    gated_pending?: number
    p95_age_minutes: number | null
    review: {
      demanded: number
      attempted: number
      served: number
      capped: number
      over_ceiling: number
    }
  }
}

/** The board's sort keys, in the order the header reads left to right. Same
 *  spelling as the query parameter and as board.SORT_KEYS on the server. */
export const SORT_KEYS = ['ticker', 'mentions', 'divergence', 'ratio',
                          'move', 'lean'] as const
export type SortKey = typeof SORT_KEYS[number]

export interface Selection {
  market: Market
  sources: string[]
  /** Server-side filter, unlike the chart span -- changing it refetches. */
  minVenues: number
  /** Several, and a union -- picking a second chip asks to see more. Empty
   *  is no filter, which is what the All chip sets. */
  segments: SegmentFilter[]
  window: number
  /** null is the default two-tier ranking. Server-side: changing it
   *  refetches, because it changes WHICH rows are on the board. */
  sort: SortKey | null
  dir: 'asc' | 'desc'
}

/** One universe match. Identity only: whether it is on the board, and its
 *  score, the island knows from the rows it holds. */
export interface SearchMatch {
  ticker: string
  name: string | null
  exchange: string | null
  segment: Segment
  watching: boolean
}

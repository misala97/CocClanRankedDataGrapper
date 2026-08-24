// Number and label formatting. Pure, and tested -- these are the functions
// that decide whether an unknown reads as unknown or as a zero.

/** The em-dash every unknown renders as. One constant so it cannot drift into
 *  a hyphen in one place and an en-dash in another. */
export const UNKNOWN = '—'

/** A signed divergence, or the phrase for a row that could not be scored.
 *
 *  Deliberately not `0.00`: a row with a frozen tape has no divergence at all,
 *  and zero is a real value meaning "chatter and price moved together". */
export function divergence(value: number | null): string {
  return value === null ? 'not scored' : signed(value, 2)
}

/** A price move as a percentage. `null` is unknown, never 0.00%. */
export function move(fraction: number | null): string {
  return fraction === null ? UNKNOWN : `${signed(fraction * 100, 2)}%`
}

export function signed(value: number, digits: number): string {
  // toFixed rounds -0.001 to "-0.00", which reads as a downward move that did
  // not happen. Normalising through +0 removes the sign from a rounded zero.
  const fixed = (value + 0).toFixed(digits)
  return Number(fixed) > 0 ? `+${fixed}` : fixed.replace('-0.00', '0.00')
}

/** A z-score for the triplet chips: one decimal, signed only when negative. */
export function zscore(value: number | null): string {
  return value === null ? UNKNOWN : value.toFixed(1)
}

const SEGMENT_LABELS: Record<string, string> = {
  all: 'All',
  small: 'Small',
  large: 'Large',
  mid: 'Mid',
  micro: 'Micro',
  unknown: 'Unknown',
  recent_ipo: 'Recent IPO',
}

/** Size order, with the two that are not sizes last. `small` leads because it
 *  is what the board opens on and what it is for; `all` sits beside it as the
 *  way back out. The three it covers stay listed -- Small is a shortcut to the
 *  common reading, not a replacement for reading them apart. */
export const SEGMENT_ORDER = ['small', 'all', 'large', 'mid', 'micro',
                              'recent_ipo', 'unknown']

export function segmentLabel(key: string): string {
  return SEGMENT_LABELS[key] ?? key
}

const SOURCE_LABELS: Record<string, string> = {
  stocktwits: 'StockTwits',
  bluesky: 'Bluesky',
  fourchan: '4chan /biz/',
}

/** A source name the config knows but this file does not still renders --
 *  adding a source must not require touching the UI (PRODUCT.md). */
export function sourceLabel(key: string): string {
  return SOURCE_LABELS[key] ?? key
}

/** Nasdaq's one-letter listing codes, as stored in radar_ticker_universe.
 *
 *  The panel printed the raw letter: `Q · large cap · $2.9T`. The tier is
 *  worth keeping rather than flattening all three Nasdaq codes to "Nasdaq" --
 *  Capital Market is the lowest listing standard and it is where most of what
 *  this board is for actually lists. Verified against the stored universe:
 *  F and GE are N, SPY and DIA are P, NVDA is Q, SOUN is G, HOWL is S. */
const EXCHANGE_LABELS: Record<string, string> = {
  Q: 'Nasdaq Global Select',
  G: 'Nasdaq Global',
  S: 'Nasdaq Capital Market',
  N: 'NYSE',
  P: 'NYSE Arca',
  A: 'NYSE American',
  Z: 'Cboe BZX',
  V: 'IEX',
}

export function exchangeLabel(code: string | null): string | null {
  if (!code) return null
  return EXCHANGE_LABELS[code] ?? code
}

export const MARK_WHY: Record<string, string> = {
  'no-print':
    'The tape has not printed for several polls, so the price looks unmoved ' +
    'because nothing traded. Any divergence here would be an artifact, so the ' +
    'row is not scored.',
  provisional:
    'Under 14 days of baseline history. The score is computed, but it is ' +
    'thinly supported and will move as history accumulates.',
  'single-source':
    'Only one of the selected sources contributed. The same reading from two ' +
    'independent sources is much stronger evidence.',
  partial:
    'A source was truncated during this window, so the count is real but ' +
    'incomplete. The true figure is higher.',
}

/** "22:14 UTC" -- the board's own clock, always UTC.
 *
 *  Not localised on purpose. Market sessions, the ingest cadence and every
 *  stored timestamp are UTC; rendering the stamp in Berlin time would be the
 *  one number on the page in a different frame from all the others. */
export function stampTime(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return UNKNOWN
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(at.getUTCHours())}:${pad(at.getUTCMinutes())} UTC`
}

export function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many
}


const SESSION_LABELS: Record<string, string> = {
  premarket: 'Pre-market',
  regular: 'Market open',
  afterhours: 'After hours',
  closed: 'Market closed',
}

export function sessionLabel(session: string): string {
  return SESSION_LABELS[session] ?? session
}

/** Whether a price is moving at all right now.
 *
 *  Divergence is chatter measured against price movement. With the exchange
 *  shut there is no movement to measure, so the score would silently collapse
 *  into "who is loudest" while still being labelled divergence. The board
 *  ranks on chatter instead and renames the column, rather than presenting the
 *  same heading over a different quantity.
 */
export function pricesAreMoving(session: string): boolean {
  return session !== 'closed'
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "22 Jul 2026" from a stored `YYYY-MM-DD`.
 *
 *  The ISO form is how the row travels and how it is compared; it is not how a
 *  date is read inside a sentence. `first ever seen on 2026-07-22` printed the
 *  storage format into prose. */
export function dayStamp(iso: string | null): string {
  if (!iso) return UNKNOWN
  const at = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(at.getTime())) return iso
  return `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()]} ${at.getUTCFullYear()}`
}

/** What the row says about the tape, under the ticker.
 *
 *  A shut exchange and a missing quote are different silences: the first says
 *  nothing about this stock and the second says the board does not know its
 *  price at all. Neither may render as a bare number pretending to be live. */
export function rowPrice(price: number | null, status: string): string {
  if (price === null) return 'no quote'
  const money = price >= 100 ? `$${price.toFixed(0)}` : `$${price.toFixed(2)}`
  if (status === 'closed') return `closed at ${money}`
  return money
}

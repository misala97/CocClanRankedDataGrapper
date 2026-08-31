// Number and label formatting. Pure, and tested -- these are the functions
// that decide whether an unknown reads as unknown or as a zero.

import type { Mark } from './types'

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
  discover: 'Discover',
  large: 'Large',
  mid: 'Mid',
  micro: 'Micro',
  unknown: 'Unknown',
  // "IPO", not "Recent IPO": the strip's eight tabs measured wider than the
  // pane with the long form, and recency is what the segment means anyway.
  recent_ipo: 'IPO',
  fund: 'Funds',
}

/** All first as the way out of any filter, then Discover as the default
 *  bundle, then the concrete sizes descending, then the three that are not
 *  sizes. The descending-cap scan is Michi's order, 2026-08-30; Discover
 *  moved out of the size run 2026-08-31 when Mid joined the bundle -- a
 *  group spanning mid..unknown has no slot inside a descending list. */
export const SEGMENT_ORDER = ['all', 'discover', 'large', 'mid', 'micro',
                              'recent_ipo', 'unknown', 'fund']

export function segmentLabel(key: string): string {
  return SEGMENT_LABELS[key] ?? key
}

const SOURCE_LABELS: Record<string, string> = {
  bluesky: 'Bluesky',
  fourchan: '4chan /biz/',
  reddit: 'Reddit',
}

/** A source name the config knows but this file does not still renders --
 *  adding a source must not require touching the UI (PRODUCT.md).
 *
 *  Rooted at the colon first. Since 2026-08-26 a stored Reddit source name
 *  carries its subreddit (`reddit:wallstreetbets`) so that one sub's feed
 *  rolling over marks its own buckets truncated rather than every other
 *  sub's. That is a decision about how STATUS and SCORING are partitioned,
 *  and it is not a decision to put subreddits on the surface -- so the label
 *  is the venue, `Reddit`, exactly as it was before the split. Showing
 *  `r/wallstreetbets` here would be its own product call, and one worth
 *  making deliberately rather than inheriting from a storage change. */
export function sourceLabel(key: string): string {
  const root = key.split(':')[0] ?? key
  // Falls through as the WHOLE key, not the root: an unknown source with a
  // suffix must render as itself rather than silently losing half its name.
  return SOURCE_LABELS[root] ?? key
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

// Typed over Mark rather than string, the way UNIVERSAL in ListPane is: a
// new mark must not be able to reach a row with no sentence explaining it.
export const MARK_WHY: Record<Mark, string> = {
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
  'warming-up':
    'Under a day of baseline history, because the extraction rules changed ' +
    'recently and older data no longer counts toward it. Not a new ticker -- ' +
    'every ticker on the board is warming up together.',
}

const BERLIN = 'Europe/Berlin'

/** A stored UTC instant in Radar's fixed display timezone.
 *
 * `de-DE` owns the local clock presentation. ICU uses the German spellings
 * MEZ/MESZ for its short zone names, while the product contract specifies the
 * internationally recognisable CET/CEST labels, so that part is obtained from
 * a second fixed-locale formatter over the same Berlin instant. Neither
 * formatter ever reads the browser's timezone. */
export function formatMarketTime(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return UNKNOWN
  const time = new Intl.DateTimeFormat('de-DE', {
    timeZone: BERLIN, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(at)
  const zone = new Intl.DateTimeFormat('en-GB', {
    timeZone: BERLIN, timeZoneName: 'short',
  }).formatToParts(at).find((part) => part.type === 'timeZoneName')?.value
  return zone ? `${time} ${zone}` : time
}

/** Compatibility name for consumers that render board timestamps. */
export const stampTime = formatMarketTime

/** A retained post needs a date as well as a clock.
 *
 * Posts stay on the panel for thirty days, so a bare `19:04` makes posts from
 * different days indistinguishable. Both date and clock use Berlin time. */
export function postStamp(iso: string): string {
  return `${formatMarketDate(iso)} · ${formatMarketTime(iso)}`
}

/** A stored UTC instant's calendar date in Radar's fixed display timezone. */
export function formatMarketDate(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return UNKNOWN
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: BERLIN, day: '2-digit', month: 'short', year: 'numeric',
  }).format(at)
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

/** What the board is ordered by, named and defined in one place.
 *
 *  The row prints this number and the glossary defines it, and the two must
 *  not be able to disagree about which quantity is on screen -- the label and
 *  the sentence come from here for both. Which of the two applies is a
 *  function of the session, because the RANKING is: with the exchange shut
 *  there is no price movement to diverge from and leaderboard.py falls
 *  through to chatter alone. */
export function rankTerm(session: string): { label: string; why: string } {
  return rankTermFor(pricesAreMoving(session) ? 'divergence' : 'chatter')
}

/** The server-serialized row term, used where an individual quote can no
 * longer score even though the board's market session is still open. */
export function rankTermFor(term: 'divergence' | 'chatter'):
    { label: string; why: string } {
  if (term === 'divergence') {
    return {
      label: 'div',
      why: 'Divergence: how far the chatter ran ahead of the price over this '
        + 'window. The board is ordered by it, highest first. A row with no '
        + 'usable quote is not scored at all rather than scored zero.',
    }
  }
  return {
    label: 'z',
    why: 'Chatter z-score: how unusual this much talk is for this ticker '
      + 'against its own history. With the market shut there is no price move '
      + 'to diverge from, so the board is ordered by this instead.',
  }
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

/** A dollar figure at the precision the figure deserves.
 *
 *  Two decimals is the reflex and it is wrong at both ends of this board. The
 *  micro segment is the point of the tool and a stock at $0.0031 rendered as
 *  `$0.00` is not a rounding, it is the assertion that the share is worthless
 *  -- so below a dollar the figure runs to four places. Above a hundred the
 *  cents are noise and the column reads better without them.
 *
 *  `scale` decides the format from a DIFFERENT number than the one being
 *  printed, so a pair of axis labels either side of one chart cannot come out
 *  as `$202` above `$46.33`. It defaults to the value itself.
 */
export function money(value: number, scale = value): string {
  if (scale >= 100) return `$${value.toFixed(0)}`
  if (scale >= 1) return `$${value.toFixed(2)}`
  return `$${value.toFixed(4)}`
}

/** A venue price in its provider-declared currency.
 *
 * `explicitCode` is for a US fallback inside Germany mode: a dollar glyph
 * alone is too easy to overlook next to German venue rows. */
export function formatPrice(value: number, currency: string,
                            { explicitCode = false }: { explicitCode?: boolean } = {}): string {
  const formatted = new Intl.NumberFormat('de-DE', {
    style: 'currency', currency,
  }).format(value)
  return explicitCode ? `${formatted} · ${currency}` : formatted
}

/** The exact delayed age, or the normal unknown marker where a provider did
 * not supply a timestamp. */
export function formatQuoteAge(ageSeconds: number | null): string {
  if (ageSeconds === null) return UNKNOWN
  return `${Math.floor(ageSeconds / 60)} min delayed`
}

/** An age in the unit a person would pick: 45 min, 46h, 3d.
 *
 *  Replaces the raw minute count the row badges used to print -- "2740 min
 *  stale" is a subtraction the reader has to finish themselves. */
export function humanAge(ageSeconds: number | null): string {
  if (ageSeconds === null) return UNKNOWN
  const minutes = Math.floor(ageSeconds / 60)
  if (minutes < 90) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

/** The ratio as the chart-row's short figure: `4.5×`, `40×`.
 *
 *  Same rounding rules as phrasing.py's `_ratio` -- a tenth matters at 3.5
 *  and is noise at 40 -- but formatting only: whether a row HAS a ratio was
 *  already decided by the server (`ratio` is null past the guard). */
export function ratioShort(value: number | null): string | null {
  if (value === null) return null
  if (value >= 10) return `${Math.round(value)}×`
  return `${value.toFixed(1)}×`.replace('.0×', '×')
}

/** What the row says about the tape, under the ticker.
 *
 *  A shut exchange and a missing quote are different silences: the first says
 *  nothing about this stock and the second says the board does not know its
 *  price at all. Neither may render as a bare number pretending to be live.
 *
 *  Zero is a third silence wearing the first one's clothes. No listed share
 *  prints at $0.00; the quote is absent and the field arrived as a zero
 *  because something upstream defaulted it. Printed as money it is the most
 *  confident wrong number on the row.
 */
export function rowPrice(price: number | null, status: string): string {
  if (price === null || price <= 0) return 'no quote'
  if (status === 'closed') return `closed at ${money(price)}`
  return money(price)
}

/** Counts, grouped. `1284392` is four glances; `1,284,392` is one.
 *
 *  Pinned to en-US rather than the reader's locale for the same reason the
 *  clock is pinned to UTC: every other figure on the surface is formatted by
 *  this app, and one number switching to `1.284.392` under a German locale
 *  would be the only one in a different convention. */
export function count(value: number): string {
  return value.toLocaleString('en-US')
}

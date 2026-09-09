// Reordering the candidates that are already on screen.
//
// This is a VIEW operation and nothing else. It does not fetch, it does not
// touch the server's sort parameters, and it does not widen the candidate set:
// the board decided which companies are eligible and how many to send, and
// this only decides the order the reader looks at them in. That distinction is
// stated on the page as well as here, because "sorted by tone" reads awfully
// like "the most bullish companies in the market" and it is not that.
//
// Every key reads the SAME value the cell displays, through the same
// validation. Sorting on a formatted string would order 10% before 2%, and
// sorting on the bar's geometry would order by the 2px minimum that exists so
// a rare share stays visible -- both would rank rows by an artifact of how
// they are drawn rather than by what was measured.
import { sourcePresentation, tonePresentation } from './chatterPresentation'
import type { Row } from '../types'

export type SortKey =
  'company' | 'attention' | 'voices' | 'sources' | 'tone' | 'price' | 'move'

export type SortDirection = 'asc' | 'desc'

export interface ChatterSort {
  key: SortKey
  dir: SortDirection
}

/** What each column is called where a sentence needs it. */
export const SORT_LABELS: Record<SortKey, string> = {
  company: 'Company',
  attention: 'Attention',
  voices: 'Voices',
  sources: 'Sources',
  tone: 'Tone',
  price: 'Price',
  move: 'Today',
}

/** The direction a column opens in. Names go A-Z; every figure opens with its
 *  largest value, because a reader who clicks "Attention" wants the loudest
 *  company, not the quietest. */
export function firstDirection(key: SortKey): SortDirection {
  return key === 'company' ? 'asc' : 'desc'
}

/** Clicking the active column flips it; clicking another opens that one. */
export function nextSort(current: ChatterSort | null, key: SortKey): ChatterSort {
  if (current && current.key === key) {
    return { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
  }
  return { key, dir: firstDirection(key) }
}

/** A row's value under one key.
 *
 *  `null` means UNKNOWN -- not zero, and not "smallest". Unknown rows sort to
 *  the end in both directions, because a company whose price nobody has is not
 *  the cheapest company, and reversing the sort must not promote it to the
 *  top. `group` exists for price alone: see `priceOf`. */
interface Value {
  group: string | null
  value: number | string | null
}

const UNKNOWN: Value = { group: null, value: null }

function numberOf(value: unknown): Value {
  return typeof value === 'number' && Number.isFinite(value)
    ? { group: null, value }
    : UNKNOWN
}

/** The price a row DISPLAYS, with the currency it is displayed in.
 *
 *  Grouped rather than compared across currencies: €4.44 is not "less than"
 *  $18.20 in any sense a reader would accept, and this board has no conversion
 *  to make it one. A German fallback row therefore sorts among the other euro
 *  rows, and the page says so when it happens. A quote with no currency at all
 *  cannot be placed in a group, so it is unknown. */
function priceOf(row: Row): Value {
  const quote = row.quote
  if (!quote || quote.quality === 'unavailable') return UNKNOWN
  if (typeof row.price !== 'number' || !Number.isFinite(row.price)) return UNKNOWN
  if (typeof quote.currency !== 'string' || !quote.currency) return UNKNOWN
  return { group: quote.currency, value: row.price }
}

function valueOf(row: Row, key: SortKey): Value {
  switch (key) {
    case 'company':
      // The ticker, not the company name: the name is clamped to one line on
      // the desk layout, and sorting by text the reader cannot fully see is
      // sorting by something invisible.
      return typeof row.ticker === 'string' && row.ticker
        ? { group: null, value: row.ticker }
        : UNKNOWN
    case 'attention':
      // phrasing.py's guard, never recomputed here. A row with no baseline
      // worth dividing by has no ratio, and inventing mentions/expected for it
      // would be a second opinion about when a baseline is thick enough.
      return numberOf(row.ratio)
    case 'voices':
      return numberOf(row.authors)
    case 'sources': {
      // Platforms, matching the cell. Missing field is unknown; an empty
      // measured list is a real zero and sorts as one.
      const sources = sourcePresentation(row.activity_sources)
      if (sources.kind === 'unavailable') return UNKNOWN
      return { group: null, value: sources.platforms.length }
    }
    case 'tone': {
      // The unrounded bullish share of the DIRECTIONAL sample -- the same
      // number the bar is drawn from, before the minimum-width floor. No
      // directional sample is unknown, never 0% bullish.
      const tone = tonePresentation(row.tone)
      return tone.kind === 'directional' ? numberOf(tone.bull) : UNKNOWN
    }
    case 'price':
      return priceOf(row)
    case 'move':
      // Zero is a measurement: the price did not move. Only a missing move,
      // or a quote too broken to show one, is unknown.
      return priceOf(row).value === null ? UNKNOWN : numberOf(row.price_move)
  }
}

const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: 'base',
})

function compareKnown(a: Value, b: Value): number {
  if (a.group !== b.group) {
    return collator.compare(a.group ?? '', b.group ?? '')
  }
  if (typeof a.value === 'string' || typeof b.value === 'string') {
    return collator.compare(String(a.value), String(b.value))
  }
  return (a.value as number) - (b.value as number)
}

/** The rows in the reader's order.
 *
 *  Pure and stable: a copy is sorted, `rows` itself is never touched, and rows
 *  that tie keep the order the server sent them in -- so a sort is a reordering
 *  of Radar's ranking, not a replacement for it. `null` is Radar order, and
 *  returns the response exactly as it arrived. */
export function sortRows(rows: Row[], sort: ChatterSort | null): Row[] {
  if (!sort) return rows
  const decorated = rows.map((row, index) => ({
    row,
    index,
    key: valueOf(row, sort.key),
  }))
  const flip = sort.dir === 'desc' ? -1 : 1
  decorated.sort((a, b) => {
    const aKnown = a.key.value !== null
    const bKnown = b.key.value !== null
    // Last in BOTH directions. Reversing the sort must not float the rows
    // nobody measured to the top of the page.
    if (!aKnown || !bKnown) {
      if (aKnown === bKnown) return a.index - b.index
      return aKnown ? -1 : 1
    }
    const base = compareKnown(a.key, b.key)
    // The index tiebreak is explicit rather than relying on the engine's sort
    // being stable, because "equal keys keep the response order" is a promise
    // this module makes and not one it borrows.
    return base !== 0 ? base * flip : a.index - b.index
  })
  return decorated.map((entry) => entry.row)
}

/** The currencies actually present among the rows that HAVE a usable price.
 *
 *  More than one means the price sort groups, and the page has to say so
 *  rather than letting a reader assume the column is one ranked list. */
export function priceCurrencies(rows: Row[]): string[] {
  const seen = new Set<string>()
  for (const row of rows) {
    const price = priceOf(row)
    if (price.group) seen.add(price.group)
  }
  return Array.from(seen).sort()
}

/** How many of the loaded rows this key could actually order. The rest are
 *  parked at the end, and a reader deserves to know that before wondering why
 *  the bottom of the list looks unsorted. */
export function knownCount(rows: Row[], key: SortKey): number {
  return rows.filter((row) => valueOf(row, key).value !== null).length
}

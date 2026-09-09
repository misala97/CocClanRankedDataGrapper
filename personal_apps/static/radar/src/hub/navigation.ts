// The hub's URL contract.
//
// One page, several destinations, and the address bar is the source of truth
// for all of them: the hash says where the reader is, the query says what they
// have filtered to, and Back restores both. That is why the route is read from
// the URL rather than held only in state -- a hub that forgets its list when
// you return from a company is the lost-place complaint the old board's `?t=`
// parameter already had to fix once.
//
// Everything here is total. A hash nobody implemented, a ticker with a broken
// percent escape, a bookmarked filter naming a source that has since been
// retired: each resolves to something renderable. A throw in this module is a
// blank page, which is the one outcome worse than a wrong page.
import { queryFor } from '../api'
import { SORT_KEYS } from '../types'
import type { Market, PanelSpan, SegmentFilter, Selection, SortKey } from '../types'

export type HubRoute =
  | { page: 'overview' | 'chatter' | 'watching' | 'activity' | 'admin' }
  | { page: 'research'; ticker: string }
  | { page: 'missing' }

/** Only what this release actually renders. News, Combined, Portfolio and
 *  Analysis stay in the prototype and the roadmap; a bookmark to one is a dead
 *  link the recovery view can explain, not an empty destination in the nav. */
const PAGES = ['overview', 'chatter', 'watching', 'activity', 'admin'] as const

const SPANS: PanelSpan[] = ['1D', '1W', '1M', '6M', '1Y', '3Y']

/** The client half of the server's vocabulary. Mirrors SegmentFilter, which
 *  the type system already pins; a value outside it would be rejected by
 *  parse_query with a 400 the reader could not escape by clicking. */
const SEGMENTS: SegmentFilter[] = ['large', 'mid', 'micro', 'unknown',
                                   'recent_ipo', 'fund', 'discover']

export function readRoute(hash: string): HubRoute {
  const raw = hash.replace(/^#/, '')
  if (raw === '') return { page: 'overview' }
  const [name = '', ...rest] = raw.split('/')
  if ((PAGES as readonly string[]).includes(name) && rest.length === 0) {
    return { page: name as Exclude<HubRoute['page'], 'research' | 'missing'> }
  }
  if (name === 'research') {
    const ticker = decode(rest.join('/'))
    if (!ticker) return { page: 'missing' }
    return { page: 'research', ticker: ticker.toUpperCase() }
  }
  return { page: 'missing' }
}

/** decodeURIComponent throws on a lone `%`. A bookmark that lost a character
 *  in a chat client is a missing page, never an exception. */
function decode(value: string): string | null {
  if (!value) return null
  try {
    const decoded = decodeURIComponent(value)
    return decoded.trim() === '' ? null : decoded
  } catch {
    return null
  }
}

export function hashFor(route: HubRoute): string {
  if (route.page === 'missing') return '#missing'
  if (route.page === 'research') {
    return `#research/${encodeURIComponent(route.ticker).replace(/%2E/gi, '.')}`
  }
  return `#${route.page}`
}

/** The reader's filters, read back from the query.
 *
 *  `fallback` is the board the server already parsed and echoed, so an absent
 *  or unusable parameter resolves to the server's own answer rather than to a
 *  default invented here. `offered` is the source vocabulary the payload
 *  reported; a stale bookmark naming a retired source loses that source
 *  instead of turning into a 400.
 */
export function readSelection(search: string, fallback: Selection,
                              offered?: string[]): Selection {
  const params = new URLSearchParams(search.replace(/^\?/, ''))
  return {
    market: pick<Market>(params.get('market'), ['us', 'de'], fallback.market),
    sources: readSources(params, fallback, offered),
    // Present-but-empty is All, which is a real selection and not a missing
    // one. Only an absent parameter falls back.
    segments: params.has('segment')
      ? (params.get('segment') as string).split(',').map((s) => s.trim())
          .filter((s): s is SegmentFilter => (SEGMENTS as string[]).includes(s))
      : fallback.segments,
    minVenues: pick(numeric(params.get('venues')), [1, 2], fallback.minVenues),
    window: pick(numeric(params.get('window')), [1, 4, 12, 24], fallback.window),
    sort: params.has('sort')
      ? pick<SortKey | null>(params.get('sort'),
                             SORT_KEYS as unknown as (SortKey | null)[],
                             fallback.sort)
      : fallback.sort,
    dir: pick<'asc' | 'desc'>(params.get('dir'), ['asc', 'desc'], fallback.dir),
  }
}

function readSources(params: URLSearchParams, fallback: Selection,
                     offered?: string[]): string[] {
  const raw = params.get('sources')
  if (!raw) return fallback.sources
  const named = raw.split(',').map((s) => s.trim()).filter(Boolean)
  // A prefixed name is valid when its ROOT is offered: the chips are per root
  // and a link may name one subreddit, which is narrower and must stay so.
  const known = offered
    ? named.filter((name) => offered.includes(name.split(':')[0] ?? name))
    : named
  return known.length ? known : fallback.sources
}

function numeric(value: string | null): number | null {
  if (value === null || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : null
}

function pick<T>(value: unknown, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly unknown[]).includes(value) ? value as T : fallback
}

export function readSpan(search: string): PanelSpan {
  const raw = new URLSearchParams(search.replace(/^\?/, '')).get('span')
  return SPANS.includes(raw as PanelSpan) ? raw as PanelSpan : '1D'
}

/** The whole address for a state: filters in the query, destination in the
 *  hash. The span rides along only where there is a chart it describes. */
export function urlFor(route: HubRoute, selection: Selection,
                       span: PanelSpan): string {
  const params = new URLSearchParams(queryFor(selection))
  if (route.page === 'research') params.set('span', span)
  return `?${params.toString()}${hashFor(route)}`
}

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

/** The client half of the server's vocabulary, and it has to be the WHOLE of
 *  it. `small` is the pre-2026-08-25 spelling of the discover group and
 *  features/radar/routes/api.py still accepts it, so dropping it here would
 *  leave a live bookmark rendering a Discover board while the controls said
 *  All -- the surface disagreeing with the server about a URL that works. */
const SEGMENTS: string[] = ['large', 'mid', 'micro', 'unknown', 'recent_ipo',
                            'fund', 'discover', 'small']

/** Values queryFor omits at their default (api.ts), which is what makes their
 *  absence from a URL mean "the default" rather than "unspecified". */
const DEFAULT_VENUES = 1
const DEFAULT_DIR = 'desc' as const

/** api.py's MAX_SOURCES: every root plus every configured subreddit. A longer
 *  list is refused there with a 400, which reaches the reader as an
 *  unexplained network error. */
const MAX_SOURCES = 64

export function readRoute(hash: string): HubRoute {
  const raw = hash.replace(/^#/, '')
  if (raw === '') return { page: 'overview' }
  const [rawName = '', ...rest] = raw.split('/')
  const name = rawName.toLowerCase()
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
    // A ticker with a slash survives the round trip because readRoute rejoins
    // everything after the first segment; encodeURIComponent leaves `.` alone,
    // so BRK.B needs nothing special.
    return `#research/${encodeURIComponent(route.ticker)}`
  }
  return `#${route.page}`
}

/** Whether a fragment is an in-page anchor rather than a destination.
 *
 *  The document uses fragments for both, and the skip link is the first
 *  control a keyboard reader meets: `#rh-main` is an element id, and treating
 *  it as a route name replaced the page with "there is nothing at this
 *  address". Any anchor added later -- a chart, a posts section, a details
 *  deep link -- would have done the same.
 */
export function isInPageAnchor(hash: string, doc: Document = document): boolean {
  const raw = hash.replace(/^#/, '')
  if (!raw) return false
  try {
    return doc.getElementById(raw) !== null
  } catch {
    return false
  }
}

/** The reader's filters, read back from the query. The inverse of `queryFor`.
 *
 *  That inverse property is load-bearing. `queryFor` omits `venues` at 1 and
 *  omits `sort`/`dir` when there is no sort, so their ABSENCE means the
 *  default -- not "unspecified, use whatever the page opened with". Resolving
 *  them to the opening echo instead made the same URL render one board for a
 *  reader who had navigated to it and a different one for anyone opening it
 *  fresh.
 *
 *  `fallback` is the board the server already parsed and echoed, and it stands
 *  in only for the parameters `queryFor` always writes -- so it applies on a
 *  bare `/radar/hub/` with no query at all, and to a value the server would
 *  refuse.
 *
 *  `offered` is the source vocabulary the payload reported; a stale bookmark
 *  naming a retired source loses that source instead of turning into a 400.
 */
export function readSelection(search: string, fallback: Selection,
                              offered?: string[]): Selection {
  const params = new URLSearchParams(search.replace(/^\?/, ''))
  const sort = params.has('sort')
    ? pick<SortKey | null>(params.get('sort'),
                           SORT_KEYS as unknown as (SortKey | null)[], null)
    : null
  return {
    market: pick<Market>(params.get('market'), ['us', 'de'], fallback.market),
    sources: readSources(params, fallback, offered),
    segments: readSegments(params, fallback),
    minVenues: params.has('venues')
      ? pick(numeric(params.get('venues')), [1, 2], DEFAULT_VENUES)
      : DEFAULT_VENUES,
    window: pick(numeric(params.get('window')), [1, 4, 12, 24], fallback.window),
    sort,
    // Direction without a sort is inert on the server, and queryFor writes the
    // pair together or not at all.
    dir: sort === null
      ? DEFAULT_DIR
      : pick<'asc' | 'desc'>(params.get('dir'), ['asc', 'desc'], DEFAULT_DIR),
  }
}

function readSegments(params: URLSearchParams, fallback: Selection): SegmentFilter[] {
  const raw = params.get('segment')
  // Present-but-empty is All, which is a real selection and not a missing one.
  if (raw === null) return fallback.segments
  if (raw === '') return []
  const named = raw.split(',').map((name) => name.trim()).filter(Boolean)
  const known = named.filter((name) => SEGMENTS.includes(name))
  // Entirely unrecognisable is a garbled bookmark, not a request for All --
  // widening the board there would show more than the reader asked for.
  return (known.length ? known : fallback.segments) as SegmentFilter[]
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
  // Deduplicated, so `?sources=bluesky,bluesky` is one cache entry and one
  // request; bounded, because a longer list is a 400 the reader would meet as
  // an unexplained network error.
  const unique = Array.from(new Set(known)).slice(0, MAX_SOURCES)
  return unique.length ? unique : fallback.sources
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

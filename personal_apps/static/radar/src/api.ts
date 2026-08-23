import type { BoardPayload, Detail, PanelSpan, Selection } from './types'

// `Accept: application/json` is explicit and not optional. A bare fetch() sends
// `*/*`, a wildcard accepts HTML, and the login redirect this route sits behind
// answers HTML -- so without the header an expired session comes back as a
// login page parsed as JSON, which fails somewhere far away from the cause.
const HEADERS = { Accept: 'application/json' }

/** Well past a slow round trip, well short of the point where the reader
 *  concludes the page is broken and reloads it. */
const TIMEOUT_MS = 8000

export class BoardUnavailable extends Error {
  constructor(readonly reason: 'timeout' | 'network' | 'session') {
    super(reason)
  }

  get message(): string {
    if (this.reason === 'session') return 'Session expired — reload to sign in again.'
    return this.reason === 'timeout'
      ? 'The board did not answer in time.'
      : 'Could not reach the board.'
  }
}

export function queryFor(selection: Selection): string {
  const params = new URLSearchParams()
  params.set('sources', selection.sources.join(','))
  params.set('window', String(selection.window))
  // Always sent, empty for All. Omitting it would hand the server its own
  // default, which is Small -- so the All chip would silently do nothing.
  params.set('segment', selection.segment ?? '')
  // Omitted at 1 so the default board keeps a clean URL.
  if (selection.minVenues > 1) params.set('venues', String(selection.minVenues))
  return params.toString()
}

/** One GET behind the timeout, the abort plumbing and the session check.
 *
 *  Shared because the login redirect is the subtle part: the routes sit behind
 *  @login_required, which redirects rather than 401s, and fetch follows that
 *  transparently -- so an expired session arrives as a 200 full of HTML. Two
 *  copies of that check is one copy that eventually goes missing. */
async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  signal?.addEventListener('abort', () => controller.abort(), { once: true })

  try {
    const response = await fetch(url, {
      headers: HEADERS, credentials: 'same-origin', signal: controller.signal,
    })
    if (response.redirected) throw new BoardUnavailable('session')
    if (!response.ok) throw new BoardUnavailable('network')
    return await response.json() as T
  } catch (error) {
    if (error instanceof BoardUnavailable) throw error
    throw new BoardUnavailable(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchBoard(
  selection: Selection, signal?: AbortSignal,
): Promise<BoardPayload> {
  return getJson<BoardPayload>(
    `/radar/api/board?${queryFor(selection)}`, signal)
}

/** One ticker's panel.
 *
 *  Its own request rather than a field on the board payload: at the 3Y span
 *  the chart is ~780 closes, so carrying it per row would have a twenty-row
 *  board ship sixteen thousand numbers to draw twenty sparklines.
 *
 *  Carries the source and window selection, because the breakdown and the
 *  posts describe the same window the row's phrase does -- a panel scoped
 *  differently from the row that opened it would quietly disagree with it. */
export async function fetchDetail(
  ticker: string, selection: Selection, span: PanelSpan,
  signal?: AbortSignal,
): Promise<Detail> {
  const params = new URLSearchParams()
  params.set('sources', selection.sources.join(','))
  params.set('window', String(selection.window))
  params.set('span', span)
  return getJson<Detail>(
    `/radar/api/ticker/${encodeURIComponent(ticker)}?${params}`, signal)
}

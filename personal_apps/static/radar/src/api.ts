import type { BoardPayload, Detail, PanelSpan, Selection } from './types'

// `Accept: application/json` is explicit and not optional. A bare fetch() sends
// `*/*`, a wildcard accepts HTML, and the login redirect this route sits behind
// answers HTML -- so without the header an expired session comes back as a
// login page parsed as JSON, which fails somewhere far away from the cause.
const HEADERS = { Accept: 'application/json' }

/** Well past a slow round trip, well short of the point where the reader
 *  concludes the page is broken and reloads it. */
const TIMEOUT_MS = 8000

/** One sentence per way this can fail, and they are deliberately different
 *  sentences.
 *
 *  Everything that was not a redirect or a timeout used to collapse into
 *  "Could not reach the board", which was read as an offline browser in three
 *  situations that are nothing of the kind. The one that mattered: a
 *  bookmarked `?t=` for a ticker that has since dropped off the board answers
 *  404, and the reader was told their connection was down. */
const REASON_TEXT = {
  session: 'Session expired — reload to sign in again.',
  timeout: 'The board did not answer in time.',
  network: 'Could not reach the board.',
  missing: 'Nothing here for that ticker.',
  server: 'The board answered with an error.',
  busy: 'The board is rate-limiting requests. Give it a moment.',
} as const

export class BoardUnavailable extends Error {
  // The text is passed to super rather than exposed through a getter.
  // `super(reason)` sets `message` as an OWN property, and an own data
  // property shadows a prototype accessor -- so a `get message()` here never
  // ran, and the banner showed readers the bare word "network" instead of a
  // sentence. Found by a test written for the two-pane rebuild; it had been
  // that way since the error path was added.
  constructor(readonly reason: keyof typeof REASON_TEXT) {
    super(REASON_TEXT[reason])
  }
}

export function queryFor(selection: Selection): string {
  const params = new URLSearchParams()
  params.set('sources', selection.sources.join(','))
  params.set('window', String(selection.window))
  // Always sent, empty for All. Omitting it would hand the server its own
  // default, which is Discover -- so the All chip would silently do nothing.
  // Comma-separated; empty is how the surface asks for All.
  params.set('segment', selection.segments.join(','))
  // Always explicit. An omitted market is US for old links, but a selected
  // market must travel through every request and cache boundary.
  params.set('market', selection.market)
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
  // Checked before the listener is attached: a signal that was ALREADY
  // aborted never fires the event, so the request went out anyway and the
  // caller's cancellation did nothing.
  if (signal?.aborted) controller.abort()
  const relay = () => controller.abort()
  signal?.addEventListener('abort', relay, { once: true })

  try {
    const response = await fetch(url, {
      headers: HEADERS, credentials: 'same-origin', signal: controller.signal,
    })
    if (response.redirected) throw new BoardUnavailable('session')
    if (!response.ok) throw new BoardUnavailable(statusReason(response.status))
    return await response.json() as T
  } catch (error) {
    if (error instanceof BoardUnavailable) throw error
    throw new BoardUnavailable(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', relay)
  }
}

/** Which sentence a status code earns.
 *
 *  401 and 403 join `session` rather than getting a permission line of their
 *  own: the routes are behind @login_required, everyone who can open the page
 *  can read every row, and the only way to see one is a session that stopped
 *  being valid. Reloading is the fix in all three cases. */
function statusReason(status: number): keyof typeof REASON_TEXT {
  if (status === 401 || status === 403) return 'session'
  if (status === 404) return 'missing'
  if (status === 429) return 'busy'
  if (status >= 500) return 'server'
  return 'network'
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
  params.set('market', selection.market)
  return getJson<Detail>(
    `/radar/api/ticker/${encodeURIComponent(ticker)}?${params}`, signal)
}

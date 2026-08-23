import type { BoardPayload, Selection } from './types'

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
  if (selection.segment) params.set('segment', selection.segment)
  // Omitted at 1 so the default board keeps a clean URL.
  if (selection.minVenues > 1) params.set('venues', String(selection.minVenues))
  return params.toString()
}

export async function fetchBoard(
  selection: Selection, signal?: AbortSignal,
): Promise<BoardPayload> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  signal?.addEventListener('abort', () => controller.abort(), { once: true })

  try {
    const response = await fetch(`/radar/api/board?${queryFor(selection)}`, {
      headers: HEADERS, credentials: 'same-origin', signal: controller.signal,
    })
    // The route is behind @login_required, which redirects rather than 401s.
    // fetch follows that transparently, so an expired session arrives as a
    // 200 full of HTML; the redirect is the only thing that gives it away.
    if (response.redirected) throw new BoardUnavailable('session')
    if (!response.ok) throw new BoardUnavailable('network')
    return await response.json() as BoardPayload
  } catch (error) {
    if (error instanceof BoardUnavailable) throw error
    throw new BoardUnavailable(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
  }
}

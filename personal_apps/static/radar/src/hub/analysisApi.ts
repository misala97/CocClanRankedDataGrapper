// The two Analysis requests (HA1), behind the same timeout, abort and
// session checks as api.ts -- and with their own error type, because the
// server answers these with a stable `code` the page can act on (409 is an
// identity that changed, 422 an instrument this slice cannot show), and the
// board's vocabulary has no words for either.
import type { AnalysisPayload, Range, ResolvePayload } from './analysisTypes'

const HEADERS = { Accept: 'application/json' }

/** Same figure as the board's: well past a slow round trip, well short of
 *  the point where the reader concludes the page is broken. */
export const TIMEOUT_MS = 8000

export type AnalysisReason =
  | 'session' | 'timeout' | 'network' | 'missing' | 'conflict' | 'unsupported'
  | 'invalid' | 'limit' | 'unavailable' | 'forbidden' | 'server'

const REASON_TEXT: Record<AnalysisReason, string> = {
  session: 'Session expired — reload to sign in again.',
  timeout: 'The analysis did not answer in time.',
  network: 'Could not reach the analysis.',
  missing: 'No current company or instrument for that link.',
  conflict: 'The current mapping no longer matches this link.',
  unsupported: 'No native-USD US primary instrument can be shown for this company.',
  invalid: 'The request was not valid.',
  limit: 'The read exceeded its bounds.',
  unavailable: 'The store could not be read.',
  forbidden: 'This account is not allowed to read that.',
  server: 'The analysis answered with an error.',
}

export class AnalysisUnavailable extends Error {
  constructor(readonly reason: AnalysisReason, readonly code: string | null = null,
              detail: string | null = null) {
    super(detail && reason !== 'session' ? detail : REASON_TEXT[reason])
  }
}

function reasonFor(status: number, code: string | null): AnalysisReason {
  if (status === 401) return 'session'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'missing'
  if (status === 409) return 'conflict'
  if (status === 422) return 'unsupported'
  if (status === 400) return 'invalid'
  if (status === 503) return code === 'analysis_limit' ? 'limit' : 'unavailable'
  if (status >= 500) return 'server'
  return 'network'
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  if (signal?.aborted) controller.abort()
  const relay = () => controller.abort()
  signal?.addEventListener('abort', relay, { once: true })
  try {
    const response = await fetch(url, {
      headers: HEADERS, credentials: 'same-origin', signal: controller.signal,
    })
    // @login_required redirects to the login page rather than answering 401,
    // and fetch follows it: an expired session arrives as 200 full of HTML.
    if (response.redirected) throw new AnalysisUnavailable('session')
    const type = response.headers.get('content-type') ?? ''
    if (!type.includes('application/json')) {
      throw new AnalysisUnavailable(response.ok ? 'session' : reasonFor(response.status, null))
    }
    if (!response.ok) {
      let code: string | null = null
      let detail: string | null = null
      try {
        const body = await response.json() as { code?: unknown; error?: unknown }
        code = typeof body.code === 'string' ? body.code : null
        detail = typeof body.error === 'string' ? body.error : null
      } catch {
        // A refused request with an unreadable body is still refused.
      }
      throw new AnalysisUnavailable(reasonFor(response.status, code), code, detail)
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof AnalysisUnavailable) throw error
    throw new AnalysisUnavailable(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', relay)
  }
}

/** The current company and its eligible US primary for a symbol. */
export function fetchAnalysisResolve(ticker: string, signal?: AbortSignal): Promise<ResolvePayload> {
  return getJson<ResolvePayload>(
    `/radar/api/analysis/resolve?ticker=${encodeURIComponent(ticker)}`, signal)
}

/** The daily series for a pinned identity and an explicit window. Never
 *  sends board filters; never sends a guessed range. */
export function fetchAnalysis(companyId: number, instrumentId: number, range: Range,
                              signal?: AbortSignal): Promise<AnalysisPayload> {
  const params = new URLSearchParams()
  params.set('instrument_id', String(instrumentId))
  params.set('from', range.from)
  params.set('to', range.to)
  return getJson<AnalysisPayload>(
    `/radar/api/analysis/company/${companyId}?${params.toString()}`, signal)
}

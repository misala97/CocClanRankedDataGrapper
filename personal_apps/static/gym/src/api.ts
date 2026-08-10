// The one HTTP core every island shares.
//
// `Accept: application/json` is not optional and not a nicety. The routes
// negotiate: a browser form post sends text/html followed by a wildcard, and a
// bare fetch() sends the wildcard alone -- and a wildcard accepts HTML, so
// neither of them gets JSON. Only this explicit header distinguishes an
// island, and without it every mutation would answer with a 302 the client
// cannot use. Pinned server-side by test_a_bare_fetch_does_not_get_json.

const JSON_HEADERS = { Accept: 'application/json' }

/**
 * A request that never resolves is the worst failure mode: the screen says
 * "working" for as long as you look at it. Eight seconds is well past a slow
 * gym-wifi round trip and well short of the point where you would put the
 * phone down.
 */
const TIMEOUT_MS = 8000

export class MutationFailed extends Error {
  constructor(readonly reason: 'timeout' | 'network') {
    super(reason)
  }

  /** The message the banner shows. German, because the banner is German. */
  get germanMessage(): string {
    return this.reason === 'timeout'
      ? 'Keine Antwort vom Server — deine letzte Änderung wurde nicht gespeichert.'
      : 'Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.'
  }
}

/** POST form fields, get the page's fresh payload back. The caller names the
 *  payload type it is owed -- which page answers is the server's decision
 *  (_mutation_response branches on finished_at). */
export function postForm<T>(
  url: string, fields: Record<string, string | number | boolean> = {},
  opts: { keepalive?: boolean } = {},
): Promise<T> {
  const body = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    body.append(key, String(value))
  }
  return postFormData<T>(url, body, opts)
}

/** Same, from a real form's FormData -- the only shape that keeps a
 *  multi-select's repeated keys (request.form.getlist on the other side). */
export async function postFormData<T>(
  url: string, body: FormData, opts: { keepalive?: boolean } = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      method: 'POST', body, headers: JSON_HEADERS,
      credentials: 'same-origin', signal: controller.signal,
      // The pagehide flush posts a write the page will not stay alive to see
      // answered; keepalive lets the request outlive the document.
      keepalive: opts.keepalive ?? false,
    })
    if (!response.ok) throw new MutationFailed('network')
    return await response.json() as T
  } catch (error) {
    if (error instanceof MutationFailed) throw error
    throw new MutationFailed(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
  }
}

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: JSON_HEADERS, credentials: 'same-origin',
  })
  if (!response.ok) throw new MutationFailed('network')
  return await response.json() as T
}

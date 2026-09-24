// The one HTTP core every island shares.
//
// `Accept: application/json` is not optional and not a nicety. The routes
// negotiate: a browser form post sends text/html followed by a wildcard, and a
// bare fetch() sends the wildcard alone -- and a wildcard accepts HTML, so
// neither of them gets JSON. Only this explicit header distinguishes an
// island, and without it every mutation would answer with a 302 the client
// cannot use. Pinned server-side by test_a_bare_fetch_does_not_get_json.

import { csrfToken } from './csrf'

const JSON_HEADERS = { Accept: 'application/json' }

/** Every write carries the session's CSRF token -- the fetch twin of the
 *  hidden field native forms embed. Built per request: the token is read
 *  lazily from the shell's meta tag. */
const writeHeaders = () => ({ ...JSON_HEADERS, 'X-CSRF-Token': csrfToken() })

/**
 * A request that never resolves is the worst failure mode: the screen says
 * "working" for as long as you look at it. Eight seconds is well past a slow
 * gym-wifi round trip and well short of the point where you would put the
 * phone down.
 */
const TIMEOUT_MS = 8000

export type FailureReason =
  'timeout' | 'network' | 'forbidden' | 'finished' | 'unauthorized' | 'invalid'

export class MutationFailed extends Error {
  /** `serverMessage`: for 'invalid', the server's own sentence saying what it
   *  refused (routes/helpers.py InvalidInput). */
  constructor(readonly reason: FailureReason, readonly serverMessage?: string) {
    super(reason)
  }

  /** The message the banner shows. German, because the banner is German. */
  get germanMessage(): string {
    // 'forbidden' is its own message: a CSRF token gone stale after a
    // long-idle PWA session used to read as "Verbindung fehlgeschlagen" with
    // a retry that could never succeed.
    if (this.reason === 'forbidden') {
      return 'Sitzung abgelaufen — bitte Seite neu laden.'
    }
    // The login ran out (401, auth.login_redirect). A reload lands on the
    // login page, which is the only way back.
    if (this.reason === 'unauthorized') {
      return 'Abgemeldet — bitte neu anmelden.'
    }
    // A value the server will not store. It says which and why; retrying the
    // same value cannot work.
    if (this.reason === 'invalid') {
      return this.serverMessage ?? 'Eingabe ungültig — nicht gespeichert.'
    }
    // A live-screen write to a workout that already finished (409, see
    // _refuse_live_write_if_finished). Nothing to retry: the screen is stale.
    if (this.reason === 'finished') {
      return 'Das Workout ist schon beendet.'
    }
    return this.reason === 'timeout'
      ? 'Keine Antwort vom Server — deine letzte Änderung wurde nicht gespeichert.'
      : 'Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.'
  }

  /** Whether the same request could work if sent again. Only a lost or slow
   *  connection can; a refused value or a stale page cannot. */
  get retryable(): boolean {
    return this.reason === 'timeout' || this.reason === 'network'
  }

  /** Whether a reload is the way out: a fresh page mints a fresh CSRF token,
   *  and without a login it lands on the login page. */
  get needsReload(): boolean {
    return this.reason === 'forbidden' || this.reason === 'unauthorized'
  }
}

/** A non-ok answer, named. Every status the server uses on purpose has its
 *  own reason; only what is left over reads as a failed connection -- a 400
 *  and a lapsed login used to be "Verbindung fehlgeschlagen" too (G-083,
 *  G-093). */
async function failureFrom(response: Response): Promise<MutationFailed> {
  switch (response.status) {
    case 401: return new MutationFailed('unauthorized')
    case 403: return new MutationFailed('forbidden')
    case 409: return new MutationFailed('finished')
    case 400: {
      const body = await response.json().catch(() => null) as { error?: unknown } | null
      return new MutationFailed('invalid',
        typeof body?.error === 'string' ? body.error : undefined)
    }
    default: return new MutationFailed('network')
  }
}

/** fetch follows redirects by itself, so a server that still sends a lapsed
 *  login to the login page answers a JSON read with that page, and a 200. */
function landedOnLogin(response: Response): boolean {
  return response.redirected && new URL(response.url, window.location.href).pathname === '/login'
}

/** POST form fields, get the page's fresh payload back. The caller names the
 *  payload type it is owed -- which page answers is the server's decision
 *  (_mutation_response branches on finished_at). */
export interface PostOptions {
  keepalive?: boolean
  /** Extra request headers -- the live workout names itself with one. */
  headers?: Record<string, string>
}

export function postForm<T>(
  url: string, fields: Record<string, string | number | boolean> = {},
  opts: PostOptions = {},
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
  url: string, body: FormData, opts: PostOptions = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      method: 'POST', body, headers: { ...writeHeaders(), ...opts.headers },
      credentials: 'same-origin', signal: controller.signal,
      // The pagehide flush posts a write the page will not stay alive to see
      // answered; keepalive lets the request outlive the document.
      keepalive: opts.keepalive ?? false,
    })
    if (!response.ok) throw await failureFrom(response)
    if (landedOnLogin(response)) throw new MutationFailed('unauthorized')
    return await response.json() as T
  } catch (error) {
    if (error instanceof MutationFailed) throw error
    throw new MutationFailed(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
  }
}

/** POST-and-navigate, for routes that answer with a redirect to a NEW page
 *  (finish -> debrief, invite -> partner confirm, save-as-template). A real
 *  form submit, so the browser follows the redirect; it carries the same
 *  csrf_token field every native form embeds. This exists because the port
 *  shipped both failure modes at once: `window.location.href` was a GET to a
 *  POST-only route (405), and the hand-built forms carried no token (403
 *  once the blueprint's CSRF gate closed). */
export function postNavigate(url: string, fields: Record<string, string> = {}): void {
  const form = document.createElement('form')
  form.method = 'post'
  form.action = url
  const all: Record<string, string> = { csrf_token: csrfToken(), ...fields }
  for (const [name, value] of Object.entries(all)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = name
    input.value = value
    form.append(input)
  }
  document.body.append(form)
  form.submit()
}

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: JSON_HEADERS, credentials: 'same-origin',
  })
  if (!response.ok) throw await failureFrom(response)
  if (landedOnLogin(response)) throw new MutationFailed('unauthorized')
  return await response.json() as T
}

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MutationFailed, getJson, postForm, postNavigate } from './api'
import { resetCsrfCache } from './csrf'

describe('postNavigate', () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok-123">'
    document.body.innerHTML = ''
    resetCsrfCache()
  })

  it('builds a real POST form carrying the csrf token', () => {
    // Both failure modes the port shipped, pinned: window.location.href was a
    // GET to a POST-only route (405), and the hand-built forms carried no
    // csrf_token (403 once the blueprint gate closed).
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(() => {})
    postNavigate('/gym/session/7/finish', { extra: 'x' })

    const form = document.querySelector('form')!
    expect(form.method).toBe('post')
    expect(form.getAttribute('action')).toBe('/gym/session/7/finish')
    expect((form.querySelector('input[name="csrf_token"]') as HTMLInputElement).value)
      .toBe('tok-123')
    expect((form.querySelector('input[name="extra"]') as HTMLInputElement).value)
      .toBe('x')
    expect(submit).toHaveBeenCalledOnce()
    submit.mockRestore()
  })
})

describe('postForm failure reasons', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('names a 403 as forbidden, with its own message and no futile retry text', async () => {
    // A stale CSRF token after a long-idle PWA session used to read as
    // "Verbindung fehlgeschlagen" with a retry that could never succeed.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 403 } as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(MutationFailed)
    expect((error as MutationFailed).reason).toBe('forbidden')
    expect((error as MutationFailed).germanMessage).toContain('neu laden')
  })

  it('names a 409 as a workout that has already finished', async () => {
    // _refuse_live_write_if_finished: the live screen outlived its workout.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409 } as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e)
    expect((error as MutationFailed).reason).toBe('finished')
  })

  it('sends extra headers alongside the ones every write carries', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) } as Response))
    vi.stubGlobal('fetch', fetchMock)
    await postForm('/gym/x', {}, { headers: { 'X-Gym-Surface': 'live' } })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['X-Gym-Surface']).toBe('live')
    expect(headers['Accept']).toBe('application/json')
  })

  it('reads a server that is down or busy as a failed connection', async () => {
    for (const status of [429, 502, 503, 504]) {
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status } as Response)))
      const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
      expect(error.reason, String(status)).toBe('network')
      expect(error.retryable).toBe(true)
    }
  })

  it('names any other non-ok a server error: worth a retry, but not forever (B6 review)', async () => {
    for (const status of [500, 413, 422]) {
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status } as Response)))
      const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
      expect(error.reason, String(status)).toBe('server')
      expect(error.retryable).toBe(true)
      expect(error.germanMessage).toBe('Fehler auf dem Server — die Änderung wurde nicht gespeichert.')
    }
  })

  it('shows the server\'s own sentence for a refused value, with nothing to retry', async () => {
    // G-070/G-083: a 400 used to read as "Verbindung fehlgeschlagen".
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 400,
      json: async () => ({ error: 'Gewicht: bitte 0 bis 1000 kg.' }),
    } as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('invalid')
    expect(error.germanMessage).toBe('Gewicht: bitte 0 bis 1000 kg.')
    expect(error.retryable).toBe(false)
  })

  it('still says the value was refused when a 400 carries no sentence', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 400, json: async () => { throw new SyntaxError('html') },
    } as unknown as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('invalid')
    expect(error.germanMessage).toContain('nicht gespeichert')
  })

  it('names a 401 as a lapsed login, and a reload as the way out', async () => {
    // G-093: auth.login_redirect answers an island's fetch with a 401.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 } as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('unauthorized')
    expect(error.germanMessage).toContain('anmelden')
    expect(error.needsReload).toBe(true)
  })

  it('reads a redirect that landed on the login page as a lapsed login', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, status: 200, redirected: true, url: 'http://localhost/login',
      json: async () => { throw new SyntaxError('html') },
    } as unknown as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('unauthorized')
  })
})

describe('getJson failure reasons', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('names a 401 on a read as a lapsed login, not a failed connection', async () => {
    // The sync.json poll and the detail read answered the login page (G-093).
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 } as Response)))
    const error = await getJson('/gym/x.json').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('unauthorized')
  })

  it('names a 404 as gone, with nothing to retry (B4 re-review)', async () => {
    // A discarded workout's read: it read as a lost connection, retried
    // forever.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 } as Response)))
    const error = await getJson('/gym/x.json').catch((e: unknown) => e) as MutationFailed
    expect(error.reason).toBe('gone')
    expect(error.retryable).toBe(false)
    expect(error.germanMessage).toContain('Gibt es nicht mehr')
  })

  it('gives up on a read with a write\'s time limit, as a retry (B6 re-review)', async () => {
    // The outbox asks under the workout's lock: a question into dead wifi
    // held every tab's writes for as long as the phone took to give up.
    vi.useFakeTimers()
    try {
      vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise((_, reject) => {
        init.signal!.addEventListener('abort', () => {
          reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
        })
      })))
      const asked = getJson('/gym/x.json').catch((e: unknown) => e)
      await vi.advanceTimersByTimeAsync(8000)
      const error = await asked as MutationFailed
      expect(error).toBeInstanceOf(MutationFailed)
      expect(error.reason).toBe('timeout')
      expect(error.retryable).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('names a read that could not get through a failed connection', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const error = await getJson('/gym/x.json').catch((e: unknown) => e) as MutationFailed
    expect(error).toBeInstanceOf(MutationFailed)
    expect(error.reason).toBe('network')
  })
})

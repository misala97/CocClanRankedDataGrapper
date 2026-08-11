import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MutationFailed, postForm, postNavigate } from './api'
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

  it('keeps any other non-ok as a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 } as Response)))
    const error = await postForm('/gym/x').catch((e: unknown) => e)
    expect((error as MutationFailed).reason).toBe('network')
  })
})

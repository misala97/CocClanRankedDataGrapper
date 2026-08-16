import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { heartbeatSubscription } from './push'

/** The shape the browser hands back from getSubscription(). */
const fakeSubscription = (endpoint: string) => ({
  endpoint,
  toJSON: () => ({ endpoint, keys: { p256dh: 'p', auth: 'a' } }),
}) as unknown as PushSubscription

describe('heartbeatSubscription', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}'))))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('re-posts the subscription this device already holds', () => {
    // The whole mechanism: the server prunes on silence, so a device in use
    // has to make a noise. Without this call the row goes stale and the
    // subscription is deleted out from under a phone still using it.
    heartbeatSubscription(fakeSubscription('https://web.push.apple.com/abc'))
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!
    expect(url).toBe('/gym/push/subscribe')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body).endpoint).toBe('https://web.push.apple.com/abc')
  })

  it('says nothing when this device has no subscription', () => {
    heartbeatSubscription(null)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('swallows a failed beat rather than surfacing it', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))))
    heartbeatSubscription(fakeSubscription('https://web.push.apple.com/abc'))
    // An unhandled rejection here would fail the suite; bookkeeping the user
    // never asked for must not become an error they see.
    await Promise.resolve()
  })
})

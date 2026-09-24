import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enablePush, heartbeatSubscription, subscribePush } from './push'
import { usePush } from './session/stores'

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

/** Any base64url string decodes; this is the shape of a real VAPID key. */
const KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'

/** A device that can push: the worker registers, the prompt answers
 *  `permission`, the push service hands out a subscription (or `subscribe`
 *  does something else), and the server answers `status`. */
function device({ permission = 'granted', status = 200, subscribe }: {
  permission?: NotificationPermission
  status?: number
  subscribe?: () => Promise<PushSubscription>
} = {}) {
  const subscription = fakeSubscription('https://web.push.apple.com/new')
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      register: vi.fn(async () => ({
        pushManager: { subscribe: subscribe ?? (async () => subscription) },
      })),
    },
  })
  vi.stubGlobal('Notification', { requestPermission: vi.fn(async () => permission) })
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status })))
}

describe('subscribePush', () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'serviceWorker')
    vi.unstubAllGlobals()
  })

  it('asks, subscribes, tells the server, and only then says on', async () => {
    device()
    expect(await subscribePush(KEY)).toBe('on')
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!
    expect(url).toBe('/gym/push/subscribe')
    expect(init.headers['X-CSRF-Token']).toBeDefined()
    expect(JSON.parse(init.body).endpoint).toBe('https://web.push.apple.com/new')
  })

  it('reports a server that refused as failed, not as on (G-148)', async () => {
    // Both old copies ignored the answer: a 500 turned the prompt off for good
    // on a device the server never heard of.
    device({ status: 500 })
    expect(await subscribePush(KEY)).toBe('failed')
  })

  it('reports a subscribe the browser rejected as failed', async () => {
    device({ subscribe: async () => { throw new DOMException('push service', 'AbortError') } })
    expect(await subscribePush(KEY)).toBe('failed')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('tells a blocked permission from a dismissed prompt', async () => {
    device({ permission: 'denied' })
    expect(await subscribePush(KEY)).toBe('denied')
    device({ permission: 'default' })
    expect(await subscribePush(KEY)).toBe('dismissed')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('is unavailable where the server has no key', async () => {
    device()
    expect(await subscribePush(null)).toBe('unavailable')
    expect(fetch).not.toHaveBeenCalled()
  })
})

describe('enablePush', () => {
  beforeEach(() => { usePush.setState(usePush.getInitialState(), true) })
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'serviceWorker')
    vi.unstubAllGlobals()
  })

  it('marks this device on and drops an earlier failure', async () => {
    usePush.setState({ subscribed: false, error: 'alt' })
    device()
    await enablePush(KEY)
    expect(usePush.getState()).toMatchObject({ subscribed: true, error: null })
  })

  it('leaves the device off and says why', async () => {
    usePush.setState({ subscribed: false })
    device({ status: 500 })
    await enablePush(KEY)
    expect(usePush.getState().subscribed).toBe(false)
    expect(usePush.getState().error).toMatch(/nicht aktivieren/)
  })

  it('says nothing about a prompt the lifter dismissed', async () => {
    usePush.setState({ subscribed: false })
    device({ permission: 'default' })
    await enablePush(KEY)
    expect(usePush.getState()).toMatchObject({ subscribed: false, error: null })
  })
})

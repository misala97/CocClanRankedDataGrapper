import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useFollowerSync } from './useFollowerSync'
import { sessionKey } from './useSessionMutation'
import { useAnnouncer } from './stores'

/* The contract this pins is the one the React port lost: the follower's poll
 * was deleted with the Jinja page and never rebuilt, so a leader's structural
 * change reached the follower's DATABASE ROWS and never their screen. These
 * assert the effect (a refetch of the session query), not the presence of a
 * hook. */

const SESSION = 42

function wrap(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function freshClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

const sync = (over: Partial<{ version: number; shared: boolean }> = {}) =>
  ({ ok: true, json: async () => ({ version: 1, shared: true, ...over }) } as Response)

beforeEach(() => {
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
})
afterEach(() => { vi.unstubAllGlobals() })

describe('useFollowerSync', () => {
  it('does not poll at all for a session that is not shared', async () => {
    const fetchMock = vi.fn(async () => sync())
    vi.stubGlobal('fetch', fetchMock)
    const client = freshClient()

    renderHook(() => useFollowerSync(SESSION, { enabled: false, knownVersion: 1 }),
      { wrapper: wrap(client) })

    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refetches the session when the leader moved the plan', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sync({ version: 7 })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    renderHook(() => useFollowerSync(SESSION, { enabled: true, knownVersion: 3 }),
      { wrapper: wrap(client) })

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(
      { queryKey: sessionKey(SESSION) }))
    // The one thing on this screen the lifter did not cause says so.
    expect(useAnnouncer.getState().message).toBe('Dein Partner hat den Plan geändert.')
  })

  it('stays quiet while the version is unchanged', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sync({ version: 3 })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    renderHook(() => useFollowerSync(SESSION, { enabled: true, knownVersion: 3 }),
      { wrapper: wrap(client) })

    await new Promise((resolve) => setTimeout(resolve, 60))
    expect(invalidate).not.toHaveBeenCalled()
    expect(useAnnouncer.getState().message).toBe('')
  })

  /* The two below run on fake timers deliberately. With real ones, a test
   * that waits 80ms and finds no second request proves nothing -- the poll
   * interval is five SECONDS, so it would pass whether polling stopped or
   * not. Asserting an absence is only worth anything once the clock has
   * actually passed the point where the thing would have happened. */

  it('keeps polling on the interval while the link is live', async () => {
    vi.useFakeTimers()
    try {
      const fetchMock = vi.fn(async () => sync({ version: 3 }))
      vi.stubGlobal('fetch', fetchMock)
      renderHook(() => useFollowerSync(SESSION, { enabled: true, knownVersion: 3 }),
        { wrapper: wrap(freshClient()) })

      await vi.advanceTimersByTimeAsync(50)
      const first = fetchMock.mock.calls.length
      expect(first).toBeGreaterThan(0)
      await vi.advanceTimersByTimeAsync(12_000)
      expect(fetchMock.mock.calls.length).toBeGreaterThan(first)
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops polling once the link has ended', async () => {
    // Ending a link stamps SharedSession.ended_at and never touches
    // structure_version, so "shared: false" has to be its own signal --
    // gating on the version alone polled forever after the leader finished.
    vi.useFakeTimers()
    try {
      const fetchMock = vi.fn(async () => sync({ shared: false }))
      vi.stubGlobal('fetch', fetchMock)
      renderHook(() => useFollowerSync(SESSION, { enabled: true, knownVersion: 1 }),
        { wrapper: wrap(freshClient()) })

      await vi.advanceTimersByTimeAsync(50)
      const afterFirst = fetchMock.mock.calls.length
      expect(afterFirst).toBeGreaterThan(0)
      // Well past two intervals: the previous version of this test waited
      // 80ms and would have passed with the stop condition deleted.
      await vi.advanceTimersByTimeAsync(12_000)
      expect(fetchMock.mock.calls.length).toBe(afterFirst)
    } finally {
      vi.useRealTimers()
    }
  })
})

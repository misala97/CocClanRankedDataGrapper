import { act, renderHook, waitFor } from '@testing-library/react'
import {
  QueryClient, QueryClientProvider, focusManager, onlineManager,
} from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FOLLOWER_POLL_MS, LEADER_POLL_MS, usePartnerSync } from './usePartnerSync'
import { sessionKey } from './api'
import { useAnnouncer, usePartnerNotice } from './stores'
import type { PartnerLink } from '../partner/types'

/* Two contracts. The follower's, which the React port once lost: a leader's
 * structural change reached the follower's DATABASE ROWS and never their
 * screen -- these assert the effect (a refetch of the session query), not
 * the presence of a hook. And the partner lines' (D14): seeded by the page,
 * kept by sync.json, asked after only while a line can still change. */

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

function link(over: Partial<PartnerLink> = {}): PartnerLink {
  return {
    id: 7, username: 'jglaser', viewer_leads: true, state: 'joined',
    since: '2026-09-25T09:26:00', finished_at: null,
    exercise: 'Bankdrücken', set_no: 2, done_in_exercise: 1, sets_in_exercise: 3,
    last_set: { weight: 60, reps: 8 }, rest_left: null, sets_done: 1, sets_total: 9, list_key: 1,
    ...over,
  }
}

interface Answer { version?: number; shared?: boolean; partner_links?: PartnerLink[] }

/** fetch, routed: sync.json answers `answer()`, anything else `other`. */
function server(answer: () => Answer, other: () => Response = () => new Response('{}')) {
  return vi.fn(async (url: string) => (String(url).endsWith('/sync.json')
    ? new Response(JSON.stringify({ version: 1, shared: true, partner_links: [], ...answer() }))
    : other()))
}

const syncCalls = (fetchMock: ReturnType<typeof server>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/sync.json')).length

/** The lifter leaves the tab and comes back. */
async function returnToTab() {
  act(() => { focusManager.setFocused(false) })
  act(() => { focusManager.setFocused(true) })
  await vi.advanceTimersByTimeAsync(50)
}

/** The phone loses the network and finds it again. */
async function returnToNetwork() {
  act(() => { onlineManager.setOnline(false) })
  act(() => { onlineManager.setOnline(true) })
  await vi.advanceTimersByTimeAsync(50)
}

beforeEach(() => {
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  usePartnerNotice.setState(usePartnerNotice.getInitialState(), true)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  focusManager.setFocused(undefined)
  onlineManager.setOnline(true)
})

/* The timing tests run on fake timers deliberately. With real ones, a test
 * that waits 80ms and finds no second request proves nothing -- the poll
 * interval is seconds, so it would pass whether polling stopped or not.
 * Asserting an absence is only worth anything once the clock has actually
 * passed the point where the thing would have happened. */

describe('usePartnerSync: the lines', () => {
  it('starts from the page and asks the leader\'s first question a full interval later', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link({ set_no: 3 })] }))
    vi.stubGlobal('fetch', fetchMock)
    const start = Date.now()
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    expect(result.current.links.map((l) => l.set_no)).toEqual([2])
    expect(result.current.receivedAt).toBe(start)
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS - 100)
    expect(syncCalls(fetchMock)).toBe(0)
    await vi.advanceTimersByTimeAsync(200)
    expect(syncCalls(fetchMock)).toBe(1)
    expect(result.current.links.map((l) => l.set_no)).toEqual([3])
    // Each rest counts down from the moment its answer came.
    expect(result.current.receivedAt).toBe(start + LEADER_POLL_MS)
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS)
    expect(syncCalls(fetchMock)).toBe(2)
  })

  it('keeps asking while an invite is unanswered', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link({ state: 'invited' })] }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ state: 'invited' })], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS * 3 + 100)
    expect(syncCalls(fetchMock)).toBe(3)
  })

  it('stops asking once every line is settled: declined or finished', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({
      partner_links: [link({ state: 'finished' }), link({ id: 8, state: 'declined' })],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link(), link({ id: 8, state: 'invited' })], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100)
    expect(syncCalls(fetchMock)).toBe(1)
    expect(result.current.links.map((l) => l.state)).toEqual(['finished', 'declined'])
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS * 4)
    expect(syncCalls(fetchMock)).toBe(1)
  })

  it('asks nothing at all without a partner', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({}))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, { initial: [], follower: false, knownVersion: 1 }),
      { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS * 4)
    expect(fetchMock).not.toHaveBeenCalled()
    // Nor on a return: a workout alone asked sync.json on every one.
    await returnToTab()
    await returnToNetwork()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asks on a return to the tab or the network while a line can change', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link()] }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, { initial: [link()], follower: false, knownVersion: 1 }),
      { wrapper: wrap(freshClient()) })

    // Older than five seconds, and the next poll still seconds away.
    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    await returnToTab()
    expect(syncCalls(fetchMock)).toBe(1)
    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    await returnToNetwork()
    expect(syncCalls(fetchMock)).toBe(2)
  })

  it('puts a declined line away at once, and the row with it', async () => {
    const fetchMock = server(() => ({}), () => new Response('{"ok": true}'))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ id: 8, state: 'declined' }), link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    act(() => result.current.dismiss(8))

    expect(result.current.links.map((l) => l.id)).toEqual([7])
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/gym/shared/8/dismiss', expect.objectContaining({ method: 'POST' })))
  })

  it('asks what a line is now after an OK that failed, and hides only a no', async () => {
    // Nothing polls a screen whose lines are all settled: an OK refused came
    // back as the stale "declined", and every tap got the same answer.
    const now = [
      link({ id: 8, state: 'declined' }), // the OK never arrived
      link({ id: 9, state: 'invited' }), // asked again from the other phone (404)
      link({ id: 10, state: 'joined' }), // joined after all (the server's 409)
      link({ id: 11, state: 'declined' }), // put away there, and a stale answer (404)
    ]
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/sync.json')) {
        return new Response(JSON.stringify({ version: 1, shared: false, partner_links: now }))
      }
      if (String(url).includes('/8/')) throw new TypeError('offline')
      if (String(url).includes('/10/')) return new Response('{}', { status: 409 })
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [8, 9, 10, 11].map((id) => link({ id, state: 'declined' })),
      follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    act(() => { [8, 9, 10, 11].forEach((id) => { result.current.dismiss(id) }) })
    expect(result.current.links).toEqual([])
    await waitFor(() => expect(result.current.links.map((l) => [l.id, l.state])).toEqual([
      [8, 'declined'], [9, 'invited'], [10, 'joined'],
    ]))
  })
})

describe('usePartnerSync: the follower keeps up with the leader\'s plan', () => {
  it('asks every five seconds while the leader trains', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link({ viewer_leads: false })] }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ viewer_leads: false })], follower: true, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS * 2 + 100)
    expect(syncCalls(fetchMock)).toBe(2)
  })

  it('refetches the session when the leader moved the plan', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({
      version: 7, partner_links: [link({ viewer_leads: false })],
    })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ viewer_leads: false })], follower: true, knownVersion: 3,
    }), { wrapper: wrap(client) })

    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: sessionKey(SESSION) })
    // The one thing on this screen the lifter did not cause says so.
    expect(useAnnouncer.getState().message).toBe('Dein Partner hat den Plan geändert.')
    // ...and says it where a sighted lifter can see it. The announcement alone
    // is sr-only text: the queue used to rearrange itself in silence.
    expect(usePartnerNotice.getState().visible).toBe(true)
  })

  it('stays quiet while the version is unchanged', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({
      version: 3, partner_links: [link({ viewer_leads: false })],
    })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ viewer_leads: false })], follower: true, knownVersion: 3,
    }), { wrapper: wrap(client) })

    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS * 2 + 100)
    expect(invalidate).not.toHaveBeenCalled()
    expect(useAnnouncer.getState().message).toBe('')
  })

  it('leaves a leader\'s version alone: only the follower\'s rows are written', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({ version: 9, partner_links: [link()] })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link()], follower: false, knownVersion: 3,
    }), { wrapper: wrap(client) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100)
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('stops asking once the leader has finished, and stops following', async () => {
    // Ending a link stamps SharedSession.ended_at and never touches
    // structure_version, so the line's own state has to stop the poll --
    // gating on the version alone polled forever after the leader finished.
    vi.useFakeTimers()
    const fetchMock = server(() => ({
      version: 1, shared: false, partner_links: [link({ state: 'finished', viewer_leads: false })],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ viewer_leads: false })], follower: true, knownVersion: 1,
    }), { wrapper: wrap(client) })

    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    expect(syncCalls(fetchMock)).toBe(1)
    // "Ab jetzt bestimmst du die Reihenfolge": the page asks after itself
    // once, and its session_is_shared lets go of the leader's order. It
    // stayed in follower mode until a reload.
    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: sessionKey(SESSION) })
    // Well past two intervals: a stop condition deleted would show here.
    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS * 4)
    expect(syncCalls(fetchMock)).toBe(1)
    expect(invalidate).toHaveBeenCalledTimes(1)
  })

  it('stops following when the link ends under a leader still training', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({ version: 1, shared: false, partner_links: [] })))
    const client = freshClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ viewer_leads: false })], follower: true, knownVersion: 1,
    }), { wrapper: wrap(client) })

    // Following, with the leader's line: nothing to ask.
    expect(invalidate).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: sessionKey(SESSION) })
  })
})

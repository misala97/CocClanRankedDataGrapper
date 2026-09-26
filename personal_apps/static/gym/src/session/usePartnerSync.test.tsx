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

/** A line as the server sends it once the link ended with the partner still
 *  training (B11): nothing of their rows. */
const ENDED = {
  state: 'ended' as const, exercise: null, set_no: null, done_in_exercise: 0,
  sets_in_exercise: 0, last_set: null, sets_done: 0, sets_total: 0, list_key: 0,
}

interface Answer { version?: number; partner_links?: PartnerLink[] }

/** fetch, routed: sync.json answers `answer()`, anything else `other`. */
function server(answer: () => Answer, other: () => Response = () => new Response('{}')) {
  return vi.fn(async (url: string) => (String(url).endsWith('/sync.json')
    ? new Response(JSON.stringify({ version: 1, partner_links: [], ...answer() }))
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
        return new Response(JSON.stringify({ version: 1, partner_links: now }))
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

describe('usePartnerSync: ending it (B11)', () => {
  const posts = (fetchMock: ReturnType<typeof server>, path: string) =>
    fetchMock.mock.calls.filter(([url]) => String(url) === path).length

  it('asks nothing more once every line has ended', async () => {
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link(ENDED)] }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100)
    expect(result.current.links.map((l) => l.state)).toEqual(['ended'])
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS * 4)
    expect(syncCalls(fetchMock)).toBe(1)
  })

  it('asks after an ended line on a return to the tab or the network', async () => {
    // It turns finished when the partner finishes, or goes with their
    // workout thrown away: too seldom to poll for, not never.
    vi.useFakeTimers()
    const fetchMock = server(() => ({ partner_links: [link(ENDED)] }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, {
      initial: [link(ENDED)], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS * 3)
    expect(syncCalls(fetchMock)).toBe(0)
    await returnToTab()
    expect(syncCalls(fetchMock)).toBe(1)
    await vi.advanceTimersByTimeAsync(FOLLOWER_POLL_MS + 100)
    await returnToNetwork()
    expect(syncCalls(fetchMock)).toBe(2)
  })

  it('takes an invite back: gone at once, then sync.json asked what is so', async () => {
    const fetchMock = server(() => ({ partner_links: [link()] }), () => new Response('{"ok": true}'))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ id: 8, state: 'invited' }), link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    let sent!: Promise<unknown>
    act(() => { sent = result.current.withdraw(8) })
    expect(result.current.links.map((l) => l.id)).toEqual([7])
    let outcome: unknown
    await act(async () => { outcome = await sent })
    expect(outcome).toEqual({ done: true })
    expect(fetchMock).toHaveBeenCalledWith(
      '/gym/shared/8/withdraw', expect.objectContaining({ method: 'POST' }))
    await waitFor(() => expect(syncCalls(fetchMock)).toBe(1))
    expect(result.current.links.map((l) => l.id)).toEqual([7])
  })

  it('brings a withdrawn invite back when the request did not get through', async () => {
    const fetchMock = server(() => ({}), () => { throw new TypeError('offline') })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link({ id: 8, state: 'invited' })], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    let outcome: unknown
    await act(async () => { outcome = await result.current.withdraw(8) })
    expect(outcome).toEqual({ done: false, message: 'Ging nicht durch — nochmal tippen.' })
    expect(result.current.links.map((l) => [l.id, l.state])).toEqual([[8, 'invited']])
    // Nothing answered, so nothing to ask sync.json about.
    expect(syncCalls(fetchMock)).toBe(0)
  })

  it('takes a 404 or a 409 as an answer: the line then says what is so', async () => {
    // Joined after all (409): back, as joined. Gone already (404): stays gone.
    let answer: PartnerLink[] = [link({ id: 8, state: 'invited' }), link({ id: 9, state: 'invited' })]
    const fetchMock = server(() => ({ partner_links: answer }), () => new Response('{}', {
      status: fetchMock.mock.calls.at(-1)![0].includes('/8/') ? 409 : 404,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    answer = [link({ id: 8 }), link({ id: 9, state: 'invited' })]
    let outcomes: unknown[] = []
    await act(async () => {
      outcomes = await Promise.all([result.current.withdraw(8), result.current.withdraw(9)])
    })
    expect(outcomes).toEqual([{ done: true }, { done: true }])
    await waitFor(() => expect(result.current.links.map((l) => [l.id, l.state]))
      .toEqual([[8, 'joined']]))
  })

  it('ends it through the one route, and asks sync.json at once', async () => {
    const fetchMock = server(() => ({ partner_links: [link(ENDED)] }),
      () => new Response('{"ok": true}'))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    let outcome: unknown
    await act(async () => { outcome = await result.current.end(7) })
    expect(outcome).toEqual({ done: true })
    expect(posts(fetchMock, '/gym/shared/7/end')).toBe(1)
    await waitFor(() => expect(result.current.links.map((l) => l.state)).toEqual(['ended']))
  })

  it('answers an end the server refused as done, and one not sent as what to say', async () => {
    let status = 409
    const fetchMock = server(() => ({ partner_links: [link()] }),
      () => new Response('{}', { status }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: [link()], follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    const outcome = async () => {
      let got: unknown
      await act(async () => { got = await result.current.end(7) })
      return got
    }
    expect(await outcome()).toEqual({ done: true })
    status = 404
    expect(await outcome()).toEqual({ done: true })
    status = 503
    expect(await outcome()).toEqual({ done: false, message: 'Ging nicht durch — nochmal tippen.' })
    // Sending again cannot mend a lapsed session: said as such.
    status = 403
    expect(await outcome()).toEqual({
      done: false, message: 'Sitzung abgelaufen — bitte Seite neu laden.',
    })
  })

  it('keeps a line whose link vanished, in its place, said as vanished', async () => {
    vi.useFakeTimers()
    let answer: PartnerLink[] = [link({ id: 3, username: 'anna' }), link(),
      link({ id: 9, username: 'mghorbani', ...ENDED }), link({ id: 11, username: 'wt', state: 'invited' })]
    const fetchMock = server(() => ({ partner_links: answer }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    // Two workouts thrown away took 3's link and 9's; an invite taken back
    // on the other phone just goes.
    answer = [link()]
    await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100) })
    expect(result.current.links.map((l) => [l.id, l.state])).toEqual([
      [3, 'vanished'], [7, 'joined'], [9, 'vanished'],
    ])
    // And stays so, answer after answer.
    await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS) })
    expect(syncCalls(fetchMock)).toBe(2)
    expect(result.current.links.map((l) => [l.id, l.state])).toEqual([
      [3, 'vanished'], [7, 'joined'], [9, 'vanished'],
    ])
  })

  it('lets a vanished line go once its partner is back on a line of their own', async () => {
    vi.useFakeTimers()
    const anna = link({ id: 5, username: 'anna' })
    let answer: PartnerLink[] = [anna, link()]
    vi.stubGlobal('fetch', server(() => ({ partner_links: answer })))
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })
    const shown = () => result.current.links.map((l) => [l.id, l.username, l.state])
    const next = async (lines: PartnerLink[]) => {
      answer = lines
      await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100) })
    }

    // jglaser's workout thrown away; asked again from the other phone: a
    // new link, and the old line goes.
    await next([anna])
    expect(shown()).toEqual([[5, 'anna', 'joined'], [7, 'jglaser', 'vanished']])
    await next([anna, link({ id: 12, state: 'invited' })])
    expect(shown()).toEqual([[5, 'anna', 'joined'], [12, 'jglaser', 'invited']])
    // For good: the invite taken back, it does not come back.
    await next([anna])
    expect(shown()).toEqual([[5, 'anna', 'joined']])
    // Asked once more and in, then thrown away once more: said once.
    await next([anna, link({ id: 14, state: 'invited' })])
    await next([anna, link({ id: 14 })])
    await next([anna])
    expect(shown()).toEqual([[5, 'anna', 'joined'], [14, 'jglaser', 'vanished']])
    // A line that comes back is itself again, and only itself.
    await next([anna, link({ id: 14 })])
    expect(shown()).toEqual([[5, 'anna', 'joined'], [14, 'jglaser', 'joined']])
    // Gone and asked again between two answers: the new line alone.
    await next([anna, link({ id: 16, state: 'invited' })])
    expect(shown()).toEqual([[5, 'anna', 'joined'], [16, 'jglaser', 'invited']])
  })

  it('keeps a vanished line beside an older line of the same partner', async () => {
    // Followed until they finished, then asked back into this workout: the
    // workout they came with thrown away, that line goes, the finished stays
    // -- answer after answer.
    vi.useFakeTimers()
    const finished = link({
      id: 4, viewer_leads: false, state: 'finished', finished_at: '2026-09-25T10:40:00',
    })
    const anna = (setNo: number) => link({ id: 5, username: 'anna', set_no: setNo })
    let answer: PartnerLink[] = [finished, anna(1), link({ id: 12 })]
    vi.stubGlobal('fetch', server(() => ({ partner_links: answer })))
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })
    const shown = () => result.current.links.map((l) => [l.id, l.state])

    answer = [finished, anna(1)]
    await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100) })
    expect(shown()).toEqual([[4, 'finished'], [5, 'joined'], [12, 'vanished']])
    answer = [finished, anna(2)]
    await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS) })
    expect(shown()).toEqual([[4, 'finished'], [5, 'joined'], [12, 'vanished']])
  })

  it('never shows a frame without the line whose link vanished', async () => {
    // Gone for one render, it would move all under it by its 52 px.
    vi.useFakeTimers()
    let answer: PartnerLink[] = [link({ id: 3, username: 'anna' }), link()]
    vi.stubGlobal('fetch', server(() => ({ partner_links: answer })))
    const frames: number[][] = []
    renderHook(() => {
      const sync = usePartnerSync(SESSION, { initial: answer, follower: false, knownVersion: 1 })
      frames.push(sync.links.map((l) => l.id))
      return sync
    }, { wrapper: wrap(freshClient()) })

    answer = [link({ id: 3, username: 'anna' })]
    await act(async () => { await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100) })
    expect(frames.length).toBeGreaterThan(1)
    expect(frames.filter((ids) => !ids.includes(7))).toEqual([])
  })

  it('says aloud when a line stops being joined, once', async () => {
    vi.useFakeTimers()
    const other = (over: Partial<PartnerLink> = {}) =>
      link({ id: 8, username: 'mghorbani', ...over })
    let answer: PartnerLink[] = [link(), other()]
    const fetchMock = server(() => ({ partner_links: answer }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100)
    expect(useAnnouncer.getState().message).toBe('')
    answer = [link(ENDED), other()]
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS)
    expect(result.current.links.map((l) => l.state)).toEqual(['ended', 'joined'])
    expect(useAnnouncer.getState().message).toBe('jglaser trainiert allein weiter.')
    expect(useAnnouncer.getState().nonce).toBe(1)
    // The other partner lifts on: nothing more is said.
    answer = [link(ENDED), other({ set_no: 3, done_in_exercise: 2, sets_done: 2 })]
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS)
    expect(result.current.links.map((l) => l.set_no)).toEqual([null, 3])
    expect(useAnnouncer.getState().nonce).toBe(1)
  })

  it('says a vanished line and a finished leader aloud too', async () => {
    vi.useFakeTimers()
    let answer: PartnerLink[] = [link({ viewer_leads: false }), link({ id: 8 })]
    const fetchMock = server(() => ({ partner_links: answer }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePartnerSync(SESSION, {
      initial: answer, follower: false, knownVersion: 1,
    }), { wrapper: wrap(freshClient()) })

    answer = [link({ id: 8 })]
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS + 100)
    expect(useAnnouncer.getState().message)
      .toBe('jglaser ist nicht mehr dabei, ab jetzt bestimmst du die Reihenfolge.')
    answer = [link({ id: 8, state: 'finished', sets_done: 9, sets_total: 9 })]
    await vi.advanceTimersByTimeAsync(LEADER_POLL_MS)
    expect(useAnnouncer.getState().message).toBe('jglaser ist fertig, alle 9 Sätze.')
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
      version: 1, partner_links: [link({ state: 'finished', viewer_leads: false })],
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
    // As the server says it since B11: the line, ended.
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({
      version: 1, partner_links: [link({ viewer_leads: false, ...ENDED })],
    })))
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

  it('stops following when the leader\'s workout is thrown away', async () => {
    // The link goes with it: no line at all, the page's own said as vanished.
    vi.useFakeTimers()
    vi.stubGlobal('fetch', server(() => ({ version: 1, partner_links: [] })))
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

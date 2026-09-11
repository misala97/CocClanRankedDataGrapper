// The board somebody else is building, on the surface.
//
// Every state here is one the old island could not express: it had a board or
// it had an error, and a miss was answered by building one in the request the
// reader was waiting on. With the shared result the answer can be "not yet",
// "not for you right now", "here, but a refresh is queued" or "the builds are
// failing" -- and the difference between them is the whole point, because
// each one asks something different of the reader.

import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { detail, payload, row } from '../fixtures'
import type { BoardPayload, Detail } from '../types'
import { BoardPage } from './BoardPage'

/** A waiting shell exactly as `board_shared._waiting` writes one: the
 *  selection echoed back, and null everywhere a board would have been. */
function waiting(over: Partial<BoardPayload> = {}): BoardPayload {
  return payload({
    shared: true, pending: true, busy: false, stale: false, failed: false,
    generated_at: null, as_of: null, built_at: null, age_seconds: null,
    retry_after_ms: 1000, queue_age_seconds: 0, ops_collected_at: null,
    rows: null, watching: [], watch_rows: [],
    segment_counts: {}, venue_counts: { any: 0, multi: 0 }, excluded: {},
    ...over,
  })
}

/** A board that was read from the store rather than built here. */
function served(over: Partial<BoardPayload> = {}): BoardPayload {
  return payload({ shared: true, ...over })
}

const ok = (body: unknown) => ({
  ok: true, redirected: false, status: 200, json: async () => body,
})

/** Route by URL, as BoardPage.test.tsx does, with one addition: a `poll=1`
 *  request may answer something different from the first read, because that
 *  is exactly what a wait is. */
function stubFetch(board: (url: string) => BoardPayload | Promise<unknown>) {
  const spy = vi.fn(async (url: string) => {
    if (url.includes('/api/ticker/')) {
      return ok(detail(url.split('/api/ticker/')[1]!.split('?')[0]!,
        (new URL(url, 'https://radar.test').searchParams
          .get('market') as Detail['market']) ?? 'us'))
    }
    const answer = board(url)
    return { ok: true, redirected: false, status: 200, json: async () => answer }
  })
  vi.stubGlobal('fetch', spy)
  return spy
}

const boardCalls = () => vi.mocked(fetch).mock.calls
  .map((c) => String(c[0])).filter((u) => u.includes('/api/board'))

const advance = (ms: number) =>
  act(async () => { await vi.advanceTimersByTimeAsync(ms) })

/** A plain click. user-event drives its own clock and deadlocks against
 *  vitest's fake timers, which every test in this file needs. */
const click = (element: Element) =>
  act(async () => { fireEvent.click(element) })

const ageLine = () => document.querySelector('.age')
const waitingLine = () => document.querySelector('.none.pending')
const rowCount = () => document.querySelectorAll('.row').length

function visibility(state: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState',
    { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
  vi.useFakeTimers()
  // The jitter, taken out: every delay below is the schedule's own number.
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  vi.setSystemTime(new Date('2026-08-22T19:00:00Z'))
  // The wait continues unless a test says otherwise: a stub that answered
  // a board would end every one of these on the first poll.
  stubFetch(() => waiting())
  window.history.replaceState(null, '', '/radar/')
  visibility('visible')
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('a board that is still being calculated', () => {
  it('says so, shows no rows, and claims no build time', async () => {
    render(<BoardPage initial={waiting()} />)

    expect(waitingLine()).toHaveTextContent('Calculating this board')
    // Empty is a real answer -- nothing was loud enough in this window -- and
    // drawing it over a board that does not exist yet is the one thing this
    // state exists to prevent.
    expect(screen.queryByText(/Nothing cleared the bar/)).toBeNull()
    expect(rowCount()).toBe(0)
    // "Calculated just now" about a board nobody has built is a lie the
    // masthead must never tell.
    expect(ageLine()).toBeNull()
    // The controls are the point of echoing the selection back: the reader
    // may ask a different question instead of watching this one.
    expect(screen.getByRole('button', { name: /Change window/i }))
      .toBeInTheDocument()
    expect(document.querySelector('.spend')).toBeNull()
  })

  it('asks again, as a poll, inside the first delay', async () => {
    render(<BoardPage initial={waiting()} />)
    expect(boardCalls()).toHaveLength(0)

    await advance(1000)

    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })

  it('draws the board the moment a poll brings one', async () => {
    stubFetch((url) => (url.includes('poll=1') ? served() : waiting()))
    render(<BoardPage initial={waiting()} />)

    await advance(1000)

    expect(screen.getByRole('link', { name: /AAA/ })).toBeInTheDocument()
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(waitingLine()).toBeNull()
  })

  it('stops asking once the board is there', async () => {
    stubFetch((url) => (url.includes('poll=1') ? served() : waiting()))
    render(<BoardPage initial={waiting()} />)

    await advance(1000)
    expect(boardCalls()).toHaveLength(1)

    await advance(30_000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('drops the answer to the question the reader has already left', async () => {
    // The wait is where a reader is most likely to change their mind, and an
    // aborted request cannot unsend a response that is already on its way.
    // Old rows under a new window's label is the exact failure being tested.
    let landLate!: (board: BoardPayload) => void
    const late = new Promise<BoardPayload>((resolve) => { landLate = resolve })
    stubFetch((url) => (url.includes('window=12')
      ? served({ window_hours: 12, rows: [row({ ticker: 'NEW' })] })
      : late))
    render(<BoardPage initial={waiting()} />)

    await advance(1000)
    expect(boardCalls()[0]).toContain('window=4')

    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: '12h' }))
    await advance(300)

    expect(screen.getByRole('link', { name: /NEW/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '12h' }))
      .toHaveAttribute('aria-pressed', 'true')

    landLate(served({ window_hours: 4, rows: [row({ ticker: 'OLD' })] }))
    await advance(50)

    expect(screen.queryByRole('link', { name: /OLD/ })).toBeNull()
    expect(screen.getByRole('link', { name: /NEW/ })).toBeInTheDocument()
  })

  it('names the new window while the new board is still being calculated', async () => {
    stubFetch(() => waiting({ window_hours: 12 }))
    render(<BoardPage initial={waiting()} />)

    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: '12h' }))
    await advance(300)

    expect(waitingLine()).toHaveTextContent('Calculating this board')
    expect(screen.getByRole('button', { name: '12h' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(boardCalls().at(-1)).toContain('window=12')

    // And the wait that belonged to the old window is over: nothing asks
    // about four hours, however long the new one takes.
    await advance(20_000)
    expect(boardCalls().filter((url) => url.includes('window=4')))
      .toHaveLength(0)
    expect(boardCalls().filter((url) => url.includes('window=12')).length)
      .toBeGreaterThan(1)
  })

  it('does not poll a queue for a tab nobody is looking at', async () => {
    render(<BoardPage initial={waiting()} />)
    await advance(1000)
    expect(boardCalls()).toHaveLength(1)

    await act(async () => { visibility('hidden') })
    await advance(30_000)
    expect(boardCalls()).toHaveLength(1)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(2)
  })

  it('admits it is taking long, and offers the way out', async () => {
    render(<BoardPage initial={waiting()} />)

    await advance(35_000)

    expect(waitingLine()).toHaveTextContent('Still calculating')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(waitingLine()).toHaveTextContent(/window or the (?:feeds|sources)/)

    // And it keeps asking, at the slower rate rather than not at all.
    const asked = boardCalls().length
    await advance(5000)
    expect(boardCalls()).toHaveLength(asked + 1)
  })

  it('refetches when the reader retries', async () => {
    render(<BoardPage initial={waiting()} />)
    await advance(35_000)
    const asked = boardCalls().length

    await click(screen.getByRole('button', { name: 'Retry' }))
    await advance(50)

    expect(boardCalls().length).toBeGreaterThan(asked)
  })
})

describe('a board that is busy with other selections', () => {
  const busy = () => waiting({
    pending: false, busy: true, retry_after_ms: 5000, queue_age_seconds: null,
  })

  it('says what is happening, keeps the controls, and slows down', async () => {
    stubFetch(() => busy())
    render(<BoardPage initial={busy()} />)

    expect(waitingLine())
      .toHaveTextContent('The board is busy with other selections.')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Change window/i }))
      .toBeInTheDocument()
    expect(rowCount()).toBe(0)

    // Nothing is queued, so there is nothing to be near the front of: the
    // server asks for five seconds and the client does not undercut it.
    await advance(4000)
    expect(boardCalls()).toHaveLength(0)
    await advance(1000)
    expect(boardCalls()).toHaveLength(1)
    await advance(5000)
    expect(boardCalls()).toHaveLength(2)
  })
})

describe('a board with a refresh queued behind it', () => {
  const stale = (over: Partial<BoardPayload> = {}) => served({
    stale: true, age_seconds: 180, retry_after_ms: 5000, ...over,
  })

  it('shows its rows and says a fresher one is on the way', async () => {
    stubFetch(() => stale())
    render(<BoardPage initial={stale()} />)

    expect(rowCount()).toBeGreaterThan(0)
    expect(ageLine()).toHaveTextContent('Calculated 3m ago · refreshing')
  })

  it('asks every five seconds until the refresh lands', async () => {
    let fresh = false
    stubFetch(() => (fresh ? served() : stale()))
    render(<BoardPage initial={stale()} />)

    await advance(5000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')

    fresh = true
    await advance(5000)
    expect(boardCalls()).toHaveLength(2)
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    await advance(30_000)
    expect(boardCalls()).toHaveLength(2)
  })
})

describe('a board that has outlived the window it names', () => {
  it('is taken off the screen rather than left there to be read', async () => {
    // Past the hard expiry the rows describe a rolling window that has moved
    // on. The client clock is what decides it: a tab left open all afternoon
    // never asks the server anything.
    stubFetch(() => waiting())
    render(<BoardPage initial={served({ age_seconds: 599,
                                        hard_expiry_seconds: 600 })} />)
    expect(rowCount()).toBeGreaterThan(0)

    await advance(1100)

    expect(rowCount()).toBe(0)
    expect(waitingLine()).toHaveTextContent('Calculating this board')
  })

  it('says the board expired while the replacement is on its way', async () => {
    stubFetch(() => new Promise(() => {}))
    render(<BoardPage initial={served({ age_seconds: 900,
                                        hard_expiry_seconds: 600 })} />)

    await advance(50)

    expect(ageLine()).toHaveClass('expired')
    expect(ageLine()).toHaveTextContent(/Expired/i)
    expect(boardCalls()).toHaveLength(1)
  })
})

describe('a board whose rebuilds are failing', () => {
  it('keeps the rows it has and says the refresh failed', async () => {
    stubFetch(() => served({ failed: true, age_seconds: 180 }))
    render(<BoardPage initial={served({ failed: true, age_seconds: 180 })} />)

    expect(rowCount()).toBeGreaterThan(0)
    expect(ageLine()).toHaveTextContent('Last refresh failed')
  })

  it('says so plainly when there is no board underneath it', async () => {
    const parked = waiting({ failed: true, retry_after_ms: 5000 })
    stubFetch(() => parked)
    render(<BoardPage initial={parked} />)

    const oops = document.querySelector('.rows .oops')
    expect(oops).toHaveTextContent(/could not be built/i)
    expect(oops?.querySelector('button')).toHaveTextContent('Retry')
    expect(waitingLine()).toBeNull()
    expect(screen.queryByText(/Nothing cleared the bar/)).toBeNull()
  })
})

describe('a board that is simply empty', () => {
  it('still says nothing cleared the bar', async () => {
    render(<BoardPage initial={served({ rows: [], excluded: {} })} />)

    expect(screen.getByText(/Nothing cleared the bar in this window/))
      .toBeInTheDocument()
    expect(waitingLine()).toBeNull()
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
  })
})

describe('a board from a server that never heard of the shared store', () => {
  it('renders exactly as it always did, and polls for nothing', async () => {
    render(<BoardPage initial={payload()} />)

    expect(rowCount()).toBe(4)
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(ageLine()).not.toHaveTextContent('refreshing')
    expect(waitingLine()).toBeNull()

    await advance(60_000)
    expect(boardCalls()).toHaveLength(0)
  })
})

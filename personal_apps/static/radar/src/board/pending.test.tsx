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

import { detail, envelope, payload, row } from '../fixtures'
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

/** A board as a deployment from before the envelope embedded one: every
 *  delivery field absent -- not false, not null -- which is the shape a
 *  browser's cache can still hand the page. */
function preEnvelope(over: Partial<BoardPayload> = {}): BoardPayload {
  const board: Record<string, unknown> = { ...payload(over) }
  for (const field of Object.keys(envelope())) delete board[field]
  return board as unknown as BoardPayload
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
  // The jitter, taken out: the spread only adds, so every delay below is the
  // schedule's own number (or the server's floor, where it asked for one).
  vi.spyOn(Math, 'random').mockReturnValue(0)
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

  it('never paints a board under a selection nobody is on any more', async () => {
    // The debounce is a quarter of a second in which the reader has already
    // moved on and the request for the new question has not gone out yet. A
    // poll answer that lands inside it belongs to a question nobody is
    // asking, and drawing it would put its rows under the new window's label
    // -- so the old wait has to be over when the control moves, not when the
    // new request is sent.
    let landPoll!: (board: BoardPayload) => void
    const held = new Promise<BoardPayload>((resolve) => { landPoll = resolve })
    stubFetch((url) => {
      if (url.includes('poll=1')) return held
      if (url.includes('window=24')) {
        return served({ window_hours: 24, rows: [row({ ticker: 'NEW' })] })
      }
      return waiting({ window_hours: 12 })
    })
    render(<BoardPage initial={waiting({ window_hours: 12 })} />)

    await advance(1000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')

    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: '24h' }))
    // Mid-debounce, the board the reader stopped waiting for arrives.
    await advance(100)
    landPoll(served({ window_hours: 12, rows: [row({ ticker: 'OLD' })] }))
    await advance(50)

    expect(screen.queryByRole('link', { name: /OLD/ })).toBeNull()
    expect(rowCount()).toBe(0)
    // Nor has anything else gone out in the meantime: the old wait is over,
    // and the new question has not been asked yet.
    expect(boardCalls()).toHaveLength(1)

    // And the new question goes out when the burst settles, as it always did.
    await advance(200)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls()[1]).toContain('window=24')
    expect(boardCalls()[1]).not.toContain('poll=1')
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

  it('keeps its place in the back-off when the reader retries', async () => {
    // A retry is an extra ask, not a new wait. Restarting the schedule would
    // put a reader who has been waiting half a minute -- and has just been
    // told so -- back on the one-second poll the wait opened with, so the
    // longer they wait the more of the queue they take.
    render(<BoardPage initial={waiting()} />)
    await advance(35_000)
    const asked = boardCalls().length

    await click(screen.getByRole('button', { name: 'Retry' }))
    await advance(50)
    expect(boardCalls()).toHaveLength(asked + 1)

    // Nothing at a second; the wait is still on its five.
    await advance(1200)
    expect(boardCalls()).toHaveLength(asked + 1)
    await advance(4000)
    expect(boardCalls()).toHaveLength(asked + 2)
  })

  it('lets a slow retry answer instead of asking over the top of it', async () => {
    // The wait keeps its schedule through a retry (above), so its next ask
    // can come due while the retry is still out. Sending it aborted the
    // reader's own request -- one board asked for twice -- and left the
    // controls marked busy, pointer events off, by a request nothing
    // remained to finish.
    let answerRetry!: (board: BoardPayload) => void
    const retried = new Promise<BoardPayload>((resolve) => {
      answerRetry = resolve
    })
    stubFetch((url) => (url.includes('poll=1') ? waiting() : retried))
    render(<BoardPage initial={waiting()} />)
    await advance(35_000)
    const asked = boardCalls().length

    await click(screen.getByRole('button', { name: 'Retry' }))
    // Past the moment the schedule's next ask came due (36.5s): it waited
    // for the retry's answer rather than sending one of its own.
    await advance(3000)
    expect(boardCalls()).toHaveLength(asked + 1)
    expect(document.querySelector('.controls'))
      .toHaveAttribute('aria-busy', 'true')

    answerRetry(waiting())
    await advance(0)
    expect(document.querySelector('.controls'))
      .toHaveAttribute('aria-busy', 'false')
    // And the wait carries on from there, on its own five seconds.
    await advance(5000)
    expect(boardCalls()).toHaveLength(asked + 2)
  })

  it('starts the wait over when the reader asks a different question', async () => {
    // The thirty seconds are how long THIS wait has lasted. A new selection
    // is a new wait, and telling a reader who has just changed the window
    // that it is "still" calculating describes somebody else's patience.
    stubFetch(() => waiting({ window_hours: 12 }))
    render(<BoardPage initial={waiting()} />)
    await advance(35_000)
    expect(waitingLine()).toHaveTextContent('Still calculating')

    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: '12h' }))
    await advance(300)

    expect(waitingLine()).toHaveTextContent('Calculating this board')
    expect(waitingLine()).not.toHaveTextContent('Still calculating')
  })

  it('opens no wait in a tab that was already hidden when it mounted', async () => {
    // A tab restored in the background fires no visibilitychange at all, so
    // the state has to be read rather than waited for -- the same reading
    // the hub's own useVisible() does.
    visibility('hidden')
    render(<BoardPage initial={waiting()} />)

    await advance(30_000)
    expect(boardCalls()).toHaveLength(0)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)
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
    expect(document.querySelector('.age b.queued'))
      .toHaveTextContent('refreshing')
    // The panel's own request settles inside act(), not after the test.
    await advance(0)
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

  it('leaves the address bar alone when a poll brings the same board', async () => {
    // replaceState on a five-second cadence, for a board that has not
    // changed, is a page rewriting its own history entry all afternoon.
    stubFetch(() => stale())
    const wrote = vi.spyOn(window.history, 'replaceState')
    render(<BoardPage initial={stale()} />)

    await advance(5000)

    expect(boardCalls()).toHaveLength(1)
    expect(wrote).not.toHaveBeenCalled()
  })

  it('says refreshing whenever the page is waiting on one, whoever built the board', async () => {
    // The line and the page read one rule. A board the store calls stale is
    // waited on whatever the flag says, so the word is "refreshing" -- not
    // "not refreshed", with a Retry beside a wait that is already asking.
    stubFetch(() => new Promise(() => {}))
    render(<BoardPage initial={payload({ stale: true, age_seconds: 180,
                                         retry_after_ms: 5000 })} />)

    expect(document.querySelector('.age b.queued'))
      .toHaveTextContent('refreshing')
    expect(ageLine()).not.toHaveTextContent('not refreshed')
    expect(ageLine()?.querySelector('button')).toBeNull()

    await advance(5000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })
})

describe('a board that goes stale while this page is holding it', () => {
  it('passes the fresh bound on its own clock and goes to look', async () => {
    // `fresh_seconds` is the server's bound, not the server's verdict: a
    // board sent as fresh crosses it a minute later with nothing on the wire
    // to say so, and a tab left open would sit on it for the afternoon.
    let fresher = false
    stubFetch(() => (fresher
      ? served({ as_of: '2026-08-22T19:02:00Z',
                 built_at: '2026-08-22T19:02:00Z' })
      : served({ age_seconds: 130 })))
    render(<BoardPage initial={served({ age_seconds: 110,
                                        fresh_seconds: 120 })} />)

    expect(ageLine()).toHaveTextContent('Calculated 1m ago')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    await advance(11_000)

    expect(ageLine()).toHaveTextContent('refreshing')
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')

    // Every five seconds from there, not the schedule's opening steps. That
    // answer said `stale: false` -- it was sent before the store would have
    // said otherwise -- so the server named no floor, and the refresh behind
    // it takes as long as a build does.
    await advance(4000)
    expect(boardCalls()).toHaveLength(1)
    fresher = true
    await advance(1000)
    expect(boardCalls()).toHaveLength(2)

    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(ageLine()).not.toHaveTextContent('refreshing')
    // A board that is fresh again sends nothing until it is not.
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

  it('asks once when it expires with a refresh already queued', async () => {
    // Expiry and the refresh it is waiting for are the same question, and
    // asking it twice in the same instant is two builds of one board.
    stubFetch(() => waiting())
    render(<BoardPage initial={served({ stale: true, age_seconds: 599,
                                        hard_expiry_seconds: 600,
                                        retry_after_ms: 1000 })} />)

    await advance(1100)

    expect(boardCalls()).toHaveLength(1)
  })

  it('asks once when it expires while a poll is already out', async () => {
    // The other order: the wait's poll went out first and has not answered
    // when the board expires. That poll's answer IS the refetch; a second
    // request sent beside it aborted the first and built the board twice.
    stubFetch(() => new Promise(() => {}))
    render(<BoardPage initial={served({ stale: true, age_seconds: 598.5,
                                        hard_expiry_seconds: 600,
                                        retry_after_ms: 1000 })} />)

    await advance(2000)

    expect(ageLine()).toHaveClass('expired')
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })

  it('stands down when a poll has just answered as it expires', async () => {
    // The poll lands a moment before the expiry clock fires -- after the
    // answer, before the render that would have disarmed the clock. The
    // board it was armed for is already gone, and asking again is a second
    // request for an answer the page already has.
    stubFetch(() => waiting())
    render(<BoardPage initial={served({ stale: true, age_seconds: 598.9,
                                        hard_expiry_seconds: 600,
                                        retry_after_ms: 1000 })} />)

    await advance(1200)

    expect(boardCalls()).toHaveLength(1)
    expect(rowCount()).toBe(0)
  })

  it('leaves a hidden tab asleep when its board expires', async () => {
    // Nobody is reading an expired board in a background tab, and coming
    // back asks at once anyway. A refetch here that also woke the wait left
    // it polling a shared queue on behalf of nobody until the tab returned.
    render(<BoardPage initial={served({ stale: true, age_seconds: 590,
                                        hard_expiry_seconds: 600,
                                        retry_after_ms: 5000 })} />)
    await act(async () => { visibility('hidden') })

    await advance(30_000)
    expect(boardCalls()).toHaveLength(0)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)
  })

  it('leaves a hidden tab asleep when a board a worker built expires', async () => {
    // No wait runs behind a flag-off board, so its expiry refetch went out
    // whatever the tab was doing -- and each answer armed the next, so a
    // background tab asked for a synchronous build every ten minutes for as
    // long as it stayed open. It waits to be looked at instead.
    stubFetch(() => payload())
    render(<BoardPage initial={payload({ age_seconds: 590 })} />)
    await act(async () => { visibility('hidden') })

    await advance(30_000)
    expect(boardCalls()).toHaveLength(0)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
  })

  it('stops claiming a recalculation once the refetch has failed', async () => {
    // The expiry refetch is the one request an expired flag-off board gets.
    // When it failed nothing re-armed it, and the line went on saying
    // "recalculating" over a page that was doing nothing of the kind.
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (
      url.includes('/api/board')
        ? { ok: false, redirected: false, status: 503, json: async () => ({}) }
        : ok(detail()))))
    render(<BoardPage initial={payload({ age_seconds: 599 })} />)

    await advance(1100)
    expect(boardCalls()).toHaveLength(1)
    expect(ageLine()).toHaveClass('expired')
    expect(ageLine()).toHaveTextContent('Expired')
    expect(ageLine()).not.toHaveTextContent('recalculating')
    // The page's banner says the refetch failed, and its Retry is the one
    // on offer.
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()

    // Nothing asks again on a timer...
    await advance(30_000)
    expect(boardCalls()).toHaveLength(1)
    // ...the reader coming back to the tab re-arms it...
    await act(async () => { visibility('hidden') })
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(2)
    // ...and so does the button.
    await click(screen.getByRole('button', { name: 'Retry' }))
    expect(boardCalls()).toHaveLength(3)
  })
})

describe('a poll that lands while the reader is reading', () => {
  // A poll is the page asking on the reader's behalf. What it brings back
  // may replace the board; it must never replace the reader's choice.
  const stale = () => served({
    stale: true, age_seconds: 180, retry_after_ms: 5000,
  })
  const rebuilt = (tickers: string[]) => served({
    as_of: '2026-08-22T19:02:00Z', built_at: '2026-08-22T19:02:00Z',
    rows: tickers.map((ticker) => row({ ticker })),
  })
  const selectedRow = () => document.querySelector('.row.on')

  it('keeps the row the reader clicked while it was out', async () => {
    let land!: (board: BoardPayload) => void
    stubFetch(() => new Promise<BoardPayload>((resolve) => { land = resolve }))
    render(<BoardPage initial={stale()} />)
    expect(selectedRow()).toHaveTextContent('AAA')

    await advance(5000)
    expect(boardCalls()).toHaveLength(1)
    await click(screen.getByRole('link', { name: /BBB/ }))
    expect(selectedRow()).toHaveTextContent('BBB')

    land(rebuilt(['AAA', 'BBB', 'CCC', 'DDD']))
    await advance(0)

    expect(selectedRow()).toHaveTextContent('BBB')
    expect(window.location.search).toContain('t=BBB')
  })

  it('keeps the reader\'s ticker when the new build no longer lists it', async () => {
    // The market switch has always kept the company when its new board does
    // not rank it. A poll is even less of a reason to move the panel: the
    // reader did nothing at all.
    let land!: (board: BoardPayload) => void
    stubFetch(() => new Promise<BoardPayload>((resolve) => { land = resolve }))
    render(<BoardPage initial={stale()} />)

    await advance(5000)
    land(rebuilt(['EEE', 'BBB']))
    await advance(0)

    expect(screen.getByRole('link', { name: /EEE/ })).toBeInTheDocument()
    expect(selectedRow()).toBeNull()
    expect(window.location.search).toContain('t=AAA')
  })
})

describe('a refetch that lands while the reader is reading', () => {
  // Not only a poll: a Retry, the refetch after a mark and the one an expired
  // board sends are all out while the reader goes on clicking, and the answer
  // to each is about the ticker on screen when it lands.
  const selectedRow = () => document.querySelector('.row.on')

  it('keeps the row the reader clicked while an expired board was being refetched', async () => {
    let land!: (board: BoardPayload) => void
    stubFetch(() => new Promise<BoardPayload>((resolve) => { land = resolve }))
    render(<BoardPage initial={payload({ age_seconds: 599 })} />)
    expect(selectedRow()).toHaveTextContent('AAA')

    await advance(1100)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
    await click(screen.getByRole('link', { name: /BBB/ }))
    expect(selectedRow()).toHaveTextContent('BBB')

    land(payload())
    await advance(0)

    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(selectedRow()).toHaveTextContent('BBB')
    expect(window.location.search).toContain('t=BBB')
  })
})

describe('the server\'s floor under a wait', () => {
  const busy = (over: Partial<BoardPayload> = {}) => waiting({
    pending: false, busy: true, retry_after_ms: 5000, queue_age_seconds: null,
    ...over,
  })

  it('holds when the reader retries over a poll that was out', async () => {
    // The Retry aborts the poll in flight, and that poll then answers
    // nothing. It used to take the server's floor with it -- the next ask
    // went out on the schedule's own step -- while the Retry's own answer,
    // busy for another five seconds, never reached the wait at all.
    let held = true
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/api/ticker/')) return Promise.resolve(ok(detail()))
      if (url.includes('poll=1') && held) {
        held = false
        return new Promise((_, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'))
          })
        })
      }
      return Promise.resolve(ok(busy()))
    }))
    render(<BoardPage initial={busy()} />)

    await advance(5000)
    expect(boardCalls()).toHaveLength(1)
    await advance(1000)
    await click(screen.getByRole('button', { name: 'Retry' }))
    expect(boardCalls()).toHaveLength(2)

    // Five seconds from the Retry's answer, not a schedule step from the
    // abort.
    await advance(4900)
    expect(boardCalls()).toHaveLength(2)
    await advance(200)
    expect(boardCalls()).toHaveLength(3)
  })

  it('holds to what the first read of a new selection said', async () => {
    // The wait for the new question opens at once, on the floor of the
    // answer on screen -- the OLD question's one second. The answer to the
    // new question asked for five, and the wait has to hear it.
    stubFetch(() => busy({ window_hours: 12 }))
    render(<BoardPage initial={waiting()} />)

    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: '12h' }))
    await advance(300)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')

    await advance(4900)
    expect(boardCalls()).toHaveLength(1)
    await advance(100)
    expect(boardCalls()).toHaveLength(2)
  })
})

describe('a board whose rebuilds are failing', () => {
  it('keeps the rows it has and says the refresh failed', async () => {
    stubFetch(() => served({ failed: true, age_seconds: 180 }))
    render(<BoardPage initial={served({ failed: true, age_seconds: 180 })} />)

    expect(rowCount()).toBeGreaterThan(0)
    expect(ageLine()).toHaveTextContent('Last refresh failed')
    // A failure is not a queued refresh, and must not be quieted into one:
    // the class that takes `refreshing` out of the caution colour is the
    // refreshing token's own, never the whole line's.
    expect(document.querySelector('.age b.queued')).toBeNull()
    // The panel's own request settles inside act(), not after the test.
    await advance(0)
  })

  it('says so plainly when there is no board underneath it', async () => {
    const parked = waiting({ failed: true, retry_after_ms: 5000 })
    stubFetch(() => parked)
    render(<BoardPage initial={parked} />)

    const oops = document.querySelector('.rows .oops')
    expect(oops).toHaveTextContent(/could not be built/i)
    expect(oops?.querySelector('button')).toHaveTextContent('Retry')
    // Named for where it sits, not for a state it is never in: the busy
    // generation has its own quiet paragraph.
    expect(oops).toHaveClass('inline')
    expect(oops).not.toHaveClass('busy')
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
  it('dates itself by its build stamp when it carries no age', async () => {
    // A document cached in a browser from before the envelope existed: no
    // age anywhere in it -- none of its fields at all -- and the build stamp
    // the corner used to print sitting right there. Printing nothing is the
    // worse answer.
    vi.setSystemTime(new Date('2026-08-22T19:03:00Z'))
    render(<BoardPage initial={preEnvelope({
      generated_at: '2026-08-22T19:00:00Z' })} />)

    expect(ageLine()).toHaveTextContent('Calculated 3m ago')
    // And nothing claims a refresh that a server without the store could
    // not be doing.
    expect(ageLine()).not.toHaveTextContent('refreshing')
    await advance(60_000)
    expect(boardCalls()).toHaveLength(0)
  })

  it('renders exactly as it always did while it is fresh', async () => {
    render(<BoardPage initial={payload()} />)

    expect(rowCount()).toBe(4)
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(ageLine()).not.toHaveClass('stale')
    expect(ageLine()).not.toHaveTextContent('refreshing')
    expect(waitingLine()).toBeNull()
    // The panel's own request settles inside act(), not after the test.
    await advance(0)
  })

  it('is marked stale past the fresh bound, says nothing is refreshing it, and asks only when told to', async () => {
    // Ruling §5: between the fresh bound and the hard expiry a board may stay
    // on screen ONLY as stale, with no exception by path -- and flag-off is
    // production until the flag flips. What a board a worker built for itself
    // lacks is anything behind it: no store, no queued refresh, and a request
    // at the bound would only build another synchronously. So it is marked,
    // the word claims no refresh, and the request is the reader's button.
    render(<BoardPage initial={payload()} />)

    await advance(150_000)
    expect(boardCalls()).toHaveLength(0)
    expect(ageLine()).toHaveClass('stale')
    expect(ageLine()).toHaveTextContent('Calculated 2m ago · not refreshed')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    await click(ageLine()!.querySelector('button')!)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
  })
})

describe('a board at exactly its fresh bound', () => {
  // board_shared.disposition reads `fresh_seconds` strictly: a board exactly
  // that old is still fresh. The page reads the bound the same way on both
  // paths; what differs is only what is done about a board past it.
  it('is plain at the bound and marked past it when a worker built it', async () => {
    render(<BoardPage initial={payload({ age_seconds: 110 })} />)

    await advance(10_000)
    expect(ageLine()).not.toHaveClass('stale')
    expect(ageLine()?.textContent).toBe('Calculated 2m ago')

    await advance(1000)
    expect(ageLine()).toHaveClass('stale')
    expect(ageLine()).toHaveTextContent('Calculated 2m ago · not refreshed')
    expect(boardCalls()).toHaveLength(0)
  })

  it('is plain at the bound and refreshing past it when the store serves it', async () => {
    stubFetch(() => new Promise(() => {}))
    render(<BoardPage initial={served({ age_seconds: 110 })} />)

    await advance(10_000)
    expect(ageLine()).not.toHaveClass('stale')
    expect(ageLine()?.textContent).toBe('Calculated 2m ago')
    expect(boardCalls()).toHaveLength(0)

    await advance(1000)
    expect(ageLine()).toHaveClass('stale')
    expect(document.querySelector('.age b.queued'))
      .toHaveTextContent('refreshing')
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })
})

describe('a Retry while the reader\'s own request is out', () => {
  // An abort stops this page listening; it does not stop the server. A board
  // a worker builds for itself is built to the end whoever stopped waiting
  // for it, so a Retry that aborted the request already out and sent another
  // was one more synchronous build per click -- the pattern the debounce on
  // the controls was put in to stop.
  it('joins the request already out instead of sending another', async () => {
    const sent: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/api/ticker/')) return Promise.resolve(ok(detail()))
      if (init?.signal) sent.push(init.signal)
      return new Promise(() => {})
    }))
    render(<BoardPage initial={payload()} />)
    await advance(150_000)
    expect(ageLine()).toHaveTextContent('not refreshed')

    await click(ageLine()!.querySelector('button')!)
    await click(ageLine()!.querySelector('button')!)

    expect(boardCalls()).toHaveLength(1)
    expect(sent[0]?.aborted).toBe(false)
  })

  it('offers one Retry once an expired board has failed to refetch, and it asks once', async () => {
    // The page's banner and the age line each offered one, a few pixels
    // apart, and they did different things: the banner's aborted whatever
    // was out and let the ticker go, the line's joined and kept it.
    let failing = true
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/ticker/')) return Promise.resolve(ok(detail()))
      if (failing) {
        return Promise.resolve({ ok: false, redirected: false, status: 503,
                                 json: async () => ({}) })
      }
      return new Promise(() => {})
    }))
    render(<BoardPage initial={payload({ age_seconds: 599 })} />)

    await advance(1100)
    expect(boardCalls()).toHaveLength(1)
    expect(screen.getByRole('alert')).toHaveTextContent('answered with an error')
    expect(ageLine()).toHaveTextContent('Expired')
    expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1)

    failing = false
    await click(screen.getByRole('button', { name: 'Retry' }))
    await click(screen.getByRole('button', { name: 'Retry' }))
    expect(boardCalls()).toHaveLength(2)
  })
})

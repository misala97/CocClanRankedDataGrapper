// The board somebody else is building, as the hub shows it.
//
// The same states the old board island learned in Task 5, on the surface that
// reads them through react-query: a board that is not built yet, one that is
// being rebuilt behind the reader, a generation too busy to take the question,
// a key whose builds keep failing, and a board that has simply outlived the
// window it names. Each asks something different of the reader, and none of
// them is an empty board.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { detail, payload, row } from '../fixtures'
import type { BoardPayload, Detail } from '../types'
import { Hub } from './Hub'

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

const busy = (over: Partial<BoardPayload> = {}) => waiting({
  pending: false, busy: true, retry_after_ms: 5000, queue_age_seconds: null,
  ...over,
})

/** A board that was read from the store rather than built here. */
function served(over: Partial<BoardPayload> = {}): BoardPayload {
  return payload({ shared: true, ...over })
}

const ok = (body: unknown) => ({
  ok: true, redirected: false, status: 200, json: async () => body,
})

/** Route by URL. A `poll=1` request may answer something different from the
 *  first read, because that is exactly what a wait is. */
function stubFetch(board: (url: string, init?: RequestInit) => unknown) {
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes('/api/ticker/')) {
      return ok(detail(url.split('/api/ticker/')[1]!.split('?')[0]!,
        (new URL(url, 'https://radar.test').searchParams
          .get('market') as Detail['market']) ?? 'us'))
    }
    if (url.includes('/api/search')) return ok({ matches: [] })
    return ok(await board(url, init))
  })
  vi.stubGlobal('fetch', spy)
  return spy
}

/** A board request that never answers. */
const never = () => new Promise(() => {})

const boardCalls = () => vi.mocked(fetch).mock.calls
  .map((c) => String(c[0])).filter((u) => u.includes('/api/board'))

const advance = (ms: number) =>
  act(async () => { await vi.advanceTimersByTimeAsync(ms) })

/** Plain events. user-event drives its own clock and deadlocks against
 *  vitest's fake timers, which every test here needs. */
const click = (element: Element) =>
  act(async () => { fireEvent.click(element) })
const choose = (element: Element, value: string) =>
  act(async () => { fireEvent.change(element, { target: { value } }) })

const notice = () => document.querySelector('.rh-wait')
const ageLine = () => document.querySelector('.rh-age')
const contextLine = () => document.querySelector('.rh-datestamp')
const listed = () => screen.queryAllByTestId('rh-row-ticker')
  .map((el) => el.textContent)
const retryButtons = () => screen.queryAllByRole('button', { name: 'Retry' })

function visibility(state: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState',
    { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

let client: QueryClient

function mount(initial: BoardPayload, hash = '#overview') {
  window.history.replaceState(null, '', `/radar/hub/${hash}`)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Hub initial={initial} isAdmin={false} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  // The jitter, taken out: the spread only adds, so every delay below is the
  // schedule's own number (or the server's floor, where it asked for one).
  vi.spyOn(Math, 'random').mockReturnValue(0)
  vi.setSystemTime(new Date('2026-08-22T19:00:00Z'))
  // The wait continues unless a test says otherwise: a stub that answered a
  // board would end every one of these on the first poll.
  stubFetch(() => waiting())
  visibility('visible')
})

afterEach(() => {
  // Unmounted on the fake clock, so nothing the page armed outlives it.
  cleanup()
  client?.clear()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/radar/hub/')
})

describe('a board that is still being calculated', () => {
  it('says so on the overview, and claims neither an empty board nor a build time', async () => {
    mount(waiting())

    expect(notice()).toHaveTextContent('Calculating this board')
    // Empty is a real answer -- nothing was loud enough in this window -- and
    // drawing it over a board that does not exist yet is the one thing this
    // state exists to prevent.
    expect(screen.queryByText(/Nothing cleared the floor/i)).toBeNull()
    expect(screen.queryByText(/No company cleared/i)).toBeNull()
    expect(screen.queryAllByTestId('rh-candidate')).toHaveLength(0)
    // "Calculated just now" about a board nobody has built is a lie the page
    // must never tell, and so is a build stamp.
    expect(document.body.textContent).not.toMatch(/built|Calculated/)
    // Nor does it tell a reader with marks that they have none: the shell
    // carries no marks at all.
    expect(screen.queryByText(/Nothing marked yet/i)).toBeNull()
  })

  it('keeps the filters on Human chatter while it waits', async () => {
    mount(waiting(), '#chatter')

    expect(notice()).toHaveTextContent('Calculating this board')
    // The controls are the point of echoing the selection back: the reader
    // may ask a different question instead of watching this one.
    for (const label of [/market/i, /window/i, /size/i]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    expect(contextLine()).toHaveTextContent('US markets · last 4 hours')
    expect(screen.queryByText(/No company cleared/i)).toBeNull()
    expect(listed()).toHaveLength(0)
  })

  it('asks again, as a poll, inside the first delay', async () => {
    mount(waiting())
    expect(boardCalls()).toHaveLength(0)

    await advance(1000)

    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })

  it('draws the board the moment a poll brings one, and says when it was calculated', async () => {
    stubFetch((url) => (url.includes('poll=1') ? served() : waiting()))
    mount(waiting(), '#chatter')

    await advance(1000)
    expect(boardCalls()).toHaveLength(1)
    // react-query tells React on its own next tick, which a timer set inside
    // a fake tick puts a millisecond later.
    await advance(1)

    expect(listed()).toEqual(['AAA', 'BBB', 'CCC', 'DDD'])
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(contextLine()).toHaveTextContent(
      'US markets · last 4 hours · Calculated 0s ago')
    expect(notice()).toBeNull()
  })

  it('stops asking once the board is there', async () => {
    stubFetch((url) => (url.includes('poll=1') ? served() : waiting()))
    mount(waiting())

    await advance(1000)
    expect(boardCalls()).toHaveLength(1)

    await advance(30_000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('does not poll a queue for a tab nobody is looking at', async () => {
    mount(waiting())
    await advance(1000)
    expect(boardCalls()).toHaveLength(1)

    await act(async () => { visibility('hidden') })
    await advance(10_000)
    expect(boardCalls()).toHaveLength(1)

    // Back, and one ask at once: the board may well have been built while
    // the tab was away.
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls()[1]).toContain('poll=1')
  })

  it('opens no wait in a tab that was already hidden when it mounted', async () => {
    visibility('hidden')
    mount(waiting())

    await advance(30_000)
    expect(boardCalls()).toHaveLength(0)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)
  })

  it('admits it is taking long, offers the way out, and slows down', async () => {
    mount(waiting())

    await advance(35_000)

    expect(notice()).toHaveTextContent('Still calculating')
    expect(notice()).toHaveTextContent(/window or the feeds/)
    expect(retryButtons()).toHaveLength(1)

    // It keeps asking, at the slower rate rather than not at all.
    const asked = boardCalls().length
    await advance(5000)
    expect(boardCalls()).toHaveLength(asked + 1)
  })

  it('keeps its place in the back-off when the reader retries', async () => {
    mount(waiting())
    await advance(35_000)
    const asked = boardCalls().length

    await click(retryButtons()[0]!)
    await advance(0)
    expect(boardCalls()).toHaveLength(asked + 1)
    // The reader's own ask, not a poll: it is new demand.
    expect(boardCalls().at(-1)).not.toContain('poll=1')

    // Nothing at a second; the wait is still on its five.
    await advance(1200)
    expect(boardCalls()).toHaveLength(asked + 1)
    await advance(3800)
    expect(boardCalls()).toHaveLength(asked + 2)
  })

  it('names the new window, and drops the answer to the question the reader has left', async () => {
    // The wait is where a reader is most likely to change their mind, and an
    // abort cannot unsend a response that is already on its way. Old rows
    // under a new window's label is the exact failure being tested.
    let landLate!: (board: BoardPayload) => void
    const late = new Promise<BoardPayload>((resolve) => { landLate = resolve })
    stubFetch((url) => (url.includes('window=12')
      ? waiting({ window_hours: 12 })
      : late))
    mount(waiting(), '#chatter')

    await advance(1000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('window=4')

    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)

    expect(boardCalls().at(-1)).toContain('window=12')
    expect(boardCalls().at(-1)).not.toContain('poll=1')
    expect(contextLine()).toHaveTextContent('last 12 hours')
    expect(notice()).toHaveTextContent('Calculating this board')

    landLate(served({ window_hours: 4, rows: [row({ ticker: 'OLD' })] }))
    await advance(50)

    expect(listed()).toEqual([])
    expect(screen.queryByText('OLD')).toBeNull()
    expect(contextLine()).toHaveTextContent('last 12 hours')
    expect(notice()).toHaveTextContent('Calculating this board')

    // And the wait that belonged to the old window is over: nothing asks
    // about four hours, however long the new one takes.
    await advance(20_000)
    expect(boardCalls().filter((url) => url.includes('window=4')))
      .toHaveLength(1)
    expect(boardCalls().filter((url) => url.includes('window=12')).length)
      .toBeGreaterThan(1)
  })

  it('starts the wait over when the reader asks a different question', async () => {
    stubFetch((url) => waiting({
      window_hours: url.includes('window=12') ? 12 : 4 }))
    mount(waiting(), '#chatter')
    await advance(35_000)
    expect(notice()).toHaveTextContent('Still calculating')

    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)

    expect(notice()).toHaveTextContent('Calculating this board')
    expect(notice()).not.toHaveTextContent('Still calculating')
  })
})

describe('a new selection while the last one is on screen', () => {
  it('shows it loading rather than the previous board under the new filters', async () => {
    stubFetch((url) => (url.includes('window=12') ? never() : served()))
    mount(served(), '#chatter')
    expect(listed()).toEqual(['AAA', 'BBB', 'CCC', 'DDD'])

    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)

    expect(listed()).toEqual([])
    expect(screen.getByText(/Loading human chatter/i)).toBeInTheDocument()
    // The controls stay where they were, set to what the reader just chose.
    expect(screen.getByLabelText(/window/i)).toHaveValue('12')
    // And nothing claims an age for a board that has not answered.
    expect(ageLine()).toBeNull()
  })
})

describe('a board that is busy with other selections', () => {
  it('says what is happening, keeps the controls, and slows down', async () => {
    stubFetch(() => busy())
    mount(busy(), '#chatter')

    expect(notice())
      .toHaveTextContent('The board is busy with other selections.')
    expect(retryButtons()).toHaveLength(1)
    expect(screen.getByLabelText(/window/i)).toBeInTheDocument()
    expect(listed()).toHaveLength(0)

    // Nothing is queued, so there is nothing to be near the front of: the
    // server asks for five seconds and the client does not undercut it.
    await advance(4000)
    expect(boardCalls()).toHaveLength(0)
    await advance(1000)
    expect(boardCalls()).toHaveLength(1)
    await advance(5000)
    expect(boardCalls()).toHaveLength(2)
  })

  it('joins the request already out when the reader retries again', async () => {
    const sent: AbortSignal[] = []
    stubFetch((_url, init) => {
      if (init?.signal) sent.push(init.signal)
      return never()
    })
    mount(busy())

    await click(retryButtons()[0]!)
    await click(retryButtons()[0]!)
    await advance(0)

    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
    expect(sent[0]?.aborted).toBe(false)
    // Nor does the wait's own next ask go out beside it.
    await advance(6000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('holds to what the first read of a new selection said', async () => {
    // The old question's wait was on a one-second floor. The first read of
    // the new one is answered busy, and its five seconds are the latest word
    // there is.
    stubFetch((url) => (url.includes('window=12')
      ? busy({ window_hours: 12 }) : waiting()))
    mount(waiting(), '#chatter')

    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')

    await advance(4900)
    expect(boardCalls()).toHaveLength(1)
    await advance(100)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls()[1]).toContain('poll=1')
  })
})

describe('a board whose rebuilds are failing', () => {
  it('says so plainly when there is no board underneath it', async () => {
    const parked = waiting({ failed: true, retry_after_ms: 5000 })
    stubFetch(() => parked)
    mount(parked, '#chatter')

    expect(notice()).toHaveTextContent(/could not be built/i)
    expect(notice()).toHaveTextContent(/still retrying/i)
    expect(retryButtons()).toHaveLength(1)
    expect(screen.queryByText(/Calculating this board/i)).toBeNull()
    expect(screen.queryByText(/No company cleared/i)).toBeNull()
  })

  it('keeps the rows it has and says the refresh failed', async () => {
    stubFetch(never)
    mount(served({ failed: true, age_seconds: 180 }), '#chatter')

    expect(listed()).toHaveLength(4)
    expect(ageLine()).toHaveTextContent('Calculated 3m ago · Last refresh failed')
    // A failure is not a queued refresh, and must not be quieted into one.
    expect(document.querySelector('.rh-age b.queued')).toBeNull()
  })
})

describe('a board with a refresh queued behind it', () => {
  const stale = (over: Partial<BoardPayload> = {}) => served({
    stale: true, age_seconds: 240, retry_after_ms: 5000, ...over,
  })

  it('shows its rows and says a fresher one is on the way', async () => {
    stubFetch(never)
    mount(stale(), '#chatter')

    expect(listed()).toHaveLength(4)
    expect(ageLine()).toHaveClass('stale')
    expect(ageLine()).toHaveTextContent('Calculated 4m ago · refreshing')
    expect(document.querySelector('.rh-age b.queued'))
      .toHaveTextContent('refreshing')
  })

  it('asks every five seconds until the refresh lands, and then stops', async () => {
    let fresh = false
    stubFetch(() => (fresh ? served() : stale()))
    mount(stale(), '#chatter')

    await advance(5000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')

    fresh = true
    await advance(5000)
    expect(boardCalls()).toHaveLength(2)
    await advance(1)
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    await advance(30_000)
    expect(boardCalls()).toHaveLength(2)
  })
})

describe('a board that goes stale while this page is holding it', () => {
  it('is plain at the bound and refreshing past it when the store serves it', async () => {
    stubFetch(never)
    mount(served({ age_seconds: 110 }), '#chatter')
    expect(ageLine()).toHaveTextContent('Calculated 1m ago')

    await advance(10_000)
    expect(ageLine()).not.toHaveClass('stale')
    expect(ageLine()?.textContent).toBe('Calculated 2m ago')
    expect(boardCalls()).toHaveLength(0)

    await advance(1100)
    expect(ageLine()).toHaveClass('stale')
    expect(document.querySelector('.rh-age b.queued'))
      .toHaveTextContent('refreshing')
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })

  it('is marked past the bound, says nothing is refreshing it, and asks only when told to, when a worker built it', async () => {
    // Ruling §5: between the fresh bound and the hard expiry a board may stay
    // on screen ONLY as stale, with no exception by path. A board a worker
    // built for itself has nothing behind it, and a request at the bound
    // would only build another synchronously -- so it is marked, the word
    // claims no refresh, and the request is the reader's button.
    stubFetch(never)
    mount(payload(), '#chatter')

    await advance(150_000)
    expect(boardCalls()).toHaveLength(0)
    expect(ageLine()).toHaveClass('stale')
    expect(ageLine()).toHaveTextContent('Calculated 2m ago · not refreshed')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    await click(ageLine()!.querySelector('button')!)
    await click(ageLine()!.querySelector('button')!)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
  })
})

describe('a board that has outlived the window it names', () => {
  it('is taken off the screen when the store has nothing newer', async () => {
    stubFetch(() => waiting())
    mount(served({ age_seconds: 599, hard_expiry_seconds: 600 }), '#chatter')
    expect(listed()).toHaveLength(4)

    await advance(1100)

    expect(listed()).toHaveLength(0)
    expect(notice()).toHaveTextContent('Calculating this board')
  })

  it('asks once when it expires while a poll is already out', async () => {
    // The wait's poll went out first and has not answered when the board
    // expires. That poll's answer IS the refetch; a second request beside it
    // would be two builds of one board.
    stubFetch(never)
    mount(served({ stale: true, age_seconds: 598.5, hard_expiry_seconds: 600,
                   retry_after_ms: 1000 }), '#chatter')

    await advance(2000)

    expect(ageLine()).toHaveClass('expired')
    expect(ageLine()).toHaveTextContent('Expired, recalculating')
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('poll=1')
  })

  it('says it expired while the replacement is on its way', async () => {
    stubFetch(never)
    mount(served({ age_seconds: 900, hard_expiry_seconds: 600 }), '#chatter')

    await advance(50)

    expect(ageLine()).toHaveClass('expired')
    expect(ageLine()).toHaveTextContent('Expired, recalculating')
    expect(boardCalls()).toHaveLength(1)
  })

  it('leaves a hidden tab asleep when a board a worker built expires', async () => {
    // Nothing waits behind a flag-off board, so its one refetch goes out
    // for a reader who is looking -- and a tab in the background owes it.
    stubFetch(() => payload())
    mount(payload({ age_seconds: 590 }), '#chatter')
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
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (
      url.includes('/api/board')
        ? { ok: false, redirected: false, status: 503, json: async () => ({}) }
        : ok(detail()))))
    mount(payload({ age_seconds: 599 }), '#chatter')

    await advance(1100)
    // Once: a refetch the page sends on its own is not retried behind the
    // reader's back.
    expect(boardCalls()).toHaveLength(1)
    expect(ageLine()).toHaveClass('expired')
    expect(ageLine()).toHaveTextContent('Expired')
    expect(ageLine()).not.toHaveTextContent('recalculating')
    // The page's notice says the refetch failed, and its Retry is the one on
    // offer.
    expect(screen.getByText(/Showing the last answer/i)).toBeInTheDocument()
    expect(retryButtons()).toHaveLength(1)

    // Nothing asks again on a timer...
    await advance(30_000)
    expect(boardCalls()).toHaveLength(1)
    // ...the reader coming back to the tab re-arms it...
    await act(async () => { visibility('hidden') })
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(2)
    // ...and so does the button.
    await click(retryButtons()[0]!)
    expect(boardCalls()).toHaveLength(3)
  })
})

describe('a board that is simply empty', () => {
  it('still says nothing cleared, with its age', async () => {
    mount(served({ rows: [], excluded: {} }), '#chatter')

    expect(screen.getByText(/No company cleared this selection/i))
      .toBeInTheDocument()
    expect(notice()).toBeNull()
    expect(ageLine()).toHaveTextContent('Calculated 0s ago')
  })
})

describe('a company opened while the board is still being built', () => {
  it('offers no mark it cannot state correctly', async () => {
    // A waiting shell's `watching: []` is a placeholder, not the account's
    // list. A Watch button drawn from it would call a marked company
    // unmarked.
    mount(waiting(), '#research/AAA')
    await advance(50)

    expect(screen.getByRole('heading', { name: 'Alpha Inc' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(Watch|✓ Watching)$/ }))
      .toBeNull()
  })
})

describe('a mark while the board is on screen', () => {
  it('keeps the board\'s age when the marks change under it', async () => {
    // The adopted list rewrites the cached board. It must not rewrite WHEN
    // the board arrived: the age line would jump back to the age it was sent
    // with, and the wait would lose its place.
    const marked = payload({ age_seconds: 30, watching: ['AAA'],
                             watch_rows: [row({ ticker: 'AAA' })] })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/watch/')) return ok({ watching: [] })
      if (url.includes('/api/board')) return never()
      return ok(detail())
    }))
    mount(marked, '#watching')

    await advance(40_000)
    expect(ageLine()).toHaveTextContent('Calculated 1m ago')

    await click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await advance(0)

    expect(screen.queryByText('Alpha Inc')).toBeNull()
    expect(ageLine()).toHaveTextContent('Calculated 1m ago')
  })

  it('refetches the board the reader is on, never the one they left', async () => {
    let answerMark!: (value: unknown) => void
    const held = new Promise((resolve) => { answerMark = resolve })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/watch/')) return held
      if (url.includes('/api/ticker/')) return ok(detail())
      if (url.includes('window=12')) return ok(waiting({ window_hours: 12 }))
      return ok(payload())
    }))
    mount(payload(), '#research/AAA')
    await advance(50)

    await click(screen.getByRole('button', { name: 'Watch' }))
    await click(screen.getByRole('button', { name: /back to the list/i }))
    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)
    const before = boardCalls().length

    answerMark(ok({ watching: ['AAA'] }))
    await advance(50)

    // One more ask, for the window on screen; nothing about four hours, and
    // nothing drawn from it.
    expect(boardCalls().slice(before).every((url) => url.includes('window=12')))
      .toBe(true)
    expect(contextLine()).toHaveTextContent('last 12 hours')
    expect(listed()).toEqual([])
  })
})

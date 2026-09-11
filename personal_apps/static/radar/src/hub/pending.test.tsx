// The board somebody else is building, as the hub shows it.
//
// The same states the old board island learned in Task 5, on the surface that
// reads them through react-query: a board that is not built yet, one that is
// being rebuilt behind the reader, a generation too busy to take the question,
// a key whose builds keep failing, and a board that has simply outlived the
// window it names. Each asks something different of the reader, and none of
// them is an empty board.

import {
  QueryClient, QueryClientProvider, onlineManager,
} from '@tanstack/react-query'
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

/** A board request that never answers, the way a real one ends: when the page
 *  stops waiting (its own 8 s timeout, or react-query leaving the key) and
 *  aborts it. `never` above ignores the abort, so it can never time out. */
const unanswered = (_url: string, init?: RequestInit) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => {
      reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    }, { once: true })
  })

/** Every board request answers with this status; the panels still answer. */
function answering(status: number) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => (
    url.includes('/api/board')
      ? { ok: false, redirected: false, status, json: async () => ({}) }
      : ok(detail()))))
}

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

  it.each(['#overview', '#watching'])(
    'names no control %s does not have when it admits the wait is long',
    async (hash) => {
      // The window and the feeds are Human chatter's. A hint naming them on
      // a page without them points the reader at nothing.
      mount(waiting(), hash)
      await advance(35_000)

      expect(notice()).toHaveTextContent('Still calculating')
      expect(notice()).toHaveTextContent('built from scratch')
      expect(notice()).not.toHaveTextContent(/window|feeds/)
      expect(retryButtons()).toHaveLength(1)
    })

  it.each(['#overview', '#watching'])(
    'names no control %s does not have when the board is busy',
    async (hash) => {
      stubFetch(() => busy())
      mount(busy(), hash)

      expect(notice()).toHaveTextContent('other readers asked for first')
      expect(notice()).not.toHaveTextContent(/window|feeds/)
    })

  it('admits it is taking long, offers the way out, and slows down', async () => {
    mount(waiting(), '#chatter')

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

  it('resends a Retry the server failed as the reader\'s own ask, never as a poll', async () => {
    // One rule for poll=1: the page asking again, on its own schedule, about
    // a board it is waiting for. react-query resending the reader's request
    // is that request again, not the wait's.
    let down = false
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (!url.includes('/api/board')) return ok(detail())
      return down
        ? { ok: false, redirected: false, status: 503, json: async () => ({}) }
        : ok(waiting())
    }))
    mount(waiting())
    await advance(35_000)
    const asked = boardCalls().length

    down = true
    await click(retryButtons()[0]!)
    await advance(3500)

    const since = boardCalls().slice(asked)
    // The Retry, and the two resends a server error earns the reader's own.
    expect(since).toHaveLength(3)
    expect(since.filter((url) => url.includes('poll=1'))).toEqual([])
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

  it('says so in the waiting notice once its polls keep failing, and keeps asking', async () => {
    // Two in a row is not a blip. Saying nothing then leaves "Calculating
    // this board…" -- and after thirty seconds a diagnosis of the queue --
    // over a wait whose every ask is failing. The notice the reader is
    // reading says why and offers the page's one Retry while the wait goes
    // on asking; nothing claims a last answer, because a shell has none.
    let down = true
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (!url.includes('/api/board')) return ok(detail())
      return down
        ? { ok: false, redirected: false, status: 503, json: async () => ({}) }
        : ok(served())
    }))
    mount(waiting(), '#chatter')

    await advance(1000)
    await advance(1)
    expect(boardCalls()).toHaveLength(1)
    expect(notice()).not.toHaveTextContent('answered with an error')

    await advance(1500)
    await advance(1)
    expect(boardCalls()).toHaveLength(2)
    expect(notice()).toHaveTextContent('Calculating this board')
    expect(notice())
      .toHaveTextContent('The board answered with an error. Still trying.')
    expect(retryButtons()).toHaveLength(1)
    expect(screen.queryByText(/Showing the last answer/i)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()

    await advance(2000)
    expect(boardCalls()).toHaveLength(3)
    expect(notice()).toHaveTextContent('Still trying.')

    // The next poll that answers takes all of it away.
    down = false
    await advance(3000)
    await advance(1)
    expect(boardCalls()).toHaveLength(4)
    expect(listed()).toHaveLength(4)
    expect(notice()).toBeNull()
  })

  it('says at once why the reader\'s own ask failed, in the same notice', async () => {
    answering(429)
    mount(busy(), '#chatter')

    await click(retryButtons()[0]!)
    await advance(1)

    expect(boardCalls()).toHaveLength(1)
    expect(notice()).toHaveTextContent('The board is busy with other selections.')
    expect(notice()).toHaveTextContent(
      'The board is rate-limiting requests. Give it a moment. Still trying.')
    expect(retryButtons()).toHaveLength(1)
    expect(screen.queryByText(/Showing the last answer/i)).toBeNull()
  })

  it('forgets the failures of a question the reader has left', async () => {
    // A new selection is a new wait, and one failed poll of it is a blip,
    // not the third in a row.
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (!url.includes('/api/board')) return ok(detail())
      if (url.includes('window=12') && !url.includes('poll=1')) {
        return ok(waiting({ window_hours: 12 }))
      }
      return { ok: false, redirected: false, status: 503, json: async () => ({}) }
    }))
    mount(waiting(), '#chatter')
    await advance(1000)
    await advance(1500)
    await advance(1)
    expect(notice()).toHaveTextContent('Still trying.')

    await choose(screen.getByLabelText(/window/i), '12')
    await advance(50)
    expect(notice()).toHaveTextContent('Calculating this board')
    expect(notice()).not.toHaveTextContent('Still trying.')

    await advance(1000)
    await advance(1)
    expect(boardCalls().filter((url) => url.includes('window=12')))
      .toHaveLength(2)
    expect(notice()).not.toHaveTextContent('Still trying.')
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

describe('the top bar while a new market loads', () => {
  it('names the market the reader chose, not the one they left', async () => {
    // The previous market's board is kept as placeholder data while the new
    // one loads. It says nothing about the market the reader is now on --
    // least of all whether that market is open.
    stubFetch((url) => (url.includes('market=de') ? never() : served()))
    mount(served(), '#chatter')
    const bar = () => document.querySelector('.rh-session')
    expect(bar()).toHaveTextContent('US markets · open')

    await choose(screen.getByLabelText(/market/i), 'de')
    await advance(50)

    expect(bar()).not.toHaveTextContent('US markets')
    expect(bar()).toHaveTextContent('Germany')
    expect(bar()).not.toHaveTextContent(/open|closed/)
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
    // claims no refresh, and the request is the reader's button. Its one
    // automatic read goes out a minute after it arrived, well inside the
    // bound; here that read times out, and is not sent again.
    stubFetch(unanswered)
    mount(payload(), '#chatter')

    await advance(150_000)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
    expect(ageLine()).toHaveClass('stale')
    expect(ageLine()).toHaveTextContent('Calculated 2m ago · not refreshed')
    expect(ageLine()).not.toHaveTextContent('refreshing')

    // The page's one Retry is the notice's, while it says why the read failed.
    expect(screen.getByText(/did not answer in time/i)).toBeInTheDocument()
    expect(retryButtons()).toHaveLength(1)
    await click(retryButtons()[0]!)
    await click(retryButtons()[0]!)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls()[1]).not.toContain('poll=1')
  })
})

describe('a board a worker built for itself, while the reader is looking', () => {
  // Nothing is queued behind it, so nothing refreshes it but this page --
  // which is what the hub always did: read its board again a minute after it
  // arrived, for a reader who is looking. Only ever inside the fresh bound: a
  // request at or past it would be an automatic synchronous build.
  it('reads it again a minute after it arrived, once, as a read', async () => {
    stubFetch(never)
    mount(payload(), '#chatter')

    await advance(59_999)
    expect(boardCalls()).toHaveLength(0)
    await advance(1)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')

    // One: nothing beside it while it is out, and nothing at the bound.
    await advance(90_000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('reads again a minute after each answer', async () => {
    stubFetch(() => payload())
    mount(payload(), '#chatter')

    await advance(60_000)
    expect(boardCalls()).toHaveLength(1)
    await advance(59_999)
    expect(boardCalls()).toHaveLength(1)
    await advance(1)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls().filter((url) => url.includes('poll=1'))).toEqual([])
  })

  it('asks nothing for a tab nobody is looking at', async () => {
    stubFetch(never)
    mount(payload(), '#chatter')
    await act(async () => { visibility('hidden') })

    await advance(150_000)
    expect(boardCalls()).toHaveLength(0)

    // Back past the bound: nothing then either. The line says so, and the
    // ask is the reader's.
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(0)
    expect(ageLine()).toHaveTextContent('Calculated 2m ago · not refreshed')
  })

  it('reads once when the reader comes back inside the bound', async () => {
    stubFetch(never)
    mount(payload(), '#chatter')
    await act(async () => { visibility('hidden') })
    await advance(90_000)
    expect(boardCalls()).toHaveLength(0)

    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')

    await advance(20_000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('keeps what a hidden tab owes through a request that fails', async () => {
    // Back at the tab while a request is already out, the page pays nothing
    // then: that request is the ask. But until it answers, the tab still
    // owes what it owed -- and when it is refused, the next look pays.
    let answerMark!: (value: unknown) => void
    const held = new Promise((resolve) => { answerMark = resolve })
    const refusals: Array<() => void> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/watch/')) return held
      if (url.includes('/api/board')) {
        return new Promise((resolve) => {
          refusals.push(() => resolve({ ok: false, redirected: false,
                                        status: 429, json: async () => ({}) }))
        })
      }
      return ok(detail())
    }))
    mount(payload({ watching: ['AAA'], watch_rows: [row({ ticker: 'AAA' })] }),
          '#watching')
    await click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await act(async () => { visibility('hidden') })
    // Its minute comes while nobody is looking: owed.
    await advance(70_000)
    expect(boardCalls()).toHaveLength(0)

    // The mark lands, and its refetch goes out from the hidden tab. (The
    // adopted list re-arms the minute's clock, which fires a fake tick
    // later.)
    answerMark(ok({ watching: [] }))
    await advance(1)
    expect(boardCalls()).toHaveLength(1)

    // Back while it is out: that request is the ask.
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(1)

    // Refused -- and the read is still owed, inside the bound.
    refusals[0]!()
    await advance(0)
    await act(async () => { visibility('hidden') })
    await act(async () => { visibility('visible') })
    await advance(0)
    expect(boardCalls()).toHaveLength(2)
    expect(boardCalls()[1]).not.toContain('poll=1')
  })

  it('asks nothing past its bound when the connection comes back', async () => {
    // A reconnect is not the reader asking: past the bound, the ask is theirs.
    stubFetch(never)
    mount(payload({ age_seconds: 300 }), '#chatter')
    await advance(61_000)

    await act(async () => { onlineManager.setOnline(false) })
    await act(async () => { onlineManager.setOnline(true) })
    await advance(0)

    expect(boardCalls()).toHaveLength(0)
  })

  it('sends nothing at or past its bound', async () => {
    // It arrived a minute old: the minute ends AT the bound, which is not
    // inside it.
    stubFetch(never)
    mount(payload({ age_seconds: 60 }), '#chatter')

    await advance(200_000)
    expect(boardCalls()).toHaveLength(0)
    expect(ageLine()).toHaveTextContent('Calculated 4m ago · not refreshed')
  })
})

describe('a request the server did not answer, or refused as busy', () => {
  // Never sent again behind the reader's back, whoever asked for it. A
  // request that timed out may still be building its board -- on the path
  // where a worker builds its own, synchronously -- and a resend is a second
  // build of the same board; a 429 is the server's own rate limit, and a
  // resend a second later is exactly what it refused.
  it('sends a Retry that timed out once', async () => {
    stubFetch(unanswered)
    mount(payload({ age_seconds: 300 }), '#chatter')

    await click(ageLine()!.querySelector('button')!)
    await advance(10_000)

    expect(boardCalls()).toHaveLength(1)
    expect(screen.getByText(/did not answer in time/i)).toBeInTheDocument()
  })

  it('sends a Retry the server refused as busy once', async () => {
    answering(429)
    mount(payload({ age_seconds: 300 }), '#chatter')

    await click(ageLine()!.querySelector('button')!)
    await advance(10_000)

    expect(boardCalls()).toHaveLength(1)
    expect(screen.getByText(/rate-limiting/i)).toBeInTheDocument()
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

  it('keeps saying the refresh failed when a mark lands', async () => {
    // The adopted list rewrites the cached board. It must not rewrite the
    // failure beside it: the notice would go, and an expired board whose
    // refetch failed would claim a recalculation nothing had asked for.
    let down = true
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/watch/')) return ok({ watching: [] })
      if (url.includes('/api/board')) {
        return down
          ? { ok: false, redirected: false, status: 503, json: async () => ({}) }
          : never()
      }
      return ok(detail())
    }))
    mount(payload({ age_seconds: 599, watching: ['AAA'],
                    watch_rows: [row({ ticker: 'AAA' })] }), '#watching')
    await advance(1100)
    expect(screen.getByText(/Showing the last answer/i)).toBeInTheDocument()
    expect(ageLine()).toHaveTextContent('Expired')
    expect(ageLine()).not.toHaveTextContent('recalculating')

    // The mark's own refetch stays out: the failure it follows is the latest
    // word on this board until it answers.
    down = false
    await click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await advance(0)

    expect(screen.getByText(/Showing the last answer/i)).toBeInTheDocument()
    expect(retryButtons()).toHaveLength(1)
  })

  it('asks after a mark as the reader, never as a poll, while a refresh is queued', async () => {
    // The refetch a mark is owed is the reader's own ask, as a Retry is --
    // new demand for the board, which the server counts. poll=1 is only
    // ever the page asking again on its own schedule.
    const marked = served({ stale: true, age_seconds: 240, retry_after_ms: 5000,
                            watching: ['AAA'],
                            watch_rows: [row({ ticker: 'AAA' })] })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/watch/')) return ok({ watching: [] })
      if (url.includes('/api/board')) return never()
      return ok(detail())
    }))
    mount(marked, '#watching')

    await click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await advance(0)

    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).not.toContain('poll=1')
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

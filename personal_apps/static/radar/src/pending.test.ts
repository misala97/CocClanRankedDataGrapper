// The wait, as arithmetic. Everything the surface does while a board is being
// built somewhere else is decided here, and it is decided without a DOM: how
// soon to ask again, when to stop asking, and which answers still belong to
// the question that is on screen.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { payload } from './fixtures'
import { DELAYED_AFTER_MS, Poller, ageAt, nextDelay, pastFresh, readAge,
         refreshes, untilExpired, untilStale } from './pending'

describe('what the age line says about a board', () => {
  // One reading for both surfaces' lines (list/ListPane.tsx,
  // hub/PageState.tsx), each printed in its own markup.
  const at = Date.parse('2026-08-22T19:00:00Z')

  it('reads a fresh board as its age alone', () => {
    expect(readAge(payload({ age_seconds: 30 }), at, at + 10_000))
      .toEqual({ expired: false, seconds: 40, stale: false, note: null })
  })

  it('says what is done about a board past its bound, by who built it', () => {
    expect(readAge(payload({ shared: true, age_seconds: 130 }), at, at))
      .toMatchObject({ stale: true, note: 'refreshing' })
    expect(readAge(payload({ shared: false, age_seconds: 130 }), at, at))
      .toMatchObject({ stale: true, note: 'not refreshed' })
    // A failing queue in place of "refreshing", never beside it.
    expect(readAge(payload({ shared: true, stale: true, failed: true,
                             age_seconds: 130 }), at, at))
      .toMatchObject({ stale: true, note: 'failed' })
  })

  it('stops printing an age past the hard expiry, and has none for a shell', () => {
    expect(readAge(payload({ age_seconds: 601 }), at, at))
      .toEqual({ expired: true })
    expect(readAge(payload({ rows: null, age_seconds: null,
                             generated_at: null }), at, at)).toBeNull()
  })
})

/** The jitter, taken out. The spread only ever adds, so its bottom is the
 *  number the schedule -- or the server's floor -- actually names. */
const NO_SPREAD = () => 0

describe('how soon to ask again', () => {
  it('walks the schedule while the wait is still young', () => {
    const walk = [0, 1, 2, 3, 4, 5].map(
      (attempt) => nextDelay(attempt, 0, null, NO_SPREAD))

    expect(walk).toEqual([1000, 1500, 2000, 3000, 3000, 3000])
  })

  it('settles at five seconds once the reader has waited half a minute', () => {
    // Not a punishment for waiting: past thirty seconds the answer is
    // dominated by whatever the producer is doing, and a three-second poll
    // only adds requests to a queue that is already the bottleneck.
    expect(nextDelay(0, DELAYED_AFTER_MS, null, NO_SPREAD)).toBe(5000)
    expect(nextDelay(9, 45_000, null, NO_SPREAD)).toBe(5000)
    expect(nextDelay(9, DELAYED_AFTER_MS - 1, null, NO_SPREAD)).toBe(3000)
  })

  it('never asks sooner than the server said to', () => {
    // `retry_after_ms` is the server's own read of the queue -- twelfth in
    // line is a longer wait than the schedule can know about.
    expect(nextDelay(0, 0, 5000, NO_SPREAD)).toBe(5000)
    // Below the schedule it is not a ceiling: the client's own back-off wins.
    expect(nextDelay(3, 0, 1000, NO_SPREAD)).toBe(3000)
  })

  it('spreads every delay upward, so a crowd does not march', () => {
    // Twenty viewers admitted in the same second must not come back in the
    // same second. The spread is what turns one queue into a trickle.
    expect(nextDelay(0, 0, null, NO_SPREAD)).toBe(1000)
    expect(nextDelay(0, 0, null, () => 1)).toBe(1200)
    for (let i = 0; i < 200; i += 1) {
      const delay = nextDelay(1, 0, null)
      expect(delay).toBeGreaterThanOrEqual(1500)
      expect(delay).toBeLessThanOrEqual(1800)
    }
  })

  it('still spreads a crowd the server has put a floor under', () => {
    // The floor is exactly when a crowd is most in step: every client in a
    // refused generation was handed the same number in the same second.
    // Clamping after the jitter collapsed them all back onto it -- the one
    // case the spread exists for was the one case it did nothing in.
    expect(nextDelay(0, 0, 5000, () => 1)).toBe(6000)
    const delays = new Set<number>()
    for (let i = 0; i < 200; i += 1) {
      const delay = nextDelay(0, 0, 5000)
      expect(delay).toBeGreaterThanOrEqual(5000)
      expect(delay).toBeLessThanOrEqual(6000)
      delays.add(delay)
    }
    expect(delays.size).toBeGreaterThan(1)
  })
})

describe('the poller', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.spyOn(Math, 'random').mockReturnValue(0) })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('asks again on the schedule until it is stopped', async () => {
    const poller = new Poller()
    const ask = vi.fn()

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1500)
    expect(ask).toHaveBeenCalledTimes(2)

    poller.stop()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(ask).toHaveBeenCalledTimes(2)
  })

  it('takes the server\'s own retry floor from the answer', async () => {
    const poller = new Poller()
    const ask = vi.fn(async () => 5000)

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)
    // The schedule's second step is 1500ms; the answer said 5000.
    await vi.advanceTimersByTimeAsync(1500)
    expect(ask).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3500)
    expect(ask).toHaveBeenCalledTimes(2)
  })

  it('stops asking while the tab is hidden and asks at once when it is back', async () => {
    // A backgrounded tab polling a shared queue is load nobody is reading.
    const poller = new Poller()
    const ask = vi.fn()

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)

    poller.pause()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(ask).toHaveBeenCalledTimes(1)

    poller.resume()
    await vi.advanceTimersByTimeAsync(0)
    expect(ask).toHaveBeenCalledTimes(2)
    // And the schedule carries on from WHERE IT WAS rather than restarting:
    // half a minute of waiting has already happened, so the next ask is five
    // seconds out and emphatically not one.
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(4000)
    expect(ask).toHaveBeenCalledTimes(3)
  })

  it('comes back from a hidden tab as one chain, never two', async () => {
    // Hidden and shown again WHILE a poll is in flight. The poll that is
    // already out IS the ask a resume would make, and making it again leaves
    // two schedules running over the same shared queue for as long as the
    // wait lasts -- one more for every flick to another tab and back.
    const poller = new Poller()
    let settle!: (value: null) => void
    let held = true
    const ask = vi.fn(() => {
      if (!held) return Promise.resolve(null)
      held = false
      return new Promise<null>((resolve) => { settle = resolve })
    })

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)

    poller.pause()
    poller.resume()
    await vi.advanceTimersByTimeAsync(0)
    // Exactly the one ask in flight, and nothing scheduled beside it.
    expect(ask).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)

    settle(null)
    await vi.advanceTimersByTimeAsync(0)
    expect(ask).toHaveBeenCalledTimes(1)
    // One timer behind it, at the schedule's next step and not two of them.
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(1500)
    expect(ask).toHaveBeenCalledTimes(2)

    // 4500, 7500, 10500, 13500, 16500, 19500, 22500 -- one chain's worth of
    // the schedule, over twenty seconds a doubled one would spend twice.
    await vi.advanceTimersByTimeAsync(20_000)
    expect(ask).toHaveBeenCalledTimes(9)
  })

  it('drops an answer that belongs to a wait it has already left', async () => {
    // The reader changed the selection while a poll was in flight. That
    // answer describes the previous question, and scheduling the next poll
    // from it would run two schedules at once.
    const poller = new Poller()
    let settle!: (value: null) => void
    const slow = vi.fn(() => new Promise<null>((resolve) => { settle = resolve }))
    const fresh = vi.fn()

    poller.start(slow)
    await vi.advanceTimersByTimeAsync(1000)
    expect(slow).toHaveBeenCalledTimes(1)

    poller.start(fresh)
    settle(null)
    await vi.advanceTimersByTimeAsync(1000)

    expect(slow).toHaveBeenCalledTimes(1)
    expect(fresh).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1500)
    expect(slow).toHaveBeenCalledTimes(1)
    expect(fresh).toHaveBeenCalledTimes(2)
  })

  it('survives a throw rather than ending the wait on one bad answer', async () => {
    const poller = new Poller()
    const ask = vi.fn(async () => { throw new Error('offline') })

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1500)

    expect(ask).toHaveBeenCalledTimes(2)
    poller.stop()
  })

  it('asks at once when told to, as its own next ask', async () => {
    // A board passing its hard expiry is a reason to hear from the server
    // sooner than the schedule would. Asked through the wait, that is one
    // request and one chain: the step that was due is replaced, not doubled.
    const poller = new Poller()
    const ask = vi.fn()

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)

    poller.askNow()
    await vi.advanceTimersByTimeAsync(0)
    expect(ask).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(1)
    // The schedule's third step from here (2000ms), and nothing at 2500,
    // where the second step it replaced would have fallen.
    await vi.advanceTimersByTimeAsync(1999)
    expect(ask).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(ask).toHaveBeenCalledTimes(3)
    poller.stop()
  })

  it('never asks beside an ask already out, nor for a hidden tab', async () => {
    const poller = new Poller()
    let settle!: (value: null) => void
    const ask = vi.fn(() => new Promise<null>((resolve) => { settle = resolve }))

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)

    // Its answer is the one a second ask would have fetched.
    poller.askNow()
    await vi.advanceTimersByTimeAsync(0)
    expect(ask).toHaveBeenCalledTimes(1)

    settle(null)
    await vi.advanceTimersByTimeAsync(0)
    // Hidden, it waits to be looked at -- and then asks at once, as a
    // returning tab always does.
    poller.pause()
    poller.askNow()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(ask).toHaveBeenCalledTimes(1)
    poller.resume()
    expect(ask).toHaveBeenCalledTimes(2)
    poller.stop()
  })

  it('keeps the server\'s floor through an answer that had nothing to say', async () => {
    // An ask the reader's Retry aborted answers nothing at all. That is no
    // reason to forget what the server said the time before: dropping the
    // floor put the next ask on the schedule's own step, under a server that
    // had asked for five seconds.
    const poller = new Poller()
    const said: (number | null)[] = [5000, null]
    const ask = vi.fn(async () => said.shift() ?? null)

    poller.start(ask)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(5000)
    expect(ask).toHaveBeenCalledTimes(2)

    // The second answer said nothing; the first one's floor stands.
    await vi.advanceTimersByTimeAsync(4999)
    expect(ask).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(ask).toHaveBeenCalledTimes(3)
    poller.stop()
  })

  it('takes a floor from an answer it did not ask for itself', async () => {
    // A Retry, or the first read of a new selection, is answered by the same
    // queue this wait is asking. When that answer says "not for five
    // seconds", the ask already on the timer must not go out after one and a
    // half -- and five seconds are counted from the answer that said so.
    const poller = new Poller()
    const ask = vi.fn(async () => 1000)

    poller.start(ask, 1000)
    await vi.advanceTimersByTimeAsync(1000)
    expect(ask).toHaveBeenCalledTimes(1)

    // Due at 2500 on the schedule; a busy answer lands at 1200.
    await vi.advanceTimersByTimeAsync(200)
    poller.guide(5000)
    await vi.advanceTimersByTimeAsync(4999)
    expect(ask).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(ask).toHaveBeenCalledTimes(2)
    poller.stop()
  })
})

describe('how long a board on screen stays good', () => {
  const at = Date.parse('2026-08-22T19:00:00Z')

  it('adds the time this page has held a board to the age it was sent with', () => {
    const board = payload({ shared: true, age_seconds: 30 })

    expect(ageAt(board, at, at)).toBe(30)
    expect(ageAt(board, at, at + 90_000)).toBe(120)
  })

  it('dates a document that carries no age by its build stamp', () => {
    // Cached from before the envelope: the stamp is all there is.
    const board = payload({ age_seconds: null,
                            generated_at: '2026-08-22T18:57:00Z' })

    expect(ageAt(board, at, at)).toBe(180)
  })

  it.each([true, false])(
    'calls a board stale strictly past its bound, as the server does (shared: %s)',
    (shared) => {
      // board_shared.disposition: a board exactly `fresh_seconds` old is
      // still fresh. The page's clock reads the same boundary the same way,
      // on both paths -- the bound is the ruling's, not the store's.
      const board = payload({ shared, age_seconds: 110, fresh_seconds: 120 })

      expect(untilStale(board, at, at)).toBe(10_000)
      expect(pastFresh(board, at, at + 10_000)).toBe(false)
      expect(pastFresh(board, at, at + 10_001)).toBe(true)
    })

  it('marks a board stale whoever built it, and waits only on the store', () => {
    // Ruling §5: between the fresh bound and the hard expiry a board may stay
    // on screen ONLY as stale, with no exception by path -- and the flag-off
    // path is production until the flag flips. What a board a worker built
    // for itself lacks is anything behind it: nothing is queued to refresh
    // it, and asking again would build another. Marked, never waited on.
    const direct = payload({ shared: false, age_seconds: 500,
                             fresh_seconds: 120 })

    expect(untilStale(direct, at, at)).toBe(-380_000)
    expect(pastFresh(direct, at, at)).toBe(true)
    expect(refreshes(direct)).toBe(false)
    expect(refreshes(payload({ shared: true }))).toBe(true)
    // The hard expiry is every board's: past it the window has moved on.
    expect(untilExpired(direct, at, at)).toBe(100_000)
  })

  it('has nothing to say about a board nobody has built yet', () => {
    const shell = payload({ shared: true, pending: true, rows: null,
                            age_seconds: null, generated_at: null })

    expect(ageAt(shell, at, at)).toBeNull()
    expect(untilStale(shell, at, at)).toBeNull()
    expect(untilExpired(shell, at, at)).toBeNull()
  })
})

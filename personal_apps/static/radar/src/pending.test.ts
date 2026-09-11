// The wait, as arithmetic. Everything the surface does while a board is being
// built somewhere else is decided here, and it is decided without a DOM: how
// soon to ask again, when to stop asking, and which answers still belong to
// the question that is on screen.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DELAYED_AFTER_MS, Poller, nextDelay } from './pending'

/** The jitter, taken out. Half of a symmetric spread is the spread's middle,
 *  so every schedule value below is the number the schedule actually names. */
const MIDDLE = () => 0.5

describe('how soon to ask again', () => {
  it('walks the schedule while the wait is still young', () => {
    const walk = [0, 1, 2, 3, 4, 5].map(
      (attempt) => nextDelay(attempt, 0, null, MIDDLE))

    expect(walk).toEqual([1000, 1500, 2000, 3000, 3000, 3000])
  })

  it('settles at five seconds once the reader has waited half a minute', () => {
    // Not a punishment for waiting: past thirty seconds the answer is
    // dominated by whatever the producer is doing, and a three-second poll
    // only adds requests to a queue that is already the bottleneck.
    expect(nextDelay(0, DELAYED_AFTER_MS, null, MIDDLE)).toBe(5000)
    expect(nextDelay(9, 45_000, null, MIDDLE)).toBe(5000)
    expect(nextDelay(9, DELAYED_AFTER_MS - 1, null, MIDDLE)).toBe(3000)
  })

  it('never asks sooner than the server said to', () => {
    // `retry_after_ms` is the server's own read of the queue -- twelfth in
    // line is a longer wait than the schedule can know about.
    expect(nextDelay(0, 0, 5000, MIDDLE)).toBe(5000)
    expect(nextDelay(0, 0, 5000, () => 0)).toBe(5000)
    // Below the schedule it is not a ceiling: the client's own back-off wins.
    expect(nextDelay(3, 0, 1000, MIDDLE)).toBe(3000)
  })

  it('spreads every delay by a fifth either way, so a crowd does not march', () => {
    // Twenty viewers admitted in the same second must not come back in the
    // same second. The spread is what turns one queue into a trickle.
    expect(nextDelay(0, 0, null, () => 0)).toBe(800)
    expect(nextDelay(0, 0, null, () => 1)).toBe(1200)
    for (let i = 0; i < 200; i += 1) {
      const delay = nextDelay(1, 0, null)
      expect(delay).toBeGreaterThanOrEqual(1200)
      expect(delay).toBeLessThanOrEqual(1800)
    }
  })
})

describe('the poller', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.spyOn(Math, 'random').mockReturnValue(0.5) })
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
    // And the schedule carries on from there rather than stopping.
    await vi.advanceTimersByTimeAsync(5000)
    expect(ask).toHaveBeenCalledTimes(3)
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
})

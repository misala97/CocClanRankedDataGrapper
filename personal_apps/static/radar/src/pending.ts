// How often to ask about a board somebody else is building.
//
// The shared result means a reader can be told "not yet". What that costs is
// a decision this file owns: too eager and every waiting tab is load on the
// queue it is waiting for, too lazy and the board sits built for five seconds
// before anyone sees it. The answer is a short schedule that opens fast and
// gives up its urgency quickly, a floor the SERVER sets because it is the
// only party that can see the queue, and jitter so that twenty viewers
// admitted in the same second do not come back in the same second.
//
// Nothing here touches the DOM or React. The wait is arithmetic plus a
// timer, and both are testable without rendering anything.

/** The client's own back-off, in milliseconds, by attempt.
 *
 *  It opens at a second because the common miss is a board that is about to
 *  exist -- the producer is already on it -- and flattens at three because
 *  past that the wait is the producer's, not the poll interval's. */
const SCHEDULE = [1000, 1500, 2000, 3000]

/** When a wait stops being a moment and becomes a background task.
 *
 *  Also what the surface reads to change what it says: thirty seconds is
 *  where "calculating" stops being reassuring and the reader deserves both
 *  an admission and a way out. */
export const DELAYED_AFTER_MS = 30_000

/** The rate a long wait settles at. The same figure the server sends for a
 *  key that is backing off or a generation that is refusing work, so a client
 *  that has been waiting a while and a server that is busy agree. */
export const SLOW_MS = 5000

/** A fifth either way. Enough to spread a crowd admitted together across a
 *  couple of seconds, small enough that the schedule still means what it
 *  says. */
const JITTER = 0.2

/** How long to wait before asking again.
 *
 *  `retryAfterMs` is a FLOOR and never a ceiling: the server knows the queue
 *  -- twelfth in line is a longer wait than any client-side schedule can
 *  guess -- while the client knows how long this particular reader has been
 *  looking at a spinner. Whichever asks for more patience wins.
 *
 *  `random` is a parameter so the schedule can be read back in a test as the
 *  numbers it names, rather than as a range.
 */
export function nextDelay(attempt: number, waitedMs: number,
                          retryAfterMs: number | null,
                          random: () => number = Math.random): number {
  const step = waitedMs >= DELAYED_AFTER_MS ? SLOW_MS
    : SCHEDULE[Math.min(Math.max(attempt, 0), SCHEDULE.length - 1)] ?? SLOW_MS
  const spread = 1 - JITTER + 2 * JITTER * random()
  // Clamped after the jitter, not before: jittering a floor downwards would
  // undercut the very number the server sent to protect the queue.
  return Math.max(Math.round(step * spread), retryAfterMs ?? 0)
}

/** What one poll does. A number it returns is the server's own
 *  `retry_after_ms` for the answer that just arrived, and becomes the floor
 *  for the next delay; anything else means there was nothing to go on. */
export type PollFn = () =>
  number | null | void | Promise<number | null | void>

/** A repeating ask, with the four things a repeating ask needs.
 *
 *  The generation counter is the load-bearing part. A poll is in flight for
 *  most of the interval between two of them, and the reader is free to change
 *  the selection in exactly that window -- so an answer can arrive describing
 *  a question nobody is asking any more. Every start (and every stop) moves
 *  the generation, and an answer stamped with an older one is dropped rather
 *  than allowed to schedule the next poll: two schedules running at once is
 *  how a board ends up being asked for twice a second.
 */
export class Poller {
  private generation = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private fn: PollFn | null = null
  private attempt = 0
  private since = 0
  private floor: number | null = null
  private paused = false

  /** Whether a wait is in progress. */
  get running(): boolean {
    return this.fn !== null
  }

  /** Begin a wait. Any wait already in progress is abandoned, answers and
   *  all -- this is a new question.
   *
   *  `retryAfterMs` is the floor from the answer that started the wait. It is
   *  passed in rather than learned from the first poll, because the answer
   *  that put the surface into this state already said how long to leave it:
   *  a `busy` generation asks for five seconds and being asked again after
   *  one is exactly what it was refusing. */
  start(fn: PollFn, retryAfterMs: number | null = null): void {
    this.generation += 1
    this.clear()
    this.fn = fn
    this.attempt = 0
    this.since = Date.now()
    this.floor = retryAfterMs
    this.paused = false
    this.schedule(this.generation)
  }

  /** The board arrived, or the page is going away. */
  stop(): void {
    this.generation += 1
    this.clear()
    this.fn = null
    this.paused = false
  }

  /** The tab is hidden. Polling a shared queue on behalf of nobody is load
   *  with no reader at the end of it. */
  pause(): void {
    if (this.fn === null || this.paused) return
    this.paused = true
    this.clear()
  }

  /** The tab is back. One ask immediately -- the board may well have been
   *  built while the tab was away -- and then the schedule as before. */
  resume(): void {
    if (this.fn === null || !this.paused) return
    this.paused = false
    void this.fire(this.generation)
  }

  private clear(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }

  private schedule(generation: number): void {
    if (generation !== this.generation || this.paused || this.fn === null) return
    this.timer = setTimeout(() => { void this.fire(generation) },
                            nextDelay(this.attempt, Date.now() - this.since,
                                      this.floor))
  }

  private async fire(generation: number): Promise<void> {
    if (generation !== this.generation || this.fn === null) return
    this.timer = null
    this.attempt += 1
    let answer: number | null | void = null
    try {
      answer = await this.fn()
    } catch {
      // One unreachable answer is not the end of the wait. The schedule is
      // the back-off; a throw simply has no retry floor to offer.
      answer = null
    }
    if (generation !== this.generation) return
    this.floor = typeof answer === 'number' ? answer : null
    this.schedule(generation)
  }
}

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
// timer, and so is how long a board on screen stays good; all of it is
// testable without rendering anything.

import type { BoardPayload } from './types'

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

/** How long a burst of control changes has to go quiet before one request
 *  goes out for all of them.
 *
 *  Here rather than in one surface, because both of them need it and a second
 *  number would be a second thing to reason about. Five quick toggles used to
 *  queue five builds on the old board, the fifth waiting past the 8 s timeout
 *  (critique, 2026-09-01); the hub was then measured sending one request per
 *  change where the old board sent one for six (browser check 2), and every
 *  one of those is an admitted build occupying the queue another reader
 *  needs. Short enough that a single click still feels immediate. */
export const SETTLE_MS = 250

/** A fifth, upward. Enough to spread a crowd admitted together across a
 *  couple of seconds, small enough that the schedule still means what it
 *  says -- and one-sided, so the spread can be applied to a number that is a
 *  floor without ever going under it. */
const JITTER = 0.2

/** How long to wait before asking again.
 *
 *  `retryAfterMs` is a FLOOR and never a ceiling: the server knows the queue
 *  -- twelfth in line is a longer wait than any client-side schedule can
 *  guess -- while the client knows how long this particular reader has been
 *  looking at a spinner. Whichever asks for more patience wins, and the
 *  spread then applies to the winner.
 *
 *  `random` is a parameter so the schedule can be read back in a test as the
 *  numbers it names, rather than as a range.
 */
export function nextDelay(attempt: number, waitedMs: number,
                          retryAfterMs: number | null,
                          random: () => number = Math.random): number {
  const step = waitedMs >= DELAYED_AFTER_MS ? SLOW_MS
    : SCHEDULE[Math.min(Math.max(attempt, 0), SCHEDULE.length - 1)] ?? SLOW_MS
  // The floor first, then the spread over it. Clamping afterwards annihilated
  // the jitter in the one case it exists for: every client in a refused
  // generation is handed the same `retry_after_ms` in the same second, and a
  // Math.max against it collapsed all of them back onto that number exactly.
  // A one-sided spread is what lets both be true at once.
  const base = Math.max(step, retryAfterMs ?? 0)
  return Math.round(base * (1 + JITTER * random()))
}

/** What one poll does. A number it returns is the server's own
 *  `retry_after_ms` for the answer that just arrived, and becomes the floor
 *  for the next delay; anything else means that ask had nothing to go on --
 *  aborted, dropped, unreachable -- and the floor already in force stands. */
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
  // Whether an ask is out right now. A poll is in flight for most of the
  // interval between two of them, so it is the likeliest thing to be true
  // when anything else asks this object to act -- and an ask that is already
  // out is an ask, whatever prompted the second one.
  private inFlight = false

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
    this.inFlight = false
    this.schedule(this.generation)
  }

  /** The board arrived, or the page is going away. */
  stop(): void {
    this.generation += 1
    this.clear()
    this.fn = null
    this.paused = false
    this.inFlight = false
  }

  /** The tab is hidden. Polling a shared queue on behalf of nobody is load
   *  with no reader at the end of it. The schedule keeps its place. */
  pause(): void {
    if (this.fn === null || this.paused) return
    this.paused = true
    this.clear()
  }

  /** The tab is back. One ask immediately -- the board may well have been
   *  built while the tab was away -- and then the schedule as before.
   *
   *  Unless an ask is ALREADY out. A hide and a show during one in-flight
   *  poll used to fire a second ask here, and each of the two answers then
   *  scheduled a poll of its own: two chains over the same queue for as long
   *  as the wait lasted, and one more for every flick to another tab and
   *  back. The ask that is out re-schedules itself when it resolves, which
   *  is the one chain there is. */
  resume(): void {
    if (this.fn === null || !this.paused) return
    this.paused = false
    if (this.inFlight) return
    void this.fire(this.generation)
  }

  /** Ask now, as the wait's own next ask rather than beside it.
   *
   *  For the rest of the page, when it has a reason to hear from the server
   *  sooner than the schedule would -- a board passing its hard expiry is the
   *  one there is. Asking THROUGH the wait is what keeps that one request: an
   *  ask sent beside the wait's is two builds of one board, and whichever of
   *  the two went second aborted the other. The schedule then carries on from
   *  its place, as it does after any ask.
   *
   *  Nothing when an ask is already out, whose answer is the one this would
   *  have fetched, and nothing for a hidden tab, which asks the moment it is
   *  looked at again. */
  askNow(): void {
    if (this.fn === null || this.paused || this.inFlight) return
    this.clear()
    void this.fire(this.generation)
  }

  /** The server's floor, from an answer this wait did not ask for itself.
   *
   *  A Retry, the refetch after a mark, the first read of a new selection:
   *  each is answered by the same queue the wait is asking, and when that
   *  answer says "not for five seconds" the ask already on the timer must
   *  not go out after one and a half. The timer is set again from now,
   *  because the answer that named the floor is the latest word there is;
   *  the schedule itself keeps its place.
   *
   *  Nothing to go on keeps the floor in force. An ask that is out sets its
   *  timer when it answers, and a hidden tab asks the moment it is back --
   *  neither has a timer here to move. */
  guide(retryAfterMs: number | null): void {
    if (this.fn === null || typeof retryAfterMs !== 'number') return
    this.floor = retryAfterMs
    if (this.timer === null) return
    this.clear()
    this.schedule(this.generation)
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
    this.inFlight = true
    let answer: number | null | void = null
    try {
      answer = await this.fn()
    } catch {
      // One unreachable answer is not the end of the wait. The schedule is
      // the back-off; a throw simply has no retry floor to offer.
      answer = null
    } finally {
      // Only ever its own. A fire left over from a wait that has since been
      // stopped or restarted must not clear a flag that now describes the
      // ask the CURRENT wait has out.
      if (generation === this.generation) this.inFlight = false
    }
    if (generation !== this.generation) return
    // Only a number moves the floor. An ask that came back with nothing --
    // aborted by the reader's own Retry, dropped, unreachable -- learned
    // nothing about the queue, and zeroing the floor on its account put the
    // next ask on the schedule's own step under a server that had asked for
    // five seconds.
    if (typeof answer === 'number') this.floor = answer
    // Paused while this was out: the schedule declines, and resume() fires
    // then -- there is nothing in flight for it to defer to any more.
    this.schedule(generation)
  }
}

// --- how long a board on screen stays good ----------------------------------
//
// The server says how old a board was when it answered and how long a board
// is good for; only this page knows how long it has held one since. Every
// part of the surface that reads a board's age -- the line that prints it,
// the wait that goes to fetch a fresher one, the timer that takes an expired
// one down -- reads it from here, so the line can never say "refreshing"
// about a board nothing is going to fetch.

/** How old a board is at `now`, in seconds, on this page's clock.
 *
 *  The server's age plus the time this page has held the answer. Neither half
 *  is enough on its own: a stored board can be a minute old before it is ever
 *  sent, and a tab left open adds an afternoon to whatever it was sent as.
 *
 *  A document served before the envelope existed, and cached in a browser
 *  since, carries no age at all -- but it carries the build stamp the age
 *  used to be printed from, read against this machine's clock because there
 *  is no other. Null only when there is no board to be old: a waiting shell
 *  has neither, and inventing an age for it would be the freshness stamp's
 *  one unforgivable lie. */
export function ageAt(board: BoardPayload, received: number,
                      now: number = Date.now()): number | null {
  if (typeof board.age_seconds === 'number'
      && Number.isFinite(board.age_seconds)) {
    return board.age_seconds + Math.max(0, now - received) / 1000
  }
  if (board.generated_at) {
    const built = Date.parse(board.generated_at)
    if (Number.isFinite(built)) return Math.max(0, now - built) / 1000
  }
  return null
}

/** Milliseconds until a board on screen passes its fresh bound -- negative
 *  once it has -- or null for a board with no such bound to pass.
 *
 *  Every board with rows has one, whoever built it: ruling §5 lets a board
 *  between the fresh bound and the hard expiry stay on screen ONLY as stale,
 *  with no exception by path. `stale` is the store's verdict at the instant
 *  it answered, and this is the same verdict carried forward on the page's
 *  clock: a board past the bound looks that way here whether or not anything
 *  asked about it since. What is DONE about such a board is a different
 *  question, and `refreshes` answers it. */
export function untilStale(board: BoardPayload, received: number,
                           now: number = Date.now()): number | null {
  if (board.rows === null || !Number.isFinite(board.fresh_seconds)) return null
  const age = ageAt(board, received, now)
  return age === null ? null : (board.fresh_seconds - age) * 1000
}

/** Whether anything stands behind a board to refresh it.
 *
 *  A shared board has the store and its producer: past the fresh bound a
 *  refresh is queued, and waiting for it is the page's whole job. A board a
 *  worker built for itself has neither. Nothing is queued, and asking again
 *  builds another synchronously -- exactly the cost the shared store exists
 *  to take away -- so it is marked past the bound, says nothing is
 *  refreshing it, and is never asked about on a timer. */
export function refreshes(board: BoardPayload): boolean {
  return board.shared === true
}

/** Whether a board has outlived its fresh bound on this page's clock.
 *
 *  Strictly past, as the server reads it: a board exactly `fresh_seconds` old
 *  is still fresh (board_shared.disposition). */
export function pastFresh(board: BoardPayload, received: number,
                          now: number = Date.now()): boolean {
  const left = untilStale(board, received, now)
  return left !== null && left < 0
}

/** Whether a board on screen has a refresh coming that this page should wait
 *  for: one the store has queued (`stale`), or one the fresh bound has made
 *  due on this page's clock -- for a board with something behind it to do
 *  the refreshing. */
export function refreshDue(board: BoardPayload, received: number,
                           now: number = Date.now()): boolean {
  return board.stale || (refreshes(board) && pastFresh(board, received, now))
}

/** Milliseconds until a board passes its hard expiry -- negative once it has
 *  -- or null when it has no bound or no age to read one against.
 *
 *  Unlike the fresh bound this one is every board's: past it the rows
 *  describe a rolling window that has moved on, whoever built them. */
export function untilExpired(board: BoardPayload, received: number,
                             now: number = Date.now()): number | null {
  if (board.rows === null || !Number.isFinite(board.hard_expiry_seconds)) {
    return null
  }
  const age = ageAt(board, received, now)
  return age === null ? null : (board.hard_expiry_seconds - age) * 1000
}

/** What a board's age line says at `now`, decided once for both surfaces;
 *  each prints it in its own markup (list/ListPane.tsx, hub/PageState.tsx).
 *
 *  Read through the same functions the pages act on, so the line can neither
 *  claim a refresh the page is not waiting on nor deny one it is. */
export type AgeReading =
  /** Past the hard expiry: the rows describe a rolling window that has moved
   *  on, and the age has stopped being worth printing. */
  | { expired: true }
  | {
    expired: false
    /** How old the board is, in seconds, on this page's clock. */
    seconds: number
    /** Called stale by the store, or past its fresh bound on this page's
     *  clock -- whoever built it (ruling §5). */
    stale: boolean
    /** The word after the age, when there is one: the queue's rebuilds are
     *  failing, a refresh the page is waiting on, or nothing refreshing a
     *  board a worker built for itself. */
    note: 'failed' | 'refreshing' | 'not refreshed' | null
  }

/** The age line's reading of a board, or null for a board nobody has built:
 *  inventing an age for a waiting shell would be the freshness stamp's one
 *  unforgivable lie. */
export function readAge(board: BoardPayload, received: number,
                        now: number = Date.now()): AgeReading | null {
  const seconds = ageAt(board, received, now)
  if (seconds === null) return null
  const expiry = untilExpired(board, received, now)
  if (expiry !== null && expiry < 0) return { expired: true }
  const stale = board.stale || pastFresh(board, received, now)
  // `failed` is a verdict on the queue, not on these rows: they are the last
  // board that built. It stands in place of "refreshing", never beside it --
  // a refresh that is failing is not one that is happening.
  const note = board.failed ? 'failed'
    : !stale ? null
    : refreshDue(board, received, now) ? 'refreshing'
    : 'not refreshed'
  return { expired: false, seconds, stale, note }
}

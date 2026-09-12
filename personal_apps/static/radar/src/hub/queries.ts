// Shared server state for the hub.
//
// One cache for the whole page, so Overview, Human chatter and Watching read
// the same board rather than each fetching one -- three views of one answer,
// which is also why they can never disagree with each other on screen.
//
// The keys are the load-bearing part. A key that held only the market would
// serve a reader the board built for a different window, sort or source set:
// silently, and only sometimes. Every dimension the server filters on is in
// the key, and the panel's key carries the listing context that opened it,
// because its breakdown and posts describe the same window the row's phrase
// did.
import {
  keepPreviousData, useMutation, useQuery, useQueryClient,
} from '@tanstack/react-query'
import type { QueryClient, UseQueryResult } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchBoard, fetchDetail, fetchSearch, queryFor, setWatch } from '../api'
import {
  DELAYED_AFTER_MS, SETTLE_MS, SLOW_MS, nextDelay, refreshDue, refreshes,
  untilExpired, untilStale,
} from '../pending'
import type { BoardPayload, PanelSpan, Selection } from '../types'

/** Every hub key starts here, so the hub and the old board island can share a
 *  browser tab without sharing a cache entry. */
const ROOT = 'radar-hub'

/** Panels are refreshed while their page is on screen, and only then. A
 *  hidden tab polling a dashboard nobody is reading is a request the reader
 *  did not ask for.
 *
 *  The board carries bounds of its own as well (ruling §5). A shared board
 *  is not read on this clock: it is asked about again from the moment it
 *  passes its fresh bound, as a wait. A board a worker built for itself is
 *  read on it -- once per answer, for a reader who is looking, as the hub
 *  always read its board -- and only while that read falls inside the fresh
 *  bound (`refreshAt`): at or past it, asking again would build another
 *  synchronously, in every open tab, and the ask is the reader's. The figure
 *  is also how long a cached answer counts as current when the reader comes
 *  back to its selection. */
export const REFRESH_MS = 60_000

export const boardKey = (s: Selection) => [ROOT, 'board', queryFor(s)] as const

export const detailKey = (ticker: string, s: Selection, span: PanelSpan) =>
  [ROOT, 'detail', ticker, s.market, s.sources.join(','), s.window, span] as const

export const searchKey = (q: string) => [ROOT, 'search', q.trim()] as const

const WARM_DISCOVER = ['discover', 'mid', 'micro', 'unknown'] as const

/** The hub's one reader-facing alias. The URL and control keep the concise
 * Discover spelling; only the backend question uses its existing warm key. */
export function requestSelection(selection: Selection): Selection {
  if (selection.segments.length !== 1 || selection.segments[0] !== 'discover') {
    return selection
  }
  return { ...selection, segments: [...WARM_DISCOVER] }
}

/** The Selection a board payload was built for, from the server's own echo.
 *
 *  Read from the echo rather than from the URL: the server has already parsed
 *  and validated it, and a second parser would be free to disagree.
 */
export function selectionOf(payload: BoardPayload): Selection {
  return {
    market: payload.market,
    sources: payload.sources,
    segments: payload.segments,
    minVenues: payload.min_venues,
    window: payload.window_hours,
    sort: payload.sort,
    dir: payload.dir,
  }
}

/** Permanent for this attempt: retrying spends the reader's time on the same
 *  answer. A forbidden endpoint will not become allowed, an expired session
 *  will not revive, and a ticker the server does not have will not appear. */
const PERMANENT = new Set(['session', 'forbidden', 'missing'])

function retry(count: number, error: unknown): boolean {
  const reason = (error as { reason?: string })?.reason
  if (reason !== undefined && PERMANENT.has(reason)) return false
  return count < 2
}

// --- the wait -----------------------------------------------------------------
//
// The same arithmetic the old board's Poller runs (../pending.ts), held where
// react-query can read it. react-query owns the timer: `refetchInterval` is
// read again after every answer and every render, and re-armed from the moment
// it is read. So what it reads has to be a DEADLINE -- when the next ask is
// due -- and never a delay counted from whenever it happens to be asked: a
// page that drew itself every second would otherwise slide its own poll out
// of reach for as long as it was on screen.

/** Where one wait for a board stands. */
export interface Wait {
  /** The selection it is for, as `queryFor` writes it. A new selection is a
   *  new question, and a new wait. */
  key: string
  /** When it began: the first answer that owed a board, or the moment a
   *  shared board passed its fresh bound on this page's clock. What "the
   *  reader has been waiting half a minute" is counted from. */
  since: number
  /** How many times it has asked on its own. A Retry is an extra ask, not a
   *  step: a reader who presses it half a minute in is not put back on the
   *  schedule's opening second. */
  attempt: number
  /** The server's floor under the next ask, from the last answer that named
   *  one. An answer that named nothing -- failed, dropped -- leaves it. */
  floor: number | null
  /** When the last word about this board arrived: an answer, whoever asked
   *  for it, or a failure. The next ask is timed from here. */
  anchor: number
  /** That answer's share of the spread, drawn once so every reading of the
   *  schedule between two answers names the same instant. */
  spread: number
}

/** Whether a board on screen has something coming that this page should go
 *  and get: one being built, a generation that asked to be asked again, or a
 *  refresh the store has queued or the fresh bound has made due. The same
 *  rule the old board's `owesABoard` reads, at any instant rather than only
 *  at the one it arrived. */
export function owesABoard(board: BoardPayload, received: number,
                           now: number): boolean {
  return board.pending || board.busy || refreshDue(board, received, now)
}

/** A wait begun now, on the floor of the answer that started it -- the busy
 *  generation's five seconds, the queue's one -- or on none, for a shared
 *  board that has only just passed its bound. */
export function beginWait(key: string, board: BoardPayload, now: number,
                          random: () => number = Math.random): Wait {
  return { key, since: now, attempt: 0, floor: board.retry_after_ms,
           anchor: now, spread: random() }
}

/** An answer landed while the wait was running, or a request failed (null).
 *
 *  Whoever asked: a Retry, the first read of a selection and the refetch
 *  after a mark are all answered by the queue the wait is asking, and when
 *  that answer says "not for five seconds" the next ask must not go out
 *  after one and a half. A board that is stale only by this page's clock was
 *  answered before the store would have said so, and gets the refresh's own
 *  five seconds -- as the old board's does. */
export function hear(wait: Wait, answer: BoardPayload | null, at: number,
                     random: () => number = Math.random): void {
  if (answer !== null) {
    const floor = answer.retry_after_ms
      ?? (refreshDue(answer, at, at) ? SLOW_MS : null)
    if (floor !== null) wait.floor = floor
  }
  wait.anchor = at
  wait.spread = random()
}

/** What react-query's `refetchInterval` reads: milliseconds until the board
 *  asks again on its own, or false for no ask on a timer.
 *
 *  Pending and busy boards, and boards with a refresh coming, wait on the
 *  schedule (`nextDelay`), never under the server's floor. A board with
 *  nothing coming is never asked about on a timer: a fresh shared board's
 *  wait is set for its fresh bound (`nextWait`) and asks a step past it, and
 *  a board a worker built for itself is marked past that bound, not polled.
 *  Nothing for a hidden tab, and nothing beside an ask already out -- its
 *  answer re-arms this. */
export function boardInterval(board: BoardPayload | undefined, { visible,
                              fetching, received, now, wait }: {
  visible: boolean
  fetching: boolean
  /** When this page received `board`. */
  received: number
  now: number
  /** The wait for this board's selection, when one is running. */
  wait: Wait | null
}): number | false {
  if (!visible || fetching || board === undefined || wait === null) return false
  // Read where the wait begins. A wait set for a fresh board's bound is for
  // a refresh that will be due then, not one that is due now.
  if (!owesABoard(board, received, Math.max(now, wait.since))) return false
  const step = nextDelay(wait.attempt, wait.anchor - wait.since, wait.floor,
                         () => wait.spread)
  // Overdue is "now", not never: a timer cannot be armed for the past.
  return Math.max(1, wait.anchor + step - now)
}

/** The wait a board is in: carried on for the same selection, begun for a
 *  new one, and over once nothing is coming.
 *
 *  A shared board with nothing coming YET has a refresh that comes due at
 *  its fresh bound -- strictly past it, as the server reads it -- and the
 *  wait for that refresh is set for then. It is the bound's own clock: the
 *  first ask goes out a schedule step after the bound whether or not the
 *  page has drawn itself since, which is the one thing a timer that only
 *  asked for a redraw could not promise (a renderer may defer a commit for
 *  as long as it likes). A board a worker built for itself has nothing
 *  behind it, and gets no wait at all. */
export function nextWait(wait: Wait | null, key: string, board: BoardPayload,
                         received: number, now: number,
                         random: () => number = Math.random): Wait | null {
  const same = wait !== null && wait.key === key
  if (owesABoard(board, received, now)) {
    return same && wait.since <= now ? wait : beginWait(key, board, now, random)
  }
  const left = refreshes(board) ? untilStale(board, received, received) : null
  if (left === null) return null
  const at = received + Math.max(0, left) + 1
  return same && wait.since === at ? wait : beginWait(key, board, at, random)
}

/** When a board a worker built for itself is read again on the page's own
 *  account: `REFRESH_MS` after it arrived, as the hub always read its board
 *  -- or null, for no such read.
 *
 *  Only while that instant is inside the board's fresh bound, strictly: at
 *  or past the bound nothing automatic goes out for a board with nothing
 *  queued behind it (ruling §5), because the read is a synchronous build.
 *  The line marks it "not refreshed" from there, and the ask is the
 *  reader's. A shared board has none: its wait begins at the bound. */
export function refreshAt(board: BoardPayload,
                          received: number): number | null {
  if (refreshes(board)) return null
  const left = untilStale(board, received, received)
  if (left === null) return null
  const at = received + REFRESH_MS
  return at < received + left ? at : null
}

/** A request this page sent on its own schedule -- a poll, the refetch a
 *  board's hard expiry is owed, or the minute's read of a board a worker
 *  built for itself -- and that failed. It is not retried behind
 *  the reader's back: the schedule is the back-off for a poll, and a failed
 *  expiry refetch is owed to the reader's next look at the tab or to their
 *  Retry. On the flag-off path each retry would be another synchronous build
 *  of the board the last one was still building. */
const SCHEDULED = new WeakSet<object>()

/** Never sent again behind the reader's back, whoever asked -- the reader's
 *  own Retry included. A request that timed out has stopped this page
 *  listening, not the server building: on the path where a worker builds its
 *  own board, a resend is a second synchronous build of a board the first may
 *  still be building. A 429 is the server's own rate limit, and a resend one
 *  second later is exactly what it refused. */
const NOT_RESENT = new Set(['timeout', 'busy'])

function retryBoard(count: number, error: unknown, flagOff: boolean): boolean {
  if (typeof error === 'object' && error !== null && SCHEDULED.has(error)) {
    return false
  }
  const reason = (error as { reason?: string })?.reason
  if (reason !== undefined && NOT_RESENT.has(reason)) return false
  // Nothing goes out again by itself where a worker builds its own board. The
  // reasons left here are a server error and an unreachable one, and neither
  // says the build stopped: the request failed, and the board it asked for is
  // still being made on a sync worker. A resend is then a second synchronous
  // build of the same board -- the block this slice exists to remove,
  // reintroduced through the error path. The reader's Retry is still theirs.
  if (flagOff) return false
  return retry(count, error)
}

// --- the quarter second a moved control owns ----------------------------------

/** Board selections whose request has not gone out yet, counted across the
 *  page: a control moved, and the settle it opened is still running.
 *
 *  The refetch a mark is owed waits on it, as the old board's does
 *  (`BoardPage.refetchMarks`): sent now it would ask the selection the reader
 *  has already left, and every admitted build occupies one of the thirty-two
 *  slots another reader needs. Waited for rather than skipped, because the
 *  request the control change sends may be answered from the cache and never
 *  go out at all -- and the mark would then have no refetch at all. */
let settling = 0
let waiters: (() => void)[] = []

/** Resolves once no control change is inside its quarter second. Immediately,
 *  which is the usual case. */
function whenSettled(): Promise<void> {
  if (settling === 0) return Promise.resolve()
  return new Promise((resolve) => { waiters.push(resolve) })
}

function endSettle(): void {
  settling -= 1
  if (settling > 0) return
  const woken = waiters
  waiters = []
  for (const wake of woken) wake()
}

/** The selection the board is actually asked for: this one, a quarter second
 *  after the reader stops moving controls.
 *
 *  The old board's debounce, at the point the hub turns a selection into a
 *  query key. The surface itself is not debounced -- the chips, the selects
 *  and the address bar follow the reader immediately, as they always did --
 *  only the request. Six control changes were measured as six admitted builds
 *  here against the old board's one (browser check 2), and a build admitted
 *  for a selection nobody is on any more still holds one of the thirty-two
 *  slots the ruling allows. */
function useSettled(selection: Selection): Selection {
  const key = queryFor(selection)
  const [settled, setSettled] = useState(selection)
  // Whether this page has counted itself into `settling`.
  const owed = useRef(false)
  const release = useCallback(() => {
    if (!owed.current) return
    owed.current = false
    endSettle()
  }, [])
  useEffect(() => {
    // Released from an effect rather than from the timer, so whoever waited
    // wakes only once the settled selection has been committed and its query
    // is the one on screen. Reached immediately by a reader who moved a
    // control and moved it back inside the quarter second: the question never
    // changed, so nothing is asked and nothing was ever owed.
    if (queryFor(settled) === key) { release(); return }
    if (!owed.current) { owed.current = true; settling += 1 }
    // Re-armed, not stacked: every further change inside the window replaces
    // this timer, and the burst counts as the one settle it is.
    const timer = setTimeout(() => setSettled(selection), SETTLE_MS)
    return () => clearTimeout(timer)
  }, [key, selection, settled, release])
  // A page that leaves mid-settle owes nothing.
  useEffect(() => release, [release])
  return settled
}

/** Why a board request is going out, when the page knows: the reader's own
 *  ask, the refetch a board's hard expiry is owed, or the minute's read of a
 *  board a worker built for itself (`refreshAt`). Otherwise it is the page's
 *  own schedule. */
type Why = 'reader' | 'expiry' | 'refresh' | null

/** Boards the reader is about to ask for from outside `useBoard` -- the
 *  refetch a mark is owed -- by `queryFor` key. Set around the one call that
 *  sends the request and cleared as soon as that call returns: react-query
 *  starts a request inside the call, so the request reads it there, and a
 *  call that joined a request already out leaves nothing behind for the
 *  next. */
const READER_ASKS = new Set<string>()

/** Failed asks about a waiting shell, for one selection (`useBoard`). */
interface Misses {
  key: string
  /** The page's own polls that have failed in a row. */
  polls: number
  /** Whether the reader's own ask was among them. */
  reader: boolean
}

const unmissed = (key: string): Misses => ({ key, polls: 0, reader: false })

/** Whether nobody is looking at this tab. Read rather than waited for: a tab
 *  restored in the background never fires a visibilitychange at all. */
function hidden(): boolean {
  return typeof document !== 'undefined'
    && document.visibilityState === 'hidden'
}

/** react-query's result for the current selection's board, and the three
 *  things about it only this page knows. */
export type BoardQuery = UseQueryResult<BoardPayload, unknown> & {
  /** The board this page holds FOR THE SELECTION ON SCREEN, or undefined
   *  while nothing it holds answers that question: a request for a new key is
   *  in flight and react-query is keeping the previous board as placeholder
   *  data, or the reader has just moved a control and the quarter second
   *  before its request has not run out. Both are the Loading state, and
   *  neither may be drawn -- the previous selection's rows under the new
   *  selection's labels is what the cold contract forbids. */
  answer: BoardPayload | undefined
  /** When this page received the board it holds: the clock its age, its
   *  fresh bound and its expiry are read on. */
  received: number
  /** A board being built has been waited on for DELAYED_AFTER_MS. */
  delayed: boolean
  /** Why this page's asks about a waiting shell keep failing -- two of its
   *  own polls in a row, or the reader's own ask -- or null. The notice
   *  standing in for the shell says it: a shell has no last answer for the
   *  failure notice to fall back on, and the wait goes on asking. */
  failing: string | null
  /** The reader's own ask, now. Joins a request already out rather than
   *  sending another: an abort stops this page listening and does not stop
   *  the server, so abort-and-resend is a second build of one board. */
  retry: () => void
}

export function useBoard(asked: Selection, initial?: BoardPayload,
                         visible = true): BoardQuery {
  const client = useQueryClient()
  // Before anything here becomes a query key, and so before anything here
  // sends a request.
  const settled = useSettled(asked)
  const selection = requestSelection(settled)
  const key = queryFor(selection)
  // The reader has moved a control and the request for it has not gone out
  // yet. Nothing on screen answers the question they are now asking, so this
  // page holds no board for it -- exactly as it holds none while a request
  // for a new key is in flight. Without this the rows of the question they
  // left would stand under the controls they just moved, which is the one
  // thing the cold contract forbids (ruling §1), and the old question's wait
  // would go on polling a selection nobody is on.
  const unsettled = queryFor(requestSelection(asked)) !== key
  // Whether a worker builds this page's boards for itself. The flag is the
  // server's, so every board on the page agrees about it; the embedded board
  // seeds it and every answer keeps it current.
  const flagOff = useRef(initial?.shared === false)
  // The embedded board seeds only the key it was actually built for. Handing
  // it to another key would present a board built under one filter as the
  // answer to a different one -- as real data, with a fresh timestamp, once,
  // on arrival, and then silently replaced a minute later. Enforced here
  // rather than asked of every caller.
  const seed = initial && queryFor(selectionOf(initial)) === key
    ? initial : undefined

  // The wait for the board on screen, keyed by its selection.
  const wait = useRef<Wait | null>(null)
  // What the next request is, when the page knows (`Why`): the reader's own
  // ask, the refetch a board's hard expiry is owed, or the minute's read.
  // Otherwise it is the page's schedule, and a poll whenever a wait is
  // running for the board on screen.
  const next = useRef<Why>(null)
  // The selection the last request was for. The first request for a
  // selection is its READ -- a new question, and new demand -- whatever is
  // cached for it. The embedded board was the seed selection's read.
  const sentFor = useRef<string | null>(seed ? key : null)
  // The request going out, as it was decided when it first went: react-query
  // resends a request the server failed (`retryBoard`), and a resend is the
  // same request asked for the same reason -- a Retry resent is still the
  // reader's own. Every attempt at one request carries one signal.
  const sending = useRef<{ signal: AbortSignal | null; why: Why;
                           poll: boolean }>({ signal: null, why: null,
                                              poll: false })
  // Asks about a waiting shell that have failed since the last answer, for
  // the selection they were about: how many of the page's own polls in a
  // row, and whether one was the reader's own. One poll that did not answer
  // is a blip the next may not have; two in a row is the wait failing. The
  // reader who asked is owed the reason at once. Any answer that lands clears
  // it, and a new selection has failed nothing yet.
  const misses = useRef<Misses>(unmissed(key))

  const query = useQuery({
    queryKey: boardKey(selection),
    queryFn: async ({ signal }) => {
      // Only this selection's wait hears about this request, and only once it
      // has begun. A request for a selection the reader has left may still
      // answer, and has nothing to tell the question that replaced it; a
      // wait set for a fresh board's bound is replaced by whatever the
      // answer turns out to be.
      const mine = () => {
        const running = wait.current
        return running !== null && running.key === key
          && running.since <= Date.now() ? running : null
      }
      if (sending.current.signal !== signal) {
        const why: Why = READER_ASKS.has(key) ? 'reader' : next.current
        next.current = null
        const first = sentFor.current !== key
        sentFor.current = key
        // One rule, the old board's: poll=1 is this page asking AGAIN, on
        // its own schedule, about a board it is already waiting for -- which
        // the server reads to leave demand and the queue position alone. The
        // reader's own asks, a Retry and the refetch after a mark, are reads:
        // new demand. So is the first request for a selection, whoever sends
        // it.
        const poll = !first && why !== 'reader' && mine() !== null
        sending.current = { signal, why, poll }
        if (poll) {
          const running = mine()
          if (running) running.attempt += 1
        }
      }
      const { why, poll } = sending.current
      try {
        const answer = await fetchBoard(selection, signal, { poll })
        flagOff.current = answer.shared === false
        const running = mine()
        if (running) hear(running, answer, Date.now())
        if (misses.current.key === key) misses.current = unmissed(key)
        return answer
      } catch (error) {
        // Aborted is abandoned -- a key change, an unmount -- and says
        // nothing about the queue: the floor in force stands, untouched.
        if (!signal.aborted) {
          const running = mine()
          if (running) hear(running, null, Date.now())
          // Counted over a waiting shell only: a board with rows says a
          // failed refresh in the notice above it, and a selection with no
          // answer yet says it where its rows would be.
          const held = client.getQueryState<BoardPayload>(boardKey(selection))
          if (held?.data !== undefined && held.data.rows === null) {
            const was = misses.current.key === key ? misses.current
              : unmissed(key)
            misses.current = poll ? { ...was, polls: was.polls + 1 }
              : { ...was, reader: true }
          }
          if ((poll || why === 'expiry' || why === 'refresh')
              && typeof error === 'object' && error !== null) {
            SCHEDULED.add(error)
          }
        }
        throw error
      }
    },
    initialData: seed,
    // The embedded board is current when the document is. Without this the
    // seeded page immediately refetches the board the server just rendered
    // into it, which is the self-inflicted wait the embed exists to avoid.
    staleTime: REFRESH_MS,
    refetchInterval: (current) => {
      const board = current.state.data
      if (board === undefined || unsettled) return false
      const now = Date.now()
      const received = current.state.dataUpdatedAt
      wait.current = nextWait(wait.current, key, board, received, now)
      return boardInterval(board, {
        visible, fetching: current.state.fetchStatus !== 'idle', received,
        now, wait: wait.current,
      })
    },
    refetchIntervalInBackground: false,
    // Coming back to the tab is this hook's to handle (below), and it asks
    // only when the board owes one. The client's default would refetch any
    // board past its staleTime, flag-off boards included.
    refetchOnWindowFocus: false,
    // Nor is a connection coming back the reader asking. The client's
    // default refetches a board past its staleTime when the network returns:
    // for a board a worker built for itself, past its fresh bound, that is
    // an automatic synchronous build the ruling forbids. A wait's own polls,
    // and a request paused while offline, carry on by themselves.
    refetchOnReconnect: false,
    // Governs a KEY CHANGE: react-query keeps the previous board as
    // placeholder data while the one for a new filter loads. The page never
    // draws it (`isPlaceholderData` is the Loading state), because that is
    // the previous selection's board under the new selection's filters.
    // Surviving a failed REFRESH is separate, and is react-query keeping
    // `data` while `status` turns to error -- which is what StaleNotice
    // renders beside.
    placeholderData: keepPreviousData,
    retry: (count, error) => retryBoard(count, error, flagOff.current),
  })

  const { refetch } = query
  const answer = query.isPlaceholderData || unsettled ? undefined : query.data
  const received = query.dataUpdatedAt

  const ask = useCallback(() => {
    const state = client.getQueryState(boardKey(selection))
    // Joined: the request already out is the one this would send, and its
    // answer is the one this would draw.
    if (state !== undefined && state.fetchStatus !== 'idle') return
    next.current = 'reader'
    void refetch({ cancelRefetch: false })
  }, [client, selection, refetch])

  // The hard expiry. Past it the rows describe a rolling window that has
  // moved on, and the client clock is what notices: a tab left open all
  // afternoon asks the server nothing at all.
  //
  // One ask, whichever path built the board. On a shared board it is the
  // wait's next poll, sent now; on a board a worker built for itself it is
  // the one refetch that board gets, and it goes out for a reader who is
  // looking. A hidden tab owes it instead, as does a tab whose refetch
  // failed; the next look at the tab pays it (below), and so does Retry.
  const owed = useRef<(() => void) | null>(null)
  // Which board's expiry has been asked about. One that arrives already past
  // its own expiry is asked about again once, slowly, rather than in a loop.
  const expiredAsked = useRef<string | null>(null)
  useEffect(() => {
    if (answer === undefined) return
    const left = untilExpired(answer, received)
    if (left === null) return
    const stamp = `${key} ${answer.as_of}`
    const again = left <= 0 && expiredAsked.current === stamp
    const refetchAtExpiry = () => {
      const state = client.getQueryState(boardKey(selection))
      // Armed for one answer. Another may have landed in the instant before
      // React re-rendered to disarm this, and the board it was armed for is
      // then already gone.
      if (state?.dataUpdatedAt !== received) return
      expiredAsked.current = stamp
      // An ask already out is this one: its answer describes the window as
      // it is now. Until it lands the refetch stays owed, since that ask may
      // fail; an answer takes it away (the cleanup below). A hidden tab owes
      // it as well.
      if (state.fetchStatus !== 'idle' || hidden()) {
        owed.current = refetchAtExpiry
        return
      }
      next.current = 'expiry'
      void refetch({ cancelRefetch: false }).then((result) => {
        if (result.isError
            && client.getQueryState(boardKey(selection))?.dataUpdatedAt
              === received) {
          owed.current = refetchAtExpiry
        }
      })
    }
    const timer = setTimeout(refetchAtExpiry,
                             again ? SLOW_MS : Math.max(0, left))
    return () => {
      clearTimeout(timer)
      if (owed.current === refetchAtExpiry) owed.current = null
    }
  }, [answer, received, key, client, selection, refetch])

  // A board a worker built for itself, read again a minute after it arrived
  // (`refreshAt`) -- as the hub always read its board -- for a reader who is
  // looking. Nothing is queued behind such a board, so nothing else will.
  // Once per answer: the answer arms the next minute, and a read that failed
  // is not sent again on the page's account, least of all at the bound. A
  // tab hidden at the minute owes the read, and pays it only if the reader
  // is back inside the bound.
  useEffect(() => {
    if (answer === undefined) return
    const at = refreshAt(answer, received)
    if (at === null) return
    const bound = received + (untilStale(answer, received, received) ?? 0)
    const read = () => {
      const state = client.getQueryState(boardKey(selection))
      // Armed for one answer, as the expiry is.
      if (state?.dataUpdatedAt !== received) return
      // Nothing at or past the bound, however late this runs.
      if (Date.now() >= bound) return
      // An ask already out is this read: its answer is the board it would
      // bring. Until it lands the read stays owed, since that ask may fail;
      // an answer takes it away (the cleanup below).
      if (state.fetchStatus !== 'idle' || hidden()) {
        owed.current = read
        return
      }
      next.current = 'refresh'
      void refetch({ cancelRefetch: false })
    }
    const timer = setTimeout(read, Math.max(0, at - Date.now()))
    return () => {
      clearTimeout(timer)
      if (owed.current === read) owed.current = null
    }
  }, [answer, received, client, selection, refetch])

  // Back from a hidden tab: one ask at once for a board this page is waiting
  // on -- it may well have been built while nobody was looking -- and the
  // schedule carries on from its place. Otherwise, whatever the tab owes.
  const looked = useRef(visible)
  useEffect(() => {
    const was = looked.current
    looked.current = visible
    if (!visible || was) return
    const state = client.getQueryState<BoardPayload>(boardKey(selection))
    // An ask already out is the one this would send. Whatever the tab owes
    // stays owed until an answer lands: that ask may yet fail, and the next
    // look pays it then. An answer that lands takes it away (the clocks'
    // own cleanup, above).
    if (state?.data === undefined || state.fetchStatus !== 'idle') return
    if (owesABoard(state.data, state.dataUpdatedAt, Date.now())) {
      void refetch({ cancelRefetch: false })
      return
    }
    const pay = owed.current
    owed.current = null
    pay?.()
  }, [visible, client, selection, refetch])

  // How long the reader has waited for a board being built, from when the
  // wait for THIS selection began. Kept here rather than in the waiting
  // notice so moving between pages does not reset it, and a new selection
  // -- a new wait -- always does.
  const building = answer !== undefined && (answer.pending || answer.busy)
  const [late, setLate] = useState<Wait | null>(null)
  useEffect(() => {
    const running = wait.current
    if (!building || running === null || running.key !== key) return
    const timer = setTimeout(() => setLate(running),
      Math.max(0, running.since + DELAYED_AFTER_MS - Date.now()))
    return () => clearTimeout(timer)
  }, [building, key, answer])
  const delayed = building && late !== null && late === wait.current

  const miss = misses.current
  const failing = query.isError && answer !== undefined && answer.rows === null
    && miss.key === key && (miss.reader || miss.polls > 1)
    ? (query.error instanceof Error ? query.error.message
      : 'The board did not answer.')
    : null

  return { ...query, answer, received, delayed, failing, retry: ask }
}

export function useDetail(ticker: string | null, selection: Selection,
                          span: PanelSpan, visible = true) {
  return useQuery({
    queryKey: detailKey(ticker ?? '', selection, span),
    queryFn: ({ signal }) => fetchDetail(ticker as string, selection, span, signal),
    enabled: Boolean(ticker),
    refetchInterval: visible ? REFRESH_MS : false,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    retry,
  })
}

/** Mark or unmark a company.
 *
 *  No optimistic flip. The endpoint answers the caller's WHOLE list, and
 *  adopting that answer is what keeps one truth about which companies are
 *  marked -- a locally applied change plus a server list is two, free to
 *  diverge the moment a write is refused. The caller disables the control
 *  until the answer lands, so the cost is a moment of latency rather than a
 *  screen that is briefly a lie.
 *
 *  Every cached board takes the list, because `watching` and `watch_rows`
 *  ride on the board payload and are now out of date in each of them.
 */
export function useWatchMutation(onSettled?: () => void) {
  const client = useQueryClient()
  return useMutation({
    // However the write ends, told through the mutation's own options: they
    // outlive the page that started it. `reset()` detaches a write from its
    // page, and react-query then drops the callbacks a `mutate` call carried.
    onSettled: () => { onSettled?.() },
    mutationFn: ({ ticker, on }: { ticker: string; on: boolean }) =>
      setWatch(ticker, on),
    onSuccess: (watching) => {
      // Adopt the server's list into every cached board, then ask again for
      // the one on screen: the adopted list is authoritative immediately, and
      // the refetch brings the rows that go with it.
      for (const cached of client.getQueryCache()
        .findAll({ queryKey: [ROOT, 'board'] })) {
        const board = cached.state.data as BoardPayload | undefined
        if (board === undefined) continue
        // The rows go with the list. Updating `watching` alone left an
        // unmarked company still in every reading of watch_rows until the
        // refetch landed, and a newly marked one in the list with no row. A
        // waiting shell's `watch_rows` is empty, and stays so.
        const rows = board.watch_rows?.filter(
          (row) => watching.includes(row.ticker))
        // The list, and nothing else about the board. WHEN it arrived is not
        // the list's to change: its age line and its wait are both counted
        // from it, and a mark that reset it would make a two-minute-old
        // board read as new. Nor is a failure beside it: a refresh that
        // failed is still the latest word on the board, and setQueryData
        // records the list as a successful answer -- the failure notice
        // went, and an expired board claimed a recalculation, until the
        // refetch below settled.
        cached.setState({ data: { ...board, watching, watch_rows: rows } })
      }
      void refreshAfterMark(client)
    },
  })
}

/** The board on screen, asked for again after a mark -- and only that one.
 *
 *  After whatever is already out rather than over it: a request sent before
 *  the mark landed answers with the old list, but aborting it to send another
 *  is two builds of one board on the path where a worker builds its own. So
 *  the refetch waits for that answer, then asks once. Asked by key, of the
 *  board still being read when the time comes: a selection the reader has
 *  since left is not asked about, and its answer could not be drawn under the
 *  current filters anyway. Every other cached board is marked out of date,
 *  and asked again when it is next on screen.
 */
async function refreshAfterMark(client: QueryClient): Promise<void> {
  const boards = { queryKey: [ROOT, 'board'] }
  await client.invalidateQueries({ ...boards, refetchType: 'none' })
  // A moved control still owes its request: asking now would ask the
  // selection the reader has already left, so the refetch waits the quarter
  // second out and then asks whatever is on screen.
  await whenSettled()
  const onScreen = client.getQueryCache().findAll({ ...boards, type: 'active' })
  await Promise.all(onScreen.map(async (query) => {
    const inflight = query.promise
    if (inflight !== undefined) {
      await inflight.catch(() => undefined)
      // Never on top of a request that just failed. The abort stopped this
      // page listening, not the server building: where a worker builds its
      // own board that one is still being made, and asking again is a second
      // concurrent synchronous build. The list is already adopted, so the
      // mark is on screen either way; the next answer brings its rows.
      if (client.getQueryState(query.queryKey)?.status === 'error') return
    }
    // The reader's own ask, as a Retry is: a read, never a poll.
    const key = String(query.queryKey[2])
    READER_ASKS.add(key)
    const sent = client.refetchQueries(
      { queryKey: query.queryKey, exact: true, type: 'active' },
      { cancelRefetch: false })
    READER_ASKS.delete(key)
    await sent
  }))
}

/** The universe, not the current board: a reader searching for a company that
 *  nobody is discussing today still expects to find it. */
export function useSearch(query: string) {
  const trimmed = query.trim()
  return useQuery({
    queryKey: searchKey(trimmed),
    queryFn: ({ signal }) => fetchSearch(trimmed, signal),
    enabled: trimmed.length > 0,
    // A universe match does not go stale in the seconds a reader spends
    // choosing one, and re-asking on every keystroke's remount would.
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    retry,
  })
}

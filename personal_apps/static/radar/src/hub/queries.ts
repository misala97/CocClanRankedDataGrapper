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
  DELAYED_AFTER_MS, SLOW_MS, nextDelay, refreshDue, refreshes, untilExpired,
  untilStale,
} from '../pending'
import type { BoardPayload, PanelSpan, Selection } from '../types'

/** Every hub key starts here, so the hub and the old board island can share a
 *  browser tab without sharing a cache entry. */
const ROOT = 'radar-hub'

/** Panels are refreshed while their page is on screen, and only then. A
 *  hidden tab polling a dashboard nobody is reading is a request the reader
 *  did not ask for.
 *
 *  The board is not refreshed on this clock any more. It carries bounds of
 *  its own (ruling §5): a shared board is asked about again from the moment
 *  it passes its fresh bound, and a board a worker built for itself is never
 *  asked about on a timer at all -- asking again would build another,
 *  synchronously, in every open tab. What remains of this figure for the
 *  board is how long a cached answer counts as current when the reader comes
 *  back to its selection. */
export const REFRESH_MS = 60_000

export const boardKey = (s: Selection) => [ROOT, 'board', queryFor(s)] as const

export const detailKey = (ticker: string, s: Selection, span: PanelSpan) =>
  [ROOT, 'detail', ticker, s.market, s.sources.join(','), s.window, span] as const

export const searchKey = (q: string) => [ROOT, 'search', q.trim()] as const

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

/** A request this page sent on its own schedule -- a poll, or the refetch a
 *  board's hard expiry is owed -- and that failed. It is not retried behind
 *  the reader's back: the schedule is the back-off for a poll, and a failed
 *  expiry refetch is owed to the reader's next look at the tab or to their
 *  Retry. On the flag-off path each retry would be another synchronous build
 *  of the board the last one was still building. */
const SCHEDULED = new WeakSet<object>()

function retryBoard(count: number, error: unknown): boolean {
  if (typeof error === 'object' && error !== null && SCHEDULED.has(error)) {
    return false
  }
  return retry(count, error)
}

/** Whether nobody is looking at this tab. Read rather than waited for: a tab
 *  restored in the background never fires a visibilitychange at all. */
function hidden(): boolean {
  return typeof document !== 'undefined'
    && document.visibilityState === 'hidden'
}

/** react-query's result for the current selection's board, and the three
 *  things about it only this page knows. */
export type BoardQuery = UseQueryResult<BoardPayload, unknown> & {
  /** When this page received the board it holds: the clock its age, its
   *  fresh bound and its expiry are read on. */
  received: number
  /** A board being built has been waited on for DELAYED_AFTER_MS. */
  delayed: boolean
  /** The reader's own ask, now. Joins a request already out rather than
   *  sending another: an abort stops this page listening and does not stop
   *  the server, so abort-and-resend is a second build of one board. */
  retry: () => void
}

export function useBoard(selection: Selection, initial?: BoardPayload,
                         visible = true): BoardQuery {
  const client = useQueryClient()
  const key = queryFor(selection)
  // The embedded board seeds only the key it was actually built for. Handing
  // it to another key would present a board built under one filter as the
  // answer to a different one -- as real data, with a fresh timestamp, once,
  // on arrival, and then silently replaced a minute later. Enforced here
  // rather than asked of every caller.
  const seed = initial && queryFor(selectionOf(initial)) === key
    ? initial : undefined

  // The wait for the board on screen, keyed by its selection.
  const wait = useRef<Wait | null>(null)
  // What the next request is, when the page knows: the reader's own ask, or
  // the refetch a board's hard expiry is owed. Otherwise it is the page's
  // schedule, and a poll whenever the board on screen owes one.
  const next = useRef<'reader' | 'expiry' | null>(null)
  // The selection the last request was for. The first request for a
  // selection is its READ -- a new question, and new demand -- whatever is
  // cached for it. The embedded board was the seed selection's read.
  const sentFor = useRef<string | null>(seed ? key : null)

  const query = useQuery({
    queryKey: boardKey(selection),
    queryFn: async ({ signal }) => {
      const held = client.getQueryState<BoardPayload>(boardKey(selection))
      const why = next.current
      next.current = null
      const first = sentFor.current !== key
      sentFor.current = key
      // Asking AGAIN about a board this page is already waiting for, which
      // the server reads to leave demand and the queue position alone.
      const poll = !first && why !== 'reader' && held?.data !== undefined
        && owesABoard(held.data, held.dataUpdatedAt, Date.now())
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
      if (poll) {
        const running = mine()
        if (running) running.attempt += 1
      }
      try {
        const answer = await fetchBoard(selection, signal, { poll })
        const running = mine()
        if (running) hear(running, answer, Date.now())
        return answer
      } catch (error) {
        // Aborted is abandoned -- a key change, an unmount -- and says
        // nothing about the queue: the floor in force stands, untouched.
        if (!signal.aborted) {
          const running = mine()
          if (running) hear(running, null, Date.now())
          if ((poll || why === 'expiry') && typeof error === 'object'
              && error !== null) {
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
      if (board === undefined) return false
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
    // Governs a KEY CHANGE: react-query keeps the previous board as
    // placeholder data while the one for a new filter loads. The page never
    // draws it (`isPlaceholderData` is the Loading state), because that is
    // the previous selection's board under the new selection's filters.
    // Surviving a failed REFRESH is separate, and is react-query keeping
    // `data` while `status` turns to error -- which is what StaleNotice
    // renders beside.
    placeholderData: keepPreviousData,
    retry: retryBoard,
  })

  const { refetch } = query
  const answer = query.isPlaceholderData ? undefined : query.data
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
      // it is now.
      if (state.fetchStatus !== 'idle') return
      if (hidden()) { owed.current = refetchAtExpiry; return }
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

  // Back from a hidden tab: one ask at once for a board this page is waiting
  // on -- it may well have been built while nobody was looking -- and the
  // schedule carries on from its place. Otherwise, whatever the tab owes.
  const looked = useRef(visible)
  useEffect(() => {
    const was = looked.current
    looked.current = visible
    if (!visible || was) return
    const pay = owed.current
    owed.current = null
    const state = client.getQueryState<BoardPayload>(boardKey(selection))
    if (state?.data === undefined || state.fetchStatus !== 'idle') return
    if (owesABoard(state.data, state.dataUpdatedAt, Date.now())) {
      void refetch({ cancelRefetch: false })
      return
    }
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

  return { ...query, received, delayed, retry: ask }
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
export function useWatchMutation() {
  const client = useQueryClient()
  return useMutation({
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
        // WHEN the board arrived is not the list's to change. Its age line
        // and its wait are both counted from it, and a mark that reset it
        // would make a two-minute-old board read as new.
        client.setQueryData<BoardPayload>(
          cached.queryKey, { ...board, watching, watch_rows: rows },
          { updatedAt: cached.state.dataUpdatedAt })
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
  const onScreen = client.getQueryCache().findAll({ ...boards, type: 'active' })
  await client.invalidateQueries({ ...boards, refetchType: 'none' })
  await Promise.all(onScreen.map(async (query) => {
    await query.promise?.catch(() => undefined)
    await client.refetchQueries(
      { queryKey: query.queryKey, exact: true, type: 'active' },
      { cancelRefetch: false })
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

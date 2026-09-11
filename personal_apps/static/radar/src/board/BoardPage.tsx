import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor, setWatch } from '../api'
import { Boundary } from '../Broken'
import { DetailPane } from '../detail/DetailPane'
import { Account } from '../list/Account'
import { ListPane, universalMarks } from '../list/ListPane'
import { Poller, SLOW_MS } from '../pending'
import { useNarrow } from './narrow'
import type { BoardPayload, Selection } from '../types'

/** The board: a list of what deserves attention beside one ticker in depth.
 *
 *  Two panes rather than one page of cards, because there are two different
 *  questions here. The list answers "which of these is worth my time"; the
 *  panel answers "is this real". Cramming both into a 300px card is what made
 *  the previous surface unreadable -- every fact the tool knew had to fit
 *  there, because there was nowhere to hand anything off to.
 */
/** How long a burst of control changes has to go quiet before one request
 *  goes out for all of them. */
const SETTLE_MS = 250

export function BoardPage({ initial }: { initial: BoardPayload }) {
  const [payload, setPayload] = useState(initial)
  // When THIS page received that payload. The server sends an age; the reader
  // keeps looking after it arrives, and the honest age on screen is the sum
  // of the two. Kept beside the payload rather than derived from a stamp so
  // the two always move together.
  const [received, setReceived] = useState(() => Date.now())
  const [selection, setSelection] = useState<Selection>({
    market: initial.market,
    sources: initial.sources,
    segments: initial.segments,
    window: initial.window_hours,
    minVenues: initial.min_venues,
    // From the ECHO, not the URL: the server already parsed and validated
    // it, and this page reads the address bar for ?t= alone.
    sort: initial.sort,
    dir: initial.dir,
  })
  const [selected, setSelected] = useState<string | null>(
    () => initialTicker(initial))
  // The caller's marks. Optimistic: the star flips before the server
  // answers, the server's list replaces it, and a refusal undoes that one
  // flip. Mutations run one at a time, in order -- a queue, never parallel
  // requests: with two in flight, a late failure could restore a snapshot
  // that predates the later success (Codex's review of 26cc82d). The
  // board's payload carries the list too; it is trusted only while nothing
  // is in flight, and one refetch follows the last mutation.
  const [watching, setWatching] = useState<string[]>(initial.watching ?? [])
  const marks = useRef<string[]>(initial.watching ?? [])   // the same list, readable now
  const queue = useRef<Promise<void>>(Promise.resolve())
  const queued = useRef<{ ticker: string; on: boolean }[]>([])
  const landed = useRef(false)   // a mutation the server accepted since the last refetch
  const mark = useCallback((next: string[]) => { marks.current = next; setWatching(next) }, [])
  useEffect(() => {
    if (queued.current.length === 0) mark(payload.watching ?? [])
  }, [payload, mark])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BoardUnavailable | null>(null)
  const inflight = useRef<AbortController | null>(null)
  // The board embedded in the document already matches the initial selection,
  // so the first effect run has nothing to fetch.
  const first = useRef(true)
  // Which question is on screen. An abort asks the transport to stop but
  // cannot unsend a response already in flight -- and a wait is precisely
  // when a reader changes their mind, so this is not a rare race here the way
  // it was on a page that only fetched when a control moved. An answer
  // stamped with an older number is dropped: old rows under a new window's
  // label is worse than a moment longer with none.
  const asked = useRef(0)
  // How many times the question itself has changed. State rather than a ref
  // because the polling effect below has to see it: a poll answering "still
  // pending" must not restart the schedule, and a new selection must.
  const [question, setQuestion] = useState(0)
  const poller = useRef<Poller | null>(null)
  if (poller.current === null) poller.current = new Poller()

  const load = useCallback(async (next: Selection, ticker: string | null,
                                  preserveTicker = false, poll = false)
      : Promise<number | null> => {
    // A poll belongs to the board on screen; anything else replaces it, and
    // takes the wait with it. Stopped here rather than in the effect below
    // so a poll for the OLD selection cannot go out during the debounce and
    // abort the request the reader is actually waiting for. The counter is
    // what lets the effect notice: a new question earns a fresh schedule.
    if (!poll) {
      poller.current?.stop()
      setQuestion((n) => n + 1)
    }
    const generation = (asked.current += 1)
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller
    // A poll is not a control change: raising the list's busy flag every few
    // seconds would flicker aria-busy at a reader who did nothing.
    if (!poll) setBusy(true)
    try {
      const fresh = await fetchBoard(next, controller.signal, { poll })
      if (generation !== asked.current) return null
      setPayload(fresh)
      setReceived(Date.now())
      setError(null)
      // The wait ends here rather than in the effect below. The effect runs a
      // React commit later, and the poller schedules its next ask the moment
      // this function returns -- so a board that arrived would still be
      // followed by one more pointless request.
      if (!(fresh.pending || fresh.busy || fresh.stale)) poller.current?.stop()
      // Selection follows filtering, but a market change is different: the
      // company identity stays the same even when its new market board does
      // not rank it. The detail endpoint can still show its marked fallback.
      //
      // A waiting shell has no rows at all, so it holds no ticker: the panel
      // empties with the list rather than describing a company the board
      // beside it has stopped listing.
      const rows = fresh.rows ?? []
      const stillThere = rows.some((row) => row.ticker === ticker)
      const nextTicker = (preserveTicker || stillThere) ? ticker
        : (rows[0]?.ticker ?? null)
      setSelected(nextTicker)
      writeUrl(next, nextTicker)
      return fresh.retry_after_ms ?? null
    } catch (problem) {
      if (controller.signal.aborted || generation !== asked.current) return null
      // The previous board stays on screen. A failed refresh is a reason to
      // say so, not a reason to throw away data that is still true.
      setError(problem as BoardUnavailable)
      return null
    } finally {
      if (inflight.current === controller) {
        inflight.current = null
        if (!poll) setBusy(false)
      }
    }
  }, [])

  // What the poller asks for, read at the moment it asks rather than closed
  // over: the schedule outlives several renders, and a poll must always
  // describe the selection that is on screen now.
  const current = useRef({ selection, selected,
                           retryAfterMs: payload.retry_after_ms })
  current.current = { selection, selected,
                      retryAfterMs: payload.retry_after_ms }
  const retry = useCallback(() => {
    void load(current.current.selection, current.current.selected, true)
  }, [load])

  // Three states, one behaviour: keep asking. Pending and busy have no board
  // to show, stale has one that is being replaced -- and in all three there
  // is an answer coming that nothing on this page would otherwise go and get.
  //
  // Keyed on the STATE rather than on the payload: a poll that answers
  // "still pending" produces a new payload object every few seconds, and
  // restarting the poller on each one would reset its back-off and its sense
  // of how long the reader has been waiting -- so it would never slow down
  // and never admit the wait is long.
  const waiting = payload.pending || payload.busy || payload.stale
  useEffect(() => {
    const wait = poller.current
    if (!wait) return
    if (!waiting) { wait.stop(); return }
    wait.start(() => load(current.current.selection,
                          current.current.selected, false, true),
               current.current.retryAfterMs)
    return () => wait.stop()
  }, [waiting, question, load])

  // A hidden tab is polling a queue on behalf of nobody. Coming back asks
  // once immediately, because the answer is usually already waiting.
  useEffect(() => {
    const change = () => {
      if (document.visibilityState === 'hidden') poller.current?.pause()
      else poller.current?.resume()
    }
    document.addEventListener('visibilitychange', change)
    return () => document.removeEventListener('visibilitychange', change)
  }, [])

  // Past its hard expiry a board stops being old and starts being wrong: the
  // rows describe a rolling window that has moved on, and the counts under
  // them are answers to a question about a different span of hours. The
  // client clock is what notices, because a tab left open all afternoon asks
  // the server nothing at all.
  const refetched = useRef<string | null>(null)
  useEffect(() => {
    if (payload.rows === null || payload.age_seconds === null) return
    if (!Number.isFinite(payload.hard_expiry_seconds)) return
    const left = payload.hard_expiry_seconds * 1000
      - payload.age_seconds * 1000 - (Date.now() - received)
    // Asking again for a board that arrives past its own expiry is right
    // once and a hot loop twice: the store never serves one (a row that old
    // reads as missing), but a deployment that did would otherwise have this
    // page fetching as fast as the network allows.
    const again = left <= 0 && refetched.current === payload.as_of
    const timer = setTimeout(() => {
      refetched.current = payload.as_of
      void load(current.current.selection, current.current.selected, true)
    }, again ? SLOW_MS : Math.max(0, left))
    return () => clearTimeout(timer)
  }, [payload, received, load])

  const previousMarket = useRef(initial.market)
  // Remembered across a burst: a market flip followed within the debounce by
  // a source toggle must still preserve the ticker the way a market flip does.
  const marketPending = useRef(false)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (previousMarket.current !== selection.market) marketPending.current = true
    previousMarket.current = selection.market
    // Coalesced. Every toggle used to fire its own request and abort the
    // last; five quick clicks queued five board builds on the server and the
    // fifth waited past the 8s timeout -- "The board did not answer in time"
    // during ordinary toggling (critique, 2026-09-01). Short enough that a
    // single click still feels immediate.
    const timer = setTimeout(() => {
      const marketChanged = marketPending.current
      marketPending.current = false
      void load(selection, selected, marketChanged)
    }, SETTLE_MS)
    return () => clearTimeout(timer)
    // Deliberately not keyed on `selected`: picking a ticker is a client-side
    // change that must not refetch the board.
  }, [selection, load])

  // A tap counter rather than a flag on `selected`: tapping the row that is
  // already selected must scroll too.
  const [tap, setTap] = useState(0)
  const select = useCallback((ticker: string) => {
    setSelected(ticker)
    setTap((n) => n + 1)
    writeUrl(selection, ticker)
  }, [selection])

  const toggleWatch = useCallback((ticker: string) => {
    const on = !marks.current.includes(ticker)
    const flip = { ticker, on }
    queued.current.push(flip)
    mark(on ? [...marks.current, ticker] : marks.current.filter((t) => t !== ticker))
    queue.current = queue.current.then(async () => {
      try {
        const fresh = await setWatch(ticker, on)
        landed.current = true
        // The server's list is the truth up to this flip; flips still
        // queued behind it were made after, so they stay applied on top.
        mark(queued.current.filter((q) => q !== flip).reduce(
          (list, q) => (q.on ? [...list.filter((t) => t !== q.ticker), q.ticker]
                             : list.filter((t) => t !== q.ticker)),
          fresh))
      } catch {
        // Undo this flip only; later flips of other tickers stand.
        mark(on ? marks.current.filter((t) => t !== ticker) : [...marks.current, ticker])
      } finally {
        queued.current = queued.current.filter((q) => q !== flip)
        if (queued.current.length === 0 && landed.current) {
          // The watched rows are built server-side; one refetch after the
          // last accepted mutation brings them in (or takes them out). Memo
          // hit. A refused flip alone changes nothing, so nothing to fetch.
          landed.current = false
          void load(selection, selected, true)
        }
      }
    })
  }, [mark, selection, selected, load])

  const narrow = useNarrow()
  const page = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!tap || !narrow) return
    // The tap's own feedback, before the detail request has answered. On a
    // desk the panel is already beside the list and this does nothing;
    // stacked, the panel sits under the whole list and a tap used to change
    // nothing on screen until the fetch resolved. Only on an explicit row
    // selection: a filter change that moves the selection must leave the
    // reader at the controls they are using.
    //
    // It travels rather than cuts, so the reader sees where the panel is in
    // relation to the list. scroll-behavior is outside the stylesheet's
    // reduced-motion rule, so the preference is consulted here.
    const reduce = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    page.current?.querySelector('.detail')?.scrollIntoView({
      block: 'start', behavior: reduce ? 'auto' : 'smooth',
    })
  }, [tap, narrow])

  // Where the panel sends a reader whose ticker has no panel to show.
  //
  // The first row that is NOT the current one, rather than simply the first:
  // the board can list a ticker the detail endpoint 404s on -- a symbol the
  // extraction found that the universe has no profile for lands on the board
  // as `unknown` and has no panel -- and when that ticker is the top row, an
  // escape hatch pointing at the top row is a button that does nothing.
  // Seen on a live board, with QQQ at rank one.
  //
  // Null on an empty board, and the panel then offers nothing rather than a
  // control that would select nothing.
  //
  // A waiting shell has no rows, and `?? []` is how every reader of them
  // treats it: there is nothing to offer, exactly as on an empty board.
  const rows = payload.rows ?? []
  const elsewhere = rows.find(
    (candidate) => candidate.ticker !== selected)?.ticker ?? null

  // Rendered once, in the slot the width calls for: at the foot of the rows
  // on a desk, under the panel once the page stacks. Below 900px the panel
  // used to sit under all of this, ~1900px down (critique, 2026-09-01).
  const account = (
    <Account payload={payload} shared={universalMarks(rows)} />
  )

  return (
    <div className="page" ref={page}>
      {/* Placed in the grid explicitly rather than left to auto-flow. As a
          plain third child spanning both columns it took a row of its own,
          which pushed the panel BELOW the list and into the list column --
          the two-pane layout came apart in the one state where the reader
          most needs to keep reading the board that is still on screen. */}
      {error && (
        <p className="oops" role="alert">
          <b>{error.message}</b> Showing the last board that loaded.
          <button type="button"
                  onClick={() => void load(selection, selected)}>Retry</button>
        </p>
      )}
      <Boundary label="The list">
        <ListPane payload={payload} received={received} selection={selection}
                  selected={selected}
                  busy={busy} onSelect={select} onChange={setSelection}
                  onRetry={retry}
                  account={narrow ? null : account}
                  watching={watching} onToggleWatch={toggleWatch} />
      </Boundary>
      {/* Its own boundary, and this is the one that earns them: the panel
          renders arbitrary post text and charts built from series with holes
          in them, and a throw in there must not take the readable list with
          it. `resetKey`, not `key` -- a key would remount the panel and take
          its span selection with it on every row click. */}
      <Boundary label="The panel" resetKey={selected ?? 'none'}>
        <DetailPane ticker={selected} selection={selection}
                    windowHours={payload.window_hours}
                    hasRows={rows.length > 0}
                    baselineDays={rows.find(
                      (r) => r.ticker === selected)?.baseline_days ?? null}
                    fallBack={elsewhere
                      ? { ticker: elsewhere, go: () => select(elsewhere) }
                      : undefined}
                    watching={watching.includes(selected ?? '')}
                    onToggleWatch={selected ? () => void toggleWatch(selected) : undefined} />
      </Boundary>
      {narrow && <div className="account">{account}</div>}
    </div>
  )
}

/** Which ticker the page opens on.
 *
 *  `?t=` wins so a bookmarked ticker survives a reload -- "what happened to
 *  the one I spotted yesterday" is a real question for a radar. Otherwise the
 *  top row, so the page is useful with no clicks at all.
 */
function initialTicker(payload: BoardPayload): string | null {
  const asked = new URLSearchParams(window.location.search).get('t')
  // Shape-checked before it is used. Anything else in `?t=` is a typed or
  // pasted address rather than a ticker, and asking the API about it spends a
  // request to be told what the shape already said. What a ticker CAN be is
  // decided by the exchanges: letters, with a class suffix on some listings
  // (BRK.B, RDS-A), and never longer than a handful of characters.
  if (asked && /^[A-Za-z][A-Za-z0-9.-]{0,9}$/.test(asked)) {
    return asked.toUpperCase()
  }
  return payload.rows?.[0]?.ticker ?? null
}

/** The address bar follows the controls and the selection together.
 *
 *  replaceState, not pushState: flipping a source or picking a ticker is not a
 *  navigation, and building a back-button history out of filter clicks is how
 *  a back button stops meaning anything.
 */
function writeUrl(selection: Selection, ticker: string | null) {
  const query = queryFor(selection) + (ticker ? `&t=${ticker}` : '')
  window.history.replaceState(
    null, '', `${window.location.pathname}?${query}`)
}

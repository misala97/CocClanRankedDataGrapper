import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor, setWatch } from '../api'
import { Boundary } from '../Broken'
import { DetailPane } from '../detail/DetailPane'
import { Account } from '../list/Account'
import { ListPane, universalMarks } from '../list/ListPane'
import { Poller, SLOW_MS, pastFresh, refreshDue, refreshes, untilExpired,
         untilStale } from '../pending'
import { useNarrow } from './narrow'
import type { BoardPayload, Row, Selection } from '../types'

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

/** How one request ended. `shown` put its answer on screen and names the
 *  floor for the next ask; `failed` left the last board up and said so;
 *  `dropped` was aborted or superseded -- something newer took its place,
 *  and it has nothing to report, not even a failure. */
type Outcome =
  | { kind: 'shown'; floor: number | null }
  | { kind: 'failed' }
  | { kind: 'dropped' }
const FAILED: Outcome = { kind: 'failed' }
const DROPPED: Outcome = { kind: 'dropped' }

/** What a wait learns from a request: the server's floor, when it named one. */
function floorOf(outcome: Outcome): number | null {
  return outcome.kind === 'shown' ? outcome.floor : null
}

/** Whether nobody is looking at this tab. Read rather than waited for: a tab
 *  restored in the background never fires a visibilitychange at all. */
function hidden(): boolean {
  return typeof document !== 'undefined'
    && document.visibilityState === 'hidden'
}

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
  // How many answers this page has taken. The two clocks further down are
  // each armed for ONE answer and stand down once another has landed -- which
  // an answer can do in the instant before React re-renders to disarm them,
  // and a clock that fired then would act on a board that is already gone.
  const answers = useRef(0)
  // The reader's own request while one is out: a retry, the refetch after a
  // mark, the one a moved control sends. Never a poll's.
  const own = useRef<Promise<Outcome> | null>(null)

  const fetchAndShow = useCallback(async (next: Selection,
                                          preserveTicker: boolean,
                                          poll: boolean)
      : Promise<Outcome> => {
    // The board as it stands, read before the ask rather than after it: what
    // an answer is compared against is the board it was asked about.
    const was = { asOf: current.current.asOf, rows: current.current.rows }
    // NOT where the wait is ended or restarted. A fetch is one more ask about
    // the same question -- a retry, the refetch after a mark, the one the
    // expiry timer sends when no wait is running -- and the wait's back-off
    // belongs to the question, not to the number of times it has been asked.
    // Only a new selection (the debounced effect below, which ends the old
    // wait the moment a control moves) and an answer that settles it (further
    // down) move the wait.
    const generation = (asked.current += 1)
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller
    // A poll is not a control change: raising the list's busy flag every few
    // seconds would flicker aria-busy at a reader who did nothing.
    if (!poll) setBusy(true)
    try {
      const fresh = await fetchBoard(next, controller.signal, { poll })
      if (generation !== asked.current) return DROPPED
      const at = Date.now()
      answers.current += 1
      setPayload(fresh)
      setReceived(at)
      setError(null)
      // The floor under the next ask. The server's own whenever it named one;
      // five seconds for a board that is stale only by this page's clock,
      // which the server answered before it was and so gave no floor for --
      // and the refresh being waited on takes as long as a build takes, not
      // the second the schedule opens with.
      const floor = fresh.retry_after_ms
        ?? (refreshDue(fresh, at, at) ? SLOW_MS : null)
      // The wait ends here rather than in the effect below. The effect runs a
      // React commit later, and the poller schedules its next ask the moment
      // this function returns -- so a board that arrived would still be
      // followed by one more pointless request.
      //
      // Otherwise the wait hears the floor, whoever asked. A Retry, or the
      // first read of a new selection, is answered by the queue the wait is
      // asking, and an ask already on its timer must not undercut that answer.
      if (!owesABoard(fresh, at)) poller.current?.stop()
      else poller.current?.guide(floor)
      // The ticker an answer is about is the one on screen NOW, whoever
      // asked. The reader goes on clicking while a request is out -- a poll,
      // a Retry, the refetch after a mark or at expiry, a moved control --
      // and an answer that restored the ticker it was sent with put back a
      // row the reader had already left.
      //
      // Selection follows filtering, but a market change is different: the
      // company identity stays the same even when its new market board does
      // not rank it. The detail endpoint can still show its marked fallback.
      // A Retry and the two refetches keep it the same way (`preserveTicker`):
      // each asks again about the board the reader is already reading.
      //
      // A poll is the page asking on the reader's behalf, so its ticker
      // stays, listed in this build or not, as it would through a market
      // switch. Only a reader with no ticker yet is handed the top row.
      //
      // Which leaves one answer that can take the ticker away: a change to
      // any control but the market. The ticker stays only if the new board
      // lists it -- and a waiting shell lists nothing, so there the panel
      // empties with the list rather than describing a company the board
      // beside it has stopped listing.
      const reader = current.current.selected
      const rows = fresh.rows ?? []
      const keep = poll ? reader !== null
        : (preserveTicker || rows.some((row) => row.ticker === reader))
      const nextTicker = keep ? reader : (rows[0]?.ticker ?? null)
      // A poll that brings the same board back has changed nothing to
      // select and nothing to write down. Doing it anyway rewrites the
      // history entry the reader is standing on every few seconds, for as
      // long as the wait lasts, over a board that has not moved.
      if (!(poll && sameBoard(was, fresh))) {
        setSelected(nextTicker)
        writeUrl(next, nextTicker)
      }
      return { kind: 'shown', floor }
    } catch (problem) {
      if (controller.signal.aborted || generation !== asked.current) {
        return DROPPED
      }
      // The previous board stays on screen. A failed refresh is a reason to
      // say so, not a reason to throw away data that is still true.
      setError(problem as BoardUnavailable)
      return FAILED
    } finally {
      if (inflight.current === controller) {
        inflight.current = null
        if (!poll) setBusy(false)
      }
    }
  }, [])

  // Every board request goes out through here. The reader's own is
  // remembered for as long as it is out, so a poll that comes due meanwhile
  // can wait for its answer instead of sending a second request (`begin`).
  const load = useCallback((next: Selection, preserveTicker = false,
                            poll = false)
      : Promise<Outcome> => {
    const answer = fetchAndShow(next, preserveTicker, poll)
    if (!poll) {
      own.current = answer
      void answer.finally(() => {
        if (own.current === answer) own.current = null
      })
    }
    return answer
  }, [fetchAndShow])

  // What the poller asks for, read at the moment it asks rather than closed
  // over: the schedule outlives several renders, and a poll must always
  // describe the selection that is on screen now.
  const current = useRef({ selection, selected,
                           retryAfterMs: payload.retry_after_ms,
                           asOf: payload.as_of, rows: payload.rows })
  current.current = { selection, selected,
                      retryAfterMs: payload.retry_after_ms,
                      asOf: payload.as_of, rows: payload.rows }
  // Every Retry on the page, whichever button it is. Joined, as a poll and
  // the expiry refetch are, when the reader's own request is already out:
  // an abort stops this page listening and does not stop the server, so a
  // board a worker builds for itself was built once more for every extra
  // click -- abort-and-resend, which the debounce on the controls exists to
  // prevent. A poll is never the reader's own, so a Retry over one still
  // goes out.
  const retry = useCallback(() => {
    void (own.current ?? load(current.current.selection, true))
  }, [load])

  // How a wait begins, wherever it begins: the polling effect, or the fresh
  // bound's own clock.
  const begin = useCallback((wait: Poller) => {
    wait.start(
      // A poll that comes due while the reader's own request is out waits
      // for that answer instead of sending another. Sent, it would abort the
      // reader's request -- a retry, a moved control -- so the one board was
      // asked for twice, and the controls were left marked busy by a request
      // nothing remained to finish.
      () => (own.current ?? load(current.current.selection, false, true))
        .then(floorOf),
      current.current.retryAfterMs)
    // A tab that was already in the background when this began -- a session
    // restored behind other windows, a link opened in a new tab -- never
    // fires a visibilitychange, so the state is read rather than waited for.
    // The hub's useVisible() reads it at mount for the same reason, and
    // getting it wrong here is a poll of a shared queue on behalf of a tab
    // nobody has looked at yet.
    if (hidden()) wait.pause()
  }, [load])

  // Freshness is a BOUND, not a verdict. `stale` is what the server saw at
  // the instant it answered; `fresh_seconds` is how long that answer is good
  // for, and a page holding one crosses it with nothing on the wire to say
  // so. A tab left open over lunch would otherwise sit on a board the store
  // stopped considering current forty minutes ago, because the only thing
  // that ever asked was a reader touching a control.
  //
  // Every board crosses it, whoever built it -- the line marks each one
  // stale past it. Only a shared board is WAITED on from here: nothing is
  // queued behind a board a worker built for itself, and asking about it on
  // a timer would only build another synchronously, in every open tab.
  const [passedFresh, setPassedFresh] = useState(
    () => pastFresh(initial, Date.now()))
  useEffect(() => {
    const left = untilStale(payload, received)
    const past = left !== null && left < 0
    setPassedFresh(past)
    if (left === null || past) return
    const armed = answers.current
    const timer = setTimeout(() => {
      if (answers.current !== armed) return
      setPassedFresh(true)
      // The wait begins on this clock, not on the render the line above asks
      // for. When a request goes out is the bound's business, and a renderer
      // is free to batch and defer a commit for as long as it likes; the
      // polling effect adopts the wait it finds running instead of starting
      // a second one.
      const wait = poller.current
      if (wait && !wait.running && refreshes(payload)) begin(wait)
    }, left)
    return () => clearTimeout(timer)
  }, [payload, received, begin])

  // Past its hard expiry a board stops being old and starts being wrong: the
  // rows describe a rolling window that has moved on, and the counts under
  // them are answers to a question about a different span of hours. The
  // client clock is what notices, because a tab left open all afternoon asks
  // the server nothing at all.
  //
  // When a wait is running -- and on a shared board one always is by then,
  // since the fresh bound comes first -- the refetch IS the wait's next ask,
  // sent now: expiry and the refresh the wait is after are one question, and
  // asking it beside the wait was two requests, whichever went second
  // aborting the other. The wait's schedule carries on from its place.
  //
  // With no wait -- a board a worker built for itself, which nothing asks
  // about on a timer -- the refetch is this one request, and it goes out for
  // a reader who is looking. A hidden tab owes it instead, as does a tab
  // whose refetch failed: each answer arms the next expiry, so a refetch sent
  // from the background was a synchronous build every ten minutes for as
  // long as the tab stayed open, and a failed one armed nothing at all.
  const refetched = useRef<string | null>(null)
  // The refetch this page owes, paid when the reader next looks at the tab
  // (the visibility handler below) and dropped once any board lands.
  const owed = useRef<(() => void) | null>(null)
  useEffect(() => {
    const left = untilExpired(payload, received)
    if (left === null) return
    // Asking again for a board that arrives past its own expiry is right
    // once and a hot loop twice: the store never serves one (a row that old
    // reads as missing), but a deployment that did would otherwise have this
    // page fetching as fast as the network allows.
    const again = left <= 0 && refetched.current === payload.as_of
    const armed = answers.current
    const refetch = () => {
      if (answers.current !== armed) return
      refetched.current = payload.as_of
      const wait = poller.current
      if (wait?.running) { wait.askNow(); return }
      if (hidden()) { owed.current = refetch; return }
      // Joined, as a poll is, when the reader's own request is already out:
      // its answer is the one this would fetch.
      void (own.current ?? load(current.current.selection, true))
        .then((outcome) => {
          if (outcome.kind === 'failed' && answers.current === armed) {
            owed.current = refetch
          }
        })
    }
    const timer = setTimeout(refetch, again ? SLOW_MS : Math.max(0, left))
    return () => {
      clearTimeout(timer)
      if (owed.current === refetch) owed.current = null
    }
  }, [payload, received, load])

  // Four states, one behaviour: keep asking. Pending and busy have no board
  // to show, stale has one that is being replaced, and a shared board that
  // has outlived its own fresh bound on this page's clock is in the same
  // position with nobody having told it -- in all four there is an answer
  // coming that nothing else on this page would go and get. A board a worker
  // built for itself has none coming: past the bound it is marked, and
  // asking again is the reader's call.
  //
  // Keyed on the STATE rather than on the payload: a poll that answers
  // "still pending" produces a new payload object every few seconds, and
  // restarting the poller on each one would reset its back-off and its sense
  // of how long the reader has been waiting -- so it would never slow down
  // and never admit the wait is long.
  const waiting = payload.pending || payload.busy || payload.stale
    || (passedFresh && refreshes(payload))
  useEffect(() => {
    const wait = poller.current
    if (!wait) return
    if (!waiting) { wait.stop(); return }
    // Adopted rather than restarted when the fresh bound's clock has already
    // begun it: a restart would take back the step it has just taken. Every
    // other way into this branch finds the poller stopped -- by the cleanup
    // below, by the `!waiting` branch that ran last, or by the selection
    // change that asked a new question.
    if (!wait.running) begin(wait)
    return () => wait.stop()
  }, [waiting, question, begin])

  // A hidden tab is polling a queue on behalf of nobody. Coming back asks
  // once immediately, because the answer is usually already waiting -- and
  // pays whatever the tab owes: an expired board's refetch that came due
  // while nobody was looking, or failed while somebody was.
  useEffect(() => {
    const change = () => {
      if (hidden()) { poller.current?.pause(); return }
      poller.current?.resume()
      const refetch = owed.current
      owed.current = null
      refetch?.()
    }
    document.addEventListener('visibilitychange', change)
    return () => document.removeEventListener('visibilitychange', change)
  }, [])

  const previousMarket = useRef(initial.market)
  // Remembered across a burst: a market flip followed within the debounce by
  // a source toggle must still preserve the ticker the way a market flip does.
  const marketPending = useRef(false)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (previousMarket.current !== selection.market) marketPending.current = true
    previousMarket.current = selection.market
    // The old question is over HERE, where the reader left it, and not 250ms
    // later when the request for the new one goes out. The wait belonged to
    // a selection nobody is on any more: its next poll must not go out, and
    // the answer to the poll already in flight must not land -- it would
    // draw the board the reader stopped waiting for under the controls they
    // just moved, which no abort can prevent for a response already sent.
    // The counter is also what re-arms: a new question earns a fresh
    // schedule, and nothing else in this file resets one.
    poller.current?.stop()
    asked.current += 1
    setQuestion((n) => n + 1)
    // Coalesced. Every toggle used to fire its own request and abort the
    // last; five quick clicks queued five board builds on the server and the
    // fifth waited past the 8s timeout -- "The board did not answer in time"
    // during ordinary toggling (critique, 2026-09-01). Short enough that a
    // single click still feels immediate.
    const timer = setTimeout(() => {
      const marketChanged = marketPending.current
      marketPending.current = false
      void load(selection, marketChanged)
    }, SETTLE_MS)
    return () => clearTimeout(timer)
    // Not keyed on the ticker: picking one is a client-side change that must
    // not refetch the board, and the answer reads whichever is on screen
    // when it lands.
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
          void load(selection, true)
        }
      }
    })
  }, [mark, selection, load])

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

  // Nothing is fetching a replacement for the board on screen: the last
  // request failed, none is out, and no wait is running to ask again. The
  // age line reads it for an expired board, which must not go on promising a
  // recalculation the page has stopped attempting.
  const stalled = error !== null && !busy && !waiting

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
          {/* The page's one Retry while this is up (the age line drops its
              own), and the same guarded ask as every other: it joins a
              request already out, and it keeps the ticker. */}
          <button type="button" onClick={retry}>Retry</button>
        </p>
      )}
      <Boundary label="The list">
        <ListPane payload={payload} received={received} selection={selection}
                  selected={selected}
                  busy={busy} onSelect={select} onChange={setSelection}
                  onRetry={retry} stalled={stalled}
                  retryInBanner={error !== null}
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

/** Whether an answer leaves this page with something still to go and get.
 *
 *  `received` is when it arrived, which is the whole of how long this page
 *  has held it at the moment it is asked. */
function owesABoard(board: BoardPayload, received: number): boolean {
  return board.pending || board.busy || refreshDue(board, received, received)
}

/** Whether two answers are the same board: the same build, listing the same
 *  rows in the same order. What a poll that brought nothing new looks like,
 *  and what a poll answering "still pending" looks like too. */
function sameBoard(was: { asOf: string | null; rows: Row[] | null },
                   fresh: BoardPayload): boolean {
  if (was.asOf !== fresh.as_of) return false
  if (was.rows === null || fresh.rows === null) return was.rows === fresh.rows
  return was.rows.length === fresh.rows.length
    && was.rows.every((row, at) => row.ticker === fresh.rows![at]!.ticker)
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

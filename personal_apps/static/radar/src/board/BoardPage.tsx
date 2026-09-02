import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor, setWatch } from '../api'
import { Boundary } from '../Broken'
import { DetailPane } from '../detail/DetailPane'
import { Account } from '../list/Account'
import { ListPane, universalMarks } from '../list/ListPane'
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
  const [selection, setSelection] = useState<Selection>({
    market: initial.market,
    sources: initial.sources,
    segments: initial.segments,
    window: initial.window_hours,
    minVenues: initial.min_venues,
  })
  const [selected, setSelected] = useState<string | null>(
    () => initialTicker(initial))
  // The caller's marks. Optimistic: the star flips before the server
  // answers, the server's list replaces it, and a refusal puts it back.
  // The board's own payload also carries the list, so a refetch keeps it
  // true without a second request.
  const [watching, setWatching] = useState<string[]>(initial.watching ?? [])
  useEffect(() => { setWatching(payload.watching ?? []) }, [payload])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BoardUnavailable | null>(null)
  const inflight = useRef<AbortController | null>(null)
  // The board embedded in the document already matches the initial selection,
  // so the first effect run has nothing to fetch.
  const first = useRef(true)

  const load = useCallback(async (next: Selection, ticker: string | null,
                                  preserveTicker = false) => {
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller
    setBusy(true)
    try {
      const fresh = await fetchBoard(next, controller.signal)
      setPayload(fresh)
      setError(null)
      // Selection follows filtering, but a market change is different: the
      // company identity stays the same even when its new market board does
      // not rank it. The detail endpoint can still show its marked fallback.
      const stillThere = fresh.rows.some((row) => row.ticker === ticker)
      const nextTicker = (preserveTicker || stillThere) ? ticker
        : (fresh.rows[0]?.ticker ?? null)
      setSelected(nextTicker)
      writeUrl(next, nextTicker)
    } catch (problem) {
      if (controller.signal.aborted) return
      // The previous board stays on screen. A failed refresh is a reason to
      // say so, not a reason to throw away data that is still true.
      setError(problem as BoardUnavailable)
    } finally {
      if (inflight.current === controller) {
        inflight.current = null
        setBusy(false)
      }
    }
  }, [])

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

  const toggleWatch = useCallback(async (ticker: string) => {
    const before = watching
    const on = !before.includes(ticker)
    setWatching(on ? [...before, ticker] : before.filter((t) => t !== ticker))
    try {
      setWatching(await setWatch(ticker, on))
      // The watched rows are built server-side; a refetch brings the new
      // one in (or takes the old one out). Memo hit, so instant.
      void load(selection, selected, true)
    } catch {
      setWatching(before)
    }
  }, [watching, selection, selected, load])

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
  const elsewhere = payload.rows.find(
    (candidate) => candidate.ticker !== selected)?.ticker ?? null

  // Rendered once, in the slot the width calls for: at the foot of the rows
  // on a desk, under the panel once the page stacks. Below 900px the panel
  // used to sit under all of this, ~1900px down (critique, 2026-09-01).
  const account = (
    <Account payload={payload} shared={universalMarks(payload.rows)} />
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
        <ListPane payload={payload} selection={selection} selected={selected}
                  busy={busy} onSelect={select} onChange={setSelection}
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
                    hasRows={payload.rows.length > 0}
                    baselineDays={payload.rows.find(
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
  return payload.rows[0]?.ticker ?? null
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

import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor } from '../api'
import { Boundary } from '../Broken'
import { DetailPane } from '../detail/DetailPane'
import { ListPane } from '../list/ListPane'
import type { BoardPayload, Selection } from '../types'

/** The board: a list of what deserves attention beside one ticker in depth.
 *
 *  Two panes rather than one page of cards, because there are two different
 *  questions here. The list answers "which of these is worth my time"; the
 *  panel answers "is this real". Cramming both into a 300px card is what made
 *  the previous surface unreadable -- every fact the tool knew had to fit
 *  there, because there was nowhere to hand anything off to.
 */
export function BoardPage({ initial }: { initial: BoardPayload }) {
  const [payload, setPayload] = useState(initial)
  const [selection, setSelection] = useState<Selection>({
    sources: initial.sources,
    segments: initial.segments,
    window: initial.window_hours,
    minVenues: initial.min_venues,
  })
  const [selected, setSelected] = useState<string | null>(
    () => initialTicker(initial))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BoardUnavailable | null>(null)
  const inflight = useRef<AbortController | null>(null)
  // The board embedded in the document already matches the initial selection,
  // so the first effect run has nothing to fetch.
  const first = useRef(true)

  const load = useCallback(async (next: Selection, ticker: string | null) => {
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller
    setBusy(true)
    try {
      const fresh = await fetchBoard(next, controller.signal)
      setPayload(fresh)
      setError(null)
      // Selection follows the board: a ticker the new filters excluded is no
      // longer there to show, and leaving the panel on it would put a ticker
      // on screen that the list beside it says is not in view.
      const stillThere = fresh.rows.some((row) => row.ticker === ticker)
      const nextTicker = stillThere ? ticker : (fresh.rows[0]?.ticker ?? null)
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

  useEffect(() => {
    if (first.current) { first.current = false; return }
    void load(selection, selected)
    // Deliberately not keyed on `selected`: picking a ticker is a client-side
    // change that must not refetch the board.
  }, [selection, load])

  const select = useCallback((ticker: string) => {
    setSelected(ticker)
    writeUrl(selection, ticker)
  }, [selection])

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

  return (
    <div className="page">
      {/* Placed in the grid explicitly rather than left to auto-flow. As a
          plain third child spanning both columns it took a row of its own,
          which pushed the panel BELOW the list and into the 420px column --
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
                  busy={busy} onSelect={select} onChange={setSelection} />
      </Boundary>
      {/* Its own boundary, and this is the one that earns them: the panel
          renders arbitrary post text and charts built from series with holes
          in them, and a throw in there must not take the readable list with
          it. Keyed on the ticker so a boundary tripped by one panel resets
          when the reader moves to another. */}
      <Boundary label="The panel" key={selected ?? 'none'}>
        <DetailPane ticker={selected} selection={selection}
                    windowHours={payload.window_hours}
                    hasRows={payload.rows.length > 0}
                    fallBack={elsewhere
                      ? { ticker: elsewhere, go: () => select(elsewhere) }
                      : undefined} />
      </Boundary>
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

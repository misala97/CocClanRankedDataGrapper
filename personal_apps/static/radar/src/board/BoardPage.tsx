import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor } from '../api'
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
    segment: initial.segment,
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

  return (
    <div className="page">
      <ListPane payload={payload} selection={selection} selected={selected}
                busy={busy} onSelect={select} onChange={setSelection} />
      {error && (
        <p className="oops" role="alert">
          <b>{error.message}</b> Showing the last board that loaded.
          <button type="button"
                  onClick={() => void load(selection, selected)}>Retry</button>
        </p>
      )}
      <DetailPane ticker={selected} selection={selection}
                  windowHours={payload.window_hours} />
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
  if (asked) return asked.toUpperCase()
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

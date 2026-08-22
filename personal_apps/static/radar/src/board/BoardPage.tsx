import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor } from '../api'
import { plural, sourceLabel, stampTime } from '../format'
import type { BoardPayload, Selection } from '../types'
import { Controls } from './Controls'
import { LeadCard } from './LeadCard'
import { MarkExplainer } from './Marks'
import { ScanRow } from './ScanRow'
import { peak } from './geometry'

export function BoardPage({ initial }: { initial: BoardPayload }) {
  const [payload, setPayload] = useState(initial)
  const [selection, setSelection] = useState<Selection>({
    sources: initial.sources,
    segment: initial.segment,
    window: initial.window_hours,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<BoardUnavailable | null>(null)
  const inflight = useRef<AbortController | null>(null)
  // The board embedded in the document already matches the initial selection,
  // so the first effect run has nothing to fetch.
  const first = useRef(true)

  const load = useCallback(async (next: Selection) => {
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller
    setBusy(true)
    try {
      const fresh = await fetchBoard(next, controller.signal)
      setPayload(fresh)
      setError(null)
      // The address bar follows the controls, so a board worth looking at
      // twice can be bookmarked. replaceState, not pushState: flipping a
      // source is not a navigation, and building a back-button history out of
      // filter clicks is how a back button stops meaning anything.
      window.history.replaceState(null, '', `${window.location.pathname}?${queryFor(next)}`)
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
    void load(selection)
  }, [selection, load])

  const leads = payload.rows.slice(0, payload.lead_count)
  const rest = payload.rows.slice(payload.lead_count)
  // One scale across the three lead charts, so a tall bar in the first card
  // means more mentions than a short bar in the third.
  const chatterMax = Math.max(1, ...leads.map((row) => peak(row.series)))

  return (
    <MarkExplainer>
      <div className="wrap">
        <header className="masthead">
          <h1>Radar</h1>
          <p className="stamp">
            <b>{payload.rows.length}</b>{' '}
            {plural(payload.rows.length, 'ticker', 'tickers')}
            <span className="sep"> · </span>
            last <b>{payload.window_hours}h</b>
            <span className="sep"> · </span>
            {stampTime(payload.generated_at)}
            <span className="sep"> · </span>
            baselines over 30 days
          </p>
        </header>

        <Controls payload={payload} selection={selection} busy={busy}
                  onChange={setSelection} />

        {error && (
          <p className="oops" role="alert">
            <b>{error.message}</b> Showing the last board that loaded.
            <button type="button" onClick={() => void load(selection)}>Retry</button>
          </p>
        )}

        {payload.rows.length === 0 ? <Empty payload={payload} /> : (
          <>
            <div className="head">
              <h2>Talked about, not yet priced</h2>
              <p>chatter against price, last {payload.series_hours} hours</p>
            </div>
            <div className="leads">
              {leads.map((row) => (
                <LeadCard key={row.ticker} row={row} chatterMax={chatterMax}
                          windowHours={payload.window_hours} />
              ))}
            </div>

            {rest.length > 0 && (
              <>
                <div className="head">
                  <h2>Also moving</h2>
                  <p>ranked by the same measure</p>
                </div>
                <div className="cols" aria-hidden="true">
                  <div>Ticker</div>
                  <div>{payload.series_hours}h chatter</div>
                  <div className="n">
                    {payload.triplet_hours.map((h) => `${h}h`).join(' · ')}
                  </div>
                  <div className="n">Divergence</div>
                  <div className="n">Mentions</div>
                  <div className="n">Authors</div>
                  <div className="n">Price {payload.window_hours}h</div>
                </div>
                {rest.map((row) => (
                  <ScanRow key={row.ticker} row={row}
                           triplet={payload.triplet_hours} />
                ))}
              </>
            )}

            <p className="foot prose">
              Divergence spans <code>-2</code> to <code>+1</code>: chatter can
              fall below normal, while price only counts magnitude. The three
              z-scores show whether a move is <em>building</em> or{' '}
              <em>fading</em> — a hot 1h against a cool 24h is new. Marks say
              when a number cannot be taken at face value. Nothing here is
              advice; every figure describes what was observed.
            </p>
          </>
        )}
      </div>
    </MarkExplainer>
  )
}

/** The empty state teaches the filter rather than announcing a void.
 *
 *  Two genuinely different situations produce zero rows and they need
 *  different sentences: a segment nobody is talking about right now, and a
 *  board where nothing anywhere cleared the eligibility floor.
 */
function Empty({ payload }: { payload: BoardPayload }) {
  const filtered = payload.segment !== null
  return (
    <div className="empty">
      <h3>{filtered ? 'Nothing in this segment right now' : 'Nothing has cleared the floor'}</h3>
      {filtered ? (
        <p className="prose">
          No ticker in this segment cleared the floor in the last{' '}
          {payload.window_hours} hours. Try <b>All</b>, or a longer window.
        </p>
      ) : (
        <p className="prose">
          A ticker reaches the board on volume, distinct authors and distinct
          wording together — one determined account posting the same line forty
          times does not count. A quiet overnight hour reading empty is the
          system working.
        </p>
      )}
      <p className="prose">
        Sources on: {payload.sources.map(sourceLabel).join(', ')}.
      </p>
    </div>
  )
}

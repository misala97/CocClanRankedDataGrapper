import { useCallback, useEffect, useRef, useState } from 'react'

import { BoardUnavailable, fetchBoard, queryFor } from '../api'
import { plural, pricesAreMoving, sessionLabel, sourceLabel, stampTime } from '../format'
import type { BoardPayload, ChartSpan, Mark, Selection } from '../types'
import { Controls } from './Controls'
import { LeadCard } from './LeadCard'
import { MarkExplainer } from './Marks'
import { ScanRow } from './ScanRow'
import { peak, peakOf, sliceChart } from './geometry'

export function BoardPage({ initial }: { initial: BoardPayload }) {
  const [payload, setPayload] = useState(initial)
  const [selection, setSelection] = useState<Selection>({
    sources: initial.sources,
    segment: initial.segment,
    window: initial.window_hours,
    minVenues: initial.min_venues,
  })
  const [busy, setBusy] = useState(false)
  // Client-side only: the payload holds the whole year, so switching span
  // costs no request. Defaults to 24h -- the operational "is this spiking
  // now" view, and the only span with a meaningful amount of chatter today.
  const [span, setSpan] = useState<ChartSpan>('24h')
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
  // One chatter scale across the three lead cards, so a tall bar in the first
  // means more mentions than a short bar in the third. It has to follow the
  // span: at 24h the source is the hourly series, at anything longer it is the
  // sliced daily array, and the two are on completely different magnitudes.
  const chatterMax = Math.max(1, ...leads.map((row) => (
    span === '24h'
      ? peak(row.series)
      : (row.chart ? peakOf(sliceChart(row.chart, span).chatter) : 0))))
  // With the exchange shut there is no price movement to diverge from, so the
  // board ranks on chatter and says so. Presenting the same "Divergence"
  // heading over what is really a chatter score would be the quiet kind of
  // wrong -- the number still looks authoritative.
  const ranked = pricesAreMoving(payload.session) ? 'divergence' : 'chatter'
  // A mark on every single row is not a mark, it is a property of the board.
  // Forty-six `provisional` badges down one column is noise the eye learns to
  // skip, which is the opposite of what a trust mark is for -- and it is the
  // same mistake as tagging every ticker no-print because it is Saturday.
  // Lifted to a sentence; the per-row badge stays for anything selective.
  const universal = universalMarks(payload)

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

        {/* Not decoration. Nights and weekends are around 60% of the clock,
            and during them the headline number stops meaning what its label
            says -- so the label changes and the reason is stated, rather than
            the reader being left to infer it from a column of zeroes. */}
        <p className={ranked === 'chatter' ? 'session shut' : 'session'}>
          <b>{sessionLabel(payload.session)}</b>
          {ranked === 'chatter'
            ? ' — no price is moving, so these are ranked by chatter against '
              + 'each ticker’s own normal. Good for deciding what to watch '
              + 'when it opens; divergence needs a live tape and returns with one.'
            : ' — ranked by the gap between chatter and price.'}
          {universal.length > 0 && (
            <>
              {' '}Every row is <b>{universal.join(' and ')}</b>, so it is said
              once here instead of {payload.rows.length} times down the column.
            </>
          )}
        </p>

        <Controls payload={payload} selection={selection} busy={busy}
                  onChange={setSelection} span={span} onSpan={setSpan} />

        {error && (
          <p className="oops" role="alert">
            <b>{error.message}</b> Showing the last board that loaded.
            <button type="button" onClick={() => void load(selection)}>Retry</button>
          </p>
        )}

        {payload.rows.length === 0 ? <Empty payload={payload} /> : (
          <>
            <div className="head">
              <h2>{ranked === 'chatter'
                ? 'Loudest against their own normal'
                : 'Talked about, not yet priced'}</h2>
              <p>{ranked === 'chatter'
                ? `chatter over the last ${payload.series_hours} hours`
                : `chatter against price, last ${payload.series_hours} hours`}</p>
            </div>
            <div className="leads">
              {leads.map((row) => (
                <LeadCard key={row.ticker} row={row} chatterMax={chatterMax}
                          windowHours={payload.window_hours} ranked={ranked}
                          hiddenMarks={universal} span={span} />
              ))}
            </div>

            {rest.length > 0 && (
              <>
                <div className="head">
                  <h2>Also moving</h2>
                  <p>ranked by the same measure</p>
                </div>
                <div className="cols" aria-hidden="true">
                  {/* SIX cells, matching six grid tracks. A seventh would
                      silently shift every column right of it. */}
                  <div>Ticker</div>
                  <div>{span} chart</div>
                  <div className="n">
                    {payload.triplet_hours.map((h) => `${h}h`).join(' · ')}
                  </div>
                  <div className="n">
                    {ranked === 'chatter' ? 'Chatter z' : 'Divergence'}
                  </div>
                  <div className="n">Mentions / people / venues</div>
                  <div className="n">Price {payload.window_hours}h</div>
                </div>
                {rest.map((row) => (
                  <ScanRow key={row.ticker} row={row} ranked={ranked}
                           hiddenMarks={universal} span={span}
                           allSources={payload.all_sources}
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

/** Marks carried by every row on the board.
 *
 *  Returned so the surface can state them once instead of badging each row.
 *  Requires more than one row: on a single-row board "every row" is a
 *  coincidence, not a property.
 */
function universalMarks(payload: BoardPayload): Mark[] {
  if (payload.rows.length < 2) return []
  const first = payload.rows[0]
  if (!first) return []
  return first.marks.filter(
    (mark) => payload.rows.every((row) => row.marks.includes(mark)))
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

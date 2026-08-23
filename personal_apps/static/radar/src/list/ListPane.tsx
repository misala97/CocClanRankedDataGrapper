import { Controls } from '../board/Controls'
import { magnitudes } from '../board/geometry'
import { Excluded } from './Excluded'
import { TickerRow } from './TickerRow'
import type { BoardPayload, Mark, Row, Selection } from '../types'

/** What a mark means when EVERY row on the board carries it.
 *
 *  A mark carried by every row is not a mark -- the same rule the session
 *  state follows, said once by the page instead of fourteen times down the
 *  list. It is also the only honest version of the header: the board used to
 *  claim "baselines over 30 days" while every row it listed was flagged
 *  provisional, which is the opposite of true.
 */
// Exhaustive over Mark on purpose: a new mark will not compile until
// someone decides what the board says when every row carries it.
const UNIVERSAL: Record<Mark, string> = {
  provisional: 'every baseline here is under 14 days old',
  'single-source': 'every row here came from a single source',
  'no-print': 'no tape has printed in this window',
  partial: 'every source here was truncated, so the counts are low',
}

/** Marks shared by the whole board, in the order they are written above.
 *
 *  Two rows minimum: on a one-row board "every row" is trivially true, and
 *  moving the only row's mark into the header would hide it from the place a
 *  reader is looking. */
export function universalMarks(rows: Row[]): Mark[] {
  if (rows.length < 2) return []
  return (Object.keys(UNIVERSAL) as Mark[]).filter(
    (mark) => rows.every((row) => row.marks.includes(mark)))
}

/** The board's state, said once by the page rather than by every row.
 *
 *  With the exchange shut there is no price movement to diverge from, so the
 *  ranking falls through to chatter -- which is the useful answer at 23:00 on
 *  a Sunday, and only honest if the page says which of the two rankings the
 *  reader is looking at.
 */
function Finding({ payload, shared }: {
  payload: BoardPayload
  shared: Mark[]
}) {
  const count = payload.rows.length
  const tickers = count === 1 ? '1 ticker' : `${count} tickers`
  const baselines = shared.includes('provisional')
    ? UNIVERSAL.provisional
    : 'baselines over 30 days'
  const rest = shared.filter((mark) => mark !== 'provisional')

  return (
    <p className="finding">
      {payload.session === 'closed' ? (
        <>
          No price is moving, so these are ranked by <b>chatter against each
          ticker&rsquo;s own normal</b> — what to look at when it opens.
          {' '}<b>{tickers}</b> cleared the bar in the last
          {' '}<b>{payload.window_hours}h</b>,{' '}
          <span className={shared.length ? 'shared' : undefined}>{baselines}</span>.
        </>
      ) : (
        <>
          <b>{tickers}</b> above their normal in the last
          {' '}<b>{payload.window_hours}h</b> ·{' '}
          <span className={shared.length ? 'shared' : undefined}>{baselines}</span>
        </>
      )}
      {rest.map((mark) => (
        <span key={mark} className="shared"> · {UNIVERSAL[mark]}</span>
      ))}
    </p>
  )
}

/** The list: what the board found, and an account of what it did not show.
 *
 *  Replaces the two-tier arrangement of three lead cards over scan rows. That
 *  split bought visual variety at the cost of making identical data look like
 *  two different kinds of thing, and it forced every fact about a ticker into
 *  a 300px card because there was nowhere else to put it.
 *
 *  The magnitude scale is computed here rather than per row, because the point
 *  of it is that the rows share one -- a bar scaled inside its own row would
 *  make every row look equally loud.
 */
export function ListPane({ payload, selection, selected, busy, onSelect,
                          onChange }: {
  payload: BoardPayload
  selection: Selection
  selected: string | null
  busy: boolean
  onSelect: (ticker: string) => void
  onChange: (next: Selection) => void
}) {
  const mags = magnitudes(payload.rows)
  const shared = universalMarks(payload.rows)

  return (
    <aside className="list">
      <div className="lhead">
        <div className="brand">
          <h1>Radar</h1>
          {payload.session === 'closed' && (
            <span className="state"><b>market closed</b></span>
          )}
        </div>
        <Finding payload={payload} shared={shared} />
      </div>

      <Controls payload={payload} selection={selection} busy={busy}
                onChange={onChange} />

      <div className="rows">
        {payload.rows.map((row) => (
          <TickerRow key={row.ticker} row={row} onSelect={onSelect}
                     magnitude={mags[row.ticker]} suppress={shared}
                     selected={row.ticker === selected} />
        ))}
        {payload.rows.length === 0 && (
          // Where the first row would have been, not as a footnote under an
          // empty frame: on this board it is the entire answer.
          <p className="none" role="status">
            Nothing cleared the bar in this window.
          </p>
        )}
        <Excluded payload={payload} />
      </div>
    </aside>
  )
}

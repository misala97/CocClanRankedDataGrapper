import { Controls } from '../board/Controls'
import { Excluded } from './Excluded'
import { TickerRow } from './TickerRow'
import type { BoardPayload, Selection } from '../types'

/** The board's state, said once by the page rather than by every row.
 *
 *  A mark carried by every row is not a mark. With the exchange shut there is
 *  no price movement to diverge from, so the ranking falls through to chatter
 *  -- which is the useful answer at 23:00 on a Sunday, and only honest if the
 *  page says which of the two rankings the reader is looking at.
 */
function Finding({ payload }: { payload: BoardPayload }) {
  const count = payload.rows.length
  const tickers = count === 1 ? '1 ticker' : `${count} tickers`

  if (payload.session === 'closed') {
    return (
      <p className="finding">
        No price is moving, so these are ranked by <b>chatter against each
        ticker&rsquo;s own normal</b> — what to look at when it opens.
        {' '}<b>{tickers}</b> cleared the bar in the last
        {' '}<b>{payload.window_hours}h</b>.
      </p>
    )
  }
  return (
    <p className="finding">
      <b>{tickers}</b> above their normal in the last
      {' '}<b>{payload.window_hours}h</b> · baselines over 30 days
    </p>
  )
}

/** The list: what the board found, and an account of what it did not show.
 *
 *  Replaces the two-tier arrangement of three lead cards over scan rows. That
 *  split bought visual variety at the cost of making identical data look like
 *  two different kinds of thing, and it forced every fact about a ticker into
 *  a 300px card because there was nowhere else to put it.
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
  return (
    <aside className="list">
      <div className="lhead">
        <div className="brand">
          <h1>Radar</h1>
          {payload.session === 'closed' && (
            <span className="state">market closed</span>
          )}
        </div>
        <Finding payload={payload} />
      </div>

      <Controls payload={payload} selection={selection} busy={busy}
                onChange={onChange} />

      <div className="rows">
        {payload.rows.map((row) => (
          <TickerRow key={row.ticker} row={row} onSelect={onSelect}
                     selected={row.ticker === selected} />
        ))}
        {payload.rows.length === 0 && (
          <p className="below" role="status">
            Nothing cleared the bar in this window.
          </p>
        )}
        <Excluded payload={payload} />
      </div>
    </aside>
  )
}

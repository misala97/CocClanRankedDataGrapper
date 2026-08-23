import { chatterRuns, peak } from '../board/geometry'
import type { Clause, Row } from '../types'

/** The row sparkline. Small on purpose: it says "this is building" or "this
 *  faded", and every quantity it implies is in the phrase as text. */
const BOX = { width: 54, height: 18, pad: 0 }

/** One row of the list.
 *
 *  The middle line is the row's reason for existing, and it arrives from the
 *  server as typed clauses. This component styles by `kind` and never reads
 *  the numbers to build wording of its own -- that judgement lives in
 *  phrasing.py and having it in two places is having two answers.
 *
 *  A link, not a button, because a ticker has a URL. Middle-click and
 *  copy-link work, and the click handler only exists to avoid a full page
 *  load for a selection the client can make itself.
 */
export function TickerRow({ row, selected, onSelect }: {
  row: Row
  selected: boolean
  onSelect: (ticker: string) => void
}) {
  const runs = chatterRuns(row.series, BOX, peak(row.series))

  return (
    <a className={`row${selected ? ' on' : ''}`}
       href={`?t=${row.ticker}`}
       aria-current={selected ? 'true' : undefined}
       onClick={(event) => {
         // Leave modified clicks to the browser -- they mean "open elsewhere".
         if (event.metaKey || event.ctrlKey || event.shiftKey) return
         event.preventDefault()
         onSelect(row.ticker)
       }}>
      <span className="rtop">
        <span className="tk">{row.ticker}</span>
        <span className="nm">{row.name ?? '—'}</span>
        <svg className="spark" viewBox="0 0 54 18" aria-hidden="true"
             focusable="false" preserveAspectRatio="none">
          {runs.map((d, index) => (
            <path key={index} d={d} fill="none" stroke="var(--mark)"
                  strokeWidth="1.6" strokeLinejoin="round"
                  strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
      </span>
      <span className="phr">
        {row.clauses.map((clause: Clause, index) => (
          <span key={index} className={`c-${clause.kind}`}>{clause.text}</span>
        ))}
      </span>
      <span className="meta">{row.segment}</span>
    </a>
  )
}

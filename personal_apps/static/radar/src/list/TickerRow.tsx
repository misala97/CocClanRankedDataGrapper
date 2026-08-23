import { chatterRuns, peak } from '../board/geometry'
import { rowPrice, segmentLabel } from '../format'
import type { Clause, Row } from '../types'

/** The row sparkline. Small on purpose: it says "this is building" or "this
 *  faded", and every quantity it implies is in the phrase as text. */
const BOX = { width: 56, height: 17, pad: 0 }

/** One row of the list.
 *
 *  The middle line is the row's reason for existing, and it arrives from the
 *  server as typed clauses. This component styles by `kind` and never reads
 *  the numbers to build wording of its own -- that judgement lives in
 *  phrasing.py and having it in two places is having two answers.
 *
 *  `magnitude` is this row's share of the board's shared axis: how far above
 *  its own normal it is, against a scale every row draws on. `undefined` is
 *  not zero -- it is a row with no baseline to be above, and it draws no axis
 *  at all rather than an empty one.
 *
 *  A link, not a button, because a ticker has a URL. Middle-click and
 *  copy-link work, and the click handler only exists to avoid a full page
 *  load for a selection the client can make itself.
 */
export function TickerRow({ row, selected, magnitude, suppress = [], onSelect }: {
  row: Row
  selected: boolean
  magnitude?: number
  /** Marks the whole board carries, which the page states once in its header
   *  instead. A mark on every row is not a mark. */
  suppress?: readonly string[]
  onSelect: (ticker: string) => void
}) {
  const runs = chatterRuns(row.series, BOX, peak(row.series))
  const measured = magnitude !== undefined

  return (
    <a className={`row${selected ? ' on' : ''}${measured ? '' : ' unmeasured'}`}
       href={`?t=${row.ticker}`}
       aria-current={selected ? 'true' : undefined}
       style={measured
         ? ({ '--mag': magnitude.toFixed(3) } as React.CSSProperties)
         : undefined}
       onClick={(event) => {
         // Leave modified clicks to the browser -- they mean "open elsewhere".
         if (event.metaKey || event.ctrlKey || event.shiftKey) return
         event.preventDefault()
         onSelect(row.ticker)
       }}>
      <span className="r1">
        <span className="tk">{row.ticker}</span>
        <span className="nm">{row.name ?? '—'}</span>
        <svg className="spark" viewBox="0 0 56 17" aria-hidden="true"
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
      {/* The marks are the reason this line exists. PRODUCT.md: they are
          load-bearing rather than metadata -- hiding one would let a reader
          act on a number the system already knows is unreliable -- and the
          row rendered its bare segment key and nothing else. */}
      <span className="meta">
        {segmentLabel(row.segment)} · {rowPrice(row.price, row.price_status)}
        {row.marks.filter((mark) => !suppress.includes(mark)).map((mark) => (
          <span key={mark} className="mark"> · {mark}</span>
        ))}
      </span>
    </a>
  )
}

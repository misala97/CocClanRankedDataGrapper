import { chatterRuns, peak } from '../board/geometry'
import { divergence, pricesAreMoving, rankTerm, rowPrice, segmentLabel,
         zscore } from '../format'
import type { Clause, Row, Session } from '../types'

/** The row sparkline. Small on purpose: it says "this is building" or "this
 *  faded", and every quantity it implies is in the phrase as text. */
const BOX = { width: 56, height: 17, pad: 0 }

/** What this row is ranked ON, which is not the same quantity in both
 *  sessions -- see leaderboard.py and the `Finding` sentence in ListPane.
 *
 *  Open: divergence, chatter measured against the price move over the same
 *  window. Shut: there is no price move to measure, so the board ranks on the
 *  chatter z-score alone and the label has to say so.
 */
function rankedBy(row: Row, session: Session) {
  const term = rankTerm(session)
  return {
    ...term,
    value: pricesAreMoving(session)
      ? divergence(row.divergence) : zscore(row.mention_z),
  }
}

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
export function TickerRow({ row, selected, magnitude, session,
                           suppress = [], onSelect }: {
  row: Row
  selected: boolean
  magnitude?: number
  /** The exchange's state, because it decides WHICH number ranks the row. */
  session: Session
  /** Marks the whole board carries, which the page states once in its header
   *  instead. A mark on every row is not a mark. */
  suppress?: readonly string[]
  onSelect: (ticker: string) => void
}) {
  const runs = chatterRuns(row.series, BOX, peak(row.series))
  const measured = magnitude !== undefined
  const ranked = rankedBy(row, session)

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
        {/* The number the list is ORDERED by, on the row, at the end of the
            line the eye already scans.

            It was rendered nowhere. `divergence()` and `zscore()` have been
            written, commented and unit-tested in format.ts since the board
            was built, and no component imported either -- so the board was
            sorted by a quantity the surface never showed, and the reader had
            no way to answer "why is this above that". The magnitude bar made
            it worse rather than better: it draws the RATIO, deliberately (see
            radar.css), so the longest bar on the board is routinely not the
            top row.

            Which number this is depends on the session, because the ranking
            does. With the exchange shut there is no price movement to diverge
            from and the board falls through to ranking on chatter alone --
            printing "divergence" over that would be the heading disagreeing
            with the quantity beneath it, which is the exact bug the header's
            universal-marks machinery exists to prevent. */}
        <span className="score" title={ranked.why}
              aria-label={ranked.why}>
          <span className="k">{ranked.label}</span>
          <b>{ranked.value}</b>
        </span>
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

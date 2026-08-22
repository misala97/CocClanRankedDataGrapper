import { divergence, move, signed, UNKNOWN, zscore } from '../format'
import type { Mark, Row } from '../types'
import { Marks } from './Marks'
import { Sparkline } from './Sparkline'

// The z at which a window is worth calling out. Matches config.ELEVATED_Z on
// the server; duplicated rather than shipped in the payload because it is a
// presentation threshold here, and a row does not change meaning if the two
// ever drift.
const ELEVATED = 2.0

export function ScanRow({ row, triplet, ranked, hiddenMarks = [] }: {
  row: Row
  triplet: number[]
  /** 'divergence' while prices move, 'chatter' while the exchange is shut. */
  ranked: 'divergence' | 'chatter'
  /** Marks every row on the board carries, which the page states once
   *  instead. A badge repeated on all 46 rows is scenery, not a warning. */
  hiddenMarks?: Mark[]
}) {
  const scores = triplet.map((hours) => row.triplet[String(hours)] ?? null)
  const hottest = scores.reduce<number | null>(
    (best, value) => (value !== null && (best === null || value > best) ? value : best),
    null)

  return (
    <div className="row">
      <div className="tick">
        <span className="sym">{row.ticker}</span>
        <span className="co">{row.name ?? ''}</span>
        <Marks marks={row.marks.filter((m) => !hiddenMarks.includes(m))} />
      </div>

      <Sparkline points={row.series} label={`${row.ticker} chatter over 24 hours`} />

      <div className="trip">
        {scores.map((value, index) => (
          <span key={triplet[index]}
                className={cellClass(value, hottest)}
                title={`${triplet[index]}h z-score`}>
            {zscore(value)}
          </span>
        ))}
      </div>

      {/* The ranking column follows the session. With the exchange shut there
          is no price movement to diverge from, so showing "not scored" down
          the whole column would hide the ranking that is actually in use. */}
      {ranked === 'divergence' ? (
        <div className={divergenceClass(row.divergence)}>
          {divergence(row.divergence)}
        </div>
      ) : (
        <div className={row.mention_z !== null && row.mention_z < 0 ? 'dv neg' : 'dv'}>
          {row.mention_z === null ? UNKNOWN : signed(row.mention_z, 1)}
        </div>
      )}

      <div className="n">{row.mentions}</div>
      <div className="n">{row.authors}</div>
      <div className="n">{priceCell(row)}</div>

      {/* Mobile restates the three numeric columns as a caption, because the
          grid drops to two columns below 720px. Same values, one source. */}
      <div className="meta">
        <span><b>{row.mentions}</b> mentions</span>
        <span><b>{row.authors}</b> authors</span>
        <span>{priceCell(row)}</span>
      </div>
    </div>
  )
}

/** Highlight only a leading score that is actually elevated. Marking the
 *  largest of three unremarkable numbers would invent a story out of noise. */
function cellClass(value: number | null, hottest: number | null): string {
  if (value === null) return 'none'
  return value === hottest && value >= ELEVATED ? 'hot' : ''
}

function divergenceClass(value: number | null): string {
  if (value === null) return 'dv none'
  return value < 0 ? 'dv neg' : 'dv'
}

function priceCell(row: Row) {
  // 'stale' means the tape has not printed for several polls. The arithmetic
  // difference between two identical prints is zero, but rendering that as
  // "0.00%" asserts the price held steady when nothing actually traded --
  // which is the exact claim the no-print mark exists to deny.
  if (row.price_status !== 'ok' || row.price_move === null) {
    const why = row.price_status === 'stale'
      ? 'The tape has not printed — no move to measure'
      : 'No quote in this window'
    return <span className="dash" title={why}>{UNKNOWN}</span>
  }
  const text = move(row.price_move)
  const direction = row.price_move > 0 ? 'up' : row.price_move < 0 ? 'down' : ''
  return <span className={direction}>{text}</span>
}

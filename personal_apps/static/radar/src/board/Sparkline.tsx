import type { Point } from '../types'
import { chatterRuns, peak, type Box } from './geometry'

const BOX: Box = { width: 124, height: 26, pad: 3 }

/** 24 hours of chatter as one line, zero-anchored, gaps left empty.
 *
 *  `aria-hidden`, deliberately: every quantity it draws is also on the row as
 *  a number, and reading "a line chart" to a screen reader adds an announcement
 *  without adding a fact. The row's own cells carry the accessible version.
 */
export function Sparkline({ points, label }: { points: Point[]; label: string }) {
  const runs = chatterRuns(points, BOX, peak(points))
  const measured = points.some((p) => p.count !== null)

  return (
    <div className="spark">
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} preserveAspectRatio="none"
           role="img" aria-hidden="true" focusable="false">
        <title>{label}</title>
        {measured
          ? runs.map((d, index) => (
              <path key={index} d={d} fill="none" stroke="var(--mark)"
                    strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round"
                    vectorEffect="non-scaling-stroke" />
            ))
          : (
            // Nothing was measured across the whole window. A dashed rule says
            // that; an empty box would read as "we drew a flat zero".
            <line x1="0" y1={BOX.height / 2} x2={BOX.width} y2={BOX.height / 2}
                  stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 3"
                  vectorEffect="non-scaling-stroke" />
          )}
      </svg>
    </div>
  )
}

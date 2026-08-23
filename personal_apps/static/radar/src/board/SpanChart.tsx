import type { Chart, ChartSpan, Point } from '../types'
import {
  chartRose, chatterRuns, dailyBars, peak, peakOf, pricePath, sliceChart,
  type Box,
} from './geometry'

/** Chatter against price over the selected span, on one axis.
 *
 *  Used at both sizes -- the 124x26 scan cell and the 300x92 lead card --
 *  because they draw the same thing, and a second implementation is a second
 *  place for the two to disagree.
 *
 *  At 24h the source is the hourly `series`, which the daily arrays cannot
 *  express; at every longer span it is the calendar-aligned `chart`. Two code
 *  paths for one component, and an honest split: they are genuinely different
 *  resolutions of different data.
 *
 *  aria-hidden, like the sparkline it replaces: every quantity it draws is on
 *  the row as text already, and announcing "a line chart" adds an
 *  announcement without adding a fact.
 */
export function SpanChart({ chart, series, span, box, label, yMax }: {
  chart: Chart | null
  series: Point[]
  span: ChartSpan
  box: Box
  label: string
  /** A chatter scale shared with sibling charts. The three lead cards pass
   *  one so a tall bar in the first means more mentions than a short bar in
   *  the third; per-card auto-scaling made three unrelated charts look
   *  identically busy. Scan rows omit it and scale to themselves, because
   *  they are read one at a time. */
  yMax?: number
}) {
  const hourly = span === '24h'
  const sliced = chart && !hourly ? sliceChart(chart, span) : null

  const runs = hourly ? chatterRuns(series, box, yMax ?? peak(series)) : []
  const bars = sliced
    ? dailyBars(sliced.chatter, box, yMax ?? peakOf(sliced.chatter))
    : []
  const path = sliced ? pricePath(sliced.closes, box) : ''
  const rose = sliced ? chartRose(sliced.closes) : true
  const blank = hourly ? runs.length === 0 : !path && bars.length === 0

  return (
    <div className="spark">
      <svg viewBox={`0 0 ${box.width} ${box.height}`} preserveAspectRatio="none"
           role="img" aria-hidden="true" focusable="false">
        <title>{label}</title>
        {runs.map((d, index) => (
          <path key={index} className="chat" d={d} fill="none"
                stroke="var(--mark)" strokeWidth="1.7" strokeLinejoin="round"
                strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        ))}
        {bars.map((bar, index) => (
          <rect key={index} x={bar.x} y={bar.y} width={bar.width}
                height={bar.height} fill="var(--mark)"
                opacity={(0.34 + 0.66 * bar.ratio).toFixed(2)} />
        ))}
        {path && (
          <path className="px" d={path} fill="none" strokeWidth="1.7"
                strokeLinejoin="round" strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                stroke={rose ? 'var(--up)' : 'var(--down)'} />
        )}
        {blank && (
          // Nothing measured across the whole span. A dashed rule says so; an
          // empty box would read as a price and a silence that held steady.
          <line x1="0" y1={box.height / 2} x2={box.width} y2={box.height / 2}
                stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke" />
        )}
      </svg>
    </div>
  )
}

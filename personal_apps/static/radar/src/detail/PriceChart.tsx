import type { DetailChart } from '../types'

const W = 860
const H = 300
/** The price lane. Chatter gets its own beneath, not an overlay. */
const PRICE_H = 196
const GAP = 14
const CHAT_H = H - PRICE_H - GAP - 26

/** Price and chatter on one shared x-axis, in two lanes.
 *
 *  Two lanes rather than an overlay because the series do not share a history:
 *  price goes back three years and chatter began on 2026-08-21, growing a day
 *  per day. Overlaid, three days out of a thousand is invisible; in its own
 *  lane it stays legible at every span.
 *
 *  Nothing is drawn where chatter is null. That region is not silence, it is a
 *  stretch nobody was watching, and a zero-height bar would assert the former.
 *  The boundary between the two is drawn explicitly for the same reason.
 *
 *  The price line spans ITS gaps, because a Saturday is not a day the price
 *  stopped existing -- breaking there would render a year as 52 fragments.
 */
export function PriceChart({ chart }: { chart: DetailChart }) {
  const { path, low, high } = pricePath(chart.closes)
  const slot = W / Math.max(chart.chatter.length, 1)
  const peak = chart.chatter.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0) || 1
  const watchIndex = chart.chatter.findIndex((v) => v !== null)

  return (
    <svg className="pxchart" viewBox={`0 0 ${W} ${H}`} role="img"
         preserveAspectRatio="none"
         aria-label={`price over ${chart.span} with chatter beneath`}>
      <line x1="0" y1={PRICE_H} x2={W} y2={PRICE_H}
            stroke="var(--rule-soft)" strokeWidth="1"
            vectorEffect="non-scaling-stroke" />

      {path ? (
        <path className="px" d={path} fill="none" strokeWidth="1.6"
              strokeLinejoin="round" strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              stroke={rose(chart.closes) ? 'var(--up)' : 'var(--down)'} />
      ) : (
        // No stored closes for this span. A dashed rule says so; an empty box
        // would read as a price that held perfectly steady.
        <line className="px-none" x1="0" y1={PRICE_H / 2} x2={W}
              y2={PRICE_H / 2} stroke="var(--rule)" strokeWidth="1"
              strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      )}

      {path && (
        <>
          <text x="4" y="12" className="ax">{money(high)}</text>
          <text x="4" y={PRICE_H - 4} className="ax">{money(low)}</text>
        </>
      )}

      {watchIndex > 0 && (
        <>
          <line className="watch-edge" x1={watchIndex * slot}
                y1={PRICE_H + GAP} x2={watchIndex * slot}
                y2={PRICE_H + GAP + CHAT_H} stroke="var(--mark)"
                strokeWidth="1" strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke" />
          <text className="ax" x="0" y={PRICE_H + GAP + CHAT_H - 6}>
            chatter not yet observed
          </text>
        </>
      )}

      {chart.chatter.map((value, index) => {
        // null is a day nobody watched. 0 is a day we watched and nothing was
        // said. Neither draws a bar -- but a 2px stub for the zero would
        // overstate it into looking like a little chatter, which is why the
        // minimum height applies only once there is something to show.
        if (value === null || value === 0) return null
        const height = Math.max(2, (value / peak) * CHAT_H)
        return (
          <rect className="chat" key={index} x={index * slot}
                y={PRICE_H + GAP + CHAT_H - height}
                width={Math.max(slot - 0.5, 2)} height={height}
                fill="var(--mark)" />
        )
      })}
    </svg>
  )
}

/** The line, drawn ACROSS days the market was shut. Points keep their
 *  calendar index, so a Monday sits three days after the Friday before it. */
function pricePath(closes: (number | null)[]) {
  const real: { value: number; index: number }[] = []
  closes.forEach((value, index) => {
    if (value !== null) real.push({ value, index })
  })
  if (real.length < 2) return { path: '', low: 0, high: 0 }

  const values = real.map((p) => p.value)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const span = high - low || 1
  const last = Math.max(closes.length - 1, 1)

  const path = real.map((point, n) => {
    const x = (point.index / last) * W
    const y = PRICE_H - ((point.value - low) / span) * PRICE_H
    return `${n ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return { path, low, high }
}

/** Direction across the whole visible span, which is the only thing green and
 *  red are allowed to mean on this surface. */
function rose(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  return real.length < 2 || real[real.length - 1]! >= real[0]!
}

function money(value: number): string {
  return value >= 100 ? `$${value.toFixed(0)}` : `$${value.toFixed(2)}`
}

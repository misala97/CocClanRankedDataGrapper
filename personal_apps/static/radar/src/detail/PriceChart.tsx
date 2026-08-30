import { count, money } from '../format'
import type { DetailChart, PanelSpan } from '../types'
import { SessionBands, sessionNames } from './SessionBands'

const W = 912
const H = 300
/** The plot ends here; what is left is a gutter for the axis labels. They
 *  used to sit inside the plot at x=4 and collided with the line itself --
 *  `$0.21` printed straight through a penny stock's own low. On the right,
 *  because that is where the most recent price is and where every broker
 *  chart puts it. */
export const PLOT_R = 848
const GUTTER = PLOT_R + 12
const TICK = PLOT_R + 6

/** The price lane. Chatter gets its own beneath, not an overlay. */
const P_TOP = 8
const P_BOT = 190
const C_TOP = 214
const C_BOT = 272
const X_LABEL_Y = 292

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Price and chatter on one shared x-axis, in two lanes.
 *
 *  Two lanes rather than an overlay because the series do not share a history:
 *  price goes back three years and chatter began on 2026-08-21, growing a day
 *  per day. Overlaid, three days out of a thousand is invisible; in its own
 *  lane it stays legible at every span.
 *
 *  Nothing is drawn where chatter is null. That region is not silence, it is a
 *  stretch nobody was watching, and a zero-height bar would assert the former.
 *  The boundary between the two is drawn explicitly, and the label that names
 *  it is set against that boundary rather than at x=0 -- stranded at the far
 *  left it read as a caption for the whole chart instead of for the gap it
 *  describes.
 *
 *  The price line spans ITS gaps, because a Saturday is not a day the price
 *  stopped existing -- breaking there would render a year as 52 fragments.
 */
export function PriceChart({ chart }: { chart: DetailChart }) {
  const { path, low, high, lastX, lastY } = pricePath(chart.closes)
  const slot = PLOT_R / Math.max(chart.chatter.length, 1)
  const observed = chart.chatter.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0)
  const peak = observed || 1
  const watchIndex = chart.chatter.findIndex((v) => v !== null)
  // -1 is a span nothing was observed in at all, which multiplied out to a
  // negative x and started the chatter baseline one slot off the left edge of
  // the viewBox. Nothing observed anywhere is the whole lane, from zero.
  const watchX = watchIndex > 0 ? watchIndex * slot : 0
  const tone = rose(chart.closes) ? 'var(--up)' : 'var(--down)'
  const sessionContext = sessionNames(chart.sessions)

  // Two groups, and the split is the animation as much as it is the drawing
  // order. `.axes` is the furniture a reader needs before the data means
  // anything -- rules, dates, the gutter numbers -- and it fades in as one
  // piece. `.plot` is what was measured, and it wipes in along x, which is
  // time. Doing that as one clip on one group rather than per element is what
  // makes it affordable: at the 3Y span this draws ~780 bars, and animating
  // each of them would be 780 animations for one gesture.
  //
  // Paint order is unchanged by the grouping: axes first and behind, exactly
  // as the flat list had it.
  return (
    <svg className="pxchart" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`price over ${chart.span} with chatter beneath${
           sessionContext ? `; extended sessions: ${sessionContext}` : ''}`}>
      <g className="axes">
        {/* Classed rather than left as a bare <g>: the gridline labels are
            the ones that must never carry a date on an intraday span, and
            they are told apart from the two labels at the ends of the axis by
            name now that everything shares one `.axes` parent. */}
        {ticks(chart).map(({ x, label }) => (
          <g className="tick" key={label + x}>
            <line x1={x} y1={P_TOP} x2={x} y2={P_BOT} stroke="var(--rule-soft)"
                  strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <text className="ax" x={x} y={X_LABEL_Y} textAnchor="middle">{label}</text>
          </g>
        ))}

        <line x1="0" y1={P_BOT} x2={PLOT_R} y2={P_BOT} stroke="var(--rule)"
              strokeWidth="1" vectorEffect="non-scaling-stroke" />

        {path && (
          <>
            {/* One format for both: `$202` above `$46.33` is two different
                kinds of number stacked in one gutter. The larger end decides. */}
            <Gutter y={priceY(high, low, high)} label={money(high, high)} />
            <Gutter y={priceY(low, low, high)} label={money(low, high)} />
          </>
        )}

        {watchIndex > 0 && (
          <>
            <line x1="0" y1={C_BOT} x2={watchX} y2={C_BOT} stroke="var(--rule)"
                  strokeWidth="1" strokeDasharray="2 4"
                  vectorEffect="non-scaling-stroke" />
            <text className="ax" x={watchX - 10} y={C_TOP + 26} textAnchor="end">
              nothing observed before {slotLabel(chart, watchIndex)}
            </text>
          </>
        )}

        <line x1={watchX} y1={C_BOT} x2={PLOT_R} y2={C_BOT} stroke="var(--rule)"
              strokeWidth="1" vectorEffect="non-scaling-stroke" />

        {/* Only where something was actually counted: `1/d` printed over an
            empty lane would put a number on a measurement nobody took. */}
        {observed > 0 && (
          <Gutter y={C_TOP} label={`${count(observed)}${perSlot(chart)}`} />
        )}

        <text className="ax" x="0" y={X_LABEL_Y}>
          {startLabel(chart)}
        </text>
        {/* "today" names a calendar day. On a chart whose last slot is the last
            fifteen minutes it names the wrong unit entirely. */}
        <text className="ax" x={PLOT_R} y={X_LABEL_Y} textAnchor="end">
          {isIntraday(chart) ? 'now' : 'today'}
        </text>
      </g>

      <SessionBands chart={chart} plotTop={P_TOP} plotBottom={P_BOT}
                    plotRight={PLOT_R} />

      <g className="plot">
        {path ? (
          <path className="px" d={path} fill="none" strokeWidth="1.5"
                strokeLinejoin="round" strokeLinecap="round"
                vectorEffect="non-scaling-stroke" stroke={tone} />
        ) : (
          // No stored closes for this span. A dashed rule says so; an empty box
          // would read as a price that held perfectly steady.
          <line className="px-none" x1="0" y1={P_BOT / 2} x2={PLOT_R}
                y2={P_BOT / 2} stroke="var(--rule)" strokeWidth="1"
                strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        )}

        {/* Where it left off. The eye looks for the last print first, and the
            wipe hands it over last -- the sweep ends on the newest price. */}
        {path && <circle cx={lastX} cy={lastY} r="3.2" fill={tone} />}

        {watchIndex > 0 && (
          <line className="watch-edge" x1={watchX} y1={C_TOP} x2={watchX}
                y2={C_BOT} stroke="var(--mark)" strokeWidth="1"
                strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        )}

        {chart.chatter.map((value, index) => {
          // null is a day nobody watched. 0 is a day we watched and nothing was
          // said. Neither draws a bar -- but a 2px stub for the zero would
          // overstate it into looking like a little chatter, which is why the
          // minimum height applies only once there is something to show.
          if (value === null || value === 0) return null
          const height = Math.max(2, (value / peak) * (C_BOT - C_TOP))
          return (
            <rect className="chat" key={index} x={index * slot}
                  y={C_BOT - height} width={Math.max(slot - 0.4, 1.4)}
                  height={height} fill="var(--mark)" />
          )
        })}
      </g>
    </svg>
  )
}

/** An axis label out in the gutter, tied to its own height by a tick. Without
 *  the tick the number floats beside the chart pointing at nothing. */
function Gutter({ y, label }: { y: number; label: string }) {
  return (
    <>
      <line x1={PLOT_R} y1={y} x2={TICK} y2={y} stroke="var(--rule)"
            strokeWidth="1" vectorEffect="non-scaling-stroke" />
      <text className="ax" x={GUTTER} y={y + 3.5}>{label}</text>
    </>
  )
}

/** Three evenly spaced gridlines, dated. A year of closes with no dates under
 *  it is not a chart, and the span buttons alone do not say where the reader
 *  is looking. */
function ticks(chart: DetailChart): { x: number; label: string }[] {
  const days = chart.closes.length
  if (days < 8) return []
  return [0.25, 0.5, 0.75].map((share) => {
    const index = Math.round((days - 1) * share)
    return {
      x: (index / Math.max(days - 1, 1)) * PLOT_R,
      label: slotLabel(chart, index),
    }
  })
}

/** True where a slot is minutes rather than a calendar day. */
export function isIntraday(chart: DetailChart): boolean {
  return chart.step_minutes < 1440
}

/** The instant slot `index` begins at.
 *
 *  `from` is a full ISO instant. It used to be a bare date and this appended
 *  `T00:00:00Z` to it -- which, once the server started sending a datetime
 *  for the intraday spans, produced `...ZT00:00:00Z` and an Invalid Date on
 *  EVERY span. The tick labels went blank and the React keys became NaN.
 */
function slotAt(chart: DetailChart, index: number): Date {
  return new Date(new Date(chart.from).getTime() + index * chart.step_minutes * 60_000)
}

/** `14:45` on an intraday slot, a date on a calendar one. */
function slotLabel(chart: DetailChart, index: number, withDate = false): string {
  const at = slotAt(chart, index)
  if (isIntraday(chart)) {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Berlin', day: 'numeric', month: 'short',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(at)
    const part = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((candidate) => candidate.type === type)?.value ?? ''
    const day = part('day')
    const month = part('month')
    const hh = part('hour')
    const mm = part('minute')
    // On a week of hourly slots the time alone repeats seven times over, so
    // the day has to ride along or three identical labels appear.
    if (withDate || chart.step_minutes >= 60) {
      return `${day} ${month} ${hh}:${mm}`
    }
    return `${hh}:${mm}`
  }
  return dayLabel(at, withDate, chart.span)
}

function startLabel(chart: DetailChart): string {
  return slotLabel(chart, 0, true)
}

/** The chatter gutter's unit, which is the slot -- not always a day. */
function perSlot(chart: DetailChart): string {
  if (!isIntraday(chart)) return '/d'
  return chart.step_minutes >= 60 ? '/h' : '/15m'
}

/** `21 Aug` inside a month, `Aug` across one, `Aug 2024` when the span is long
 *  enough that the year is the part in question. */
function dayLabel(date: Date, withYear = false, span?: PanelSpan): string {
  const month = MONTHS[date.getUTCMonth()]!
  if (withYear) return `${month} ${date.getUTCFullYear()}`
  if (span === '1M') return `${date.getUTCDate()} ${month}`
  if (span === '3Y') return `${month} ${date.getUTCFullYear()}`
  if (span === undefined) return `${date.getUTCDate()} ${month}`
  return month
}

/** The line, drawn ACROSS days the market was shut. Points keep their
 *  calendar index, so a Monday sits three days after the Friday before it. */
function pricePath(closes: (number | null)[]) {
  const real: { value: number; index: number }[] = []
  closes.forEach((value, index) => {
    if (value !== null) real.push({ value, index })
  })
  if (real.length < 2) return { path: '', low: 0, high: 0, lastX: 0, lastY: 0 }

  const values = real.map((p) => p.value)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const last = Math.max(closes.length - 1, 1)

  const at = (point: { value: number; index: number }) => ({
    x: (point.index / last) * PLOT_R,
    y: priceY(point.value, low, high),
  })

  const path = real.map((point, n) => {
    const { x, y } = at(point)
    return `${n ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  const end = at(real[real.length - 1]!)
  return { path, low, high, lastX: end.x, lastY: end.y }
}

function priceY(value: number, low: number, high: number): number {
  const span = high - low || 1
  return P_BOT - ((value - low) / span) * (P_BOT - P_TOP)
}

/** Direction across the whole visible span, which is the only thing green and
 *  red are allowed to mean on this surface. */
function rose(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  return real.length < 2 || real[real.length - 1]! >= real[0]!
}

import { count, formatMarketDate, money } from '../format'
import type { DetailChart, PanelSpan } from '../types'
import { ChartHover } from './ChartHover'
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

/** One lane (2026-08-30, Michi's pick over the two-lane draft): the panel is
 *  the chart-row at full size. The violet chatter body grows from the floor
 *  through the lower band, the price line rides the upper band of the SAME
 *  canvas, and the two overlap in the middle exactly where a spike meets a
 *  move -- which is the product's whole question, at every zoom. */
export const TOP = 8
export const FLOOR = 272
/** Share of the plot the chatter body may fill, from the floor up. */
export const CHAT_BAND = 0.52
/** Share of the plot the price line is mapped into, from the top down.
 *  The two bands deliberately sum under 1: with them touching, the price
 *  low label and the chatter peak label landed on the same gutter pixel
 *  and the right edge read $256 / 33/h / $203 interleaved. */
const PRICE_BAND = 0.4
const X_LABEL_Y = 292

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Price and chatter on one canvas, over bands that say what kind of time.
 *
 *  The session bands are what make the single lane readable at the longer
 *  spans: nights, weekends and holidays wash gray, the extended sessions
 *  keep their tints, and a missing stretch of price line means one thing
 *  inside a gray band (the market was shut) and another on bare paper (an
 *  outage nobody quoted through).
 *
 *  Nothing is drawn where chatter is null. That region is not silence, it is
 *  a stretch nobody was watching, and the boundary is drawn explicitly. The
 *  ticker's own normal runs through the body as the dashed line, exactly as
 *  on the rows, so "above its normal" reads the same everywhere.
 *
 *  The price line spans its gaps on the CALENDAR spans, because a Saturday is
 *  not a day the price stopped existing -- breaking there would render a year
 *  as 52 fragments (the gray wash names those days instead). On the intraday
 *  spans it breaks at gaps: an hour nobody quoted is a real absence.
 */
export function PriceChart({ chart, currency = 'USD' }: {
  chart: DetailChart
  /** The quote's currency, for the axis and the hover readout. */
  currency?: string
}) {
  const priced = chart.closes.filter((v) => v !== null).length >= 2

  const { paths, gaps, low, high, lastX, lastY } = pricePaths(chart, priced)
  const slot = PLOT_R / Math.max(chart.chatter.length, 1)
  const observed = chart.chatter.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0)
  const normal = chart.normal_per_slot
  // One scale for the talk AND its normal, exactly as the rows do it.
  const peak = Math.max(observed, normal ?? 0) || 1
  const watchIndex = chart.chatter.findIndex((v) => v !== null)
  const peakIndex = chart.chatter.findIndex((v) => v === observed)
  // -1 is a span nothing was observed in at all, which multiplied out to a
  // negative x and started the chatter baseline one slot off the left edge of
  // the viewBox. Nothing observed anywhere is the whole lane, from zero.
  const watchX = watchIndex > 0 ? watchIndex * slot : 0
  const tone = rose(chart.closes) ? 'var(--up)' : 'var(--down)'
  const sessionContext = sessionNames(chart.sessions)
  // With no price the body may reach for the whole plot -- there is no line
  // left to stay out of the way of.
  const band = priced ? CHAT_BAND : 0.94
  const chatter = chatterBody(chart.chatter, peak, slot, band)
  const yNormal = normal !== null ? chatterY(normal, peak, band) : null

  // Two groups, and the split is the animation as much as it is the drawing
  // order. `.axes` is the furniture a reader needs before the data means
  // anything -- rules, dates, the gutter numbers -- and it fades in as one
  // piece. `.plot` is what was measured, and it wipes in along x, which is
  // time. One clip on one group keeps that affordable at the long spans.
  /* The Xetra->Tradegate seam is stated in text NEXT TO the chart, never a
   * tooltip: proxy history must not read as native (spec 8.2/10). */
  const proxyNote = chart.history_proxy && chart.proxy_venue &&
      chart.native_venue
    ? `${chart.proxy_venue} history${chart.native_from
        ? ` through ${formatMarketDate(chart.native_from)}`
        : ''} · ${chart.native_venue} now`
    : null

  return (<>
    {proxyNote ? <p className="history-proxy-note">{proxyNote}</p> : null}
    <svg className="pxchart" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`price over ${chart.span} with chatter beneath${
           sessionContext ? `; extended sessions: ${sessionContext}` : ''}`}>
      <SessionBands chart={chart} plotTop={TOP} plotBottom={FLOOR}
                    plotRight={PLOT_R} />

      <g className="axes">
        {ticks(chart).map(({ x, label }) => (
          <g className="tick" key={label + x}>
            <line x1={x} y1={TOP} x2={x} y2={FLOOR} stroke="var(--rule-soft)"
                  strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <text className="ax" x={x} y={X_LABEL_Y} textAnchor="middle">{label}</text>
          </g>
        ))}

        {priced ? (
          <>
            {/* One format for both: `$202` above `$46.33` is two different
                kinds of number stacked in one gutter. The larger end decides. */}
            <Gutter y={priceY(high, low, high)} label={money(high, high, currency)} />
            <Gutter y={priceY(low, low, high)} label={money(low, high, currency)} />
          </>
        ) : (
          // One sentence instead of an empty upper band. Muted, not amber: a
          // span the poller was not following is an absence, not a caution.
          <text className="ax" x={PLOT_R} y={TOP + 14} textAnchor="end">
            no stored price for this span
          </text>
        )}

        {watchIndex > 0 && (
          <>
            <line x1="0" y1={FLOOR} x2={watchX} y2={FLOOR}
                  stroke="var(--rule)"
                  strokeWidth="1" strokeDasharray="2 4"
                  vectorEffect="non-scaling-stroke" />
            <text className="ax" x={watchX - 10} y={FLOOR - 8} textAnchor="end">
              nothing observed before {slotLabel(chart, watchIndex)}
            </text>
          </>
        )}

        <line x1={watchX} y1={FLOOR} x2={PLOT_R} y2={FLOOR}
              stroke="var(--rule)"
              strokeWidth="1" vectorEffect="non-scaling-stroke" />

        {/* The peak annotates itself, in violet, at its own spike -- the
            right gutter belongs to price alone. Sharing it stacked `$203`
            over `33/h` into one unreadable block (seen live twice). Only
            where something was counted: a number over an empty lane would
            label a measurement nobody took. */}
        {observed > 0 && peakIndex >= 0 && (
          <text className="ax peak" fill="var(--mark)"
                x={Math.min(peakIndex * slot + slot / 2, PLOT_R - 4)}
                y={Math.max(chatterY(observed, peak, band) - 6, 12)}
                textAnchor={peakIndex * slot > PLOT_R - 60 ? 'end' : 'middle'}>
            {count(observed)}{perSlot(chart)}
          </text>
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

      <g className="plot">
        {chatter.areas.map((d, index) => (
          <path key={`a${index}`} d={d} fill="var(--mark-soft)" />
        ))}
        {chatter.lines.map((d, index) => (
          <path key={`l${index}`} d={d} fill="none" stroke="var(--mark)"
                strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"
                vectorEffect="non-scaling-stroke" />
        ))}
        {/* The ticker's own normal, dashed through the talk exactly as the
            rows draw it -- only over the stretch that was observed, because
            left of the boundary there is nothing to measure against. */}
        {yNormal !== null && observed > 0 && (
          <line x1={watchX} y1={yNormal} x2={PLOT_R} y2={yNormal}
                stroke="var(--dim)" strokeWidth="1" strokeDasharray="3 4"
                opacity="0.55" vectorEffect="non-scaling-stroke" />
        )}

        {watchIndex > 0 && (
          <line className="watch-edge" x1={watchX} y1={TOP} x2={watchX}
                y2={FLOOR} stroke="var(--mark)" strokeWidth="1"
                strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        )}

        {/* Price last: where a spike genuinely meets a move the line reads
            over the body, not under it. The dotted bridges go first so the
            measured runs paint over their endpoints. */}
        {gaps.map((d, index) => (
          <path className="px-gap" key={`g${index}`} d={d} fill="none"
                strokeWidth="1.2" strokeDasharray="2 5" opacity="0.55"
                strokeLinecap="round" vectorEffect="non-scaling-stroke"
                stroke={tone} />
        ))}
        {paths.map((d, index) => (
          <path className="px" key={index} d={d} fill="none" strokeWidth="1.8"
                strokeLinejoin="round" strokeLinecap="round"
                vectorEffect="non-scaling-stroke" stroke={tone} />
        ))}

        {/* Where it left off. The eye looks for the last print first, and the
            wipe hands it over last -- the sweep ends on the newest price. */}
        {priced && <circle cx={lastX} cy={lastY} r="3.2" fill={tone} />}
      </g>
      {/* The chart answering the cursor: a hairline on the nearest slot and its
          three facts in words. Last, so it sits over everything it reads. */}
      <ChartHover chart={chart} geometry={{ priced, low, high, peak, band }} currency={currency} />
    </svg>
  </>)
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

/** Where a chatter value sits: zero-anchored at the floor, filling `band`
 *  of the plot upward -- the rows' scale, at panel size. */
export function chatterY(value: number, peak: number, band: number): number {
  return FLOOR - (value / peak) * (FLOOR - TOP) * band
}

/** The chatter body as area polygons plus outlines, one per unbroken run --
 *  the chart-row's drawing at panel scale. Zeros ride the floor; nulls
 *  break the shape. */
function chatterBody(values: (number | null)[], peak: number, slot: number,
                     band: number) {
  const areas: string[] = []
  const lines: string[] = []
  let run: { x: number; y: number }[] = []

  const flush = () => {
    const first = run[0]
    const last = run[run.length - 1]
    if (first === undefined || last === undefined) { run = []; return }
    const xEnd = run.length === 1 ? last.x + Math.max(slot * 0.6, 1) : last.x
    const spine = run.map((p, i) =>
      `${i ? 'L' : ''}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    areas.push(`M${first.x.toFixed(1)},${FLOOR} L${spine}`
      + ` L${xEnd.toFixed(1)},${FLOOR} Z`)
    lines.push(`M${spine}${run.length === 1 ? ` L${xEnd.toFixed(1)},${last.y.toFixed(1)}` : ''}`)
    run = []
  }

  values.forEach((value, index) => {
    if (value === null) { flush(); return }
    run.push({
      // Mid-slot, so a bar-wide unit of time is drawn at its own centre.
      x: index * slot + slot / 2,
      y: chatterY(value, peak, band),
    })
  })
  flush()
  return { areas, lines }
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
export function slotLabel(chart: DetailChart, index: number, withDate = false): string {
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
export function perSlot(chart: DetailChart): string {
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

/** The price line, mapped into the upper band of the shared canvas.
 *
 *  Calendar spans draw ONE path across gaps -- the market being shut on a
 *  Saturday is not a hole in the price's existence, and points keep their
 *  calendar index so a Monday sits three days after its Friday; the gray
 *  wash is what names those days. Intraday spans break at gaps instead: an
 *  unquoted hour is a real absence. Single quoted slots draw nothing on
 *  their own -- a price dot at an arbitrary height reads as a glitch.
 */
function pricePaths(chart: DetailChart, priced: boolean) {
  const closes = chart.closes
  if (!priced) {
    return { paths: [], gaps: [], low: 0, high: 0, lastX: 0, lastY: 0 }
  }

  const real: { value: number; index: number }[] = []
  closes.forEach((value, index) => {
    if (value !== null) real.push({ value, index })
  })
  const values = real.map((p) => p.value)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const last = Math.max(closes.length - 1, 1)

  const at = (point: { value: number; index: number }) => ({
    x: (point.index / last) * PLOT_R,
    y: priceY(point.value, low, high),
  })

  const paths: string[] = []
  const gaps: string[] = []
  // Splitting and bridging is the 15-minute chart's honesty; the hourly
  // week prices from daily-close anchors, whose gaps are structural, and
  // spans them exactly as the month does.
  if (chart.step_minutes < 60) {
    let runPoints: { x: number; y: number }[] = []
    let previous = -2
    const flush = () => {
      if (runPoints.length > 1) {
        paths.push(runPoints.map((p, n) =>
          `${n ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))
      }
      runPoints = []
    }
    let lastOfPrevRun: { x: number; y: number } | null = null
    for (const point of real) {
      const here = at(point)
      if (point.index !== previous + 1 && runPoints.length) {
        const tail = runPoints[runPoints.length - 1]!
        lastOfPrevRun = tail
        flush()
      }
      if (!runPoints.length && lastOfPrevRun) {
        // The dotted bridge: nobody quoted between these two prints, and a
        // solid line there would be a measurement that was never taken --
        // but a field of floating dashes was unreadable as a price at all.
        // Dotted is the chart saying "resumed here", visibly not data.
        gaps.push(`M${lastOfPrevRun.x.toFixed(1)},${lastOfPrevRun.y.toFixed(1)}`
          + ` L${here.x.toFixed(1)},${here.y.toFixed(1)}`)
        lastOfPrevRun = null
      }
      runPoints.push(here)
      previous = point.index
    }
    flush()
  } else {
    paths.push(real.map((point, n) => {
      const { x, y } = at(point)
      return `${n ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' '))
  }

  const end = at(real[real.length - 1]!)
  return { paths, gaps, low, high, lastX: end.x, lastY: end.y }
}

/** High maps to the top pad, low to the bottom of the price band -- the top
 *  `PRICE_BAND` share of the plot, riding above the chatter body with the
 *  overlap in the middle where a spike actually meets a move. */
export function priceY(value: number, low: number, high: number): number {
  const span = high - low || 1
  const height = (FLOOR - TOP) * PRICE_BAND
  return TOP + (1 - (value - low) / span) * height
}

/** Direction across the whole visible span, which is the only thing green and
 *  red are allowed to mean on this surface. */
function rose(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  return real.length < 2 || real[real.length - 1]! >= real[0]!
}

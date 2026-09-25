import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, MouseEvent } from 'react'
import type { SessionRow, Stair, StairCol } from '../types'
import { dayDate, kg1, localParts, setsLine, weekdayDate } from '../format'

/* The drawing's frame, in px. The width is the figure's own: a fixed viewBox
   scaled every label with the page, 13px on a phone and 26px on a tablet. */
const FALLBACK_WIDTH = 358
const GUTTER = 30           // the kg labels
const LEFT = GUTTER + 10    // the first workout
const RIGHT = 6             // after the last one
const TOP = 26              // room for "N ohne Rekord" over the top tread
const PLOT = 128
const PAD = 8
const LANE_GAP = 14         // the deload lane under the plot
const AXIS_GAP = 30         // the months under that
const BOTTOM = 6
const DOT = 4
const RECORD_DOT = 5.5
/** A month name's width at 13px, per character, and the air between two. */
const CHAR = 7.5
const LABEL_GAP = 8

const MONTHS = ['Jan.', 'Feb.', 'März', 'Apr.', 'Mai', 'Juni', 'Juli', 'Aug.', 'Sep.', 'Okt.',
  'Nov.', 'Dez.']

interface Month { x: number; tx: number; anchor: 'start' | 'end'; text: string }

/** A tick at the first workout of every month, and its name where there is
 *  room: a name that would run into one already placed is left out, the tick
 *  kept. A later year's first month is named by the year instead -- January
 *  or not, a lift can skip it -- and a year is placed before any month, so
 *  the drawing never crosses a year unsaid. */
function months(cols: StairCol[], x: (i: number) => number, width: number): Month[] {
  const out: (Month & { from: number; to: number; year: boolean })[] = []
  let seen = ''
  let lastYear = cols.length > 0 ? localParts(cols[0]!.started_at).year : 0
  cols.forEach((col, i) => {
    const { year, month } = localParts(col.started_at)
    const key = `${year}-${month}`
    if (key === seen) return
    seen = key
    const newYear = year !== lastYear
    lastYear = year
    const text = newYear ? String(year) : MONTHS[month - 1]!
    const w = CHAR * text.length
    const flip = x(i) + 4 + w > width
    const from = flip ? x(i) + 4 - w : x(i) - 4
    out.push({ x: x(i), tx: flip ? x(i) + 4 : x(i) - 4, anchor: flip ? 'end' : 'start',
      text, from, to: from + w, year: newYear })
  })
  const placed: [number, number][] = []
  for (const month of [...out.filter((m) => m.year), ...out.filter((m) => !m.year)]) {
    if (placed.every(([from, to]) => month.to + LABEL_GAP <= from || month.from >= to + LABEL_GAP)) {
      placed.push([month.from, month.to])
    } else {
      month.text = ''
    }
  }
  return out.map(({ x: at, tx, anchor, text }) => ({ x: at, tx, anchor, text }))
}

/** Where the lane's one "Deload" goes: beside a ring, where it runs into no
 *  other ring and stays in the drawing -- the last ring's right first, then
 *  its left, then the rings before it. A deload week at the right edge
 *  flipped it left across the ring before. Nowhere free: right of the last
 *  ring, or left of it at the edge, as before. */
function laneLabel(cols: StairCol[], x: (i: number) => number, width: number) {
  const rings = cols.flatMap((col, i) => (col.kind === 'deload' ? [x(i)] : []))
  const w = CHAR * 6
  const free = (from: number, to: number) => from >= GUTTER && to <= width
    && rings.every((at) => at + DOT + 2 <= from || at - DOT - 2 >= to)
  for (const at of [...rings].reverse()) {
    if (free(at + 9, at + 9 + w)) return { x: at + 9, anchor: 'start' as const }
    if (free(at - 9 - w, at - 9)) return { x: at - 9, anchor: 'end' as const }
  }
  const last = rings[rings.length - 1]!
  return last + 9 + w > width ? { x: last - 9, anchor: 'end' as const } : { x: last + 9, anchor: 'start' as const }
}

/** A sentence ending on a date: "07.09." ends it already, "07.09.2025" not. */
const ended = (text: string) => (text.endsWith('.') ? text : `${text}.`)

interface Props {
  stair: Stair
  /** The log row a workout's readout names. */
  rowOf: (col: StairCol) => SessionRow | undefined
}

/**
 * The Rekordtreppe (D9, M2 chart 1): the best estimated max so far as a
 * staircase, every workout a dot on or under its tread, a record a gold dot
 * where the stair climbs. A stall is the flat last tread, "N ohne Rekord",
 * in the stall hue only while it is one. Deloads sit in a lane under the
 * plot: they are no attempt. The target stays in the header, not here.
 *
 * Tap a workout, or walk them with the arrow keys, for its day, 1RM and
 * sets; the readout's two lines are reserved, so nothing moves under the
 * finger. Every number is the server's (stats.record_stair); only the pixels
 * are worked out here.
 */
export function RecordStair({ stair, rowOf }: Props) {
  const figure = useRef<HTMLElement>(null)
  const [width, setWidth] = useState(FALLBACK_WIDTH)
  const [at, setAt] = useState<number | null>(null)

  useLayoutEffect(() => {
    const node = figure.current
    if (node === null) return
    const measure = () => { if (node.clientWidth > 0) setWidth(node.clientWidth) }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const { cols, lo, hi } = stair
  const n = cols.length
  const last = cols[n - 1]!
  const hasLane = cols.some((col) => col.kind === 'deload')
  const bottom = TOP + PLOT
  const lane = bottom + LANE_GAP
  const axis = (hasLane ? lane : bottom) + AXIS_GAP
  const height = axis + BOTTOM
  const step = (width - RIGHT - LEFT) / Math.max(1, n - 1)
  const x = (i: number) => +(LEFT + i * step).toFixed(2)
  const y = (value: number) => +(TOP + PAD + (hi - value) / (hi - lo) * (PLOT - 2 * PAD)).toFixed(2)

  // The treads: one per best, a riser where it climbs.
  let tread = `M${x(0)} ${y(cols[0]!.best)}`
  let rise = 0
  for (let i = 1; i < n; i++) {
    if (cols[i]!.best !== cols[i - 1]!.best) {
      tread += ` H${x(i)} V${y(cols[i]!.best)}`
      rise = i
    }
  }
  const area = `${tread} H${x(n - 1)} V${bottom} H${x(0)} Z`
  const stalled = stair.stalled ? ' is-stall' : ''
  const since = stair.since !== null && stair.since >= 1 ? stair.since : null
  const deloadLabel = hasLane ? laneLabel(cols, x, width) : null

  const select = (i: number) => setAt(Math.max(0, Math.min(n - 1, i)))
  const onClick = (event: MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const px = box.width > 0 ? (event.clientX - box.left) * (width / box.width) : 0
    let best = 0
    for (let i = 1; i < n; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i
    select(best)
  }
  const onKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    select(at === null ? n - 1 : at + (event.key === 'ArrowRight' ? 1 : -1))
  }

  const chosen = at === null ? null : cols[at]!
  const chosenRow = chosen === null ? undefined : rowOf(chosen)
  const label = `Geschätztes Maximum in ${n} Workouts, ${dayDate(cols[0]!.started_at)} bis `
    + `${ended(dayDate(last.started_at))} Bestwert ${kg1(last.best)} kg seit `
    + (since !== null
      ? `${dayDate(cols[rise]!.started_at)}, seitdem ${since} ${since === 1 ? 'Workout' : 'Workouts'} ohne Rekord.`
      : ended(dayDate(cols[rise]!.started_at)))

  return (
    <figure className="stair" ref={figure} tabIndex={0} onKeyDown={onKey}>
      <div className="exlegend">
        <span className="key">
          <svg className="key__stair" viewBox="0 0 18 10" aria-hidden="true">
            <path d="M1 9H6V5H12V1.5H17" />
          </svg>
          Bestwert bis dahin
        </span>
        <span className="key"><span className="key__dot key__dot--done" />Workout</span>
        {cols.some((col) => col.kind === 'record') && (
          <span className="key"><span className="key__dot key__dot--rec" />Rekord</span>
        )}
      </div>
      <svg className="stair__plot" viewBox={`0 0 ${width} ${height}`} width={width} height={height}
        role="img" aria-label={label} onClick={onClick}>
        <g>
          {stair.ticks.map((tick) => (
            <g key={tick}>
              <line className="stair__grid" x1={GUTTER} y1={y(tick)} x2={width} y2={y(tick)} />
              <text className="stair__axis" x={0} y={y(tick) + 4.5}>{tick}</text>
            </g>
          ))}
        </g>
        <g className="chart__ink">
          <path className="stair__area" d={area} />
          <path className="stair__tread" d={tread} />
          <path className={`stair__tread stair__tread--now${stalled}`}
            d={`M${x(rise)} ${y(last.best)} H${x(n - 1)}`} />
          {cols.map((col, i) => {
            if (col.kind === 'deload') {
              return <circle key={i} className="stair__dot stair__dot--deload" cx={x(i)} cy={lane} r={DOT} />
            }
            if (col.kind === 'record') {
              return (
                <circle key={i} className="stair__dot stair__dot--rec chart__pr" cx={x(i)}
                  cy={y(col.e1rm)} r={RECORD_DOT}
                  style={{ '--at': (x(i) / width).toFixed(3) } as CSSProperties} />
              )
            }
            return <circle key={i} className="stair__dot" cx={x(i)} cy={y(col.e1rm)} r={DOT} />
          })}
          {deloadLabel !== null && (
            <text className="stair__axis" x={deloadLabel.x} y={lane + 4.5}
              textAnchor={deloadLabel.anchor}>Deload</text>
          )}
        </g>
        {since !== null && (
          <text className={`stair__now${stalled}`} x={width - 2} y={y(last.best) - 12}
            textAnchor="end">{`${since} ohne Rekord`}</text>
        )}
        {months(cols, x, width).map((month) => (
          <g key={month.x}>
            <line className="stair__tick" x1={month.x} y1={axis - 20} x2={month.x} y2={axis - 14} />
            {month.text !== '' && (
              <text className="stair__axis" x={month.tx} y={axis} textAnchor={month.anchor}>
                {month.text}
              </text>
            )}
          </g>
        ))}
        <g className="stair__sel" visibility={at === null ? 'hidden' : 'visible'}
          transform={`translate(${at === null ? 0 : x(at)} 0)`}>
          <line x1={0} y1={TOP - 2} x2={0} y2={(hasLane ? lane : bottom) + 8} />
        </g>
        <rect className="stair__hit" x={GUTTER} y={0} width={Math.max(0, width - GUTTER)} height={height} />
      </svg>
      {/* After the drawing: its reserved second line then ends the figure
          instead of opening a gap above the key. */}
      <p className="exread" aria-live="polite">
        {chosen === null ? (
          <>
            <span className="exread__l1"><span className="exread__hint">Workout antippen für Details</span></span>
            <span className="exread__l2" />
          </>
        ) : (
          <>
            <span className="exread__l1">
              <b>{weekdayDate(chosen.started_at)}</b>
              {` · 1RM ${kg1(chosen.e1rm)} kg`}
              {chosen.kind === 'record' && <span className="vtag vtag--record">Rekord</span>}
              {/* By the row: a deload the stair climbs at is drawn on it. */}
              {(chosen.kind === 'deload' || chosenRow?.is_deload) && (
                <span className="vtag vtag--deload">Deload</span>
              )}
            </span>
            <span className="exread__l2">{chosenRow !== undefined ? setsLine(chosenRow.sets) : ''}</span>
          </>
        )}
      </p>
    </figure>
  )
}

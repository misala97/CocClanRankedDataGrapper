// Two aligned daily panels (HA1): closes above, retained mention counts
// below, one column per requested date, and a row of date buttons that
// selects a day for the detail beside them.
//
// The chart renders the payload and nothing else: it does not fetch, does
// not aggregate across days and does not decide what may be joined -- that
// is `priceRuns` in analysisTypes.ts, which the tests call directly. A
// shared column is a shared calendar date, not simultaneous measurement:
// closes carry the stored trading date, counts run midnight to midnight
// UTC, and the caption under the panels says so.
//
// Every state has a text as well as a colour: a missing close is an open
// marker with the word in the table, a partial day a hatched bar with its
// caption, an observed zero a labelled baseline tick, and the withheld
// pooled count a question mark. Nothing is tooltip-only.
import { useRef } from 'react'
import type { KeyboardEvent } from 'react'

import type { AnalysisPayload, ChatterDay, PriceDay } from './analysisTypes'
import { chatterLabel, dayLabel, formatClose, priceRuns, priceStateLabel } from './analysisTypes'

const W = 720
const LEFT = 52
const RIGHT = 14
const PRICE_H = 190
const COUNT_H = 150
const PAD_TOP = 18
const PAD_BOTTOM = 14

export function AnalysisChart({ payload, selected, onSelect }: {
  payload: AnalysisPayload
  selected: string | null
  onSelect: (day: string) => void
}) {
  const price = payload.price.days
  const chatter = payload.chatter.days
  const n = price.length
  const plotW = W - LEFT - RIGHT
  const colW = plotW / Math.max(1, n)
  const x = (index: number) => LEFT + (index + 0.5) * colW
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1
      : event.key === 'Home' ? -index : event.key === 'End' ? n - 1 - index : 0
    if (step === 0) return
    event.preventDefault()
    const next = Math.max(0, Math.min(n - 1, index + step))
    buttons.current[next]?.focus()
    onSelect(price[next]!.date)
  }

  // The panels and the day buttons share one box, so the buttons' columns sit
  // under the plotted columns at every width: the buttons row is padded by
  // the same LEFT/RIGHT fractions of W the panels plot inside. On a phone
  // that box keeps a minimum width and scrolls sideways inside itself, which
  // keeps each day button at least 44px wide; the caption below stays put.
  return (
    <div className="rh-an-chart">
      <div className="rh-an-plotscroll">
      <div className="rh-an-plots">
      <PricePanel days={price} x={x} colW={colW} selected={selected} onSelect={onSelect} />
      <CountPanel days={chatter} x={x} colW={colW} selected={selected} onSelect={onSelect} />
      <div className="rh-an-days" role="group" aria-label="Select a day"
           style={{ paddingLeft: `${(LEFT / W) * 100}%`, paddingRight: `${(RIGHT / W) * 100}%` }}>
        {price.map((day, index) => (
          <button
            key={day.date}
            type="button"
            ref={(el) => { buttons.current[index] = el }}
            className={`rh-an-day${selected === day.date ? ' selected' : ''}`}
            aria-pressed={selected === day.date}
            onClick={() => onSelect(day.date)}
            onKeyDown={(event) => onKey(event, index)}
            tabIndex={selected === null ? (index === 0 ? 0 : -1) : (selected === day.date ? 0 : -1)}
          >
            <span className="rh-an-daylabel">{dayLabel(day.date)}</span>
            <span className="rh-an-dayfacts">
              {day.state === 'observed' && day.close !== null ? formatClose(day.close) : '—'}
              {' · '}
              {chatter[index]?.mentions === null || chatter[index]?.overlap_ambiguous
                ? '—' : chatter[index]?.mentions}
            </span>
          </button>
        ))}
      </div>
      </div>
      </div>
      <p className="rh-an-caption muted small">
        Daily closes use the stored trading date. Chatter days run midnight to
        midnight UTC. A shared column is a shared calendar date, not a
        simultaneous measurement.
      </p>
    </div>
  )
}

function PricePanel({ days, x, colW, selected, onSelect }: {
  days: PriceDay[]
  x: (index: number) => number
  colW: number
  selected: string | null
  onSelect: (day: string) => void
}) {
  const observed = days.filter((d) => d.state === 'observed' && d.close !== null)
  const values = observed.map((d) => d.close as number)
  const lo = values.length ? Math.min(...values) : 0
  const hi = values.length ? Math.max(...values) : 1
  const span = hi - lo || Math.max(hi * 0.02, 0.01)
  const top = PAD_TOP
  const bottom = PRICE_H - PAD_BOTTOM
  const y = (value: number) => bottom - ((value - lo) / span) * (bottom - top) * 0.84
    - (bottom - top) * 0.08
  const runs = priceRuns(days)
  const ticks = values.length ? [hi, (hi + lo) / 2, lo] : []
  return (
    <svg className="rh-an-svg price" viewBox={`0 0 ${W} ${PRICE_H}`} role="img"
         aria-label={`Daily closes, ${observed.length} of ${days.length} days observed`}>
      <SelectedColumn days={days} x={x} colW={colW} height={PRICE_H} selected={selected} />
      {ticks.map((tick, index) => (
        <g key={index}>
          <line x1={LEFT} x2={W - RIGHT} y1={y(tick)} y2={y(tick)} className="rh-an-grid" />
          <text x={LEFT - 6} y={y(tick) + 4} className="rh-an-axis" textAnchor="end">
            {formatClose(tick)}
          </text>
        </g>
      ))}
      {values.length === 0 ? (
        <text x={W / 2} y={PRICE_H / 2} className="rh-an-emptytext" textAnchor="middle">
          No usable close in this window
        </text>
      ) : null}
      {runs.filter((run) => run.length > 1).map((run) => (
        <polyline
          key={run[0]}
          className="rh-an-line"
          data-run={run.join(',')}
          points={run.map((index) => `${x(index)},${y(days[index]!.close as number)}`).join(' ')}
        />
      ))}
      {days.map((day, index) => {
        const cx = x(index)
        const label = `${dayLabel(day.date)}: ${priceStateLabel(day)}`
        if (day.state === 'observed' && day.close !== null) {
          return (
            <g key={day.date} className="rh-an-point" onClick={() => onSelect(day.date)}>
              <circle cx={cx} cy={y(day.close)} r={5} data-state="observed" />
              <text x={cx} y={y(day.close) - 10} className="rh-an-value" textAnchor="middle">
                {formatClose(day.close)}
              </text>
              <title>{`${label} ${formatClose(day.close)} USD`}</title>
            </g>
          )
        }
        return (
          <g key={day.date} className="rh-an-point" onClick={() => onSelect(day.date)}>
            <Marker state={day.state} hint={day.calendar_hint} cx={cx} cy={bottom - 6} />
            <title>{label}</title>
          </g>
        )
      })}
    </svg>
  )
}

/** Non-observed days say so in a shape, not only a colour: a hollow circle
 *  for a missing close on a modeled-open day, a short dash on a modeled-
 *  closed one, a small triangle for an unusable row, a struck circle for a
 *  date before the company record. */
function Marker({ state, hint, cx, cy }: {
  state: PriceDay['state']
  hint: PriceDay['calendar_hint']
  cx: number
  cy: number
}) {
  if (state === 'invalid') {
    return <path data-state="invalid" d={`M${cx} ${cy - 6} L${cx + 6} ${cy + 5} L${cx - 6} ${cy + 5} Z`} />
  }
  if (state === 'identity_unverified') {
    return (
      <g data-state="identity_unverified">
        <circle cx={cx} cy={cy} r={5} />
        <line x1={cx - 6} y1={cy + 6} x2={cx + 6} y2={cy - 6} />
      </g>
    )
  }
  if (hint === 'modeled_closed') {
    return <line data-state="missing-closed" x1={cx - 5} x2={cx + 5} y1={cy} y2={cy} />
  }
  return <circle data-state={hint === 'unknown' ? 'missing-unknown' : 'missing-open'}
                 cx={cx} cy={cy} r={5} />
}

function CountPanel({ days, x, colW, selected, onSelect }: {
  days: ChatterDay[]
  x: (index: number) => number
  colW: number
  selected: string | null
  onSelect: (day: string) => void
}) {
  const counts = days.map((d) => (d.mentions !== null && !d.overlap_ambiguous ? d.mentions : null))
  const max = Math.max(1, ...counts.filter((c): c is number => c !== null))
  const top = PAD_TOP
  const bottom = COUNT_H - PAD_BOTTOM
  const barW = Math.min(46, colW * 0.6)
  const h = (value: number) => ((bottom - top) * 0.86) * (value / max)
  return (
    <svg className="rh-an-svg counts" viewBox={`0 0 ${W} ${COUNT_H}`} role="img"
         aria-label={`Retained mention counts, ${counts.filter((c) => c !== null).length} of ${days.length} days with a pooled count`}>
      <defs>
        <pattern id="rh-an-hatch" width="6" height="6" patternUnits="userSpaceOnUse"
                 patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" className="rh-an-hatchline" />
        </pattern>
      </defs>
      <SelectedColumn days={days} x={x} colW={colW} height={COUNT_H} selected={selected} />
      <line x1={LEFT} x2={W - RIGHT} y1={bottom} y2={bottom} className="rh-an-baseline" />
      <text x={LEFT - 6} y={top + 4} className="rh-an-axis" textAnchor="end">{max}</text>
      <text x={LEFT - 6} y={bottom + 4} className="rh-an-axis" textAnchor="end">0</text>
      {days.map((day, index) => {
        const cx = x(index)
        const label = `${dayLabel(day.date)}: ${chatterLabel(day)}`
        const count = counts[index] ?? null
        if (count === null) {
          return (
            <g key={day.date} className="rh-an-bar" onClick={() => onSelect(day.date)}>
              <rect x={cx - barW / 2} y={bottom - 18} width={barW} height={18}
                    data-coverage={day.overlap_ambiguous ? 'overlap' : 'unavailable'}
                    className="rh-an-gap" />
              <text x={cx} y={bottom - 5} className="rh-an-gaptext" textAnchor="middle">
                {day.overlap_ambiguous ? '?' : 'n/a'}
              </text>
              <title>{label}</title>
            </g>
          )
        }
        const height = h(count)
        const partial = day.coverage === 'partial'
        return (
          <g key={day.date} className="rh-an-bar" onClick={() => onSelect(day.date)}>
            {count === 0 ? (
              <rect x={cx - barW / 2} y={bottom - 3} width={barW} height={3}
                    data-coverage={partial ? 'partial-zero' : 'zero'}
                    className={partial ? 'rh-an-zero partial' : 'rh-an-zero'} />
            ) : (
              <rect x={cx - barW / 2} y={bottom - height} width={barW} height={height}
                    data-coverage={partial ? 'partial' : 'observed'}
                    className={partial ? 'rh-an-fill partial' : 'rh-an-fill'}
                    fill={partial ? 'url(#rh-an-hatch)' : undefined} />
            )}
            <text x={cx} y={bottom - height - 5} className="rh-an-value" textAnchor="middle">
              {count}{partial ? '*' : ''}
            </text>
            <title>{label}</title>
          </g>
        )
      })}
    </svg>
  )
}

function SelectedColumn({ days, x, colW, height, selected }: {
  days: { date: string }[]
  x: (index: number) => number
  colW: number
  height: number
  selected: string | null
}) {
  const index = days.findIndex((d) => d.date === selected)
  if (index < 0) return null
  return <rect className="rh-an-selected" x={x(index) - colW / 2} y={2}
               width={colW} height={height - 4} rx={4} />
}

import { useState } from 'react'
import type { PointerEvent } from 'react'

import { count, formatMarketDate, formatMarketTime, money } from '../format'
import type { DetailChart } from '../types'
import { FLOOR, PLOT_R, TOP, chatterY, isIntraday, perSlot, priceY }
  from './PriceChart'

/** The exact instant a slot names, as a reader would say it: `21 Aug 2026`
 *  on a calendar span, `1 Sep 2026 · 14:45` on an intraday one. The chart's
 *  own axis labels are deliberately coarser (a month, a day) because they
 *  are ticks; a readout is the one place the full date belongs. */
export function whenLabel(chart: DetailChart, index: number): string {
  const at = new Date(new Date(chart.from).getTime()
    + index * chart.step_minutes * 60_000)
  const iso = at.toISOString()
  return isIntraday(chart)
    ? `${formatMarketDate(iso)} · ${formatMarketTime(iso).replace(/ (?:CET|CEST)$/, '')}`
    : formatMarketDate(iso)
}

/** What the chart already computed for its own drawing, handed down so the
 *  overlay lands its marks exactly where the lines are. */
export interface HoverGeometry {
  priced: boolean
  low: number
  high: number
  peak: number
  band: number
}

/** The chart answering the cursor.
 *
 *  A price line and a chatter body are a picture until you can ask them a
 *  question; this is the asking (live mode, 2026-09-02: "nothing going on
 *  here that's helpful -- when the mouse is in there I get info about
 *  that"). Hover puts a hairline on the nearest slot and reads out the three
 *  facts that slot holds -- when, the close, the count -- as words, in the
 *  axis register, beside the cursor.
 *
 *  Absences stay absences: a slot with no close says `no close`, a slot
 *  before watching began says `not observed`. Nothing is interpolated, and
 *  the readout never says a number the chart did not draw.
 *
 *  Pointer, not mouse: the same code serves a finger on the panning mobile
 *  chart. Everything drawn here is in the SVG's own units, so it scales with
 *  the chart and needs no layout measurement. Decorative to a screen reader:
 *  the facts it shows are the chart's own, already in the gutter and the
 *  breakdown.
 */
export function ChartHover({ chart, geometry }: {
  chart: DetailChart
  geometry: HoverGeometry
}) {
  const [at, setAt] = useState<number | null>(null)

  const last = Math.max(chart.closes.length - 1, 1)
  const xAt = (index: number) => (index / last) * PLOT_R

  // Client pixels to viewBox units through the SVG's own matrix, so the
  // overlay is right whatever the chart was scaled or panned to.
  const indexFrom = (event: PointerEvent<SVGRectElement>): number => {
    const svg = event.currentTarget.ownerSVGElement
    // jsdom has no SVG geometry at all; slot 0 is the honest answer there.
    const ctm = typeof svg?.getScreenCTM === 'function' ? svg.getScreenCTM() : null
    if (!ctm) return 0
    const point = new DOMPoint(event.clientX, event.clientY)
      .matrixTransform(ctm.inverse())
    return Math.max(0, Math.min(last, Math.round((point.x / PLOT_R) * last)))
  }

  const close = at === null ? null : chart.closes[at] ?? null
  const talk = at === null ? null : chart.chatter[at] ?? null

  return (
    <g className="hover" aria-hidden="true">
      {at !== null && (
        <>
          <line className="hover-line" x1={xAt(at)} x2={xAt(at)} y1={TOP} y2={FLOOR}
                vectorEffect="non-scaling-stroke" />
          {geometry.priced && close !== null && (
            <circle className="hover-dot px" cx={xAt(at)}
                    cy={priceY(close, geometry.low, geometry.high)} r="3.5" />
          )}
          {talk !== null && (
            <circle className="hover-dot talk" cx={xAt(at)}
                    cy={chatterY(talk, geometry.peak, geometry.band)} r="3.5" />
          )}
          <Readout x={xAt(at)} lines={[
            whenLabel(chart, at),
            geometry.priced && close !== null ? money(close, geometry.high) : 'no close',
            talk === null ? 'not observed' : `${count(talk)}${perSlot(chart)}`,
          ]} />
        </>
      )}

      {/* Last, so it is on top of everything it reports on. */}
      <rect className="hover-hit" x="0" y={TOP} width={PLOT_R} height={FLOOR - TOP}
            fill="transparent"
            onPointerMove={(event) => setAt(indexFrom(event))}
            onPointerLeave={() => setAt(null)} />
    </g>
  )
}

/** Three short lines in the axis register, beside the hairline -- on its
 *  left once the cursor is near the gutter, so the words never leave the
 *  plot. Sized in user units like every label on the chart. */
function Readout({ x, lines }: { x: number; lines: string[] }) {
  const width = 150
  const flip = x > PLOT_R - width - 24
  const left = flip ? x - width - 12 : x + 12
  return (
    <g className="hover-readout" transform={`translate(${left.toFixed(1)}, ${TOP + 10})`}>
      <rect className="hover-card" x="0" y="0" width={width} height={16 * lines.length + 10}
            rx="3" />
      {lines.map((line, index) => (
        <text key={index} className={`ax hover-text l${index}`} x="8" y={16 * index + 18}>
          {line}
        </text>
      ))}
    </g>
  )
}

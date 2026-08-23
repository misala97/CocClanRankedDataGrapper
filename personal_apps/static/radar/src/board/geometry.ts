// Chart geometry, kept out of the components so it can be tested as maths.
//
// Two decisions here are editorial rather than technical, and both were made
// after looking at a rendered board:
//
// 1. THE CHATTER AXIS STARTS AT ZERO. Auto-scaling min..max is the default
//    sparkline behaviour and it lies by omission: a ticker sitting flat at
//    eight mentions an hour with normal jitter renders as a dramatic zigzag
//    identical in shape to a real spike. Anchored at zero, flat-and-noisy
//    looks flat and a spike looks like a spike, which is the entire question
//    the column is there to answer.
//
// 2. GAPS BREAK THE LINE. A null hour is an hour nobody measured. Interpolating
//    across it would draw a measurement that was never taken, so the path is
//    emitted in runs and the gap is left empty.
//
// The price axis is NOT zero-anchored -- a stock does not trade down to zero
// and the question there is the shape of the move, whose magnitude is printed
// in words beside the chart anyway.
//
// 3. THE TWO SERIES SHARE AN X AXIS AND SPLIT THE Y. Drawn over the full box
//    each, the price line's own noise sat on top of the bars and the chart
//    read as "a price chart with some decoration under it" -- which inverts
//    what the card is for. Bars now grow from the floor through the lower
//    band, the line is mapped into the upper band, and the two overlap in the
//    middle where a spike actually meets a move. Verified by rendering it.

import type { Chart, ChartSpan, Point } from '../types'

export interface Box {
  width: number
  height: number
  pad: number
  /** Share of the plot height the chatter bars may fill. The price line gets
   *  the top `1 - barBand` plus the overlap. Sparklines leave it at 1. */
  barBand?: number
  /** Share of the plot height the price line is mapped into, measured from
   *  the top. */
  priceBand?: number
}

/** Highest measured count in a series, or 0 when nothing was measured. */
export function peak(points: Point[]): number {
  return points.reduce<number>(
    (best, p) => (p.count !== null && p.count > best ? p.count : best), 0)
}

/** SVG path segments for a zero-anchored chatter line, one per unbroken run.
 *
 *  `yMax` is passed in rather than derived so several charts can share one
 *  scale -- the three lead cards do, which is what makes their bar heights
 *  comparable to each other instead of only within a card. */
export function chatterRuns(points: Point[], box: Box, yMax: number): string[] {
  const top = Math.max(yMax, 1)
  const runs: string[] = []
  let current: string[] = []

  points.forEach((point, index) => {
    if (point.count === null) {
      if (current.length) runs.push(current.join(' '))
      current = []
      return
    }
    const x = xAt(index, points.length, box)
    const y = box.height - box.pad
      - (point.count / top) * plot(box) * (box.barBand ?? 1)
    current.push(`${current.length ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
  })

  if (current.length) runs.push(current.join(' '))
  // A single measured point among gaps produces a one-point path, which draws
  // nothing. Give it a dot's worth of length so the hour is still visible.
  return runs.map((run) => (run.includes('L') ? run : `${run}l0.01,0`))
}

/** One bar per hour, for the lead chart. Unmeasured hours emit no bar. */
export interface Bar { x: number; y: number; width: number; height: number; ratio: number }

export function chatterBars(points: Point[], box: Box, yMax: number): Bar[] {
  const top = Math.max(yMax, 1)
  const slot = box.width / Math.max(points.length, 1)
  const bars: Bar[] = []

  points.forEach((point, index) => {
    if (point.count === null) return
    const ratio = point.count / top
    const full = plot(box) * (box.barBand ?? 1)
    const height = Math.max(ratio * full, point.count > 0 ? 1.2 : 0)
    if (height <= 0) return
    bars.push({
      x: index * slot + slot * 0.17,
      y: box.height - box.pad - height,
      width: slot * 0.66,
      height,
      ratio,
    })
  })
  return bars
}

function plot(box: Box): number {
  return box.height - box.pad * 2
}

function xAt(index: number, total: number, box: Box): number {
  return total <= 1 ? box.width / 2 : (index / (total - 1)) * box.width
}

/** Calendar days per span. '24h' is absent on purpose: that span reads the
 *  hourly `series` the payload already carried, at a resolution the daily
 *  arrays cannot express. */
export const SPAN_DAYS: Record<Exclude<ChartSpan, '24h'>, number> = {
  '1M': 30,
  '3M': 90,
  '1Y': 365,
}

/** The most recent N calendar days of both series, with `from` moved to match.
 *
 *  Slicing both by the same count is what keeps them aligned; moving `from`
 *  is what stops every span claiming to start a year ago. */
export function sliceChart(chart: Chart, span: ChartSpan): Chart {
  const days = span === '24h' ? SPAN_DAYS['1M'] : SPAN_DAYS[span]
  if (chart.closes.length <= days) return chart

  const cut = chart.closes.length - days
  const start = new Date(`${chart.from}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() + cut)
  return {
    from: start.toISOString().slice(0, 10),
    closes: chart.closes.slice(cut),
    chatter: chart.chatter.slice(cut),
  }
}

/** The price line, drawn ACROSS days the market was shut.
 *
 *  The chatter line breaks at its gaps because a gap there is an hour nobody
 *  measured. A gap here is a weekend: the price did not stop existing, and
 *  breaking at every Saturday would render a year as 52 fragments. Points
 *  keep their calendar index, so a Monday sits three days after the Friday
 *  before it whether or not anything traded between. */
export function pricePath(closes: (number | null)[], box: Box): string {
  const real = closes
    .map((value, index) => ({ value, index }))
    .filter((p): p is { value: number; index: number } => p.value !== null)
  if (real.length < 2) return ''

  const values = real.map((p) => p.value)
  const low = Math.min(...values)
  const span = Math.max(...values) - low || 1
  // priceBand keeps the line in the upper part of the box so the chatter bars
  // growing from the floor can cross it rather than hide under it. The scan
  // cell leaves it unset and uses the full height; the lead card sets 0.5.
  const band = plot(box) * (box.priceBand ?? 1)
  const lastIndex = Math.max(closes.length - 1, 1)

  return real.map((point, n) => {
    const x = (point.index / lastIndex) * box.width
    const y = box.pad + band - ((point.value - low) / span) * band
    return `${n ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

/** Highest measured value, ignoring nulls. */
export function peakOf(values: (number | null)[]): number {
  return values.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0)
}

/** One bar per day of chatter, zero-anchored, nothing for a null day. */
export function dailyBars(chatter: (number | null)[], box: Box,
                          yMax: number): Bar[] {
  const top = Math.max(yMax, 1)
  const slot = box.width / Math.max(chatter.length, 1)
  const full = plot(box) * (box.barBand ?? 1)
  const bars: Bar[] = []

  chatter.forEach((count, index) => {
    if (count === null || count === 0) return
    const ratio = count / top
    const height = Math.max(ratio * full, 1.2)
    bars.push({
      x: index * slot + slot * 0.15,
      y: box.height - box.pad - height,
      // A floor of 1.2px, not the 0.7 gap ratio alone. Over a year a day is
      // 0.34px in a scan cell, so the honest width rounds to nothing and five
      // real days of chatter render invisible. Only the HEIGHT carries the
      // value; the width is legibility, and a bar you cannot see is worse
      // than one a third of a pixel too wide.
      width: Math.max(slot * 0.7, 1.2),
      height,
      ratio,
    })
  })
  return bars
}

/** Whether the span ended higher than it began, ignoring untraded days. */
export function chartRose(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  const first = real.at(0)
  const last = real.at(-1)
  if (first === undefined || last === undefined) return true
  return last >= first
}

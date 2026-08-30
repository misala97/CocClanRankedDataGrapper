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

import type { Point } from '../types'

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

/** The chatter line closed to the floor, one polygon per unbroken run.
 *
 *  The chart-row's violet body. Same runs discipline as `chatterRuns`: a
 *  null hour breaks the shape, because filling across it would paint a
 *  measurement nobody took. */
export function chatterAreas(points: Point[], box: Box, yMax: number): string[] {
  const top = Math.max(yMax, 1)
  const floor = box.height - box.pad
  const areas: string[] = []
  let run: { x: number; y: number }[] = []

  const flush = () => {
    const first = run[0]
    const last = run[run.length - 1]
    if (first === undefined || last === undefined) return
    // A one-point run still gets a sliver, matching chatterRuns' dot.
    const x1 = run.length === 1 ? last.x + 0.5 : last.x
    const line = run.map((p, i) =>
      `${i ? 'L' : ''}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    areas.push(`M${first.x.toFixed(1)},${floor.toFixed(1)} L${line}`
      + ` L${x1.toFixed(1)},${floor.toFixed(1)} Z`)
    run = []
  }

  points.forEach((point, index) => {
    if (point.count === null) { flush(); return }
    run.push({
      x: xAt(index, points.length, box),
      y: floor - (point.count / top) * plot(box) * (box.barBand ?? 1),
    })
  })
  flush()
  return areas
}

/** Where a chatter value sits on the shared y scale -- for the dashed
 *  own-normal line the chart-row draws through its body. */
export function chatterY(value: number, box: Box, yMax: number): number {
  const top = Math.max(yMax, 1)
  return box.height - box.pad - (value / top) * plot(box) * (box.barBand ?? 1)
}

/** SVG path segments for the price line, one per unbroken run of quotes.
 *
 *  Its own scale, min..max padded -- a stock does not trade down to zero
 *  (see the axis note at the top of this file) -- and mapped into the upper
 *  `band` share of the box so the line rides above the chatter body and the
 *  two only meet where a spike actually meets a move. All-equal prices draw
 *  a mid-band flat line rather than dividing by zero. */
export function priceRuns(values: (number | null)[], box: Box,
                          band = 0.55): string[] {
  const seen = values.filter((v): v is number => v !== null)
  if (!seen.length) return []
  const min = Math.min(...seen)
  const max = Math.max(...seen)
  const span = max - min
  const height = plot(box) * band
  const runs: string[] = []
  let current: string[] = []

  values.forEach((value, index) => {
    if (value === null) {
      if (current.length) runs.push(current.join(' '))
      current = []
      return
    }
    const x = xAt(index, values.length, box)
    const share = span === 0 ? 0.5 : (value - min) / span
    const y = box.pad + (1 - share) * height
    current.push(`${current.length ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
  })
  if (current.length) runs.push(current.join(' '))
  // A lone quoted hour has no shape to contribute -- unlike the chatter
  // sliver, a price dot at an arbitrary height only reads as a glitch.
  return runs.filter((run) => run.includes('L'))
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

// ---------------------------------------------------------------------------
// THE BOARD'S SHAPE, AS ONE SHARED SCALE
//
// Every row draws how far above its own normal it is, on an axis all the rows
// share. Three decisions, and each one is about honesty rather than looks:
//
// 1. THE QUANTITY IS EXCESS, NOT THE RATIO. 1x is "exactly its normal", which
//    is no news at all, so it draws nothing. A bar proportional to the ratio
//    itself would give a row with nothing to report a third of the width.
//
// 2. THE SCALE RUNS TO A ROUND NUMBER, the way an axis does, rather than to
//    the loudest row exactly. Otherwise the top bar is always full width and
//    reads as a rule under the row rather than as a measurement.
//
// 3. LINEAR. A square root would spread a heavy-tailed board into a prettier
//    staircase and would misstate every magnitude on it. When one ticker is
//    forty times its normal and the rest are three, the flat-looking tail is
//    the finding.

/** The round number just above `value`, on a fine enough ladder to be worth
 *  rounding to.
 *
 *  A 1/2/5 ladder is the reflex and it wastes the axis: a board topping out at
 *  1.3x its normal rounds to 2 and every bar on it lands in the middle third,
 *  which is the shape of no board in particular. Real boards cluster -- twelve
 *  tickers between 1.4x and 2.3x is the ordinary Tuesday -- so the rounding has
 *  to be fine enough that the top bar still reaches. This ladder keeps it
 *  between two thirds and all of the axis at every magnitude -- the rung at
 *  4 is there only because 3 -> 5 was a 0.60 gap, found by the property
 *  test rather than by the handful of values that looked convenient. */
export function niceMax(value: number): number {
  if (value <= 0) return 1
  const decade = 10 ** Math.floor(Math.log10(value))
  for (const mantissa of [1, 1.5, 2, 3, 4, 5, 7.5]) {
    if (mantissa * decade >= value) return mantissa * decade
  }
  return 10 * decade
}

/** Each row's share of the shared scale, keyed by ticker.
 *
 *  A row with no ratio is absent from the map rather than present at zero.
 *  An empty track beside six filled ones would say "we measured this and it
 *  was nothing", which is the one thing it does not mean. */
export function magnitudes(rows: { ticker: string; ratio: number | null }[]):
    Record<string, number> {
  const excess = (ratio: number) => Math.max(0, ratio - 1)
  const top = rows.reduce(
    (best, row) => (row.ratio !== null ? Math.max(best, excess(row.ratio)) : best),
    0)
  if (top <= 0) return {}

  const scale = niceMax(top)
  const out: Record<string, number> = {}
  for (const row of rows) {
    if (row.ratio === null) continue
    out[row.ticker] = excess(row.ratio) / scale
  }
  return out
}

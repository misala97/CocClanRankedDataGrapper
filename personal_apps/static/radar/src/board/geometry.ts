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

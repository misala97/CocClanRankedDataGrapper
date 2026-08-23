import { describe, expect, it } from 'vitest'

import type { Point } from '../types'
import {
  chartRose, chatterBars, chatterRuns, dailyBars, peak, peakOf, pricePath,
  sliceChart, type Box,
} from './geometry'

const BOX: Box = { width: 100, height: 40, pad: 0 }

function series(counts: (number | null)[]): Point[] {
  return counts.map((count, index) => ({ hour: `h${index}`, count }))
}

/** Every y value in a path, in order. */
function ys(path: string): number[] {
  return [...path.matchAll(/[ML]([\d.]+),([\d.]+)/g)].map((m) => Number(m[2]))
}

describe('the chatter axis is anchored at zero', () => {
  it('draws a flat-but-jittery series near the top, not as a full-height zigzag', () => {
    // The defect this pins: min..max auto-scaling made 8,9,8,9 look exactly
    // like 0,40,0,40. Anchored at zero the whole run sits in the top tenth.
    const runs = chatterRuns(series([8, 9, 8, 9]), BOX, 9)
    const heights = ys(runs[0]!).map((y) => BOX.height - y)

    expect(Math.min(...heights)).toBeGreaterThan(BOX.height * 0.8)
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThan(BOX.height * 0.2)
  })

  it('still draws a real spike as a spike', () => {
    const heights = ys(chatterRuns(series([1, 1, 1, 20]), BOX, 20)[0]!)
      .map((y) => BOX.height - y)

    expect(Math.max(...heights)).toBe(BOX.height)
    expect(Math.min(...heights)).toBeLessThan(BOX.height * 0.1)
  })

  it('scales against the max it is given, so charts can share one scale', () => {
    const alone = ys(chatterRuns(series([5, 5]), BOX, 5)[0]!)
    const shared = ys(chatterRuns(series([5, 5]), BOX, 50)[0]!)

    expect(BOX.height - alone[0]!).toBe(BOX.height)
    expect(BOX.height - shared[0]!).toBeCloseTo(BOX.height * 0.1)
  })
})

describe('unmeasured hours', () => {
  it('breaks the line rather than interpolating across the gap', () => {
    const runs = chatterRuns(series([3, 4, null, null, 6, 7]), BOX, 10)

    expect(runs).toHaveLength(2)
    expect(ys(runs[0]!)).toHaveLength(2)
    expect(ys(runs[1]!)).toHaveLength(2)
  })

  it('keeps a lone measured hour visible instead of dropping it', () => {
    // A one-point path renders nothing at all, so the hour would vanish.
    const runs = chatterRuns(series([null, 5, null]), BOX, 10)

    expect(runs).toHaveLength(1)
    expect(runs[0]!).toContain('l0.01,0')
  })

  it('emits no bar for them, and no bar for a measured zero', () => {
    const bars = chatterBars(series([0, null, 4]), BOX, 4)

    expect(bars).toHaveLength(1)
    expect(bars[0]!.ratio).toBe(1)
  })

  it('reports the peak over measured hours only', () => {
    expect(peak(series([null, 3, null, 7]))).toBe(7)
    expect(peak(series([null, null]))).toBe(0)
  })
})

describe('the chart span', () => {
  const chart = {
    from: '2025-08-23',
    closes: Array.from({ length: 365 }, (_, i) => (i % 7 < 5 ? 100 + i : null)),
    chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
  }

  it('slices both series to the same days', () => {
    const month = sliceChart(chart, '1M')

    expect(month.closes).toHaveLength(30)
    expect(month.chatter).toHaveLength(30)
  })

  it('moves the start date with the slice', () => {
    // Otherwise every span would claim to begin a year ago.
    expect(sliceChart(chart, '1Y').from).toBe('2025-08-23')
    expect(sliceChart(chart, '1M').from).not.toBe('2025-08-23')
  })

  it('returns everything it has when the series is shorter than the span', () => {
    const young = { from: '2026-08-01', closes: [1, 2, 3], chatter: [1, 2, 3] }

    expect(sliceChart(young, '1Y').closes).toEqual([1, 2, 3])
  })
})

describe('the price line across a closed market', () => {
  it('draws through a gap rather than breaking at it', () => {
    // A weekend is not missing data about the price, it is a weekend. The
    // chatter line breaks at its gaps; this one must not, or a year renders
    // as 52 fragments.
    const path = pricePath([10, null, null, 13], BOX)

    expect(path.split('M')).toHaveLength(2)
    expect(path.match(/L/g) ?? []).toHaveLength(1)
  })

  it('keeps calendar position, not the order of surviving points', () => {
    const path = pricePath([10, null, null, 13], BOX)
    const xs = [...path.matchAll(/[ML]([\d.]+),/g)].map((m) => Number(m[1]))

    expect(xs[0]).toBe(0)
    expect(xs[1]).toBeCloseTo(BOX.width)
  })

  it('draws nothing from fewer than two real closes', () => {
    expect(pricePath([null, null], BOX)).toBe('')
    expect(pricePath([10, null], BOX)).toBe('')
  })

  it('stays in its band when one is set, leaving the floor to the bars', () => {
    const banded = pricePath([100, 110], { ...BOX, priceBand: 0.5 })
    const ys = [...banded.matchAll(/[ML][\d.]+,([\d.]+)/g)].map((m) => Number(m[1]))

    expect(Math.max(...ys)).toBeLessThanOrEqual(BOX.height * 0.5)
  })

  it('reads direction across the span, ignoring untraded days', () => {
    expect(chartRose([100, null, 50])).toBe(false)
    expect(chartRose([50, null, 100])).toBe(true)
    expect(chartRose([null, null])).toBe(true)
  })
})

describe('daily chatter bars', () => {
  it('emits nothing for a day nobody was watching', () => {
    expect(dailyBars([null, null, 4], BOX, 4)).toHaveLength(1)
  })

  it('emits nothing for a measured zero, and something for a one', () => {
    const bars = dailyBars([0, 1], BOX, 4)

    expect(bars).toHaveLength(1)
    expect(bars[0]!.ratio).toBeCloseTo(0.25)
  })

  it('ignores nulls when finding the peak', () => {
    expect(peakOf([null, 7, null, 3])).toBe(7)
    expect(peakOf([null, null])).toBe(0)
  })
})

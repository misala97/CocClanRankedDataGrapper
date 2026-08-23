import { describe, expect, it } from 'vitest'

import type { Point } from '../types'
import { chatterBars, chatterRuns, peak, type Box } from './geometry'

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

// The span slicing, the price line and the daily bars moved to the panel
// chart on 2026-08-23 -- see detail/PriceChart.test.tsx, which carries the
// two behaviours worth keeping: a measured zero draws nothing, and points
// keep their calendar position rather than their order among survivors.

import { describe, expect, it } from 'vitest'

import { priceChartResponse } from './priceChartFixtures'
import {
  PLOT_R, berlinClock, berlinZone, chatterBars, frameOf, newYorkDate, pointsInSlot,
  priceRuns, sessionDateLabel, slotIndexAt, toneFor, xOf,
} from './selectedPriceGeometry'

const data = priceChartResponse()
const frame = frameOf(data.window)                 // 08:00Z .. 09:07Z, 67 minutes
const at = (iso: string) => Date.parse(iso)

describe('one time axis', () => {
  it('maps the window ends to the plot ends and a zero-length window to nothing', () => {
    expect(xOf(frame, frame.from)).toBe(0)
    expect(xOf(frame, frame.to)).toBe(PLOT_R)
    expect(xOf({ from: 5, to: 5 }, 5)).toBe(0)
  })

  it('aligns price points and chatter slots of different lengths by their instants', () => {
    const { lines, dots } = priceRuns(data.price!.points, frame)
    const bars = chatterBars(data.chatter.slots, data.chatter.tone.slots, frame)
    expect(data.price!.points).toHaveLength(6)
    expect(bars).toHaveLength(5)
    const provisional = dots[0]!
    expect(provisional.x).toBeGreaterThanOrEqual(bars[4]!.left)
    expect(provisional.x).toBeLessThanOrEqual(bars[4]!.right)
    // A bar close sits at its end: the 08:00 bar is plotted at 08:01.
    expect(lines[0]![0]!.x).toBeCloseTo((60 / 4020) * PLOT_R, 6)
  })

  it('draws a short last slot short instead of stretching the axis', () => {
    const bars = chatterBars(data.chatter.slots, data.chatter.tone.slots, frame)
    const full = bars[0]!.right - bars[0]!.left
    const last = bars[4]!.right - bars[4]!.left
    expect(bars[4]!.right).toBeCloseTo(PLOT_R, 6)
    expect(last / full).toBeCloseTo(7 / 15, 6)
  })
})

describe('gaps stay gaps', () => {
  it('breaks at nulls and break_before and keeps a lone point as a dot', () => {
    const { lines, dots } = priceRuns(data.price!.points, frame)
    expect(lines.map((run) => run.map((p) => p.point.start.slice(11, 16)))).toEqual([
      ['08:00', '08:01'], ['08:03', '08:04']])
    expect(dots.map((d) => d.point.start.slice(11, 16))).toEqual(['09:06'])
  })

  it('draws no line at all without a valid price', () => {
    expect(priceRuns([], frame)).toEqual({ lines: [], dots: [] })
  })
})

describe('counts and tone', () => {
  it('keeps unknown, zero and invalid tone apart', () => {
    const bars = chatterBars(data.chatter.slots, data.chatter.tone.slots, frame)
    expect(bars[2]).toMatchObject({ count: null, stacks: [] })
    expect(bars[1]).toMatchObject({ count: 0, stacks: [] })
    expect(bars[0]!.stacks.map((s) => [s.key, s.value])).toEqual([['bullish', 2], ['bearish', 1]])
    const broken = toneFor(data.chatter.slots[0]!, { bullish: 9, bearish: 0, neutral: 0, unjudged: 0,
                                                     unavailable: 0, status: 'complete' })
    expect(broken).toEqual({ bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: 3 })
    expect(bars[3]!.partial).toBe(true)
  })

  it('finds the slot for an instant and the price observations inside it', () => {
    expect(slotIndexAt(data.chatter.slots, at('2026-09-15T08:16:00Z'))).toBe(1)
    expect(slotIndexAt(data.chatter.slots, at('2026-09-15T10:00:00Z'))).toBe(4)
    expect(pointsInSlot(data.price!.points, data.chatter.slots[0]!)).toHaveLength(5)
    expect(pointsInSlot(data.price!.points, data.chatter.slots[4]!)).toHaveLength(1)
  })
})

describe('wording', () => {
  it('labels session dates without shifting them and hover times in Berlin', () => {
    expect(sessionDateLabel('2026-09-15')).toBe('Tue 15 Sep')
    expect(berlinClock('2026-09-15T08:00:00Z')).toBe('10:00')
    expect(berlinZone('2026-09-15T08:00:00Z')).toBe('CEST')
    expect(newYorkDate('2026-09-15T02:00:00Z')).toBe('Mon 14 Sep')
  })
})

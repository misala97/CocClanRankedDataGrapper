import { describe, expect, it } from 'vitest'

import type { PricePoint } from './priceChart'
import { PREMARKET, alpacaPrice, bar, priceChartResponse } from './priceChartFixtures'
import {
  PLOT_R, PRICE_BOTTOM, areaPathOf, berlinClock, berlinZone, chatterBars, frameOf, latestValid,
  newYorkDate, pathOf, pointsInSlot, priceSegments, sessionDateLabel, slotIndexAt, sourceWord,
  toneFor, xOf,
} from './selectedPriceGeometry'

const data = priceChartResponse()
const frame = frameOf(data.window)                 // 08:00Z .. 09:07Z, 67 minutes
const at = (iso: string) => Date.parse(iso)

const keys = (points: PricePoint[]) => priceSegments(points, frame).map((s) => s.key)
const sizes = (points: PricePoint[]) => priceSegments(points, frame).map((s) => s.points.length)

/** FT's actual shape: 64 reported minutes scattered over a 390-minute session,
 *  all in one market state, with minutes the tape simply did not report in
 *  between. Every one of them is a real observation; the 326 absent minutes
 *  are absent, not zero. */
const SPARSE = alpacaPrice(Array.from({ length: 64 }, (_, i) => i * 6 + (i % 3)))
const sessionFrame = { from: Date.parse('2026-09-15T08:00:00Z'),
                       to: Date.parse('2026-09-15T14:30:00Z') }

describe('one time axis', () => {
  it('maps the window ends to the plot ends and a zero-length window to nothing', () => {
    expect(xOf(frame, frame.from)).toBe(0)
    expect(xOf(frame, frame.to)).toBe(PLOT_R)
    expect(xOf({ from: 5, to: 5 }, 5)).toBe(0)
  })

  it('aligns price points and chatter slots of different lengths by their instants', () => {
    const segments = priceSegments(data.price!.points, frame)
    const bars = chatterBars(data.chatter.slots, data.chatter.tone.slots, frame)
    expect(data.price!.points).toHaveLength(6)
    expect(bars).toHaveLength(5)
    const last = segments[0]!.points[segments[0]!.points.length - 1]!
    expect(last.x).toBeGreaterThanOrEqual(bars[4]!.left)
    expect(last.x).toBeLessThanOrEqual(bars[4]!.right)
    // A bar close sits at its end: the 08:00 bar is plotted at 08:01.
    expect(segments[0]!.points[0]!.x).toBeCloseTo((60 / 4020) * PLOT_R, 6)
  })

  it('draws a short last slot short instead of stretching the axis', () => {
    const bars = chatterBars(data.chatter.slots, data.chatter.tone.slots, frame)
    const full = bars[0]!.right - bars[0]!.left
    const last = bars[4]!.right - bars[4]!.left
    expect(bars[4]!.right).toBeCloseTo(PLOT_R, 6)
    expect(last / full).toBeCloseTo(7 / 15, 6)
  })
})

describe('hard segments, and only hard segments, split the drawing', () => {
  it('keeps 64 sparse reported minutes in one segment rather than dozens of fragments', () => {
    const segments = priceSegments(SPARSE.points, sessionFrame)
    expect(SPARSE.points).toHaveLength(64)
    expect(SPARSE.points.filter((p) => p.break_before)).not.toHaveLength(0)
    expect(segments).toHaveLength(1)
    expect(segments[0]!.points).toHaveLength(64)
    expect(pathOf(segments[0]!.points).match(/L/g)).toHaveLength(63)
  })

  it('does not end a segment at a disclosed gap or a null close', () => {
    const points = [bar('08:00', 100), bar('08:02', null, { breakBefore: true }),
                    bar('08:40', 101, { breakBefore: true })]
    expect(keys(points)).toEqual([PREMARKET])
    expect(sizes(points)).toEqual([2])
  })

  it.each([
    ['a market-state change', `regular:2026-09-15|yahoo_chart:provider_bar_close:unknown`],
    ['a session day change', `premarket:2026-09-16|yahoo_chart:provider_bar_close:unknown`],
    ['a source change', `premarket:2026-09-15|alpaca_sip:provider_bar_close:raw`],
  ])('starts a new segment at %s', (_label, segment) => {
    const points = [bar('08:00', 100), bar('08:01', 101),
                    bar('08:02', 102, { segment }), bar('08:03', 103, { segment })]
    expect(keys(points)).toEqual([PREMARKET, segment])
    expect(sizes(points)).toEqual([2, 2])
  })

  it('never draws anything for a window with no valid price', () => {
    expect(priceSegments([], frame)).toEqual([])
    expect(priceSegments([bar('08:00', null)], frame)).toEqual([])
  })
})

describe('the area is geometry, never a datum', () => {
  it('closes each multi-point segment to the price baseline and adds no vertex', () => {
    const segment = priceSegments(SPARSE.points, sessionFrame)[0]!
    const area = areaPathOf(segment.points, PRICE_BOTTOM)
    expect(area.startsWith(pathOf(segment.points))).toBe(true)
    expect(area.endsWith('Z')).toBe(true)
    const first = segment.points[0]!
    const last = segment.points[segment.points.length - 1]!
    expect(area.slice(pathOf(segment.points).length)).toBe(
      ` L${last.x.toFixed(2)},${PRICE_BOTTOM.toFixed(2)}`
      + ` L${first.x.toFixed(2)},${PRICE_BOTTOM.toFixed(2)} Z`)
    // Exactly one vertex per actual observation, plus the two baseline corners.
    expect(area.match(/[ML]/g)).toHaveLength(segment.points.length + 2)
  })

  it('has no area for a one-observation segment', () => {
    const single = priceSegments([bar('08:00', 100)], frame)[0]!
    expect(single.points).toHaveLength(1)
    expect(areaPathOf(single.points, PRICE_BOTTOM)).toBe('')
  })

  it('offers exactly the actual observations for inspection, in order', () => {
    const segments = priceSegments(data.price!.points, frame)
    const plotted = segments.flatMap((s) => s.points.map((p) => ({ at: p.point.at, value: p.point.value })))
    const actual = data.price!.points.filter((p) => p.value !== null)
      .map((p) => ({ at: p.at, value: p.value }))
    expect(plotted).toEqual(actual)
    expect(latestValid(data.price!.points)!.at).toBe(actual[actual.length - 1]!.at)
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
  it('names the US sources and passes an unknown source code through', () => {
    expect(sourceWord('alpaca_sip')).toBe('Alpaca consolidated SIP (delayed)')
    expect(sourceWord('yahoo_chart')).toBe('Yahoo chart')
    // A source code with no entry is shown as its raw code, never dressed up.
    expect(sourceWord('some_future_feed')).toBe('some_future_feed')
  })

  it('labels session dates without shifting them and hover times in Berlin', () => {
    expect(sessionDateLabel('2026-09-15')).toBe('Tue 15 Sep')
    expect(berlinClock('2026-09-15T08:00:00Z')).toBe('10:00')
    expect(berlinZone('2026-09-15T08:00:00Z')).toBe('CEST')
    expect(newYorkDate('2026-09-15T02:00:00Z')).toBe('Mon 14 Sep')
  })
})

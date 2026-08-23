import { describe, expect, it } from 'vitest'
import { magnitudes, niceMax } from './geometry'

const row = (ticker: string, ratio: number | null) => ({ ticker, ratio })

describe('the row magnitude axis', () => {
  it('measures how far above normal, not the ratio itself', () => {
    /* 1x is "exactly its own normal", which is no news at all. A bar
       proportional to the ratio would hand a row with nothing to report a
       third of the axis. */
    const mags = magnitudes([row('A', 3), row('B', 1)])

    expect(mags.A).toBeGreaterThan(0)
    expect(mags.B).toBe(0)
  })

  it('leaves a row with no baseline out of the scale entirely', () => {
    /* Absent, not zero. Present at zero would draw an empty track beside the
       filled ones, which says "we measured this and it was nothing" -- the one
       thing it does not mean. */
    const mags = magnitudes([row('A', 3), row('B', null)])

    expect('B' in mags).toBe(false)
  })

  it('shares one scale across the rows rather than one per row', () => {
    /* Scaled inside its own row every row is equally loud, which is the
       opposite of what a ranked board is for. */
    const mags = magnitudes([row('A', 5), row('B', 3), row('C', 2)])

    expect(mags.A).toBeGreaterThan(mags.B!)
    expect(mags.B).toBeGreaterThan(mags.C!)
  })

  it('still fills most of the axis when the board is clustered', () => {
    /* The ordinary case, measured off the live board: twelve tickers between
       1.4x and 2.3x their own normal. A 1/2/5 ladder rounds that to 2 and puts
       every bar in the middle third of the track. */
    const mags = magnitudes([
      row('A', 2.27), row('B', 1.9), row('C', 1.8), row('D', 1.42),
    ])

    expect(mags.A).toBeGreaterThan(0.66)
    expect(mags.D).toBeLessThan(mags.A!)
  })

  it('survives a board where nothing is above its normal', () => {
    /* Dividing by a top of zero would be Infinity in every bar. */
    expect(magnitudes([row('A', 1), row('B', 0.8)])).toEqual({})
  })

  it('rounds up to a number an axis would be labelled with', () => {
    expect(niceMax(0.9)).toBe(1)
    expect(niceMax(1.27)).toBe(1.5)
    expect(niceMax(2.2)).toBe(3)
    expect(niceMax(39)).toBe(40)
    expect(niceMax(0)).toBe(1)
  })

  it('never lets the loudest row fall below two thirds of the axis', () => {
    /* The property the ladder exists for. Checked across three decades rather
       than at the handful of points that happen to be convenient. */
    for (let value = 0.05; value < 120; value *= 1.07) {
      expect(value / niceMax(value)).toBeGreaterThan(0.66)
    }
  })
})

import { describe, expect, it } from 'vitest'
import {
  barChoices, barLabel, clock, evenStops, kg, parseStops, restChoices, stepChoices, stopsLine,
} from './values'

describe('how a setting reads', () => {
  it('reads a rest as m:ss and a weight with a comma', () => {
    expect([clock(45), clock(90), clock(150), clock(600)]).toEqual(['0:45', '1:30', '2:30', '10:00'])
    expect([clock(3599), clock(3600), clock(3725)]).toEqual(['59:59', '1:00:00', '1:02:05'])
    expect([kg(2.5), kg(5), kg(1.25), kg(0.1 + 0.2)]).toEqual(['2,5', '5', '1,25', '0,3'])
    expect([barLabel(0), barLabel(20)]).toEqual(['Ohne', '20'])
  })
})

describe('restChoices', () => {
  it('puts the reference one in for the settings, two in for "Pause heute"', () => {
    expect(restChoices(90, 1)).toEqual([60, 90, 120, 150, 180])
    expect(restChoices(150, 2)).toEqual([90, 120, 150, 180, 210])
  })

  it('always holds the reference, with fewer before it than any below half a minute', () => {
    expect(restChoices(60, 2)).toEqual([30, 60, 90, 120, 150])
    expect(restChoices(45, 1)).toEqual([45, 75, 105, 135, 165])
    expect(restChoices(15, 2)[0]).toBe(15)
  })

  it('starts around two minutes when nothing marks a reference', () => {
    expect(restChoices(null, 2)).toEqual([60, 90, 120, 150, 180])
  })
})

describe('stepChoices and barChoices', () => {
  it('offers the steps real gyms load in, by equipment', () => {
    expect(stepChoices('stack', 5)).toEqual([2.5, 5, 7, 8, 10])
    expect(stepChoices('dumbbell', 2)).toEqual([1, 1.25, 2, 2.5, 4])
    expect(stepChoices(null, 2.5)).toEqual([1, 2, 2.5, 5, 10])
  })

  it("puts the list's value in the row in place of its nearest, keeping five", () => {
    expect(stepChoices('stack', 6)).toEqual([2.5, 6, 7, 8, 10])
    expect(barChoices(7)).toEqual([0, 7, 15, 20, 25])
    expect(barChoices(null)).toEqual([0, 10, 15, 20, 25])
  })
})

describe('stops', () => {
  it('reads the first stops of a machine, and an even stack from its step', () => {
    expect(stopsLine([5, 13, 21])).toBe('5, 13, 21')
    expect(stopsLine([5, 12, 19, 26, 33, 40])).toBe('5, 12, 19, 26, 33 …')
    expect(evenStops(2.5)).toEqual([2.5, 5, 7.5])
    // A decimal comma between list commas would read as more numbers.
    expect(stopsLine(evenStops(2.5))).toBe('2,5 · 5 · 7,5')
  })

  it('takes stops typed any way, ascending and once each, and at least two', () => {
    expect(parseStops('19, 5; 12 12')).toEqual([5, 12, 19])
    expect(parseStops('5.5,13')).toEqual([5.5, 13])
    expect(parseStops('12')).toBeNull()
    expect(parseStops('abc, -3, 0')).toBeNull()
  })
})

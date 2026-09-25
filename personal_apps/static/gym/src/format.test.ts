import { describe, expect, it } from 'vitest'
import {
  dayDate, dayMonth, kg, kg1, kgSetting, localParts, roundTo, setsLine, shortDate, signedKg1,
  signedWhole, volume, weekdayDate, whenSaid, whole,
} from './format'

describe('kg1', () => {
  it('uses a comma', () => {
    expect(kg1(62.5)).toBe('62,5')
    expect(kg1(0)).toBe('0,0')
  })

  it('rounds a tie to the even digit, as Python does', () => {
    // The whole reason this is not a toFixed one-liner. Left column is what
    // `'%.1f'|format(x)` printed on the Jinja page.
    expect(kg1(3.25)).toBe('3,2')   // toFixed would say 3,3
    expect(kg1(3.75)).toBe('3,8')
    expect(kg1(2.25)).toBe('2,2')
    expect(kg1(2.75)).toBe('2,8')   // toFixed agrees here
    expect(kg1(0.25)).toBe('0,2')
    expect(kg1(1.25)).toBe('1,2')
  })

  it('rounds everything else normally', () => {
    expect(kg1(3.26)).toBe('3,3')
    expect(kg1(3.24)).toBe('3,2')
    expect(kg1(1.125)).toBe('1,1')
    expect(kg1(100)).toBe('100,0')
  })

  it('keeps the sign', () => {
    expect(kg1(-3.25)).toBe('-3,2')
    expect(kg1(-2.5)).toBe('-2,5')
  })
})

describe('volume', () => {
  it('groups thousands with a dot', () => {
    expect(volume(12345)).toBe('12.345')
    expect(volume(999)).toBe('999')
    expect(volume(1234.6)).toBe('1.235')
  })

  it('rounds a tie to even, as "{:,.0f}".format does', () => {
    expect(volume(1234.5)).toBe('1.234')
    expect(volume(1235.5)).toBe('1.236')
  })
})

describe('whole', () => {
  it('mirrors the |round|int filter, which is Python round()', () => {
    // The filter documents half-up and does not do it: a 22,5 % share
    // printed 22 on the Jinja page and Math.round would print 23.
    expect(whole(22.5)).toBe(22)
    expect(whole(23.5)).toBe(24)
    expect(whole(22.6)).toBe(23)
    expect(whole(15.0)).toBe(15)
  })
})

describe('signedWhole', () => {
  it('always carries a sign', () => {
    expect(signedWhole(180.1)).toBe('+180')
    expect(signedWhole(-12.4)).toBe('-12')
    expect(signedWhole(0)).toBe('+0')
  })

  it('rounds a tie to even too', () => {
    expect(signedWhole(12.5)).toBe('+12')
    expect(signedWhole(-12.5)).toBe('-12')
  })
})

describe('roundTo', () => {
  it('rounds to a fixed number of places', () => {
    expect(roundTo(33.333, 1)).toBe(33.3)
    expect(roundTo(0.887, 3)).toBe(0.887)
  })

  it('rounds a tie to even', () => {
    // Both exact in binary, which is what makes them real ties -- see the
    // note on halfEven about the domain this holds over.
    expect(roundTo(0.25, 1)).toBe(0.2)
    expect(roundTo(0.75, 1)).toBe(0.8)
  })
})

describe('shortDate', () => {
  it('renders dd.MM.yyyy regardless of the browser locale', () => {
    expect(shortDate('2026-08-09T18:00:00')).toBe('09.08.2026')
  })

  // G-032 / G-052: timestamps arrive naive-UTC. Read as the browser's local
  // time, 00:10 on 23 September in Berlin printed as the 22nd.
  it('reads a naive timestamp as UTC and dates it in Berlin', () => {
    expect(shortDate('2026-09-22T22:10:41')).toBe('23.09.2026')
  })

  it('knows winter time', () => {
    expect(shortDate('2026-01-01T23:30:00')).toBe('02.01.2026')
    expect(shortDate('2026-01-01T22:30:00')).toBe('01.01.2026')
  })

  it('leaves a stamp that names its zone alone', () => {
    expect(shortDate('2026-09-22T22:10:41Z')).toBe('23.09.2026')
    expect(shortDate('2026-09-23T00:10:41+02:00')).toBe('23.09.2026')
  })
})

describe('dayMonth', () => {
  it('is shortDate without the year', () => {
    expect(dayMonth('2026-09-22T22:10:41')).toBe('23.09.')
  })
})

describe('localParts', () => {
  it('gives the Berlin wall clock, Monday first', () => {
    // Wednesday 23 September, 00:10 in Berlin.
    expect(localParts('2026-09-22T22:10:41')).toEqual(
      { year: 2026, month: 9, day: 23, hour: 0, minute: 10, weekday: 2 })
  })
})

describe('whenSaid', () => {
  // Thursday 24 September, noon in Berlin.
  const now = new Date('2026-09-24T10:00:00Z')

  it('says the day the way a lifter does', () => {
    expect(whenSaid('2026-09-24T06:00:00', now)).toBe('heute')
    expect(whenSaid('2026-09-23T06:00:00', now)).toBe('gestern')
    expect(whenSaid('2026-09-21T16:00:00', now)).toBe('Mo')
    expect(whenSaid('2026-09-18T16:00:00', now)).toBe('Fr')
  })

  it('names the date once the weekday would be ambiguous', () => {
    // A week ago was a Thursday too.
    expect(whenSaid('2026-09-17T16:00:00', now)).toBe('17.09.')
  })

  it('counts Berlin days, not UTC ones', () => {
    // 00:30 on Wednesday in Berlin is still Tuesday in UTC.
    expect(whenSaid('2026-09-22T22:30:00', now)).toBe('gestern')
  })

  it('says the year of a day in another year', () => {
    // "15.12." under "Letztes Mal" named last December as this one.
    expect(whenSaid('2025-12-15T16:00:00', now)).toBe('15.12.2025')
  })
})

describe('dayDate and weekdayDate', () => {
  const now = new Date('2026-09-24T10:00:00Z')

  it('leave out this year, and say any other', () => {
    expect(dayDate('2026-08-25T16:00:00', now)).toBe('25.08.')
    expect(dayDate('2025-08-25T16:00:00', now)).toBe('25.08.2025')
    expect(weekdayDate('2026-08-25T16:00:00', now)).toBe('Di 25.08.')
    expect(weekdayDate('2025-12-15T16:00:00', now)).toBe('Mo 15.12.2025')
  })

  it('read the year in Berlin: New Year\'s Eve at 23:30 UTC is the new year', () => {
    expect(dayDate('2025-12-31T23:30:00', now)).toBe('01.01.')
    expect(weekdayDate('2025-12-31T23:30:00', now)).toBe('Do 01.01.')
  })
})

describe('signedKg1', () => {
  it('always carries a sign, a true minus below zero', () => {
    expect(signedKg1(1.24)).toBe('+1,2')
    expect(signedKg1(-0.4)).toBe('−0,4')
  })

  it('says a rate that rounds to nothing as ±0', () => {
    expect(signedKg1(0)).toBe('±0')
    expect(signedKg1(0.04)).toBe('±0')
    expect(signedKg1(-0.04)).toBe('±0')
  })
})

describe('setsLine', () => {
  it('says the weight once while it holds', () => {
    expect(setsLine([{ weight: 55, reps: 10 }, { weight: 55, reps: 9 }, { weight: 55, reps: 8 }]))
      .toBe('55,0 × 10 · 9 · 8')
  })

  it('says it again where it changes', () => {
    expect(setsLine([{ weight: 60, reps: 8 }, { weight: 62.5, reps: 6 }, { weight: 62.5, reps: 6 }]))
      .toBe('60,0 × 8 · 62,5 × 6 · 6')
  })

  it('says a quarter-kilo weight as it was logged (G-146)', () => {
    expect(setsLine([{ weight: 11.25, reps: 8 }, { weight: 11.25, reps: 7 }]))
      .toBe('11,25 × 8 · 7')
  })
})

describe('kg (G-146)', () => {
  // One screen said 11,2, the stepper 11,3 and the settings 11,25 for the
  // same logged weight.
  it('keeps a weight to the hundredth, and one decimal at least', () => {
    expect([kg(11.25), kg(11.5), kg(80), kg(62.5), kg(0)])
      .toEqual(['11,25', '11,5', '80,0', '62,5', '0,0'])
  })

  it('rounds past the hundredth the way Python does', () => {
    // 11.125 is exact in binary, a true tie: even, as '{:.2f}' prints it.
    expect([kg(11.125), kg(0.1 + 0.2), kg(72.35)]).toEqual(['11,12', '0,3', '72,35'])
    expect(kg(11.375)).toBe('11,38')
  })

  it('reads no tie into a double that only scales to one (B9 review)', () => {
    // 47.505 is a hair above, 0.015 a hair below: '{:.2f}' prints 47.51 and
    // 0.01, and times 100 both land on ,5 exactly.
    expect([kg(47.505), kg(0.015), kgSetting(0.015)]).toEqual(['47,51', '0,01', '0,01'])
    // '%.1f' % 0.35 is 0.3: the double is 0.34999...
    expect(kg1(0.35)).toBe('0,3')
  })

  it('reads a setting the way it is typed', () => {
    expect([kgSetting(20), kgSetting(2.5), kgSetting(1.25), kgSetting(0.1 + 0.2)])
      .toEqual(['20', '2,5', '1,25', '0,3'])
  })
})

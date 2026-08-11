import { describe, expect, it } from 'vitest'
import { kg1, roundTo, shortDate, signedWhole, volume, whole } from './format'

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
})

import { describe, expect, it } from 'vitest'
import { kg1, volume, shortDate } from './format'

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
})

describe('shortDate', () => {
  it('renders dd.MM.yyyy regardless of the browser locale', () => {
    expect(shortDate('2026-08-09T18:00:00')).toBe('09.08.2026')
  })
})

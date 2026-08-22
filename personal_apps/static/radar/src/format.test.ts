import { describe, expect, it } from 'vitest'

import { divergence, move, segmentLabel, signed, sourceLabel, stampTime, zscore } from './format'

describe('an unknown never renders as a zero', () => {
  // The single rule PRODUCT.md is most insistent about. A row with no quote,
  // or a frozen tape, has no divergence -- and 0.00 means something else
  // entirely: that chatter and price moved together.
  it('says so in words for divergence', () => {
    expect(divergence(null)).toBe('not scored')
    expect(divergence(0)).toBe('0.00')
  })

  it('uses an em-dash for an unknown price move', () => {
    expect(move(null)).toBe('—')
    expect(move(0)).toBe('0.00%')
  })

  it('uses an em-dash for an unscored window', () => {
    expect(zscore(null)).toBe('—')
    expect(zscore(0)).toBe('0.0')
  })
})

describe('signed numbers', () => {
  it('marks a rise and leaves a fall with its own sign', () => {
    expect(signed(1.5, 2)).toBe('+1.50')
    expect(signed(-1.5, 2)).toBe('-1.50')
  })

  it('never prints a negative zero', () => {
    // toFixed(-0.001) is "-0.00", which reads as a downward move that did not
    // happen -- and on a price column that is a wrong fact, not a typo.
    expect(signed(-0.001, 2)).toBe('0.00')
    expect(move(-0.0000001)).toBe('0.00%')
  })
})

describe('labels', () => {
  it('renders a source the label table does not know', () => {
    // Adding a source must be a config entry plus an ingest module, never a
    // UI change (PRODUCT.md). An unknown key falling through as itself is
    // what keeps that true.
    expect(sourceLabel('bluesky')).toBe('Bluesky')
    expect(sourceLabel('discord')).toBe('discord')
    expect(segmentLabel('nonsense')).toBe('nonsense')
  })
})

describe('the stamp', () => {
  it('is UTC, matching every other time on the page', () => {
    expect(stampTime('2026-08-22T19:04:11Z')).toBe('19:04 UTC')
  })

  it('does not crash on a malformed timestamp', () => {
    expect(stampTime('not a date')).toBe('—')
  })
})

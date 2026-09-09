import { describe, expect, it } from 'vitest'

import { payload } from '../fixtures'
import type { Selection } from '../types'
import { boardKey, detailKey, searchKey, selectionOf } from './queries'

const initial = payload()
const selection: Selection = {
  market: initial.market, sources: initial.sources, segments: initial.segments,
  minVenues: initial.min_venues, window: initial.window_hours,
  sort: initial.sort, dir: initial.dir,
}

describe('cache identity', () => {
  it('keeps listing context in cache identity', () => {
    const us = { ...selection, market: 'us' as const }
    expect(boardKey(us)).not.toEqual(boardKey({ ...us, market: 'de' }))
    expect(detailKey('AAA', us, '1D')).not.toEqual(detailKey('AAA', us, '1M'))
  })

  it('separates every dimension the server filters on', () => {
    // A key that held only the market would serve the reader a board built
    // for a different window, sort or source set -- silently, and only
    // sometimes, which is the worst kind of only sometimes.
    const variants: Selection[] = [
      { ...selection, sources: ['bluesky'] },
      { ...selection, segments: ['large'] },
      { ...selection, window: 24 },
      { ...selection, minVenues: 2 },
      { ...selection, sort: 'mentions' },
      { ...selection, sort: 'mentions', dir: 'asc' },
    ]
    const base = JSON.stringify(boardKey(selection))
    for (const variant of variants) {
      expect(JSON.stringify(boardKey(variant))).not.toBe(base)
    }
    expect(new Set(variants.map((v) => JSON.stringify(boardKey(v)))).size)
      .toBe(variants.length)
  })

  it('gives the same selection the same key', () => {
    expect(boardKey({ ...selection })).toEqual(boardKey({ ...selection }))
  })

  it('separates one panel from another', () => {
    expect(detailKey('AAA', selection, '1D'))
      .not.toEqual(detailKey('BBB', selection, '1D'))
  })

  it('keeps the panel scoped to the listing that opened it', () => {
    // The breakdown and the posts describe the same window and sources the
    // row's phrase did. A panel keyed without them would answer for a
    // selection the reader is no longer looking at.
    const other = { ...selection, sources: ['fourchan'], window: 24 }
    expect(detailKey('AAA', selection, '1D'))
      .not.toEqual(detailKey('AAA', other, '1D'))
  })

  it('never collides a search with a board', () => {
    expect(searchKey('AA')).not.toEqual(boardKey(selection))
    expect(searchKey('AA')).not.toEqual(searchKey('AAA'))
  })

  it('namespaces every hub key away from the old board island', () => {
    for (const key of [boardKey(selection), detailKey('AAA', selection, '1D'),
                       searchKey('AA')]) {
      expect(key[0]).toBe('radar-hub')
    }
  })

  it('does not spend two requests on the same search', () => {
    expect(searchKey('AAPL ')).toEqual(searchKey('AAPL'))
  })

  it('reads a payload’s own selection back out of it', () => {
    // This is what decides whether the embedded board may seed a cache key.
    // A payload built under one filter presented as the answer to another
    // would arrive as real data with a fresh timestamp.
    expect(selectionOf(initial)).toEqual(selection)
    expect(boardKey(selectionOf(initial))).toEqual(boardKey(selection))
    expect(boardKey(selectionOf(payload({ market: 'de' }))))
      .not.toEqual(boardKey(selection))
  })
})

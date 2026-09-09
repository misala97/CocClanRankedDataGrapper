import { describe, expect, it } from 'vitest'

import { payload } from '../fixtures'
import type { Selection } from '../types'
import { hashFor, readRoute, readSelection, readSpan, urlFor } from './navigation'

const initial = payload()
const selection: Selection = {
  market: initial.market, sources: initial.sources, segments: initial.segments,
  minVenues: initial.min_venues, window: initial.window_hours,
  sort: initial.sort, dir: initial.dir,
}

describe('reading the address bar', () => {
  it('opens direct research links', () => {
    expect(readRoute('#research/AAA')).toEqual({ page: 'research', ticker: 'AAA' })
    expect(readRoute('#nonsense')).toEqual({ page: 'missing' })
  })

  it('treats an empty hash as the overview', () => {
    expect(readRoute('')).toEqual({ page: 'overview' })
    expect(readRoute('#')).toEqual({ page: 'overview' })
    expect(readRoute('#overview')).toEqual({ page: 'overview' })
  })

  it('knows every implemented destination', () => {
    for (const page of ['overview', 'chatter', 'watching', 'activity', 'admin']) {
      expect(readRoute(`#${page}`)).toEqual({ page })
    }
  })

  it('does not invent a destination the release does not have', () => {
    // News, Combined, Portfolio and Analysis live in the prototype and the
    // roadmap. A bookmark to one of them is a dead link, not a blank page.
    for (const page of ['news', 'combined', 'portfolio', 'analysis']) {
      expect(readRoute(`#${page}`)).toEqual({ page: 'missing' })
    }
  })

  it('survives malformed percent encoding', () => {
    // decodeURIComponent throws on a lone %; a thrown route is a white page.
    expect(readRoute('#research/%E0%A4%A')).toEqual({ page: 'missing' })
    expect(readRoute('#research/%')).toEqual({ page: 'missing' })
  })

  it('reads an encoded ticker and normalises its case', () => {
    expect(readRoute('#research/brk%2Eb')).toEqual({ page: 'research', ticker: 'BRK.B' })
    expect(readRoute('#research/aaa')).toEqual({ page: 'research', ticker: 'AAA' })
  })

  it('has no research route without a ticker', () => {
    expect(readRoute('#research')).toEqual({ page: 'missing' })
    expect(readRoute('#research/')).toEqual({ page: 'missing' })
  })

  it('round-trips every route through its hash', () => {
    const routes = [{ page: 'overview' }, { page: 'chatter' }, { page: 'watching' },
                    { page: 'activity' }, { page: 'admin' },
                    { page: 'research', ticker: 'BRK.B' }] as const
    for (const route of routes) {
      expect(readRoute(hashFor(route))).toEqual(route)
    }
  })
})

describe('reading the filters out of the query', () => {
  it('falls back to the board the server already parsed', () => {
    // The server's own answer, not a guess: an absent query means whatever
    // defaults it applied, which the payload echoes back.
    expect(readSelection('', selection)).toEqual(selection)
  })

  it('honours a selection the reader made', () => {
    const read = readSelection(
      '?market=de&sources=bluesky&window=24&segment=large,fund&venues=2'
      + '&sort=mentions&dir=asc', selection)
    expect(read).toEqual({
      market: 'de', sources: ['bluesky'], segments: ['large', 'fund'],
      minVenues: 2, window: 24, sort: 'mentions', dir: 'asc',
    })
  })

  it('keeps an empty segment as All rather than as the server default', () => {
    // `segment=` is how the surface asks for All. Dropping it would hand the
    // server its own default, which is Discover -- so the All chip would
    // silently do nothing.
    expect(readSelection('?segment=', selection).segments).toEqual([])
  })

  it('refuses values the API would reject instead of forwarding them', () => {
    const read = readSelection(
      '?market=moon&window=abc&venues=9&sort=vibes&dir=sideways', selection)
    expect(read.market).toBe(selection.market)
    expect(read.window).toBe(selection.window)
    expect(read.minVenues).toBe(selection.minVenues)
    expect(read.sort).toBe(selection.sort)
    expect(read.dir).toBe(selection.dir)
  })

  it('drops a source the server never offered', () => {
    // all_sources is the server's vocabulary. A stale bookmark naming a
    // retired source must not turn into a 400 the reader cannot escape.
    const read = readSelection('?sources=bluesky,stocktwits', selection,
                               initial.all_sources)
    expect(read.sources).toEqual(['bluesky'])
  })

  it('keeps a concrete subreddit selection intact', () => {
    // reddit:wallstreetbets is narrower than reddit and must not widen.
    const read = readSelection('?sources=reddit:wallstreetbets', selection,
                               initial.all_sources)
    expect(read.sources).toEqual(['reddit:wallstreetbets'])
  })

  it('never yields an empty source list', () => {
    expect(readSelection('?sources=', selection).sources).toEqual(selection.sources)
  })
})

describe('the research span', () => {
  it('defaults to one day', () => {
    expect(readSpan('')).toBe('1D')
  })

  it('travels in the URL', () => {
    expect(readSpan('?span=1M')).toBe('1M')
  })

  it('ignores a span the panel cannot draw', () => {
    expect(readSpan('?span=10Y')).toBe('1D')
  })
})

describe('writing the address bar', () => {
  it('carries route, filters and span together', () => {
    const url = urlFor({ page: 'research', ticker: 'AAA' }, selection, '1M')
    expect(url).toContain('#research/AAA')
    expect(url).toContain('market=us')
    expect(url).toContain('span=1M')
  })

  it('leaves the span out of a listing URL', () => {
    // It belongs to one ticker's chart. On the chatter list it would be a
    // parameter describing nothing on screen.
    expect(urlFor({ page: 'chatter' }, selection, '1M')).not.toContain('span=')
  })

  it('encodes a ticker that needs it', () => {
    expect(urlFor({ page: 'research', ticker: 'BRK.B' }, selection, '1D'))
      .toContain('#research/BRK.B')
  })
})

import { describe, expect, it } from 'vitest'

import { payload } from '../fixtures'
import type { Selection } from '../types'
import { queryFor } from '../api'
import {
  hashFor, isInPageAnchor, readRoute, readSelection, readSpan, urlFor,
} from './navigation'

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

  it('is case-insensitive about page names', () => {
    // A hash typed or pasted with a capital is the same destination.
    expect(readRoute('#Overview')).toEqual({ page: 'overview' })
    expect(readRoute('#ACTIVITY')).toEqual({ page: 'activity' })
  })

  it('knows an element id from a destination', () => {
    // The skip link points at #rh-main, which is an element. Reading it as a
    // route name replaced the page with the recovery view -- on the first
    // control a keyboard reader meets.
    const doc = document.implementation.createHTMLDocument()
    const main = doc.createElement('main')
    main.id = 'rh-main'
    doc.body.append(main)

    expect(isInPageAnchor('#rh-main', doc)).toBe(true)
    expect(isInPageAnchor('#portfolio', doc)).toBe(false)
    expect(isInPageAnchor('', doc)).toBe(false)
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

  it('is the inverse of the query the client writes', () => {
    // The property that keeps a URL meaning one thing. queryFor omits venues
    // at 1 and omits sort/dir without a sort, so their absence has to read as
    // the default -- resolving them to the page's opening echo instead made
    // the same address render one board after Back and another when opened
    // fresh.
    const opened: Selection = { ...selection, minVenues: 2, sort: 'mentions',
                                dir: 'asc' }
    const cleared: Selection = { ...selection, minVenues: 1, sort: null,
                                 dir: 'desc' }
    for (const state of [opened, cleared, selection]) {
      expect(readSelection(`?${queryFor(state)}`, opened, initial.all_sources))
        .toEqual(state)
    }
  })

  it('keeps a legacy segment spelling the server still accepts', () => {
    // `?segment=small` builds the discover board on the server and is echoed
    // back verbatim. Dropping it here made the controls say All while the
    // board on screen said Discover.
    expect(readSelection('?segment=small', selection).segments).toEqual(['small'])
  })

  it('does not widen the board for a garbled segment', () => {
    // Entirely unrecognisable is a mangled bookmark, not a request for All.
    expect(readSelection('?segment=bogus', selection).segments)
      .toEqual(selection.segments)
  })

  it('deduplicates and bounds the source list', () => {
    // Past the server's ceiling the request is a 400, which reaches the
    // reader as an unexplained network error.
    const many = Array.from({ length: 80 }, (_, i) => `reddit:sub${i}`)
    const read = readSelection(`?sources=${many.join(',')}`, selection,
                               initial.all_sources)
    expect(read.sources.length).toBeLessThanOrEqual(64)

    expect(readSelection('?sources=bluesky,bluesky', selection,
                         initial.all_sources).sources).toEqual(['bluesky'])
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

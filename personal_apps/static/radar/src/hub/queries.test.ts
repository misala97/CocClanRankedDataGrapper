import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { payload } from '../fixtures'
import type { Selection } from '../types'
import { boardKey, detailKey, searchKey, selectionOf, useBoard } from './queries'

const initial = payload()
const selection: Selection = {
  sources: initial.sources, segments: initial.segments,
  minVenues: initial.min_venues, window: initial.window_hours,
  sort: initial.sort, dir: initial.dir,
}

describe('cache identity', () => {
  it('keeps listing context in cache identity, and no market', () => {
    expect(boardKey(selection)).not.toEqual(boardKey({ ...selection, window: 24 }))
    expect(detailKey('AAA', selection, '1D'))
      .not.toEqual(detailKey('AAA', selection, '1M'))
    expect(JSON.stringify(boardKey(selection))).not.toContain('market')
    expect(detailKey('AAA', selection, '1D')).not.toContain('us')
  })

  it('separates every dimension the server filters on', () => {
    // A key that held only the sources would serve the reader a board built
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
    expect(boardKey(selectionOf(payload({ window_hours: 24 }))))
      .not.toEqual(boardKey(selection))
    expect('market' in selectionOf(initial)).toBe(false)
  })
})

describe('a page that has no use for a board (HA1)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  function Probe({ enabled, seed }: { enabled: boolean; seed?: typeof initial }) {
    const board = useBoard(selection, seed, true, enabled)
    return createElement('p', { 'data-testid': 'state' },
                         `${board.fetchStatus}/${board.answer ? 'answer' : 'none'}`)
  }

  function mount(props: { enabled: boolean; seed?: typeof initial }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(createElement(QueryClientProvider, { client }, createElement(Probe, props)))
  }

  it('sends nothing while disabled and keeps the embedded seed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const boards = vi.spyOn(api, 'fetchBoard')
    // A board that is already past its fresh bound would, when enabled, be
    // asked about again at once; disabled, it is left alone.
    const stale = payload({ generated_at: new Date(Date.now() - 600_000).toISOString(),
                            as_of: new Date(Date.now() - 600_000).toISOString() })
    mount({ enabled: false, seed: stale })
    expect(screen.getByTestId('state')).toHaveTextContent('idle/answer')
    await vi.advanceTimersByTimeAsync(130_000)
    expect(boards).not.toHaveBeenCalled()
  })

  it('fetches as before once enabled', async () => {
    const boards = vi.spyOn(api, 'fetchBoard').mockResolvedValue(payload())
    mount({ enabled: true })
    await vi.waitFor(() => expect(boards).toHaveBeenCalledTimes(1))
  })
})

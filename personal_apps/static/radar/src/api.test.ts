import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { defaultDirection, fetchSearch, queryFor, setWatch } from './api'
import { resetCsrfCache } from './csrf'
import type { Selection } from './types'

const baseSelection: Selection = {
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [],
  window: 4, minVenues: 1, sort: null, dir: 'desc' as const,
}

beforeEach(() => {
  document.head.innerHTML = '<meta name="csrf-token" content="tok-123">'
  resetCsrfCache()
})
afterEach(() => { vi.unstubAllGlobals(); document.head.innerHTML = '' })

describe('search', () => {
  it('asks for the query and unwraps the matches', async () => {
    const spy = vi.fn(async (_url: string) => ({
      ok: true, redirected: false, status: 200,
      json: async () => ({ matches: [{ ticker: 'NVDA', name: 'NVIDIA', exchange: 'Q', segment: 'large', watching: false }] }),
    }))
    vi.stubGlobal('fetch', spy)

    const found = await fetchSearch('nv idia')

    expect(String(spy.mock.calls[0]![0])).toBe('/radar/api/search?q=nv%20idia')
    expect(found.map((m) => m.ticker)).toEqual(['NVDA'])
  })
})

describe('watching', () => {
  it('PUTs to mark and DELETEs to unmark, with the csrf token, and returns the list', async () => {
    const spy = vi.fn(async () => ({
      ok: true, redirected: false, status: 200,
      json: async () => ({ watching: ['NVDA'] }),
    }))
    vi.stubGlobal('fetch', spy)

    expect(await setWatch('NVDA', true)).toEqual(['NVDA'])
    expect(await setWatch('NVDA', false)).toEqual(['NVDA'])

    const [onUrl, onInit] = spy.mock.calls[0] as unknown as [string, RequestInit]
    const [, offInit] = spy.mock.calls[1] as unknown as [string, RequestInit]
    expect(onUrl).toBe('/radar/api/watch/NVDA')
    expect(onInit.method).toBe('PUT')
    expect(offInit.method).toBe('DELETE')
    expect((onInit.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok-123')
    expect((onInit.headers as Record<string, string>).Accept).toBe('application/json')
  })
})


describe('sort in the query', () => {
  it('is absent when no sort is asked for', () => {
    const query = queryFor({ ...baseSelection, sort: null, dir: 'desc' as const })
    expect(query).not.toContain('sort=')
    expect(query).not.toContain('dir=')
  })

  it('carries the key and the direction when one is', () => {
    const query = queryFor({ ...baseSelection, sort: 'mentions', dir: 'asc' })
    expect(query).toContain('sort=mentions')
    expect(query).toContain('dir=asc')
  })
})

describe('defaultDirection', () => {
  it('reads ticker A to Z and every number largest first', () => {
    expect(defaultDirection('ticker')).toBe('asc')
    for (const key of ['mentions', 'divergence', 'ratio', 'move', 'lean'] as const) {
      expect(defaultDirection(key)).toBe('desc')
    }
  })
})

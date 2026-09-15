import { afterEach, describe, expect, it, vi } from 'vitest'

import { PriceChartUnavailable, fetchPriceChart, validatePriceChart } from './priceChart'
import type { ChartSpan, PriceChartResponse } from './priceChart'
import { priceChartResponse } from './priceChartFixtures'

const expected: { ticker: string; span: ChartSpan } = { ticker: 'AAA', span: '1D' }

function refused(raw: unknown, want = expected): string {
  try {
    validatePriceChart(raw, want)
  } catch (error) {
    return (error as PriceChartUnavailable).reason
  }
  return 'accepted'
}

function mutate(change: (copy: PriceChartResponse) => void): PriceChartResponse {
  const copy = JSON.parse(JSON.stringify(priceChartResponse())) as PriceChartResponse
  change(copy)
  return copy
}

afterEach(() => { vi.unstubAllGlobals() })

describe('validating the answer at the boundary', () => {
  it('accepts the contract', () => {
    expect(refused(priceChartResponse())).toBe('accepted')
  })

  it('refuses a late reply about another ticker or span rather than drawing it', () => {
    expect(refused(priceChartResponse({}, 'BBB'))).toBe('mismatch')
    expect(refused(priceChartResponse(), { ticker: 'AAA', span: '1W' })).toBe('mismatch')
  })

  it('refuses tone that does not reconcile to its own count', () => {
    expect(refused(mutate((c) => { c.chatter.tone.slots[0]!.bullish = 5 }))).toBe('invalid')
    expect(refused(mutate((c) => { c.chatter.tone.slots.pop() }))).toBe('invalid')
    expect(refused(mutate((c) => { c.chatter.tone.slots[2] = c.chatter.tone.slots[1]! }))).toBe('invalid')
  })

  it('refuses chatter that does not share the window bounds', () => {
    expect(refused(mutate((c) => { c.chatter.from = '2026-09-15T07:45:00Z' }))).toBe('invalid')
  })

  it('refuses an unknown count dressed as observed, and a zero dressed as unknown', () => {
    expect(refused(mutate((c) => { c.chatter.slots[2]!.coverage = 'observed' }))).toBe('invalid')
    expect(refused(mutate((c) => { c.chatter.slots[1]!.coverage = 'unknown' }))).toBe('invalid')
  })

  it('refuses nonpositive prices, a normal line and other versions', () => {
    expect(refused(mutate((c) => { c.price!.points[0]!.value = 0 }))).toBe('invalid')
    expect(refused(mutate((c) => { (c.chatter as { normal_per_slot: unknown }).normal_per_slot = 3 }))).toBe('invalid')
    expect(refused(mutate((c) => { (c as { version: unknown }).version = 2 }))).toBe('invalid')
    expect(refused(null)).toBe('invalid')
  })

  it('accepts a window with no price at all', () => {
    expect(refused(mutate((c) => { c.price = null }))).toBe('accepted')
  })
})

describe('the one request', () => {
  it('sends only span, market and sources', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(priceChartResponse()),
      { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await fetchPriceChart('AAA', ['bluesky', 'reddit'], '1D')
    const url = new URL(fetch.mock.calls[0]![0] as string, 'http://x')
    expect(url.pathname).toBe('/radar/api/ticker/AAA/price-chart')
    expect([...url.searchParams.keys()]).toEqual(['span', 'market', 'sources'])
    expect(url.searchParams.get('sources')).toBe('bluesky,reddit')
    expect(url.searchParams.get('market')).toBe('us')
  })

  it.each([
    [404, { code: 'feature_disabled' }, 'disabled'],
    [404, { code: 'unknown_ticker' }, 'missing'],
    [422, { code: 'unsupported_instrument' }, 'unsupported'],
    [400, { code: 'unknown_query' }, 'invalid'],
    [503, { code: 'read_limit' }, 'limit'],
    [503, { code: 'store_unavailable' }, 'unavailable'],
    [500, {}, 'server'],
  ])('maps %i %j to %s', async (status, body, reason) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })))
    await expect(fetchPriceChart('AAA', ['bluesky'], '1D')).rejects.toMatchObject({ reason })
  })

  it('treats a redirect as an expired session, an unreadable body as invalid and a throw as network', async () => {
    const redirected = new Response('<html>', { status: 200 })
    Object.defineProperty(redirected, 'redirected', { value: true })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(redirected))
    await expect(fetchPriceChart('AAA', [], '1D')).rejects.toMatchObject({ reason: 'session' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not json', { status: 200 })))
    await expect(fetchPriceChart('AAA', [], '1D')).rejects.toMatchObject({ reason: 'invalid' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(fetchPriceChart('AAA', [], '1D')).rejects.toMatchObject({ reason: 'network' })
  })
})

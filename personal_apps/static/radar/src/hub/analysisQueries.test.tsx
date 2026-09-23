import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from './analysisApi'
import { analysis } from './analysisFixtures'
import {
  ANALYSIS_GC_MS, ANALYSIS_RESOLVE_GC_MS, ANALYSIS_STALE_MS, analysisKey, resolveKey, useAnalysis,
} from './analysisQueries'
import type { AnalysisPayload } from './analysisTypes'

const RANGE = { from: '2026-09-07', to: '2026-09-13' }

afterEach(() => vi.restoreAllMocks())

describe('cache identity (C12)', () => {
  it('names both IDs, the ticker, both dates and the schema version', () => {
    const base = analysisKey(11, 7, 'AAA', RANGE)
    expect(base[0]).toBe('radar-hub')
    expect(base).toContain('v1')
    const variants = [
      analysisKey(12, 7, 'AAA', RANGE), analysisKey(11, 8, 'AAA', RANGE),
      analysisKey(11, 7, 'AAB', RANGE), analysisKey(11, 7, 'AAA', { ...RANGE, from: '2026-09-08' }),
      analysisKey(11, 7, 'AAA', { ...RANGE, to: '2026-09-12' }),
    ]
    for (const variant of variants) expect(variant).not.toEqual(base)
    expect(new Set(variants.map((v) => JSON.stringify(v))).size).toBe(variants.length)
    expect(analysisKey(11, 7, 'AAA', { ...RANGE })).toEqual(base)
    expect(resolveKey('AAA')).not.toEqual(resolveKey('AAB'))
    expect(resolveKey('AAA')[0]).toBe('radar-hub')
  })

  it('keeps the agreed lifetimes', () => {
    expect(ANALYSIS_STALE_MS).toBe(60_000)
    expect(ANALYSIS_GC_MS).toBe(300_000)
    // A resolution is never kept for a later pin (P2-7).
    expect(ANALYSIS_RESOLVE_GC_MS).toBe(0)
  })
})

function Probe({ companyId, instrumentId, ticker }: {
  companyId: number
  instrumentId: number
  ticker: string
}) {
  const query = useAnalysis(companyId, instrumentId, ticker, RANGE)
  return (
    <div>
      <p data-testid="status">{query.status}/{query.fetchStatus}</p>
      <p data-testid="company">{query.data ? `${query.data.company.ticker}#${query.data.company.id}` : 'none'}</p>
      <p data-testid="placeholder">{String(query.isPlaceholderData)}</p>
    </div>
  )
}

function mount(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
  return { client, view }
}

describe('lifecycle (C12)', () => {
  it('never shows A under B: a slow answer for the previous key stays with its key', async () => {
    let releaseA: (value: AnalysisPayload) => void = () => undefined
    const slowA = new Promise<AnalysisPayload>((resolve) => { releaseA = resolve })
    const spy = vi.spyOn(api, 'fetchAnalysis').mockImplementation((companyId) => {
      if (companyId === 11) return slowA
      return Promise.resolve(analysis({
        company: { id: 12, ticker: 'BBB', name: 'Bbb', first_seen: '2026-01-01T00:00:00Z' },
      }))
    })
    const { client, view } = mount(<Probe companyId={11} instrumentId={7} ticker="AAA" />)
    expect(screen.getByTestId('company')).toHaveTextContent('none')
    view.rerender(
      <QueryClientProvider client={client}><Probe companyId={12} instrumentId={9} ticker="BBB" /></QueryClientProvider>)
    await waitFor(() => expect(screen.getByTestId('company')).toHaveTextContent('BBB#12'))
    // No previous-key placeholder was ever offered.
    expect(screen.getByTestId('placeholder')).toHaveTextContent('false')
    await act(async () => { releaseA(analysis()) })
    // B's screen did not change. A's late answer either went to A's own
    // entry or was discarded with its cancelled request; it is never B's.
    expect(screen.getByTestId('company')).toHaveTextContent('BBB#12')
    const a = client.getQueryData<AnalysisPayload>(analysisKey(11, 7, 'AAA', RANGE))
    expect(a === undefined || a.company.id === 11).toBe(true)
    expect(client.getQueryData<AnalysisPayload>(analysisKey(12, 9, 'BBB', RANGE))?.company.id).toBe(12)
    expect(spy).toHaveBeenCalledTimes(2)
  })

  it('does not fetch while any part of the identity or window is unknown', () => {
    const spy = vi.spyOn(api, 'fetchAnalysis')
    function Idle() {
      const query = useAnalysis(null, 7, 'AAA', RANGE)
      return <p data-testid="idle">{query.fetchStatus}</p>
    }
    mount(<Idle />)
    expect(screen.getByTestId('idle')).toHaveTextContent('idle')
    expect(spy).not.toHaveBeenCalled()
  })

  it('keeps the last answer beside a failed refresh rather than dropping it', async () => {
    vi.spyOn(api, 'fetchAnalysis')
      .mockResolvedValueOnce(analysis())
      .mockRejectedValueOnce(new api.AnalysisUnavailable('timeout'))
    function Refresh() {
      const query = useAnalysis(11, 7, 'AAA', RANGE)
      return (
        <div>
          <p data-testid="state">{query.status}/{String(query.isError)}/{query.data ? 'data' : 'none'}</p>
          <button type="button" onClick={() => void query.refetch()}>again</button>
        </div>
      )
    }
    mount(<Refresh />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('success/false/data'))
    await act(async () => { screen.getByRole('button', { name: 'again' }).click() })
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('error/true/data'))
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { detail, payload } from '../fixtures'
import type { PanelSpan, Selection } from '../types'
import * as priceChart from './priceChart'
import { PriceChartUnavailable } from './priceChart'
import { priceChartResponse, yahooPrice } from './priceChartFixtures'
import {
  PENDING_POLLS, PENDING_POLL_MS, REFRESH_MS, priceChartInterval, priceChartKey, selectionOf,
} from './queries'
import { ChartSection } from './ResearchContent'
import { SelectedPriceCharts } from './selectedPriceContext'

const selection: Selection = selectionOf(payload())

function show({ offered = true, span = '1D' as PanelSpan, ticker = 'AAA',
                client = new QueryClient({ defaultOptions: { queries: { retry: false } } }) } = {}) {
  const tree = (t: string) => (
    <QueryClientProvider client={client}>
      <SelectedPriceCharts.Provider value={offered}>
        <div className="rh">
          <ChartSection chart={detail(t).chart} ticker={t} span={span} onSpan={vi.fn()}
                        selection={selection} />
        </div>
      </SelectedPriceCharts.Provider>
    </QueryClientProvider>
  )
  const result = render(tree(ticker))
  return { ...result, client, rerenderWith: (t: string) => result.rerender(tree(t)) }
}

afterEach(() => { vi.restoreAllMocks() })

describe('which chart the section draws', () => {
  it('keeps the original chart when the server does not offer the new one', () => {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart')
    const { container } = show({ offered: false })
    expect(container.querySelector('svg.pxchart')).not.toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['1M', '6M'] as const)('keeps it for %s', (span) => {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart')
    const { container } = show({ span })
    expect(container.querySelector('svg.pxchart')).not.toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('draws the selected-session chart for a US selection on 1D, from its own request', async () => {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart').mockResolvedValue(priceChartResponse())
    const { container } = show()
    expect(screen.getByRole('status')).toHaveTextContent('Loading the 1D price and chatter chart for AAA')
    expect(container.querySelector('svg.pxchart')).toBeNull()
    await screen.findByText('Current session so far')
    expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull()
    expect(container.querySelector('svg.pxchart')).toBeNull()
    expect(fetch).toHaveBeenCalledWith('AAA', selection.sources, '1D', expect.anything())
    expect(screen.getByText(/Current session so far · 1-minute bar closes · mentions per 15 min/))
      .toBeInTheDocument()
  })

  it('falls back to the original chart for a company the server cannot chart that way', async () => {
    vi.spyOn(priceChart, 'fetchPriceChart')
      .mockRejectedValue(new PriceChartUnavailable('unsupported', 'unsupported_instrument'))
    const { container } = show()
    await waitFor(() => expect(container.querySelector('svg.pxchart')).not.toBeNull())
  })

  it('offers a chart-local retry when the chart fails', async () => {
    // A transient refusal is retried once by the hook itself; only then is
    // the failure the reader's to retry.
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart')
      .mockRejectedValue(new PriceChartUnavailable('unavailable', 'store_unavailable'))
    show()
    const alert = await screen.findByRole('alert', {}, { timeout: 4000 })
    expect(alert).toHaveTextContent('The chart data could not be read.')
    expect(fetch).toHaveBeenCalledTimes(2)
    fetch.mockResolvedValue(priceChartResponse())
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByText('Current session so far')
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('never shows an old company’s late answer under the new company', async () => {
    let releaseOld: (value: priceChart.PriceChartResponse) => void = () => {}
    vi.spyOn(priceChart, 'fetchPriceChart').mockImplementation((ticker) => ticker === 'AAA'
      ? new Promise((resolve) => { releaseOld = resolve })
      : Promise.resolve(priceChartResponse({}, 'BBB')))
    const { rerenderWith, container } = show()
    rerenderWith('BBB')
    await screen.findByText('Current session so far')
    releaseOld(priceChartResponse())
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(container.querySelector('.rh-sp-summary')?.textContent).toMatch(/^BBB,/)
  })
})

// F3 (MD-SELECTED-PRICE-CORRECTION-1): a failed refresh is a failure, not a
// quiet footnote under the previous chart. TanStack keeps the last answer in
// its cache when a refetch errors, and nothing on the client can prove that
// answer still describes the same identity and window -- a session may have
// rolled over or the listing been remapped -- so the chart shows its retry
// state until a refresh succeeds. Standalone Research and the chatter
// workspace both draw this ChartSection.
describe('when a refresh fails after an answer', () => {
  const failure = () => new PriceChartUnavailable('unavailable', 'store_unavailable')
  const closedOtherIdentity = () => priceChartResponse({
    window: { ...priceChartResponse().window, partial: false, session_dates: ['2026-09-14'] },
    identity: { ...priceChartResponse().identity, fingerprint: 'remapped'.padEnd(32, '1') },
  })

  async function answeredThenFailed(first: priceChart.PriceChartResponse) {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart').mockResolvedValue(first)
    const view = show()
    await waitFor(() => expect(view.container.querySelector('svg.rh-sp-svg')).not.toBeNull())
    fetch.mockRejectedValue(failure())
    await act(async () => { await view.client.refetchQueries() })
    return { ...view, fetch }
  }

  function expectNoOldChart(container: HTMLElement) {
    expect(container.querySelector('svg.rh-sp-svg')).toBeNull()
    expect(container.querySelector('svg.pxchart')).toBeNull()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/Current session so far|Last completed session|\bnow\b|so far/)
    expect(text).not.toMatch(/Showing the chart answered/)
  }

  it.each([
    ['the live session it answered for (a rollover may have happened)', () => priceChartResponse()],
    ['a closed session of an identity that may since have been remapped', closedOtherIdentity],
  ])('shows the chart-local retry instead of %s', async (_label, first) => {
    const { container, client } = await answeredThenFailed(first())
    // TanStack notifies observers on its own schedule, after act() resolves.
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The latest 1D chart for AAA could not be loaded')
    expect(alert).toHaveTextContent('The chart data could not be read.')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
    expectNoOldChart(container)
    // The previous answer is still in the cache; it is simply not shown.
    expect(client.getQueryData(priceChartKey('AAA', selection.sources, '1D'))).toBeDefined()
  }, 10_000)

  it('draws the chart again once a refresh succeeds', async () => {
    const { container, fetch } = await answeredThenFailed(priceChartResponse())
    fetch.mockResolvedValue(priceChartResponse({ generated_at: '2026-09-15T09:08:00Z' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull())
    expect(screen.queryByRole('alert')).toBeNull()
    // Caption and chart header both say it again once the chart is back.
    expect(screen.getAllByText(/Current session so far/).length).toBeGreaterThan(0)
  }, 10_000)

  it('keeps drawing a valid stale or stored-fallback answer the server sent with HTTP 200', async () => {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart').mockResolvedValue(priceChartResponse())
    const { container, client } = show()
    await waitFor(() => expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull())
    fetch.mockResolvedValue(priceChartResponse({
      acquisition: { state: 'pending', retry_after_seconds: 2, reason: 'refreshing an aged series' },
      price: yahooPrice({ stale: true, cache_age_seconds: 400 }),
    }))
    await act(async () => { await client.refetchQueries() })
    expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    const regime = 'finnhub:trade:unknown'
    fetch.mockResolvedValue(priceChartResponse({
      acquisition: { state: 'backoff', retry_after_seconds: 60, reason: 'the provider throttled this process' },
      price: yahooPrice({
        source: 'finnhub', kind: 'stored_quote', fallback: true, interval_seconds: null, price_basis: 'trade',
        regimes: [{ id: regime, source: 'finnhub', price_basis: 'trade', adjustment_basis: 'unknown' }],
        points: yahooPrice().points.map((point) => ({ ...point, regime, provisional: false })),
      }),
    }))
    await act(async () => { await client.refetchQueries() })
    expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('still falls back to the original chart when the refresh says the company cannot be charted', async () => {
    const fetch = vi.spyOn(priceChart, 'fetchPriceChart').mockResolvedValue(priceChartResponse())
    const { container, client } = show()
    await waitFor(() => expect(container.querySelector('svg.rh-sp-svg')).not.toBeNull())
    fetch.mockRejectedValue(new PriceChartUnavailable('unsupported', 'unsupported_instrument'))
    await act(async () => { await client.refetchQueries() })
    await waitFor(() => expect(container.querySelector('svg.pxchart')).not.toBeNull())
    expect(container.querySelector('svg.rh-sp-svg')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('falls back to the original chart when the server has the chart switched off', async () => {
    vi.spyOn(priceChart, 'fetchPriceChart')
      .mockRejectedValue(new PriceChartUnavailable('disabled', 'feature_disabled'))
    const { container } = show()
    await waitFor(() => expect(container.querySelector('svg.pxchart')).not.toBeNull())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('when the chart asks again', () => {
  const answer = (state: priceChart.AcquisitionState, retry: number | null = null) =>
    priceChartResponse({ acquisition: { state, retry_after_seconds: retry, reason: null } })

  it('never for a hidden tab or before an answer', () => {
    expect(priceChartInterval(answer('pending'), { visible: false, polls: 1 })).toBe(false)
    expect(priceChartInterval(undefined, { visible: true, polls: 0 })).toBe(false)
  })

  it('polls a pending acquisition at most five times, then on the minute', () => {
    for (let polls = 1; polls <= PENDING_POLLS; polls++) {
      expect(priceChartInterval(answer('pending'), { visible: true, polls })).toBe(PENDING_POLL_MS)
    }
    expect(priceChartInterval(answer('pending'), { visible: true, polls: PENDING_POLLS + 1 }))
      .toBe(REFRESH_MS)
  })

  it('never asks sooner than retry_after_seconds', () => {
    expect(priceChartInterval(answer('busy', 5), { visible: true, polls: 1 })).toBe(5000)
    expect(priceChartInterval(answer('backoff', 120), { visible: true, polls: 0 })).toBe(120_000)
    expect(priceChartInterval(answer('unavailable', 86_400), { visible: true, polls: 0 }))
      .toBe(86_400_000)
  })

  it('refreshes ready, disabled and unavailable charts on the minute', () => {
    for (const state of ['ready', 'disabled', 'unavailable'] as const) {
      expect(priceChartInterval(answer(state), { visible: true, polls: 0 })).toBe(REFRESH_MS)
    }
  })

  it('keys on ticker, sources and span, and not on the board window', () => {
    const key = priceChartKey('AAA', ['bluesky', 'reddit'], '1W')
    expect(key).toEqual(['radar-hub', 'price-chart', 'AAA', 'bluesky,reddit', '1W',
      'selected-price-v1'])
  })
})

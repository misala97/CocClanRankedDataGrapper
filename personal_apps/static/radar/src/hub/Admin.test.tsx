import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import type { OpsPayload } from '../types'
import { Admin } from './Admin'
import type { SelectedPriceOps } from './priceChart'

const ops = (over: Partial<OpsPayload> = {}): OpsPayload => ({
  generated_at: '2026-09-09T10:00:00Z',
  spend: { today_usd: 0, month_usd: 1.25, unpriced_tokens: 501_000 },
  sentiment: {
    pending: 12, gated_pending: 4, p95_age_minutes: 31,
    review: { demanded: 5, attempted: 5, served: 4, capped: 1, over_ceiling: 0 },
  },
  market_data: {
    quote_basis_24h: { trade: 900, midpoint: 12 },
    grouped_closes: {
      latest_accepted_date: '2026-09-08', retryable_gaps: [],
      counts: { provider_rows: 9000, written: 8800 },
      error_code: null, http_status: null, backoff_until: null,
    },
    post_close_claims: {},
  },
  capture: { latest_observed_at: null },
  ...over,
})

function show(payload?: OpsPayload, error?: unknown) {
  if (error) vi.spyOn(api, 'fetchOps').mockRejectedValue(error)
  else vi.spyOn(api, 'fetchOps').mockResolvedValue(payload!)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Admin />
    </QueryClientProvider>,
  )
}

afterEach(() => { vi.restoreAllMocks() })

describe('selected price chart health', () => {
  const health = (over: Partial<SelectedPriceOps> = {}): SelectedPriceOps => ({
    scope: 'process', pid: 4242, coordinator_started_at: '2026-09-15T08:00:00Z',
    charts_enabled: true, yahoo_enabled: false, alpaca_enabled: false,
    credentials_present: true, source: null, source_state: 'disabled',
    configured_web_workers: 2, configured_web_workers_source: 'WEB_CONCURRENCY',
    note: 'Counts for this web process only, reset when it restarts.',
    in_flight: false, cache_keys: 3, cache_bytes: 20480, rolling_starts_60s: 1,
    backoff_until: null, quarantined: false,
    counters: { success: 4, timeout: 1, busy: 0 },
    latency: { count: 5, sum_seconds: 5, max_seconds: 2.5 },
    limits: { starts_per_60s: 10, deadline_seconds: 6 },
    ...over,
  })

  it('is shown as one web process’s figures, with its reset scope', async () => {
    show(ops({ selected_price_ops: health() }))
    expect(await screen.findByText('Selected price charts')).toBeVisible()
    expect(screen.getByText('This web process (pid 4242)')).toBeVisible()
    expect(screen.getByText('on / off')).toBeVisible()
    expect(screen.getByText('1 of 10')).toBeVisible()
    expect(screen.getByText('success 4 · timeout 1')).toBeVisible()
    expect(screen.getByText('avg 1.00 s · max 2.50 s')).toBeVisible()
    expect(screen.getByText(/reset when it restarts\./)).toBeVisible()
  })

  it('names the coordinator start and the configured workers with their source', async () => {
    show(ops({ selected_price_ops: health() }))
    await screen.findByText('Selected price charts')
    expect(screen.getByText('Acquisition coordinator started')).toBeVisible()
    expect(screen.getByText('15 Sep, 10:00 Berlin')).toBeVisible()
    expect(screen.getByText('Configured web workers')).toBeVisible()
    expect(screen.getByText('2 (from WEB_CONCURRENCY)')).toBeVisible()
    expect(screen.queryByText(/process started/i)).toBeNull()
  })

  it('says Unknown, and why, when no positive worker count is configured', async () => {
    show(ops({ selected_price_ops: health({ configured_web_workers: null, coordinator_started_at: null }) }))
    await screen.findByText('Selected price charts')
    expect(screen.getByText(
      'Unknown — WEB_CONCURRENCY is not set to a positive number; each worker keeps its own limits',
    )).toBeVisible()
    expect(screen.getByText('not started in this process')).toBeVisible()
    expect(screen.queryByText(/web workers are configured/)).toBeNull()
  })

  it('is absent when the server does not send it', async () => {
    show(ops())
    await screen.findByText(/\$1\.25/)
    expect(screen.queryByText('Selected price charts')).toBeNull()
  })

  // C1: the switch is Alpaca's now, and "the charts are on" is not the same
  // claim as "the source is acquiring".
  it('names the Alpaca switch and the effective source state, not just the chart flag', async () => {
    show(ops({ selected_price_ops: health() }))
    await screen.findByText('Selected price charts')
    expect(screen.getByText('Chart / Alpaca switch')).toBeVisible()
    expect(screen.getByText('on / off')).toBeVisible()
    // Neither source switch is on, so no source is claimed.
    expect(screen.getByText('None selected — switched off')).toBeVisible()
    expect(screen.queryByText(/Alpaca consolidated SIP/)).toBeNull()
  })

  // C2-4: the panel names the source the server actually selected. Claiming
  // Alpaca while the historical Yahoo source is the active one is a lie the
  // reader has no way to catch.
  it.each([
    ['alpaca_sip', 'active', 'Alpaca consolidated SIP (delayed) — acquiring'],
    ['alpaca_sip', 'credentials_missing',
     'Alpaca consolidated SIP (delayed) — credentials not configured'],
    ['alpaca_sip', 'charts_off', 'Alpaca consolidated SIP (delayed) — selected charts switched off'],
    ['yahoo_chart', 'yahoo', 'Yahoo chart — the historical Yahoo source is active instead'],
    [null, 'disabled', 'None selected — switched off'],
  ] as const)('reports %s in the %s state in words', async (source, state, text) => {
    show(ops({ selected_price_ops: health({
      source, source_state: state, alpaca_enabled: source === 'alpaca_sip' && state === 'active',
    }) }))
    await screen.findByText('Selected price charts')
    expect(screen.getByText(text)).toBeVisible()
  })

  it('says whether the credential variables hold anything, never what', async () => {
    show(ops({ selected_price_ops: health({ credentials_present: false }) }))
    await screen.findByText('Selected price charts')
    expect(screen.getByText('Credentials configured')).toBeVisible()
    // "Acquiring now" is the other no; neither says what a credential is.
    expect(screen.getAllByText('no')).toHaveLength(2)
    expect(document.body.textContent).not.toMatch(/APCA|key id|secret/i)
  })
})

describe('the operations page', () => {
  it('shows the summaries the server already computes', async () => {
    show(ops())
    expect(await screen.findByText(/\$1\.25/)).toBeVisible()
    expect(screen.getByText(/501,000/)).toBeVisible()
    expect(screen.getByText('12')).toBeVisible()
  })

  it('does not read zero API spend as zero cost', async () => {
    // The judge runs locally and is priced at zero by this meter. Presenting
    // that as "no cost" would be a claim about infrastructure this number
    // knows nothing about.
    show(ops())
    await screen.findByText(/\$1\.25/)
    expect(screen.getByText(/model API only/i)).toBeVisible()
  })

  it('says the archive is empty rather than showing a blank age', async () => {
    show(ops())
    expect(await screen.findByText(/nothing captured yet/i)).toBeVisible()
  })

  it('shows the archive age when there is one', async () => {
    show(ops({ capture: { latest_observed_at: '2026-09-09T09:45:00Z' } }))
    expect(await screen.findByText(/11:45 Berlin/)).toBeVisible()
  })

  it('offers no control at all on the success path', async () => {
    // Walking the buttons and asserting none of them says "retry" passes
    // trivially when there are none -- and would keep passing against a
    // button labelled "Backfill" or "Enable capture". The line is that this
    // page has no controls.
    show(ops())
    await screen.findByText(/\$1\.25/)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('rounds the backlog age rather than printing a raw float', async () => {
    // ops_summary divides seconds by 60. Unrounded this tile read
    // "43.31666666666667 min".
    show(ops({ sentiment: { ...ops().sentiment, p95_age_minutes: 43.31666666666667 } }))
    expect(await screen.findByText('43 min')).toBeVisible()
  })

  it('shows the backlog the pass can never reach', async () => {
    // Two zeroes above it would otherwise read as an empty backlog.
    show(ops({ sentiment: { ...ops().sentiment, pinned_pending: 7 } }))
    expect(await screen.findByText(/unreachable/i)).toBeVisible()
    expect(screen.getByText('7')).toBeVisible()
  })

  it('does not round sub-cent spend down to nothing', async () => {
    show(ops({ spend: { today_usd: 0.004, month_usd: 0.004, unpriced_tokens: 0 } }))
    expect((await screen.findAllByText(/under \$0\.01/)).length).toBeGreaterThan(0)
  })

  it('shows the US market-data facts and nothing of the retired collector', async () => {
    show(ops())
    expect(await screen.findByText('2026-09-08')).toBeVisible()
    expect(screen.getByText(/trade 900 · midpoint 12/)).toBeVisible()
    expect(screen.queryByText(/download budget/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/collection cycles/i)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/German|XETR|XGAT/)
  })

  it('says forbidden when the reader is not an administrator', async () => {
    show(undefined, new BoardUnavailable('forbidden'))
    expect(await screen.findByText(/not allowed/i)).toBeVisible()
    // Not "reload to sign in": reloading fixes an expired session and will
    // never fix a permission.
    expect(screen.queryByText(/sign in again/i)).not.toBeInTheDocument()
  })

  it('says signed out when the session expired', async () => {
    show(undefined, new BoardUnavailable('session'))
    expect(await screen.findByText(/sign in again/i)).toBeVisible()
  })

  it('does not retry a refusal', async () => {
    const fetchOps = vi.spyOn(api, 'fetchOps')
      .mockRejectedValue(new BoardUnavailable('forbidden'))
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <Admin />
      </QueryClientProvider>,
    )
    await screen.findByText(/not allowed/i)
    expect(fetchOps).toHaveBeenCalledTimes(1)
  })

  it('lets a reader ask again after a transport failure', async () => {
    const fetchOps = vi.spyOn(api, 'fetchOps')
      .mockRejectedValue(new BoardUnavailable('network'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Admin />
      </QueryClientProvider>,
    )
    // A transport failure IS retried twice with backoff before it is shown,
    // which is the point of separating it from a refusal -- so this waits
    // through those attempts rather than assuming the first one is final.
    const again = await screen.findByRole('button', { name: /try again/i },
                                          { timeout: 8000 })
    fetchOps.mockResolvedValue(ops())
    await userEvent.click(again)
    expect(await screen.findByText(/\$1\.25/)).toBeVisible()
  })
})

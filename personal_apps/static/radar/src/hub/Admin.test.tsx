import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import type { OpsPayload } from '../types'
import { Admin } from './Admin'

const ops = (over: Partial<OpsPayload> = {}): OpsPayload => ({
  generated_at: '2026-09-09T10:00:00Z',
  spend: { today_usd: 0, month_usd: 1.25, unpriced_tokens: 501_000 },
  sentiment: {
    pending: 12, gated_pending: 4, p95_age_minutes: 31,
    review: { demanded: 5, attempted: 5, served: 4, capped: 1, over_ceiling: 0 },
  },
  market_data: {
    cycles: {
      'XETR:pretrade': {
        status: 'accepted', scheduled_at: '2026-09-09T09:55:00Z',
        files_seen: 3, files_accepted: 3, selected: 120, rejected: 0,
        parse_ms: 88, error_code: null,
      },
    },
    mapping_generations: { active: 1 },
    quote_basis_24h: { trade: 900, midpoint: 12 },
    grouped_closes: {
      latest_accepted_date: '2026-09-08', retryable_gaps: [],
      counts: { provider_rows: 9000, written: 8800 },
      error_code: null, http_status: null, backoff_until: null,
    },
    post_close_claims: {},
    de_download_budget_24h: { spent: 4, limit: 40, remaining: 36 },
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

  it('offers no control that could start, stop or retry anything', async () => {
    show(ops())
    await screen.findByText(/\$1\.25/)
    for (const button of screen.queryAllByRole('button')) {
      expect(button.textContent ?? '').not.toMatch(/retry|restart|retrain|run|stop|clear/i)
    }
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

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import type { ActivityDay, ActivityPayload } from '../types'
import { Activity } from './Activity'

const day = (over: Partial<ActivityDay> = {}): ActivityDay => ({
  date: '2026-09-08',
  posts_seen: 1200, posts_new: 300, mentions: 90, buckets_written: 40,
  completed_runs: 96, counted_runs: 96, incomplete_runs: 0, error_runs: 0,
  completeness: 'partial',
  ...over,
})

const activity = (days: ActivityDay[],
                  over: Partial<ActivityPayload> = {}): ActivityPayload => ({
  generated_at: '2026-09-09T10:00:00Z',
  from: '2026-09-08T22:00:00Z',
  to: '2026-09-09T22:00:00Z',
  recording_started_at: '2026-09-01T06:00:00Z',
  days,
  ...over,
})

function show(payload: ActivityPayload) {
  vi.spyOn(api, 'fetchActivity').mockResolvedValue(payload)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Activity />
    </QueryClientProvider>,
  )
}

afterEach(() => { vi.restoreAllMocks() })

describe('recorded activity', () => {
  it('renders a gap where nothing was recorded', async () => {
    show(activity([day({
      posts_seen: null, posts_new: null, mentions: null, buckets_written: null,
      completed_runs: 0, counted_runs: 0, completeness: 'unknown',
    })]))
    const row = await screen.findByTestId('rh-day-2026-09-08')
    // Not zero. A day nobody recorded and a day the sources were silent are
    // different facts, and this table is the one place that must not blur them.
    expect(within(row).queryByText('0')).not.toBeInTheDocument()
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0)
    expect(within(row).getByText(/not recorded/i)).toBeVisible()
  })

  it('renders a recorded zero as zero', async () => {
    show(activity([day({
      posts_seen: 0, posts_new: 0, mentions: 0, buckets_written: 0,
      completed_runs: 4, counted_runs: 4,
    })]))
    const row = await screen.findByTestId('rh-day-2026-09-08')
    expect(within(row).getAllByText('0').length).toBeGreaterThan(0)
    expect(within(row).queryByText(/not recorded/i)).not.toBeInTheDocument()
  })

  it('labels partial coverage as partial and never as complete', async () => {
    show(activity([day()]))
    expect(await screen.findByText(/partial/i)).toBeVisible()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/\b100%\b/)
    expect(text).not.toMatch(/\bcomplete\b/i)
  })

  it('counts crashed and failed runs separately from completed ones', async () => {
    show(activity([day({ completed_runs: 90, counted_runs: 90,
                         incomplete_runs: 4, error_runs: 2 })]))
    const row = await screen.findByTestId('rh-day-2026-09-08')
    expect(within(row).getByText(/4 unfinished/i)).toBeVisible()
    expect(within(row).getByText(/2 failed/i)).toBeVisible()
  })

  it('says when the counters were drawn from fewer runs than completed', async () => {
    // Off-version summaries are skipped from the sums. Without this line a
    // per-run rate read off the page is silently wrong.
    show(activity([day({ completed_runs: 96, counted_runs: 50 })]))
    const row = await screen.findByTestId('rh-day-2026-09-08')
    expect(within(row).getByText(/50 of 96/i)).toBeVisible()
  })

  it('explains that days before recording began are not missing data', async () => {
    show(activity([day()], { recording_started_at: '2026-09-01T06:00:00Z' }))
    expect(await screen.findByText(/recording began/i)).toBeVisible()
  })

  it('says so when nothing has ever been recorded', async () => {
    show(activity([day()], { recording_started_at: null }))
    expect(await screen.findByText(/no run has been recorded/i)).toBeVisible()
  })

  it('offers only the windows the server accepts', async () => {
    show(activity([day()]))
    await screen.findByTestId('rh-day-2026-09-08')
    const group = screen.getByRole('group', { name: /window/i })
    const labels = within(group).getAllByRole('button').map((b) => b.textContent)
    expect(labels).toEqual(['1 day', '7 days', '30 days'])
  })

  it('gives the table a text equivalent for every figure it draws', async () => {
    show(activity([day()]))
    const table = await screen.findByRole('table')
    // Bars are decoration over a table that already reads. The figures are in
    // cells, not only in a chart.
    expect(within(table).getByText('1,200')).toBeVisible()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HistoryPage } from './HistoryPage'
import type { HistoryEntry, HistoryPayload } from './types'

const entry = (over: Partial<HistoryEntry> = {}): HistoryEntry => ({
  session_id: 7, name: 'Push Day', started_at: '2026-09-23T16:00:00',
  finished_at: '2026-09-23T16:52:00', is_deload: false, auto_finished: false,
  volume: 4200, record_count: 0, exercises: ['Bankdrücken', 'Dips'],
  search_date: '23.09.2026 september 2026', gap_days: null, ...over,
})

const payload = (entries: HistoryEntry[]): HistoryPayload => ({
  months: [{ label: 'September 2026', slug: '2026-09', entries, volume: 4200, records: 0 }],
  total: entries.length, gap_threshold: 14,
  weekday_short: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
})

describe('HistoryPage', () => {
  it('says which workouts the app ended itself (D5)', () => {
    // Its end is its last set's time, three hours before anyone closed it.
    render(<HistoryPage payload={payload([entry({ auto_finished: true })])} />)
    expect(screen.getByText(/52 min · automatisch beendet$/)).toBeInTheDocument()
  })

  it('says nothing more about a workout the lifter finished', () => {
    render(<HistoryPage payload={payload([entry()])} />)
    expect(screen.getByText(/52 min$/)).toBeInTheDocument()
    expect(screen.queryByText(/automatisch beendet/)).not.toBeInTheDocument()
  })
})

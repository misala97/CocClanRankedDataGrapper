import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { HistoryPage } from './HistoryPage'
import type { HistoryEntry, HistoryPayload } from './types'
import { useHistoryUi } from './store'

const entry = (over: Partial<HistoryEntry> = {}): HistoryEntry => ({
  session_id: 7, name: 'Push Day', started_at: '2026-09-23T16:00:00',
  finished_at: '2026-09-23T16:52:00', is_deload: false, auto_finished: false,
  volume: 4200, record_count: 0, exercises: ['Bankdrücken', 'Dips'],
  search: 'push day\n23.09.2026 september 2026', gap_days: null, ...over,
})

const payload = (entries: HistoryEntry[]): HistoryPayload => ({
  months: [{ label: 'September 2026', slug: '2026-09', entries, volume: 4200, records: 0 }],
  total: entries.length, gap_threshold: 14,
  weekday_short: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
  exercise_search: {
    Bankdrücken: 'bankdrucken langhantel\nbench press\nflachbankdrucken', Dips: 'dips maschine',
  },
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

describe('the Verlauf search (G-145)', () => {
  beforeEach(() => { useHistoryUi.setState(useHistoryUi.getInitialState(), true) })

  const legs = entry({
    session_id: 8, name: 'Leg Day', exercises: ['Kniebeugen'],
    search: 'leg day\n20.09.2026 september 2026',
  })
  const both = () => ({
    ...payload([entry(), legs]),
    exercise_search: {
      ...payload([]).exercise_search, Kniebeugen: 'kniebeugen langhantel\nsquat\nback squat',
    },
  })
  const names = () => [...document.querySelectorAll('.row__name')].map((n) => n.textContent)

  it('finds a workout by what its exercises are also called, and by a typo', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'bench')
    expect(names()).toEqual(['Push Day'])
    // The exercise it was found by comes first, marked.
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Bankdrücken')
    await userEvent.clear(field)
    await userEvent.type(field, 'Kniebeigen')
    expect(names()).toEqual(['Leg Day'])
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Kniebeugen')
  })

  it('finds by the date words and the name, umlauts folded', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, '20.09')
    expect(names()).toEqual(['Leg Day'])
    await userEvent.clear(field)
    await userEvent.type(field, 'PUSH')
    expect(names()).toEqual(['Push Day'])
    expect(document.querySelector('mark.row__hit')).toBeNull()
    await userEvent.clear(field)
    await userEvent.type(field, 'BANKDRÜCKEN')
    expect(names()).toEqual(['Push Day'])
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Bankdrücken')
  })

  it('says when what it shows is only a typo away', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'Kniebeigen')
    expect(screen.getByText('Kein genauer Treffer für „Kniebeigen“ – ähnlich geschrieben:'))
      .toBeInTheDocument()
    await userEvent.clear(field)
    await userEvent.type(field, 'Kniebeugen')
    expect(names()).toEqual(['Leg Day'])
    expect(screen.queryByText(/Kein genauer Treffer/)).toBeNull()
  })

  it('takes a whole name before its words: "Push 2" is not every Push', async () => {
    const two = entry({
      session_id: 9, name: 'Push 2', search: 'push 2\n31.07.2026 juli 2026',
    })
    const push = entry({ session_id: 10, name: 'Push', search: 'push\n23.09.2026 september 2026' })
    render(<HistoryPage payload={payload([two, push])} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'push 2')
    expect(names()).toEqual(['Push 2'])
    await userEvent.clear(field)
    await userEvent.type(field, 'push 23.09')
    expect(names()).toEqual(['Push'])
  })

  it('marks the exercise that holds the whole query, not its words spread over two', async () => {
    const flat = entry({ session_id: 11, name: 'A', exercises: ['Bankdrücken (Langhantel)', 'Seitheben (Kurzhantel)'] })
    const dumbbell = entry({ session_id: 12, name: 'B', exercises: ['Bankdrücken (Kurzhantel)', 'Dips'] })
    render(<HistoryPage payload={{
      ...payload([flat, dumbbell]),
      exercise_search: {
        'Bankdrücken (Langhantel)': 'bankdrucken langhantel\nbench press',
        'Seitheben (Kurzhantel)': 'seitheben kurzhantel\nlateral raise',
        'Bankdrücken (Kurzhantel)': 'bankdrucken kurzhantel\ndumbbell bench press',
        Dips: 'dips maschine',
      },
    }} />)
    await userEvent.type(screen.getByRole('searchbox'), 'Bankdrücken Kurzhantel')
    expect(names()).toEqual(['B'])
    expect([...document.querySelectorAll('mark.row__hit')].map((m) => m.textContent))
      .toEqual(['Bankdrücken (Kurzhantel)'])
  })

  it('reads a query that folds to nothing as none', async () => {
    render(<HistoryPage payload={both()} />)
    await userEvent.type(screen.getByRole('searchbox'), '-')
    expect(names()).toEqual(['Push Day', 'Leg Day'])
    expect(document.querySelector('mark.row__hit')).toBeNull()
  })
})

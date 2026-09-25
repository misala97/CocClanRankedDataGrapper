import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Fortschritt, SHOWN, Spark } from './Progress'
import type { DeloadSuggestion, Progress, ProgressLift, Stall } from './types'

// dayDate drops the year inside the current one: pinned, so the dates below
// read the same whatever year the suite runs in.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-08-10T18:00:00Z'))
})
afterEach(() => {
  vi.useRealTimers()
})

const lift = (over: Partial<ProgressLift> = {}): ProgressLift => ({
  exercise_id: 12, name: 'Kniebeuge', per_month: 2.5, workouts: 6,
  points: [
    { started_at: '2026-07-01T10:00:00', e1rm: 100 },
    { started_at: '2026-07-29T10:00:00', e1rm: 104 },
  ],
  best: { e1rm: 104, started_at: '2026-07-29T10:00:00', is_record: true },
  ...over,
})

const stall = (over: Partial<Stall> = {}): Stall => ({
  exercise_id: 10, name: 'Bankdrücken', position: 1, stuck_at: 60.0,
  since: '2026-06-03T10:00:00', sessions_since_pr: 4, last_record_at: '2026-06-03T10:00:00',
  ...over,
})

const mount = (over: Partial<Progress> = {}, stalls: Stall[] = [],
  deload: DeloadSuggestion | null = null) =>
  render(<Fortschritt progress={{ up: [], with_trend: 0, min_workouts: 4, min_days: 14, ...over }}
    stalls={stalls} deload={deload} />)

const lede = () => document.querySelector('.sec__lede')

describe('the lede says the answer first (D11)', () => {
  it('counts what goes up and what stands still', () => {
    mount({ up: [lift(), lift({ exercise_id: 13, name: 'Kreuzheben' })], with_trend: 3 }, [stall()])
    expect(lede()).toHaveTextContent(
      '2 Übungen legen zu, 1 steht still: der Trend ihrer letzten Workouts, '
      + 'gemessen am geschätzten Maximum (1RM).')
  })

  it('speaks of one in the singular, and of no stall as none', () => {
    mount({ up: [lift()], with_trend: 1 })
    expect(lede()).toHaveTextContent(/^1 Übung legt zu, keine steht still: der Trend/)
  })

  it('says nothing goes up while some lift has a pace', () => {
    mount({ with_trend: 2 }, [stall(), stall({ exercise_id: 11, name: 'Dips' })])
    expect(lede()).toHaveTextContent(/^Keine Übung legt gerade zu, 2 stehen still: der Trend/)
  })

  it('says what a pace needs before any lift has one', () => {
    mount()
    expect(lede()).toHaveTextContent(
      'Einen Trend zeigt eine Übung ab 4 Workouts über zwei Wochen, '
      + 'gemessen am geschätzten Maximum (1RM).')
  })

  it('still counts the stalls then', () => {
    mount({}, [stall()])
    expect(lede()).toHaveTextContent(/^1 Übung steht still\. Einen Trend zeigt eine Übung ab 4 Workouts/)
  })
})

describe('Legen zu', () => {
  it('ranks each lift by its pace, with its best beside it', () => {
    mount({ up: [lift()], with_trend: 1 })
    expect(screen.getByRole('heading', { name: 'Legen zu 1' })).toBeInTheDocument()
    const row = screen.getByRole('link', {
      name: 'Kniebeuge: Trend der letzten 6 Workouts +2,5 kg im Monat, Rekord 104,0 kg am 29.07.',
    })
    expect(row).toHaveAttribute('href', '/gym/exercises/12')
    expect(row.querySelector('.row__meta')).toHaveTextContent('Rekord 104,0 kg am 29.07.')
    expect(row.querySelector('.prog__trend')).toHaveTextContent('+2,5kgim Monat')
  })

  it('calls a best that beat nothing a Bestwert (D3)', () => {
    mount({ up: [lift({ best: { e1rm: 104, started_at: '2026-07-01T10:00:00', is_record: false } })] })
    expect(screen.getByRole('link').querySelector('.row__meta'))
      .toHaveTextContent('Bestwert 104,0 kg am 01.07.')
  })

  it('is absent while nothing goes up', () => {
    mount({ with_trend: 2 }, [stall()])
    expect(screen.queryByRole('heading', { name: /^Legen zu/ })).not.toBeInTheDocument()
  })
})

describe('Steht still', () => {
  it('says since when, and what the newest attempt lifted', () => {
    mount({}, [stall()])
    expect(screen.getByRole('heading', { name: 'Steht still 1' })).toBeInTheDocument()
    const row = screen.getByRole('link', {
      name: 'Bankdrücken: seit 4 Workouts ohne Rekord, letzter am 03.06., zuletzt 60,0 kg',
    })
    expect(row.querySelector('.row__meta')).toHaveTextContent('Seit 4 Workouts ohne Rekord · letzter am 03.06.')
    expect(row.querySelector('.stall-ink')).toHaveTextContent(/^Seit 4 Workouts ohne Rekord$/)
    expect(row.querySelector('.row__trail')).toHaveTextContent('60,0kgzuletzt')
  })

  it('counts from the first judged workout of a lift that never set a record', () => {
    // A set at 0 kg or of 13+ reps judges nothing (G-038): a lift done at
    // bodyweight since before `since` did have earlier workouts.
    mount({}, [stall({ last_record_at: null, since: '2026-05-20T10:00:00' })])
    expect(screen.getByRole('link').querySelector('.row__meta'))
      .toHaveTextContent('Seit 4 Workouts ohne Rekord · erstes gewertetes Workout am 20.05.')
    expect(screen.getByRole('link')).toHaveAccessibleName(
      'Bankdrücken: seit 4 Workouts ohne Rekord, erstes gewertetes Workout am 20.05., zuletzt 60,0 kg')
  })

  it('scopes the deload note to what is actively trained', () => {
    const many = Array.from({ length: 4 }, (_, i) => stall({ exercise_id: 100 + i, name: `Lift ${i}` }))
    mount({}, many, { count: 3, stalls: many.slice(0, 3) })
    expect(document.querySelector('.stall-note'))
      .toHaveTextContent('3 davon aktiv trainiert — ein Deload könnte fällig sein.')
  })

  it('is absent when nothing stalls', () => {
    mount({ up: [lift()], with_trend: 1 })
    expect(screen.queryByRole('heading', { name: /^Steht still/ })).not.toBeInTheDocument()
    expect(document.querySelector('.stall-note')).toBeNull()
  })
})

describe('a long list', () => {
  const many = Array.from({ length: SHOWN + 2 }, (_, i) =>
    stall({ exercise_id: 100 + i, name: `Lift ${i}` }))

  it('shows five and brings the rest in place, focus on the first it brought', async () => {
    const user = userEvent.setup()
    mount({}, many)
    expect(screen.getAllByRole('link')).toHaveLength(SHOWN)
    await user.click(screen.getByRole('button', { name: `Alle ${SHOWN + 2} zeigen` }))
    const rows = screen.getAllByRole('link')
    expect(rows).toHaveLength(SHOWN + 2)
    expect(screen.queryByRole('button', { name: /^Alle/ })).not.toBeInTheDocument()
    await waitFor(() => expect(rows[SHOWN]).toHaveFocus())
    expect(rows[SHOWN]).toHaveAccessibleName(/^Lift 5:/)
  })

  it('folds each half on its own', () => {
    mount({ up: Array.from({ length: SHOWN + 1 }, (_, i) => lift({ exercise_id: 200 + i, name: `Up ${i}` })) },
      [stall()])
    expect(screen.getAllByRole('button', { name: /^Alle/ }).map((b) => b.textContent))
      .toEqual([`Alle ${SHOWN + 1} zeigen`])
    // Five of the six going up, and the one standing still below them.
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href')))
      .toEqual([200, 201, 202, 203, 204, 10].map((id) => `/gym/exercises/${id}`))
  })
})

describe('the spark', () => {
  it('spaces the workouts by date and spans a tenth of the level at least', () => {
    // 100 to 104 over four weeks: 4 kg is under a tenth of 104, so the
    // height spans 10,4 kg -- a small gain draws flat, not steep.
    const { container } = render(<Spark points={[
      { started_at: '2026-07-01T10:00:00', e1rm: 100 },
      { started_at: '2026-07-08T10:00:00', e1rm: 101 },
      { started_at: '2026-07-15T10:00:00', e1rm: 102.5 },
      { started_at: '2026-07-29T10:00:00', e1rm: 104 },
    ]} />)
    expect(container.querySelector('polyline')).toHaveAttribute('points', '3,16.8 15.5,14.9 28,12 53,9.2')
    const dot = container.querySelector('circle')!
    expect([dot.getAttribute('cx'), dot.getAttribute('cy')]).toEqual(['53', '9.2'])
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})

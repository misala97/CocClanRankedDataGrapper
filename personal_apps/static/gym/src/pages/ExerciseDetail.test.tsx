import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ExerciseDetailPage } from './ExerciseDetail'
import type { ExerciseDetailPayload, ExerciseMeta, SessionRow } from '../types'

function payload(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return {
    exercise: {
      id: 1, name: 'Bankdrücken', muscle_group: 'Brust', is_unilateral: false,
      default_rest_seconds: 90, weight_increment: 2.5, equipment: 'barbell',
      bar_weight: 20, stack_kg: null, secondary_muscle_groups: null,
      list_defaults: {
        default_rest_seconds: 90, weight_increment: 2.5, bar_weight: 20, stack_kg: null,
      },
      own: [], rest_for_all: null,
    },
    table: [], series: [], available_positions: [], selected_position: null,
    selected_position_is_default: false, selected_position_reason: null,
    last_overall: null, pr_weight: null, pr_e1rm: null, last_progression: null,
    state: null, sessions_since_pr: null, chart: null,
    chip_class: null, chip_label: null,
    equipment_labels: { barbell: 'Langhantel', stack: 'Stack', dumbbell: 'Kurzhantel' },
    ...over,
  }
}

/** A stack the lifter set up: their own step, rest and stops over the list's. */
const stackExercise: ExerciseMeta = {
  ...payload().exercise, name: 'Latzug (Kabel)', muscle_group: 'Rücken', equipment: 'stack',
  weight_increment: 5, default_rest_seconds: 120, bar_weight: null, stack_kg: [5, 13, 21],
  list_defaults: {
    default_rest_seconds: 90, weight_increment: 2.5, bar_weight: null, stack_kg: null,
  },
  own: ['default_rest_seconds', 'stack_kg', 'weight_increment'],
}

function row(over: Partial<SessionRow> = {}): SessionRow {
  return {
    session_id: 7, started_at: '2026-08-01T18:30:00', position: 2,
    is_deload: false, sets_display: '3 × 8', best_weight: 80,
    volume: 1920, e1rm: 100, ...over,
  }
}

describe('ExerciseDetailPage', () => {
  it('names the exercise as the h1', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bankdrücken')
  })

  it('shows the empty state when nothing is logged', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.getByText(/Noch keine Sätze protokolliert/)).toBeInTheDocument()
    expect(screen.queryByText('Einheiten')).not.toBeInTheDocument()
  })

  it('formats volume with a German thousands separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.getByText('1.920')).toBeInTheDocument()
  })

  it('formats weights with a comma decimal separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.getByText('e1RM 100,0')).toBeInTheDocument()
  })

  it('scopes the session count to the selected position', () => {
    // Queried through the chart section rather than by text: "Pos. 2 ·" also
    // appears in every row's meta line, and the point of this assertion is
    // that the CHART's count says what it is counting.
    const { container } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], selected_position: 2, available_positions: [1, 2],
      })} />)
    const head = container.querySelector('.sec--chart .sec__head')!
    expect(head.textContent).toContain('Pos. 2 · 1 Einheit')
  })

  it('pluralises Einheit correctly', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row(), row({ session_id: 8 })] })} />)
    expect(screen.getByText(/2 Einheiten/)).toBeInTheDocument()
  })

  it('offers position pills only when more than one slot exists', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [2] })} />)
    expect(screen.queryByText('Alle')).not.toBeInTheDocument()

    rerender(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })} />)
    expect(screen.getByText('Alle')).toBeInTheDocument()
    expect(screen.getByText('Position 1')).toBeInTheDocument()
  })

  it('pills are real links, so deep links and the back button keep working', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })} />)
    expect(screen.getByText('Alle')).toHaveAttribute('href', '/gym/exercises/1?position=all')
    expect(screen.getByText('Position 1')).toHaveAttribute('href', '/gym/exercises/1?position=1')
  })

  it('explains a slot the page chose rather than one the reader picked', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: true, selected_position_reason: 'strongest',
      })} />)
    expect(screen.getByText(/die stärkste mit mindestens zwei Einheiten/)).toBeInTheDocument()

    // Explicitly chosen -- no explanation, because the reader made the choice.
    rerender(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: false, selected_position_reason: null,
      })} />)
    expect(screen.queryByText(/die stärkste/)).not.toBeInTheDocument()
  })

  it('marks the record row on session_id, not on the date', () => {
    const sameDay = [
      row({ session_id: 7, e1rm: 100 }),
      row({ session_id: 8, e1rm: 90, volume: 2200 }),
    ]
    render(<ExerciseDetailPage
      payload={payload({
        table: sameDay,
        pr_e1rm: {
          e1rm: 100, weight: 80, reps: 5, session_id: 7,
          started_at: '2026-08-01T18:30:00', position: 2,
        },
      })} />)
    // exactly one row is gold, even though both share a date
    expect(screen.getAllByText('Rekord')).toHaveLength(1)
  })

  it('labels deload rows', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row({ is_deload: true })] })} />)
    expect(screen.getByText('Deload')).toBeInTheDocument()
  })

  it('offers no way to delete the exercise: the list is everyone\'s', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.queryByText(/löschen/i)).not.toBeInTheDocument()
  })

  it('opens the settings from the maintenance button', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload()} />)

    const dialog = document.querySelector('dialog')!
    expect(dialog.open).toBe(false)
    await user.click(screen.getByText(/Pause und Schritt einstellen/))
    expect(dialog.open).toBe(true)
    expect(within(dialog).getByRole('heading', { name: 'Deine Einstellungen' })).toBeInTheDocument()
  })

  it('opens on the settings when "Deine Pause" links an exception here', () => {
    // The hash is dropped once used: a reload lands on the page itself.
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload()} />)
    expect(document.querySelector('dialog')!.open).toBe(true)
    expect(window.location.hash).toBe('')
  })
})

describe('Deine Einstellungen', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  /** The sheet open on `exercise`, with the server answering `answer`. */
  function sheet(exercise: ExerciseMeta, answer?: (fields: FormData) => ExerciseMeta | Error) {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const fields = init.body as FormData
      const reply = answer?.(fields) ?? exercise
      if (reply instanceof Error) throw reply
      return { ok: true, status: 200, json: async () => reply } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload({ exercise })} />)
    return { fetchMock, dialog: within(document.querySelector('dialog')!) }
  }

  const setting = (name: string) =>
    within(screen.getByRole('heading', { name }).closest('section')!)

  it('says where each value comes from, and marks what it falls back to', () => {
    sheet(stackExercise)
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Von dir')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['1:00', '1:30Liste', '2:00', '2:30', '3:00', 'Andere'])
    expect(rest.getByRole('button', { name: '2:00' })).toHaveAttribute('aria-pressed', 'true')

    const step = setting('Schritt bei + und − (kg)')
    expect(step.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['2,5Liste', '5', '7', '8', '10', 'Andere'])
    expect(step.getByRole('button', { name: '5' })).toHaveAttribute('aria-pressed', 'true')

    const stops = setting('Stufen am Gerät')
    expect(stops.getByText('5, 13, 21')).toBeInTheDocument()
    expect(stops.getByRole('button', { name: 'Wieder gleichmäßig' })).toBeInTheDocument()
  })

  it('asks for a bar only where the list knows one, and stops only on a stack', () => {
    sheet(payload().exercise)
    const bar = setting('Stangengewicht (kg)')
    expect(bar.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['Ohne', '10', '15', '20Liste', '25', 'Andere'])
    expect(screen.queryByRole('heading', { name: 'Stufen am Gerät' })).toBeNull()
  })

  it('never asks a stack for a bar', () => {
    sheet(stackExercise)
    expect(screen.queryByRole('heading', { name: 'Stangengewicht (kg)' })).toBeNull()
  })

  it('saves a tap at once, one field, and shows it as the lifter\'s', async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(payload().exercise, (fields) => ({
      ...payload().exercise, default_rest_seconds: Number(fields.get('default_rest_seconds')),
      own: ['default_rest_seconds'],
    }))
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Wie die Liste')).toBeInTheDocument()

    await user.click(rest.getByRole('button', { name: '3:00' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/gym/exercises/1/update')
    expect([...(init.body as FormData).entries()]).toEqual([['default_rest_seconds', '180']])
    expect(rest.getByRole('button', { name: '3:00' })).toHaveAttribute('aria-pressed', 'true')
    expect(await rest.findByText('Von dir')).toBeInTheDocument()
  })

  it("goes back to the list's value in one tap", async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(stackExercise, () => ({
      ...stackExercise, default_rest_seconds: 90,
      own: stackExercise.own.filter((f) => f !== 'default_rest_seconds'),
    }))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '1:30 Liste' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['default_rest_seconds', '90']])
    expect(rest.getByText('Wie die Liste')).toBeInTheDocument()
  })

  it('puts the value back and says why when a save fails', async () => {
    const user = userEvent.setup()
    sheet(payload().exercise, () => new TypeError('Failed to fetch'))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '3:00' }))
    expect(await screen.findByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.')
    expect(rest.getByRole('button', { name: '1:30 Liste' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('falls back to the rest for all, and calls an own rest an exception', () => {
    sheet({ ...payload().exercise, default_rest_seconds: 180, rest_for_all: 150,
      own: ['default_rest_seconds'] })
    expect(screen.getByText('Nur für dich. Ohne Ausnahme gilt deine Pause, 2:30.'))
      .toBeInTheDocument()
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Ausnahme')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['2:00', '2:30deine', '3:00', '3:30', '4:00', 'Andere'])
  })

  it('takes a machine\'s own stops typed once, and only a list of them', async () => {
    const user = userEvent.setup()
    const even = { ...stackExercise, stack_kg: null,
      own: stackExercise.own.filter((f) => f !== 'stack_kg') }
    const { fetchMock } = sheet(even)
    const stops = setting('Stufen am Gerät')
    expect(stops.getByText('Gleichmäßig, im Schritt von oben: 5, 10, 15 …')).toBeInTheDocument()

    await user.click(stops.getByRole('button', { name: 'Das Gerät hat andere Stufen' }))
    const field = stops.getByLabelText(/Jede Stufe in kg/)
    await user.type(field, '12')
    expect(stops.getByRole('button', { name: 'Übernehmen' })).toBeDisabled()
    await user.type(field, ', 5; 19')
    await user.click(stops.getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['stack_kg', '5, 12, 19']])
  })
})

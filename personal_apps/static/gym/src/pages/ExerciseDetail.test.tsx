import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ExerciseDetailPage } from './ExerciseDetail'
import type { ExerciseDetailPayload, SessionRow } from '../types'

function payload(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return {
    exercise: {
      id: 1, name: 'Bankdrücken', muscle_group: 'Brust', is_unilateral: false,
      default_rest_seconds: 90, weight_increment: 2.5, equipment: 'barbell',
      bar_weight: 20, stack_kg: null, secondary_muscle_groups: null,
      list_defaults: {
        default_rest_seconds: 90, weight_increment: 2.5, bar_weight: 20, stack_kg: null,
      },
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
const stackExercise = {
  ...payload().exercise, name: 'Latzug (Kabel)', muscle_group: 'Rücken', equipment: 'stack',
  weight_increment: 5, default_rest_seconds: 120, bar_weight: null, stack_kg: [5, 13, 21],
  list_defaults: {
    default_rest_seconds: 90, weight_increment: 2.5, bar_weight: null, stack_kg: null,
  },
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
    await user.click(screen.getByText(/Schrittweite und Pause einstellen/))
    expect(dialog.open).toBe(true)
  })

  it('edits only the lifter\'s own four settings, the list\'s values as placeholders', () => {
    render(<ExerciseDetailPage payload={payload({ exercise: stackExercise })} />)

    const form = document.querySelector('dialog form')!
    const names = [...form.querySelectorAll('input:not([type=hidden]), select, textarea')]
      .map((field) => field.getAttribute('name'))
    expect(names.sort()).toEqual(
      ['bar_weight', 'default_rest_seconds', 'stack_kg', 'weight_increment'])

    // Prefilled with what is in use for this lifter; a blank field is the
    // list's value, which is what the placeholder shows.
    const step = screen.getByLabelText('Schrittweite (kg)')
    expect(step).toHaveValue(5)
    expect(step).toHaveAttribute('placeholder', '2,5')
    const rest = screen.getByLabelText('Pause (Sek.)')
    expect(rest).toHaveValue(120)
    expect(rest).toHaveAttribute('placeholder', '90')
    expect(screen.getByLabelText(/Stack-Stufen/)).toHaveValue('5, 13, 21')
  })

  it('shows what the list decides as text, not as fields', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    const dialog = document.querySelector('dialog')!
    expect(dialog).toHaveTextContent('Bankdrücken')
    expect(dialog).toHaveTextContent('Brust · Langhantel')
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Muskelgruppe')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Art')).not.toBeInTheDocument()
  })

  it('asks for stack stops only on a stack', () => {
    const { unmount } = render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.queryByLabelText(/Stack-Stufen/)).not.toBeInTheDocument()
    unmount()

    render(<ExerciseDetailPage payload={payload({ exercise: stackExercise })} />)
    expect(screen.getByLabelText(/Stack-Stufen/)).toBeInTheDocument()
  })

  it('keeps the settings form a native POST to the update route', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    const form = screen.getByLabelText('Schrittweite (kg)').closest('form')!
    expect(form).toHaveAttribute('method', 'post')
    expect(form).toHaveAttribute('action', '/gym/exercises/1/update')
  })
})

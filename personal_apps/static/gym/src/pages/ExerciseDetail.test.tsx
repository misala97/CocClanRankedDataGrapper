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
    },
    table: [], series: [], available_positions: [], selected_position: null,
    selected_position_is_default: false, selected_position_reason: null,
    last_overall: null, pr_weight: null, pr_e1rm: null, last_progression: null,
    state: null, sessions_since_pr: null, chart: null,
    chip_class: null, chip_label: null, can_delete: true,
    muscle_groups: ['Brust', 'Trizeps'],
    equipment_labels: { barbell: 'Langhantel', stack: 'Stack', dumbbell: 'Kurzhantel' },
    ...over,
  }
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
    render(<ExerciseDetailPage payload={payload()} nameTaken={false} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bankdrücken')
  })

  it('shows the empty state when nothing is logged', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken={false} />)
    expect(screen.getByText(/Noch keine Sätze protokolliert/)).toBeInTheDocument()
    expect(screen.queryByText('Einheiten')).not.toBeInTheDocument()
  })

  it('formats volume with a German thousands separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} nameTaken={false} />)
    expect(screen.getByText('1.920')).toBeInTheDocument()
  })

  it('formats weights with a comma decimal separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} nameTaken={false} />)
    expect(screen.getByText('e1RM 100,0')).toBeInTheDocument()
  })

  it('scopes the session count to the selected position', () => {
    // Queried through the chart section rather than by text: "Pos. 2 ·" also
    // appears in every row's meta line, and the point of this assertion is
    // that the CHART's count says what it is counting.
    const { container } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], selected_position: 2, available_positions: [1, 2],
      })}
      nameTaken={false} />)
    const head = container.querySelector('.sec--chart .sec__head')!
    expect(head.textContent).toContain('Pos. 2 · 1 Einheit')
  })

  it('pluralises Einheit correctly', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row(), row({ session_id: 8 })] })}
      nameTaken={false} />)
    expect(screen.getByText(/2 Einheiten/)).toBeInTheDocument()
  })

  it('offers position pills only when more than one slot exists', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [2] })}
      nameTaken={false} />)
    expect(screen.queryByText('Alle')).not.toBeInTheDocument()

    rerender(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })}
      nameTaken={false} />)
    expect(screen.getByText('Alle')).toBeInTheDocument()
    expect(screen.getByText('Position 1')).toBeInTheDocument()
  })

  it('pills are real links, so deep links and the back button keep working', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })}
      nameTaken={false} />)
    expect(screen.getByText('Alle')).toHaveAttribute('href', '/gym/exercises/1?position=all')
    expect(screen.getByText('Position 1')).toHaveAttribute('href', '/gym/exercises/1?position=1')
  })

  it('explains a slot the page chose rather than one the reader picked', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: true, selected_position_reason: 'strongest',
      })} nameTaken={false} />)
    expect(screen.getByText(/die stärkste mit mindestens zwei Einheiten/)).toBeInTheDocument()

    // Explicitly chosen -- no explanation, because the reader made the choice.
    rerender(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: false, selected_position_reason: null,
      })} nameTaken={false} />)
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
      })} nameTaken={false} />)
    // exactly one row is gold, even though both share a date
    expect(screen.getAllByText('Rekord')).toHaveLength(1)
  })

  it('labels deload rows', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row({ is_deload: true })] })} nameTaken={false} />)
    expect(screen.getByText('Deload')).toBeInTheDocument()
  })

  it('hides the delete form when the exercise is in use', () => {
    render(<ExerciseDetailPage payload={payload({ can_delete: false })} nameTaken={false} />)
    expect(screen.queryByText('Übung löschen')).not.toBeInTheDocument()
  })

  it('announces a rejected rename and reopens the editor', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken />)
    expect(screen.getByText('Name nicht geändert')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('opens the edit sheet from the maintenance button', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload()} nameTaken={false} />)

    const dialog = document.querySelector('dialog')!
    expect(dialog.open).toBe(false)
    await user.click(screen.getByText(/Name, Muskelgruppe, Standard-Pause bearbeiten/))
    expect(dialog.open).toBe(true)
  })

  it('shows the stack-steps field only for stack equipment', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload()} nameTaken />)

    const stackField = screen.getByLabelText(/Stack-Stufen/).closest('.field')!
    expect(stackField).toHaveAttribute('hidden')

    await user.selectOptions(screen.getByLabelText('Art'), 'stack')
    expect(stackField).not.toHaveAttribute('hidden')
  })

  it('keeps the edit form a native POST to the update route', () => {
    render(<ExerciseDetailPage payload={payload()} nameTaken />)
    const form = screen.getByLabelText('Name').closest('form')!
    expect(form).toHaveAttribute('method', 'post')
    expect(form).toHaveAttribute('action', '/gym/exercises/1/update')
  })
})

import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useUndo } from '../../undo'
import { ExerciseSheet } from './ExerciseSheet'
import { useSheets } from '../stores'
import { payload } from '../types.test-d'
import type { LiveExercise } from '../types'

beforeEach(() => {
  useUndo.setState({ pending: null, timer: null })
  useSheets.setState(useSheets.getInitialState(), true)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const exercise = payload.visible_exercises[0]!
const catalogue = [
  { id: exercise.exercise_id, name: exercise.name, muscle_group: exercise.muscle_group },
  { id: 900, name: 'Andere Brustübung', muscle_group: exercise.muscle_group },
  { id: 901, name: 'Ganz andere Gruppe', muscle_group: 'Waden' },
]

const actions = () => ({
  onRestChange: vi.fn(), onIncrementChange: vi.fn(), onMetaSave: vi.fn(),
  onSetUpdate: vi.fn(), onSetDelete: vi.fn(), onAddSet: vi.fn(),
  onToggleSkip: vi.fn(), onReplace: vi.fn(), onReplaceWithNew: vi.fn(),
  onRemove: vi.fn(), onShowProgress: vi.fn(),
})

function open(props: Partial<Parameters<typeof ExerciseSheet>[0]> = {}) {
  const a = actions()
  const result = render(
    <ExerciseSheet exercise={exercise} catalogue={catalogue}
      suggestion={{ weight: 60, reps: 8 }} {...a} {...props} />)
  act(() => { useSheets.getState().open(`sheet-ex-${exercise.id}`) })
  return { ...result, actions: a }
}

describe('ExerciseSheet', () => {
  it('separates the two fields with opposite lifetimes', () => {
    // Rest belongs to this session; the increment belongs to the exercise and
    // outlives the workout. The caption names both lifetimes in one line, and
    // the note-and-pain group carries its own head.
    open()
    expect(screen.getByText('Pause gilt für dieses Workout, Schrittweite für die Übung.'))
      .toBeInTheDocument()
    expect(screen.getByText('Heute')).toBeInTheDocument()
  })

  it('saves the rest time on blur', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    const field = screen.getByLabelText('Pause (Sekunden)')
    await user.clear(field)
    await user.type(field, '120')
    await user.tab()
    expect(a.onRestChange).toHaveBeenCalledWith(120)
  })

  it('clears the rest time back to the exercise default', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.clear(screen.getByLabelText('Pause (Sekunden)'))
    await user.tab()
    expect(a.onRestChange).toHaveBeenCalledWith(null)
  })

  it('saves the twinge and the note together', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Schmerz / Zwicken'))
    await user.type(screen.getByLabelText('Notiz'), 'linke Schulter')
    await user.click(screen.getByText('Speichern'))
    expect(a.onMetaSave).toHaveBeenCalledWith({ pain: true, notes: 'linke Schulter' })
  })

  it('edits and deletes an individual set', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    const first = exercise.sets[0]!

    await user.click(screen.getByLabelText('Satz 1 speichern'))
    expect(a.onSetUpdate).toHaveBeenCalledWith(first.id, first.weight, first.reps)

    const rowsBefore = screen.getAllByLabelText(/Satz \d+ löschen/).length
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    // Delayed commit: the row hides now (the ones behind it renumber), the
    // DELETE waits out the undo window -- nothing has hit the server yet.
    expect(a.onSetDelete).not.toHaveBeenCalled()
    expect(screen.getAllByLabelText(/Satz \d+ löschen/)).toHaveLength(rowsBefore - 1)
    useUndo.getState().commitNow()
    expect(a.onSetDelete).toHaveBeenCalledWith(first.id)
  })

  it('undo brings a deleted set back without any server call', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    useUndo.getState().undoNow()
    expect(screen.getByLabelText('Satz 1 löschen')).toBeInTheDocument()
    expect(a.onSetDelete).not.toHaveBeenCalled()
  })

  it('pre-fills the append row from the suggestion', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByRole('button', { name: 'Satz anhängen' }))
    expect(a.onAddSet).toHaveBeenCalledWith(60, 8)
  })

  it('leaves the append row empty when there is nothing to seed from', () => {
    open({ suggestion: null })
    expect(screen.getByLabelText('Neuer Satz, Gewicht in kg')).toHaveValue(null)
  })

  it('offers the replace picker filtered to the same muscle group', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Übung ersetzen'))

    const select = screen.getByLabelText('Ersatzübung')
    // Same group, and never the exercise being replaced.
    expect(select).toHaveTextContent('Andere Brustübung')
    expect(select).not.toHaveTextContent('Ganz andere Gruppe')
    expect(select).not.toHaveTextContent(exercise.name)

    await user.click(screen.getByText('Ersetzen'))
    expect(a.onReplace).toHaveBeenCalledWith(900)
  })

  it('starts on the create pane when nothing in the group can replace it', () => {
    // The pane choice keys off the FILTERED list, which can be empty even for
    // a full catalogue -- that is why it is not keyed off the catalogue.
    open({ catalogue: [{ id: 901, name: 'Ganz andere Gruppe', muscle_group: 'Waden' }] })
    expect(screen.getByText(/Keine andere Übung für/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Ersatzübung')).not.toBeInTheDocument()
  })

  it('switches to creating a replacement and back', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Übung ersetzen'))
    await user.click(screen.getByText('+ Neue Übung anlegen'))

    await user.type(screen.getByLabelText('Name'), 'Kabelzug')
    await user.click(screen.getByText('Anlegen und ersetzen'))
    expect(a.onReplaceWithNew).toHaveBeenCalledWith('Kabelzug')
  })

  it('names the skip action for what it will do', () => {
    const skipped: LiveExercise = { ...exercise, skipped: true }
    const { rerender } = open()
    expect(screen.getByText('Übung überspringen')).toBeInTheDocument()

    rerender(<ExerciseSheet exercise={skipped} catalogue={catalogue}
      suggestion={null} {...actions()} />)
    expect(screen.getByText('Nicht mehr überspringen')).toBeInTheDocument()
  })

  it('offers undo instead of a confirm before removing the exercise', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Übung entfernen'))
    // No confirm() dialog, no write yet: the toast window is the decision.
    expect(a.onRemove).not.toHaveBeenCalled()
    expect(useUndo.getState().pending?.label).toContain('wird entfernt')
    useUndo.getState().commitNow()
    expect(a.onRemove).toHaveBeenCalled()
  })

  it('undo keeps the exercise, nothing was written', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Übung entfernen'))
    useUndo.getState().undoNow()
    expect(a.onRemove).not.toHaveBeenCalled()
    expect(useUndo.getState().pending).toBeNull()
  })
})

import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useUndo } from '../../undo'
import { fold } from '../../search'
import { ExerciseSheet } from './ExerciseSheet'
import { useSaveState, useSheets } from '../stores'
import { payload } from '../types.test-d'
import { listed } from '../__fixtures__/catalogue'
import type { LiveExercise } from '../types'

beforeEach(() => {
  useUndo.setState({ pending: null, timer: null })
  useSheets.setState(useSheets.getInitialState(), true)
  useSaveState.setState({ locked: {} })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const exercise = payload.visible_exercises[0]!
const catalogue = [
  listed(exercise.exercise_id, exercise.name,
    { muscle_group: exercise.muscle_group, search: fold(exercise.name) }),
  listed(900, 'Andere Brustübung',
    { muscle_group: exercise.muscle_group, search: 'andere brustubung' }),
  listed(901, 'Ganz andere Gruppe', { muscle_group: 'Waden', search: 'ganz andere gruppe' }),
]

const actions = () => ({
  onRestChange: vi.fn(), onIncrementChange: vi.fn(), onMetaSave: vi.fn(),
  onSetUpdate: vi.fn(), onSetDelete: vi.fn(), onAddSet: vi.fn(),
  onToggleSkip: vi.fn(), onReplace: vi.fn(),
  onRemove: vi.fn(), onShowProgress: vi.fn(), onMakeLive: vi.fn(),
})

function open(props: Partial<Parameters<typeof ExerciseSheet>[0]> = {}) {
  const a = actions()
  const result = render(
    <ExerciseSheet exercise={exercise} catalogue={catalogue}
      suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} {...a} {...props} />)
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

  it('saves the twinge on the tap, with no button to forget', async () => {
    // It waited for a Speichern beside the note: tick it, close the sheet,
    // and the tick stayed on screen while nothing was saved.
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Schmerz / Zwicken'))
    expect(a.onMetaSave).toHaveBeenCalledWith({ pain: true, notes: '' })
    expect(screen.queryByText('Speichern')).toBeNull()
  })

  it('saves the note when the field is left, and only if it changed', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByLabelText('Notiz'))
    await user.tab()
    expect(a.onMetaSave).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('Notiz'), 'linke Schulter')
    await user.tab()
    expect(a.onMetaSave).toHaveBeenCalledWith({ pain: false, notes: 'linke Schulter' })
  })

  it('edits and deletes an individual set', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    const first = exercise.sets[0]!

    // Unchanged, there is nothing to save.
    expect(screen.getByLabelText('Satz 1 speichern')).toBeDisabled()
    await user.clear(screen.getByLabelText('Satz 1, Wiederholungen'))
    await user.type(screen.getByLabelText('Satz 1, Wiederholungen'), '7')
    await user.click(screen.getByLabelText('Satz 1 speichern'))
    expect(a.onSetUpdate).toHaveBeenCalledWith(first.id, first.weight, 7)

    const rowsBefore = screen.getAllByLabelText(/Satz \d+ löschen/).length
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    // Delayed commit: the row hides now (the ones behind it renumber), the
    // DELETE waits out the undo window -- nothing has hit the server yet.
    expect(a.onSetDelete).not.toHaveBeenCalled()
    expect(screen.getAllByLabelText(/Satz \d+ löschen/)).toHaveLength(rowsBefore - 1)
    useUndo.getState().commitNow()
    expect(a.onSetDelete).toHaveBeenCalledWith(first.id)
  })

  it('shows what a set is worth now, not what it was at page load', async () => {
    // The bug this pins: the sheet's editors seeded their state once, when the
    // page mounted, and a closed <dialog> renders its children -- so every set
    // logged through the live panel afterwards left the editors showing the
    // opening numbers. Saving then posted those stale numbers back over the
    // real ones (typing 62,5 on a set logged at 60x5 stored 62,5x8).
    const user = userEvent.setup()
    const a = actions()
    const first = exercise.sets[0]!
    const logged: LiveExercise = {
      ...exercise,
      sets: exercise.sets.map((s, i) =>
        i === 0 ? { ...s, weight: 60, reps: 5, completed: true } : s),
    }
    const view = render(
      <ExerciseSheet exercise={exercise} catalogue={catalogue}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} {...a} />)
    view.rerender(
      <ExerciseSheet exercise={logged} catalogue={catalogue}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} {...a} />)
    act(() => { useSheets.getState().open(`sheet-ex-${exercise.id}`) })

    expect(screen.getByLabelText('Satz 1, Gewicht in kg')).toHaveValue(60)
    expect(screen.getByLabelText('Satz 1, Wiederholungen')).toHaveValue(5)
    await user.clear(screen.getByLabelText('Satz 1, Wiederholungen'))
    await user.type(screen.getByLabelText('Satz 1, Wiederholungen'), '6')
    await user.click(screen.getByLabelText('Satz 1 speichern'))
    expect(a.onSetUpdate).toHaveBeenCalledWith(first.id, 60, 6)
  })

  it('will not save a cleared field as zero', async () => {
    // Number('') is 0: clearing the reps and saving overwrote a real set
    // with 0 reps.
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.clear(screen.getByLabelText('Satz 1, Wiederholungen'))
    expect(screen.getByLabelText('Satz 1 speichern')).toBeDisabled()
    await user.click(screen.getByLabelText('Satz 1 speichern'))
    expect(a.onSetUpdate).not.toHaveBeenCalled()
  })

  it('follows a set that changes while the sheet is open', async () => {
    // A shared workout writes into these rows from the other phone, and a
    // deload rewrites them from this one. An editor left showing the previous
    // number would post it back the next time it is saved.
    const { rerender } = open()
    expect(screen.getByLabelText('Satz 1, Gewicht in kg'))
      .toHaveValue(exercise.sets[0]!.weight)

    const changed: LiveExercise = {
      ...exercise,
      sets: exercise.sets.map((s, i) => (i === 0 ? { ...s, weight: 42.5 } : s)),
    }
    rerender(<ExerciseSheet exercise={changed} catalogue={catalogue}
      suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} {...actions()} />)
    expect(screen.getByLabelText('Satz 1, Gewicht in kg')).toHaveValue(42.5)
  })

  it('undo brings a deleted set back without any server call', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    useUndo.getState().undoNow()
    expect(screen.getByLabelText('Satz 1 löschen')).toBeInTheDocument()
    expect(a.onSetDelete).not.toHaveBeenCalled()
  })

  it('pre-fills the append row from the last set', async () => {
    // Appending is usually one more of what you just did.
    const user = userEvent.setup()
    const { actions: a } = open()
    const last = exercise.sets[exercise.sets.length - 1]!
    await user.click(screen.getByRole('button', { name: 'Satz anhängen' }))
    expect(a.onAddSet).toHaveBeenCalledWith(last.weight, last.reps)
  })

  it('pre-fills the append row from the suggestion when nothing is logged', async () => {
    const user = userEvent.setup()
    const { actions: a } = open({ exercise: { ...exercise, sets: [] } })
    await user.click(screen.getByRole('button', { name: 'Satz anhängen' }))
    expect(a.onAddSet).toHaveBeenCalledWith(60, 8)
  })

  it('leaves the append row empty, and shut, when there is nothing to seed from', async () => {
    // An empty row used to log a completed 0 kg x 0 set.
    const user = userEvent.setup()
    const { actions: a } = open({ exercise: { ...exercise, sets: [] }, suggestion: null })
    expect(screen.getByLabelText('Neuer Satz, Gewicht in kg')).toHaveValue(null)
    const add = screen.getByRole('button', { name: 'Satz anhängen' })
    expect(add).toBeDisabled()
    await user.type(screen.getByLabelText('Neuer Satz, Gewicht in kg'), '20')
    await user.type(screen.getByLabelText('Neuer Satz, Wiederholungen'), '0')
    expect(add).toBeDisabled()
    await user.clear(screen.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(screen.getByLabelText('Neuer Satz, Wiederholungen'), '10')
    await user.click(add)
    expect(a.onAddSet).toHaveBeenCalledWith(20, 10)
  })

  it('holds the append row while an append for this exercise is in flight', () => {
    useSaveState.setState({ locked: { [`add-${exercise.id}`]: true } })
    open()
    expect(screen.getByRole('button', { name: 'Satz anhängen' })).toBeDisabled()
  })

  it('offers "Jetzt machen" only when asked to, and pulls the exercise forward', async () => {
    const user = userEvent.setup()
    const first = open()
    expect(screen.queryByText('Jetzt machen')).toBeNull()
    first.unmount()

    const { actions: a } = open({ canMakeLive: true })
    await user.click(screen.getByText('Jetzt machen'))
    expect(a.onMakeLive).toHaveBeenCalled()
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

  it('offers the whole list when nothing in the group can replace it', async () => {
    // The filtered list can be empty -- an exercise with no group, or one the
    // list has no neighbour for -- and there is no creating one instead.
    const user = userEvent.setup()
    const { actions: a } = open({ catalogue: [catalogue[0]!, catalogue[2]!] })
    await user.click(screen.getByText('Übung ersetzen'))

    const select = screen.getByLabelText('Ersatzübung')
    expect(select).toHaveTextContent('Ganz andere Gruppe')
    expect(select).not.toHaveTextContent(exercise.name)

    await user.click(screen.getByText('Ersetzen'))
    expect(a.onReplace).toHaveBeenCalledWith(901)
  })

  it('replaces only with an exercise from the list', async () => {
    const user = userEvent.setup()
    open()
    await user.click(screen.getByText('Übung ersetzen'))
    expect(screen.queryByText(/anlegen/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('names the skip action for what it will do', () => {
    const skipped: LiveExercise = { ...exercise, skipped: true }
    const { rerender } = open()
    expect(screen.getByText('Übung überspringen')).toBeInTheDocument()

    rerender(<ExerciseSheet exercise={skipped} catalogue={catalogue}
      suggestion={null} canMakeLive={false} {...actions()} />)
    expect(screen.getByText('Nicht mehr überspringen')).toBeInTheDocument()
  })

  it('says what skipping does to the sets that are still open', () => {
    // The old line promised "Sätze bleiben" while the server dropped every
    // pending set on skip and re-seeded from history on the way back.
    open()
    expect(screen.getByText('Offene Sätze entfallen, erledigte bleiben.')).toBeInTheDocument()
    expect(screen.queryByText(/Sätze bleiben, zählen aber nicht/)).toBeNull()
  })

  it('does not offer to remove an exercise that belongs to the shared plan', () => {
    // A follower's remove was undone by the leader's next change -- the row is
    // the leader's structure. Skipping is theirs, and sticks.
    open({ exercise: { ...exercise, mirrored: true } })
    expect(screen.queryByText('Übung entfernen')).toBeNull()
    expect(screen.getByText('Übung überspringen')).toBeInTheDocument()
    expect(screen.getByText('Übung ersetzen')).toBeInTheDocument()
    expect(screen.getByText(/Gehört zum gemeinsamen Plan/)).toBeInTheDocument()
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

import { act, render, screen, within } from '@testing-library/react'
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

// Its own rest, 2:30, and none for today, whatever the lifter the fixture
// was captured from had set when it was: the pills below are read against it.
const exercise = {
  ...payload.visible_exercises[0]!, rest_setting: 150, rest_setting_mine: true, rest_seconds: null,
}
const catalogue = [
  listed(exercise.exercise_id, exercise.name,
    { muscle_group: exercise.muscle_group, search: fold(exercise.name) }),
  listed(900, 'Andere Brustübung',
    { muscle_group: exercise.muscle_group, search: 'andere brustubung' }),
  listed(901, 'Ganz andere Gruppe', { muscle_group: 'Waden', search: 'ganz andere gruppe' }),
]

const actions = () => ({
  onRestChange: vi.fn(), onOpenSettings: vi.fn(), onMetaSave: vi.fn(),
  onSetUpdate: vi.fn(), onSetDelete: vi.fn(() => Promise.resolve()), onAddSet: vi.fn(),
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
  it('opens with the drawing on top, named for a screen reader', () => {
    // Round 4: the live card's tile opens this sheet to show it whole.
    expect(exercise.picture).not.toBeNull()
    open()
    // The movement's drawing (review): "Bankdrücken", not the Kurzhantel entry.
    const img = screen.getByRole('img', { name: 'Zeichnung: Bankdrücken' })
    expect(img).toHaveAttribute('src', exercise.picture)
    const body = img.closest('.sheet__body')!
    expect(body.firstElementChild).toHaveClass('pic-full')
  })

  it('leaves the picture out while the exercise has none', () => {
    const { container } = open({ exercise: { ...exercise, picture: null } })
    expect(container.ownerDocument.querySelector('.pic-full')).toBeNull()
    expect(screen.getByText('Pause heute')).toBeInTheDocument()
  })

  it("keeps today's rest apart from the settings that hold for every workout", () => {
    // Two rest fields side by side read as one. Today's is here; the lifter's
    // settings are one level down, and the row says they always apply.
    open()
    expect(screen.getByText('Pause heute')).toBeInTheDocument()
    expect(screen.getByText('Eine andere Zeit gilt nur für dieses Workout.')).toBeInTheDocument()
    expect(screen.getByText('Pause 2:30 · Schritt 2 kg — gelten immer')).toBeInTheDocument()
    expect(screen.getByText('Heute')).toBeInTheDocument()
    expect(screen.queryByLabelText('Pause (Sekunden)')).toBeNull()
    expect(screen.queryByLabelText('Schrittweite (kg)')).toBeNull()
  })

  it('marks the rest in force and saves a pick on the tap', async () => {
    // The exercise has its own rest, 2:30, and none for today: the row
    // centres on it, marked "deine".
    const user = userEvent.setup()
    const { actions: a } = open()
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['1:30', '2:00', '2:30deine', '3:00', '3:30', 'Andere'])
    expect(row.getByRole('button', { name: '2:30 deine' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(row.getByRole('button', { name: '3:00' }))
    expect(a.onRestChange).toHaveBeenCalledWith(180)
  })

  it('goes back to the setting in one tap', async () => {
    const user = userEvent.setup()
    const { actions: a } = open({ exercise: { ...exercise, rest_seconds: 180 } })
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getByRole('button', { name: '3:00' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(row.getByRole('button', { name: '2:30 deine' }))
    expect(a.onRestChange).toHaveBeenCalledWith(150)
  })

  it("marks the list's rest as the list's", () => {
    open({ exercise: { ...exercise, rest_setting: 90, rest_setting_mine: false } })
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getByRole('button', { name: '1:30 Liste' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('nudges another rest in 15 seconds and sends it once, when it settles', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      const { actions: a } = open()
      await user.click(screen.getByRole('button', { name: 'Andere' }))
      for (let i = 0; i < 3; i += 1) {
        await user.click(screen.getByRole('button', { name: '15 Sekunden mehr' }))
      }
      // Off the row: "Andere" is the one lit, showing the value.
      const row = within(screen.getByRole('group', { name: 'Pause heute' }))
      expect(row.getByRole('button', { name: '3:15 Andere' }))
        .toHaveAttribute('aria-pressed', 'true')
      expect(a.onRestChange).not.toHaveBeenCalled()

      act(() => { vi.advanceTimersByTime(500) })
      expect(a.onRestChange).toHaveBeenCalledTimes(1)
      expect(a.onRestChange).toHaveBeenCalledWith(195)
    } finally {
      vi.useRealTimers()
    }
  })

  it('opens the settings one level down', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByRole('button', { name: /Deine Einstellungen/ }))
    expect(a.onOpenSettings).toHaveBeenCalled()
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
    expect(a.onSetDelete).toHaveBeenCalledWith(first.id, false)
  })

  it('sends a delete flushed on the way out with keepalive (G-062)', async () => {
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    useUndo.getState().commitNow(true)
    expect(a.onSetDelete).toHaveBeenCalledWith(exercise.sets[0]!.id, true)
  })

  it('brings the row back when its delete fails (G-147)', async () => {
    // The set stayed hidden: gone from the screen, still on the server.
    const user = userEvent.setup()
    open({ onSetDelete: vi.fn(() => Promise.reject(new Error('offline'))) })
    const rowsBefore = screen.getAllByLabelText(/Satz \d+ löschen/).length
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    await act(async () => { useUndo.getState().commitNow() })
    expect(screen.getAllByLabelText(/Satz \d+ löschen/)).toHaveLength(rowsBefore)
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

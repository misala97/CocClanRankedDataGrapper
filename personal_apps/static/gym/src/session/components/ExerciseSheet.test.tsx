import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useUndo } from '../../undo'
import { fold } from '../../search'
import { ExerciseSheet, SAVED_MS } from './ExerciseSheet'
import { useDeleting, useOutbox, useSheets } from '../stores'
import { payload } from '../types.test-d'
import { listed } from '../__fixtures__/catalogue'
import type { LiveExercise } from '../types'
import { NUDGE_SETTLE_MS } from '../../settings/Choice'

beforeEach(() => {
  useUndo.setState({ pending: null, timer: null })
  useSheets.setState(useSheets.getInitialState(), true)
  useOutbox.setState(useOutbox.getInitialState(), true)
  useDeleting.setState(useDeleting.getInitialState(), true)
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
  onRoutinePlanChange: vi.fn(),
})

function open(props: Partial<Parameters<typeof ExerciseSheet>[0]> = {}) {
  const a = actions()
  const result = render(
    <ExerciseSheet exercise={exercise} catalogue={catalogue} inWorkout={[]}
      suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null}
      {...a} {...props} />)
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
    // centres on it, marked "Deine".
    const user = userEvent.setup()
    const { actions: a } = open()
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['1:30', '2:00', '2:30Deine', '3:00', '3:30', 'Andere'])
    expect(row.getByRole('button', { name: '2:30 Deine' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(row.getByRole('button', { name: '3:00' }))
    expect(a.onRestChange).toHaveBeenCalledWith(180)
  })

  it('goes back to the setting in one tap', async () => {
    const user = userEvent.setup()
    const { actions: a } = open({ exercise: { ...exercise, rest_seconds: 180 } })
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getByRole('button', { name: '3:00' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(row.getByRole('button', { name: '2:30 Deine' }))
    expect(a.onRestChange).toHaveBeenCalledWith(150)
  })

  it('marks the standard rest by that name', () => {
    open({ exercise: { ...exercise, rest_setting: 90, rest_setting_mine: false } })
    const row = within(screen.getByRole('group', { name: 'Pause heute' }))
    expect(row.getByRole('button', { name: '1:30 Standard' })).toHaveAttribute('aria-pressed', 'true')
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
    expect(a.onSetDelete).toHaveBeenCalledWith(first.id)
  })

  it('sends a delete flushed on the way out (G-062)', async () => {
    // Queued on the phone by the island, which keeps it through the page
    // going away -- nothing here has to say how.
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    useUndo.getState().commitNow(true)
    expect(a.onSetDelete).toHaveBeenCalledWith(exercise.sets[0]!.id)
  })

  it('hides a set for the whole screen while its delete waits, and hands it on at the commit (G-061)', async () => {
    // Hidden only here, the totals under the sheet still counted it. From the
    // commit on the outbox draws it gone until it lands, and brings a refused
    // one back (G-147) -- this list hiding it on would hide that too.
    const user = userEvent.setup()
    const refused = vi.fn(() => Promise.reject(new Error('refused')))
    open({ onSetDelete: refused })
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    expect(useDeleting.getState().names).toEqual([`#${exercise.sets[0]!.id}`])
    await act(async () => { useUndo.getState().commitNow() })
    expect(refused).toHaveBeenCalledWith(exercise.sets[0]!.id)
    expect(useDeleting.getState().names).toEqual([])
  })

  it('undo shows the set again everywhere (G-061)', async () => {
    const user = userEvent.setup()
    open()
    await user.click(screen.getByLabelText('Satz 1 löschen'))
    act(() => { useUndo.getState().undoNow() })
    expect(useDeleting.getState().names).toEqual([])
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
      <ExerciseSheet exercise={exercise} catalogue={catalogue} inWorkout={[]}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null} {...a} />)
    view.rerender(
      <ExerciseSheet exercise={logged} catalogue={catalogue} inWorkout={[]}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null} {...a} />)
    act(() => { useSheets.getState().open(`sheet-ex-${exercise.id}`) })

    expect(screen.getByLabelText('Satz 1, Gewicht in kg je Seite')).toHaveValue(60)
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
    expect(screen.getByLabelText('Satz 1, Gewicht in kg je Seite'))
      .toHaveValue(exercise.sets[0]!.weight)

    const changed: LiveExercise = {
      ...exercise,
      sets: exercise.sets.map((s, i) => (i === 0 ? { ...s, weight: 42.5 } : s)),
    }
    rerender(<ExerciseSheet exercise={changed} catalogue={catalogue} inWorkout={[]}
      suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null}
      {...actions()} />)
    expect(screen.getByLabelText('Satz 1, Gewicht in kg je Seite')).toHaveValue(42.5)
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
    expect(screen.getByLabelText('Neuer Satz, Gewicht in kg je Seite')).toHaveValue(null)
    const add = screen.getByRole('button', { name: 'Satz anhängen' })
    expect(add).toBeDisabled()
    await user.type(screen.getByLabelText('Neuer Satz, Gewicht in kg je Seite'), '20')
    await user.type(screen.getByLabelText('Neuer Satz, Wiederholungen'), '0')
    expect(add).toBeDisabled()
    await user.clear(screen.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(screen.getByLabelText('Neuer Satz, Wiederholungen'), '10')
    await user.click(add)
    expect(a.onAddSet).toHaveBeenCalledWith(20, 10)
  })

  it('takes a quarter-kilo weight as a valid one, and nothing finer (G-146)', async () => {
    // step="0.5" marked 11,25 invalid. The weight is kept to the hundredth.
    const user = userEvent.setup()
    const { actions: a } = open({ exercise: { ...exercise, sets: [] }, suggestion: null })
    const weight = screen.getByLabelText('Neuer Satz, Gewicht in kg je Seite') as HTMLInputElement
    await user.type(weight, '11.25')
    expect(weight.validity.valid).toBe(true)
    await user.type(screen.getByLabelText('Neuer Satz, Wiederholungen'), '8')
    await user.click(screen.getByRole('button', { name: 'Satz anhängen' }))
    expect(a.onAddSet).toHaveBeenCalledWith(11.25, 8)

    await user.clear(weight)
    await user.type(weight, '11.125')
    expect(weight.validity.valid).toBe(false)
    expect(screen.getByRole('button', { name: 'Satz anhängen' })).toBeDisabled()
  })

  it('never holds the append row for the connection (G-138)', () => {
    // Held while an append was in flight, it stayed held for as long as the
    // wifi was gone. A double tap is the island's to drop.
    useOutbox.setState({ state: 'waiting', count: 1, setIds: [-5] })
    open()
    expect(screen.getByRole('button', { name: 'Satz anhängen' })).toBeEnabled()
  })

  it('keeps what is being typed when the set just added gets its real id (B6 review)', async () => {
    // Drawn as -5 until the add lands: the same set, so nothing remounts.
    const user = userEvent.setup()
    const drawn = { ...exercise, sets: [...exercise.sets,
      { id: -5, weight: 70, reps: 5, completed: true, base_weight: null, key: 'k1' }] }
    const view = open({ exercise: drawn })
    const typed = () => screen.getByLabelText('Neuer Satz, Gewicht in kg je Seite')
    await user.clear(typed())
    await user.type(typed(), '72.5')
    const last = screen.getAllByLabelText(/^Satz \d+, Gewicht in kg je Seite$/).at(-1)!
    await user.clear(last)
    await user.type(last, '71')

    const named = { ...drawn, sets: drawn.sets.map((s) => (s.id === -5 ? { ...s, id: 900 } : s)) }
    view.rerender(
      <ExerciseSheet exercise={named} catalogue={catalogue} inWorkout={[]}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null}
        {...view.actions} />)
    expect(typed()).toHaveValue(72.5)
    expect(screen.getAllByLabelText(/^Satz \d+, Gewicht in kg je Seite$/).at(-1)).toHaveValue(71)
  })

  it('keeps a set just added hidden while its delete waits, as the set gets its real id (B6 re-review)', async () => {
    // Hidden by its drawn id, the row came back when the add landed, for the
    // rest of the undo window.
    const user = userEvent.setup()
    const drawn = { ...exercise, sets: [...exercise.sets,
      { id: -5, weight: 70, reps: 5, completed: true, base_weight: null, key: 'k1' }] }
    const view = open({ exercise: drawn })
    const rows = () => screen.getAllByLabelText(/^Satz \d+, Gewicht in kg je Seite$/)
    const before = rows().length
    await user.click(screen.getByRole('button', { name: `Satz ${before} löschen` }))
    expect(rows()).toHaveLength(before - 1)

    const named = { ...drawn, sets: drawn.sets.map((s) => (s.id === -5 ? { ...s, id: 900 } : s)) }
    view.rerender(
      <ExerciseSheet exercise={named} catalogue={catalogue} inWorkout={[]}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null}
        {...view.actions} />)
    expect(rows()).toHaveLength(before - 1)
  })

  it('marks a set whose write waits on the phone (B6)', () => {
    const [first, second] = exercise.sets
    useOutbox.setState({ state: 'waiting', count: 1, setIds: [first!.id] })
    const { container } = open()
    const labels = container.querySelectorAll('.sset .label')
    expect(labels[0]).toHaveClass('is-waiting')
    expect(labels[0]).toHaveTextContent('erledigt, wartet auf Verbindung')
    expect(labels[1]).not.toHaveClass('is-waiting')
    expect(second).toBeDefined()
  })

  it('says it waits for a reload while only a fresh page can send (B6 review)', () => {
    useOutbox.setState({ state: 'blocked', count: 1, setIds: [exercise.sets[0]!.id] })
    const { container } = open()
    expect(container.querySelector('.sset .label')).toHaveTextContent('erledigt, wartet auf Neuladen')
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

    await user.selectOptions(select, '900')
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

    await user.selectOptions(select, '901')
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

    rerender(<ExerciseSheet exercise={skipped} catalogue={catalogue} inWorkout={[]}
      suggestion={null} canMakeLive={false} routine={null}
      {...actions()} />)
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

  it('closes the sheet at the remove tap and hands the remove on (G-067)', async () => {
    // Open, it stayed editable for the whole window, on an exercise about
    // to go. The undo is the island's, which hides the row meanwhile.
    const user = userEvent.setup()
    const { actions: a } = open()
    await user.click(screen.getByText('Übung entfernen'))
    expect(useSheets.getState().openId).toBeNull()
    expect(a.onRemove).toHaveBeenCalledTimes(1)
  })

  describe('a set row saves itself (G-058)', () => {
    const reps = () => screen.getByLabelText('Satz 2, Wiederholungen')
    const second = exercise.sets[1]!

    it('saves as focus leaves the row, not as it moves inside it', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(reps())
      await user.type(reps(), '9')
      // Back to the weight: the same row.
      await user.click(screen.getByLabelText('Satz 2, Gewicht in kg je Seite'))
      expect(a.onSetUpdate).not.toHaveBeenCalled()
      await user.click(screen.getByLabelText('Notiz'))
      expect(a.onSetUpdate).toHaveBeenCalledTimes(1)
      expect(a.onSetUpdate).toHaveBeenCalledWith(second.id, second.weight, 9)
    })

    it('saves on Enter', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(reps())
      await user.type(reps(), '9{Enter}')
      expect(a.onSetUpdate).toHaveBeenCalledWith(second.id, second.weight, 9)
    })

    it('saves what was typed when the sheet closes', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(reps())
      await user.type(reps(), '9')
      act(() => { useSheets.getState().close() })
      expect(a.onSetUpdate).toHaveBeenCalledTimes(1)
      expect(a.onSetUpdate).toHaveBeenCalledWith(second.id, second.weight, 9)
    })

    it('saves the same numbers once, left and then closed', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(reps())
      await user.type(reps(), '9')
      await user.click(screen.getByLabelText('Notiz'))
      act(() => { useSheets.getState().close() })
      expect(a.onSetUpdate).toHaveBeenCalledTimes(1)
    })

    it('saves nothing unchanged or unsaveable', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.click(reps())
      await user.click(screen.getByLabelText('Notiz'))
      await user.clear(reps())
      await user.click(screen.getByLabelText('Notiz'))
      act(() => { useSheets.getState().close() })
      expect(a.onSetUpdate).not.toHaveBeenCalled()
    })

    it('says "Gespeichert" for a moment, under the row that saved', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      try {
        const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
        open()
        await user.clear(reps())
        await user.type(reps(), '9{Enter}')
        const hint = screen.getByText('Gespeichert')
        expect(hint).toHaveClass('sset__hint--ok')
        expect(screen.getAllByText('Gespeichert')).toHaveLength(1)
        act(() => { vi.advanceTimersByTime(SAVED_MS) })
        expect(screen.queryByText('Gespeichert')).toBeNull()
      } finally {
        vi.useRealTimers()
      }
    })
  })

  it('marks each set done or open, and says so beside its numbers (G-059)', () => {
    // Done: a tick; open: its number -- in the card chips' colours. A
    // screen reader hears the word with each field.
    const { container } = open()
    const marks = [...container.querySelectorAll('.sset__ord')]
    expect(marks.map((m) => m.classList.contains('is-done'))).toEqual([true, false, false])
    expect(marks[0]!.querySelector('svg')).not.toBeNull()
    expect(marks[1]).toHaveTextContent('2offen')
    expect(screen.getByLabelText('Satz 1, Wiederholungen')).toHaveAccessibleDescription('erledigt')
    expect(screen.getByLabelText('Satz 2, Gewicht in kg je Seite')).toHaveAccessibleDescription('offen')
  })

  it('says the weight is per side for a one-sided exercise, as the card does (G-057)', () => {
    const { container, unmount } = open()
    expect(screen.getByLabelText('Satz 1, Gewicht in kg je Seite')).toBeInTheDocument()
    expect(screen.getByLabelText('Neuer Satz, Gewicht in kg je Seite')).toBeInTheDocument()
    expect(container.ownerDocument.querySelector('.sset__unit--side')).toHaveTextContent('kgje Seite')
    unmount()

    open({ exercise: { ...exercise, is_unilateral: false } })
    expect(screen.getByLabelText('Satz 1, Gewicht in kg')).toBeInTheDocument()
    expect(document.querySelector('.sset__unit--side')).toBeNull()
  })

  it('plans no set for a skipped exercise, and says why', () => {
    open({ exercise: { ...exercise, skipped: true } })
    expect(screen.queryByRole('button', { name: 'Satz anhängen' })).toBeNull()
    expect(screen.getByText(/Übersprungen — neue Sätze erst nach/)).toBeInTheDocument()
  })

  describe('replacing (G-068)', () => {
    const mine = [
      catalogue[0]!,
      listed(902, 'Seltene Brustübung', { muscle_group: exercise.muscle_group }),
      listed(903, 'Zweite von dir', { muscle_group: exercise.muscle_group, common: true, rank: 2 }),
      listed(904, 'Erste von dir', { muscle_group: exercise.muscle_group, common: true, rank: 1 }),
    ]

    it('chooses nothing until the lifter does', async () => {
      // The first of the list stood preselected: one tap swapped in an
      // exercise nobody picked.
      const user = userEvent.setup()
      const { actions: a } = open({ catalogue: mine })
      await user.click(screen.getByText('Übung ersetzen'))
      expect(screen.getByLabelText('Ersatzübung')).toHaveValue('')
      const go = screen.getByRole('button', { name: 'Ersetzen' })
      expect(go).toBeDisabled()
      await user.click(go)
      expect(a.onReplace).not.toHaveBeenCalled()
    })

    it("lists the lifter's own first, in the order they do them most", () => {
      open({ catalogue: mine })
      const groups = [...document.querySelectorAll('#replace-select-10 optgroup')]
      expect(groups.map((g) => g.getAttribute('label'))).toEqual(['Deine', 'Weitere'])
      expect([...groups[0]!.querySelectorAll('option')].map((o) => o.textContent))
        .toEqual(['Erste von dir', 'Zweite von dir'])
      expect([...groups[1]!.querySelectorAll('option')].map((o) => o.textContent))
        .toEqual(['Seltene Brustübung'])
    })

    it('marks the ones already in the workout', async () => {
      const user = userEvent.setup()
      open({ catalogue: mine, inWorkout: [exercise.exercise_id, 903] })
      await user.click(screen.getByText('Übung ersetzen'))
      expect(screen.getByRole('option', { name: 'Zweite von dir — schon im Workout' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Erste von dir' })).toBeInTheDocument()
    })

    it('puts the button beside the list', async () => {
      const user = userEvent.setup()
      open({ catalogue: mine })
      await user.click(screen.getByText('Übung ersetzen'))
      const row = screen.getByLabelText('Ersatzübung').closest('.sheet__save-row')!
      expect(within(row as HTMLElement).getByRole('button', { name: 'Ersetzen' })).toBeInTheDocument()
    })
  })

  describe('"Sicher?" past twice the best (Q5, G-070)', () => {
    // The fixture's best: 60 kg, 10 reps.
    const weight = () => screen.getByLabelText('Satz 2, Gewicht in kg je Seite')

    it('asks before a row saves a weight past twice the best, and saves on "Ja"', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(weight())
      await user.type(weight(), '600')
      expect(screen.getByText('Sicher? Bisher höchstens 60,0 kg je Seite.')).toBeInTheDocument()
      expect(screen.getByLabelText('Satz 2 speichern')).toBeDisabled()
      await user.click(screen.getByLabelText('Notiz'))
      expect(a.onSetUpdate).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: 'Ja, speichern' }))
      expect(a.onSetUpdate).toHaveBeenCalledTimes(1)
      expect(a.onSetUpdate).toHaveBeenCalledWith(exercise.sets[1]!.id, 600, exercise.sets[1]!.reps)
    })

    it('saves nothing unanswered as the sheet closes', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      await user.clear(weight())
      await user.type(weight(), '600')
      act(() => { useSheets.getState().close() })
      expect(a.onSetUpdate).not.toHaveBeenCalled()
    })

    it('asks again for other numbers', async () => {
      const user = userEvent.setup()
      open()
      await user.clear(weight())
      await user.type(weight(), '600')
      await user.click(screen.getByRole('button', { name: 'Ja, speichern' }))
      await user.clear(weight())
      await user.type(weight(), '300')
      expect(screen.getByText('Sicher? Bisher höchstens 60,0 kg je Seite.')).toBeInTheDocument()
    })

    it('asks before the add row plans reps past twice the best', async () => {
      const user = userEvent.setup()
      const { actions: a } = open()
      const reps = screen.getByLabelText('Neuer Satz, Wiederholungen')
      await user.clear(reps)
      await user.type(reps, '21')
      expect(screen.getByText('Sicher? Bisher höchstens 10 Wdh.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Satz anhängen' })).toBeDisabled()
      await user.click(screen.getByRole('button', { name: 'Ja, anhängen' }))
      expect(a.onAddSet).toHaveBeenCalledWith(exercise.sets[2]!.weight, 21)
    })

    it('asks nothing about the numbers the add row starts from (B7 review)', async () => {
      // After "Ja, anhängen" the row starts from the set just said yes to:
      // asked again, a second "Ja" planned that set twice.
      const user = userEvent.setup()
      const { actions: a, rerender } = open()
      const reps = screen.getByLabelText('Neuer Satz, Wiederholungen')
      await user.clear(reps)
      await user.type(reps, '21')
      await user.click(screen.getByRole('button', { name: 'Ja, anhängen' }))
      const last = exercise.sets[exercise.sets.length - 1]!
      const planned: LiveExercise = { ...exercise, sets: [...exercise.sets,
        { ...last, id: -7, reps: 21, completed: false, key: 'k7' }] }
      rerender(<ExerciseSheet exercise={planned} catalogue={catalogue} inWorkout={[]}
        suggestion={{ weight: 60, reps: 8 }} canMakeLive={false} routine={null} {...a} />)
      expect(screen.getByLabelText('Neuer Satz, Wiederholungen')).toHaveValue(21)
      expect(screen.queryByText(/Sicher\?/)).toBeNull()
      expect(screen.getByRole('button', { name: 'Satz anhängen' })).toBeEnabled()
    })

    it('asks nothing before the first set', async () => {
      const user = userEvent.setup()
      open({ exercise: { ...exercise, best: null } })
      await user.clear(weight())
      await user.type(weight(), '600')
      expect(screen.queryByText(/Sicher\?/)).toBeNull()
      expect(screen.getByLabelText('Satz 2 speichern')).toBeEnabled()
    })
  })

  describe("the routine's plan (D2 P1)", () => {
    const routine = { name: 'Push', plan: { sets: 3, rep_min: 6, rep_max: 10 } }

    it('shows what the routine keeps, when the routine holds the exercise', () => {
      open({ routine })
      const group = screen.getByText('Routine „Push“').closest('.sheet__group')!
      expect([...group.querySelectorAll('.field-num__val')].map((o) => o.textContent))
        .toEqual(['3', '6', '10'])
      // What changes when: the routine from the next workout, today's
      // target at once -- the sets already planned stay.
      expect(group).toHaveTextContent(
        'Ab dem nächsten Workout plant die Routine so. Das Ziel heute rechnet schon damit.')
    })

    it('has nothing to change without a routine that holds the exercise', () => {
      open({ routine: null })
      expect(screen.queryByText(/^Routine „/)).toBeNull()
    })

    it('saves a run of taps once, when they settle', () => {
      vi.useFakeTimers()
      try {
        const { actions: a } = open({ routine })
        fireEvent.click(screen.getByRole('button', { name: 'Ein Satz mehr' }))
        fireEvent.click(screen.getByRole('button', { name: 'Ein Satz mehr' }))
        fireEvent.click(screen.getByRole('button', { name: 'Bis: eine Wiederholung mehr' }))
        expect(a.onRoutinePlanChange).not.toHaveBeenCalled()
        act(() => { vi.advanceTimersByTime(NUDGE_SETTLE_MS) })
        expect(a.onRoutinePlanChange).toHaveBeenCalledTimes(1)
        expect(a.onRoutinePlanChange)
          .toHaveBeenCalledWith({ sets: 5, rep_min: 6, rep_max: 11 })
      } finally {
        vi.useRealTimers()
      }
    })

    it('keeps the range the right way round', () => {
      open({ routine: { name: 'Push', plan: { sets: 3, rep_min: 8, rep_max: 8 } } })
      expect(screen.getByRole('button', { name: 'Ab: eine Wiederholung mehr' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Bis: eine Wiederholung weniger' })).toBeDisabled()
    })

    it('stays within one to ten sets', () => {
      open({ routine: { name: 'Push', plan: { sets: 10, rep_min: 6, rep_max: 10 } } })
      expect(screen.getByRole('button', { name: 'Ein Satz mehr' })).toBeDisabled()
    })

    it('sends a draft still settling when the sheet goes away', () => {
      vi.useFakeTimers()
      try {
        const { actions: a, unmount } = open({ routine })
        fireEvent.click(screen.getByRole('button', { name: 'Ein Satz weniger' }))
        unmount()
        expect(a.onRoutinePlanChange).toHaveBeenCalledTimes(1)
        expect(a.onRoutinePlanChange)
          .toHaveBeenCalledWith({ sets: 2, rep_min: 6, rep_max: 10 })
      } finally {
        vi.useRealTimers()
      }
    })

    it('sends a draft still settling when the page goes away', () => {
      // A tap on "Fortschritt" or a closed tab: the write has to outlive
      // the page (B5 review) -- queued, it is on the phone already.
      vi.useFakeTimers()
      try {
        const { actions: a } = open({ routine })
        fireEvent.click(screen.getByRole('button', { name: 'Ein Satz mehr' }))
        act(() => { window.dispatchEvent(new Event('pagehide')) })
        expect(a.onRoutinePlanChange).toHaveBeenCalledTimes(1)
        expect(a.onRoutinePlanChange)
          .toHaveBeenCalledWith({ sets: 4, rep_min: 6, rep_max: 10 })
      } finally {
        vi.useRealTimers()
      }
    })
  })
})

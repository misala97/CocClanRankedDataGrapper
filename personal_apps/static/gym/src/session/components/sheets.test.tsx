import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeloadSheet } from './DeloadSheet'
import { TemplateSheet } from './TemplateSheet'
import { AddExerciseSheet } from './AddExerciseSheet'
import { useSheets } from '../stores'
import { payload } from '../types.test-d'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const open = (id: string) => act(() => { useSheets.getState().open(id) })
const session = payload.session

describe('DeloadSheet', () => {
  const base = {
    deloadApplied: false, deloadPcts: [60, 70, 80], deloadDefaultPct: 70,
    hasCompletedSet: false, onToggle: vi.fn(),
  }

  it('offers to mark a normal session as a deload', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<DeloadSheet {...base} session={session} onToggle={onToggle} />)
    open('sheet-deload')

    await user.click(screen.getByText('Als Deload markieren'))
    expect(onToggle).toHaveBeenCalledWith(true, 70)
  })

  it('offers the depth picker only while nothing is logged', () => {
    // Changing the percentage after a set is logged would rewrite nothing --
    // the weights that were lifted are the weights that were lifted.
    const deload = { ...session, is_deload: true, deload_pct: 70 }
    const { rerender } = render(
      <DeloadSheet {...base} session={deload} onToggle={vi.fn()} />)
    open('sheet-deload')
    expect(screen.getByRole('group', { name: 'Deload-Tiefe' })).toBeInTheDocument()

    rerender(<DeloadSheet {...base} session={deload} hasCompletedSet onToggle={vi.fn()} />)
    expect(screen.queryByRole('group', { name: 'Deload-Tiefe' })).not.toBeInTheDocument()
  })

  it('marks the chosen depth for assistive tech, not by class alone', () => {
    const deload = { ...session, is_deload: true, deload_pct: 70 }
    render(<DeloadSheet {...base} session={deload} onToggle={vi.fn()} />)
    open('sheet-deload')
    expect(screen.getByText('70 %')).toHaveAttribute('aria-current', 'true')
    expect(screen.getByText('60 %')).not.toHaveAttribute('aria-current')
  })

  it('explains a flag that changed no weights', () => {
    const deload = { ...session, is_deload: true, deload_pct: 70 }
    render(<DeloadSheet {...base} session={deload} hasCompletedSet
      deloadApplied={false} onToggle={vi.fn()} />)
    open('sheet-deload')
    expect(screen.getByText(/Nur markiert/)).toBeInTheDocument()
  })

  it('ends a deload from the same control', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<DeloadSheet {...base} session={{ ...session, is_deload: true, deload_pct: 80 }}
      hasCompletedSet onToggle={onToggle} />)
    open('sheet-deload')

    await user.click(screen.getByText('Deload beenden'))
    expect(onToggle).toHaveBeenCalledWith(false, 80)
  })
})

describe('TemplateSheet', () => {
  it('saves the typed name', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<TemplateSheet onSave={onSave} />)
    open('sheet-template')

    await user.type(screen.getByLabelText('Name der Routine'), 'Push Day')
    await user.click(screen.getByText('Speichern'))
    expect(onSave).toHaveBeenCalledWith('Push Day')
  })

  it('dismisses with Abbrechen, because it is one decision not a workspace', () => {
    render(<TemplateSheet onSave={vi.fn()} />)
    open('sheet-template')
    expect(screen.getByText('Abbrechen')).toBeInTheDocument()
  })
})

describe('AddExerciseSheet', () => {
  // `search` as the server sends it (exercises.search_text): the folded name
  // and aliases.
  const catalogue = [
    { id: 1, name: 'Bankdrücken', muscle_group: 'Brust', search: 'bankdrucken bench press' },
    { id: 2, name: 'Klimmzug', muscle_group: 'Rücken', search: 'klimmzug pull up' },
  ]
  const props = { catalogue, inSession: [], onAdd: vi.fn() }

  it('filters the list as you type, without a round trip', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen'), 'klimm')
    expect(screen.getByText('Klimmzug')).toBeInTheDocument()
    expect(screen.queryByText('Bankdrücken')).not.toBeInTheDocument()
  })

  it('finds a German name by an English one, and without the umlaut', async () => {
    // The list renamed every lifter's exercise to German; "Bench Press" and
    // "bankdruecken" are how they typed it before.
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    const field = screen.getByLabelText('Übung suchen')

    await user.type(field, 'Bench Press')
    expect(screen.getByText('Bankdrücken')).toBeInTheDocument()
    expect(screen.queryByText('Klimmzug')).not.toBeInTheDocument()

    await user.clear(field)
    await user.type(field, 'bankdruecken')
    expect(screen.getByText('Bankdrücken')).toBeInTheDocument()
  })

  it('offers nothing to create, and says when the list has no match', async () => {
    // One list for everyone: an exercise that is not on it cannot be made up
    // here.
    const user = userEvent.setup()
    const { container } = render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen'), 'Nackenzieher')
    expect(screen.queryByText(/anlegen/i)).not.toBeInTheDocument()
    expect(container.querySelectorAll('.exadd__row')).toHaveLength(0)
    expect(screen.getByText(/Keine Übung in der Liste/)).toBeInTheDocument()
  })

  it('counts what is already in the session from the payload', () => {
    // Derived from the session's real contents rather than tallied
    // client-side, so the count cannot drift from the workout.
    render(<AddExerciseSheet {...props}
      inSession={payload.visible_exercises}
      catalogue={[{ id: payload.visible_exercises[0]!.exercise_id,
                    name: 'Schon drin', muscle_group: null, search: 'schon drin' }]} />)
    open('sheet-add-exercise')
    expect(screen.getByText('1× drin')).toBeInTheDocument()
  })

  it('keeps the query when the sheet is closed and reopened', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    await user.type(screen.getByLabelText('Übung suchen'), 'klimm')

    act(() => { useSheets.getState().close() })
    open('sheet-add-exercise')
    expect(screen.getByLabelText('Übung suchen')).toHaveValue('klimm')
  })

  it('marks the row it is adding and refuses a second tap on it', async () => {
    // Adding an exercise has no optimistic path -- it waits for the server,
    // which recomputes which exercise is live -- and the sheet stays open, so
    // without this a slow add looks like a tap that did nothing. Tapping again
    // adds the exercise twice. .exadd__row.is-busy was written for exactly
    // this and nothing ever applied it.
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const { container } = render(
      <AddExerciseSheet {...props} onAdd={onAdd} busyExerciseId={1} />)
    open('sheet-add-exercise')

    const row = screen.getByText('Bankdrücken').closest('button')!
    expect(row).toHaveClass('is-busy')
    expect(container.querySelectorAll('.is-busy')).toHaveLength(1)

    await user.click(row)
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('opens with the cursor in the search field, not on Fertig', () => {
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    expect(screen.getByLabelText('Übung suchen')).toHaveFocus()
  })

  it('asks before adding a second copy of an exercise already in the workout', async () => {
    // After an add the one row left under the thumb was that exercise itself,
    // and tapping it -- the natural "that one" -- added it twice.
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const inWorkout = [{ ...payload.visible_exercises[0]!, exercise_id: 1, name: 'Bankdrücken' }]
    render(<AddExerciseSheet {...props} onAdd={onAdd} inSession={inWorkout} />)
    open('sheet-add-exercise')

    await user.click(screen.getByText('Bankdrücken'))
    expect(onAdd).not.toHaveBeenCalled()
    expect(screen.getByText('Nochmal hinzufügen?')).toBeInTheDocument()

    await user.click(screen.getByText('Bankdrücken'))
    expect(onAdd).toHaveBeenCalledWith(1)
  })

  it('empties the search and confirms once the add has landed, not before', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const { rerender } = render(<AddExerciseSheet {...props} onAdd={onAdd} />)
    open('sheet-add-exercise')
    const field = screen.getByLabelText('Übung suchen')
    await user.type(field, 'bank')
    await user.click(screen.getByText('Bankdrücken'))

    // Still waiting on the server: the query stays for a retry.
    expect(onAdd).toHaveBeenCalledWith(1)
    expect(field).toHaveValue('bank')
    expect(field).toHaveFocus()

    const landed = [{ ...payload.visible_exercises[0]!, exercise_id: 1, name: 'Bankdrücken' }]
    rerender(<AddExerciseSheet {...props} onAdd={onAdd} inSession={landed} />)
    expect(field).toHaveValue('')
    expect(screen.getByRole('status')).toHaveTextContent('✓ Bankdrücken ist drin.')
  })

  it('adds without closing, so six exercises is not six round trips', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<AddExerciseSheet {...props} onAdd={onAdd} />)
    open('sheet-add-exercise')

    await user.click(screen.getByText('Bankdrücken'))
    expect(onAdd).toHaveBeenCalledWith(1)
    expect(useSheets.getState().openId).toBe('sheet-add-exercise')
  })
})

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

    await user.type(screen.getByLabelText('Name der Vorlage'), 'Push Day')
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
  const catalogue = [
    { id: 1, name: 'Bankdrücken', muscle_group: 'Brust' },
    { id: 2, name: 'Klimmzug', muscle_group: 'Rücken' },
  ]
  const props = { catalogue, inSession: [], onAdd: vi.fn(), onCreate: vi.fn() }

  it('filters the list as you type, without a round trip', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen oder anlegen'), 'klimm')
    expect(screen.getByText('Klimmzug')).toBeInTheDocument()
    expect(screen.queryByText('Bankdrücken')).not.toBeInTheDocument()
  })

  it('offers to create only when nothing matches', async () => {
    // The create path is what the list offers when the search matches nothing
    // -- never a mode to switch into.
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    expect(screen.queryByText(/Anlegen:/)).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Übung suchen oder anlegen'), 'Nackenzieher')
    expect(screen.getByText(/Anlegen:/)).toBeInTheDocument()
  })

  it('does not offer to create a duplicate of an exact match', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen oder anlegen'), 'Klimmzug')
    expect(screen.queryByText(/Anlegen:/)).not.toBeInTheDocument()
  })

  it('counts what is already in the session from the payload', () => {
    // Derived from the session's real contents rather than tallied
    // client-side, so the count cannot drift from the workout.
    render(<AddExerciseSheet {...props}
      inSession={payload.visible_exercises}
      catalogue={[{ id: payload.visible_exercises[0]!.exercise_id,
                    name: 'Schon drin', muscle_group: null }]} />)
    open('sheet-add-exercise')
    expect(screen.getByText('1× drin')).toBeInTheDocument()
  })

  it('keeps the query when the sheet is closed and reopened', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    await user.type(screen.getByLabelText('Übung suchen oder anlegen'), 'klimm')

    act(() => { useSheets.getState().close() })
    open('sheet-add-exercise')
    expect(screen.getByLabelText('Übung suchen oder anlegen')).toHaveValue('klimm')
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

import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeloadSheet } from './DeloadSheet'
import { TemplateSheet } from './TemplateSheet'
import { AddExerciseSheet } from './AddExerciseSheet'
import { useSheets } from '../stores'
import { payload } from '../types.test-d'
import { listed } from '../__fixtures__/catalogue'

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

  it('draws its decision as a button, both ways (G-075)', () => {
    // As a bare text row, "Als Deload markieren" read as a line of prose.
    const { rerender } = render(<DeloadSheet {...base} session={session} onToggle={vi.fn()} />)
    open('sheet-deload')
    expect(screen.getByRole('button', { name: 'Als Deload markieren' }))
      .toHaveClass('btn', 'btn--live', 'btn--block')
    rerender(<DeloadSheet {...base} session={{ ...session, is_deload: true, deload_pct: 70 }}
      onToggle={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Deload beenden' }))
      .toHaveClass('btn', 'btn--ghost', 'btn--block')
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

  it('keeps a record a deload sets (G-078)', () => {
    render(<DeloadSheet {...base} session={session} onToggle={vi.fn()} />)
    open('sheet-deload')
    expect(screen.getByText(/Ein Rekord bleibt ein Rekord\./)).toBeInTheDocument()
    expect(screen.queryByText(/keine\s+Rekorde/)).not.toBeInTheDocument()
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
  // As the server sends them: `search` is the folded name and aliases.
  const catalogue = [
    listed(1, 'Bankdrücken (Langhantel)', { search: 'bankdrucken langhantel bench press' }),
    listed(2, 'Latzug (Kabel)', { muscle_group: 'Rücken', search: 'latzug kabel lat pulldown' }),
  ]
  const props = { catalogue, groups: ['Brust', 'Rücken'], inSession: [], onAdd: vi.fn() }

  // One lifter's history: two preacher-curl machines, one of them mainly
  // (owner: "we have 2 preacher curls and we only do one mainly"), a row
  // machine done a lot, a second one done twice long ago, a curl tried once.
  const history = [
    listed(10, 'Scottcurls (Maschine)',
      { muscle_group: 'Bizeps', workouts: 12, days_ago: 1, rank: 2, common: true }),
    listed(11, 'Scottcurls (Maschine, Scheiben)',
      { muscle_group: 'Bizeps', workouts: 9, days_ago: 33, rank: 3, common: true }),
    listed(12, 'Scottcurls (SZ-Stange)', { muscle_group: 'Bizeps' }),
    listed(20, 'Rudern (Maschine)',
      { muscle_group: 'Rücken', workouts: 23, days_ago: 1, rank: 1, common: true }),
    listed(21, 'Rudern (T-Bar, liegend)',
      { muscle_group: 'Rücken', workouts: 2, days_ago: 70, rank: 5 }),
    listed(22, 'Rudern (Kabel)', { muscle_group: 'Rücken' }),
    listed(30, 'Bizepscurls (Kurzhantel)',
      { muscle_group: 'Bizeps', workouts: 1, days_ago: 4, rank: 4 }),
    listed(31, 'Bankdrücken (Langhantel)'),
  ]
  const lived = { ...props, catalogue: history, groups: ['Brust', 'Rücken', 'Bizeps'] }

  /** The exercise or movement each row names, in order. */
  const names = (root: ParentNode) => Array.from(root.querySelectorAll('.sheet-row__name'))
    .map((name) => name.childNodes[0]?.textContent)
  const section = (name: string) => screen.getByRole('region', { name: new RegExp(`^${name}`) })

  it('leads with what you do often, one movement’s machines together, the main one first', () => {
    render(<AddExerciseSheet {...lived} />)
    open('sheet-add-exercise')

    const deine = section('Deine')
    expect(names(deine)).toEqual(
      ['Rudern (Maschine)', 'Scottcurls (Maschine)', 'Scottcurls (Maschine, Scheiben)'])
    expect(within(deine).getByText('23×')).toBeInTheDocument()
    expect(within(deine).getAllByText('Gestern')).toHaveLength(2)
    // Done, but not often: down in the full list, not up here.
    expect(within(deine).queryByText('Rudern (T-Bar, liegend)')).not.toBeInTheDocument()
    expect(within(deine).queryByText('Bizepscurls (Kurzhantel)')).not.toBeInTheDocument()
  })

  it('lists every movement once below it, by muscle in the list’s order, A-Z', () => {
    render(<AddExerciseSheet {...lived} />)
    open('sheet-add-exercise')

    expect(screen.getByText('Alle Übungen')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 4 })
      .map((head) => head.querySelector('.label')!.textContent)).toEqual(['Brust', 'Rücken', 'Bizeps'])
    const bizeps = section('Bizeps')
    expect(names(bizeps)).toEqual(['Bizepscurls', 'Scottcurls'])
    // The variants you do, with how often; one Gerät is its own row.
    expect(within(bizeps).getByText('Maschine 12× · Maschine, Scheiben 9×')).toBeInTheDocument()
    expect(within(bizeps).getByText('Kurzhantel 1×')).toBeInTheDocument()
    expect(within(section('Rücken')).getByText('Maschine 23× · T-Bar, liegend 2×')).toBeInTheDocument()
  })

  it('adds a one-Gerät movement straight from the list, keyboard down', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    render(<AddExerciseSheet {...lived} onAdd={onAdd} />)
    open('sheet-add-exercise')

    await user.click(within(section('Brust')).getByText('Bankdrücken'))
    expect(onAdd).toHaveBeenCalledWith(31)
    expect(screen.getByLabelText('Übung suchen')).not.toHaveFocus()
  })

  it('opens a movement’s machines one level deeper, yours first, the main one marked', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const { container } = render(<AddExerciseSheet {...lived} onAdd={onAdd} />)
    open('sheet-add-exercise')

    await user.click(within(section('Bizeps')).getByText('Scottcurls'))
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Scottcurls')
    expect(screen.queryByLabelText('Übung suchen')).not.toBeInTheDocument()
    expect(names(container)).toEqual(['Maschine', 'Maschine, Scheiben', 'SZ-Stange'])
    expect(screen.getAllByText('meistens')).toHaveLength(1)
    expect(screen.getByText('Gestern · 12 Workouts')).toBeInTheDocument()
    expect(screen.getByText('vor 5 Wochen · 9 Workouts')).toBeInTheDocument()
    expect(screen.getByText('Weitere Geräte')).toBeInTheDocument()
    expect(screen.getByText('Noch nie gemacht')).toBeInTheDocument()
    // The reader moves with the sheet.
    expect(screen.getByLabelText('Zurück')).toHaveFocus()

    await user.click(screen.getByText('SZ-Stange'))
    expect(onAdd).toHaveBeenCalledWith(12)

    await user.click(screen.getByLabelText('Zurück'))
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Übung hinzufügen')
    expect(container.querySelector('[data-movement="Scottcurls"]')).toHaveFocus()
  })

  it('marks "meistens" only where there was a choice', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...lived} catalogue={history.filter((e) => e.id !== 11)} />)
    open('sheet-add-exercise')
    await user.click(within(section('Bizeps')).getByText('Scottcurls'))
    // One machine of yours is trivially the main one: nothing to say.
    expect(screen.queryByText('meistens')).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Zurück'))
    await user.click(within(section('Rücken')).getByText('Rudern'))
    expect(names(screen.getByRole('dialog'))).toEqual(['Maschine', 'T-Bar, liegend', 'Kabel'])
    expect(screen.getAllByText('meistens')).toHaveLength(1)
  })

  it('finds exact exercises, yours first and the rest quieter', async () => {
    const user = userEvent.setup()
    const { container } = render(<AddExerciseSheet {...lived} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen'), 'curls')
    const rows = Array.from(container.querySelectorAll('.exadd__row'))
    expect(names(container)).toEqual(['Scottcurls (Maschine)', 'Scottcurls (Maschine, Scheiben)',
      'Scottcurls (SZ-Stange)', 'Bizepscurls (Kurzhantel)'])
    expect(rows[0]).not.toHaveClass('exadd__row--other')
    expect(rows[2]).toHaveClass('exadd__row--other')
  })

  it('on a first run says the top fills up, and shows the whole list', () => {
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    expect(screen.getByText('Was du oft machst, rückt hier nach oben.')).toBeInTheDocument()
    expect(screen.queryByText('Deine')).not.toBeInTheDocument()
    expect(screen.queryByText('Alle Übungen')).not.toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 })
      .map((head) => head.querySelector('.label')!.textContent)).toEqual(['Brust', 'Rücken'])
  })

  it('filters the list as you type, without a round trip', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')

    await user.type(screen.getByLabelText('Übung suchen'), 'lat')
    expect(screen.getByText('Latzug (Kabel)')).toBeInTheDocument()
    expect(screen.queryByText(/Bankdrücken/)).not.toBeInTheDocument()
  })

  it('finds a German name by an English one, and without the umlaut', async () => {
    // The list renamed every lifter's exercise to German; "Bench Press" and
    // "bankdruecken" are how they typed it before.
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    const field = screen.getByLabelText('Übung suchen')

    await user.type(field, 'Bench Press')
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
    expect(screen.queryByText(/Latzug/)).not.toBeInTheDocument()

    await user.clear(field)
    await user.type(field, 'bankdruecken')
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
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

  it('marks what is already in the session, from the payload', () => {
    // Derived from the session's real contents rather than tallied
    // client-side, so the mark cannot drift from the workout.
    const first = payload.visible_exercises[0]!
    const { rerender } = render(<AddExerciseSheet {...props} inSession={[first]}
      catalogue={[listed(first.exercise_id, 'Schon drin (Maschine)')]} />)
    open('sheet-add-exercise')
    expect(screen.getByText('drin')).toBeInTheDocument()

    rerender(<AddExerciseSheet {...props} inSession={[first, { ...first, id: 999 }]}
      catalogue={[listed(first.exercise_id, 'Schon drin (Maschine)')]} />)
    expect(screen.getByText('2× drin')).toBeInTheDocument()
  })

  it('keeps the query when the sheet is closed and reopened', async () => {
    const user = userEvent.setup()
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    await user.type(screen.getByLabelText('Übung suchen'), 'lat')

    act(() => { useSheets.getState().close() })
    open('sheet-add-exercise')
    expect(screen.getByLabelText('Übung suchen')).toHaveValue('lat')
  })

  it('marks the row it is adding and refuses a second tap on it', async () => {
    // Adding an exercise has no optimistic path -- it waits for the server,
    // which recomputes which exercise is live -- and the sheet stays open, so
    // without this a slow add looks like a tap that did nothing. Tapping again
    // adds the exercise twice.
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

  it('keeps focus on the row while it adds, not on the page behind', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const { rerender } = render(<AddExerciseSheet {...props} onAdd={onAdd} />)
    open('sheet-add-exercise')

    const row = screen.getByText('Bankdrücken').closest('button')!
    await user.click(row)
    expect(onAdd).toHaveBeenCalledWith(1)
    rerender(<AddExerciseSheet {...props} onAdd={onAdd} busyExerciseId={1} />)
    expect(row).toHaveAttribute('aria-disabled', 'true')
    expect(row).toHaveFocus()
  })

  it('opens without taking focus, so no keyboard jumps up over the list', () => {
    render(<AddExerciseSheet {...props} />)
    open('sheet-add-exercise')
    const field = screen.getByLabelText('Übung suchen')
    expect(field).not.toHaveFocus()
    expect(field).not.toHaveAttribute('data-autofocus')
  })

  it('asks before adding a second copy of an exercise already in the workout', async () => {
    // After an add the one row left under the thumb was that exercise itself,
    // and tapping it -- the natural "that one" -- added it twice.
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const inWorkout = [{ ...payload.visible_exercises[0]!, exercise_id: 1, name: 'Bankdrücken (Langhantel)' }]
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
    await user.click(screen.getByText('Bankdrücken (Langhantel)'))

    // Still waiting on the server: the query stays for a retry, and the
    // cursor stays where the next name is typed.
    expect(onAdd).toHaveBeenCalledWith(1)
    expect(field).toHaveValue('bank')
    expect(field).toHaveFocus()

    const landed = [{ ...payload.visible_exercises[0]!, exercise_id: 1, name: 'Bankdrücken (Langhantel)' }]
    rerender(<AddExerciseSheet {...props} onAdd={onAdd} inSession={landed} />)
    expect(field).toHaveValue('')
    expect(screen.getByRole('status')).toHaveTextContent('✓ Bankdrücken (Langhantel) ist drin.')
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

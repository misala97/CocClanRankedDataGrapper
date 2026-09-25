import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CataloguePage } from './CataloguePage'
import type { CatalogueEntry, CataloguePayload, RestOverview } from './types'
import { useCatalogueUi } from './store'
import { fold } from '../search'

beforeEach(() => {
  useCatalogueUi.setState(useCatalogueUi.getInitialState(), true)
  sessionStorage.clear()
})
afterEach(() => { vi.unstubAllGlobals() })

/** By kind of exercise, nothing of the lifter's own. */
const REST: RestOverview = {
  rest_for_all: null, exceptions: [], start_seconds: 150,
  list_min_seconds: 60, list_max_seconds: 180, min_seconds: 15, max_seconds: 600,
}

const LIST = { default_rest_seconds: 180, weight_increment: 2.5, bar_weight: 20, stack_kg: null }

const entry = (id: number, name: string, aka = ''): CatalogueEntry => ({
  exercise: {
    id, name, muscle_group: 'Brust', is_unilateral: false,
    default_rest_seconds: 180, weight_increment: 2.5, equipment: 'barbell',
    bar_weight: 20, stack_kg: null, secondary_muscle_groups: null, list_defaults: LIST,
    own: [], rest_for_all: null,
  },
  search: fold(`${name} ${aka}`),
  chip_class: null, chip_label: null, last_done: null, best_weight: null,
  last_weight: null, days_ago: null, sessions_since_pr: null,
})

const base: CataloguePayload = {
  groups: [
    { name: 'Brust', entries: [entry(1, 'Bankdrücken (Langhantel)')] },
    { name: 'Beine', entries: [] },
  ],
  open_by_default: true,
  rest: REST,
}

const mount = (over: Partial<CataloguePayload> = {}) =>
  render(<CataloguePage payload={{ ...base, ...over }} />)

describe('CataloguePage', () => {
  it('lists the lifter\'s exercises and offers nothing to create', () => {
    // One list for everyone: an exercise comes from the add sheet in a
    // workout, never from here.
    const { container } = mount()
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Neue Übung/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/anlegen/i)).not.toBeInTheDocument()
    // The one sheet here sets the rest; none creates an exercise.
    expect([...container.querySelectorAll('dialog')].map((d) => d.id)).toEqual(['sheet-rest'])
  })

  it('points an empty group to the add sheet in a workout', () => {
    mount()
    expect(screen.getByText('keine Übung')).toBeInTheDocument()
    expect(screen.getByText(/Übungen für Beine findest du im Workout unter „Übung hinzufügen“/))
      .toBeInTheDocument()
  })

  it('points an empty catalogue there too, by way of the start page', () => {
    mount({ groups: [{ name: 'Brust', entries: [] }] })
    expect(screen.getByText('Noch keine Übungen')).toBeInTheDocument()
    expect(screen.getByText(/„Übung hinzufügen“/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Auf Start ein Workout beginnen' }))
      .toHaveAttribute('href', '/gym')
    // Nothing to rest between yet.
    expect(screen.queryByText('Deine Pause')).toBeNull()
  })

  it('names each order by what it does, the first grouping as well (G-022)', () => {
    mount()
    const orders = within(screen.getByRole('group', { name: 'Übungen ordnen' }))
    expect(orders.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['Nach Muskelgruppe', 'Stagniert zuerst', 'Zuletzt trainiert'])
    expect(orders.getByRole('button', { name: 'Nach Muskelgruppe' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('counts a stall in workouts since the last record, and drops it at none (D16)', () => {
    mount({
      groups: [{
        name: 'Brust',
        entries: [
          { ...entry(1, 'Bankdrücken (Langhantel)'), days_ago: 3, sessions_since_pr: 4 },
          { ...entry(2, 'Schrägbankdrücken'), days_ago: 3, sessions_since_pr: 1 },
          { ...entry(3, 'Butterfly'), days_ago: 3, sessions_since_pr: 0 },
        ],
      }],
    })
    const meta = (name: string) =>
      screen.getByText(name).closest('a')!.querySelector('.row__meta')!.textContent
    expect(meta('Bankdrücken (Langhantel)')).toBe('vor 3 Tagen · seit 4 Workouts ohne Rekord')
    expect(meta('Schrägbankdrücken')).toBe('vor 3 Tagen · seit 1 Workout ohne Rekord')
    expect(meta('Butterfly')).toBe('vor 3 Tagen')
  })
})

describe('the Übungen search (G-020)', () => {
  const groups = [
    {
      name: 'Brust',
      entries: [
        { ...entry(1, 'Bankdrücken (Langhantel)', 'Bench Press'), last_done: '2026-09-01T10:00:00' },
        { ...entry(2, 'Butterfly (Maschine)', 'Pec Deck Chest Fly'), last_done: '2026-09-20T10:00:00' },
      ],
    },
    { name: 'Beine', entries: [entry(3, 'Beinpresse (Maschine)', 'Leg Press')] },
  ]
  const shown = () => [...document.querySelectorAll('.uebungen-row .nameline__n')]
    .map((n) => n.textContent)

  it('finds by the add sheet\'s text: English names, and one typo', async () => {
    mount({ groups })
    const field = screen.getByRole('searchbox', { name: 'Übungen durchsuchen' })
    await userEvent.type(field, 'bench')
    expect(shown()).toEqual(['Bankdrücken (Langhantel)'])
    expect(screen.queryByText(/Kein genauer Treffer/)).toBeNull()
    await userEvent.clear(field)
    await userEvent.type(field, 'Bankdrüken')
    expect(shown()).toEqual(['Bankdrücken (Langhantel)'])
    // Found a typo away, and it says so: unlabelled, a near miss read as
    // what the search matched.
    expect(screen.getByText('Kein genauer Treffer für „Bankdrüken“ – ähnlich geschrieben:'))
      .toBeInTheDocument()
    await userEvent.clear(field)
    await userEvent.type(field, 'beine')
    expect(shown()).toEqual(['Beinpresse (Maschine)'])
  })

  it('reads a query that folds to nothing as none', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, set href(url: string) { assign(url) } })
    mount({ groups })
    await userEvent.type(screen.getByRole('searchbox', { name: 'Übungen durchsuchen' }), '-{Enter}')
    expect(shown()).toHaveLength(3)
    expect(screen.queryByText(/Keine Übung gefunden/)).toBeNull()
    // Not a search: the bands say their size, not "n von m", and Enter
    // opens nothing.
    expect(document.querySelector('.uebungen-group-header')?.textContent).not.toMatch(/ von /)
    expect(assign).not.toHaveBeenCalled()
  })

  it('opens with Enter the first row as shown, in a flat order too', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, set href(url: string) { assign(url) } })
    useCatalogueUi.setState({ sort: 'recent' })
    mount({ groups })
    await userEvent.type(screen.getByRole('searchbox', { name: 'Übungen durchsuchen' }),
      'brust{Enter}')
    // Newest first: the Butterfly, not the list's first row.
    expect(shown()[0]).toBe('Butterfly (Maschine)')
    expect(assign).toHaveBeenCalledWith('/gym/exercises/2')
  })
})

describe('Deine Pause', () => {
  /** The server's answer to POST /gym/rest, from what was sent. */
  function server(answer: (seconds: number | null) => RestOverview) {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const sent = (init.body as FormData).get('rest_seconds') as string
      const reply = answer(sent === '' ? null : Number(sent))
      return { ok: true, status: 200, json: async () => reply } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }
  const sent = (fetchMock: ReturnType<typeof server>, call = 0) =>
    [fetchMock.mock.calls[call]![0], (fetchMock.mock.calls[call]![1].body as FormData)
      .get('rest_seconds')]

  it("sits above the exercises and says the list's range by kind of exercise", () => {
    mount()
    const row = screen.getByRole('button', { name: /Deine Pause/ })
    expect(row).toHaveTextContent('Je nach Übungsart')
    expect(row).toHaveTextContent('1:00–3:00')
  })

  it('says a rest for all and counts its exceptions', () => {
    mount({ rest: { ...REST, rest_for_all: 150, exceptions: [
      { exercise_id: 7, name: 'Latzug (Kabel)', rest_seconds: 180 },
      { exercise_id: 8, name: 'Scottcurls (Maschine)', rest_seconds: 180 },
    ] } })
    const row = screen.getByRole('button', { name: /Deine Pause/ })
    expect(row).toHaveTextContent('Für alle Übungen · 2 Ausnahmen')
    expect(row).toHaveTextContent('2:30')
  })

  it('switches to one rest for all, from where the lifter already is', async () => {
    const user = userEvent.setup()
    const fetchMock = server((seconds) => ({ ...REST, rest_for_all: seconds }))
    mount({ rest: { ...REST, exceptions: [
      { exercise_id: 7, name: 'Latzug (Kabel)', rest_seconds: 180 },
    ] } })
    await user.click(screen.getByRole('button', { name: /Deine Pause/ }))
    const sheet = within(document.getElementById('sheet-rest')!)
    expect(sheet.getByText('Eigene Pausen')).toBeInTheDocument()

    await user.click(sheet.getByRole('button', { name: 'Eine für alle' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(sent(fetchMock)).toEqual(['/gym/rest', '150'])
    expect(sheet.getByRole('button', { name: 'Eine für alle' })).toHaveAttribute('aria-pressed', 'true')
    expect(sheet.getByText('2:30')).toBeInTheDocument()
    // Absorbed by the server: the answer is what the list shows.
    expect(await sheet.findByText('Keine — jede deiner Übungen pausiert 2:30.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Deine Pause/ })).toHaveTextContent('Für alle Übungen')
  })

  it('sends a nudged rest once, at the latest when the sheet closes', async () => {
    const user = userEvent.setup()
    const fetchMock = server((seconds) => ({ ...REST, rest_for_all: seconds }))
    mount({ rest: { ...REST, rest_for_all: 150 } })
    await user.click(screen.getByRole('button', { name: /Deine Pause/ }))
    const sheet = within(document.getElementById('sheet-rest')!)
    await user.click(sheet.getByRole('button', { name: '15 Sekunden mehr' }))
    await user.click(sheet.getByRole('button', { name: '15 Sekunden mehr' }))
    expect(fetchMock).not.toHaveBeenCalled()

    await user.click(sheet.getByRole('button', { name: 'Fertig' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(sent(fetchMock)).toEqual(['/gym/rest', '180'])
    await waitFor(() => expect(screen.getByRole('button', { name: /Deine Pause/ }))
      .toHaveTextContent('3:00'))
  })

  it("goes back to the list's rest by kind of exercise", async () => {
    const user = userEvent.setup()
    const fetchMock = server((seconds) => ({ ...REST, rest_for_all: seconds }))
    mount({ rest: { ...REST, rest_for_all: 150 } })
    await user.click(screen.getByRole('button', { name: /Deine Pause/ }))
    const sheet = within(document.getElementById('sheet-rest')!)
    await user.click(sheet.getByRole('button', { name: 'Je nach Übungsart' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(sent(fetchMock)).toEqual(['/gym/rest', ''])
    expect(sheet.queryByRole('button', { name: '15 Sekunden mehr' })).toBeNull()
    expect(sheet.getByText('Standard: je nach Übung 1:00 bis 3:00 — Kreuzheben mehr, Curls weniger.'))
      .toBeInTheDocument()
  })

  it("links each exception to the exercise's own settings", async () => {
    const user = userEvent.setup()
    mount({ rest: { ...REST, rest_for_all: 150, exceptions: [
      { exercise_id: 7, name: 'Latzug (Kabel)', rest_seconds: 180 },
    ] } })
    await user.click(screen.getByRole('button', { name: /Deine Pause/ }))
    const link = within(document.getElementById('sheet-rest')!)
      .getByRole('link', { name: /Latzug \(Kabel\)/ })
    expect(link).toHaveAttribute('href', '/gym/exercises/7#einstellungen')
    expect(link).toHaveTextContent('Eigene Pause bei der Übung')
    expect(link).toHaveTextContent('3:00')
  })
})

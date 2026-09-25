import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CataloguePage } from './CataloguePage'
import type { CatalogueEntry, CataloguePayload, LibraryEntry, RestOverview } from './types'
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
  last_weight: null, days_ago: null, sessions_since_pr: null, picture: null, in_running: false,
})

/** library.LIST_GROUPS */
const LIST_GROUPS = ['Brust', 'Rücken', 'Schultern', 'Bizeps', 'Trizeps', 'Beine', 'Gesäß',
  'Waden', 'Bauch', 'Unterarme']

const base: CataloguePayload = {
  groups: [
    { name: 'Brust', entries: [entry(1, 'Bankdrücken (Langhantel)')] },
    { name: 'Beine', entries: [] },
  ],
  open_by_default: true,
  rest: REST,
  library: [],
  list_groups: LIST_GROUPS,
}

/** A list exercise the lifter has not had. */
const listed = (id: number, movement: string, label: string, group: string, aka = ''): LibraryEntry => ({
  id, name: `${movement} (${label})`, movement, label, movement_group: group,
  search: fold(`${movement} (${label}) ${aka}`), picture: `/static/gym/art/${id}.webp`,
})

/** The rest of a small list, in the server's order (by name) -- not the
 *  order it shows in. */
const LIBRARY: LibraryEntry[] = [
  listed(10, 'Kniebeugen', 'Langhantel', 'Beine', 'Squat'),
  listed(11, 'Kniebeugen', 'Smith-Maschine', 'Beine', 'Squat'),
  listed(12, 'Beinstrecker', 'Maschine', 'Beine', 'Leg Extension'),
  listed(20, 'Wadenheben', 'stehend', 'Waden', 'Calf Raise'),
  listed(30, 'Schrägbankdrücken', 'Langhantel', 'Brust', 'Incline Bench Press'),
]

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

  it('says a row of yours with no set yet as that, not as never done (M6)', () => {
    // "Noch nie gemacht" names the part below now: the list's rest.
    mount({ groups: [{ name: 'Brust', entries: [
      entry(1, 'Bankdrücken (Langhantel)'),
      { ...entry(2, 'Butterfly (Maschine)'), days_ago: 3, in_running: true },
      { ...entry(3, 'Dips'), in_running: true },
    ] }] })
    const meta = (name: string) =>
      screen.getByText(name).closest('a')!.querySelector('.row__meta')!.textContent
    expect(meta('Bankdrücken (Langhantel)')).toBe('Noch kein Satz')
    expect(meta('Butterfly (Maschine)')).toBe('vor 3 Tagen')
    // Sets in the running workout, none finished: as its page says.
    expect(meta('Dips')).toBe('Heute im Workout')
  })

  it('opens and folds a band of yours on a tap (G-019)', async () => {
    // The page read the store's `isOpen`, a function that never changed:
    // a tapped band stayed as it was until a reload.
    const user = userEvent.setup()
    mount({ open_by_default: false })
    const band = document.getElementById('g-Brust')!
    expect(band).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Bankdrücken (Langhantel)')).toBeNull()
    await user.click(band)
    expect(band).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
    await user.click(band)
    expect(band).toHaveAttribute('aria-expanded', 'false')
    expect(JSON.parse(sessionStorage.getItem('gym.uebungen.open')!)).toEqual([])
  })

  it('puts the drawing in front of every row of yours, the dumbbell without one', () => {
    mount({ groups: [{ name: 'Brust', entries: [
      { ...entry(1, 'Bankdrücken (Langhantel)'), picture: '/static/gym/art/bench.webp' },
      entry(2, 'Butterfly (Maschine)'),
    ] }] })
    const row = (name: string) => screen.getByText(name).closest('a')!
    expect(row('Bankdrücken (Langhantel)').querySelector('.pic--list img'))
      .toHaveAttribute('src', '/static/gym/art/bench.webp')
    expect(row('Butterfly (Maschine)').querySelector('.pic--list.pic--none')).not.toBeNull()
  })

  it('heads your part with how many are yours, and no count beside the page name', () => {
    mount()
    expect(screen.getByRole('heading', { level: 2, name: 'Deine 1' })).toBeInTheDocument()
    expect(document.querySelector('.verlauf__head')).toHaveTextContent(/^Übungen$/)
  })

  it('gives a new lifter the whole list, their rest and the search (G-004)', () => {
    mount({ groups: [{ name: 'Brust', entries: [] }, { name: 'Beine', entries: [] }],
      library: LIBRARY })
    // Yours: nothing, and what will be here.
    expect(screen.getByRole('heading', { level: 2, name: 'Deine' })).toBeInTheDocument()
    expect(screen.getByText('Noch keine. Was du im Workout loggst, steht danach hier, mit deinem '
      + 'Gewicht und deinen Einstellungen.')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Übungen ordnen' })).toBeNull()
    expect(document.querySelector('.ueb-none')).toBeNull()
    // The rest is all of it.
    expect(screen.getByRole('heading', { level: 2, name: 'Noch nie gemacht 5' })).toBeInTheDocument()
    expect(screen.getByText('Die ganze Liste, nach Muskel und A–Z. Tipp eine Übung an, um sie anzusehen.'))
      .toBeInTheDocument()
    // A rest is set before a first workout too.
    expect(screen.getByRole('button', { name: /Deine Pause/ })).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: 'Übungen durchsuchen' })).toBeInTheDocument()
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

  it('shows its hits in their bands whatever the order, with no order to pick (M6)', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, set href(url: string) { assign(url) } })
    useCatalogueUi.setState({ sort: 'recent' })
    mount({ groups })
    const field = screen.getByRole('searchbox', { name: 'Übungen durchsuchen' })
    // Browsing: the order kept from last time, newest first.
    expect(shown()[0]).toBe('Butterfly (Maschine)')
    await userEvent.type(field, 'brust')
    // Searching: banded as the rest's hits are, "N von M", and no sorts.
    expect(screen.queryByRole('group', { name: 'Übungen ordnen' })).toBeNull()
    expect(document.getElementById('g-Brust')).toHaveTextContent('2 von 2')
    expect(shown()).toEqual(['Bankdrücken (Langhantel)', 'Butterfly (Maschine)'])
    // Enter opens the first as shown.
    await userEvent.type(field, '{Enter}')
    expect(assign).toHaveBeenCalledWith('/gym/exercises/1')
    // The search cleared, the order is back.
    await userEvent.clear(field)
    expect(shown()[0]).toBe('Butterfly (Maschine)')
    expect(screen.getByRole('group', { name: 'Übungen ordnen' })).toBeInTheDocument()
  })
})

describe('Noch nie gemacht (M6, D13-A)', () => {
  const band = (group: string) => document.getElementById(`n-${group}`)!
  const part = () => document.querySelector('.ueb-part--nie') as HTMLElement

  it('lists the rest of the list under yours, banded in the list\'s order and folded', () => {
    mount({ library: LIBRARY })
    expect(within(part()).getByRole('heading', { level: 2 })).toHaveTextContent('Noch nie gemacht 5')
    expect(screen.getByText('Der Rest der Liste, nach Muskel und A–Z. Tipp eine Übung an, um sie '
      + 'anzusehen.')).toBeInTheDocument()
    // The list's order, not the payload's or the alphabet's.
    expect([...part().querySelectorAll('.uebungen-group-header')]
      .map((b) => [b.querySelector('.label')!.textContent, b.getAttribute('aria-expanded')]))
      .toEqual([['Brust', 'false'], ['Beine', 'false'], ['Waden', 'false']])
    expect(band('Beine')).toHaveTextContent('3 Übungen')
    expect(band('Waden')).toHaveTextContent('1 Übung')
    // Folded is folded: no row of it is on the page.
    expect(part().querySelector('a')).toBeNull()
  })

  it('opens a band onto its movements A-Z, each variant a way into its page', async () => {
    const user = userEvent.setup()
    mount({ library: LIBRARY })
    await user.click(band('Beine'))
    expect(band('Beine')).toHaveAttribute('aria-expanded', 'true')
    const moves = [...document.getElementById('nie-Beine')!.querySelectorAll('.nie-move')]
    expect(moves.map((m) => m.querySelector('.nie-move__name')!.textContent))
      .toEqual(['Beinstrecker', 'Kniebeugen'])
    // One variant: the movement is one link, its variant under its name.
    expect(moves[0]!.tagName).toBe('A')
    expect(moves[0]).toHaveAttribute('href', '/gym/exercises/12')
    expect(moves[0]).toHaveTextContent('Beinstrecker Maschine')
    // Several: the drawing once, then each variant its own row, A-Z, named
    // with its movement for a screen reader -- "Langhantel" names nothing.
    expect(moves[1]!.querySelectorAll('.pic--list')).toHaveLength(1)
    expect(within(moves[1] as HTMLElement).getAllByRole('link')
      .map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['Kniebeugen Langhantel', '/gym/exercises/10'],
        ['Kniebeugen Smith-Maschine', '/gym/exercises/11']])
    expect(moves[1]!.querySelector('.pic--list img')).toHaveAttribute('src', '/static/gym/art/10.webp')
  })

  it('remembers its open bands apart from yours', async () => {
    const user = userEvent.setup()
    const { unmount } = mount({ library: LIBRARY })
    await user.click(band('Waden'))
    expect(JSON.parse(sessionStorage.getItem('gym.uebungen.nie')!)).toEqual(['Waden'])
    expect(sessionStorage.getItem('gym.uebungen.open')).toBeNull()
    // Your Brust band is open by the catalogue's size, the rest's is not.
    expect(document.getElementById('g-Brust')).toHaveAttribute('aria-expanded', 'true')
    expect(band('Brust')).toHaveAttribute('aria-expanded', 'false')
    unmount()
    mount({ library: LIBRARY })
    expect(band('Waden')).toHaveAttribute('aria-expanded', 'true')
    await user.click(band('Waden'))
    expect(JSON.parse(sessionStorage.getItem('gym.uebungen.nie')!)).toEqual([])
  })

  it('reads its open bands back on the next page of the visit', async () => {
    sessionStorage.setItem('gym.uebungen.nie', '["Waden"]')
    vi.resetModules()
    const { useCatalogueUi: next } = await import('./store')
    expect(next.getState().nieOpen).toEqual(['Waden'])
  })

  it('names the groups with nothing of yours under your list, each a jump to its band (G-013)', async () => {
    const user = userEvent.setup()
    mount({
      groups: [
        { name: 'Brust', entries: [entry(1, 'Bankdrücken (Langhantel)')] },
        { name: 'Beine', entries: [] }, { name: 'Gesäß', entries: [] }, { name: 'Waden', entries: [] },
      ],
      library: LIBRARY,
    })
    const none = document.querySelector('.ueb-none') as HTMLElement
    expect(none).toHaveTextContent(/^Noch nichts für Beine, Gesäß und Waden\.$/)
    // Your bands name no empty group: it is named once, here.
    expect(document.getElementById('g-Beine')).toBeNull()
    // Gesäß has no band in the rest to jump to (in this list): named, no link.
    expect(within(none).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['Beine', '#nie-Beine'], ['Waden', '#nie-Waden']])
    await user.click(within(none).getByRole('link', { name: 'Beine' }))
    expect(band('Beine')).toHaveAttribute('aria-expanded', 'true')
    // Opened, never closed: a second jump leaves it open.
    await user.click(within(none).getByRole('link', { name: 'Beine' }))
    expect(band('Beine')).toHaveAttribute('aria-expanded', 'true')
    // A search shows hits, not what is missing.
    await user.type(screen.getByRole('searchbox', { name: 'Übungen durchsuchen' }), 'bank')
    expect(document.querySelector('.ueb-none')).toBeNull()
  })

  it('is not there when the lifter has the whole list', () => {
    mount()
    expect(part()).toBeNull()
  })
})

describe('one search over both parts', () => {
  const groups = [{ name: 'Brust', entries: [
    entry(1, 'Bankdrücken (Langhantel)', 'Bench Press'),
    entry(2, 'Butterfly (Maschine)', 'Pec Deck'),
  ] }]
  const type = async (text: string) => {
    const field = screen.getByRole('searchbox', { name: 'Übungen durchsuchen' })
    await userEvent.clear(field)
    await userEvent.type(field, text)
  }
  const status = () => [...document.querySelectorAll('p.sr-only[role="status"]')]
    .map((p) => p.textContent)

  it('shows each part its hits, opened, and says the counts', async () => {
    mount({ groups, library: LIBRARY })
    expect(status()).toEqual([''])
    await type('bench press')
    expect(screen.getByRole('heading', { level: 2, name: 'Deine 1' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Noch nie gemacht 1' })).toBeInTheDocument()
    expect(document.getElementById('g-Brust')).toHaveTextContent('1 von 2')
    expect(document.getElementById('n-Brust')).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById('n-Brust')).toHaveTextContent('1 von 1')
    expect(screen.getByRole('link', { name: 'Schrägbankdrücken Langhantel' }))
      .toHaveAttribute('href', '/gym/exercises/30')
    // No lead while searching: the hits are the point.
    expect(document.querySelector('.ueb-part--nie .ueb-part__lead')).toBeNull()
    expect(status()).toEqual(['1 eigene, 1 aus der Liste'])
  })

  it('drops a part without hits, and says none only when neither has one', async () => {
    mount({ groups, library: LIBRARY })
    await type('squat')
    expect(screen.queryByRole('heading', { level: 2, name: /^Deine/ })).toBeNull()
    expect(screen.getByRole('heading', { level: 2, name: 'Noch nie gemacht 2' })).toBeInTheDocument()
    expect(document.getElementById('n-Beine')).toHaveTextContent('2 von 3')
    expect(status()).toEqual(['0 eigene, 2 aus der Liste'])
    await type('pec deck')
    expect(document.querySelector('.ueb-part--nie')).toBeNull()
    await type('zumba')
    expect(document.querySelector('.ueb-part')).toBeNull()
    expect(screen.getByText(/Keine Übung gefunden für/)).toHaveTextContent('Keine Übung gefunden für zumba.')
  })

  it('searches both at one tier: an exact hit in one part hides the other\'s loose ones', async () => {
    // "calf raise" runs whole in the list's Wadenheben; yours hold both
    // words apart, which is a hit only when nothing runs whole.
    mount({ groups: [{ name: 'Waden', entries: [entry(3, 'Wadenheben (Maschine)', 'Raise Calf')] }],
      library: LIBRARY })
    await type('calf raise')
    expect(screen.queryByText('Wadenheben (Maschine)')).toBeNull()
    expect(screen.getByRole('link', { name: 'Wadenheben stehend' })).toBeInTheDocument()
  })

  it('says a typo\'s near misses once, over both parts', async () => {
    mount({ groups, library: LIBRARY })
    await type('Bankdrüken')
    expect(screen.getByText('Bankdrücken (Langhantel)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Schrägbankdrücken Langhantel' })).toBeInTheDocument()
    expect(screen.getAllByText(/Kein genauer Treffer/)).toHaveLength(1)
  })

  it('opens with Enter the first row as shown: yours, else the rest\'s', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, set href(url: string) { assign(url) } })
    mount({ groups, library: LIBRARY })
    // Yours and the rest's: yours.
    await type('bench press{Enter}')
    expect(assign).toHaveBeenLastCalledWith('/gym/exercises/1')
    // None of yours: the rest's first as it shows -- Beinstrecker before
    // Kniebeugen, though the list sends the Smith squat first.
    await type('beine maschine{Enter}')
    expect(assign).toHaveBeenCalledTimes(2)
    expect(assign).toHaveBeenLastCalledWith('/gym/exercises/12')
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

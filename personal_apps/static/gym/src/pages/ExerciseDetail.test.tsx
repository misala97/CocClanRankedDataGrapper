import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ExerciseDetailPage } from './ExerciseDetail'
import type { ExerciseDetailPayload, ExerciseMeta, SessionRow } from '../types'

/** The first mention of the 1RM a reader meets -- text or aria-label, in
 *  document order. D16: it is the one that names it in full. */
function firstOneRm(root: HTMLElement): string | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const said = node.nodeType === Node.TEXT_NODE
      ? node.textContent
      : (node as Element).getAttribute('aria-label')
    if (said?.includes('1RM')) return said
  }
  return null
}

function payload(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return {
    exercise: {
      id: 1, name: 'Bankdrücken', muscle_group: 'Brust', is_unilateral: false,
      default_rest_seconds: 90, weight_increment: 2.5, equipment: 'barbell',
      bar_weight: 20, stack_kg: null, secondary_muscle_groups: null,
      list_defaults: {
        default_rest_seconds: 90, weight_increment: 2.5, bar_weight: 20, stack_kg: null,
      },
      own: [], rest_for_all: null,
    },
    table: [], series: [], available_positions: [], selected_position: null,
    selected_position_is_default: false, selected_position_reason: null,
    last_overall: null, pr_weight: null, pr_e1rm: null, last_progression: null,
    state: null, sessions_since_pr: null, chart: null,
    chip_class: null, chip_label: null,
    equipment_labels: { barbell: 'Langhantel', stack: 'Stack', dumbbell: 'Kurzhantel' },
    ...over,
  }
}

/** A stack the lifter set up: their own step, rest and stops over the list's. */
const stackExercise: ExerciseMeta = {
  ...payload().exercise, name: 'Latzug (Kabel)', muscle_group: 'Rücken', equipment: 'stack',
  weight_increment: 5, default_rest_seconds: 120, bar_weight: null, stack_kg: [5, 13, 21],
  list_defaults: {
    default_rest_seconds: 90, weight_increment: 2.5, bar_weight: null, stack_kg: null,
  },
  own: ['default_rest_seconds', 'stack_kg', 'weight_increment'],
}

function row(over: Partial<SessionRow> = {}): SessionRow {
  return {
    session_id: 7, started_at: '2026-08-01T18:30:00', position: 2,
    is_deload: false, is_record: false, sets_display: '3 × 8', best_weight: 80,
    volume: 1920, e1rm: 100, ...over,
  }
}

describe('ExerciseDetailPage', () => {
  it('names the exercise as the h1', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bankdrücken')
  })

  it('shows the empty state when nothing is logged', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.getByText(/Noch keine Sätze protokolliert/)).toHaveTextContent(
      'Noch keine Sätze protokolliert. Sobald du diese Übung in einem Workout loggst, stehen '
      + 'hier Rekorde, der Verlauf deines geschätzten Maximums (1RM) und jedes einzelne Workout.')
    expect(screen.queryByText('Workouts')).not.toBeInTheDocument()
  })

  it('formats volume with a German thousands separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.getByText('1.920')).toBeInTheDocument()
  })

  it('formats weights with a comma decimal separator', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.getByText('1RM 100,0')).toBeInTheDocument()
  })

  it('scopes the session count to the selected position', () => {
    // Queried through the chart section rather than by text: "Pos. 2 ·" also
    // appears in every row's meta line, and the point of this assertion is
    // that the CHART's count says what it is counting.
    const { container } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], selected_position: 2, available_positions: [1, 2],
      })} />)
    const head = container.querySelector('.sec--chart .sec__head')!
    expect(head.textContent).toContain('Pos. 2 · 1 Workout')
  })

  it('pluralises Workout correctly', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row(), row({ session_id: 8 })] })} />)
    expect(screen.getByText(/2 Workouts/)).toBeInTheDocument()
  })

  it('offers position pills only when more than one slot exists', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [2] })} />)
    expect(screen.queryByText('Alle')).not.toBeInTheDocument()

    rerender(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })} />)
    expect(screen.getByText('Alle')).toBeInTheDocument()
    expect(screen.getByText('Position 1')).toBeInTheDocument()
  })

  it('pills are real links, so deep links and the back button keep working', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row()], available_positions: [1, 2] })} />)
    expect(screen.getByText('Alle')).toHaveAttribute('href', '/gym/exercises/1?position=all')
    expect(screen.getByText('Position 1')).toHaveAttribute('href', '/gym/exercises/1?position=1')
  })

  it('explains a slot the page chose rather than one the reader picked', () => {
    const { rerender } = render(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: true, selected_position_reason: 'strongest',
      })} />)
    expect(screen.getByText(/die stärkste mit mindestens zwei Workouts/)).toBeInTheDocument()

    // Explicitly chosen -- no explanation, because the reader made the choice.
    rerender(<ExerciseDetailPage
      payload={payload({
        table: [row()], available_positions: [1, 2], selected_position: 2,
        selected_position_is_default: false, selected_position_reason: null,
      })} />)
    expect(screen.queryByText(/die stärkste/)).not.toBeInTheDocument()
  })

  it('tags every row the server marks as a record, an overtaken one too', () => {
    // Same day, and the older record since beaten: the tag is the server's
    // per-row mark (D3), not a match against the one best set.
    const rows = [
      row({ session_id: 9, e1rm: 104, is_record: true }),
      row({ session_id: 8, e1rm: 90, volume: 2200 }),
      row({ session_id: 7, e1rm: 100, is_record: true }),
    ]
    render(<ExerciseDetailPage
      payload={payload({
        table: rows,
        pr_e1rm: {
          e1rm: 104, weight: 84, reps: 5, session_id: 9,
          started_at: '2026-08-01T18:30:00', position: 2,
        },
      })} />)
    expect(screen.getAllByText('Rekord')).toHaveLength(2)
  })

  it('labels deload rows', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row({ is_deload: true })] })} />)
    expect(screen.getByText('Deload')).toBeInTheDocument()
  })

  it('says what a record is, and lets a deload row hold one (G-078)', () => {
    render(<ExerciseDetailPage
      payload={payload({ table: [row({ is_deload: true, is_record: true })] })} />)
    expect(screen.getByText(/Rekord heißt: das beste 1RM bis zu diesem Tag\./))
      .toBeInTheDocument()
    expect(screen.queryByText(/keine Rekorde/)).not.toBeInTheDocument()
    expect(screen.getByText('Rekord')).toBeInTheDocument()
    expect(screen.getByText('Deload')).toBeInTheDocument()
  })

  it('names the 1RM in full once, and counts in workouts and records (D16)', () => {
    const { container } = render(<ExerciseDetailPage payload={payload({
      exercise: { ...payload().exercise, muscle_group: null, is_unilateral: true },
      table: [row()],
      pr_e1rm: {
        e1rm: 104, weight: 84, reps: 5, session_id: 9,
        started_at: '2026-08-01T18:30:00', position: 2,
      },
      sessions_since_pr: 3,
    })} />)
    expect(screen.getByText('Bestes geschätztes Maximum (1RM)')).toBeInTheDocument()
    expect(firstOneRm(container)).toBe('Bestes geschätztes Maximum (1RM)')
    expect(screen.getByText('Seit 3 Workouts kein neuer Rekord')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Verlauf 1RM' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Workouts' })).toBeInTheDocument()
    // Per side, not "einseitig": a dumbbell press is two-sided (G-039).
    const sub = container.querySelector('.exdetail__sub')
    expect(sub).toHaveTextContent('Ohne Muskelgruppe')
    expect(sub).toHaveTextContent('Gewicht je Seite')
    // Not "je Hantel": a one-sided cable or machine logs per side too.
    expect(screen.getByText(
      'Gewicht je Seite geloggt; das Volumen zählt beide Seiten (×2).',
    )).toBeInTheDocument()
  })

  it('names the 1RM in full in the heading when no set earned the tile', () => {
    // Every set past 12 reps: no best e1RM to show, and the chart still
    // plots an estimate, so the heading is the first mention.
    const { container } = render(<ExerciseDetailPage
      payload={payload({ table: [row()], pr_e1rm: null })} />)
    expect(screen.getByRole('heading', { name: 'Verlauf des geschätzten Maximums (1RM)' }))
      .toBeInTheDocument()
    expect(firstOneRm(container)).toBe('Verlauf des geschätzten Maximums (1RM)')
  })

  it('counts a workout once when the exercise sat at two positions in it', () => {
    render(<ExerciseDetailPage payload={payload({
      table: [row({ session_id: 5, position: 1 }), row({ session_id: 5, position: 4 }),
        row({ session_id: 6, position: 1 })],
    })} />)
    expect(screen.getByText('2 Workouts')).toBeInTheDocument()
  })

  it('says why there is no best yet when no set had a weight', () => {
    // Deloads no longer explain an empty band: they hold records (G-078).
    render(<ExerciseDetailPage
      payload={payload({ table: [row({ best_weight: 0, e1rm: 0, volume: 0 })] })} />)
    expect(screen.getByText('Noch kein Bestwert — bisher nur Sätze ohne Gewicht.'))
      .toBeInTheDocument()
  })

  it('offers no way to delete the exercise: the list is everyone\'s', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row()] })} />)
    expect(screen.queryByText(/löschen/i)).not.toBeInTheDocument()
  })

  it('opens the settings from the maintenance button', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload()} />)

    const dialog = document.querySelector('dialog')!
    expect(dialog.open).toBe(false)
    await user.click(screen.getByText(/Pause und Schritt einstellen/))
    expect(dialog.open).toBe(true)
    expect(within(dialog).getByRole('heading', { name: 'Deine Einstellungen' })).toBeInTheDocument()
  })

  it('opens on the settings when "Deine Pause" links an exception here', () => {
    // The hash is dropped once used: a reload lands on the page itself.
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload()} />)
    expect(document.querySelector('dialog')!.open).toBe(true)
    expect(window.location.hash).toBe('')
  })
})

describe('Deine Einstellungen', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  /** The sheet open on `exercise`, with the server answering `answer`. */
  function sheet(exercise: ExerciseMeta, answer?: (fields: FormData) => ExerciseMeta | Error) {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const fields = init.body as FormData
      const reply = answer?.(fields) ?? exercise
      if (reply instanceof Error) throw reply
      return { ok: true, status: 200, json: async () => reply } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload({ exercise })} />)
    return { fetchMock, dialog: within(document.querySelector('dialog')!) }
  }

  const setting = (name: string) =>
    within(screen.getByRole('heading', { name }).closest('section')!)

  it('says where each value comes from, and marks what it falls back to', () => {
    sheet(stackExercise)
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Deine')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['0:30', '1:00', '1:30Standard', '2:00', '2:30', 'Andere'])
    expect(rest.getByRole('button', { name: '2:00' })).toHaveAttribute('aria-pressed', 'true')

    const step = setting('Schritt bei + und − (kg)')
    expect(step.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['2,5Standard', '5', '7', '8', '10', 'Andere'])
    expect(step.getByRole('button', { name: '5' })).toHaveAttribute('aria-pressed', 'true')

    const stops = setting('Gewichtsstufen')
    expect(stops.getByText('5, 13, 21')).toBeInTheDocument()
    expect(stops.getByRole('button', { name: 'Gewichtsstufen ändern' })).toBeInTheDocument()
    expect(stops.getByRole('button', { name: 'Wieder gleichmäßig' })).toBeInTheDocument()
  })

  it('goes back to the standard stops by that name', () => {
    sheet({ ...stackExercise,
      list_defaults: { ...stackExercise.list_defaults, stack_kg: [5, 10, 15] } })
    expect(setting('Gewichtsstufen').getByRole('button', { name: 'Zurück zum Standard' }))
      .toBeInTheDocument()
  })

  it('asks for a bar only where the list knows one, and stops only on a stack', () => {
    sheet(payload().exercise)
    const bar = setting('Stangengewicht (kg)')
    expect(bar.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['Ohne', '10', '15', '20Standard', '25', 'Andere'])
    expect(screen.queryByRole('heading', { name: 'Gewichtsstufen' })).toBeNull()
  })

  it('never asks a stack for a bar', () => {
    sheet(stackExercise)
    expect(screen.queryByRole('heading', { name: 'Stangengewicht (kg)' })).toBeNull()
  })

  it('saves a tap at once, one field, and shows it as the lifter\'s', async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(payload().exercise, (fields) => ({
      ...payload().exercise, default_rest_seconds: Number(fields.get('default_rest_seconds')),
      own: ['default_rest_seconds'],
    }))
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Standard', { selector: '.setting__src' })).toBeInTheDocument()

    await user.click(rest.getByRole('button', { name: '2:30' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/gym/exercises/1/update')
    expect([...(init.body as FormData).entries()]).toEqual([['default_rest_seconds', '150']])
    expect(rest.getByRole('button', { name: '2:30' })).toHaveAttribute('aria-pressed', 'true')
    expect(await rest.findByText('Deine')).toBeInTheDocument()
  })

  it('goes back to the standard in one tap', async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(stackExercise, () => ({
      ...stackExercise, default_rest_seconds: 90,
      own: stackExercise.own.filter((f) => f !== 'default_rest_seconds'),
    }))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '1:30 Standard' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['default_rest_seconds', '90']])
    expect(rest.getByText('Standard', { selector: '.setting__src' })).toBeInTheDocument()
  })

  it('puts the value back and says why when a save fails', async () => {
    const user = userEvent.setup()
    sheet(payload().exercise, () => new TypeError('Failed to fetch'))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '2:30' }))
    expect(await screen.findByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.')
    expect(rest.getByRole('button', { name: '1:30 Standard' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('falls back to the rest for all, and calls an own rest an exception', () => {
    sheet({ ...payload().exercise, default_rest_seconds: 180, rest_for_all: 150,
      own: ['default_rest_seconds'] })
    expect(screen.getByText('Nur für dich. Ohne Ausnahme gilt deine Pause, 2:30.'))
      .toBeInTheDocument()
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Ausnahme')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['1:30', '2:00', '2:30Deine', '3:00', '3:30', 'Andere'])
  })

  it('says a rest that is not its own follows the rest for all', () => {
    sheet({ ...payload().exercise, default_rest_seconds: 150, rest_for_all: 150, own: [] })
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Wie deine Pause', { selector: '.setting__src' })).toBeInTheDocument()
  })

  it('takes a machine\'s own stops typed once, and only a list of them', async () => {
    const user = userEvent.setup()
    const even = { ...stackExercise, stack_kg: null,
      own: stackExercise.own.filter((f) => f !== 'stack_kg') }
    const { fetchMock } = sheet(even)
    const stops = setting('Gewichtsstufen')
    // The step, not a ladder from 0: a real stack starts where it starts (G-042).
    expect(stops.getByText('Gleichmäßig, in Schritten von 5 kg.')).toBeInTheDocument()

    await user.click(stops.getByRole('button', { name: 'Das Gerät hat andere Gewichtsstufen' }))
    const field = stops.getByLabelText(/Jede Gewichtsstufe in kg/)
    await user.type(field, '12')
    expect(stops.getByRole('button', { name: 'Übernehmen' })).toBeDisabled()
    await user.type(field, ', 5; 19')
    await user.click(stops.getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['stack_kg', '5, 12, 19']])
  })
})

describe('the position pills (G-150)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    history.replaceState(null, '', '/')
  })

  const served = payload({ table: [row()], available_positions: [1, 2] })
  const at = (position: number) => payload({
    table: [row({ position, session_id: 10 + position })], available_positions: [1, 2],
    selected_position: position,
  })
  /** The chart's count, which names the position it is scoped to. */
  const scope = (position: number) =>
    screen.queryByText(new RegExp(`^Pos\\. ${position} · \\d+ Workouts?$`))

  /** A server that answers each position when the test says so. */
  function server() {
    const waiting = new Map<string, (body: ExerciseDetailPayload) => void>()
    const fetchMock = vi.fn((url: string) => new Promise<Response>((resolve) => {
      const position = new URL(url, window.location.href).searchParams.get('position')!
      waiting.set(position, (body) => resolve({
        ok: true, status: 200, redirected: false, url, json: async () => body,
      } as Response))
    }))
    vi.stubGlobal('fetch', fetchMock)
    return { fetchMock, answer: (position: string, body: ExerciseDetailPayload) => waiting.get(position)!(body) }
  }

  it('shows the pill tapped last, whatever order the answers come in', async () => {
    const { answer } = server()
    render(<ExerciseDetailPage payload={served} />)
    await userEvent.click(screen.getByText('Position 1'))
    await userEvent.click(screen.getByText('Position 2'))
    answer('2', at(2))
    await waitFor(() => expect(scope(2)).toBeInTheDocument())
    answer('1', at(1))
    await new Promise((settle) => setTimeout(settle, 0))
    expect(scope(2)).toBeInTheDocument()
    expect(window.location.search).toBe('?position=2')
  })

  it('asks for a position once', async () => {
    const { fetchMock, answer } = server()
    render(<ExerciseDetailPage payload={served} />)
    await userEvent.click(screen.getByText('Position 1'))
    answer('1', at(1))
    await waitFor(() => expect(scope(1)).toBeInTheDocument())
    await userEvent.click(screen.getByText('Position 2'))
    answer('2', at(2))
    await waitFor(() => expect(scope(2)).toBeInTheDocument())
    await userEvent.click(screen.getByText('Position 1'))
    await waitFor(() => expect(scope(1)).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('goes back to the page as it was served, without asking', async () => {
    const { fetchMock, answer } = server()
    render(<ExerciseDetailPage payload={served} />)
    await userEvent.click(screen.getByText('Position 2'))
    answer('2', at(2))
    await waitFor(() => expect(scope(2)).toBeInTheDocument())

    history.replaceState(null, '', '/gym/exercises/1')
    window.dispatchEvent(new PopStateEvent('popstate'))
    await waitFor(() => expect(scope(2)).toBeNull())
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('asks for "Alle" on a page served on its default slot', async () => {
    // A bare URL is the server's pick, not every position: the page opened
    // on Position 1 has not shown "Alle" yet (G-037).
    const { fetchMock, answer } = server()
    history.replaceState(null, '', '/gym/exercises/1')
    render(<ExerciseDetailPage payload={at(1)} />)
    await userEvent.click(screen.getByText('Alle'))
    expect(fetchMock).toHaveBeenCalledOnce()
    answer('all', served)
    await waitFor(() => expect(scope(1)).toBeNull())
    expect(window.location.search).toBe('?position=all')
  })

  it('leaves a failed answer alone once a later tap has taken over', async () => {
    // The latest tap's failure falls back to the link; an earlier one's
    // would navigate away from the pill tapped since.
    const moved: string[] = []
    const answers = new Map<string, { ok: (body: ExerciseDetailPayload) => void, fail: () => void }>()
    vi.stubGlobal('fetch', vi.fn((url: string) => new Promise<Response>((resolve, reject) => {
      const position = new URL(url, 'http://localhost').searchParams.get('position')!
      answers.set(position, {
        ok: (body) => resolve({
          ok: true, status: 200, redirected: false, url, json: async () => body,
        } as Response),
        fail: () => reject(new TypeError('Failed to fetch')),
      })
    })))
    vi.stubGlobal('location', { ...window.location, search: '', set href(url: string) { moved.push(url) } })
    render(<ExerciseDetailPage payload={served} />)
    await userEvent.click(screen.getByText('Position 1'))
    await userEvent.click(screen.getByText('Position 2'))
    answers.get('1')!.fail()
    answers.get('2')!.ok(at(2))
    await waitFor(() => expect(scope(2)).toBeInTheDocument())
    expect(moved).toEqual([])
  })
})

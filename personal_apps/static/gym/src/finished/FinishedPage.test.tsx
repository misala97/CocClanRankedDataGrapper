import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FinishedPage } from './FinishedPage'
import type { FinishedExercise, FinishedPayload, SessionRecord } from './types'
import { useSheets } from '../session/stores'
import { useUndo } from '../undo'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const exercise = (over: Partial<FinishedExercise> = {}): FinishedExercise => ({
  exercise_id: 10, name: 'Bankdrücken', position: 1,
  sets: [[60, 8], [60, 8]], sets_display: '2 × 60 kg', volume: 960,
  best_weight: 60, e1rm: 75, has_history: true, avg_volume: 900,
  volume_delta_pct: 7, is_record: false,
  sessions_since_pr: 2, verdict: null,
  set_rows: [{ id: 501, weight: 60, reps: 8 }, { id: 502, weight: 60, reps: 8 }],
  session_exercise_id: 90, notes: null, pain: false, ...over,
})

const record = (over: Partial<SessionRecord> = {}): SessionRecord => ({
  kind: 'e1rm', name: 'Bankdrücken', exercise_id: 10, position: 1,
  value: 72.5, previous: 70, previous_at: '2026-07-20T10:00:00', ...over,
})

const base: FinishedPayload = {
  session: {
    id: 42, name: 'Push Day',
    started_at: '2026-08-09T16:00:00', finished_at: '2026-08-09T17:05:00',
    is_deload: false, deload_pct: null, bodyweight_kg: null, notes: null,
    template_id: null, template_name: null,
  },
  exercises: [exercise()],
  total_volume: 12345,
  total_sets: 2,
  avg_total_volume: 11000,
  total_volume_delta_pct: 7,
  records: [],
  record_count: 0,
  advice: [],
  is_deload: false,
  deload_default_pct: 60,
  deload_applied: false,
  previous_session: null,
  tick_states: ['done', 'done'],
  set_pace_seconds: null,
  unlogged: [],
  weekday_short: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
  just_finished: false,
  template_exercises: null,
  template_next_exercises: null,
}

const mount = (over: Partial<FinishedPayload> = {}) =>
  render(<FinishedPage payload={{ ...base, ...over }} />)

const deload = (over: Partial<FinishedPayload> = {}): Partial<FinishedPayload> => ({
  session: { ...base.session, is_deload: true, deload_pct: 70 },
  is_deload: true, ...over,
})

/**
 * The markup half of the finished-page tests that used to live in the Python
 * suite: those now assert on the payload the server embeds, and the rendering
 * they grepped for is asserted here.
 */
describe('FinishedPage', () => {
  it('heads with the session, its date and its duration', () => {
    mount()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Push Day')
    // Weekday first, then the date once -- the name often embeds one already.
    expect(screen.getByText(/So · 09\.08\.2026 · 65 Minuten/)).toBeInTheDocument()
  })

  describe('the verdict', () => {
    it('leads with records when there are any', () => {
      mount({ records: [record()], record_count: 1 })
      expect(screen.getByText('1 neuer Rekord.')).toBeInTheDocument()
      mount({ records: [record(), record({ name: 'Dips', exercise_id: 11 })], record_count: 2 })
      expect(screen.getByText('2 neue Rekorde.')).toBeInTheDocument()
    })

    it('says an empty workout does not count', () => {
      mount({ total_sets: 0, exercises: [], tick_states: [] })
      expect(screen.getByText(/Kein Satz erfasst/)).toBeInTheDocument()
    })

    it('reads a deload as deliberate rather than as a shortfall', () => {
      // Ordering matters: without this branch before every volume branch, a
      // deload that worked exactly as intended reads as a bad day.
      mount({ ...deload(), deload_applied: true, total_volume_delta_pct: -40 })
      expect(screen.getByText('Deload — 70 %. Bewusst leichter.')).toBeInTheDocument()
    })

    it('drops the percentage when the weights were never scaled', () => {
      mount({ ...deload(), deload_applied: false })
      expect(screen.getByText('Als Deload markiert. Bewusst leichter.')).toBeInTheDocument()
    })

    it('has a ±15 % dead band, not ±5 %', () => {
      // At ±5 % an ordinary Tuesday was headlined in 28px display type.
      mount({ total_volume_delta_pct: 12 })
      expect(screen.getByText('Im gewohnten Rahmen.')).toBeInTheDocument()
      mount({ total_volume_delta_pct: 18 })
      expect(screen.getByText('+18 % über deinem Schnitt.')).toBeInTheDocument()
    })

    it('states the low comparison rather than judging it', () => {
      mount({ total_volume_delta_pct: -22 })
      expect(screen.getByText('22 % unter deinem Schnitt für dieses Workout.'))
        .toBeInTheDocument()
    })

    it('falls back to the set count with nothing to compare against', () => {
      mount({ total_volume_delta_pct: null, avg_total_volume: null })
      expect(screen.getByText('2 Sätze erledigt.')).toBeInTheDocument()
      mount({ total_volume_delta_pct: null, avg_total_volume: null, total_sets: 1 })
      expect(screen.getByText('1 Satz erledigt.')).toBeInTheDocument()
    })
  })

  describe('the tick strip', () => {
    it('counts the gold ticks in its label, not the records', () => {
      // 21 ticks with 1 gold once announced "davon 3 mit Rekord": the label
      // counted records while the strip shows record SETS.
      mount({ tick_states: ['done', 'record', 'done'], total_sets: 3,
              records: [record()], record_count: 1 })
      expect(screen.getByRole('img'))
        .toHaveAccessibleName('3 Sätze erledigt, davon 1 mit Rekord')
    })

    it('says nothing about records when none earned a tick', () => {
      mount()
      expect(screen.getByRole('img')).toHaveAccessibleName('2 Sätze erledigt')
    })
  })

  describe('the volume block', () => {
    it('names the baseline in words', () => {
      mount()
      expect(screen.getByText('12.345')).toBeInTheDocument()
      expect(screen.getByText('+7 % zum Schnitt dieses Workouts')).toBeInTheDocument()
    })

    it('says nothing about the average on a deload', () => {
      // The pill and the verdict have both already said it, and the long
      // string wrapped "kg bewegt" onto two lines beside the figure.
      mount({ ...deload(), total_volume_delta_pct: -40 })
      expect(screen.queryByText(/zum Schnitt/)).not.toBeInTheDocument()
    })

    it('shows the mean it quotes a percentage of', () => {
      // "+34 % ggü. Ø" was a percentage of a number the reader could not see.
      const { container } = mount()
      expect(container.querySelector('.finished__prev'))
        .toHaveTextContent('Schnitt dieses Workouts 11.000 kg')
    })

    it('puts last time next to the mean', () => {
      mount({
        previous_session: { id: 7, started_at: '2026-08-02T16:00:00', volume: 11500 },
      })
      const line = screen.getByText(/Letztes Mal/)
      expect(line).toHaveTextContent('11.500 kg am 02.08.')
      expect(line).toHaveTextContent('Schnitt 11.000 kg')
      expect(within(line).getByRole('link')).toHaveAttribute('href', '/gym/session/7')
    })

    it('is suppressed entirely at zero sets', () => {
      // The verdict directly above says this workout does not count, and the
      // page then scored it "-100 %" over a band of three zeroes.
      mount({ total_sets: 0, exercises: [], tick_states: [] })
      expect(screen.queryByText('kg bewegt')).not.toBeInTheDocument()
      expect(screen.queryByText(/zum Schnitt/)).not.toBeInTheDocument()
    })
  })

  describe('records', () => {
    it('flares exactly one, however many there are', () => {
      // It used to loop: six records meant six identical full-bleed gold slabs.
      mount({
        records: [record(), record({ name: 'Dips', exercise_id: 11 }),
          record({ name: 'Rudern', exercise_id: 12 })],
        record_count: 3,
      })
      expect(screen.getAllByText(/Neuer .*-Rekord/)).toHaveLength(1)
      expect(screen.getByText('Neuer e1RM-Rekord')).toBeInTheDocument()
      // The rest become quiet rows.
      const others = screen.getByRole('region', { name: 'Weitere Rekorde' })
      expect(within(others).getAllByRole('link')).toHaveLength(2)
    })

    it('celebrates on arrival, not on every later visit', () => {
      const { container } = mount({ records: [record()], record_count: 1 })
      expect(container.querySelector('.record-flare')).not.toHaveClass('is-fresh')
      const fresh = mount({ records: [record()], record_count: 1, just_finished: true })
      expect(fresh.container.querySelector('.record-flare')).toHaveClass('is-fresh')
    })

    it('states what the record beat', () => {
      mount({ records: [record()], record_count: 1 })
      expect(screen.getByText('72,5')).toBeInTheDocument()
      expect(screen.getByText(/vorher 70,0 kg · 20\.07\.2026 · als 1\. Übung/))
        .toBeInTheDocument()
    })
  })

  it('prescribes a heavier weight for a plateau', () => {
    mount({
      advice: [{
        exercise_id: 10, name: 'Bankdrücken', stuck_at: 63.5,
        sessions: 3, suggested_weight: 68,
      }],
    })
    const line = screen.getByText(/steht seit 3 Einheiten auf/)
    expect(line).toHaveTextContent('63,5 kg — auf 68,0 kg gehen, notfalls 2 Wdh. weniger.')
  })

  describe('the per-exercise list', () => {
    it('tags each verdict', () => {
      mount({
        exercises: [
          exercise({ position: 1, verdict: 'rekord' }),
          exercise({ position: 2, verdict: 'stagniert', sessions_since_pr: 4 }),
          exercise({ position: 3, verdict: 'steigend', volume_delta_pct: 12 }),
          exercise({ position: 4, verdict: 'neu' }),
        ],
      })
      expect(screen.getByText('Rekord')).toBeInTheDocument()
      expect(screen.getByText('4 ohne PR')).toBeInTheDocument()
      expect(screen.getByText('+12 % Vol.')).toBeInTheDocument()
      expect(screen.getByText('Erste Aufzeichnung')).toBeInTheDocument()
    })

    it('carries no tag on a deload, where every verdict is null', () => {
      mount(deload())
      const list = screen.getByRole('region', { name: 'Nach Übung' })
      expect(within(list).queryByText('Rekord')).not.toBeInTheDocument()
    })

    it('says so when nothing was completed', () => {
      mount({ exercises: [], total_sets: 0, tick_states: [] })
      expect(screen.getByText('Keine erledigten Sätze in diesem Workout.'))
        .toBeInTheDocument()
    })
  })

  describe('the correction sheet', () => {
    it('edits the real set rows', async () => {
      mount()
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      const forms = within(sheet).getAllByRole('button', { name: /Satz \d speichern/ })
      expect(forms).toHaveLength(2)
      expect(forms[0]!.closest('form')).toHaveAttribute('action', '/gym/set/501/update')
      expect(forms[1]!.closest('form')).toHaveAttribute('action', '/gym/set/502/update')
    })

    it('carries the note and the pain flag', async () => {
      mount({ exercises: [exercise({ notes: 'Knie zwickt', pain: true })] })
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      expect(within(sheet).getByRole('checkbox', { name: /Schmerz/ })).toBeChecked()
      expect(within(sheet).getByLabelText('Notiz')).toHaveValue('Knie zwickt')
    })

    it('offers no note form for an exercise with no session row behind it', async () => {
      mount({ exercises: [exercise({ session_exercise_id: null })] })
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      expect(within(sheet).queryByRole('checkbox')).not.toBeInTheDocument()
    })
  })

  it('offers bodyweight and a session note, which only this screen can edit', async () => {
    mount({ session: { ...base.session, bodyweight_kg: 91.4, notes: 'nach Feierabend' } })
    await userEvent.click(screen.getByRole('button', { name: /Körpergewicht/ }))
    const sheet = screen.getByRole('dialog')
    expect(within(sheet).getByLabelText(/Körpergewicht/)).toHaveValue(91.4)
    expect(within(sheet).getByLabelText('Notiz')).toHaveValue('nach Feierabend')
  })

  describe('the template prompt', () => {
    it('offers to save a freeform workout as a template', () => {
      mount({ just_finished: true })
      expect(screen.getByText('Dieses Workout als Routine speichern?')).toBeInTheDocument()
      const input = screen.getByLabelText('Name der neuen Routine')
      // template_name, not name: gym_save_as_template reads the former, and
      // the route redirects identically whether it saved anything or not.
      expect(input).toHaveAttribute('name', 'template_name')
      expect(input.closest('form'))
        .toHaveAttribute('action', '/gym/session/42/save_as_template')
    })

    it('offers to update the routine a template workout came from', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        // A real difference -- with none, the prompt (rightly) does not exist.
        template_exercises: ['Dips'],
        template_next_exercises: ['Bankdrücken'],
      })
      expect(screen.getByText(/mit dieser Übungsliste und Reihenfolge aktualisieren/))
        .toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Routine aktualisieren' }).closest('form'))
        .toHaveAttribute('action', '/gym/session/42/update_template')
    })

    it('states what the update would change', () => {
      // The rendered diff that replaced the blind confirm(). Both halves are
      // server-computed: the "after" is what the update route would actually
      // write, not the performed list.
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        template_exercises: ['Dips'],
        template_next_exercises: ['Bankdrücken'],
      })
      const diff = document.querySelector('.prompt__diff')!
      expect(diff.textContent).toContain('Neu: Bankdrücken.')
      expect(diff.textContent).toContain('Entfällt: Dips.')
    })

    it('names a pure reorder as such', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        template_exercises: ['Dips', 'Bankdrücken'],
        template_next_exercises: ['Bankdrücken', 'Dips'],
      })
      expect(document.querySelector('.prompt__diff')!.textContent)
        .toBe('Nur die Reihenfolge ändert sich.')
    })

    it('disappears when the update would change nothing', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        template_exercises: ['Bankdrücken'],
        template_next_exercises: ['Bankdrücken'],
      })
      expect(screen.queryByText(/mit dieser Übungsliste und Reihenfolge aktualisieren/))
        .not.toBeInTheDocument()
    })

    it('is absent on a later visit and on an empty workout', () => {
      mount()
      expect(screen.queryByText(/als Routine speichern/)).not.toBeInTheDocument()
      mount({ just_finished: true, total_sets: 0, exercises: [], tick_states: [] })
      expect(screen.queryByText(/als Routine speichern/)).not.toBeInTheDocument()
    })
  })

  describe('measured pace', () => {
    // Pace per set, not "Pause": the gap between two logged sets includes the
    // set itself, so the old total claimed nearly the whole workout as rest.
    it('reports what it counted, per set', () => {
      mount({ set_pace_seconds: 185 })
      expect(screen.getByText('Ø 3:05 min pro Satz')).toBeInTheDocument()
      expect(screen.queryByText(/Pause/)).not.toBeInTheDocument()
    })

    it('says nothing without timestamps to build it from', () => {
      mount({ set_pace_seconds: null })
      expect(screen.queryByText(/pro Satz/)).not.toBeInTheDocument()
    })
  })

  it('keeps a replaced original and its substitute apart in one slot', () => {
    // B3 review: both sit at position 1, and the position was the key.
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    mount({ exercises: [
      exercise({ session_exercise_id: 90 }),
      exercise({ exercise_id: 11, name: 'Schrägbankdrücken', session_exercise_id: 91,
                 set_rows: [{ id: 503, weight: 50, reps: 8 }] }),
    ] })
    expect(screen.getAllByText('Bankdrücken').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Schrägbankdrücken').length).toBeGreaterThan(0)
    expect(errors.mock.calls.flat().join(' ')).not.toMatch(/same key/)
    errors.mockRestore()
  })

  it('keeps deleting a workout quiet', () => {
    mount()
    const del = screen.getByRole('button', { name: 'Workout löschen' })
    expect(del).toHaveClass('quiet-acts__btn--danger')
    // Not one of the two ways out of this screen.
    expect(screen.getByRole('link', { name: 'Zum Start' })).toHaveAttribute('href', '/gym')
    expect(screen.getByRole('link', { name: 'Verlauf' })).toHaveAttribute('href', '/gym/verlauf')
  })
})

describe('saving without a reload', () => {
  const fetchPayload = (over: Partial<FinishedPayload>) =>
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ ...base, ...over }),
    } as unknown as Response))

  it('posts the correction and re-renders from the answer, sheet still open', async () => {
    const fresh = exercise({ sets_display: '2 × 65 kg', set_rows: [
      { id: 501, weight: 65, reps: 8 }, { id: 502, weight: 60, reps: 8 },
    ] })
    // just_finished true in the ANSWER: the client must overwrite it with its
    // own, because a POST carries no ?just_finished and the flare belongs to
    // the visit.
    vi.stubGlobal('fetch', fetchPayload({ exercises: [fresh], just_finished: false }))

    mount({ just_finished: true })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Satz 1 speichern' }))

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/gym/set/501/update')
    expect((init.headers as Record<string, string>)['Accept']).toBe('application/json')
    expect((init.body as FormData).get('weight')).toBe('60')

    // Re-rendered from the answer...
    expect(screen.getByText('2 × 65 kg')).toBeInTheDocument()
    // ...with the sheet still open and the visit's flag preserved.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Dieses Workout als Routine speichern?')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('re-renders the verdict when the deload toggle answers', async () => {
    vi.stubGlobal('fetch', fetchPayload({
      session: { ...base.session, is_deload: true, deload_pct: 60 },
      is_deload: true,
    }))
    mount()
    await userEvent.click(screen.getByRole('button', { name: 'Als Deload markieren' }))
    expect(await screen.findByText('Als Deload markiert. Bewusst leichter.'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deload-Markierung entfernen' }))
      .toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('says so when the save fails, and keeps the page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Körpergewicht/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    expect(await within(sheet).findByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen')
    // Nothing navigated, nothing blanked.
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Push Day')
    vi.unstubAllGlobals()
  })

  it('deletes a set after the undo window, and the debrief follows', async () => {
    // A set logged by mistake used to be permanent once the workout finished.
    useUndo.setState({ pending: null, timer: null })
    const fetchMock = fetchPayload({
      exercises: [exercise({ sets_display: '1 × 60 kg',
        set_rows: [{ id: 502, weight: 60, reps: 8 }] })],
      total_sets: 1,
    })
    vi.stubGlobal('fetch', fetchMock)
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Bankdrücken, Satz 1 löschen' }))

    // Hidden at once, nothing sent yet.
    expect(within(sheet).getAllByRole('button', { name: /Satz \d speichern/ })).toHaveLength(1)
    expect(fetchMock).not.toHaveBeenCalled()

    useUndo.getState().commitNow()
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/gym/set/501/delete')
    expect(await screen.findByText('1 × 60 kg')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('adds a set -- also to an exercise with nothing logged', async () => {
    const fetchMock = fetchPayload({})
    vi.stubGlobal('fetch', fetchMock)
    mount({ unlogged: [{ session_exercise_id: 91, name: 'Butterfly' }] })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')

    // Seeded from the last set of the exercise it belongs to.
    expect(within(sheet).getByLabelText('Bankdrücken, neuer Satz, Gewicht in kg')).toHaveValue(60)
    expect(within(sheet).getByText('Butterfly')).toBeInTheDocument()

    await userEvent.type(within(sheet).getByLabelText('Butterfly, neuer Satz, Gewicht in kg'), '30')
    await userEvent.type(within(sheet).getByLabelText('Butterfly, neuer Satz, Wiederholungen'), '12')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Butterfly, Satz nachtragen' }))
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/gym/session-exercise/91/sets/add')
    expect((init.body as FormData).get('weight')).toBe('30')
    expect((init.body as FormData).get('reps')).toBe('12')
    // The debrief writes without the live screen's header: corrections to a
    // finished workout are allowed, a stale live screen's writes are not.
    expect((init.headers as Record<string, string>)['X-Gym-Surface']).toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('will not add an empty set', async () => {
    const fetchMock = fetchPayload({})
    vi.stubGlobal('fetch', fetchMock)
    mount({ unlogged: [{ session_exercise_id: 91, name: 'Butterfly' }] })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Butterfly, Satz nachtragen' }))
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

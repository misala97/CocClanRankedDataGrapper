import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StartPage } from './StartPage'
import type { HeutePayload, RoutineMemory, Stall } from './types'
import { usePush, useSheets } from '../session/stores'
import { useUndo } from '../undo'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useUndo.setState({ pending: null, timer: null })
})

const routine = (over: Partial<RoutineMemory> = {}): RoutineMemory => ({
  template_id: 1, name: 'Push', exercises: ['Bankdrücken'], exercise_ids: [10],
  last_done: '2026-08-01T10:00:00', days_ago: 9, ...over,
})

const stall = (over: Partial<Stall> = {}): Stall => ({
  exercise_id: 10, name: 'Bankdrücken', position: 1, stuck_at: 60.0,
  since: '2026-07-01T10:00:00', sessions_since_pr: 4, last_record_at: '2026-07-01T10:00:00',
  ...over,
})

const base: HeutePayload = {
  now: '2026-08-10T18:00:00',
  active_session_id: null,
  active_session_name: null,
  active_session_started_at: null,
  active_session_exercise: null,
  active_session_rest_ends_at: null,
  vapid_public_key: null,
  consistency: { sessions: 8, per_week: 2.5, days_since_last: 2, window_days: 28 },
  routines: [routine()],
  progress: { up: [], with_trend: 0, min_workouts: 4, min_days: 14 },
  stalls: [],
  deload_suggestion: null,
  balance: [],
  tonnage: [],
  tonnage_peak: 0,
  templates: [routine()],
  pending_invites: [],
  onboarding: null,
}

const mount = (over: Partial<HeutePayload> = {}) =>
  render(<StartPage payload={{ ...base, ...over }} />)

/**
 * The markup half of the Heute tests that used to live in
 * tests/test_gym_routes_smoke.py and tests/test_gym_sharing.py: those now
 * assert on the payload the server embeds, and the rendering they used to
 * grep for is asserted here.
 */
describe('StartPage', () => {
  it('closes the sheet on back, not the page (G-066)', async () => {
    history.replaceState(null, '')
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Freies Workout starten/ }))
    expect(useSheets.getState().openId).toBe('sheet-free')
    expect((history.state as { gymSheet?: boolean } | null)?.gymSheet).toBe(true)
    const popped = new Promise<void>((resolve) => {
      window.addEventListener('popstate', () => resolve(), { once: true })
    })
    history.back()
    await act(() => popped)
    expect(useSheets.getState().openId).toBeNull()
  })

  it("starts a free workout without leaving the sheet's entry behind (B7 re-review)", async () => {
    // Back from the workout landed on that entry: one dead step.
    const user = userEvent.setup()
    history.replaceState({ page: 'heute' }, '')
    const sent: unknown[] = []
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(function record(this: HTMLFormElement) {
        sent.push([this.getAttribute('action'), history.state])
      })
    mount()
    await user.click(screen.getByRole('button', { name: /Freies Workout starten/ }))
    const sheet = within(document.querySelector('#sheet-free') as HTMLElement)
    await user.click(sheet.getByRole('button', { name: 'Workout starten' }))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toEqual(['/gym/start', { page: 'heute' }])
    submit.mockRestore()
  })

  it('names the lead routine and offers to start it', () => {
    mount()
    expect(screen.getByRole('heading', { name: 'Am längsten her' })).toBeInTheDocument()
    // Scoped: the sheet's template <select> carries the same name as an option.
    const routines = screen.getByRole('region', { name: /Am längsten her|Routinen/ })
    expect(within(routines).getByText('Push')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Starten/ })).toBeInTheDocument()
  })

  describe('the lead briefing', () => {
    it('names a stall the lead routine contains', () => {
      mount({ stalls: [stall()] })
      expect(screen.getByText(/Bankdrücken steht seit 4 Workouts bei 60,0 kg\./))
        .toBeInTheDocument()
    })

    it('is silent about a stall the routine does not contain', () => {
      // Same name, different exercise: the routine holds id 10, the stall is
      // id 99. Matching by name would report it.
      mount({ stalls: [stall({ exercise_id: 99, name: 'Bankdrücken' })] })
      expect(screen.queryByText(/steht seit/)).not.toBeInTheDocument()
    })

    it('counts the rest instead of listing them', () => {
      mount({
        routines: [routine({ exercise_ids: [10, 11], exercises: ['Bankdrücken', 'Dips'] })],
        stalls: [stall(), stall({ exercise_id: 11, name: 'Dips' })],
      })
      const line = screen.getByText(/steht seit/)
      expect(line).toHaveTextContent('· 1 weitere')
      // Worst-first: the first survivor is the one named.
      expect(line).toHaveTextContent(/^Bankdrücken/)
    })

    it('renders nothing when nothing in the routine stalls', () => {
      mount({ stalls: [] })
      expect(screen.queryByText(/steht seit/)).not.toBeInTheDocument()
    })

    it('says one Workout in the singular', () => {
      mount({ stalls: [stall({ sessions_since_pr: 1 })] })
      expect(screen.getByText(/seit 1 Workout bei/)).toBeInTheDocument()
    })
  })

  describe('a pending invite', () => {
    it('names who is training and what', () => {
      mount({
        pending_invites: [
          { shared_id: 7, leader_name: 'Michi', session_name: 'Pull Day' },
        ],
      })
      expect(screen.getByText('Michi trainiert')).toBeInTheDocument()
      expect(screen.getByText('Pull Day')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Mitmachen' }))
        .toHaveAttribute('href', '/gym/shared/7/confirm')
    })

    it('is absent when there is none', () => {
      mount()
      expect(screen.queryByRole('link', { name: 'Mitmachen' })).not.toBeInTheDocument()
    })
  })

  describe('while a workout is running', () => {
    const running = {
      active_session_id: 42,
      active_session_name: 'Leg Day',
      // An hour before the payload's `now`, and much longer before any
      // Date.now() the test runs at.
      active_session_started_at: '2026-08-10T17:00:00',
      active_session_exercise: 'Bench Press (Dumbbell)',
    }

    it('leads with getting back into it', () => {
      mount(running)
      expect(screen.getByRole('heading', { name: 'Läuft gerade' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /Weiter/ }))
        .toHaveAttribute('href', '/gym/session/42')
    })

    it('measures the clock from the session start, not the page render', () => {
      // The bug this pins: useElapsed(payload.now) showed "00:00:01 läuft"
      // twenty minutes into a workout -- the one live datum on the page,
      // false at the exact glance the card exists for.
      mount(running)
      const clock = document.getElementById('heute-elapsed')!
      expect(clock.textContent).toMatch(/^\d{2,}:\d{2}:\d{2}$/)
      expect(clock.textContent).not.toBe('00:00:00')
      expect(clock.textContent).not.toBe('00:00:01')
    })

    it('says what you were on', () => {
      mount(running)
      expect(screen.getByText('Bench Press (Dumbbell)')).toBeInTheDocument()
    })

    it('shows no rest countdown without a running rest', () => {
      mount(running)
      expect(screen.queryByText(/Pause/)).not.toBeInTheDocument()
    })

    it('ignores a stale rest stamp past the ceiling', () => {
      // Same 900s cap as the Jinja resume strip: a stale rest_ends_at must
      // not strand the card on a garbage countdown.
      mount({ ...running, active_session_rest_ends_at: '2030-01-01T00:00:00' })
      expect(screen.queryByText(/Pause/)).not.toBeInTheDocument()
    })

    it('offers no way to start another one', () => {
      mount(running)
      expect(screen.queryByRole('button', { name: /Starten/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Freies Workout/ })).not.toBeInTheDocument()
      expect(screen.getByText(/Ein Workout läuft schon/)).toBeInTheDocument()
      // The routines stay as reading material, so the lead is a plain row now.
      const routines = screen.getByRole('region', { name: 'Routinen' })
      expect(within(routines).getByText('Push')).toBeInTheDocument()
    })
  })

  describe('Fortschritt (M3)', () => {
    it('leads the reading with what goes up and what stands still', () => {
      mount({
        progress: {
          up: [{
            exercise_id: 12, name: 'Kniebeuge', per_month: 2.5, workouts: 6,
            points: [{ started_at: '2026-07-01T10:00:00', e1rm: 100 },
              { started_at: '2026-07-29T10:00:00', e1rm: 104 }],
            best: { e1rm: 104, started_at: '2026-07-29T10:00:00', is_record: true },
          }],
          with_trend: 2, min_workouts: 4, min_days: 14,
        },
        stalls: [stall({ exercise_id: 11, name: 'Dips' })],
      })
      const section = screen.getByRole('region', { name: 'Fortschritt' })
      expect(within(section).getByRole('link', { name: /^Kniebeuge: Trend der letzten 6 Workouts/ }))
        .toHaveAttribute('href', '/gym/exercises/12')
      expect(within(section).getByRole('link', { name: /^Dips: seit 4 Workouts ohne Rekord/ }))
        .toHaveAttribute('href', '/gym/exercises/11')
    })

    it('took the place of the recent workouts, which Verlauf lists (D7-C)', () => {
      mount({ stalls: [stall()] })
      expect(screen.queryByRole('heading', { name: 'Letzte Workouts' })).not.toBeInTheDocument()
    })
  })

  describe('tonnage', () => {
    const weeks = [
      { week_start: '2026-08-03', volume: 4000, is_current: false, has_deload: true },
      { week_start: '2026-08-10', volume: 2000, is_current: true, has_deload: false },
    ]

    it('draws each week against the named peak', () => {
      mount({ tonnage: weeks, tonnage_peak: 4000 })
      expect(document.querySelector('.vbars__peak'))
        .toHaveTextContent('Höchste Woche 4.000 kg, ab 03.08.')
      const bars = screen.getAllByRole('listitem')
      expect(bars[0]).toHaveStyle({ blockSize: '100%' })
      expect(bars[1]).toHaveStyle({ blockSize: '50%' })
      // Magnitude is not left to bar height alone.
      expect(bars[0]).toHaveAccessibleName(/4\.000 kg, mit Deload-Workout/)
      expect(bars[1]).toHaveAccessibleName(/Diese Woche: 2\.000 kg/)
      expect(screen.getByText(/kg diese Woche bisher/))
        .toHaveTextContent('2.000 kg diese Woche bisher — läuft noch. Schraffiert: Woche mit Deload-Workout.')
    })

    it('draws a week without a workout as a baseline, and names it', () => {
      mount({
        tonnage: [{ week_start: '2026-07-27', volume: 0, is_current: false, has_deload: false },
          ...weeks.slice(0, 1),
          { ...weeks[1]!, volume: 0 }],
        tonnage_peak: 4000,
      })
      const bars = screen.getAllByRole('listitem')
      expect(bars.map((bar) => bar.classList.contains('is-zero'))).toEqual([true, false, true])
      expect(bars[0]).toHaveAccessibleName('Woche ab 27.07.: kein Workout')
      expect(bars[2]).toHaveAccessibleName('Diese Woche: noch kein Workout')
    })

    it('says so rather than drawing eight stubs when there is nothing', () => {
      mount({ tonnage: weeks, tonnage_peak: 0 })
      expect(screen.getByText('Noch keine Sätze in den letzten 8 Wochen.'))
        .toBeInTheDocument()
      expect(screen.queryAllByRole('listitem')).toHaveLength(0)
    })
  })

  it('marks an under-trained muscle group', () => {
    mount({
      balance: [
        { group: 'Brust', sets: 12, volume: 9000, share: 0.6, under_trained: false },
        { group: 'Rücken', sets: 2, volume: 1500, share: 0.1, under_trained: true },
      ],
    })
    expect(screen.getByText('zu wenig')).toBeInTheDocument()
    expect(screen.getByText('Brust').parentElement!.querySelector('.hbar__fill'))
      .toHaveStyle({ inlineSize: '60%' })
  })

  it('states the pulse from the consistency window', () => {
    mount()
    expect(screen.getByText(/Zuletzt vor/)).toHaveTextContent(
      'Zuletzt vor 2 Tagen · 2,5 Workouts pro Woche')
  })

  it('says heute and gestern rather than counting days', () => {
    mount({ consistency: { ...base.consistency, days_since_last: 0 } })
    expect(screen.getByText(/Zuletzt/)).toHaveTextContent('Zuletzt heute')
    mount({ consistency: { ...base.consistency, days_since_last: 1 } })
    expect(screen.getAllByText(/Zuletzt/)[1]).toHaveTextContent('Zuletzt gestern')
  })

  it('has nothing to report before the first workout', () => {
    mount({ consistency: { ...base.consistency, days_since_last: null } })
    expect(screen.getByText('Noch keine Workouts protokolliert')).toBeInTheDocument()
  })

  it('points at the catalogue when there are no templates yet', () => {
    mount({ routines: [] })
    expect(screen.getByText(/Noch keine Routinen/)).toBeInTheDocument()
    // Starting without one is still a real path.
    expect(screen.getByRole('button', { name: /Freies Workout/ })).toBeInTheDocument()
  })
})

describe('editing a routine in place', () => {
  it('renames over fetch and re-renders the row from the answer', async () => {
    const fresh: HeutePayload = {
      ...base,
      routines: [routine({ name: 'Push v2' })],
      templates: [routine({ name: 'Push v2' })],
    }
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => fresh,
    } as unknown as Response)))

    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    const input = screen.getByLabelText('Neuer Name für Push')
    await user.clear(input)
    await user.type(input, 'Push v2')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/gym/templates/1/rename')
    expect((init.headers as Record<string, string>)['Accept']).toBe('application/json')
    expect((init.body as FormData).get('name')).toBe('Push v2')

    const routines = screen.getByRole('region', { name: /Am längsten her|Routinen/ })
    expect(await within(routines).findByText('Push v2')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('drops the row instantly and only deletes when the window closes', async () => {
    const spy = vi.fn(async () => ({
      ok: true, json: async () => ({ ...base, routines: [], templates: [] }),
    } as unknown as Response))
    vi.stubGlobal('fetch', spy)

    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Löschen' }))

    // Gone from the page, said in the toast, nothing on the wire yet.
    expect(screen.getByText(/Noch keine Routinen/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Routine „Push“ gelöscht.')
    expect(spy).not.toHaveBeenCalled()

    useUndo.getState().commitNow()
    expect(spy).toHaveBeenCalledWith('/gym/templates/1/delete', expect.anything())
    vi.unstubAllGlobals()
  })

  it('undo restores the row and never touches the server', async () => {
    const spy = vi.fn()
    vi.stubGlobal('fetch', spy)

    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Löschen' }))
    await user.click(screen.getByRole('button', { name: 'Rückgängig' }))

    const routines = screen.getByRole('region', { name: /Am längsten her|Routinen/ })
    expect(within(routines).getByText('Push')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('brings the routine back when its delete fails (G-147)', async () => {
    // The row went at the tap; a delete that never reached the server left
    // it gone from the page while it still existed.
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Löschen' }))
    expect(screen.getByText(/Noch keine Routinen/)).toBeInTheDocument()

    await act(async () => { useUndo.getState().commitNow() })
    expect(await screen.findByRole('alert')).toHaveTextContent('Verbindung fehlgeschlagen')
    const routines = screen.getByRole('region', { name: /Am längsten her|Routinen/ })
    expect(within(routines).getByText('Push')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('says why push did not turn on, beside the prompt (G-148)', async () => {
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        getRegistration: async () => ({ pushManager: { getSubscription: async () => null } }),
        register: async () => ({
          pushManager: { subscribe: async () => ({ toJSON: () => ({ endpoint: 'e' }) }) },
        }),
      },
    })
    vi.stubGlobal('PushManager', function PushManager() {})
    vi.stubGlobal('Notification', { requestPermission: async () => 'granted' })
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 500 })))
    try {
      mount({ vapid_public_key: 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U' })
      const user = userEvent.setup()
      await user.click(await screen.findByText('Pausen-Benachrichtigung aktivieren'))
      expect(await screen.findByRole('alert')).toHaveTextContent(/nicht aktivieren/)
      // Still offered: the device is not subscribed, so the tap can be tried again.
      expect(screen.getByText('Pausen-Benachrichtigung aktivieren')).toBeInTheDocument()
    } finally {
      Reflect.deleteProperty(navigator, 'serviceWorker')
      vi.unstubAllGlobals()
    }
  })

  it('states a failure and keeps the page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Verbindung fehlgeschlagen')
    const routines = screen.getByRole('region', { name: /Am längsten her|Routinen/ })
    expect(within(routines).getByText('Push')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

describe('the first-run checklist', () => {
  const empty: Partial<HeutePayload> = {
    consistency: { sessions: 0, per_week: 0, days_since_last: null, window_days: 28 },
    routines: [], templates: [],
    onboarding: { workouts: 0, last: null },
  }
  const once: Partial<HeutePayload> = {
    ...empty,
    consistency: { sessions: 1, per_week: 0.25, days_since_last: 0, window_days: 28 },
    onboarding: {
      workouts: 1,
      last: {
        session_id: 7, name: 'Oberkörper', exercises: 5,
        started_at: '2026-08-10T16:00:00', finished_at: '2026-08-10T16:42:30',
      },
    },
  }
  const step = (name: RegExp) => screen.getByText(name, { selector: '.onb__t' }).closest('li')!

  it('makes the first workout the one thing to do on an empty account', () => {
    mount(empty)
    expect(screen.getByRole('heading', { name: 'So fängst du an' })).toBeInTheDocument()
    expect(screen.getByText('0 von 3')).toBeInTheDocument()
    const first = step(/Erstes Workout/)
    expect(first).toHaveAttribute('aria-current', 'step')
    // Straight in: no sheet asking for a name and a template it cannot have.
    const go = within(first).getByRole('button', { name: /Workout starten/ })
    expect(go.closest('form')).toHaveAttribute('action', '/gym/start')
    expect(go.closest('form')!.querySelector('[name=template_id]')).toBeNull()
  })

  it('hides the sections that have nothing to say yet', () => {
    mount(empty)
    for (const name of [/^Tonnage pro Woche/, /^Sätze pro Muskelgruppe/, /^Fortschritt/,
      /^Routinen/]) {
      expect(screen.queryByRole('heading', { name })).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/Pausen-Benachrichtigung aktivieren/)).not.toBeInTheDocument()
  })

  it('ticks the workout off and asks to keep it as a routine', () => {
    mount(once)
    expect(screen.getByText('1 von 3')).toBeInTheDocument()
    const first = step(/Erstes Workout/)
    expect(first).toHaveClass('is-done')
    expect(first).toHaveTextContent('Heute · 5 Übungen · 42 min')
    const save = step(/Als Routine speichern/)
    expect(save).toHaveAttribute('aria-current', 'step')
    const form = within(save).getByRole('button', { name: 'Als Routine speichern' }).closest('form')!
    expect(form).toHaveAttribute('action', '/gym/session/7/save_as_template')
    expect(form.querySelector('[name=next]')).toHaveValue('start')
    expect(within(save).getByLabelText('Name der Routine')).toHaveValue('Oberkörper')
    // The next workout still has a way in, and the page now has data to show.
    expect(screen.getByRole('button', { name: /Freies Workout starten/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tonnage pro Woche 8 Wochen' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Fortschritt' })).toBeInTheDocument()
  })

  it('counts workouts once there is more than one', () => {
    mount({ ...once, onboarding: { ...once.onboarding!, workouts: 2 } })
    expect(step(/Erstes Workout/)).toHaveTextContent('2 Workouts · zuletzt heute')
  })

  it('lower-cases only the adverb mid-sentence, never a noun', () => {
    mount({
      ...once,
      consistency: { ...once.consistency!, days_since_last: 3 },
      onboarding: { ...once.onboarding!, workouts: 2 },
    })
    expect(step(/Erstes Workout/)).toHaveTextContent('2 Workouts · zuletzt vor 3 Tagen')
  })

  it('steps aside while a workout runs', () => {
    mount({ ...empty, active_session_id: 42, active_session_started_at: '2026-08-10T17:00:00' })
    expect(screen.getByRole('heading', { name: 'Läuft gerade' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'So fängst du an' })).not.toBeInTheDocument()
  })

  it('explains the home-screen step where the browser cannot push', () => {
    // jsdom has neither serviceWorker nor PushManager.
    mount(empty)
    const push = step(/Pausen-Timer aufs Handy/)
    expect(push).toHaveTextContent(/Zum Home-Bildschirm/)
    expect(within(push).queryByRole('button')).not.toBeInTheDocument()
  })

  it('ticks the push step off on a subscribed device', async () => {
    const subscription = { toJSON: () => ({}) }
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        getRegistration: async () =>
          ({ pushManager: { getSubscription: async () => subscription } }),
      },
    })
    vi.stubGlobal('PushManager', function PushManager() {})
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true })))
    try {
      mount(empty)
      expect(await screen.findByText('Auf diesem Gerät aktiv.')).toBeInTheDocument()
      expect(screen.getByText('1 von 3')).toBeInTheDocument()
      expect(step(/Pausen-Timer aufs Handy/)).toHaveClass('is-done')
    } finally {
      Reflect.deleteProperty(navigator, 'serviceWorker')
      vi.unstubAllGlobals()
    }
  })

  it('is gone once the account has a routine', () => {
    mount()
    expect(screen.queryByRole('heading', { name: 'So fängst du an' })).not.toBeInTheDocument()
  })
})

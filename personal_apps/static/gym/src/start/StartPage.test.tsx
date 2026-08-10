import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StartPage } from './StartPage'
import type { HeutePayload, RoutineMemory, Stall } from './types'
import { usePush, useSheets } from '../session/stores'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
})

const routine = (over: Partial<RoutineMemory> = {}): RoutineMemory => ({
  template_id: 1, name: 'Push', exercises: ['Bankdrücken'], exercise_ids: [10],
  last_done: '2026-08-01T10:00:00', days_ago: 9, ...over,
})

const stall = (over: Partial<Stall> = {}): Stall => ({
  exercise_id: 10, name: 'Bankdrücken', position: 1, stuck_at: 60.0,
  since: '2026-07-01T10:00:00', sessions_since_pr: 4, ...over,
})

const base: HeutePayload = {
  now: '2026-08-10T18:00:00',
  active_session_id: null,
  active_session_name: null,
  vapid_public_key: null,
  consistency: { sessions: 8, per_week: 2.5, days_since_last: 2, window_days: 28 },
  routines: [routine()],
  recent_sessions: [],
  stalls: [],
  deload_suggestion: null,
  balance: [],
  tonnage: [],
  tonnage_peak: 0,
  templates: [routine()],
  pending_invites: [],
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
      expect(screen.getByText(/Bankdrücken steht seit 4 Sessions bei 60,0 kg\./))
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

    it('says one Session in the singular', () => {
      mount({ stalls: [stall({ sessions_since_pr: 1 })] })
      expect(screen.getByText(/seit 1 Session bei/)).toBeInTheDocument()
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
    const running = { active_session_id: 42, active_session_name: 'Leg Day' }

    it('leads with getting back into it', () => {
      mount(running)
      expect(screen.getByRole('heading', { name: 'Läuft gerade' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /Weiter/ }))
        .toHaveAttribute('href', '/gym/session/42')
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

  describe('the stall roster', () => {
    const many = Array.from({ length: 7 }, (_, i) =>
      stall({ exercise_id: 100 + i, name: `Lift ${i}` }))

    it('shows five and folds the rest away', () => {
      mount({ stalls: many })
      const section = screen.getByRole('region', { name: 'Steht still' })
      expect(within(section).getByText('7 Übungen')).toBeInTheDocument()
      expect(within(section).getByText('2 weitere')).toBeInTheDocument()
      // Folded, not dropped: all seven are in the DOM.
      expect(within(section).getAllByRole('link')).toHaveLength(7)
    })

    it('scopes the deload note to what is actively trained', () => {
      mount({ stalls: many, deload_suggestion: { count: 3, stalls: many.slice(0, 3) } })
      expect(screen.getByText('3 davon aktiv trainiert')).toBeInTheDocument()
    })

    it('is absent when nothing stalls', () => {
      mount()
      expect(screen.queryByRole('region', { name: 'Steht still' })).not.toBeInTheDocument()
    })
  })

  describe('tonnage', () => {
    const weeks = [
      { week_start: '2026-08-03', volume: 4000, is_current: false, has_deload: true },
      { week_start: '2026-08-10', volume: 2000, is_current: true, has_deload: false },
    ]

    it('draws each week against the named peak', () => {
      mount({ tonnage: weeks, tonnage_peak: 4000 })
      expect(screen.getByText('Höchste Woche').parentElement)
        .toHaveTextContent('4.000 kg')
      const bars = screen.getAllByRole('listitem')
      expect(bars[0]).toHaveStyle({ blockSize: '100%' })
      expect(bars[1]).toHaveStyle({ blockSize: '50%' })
      // Magnitude is not left to bar height alone.
      expect(bars[0]).toHaveAccessibleName(/4\.000 kg, mit Deload-Einheit/)
      expect(bars[1]).toHaveAccessibleName(/Diese Woche: 2\.000 kg/)
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
    expect(screen.getByText(/Noch keine Vorlagen/)).toBeInTheDocument()
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

  it('deletes after the confirm and drops the row', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => ({ ...base, routines: [], templates: [] }),
    } as unknown as Response)))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Löschen' }))

    expect(await screen.findByText(/Noch keine Vorlagen/)).toBeInTheDocument()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('does nothing when the confirm is declined', async () => {
    const spy = vi.fn()
    vi.stubGlobal('fetch', spy)
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    const { container } = mount()
    const user = userEvent.setup()
    await user.click(container.querySelector('.lead__edit-toggle')!)
    await user.click(screen.getByRole('button', { name: 'Löschen' }))

    expect(spy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
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

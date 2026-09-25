import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionPage, type SessionActions } from './SessionPage'
import { useAnnouncer, usePush, useSaveState, useSheets, useWorkoutUi } from './stores'
import { payload } from './types.test-d'
import type { PartnerLink } from '../partner/types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const actions = (): SessionActions => ({
  onConfirmSet: vi.fn(), onToggleSet: vi.fn(), onFinish: vi.fn(), onDiscard: vi.fn(),
  onSendNow: vi.fn(),
  onReload: vi.fn(),
  onReorder: vi.fn(),
  onSessionMetaSave: vi.fn(), onSkipRest: vi.fn(), onShiftRest: vi.fn(), onInvite: vi.fn(),
  onEnablePush: vi.fn(), onToggleDeload: vi.fn(), onAddExercise: vi.fn(),
  onSaveTemplate: vi.fn(),
  exerciseActions: () => ({
    onRestChange: vi.fn(), onOpenSettings: vi.fn(), onMetaSave: vi.fn(),
    onSetUpdate: vi.fn(), onSetDelete: vi.fn(), onAddSet: vi.fn(),
    onToggleSkip: vi.fn(), onReplace: vi.fn(),
    onRemove: vi.fn(), onShowProgress: vi.fn(), onMakeLive: vi.fn(),
    onRoutinePlanChange: vi.fn(),
  }),
})

function mount(over: Partial<Parameters<typeof SessionPage>[0]> = {}) {
  const a = over.actions ?? actions()
  return {
    ...render(<SessionPage payload={payload} actions={a} pushSupported {...over} />),
    actions: a,
  }
}

/**
 * Composition only. Each child has its own suite; this asserts the page has
 * the shape the design describes and that the parts are wired to each other.
 */
describe('SessionPage', () => {
  it('renders the whole screen from one payload', () => {
    mount()
    expect(screen.getByRole('heading', { level: 1 }))
      .toHaveTextContent(payload.session.name!)
    // The live panel names the exercise you are on...
    const live = payload.visible_exercises.find((se) => se.id === payload.live_id)!
    expect(screen.getAllByText(live.name).length).toBeGreaterThan(0)
    // ...and the queue lists every exercise, including that one.
    for (const se of payload.visible_exercises) {
      expect(screen.getAllByText(se.name).length).toBeGreaterThan(0)
    }
  })

  it('hands a deload marked late to the rows still ahead', () => {
    // D4: the payload's hints reach the queue, not only the live card.
    const ahead = payload.visible_exercises.find((se) => se.id !== payload.live_id)!
    const { container } = mount({
      payload: { ...payload, deload_hints: { [String(ahead.id)]: 35 } },
    })
    expect(container.querySelector('.queue__deload')).toHaveTextContent('Deload ≈ 35,0')
  })

  it("gives an exercise its routine's plan in its sheet, and only that one", () => {
    const [held, added] = payload.visible_exercises
    mount({ payload: {
      ...payload,
      session: { ...payload.session, template_name: 'Push' },
      routine_plans: { [String(held!.id)]: { sets: 4, rep_min: 8, rep_max: 12 } },
    } })
    act(() => { useSheets.getState().open(`sheet-ex-${held!.id}`) })
    expect(document.querySelector(`#sheet-ex-${held!.id}`)).toHaveTextContent('Routine „Push“')
    act(() => { useSheets.getState().open(`sheet-ex-${added!.id}`) })
    expect(document.querySelector(`#sheet-ex-${added!.id}`)).not.toHaveTextContent('Routine „')
  })

  it('has a live region before anything is announced', () => {
    const { container } = mount()
    expect(container.querySelector('[aria-live="polite"]')).toBeInTheDocument()
  })

  it('gives every exercise its own sheet', () => {
    mount()
    for (const se of payload.visible_exercises) {
      expect(document.querySelector(`#sheet-ex-${se.id}`)).toBeInTheDocument()
    }
  })

  it('opens exactly one sheet at a time from anywhere on the page', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByLabelText('Workout-Optionen'))
    expect(document.querySelector('#sheet-session')).toHaveAttribute('open')

    // Scoped: "Als Deload markieren" is the handoff inside the options sheet
    // AND the primary action inside the deload sheet itself.
    const options = within(document.querySelector('#sheet-session') as HTMLElement)
    await user.click(options.getByText('Als Deload markieren'))
    expect(document.querySelector('#sheet-session')).not.toHaveAttribute('open')
    expect(document.querySelector('#sheet-deload')).toHaveAttribute('open')
  })

  it('opens the finish sheet instead of a native confirm', async () => {
    // The pre-debrief beat: what the session became, then one decision --
    // in the app's own dialog vocabulary, not browser chrome.
    const user = userEvent.setup()
    const { actions: a } = mount()
    await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
    expect(window.confirm).not.toHaveBeenCalled()
    expect(document.querySelector('#sheet-finish')).toHaveAttribute('open')
    expect(a.onFinish).not.toHaveBeenCalled()

    const sheet = within(document.querySelector('#sheet-finish') as HTMLElement)
    await user.click(sheet.getByRole('button', { name: 'Beenden' }))
    expect(a.onFinish).toHaveBeenCalled()
  })

  it('does not finish when the sheet is dismissed', async () => {
    const user = userEvent.setup()
    const { actions: a } = mount()
    await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
    const sheet = within(document.querySelector('#sheet-finish') as HTMLElement)
    await user.click(sheet.getByRole('button', { name: 'Abbrechen' }))
    expect(document.querySelector('#sheet-finish')).not.toHaveAttribute('open')
    expect(a.onFinish).not.toHaveBeenCalled()
  })

  it('states what the session became and what is still open', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
    const sheet = within(document.querySelector('#sheet-finish') as HTMLElement)
    // The fixture: sets_done of sets_total, session_volume.
    expect(sheet.getByText(new RegExp(
      `${payload.sets_done} von ${payload.sets_total} Sätzen erledigt`))).toBeInTheDocument()
    expect(sheet.getByText(/kg bewegt/)).toBeInTheDocument()
    // Open sets do not survive the finish, and the sheet says so (D5).
    if (payload.sets_total - payload.sets_done > 0) {
      expect(sheet.getByText(/werden? gelöscht\./)).toBeInTheDocument()
    }
  })

  it('shows the reorder bar without re-rendering from the server', () => {
    // The state the whole port exists for: the server has no notion of this
    // mode, so every in-place mutation used to reset it and applyReorderUI
    // existed only to put it back.
    // Scoped to the bar: every sheet's close control is also labelled Fertig.
    const { container } = mount()
    expect(container.querySelector('.reorder-bar')).not.toBeInTheDocument()
    act(() => { useWorkoutUi.getState().setReorder(true) })
    expect(container.querySelector('.reorder-bar__done')).toHaveTextContent('Fertig')
  })

  it('surfaces a save failure without touching the payload', () => {
    mount()
    act(() => { useSaveState.getState().fail('set-1', 'Verbindung fehlgeschlagen', vi.fn()) })
    expect(screen.getByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen')
  })

  it('retries a failed save by itself when the connection returns', () => {
    // Gym wifi comes back before anyone finds the retry button.
    mount()
    const retry = vi.fn()
    act(() => { useSaveState.getState().fail('set-1', 'Verbindung fehlgeschlagen', retry) })
    act(() => { window.dispatchEvent(new Event('online')) })
    expect(retry).toHaveBeenCalledOnce()
  })

  it('keeps client state across a new payload from the server', async () => {
    // The whole promise of the port: a refetch replaces server state and
    // leaves reorder mode, the open sheet and the search query untouched.
    const user = userEvent.setup()
    const { rerender, actions: a } = mount()

    await user.click(screen.getByLabelText('Workout-Optionen'))
    act(() => { useWorkoutUi.getState().setReorder(true) })

    rerender(<SessionPage payload={{ ...payload, sets_done: 99 }}
      actions={a} pushSupported />)

    expect(useSheets.getState().openId).toBe('sheet-session')
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(true)
    expect(document.querySelector('#sheet-session')).toHaveAttribute('open')
  })
})

describe('the partner lines (D14)', () => {
  const line = (over: Partial<PartnerLink> = {}): PartnerLink => ({
    id: 7, username: 'jglaser', viewer_leads: true, state: 'joined',
    since: '2026-09-25T09:26:00', finished_at: null,
    exercise: 'Rudern', set_no: 2, done_in_exercise: 1, sets_in_exercise: 3,
    last_set: { weight: 60, reps: 8 }, rest_left: null, sets_done: 4, sets_total: 12, list_key: 1,
    ...over,
  })
  const partnerList = (over: Record<string, unknown> = {}) => ({
    id: 7, username: 'jglaser', viewer_leads: true, link_live: true,
    since: '2026-09-25T09:26:00', started_at: '2026-09-25T09:20:00', finished_at: null,
    sets_done: 4, sets_total: 12, rest_left: null,
    rows: [{ id: 1, name: 'Rudern', picture: null, state: 'now',
      sets: [{ weight: 60, reps: 8 }], done: 1, open: 2, set_no: 2 }],
    ...over,
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('sits right under the header, one line per partner', () => {
    const { container } = mount({ partners: {
      links: [line(), line({ id: 9, username: 'anna', state: 'invited', exercise: null })],
      receivedAt: Date.now(), dismiss: vi.fn(),
    } })
    const lines = container.querySelector('.partners')!
    expect(container.querySelector('.session-top')!.nextElementSibling).toBe(lines)
    expect(lines.querySelectorAll('.partner')).toHaveLength(2)
  })

  it('shows none while nobody trains along', () => {
    const { container } = mount()
    expect(container.querySelector('.partners')).toBeNull()
  })

  it("opens a partner's list from their line, and follows the line as it moves", async () => {
    const user = userEvent.setup()
    let answer = partnerList()
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(answer)))
    vi.stubGlobal('fetch', fetchMock)
    const a = actions()
    const { rerender } = mount({ actions: a, partners: {
      links: [line()], receivedAt: Date.now(), dismiss: vi.fn(),
    } })
    await user.click(screen.getByRole('button', { name: /^jglaser: Satz 2 von 3, Rudern/ }))
    const sheet = screen.getByRole('dialog', { name: 'jglaser' })
    await waitFor(() => expect(sheet).toHaveTextContent('Zusammen seit 11:26 · 4 von 12 Sätzen'))

    // The next poll moved them on: the open list is fetched again.
    answer = partnerList({ sets_done: 5 })
    rerender(<SessionPage payload={payload} actions={a} pushSupported partners={{
      links: [line({ set_no: 3, done_in_exercise: 2, sets_done: 5, list_key: 2 })],
      receivedAt: Date.now(), dismiss: vi.fn(),
    }} />)
    await waitFor(() => expect(sheet).toHaveTextContent('5 von 12 Sätzen'))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await user.click(within(sheet).getByRole('button', { name: 'Fertig' }))
    expect(sheet).not.toHaveAttribute('open')
  })

  it("keeps a sheet as its line last was once the poll drops it", async () => {
    // Declined, then put away on the other phone while this one had it open:
    // the sheet asked for a list nobody has, and said it could not be loaded.
    const user = userEvent.setup()
    const fetchMock = vi.fn(async () => new Response('{}', { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)
    const a = actions()
    const invite = { exercise: null, last_set: null }
    const show = (links: PartnerLink[]) => rerender(
      <SessionPage payload={payload} actions={a} pushSupported partners={{
        links, receivedAt: Date.now(), dismiss: vi.fn(),
      }} />)
    const { rerender } = mount({ actions: a, partners: {
      links: [line({ state: 'invited', ...invite })], receivedAt: Date.now(), dismiss: vi.fn(),
    } })
    await user.click(screen.getByRole('button', { name: /^jglaser ist eingeladen/ }))
    const sheet = screen.getByRole('dialog', { name: 'jglaser' })
    show([line({ state: 'declined', since: '2026-09-25T09:30:00', ...invite })])
    show([])
    // As last carried, not as opened: the no, not "noch keine Antwort".
    expect(sheet).toHaveTextContent('Abgelehnt um 11:30')
    expect(fetchMock).not.toHaveBeenCalled()
    await user.click(within(sheet).getByRole('button', { name: 'Fertig' }))
  })

  it("hands a declined invite's OK to the sync", async () => {
    const user = userEvent.setup()
    const dismiss = vi.fn()
    mount({ partners: {
      links: [line({ state: 'declined', exercise: null, last_set: null })],
      receivedAt: 0, dismiss,
    } })
    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(dismiss).toHaveBeenCalledWith(7)
  })
})

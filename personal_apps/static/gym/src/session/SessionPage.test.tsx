import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionPage, type SessionActions } from './SessionPage'
import { useAnnouncer, usePush, useSaveState, useSheets, useWorkoutUi } from './stores'
import { payload } from './types.test-d'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

const actions = (): SessionActions => ({
  onConfirmSet: vi.fn(), onToggleSet: vi.fn(), onFinish: vi.fn(), onReorder: vi.fn(),
  onSessionMetaSave: vi.fn(), onSkipRest: vi.fn(), onInvite: vi.fn(),
  onEnablePush: vi.fn(), onToggleDeload: vi.fn(), onAddExercise: vi.fn(),
  onCreateExercise: vi.fn(), onSaveTemplate: vi.fn(),
  exerciseActions: () => ({
    onRestChange: vi.fn(), onIncrementChange: vi.fn(), onMetaSave: vi.fn(),
    onSetUpdate: vi.fn(), onSetDelete: vi.fn(), onAddSet: vi.fn(),
    onToggleSkip: vi.fn(), onReplace: vi.fn(), onReplaceWithNew: vi.fn(),
    onRemove: vi.fn(), onShowProgress: vi.fn(),
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
    if (payload.sets_total - payload.sets_done > 0) {
      expect(sheet.getByText(/offen\./)).toBeInTheDocument()
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
    act(() => { useSaveState.getState().fail('Verbindung fehlgeschlagen', vi.fn()) })
    expect(screen.getByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen')
  })

  it('retries a failed save by itself when the connection returns', () => {
    // Gym wifi comes back before anyone finds the retry button.
    mount()
    const retry = vi.fn()
    act(() => { useSaveState.getState().fail('Verbindung fehlgeschlagen', retry) })
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

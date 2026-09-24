import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionIsland } from './SessionIsland'
import { useAnnouncer, usePush, useSaveState, useSheets, useWorkoutUi } from './stores'
import { useUndo } from '../undo'
import { payload } from './types.test-d'

/**
 * The island with its real mutation layer, against a stubbed network: what
 * the parts do together on the way out of a workout (B4 review).
 */
beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  useUndo.setState(useUndo.getInitialState(), true)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  // Reduced motion: the totals count up without a clock to run on.
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
})

afterEach(() => {
  // Unmounted while the stubs still stand: a refetch landing late re-runs
  // the totals' count-up, which asks matchMedia.
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// Exercise 10: set 100 done, 101 and 102 open.
const SHEET = '#sheet-ex-10'
const DETAIL = `/gym/session/${payload.session.id}/detail.json`

type Answer = (url: string) => Promise<Response>

function network(answer: Answer) {
  const calls: { url: string; init: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit = {}) => {
    calls.push({ url, init })
    return answer(url)
  }))
  return calls
}

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), {
  status: 200, headers: { 'Content-Type': 'application/json' },
}))
const offline = () => Promise.reject(new TypeError('Failed to fetch'))

async function editFirstSet(user: ReturnType<typeof userEvent.setup>) {
  act(() => { useSheets.getState().open('sheet-ex-10') })
  const sheet = within(document.querySelector(SHEET) as HTMLElement)
  await user.clear(sheet.getByLabelText('Satz 1, Wiederholungen'))
  await user.type(sheet.getByLabelText('Satz 1, Wiederholungen'), '7')
  await user.click(sheet.getByLabelText('Satz 1 speichern'))
}

async function finish(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
  const sheet = within(document.querySelector('#sheet-finish') as HTMLElement)
  await user.click(sheet.getByRole('button', { name: 'Beenden' }))
}

describe('SessionIsland', () => {
  it('sends a delete flushed on the way out at once, past a write in flight', async () => {
    // Queued behind the save still waiting on gym wifi, the keepalive delete
    // never started before the phone put the page away (G-147).
    const user = userEvent.setup()
    const calls = network((url) => (url.endsWith('/update') ? new Promise(() => {}) : json(payload)))
    render(<SessionIsland initial={payload} />)
    await editFirstSet(user)
    await waitFor(() => expect(calls.some((c) => c.url === '/gym/set/100/update')).toBe(true))

    await user.click(within(document.querySelector(SHEET) as HTMLElement)
      .getByLabelText('Satz 2 löschen'))
    useUndo.getState().commitNow(true)

    await waitFor(() => {
      expect(calls.find((c) => c.url === '/gym/set/101/delete')?.init.keepalive).toBe(true)
    })
  })

  it('sends a routine plan flushed on the way out at once, past a write in flight', async () => {
    // Queued behind the save still waiting on gym wifi, the plan never left
    // before the page was gone, and the edit was lost (B5 review).
    const withRoutine = {
      ...payload,
      session: { ...payload.session, template_name: 'Push' },
      routine_plans: { '10': { sets: 3, rep_min: 6, rep_max: 10 } },
    }
    const user = userEvent.setup()
    const calls = network((url) => (url.endsWith('/update')
      ? new Promise(() => {}) : json(withRoutine)))
    render(<SessionIsland initial={withRoutine} />)
    await editFirstSet(user)
    await waitFor(() => expect(calls.some((c) => c.url === '/gym/set/100/update')).toBe(true))

    await user.click(within(document.querySelector(SHEET) as HTMLElement)
      .getByRole('button', { name: 'Ein Satz mehr' }))
    act(() => { window.dispatchEvent(new Event('pagehide')) })

    await waitFor(() => {
      expect(calls.find((c) => c.url === '/gym/session-exercise/10/routine-plan')?.init.keepalive)
        .toBe(true)
    })
  })

  it('sends a lost write again before finishing, and stays when it fails again', async () => {
    // Finishing past it filed the workout without the set -- the banner had
    // said so, but only for the writes that failed AFTER the tap.
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    const calls = network((url) => (url.endsWith('/update') ? offline() : json(payload)))
    const updates = () => calls.filter((c) => c.url === '/gym/set/100/update').length
    render(<SessionIsland initial={payload} />)
    await editFirstSet(user)
    await screen.findByText('Nicht gespeichert')

    await finish(user)

    await waitFor(() => expect(updates()).toBe(2))
    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(submit).not.toHaveBeenCalled()
    expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()
  })

  it('finishes once the lost write has landed after all', async () => {
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    let failed = false
    const calls = network((url) => {
      if (url.endsWith('/update') && !failed) { failed = true; return offline() }
      return json(payload)
    })
    render(<SessionIsland initial={payload} />)
    await editFirstSet(user)
    await screen.findByText('Nicht gespeichert')

    await finish(user)

    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(calls.filter((c) => c.url === '/gym/set/100/update')).toHaveLength(2)
    expect((submit.mock.contexts[0] as HTMLFormElement).getAttribute('action'))
      .toBe(`/gym/session/${payload.session.id}/finish`)
  })

  it('never sends a lost add again by itself, and stays for the lifter to decide (B4 re-review)', async () => {
    // Its answer may be what was lost: the set is in, and sent again it lands
    // twice -- by the returning connection, or on the way out.
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    const calls = network((url) => (url.endsWith('/sets/add') ? offline() : json(payload)))
    const adds = () => calls.filter((c) => c.url.endsWith('/sets/add')).length
    render(<SessionIsland initial={payload} />)
    act(() => { useSheets.getState().open('sheet-ex-10') })
    const sheet = within(document.querySelector(SHEET) as HTMLElement)
    await user.clear(sheet.getByLabelText('Neuer Satz, Gewicht in kg'))
    await user.type(sheet.getByLabelText('Neuer Satz, Gewicht in kg'), '60')
    await user.clear(sheet.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(sheet.getByLabelText('Neuer Satz, Wiederholungen'), '8')
    await user.click(sheet.getByLabelText('Satz anhängen'))
    await screen.findByText('Nicht gespeichert')

    act(() => { window.dispatchEvent(new Event('online')) })
    await finish(user)

    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(adds()).toBe(1)
    expect(submit).not.toHaveBeenCalled()
    expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()
  })

  it('throws the workout away without sending its lost writes first (B4 re-review)', async () => {
    // Sent again, a lost set would land, and the discard would refuse a
    // workout that now has one.
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    const empty = { ...payload, sets_done: 0 }
    const calls = network((url) => (url.endsWith('/update') ? offline() : json(empty)))
    render(<SessionIsland initial={empty} />)
    await editFirstSet(user)
    await screen.findByText('Nicht gespeichert')

    await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
    await user.click(within(document.querySelector('#sheet-finish') as HTMLElement)
      .getByRole('button', { name: 'Workout verwerfen' }))

    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(calls.filter((c) => c.url === '/gym/set/100/update')).toHaveLength(1)
    expect((submit.mock.contexts[0] as HTMLFormElement).getAttribute('action'))
      .toBe(`/gym/session/${payload.session.id}/discard`)
  })

  it('sends an un-log flushed on the way out at once, past a write in flight (B4 re-review)', async () => {
    // Like the delete: queued behind the save still waiting on gym wifi, it
    // never started before the page was gone.
    const user = userEvent.setup()
    const calls = network((url) => (url.endsWith('/update') ? new Promise(() => {}) : json(payload)))
    render(<SessionIsland initial={payload} />)
    await editFirstSet(user)
    await waitFor(() => expect(calls.some((c) => c.url === '/gym/set/100/update')).toBe(true))
    act(() => { useSheets.getState().close() })

    await user.click(screen.getByLabelText(/^Satz 1 (erledigt|— Rekord)/))
    act(() => { useUndo.getState().commitNow(true) })

    await waitFor(() => {
      expect(calls.find((c) => c.url === '/gym/set/100/toggle_complete')?.init.keepalive)
        .toBe(true)
    })
  })

  it('lets a delete sent past the queue answer the set\'s lost tick (B4 re-review)', async () => {
    // The set is gone. Its lost tick stayed on the banner, and resent, it
    // hit a set that was not there any more.
    const user = userEvent.setup()
    network((url) => (url.endsWith('/toggle_complete') ? offline() : json(payload)))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Nicht gespeichert')

    act(() => { useSheets.getState().open('sheet-ex-10') })
    await user.click(within(document.querySelector(SHEET) as HTMLElement)
      .getByLabelText('Satz 2 löschen'))
    act(() => { useUndo.getState().commitNow(true) })

    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(0))
  })

  it('reloads into the debrief when a refetch finds the workout finished', async () => {
    // The finish on the other phone, or the three-hour rule, ended it; the
    // screen kept taking sets for it.
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const user = userEvent.setup()
    network((url) => {
      if (url.endsWith('/update')) return offline()
      if (url === DETAIL) {
        return json({ ...payload, session: { ...payload.session, finished_at: '2026-09-24T09:00:00' } })
      }
      return json(payload)
    })
    render(<SessionIsland initial={payload} />)
    await editFirstSet(user)

    await waitFor(() => expect(reload).toHaveBeenCalled())
  })
})

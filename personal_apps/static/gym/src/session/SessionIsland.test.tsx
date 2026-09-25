import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionIsland } from './SessionIsland'
import {
  useAnnouncer, useOutbox, usePush, useSaveState, useSheets, useWorkoutUi,
} from './stores'
import { useUndo } from '../undo'
import { OUTBOX_VERSION } from './outbox'
import * as optimistic from './optimistic'
import { payload } from './types.test-d'

/**
 * The island with its real outbox, against a stubbed network: what the
 * parts do together when the gym has no signal (B6, D6-A), and on the way
 * out of a workout (B4).
 */
beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  useUndo.setState(useUndo.getInitialState(), true)
  useOutbox.setState(useOutbox.getInitialState(), true)
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

// Workout 1, exercise 10: set 100 done (60 x 8), 101 and 102 open.
const SHEET = '#sheet-ex-10'
const DETAIL = `/gym/session/${payload.session.id}/detail.json`
const KEPT = `gym-outbox:v${OUTBOX_VERSION}:${payload.session.id}:`

type Answer = (url: string) => Promise<Response>

function network(answer: Answer) {
  const calls: { url: string; init: RequestInit; sentAt: number }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit = {}) => {
    calls.push({ url, init, sentAt: Date.now() })
    return answer(url)
  }))
  return calls
}

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
}))
const offline = () => Promise.reject(new TypeError('Failed to fetch'))
// The writes, not the sets named so far, which the shelf keeps beside them.
const kept = () => Object.keys(localStorage)
  .filter((key) => key.startsWith(KEPT) && key !== `${KEPT}names`)
  .map((key) => JSON.parse(localStorage.getItem(key)!) as { kind: string; args: unknown[] })
const headersOf = (init: RequestInit) => init.headers as Record<string, string>

async function finish(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
  const sheet = within(document.querySelector('#sheet-finish') as HTMLElement)
  await user.click(sheet.getByRole('button', { name: 'Beenden' }))
}

describe('SessionIsland', () => {
  it('logs a set with no connection: done, marked, and nothing waits on it (G-138, D6-A)', async () => {
    const user = userEvent.setup()
    network(() => offline())
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))

    const chip = await screen.findByLabelText(/^Satz 2 erledigt, .*wartet auf Verbindung/)
    expect(chip).toHaveClass('is-done', 'is-waiting')
    expect(await screen.findByText('Wartet auf Verbindung')).toBeInTheDocument()
    // Calm, not the red banner -- and no control held for the connection.
    expect(screen.queryByText('Nicht gespeichert')).toBeNull()
    expect(screen.getByText('Satz geschafft').closest('button')).toBeEnabled()
    expect(kept()).toMatchObject([{ kind: 'toggleSet', args: [101, true, 60, 8] }])
  })

  it('says a set kept through a lapsed login waits for a reload, not for the connection (B6 review)', async () => {
    // The chip said "Verbindung" under a line saying "Neuladen", and the
    // banner called the kept set lost, with a "Verwerfen" that only hid it.
    const user = userEvent.setup()
    network(() => json({ error: 'CSRF' }, 403))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))

    expect(await screen.findByText('Wartet auf Neuladen')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Satz 2 erledigt, .*wartet auf Neuladen/)).toHaveClass('is-waiting')
    const banner = screen.getByRole('alert')
    expect(banner).toHaveTextContent('Auf diesem Handy gespeichert')
    expect(banner).toHaveTextContent('Sitzung abgelaufen — bitte Seite neu laden.')
    expect(within(banner).getByRole('button', { name: 'Neu laden' })).toBeInTheDocument()

    await user.click(within(banner).getByRole('button', { name: 'Ausblenden' }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(kept()).toMatchObject([{ kind: 'toggleSet', args: [101, true, 60, 8] }])
  })

  it('puts what the server refused back on the phone before it reloads (B6 third review)', async () => {
    // Refused and off the phone, a set waited for "Erneut versuchen" -- a
    // tap nothing offered once only a fresh page could send.
    const user = userEvent.setup()
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    network(() => json({ error: 'CSRF' }, 403))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Neuladen')
    const refused = vi.fn()
    act(() => { useSaveState.getState().fail('add-k1', 'Serverfehler', refused, 'manual') })

    const status = document.querySelector('.outbox') as HTMLElement
    await user.click(within(status).getByRole('button', { name: 'Neu laden' }))
    expect(refused).toHaveBeenCalledOnce()
    expect(reload).toHaveBeenCalled()
    expect(refused.mock.invocationCallOrder[0]).toBeLessThan(reload.mock.invocationCallOrder[0]!)
  })

  it('starts the rest on the tap, not on the answer (G-072)', async () => {
    const user = userEvent.setup()
    network(() => offline())
    render(<SessionIsland initial={payload} />)
    expect(screen.queryByRole('group', { name: 'Pause' })).toBeNull()
    await user.click(screen.getByText('Satz geschafft'))
    expect(await screen.findByRole('group', { name: 'Pause' })).toHaveTextContent('von 2:30')
  })

  it('logs the next set a moment later, and drops a bounce', async () => {
    const user = userEvent.setup()
    network(() => offline())
    let now = 1_800_000_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    render(<SessionIsland initial={payload} />)
    const go = () => screen.getByText('Satz geschafft').closest('button')!

    await user.click(go())
    await user.click(go())
    now += 700
    await user.click(go())
    await waitFor(() => expect(kept()).toHaveLength(2))
    expect(kept().map((entry) => entry.args[0]).sort()).toEqual([101, 102])
  })

  it('sends what it kept once the connection is back, with the time each was made', async () => {
    const user = userEvent.setup()
    let online = false
    const calls = network(() => (online ? json(payload) : offline()))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')

    online = true
    act(() => { window.dispatchEvent(new Event('online')) })
    await waitFor(() => expect(screen.queryByText('Wartet auf Verbindung')).toBeNull())

    const sent = calls.filter((c) => c.url === '/gym/set/101/toggle_complete')
    expect(sent).toHaveLength(2)
    // Said as an age, so this phone's clock cannot be off: each copy names
    // the same tap, the later one as longer ago.
    const made = sent.map((c) => {
      const age = headersOf(c.init)['X-Gym-Write-Age']!
      expect(age).toMatch(/^\d+$/)
      return c.sentAt - Number(age)
    })
    expect(Math.abs(made[1]! - made[0]!)).toBeLessThanOrEqual(2)
    expect(Number(headersOf(sent[1]!.init)['X-Gym-Write-Age']))
      .toBeGreaterThan(Number(headersOf(sent[0]!.init)['X-Gym-Write-Age']))
    expect(sent.every((c) => c.init.keepalive === true)).toBe(true)
    expect(kept()).toEqual([])
  })

  it('keeps what it held through a reload, draws it, and sends it', async () => {
    const user = userEvent.setup()
    network(() => offline())
    const first = render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')
    first.unmount()

    const calls = network(() => json(payload))
    render(<SessionIsland initial={payload} />)
    expect(screen.getByLabelText(/^Satz 2 erledigt/)).toBeInTheDocument()
    await waitFor(() => {
      expect(calls.filter((c) => c.url === '/gym/set/101/toggle_complete')).toHaveLength(1)
    })
    await waitFor(() => expect(kept()).toEqual([]))
    // Everything held back is in: the page asks the server again, and a
    // workout past the three-hour rule ends there, at its real last set.
    await waitFor(() => expect(calls.some((c) => c.url === DETAIL)).toBe(true))
  })

  it('names an added set with a key, the same on every try', async () => {
    // Its answer can be lost after it landed: the key makes the copy find it.
    const user = userEvent.setup()
    let online = false
    const calls = network(() => (online ? json(payload) : offline()))
    render(<SessionIsland initial={payload} />)
    act(() => { useSheets.getState().open('sheet-ex-10') })
    const sheet = within(document.querySelector(SHEET) as HTMLElement)
    await user.clear(sheet.getByLabelText('Neuer Satz, Gewicht in kg'))
    await user.type(sheet.getByLabelText('Neuer Satz, Gewicht in kg'), '60')
    await user.clear(sheet.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(sheet.getByLabelText('Neuer Satz, Wiederholungen'), '8')
    await user.click(sheet.getByLabelText('Satz anhängen'))
    await screen.findByText('Wartet auf Verbindung')

    online = true
    act(() => { window.dispatchEvent(new Event('online')) })
    await waitFor(() => expect(kept()).toEqual([]))
    const adds = calls.filter((c) => c.url === '/gym/session-exercise/10/sets/add')
    expect(adds).toHaveLength(2)
    const keys = adds.map((c) => (c.init.body as FormData).get('key'))
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/)
    expect(keys[1]).toBe(keys[0])
  })

  it('keeps a set just added open while its un-log waits, as the set gets its real id (B6 re-review)', async () => {
    // Held by its drawn id, the chip showed done again the moment the add
    // landed, until the undo window closed.
    const user = userEvent.setup()
    let online = false
    let server = payload
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit = {}) => {
      calls.push(url)
      if (!online) return offline()
      if (url.endsWith('/sets/add')) {
        const key = (init.body as FormData).get('key') as string
        server = optimistic.addSet(server, 10, 60, 8, key, 900)
      }
      return json(server)
    }))
    render(<SessionIsland initial={payload} />)
    act(() => { useSheets.getState().open('sheet-ex-10') })
    const sheet = within(document.querySelector(SHEET) as HTMLElement)
    await user.clear(sheet.getByLabelText('Neuer Satz, Gewicht in kg'))
    await user.type(sheet.getByLabelText('Neuer Satz, Gewicht in kg'), '60')
    await user.clear(sheet.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(sheet.getByLabelText('Neuer Satz, Wiederholungen'), '8')
    await user.click(sheet.getByLabelText('Satz anhängen'))
    act(() => { useSheets.getState().close() })
    await screen.findByText('Wartet auf Verbindung')

    await user.click(screen.getByLabelText(/^Satz 4 erledigt/))
    expect(screen.getByLabelText(/^Satz 4, geplant/)).toBeInTheDocument()
    online = true
    act(() => { window.dispatchEvent(new Event('online')) })
    await waitFor(() => expect(calls).toContain('/gym/session-exercise/10/sets/add'))
    await waitFor(() => expect(kept()).toEqual([]))
    expect(screen.getByLabelText(/^Satz 4, geplant/)).toBeInTheDocument()

    act(() => { useUndo.getState().commitNow() })
    await waitFor(() => expect(calls).toContain('/gym/set/900/toggle_complete'))
  })

  it('adds one set for a double tap on "Anhängen", and the next a moment later', async () => {
    // Nothing holds the button for the answer any more (G-138): the bounce
    // is the island's to drop.
    const user = userEvent.setup()
    network(() => offline())
    let now = 1_800_000_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    render(<SessionIsland initial={payload} />)
    act(() => { useSheets.getState().open('sheet-ex-10') })
    const sheet = within(document.querySelector(SHEET) as HTMLElement)
    await user.clear(sheet.getByLabelText('Neuer Satz, Gewicht in kg'))
    await user.type(sheet.getByLabelText('Neuer Satz, Gewicht in kg'), '60')
    await user.clear(sheet.getByLabelText('Neuer Satz, Wiederholungen'))
    await user.type(sheet.getByLabelText('Neuer Satz, Wiederholungen'), '8')
    const add = () => sheet.getByLabelText('Satz anhängen')

    await user.click(add())
    await user.click(add())
    now += 700
    await user.click(add())
    await waitFor(() => expect(kept().filter((e) => e.kind === 'addSet')).toHaveLength(2))
  })

  it('fails a swap at once while writes wait, and says so', async () => {
    const user = userEvent.setup()
    const calls = network(() => offline())
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')

    act(() => { useSheets.getState().open('sheet-ex-10') })
    await user.click(within(document.querySelector(SHEET) as HTMLElement).getByText('Ersetzen'))
    expect(await screen.findByText('Nicht gespeichert')).toBeInTheDocument()
    expect(calls.some((c) => c.url.endsWith('/replace'))).toBe(false)
  })

  it('shows what the server refused, and draws it no more', async () => {
    const user = userEvent.setup()
    network((url) => (url.endsWith('/toggle_complete')
      ? json({ error: 'Gewicht zu hoch.' }, 400) : json(payload)))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))

    expect(await screen.findByText('Gewicht zu hoch.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Satz 2, geplant/)).toBeInTheDocument()
    expect(kept()).toEqual([])
  })

  it('finishes once everything it held is in', async () => {
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    let online = false
    const calls = network(() => (online ? json(payload) : offline()))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')

    online = true
    await finish(user)
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(calls.filter((c) => c.url === '/gym/set/101/toggle_complete')).toHaveLength(2)
    expect((submit.mock.contexts[0] as HTMLFormElement).getAttribute('action'))
      .toBe(`/gym/session/${payload.session.id}/finish`)
  })

  it('stays while what it holds cannot get through, and says why', async () => {
    // Finishing past a set still on the phone filed the workout without it.
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    network(() => offline())
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')

    await finish(user)
    expect(await screen.findByText('Beenden geht, sobald alles gespeichert ist.')).toBeInTheDocument()
    expect(submit).not.toHaveBeenCalled()
    expect(kept()).toHaveLength(1)
  })

  it('throws the workout away without sending what it held (B4 re-review)', async () => {
    // Sent first, a held set would land, and the discard would refuse a
    // workout that now had one.
    localStorage.setItem(`${KEPT}x`, JSON.stringify({
      v: OUTBOX_VERSION, id: 'x', order: Date.now(), at: Date.now(), kind: 'sessionMeta',
      args: [{ notes: 'Knie' }],
    }))
    const user = userEvent.setup()
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    const empty = { ...payload, sets_done: 0 }
    const calls = network(() => offline())
    render(<SessionIsland initial={empty} />)
    await screen.findByText('Wartet auf Verbindung')

    await user.click(screen.getByRole('button', { name: 'Workout beenden' }))
    await user.click(within(document.querySelector('#sheet-finish') as HTMLElement)
      .getByRole('button', { name: 'Workout verwerfen' }))

    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(calls.filter((c) => c.url.endsWith('/meta'))).toHaveLength(1)
    expect((submit.mock.contexts[0] as HTMLFormElement).getAttribute('action'))
      .toBe(`/gym/session/${payload.session.id}/discard`)
    expect(kept()).toEqual([])
  })

  it('keeps an un-log flushed on the way out on the phone at once (G-147)', async () => {
    // Everything hangs: the page is going away before any answer.
    const user = userEvent.setup()
    network(() => new Promise(() => {}))
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByLabelText(/^Satz 1 (erledigt|— Rekord)/))
    act(() => { useUndo.getState().commitNow(true) })

    expect(kept()).toMatchObject([{ kind: 'toggleSet', args: [100, false, 60, 8] }])
    expect(screen.getByLabelText(/^Satz 1, geplant/)).toBeInTheDocument()
  })

  it('keeps a delete and a routine plan flushed on the way out on the phone at once', async () => {
    const withRoutine = {
      ...payload,
      session: { ...payload.session, template_name: 'Push' },
      routine_plans: { '10': { sets: 3, rep_min: 6, rep_max: 10 } },
    }
    const user = userEvent.setup()
    network(() => new Promise(() => {}))
    render(<SessionIsland initial={withRoutine} />)
    act(() => { useSheets.getState().open('sheet-ex-10') })
    const sheet = within(document.querySelector(SHEET) as HTMLElement)
    await user.click(sheet.getByLabelText('Satz 2 löschen'))
    await user.click(sheet.getByRole('button', { name: 'Ein Satz mehr' }))
    act(() => {
      useUndo.getState().commitNow(true)
      window.dispatchEvent(new Event('pagehide'))
    })

    expect(kept().map((entry) => entry.kind).sort()).toEqual(['deleteSet', 'routinePlan'])
  })

  it('reloads into the debrief when a write finds the workout finished', async () => {
    // The finish on the other phone, or the three-hour rule, ended it.
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const user = userEvent.setup()
    network((url) => {
      if (url.endsWith('/toggle_complete')) return json({}, 409)
      if (url === DETAIL) {
        return json({ ...payload, session: { ...payload.session, finished_at: '2026-09-25T09:00:00' } })
      }
      return json(payload)
    })
    render(<SessionIsland initial={payload} />)
    await user.click(screen.getByText('Satz geschafft'))

    await waitFor(() => expect(reload).toHaveBeenCalled())
    expect(kept()).toEqual([])
  })

  it('asks again after half an hour away, unless writes it holds will ask once they are in', async () => {
    // The partner logged, or the workout ended, while the phone was in a
    // pocket: nothing else would redraw the screen (B6).
    let now = 1_800_000_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
    const away = (ms: number) => act(() => {
      visibility = 'hidden'
      document.dispatchEvent(new Event('visibilitychange'))
      now += ms
      visibility = 'visible'
      document.dispatchEvent(new Event('visibilitychange'))
    })
    let online = true
    const calls = network(() => (online ? json(payload) : offline()))
    const asked = () => calls.filter((c) => c.url === DETAIL).length
    render(<SessionIsland initial={payload} />)

    away(29 * 60_000)
    await act(() => Promise.resolve())
    expect(asked()).toBe(0)
    away(31 * 60_000)
    await waitFor(() => expect(asked()).toBe(1))

    online = false
    const user = userEvent.setup()
    await user.click(screen.getByText('Satz geschafft'))
    await screen.findByText('Wartet auf Verbindung')
    away(31 * 60_000)
    await act(() => Promise.resolve())
    expect(asked()).toBe(1)
  })
})

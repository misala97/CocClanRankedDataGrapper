// The shared server state, exercised rather than described.
//
// The key-builders have their own tests. These are about what the hooks DO
// with them: which payload is allowed to seed which key, what a failed refresh
// leaves on screen, and which failures are permanent enough to stop retrying.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { payload } from '../fixtures'
import type { BoardPayload, Selection } from '../types'
import {
  beginWait, boardInterval, boardKey, hear, nextWait, owesABoard, selectionOf,
  useBoard, useWatchMutation,
} from './queries'

const initial = payload()
const selection: Selection = selectionOf(initial)

function Probe({ selection: sel, initial: seed }: {
  selection: Selection; initial?: BoardPayload
}) {
  const board = useBoard(sel, seed, true)
  return (
    <div>
      <p data-testid="market">{board.data ? board.data.market : 'none'}</p>
      <p data-testid="status">{board.status}</p>
      <p data-testid="stamp">{board.data?.generated_at ?? '—'}</p>
      <p data-testid="failed">{board.error ? 'failed' : 'ok'}</p>
    </div>
  )
}

function mount(props: Parameters<typeof Probe>[0]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <Probe {...props} />
    </QueryClientProvider>,
  )
  return client
}

afterEach(() => { vi.restoreAllMocks() })

describe('seeding the cache with the embedded board', () => {
  it('uses it for the selection it was built for', async () => {
    const fetchBoard = vi.spyOn(api, 'fetchBoard')
    mount({ selection, initial })

    expect(screen.getByTestId('market')).toHaveTextContent('us')
    expect(screen.getByTestId('status')).toHaveTextContent('success')
    // Seeded, so nothing was fetched to paint the first screen.
    expect(fetchBoard).not.toHaveBeenCalled()
  })

  it('refuses to seed a different selection with it', async () => {
    // The failure this prevents is silent: a board built for one filter shown
    // as the answer to another, as real data, with a fresh timestamp.
    const german = payload({ market: 'de', generated_at: '2026-08-22T20:00:00Z' })
    const fetchBoard = vi.spyOn(api, 'fetchBoard').mockResolvedValue(german)

    mount({ selection: { ...selection, market: 'de' }, initial })

    expect(screen.getByTestId('market')).not.toHaveTextContent('us')
    await waitFor(() => {
      expect(screen.getByTestId('market')).toHaveTextContent('de')
    })
    expect(fetchBoard).toHaveBeenCalledTimes(1)
  })
})

describe('when a refresh fails', () => {
  it('keeps the last good board on screen with its own timestamp', async () => {
    vi.spyOn(api, 'fetchBoard')
      .mockRejectedValue(new BoardUnavailable('network'))
    const client = mount({ selection, initial })

    // The seeded board is fresh, so nothing refetches on mount. Force the
    // refresh this test is about.
    await client.refetchQueries()
    await waitFor(() => {
      expect(screen.getByTestId('failed')).toHaveTextContent('failed')
    })
    // Data that was true a minute ago beats a blank page -- as long as the
    // surface says when it was true, which is what the stamp is for.
    expect(screen.getByTestId('market')).toHaveTextContent('us')
    expect(screen.getByTestId('stamp')).toHaveTextContent(initial.generated_at!)
  })

  it('stops retrying what cannot come good', async () => {
    for (const reason of ['session', 'forbidden', 'missing'] as const) {
      const fetchBoard = vi.spyOn(api, 'fetchBoard')
        .mockRejectedValue(new BoardUnavailable(reason))
      const client = mount({ selection: { ...selection, market: 'de' } })
      await waitFor(() => {
        expect(screen.getByTestId('status')).toHaveTextContent('error')
      })
      expect(fetchBoard, reason).toHaveBeenCalledTimes(1)
      client.clear()
      vi.restoreAllMocks()
      screen.getByTestId('status').remove()
    }
  })
})

describe('the reasons a request can fail', () => {
  it('retries what might come good', async () => {
    // The positive control. Without it a retry rule of "never" would satisfy
    // every assertion in the block above.
    const fetchBoard = vi.spyOn(api, 'fetchBoard')
      .mockRejectedValue(new BoardUnavailable('network'))
    const client = new QueryClient({
      defaultOptions: { queries: { retryDelay: 1 } },
    })
    render(
      <QueryClientProvider client={client}>
        <Probe selection={{ ...selection, market: 'de' }} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(fetchBoard.mock.calls.length).toBeGreaterThan(1),
                  { timeout: 4000 })
  })

  it('reads 403 as forbidden on a read and as a session on a write', async () => {
    // The admin endpoint answers 403 to a signed-in non-admin, which
    // reloading will never fix. A WRITE answers 403 from the blueprint's CSRF
    // gate, which runs before the login check -- so there it IS an expired
    // session and reloading re-mints the token. Same status, opposite advice.
    const answer = (status: number) => Promise.resolve(new Response('{}', {
      status, headers: { 'Content-Type': 'application/json' },
    }))
    const fetchMock = vi.spyOn(globalThis, 'fetch')

    fetchMock.mockImplementation(() => answer(403))
    await expect(api.fetchOps()).rejects.toMatchObject({ reason: 'forbidden' })
    await expect(api.setWatch('AAA', true)).rejects
      .toMatchObject({ reason: 'session' })

    fetchMock.mockImplementation(() => answer(401))
    await expect(api.setWatch('AAA', true)).rejects
      .toMatchObject({ reason: 'session' })
  })

  it('separates a forbidden endpoint from an expired session', () => {
    // Reloading fixes one and will never fix the other, so they cannot share
    // a sentence. 403 stopped meaning "signed out" when the admin operations
    // endpoint began answering it to signed-in non-admins.
    expect(new BoardUnavailable('session').message).toMatch(/sign in again/i)
    expect(new BoardUnavailable('forbidden').message).toMatch(/not allowed/i)
    expect(new BoardUnavailable('forbidden').message)
      .not.toEqual(new BoardUnavailable('session').message)
  })
})

describe('when the board asks again on its own', () => {
  // The function react-query calls for `refetchInterval`, read back as the
  // numbers it names. The spread is drawn once per answer and kept on the
  // wait, so every reading of the schedule between two answers agrees -- and
  // with it at zero, each number below is the schedule's own.
  const at = Date.parse('2026-08-22T19:00:00Z')
  const shell = (over: Partial<BoardPayload> = {}) => payload({
    shared: true, pending: true, rows: null, as_of: null, built_at: null,
    generated_at: null, age_seconds: null, retry_after_ms: 1000,
    watching: [], watch_rows: [], ...over,
  })
  const reading = (board: BoardPayload,
                   over: Partial<Parameters<typeof boardInterval>[1]> = {}) => ({
    visible: true, fetching: false, received: at, now: at,
    wait: beginWait('k', board, at, () => 0), ...over,
  })

  it('walks the schedule for a board being built, from the server\'s floor up', () => {
    const board = shell()
    expect(boardInterval(board, reading(board))).toBe(1000)

    const wait = beginWait('k', board, at, () => 0)
    wait.attempt = 3
    wait.anchor = at + 10_000
    expect(boardInterval(board, reading(board, { wait, now: at + 10_000 })))
      .toBe(3000)
  })

  it('settles at five seconds once the reader has waited half a minute', () => {
    const board = shell()
    const wait = beginWait('k', board, at, () => 0)
    wait.attempt = 9
    wait.anchor = at + 30_000
    expect(boardInterval(board, reading(board, { wait, now: at + 30_000 })))
      .toBe(5000)
  })

  it('never asks a busy generation sooner than it said to', () => {
    const board = shell({ pending: false, busy: true, retry_after_ms: 5000 })
    expect(boardInterval(board, reading(board))).toBe(5000)
  })

  it('asks every five seconds while a refresh is queued', () => {
    const board = payload({ shared: true, stale: true, age_seconds: 180,
                            retry_after_ms: 5000 })
    expect(boardInterval(board, reading(board))).toBe(5000)
  })

  it('goes to look a step after a shared board passes its fresh bound', () => {
    // Sent fresh, so the server named no floor: the first ask is the
    // schedule's opening step, and it is the ask that gets a refresh queued.
    const board = payload({ shared: true, age_seconds: 110 })
    const now = at + 10_001
    const wait = beginWait('k', board, now, () => 0)
    expect(owesABoard(board, at, now)).toBe(true)
    expect(boardInterval(board, reading(board, { wait, now }))).toBe(1000)

    // Its answer is stale by then with no floor of its own, and the wait
    // takes the refresh's five seconds.
    hear(wait, payload({ shared: true, age_seconds: 130 }), now + 1000, () => 0)
    expect(wait.floor).toBe(5000)
  })

  it('sets the wait for a fresh shared board\'s refresh at its bound, and its first ask a step past it', () => {
    // The bound's own clock, needing nobody to redraw the page: strictly
    // past the bound, as the server reads it, then the opening step.
    const board = payload({ shared: true, age_seconds: 110 })
    const wait = nextWait(null, 'k', board, at, at, () => 0)
    expect(wait?.since).toBe(at + 10_001)
    expect(boardInterval(board, reading(board, { wait }))).toBe(11_001)
    // Read again later, it is the same wait and the same instant.
    expect(nextWait(wait, 'k', board, at, at + 5000)).toBe(wait)
    expect(boardInterval(board, reading(board, { wait, now: at + 5000 })))
      .toBe(6001)
    // Nothing is set for a board a worker built for itself, and a new
    // selection is a new question.
    expect(nextWait(null, 'k', payload(), at, at)).toBeNull()
    expect(nextWait(wait, 'other', board, at, at)).not.toBe(wait)
  })

  it('counts each step from the last answer, not from whenever it is read', () => {
    // react-query reads this on every render. A delay counted from "now"
    // would slide the ask away every time the page drew itself.
    const board = shell()
    expect(boardInterval(board, reading(board, { now: at + 400 }))).toBe(600)
  })

  it('keeps the floor through an answer that had nothing to say', () => {
    const board = shell({ retry_after_ms: 5000 })
    const wait = beginWait('k', board, at, () => 0)
    hear(wait, null, at + 5000, () => 0)
    expect(wait.floor).toBe(5000)
    expect(boardInterval(board, reading(board, { wait, now: at + 5000 })))
      .toBe(5000)
  })

  it('asks nothing on a timer for a board with nothing coming', () => {
    // Fresh, whoever built it: the fresh bound's own clock starts any wait.
    for (const shared of [true, false]) {
      const board = payload({ shared })
      expect(boardInterval(board, reading(board))).toBe(false)
    }
    // Past the bound and built by a worker for itself: nothing stands behind
    // it to refresh, and asking again would build another synchronously.
    // Marked stale, never polled.
    const direct = payload({ shared: false, age_seconds: 300 })
    expect(owesABoard(direct, at, at)).toBe(false)
    expect(boardInterval(direct, reading(direct))).toBe(false)
  })

  it('asks nothing for a hidden tab, beside an ask already out, or with nothing loaded', () => {
    const board = shell()
    expect(boardInterval(board, reading(board, { visible: false }))).toBe(false)
    expect(boardInterval(board, reading(board, { fetching: true }))).toBe(false)
    expect(boardInterval(undefined, reading(board))).toBe(false)
  })
})

describe('a mark that lands while a board is still being built', () => {
  it('adopts the list into the waiting shell, which stays waiting and as old as it was', async () => {
    const setWatch = vi.spyOn(api, 'setWatch').mockResolvedValue(['AAA'])
    const fetchBoard = vi.spyOn(api, 'fetchBoard')
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const shell = payload({
      shared: true, pending: true, rows: null, as_of: null, built_at: null,
      generated_at: null, age_seconds: null, retry_after_ms: 1000,
      watching: [], watch_rows: [],
    })
    client.setQueryData(boardKey(selection), shell, { updatedAt: 1234 })
    function Mark() {
      const watch = useWatchMutation()
      return (
        <button type="button"
                onClick={() => watch.mutate({ ticker: 'AAA', on: true })}>
          Mark
        </button>
      )
    }
    render(
      <QueryClientProvider client={client}>
        <Mark />
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Mark' }))
    await waitFor(() => {
      expect(client.getQueryData<BoardPayload>(boardKey(selection))?.watching)
        .toEqual(['AAA'])
    })

    const state = client.getQueryState<BoardPayload>(boardKey(selection))
    expect(state?.data?.rows).toBeNull()
    expect(state?.data?.pending).toBe(true)
    expect(state?.data?.watch_rows).toEqual([])
    // When it arrived is what its age and its wait are counted from, and a
    // mark changes neither.
    expect(state?.dataUpdatedAt).toBe(1234)
    expect(setWatch).toHaveBeenCalledWith('AAA', true)
    // Nobody is reading this board, so nothing asks for it now.
    expect(fetchBoard).not.toHaveBeenCalled()
  })
})

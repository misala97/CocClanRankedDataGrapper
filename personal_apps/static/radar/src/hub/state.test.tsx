// The shared server state, exercised rather than described.
//
// The key-builders have their own tests. These are about what the hooks DO
// with them: which payload is allowed to seed which key, what a failed refresh
// leaves on screen, and which failures are permanent enough to stop retrying.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { payload } from '../fixtures'
import type { BoardPayload, Selection } from '../types'
import { selectionOf, useBoard } from './queries'

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
    expect(screen.getByTestId('stamp')).toHaveTextContent(initial.generated_at)
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

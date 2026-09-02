// The star's optimism: it flips at once, the server is told, the board is
// refetched on success, and it reverts on failure.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BoardPage } from './BoardPage'
import { detail, payload, row } from '../fixtures'

function stubFetch({ watchFails = false, watching = ['BBB'] } = {}) {
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes('/api/watch/')) {
      if (watchFails) return { ok: false, redirected: false, status: 500, json: async () => ({}) }
      return { ok: true, redirected: false, status: 200, json: async () => ({ watching }) }
    }
    if (url.includes('/api/ticker/')) {
      return { ok: true, redirected: false, status: 200,
        json: async () => detail(url.split('/api/ticker/')[1]!.split('?')[0]!) }
    }
    return { ok: true, redirected: false, status: 200,
      json: async () => payload({ watching, watch_rows: [row({ ticker: 'BBB' })] }) }
  })
  vi.stubGlobal('fetch', spy)
  return spy
}
const calls = (part: string) => vi.mocked(fetch).mock.calls.filter((c) => String(c[0]).includes(part))

beforeEach(() => { window.history.replaceState(null, '', '/radar/') })
afterEach(() => vi.unstubAllGlobals())

describe('marking a stock', () => {
  it('flips the star at once, tells the server, then refetches the board', async () => {
    stubFetch()
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('button', { name: 'Watch BBB' }))

    expect(screen.getByRole('button', { name: 'Stop watching BBB' })).toBeInTheDocument()
    await waitFor(() => expect(calls('/api/watch/BBB')).toHaveLength(1))
    await waitFor(() => expect(calls('/api/board')).toHaveLength(1))
  })

  it('reverts the star when the server refuses', async () => {
    stubFetch({ watchFails: true })
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('button', { name: 'Watch BBB' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeInTheDocument())
    expect(calls('/api/board')).toHaveLength(0)
  })

  it('keeps a later mark when an earlier unmark fails late', async () => {
    /* Codex's case: removing A fails after adding B succeeded. The late
       failure must undo only A's flip, never restore a snapshot that
       predates B. Mutations run one at a time, in order. */
    let failA!: () => void
    const aFailure = new Promise<unknown>((resolve) => {
      failA = () => resolve({ ok: false, redirected: false, status: 500, json: async () => ({}) })
    })
    const spy = vi.fn(async (url: string) => {
      if (url.includes('/api/watch/AAA')) return aFailure
      if (url.includes('/api/watch/BBB')) {
        return { ok: true, redirected: false, status: 200, json: async () => ({ watching: ['AAA', 'BBB'] }) }
      }
      if (url.includes('/api/ticker/')) {
        return { ok: true, redirected: false, status: 200,
          json: async () => detail(url.split('/api/ticker/')[1]!.split('?')[0]!) }
      }
      return { ok: true, redirected: false, status: 200,
        json: async () => payload({ watching: ['AAA', 'BBB'],
                                    watch_rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' })] }) }
    })
    vi.stubGlobal('fetch', spy)
    render(<BoardPage initial={payload({ watching: ['AAA'] })} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getAllByRole('button', { name: 'Stop watching AAA' })[0]!)
    await userEvent.click(screen.getByRole('button', { name: 'Watch BBB' }))
    await waitFor(() => expect(calls('/api/watch/AAA')).toHaveLength(1))
    failA()

    // AAA is also the selected ticker, so its name appears on the row star
    // and on the panel's button alike.
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Stop watching AAA' }).length).toBeGreaterThan(0))
    await waitFor(() => expect(calls('/api/watch/BBB')).toHaveLength(1))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop watching BBB' })).toBeInTheDocument())
    // One refetch, after the last mutation settled.
    await waitFor(() => expect(calls('/api/board')).toHaveLength(1))
    expect(screen.getAllByRole('button', { name: 'Stop watching AAA' }).length).toBeGreaterThan(0)
  })

  it('opens on the watching list the server embedded', () => {
    stubFetch()
    render(<BoardPage initial={payload({ watching: ['AAA'] })} />)

    expect(screen.getByRole('button', { name: 'Stop watching AAA' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeInTheDocument()
  })
})

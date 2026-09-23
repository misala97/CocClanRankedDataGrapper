// The star's optimism: it flips at once, the server is told, the board is
// refetched on success, and it reverts on failure.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BoardPage } from './BoardPage'
import { detail, payload, row } from '../fixtures'
import type { BoardPayload } from '../types'

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

/** Every board and mark request held until the test answers it, so the order
 *  things land in is the test's to choose. An abort rejects a held board
 *  request, as it does a real one. */
function holdRequests() {
  const answered = (body: unknown) =>
    ({ ok: true, redirected: false, status: 200, json: async () => body })
  const boards: { url: string; signal: AbortSignal
                  answer: (board: BoardPayload) => void; fail: () => void }[] = []
  const marks: ((watching: string[]) => void)[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/api/ticker/')) {
      return Promise.resolve(
        answered(detail(url.split('/api/ticker/')[1]!.split('?')[0]!)))
    }
    return new Promise((resolve, reject) => {
      if (url.includes('/api/watch/')) {
        marks.push((watching) => resolve(answered({ watching })))
        return
      }
      init!.signal!.addEventListener('abort', () => {
        reject(new DOMException('aborted', 'AbortError'))
      })
      boards.push({
        url, signal: init!.signal!,
        answer: (board) => resolve(answered(board)),
        fail: () => resolve({ ok: false, redirected: false, status: 503,
                              json: async () => ({}) }),
      })
    })
  }))
  return { boards, marks }
}

/** On vitest's fake clock, clicking with a plain event: user-event drives a
 *  clock of its own and deadlocks against the fake one. */
const advance = (ms: number) =>
  act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const click = (element: Element) =>
  act(async () => { fireEvent.click(element) })
/** Let a held request answer, and whatever follows from it run. */
const land = async (settle: () => void) => {
  await act(async () => { settle() })
  await advance(0)
}
const withBBB = (over: Partial<BoardPayload> = {}) => payload({
  watching: ['BBB'], watch_rows: [row({ ticker: 'BBB' })], ...over,
})

describe('the refetch after a mark', () => {
  // One board request follows the last mark to land, to bring its watched row
  // in. It asks about the board the reader is on when it goes out -- which,
  // while the mark was out, need not be the one the star was clicked on -- and
  // it goes out after the reader's own request, never over it: an abort stops
  // this page listening, not a build a worker has already started.
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  const moveWindow = async (hours: string) => {
    await click(screen.getByRole('button', { name: /Change window/i }))
    await click(screen.getByRole('button', { name: hours }))
  }
  const urls = (boards: { url: string }[]) => boards.map((b) => b.url)

  it('asks about the window the reader moved to while the mark was out', async () => {
    const { boards, marks } = holdRequests()
    render(<BoardPage initial={payload()} />)
    await advance(0)

    await click(screen.getByRole('button', { name: 'Watch BBB' }))
    await moveWindow('12h')
    await advance(300)
    expect(urls(boards)).toEqual([expect.stringContaining('window=12')])

    await land(() => marks[0]!(['BBB']))

    // Nothing about four hours goes out, and the twelve-hour request is left
    // to answer.
    expect(urls(boards).filter((url) => url.includes('window=4'))).toEqual([])
    expect(boards[0]!.signal.aborted).toBe(false)
    expect(boards).toHaveLength(1)

    // It was asked before the mark landed, so its list does not have the mark
    // yet -- and must not take the star back. The refetch follows it.
    await land(() => boards[0]!.answer(payload({ window_hours: 12 })))
    expect(screen.getByRole('button', { name: 'Stop watching BBB' }))
      .toBeInTheDocument()
    expect(boards).toHaveLength(2)
    expect(boards[1]!.url).toContain('window=12')
    expect(boards[1]!.url).not.toContain('poll=1')

    await land(() => boards[1]!.answer(withBBB({ window_hours: 12 })))
    expect(urls(boards).filter((url) => url.includes('window=4'))).toEqual([])
    expect(window.location.search).toContain('window=12')
    expect(screen.getByRole('button', { name: 'Stop watching BBB' }))
      .toBeInTheDocument()
  })

  it('lets the reader\'s own request answer, then asks once', async () => {
    const { boards, marks } = holdRequests()
    // A board a worker built, a second from its expiry: the refetch that goes
    // out then is the reader's own request.
    render(<BoardPage initial={payload({ age_seconds: 599 })} />)
    await advance(1100)
    expect(boards).toHaveLength(1)
    expect(boards[0]!.url).not.toContain('poll=1')

    await click(screen.getByRole('button', { name: 'Watch BBB' }))
    await land(() => marks[0]!(['BBB']))

    expect(boards[0]!.signal.aborted).toBe(false)
    expect(boards).toHaveLength(1)

    await land(() => boards[0]!.answer(payload()))
    expect(screen.getByRole('button', { name: 'Stop watching BBB' }))
      .toBeInTheDocument()
    expect(boards).toHaveLength(2)
    expect(boards[1]!.url).toBe(boards[0]!.url)

    await land(() => boards[1]!.answer(withBBB()))
    await advance(5000)
    expect(boards).toHaveLength(2)
  })

  it('sends nothing more when the mark lands inside a control\'s quarter second', async () => {
    const { boards, marks } = holdRequests()
    render(<BoardPage initial={payload()} />)
    await advance(0)

    await click(screen.getByRole('button', { name: 'Watch BBB' }))
    await moveWindow('12h')
    await advance(100)
    await land(() => marks[0]!(['BBB']))
    // The request the window sends has not gone out yet. When it does, it is
    // after the mark, and it carries it.
    expect(boards).toHaveLength(0)

    await advance(200)
    expect(urls(boards)).toEqual([expect.stringContaining('window=12')])
    await land(() => boards[0]!.answer(withBBB({ window_hours: 12 })))
    await advance(5000)
    expect(boards).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Stop watching BBB' }))
      .toBeInTheDocument()
  })

  it('asks nothing more when a control moves while the refetch waits', async () => {
    // The mark landed with the reader's own request out, so the refetch was
    // waiting for it -- and then the reader moved the window. The request
    // that sends goes out after the mark, and carries it.
    const { boards, marks } = holdRequests()
    render(<BoardPage initial={payload({ age_seconds: 599 })} />)
    await advance(1100)
    expect(boards).toHaveLength(1)

    await click(screen.getByRole('button', { name: 'Watch BBB' }))
    await land(() => marks[0]!(['BBB']))
    await moveWindow('12h')
    await advance(300)
    expect(urls(boards)).toEqual([expect.stringContaining('window=4'),
                                  expect.stringContaining('window=12')])

    await land(() => boards[1]!.answer(withBBB({ window_hours: 12 })))
    await advance(5000)
    expect(boards).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Stop watching BBB' }))
      .toBeInTheDocument()
  })

  it('lets go of a ticker the new window does not list, as the failed change would have', async () => {
    // The window moved and its request failed, so the four-hour board is
    // still up, said to be the last one that loaded. The refetch after a
    // mark is then the first answer about twelve hours, and it treats the
    // reader's ticker as that change would have.
    const { boards, marks } = holdRequests()
    render(<BoardPage initial={payload()} />)
    await advance(0)
    await moveWindow('12h')
    await advance(300)
    await land(() => boards[0]!.fail())
    expect(screen.getByRole('alert'))
      .toHaveTextContent('Showing the last board that loaded.')
    expect(document.querySelector('.row.on')).toHaveTextContent('AAA')

    await click(screen.getByRole('button', { name: 'Watch BBB' }))
    await land(() => marks[0]!(['BBB']))
    expect(boards[1]!.url).toContain('window=12')
    await land(() => boards[1]!.answer(withBBB({
      window_hours: 12, rows: [row({ ticker: 'ZZZ' }), row({ ticker: 'BBB' })],
    })))

    expect(document.querySelector('.row.on')).toHaveTextContent('ZZZ')
    expect(window.location.search).toContain('t=ZZZ')
    await advance(0)
  })
})

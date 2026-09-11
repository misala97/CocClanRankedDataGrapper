import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BoardPayload, Detail } from '../types'
import { detail, payload, row } from '../fixtures'
import { BoardPage } from './BoardPage'

/** Route by URL. The page makes two different requests now, and a stub that
 *  answered both with a board payload would hand the panel the wrong shape. */
function stubFetch(board: BoardPayload = payload()) {
  const spy = vi.fn(async (url: string) => ({
    ok: true,
    redirected: false,
    json: async () => (url.includes('/api/ticker/')
      ? detail(url.split('/api/ticker/')[1]!.split('?')[0]!,
        (new URL(url, 'https://radar.test').searchParams.get('market') as Detail['market'])
          ?? 'us')
      : board),
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => {
  stubFetch()
  window.history.replaceState(null, '', '/radar/')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const boardCalls = () => vi.mocked(fetch).mock.calls
  .map((c) => String(c[0])).filter((u) => u.includes('/api/board'))

/** For a test whose answer depends on the controls' quarter-second debounce:
 *  on vitest's fake clock that time passes only when the test says so, and a
 *  loaded machine cannot stretch the gap between two clicks past it.
 *  user-event drives a clock of its own and deadlocks against the fake one,
 *  so those tests click with a plain event. */
const advance = (ms: number) =>
  act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const click = (element: Element) =>
  act(async () => { fireEvent.click(element) })

describe('the two panes', () => {
  it('renders the peak chatter hour in Radar\'s Berlin timezone', async () => {
    render(<BoardPage initial={payload()} />)

    await screen.findByText(/AAA is being discussed/)
    expect(screen.getByText('16:00 CEST')).toBeInTheDocument()
  })

  it('lists one row per ticker, with no promoted tier', () => {
    /* The two-tier arrangement is gone. It bought visual variety at the cost
       of making identical data look like two different kinds of thing. */
    const { container } = render(<BoardPage initial={payload()} />)

    expect(container.querySelectorAll('.row')).toHaveLength(4)
    expect(container.querySelectorAll('.lead')).toHaveLength(0)
  })

  it('opens on the top row so the page is useful with no clicks', async () => {
    render(<BoardPage initial={payload()} />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /AAA/ }))
        .toHaveAttribute('aria-current', 'true'))
  })

  it('opens on the ticker in the address bar instead, when there is one', async () => {
    /* "What happened to the one I spotted yesterday" is a real question for a
       radar, so a bookmarked ticker has to survive a reload. */
    window.history.replaceState(null, '', '/radar/?t=CCC')

    render(<BoardPage initial={payload()} />)

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /CCC/ }))
        .toHaveAttribute('aria-current', 'true'))
  })

  it('does not fetch the board on mount -- it is already in the document', () => {
    render(<BoardPage initial={payload()} />)

    expect(boardCalls()).toHaveLength(0)
  })

  it('fetches the panel for the opening ticker', async () => {
    render(<BoardPage initial={payload()} />)

    await waitFor(() => expect(vi.mocked(fetch).mock.calls
      .some((c) => String(c[0]).includes('/api/ticker/AAA'))).toBe(true))
  })
})

describe('selecting a ticker', () => {
  it('swaps the panel without refetching the board', async () => {
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))

    await screen.findByText(/BBB is being discussed/)
    expect(boardCalls()).toHaveLength(0)
  })

  it('puts the ticker in the address bar', async () => {
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))

    await waitFor(() =>
      expect(window.location.search).toContain('t=BBB'))
  })
})

describe('the controls', () => {
  it('does not show a loaded US panel while Germany is loading', async () => {
    /* Detail state is retained so a retry can recover, but it is only valid
       for the request that produced it. A market change must put that cached
       US view behind a loader before the German response is available. */
    let resolveDe!: (response: object) => void
    const deResponse = new Promise<object>((resolve) => { resolveDe = resolve })
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/board')) {
        return Promise.resolve({ ok: true, redirected: false,
          json: async () => payload({ market: 'de' }) })
      }
      if (url.includes('market=de')) return deResponse
      return Promise.resolve({ ok: true, redirected: false,
        json: async () => detail('AAA', 'us') })
    }))

    render(<BoardPage initial={payload()} />)
    expect(await screen.findByText(/^AAA is being discussed\.$/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: 'Germany' }))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
      .some((url) => url.includes('/api/ticker/AAA?') && url.includes('market=de')))
      .toBe(true))
    expect(screen.getByRole('main', { busy: true })).toHaveTextContent('Loading AAA')
    expect(screen.queryByText(/^AAA is being discussed\.$/)).toBeNull()

    resolveDe({ ok: true, redirected: false, json: async () => detail('AAA', 'de') })
    expect(await screen.findByText(/AAA on de is being discussed/)).toBeInTheDocument()
  })

  it('keeps the Germany panel when an aborted US response arrives late', async () => {
    /* An abort asks the transport to stop but cannot unsend a response already
       in flight. The late US payload used to overwrite Germany's same-ticker
       panel because only the ticker was checked before rendering it. */
    let resolveUs!: (response: object) => void
    let resolveDe!: (response: object) => void
    const usResponse = new Promise<object>((resolve) => { resolveUs = resolve })
    const deResponse = new Promise<object>((resolve) => { resolveDe = resolve })
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/board')) {
        return Promise.resolve({ ok: true, redirected: false,
          json: async () => payload({ market: 'de' }) })
      }
      return url.includes('market=de') ? deResponse : usResponse
    }))

    render(<BoardPage initial={payload()} />)
    await userEvent.click(screen.getByRole('radio', { name: 'Germany' }))

    await waitFor(() => expect(vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
      .some((url) => url.includes('/api/ticker/AAA?') && url.includes('market=de')))
      .toBe(true))
    resolveDe({ ok: true, redirected: false, json: async () => detail('AAA', 'de') })
    expect(await screen.findByText(/AAA on de is being discussed/)).toBeInTheDocument()

    resolveUs({ ok: true, redirected: false, json: async () => detail('AAA', 'us') })
    await waitFor(() => expect(screen.getByText(/AAA on de is being discussed/))
      .toBeInTheDocument())
    expect(screen.queryByText(/^AAA is being discussed\.$/)).toBeNull()
  })

  it('switches market while retaining ticker, filters, and panel span', async () => {
    /* The market is price context, not a reset button: the reader keeps the
       company and every filter while swapping the venue underneath it. */
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)
    await userEvent.click(screen.getByRole('button', { name: '1M' }))

    await userEvent.click(screen.getByRole('radio', { name: 'Germany' }))

    await waitFor(() => expect(boardCalls()).toContain(
      '/radar/api/board?sources=bluesky%2Cfourchan%2Creddit&window=4&segment=&market=de'))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
      .some((url) => url.includes('/api/ticker/AAA?')
        && url.includes('sources=bluesky%2Cfourchan%2Creddit')
        && url.includes('window=4') && url.includes('span=1M')
        && url.includes('market=de'))).toBe(true))
    expect(window.location.search).toContain('market=de')
    expect(window.location.search).toContain('t=AAA')
    expect(window.location.search).toContain('window=4')
    expect(screen.getByRole('button', { name: '1M' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('keeps the selected company when the other market board omits it', async () => {
    /* On the fake clock, so the German board has answered by the time this
       looks. On the real one every assertion here was already true before
       the debounce let that request out -- `t=BBB` was the row click's own
       doing -- and the test usually ended first, the board it is named for
       never asked for. */
    vi.useFakeTimers()
    render(<BoardPage initial={payload()} />)
    await advance(0)
    expect(screen.getByText(/AAA is being discussed/)).toBeInTheDocument()
    await click(screen.getByRole('link', { name: /BBB/ }))

    stubFetch(payload({ market: 'de', market_venue: 'Xetra',
      rows: [row({ ticker: 'AAA' })] }))
    await click(screen.getByRole('radio', { name: 'Germany' }))
    await advance(300)

    expect(boardCalls()).toEqual([
      '/radar/api/board?sources=bluesky%2Cfourchan%2Creddit&window=4&segment=&market=de'])
    // The German board is on screen, and BBB is not on it...
    expect(document.querySelectorAll('.row')).toHaveLength(1)
    // ...but the reader is still on BBB: in the address bar the answer
    // wrote, and in the panel, which now asks about it on the German market.
    expect(window.location.search).toContain('market=de')
    expect(window.location.search).toContain('t=BBB')
    expect(vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
      .some((url) => url.includes('/api/ticker/BBB?') && url.includes('market=de')))
      .toBe(true)
  })

  it('names the venue, session, and next boundary in the header', () => {
    render(<BoardPage initial={payload({
      market: 'de', market_venue: 'Xetra', session: 'regular',
      next_boundary_label: 'closes',
      next_boundary_at: '2026-08-28T15:30:00Z',
    })} />)

    /* The enum used to be printed raw ("regular"); the status line says it
       as a word now, with real dot separators so the announcement a
       role="status" change produces keeps them. */
    // The head's status line is the FIRST status region; the empty-board
    // account further down is its own.
    const [head] = screen.getAllByRole('status')
    expect(head).toHaveTextContent('Xetra open · closes 17:30')
  })

  it('refetches and rewrites the address bar when a source is dropped', async () => {
    render(<BoardPage initial={payload()} />)

    // The sources fold under the summary line since 2026-09-01.
    await userEvent.click(screen.getByRole('button', { name: /change/i }))
    await userEvent.click(screen.getByRole('button', { name: /4chan/ }))

    await waitFor(() => expect(boardCalls()).toHaveLength(1))
    expect(boardCalls()[0]).toBe(
      '/radar/api/board?sources=bluesky%2Creddit&window=4&segment=&market=us')
    await waitFor(() =>
      expect(window.location.search)
        .toContain('sources=bluesky%2Creddit&window=4&segment='))
  })

  it('keeps All in the address bar rather than omitting it', async () => {
    /* The server's default segment is Discover, so a URL with no segment
       param reloads as Discover. Sharing the All view has to survive a
       reload, which means the empty value is the state, not the absence of
       one. */
    render(<BoardPage initial={payload({ segments: ['discover'] })} />)

    await userEvent.click(screen.getByRole('button', { name: /^All/ }))

    await waitFor(() => expect(window.location.search).toContain('segment='))
    expect(window.location.search).not.toContain('segment=discover')
  })

  it('will not let the last source be turned off', async () => {
    render(<BoardPage initial={payload({ sources: ['bluesky'] })} />)

    await userEvent.click(screen.getByRole('button', { name: /change/i }))

    expect(screen.getByRole('button', { name: /Bluesky/ }))
      .toHaveAttribute('aria-disabled', 'true')
  })

  it('coalesces a burst of control changes into one request', async () => {
    /* Every toggle used to fire its own fetch, aborting the previous one.
       Five quick clicks queued five board builds on the server and the last
       waited past the 8s timeout -- "The board did not answer in time"
       during ordinary toggling (critique, 2026-09-01).

       On the fake clock. Against the real one this raced the debounce: on a
       loaded machine two clicks could land more than a quarter second apart,
       the first change went out alone, and the test failed about half of
       the whole-suite runs. */
    vi.useFakeTimers()
    render(<BoardPage initial={payload()} />)

    await click(screen.getByRole('button', { name: /change/i }))
    await click(screen.getByRole('button', { name: /4chan/ }))
    await advance(200)
    await click(screen.getByRole('button', { name: /Reddit/ }))
    // Four hundred milliseconds into the burst and nothing has gone out:
    // each change starts the quiet period over.
    await advance(200)
    expect(boardCalls()).toHaveLength(0)

    await advance(50)
    expect(boardCalls()).toHaveLength(1)
    expect(boardCalls()[0]).toContain('sources=bluesky&')
    // And nothing else arrives later.
    await advance(10_000)
    expect(boardCalls()).toHaveLength(1)
  })

  it('renders every view whatever the data says', () => {
    /* Michi, 2026-08-23: "the settings are bad and switch around". They did --
       chips were filtered by count, so a segment with no rows vanished and
       came back as data changed, moving everything else under the cursor.
       Since 2026-09-01 the strip is five views; Discover's members appear
       under it only while Discover is in force (Controls.test.tsx). */
    render(<BoardPage initial={payload({
      segment_counts: { all: 1, micro: 1 }, segments: ['discover'],
    })} />)

    for (const label of ['Discover', 'All', 'Large', 'Mid', 'Micro',
                         'IPO', 'Unknown', 'Funds']) {
      expect(screen.getByRole('button', { name: new RegExp(`^${label}`) }))
        .toBeInTheDocument()
    }
  })

  it('does not put the chart span in the board controls', () => {
    /* The span belongs to the panel: it changes one ticker's chart, not which
       rows the board lists. */
    render(<BoardPage initial={payload()} />)

    expect(screen.queryByRole('button', { name: /^3M$/ })).toBeNull()
  })
})

describe('when the board changes under the selection', () => {
  it('moves to the top row if the selected ticker is filtered out', async () => {
    /* Leaving the panel on a ticker the list no longer contains puts a stock
       on screen that the list beside it says is not in view. */
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    stubFetch(payload({ rows: [row({ ticker: 'ZZZ' })] }))
    await userEvent.click(screen.getByRole('button', { name: /change/i }))
    await userEvent.click(screen.getByRole('button', { name: /2\+/ }))

    await waitFor(() =>
      expect(window.location.search).toContain('t=ZZZ'))
  })
})

describe('the account of what was left out', () => {
  it('is shown beneath the rows', () => {
    render(<BoardPage initial={payload({
      excluded: { too_few_voices: 9, one_venue: 4 },
    })} />)

    expect(screen.getByText(/13 other tickers/)).toBeInTheDocument()
  })
})

describe('when the board cannot be reached', () => {
  it('keeps the last board and says the refresh failed', async () => {
    render(<BoardPage initial={payload()} />)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('nope') }))

    await userEvent.click(screen.getByRole('button', { name: /change/i }))
    await userEvent.click(screen.getByRole('button', { name: /4chan/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not reach/)
    expect(screen.getByRole('link', { name: /AAA/ })).toBeInTheDocument()
  })
})

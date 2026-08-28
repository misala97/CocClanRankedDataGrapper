// What the board does when the data is not the data it was designed against.
//
// Every case in here was reproduced in a browser against the running app
// before it was fixed -- a served 500, a truncated payload, a 404 from a
// bookmarked `?t=`, a pasted wall of text, a sub-penny quote. The assertions
// are written against the symptom that was actually visible, not against the
// implementation that produces it.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BoardUnavailable, fetchBoard } from './api'
import { BoardPage } from './board/BoardPage'
import { Boundary } from './Broken'
import { parsePayload } from './embedded'
import { Posts } from './detail/Posts'
import type { BoardPayload, Detail, Post, Row } from './types'

function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, ratio: 20 / 6,
    authors: 9, text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    clauses: [{ kind: 'ratio', text: '3x its normal' }],
    ...over,
  }
}

function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, venue_counts: { any: 2, multi: 1 },
    segment_counts: { all: 2, large: 2 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' })],
    excluded: {},
    ...over,
  }
}

function detail(ticker = 'AAA'): Detail {
  return {
    identity: {
      ticker, name: 'Alpha Inc', exchange: 'N', segment: 'large',
      market_cap: 1e9, ipo_date: '2020-01-01', price: 10, price_move: 0.012,
      price_status: 'ok', session: 'regular',
    },
    read: [{ kind: 'plain', text: `${ticker} is being discussed.` }],
    chart: {
      from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, (_, i) => 100 + i),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
      watched_from: '2026-08-18',
    },
    breakdown: {
      venues: [{ source: 'bluesky', mentions: 20, voices: 9 }],
      bullish: 4, neutral: 10, bearish: 2, disagreements: 1,
      top_author_share: 0.2, top_two_share: 0.3,
      peak_hour: '2026-08-22T14:00:00Z', peak_count: 9,
      first_seen: '2026-08-18', mentions: 20, voices: 9,
    },
    posts: [], post_total: 0,
  }
}

function stubFetch(board: BoardPayload = payload()) {
  const spy = vi.fn(async (url: string) => ({
    ok: true,
    redirected: false,
    status: 200,
    json: async () => (url.includes('/api/ticker/')
      ? detail(url.split('/api/ticker/')[1]!.split('?')[0]!)
      : board),
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

/** One failing status, for every request. */
function stubStatus(status: number) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: false, redirected: false, status, json: async () => ({}),
  })))
}

beforeEach(() => {
  stubFetch()
  window.history.replaceState(null, '', '/radar/')
})
afterEach(() => vi.unstubAllGlobals())

// ---------------------------------------------------------------------------

describe('the embedded payload', () => {
  it('is rejected rather than parsed into a page that throws later', () => {
    // Both of these used to reach React. `'{}'` is the one that hurt: it
    // parses, so the failure surfaced deep inside a render as
    // "Cannot read properties of undefined (reading '0')" and the whole
    // island unmounted to a blank viewport.
    expect(parsePayload('{}')).toBeNull()
    expect(parsePayload('{"rows":[{"ticker":"AAA"')).toBeNull()
    expect(parsePayload('')).toBeNull()
    expect(parsePayload(null)).toBeNull()
    expect(parsePayload('[]')).toBeNull()
  })

  it('accepts a board that has rows, including an empty one', () => {
    // An empty board is a legitimate answer -- a quiet Sunday -- and must not
    // be confused with a payload that never arrived.
    expect(parsePayload('{"rows":[]}')).not.toBeNull()
  })
})

describe('a zone that throws', () => {
  function Bomb(): never {
    throw new Error('kaboom')
  }

  it('leaves words on the page instead of unmounting the tree', () => {
    // The failure mode this exists for: a React island with no boundary
    // renders nothing at all, and the reader gets a white viewport.
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(<Boundary label="The panel"><Bomb /></Boundary>)

    expect(screen.getByRole('alert')).toHaveTextContent(/The panel could not be drawn/)
  })

  it('does not take the rest of the board down with it', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <div>
        <p>the list is still here</p>
        <Boundary label="The panel"><Bomb /></Boundary>
      </div>,
    )

    expect(screen.getByText('the list is still here')).toBeInTheDocument()
  })
})

describe('the panel across a row change', () => {
  it('keeps the chart span the reader chose', async () => {
    // The boundary around the panel was keyed on the selected ticker, which
    // remounts the CHILD as well as resetting the boundary -- so every row
    // click threw the panel's own state away and the span snapped back to 1Y.
    // Comparing three tickers at 1M was not possible. Found while adding the
    // chart's draw animation, which fires on exactly this path.
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('button', { name: '1M' }))
    await userEvent.click(screen.getByRole('link', { name: /BBB/ }))
    await screen.findByText(/BBB is being discussed/)

    expect(screen.getByRole('button', { name: '1M' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('still clears a tripped boundary when the ticker changes', () => {
    // The reason the key was there in the first place. Whatever replaces it
    // has to keep doing this, or one bad panel poisons every later one.
    vi.spyOn(console, 'error').mockImplementation(() => {})
    let explode = true
    function Sometimes() {
      if (explode) throw new Error('kaboom')
      return <p>recovered</p>
    }

    const { rerender } = render(
      <Boundary label="The panel" resetKey="AAA"><Sometimes /></Boundary>)
    expect(screen.getByRole('alert')).toBeInTheDocument()

    explode = false
    rerender(
      <Boundary label="The panel" resetKey="BBB"><Sometimes /></Boundary>)

    expect(screen.getByText('recovered')).toBeInTheDocument()
  })
})

describe('the chart draws itself', () => {
  it('separates the furniture from the data so the wipe has something to wipe', () => {
    render(<BoardPage initial={payload()} />)
    // Structural, and it is load-bearing: `.plot` is the group the clip-path
    // animation runs on. One clip on one group instead of ~780 animated bars
    // at the 3Y span.
    return screen.findByText(/AAA is being discussed/).then(() => {
      expect(document.querySelector('.pxchart .plot')).not.toBeNull()
      expect(document.querySelector('.pxchart .axes')).not.toBeNull()
    })
  })

  it('is drawn by default, not revealed by a class', () => {
    // The rule the whole motion pass hangs on: every animation here animates
    // the FROM. Nothing is made visible by an animation completing, so a
    // headless render, a background tab and prefers-reduced-motion all show a
    // finished chart. A `.plot` that needed a class to become visible would
    // ship blank in all three.
    render(<BoardPage initial={payload()} />)
    return screen.findByText(/AAA is being discussed/).then(() => {
      const plot = document.querySelector('.pxchart .plot')!
      expect(plot.getAttribute('class')).toBe('plot')
      expect(plot.querySelectorAll('rect.chat').length).toBeGreaterThan(0)
    })
  })
})

describe('what a failing status actually says', () => {
  // Everything that was not a redirect or a timeout collapsed into "Could not
  // reach the board", which reads as an offline browser. A bookmarked `?t=`
  // for a ticker that has dropped off answers 404, and the reader was told
  // their connection was down.
  const selection = { sources: ['bluesky'], minVenues: 1, segments: [], window: 4 }

  it('separates a missing ticker from an unreachable board', async () => {
    stubStatus(404)
    await expect(fetchBoard(selection)).rejects
      .toMatchObject({ reason: 'missing' })
  })

  it('names a server error as one', async () => {
    stubStatus(500)
    await expect(fetchBoard(selection)).rejects
      .toMatchObject({ reason: 'server' })
  })

  it('says so when it is being rate-limited', async () => {
    stubStatus(429)
    await expect(fetchBoard(selection)).rejects.toMatchObject({ reason: 'busy' })
  })

  it('treats a rejected session as a session, not a network fault', async () => {
    stubStatus(401)
    await expect(fetchBoard(selection)).rejects
      .toMatchObject({ reason: 'session' })
  })

  it('carries a sentence, not the bare reason word', async () => {
    stubStatus(404)
    const problem = await fetchBoard(selection)
      .then(() => null, (e: BoardUnavailable) => e)
    expect(problem?.message).toBe('Nothing here for that ticker.')
  })
})

describe('a panel that failed', () => {
  it('offers a way back rather than a dead end', async () => {
    // Reproduced with ?t=NOTATICKER against the running app: the panel showed
    // one amber sentence, the list had no selection, and there was no control
    // anywhere to get out of it.
    window.history.replaceState(null, '', '/radar/?t=NOPE')
    const board = payload()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (
      String(url).includes('/api/ticker/NOPE')
        ? { ok: false, redirected: false, status: 404, json: async () => ({}) }
        : { ok: true, redirected: false, status: 200,
            json: async () => (String(url).includes('/api/ticker/')
              ? detail(String(url).split('/api/ticker/')[1]!.split('?')[0]!)
              : board) }
    )))

    render(<BoardPage initial={board} />)

    expect(await screen.findByText(/Nothing here for that ticker/))
      .toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: /Show AAA instead/ }))

    expect(await screen.findByText(/AAA is being discussed/)).toBeInTheDocument()
  })

  it('still offers a way out when the DEAD ticker is the top row', async () => {
    // The board can list a ticker whose panel 404s: a symbol the extraction
    // found that the universe has no profile for lands on the board as
    // `unknown` and has no panel at all. Seen live with QQQ at rank one --
    // and an escape hatch pointing at "the top of the board" would then have
    // been a button that reselected the ticker that just failed.
    const board = payload()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (
      String(url).includes('/api/ticker/AAA')
        ? { ok: false, redirected: false, status: 404, json: async () => ({}) }
        : { ok: true, redirected: false, status: 200,
            json: async () => detail('BBB') }
    )))

    render(<BoardPage initial={board} />)
    await screen.findByText(/Nothing here for that ticker/)

    await userEvent.click(
      screen.getByRole('button', { name: /Show BBB instead/ }))

    expect(await screen.findByText(/BBB is being discussed/)).toBeInTheDocument()
  })

  it('can retry the same ticker without leaving it', async () => {
    stubStatus(500)
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/The board answered with an error/)

    stubFetch()
    await userEvent.click(screen.getByRole('button', { name: /Retry AAA/ }))

    expect(await screen.findByText(/AAA is being discussed/)).toBeInTheDocument()
  })
})

describe('an empty board', () => {
  it('does not invite a selection from a list with nothing in it', () => {
    render(<BoardPage initial={payload({ rows: [] })} />)

    expect(screen.queryByText(/Select a ticker/)).toBeNull()
  })

  it('names the two controls that would widen the net', () => {
    // With nothing excluded there is no account below to carry the way out,
    // and the board used to end on a full stop.
    render(<BoardPage initial={payload({ rows: [], excluded: {} })} />)

    expect(screen.getByText(/Nothing cleared the bar/)).toBeInTheDocument()
    // Both panes, and the SAME sentence in both. The three places that say
    // this had drifted into "widen the window", "a longer Score window" and
    // "switch the segment to All" -- two of which appeared on screen at once,
    // reading as two different suggestions instead of one.
    const ways = screen.getAllByText(/Try a longer/)
    expect(ways).toHaveLength(2)
    for (const way of ways) {
      expect(way.textContent)
        .toContain('Try a longer Score window, or the All segment')
    }
  })
})

describe('the marks', () => {
  it('says what each one on the board means', () => {
    // PRODUCT.md calls the marks load-bearing. The rows printed
    // `· no-print` and nothing on the surface defined it; the sentence had
    // been sitting unrendered in format.ts since the marks were added.
    render(<BoardPage initial={payload({
      rows: [row({ ticker: 'AAA', marks: ['no-print'] }), row({ ticker: 'BBB' })],
    })} />)

    expect(screen.getByText(/Any divergence here would be an artifact/))
      .toBeInTheDocument()
  })

  it('does not define a mark the header has already taken over', () => {
    // A mark every row carries is stated once in the header instead, and
    // defining it again below would explain the same word twice on one screen.
    render(<BoardPage initial={payload({
      rows: [row({ ticker: 'AAA', marks: ['provisional'] }),
             row({ ticker: 'BBB', marks: ['provisional'] })],
    })} />)

    expect(screen.queryByText(/thinly supported/)).toBeNull()
  })

  it('explains nothing when no row carries a mark', () => {
    render(<BoardPage initial={payload()} />)

    expect(screen.queryByText(/What the marks on these rows mean/)).toBeNull()
  })
})

describe('a post nobody sized', () => {
  function post(over: Partial<Post> = {}): Post {
    return {
      source: 'fourchan', author: 'anon', channel: '/biz/',
      created: '2026-08-22T19:00:00Z', title: null, body: 'short one',
      url: null, ...over,
    }
  }

  it('clips a wall of text rather than letting it become the page', () => {
    // Measured against the running app: one pasted copypasta ran past thirty
    // screen-heights and buried the twenty-four posts under it.
    const { container } = render(
      <Posts posts={[post({ body: 'x'.repeat(4000) })]} total={1} />)

    expect(container.querySelector('.post p.clamp')).not.toBeNull()
  })

  it('opens it in place rather than hiding it for good', async () => {
    const { container } = render(
      <Posts posts={[post({ body: 'x'.repeat(4000) })]} total={1} />)

    await userEvent.click(screen.getByRole('button', { name: /whole post/ }))

    expect(container.querySelector('.post p.clamp')).toBeNull()
  })

  it('leaves an ordinary post alone', () => {
    const { container } = render(<Posts posts={[post()]} total={1} />)

    expect(container.querySelector('.post p.clamp')).toBeNull()
    expect(screen.queryByRole('button', { name: /whole post/ })).toBeNull()
  })
})

describe('how old the board is', () => {
  it('stays quiet while it is still fresh', () => {
    vi.setSystemTime(new Date('2026-08-22T19:05:00Z'))
    render(<BoardPage initial={payload()} />)

    expect(screen.queryByText(/built/)).toBeNull()
    vi.useRealTimers()
  })

  it('says so once a tab has been left open', async () => {
    // The island fetches on a control change and never on a clock, so a board
    // from before lunch looks exactly like a live one.
    vi.setSystemTime(new Date('2026-08-22T22:00:00Z'))
    render(<BoardPage initial={payload()} />)

    expect(await screen.findByText(/built 3 hours ago/)).toBeInTheDocument()
    vi.useRealTimers()
  })
})

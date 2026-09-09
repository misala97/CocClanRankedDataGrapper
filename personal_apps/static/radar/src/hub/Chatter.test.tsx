import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { payload, quote, row } from '../fixtures'
import type { Row, Selection } from '../types'
import { Chatter } from './Chatter'

const initial = payload()
const selection: Selection = {
  market: initial.market, sources: initial.sources, segments: initial.segments,
  minVenues: initial.min_venues, window: initial.window_hours,
  sort: initial.sort, dir: initial.dir,
}
const payloadWithRows = (rows: Row[]) => payload({ rows })

function show(rows: Row[], onOpen = vi.fn()) {
  render(<Chatter board={payloadWithRows(rows)} selection={selection}
                  onOpen={onOpen} />)
  return onOpen
}

describe('the ranked list', () => {
  it('keeps the server’s order', () => {
    show([row({ ticker: 'CCC' }), row({ ticker: 'AAA' }), row({ ticker: 'BBB' })])
    const tickers = screen.getAllByTestId('rh-row-ticker').map((el) => el.textContent)
    expect(tickers).toEqual(['CCC', 'AAA', 'BBB'])
  })

  it('opens research from a row', async () => {
    const onOpen = show([row({ ticker: 'AAA' })])
    // Named specifically: the row now also carries a chevron to the same
    // destination, and /AAA/ alone matches both.
    await userEvent.click(screen.getByRole('button', { name: /^AAA Alpha Inc/ }))
    expect(onOpen).toHaveBeenCalledWith('AAA')
  })

  it('preserves unavailable quotes', () => {
    const r = row({ price: null, quote: { ...quote(), price: null, quality: 'unavailable' } })
    show([r])
    expect(screen.getByText('Price unavailable')).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })

  it('reads tone as a share of the DIRECTIONAL sample, not of the total', () => {
    // The old three-count treatment was built on an objection to the
    // DENOMINATOR, and it was right about that one: the residual holds
    // balanced reads and unclassified ones together, so a share over the
    // total says more than it knows. The correction keeps the objection and
    // names the denominator instead of withholding the reading.
    show([row({ tone: { bullish: 10, neutral: 45, bearish: 16 } })])
    expect(screen.getByText('38.5% bullish')).toBeVisible()
    expect(screen.getByText('26 directional / 71 total')).toBeVisible()
    // 10/71 would be 14.1%. Bar and percentage share one denominator.
    expect(screen.queryByText(/14\.1%/)).not.toBeInTheDocument()
  })

  it('draws the bar over the same denominator as the percentage', () => {
    const { container } = render(
      <Chatter board={payloadWithRows([row({
        tone: { bullish: 3, neutral: 96, bearish: 1 } })])}
        selection={selection} onOpen={vi.fn()} />)
    const segments = container.querySelectorAll('.rh-tonebar span')
    expect(segments).toHaveLength(2)
    expect((segments[0] as HTMLElement).style.flexGrow).toBe('0.75')
    expect((segments[1] as HTMLElement).style.flexGrow).toBe('0.25')
  })

  it('still refuses to round a rare share away to zero', () => {
    // The specific objection to the old percentage, and it still holds.
    show([row({ tone: { bullish: 1, neutral: 200, bearish: 199 } })])
    expect(screen.getByText('0.5% bullish')).toBeVisible()
    expect(screen.queryByText('0% bullish')).not.toBeInTheDocument()
  })

  it('keeps the exact counts reachable rather than printing them per row', () => {
    show([row({ tone: { bullish: 10, neutral: 45, bearish: 16 } })])
    // Not on the row: three stacked counts are what made it tall.
    expect(screen.queryByText(/45 unread or non-directional/))
      .not.toBeVisible()
    expect(screen.getByRole('button', { name: /tone is counted/i }))
      .toHaveAttribute('aria-expanded', 'false')
  })

  it('opens the tone detail with the exact counts and what they mean',
    async () => {
      show([row({ tone: { bullish: 10, neutral: 45, bearish: 16 } })])
      await userEvent.click(
        screen.getByRole('button', { name: /tone is counted/i }))
      const detail = screen.getByRole('group', { name: /tone is counted/i })
      expect(within(detail).getByText(/10 bullish, 16 bearish and 45/)).toBeVisible()
      expect(within(detail).getByText(/not known neutral sentiment/i)).toBeVisible()
    })

  it('closes a row detail on Escape and gives focus back', async () => {
    show([row()])
    const toggle = screen.getByRole('button', { name: /tone is counted/i })
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.keyboard('{Escape}')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveFocus()
  })

  it('opening a detail does not open research', async () => {
    const onOpen = show([row()])
    await userEvent.click(
      screen.getByRole('button', { name: /tone is counted/i }))
    await userEvent.click(screen.getByRole('button', { name: /which feeds/i }))
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('says there is no direction rather than printing 0% or 50%', () => {
    show([row({ tone: { bullish: 0, neutral: 45, bearish: 0 } })])
    expect(screen.getByText('No directional signal')).toBeVisible()
    expect(screen.getByText('45 unread or non-directional')).toBeVisible()
    expect(screen.queryByText(/0% bullish|50% bullish/)).not.toBeInTheDocument()
  })

  it('says the tone has not been sampled rather than calling it neutral', () => {
    show([row({ tone: { bullish: 0, neutral: 0, bearish: 0 } })])
    expect(screen.getByText(/no tone sample/i)).toBeVisible()
    expect(screen.queryByText(/% bullish/)).not.toBeInTheDocument()
    // And no breakdown control: a row with nothing counted has nothing to
    // break down, and the link cost a line on every row of a board whose
    // tone has not been read yet.
    expect(screen.queryByRole('button', { name: /tone is counted/i })).toBeNull()
  })

  it('reports broken tone counts as unavailable rather than as zero', () => {
    const { container } = render(
      <Chatter board={payloadWithRows([row({
        tone: { bullish: -1, neutral: 4, bearish: 2 } })])}
        selection={selection} onOpen={vi.fn()} />)
    expect(screen.getByText(/tone unavailable/i)).toBeVisible()
    // No bar at all rather than an empty one: an empty track reads as a
    // measured absence of direction, which is a different claim.
    expect(container.querySelector('.rh-tonebar')).toBeNull()
  })

  it('shows a measured zero move as zero', () => {
    // 0% is a fact: the price did not move. It must not read as "no data",
    // and "no data" must not read as 0%.
    show([row({ price: 10, price_move: 0, direction: 'flat' })])
    expect(screen.getByText('0.0%')).toBeVisible()
  })

  it('keeps the qualifying marks visible', () => {
    // PRODUCT.md: rendered, never hidden behind a hover.
    show([row({ marks: ['single-source', 'provisional'] })])
    expect(screen.getByText(/single source/i)).toBeVisible()
    expect(screen.getByText(/provisional/i)).toBeVisible()
  })

  it('says when a company has no baseline to compare against', () => {
    // ratio null is phrasing.py's own guard: there is no normal worth
    // dividing by. An em dash, never a 0x.
    show([row({ ratio: null, baseline_days: 2 })])
    expect(screen.queryByText(/0\.0×/)).not.toBeInTheDocument()
    expect(screen.getByText(/^New here/)).toBeVisible()
  })

  it('does not repeat the columns as prose', () => {
    // The server's phrase says "3.2x its normal, 2 venues, 6 people, price
    // +3%" -- which is the Attention, Sources, Voices and Price columns
    // again, in words, under every row. The phrase belongs on Research, where
    // it is the summary rather than a second copy of the table.
    show([row({ clauses: [{ kind: 'ratio', text: '8.4× its normal' },
                          { kind: 'venues', text: '2 venues' }] })])
    expect(screen.queryByText('8.4× its normal')).not.toBeInTheDocument()
    expect(screen.queryByText('2 venues')).not.toBeInTheDocument()
  })

  it('summarises the platforms that counted something', () => {
    show([row({ sources: ['bluesky', 'reddit:a'],
                activity_sources: ['bluesky', 'reddit:a'] })])
    const cell = screen.getByTestId('rh-row-sources')
    expect(within(cell).getByText('2 platforms')).toBeVisible()
    expect(within(cell).getByText(/Bluesky · Reddit|Reddit · Bluesky/)).toBeVisible()
  })

  it('does not print a feed label per subreddit', () => {
    // The rejected board: thirty subreddits, thirty copies of the word
    // Reddit, most of the table's width spent on them.
    const subs = ['options', 'wallstreetbets', 'stocks', 'pennystocks']
      .map((sub) => `reddit:${sub}`)
    show([row({ sources: subs, activity_sources: subs })])
    const cell = screen.getByTestId('rh-row-sources')
    expect(within(cell).getByText('1 platform')).toBeVisible()
    // One label for the platform, not one per subreddit.
    expect(cell.querySelector('.rh-sub')!.textContent).toBe('Reddit')
  })

  it('keeps the concrete feed identifiers one press away', async () => {
    show([row({ activity_sources: ['reddit:options', 'reddit:wallstreetbets'] })])
    await userEvent.click(screen.getByRole('button', { name: /which feeds/i }))
    const detail = screen.getByRole('group', { name: /which feeds/i })
    expect(within(detail).getByText(/r\/options, r\/wallstreetbets/)).toBeVisible()
    // Never claimed as corroboration: they share a site and an audience.
    expect(within(detail).getByText(/do not corroborate/i)).toBeVisible()
  })

  it('counts only the feeds that counted something', () => {
    // `sources` is every scored feed that was LOOKED AT, and it is what the
    // breadth filter is built on. The cell shows the measured subset.
    show([row({ sources: ['bluesky', 'fourchan', 'reddit:a'],
                activity_sources: ['bluesky'] })])
    const cell = screen.getByTestId('rh-row-sources')
    expect(within(cell).getByText('1 platform')).toBeVisible()
    expect(within(cell).queryByText('3 platforms')).toBeNull()
  })

  it('distinguishes a measured zero from a board that never sent the field', () => {
    show([row({ ticker: 'ZRO', activity_sources: [] }),
          row({ ticker: 'OLD', activity_sources: undefined })])
    const cells = screen.getAllByTestId('rh-row-sources')
    const [measured, missing] = [cells[0]!, cells[1]!]
    expect(within(measured).getByText(/no active feeds/i)).toBeVisible()
    expect(within(missing).getByText(/source activity unavailable/i)).toBeVisible()
    // Never falls back to sources.length, which is the count that was wrong.
    expect(within(missing).queryByText(/1 platform/)).toBeNull()
  })

  it('states the window and the market it is describing', () => {
    show([row()])
    // Both above the list and again under it: the window is what "8.4x its
    // normal" is a ratio OVER, and a table read without it means nothing.
    expect(screen.getByText(/US markets · last 4 hours/i)).toBeVisible()
    expect(screen.getByText(/prices from US markets/i)).toBeVisible()
  })

  it('distinguishes a quiet board from a stopped one', () => {
    // `excluded` is why the list is short. Without it a quiet market and a
    // broken ingest look identical.
    render(<Chatter board={payload({ rows: [], excluded: { floor: 12 } })}
                    selection={selection} onOpen={vi.fn()} />)
    expect(screen.getByText(/12/)).toBeVisible()
    expect(screen.getByText(/nothing cleared/i)).toBeVisible()
  })

  it('says so when nothing was excluded either', () => {
    render(<Chatter board={payload({ rows: [], excluded: {} })}
                    selection={selection} onOpen={vi.fn()} />)
    expect(screen.getByText(/no company/i)).toBeVisible()
  })
})

describe('filtering the list in place', () => {
  it('offers the server-side filters the spec requires', async () => {
    // The in-page text box narrows what is on screen; these change which
    // board the server builds, which is a different thing and a new request.
    //
    // Market, window and size are on the bar. Breadth and the feeds moved
    // behind a disclosure in the VC1 correction -- one press, not gone.
    render(<Chatter board={payloadWithRows([row()])} selection={selection}
                    onOpen={vi.fn()} onSelect={vi.fn()} />)
    for (const label of [/market/i, /window/i, /size/i]) {
      expect(screen.getByLabelText(label)).toBeVisible()
    }
    await userEvent.click(screen.getByRole('button', { name: /more filters/i }))
    expect(screen.getByLabelText(/breadth/i)).toBeVisible()
    expect(screen.getByRole('group', { name: /feeds/i })).toBeVisible()
  })

  it('says what the hidden filters are set to without opening them', () => {
    render(<Chatter board={payloadWithRows([row()])}
                    selection={{ ...selection, minVenues: 2,
                                 sources: ['bluesky'] }}
                    onOpen={vi.fn()} onSelect={vi.fn()} />)
    // A filter behind a disclosure that does not announce itself is a filter
    // the reader cannot account for when the board comes back short.
    const more = screen.getByRole('button', { name: /more filters/i })
    expect(more).toHaveTextContent(/more than one venue/i)
    expect(more).toHaveTextContent(/1 of 3 feeds/i)
    expect(more).toHaveAttribute('aria-expanded', 'false')
  })

  it('asks the server for a new board when a filter changes', async () => {
    const onSelect = vi.fn()
    render(<Chatter board={payloadWithRows([row()])} selection={selection}
                    onOpen={vi.fn()} onSelect={onSelect} />)
    await userEvent.selectOptions(screen.getByLabelText(/market/i), 'de')
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ market: 'de' }))
  })

  it('asks for All with an empty segment rather than omitting it', async () => {
    const onSelect = vi.fn()
    render(<Chatter board={payload({ rows: [row()], segments: ['large'] })}
                    selection={{ ...selection, segments: ['large'] }}
                    onOpen={vi.fn()} onSelect={onSelect} />)
    await userEvent.selectOptions(screen.getByLabelText(/size/i), 'all')
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ segments: [] }))
  })

  it('narrows by company without asking the server', async () => {
    show([row({ ticker: 'AAA', name: 'Alpha Inc' }),
          row({ ticker: 'BBB', name: 'Beta Corp' })])
    await userEvent.type(screen.getByLabelText(/filter/i), 'beta')
    expect(screen.getByText('BBB')).toBeVisible()
    expect(screen.queryByText('AAA')).not.toBeInTheDocument()
  })

  it('says the list is filtered rather than empty', async () => {
    show([row({ ticker: 'AAA', name: 'Alpha Inc' })])
    await userEvent.type(screen.getByLabelText(/filter/i), 'zzzz')
    expect(screen.getByText(/no company here matches/i)).toBeVisible()
  })
})

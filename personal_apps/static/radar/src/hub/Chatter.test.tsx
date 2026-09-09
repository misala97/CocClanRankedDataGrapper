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
    await userEvent.click(screen.getByRole('button', { name: /AAA/ }))
    expect(onOpen).toHaveBeenCalledWith('AAA')
  })

  it('preserves unavailable quotes', () => {
    const r = row({ price: null, quote: { ...quote(), price: null, quality: 'unavailable' } })
    show([r])
    expect(screen.getByText(/unavailable/i)).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })

  it('never computes a percentage over the tone counts', () => {
    // board.py returns three counts for a stated reason: the lexicon scores
    // 0.0 both for "balanced" and for "no lexicon word matched", the second
    // dominates, and a single "% bullish" over that is -- its words -- noise
    // wearing a percentage sign. A rounded one would also print 0% for one
    // bullish post in two hundred.
    show([row({ tone: { bullish: 1, neutral: 200, bearish: 0 } })])
    expect(screen.queryByText(/%\s*positive/i)).not.toBeInTheDocument()
    expect(screen.queryByText('0% positive')).not.toBeInTheDocument()
    expect(screen.getByText(/1\s*bullish|bullish/)).toBeVisible()
    expect(screen.getByText(/unread or balanced/i)).toBeVisible()
  })

  it('says the tone has not been read rather than calling it neutral', () => {
    show([row({ tone: { bullish: 0, neutral: 0, bearish: 0 } })])
    expect(screen.getByText(/not read yet/i)).toBeVisible()
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
    expect(screen.getByText(/new here|no baseline/i)).toBeVisible()
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

  it('names the actual sources a company was discussed on', () => {
    show([row({ sources: ['bluesky', 'reddit'] })])
    const cell = screen.getByTestId('rh-row-sources')
    expect(within(cell).getByText(/bluesky/i)).toBeVisible()
    expect(within(cell).getByText(/reddit/i)).toBeVisible()
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
  it('offers the server-side filters the spec requires', () => {
    // The in-page text box narrows what is on screen; these change which
    // board the server builds, which is a different thing and a new request.
    render(<Chatter board={payloadWithRows([row()])} selection={selection}
                    onOpen={vi.fn()} onSelect={vi.fn()} />)
    for (const label of [/market/i, /window/i, /size/i, /breadth/i]) {
      expect(screen.getByLabelText(label)).toBeVisible()
    }
    expect(screen.getByRole('group', { name: /feeds/i })).toBeVisible()
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

  it('refuses to leave the board with no feed at all', async () => {
    // An empty source list is not a board the API can build, and answering
    // with all of them would be a selection the reader never made.
    const onSelect = vi.fn()
    render(<Chatter board={payloadWithRows([row()])}
                    selection={{ ...selection, sources: ['bluesky'] }}
                    onOpen={vi.fn()} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('checkbox', { name: /bluesky/i }))
    const next = onSelect.mock.calls[0]![0] as { sources: string[] }
    expect(next.sources.length).toBeGreaterThan(0)
    expect(next.sources).not.toContain('bluesky')
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

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TickerRow } from './TickerRow'
import { Excluded } from './Excluded'
import type { BoardPayload, MarketQuote, Row } from '../types'

function quote(): MarketQuote {
  return {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 0.31,
    regular_move: 0.182, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    is_fallback: false,
  }
}

const row = (over: Partial<Row> = {}): Row => ({
  ticker: 'HOWL', name: 'Werewolf Therapeutics', segment: 'micro',
  divergence: 4.1, mention_z: 4.1, mentions: 284, expected: 7, ratio: 284 / 7,
  authors: 11,
  text_ratio: 0.9, sources: ['bluesky', 'fourchan'], price: 0.31,
  price_move: 0.182, direction: 'up', price_status: 'ok', baseline_days: 2,
  marks: [], series: [], triplet: {},
  tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '40x its normal' },
            { kind: 'venues', text: '2 venues' }],
  ...over, quote: over.quote ?? quote(),
})

describe('a ticker row', () => {
  it('renders the phrase the server wrote', () => {
    render(<TickerRow session="regular" row={row()} selected={false} onSelect={() => {}} />)

    expect(screen.getByText('40x its normal')).toBeInTheDocument()
    expect(screen.getByText('2 venues')).toBeInTheDocument()
  })

  it('styles each clause by its kind, never by parsing the text', () => {
    /* The contract with phrasing.py. A component that decided "this looks
       like a price" from the string would be a second implementation of a
       judgement the server already made. */
    const { container } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}} row={row({
        clauses: [{ kind: 'warn', text: 'one venue only' },
                  { kind: 'price-down', text: 'price -7%' }],
      })} />)

    expect(container.querySelector('.c-warn')).toHaveTextContent('one venue only')
    expect(container.querySelector('.c-price-down')).toHaveTextContent('price -7%')
  })

  it('never renders a ratio against a zero baseline', () => {
    /* The live page printed "209 mentions against 0 typical" and scored it
       with an em-dash. The server decides the wording now; this pins that the
       row does not reconstruct its own from the raw numbers. */
    render(<TickerRow session="regular" selected={false} onSelect={() => {}} row={row({
      expected: 0, ratio: null, mentions: 209, clauses: [
        { kind: 'new', text: 'new here' },
        { kind: 'ratio', text: '209 mentions, nothing to compare against yet' },
      ],
    })} />)

    expect(screen.queryByText(/0 typical/)).not.toBeInTheDocument()
    expect(screen.getByText(/nothing to compare against yet/))
      .toBeInTheDocument()
  })

  it('reports selection by ticker without navigating', async () => {
    const onSelect = vi.fn()
    render(<TickerRow session="regular" row={row()} selected={false} onSelect={onSelect} />)

    await userEvent.click(screen.getByRole('link', { name: /HOWL/ }))

    expect(onSelect).toHaveBeenCalledWith('HOWL')
  })

  it('is a real link so a ticker can be opened in a new tab', () => {
    render(<TickerRow session="regular" row={row()} selected={false} onSelect={() => {}} />)

    expect(screen.getByRole('link', { name: /HOWL/ }))
      .toHaveAttribute('href', '?t=HOWL')
  })

  it('marks the selected row for assistive tech, not only in colour', () => {
    render(<TickerRow session="regular" row={row()} selected onSelect={() => {}} />)

    expect(screen.getByRole('link', { name: /HOWL/ }))
      .toHaveAttribute('aria-current', 'true')
  })
})

const payload = (excluded: Record<string, number>): BoardPayload =>
  ({ excluded } as BoardPayload)

describe('the account of what was left out', () => {
  it('names each reason the floor rejected something', () => {
    render(<Excluded payload={payload({ too_few_voices: 9, one_venue: 4 })} />)

    expect(screen.getByText(/13 other tickers/)).toBeInTheDocument()
    expect(screen.getByText(/9 came from a single voice/)).toBeInTheDocument()
    expect(screen.getByText(/4 from one venue only/)).toBeInTheDocument()
  })

  it('says nothing when nothing was left out', () => {
    /* An empty board with a line saying zero tickers were excluded is worse
       than silence -- it implies the floor did something. */
    const { container } = render(<Excluded payload={payload({})} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('still counts a reason it has no wording for', () => {
    /* The total comes from the payload, not from the labels. A reason added
       server-side renders unlabelled rather than silently undercounting. */
    render(<Excluded payload={payload({ some_new_reason: 5 })} />)

    expect(screen.getByText(/5 other tickers/)).toBeInTheDocument()
  })
})

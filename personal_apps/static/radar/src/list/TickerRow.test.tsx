import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TickerRow } from './TickerRow'
import { Excluded } from './Excluded'
import type { BoardPayload, MarketQuote, Row, Selection } from '../types'

function quote(over: Partial<MarketQuote> = {}): MarketQuote {
  return {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 0.31,
    regular_move: 0.182, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    is_fallback: false,
    ...over,
    tape_status: over.tape_status ?? 'ok',
    score_eligible: over.score_eligible ?? true,
    score_term: over.score_term ?? 'divergence',
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

  it('keeps the complete current selection in modified-click and copied links', () => {
    /* This href is the browser-owned path for new tabs and copied links. A
       shortened `?t=` silently drops the reader back into the default US
       board, with different filters and score window. */
    const selection: Selection = {
      market: 'de', sources: ['bluesky', 'reddit'], segments: ['micro'],
      minVenues: 2, window: 24,
    }
    render(<TickerRow session="regular" row={row()} selected={false}
                      selection={selection} onSelect={() => {}} />)

    expect(screen.getByRole('link', { name: /HOWL/ })).toHaveAttribute(
      'href', '?sources=bluesky%2Creddit&window=24&segment=micro&market=de&venues=2&t=HOWL')
  })

  it('marks the selected row for assistive tech, not only in colour', () => {
    render(<TickerRow session="regular" row={row()} selected onSelect={() => {}} />)

    expect(screen.getByRole('link', { name: /HOWL/ }))
      .toHaveAttribute('aria-current', 'true')
  })

  it('marks a US fallback without hiding its currency', () => {
    render(<TickerRow session="regular" selected={false} onSelect={() => {}}
                      row={row({ quote: quote({ is_fallback: true }) })} />)

    expect(screen.getByText('US fallback · Nasdaq · USD')).toBeVisible()
  })

  it('names delayed, EOD, and stale quote states', () => {
    const { rerender } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'delayed', age_seconds: 720 }) })} />)
    expect(screen.getByText('12 min delayed')).toBeVisible()

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'eod' }) })} />)
    expect(screen.getByText(/EOD · 22\. Aug\. 2026/)).toBeVisible()

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'stale', age_seconds: 720 }) })} />)
    expect(screen.getByText('12 min stale')).toBeVisible()
  })

  it('names a fallback row\'s own after-hours session', () => {
    /* Germany's board can be regular while an individual US fallback is in
       after-hours.  Its explanation must follow the quote, not the board. */
    render(<TickerRow session="regular" selected={false} onSelect={() => {}}
                      row={row({ quote: quote({ is_fallback: true,
                                                 session: 'afterhours' }) })} />)

    expect(screen.getByText('After hours')).toBeVisible()
  })

  it('explains ranking from the row\'s own session', () => {
    /* A US fallback can be closed while Germany's board is still regular.
       The board header remains useful context, but it cannot explain this
       individual row's chatter-only score. */
    render(<TickerRow session="regular" selected={false} onSelect={() => {}}
                      row={row({ quote: quote({ is_fallback: true,
                                                 session: 'closed',
                                                 score_eligible: false,
                                                 score_term: 'chatter' }) })} />)

    expect(screen.getByLabelText(/Chatter z-score/)).toBeVisible()
  })

  it.each([
    ['EOD quote', { quality: 'eod' as const }],
    ['stale quote', { quality: 'stale' as const }],
    ['unavailable quote', { quality: 'unavailable' as const }],
    ['frozen live tape', { quality: 'live' as const, tape_status: 'stale' as const }],
  ])('explains a %s row with its serialized chatter score term', (_, state) => {
    /* A regular-session board still falls back to chatter when THIS quote
       cannot score.  Re-inferring divergence from the board or quote session
       falsely explains why the row is positioned. */
    render(<TickerRow session="regular" selected={false} onSelect={() => {}}
                      row={row({ quote: quote({ ...state, score_eligible: false,
                                                 score_term: 'chatter' }) })} />)

    expect(screen.getByLabelText(/Chatter z-score/)).toBeVisible()
  })

  it('keeps an ineligible row on chatter if an old payload term disagrees', () => {
    /* Eligibility is the safety verdict. The term is presentation metadata;
       a cached mixed-version payload must never revive divergence for a quote
       the server explicitly says cannot score. */
    render(<TickerRow session="regular" selected={false} onSelect={() => {}}
                      row={row({ quote: quote({ score_eligible: false,
                                                 score_term: 'divergence' }) })} />)

    expect(screen.getByLabelText(/Chatter z-score/)).toBeVisible()
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

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
  marks: [], series: [], price_series: [], normal_per_hour: null,
  triplet: {},
  tone: { bullish: 1, neutral: 1, bearish: 0 },
  clauses: [{ kind: 'ratio', text: '40x its normal' },
            { kind: 'venues', text: '2 venues' }],
  ...over, quote: over.quote ?? quote(),
})

describe('a ticker row', () => {
  it('summarises the finding in the facts column', () => {
    /* The sentence moved to the panel with the chart-row; the row keeps the
       short figures. 284/7 rounds past ten, so no decimal survives. */
    render(<TickerRow session="regular" row={row()} selected={false} onSelect={() => {}} />)

    expect(screen.getByText(/41×/)).toBeInTheDocument()
    expect(screen.getByText('2 venues')).toBeInTheDocument()
  })

  it('takes the move verdict from the clause kind, never from the text', () => {
    /* The contract with phrasing.py survives the chart-row: whether a move
       is worth stating, and which way it went, is the price clause's KIND.
       The row formats digits from price_move but renders nothing when the
       server sent no price clause. */
    const { container, rerender } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}} row={row({
        price_move: -0.07,
        clauses: [{ kind: 'warn', text: 'one venue only' },
                  { kind: 'price-down', text: 'price -7%' }],
      })} />)

    expect(container.querySelector('.facts .down')).toHaveTextContent('7.0%')
    expect(container.querySelector('.sub.warn')).toHaveTextContent('one venue only')

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}} row={row({
        price_move: -0.07, clauses: [{ kind: 'ratio', text: '40x its normal' }],
      })} />)
    // Same number, no clause: the server judged it not worth stating.
    expect(container.querySelector('.facts .down')).toBeNull()
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
    // ratio null -> the guard's wording, not a number the client re-divided.
    expect(screen.getByText('new here')).toBeInTheDocument()
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

  it('marks a deviant US fallback, and stays quiet when the header already said it', () => {
    /* The badge essay ("US fallback · NYSE · USD") died with the chart-row.
       A fallback row on a mostly-live board says so in two words; on the
       all-fallback German board the header says it once and the row adds
       nothing (quoteSuppress, from universalQuoteFacts). */
    const { rerender } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ is_fallback: true }) })} />)
    expect(screen.getByText(/US price/)).toBeVisible()

    rerender(<TickerRow session="regular" selected={false} onSelect={() => {}}
                        quoteSuppress={['fallback']}
                        row={row({ quote: quote({ is_fallback: true }) })} />)
    expect(screen.queryByText(/US price/)).toBeNull()
  })

  it('warns about stale, EOD, and unavailable quotes in a human unit', () => {
    /* "2740 min stale" asked the reader to finish a subtraction. Delayed is
       deliberately absent: a 15-minute provider delay is this feed's normal
       operating state, not a caution -- the panel still details it. */
    const { rerender } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'stale', age_seconds: 164600 }) })} />)
    expect(screen.getByText(/quote 45h old/)).toBeVisible()

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'eod' }) })} />)
    expect(screen.getByText(/EOD quote/)).toBeVisible()

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'unavailable' }) })} />)
    expect(screen.getByText(/no live quote/)).toBeVisible()

    rerender(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ quote: quote({ quality: 'delayed', age_seconds: 720 }) })} />)
    expect(screen.queryByText(/delayed/)).toBeNull()
  })

  it('draws honest chart runs: a gap splits the area, and no prices means no line', () => {
    /* The chart inherits the sparkline's discipline -- a null hour breaks
       the shape rather than being interpolated -- and a payload with nothing
       priced draws no price line at all. */
    const hours = (counts: (number | null)[]) => counts.map((count, i) => ({
      hour: `2026-08-30T0${i}:00:00Z`, count,
    }))
    const { container } = render(
      <TickerRow session="regular" selected={false} onSelect={() => {}}
                 row={row({ series: hours([2, 5, null, 4, 1]),
                            price_series: [null, null, null, null, null],
                            normal_per_hour: 1.5 })} />)

    const areas = container.querySelectorAll('path[fill="var(--mark-soft)"]')
    expect(areas).toHaveLength(2)
    // the dashed own-normal line plus the floor
    expect(container.querySelectorAll('line')).toHaveLength(2)
    expect(container.querySelector('path[stroke="var(--up)"]')).toBeNull()
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

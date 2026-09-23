import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { QuoteBadges } from './QuoteBadges'
import type { MarketQuote } from './types'

function quote(over: Partial<MarketQuote> = {}): MarketQuote {
  return {
    market: 'us',
    venue: 'NASDAQ',
    mic: 'XNAS',
    currency: 'USD',
    price: 100,
    regular_move: 0.01,
    extended_move: null,
    session: 'regular',
    quality: 'delayed',
    age_seconds: 600,
    quoted_at: '2026-08-31T12:43:00Z',
    tape_status: 'ok',
    score_eligible: false,
    score_term: 'chatter',
    source: 'finnhub',
    price_basis: 'trade',
    bid: null,
    ask: null,
    ...over,
  }
}

describe('market-data v2 provenance badges', () => {
  it('labels a midpoint as indicative and not as a trade', () => {
    render(<QuoteBadges quote={quote({
      price_basis: 'midpoint', bid: 99.9, ask: 100.1,
    })} />)
    expect(screen.getByText('NASDAQ · USD')).toBeInTheDocument()
    expect(screen.getByText(/indicative/)).toBeInTheDocument()
    expect(screen.queryByText(/executed/i)).not.toBeInTheDocument()
  })

  it('carries the book in accessible text, not crammed into the row', () => {
    render(<QuoteBadges quote={quote({
      price_basis: 'midpoint', bid: 99.9, ask: 100.1,
    })} />)
    expect(
      screen.getByText(/midpoint of the delayed book \(bid 99.9 \/ ask 100.1\)/),
    ).toBeInTheDocument()
  })

  it('a trade never wears the indicative badge', () => {
    render(<QuoteBadges quote={quote({ price_basis: 'trade' })} />)
    expect(screen.queryByText(/indicative/)).not.toBeInTheDocument()
  })

  it('names the US venue and dollars, and never a fallback listing', () => {
    const { container } = render(<QuoteBadges quote={quote({
      venue: 'NYSE', mic: 'XNYS',
    })} />)
    expect(screen.getByText('NYSE · USD')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/fallback|EUR|€/i)
  })

  it('says so when a quote has no currency, rather than guessing one', () => {
    render(<QuoteBadges quote={quote({ currency: null })} />)
    expect(screen.getByText('NASDAQ · Currency unavailable')).toBeInTheDocument()
  })
})

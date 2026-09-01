import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { QuoteBadges } from './QuoteBadges'
import type { MarketQuote } from './types'

function quote(over: Partial<MarketQuote> = {}): MarketQuote {
  return {
    market: 'de',
    venue: 'Tradegate BSX',
    mic: 'XGAT',
    currency: 'EUR',
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
    is_fallback: false,
    source: 'deutsche_boerse_delayed',
    price_basis: 'trade',
    bid: null,
    ask: null,
    ...over,
  }
}

describe('market-data v2 provenance badges', () => {
  it('labels an XGAT midpoint as indicative and not as a trade', () => {
    render(<QuoteBadges quote={quote({
      price_basis: 'midpoint', bid: 99.9, ask: 100.1,
    })} />)
    expect(screen.getByText('Tradegate BSX · EUR')).toBeInTheDocument()
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

  it('a US fallback keeps USD and never the German venue label', () => {
    render(<QuoteBadges quote={quote({
      is_fallback: true, market: 'us', venue: 'NASDAQ', mic: 'XNAS',
      currency: 'USD', source: 'finnhub',
    })} />)
    expect(screen.getByText('US fallback · NASDAQ · USD')).toBeInTheDocument()
    expect(screen.queryByText(/Tradegate/)).not.toBeInTheDocument()
  })

  it('an Xetra trade names its venue in EUR', () => {
    render(<QuoteBadges quote={quote({
      venue: 'Xetra', mic: 'XETR',
    })} />)
    expect(screen.getByText('Xetra · EUR')).toBeInTheDocument()
  })
})

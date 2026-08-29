import { formatQuoteAge, postStamp } from './format'
import type { MarketQuote } from './types'

/**
 * The quote's provenance and freshness travel with the quote itself.  Keeping
 * this treatment shared prevents a list row from claiming a live Xetra quote
 * while its detail panel says something different about the same snapshot.
 */
export function QuoteBadges({ quote, moves = false }: {
  quote: MarketQuote
  /** The compact list states source and freshness; detail also has room for
      the two different move baselines. */
  moves?: boolean
}) {
  return (
    <span className="quote-badges">
      <span className={`quote-source${quote.is_fallback ? ' fallback' : ''}`}>
        {quote.is_fallback
          ? `US fallback · ${quote.venue ?? 'US venue'} · ${quote.currency}`
          : `${quote.venue ?? 'Venue unavailable'} · ${quote.currency}`}
      </span>
      <SessionBadge session={quote.session} />
      <QualityBadge quote={quote} />
      {moves && <QuoteMoves quote={quote} />}
    </span>
  )
}

function SessionBadge({ session }: Pick<MarketQuote, 'session'>) {
  if (session === 'premarket') {
    return <span className="quote-session premarket"><i aria-hidden="true">◷</i> Pre-market</span>
  }
  if (session === 'afterhours') {
    return <span className="quote-session afterhours"><i aria-hidden="true">☾</i> After hours</span>
  }
  if (session === 'closed') {
    return <span className="quote-session closed">Market closed</span>
  }
  return <span className="quote-session regular">Regular session</span>
}

function QualityBadge({ quote }: { quote: MarketQuote }) {
  const text = qualityText(quote)
  return text ? <span className={`quote-quality ${quote.quality}`}>{text}</span> : null
}

function qualityText(quote: MarketQuote): string | null {
  if (quote.quality === 'delayed') return formatQuoteAge(quote.age_seconds)
  if (quote.quality === 'stale') {
    return quote.age_seconds === null ? 'stale quote'
      : `${Math.floor(quote.age_seconds / 60)} min stale`
  }
  if (quote.quality === 'eod') {
    const date = quote.quoted_at?.split('T')[0]
    return date ? `EOD · ${postStamp(`${date}T00:00:00Z`).split(' · ')[0]}` : 'EOD'
  }
  if (quote.quality === 'unavailable') return 'quote unavailable'
  return null
}

function QuoteMoves({ quote }: { quote: MarketQuote }) {
  return (
    <span className="quote-moves">
      {quote.regular_move !== null && (
        <Move value={quote.regular_move} label="regular" />
      )}
      {quote.extended_move !== null && (
        <Move value={quote.extended_move}
              label={quote.session === 'afterhours' ? 'after hours' : 'pre-market'} />
      )}
    </span>
  )
}

function Move({ value, label }: { value: number; label: string }) {
  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always',
  }).format(value * 100).replace('-', '−')
  return (
    <span className={`quote-move ${value >= 0 ? 'up' : 'down'}`}>
      {`${formatted}\u00a0% ${label}`}
    </span>
  )
}

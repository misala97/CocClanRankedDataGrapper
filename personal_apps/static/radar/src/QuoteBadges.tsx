import { formatMarketDate, formatQuoteAge } from './format'
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
          ? `US fallback · ${quote.venue ?? 'US venue'} · ${currencyLabel(quote.currency)}`
          : `${quote.venue ?? 'Venue unavailable'} · ${currencyLabel(quote.currency)}`}
      </span>
      <SessionBadge session={quote.session} />
      <TapeBadge quote={quote} />
      <QualityBadge quote={quote} />
      {moves && <QuoteMoves quote={quote} />}
    </span>
  )
}

function currencyLabel(currency: string | null): string {
  return currency ?? 'Currency unavailable'
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

function TapeBadge({ quote }: { quote: MarketQuote }) {
  return quote.tape_status === 'stale'
    ? <span className="quote-tape frozen">no print</span>
    : null
}

function qualityText(quote: MarketQuote): string | null {
  if (quote.quality === 'delayed') return formatQuoteAge(quote.age_seconds)
  if (quote.quality === 'stale') {
    return quote.age_seconds === null ? 'stale quote'
      : `${Math.floor(quote.age_seconds / 60)} min stale`
  }
  if (quote.quality === 'eod') {
    return quote.quoted_at ? `EOD · ${formatMarketDate(quote.quoted_at)}` : 'EOD'
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

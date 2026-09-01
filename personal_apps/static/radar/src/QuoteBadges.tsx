import { formatMarketDate, formatQuoteAge, humanAge, move } from './format'
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
      <BasisBadge quote={quote} />
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

function BasisBadge({ quote }: { quote: MarketQuote }) {
  /* A midpoint is visible because it beats an empty cell, but it must never
   * wear trade-like copy: the word is `indicative`, styled neutral, and the
   * detail surface carries the book it was derived from (spec 4.3/10). */
  if (quote.price_basis !== 'midpoint') return null
  const spread = quote.bid != null && quote.ask != null
    ? ` (bid ${quote.bid} / ask ${quote.ask})`
    : ''
  return (
    <span className="quote-basis indicative">
      indicative
      <span className="aural">{` midpoint of the delayed book${spread}`}</span>
    </span>
  )
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
    // The row said "quote 22h old" while this said "1359 min stale" of the
    // same snapshot (critique, 2026-09-01). One unit, humanAge's.
    return quote.age_seconds === null ? 'stale quote'
      : `${humanAge(quote.age_seconds)} stale`
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

/** The percent through format.ts's own formatter -- this was a one-off
 *  de-DE Intl call, so the panel said `−4,81 %` while the row said `−4.5%`
 *  of the same stock. One dialect for one number. */
function Move({ value, label }: { value: number; label: string }) {
  const formatted = move(value)
  return (
    <span className={`quote-move ${value >= 0 ? 'up' : 'down'}`}>
      {`${formatted} ${label}`}
    </span>
  )
}

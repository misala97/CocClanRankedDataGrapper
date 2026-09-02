import { UNKNOWN, exchangeLabel, formatPrice, segmentLabel } from '../format'
import { QuoteBadges } from '../QuoteBadges'
import type { Detail } from '../types'

/** Who this is, and what the tape says right now.
 *
 *  The full company name, untruncated. The list truncates because it has
 *  400px; the panel has the width, and "Subversive Congressional ..." is the
 *  half that carries the meaning.
 */
export function Identity({ identity, watching = false, onToggleWatch }: {
  identity: Detail['identity']
  /** The reader's mark on this ticker, and how to flip it. Absent where the
   *  panel is rendered without an account (tests, legacy) -- same convention
   *  as the row's own star (TickerRow). */
  watching?: boolean
  onToggleWatch?: () => void
}) {
  const facts = [
    exchangeLabel(identity.exchange),
    segmentPhrase(identity.segment),
    identity.market_cap ? cap(identity.market_cap) : null,
    identity.ipo_date ? `IPO ${identity.ipo_date.slice(0, 7)}` : null,
  ].filter(Boolean)

  return (
    <div className="ident">
      <div>
        {/* Named so the panel can be labelled by it: a landmark whose label
            is the ticker it is showing tells a screen-reader user which
            ticker they have landed in, without a second announcement. */}
        <h2 id="panel-ticker">{identity.ticker}</h2>
        <div className="full">{identity.name ?? 'Name unknown'}</div>
        <div className="facts">{facts.join(' · ')}</div>
        {onToggleWatch && (
          <button type="button" className={`watch${watching ? ' on' : ''}`}
                  aria-pressed={watching}
                  aria-label={`${watching ? 'Stop watching' : 'Watch'} ${identity.ticker}`}
                  onClick={onToggleWatch}>
            {watching ? '★ Watching' : '☆ Watch'}
          </button>
        )}
      </div>
      <div className="px">
        <div className="v">
          {/* Zero is not a price. A share does not trade at nothing, so a
              zero here is an absent quote that arrived as a default -- and
              `$0.00` printed at 26px is the most confident wrong number on
              the page. It reads as the em-dash every other unknown does. */}
          {identity.quote.price === null || identity.quote.price <= 0
            ? UNKNOWN : quotePrice(identity.quote.price, identity.quote)}
        </div>
        <QuoteBadges quote={identity.quote} moves />
      </div>
    </div>
  )
}

function quotePrice(value: number, quote: Detail['identity']['quote']): string {
  if (!quote.currency) return UNKNOWN
  return formatPrice(value, quote.currency, { explicitCode: quote.is_fallback })
}

/** The segment, said the way a person would say it.
 *
 *  This line printed the raw enum with a word stuck on the end -- `${segment}
 *  cap` -- which reads as "recent_ipo cap" on the panel while the row two
 *  inches away says "IPO", because the row uses `segmentLabel()` and
 *  the panel did not. It also produces "unknown cap" and "fund cap", and
 *  neither of those is a cap at all: `fund` has no market capitalisation to
 *  describe and `unknown` is the absence of one.
 *
 *  So the three that ARE sizes take "cap" and the two that are not say what
 *  they are instead. Falls through `segmentLabel` for anything the server
 *  adds later, which keeps a new segment readable rather than raw.
 */
function segmentPhrase(segment: string): string {
  if (segment === 'fund') return 'a pooled fund'
  if (segment === 'unknown') return 'size unknown'
  if (segment === 'recent_ipo') return 'recently listed'
  return `${segmentLabel(segment).toLowerCase()} cap`
}

/** Market cap, abbreviated to the unit that fits it.
 *
 *  The millions rung rounds to whole millions, which printed `$0M` for the
 *  sub-million shells this board's micro segment is largely made of -- a size
 *  fact that says the company has no value. Below ten million the decimal is
 *  the whole content of the number, and below a million the unit changes. */
function cap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (value >= 1e7) return `$${Math.round(value / 1e6)}M`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return `$${Math.round(value / 1e3)}K`
}

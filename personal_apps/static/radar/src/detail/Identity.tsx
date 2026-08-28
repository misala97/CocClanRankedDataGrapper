import { UNKNOWN, exchangeLabel, money } from '../format'
import type { Detail } from '../types'

/** Who this is, and what the tape says right now.
 *
 *  The full company name, untruncated. The list truncates because it has
 *  400px; the panel has the width, and "Subversive Congressional ..." is the
 *  half that carries the meaning.
 */
export function Identity({ identity }: { identity: Detail['identity'] }) {
  const facts = [
    exchangeLabel(identity.exchange),
    `${identity.segment} cap`,
    identity.market_cap ? cap(identity.market_cap) : null,
    identity.ipo_date ? `IPO ${identity.ipo_date.slice(0, 7)}` : null,
  ].filter(Boolean)

  return (
    <div className="ident">
      <div>
        <h2>{identity.ticker}</h2>
        <div className="full">{identity.name ?? 'Name unknown'}</div>
        <div className="facts">{facts.join(' · ')}</div>
      </div>
      <div className="px">
        <div className="v">
          {/* Zero is not a price. A share does not trade at nothing, so a
              zero here is an absent quote that arrived as a default -- and
              `$0.00` printed at 26px is the most confident wrong number on
              the page. It reads as the em-dash every other unknown does. */}
          {identity.price === null || identity.price <= 0
            ? UNKNOWN : money(identity.price)}
        </div>
        <Move identity={identity} />
      </div>
    </div>
  )
}

/** The move, or why there is not one.
 *
 *  Three silences that must not collapse into each other: the exchange is
 *  shut, which says nothing about this stock; the tape has not printed, which
 *  does and is a warning; or there is no quote at all. The live page printed
 *  0.00% for the first, which asserts the price held steady when nothing
 *  traded.
 */
function Move({ identity }: { identity: Detail['identity'] }) {
  if (identity.price_status === 'closed' || identity.session === 'closed') {
    return <div className="st closed">market closed</div>
  }
  if (identity.price_status === 'stale') {
    return <div className="st warn">tape has not printed</div>
  }
  if (identity.price_move === null) return <div className="st">no quote</div>

  const pct = identity.price_move * 100
  return (
    <div className={`mv ${pct >= 0 ? 'up' : 'down'}`}>
      {pct >= 0 ? '+' : ''}{pct.toFixed(1)}%
    </div>
  )
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

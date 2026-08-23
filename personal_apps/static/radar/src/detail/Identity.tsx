import type { Detail } from '../types'

/** Who this is, and what the tape says right now.
 *
 *  The full company name, untruncated. The list truncates because it has
 *  400px; the panel has the width, and "Subversive Congressional ..." is the
 *  half that carries the meaning.
 */
export function Identity({ identity }: { identity: Detail['identity'] }) {
  const facts = [
    identity.exchange,
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
          {identity.price === null ? '—' : money(identity.price)}
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

function cap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  return `$${Math.round(value / 1e6)}M`
}

function money(value: number): string {
  return value >= 100 ? `$${value.toFixed(0)}` : `$${value.toFixed(2)}`
}

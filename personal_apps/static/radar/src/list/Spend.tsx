import type { BoardPayload } from '../types'

/** Money in USD, at the precision the number deserves.
 *
 *  Cents once there are dollars to round; three places below a dollar,
 *  because a day of this costs about twenty cents and "$0.20" reads as a
 *  rounding of something unknown while "$0.196" reads as a measurement.
 */
function usd(amount: number): string {
  if (amount >= 1) return `$${amount.toFixed(2)}`
  return `$${amount.toFixed(3)}`
}

/** What the model re-read of tone has cost.
 *
 *  Counted from the token usage every API response carries, not asked for:
 *  there is no balance endpoint anywhere in the Claude API. The Cost API
 *  reports spend rather than remaining credit, needs a separate Admin API
 *  key, and is documented as unavailable for individual accounts.
 *
 *  So this is spend, and it is read against whatever was last loaded onto the
 *  account. It deliberately does not claim to be a balance, because a number
 *  labelled "remaining" that was never told the top-ups would be worse than
 *  no number at all.
 */
export function Spend({ payload }: { payload: BoardPayload }) {
  const spend = payload.spend
  // Absent until the first pass books something. Rendering "$0.00" before any
  // call has happened would look like a working meter reading zero, which is
  // a different claim from having nothing to report yet.
  if (!spend || (!spend.today_usd && !spend.month_usd && !spend.unpriced_tokens)) return null

  return (
    <p className="below">
      <b>{usd(spend.today_usd)}</b> spent reading tone today,
      {' '}<b>{usd(spend.month_usd)}</b> this month.
      {spend.unpriced_tokens > 0 && (
        <> plus {spend.unpriced_tokens.toLocaleString()} tokens at an unknown rate.</>
      )}
    </p>
  )
}

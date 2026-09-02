import { count } from '../format'
import type { BoardPayload } from '../types'

/** Money in USD, at the precision the number deserves.
 *
 *  Cents once there are dollars to round; three places below a dollar,
 *  because a sub-dollar spend reads as a rounding of something unknown at two
 *  decimal places ("$0.20") and as a measurement at three ("$0.196").
 */
function usd(amount: number): string {
  if (amount >= 1) return `$${amount.toFixed(2)}`
  return `$${amount.toFixed(3)}`
}

/** Whether there is anything to report at all. Rendering "$0.000" before any
 *  call has happened would look like a working meter reading zero, which is
 *  a different claim from having nothing to report yet. */
function booked(spend: BoardPayload['spend']): spend is NonNullable<BoardPayload['spend']> {
  return Boolean(spend
    && (spend.today_usd || spend.month_usd || spend.unpriced_tokens))
}

/** Today's spend as one token in the masthead, beside the freshness stamp.
 *
 *  The full sentence (below) sits at the foot of the list, after the
 *  excluded account and the marks legend -- 2,660px down a 24h board, and
 *  off the pane's bottom edge even on an empty one, so the meter was never
 *  where a reader looked (Michi, 2026-09-02). The one figure that moves
 *  during a day goes where the eye already goes for "how fresh is this";
 *  the month rides in the accessible name and the title. */
export function SpendMark({ payload }: { payload: BoardPayload }) {
  const spend = payload.spend
  if (!booked(spend)) return null
  const whole = `${usd(spend.today_usd)} spent reading tone today, `
    + `${usd(spend.month_usd)} this month`
  // A day that rounds to nothing must not print "$0.000 today": true (the
  // UTC day is two hours old at 02:00 CEST and a month of tone costs about
  // a millidollar) and yet it reads as a meter that stopped. Below display
  // precision the token says so; with nothing booked today it says the
  // month, which is the figure that is actually moving.
  const todayShown = spend.today_usd >= 0.0005
  const todayTrace = spend.today_usd > 0 && !todayShown
  // Not aria-label: a bare span is role `generic`, which ARIA forbids naming,
  // so a label there is silently ignored. Hidden text is read; the title is
  // the same sentence for a mouse.
  return (
    <span className="spend" title={whole}>
      {todayShown || todayTrace ? (
        <>
          <b>{todayTrace ? '<$0.001' : usd(spend.today_usd)}</b> today
          <span className="aural">, {usd(spend.month_usd)} this month, reading tone</span>
        </>
      ) : (
        <>
          <b>{usd(spend.month_usd)}</b> this month
          <span className="aural">, nothing yet today, reading tone</span>
        </>
      )}
    </span>
  )
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
  if (!booked(spend)) return null

  const review = payload.sentiment_ops?.review
  return (
    <p className="below">
      <b>{usd(spend.today_usd)}</b> spent reading tone today,
      {' '}<b>{usd(spend.month_usd)}</b> this month.
      {spend.unpriced_tokens > 0 && (
        // A bare toLocaleString() follows the READER's locale, and under a
        // German one this came out as `1.284.392` -- the only figure on a
        // surface that is otherwise entirely en-US and UTC. Seen on the
        // running board, not reasoned about.
        <> plus {count(spend.unpriced_tokens)} tokens at an unknown rate.</>
      )}
      {review && review.demanded > 0 && (
        // The review tier's day so far, only once it wants anything: served
        // over unique demand, and how many the daily ceiling refused.
        <> Review: <b>{count(review.served)}</b>/{count(review.demanded)} served
        {review.capped > 0 && <>, {count(review.capped)} capped</>}.</>
      )}
    </p>
  )
}

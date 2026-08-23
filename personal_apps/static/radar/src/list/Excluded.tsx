import type { BoardPayload } from '../types'

/** Why a ticker is not listed, in the order a reader would ask.
 *
 *  The vocabulary matches leaderboard._rejection exactly. A reason the server
 *  starts sending that is missing here renders as nothing, which is why the
 *  total is computed from the payload rather than from this list -- a silent
 *  undercount would be worse than an unlabelled one.
 */
const REASONS: [string, (n: number) => string][] = [
  ['too_few_voices', (n) => `${n} came from a single voice`],
  ['one_venue', (n) => `${n} from one venue only`],
  ['too_few_mentions', (n) => `${n} were mentioned only once or twice`],
  ['repeated_text', (n) => `${n} were the same message pasted repeatedly`],
]

/** An account of what the list left out.
 *
 *  Not a footnote. A two-row board and a stopped ingest are indistinguishable
 *  without this, and the eligibility floor is the single largest reason this
 *  board is short -- until now it dropped tickers with no trace at all.
 */
export function Excluded({ payload }: { payload: BoardPayload }) {
  const counted = REASONS
    .filter(([key]) => payload.excluded[key])
    .map(([key, phrase]) => phrase(payload.excluded[key]!))
  const total = Object.values(payload.excluded).reduce((a, b) => a + b, 0)

  if (!total) return null

  return (
    <p className="below">
      <b>{total === 1 ? '1 other ticker' : `${total} other tickers`}</b> were
      {' '}mentioned in this window and are not listed
      {counted.length ? <>: {counted.join(', ')}</> : null}.
      {' '}Widen the window, or switch to <b>All</b>, to see more.
    </p>
  )
}

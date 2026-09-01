import { Excluded } from './Excluded'
import { Marks } from './Marks'
import { Spend } from './Spend'
import type { BoardPayload, Mark } from '../types'

/** What the board did not show, what its marks mean, and what the tone
 *  pass cost -- the list's footer matter, in that order.
 *
 *  One component because it renders in two places: at the foot of the rows
 *  on a desk, and under the panel once the page stacks. Below 900px the
 *  panel used to sit under all three, ~1900px down, which is why a row tap
 *  looked like nothing had happened (critique, 2026-09-01). */
export function Account({ payload, shared }: {
  payload: BoardPayload
  /** Marks the head already states for the whole board; the legend must
   *  not define them a second time. */
  shared: readonly Mark[]
}) {
  return (
    <>
      <Excluded payload={payload} />
      <Marks rows={payload.rows} suppress={shared} session={payload.session} />
      <Spend payload={payload} />
    </>
  )
}

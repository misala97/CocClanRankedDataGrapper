import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useSaveState } from '../stores'

/** A save that answers inside this window never says anything. The indicator
 *  means "this is taking a moment", not "something happened". */
const PATIENCE_MS = 300

/**
 * The screen is waiting on the network: a 2px sweep across the top edge.
 *
 * The store has counted in-flight writes since the port and nothing read the
 * number -- the CSS consumer was `#session-body.is-saving::before`, and the
 * island has no #session-body, so a slow save has been silent on exactly the
 * connection the indicator exists for.
 *
 * Portalled to <body> rather than rendered in place: the mount node is
 * .session-view, which is a grid at >=900px, and the bar is docked to the
 * viewport anyway.
 */
export function SavingSweep() {
  // The boolean, not the count: a second write starting while the first is
  // still out must not restart the patience window, or a screen saving
  // continuously would stay silent forever.
  const busy = useSaveState((s) => s.pending > 0)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (!busy) { setShown(false); return }
    const timer = setTimeout(() => setShown(true), PATIENCE_MS)
    return () => clearTimeout(timer)
  }, [busy])

  if (!shown) return null
  return createPortal(
    // aria-hidden: the save states that matter are announced elsewhere -- the
    // error banner has role="alert", and a bar that appears for a second is
    // not worth interrupting a screen reader mid-set for.
    <span className="saving-sweep" data-testid="saving-sweep" aria-hidden="true">
      <span className="saving-sweep__bar" />
    </span>,
    document.body,
  )
}

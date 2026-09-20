import { useEffect } from 'react'
import { usePartnerNotice } from '../stores'

/** Long enough to be read between sets, short enough not to need dismissing. */
const NOTICE_MS = 8000

/**
 * The visible half of "Dein Partner hat den Plan geändert."
 *
 * useFollowerSync announces the same sentence to the live region, but that is
 * sr-only text: for anyone LOOKING at the screen the queue rearranged itself
 * without a word. A bar in the page flow, where the reorder bar sits and for
 * the same reason -- it is a statement about the list below, and it must not
 * float over the confirm button the way a bottom toast would.
 *
 * Not a live region itself: inserting one already filled with text does not
 * reliably announce, which is exactly why LiveRegion exists and stays mounted.
 */
export function PartnerNotice() {
  const visible = usePartnerNotice((s) => s.visible)
  const nonce = usePartnerNotice((s) => s.nonce)
  const dismiss = usePartnerNotice((s) => s.dismiss)

  // Keyed on the nonce as well: a second change while the bar is up restarts
  // the clock instead of letting the first one's timer take it down early.
  useEffect(() => {
    if (!visible) return
    const timer = setTimeout(dismiss, NOTICE_MS)
    return () => clearTimeout(timer)
  }, [visible, nonce, dismiss])

  if (!visible) return null

  return (
    <div className="reorder-bar">
      <span className="reorder-bar__txt">
        Dein Partner hat den Plan geändert. Was du angefangen hast, bleibt dran.
      </span>
      <button type="button" className="reorder-bar__done" onClick={dismiss}>OK</button>
    </div>
  )
}

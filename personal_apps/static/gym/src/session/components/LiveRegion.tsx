import { useAnnouncer } from '../stores'

/**
 * The screen's live region.
 *
 * Always mounted, never conditional: a live region has to persist to be
 * announced, and a freshly inserted one carrying pre-filled text does not
 * reliably announce it. The original kept #rest-announce outside #session-body
 * for exactly that reason, because everything inside was destroyed on every
 * refresh. Here it simply stays in the tree.
 *
 * 'polite' rather than 'assertive': the user is mid-workout, not mid-error.
 *
 * The key on the nonce is the other half of the problem. Writing the same
 * string into a live region does not re-fire it, and two identical
 * announcements in a row are two events -- remounting the text node makes the
 * second one land.
 */
export function LiveRegion() {
  const message = useAnnouncer((s) => s.message)
  const nonce = useAnnouncer((s) => s.nonce)

  return (
    <p className="sr-only" id="rest-announce" aria-live="polite">
      <span key={nonce}>{message}</span>
    </p>
  )
}

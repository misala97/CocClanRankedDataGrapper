import { useEffect } from 'react'
import { useSaveState } from '../stores'

/**
 * The one shared, visible answer to "did that save?" when a gym-wifi write
 * drops.
 *
 * Rendered from the store rather than toggled in the DOM: the old banner lived
 * outside #session-body precisely so refreshBody would not destroy it, and
 * owning it here removes the reason that mattered.
 *
 * It speaks for every write that was lost, not only the last one: each was
 * rolled back, and a banner that forgot the earlier ones let them vanish
 * (G-139). One retry sends them all again.
 */
export function SaveErrorBanner() {
  const errors = useSaveState((s) => s.errors)
  const retryAll = useSaveState((s) => s.retryAll)
  const resendAll = useSaveState((s) => s.resendAll)
  const dismiss = useSaveState((s) => s.dismissErrors)
  const canRetry = errors.some((e) => e.retry !== null)
  const canResend = errors.some((e) => e.retry !== null && e.remedy === 'auto')

  // Gym wifi comes back before anyone finds the retry button: when the
  // connection returns, the banner sends the lost writes itself. Each is
  // taken off the list as it is sent, so the tap and the event cannot both
  // send it. Never a reload: that is the lifter's call, not the wifi's --
  // it would throw away whatever they were typing (B4 review). Never an
  // added set either: it may be in already (Remedy 'manual').
  useEffect(() => {
    if (!canResend) return
    window.addEventListener('online', resendAll)
    return () => window.removeEventListener('online', resendAll)
  }, [canResend, resendAll])

  if (errors.length === 0) return null
  // Three sets lost to the same dead wifi are one reason, said once.
  const reasons = [...new Set(errors.map((e) => e.message))]

  return (
    <div className="note-save" role="alert">
      <span className="note-save__label">
        {errors.length === 1 ? 'Nicht gespeichert' : `${errors.length} Änderungen nicht gespeichert`}
      </span>
      {reasons.map((reason) => (
        <span key={reason} className="note-save__msg">{reason}</span>
      ))}
      <div className="save-error__actions">
        {/* --ghost, not --stall: .btn--stall paints --live-ink, which put a
            second orange control on screen beside the solid-orange confirm
            button. The retry is this banner's own primary action and the
            banner already has all the attention it needs. A refused value
            has no retry -- the message says what to change instead. */}
        {canRetry && (
          <button type="button" className="btn btn--ghost btn--sm"
            onClick={retryAll}>Erneut versuchen</button>
        )}
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={dismiss}>{canRetry ? 'Verwerfen' : 'OK'}</button>
      </div>
    </div>
  )
}

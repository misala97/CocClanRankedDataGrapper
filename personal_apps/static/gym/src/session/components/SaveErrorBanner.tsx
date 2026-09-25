import { useEffect, useRef } from 'react'
import { useOutbox, useSaveState } from '../stores'

/** The outbox's own entry once only a fresh page can send (outbox.ts). */
const BLOCKED = 'outbox-blocked'

/**
 * The one shared, visible answer to "did that save?" when a gym-wifi write
 * drops.
 *
 * Rendered from the store rather than toggled in the DOM: the old banner lived
 * outside #session-body precisely so refreshBody would not destroy it, and
 * owning it here removes the reason that mattered.
 *
 * It speaks for every write that did not keep, not only the last one: none
 * of them is on the screen any more, and a banner that forgot the earlier
 * ones let them vanish (G-139). One retry sends them all again.
 */
export function SaveErrorBanner() {
  const errors = useSaveState((s) => s.errors)
  const retryAll = useSaveState((s) => s.retryAll)
  const resendAll = useSaveState((s) => s.resendAll)
  const dismiss = useSaveState((s) => s.dismissErrors)
  const outbox = useOutbox((s) => s.state)
  const kept = useOutbox((s) => s.count)
  const canRetry = errors.some((e) => e.retry !== null)
  const canResend = errors.some((e) => e.retry !== null && e.remedy === 'auto')
  const reloads = errors.some((e) => e.retry !== null && e.remedy === 'reload')

  // Gym wifi comes back before anyone finds the retry button: when the
  // connection returns, the banner sends the lost writes itself. Each is
  // taken off the list as it is sent, so the tap and the event cannot both
  // send it. Never a reload: that is the lifter's call, not the wifi's --
  // it would throw away whatever they were typing (B4 review). Never an
  // added set either: it may be in already (Remedy 'manual').
  //
  // Not while the phone still holds writes: on `online` their first try is
  // still out, and a write sent behind them was failed again at once (B6
  // review). Their landing is the better sign, and sends it (below).
  useEffect(() => {
    if (!canResend) return
    const resend = () => {
      const { state } = useOutbox.getState()
      if (state !== 'waiting' && state !== 'blocked') resendAll()
    }
    window.addEventListener('online', resend)
    return () => window.removeEventListener('online', resend)
  }, [canResend, resendAll])

  const held = useRef(false)
  useEffect(() => {
    if (outbox === 'waiting' || outbox === 'blocked') {
      held.current = true
      return
    }
    if (outbox !== 'idle' || !held.current) return
    held.current = false
    if (canResend) resendAll()
  }, [outbox, canResend, resendAll])

  if (errors.length === 0) return null
  // After a stale token or a lapsed login the kept writes are not lost: they
  // wait on the phone for the fresh page that sends them. "Nicht gespeichert"
  // said the opposite, and "Verwerfen" only hid the banner (B6 review). The
  // outbox's own note says why they wait; it is no change of its own --
  // counted, one lost swap read "2 Änderungen" (B6 re-review).
  const lost = errors.filter((e) => e.key !== BLOCKED)
  const keptOnly = lost.length === 0 && kept > 0
  // Three sets lost to the same dead wifi are one reason, said once.
  const reasons = [...new Set(errors.map((e) => e.message))]

  return (
    <div className="note-save" role="alert">
      <span className="note-save__label">
        {keptOnly ? 'Auf diesem Handy gespeichert'
          : lost.length <= 1 ? 'Nicht gespeichert' : `${lost.length} Änderungen nicht gespeichert`}
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
            onClick={retryAll}>{reloads ? 'Neu laden' : 'Erneut versuchen'}</button>
        )}
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={dismiss}>{keptOnly ? 'Ausblenden' : canRetry ? 'Verwerfen' : 'OK'}</button>
      </div>
    </div>
  )
}

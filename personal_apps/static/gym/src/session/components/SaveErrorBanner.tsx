import { useEffect } from 'react'
import { useSaveState } from '../stores'

/**
 * The one shared, visible answer to "did that save?" when a gym-wifi write
 * drops.
 *
 * Rendered from the store rather than toggled in the DOM: the old banner lived
 * outside #session-body precisely so refreshBody would not destroy it, and
 * owning it here removes the reason that mattered.
 */
export function SaveErrorBanner() {
  const error = useSaveState((s) => s.error)
  const dismiss = useSaveState((s) => s.dismissError)

  // Gym wifi comes back before anyone finds the retry button: when the
  // connection returns, the banner retries itself. Safe to fire twice --
  // toggleSet states its target (idempotent) and addSet is lock-guarded.
  useEffect(() => {
    if (error === null) return
    const retry = () => error.retry()
    window.addEventListener('online', retry)
    return () => window.removeEventListener('online', retry)
  }, [error])

  if (error === null) return null

  return (
    <div className="note-save" role="alert">
      <span className="note-save__label">Nicht gespeichert</span>
      <span>{error.message}</span>
      <div className="save-error__actions">
        {/* --ghost, not --stall: .btn--stall paints --live-ink, which put a
            second orange control on screen beside the solid-orange confirm
            button. The retry is this banner's own primary action and the
            banner already has all the attention it needs. */}
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={() => error.retry()}>Erneut versuchen</button>
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={dismiss}>Verwerfen</button>
      </div>
    </div>
  )
}

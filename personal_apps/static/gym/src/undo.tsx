import { useEffect } from 'react'
import { create } from 'zustand'

/**
 * Delayed-commit undo, replacing confirm() on destructive taps.
 *
 * The pattern: the UI reports the outcome immediately, the server write fires
 * UNDO_MS later unless Rückgängig is tapped. Nothing has to be un-deleted --
 * before the timer runs out there is nothing on the server to restore, which
 * is why this works without any un-delete routes.
 *
 * One offer at a time: a second destructive tap COMMITS the first
 * immediately rather than stacking toasts -- two pending deletions with one
 * visible button is how the wrong one gets kept. The pagehide flush is what
 * makes the delay safe: navigating away commits the pending write (with
 * keepalive, so the request survives the page), instead of silently
 * forgetting it.
 */
const UNDO_MS = 5000

interface Pending {
  /** What the toast says happened, e.g. 'Routine „Push" gelöscht.' */
  label: string
  /** Performs the real (server) write. May receive keepalive=true when fired
   *  from pagehide, where a normal fetch would be killed mid-flight. */
  commit: (keepalive: boolean) => void
  /** Reverts the optimistic UI. Nothing has hit the server yet. */
  undo: () => void
}

interface UndoState {
  pending: Pending | null
  timer: ReturnType<typeof setTimeout> | null
  offer(next: Pending): void
  undoNow(): void
  commitNow(keepalive?: boolean): void
}

export const useUndo = create<UndoState>((set, get) => ({
  pending: null,
  timer: null,
  offer(next) {
    get().commitNow()
    set({
      pending: next,
      timer: setTimeout(() => get().commitNow(), UNDO_MS),
    })
  },
  undoNow() {
    const { pending, timer } = get()
    if (timer !== null) clearTimeout(timer)
    set({ pending: null, timer: null })
    pending?.undo()
  },
  commitNow(keepalive = false) {
    const { pending, timer } = get()
    if (timer !== null) clearTimeout(timer)
    set({ pending: null, timer: null })
    pending?.commit(keepalive)
  },
}))

/**
 * The toast itself. Mounted once per island root.
 *
 * role="status", not alert: the action was the user's own, nothing is on
 * fire. The button is a real <button>, and the whole thing sits above the
 * thumb zone rather than over it.
 */
export function UndoToast() {
  const pending = useUndo((s) => s.pending)
  const undoNow = useUndo((s) => s.undoNow)
  const commitNow = useUndo((s) => s.commitNow)

  // A pending write must survive leaving the page: commit it with keepalive
  // the moment the document starts to hide. Registered while something is
  // pending only, so the listener does not outlive its reason.
  useEffect(() => {
    if (pending === null) return
    const flush = () => useUndo.getState().commitNow(true)
    window.addEventListener('pagehide', flush)
    return () => window.removeEventListener('pagehide', flush)
  }, [pending])

  if (pending === null) return null
  return (
    <div className="undo-toast" role="status">
      <span className="undo-toast__label">{pending.label}</span>
      <button type="button" className="undo-toast__act" onClick={undoNow}>
        Rückgängig
      </button>
      {/* Dismiss = accept: commits right away instead of waiting the timer
          out, so the toast never has to be endured. */}
      <button type="button" className="undo-toast__close" aria-label="Schließen"
        onClick={() => commitNow()}>✕</button>
    </div>
  )
}

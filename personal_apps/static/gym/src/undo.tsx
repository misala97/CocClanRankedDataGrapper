import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
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
 * visible button is how the wrong one gets kept. The flush is what makes the
 * delay safe: navigating away or going to the background commits the pending
 * write (with keepalive, so the request survives the page), instead of
 * silently forgetting it.
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
  // the moment the document starts to hide. pagehide alone was not enough
  // (G-062): a phone kills a backgrounded app without one, and the delete
  // waiting out its window never reached the server -- the set came back.
  // Going to the background is the last moment a page is sure to get, so it
  // commits there, the window cut short. Registered while something is
  // pending only, so the listeners do not outlive their reason.
  useEffect(() => {
    if (pending === null) return
    const flush = () => useUndo.getState().commitNow(true)
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flush()
    }
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('pagehide', flush)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [pending])

  // Most offers are made from inside a sheet -- a set deleted in the exercise
  // sheet or the debrief's correction sheet. A modal <dialog> makes the rest
  // of the page inert, so a toast rendered beside it could be seen behind the
  // backdrop and not tapped: "Rückgängig" was unreachable until the sheet was
  // closed. While a sheet is open the toast lives inside it, and moves back
  // out when the sheet closes.
  const [host, setHost] = useState<HTMLDialogElement | null>(null)
  useEffect(() => {
    if (pending === null) { setHost(null); return }
    const sheet = document.querySelector<HTMLDialogElement>('dialog[open]')
    setHost(sheet)
    if (sheet === null) return
    const leave = () => setHost(null)
    sheet.addEventListener('close', leave)
    return () => sheet.removeEventListener('close', leave)
  }, [pending])

  if (pending === null) return null
  const toast = (
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
  return host === null ? toast : createPortal(toast, host)
}

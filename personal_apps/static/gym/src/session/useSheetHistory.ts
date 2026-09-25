import { useEffect, type FormEvent } from 'react'
import { useSheets } from './stores'

/** Whether the current history entry is one a sheet added. From the entry,
 *  not a flag: a reload keeps the entry, and a flag would start over. */
const onSheetEntry = () =>
  (history.state as { gymSheet?: boolean } | null)?.gymSheet === true

let leaving = false

/** How long leavePage waits for its step back before it leaves anyway. */
export const LEAVE_FALLBACK_MS = 1000

/**
 * Leave the page by `go`, a navigation, without leaving a sheet's entry
 * behind it: back from the next page landed on this page's sheet entry, one
 * dead step -- after every finish, from the finish sheet (B7 review). With a
 * sheet's entry current it is taken back first, and the page is left once
 * that step is done; the sheet stays up until the page is gone. Once: a
 * second tap would step back past the page. A step that never lands -- a
 * view that will not walk its history -- must not keep the lifter here:
 * after a second the page is left anyway, entry or not.
 */
export function leavePage(go: () => void): void {
  if (leaving) return
  if (!onSheetEntry()) { go(); return }
  leaving = true
  const leave = () => {
    window.removeEventListener('popstate', leave)
    clearTimeout(fallback)
    leaving = false
    go()
  }
  window.addEventListener('popstate', leave)
  const fallback = setTimeout(leave, LEAVE_FALLBACK_MS)
  history.back()
}

/** A form that leaves the page (a plain POST), sent by leavePage: from a
 *  sheet, the sheet's entry is taken back first (B7 re-review). */
export function leaveBySubmit(event: FormEvent<HTMLFormElement>): void {
  event.preventDefault()
  const form = event.currentTarget
  leavePage(() => form.submit())
}

/**
 * Back closes the open sheet, not the page (G-066).
 *
 * A sheet pushed no history entry, so a back gesture that walks history -- an
 * iOS swipe, Firefox, an in-app browser -- left the workout with the sheet
 * still open and its drafts gone; only Chrome's own close request for a
 * dialog closed it instead. Now opening a sheet adds one entry, back takes it
 * and closes the sheet, and a sheet closed any other way (Fertig, Esc, an
 * action) takes its entry back itself, so no dead step is left behind.
 *
 * One entry for "a sheet is open", not one per sheet: going from one sheet to
 * the next (an exercise to its settings) keeps it, and back closes whichever
 * is open. Our own step back is told apart from the lifter's by count: it
 * lands on the page's entry too, and must not close a sheet opened while it
 * was on its way -- that sheet gets its entry once the step is done.
 *
 * Mounted once per page that has sheets.
 */
export function useSheetHistory(): void {
  useEffect(() => {
    let returning = 0
    const push = () => {
      history.pushState({ ...(history.state as object | null), gymSheet: true }, '')
    }
    const unsubscribe = useSheets.subscribe((state, previous) => {
      if (state.openId === previous.openId || returning > 0) return
      if (state.openId !== null) {
        if (!onSheetEntry()) push()
      } else if (onSheetEntry()) {
        returning += 1
        history.back()
      }
    })
    const onPop = () => {
      const open = useSheets.getState().openId !== null
      if (returning > 0) {
        returning -= 1
        if (returning === 0 && open && !onSheetEntry()) push()
        return
      }
      // leavePage's own step: the sheet stays up until the page is gone.
      // Closed, it left the page it covered live for the whole round trip
      // of a finish (B7 re-review).
      if (leaving) return
      if (open) useSheets.getState().close()
    }
    // Back on a page the browser kept whole (the bfcache), left from a sheet:
    // the sheet is still up, its entry taken back by leavePage. It gets one
    // again, or the next back would leave the page past it.
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted && useSheets.getState().openId !== null && !onSheetEntry()) push()
    }
    window.addEventListener('popstate', onPop)
    window.addEventListener('pageshow', onShow)
    return () => {
      unsubscribe()
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('pageshow', onShow)
    }
  }, [])
}

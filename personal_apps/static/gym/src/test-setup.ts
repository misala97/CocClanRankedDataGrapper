import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { useUndo } from './undo'

// The live workout keeps its outbox and the steppers' draft in localStorage
// (B6, G-009), and jsdom keeps one localStorage per test file: what one test
// left there would be sent, or restored, by the next.
beforeEach(() => { localStorage.clear() })

// A sheet's step back (useSheetHistory, leavePage) is a history traversal,
// and jsdom fires its popstate three chained tasks after history.back(). One
// still on its way when a test ended landed in the next test, and closed the
// sheet open there. Counted here, so only a test that stepped back waits.
let steppedBack = false
const back = History.prototype.back
History.prototype.back = function stepBack(this: History) {
  steppedBack = true
  back.call(this)
}

afterEach(async () => {
  vi.useRealTimers()
  // An undo offer's timer outlives the store resets between tests: dropped,
  // not cleared, it fired five seconds on and committed whatever the next
  // test had on offer then -- a flake that only showed under load.
  const { timer } = useUndo.getState()
  if (timer !== null) clearTimeout(timer)
  useUndo.setState({ pending: null, timer: null })
  if (!steppedBack) return
  steppedBack = false
  // Each task awaited lets every traversal on its way take one step.
  for (let step = 0; step < 6; step += 1) {
    await new Promise((resolve) => { setTimeout(resolve, 0) })
  }
})

// jsdom does not implement HTMLDialogElement.showModal()/close(). The gym app
// uses native <dialog> throughout precisely because the platform supplies the
// backdrop, Esc and the focus trap, so the components legitimately call them.
//
// This is a minimal stand-in: it toggles `open` so tests can assert the sheet
// opened, and nothing more. It does NOT reproduce the backdrop, the focus trap
// or Esc-to-close -- those are the browser's, and verifying them is the job of
// the browser pass in Task 6, not of jsdom.
// `open` is a reflected attribute on a real <dialog>, so both the property and
// the attribute have to move together -- code and tests legitimately look at
// either. Setting only the property made every attribute assertion fail while
// the component was correct.
if (typeof HTMLDialogElement !== 'undefined'
    && !HTMLDialogElement.prototype.showModal) {
  const open = (node: HTMLDialogElement) => {
    node.open = true
    node.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    open(this)
  }
  HTMLDialogElement.prototype.show = function show(this: HTMLDialogElement) {
    open(this)
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}

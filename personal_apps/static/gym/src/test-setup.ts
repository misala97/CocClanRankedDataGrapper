import '@testing-library/jest-dom/vitest'

// jsdom does not implement HTMLDialogElement.showModal()/close(). The gym app
// uses native <dialog> throughout precisely because the platform supplies the
// backdrop, Esc and the focus trap, so the components legitimately call them.
//
// This is a minimal stand-in: it toggles `open` so tests can assert the sheet
// opened, and nothing more. It does NOT reproduce the backdrop, the focus trap
// or Esc-to-close -- those are the browser's, and verifying them is the job of
// the browser pass in Task 6, not of jsdom.
if (typeof HTMLDialogElement !== 'undefined'
    && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true
  }
  HTMLDialogElement.prototype.show = function show(this: HTMLDialogElement) {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false
    this.dispatchEvent(new Event('close'))
  }
}

import '@testing-library/jest-dom/vitest'

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

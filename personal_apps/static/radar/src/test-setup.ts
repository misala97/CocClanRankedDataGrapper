import '@testing-library/jest-dom/vitest'

// jsdom has no layout engine and no top layer, so the popover API is absent.
// The explainer calls showPopover() directly, and an undefined method there
// would fail every test that renders a marked row -- which is most of them.
// Stubbed to record open state so the tests can still assert on it.
if (!HTMLElement.prototype.showPopover) {
  HTMLElement.prototype.showPopover = function showPopover() {
    this.setAttribute('data-open', 'true')
  }
  HTMLElement.prototype.hidePopover = function hidePopover() {
    this.removeAttribute('data-open')
  }
}

// :popover-open is likewise unknown to jsdom's selector engine; matches()
// throws on it rather than returning false.
const realMatches = HTMLElement.prototype.matches
HTMLElement.prototype.matches = function matches(selector: string) {
  if (selector === ':popover-open') return this.hasAttribute('data-open')
  return realMatches.call(this, selector)
}

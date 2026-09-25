import { Component, type ErrorInfo, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { reloadWhenRestored } from './fresh'

/**
 * Draws a page's island: its payload, embedded in the document by the Jinja
 * shell (#gym-data) rather than fetched, so the first render has everything
 * and there is no waterfall on load -- rendered into #gym-root.
 *
 * One mount for all eight pages. They were eight copies, none of which
 * caught a render error, so one threw and left a blank page with the nav
 * above it (walkthrough G-150).
 */
export function mount<P>(render: (payload: P) => ReactNode): void {
  reloadWhenRestored()
  const dataEl = document.getElementById('gym-data')
  const rootEl = document.getElementById('gym-root')
  if (!dataEl || !rootEl) return
  const payload = JSON.parse(dataEl.textContent ?? '{}') as P
  createRoot(rootEl).render(<Crash>{render(payload)}</Crash>)
}

/** What a page says when it could not draw itself: that, and the one thing
 *  that helps. A set kept on the phone is sent after the reload (the
 *  outbox), so the reload loses nothing typed into the workout. */
export class Crash extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error(error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="crash" role="alert">
        <p className="crash__h">Die Seite konnte nicht angezeigt werden.</p>
        <p className="crash__p">Neu laden hilft meistens.</p>
        <button type="button" className="btn btn--ghost"
          onClick={() => { window.location.reload() }}>Neu laden</button>
      </div>
    )
  }
}

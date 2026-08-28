import { Component, type ErrorInfo, type ReactNode } from 'react'

/** The page that is left when the board cannot be drawn.
 *
 *  Deliberately not a spinner and not an empty div. A React island that throws
 *  unmounts its whole tree, and what the reader was left with was a white
 *  viewport -- no heading, no wording, nothing to search for, and no clue that
 *  the failure was in the browser rather than in the market. The JSON route is
 *  named because the data usually survives the surface that failed to draw it,
 *  and reading it raw is a real answer at 09:28.
 */
export function Broken({ detail }: { detail?: string }) {
  return (
    <div className="broken" role="alert">
      <h1>Radar</h1>
      <h2>The board could not be drawn.</h2>
      <p>
        The data may still be fine — this is the page failing to render it, not
        the market. Reloading fixes the common case.
      </p>
      {detail && <p className="why">{detail}</p>}
      <p>
        <button type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
        {' '}or read the underlying board as JSON at{' '}
        <a href="/radar/api/board"><code>/radar/api/board</code></a>.
      </p>
    </div>
  )
}

/** Keeps one broken zone from taking the page with it.
 *
 *  The panel renders whatever the ingest picked up -- arbitrary post text,
 *  charts built from series with holes in them, identity fields that are null
 *  in combinations nobody has seen yet. Without a boundary, one unexpected
 *  shape in one ticker's panel unmounts the list beside it, and a board that
 *  is entirely readable disappears because of the row that happened to be
 *  selected. Scoped per zone for exactly that reason.
 */
export class Boundary extends Component<
  { children: ReactNode; label: string; resetKey?: string | number },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Logged rather than swallowed: this is the only trace that the zone ever
    // threw, and a silent boundary turns a render bug into a mystery.
    console.error(`radar: ${this.props.label} failed to render`, error, info)
  }

  /** Clears a tripped boundary when the caller says the situation changed.
   *
   *  A prop rather than a `key` on the element, which is what this was at
   *  first. A key remounts the CHILDREN too, and the child here is the panel:
   *  keying it on the selected ticker quietly threw away the panel's own
   *  state on every row click, so the chart span snapped back to 1Y each time
   *  the reader moved down the list. Comparing three tickers at 1M was not
   *  possible. The boundary needed to reset; the panel did not. */
  componentDidUpdate(prev: { resetKey?: string | number }) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) {
      this.setState({ failed: false })
    }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <p className="zonefail" role="alert">
        {this.props.label} could not be drawn. The rest of the board is
        unaffected.
      </p>
    )
  }
}

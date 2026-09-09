// The hub shell: navigation, the address bar, and whichever page is showing.
//
// One React root for the whole surface rather than a page per document. The
// reason is the board: Overview, Human chatter and Watching are three readings
// of one answer, and three documents would fetch it three times and be able to
// disagree with each other on screen.
//
// The address bar is the state. The hash says which page, the query says what
// it is filtered to, and both are restored by Back -- so returning from a
// company lands on the list the reader left, not a reset one.
import { useCallback, useEffect, useRef, useState } from 'react'

import type { BoardPayload, PanelSpan, Selection } from '../types'
import { Missing } from './PageState'
import { hashFor, readRoute, readSelection, readSpan, urlFor } from './navigation'
import type { HubRoute } from './navigation'
import './hub.css'

/** Only destinations this release actually renders. An empty page behind a
 *  nav item is a promise the surface cannot keep. */
const DESTINATIONS = [
  { group: null, items: [{ page: 'overview', label: 'Overview' }] },
  { group: 'Discover', items: [{ page: 'chatter', label: 'Human chatter' }] },
  { group: 'Your stocks', items: [{ page: 'watching', label: 'Watching' }] },
  { group: 'Review', items: [{ page: 'activity', label: 'Activity' }] },
] as const

export function Hub({ initial, isAdmin }: { initial: BoardPayload; isAdmin: boolean }) {
  const [route, setRoute] = useState<HubRoute>(() => readRoute(window.location.hash))
  const [selection, setSelection] = useState<Selection>(
    () => readSelection(window.location.search, seedSelection(initial),
                        initial.all_sources))
  const [span, setSpan] = useState<PanelSpan>(() => readSpan(window.location.search))
  const [menuOpen, setMenuOpen] = useState(false)
  const main = useRef<HTMLElement>(null)

  // Both events, because they are not the same event. A hash typed into the
  // address bar fires hashchange; Back across a pushState that changed only
  // the query fires popstate. Reading the URL for both keeps one source of
  // truth instead of two half-synchronised copies.
  useEffect(() => {
    const resync = () => {
      setRoute(readRoute(window.location.hash))
      setSelection(readSelection(window.location.search, seedSelection(initial),
                                 initial.all_sources))
      setSpan(readSpan(window.location.search))
    }
    window.addEventListener('popstate', resync)
    window.addEventListener('hashchange', resync)
    return () => {
      window.removeEventListener('popstate', resync)
      window.removeEventListener('hashchange', resync)
    }
  }, [initial])

  const go = useCallback((next: HubRoute, nextSelection = selection,
                          nextSpan = span) => {
    window.history.pushState(null, '', urlFor(next, nextSelection, nextSpan))
    setRoute(next)
    setSelection(nextSelection)
    setSpan(nextSpan)
    setMenuOpen(false)
    // The reader asked for a different page; the keyboard should be on it and
    // a screen reader should be told, which neither gets from a URL change.
    main.current?.focus()
  }, [selection, span])

  const title = titleFor(route)

  return (
    <div className="rh">
      <a className="rh-skip" href="#rh-main">Skip to the page</a>

      <nav id="rh-nav" className={`rh-nav${menuOpen ? ' open' : ''}`}
           aria-label="Radar">
        <div className="rh-brand">
          <Logo />
          RADAR
        </div>
        {DESTINATIONS.map(({ group, items }) => (
          <div className="rh-navgroup" key={group ?? 'top'}>
            {group ? <p className="rh-navlabel">{group}</p> : null}
            {items.map((item) => (
              <a
                key={item.page}
                className="rh-navlink"
                href={urlFor({ page: item.page }, selection, span)}
                aria-current={route.page === item.page ? 'page' : undefined}
                onClick={(event) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey) return
                  event.preventDefault()
                  go({ page: item.page })
                }}
              >
                {item.label}
              </a>
            ))}
          </div>
        ))}
        {/* Rendered for admins only; /radar/api/ops enforces this itself and
            does not trust the absence of a link. */}
        {isAdmin ? (
          <div className="rh-navbottom">
            <a
              className="rh-navlink"
              href={urlFor({ page: 'admin' }, selection, span)}
              aria-current={route.page === 'admin' ? 'page' : undefined}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey) return
                event.preventDefault()
                go({ page: 'admin' })
              }}
            >
              Administration
            </a>
          </div>
        ) : null}
      </nav>

      <div className="rh-workspace">
        <header className="rh-topbar">
          <button
            type="button"
            className="rh-menu"
            aria-expanded={menuOpen}
            aria-controls="rh-nav"
            aria-label="Navigation"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden="true">☰</span>
          </button>
          <p className="rh-session">
            <span className={`rh-dot${initial.session === 'closed' ? ' closed' : ''}`} />
            {marketLabel(initial)}
          </p>
        </header>

        <main id="rh-main" className="rh-main" ref={main} tabIndex={-1}
              aria-label={title}>
          {route.page === 'missing'
            ? <Missing onHome={() => go({ page: 'overview' })} />
            : <Placeholder title={title} />}
        </main>
      </div>
    </div>
  )
}

/** H1 ships the shell. Each page arrives in H2-H4 and replaces this; until
 *  then the area says what it is waiting for rather than rendering an empty
 *  panel that could be mistaken for a measured emptiness. */
function Placeholder({ title }: { title: string }) {
  return (
    <>
      <div className="rh-heading">
        <div>
          <h1>{title}</h1>
          <p>This page is not built yet.</p>
        </div>
      </div>
      <div className="rh-empty">
        <h2>Nothing here yet.</h2>
        <p>The navigation, the address bar and the shared board state are in
           place. This page arrives with the next task.</p>
      </div>
    </>
  )
}

function titleFor(route: HubRoute): string {
  switch (route.page) {
    case 'overview': return 'Overview'
    case 'chatter': return 'Human chatter'
    case 'watching': return 'Watching'
    case 'activity': return 'Activity'
    case 'admin': return 'Administration'
    case 'research': return route.ticker
    default: return 'Not found'
  }
}

/** The Selection the server itself parsed, echoed back in the payload. Read
 *  from the echo rather than from the URL: the server has already validated
 *  it, and a second parser would be free to disagree. */
export function seedSelection(payload: BoardPayload): Selection {
  return {
    market: payload.market,
    sources: payload.sources,
    segments: payload.segments,
    minVenues: payload.min_venues,
    window: payload.window_hours,
    sort: payload.sort,
    dir: payload.dir,
  }
}

function marketLabel(payload: BoardPayload): string {
  const state = payload.session === 'regular' ? 'open' : payload.session
  return `${payload.market_venue} · ${state}`
}

function Logo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    </svg>
  )
}

export { hashFor, readRoute }

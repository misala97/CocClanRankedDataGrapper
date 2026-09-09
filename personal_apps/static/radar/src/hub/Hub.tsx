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

import { useQueryClient } from '@tanstack/react-query'

import { BoardUnavailable } from '../api'
import type { BoardPayload, PanelSpan, Selection } from '../types'
import { Activity } from './Activity'
import { Admin } from './Admin'
import { Chatter } from './Chatter'
import { Overview } from './Overview'
import {
  Forbidden, Loading, Missing, SignedOut, StaleNotice, Unavailable,
} from './PageState'
import { Research } from './Research'
import { Watching } from './Watching'
import { Search } from './Search'
import {
  hashFor, isInPageAnchor, readRoute, readSelection, readSpan, urlFor,
} from './navigation'
import type { HubRoute } from './navigation'
import { selectionOf, useBoard, useWatchMutation } from './queries'
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
  const menuButton = useRef<HTMLButtonElement>(null)
  const expiredRef = useRef(false)
  const visible = useVisible()
  const client = useQueryClient()

  // useBoard decides for itself whether this payload matches the key it would
  // seed; passing it unconditionally is safe.
  const board = useBoard(selection, expiredRef.current ? undefined : initial,
                         visible)

  // Both events, because they are not the same event. A hash typed into the
  // address bar fires hashchange; Back across a pushState that changed only
  // the query fires popstate. Reading the URL for both keeps one source of
  // truth instead of two half-synchronised copies.
  useEffect(() => {
    const resync = () => {
      // An in-page anchor is not a destination. The skip link points at
      // #rh-main, which is an element id, and reading it as a route name
      // replaced the page with the recovery view -- on the first control a
      // keyboard reader meets.
      if (!isInPageAnchor(window.location.hash)) {
        setRoute(readRoute(window.location.hash))
      }
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

  // An expired session invalidates everything cached under this account. The
  // board is shared, but watch marks are not, and a cache surviving a sign-out
  // is how one reader sees another's.
  const expired = board.error instanceof BoardUnavailable
    && board.error.reason === 'session'
  // Latched, and read before the query is built. The embedded payload carries
  // this account's `watching`, so re-seeding the cleared cache from it would
  // put the previous reader's marks back -- marked fresh, defeating the clear
  // for the one payload the clear exists for.
  if (expired) expiredRef.current = true
  useEffect(() => {
    if (expired) client.clear()
  }, [expired, client])

  // Escape closes the menu wherever focus is; without it the only way out of
  // an opened off-canvas nav is to find the toggle again.
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const go = useCallback((next: HubRoute, nextSelection = selection,
                          nextSpan = span,
                          options: { keepFocus?: boolean } = {}) => {
    window.history.pushState(null, '', urlFor(next, nextSelection, nextSpan))
    setRoute(next)
    setSelection(nextSelection)
    setSpan(nextSpan)
    setMenuOpen(false)
    // The reader asked for a different page; the keyboard should be on it and
    // a screen reader should be told, which neither gets from a URL change.
    //
    // Not for a control INSIDE the page. Changing the chart span or a filter
    // is a toggle, and moving focus to the top would make a keyboard reader
    // tab back through the whole page to press the next one.
    if (!options.keepFocus) main.current?.focus()
  }, [selection, span])

  const title = titleFor(route)

  return (
    <div className="rh">
      {/* A real anchor for the semantics a screen reader announces, but it
          moves focus itself rather than letting the fragment land in the
          address bar: the hash is this hub's route, and #rh-main is not one. */}
      <a
        className="rh-skip"
        href="#rh-main"
        onClick={(event) => { event.preventDefault(); main.current?.focus() }}
      >
        Skip to the page
      </a>

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
            ref={menuButton}
            type="button"
            className="rh-menu"
            aria-expanded={menuOpen}
            aria-controls="rh-nav"
            aria-label="Navigation"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden="true">☰</span>
          </button>
          <Search onOpen={(ticker) => go({ page: 'research', ticker })} />
          <p className="rh-session">
            <span className={`rh-dot${(board.data ?? initial).session === 'closed' ? ' closed' : ''}`} />
            {marketLabel(board.data ?? initial)}
          </p>
        </header>

        <main id="rh-main" className="rh-main" ref={main} tabIndex={-1}
              aria-label={title}>
          {/* Data that was true a minute ago beats a blank page, as long as
              the surface says the refresh failed and when it last succeeded. */}
          {board.data && board.isError
            ? <StaleNotice error={board.error}
                           since={berlinStamp(board.data.generated_at)} />
            : null}
          {expired
            ? <SignedOut />
            : <Page route={route} board={board} selection={selection}
                    span={span} title={title} visible={visible}
                    isAdmin={isAdmin} go={go} />}
        </main>
      </div>
    </div>
  )
}

/** Which page, and what it needs.
 *
 *  Overview, Watching, Activity and Admin arrive in H3 and H4; until then they
 *  say so rather than rendering an empty panel, which a reader could not tell
 *  from a measured emptiness.
 */
function Page({ route, board, selection, span, title, visible, isAdmin, go }: {
  route: HubRoute
  board: ReturnType<typeof useBoard>
  selection: Selection
  span: PanelSpan
  title: string
  visible: boolean
  isAdmin: boolean
  go: (route: HubRoute, selection?: Selection, span?: PanelSpan,
       options?: { keepFocus?: boolean }) => void
}) {
  // Declared before any early return, because hooks are.
  const watch = useWatchMutation()
  const [marking, setMarking] = useState<string | null>(null)
  const watching = board.data?.watching
  // A refusal belongs to the page it happened on. Without this the red
  // "could not be saved" banner followed the reader to another company.
  const here = route.page === 'research' ? route.ticker : route.page
  const lastPlace = useRef(here)
  useEffect(() => {
    if (lastPlace.current !== here) {
      lastPlace.current = here
      watch.reset()
    }
  }, [here, watch])

  const onToggleWatch = (ticker: string) => {
    // One write at a time. Two in flight can land out of order, and the later
    // answer would restore a list that predates the earlier one.
    if (marking) return
    setMarking(ticker)
    watch.mutate({ ticker, on: !(watching ?? []).includes(ticker) },
                 { onSettled: () => setMarking(null) })
  }

  if (route.page === 'missing') {
    return <Missing onHome={() => go({ page: 'overview' })} />
  }

  // The nav link is rendered for admins only, but a typed hash is not a link.
  // /radar/api/ops enforces this itself; saying so here is the difference
  // between a refusal and an empty page.
  if (route.page === 'admin') {
    // The nav link is rendered for admins only, but a typed hash is not a
    // link. /radar/api/ops enforces this itself; refusing here is the
    // difference between a refusal and an empty page.
    return isAdmin ? <Admin /> : <Forbidden what="Administration" />
  }

  if (route.page === 'activity') return <Activity />

  if (route.page === 'research') {
    return (
      <Research
        ticker={route.ticker}
        selection={selection}
        span={span}
        visible={visible}
        watching={watching}
        onToggleWatch={watching === undefined ? undefined : onToggleWatch}
        watchPending={marking !== null}
        watchError={watch.error}
        onSpan={(next) => go(route, selection, next, { keepFocus: true })}
        onBack={() => go({ page: 'chatter' })}
        onSearch={() => document.getElementById('rh-search-input')?.focus()}
      />
    )
  }

  // Overview, Human chatter and Watching are three readings of one board.
  if (route.page === 'overview' || route.page === 'chatter'
      || route.page === 'watching') {
    if (!board.data) {
      return board.isError
        ? <Unavailable error={board.error} retry={() => void board.refetch()} />
        : <Loading label={`Loading ${title.toLowerCase()}…`} />
    }
    const open = (ticker: string) => go({ page: 'research', ticker })
    if (route.page === 'overview') {
      return <Overview board={board.data} onOpen={open}
                       onGo={(page) => go({ page })} />
    }
    if (route.page === 'watching') {
      return (
        <Watching board={board.data} onOpen={open} watching={watch.data}
                  onToggleWatch={onToggleWatch} pending={marking}
                  watchError={watch.error} />
      )
    }
    return (
      <Chatter board={board.data} selection={selection} onOpen={open}
              onSelect={(next) => go(route, next)} />
    )
  }

  return <Placeholder title={title} />
}

/** Refreshes run while the page is being looked at, and only then. A hidden
 *  tab polling a dashboard nobody is reading is a request the reader did not
 *  ask for -- and on a metered pipeline it is not free. */
function useVisible(): boolean {
  const [visible, setVisible] = useState(
    () => (typeof document === 'undefined' ? true
      : document.visibilityState !== 'hidden'))
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  return visible
}

function berlinStamp(iso: string): string | null {
  try {
    return `${new Date(iso).toLocaleTimeString('en-GB',
      { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })} Berlin`
  } catch {
    return null
  }
}

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
        <p>Human chatter and Research are built. This page is not, and is
           showing you that rather than an empty panel you could mistake for a
           quiet day.</p>
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

/** The Selection the server itself parsed, echoed back in the payload.
 *
 *  One implementation, in queries.ts, because the cache uses it to decide
 *  whether the embedded board may seed a key -- and two copies of that
 *  judgement would eventually disagree about which board is on screen.
 */
export const seedSelection = selectionOf

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

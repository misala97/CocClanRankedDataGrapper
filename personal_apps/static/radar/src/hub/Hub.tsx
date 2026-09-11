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
import { isReady } from '../types'
import type { BoardPayload, PanelSpan, Selection } from '../types'
import { Activity } from './Activity'
import { Admin } from './Admin'
import { Chatter } from './Chatter'
import type { ChatterSort } from './chatterSort'
import { Overview } from './Overview'
import {
  Busy, FailedNotice, Forbidden, Loading, Missing, Pending, SignedOut,
  StaleNotice, Unavailable,
} from './PageState'
import { Research } from './Research'
import { Watching } from './Watching'
import { Search } from './Search'
import {
  hashFor, isInPageAnchor, readRoute, readSelection, readSpan, urlFor,
} from './navigation'
import type { HubRoute } from './navigation'
import {
  owesABoard, selectionOf, useBoard, useWatchMutation,
} from './queries'
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
  // Chatter's ordering lives HERE, not in Chatter, because Chatter unmounts
  // when the reader opens a company. Held in memory only: it is a view over
  // whichever response is current, so it survives a refresh and a filter
  // change without being stored anywhere or sent to the server. Not in the
  // URL either -- the query string is the SELECTION, which decides what the
  // server builds, and this decides nothing the server does.
  const [sort, setSort] = useState<ChatterSort | null>(null)
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
  // The board on screen, when a refresh of it has failed. Never the previous
  // selection's (react-query's placeholder), and never a waiting shell: a
  // shell has no last answer to fall back on, and says what is happening in
  // its own words.
  const shown = board.answer
  const banner = shown !== undefined && isReady(shown) && board.isError
    ? shown : null
  // The market the top bar names is the one the reader is on. Placeholder
  // data is the previous selection's board -- after a market switch, the
  // previous MARKET's, session and all -- so a board speaks for the bar only
  // when it is this market's. Until one is, the bar names the market the
  // reader chose and claims no session for it.
  const context = [board.data, initial].find(
    (candidate) => candidate?.market === selection.market) ?? null

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
            {context ? (
              <>
                <span className={`rh-dot${context.session === 'closed' ? ' closed' : ''}`} />
                {marketLabel(context)}
              </>
            ) : MARKET_NAME[selection.market]}
          </p>
        </header>

        <main id="rh-main" className="rh-main" ref={main} tabIndex={-1}
              aria-label={title}>
          {/* Data that was true a minute ago beats a blank page, as long as
              the surface says the refresh failed and when it last succeeded. */}
          {banner
            ? <StaleNotice error={board.error}
                           since={berlinStamp(banner.generated_at)}
                           onRetry={board.retry} />
            : null}
          {expired
            ? <SignedOut />
            : <Page route={route} board={board} selection={selection}
                    span={span} title={title} visible={visible}
                    isAdmin={isAdmin} go={go} vocabulary={initial}
                    bannerUp={banner !== null}
                    sort={sort} onSort={setSort} />}
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
function Page({ route, board, selection, span, title, visible, isAdmin, go,
                vocabulary, bannerUp, sort, onSort }: {
  route: HubRoute
  board: ReturnType<typeof useBoard>
  selection: Selection
  span: PanelSpan
  title: string
  visible: boolean
  isAdmin: boolean
  go: (route: HubRoute, selection?: Selection, span?: PanelSpan,
       options?: { keepFocus?: boolean }) => void
  /** Where the filters read the server's vocabulary while this selection
   *  has no board of its own yet. */
  vocabulary: BoardPayload
  /** The failure notice is up, with a Retry of its own. */
  bannerUp: boolean
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
}) {
  // Declared before any early return, because hooks are.
  const [marking, setMarking] = useState<string | null>(null)
  // Freed by the write itself settling, never by a callback handed to one
  // `mutate` call: leaving a page resets the write's refusal (below), which
  // detaches the write from this page, and react-query then drops the
  // callbacks that call carried -- the guard stayed shut until a reload.
  const settled = useCallback(() => setMarking(null), [])
  const watch = useWatchMutation(settled)
  // The reader's marks. A waiting shell carries none -- its `watching: []` is
  // a placeholder, not this account's list -- so they are known from a built
  // board or from the last mark's own answer, and otherwise not at all: a
  // Watch button offered then would call a marked company unmarked.
  const watching = board.data !== undefined && isReady(board.data)
    ? board.data.watching : watch.data
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
    watch.mutate({ ticker, on: !(watching ?? []).includes(ticker) })
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

  // Overview, Human chatter and Watching are three readings of one board --
  // and each is drawn in every state that board can be in, under its own
  // heading and controls. What changes is only what stands where the rows
  // would, decided here, once, before any page reads a row.
  if (route.page === 'overview' || route.page === 'chatter'
      || route.page === 'watching') {
    // The answer for THIS selection. Placeholder data is the previous
    // selection's board, kept by react-query while the new one loads;
    // drawing it would put one question's rows under another's filters.
    const answer = board.answer
    // Only Human chatter has the window and feed controls the waiting
    // notices point a tired reader at.
    const controls = route.page === 'chatter'
    const standIn = answer === undefined
      ? (board.isError
        ? <Unavailable error={board.error} retry={board.retry} />
        : <Loading label={`Loading ${title.toLowerCase()}…`} />)
      : isReady(answer) ? null
      // A shell. Failing builds first: "this is taking a while" is the wrong
      // thing to keep saying about a key whose builds are failing.
      : answer.failed
        ? <FailedNotice failing={board.failing} onRetry={board.retry} />
      // Asks that keep failing are said in the shell's own notice, with the
      // page's one Retry: there is no board for "Showing the last answer" to
      // be about.
      : answer.busy
        ? <Busy failing={board.failing} controls={controls}
                onRetry={board.retry} />
      : <Pending delayed={board.delayed} failing={board.failing}
                 controls={controls} onRetry={board.retry} />
    const freshness = {
      received: board.received,
      // Nothing is fetching a replacement: the last request failed, none is
      // out, and nothing is waiting to ask again. An expired board must not
      // go on promising a recalculation the page has stopped attempting.
      stalled: board.isError && board.fetchStatus === 'idle'
        && !(answer !== undefined
             && owesABoard(answer, board.received, Date.now())),
      // One Retry on the page: the failure notice's, while it is up.
      onRetry: bannerUp ? undefined : board.retry,
    }
    const shown = answer ?? null
    const open = (ticker: string) => go({ page: 'research', ticker })
    if (route.page === 'overview') {
      return <Overview board={shown} {...freshness} standIn={standIn}
                       onOpen={open} onGo={(page) => go({ page })} />
    }
    if (route.page === 'watching') {
      return (
        <Watching board={shown} {...freshness} standIn={standIn}
                  onOpen={open} watching={watch.data}
                  onToggleWatch={onToggleWatch} pending={marking}
                  watchError={watch.error} />
      )
    }
    return (
      <Chatter board={shown} vocabulary={board.data ?? vocabulary}
               selection={selection} {...freshness} standIn={standIn}
               onOpen={open} onSelect={(next) => go(route, next)}
               sort={sort} onSort={onSort} />
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

function berlinStamp(iso: string | null): string | null {
  if (iso === null) return null
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

/** What the top bar calls a market no board of it has answered for yet. */
const MARKET_NAME: Record<Selection['market'], string> = {
  us: 'US markets',
  de: 'Germany',
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

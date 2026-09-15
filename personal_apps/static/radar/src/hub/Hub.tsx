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
import { Analysis } from './Analysis'
import type { AnalysisRoute } from './Analysis'
import type { Range } from './analysisTypes'
import { Chatter } from './Chatter'
import type { ChatterMode } from './Chatter'
import type { ChatterSort } from './chatterSort'
import { Overview } from './Overview'
import {
  Busy, FailedNotice, Forbidden, Loading, Missing, Pending, SignedOut,
  StaleNotice, Unavailable,
} from './PageState'
import { Research } from './Research'
import { SelectedPriceCharts } from './selectedPriceContext'
import { Watching } from './Watching'
import { Search } from './Search'
import {
  hashFor, isInPageAnchor, readAnalysisRange, readRootRoute, readRoute,
  readSelection, readSpan, urlFor,
} from './navigation'
import type { AnalysisRange, HubRoute } from './navigation'
import {
  owesABoard, selectionOf, useBoard, useWatchMutation,
} from './queries'
import './hub.css'

/** Only destinations this release actually renders. An empty page behind a
 *  nav item is a promise the surface cannot keep -- which is why the B
 *  reference's News, Combined radar, Portfolio and Analysis are not here.
 *
 *  Flat, not grouped. The old left rail had room for `Discover` / `Your
 *  stocks` / `Review` headings above one item each; a 48px horizontal band
 *  does not, and four labels across a bar need no taxonomy to be found. */
const DESTINATIONS = [
  { page: 'overview', label: 'Overview' },
  { page: 'chatter', label: 'Human Chatter' },
  { page: 'analysis', label: 'Analysis' },
  { page: 'watching', label: 'Watching' },
  { page: 'activity', label: 'Activity' },
] as const

export function Hub({ initial, isAdmin, selectedPriceCharts = false }: {
  initial: BoardPayload
  isAdmin: boolean
  /** The server's selected-session chart flag, from the shell (a rendering
   *  hint; the chart endpoint enforces it itself). */
  selectedPriceCharts?: boolean
}) {
  const [route, setRoute] = useState<HubRoute>(() => initialRoute())
  const [selection, setSelection] = useState<Selection>(
    () => readSelection(window.location.search, seedSelection(initial),
                        initial.all_sources))
  const [span, setSpan] = useState<PanelSpan>(() => readSpan(window.location.search))
  // The Analysis window as written in the address (HA1). Beside the board's
  // selection, never inside it: the board API never receives these keys and
  // Back from Analysis returns to the board the reader left.
  const [analysisRange, setAnalysisRange] = useState<AnalysisRange | null>(
    () => readAnalysisRange(window.location.search))
  // Analysis reads its own series; an expired session there is as final as
  // one the board reports.
  const [analysisExpired, setAnalysisExpired] = useState(false)
  // Chatter's ordering lives HERE, not in Chatter, because Chatter unmounts
  // when the reader opens a company. Held in memory only: it is a view over
  // whichever response is current, so it survives a refresh and a filter
  // change without being stored anywhere or sent to the server. Not in the
  // URL either -- the query string is the SELECTION, which decides what the
  // server builds, and this decides nothing the server does.
  const [sort, setSort] = useState<ChatterSort | null>(null)
  // The text filter and the chatter mode live here for the same reason the
  // ordering does: they are a view over whichever response is current, and
  // Chatter unmounts whenever the reader opens a company from somewhere else
  // or steps out to Overview. Held in memory only -- the query string is the
  // SELECTION, which decides what the server builds, and neither of these
  // decides anything the server does.
  const [filter, setFilter] = useState('')
  const [mode, setMode] = useState<ChatterMode>('research')
  // Whether this visit to Human chatter has already made its opening
  // selection. Up here for the same reason as the three above: the workspace
  // unmounts on every Table/Research toggle, and a remount that forgot would
  // re-select a company the reader had deliberately cleared -- REPLACING the
  // `#chatter` entry they were standing on, so Back could not return to it.
  const [opened, setOpened] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const main = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const expiredRef = useRef(false)
  const visible = useVisible()
  const client = useQueryClient()

  // Human Chatter owns a distinct, price-independent candidate set. Other
  // hub pages retain their existing board selection and default behaviour.
  const pageSelection = route.page === 'chatter'
    ? { ...selection, sort: 'chatter' as const, dir: 'desc' as const }
    : selection

  // useBoard decides for itself whether this payload matches the key it would
  // seed; passing it unconditionally is safe. Analysis has no use for a board
  // and disables its recurring reads while it is the page (HA1).
  const board = useBoard(pageSelection, expiredRef.current ? undefined : initial,
                         visible, route.page !== 'analysis')

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
        setRoute(initialRoute())
      }
      setSelection(readSelection(window.location.search, seedSelection(initial),
                                 initial.all_sources))
      setSpan(readSpan(window.location.search))
      setAnalysisRange(readAnalysisRange(window.location.search))
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
  const expired = (board.error instanceof BoardUnavailable
    && board.error.reason === 'session') || analysisExpired
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
                          options: { keepFocus?: boolean; analysis?: AnalysisRange | null } = {}) => {
    // The analysis window travels only with the analysis destination; every
    // other page drops it from the address, and the board context stays.
    const nextAnalysis = next.page === 'analysis'
      ? (options.analysis !== undefined ? options.analysis : analysisRange) : null
    window.history.pushState(null, '', urlFor(next, nextSelection, nextSpan, nextAnalysis))
    setRoute(next)
    setSelection(nextSelection)
    setSpan(nextSpan)
    setAnalysisRange(nextAnalysis)
    setMenuOpen(false)
    // The reader asked for a different page; the keyboard should be on it and
    // a screen reader should be told, which neither gets from a URL change.
    //
    // Not for a control INSIDE the page. Changing the chart span or a filter
    // is a toggle, and moving focus to the top would make a keyboard reader
    // tab back through the whole page to press the next one.
    if (!options.keepFocus) main.current?.focus()
  }, [selection, span, analysisRange])

  /** The same navigation as `go`, without a history entry and without moving
   *  focus. For the cases that are not a reader's choice: the workspace
   *  opening on the first candidate, and Analysis pinning a resolved ticker
   *  to its IDs. A pushState there would make Back a no-op that lands on the
   *  same page with nothing selected. */
  const replace = useCallback((next: HubRoute, nextSelection = selection,
                               nextSpan = span, analysis: AnalysisRange | null = null) => {
    const nextAnalysis = next.page === 'analysis' ? analysis : null
    window.history.replaceState(null, '', urlFor(next, nextSelection, nextSpan, nextAnalysis))
    setRoute(next)
    setAnalysisRange(nextAnalysis)
  }, [selection, span])

  /** Analysis's one way to move: push for a reader's change of company or
   *  window, replace for the canonical pinning of a resolved ticker. */
  const onAnalysisNavigate = useCallback((next: AnalysisRoute, range: Range | null,
                                          options: { replace?: boolean; keepFocus?: boolean } = {}) => {
    const written: AnalysisRange | null = range === null ? null : { from: range.from, to: range.to }
    if (options.replace) replace(next, selection, span, written)
    else go(next, selection, span, { keepFocus: options.keepFocus, analysis: written })
  }, [go, replace, selection, span])
  const onAnalysisExpired = useCallback(() => setAnalysisExpired(true), [])

  // Leaving Human chatter ends the visit. Coming back is a fresh one, and a
  // fresh one opens on the first candidate again -- which is what the brief
  // asks for and what a reader returning to a list expects.
  useEffect(() => {
    if (route.page !== 'chatter') setOpened(false)
  }, [route.page])

  const title = titleFor(route)
  // The board on screen, when a refresh of it has failed. Never the previous
  // selection's (react-query's placeholder), and never a waiting shell: a
  // shell has no last answer to fall back on, and says what is happening in
  // its own words.
  const shown = board.answer
  // Not on Analysis: its series are its own, and a board refresh that failed
  // behind it is nothing the reader asked about there.
  const banner = shown !== undefined && isReady(shown) && board.isError
    && route.page !== 'analysis' ? shown : null
  // The market the top bar names is the one the reader is on. Placeholder
  // data is the previous selection's board -- after a market switch, the
  // previous MARKET's, session and all -- so a board speaks for the bar only
  // when it is this market's. Until one is, the bar names the market the
  // reader chose and claims no session for it.
  const context = [board.data, initial].find(
    (candidate) => candidate?.market === selection.market) ?? null

  return (
    <SelectedPriceCharts.Provider value={selectedPriceCharts}>
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

      <header className="rh-top">
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
        <p className="rh-brand">
          <Logo />
          {/* In its own element so the narrow bar can drop the word without
              collapsing the mark: `font-size: 0` on the paragraph took the
              brand's width to zero and left the logo overflowing onto the
              search field. */}
          <span className="rh-wordmark">RADAR</span>
        </p>
        <div className="rh-topmid">
          <Search onOpen={(ticker) => go(openRoute(route, ticker))} />
        </div>
        <p className="rh-session">
          {route.page === 'analysis' ? (
            // Analysis is not a market board: it names its own explicit scope
            // rather than the selected market's session.
            <><span className="rh-venue">US primary · </span>USD · retrospective</>
          ) : context ? (
            <>
              <span className={`rh-dot${context.session === 'closed' ? ' closed' : ''}`} />
              {/* The venue is the half that stops fitting on a phone. The
                  state is the half that changes what the ranking MEANS --
                  with the exchange shut there is no movement to diverge from
                  -- so it stays at every width. */}
              <span className="rh-venue">
                {context.market_venue}{' · '}
              </span>
              {sessionWord(context)}
            </>
          ) : MARKET_NAME[selection.market]}
        </p>
        {/* Where Radar is going. Three fictional mockups the owner asked to
            keep reachable from the live hub -- long-term visual references,
            not shipped capability, and the gallery page says so. In the
            identity bar, not the destination band: it is a document that
            leaves the application, not a page of it, so the router is not
            involved and Back returns here. */}
        <a className="rh-gallerylink"
           href="/static/radar/design-reference/index.html">
          Future Radar design
        </a>
      </header>

      <nav id="rh-nav" className={`rh-nav${menuOpen ? ' open' : ''}`}
           aria-label="Radar">
        {DESTINATIONS.map((item) => (
          <a
            key={item.page}
            className="rh-navlink"
            href={urlFor({ page: item.page }, selection, span)}
            // Human chatter stays the current destination while a company is
            // open inside it: the workspace IS the page, not a page the
            // reader left.
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
        {/* Standalone research is not a destination anybody navigates to; it
            is where a search from another page, or an old bookmark, lands.
            The band names the company rather than leaving all four labels
            inactive with no account of where the reader is -- and it sits
            NEXT TO the destinations it qualifies, not pushed to the far end
            of a 1920px bar beside Administration, which is what it did when
            it shared their container. */}
        {route.page === 'research' ? (
          <span className="rh-navcrumb">{route.ticker}</span>
        ) : null}
        <div className="rh-navend">
          <a className="rh-navlink" href={`/radar/legacy/${window.location.search}`}>
            Legacy Radar
          </a>
          {/* Rendered for admins only; /radar/api/ops enforces this itself and
              does not trust the absence of a link. */}
          {isAdmin ? (
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
          ) : null}
        </div>
      </nav>

      <main id="rh-main" className="rh-main" ref={main} tabIndex={-1}
            aria-label={title}>
        {route.page === 'analysis' && !expired ? (
          <Analysis route={route} rawRange={analysisRange}
                    onNavigate={onAnalysisNavigate}
                    onSearch={() => document.getElementById('rh-search-input')?.focus()}
                    onSessionExpired={onAnalysisExpired} />
        ) : null}
        {/* Data that was true a minute ago beats a blank page, as long as
            the surface says the refresh failed and when it last succeeded. */}
        {banner
          ? <StaleNotice error={board.error}
                         since={berlinStamp(banner.generated_at)}
                         onRetry={board.retry} />
          : null}
        {expired
          ? <SignedOut />
          : route.page === 'analysis' ? null
          : <Page route={route} board={board} selection={selection}
                  span={span} title={title} visible={visible}
                  isAdmin={isAdmin} go={go} replace={replace}
                  vocabulary={initial} bannerUp={banner !== null}
                  sort={sort} onSort={setSort}
                  filter={filter} onFilter={setFilter}
                  mode={mode} onMode={setMode}
                  opened={opened} onOpened={() => setOpened(true)} />}
      </main>
    </div>
    </SelectedPriceCharts.Provider>
  )
}

/** Where a global search hit opens.
 *
 *  Inside the chatter workspace it opens IN the workspace, because that is
 *  where the reader already is and the candidate rail beside it is the
 *  context they were using. Anywhere else it opens standalone research,
 *  exactly as before: a company found from Overview has no candidate list to
 *  sit inside. */
function initialRoute(): HubRoute {
  return window.location.pathname === '/radar/'
    ? readRootRoute(window.location.search, window.location.hash)
    : readRoute(window.location.hash)
}

function openRoute(route: HubRoute, ticker: string): HubRoute {
  // On Analysis a search hit is the explicit way to resolve a company's
  // current mapping again; it stays on Analysis.
  if (route.page === 'analysis') return { page: 'analysis', ticker }
  return route.page === 'chatter'
    ? { page: 'chatter', ticker }
    : { page: 'research', ticker }
}

/** Which page, and what it needs.
 *
 *  Overview, Watching, Activity and Admin arrive in H3 and H4; until then they
 *  say so rather than rendering an empty panel, which a reader could not tell
 *  from a measured emptiness.
 */
function Page({ route, board, selection, span, title, visible, isAdmin, go,
                replace, vocabulary, bannerUp, sort, onSort, filter, onFilter,
                mode, onMode, opened, onOpened }: {
  route: HubRoute
  board: ReturnType<typeof useBoard>
  selection: Selection
  span: PanelSpan
  title: string
  visible: boolean
  isAdmin: boolean
  go: (route: HubRoute, selection?: Selection, span?: PanelSpan,
       options?: { keepFocus?: boolean }) => void
  replace: (route: HubRoute, selection?: Selection, span?: PanelSpan) => void
  /** Where the filters read the server's vocabulary while this selection
   *  has no board of its own yet. */
  vocabulary: BoardPayload
  /** The failure notice is up, with a Retry of its own. */
  bannerUp: boolean
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
  filter: string
  onFilter: (next: string) => void
  mode: ChatterMode
  onMode: (next: ChatterMode) => void
  opened: boolean
  onOpened: () => void
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
  // "could not be saved" banner followed the reader to another company --
  // including from one selected candidate to the next inside the workspace,
  // which is why the chatter route keys on its ticker too.
  const here = route.page === 'research' ? route.ticker
    : route.page === 'chatter' ? `chatter:${route.ticker ?? ''}`
    : route.page
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
    // Explicitly, rather than by elimination: `page` on the first union
    // member is itself a union of four literals, so ruling out two of them
    // leaves TypeScript unable to see that only `chatter` is left -- and
    // `route.ticker` unreachable.
    if (route.page !== 'chatter') return <Placeholder title={title} />
    return (
      <Chatter
        // This selection's answer: a board, a waiting shell, or null while
        // nothing for it has answered yet. Only a built board has rows; the
        // rest is `standIn`, under the same heading and controls.
        board={shown}
        vocabulary={board.data ?? vocabulary}
        selection={selection}
        {...freshness}
        standIn={standIn}
        span={span}
        visible={visible}
        selected={route.ticker ?? null}
        mode={mode}
        onMode={onMode}
        // A deliberate choice: it goes in the history, so Back returns to the
        // company the reader was looking at before this one.
        //
        // Opening from the comparison table switches to the workspace, which
        // is where an opened company is actually readable. The table has no
        // room to show one, and leaving the reader on it after they asked for
        // a company would look like the press did nothing.
        onOpen={(ticker) => { onMode('research'); go({ page: 'chatter', ticker }) }}
        onOpenReplace={(ticker) => replace({ page: 'chatter', ticker })}
        // Clearing is a decision, so it ends the opening-selection question
        // for this visit: the workspace must not put a company back the
        // moment the reader steps through Table and returns.
        onClear={() => { onOpened(); go({ page: 'chatter' }) }}
        hrefFor={(ticker) => urlFor({ page: 'chatter', ticker }, selection, span)}
        onSpan={(next) => go(route, selection, next, { keepFocus: true })}
        onSelect={(next) => go(route, next)}
        onSearch={() => document.getElementById('rh-search-input')?.focus()}
        sort={sort}
        onSort={onSort}
        filter={filter}
        onFilter={onFilter}
        opened={opened}
        onOpened={onOpened}
        watching={watching}
        onToggleWatch={watching === undefined ? undefined : onToggleWatch}
        watchPending={marking !== null}
        watchError={watch.error}
      />
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
    case 'chatter': return 'Human Chatter'
    case 'watching': return 'Watching'
    case 'activity': return 'Activity'
    case 'admin': return 'Administration'
    case 'analysis': return 'Analysis'
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

function sessionWord(payload: BoardPayload): string {
  return payload.session === 'regular' ? 'open' : payload.session
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

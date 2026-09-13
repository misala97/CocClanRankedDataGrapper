// Human chatter as a workspace: candidates on the left, the one being
// examined in the middle, its evidence on the right.
//
// The two questions the surface exists to answer -- which of these is worth
// my time, and is this one real -- stop being two pages. Picking a candidate
// does not leave the list, so comparing three of them is three presses rather
// than three round trips through a back button.
//
// One board query (the hub's, already loaded) and one detail query for
// whichever company is selected. Not one per row, and not a second query to
// fill the right rail: that rail is the selected company's OWN board row,
// which is already in hand.
//
// The selected company lives in the address (#chatter/KSTR), so Back returns
// to the one before it and a link to a company is a link anybody can send.
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import type { BoardPayload, PanelSpan, ReadyBoard, Row, Selection } from '../types'
import { exchangeLabel, segmentLabel } from '../format'
import { CandidateList } from './CandidateList'
import { EvidenceRail } from './EvidenceRail'
import { Filters } from './Filters'
import { Loading } from './PageState'
import {
  ChartSection, EvidencePanel, NotHere, PostsPanel, Quote,
} from './ResearchContent'
import { SortPicker } from './SortPicker'
import type { ChatterSort } from './chatterSort'
import { useDetail } from './queries'

/** Above this width the workspace shows the rail and the company side by
 *  side, so opening on the first candidate costs the reader nothing. Below it
 *  they are sequential screens, and pre-selecting would drop a reader who
 *  asked for the list into a company they did not choose.
 *
 *  860 is where the two columns stop fitting: a 300px rail, the 12px gutter,
 *  28px of page padding and the 500px the centre needs for a legible chart.
 *  hub.css carries the same number -- stated twice, because a media query
 *  cannot decide a navigation. Its half is written `max-width: 859.98px` for
 *  the reason every responsive stylesheet eventually learns: a viewport is
 *  not an integer. At 859.5 -- routine under browser zoom and fractional DPI
 *  -- `max-width: 859px` and `min-width: 860px` are BOTH false, and the two
 *  halves disagreed about which layout was on screen. */
const SIDE_BY_SIDE = '(min-width: 860px)'

const NO_ROWS: Row[] = []

export function ChatterWorkspace({
  board, ready = null, standIn, selection, rows, selected, onSelect,
  onSelectReplace, onClear, hrefFor, span, onSpan, visible, filter, onFilter,
  sort, onSort, onSelection, watching, onToggleWatch, watchPending,
  watchError, onSearch, opened, onOpened,
}: {
  /** Where the feed controls read the server's vocabulary. A built board, or
   *  -- while this selection is still being built -- a waiting shell or any
   *  earlier board: the vocabulary is the server's, not the selection's. */
  board: BoardPayload
  /** The built board for THIS selection, or null while there is none. Only
   *  a built board has candidates; the evidence rail reads its rows. */
  ready?: ReadyBoard | null
  /** What stands where the candidates would while `ready` is null: the
   *  pending, busy or failed notice, or the unavailable view. */
  standIn?: ReactNode
  selection: Selection
  /** What the filter and the ordering left, in the order they are shown. */
  rows: Row[]
  selected: string | null
  /** A deliberate choice: pushes history. */
  onSelect: (ticker: string) => void
  /** The opening selection: replaces, so Back leaves the hub rather than
   *  stepping through a company nobody chose. */
  onSelectReplace: (ticker: string) => void
  onClear: () => void
  hrefFor: (ticker: string) => string
  span: PanelSpan
  onSpan: (span: PanelSpan) => void
  visible: boolean
  filter: string
  onFilter: (next: string) => void
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
  onSelection?: (next: Selection) => void
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  watchPending: boolean
  watchError: unknown
  onSearch: () => void
  /** Whether this visit to Human chatter has already made its opening
   *  selection. Held by the hub, NOT here: this component unmounts on every
   *  Table/Research toggle, and a remount that forgot would re-select a
   *  company the reader had deliberately cleared -- replacing, and so
   *  destroying, the `#chatter` history entry they were standing on. */
  opened: boolean
  onOpened: () => void
}) {
  const first = rows[0]?.ticker ?? null
  // The board's own candidates, before the filter -- none while a shell is
  // standing in for the board. The counts and the evidence rail read THIS,
  // never a shell's null rows.
  const all = ready ? ready.rows : NO_ROWS

  // Whether both columns fit. Tracked rather than read once, so a reader who
  // opens the list narrow and then widens -- a rotation, a resized window --
  // gets the opening selection when the layout that wants it appears.
  const [sideBySide, setSideBySide] = useState(matchesSideBySide)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia(SIDE_BY_SIDE)
    const update = () => setSideBySide(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  // The opening selection, and only the opening one. Guarded on `selected`
  // being null, so a refresh that reorders the board -- or a sort, or a
  // filter -- can never move the reader off the company they are reading.
  useEffect(() => {
    if (selected !== null || first === null || opened || !sideBySide) return
    onOpened()
    onSelectReplace(first)
  }, [selected, first, opened, sideBySide, onOpened, onSelectReplace])

  // On the sequential layout the list and the company are two screens in one
  // document, so choosing a candidate from halfway down the list opened the
  // company already scrolled halfway down -- past its own heading and its
  // price. Side by side there is nothing to correct: the reader never left
  // the top of the page.
  useEffect(() => {
    if (sideBySide || selected === null) return
    window.scrollTo({ top: 0 })
  }, [selected, sideBySide])

  // The selected company's row on THIS board, which is what the evidence rail
  // reads. Looked up in the whole response rather than in the filtered view:
  // a company the text filter hides is still on the board, and its figures
  // are still this window's.
  const row = selected
    ? all.find((candidate) => candidate.ticker === selected) ?? null
    : null
  // Two different absences. A company the text filter hides is on this
  // board and one keystroke away; a company reached by search or by a link
  // was never ranked here at all, and blaming the filter for that would send
  // the reader to clear a filter that is not the reason.
  const outside = selected !== null
    && !rows.some((candidate) => candidate.ticker === selected)
  const onBoard = row !== null

  return (
    <div className="rh-workspacegrid"
         data-view={selected === null ? 'list' : 'company'}>
      <section className="rh-rail" aria-labelledby="rh-candidates-head">
        <div className="rh-railhead">
          <div>
            <h2 id="rh-candidates-head">Candidates</h2>
            <p className="small muted">
              {ready === null
                ? 'Waiting for this selection'
                : rows.length === all.length
                  ? `${all.length} ${all.length === 1 ? 'company' : 'companies'}`
                  : `${rows.length} of ${all.length} shown`}
            </p>
          </div>
        </div>

        <div className="rh-railcontrols">
          <label className="rh-field rh-railfilter">
            <span>Filter companies</span>
            <input
              type="search"
              value={filter}
              placeholder="Ticker or name"
              onChange={(event) => onFilter(event.target.value)}
            />
          </label>
          <SortPicker sort={sort} onSort={onSort} className="rh-railsort"
                      idPrefix="rh-railsort" />
          {sort ? (
            <button type="button" className="rh-textbutton rh-railreset"
                    onClick={() => onSort(null)}>
              Unusual activity
            </button>
          ) : null}
          {onSelection ? (
            <Filters board={board} selection={selection} onChange={onSelection}
                     compact />
          ) : null}
        </div>

        {ready === null ? (
          // The board is being built, or could not be. The notice says
          // which, in the rail, where the candidates it stands for would be.
          <div className="rh-railstandin">{standIn}</div>
        ) : rows.length === 0 ? (
          <p className="muted small rh-railempty">
            {all.length === 0
              ? 'No company cleared this selection. Widen the window or the '
                + 'feeds, or check Activity for whether the fetch ran.'
              : `Nothing among the ${all.length} loaded ${
                  all.length === 1 ? 'company' : 'companies'} matches `
                + 'that filter. Clearing it brings them back.'}
          </p>
        ) : (
          <div className="rh-railscroll">
            <CandidateList rows={rows} selected={selected} hrefFor={hrefFor}
                           onSelect={onSelect}
                           labelledBy="rh-candidates-head" />
          </div>
        )}
      </section>

      {selected === null ? (
        <section className="rh-selected rh-nothingpicked">
          <div className="rh-empty">
            <h2>Pick a candidate.</h2>
            <p>
              {ready === null
                ? 'The candidate list is waiting on the board. Nothing was '
                  + 'requested for a company, so nothing here is loading.'
                : rows.length === 0
                  ? 'There is nothing on this board to open. Nothing was '
                    + 'requested for a company, so nothing here is loading.'
                  : 'Choosing one from the list shows its price, its chart '
                    + 'against the chatter, and the evidence behind the row.'}
            </p>
          </div>
        </section>
      ) : (
        <SelectedCompany
          ticker={selected} board={board} selection={selection} row={row}
          outside={outside} first={first} span={span} onSpan={onSpan}
          visible={visible} onBack={onClear} onSearch={onSearch}
          onSelect={onSelect} watching={watching}
          onToggleWatch={onToggleWatch} watchPending={watchPending}
          watchError={watchError} onBoard={onBoard} />
      )}
    </div>
  )
}

/** The centre and the right rail, which are one company between them.
 *
 *  Both read one `useDetail`. Errors and loading are scoped HERE, not to the
 *  workspace: a company whose panel fails must not blank the candidate list
 *  the reader would use to pick another one.
 */
function SelectedCompany({ ticker, board, selection, row, outside, onBoard,
                          first, span, onSpan, visible, onBack, onSearch,
                          onSelect, watching, onToggleWatch, watchPending,
                          watchError }: {
  ticker: string
  board: BoardPayload
  selection: Selection
  row: Row | null
  outside: boolean
  onBoard: boolean
  first: string | null
  span: PanelSpan
  onSpan: (span: PanelSpan) => void
  visible: boolean
  onBack: () => void
  onSearch: () => void
  onSelect: (ticker: string) => void
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  watchPending: boolean
  watchError: unknown
}) {
  const { data, error, isPlaceholderData, refetch } = useDetail(
    ticker, selection, span, visible)

  const backToList = (
    <p className="rh-crumb rh-backtolist">
      <button type="button" className="rh-textbutton" onClick={onBack}>
        ← Back to candidates
      </button>
    </p>
  )

  /** The rail, whatever the centre is doing.
   *
   *  Every figure in it comes from the BOARD row, which is in hand before the
   *  detail request is even made -- so blanking it while the centre loads, or
   *  losing it entirely when the centre fails, would throw away evidence that
   *  never depended on the thing that broke. It also carries the Watch
   *  control, which is the only write on the page. */
  const rail = (
    <EvidenceRail ticker={ticker} row={row} detail={data ?? null}
                  windowHours={board.window_hours}
                  marketVenue={board.market_venue}
                  isWatched={watching?.includes(ticker) ?? false}
                  onToggleWatch={onToggleWatch}
                  watchPending={watchPending} watchError={watchError} />
  )

  // Placeholder data is the PREVIOUS company's panel. Rendering it would put
  // one company's price, chart and evidence under another company's heading
  // and address.
  if (!data || isPlaceholderData) {
    if (error && !isPlaceholderData) {
      return (
        <>
          <section className="rh-selected">
            {backToList}
            <NotHere ticker={ticker} error={error} onBack={onBack}
                     onSearch={onSearch} retry={() => void refetch()}
                     backLabel="Back to candidates" onBoard={onBoard} />
          </section>
          {rail}
        </>
      )
    }
    return (
      <>
        <section className="rh-selected">
          {backToList}
          <Loading label={`Loading ${ticker}…`} />
        </section>
        {rail}
      </>
    )
  }

  const { identity, chart, breakdown } = data

  return (
    <>
      <section className="rh-selected" aria-labelledby="rh-selected-head">
        {backToList}

        {outside ? (
          <div className="rh-notice amber" role="status">
            <div>
              <strong>Outside this candidate list.</strong>
              <p>
                {onBoard
                  ? `${identity.ticker} is on this board, but the filter you `
                    + 'typed leaves it out of the list beside this.'
                  : `${identity.ticker} did not rank on this board at all in `
                    + 'the current window, market and feed selection, so it '
                    + 'has no row in the list beside this.'}
                {' '}Its own figures below are unaffected.
                {first ? (
                  <>
                    {' '}
                    <button type="button" className="rh-textbutton"
                            onClick={() => onSelect(first)}>
                      Open the first candidate instead
                    </button>
                  </>
                ) : null}
              </p>
            </div>
          </div>
        ) : null}

        <div className="rh-selectedhead">
          <div className="rh-identity">
            <span className="rh-mark large" aria-hidden="true">
              {identity.ticker.slice(0, 2)}
            </span>
            <div>
              <h2 id="rh-selected-head">
                {identity.name ?? identity.ticker}{' '}
                <span className="rh-selectedticker">{identity.ticker}</span>
              </h2>
              <p className="muted small">
                {[segmentLabel(identity.segment),
                  exchangeLabel(identity.exchange)].filter(Boolean).join(' · ')}
              </p>
            </div>
          </div>
        </div>

        <div className="rh-stack">
          <Quote detail={data} headingId="rh-ws-quote-head" />
          <ChartSection chart={chart} quoteVenue={identity.quote.venue}
                        ticker={identity.ticker} span={span} onSpan={onSpan}
                        headingId="rh-ws-chart-head" />
          <Tabs breakdown={breakdown} detail={data}
                windowHours={selection.window} />
        </div>
      </section>

      {rail}
    </>
  )
}

/** Whether both columns fit, right now. `true` where there is no matchMedia
 *  at all -- a server render or a test environment has no viewport to ask
 *  about, and the desk layout is the one the component is written for. */
function matchesSideBySide(): boolean {
  if (typeof window === 'undefined'
      || typeof window.matchMedia !== 'function') return true
  return window.matchMedia(SIDE_BY_SIDE).matches
}

/** Evidence and the source posts, one at a time.
 *
 *  Both are long, and stacked they push the chart off the top of a workspace
 *  column that is already sharing the width with two rails. Rendered as real
 *  tab semantics -- and both panels stay in the tree, hidden with the
 *  attribute, so nothing has to re-fetch or re-measure to come back.
 */
function Tabs({ breakdown, detail, windowHours }: {
  breakdown: Parameters<typeof EvidencePanel>[0]['breakdown']
  detail: Parameters<typeof PostsPanel>[0]['detail']
  windowHours: number
}) {
  const tabs = [
    { id: 'evidence', label: 'Evidence' },
    { id: 'posts', label: `Source posts (${detail.post_total})` },
  ] as const
  // Component state, deliberately: which tab is open is a preference about
  // one company's panel, not a place, and putting it in the address would
  // make Back step through tab presses.
  const [active, setActive] = useState<'evidence' | 'posts'>('evidence')
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const move = (delta: number) => {
    const index = tabs.findIndex((tab) => tab.id === active)
    const next = tabs[(index + delta + tabs.length) % tabs.length]!
    setActive(next.id)
    refs.current[next.id]?.focus()
  }

  return (
    <section className="rh-panel rh-tabs">
      <div className="rh-tablist" role="tablist" aria-label="Evidence for this company">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`rh-tab-${tab.id}`}
            ref={(node) => { refs.current[tab.id] = node }}
            aria-selected={active === tab.id}
            aria-controls={`rh-tabpanel-${tab.id}`}
            // One tab stop for the whole set, arrows to move between them,
            // which is what a tablist owes a keyboard reader.
            tabIndex={active === tab.id ? 0 : -1}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
              if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
            }}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="rh-tabpanel-evidence"
           aria-labelledby="rh-tab-evidence" hidden={active !== 'evidence'}>
        <EvidencePanel breakdown={breakdown} windowHours={windowHours} />
      </div>
      <div role="tabpanel" id="rh-tabpanel-posts"
           aria-labelledby="rh-tab-posts" hidden={active !== 'posts'}>
        <PostsPanel detail={detail} />
      </div>
    </section>
  )
}

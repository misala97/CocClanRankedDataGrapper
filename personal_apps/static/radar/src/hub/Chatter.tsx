// Human chatter: what people are actually discussing, in the server's order.
//
// The list answers one question -- which of these is worth my time -- and
// hands the second, is this real, to Research. That split is why the row shows
// its evidence rather than a score: how far above its own normal, how many
// voices, which platforms were talking, and every qualification the server
// attached. A single number would rank the same companies while telling the
// reader nothing about whether to believe it.
//
// Nothing here is a recommendation. The rank is unusual chatter with price
// context, and the copy says so.
//
// The row is deliberately COMPACT. The first version let two cells set the
// height: it printed every concrete feed name, so a ticker seen on thirty
// subreddits filled most of the table width with the word Reddit, and it
// stacked three tone counts vertically. Both facts are still here -- the
// concrete feed identifiers and the exact tone counts -- inside a detail the
// reader opens, rather than as prose every row has to carry.
import { useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { usdText } from '../format'
import { isReady } from '../types'
import type {
  BoardPayload, PanelSpan, QuoteCurrency, ReadyBoard, Row, Selection,
} from '../types'
import { ChatterWorkspace } from './ChatterWorkspace'
import { sourcePresentation, tonePresentation } from './chatterPresentation'
import type { SourcePresentation, TonePresentation } from './chatterPresentation'
import {
  SORT_LABELS, knownCount, nextSort, readingWord, sortRows,
} from './chatterSort'
import type { ChatterSort, SortKey } from './chatterSort'
import { Disclosure } from './Disclosure'
import { Filters } from './Filters'
import { AgeLine, Empty } from './PageState'
import { SortPicker } from './SortPicker'

/** Two readings of one list.
 *
 *  `research` is the workspace: candidates on the left, the one being
 *  examined in the middle, its evidence on the right. `table` is the
 *  seven-column comparison, which answers a question the workspace cannot --
 *  how do all fifty of these compare on tone, or on breadth, at once.
 *
 *  Same rows, same filters, same ordering, same cached response. Not two data
 *  models and not two applications. */
export type ChatterMode = 'research' | 'table'

/** A stable empty list for the states that have no rows, so the ordering
 *  memo below does not re-run on every render of a waiting shell. */
const NO_ROWS: Row[] = []

export function Chatter({ board, vocabulary, selection, sort = null,
                         received, stalled = false, onRetry, standIn, onOpen,
                         onSelect, onSort, mode = 'table', onMode,
                         selected = null, onOpenReplace, onClear, hrefFor,
                         span = '1D', onSpan, onSearch, visible = true, filter,
                         onFilter, opened = false, onOpened, watching,
                         onToggleWatch, watchPending = false, watchError }: {
  /** This selection's answer: a board, a waiting shell, or null while
   *  nothing for it has answered yet. Only a built board has rows to list;
   *  anything else is `standIn`, under the same heading and controls. */
  board: BoardPayload | null
  /** Where the filters read the server's vocabulary -- which feeds it offers
   *  -- while this selection has not answered. Any board will do: the
   *  vocabulary is the server's, not the selection's. */
  vocabulary?: BoardPayload
  selection: Selection
  /** Null is Radar order: the response exactly as it arrived. Held by the hub
   *  rather than here, so leaving for Research and coming back does not throw
   *  the reader's ordering away. */
  sort?: ChatterSort | null
  /** When the page received the board, so its age keeps moving. Defaults to
   *  when this mounted, for the suites that render the page on its own. */
  received?: number
  /** Nothing is fetching a replacement for an expired board. */
  stalled?: boolean
  onRetry?: () => void
  /** What stands where the list would, for anything but a built board. */
  standIn?: ReactNode
  onOpen: (ticker: string) => void
  onSelect?: (next: Selection) => void
  onSort?: (next: ChatterSort | null) => void
  /** Defaults to the table, which is what this component has always been. The
   *  hub opens on `research`; a caller that does not supply the workspace's
   *  navigation cannot render the workspace, and gets the list it asked for. */
  mode?: ChatterMode
  onMode?: (next: ChatterMode) => void
  selected?: string | null
  onOpenReplace?: (ticker: string) => void
  onClear?: () => void
  hrefFor?: (ticker: string) => string
  span?: PanelSpan
  onSpan?: (next: PanelSpan) => void
  onSearch?: () => void
  visible?: boolean
  /** Held by the hub when there is one, so opening a company and coming back
   *  does not clear what the reader typed. Uncontrolled otherwise. */
  filter?: string
  onFilter?: (next: string) => void
  /** The hub's record of whether this visit has already opened a company.
   *  See ChatterWorkspace: it cannot live in the workspace, which unmounts
   *  whenever the reader switches to the table and back. */
  opened?: boolean
  onOpened?: () => void
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  watchPending?: boolean
  watchError?: unknown
}) {
  const [ownFilter, setOwnFilter] = useState('')
  const text = filter ?? ownFilter
  const setText = onFilter ?? setOwnFilter
  const needle = text.trim().toLowerCase()
  const [mounted] = useState(() => Date.now())
  // Only a built board has rows to list. A waiting shell, a failing key, or
  // null -- nothing for this selection has answered yet -- is `standIn`,
  // drawn under the same heading and the same controls in either reading.
  const ready = board !== null && isReady(board) ? board : null
  const offered = board ?? vocabulary
  // Filter first, then order what survived. Both are views over the response:
  // neither fetches, and neither can add a company the server did not send.
  // Sorting outlives a refresh because it is applied to whatever `board.rows`
  // currently is, rather than stored as a reordered copy that would go stale.
  //
  // ONE list, for both modes. The workspace's rail and the comparison table
  // are the same rows in the same order -- switching between them is a change
  // of presentation, never of population.
  const source = ready ? ready.rows : NO_ROWS
  const rows = useMemo(() => {
    const matching = needle
      ? source.filter((row) => matches(row, needle))
      : source
    return sortRows(matching, sort)
  }, [source, needle, sort])

  const excluded = Object.values(ready?.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  // Every capability the workspace needs, or it does not render one. The
  // list includes `onSort` and `onSelect` deliberately: without them the rail
  // would draw a Sort by control that does nothing and drop every
  // server-side filter, which is precisely what the brief says not to do for
  // visual space. A caller that cannot supply them gets the table, which is
  // honest about what it is. And it needs SOME board to read the server's
  // vocabulary from: with neither an answer nor a vocabulary there is no
  // feed list to draw.
  const workspace = mode === 'research' && offered !== undefined && hrefFor
    && onOpenReplace && onClear && onSpan && onSearch && onSort && onSelect
    && onOpened

  return (
    <>
      <div className={`rh-heading rh-chatterhead${workspace ? ' tight' : ''}`}>
        <div>
          {board ? (
            <p className="rh-datestamp">
              {contextLine(board)}
              {ready ? (
                <>
                  {' · '}
                  <AgeLine board={ready} received={received ?? mounted}
                           stalled={stalled} onRetry={onRetry} />
                </>
              ) : null}
            </p>
          ) : null}
          <h1>Human Chatter</h1>
          <p>Discussion ranked by how unusual it is against its baseline. Price movement is shown separately.</p>
        </div>
        {onMode ? <ModeToggle mode={mode} onMode={onMode} /> : null}
      </div>

      {ready !== null ? <SelectionState rows={ready.rows} /> : null}

      {workspace ? (
        // In every state, and at the same place in the tree: the rail keeps
        // its filter, its ordering and the server-side feed controls while a
        // board is being built, and `standIn` stands where the candidates
        // would. Controls that remounted when the answer landed would drop
        // their focus and fold their disclosure.
        <ChatterWorkspace
          board={offered}
          ready={ready}
          standIn={standIn}
          selection={selection}
          rows={rows}
          selected={selected}
          onSelect={onOpen}
          onSelectReplace={onOpenReplace}
          onClear={onClear}
          hrefFor={hrefFor}
          span={span}
          onSpan={onSpan}
          visible={visible}
          filter={text}
          onFilter={setText}
          sort={sort}
          onSort={onSort}
          onSelection={onSelect}
          opened={opened}
          onOpened={onOpened}
          watching={watching}
          onToggleWatch={onToggleWatch}
          watchPending={watchPending}
          watchError={watchError}
          onSearch={onSearch}
        />
      ) : (
        <>
          {/* In every state, and at the same place in the tree: a reader
              waiting on one question may ask another, and controls that
              remounted when an answer landed would drop their focus and
              fold their disclosure. */}
          {onSelect && offered ? (
            <Filters board={offered} selection={selection} onChange={onSelect} />
          ) : null}

          {ready === null ? standIn
            : ready.rows.length === 0 ? <EmptyBoard excluded={excluded} />
            : (
              <Panel board={ready} rows={rows} filter={text}
                     onFilter={setText} onOpen={onOpen}
                     sort={sort} onSort={onSort} />
            )}
        </>
      )}
    </>
  )
}

function SelectionState({ rows }: { rows: Row[] }) {
  const measured = rows.filter((row) => typeof row.mention_z === 'number'
    && Number.isFinite(row.mention_z))
  if (measured.length === 0 && rows.length > 0) {
    return <p className="small muted">Not enough history to measure unusual activity.</p>
  }
  if (measured.length > 0 && measured.every((row) => row.mention_z! <= 0)) {
    return <p className="small muted">
      {measured.length === rows.length
        ? 'No elevated discussion in this selection.'
        : 'No elevated discussion among companies with a measurable baseline. Some companies have insufficient history.'}
    </p>
  }
  return null
}

/** Which reading of the list is on screen.
 *
 *  A pressed pair rather than a select: there are two of them, they are
 *  mutually exclusive, and the one in effect should be readable without
 *  opening anything. `aria-pressed` carries the state, and the label is the
 *  destination rather than the current place -- pressing "Table" gives the
 *  table. */
function ModeToggle({ mode, onMode }: {
  mode: ChatterMode
  onMode: (next: ChatterMode) => void
}) {
  return (
    <div className="rh-modetoggle" role="group" aria-label="List view">
      <button type="button" aria-pressed={mode === 'research'}
              onClick={() => onMode('research')}>
        Research
      </button>
      <button type="button" aria-pressed={mode === 'table'}
              onClick={() => onMode('table')}>
        Table
      </button>
    </div>
  )
}

function EmptyBoard({ excluded }: { excluded: number }) {
  // A quiet market and a stopped ingest are different situations, and
  // `excluded` is what tells them apart.
  if (excluded > 0) {
    return (
      <Empty title="Nothing cleared the floor in this window.">
        {excluded} {excluded === 1 ? 'company was' : 'companies were'} left out
        by the eligibility floor and the breadth filter. That is a quiet
        window, not a missing one.
      </Empty>
    )
  }
  return (
    <Empty title="No company cleared this selection.">
      Nothing was recorded as excluded by the eligibility floor or the breadth
      filter — a segment filter does not report itself that way. Widen the
      window or the feeds, or check Activity for whether the fetch ran.
    </Empty>
  )
}

function Panel({ board, rows, filter, onFilter, onOpen, sort, onSort }: {
  board: ReadyBoard
  rows: Row[]
  filter: string
  onFilter: (next: string) => void
  onOpen: (ticker: string) => void
  sort: ChatterSort | null
  onSort?: (next: ChatterSort | null) => void
}) {
  const total = board.rows.length
  const shown = rows.length
  // Somewhere for focus to land when the control holding it unmounts -- see
  // SortNote's reset.
  const region = useRef<HTMLDivElement>(null)
  return (
    <section className="rh-panel rh-chatterpanel">
      <div className="rh-panelhead">
        <div className="rh-panelheadtext">
          <h2>Ranked companies</h2>
          <p className="small muted">
            Unusual attention, with voices and sources in view.
          </p>
        </div>
        <div className="rh-panelheadtools">
          <label className="rh-field rh-tablefilter">
            <span>Filter companies</span>
            <input
              type="search"
              value={filter}
              placeholder="Ticker or name"
              onChange={(event) => onFilter(event.target.value)}
            />
          </label>
          {onSort ? <SortPicker sort={sort} onSort={onSort} /> : null}
          <p className="small muted rh-panelcount">
            {shown === total
              ? `${total} ${total === 1 ? 'company' : 'companies'}`
              : `${shown} of ${total} shown`}
          </p>
        </div>
      </div>

      {onSort && sort
        ? <SortNote rows={rows} sort={sort} onSort={onSort}
                    onReset={() => region.current?.focus()} />
        : null}

      {shown === 0 ? (
        <div className="rh-panelempty">
          <Empty title="No company here matches that.">
            The filter runs over the {total}{' '}
            {total === 1 ? 'company' : 'companies'} already listed. Clearing it
            brings them back.
          </Empty>
        </div>
      ) : (
        <Table rows={rows} onOpen={onOpen} sort={sort} onSort={onSort}
               region={region} />
      )}

      {/* Announced, not merely rendered. `aria-sort` tells a reader who lands
          on a header what the order IS; it does not tell anyone that the list
          just moved under them -- and on the stacked layout there is no header
          to land on at all. */}
      <p className="rh-visually-hidden" role="status">
        {onSort && sort ? sortSentence(rows, sort) : ''}
      </p>

      <Foot board={board} shown={shown} />
    </section>
  )
}

/** The proportions the design contract sets at 1440, carried by a colgroup so
 *  the widest feed name can never decide them again. Percentages of the
 *  table's own content width; they add to 100. */
// Three points off the contract's 26/13/11/15/19/12/4, which it allows to
// avoid collisions. Sources needs them: `Reddit · 4chan /biz/ · Bluesky` wraps
// at 15%. They come from Voices and Tone, and deliberately NOT from Attention
// -- the contract names that one specifically: "do not compress Attention to
// make room for source prose". An earlier revision took a point from it
// anyway, which is exactly the thing it says not to do.
const COLUMNS = ['26%', '13%', '10%', '18%', '17%', '12%', '4%']

function Table({ rows, onOpen, sort, onSort, region }: {
  rows: Row[]
  onOpen: (ticker: string) => void
  sort: ChatterSort | null
  onSort?: (next: ChatterSort | null) => void
  region?: React.RefObject<HTMLDivElement | null>
}) {
  return (
    // Labelled and scrollable: the table may scroll inside this region, but
    // the document never scrolls sideways.
    <div className="rh-tablewrap" role="region" aria-label="Ranked companies"
         tabIndex={0} ref={region}>
      <table role="table" className="rh-table rh-chatter">
        <colgroup>
          {COLUMNS.map((width, index) => (
            <col key={index} style={{ width }} />
          ))}
        </colgroup>
        <thead>
          <tr role="row">
            <SortHead sortKey="company" label="Company" sort={sort} onSort={onSort} />
            <SortHead sortKey="attention" label="Attention" sort={sort} onSort={onSort} />
            <SortHead sortKey="voices" label="Voices" sort={sort} onSort={onSort} />
            <SortHead sortKey="sources" label="Sources" sort={sort} onSort={onSort} />
            <SortHead sortKey="tone" label="Tone" sort={sort} onSort={onSort} />
            <PriceHead sort={sort} onSort={onSort} />
            {/* The chevron's column. Named for a screen reader rather than
                left as an empty header, which reads as a missing one. */}
            <th scope="col"><span className="rh-visually-hidden">Open research</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TickerRow key={row.ticker} row={row} onOpen={onOpen} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A column header that is also its sort control.
 *
 *  `aria-sort` lives on the header cell, where assistive technology looks for
 *  it, and the button's own accessible name is just the column name -- no
 *  aria-label overriding the visible text, which is how the row disclosures
 *  first broke WCAG 2.5.3. A native button gives Enter and Space for free.
 *
 *  When no sort control is supplied the header is plain text, so a Chatter
 *  rendered without `onSort` is exactly what it was before. */
function SortHead({ sortKey, label, className, sort, onSort }: {
  sortKey: SortKey
  label: string
  className?: string
  sort: ChatterSort | null
  onSort?: (next: ChatterSort | null) => void
}) {
  const active = sort && sort.key === sortKey ? sort : null
  return (
    <th scope="col" className={className} aria-sort={ariaSort(active)}>
      {onSort
        ? <SortControl sortKey={sortKey} label={label} sort={sort} onSort={onSort} />
        : label}
    </th>
  )
}

/** Price and today's move are two questions and two controls.
 *
 *  One combined "Price / today" sort would be ambiguous -- a reader clicking it
 *  cannot know whether they asked for the dearest company or the one that rose
 *  most. Because both controls live under one header, the header takes an
 *  explicit name saying WHICH of them `aria-sort` is describing. */
function PriceHead({ sort, onSort }: {
  sort: ChatterSort | null
  onSort?: (next: ChatterSort | null) => void
}) {
  const active = sort && (sort.key === 'price' || sort.key === 'move')
    ? sort : null
  return (
    <th
      scope="col"
      className="right rh-pricehead"
      aria-sort={ariaSort(active)}
      aria-label={active
        ? (active.key === 'price' ? 'Price' : 'Today')
        : 'Price and today'}
    >
      {onSort ? (
        <>
          <SortControl sortKey="price" label="Price" sort={sort} onSort={onSort} />
          <span aria-hidden="true"> · </span>
          <SortControl sortKey="move" label="Today" sort={sort} onSort={onSort} />
        </>
      ) : 'Price · today'}
    </th>
  )
}

function ariaSort(active: ChatterSort | null) {
  if (!active) return 'none' as const
  return active.dir === 'asc' ? ('ascending' as const) : ('descending' as const)
}

function SortControl({ sortKey, label, sort, onSort }: {
  sortKey: SortKey
  label: string
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
}) {
  const active = sort && sort.key === sortKey ? sort : null
  return (
    <button
      type="button"
      className={`rh-sortbutton${active ? ' active' : ''}`}
      onClick={() => onSort(nextSort(sort, sortKey))}
      data-testid={`rh-sort-${sortKey}`}
    >
      {label}
      {/* The arrow is decoration; `aria-sort` on the header carries the state,
          and colour is not the only thing marking the active column -- the
          arrow and the weight do too. */}
      {active ? (
        <span className="rh-sortarrow" aria-hidden="true">
          {active.dir === 'asc' ? '↑' : '↓'}
        </span>
      ) : null}
    </button>
  )
}

/** What the sort did, and — more importantly — what it did not do.
 *
 *  "Sorted by tone" reads like "the most bullish companies in the market". It
 *  is not that: it is the loaded candidates reordered. The eligibility floor,
 *  the breadth filter and Radar's own ranking all ran before this, and none of
 *  them moved. */
function SortNote({ rows, sort, onSort, onReset }: {
  rows: Row[]
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
  onReset?: () => void
}) {
  if (!sort) return null
  const missing = rows.length - knownCount(rows, sort.key)
  return (
    <p className="small muted rh-sortnote">
      <span>
        Sorted by <strong>{SORT_LABELS[sort.key]}</strong>,{' '}
        {sort.dir === 'asc' ? 'lowest first' : 'highest first'}.
      </span>
      {rows.length === 0 ? (
        // "Sorts these 0 candidates" is not a sentence anyone needs above
        // "No company here matches that."
        <span>Nothing is left to sort under the current filter.</span>
      ) : (
        <span>
          Sorts these {rows.length}{' '}
          {rows.length === 1 ? 'candidate' : 'candidates'}, not the whole
          market — Radar’s ranking and eligibility are unchanged.
        </span>
      )}
      {missing > 0 ? (
        <span>
          {missing} with no {readingWord(sort.key)} reading{' '}
          {missing === 1 ? 'stays' : 'stay'} at the end.
        </span>
      ) : null}
      {/* Focus is handed on deliberately: pressing this unmounts it, and
          React leaves focus on the body when that happens -- so a keyboard
          reader's next Tab restarted from the top of the document, past the
          navigation and every filter. */}
      <button type="button" className="rh-textbutton rh-sortreset"
              onClick={() => { onSort(null); onReset?.() }}>
        Unusual activity
      </button>
    </p>
  )
}

/** The same reading as the note, in one sentence, for the status region.
 *  A screen reader gets told the list moved and what it moved by -- which
 *  `aria-sort` alone cannot say, and cannot say at all on the stacked layout
 *  where the header row does not exist. */
function sortSentence(rows: Row[], sort: ChatterSort): string {
  const missing = rows.length - knownCount(rows, sort.key)
  const order = sort.dir === 'asc' ? 'lowest first' : 'highest first'
  const tail = missing > 0
    ? ` ${missing} with no ${readingWord(sort.key)} reading at the end.`
    : ''
  return `Sorted by ${SORT_LABELS[sort.key]}, ${order}. `
    + `${rows.length} ${rows.length === 1 ? 'candidate' : 'candidates'}.${tail}`
}

function TickerRow({ row, onOpen }: { row: Row; onOpen: (t: string) => void }) {
  const tone = tonePresentation(row.tone)
  const sources = sourcePresentation(row.activity_sources)
  return (
    <tr role="row">
      <th role="rowheader" scope="row" className="rh-company rh-col-company">
        <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
          <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
          <span className="rh-openname">
            <span className="rh-ticker" data-testid="rh-row-ticker">{row.ticker}</span>
            {/* Clamped to one line on the desk layout, never truncated in the
                accessible name: the text node is whole and `title` repeats
                it. A legal name is routinely longer than the column, and
                shortening the NAME rather than its display would be a lie
                about the company. */}
            <span className="rh-name" title={row.name ?? undefined}>
              {row.name ?? 'Name unknown'}
            </span>
          </span>
        </button>
        <Marks marks={row.marks} />
      </th>
      <Cell label="Attention" className="rh-col-attention">
        <Attention row={row} />
      </Cell>
      <Cell label="Voices" className="rh-col-voices">
        <strong className="num">{row.authors}</strong>
        {/* The backend's own meaning: distinct authors seen in the window, and
            the posts they wrote. Never "investors" and never "people" -- one
            person posting from three accounts is three authors here. */}
        <span className="rh-sub">
          {row.mentions} {row.mentions === 1 ? 'post' : 'posts'}
        </span>
      </Cell>
      <Cell label="Sources" className="rh-col-sources" testId="rh-row-sources">
        <Sources ticker={row.ticker} sources={sources} />
      </Cell>
      <Cell label="Tone" className="rh-col-tone">
        <ToneCell ticker={row.ticker} tone={tone} />
      </Cell>
      <Cell label="Price · today" className="right rh-col-price">
        <Price row={row} />
      </Cell>
      <Cell label="" className="rh-col-open">
        <button type="button" className="rh-chevron"
                onClick={() => onOpen(row.ticker)}>
          <span className="rh-visually-hidden">Open {row.ticker} research</span>
          <Chevron />
        </button>
      </Cell>
    </tr>
  )
}

function Chevron() {
  return (
    <svg className="rh-icon" viewBox="0 0 24 24" aria-hidden="true"
         focusable="false">
      <path d="m9 5 7 7-7 7" />
    </svg>
  )
}

/** How far above its own normal, when there is a normal worth dividing by.
 *  `ratio` null is phrasing.py's guard, decided once on the server -- the
 *  client never rebuilds it from mentions and expected. */
function Attention({ row }: { row: Row }) {
  if (row.ratio === null) {
    return (
      <>
        {/* The dash is decoration; "New here" beneath it is the reading, and
            it is what a screen reader gets. */}
        <strong aria-hidden="true">—</strong>
        <span className="rh-sub">
          New here{row.baseline_days !== null
            ? ` · ${row.baseline_days}-day baseline` : ''}
        </span>
      </>
    )
  }
  return (
    <>
      <strong className="num">{row.ratio.toFixed(1)}×</strong>
      <span className="rh-sub">its normal rate</span>
    </>
  )
}

/** The platforms that counted something, and every concrete feed behind them.
 *
 *  The compact form is a platform COUNT, not a list of labels: two subreddits
 *  are one platform, and printing `Reddit, Reddit` claimed a breadth that is
 *  not there while filling the column. The identifiers are not thrown away --
 *  they are one keystroke behind the summary. */
function Sources({ ticker, sources }: {
  ticker: string; sources: SourcePresentation
}) {
  if (sources.kind !== 'platforms') {
    return (
      <>
        <strong className="rh-tonequiet">{sources.label}</strong>
        {sources.summary ? <span className="rh-sub">{sources.summary}</span> : null}
      </>
    )
  }
  return (
    <>
      <strong className="num">{sources.label}</strong>
      {/* The summary IS the control. A separate "which feeds" link under it
          cost every row a line, which is how the row got tall in the first
          place -- and this correction exists because the rows were tall. */}
      <Disclosure label={`Which feeds counted for ${ticker}`}
              trigger={sources.summary ?? 'Which feeds'}>
        <p className="rh-detailnote">
          {sources.feedCount} {sources.feedCount === 1 ? 'feed' : 'feeds'}{' '}
          counted at least one post in this window, across{' '}
          {sources.platforms.length}{' '}
          {sources.platforms.length === 1 ? 'platform' : 'platforms'}. Feeds on
          the same platform share a site and an audience, so they do not
          corroborate one another.
        </p>
        <ul className="rh-detaillist">
          {sources.platforms.map((platform) => (
            <li key={platform.root}>
              <strong>{platform.label}</strong>
              <span>{platform.feeds.join(', ')}</span>
            </li>
          ))}
        </ul>
      </Disclosure>
    </>
  )
}

/** Tone as a share of the directional sample, with the sample size beside it.
 *
 *  The percentage and the bar have ONE denominator: the bullish and bearish
 *  signals. The residual is stated rather than folded in, because it holds
 *  balanced reads and unclassified ones together and neither is a vote for
 *  the middle. tonePresentation owns every rule; this only draws it. */
function ToneCell({ ticker, tone }: { ticker: string; tone: TonePresentation }) {
  const proportional = tone.bull !== null && tone.bear !== null
  return (
    <>
      <strong className={tone.kind === 'directional' ? 'num' : 'rh-tonequiet'}>
        {tone.label}
      </strong>
      {/* Drawn for every sampled row, empty track included, so the column does
          not jump between rows that have a reading and rows that do not.
          Colour never carries the meaning alone: the percentage above it is
          the reading, and this is its proportion. */}
      {tone.kind !== 'unavailable' ? (
        <span className="rh-tonebar" aria-hidden="true">
          {proportional && tone.bull! > 0
            ? <span className="bull" style={{ flexGrow: tone.bull! }} /> : null}
          {proportional && tone.bear! > 0
            ? <span className="bear" style={{ flexGrow: tone.bear! }} /> : null}
          {!proportional ? <span className="flat" style={{ flexGrow: 1 }} /> : null}
        </span>
      ) : null}
      {/* Same economy as the source cell: the sample line IS the control, so
          the exact counts cost the row no height at all.
          ------------------------------------------------------------------
          And no control at all when there is no sample line to hang it on. A
          row with nothing to count has nothing to break down, and giving it
          its own "how this is counted" link cost a line on every row of a
          board where no tone has been read yet -- which is exactly the board
          the local development copy produces. The footer's "How to read
          this" still explains the column. */}
      {tone.sample ? (
        <Disclosure label={`How ${ticker}’s tone is counted`} trigger={tone.sample}>
          <p className="rh-detailnote">{tone.detail}</p>
        </Disclosure>
      ) : null}
    </>
  )
}

function Price({ row }: { row: Row }) {
  const { quote } = row
  if (quote.quality === 'unavailable' || row.price === null) {
    return (
      <>
        <strong aria-hidden="true">—</strong>
        <span className="rh-sub">Price unavailable</span>
      </>
    )
  }
  const move = row.price_move
  return (
    <>
      <strong className="num">
        {formatPrice(row.price, quote.currency)}
      </strong>
      <span className={`rh-sub num ${moveClass(move)}`}>
        {move === null
          ? 'Move unknown'
          : `${move > 0 ? '+' : ''}${(move * 100).toFixed(1)}%`}
        {move !== null && tapeNote(row.price_status)
          ? <span className="muted"> · {tapeNote(row.price_status)}</span>
          : null}
      </span>
    </>
  )
}

/** What to say about a move the exchange is not currently confirming.
 *
 *  The move itself is measured either way -- two snapshots in the window and
 *  the difference between them. What changes with the session is whether it is
 *  still moving, and a reader looking at `-2.3%` at two in the morning deserves
 *  to be told which. `Move unknown` is reserved for the one case that really is
 *  unknown: fewer than two snapshots, decided in `quotes.moves_for`. */
function tapeNote(status: Row['price_status']): string | null {
  if (status === 'closed') return 'at close'
  // The exchange is open and this tape is not printing. The row already
  // carries the No print badge; this says what the number is in spite of it.
  //
  // Not `no print since`: that is a sentence with its object missing, and
  // the row printed `0.0% · no print since` and stopped. The row has no date
  // to finish it with -- the panel's quote line is where the timestamp is.
  if (status === 'stale') return 'tape not printing'
  return null
}

function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

function formatPrice(value: number, currency: QuoteCurrency | null): string {
  return usdText(value, currency)
}

/** What the numbers above mean, once, under the table.
 *
 *  Once is the point. The rejected version repeated its warnings in every
 *  cell, which is how a caveat stops being read. */
function Foot({ board, shown }: { board: BoardPayload; shown: number }) {
  return (
    <div className="rh-tablefoot">
      <p className="small muted rh-footline">
        <span>
          <strong>{shown}</strong>{' '}
          {shown === 1 ? 'company' : 'companies'} in view
        </span>
        <span>prices from {board.market_venue}</span>
        <span>
          attention compares equivalent hourly windows against each company’s
          own baseline
        </span>
      </p>
      <Disclosure label="How to read this table" trigger="How to read this">
        <dl className="rh-glossary">
          <dt>Attention</dt>
          <dd>
            How many times its own normal rate the discussion is running at,
            over equivalent windows. A company with too little history to have
            a normal shows an em dash and says so, rather than a ratio.
          </dd>
          <dt>Voices</dt>
          <dd>
            Distinct authors seen in the window, and the posts they wrote. One
            person posting from three accounts counts as three authors; this is
            not a count of investors.
          </dd>
          <dt>Sources</dt>
          <dd>
            Platforms with at least one counted post in this window. Feeds on
            the same platform — several subreddits, say — are one platform and
            do not corroborate each other. This display count is not what the
            breadth filter uses: that filter follows the scoring breadth, which
            counts every feed that was read, including the quiet ones.
          </dd>
          <dt>Tone</dt>
          <dd>
            Share of directional signals that are bullish. Signals may come
            from model judgments or keyword rules. The rest of the sample is
            unread or non-directional and is excluded from the percentage — it
            is not agreement that the outlook is neutral.
          </dd>
          <dt>Price · today</dt>
          <dd>
            The latest price this board has for the selected market, and the
            move across the window. An unavailable quote stays unavailable
            rather than rendering as a zero.
          </dd>
        </dl>
      </Disclosure>
    </div>
  )
}

const MARK_TEXT: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

/** Rendered, never behind a hover. A qualification the reader has to discover
 *  is a qualification that did not happen -- so this is the one thing on the
 *  row allowed to make it taller. */
function Marks({ marks }: { marks: Row['marks'] }) {
  if (!marks.length) return null
  return (
    <p className="rh-marks">
      {marks.map((mark) => (
        <span key={mark} className="rh-badge amber">{MARK_TEXT[mark] ?? mark}</span>
      ))}
    </p>
  )
}

function matches(row: Row, needle: string): boolean {
  return row.ticker.toLowerCase().includes(needle)
    || (row.name ?? '').toLowerCase().includes(needle)
}

/** Both halves from the payload's own echo -- a waiting shell's included,
 *  which is the selection being built. Taking the venue from the board and
 *  the window from the request meant that, while a new window loaded, the
 *  previous window's rows sat under a heading naming the new one. The age
 *  follows it (AgeLine), and only for a board that exists. */
function contextLine(board: BoardPayload): string {
  const hours = board.window_hours
  return `${board.market_venue} · last ${hours} ${hours === 1 ? 'hour' : 'hours'}`
}

function Cell({ label, className, testId, children }: {
  label: string
  className?: string
  testId?: string
  children: React.ReactNode
}) {
  // An explicit role, because `display: block` in the stacked mobile layout
  // drops the implicit one; and a real element for the label rather than
  // generated content, because ::before is not part of a cell's accessible
  // name and cannot carry the header association a stacked table loses.
  //
  // Not aria-hidden. On the desk layout the column header supplies the
  // association and this repeats it, which costs a word; below 860px the
  // header row is gone and this is the only thing naming the figure.
  return (
    <td role="cell" className={className} data-testid={testId}>
      {/* No `rh-visually-hidden` here any more: the class hid it from the eye
          while leaving it in the accessibility tree, so the desk layout
          announced every column name twice per cell. hub.css toggles its
          `display` instead -- gone on the desk layout, visible and announced
          in the stacked one, where the header row no longer exists. */}
      {label ? <span className="rh-cell-label">{label}</span> : null}
      {children}
    </td>
  )
}

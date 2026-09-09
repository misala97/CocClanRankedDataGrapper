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
import { useId, useMemo, useRef, useState } from 'react'

import type { BoardPayload, Row, Selection } from '../types'
import { sourcePresentation, tonePresentation } from './chatterPresentation'
import type { SourcePresentation, TonePresentation } from './chatterPresentation'
import {
  SORT_LABELS, knownCount, nextSort, priceCurrencies, readingWord, sortRows,
} from './chatterSort'
import type { ChatterSort, SortKey } from './chatterSort'
import { Filters } from './Filters'
import { Empty } from './PageState'

export function Chatter({ board, selection, sort = null, onOpen, onSelect,
                         onSort }: {
  board: BoardPayload
  selection: Selection
  /** Null is Radar order: the response exactly as it arrived. Held by the hub
   *  rather than here, so leaving for Research and coming back does not throw
   *  the reader's ordering away. */
  sort?: ChatterSort | null
  onOpen: (ticker: string) => void
  onSelect?: (next: Selection) => void
  onSort?: (next: ChatterSort | null) => void
}) {
  const [filter, setFilter] = useState('')
  const needle = filter.trim().toLowerCase()
  // Filter first, then order what survived. Both are views over the response:
  // neither fetches, and neither can add a company the server did not send.
  // Sorting outlives a refresh because it is applied to whatever `board.rows`
  // currently is, rather than stored as a reordered copy that would go stale.
  const rows = useMemo(() => {
    const matching = needle
      ? board.rows.filter((row) => matches(row, needle))
      : board.rows
    return sortRows(matching, sort)
  }, [board.rows, needle, sort])

  const excluded = Object.values(board.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  return (
    <>
      <div className="rh-heading">
        <div>
          <p className="rh-datestamp">{contextLine(board)}</p>
          <h1>Human chatter</h1>
          <p>Find unusual discussion, then inspect the evidence.</p>
        </div>
      </div>

      {onSelect ? (
        <Filters board={board} selection={selection} onChange={onSelect} />
      ) : null}

      {board.rows.length === 0
        ? <EmptyBoard excluded={excluded} />
        : (
          <Panel board={board} rows={rows} filter={filter}
                 onFilter={setFilter} onOpen={onOpen}
                 sort={sort} onSort={onSort} />
        )}
    </>
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
  board: BoardPayload
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

const SORT_KEYS: SortKey[] = ['company', 'attention', 'voices', 'sources',
                              'tone', 'price', 'move']

/** The stacked layout's sort control.
 *
 *  Below 860px the header row is `display: none`, which takes it out of the
 *  accessibility tree along with the eye's -- so without this, sorting would
 *  exist only in controls nobody on a phone can reach. Rendered always and
 *  hidden by the same CSS breakpoint, rather than by JavaScript watching the
 *  viewport: one switch, one source of truth. */
function SortPicker({ sort, onSort }: {
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
}) {
  return (
    <div className="rh-sortpicker">
      <label className="rh-field">
        <span>Sort by</span>
        <select
          value={sort ? sort.key : 'radar'}
          onChange={(event) => {
            const value = event.target.value
            onSort(value === 'radar'
              ? null
              : nextSort(null, value as SortKey))
          }}
        >
          <option value="radar">Radar order</option>
          {SORT_KEYS.map((key) => (
            <option key={key} value={key}>{SORT_LABELS[key]}</option>
          ))}
        </select>
      </label>
      {/* The visible text is the CURRENT order; the accessible name is what
          pressing it does, because "Lowest first" as a name promises the
          opposite of what happens. Disabled with no sort, and then it claims
          no order at all rather than asserting one that is not in effect. */}
      <button
        type="button"
        className="rh-button rh-sortdir"
        disabled={!sort}
        aria-label={sort
          ? `Sort ${sort.dir === 'asc' ? 'highest' : 'lowest'} first`
          : 'Sort direction'}
        onClick={() => sort && onSort({
          key: sort.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' })}
      >
        {!sort ? 'Direction'
          : sort.dir === 'asc' ? 'Lowest first' : 'Highest first'}
      </button>
    </div>
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
  const currencies = sort.key === 'price' ? priceCurrencies(rows) : []
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
      {currencies.length > 1 ? (
        <span>
          Prices are grouped by currency ({currencies.join(', ')}) rather than
          converted, so reversing moves the groups as well as the rows.
        </span>
      ) : null}
      {/* Focus is handed on deliberately: pressing this unmounts it, and
          React leaves focus on the body when that happens -- so a keyboard
          reader's next Tab restarted from the top of the document, past the
          navigation and every filter. */}
      <button type="button" className="rh-textbutton rh-sortreset"
              onClick={() => { onSort(null); onReset?.() }}>
        Radar order
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
      <Detail label={`Which feeds counted for ${ticker}`}
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
      </Detail>
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
        <Detail label={`How ${ticker}’s tone is counted`} trigger={tone.sample}>
          <p className="rh-detailnote">{tone.detail}</p>
        </Detail>
      ) : null}
    </>
  )
}

/** A disclosure that opens in place.
 *
 *  In place rather than floating: the table scrolls inside its own region, and
 *  anything absolutely positioned in a cell would be clipped by that scroll
 *  box. A row that grows while it is open is at least honest about what it is
 *  showing.
 *
 *  Escape closes it and returns focus to the control that opened it. A reader
 *  who opened it from the keyboard otherwise has nowhere obvious to go back
 *  to. Rendered always and hidden with the attribute rather than unmounted,
 *  so `aria-controls` points at something that exists. */
function Detail({ label, trigger, children }: {
  label: string; trigger: string; children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const button = useRef<HTMLButtonElement>(null)
  return (
    <span
      className="rh-detail"
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !open) return
        // Stopped here so Escape closes THIS and does not travel on to
        // whatever else on the page listens for it.
        event.stopPropagation()
        setOpen(false)
        button.current?.focus()
      }}
    >
      <button
        type="button"
        ref={button}
        className="rh-detailtoggle"
        aria-expanded={open}
        aria-controls={id}
        // The visible text LEADS the accessible name, then the label says what
        // opening it does. Replacing the visible text outright failed WCAG
        // 2.5.3 Label in Name: the button read `26 directional / 71 total` and
        // answered to "How KSTR's tone is counted", so a voice-control reader
        // saying "click 26 directional" had no handle on it at all.
        aria-label={`${trigger} — ${label}`}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="rh-sub">{trigger}</span>
      </button>
      <span className="rh-detailbody" id={id} role="group" aria-label={label}
            hidden={!open}>
        {children}
      </span>
    </span>
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
        {move === null ? 'Move unknown' : `${move > 0 ? '+' : ''}${(move * 100).toFixed(1)}%`}
      </span>
    </>
  )
}

function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

function formatPrice(value: number, currency: string | null): string {
  const symbol = currency === 'EUR' ? '€' : currency === 'USD' ? '$' : ''
  const text = value.toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return symbol ? `${symbol}${text}` : `${text} ${currency ?? ''}`.trim()
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
      <Detail label="How to read this table" trigger="How to read this">
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
      </Detail>
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

/** Both halves from the payload's own echo. Taking the venue from the board
 *  and the window from the request meant that, while a new window loaded, the
 *  previous window's rows sat under a heading naming the new one. */
function contextLine(board: BoardPayload): string {
  const hours = board.window_hours
  return `${board.market_venue} · last ${hours} ${hours === 1 ? 'hour' : 'hours'}`
    + ` · built ${stamp(board.generated_at)}`
}

/** The board's own build time, in the timezone the reader lives in. A board
 *  with no visible age is one nobody can tell is stale. */
function stamp(iso: string): string {
  try {
    return `${new Date(iso).toLocaleTimeString('en-GB',
      { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })} Berlin`
  } catch {
    return 'time unknown'
  }
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

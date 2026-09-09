// Human chatter: what people are actually discussing, in the server's order.
//
// The list answers one question -- which of these is worth my time -- and
// hands the second, is this real, to Research. That split is why the row shows
// its evidence rather than a score: how far above its own normal, how many
// independent voices, how many venues, and every qualification the server
// attached. A single number would rank the same companies while telling the
// reader nothing about whether to believe it.
//
// Nothing here is a recommendation. The rank is unusual chatter with price
// context, and the copy says so in the words the spec insists on.
import { useMemo, useState } from 'react'

import { sourceLabel } from '../format'
import type { BoardPayload, Row, Selection } from '../types'
import { Filters } from './Filters'
import { Empty } from './PageState'

export function Chatter({ board, selection, onOpen, onSelect }: {
  board: BoardPayload
  selection: Selection
  onOpen: (ticker: string) => void
  onSelect?: (next: Selection) => void
}) {
  const [filter, setFilter] = useState('')
  const needle = filter.trim().toLowerCase()
  const rows = useMemo(() => (
    needle
      ? board.rows.filter((row) => matches(row, needle))
      : board.rows
  ), [board.rows, needle])

  const excluded = Object.values(board.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  return (
    <>
      <div className="rh-heading">
        <div>
          <p className="rh-datestamp">{contextLine(board)}</p>
          <h1>Human chatter</h1>
          <p>
            Ranked by how unusual the discussion is, with the independent
            voices behind it kept in view. Not a view on the company.
          </p>
        </div>
      </div>

      {onSelect ? (
        <Filters board={board} selection={selection} onChange={onSelect} />
      ) : null}

      <div className="rh-filters">
        <label className="rh-field">
          <span>Filter companies</span>
          <input
            type="search"
            value={filter}
            placeholder="Ticker or name"
            onChange={(event) => setFilter(event.target.value)}
          />
        </label>
        <p className="muted small rh-filters-note">
          {board.rows.length} {board.rows.length === 1 ? 'company' : 'companies'}
          {needle && rows.length !== board.rows.length
            ? ` · ${rows.length} shown` : ''}
        </p>
      </div>

      {board.rows.length === 0
        ? <EmptyBoard excluded={excluded} />
        : rows.length === 0
          ? (
            <Empty title="No company here matches that.">
              The filter runs over the {board.rows.length} companies already
              listed. Clearing it brings them back.
            </Empty>
          )
          : <Table rows={rows} board={board} onOpen={onOpen} />}
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

function Table({ rows, board, onOpen }: {
  rows: Row[]; board: BoardPayload; onOpen: (ticker: string) => void
}) {
  return (
    <div className="rh-panel">
      {/* Labelled and scrollable: the table may scroll inside this region,
          but the document never scrolls sideways. */}
      <div className="rh-tablewrap" role="region" aria-label="Ranked companies"
           tabIndex={0}>
        <table role="table" className="rh-table">
          <thead>
            <tr role="row">
              <th scope="col">Company</th>
              <th scope="col">Attention</th>
              <th scope="col">Voices</th>
              <th scope="col">Feeds</th>
              <th scope="col">Tone</th>
              <th scope="col" className="right">Price / today</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <TickerRow key={row.ticker} row={row} onOpen={onOpen} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="rh-tablefoot small muted">
        {rows.length} {rows.length === 1 ? 'company' : 'companies'} ·
        {' '}prices from {board.market_venue} ·
        {' '}attention compares equivalent hourly windows
      </p>
    </div>
  )
}

function TickerRow({ row, onOpen }: { row: Row; onOpen: (t: string) => void }) {
  return (
    <tr role="row">
      <th role="rowheader" scope="row" className="rh-company">
        <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
          <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
          <span>
            <span className="rh-ticker" data-testid="rh-row-ticker">{row.ticker}</span>
            <span className="rh-name">{row.name ?? 'Name unknown'}</span>
          </span>
        </button>
        <Marks marks={row.marks} />
      </th>
      <Cell label="Attention">
        <Attention row={row} />
      </Cell>
      <Cell label="Voices">
        <strong className="num">{row.authors}</strong>
        <span className="rh-sub">{row.mentions} {row.mentions === 1 ? 'post' : 'posts'}</span>
      </Cell>
      {/* Feeds, not venues. A row lists every concrete feed it was seen on,
          including each subreddit; the research page counts venues with all
          the subreddits rooted into one. Two honest numbers, so they are
          given two different names rather than left to look inconsistent. */}
      <Cell label="Feeds" testId="rh-row-sources">
        <strong className="num">{row.sources.length}</strong>
        <span className="rh-sub">
          {row.sources.map((source) => sourceLabel(source)).join(', ')}
        </span>
      </Cell>
      <Cell label="Tone">
        <Tone row={row} />
      </Cell>
      <Cell label="Price / today" className="right">
        <Price row={row} />
      </Cell>
    </tr>
  )
}

/** How far above its own normal, when there is a normal worth dividing by.
 *  `ratio` null is phrasing.py's guard, decided once on the server -- the
 *  client never rebuilds it from mentions and expected. */
function Attention({ row }: { row: Row }) {
  if (row.ratio === null) {
    return (
      <>
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

/** Three counts, and deliberately not a percentage.
 *
 *  board.py returns the split as three numbers for a stated reason: the
 *  lexicon scores 0.0 both for "balanced" and for "no lexicon word matched",
 *  the second dominates, and a single "% bullish" computed over that is --
 *  its words -- "mostly noise wearing a percentage sign". `neutral` is not
 *  padding; it is every mention nothing has read yet, and folding it into a
 *  denominator turns a handful of scored posts into a confident-looking
 *  reading. A rounded percentage would also print 0% for one bullish post in
 *  two hundred, and 100% for one bearish one.
 */
function Tone({ row }: { row: Row }) {
  const { bullish, neutral, bearish } = row.tone
  if (bullish + neutral + bearish === 0) {
    return <span className="muted small">Not read yet</span>
  }
  return (
    <span className="rh-tone">
      <span><strong className="num">{bullish}</strong> bullish</span>
      <span><strong className="num">{bearish}</strong> bearish</span>
      <span className="muted">
        <strong className="num">{neutral}</strong> unread or balanced
      </span>
    </span>
  )
}

function Price({ row }: { row: Row }) {
  const { quote } = row
  if (quote.quality === 'unavailable' || row.price === null) {
    return (
      <>
        <strong>—</strong>
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

const MARK_TEXT: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

/** Rendered, never behind a hover. A qualification the reader has to discover
 *  is a qualification that did not happen. */
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
  // association and this repeats it, which costs a word; below 700px the
  // header row is gone and this is the only thing naming the figure.
  return (
    <td role="cell" className={className} data-testid={testId}>
      <span className="rh-cell-label rh-visually-hidden">{label}</span>
      {children}
    </td>
  )
}

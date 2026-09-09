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

import type { BoardPayload, Row, Selection } from '../types'
import { Empty } from './PageState'

export function Chatter({ board, selection, onOpen }: {
  board: BoardPayload
  selection: Selection
  onOpen: (ticker: string) => void
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
          <p className="rh-datestamp">{contextLine(board, selection)}</p>
          <h1>Human chatter</h1>
          <p>
            Ranked by how unusual the discussion is, with the independent
            voices behind it kept in view. Not a view on the company.
          </p>
        </div>
      </div>

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
    <Empty title="No company was measured in this window.">
      Nothing was excluded either, so there was nothing to exclude. Widen the
      window or the sources, or check Activity for whether the fetch ran.
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
        <table className="rh-table">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Attention</th>
              <th scope="col">Voices</th>
              <th scope="col">Sources</th>
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
    <tr>
      <th scope="row" className="rh-company">
        <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
          <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
          <span>
            <span className="rh-ticker" data-testid="rh-row-ticker">{row.ticker}</span>
            <span className="rh-name">{row.name ?? 'Name unknown'}</span>
          </span>
        </button>
        <Marks marks={row.marks} />
      </th>
      <td data-label="Attention">
        <Attention row={row} />
      </td>
      <td data-label="Voices">
        <strong className="num">{row.authors}</strong>
        <span className="rh-sub">{row.mentions} {row.mentions === 1 ? 'post' : 'posts'}</span>
      </td>
      <td data-label="Sources" data-testid="rh-row-sources">
        <strong className="num">{row.sources.length}</strong>
        <span className="rh-sub">{row.sources.join(', ')}</span>
      </td>
      <td data-label="Tone">
        <Tone row={row} />
      </td>
      <td className="right" data-label="Price / today">
        <Price row={row} />
      </td>
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

function Tone({ row }: { row: Row }) {
  const total = row.tone.bullish + row.tone.neutral + row.tone.bearish
  if (total === 0) {
    return <span className="muted small">Not read yet</span>
  }
  const positive = Math.round((row.tone.bullish / total) * 100)
  return (
    <>
      <strong className="num">{positive}% positive</strong>
      {/* Proportions as text first, then as a bar. Colour is never the only
          signal, and the bar is decoration over a figure that already reads. */}
      <span className="rh-tonebar" aria-hidden="true">
        <span style={{ flexGrow: row.tone.bullish || 0.001 }} className="bull" />
        <span style={{ flexGrow: row.tone.neutral || 0.001 }} className="flat" />
        <span style={{ flexGrow: row.tone.bearish || 0.001 }} className="bear" />
      </span>
    </>
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

function contextLine(board: BoardPayload, selection: Selection): string {
  const hours = selection.window
  return `${board.market_venue} · last ${hours} ${hours === 1 ? 'hour' : 'hours'}`
}

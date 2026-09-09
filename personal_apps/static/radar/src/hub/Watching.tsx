// The companies this account marked.
//
// Built from `watch_rows` and never by filtering the ranked list. The two
// answer different questions: the ranked list is what cleared the floor in
// this window, and a mark is a standing instruction to keep showing me this
// one. Filtering the ranked rows would silently drop exactly the companies
// that went quiet -- which is usually why somebody marked them.
//
// The mark itself is per account. Nothing here is cached in the browser: a
// watch list in localStorage survives a sign-out, and the next reader on the
// same machine would see it.
import { useState } from 'react'

import { BoardUnavailable } from '../api'
import type { BoardPayload, Row } from '../types'
import { Empty } from './PageState'
import { useWatchMutation } from './queries'

export function Watching({ board, onOpen }: {
  board: BoardPayload
  onOpen: (ticker: string) => void
}) {
  const watch = useWatchMutation()
  const [pending, setPending] = useState<string | null>(null)
  // The server's answer is the whole list, and it is authoritative the moment
  // it lands -- before the board refetch that brings the matching rows. Until
  // then the rows already in hand are filtered to it, so a removed company
  // leaves immediately instead of lingering for a network round trip.
  const watching = watch.data ?? board.watching
  const rows = board.watch_rows === undefined || watching === undefined
    ? board.watch_rows
    : board.watch_rows.filter((row) => watching.includes(row.ticker))

  return (
    <>
      <div className="rh-heading">
        <div>
          <p className="rh-datestamp">{board.market_venue}</p>
          <h1>Watching</h1>
          <p>
            The companies you marked, whether or not they are loud today. A
            mark keeps a company in view; it is not an alert and nothing here
            is monitored while you are away.
          </p>
        </div>
      </div>

      {watch.error ? <WriteFailed error={watch.error} /> : null}

      <Body board={board} rows={rows} onOpen={onOpen}
            pending={pending}
            onRemove={(ticker) => {
              if (pending) return
              setPending(ticker)
              watch.mutate({ ticker, on: false },
                           { onSettled: () => setPending(null) })
            }} />
    </>
  )
}

function Body({ board, rows, onOpen, onRemove, pending }: {
  board: BoardPayload
  rows: Row[] | undefined
  onOpen: (ticker: string) => void
  onRemove: (ticker: string) => void
  pending: string | null
}) {
  // Absent is not empty. An older or truncated payload did not send the list;
  // an empty one says this account marks nothing. Rendering both as "nothing
  // here" would tell a reader with marks that they have none.
  if (rows === undefined) {
    return (
      <Empty title="Your marks were not included in this board.">
        The list could not be loaded with it. Reload the page; if it stays
        missing, the board is answering an older shape than this page expects.
      </Empty>
    )
  }

  if (rows.length === 0) {
    return (
      <Empty title="Nothing marked yet.">
        Open a company from Human chatter or the search box and choose Watch.
        Marked companies stay listed here on the quiet days too.
      </Empty>
    )
  }

  return (
    <div className="rh-panel">
      <div className="rh-tablewrap" role="region" aria-label="Watched companies"
           tabIndex={0}>
        <table className="rh-table">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Attention</th>
              <th scope="col">Voices</th>
              <th scope="col" className="right">Price / today</th>
              <th scope="col" className="right">Mark</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <WatchRow key={row.ticker} row={row} onOpen={onOpen}
                        onRemove={onRemove} busy={pending === row.ticker}
                        frozen={pending !== null} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="rh-tablefoot small muted">
        {rows.length} marked · prices from {board.market_venue}
      </p>
    </div>
  )
}

function WatchRow({ row, onOpen, onRemove, busy, frozen }: {
  row: Row
  onOpen: (ticker: string) => void
  onRemove: (ticker: string) => void
  busy: boolean
  frozen: boolean
}) {
  const quiet = row.eligible === false
  return (
    <tr>
      <th scope="row" className="rh-company">
        <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
          <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
          <span>
            <span className="rh-ticker">{row.ticker}</span>
            <span className="rh-name">{row.name ?? 'Name unknown'}</span>
          </span>
        </button>
        {quiet ? (
          <p className="rh-marks">
            <span className="rh-badge neutral">
              Quiet — below the floor in this window
            </span>
          </p>
        ) : null}
      </th>
      <td data-label="Attention">
        {row.ratio === null
          ? <span className="muted">No baseline</span>
          : <strong className="num">{row.ratio.toFixed(1)}×</strong>}
      </td>
      <td data-label="Voices">
        <strong className="num">{row.authors}</strong>
        <span className="rh-sub">{row.mentions} {row.mentions === 1 ? 'post' : 'posts'}</span>
      </td>
      <td className="right" data-label="Price / today">
        {row.price === null || row.quote.quality === 'unavailable'
          ? <span className="muted">Unavailable</span>
          : <strong className="num">{price(row)}</strong>}
      </td>
      <td className="right" data-label="Mark">
        <button
          type="button"
          className="rh-button"
          // Disabled while its own write is in flight AND while another one
          // is: two marks changing at once can land out of order, and the
          // later answer would restore a list that predates the earlier one.
          disabled={frozen}
          aria-busy={busy || undefined}
          onClick={() => onRemove(row.ticker)}
        >
          {busy ? 'Removing…' : `Stop watching ${row.ticker}`}
        </button>
      </td>
    </tr>
  )
}

function WriteFailed({ error }: { error: unknown }) {
  const reason = error instanceof BoardUnavailable ? error.message
    : 'The change could not be saved.'
  return (
    <div className="rh-notice red" role="alert">
      <div>
        <strong>That change could not be saved.</strong>
        <p>{reason} Your marks are unchanged.</p>
      </div>
    </div>
  )
}

function price(row: Row): string {
  const symbol = row.quote.currency === 'EUR' ? '€'
    : row.quote.currency === 'USD' ? '$' : ''
  const text = (row.price as number).toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return symbol ? `${symbol}${text}` : `${text} ${row.quote.currency ?? ''}`.trim()
}

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
import type { ReactNode } from 'react'

import { BoardUnavailable } from '../api'
import { isReady } from '../types'
import type { BoardPayload, ReadyBoard, Row } from '../types'
import { AgeLine, Empty } from './PageState'

export function Watching({ board, onOpen, watching: adopted, onToggleWatch,
                           pending, watchError, received, stalled = false,
                           onRetry, standIn }: {
  /** This selection's answer: a board, a waiting shell, or null while
   *  nothing for it has answered yet. The marks ride on a built board; a
   *  waiting shell carries none, and says so through `standIn`. */
  board: BoardPayload | null
  onOpen: (ticker: string) => void
  /** The server's last answer, when one has landed since this board was
   *  fetched. Authoritative immediately; the rows follow on the refetch. */
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  /** Which mark is being written, from the one guard the hub holds. Two
   *  guards -- one here and one on Research -- left both open across a
   *  navigation, which is the out-of-order landing they exist to prevent. */
  pending?: string | null
  watchError?: unknown
  /** When the page received the board, so its age keeps moving. Defaults to
   *  when this mounted, for the suites that render the page on its own. */
  received?: number
  /** Nothing is fetching a replacement for an expired board. */
  stalled?: boolean
  onRetry?: () => void
  /** What stands where the list would, for anything but a built board. */
  standIn?: ReactNode
}) {
  const [mounted] = useState(() => Date.now())
  const ready = board !== null && isReady(board) ? board : null

  return (
    <>
      <div className="rh-heading">
        <div>
          {board ? (
            <p className="rh-datestamp">
              {board.market_venue}
              {ready ? (
                <>
                  {' · '}
                  <AgeLine board={ready} received={received ?? mounted}
                           stalled={stalled} onRetry={onRetry} />
                </>
              ) : null}
            </p>
          ) : null}
          <h1>Watching</h1>
          <p>
            The companies you marked, whether or not they are loud today. A
            mark keeps a company in view; it is not an alert and nothing here
            is monitored while you are away.
          </p>
        </div>
      </div>

      {watchError ? <WriteFailed error={watchError} /> : null}

      {ready === null ? standIn : (
        <Body board={ready} rows={markedRows(ready, adopted)} onOpen={onOpen}
              pending={pending ?? null} onRemove={onToggleWatch} />
      )}
    </>
  )
}

/** The marked rows of a built board.
 *
 *  The server's answer is the whole list, and it is authoritative the moment
 *  it lands -- before the board refetch that brings the matching rows. Until
 *  then the rows already in hand are filtered to it, so a removed company
 *  leaves immediately instead of lingering for a network round trip. */
function markedRows(board: ReadyBoard,
                    adopted: string[] | undefined): Row[] | undefined {
  const watching = adopted ?? board.watching
  return board.watch_rows === undefined || watching === undefined
    ? board.watch_rows
    : board.watch_rows.filter((row) => watching.includes(row.ticker))
}

function Body({ board, rows, onOpen, onRemove, pending }: {
  board: ReadyBoard
  rows: Row[] | undefined
  onOpen: (ticker: string) => void
  onRemove?: (ticker: string) => void
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
        <table role="table" className="rh-table">
          <thead>
            <tr role="row">
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
  onRemove?: (ticker: string) => void
  busy: boolean
  frozen: boolean
}) {
  const quiet = row.eligible === false
  return (
    <tr role="row">
      <th role="rowheader" scope="row" className="rh-company">
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
      <Cell label="Attention">
        {row.ratio === null
          ? <span className="muted">No baseline</span>
          : <strong className="num">{row.ratio.toFixed(1)}×</strong>}
      </Cell>
      <Cell label="Voices">
        <strong className="num">{row.authors}</strong>
        <span className="rh-sub">{row.mentions} {row.mentions === 1 ? 'post' : 'posts'}</span>
      </Cell>
      <Cell label="Price / today" className="right">
        {row.price === null || row.quote.quality === 'unavailable'
          ? <span className="muted">Unavailable</span>
          : (
            <>
              <strong className="num">{price(row)}</strong>
              <span className={`rh-sub num ${moveClass(row.price_move)}`}>
                {row.price_move === null
                  ? 'Move unknown'
                  : `${row.price_move > 0 ? '+' : ''}${(row.price_move * 100).toFixed(1)}%`}
              </span>
            </>
          )}
      </Cell>
      <Cell label="Mark" className="right">
        {onRemove ? (
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
        ) : null}
      </Cell>
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
        <p>
          {reason} The list below is the last one the server confirmed — a
          request that timed out may still have been applied, so reload before
          assuming it was not.
        </p>
      </div>
    </div>
  )
}

function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

function price(row: Row): string {
  const symbol = row.quote.currency === 'EUR' ? '€'
    : row.quote.currency === 'USD' ? '$' : ''
  const text = (row.price as number).toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return symbol ? `${symbol}${text}` : `${text} ${row.quote.currency ?? ''}`.trim()
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

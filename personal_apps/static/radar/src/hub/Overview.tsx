// The first screen: what is loud right now, and what you asked to keep an eye on.
//
// Everything here is a shortened view of one board -- the same board Human
// chatter and Watching read -- so the three can never disagree. What it is not
// is a daily narrative. There is no greeting, no "since your last visit", no
// story of the day: the surface does not know when the reader last looked, and
// a sentence that pretends to would be the first invented thing on a page whose
// whole argument is that it does not invent.
//
// Nor is anything totalled across companies. Two companies discussed by the
// same account are not two people, and the board carries nothing that could
// tell the difference -- so "47 people talking today" would be a number nobody
// measured.
import { useState } from 'react'
import type { ReactNode } from 'react'

import { isReady } from '../types'
import type { BoardPayload, ReadyBoard, Row } from '../types'
import { AgeLine } from './PageState'

const LEAD = 3
const MARKS = 5

export function Overview({ board, received, stalled = false, onRetry,
                          standIn, onOpen, onGo }: {
  /** This selection's answer: a board, a waiting shell, or null while
   *  nothing for it has answered yet. Only a built board has candidates and
   *  marks to show; anything else is `standIn`, under the same heading. */
  board: BoardPayload | null
  /** When the page received the board, so its age keeps moving. Defaults to
   *  when this mounted, for the suites that render the page on its own. */
  received?: number
  /** Nothing is fetching a replacement for an expired board. */
  stalled?: boolean
  onRetry?: () => void
  /** What stands where the panels would, for anything but a built board. */
  standIn?: ReactNode
  onOpen: (ticker: string) => void
  onGo: (page: 'chatter' | 'watching') => void
}) {
  const [mounted] = useState(() => Date.now())
  const ready = board !== null && isReady(board) ? board : null

  return (
    <>
      <div className="rh-heading">
        <div>
          {board ? (
            <p className="rh-datestamp">
              {board.market_venue} · {sessionWord(board)}
              {ready ? (
                <>
                  {' · '}
                  <AgeLine board={ready} received={received ?? mounted}
                           stalled={stalled} onRetry={onRetry} />
                </>
              ) : null}
            </p>
          ) : null}
          <h1>Radar</h1>
          <p>
            What is unusually discussed right now, and the companies you
            marked. Ranked by chatter against each company&rsquo;s own normal,
            with price for context — not a view on any of them.
          </p>
        </div>
      </div>

      {ready === null ? standIn
        : <Panels board={ready} onOpen={onOpen} onGo={onGo} />}
    </>
  )
}

/** The two readings of a built board: what is loud, and what is marked. A
 *  waiting shell has neither -- its `watch_rows` is a placeholder, not the
 *  account's list, and telling a reader with marks that they have none is
 *  the mistake the Watching panel is built to avoid. */
function Panels({ board, onOpen, onGo }: {
  board: ReadyBoard
  onOpen: (ticker: string) => void
  onGo: (page: 'chatter' | 'watching') => void
}) {
  const candidates = board.rows.slice(0, LEAD)
  const marks = board.watch_rows
  const excluded = Object.values(board.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  return (
      <div className="rh-twocol">
        <section className="rh-panel rh-pad" aria-labelledby="rh-lead-head">
          <div className="rh-sectionhead">
            <div>
              <h2 id="rh-lead-head">Current chatter</h2>
              <p className="muted small">
                {orderWord(board)}, last {board.window_hours}
                {board.window_hours === 1 ? ' hour' : ' hours'}
              </p>
            </div>
            <button type="button" className="rh-textbutton"
                    onClick={() => onGo('chatter')}>
              All chatter →
            </button>
          </div>

          {candidates.length === 0
            ? <EmptyBoard excluded={excluded} />
            : (
              <ul className="rh-leads" aria-label="Current chatter">
                {candidates.map((row) => (
                  <li key={row.ticker} data-testid="rh-candidate">
                    <Candidate row={row} onOpen={onOpen} />
                  </li>
                ))}
              </ul>
            )}
        </section>

        <section className="rh-panel rh-pad" aria-labelledby="rh-marks-head">
          <div className="rh-sectionhead">
            <h2 id="rh-marks-head">Watching</h2>
            {marks !== undefined && marks.length > MARKS ? (
              <button type="button" className="rh-textbutton"
                      onClick={() => onGo('watching')}>
                All {marks.length} marked →
              </button>
            ) : null}
          </div>

          {marks === undefined
            ? (
              // Absent, not empty. Telling a reader with marks that they have
              // none is the mistake Watching is built to avoid, and it would
              // be no better here.
              <p className="muted small">
                Your marks were not included in this board. Reload the page;
                this is a missing list, not an empty one.
              </p>
            )
            : marks.length === 0
            ? (
              <p className="muted small">
                Nothing marked yet. Open a company and choose Watch; marked
                companies stay listed on the quiet days too.
              </p>
            )
            : (
              <ul className="rh-marklist" aria-label="Watching">
                {marks.slice(0, MARKS).map((row) => (
                  <li key={row.ticker} data-testid="rh-watchrow">
                    <button type="button" className="rh-marklink"
                            onClick={() => onOpen(row.ticker)}>
                      <span className="rh-ticker">{row.ticker}</span>
                      <span className="rh-name">{row.name ?? 'Name unknown'}</span>
                    </button>
                    <span className="rh-markprice num">{priceText(row)}</span>
                  </li>
                ))}
              </ul>
            )}
          {marks !== undefined && marks.length > 0 && marks.length <= MARKS ? (
            <button type="button" className="rh-textbutton"
                    onClick={() => onGo('watching')}>
              Open Watching →
            </button>
          ) : null}
        </section>
      </div>
  )
}

function Candidate({ row, onOpen }: { row: Row; onOpen: (t: string) => void }) {
  return (
    <>
      <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
        <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
        <span>
          <span className="rh-ticker">{row.ticker}</span>
          <span className="rh-name">{row.name ?? 'Name unknown'}</span>
        </span>
      </button>
      {/* The server's own phrasing, styled by kind and never parsed. This is
          the one place the clauses earn their room: three rows, not sixteen,
          and no column beside them saying the same thing. */}
      {row.clauses.length ? (
        <p className="rh-clauses">
          {row.clauses.map((clause, index) => (
            <span key={index} className={`rh-clause ${clause.kind}`}>
              {clause.text}
            </span>
          ))}
        </p>
      ) : null}
      <p className="rh-leadprice small">
        {priceText(row)}
        {row.marks.length ? (
          <span className="rh-badge amber">{markWord(row.marks[0]!)}</span>
        ) : null}
      </p>
    </>
  )
}

function EmptyBoard({ excluded }: { excluded: number }) {
  if (excluded > 0) {
    return (
      <p className="muted small">
        Nothing cleared the floor in this window. {excluded}
        {excluded === 1 ? ' company was' : ' companies were'} left out by the
        eligibility floor and the breadth filter — a quiet window, not a
        missing one.
      </p>
    )
  }
  return (
    <p className="muted small">
      No company cleared this selection in this window. Nothing was recorded
      as excluded by the floor or the breadth filter, so try a wider window or
      more feeds — and Activity says whether the fetch ran at all.
    </p>
  )
}

const MARK_WORD: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

function markWord(mark: string): string {
  return MARK_WORD[mark] ?? mark
}

/** The board can be sorted, and a sorted board's first three are not the
 *  loudest three. Saying so anyway would caption the rows with a claim the
 *  ordering does not support. */
const SORT_WORD: Record<string, string> = {
  ticker: 'First alphabetically', mentions: 'Most mentions',
  divergence: 'Largest divergence', ratio: 'Furthest above their own normal',
  move: 'Largest price move', lean: 'Strongest lean',
}

function orderWord(board: BoardPayload): string {
  if (board.sort === null) return 'Loudest against their own normal'
  return SORT_WORD[board.sort] ?? 'In the order the board is sorted'
}

function sessionWord(board: BoardPayload): string {
  return board.session === 'regular' ? 'open' : board.session
}

function priceText(row: Row): string {
  if (row.price === null || row.quote.quality === 'unavailable') {
    return 'Price unavailable'
  }
  const symbol = row.quote.currency === 'EUR' ? '€'
    : row.quote.currency === 'USD' ? '$' : ''
  const value = row.price.toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const move = row.price_move === null ? ''
    : ` ${row.price_move > 0 ? '+' : ''}${(row.price_move * 100).toFixed(1)}%`
  const price = symbol ? `${symbol}${value}` : `${value} ${row.quote.currency ?? ''}`
  return `${price.trim()}${move}`
}

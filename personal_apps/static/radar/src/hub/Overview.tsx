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
import type { BoardPayload, Row } from '../types'

const LEAD = 3
const MARKS = 5

export function Overview({ board, onOpen, onGo }: {
  board: BoardPayload
  onOpen: (ticker: string) => void
  onGo: (page: 'chatter' | 'watching') => void
}) {
  const candidates = board.rows.slice(0, LEAD)
  const marks = board.watch_rows ?? []
  const excluded = Object.values(board.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  return (
    <>
      <div className="rh-heading">
        <div>
          <p className="rh-datestamp">
            {board.market_venue} · {sessionWord(board)} · built {stamp(board.generated_at)}
          </p>
          <h1>Radar</h1>
          <p>
            What is unusually discussed right now, and the companies you
            marked. Ranked by chatter against each company&rsquo;s own normal,
            with price for context — not a view on any of them.
          </p>
        </div>
      </div>

      <div className="rh-twocol">
        <section className="rh-panel rh-pad" aria-labelledby="rh-lead-head">
          <div className="rh-sectionhead">
            <div>
              <h2 id="rh-lead-head">Current chatter</h2>
              <p className="muted small">
                Loudest against their own normal, last {board.window_hours}
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
            {marks.length > MARKS ? (
              <button type="button" className="rh-textbutton"
                      onClick={() => onGo('watching')}>
                All {marks.length} marked →
              </button>
            ) : null}
          </div>

          {marks.length === 0
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
          {marks.length > 0 && marks.length <= MARKS ? (
            <button type="button" className="rh-textbutton"
                    onClick={() => onGo('watching')}>
              Open Watching →
            </button>
          ) : null}
        </section>
      </div>
    </>
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
      No company was measured in this window, and nothing was excluded either.
      Activity says whether the fetch ran.
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

function stamp(iso: string): string {
  try {
    return `${new Date(iso).toLocaleTimeString('en-GB',
      { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })} Berlin`
  } catch {
    return 'time unknown'
  }
}

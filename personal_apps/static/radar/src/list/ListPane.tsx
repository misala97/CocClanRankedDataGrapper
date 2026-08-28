import { useEffect, useState } from 'react'

import { Controls } from '../board/Controls'
import { magnitudes } from '../board/geometry'
import { stampTime } from '../format'
import { Widen } from '../Widen'
import { Excluded } from './Excluded'
import { Marks } from './Marks'
import { Spend } from './Spend'
import { TickerRow } from './TickerRow'
import type { BoardPayload, Mark, Row, Selection } from '../types'

/** How long a board stays worth reading without saying how old it is.
 *
 *  The island fetches on a control change and never on a clock, which is the
 *  right behaviour for a page read in bursts -- but it means a tab left open
 *  over lunch shows the pre-lunch board with nothing to distinguish it from a
 *  live one. On a surface about what people are saying RIGHT NOW that is the
 *  most expensive silence available. Fifteen minutes is short enough that a
 *  stamp appearing means something and long enough that the ordinary read,
 *  where a control gets touched every couple of minutes, never sees it. */
const STALE_MINUTES = 15

/** When this board was built, once it is old enough for that to matter.
 *
 *  `generated_at` is the request time rather than the last ingest, so it
 *  answers exactly one question and it is the question the reader has: is
 *  what I am looking at from this visit or from the one before lunch.
 */
function Age({ iso }: { iso: string }) {
  // The page has no other reason to re-render while it sits untouched, which
  // is precisely the situation this warns about -- computed once at mount it
  // would be permanently zero minutes old. One timer for the whole board.
  const [, tick] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 60_000)
    return () => clearInterval(timer)
  }, [])

  const at = new Date(iso).getTime()
  if (Number.isNaN(at)) return null
  const minutes = Math.floor((Date.now() - at) / 60_000)
  if (minutes < STALE_MINUTES) return null

  const age = minutes < 120 ? `${minutes} minutes`
    : `${Math.floor(minutes / 60)} hours`
  return (
    <span className="age">
      <b>built {age} ago</b> at {stampTime(iso)}
      {' '}
      <button type="button" onClick={() => window.location.reload()}>
        Reload
      </button>
    </span>
  )
}

/** What a mark means when EVERY row on the board carries it.
 *
 *  A mark carried by every row is not a mark -- the same rule the session
 *  state follows, said once by the page instead of fourteen times down the
 *  list. It is also the only honest version of the header: the board used to
 *  claim "baselines over 30 days" while every row it listed was flagged
 *  provisional, which is the opposite of true.
 */
// Exhaustive over Mark on purpose: a new mark will not compile until
// someone decides what the board says when every row carries it.
const UNIVERSAL: Record<Mark, string> = {
  provisional: 'every baseline here is under 14 days old',
  'single-source': 'every row here came from a single source',
  'no-print': 'no tape has printed in this window',
  partial: 'every source here was truncated, so the counts are low',
  // Distinct from `provisional`: this fires when the extraction rules
  // changed recently, not when a ticker itself is new -- see marks.test.tsx.
  'warming-up': 'the extraction rules changed recently, so every baseline '
    + 'here is starting over',
}

/** Marks shared by the whole board, in the order they are written above.
 *
 *  Two rows minimum: on a one-row board "every row" is trivially true, and
 *  moving the only row's mark into the header would hide it from the place a
 *  reader is looking. */
export function universalMarks(rows: Row[]): Mark[] {
  if (rows.length < 2) return []
  return (Object.keys(UNIVERSAL) as Mark[]).filter(
    (mark) => rows.every((row) => row.marks.includes(mark)))
}

/** The board's state, said once by the page rather than by every row.
 *
 *  With the exchange shut there is no price movement to diverge from, so the
 *  ranking falls through to chatter -- which is the useful answer at 23:00 on
 *  a Sunday, and only honest if the page says which of the two rankings the
 *  reader is looking at.
 */
function Finding({ payload, shared }: {
  payload: BoardPayload
  shared: Mark[]
}) {
  const count = payload.rows.length
  const tickers = count === 1 ? '1 ticker' : `${count} tickers`
  // The two never both apply to one row -- leaderboard.py picks exactly one
  // per row, by age -- so at most one is ever universal at a time. Either
  // way the header must not say "baselines over 30 days" while every row
  // disagrees; that was the bug this whole section exists to fix.
  const thinBaseline = shared.includes('provisional') ? 'provisional'
    : shared.includes('warming-up') ? 'warming-up'
    : null
  const baselines = thinBaseline ? UNIVERSAL[thinBaseline] : 'baselines over 30 days'
  const rest = shared.filter(
    (mark) => mark !== 'provisional' && mark !== 'warming-up')

  return (
    <p className="finding">
      {payload.session === 'closed' ? (
        <>
          No price is moving, so these are ranked by <b>chatter against each
          ticker&rsquo;s own normal</b> — what to look at when it opens.
          {' '}<b>{tickers}</b> cleared the bar in the last
          {' '}<b>{payload.window_hours}h</b>,{' '}
          <span className={shared.length ? 'shared' : undefined}>{baselines}</span>.
        </>
      ) : (
        <>
          <b>{tickers}</b> above their normal in the last
          {' '}<b>{payload.window_hours}h</b> ·{' '}
          <span className={shared.length ? 'shared' : undefined}>{baselines}</span>
        </>
      )}
      {rest.map((mark) => (
        <span key={mark} className="shared"> · {UNIVERSAL[mark]}</span>
      ))}
    </p>
  )
}

/** The list: what the board found, and an account of what it did not show.
 *
 *  Replaces the two-tier arrangement of three lead cards over scan rows. That
 *  split bought visual variety at the cost of making identical data look like
 *  two different kinds of thing, and it forced every fact about a ticker into
 *  a 300px card because there was nowhere else to put it.
 *
 *  The magnitude scale is computed here rather than per row, because the point
 *  of it is that the rows share one -- a bar scaled inside its own row would
 *  make every row look equally loud.
 */
export function ListPane({ payload, selection, selected, busy, onSelect,
                          onChange }: {
  payload: BoardPayload
  selection: Selection
  selected: string | null
  busy: boolean
  onSelect: (ticker: string) => void
  onChange: (next: Selection) => void
}) {
  const mags = magnitudes(payload.rows)
  const shared = universalMarks(payload.rows)

  return (
    <aside className="list">
      <div className="lhead">
        <div className="brand">
          <h1>Radar</h1>
          {payload.session === 'closed' && (
            <span className="state"><b>market closed</b></span>
          )}
          <Age iso={payload.generated_at} />
        </div>
        <Finding payload={payload} shared={shared} />
      </div>

      <Controls payload={payload} selection={selection} busy={busy}
                onChange={onChange} />

      {/* The busy signal sits here rather than on the controls: the chips are
          not stale, this list is. */}
      <div className="rows" aria-busy={busy || undefined}>
        {payload.rows.map((row) => (
          <TickerRow key={row.ticker} row={row} onSelect={onSelect}
                     magnitude={mags[row.ticker]} suppress={shared}
                     selected={row.ticker === selected} />
        ))}
        {payload.rows.length === 0 && (
          // Where the first row would have been, not as a footnote under an
          // empty frame: on this board it is the entire answer.
          //
          // With something excluded, the account below carries the way out
          // and repeating it here would say it twice. With nothing excluded
          // there is no account, and the empty board used to end in a full
          // stop -- a state with no next action on a surface whose two
          // controls are exactly what to reach for.
          <p className="none" role="status">
            Nothing cleared the bar in this window.
            {Object.keys(payload.excluded).length === 0 && (
              <span className="pointer"><Widen /></span>
            )}
          </p>
        )}
        <Excluded payload={payload} />
        <Marks rows={payload.rows} suppress={shared} />
        <Spend payload={payload} />
      </div>
    </aside>
  )
}

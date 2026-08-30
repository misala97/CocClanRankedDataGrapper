import { Fragment, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { Controls } from '../board/Controls'
import { MarketSwitch } from '../board/MarketSwitch'
import { magnitudes } from '../board/geometry'
import { formatMarketTime, humanAge, plural, stampTime } from '../format'
import { Widen } from '../Widen'
import { Excluded } from './Excluded'
import { Marks } from './Marks'
import { Spend } from './Spend'
import { TickerRow } from './TickerRow'
import type { BoardPayload, Mark, Row, Selection } from '../types'

/** When the always-visible UTC stamp becomes a stale-board warning.
 *
 *  The island fetches on a control change and never on a clock, so the stamp
 *  itself is always useful and the reload action becomes useful once a tab
 *  has plausibly been left behind. */
const STALE_MINUTES = 15

/** When this board was built, always; a reload control once it is stale.
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
  const stale = minutes >= STALE_MINUTES
  const age = minutes < 120 ? `${minutes}m` : `${Math.floor(minutes / 60)}h`
  // Fresh states the build time; stale states the age instead -- the age is
  // the actionable number, and both never share the line since a masthead
  // corner does not fit "117m old · 16:46 CEST · Reload".
  return (
    <span className="age">
      {stale ? <b>{age} old</b>
             : <>updated <time dateTime={iso}>{stampTime(iso)}</time></>}
      {stale && (
        <>
          {' '}
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </>
      )}
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
//
// Token-length by design since the 2026-08-30 head rework: these render in
// a one-line status strip, not a sentence, so each is a clause a scanning
// reader absorbs whole. Full prose explanations live on the marks legend.
const UNIVERSAL: Record<Mark, string> = {
  provisional: 'baselines under 14d',
  'single-source': 'all single-source',
  'no-print': 'no tape printed',
  partial: 'sources truncated',
  // Distinct from `provisional`: this fires when the extraction rules
  // changed recently, not when a ticker itself is new -- see marks.test.tsx.
  'warming-up': 'baselines starting over',
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

/** Quote provenance the whole board carries, lifted the same way.
 *
 *  On the German board with no Xetra entitlement EVERY row's quote is a US
 *  fallback, aged the same ~46 hours -- and five badges times seventeen rows
 *  all saying one thing is how the old row drowned. The board states it once,
 *  in amber, and each row keeps only what deviates (see deviantQuoteFacts).
 *
 *  `keys` is the suppression contract with TickerRow; `tokens` is what the
 *  Status line prints. Same two-row floor as universalMarks, same reason.
 */
export function universalQuoteFacts(rows: Row[]): {
  keys: string[]
  tokens: string[]
} {
  if (rows.length < 2) return { keys: [], tokens: [] }
  const keys: string[] = []
  const tokens: string[] = []

  if (rows.every((row) => row.quote.is_fallback)) {
    keys.push('fallback')
    tokens.push('US prices')
  }
  const aged = rows.every((row) =>
    row.quote.quality === 'stale' || row.quote.quality === 'eod')
  if (aged) {
    keys.push('aged')
    const oldest = rows.reduce<number | null>(
      (best, row) => (row.quote.age_seconds !== null
        && (best === null || row.quote.age_seconds > best)
        ? row.quote.age_seconds : best), null)
    tokens.push(oldest !== null ? `quotes ${humanAge(oldest)} old` : 'EOD quotes')
  }
  return { keys, tokens }
}

/** The session enum as a status word beside the venue: "US markets open".
 *  sessionLabel() says "Market open", which next to `market_venue` would
 *  read "US markets Market open". */
const SESSION_WORDS: Record<string, string> = {
  premarket: 'pre-market',
  regular: 'open',
  afterhours: 'after hours',
  closed: 'closed',
}

/** The board's state as one line of tokens, said once by the page.
 *
 *  This replaced a three-sentence paragraph 2026-08-30. The prose restated
 *  what the rows already show ("what is being talked about more than usual")
 *  every single visit, and a reader who has seen it once never reads it
 *  again -- it was 60px of the same words between them and the first ticker.
 *  What survives is exactly the facts that change: venue and session, the
 *  next boundary, which ranking is in force, how many rows, and any caution
 *  the whole board carries.
 *
 *  With the exchange shut there is no price movement to diverge from, so the
 *  ranking falls through to chatter -- and the RANKED BY CHATTER token says
 *  which of the two rankings the reader is looking at. It is the one token
 *  set in the accent, because it changes what the score column means.
 */
function Status({ payload, shared, quoteTokens }: {
  payload: BoardPayload
  shared: Mark[]
  quoteTokens: string[]
}) {
  const count = payload.rows.length
  // The two never both apply to one row -- leaderboard.py picks exactly one
  // per row, by age -- so at most one is ever universal at a time. Either
  // way the line must not say "30d baselines" while every row disagrees;
  // that was the bug the shared-marks logic exists to fix.
  const thinBaseline = shared.includes('provisional') ? 'provisional'
    : shared.includes('warming-up') ? 'warming-up'
    : null
  const rest = shared.filter(
    (mark) => mark !== 'provisional' && mark !== 'warming-up')
  const closed = payload.session === 'closed'

  // Composed as a list first so the separating dots can be real text.
  // A CSS-generated separator is invisible to screen readers AND to the
  // announcement a role="status" change produces, which would read
  // "17:30 ranked by chatter" as one runon. The dot rides at the END of
  // its token, so a wrapped line never opens with punctuation.
  const tokens: { key: string; node: ReactNode; cls?: string }[] = [
    {
      key: 'session',
      node: (
        <>
          {payload.market_venue}{' '}
          <b className={closed ? 'off' : undefined}>
            {SESSION_WORDS[payload.session] ?? payload.session}
          </b>
          {' '}· {payload.next_boundary_label} {clock(payload.next_boundary_at)}
        </>
      ),
    },
    // Chatter ranking is a fact about the closed session, so it follows
    // directly from the session token it is a consequence of.
    ...(closed
      ? [{ key: 'mode', cls: 'mode', node: 'ranked by chatter' as ReactNode }]
      : []),
    {
      key: 'count',
      // The baselines claim only when the board could actually survey it:
      // universalMarks() answers nothing under two rows, so a one-row board
      // saying "30d baselines" beside a row marked provisional was the head
      // contradicting its own list. Seen live 2026-08-30, one SPCX row.
      node: count < 2
        ? <>{count} {plural(count, 'ticker', 'tickers')}</>
        : (
          <>
            {count} tickers ·{' '}
            {thinBaseline
              ? <span className="shared">{UNIVERSAL[thinBaseline]}</span>
              : '30d baselines'}
          </>
        ),
    },
    ...rest.map((mark) => ({
      key: mark, cls: 'shared', node: UNIVERSAL[mark] as ReactNode,
    })),
    // Quote provenance the whole board carries -- see universalQuoteFacts.
    ...quoteTokens.map((token) => ({
      key: `q-${token}`, cls: 'shared', node: token as ReactNode,
    })),
  ]

  return (
    // role="status" so a filter change is announced. Going from ten rows
    // to three used to be silent to a screen reader: the rows swapped, the
    // count in this line changed, and nothing told anyone.
    //
    // Each token is a nowrap span with its separating dot INSIDE it, and the
    // plain space between spans is the only break opportunity -- so the line
    // wraps between facts, never inside one, and never opens with a dot.
    <p className="status" role="status">
      {tokens.map(({ key, node, cls }, index) => (
        <Fragment key={key}>
          <span className={cls ? `tok ${cls}` : 'tok'}>
            {node}
            {index < tokens.length - 1 && <span className="dot"> ·</span>}
          </span>
          {index < tokens.length - 1 && ' '}
        </Fragment>
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
  const quoteShared = universalQuoteFacts(payload.rows)

  return (
    <aside className="list" aria-label="Board">
      <div className="lhead">
        {/* Masthead: identity, the market the prices come from, freshness.
            The market switch sits beside the wordmark because it changes
            what the board IS -- unlike the strip below, which narrows it.
            The session state that used to sit here as a chip lives in the
            status line now; it was the same fact stated twice. */}
        <div className="brand">
          <h1>Radar</h1>
          <MarketSwitch selection={selection} onChange={onChange} />
          <Age iso={payload.generated_at} />
        </div>
        <Status payload={payload} shared={shared}
                quoteTokens={quoteShared.tokens} />
      </div>

      <Controls payload={payload} selection={selection} busy={busy}
                onChange={onChange} />

      {/* The busy signal sits here rather than on the controls: the chips are
          not stale, this list is. */}
      <div className="rows" id="radar-rows" tabIndex={-1}
           aria-busy={busy || undefined}>
        {payload.rows.map((row) => (
          <TickerRow key={row.ticker} row={row} onSelect={onSelect}
                     magnitude={mags[row.ticker]} suppress={shared}
                     quoteSuppress={quoteShared.keys}
                     session={payload.session} selection={selection}
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
        <Marks rows={payload.rows} suppress={shared}
               session={payload.session} />
        <Spend payload={payload} />
      </div>
    </aside>
  )
}

/** Header boundaries are local Berlin clock times; the zone is fixed elsewhere
 * in the board's timestamp treatment and would only make this terse context
 * line wrap sooner on a phone. */
function clock(iso: string): string {
  return formatMarketTime(iso).replace(/ (?:CET|CEST)$/, '')
}

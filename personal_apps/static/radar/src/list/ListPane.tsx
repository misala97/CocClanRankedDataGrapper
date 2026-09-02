import { Fragment, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import { Controls } from '../board/Controls'
import { MarketSwitch } from '../board/MarketSwitch'
import { Search } from '../board/Search'
import { formatMarketTime, humanAge, plural, stampTime } from '../format'
import { Widen } from '../Widen'
import { SpendMark } from './Spend'
import { TickerRow, scoredAgainstPrice } from './TickerRow'
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
  /** The lifted age in seconds when `aged` is among the keys -- the age
   *  most rows share, which a row compares its own against to decide
   *  whether it still has something to say (TickerRow.deviantQuoteFacts). */
  agedTypical: number | null
} {
  if (rows.length < 2) return { keys: [], tokens: [], agedTypical: null }
  const keys: string[] = []
  const tokens: string[] = []
  let agedTypical: number | null = null

  if (rows.every((row) => row.quote.is_fallback)) {
    keys.push('fallback')
    tokens.push('US prices')
  }
  // Over the rows that HAVE a quote. One row with no quote at all (QQQ, live
  // 2026-09-01) used to block the lift, so six stale rows each said "quote
  // 1h old" and every row grew a flags line -- the wallpaper the lift exists
  // to prevent. An unquoted row has no age to lift; it says "no live quote"
  // itself, and that survives the suppression (deviantQuoteFacts).
  const quoted = rows.filter((row) => row.quote.quality !== 'unavailable')
  const aged = quoted.length > 0 && quoted.every((row) =>
    row.quote.quality === 'stale' || row.quote.quality === 'eod')
  if (aged) {
    keys.push('aged')
    // The age most rows share -- the upper median -- not the oldest. The
    // status line said "quotes 320d old" over a board of hour-old quotes
    // because one delisted ticker carried a year-old print; that row keeps
    // its own age as a deviation (TickerRow), the board states the typical.
    const ages = quoted.map((row) => row.quote.age_seconds)
      .filter((age): age is number => age !== null)
      .sort((a, b) => a - b)
    agedTypical = ages[Math.floor(ages.length / 2)] ?? null
    tokens.push(agedTypical !== null
      ? `quotes ${humanAge(agedTypical)} old` : 'EOD quotes')
  }
  return { keys, tokens, agedTypical }
}

/** The thin-baseline caution the whole board carries, if any.
 *
 *  The two never both apply to one row -- leaderboard.py picks exactly one
 *  per row, by age -- so at most one is ever universal at a time. */
function thinBaselineOf(shared: readonly Mark[]): Mark | null {
  return shared.includes('provisional') ? 'provisional'
    : shared.includes('warming-up') ? 'warming-up'
    : null
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
  // Either way the line must not say "30d baselines" while every row
  // disagrees; that was the bug the shared-marks logic exists to fix.
  const thinBaseline = thinBaselineOf(shared)
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

export interface Tier {
  key: 'scored' | 'chatter'
  rows: Row[]
}

/** The list in its two tiers: rows scored against the price move, then
 *  rows ranked on chatter alone.
 *
 *  A presentation of the server's order, never a reordering of it:
 *  leaderboard.py sorts scored rows first and everything else after, by
 *  chatter. The boundary was invisible on the surface -- `DIV +0.10`,
 *  `Z 4.9` and `DIV not scored` read as one ordering down one column
 *  (critique, 2026-09-01) when loud-and-unmoved and quiet-but-quoted-less
 *  are ranked on different quantities. */
export function splitTiers(rows: Row[]): [Tier, Tier] {
  return [
    { key: 'scored', rows: rows.filter(scoredAgainstPrice) },
    { key: 'chatter', rows: rows.filter((row) => !scoredAgainstPrice(row)) },
  ]
}

/** A tier's caption: the term the rows under it are ordered by, said once
 *  where the ordering changes rather than as a 10.5px prefix on every score.
 *
 *  Not a control. It does not fold or filter; it is the rule between two
 *  quantities. */
function TierCaption({ tier, windowHours, count, reason }: {
  tier: Tier['key']
  windowHours: number
  count: number
  /** Why an open market has nothing scored, when the board as a whole knows
   *  -- "baselines starting over". Rendered only at zero, where an absent
   *  caption would read as "there is no such thing". */
  reason: string | null
}) {
  const scored = tier === 'scored'
  return (
    // Real spaces between the spans: a screen reader runs "DIV2" together
    // without them, and the flex gap is invisible to it.
    <p className={`tier ${tier}`}>
      <b>{scored ? 'Scored against price' : 'Chatter only'}</b>
      <span className="dot"> ·</span>{' '}
      <span className="what">
        {scored
          ? `chatter vs the ${windowHours}h price move`
          : 'unusual talk, no usable price move to compare'}
      </span>
      <span className="dot"> ·</span>{' '}
      <span className="term">{scored ? 'DIV' : 'Z'}</span>
      {count === 0 && reason && <span className="why"> — {reason}</span>}
      {' '}
      <span className="n">{count}</span>
    </p>
  )
}

/** The list: what the board found, in two tiers, over an account of what it
 *  did not show.
 *
 *  A ledger since the 2026-09-01 layout round: one line per row under a
 *  column header, so that the 10-15 rows PRODUCT.md calls the majority state
 *  fit a 1440×900 desk without scrolling. The account (excluded, marks,
 *  spend) arrives as a slot rather than being rendered here, because below
 *  900px the page places it after the panel instead -- see BoardPage.
 */
export function ListPane({ payload, selection, selected, busy, onSelect,
                          onChange, account, watching = [], onToggleWatch }: {
  payload: BoardPayload
  selection: Selection
  selected: string | null
  busy: boolean
  onSelect: (ticker: string) => void
  onChange: (next: Selection) => void
  /** The footer matter, when this pane is where it belongs. */
  account?: ReactNode
  /** The reader's marks and how to flip one; rendered as the Watching tier
   *  and as the star beside each row. */
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
}) {
  const shared = universalMarks(payload.rows)
  const quoteShared = universalQuoteFacts(payload.rows)
  // Watched rows come from the server (`watch_rows`, built whatever the
  // floor said) -- and, until the refetch after a star lands, from the
  // board's own rows, so a fresh mark moves up at once. One row per ticker,
  // in the order the marks were made; the ranked tiers skip them.
  const marked = new Set(watching)
  const served = payload.watch_rows ?? []
  const watchRows = [
    ...served.filter((r) => marked.has(r.ticker)),
    ...payload.rows.filter((r) => marked.has(r.ticker)
      && !served.some((w) => w.ticker === r.ticker)),
  ].sort((a, b) => watching.indexOf(a.ticker) - watching.indexOf(b.ticker))
  const ranked = payload.rows.filter((r) => !marked.has(r.ticker))
  const [scored, chatter] = splitTiers(ranked)
  // The board loads into a task and performs no entrance. A board that
  // REPLACES the one on screen may settle -- as one block, no stagger -- so
  // the swap reads as arrival rather than a hard cut. `generated_at` is the
  // build stamp: it changes on every refetch and never on a selection, so
  // "not the embedded board any more" is exactly this comparison. The class
  // only arms the CSS; the browser animates whatever is inserted while it is
  // on, which is the rows and captions the new board brought.
  const embeddedStamp = useRef(payload.generated_at)
  const settled = payload.generated_at !== embeddedStamp.current
  // With the exchange shut every row is chatter-ranked and the status line
  // already says RANKED BY CHATTER; one caption over one tier would be a
  // heading with nothing to distinguish from.
  const captions = payload.session !== 'closed' && ranked.length > 0
  const thin = thinBaselineOf(shared)

  const renderRow = (row: Row) => (
    <TickerRow key={row.ticker} row={row} onSelect={onSelect}
               suppress={shared} quoteSuppress={quoteShared.keys}
               liftedAge={quoteShared.agedTypical}
               session={payload.session} selection={selection}
               selected={row.ticker === selected}
               watching={marked.has(row.ticker)} onToggleWatch={onToggleWatch} />
  )

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
          <Search rows={payload.rows} watching={watching}
                  onPick={onSelect} onToggleWatch={onToggleWatch} />
          {/* Ops at a glance, in the corner the eye already checks for
              freshness: today's tone spend, then the stamp. */}
          <SpendMark payload={payload} />
          <Age iso={payload.generated_at} />
        </div>
        <Status payload={payload} shared={shared}
                quoteTokens={quoteShared.tokens} />
      </div>

      <Controls payload={payload} selection={selection} busy={busy}
                onChange={onChange} />

      {/* The busy signal sits here rather than on the controls: the chips are
          not stale, this list is. */}
      <div className={settled ? 'rows settled' : 'rows'} id="radar-rows"
           tabIndex={-1} aria-busy={busy || undefined} onKeyDown={walkRows}>
        {/* Column names only. The terms the scores carry -- DIV, Z -- belong
            to the tier captions, where the ordering actually changes. Hidden
            from assistive tech: every cell already names itself.

            INSIDE the scroller, sticky, not above it: outside, it was laid
            out to the pane's full width while the rows sat inside the
            scrollbar 17px narrower, and the fr column absorbed the difference
            -- Score and Lean drifted ~20px off the cells under them. One grid
            on one width, and it stays put on a long board. */}
        <div className="cols" aria-hidden="true">
          <span>Ticker</span>
          <span>Talk · price</span>
          <span className="r">Score</span>
          <span>Ratio · price · move</span>
          <span className="r">Lean</span>
        </div>
        {watchRows.length > 0 && (
          <p className="tier watching">
            <b>Watching</b>
            <span className="dot"> ·</span>{' '}
            <span className="what">your marks, in every view</span>
            {' '}
            <span className="n">{watchRows.length}</span>
          </p>
        )}
        {watchRows.map(renderRow)}
        {captions && (
          <TierCaption tier="scored" windowHours={payload.window_hours}
                       count={scored.rows.length}
                       reason={thin ? UNIVERSAL[thin] : null} />
        )}
        {scored.rows.map(renderRow)}
        {captions && chatter.rows.length > 0 && (
          <TierCaption tier="chatter" windowHours={payload.window_hours}
                       count={chatter.rows.length} reason={null} />
        )}
        {chatter.rows.map(renderRow)}
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
        {account}
      </div>
    </aside>
  )
}

/** The arrow keys walk the rows; Home and End jump to either end.
 *
 *  Focus only. Selecting on every keystroke would fetch a panel per press;
 *  Enter selects, as on any link. Tab used to be the only way down the list
 *  -- eleven stops to reach the last row (critique, 2026-09-01). */
function walkRows(event: KeyboardEvent<HTMLDivElement>) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const current = (event.target as HTMLElement).closest<HTMLElement>('.row')
  if (!current) return
  const rows = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>('.row'))
  const index = rows.indexOf(current)
  const next = event.key === 'ArrowDown' ? Math.min(index + 1, rows.length - 1)
    : event.key === 'ArrowUp' ? Math.max(index - 1, 0)
    : event.key === 'Home' ? 0
    : rows.length - 1
  event.preventDefault()
  rows[next]?.focus()
}

/** Header boundaries are local Berlin clock times; the zone is fixed elsewhere
 * in the board's timestamp treatment and would only make this terse context
 * line wrap sooner on a phone. */
function clock(iso: string): string {
  return formatMarketTime(iso).replace(/ (?:CET|CEST)$/, '')
}

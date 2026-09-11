import { Fragment, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import { Controls } from '../board/Controls'
import { MarketSwitch } from '../board/MarketSwitch'
import { Search } from '../board/Search'
import { defaultDirection, queryFor } from '../api'
import { formatMarketTime, humanAge, plural } from '../format'
import { DELAYED_AFTER_MS, ageAt, pastFresh, refreshDue, untilExpired }
  from '../pending'
import { Widen } from '../Widen'
import { SpendMark } from './Spend'
import { TickerRow, scoredAgainstPrice } from './TickerRow'
import type { BoardPayload, Mark, Row, Selection, SortKey } from '../types'

/** An age at the resolution the state it describes actually moves at.
 *
 *  Seconds below a minute, because this line ticks every second and a board
 *  that has just arrived saying "0 min ago" cannot be watched getting older.
 *  `humanAge` takes over past ninety minutes, where its units -- hours, then
 *  days -- are the ones a person would pick and the seconds stopped meaning
 *  anything hours ago.
 */
function boardAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`
  const minutes = Math.floor(seconds / 60)
  return minutes < 90 ? `${minutes}m` : humanAge(seconds)
}

/** When this board was calculated -- always, in as many words.
 *
 *  It used to print the build time as a clock ("updated 16:46 CEST") and turn
 *  amber after fifteen minutes, which was the right shape for an island that
 *  only ever fetched when a control moved. A shared board can be older than
 *  this tab is, can be being rebuilt while it is read, and can outlive the
 *  window it names -- so the corner says the AGE, which is the number all
 *  three of those states are about, and adds what is being done about it.
 */
function AgeLine({ payload, received, stalled = false, onRetry }: {
  payload: BoardPayload
  received: number
  /** Nothing is fetching a replacement: the last request failed and no wait
   *  is running. Only an expired board has anything to say about it. */
  stalled?: boolean
  onRetry?: () => void
}) {
  // The page has no other reason to re-render while it sits untouched, which
  // is precisely the situation this describes. One timer for the whole board,
  // at the resolution the line is printed in.
  const [, tick] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  // One reading of the clock for everything this line says, through the same
  // functions BoardPage acts on, so the line and the page cannot disagree
  // about what is being done for the board on screen.
  const now = Date.now()
  const age = ageAt(payload, received, now)
  if (age === null) return null
  const retry = onRetry
    ? <button type="button" onClick={onRetry}>Retry</button> : null
  // Past the hard expiry the age itself has stopped being worth printing:
  // the rows describe a rolling window that has moved, and the page has
  // already gone to ask for a board that describes this one.
  const expiry = untilExpired(payload, received, now)
  if (expiry !== null && expiry < 0) {
    return (
      <span className="age expired">
        {stalled
          // Unless that ask failed and nothing else is asking. Promising a
          // recalculation then is the line describing work the page is not
          // doing; the next ask is the reader's, or the next look at the tab.
          ? <><b>Expired</b>{retry}</>
          : <b>Expired, recalculating</b>}
      </span>
    )
  }
  // `stale` is what the server saw when it answered; the fresh bound is how
  // long that answer was good for. A page that has held a board past it is
  // looking at the same thing a stale flag describes, and saying so only
  // when the server happened to notice first would make the line a report on
  // when this tab last asked. Every board, whoever built it: ruling §5 lets
  // one past the bound stay on screen ONLY as stale. What is being done
  // about it is the part that differs, and the word after the age says which.
  const stale = payload.stale || pastFresh(payload, received, now)
  return (
    <span className={stale ? 'age stale' : 'age'}>
      Calculated {boardAge(age)} ago
      {payload.failed
        // A verdict on the queue, not on these rows: they are the last board
        // that built. Printed in place of "refreshing", never beside it -- a
        // refresh that is failing is not one that is happening -- so a stale
        // board whose rebuilds are failing says only this, in the caution
        // colour. Not alone in it: "not refreshed" and "Expired" wear the same
        // amber. Only "refreshing" is quiet (`.age b.queued`, radar.css).
        ? <> · <b>Last refresh failed</b></>
        : !stale ? null
        // The store has a refresh queued and the page is waiting on it --
        // asked by the rule the page waits by (`refreshDue`), so the word can
        // neither claim a refresh the page is not waiting on nor deny one it
        // is. Its own class, not the line's: the quiet treatment belongs to
        // this word.
        : refreshDue(payload, received, now)
          ? <> · <b className="queued">refreshing</b></>
        // A board a worker built for itself. Nothing is queued behind it and
        // nothing asks on its behalf, so the word claims no refresh, and the
        // ask it would take -- a synchronous build -- is the reader's to make.
        : <> · <b>not refreshed</b>{retry}</>}
    </span>
  )
}

/** What the rows area says while there are no rows to put in it.
 *
 *  Its own component for its own clock: how long the reader has been waiting
 *  is measured from when this mounted, which is when the board stopped being
 *  on screen -- not from the last answer, since a poll answering "still
 *  pending" every two seconds would keep resetting a wait that is not
 *  resetting at all.
 *
 *  Mounted under a key of the question being waited for (see the render
 *  below), because the converse is just as wrong: a reader who has just
 *  changed the window has waited no time at all for the board they are now
 *  waiting for, and "Still calculating…" would be describing somebody
 *  else's half minute.
 */
function Waiting({ payload, failing = null, onRetry }: {
  payload: BoardPayload
  /** Why the wait's own asks keep failing, when two in a row have. */
  failing?: string | null
  onRetry?: () => void
}) {
  const [, tick] = useState(0)
  const since = useRef(Date.now())
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const delayed = Date.now() - since.current >= DELAYED_AFTER_MS
  // Busy is not a queue: the generation is refusing work, so there is no
  // position to be near the front of and nothing to be patient about.
  const busy = payload.busy
  return (
    <p className="none pending" role="status">
      {busy ? <b>The board is busy with other selections.</b>
        : delayed ? <b>Still calculating…</b>
        : <b>Calculating this board…</b>}
      {failing !== null ? (
        // The asks themselves are failing, and that is what there is to say.
        // A reading of the queue -- busy, or a board built from scratch --
        // describes a wait this page cannot see just now, and after thirty
        // seconds it would be the wrong diagnosis. Said here, not in an
        // alert: the wait goes on asking.
        <span className="pointer">{failing} Still trying.</span>
      ) : (busy || delayed) && (
        <span className="pointer">
          {busy
            ? 'It is building boards other readers asked for first.'
            : 'A board nobody has asked for recently is built from scratch.'}
          {' '}
          Change the window or the feeds to ask for one that may already be
          built.
        </span>
      )}
      {(busy || delayed || failing !== null) && onRetry && (
        <button type="button" onClick={onRetry}>Retry</button>
      )}
    </p>
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
  // Null, not zero: nobody has counted yet. "0 tickers" over a board that is
  // still being built is a measurement nobody made, and it would be the one
  // number on the line that is not a fact.
  const count = payload.rows === null ? null : payload.rows.length
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
    ...(count === null ? [] : [{
      key: 'count',
      // The baselines claim only when the board could actually survey it:
      // universalMarks() answers nothing under two rows, so a one-row board
      // saying "30d baselines" beside a row marked provisional was the head
      // contradicting its own list. Seen live 2026-08-30, one SPCX row.
      node: (count < 2
        ? <>{count} {plural(count, 'ticker', 'tickers')}</>
        : (
          <>
            {count} tickers ·{' '}
            {thinBaseline
              ? <span className="shared">{UNIVERSAL[thinBaseline]}</span>
              : '30d baselines'}
          </>
        )) as ReactNode,
    }]),
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

/** One header token and what it sorts by. `null` is a label that is not a
 *  control: `price` is a sparkline in one column and the quoted price in
 *  the other, and neither is a ranking anyone asks for. */
const TOKENS: { text: string; key: SortKey | null; name?: string }[][] = [
  [{ text: 'Ticker', key: 'ticker', name: 'ticker A to Z' }],
  [{ text: 'Talk', key: 'mentions', name: 'mentions' },
   { text: 'price', key: null }],
  [{ text: 'Score', key: 'divergence', name: 'divergence' }],
  [{ text: 'Ratio', key: 'ratio', name: 'ratio to normal' },
   { text: 'price', key: null },
   { text: 'move', key: 'move', name: 'price move' }],
  [{ text: 'Lean', key: 'lean', name: 'lean' }],
]

/** What the flat list says it is ordered by. The header token's word is
 *  too terse on its own line: "Sorted by Talk" reads as a proper noun. */
const SORT_LABEL: Record<SortKey, string> = {
  ticker: 'ticker', mentions: 'mentions', divergence: 'divergence',
  ratio: 'ratio to normal', move: 'price move', lean: 'lean',
}

/** The ledger's column header, and the board's only sort control.
 *
 *  Was `aria-hidden` decoration until 2026-09-04. Each dot-separated token
 *  is its own button, so six keys fit without a new control and without
 *  touching the grid: `.cols` is INSIDE the rows scroller and shares one
 *  grid with the rows, so anything that changes a cell's width drifts the
 *  columns off the figures under them (radar.css).
 *
 *  The aria-hidden had to go with it. A focusable button inside an
 *  aria-hidden container is reachable by keyboard and absent from the
 *  accessibility tree at the same time -- a violation rather than a
 *  cosmetic slip -- so each button now names its own action instead.
 *
 *  Hidden below 900px with the rest of the header: the rows stack there and
 *  there is no column to head. A sort in the URL is still honoured at any
 *  width; only the means of changing it is absent. */
export function SortCols({ selection, onChange }: {
  selection: Selection
  onChange: (next: Selection) => void
}) {
  function click(key: SortKey) {
    if (selection.sort !== key) {
      onChange({ ...selection, sort: key, dir: defaultDirection(key) })
    } else if (selection.dir === defaultDirection(key)) {
      onChange({ ...selection, dir: selection.dir === 'asc' ? 'desc' : 'asc' })
    } else {
      // Third click: back to the default ranking, where a reader's hand
      // already is rather than at a Reset that exists to undo furniture.
      onChange({ ...selection, sort: null, dir: 'desc' })
    }
  }

  return (
    <div className="cols">
      {TOKENS.map((group, index) => {
        const active = group.some((t) => t.key && t.key === selection.sort)
        return (
          <span key={index}
                className={index === 2 || index === 4 ? 'r' : undefined}
                aria-sort={active
                  ? (selection.dir === 'asc' ? 'ascending' : 'descending')
                  : undefined}>
            {group.map((token, at) => (
              <Fragment key={token.text + at}>
                {at > 0 && ' · '}
                {token.key ? (
                  <button type="button"
                          className={token.key === selection.sort ? 'on' : undefined}
                          aria-label={`Sort by ${token.name}`}
                          onClick={() => click(token.key as SortKey)}>
                    {token.text}
                    {/* The arrow, not the weight, is what says "this one".
                        Bold uppercase at 10.5px reads as emphasis, not as
                        state, and it cannot say WHICH WAY at all. */}
                    {token.key === selection.sort && (
                      <span className="dir" aria-hidden="true">
                        {selection.dir === 'asc' ? '↑' : '↓'}
                      </span>
                    )}
                  </button>
                ) : token.text}
              </Fragment>
            ))}
          </span>
        )
      })}
    </div>
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
export function ListPane({ payload, received, selection, selected, busy,
                          onSelect, onChange, onRetry, stalled = false,
                          retryInBanner = false, failing = null,
                          account, watching = [], onToggleWatch }: {
  payload: BoardPayload
  /** When this page received that payload, so the age on screen can keep
   *  moving between answers. Defaults to now for the suites that render this
   *  pane on its own. */
  received?: number
  selection: Selection
  selected: string | null
  busy: boolean
  onSelect: (ticker: string) => void
  onChange: (next: Selection) => void
  /** Ask again, now. Offered in the states where the wait has gone on long
   *  enough that a reader wants a button rather than patience, and beside a
   *  board that nothing else is going to ask about. */
  onRetry?: () => void
  /** Nothing is fetching a replacement for the board on screen: the last
   *  request failed and no wait is running. */
  stalled?: boolean
  /** The page's failure banner is up, with a Retry of its own. The age line
   *  then offers none: two buttons a few pixels apart for one request is
   *  one too many. */
  retryInBanner?: boolean
  /** Why the wait's own asks keep failing, once two in a row have. Said in
   *  the waiting line, which goes on asking. Null while the banner is up:
   *  a failure of the reader's own request is the banner's to say, with the
   *  page's one Retry. */
  failing?: string | null
  /** The footer matter, when this pane is where it belongs. */
  account?: ReactNode
  /** The reader's marks and how to flip one; rendered as the Watching tier
   *  and as the star beside each row. */
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
}) {
  // No board at all, as opposed to a board with nothing on it. The two states
  // have opposite meanings and, before the shared result, only one of them
  // could happen.
  const rows = payload.rows ?? []
  const waiting = payload.rows === null
  // Watched rows come from the server (`watch_rows`, built whatever the
  // floor said) -- and, until the refetch after a star lands, from the
  // board's own rows, so a fresh mark moves up at once. One row per ticker,
  // in the order the marks were made; the ranked tiers skip them.
  const marked = new Set(watching)
  const served = payload.watch_rows ?? []
  const watchRows = [
    ...served.filter((r) => marked.has(r.ticker)),
    ...rows.filter((r) => marked.has(r.ticker)
      && !served.some((w) => w.ticker === r.ticker)),
  ].sort((a, b) => watching.indexOf(a.ticker) - watching.indexOf(b.ticker))
  const ranked = rows.filter((r) => !marked.has(r.ticker))
  // The universal marks/quote facts are lifted to the header only when
  // every row actually ON SCREEN carries them -- the watched rows included,
  // not just the ranked ones the server counted them over.
  const shown = [...watchRows, ...ranked]
  const shared = universalMarks(shown)
  const quoteShared = universalQuoteFacts(shown)
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
  // ...unless the reader has marks. Then there ARE two things to tell apart,
  // and the Watching caption alone cannot do it: it is a heading that starts
  // its group, so with nothing heading the ranked rows the marks bleed
  // straight into the board (reported 2026-09-04, market shut). One caption
  // where the ownership changes, which is exactly what the tier captions are
  // for. All ranked rows are chatter with the exchange shut, so it is the
  // chatter caption that belongs here.
  const marksNeedABoundary = (
    !captions && watchRows.length > 0 && chatter.rows.length > 0)
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
          <Search rows={rows} watching={watching}
                  onPick={onSelect} onToggleWatch={onToggleWatch} />
          {/* Ops at a glance, in the corner the eye already checks for
              freshness: today's tone spend, then the stamp. */}
          <SpendMark payload={payload} />
          <AgeLine payload={payload} received={received ?? Date.now()}
                   stalled={stalled}
                   onRetry={retryInBanner ? undefined : onRetry} />
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
        <SortCols selection={selection} onChange={onChange} />
        {waiting ? (
          // No rows, and no pretending otherwise. The controls above stay
          // exactly where they were: a reader who is tired of waiting can
          // ask a different question, which is often a question the store
          // has already answered for somebody else.
          payload.failed ? (
            // The builds for this selection are failing, not merely slow.
            // An `.oops` rather than the calm waiting line, because "this is
            // taking a while" would be the wrong thing to keep saying.
            //
            // `inline` names where it is, not what it says: the same banner
            // as the page-level one, placed inside the rows scroller because
            // this one is about the board and not about the page.
            <p className="oops inline" role="alert">
              <b>This board could not be built.</b> Radar is still retrying.
              {onRetry && (
                <button type="button" onClick={onRetry}>Retry</button>
              )}
            </p>
          ) : (
            // Keyed on the question: a new selection is a new wait, and the
            // thirty seconds this component counts are how long THIS one has
            // taken. Remounting is the whole of the reset.
            <Waiting key={queryFor(selection)} payload={payload}
                     failing={failing} onRetry={onRetry} />
          )
        ) : (
        <>
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
        {selection.sort ? (
          <>
            <p className="tier">
              <b>Sorted by {SORT_LABEL[selection.sort]}</b>
              <span className="dot"> ·</span>{' '}
              <span className="what">
                {selection.dir === 'asc' ? 'smallest first' : 'largest first'}
                , across the whole board
              </span>
              {' '}
              <span className="n">{ranked.length}</span>
            </p>
            {ranked.map(renderRow)}
          </>
        ) : (
          <>
            {captions && (
              <TierCaption tier="scored" windowHours={payload.window_hours}
                           count={scored.rows.length}
                           reason={thin ? UNIVERSAL[thin] : null} />
            )}
            {scored.rows.map(renderRow)}
            {(captions || marksNeedABoundary) && chatter.rows.length > 0 && (
              <TierCaption tier="chatter" windowHours={payload.window_hours}
                           count={chatter.rows.length} reason={null} />
            )}
            {chatter.rows.map(renderRow)}
          </>
        )}
        {rows.length === 0 && (
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
        </>
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

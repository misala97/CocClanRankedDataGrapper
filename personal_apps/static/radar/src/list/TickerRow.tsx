import { chatterAreas, chatterRuns, chatterY, peak, priceRuns }
  from '../board/geometry'
import { divergence, formatPrice, humanAge, ratioShort, rankTermFor, zscore }
  from '../format'
import { queryFor } from '../api'
import type { Clause, Row, Selection, Session } from '../types'

/** The chart-row's drawing box. Stretched to the pane width by the SVG
 *  (`preserveAspectRatio="none"`), so these are proportions, not pixels. */
const BOX = { width: 300, height: 44, pad: 2 }

/** Whether this row is ranked on divergence -- chatter measured against the
 *  price move over the window -- rather than on chatter alone.
 *
 *  Eligibility is the server's safety verdict and it is checked first: a
 *  cached, mixed-version payload can carry an older `divergence` term (or a
 *  stale value) on a quote the server explicitly says cannot score, and that
 *  row must stay on chatter. The same predicate decides the tier the row sits
 *  in (ListPane.splitTiers) and the number its score cell prints, so the two
 *  cannot disagree. */
export function scoredAgainstPrice(row: Row): boolean {
  return row.quote.score_eligible
    && row.quote.score_term === 'divergence'
    && row.divergence !== null
}

/** What this row is ranked ON, which is not the same quantity in both
 *  sessions -- see leaderboard.py and the tier captions in ListPane.
 *
 *  Open and scored: divergence. Otherwise the chatter z-score -- with the
 *  market shut there is no price move to measure, and a row the server
 *  could not score (frozen tape, flat move, no quote) sits in the chatter
 *  tier and shows the quantity that tier is ordered by, not "not scored".
 *  WHY it was not scored is already on the row: the warn clause, the price
 *  figure, the flags. */
function rankedBy(row: Row) {
  const scored = scoredAgainstPrice(row)
  const term = rankTermFor(scored ? 'divergence' : 'chatter')
  return {
    ...term,
    value: scored ? divergence(row.divergence) : zscore(row.mention_z),
  }
}

/** One row of the ledger: identity, the drawing, the score, the figures,
 *  the lean -- one line, five columns, under a column header.
 *
 *  The chart-row of 2026-08-30 survives intact in the second column: the
 *  violet body is the talk, the dashed line is this ticker's own normal,
 *  and the price line rides above -- talk swelling while the line stays
 *  flat IS the board's question, visible per row. What changed in the
 *  2026-09-01 layout round is the arrangement around it: the facts that
 *  used to stack four lines high beside the drawing now run in columns, so
 *  a row is ~46px rather than ~100px and the 10-15 rows PRODUCT.md calls
 *  the majority state fit a desk without scrolling.
 *
 *  Wording still arrives as typed clauses (phrasing.py) -- the cells style
 *  by kind and never re-derive a judgement; full sentences live in the
 *  panel.
 *
 *  A link, not a button, because a ticker has a URL. Middle-click and
 *  copy-link work, and the click handler only exists to avoid a full page
 *  load for a selection the client can make itself.
 */
export function TickerRow(props: {
  row: Row
  selected: boolean
  /** Kept for the shared-scale contract with ListPane; the chart-row scales
   *  within itself, so this no longer draws anything. */
  magnitude?: number
  /** Retained for one rendering phase; each quote now owns this decision. */
  session?: Session
  /** Marks the whole board carries, which the page states once in its header
   *  instead. A mark on every row is not a mark. */
  suppress?: readonly string[]
  /** Quote facts the whole board carries -- 'fallback', 'aged' -- lifted to
   *  the header the same way. See universalQuoteFacts in ListPane. */
  quoteSuppress?: readonly string[]
  /** The age the head lifted, in seconds, when it lifted one. A row whose
   *  quote is far older than that still says so: the lift is the typical
   *  age, not a promise about every row. */
  liftedAge?: number | null
  /** The link is used outside this client too, so it carries the whole view. */
  selection?: Selection
  onSelect: (ticker: string) => void
}) {
  const { row, selected, suppress = [], quoteSuppress = [], liftedAge = null,
          selection, onSelect } = props
  const ranked = rankedBy(row)

  // Mixed-version tolerance: an embedded payload cached from before the
  // chart-row has no price series. An empty drawing is the honest render of
  // a payload that carried nothing to draw.
  const priceSeries = row.price_series ?? []
  const normalPerHour = row.normal_per_hour ?? null
  // One y scale for talk AND its normal, so the dashed line is honest about
  // where normal sits under the spike.
  const yMax = Math.max(peak(row.series), normalPerHour ?? 0)
  const areas = chatterAreas(row.series, BOX, yMax)
  const outline = chatterRuns(row.series, BOX, yMax)
  // The line draws only when there is a price STORY -- the same condition
  // under which phrasing.py writes a price clause at all. On a shut
  // exchange or a frozen tape the scattered stale fragments rendered as
  // context-free gray dashes at arbitrary heights; seen on the live DE
  // board 2026-08-30, twelve rows of chart glitch.
  const price = row.price_status === 'ok' ? priceRuns(priceSeries, BOX) : []
  // Colour is the window's verdict, not the line's own slope: green and red
  // mean price direction over the score window and nothing else. Without a
  // move to judge, the line is neutral ink.
  const priceTone = row.price_move === null ? 'var(--ink-2)'
    : row.direction === 'down' ? 'var(--down)' : 'var(--up)'

  const clause = (kind: string) =>
    row.clauses.find((c: Clause) => c.kind === kind)
  const breadth = row.clauses
    .filter((c: Clause) => c.kind === 'venues' || c.kind === 'people')
    .map((c: Clause) => c.text).join(' · ')
  const warn = clause('warn')
  const moveClause = row.clauses.find(
    (c: Clause) => c.kind.startsWith('price-'))

  const marks = row.marks.filter((mark) => !suppress.includes(mark))
  const quoteFacts = deviantQuoteFacts(row, quoteSuppress, liftedAge)

  return (
    <a className={`row${selected ? ' on' : ''}`}
       id={`radar-row-${row.ticker}`}
       href={selection
         ? `?${queryFor(selection)}&t=${encodeURIComponent(row.ticker)}`
         : `?t=${encodeURIComponent(row.ticker)}`}
       aria-current={selected ? 'true' : undefined}
       onClick={(event) => {
         // Leave modified clicks to the browser -- they mean "open elsewhere".
         if (event.metaKey || event.ctrlKey || event.shiftKey) return
         event.preventDefault()
         onSelect(row.ticker)
       }}>
      <span className="cap">
        <span className="tk">{row.ticker}</span>
        <span className="nm">{row.name ?? '—'}</span>
      </span>

      {/* Decorative to a screen reader: every quantity it draws is text in
          the cap and the facts column. */}
      <span className="chart">
        <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`}
             preserveAspectRatio="none" aria-hidden="true" focusable="false">
          <line x1="0" y1={BOX.height - BOX.pad}
                x2={BOX.width} y2={BOX.height - BOX.pad}
                stroke="var(--rule)" strokeWidth="1"
                vectorEffect="non-scaling-stroke" />
          {areas.map((d, index) => (
            <path key={`a${index}`} d={d} fill="var(--mark-soft)" />
          ))}
          {outline.map((d, index) => (
            <path key={`o${index}`} d={d} fill="none" stroke="var(--mark)"
                  strokeWidth="1.5" strokeLinejoin="round"
                  strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          ))}
          {normalPerHour !== null && (
            <line x1="0" x2={BOX.width}
                  y1={chatterY(normalPerHour, BOX, yMax)}
                  y2={chatterY(normalPerHour, BOX, yMax)}
                  stroke="var(--dim)" strokeWidth="1"
                  strokeDasharray="3 4" opacity="0.55"
                  vectorEffect="non-scaling-stroke" />
          )}
          {price.map((d, index) => (
            <path key={`p${index}`} d={d} fill="none" stroke={priceTone}
                  strokeWidth="1.5" strokeLinecap="round" opacity="0.9"
                  vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
      </span>

      {/* The number the tier is ordered by. No visible prefix: the tier
          caption and the column header name the quantity, and the 10.5px
          `DIV`/`Z` this used to carry was the smallest text on the board.
          The label survives for assistive tech, which reads no captions. */}
      <span className="score" title={ranked.why} aria-label={ranked.why}>
        <b>{ranked.value}</b>
      </span>

      <span className="facts">
        <span className="fig">
          {ratioShort(row.ratio) ?? <span className="warn">new here</span>}
          {' · '}
          {rowFigPrice(row)}
          {moveClause && (
            <>
              {' · '}
              <span className={moveClause.kind === 'price-up' ? 'up'
                : moveClause.kind === 'price-down' ? 'down' : undefined}>
                {shortMove(moveClause, row.price_move)}
              </span>
            </>
          )}
        </span>
        {warn
          ? <span className="sub warn">{warn.text}</span>
          : breadth && <span className="sub">{breadth}</span>}
      </span>

      <Lean tone={row.tone} />

      {/* Full-width, because marks are load-bearing (PRODUCT.md): crammed
          into the facts column they truncated -- "single-source · war…" on
          the live board -- and a caution the reader cannot finish reading
          is not a caution. The row grows only when it has something amber
          to say. */}
      {(marks.length > 0 || quoteFacts.length > 0) && (
        <span className="flags">
          {[...quoteFacts, ...marks].join(' · ')}
        </span>
      )}
    </a>
  )
}

/** Which way the scored talk leans: `↑4 ↓2` on a washed chip --
 *  green-tinted bullish, red-tinted bearish, gray when even or unscored.
 *
 *  The tint is Michi's 2026-08-31 call and the one sanctioned exception to
 *  green/red meaning price direction alone; it stays confined to this chip
 *  and faint, so it reads as annotation rather than verdict. The counts
 *  still carry the fact, the dominant side is bold, and equal counts show
 *  their own equality: neither bold, no tint.
 */
function Lean({ tone }: { tone: Row['tone'] }) {
  const bull = tone.bullish > tone.bearish
  const bear = tone.bearish > tone.bullish
  // Unscored renders too, on gray -- "no wording at all" is itself worth a
  // glance (Michi, 2026-08-31; supersedes the render-nothing first cut).
  return (
    <span className={`sub lean${bull ? ' bull' : bear ? ' bear' : ''}`}
          aria-label={`${tone.bullish} bullish, ${tone.bearish} bearish`}>
      {bull ? <b>{'↑'}{tone.bullish}</b>
            : <span>{'↑'}{tone.bullish}</span>}
      {' '}
      {bear ? <b>{'↓'}{tone.bearish}</b>
            : <span>{'↓'}{tone.bearish}</span>}
    </span>
  )
}

/** Quote provenance THIS row carries that the board as a whole does not.
 *
 *  The badges said "US fallback - NYSE - USD - After hours - 2740 min stale"
 *  on every row of a board where every one of those was true of every row.
 *  What the whole board shares, the header states once; what remains here is
 *  only the deviation worth noticing.
 */
/** How much older than the lifted age a quote has to be before the row says
 *  its own. Three times: an hour lifted, a two-hour quote is the same fact;
 *  a year-old one is not. */
const AGE_DEVIATION = 3

function deviantQuoteFacts(row: Row, quoteSuppress: readonly string[],
                           liftedAge: number | null): string[] {
  const facts: string[] = []
  const quote = row.quote
  if (quote.is_fallback && !quoteSuppress.includes('fallback')) {
    facts.push('US price')
  }
  if (!quoteSuppress.includes('aged')) {
    if (quote.quality === 'stale') {
      facts.push(`quote ${humanAge(quote.age_seconds)} old`)
    } else if (quote.quality === 'eod') {
      facts.push('EOD quote')
    }
  } else if ((quote.quality === 'stale' || quote.quality === 'eod')
             && liftedAge !== null && quote.age_seconds !== null
             && quote.age_seconds > AGE_DEVIATION * liftedAge) {
    // The head lifted the typical age; this quote is nothing like it.
    facts.push(`quote ${humanAge(quote.age_seconds)} old`)
  }
  // Outside the age suppression: the board lifting "quotes 1h old" says
  // nothing about a row that has no quote at all.
  if (quote.quality === 'unavailable') facts.push('no live quote')
  return facts
}

/** The price figure beside the ratio. The "closed at" prefix the old row
 *  carried is the session's fact, said once by the header; the currency code
 *  a fallback used to append is covered by the 'US price' fact (or by the
 *  header, when every row is a fallback). */
function rowFigPrice(row: Row): string {
  const price = row.quote.price
  if (price === null || price <= 0 || !row.quote.currency) return 'no quote'
  return formatPrice(price, row.quote.currency)
}

/** `+3%` from the clause's own verdict: the KIND (up/down/flat, and whether
 *  a move is worth stating at all) is phrasing.py's judgement; only the
 *  digits are formatted here. */
function shortMove(clause: Clause, fraction: number | null): string {
  if (clause.kind === 'price-flat') return 'flat'
  if (fraction === null) return clause.text
  const pct = fraction * 100
  const sign = pct > 0 ? '+' : '−'
  return `${sign}${Math.abs(pct).toFixed(Math.abs(pct) >= 10 ? 0 : 1)}%`
}

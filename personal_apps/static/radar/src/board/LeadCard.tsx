import { divergence, move, plural, signed, UNKNOWN } from '../format'
import type { ChartSpan, Mark, Row } from '../types'
import { type Box } from './geometry'
import { Marks } from './Marks'
import { SpanChart } from './SpanChart'

// The bars get almost the full height and the price line is mapped into the
// upper half, so a peak grows UP THROUGH the line rather than cowering under
// it. Two earlier splits were rendered and rejected: full height for both put
// the line's own jitter on top of the bars and the card read as a price chart
// with decoration, and a clean 62/38 band split shrank the bars to nothing --
// real chatter is peaked, so most hours are one pixel tall and only the
// crossing carries the story.
const BOX: Box = { width: 300, height: 92, pad: 11, barBand: 0.94, priceBand: 0.5 }

/** The top rows, where the argument is made rather than tabulated.
 *
 *  Chatter and price are drawn on ONE set of axes on purpose. Two stacked
 *  charts would show the same two facts and hide the relationship between
 *  them, and the relationship is the entire product: violet climbing while
 *  the price line stays flat is what "talked about, not yet priced" looks
 *  like.
 *
 *  `chatterMax` is shared across all the leads by the page, so a tall bar in
 *  one card means more mentions than a short bar in the next. Per-card
 *  auto-scaling made three unrelated charts look identically busy.
 */
export function LeadCard({ row, chatterMax, windowHours, ranked,
                          hiddenMarks = [], span }: {
  row: Row
  /** Shared across all three cards -- see SpanChart's yMax. */
  chatterMax: number
  windowHours: number
  /** 'divergence' while prices move, 'chatter' while the exchange is shut. */
  ranked: 'divergence' | 'chatter'
  /** Marks every row on the board carries, which the page states once
   *  instead. A badge repeated on all 46 rows is scenery, not a warning. */
  hiddenMarks?: Mark[]
  /** Which slice of the year the chart draws. */
  span: ChartSpan
}) {
  const byChatter = ranked === 'chatter'
  const scored = byChatter ? row.mention_z !== null : row.divergence !== null
  const headline = byChatter
    ? (row.mention_z === null ? UNKNOWN : signed(row.mention_z, 1))
    : divergence(row.divergence)
  // A frozen tape has no move to report. Printing the arithmetic difference
  // between two identical prints as "0.00%" would state that the price held
  // steady, when in fact nothing traded.
  const priced = row.price_status === 'ok' && row.price_move !== null
  const peakHour = Math.max(...row.series.map((p) => p.count ?? 0), 0)

  return (
    <article className="lead">
      <div className="lead-top">
        <div>
          <span className="lead-sym">{row.ticker}</span>
          <span className="lead-co">{row.name ?? 'Name unknown'}</span>
        </div>
        <div className={scored ? 'lead-div' : 'lead-div none'}>
          <span className="v">{headline}</span>
          {scored && (
            <span className="k">{byChatter ? 'chatter z' : 'divergence'}</span>
          )}
        </div>
      </div>

      <p className="sentence prose">
        <b>{row.mentions} {plural(row.mentions, 'mention', 'mentions')}</b>{' '}
        in {windowHours}h against {row.expected.toFixed(0)} typical, from{' '}
        <b>{row.authors} {plural(row.authors, 'person', 'people')}</b>.{' '}
        {priced
          ? <>Price <b>{move(row.price_move)}</b>.</>
          : <>Price <b>{UNKNOWN}</b>{
              row.price_status === 'closed' ? ' — the market is closed.'
                : row.price_status === 'stale' ? ' — the tape has not printed.'
                  : ' — no quote in this window.'}</>}
      </p>

      <div className="chart">
        {/* The same component the scan rows use. A card and a row draw the
            same two series over the same span, and a second implementation
            would be a second place for them to disagree. */}
        <SpanChart chart={row.chart} series={row.series} span={span}
                   box={BOX} yMax={chatterMax}
                   label={`${row.ticker}, ${span}`} />
        <div className="legend">
          <span className="keys">
            <span className="k-chat">▪ chatter</span>
            <span className="k-price">— price</span>
          </span>
          <span>{span === '24h' ? `peak ${peakHour}/h · 24h` : span}</span>
        </div>
      </div>

      <div className="lead-foot">
        {/* No coloured tone bar. Green and red are reserved for price
            direction on this surface, and a green sentiment bar beside a red
            price line is the exact ambiguity that reservation exists to
            prevent -- the counts say it in words, unambiguously. */}
        <span>
          <b>{row.tone.bullish}</b> bull · <b>{row.tone.bearish}</b> bear ·{' '}
          {row.tone.neutral} no wording
        </span>
        <span>
          <b>{row.sources.length}</b>{' '}
          {plural(row.sources.length, 'source', 'sources')}
        </span>
        <Marks marks={row.marks.filter((m) => !hiddenMarks.includes(m))} />
      </div>
    </article>
  )
}

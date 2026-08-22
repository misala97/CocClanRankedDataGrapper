import { divergence, move, plural, UNKNOWN } from '../format'
import type { Row } from '../types'
import { chatterBars, priceLine, priceRose, type Box } from './geometry'
import { Marks } from './Marks'

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
export function LeadCard({ row, chatterMax, windowHours }: {
  row: Row
  chatterMax: number
  windowHours: number
}) {
  const bars = chatterBars(row.series, BOX, chatterMax)
  const line = priceLine(row.price_series, BOX)
  const rose = priceRose(row.price_series)
  const stroke = rose ? 'var(--up)' : 'var(--down)'
  const scored = row.divergence !== null
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
          <span className="v">{divergence(row.divergence)}</span>
          {scored && <span className="k">divergence</span>}
        </div>
      </div>

      <p className="sentence prose">
        <b>{row.mentions} {plural(row.mentions, 'mention', 'mentions')}</b>{' '}
        in {windowHours}h against {row.expected.toFixed(0)} typical, from{' '}
        <b>{row.authors} {plural(row.authors, 'person', 'people')}</b>.{' '}
        {priced
          ? <>Price <b>{move(row.price_move)}</b>.</>
          : <>Price <b>{UNKNOWN}</b>{row.price_status === 'stale'
              ? ' — the tape has not printed.'
              : ' — no quote in this window.'}</>}
      </p>

      <div className="chart">
        <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} preserveAspectRatio="none"
             role="img"
             aria-label={
               `${row.ticker}: chatter and price over 24 hours. ` +
               `${row.mentions} mentions in the last ${windowHours} hours ` +
               `against ${row.expected.toFixed(0)} typical, price ` +
               `${priced ? move(row.price_move) : 'unknown'}.`
             }>
          {bars.map((bar, index) => (
            <rect key={index} x={bar.x} y={bar.y} width={bar.width}
                  height={bar.height} rx="1" fill="var(--mark)"
                  opacity={(0.32 + 0.68 * bar.ratio).toFixed(2)} />
          ))}
          {line && (
            <path d={line} fill="none" stroke={stroke} strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        <div className="legend">
          <span className="keys">
            <span className="k-chat">▪ chatter</span>
            {line
              ? <span className={rose ? 'k-price up' : 'k-price down'}>— price</span>
              : <span>no price history</span>}
          </span>
          {/* The scale is shared across all three cards, so a bar height is
              only comparable once the reader knows what full height means. */}
          <span>peak {peakHour}/h · 24h</span>
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
        <Marks marks={row.marks} />
      </div>
    </article>
  )
}

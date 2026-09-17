// The parts of "one company, in depth" that two surfaces both need.
//
// Standalone Research renders them stacked down a page; the chatter workspace
// renders the same pieces in its centre column with the candidate rail beside
// them. They are the SAME pieces, not two implementations that happen to
// agree today -- the price provenance, the chart's caption rules, the
// concentration figures and the "what this is not" paragraph are exactly the
// things two copies would eventually disagree about.
//
// Nothing here fetches. Both callers own one `useDetail` for the company they
// have open and hand the answer in, which is what keeps a selected company to
// one request no matter how many panels are reading it.
import { useContext, useEffect, useRef } from 'react'

import { Breakdown } from '../detail/Breakdown'
import { Posts } from '../detail/Posts'
import { ChartBasisNote, PriceChart, roseOverSpan } from '../detail/PriceChart'
import { sourceLabel, usdText } from '../format'
import type {
  Detail, DetailChart, PanelSpan, QuoteCurrency, Selection,
} from '../types'
import { BoardUnavailable } from '../api'
import { Unavailable } from './PageState'
import { PriceChartUnavailable } from './priceChart'
import { usePriceChart } from './queries'
import { SelectedPriceChart, selectedCaption } from './SelectedPriceChart'
import { SelectedPriceCharts } from './selectedPriceContext'

export const SPANS: PanelSpan[] = ['1D', '1W', '1M', '6M', '1Y', '3Y']

/** What the two lanes are made of, which differs by span. Copied in meaning
 *  from the board panel, because a caption claiming intraday resolution the
 *  line does not have is worse than no caption. */
const CAPTIONS: Record<PanelSpan, string> = {
  '1D': 'intraday quotes · mentions per 15 min',
  '1W': 'intraday quotes · mentions per hour',
  '1M': 'daily closes · mentions per day',
  '6M': 'daily closes · mentions per day',
  '1Y': 'daily closes · mentions per day',
  '3Y': 'daily closes · mentions per day',
}

/** 1D prices from quote snapshots when there are enough of them and from
 *  stored daily closes when there are not, so its caption cannot be a
 *  constant -- it would claim a resolution the line does not have. The board
 *  panel guards this the same way; copying the table and not the guard is how
 *  the hub came to label a daily line "intraday quotes". */
export function captionFor(chart: DetailChart): string {
  if (chart.span === '1D' && chart.priced_from === 'daily') {
    return 'daily closes · mentions per 15 min'
  }
  return CAPTIONS[chart.span]
}

/** Price and chatter, with the spans that change it and a legend that says
 *  which line is which.
 *
 *  The legend is not decoration. On the dark surface the price line is cyan
 *  because cyan is what tells it apart from the orange chatter body -- and
 *  under the previous light system that stroke carried a second fact, whether
 *  the span rose or fell. That fact is not thrown away; it is stated here, in
 *  a word as well as a colour, which is a reading a screen reader can also
 *  get and a stroke colour never was.
 */
export function ChartSection({ chart, quoteVenue, ticker, span, onSpan,
                              headingId = 'rh-chart-head', selection, visible = true }: {
  chart: DetailChart
  quoteVenue?: string | null
  ticker: string
  span: PanelSpan
  onSpan: (span: PanelSpan) => void
  headingId?: string
  /** The listing context, which the selected-session chart needs for its
   *  sources. Without it the original chart is drawn. */
  selection?: Selection
  visible?: boolean
}) {
  // The selected-session chart (MD-SELECTED-PRICE) replaces ONLY this
  // section's drawing, and only where the server offers it, for a listing
  // selection, on 1D and 1W. A company the server cannot chart that way (no
  // native-USD US primary) and a switched-off server keep the original chart.
  // Everything else on the page -- the quote, evidence, posts -- is untouched.
  const offered = useContext(SelectedPriceCharts)
  const eligible = offered && selection !== undefined
    && (span === '1D' || span === '1W')
  const priceChart = usePriceChart({ ticker, selection, span, enabled: eligible, visible })
  const refused = priceChart.error instanceof PriceChartUnavailable
    && (priceChart.error.reason === 'unsupported' || priceChart.error.reason === 'disabled')
  const selected = eligible && !refused
  const failed = selected && Boolean(priceChart.error)

  // Where the chart is looking when it does not all fit.
  //
  // Below the desk widths the drawing keeps a 620px floor and pans inside
  // this scroller, and a scroller opens at its START -- the OLDEST end. At
  // 390 that put the price axis, the last time tick, the `now` label and the
  // peak annotation all off screen, so the reader met a rising cyan line
  // with no vertical scale at all. The newest price is what a price chart is
  // for, and the caption already says to swipe back for earlier history.
  const pan = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const box = pan.current
    if (!box) return
    // Pin to the newest end, but never against the reader: only from a
    // resting position of zero, so someone who has scrolled back into
    // history is left where they put themselves.
    const toNewest = () => {
      box.style.setProperty('--chart-visible-width', `${Math.max(1, box.clientWidth - 38)}px`)
      if (box.scrollWidth > box.clientWidth && box.scrollLeft === 0) {
        box.scrollLeft = box.scrollWidth
      }
    }
    // After a frame, not during the effect: the drawing is 912px wide from
    // its own rule, but the COLUMN around it is still settling when the
    // effect first runs, so a scroll set against the old width landed back
    // at zero.
    const frame = requestAnimationFrame(toNewest)
    // And again whenever the column changes size. A window narrowed from a
    // width that fitted the whole chart into one that does not starts
    // panning at the OLDEST end, which is where the price axis is not.
    const observer = typeof ResizeObserver === 'function'
      ? new ResizeObserver(toNewest) : null
    observer?.observe(box)
    return () => { cancelAnimationFrame(frame); observer?.disconnect() }
  }, [chart])

  return (
    <section className="rh-panel rh-pad" aria-labelledby={headingId}>
      <div className="rh-sectionhead">
        <div>
          <h2 id={headingId}>Price and chatter</h2>
          <p className="muted small">
            {selected
              ? selectedCaption(failed ? undefined : priceChart.data, span, failed ? 'failed' : 'loading')
              : captionFor(chart)}
          </p>
        </div>
        <div className="rh-spans" role="group" aria-label="Chart span">
          {SPANS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={option === span}
              onClick={() => onSpan(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      {selected ? (
        <SelectedChartBody query={priceChart} ticker={ticker} span={span} />
      ) : (
        <>
          <ChartBasisNote chart={chart} quoteVenue={quoteVenue} />
          <ChartLegend chart={chart} />
          {/* Its own scroller: below the desk widths the chart pans rather
              than being scaled until its axis is unreadable. The document
              itself never scrolls sideways. */}
          <div className="rh-chartwrap" role="region"
               aria-label={`Price and chatter for ${ticker}`}
               tabIndex={0} ref={pan}>
            <PriceChart chart={chart} chatterMode="sentiment-bars" />
          </div>
          <p className="rh-caption">
            Swipe or scroll sideways for earlier history. The chart has a
            text equivalent under every figure it draws: the price and the
            window are stated above, and the counts are in the breakdown.
          </p>
        </>
      )}
    </section>
  )
}

/** The selected-session chart's own states, scoped to the chart.
 *
 *  Loading and failure never overlay a previous company's or span's chart:
 *  the query keeps no placeholder, so without an answer for THIS key there is
 *  nothing to draw but the state.
 *
 *  A failed request shows the retry state even when the cache still holds an
 *  earlier answer for this key. The key is ticker, market, sources and span;
 *  it is not the identity or the window, and after a failure nothing here can
 *  prove the earlier answer still describes them -- the session may have
 *  rolled over or the listing been remapped since it was answered. So that
 *  answer, and its "current session" and "now" wording, stays hidden until a
 *  refresh succeeds. A stale or stored-fallback answer the server sends with
 *  HTTP 200 is an answer, not a failure, and is drawn with its own labels. */
function SelectedChartBody({ query, ticker, span }: {
  query: ReturnType<typeof usePriceChart>
  ticker: string
  span: PanelSpan
}) {
  const { data, error, refetch, isFetching } = query
  if (error) {
    const message = error instanceof Error ? error.message : 'The chart did not answer.'
    return (
      <div className="rh-sp-state" role="alert">
        <p>
          {data
            ? `The latest ${span} chart for ${ticker} could not be loaded, so the earlier chart is hidden. `
            : `The ${span} chart for ${ticker} could not be loaded. `}
          {message}
        </p>
        <button type="button" className="rh-button" disabled={isFetching}
                onClick={() => void refetch()}>
          {isFetching ? 'Retrying…' : 'Retry'}
        </button>
      </div>
    )
  }
  if (!data) {
    return (
      <p className="rh-sp-state" role="status">
        Loading the {span} price and chatter chart for {ticker}…
      </p>
    )
  }
  return <SelectedPriceChart data={data} ticker={ticker} />
}

/** Which mark is which series, and which way the price went across the span.
 *
 *  Direction is claimed only where there is a line to claim it about: under
 *  two stored closes there is nothing to compare, and `PriceChart` draws no
 *  line at all. */
export function ChartLegend({ chart }: { chart: DetailChart }) {
  const priced = chart.closes.filter((value) => value !== null).length >= 2
  const rose = roseOverSpan(chart.closes)
  return (
    <p className="rh-chartlegend">
      <span className="rh-legenditem">
        <span className="rh-swatch price" aria-hidden="true" />
        Price{chart.currency ? ` (${chart.currency})` : ''}
        {priced ? (
          <span className={rose ? 'positive' : 'negative'}>
            {rose ? ' · up over this span' : ' · down over this span'}
          </span>
        ) : (
          <span className="muted"> · no stored price for this span</span>
        )}
      </span>
      <span className="rh-legenditem">
        <span className="rh-swatch chatter-tone" aria-hidden="true" />
        Chatter (mentions{perSlotWord(chart)})
      </span>
      {/* The dashed line through the chatter body is the ticker's own normal
          rate -- the thing "2.6x normal" is measured against. It was drawn
          on every span and named on none of them. Claimed only where the
          server actually supplied a baseline to draw. */}
      {chart.normal_per_slot !== null ? (
        <span className="rh-legenditem">
          <span className="rh-swatch normal" aria-hidden="true" />
          This company&rsquo;s normal rate
        </span>
      ) : null}
      {/* And the washes behind everything, which had no key at all: on 1M a
          reader got five lighter columns and no account of what they mark. */}
      <span className="rh-legenditem">
        <span className="rh-swatch band" aria-hidden="true" />
        Shaded: the market was shut or in an extended session
      </span>
    </p>
  )
}

/** The chatter lane's unit, in words rather than the axis's `/15m`. */
function perSlotWord(chart: DetailChart): string {
  if (chart.step_minutes >= 1440) return ' per day'
  return chart.step_minutes >= 60 ? ' per hour' : ' per 15 min'
}

/** Identity and provenance together, because a price without the venue,
 *  currency and time it was taken at is a number, not a fact. */
export function Quote({ detail, headingId = 'rh-quote-head' }: {
  detail: Detail
  headingId?: string
}) {
  const { identity } = detail
  const { quote } = identity
  const unavailable = quote.quality === 'unavailable' || identity.price === null
  return (
    <section className="rh-panel rh-pad" aria-labelledby={headingId}>
      <h2 id={headingId} className="rh-visually-hidden">Price</h2>
      {unavailable ? (
        <>
          <p className="rh-bigprice">Price unavailable</p>
          <p className="muted small">
            No quote was available for this listing. The chatter figures below
            are unaffected — they do not depend on a price.
          </p>
        </>
      ) : (
        <>
          <p className="rh-bigprice num">
            {formatPrice(identity.price as number, quote.currency)}
            <span className={`rh-move ${moveClass(identity.price_move)}`}>
              {identity.price_move === null
                ? ' move unknown'
                : ` ${identity.price_move > 0 ? '+' : ''}${(identity.price_move * 100).toFixed(1)}%`
                  + ` ${moveWhen(identity.price_status)}`}
            </span>
          </p>
          <p className="muted small" data-testid="rh-quote-provenance">
            {[quote.venue, quote.currency, quote.mic].filter(Boolean).join(' · ')}
            {quote.quoted_at ? ` · quoted ${berlinStamp(quote.quoted_at)}` : ''}
            {' · '}{qualityWord(quote.quality)}
          </p>
        </>
      )}
      <dl className="rh-facts">
        <div>
          <dt>Session</dt>
          <dd>{SESSION_WORD[identity.session] ?? identity.session}</dd>
        </div>
        <div>
          <dt>Market cap</dt>
          <dd>{identity.market_cap === null ? 'Not measured' : cap(identity.market_cap)}</dd>
        </div>
        <div>
          <dt>Basis</dt>
          <dd>{BASIS_WORD[quote.price_basis ?? ''] ?? 'unknown'}</dd>
        </div>
      </dl>
      {/* A quote timestamp is not the observation time of the chatter. Two
          different clocks, and conflating them is how a stale price gets read
          as a stale conversation. */}
      <p className="rh-caption">
        The quote time above is when the price was taken. It is not when the
        discussion happened.
      </p>
    </section>
  )
}

/** What is known, and what is explicitly not. Never a trade thesis. */
export function Summary({ detail, headingId = 'rh-summary-head' }: {
  detail: Detail
  headingId?: string
}) {
  const { breakdown, read } = detail
  const concentrated = breakdown.top_author_share !== null
    && breakdown.top_author_share >= 0.5
  // No venue rows at all means the evidence behind the window is not held any
  // more, not that nobody spoke.
  const noEvidence = breakdown.venues.length === 0 && breakdown.mentions === 0
  return (
    <aside className="rh-summary" aria-labelledby={headingId}>
      <h2 id={headingId}>What the figures say</h2>

      {read.length ? (
        <p className="rh-read">
          {read.map((clause, index) => (
            <span key={index} className={`rh-clause ${clause.kind}`}>
              {clause.text}{' '}
            </span>
          ))}
        </p>
      ) : (
        <p className="muted small">
          No phrase was produced for this company in this window.
        </p>
      )}

      <h3>How concentrated it is</h3>
      {noEvidence ? (
        // Not zero. The per-mention evidence has a much shorter retention than
        // the bucket totals the clauses above are counted from, so an older
        // window legitimately has totals and no rows behind them. Printing
        // "0 independent voices across 0 posts" beside a clause saying 80
        // mentions would report an absence as a measurement.
        <p className="muted small">
          No per-post evidence is held for this window. The figures above come
          from stored bucket totals, which outlive the individual mentions and
          posts behind them — so this is missing detail rather than a quiet
          company.
        </p>
      ) : (
        <ul className="rh-facts-list">
          <li>
            <strong className="num">{breakdown.voices}</strong> independent
            {breakdown.voices === 1 ? ' voice' : ' voices'} across
            {' '}<strong className="num">{breakdown.mentions}</strong>
            {breakdown.mentions === 1 ? ' post' : ' posts'}
          </li>
          <li>
            <strong className="num">{breakdown.venues.length}</strong>
            {breakdown.venues.length === 1 ? ' venue' : ' venues'}:
            {' '}{breakdown.venues.map((venue) => sourceLabel(venue.source))
                   .join(', ')}
          </li>
          <li className={concentrated ? 'warning' : undefined}>
            {breakdown.top_author_share === null
              ? 'Author concentration not measured'
              : `Loudest account is ${(breakdown.top_author_share * 100).toFixed(0)}% of the posts`}
          </li>
          {breakdown.disagreements > 0 ? (
            <li>
              <strong className="num">{breakdown.disagreements}</strong> posts
              where the wording score and the model read the tone differently
            </li>
          ) : null}
        </ul>
      )}

      <h3>What this is not</h3>
      <p className="muted small">
        A rank here is unusual discussion with price context. It is not a view
        on the company, a probability, or a recommendation to buy or sell.
      </p>
      <p className="muted small">
        The ticker above identifies the company Radar tracked in social posts.
        Whether a matching listing is available in any particular broker,
        including Scalable, has not been verified.
      </p>
    </aside>
  )
}

/** The evidence behind the window, and the posts themselves. Both components
 *  bring their own heading and their own caption, and both captions name the
 *  window -- wrapping them in a second heading said the same thing twice. */
export function EvidencePanel({ breakdown, windowHours }: {
  breakdown: Detail['breakdown']
  windowHours: number
}) {
  return (
    <section className="rh-panel rh-pad">
      <Breakdown breakdown={breakdown} windowHours={windowHours} />
    </section>
  )
}

export function PostsPanel({ detail }: { detail: Detail }) {
  return (
    <section className="rh-panel rh-pad">
      <Posts posts={detail.posts} total={detail.post_total} retentionNote />
    </section>
  )
}

/** A company the server has no panel for, in the window currently
 *  selected. Distinct from a failure, which keeps its retry. */
export function NotHere({ ticker, error, onBack, onSearch, retry, backLabel,
                         onBoard = false }: {
  ticker: string
  error: unknown
  onBack: () => void
  onSearch: () => void
  retry: () => void
  backLabel?: string
  /** Whether this company is on the board the reader is looking at. When it
   *  is, "it may have dropped off the board" contradicts a row they can see
   *  two inches away -- the panel is missing, the company is not. */
  onBoard?: boolean
}) {
  const missing = error instanceof BoardUnavailable && error.reason === 'missing'
  if (!missing) return <Unavailable error={error} retry={retry} />
  return (
    <div className="rh-empty">
      <h2>No panel for {ticker}.</h2>
      <p>
        {onBoard
          ? `${ticker} is ranked on this board, but Radar has no detail panel `
            + 'for it in the current window — the company profile '
            + 'behind the ticker is missing, not the chatter.'
          : 'Radar has no panel for that ticker in the current window. It '
            + 'may have dropped off the board, or the symbol may be spelled '
            + 'differently.'}
      </p>
      <p className="rh-empty-actions">
        <button type="button" className="rh-button primary" onClick={onBack}>
          {backLabel ?? 'Back to the list'}
        </button>
        <button type="button" className="rh-button" onClick={onSearch}>
          Search for a company
        </button>
      </p>
    </div>
  )
}

/** Which session the move belongs to, in the row's own words.
 *
 *  `today` is only true while the exchange is trading. With it shut the same
 *  percentage describes the last session, and with the tape frozen it
 *  describes whatever happened before it stopped printing -- and the row has
 *  said so since the closed-session correction. The panel beside the row now
 *  says the same thing, because they are the same number. */
function moveWhen(status: string): string {
  if (status === 'closed') return 'at close'
  if (status === 'stale') return '· no print since'
  return 'today'
}

export function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

export function formatPrice(value: number, currency: QuoteCurrency | null): string {
  return usdText(value, currency)
}

export const SESSION_WORD: Record<string, string> = {
  regular: 'open', premarket: 'pre-market', afterhours: 'after hours',
  closed: 'closed',
}

const BASIS_WORD: Record<string, string> = {
  trade: 'last trade', midpoint: 'bid/ask midpoint', close: 'closing price',
}

/** With the date. A bare clock time reads as today, which is precisely wrong
 *  for the `eod` and `stale` qualities the timestamp exists to qualify. */
function berlinStamp(iso: string): string {
  const when = new Date(iso)
  const day = when.toLocaleDateString('en-GB',
    { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Berlin' })
  const time = when.toLocaleTimeString('en-GB',
    { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })
  return `${day}, ${time} Berlin`
}

/** The provider's own classification, in words. "eod" is not one. */
const QUALITY_WORD: Record<string, string> = {
  live: 'live', delayed: 'delayed', eod: 'previous close',
  stale: 'not printing', unavailable: 'unavailable',
}

function qualityWord(quality: string): string {
  return QUALITY_WORD[quality] ?? quality
}

function cap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
  return `$${value.toLocaleString('en-US')}`
}

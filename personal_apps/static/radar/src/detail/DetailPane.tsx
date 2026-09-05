import { useEffect, useRef, useState } from 'react'
import { fetchDetail } from '../api'
import { Breakdown } from './Breakdown'
import { Identity } from './Identity'
import { Posts } from './Posts'
import { ChartBasisNote, PriceChart } from './PriceChart'
import type { Detail, DetailChart, PanelSpan, Selection } from '../types'

const SPANS: PanelSpan[] = ['1D', '1W', '1M', '6M', '1Y', '3Y']

/** The span to open on, from how long this ticker has actually been watched.
 *
 *  It was a constant, '1Y', and at 1Y the chatter bars occupy roughly the last
 *  7% of the plot: 93% of the hero chart is a price line above an empty violet
 *  lane. The CSS header says every chart here draws exactly two things and
 *  that the product IS where they disagree -- the default was hiding one of
 *  them, and on a phone the opening viewport showed price only.
 *
 *  Derived rather than moved to another constant, because chatter history
 *  GROWS. A hardcoded 1M is right this month and wrong once there is a year of
 *  it. `baseline_days` is how much history the scoring has for this ticker,
 *  which is the same thing as how long the chatter lane has anything in it.
 *
 *  Null means no baseline at all -- a ticker seen for the first time today.
 *  The shortest span is the only one with anything to show it in.
 */
export function openingSpan(baselineDays: number | null): PanelSpan {
  if (baselineDays === null) return '1W'
  if (baselineDays <= 45) return '1M'
  if (baselineDays <= 200) return '6M'
  return '1Y'
}

/** What the two lanes are made of, which is not the same on every span.
 *
 *  The long spans price from stored daily closes and count mentions per day.
 *  1D and 1W price from the 5-minute quote snapshots and count per slot --
 *  different source, different grain, and the caption has to say so or the
 *  reader assumes a daily close is being plotted every fifteen minutes.
 */
const CAPTIONS: Record<PanelSpan, string> = {
  '1D': 'intraday quotes · mentions per 15 min',
  '1W': 'intraday quotes · mentions per hour',
  '1M': 'daily closes · mentions per day',
  '6M': 'daily closes · mentions per day',
  '1Y': 'daily closes · mentions per day',
  '3Y': 'daily closes · mentions per day',
}

/** 1D prices from quote snapshots when there are enough of them and from
 *  stored daily closes when there are not, so its subtitle cannot be a
 *  constant -- it would claim intraday resolution the line does not have. */
function subtitleFor(chart: DetailChart): string {
  if (chart.span === '1D' && chart.priced_from === 'daily') {
    return 'daily closes · mentions per 15 min'
  }
  return CAPTIONS[chart.span]
}

/** The legend says the same thing as the caption, in two halves.
 *
 *  It used to be hardcoded to "daily close" and "mentions per day", which on
 *  an intraday span sat directly under a caption saying the opposite. Two
 *  labels for one line, disagreeing, is worse than neither.
 */
const LEGEND: Record<PanelSpan, { price: string; chatter: string }> = {
  '1D': { price: 'intraday quote', chatter: 'mentions per 15 min' },
  '1W': { price: 'intraday quote', chatter: 'mentions per hour' },
  '1M': { price: 'daily close', chatter: 'mentions per day' },
  '6M': { price: 'daily close', chatter: 'mentions per day' },
  '1Y': { price: 'daily close', chatter: 'mentions per day' },
  '3Y': { price: 'daily close', chatter: 'mentions per day' },
}

/** One ticker, in depth: is this real?
 *
 *  The span lives here rather than in the board controls because it changes
 *  one ticker's chart and nothing about which rows are listed. It also costs a
 *  request, unlike the old client-side span switch -- three years of closes is
 *  not something to carry per row on the chance the reader wants it.
 *
 *  Five zones, each opened by a hairline with its heading under it. Not four
 *  tracked-uppercase eyebrows down the page: that is the scaffold every
 *  generated dashboard reaches for, and it makes a section heading and a
 *  column header look like the same kind of thing.
 */
export function DetailPane({ ticker, selection, windowHours, hasRows,
                            baselineDays, fallBack, watching, onToggleWatch }: {
  ticker: string | null
  selection: Selection
  windowHours: number
  /** How many days of baseline the SELECTED row has, which decides the span
   *  the chart opens on. From the board payload, because the span has to be
   *  chosen before the panel's own request goes out. */
  baselineDays: number | null
  /** Whether the list beside this has anything in it. An empty panel next to
   *  an empty board must not invite a selection there is nothing to make. */
  hasRows: boolean
  /** Another ticker on the board that is worth trying, and how to get to it.
   *  Named rather than described: "the top of the board" was the label until
   *  the escape had to stop pointing at the top row (see BoardPage), and a
   *  button that says where it goes is right either way. */
  fallBack?: { ticker: string; go: () => void }
  /** Whether the SELECTED ticker is watched. Optional until Task 8 wires
   *  the panel's own star button. */
  watching?: boolean
  onToggleWatch?: () => void
}) {
  const [span, setSpan] = useState<PanelSpan>(() => openingSpan(baselineDays))
  const [loaded, setLoaded] = useState<{
    detail: Detail
    request: string
  } | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  // Bumped by Retry. A failed panel had no way back at all: the reader had to
  // pick a different ticker and return, and on a `?t=` link that had 404'd
  // there was no different ticker on screen to pick.
  const [attempt, setAttempt] = useState(0)
  // Bumped when a fetch RESOLVES, and used as the chart's key so the draw
  // animation restarts exactly once per chart the reader has not seen yet.
  // Keying on the ticker alone would miss a span change; keying on ticker and
  // span would miss a source change that redraws the chatter lane; keying on
  // a render would replay the animation on every hover in the panel.
  const [drawn, setDrawn] = useState(0)
  // Where focus goes when the reader picks a row.
  const landing = useRef<HTMLElement>(null)
  // The narrow layout pans the chart rather than crushing its labels. Newest
  // is the operational end of a market chart, so that is where it opens.
  const chartScroller = useRef<HTMLDivElement>(null)
  // Abort is best-effort: a request can resolve after being aborted. Only the
  // current request may publish detail or failure state.
  const requestNumber = useRef(0)
  // The ticker the panel last handed focus to. Starts at the opening ticker
  // rather than null, so the FIRST panel does not steal focus from the top of
  // the document on page load -- arriving at a page with focus already six
  // hundred pixels in is its own accessibility problem.
  const focused = useRef<string | null>(ticker)
  const request = ticker === null ? null
    : `${ticker}|${selection.market}|${selection.sources.join(',')}|${selection.window}|${span}`
  const fresh = loaded !== null && loaded.request === request
  // Stale-while-revalidate, but only within one ticker and market: a span,
  // source or window change keeps the previous chart on screen, dimmed,
  // instead of blanking the whole panel into "Loading" -- which is what a
  // span click did for the full length of the fetch (measured at 7s on 1W
  // before coverage.py; the blank was most of "the chart does not load").
  // A different ticker or market still gets the loading state: showing
  // MRNA's chart under NVDA's name would be worse than a blank.
  const detail = fresh ? loaded.detail
    : loaded !== null
        && loaded.detail.identity.ticker === ticker
        && loaded.detail.market === selection.market
      ? loaded.detail : null
  const revalidating = !fresh && detail !== null

  useEffect(() => {
    if (!detail || detail.identity.ticker !== ticker) return
    if (focused.current === ticker) return
    focused.current = ticker
    // Not `preventScroll`. On desktop the panel is already in view so this
    // does nothing; below 900px the panel sits ~1500px down the document and
    // scrolling to it is exactly what was missing -- tapping a row used to
    // change nothing on screen at all.
    landing.current?.focus()
  }, [detail, ticker])

  useEffect(() => {
    if (!drawn || !chartScroller.current) return
    chartScroller.current.scrollLeft = chartScroller.current.scrollWidth
  }, [drawn])

  useEffect(() => {
    if (!ticker) {
      requestNumber.current += 1
      setLoaded(null)
      return
    }
    const controller = new AbortController()
    const number = ++requestNumber.current
    const activeRequest = request!
    setFailed(null)
    fetchDetail(ticker, selection, span, controller.signal)
      .then((next) => {
        if (controller.signal.aborted || requestNumber.current !== number) return
        // The server answering about a different ticker than the one asked
        // for is not something to sit in a spinner over. The guard below
        // renders "Loading" for any mismatch, and a mismatch that is the
        // server's rather than a race would have loaded forever.
        if (next.identity.ticker !== ticker || next.market !== selection.market) {
          setFailed(`The board answered about ${next.identity.ticker} on ${next.market}, `
            + `not ${ticker} on ${selection.market}.`)
          return
        }
        setLoaded({ detail: next, request: activeRequest })
        setDrawn((n) => n + 1)
      })
      .catch((error: Error) => {
        // An abort is this effect being superseded, not a failure. Reporting
        // it would flash an error every time the reader moves down the list.
        if (controller.signal.aborted || requestNumber.current !== number) return
        setFailed(error.message)
      })
    return () => controller.abort()
    // `selection` is a fresh object each render in the parent; the fields it
    // holds are what actually change the request.
  }, [ticker, span, attempt, request, selection.market, selection.sources.join(','), selection.window])

  if (!ticker) {
    return (
      <main className="detail empty">
        <p role="status">
          {/* Inviting a selection from a list with nothing in it was the
              wording the empty board actually shipped with. */}
          {hasRows
            ? 'Select a ticker to see what it has been doing.'
            : 'Nothing on the board to look at.'}
        </p>
      </main>
    )
  }
  if (failed) {
    return (
      <main className="detail">
        <p role="status" className="failed">
          <b>{failed}</b>
          <span className="acts">
            <button type="button" onClick={() => setAttempt(attempt + 1)}>
              Retry {ticker}
            </button>
            {fallBack && (
              <button type="button" onClick={fallBack.go}>
                Show {fallBack.ticker} instead
              </button>
            )}
          </span>
        </p>
      </main>
    )
  }
  if (!detail || detail.identity.ticker !== ticker) {
    // The ticker check keeps the previous ticker's panel from being read as
    // this one's while its request is still in flight.
    //
    // A skeleton in the panel's own shape -- identity, the read, the chart,
    // the breakdown's head -- rather than one line of grey text, so the
    // wait looks like the thing that is coming. Decoration to a reader who
    // cannot see it, which is why the words stay, visually hidden.
    return (
      <main className="detail loading" aria-busy="true">
        <p role="status" className="aural">Loading {ticker}…</p>
        <div className="sk sk-ticker" />
        <div className="sk sk-name" />
        <div className="sk sk-line" />
        <div className="sk sk-line short" />
        <div className="sk sk-chart" />
        <div className="sk sk-table" />
      </main>
    )
  }

  const rising = firstAndLast(detail.chart.closes)

  return (
    // Keyed on the ticker, which does two things at once. The panel is the
    // scroller on desktop, so a fresh mount puts a newly picked ticker at its
    // own top instead of at the scroll position the last one was left at --
    // picking a row and landing halfway down someone else's posts was the old
    // behaviour. And the fresh mount is what runs the settle: the swap
    // between two tickers was a hard cut, on the most repeated action here.
    //
    // `tabindex=-1` and `aria-labelledby` make it a named, focusable landmark.
    // Activating a row used to be completely silent to a screen reader --
    // focus stayed on the link, the panel had no live region, and the only
    // route to the answer was tabbing through every remaining row. Focus is
    // moved here on selection instead of announcing, because moving focus
    // both says where you are and puts you there; see BoardPage.
    <main className="detail" key={ticker} tabIndex={-1}
          aria-labelledby="panel-ticker" ref={landing}>
      <a className="backboard" href={`#radar-row-${ticker}`}>Back to board</a>
      <Identity identity={detail.identity} watching={watching} onToggleWatch={onToggleWatch} />

      <p className="read">
        {detail.read.map((clause, index) => (
          <span key={index} className={`c-${clause.kind}`}>
            {clause.text}{' '}
          </span>
        ))}
      </p>

      <section className="zone" aria-labelledby="zone-chart">
        <h3 id="zone-chart">
          Price and chatter
          <span className="q">{subtitleFor(detail.chart)}</span>
          <span className="print-span" aria-hidden="true"> · {span}</span>
          <span className="spans" role="group" aria-label="Chart span">
            {SPANS.map((option) => (
              <button key={option} type="button"
                      aria-pressed={option === span}
                      onClick={() => setSpan(option)}>{option}</button>
            ))}
          </span>
        </h3>
        <ChartBasisNote chart={detail.chart}
                        quoteVenue={detail.identity.quote.venue} />
        {/* Its own scroller. Below 900px the chart pans instead of being
            scaled until its axis is unreadable -- see radar.css. */}
        <div className="chartwrap" ref={chartScroller}
             aria-busy={revalidating || undefined}>
          <PriceChart key={drawn} chart={detail.chart} />
        </div>
        {/* CSS shows this only at the widths where the chart pans. The right
            edge is the most recent price, so a chart silently cut off there
            hides the part being looked for. */}
        <p className="panhint">Swipe sideways for earlier history.</p>
        <div className="legend">
          <i><span className={`key line${rising ? '' : ' down'}`} />
            price · {LEGEND[span].price}</i>
          <i><span className="key" />chatter · {LEGEND[span].chatter}</i>
        </div>
      </section>

      <Breakdown breakdown={detail.breakdown} windowHours={windowHours} />
      <Posts posts={detail.posts} total={detail.post_total} retentionNote />
    </main>
  )
}

/** The legend's price key has to match the line, and the line is coloured by
 *  the direction of the whole visible span -- the only thing green and red are
 *  allowed to mean here. */
function firstAndLast(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  return real.length < 2 || real[real.length - 1]! >= real[0]!
}

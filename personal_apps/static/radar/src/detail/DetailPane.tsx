import { useEffect, useState } from 'react'
import { fetchDetail } from '../api'
import { Widen } from '../Widen'
import { Breakdown } from './Breakdown'
import { Identity } from './Identity'
import { Posts } from './Posts'
import { PriceChart } from './PriceChart'
import type { Detail, PanelSpan, Selection } from '../types'

const SPANS: PanelSpan[] = ['1D', '1W', '1M', '6M', '1Y', '3Y']

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
                            fallBack }: {
  ticker: string | null
  selection: Selection
  windowHours: number
  /** Whether the list beside this has anything in it. An empty panel next to
   *  an empty board must not invite a selection there is nothing to make. */
  hasRows: boolean
  /** Another ticker on the board that is worth trying, and how to get to it.
   *  Named rather than described: "the top of the board" was the label until
   *  the escape had to stop pointing at the top row (see BoardPage), and a
   *  button that says where it goes is right either way. */
  fallBack?: { ticker: string; go: () => void }
}) {
  const [span, setSpan] = useState<PanelSpan>('1Y')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  // Bumped by Retry. A failed panel had no way back at all: the reader had to
  // pick a different ticker and return, and on a `?t=` link that had 404'd
  // there was no different ticker on screen to pick.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!ticker) {
      setDetail(null)
      return
    }
    const controller = new AbortController()
    setFailed(null)
    fetchDetail(ticker, selection, span, controller.signal)
      .then((next) => {
        // The server answering about a different ticker than the one asked
        // for is not something to sit in a spinner over. The guard below
        // renders "Loading" for any mismatch, and a mismatch that is the
        // server's rather than a race would have loaded forever.
        if (next.identity.ticker !== ticker) {
          setFailed(`The board answered about ${next.identity.ticker}, `
            + `not ${ticker}.`)
          return
        }
        setDetail(next)
      })
      .catch((error: Error) => {
        // An abort is this effect being superseded, not a failure. Reporting
        // it would flash an error every time the reader moves down the list.
        if (controller.signal.aborted) return
        setFailed(error.message)
      })
    return () => controller.abort()
    // `selection` is a fresh object each render in the parent; the fields it
    // holds are what actually change the request.
  }, [ticker, span, attempt, selection.sources.join(','), selection.window])

  if (!ticker) {
    return (
      <main className="detail empty">
        <p role="status">
          {/* Inviting a selection from a list with nothing in it was the
              wording the empty board actually shipped with. */}
          {hasRows
            ? 'Select a ticker to see what it has been doing.'
            : <>Nothing on the board to look at. <Widen /></>}
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
    return (
      <main className="detail" aria-busy="true">
        <p role="status">Loading {ticker}…</p>
      </main>
    )
  }

  const rising = firstAndLast(detail.chart.closes)

  return (
    <main className="detail">
      <Identity identity={detail.identity} />

      <p className="read">
        {detail.read.map((clause, index) => (
          <span key={index} className={`c-${clause.kind}`}>
            {clause.text}{' '}
          </span>
        ))}
      </p>

      <section className="zone">
        <h3>
          Price and chatter
          <span className="q">{CAPTIONS[span]}</span>
          <span className="spans" role="group" aria-label="Chart span">
            {SPANS.map((option) => (
              <button key={option} type="button"
                      aria-pressed={option === span}
                      onClick={() => setSpan(option)}>{option}</button>
            ))}
          </span>
        </h3>
        {/* Its own scroller. Below 900px the chart pans instead of being
            scaled until its axis is unreadable -- see radar.css. */}
        <div className="chartwrap">
          <PriceChart chart={detail.chart} />
        </div>
        {/* CSS shows this only at the widths where the chart pans. The right
            edge is the most recent price, so a chart silently cut off there
            hides the part being looked for. */}
        <p className="panhint">Scroll the chart sideways for the rest of the
          span.</p>
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

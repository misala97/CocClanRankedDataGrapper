import { useEffect, useState } from 'react'
import { fetchDetail } from '../api'
import { Breakdown } from './Breakdown'
import { Identity } from './Identity'
import { Posts } from './Posts'
import { PriceChart } from './PriceChart'
import type { Detail, PanelSpan, Selection } from '../types'

const SPANS: PanelSpan[] = ['1M', '6M', '1Y', '3Y']

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
export function DetailPane({ ticker, selection, windowHours }: {
  ticker: string | null
  selection: Selection
  windowHours: number
}) {
  const [span, setSpan] = useState<PanelSpan>('1Y')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    if (!ticker) {
      setDetail(null)
      return
    }
    const controller = new AbortController()
    setFailed(null)
    fetchDetail(ticker, selection, span, controller.signal)
      .then((next) => setDetail(next))
      .catch((error: Error) => {
        // An abort is this effect being superseded, not a failure. Reporting
        // it would flash an error every time the reader moves down the list.
        if (controller.signal.aborted) return
        setFailed(error.message)
      })
    return () => controller.abort()
    // `selection` is a fresh object each render in the parent; the fields it
    // holds are what actually change the request.
  }, [ticker, span, selection.sources.join(','), selection.window])

  if (!ticker) {
    return (
      <main className="detail empty">
        <p role="status">Select a ticker to see what it has been doing.</p>
      </main>
    )
  }
  if (failed) {
    return (
      <main className="detail">
        <p role="status" className="failed">{failed}</p>
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
          <span className="q">daily closes · mentions per day</span>
          <span className="spans" role="group" aria-label="Chart span">
            {SPANS.map((option) => (
              <button key={option} type="button"
                      aria-pressed={option === span}
                      onClick={() => setSpan(option)}>{option}</button>
            ))}
          </span>
        </h3>
        <PriceChart chart={detail.chart} />
        <div className="legend">
          <i><span className={`key line${rising ? '' : ' down'}`} />
            price · daily close</i>
          <i><span className="key" />chatter · mentions per day</i>
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

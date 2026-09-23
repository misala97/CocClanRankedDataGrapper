// The candidates, as a rail rather than a table.
//
// Seven columns do not fit in 320px, and squeezing them there is how a
// comparison table becomes an unreadable one. So the rail carries the four
// facts a reader picks a candidate BY -- how far above its own normal, how
// many voices, what it costs and which way the tone leans -- and every
// qualification the server attached, because a caveat behind a click is a
// caveat that did not happen.
//
// What it drops is not thrown away: the platform count and the concrete feeds
// are in the evidence rail for whichever company is selected, and the whole
// seven-column comparison is one press away in Table mode. Same rows, same
// filters, same ordering, same response.
import { useEffect, useRef } from 'react'

import { usdText } from '../format'
import type { QuoteCurrency, Row } from '../types'
import { tonePresentation } from './chatterPresentation'
import type { TonePresentation } from './chatterPresentation'

const MARK_TEXT: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

export function CandidateList({ rows, selected, hrefFor, onSelect, labelledBy }: {
  rows: Row[]
  selected: string | null
  /** A real address for each candidate, so the row is a link a reader can
   *  middle-click, copy or open in a new tab -- not a div that only responds
   *  to a left click. */
  hrefFor: (ticker: string) => string
  onSelect: (ticker: string) => void
  labelledBy: string
}) {
  const list = useRef<HTMLUListElement>(null)
  // A shared link, or Back, can land on a candidate well down a fifty-row
  // list. The rail opens at the top, so the selected row was simply not on
  // screen -- the centre showed one company while the rail showed four
  // others and nothing was marked. Measured at 1440: the selected row 1756px
  // inside a 465px scroller, at scrollTop 0.
  //
  // Only when it is actually out of view, and never smoothly: this is where
  // the reader ARRIVED, not somewhere they asked to be taken.
  useEffect(() => {
    if (selected === null) return
    const box = list.current?.parentElement
    const row = list.current?.querySelector<HTMLElement>('.rh-candidate.selected')
    if (!box || !row) return
    const top = row.offsetTop - box.offsetTop
    const bottom = top + row.offsetHeight
    if (top < box.scrollTop) box.scrollTop = top
    else if (bottom > box.scrollTop + box.clientHeight) {
      box.scrollTop = bottom - box.clientHeight
    }
  }, [selected, rows])

  return (
    <ul className="rh-candidates" aria-labelledby={labelledBy} ref={list}>
      {rows.map((row) => (
        <li key={row.ticker}>
          <Candidate row={row} selected={row.ticker === selected}
                     href={hrefFor(row.ticker)} onSelect={onSelect} />
        </li>
      ))}
    </ul>
  )
}

/** One candidate.
 *
 *  ONE control for the whole row. A nested button -- a star, a chevron, a
 *  disclosure -- inside a link is a tab stop a reader has to pass through for
 *  every row on the list, and on a touch screen it is a target that steals
 *  the press meant for the row.
 *
 *  Selection is `aria-current`, which is the state a list of destinations
 *  actually has. `aria-selected` belongs to a listbox option, and these are
 *  links; claiming it on an anchor tells a screen reader about a widget that
 *  is not there.
 */
function Candidate({ row, selected, href, onSelect }: {
  row: Row
  selected: boolean
  href: string
  onSelect: (ticker: string) => void
}) {
  const tone = tonePresentation(row.tone)
  return (
    <a
      className={`rh-candidate${selected ? ' selected' : ''}`}
      href={href}
      aria-current={selected ? 'true' : undefined}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey) return
        event.preventDefault()
        onSelect(row.ticker)
      }}
    >
      <span className="rh-candtop">
        <span className="rh-candname">
          <span className="rh-ticker" data-testid="rh-candidate-ticker">
            {row.ticker}
          </span>
          <span className="rh-name" title={row.name ?? undefined}>
            {row.name ?? 'Name unknown'}
          </span>
        </span>
        <span className="rh-candattention">
          <Attention row={row} />
        </span>
      </span>

      <span className="rh-candbottom">
        <span className="rh-candprice">
          <Price row={row} />
        </span>
        <span className="rh-candtone">
          <ToneMark tone={tone} />
        </span>
      </span>

      {row.marks.length ? (
        <span className="rh-marks">
          {row.marks.map((mark) => (
            <span key={mark} className="rh-badge amber">
              {MARK_TEXT[mark] ?? mark}
            </span>
          ))}
        </span>
      ) : null}
    </a>
  )
}

/** How far above its own normal, with the voices behind it.
 *
 *  Two lines, not three. The contract's row is 100-124px and the rail was
 *  building 143px ones: the right column stacked six lines against the
 *  left's four and left a hollow band down the middle. `normal` and the
 *  voice count read perfectly well on one line, and the row got its height
 *  back.
 *
 *  `ratio` null is phrasing.py's guard, decided once on the server -- the
 *  client never rebuilds it from mentions and expected. */
function Attention({ row }: { row: Row }) {
  const voices = `${row.authors} ${row.authors === 1 ? 'voice' : 'voices'}`
  return (
    <>
      {row.ratio === null ? (
        <>
          <strong aria-hidden="true">—</strong>
          <span className="rh-sub">New here · {voices}</span>
        </>
      ) : (
        <>
          <strong className="num">{row.ratio.toFixed(1)}×</strong>
          <span className="rh-sub">normal · {voices}</span>
        </>
      )}
    </>
  )
}

function Price({ row }: { row: Row }) {
  const { quote } = row
  if (quote.quality === 'unavailable' || row.price === null) {
    return (
      <>
        <strong aria-hidden="true">—</strong>
        <span className="rh-sub">Price unavailable</span>
      </>
    )
  }
  const move = row.price_move
  return (
    <>
      <strong className="num">{formatPrice(row.price, quote.currency)}</strong>
      <span className={`rh-sub num ${moveClass(move)}`}>
        {move === null
          ? 'Move unknown'
          : `${move > 0 ? '+' : ''}${(move * 100).toFixed(1)}%`}
        {move !== null && tapeNote(row.price_status)
          ? <span className="muted"> · {tapeNote(row.price_status)}</span>
          : null}
      </span>
    </>
  )
}

/** Tone as a share of the directional sample, with the sample size beside it.
 *
 *  The percentage and the bar have ONE denominator, and the bar is never the
 *  only thing saying which way it leans -- the label above it is the reading.
 *  The exact counts and what the residual holds are in the evidence rail for
 *  the selected company; repeating them on every row is what made the
 *  original list tall. */
function ToneMark({ tone }: { tone: TonePresentation }) {
  const proportional = tone.bull !== null && tone.bear !== null
  return (
    <>
      <strong className={tone.kind === 'directional' ? 'num' : 'rh-tonequiet'}>
        {tone.label}
      </strong>
      {tone.kind !== 'unavailable' ? (
        <span className="rh-tonebar" aria-hidden="true">
          {proportional && tone.bull! > 0
            ? <span className="bull" style={{ flexGrow: tone.bull! }} /> : null}
          {proportional && tone.bear! > 0
            ? <span className="bear" style={{ flexGrow: tone.bear! }} /> : null}
          {!proportional ? <span className="flat" style={{ flexGrow: 1 }} /> : null}
        </span>
      ) : null}
      {tone.sample ? <span className="rh-sub">{tone.sample}</span> : null}
    </>
  )
}

/** What to say about a move the exchange is not currently confirming. The
 *  same rule the table uses: `Move unknown` is reserved for the one case that
 *  really is unknown, decided in `quotes.moves_for`.
 *
 *  `no print since` was a sentence with its object missing -- the row read
 *  `0.0% · no print since` and simply stopped. The row has no date to put
 *  there; the panel's quote line does. So it says what is true without
 *  promising a word it cannot supply. */
function tapeNote(status: Row['price_status']): string | null {
  if (status === 'closed') return 'at close'
  if (status === 'stale') return 'tape not printing'
  return null
}

function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

function formatPrice(value: number, currency: QuoteCurrency | null): string {
  return usdText(value, currency)
}

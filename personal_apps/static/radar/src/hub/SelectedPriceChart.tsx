// The selected-session chart (MD-SELECTED-PRICE): price and chatter for ONE
// explicit window, on one time axis.
//
// Its own renderer rather than a mode of PriceChart. That chart draws evenly
// spaced slots and means something to other consumers; this one places every
// price observation and every chatter slot by its own UTC instant, so the two
// line up because they share the axis, not an index. It computes no return,
// no direction and no normal rate: the payload carries none of them.
//
// What it must say rather than draw: which session(s), whether a price point
// is a bar close or a stored observation, whether a bar was still open when it
// was received, whether a count is observed, partial or unknown, where the
// price came from and how old it is, and that the adjustment basis is unknown.
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'

import { TONE_COLORS } from '../detail/ChatterHistogram'
import type { PriceChartResponse, PricePoint, ToneKey } from './priceChart'
import { TONE_KEYS } from './priceChart'
import {
  AXIS_Y, AXIS_Y2, BARS_TOP, CHART_H, CHART_W, FLOOR, PLOT_R, PRICE_BOTTOM, PRICE_TOP,
  ageWord, areaPathOf, bandAt, bandBoxes, berlinClock, berlinStamp, berlinZone, chatterBars,
  coverageWord, frameOf, instant, intervalWord, latestValid, money, newYorkDate, pathOf,
  peakCount, pointsInSlot, priceExtent, priceKindWord, priceSegments, priceY,
  sessionDateLabel, slotIndexAt, sourceWord, toneFor, xOf,
} from './selectedPriceGeometry'
import './selected-price.css'

const TONE_WORD: Record<ToneKey, string> = {
  bullish: 'bullish', bearish: 'bearish', neutral: 'neutral / mixed',
  unjudged: 'unjudged', unavailable: 'tone unavailable',
}

const STATE_WORD: Record<string, string> = {
  regular: 'regular session', premarket: 'pre-market', afterhours: 'after hours',
  closed: 'market closed',
}

/** How much room the panned chart keeps to the RIGHT of the latest observation
 *  when it has to choose that over the gutter, so the newest price is not
 *  flush against the edge. CSS pixels, not drawing units. */
const TRAILING_PX = 96

/** Where a panned chart opens, or null when the drawing fits and nothing needs
 *  placing.
 *
 *  Two things want the right-hand end: the price axis and the window-end label
 *  live past the plot, and the latest actual observation is what a price chart
 *  is for. On a 1D window -- which runs to the extended close -- a listing that
 *  stopped trading at the bell puts them hours apart. So: take the rightmost
 *  position while it still leaves half a viewport of line to the left of the
 *  latest observation, and otherwise keep the observation on screen and let the
 *  gutter be scrolled to. Neither branch ever pushes the latest observation
 *  out of view. */
export function panOffset({ scrollWidth, clientWidth, drawingWidth, latestX }: {
  scrollWidth: number
  clientWidth: number
  drawingWidth: number
  latestX: number | null
}): number | null {
  const maxLeft = scrollWidth - clientWidth
  if (maxLeft <= 0) return null
  if (latestX === null) return maxLeft
  const latest = (latestX * drawingWidth) / CHART_W
  if (maxLeft <= latest - clientWidth / 2) return maxLeft
  return Math.round(Math.max(0, Math.min(maxLeft, latest + TRAILING_PX - clientWidth)))
}

const ACQUISITION_WORD: Record<string, string> = {
  ready: 'provider chart ready', pending: 'provider chart still loading',
  backoff: 'provider chart paused', busy: 'provider chart busy',
  disabled: 'provider chart switched off', unavailable: 'provider chart unavailable',
}

export function windowTitle(data: PriceChartResponse): string {
  if (data.span === '1W') return data.window.partial ? '5 sessions · today partial' : '5 sessions'
  return data.window.partial ? 'Current session so far' : 'Last completed session'
}

function sessionsWord(data: PriceChartResponse): string {
  const dates = data.window.session_dates
  if (dates.length === 1) return sessionDateLabel(dates[0]!)
  return `${sessionDateLabel(dates[0]!)} – ${sessionDateLabel(dates[dates.length - 1]!)}`
}

export function selectedCaption(data: PriceChartResponse | undefined, span: string,
                                missing: 'loading' | 'failed' = 'loading'): string {
  if (!data) {
    const state = missing === 'failed' ? 'not loaded' : 'loading'
    return span === '1W' ? `Five sessions · ${state}` : `Current or last session · ${state}`
  }
  const price = data.price ? priceKindWord(data.price) : 'no price'
  return `${windowTitle(data)} · ${price} · mentions per ${data.chatter.step_minutes === 15 ? '15 min' : 'hour'}`
}

function barWords(point: PricePoint, kind: string): string {
  if (kind === 'stored_quote') return `stored quote at ${berlinClock(point.at)}`
  if (kind === 'daily_close') return 'stored daily close for that session'
  const provisional = point.provisional
    ? `, provisional: the bar was still open when received at ${berlinClock(point.at)}` : ''
  return `bar ${berlinClock(point.start)}–${berlinClock(point.end)} close${provisional}`
}

export function slotReadout(data: PriceChartResponse, index: number): string {
  const slot = data.chatter.slots[index]
  if (!slot) return ''
  const words: string[] = [
    `${berlinStamp(slot.start)}–${berlinClock(slot.end)} ${berlinZone(slot.start)}`,
  ]
  const unit = slot.count === 1 ? 'mention' : 'mentions'
  words.push(slot.count === null
    ? 'mentions unknown: nothing valid was recorded, which is not zero'
    : `${slot.count} ${unit}, ${slot.coverage === 'observed' ? 'observed' : 'partial coverage'}`)
  if (slot.truncated) words.push('a source was truncated')
  if (slot.config_transition) words.push('source configuration changed')
  if (slot.overlap_ambiguous) words.push('bare Reddit and a subreddit overlap, so the total is withheld')
  const tone = toneFor(slot, data.chatter.tone.slots[index])
  if (tone && slot.count) {
    words.push(TONE_KEYS.filter((key) => tone[key] > 0)
      .map((key) => `${TONE_WORD[key]} ${tone[key]}`).join(', ') + ' (recorded judgments)')
  }
  const price = data.price
  if (!price) {
    words.push('no price observation in this window')
  } else {
    const inSlot = pointsInSlot(price.points, slot)
    const valid = latestValid(inSlot)
    if (valid && valid.value !== null) {
      const interval = price.kind === 'bar_close' ? `${intervalWord(price.interval_seconds)} ` : ''
      words.push(`price ${money(valid.value)}, ${interval}${barWords(valid, price.kind)}, `
        + `${sourceWord(price.source)}, adjustment basis ${price.adjustment_basis}`)
    } else if (inSlot.length) {
      words.push('a price bar without a valid close here: a gap')
    } else {
      const state = bandAt(data.window.bands, instant(slot.start))
      words.push(`no price bar in this interval${state ? ` (${STATE_WORD[state]})` : ''}`)
    }
  }
  return words.join('; ')
}

export function chartSummary(data: PriceChartResponse): string {
  const slots = data.chatter.slots
  const observed = slots.filter((s) => s.coverage === 'observed').length
  const partial = slots.filter((s) => s.coverage === 'partial').length
  const unknown = slots.filter((s) => s.coverage === 'unknown').length
  const counted = slots.reduce((sum, s) => sum + (s.count ?? 0), 0)
  const step = data.chatter.step_minutes === 15 ? '15-minute' : 'hourly'
  const when = data.span === '1W'
    ? `sessions ${sessionsWord(data)}, US Eastern modeled calendar${data.window.partial ? ', today partial' : ''}`
    : `session ${sessionsWord(data)}, US Eastern modeled calendar, extended hours${data.window.partial ? ' so far' : ''}`
  let price = 'no price observation inside this window'
  if (data.price) {
    const valid = data.price.points.filter((p) => p.value !== null)
    const latest = latestValid(data.price.points)
    const segments = priceSegments(data.price.points, frameOf(data.window))
    const coverage = coverageWord(data.price)
    price = `${valid.length} ${priceKindWord(data.price)} from ${sourceWord(data.price.source)}`
      + `${data.price.fallback ? ' (stored fallback)' : ''} in ${segments.length} `
      + `${segments.length === 1 ? 'segment' : 'segments'}`
      + `${coverage ? `, ${coverage}` : ''}`
    if (latest && latest.value !== null) {
      price += `; latest ${money(latest.value)} at ${berlinStamp(latest.at)} ${berlinZone(latest.at)}`
        + `${latest.provisional ? ' (provisional)' : ''}`
    }
  }
  return `${data.identity.ticker}, ${when}. Price: ${price}. Chatter: ${slots.length} ${step} `
    + `slots, ${observed} observed, ${partial} partial, ${unknown} unknown, ${counted} mentions counted.`
}

/** Where the price came from, in one line of words. */
function provenance(data: PriceChartResponse): { text: string; stale: boolean } {
  const { price, identity, acquisition } = data
  if (!price) {
    return { text: `No price inside this window · ${ACQUISITION_WORD[acquisition.state]}`
      + `${acquisition.reason ? ` (${acquisition.reason})` : ''}`, stale: false }
  }
  const listing = `${identity.venue} (${identity.mic}) · USD`
  // How much of the window the source reported rides on this line rather than
  // a paragraph of its own: at phone width every extra paragraph pushes the
  // drawing further off the screen.
  const covered = price.expected_intervals === null || price.expected_intervals <= 0 ? ''
    : ` · ${price.observations} of ${price.expected_intervals} reported`
  if (!price.fallback) {
    const age = price.cache_age_seconds === null ? '' : ` · received ${ageWord(price.cache_age_seconds)} ago`
    return { text: `${sourceWord(price.source)} · ${listing} · ${priceKindWord(price)}${covered}${age}`
      + `${price.stale ? ' · stale' : ''}`, stale: price.stale }
  }
  const received = price.received_at ? ` · stored ${berlinStamp(price.received_at)}` : ''
  return { text: `${sourceWord(price.source)} · ${listing} · ${priceKindWord(price)} · fallback while the `
    + `${ACQUISITION_WORD[acquisition.state]}${received}`, stale: price.stale }
}

function Header({ data }: { data: PriceChartResponse }) {
  const source = provenance(data)
  const basis = data.price
    ? `Adjustment basis ${data.price.adjustment_basis}. `
      + (data.price.kind === 'bar_close'
        ? 'Each point is a bar close at the bar’s end; the line between two of them is a '
          + 'guide, not a price.'
        : data.price.kind === 'stored_quote'
          ? 'Each point is a stored quote at its own event time.'
          : 'Each point is a stored daily close at the modeled regular close.')
    : null
  return (
    <div className="rh-sp-meta">
      <p>
        <strong>{windowTitle(data)}</strong>
        {' · '}{sessionsWord(data)} (US Eastern, modeled calendar)
      </p>
      <p className={source.stale ? 'rh-sp-stale' : undefined} data-testid="rh-sp-provenance">
        {source.text}
      </p>
      {basis ? <p>{basis}</p> : null}
      <p className="rh-sp-legend" aria-label="Chart legend">
        <span><i className="price" />Price (USD)</span>
        {TONE_KEYS.map((key) => (
          <span key={key}><i style={{ background: TONE_COLORS[key] }} />{TONE_WORD[key]}</span>
        ))}
        <span><i className="unknown" />count unknown</span>
        <span><i className="band" />market closed or extended session</span>
      </p>
    </div>
  )
}

interface Tick { x: number; label: string; anchor: 'start' | 'middle' | 'end' }

function ticks(data: PriceChartResponse): Tick[] {
  const frame = frameOf(data.window)
  if (frame.to <= frame.from) return []
  if (data.span === '1W') {
    return data.window.bands.filter((b) => b.state === 'regular').map((band) => ({
      x: xOf(frame, instant(band.from)), label: newYorkDate(band.from), anchor: 'start' as const,
    })).filter((tick) => tick.x < PLOT_R - 70)
  }
  const out: Tick[] = []
  const hour = 3_600_000
  for (let t = Math.ceil(frame.from / (2 * hour)) * 2 * hour; t < frame.to; t += 2 * hour) {
    const x = xOf(frame, t)
    if (x > 20 && x < PLOT_R - 20) {
      out.push({ x, label: berlinClock(new Date(t).toISOString()), anchor: 'middle' })
    }
  }
  return out
}

export function SelectedPriceChart({ data, ticker }: { data: PriceChartResponse; ticker: string }) {
  const summaryId = useId()
  // One gradient per mounted chart: two of them share a page (standalone
  // Research and the chatter workspace), and a duplicate SVG id would make
  // one of them paint with the other's fill.
  const fillId = `${useId().replace(/[^\w-]/g, '')}-price-area`
  const frame = useMemo(() => frameOf(data.window), [data])
  const points = data.price?.points ?? []
  const segments = useMemo(() => priceSegments(points, frame), [points, frame])
  const bars = useMemo(() => chatterBars(data.chatter.slots, data.chatter.tone.slots, frame),
    [data, frame])
  const bands = useMemo(() => bandBoxes(data.window.bands, frame), [data, frame])
  const extent = priceExtent(points)
  const latest = latestValid(points)
  const peak = peakCount(data.chatter.slots)
  const [selected, setSelected] = useState<number | null>(null)
  const [hovered, setHovered] = useState<number | null>(null)
  const slots = data.chatter.slots
  const active = hovered ?? selected
  const waiting = frame.to <= frame.from
  const endLabel = data.window.partial
    ? `now ${berlinClock(data.window.to)}` : `${berlinClock(data.window.to)} session end`

  // A new answer for another window must not keep a slot index from the old one.
  useEffect(() => {
    setSelected((current) => (current !== null && current >= slots.length ? null : current))
    setHovered(null)
  }, [slots.length])

  // Below the desk widths the drawing pans rather than being squeezed until
  // its axis is unreadable, and it is placed ONCE per chart -- a new ticker or
  // span -- and then left to the reader.
  //
  // `placedFor` remembers which chart has been placed; `readerMoved` records
  // that the reader has taken it over. Neither is inferred from scrollLeft: a
  // reader who scrolls all the way LEFT to see the session open sits at
  // exactly 0, which an "is it still at zero?" test cannot tell apart from a
  // chart nobody has placed yet -- and the 60-second refresh would then drag
  // them back every minute.
  const pan = useRef<HTMLDivElement>(null)
  const latestX = latest && extent ? xOf(frame, instant(latest.at)) : null
  const chart = `${ticker}|${data.span}`
  const placedFor = useRef<string | null>(null)
  const readerMoved = useRef(false)
  const placing = useRef(false)
  useEffect(() => {
    const box = pan.current
    if (!box) return
    if (placedFor.current !== chart) readerMoved.current = false
    const place = () => {
      if (readerMoved.current) return
      const drawing = box.querySelector('svg')?.getBoundingClientRect().width ?? box.scrollWidth
      const wanted = panOffset({ scrollWidth: box.scrollWidth, clientWidth: box.clientWidth,
                                 drawingWidth: drawing, latestX })
      if (wanted === null) return
      placedFor.current = chart
      if (Math.round(box.scrollLeft) === wanted) return
      // The assignment fires a scroll event of its own; it is not the reader's.
      placing.current = true
      box.scrollLeft = wanted
    }
    const onScroll = () => {
      if (placing.current) {
        placing.current = false
        return
      }
      readerMoved.current = true
    }
    box.addEventListener('scroll', onScroll, { passive: true })
    const frameId = requestAnimationFrame(place)
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(place) : null
    observer?.observe(box)
    return () => {
      cancelAnimationFrame(frameId)
      observer?.disconnect()
      box.removeEventListener('scroll', onScroll)
    }
  }, [chart, data, latestX])

  const move = (next: number) => {
    if (!slots.length) return
    setSelected(Math.max(0, Math.min(slots.length - 1, next)))
  }
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = selected ?? slots.length - 1
    const page = data.chatter.step_minutes === 15 ? 4 : 24
    const actions: Record<string, () => void> = {
      ArrowLeft: () => move(selected === null ? slots.length - 1 : current - 1),
      ArrowRight: () => move(selected === null ? slots.length - 1 : current + 1),
      PageUp: () => move(current - page),
      PageDown: () => move(current + page),
      Home: () => move(0),
      End: () => move(slots.length - 1),
    }
    if (event.key === 'Escape') {
      setSelected(null)
      setHovered(null)
      return
    }
    const action = actions[event.key]
    if (action) {
      event.preventDefault()
      action()
    }
  }
  const slotFromPointer = (event: PointerEvent<SVGSVGElement>): number | null => {
    const svg = event.currentTarget
    const ctm = typeof svg.getScreenCTM === 'function' ? svg.getScreenCTM() : null
    if (!ctm || waiting) return null
    const x = new DOMPoint(event.clientX, event.clientY).matrixTransform(ctm.inverse()).x
    const at = frame.from + (Math.max(0, Math.min(PLOT_R, x)) / PLOT_R) * (frame.to - frame.from)
    const index = slotIndexAt(slots, at)
    return index >= 0 ? index : null
  }

  const activeBar = active !== null ? bars[active] : undefined
  const activePoints = active !== null && slots[active] ? pointsInSlot(points, slots[active]!) : []
  const activePoint = latestValid(activePoints)
  const stepUnit = data.chatter.step_minutes === 15 ? '/15m' : '/h'

  return (
    <div className="rh-sp">
      <Header data={data} />
      <div className="rh-chartwrap rh-sp-wrap" ref={pan}>
        <div className="rh-sp-canvas" role="group" tabIndex={0} onKeyDown={onKeyDown}
             aria-label={`Price and chatter intervals for ${ticker}. Use the arrow keys, `
               + 'Page Up, Page Down, Home and End to read each interval; Escape clears.'}
             aria-describedby={summaryId}>
          <svg className="rh-sp-svg" viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img"
               aria-label={`Selected-session price and chatter chart for ${ticker}`}
               onPointerMove={(event) => setHovered(slotFromPointer(event))}
               onPointerLeave={() => setHovered(null)}
               onClick={(event) => {
                 const index = slotFromPointer(event as unknown as PointerEvent<SVGSVGElement>)
                 if (index !== null) setSelected(index)
               }}>
            <g aria-hidden="true">
              {bands.map((band) => band.state === 'regular' || band.width <= 0 ? null : (
                <rect key={`${band.state}-${band.from}`} className={`band band-${band.state}`}
                      x={band.x} y={PRICE_TOP - 8} width={band.width} height={FLOOR - PRICE_TOP + 8} />
              ))}
              <line className="rule" x1={0} x2={PLOT_R} y1={PRICE_BOTTOM + 12} y2={PRICE_BOTTOM + 12} />
              <line className="floor" x1={0} x2={PLOT_R} y1={FLOOR} y2={FLOOR} />
              {ticks(data).map((tick) => (
                <g key={`${tick.label}-${tick.x}`}>
                  <line className="tick" x1={tick.x} x2={tick.x} y1={FLOOR} y2={FLOOR + 5} />
                  <text className="ax" x={tick.x + (tick.anchor === 'start' ? 3 : 0)} y={AXIS_Y}
                        textAnchor={tick.anchor}>{tick.label}</text>
                </g>
              ))}
              <text className="ax" x={0} y={AXIS_Y2}>
                {data.span === '1D'
                  ? `${sessionDateLabel(data.window.session_dates[0]!)} ${berlinClock(data.window.from)}`
                  : `from ${berlinStamp(data.window.from)}`}
              </text>
              <text className="ax" x={PLOT_R} y={AXIS_Y2} textAnchor="end">
                {endLabel} {berlinZone(data.window.to)}
              </text>
              {extent ? (
                <>
                  <text className="ax" x={PLOT_R + 8} y={PRICE_TOP + 4}>{money(extent.high)}</text>
                  <text className="ax" x={PLOT_R + 8} y={PRICE_BOTTOM + 4}>{money(extent.low)}</text>
                </>
              ) : (
                <text className="ax rh-sp-empty" x={PLOT_R / 2} y={(PRICE_TOP + PRICE_BOTTOM) / 2}
                      textAnchor="middle">
                  {waiting ? 'The session has only just begun: nothing to plot yet'
                    : 'No price observation inside this window'}
                </text>
              )}
              <text className="ax" x={PLOT_R + 8} y={BARS_TOP + 4}>{peak}{stepUnit}</text>
            </g>

            <g className="bars" aria-hidden="true">
              {bars.map((bar) => {
                if (bar.count === null) {
                  return <line key={bar.index} className="unknown" x1={bar.left + 0.5}
                               x2={Math.max(bar.left + 0.5, bar.right - 0.5)} y1={FLOOR - 2} y2={FLOOR - 2} />
                }
                const top = bar.stacks.length ? Math.min(...bar.stacks.map((s) => s.y)) : FLOOR
                return (
                  <g key={bar.index}>
                    {bar.stacks.map((stack) => (
                      <rect key={stack.key} x={bar.x} y={stack.y} width={bar.width}
                            height={Math.max(stack.height, 0.5)} data-tone={stack.key}
                            fill={TONE_COLORS[stack.key]} />
                    ))}
                    {bar.count === 0 ? (
                      <line className="zero" x1={bar.x} x2={bar.x + bar.width} y1={FLOOR - 1} y2={FLOOR - 1} />
                    ) : null}
                    {bar.partial ? (
                      <rect className="partial" x={bar.x} y={top - 3} width={bar.width}
                            height={Math.max(FLOOR - top + 3, 3)} />
                    ) : null}
                  </g>
                )
              })}
            </g>

            {/* One line and one baseline-closing area per HARD segment, and a
                single marker on the latest actual observation. No dot at
                every reported price: on a dense session that is a cloud, and
                on a sparse one it hides the shape the chart is for. A segment
                with one observation has nothing to connect, so it keeps its
                own dot. */}
            <g className="price" aria-hidden="true">
              <defs>
                <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                  <stop className="rh-sp-area-top" offset="0%" />
                  <stop className="rh-sp-area-foot" offset="100%" />
                </linearGradient>
              </defs>
              {segments.map((segment) => segment.points.length > 1 ? (
                <path key={`a${segment.points[0]!.index}`} className="rh-sp-area"
                      d={areaPathOf(segment.points, PRICE_BOTTOM)} fill={`url(#${fillId})`} />
              ) : null)}
              {segments.map((segment) => segment.points.length > 1 ? (
                <path key={`l${segment.points[0]!.index}`} className="price-line"
                      d={pathOf(segment.points)} />
              ) : null)}
              {segments.map((segment) => segment.points.length === 1 ? (
                <circle key={`d${segment.points[0]!.index}`} className="price-dot"
                        cx={segment.points[0]!.x} cy={segment.points[0]!.y} r={3.2} />
              ) : null)}
              {latest && extent ? (
                <circle className={latest.provisional ? 'price-provisional' : 'price-last'}
                        cx={xOf(frame, instant(latest.at))}
                        cy={priceY(latest.value as number, extent.low, extent.high)}
                        r={latest.provisional ? 4.2 : 3.8} />
              ) : null}
            </g>

            {activeBar ? (
              <g aria-hidden="true">
                <rect className="active" x={activeBar.left} y={PRICE_TOP - 8}
                      width={Math.max(activeBar.right - activeBar.left, 1)} height={FLOOR - PRICE_TOP + 8} />
                {activePoint && extent && activePoint.value !== null ? (
                  <circle className="price-active" cx={xOf(frame, instant(activePoint.at))}
                          cy={priceY(activePoint.value, extent.low, extent.high)} r={4.5} />
                ) : null}
              </g>
            ) : null}
          </svg>
        </div>
      </div>
      <p className="rh-sp-readout" aria-live="polite" data-testid="rh-sp-readout">
        {active !== null
          ? slotReadout(data, active)
          : 'Focus the chart, then use the arrow keys (or hover) to read each interval’s '
            + 'price bar, mention count, coverage and provenance.'}
      </p>
      <p id={summaryId} className="rh-sp-summary">{chartSummary(data)}</p>
      <p className="rh-caption">
        Counts here cover this chart’s own window and slots. The evidence and posts
        below cover the board’s window, which is a different period. No return or
        direction is computed from this series.
      </p>
      {data.warnings.length ? (
        <details className="rh-sp-notes">
          <summary>Data notes ({data.warnings.length})</summary>
          <ul>{data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}
    </div>
  )
}

// Pure geometry and wording for the selected-session chart.
//
// Everything is placed by its own UTC instant on ONE linear time axis from
// window.from to window.to. Price points and chatter slots are independent
// arrays of different lengths; they line up because they share the axis, never
// because they share an index. Nothing here resamples, interpolates or bridges.
import type {
  ChatterSlot, PriceBand, PricePoint, PriceSeries, ToneKey, ToneSlot,
} from './priceChart'
import { TONE_KEYS } from './priceChart'

export const CHART_W = 912
/** The plot ends here; the rest is the price gutter, as on the older chart. */
export const PLOT_R = 848
export const PRICE_TOP = 16
export const PRICE_BOTTOM = 150
export const BARS_TOP = 178
export const FLOOR = 300
export const AXIS_Y = 318
/** The window's own start and end labels, on a line of their own so a tick
 *  can never print over them. */
export const AXIS_Y2 = 336
export const CHART_H = 344

export interface Frame { from: number; to: number }

export const instant = (iso: string): number => Date.parse(iso)

export function frameOf(window: { from: string; to: string }): Frame {
  return { from: instant(window.from), to: instant(window.to) }
}

/** x for an instant; the whole plot collapses to 0 on a zero-length window. */
export function xOf(frame: Frame, at: number): number {
  const span = frame.to - frame.from
  if (!(span > 0)) return 0
  return Math.min(PLOT_R, Math.max(0, ((at - frame.from) / span) * PLOT_R))
}

export function priceExtent(points: PricePoint[]): { low: number; high: number } | null {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null)
  if (!values.length) return null
  return { low: Math.min(...values), high: Math.max(...values) }
}

export function priceY(value: number, low: number, high: number): number {
  const range = high - low
  if (!(range > 0)) return (PRICE_TOP + PRICE_BOTTOM) / 2
  return PRICE_TOP + (1 - (value - low) / range) * (PRICE_BOTTOM - PRICE_TOP)
}

export interface PlotPoint { x: number; y: number; index: number; point: PricePoint }

/** Connected runs and lone dots. A null value or `break_before` ends a run;
 *  a run of one is a dot with its own timestamp, never an invisible line. */
export function priceRuns(points: PricePoint[], frame: Frame):
  { lines: PlotPoint[][]; dots: PlotPoint[] } {
  const extent = priceExtent(points)
  if (!extent) return { lines: [], dots: [] }
  const runs: PlotPoint[][] = []
  let current: PlotPoint[] = []
  const flush = () => {
    if (current.length) runs.push(current)
    current = []
  }
  points.forEach((point, index) => {
    if (point.value === null) {
      flush()
      return
    }
    if (point.break_before) flush()
    current.push({
      x: xOf(frame, instant(point.at)),
      y: priceY(point.value, extent.low, extent.high),
      index, point,
    })
  })
  flush()
  return {
    lines: runs.filter((run) => run.length > 1),
    dots: runs.filter((run) => run.length === 1).map((run) => run[0]!),
  }
}

export function pathOf(run: PlotPoint[]): string {
  return run.map((p, n) => `${n ? 'L' : 'M'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')
}

export interface Stack { key: ToneKey; y: number; height: number; value: number }

export interface Bar {
  index: number
  left: number
  right: number
  x: number
  width: number
  count: number | null
  stacks: Stack[]
  partial: boolean
}

/** A tone partition the chart may colour by: whole non-negative counts that
 *  add up to the slot's own count. Anything else is all `unavailable`. */
export function toneFor(slot: ChatterSlot, tone: ToneSlot | undefined): Record<ToneKey, number> | null {
  if (slot.count === null) return null
  const valid = tone !== null && tone !== undefined
    && TONE_KEYS.every((key) => Number.isInteger(tone[key]) && tone[key] >= 0)
    && TONE_KEYS.reduce((sum, key) => sum + tone[key], 0) === slot.count
  if (valid) {
    return Object.fromEntries(TONE_KEYS.map((key) => [key, tone![key]])) as Record<ToneKey, number>
  }
  return { bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: slot.count }
}

export function peakCount(slots: ChatterSlot[]): number {
  return Math.max(1, ...slots.map((slot) => slot.count ?? 0))
}

/** Bars placed by each slot's own start and end, so a short last slot is a
 *  short bar and the axis never stretches to fit an array length. */
export function chatterBars(slots: ChatterSlot[], tone: ToneSlot[], frame: Frame): Bar[] {
  const peak = peakCount(slots)
  const height = FLOOR - BARS_TOP
  return slots.map((slot, index) => {
    const left = xOf(frame, instant(slot.start))
    const right = xOf(frame, instant(slot.end))
    const full = Math.max(0, right - left)
    const width = Math.max(Math.min(full, 1), full * 0.72)
    const parts = toneFor(slot, tone[index])
    const stacks: Stack[] = []
    if (parts) {
      let y = FLOOR
      for (const key of TONE_KEYS) {
        const h = (parts[key] / peak) * height
        y -= h
        if (parts[key] > 0) stacks.push({ key, y, height: h, value: parts[key] })
      }
    }
    return { index, left, right, x: left + (full - width) / 2, width, count: slot.count,
             stacks, partial: slot.coverage === 'partial' }
  })
}

export function bandBoxes(bands: PriceBand[], frame: Frame) {
  return bands.map((band) => {
    const x = xOf(frame, instant(band.from))
    return { x, width: Math.max(0, xOf(frame, instant(band.to)) - x), state: band.state,
             from: band.from, to: band.to }
  })
}

/** The slot an instant falls in, clamped to the ends. */
export function slotIndexAt(slots: ChatterSlot[], at: number): number {
  if (!slots.length) return -1
  for (let i = 0; i < slots.length; i++) {
    if (at < instant(slots[i]!.end)) return i
  }
  return slots.length - 1
}

/** Price observations belonging to a slot: bars that start inside it, or a
 *  stored observation stamped inside it. */
export function pointsInSlot(points: PricePoint[], slot: ChatterSlot): PricePoint[] {
  const start = instant(slot.start)
  const end = instant(slot.end)
  return points.filter((p) => {
    const t = p.start === p.end ? instant(p.at) : instant(p.start)
    return t >= start && t < end
  })
}

export function latestValid(points: PricePoint[]): PricePoint | null {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i]!.value !== null) return points[i]!
  }
  return null
}

export function bandAt(bands: PriceBand[], at: number): PriceBand['state'] | null {
  const band = bands.find((b) => instant(b.from) <= at && at < instant(b.to))
  return band ? band.state : null
}

// --- wording -------------------------------------------------------------------

const BERLIN = 'Europe/Berlin'
const NEW_YORK = 'America/New_York'

function parts(iso: string, zone: string, options: Intl.DateTimeFormatOptions) {
  const formatted = new Intl.DateTimeFormat('en-GB', { timeZone: zone, ...options })
    .formatToParts(new Date(iso))
  return (type: Intl.DateTimeFormatPartTypes) =>
    formatted.find((part) => part.type === type)?.value ?? ''
}

/** `14:45` in Berlin. */
export function berlinClock(iso: string): string {
  const part = parts(iso, BERLIN, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  return `${part('hour')}:${part('minute')}`
}

/** `CEST` or `CET` for that instant in Berlin. */
export function berlinZone(iso: string): string {
  return parts(iso, BERLIN, { timeZoneName: 'short' })('timeZoneName') || 'Berlin'
}

/** Month names written out here rather than taken from Intl: ICU versions
 *  disagree about en-GB's short September ("Sep" or "Sept"). */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function dayLabel(iso: string, zone: string): string {
  const part = parts(iso, zone, { weekday: 'short', day: 'numeric', month: 'numeric' })
  // Number(): with a weekday present Chromium's en-GB pattern pads the day
  // ("Wed 09 Sep") where Node's does not.
  return `${part('weekday')} ${Number(part('day'))} ${MONTHS[Number(part('month')) - 1] ?? ''}`
}

/** `Tue 15 Sep, 14:45` in Berlin. */
export function berlinStamp(iso: string): string {
  return `${dayLabel(iso, BERLIN)}, ${berlinClock(iso)}`
}

/** A modeled session date as written by the server (an ET calendar date),
 *  labelled without any timezone conversion: `Tue 15 Sep`. */
export function sessionDateLabel(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  return dayLabel(new Date(Date.UTC(year!, (month ?? 1) - 1, day ?? 1, 12)).toISOString(), 'UTC')
}

/** `Tue 15 Sep` for the US Eastern calendar date of an instant. */
export function newYorkDate(iso: string): string {
  return dayLabel(iso, NEW_YORK)
}

/** `09:30 ET` for an instant. */
export function newYorkClock(iso: string): string {
  const part = parts(iso, NEW_YORK, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  return `${part('hour')}:${part('minute')} ET`
}

export function intervalWord(seconds: number | null): string {
  if (seconds === null) return ''
  if (seconds % 60 === 0) {
    const minutes = seconds / 60
    return minutes === 1 ? '1-minute' : `${minutes}-minute`
  }
  return `${seconds}-second`
}

export function ageWord(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  return `${Math.round(seconds / 3600)} h`
}

const SOURCE_WORD: Record<string, string> = {
  yahoo_chart: 'Yahoo chart', finnhub: 'Finnhub', twelvedata: 'Twelve Data',
  massive_grouped: 'Massive', legacy: 'legacy feed',
  deutsche_boerse_delayed: 'Deutsche Börse (delayed)',
}

export function sourceWord(source: string): string {
  return SOURCE_WORD[source] ?? source
}

export function priceKindWord(price: PriceSeries): string {
  if (price.kind === 'bar_close') {
    return `${intervalWord(price.interval_seconds)} bar closes`
  }
  return price.kind === 'stored_quote' ? 'stored quotes' : 'stored daily closes'
}

export function money(value: number): string {
  const digits = value < 1 ? 4 : 2
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

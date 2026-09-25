// German number and date formatting, matching what the Jinja filters produced.
// Comma decimal separator, dot thousands separator, dd.MM.yyyy dates.

/**
 * `round(value)` as Python does it: a tie goes to the EVEN digit, where
 * JavaScript's Math.round and toFixed both send it away from zero.
 *
 * Every number-rendering helper here needs this, and every one of them is fed
 * dyadic rationals -- sessions over four weeks, weights in 1,25 / 2,5 kg
 * steps, shares of a total that land on x,5 -- so ties are the normal case,
 * not an exotic one. Two of them shipped: "3,25 Workouts pro Woche" printed
 * 3,2 for years and became 3,3, and a 22,5 % share printed 22 and became 23.
 *
 * Only a few doubles are ties, and the test for one is exact: half-way to
 * the next whole is an odd half, to the next tenth an odd quarter (3,25), to
 * the next hundredth an odd eighth (11,125) -- a value that many of which
 * make an odd whole number, and multiplying by a power of two rounds
 * nothing. Scaling by the power of ten first could land on ,5 by rounding:
 * 0,015 is really 0,01499..., which Python rounds down, and kg printed it
 * 0,02 (B9 review). Anything that is not a tie is left alone for the caller,
 * and toFixed rounds it as Python's '%.Nf' does: the double as it is.
 *
 * roundTo still scales before it rounds, so there a value like 0,8875 (really
 * 0,887499...) can come out one up in its last place -- a CSS length, where
 * that is nothing.
 *
 * Jinja's `|round` filter documents "common" (half-up) rounding and does not
 * do it -- it delegates to Python's round(). This mirrors the behaviour, not
 * the documentation.
 */
function halfEven(value: number, places = 0): number {
  const halves = value * 2 ** (places + 1)
  if (!Number.isInteger(halves) || halves % 2 === 0) return value
  const scale = 10 ** places
  const lower = Math.floor(value * scale)
  return (lower % 2 === 0 ? lower : lower + 1) / scale
}

/** `'%.1f'|format(x)` + `.replace('.', ',')` -- for a number worked out from
 *  weights (a 1RM, a share, a rate), never for a weight itself: that is `kg`. */
export function kg1(value: number): string {
  return halfEven(value, 1).toFixed(1).replace('.', ',')
}

/**
 * A weight, to the hundredth the app keeps: 11,25 reads 11,25 on every
 * screen. A quarter-kilo step is real, and three formatters used to disagree
 * on it -- 11,2 in the set row, 11,3 in the stepper, 11,25 in the settings --
 * and the stepper then wrote its 11,3 back (walkthrough G-146).
 *
 * A logged weight keeps the one decimal it has always shown: "80,0".
 */
export function kg(value: number): string {
  return hundredths(value).replace('.', ',')
}

/** The same weight as a setting, read the way it is typed: "20", "2,5". */
export function kgSetting(value: number): string {
  return hundredths(value).replace(/\.0$/, '').replace('.', ',')
}

/** "80.0", "11.5", "11.25": to the hundredth as stats.kg_text's '{:.2f}'
 *  has it, no zero past the first. */
function hundredths(value: number): string {
  return halfEven(value, 2).toFixed(2).replace(/0$/, '')
}

/** `'{:,.0f}'.format(v).replace(',', '.')` */
export function volume(value: number): string {
  return Math.round(halfEven(value)).toLocaleString('de-DE')
}

/** `x|round|int` -- a whole-number percentage or count. */
export function whole(value: number): number {
  return Math.round(halfEven(value))
}

/** `x|round(places)` -- for a CSS length, where a tie is a pixel either way. */
export function roundTo(value: number, places: number): number {
  const scale = 10 ** places
  return Math.round(halfEven(value, places) * scale) / scale
}

/** `'%+.0f'|format(x)`, which rounds a tie to even like everything else. */
export function signedWhole(value: number): string {
  const rounded = whole(Math.abs(value))
  return `${value >= 0 ? '+' : '-'}${rounded}`
}

/** A stored timestamp as an instant. They are naive UTC throughout this app,
 *  so a string that names no zone is UTC -- never the browser's local time,
 *  which is what `new Date()` assumes and what printed 00:10 on the 23rd as
 *  the 22nd (G-032, G-052). */
export function instant(iso: string): Date {
  return new Date(/(?:Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`)
}

/** The server's calendar zone (stats.LOCAL_TZ). Dates are read there whatever
 *  zone the device is in: the server files weeks and months by it, and a date
 *  printed in any other zone can disagree with its own bucket. */
const ZONE = 'Europe/Berlin'

const WALL_CLOCK = new Intl.DateTimeFormat('en-GB', {
  timeZone: ZONE, year: 'numeric', month: 'numeric', day: 'numeric',
  hour: 'numeric', minute: 'numeric', hourCycle: 'h23', weekday: 'short',
})
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export interface LocalParts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  /** Monday first, matching WEEKDAY_SHORT: 0 is Monday. */
  weekday: number
}

/** `x|local`: the wall clock in Berlin at a stored timestamp. */
export function localParts(iso: string): LocalParts {
  const part: Record<string, string> = {}
  for (const { type, value } of WALL_CLOCK.formatToParts(instant(iso))) part[type] = value
  return {
    year: Number(part.year), month: Number(part.month), day: Number(part.day),
    hour: Number(part.hour), minute: Number(part.minute),
    weekday: WEEKDAYS.indexOf(part.weekday ?? ''),
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** `(x|local).strftime('%d.%m.%Y')`
 *
 *  Built from the wall-clock parts rather than toLocaleDateString, which
 *  varies with the browser's locale settings -- the app renders German dates
 *  regardless of who is looking at it. */
export function shortDate(iso: string): string {
  const d = localParts(iso)
  return `${pad(d.day)}.${pad(d.month)}.${d.year}`
}

/** `(x|local).strftime('%d.%m.')` */
export function dayMonth(iso: string): string {
  const d = localParts(iso)
  return `${pad(d.day)}.${pad(d.month)}.`
}

/** WEEKDAY_SHORT, the server's own: the app speaks German to everyone. */
const WEEKDAY_DE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

/** A past day as a lifter says it: "heute", "gestern", the weekday within the
 *  last week, the date before that -- a week ago was the same weekday as
 *  today -- with its year when not this one (dayDate). Calendar days in
 *  Berlin, like every other date here. `now` is for tests. */
export function whenSaid(iso: string, now: Date = new Date()): string {
  const then = localParts(iso)
  const today = localParts(now.toISOString())
  const days = Math.round((Date.UTC(today.year, today.month - 1, today.day)
    - Date.UTC(then.year, then.month - 1, then.day)) / 86_400_000)
  if (days === 0) return 'heute'
  if (days === 1) return 'gestern'
  if (days > 1 && days < 7) return WEEKDAY_DE[then.weekday] ?? dayMonth(iso)
  return dayDate(iso, now)
}

/** A day in a sentence or a list: "25.08.", the year added when it is not
 *  this one -- "25.08." alone names a day in every year. Berlin's calendar;
 *  `now` is for tests. */
export function dayDate(iso: string, now: Date = new Date()): string {
  const then = localParts(iso)
  return then.year === localParts(now.toISOString()).year
    ? dayMonth(iso) : shortDate(iso)
}

/** "Mo 25.08.": a workout's day in the exercise page's log and readout. */
export function weekdayDate(iso: string, now: Date = new Date()): string {
  return `${WEEKDAY_DE[localParts(iso).weekday] ?? ''} ${dayDate(iso, now)}`.trim()
}

/** A kg rate with its sign, to the tenth: "+1,2", "−0,4" (a true minus), and
 *  "±0" for what rounds to nothing. */
export function signedKg1(value: number): string {
  const text = kg1(Math.abs(value))
  if (text === '0,0') return '±0'
  return `${value > 0 ? '+' : '−'}${text}`
}

/** A workout's sets as one line, the weight said again only where it
 *  changes: "55,0 × 10 · 9 · 8", "60,0 × 8 · 62,5 × 6 · 6". */
export function setsLine(sets: { weight: number; reps: number }[]): string {
  return sets.map((set, i) => (i > 0 && set.weight === sets[i - 1]!.weight
    ? String(set.reps)
    : `${kg(set.weight)} × ${set.reps}`)).join(' · ')
}

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
 * Exact over that domain, because a dyadic rational scaled by a power of ten
 * is still exact in binary, so the `=== 0.5` test is a real tie test rather
 * than a float comparison. Anything that is not a tie is left alone for the
 * caller to round normally, which agrees with Python everywhere else.
 *
 * Outside that domain it can differ by one in the last place: 0,8875 is really
 * 0,887499..., which Python rounds down and the scaling here reads as a tie.
 * Nothing on these pages formats a value like that -- the inputs are ints,
 * one-decimal floats from Python, and quarters -- but it is the boundary.
 *
 * Jinja's `|round` filter documents "common" (half-up) rounding and does not
 * do it -- it delegates to Python's round(). This mirrors the behaviour, not
 * the documentation.
 */
function halfEven(value: number, places = 0): number {
  const scale = 10 ** places
  const scaled = value * scale
  const lower = Math.floor(scaled)
  if (scaled - lower !== 0.5) return value
  return (lower % 2 === 0 ? lower : lower + 1) / scale
}

/** `'%.1f'|format(x)` + `.replace('.', ',')` */
export function kg1(value: number): string {
  return halfEven(value, 1).toFixed(1).replace('.', ',')
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
 *  today. Calendar days in Berlin, like every other date here. `now` is for
 *  tests. */
export function whenSaid(iso: string, now: Date = new Date()): string {
  const then = localParts(iso)
  const today = localParts(now.toISOString())
  const days = Math.round((Date.UTC(today.year, today.month - 1, today.day)
    - Date.UTC(then.year, then.month - 1, then.day)) / 86_400_000)
  if (days === 0) return 'heute'
  if (days === 1) return 'gestern'
  if (days > 1 && days < 7) return WEEKDAY_DE[then.weekday] ?? dayMonth(iso)
  return dayMonth(iso)
}

/** A workout's sets as one line, the weight said again only where it
 *  changes: "55,0 × 10 · 9 · 8", "60,0 × 8 · 62,5 × 6 · 6". */
export function setsLine(sets: { weight: number; reps: number }[]): string {
  return sets.map((set, i) => (i > 0 && set.weight === sets[i - 1]!.weight
    ? String(set.reps)
    : `${kg1(set.weight)} × ${set.reps}`)).join(' · ')
}

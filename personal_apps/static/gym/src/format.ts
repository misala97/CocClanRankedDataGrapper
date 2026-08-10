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

/** `(x|local).strftime('%d.%m.%Y')`
 *
 *  Built from the local-time parts rather than toLocaleDateString, which
 *  varies with the browser's locale settings -- the app renders German dates
 *  regardless of who is looking at it. */
export function shortDate(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}

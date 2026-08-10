// German number and date formatting, matching what the Jinja filters produced.
// Comma decimal separator, dot thousands separator, dd.MM.yyyy dates.

/** `'%.1f'|format(x)` + `.replace('.', ',')`
 *
 *  Not just toFixed: Python rounds a tie to the EVEN digit, JavaScript rounds
 *  it away from zero. 3,25 Workouts pro Woche printed as "3,2" for years and
 *  toFixed made it "3,3" -- and ties are not exotic here, they are the normal
 *  case. Everything this formats is a dyadic rational: sessions / 4 weeks, and
 *  weights in 1,25 / 2,5 kg steps. Both are exact in binary, so the tie test
 *  below is exact too, and anything that is not a tie falls through to toFixed,
 *  which agrees with Python everywhere else. */
export function kg1(value: number): string {
  const tenths = value * 10
  const lower = Math.floor(tenths)
  const rounded = tenths - lower === 0.5
    ? (lower % 2 === 0 ? lower : lower + 1) / 10
    : value
  return rounded.toFixed(1).replace('.', ',')
}

/** `'{:,.0f}'.format(v).replace(',', '.')` */
export function volume(value: number): string {
  return Math.round(value).toLocaleString('de-DE')
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

// German number and date formatting, matching what the Jinja filters produced.
// Comma decimal separator, dot thousands separator, dd.MM.yyyy dates.

/** `'%.1f'|format(x)` + `.replace('.', ',')` */
export function kg1(value: number): string {
  return value.toFixed(1).replace('.', ',')
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

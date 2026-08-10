/**
 * The two shared phrases from templates/gym/_macros.html, ported verbatim.
 * They are macros there because more than one page says them and the wording
 * must not drift between surfaces.
 */

/** How long ago, in words. */
export function recency(daysAgo: number | null, lead = false): string {
  if (daysAgo === null) return 'Noch nie gemacht'
  if (daysAgo === 0) return lead ? 'Heute schon gemacht' : 'Heute'
  if (daysAgo === 1) return 'Gestern'
  if (daysAgo < 7) return `vor ${daysAgo} Tagen`
  if (daysAgo < 14) return 'letzte Woche'
  if (daysAgo < 60) return `vor ${Math.round(daysAgo / 7)} Wochen`
  return `vor ${Math.round(daysAgo / 30)} Monaten`
}

/**
 * "4 Einheiten ohne PR", never a bare "4 ohne PR": the unit is the whole
 * meaning. At 0 the clause is dropped rather than rendered blank -- a row that
 * just set a record was showing an empty slot where every other row has a
 * count, which reads as missing data.
 */
export function sincePr(sessions: number | null): string {
  if (!sessions) return ''
  return `${sessions} ${sessions === 1 ? 'Einheit' : 'Einheiten'} ohne PR`
}

/**
 * Search folding: lowercase, and German umlauts to their two-letter forms so
 * "uebung" finds "Übung" and vice versa.
 */
export function fold(value: string): string {
  return value.toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
}

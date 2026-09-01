import type { BoardPayload } from './types'

/** The board embedded in the document, or null if it is not one.
 *
 *  Its own module so it can be tested: the entry point mounts React as an
 *  import side effect, so anything defined in there is only reachable by
 *  performing that mount.
 *
 *  The entry used to do `JSON.parse(el?.textContent ?? '{}')` inline, which
 *  has two ways of ending in a blank white viewport. Truncated JSON -- a
 *  response cut off mid-render -- throws before React is called at all. And
 *  the `'{}'` fallback parses cleanly into an object with no `rows`, which
 *  reaches `initial.rows[0]` and throws there instead. Both were reproduced
 *  against a served document: the reader gets a page with nothing on it, no
 *  heading, and nothing to search for.
 *
 *  `rows` is the check because it is what the page IS. A payload without it
 *  is not a thin board; it is not a board.
 */
export function parsePayload(text: string | null | undefined): BoardPayload | null {
  try {
    const parsed = JSON.parse(text ?? '') as unknown
    if (!parsed || typeof parsed !== 'object') return null
    if (!Array.isArray((parsed as BoardPayload).rows)) return null
    // Older server-rendered documents omitted these fields. Keep them usable
    // at the boundary rather than letting legacy embeds create an untyped
    // third market inside the page.
    const embedded = parsed as Partial<BoardPayload>
    return {
      ...(parsed as BoardPayload),
      market: embedded.market === 'de' ? 'de' : 'us',
      display_timezone: 'Europe/Berlin',
    }
  } catch {
    return null
  }
}

/** The board the page opens on.
 *
 *  Embedded when Flask rendered the document (production: the payload IS the
 *  page, and a spinner on arrival for data the server had in hand is a
 *  self-inflicted wait). Fetched when nothing is embedded -- the Vite dev
 *  harness at static/radar/dev.html has no Jinja to embed it -- for the
 *  page's own query, so `?market=de&window=12` opens the same board it would
 *  under Flask. Null on any failure; the entry renders words, not a throw.
 *
 *  A redirected response is a failure: @login_required redirects rather than
 *  401s and fetch follows it transparently, so a signed-out harness would
 *  otherwise hand the parser a login page with a 200.
 */
export async function loadPayload(): Promise<BoardPayload | null> {
  const embedded = document.getElementById('radar-data')
  if (embedded) return parsePayload(embedded.textContent)
  try {
    const response = await fetch(`/radar/api/board${window.location.search}`, {
      headers: { Accept: 'application/json' }, credentials: 'same-origin',
    })
    if (!response.ok || response.redirected) return null
    return parsePayload(await response.text())
  } catch {
    return null
  }
}

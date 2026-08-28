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
    return parsed as BoardPayload
  } catch {
    return null
  }
}

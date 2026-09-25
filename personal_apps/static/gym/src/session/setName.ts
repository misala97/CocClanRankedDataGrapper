import type { LiveSet } from './types'

/** What the screen holds a set by: its key for one this screen added -- its
 *  id changes from the drawn one to the real one when the server names it
 *  (B6) -- else its id. Held by the id, a set un-logged or deleted while its
 *  add landed came back for the rest of the undo window (B6 re-review). */
export const setName = (set: Pick<LiveSet, 'id' | 'key'>): string =>
  set.key ?? `#${set.id}`

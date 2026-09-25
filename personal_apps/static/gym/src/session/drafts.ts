/**
 * The live card's steppers, as the lifter left them (G-009). They lived in
 * component state alone, so a reload -- iOS dropping a PWA in the
 * background, a pull to refresh -- put last week's numbers back on a set the
 * lifter had already dialled in.
 *
 * One draft per workout, for the set the steppers are bound to (`bound`, the
 * card's boundTo): a draft for any other set is stale and never shown.
 * localStorage can throw (a private window, a full disk): then there is
 * simply no draft.
 */

const PREFIX = 'gym-draft:'

export interface Draft {
  bound: string
  weight: number | null
  reps: number | null
}

const keyOf = (sessionId: number) => `${PREFIX}${sessionId}`

export function readDraft(sessionId: number, bound: string): Draft | null {
  try {
    const draft = JSON.parse(localStorage.getItem(keyOf(sessionId)) ?? 'null') as Draft | null
    if (draft === null || draft.bound !== bound) return null
    const number = (v: unknown) => v === null || (typeof v === 'number' && Number.isFinite(v))
    return number(draft.weight) && number(draft.reps) ? draft : null
  } catch {
    return null
  }
}

export function saveDraft(sessionId: number, draft: Draft): void {
  try { localStorage.setItem(keyOf(sessionId), JSON.stringify(draft)) } catch { /* no draft */ }
}

export function clearDraft(sessionId: number): void {
  try { localStorage.removeItem(keyOf(sessionId)) } catch { /* no draft */ }
}

/** Another workout's draft is over: only one runs at a time. */
export function sweepDrafts(sessionId: number): void {
  try {
    const stale: string[] = []
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i)
      if (key !== null && key.startsWith(PREFIX) && key !== keyOf(sessionId)) stale.push(key)
    }
    for (const key of stale) localStorage.removeItem(key)
  } catch { /* nothing to sweep */ }
}

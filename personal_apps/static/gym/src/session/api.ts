import type { SessionDetailPayload } from './types'

/**
 * Every write the live workout can perform, and the one read it starts from.
 *
 * `Accept: application/json` is not optional and not a nicety. The routes
 * negotiate: a browser form post sends text/html followed by a wildcard, and a
 * bare fetch() sends the wildcard alone -- and a wildcard accepts HTML, so
 * neither of them gets JSON. Only this explicit header distinguishes the
 * island, and without it every mutation would answer with a 302 the client
 * cannot use. Pinned server-side by test_a_bare_fetch_does_not_get_json.
 */
const JSON_HEADERS = { Accept: 'application/json' }

/**
 * A request that never resolves is the worst failure mode: the sweep runs
 * forever and the banner never comes, so the screen says "working" for as long
 * as you look at it. Eight seconds is well past a slow gym-wifi round trip and
 * well short of the point where you would put the phone down.
 */
const TIMEOUT_MS = 8000

export class MutationFailed extends Error {
  constructor(readonly reason: 'timeout' | 'network') {
    super(reason)
  }

  /** The message the banner shows. German, because the banner is German. */
  get germanMessage(): string {
    return this.reason === 'timeout'
      ? 'Keine Antwort vom Server — deine letzte Änderung wurde nicht gespeichert.'
      : 'Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.'
  }
}

async function post(url: string, fields: Record<string, string | number | boolean> = {}) {
  const body = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    body.append(key, String(value))
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      method: 'POST', body, headers: JSON_HEADERS,
      credentials: 'same-origin', signal: controller.signal,
    })
    if (!response.ok) throw new MutationFailed('network')
    return await response.json() as SessionDetailPayload
  } catch (error) {
    if (error instanceof MutationFailed) throw error
    throw new MutationFailed(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchSession(sessionId: number): Promise<SessionDetailPayload> {
  const response = await fetch(`/gym/session/${sessionId}/detail.json`, {
    headers: JSON_HEADERS, credentials: 'same-origin',
  })
  if (!response.ok) throw new MutationFailed('network')
  return await response.json() as SessionDetailPayload
}

export const api = {
  /** States the state it wants rather than asking for a flip, which is what
   *  makes gym_toggle_set_complete idempotent -- a second tap is a no-op
   *  rather than an un-log. */
  toggleSet: (setId: number, completed: boolean, weight: number, reps: number) =>
    post(`/gym/set/${setId}/toggle_complete`,
      { completed: completed ? '1' : '0', weight, reps }),

  /** gym_add_set creates the set already completed and starts its rest, which
   *  is what "Satz geschafft" means everywhere else on this screen. It cannot
   *  be made idempotent the way the toggle can -- a second POST creates a
   *  second set -- so the in-flight lock is what protects it. */
  addSet: (sessionExerciseId: number, weight: number, reps: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/sets/add`, { weight, reps }),

  updateSet: (setId: number, weight: number, reps: number) =>
    post(`/gym/set/${setId}/update`, { weight, reps }),

  deleteSet: (setId: number) => post(`/gym/set/${setId}/delete`),

  addExercise: (sessionId: number, exerciseId: number) =>
    post(`/gym/session/${sessionId}/exercises/add`, { exercise_id: exerciseId }),

  createExercise: (sessionId: number, name: string) =>
    post(`/gym/session/${sessionId}/exercises/add`, { new_exercise_name: name }),

  removeExercise: (sessionExerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/delete`),

  toggleSkip: (sessionExerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/skip`),

  replaceExercise: (sessionExerciseId: number, exerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/replace`, { exercise_id: exerciseId }),

  replaceWithNew: (sessionExerciseId: number, name: string) =>
    post(`/gym/session-exercise/${sessionExerciseId}/replace`, { new_exercise_name: name }),

  setRest: (sessionExerciseId: number, seconds: number | null) =>
    post(`/gym/session-exercise/${sessionExerciseId}/rest`,
      { rest_seconds: seconds === null ? '' : seconds }),

  setIncrement: (sessionExerciseId: number, kg: number | null) =>
    post(`/gym/session-exercise/${sessionExerciseId}/increment`,
      { weight_increment: kg === null ? '' : kg }),

  setExerciseMeta: (sessionExerciseId: number, meta: { pain: boolean; notes: string }) =>
    post(`/gym/session-exercises/${sessionExerciseId}/meta`,
      { pain: meta.pain ? 'on' : '', notes: meta.notes }),

  setSessionMeta: (sessionId: number, meta: { bodyweightKg: number | null; notes: string }) =>
    post(`/gym/sessions/${sessionId}/meta`, {
      bodyweight_kg: meta.bodyweightKg === null ? '' : meta.bodyweightKg,
      notes: meta.notes,
    }),

  reorder: (sessionId: number, order: number[]) =>
    post(`/gym/session/${sessionId}/exercises/reorder`, { order: order.join(',') }),

  skipRest: (sessionId: number) => post(`/gym/session/${sessionId}/rest/skip`),

  toggleDeload: (sessionId: number, on: boolean, pct: number) =>
    post(`/gym/session/${sessionId}/deload`, { on: on ? '1' : '0', pct }),
}

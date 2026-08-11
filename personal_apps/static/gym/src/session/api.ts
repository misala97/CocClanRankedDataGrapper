import type { SessionDetailPayload } from './types'
import { getJson, postForm, MutationFailed } from '../api'

/**
 * Every write the live workout can perform, and the one read it starts from.
 * The HTTP core (Accept negotiation, timeout, MutationFailed) lives in
 * ../api.ts and is shared with the other islands' saves.
 */
export { MutationFailed }

const post = (url: string, fields: Record<string, string | number | boolean> = {}) =>
  postForm<SessionDetailPayload>(url, fields)

export function fetchSession(sessionId: number): Promise<SessionDetailPayload> {
  return getJson<SessionDetailPayload>(`/gym/session/${sessionId}/detail.json`)
}

/** The follower's version check. Reads the caller's OWN session -- a
 *  structural change arrives as a write into their rows, so nothing here
 *  reads the partner's data. */
export function fetchSync(sessionId: number): Promise<{ version: number; shared: boolean }> {
  return getJson<{ version: number; shared: boolean }>(`/gym/session/${sessionId}/sync.json`)
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

import type { SessionDetailPayload } from './types'
import { getJson, postForm, MutationFailed } from '../api'

/**
 * Every write the live workout can perform, and the one read it starts from.
 * The HTTP core (Accept negotiation, timeout, MutationFailed) lives in
 * ../api.ts and is shared with the other islands' saves.
 */
export { MutationFailed }

/** Every write names the live screen as its source. The debrief posts to the
 *  same set routes to correct a finished workout; this header is how the
 *  server tells a stale live screen (refused, 409) from a correction. */
const LIVE = { 'X-Gym-Surface': 'live' }

const post = (url: string, fields: Record<string, string | number | boolean> = {}) =>
  postForm<SessionDetailPayload>(url, fields, { headers: LIVE })

/** A workout's own bodyweight and note. A key left out is left alone; a
 *  null bodyweight clears it. */
export interface SessionMetaPatch {
  bodyweightKg?: number | null
  notes?: string
}

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
  toggleSet: (setId: number, completed: boolean, weight: number | null, reps: number | null) =>
    // A blank goes as an empty field, which the server reads as "leave it".
    post(`/gym/set/${setId}/toggle_complete`,
      { completed: completed ? '1' : '0', weight: weight ?? '', reps: reps ?? '' }),

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

  removeExercise: (sessionExerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/delete`),

  toggleSkip: (sessionExerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/skip`),

  replaceExercise: (sessionExerciseId: number, exerciseId: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/replace`, { exercise_id: exerciseId }),

  /** "Pause heute". The step and the rest that always apply are the
   *  lifter's settings, saved by ../settings/api. */
  setRest: (sessionExerciseId: number, seconds: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/rest`, { rest_seconds: seconds }),

  setExerciseMeta: (sessionExerciseId: number, meta: { pain: boolean; notes: string }) =>
    post(`/gym/session-exercises/${sessionExerciseId}/meta`,
      { pain: meta.pain ? 'on' : '', notes: meta.notes }),

  /** Either field alone, or both: the server writes only what is sent, so
   *  the bodyweight saves on its own and the note on its own (G-071 -- one
   *  shared button beside the note used to leave a typed bodyweight unsaved). */
  setSessionMeta: (sessionId: number, meta: SessionMetaPatch) => {
    const fields: Record<string, string | number> = {}
    if (meta.bodyweightKg !== undefined) {
      fields.bodyweight_kg = meta.bodyweightKg === null ? '' : meta.bodyweightKg
    }
    if (meta.notes !== undefined) fields.notes = meta.notes
    return post(`/gym/sessions/${sessionId}/meta`, fields)
  },

  reorder: (sessionId: number, order: number[]) =>
    post(`/gym/session/${sessionId}/exercises/reorder`, { order: order.join(',') }),

  skipRest: (sessionId: number) => post(`/gym/session/${sessionId}/rest/skip`),

  /** "−15" / "+15" on the countdown band: `seconds` is one of the two. */
  shiftRest: (sessionId: number, seconds: number) =>
    post(`/gym/session/${sessionId}/rest/shift`, { seconds }),

  toggleDeload: (sessionId: number, on: boolean, pct: number) =>
    post(`/gym/session/${sessionId}/deload`, { on: on ? '1' : '0', pct }),
}

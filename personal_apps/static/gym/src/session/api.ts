import type { RoutinePlan, SessionDetailPayload } from './types'
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

/** Every write goes out through the outbox (./outbox.ts), which may send it
 *  minutes or a day after the tap: `at` says when the lifter made it, and
 *  the server stamps the set and runs the rest from there, not from when it
 *  arrived (helpers._write_time). Sent as its age, not as a time: this
 *  phone's clock can be minutes off the server's, an age cannot. keepalive,
 *  always: a write in flight when the page goes away still lands, and the
 *  outbox, which never saw its answer, sends it once more at the next open
 *  -- a no-op by then. */
const post = (url: string, fields: Record<string, string | number | boolean> = {},
  at?: number) =>
  postForm<SessionDetailPayload>(url, fields, {
    headers: at === undefined
      ? LIVE
      : { ...LIVE, 'X-Gym-Write-Age': String(Math.max(0, Math.round(Date.now() - at))) },
    keepalive: true,
  })

/** A workout's own bodyweight and note. A key left out is left alone; a
 *  null bodyweight clears it. */
export interface SessionMetaPatch {
  bodyweightKg?: number | null
  notes?: string
}

/** The live payload's place in the island's query cache. */
export const sessionKey = (sessionId: number) => ['session', sessionId] as const

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
  toggleSet: (setId: number, completed: boolean, weight: number | null, reps: number | null,
    at?: number) =>
    // A blank goes as an empty field, which the server reads as "leave it".
    post(`/gym/set/${setId}/toggle_complete`,
      { completed: completed ? '1' : '0', weight: weight ?? '', reps: reps ?? '' }, at),

  /** gym_add_set creates the set already completed and starts its rest, which
   *  is what "Satz geschafft" means everywhere else on this screen. `key`
   *  names the set: sent twice, the second copy finds it instead of making
   *  another (SessionSet.client_key). */
  addSet: (sessionExerciseId: number, weight: number, reps: number, key: string, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/sets/add`, { weight, reps, key }, at),

  /** The sheet's "Anhängen" (Q2): the same route with `open`, which adds the
   *  set open behind the others -- no rest, no record until it is ticked. */
  planSet: (sessionExerciseId: number, weight: number, reps: number, key: string, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/sets/add`,
      { weight, reps, key, open: '1' }, at),

  updateSet: (setId: number, weight: number, reps: number, at?: number) =>
    post(`/gym/set/${setId}/update`, { weight, reps }, at),

  deleteSet: (setId: number, at?: number) =>
    post(`/gym/set/${setId}/delete`, {}, at),

  addExercise: (sessionId: number, exerciseId: number, at?: number) =>
    post(`/gym/session/${sessionId}/exercises/add`, { exercise_id: exerciseId }, at),

  /** `done`: the done sets the screen showed when the lifter asked. A row
   *  holding more by the time this lands stays (a 409): a swap's undo sent
   *  again later took the sets logged since with it (B7 review). */
  removeExercise: (sessionExerciseId: number, done: number, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/delete`, { done: String(done) }, at),

  /** The state wanted, like the tick: a flip sent twice undid itself. */
  toggleSkip: (sessionExerciseId: number, skipped: boolean, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/skip`, { skipped: skipped ? '1' : '0' }, at),

  replaceExercise: (sessionExerciseId: number, exerciseId: number, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/replace`, { exercise_id: exerciseId }, at),

  /** "Pause heute". The step and the rest that always apply are the
   *  lifter's settings, saved by ../settings/api. */
  setRest: (sessionExerciseId: number, seconds: number, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/rest`, { rest_seconds: seconds }, at),

  /** The routine's plan for the exercise (D2 P1): kept by the routine, so it
   *  plans the next workout; this one's sets stay. */
  setRoutinePlan: (sessionExerciseId: number, plan: RoutinePlan, at?: number) =>
    post(`/gym/session-exercise/${sessionExerciseId}/routine-plan`,
      { sets: plan.sets, rep_min: plan.rep_min, rep_max: plan.rep_max }, at),

  setExerciseMeta: (sessionExerciseId: number, meta: { pain: boolean; notes: string },
    at?: number) =>
    post(`/gym/session-exercises/${sessionExerciseId}/meta`,
      { pain: meta.pain ? 'on' : '', notes: meta.notes }, at),

  /** Either field alone, or both: the server writes only what is sent, so
   *  the bodyweight saves on its own and the note on its own (G-071 -- one
   *  shared button beside the note used to leave a typed bodyweight unsaved). */
  setSessionMeta: (sessionId: number, meta: SessionMetaPatch, at?: number) => {
    const fields: Record<string, string | number> = {}
    if (meta.bodyweightKg !== undefined) {
      fields.bodyweight_kg = meta.bodyweightKg === null ? '' : meta.bodyweightKg
    }
    if (meta.notes !== undefined) fields.notes = meta.notes
    return post(`/gym/sessions/${sessionId}/meta`, fields, at)
  },

  reorder: (sessionId: number, order: number[], at?: number) =>
    post(`/gym/session/${sessionId}/exercises/reorder`, { order: order.join(',') }, at),

  skipRest: (sessionId: number, at?: number) =>
    post(`/gym/session/${sessionId}/rest/skip`, {}, at),

  /** "−15" / "+15" on the countdown band: `seconds` is one of the two. */
  shiftRest: (sessionId: number, seconds: number, at?: number) =>
    post(`/gym/session/${sessionId}/rest/shift`, { seconds }, at),

  toggleDeload: (sessionId: number, on: boolean, pct: number, at?: number) =>
    post(`/gym/session/${sessionId}/deload`, { on: on ? '1' : '0', pct }, at),
}

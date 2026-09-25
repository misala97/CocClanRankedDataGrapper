import type { RoutinePlan, SessionDetailPayload } from './types'
import { api, type SessionMetaPatch } from './api'
import * as optimistic from './optimistic'
import type { WriteSpec } from './outbox'
import type { Remedy } from './stores'

/**
 * Every write the live workout makes, as the outbox sends, draws and keeps it
 * (B6). Arguments are stored on the phone as JSON and read back by a later
 * version of this file: changing what a kind takes means a new kind, or a
 * new OUTBOX_VERSION.
 */
export interface WriteArgs {
  toggleSet: [setId: number, completed: boolean, weight: number | null, reps: number | null]
  /** `key`: the set's own name (SessionSet.client_key). `tempId`: the id it
   *  has on the screen until the server names it -- negative. */
  addSet: [seId: number, weight: number, reps: number, key: string, tempId: number]
  /** The sheet's "Anhängen" (Q2): addSet's, the set added open. */
  planSet: [seId: number, weight: number, reps: number, key: string, tempId: number]
  updateSet: [setId: number, weight: number, reps: number]
  deleteSet: [setId: number]
  toggleSkip: [seId: number, skipped: boolean]
  exerciseMeta: [seId: number, meta: { pain: boolean; notes: string }]
  setRest: [seId: number, seconds: number]
  routinePlan: [seId: number, plan: RoutinePlan]
  sessionMeta: [meta: SessionMetaPatch]
  reorder: [order: number[]]
  skipRest: []
  shiftRest: [seconds: number]
  addExercise: [exerciseId: number]
  /** `done`: the done sets on the row as the lifter saw it (api.removeExercise). */
  removeExercise: [seId: number, done: number]
  replaceExercise: [seId: number, exerciseId: number]
  toggleDeload: [on: boolean, pct: number]
}

export type WriteKind = keyof WriteArgs

interface Spec<A extends unknown[]> {
  send(args: A, at: number): Promise<SessionDetailPayload>
  apply?(payload: SessionDetailPayload, args: A, at: number): SessionDetailPayload
  durable: boolean
  key(args: A): string
  resend?: Remedy | null
  setArg?: number
  creates?: { key: number; temp: number }
}

type Specs = { [K in WriteKind]: Spec<WriteArgs[K]> }

/** The specs for one workout. What a failure is filed under (`key`) is the
 *  thing the write states the whole of: its newest intent answers an older
 *  failure whose retry would put back what the lifter had already changed
 *  (G-139), and a set's delete answers its lost tick ('set-4' answers
 *  'set-4:done', stores.succeed). */
export function writeSpecs(sessionId: number): Record<string, WriteSpec> {
  const specs: Specs = {
    // Kept: each states what it wants, so sending it twice is doing it once
    // -- and its answer can be lost after it landed.
    toggleSet: {
      send: ([setId, completed, weight, reps], at) =>
        api.toggleSet(setId, completed, weight, reps, at),
      apply: (p, [setId, completed, weight, reps], at) =>
        optimistic.toggleSet(p, setId, completed, weight, reps, at),
      durable: true, key: ([setId]) => `set-${setId}:done`, setArg: 0,
    },
    // Sent twice, the key finds the set the first copy made.
    addSet: {
      send: ([seId, weight, reps, key], at) => api.addSet(seId, weight, reps, key, at),
      apply: (p, [seId, weight, reps, key, tempId], at) =>
        optimistic.addSet(p, seId, weight, reps, key, tempId, at),
      durable: true, key: ([, , , key]) => `add-${key}`, creates: { key: 3, temp: 4 },
    },
    planSet: {
      send: ([seId, weight, reps, key], at) => api.planSet(seId, weight, reps, key, at),
      apply: (p, [seId, weight, reps, key, tempId]) =>
        optimistic.planSet(p, seId, weight, reps, key, tempId),
      durable: true, key: ([, , , key]) => `add-${key}`, creates: { key: 3, temp: 4 },
    },
    updateSet: {
      send: ([setId, weight, reps], at) => api.updateSet(setId, weight, reps, at),
      apply: (p, [setId, weight, reps]) => optimistic.updateSet(p, setId, weight, reps),
      durable: true, key: ([setId]) => `set-${setId}:numbers`, setArg: 0,
    },
    deleteSet: {
      send: ([setId], at) => api.deleteSet(setId, at),
      apply: (p, [setId]) => optimistic.deleteSet(p, setId),
      durable: true, key: ([setId]) => `set-${setId}`, setArg: 0,
    },
    toggleSkip: {
      send: ([seId, skipped], at) => api.toggleSkip(seId, skipped, at),
      apply: (p, [seId, skipped]) => optimistic.toggleSkip(p, seId, skipped),
      durable: true, key: ([seId]) => `skip-${seId}`,
    },
    exerciseMeta: {
      send: ([seId, meta], at) => api.setExerciseMeta(seId, meta, at),
      apply: (p, [seId, meta]) => optimistic.setExerciseMeta(p, seId, meta),
      durable: true, key: ([seId]) => `exercise-meta-${seId}`,
    },
    setRest: {
      send: ([seId, seconds], at) => api.setRest(seId, seconds, at),
      apply: (p, [seId, seconds]) => optimistic.setRest(p, seId, seconds),
      durable: true, key: ([seId]) => `rest-${seId}`,
    },
    routinePlan: {
      send: ([seId, plan], at) => api.setRoutinePlan(seId, plan, at),
      apply: (p, [seId, plan]) => optimistic.setRoutinePlan(p, seId, plan),
      durable: true, key: ([seId]) => `routine-plan-${seId}`,
    },
    // By field: the bodyweight saved later answers the one that was lost.
    sessionMeta: {
      send: ([meta], at) => api.setSessionMeta(sessionId, meta, at),
      apply: (p, [meta]) => optimistic.setSessionMeta(p, meta),
      durable: true, key: ([meta]) => `meta:${Object.keys(meta).sort().join(',')}`,
    },
    reorder: {
      send: ([order], at) => api.reorder(sessionId, order, at),
      apply: (p, [order]) => optimistic.reorderExercises(p, order),
      durable: true, key: () => 'order',
    },
    // Ends the rest at the tap, however late it lands (helpers._write_time).
    skipRest: {
      send: (_, at) => api.skipRest(sessionId, at),
      apply: (p, _, at) => optimistic.skipRest(p, at),
      durable: true, key: () => 'rest',
    },

    // Not kept. About this moment only: a minute later "+15 s" moves a
    // different rest -- reported, never sent again.
    shiftRest: {
      send: ([seconds], at) => api.shiftRest(sessionId, seconds, at),
      apply: (p, [seconds], at) => optimistic.shiftRest(p, seconds, at),
      durable: false, key: () => 'rest', resend: null,
    },
    // Not kept, and not drawn: each moves which exercise is live, or the
    // weights, and that is the server's to decide. Adding and swapping are
    // new work each time -- sent again only on the lifter's tap.
    addExercise: {
      send: ([exerciseId], at) => api.addExercise(sessionId, exerciseId, at),
      durable: false, key: ([exerciseId]) => `add-exercise-${exerciseId}`, resend: 'manual',
    },
    removeExercise: {
      send: ([seId, done], at) => api.removeExercise(seId, done, at),
      durable: false, key: ([seId]) => `exercise-${seId}`, resend: 'auto',
    },
    replaceExercise: {
      send: ([seId, exerciseId], at) => api.replaceExercise(seId, exerciseId, at),
      durable: false, key: ([seId]) => `replace-${seId}`, resend: 'manual',
    },
    toggleDeload: {
      send: ([on, pct], at) => api.toggleDeload(sessionId, on, pct, at),
      durable: false, key: () => 'deload', resend: 'auto',
    },
  }
  return specs as unknown as Record<string, WriteSpec>
}

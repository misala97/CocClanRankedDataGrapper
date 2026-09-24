import type { LiveExercise, LiveSet, RoutinePlan, SessionDetailPayload } from './types'
import { instant } from '../format'
import { REST_MAX } from '../settings/values'

/**
 * Local guesses at what a write will do, applied before the server answers.
 *
 * Only for writes whose effect is computable honestly and completely. The ones
 * that are not -- adding or replacing an exercise, anything that changes which
 * exercise is live -- have no entry here and wait for the server. A screen
 * that is briefly a lie is worse than one that is briefly slow, and
 * `_live_context` deliberately owns the live-exercise rule because three
 * surfaces have to agree on it. (Reordering is the one write that LOOKS like
 * it belongs in that group but does not: the row order is the user's explicit
 * intent, so it is honest -- only `live_id` stays the server's and is left
 * untouched below.)
 */

/** Whether a set counts: done, with reps (Q1, G-038) -- stats.set_counts,
 *  the one rule every screen counts by. */
const counts = (s: LiveSet) => s.completed && s.reps !== null && s.reps >= 1

/** Recompute the tallies a set change moves. Kept together because they are
 *  one fact counted three ways, and updating one without the others would show
 *  a strip that disagreed with the number above it. The same walk as
 *  _live_data's, so the server's answer never moves the strip. */
function retally(payload: SessionDetailPayload): SessionDetailPayload {
  let done = 0
  let total = 0
  let volume = 0
  const ticks: SessionDetailPayload['tick_states'] = []

  // 'now' is the first open set of the live exercise, the one the steppers
  // are bound to.
  const live = payload.visible_exercises.find((se) => se.id === payload.live_id)
  const nowId = live && !live.skipped ? live.sets.find((s) => !s.completed)?.id : undefined

  for (const se of payload.visible_exercises) {
    // The hidden originals this row replaced: their done sets count in place,
    // ahead of the row's own (Q1).
    done += se.replaced_sets_done
    total += se.replaced_sets_done
    volume += se.replaced_volume
    for (let i = 0; i < se.replaced_sets_done; i += 1) ticks.push('done')
    for (const s of se.sets) {
      if (counts(s)) {
        done += 1
        total += 1
        ticks.push('done')
        // A counted set always has its numbers; the ?? only satisfies the
        // type, which a blank planned set shares.
        volume += (s.weight ?? 0) * (s.reps ?? 0) * (se.is_unilateral ? 2 : 1)
      } else if (!se.skipped && !s.completed) {
        // A skipped exercise's open sets are not going to be lifted, and a
        // done set without reps is no set: neither is a tick.
        total += 1
        ticks.push(s.id === nowId ? 'now' : 'open')
      }
    }
  }

  return {
    ...payload,
    tick_states: ticks,
    sets_done: done,
    sets_total: total,
    sets_open: total - done,
    session_volume: volume,
    has_completed_set: done > 0,
  }
}

/** Ticking a set off, or putting it back. The one write that happens dozens of
 *  times per workout, and the only one where the round trip is felt. */
export function toggleSet(
  payload: SessionDetailPayload,
  setId: number,
  completed: boolean,
  weight: number | null,
  reps: number | null,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => {
      const at = se.sets.findIndex((s) => s.id === setId)
      if (at === -1) return se
      // Logging a set fills the blanks of the open sets after it -- the
      // server does the same (workout._fill_blanks_after). Without it here
      // the next set flashed blank for the length of the request.
      const fills = completed && !se.sets[at]!.completed
      return {
        ...se,
        sets: se.sets.map((s, i) => {
          if (i === at) return { ...s, completed, weight, reps }
          if (fills && i > at && !s.completed && (s.weight === null || s.reps === null)) {
            return { ...s, weight: s.weight ?? weight, reps: s.reps ?? reps }
          }
          return s
        }),
      }
    }),
  })
}

/** Correcting a logged set's numbers without changing whether it is done. */
export function updateSet(
  payload: SessionDetailPayload,
  setId: number,
  weight: number,
  reps: number,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => ({
      ...se,
      sets: se.sets.map((s) => (s.id === setId ? { ...s, weight, reps } : s)),
    })),
  })
}

export function deleteSet(
  payload: SessionDetailPayload,
  setId: number,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => ({
      ...se,
      sets: se.sets.filter((s) => s.id !== setId),
    })),
  })
}

/** Skipping is instant and reversible, and it changes the totals because a
 *  skipped exercise's open sets leave the strip; its done sets stay. */
export function toggleSkip(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      se.id === sessionExerciseId ? { ...se, skipped: !se.skipped } : se),
  })
}

/** The rows in the order the user just chose. Positions renumber to match,
 *  and retally keeps the tick strip reading in queue order; which exercise is
 *  live is not guessed at -- the server's answer replaces this wholesale. */
export function reorderExercises(
  payload: SessionDetailPayload,
  order: number[],
): SessionDetailPayload {
  const byId = new Map(payload.visible_exercises.map((se) => [se.id, se]))
  const reordered = order
    .map((id) => byId.get(id))
    .filter((se): se is LiveExercise => se !== undefined)
  // Anything the order list missed keeps its place at the end rather than
  // vanishing from the screen until the server answers.
  for (const se of payload.visible_exercises) {
    if (!order.includes(se.id)) reordered.push(se)
  }
  return retally({
    ...payload,
    visible_exercises: reordered.map((se, i) => ({ ...se, position: i + 1 })),
  })
}

/** Notes and the pain flag: local, immediate, and with no effect on anything
 *  else the screen shows. */
export function setExerciseMeta(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  meta: { pain: boolean; notes: string },
): SessionDetailPayload {
  return {
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      se.id === sessionExerciseId
        ? { ...se, pain: meta.pain, notes: meta.notes || null }
        : se),
  }
}

/** The routine's plan for a row, as the steppers left it. Only that: the
 *  target it changes is worked out on the server, and arrives with the
 *  answer. */
export function setRoutinePlan(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  plan: RoutinePlan,
): SessionDetailPayload {
  return {
    ...payload,
    routine_plans: { ...payload.routine_plans, [String(sessionExerciseId)]: plan },
  }
}

/** "Pause heute". The setting's own value is stored as nothing -- the row
 *  follows the setting again -- which is the server's rule too
 *  (gym_update_session_exercise_rest). The rest already running keeps the
 *  length it started with; that stays the server's to say. */
export function setRest(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  seconds: number,
): SessionDetailPayload {
  return {
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      se.id === sessionExerciseId
        ? { ...se, rest_seconds: seconds === se.rest_setting ? null : seconds }
        : se),
  }
}

/** Naive UTC, as the server sends it. */
function naive(ms: number): string {
  return new Date(ms).toISOString().replace('Z', '')
}

/** The running rest ended now, as gym_skip_rest leaves it: its end stamped
 *  now (whole seconds, as the database keeps it) and the set it followed
 *  kept, so the band stays and counts up until the next set. A rest that is
 *  not running is left alone. `now` is for tests. */
export function skipRest(
  payload: SessionDetailPayload,
  now: number = Date.now(),
): SessionDetailPayload {
  const endsAt = payload.session.rest_ends_at
  if (!payload.resting || endsAt === null || instant(endsAt).getTime() <= now) return payload
  return {
    ...payload,
    resting: false,
    rest_total_seconds: 0,
    session: { ...payload.session, rest_ends_at: naive(Math.floor(now / 1000) * 1000) },
  }
}

/** "−15" / "+15" on the running rest, as gym_shift_rest answers it: the end
 *  and the total move together, "+15" stops at the longest rest there is
 *  (never shortening one already longer), and a step past the end ends the
 *  rest as the skip does. A rest that is not running -- or already ran out --
 *  is left alone. `now` is for tests. */
export function shiftRest(
  payload: SessionDetailPayload,
  seconds: number,
  now: number = Date.now(),
): SessionDetailPayload {
  const endsAt = payload.session.rest_ends_at
  if (!payload.resting || endsAt === null) return payload
  const ends = instant(endsAt).getTime()
  if (ends <= now) return payload
  const started = ends - payload.rest_total_seconds * 1000
  const moved = seconds > 0
    ? Math.min(ends + seconds * 1000, Math.max(ends, started + REST_MAX * 1000))
    : ends + seconds * 1000
  if (moved === ends) return payload
  if (moved <= now) return skipRest(payload, now)
  return {
    ...payload,
    rest_total_seconds: Math.round((moved - started) / 1000),
    session: { ...payload.session, rest_ends_at: naive(moved) },
  }
}

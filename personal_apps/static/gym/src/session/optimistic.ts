import type { LiveExercise, SessionDetailPayload } from './types'

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

/** Recompute the tallies a set change moves. Kept together because they are
 *  one fact counted three ways, and updating one without the others would show
 *  a strip that disagreed with the number above it. */
function retally(payload: SessionDetailPayload): SessionDetailPayload {
  let done = 0
  let total = 0
  let volume = 0
  const ticks: SessionDetailPayload['tick_states'] = []

  for (const se of payload.visible_exercises) {
    // Sets on a skipped exercise are omitted from the strip and the totals --
    // matching _live_data, which skips them outright.
    if (se.skipped) continue
    for (const s of se.sets) {
      total += 1
      if (s.completed) {
        done += 1
        ticks.push('done')
        volume += s.weight * s.reps * (se.is_unilateral ? 2 : 1)
      } else {
        ticks.push('open')
      }
    }
  }

  // 'now' is the first open set of the live exercise, the one the steppers are
  // bound to. Marked after the fact so the walk above stays simple.
  const live = payload.visible_exercises.find((se) => se.id === payload.live_id)
  if (live && !live.skipped) {
    let index = 0
    for (const se of payload.visible_exercises) {
      if (se.skipped) continue
      for (const s of se.sets) {
        if (se.id === live.id && !s.completed) { ticks[index] = 'now'; break }
        index += 1
      }
      if (se.id === live.id) break
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
  weight: number,
  reps: number,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => ({
      ...se,
      sets: se.sets.map((s) =>
        s.id === setId ? { ...s, completed, weight, reps } : s),
    })),
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
 *  skipped exercise's sets leave the strip entirely. */
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

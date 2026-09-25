import type { LiveExercise, LiveSet, RoutinePlan, SessionDetailPayload } from './types'
import { instant } from '../format'
import { REST_MAX } from '../settings/values'

/**
 * Local guesses at what a write will do, applied before the server answers.
 *
 * Only for writes whose effect is computable honestly and completely. The ones
 * that are not -- adding or replacing an exercise, the deload -- have no entry
 * here and wait for the server. A screen that is briefly a lie is worse than
 * one that is briefly slow, and `_live_context` deliberately owns the
 * live-exercise rule because three surfaces have to agree on it: these leave
 * `live_id` alone, and the server's answer moves it. Only when that answer
 * cannot come -- offline, with the outbox waiting (B6) -- does `relive` apply
 * the same rule here. (Reordering is the one write that LOOKS like it belongs
 * in the first group but does not: the row order is the user's explicit
 * intent, so it is honest.)
 *
 * Each takes the moment the lifter acted as its last argument where time
 * matters (the rest): the outbox applies a write again on every answer that
 * comes in before it lands, and "now" would move its rest each time.
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

/** Naive UTC, as the server sends it. */
function naive(ms: number): string {
  return new Date(ms).toISOString().replace('Z', '')
}

/** The rest a set logged at `at` starts, as workout._schedule_rest starts it:
 *  from the set's own moment, as long as the row's rest -- this workout's
 *  own, else the lifter's setting. No rest ends the one running. It used to
 *  start only when the server answered, so on a slow network the band came
 *  late and offline it never came (G-072). */
function startRest(
  payload: SessionDetailPayload, se: LiveExercise, setId: number, at: number,
): SessionDetailPayload {
  const seconds = se.rest_seconds ?? se.rest_setting
  if (!seconds) return endRest(payload)
  const ends = at + seconds * 1000
  return {
    ...payload,
    resting: ends > Date.now(),
    rest_total_seconds: seconds,
    session: { ...payload.session, rest_ends_at: naive(ends), resting_set_id: setId },
  }
}

/** A set reopened or deleted is no record: the server's answer says so too.
 *  Drawn until then -- offline, for good -- an open chip stayed gold. */
function dropRecord(payload: SessionDetailPayload, setId: number): SessionDetailPayload {
  if (!payload.record_set_ids.includes(setId)) return payload
  const details = { ...payload.record_details }
  delete details[String(setId)]
  return {
    ...payload,
    record_set_ids: payload.record_set_ids.filter((id) => id !== setId),
    record_details: details,
  }
}

/** No rest running, and no band: its set was reopened or deleted. */
function endRest(payload: SessionDetailPayload): SessionDetailPayload {
  return {
    ...payload,
    resting: false,
    rest_total_seconds: 0,
    session: { ...payload.session, rest_ends_at: null, resting_set_id: null },
  }
}

/** Ticking a set off, or putting it back. The one write that happens dozens of
 *  times per workout, and the only one where the round trip is felt. `at`:
 *  when the lifter tapped, which the rest runs from. */
export function toggleSet(
  payload: SessionDetailPayload,
  setId: number,
  completed: boolean,
  weight: number | null,
  reps: number | null,
  at: number = Date.now(),
): SessionDetailPayload {
  const owner = payload.visible_exercises.find((se) => se.sets.some((s) => s.id === setId))
  const was = owner?.sets.find((s) => s.id === setId)
  const next = retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => {
      const index = se.sets.findIndex((s) => s.id === setId)
      if (index === -1) return se
      // Logging a set fills the blanks of the open sets after it -- the
      // server does the same (workout._fill_blanks_after). Without it here
      // the next set flashed blank for the length of the request.
      const fills = completed && !se.sets[index]!.completed
      return {
        ...se,
        sets: se.sets.map((s, i) => {
          if (i === index) return { ...s, completed, weight, reps }
          if (fills && i > index && !s.completed && (s.weight === null || s.reps === null)) {
            return { ...s, weight: s.weight ?? weight, reps: s.reps ?? reps }
          }
          return s
        }),
      }
    }),
  })
  if (owner === undefined || was === undefined) return next
  // A set already logged, logged again, keeps the rest it is part-way
  // through -- the server's duplicate rule. A blank cannot be logged.
  if (completed && !was.completed && weight !== null && reps !== null) {
    return startRest(next, owner, setId, at)
  }
  if (completed) return next
  const open = dropRecord(next, setId)
  return payload.session.resting_set_id === setId ? endRest(open) : open
}

/** `added` appended to its row, or null when the payload already holds its
 *  key: the server answered a copy of the write first. */
function append(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  added: LiveSet,
): SessionDetailPayload | null {
  const se = payload.visible_exercises.find((row) => row.id === sessionExerciseId)
  if (se === undefined || se.sets.some((s) => s.key === added.key)) return null
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((row) =>
      row.id === sessionExerciseId ? { ...row, sets: [...row.sets, added] } : row),
  })
}

/** A set appended already done: "Satz geschafft" with no open set left.
 *  `tempId` names it until the server does -- negative, so it is never a
 *  real id -- and `key` is how the outbox finds the real one in the answer
 *  (SessionSet.client_key). */
export function addSet(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  weight: number,
  reps: number,
  key: string,
  tempId: number,
  at: number = Date.now(),
): SessionDetailPayload {
  const next = append(payload, sessionExerciseId,
    { id: tempId, weight, reps, completed: true, base_weight: null, key })
  if (next === null) return payload
  const se = payload.visible_exercises.find((row) => row.id === sessionExerciseId)!
  return startRest(next, se, tempId, at)
}

/** The sheet's "Anhängen" (Q2, G-060): a set planned open behind the others,
 *  ticked on the card when it is lifted. Nothing was lifted, so no rest
 *  starts; named as addSet's. */
export function planSet(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  weight: number,
  reps: number,
  key: string,
  tempId: number,
): SessionDetailPayload {
  return append(payload, sessionExerciseId,
    { id: tempId, weight, reps, completed: false, base_weight: null, key }) ?? payload
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
  const next = dropRecord(retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => ({
      ...se,
      sets: se.sets.filter((s) => s.id !== setId),
    })),
  }), setId)
  // The server clears a rest whose set goes (gym_delete_set).
  return payload.session.resting_set_id === setId ? endRest(next) : next
}

/** Skipping is instant and reversible, and it changes the totals because a
 *  skipped exercise's open sets leave the strip; its done sets stay. The
 *  state wanted, not a flip: the outbox may apply and send it twice. */
export function toggleSkip(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
  skipped: boolean,
): SessionDetailPayload {
  return retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      se.id === sessionExerciseId ? { ...se, skipped } : se),
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

/** The workout's bodyweight and note, as gym_update_session_meta stores
 *  them: a key left out is left alone, a blank note is none. */
export function setSessionMeta(
  payload: SessionDetailPayload,
  meta: { bodyweightKg?: number | null; notes?: string },
): SessionDetailPayload {
  const session = { ...payload.session }
  if (meta.bodyweightKg !== undefined) session.bodyweight_kg = meta.bodyweightKg
  if (meta.notes !== undefined) session.notes = meta.notes.trim() || null
  return { ...payload, session }
}

/** Which exercise is live, by the server's own rule (workout._live_context),
 *  for a screen whose writes cannot reach the server (B6): offline, the
 *  answer that moves the card on never came, and the last set of an
 *  exercise left "Satz geschafft" appending to it for the rest of the
 *  workout.
 *
 *  The first visible row, not skipped, not fully logged; with everything
 *  logged, the last one still counting; with everything skipped, none. In a
 *  shared workout, the row the lifter has started stays live until it is
 *  done (keep_started) -- the server picks the most recently logged of two
 *  started rows, which needs stamps this payload does not carry, so the one
 *  live now wins here, else the first. */
export function relive(payload: SessionDetailPayload): SessionDetailPayload {
  const rows = payload.visible_exercises
  const logged = (se: LiveExercise) => se.sets.length > 0 && se.sets.every((s) => s.completed)
  let live: LiveExercise | undefined
  if (payload.session_is_shared) {
    const started = rows.filter((se) =>
      !se.skipped && se.sets.some((s) => s.completed) && !logged(se))
    live = started.find((se) => se.id === payload.live_id) ?? started[0]
  }
  live ??= rows.find((se) => !se.skipped && !logged(se))
  live ??= rows.filter((se) => !se.skipped).at(-1)
  if ((live?.id ?? null) === payload.live_id) return payload
  return retally({
    ...payload,
    live_id: live?.id ?? null,
    live_index: live === undefined ? 0 : rows.indexOf(live) + 1,
    live_increment: live?.increment ?? payload.live_increment,
    live_floor: live?.floor ?? null,
  })
}

/** An exercise removed while its undo runs (G-067): gone from the queue and
 *  every total, and the card on the next one by the live rule -- it stayed
 *  live for the five seconds, and a set logged on it then went with it (B7
 *  review). Not a write's guess -- the remove is sent when the window ends,
 *  and not drawn then (writes.ts) -- so the live rule is applied here as
 *  offline (`relive`). */
export function removeExercise(
  payload: SessionDetailPayload,
  sessionExerciseId: number,
): SessionDetailPayload {
  const doomed = payload.visible_exercises.find((se) => se.id === sessionExerciseId)
  if (doomed === undefined) return payload
  let next = retally({
    ...payload,
    visible_exercises: payload.visible_exercises.filter((se) => se !== doomed),
  })
  // The server clears a rest whose set goes with the row.
  if (doomed.sets.some((s) => s.id === payload.session.resting_set_id)) next = endRest(next)
  next = relive(next)
  const index = next.visible_exercises.findIndex((se) => se.id === next.live_id)
  return { ...next, live_index: index + 1 }
}

/** A swap taken back (G-068): the original in its substitute's place, as the
 *  server puts it back, while the remove is on its way. Nothing once the
 *  answer has the original: the substitute is gone from it. */
export function unswap(
  payload: SessionDetailPayload,
  substituteId: number,
  original: LiveExercise,
): SessionDetailPayload {
  const at = payload.visible_exercises.findIndex((se) => se.id === substituteId)
  if (at === -1) return payload
  const next = relive(retally({
    ...payload,
    visible_exercises: payload.visible_exercises.map((se, i) => (i === at ? original : se)),
  }))
  const index = next.visible_exercises.findIndex((se) => se.id === next.live_id)
  return { ...next, live_index: index + 1 }
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

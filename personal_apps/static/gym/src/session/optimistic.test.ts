import { describe, expect, it } from 'vitest'
import {
  addSet, deleteSet, planSet, relive, removeExercise, reorderExercises, setExerciseMeta, setRest,
  setRoutinePlan, setSessionMeta, shiftRest, skipRest, toggleSet, toggleSkip, unswap, updateSet,
} from './optimistic'
import { payload } from './types.test-d'
import type { SessionDetailPayload } from './types'
import { REST_MAX } from '../settings/values'

const live = payload.visible_exercises.find((se) => se.id === payload.live_id)!
const openSet = live.sets.find((s) => !s.completed)!
const doneSet = live.sets.find((s) => s.completed)!

describe('optimistic toggleSet', () => {
  it('ticks the set and moves every tally with it', () => {
    // One fact counted three ways. Updating the strip without the number above
    // it would show them disagreeing for the length of a round trip.
    const next = toggleSet(payload, openSet.id, true, openSet.weight, openSet.reps)
    expect(next.sets_done).toBe(payload.sets_done + 1)
    expect(next.sets_open).toBe(payload.sets_open - 1)
    expect(next.tick_states.filter((t) => t === 'done'))
      .toHaveLength(payload.sets_done + 1)
    expect(next.session_volume).toBeGreaterThan(payload.session_volume)
  })

  it('un-ticks symmetrically', () => {
    const next = toggleSet(payload, doneSet.id, false, doneSet.weight, doneSet.reps)
    expect(next.sets_done).toBe(payload.sets_done - 1)
    expect(next.session_volume).toBeLessThan(payload.session_volume)
  })

  it('records the numbers the steppers held, not the ones the set had', () => {
    const next = toggleSet(payload, openSet.id, true, 99, 3)
    const updated = next.visible_exercises
      .flatMap((se) => se.sets).find((s) => s.id === openSet.id)!
    expect(updated.weight).toBe(99)
    expect(updated.reps).toBe(3)
  })

  it('counts a unilateral set twice, as the server does', () => {
    // Both sides are constructed rather than one being taken from the fixture:
    // the fixture's live exercise happens to BE unilateral, so using it as the
    // bilateral baseline compared a thing against itself and passed for the
    // wrong reason until it didn't.
    const withFlag = (is_unilateral: boolean) => ({
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, is_unilateral } : se),
    })

    const bilateralBase = withFlag(false)
    const perSideBase = withFlag(true)
    const bilateral = toggleSet(bilateralBase, openSet.id, true, 50, 10)
    const perSide = toggleSet(perSideBase, openSet.id, true, 50, 10)

    // retally recomputes from scratch, so compare the recomputed totals
    // against each other rather than against the server's original figure.
    expect(perSide.session_volume).toBe(bilateral.session_volume * 2)
  })

  it('fills the blanks after a logged set, as the server does', () => {
    // workout._fill_blanks_after: a blank is a plan waiting for its number,
    // and the set just lifted gives it one. Without this the next set
    // flashed blank for the length of the request.
    const blankPlan = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) => (se.id !== live.id ? se : {
        ...se,
        sets: se.sets.map((s) => ({ ...s, completed: false, weight: null, reps: null })),
      })),
    }
    const [first, ...rest] = blankPlan.visible_exercises.find((se) => se.id === live.id)!.sets
    const next = toggleSet(blankPlan, first!.id, true, 40, 10)
    const sets = next.visible_exercises.find((se) => se.id === live.id)!.sets
    expect(sets.map((s) => [s.weight, s.reps, s.completed])).toEqual([
      [40, 10, true], ...rest.map(() => [40, 10, false])])

    // Putting it back open takes nothing back: those numbers are the plan now.
    const undone = toggleSet(next, first!.id, false, 40, 10)
    expect(undone.visible_exercises.find((se) => se.id === live.id)!.sets
      .slice(1).map((s) => s.weight)).toEqual(rest.map(() => 40))
  })

  it('leaves the total alone, because ticking a set does not create one', () => {
    const next = toggleSet(payload, openSet.id, true, openSet.weight, openSet.reps)
    expect(next.sets_total).toBe(payload.sets_total)
  })
})

describe('optimistic updateSet', () => {
  it('changes the numbers without changing whether it is done', () => {
    const next = updateSet(payload, doneSet.id, 80, 5)
    const updated = next.visible_exercises
      .flatMap((se) => se.sets).find((s) => s.id === doneSet.id)!
    expect(updated).toMatchObject({ weight: 80, reps: 5, completed: true })
    expect(next.sets_done).toBe(payload.sets_done)
  })
})

describe('optimistic deleteSet', () => {
  it('removes it and shortens the strip', () => {
    const next = deleteSet(payload, openSet.id)
    expect(next.sets_total).toBe(payload.sets_total - 1)
    expect(next.tick_states).toHaveLength(payload.tick_states.length - 1)
    expect(next.visible_exercises.flatMap((se) => se.sets)
      .some((s) => s.id === openSet.id)).toBe(false)
  })
})

describe('optimistic toggleSkip', () => {
  it('keeps a skipped exercise\'s done sets and drops its open ones', () => {
    // Matching _live_data (Q1): what was lifted before the skip was lifted,
    // and the sets still open are not going to be.
    const before = payload.tick_states.length
    const open = live.sets.filter((s) => !s.completed).length
    const next = toggleSkip(payload, live.id, true)
    expect(next.visible_exercises.find((se) => se.id === live.id)!.skipped).toBe(true)
    expect(next.tick_states.length).toBe(before - open)
    expect(next.sets_done).toBe(payload.sets_done)
    expect(next.session_volume).toBe(payload.session_volume)
  })

  it('puts them back when un-skipped', () => {
    const skipped = payload.visible_exercises.find((se) => se.skipped)!
    const next = toggleSkip(payload, skipped.id, false)
    expect(next.tick_states.length)
      .toBe(payload.tick_states.length + skipped.sets.length)
  })
})

describe('optimistic retally', () => {
  it('counts the done sets of a replaced original in place (Q1)', () => {
    // The server carries them on the substitute; the retally must keep them,
    // or every tick would drop them until the server answered.
    const carried: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, replaced_sets_done: 2, replaced_volume: 1000 } : se),
    }
    const next = toggleSet(carried, openSet.id, true, 20, 8)
    expect(next.sets_done).toBe(payload.sets_done + 2 + 1)
    expect(next.sets_total).toBe(payload.sets_total + 2)
    expect(next.tick_states.slice(0, 2)).toEqual(['done', 'done'])
    expect(next.session_volume).toBe(payload.session_volume + 1000 + 20 * 8 * 2)
  })

  it('counts no done set without reps (G-038)', () => {
    const zero: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id
          ? { ...se, sets: se.sets.map((s) => (s.id === doneSet.id ? { ...s, reps: 0 } : s)) }
          : se),
    }
    const next = toggleSkip(toggleSkip(zero, live.id, true), live.id, false)
    expect(next.sets_done).toBe(payload.sets_done - 1)
    expect(next.has_completed_set).toBe(payload.sets_done - 1 > 0)
  })
})

describe('optimistic setExerciseMeta', () => {
  it('applies the note and the flag and touches nothing else', () => {
    const next = setExerciseMeta(payload, live.id, { pain: true, notes: 'Schulter' })
    const updated = next.visible_exercises.find((se) => se.id === live.id)!
    expect(updated.pain).toBe(true)
    expect(updated.notes).toBe('Schulter')
    expect(next.sets_done).toBe(payload.sets_done)
  })

  it('stores an empty note as null, matching the column', () => {
    const next = setExerciseMeta(payload, live.id, { pain: false, notes: '' })
    expect(next.visible_exercises.find((se) => se.id === live.id)!.notes).toBeNull()
  })
})

describe('what deliberately has no optimistic path', () => {
  it('does not guess at anything that moves which exercise is live', async () => {
    // Adding and replacing change the live-exercise decision, and that rule
    // lives in _live_context precisely because three surfaces have to agree
    // on it. Guessing locally would show a screen that is briefly a lie.
    // Reordering is IN the list on purpose: the row order is the user's
    // explicit intent, so it is honest -- reorderExercises leaves live_id
    // untouched and the server's answer still replaces it wholesale.
    // `relive` is that rule, for the one screen whose answer is not coming
    // (B6, offline) -- the outbox applies it only then -- and for an exercise
    // removed while its undo runs, which no answer covers until it is sent
    // (removeExercise, G-067), or a swap taken back, whose original the
    // screen still holds (unswap). A set planned on a row already done makes
    // it live again on the server (G-060): the same rule, the same answer.
    const module = await import('./optimistic')
    expect(Object.keys(module).sort()).toEqual(
      ['addSet', 'deleteSet', 'planSet', 'relive', 'removeExercise', 'reorderExercises',
        'setExerciseMeta', 'setRest', 'setRoutinePlan', 'setSessionMeta', 'shiftRest',
        'skipRest', 'toggleSet', 'toggleSkip', 'unswap', 'updateSet'])
  })
})

// B6: the outbox draws every write until it lands -- offline, for as long as
// that takes -- so each guess has to be what the server would answer.
const AT = Date.UTC(2026, 0, 5, 10, 0, 0) // long past: its rest is over
const naive = (ms: number) => new Date(ms).toISOString().replace('Z', '')

describe('the rest a logged set starts (G-072)', () => {
  it('runs from the tap, as long as the row\'s rest', () => {
    const next = toggleSet(payload, openSet.id, true, 60, 8, AT)
    expect(next.session.rest_ends_at).toBe(naive(AT + live.rest_setting! * 1000))
    expect(next.session.resting_set_id).toBe(openSet.id)
    expect(next.rest_total_seconds).toBe(live.rest_setting)
  })

  it('says it is over when the tap was longer ago than the rest', () => {
    expect(toggleSet(payload, openSet.id, true, 60, 8, AT).resting).toBe(false)
    expect(toggleSet(payload, openSet.id, true, 60, 8, Date.now()).resting).toBe(true)
  })

  it('takes this workout\'s own rest over the setting', () => {
    const own = withLive({ rest_seconds: 45 })
    expect(toggleSet(own, openSet.id, true, 60, 8, AT).session.rest_ends_at)
      .toBe(naive(AT + 45_000))
  })

  it('ends the rest running when the row has none, as _schedule_rest does', () => {
    const resting = toggleSet(payload, openSet.id, true, 60, 8, AT)
    const none = {
      ...resting,
      visible_exercises: resting.visible_exercises.map((se) =>
        (se.id === live.id ? { ...se, rest_seconds: null, rest_setting: null } : se)),
    }
    const next = toggleSet(none, live.sets[2]!.id, true, 60, 8, AT)
    expect(next.session.rest_ends_at).toBeNull()
    expect(next.session.resting_set_id).toBeNull()
  })

  it('keeps the rest of a set logged again', () => {
    const resting = toggleSet(payload, openSet.id, true, 60, 8, AT)
    expect(toggleSet(resting, doneSet.id, true, 60, 8, AT + 60_000).session)
      .toEqual(resting.session)
  })

  it('ends with its set reopened or deleted, and only then', () => {
    const resting = toggleSet(payload, openSet.id, true, 60, 8, AT)
    expect(toggleSet(resting, openSet.id, false, 60, 8).session.rest_ends_at).toBeNull()
    expect(deleteSet(resting, openSet.id).session.rest_ends_at).toBeNull()
    expect(toggleSet(resting, doneSet.id, false, 60, 8).session.rest_ends_at)
      .toBe(resting.session.rest_ends_at)
  })
})

function withLive(over: Partial<(typeof payload.visible_exercises)[number]>): SessionDetailPayload {
  return {
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      (se.id === live.id ? { ...se, ...over } : se)),
  }
}

describe('a record reopened or deleted', () => {
  it('is no record any more, as the server will answer', () => {
    expect(payload.record_set_ids).toContain(doneSet.id)
    for (const next of [
      toggleSet(payload, doneSet.id, false, 60, 8), deleteSet(payload, doneSet.id)]) {
      expect(next.record_set_ids).not.toContain(doneSet.id)
      expect(next.record_details[String(doneSet.id)]).toBeUndefined()
    }
  })
})

describe('optimistic addSet', () => {
  it('appends a done set under its temporary id and key, counted, with its rest', () => {
    const next = addSet(payload, live.id, 70, 5, 'k-1', -9, AT)
    const added = next.visible_exercises.find((se) => se.id === live.id)!.sets.at(-1)!
    expect(added).toEqual({ id: -9, weight: 70, reps: 5, completed: true, base_weight: null, key: 'k-1' })
    expect(next.sets_done).toBe(payload.sets_done + 1)
    expect(next.session_volume).toBe(payload.session_volume + 70 * 5 * 2) // one-sided: both sides count
    expect(next.session.resting_set_id).toBe(-9)
    expect(next.session.rest_ends_at).toBe(naive(AT + live.rest_setting! * 1000))
  })

  it('adds nothing when the answer already holds the set -- a copy landed first', () => {
    const landed = addSet(payload, live.id, 70, 5, 'k-1', 500, AT)
    expect(addSet(landed, live.id, 70, 5, 'k-1', -9, AT)).toBe(landed)
  })
})

describe('optimistic planSet (Q2, G-060)', () => {
  it('plans an open set behind the others: counted in the total, not as done, no rest', () => {
    const next = planSet(payload, live.id, 70, 5, 'k-1', -9)
    const sets = next.visible_exercises.find((se) => se.id === live.id)!.sets
    expect(sets.at(-1)).toEqual({ id: -9, weight: 70, reps: 5, completed: false, base_weight: null, key: 'k-1' })
    expect(sets).toHaveLength(live.sets.length + 1)
    expect(next.sets_total).toBe(payload.sets_total + 1)
    expect(next.sets_done).toBe(payload.sets_done)
    expect(next.session_volume).toBe(payload.session_volume)
    expect(next.tick_states).toHaveLength(payload.tick_states.length + 1)
    expect(next.session.rest_ends_at).toBe(payload.session.rest_ends_at)
    expect(next.session.resting_set_id).toBe(payload.session.resting_set_id)
  })

  it('adds nothing when the answer already holds the set', () => {
    const landed = planSet(payload, live.id, 70, 5, 'k-1', 500)
    expect(planSet(landed, live.id, 70, 5, 'k-1', -9)).toBe(landed)
  })
})

describe('optimistic toggleSkip, stated', () => {
  it('is the same applied twice as once: the outbox may do both', () => {
    const once = toggleSkip(payload, live.id, true)
    expect(toggleSkip(once, live.id, true)).toEqual(once)
  })
})

describe('optimistic setSessionMeta', () => {
  it('writes the fields sent and leaves the rest, a blank note as none', () => {
    const noted = setSessionMeta(payload, { notes: '  Knie  ' })
    expect(noted.session.notes).toBe('Knie')
    expect(noted.session.bodyweight_kg).toBe(payload.session.bodyweight_kg)
    const weighed = setSessionMeta(noted, { bodyweightKg: 81.5 })
    expect(weighed.session).toMatchObject({ notes: 'Knie', bodyweight_kg: 81.5 })
    expect(setSessionMeta(weighed, { notes: ' ', bodyweightKg: null }).session)
      .toMatchObject({ notes: null, bodyweight_kg: null })
  })
})

describe('relive: the live rule, for a screen whose answer is not coming', () => {
  // Both rows counting: exercise 10 live, 11 after it.
  const two: SessionDetailPayload = {
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) => ({ ...se, skipped: false })),
  }
  const other = two.visible_exercises.find((se) => se.id !== live.id)!
  const logAll = (p: SessionDetailPayload, seId: number) => p.visible_exercises
    .find((se) => se.id === seId)!.sets.filter((s) => !s.completed)
    .reduce((acc, s) => toggleSet(acc, s.id, true, 60, 8, AT), p)

  it('leaves a screen whose live row still has open sets alone', () => {
    expect(relive(two)).toBe(two)
  })

  it('moves on once the live row is logged, with that row\'s step and floor', () => {
    const next = relive(logAll(two, live.id))
    expect(next.live_id).toBe(other.id)
    expect(next.live_index).toBe(two.visible_exercises.indexOf(other) + 1)
    expect(next.live_increment).toBe(other.increment)
    expect(next.live_floor).toBe(other.floor)
    expect(next.tick_states).toContain('now')
  })

  it('passes over a skipped row', () => {
    const skipped = toggleSkip(logAll(two, live.id), other.id, true)
    expect(relive(skipped).live_id).toBe(live.id)
  })

  it('keeps the last counting row with everything logged, and none with everything skipped', () => {
    const done = logAll(logAll(two, live.id), other.id)
    expect(relive(done).live_id).toBe(two.visible_exercises.at(-1)!.id)
    const none = two.visible_exercises.reduce((acc, se) => toggleSkip(acc, se.id, true), two)
    expect(relive(none)).toMatchObject({ live_id: null, live_index: 0, live_floor: null })
  })

  it('keeps a started row live in a shared workout, the first rule aside', () => {
    // The partner's order put 11 first; the lifter had started 10.
    const shared: SessionDetailPayload = {
      ...two, session_is_shared: true,
      visible_exercises: [...two.visible_exercises].reverse(),
    }
    expect(relive(shared).live_id).toBe(live.id)
    expect(relive({ ...shared, session_is_shared: false }).live_id).toBe(other.id)
  })
})

describe('setRoutinePlan', () => {
  it("stores the routine's plan for the row, and guesses no target", () => {
    const plan = { sets: 4, rep_min: 8, rep_max: 12 }
    const next = setRoutinePlan(payload, 10, plan)
    expect(next.routine_plans).toEqual({ ...payload.routine_plans, '10': plan })
    // The target follows the plan, but it is the server's to work out.
    expect(next.next_targets).toBe(payload.next_targets)
  })
})

describe('setRest', () => {
  const se = payload.visible_exercises[0]!

  it("stores today's own rest", () => {
    const next = setRest(payload, se.id, 180)
    expect(next.visible_exercises[0]!.rest_seconds).toBe(180)
    expect(next.visible_exercises[1]).toBe(payload.visible_exercises[1])
  })

  it("stores the setting's own value as nothing, so the row follows the setting", () => {
    const today = setRest(payload, se.id, 180)
    expect(setRest(today, se.id, se.rest_setting!).visible_exercises[0]!.rest_seconds).toBeNull()
  })
})

describe('shiftRest', () => {
  // A 90-second rest with 60 left, at a fixed now.
  const now = Date.parse('2026-09-24T10:00:00Z')
  const resting: SessionDetailPayload = {
    ...payload,
    resting: true,
    rest_total_seconds: 90,
    session: { ...payload.session, rest_ends_at: '2026-09-24T10:01:00', resting_set_id: doneSet.id },
  }
  const endsAt = (p: SessionDetailPayload) => Date.parse(`${p.session.rest_ends_at}Z`)

  it('moves the end and the total together, as gym_shift_rest does', () => {
    const later = shiftRest(resting, 15, now)
    expect(endsAt(later) - endsAt(resting)).toBe(15_000)
    expect(later.rest_total_seconds).toBe(105)

    const sooner = shiftRest(resting, -15, now)
    expect(endsAt(resting) - endsAt(sooner)).toBe(15_000)
    expect(sooner.rest_total_seconds).toBe(75)
  })

  it('ends the rest when the step goes past its end, as a skip leaves it', () => {
    const almost = { ...resting, session: { ...resting.session, rest_ends_at: '2026-09-24T10:00:10' } }
    const over = shiftRest(almost, -15, now)
    expect(over.resting).toBe(false)
    expect(endsAt(over)).toBe(now)
    expect(over.session.resting_set_id).toBe(doneSet.id)
    expect(over.rest_total_seconds).toBe(0)
  })

  it('stops at the longest rest there is', () => {
    const long = { ...resting, rest_total_seconds: 595 }
    expect(shiftRest(long, 15, now).rest_total_seconds).toBe(REST_MAX)
    expect(shiftRest(shiftRest(long, 15, now), 15, now).rest_total_seconds).toBe(REST_MAX)
  })

  it('never shortens a rest already longer than that, and "−15" still works on it', () => {
    // 15 minutes, saved before rests had a cap: 60 s left of it.
    const legacy = { ...resting, rest_total_seconds: 900 }
    expect(shiftRest(legacy, 15, now)).toEqual(legacy)
    expect(shiftRest(legacy, -15, now).rest_total_seconds).toBe(885)
  })

  it('leaves a payload with no rest running alone', () => {
    expect(shiftRest(payload, 15, now)).toBe(payload)
  })
})

describe('skipRest', () => {
  const now = Date.parse('2026-09-24T10:00:00.400Z')
  const resting: SessionDetailPayload = {
    ...payload,
    resting: true,
    rest_total_seconds: 90,
    session: { ...payload.session, rest_ends_at: '2026-09-24T10:01:00', resting_set_id: doneSet.id },
  }

  it('stamps the end now, in whole seconds, and keeps the set the rest followed', () => {
    const over = skipRest(resting, now)
    expect(over.resting).toBe(false)
    expect(over.rest_total_seconds).toBe(0)
    expect(Date.parse(`${over.session.rest_ends_at}Z`)).toBe(Date.parse('2026-09-24T10:00:00Z'))
    expect(over.session.resting_set_id).toBe(doneSet.id)
  })

  it('leaves a rest that is not running alone', () => {
    expect(skipRest(payload, now)).toBe(payload)
    const ranOut = { ...resting, session: { ...resting.session, rest_ends_at: '2026-09-24T09:59:00' } }
    expect(skipRest(ranOut, now)).toBe(ranOut)
  })
})

describe('removeExercise, drawn while its undo waits (B7 review)', () => {
  // Shown for the five seconds, the row stayed live and took the next
  // "Satz geschafft" -- and the set went with the exercise at the commit.
  const [bench, butterfly] = payload.visible_exercises
  const two: SessionDetailPayload = {
    ...payload, visible_exercises: [bench!, { ...butterfly!, skipped: false }],
  }

  it('drops the row, its sets from the tally, and hands the card to the next', () => {
    const next = removeExercise(two, bench!.id)
    expect(next.visible_exercises.map((se) => se.id)).toEqual([butterfly!.id])
    expect(next.live_id).toBe(butterfly!.id)
    expect(next.live_index).toBe(1)
    expect(next.sets_done).toBe(0)
    expect(next.tick_states).toHaveLength(butterfly!.sets.length)
  })

  it('ends a rest whose set goes with the row, as the server does', () => {
    const resting: SessionDetailPayload = {
      ...two, resting: true, rest_total_seconds: 90,
      session: { ...two.session, rest_ends_at: '2026-09-24T10:01:00', resting_set_id: doneSet.id },
    }
    expect(removeExercise(resting, bench!.id).resting).toBe(false)
    expect(removeExercise(resting, butterfly!.id).resting).toBe(true)
  })

  it('leaves a payload without the row as it is', () => {
    expect(removeExercise(two, 99_999)).toBe(two)
  })
})

describe('unswap, drawn while a swap\'s undo is on its way (B7 re-review)', () => {
  // Left live until the remove landed, the substitute took the next set,
  // and the remove took the set with it.
  const [bench, ...rest] = payload.visible_exercises
  const open = { id: 770, weight: 60, reps: 8, completed: false, base_weight: null, key: null }
  const swapped: SessionDetailPayload = {
    ...payload,
    live_id: 77,
    live_index: 1,
    sets_done: payload.sets_done - 1,
    visible_exercises: [
      { ...bench!, id: 77, exercise_id: 999, name: 'Ersatz', sets: [open], is_substitute: true },
      ...rest,
    ],
  }

  it('puts the original back in its place, with its sets and the card', () => {
    const next = unswap(swapped, 77, bench!)
    expect(next.visible_exercises.map((se) => se.id)).toEqual(payload.visible_exercises.map((se) => se.id))
    expect(next.live_id).toBe(bench!.id)
    expect(next.live_index).toBe(1)
    expect(next.sets_done).toBe(payload.sets_done)
    expect(next.sets_total).toBe(payload.sets_total)
    expect(next.tick_states).toEqual(payload.tick_states)
  })

  it('counts the original back in while the card stays on another lift', () => {
    // The card does not move, so nothing else recounts: the totals must.
    const [butterfly] = rest
    const away: SessionDetailPayload = {
      ...payload,
      sets_done: -1,
      sets_total: -1,
      tick_states: [],
      visible_exercises: [bench!, { ...butterfly!, id: 77, sets: [open], is_substitute: true }],
    }
    const next = unswap(away, 77, butterfly!)
    expect(next.live_id).toBe(payload.live_id)
    expect(next.sets_done).toBe(payload.sets_done)
    expect(next.sets_total).toBe(payload.sets_total)
    expect(next.tick_states).toEqual(payload.tick_states)
  })

  it('leaves an answer without the substitute as it is', () => {
    expect(unswap(payload, 77, bench!)).toBe(payload)
  })
})

describe('reorderExercises', () => {
  it('reorders the rows, renumbers positions, and leaves live_id alone', () => {
    const ids = payload.visible_exercises.map((se) => se.id)
    const flipped = [...ids].reverse()
    const next = reorderExercises(payload, flipped)
    expect(next.visible_exercises.map((se) => se.id)).toEqual(flipped)
    expect(next.visible_exercises.map((se) => se.position))
      .toEqual(flipped.map((_, i) => i + 1))
    expect(next.live_id).toBe(payload.live_id)
  })

  it('keeps a row the order list missed instead of dropping it', () => {
    const ids = payload.visible_exercises.map((se) => se.id)
    const next = reorderExercises(payload, ids.slice(1))
    expect(next.visible_exercises.map((se) => se.id))
      .toEqual([...ids.slice(1), ids[0]])
  })
})

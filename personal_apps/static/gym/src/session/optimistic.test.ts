import { describe, expect, it } from 'vitest'
import {
  deleteSet, reorderExercises, setExerciseMeta, setRest, shiftRest, skipRest, toggleSet, toggleSkip,
  updateSet,
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
    const next = toggleSkip(payload, live.id)
    expect(next.visible_exercises.find((se) => se.id === live.id)!.skipped).toBe(true)
    expect(next.tick_states.length).toBe(before - open)
    expect(next.sets_done).toBe(payload.sets_done)
    expect(next.session_volume).toBe(payload.session_volume)
  })

  it('puts them back when un-skipped', () => {
    const skipped = payload.visible_exercises.find((se) => se.skipped)!
    const next = toggleSkip(payload, skipped.id)
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
    const next = toggleSkip(toggleSkip(zero, live.id), live.id)
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
    const module = await import('./optimistic')
    expect(Object.keys(module).sort()).toEqual(
      ['deleteSet', 'reorderExercises', 'setExerciseMeta', 'setRest', 'shiftRest', 'skipRest', 'toggleSet',
        'toggleSkip', 'updateSet'])
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

import { describe, expect, it } from 'vitest'
import { deleteSet, reorderExercises, setExerciseMeta, toggleSet, toggleSkip, updateSet } from './optimistic'
import { payload } from './types.test-d'

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
  it('takes a skipped exercise sets out of the strip entirely', () => {
    // Matching _live_data, which skips them outright -- so skipping changes
    // the totals, not just a class on a row.
    const before = payload.tick_states.length
    const next = toggleSkip(payload, live.id)
    expect(next.visible_exercises.find((se) => se.id === live.id)!.skipped).toBe(true)
    expect(next.tick_states.length).toBe(before - live.sets.length)
  })

  it('puts them back when un-skipped', () => {
    const skipped = payload.visible_exercises.find((se) => se.skipped)!
    const next = toggleSkip(payload, skipped.id)
    expect(next.tick_states.length)
      .toBe(payload.tick_states.length + skipped.sets.length)
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
      ['deleteSet', 'reorderExercises', 'setExerciseMeta', 'toggleSet',
        'toggleSkip', 'updateSet'])
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

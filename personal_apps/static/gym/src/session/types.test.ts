import { describe, expect, it } from 'vitest'
import fixture from './__fixtures__/session-payload.json'

/**
 * types.test-d.ts asserts the fixture against the types at compile time, but
 * one field cannot be checked that way: an imported JSON string[] never infers
 * as a union, so tick_states is narrowed with a cast there. This checks that
 * cast against the real values, which is the only thing standing between the
 * cast and a lie.
 */
describe('the session payload fixture', () => {
  it('only contains tick states the union allows', () => {
    const allowed = new Set(['done', 'now', 'open'])
    const unexpected = fixture.tick_states.filter((t) => !allowed.has(t))
    expect(unexpected).toEqual([])
  })

  it('omits sets belonging to a skipped exercise', () => {
    // The route counts ticks only for exercises it did not skip, so the strip
    // is shorter than the sum of every exercise's sets. A component that
    // zipped ticks against all sets would silently misalign.
    const everySet = fixture.visible_exercises
      .reduce((n, se) => n + se.sets.length, 0)
    const skippedSets = fixture.visible_exercises
      .filter((se) => se.skipped)
      .reduce((n, se) => n + se.sets.length, 0)

    expect(skippedSets).toBeGreaterThan(0)
    expect(fixture.tick_states).toHaveLength(everySet - skippedSets)
    expect(fixture.sets_total).toBe(everySet - skippedSets)
  })

  it('keys suggestions by SessionExercise id as a string', () => {
    const ids = fixture.visible_exercises.map((se) => String(se.id))
    for (const key of Object.keys(fixture.suggestions)) {
      expect(ids).toContain(key)
    }
  })

  it('is rich enough to render the components against', () => {
    // A one-exercise fixture cannot exercise the queue, the live/not-live
    // split, or the tick strip's grouping -- the generator builds two on
    // purpose and this stops a later regeneration from quietly shrinking it.
    expect(fixture.visible_exercises.length).toBeGreaterThanOrEqual(2)
    expect(fixture.visible_exercises.some((se) => se.skipped)).toBe(true)
    expect(fixture.live_id).not.toBeNull()
    expect(fixture.sets_done).toBeGreaterThan(0)
  })
})

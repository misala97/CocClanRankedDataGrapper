// Compile-time check, not a runtime test: the fixture captured from the real
// endpoint must satisfy the hand-written types. `npx tsc --noEmit` fails if a
// field is missing or mistyped, which is how step 1's five wrong fields would
// have been caught before any component was built on them.
//
// Named .test-d.ts so vitest does not try to run it -- there is nothing to
// run. Its whole value is that tsc reads it.
//
// NO `as SessionDetailPayload` anywhere in this file. A cast silences exactly
// the mismatch this exists to find; the plain assignment below is the check.
import fixture from './__fixtures__/session-payload.json'
import type { SessionDetailPayload, TickState } from './types'

// tick_states is the one field TypeScript cannot check from JSON: an imported
// array of strings infers as string[], never as a union, however narrow the
// real values are. Narrowed here and then verified at RUNTIME in
// types.test.ts, so the cast is checked rather than trusted.
export const payload: SessionDetailPayload = {
  ...fixture,
  tick_states: fixture.tick_states as TickState[],
}

// The properties most likely to be got wrong, exported so noUnusedLocals does
// not reject them and so a change to any of them is a type error here rather
// than a runtime surprise inside a component.
export const liveId: number | null = payload.live_id
export const pain: boolean = payload.visible_exercises[0]!.pain
export const ticks: TickState[] = payload.tick_states
export const suggestionKeyIsAString: string = Object.keys(payload.suggestions)[0]!
export const recordIds: number[] = payload.record_set_ids
export const ready: null | { sets: number } = payload.ready_for_more

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
import type { LiveRecord, SeedSource, SessionDetailPayload, TickState } from './types'

// tick_states is one of three fields TypeScript cannot check from JSON: an
// imported array of strings infers as string[], never as a union, however
// narrow the real values are. seed_sources' `basis` and record_details' `kind`
// are the others, for the same reason. All three are narrowed here and then
// verified at RUNTIME in types.test.ts, so the casts are checked rather than
// trusted.
//
// record_details is empty in the current fixture, which is why the cast is not
// load-bearing yet -- it is here so that regenerating the fixture from a
// workout that DID set a record is not a confusing type error.
export const payload: SessionDetailPayload = {
  ...fixture,
  tick_states: fixture.tick_states as TickState[],
  seed_sources: fixture.seed_sources as Record<string, SeedSource | null>,
  record_details: fixture.record_details as Record<string, LiveRecord>,
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

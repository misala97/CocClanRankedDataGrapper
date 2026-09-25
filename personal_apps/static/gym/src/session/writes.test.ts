import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { Outbox, type OutboxHooks } from './outbox'
import * as optimistic from './optimistic'
import type { RoutinePlan, SessionDetailPayload } from './types'
import { payload } from './types.test-d'
import { writeSpecs } from './writes'

/**
 * The live workout's writes as the outbox sends them (B6, D6-A): which are
 * kept on the phone, what each sends, and that a write about a set drawn
 * before the server named it reaches the set the server made.
 */

afterEach(() => { vi.restoreAllMocks() })

type Method = keyof typeof api
const spyOn = (method: Method) =>
  vi.spyOn(api as unknown as Record<string, (...args: unknown[]) => unknown>, method)

// One call of each kind, and the api method it goes out through.
const SAMPLES: Record<string, [Method, unknown[]]> = {
  toggleSet: ['toggleSet', [101, true, 60, 8]],
  addSet: ['addSet', [10, 60, 8, 'k1', -5]],
  updateSet: ['updateSet', [101, 62.5, 8]],
  deleteSet: ['deleteSet', [101]],
  toggleSkip: ['toggleSkip', [10, true]],
  exerciseMeta: ['setExerciseMeta', [10, { pain: true, notes: '' }]],
  setRest: ['setRest', [10, 90]],
  routinePlan: ['setRoutinePlan', [10, {} as RoutinePlan]],
  sessionMeta: ['setSessionMeta', [{ notes: 'Knie' }]],
  reorder: ['reorder', [[11, 10]]],
  skipRest: ['skipRest', []],
  shiftRest: ['shiftRest', [15]],
  addExercise: ['addExercise', [5]],
  removeExercise: ['removeExercise', [10]],
  replaceExercise: ['replaceExercise', [10, 5]],
  toggleDeload: ['toggleDeload', [true, 70]],
}

describe('writeSpecs', () => {
  it('keeps on the phone exactly the writes that state what they want -- safe to send twice', () => {
    // Not kept: "+15 s" is about its moment only; adding, removing and
    // swapping an exercise and the deload move what is live or the weights,
    // which is the server's to decide.
    const specs = writeSpecs(1)
    expect(Object.keys(specs).filter((kind) => specs[kind]!.durable).sort()).toEqual([
      'addSet', 'deleteSet', 'exerciseMeta', 'reorder', 'routinePlan', 'sessionMeta', 'setRest',
      'skipRest', 'toggleSet', 'toggleSkip', 'updateSet',
    ])
  })

  it('sends every write with the moment it was made, and an add with its key', async () => {
    const specs = writeSpecs(7)
    expect(Object.keys(SAMPLES).sort()).toEqual(Object.keys(specs).sort())
    for (const [kind, [method, args]] of Object.entries(SAMPLES)) {
      const spy = spyOn(method).mockResolvedValue(payload)
      await specs[kind]!.send(args, 4242)
      expect(spy.mock.calls.at(-1)!.at(-1), kind).toBe(4242)
    }
    expect(api.addSet).toHaveBeenCalledWith(10, 60, 8, 'k1', 4242)
  })

  it('sends each write about a set drawn before the server named it to the set the server made', async () => {
    // Added offline, then corrected, reopened and deleted, all before the
    // add got through: each has to reach set 900, not the drawn -5.
    let state: SessionDetailPayload = payload
    spyOn('addSet').mockImplementation(async (...args: unknown[]) => {
      const [seId, weight, reps, key, at] = args as [number, number, number, string, number]
      state = optimistic.addSet(state, seId, weight, reps, key, 900, at)
      return state
    })
    const sent: [string, unknown][] = []
    for (const method of ['updateSet', 'toggleSet', 'deleteSet'] as const) {
      spyOn(method).mockImplementation(async (setId: unknown) => { sent.push([method, setId]); return state })
    }
    const outbox = new Outbox(payload, hooks())
    outbox.start()
    void outbox.enqueue('addSet', [10, 60, 8, 'k1', -5])
    void outbox.enqueue('updateSet', [-5, 62.5, 8])
    void outbox.enqueue('toggleSet', [-5, false, 62.5, 8])
    await outbox.enqueue('deleteSet', [-5])
    expect(sent).toEqual([['updateSet', 900], ['toggleSet', 900], ['deleteSet', 900]])
    outbox.stop()
  })
})

function hooks(): OutboxHooks {
  let ids = 0
  return {
    specs: writeSpecs(payload.session.id),
    shelf: {
      read: () => ({ entries: [], stale: 0 }), put: () => true, drop: () => {},
      get: () => undefined, oldest: () => null, list: () => [],
      name: () => {}, named: () => null,
    },
    show: () => {},
    status: () => {},
    hold: () => {},
    begin: () => {},
    end: () => {},
    succeed: () => {},
    fail: () => {},
    fetchFresh: () => Promise.resolve(payload),
    finished: () => {},
    gone: () => {},
    reload: () => {},
    drained: () => {},
    relive: (p) => p,
    exclusive: (run) => run(),
    now: () => 1_000_000,
    newId: () => `w${++ids}`,
  }
}

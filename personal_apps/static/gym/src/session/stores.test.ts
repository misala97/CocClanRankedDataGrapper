import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  failureCheckpoint, useOutbox, usePush, useSaveState, useSheets, useWorkoutUi,
} from './stores'

/**
 * The eleven pieces of state the server cannot know. Every one of them was
 * destroyed by refreshBody and rebuilt by hand afterwards; these stores are
 * where that stops being necessary.
 *
 * Tested through getState()/setState() rather than by rendering: none of this
 * is React-specific, and a store that needs a component to be exercised has
 * already leaked into the view.
 */
beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
  useOutbox.setState(useOutbox.getInitialState(), true)
})

describe('useSheets', () => {
  it('opens one sheet at a time', () => {
    // The old code called current.close() before showModal(): a sheet on top
    // of a sheet is not a state this design has.
    useSheets.getState().open('sheet-session')
    useSheets.getState().open('sheet-deload')
    expect(useSheets.getState().openId).toBe('sheet-deload')
  })

  it('closes', () => {
    useSheets.getState().open('sheet-session')
    useSheets.getState().close()
    expect(useSheets.getState().openId).toBeNull()
  })

  it('remembers which pane a sheet was showing', () => {
    useSheets.getState().showPane('sheet-add-exercise', 'create')
    expect(useSheets.getState().paneOf('sheet-add-exercise')).toBe('create')
  })

  it('resets a sheet to its first pane when reopened', () => {
    // Reopening the add sheet on the "invent a new exercise" pane would be
    // answering a question the lifter did not ask this time.
    useSheets.getState().showPane('sheet-add-exercise', 'create')
    useSheets.getState().open('sheet-add-exercise')
    expect(useSheets.getState().paneOf('sheet-add-exercise')).toBeNull()
  })

  it('keeps the add-list query across a close and reopen', () => {
    // Matches the old behaviour exactly: refreshBody replaced #exadd-list but
    // never #exadd-search, and closing a <dialog> does not clear its inputs,
    // so the typed query survived. Changing that here would be a silent
    // behaviour change dressed up as a port.
    useSheets.getState().setAddQuery('bank')
    useSheets.getState().open('sheet-add-exercise')
    useSheets.getState().close()
    useSheets.getState().open('sheet-add-exercise')
    expect(useSheets.getState().addQuery).toBe('bank')
  })
})

describe('useWorkoutUi', () => {
  it('starts locked and toggles', () => {
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(false)
    useWorkoutUi.getState().toggleReorder()
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(true)
    useWorkoutUi.getState().toggleReorder()
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(false)
  })

  it('survives anything the server sends', () => {
    // The whole point. The server has no notion of this mode, so every
    // in-place mutation used to reset it -- applyReorderUI existed only to
    // put it back.
    useWorkoutUi.getState().toggleReorder()
    useSaveState.getState().begin()
    useSaveState.getState().end()
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(true)
  })
})

describe('useSaveState', () => {
  it('counts saves rather than flagging them', () => {
    // Two concurrent saves need two ends. A boolean would clear the sweep on
    // the first one while a second write was still in flight -- the old code
    // used an integer for exactly this reason.
    useSaveState.getState().begin()
    useSaveState.getState().begin()
    useSaveState.getState().end()
    expect(useSaveState.getState().pending).toBe(1)
    useSaveState.getState().end()
    expect(useSaveState.getState().pending).toBe(0)
  })

  it('never counts below zero', () => {
    useSaveState.getState().end()
    expect(useSaveState.getState().pending).toBe(0)
  })

  it('records a failure with the retry that produced it', () => {
    const retry = vi.fn()
    useSaveState.getState().fail('set-1', 'Keine Antwort vom Server', retry)
    const [error] = useSaveState.getState().errors
    expect(error?.message).toBe('Keine Antwort vom Server')
    error?.retry?.()
    expect(retry).toHaveBeenCalledOnce()
  })

  it('keeps every failed write, not only the last one (G-139)', () => {
    // Each failed write was already rolled back. One slot kept only the
    // newest, and ANY later success emptied it -- earlier losses vanished
    // with no banner.
    useSaveState.getState().fail('set-1', 'Keine Antwort vom Server', vi.fn())
    useSaveState.getState().fail('set-2', 'Keine Antwort vom Server', vi.fn())
    useSaveState.getState().succeed('set-3')
    expect(useSaveState.getState().errors.map((e) => e.key)).toEqual(['set-1', 'set-2'])
  })

  it('holds one entry per write, cleared when that write lands', () => {
    useSaveState.getState().fail('set-1', 'x', vi.fn())
    useSaveState.getState().fail('set-1', 'y', vi.fn())
    expect(useSaveState.getState().errors.map((e) => e.message)).toEqual(['y'])
    useSaveState.getState().succeed('set-1')
    expect(useSaveState.getState().errors).toEqual([])
  })

  it('sends every retryable failure once, and keeps the refused ones', () => {
    const first = vi.fn()
    const second = vi.fn()
    useSaveState.getState().fail('a', 'Keine Antwort vom Server', first)
    useSaveState.getState().fail('b', 'Gewicht: bitte 0 bis 1000 kg.', null)
    useSaveState.getState().fail('c', 'Keine Antwort vom Server', second)
    // Twice: the tap and the returning connection can both ask.
    useSaveState.getState().retryAll()
    useSaveState.getState().retryAll()
    expect(first).toHaveBeenCalledOnce()
    expect(second).toHaveBeenCalledOnce()
    expect(useSaveState.getState().errors.map((e) => e.key)).toEqual(['b'])
  })

  it('lets a fresh page answer every failure when one needs it (B4 review)', () => {
    // A stale token or a lapsed login fails every write alike: resending
    // the others first only raced the reload.
    const resend = vi.fn()
    const reload = vi.fn()
    useSaveState.getState().fail('a', 'Keine Antwort vom Server', resend)
    useSaveState.getState().fail('b', 'Bitte neu anmelden', reload, 'reload')
    useSaveState.getState().retryAll()
    expect(reload).toHaveBeenCalledOnce()
    expect(resend).not.toHaveBeenCalled()
  })

  it('resends only what resending can fix, and leaves the reload to the lifter (B4 review)', () => {
    const resend = vi.fn()
    const reload = vi.fn()
    useSaveState.getState().fail('a', 'Keine Antwort vom Server', resend)
    useSaveState.getState().fail('b', 'Bitte neu anmelden', reload, 'reload')
    useSaveState.getState().resendAll()
    expect(resend).toHaveBeenCalledOnce()
    expect(reload).not.toHaveBeenCalled()
    expect(useSaveState.getState().errors.map((e) => e.key)).toEqual(['b'])
  })

  it('resends a write that is new work each time only on the lifter\'s say-so (B4 re-review)', () => {
    // Its answer may be what was lost: the set is in, and sent again by
    // itself it lands twice. The lifter sees the refetched screen and knows.
    const added = vi.fn()
    const moved = vi.fn()
    useSaveState.getState().fail('add', 'Keine Antwort vom Server', added, 'manual')
    useSaveState.getState().fail('order', 'Keine Antwort vom Server', moved)
    useSaveState.getState().resendAll()
    expect(moved).toHaveBeenCalledOnce()
    expect(added).not.toHaveBeenCalled()
    expect(useSaveState.getState().errors.map((e) => e.key)).toEqual(['add'])

    useSaveState.getState().retryAll()
    expect(added).toHaveBeenCalledOnce()
    expect(useSaveState.getState().errors).toEqual([])
  })

  it('lets a write answer the failures about a part of what it names (B4 re-review)', () => {
    // The set is gone: its lost tick and its lost numbers are moot.
    const { fail } = useSaveState.getState()
    fail('set-4:done', 'Keine Antwort vom Server', vi.fn())
    fail('set-4:numbers', 'Keine Antwort vom Server', vi.fn())
    fail('set-41:done', 'Keine Antwort vom Server', vi.fn())
    useSaveState.getState().succeed('set-4')
    expect(useSaveState.getState().errors.map((e) => e.key)).toEqual(['set-41:done'])
  })

  it('clears the errors on dismiss and on success -- NOT on settle', () => {
    useSaveState.getState().fail('a', 'x', () => {})
    useSaveState.getState().dismissErrors()
    expect(useSaveState.getState().errors).toEqual([])

    // A write that FINISHES is not a write that WORKED. end() runs from
    // onSettled, which fires straight after onError -- when end() also
    // cleared the error, the banner for a lost write was removed in the same
    // tick it appeared, so a failed save reverted in silence. Only a real
    // answer from the server clears it.
    useSaveState.getState().fail('a', 'y', () => {})
    useSaveState.getState().begin()
    useSaveState.getState().end()
    expect(useSaveState.getState().errors.map((e) => e.message)).toEqual(['y'])

    useSaveState.getState().succeed('a')
    expect(useSaveState.getState().errors).toEqual([])
  })
})

describe('useOutbox', () => {
  it('forgets a refused finish once everything is in, not before', () => {
    const { publish, refuseFinish } = useOutbox.getState()
    publish({ state: 'waiting', count: 2, setIds: [5] })
    refuseFinish()
    publish({ state: 'sending', count: 1, setIds: [] })
    expect(useOutbox.getState().finishRefused).toBe(true)
    publish({ state: 'idle', count: 0, setIds: [] })
    expect(useOutbox.getState().finishRefused).toBe(false)
  })
})

describe('failureCheckpoint', () => {
  // What "Beenden" waits on: leave only if nothing failed on the way out.
  it('is quiet when nothing failed after it, whatever failed before', () => {
    useSaveState.getState().fail('set-1', 'x', vi.fn())
    const failedSince = failureCheckpoint()
    expect(failedSince()).toBe(false)
    useSaveState.getState().succeed('set-1')
    expect(failedSince()).toBe(false)
  })

  it('sees a new failure, and the same write failing again', () => {
    useSaveState.getState().fail('set-1', 'x', vi.fn())
    const failedSince = failureCheckpoint()
    useSaveState.getState().fail('set-1', 'x', vi.fn())
    expect(failedSince()).toBe(true)

    const later = failureCheckpoint()
    useSaveState.getState().fail('set-2', 'y', null)
    expect(later()).toBe(true)
  })
})

describe('usePush', () => {
  it('is tri-state while the one-time probe is in flight', () => {
    // null means "not asked yet", and the row stays at its template default
    // until it resolves. Conflating that with false would offer to enable
    // push on a device that already has it.
    expect(usePush.getState().subscribed).toBeNull()
    usePush.getState().setSubscribed(false)
    expect(usePush.getState().subscribed).toBe(false)
    usePush.getState().setSubscribed(true)
    expect(usePush.getState().subscribed).toBe(true)
  })
})


describe('the stores as a boundary', () => {
  it('never imports the server payload types', async () => {
    // Structural, not advisory. Client state deriving from the payload is the
    // exact defect this port removes -- the old screen kept reorder mode and
    // the open sheet in DOM that refreshBody then replaced. If a store ever
    // needs a payload type, the state it is holding belongs in server state
    // instead, and this failing is the signal.
    const source = await import('./stores.ts?raw').then((m) => m.default as string)
    expect(source).not.toMatch(/from ['"]\.\/types['"]/)
    expect(source).not.toMatch(/SessionDetailPayload/)
  })
})

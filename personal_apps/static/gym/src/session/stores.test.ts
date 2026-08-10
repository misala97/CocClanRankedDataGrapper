import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePush, useSaveState, useSheets, useWorkoutUi } from './stores'

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

  it('records an error with the retry that produced it', () => {
    const retry = vi.fn()
    useSaveState.getState().fail('Keine Antwort vom Server', retry)
    expect(useSaveState.getState().error?.message).toBe('Keine Antwort vom Server')
    useSaveState.getState().error?.retry()
    expect(retry).toHaveBeenCalledOnce()
  })

  it('clears the error on dismiss and on the next success', () => {
    useSaveState.getState().fail('x', () => {})
    useSaveState.getState().dismissError()
    expect(useSaveState.getState().error).toBeNull()

    useSaveState.getState().fail('y', () => {})
    useSaveState.getState().begin()
    useSaveState.getState().end()
    expect(useSaveState.getState().error).toBeNull()
  })

  it('locks a form while its write is in flight', () => {
    // One write per form at a time. The confirm button is in the thumb zone
    // and its answer arrives a round trip later, so a second tap before the
    // first resolves is what a sweaty hand does -- not an edge case.
    const form = 'set-100'
    expect(useSaveState.getState().isLocked(form)).toBe(false)
    useSaveState.getState().lock(form)
    expect(useSaveState.getState().isLocked(form)).toBe(true)
    useSaveState.getState().unlock(form)
    expect(useSaveState.getState().isLocked(form)).toBe(false)
  })

  it('locks each form independently', () => {
    // Two different sets landing in quick succession is legitimate; the same
    // one twice is not.
    useSaveState.getState().lock('set-100')
    expect(useSaveState.getState().isLocked('set-101')).toBe(false)
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

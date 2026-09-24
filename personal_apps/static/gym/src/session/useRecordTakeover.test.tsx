import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRecordTakeover, TAKEOVER_MS } from './useRecordTakeover'
import { payload as fixture } from './types.test-d'
import type { LiveRecord, SessionDetailPayload } from './types'

/* The hook is the whole trigger. Everything else is presentation, so these
 * pin WHEN a record celebrates rather than what it looks like: the failures
 * that matter are celebrating on a reload and not celebrating at all. */

const RECORD: LiveRecord = {
  kind: 'e1rm', value: 82.5, previous: 80.0,
  previous_at: '2026-09-09T18:30:00',
}

/** The fixture with a chosen set marked as a record. */
function withRecord(setIds: number[], record: LiveRecord = RECORD): SessionDetailPayload {
  return {
    ...fixture,
    record_set_ids: setIds,
    record_details: Object.fromEntries(setIds.map((id) => [String(id), record])),
  }
}

const firstSetId = fixture.visible_exercises[0]!.sets[0]!.id
const secondSetId = fixture.visible_exercises[0]!.sets[1]!.id

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('useRecordTakeover', () => {
  it('says nothing about records that were already there on the first payload', () => {
    // Reloading mid-workout, resuming after a phone lock, coming back from the
    // exercise page: the payload arrives with records in it and none of them
    // just happened.
    const { result } = renderHook(() => useRecordTakeover(withRecord([firstSetId])))
    expect(result.current.celebration).toBeNull()
  })

  it('fires when a set id that was not there before arrives', () => {
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    expect(result.current.celebration).toBeNull()
    rerender(withRecord([firstSetId]))

    expect(result.current.celebration).not.toBeNull()
    expect(result.current.celebration!.setId).toBe(firstSetId)
    expect(result.current.celebration!.record.previous).toBe(80.0)
    expect(result.current.celebration!.exerciseName)
      .toBe(fixture.visible_exercises[0]!.name)
    expect(result.current.celebration!.ordinal).toBe(1)
  })

  it('does not fire again for a payload that carries the same records', () => {
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender(withRecord([firstSetId]))
    act(() => { vi.advanceTimersByTime(TAKEOVER_MS) })
    expect(result.current.celebration).toBeNull()

    // A follower's five-second poll, a refetch, any re-render at all.
    rerender(withRecord([firstSetId]))
    expect(result.current.celebration).toBeNull()
  })

  it('clears itself after one second', () => {
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender(withRecord([firstSetId]))
    expect(result.current.celebration).not.toBeNull()

    act(() => { vi.advanceTimersByTime(TAKEOVER_MS - 1) })
    expect(result.current.celebration).not.toBeNull()
    act(() => { vi.advanceTimersByTime(1) })
    expect(result.current.celebration).toBeNull()
  })

  it('can be dismissed early', () => {
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender(withRecord([firstSetId]))
    act(() => { result.current.dismiss() })
    expect(result.current.celebration).toBeNull()
  })

  it('celebrates the newest set when one payload brings several', () => {
    // Two writes queued behind each other land together. The set logged last
    // is the one the lifter is standing over.
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender(withRecord([firstSetId, secondSetId]))
    expect(result.current.celebration!.setId).toBe(secondSetId)
    expect(result.current.celebration!.ordinal).toBe(2)
  })

  it('fires again when a record set is un-ticked and ticked once more', () => {
    // Not a bug to suppress: that is a lifter re-logging a real record.
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender(withRecord([firstSetId]))
    act(() => { result.current.dismiss() })
    rerender(withRecord([]))
    expect(result.current.celebration).toBeNull()

    rerender(withRecord([firstSetId]))
    expect(result.current.celebration).not.toBeNull()
  })

  it('stays silent when the id arrives without a detail to show', () => {
    // Server-side the two are built in one loop, so this cannot happen -- but
    // a half-populated payload must degrade to the quiet note, not to a slab
    // reading "undefined kg".
    const { result, rerender } = renderHook(
      (p: SessionDetailPayload) => useRecordTakeover(p),
      { initialProps: withRecord([]) })

    rerender({ ...fixture, record_set_ids: [firstSetId], record_details: {} })
    expect(result.current.celebration).toBeNull()
  })
})

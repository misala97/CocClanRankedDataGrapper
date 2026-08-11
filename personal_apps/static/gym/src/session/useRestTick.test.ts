import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRestTick } from './useRestTick'

/**
 * The countdown between sets. Derived from the server's rest_ends_at rather
 * than owned by the client -- the server decides when a rest ends, and the
 * client only draws it.
 *
 * The behaviour worth preserving from the original is that it is keyed on the
 * rest's OWN end time. The old startRestTick re-ran after every refresh, and a
 * rest that is merely still running is not news; announcing it again on each
 * mutation would talk over a lifter mid-set.
 */
const T0 = new Date('2026-08-10T12:00:00Z').getTime()

/** The payload stores naive UTC, no zone suffix -- same convention as every
 *  other timestamp in this app. */
const iso = (msFromT0: number) =>
  new Date(T0 + msFromT0).toISOString().replace('Z', '')

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(T0)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useRestTick', () => {
  it('reports the time left and counts it down', () => {
    const { result } = renderHook(() => useRestTick(iso(90_000), 90))
    expect(result.current.running).toBe(true)
    expect(result.current.remaining).toBe(90)

    act(() => { vi.advanceTimersByTime(30_000) })
    expect(result.current.remaining).toBe(60)
  })

  it('reports progress as a fraction of the whole rest', () => {
    const { result } = renderHook(() => useRestTick(iso(90_000), 90))
    expect(result.current.progress).toBeCloseTo(0)

    act(() => { vi.advanceTimersByTime(45_000) })
    expect(result.current.progress).toBeCloseTo(0.5, 1)
  })

  it('fires onOver exactly once, and clamps rather than going negative', () => {
    const onOver = vi.fn()
    const { result } = renderHook(() => useRestTick(iso(10_000), 10, { onOver }))

    act(() => { vi.advanceTimersByTime(10_000) })
    expect(onOver).toHaveBeenCalledOnce()
    expect(result.current.running).toBe(false)
    expect(result.current.remaining).toBe(0)
    expect(result.current.progress).toBe(1)

    // Keeps ticking past zero without firing again -- the server still thinks
    // a rest is running, so the component stays mounted with the same props.
    act(() => { vi.advanceTimersByTime(30_000) })
    expect(onOver).toHaveBeenCalledOnce()
    expect(result.current.remaining).toBe(0)
  })

  it('announces a rest starting once per distinct end time, not per render', () => {
    const onStart = vi.fn()
    const { rerender } = renderHook(
      ({ ends }) => useRestTick(ends, 90, { onStart }),
      { initialProps: { ends: iso(90_000) } })
    expect(onStart).toHaveBeenCalledOnce()

    // A mutation elsewhere re-renders with the SAME rest still running. The
    // original keyed on endsAt precisely so this stays silent.
    rerender({ ends: iso(90_000) })
    expect(onStart).toHaveBeenCalledOnce()

    // A genuinely new rest is news again.
    rerender({ ends: iso(180_000) })
    expect(onStart).toHaveBeenCalledTimes(2)
  })

  it('restarts cleanly when a new rest replaces a running one', () => {
    const { result, rerender } = renderHook(
      ({ ends }) => useRestTick(ends, 90),
      { initialProps: { ends: iso(90_000) } })

    act(() => { vi.advanceTimersByTime(60_000) })
    expect(result.current.remaining).toBe(30)

    rerender({ ends: iso(60_000 + 90_000) })
    expect(result.current.remaining).toBe(90)
    expect(result.current.running).toBe(true)
  })

  it('is idle when nothing is resting', () => {
    const onStart = vi.fn()
    const { result } = renderHook(() => useRestTick(null, 0, { onStart }))
    expect(result.current.running).toBe(false)
    expect(result.current.remaining).toBe(0)
    expect(onStart).not.toHaveBeenCalled()
  })

  it('does not announce a rest that already elapsed before mount', () => {
    // Reloading the page after the rest ended must not say it is running.
    const onStart = vi.fn()
    const onOver = vi.fn()
    const { result } = renderHook(() => useRestTick(iso(-5_000), 90, { onStart, onOver }))
    expect(result.current.running).toBe(false)
    expect(onStart).not.toHaveBeenCalled()
  })

  it('clears its timer on unmount', () => {
    const onOver = vi.fn()
    const { unmount } = renderHook(() => useRestTick(iso(10_000), 10, { onOver }))
    unmount()
    act(() => { vi.advanceTimersByTime(30_000) })
    expect(onOver).not.toHaveBeenCalled()
  })

  it('treats a zero total as nothing to draw', () => {
    // rest_total_seconds is 0 when nothing is resting, and the progress bar
    // divides by it.
    const { result } = renderHook(() => useRestTick(iso(10_000), 0))
    expect(result.current.progress).toBe(1)
    expect(Number.isFinite(result.current.progress)).toBe(true)
  })
})

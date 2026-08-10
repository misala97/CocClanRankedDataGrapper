import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWakeLock } from './useWakeLock'

function stubWakeLock() {
  const release = vi.fn(async () => {})
  const request = vi.fn(async () => ({ release }) as unknown as WakeLockSentinel)
  Object.defineProperty(navigator, 'wakeLock', {
    value: { request }, configurable: true,
  })
  return { request, release }
}

beforeEach(() => {
  Object.defineProperty(document, 'visibilityState', {
    value: 'visible', configurable: true,
  })
})

afterEach(() => {
  // @ts-expect-error -- remove the stub between tests
  delete navigator.wakeLock
})

describe('useWakeLock', () => {
  it('requests a screen lock while active', async () => {
    const { request } = stubWakeLock()
    renderHook(() => useWakeLock(true))
    expect(request).toHaveBeenCalledWith('screen')
  })

  it('does nothing when inactive or unsupported', () => {
    const { request } = stubWakeLock()
    renderHook(() => useWakeLock(false))
    expect(request).not.toHaveBeenCalled()
  })

  it('reacquires when the page becomes visible again', () => {
    // The platform releases the lock on every hide and never reacquires --
    // that half is ours.
    const { request } = stubWakeLock()
    renderHook(() => useWakeLock(true))
    document.dispatchEvent(new Event('visibilitychange'))
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('does not reacquire while hidden', () => {
    const { request } = stubWakeLock()
    renderHook(() => useWakeLock(true))
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden', configurable: true,
    })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('releases on unmount', async () => {
    const { release } = stubWakeLock()
    const { unmount } = renderHook(() => useWakeLock(true))
    // let the request promise resolve so the sentinel is held
    await Promise.resolve()
    unmount()
    expect(release).toHaveBeenCalled()
  })
})

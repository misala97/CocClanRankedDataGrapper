import { useEffect } from 'react'

/**
 * Keeps the screen on while a workout is live.
 *
 * A phone locking mid-set is the single most common interruption this screen
 * has: rest runs out, the lifter looks down, the display is dark. The Screen
 * Wake Lock API exists for exactly this.
 *
 * The lock is RELEASED BY THE PLATFORM every time the page is hidden --
 * switching apps, locking manually -- which is correct (the platform knows
 * better than we do when the screen must be allowed to sleep). What the
 * platform does not do is reacquire, so the visibilitychange listener asks
 * again whenever the workout returns to the foreground.
 *
 * Everything is best-effort and silent. The API needs a secure context
 * (HTTPS in prod, localhost in dev -- the LAN-IP phone test has neither and
 * simply keeps the OS timeout), the browser may refuse on battery saver, and
 * a tracker must never surface an error about screen politics.
 */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return

    let lock: WakeLockSentinel | null = null
    let gone = false

    const acquire = () => {
      if (gone || document.visibilityState !== 'visible') return
      navigator.wakeLock.request('screen')
        .then((sentinel) => {
          if (gone) { void sentinel.release(); return }
          lock = sentinel
        })
        .catch(() => { /* refused: battery saver, policy -- fine */ })
    }

    acquire()
    document.addEventListener('visibilitychange', acquire)
    return () => {
      gone = true
      document.removeEventListener('visibilitychange', acquire)
      void lock?.release().catch(() => { /* already released */ })
    }
  }, [active])
}

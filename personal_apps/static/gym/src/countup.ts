import { useEffect, useRef, useState } from 'react'

/**
 * Tween a number towards `target`, ease-out, honouring prefers-reduced-motion.
 *
 * Shared because two screens count: the session total ticks up 220ms every
 * time a set lands, and the record takeover's slab runs the same tween over
 * 520ms from the beaten weight to the new one. Two copies of a tween drift --
 * the clamp below was a real bug fixed in one of them, and a second copy would
 * still have it.
 *
 * `counting` is true while the tween runs, for a class that lights the digits
 * so the movement has a reason attached.
 */
export function useCountUp(target: number, durationMs: number): {
  shown: number
  counting: boolean
} {
  const [shown, setShown] = useState(target)
  const [counting, setCounting] = useState(false)
  const shownRef = useRef(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    const from = shownRef.current
    if (from === target) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      shownRef.current = target
      setShown(target)
      return
    }
    const t0 = performance.now()
    setCounting(true)
    const step = (t: number) => {
      // Clamped below as well: the first frame's timestamp can PREDATE t0
      // (rAF stamps the frame's start, not the callback's), and a negative k
      // pushed the eased value below `from` -- the count flashed "-120" on
      // its way to 960.
      const k = Math.min(1, Math.max(0, (t - t0) / durationMs))
      const eased = 1 - Math.pow(1 - k, 3)
      shownRef.current = from + (target - from) * eased
      setShown(shownRef.current)
      if (k < 1) {
        rafRef.current = requestAnimationFrame(step)
      } else {
        shownRef.current = target
        setCounting(false)
        rafRef.current = null
      }
    }
    rafRef.current = requestAnimationFrame(step)
    return () => {
      // A new target mid-tween starts from wherever the count visibly is.
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, durationMs])

  return { shown, counting }
}

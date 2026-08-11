import { useEffect, useRef, useState } from 'react'

interface Options {
  /** Fired once when a rest begins, and again only for a genuinely different
   *  rest. The original keyed this on the rest's own end time because
   *  startRestTick re-ran after every refresh, and a rest that is merely still
   *  running is not news -- re-announcing it would talk over a lifter mid-set. */
  onStart?(remainingSeconds: number): void
  /** Fired once when the countdown reaches zero. No refetch happens here: the
   *  server still thinks a rest is running, and it is right to. */
  onOver?(): void
}

export interface RestTick {
  running: boolean
  /** Whole seconds left, never negative. */
  remaining: number
  /** 0 at the start, 1 when elapsed. Drawn as scaleX, so it must stay finite
   *  even when total is 0 -- which it is whenever nothing is resting. */
  progress: number
}

/**
 * The countdown between sets, derived from the server's `rest_ends_at`.
 *
 * Timestamps are stored naive-UTC throughout this app, so the 'Z' is appended
 * here rather than assumed. Getting that wrong shifts every countdown by the
 * timezone offset, which on CEST would mean a two-hour rest.
 */
export function useRestTick(
  restEndsAt: string | null,
  totalSeconds: number,
  { onStart, onOver }: Options = {},
): RestTick {
  const endsAt = restEndsAt === null
    ? null
    : new Date(`${restEndsAt}Z`).getTime()

  const [now, setNow] = useState(() => Date.now())

  // Keyed on the rest's own end time, not on "is a rest running".
  const announced = useRef<number | null>(null)
  const fired = useRef<number | null>(null)
  const onStartRef = useRef(onStart)
  const onOverRef = useRef(onOver)
  onStartRef.current = onStart
  onOverRef.current = onOver

  useEffect(() => {
    if (endsAt === null) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [endsAt])

  const remainingMs = endsAt === null ? 0 : Math.max(0, endsAt - now)
  const running = endsAt !== null && remainingMs > 0

  useEffect(() => {
    if (endsAt === null || announced.current === endsAt) return
    // A rest that already elapsed before this mounted is not starting.
    if (endsAt > Date.now()) {
      announced.current = endsAt
      onStartRef.current?.(Math.round((endsAt - Date.now()) / 1000))
    }
  }, [endsAt])

  useEffect(() => {
    if (endsAt === null || running || fired.current === endsAt) return
    // Only for a rest this hook actually watched run down: one that was
    // already over at mount never announced its start either.
    if (announced.current !== endsAt) return
    fired.current = endsAt
    onOverRef.current?.()
  }, [endsAt, running])

  return {
    running,
    remaining: Math.round(remainingMs / 1000),
    progress: totalSeconds > 0
      ? Math.min(1, 1 - remainingMs / (totalSeconds * 1000))
      : 1,
  }
}

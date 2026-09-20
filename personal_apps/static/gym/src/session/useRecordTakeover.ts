import { useCallback, useEffect, useRef, useState } from 'react'
import type { LiveRecord, SessionDetailPayload } from './types'

/** Slab in, number lands at 660ms and holds, exit starts at 820, gone at 1000.
 *  One second start to finish: long enough for the number to read, short
 *  enough that it is over before you are ready to lift again. */
export const TAKEOVER_MS = 1000

export interface Celebration {
  setId: number
  record: LiveRecord
  /** The exercise the set belongs to, for the slab's second line. */
  exerciseName: string
  /** 1-based position of the set within its exercise. */
  ordinal: number
  /** The slot the exercise is in this workout. */
  position: number
}

/**
 * Fires the record takeover at the moment a set's chip goes gold.
 *
 * There is no prediction and no second clock: `record_set_ids` is computed
 * server-side and arrives with the payload that a write returns, so the
 * celebration is triggered by the same data that turns the chip gold, at the
 * same render. On a slow connection both are late together, which is the
 * honest behaviour -- a confetti burst that beat the chip to the screen would
 * be celebrating a record the server had not confirmed.
 *
 * The seen-set is seeded on the first payload WITHOUT firing. Opening a
 * workout that already contains records -- a reload, resuming after a phone
 * lock, coming back from the exercise page -- is reading, not setting one.
 *
 * Un-ticking a record set and ticking it again does fire again. That is a
 * lifter re-logging a real record, not a bug to suppress.
 */
export function useRecordTakeover(payload: SessionDetailPayload): {
  celebration: Celebration | null
  dismiss(): void
} {
  const seen = useRef<Set<number> | null>(null)
  const [celebration, setCelebration] = useState<Celebration | null>(null)

  useEffect(() => {
    const current = new Set(payload.record_set_ids)

    if (seen.current === null) {
      seen.current = current
      return
    }

    // Newest first: when one payload brings several (a queued write landing
    // behind another), the last one logged is the one being celebrated.
    const fresh = payload.record_set_ids
      .filter((id) => !seen.current!.has(id))
      .sort((a, b) => b - a)
    seen.current = current

    const setId = fresh[0]
    if (setId === undefined) return

    const record = payload.record_details[String(setId)]
    if (record === undefined) return

    for (const se of payload.visible_exercises) {
      const index = se.sets.findIndex((s) => s.id === setId)
      if (index === -1) continue
      setCelebration({
        setId, record, exerciseName: se.name,
        ordinal: index + 1, position: se.position,
      })
      return
    }
  }, [payload])

  const dismiss = useCallback(() => setCelebration(null), [])

  useEffect(() => {
    if (celebration === null) return
    const timer = setTimeout(() => setCelebration(null), TAKEOVER_MS)
    return () => clearTimeout(timer)
  }, [celebration])

  return { celebration, dismiss }
}
